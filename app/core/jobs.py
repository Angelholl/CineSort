"""后台任务编排：扫描 / 执行 / 回滚（单工作线程，GUI 轮询进度与日志）。"""
from __future__ import annotations

import threading
import traceback
import uuid
from pathlib import Path

from . import fsops, preflight
from . import learned as learned_store
from . import scanner as scanner_mod
from .config import check_session_root, load_config
from .journal import Journal, done_entries, is_valid_session_name
from .planner import (
    READY,
    ST_BATCH,
    build_plan,
    check_plan_freshness,
    load_plan,
    mark_applied,
    mark_undone,
    save_plan,
    session_dst_root,
    unit_dst_dir,
)


class BusyError(RuntimeError):
    pass


class Job:
    def __init__(self, kind: str):
        self.id = uuid.uuid4().hex[:8]
        self.kind = kind
        self.status = "running"          # running | done | failed
        self.total = 0
        self.cur = 0
        self.label = ""
        self.log_lines: list[str] = []
        self.error: str | None = None
        self.result: dict = {}
        self.cancel = False
        self._lock = threading.Lock()

    def log(self, msg: str) -> None:
        with self._lock:
            self.log_lines.append(msg)
            if len(self.log_lines) > 500:
                del self.log_lines[: len(self.log_lines) - 500]

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "id": self.id, "kind": self.kind, "status": self.status,
                "total": self.total, "cur": self.cur, "label": self.label,
                "log": list(self.log_lines[-300:]),
                "error": self.error, "result": dict(self.result),
            }


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.job: Job | None = None

    def start(self, kind: str, fn) -> Job:
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise BusyError("已有任务在运行，请等待完成")
            job = Job(kind)

            def runner():
                try:
                    fn(job)
                    job.status = "done"
                except Exception as exc:  # noqa: BLE001
                    job.error = str(exc)
                    job.log(f"任务失败：{exc}")
                    traceback.print_exc()
                    job.status = "failed"

            self._thread = threading.Thread(target=runner, daemon=True)
            self.job = job
            self._thread.start()
            return job

    def cancel(self) -> bool:
        if self.job and self.job.status == "running":
            self.job.cancel = True
            self.job.log("已请求取消，将在当前单元完成后停止")
            return True
        return False


def _src_dir(unit: dict) -> str:
    """日志/回滚用的源目录：目录单元为自身，散装文件单元为其所在目录。"""
    if unit["kind"] == "file":
        return str(Path(unit["src"]).parent)
    return str(Path(unit["src"]))


def run_preflight(state, job: Job, ids: list[str]) -> None:
    """体检任务：run_preflight 必须离开 UI/HTTP 请求线程——内部有
    tasklist 子进程（最长 15s）+ 磁盘空间探测 + staging 目录遍历，
    同步调用会把界面冻住（D-20261102-01 纪律 1）。"""
    cfg = load_config(state.config_path)
    plan = load_plan(cfg.runtime_dir)
    job.label = "执行前体检"
    job.log("开始执行前体检（Jellyfin 进程 / 磁盘空间 / staging 残留…）")
    items = preflight.run_preflight(cfg, plan, selected_ids=set(ids) or None)
    blocks = [i for i in items if i["level"] == "block"]
    warns = [i for i in items if i["level"] == "warn"]
    job.result = {"items": items, "ids": sorted(ids)}
    job.log(f"体检完成：{len(items)} 项"
            f"（阻断 {len(blocks)} / 警告 {len(warns)} / 提示 {len(items) - len(blocks) - len(warns)}）")


def run_scan(state, job: Job) -> None:
    cfg = load_config(state.config_path)
    job.log(f"开始扫描源目录：{cfg.source_root}")
    units, notes = scanner_mod.scan_source_root(cfg)
    job.total = len(units)
    plan = build_plan(cfg, units, notes)
    save_plan(cfg.runtime_dir, plan)
    state.invalidate_plan()
    st = plan["stats"]
    job.log(
        f"扫描完成：影片单元 {st['total']} 个；可执行 {st['ready']} 个"
        f"（规则 {st['ready_levels'].get('rule', 0)}"
        f" / 摘要预判 {st['ready_levels'].get('plot', 0)}"
        f" / 兜底 {st['ready_levels'].get('fallback', 0)}）"
    )
    job.result = st


def run_apply(state, job: Job, ids: list[str], acks: set[str],
              overrides: dict[str, str], output_root: str | None = None,
              group_by_category: bool = True) -> None:
    cfg = load_config(state.config_path)
    plan = load_plan(cfg.runtime_dir)
    if not plan:
        raise RuntimeError("没有可执行的计划，请先在「分类计划」页扫描")
    problems = check_plan_freshness(cfg, plan, only_ids=set(ids))
    if problems:
        raise RuntimeError("计划已过期，未执行任何操作。" + "；".join(problems[:5]))
    units = [u for u in plan["units"] if u["id"] in set(ids)]
    # ST_BATCH（整目录待改判）仅在人工指定目标库后放行
    bad = [u["id"] for u in units
           if u["status"] != READY
           and not (u["status"] == ST_BATCH and overrides.get(u["id"]))]
    if bad:
        raise RuntimeError("以下影片不在可执行状态：" + "、".join(bad))
    if not units:
        raise RuntimeError("未选择任何影片")

    # 逐行覆盖目标库（内存改写，不写 plan.json）
    for u in units:
        ov = overrides.get(u["id"])
        if not ov:
            continue
        if ov == "__fallback__":
            u["target_lib"] = "兜底库"
            u["target_root"] = str(cfg.fallback_path)
        else:
            lib = cfg.libraries.get(ov)
            if not lib:
                raise RuntimeError(f"无效的覆盖目标：{ov}")
            u["target_lib"] = ov
            u["target_root"] = str(lib.path)
        u["dst_dir"] = str(unit_dst_dir(u["target_root"], u.get("actress"), u["dst_name"]))
        u["evidence"] = list(u["evidence"]) + ["目标库由人工指定"]

    # 本次输出目录（会话级覆盖，只计算不改盘）
    extra_roots = None
    if output_root:
        err = check_session_root(output_root, cfg)
        if err:
            raise RuntimeError(f"输出目录不可用：{err}")   # 先于任何文件操作
        out = Path(output_root)
        for u in units:
            root = session_dst_root(out, u["target_lib"], group_by_category)
            u["target_root"] = str(root)
            u["dst_dir"] = str(unit_dst_dir(root, u.get("actress"), u["dst_name"]))
            u["evidence"] = list(u["evidence"]) + ["本次输出目录（会话级，不改全局配置）"]
        extra_roots = sorted({fsops.staging_for_root(Path(u["target_root"]))
                              for u in units}, key=str)
        job.log(f"本次输出目录：{output_root}"
                + ("（按类别建子文件夹）" if group_by_category else "（平铺）"))

    pf = preflight.run_preflight(cfg, plan, selected_ids=set(ids),
                                 extra_staging_roots=extra_roots)
    blocks = [i for i in pf if i["level"] == "block" and i["code"] not in acks]
    if blocks:
        raise RuntimeError("预检未通过，未执行任何操作：" + "；".join(
            f"[{b['code']}] {b['message']}" for b in blocks))

    # 输出模式下补建类别根目录（必须在阻断门之后，避免被阻断时留下空目录）
    if output_root:
        for root in sorted({u["target_root"] for u in units}):
            Path(root).mkdir(parents=True, exist_ok=True)

    job.total = len(units)
    jr = Journal(cfg.runtime_dir / "journals", "apply", {
        "plan_id": plan["plan_id"], "config_hash": cfg.config_hash(),
        "ids": sorted(ids),
    })
    moved = failed = 0
    failures: list[dict] = []
    done_ids: list[str] = []
    try:
        for u in units:
            if job.cancel:
                jr.event(msg="用户取消")
                job.log("已取消：剩余影片未处理")
                break
            src = Path(u["src"])
            dst = Path(u["dst_dir"])
            job.label = u["label"]
            if dst.exists():                     # TOCTOU 终检
                jr.aborted(unit_id=u["id"], src_dir=_src_dir(u), dst_dir=str(dst),
                           reason="执行时发现目标已存在")
                failed += 1
                failures.append({"label": u["label"], "error": "执行时发现目标已存在"})
                job.cur = moved + failed
                job.log(f"❌ {u['label']}：执行时发现目标已存在")
                continue
            expected = {rel: size for rel, size, _mt in u["files"]}
            jr.intent(unit_id=u["id"], kind=u["kind"], src_dir=_src_dir(u),
                      dst_dir=str(dst), bytes=u["total_size"], files=len(expected))
            job.log(f"▶ {u['label']} → {u['target_lib']}")
            try:
                staging = fsops.staging_for_root(Path(u["target_root"]))
                if u["kind"] == "dir":
                    dst.parent.mkdir(parents=True, exist_ok=True)  # 女优目录缺失时自动创建
                    info = fsops.transfer_dir(src, dst, staging, expected)
                else:
                    files_abs = [src.parent / rel for rel in expected]
                    info = fsops.transfer_loose(files_abs, dst, staging, expected)
                jr.done(unit_id=u["id"], src_dir=_src_dir(u), dst_dir=str(dst),
                        kind=u["kind"], mode=info.get("mode"), files=expected,
                        bytes=u["total_size"], target_lib=u["target_lib"])
                moved += 1
                done_ids.append(u["id"])
                job.cur = moved + failed
                job.log(f"✅ {u['label']} → {u['target_lib']}（{info.get('mode')}）")
            except Exception as exc:  # noqa: BLE001
                jr.aborted(unit_id=u["id"], src_dir=_src_dir(u), dst_dir=str(dst),
                           reason=str(exc))
                failed += 1
                failures.append({"label": u["label"], "error": str(exc)})
                job.cur = moved + failed
                job.log(f"❌ {u['label']}：{exc}")
    finally:
        jr.close()
    if done_ids:
        mark_applied(cfg.runtime_dir, done_ids)
        state.invalidate_plan()
        if cfg.learning.enabled:
            # 自学习沉淀（D-20261101-03）：人工改判×2票，确认结果×1票。
            # 复合单元整目录改判不入学习：其 NFO 至多描述其中一部影片，
            # 不为占位分类记账（计划 Task-05「learned 空转」的落实）。
            for u in units:
                if u["id"] in set(done_ids) and not u.get("composite"):
                    learned_store.record(cfg.runtime_dir, u["genres"],
                                         u["target_lib"],
                                         manual=u["id"] in overrides)
    job.result = {"moved": moved, "failed": failed, "failures": failures,
                  "session": jr.sid}


def run_undo(state, job: Job, fname: str) -> None:
    cfg = load_config(state.config_path)
    if not is_valid_session_name(fname):
        raise RuntimeError("非法的会话文件名")
    path = cfg.runtime_dir / "journals" / fname
    if not path.is_file():
        raise RuntimeError("会话日志不存在")
    dones = done_entries(path)
    if not dones:
        raise RuntimeError("该会话没有可回滚的成功记录")
    job.total = len(dones)
    jr = Journal(cfg.runtime_dir / "journals", "undo", {"undoes": fname})
    restored = skipped = failed = 0
    failures: list[dict] = []
    undone_ids: list[str] = []
    try:
        for e in reversed(dones):
            if job.cancel:
                jr.event(msg="用户取消")
                break
            dst_dir = Path(e.get("dst_dir", ""))
            src_dir = Path(e.get("src_dir", ""))
            kind = e.get("kind", "dir")
            uid = e.get("unit_id", "?")
            job.label = f"回滚 {uid}"
            if not dst_dir.exists():
                skipped += 1
                jr.aborted(unit_id=uid, reason="待还原目录不存在，可能已被手动移动")
                job.log(f"⏭ {uid}：目标不存在，跳过")
                continue
            if kind == "dir" and src_dir.exists():
                skipped += 1
                jr.aborted(unit_id=uid, reason="源位置已存在同名目录，跳过")
                job.log(f"⏭ {uid}：源位置已存在，跳过")
                continue
            expected = dict(e.get("files") or {})
            jr.intent(unit_id=uid, kind=kind, src_dir=str(src_dir), dst_dir=str(dst_dir))
            try:
                if kind == "dir":
                    fsops.transfer_dir(dst_dir, src_dir,
                                       fsops.staging_for_root(cfg.source_root), expected)
                else:
                    fsops.restore_loose(dst_dir, src_dir, expected)
                jr.done(unit_id=uid, src_dir=str(src_dir), dst_dir=str(dst_dir),
                        kind=kind, files=expected)
                restored += 1
                undone_ids.append(uid)
                job.cur += 1
                job.log(f"✅ 已还原 {uid}")
            except Exception as exc:  # noqa: BLE001
                jr.aborted(unit_id=uid, reason=str(exc))
                failed += 1
                failures.append({"label": uid, "error": str(exc)})
                job.log(f"❌ {uid}：{exc}")
    finally:
        jr.close()
    if undone_ids:
        mark_undone(cfg.runtime_dir, undone_ids)
        state.invalidate_plan()
    job.result = {"restored": restored, "skipped": skipped, "failed": failed,
                  "failures": failures, "session": jr.sid}

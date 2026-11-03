"""共享应用状态：配置路径 / 计划缓存 / 任务管理器。与任何 UI 形态（HTTP 或原生窗口）无关。"""
from __future__ import annotations

import threading
from pathlib import Path

import tomllib

from . import __version__
from .core import jobs as jobs_mod
from .core import learned as learned_store
from .core import preflight
from .core.config import (
    ConfigError,
    describe,
    load_config,
    raw_describe,
    save_config_dict,
)
from .core.journal import done_entries, is_valid_session_name, list_sessions
from .core.planner import load_plan, plan_digest


class AppState:
    """共享状态与操作入口：配置路径 / 计划缓存 / 任务管理器。

    这里承载全部"用户可触发"的操作（扫描/执行/回滚/体检/配置…），
    使 HTTP 层与原生 GUI 层都只做参数归一化与渲染，不重复业务编排。
    """

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self.jobs = jobs_mod.JobManager()
        self._plan_lock = threading.Lock()
        self._plan_cache: dict | None = None

    def runtime_dir(self) -> Path:
        return self.config_path.parent / "runtime"

    def plan(self) -> dict | None:
        with self._plan_lock:
            if self._plan_cache is None:
                self._plan_cache = load_plan(self.runtime_dir())
            return self._plan_cache

    def invalidate_plan(self) -> None:
        with self._plan_lock:
            self._plan_cache = None

    def config_describe(self) -> tuple[dict | None, str | None]:
        try:
            cfg = load_config(self.config_path)
            return describe(cfg), None
        except ConfigError as exc:
            err = str(exc)
        # 配置非法时用示例/原始文件兜底展示，便于 GUI 首跑编辑
        for candidate in (self.config_path,
                          self.config_path.parent / "config.example.toml"):
            try:
                with open(candidate, "rb") as fh:
                    return raw_describe(tomllib.load(fh)), err
            except (OSError, tomllib.TOMLDecodeError):
                continue
        return None, err

    def state_snapshot(self) -> dict:
        cfg_desc, cfg_error = self.config_describe()
        plan = self.plan()
        return {
            "ok": True,
            "version": __version__,
            "config_path": str(self.config_path),
            "config": cfg_desc,
            "config_error": cfg_error,
            "plan": plan,
            "plan_digest": plan_digest(plan) if plan else None,
            "job": self.job_snapshot(),
            "sessions": list_sessions(self.runtime_dir() / "journals"),
            "learned": learned_store.items(learned_store.load(self.runtime_dir())),
        }

    # ------------------------------------------------------- 任务与操作入口

    def job_snapshot(self) -> dict | None:
        return self.jobs.job.snapshot() if self.jobs.job else None

    def start_scan(self) -> dict:
        """启动扫描任务。BusyError 由 JobManager 抛出，不在此吞掉。"""
        self.jobs.start("scan", lambda job: jobs_mod.run_scan(self, job))
        return {"ok": True}

    def start_apply(self, ids: list[str], acks: set[str],
                    overrides: dict[str, str]) -> dict:
        self.jobs.start("apply", lambda job: jobs_mod.run_apply(
            self, job, ids, acks, overrides))
        return {"ok": True}

    def start_undo(self, fname: str) -> dict:
        self.jobs.start("undo", lambda job: jobs_mod.run_undo(self, job, fname))
        return {"ok": True}

    def start_preflight(self, ids: list[str]) -> dict:
        """后台体检。结果（含阻断项清单）在 job.result["items"]，
        由调用方在任务完成后读取——不得在 UI 线程同步调用 preflight_items。"""
        self.jobs.start("preflight",
                        lambda job: jobs_mod.run_preflight(self, job, list(ids)))
        return {"ok": True}

    def cancel_job(self) -> bool:
        return self.jobs.cancel()

    def sessions(self) -> list[dict]:
        """回滚会话清单（慢活：读 journals 目录，只允许在慢 tick 调用）。"""
        return list_sessions(self.runtime_dir() / "journals")

    def undo_preview(self, fname: str) -> dict:
        if not is_valid_session_name(fname):
            raise ValueError("非法的会话文件名")
        path = self.runtime_dir() / "journals" / fname
        if not path.is_file():
            raise ValueError("会话日志不存在")
        ops = []
        for e in reversed(done_entries(path)):
            dst = Path(e.get("dst_dir", ""))
            src = Path(e.get("src_dir", ""))
            st = "ok"
            if not dst.exists():
                st = "skip_target_missing"
            elif e.get("kind", "dir") == "dir" and src.exists():
                st = "skip_src_exists"
            ops.append({"unit_id": e.get("unit_id", "?"), "kind": e.get("kind", "dir"),
                        "src_dir": str(src), "dst_dir": str(dst), "state": st})
        return {"ops": ops, "file": fname}

    def preflight_items(self, ids: set[str] | None = None) -> list[dict]:
        # 注意：内部含 tasklist 子进程（最长 15s）与磁盘遍历，调用方不得在
        # UI 线程直接调用（D-20261102-01 纪律 1）。后台化在后续卡处理。
        cfg = load_config(self.config_path)
        return preflight.run_preflight(cfg, self.plan(), selected_ids=ids or None)

    def cleanup_staging(self) -> int:
        # 同上：目录遍历属慢活，不得在 UI 线程直接调用。
        return preflight.cleanup_staging(load_config(self.config_path))

    def learned_forget(self, key: str, lib: str) -> list[dict]:
        learned_store.forget(self.runtime_dir(), key, lib)
        return learned_store.items(learned_store.load(self.runtime_dir()))

    def save_config(self, data: dict) -> dict:
        new_cfg = save_config_dict(self.config_path, data)
        self.invalidate_plan()          # 配置已变，旧计划按哈希自动过期
        return describe(new_cfg)

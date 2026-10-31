"""计划构建 / 冻结 / 漂移校验（评议条件 C3 / C7）。

- 计划一经扫描即冻结（plan.json 内含配置哈希 + 每单元文件快照），
  apply 只消费冻结计划，配置或源漂移即拒绝，杜绝 TOCTOU；
- 冲突三分：同名异片 / 已在位（同 provider id）/ 半成品残留；
- 同 provider id 多个目录 → 多版本，默认不选入批量执行。
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from . import learned as learned_store
from .classifier import classify, map_genres
from .config import Config
from .nfo import parse_nfo_file
from .scanner import _analyze_loose, find_nfo, snapshot_dir

READY = "ready"
ST_CONFLICT = "conflict_name"
ST_PLACED = "already_placed"
ST_INCOMPLETE = "incomplete_leftover"
ST_MULTI = "multi_version"
ST_APPLIED = "applied"

MARKER_PREFIX = ".incomplete-"

STATUS_LABELS = {
    READY: "可执行", ST_CONFLICT: "同名冲突", ST_PLACED: "已在位",
    ST_INCOMPLETE: "半成品残留", ST_MULTI: "多版本需确认", ST_APPLIED: "已执行",
}


def _existing_dir(dst_dir: Path) -> Path | None:
    """大小写不敏感地查找已存在的同名目录（Windows）。"""
    parent = dst_dir.parent
    if not parent.is_dir():
        return None
    key = dst_dir.name.casefold()
    for c in parent.iterdir():
        if c.is_dir() and c.name.casefold() == key:
            return c
    return None


def _has_incomplete_marker(d: Path) -> bool:
    try:
        return any(c.name.startswith(MARKER_PREFIX) for c in d.iterdir() if c.is_file())
    except OSError:
        return False


def _quick_provider(d: Path) -> str | None:
    nfo_path = find_nfo(d, [], False)
    if not nfo_path:
        return None
    return parse_nfo_file(nfo_path).provider_id


def build_plan(cfg: Config, units, notes: list[dict]) -> dict:
    created = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    learned = learned_store.load(cfg.runtime_dir)
    plan_units: list[dict] = []
    for u in units:
        dec = classify(u, cfg, learned)
        dst_dir = Path(dec.target_path) / u.dst_name
        status, conflict_kind, unotes = READY, None, []
        genres, unmapped = (list(u.nfo.genres), []) if u.nfo else ([], [])
        if u.nfo:
            _, unmapped = map_genres(cfg, u.nfo.genres)

        existing = _existing_dir(dst_dir)
        if existing is not None:
            if _has_incomplete_marker(existing):
                status, conflict_kind = ST_INCOMPLETE, "incomplete"
                unotes.append("目标位置存在上次中断的半成品（.incomplete 标记），"
                              "需人工清理后重新扫描，绝不按跳过处理")
            else:
                other = _quick_provider(existing)
                if u.provider and other and u.provider == other:
                    status, conflict_kind = ST_PLACED, "same_id"
                    unotes.append("目标库已存在同一部影片（provider id 相同），不移动；"
                                  "源目录为冗余副本，请人工确认后清理")
                elif u.provider and cfg.on_conflict == "rename":
                    base, suffix = dst_dir.name, 2
                    while _existing_dir(dst_dir.parent / f"{base} ({suffix})") is not None:
                        suffix += 1
                    dst_dir = dst_dir.parent / f"{base} ({suffix})"
                    unotes.append(f"目标同名，按 rename 策略改为「{dst_dir.name}」")
                else:
                    status, conflict_kind = ST_CONFLICT, "name"
                    unotes.append("目标库已存在同名文件夹（非同一部影片），按 skip 策略跳过")

        plan_units.append({
            "id": u.id,
            "kind": u.kind,
            "label": u.title + (f" ({u.year})" if u.year else ""),
            "title": u.title,
            "year": u.year,
            "src": str(u.path),
            "dst_dir": str(dst_dir),
            "dst_name": u.dst_name,
            "target_lib": dec.target,
            "target_root": dec.target_path,
            "level": dec.level,
            "reason": dec.reason,
            "evidence": dec.evidence,
            "confidence": dec.confidence,
            "genres": genres,
            "unmapped": unmapped,
            "nfo_path": str(u.nfo_path) if u.nfo_path else None,
            "nfo_encoding": u.nfo.encoding if u.nfo else "",
            "provider": u.provider,
            "multi_cd": u.multi_cd,
            "disc": u.disc,
            "flags": list(u.flags),
            "status": status,
            "conflict_kind": conflict_kind,
            "notes": unotes,
            "default_selected": status == READY and (
                dec.level == "rule"
                or (dec.level == "learned" and dec.confidence == "medium")),
            "applied": False,
            "files": [[rel, size, mtime] for rel, size, mtime in u.files],
            "total_size": u.total_size,
            "file_count": u.file_count,
            "max_mtime_ns": u.max_mtime_ns,
        })

    # 同 provider id 多版本 → 默认排除出批量执行
    by_provider: dict[str, list[dict]] = {}
    for pu in plan_units:
        if pu["status"] == READY and pu["provider"]:
            by_provider.setdefault(pu["provider"], []).append(pu)
    for prov, group in by_provider.items():
        if len(group) > 1:
            for pu in group:
                pu["status"] = ST_MULTI
                pu["conflict_kind"] = "multi_version"
                pu["default_selected"] = False
                pu["notes"].append(
                    f"同一 provider id（{prov}）存在 {len(group)} 个版本/副本，"
                    "为避免重复条目默认不执行，请人工确认")

    status_counter = Counter(pu["status"] for pu in plan_units)
    ready_levels = Counter(pu["level"] for pu in plan_units if pu["status"] == READY)
    total = len(plan_units)
    fb = ready_levels.get("fallback", 0)
    unmapped_counter = Counter(g for pu in plan_units for g in pu["unmapped"])

    plan_id_src = cfg.config_hash() + created + "|".join(sorted(pu["id"] for pu in plan_units))
    plan = {
        "plan_id": hashlib.sha1(plan_id_src.encode("utf-8")).hexdigest()[:10],
        "created_at": created,
        "config_hash": cfg.config_hash(),
        "strategy": cfg.strategy,
        "units": plan_units,
        "stats": {
            "total": total,
            "ready": status_counter.get(READY, 0),
            "by_status": dict(status_counter),
            "ready_levels": dict(ready_levels),
            "fallback_ratio": (fb / total) if total else 0.0,
            "no_nfo": sum(1 for pu in plan_units if not pu["nfo_path"]),
            "unmapped_genres": dict(unmapped_counter),
            "total_size": sum(pu["total_size"] for pu in plan_units),
        },
        "notes": notes,
    }
    return plan


def plan_digest(plan: dict) -> str:
    raw = json.dumps(plan, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def save_plan(runtime_dir: Path, plan: dict) -> Path:
    runtime_dir = Path(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    target = runtime_dir / "plan.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, target)
    return target


def load_plan(runtime_dir: Path) -> dict | None:
    target = Path(runtime_dir) / "plan.json"
    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def check_plan_freshness(cfg: Config, plan: dict,
                         only_ids: set[str] | None = None) -> list[str]:
    """apply 前置校验：配置哈希 + 逐单元快照（文件数/总字节/最新 mtime）。"""
    problems: list[str] = []
    if plan.get("config_hash") != cfg.config_hash():
        return ["配置已变更，请重新扫描后再执行"]
    for pu in plan["units"]:
        if only_ids is not None and pu["id"] not in only_ids:
            continue
        if pu["status"] != READY:
            continue
        src = Path(pu["src"])
        if not src.exists():
            problems.append(f"源已不存在：{pu['id']}")
            continue
        try:
            if pu["kind"] == "dir":
                files = snapshot_dir(src)
            else:
                unit2, _ = _analyze_loose(src, pu["id"])
                files = unit2.files if unit2 else []
        except OSError as exc:
            problems.append(f"源读取失败：{pu['id']}（{exc}）")
            continue
        total = sum(s for _, s, _ in files)
        count = len(files)
        mx = max((m for _, _, m in files), default=0)
        if (count, total, mx) != (pu["file_count"], pu["total_size"], pu["max_mtime_ns"]):
            problems.append(f"源内容自扫描后已变化：{pu['id']}")
    return problems


def _refresh_stats(plan: dict) -> None:
    """状态标记变更后同步刷新统计块，保证 GUI 过滤器与卡片不显示过期数据。"""
    sc = Counter(pu["status"] for pu in plan["units"])
    ready_levels = Counter(pu["level"] for pu in plan["units"]
                           if pu["status"] == READY)
    st = plan["stats"]
    st["by_status"] = dict(sc)
    st["ready"] = sc.get(READY, 0)
    st["ready_levels"] = dict(ready_levels)
    total = st.get("total") or len(plan["units"])
    st["fallback_ratio"] = (ready_levels.get("fallback", 0) / total) if total else 0.0


def mark_applied(runtime_dir: Path, ids: list[str]) -> None:
    plan = load_plan(runtime_dir)
    if not plan:
        return
    idset = set(ids)
    for pu in plan["units"]:
        if pu["id"] in idset:
            pu["applied"] = True
            pu["status"] = ST_APPLIED
            pu["default_selected"] = False
    _refresh_stats(plan)
    save_plan(runtime_dir, plan)


def mark_undone(runtime_dir: Path, ids: list[str]) -> None:
    plan = load_plan(runtime_dir)
    if not plan:
        return
    idset = set(ids)
    for pu in plan["units"]:
        if pu["id"] in idset:
            pu["applied"] = False
            pu["status"] = READY
    _refresh_stats(plan)
    save_plan(runtime_dir, plan)

"""执行前体检（决策 D-20261031-03，评议条件 C4/C5/C6）。

检查项：配置路径、Jellyfin 进程/服务运行（阻断门）、磁盘空间（留 10% 余量）、
staging 半成品残留、超长路径、兜底占比阈值。阻断项需在 GUI 显式确认才能越过
（磁盘空间不足与配置路径缺失不可越过）。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import Config
from .fsops import find_staging_leftovers, split_drive, staging_for_root
from .planner import READY, ST_BATCH, ST_MULTI

LONG_PATH_WARN = 240


def detect_jellyfin_processes() -> list[str]:
    """检测正在运行的 Jellyfin 进程/服务（用于 apply 前置阻断门）。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", timeout=15,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    names = set()
    for line in out.splitlines():
        if "jellyfin" in line.lower():
            first = line.split('","')[0].strip().strip('"')
            if first:
                names.add(first)
    return sorted(names)


def staging_roots_for(cfg: Config) -> list[Path]:
    """所有可能用到的 staging 根（apply 用库旁、undo 用源旁 + 显式配置）。"""
    roots = set()
    if cfg.staging_dir:
        roots.add(cfg.staging_dir)
    for p in cfg.library_paths():
        roots.add(staging_for_root(p))
    roots.add(staging_for_root(cfg.source_root))
    return sorted(roots)


def run_preflight(cfg: Config, plan: dict | None = None,
                  selected_ids: set[str] | None = None,
                  extra_staging_roots: list[Path] | None = None) -> list[dict]:
    items: list[dict] = []

    # 1) 配置路径仍存在（C4）
    missing = []
    if not cfg.source_root.is_dir():
        missing.append(f"source_root：{cfg.source_root}")
    for name, lib in cfg.libraries.items():
        if not lib.path.is_dir():
            missing.append(f"媒体库[{name}]：{lib.path}")
    if not cfg.fallback_path.is_dir():
        missing.append(f"fallback_path：{cfg.fallback_path}")
    if missing:
        items.append({"level": "block", "code": "paths_missing",
                      "message": "配置中的目录不存在（不可越过，请修正配置）",
                      "detail": missing})

    # 2) Jellyfin 运行检测（C5 前置阻断门）
    procs = detect_jellyfin_processes()
    if procs:
        items.append({
            "level": "block", "code": "jellyfin_running",
            "message": "检测到 Jellyfin 正在运行，批量移动期间实时监控可能产生残缺条目"
                       "（建议先停止 Jellyfin 服务或关闭相关库的实时监控；确认已停止/关闭可勾选越过）",
            "detail": procs,
        })
    else:
        items.append({"level": "info", "code": "jellyfin_ok",
                      "message": "未检测到运行中的 Jellyfin 进程", "detail": []})

    # 3) 磁盘空间预检（C6，跨盘复制场景）
    if plan:
        units = [u for u in plan["units"] if u["status"] in (READY, ST_BATCH, ST_MULTI) and
                 (selected_ids is None or u["id"] in selected_ids)]
        needed_by_drive: dict[str, int] = {}
        sample_by_drive: dict[str, Path] = {}
        for u in units:
            drive = split_drive(u["dst_dir"])
            needed_by_drive[drive] = needed_by_drive.get(drive, 0) + u["total_size"]
            sample_by_drive.setdefault(drive, Path(u["dst_dir"]))
        for drive, needed in sorted(needed_by_drive.items()):
            try:
                free = shutil.disk_usage(str(sample_by_drive[drive])).free
            except OSError:
                continue
            margin = max(free // 10, 1 << 30)
            if needed > free - margin:
                items.append({
                    "level": "block", "code": "disk_space",
                    "message": f"目标盘 {drive} 剩余空间不足（不可越过）",
                    "detail": [(f"待迁移约 {needed / (1 << 30):.2f} GiB，"
                                f"剩余 {free / (1 << 30):.2f} GiB（需留 10% 余量）")],
                })

    # 4) staging 半成品残留
    roots = set(staging_roots_for(cfg))
    for p in extra_staging_roots or ():
        roots.add(Path(p))
    leftovers = find_staging_leftovers(sorted(roots, key=str))
    if leftovers:
        items.append({
            "level": "block", "code": "staging_leftover",
            "message": "发现上次迁移中断留下的半成品目录（不可按跳过放过；"
                       "请先在「执行 / 回滚」页点击「清理残留」或人工核对后清理）",
            "detail": [str(p) for p in leftovers[:10]],
        })

    # 5) 超长路径（与磁盘空间检查同口径：只看本次选中单元）
    if plan:
        longs = []
        for u in plan["units"]:
            if u["status"] not in (READY, ST_BATCH, ST_MULTI):
                continue
            if selected_ids is not None and u["id"] not in selected_ids:
                continue
            if len(u["dst_dir"]) > LONG_PATH_WARN:
                longs.append(f"{u['id']} → {len(u['dst_dir'])} 字符")
        if longs:
            items.append({"level": "warn", "code": "long_paths",
                          "message": "以下目标路径超过 240 字符，Windows 可能移动失败",
                          "detail": longs[:10]})

    # 6) 兜底占比阈值（规则质量的直观指标）
    if plan:
        ratio = plan["stats"].get("fallback_ratio", 0.0)
        if ratio >= cfg.block_fallback_ratio:
            items.append({"level": "block", "code": "fallback_ratio",
                          "message": f"兜底占比 {ratio:.0%} 超过阻断阈值 "
                                     f"{cfg.block_fallback_ratio:.0%}，规则可能配置有误"
                                     "（确认规则无误可勾选越过）",
                          "detail": []})
        elif ratio >= cfg.warn_fallback_ratio:
            items.append({"level": "warn", "code": "fallback_ratio",
                          "message": f"兜底占比 {ratio:.0%} 超过提醒阈值 "
                                     f"{cfg.warn_fallback_ratio:.0%}，建议检查映射表",
                          "detail": []})
    return items


def cleanup_staging(cfg: Config) -> list[str]:
    """清理所有 staging 残留（仅带 .incomplete 标记的目录）。"""
    from .fsops import cleanup_leftovers
    return cleanup_leftovers(find_staging_leftovers(staging_roots_for(cfg)))

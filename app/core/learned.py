"""自学习历史票存储（legacy，决策 D-20261125-05 Task-07 A-1）。

- 数据在 runtime/learned.json（跟配置位置走，不进用户手写的 config.toml）；
- A-1 起全面停记：人工改判与确认结果一律不再写票（人工信号在会话留痕），
  文件冻结为只读 legacy 建议展示 + 逐条「忘记」；
- 旧票由 prune_legacy 一次性幂等迁移：被库名/别名覆盖的死键与空壳删除，
  其余保留为 legacy 低置信建议、默认不勾选，票数永不自动生效或参与择优。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .nfo import normalize_key


def _path(runtime_dir: Path) -> Path:
    return Path(runtime_dir) / "learned.json"


def load(runtime_dir: Path) -> dict:
    p = _path(runtime_dir)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) and isinstance(data.get("entries"), dict) else {}


def save(runtime_dir: Path, data: dict) -> None:
    runtime_dir = Path(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    tmp = _path(runtime_dir).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _path(runtime_dir))


def prune_legacy(runtime_dir: Path, covered: set[str]) -> int:
    """A-1 旧票迁移：删除被别名表/库名覆盖的死键及空壳项，返回删除数。

    covered 为 normalize_key 形态的已覆盖键；幂等——二次运行返回 0。
    无删除时不写盘，避免给没有历史票的安装凭空生成 learned.json。
    """
    data = load(runtime_dir)
    entries = data.get("entries") or {}
    removed = 0
    for key in list(entries):
        e = entries[key] or {}
        if normalize_key(key) in covered or not (e.get("libs") or {}):
            entries.pop(key, None)
            removed += 1
    if removed:
        save(runtime_dir, data)
    return removed


def forget(runtime_dir: Path, key: str, lib: str) -> None:
    data = load(runtime_dir)
    e = data.get("entries", {}).get(key)
    if e:
        e["libs"].pop(lib, None)
        if not e["libs"]:
            data["entries"].pop(key, None)
        save(runtime_dir, data)


def items(learned: dict) -> list[dict]:
    """展平为 GUI 列表行（按票数降序）。"""
    out = []
    for key, e in (learned.get("entries") or {}).items():
        for lib, info in e.get("libs", {}).items():
            out.append({"key": key, "genre": e.get("display", key), "lib": lib,
                        "votes": info.get("votes", 0),
                        "manual": info.get("manual", 0),
                        "last": info.get("last", "")})
    out.sort(key=lambda r: (-r["votes"], r["genre"], r["lib"]))
    return out


def best_for(learned: dict, genre: str) -> tuple[str, int, int] | None:
    """该题材票数最高的 (库, 票数, 人工次数)，无记录返回 None。"""
    entries = (learned or {}).get("entries") or {}
    e = entries.get(normalize_key(genre))
    if not e or not e.get("libs"):
        return None
    lib, info = max(e["libs"].items(),
                    key=lambda kv: (kv[1].get("votes", 0), kv[1].get("manual", 0)))
    return lib, info.get("votes", 0), info.get("manual", 0)


def votes_for(learned: dict, genres, lib: str) -> int:
    """多题材共同为 lib 投出的总票数（smart 平手裁决用）。"""
    entries = (learned or {}).get("entries") or {}
    total = 0
    for g in genres or []:
        e = entries.get(normalize_key(g))
        if e and lib in e.get("libs", {}):
            total += e["libs"][lib].get("votes", 0)
    return total

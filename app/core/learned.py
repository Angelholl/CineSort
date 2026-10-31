"""自学习存储：把执行结果沉淀为 题材→库 映射（决策 D-20261101-03）。

- 数据在 runtime/learned.json（跟配置位置走，不进用户手写的 config.toml）；
- 人工改判一票记 2 分（强信号），确认规则/预判结果一票记 1 分；
- 兜底库不入学习（防止短路摘要预判与规则）；
- 票数 ≥ learning.min_votes 后作为「自学习」级自动生效，未达到作为低置信建议。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .nfo import normalize_key

_FALLBACK_NAME = "兜底库"


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


def record(runtime_dir: Path, genres, target_lib: str, manual: bool) -> None:
    """一次执行完成即沉淀：题材列表 → 目标库。"""
    if not genres or not target_lib or target_lib == _FALLBACK_NAME:
        return
    data = load(runtime_dir)
    entries = data.setdefault("entries", {})
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    for g in genres:
        key = normalize_key(g)
        if not key:
            continue
        e = entries.setdefault(key, {"display": str(g).strip(), "libs": {}})
        info = e["libs"].setdefault(target_lib, {"votes": 0, "manual": 0, "last": ""})
        info["votes"] += 2 if manual else 1
        if manual:
            info["manual"] += 1
        info["last"] = now
    save(runtime_dir, data)


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

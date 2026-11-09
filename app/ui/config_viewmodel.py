"""配置页逻辑层（零 Qt 导入）：describe↔表单 互转 + 自学习行渲染。

纪律（D-20261102-02 协议第 1 条）：形状归一在本层，事务性校验
（枚举/路径存在性等）归 save_config 的 ConfigError，本层不做。
"""
from __future__ import annotations

import re

_SPLIT = re.compile(r"[、,，]")


def _split_items(text: str) -> list[str]:
    """按顿号/中英逗号拆分，去空白去空串，保序。"""
    return [x for x in (t.strip() for t in _SPLIT.split(text or "")) if x]


def _fmt_weight(w: float) -> str:
    """权重格式化：float 去掉 trailing 0（1.5→'1.5'，2.0→'2'）。"""
    return f"{float(w):g}"


def _parse_alias_lines(text: str) -> dict[str, str]:
    """解析「每行 k=v」别名框：空行/无等号/空键或空值均忽略。"""
    aliases: dict[str, str] = {}
    for line in str(text or "").splitlines():
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key and val:
            aliases[key] = val
    return aliases


def describe_to_form(desc: dict) -> dict:
    """把 describe dict 拍平为表单初值。"""
    plot = desc.get("plot") or {}
    learning = desc.get("learning") or {}
    lib_rows: list[list[str]] = []
    for lib in desc.get("libraries") or []:
        kww = "、".join(
            f"{k}={_fmt_weight(v)}"
            for k, v in (lib.get("keywords_weighted") or {}).items())
        lib_rows.append([
            str(lib.get("name") or ""),
            str(lib.get("path") or ""),
            "、".join(lib.get("keywords") or []),
            kww,
        ])
    return {
        "source_root": str(desc.get("source_root") or ""),
        "fallback_path": str(desc.get("fallback_path") or ""),
        "staging_dir": str(desc.get("staging_dir") or ""),
        "strategy": str(desc.get("strategy") or "smart"),
        "on_conflict": str(desc.get("on_conflict") or "skip"),
        "warn": float(desc.get("warn_fallback_ratio") or 0.0),
        "block": float(desc.get("block_fallback_ratio") or 0.0),
        "plot_enabled": bool(plot.get("enabled")),
        "plot_min_score": float(plot.get("min_score") or 0.0),
        "plot_normalize": bool(plot.get("normalize")),
        "learning_enabled": bool(learning.get("enabled")),
        "learning_min_votes": int(learning.get("min_votes") or 2),
        "priority_text": "、".join(desc.get("genre_priority") or []),
        "alias_text": "\n".join(
            f"{k}={v}" for k, v in (desc.get("genre_aliases") or {}).items()),
        "weak_alias_text": "\n".join(
            f"{k}={v}" for k, v in (desc.get("weak_genre_aliases") or {}).items()),
        "library_rows": lib_rows,
    }


def form_to_body(form: dict, library_rows: list[list[str]]) -> dict:
    """表单值逆转换为 save_config 的 body（只保证形状，不做事务校验）。"""
    aliases = _parse_alias_lines(form.get("alias_text"))
    weak_aliases = _parse_alias_lines(form.get("weak_alias_text"))

    libraries: list[dict] = []
    for row in library_rows or []:
        row = list(row) + [""] * (4 - len(row))
        name = str(row[0]).strip()
        if not name:
            continue
        weighted: dict[str, float] = {}
        for chunk in _split_items(str(row[3])):
            word, _, w = chunk.partition("=")
            word = word.strip()
            if not word:
                continue
            try:
                weighted[word] = float(w)
            except ValueError:
                continue
        libraries.append({
            "name": name,
            "path": str(row[1]).strip(),
            "keywords": _split_items(str(row[2])),
            "keywords_weighted": weighted,
        })

    return {
        "source_root": str(form.get("source_root") or "").strip(),
        "fallback_path": str(form.get("fallback_path") or "").strip(),
        "staging_dir": str(form.get("staging_dir") or "").strip(),
        "strategy": str(form.get("strategy") or "smart"),
        "on_conflict": str(form.get("on_conflict") or "skip"),
        "warn_fallback_ratio": float(form.get("warn") or 0.0),
        "block_fallback_ratio": float(form.get("block") or 0.0),
        "plot": {
            "enabled": bool(form.get("plot_enabled")),
            "min_score": float(form.get("plot_min_score") or 0.0),
            "normalize": bool(form.get("plot_normalize")),
        },
        "learning": {
            "enabled": bool(form.get("learning_enabled")),
            "min_votes": int(form.get("learning_min_votes") or 2),
        },
        "genre_priority": _split_items(str(form.get("priority_text") or "")),
        "genre_aliases": aliases,
        "weak_genre_aliases": weak_aliases,
        "libraries": libraries,
    }


def learned_rows(items: list[dict]) -> list[tuple]:
    """learned item → 表行，末两列 (key, lib) 供忘记按钮捕获。"""
    rows: list[tuple] = []
    for it in items or []:
        rows.append((
            str(it.get("genre") or ""), str(it.get("lib") or ""),
            it.get("votes", 0), it.get("manual", 0), str(it.get("last") or ""),
            it.get("key"), it.get("lib"),
        ))
    return rows

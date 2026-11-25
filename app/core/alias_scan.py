"""别名扫描分析（owner 2026-11-25）：扫描源目录影片，汇总 NFO 未映射题材频次
与影片名词频榜，供配置页人工逐条指定目标库后写回别名表/弱别名表。

纯本地规则，不做任何外部查询/LLM（D-20261109-01）；产出为候选建议，
不自动写配置（沿用「弱信号=人工确认」范式）。
"""
from __future__ import annotations

import re

from . import scanner
from .classifier import map_genres_ex
from .config import Config
from .nfo import normalize_key

# 影片名分词分隔符：空白与常见命名标点（含全角）
_SEP_RE = re.compile(r"[\s._\-\[\]()（）【】·,，]+")

# 质量480p/编码/容器等无分类价值的噪声词（小写）
_JUNK_TOKENS = {
    "4k", "8k", "hdr", "uhd", "sdr", "dv",
    "1080p", "720p", "2160p", "480p", "540p",
    "h264", "h265", "x264", "x265", "hevc", "avc",
    "mp4", "mkv", "avi", "wmv", "mov", "ts", "m2ts", "iso",
    "web", "webdl", "webrip", "bluray", "bdrip", "dvdrip", "hdtv", "remux",
    "cd1", "cd2", "cd3", "part1", "part2", "disc1", "disc2",
}


def name_tokens(name: str) -> list[str]:
    """影片名 → 候选词：按分隔符切词，保留长度 ≥2 的非常见噪声词。

    纯数字、质量/编码噪声词剔除；其余保留原样（大小写归并由调用方分组）。"""
    out = []
    for tok in _SEP_RE.split(name):
        t = tok.strip()
        if len(t) < 2 or t.lower() in _JUNK_TOKENS or t.isdigit():
            continue
        out.append(t)
    return out


def scan_alias_candidates(cfg: Config) -> dict:
    """扫描源目录，返回别名候选榜与审计摘要（D-20261109-01 审计方案工具化）：

    {"unit_count": int, "unit_with_nfo": int,
     "unit_strong_hit": int,         # 至少一个强命中库的单元数
     "unit_weak_only": int,          # 仅弱命中的单元数
     "genres": [(题材原样, 次数), ...]  # 未映射题材，按 normalize_key 归组计频
     "tokens": [(词, 次数), ...]}       # 影片名词频，casefold 归组、原样展示
    两个榜均按次数降序、同次数按名称升序。
    """
    units, _ = scanner.scan_source_root(cfg)
    genre_groups: dict[str, tuple[str, int]] = {}   # normalize_key -> (展示原样, 次数)
    token_groups: dict[str, tuple[str, int]] = {}   # casefold   -> (展示原样, 次数)
    strong_hit = weak_only = with_nfo = 0
    for u in units:
        genres = u.nfo.genres if u.nfo else []
        if genres:
            with_nfo += 1
            strong, weak, unmapped = map_genres_ex(cfg, genres)
            if strong:
                strong_hit += 1
            elif weak:
                weak_only += 1
            for g in unmapped:
                key = normalize_key(g)
                if not key:
                    continue
                if key in genre_groups:
                    old, n = genre_groups[key]
                    genre_groups[key] = (old, n + 1)
                else:
                    genre_groups[key] = (g, 1)
        for tok in name_tokens(u.dst_name):
            key = tok.casefold()
            if key in token_groups:
                old, n = token_groups[key]
                token_groups[key] = (old, n + 1)
            else:
                token_groups[key] = (tok, 1)

    def _sorted(groups: dict) -> list[tuple[str, int]]:
        return sorted(groups.values(), key=lambda kv: (-kv[1], kv[0]))

    return {
        "unit_count": len(units),
        "unit_with_nfo": with_nfo,
        "unit_strong_hit": strong_hit,
        "unit_weak_only": weak_only,
        "genres": _sorted(genre_groups),
        "tokens": _sorted(token_groups),
    }


def filter_covered(candidates: dict, covered_keys: set[str]) -> dict:
    """题材榜中已覆盖的候选不再列出（owner 2026-11-25：加入别名表后应扫不出）。

    covered_keys 为已生效别名键（normalize_key 形态，含已落盘配置与编辑框
    待保存行）；按 normalize_key 归一比对，其余字段原样保留。"""
    if not covered_keys:
        return candidates
    out = dict(candidates)
    out["genres"] = [(g, n) for g, n in candidates.get("genres") or []
                     if normalize_key(g) not in covered_keys]
    return out

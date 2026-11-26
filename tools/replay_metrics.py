"""离线重放四指标量尺（D-20261125-05 Task-01，只读）。

对给定 config 跑一遍扫描→分类→建计划，输出计划 §4 的五键结果：
自动生效单元数 / 多候选胜出依据分布 / 默认勾选数 / 票数闭合不一致对数 /
最大目标库占比。全程不写 plan.json / learned.json：build_plan 不 save，
本工具无任何 save 调用。

私有导入说明：``_rank`` 是 classifier 的模块私有函数，量尺必须与决策引擎
共用同一优先级排序键才能复算「胜出依据」，故此处显式只读导入。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# _rank 私有导入：与 classifier.rule_pick 完全同口径地复算无票/带票胜者。
from app.core.classifier import _rank, map_genres_ex
from app.core.config import Config, ConfigError, load_config
from app.core.journal import list_sessions, read_entries
from app.core.learned import load as load_learned
from app.core.learned import votes_for
from app.core.nfo import normalize_key
from app.core.planner import build_plan
from app.core.scanner import scan_source_root

BASIS_ORDER = ("priority", "plot", "decl_order", "votes", "unexpected")


def build_replay_plan(cfg: Config, strategy: str | None = None) -> dict:
    """扫描 + 建计划（只读）；strategy 仅覆盖内存配置，不改配置文件。"""
    effective = replace(cfg, strategy=strategy) if strategy else cfg
    units, notes = scan_source_root(effective)
    return build_plan(effective, units, notes)


def _winner_basis(cfg: Config, unit: dict, learned: dict) -> str | None:
    """多候选单元的胜出依据；单候选返回 None（不进分布）。"""
    genres = unit.get("genres") or []
    strong, weak, _unmapped = map_genres_ex(cfg, genres)
    cand = list(dict.fromkeys(strong + weak))
    if len(cand) <= 1:
        return None
    if unit.get("level") == "plot":
        return "plot"

    votes = {n: votes_for(learned, genres, n) for n in cand}
    decl = {n: i for i, n in enumerate(cfg.libraries)}
    no_vote = min(cand, key=lambda n: (*_rank(cfg, n), decl[n]))
    with_vote = min(cand, key=lambda n: (*_rank(cfg, n), -votes[n], decl[n]))
    actual = unit.get("target_lib")
    if actual != no_vote and actual == with_vote:
        return "votes"
    if actual == no_vote:
        winner_rank = _rank(cfg, no_vote)
        if sum(1 for n in cand if _rank(cfg, n) == winner_rank) > 1:
            return "decl_order"
        return "priority"
    return "unexpected"


def _closure(cfg: Config, plan: dict) -> dict:
    """票数闭合：只认留痕上线后的 done 记录；历史票目单列不判错。"""
    sessions = list_sessions(cfg.runtime_dir / "journals")
    rolled_back: set[str] = set()
    for s in sessions:
        if s.get("kind") != "undo" or not s.get("undoes"):
            continue
        for entry in read_entries(Path(s["path"])):
            if entry.get("type") == "done" and entry.get("unit_id") is not None:
                rolled_back.add(str(entry["unit_id"]))

    units = plan.get("units") or []
    by_id = {str(u["id"]): u for u in units if u.get("id")}
    by_src = {str(u["src"]): u for u in units if u.get("src")}

    # 按 header ts 升序复放 apply 会话：A-1 起确认与改判都不再记票，
    # 触及对恒为 0 票；tuple 入键即使加 0 也建立「触及对」。
    expected: Counter[tuple[str, str]] = Counter()
    applies = sorted((s for s in sessions if s.get("kind") == "apply"),
                     key=lambda s: s.get("ts") or "")
    for s in applies:
        for entry in read_entries(Path(s["path"])):
            if entry.get("type") != "done":
                continue
            if "title" not in entry or "manual" not in entry:
                continue  # 留痕上线前的 done 记录不参与闭合
            uid = entry.get("unit_id")
            pu = by_id.get(str(uid)) if uid is not None else None
            if pu is None:
                pu = by_src.get(str(entry.get("src_dir")))
            if pu is None or (uid is not None and str(uid) in rolled_back):
                continue
            target = str(entry.get("target_lib") or pu.get("target_lib") or "")
            if not target:
                continue
            for g in pu.get("genres") or []:
                expected[(normalize_key(g), target)] += 0

    learned = load_learned(cfg.runtime_dir)
    actual: dict[tuple[str, str], int] = {}
    for key, info in (learned.get("entries") or {}).items():
        for lib, detail in (info.get("libs") or {}).items():
            votes = int(detail.get("votes") or 0)
            if votes:
                actual[(str(key), str(lib))] = votes

    inconsistent = sorted(p for p, want in expected.items()
                          if actual.get(p, 0) != want)
    legacy = sorted(set(actual) - set(expected))
    return {
        "inconsistencies": len(inconsistent),
        "inconsistent_pairs": inconsistent,
        "touched_pairs": sorted(expected),
        "legacy_pairs": legacy,
        "expected": {f"{g}|{lib}": n for (g, lib), n in sorted(expected.items())},
    }


def replay_metrics(cfg: Config, plan: dict | None = None) -> dict:
    """§4 五键量尺；传入已建好的 plan 可避免重复扫描。"""
    if plan is None:
        plan = build_replay_plan(cfg)
    units = plan.get("units") or []
    learned = load_learned(cfg.runtime_dir)

    basis: Counter[str] = Counter()
    for pu in units:
        kind = _winner_basis(cfg, pu, learned)
        if kind:
            basis[kind] += 1

    targets = Counter(str(u.get("target_lib")) for u in units)
    total = len(units)
    return {
        "auto_effective_units": sum(
            1 for u in units
            if u.get("level") == "learned" and u.get("default_selected")),
        "winner_basis": {k: basis.get(k, 0) for k in BASIS_ORDER},
        "default_selected": sum(1 for u in units if u.get("default_selected")),
        "vote_closure_inconsistencies": _closure(cfg, plan)["inconsistencies"],
        "top_target_share": (max(targets.values()) / total) if total else 0.0,
    }


def _report(result: dict, strategy: str) -> str:
    basis = result["winner_basis"]
    return "\n".join([
        "离线重放四指标量尺（D-20261125-05）",
        f"策略：{strategy}",
        f"自动生效单元数（level=learned 且默认勾选）：{result['auto_effective_units']}",
        "多候选胜出依据分布：" + "、".join(f"{k}={v}" for k, v in basis.items()),
        f"默认勾选数：{result['default_selected']}",
        f"票数闭合不一致对数：{result['vote_closure_inconsistencies']}",
        f"最大目标库占比：{result['top_target_share']:.1%}",
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="离线重放四指标量尺（只读，不写 plan.json / learned.json）")
    parser.add_argument("config", help="config.toml 路径")
    parser.add_argument("--strategy", default=None,
                        help="覆盖 cfg.strategy 做 what-if 对比（不改配置文件）")
    parser.add_argument("--json", action="store_true", help="机器可读 JSON 输出")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2
    plan = build_replay_plan(cfg, args.strategy)
    result = replay_metrics(cfg, plan)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(_report(result, plan["strategy"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

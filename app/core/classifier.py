"""分类决策引擎：题材优先级表 → 摘要关键词评分 → 兜底库。

决策链（决策 D-20261031-02）：
- rule     ：NFO 题材经别名表映射到库，按 genre_priority 取最优命中；
- smart 策略：多个候选库时用摘要评分择优，评分不足以区分再回退优先级表；
- plot     ：题材未映射/缺失时用 <plot> 关键词评分预判（可解释证据）；
- fallback ：以上全部失败进兜底库。
每个决策都携带 evidence，保证「为什么进这个库」可复核（评议认可点）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .learned import best_for, votes_for
from .nfo import normalize_key

LEVEL_RULE = "rule"
LEVEL_PLOT = "plot"
LEVEL_LEARNED = "learned"
LEVEL_FALLBACK = "fallback"

LEVEL_LABELS = {LEVEL_RULE: "规则", LEVEL_PLOT: "摘要预判",
                LEVEL_LEARNED: "自学习", LEVEL_FALLBACK: "兜底"}


@dataclass
class Decision:
    target: str            # 目标库显示名
    target_path: str
    level: str
    reason: str
    evidence: list[str] = field(default_factory=list)
    confidence: str = "high"   # high | medium | low


def alias_map(cfg: Config) -> dict[str, str]:
    """库自身名的归一键 → 库名，再叠加用户别名表（用户别名优先）。"""
    amap = {normalize_key(name): name for name in cfg.libraries}
    for k, v in cfg.genre_aliases.items():
        if v in cfg.libraries:
            amap[normalize_key(k)] = v
    return amap


def weak_alias_map(cfg: Config) -> dict[str, str]:
    """弱别名归一键 → 库名（弱信号：唯一命中时降级，永不压过强命中）。"""
    return {normalize_key(k): v for k, v in cfg.weak_genre_aliases.items()
            if v in cfg.libraries}


def map_genres_ex(cfg: Config,
                  genres: list[str]) -> tuple[list[str], list[str], list[str]]:
    """返回 (强命中库, 弱命中库, 未映射题材)，各自保序去重；同名键强表胜出。"""
    smap = alias_map(cfg)
    wmap = weak_alias_map(cfg)
    strong: list[str] = []
    weak: list[str] = []
    unmapped: list[str] = []
    for g in genres:
        target = smap.get(normalize_key(g))
        if target:
            if target not in strong:
                strong.append(target)
        else:
            wtarget = wmap.get(normalize_key(g))
            if wtarget:
                if wtarget not in weak:
                    weak.append(wtarget)
            else:
                unmapped.append(g)
    return strong, weak, unmapped


def map_genres(cfg: Config, genres: list[str]) -> tuple[list[str], list[str]]:
    """返回 (映射到的库名列表-去重保序, 未映射题材列表)。"""
    s, _w, u = map_genres_ex(cfg, genres)
    return s, u


def score_plot(plot: str, cfg: Config) -> list[tuple[str, float, list[str]]]:
    """摘要关键词评分：score = Σ 权重×次数。返回 [(库名, 分, 命中明细)] 降序。"""
    text = (plot or "").lower()
    if not text:
        return []
    results = []
    for lib in cfg.libraries.values():
        score = 0.0
        hits: list[str] = []
        for kw in lib.keywords:
            n = text.count(kw.lower())
            if n:
                score += n
                hits.append(f"{kw}×{n}")
        for kw, w in lib.keywords_weighted.items():
            n = text.count(kw.lower())
            if n:
                score += w * n
                hits.append(f"{kw}×{n}(权重{w:g})")
        if score > 0:
            if cfg.plot.normalize:
                score = score / max(len(plot) ** 0.5, 1.0)
            results.append((lib.name, score, hits))
    results.sort(key=lambda x: (-x[1], x[0]))
    return results


def _rank(cfg: Config, lib_name: str) -> tuple[int, int]:
    """优先级排序键：表内位置优先；未列入的库同档（交由历史倾向/声明顺序裁决）。"""
    if lib_name in cfg.genre_priority:
        return (0, cfg.genre_priority.index(lib_name))
    return (1, 0)


def classify(unit, cfg: Config, learned: dict | None = None) -> Decision:
    learned = learned or {}
    nfo = getattr(unit, "nfo", None)
    plot = (nfo.plot if nfo else "") or ""
    genres = list(nfo.genres) if nfo else []
    mapped_s, mapped_w, unmapped = map_genres_ex(cfg, genres)
    mapped = mapped_s + [w for w in mapped_w if w not in mapped_s]
    min_votes = max(int(cfg.learning.min_votes), 1)

    # 未映射题材的自学习命中：达阈值自动生效，未达阈值作低置信建议
    auto_hits, soft_hits = [], []
    for g in unmapped:
        hit = best_for(learned, g)
        if not hit:
            continue
        lib, votes, manual = hit
        if votes >= min_votes:
            auto_hits.append((g, lib, votes, manual))
        elif votes > 0:
            soft_hits.append((g, lib, votes, manual))
    auto_hits.sort(key=lambda h: (-h[2], -h[3]))

    scoring = score_plot(plot, cfg) if cfg.plot.enabled else []
    best = scoring[0] if scoring else None

    def fallback(reason: str) -> Decision:
        ev = []
        if genres:
            ev.append("NFO 题材：" + "、".join(genres))
        if scoring:
            ev.append("摘要评分未达阈值 " + "；".join(
                f"{n}={s:.1f}" for n, s, _ in scoring[:3]))
        elif cfg.plot.enabled and not plot:
            ev.append("无摘要文本可分析")
        if soft_hits:
            g, lib, votes, manual = soft_hits[0]
            ev.append(f"自学习仅 {votes} 票未自动生效（『{g}』→『{lib}』），"
                      "可在计划页人工确认")
        return Decision("兜底库", str(cfg.fallback_path), LEVEL_FALLBACK, reason, ev, "low")

    def plot_pick(prefix: str) -> Decision:
        name, sc, hits = best
        conf = "medium" if sc >= cfg.plot.min_score * 2 else "low"
        return Decision(
            name, str(cfg.libraries[name].path), LEVEL_PLOT,
            f"{prefix}：摘要评分『{name}』{sc:g} 分",
            [f"摘要命中：{h}" for h in hits[:8]], conf)

    def learned_pick(hit) -> Decision:
        g, lib, votes, manual = hit
        ev = [f"自学习：『{g}』此前已 {votes} 次归入『{lib}』（人工指定 {manual} 次）"]
        if genres:
            ev.append("NFO 题材：" + "、".join(genres))
        return Decision(lib, str(cfg.libraries[lib].path), LEVEL_LEARNED,
                        f"自学习映射：『{g}』→『{lib}』", ev,
                        "medium" if votes >= min_votes else "low")

    def rule_pick(extra: str = "") -> Decision:
        weak_only = bool(mapped_w) and not mapped_s
        candidates = mapped_s or mapped_w
        votes_map = {n: votes_for(learned, genres, n) for n in mapped}
        # 优先级表为主；未列入优先级的库之间按历史倾向（自学习票数）裁决
        decl = {n: i for i, n in enumerate(cfg.libraries)}
        winner = min(candidates, key=lambda n: (*_rank(cfg, n), -votes_map[n], decl[n]))
        rank = _rank(cfg, winner)
        ev = []
        for g in genres:
            mm, _ = map_genres(cfg, [g])
            if mm:
                t = mm[0]
                ev.append(f"题材『{g}』→ {t}（优先级第 {rank[1] + 1} 位）"
                          if t == winner else f"题材『{g}』→ {t}")
        if weak_only:
            wmap = weak_alias_map(cfg)
            trig = "、".join(g for g in genres if wmap.get(normalize_key(g)) == winner)
            ev.append(f"弱标签『{trig}』→ {winner}（弱信号，默认不勾选）")
        if unmapped:
            ev.append("未映射题材：" + "、".join(unmapped))
        if any(votes_map.values()):
            ev.append("历史倾向：" + "；".join(
                f"{n} {v} 票" for n, v in votes_map.items() if v))
        if extra:
            ev.append(extra)
        if len(mapped) > 1 and cfg.strategy == "smart" and scoring:
            ev.append("候选库摘要评分：" + "；".join(
                f"{n}={s:.1f}" for n, s, _ in scoring if n in mapped))
        conf = "low" if weak_only else "high"
        return Decision(winner, str(cfg.libraries[winner].path), LEVEL_RULE,
                        f"题材规则命中『{winner}』" + (f"（{extra}）" if extra else "")
                        + ("（弱标签）" if weak_only else ""),
                        ev, conf)

    if not genres:
        if best and best[1] >= cfg.plot.min_score:
            return plot_pick("NFO 缺失或无题材，按摘要预判")
        if soft_hits:
            return learned_pick(soft_hits[0])
        return fallback("无 NFO 或无题材信息，落入兜底库")

    if mapped:
        if cfg.strategy == "smart" and len(mapped) > 1:
            cand = [(n, s, h) for n, s, h in scoring if n in mapped]
            if cand and cand[0][1] >= cfg.plot.min_score and \
                    (len(cand) == 1 or cand[0][1] - cand[1][1] >= 1.0):
                return plot_pick(f"多题材候选 {'/'.join(mapped)}，摘要评分择优")
            return rule_pick("多题材候选，摘要评分不足以区分，按优先级表与历史倾向")
        return rule_pick()

    # 有题材但全部未映射：自学习（达阈值）→ 摘要预判 → 低票建议 → 兜底
    if auto_hits:
        return learned_pick(auto_hits[0])
    if best and best[1] >= cfg.plot.min_score:
        return plot_pick(f"题材 {'、'.join(unmapped)} 未映射，按摘要预判")
    if soft_hits:
        return learned_pick(soft_hits[0])
    return fallback(f"题材 {'、'.join(unmapped)} 未映射且摘要评分不足")

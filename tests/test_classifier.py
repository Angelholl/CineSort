"""分类决策引擎测试：优先级表 → 摘要评分 → 兜底（决策 D-20261031-02）。"""
from pathlib import Path
from types import SimpleNamespace

from app.core.classifier import classify, map_genres, score_plot
from app.core.config import Config, Library, PlotOptions
from app.core.nfo import NfoInfo


def make_cfg(strategy="smart", plot_enabled=True, min_score=2.0) -> Config:
    libs = {
        "科幻": Library("科幻", Path("X:/lib/科幻"),
                        keywords=["太空", "宇宙", "外星人"],
                        keywords_weighted={"星际": 2.0}),
        "动作": Library("动作", Path("X:/lib/动作"),
                        keywords=["枪战", "特工"], keywords_weighted={}),
        "恐怖": Library("恐怖", Path("X:/lib/恐怖"),
                        keywords=["鬼屋", "诅咒"], keywords_weighted={}),
    }
    return Config(path=Path("X:/config.toml"), source_root=Path("X:/src"),
                  libraries=libs, genre_priority=["科幻", "动作", "恐怖"],
                  genre_aliases={"sci-fi": "科幻", "scifi": "科幻", "動作": "动作"},
                  fallback_path=Path("X:/fb"), strategy=strategy,
                  plot=PlotOptions(enabled=plot_enabled, min_score=min_score))


def unit(genres, plot=""):
    return SimpleNamespace(nfo=NfoInfo(genres=list(genres), plot=plot))


def test_priority_first_hit():
    d = classify(unit(["动作", "科幻"]), make_cfg())
    assert d.target == "科幻" and d.level == "rule" and d.confidence == "high"


def test_alias_and_priority():
    d = classify(unit(["Sci-Fi", "動作"]), make_cfg(strategy="priority"))
    assert d.target == "科幻"


def test_single_mapped_under_smart():
    d = classify(unit(["动作"]), make_cfg())
    assert d.target == "动作" and d.level == "rule"


def test_smart_plot_decides_among_candidates():
    d = classify(unit(["动作", "科幻"], "飞船穿越太空，外星人入侵地球，星际战争爆发"),
                 make_cfg())
    assert d.target == "科幻" and d.level == "plot"
    assert any("摘要命中" in e for e in d.evidence)


def test_smart_plot_insufficient_falls_back_to_priority():
    d = classify(unit(["动作", "科幻"], "一家人在海边度假的故事"), make_cfg())
    assert d.target == "科幻" and d.level == "rule"


def test_unmapped_plot_prediction():
    d = classify(unit(["西部"], "荒野枪战，赏金特工追捕逃犯"), make_cfg())
    assert d.target == "动作" and d.level == "plot"


def test_unmapped_no_hit_goes_fallback():
    d = classify(unit(["西部"], "乡村爱情故事"), make_cfg())
    assert d.target == "兜底库" and d.level == "fallback"


def test_no_nfo_fallback():
    d = classify(SimpleNamespace(nfo=None), make_cfg())
    assert d.level == "fallback" and d.target == "兜底库"


def test_no_genres_plot_hit():
    d = classify(unit([], "太空站发生宇宙灾难"), make_cfg())
    assert d.target == "科幻" and d.level == "plot"


def test_plot_disabled_fallback():
    d = classify(unit(["西部"], "荒野枪战特工"), make_cfg(plot_enabled=False))
    assert d.level == "fallback"


def test_min_score_threshold():
    d = classify(unit(["西部"], "一次枪战"), make_cfg(min_score=2.0))
    assert d.level == "fallback"


def test_weighted_keywords():
    d = classify(unit(["西部"], "一场星际远征"), make_cfg())
    assert d.target == "科幻" and d.level == "plot"


def test_score_plot_evidence():
    name, sc, ev = score_plot("太空宇宙太空", make_cfg())[0]
    assert name == "科幻" and sc == 3
    assert any("太空×2" in h for h in ev)


def test_map_genres_alias():
    mapped, unmapped = map_genres(make_cfg(), ["scifi", "科幻", "西部"])
    assert mapped == ["科幻"] and unmapped == ["西部"]

# 卡 C4（D-20261109-01）：弱标签裁决语义。弱命中永不与强命中同台竞争；
# 唯一命中且来自弱标签 → rule/low → 默认不勾选（不自动改判，降为人工复核）。


def weak_cfg(tmp_path, overrides=None):
    """build_env 默认环境 + overrides（genre_aliases / weak_genre_aliases / genre_priority）。"""
    from conftest import build_env

    from app.core.config import load_config

    return load_config(build_env(tmp_path, overrides=overrides))


def test_weak_only_single_hit_low_confidence(tmp_path):
    cfg = weak_cfg(tmp_path, {"weak_genre_aliases": {"护士": "动作"}})
    d = classify(unit(("护士",)), cfg)
    assert d.level == "rule"
    assert d.confidence == "low"
    assert d.target == "动作"
    assert any("弱标签" in e for e in d.evidence)
    assert "（弱标签）" in d.reason


def test_weak_cannot_beat_strong(tmp_path):
    cfg = weak_cfg(tmp_path, {"weak_genre_aliases": {"护士": "动作"},
                              "genre_priority": ["动作", "科幻"]})
    d = classify(unit(("护士", "Sci-Fi")), cfg)
    assert d.target == "科幻"
    assert d.confidence == "high"


def test_multiple_weak_candidates_use_priority(tmp_path):
    cfg = weak_cfg(tmp_path, {"weak_genre_aliases": {"护士": "动作", "空姐": "科幻"},
                              "genre_priority": ["科幻", "动作"]})
    d = classify(unit(("护士", "空姐")), cfg)
    assert d.target == "科幻"
    assert d.confidence == "low"


def test_strong_only_unchanged(tmp_path):
    cfg = weak_cfg(tmp_path)
    d = classify(unit(("Sci-Fi",)), cfg)
    assert d.confidence == "high"
    assert d.target == "科幻"
    assert not any("弱标签" in e for e in d.evidence)
    assert "（弱标签）" not in d.reason


def test_same_lib_strong_and_weak_not_demoted(tmp_path):
    cfg = weak_cfg(tmp_path, {"weak_genre_aliases": {"sf2": "科幻"}})
    d = classify(unit(("Sci-Fi", "sf2")), cfg)
    assert d.confidence == "high"
    assert d.target == "科幻"


def test_map_genres_ex_shapes(tmp_path):
    from app.core.classifier import map_genres_ex

    cfg = weak_cfg(tmp_path, {"weak_genre_aliases": {"护士": "动作"}})
    strong, weak, unmapped = map_genres_ex(
        cfg, ["Sci-Fi", "护士", "西部", "scifi"])
    assert strong == ["科幻"]
    assert weak == ["动作"]
    assert unmapped == ["西部"]
    s, u = map_genres(cfg, ["Sci-Fi", "护士", "西部", "scifi"])
    assert s == strong and u == unmapped

# ---------------------------------------------------------------- 卡 C7（Task-08）：score_title 标题弱评分

def title_unit(title, genres=(), plot=""):
    """带标题文本的单元：NFO title 与单元 title 各携一份（scanner 真实形态）。"""
    return SimpleNamespace(nfo=NfoInfo(genres=list(genres), plot=plot, title=title),
                           title=title)


def test_score_title_counts_alias_hits():
    from app.core.classifier import score_title

    cfg = make_cfg()
    cfg.weak_genre_aliases = {"マジックミラー号": "科幻"}
    res = score_title("マジックミラー号 陥没陷阱", cfg)
    assert res and res[0][0] == "科幻"
    assert res[0][1] >= 1.0
    assert any("マジックミラー号×1" in h for h in res[0][2])


def test_score_title_no_length_normalization():
    from app.core.classifier import score_title

    cfg = make_cfg()
    # 20 字短标题命中 1 次：不做 len**0.5 归一，分恰为 1.0
    res = score_title("一段二十字符的普通描述文字样本科幻", cfg)
    assert res[0][1] == 1.0


def test_score_title_skips_short_keys():
    from app.core.classifier import score_title

    cfg = make_cfg()
    cfg.libraries["P"] = Library("P", Path("X:/lib/P"))
    cfg.weak_genre_aliases = {"Q": "科幻"}
    res = score_title("P和Q都是单字符键", cfg)
    assert res == []


def test_score_title_no_double_count_on_overlap():
    from app.core.classifier import score_title

    cfg = make_cfg()
    cfg.libraries["美女"] = Library("美女", Path("X:/lib/美女"))
    cfg.weak_genre_aliases = {"美少女": "动作"}
    res = score_title("美少女物语", cfg)
    total = sum(s for _n, s, _h in res)
    assert total == 1.0
    assert not any(n == "美女" for n, _s, _h in res), \
        "美女库不得因『美少女』同一跨度得分（最长键优先、跨度被消费）"
    assert res[0][0] == "动作" and res[0][1] == 1.0


def test_title_pick_no_genres():
    cfg = make_cfg()
    cfg.weak_genre_aliases = {"マジックミラー号": "科幻"}
    d = classify(title_unit("マジックミラー号 陥没"), cfg)
    assert d.level == "title"
    assert d.confidence == "low"
    assert "标题" in d.reason
    assert any("标题命中" in e for e in d.evidence)


def test_title_pick_after_soft_learned():
    cfg = make_cfg()
    cfg.weak_genre_aliases = {"マジックミラー号": "科幻"}
    cfg.learning.min_votes = 2
    learned = {"entries": {"西部": {"display": "西部",
                                    "libs": {"动作": {"votes": 1, "manual": 0,
                                                      "last": ""}}}}}
    d = classify(title_unit("マジックミラー号 陥没", genres=("西部",)), cfg, learned)
    assert d.level == "learned"


def test_title_never_overrides_rule():
    cfg = make_cfg()
    cfg.weak_genre_aliases = {"マジックミラー号": "科幻"}
    d = classify(title_unit("动作大片 マジックミラー号 出撃", genres=("Sci-Fi",)), cfg)
    assert d.target == "科幻"
    assert d.level == "rule"
    assert not any("标题命中" in e for e in d.evidence)


def test_title_disabled_by_config():
    cfg = make_cfg()
    cfg.weak_genre_aliases = {"マジックミラー号": "科幻"}
    cfg.title.enabled = False
    d = classify(title_unit("マジックミラー号 陥没"), cfg)
    assert d.level == "fallback"


def test_title_evidence_label_distinct():
    cfg = make_cfg(min_score=2.0)
    cfg.weak_genre_aliases = {"マジックミラー号": "科幻"}
    plot_d = classify(unit([], "太空站发生宇宙灾难"), cfg)
    assert plot_d.level == "plot"
    assert any(e.startswith("摘要命中") for e in plot_d.evidence)
    assert not any(e.startswith("标题命中") for e in plot_d.evidence)
    title_d = classify(title_unit("マジックミラー号 陥没"), cfg)
    assert title_d.level == "title"
    assert any(e.startswith("标题命中") for e in title_d.evidence)
    assert not any(e.startswith("摘要命中") for e in title_d.evidence)


def test_learned_lib_removed_from_config_is_ignored(tmp_path):
    """审计回归：learned.json 指向已删除/改名的库时必须跳过该映射，
    不得 KeyError 崩掉扫描（build_plan → classify）。"""
    from conftest import build_env

    from app.core import learned as learned_store
    from app.core.config import load_config

    cfg = load_config(build_env(tmp_path))
    learned_store.record(cfg.runtime_dir, ["西部"], "动作", manual=True)
    learned_store.record(cfg.runtime_dir, ["西部"], "动作", manual=True)  # 达阈值（auto 路径）
    learned_store.record(cfg.runtime_dir, ["悬疑"], "动作", manual=False)  # 1 票未达阈值（soft 建议路径）
    cfg.libraries.pop("动作")                       # 用户随后删除该库
    d = classify(unit(("西部",)), cfg, learned_store.load(cfg.runtime_dir))
    assert d.level == "fallback" and d.target == "兜底库"
    d2 = classify(unit(("悬疑",)), cfg, learned_store.load(cfg.runtime_dir))
    assert d2.level == "fallback" and d2.target == "兜底库"
    assert not any("自学习" in e for e in d2.evidence)   # 失效库不得作低置信建议

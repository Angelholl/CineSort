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

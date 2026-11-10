"""自学习测试（决策 D-20261101-03）。"""
from pathlib import Path
from types import SimpleNamespace

from app.core import learned as ls
from app.core.classifier import classify
from app.core.config import Config, LearningOptions, Library, PlotOptions
from app.core.nfo import NfoInfo


def make_cfg(min_votes=2, priority=("武侠", "喜剧")) -> Config:
    libs = {
        "武侠": Library("武侠", Path("X:/lib/武侠"),
                        keywords=["江湖", "武功"], keywords_weighted={}),
        "喜剧": Library("喜剧", Path("X:/lib/喜剧"),
                        keywords=["搞笑"], keywords_weighted={}),
    }
    return Config(path=Path("X:/config.toml"), source_root=Path("X:/src"),
                  libraries=libs, genre_priority=list(priority),
                  genre_aliases={}, fallback_path=Path("X:/fb"),
                  strategy="smart", plot=PlotOptions(True, 2.0, False),
                  learning=LearningOptions(True, min_votes))


def unit(genres, plot=""):
    return SimpleNamespace(nfo=NfoInfo(genres=list(genres), plot=plot))


def test_record_votes_and_manual_weight(tmp_path):
    ls.record(tmp_path, ["古装"], "武侠", manual=False)
    ls.record(tmp_path, ["古装"], "武侠", manual=True)
    info = ls.load(tmp_path)["entries"]["古装"]["libs"]["武侠"]
    assert info["votes"] == 3 and info["manual"] == 1      # 1 + 2


def test_fallback_never_learned(tmp_path):
    ls.record(tmp_path, ["古装"], "兜底库", manual=True)
    assert ls.load(tmp_path).get("entries", {}) == {}


def test_best_for_and_votes_for(tmp_path):
    ls.record(tmp_path, ["古装"], "武侠", manual=True)
    ls.record(tmp_path, ["武侠"], "武侠", manual=False)
    assert ls.best_for(ls.load(tmp_path), "古装") == ("武侠", 2, 1)
    assert ls.votes_for(ls.load(tmp_path), ["古装", "武侠"], "武侠") == 3


def test_learned_auto_hit_threshold(tmp_path):
    cfg = make_cfg(min_votes=2)
    assert classify(unit(["古装"]), cfg).level == "fallback"   # 无学习记录
    ls.record(tmp_path, ["古装"], "武侠", manual=True)          # 2 票达标
    d = classify(unit(["古装"]), cfg, ls.load(tmp_path))
    assert d.level == "learned" and d.target == "武侠"
    assert d.confidence == "medium"
    assert any("自学习" in e for e in d.evidence)


def test_learned_soft_below_threshold_loses_to_plot(tmp_path):
    cfg = make_cfg(min_votes=2)
    ls.record(tmp_path, ["古装"], "喜剧", manual=False)         # 1 票 < 2
    learned = ls.load(tmp_path)
    d = classify(unit(["古装"], "江湖武功传奇"), cfg, learned)   # 摘要命中 → plot 优先
    assert d.level == "plot" and d.target == "武侠"
    d2 = classify(unit(["古装"], "乡村爱情"), cfg, learned)      # 摘要不中 → 低票建议
    assert d2.level == "learned" and d2.target == "喜剧" and d2.confidence == "low"


def test_smart_tie_break_by_votes_among_unprioritized(tmp_path):
    """两库都未列入优先级表时，历史倾向（票数）裁决归属。"""
    cfg = make_cfg(min_votes=99, priority=())
    learned = {"entries": {
        "武侠": {"display": "武侠",
                 "libs": {"喜剧": {"votes": 4, "manual": 2, "last": ""}}},
        "喜剧": {"display": "喜剧",
                 "libs": {"喜剧": {"votes": 1, "manual": 0, "last": ""}}},
    }}
    d = classify(unit(["武侠", "喜剧"]), cfg, learned)
    assert d.target == "喜剧" and d.level == "rule"
    assert any("历史倾向" in e for e in d.evidence)


def test_explicit_priority_beats_votes(tmp_path):
    cfg = make_cfg(min_votes=2, priority=("武侠",))
    learned = {"entries": {
        "武侠": {"display": "武侠",
                 "libs": {"喜剧": {"votes": 9, "manual": 5, "last": ""}}}}}
    d = classify(unit(["武侠", "喜剧"]), cfg, learned)
    assert d.target == "武侠"      # 显式优先级表永远赢过自学习


def test_forget(tmp_path):
    ls.record(tmp_path, ["古装"], "武侠", manual=True)
    ls.forget(tmp_path, "古装", "武侠")
    assert ls.load(tmp_path)["entries"] == {}


def test_config_learning_defaults(tmp_path):
    from conftest import build_env

    from app.core.config import load_config
    cfg = load_config(build_env(tmp_path))
    assert cfg.learning.enabled is True and cfg.learning.min_votes == 2

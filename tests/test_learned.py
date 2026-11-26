"""自学习测试（决策 D-20261101-03）。"""
from pathlib import Path
from types import SimpleNamespace

from conftest import seed_learned

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


def test_record_retired(tmp_path):
    """A-1：record 已退役；既购票目经确认+改判 apply 后逐字节不变。"""
    assert hasattr(ls, "record") is False
    from conftest import build_env, make_movie

    from app.core import jobs
    from app.core.config import load_config
    from app.state import AppState

    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    make_movie(cfg.source_root, "Opera (2021)", title="Opera", genres=("戏曲",),
               plot="剧情简介", tmdb="31")
    make_movie(cfg.source_root, "Gun Fight (2022)", title="Gun Fight", genres=("动作",),
               plot="特工枪战", tmdb="22")
    lp = seed_learned(cfg.runtime_dir, {"戏曲": {"科幻": {"votes": 1, "manual": 1}}})
    before = lp.read_bytes()

    state = AppState(cfg_path)
    jobs.run_scan(state, jobs.Job("scan"))
    jobs.run_apply(state, jobs.Job("apply"),
                   ["Opera (2021)", "Gun Fight (2022)"],
                   {"jellyfin_running", "fallback_ratio"},
                   {"Opera (2021)": "科幻"})
    assert lp.read_bytes() == before


def test_fallback_never_learned(tmp_path):
    """兜底库不入学习：A-1 后指向兜底库的 legacy 票也不参与建议。"""
    seed_learned(tmp_path, {"古装": {"兜底库": {"votes": 1, "manual": 1}}})
    cfg = make_cfg()
    d = classify(unit(["古装"]), cfg, ls.load(tmp_path))
    assert d.level == "fallback" and d.target == "兜底库"
    assert not any("自学习" in e for e in d.evidence)


def test_best_for_and_votes_for(tmp_path):
    seed_learned(tmp_path, {"古装": {"武侠": {"votes": 1, "manual": 1}},
                            "武侠": {"武侠": {"votes": 1, "manual": 0}}})
    assert ls.best_for(ls.load(tmp_path), "古装") == ("武侠", 1, 1)
    assert ls.votes_for(ls.load(tmp_path), ["古装", "武侠"], "武侠") == 2


def test_learned_never_auto_effective_at_any_votes(tmp_path):
    cfg = make_cfg(min_votes=2)
    assert classify(unit(["古装"]), cfg).level == "fallback"   # 无学习记录
    seed_learned(tmp_path, {"古装": {"武侠": {"votes": 2, "manual": 2}}})  # 2 票达标
    d = classify(unit(["古装"]), cfg, ls.load(tmp_path))
    assert d.level == "learned" and d.target == "武侠"
    assert d.confidence == "low"                              # 票数永不升置信
    assert any("自学习" in e for e in d.evidence)


def test_learned_soft_below_threshold_loses_to_plot(tmp_path):
    cfg = make_cfg(min_votes=2)
    seed_learned(tmp_path, {"古装": {"喜剧": {"votes": 1, "manual": 0}}})  # 1 票 < 2
    learned = ls.load(tmp_path)
    d = classify(unit(["古装"], "江湖武功传奇"), cfg, learned)   # 摘要命中 → plot 优先
    assert d.level == "plot" and d.target == "武侠"
    d2 = classify(unit(["古装"], "乡村爱情"), cfg, learned)      # 摘要不中 → 低票建议
    assert d2.level == "learned" and d2.target == "喜剧" and d2.confidence == "low"


def test_multi_candidate_ignores_votes_decl_order_decides(tmp_path):
    """票数退出择优：两库都未列入优先级表时，按声明顺序裁决。"""
    cfg = make_cfg(min_votes=99, priority=())
    learned = {"entries": {
        "武侠": {"display": "武侠",
                 "libs": {"喜剧": {"votes": 4, "manual": 2, "last": ""}}},
        "喜剧": {"display": "喜剧",
                 "libs": {"喜剧": {"votes": 1, "manual": 0, "last": ""}}},
    }}
    d = classify(unit(["武侠", "喜剧"]), cfg, learned)
    assert d.target == "武侠" and d.level == "rule"      # 声明顺序赢，票数不参与
    assert not any("历史倾向" in e for e in d.evidence)


def test_explicit_priority_beats_votes(tmp_path):
    cfg = make_cfg(min_votes=2, priority=("武侠",))
    learned = {"entries": {
        "武侠": {"display": "武侠",
                 "libs": {"喜剧": {"votes": 9, "manual": 5, "last": ""}}}}}
    d = classify(unit(["武侠", "喜剧"]), cfg, learned)
    assert d.target == "武侠"      # 显式优先级表永远赢过自学习


def test_forget(tmp_path):
    seed_learned(tmp_path, {"古装": {"武侠": {"votes": 1, "manual": 1}}})
    ls.forget(tmp_path, "古装", "武侠")
    assert ls.load(tmp_path)["entries"] == {}


def test_prune_drops_covered_keeps_rest(tmp_path):
    """A-1 旧票迁移：被库名/别名覆盖的键删除，其余保留；二次调用幂等。"""
    from app.core.classifier import covered_keys

    covered = covered_keys(make_cfg())
    seed_learned(tmp_path, {"武侠": {"武侠": {"votes": 3, "manual": 1}},
                            "西部": {"喜剧": {"votes": 2, "manual": 1}}})
    assert ls.prune_legacy(tmp_path, covered) == 1
    assert set(ls.load(tmp_path)["entries"]) == {"西部"}
    assert ls.prune_legacy(tmp_path, covered) == 0


def test_prune_empty_entry_removed(tmp_path):
    """A-1 旧票迁移：libs 全空的 legacy 壳一并清掉。"""
    seed_learned(tmp_path, {"空壳": {},
                            "保留": {"武侠": {"votes": 1, "manual": 0}}})
    assert ls.prune_legacy(tmp_path, set()) == 1
    assert set(ls.load(tmp_path)["entries"]) == {"保留"}


def test_config_learning_defaults(tmp_path):
    from conftest import build_env

    from app.core.config import load_config
    cfg = load_config(build_env(tmp_path))
    assert cfg.learning.enabled is True and cfg.learning.min_votes == 2

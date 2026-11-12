"""配置校验测试（评议条件 C4）。"""
from pathlib import Path

import pytest
import tomllib
from conftest import build_env

from app.core.config import (
    ConfigError,
    TitleOptions,
    check_session_root,
    describe,
    dump_config_text,
    ensure_first_run_config,
    is_sub_path,
    load_config,
    raw_describe,
    save_config_dict,
)


def test_valid_load_and_hash_stable(tmp_path):
    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    assert cfg.source_root == (tmp_path / "src").resolve()
    assert set(cfg.libraries) == {"科幻", "动作"}
    assert cfg.fallback_path == (tmp_path / "未分类").resolve()
    assert cfg.config_hash() == load_config(cfg_path).config_hash()


def test_missing_source_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_config(build_env(tmp_path, overrides={
            "source_root": str(tmp_path / "nope")}))


def test_missing_library_rejected(tmp_path):
    lib = [{"name": "科幻", "path": str(tmp_path / "nope"),
            "keywords": [], "keywords_weighted": {}}]
    with pytest.raises(ConfigError):
        load_config(build_env(tmp_path, overrides={"libraries": lib}))


def test_library_inside_source_rejected(tmp_path):
    bad = tmp_path / "src" / "科幻"
    bad.mkdir(parents=True)
    lib = [{"name": "科幻", "path": str(bad),
            "keywords": [], "keywords_weighted": {}}]
    with pytest.raises(ConfigError):
        load_config(build_env(tmp_path, overrides={"libraries": lib}))


def test_nested_libraries_rejected(tmp_path):
    outer = tmp_path / "libA"
    inner = outer / "sub"
    inner.mkdir(parents=True)
    libs = [{"name": "A", "path": str(outer), "keywords": [], "keywords_weighted": {}},
            {"name": "B", "path": str(inner), "keywords": [], "keywords_weighted": {}}]
    with pytest.raises(ConfigError):
        load_config(build_env(tmp_path, overrides={"libraries": libs}))


def test_unknown_priority_downgraded_to_warning(tmp_path):
    cfg = load_config(build_env(tmp_path, overrides={
        "genre_priority": ["不存在", "科幻"]}))
    assert cfg.genre_priority == ["科幻"]            # 悬空条目被丢弃、合法条目保留
    assert len(cfg.warnings) == 1
    assert "genre_priority" in cfg.warnings[0] and "不存在" in cfg.warnings[0]


def test_unknown_alias_downgraded_to_warning(tmp_path):
    cfg = load_config(build_env(tmp_path, overrides={
        "genre_aliases": {"Sci-Fi": "科幻", "x": "不存在"}}))
    assert cfg.genre_aliases == {"Sci-Fi": "科幻"}
    assert any("genre_aliases" in w and "不存在" in w for w in cfg.warnings)


def test_staging_inside_source_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_config(build_env(tmp_path, overrides={
            "staging_dir": str(tmp_path / "src" / "stage")}))


def test_invalid_strategy_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_config(build_env(tmp_path, overrides={"strategy": "bad"}))


def test_hash_changes_on_strategy(tmp_path):
    h1 = load_config(build_env(tmp_path)).config_hash()
    h2 = load_config(build_env(tmp_path / "second",
                               overrides={"strategy": "genre_only"})).config_hash()
    assert h1 != h2


def test_is_sub_path_windows_case():
    assert is_sub_path("G:\\A\\b", "G:\\a")
    assert is_sub_path("G:\\a", "G:\\a")
    assert not is_sub_path("G:\\ab", "G:\\a")
    assert not is_sub_path("G:\\a", "G:\\a\\b")


def test_session_root_accepts_sibling_dir(tmp_path):
    cfg = load_config(build_env(tmp_path))
    out = tmp_path / "out"
    out.mkdir()
    assert check_session_root(out, cfg) is None


def test_session_root_missing_dir_rejected(tmp_path):
    cfg = load_config(build_env(tmp_path))
    err = check_session_root(tmp_path / "ghost", cfg)
    assert err is not None and "不存在" in err


def test_session_root_same_as_source_rejected(tmp_path):
    cfg = load_config(build_env(tmp_path))
    err = check_session_root(str(cfg.source_root), cfg)
    assert err is not None and "不能是同一个目录" in err and "源目录" in err


def test_session_root_inside_source_rejected(tmp_path):
    cfg = load_config(build_env(tmp_path))
    sub = cfg.source_root / "sub"
    sub.mkdir()
    err = check_session_root(sub, cfg)
    assert err is not None and "不能位于源目录" in err


def test_session_root_containing_library_rejected(tmp_path):
    cfg = load_config(build_env(tmp_path))
    libs_parent = tmp_path / "libs"
    err = check_session_root(libs_parent, cfg)
    assert err is not None and "媒体库[科幻]" in err and "不能位于输出目录" in err


def test_session_root_inside_fallback_rejected(tmp_path):
    cfg = load_config(build_env(tmp_path))
    sub = cfg.fallback_path / "sub"
    sub.mkdir()
    err = check_session_root(sub, cfg)
    assert err is not None and "不能位于兜底库" in err


def test_weak_genre_aliases_loaded(tmp_path):
    cfg = load_config(build_env(
        tmp_path, overrides={"weak_genre_aliases": {"护士": "动作"}}))
    assert cfg.weak_genre_aliases == {"护士": "动作"}


def test_weak_alias_unknown_downgraded_to_warning(tmp_path):
    cfg = load_config(build_env(
        tmp_path, overrides={"weak_genre_aliases": {"护士": "不存在"}}))
    assert cfg.weak_genre_aliases == {}
    assert any("weak_genre_aliases" in w and "不存在" in w for w in cfg.warnings)


def test_weak_alias_defaults_empty(tmp_path):
    cfg = load_config(build_env(tmp_path))
    assert cfg.weak_genre_aliases == {}


def test_dump_round_trips_weak_aliases(tmp_path):
    cfg = load_config(build_env(
        tmp_path,
        overrides={"weak_genre_aliases": {"护士": "动作", "女同接吻": "科幻"}}))
    target = tmp_path / "roundtrip.toml"
    target.write_text(dump_config_text(describe(cfg)), encoding="utf-8")
    assert load_config(target).weak_genre_aliases == cfg.weak_genre_aliases


def test_describe_and_raw_describe_include_weak(tmp_path):
    cfg = load_config(build_env(
        tmp_path, overrides={"weak_genre_aliases": {"护士": "动作"}}))
    described = describe(cfg)
    assert isinstance(described["weak_genre_aliases"], dict)
    assert described["weak_genre_aliases"] == {"护士": "动作"}
    raw = raw_describe({"weak_genre_aliases": {"护士": "动作"}})
    assert isinstance(raw["weak_genre_aliases"], dict)
    assert raw["weak_genre_aliases"] == {"护士": "动作"}


def test_config_hash_changes_with_weak(tmp_path):
    plain = load_config(build_env(tmp_path))
    weak = load_config(build_env(
        tmp_path, overrides={"weak_genre_aliases": {"护士": "动作"}}))
    assert plain.config_hash() != weak.config_hash()


def test_title_options_loaded_defaults(tmp_path):
    cfg = load_config(build_env(tmp_path))
    assert cfg.title.enabled is True
    assert cfg.title.min_score == 1.0


def test_title_min_score_negative_rejected(tmp_path):
    with pytest.raises(ConfigError) as excinfo:
        load_config(build_env(
            tmp_path, overrides={"title": {"enabled": True, "min_score": -0.5}}))
    assert "title.min_score" in str(excinfo.value)


def test_dump_round_trips_title(tmp_path):
    cfg = load_config(build_env(
        tmp_path, overrides={"title": {"enabled": False, "min_score": 0.5}}))
    target = tmp_path / "roundtrip_title.toml"
    target.write_text(dump_config_text(describe(cfg)), encoding="utf-8")
    reloaded = load_config(target)
    assert reloaded.title.enabled == cfg.title.enabled
    assert reloaded.title.min_score == cfg.title.min_score


def test_describe_raw_describe_title(tmp_path):
    cfg = load_config(build_env(tmp_path))
    described = describe(cfg)
    assert isinstance(described["title"], dict)
    assert "enabled" in described["title"]
    assert "min_score" in described["title"]
    raw = raw_describe({})
    assert isinstance(raw["title"], dict)
    assert "enabled" in raw["title"]
    assert "min_score" in raw["title"]


def test_config_hash_changes_with_title(tmp_path):
    plain = load_config(build_env(tmp_path))
    other = load_config(build_env(tmp_path))
    other.title = TitleOptions(enabled=False, min_score=0.5)
    assert plain.config_hash() != other.config_hash()


def test_config_hash_covers_on_conflict_plot_learning(tmp_path):
    """审计回归：影响计划生成的配置（on_conflict / plot / learning）必须进哈希，
    否则外部手改 config.toml 后冻结计划的漂移检测形同虚设。"""
    from app.core.config import LearningOptions, PlotOptions

    h0 = load_config(build_env(tmp_path)).config_hash()
    other1 = load_config(build_env(tmp_path))
    other1.on_conflict = "rename"
    other2 = load_config(build_env(tmp_path))
    other2.plot = PlotOptions(enabled=True, min_score=3.5, normalize=False)
    other3 = load_config(build_env(tmp_path))
    other3.learning = LearningOptions(enabled=True, min_votes=5)
    assert other1.config_hash() != h0, "on_conflict 影响 build_plan 冲突状态，必须进哈希"
    assert other2.config_hash() != h0, "plot.min_score 影响摘要择优判定，必须进哈希"
    assert other3.config_hash() != h0, "learning.min_votes 影响自学习自动生效，必须进哈希"


# ---------------- 悬空引用宽容降级（卡 card-20261112-lenient-aliases） ----------------

def test_dangling_entries_excluded_from_config_hash(tmp_path):
    """被忽略的悬空条目不得进 config_hash，否则计划页误报配置漂移。
    （同根目录重写配置再比对：换根目录会连路径哈希一起变，测不到悬空条目。）"""
    cfg_path = build_env(tmp_path)
    h1 = load_config(cfg_path).config_hash()
    build_env(tmp_path, overrides={
        "genre_aliases": {"Sci-Fi": "科幻", "scifi": "科幻", "僵尸": "不存在"}})
    h2 = load_config(cfg_path).config_hash()
    assert h1 == h2


def test_describe_includes_warnings(tmp_path):
    cfg = load_config(build_env(
        tmp_path, overrides={"genre_aliases": {"x": "不存在"}}))
    assert describe(cfg)["warnings"] == cfg.warnings
    assert cfg.warnings                              # 非空


def test_describe_warnings_empty_when_clean(tmp_path):
    assert describe(load_config(build_env(tmp_path)))["warnings"] == []


def test_save_config_dict_accepts_dangling_aliases(tmp_path):
    """含悬空别名的表单保存必须成功：写盘透明 + 返回的 Config 带警告。"""
    cfg_path = build_env(tmp_path)
    d = describe(load_config(cfg_path))
    d["genre_aliases"] = {"幽灵": "不存在"}
    new_cfg = save_config_dict(cfg_path, d)
    assert any("幽灵" in w for w in new_cfg.warnings)
    assert "幽灵" in cfg_path.read_text(encoding="utf-8")     # 原样写盘
    assert not (tmp_path / "runtime" / "config.candidate.toml").exists()  # 原子替换完成


def test_example_config_aliases_are_self_consistent():
    """example 的别名/优先级必须全部指向 example 自带的库（tomllib 裸解析——
    example 路径指向不存在的盘符，走完整 load_config 会卡在 _require_dir）。"""
    root = Path(__file__).resolve().parents[1]
    with open(root / "config.example.toml", "rb") as fh:
        data = tomllib.load(fh)
    names = {lib["name"] for lib in data.get("library", [])}
    assert "thriller" not in (data.get("genre_aliases") or {})
    assert "musical" not in (data.get("genre_aliases") or {})
    assert all(v in names for v in (data.get("genre_aliases") or {}).values())
    assert all(v in names for v in (data.get("weak_genre_aliases") or {}).values())
    assert all(n in names for n in data.get("genre_priority", []))


# ---------------- 首跑自洽（卡 card-20261112-firstrun-tooltips-icon） ----------------

def test_first_run_bootstrap_creates_valid_config(tmp_path):
    cfg_path = tmp_path / "cfg" / "config.toml"
    assert ensure_first_run_config(cfg_path) is True
    cfg = load_config(cfg_path)                       # 必须全量校验通过（首跑不炸的硬承诺）
    assert list(cfg.libraries) == ["电影"]
    base = cfg_path.parent / "data"
    assert cfg.source_root == (base / "待整理").resolve()
    assert cfg.fallback_path == (base / "未分类").resolve()
    assert (base / "待整理").is_dir() and (base / "电影").is_dir() \
        and (base / "未分类").is_dir()


def test_first_run_bootstrap_is_idempotent(tmp_path):
    cfg_path = tmp_path / "config.toml"
    assert ensure_first_run_config(cfg_path) is True
    text = cfg_path.read_text(encoding="utf-8")
    assert ensure_first_run_config(cfg_path) is False
    assert cfg_path.read_text(encoding="utf-8") == text


def test_first_run_bootstrap_independent_of_cwd(tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    cfg_path = tmp_path / "cfg" / "config.toml"
    ensure_first_run_config(cfg_path)
    cfg = load_config(cfg_path)
    assert cfg.source_root == (cfg_path.parent / "data" / "待整理").resolve()

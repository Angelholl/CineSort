"""配置校验测试（评议条件 C4）。"""
import pytest
from conftest import build_env

from app.core.config import (
    ConfigError,
    check_session_root,
    describe,
    dump_config_text,
    is_sub_path,
    load_config,
    raw_describe,
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


def test_unknown_priority_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_config(build_env(tmp_path, overrides={"genre_priority": ["不存在"]}))


def test_unknown_alias_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_config(build_env(tmp_path, overrides={"genre_aliases": {"x": "不存在"}}))


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


def test_weak_alias_unknown_lib_rejected(tmp_path):
    with pytest.raises(ConfigError) as excinfo:
        load_config(build_env(
            tmp_path, overrides={"weak_genre_aliases": {"护士": "不存在"}}))
    assert "weak_genre_aliases" in str(excinfo.value)


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

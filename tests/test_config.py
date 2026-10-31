"""配置校验测试（评议条件 C4）。"""
import pytest

from app.core.config import ConfigError, is_sub_path, load_config
from conftest import build_env


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

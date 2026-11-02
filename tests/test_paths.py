"""冻结（exe）路径解析测试。"""
import sys
from pathlib import Path

from app import paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_source_mode_roots(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert paths.app_root() == PROJECT_ROOT
    assert paths.resource_root() == PROJECT_ROOT
    assert paths.default_config_path() == PROJECT_ROOT / "config.toml"


def test_frozen_mode_roots(tmp_path, monkeypatch):
    fake_exe = tmp_path / "dist" / "JellyfinNFOSorter.exe"
    fake_exe.parent.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    assert paths.app_root() == fake_exe.parent
    assert paths.resource_root() == tmp_path / "bundle"


def _frozen_unwritable(tmp_path, monkeypatch):
    """模拟"装进 Program Files（不可写）"的冻结形态。"""
    fake_exe = tmp_path / "read-only" / "CineSort.exe"
    fake_exe.parent.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
    monkeypatch.setattr(paths, "_dir_writable", lambda p: False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return tmp_path / "appdata"


def test_frozen_unwritable_dir_falls_back_to_appdata(tmp_path, monkeypatch):
    """安装版主路径：Program Files 不可写 → 配置落 %APPDATA%/CineSort。

    目录名必须是 CineSort（D-20261102-01 裁定），旧 JellyfinNFOSorter 为漏改。
    """
    appdata = _frozen_unwritable(tmp_path, monkeypatch)
    p = paths.default_config_path()
    assert p == appdata / "CineSort" / "config.toml"
    assert p.parent.is_dir()                      # 回退目录需已建好
    assert (appdata / "JellyfinNFOSorter").exists() is False


def test_legacy_appdata_config_is_reused(tmp_path, monkeypatch):
    """旧安装（%APPDATA%/JellyfinNFOSorter/config.toml）不得被静默丢弃。

    返回旧路径即 runtime/（journals + learned.json）继续留在旧目录，
    与 config.toml 同父，回滚日志与自学习数据不会失联。
    """
    appdata = _frozen_unwritable(tmp_path, monkeypatch)
    legacy = appdata / "JellyfinNFOSorter"
    legacy.mkdir(parents=True)
    (legacy / "config.toml").write_text("[legacy]", encoding="utf-8")
    assert paths.default_config_path() == legacy / "config.toml"


def test_new_appdata_wins_over_legacy(tmp_path, monkeypatch):
    """新目录已有配置时，旧目录不再参与解析。"""
    appdata = _frozen_unwritable(tmp_path, monkeypatch)
    for name in ("CineSort", "JellyfinNFOSorter"):
        d = appdata / name
        d.mkdir(parents=True)
        (d / "config.toml").write_text("[new]", encoding="utf-8")
    assert paths.default_config_path() == appdata / "CineSort" / "config.toml"


def test_dir_writable_probe(tmp_path):
    assert paths._dir_writable(tmp_path) is True
    assert not (tmp_path / ".write_probe").exists()

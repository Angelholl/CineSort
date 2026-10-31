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


def test_frozen_unwritable_dir_falls_back_to_appdata(tmp_path, monkeypatch):
    fake_exe = tmp_path / "read-only" / "JellyfinNFOSorter.exe"
    fake_exe.parent.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
    monkeypatch.setattr(paths, "_dir_writable", lambda p: False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    p = paths.default_config_path()
    assert p == tmp_path / "appdata" / "JellyfinNFOSorter" / "config.toml"


def test_dir_writable_probe(tmp_path):
    assert paths._dir_writable(tmp_path) is True
    assert not (tmp_path / ".write_probe").exists()

"""路径解析：兼容源码运行与 PyInstaller 冻结（exe）两种形态。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_root() -> Path:
    """可写的工作根：源码形态=项目根；exe 形态=exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """只读资源根（static / config.example.toml）：exe 形态=解包临时目录。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", "") \
            else Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _dir_writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write_probe"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


_APPDATA_DIR = "CineSort"
# 更名（D-20261101-05）漏改的旧目录名：若用户已有旧安装，其 config.toml
# 与同父的 runtime/（journals + learned.json）必须继续可见，不得静默丢弃。
_LEGACY_APPDATA_DIRS = ("JellyfinNFOSorter",)


def default_config_path() -> Path:
    """默认配置路径：exe 优先放 exe 旁（便携模式）；目录不可写
    （如安装进 Program Files）则退回 %APPDATA%/CineSort（D-20261102-01）。

    安装版分发下不可写是常态，故此回退路径是主路径而非边缘情况。
    新目录尚无配置时，复用旧 JellyfinNFOSorter 目录里的既有配置。
    """
    root = app_root()
    if getattr(sys, "frozen", False) and not _dir_writable(root):
        appdata = Path(os.environ.get("APPDATA") or Path.home())
        new_cfg = appdata / _APPDATA_DIR / "config.toml"
        if not new_cfg.exists():
            for legacy in _LEGACY_APPDATA_DIRS:
                old_cfg = appdata / legacy / "config.toml"
                if old_cfg.exists():
                    return old_cfg
        new_cfg.parent.mkdir(parents=True, exist_ok=True)
        return new_cfg
    return root / "config.toml"

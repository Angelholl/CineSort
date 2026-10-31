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


def default_config_path() -> Path:
    """默认配置路径：exe 优先放 exe 旁（便携模式）；目录不可写
    （如安装进 Program Files）则退回 %APPDATA%/JellyfinNFOSorter。"""
    root = app_root()
    if getattr(sys, "frozen", False) and not _dir_writable(root):
        base = Path(os.environ.get("APPDATA") or Path.home()) / "JellyfinNFOSorter"
        base.mkdir(parents=True, exist_ok=True)
        return base / "config.toml"
    return root / "config.toml"

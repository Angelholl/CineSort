"""启动链守卫：入口不含 HTTP/网页版残留；单实例锁语义；删除文件防复活。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_entry_has_no_http_references():
    """run.py / app.__main__ / main_window 源码不得再引用网页版符号。"""
    banned = ("main_gui", "app.server", "create_server",
              "serve_forever", "static/index.html")
    for name in ("run.py", "app/__main__.py", "app/ui/main_window.py"):
        text = (ROOT / name).read_text(encoding="utf-8")
        hits = [b for b in banned if b in text]
        assert not hits, f"{name} 残留网页版引用：{hits}"


def test_acquire_lock_excludes_second_instance(tmp_path):
    """单实例锁：同目录首次 True、二次 False；不同目录再 True（按目录隔离）。"""
    import importlib

    from app.ui import main_window as mw
    importlib.reload(mw)  # 重置模块级句柄，避免受其他测试影响
    fh1 = mw._acquire_lock(tmp_path)
    try:
        assert fh1 is not None
        # 锁随句柄存活：句柄在持（fh1 未关）时同目录二次加锁必须失败
        assert mw._acquire_lock(tmp_path) is None
        tmp_path2 = tmp_path / "other"
        assert mw._acquire_lock(tmp_path2) is not None
    finally:
        fh1.close()


def test_deleted_files_gone():
    """网页版残留文件不得复活。"""
    gone = ("app/server.py", "app/main_gui.py", "app/static/index.html",
            "tests/test_api.py", "JellyfinNFOSorter.spec")
    for rel in gone:
        assert (ROOT / rel).exists() is False, f"{rel} 不应存在"

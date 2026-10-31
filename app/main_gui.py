"""GUI 启动入口：单实例锁 → 配置兜底 → 起服务 → 打开浏览器。

    python -m app.main_gui [--config 路径] [--port 8765] [--no-browser]
"""
from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__
from .paths import app_root, default_config_path, resource_root
from .server import AppState, create_server

log = logging.getLogger("nfo-sorter")


def _acquire_lock(runtime_dir: Path):
    """单实例锁：msvcrt.locking（Windows）/ fcntl.flock（其他）。"""
    runtime_dir.mkdir(parents=True, exist_ok=True)
    fh = open(runtime_dir / "app.lock", "a+b")
    try:
        import msvcrt
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except ImportError:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return None
    except OSError:
        fh.close()
        return None
    return fh


def _find_free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 0


def _setup_logging(runtime_dir: Path) -> None:
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(log_dir / "gui.log", encoding="utf-8")]
    if sys.stdout:                      # pythonw 下 stdout 为 None
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(message)s")


def print_safe(msg: str) -> None:
    try:
        print(msg)
    except Exception:  # noqa: BLE001  pythonw 下无 stdout
        pass


def _alert(msg: str) -> None:
    log.error(msg)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "CineSort 影片归类器", 0x30)
    except Exception:  # noqa: BLE001
        print_safe(msg)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="cinesort", description="CineSort 影片归类器")
    parser.add_argument("--config", default=None,
                        help="config.toml 路径（默认程序根目录）")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    root = app_root()
    config_path = Path(args.config).resolve() if args.config else default_config_path()
    if not config_path.exists():
        example = resource_root() / "config.example.toml"
        if example.exists():
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(example.read_text(encoding="utf-8"),
                                   encoding="utf-8")

    runtime = config_path.parent / "runtime"
    lock = _acquire_lock(runtime)
    if lock is None:
        _alert("已有实例在运行（如确认没有，请删除 runtime/app.lock 后重试）")
        return 1
    _setup_logging(runtime)
    log.info("CineSort v%s 启动，配置：%s", __version__, config_path)

    state = AppState(config_path)
    port = _find_free_port(args.port)
    httpd = create_server(state, port)
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    log.info("GUI 地址：%s", url)
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    print_safe(f"CineSort 已启动：{url}（关闭本窗口即退出）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        import traceback
        err = traceback.format_exc()
        try:
            errlog = app_root() / "startup-error.log"
            errlog.write_text(err, encoding="utf-8")
        except OSError:
            pass
        _alert("启动失败，详情见 startup-error.log：\n" + err[-800:])
        sys.exit(1)

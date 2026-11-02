"""本地 GUI 服务：stdlib HTTP + JSON API，仅绑定 127.0.0.1。"""
from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .core import jobs as jobs_mod
from .core.config import ConfigError
from .paths import resource_root

log = logging.getLogger("nfo-sorter.server")

_STATIC_DIR = resource_root() / "app" / "static"

from .state import AppState  # re-export：保持既有 import 路径有效


def route_post(state: AppState, path: str, body: dict) -> dict:
    """薄转发层：仅做 JSON 字段到 str 的归一化，业务编排在 AppState 里。"""
    if path == "/api/scan":
        return state.start_scan()
    if path == "/api/apply":
        ids = [str(x) for x in (body.get("ids") or [])]
        acks = {str(x) for x in (body.get("acks") or [])}
        overrides = {str(k): str(v)
                     for k, v in (body.get("overrides") or {}).items()}
        return state.start_apply(ids, acks, overrides)
    if path == "/api/undo":
        return state.start_undo(str(body.get("file") or ""))
    if path == "/api/undo_preview":
        return state.undo_preview(str(body.get("file") or ""))
    if path == "/api/preflight":
        ids = {str(x) for x in (body.get("ids") or [])}
        return {"items": state.preflight_items(ids or None)}
    if path == "/api/cleanup_staging":
        return {"removed": state.cleanup_staging()}
    if path == "/api/learned_forget":
        return {"learned": state.learned_forget(
            str(body.get("key") or ""), str(body.get("lib") or ""))}
    if path == "/api/config":
        return {"valid": True, "config": state.save_config(body)}
    if path == "/api/cancel":
        return {"cancelled": state.cancel_job()}
    raise KeyError(f"未知 API：{path}")


def make_handler(state: AppState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "NFOSorter/" + __version__

        def log_message(self, fmt, *args):   # 安静模式：仅 debug
            log.debug("%s " + fmt, self.address_string(), *args)

        def _send(self, code: int, payload, ctype="application/json; charset=utf-8"):
            if isinstance(payload, (dict, list)):
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            else:
                data = payload
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _json_body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                obj = json.loads(raw.decode("utf-8"))
                return obj if isinstance(obj, dict) else {}
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {}

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                try:
                    data = (_STATIC_DIR / "index.html").read_bytes()
                except OSError:
                    self._send(500, {"error": "前端文件缺失：app/static/index.html"})
                    return
                self._send(200, data, "text/html; charset=utf-8")
            elif path == "/favicon.ico":
                self._send(204, b"", "image/x-icon")
            elif path == "/api/state":
                self._send(200, state.state_snapshot())
            elif path == "/api/config":
                desc, err = state.config_describe()
                self._send(200, {"valid": err is None, "config": desc, "error": err})
            elif path == "/api/plan":
                self._send(200, {"plan": state.plan()})
            else:
                self._send(404, {"error": f"未知路径：{path}"})

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            body = self._json_body()
            try:
                self._send(200, route_post(state, path, body))
            except ConfigError as exc:
                self._send(200, {"error": str(exc)})
            except (jobs_mod.BusyError, ValueError) as exc:
                self._send(409, {"error": str(exc)})
            except Exception as exc:
                log.exception("POST %s 失败", path)
                self._send(500, {"error": str(exc)})

    return Handler


def create_server(state: AppState, port: int = 0) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    httpd.daemon_threads = True
    return httpd

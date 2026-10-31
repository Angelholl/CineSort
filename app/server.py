"""本地 GUI 服务：stdlib HTTP + JSON API，仅绑定 127.0.0.1。"""
from __future__ import annotations

import json
import logging
import threading
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from .core import jobs as jobs_mod, preflight
from .core import learned as learned_store
from .core.config import (ConfigError, describe, load_config, raw_describe,
                          save_config_dict)
from .core.journal import done_entries, is_valid_session_name, list_sessions
from .core.planner import load_plan, plan_digest
from .paths import resource_root

log = logging.getLogger("nfo-sorter.server")

_STATIC_DIR = resource_root() / "app" / "static"


class AppState:
    """服务端共享状态：配置路径 / 计划缓存 / 任务管理器。"""

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self.jobs = jobs_mod.JobManager()
        self._plan_lock = threading.Lock()
        self._plan_cache: dict | None = None

    def runtime_dir(self) -> Path:
        return self.config_path.parent / "runtime"

    def plan(self) -> dict | None:
        with self._plan_lock:
            if self._plan_cache is None:
                self._plan_cache = load_plan(self.runtime_dir())
            return self._plan_cache

    def invalidate_plan(self) -> None:
        with self._plan_lock:
            self._plan_cache = None

    def config_describe(self) -> tuple[dict | None, str | None]:
        try:
            cfg = load_config(self.config_path)
            return describe(cfg), None
        except ConfigError as exc:
            err = str(exc)
        # 配置非法时用示例/原始文件兜底展示，便于 GUI 首跑编辑
        for candidate in (self.config_path,
                          self.config_path.parent / "config.example.toml"):
            try:
                with open(candidate, "rb") as fh:
                    return raw_describe(tomllib.load(fh)), err
            except (OSError, tomllib.TOMLDecodeError):
                continue
        return None, err

    def state_snapshot(self) -> dict:
        cfg_desc, cfg_error = self.config_describe()
        plan = self.plan()
        return {
            "ok": True,
            "version": __version__,
            "config_path": str(self.config_path),
            "config": cfg_desc,
            "config_error": cfg_error,
            "plan": plan,
            "plan_digest": plan_digest(plan) if plan else None,
            "job": self.jobs.job.snapshot() if self.jobs.job else None,
            "sessions": list_sessions(self.runtime_dir() / "journals"),
            "learned": learned_store.items(learned_store.load(self.runtime_dir())),
        }


def undo_preview(state: AppState, fname: str) -> dict:
    if not is_valid_session_name(fname):
        raise ValueError("非法的会话文件名")
    path = state.runtime_dir() / "journals" / fname
    if not path.is_file():
        raise ValueError("会话日志不存在")
    ops = []
    for e in reversed(done_entries(path)):
        dst = Path(e.get("dst_dir", ""))
        src = Path(e.get("src_dir", ""))
        st = "ok"
        if not dst.exists():
            st = "skip_target_missing"
        elif e.get("kind", "dir") == "dir" and src.exists():
            st = "skip_src_exists"
        ops.append({"unit_id": e.get("unit_id", "?"), "kind": e.get("kind", "dir"),
                    "src_dir": str(src), "dst_dir": str(dst), "state": st})
    return {"ops": ops, "file": fname}


def route_post(state: AppState, path: str, body: dict) -> dict:
    if path == "/api/scan":
        state.jobs.start("scan", lambda job: jobs_mod.run_scan(state, job))
        return {"ok": True}
    if path == "/api/apply":
        ids = [str(x) for x in (body.get("ids") or [])]
        acks = {str(x) for x in (body.get("acks") or [])}
        overrides = {str(k): str(v)
                     for k, v in (body.get("overrides") or {}).items()}
        state.jobs.start("apply", lambda job: jobs_mod.run_apply(
            state, job, ids, acks, overrides))
        return {"ok": True}
    if path == "/api/undo":
        fname = str(body.get("file") or "")
        state.jobs.start("undo", lambda job: jobs_mod.run_undo(state, job, fname))
        return {"ok": True}
    if path == "/api/undo_preview":
        return undo_preview(state, str(body.get("file") or ""))
    if path == "/api/preflight":
        cfg = load_config(state.config_path)
        ids = {str(x) for x in (body.get("ids") or [])}
        items = preflight.run_preflight(cfg, state.plan(), selected_ids=ids or None)
        return {"items": items}
    if path == "/api/cleanup_staging":
        cfg = load_config(state.config_path)
        return {"removed": preflight.cleanup_staging(cfg)}
    if path == "/api/learned_forget":
        learned_store.forget(state.runtime_dir(),
                             str(body.get("key") or ""), str(body.get("lib") or ""))
        return {"learned": learned_store.items(
            learned_store.load(state.runtime_dir()))}
    if path == "/api/config":
        new_cfg = save_config_dict(state.config_path, body)
        state.invalidate_plan()          # 配置已变，旧计划按哈希自动过期
        return {"valid": True, "config": describe(new_cfg)}
    if path == "/api/cancel":
        return {"cancelled": state.jobs.cancel()}
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
            except Exception as exc:  # noqa: BLE001
                log.exception("POST %s 失败", path)
                self._send(500, {"error": str(exc)})

    return Handler


def create_server(state: AppState, port: int = 0) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    httpd.daemon_threads = True
    return httpd

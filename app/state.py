"""共享应用状态：配置路径 / 计划缓存 / 任务管理器。与任何 UI 形态（HTTP 或原生窗口）无关。"""
from __future__ import annotations

import threading
import tomllib
from pathlib import Path

from . import __version__
from .core import jobs as jobs_mod
from .core import learned as learned_store
from .core.config import ConfigError, describe, load_config, raw_describe
from .core.journal import list_sessions
from .core.planner import load_plan, plan_digest


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

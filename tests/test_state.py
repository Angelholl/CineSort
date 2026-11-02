"""AppState 必须能在完全不触碰 http.server 的前提下被导入与使用。"""
from __future__ import annotations

import subprocess
import sys

from app.state import AppState


def test_importing_state_does_not_pull_http_server():
    """架构守卫：app.state 及其全部下游依赖不得引入 http.server。
    桌面 GUI 依赖 app.state，若它把 http.server 拖进来则层次划分失效。"""
    code = (
        "import sys, app.state;"
        "bad=[m for m in sys.modules if m.startswith('http')];"
        "print(bad);sys.exit(1 if bad else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"app.state 拖进了 HTTP 模块：{proc.stdout}{proc.stderr}"


def test_state_snapshot_shape(tmp_path):
    """AppState 搬到新模块后，快照字段必须与迁移前完全一致。"""
    state = AppState(tmp_path / "config.toml")
    snap = state.state_snapshot()
    assert set(snap) == {"ok", "version", "config_path", "config", "config_error",
                         "plan", "plan_digest", "job", "sessions", "learned"}
    assert snap["ok"] is True
    assert snap["plan"] is None and snap["job"] is None
    assert snap["config_path"] == str(tmp_path / "config.toml")
    # 配置缺失时 config_error 非空、config 走示例兜底或 None，不得抛异常
    assert snap["config_error"]

    assert state.plan() is None
    state.invalidate_plan()
    assert state.runtime_dir() == tmp_path / "runtime"

    # 防回归：server 的 re-export 必须仍指向同一个类
    from app.server import AppState as S2
    assert S2 is AppState

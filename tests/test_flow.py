"""全链路集成测试（不经 HTTP）：扫描 → 执行 → 自学习 → 回滚，兼作冒烟。

与 tests/test_api.py 逐一对应，是删除网页版后的唯一全链路证据，不得删减。
"""
from __future__ import annotations

import json
import threading
import time

import pytest
from conftest import build_env, make_movie

from app.core import jobs as jobs_mod
from app.core.config import ConfigError, load_config
from app.core.journal import list_sessions
from app.state import AppState


def wait_job(state, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = state.jobs.job
        if job and job.status != "running":
            return job.snapshot()
        time.sleep(0.15)
    raise AssertionError("任务超时未结束")


@pytest.fixture()
def env_state(tmp_path):
    """返回 (AppState, Config)：state 驱动全流程，cfg 供磁盘断言取路径。"""
    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    src = cfg.source_root
    make_movie(src, "Space War (2021)", title="Space War", genres=("科幻",),
               plot="太空宇宙飞船大战", tmdb="21")
    make_movie(src, "Gun Fight (2022)", title="Gun Fight", genres=("动作",),
               plot="特工枪战", tmdb="22")
    return AppState(cfg_path), cfg


def test_scan_apply_undo_flow(env_state):
    state, env = env_state

    state.start_scan()
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    plan = state.plan()
    assert plan["stats"]["ready"] == 2
    units = {u["id"]: u for u in plan["units"]}
    assert units["Space War (2021)"]["target_lib"] == "科幻"
    assert units["Gun Fight (2022)"]["target_lib"] == "动作"

    state.start_apply(list(units), {"jellyfin_running"}, {})
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    r = st["result"]
    assert r["moved"] == 2 and r["failed"] == 0
    assert (env.libraries["科幻"].path / "Space War (2021)").is_dir()
    assert (env.libraries["动作"].path / "Gun Fight (2022)").is_dir()
    assert not (env.source_root / "Space War (2021)").exists()
    # invalidate_plan 已由 run_apply 触发，重新读盘后应见 applied
    assert state.plan()["stats"]["by_status"]["applied"] == 2

    # 执行结果应沉淀为自学习映射（D-20261101-03）
    learned = json.loads((env.path.parent / "runtime" / "learned.json")
                         .read_text(encoding="utf-8"))
    libs_voted = {lib for e in learned["entries"].values() for lib in e["libs"]}
    assert {"科幻", "动作"} <= libs_voted
    assert "learned" in state.state_snapshot()

    sess = list_sessions(state.runtime_dir() / "journals")[0]["file"]
    prev = state.undo_preview(sess)
    assert len(prev["ops"]) == 2 and all(o["state"] == "ok" for o in prev["ops"])
    state.start_undo(sess)
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    assert st["result"]["restored"] == 2
    assert (env.source_root / "Space War (2021)").is_dir()
    assert not (env.libraries["科幻"].path / "Space War (2021)").exists()


def test_apply_blocked_on_source_drift(env_state):
    state, env = env_state
    state.start_scan()
    st = wait_job(state)
    unit = state.plan()["units"][0]
    make_movie(env.source_root, unit["id"], title="x", genres=("科幻",), tmdb="99")
    state.start_apply([unit["id"]], set(), {})
    st = wait_job(state)
    assert st["status"] == "failed"
    assert "未执行任何操作" in st["error"]


def test_config_save_validate_and_reject(env_state):
    state, env = env_state
    cfg_desc = state.state_snapshot()["config"]
    assert cfg_desc["strategy"] == "smart"
    cfg_desc["strategy"] = "priority"
    assert state.save_config(cfg_desc)["strategy"] == "priority"
    assert state.state_snapshot()["config"]["strategy"] == "priority"

    bad = dict(state.state_snapshot()["config"])
    bad["source_root"] = str(env.path.parent / "nope")
    with pytest.raises(ConfigError):
        state.save_config(bad)
    assert state.state_snapshot()["config"]["source_root"] == str(env.source_root)


def test_undo_preview_rejects_bad_name(env_state):
    state, _ = env_state
    with pytest.raises(ValueError):
        state.undo_preview("../../evil.jsonl")


def test_preflight_job_reports_items(env_state):
    """体检走后台任务（D-20261102-01 纪律 1）：结果在 job.result["items"]，
    环境健康时无阻断。"""
    state, _ = env_state
    state.start_scan()
    wait_job(state)
    ids = [u["id"] for u in state.plan()["units"]]
    state.start_preflight(ids)
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    items = st["result"]["items"]
    assert items, "体检至少应输出一项"
    assert all(i["level"] in ("block", "warn", "info") for i in items)
    assert all({"code", "message"} <= set(i) for i in items)
    # 测试环境的目录全部存在，不应出现路径缺失阻断
    assert all(i["code"] != "paths_missing" for i in items)


def test_busy_error_on_concurrent_jobs(env_state):
    """任务运行中重复触发必须报错（桌面版按钮双击的前提）。"""
    state, _ = env_state
    gate = threading.Event()
    try:
        state.jobs.start("scan", lambda job: gate.wait(5))
        with pytest.raises(jobs_mod.BusyError):
            state.start_apply(["nope"], set(), {})
    finally:
        gate.set()

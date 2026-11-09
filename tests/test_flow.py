"""全链路集成测试（不经 HTTP）：扫描 → 执行 → 自学习 → 回滚，兼作冒烟。

与 tests/test_api.py 逐一对应，是删除网页版后的唯一全链路证据，不得删减。
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from conftest import build_env, make_movie

from app.core import jobs as jobs_mod
from app.core import preflight, scanner
from app.core.config import ConfigError, load_config
from app.core.journal import list_sessions
from app.core.planner import build_plan
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


def test_preflight_extra_staging_roots_block(tmp_path):
    """本次输出目录的 staging 根也纳入残留检测（Task-03）。"""
    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    extra = tmp_path / "out" / ".nfo-sorter-staging" / "some-session"
    extra.mkdir(parents=True)
    (extra / ".incomplete-20261109").write_text("x", encoding="utf-8")
    items = preflight.run_preflight(
        cfg, None, extra_staging_roots=[tmp_path / "out" / ".nfo-sorter-staging"])
    assert any(i["level"] == "block" and i["code"] == "staging_leftover"
               for i in items)
    # 对照组：不传 extra_staging_roots 时同一残留不报（参数生效且不影响默认行为）
    items_plain = preflight.run_preflight(cfg, None)
    assert all(i["code"] != "staging_leftover" for i in items_plain)


def _apply_session(state, out, group_by_category):
    state.start_scan()
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    ids = [u["id"] for u in state.plan()["units"]]
    out.mkdir(parents=True, exist_ok=True)
    state.start_apply(ids, {"jellyfin_running"}, {},
                      output_root=str(out), group_by_category=group_by_category)
    return wait_job(state)


def test_apply_session_output_flat(env_state):
    state, env = env_state
    out = env.path.parent / "本次输出"
    st = _apply_session(state, out, group_by_category=False)
    assert st["status"] == "done", st["log"]
    r = st["result"]
    assert r["moved"] == 2 and r["failed"] == 0
    assert (out / "Space War (2021)").is_dir()
    assert (out / "Gun Fight (2022)").is_dir()
    assert not (env.source_root / "Space War (2021)").exists()
    assert not (env.source_root / "Gun Fight (2022)").exists()


def test_apply_session_output_group_by_category(env_state):
    state, env = env_state
    out = env.path.parent / "本次输出"
    st = _apply_session(state, out, group_by_category=True)
    assert st["status"] == "done", st["log"]
    assert (out / "科幻" / "Space War (2021)").is_dir()
    assert (out / "动作" / "Gun Fight (2022)").is_dir()


def test_apply_session_output_not_persisted_to_plan(env_state):
    state, env = env_state
    out = env.path.parent / "本次输出"
    st = _apply_session(state, out, group_by_category=False)
    assert st["status"] == "done", st["log"]
    plan = state.plan()
    for u in plan["units"]:
        assert "本次输出" not in u["dst_dir"]
    assert "本次输出" not in env.path.read_text(encoding="utf-8")


def test_apply_session_output_rejects_invalid_root(env_state):
    state, env = env_state
    state.start_scan()
    st = wait_job(state)
    ids = [u["id"] for u in state.plan()["units"]]
    ghost = env.path.parent / "ghost"
    state.start_apply(ids, {"jellyfin_running"}, {},
                      output_root=str(ghost), group_by_category=False)
    st = wait_job(state)
    assert st["status"] == "failed"
    assert "输出目录不可用" in st["error"]
    assert (env.source_root / "Space War (2021)").is_dir()
    assert (env.source_root / "Gun Fight (2022)").is_dir()


def test_apply_session_output_inside_source_rejected(env_state):
    state, env = env_state
    state.start_scan()
    st = wait_job(state)
    ids = [u["id"] for u in state.plan()["units"]]
    out = env.source_root / "out"
    out.mkdir()
    state.start_apply(ids, {"jellyfin_running"}, {},
                      output_root=str(out), group_by_category=False)
    st = wait_job(state)
    assert st["status"] == "failed"
    assert "输出目录不可用" in st["error"]
    assert (env.source_root / "Space War (2021)").is_dir()
    assert (env.source_root / "Gun Fight (2022)").is_dir()


# ---------------- 三层布局执行链（D-20261110-01，Task-03） ----------------

def _make_actress_env(tmp_path):
    """女优容器环境：build_env + 源根下一乃あおい/ABC-1 科幻单元。"""
    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    make_movie(cfg.source_root / "一乃あおい", "ABC-1", title="ABC-1",
               genres=("科幻",), plot="太空宇宙", tmdb="31")
    return AppState(cfg_path), cfg


def test_apply_drilled_unit_three_layer_layout(tmp_path):
    state, cfg = _make_actress_env(tmp_path)
    scifi = cfg.libraries["科幻"].path
    state.start_scan()
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    state.start_apply(["一乃あおい/ABC-1"], {"jellyfin_running"}, {})
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    assert st["result"]["moved"] == 1
    assert (scifi / "一乃あおい" / "ABC-1").is_dir()
    assert not (cfg.source_root / "一乃あおい" / "ABC-1").exists()
    assert (cfg.source_root / "一乃あおい").is_dir()   # 空壳=规格接受的残留
    assert state.plan()["stats"]["by_status"]["applied"] == 1


def test_apply_drilled_unit_creates_actress_dir(tmp_path):
    """库内无该女优目录：dst.parent.mkdir 自动创建女优层。"""
    state, cfg = _make_actress_env(tmp_path)
    make_movie(cfg.source_root / "新人子", "XYZ-1", title="XYZ-1",
               genres=("科幻",), plot="太空宇宙", tmdb="32")
    scifi = cfg.libraries["科幻"].path
    assert not (scifi / "新人子").exists()
    state.start_scan()
    wait_job(state)
    state.start_apply(["新人子/XYZ-1"], {"jellyfin_running"}, {})
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    assert (scifi / "新人子" / "XYZ-1").is_dir()


def test_apply_session_output_grouped_three_layers(tmp_path):
    state, cfg = _make_actress_env(tmp_path)
    out = cfg.path.parent / "本次输出"
    state.start_scan()
    wait_job(state)
    out.mkdir(parents=True, exist_ok=True)
    state.start_apply(["一乃あおい/ABC-1"], {"jellyfin_running"}, {},
                      output_root=str(out), group_by_category=True)
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    assert (out / "科幻" / "一乃あおい" / "ABC-1").is_dir()


def test_apply_session_output_flat_keeps_actress_layer(tmp_path):
    state, cfg = _make_actress_env(tmp_path)
    out = cfg.path.parent / "本次输出"
    state.start_scan()
    wait_job(state)
    out.mkdir(parents=True, exist_ok=True)
    state.start_apply(["一乃あおい/ABC-1"], {"jellyfin_running"}, {},
                      output_root=str(out), group_by_category=False)
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    assert (out / "一乃あおい" / "ABC-1").is_dir()
    assert (out / "科幻").exists() is False


def test_undo_drilled_unit_preserves_library_siblings(tmp_path):
    """undo 只回滚本次放入的影片目录，绝不动女优目录里的原有兄弟影片。"""
    state, cfg = _make_actress_env(tmp_path)
    scifi = cfg.libraries["科幻"].path
    make_movie(scifi / "一乃あおい", "KEEP-1", genres=("科幻",), tmdb="77")
    state.start_scan()
    wait_job(state)
    state.start_apply(["一乃あおい/ABC-1"], {"jellyfin_running"}, {})
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    assert (scifi / "一乃あおい" / "KEEP-1").is_dir()
    sess = list_sessions(state.runtime_dir() / "journals")[0]["file"]
    state.start_undo(sess)
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    assert st["result"]["restored"] == 1
    assert (cfg.source_root / "一乃あおい" / "ABC-1").is_dir()
    assert (scifi / "一乃あおい" / "KEEP-1").is_dir()


def test_preflight_long_path_warns_on_three_layer_dst(tmp_path):
    """三层路径超 240 字符 → long_paths warn（维持 warn 不升级 block）。"""
    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    make_movie(cfg.source_root / ("あ" * 80), "長" * 120,
               genres=("科幻",), plot="太空宇宙", tmdb="41")
    units, notes = scanner.scan_source_root(cfg)
    plan = build_plan(cfg, units, notes)
    items = preflight.run_preflight(cfg, plan)
    lp = [i for i in items if i["code"] == "long_paths"]
    assert lp and lp[0]["level"] == "warn"
    assert any(("長" * 120) in d for d in lp[0]["detail"])


def test_jobs_dst_combination_uses_planner_single_point():
    """组合单点架构钉：jobs 的 dst 改写一律经 planner.unit_dst_dir。"""
    src = Path(jobs_mod.__file__).read_text(encoding="utf-8")
    assert src.count("unit_dst_dir(") >= 2   # 人工改判 + 会话输出两分支
    assert "session_dst_root(" in src
    assert '/ u["dst_name"]' not in src


def test_preflight_covers_batch_units(tmp_path):
    """复合单元（ST_BATCH）也纳入长路径体检：detail 引用复合 id。"""
    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    name = "混" * 165
    make_movie(cfg.source_root, name, title=name, genres=("西部",),
               plot="乡村爱情", tmdb="55", extra_files=[("另一部.mkv", b"V" * 1024)])
    units, notes = scanner.scan_source_root(cfg)
    plan = build_plan(cfg, units, notes)
    u = plan["units"][0]
    assert u["composite"] is True and u["status"] == "batch_target"
    assert len(u["dst_dir"]) > 240
    items = preflight.run_preflight(cfg, plan)
    lp = [i for i in items if i["code"] == "long_paths"]
    assert lp and lp[0]["level"] == "warn"
    assert any(name in d for d in lp[0]["detail"])

"""计划构建 / 冲突三分 / 漂移检测测试（评议条件 C3 / C7）。"""
import os

from app.core import scanner
from app.core.config import load_config, save_config_dict, describe
from app.core.planner import (build_plan, check_plan_freshness, load_plan,
                              mark_applied, save_plan)
from conftest import build_env, make_movie


def scan_and_plan(cfg):
    units, notes = scanner.scan_source_root(cfg)
    return build_plan(cfg, units, notes)


def by_id(plan):
    return {u["id"]: u for u in plan["units"]}


def test_plan_ready_and_decision(tmp_path):
    cfg = load_config(build_env(tmp_path))
    make_movie(cfg.source_root, "太空大战 (2021)", title="太空大战",
               genres=("科幻",), plot="太空宇宙飞船", tmdb="11")
    plan = scan_and_plan(cfg)
    assert plan["stats"]["ready"] == 1
    u = by_id(plan)["太空大战 (2021)"]
    assert u["status"] == "ready" and u["level"] == "rule"
    assert u["target_lib"] == "科幻" and u["default_selected"] is True
    assert u["dst_dir"].startswith(str(cfg.libraries["科幻"].path))


def test_fallback_decision(tmp_path):
    cfg = load_config(build_env(tmp_path))
    make_movie(cfg.source_root, "Unknown Film", title="Unknown",
               genres=("西部",), plot="乡村爱情", tmdb="13")
    plan = scan_and_plan(cfg)
    u = by_id(plan)["Unknown Film"]
    assert u["status"] == "ready" and u["level"] == "fallback"
    assert u["target_root"] == str(cfg.fallback_path)


def test_conflict_three_ways(tmp_path):
    cfg = load_config(build_env(tmp_path))
    src = cfg.source_root
    lib = cfg.libraries["科幻"].path
    make_movie(src, "Same Name", title="Same", genres=("科幻",), tmdb="1")
    make_movie(lib, "Same Name", title="Same", genres=("动作",), tmdb="2")
    make_movie(src, "Placed Film", title="Placed", genres=("科幻",), tmdb="3")
    make_movie(lib, "Placed Film", title="Placed", genres=("科幻",), tmdb="3")
    make_movie(src, "Broken Film", title="Broken", genres=("科幻",), tmdb="4")
    leftover = lib / "Broken Film"
    leftover.mkdir()
    (leftover / ".incomplete-20260101T000000").write_text("x", encoding="utf-8")
    plan = scan_and_plan(cfg)
    st = {u["id"]: u["status"] for u in plan["units"]}
    assert st["Same Name"] == "conflict_name"
    assert st["Placed Film"] == "already_placed"
    assert "冗余副本" in " ".join(by_id(plan)["Placed Film"]["notes"])
    assert st["Broken Film"] == "incomplete_leftover"
    assert plan["stats"]["ready"] == 0


def test_multi_version_grouped(tmp_path):
    cfg = load_config(build_env(tmp_path))
    make_movie(cfg.source_root, "Multi Film - 1080p", title="Multi",
               genres=("科幻",), tmdb="7")
    make_movie(cfg.source_root, "Multi Film - 2160p", title="Multi",
               genres=("科幻",), tmdb="7")
    plan = scan_and_plan(cfg)
    assert {u["status"] for u in plan["units"]} == {"multi_version"}
    assert all(not u["default_selected"] for u in plan["units"])


def test_freshness_drift_and_config_change(tmp_path):
    cfg = load_config(build_env(tmp_path))
    d = make_movie(cfg.source_root, "Drift Film", title="Drift",
                   genres=("科幻",), tmdb="9")
    plan = scan_and_plan(cfg)
    save_plan(cfg.runtime_dir, plan)
    assert check_plan_freshness(cfg, plan) == []
    for f in d.iterdir():
        os.utime(f, ns=(10 ** 18, 10 ** 18))
    assert any("已变化" in p for p in check_plan_freshness(cfg, plan))
    d2 = describe(cfg)
    d2["strategy"] = "genre_only"
    cfg2 = save_config_dict(cfg.path, d2)
    assert any("配置已变更" in p for p in check_plan_freshness(cfg2, plan))


def test_mark_applied_roundtrip(tmp_path):
    cfg = load_config(build_env(tmp_path))
    make_movie(cfg.source_root, "Mark Film", title="Mark", genres=("科幻",), tmdb="12")
    plan = scan_and_plan(cfg)
    save_plan(cfg.runtime_dir, plan)
    mark_applied(cfg.runtime_dir, ["Mark Film"])
    assert load_plan(cfg.runtime_dir)["units"][0]["status"] == "applied"

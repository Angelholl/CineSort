"""计划构建 / 冲突三分 / 漂移检测测试（评议条件 C3 / C7）。"""
import os

from conftest import build_env, make_movie

from app.core import scanner
from app.core.config import describe, load_config, save_config_dict
from app.core.planner import (
    build_plan,
    check_plan_freshness,
    load_plan,
    mark_applied,
    save_plan,
)


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


def test_plan_evidence_notes_recovery(tmp_path):
    cfg = load_config(build_env(tmp_path))
    d = make_movie(cfg.source_root, "Recovery Film", title="Recovery",
                   genres=("科幻",), tmdb="21")
    (d / "movie.nfo").write_text(
        '<movie><title>Recovery</title><genre>科幻</genre><plot>太空</plot>'
        '<uniqueid type="tmdb">21</uniqueid><7mmtvid>x</7mmtvid></movie>',
        encoding="utf-8")
    plan = scan_and_plan(cfg)
    u = by_id(plan)["Recovery Film"]
    assert any(e.startswith("NFO 已容错恢复") for e in u["evidence"])

def test_plan_weak_rule_not_selected(tmp_path):
    """弱标签唯一命中 → rule/low：计入 ready 的 rule 而非 fallback，但默认不勾选。"""
    cfg = load_config(build_env(tmp_path, overrides={
        "weak_genre_aliases": {"护士": "动作"}}))
    make_movie(cfg.source_root, "Weak Film", title="Weak Film",
               genres=("护士",), tmdb="88")
    plan = scan_and_plan(cfg)
    u = by_id(plan)["Weak Film"]
    assert u["status"] == "ready"
    assert u["level"] == "rule" and u["confidence"] == "low"
    assert u["target_lib"] == "动作"
    assert u["target_root"] == str(cfg.libraries["动作"].path)
    assert u["default_selected"] is False
    assert plan["stats"]["ready"] == 1
    assert plan["stats"]["ready_levels"] == {"rule": 1}


# ---------------- C9 整目录批次门禁（card-20261110-batch-gate） ----------------

def _make_composite(cfg, name, *, genres=("西部",), plot="乡村爱情", tmdb="33"):
    """造一个复合目录单元（两个不同影片 base + 一张 NFO）。"""
    return make_movie(cfg.source_root, name, title=name,
                      genres=genres, plot=plot, tmdb=tmdb,
                      extra_files=[("另一部影片.mkv", b"V" * 1024)])


def test_plan_composite_status_and_level(tmp_path):
    from app.core.planner import ST_BATCH
    cfg = load_config(build_env(tmp_path))
    _make_composite(cfg, "Comp Dir")
    plan = scan_and_plan(cfg)
    assert plan["stats"]["total"] == 1
    u = by_id(plan)["Comp Dir"]
    assert u["status"] == ST_BATCH
    assert u["level"] == "composite"
    assert u["default_selected"] is False
    assert u["target_lib"] == "兜底库"   # 占位：分类结果保留，需人工改判
    assert u["composite"] is True


def test_plan_composite_out_of_fallback_ratio(tmp_path):
    cfg = load_config(build_env(tmp_path))
    make_movie(cfg.source_root, "Unknown Film", title="Unknown",
               genres=("西部",), plot="乡村爱情", tmdb="13")
    make_movie(cfg.source_root, "Rule Film", title="Rule",
               genres=("科幻",), tmdb="14")
    _make_composite(cfg, "Comp Dir")
    plan = scan_and_plan(cfg)
    assert plan["stats"]["total"] == 3
    assert plan["stats"]["composite"] == 1
    assert plan["stats"]["fallback_ratio"] == 0.5   # 分母 2（3-1），而非 3


def test_plan_stats_composite_count(tmp_path):
    from app.core.planner import ST_BATCH
    cfg = load_config(build_env(tmp_path))
    _make_composite(cfg, "Comp Dir")
    make_movie(cfg.source_root, "Rule Film", title="Rule",
               genres=("科幻",), tmdb="14")
    plan = scan_and_plan(cfg)
    assert plan["stats"]["composite"] == 1
    assert plan["stats"]["by_status"][ST_BATCH] == 1
    assert plan["stats"]["by_status"]["ready"] == 1


def test_refresh_stats_keeps_denominator(tmp_path):
    cfg = load_config(build_env(tmp_path))
    make_movie(cfg.source_root, "Unknown Film", title="Unknown",
               genres=("西部",), plot="乡村爱情", tmdb="13")
    make_movie(cfg.source_root, "Rule Film", title="Rule",
               genres=("科幻",), tmdb="14")
    _make_composite(cfg, "Comp Dir")
    plan = scan_and_plan(cfg)
    assert plan["stats"]["fallback_ratio"] == 0.5
    save_plan(cfg.runtime_dir, plan)
    mark_applied(cfg.runtime_dir, ["Comp Dir"])
    plan2 = load_plan(cfg.runtime_dir)
    assert plan2["stats"]["fallback_ratio"] == 0.5   # 分母仍排除 composite
    assert plan2["stats"]["composite"] == 1


def test_mark_undone_restores_batch_status(tmp_path):
    from app.core.planner import ST_BATCH, mark_undone
    cfg = load_config(build_env(tmp_path))
    _make_composite(cfg, "Comp Dir")
    plan = scan_and_plan(cfg)
    save_plan(cfg.runtime_dir, plan)
    mark_applied(cfg.runtime_dir, ["Comp Dir"])
    assert load_plan(cfg.runtime_dir)["units"][0]["status"] == "applied"
    mark_undone(cfg.runtime_dir, ["Comp Dir"])
    u = load_plan(cfg.runtime_dir)["units"][0]
    assert u["status"] == ST_BATCH   # 不得恢复成 READY


def test_composite_conflict_detection(tmp_path):
    from app.core.planner import ST_CONFLICT
    cfg = load_config(build_env(tmp_path))
    _make_composite(cfg, "Comp Dir", tmdb="33")
    make_movie(cfg.fallback_path, "Comp Dir", title="Comp Dir",
               genres=("动作",), tmdb="99")
    plan = scan_and_plan(cfg)
    u = by_id(plan)["Comp Dir"]
    assert u["status"] == ST_CONFLICT   # 硬状态优先于 ST_BATCH

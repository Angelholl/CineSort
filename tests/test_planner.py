"""计划构建 / 冲突三分 / 漂移检测测试（评议条件 C3 / C7）。"""
import json
import os
from pathlib import Path

from conftest import build_env, make_movie, seed_learned

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


def test_plan_learned_level_never_default_selected(tmp_path):
    """A-2：票数退出择优后，自学习级单元即便票数达标也永不默认勾选。"""
    cfg = load_config(build_env(tmp_path))
    make_movie(cfg.source_root, "播剧 (2021)", title="播剧", genres=("播",),
               plot="剧情简介", tmdb="31")
    seed_learned(cfg.runtime_dir, {"播": {"科幻": {"votes": 2, "manual": 2}}})  # 2 票人工票
    plan = scan_and_plan(cfg)
    u = by_id(plan)["播剧 (2021)"]
    assert u["level"] == "learned" and u["status"] == "ready"
    assert u["default_selected"] is False


def test_learning_disabled_gates_suggestions(tmp_path):
    """enabled=False 即建议门控关闭：build_plan 不咨询 learned。"""
    cfg = load_config(build_env(tmp_path, overrides={
        "learning": {"enabled": False, "min_votes": 2}}))
    make_movie(cfg.source_root, "播剧 (2021)", title="播剧", genres=("播",),
               plot="剧情简介", tmdb="31")
    seed_learned(cfg.runtime_dir, {"播": {"科幻": {"votes": 2, "manual": 2}}})
    plan = scan_and_plan(cfg)
    u = by_id(plan)["播剧 (2021)"]
    assert u["level"] != "learned"
    assert not any("自学习" in e for e in u["evidence"])


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


# ---------------- 三层布局：unit_dst_dir 组合单点与冲突语义（D-20261110-01，Task-02） ----------------

def test_unit_dst_dir_combination_rule():
    """组合单点：有女优段三层、无女优段扁平、会话根经 session_dst_root 后仍三层。"""
    from app.core.planner import session_dst_root, unit_dst_dir
    assert unit_dst_dir(r"E:\lib", "女优", "MOVIE") == Path(r"E:\lib\女优\MOVIE")
    assert unit_dst_dir(r"E:\lib", None, "MOVIE") == Path(r"E:\lib\MOVIE")
    root = session_dst_root("E:/out", "科幻", True)
    assert unit_dst_dir(root, "女优", "M") == Path("E:/out/科幻/女优/M")


def test_plan_drilled_unit_dst_three_layers(tmp_path):
    cfg = load_config(build_env(tmp_path))
    scifi = cfg.libraries["科幻"].path
    make_movie(cfg.source_root / "一乃あおい", "ABC-1", genres=("科幻",),
               plot="太空宇宙", tmdb="1")
    plan = scan_and_plan(cfg)
    u = by_id(plan)["一乃あおい/ABC-1"]
    assert u["actress"] == "一乃あおい"
    assert u["dst_dir"] == str(scifi / "一乃あおい" / "ABC-1")
    assert u["status"] == "ready" and u["level"] == "rule"
    assert u["default_selected"] is True


def test_plan_actress_dir_exists_merges_not_conflict(tmp_path):
    """目标女优目录已存在（含其他影片）→ 合并进该女优目录，不判 conflict_name。"""
    cfg = load_config(build_env(tmp_path))
    scifi = cfg.libraries["科幻"].path
    make_movie(scifi / "一乃あおい", "EXIST-1", genres=("科幻",), tmdb="9")
    make_movie(cfg.source_root / "一乃あおい", "ABC-2", genres=("科幻",),
               plot="太空宇宙", tmdb="1")
    plan = scan_and_plan(cfg)
    u = by_id(plan)["一乃あおい/ABC-2"]
    assert u["status"] == "ready"          # owner 拍板 2：女优层撞名=合并
    assert u["dst_dir"] == str(scifi / "一乃あおい" / "ABC-2")


def test_plan_same_movie_three_layers_already_placed(tmp_path):
    cfg = load_config(build_env(tmp_path))
    scifi = cfg.libraries["科幻"].path
    make_movie(scifi / "一乃あおい", "ABC-1", genres=("科幻",), tmdb="1")
    make_movie(cfg.source_root / "一乃あおい", "ABC-1", genres=("科幻",),
               plot="太空宇宙", tmdb="1")
    plan = scan_and_plan(cfg)
    u = by_id(plan)["一乃あおい/ABC-1"]
    assert u["status"] == "already_placed"
    assert "冗余副本" in " ".join(u["notes"])


def test_plan_same_name_movie_three_layers_conflict(tmp_path):
    """同名异片在影片层冲突（既有语义），不因女优层存在而误判。"""
    cfg = load_config(build_env(tmp_path))
    scifi = cfg.libraries["科幻"].path
    make_movie(scifi / "一乃あおい", "ABC-1", genres=("科幻",), tmdb="2")
    make_movie(cfg.source_root / "一乃あおい", "ABC-1", genres=("科幻",),
               plot="太空宇宙", tmdb="1")
    plan = scan_and_plan(cfg)
    assert by_id(plan)["一乃あおい/ABC-1"]["status"] == "conflict_name"


def test_plan_movie_dir_name_equals_actress_name(tmp_path):
    """影片目录名==女优名：三层组合天然区分，不与女优层撞名混淆。"""
    cfg = load_config(build_env(tmp_path))
    scifi = cfg.libraries["科幻"].path
    make_movie(scifi / "一乃あおい", "EXIST", genres=("科幻",), tmdb="9")
    make_movie(cfg.source_root / "一乃あおい", "一乃あおい", genres=("科幻",),
               plot="太空宇宙", tmdb="1")
    plan = scan_and_plan(cfg)
    u = by_id(plan)["一乃あおい/一乃あおい"]
    assert u["status"] == "ready"
    assert u["dst_dir"] == str(scifi / "一乃あおい" / "一乃あおい")


def test_plan_actressless_unit_flat_dst_regression(tmp_path):
    """无女优段单元（顶层单片目录）→ 扁平 dst，既有语义回归钉。"""
    cfg = load_config(build_env(tmp_path))
    scifi = cfg.libraries["科幻"].path
    make_movie(cfg.source_root, "Flat Film", genres=("科幻",), tmdb="5")
    plan = scan_and_plan(cfg)
    u = by_id(plan)["Flat Film"]
    assert u["actress"] is None
    assert u["dst_dir"] == str(scifi / "Flat Film")


def test_plan_incomplete_marker_at_movie_level(tmp_path):
    """半成品检查点随 dst 升到影片层：库内影片目录含 .incomplete 标记 → ST_INCOMPLETE。"""
    cfg = load_config(build_env(tmp_path))
    scifi = cfg.libraries["科幻"].path
    leftover = scifi / "一乃あおい" / "ABC-1"
    leftover.mkdir(parents=True)
    (leftover / ".incomplete-20261110").write_text("x", encoding="utf-8")
    make_movie(cfg.source_root / "一乃あおい", "ABC-1", genres=("科幻",),
               plot="太空宇宙", tmdb="1")
    plan = scan_and_plan(cfg)
    assert by_id(plan)["一乃あおい/ABC-1"]["status"] == "incomplete_leftover"


# ---------------- 放行 ST_BATCH：freshness 覆盖复合单元（owner 放行，Task-04） ----------------

def test_freshness_covers_batch_units(tmp_path):
    """复合单元（ST_BATCH）也纳入漂移校验：改源后 check_plan_freshness 报已变化。"""
    cfg = load_config(build_env(tmp_path))
    d = _make_composite(cfg, "Comp Dir")
    plan = scan_and_plan(cfg)
    assert by_id(plan)["Comp Dir"]["status"] == "batch_target"
    assert check_plan_freshness(cfg, plan) == []
    for f in d.iterdir():
        os.utime(f, ns=(10 ** 18, 10 ** 18))
    problems = check_plan_freshness(cfg, plan)
    assert any("Comp Dir" in p and "已变化" in p for p in problems)


# ---------------- 卡 Task-05：smart_weighted 默认勾选结构性红线 ----------------
def test_smart_weighted_default_not_selected(tmp_path):
    """两条路径（加权词胜出 / 低置信回退）build_plan 后都不得默认勾选。"""
    cfg = load_config(build_env(tmp_path, strategy="smart_weighted"))
    make_movie(cfg.source_root, "加权胜出 (2021)", title="加权胜出",
               genres=("动作", "科幻"), plot="一场星际远征", tmdb="41")
    make_movie(cfg.source_root, "回退低置信 (2021)", title="回退低置信",
               genres=("动作", "科幻"), plot="一家人在海边度假", tmdb="42")
    plan = scan_and_plan(cfg)
    p = by_id(plan)
    assert p["加权胜出 (2021)"]["level"] == "plot"
    assert p["回退低置信 (2021)"]["level"] == "rule"
    assert p["回退低置信 (2021)"]["confidence"] == "low"
    assert p["加权胜出 (2021)"]["default_selected"] is False
    assert p["回退低置信 (2021)"]["default_selected"] is False


# ---------------- 卡 Task-09：B(ii) 跨扫描记忆注记（不改判定、不默认勾选） ----------------
def _seed_memory_session(runtime_dir, *, title, year, lib,
                         sid="20260101T000000-0001",
                         ts="2026-01-01T00:00:00+08:00", unit_id="U"):
    journals = Path(runtime_dir) / "journals"
    journals.mkdir(parents=True, exist_ok=True)
    lines = [
        {"type": "header", "kind": "apply", "sid": sid, "ts": ts, "meta": {}},
        {"type": "done", "ts": ts, "unit_id": unit_id, "title": title, "year": year,
         "target_lib": lib, "manual": True, "orig_lib": "科幻", "provider": "tmdb:21"},
    ]
    p = journals / f"apply-{sid}.jsonl"
    p.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in lines) + "\n",
        encoding="utf-8")
    return p


def test_plan_memory_note_no_side_effects(tmp_path):
    """命中单元只加注记 + memory_lib；target_lib/default_selected 均不变。"""
    cfg = load_config(build_env(tmp_path))
    make_movie(cfg.source_root, "Memory Hit (2020)", title="Memory Hit",
               genres=("科幻",), plot="太空宇宙飞船", tmdb="31")
    make_movie(cfg.source_root, "No Memory (2020)", title="No Memory",
               genres=("科幻",), plot="太空宇宙飞船", tmdb="32")
    baseline = by_id(scan_and_plan(cfg))                 # 注记前基线

    _seed_memory_session(cfg.runtime_dir, title="Memory Hit", year=2020, lib="动作")
    plan = scan_and_plan(cfg)
    hit, miss = by_id(plan)["Memory Hit (2020)"], by_id(plan)["No Memory (2020)"]

    assert any("跨扫描记忆" in n for n in hit["notes"])
    assert hit["memory_lib"] == "动作"
    assert hit["target_lib"] == baseline["Memory Hit (2020)"]["target_lib"]
    assert hit["default_selected"] == baseline["Memory Hit (2020)"]["default_selected"]
    assert "memory_lib" not in miss
    assert not any("跨扫描记忆" in n for n in miss["notes"])


def test_plan_memory_key_normalization(tmp_path):
    """会话全角片名与新单元半角片名同年份 → normalize_key 归一后命中。"""
    cfg = load_config(build_env(tmp_path))
    make_movie(cfg.source_root, "Test Movie (2020)", title="Test Movie",
               genres=("科幻",), plot="太空宇宙飞船", tmdb="33")
    _seed_memory_session(cfg.runtime_dir, title="Ｔｅｓｔ Ｍｏｖｉｅ", year=2020, lib="动作")

    plan = scan_and_plan(cfg)
    u = by_id(plan)["Test Movie (2020)"]
    assert any("跨扫描记忆" in n for n in u["notes"])
    assert u["memory_lib"] == "动作"

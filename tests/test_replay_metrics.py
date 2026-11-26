"""离线重放四指标量尺测试（D-20261125-05 Task-01）。"""
import importlib.util
import json
import sys
from pathlib import Path

from conftest import build_env, make_movie, seed_learned

from app.core.config import load_config

ROOT = Path(__file__).resolve().parents[1]


def _replay_module():
    """importlib 挂载范式同 test_measure_no_nfo.py:8-14；延后到用例内以逐项报红。"""
    spec = importlib.util.spec_from_file_location(
        "replay_metrics", ROOT / "tools" / "replay_metrics.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["replay_metrics"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_replay_writes_nothing(tmp_path):
    mod = _replay_module()
    cfg_path = build_env(tmp_path)
    make_movie(tmp_path / "src", "a", genres=("动作",))
    make_movie(tmp_path / "src", "b", genres=("科幻",))
    cfg = load_config(cfg_path)
    runtime = cfg.runtime_dir
    names = ("plan.json", "learned.json")

    def snap():
        return {n: (runtime / n).read_bytes() if (runtime / n).is_file() else None
                for n in names}

    before = snap()
    mod.replay_metrics(cfg)
    assert snap() == before


def test_replay_auto_effective_zero_after_a2(tmp_path):
    """A-2：票数不再触发自动生效，自学习单元默认不勾选。"""
    mod = _replay_module()
    cfg_path = build_env(tmp_path)
    make_movie(tmp_path / "src", "opera", genres=("戏曲",))
    cfg = load_config(cfg_path)
    seed_learned(cfg.runtime_dir, {"戏曲": {"科幻": {"votes": 2, "manual": 2}}})

    result = mod.replay_metrics(cfg)
    plan = mod.build_replay_plan(cfg)
    learned_units = [u for u in plan["units"] if u["level"] == "learned"]
    assert len(learned_units) == 1
    assert all(not u["default_selected"] for u in learned_units)
    assert result["auto_effective_units"] == 0


def test_replay_winner_basis_no_votes_after_a2(tmp_path):
    """A-2：票数退出择优后，重放量尺不再出现 votes 胜出依据。"""
    mod = _replay_module()
    cfg_path = build_env(tmp_path, overrides={
        "genre_priority": [],
        "genre_aliases": {"喜剧": "科幻"},
    })
    make_movie(tmp_path / "src", "comedy", genres=("喜剧", "动作"))
    cfg = load_config(cfg_path)
    seed_learned(cfg.runtime_dir, {"喜剧": {"动作": {"votes": 4, "manual": 0}}})

    result = mod.replay_metrics(cfg)
    assert result["winner_basis"]["votes"] == 0
    assert result["winner_basis"]["decl_order"] >= 1


def test_replay_default_selected_count(tmp_path):
    mod = _replay_module()
    cfg_path = build_env(tmp_path)
    make_movie(tmp_path / "src", "a", genres=("动作",))
    make_movie(tmp_path / "src", "b", genres=("科幻",))
    cfg = load_config(cfg_path)

    result = mod.replay_metrics(cfg)
    plan = mod.build_replay_plan(cfg)
    assert result["default_selected"] == sum(
        1 for u in plan["units"] if u["default_selected"])


def test_replay_closure_flags_manual_leak(tmp_path):
    mod = _replay_module()
    cfg_path = build_env(tmp_path)
    make_movie(tmp_path / "src", "a", genres=("动作",))
    make_movie(tmp_path / "src", "b", genres=("科幻",))
    cfg = load_config(cfg_path)
    plan = mod.build_replay_plan(cfg)
    seed_learned(cfg.runtime_dir, {"动作": {"动作": {"votes": 1, "manual": 0}},
                                   "戏曲": {"科幻": {"votes": 1, "manual": 0}}})  # 历史票目

    unit = plan["units"][0]
    sid = "20261126T000000-0001"
    jdir = cfg.runtime_dir / "journals"
    jdir.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "header", "kind": "apply", "sid": sid,
         "ts": "2026-11-26T00:00:00+08:00", "meta": {"plan_id": plan["plan_id"]}},
        {"type": "done", "ts": "2026-11-26T00:01:00+08:00", "unit_id": unit["id"],
         "src_dir": unit["src"], "target_lib": unit["target_lib"],
         "title": unit["title"], "manual": True,
         "orig_lib": unit["target_lib"], "provider": "tmdb:1"},
    ]
    (jdir / f"apply-{sid}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")

    result = mod.replay_metrics(cfg)
    assert result["vote_closure_inconsistencies"] == 1
    detail = mod._closure(cfg, plan)
    assert detail["legacy_pairs"] == [("戏曲", "科幻")]


def test_replay_closure_zero_after_a1(tmp_path):
    """A-1：post-留痕确认+改判会话触及对票数恒 0 → 不一致对 == 0。"""
    mod = _replay_module()
    cfg_path = build_env(tmp_path)
    make_movie(tmp_path / "src", "a", genres=("动作",))
    make_movie(tmp_path / "src", "b", genres=("科幻",))
    cfg = load_config(cfg_path)
    plan = mod.build_replay_plan(cfg)
    seed_learned(cfg.runtime_dir, {"动作": {"动作": {"votes": 0}},
                                   "科幻": {"科幻": {"votes": 0}}})
    u_manual = next(u for u in plan["units"] if "动作" in (u.get("genres") or []))
    u_confirm = next(u for u in plan["units"] if "科幻" in (u.get("genres") or []))
    sid = "20261126T020000-0001"
    jdir = cfg.runtime_dir / "journals"
    jdir.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "header", "kind": "apply", "sid": sid,
         "ts": "2026-11-26T02:00:00+08:00", "meta": {"plan_id": plan["plan_id"]}},
        {"type": "done", "ts": "2026-11-26T02:01:00+08:00", "unit_id": u_manual["id"],
         "src_dir": u_manual["src"], "target_lib": u_manual["target_lib"],
         "title": u_manual["title"], "manual": True},
        {"type": "done", "ts": "2026-11-26T02:02:00+08:00", "unit_id": u_confirm["id"],
         "src_dir": u_confirm["src"], "target_lib": u_confirm["target_lib"],
         "title": u_confirm["title"], "manual": False},
    ]
    (jdir / f"apply-{sid}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")

    detail = mod._closure(cfg, plan)
    assert detail["expected"] and set(detail["expected"].values()) == {0}
    assert detail["inconsistencies"] == 0
    assert mod.replay_metrics(cfg, plan)["vote_closure_inconsistencies"] == 0


def test_replay_strategy_override(tmp_path, capsys, monkeypatch):
    mod = _replay_module()
    cfg_path = build_env(tmp_path)
    make_movie(tmp_path / "src", "a", genres=("动作",))
    make_movie(tmp_path / "src", "b", genres=("科幻",))
    before = cfg_path.read_bytes()

    seen = {}
    real_build = mod.build_replay_plan

    def spy(cfg, strategy=None):
        seen["strategy"] = strategy
        return real_build(cfg, strategy)

    monkeypatch.setattr(mod, "build_replay_plan", spy)
    assert mod.main([str(cfg_path), "--strategy", "genre_only", "--json"]) == 0
    assert seen["strategy"] == "genre_only"
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"auto_effective_units", "winner_basis", "default_selected",
                        "vote_closure_inconsistencies", "top_target_share"}

    cfg = load_config(cfg_path)
    plan = mod.build_replay_plan(cfg, strategy="genre_only")
    assert plan["strategy"] == "genre_only"
    assert {u["level"] for u in plan["units"]} <= {"rule", "fallback"}
    assert cfg_path.read_bytes() == before

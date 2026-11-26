"""事务日志测试（评议条件 C6：fsync 落盘 / 容忍末尾半行 / 会话隔离）。"""
import json
import time

from conftest import build_env, make_movie

from app.core.config import load_config
from app.core.journal import (
    Journal,
    done_entries,
    is_valid_session_name,
    list_sessions,
    read_entries,
    session_summary,
)
from app.state import AppState


def test_roundtrip_and_summary(tmp_path):
    j = Journal(tmp_path, "apply", {"plan_id": "abc"})
    j.intent(unit_id="A", src_dir="x", dst_dir="y")
    j.done(unit_id="A", src_dir="x", dst_dir="y", kind="dir", files={"a.mkv": 1})
    j.aborted(unit_id="B", reason="目标已存在")
    j.close()
    entries = read_entries(j.path)
    assert [e["type"] for e in entries] == ["header", "intent", "done", "aborted"]
    s = session_summary(j.path)
    assert s["done"] == 1 and s["aborted"] == 1 and s["intents"] == 1
    assert s["kind"] == "apply" and s["plan_id"] == "abc"


def test_corrupt_last_line_skipped(tmp_path):
    j = Journal(tmp_path, "apply", {})
    j.done(unit_id="A", src_dir="x", dst_dir="y", kind="dir")
    j.close()
    with open(j.path, "a", encoding="utf-8") as fh:
        fh.write('{"type": "done", "trunc')
    entries = read_entries(j.path)
    assert entries[-1]["unit_id"] == "A"


def test_list_sessions_sorted_desc(tmp_path):
    a = Journal(tmp_path, "apply", {})
    a.close()
    time.sleep(1.1)
    b = Journal(tmp_path, "apply", {})
    b.close()
    names = [s["file"] for s in list_sessions(tmp_path)]
    assert names[0] == b.path.name and names[1] == a.path.name


def test_done_entries_filter(tmp_path):
    j = Journal(tmp_path, "apply", {})
    j.done(unit_id="A", src_dir="x", dst_dir="y", kind="dir", files={"a": 1})
    j.aborted(unit_id="B", reason="x")
    j.close()
    dones = done_entries(j.path)
    assert len(dones) == 1 and dones[0]["unit_id"] == "A"


def test_session_name_guard():
    assert is_valid_session_name("apply-20261031T101112-0001.jsonl")
    assert is_valid_session_name("undo-20261031T101112-0042.jsonl")
    assert not is_valid_session_name("..\\evil.jsonl")
    assert not is_valid_session_name("apply-x.jsonl")
    assert not is_valid_session_name("apply-20261031T101112-0001.txt")


def test_list_sessions_sorted_by_time_across_kinds(tmp_path):
    """执行页承诺「按时间倒序」：较早的 undo 会话不得因文件名前缀
    （undo- > apply-）恒排在较新的 apply 会话之前。"""
    u = Journal(tmp_path, "undo", {})
    u.close()
    time.sleep(1.1)
    a = Journal(tmp_path, "apply", {})
    a.close()
    names = [s["file"] for s in list_sessions(tmp_path)]
    assert names[0] == a.path.name and names[1] == u.path.name


def _wait_job(state, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = state.jobs.job
        if job and job.status != "running":
            return job.snapshot()
        time.sleep(0.05)
    raise AssertionError("任务超时未结束")


def _apply_one(tmp_path, *, title, year, genres, tmdb, override=None):
    """扫描单个单元后执行，返回 (state, unit, apply 日志路径)。"""
    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    make_movie(cfg.source_root, f"{title} ({year})", title=title, genres=genres,
               plot="太空宇宙飞船大战", tmdb=tmdb)
    state = AppState(cfg_path)
    state.start_scan()
    st = _wait_job(state)
    assert st["status"] == "done", st["log"]
    unit = next(u for u in state.plan()["units"] if u["title"] == title)
    overrides = {unit["id"]: override} if override else {}
    state.start_apply([unit["id"]], {"jellyfin_running", "fallback_ratio"}, overrides)
    st = _wait_job(state)
    assert st["status"] == "done", st["log"]
    log_path = (state.runtime_dir() / "journals"
                / f"apply-{st['result']['session']}.jsonl")
    return state, unit, log_path


def test_done_entry_carries_override_trace(tmp_path):
    """人工改判「科幻」→「动作」：done 须留痕原库、人工标记、来源与片名年份。"""
    _state, unit, log_path = _apply_one(
        tmp_path, title="Space War", year=2021, genres=("科幻",), tmdb="21",
        override="动作")
    d = done_entries(log_path)[0]
    assert d["manual"] is True
    assert d["orig_lib"] == "科幻"
    assert d["target_lib"] == "动作"
    assert d["provider"] == "tmdb:21"
    assert d["title"] == unit["title"]
    assert d["year"] == unit["year"]


def test_done_entry_confirm_trace(tmp_path):
    """无人工改判的确认执行：manual False，orig_lib 与 target_lib 一致。"""
    _state, _unit, log_path = _apply_one(
        tmp_path, title="Gun Fight", year=2022, genres=("动作",), tmdb="22")
    d = done_entries(log_path)[0]
    assert d["manual"] is False
    assert d["orig_lib"] == d["target_lib"] == "动作"


def test_old_journal_still_readable(tmp_path):
    """留痕上线前的旧格式 jsonl（无五字段）仍可读，且能与新留痕记录共存。"""
    journals = tmp_path / "runtime" / "journals"
    journals.mkdir(parents=True, exist_ok=True)
    old = journals / "apply-20261125T000000-0001.jsonl"
    old.write_text(
        '{"type":"header","kind":"apply","sid":"s","ts":"2026-01-01T00:00:00+08:00","meta":{}}\n'
        '{"type":"done","ts":"2026-01-01T00:00:01+08:00","unit_id":"OLD",'
        '"src_dir":"x","dst_dir":"y","kind":"dir","target_lib":"科幻"}\n',
        encoding="utf-8")
    assert [e["type"] for e in read_entries(old)] == ["header", "done"]
    assert done_entries(old)[0]["unit_id"] == "OLD"
    assert any(s["file"] == old.name for s in list_sessions(journals))

    _state, _unit, log_path = _apply_one(
        tmp_path, title="Gun Fight", year=2022, genres=("动作",), tmdb="22")
    names = {s["file"] for s in list_sessions(journals)}
    assert old.name in names and log_path.name in names
    assert "manual" not in done_entries(old)[0]      # 旧记录不被回填
    new_done = done_entries(log_path)[0]              # 新记录带五字段
    assert new_done["manual"] is False and new_done["orig_lib"] == new_done["target_lib"]


# ------------------------------------------------------- B(ii) 跨扫描记忆派生
def _write_session(journals, kind, sid, ts, meta, dones):
    """直接落一个 ts 可控的会话 jsonl（不经过真实执行）。"""
    path = journals / f"{kind}-{sid}.jsonl"
    lines = [{"type": "header", "kind": kind, "sid": sid, "ts": ts, "meta": meta}]
    lines.extend(dones)
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in lines) + "\n",
        encoding="utf-8")
    return path


def _done(unit_id, title, year, target_lib, *, manual=True, traced=True):
    e = {"type": "done", "ts": "2026-01-01T00:00:02+08:00", "unit_id": unit_id,
         "src_dir": "x", "dst_dir": "y", "kind": "dir", "target_lib": target_lib}
    if traced:
        e.update(title=title, year=year, manual=manual, provider="tmdb:21",
                 orig_lib="科幻" if manual else target_lib)
    return e


def test_derive_manual_only(tmp_path):
    """manual=False 的 done 记录不派生（确认执行不构成改判记忆）。"""
    from app.core.journal import derive_memory

    journals = tmp_path / "journals"
    journals.mkdir()
    _write_session(journals, "apply", "20260101T000000-0001",
                   "2026-01-01T00:00:00+08:00", {},
                   [_done("A", "Manual Movie", 2021, "动作", manual=False)])
    assert derive_memory(journals) == {}


def test_derive_skips_pre_trace_entries(tmp_path):
    """留痕前旧格式（done 无 title/manual）跳过不炸，且不影响同会话新记录。"""
    from app.core.journal import derive_memory

    journals = tmp_path / "journals"
    journals.mkdir()
    _write_session(journals, "apply", "20260101T000000-0001",
                   "2026-01-01T00:00:00+08:00", {},
                   [_done("OLD", "Old Movie", 2020, "科幻", traced=False),
                    _done("NEW", "New Movie", 2021, "动作")])
    mem = derive_memory(journals)
    assert set(mem) == {("new movie", 2021)}


def test_derive_excludes_undone(tmp_path):
    """风险 #4：apply + 对应 undo 会话 → 被回滚的 unit 不派生。"""
    from app.core.journal import derive_memory

    journals = tmp_path / "journals"
    journals.mkdir()
    apply_name = "apply-20260101T000000-0001.jsonl"
    _write_session(journals, "apply", "20260101T000000-0001",
                   "2026-01-01T00:00:00+08:00", {},
                   [_done("A", "Undone Movie", 2021, "动作")])
    _write_session(journals, "undo", "20260101T000100-0002",
                   "2026-01-01T00:01:00+08:00", {"undoes": apply_name},
                   [{"type": "done", "unit_id": "A", "kind": "dir"}])
    assert derive_memory(journals) == {}


def test_derive_partial_undo(tmp_path):
    """3 单元 apply、undo 回滚其中 1 个 → 其余 2 个仍派生。"""
    from app.core.journal import derive_memory

    journals = tmp_path / "journals"
    journals.mkdir()
    _write_session(journals, "apply", "20260101T000000-0001",
                   "2026-01-01T00:00:00+08:00", {},
                   [_done("A", "Movie One", 2021, "动作"),
                    _done("B", "Movie Two", 2022, "动作"),
                    _done("C", "Movie Three", 2023, "动作")])
    _write_session(journals, "undo", "20260101T000100-0002",
                   "2026-01-01T00:01:00+08:00",
                   {"undoes": "apply-20260101T000000-0001.jsonl"},
                   [{"type": "done", "unit_id": "B", "kind": "dir"}])
    mem = derive_memory(journals)
    assert set(mem) == {("movie one", 2021), ("movie three", 2023)}


def test_derive_last_session_wins(tmp_path):
    """同作品多会话不一致时，header ts 较后的会话胜出。"""
    from app.core.journal import derive_memory

    journals = tmp_path / "journals"
    journals.mkdir()
    _write_session(journals, "apply", "20260101T000000-0001",
                   "2026-01-01T00:00:00+08:00", {},
                   [_done("A", "Last Win", 2021, "科幻")])
    _write_session(journals, "apply", "20260102T000000-0002",
                   "2026-01-02T00:00:00+08:00", {},
                   [_done("B", "Last Win", 2021, "动作")])
    mem = derive_memory(journals)
    assert mem[("last win", 2021)] == {
        "lib": "动作", "sid": "20260102T000000-0002",
        "ts": "2026-01-02T00:00:00+08:00"}

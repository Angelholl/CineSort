"""事务日志测试（评议条件 C6：fsync 落盘 / 容忍末尾半行 / 会话隔离）。"""
import time

from app.core.journal import (Journal, done_entries, is_valid_session_name,
                              list_sessions, read_entries, session_summary)


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

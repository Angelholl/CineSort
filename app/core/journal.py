"""每会话 JSONL 事务日志（评议条件 C6）。

- 每次执行/回滚一个独立文件：journals/<kind>-<sid>.jsonl；
- 每行写后 flush + fsync，进程被杀也不丢记录；
- 三态：intent → done / aborted；undo 只依赖日志里的 src/dst 快照，
  绝不读当前 config 的路径（防止用户改过映射后回滚到错误位置）；
- 解析时容忍末尾半行（进程崩溃瞬间被截断的行）。
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

_SID_RE = re.compile(r"^(apply|undo)-[0-9T-]{15,}-\d{4}\.jsonl$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sid() -> str:
    return time.strftime("%Y%m%dT%H%M%S") + "-" + f"{random.randint(0, 9999):04d}"


class Journal:
    def __init__(self, journals_dir: Path, kind: str, meta: dict | None = None):
        self.dir = Path(journals_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.kind = kind
        self.sid = _sid()
        self.path = self.dir / f"{kind}-{self.sid}.jsonl"
        self._fh = open(self.path, "a", encoding="utf-8")
        self._write({"type": "header", "kind": kind, "sid": self.sid,
                     "meta": meta or {}, "ts": _now_iso()})

    def _write(self, obj: dict) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def intent(self, **kw) -> None:
        self._write({"type": "intent", "ts": _now_iso(), **kw})

    def done(self, **kw) -> None:
        self._write({"type": "done", "ts": _now_iso(), **kw})

    def aborted(self, **kw) -> None:
        self._write({"type": "aborted", "ts": _now_iso(), **kw})

    def event(self, **kw) -> None:
        self._write({"type": "event", "ts": _now_iso(), **kw})

    def close(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass


def is_valid_session_name(name: str) -> bool:
    """仅允许 journals 目录内的会话文件名，杜绝路径穿越。"""
    return bool(_SID_RE.match(name))


def read_entries(path: Path) -> list[dict]:
    """读取会话日志；跳过无法解析的行（含崩溃导致的末尾半行）。"""
    out: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def session_summary(path: Path) -> dict | None:
    try:
        entries = read_entries(path)
    except OSError:
        return None
    headers = [e for e in entries if e.get("type") == "header"]
    if not headers:
        return None
    done_entries = [e for e in entries if e.get("type") == "done"]
    aborted = sum(1 for e in entries if e.get("type") == "aborted")
    intents = sum(1 for e in entries if e.get("type") == "intent")
    meta = headers[0].get("meta") or {}
    return {
        "file": Path(path).name,
        "kind": headers[0].get("kind"),
        "sid": headers[0].get("sid"),
        "ts": headers[0].get("ts"),
        "intents": intents,
        "done": len(done_entries),
        "aborted": aborted,
        "plan_id": meta.get("plan_id"),
        "undoes": meta.get("undoes"),
        "path": str(path),
    }


def list_sessions(journals_dir: Path) -> list[dict]:
    journals_dir = Path(journals_dir)
    if not journals_dir.is_dir():
        return []
    out = []
    for f in journals_dir.glob("*.jsonl"):
        s = session_summary(f)
        if s:
            out.append(s)
    out.sort(key=lambda s: s["file"], reverse=True)
    return out


def done_entries(path: Path) -> list[dict]:
    """可回滚的 done 记录（回滚时逆序执行）。"""
    return [e for e in read_entries(path) if e.get("type") == "done"]

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

from .nfo import normalize_key

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
        # 句柄须持存到 close()（逐事件 fsync），不能走 context manager
        self._fh = open(self.path, "a", encoding="utf-8")  # noqa: SIM115
        self._write({"type": "header", "kind": kind, "sid": self.sid,
                     "meta": meta or {}, "ts": _now_iso()})

    def _write(self, obj: dict) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def intent(self, **kw) -> None:
        self._write({"type": "intent", "ts": _now_iso(), **kw})

    def done(self, **kw) -> None:
        """追加一条 done 留痕（kw 透传，签名不变）。

        Task-04 五字段语义：provider=数据源标识（如 tmdb:21）；manual=本条
        是否经人工改判目标库；orig_lib=改判前的原判定库；title/year=单元
        片名与年份。旧格式记录不含这些字段，天然按「留痕上线前」判别跳过。
        """
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
    # 按会话开始时间倒序（执行页承诺「按时间倒序」）：按文件名排会让
    # undo-* 恒排在 apply-* 之前（kind 前缀先于时间戳参与比较）
    out.sort(key=lambda s: (s["ts"] or "", s["file"]), reverse=True)
    return out


def done_entries(path: Path) -> list[dict]:
    """可回滚的 done 记录（回滚时逆序执行）。"""
    return [e for e in read_entries(path) if e.get("type") == "done"]


def derive_memory(journals_dir: Path) -> dict[tuple[str, int | None], dict]:
    """从会话日志派生「同作品人工改判」记忆（B(ii)，不新建持久层文件）。

    - undo 会话的 done unit_id = 回滚排除集（风险 #4：被回滚的会话不派生）；
    - apply 会话按 header.ts 升序处理，后到会话覆盖先到；
    - 仅带留痕字段（同时含 title 与 manual）且 manual is True 的 done 才派生，
      留痕上线前的旧格式记录天然跳过。
    """
    journals_dir = Path(journals_dir)
    excluded: set[str] = set()
    applies: list[tuple[str, str, str, list[dict]]] = []
    if journals_dir.is_dir():
        for path in journals_dir.glob("*.jsonl"):
            try:
                entries = read_entries(path)
            except OSError:
                continue
            headers = [e for e in entries if e.get("type") == "header"]
            if not headers:
                continue
            header = headers[0]
            dones = [e for e in entries if e.get("type") == "done"]
            if header.get("kind") == "undo":
                excluded.update(str(e["unit_id"]) for e in dones
                                if e.get("unit_id") is not None)
            elif header.get("kind") == "apply":
                applies.append((str(header.get("ts") or ""), Path(path).name,
                                str(header.get("sid") or ""), dones))

    # ts 升序（同 ts 用文件名定序）→ 后到会话覆盖先到会话
    applies.sort(key=lambda item: (item[0], item[1]))
    mem: dict[tuple[str, int | None], dict] = {}
    for ts, _name, sid, dones in applies:
        for e in dones:
            if "title" not in e or "manual" not in e or e["manual"] is not True:
                continue
            if e.get("unit_id") in excluded:
                continue
            key = (normalize_key(e["title"]), e.get("year"))
            mem[key] = {"lib": e.get("target_lib"), "sid": sid, "ts": ts}
    return mem

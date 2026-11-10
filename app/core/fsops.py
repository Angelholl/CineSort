"""文件迁移原语（决策 D-20261031-03/05，评议条件 C2）。

- 同卷：os.rename 原子改名；
- 跨卷：先复制到「目标盘、库根之外」的 staging 目录并写 .incomplete 标记，
  逐文件校验大小后再原子改名进库，最后才删源；中断留下的 staging 残留
  由 preflight 报告并可一键清理，绝不静默当成已完成；
- 绝不使用 shutil.move 的目录语义（目标已存在时会把源搬进目标内部）；
- 散装文件归位：包一层目标文件夹再逐文件迁移（统一冲突/日志/回滚语义）。
"""
from __future__ import annotations

import os
import shutil
import stat
import time
from pathlib import Path

from .config import STAGING_NAME

MARKER_PREFIX = ".incomplete-"


class TransferError(Exception):
    """迁移前置条件不满足（目标已存在、源缺失等）。"""


class IncompleteTransfer(TransferError):
    """复制过程中断/校验失败（留有 .incomplete 标记的残留）。"""


def split_drive(p) -> str:
    return os.path.splitdrive(str(p))[0].lower()


def staging_for_root(root) -> Path:
    """root 为库根/兜底库/源根：staging 放在其父目录下（必然在所有库根之外）。"""
    return Path(root).parent / STAGING_NAME


def _copy_with_retry(src: Path, dst: Path, retries: int = 3) -> None:
    for attempt in range(retries):
        try:
            shutil.copy2(src, dst)
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            time.sleep(0.3 * (attempt + 1))


def _verify_tree(root: Path, expected: dict[str, int]) -> None:
    found: dict[str, int] = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.startswith(MARKER_PREFIX):
                continue
            p = Path(dirpath) / fn
            found[p.relative_to(root).as_posix()] = p.stat().st_size
    missing = sorted(set(expected) - set(found))
    if missing:
        raise IncompleteTransfer(f"复制后缺失 {len(missing)} 个文件，例如 {missing[:3]}")
    extra = sorted(set(found) - set(expected))
    if extra:
        raise IncompleteTransfer(f"复制后出现快照之外的文件，例如 {extra[:3]}")
    bad = [rel for rel, size in expected.items() if rel in found and found[rel] != size]
    if bad:
        raise IncompleteTransfer(f"复制后大小不一致，例如 {bad[:3]}")


def _force_rmtree(path: Path) -> None:
    def _onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
        func(p)
    shutil.rmtree(path, onerror=_onerror)


def transfer_dir(src: Path, dst: Path, staging_root: Path,
                 expected: dict[str, int], on_progress=None) -> dict:
    """目录单元迁移。返回 {"mode": "rename"|"staging", ...}。"""
    src, dst = Path(src), Path(dst)
    if not src.is_dir():
        raise TransferError(f"源目录不存在：{src}")
    if dst.exists():
        raise TransferError(f"目标已存在（拒绝移动以免嵌套）：{dst}")
    if split_drive(src) == split_drive(dst):
        os.rename(src, dst)                      # 同卷原子改名
        return {"mode": "rename"}

    staging_root = Path(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    base = staging_root / f"{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}-{src.name}"[:180]
    tmp, i = base, 2
    while tmp.exists():
        tmp = base.parent / f"{base.name}({i})"
        i += 1
    marker = tmp / (MARKER_PREFIX + time.strftime("%Y%m%dT%H%M%S"))
    # 异常直接上抛：staging 残留（含标记）与源目录原地保留，供 preflight 报告与人工清理
    tmp.mkdir(parents=True)
    marker.write_text("transfer in progress", encoding="utf-8")
    for rel in sorted(expected):
        s = src / rel
        if not s.is_file():
            raise IncompleteTransfer(f"快照中的文件已消失：{rel}")
        d = tmp / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        _copy_with_retry(s, d)
        if d.stat().st_size != expected[rel]:
            raise IncompleteTransfer(f"复制后大小不一致：{rel}")
        if on_progress:
            on_progress(rel, expected[rel])
    _verify_tree(tmp, expected)
    marker.unlink()
    os.rename(tmp, dst)                      # staging 与库同卷 → 原子
    _force_rmtree(src)
    return {"mode": "staging", "staging": str(tmp)}


def transfer_loose(files: list, dst_dir: Path, staging_root: Path,
                   expected: dict[str, int], on_progress=None) -> dict:
    """散装文件单元：包一层 dst_dir 再迁移。"""
    files = [Path(f) for f in files]
    for f in files:
        if not f.is_file():
            raise TransferError(f"源文件不存在：{f}")
    dst_dir = Path(dst_dir)
    if dst_dir.exists():
        raise TransferError(f"目标已存在（拒绝覆盖）：{dst_dir}")
    dst_dir.mkdir(parents=True)
    same = split_drive(files[0]) == split_drive(dst_dir) and \
        len({split_drive(f) for f in files}) == 1
    marker = None
    if not same:
        marker = dst_dir / (MARKER_PREFIX + time.strftime("%Y%m%dT%H%M%S"))
        marker.write_text("transfer in progress", encoding="utf-8")
    for f in files:
        rel = f.name
        if rel not in expected:
            raise IncompleteTransfer(f"文件不在计划快照中：{rel}")
        d = dst_dir / rel
        if same:
            os.rename(f, d)
        else:
            _copy_with_retry(f, d)
            if d.stat().st_size != expected[rel]:
                raise IncompleteTransfer(f"复制后大小不一致：{rel}")
            f.unlink()
        if on_progress:
            on_progress(rel, expected[rel])
    _verify_tree(dst_dir, expected)
    if marker:
        marker.unlink()
    return {"mode": "rename" if same else "staging"}


def restore_loose(dst_dir: Path, src_dir: Path, expected: dict[str, int]) -> dict:
    """散装文件单元回滚：逐文件还原到源位置。"""
    dst_dir, src_dir = Path(dst_dir), Path(src_dir)
    if not dst_dir.is_dir():
        raise TransferError(f"待还原目录不存在：{dst_dir}")
    src_dir.mkdir(parents=True, exist_ok=True)
    same = split_drive(dst_dir) == split_drive(src_dir)
    for rel in sorted(expected):
        s = dst_dir / rel
        d = src_dir / rel
        if not s.is_file():
            raise IncompleteTransfer(f"待还原文件缺失：{rel}")
        if d.exists():
            raise TransferError(f"还原位置已存在同名文件：{d}")
        if same:
            os.rename(s, d)
        else:
            _copy_with_retry(s, d)
            if d.stat().st_size != expected[rel]:
                raise IncompleteTransfer(f"还原后大小不一致：{rel}")
            s.unlink()
    leftover = [c.name for c in dst_dir.iterdir()
                if not c.name.startswith(MARKER_PREFIX)]
    if not leftover:
        _force_rmtree(dst_dir)
    return {"mode": "rename" if same else "staging"}


def find_staging_leftovers(roots) -> list[Path]:
    """在候选 staging 根下找带 .incomplete 标记的残留目录。"""
    out: list[Path] = []
    for r in roots:
        r = Path(r)
        if not r.is_dir():
            continue
        try:
            children = list(r.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            try:
                marked = any(c.is_file() and c.name.startswith(MARKER_PREFIX)
                             for c in child.iterdir())
            except OSError:
                continue
            if marked:
                out.append(child)
    return out


def cleanup_leftovers(paths) -> list[str]:
    removed = []
    for p in paths:
        _force_rmtree(Path(p))
        removed.append(str(p))
    return removed

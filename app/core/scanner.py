"""影片单元扫描：识别目录/散装文件、定位 NFO、生成迁移快照。

单元识别规则（决策 D-20261031-05，经 D-20261110-01 复议）：
- 一个"影片单元"= 含恰好一部影片（单 base/单 disc）的最内层完整目录，或散装单视频文件
  （归位时包一层同名文件夹）；
- 源根顶层纯容器目录（根层无正片视频、全部视频内容位于单片子目录）下钻，
  每个子目录一个单元，女优段（actress）取容器目录名逐字保留；
- extras/trailers/sample/@eaDir 等目录与 sample/trailer 视频不参与识别；
- 多 CD/part 视频合并为一个单元；BDMV/VIDEO_TS/ISO 光盘结构视为一个单元；
- 容器混合（存在多 base 子目录或根层正片视频与子目录影片并存）→ 整目录复合单元
  （ST_BATCH 待人工改判）；
- 快照覆盖目录内全部文件（含 extras），保证跨盘复制零遗漏。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .nfo import NfoInfo, parse_nfo_file

VIDEO_EXTS = {
    ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg",
    ".mpe", ".ts", ".m2ts", ".mts", ".vob", ".iso", ".strm", ".rmvb", ".rm",
    ".3gp", ".webm", ".ogv", ".divx", ".f4v", ".m2v", ".tp", ".trp",
}
SUB_EXTS = {".srt", ".ass", ".ssa", ".sub", ".sup", ".vtt"}

EXCLUDED_DIRS = {
    "extras", "featurettes", "trailers", "trailer", "behind the scenes",
    "behind_the_scenes", "sample", "samples", "@eadir", "#recycle",
    "$recycle.bin", "recycle.bin", "recycled", "system volume information",
    "lost+found", ".actors", ".deletedbyinclusion", "extrafanart",
    "extrathumbs", ".nfo-sorter-staging", "subs", "subtitles", "cover", "covers",
}

RE_MULTI_CD = re.compile(
    r"^(.*?)[\s._\-(]*(?:cd|dvd|part|pt|disc|dis[kc])[\s._\-(]*(\d{1,2})[\s._\)-]*$", re.IGNORECASE)
RE_SAMPLE = re.compile(r"(^|[.\-_ ])(sample|trailer|prologue)([.\-_ ]|$)", re.IGNORECASE)
# 已刮削文件夹常见的花絮/预告/附加视频（尾部锚定，避免误伤正片标题）
RE_SUPPLEMENT = re.compile(
    r"(?:^|[\s._\-[(])(?:sample|trailers?|prologue|featurettes?|interviews?"
    r"|behind[\s._\-]?the[\s._\-]?scenes?|deleted[\s._\-]?scenes?|extended[\s._\-]?scenes?"
    r"|making[\s._\-]?of|extras?|scenes?|shorts?|bonus)"
    r"(?:[\s._\-]*(?:\d{1,4}|[a-z]{1,3}))?$", re.IGNORECASE)

EXCLUDED_DIR_TOKENS = ("extras", "trailers", "featurettes",
                       "behind the scenes", "bonus", "samples")


def _is_excluded_dir(name: str) -> bool:
    """单元内部子目录剔除：精确名单 + 关键词包含（如『片名 - Extras』）。"""
    n = name.lower()
    if n in EXCLUDED_DIRS or n.startswith("."):
        return True
    return any(tok in n for tok in EXCLUDED_DIR_TOKENS)


def _own_main_videos(d: Path) -> list[Path]:
    """d 直接子文件中的正片视频：¬RE_SAMPLE ∧ ¬RE_SUPPLEMENT（深度 1，不回退）。"""
    return [f for f in sorted(d.iterdir(), key=lambda p: p.name.lower())
            if f.is_file() and f.suffix.lower() in VIDEO_EXTS
            and not RE_SAMPLE.search(f.stem) and not RE_SUPPLEMENT.search(f.stem)]


def _has_disc_structure(d: Path) -> bool:
    """BDMV/VIDEO_TS 子目录存在，或直接子文件正片视频里含 .iso。"""
    if (d / "BDMV").is_dir() or (d / "VIDEO_TS").is_dir():
        return True
    return any(f.suffix.lower() == ".iso" for f in _own_main_videos(d))


def _child_dirs(d: Path) -> list[Path]:
    """直接子目录，剔除排除名单与点目录，按名排序。"""
    return sorted((c for c in d.iterdir() if c.is_dir() and not _is_excluded_dir(c.name)),
                  key=lambda p: p.name.lower())


def _dir_has_video(d: Path) -> bool:
    """识别遍历下存在 ≥1 个非 sample 视频（花絮也计入，供容器判定用）。"""
    return any(f.suffix.lower() in VIDEO_EXTS and not RE_SAMPLE.search(f.stem)
               for f in _walk_files_pruned(d))


def _is_movie_dir(d: Path) -> bool:
    """单片影片目录判定：恰一部影片（单 base/单 disc），不要求 NFO。"""
    videos = [f for f in _walk_files_pruned(d)
              if f.suffix.lower() in VIDEO_EXTS and not RE_SAMPLE.search(f.stem)]
    if not videos:
        return False
    mains = [f for f in videos if not RE_SUPPLEMENT.search(f.stem)]
    if not mains:
        return False  # 只有花絮/预告：不猜归属，交由容器整体判定
    if (d / "BDMV").is_dir() or (d / "VIDEO_TS").is_dir() \
            or any(v.suffix.lower() == ".iso" for v in mains):
        return True
    bases = set()
    for v in mains:
        m = RE_MULTI_CD.match(v.stem)
        bases.add(m.group(1).strip(" ._-").lower() if m else v.stem.lower())
    return len(bases) == 1


@dataclass
class Unit:
    id: str                       # 相对 source_root 的 posix 路径，唯一
    path: Path                    # 目录（kind=dir）或视频文件（kind=file）
    kind: str                     # dir | file
    dst_name: str                 # 归位后的目标文件夹名
    videos: list[Path] = field(default_factory=list)
    multi_cd: bool = False
    disc: bool = False
    composite: bool = False
    actress: str | None = None   # 下钻单元的女优段（容器目录名逐字保留）；无女优段为 None
    nfo_path: Path | None = None
    nfo: NfoInfo | None = None
    title: str = ""
    year: int | None = None
    provider: str | None = None
    files: list[tuple[str, int, int]] = field(default_factory=list)  # (rel, size, mtime_ns)
    total_size: int = 0
    file_count: int = 0
    max_mtime_ns: int = 0
    flags: list[str] = field(default_factory=list)


def _walk_files_pruned(root: Path):
    """识别用遍历：跳过 extras/花絮/系统目录与点目录。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]
        for fn in sorted(filenames):
            yield Path(dirpath) / fn


def _walk_files_full(root: Path):
    """快照用遍历：目录内所有文件（迁移必须零遗漏）。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".nfo-sorter-staging"]
        for fn in sorted(filenames):
            yield Path(dirpath) / fn


def snapshot_dir(path: Path) -> list[tuple[str, int, int]]:
    out = []
    for f in _walk_files_full(path):
        st = f.stat()
        rel = f.relative_to(path).as_posix()
        out.append((rel, st.st_size, st.st_mtime_ns))
    return out


def _snapshot_stats(files: list[tuple[str, int, int]]) -> tuple[int, int, int]:
    total = sum(s for _, s, _ in files)
    count = len(files)
    mx = max((m for _, _, m in files), default=0)
    return total, count, mx


def find_nfo(d: Path, videos: list[Path], multi_cd: bool) -> Path | None:
    cands: list[Path] = [d / "movie.nfo"]
    if videos:
        first = videos[0]
        cands.append(first.with_suffix(".nfo"))
        if multi_cd:
            m = RE_MULTI_CD.match(first.stem)
            if m:
                base = m.group(1).strip(" ._-")
                if base:
                    cands.append(d / f"{base}.nfo")
    cands.append(d / f"{d.name}.nfo")
    cands.extend(sorted(d.glob("*.nfo")))
    seen: set[Path] = set()
    for c in cands:
        if c in seen:
            continue
        seen.add(c)
        if c.is_file():
            return c
    return None


def _analyze_dir(d: Path, rel_id: str,
                 actress: str | None = None) -> tuple[Unit | None, dict | None]:
    all_files = list(_walk_files_full(d))
    if not all_files and not any(d.iterdir()):
        return None, None
    videos = [f for f in _walk_files_pruned(d)
              if f.suffix.lower() in VIDEO_EXTS and not RE_SAMPLE.search(f.stem)]
    disc = (d / "BDMV").is_dir() or (d / "VIDEO_TS").is_dir() or \
        any(f.suffix.lower() == ".iso" for f in videos)
    flags = ["disc_structure"] if disc else []

    if not videos:
        has_nfo = (d / "movie.nfo").is_file() or any(d.glob("*.nfo"))
        note = {"level": "warn", "path": str(d),
                "reason": "目录内未发现视频文件（含 NFO），已跳过"} if has_nfo else None
        return None, note

    # 已刮削文件夹：散落的花絮/预告/附加视频不算正片，避免误判成复合目录；
    # 整个文件夹（含这些花絮与海报/字幕）仍按快照整目录迁移。
    mains = [f for f in videos if not RE_SUPPLEMENT.search(f.stem)]
    if mains:
        videos = mains

    multi_cd = False
    if not disc:
        bases: dict[str, list[Path]] = {}
        for v in videos:
            m = RE_MULTI_CD.match(v.stem)
            key = m.group(1).strip(" ._-").lower() if m else v.stem.lower()
            bases.setdefault(key, []).append(v)
        if len(bases) > 1:
            vids = sorted(mains or videos, key=lambda p: p.name.lower())
            nfo_path = find_nfo(d, vids, False)
            info = parse_nfo_file(nfo_path) if nfo_path else None
            if info and info.parse_error:
                flags.append("nfo_parse_warning")
            elif info and info.recovery:
                flags.append("nfo_recovered")
            files = snapshot_dir(d)
            total, count, mx = _snapshot_stats(files)
            unit = Unit(
                id=rel_id, path=d, kind="dir", dst_name=d.name,
                videos=vids, multi_cd=False, disc=disc, composite=True,
                actress=actress,
                nfo_path=nfo_path, nfo=info,
                title=(info.title if info and info.title else d.name),
                year=(info.year if info else None),
                provider=(info.provider_id if info else None),
                files=files, total_size=total, file_count=count, max_mtime_ns=mx,
                flags=flags + ["composite"],
            )
            return unit, {"level": "info", "path": str(d),
                          "reason": f"复合目录：{len(bases)} 个疑似影片 base，"
                                    "已作为整目录单元生成（需目录级改判后执行）"}
        vids = next(iter(bases.values()))
        multi_cd = len(vids) > 1 and any(RE_MULTI_CD.match(v.stem) for v in vids)
    else:
        vids = videos
    vids = sorted(vids, key=lambda p: p.name.lower())

    nfo_path = find_nfo(d, vids, multi_cd)
    info = parse_nfo_file(nfo_path) if nfo_path else None
    if info and info.parse_error:
        flags.append("nfo_parse_warning")
    elif info and info.recovery:
        flags.append("nfo_recovered")

    files = snapshot_dir(d)
    total, count, mx = _snapshot_stats(files)
    unit = Unit(
        id=rel_id, path=d, kind="dir", dst_name=d.name,
        videos=vids, multi_cd=multi_cd, disc=disc,
        actress=actress,
        nfo_path=nfo_path, nfo=info,
        title=(info.title if info and info.title else d.name),
        year=(info.year if info else None),
        provider=(info.provider_id if info else None),
        files=files, total_size=total, file_count=count, max_mtime_ns=mx,
        flags=flags,
    )
    return unit, None


def _analyze_loose(f: Path, rel_id: str) -> tuple[Unit | None, dict | None]:
    stem = f.stem
    sibs = []
    for s in sorted(f.parent.iterdir(), key=lambda p: p.name.lower()):
        if not s.is_file() or s == f:
            continue
        if ((s.stem == stem or s.stem.startswith(stem + "."))
                and (s.suffix.lower() in SUB_EXTS or s.suffix.lower() == ".nfo")):
            sibs.append(s)
    files_paths = [f] + sibs
    nfo_path = next((s for s in sibs if s.suffix.lower() == ".nfo"), None)
    info = parse_nfo_file(nfo_path) if nfo_path else None

    rel_files = []
    for p in files_paths:
        st = p.stat()
        rel_files.append((p.name, st.st_size, st.st_mtime_ns))
    total, count, mx = _snapshot_stats(rel_files)
    unit = Unit(
        id=rel_id, path=f, kind="file", dst_name=stem,
        videos=[f], nfo_path=nfo_path, nfo=info,
        title=(info.title if info and info.title else stem),
        year=(info.year if info else None),
        provider=(info.provider_id if info else None),
        files=rel_files, total_size=total, file_count=count, max_mtime_ns=mx,
    )
    return unit, None


def scan_source_root(cfg: Config) -> tuple[list[Unit], list[dict]]:
    units: list[Unit] = []
    notes: list[dict] = []
    root = cfg.source_root
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        name = entry.name
        if name.startswith((".", "$")) or name.lower() in EXCLUDED_DIRS:
            continue
        if entry.is_file() and RE_SUPPLEMENT.search(entry.stem):
            continue  # 散落的花絮/预告文件不作为影片单元
        rel_id = entry.relative_to(root).as_posix()
        try:
            if entry.is_dir():
                if _own_main_videos(entry) or _has_disc_structure(entry):
                    # R1：容器根层直接躺正片视频或光盘结构 → 容器自身就是影片目录，绝不拆
                    unit, note = _analyze_dir(entry, rel_id)
                else:
                    kids = _child_dirs(entry)
                    withvid = [c for c in kids if _dir_has_video(c)]
                    movies = [c for c in withvid if _is_movie_dir(c)]
                    if movies and len(movies) == len(withvid):
                        # R2：纯容器（全部视频内容位于单片子目录）→ 下钻，女优段=容器名
                        for c in movies:
                            cu, cn = _analyze_dir(
                                c, c.relative_to(root).as_posix(), actress=entry.name)
                            if cn:
                                notes.append(cn)
                            if cu:
                                if cu.nfo and cu.nfo.parse_error:
                                    notes.append({"level": "warn",
                                                  "path": str(cu.nfo_path or cu.path),
                                                  "reason": cu.nfo.parse_error})
                                cu.flags.append("nested")
                                units.append(cu)
                        notes.append({"level": "info", "path": str(entry),
                                      "reason": f"容器目录：内含 {len(movies)} 个影片目录，"
                                                f"已按 女优\\影片 拆为独立单元"
                                                f"（女优段={entry.name}）"})
                        kept = set(movies)
                        left_dirs = sorted((c.name for c in entry.iterdir()
                                            if c.is_dir() and c not in kept),
                                           key=str.lower)
                        left_files = sorted((f.name for f in entry.iterdir()
                                             if f.is_file()), key=str.lower)
                        parts = []
                        if left_dirs:
                            parts.append("子目录 " + "、".join(left_dirs[:5]))
                        if left_files:
                            parts.append("文件 " + "、".join(left_files[:5]))
                        if parts:
                            notes.append({"level": "warn", "path": str(entry),
                                          "reason": "容器目录附件残留（不随单元迁移，"
                                                    "留在源处）：" + "；".join(parts)})
                        unit, note = None, None
                    else:
                        # R3：混合（存在多 base/非单片子目录）或全目录无视频 → 整目录既有语义
                        unit, note = _analyze_dir(entry, rel_id)
                        if withvid and len(movies) < len(withvid):
                            notes.append({"level": "info", "path": str(entry),
                                          "reason": f"容器目录混合：{len(withvid) - len(movies)}"
                                                    " 个子目录为多 base/非单片内容，"
                                                    "整目录回退为复合单元（待人工改判）"})
            elif entry.suffix.lower() in VIDEO_EXTS:
                unit, note = _analyze_loose(entry, rel_id)
            else:
                continue
        except OSError as exc:
            notes.append({"level": "warn", "path": str(entry), "reason": f"访问失败：{exc}"})
            continue
        if note:
            notes.append(note)
        if unit:
            if unit.nfo and unit.nfo.parse_error:
                notes.append({"level": "warn", "path": str(unit.nfo_path or unit.path),
                              "reason": unit.nfo.parse_error})
            units.append(unit)
    units.sort(key=lambda u: u.id.lower())
    return units, notes

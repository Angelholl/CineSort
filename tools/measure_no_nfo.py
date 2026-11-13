"""无 NFO 残差双口径测量（决策 D-20261113-01 Step A，一次性只读脚本）。

口径：
- production：复用 ``app.core.scanner.scan_source_root``，与主流程同语义；
- 深查：独立递归遍历全树，逐视频文件判定 NFO 共位、伴随字幕类目与番号。

脱敏红线：Markdown / JSON 均不落完整文件名、目录名、女优名或根路径之外的
路径成分；样本区只允许番号与扩展名类目。脚本对被测目录只读，不写任何文件。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Config, ConfigError, is_sub_path, load_config
from app.core.scanner import VIDEO_EXTS, scan_source_root

TEXT_SUBS = {".srt", ".ass", ".ssa", ".vtt"}
BITMAP_SUBS = {".sub", ".sup"}
STAGING_NAME = ".nfo-sorter-staging"

_RE_LEAD_TAGS = re.compile(r"^(?:\s*[\[【][^\]】]*[\]】])+")
_RE_FC2 = re.compile(
    r"(?<![A-Za-z0-9])FC2[-_ ]?PPV[-_ ]?(\d{6,8})(?!\d)", re.IGNORECASE
)
_RE_CODE = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z]{2,6})[-_ ]?(\d{2,5})"
    r"(?:-(?!CD\d)([A-Za-z]))?(?!\d)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VideoRecord:
    """深查视角的单个视频文件（parent 仅供内部去重，不进入报告）。"""

    parent: Path
    depth: int
    ext: str
    code: str | None
    has_nfo: bool
    text_sub: bool
    bitmap_sub: bool


def strip_leading_tags(stem: str) -> str:
    """剥除前导【】/[] 字幕组、站点标记（可连续多个）。"""
    return _RE_LEAD_TAGS.sub("", stem).strip()


def extract_code(stem: str) -> str | None:
    """保守番号提取：匹配不到返回 None，不猜。"""
    name = strip_leading_tags(stem)
    m = _RE_FC2.search(name)
    if m:
        return f"FC2-PPV-{m.group(1)}"
    m = _RE_CODE.search(name)
    if not m:
        return None
    code = f"{m.group(1).upper()}-{m.group(2)}"
    if m.group(3):
        code += f"-{m.group(3).upper()}"
    return code


def _nfo_in_dir(d: Path) -> bool:
    try:
        for entry in os.scandir(d):
            if entry.is_file() and Path(entry.name).suffix.lower() == ".nfo":
                return True
    except OSError:
        return False
    return False


def _sub_signal_in_dir(d: Path) -> tuple[bool, bool]:
    """同目录及一层子目录内是否出现文本/位图字幕（大小写不敏感）。"""
    text = bitmap = False
    dirs = [d]
    try:
        dirs.extend(p for p in d.iterdir() if p.is_dir()
                    and not p.name.startswith("."))
    except OSError:
        return False, False
    for cur in dirs:
        try:
            names = os.listdir(cur)
        except OSError:
            continue
        for name in names:
            ext = Path(name).suffix.lower()
            if ext in TEXT_SUBS:
                text = True
            elif ext in BITMAP_SUBS:
                bitmap = True
        if text and bitmap:
            break
    return text, bitmap


def deep_walk(root: Path) -> list[VideoRecord]:
    """递归全树逐视频文件采集（地面真值，不受单元语义影响）。"""
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    nfo_cache: dict[Path, bool] = {}
    sub_cache: dict[Path, tuple[bool, bool]] = {}
    records: list[VideoRecord] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != STAGING_NAME)
        d = Path(dirpath)
        depth = len(d.relative_to(root).parts)
        for name in sorted(filenames):
            ext = Path(name).suffix.lower()
            if ext not in VIDEO_EXTS:
                continue
            if d not in nfo_cache:
                nfo_cache[d] = _nfo_in_dir(d)
            if d not in sub_cache:
                sub_cache[d] = _sub_signal_in_dir(d)
            text_sub, bitmap_sub = sub_cache[d]
            records.append(VideoRecord(
                parent=d,
                depth=depth,
                ext=ext,
                code=extract_code(Path(name).stem),
                has_nfo=nfo_cache[d],
                text_sub=text_sub,
                bitmap_sub=bitmap_sub,
            ))
    return records


def measure(root: Path, cfg: Config) -> dict:
    """双口径测量，返回可脱敏落盘的汇总 + 明细。"""
    units, _notes = scan_source_root(cfg)
    records = deep_walk(root)
    matched = [r for r in records if r.code]
    distinct = {(r.parent, r.code) for r in matched}
    extensions: dict[str, int] = {}
    for r in records:
        extensions[r.ext] = extensions.get(r.ext, 0) + 1
    return {
        "root": str(root),
        "generated": datetime.now().astimezone().date().isoformat(),
        "production": {
            "units_total": len(units),
            "units_without_nfo": sum(1 for u in units if u.nfo_path is None),
        },
        "deep": {
            "videos_total": len(records),
            "videos_without_nfo": sum(1 for r in records if not r.has_nfo),
            "text_sub_videos": sum(1 for r in records if r.text_sub),
            "bitmap_sub_videos": sum(1 for r in records if r.bitmap_sub),
            "codes_extracted": len(matched),
            "code_units_deduped": len(distinct),
            "shards_merged": len(matched) - len(distinct),
        },
        "samples": {
            "codes": sorted({r.code for r in matched if r.code})[:20],
            "extensions": dict(sorted(extensions.items())),
        },
        "videos": [
            {
                "idx": i,
                "depth": r.depth,
                "ext": r.ext,
                "code": r.code,
                "has_nfo": r.has_nfo,
                "text_sub": r.text_sub,
                "bitmap_sub": r.bitmap_sub,
            }
            for i, r in enumerate(records)
        ],
    }


def render_markdown(result: dict) -> str:
    prod = result["production"]
    deep = result["deep"]
    samples = result["samples"]
    codes = "、".join(samples["codes"]) or "（无）"
    exts = "、".join(
        f"`{ext}` × {count}" for ext, count in samples["extensions"].items()
    ) or "（无）"
    lines = [
        "# 无 NFO 残差测量报告",
        "",
        f"- 生成日期：{result['generated']}",
        (
            "- 口径：production = scan_source_root（与主流程同语义）；"
            "深查 = 全树递归（地面真值）"
        ),
        f"- 源根：{result['root']}",
        "",
        "## 汇总",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| production 单元总数 | {prod['units_total']} |",
        f"| 无 NFO 单元数 | {prod['units_without_nfo']} |",
        f"| 深查视频总数 | {deep['videos_total']} |",
        f"| 无 NFO 视频数 | {deep['videos_without_nfo']} |",
        f"| 文本字幕视频数 | {deep['text_sub_videos']} |",
        f"| 位图字幕视频数 | {deep['bitmap_sub_videos']} |",
        f"| 番号可提取视频数 | {deep['codes_extracted']} |",
        (
            f"| 同番号分片去重数 | {deep['code_units_deduped']}"
            f"（合并分片文件 {deep['shards_merged']} 个） |"
        ),
        "",
        "## 样本（脱敏：仅番号与扩展名类目）",
        "",
        f"- 番号样本（最多 20 个）：{codes}",
        f"- 扩展名类目：{exts}",
        "",
    ]
    return "\n".join(lines)


def write_report(result: dict, out_dir: Path) -> tuple[Path, Path]:
    """写 Markdown 摘要 + JSON 明细，返回两个路径。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = out_dir.name or "measure-no-nfo"
    md_path = out_dir / f"{name}.md"
    json_path = out_dir / f"{name}.json"
    md_path.write_text(render_markdown(result), encoding="utf-8")
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return md_path, json_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="无 NFO 残差双口径只读测量（D-20261113-01 Step A）"
    )
    parser.add_argument(
        "--config", default=str(PROJECT_ROOT / "config.toml"),
        help="配置文件路径（默认项目根 config.toml）",
    )
    parser.add_argument(
        "--root", default=None,
        help="被测源根（默认取配置的 source_root）",
    )
    parser.add_argument(
        "--out", default=None,
        help="输出目录（默认 artifacts/measure-no-nfo-<YYYYMMDD>）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2
    root = Path(args.root).expanduser().resolve() if args.root else cfg.source_root
    if not root.is_dir():
        print(f"源根不存在或不是目录：{root}", file=sys.stderr)
        return 2
    if root != cfg.source_root:
        cfg = replace(cfg, source_root=root)
    day = datetime.now().astimezone().strftime("%Y%m%d")
    out_dir = (
        Path(args.out).expanduser() if args.out
        else PROJECT_ROOT / "artifacts" / f"measure-no-nfo-{day}"
    )
    out_dir = out_dir.resolve()
    if is_sub_path(out_dir, root):
        print(f"输出目录不能位于被测源根内部：{out_dir}", file=sys.stderr)
        return 2
    result = measure(root, cfg)
    md_path, json_path = write_report(result, out_dir)
    deep = result["deep"]
    prod = result["production"]
    print(f"报告：{md_path}")
    print(f"明细：{json_path}")
    print(
        f"production 单元 {prod['units_total']}（无 NFO {prod['units_without_nfo']}）"
        f" / 深查视频 {deep['videos_total']}（无 NFO {deep['videos_without_nfo']}）"
        f" / 文本字幕 {deep['text_sub_videos']}"
        f" / 位图字幕 {deep['bitmap_sub_videos']}"
        f" / 番号 {deep['codes_extracted']}"
        f"（去重 {deep['code_units_deduped']}）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

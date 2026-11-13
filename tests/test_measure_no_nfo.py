"""无 NFO 残差测量脚本测试（D-20261113-01 Step A）。"""
import importlib.util
import sys
from pathlib import Path

from app.core.config import Config

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "measure_no_nfo", ROOT / "tools" / "measure_no_nfo.py"
)
measure_no_nfo = importlib.util.module_from_spec(_SPEC)
sys.modules["measure_no_nfo"] = measure_no_nfo
_SPEC.loader.exec_module(measure_no_nfo)


def bare_cfg(src) -> Config:
    return Config(path=Path("X:/config.toml"), source_root=Path(src),
                  libraries={}, genre_priority=[], genre_aliases={},
                  fallback_path=Path("X:/fb"))


def _records_by_parent(root):
    return {r.parent: r for r in measure_no_nfo.deep_walk(root)}


def test_deep_walk_finds_nested(tmp_path):
    root = tmp_path / "src"
    target = root / "a" / "b" / "c"
    target.mkdir(parents=True)
    (target / "v.mp4").write_bytes(b"V")
    records = measure_no_nfo.deep_walk(root)
    assert len(records) == 1
    assert records[0].parent == target
    assert records[0].ext == ".mp4"


def test_nfo_colocation(tmp_path):
    root = tmp_path / "src"
    with_nfo = root / "one"
    without = root / "two"
    with_nfo.mkdir(parents=True)
    without.mkdir()
    (with_nfo / "v1.mp4").write_bytes(b"V")
    (with_nfo / "v1.nfo").write_text("<movie/>", encoding="utf-8")
    (without / "v2.mp4").write_bytes(b"V")
    records = _records_by_parent(root)
    assert records[with_nfo].has_nfo is True
    assert records[without].has_nfo is False


def test_subtitle_classification(tmp_path):
    root = tmp_path / "src"
    plain = root / "a"
    bitmap = root / "b"
    upper = root / "c"
    for d in (plain, bitmap, upper):
        d.mkdir(parents=True)
    (plain / "v.mp4").write_bytes(b"V")
    (plain / "v.srt").write_bytes(b"S")
    (bitmap / "v.mp4").write_bytes(b"V")
    (bitmap / "v.sup").write_bytes(b"S")
    (upper / "v.mp4").write_bytes(b"V")
    (upper / "v.SRT").write_bytes(b"S")
    records = _records_by_parent(root)
    assert (records[plain].text_sub, records[plain].bitmap_sub) == (True, False)
    assert (records[bitmap].text_sub, records[bitmap].bitmap_sub) == (False, True)
    assert (records[upper].text_sub, records[upper].bitmap_sub) == (True, False)


def test_code_extraction_standard():
    assert measure_no_nfo.extract_code("ABP-123") == "ABP-123"
    assert measure_no_nfo.extract_code("JUR-439-C") == "JUR-439-C"


def test_code_extraction_fc2():
    assert measure_no_nfo.extract_code("FC2-PPV-1234567") == "FC2-PPV-1234567"


def test_code_prefix_strip():
    assert measure_no_nfo.extract_code("【某字幕组】ABP-123") == "ABP-123"


def test_code_dedupe_cd(tmp_path):
    root = tmp_path / "src"
    d = root / "ABP-123"
    d.mkdir(parents=True)
    (d / "ABP-123 CD1.mp4").write_bytes(b"V")
    (d / "ABP-123 CD2.mp4").write_bytes(b"V")
    result = measure_no_nfo.measure(root, bare_cfg(root))
    deep = result["deep"]
    assert deep["codes_extracted"] == 2
    assert deep["code_units_deduped"] == 1
    assert deep["shards_merged"] == 1


def test_no_code_chinese(tmp_path):
    assert measure_no_nfo.extract_code("某中文标题 第一集") is None
    root = tmp_path / "src"
    root.mkdir()
    (root / "某中文标题.mp4").write_bytes(b"V")
    result = measure_no_nfo.measure(root, bare_cfg(root))
    assert result["deep"]["codes_extracted"] == 0


def test_report_masking(tmp_path):
    secret = "女优某某"
    root = tmp_path / "src"
    d = root / f"{secret} ABP-123"
    d.mkdir(parents=True)
    (d / f"{secret} ABP-123.mp4").write_bytes(b"V")
    (d / f"{secret} ABP-123.srt").write_bytes(b"S")
    out = tmp_path / "out"
    result = measure_no_nfo.measure(root, bare_cfg(root))
    md_path, json_path = measure_no_nfo.write_report(result, out)
    md = md_path.read_text(encoding="utf-8")
    js = json_path.read_text(encoding="utf-8")
    assert secret not in md
    assert secret not in js
    assert "ABP-123" in md
    assert "ABP-123" in js
    assert ".mp4" in md


def test_walk_ge_production(tmp_path):
    root = tmp_path / "src"
    one = root / "one"
    two = root / "two"
    one.mkdir(parents=True)
    two.mkdir()
    (one / "x.mp4").write_bytes(b"V")
    (one / "x.srt").write_bytes(b"S")
    (two / "y.mp4").write_bytes(b"V")
    cfg = bare_cfg(root)
    result = measure_no_nfo.measure(root, cfg)
    assert result["deep"]["videos_total"] >= result["production"]["units_total"]
    assert result["production"]["units_total"] == 2

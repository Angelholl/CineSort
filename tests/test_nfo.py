"""NFO 解析容错测试（评议条件 C1：≥12 个现实变体）。"""
import codecs

from app.core.nfo import normalize_key, parse_nfo_file, parse_nfo_text
from conftest import nfo_xml


def write(tmp_path, data: bytes, name="movie.nfo"):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_utf8_basic(tmp_path):
    p = write(tmp_path, nfo_xml(genres=("动作", "科幻")).encode("utf-8"))
    info = parse_nfo_file(p)
    assert info.genres == ["动作", "科幻"]
    assert info.year == 2020
    assert info.title == "测试电影"
    assert info.provider_id == "tmdb:123"
    assert info.encoding == "utf-8"
    assert info.parse_error is None


def test_utf8_bom(tmp_path):
    p = write(tmp_path, codecs.BOM_UTF8 + nfo_xml().encode("utf-8"))
    info = parse_nfo_file(p)
    assert info.genres == ["动作", "科幻"]
    assert info.encoding == "utf-8-sig"


def test_utf16_bom(tmp_path):
    p = write(tmp_path, nfo_xml().encode("utf-16"))
    info = parse_nfo_file(p)
    assert info.genres == ["动作", "科幻"]
    assert info.encoding == "utf-16"


def test_declared_gbk(tmp_path):
    text = ("<?xml version='1.0' encoding='gbk'?>"
            "<movie><title>枪战片</title><genre>动作</genre><plot>兵工厂</plot></movie>")
    info = parse_nfo_file(write(tmp_path, text.encode("gbk")))
    assert info.genres == ["动作"]
    assert info.title == "枪战片"
    assert info.encoding.lower() == "gbk"


def test_undeclared_gb18030(tmp_path):
    text = "<movie><title>老片</title><genre>剧情</genre></movie>"
    info = parse_nfo_file(write(tmp_path, text.encode("gb18030")))
    assert info.encoding == "gb18030"
    assert info.genres == ["剧情"]


def test_bare_ampersand_in_plot(tmp_path):
    text = ("<movie><title>A & B</title><genre>动作</genre>"
            "<plot>Tom & Jerry 大战</plot></movie>")
    info = parse_nfo_file(write(tmp_path, text.encode("utf-8")))
    assert "Tom & Jerry" in info.plot
    assert info.parse_error is None


def test_escaped_entity_genre(tmp_path):
    """`Action &amp; Adventure` 是别名匹配最易翻车的点（必须解到实体原义）。"""
    text = "<movie><title>T</title><genre>Action &amp; Adventure</genre><plot>p</plot></movie>"
    info = parse_nfo_text(text)
    assert info.genres == ["Action & Adventure"]


def test_namespace(tmp_path):
    text = ("<movie xmlns='http://kodi.org'><title>T</title>"
            "<genre>喜剧</genre></movie>")
    assert parse_nfo_text(text).genres == ["喜剧"]


def test_multi_root_and_trailing_junk(tmp_path):
    text = nfo_xml(genres=("战争",)) + "\n<other><x>1</x></other>\n垃圾数据"
    assert parse_nfo_text(text).genres == ["战争"]


def test_combined_genres(tmp_path):
    text = ("<movie><title>T</title><genre>动作, 科幻</genre>"
            "<genre>Action/Adventure</genre></movie>")
    assert parse_nfo_text(text).genres == ["动作", "科幻", "Action", "Adventure"]


def test_broken_xml_regex_fallback(tmp_path):
    text = "<movie><title>残片</title><genre>恐怖</genre><plot>鬼宅</plot>"
    info = parse_nfo_text(text)
    assert info.parse_error
    assert info.parse_mode == "regex"
    assert info.genres == ["恐怖"]


def test_empty_and_whitespace_genre(tmp_path):
    info = parse_nfo_text(
        "<movie><title>T</title><genre></genre><genre> 动作 </genre></movie>")
    assert info.genres == ["动作"]


def test_year_with_suffix(tmp_path):
    info = parse_nfo_text("<movie><year>2020年</year></movie>")
    assert info.year == 2020


def test_normalize_key_fullwidth():
    assert normalize_key("Ｓｃｉ－Ｆｉ") == normalize_key("sci-fi")
    assert normalize_key("  Sci Fi ") == "sci fi"


def test_undecodable_returns_error(tmp_path):
    info = parse_nfo_file(write(tmp_path, bytes(range(0x80, 0x100)) * 4))
    assert info.parse_error
    assert info.genres == []

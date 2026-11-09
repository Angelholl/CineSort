"""NFO 解析容错测试（评议条件 C1：≥12 个现实变体）。"""
import codecs

from conftest import nfo_xml

from app.core.nfo import (
    NfoInfo,
    _fill_from_regex,
    normalize_key,
    parse_nfo_file,
    parse_nfo_text,
)


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


DIGIT_TAG_TEXT = ("<movie><title>T</title><genre>动作</genre><plot>p</plot>"
                  "<7mmtvid>wKV281</7mmtvid></movie>")


def test_digit_leading_tag_recovers_via_xml():
    info = parse_nfo_text(DIGIT_TAG_TEXT)
    assert info.parse_mode == "xml"
    assert info.parse_error is None
    assert info.title == "T"
    assert info.genres == ["动作"]
    assert info.plot == "p"


def test_digit_tag_recovery_recorded():
    info = parse_nfo_text(DIGIT_TAG_TEXT)
    assert "数字开头" in info.recovery


def test_digit_rewrite_leaves_wellformed_untouched():
    info = parse_nfo_text(nfo_xml())
    assert info.parse_mode == "xml"
    assert info.recovery == ""
    assert info.parse_error is None


def test_digit_tag_xml_and_regex_paths_agree():
    xml_info = parse_nfo_text(DIGIT_TAG_TEXT)
    regex_info = NfoInfo()
    _fill_from_regex(regex_info, DIGIT_TAG_TEXT)
    assert xml_info.genres == regex_info.genres
    assert xml_info.title == regex_info.title
    assert xml_info.plot == regex_info.plot


def test_bare_javdbid_becomes_provider():
    info = parse_nfo_text(
        "<movie><title>T</title><genre>动作</genre><javdbid>wKV281</javdbid></movie>")
    assert info.uniqueids == {"javdb": "wKV281"}
    assert info.provider_id == "javdb:wKV281"


def test_bare_tmdbid_merges_scheme():
    info = parse_nfo_text("<movie><tmdbid>42</tmdbid></movie>")
    assert info.provider_id == "tmdb:42"


def test_uniqueid_attr_beats_bare_id():
    info = parse_nfo_text(
        '<movie><uniqueid type="tmdb">1</uniqueid><tmdbid>2</tmdbid></movie>')
    assert info.uniqueids["tmdb"] == "1"


def test_bare_id_regex_path():
    info = parse_nfo_text(
        "<movie><genre>恐怖</genre><javdbid>wKV281</javdbid>")
    assert info.parse_mode == "regex"
    assert info.uniqueids == {"javdb": "wKV281"}


def test_bare_id_ignores_empty_and_plain_id():
    info = parse_nfo_text("<movie><id>plain</id><javdbid></javdbid></movie>")
    assert info.uniqueids == {}


def test_url_valued_bare_id_is_not_an_identifier():
    """值像 URL 的裸 id 标签（<iqqtvid>https://…）不是稳定标识，不得进 uniqueids（xml 与 regex 两档一致）。"""
    xml_info = parse_nfo_text(
        "<movie><title>T</title><genre>动作</genre>"
        "<javdbid>wKV281</javdbid><iqqtvid>https://iqq5.xyz/jp/player.php?uuid=a</iqqtvid></movie>")
    assert xml_info.uniqueids == {"javdb": "wKV281"}
    regex_info = parse_nfo_text(
        "<movie><genre>动作</genre><iqqtvid>https://iqq5.xyz/x</iqqtvid>")
    assert regex_info.parse_mode == "regex"
    assert regex_info.uniqueids == {}
    assert regex_info.provider_id is None


def test_rewritten_digit_tag_never_becomes_provider_id():
    """重写产物 <_7mmtvid> 不得进入 uniqueids，否则 provider id 被 URL 污染且随元素顺序漂移。"""
    info = parse_nfo_text(
        "<movie><title>T</title><genre>动作</genre>"
        "<7mmtvid>https://x</7mmtvid><javdbid>wKV281</javdbid></movie>")
    assert info.parse_mode == "xml"
    assert info.recovery
    assert info.uniqueids == {"javdb": "wKV281"}
    assert info.provider_id == "javdb:wKV281"


def test_digit_tag_only_file_has_no_provider_id():
    """只有被重写的外部链接标签时，不应凭空产生 provider id。"""
    info = parse_nfo_text(
        "<movie><title>T</title><genre>动作</genre><7mmtvid>https://x</7mmtvid></movie>")
    assert info.parse_mode == "xml"
    assert info.uniqueids == {}
    assert info.provider_id is None

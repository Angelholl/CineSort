"""NFO 文件解析（Kodi / Jellyfin / tinyMediaManager 兼容）。

编码探测链（评议条件 C1）：UTF-8/UTF-16/UTF-32 BOM → XML 声明编码 → utf-8 → gb18030 → cp1252。
XML 容错：BOM、多根/尾部垃圾、裸 `&`、命名空间、标签大小写；
正则兜底路径必须 html.unescape（`Action &amp; Adventure` 是最易翻车点）。
"""
from __future__ import annotations

import codecs
import html
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

_RE_DECL_ENC = re.compile(rb'<\?xml[^>]*encoding=["\']([A-Za-z0-9._-]+)["\']')
_RE_MOVIE_BLOCK = re.compile(r"<movie[\s>].*?</movie\s*>", re.S | re.I)
_RE_BARE_AMP = re.compile(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)")
_RE_GENRE_TAG = re.compile(r"<genre[^>]*>(.*?)</genre\s*>", re.S | re.I)
_RE_PLOT_TAG = re.compile(r"<plot[^>]*>(.*?)</plot\s*>", re.S | re.I)
_RE_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title\s*>", re.S | re.I)
_RE_YEAR_TAG = re.compile(r"<year[^>]*>(.*?)</year\s*>", re.S | re.I)
_RE_UNIQUEID_TAG = re.compile(
    r"<uniqueid[^>]*type=[\"']([^\"']*)[\"'][^>]*>([^<]*)</uniqueid\s*>", re.S | re.I)
_RE_ID_TAG = re.compile(
    r"<id[^>]*moviedb=[\"']([^\"']*)[\"'][^>]*>([^<]*)</id\s*>", re.S | re.I)
_GENRE_SPLIT = re.compile(r"[,，/;；|、]+")
_STRIP_TAGS = re.compile(r"<[^>]+>")
_ENC_CHAIN = ("utf-8", "gb18030", "cp1252")


@dataclass
class NfoInfo:
    title: str | None = None
    year: int | None = None
    genres: list[str] = field(default_factory=list)
    plot: str = ""
    uniqueids: dict[str, str] = field(default_factory=dict)
    encoding: str = ""
    parse_mode: str = "xml"          # xml | regex
    parse_error: str | None = None

    @property
    def provider_id(self) -> str | None:
        for scheme in ("tmdb", "imdb", "tvdb"):
            v = self.uniqueids.get(scheme)
            if v:
                return f"{scheme}:{v}"
        for scheme, v in self.uniqueids.items():
            if v:
                return f"{scheme}:{v}"
        return None


def normalize_key(s: str) -> str:
    """题材/别名匹配键：NFKC 归一（全角→半角）+ casefold + 压缩空白。"""
    t = unicodedata.normalize("NFKC", str(s))
    return re.sub(r"\s+", " ", t).strip().casefold()


def split_genres(raw: str) -> list[str]:
    """拆分组合题材：`动作,科幻` / `Action/Adventure` / `动作、科幻`。"""
    parts = []
    for p in _GENRE_SPLIT.split(str(raw)):
        p = unicodedata.normalize("NFKC", p).strip()
        if p:
            parts.append(p)
    return parts


def decode_bytes(data: bytes) -> tuple[str, str]:
    """按探测链解码，全部失败抛 UnicodeDecodeError。"""
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig"), "utf-8-sig"
    for bom, enc in (
        (codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
        (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16"),
    ):
        if data.startswith(bom):
            return data.decode(enc), enc
    m = _RE_DECL_ENC.search(data[:200])
    chain = ([m.group(1).decode("ascii", "ignore")] if m else []) + list(_ENC_CHAIN)
    seen: set[str] = set()
    for enc in chain:
        key = enc.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            text = data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        if "<" in text:              # 防止 cp1252 解出无意义字符
            return text, enc
    raise UnicodeDecodeError("utf-8", data[:64], 0, 1, "NFO 无法用任何已知编码解码")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _find_movie(root: ET.Element) -> ET.Element:
    if _local(root.tag) == "movie":
        return root
    for el in root.iter():
        if _local(el.tag) == "movie":
            return el
    return root                       # 无 movie 包裹时把根当容器


def _fill_from_xml(info: NfoInfo, root: ET.Element) -> None:
    movie = _find_movie(root)
    for el in movie.iter():
        t = _local(el.tag)
        text = (el.text or "").strip()
        if t == "title" and info.title is None and text:
            info.title = text
        elif t == "year" and info.year is None and text:
            m = re.search(r"\d{4}", text)
            info.year = int(m.group()) if m else None
        elif t == "plot" and not info.plot and text:
            info.plot = _STRIP_TAGS.sub(" ", text).strip()
        elif t == "genre" and text:
            info.genres.extend(split_genres(text))
        elif t == "uniqueid":
            typ = (el.get("type") or "").strip().lower()
            if typ and text:
                info.uniqueids.setdefault(typ, text)
        elif t == "id":
            db = (el.get("moviedb") or "").strip().lower()
            if db and text:
                info.uniqueids.setdefault(db, text)
    # 去重保序
    info.genres = list(dict.fromkeys(info.genres))


def _fill_from_regex(info: NfoInfo, text: str) -> None:
    for m in _RE_GENRE_TAG.finditer(text):
        inner = html.unescape(_STRIP_TAGS.sub("", m.group(1)))
        info.genres.extend(split_genres(inner))
    info.genres = list(dict.fromkeys(info.genres))
    if not info.plot:
        m = _RE_PLOT_TAG.search(text)
        if m:
            info.plot = html.unescape(_STRIP_TAGS.sub(" ", m.group(1))).strip()
    if info.title is None:
        m = _RE_TITLE_TAG.search(text)
        if m:
            info.title = html.unescape(_STRIP_TAGS.sub("", m.group(1))).strip() or None
    if info.year is None:
        m = _RE_YEAR_TAG.search(text)
        if m:
            mm = re.search(r"\d{4}", m.group(1))
            info.year = int(mm.group()) if mm else None
    for m in _RE_UNIQUEID_TAG.finditer(text):
        typ, val = m.group(1).strip().lower(), m.group(2).strip()
        if typ and val:
            info.uniqueids.setdefault(typ, val)
    for m in _RE_ID_TAG.finditer(text):
        typ, val = m.group(1).strip().lower(), m.group(2).strip()
        if typ and val:
            info.uniqueids.setdefault(typ, val)


def parse_nfo_text(text: str) -> NfoInfo:
    text = text.lstrip("\ufeff").strip()
    info = NfoInfo()
    root: ET.Element | None = None
    err: str | None = None
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        err = str(exc)
    if root is None:
        m = _RE_MOVIE_BLOCK.search(text)          # 多根 / 尾部垃圾：截取 movie 块
        if m:
            try:
                root = ET.fromstring(m.group(0))
                err = None
            except ET.ParseError as exc:
                err = f"{err}; {exc}"
    if root is None:                              # 裸 & 等非法实体
        escaped = _RE_BARE_AMP.sub("&amp;", text)
        try:
            root = ET.fromstring(escaped)
            err = None
        except ET.ParseError:
            m = _RE_MOVIE_BLOCK.search(escaped)
            if m:
                try:
                    root = ET.fromstring(m.group(0))
                    err = None
                except ET.ParseError as exc:
                    err = f"{err}; {exc}"
    if root is not None:
        info.parse_mode = "xml"
        _fill_from_xml(info, root)
        if err:
            info.parse_error = f"XML 已容错恢复（{err}）"
        if not info.genres and not info.title:    # 结构怪异：正则兜底补抓
            _fill_from_regex(info, text)
    else:
        info.parse_mode = "regex"
        info.parse_error = f"XML 解析失败：{err}"
        _fill_from_regex(info, text)
    return info


def parse_nfo_file(path: Path) -> NfoInfo:
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        return NfoInfo(parse_error=f"NFO 读取失败：{exc}")
    try:
        text, enc = decode_bytes(data)
    except UnicodeDecodeError as exc:
        return NfoInfo(parse_error=f"NFO 编码无法识别：{exc}")
    info = parse_nfo_text(text)
    info.encoding = enc
    return info

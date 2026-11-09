"""影片单元扫描测试。"""
from pathlib import Path

from conftest import build_env, make_movie, nfo_xml

from app.core import scanner
from app.core.config import Config, Library, load_config


def bare_cfg(src) -> Config:
    return Config(path=Path("X:/config.toml"), source_root=Path(src),
                  libraries={"科幻": Library("科幻", Path("X:/lib/科幻"))},
                  genre_priority=[], genre_aliases={},
                  fallback_path=Path("X:/fb"))


def test_basic_dir_unit(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    make_movie(src, "Sci Fi Movie (2020)", title="Sci Fi Movie",
               genres=("科幻",), tmdb="10")
    units, notes = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1 and not notes
    u = units[0]
    assert u.kind == "dir" and u.dst_name == "Sci Fi Movie (2020)"
    assert u.title == "Sci Fi Movie" and u.year == 2020
    assert u.provider == "tmdb:10"
    assert u.file_count >= 2 and u.total_size > 0 and u.max_mtime_ns > 0
    assert u.id == "Sci Fi Movie (2020)"


def test_loose_file_unit_with_subs(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Loose Film.mkv").write_bytes(b"V" * 100)
    (src / "Loose Film.nfo").write_text(
        nfo_xml(title="Loose Film", genres=("动作",), tmdb="5"), encoding="utf-8")
    (src / "Loose Film.chs.srt").write_bytes(b"S")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    u = units[0]
    assert u.kind == "file" and u.dst_name == "Loose Film"
    assert {f[0] for f in u.files} == {"Loose Film.mkv", "Loose Film.nfo",
                                       "Loose Film.chs.srt"}


def test_multi_cd_one_unit(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    d = make_movie(src, "Big Film", title="Big Film", genres=("动作",))
    (d / "Big Film-cd2.mkv").write_bytes(b"V" * 100)
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1 and units[0].multi_cd


def test_complex_dir_excluded(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    d = src / "Pack"
    d.mkdir()
    make_movie(d, "Film A", genres=("动作",))
    make_movie(d, "Film B", genres=("恐怖",))
    units, notes = scanner.scan_source_root(bare_cfg(src))
    assert units == []
    assert any(n["level"] == "excluded" and "复合目录" in n["reason"] for n in notes)


def test_extras_sample_trailer_ignored(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    d = make_movie(src, "Film X", title="Film X", genres=("动作",))
    (d / "extras").mkdir()
    (d / "extras" / "making.mkv").write_bytes(b"V")
    (d / "sample.mkv").write_bytes(b"V")
    (d / "Film X-trailer.mkv").write_bytes(b"V")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert [v.name for v in units[0].videos] == ["Film X.mkv"]
    # 快照仍覆盖全部文件（迁移零遗漏）
    assert "extras/making.mkv" in [f[0] for f in units[0].files]


def test_bdmv_disc_unit(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    d = src / "Disc Film"
    d.mkdir()
    (d / "BDMV" / "STREAM").mkdir(parents=True)
    (d / "BDMV" / "STREAM" / "00000.m2ts").write_bytes(b"B" * 100)
    (d / "movie.nfo").write_text(nfo_xml(title="Disc Film", genres=("科幻",)),
                                 encoding="utf-8")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1 and units[0].disc


def test_nfo_priority_movie_nfo_wins(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    d = src / "My Film"
    d.mkdir()
    (d / "My Film.mkv").write_bytes(b"V" * 100)
    (d / "movie.nfo").write_text(nfo_xml(title="正主", genres=("动作",), tmdb="1"),
                                 encoding="utf-8")
    (d / "My Film.nfo").write_text(nfo_xml(title="冒牌", genres=("恐怖",), tmdb="999"),
                                   encoding="utf-8")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert units[0].title == "正主" and units[0].provider == "tmdb:1"


def test_hidden_and_junk_dirs_skipped(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for name in (".git", "@eaDir", "$RECYCLE.BIN", ".nfo-sorter-staging"):
        (src / name).mkdir()
        (src / name / "x.mkv").write_bytes(b"V")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert units == []


def test_no_video_dir_with_nfo_noted(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    d = src / "Empty Film"
    d.mkdir()
    (d / "movie.nfo").write_text(nfo_xml(), encoding="utf-8")
    units, notes = scanner.scan_source_root(bare_cfg(src))
    assert units == []
    assert any("未发现视频" in n["reason"] for n in notes)


# ---------------- 已刮削文件夹：整目录迁移回归测试 ----------------

def test_scraped_folder_supplements_not_split(tmp_path):
    """散落的花絮/预告不把已刮削文件夹误判成复合目录，且快照覆盖全部文件。"""
    src = tmp_path / "src"
    src.mkdir()
    d = make_movie(src, "Southbound Quest (2019)", title="Southbound Quest",
                   genres=("冒险",), tmdb="66")
    (d / "poster.jpg").write_bytes(b"P" * 300)
    (d / "Southbound Quest.chs.srt").write_bytes(b"S" * 100)
    (d / "Southbound Quest - Behind The Scenes.mkv").write_bytes(b"V" * 2048)
    (d / "Southbound Quest - Trailer 2.mkv").write_bytes(b"V" * 1024)
    feats = d / "featurettes"
    feats.mkdir()
    (feats / "interview.mkv").write_bytes(b"V" * 512)
    units, notes = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1 and not any(n["level"] == "excluded" for n in notes)
    u = units[0]
    assert [v.name for v in u.videos] == ["Southbound Quest.mkv"]
    rels = {f[0] for f in u.files}
    # 整目录快照：海报/字幕/散落花絮/子目录全部在内
    assert {"poster.jpg", "Southbound Quest.chs.srt",
            "Southbound Quest - Behind The Scenes.mkv",
            "Southbound Quest - Trailer 2.mkv",
            "featurettes/interview.mkv"} <= rels


def test_main_title_with_supplement_like_words_kept(tmp_path):
    """正片名含 supplement 词形（如 Shorts/Scenes）不能被误剔除。"""
    src = tmp_path / "src"
    src.mkdir()
    make_movie(src, "Shorts (2009)", title="Shorts", genres=("喜剧",), tmdb="77")
    make_movie(src, "Scenes from a Mall (1991)", title="Scenes from a Mall",
               genres=("剧情",), tmdb="78")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    ids = {u.id for u in units}
    assert ids == {"Shorts (2009)", "Scenes from a Mall (1991)"}


def test_supplement_only_dir_still_unit(tmp_path):
    """目录里只有花絮视频（无正片）时回退为单元，不静默丢目录。"""
    src = tmp_path / "src"
    src.mkdir()
    d = src / "Extras Only"
    d.mkdir()
    (d / "Making.of.mkv").write_bytes(b"V" * 100)
    (d / "movie.nfo").write_text(nfo_xml(title="Extras Only"), encoding="utf-8")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    assert [v.name for v in units[0].videos] == ["Making.of.mkv"]


def test_named_extras_subdir_excluded_from_detection(tmp_path):
    """『片名 - Extras』这类包含式子目录里的视频不参与单元识别，但随整目录迁移。"""
    src = tmp_path / "src"
    src.mkdir()
    d = make_movie(src, "Film Y", title="Film Y", genres=("动作",), tmdb="88")
    extra = d / "Film Y - Extras"
    extra.mkdir()
    (extra / "clip1.mkv").write_bytes(b"V" * 100)
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    assert [v.name for v in units[0].videos] == ["Film Y.mkv"]
    assert "Film Y - Extras/clip1.mkv" in {f[0] for f in units[0].files}


def test_loose_supplement_file_skipped(tmp_path):
    """源根下散落的 trailer.mkv 等不作为影片单元。"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "trailer.mkv").write_bytes(b"V" * 100)
    (src / "sample.mp4").write_bytes(b"V" * 100)
    make_movie(src, "Real Film", title="Real Film", genres=("动作",), tmdb="99")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert [u.id for u in units] == ["Real Film"]


def test_recovered_nfo_flags_without_warning(tmp_path):
    """容错恢复的 NFO 只挂 nfo_recovered flag，不挂 nfo_parse_warning 也不产生 warn note。"""
    cfg_path = build_env(tmp_path)
    d = make_movie(cfg_path.parent / "src", "Recovered Film",
                   title="Recovered Film", tmdb="10")
    (d / "movie.nfo").write_text(
        nfo_xml(title="Recovered Film", tmdb="10").replace(
            "</movie>", "<7mmtvid>x</7mmtvid></movie>"),
        encoding="utf-8")
    units, notes = scanner.scan_source_root(load_config(cfg_path))
    assert len(units) == 1
    assert units[0].nfo.parse_error is None and units[0].nfo.recovery
    assert units[0].flags == ["nfo_recovered"]
    warn_paths = [n.get("path") for n in notes if n.get("level") == "warn"]
    assert not warn_paths


def test_broken_nfo_keeps_warning(tmp_path):
    """硬失败的 NFO 仍挂 nfo_parse_warning，且扫描 notes 保留同 path 的 warn。"""
    cfg_path = build_env(tmp_path)
    d = make_movie(cfg_path.parent / "src", "Broken Film",
                   title="Broken Film", tmdb="10")
    (d / "movie.nfo").write_text("<movie><genre>恐怖</genre>", encoding="utf-8")
    units, notes = scanner.scan_source_root(load_config(cfg_path))
    assert len(units) == 1
    assert "nfo_parse_warning" in units[0].flags
    assert any(n.get("level") == "warn" and n.get("path") == str(units[0].nfo_path)
               for n in notes)


def test_clean_nfo_has_no_nfo_flags(tmp_path):
    """正常解析的 NFO 不挂任何 NFO 相关 flag。"""
    cfg_path = build_env(tmp_path)
    make_movie(cfg_path.parent / "src", "Clean Film",
               title="Clean Film", genres=("动作",), tmdb="10")
    units, notes = scanner.scan_source_root(load_config(cfg_path))
    assert len(units) == 1
    assert not notes
    assert units[0].flags == []

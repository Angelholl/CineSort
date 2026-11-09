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


def test_nested_container_drills_two_units(tmp_path):
    """纯容器顶层目录下钻：每个单片子目录一个独立单元，女优段=容器名
    （修订原 test_complex_dir_becomes_batch_unit，依据 D-20261110-01 §4 复议 + owner 拍板 2）。"""
    src = tmp_path / "src"
    src.mkdir()
    d = src / "Pack"
    d.mkdir()
    make_movie(d, "Film A", genres=("动作",))
    make_movie(d, "Film B", genres=("恐怖",))
    units, notes = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 2
    assert {u.id for u in units} == {"Pack/Film A", "Pack/Film B"}
    assert all(u.actress == "Pack" for u in units)
    assert all("nested" in u.flags for u in units)
    assert all(u.composite is False for u in units)
    assert all(u.kind == "dir" for u in units)
    assert not any(n["level"] == "excluded" for n in notes)
    assert any(n["level"] == "info" and "容器目录" in n["reason"] for n in notes)


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


# ---------------- 复合目录 → 整目录单元（Task-09，D-20261109-01） ----------------

def test_composite_unit_covers_whole_dir(tmp_path):
    """复合单元的快照覆盖整目录全部文件，videos 为 mains 按名排序。"""
    src = tmp_path / "src"
    src.mkdir()
    d = src / "Pack"
    d.mkdir()
    (d / "Film B.mkv").write_bytes(b"V" * 100)
    (d / "Film A.mkv").write_bytes(b"V" * 100)
    (d / "poster.jpg").write_bytes(b"P" * 300)
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    u = units[0]
    assert u.composite is True and u.file_count == 3
    rels = {f[0] for f in u.files}
    assert rels == {"Film A.mkv", "Film B.mkv", "poster.jpg"}
    assert [v.name for v in u.videos] == ["Film A.mkv", "Film B.mkv"]


def test_composite_with_nfo_still_batch(tmp_path):
    """复合目录带 NFO 时仍只产 1 个整目录单元，不拆分。"""
    src = tmp_path / "src"
    src.mkdir()
    d = src / "Pack"
    d.mkdir()
    (d / "Film A.mkv").write_bytes(b"V" * 100)
    (d / "Film B.mkv").write_bytes(b"V" * 100)
    (d / "movie.nfo").write_text(nfo_xml(title="Pack", tmdb="42"),
                                 encoding="utf-8")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    u = units[0]
    assert u.composite is True
    assert u.nfo_path is not None and u.provider == "tmdb:42"


def test_composite_no_split_on_c_variant(tmp_path):
    """同番号 -C 变体不得被拆开：仍只产 1 个 composite 单元。"""
    src = tmp_path / "src"
    src.mkdir()
    d = src / "Pack"
    d.mkdir()
    (d / "[ABC-1].mp4").write_bytes(b"V" * 100)
    (d / "[ABC-1-C].mp4").write_bytes(b"V" * 100)
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    assert units[0].composite is True


def test_supplement_dirs_not_composite(tmp_path):
    """花絮过滤回退保护：『片名 - Behind The Scenes』场景单元 composite 为 False。"""
    src = tmp_path / "src"
    src.mkdir()
    d = make_movie(src, "Film Z", title="Film Z", genres=("动作",))
    (d / "Film Z - Behind The Scenes.mkv").write_bytes(b"V" * 2048)
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    assert units[0].composite is False


# ---------------- 嵌套容器下钻与女优段（D-20261110-01，Task-01） ----------------

def test_actress_container_drills_into_movie_units(tmp_path):
    """纯容器（女优目录）下钻：内层单片目录成为独立单元，actress=容器名。"""
    src = tmp_path / "src"
    src.mkdir()
    make_movie(src / "伊藤舞雪", "CAWD-876", title="CAWD-876", tmdb="1")
    units, notes = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    u = units[0]
    assert u.id == "伊藤舞雪/CAWD-876"
    assert u.actress == "伊藤舞雪"
    assert u.dst_name == "CAWD-876"
    assert u.path == src / "伊藤舞雪" / "CAWD-876"
    assert u.provider == "tmdb:1"  # 内层 NFO 正常解析
    assert any(n["level"] == "info" and "伊藤舞雪" in n["reason"] for n in notes)


def test_drill_two_containers_actress_segments(tmp_path):
    """多个容器各自下钻，女优段逐单元等于其容器名，无复合。"""
    src = tmp_path / "src"
    src.mkdir()
    make_movie(src / "一乃あおい", "A-1")
    make_movie(src / "伊藤舞雪", "B-2")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 2
    assert {u.actress for u in units} == {"一乃あおい", "伊藤舞雪"}
    for u in units:
        assert u.actress == u.id.split("/")[0]
    assert not any(u.composite for u in units)


def test_top_level_movie_dir_not_drilled(tmp_path):
    """顶层直接躺正片视频的目录不下钻（R1），actress 保持 None。"""
    src = tmp_path / "src"
    src.mkdir()
    make_movie(src, "Flat Film")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    assert units[0].id == "Flat Film"
    assert units[0].actress is None
    assert "nested" not in units[0].flags


def test_disc_container_not_drilled(tmp_path):
    """BDMV 光盘结构是容器自身影片目录（R1），BDMV 子目录不得当内层影片目录。"""
    src = tmp_path / "src"
    src.mkdir()
    d = src / "Bluay Set"
    d.mkdir()
    (d / "BDMV" / "STREAM").mkdir(parents=True)
    (d / "BDMV" / "STREAM" / "00000.m2ts").write_bytes(b"B" * 100)
    (d / "movie.nfo").write_text(nfo_xml(title="Bluay Set"), encoding="utf-8")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    assert units[0].id == "Bluay Set"
    assert units[0].disc is True
    assert units[0].actress is None


def test_mixed_container_falls_back_to_composite(tmp_path):
    """容器内混有多 base 子目录 → 不下钻，整目录回退为复合单元（R3）。"""
    src = tmp_path / "src"
    src.mkdir()
    d = src / "混杂包"
    d.mkdir()
    make_movie(d, "好片A")
    bad = d / "坏片"
    bad.mkdir()
    (bad / "片头.mkv").write_bytes(b"V" * 100)
    (bad / "片尾.mkv").write_bytes(b"V" * 100)
    units, notes = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    u = units[0]
    assert u.composite is True and u.id == "混杂包" and u.actress is None
    assert any(n["level"] == "info" and "混合" in n["reason"] for n in notes)


def test_inner_dir_without_nfo_still_drills(tmp_path):
    """内层目录无 NFO 仍下钻：走既有兜底/人工语义，不拖死整容器。"""
    src = tmp_path / "src"
    src.mkdir()
    make_movie(src / "一乃あおい", "ABC-1", nfo=False)
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    u = units[0]
    assert u.actress == "一乃あおい"
    assert u.nfo_path is None
    assert u.flags == ["nested"]


def test_inner_dir_multi_base_blocks_drill_to_composite(tmp_path):
    """容器内一个子目录多 base → 混合，整目录回退为 composite 单元。"""
    src = tmp_path / "src"
    src.mkdir()
    d = src / "一乃あおい"
    d.mkdir()
    make_movie(d, "ABC-1")
    e = d / "XYZ-9"
    e.mkdir()
    (e / "XYZ-9.mkv").write_bytes(b"V" * 100)
    (e / "OTHER.mkv").write_bytes(b"V" * 100)
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    u = units[0]
    assert u.composite is True and u.id == "一乃あおい" and u.actress is None


def test_videoless_child_dir_warn_and_left_behind(tmp_path):
    """容器内无视频子目录与非视频文件：warn 残留、不随单元迁移。"""
    src = tmp_path / "src"
    src.mkdir()
    d = src / "一乃あおい"
    d.mkdir()
    make_movie(d, "ABC-1")
    (d / "covers").mkdir()
    (d / "covers" / "x.jpg").write_bytes(b"J")
    (d / "poster.jpg").write_bytes(b"P")
    units, notes = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1 and units[0].actress == "一乃あおい"
    warns = [n["reason"] for n in notes if n["level"] == "warn"]
    assert any("残留" in r and "covers" in r and "poster.jpg" in r for r in warns)
    rels = {f[0] for f in units[0].files}
    assert "covers/x.jpg" not in rels and "poster.jpg" not in rels


def test_unknown_actress_placeholder_kept_verbatim(tmp_path):
    """占位女优名逐字保留（含 #），不做归一。"""
    src = tmp_path / "src"
    src.mkdir()
    make_movie(src / "#未知女优", "GOV-004")
    units, _ = scanner.scan_source_root(bare_cfg(src))
    assert len(units) == 1
    assert units[0].actress == "#未知女优"

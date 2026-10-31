"""迁移原语测试（评议条件 C2：staging + 校验 + 原子改名 + 半成品识别）。"""
import pytest

from app.core import fsops


def make_tree(root) :
    d = root / "Movie (2020)"
    (d / "sub").mkdir(parents=True)
    (d / "movie.nfo").write_bytes(b"N" * 10)
    (d / "film.mkv").write_bytes(b"V" * 100)
    (d / "sub" / "note.txt").write_bytes(b"T" * 5)
    return d


def snap(d):
    return {f.relative_to(d).as_posix(): f.stat().st_size
            for f in d.rglob("*") if f.is_file()}


def test_same_drive_rename(tmp_path):
    src = make_tree(tmp_path / "src")
    dst = tmp_path / "lib" / "Movie (2020)"
    (tmp_path / "lib").mkdir()
    expected = snap(src)
    info = fsops.transfer_dir(src, dst, tmp_path / "staging", expected)
    assert info["mode"] == "rename"
    assert not src.exists()
    assert snap(dst) == expected


def test_dst_exists_refused_no_nesting(tmp_path):
    """关键回归：shutil.move 坑——目标已存在时不得把源搬进目标内部。"""
    src = make_tree(tmp_path / "src")
    dst = tmp_path / "lib" / "Movie (2020)"
    dst.mkdir(parents=True)
    with pytest.raises(fsops.TransferError):
        fsops.transfer_dir(src, dst, tmp_path / "staging", snap(src))
    assert not (dst / "Movie (2020)").exists()
    assert src.exists()


def test_cross_drive_staging_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(fsops, "split_drive",
                        lambda p: "x:" if str(p).startswith(str(tmp_path / "src"))
                        else "y:")
    src = make_tree(tmp_path / "src")
    lib = tmp_path / "lib"
    lib.mkdir()
    dst = lib / "Movie (2020)"
    staging = lib.parent / ".nfo-sorter-staging"
    expected = snap(src)
    info = fsops.transfer_dir(src, dst, staging, expected)
    assert info["mode"] == "staging"
    assert snap(dst) == expected
    assert not src.exists()
    assert fsops.find_staging_leftovers([staging]) == []


def test_incomplete_transfer_leftover_detected(tmp_path, monkeypatch):
    """故障注入：复制截断 → 必须报 IncompleteTransfer，源完好、目标未创建、
    残留带 .incomplete 标记可被识别（绝不静默当成功）。"""
    monkeypatch.setattr(fsops, "split_drive",
                        lambda p: "x:" if str(p).startswith(str(tmp_path / "src"))
                        else "y:")

    def fake_copy(s, d, retries=3):
        data = s.read_bytes()
        d.write_bytes(data[: len(data) // 2])   # 模拟复制中断（只写一半）

    monkeypatch.setattr(fsops, "_copy_with_retry", fake_copy)
    src = make_tree(tmp_path / "src")
    lib = tmp_path / "lib"
    lib.mkdir()
    dst = lib / "Movie (2020)"
    staging = lib.parent / ".nfo-sorter-staging"
    expected = snap(src)
    with pytest.raises(fsops.IncompleteTransfer):
        fsops.transfer_dir(src, dst, staging, expected)
    leftovers = fsops.find_staging_leftovers([staging])
    assert len(leftovers) == 1
    assert src.exists() and not dst.exists()
    removed = fsops.cleanup_leftovers(leftovers)
    assert removed and not leftovers[0].exists()


def test_missing_source_file_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(fsops, "split_drive",
                        lambda p: "x:" if str(p).startswith(str(tmp_path / "src"))
                        else "y:")
    src = make_tree(tmp_path / "src")
    expected = snap(src)          # 快照先于删文件
    (src / "film.mkv").unlink()
    dst = tmp_path / "lib" / "M"
    (tmp_path / "lib").mkdir()
    with pytest.raises(fsops.IncompleteTransfer):
        fsops.transfer_dir(src, dst,
                           tmp_path / "lib" / ".nfo-sorter-staging", expected)
    assert src.exists()


def test_transfer_loose_wrap(tmp_path):
    f1 = tmp_path / "src" / "A.mkv"
    f1.parent.mkdir(parents=True)
    f1.write_bytes(b"V" * 50)
    f2 = tmp_path / "src" / "A.nfo"
    f2.write_bytes(b"N")
    dst = tmp_path / "lib" / "A"
    (tmp_path / "lib").mkdir()
    fsops.transfer_loose([f1, f2], dst, tmp_path / "st",
                         {"A.mkv": 50, "A.nfo": 1})
    assert not f1.exists() and not f2.exists()
    assert (dst / "A.mkv").stat().st_size == 50


def test_transfer_loose_dst_exists_refused(tmp_path):
    f1 = tmp_path / "src" / "A.mkv"
    f1.parent.mkdir(parents=True)
    f1.write_bytes(b"V" * 50)
    dst = tmp_path / "lib" / "A"
    dst.mkdir(parents=True)
    with pytest.raises(fsops.TransferError):
        fsops.transfer_loose([f1], dst, tmp_path / "st", {"A.mkv": 50})


def test_restore_loose(tmp_path):
    d = tmp_path / "lib" / "A"
    d.mkdir(parents=True)
    (d / "A.mkv").write_bytes(b"V" * 50)
    src_dir = tmp_path / "src"
    fsops.restore_loose(d, src_dir, {"A.mkv": 50})
    assert (src_dir / "A.mkv").stat().st_size == 50
    assert not d.exists()

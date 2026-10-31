"""公共测试夹具与构造器。"""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def nfo_xml(*, title="测试电影", year=2020, genres=("动作", "科幻"), plot="一个故事",
            tmdb="123", encoding_decl=True):
    g = "".join(f"<genre>{x}</genre>" for x in genres)
    u = f'<uniqueid type="tmdb" default="true">{tmdb}</uniqueid>' if tmdb else ""
    d = "<?xml version='1.0' encoding='utf-8'?>" if encoding_decl else ""
    y = f"<year>{year}</year>" if year else ""
    return f"{d}\n<movie><title>{title}</title>{y}{g}<plot>{plot}</plot>{u}</movie>"


def make_movie(root, name, *, title=None, genres=("动作",), plot="剧情简介",
               tmdb=None, nfo=True, video="mkv", extra_files=()):
    d = Path(root) / name
    d.mkdir(parents=True, exist_ok=True)
    t = title or name
    (d / f"{t}.{video}").write_bytes(b"V" * 1024)
    if nfo:
        (d / "movie.nfo").write_text(
            nfo_xml(title=t, genres=genres, plot=plot, tmdb=tmdb), encoding="utf-8")
    for rel, data in extra_files:
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return d


def build_env(tmp_path, *, strategy="smart", overrides=None) -> Path:
    """构造完整可运行环境：源目录 + 两个媒体库 + 兜底库 + config.toml。"""
    from app.core.config import dump_config_text

    tmp_path = Path(tmp_path)
    src = tmp_path / "src"
    lib_root = tmp_path / "libs"
    scifi = lib_root / "科幻"
    action = lib_root / "动作"
    fb = tmp_path / "未分类"
    for p in (src, scifi, action, fb):
        p.mkdir(parents=True, exist_ok=True)

    cfg_dict = {
        "source_root": str(src),
        "fallback_path": str(fb),
        "strategy": strategy,
        "on_conflict": "skip",
        "staging_dir": "",
        "warn_fallback_ratio": 0.15,
        "block_fallback_ratio": 0.30,
        "plot": {"enabled": True, "min_score": 2.0, "normalize": False},
        "genre_priority": ["科幻", "动作"],
        "genre_aliases": {"Sci-Fi": "科幻", "scifi": "科幻"},
        "libraries": [
            {"name": "科幻", "path": str(scifi),
             "keywords": ["太空", "宇宙", "外星人"],
             "keywords_weighted": {"星际": 2.0}},
            {"name": "动作", "path": str(action),
             "keywords": ["枪战", "特工", "打斗"],
             "keywords_weighted": {}},
        ],
    }
    if overrides:
        cfg_dict.update(overrides)
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(dump_config_text(cfg_dict), encoding="utf-8")
    return cfg_path

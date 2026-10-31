"""生成 GUI 演示环境：demo/ 下的源目录、媒体库与 config.toml。

覆盖场景：smart 多题材摘要择优 / 单题材规则命中 / 英文题材别名 /
未映射题材摘要预判 / GBK 编码 NFO / 散装文件 / 兜底库。
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"


def nfo(title, genres, plot, tmdb, year=2020):
    g = "".join(f"<genre>{x}</genre>" for x in genres)
    return (f"<?xml version='1.0' encoding='utf-8'?>\n<movie><title>{title}</title>"
            f"<year>{year}</year>{g}<plot>{plot}</plot>"
            f"<uniqueid type=\"tmdb\" default=\"true\">{tmdb}</uniqueid></movie>")


def movie(dir_path, title, genres, plot, tmdb, year=2020, size=2048):
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / f"{title}.mkv").write_bytes(b"V" * size)
    (dir_path / "movie.nfo").write_text(nfo(title, genres, plot, tmdb, year),
                                        encoding="utf-8")
    return dir_path


def main():
    if DEMO.exists():
        shutil.rmtree(DEMO)
    src = DEMO / "src"
    libs = DEMO / "libs"
    for p in (src, libs / "科幻", libs / "动作", libs / "喜剧", DEMO / "未分类"):
        p.mkdir(parents=True)

    movie(src / "星际边缘 (2021)", "星际边缘", ["动作", "科幻", "冒险"],
          "飞船驶向深空，太空站遭遇外星人袭击，一场星际战争爆发", "1001", 2021)
    movie(src / "枪火行动 (2022)", "枪火行动", ["动作"],
          "退役特工卷入枪战漩涡", "1002", 2022)
    movie(src / "The Void (2019)", "The Void", ["Sci-Fi", "Mystery"],
          "太空飞船上的宇宙谜团", "1003", 2019)
    movie(src / "乌龙合伙人 (2020)", "乌龙合伙人", ["西部"],
          "两个搞笑拍档的爆笑乌龙冒险", "1004", 2020)
    # 已刮削文件夹：海报/字幕/散落花絮与预告/featurettes 子目录 → 整目录迁移
    d = movie(src / "Southbound Quest (2019)", "Southbound Quest", ["冒险"],
              "一次穿越丛林的长途探险", "1006", 2019)
    (d / "poster.jpg").write_bytes(b"P" * 300)
    (d / "fanart.jpg").write_bytes(b"P" * 300)
    (d / "Southbound Quest.chs.srt").write_bytes(b"S" * 100)
    (d / "Southbound Quest - Behind The Scenes.mkv").write_bytes(b"V" * 2048)
    (d / "Southbound Quest - Trailer 2.mkv").write_bytes(b"V" * 1024)
    feats = d / "featurettes"
    feats.mkdir(exist_ok=True)
    (feats / "interview.mkv").write_bytes(b"V" * 512)
    # 散装文件 + GBK 编码 NFO（题材未映射 → 走摘要预判/兜底）
    (src / "幽灵古宅.mkv").write_bytes(b"V" * 4096)
    gbk_nfo = ("<?xml version='1.0' encoding='gbk'?><movie><title>幽灵古宅</title>"
               "<year>2018</year><genre>恐怖</genre>"
               "<plot>凶宅诅咒，闹鬼连环</plot>"
               "<uniqueid type='tmdb' default='true'>1005</uniqueid></movie>")
    (src / "幽灵古宅.nfo").write_bytes(gbk_nfo.encode("gbk"))

    cfg = f"""# 演示配置（GUI 黑盒测试用，可随时删除整个 demo/ 目录）
source_root = {str(src)!r}
fallback_path = {str(DEMO / '未分类')!r}
strategy = 'smart'
on_conflict = 'skip'
warn_fallback_ratio = 0.15
block_fallback_ratio = 0.30
genre_priority = ['科幻', '动作', '喜剧']
genre_aliases = {{ 'sci-fi' = '科幻', 'scifi' = '科幻' }}

[plot]
enabled = true
min_score = 2.0
normalize = false

[[library]]
name = '科幻'
path = {str(libs / '科幻')!r}
keywords = ['太空', '宇宙', '飞船', '外星人', '星际']
keywords_weighted = {{}}

[[library]]
name = '动作'
path = {str(libs / '动作')!r}
keywords = ['枪战', '特工']
keywords_weighted = {{}}

[[library]]
name = '喜剧'
path = {str(libs / '喜剧')!r}
keywords = ['搞笑', '爆笑', '乌龙']
keywords_weighted = {{}}
"""
    (DEMO / "config.toml").write_text(cfg, encoding="utf-8")
    print(f"演示环境已生成：{DEMO}")


if __name__ == "__main__":
    main()

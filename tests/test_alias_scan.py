"""别名扫描分析测试（owner 2026-11-25 立项：未映射题材榜 + 影片名词榜）。"""

from conftest import build_env, make_movie

from app.core.alias_scan import filter_covered, name_tokens, scan_alias_candidates
from app.core.config import load_config


def test_name_tokens_filters_noise():
    toks = name_tokens("FC2-PPV-1234 [4K] 无码流出 1080p 外卖.01.mkv")
    assert "4K" not in [t.upper() for t in toks]          # 质量噪声剔除
    assert not any(t.isdigit() for t in toks)             # 纯数字剔除
    assert "无码流出" in toks and "外卖" in toks           # CJK 词保留


def test_scan_candidates_counts_genres_and_tokens(tmp_path):
    # 两部片带未映射题材「西部」「Western」，其中一部另有已映射题材「动作」
    make_movie(tmp_path / "src", "a_西部大片",
               genres=("西部", "动作"), extra_files=[("b.mkv", b"V" * 64)])
    make_movie(tmp_path / "src", "b_western_movie",
               genres=("Western",), extra_files=[("c.mkv", b"V" * 64)])
    cfg = load_config(build_env(tmp_path))
    res = scan_alias_candidates(cfg)
    assert res["unit_count"] == 2
    # 审计摘要（D-20261109-01 方案工具化）：a 片带「动作」=库名同名强命中；
    # b 片西部/Western 全未映射 → 仅 a 片强命中
    assert res["unit_with_nfo"] == 2
    assert res["unit_strong_hit"] == 1
    assert res["unit_weak_only"] == 0
    genre_map = {g: n for g, n in res["genres"]}
    # normalize_key 归组：Western 与 western 同组（展示先见原样），动作已映射不入榜
    keys = {g.casefold() for g, _ in res["genres"]}
    assert keys == {"西部", "western"}
    assert "动作" not in keys
    assert sum(genre_map.values()) == 2                   # 西部×1 + Western×1
    token_map = {t.casefold(): n for t, n in res["tokens"]}
    assert token_map.get("西部大片") == 1
    assert token_map.get("western") == 1                  # b_western_movie 归组
    assert all(n >= 1 for n in token_map.values())


def test_scan_audit_counts_strong_hit(tmp_path):
    # 库名同名题材=天然强命中（classifier.alias_map 把库名入表）：
    # 1 部带「科幻」强命中、1 部仅弱命中（弱别名表可配场景）、1 部无标签
    from app.core.config import (
        describe,
        dump_config_text,
        load_config,
        save_config_dict,
    )
    make_movie(tmp_path / "src", "强命中片", genres=("科幻",),
               extra_files=[("a.mkv", b"V" * 64)])
    make_movie(tmp_path / "src", "弱命中片", genres=("弱标签",),
               extra_files=[("b.mkv", b"V" * 64)])
    make_movie(tmp_path / "src", "无标签片", nfo=False,
               extra_files=[("c.mkv", b"V" * 64)])
    cfg_path = build_env(tmp_path, overrides={"genre_priority": []})
    cfg = load_config(cfg_path)
    res = scan_alias_candidates(cfg)
    assert res["unit_count"] == 3
    assert res["unit_with_nfo"] == 2
    assert res["unit_strong_hit"] == 1                     # 科幻=库名同名
    assert res["unit_weak_only"] == 0                      # 未配弱别名表
    assert {g for g, _ in res["genres"]} == {"弱标签"}
    _ = (dump_config_text, describe, save_config_dict)     # 保持导入最小化


def test_scan_candidates_desc_order_and_no_nfo_unit(tmp_path):
    make_movie(tmp_path / "src", "重复词甲_重复词乙",
               extra_files=[("a.mkv", b"V" * 64)])
    make_movie(tmp_path / "src", "重复词甲_另词",
               extra_files=[("b.mkv", b"V" * 64)])        # 无 NFO：只进词榜
    cfg = load_config(build_env(tmp_path))
    res = scan_alias_candidates(cfg)
    assert res["genres"] == []                            # 两部均无 NFO 题材
    token_map = {t: n for t, n in res["tokens"]}
    assert token_map["重复词甲"] == 2                      # casefold 归组计频
    top = res["tokens"][0]
    assert top[1] == 2                                    # 按次数降序


# ---------------- 已覆盖候选过滤（owner 2026-11-25：加入别名表后不再扫出） ----------------

def test_filter_covered_removes_aliased_genres():
    candidates = {"unit_count": 2,
                  "genres": [("西部", 2), ("Western", 1), ("田园", 1)],
                  "tokens": [("重复词", 3)]}
    # normalize 归一比对：大小写/全半角差异也算已覆盖
    out = filter_covered(candidates, {"western", "田园"})
    assert [g for g, _ in out["genres"]] == ["西部"]
    assert out["tokens"] == candidates["tokens"]          # 词榜不受影响
    assert out["unit_count"] == 2                          # 其余字段原样保留


# ---------------- 提升建议（D：A-1 门控的真实题材信号） ----------------

def test_promotion_candidates_filters(tmp_path):
    """播票（covered 键 / votes<bar / 悬空库 / 正常票）→ 仅正常票行返回。"""
    from conftest import seed_learned

    from app.core import learned as learned_store
    from app.core.alias_scan import promotion_candidates
    from app.core.config import load_config
    from app.core.nfo import normalize_key

    cfg = load_config(build_env(tmp_path))
    seed_learned(cfg.runtime_dir, {
        "科幻": {"动作": {"votes": 5, "manual": 5}},        # 库名已覆盖 → 剔除
        "西部": {
            "动作": {"votes": 1, "manual": 0},              # 1 票 < bar=2 → 剔除
            "科幻": {"votes": 3, "manual": 0},              # 正常票（同题材不同库）
        },
        "悬疑": {"悬空库": {"votes": 4, "manual": 1}},      # 目标库不存在 → 剔除
        "古装": {"科幻": {"votes": 3, "manual": 1}},        # 正常票
    })
    rows = promotion_candidates(learned_store.load(cfg.runtime_dir), cfg)
    # 字段与排序钉：按 (-votes, genre)，同票时题材升序
    assert rows == [
        {"genre": "古装", "key": normalize_key("古装"), "lib": "科幻",
         "votes": 3, "manual": 1},
        {"genre": "西部", "key": normalize_key("西部"), "lib": "科幻",
         "votes": 3, "manual": 0},
    ]


def test_promotion_candidates_empty_store(tmp_path):
    """learned 空 → []（当前实机 0 对的形态钉）。"""
    from app.core.alias_scan import promotion_candidates
    from app.core.config import load_config

    cfg = load_config(build_env(tmp_path))
    assert promotion_candidates({}, cfg) == []
    assert promotion_candidates({"entries": {}}, cfg) == []


def test_scan_alias_candidates_carries_promotions(tmp_path):
    """scan 透传 promotions 键；filter_covered 只动 genres、不误伤 promotions。"""
    from conftest import seed_learned

    from app.core import learned as learned_store
    from app.core.alias_scan import (
        filter_covered,
        promotion_candidates,
        scan_alias_candidates,
    )
    from app.core.config import load_config
    from app.core.nfo import normalize_key

    make_movie(tmp_path / "src", "西部片", genres=("西部",),
               extra_files=[("a.mkv", b"V" * 64)])
    cfg = load_config(build_env(tmp_path))
    seed_learned(cfg.runtime_dir, {"古装": {"科幻": {"votes": 3, "manual": 1}}})
    res = scan_alias_candidates(cfg)
    assert "promotions" in res
    expected = promotion_candidates(learned_store.load(cfg.runtime_dir), cfg)
    assert res["promotions"] == expected == [
        {"genre": "古装", "key": normalize_key("古装"), "lib": "科幻",
         "votes": 3, "manual": 1},
    ]
    out = filter_covered(res, {"西部", normalize_key("古装")})
    assert out["genres"] == []                             # 已覆盖题材从题材榜剔除
    assert out["promotions"] == res["promotions"]          # 提升建议键原样保留

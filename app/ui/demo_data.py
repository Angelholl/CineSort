"""演示与截图用假数据：字段口径对齐 planner 的真实 unit（D-20261102-01）。

供 `python -m app.ui.main_window --demo` 生成样式走查/验收截图环境。
必须与 app/core/planner.py 产出的 unit 同构，否则演示模式会掩盖
只有真数据才暴露的问题（例如 confidence 是字符串不是数值）。
"""
from __future__ import annotations

import random

LIBS = ["科幻", "动作", "恐怖", "喜剧", "剧情", "动画", "纪录", "犯罪"]
GENRES = ["科幻", "动作", "恐怖", "喜剧", "剧情", "动画", "纪录", "犯罪", "悬疑"]
TITLE_A = ["太空", "深海", "午夜", "最后的", "第七", "黑色", "孤独", "狂野", "沉默的",
           "红色", "隐形", "二手", "长安", "夜航", "荒原", "边境", "雾港", "寒夜"]
TITLE_B = ["战争", "回声", "列车", "档案", "编年史", "委托", "遗产", "往事",
           "协议", "计划", "纪元", "迷城", "追缉", "名单", "回声"]
EN_TITLES = ["Silent Orbit", "The Last Ledger", "Nightfall Protocol", "Iron Meridian",
             "Paper Kingdoms", "Cold Static", "Quiet Harbor", "Nine Tails",
             "The Understudy", "Bone Cathedral", "Slow Thunder", "Glass Republic"]

_EVIDENCE = {
    "rule": ["NFO <genre> 命中「{g}」→ 库「{lib}」", "别名表：Sci-Fi → 科幻",
             "genre_priority 首位候选"],
    "plot": ["摘要关键词「太空」×2 ×权重1.0 = 2.0 ≥ min_score 2.0",
             "题材未映射，改用摘要预判"],
    "learned": ["自学习：题材「{g}」累计 3 票 → 库「{lib}」",
                "你于会话 7a3f9c21 人工改判（记 2 票）"],
    "fallback": ["题材全部未映射且摘要评分不足 → 兜底库",
                 "兜底占比 18.4% 超过 warn 阈值 15%"],
}
_LEVELS = ("rule", "plot", "learned", "fallback")
_STATUSES = ("ready", "conflict_name", "already_placed", "multi_version",
             "incomplete_leftover", "applied")


def fake_units(n: int, seed: int = 20261102) -> list[dict]:
    """生成 n 条贴近真实结构的计划单元（默认勾选规则复刻 planner）。"""
    rnd = random.Random(seed)
    units: list[dict] = []
    used: set[str] = set()
    for _ in range(n):
        while True:
            if rnd.random() < 0.45:
                title = rnd.choice(TITLE_A) + rnd.choice(TITLE_B)
            else:
                title = rnd.choice(EN_TITLES)
            year = rnd.randint(1972, 2026)
            name = f"{title} ({year})"
            if name not in used:
                used.add(name)
                break
        level = rnd.choices(_LEVELS, weights=[62, 17, 12, 9])[0]
        status = rnd.choices(_STATUSES, weights=[80, 4, 5, 4, 2, 5])[0]
        if level == "fallback":
            lib, lib_root = "兜底库", r"I:\媒体库\未分类"
        else:
            lib = rnd.choice(LIBS)
            lib_root = rf"I:\媒体库\{lib}"
        genre = lib if lib != "兜底库" else rnd.choice(GENRES)
        conf = {"rule": "high", "learned": "medium",
                "plot": rnd.choice(["medium", "low"]), "fallback": "low"}[level]
        files = rnd.randint(1, 14)
        # 与 planner 产物同构：部分行带女优段（「库\女优\影片」三层布局）
        actress = rnd.choice(["篠田ゆあ", "伊藤舞雪", "#未知女优", None, None])
        src = rf"I:\待整理\{actress}\{name}" if actress else rf"I:\待整理\{name}"
        dst_dir = rf"{lib_root}\{actress}\{name}" if actress else rf"{lib_root}\{name}"
        units.append({
            "id": name,
            "kind": "dir",
            "label": name,
            "title": title,
            "year": year,
            "src": src,
            "dst_dir": dst_dir,
            "dst_name": name,
            "actress": actress,
            "target_lib": lib,
            "target_root": lib_root,
            "level": level,
            "confidence": conf,
            "genres": (genre,),
            "evidence": [e.format(g=genre, lib=lib) for e in
                         rnd.sample(_EVIDENCE[level], rnd.randint(1, 2))],
            "status": status,
            "notes": [],
            "default_selected": status == "ready" and (
                level == "rule" or (level == "learned" and conf == "medium")),
            "file_count": files,
            "total_size": rnd.randint(700, 42_000) * 1_048_576,
        })
    return units

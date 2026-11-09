# 卡 C4：弱标签裁决语义 + default_selected 门（计划 Task-05）

规格：`docs/design/2026-11-09-classification-quality.md` §3.2、§3.3　计划：`docs/plans/2026-11-09-classification-quality.md` Task-05
决策依据：`docs/decision-log.md` D-20261109-01　前置：Task-04 已合入（`dfddf1a`，`Config.weak_genre_aliases` 已存在）
测试基线：**219 passed**（本卡净增 7 新测试 + 1 处授权修订，收口应 226）

## 一、本卡要解决的问题（不得重新调查）

实测 30 例审计里有两类错判是"标签与标题语义冲突"（`ABF-312` 标题 NTR 却因 `护士` 标签进医护；`JUR-555` 标题不倫NTR 却因 `女同性戀` 标签进百合）。现状 `rule_pick` 只要有一个标签能映射到库就给 `confidence="high"`，planner 又把 rule/high 单元 `default_selected=True` —— 可疑命中会被默认勾选、批量错位入库。

本卡建立"弱标签"这一档：**弱命中永不与强命中同台竞争；唯一命中且来自弱标签 → 低置信 → 默认不勾选**。规格 §3.3 已写明诚实边界：本特性不自动修对任何一例错判，只把可疑命中从"高置信直接进库"降为"低置信人工复核"。卡面测试必须钉住这个边界，不得测成"自动改判成功"。

## 二、改动文件（只许改这五个）

| 文件 | 动作 | 落点 |
|---|---|---|
| `app/core/classifier.py` | Modify | :43 之后新增 `weak_alias_map`；`map_genres`（:46-58）改 wrapper；新增 `map_genres_ex`；`classify`（:100）取三段；`rule_pick`（:151-176）候选集与置信改造 |
| `app/core/planner.py` | Modify | :132-134 `default_selected` 一行 |
| `tests/test_classifier.py` | Test | 末尾追加 6 个 |
| `tests/test_planner.py` | Test | 末尾追加 1 个 |
| `tests/test_viewmodel.py` | **修订（全卡唯一授权改动点）** | `make_unit` 的 :24-26 复刻规则补 `and conf != "low"`；:22 docstring 补一句"弱规则（low）不默认勾选" |

`tests/test_viewmodel.py` 现有 27 个测试**除上述复刻规则那一处外，0 删 0 改**；其余现有测试一律 0 删 0 改。

## 三、改法（照抄执行，不得自行变更设计）

1. `classifier.py:43` 之后新增：

```python
def weak_alias_map(cfg: Config) -> dict[str, str]:
    """弱别名归一键 → 库名（弱信号：唯一命中时降级，永不压过强命中）。"""
    return {normalize_key(k): v for k, v in cfg.weak_genre_aliases.items()
            if v in cfg.libraries}
```

2. 新增 `map_genres_ex(cfg, genres) -> tuple[list[str], list[str], list[str]]`，返回 `(强命中库, 弱命中库, 未映射题材)`，保序去重；**同名键强表胜出**（先查 `alias_map` 命中即算强，不再查 `weak_alias_map`）。`map_genres` 改为 `s, _w, u = map_genres_ex(cfg, genres); return s, u`——签名与返回形状不变（`planner.py:82` 的 unmapped 用法零改动）。
3. `classify`（:100）改为 `mapped_s, mapped_w, unmapped = map_genres_ex(cfg, genres)`，并令 `mapped = mapped_s + [w for w in mapped_w if w not in mapped_s]`（供既有证据/统计分支继续用）。
4. `rule_pick`（:151-176）：`candidates = mapped_s or mapped_w`；`weak_only = bool(mapped_w) and not mapped_s`；winner 仍在 candidates 内用**既有 min 键**（`_rank` / 票数 / 声明序，:154-155 不改算法，只把 `mapped` 换成 `candidates`）；置信改 `conf = "low" if weak_only else "high"`；`weak_only` 时 reason 追加 `（弱标签）`、evidence 追加一行 `弱标签『<触发题材>』→ <winner>（弱信号，默认不勾选）`。`smart` 多候选择优分支（:186-191）判定仍用 `len(mapped) > 1`，强弱并存时行为与现状逐字节一致。
5. `planner.py:132-134` 改为：

```python
            "default_selected": status == READY and (
                (dec.level == "rule" and dec.confidence != "low")
                or (dec.level == "learned" and dec.confidence == "medium")),
```

## 四、先红后绿的回归测试（7 新 + 1 修订）

`tests/test_classifier.py` 末尾 6 个（cfg 用 `build_env`，overrides 注入 `genre_aliases` / `weak_genre_aliases` / `genre_priority`）：

| 测试名 | 输入 | 断言（逐字段钉，不许只钉 target） |
|---|---|---|
| `test_weak_only_single_hit_low_confidence` | genres=`("护士",)`，weak `护士→动作` | `level=="rule"`；`confidence=="low"`；`target=="动作"`；evidence 存在含 `"弱标签"` 的行；reason 含 `"（弱标签）"` |
| `test_weak_cannot_beat_strong` | genres=`("护士","Sci-Fi")`，weak `护士→动作`、强 `Sci-Fi→科幻`，`genre_priority=["动作","科幻"]`（动作在前） | `target=="科幻"`（强胜出，优先级顺序不得翻盘）；`confidence=="high"` |
| `test_multiple_weak_candidates_use_priority` | weak `护士→动作`、`空姐→科幻`，两题材都在 genres，`genre_priority=["科幻","动作"]` | `target=="科幻"`（弱候选内部按优先级裁决）；`confidence=="low"` |
| `test_strong_only_unchanged` | 仅强别名唯一命中（`build_env` 默认配置） | `confidence=="high"`；evidence **无**含"弱标签"的行；reason 无"（弱标签）"（回归钉：现状不变） |
| `test_same_lib_strong_and_weak_not_demoted` | 强 `Sci-Fi→科幻` + 弱 `sf2→科幻`，genres=`("Sci-Fi","sf2")` | `confidence=="high"`（同库强弱并存视为强） |
| `test_map_genres_ex_shapes` | 混合强/弱/未映射 genres | `(strong, weak, unmapped)` 三段内容与顺序逐一相等；且 `map_genres(...)` 返回 `(strong, unmapped)` 与旧契约逐字段一致 |

`tests/test_planner.py` 末尾 1 个：

| 测试名 | 构造 | 断言 |
|---|---|---|
| `test_plan_weak_rule_not_selected` | weak-only 单元走完整 `build_plan` | `level=="rule"`、`confidence=="low"`、`default_selected is False`、`stats` 里该单元计入 ready 的 rule 而非 fallback |

修订（唯一授权）：`tests/test_viewmodel.py` 的 `make_unit` 复刻规则补 `and conf != "low"`，docstring 补"弱规则（low）不默认勾选"。

## 五、验收命令（以下命令均在项目根目录执行，cwd 即仓库根）

1. 红：`python -m pytest tests/test_classifier.py tests/test_planner.py -q`（新测试先失败）
2. 绿：`python -m ruff check app/core/classifier.py app/core/planner.py tests/test_classifier.py tests/test_planner.py tests/test_viewmodel.py` 必须 **0 项**（**五个文件全列，含 tests**）；`python -m pytest tests/test_classifier.py tests/test_planner.py tests/test_viewmodel.py -q` 全绿（**实测现有 14 + 7 + 27 = 48**，加 7 新 = **55**；test_planner 已是 7 而非 6，因卡 C1 已净增 1）
3. 全量不回归：`python -m pytest tests -q` → **0 failed，用例总数 = 226**（219 + 7）
4. 修订面自查（必须贴输出）：`git diff --stat HEAD -- tests/test_viewmodel.py` 与 `git diff HEAD -- tests/test_viewmodel.py` → 只允许出现 `make_unit` 复刻规则那一行 + docstring 一行，不得有其他测试被改/被删
5. 真实数据只读自检（不得写盘）：`py -3.12 -c "import sys;sys.path.insert(0,'.');from app.core.config import load_config;cfg=load_config(r'D:/CineSort-beta/CineSort/config.toml');print('weak_loaded=',cfg.weak_genre_aliases)"` → 期望 `weak_loaded= {}`（实机配置尚未注入弱表，本卡不改用户配置）

## 六、约束

- 只改卡面五个文件；除 §4 那处 `test_viewmodel.make_unit` 修订外，现有测试 0 删 0 改；不得为变绿放宽断言、不得删断言字段。
- 不得改 `genre_aliases`（强表）语义、不得改 `_rank`/票数/声明序算法、不得改 `smart` 多候选择优分支的判定条件。
- 不得写 `D:\CineSort\config.toml`、`D:\CineSort-beta\CineSort\config.toml`、`config.example.toml`（已知坏文件）或 `E:\已刮削` 下任何文件。
- 不得联网。卡外问题即停，在回报里单列，不得顺手改。
- 读大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 `pointerize` / `read_pointer` / `read_diff_only`，禁止整读文件全文。
- 完成后 `git commit`（Conventional 前缀 + 中文描述，正文 `verify:` 写实测结果与 `Refs: D-20261109-01`），**不得 push**，不得 `git add -A`、不得 `--no-verify`。

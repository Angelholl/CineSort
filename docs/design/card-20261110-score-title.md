# 卡 C7：`score_title` 标题弱评分入决策链（计划 Task-08，特性 D 核心）

规格：`docs/design/2026-11-09-classification-quality.md` §5.1-§5.5　计划：`docs/plans/2026-11-09-classification-quality.md` Task-08
决策依据：`docs/decision-log.md` D-20261109-01　前置：Task-05（`5e95334`）、Task-07（`9ae12b2`）已合入
测试基线：**238 passed**（本卡净增 10：classifier 9 + viewmodel 1，收口应 248）；全仓 ruff 基线 **10 项**（只降不增）

## 一、本卡要解决的问题

实测审计里有一类错判**只有标题文本能提供线索**：`SDJS-348` 标题含 `マジックミラー号`，应进 `魔镜号` 库，但 NFO 标签里根本没有这个词；`ABF-312`（标题 NTR）、`JUR-555`（标题不倫NTR）也属于"标签与标题冲突"。另外 147 个复合目录视频**完全没有 NFO**，唯一文本源就是文件名标题。

本卡加一条**最后的弱信号**：在规则/自学习/摘要都不成立、即将落兜底之前，用"别名 ∪ 弱别名 ∪ 库名"词表对标题做子串计数；达标则给 `level="title"`、`confidence="low"`、**默认不勾选**的建议，否则才落兜底。

**硬边界（规格 §5.3）**：强/弱规则命中、plot 摘要达标、learned 命中三条路径**全部不经过 title**。title 只替换"兜底"这一档，绝不越位改写已有判定。

## 二、改动文件（只许改这四个）

| 文件 | 动作 | 落点 |
|---|---|---|
| `app/core/classifier.py` | Modify | :20 附近 `LEVEL_TITLE`；`LEVEL_LABELS`（:23-24）；`score_plot`（:85）之后新增 `score_title`；`classify`（:116 之后接 title_scoring、`fallback` :119-132 改造、两处调用点 :183/:201） |
| `app/ui/viewmodel.py` | Modify | `LEVEL_FILTERS`（:21）、`LEVEL_BADGES`（:26-31） |
| `tests/test_classifier.py` | Test | 末尾追加 9 个 |
| `tests/test_viewmodel.py` | Test | 末尾追加 1 个 |

不动 `planner.py`、`scanner.py`、`config.py`、`config_tab.py`、`plan_tab.py`。现有测试 0 删 0 改。

## 三、改法（签名、无长度归一、命中明细格式三点不得偏离；其余结构可微调）

1. `LEVEL_TITLE = "title"`；`LEVEL_LABELS` 加 `"title": "标题预判"`。
2. `score_plot` 之后新增 `score_title(text, cfg) -> list[tuple[str, float, list[str]]]`，语义：词表 = 各库名 + 强别名键 + 弱别名键（归一键 → 库名，同名先出现者胜出），**键长 < 2 一律跳过**；对归一后的标题做计数；**不做 `len**0.5` 长度归一**（短文本会被放大）；同库命中聚合求和；按 `(-分, 库名)` 降序。
3. **重叠词不得重复计分（主审新增要求）**：词表里存在互为子串的键时（实测真实存在：库名 `美女` 是标签词 `美少女` 的子串），`美少女` 命中一次**只能给一个库**计分——最长键优先、命中跨度被消费掉，短键不得在同一跨度上重复计分。理由：否则每个"美少女"标题都会给 `美女` 库凑一票噪声建议。**这条必须用测试钉死，不许把测试写成"接受重复计分"。**
4. `classify` 内 `scoring` 之后接：`title_scoring = score_title(<标题文本>, cfg) if cfg.title.enabled else []`，标题文本 = NFO title 与单元 title 去空拼接。
5. `fallback(reason, title_ok=True)`：当 `title_ok and cfg.title.enabled and title_scoring and title_scoring[0][1] >= cfg.title.min_score` 时返回 title_pick 而非兜底。title_pick 内联构造：

```python
Decision(name, str(cfg.libraries[name].path), LEVEL_TITLE,
         f"标题弱命中『{name}』{sc:g} 分（低置信，默认不勾选）",
         [f"标题命中：{h}" for h in hits[:8]], "low")
```

两处原 `fallback(...)` 调用点（:183、:201）保持"最后手段"语义不变。
6. `viewmodel.py`：`LEVEL_FILTERS` 追加 `"title"`；`LEVEL_BADGES` 加 `"title": ("标题预判", "plot")`（复用 plot 现有色值，**不得新增颜色**）。

## 四、先红后绿的回归测试（10 个）

`tests/test_classifier.py` 末尾 9 个：

| 测试名 | 构造 | 断言（逐字段钉） |
|---|---|---|
| `test_score_title_counts_alias_hits` | 建库名 `科幻`，弱别名 `マジックミラー号→科幻`，标题含该词 | 首项库为 `科幻`、分 ≥ 1.0、hits 含 `词×次数` 格式 |
| `test_score_title_no_length_normalization` | 20 字短标题命中 1 次 | 分**恰为 1.0**（不被长度归一放大） |
| `test_score_title_skips_short_keys` | 词表含长度 1 的键（库名或别名 `P`） | 该键不产生命中 |
| `test_score_title_no_double_count_on_overlap` | 词表同时含 `美女`（库名）与 `美少女`（别名→另一库），标题只含 `美少女` | 两库总分之和 == 1.0，且 `美女` 库不得因同一跨度得分（**主审新增的重叠钉**） |
| `test_title_pick_no_genres` | 无 genres、无 plot、标题含别名词 | `level=="title"`、`confidence=="low"`、reason 含 `"标题"`、`default_selected` 语义为不选（confidence low） |
| `test_title_pick_after_soft_learned` | 无 genres + 存在 votes=1 的 learned 软建议 + 标题命中 | `level=="learned"`（title 不越位） |
| `test_title_never_overrides_rule` | 强规则命中 + 标题含别的库的词 | `target` == 规则库；evidence **无**含 `"标题命中"` 的行 |
| `test_title_disabled_by_config` | `title.enabled=False`，同输入 | `level=="fallback"` |
| `test_title_evidence_label_distinct` | 一个 plot 单元 + 一个 title 单元 | plot 的 evidence 前缀是 `"摘要命中"`、title 的是 `"标题命中"`，两者不得混用 |

`tests/test_viewmodel.py` 末尾 1 个：`test_title_badge_and_filter` —— `LEVEL_BADGES["title"]` 存在且色值沿用 plot 那一档；`set_filter("title")` 后 rows 只含 title 单元。

## 五、验收命令（以下命令均在项目根目录执行，cwd 即仓库根）

1. 红：`python -m pytest tests/test_classifier.py tests/test_viewmodel.py -q`（10 个新测试先失败）
2. 绿：`python -m ruff check app/core/classifier.py app/ui/viewmodel.py tests/test_classifier.py tests/test_viewmodel.py` 必须 **0 项**（四个文件全列）；`python -m pytest tests/test_classifier.py tests/test_viewmodel.py -q` 全绿（**实测现有 20 + 27 = 47**，加 10 新 = **57**）
3. 全量不回归：`python -m pytest tests -q` → **0 failed，用例总数 = 248**（238 + 10）
4. 全仓 lint 不增：`python -m ruff check . 2>&1 | grep "^Found"` → 必须 **≤ 10 errors**
5. 真实数据只读自检（不得写盘）：`py -3.12 -c "import sys;sys.path.insert(0,'.');from app.core.config import load_config;from app.core.scanner import scan_source_root;from app.core.classifier import classify;cfg=load_config(r'D:/CineSort-beta/CineSort/config.toml');us,_=scan_source_root(cfg);d=[classify(u,cfg) for u in us];import collections;print(collections.Counter(x.level for x in d))"` → 期望 `rule` 仍为 95 左右、`fallback` 由 2 减少或持平、出现 `title` 计数；**必须把原样输出贴进回报**，不许只说"符合预期"

## 六、约束

- 只改卡面四个文件；现有测试 0 删 0 改；不得为变绿放宽断言、不得删断言字段。
- 不得改 `score_plot`、`map_genres`/`map_genres_ex`、`rule_pick`、`learned_pick`、`plot_pick` 的任何既有行为；title 只能出现在"即将兜底"之前那一档。
- 不得新增颜色常量；不得改 `planner.py` 的 `default_selected` 规则（low 已被上一卡排除）。
- 不得写 `D:\CineSort\config.toml`、`D:\CineSort-beta\CineSort\config.toml`、`config.example.toml`（已知坏文件）或 `E:\已刮削` 下任何文件；不得联网。
- 第 3 条（重叠词不重复计分）与第 5 节第 5 条（真实数据自检）若做不到，**如实回报并停在卡外单列**，不许静默降级测试。
- 卡外问题即停，在回报里单列，不得顺手改。
- 读大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 `pointerize` / `read_pointer` / `read_diff_only`，禁止整读文件全文。
- 完成后 `git commit`（Conventional 前缀 + 中文描述，正文 `verify:` 写实测结果与 `Refs: D-20261109-01`），**不得 push**，不得 `git add -A`、不得 `--no-verify`。

# Task-02 卡面：A-2 自学习只作建议 + 票数退出多候选择优（涉 GUI 文案）

- 决策真值：`docs/decision-log.md` **D-20261125-05** ｜ 实施计划：`docs/plans/2026-11-25-classify-adjustments.md` Task-02
- 卡状态：待执行 ｜ 依赖：Task-01（已收口，量尺 `tools/replay_metrics.py` 可用）

## 一、根因与目标

owner 拍板推翻 D-20261101-03 的自动生效层：classify 永不因票数自动生效/择优；人工改判不再记题材票（人工信号移入会话留痕，Task-04 落地）；自学习建议全面低置信；GUI/README 文案同步。票数退出多候选择优**由代码保证**（破平手键删 votes 项），不依赖优先级表填全。

## 二、改动文件与落点（行号为写卡时锚，实施前 grep 复核，行号漂移以函数/锚文本定位）

- `app/core/classifier.py`：
  - `:15` import 去 votes_for；
  - `:164` min_votes 变量退役；
  - `:166-181` auto/soft 分流合并为 soft_hits 单路；
  - `:210` 兜底建议文案；
  - `:222-229` learned_pick 置信恒 "low"；
  - `:234-237` 破平手键删 votes（`(优先级位次, -票数, 声明顺序)` → `(优先级位次, 声明顺序)`）；
  - `:252-254` 删「历史倾向」证据块；
  - `:282-289` 未映射路径序=摘要→建议→兜底，auto_hits 分支删除。
- `app/core/planner.py:153-155`：default_selected 删 learned 子句 → `(dec.level == "rule" and dec.confidence != "low")`。
- `app/core/learned.py:43-60`：`record` 权重 `+= 2 if manual else 1` → `+= 1`（manual 仍计数）；模块 docstring 改「一律 +1 票，仅作建议」。
- `app/core/jobs.py:261-269`：`if cfg.learning.enabled:` 块内 record 调用改为**跳过人工改判单元**：`if u["id"] in overrides: continue`；其余确认单元 `manual=False` 记 1 票（A-1 落地前窗口期语义）。
- GUI 文案四处：`app/ui/plan_tab.py:295` hint → 「改判不再记自学习票；「执行选中」按改判后的目标库搬运。」；`app/ui/config_tab.py:150-154` tooltip 与 `:236` 标签 → 「自学习映射（仅作建议）」口径。
- `README.md:46`、`:114-115`：自学习段改为建议口径（不再「自动生效/默认勾选」）。
- `tests/test_viewmodel.py:15-26` make_unit 的 default_selected 缺省复刻删 learned 分支（原地改写，随 planner 同步）。

**Interfaces**：Consumes=`learned.best_for`（不变）、`learned.votes_for` 保留（量尺消费，classifier 不再 import）；Produces=classify 未映射路径输出建议 Decision（level=learned、confidence 恒 "low"），plan 单元 learned 级 default_selected 恒 False。

## 三、先红后绿回归测试（8 项 = 改写 5 + 新增 3，基线只增不减）

| 测试名（文件） | 断言 |
|---|---|
| `test_record_manual_counts_one_vote`（test_learned.py，改写 `test_record_votes_and_manual_weight`） | manual=False 后 manual=True 两次 record → votes==2、manual==1 |
| `test_learned_never_auto_effective_at_any_votes`（test_learned.py，改写 `test_learned_auto_hit_threshold`） | 2 票达标 → classify → level=="learned" 且 confidence=="low" 且 target=="武侠" |
| `test_multi_candidate_ignores_votes_decl_order_decides`（test_learned.py，改写 `test_smart_tie_break_by_votes_among_unprioritized`） | 两库未列入表、喜剧 4 票 → 胜者=武侠（声明顺序），evidence 无「历史倾向」 |
| `test_plan_learned_level_never_default_selected`（test_planner.py，新） | 播 2 票人工票 → build_plan 单元 level=="learned"、default_selected is False、status=="ready" |
| `test_apply_manual_override_records_no_votes`（test_flow.py，新） | 独有题材「戏曲」单元改判到科幻并 apply → learned.json 无「戏曲」键；同批无改判的确认单元仍记 1 票（窗口期语义，Task-07 再改写归零） |
| `test_rule_evidence_no_votes_lines`（test_classifier.py，新） | 多候选+票数在场 → evidence 不含「历史倾向」且不含「票」行 |
| `test_replay_winner_basis_no_votes_after_a2`（test_replay_metrics.py，改写 Task-01 的 `test_replay_winner_basis_detects_votes`） | 同种子 → winner_basis["votes"] == 0 且 decl_order ≥ 1 |
| `test_replay_auto_effective_zero_after_a2`（test_replay_metrics.py，改写 Task-01 的 `test_replay_auto_effective_matches_plan`） | 2 票人工票 → auto_effective_units == 0 |

语义兼容保留项（跑绿即证，不减量）：test_learned.py:58-65、:82-88；test_classifier.py:282-290；test_flow.py:71-76。

## 四、验收命令（以下命令均在项目根目录执行；测试解释器用 G:/python/python.exe）

1. 按表改写+新增 8 项测试（红）：`G:/python/python.exe -m pytest tests/test_learned.py tests/test_classifier.py tests/test_planner.py tests/test_flow.py tests/test_replay_metrics.py -q` → 表内 8 项 fail，其余绿。
2. 最小实现按落点清单逐处修改。
3. 跑绿定向：同步骤 1 命令 → all passed。
4. GUI 文案四处（plan_tab/config_tab×2/README×2 行段）替换。
5. `G:/python/python.exe -m ruff check <全部改动文件>` → 0 项；`G:/python/python.exe -m mypy app` → errors ≤149（INTERNAL ERROR 先清 .mypy_cache）。
6. 全量：`G:/python/python.exe -m pytest -q` → **385→388 passed**（实测前基线 385=Task-01 收口数；计划账户 373→376 净增 +3）。
7. 离屏复验：`QT_QPA_PLATFORM=offscreen G:/python/python.exe -m pytest tests/test_config_tab.py tests/test_plan_tab.py -q` → all passed（钉旧文案者原地改写，不减量）。
8. 重放核对：`G:/python/python.exe tools/replay_metrics.py config.toml` → **自动生效 0、winner_basis 无 votes**；默认勾选数较 Task-01 基线（181）的变动记录进 verify:。

## 五、提交与约束

- commit：`feat(classify): A-2 自学习只作建议、票数退出多候选择优（owner 拍板）`；正文 `verify:` 全量 385→388 + 四指标前后值 + 「GUI 已验证（离屏）」+ `Refs: D-20261125-05`。中文提交信息写 UTF-8 文件后 `git commit -F <文件>`。
- 显式列文件 add；永不 `git add -A`、永不 `--no-verify`；只 commit 不 push。
- 同工作树 ≤1 卡（本卡独占执行）；禁触 `app/__init__.py`、`installer/installer.iss`（他人未提交改动，勿动勿收）。
- GUI 按离屏协议（viewmodel 级零 Qt 单测 + offscreen widget 驱动），不引入新依赖；实机黑盒留统一复测轮。
- learned 数据安全：本卡只改 record 权重与分流路径，不删不改票目存量。
- 执行纪律：卡面外发现的问题只记录回报，不擅自扩范围。

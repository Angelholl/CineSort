# Task-01 卡面：离线重放四指标量尺工具（无 GUI）

- 决策真值：`docs/decision-log.md` **D-20261125-05** ｜ 实施计划：`docs/plans/2026-11-25-classify-adjustments.md` Task-01
- 卡状态：待执行 ｜ 依赖：无（十卡串行首卡）

## 一、根因与目标

后续每卡验收需要统一量尺与可比数字。本卡交付四指标离线重放工具 `tools/replay_metrics.py`，对给定 config 跑一遍扫描→分类→建计划（**全程不写 plan.json / learned.json**，build_plan 不 save，工具内不得有任何 save 调用），输出五键结果。

## 二、改动文件与改法

### 1. 新增 `tools/replay_metrics.py`

- 模块级纯函数 + CLI 入口；文件顶部 sys.path 注入 PROJECT（同 `tools/measure_no_nfo.py` 范式）。
- Consumes：`app.core.config.load_config`、`app.core.scanner.scan_source_root`、`app.core.planner.build_plan`（不 save）、`app.core.classifier.map_genres_ex / score_plot / _rank`（私有 `_rank` 导入，文件内注释说明允许）、`app.core.learned.load / votes_for`、`app.core.journal.read_entries / list_sessions`。
- Produces：`replay_metrics(cfg) -> dict`（五键：`auto_effective_units`、`winner_basis`、`default_selected`、`vote_closure_inconsistencies`、`top_target_share`）；`main(argv) -> int`。
- CLI：`python tools/replay_metrics.py <config.toml> [--strategy smart|smart_weighted|...] [--json]`；`--strategy` 覆盖 cfg.strategy 后再 build_plan（what-if 对比，不改配置文件）；`--json` 机器可读输出；默认打印中文报表。

**票数闭合算法（钉死）**：读 journals——undo 会话（header meta.undoes）取其 done unit_id 集 = 回滚排除集；apply 会话按 header ts 升序，done 记录**含 title 且含 manual 字段**（留痕上线后）且 unit_id 未被回滚、且能按 unit_id（退 src_dir）对账当前冻结 plan 单元 → 取该单元 genres；`expected[(normalize_key(g), target_lib)] += 0 if manual else 1`。触及对 = expected>0 或存在 manual 触及；不一致对 = 触及对中 learned.json 实际票数 ≠ expected。未被留痕后会话触及的历史票目不计（`legacy_pairs` 另行输出不判错）。

**胜出依据算法（钉死）**：对 `len(set(强命中∪弱命中去重))>1` 的单元——level=plot → `plot`；否则分别计算无票键 `min(cand, key=(*_rank, decl))` 与带票键 `min(cand, key=(*_rank, -votes, decl))`：实际目标≠无票键且=带票键 → `votes`；实际目标=无票键且胜者表内位次并列 → `decl_order`，否则 `priority`；兜底 `unexpected`。

### 2. 新增 `tests/test_replay_metrics.py`

importlib 挂载范式同 `tests/test_measure_no_nfo.py:8-14`。测试表（先红后绿）：

| 测试名 | 输入 | 断言 |
|---|---|---|
| `test_replay_writes_nothing` | build_env+make_movie×2，无 plan.json 起跑 | 跑前后 learned.json/plan.json 均不存在或逐字节相同 |
| `test_replay_auto_effective_matches_plan` | learned 播 2 票人工票（`record(genres=["戏曲"], "科幻", manual=True)`），min_votes=2 | 输出 auto_effective_units == 1 == plan 中 learned 级 default_selected 数 |
| `test_replay_winner_basis_detects_votes` | 两库均未列入优先级表，learned 给喜剧 4 票 | 输出 winner_basis["votes"] ≥ 1（当前代码语义；Task-02 改写为 ==0） |
| `test_replay_default_selected_count` | 常规 2 库配置 | 输出 == plan["units"] 中 default_selected 计数 |
| `test_replay_closure_flags_manual_leak` | 手工造 post-留痕 done 记录（manual=true、title/genres 可对账）+ learned.json 同对有票 | vote_closure_inconsistencies == 1；`legacy_pairs` 分开计数 |
| `test_replay_strategy_override` | 同环境 `--strategy genre_only` | plan 全部 rule/fallback，无 plot 级（覆盖生效且未写配置文件） |

## 三、验收命令（以下命令均在项目根目录执行；测试解释器用 G:/python/python.exe，默认 python 无 pytest）

1. 先红：`G:/python/python.exe -m pytest tests/test_replay_metrics.py -q` → 6 failed（模块不存在）。
2. 实现后跑绿：同命令 → `6 passed`。
3. `G:/python/python.exe -m ruff check tools/replay_metrics.py tests/test_replay_metrics.py` → 0 项；`G:/python/python.exe -m mypy tools/replay_metrics.py` → errors 0（全仓不超基线 149；INTERNAL ERROR 先清 .mypy_cache 重跑）。
4. 全量：`G:/python/python.exe -m pytest -q` → 实测前基线 **379 passed**（2026-11-26 主审实测；计划口径 367，以实测为准只增不减）→ `385 passed`。
5. 冒烟：`G:/python/python.exe tools/replay_metrics.py config.toml`（实机池不可达则夹具跑 + verify: 标 `[INFO_GAP] 实机数`）与 `--json` 各一次，报表输出正常、全程零写入。
6. 实机基线实测：同步骤 5 命令 → 把四指标+占比填进计划文档 §4 基线列（该文件单独 commit）。

## 四、提交与约束

- 代码 commit：`feat(tools): 离线重放四指标量尺（D-20261125-05 每卡验收用）`，正文 `verify:`（全量前后数 + 四指标前后数）+ `Refs: D-20261125-05`；中文提交信息写 UTF-8 文件后 `git commit -F <文件>`。
- 文档 commit：计划 §4 基线列回填，`docs(plan): T-01 实机基线四指标回填`（同 Refs）。
- 显式列文件 add；永不 `git add -A`、永不 `--no-verify`；只 commit 不 push。
- 禁触：`app/__init__.py`、`installer/installer.iss`（他人未提交改动，勿动勿收）；本卡不 bump 版本、不发版、不动 CI；`runtime/` 不入库。
- learned 数据安全：本卡只读不改任何票目。
- 卡面外发现的问题只记录回报，不擅自扩范围；步骤行号以实施前 grep 复核为准（行号漂移以函数/锚文本定位）。

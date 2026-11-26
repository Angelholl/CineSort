# Task-07 卡面：A-1 学习票全面停记 + 旧票迁移 + enabled 改义（涉 GUI 文案）

- 决策真值：`docs/decision-log.md` **D-20261125-05** ｜ 实施计划：`docs/plans/2026-11-25-classify-adjustments.md` Task-07（含 §2.2-3 A-1 定读，已批准）
- 卡状态：待执行 ｜ 依赖：Task-03（C-1 填表）✓、Task-05（E）✓；十卡串行第 7 卡

## 一、根因与目标

执行侧不再向 learned.json 记任何题材键票（人工/确认一并停记——窗口期语义至此关闭）；旧票一次性幂等迁移（prune 掉已被别名表/库名覆盖的死键，其余保留为 legacy 建议）；`[learning].enabled` 改义为「自学习建议门控」（关=classify 不咨询 learned）；`min_votes` 转作 D 的提升阈值（字段获新消费方，不删配置键）。

## 二、改动文件与落点（行号为写卡时锚，实施前 grep 复核）

- `app/core/jobs.py:258-269`：删除整个 `if cfg.learning.enabled:` record 块（注释改「A-1 起停记；人工信号在会话留痕」）。
- `app/core/learned.py`：删除 `record()`（:43-60）；新增 `prune_legacy(runtime_dir: Path, covered: set[str]) -> int`（load→按 normalize_key 删 covered 键的 entries→空 entries 项一并删→save→返回删除数；**幂等=二次运行返回 0**）；模块 docstring 改 legacy 口径。
- `app/core/classifier.py`：新增 `covered_keys(cfg) -> set[str]` = `set(alias_map(cfg)) | set(weak_alias_map(cfg))`。
- `app/core/jobs.py run_scan`（:120-135 尾部，save_plan 之后）：`n = learned_store.prune_legacy(cfg.runtime_dir, covered_keys(cfg))` + `job.log(f"旧票迁移：清理已被别名表覆盖的学习票 {n} 条")`。
- `app/core/planner.py:86`：`learned = learned_store.load(cfg.runtime_dir) if cfg.learning.enabled else {}`（enabled 改义=建议门控）。
- GUI/文档：`app/ui/config_tab.py` tooltip（现「自学习」行）改「自学习建议开关：历史学习票仅作低置信建议展示，不再自动生效、不再记新票；阈值用于『提升建议』」；`:236` 标签 → 「自学习映射（仅作建议，不再记新票）」；`README.md:110-115` 同口径。
- 测试播种改造：`tests/conftest.py` 新增 `seed_learned(tmp_path, entries: dict)`（用 `learned_store.save` 直写构造票目）；本卡把 tests 内所有 `learned.record(...)` 播种调用改为该 helper（原地改写不减量——record 退役后唯一播种路径）。

**Interfaces**：Consumes=既有 load/save/items/forget/best_for/votes_for（全部保留——GUI 清单与量尺仍消费）；Produces=`learned.prune_legacy(runtime_dir, covered) -> int`、`classifier.covered_keys(cfg) -> set[str]`、learned.json 冻结（无新票写入路径）、`tests/conftest.py seed_learned(tmp_path, entries)`。

## 三、先红后绿回归测试（9 项 = 改写 3 + 新增 6，基线只增不减）

| 测试名（文件） | 断言 |
|---|---|
| `test_record_retired_no_votes_written`（test_flow.py，改写 test_flow.py:71-76 沉淀断言） | 全链路 apply（确认+改判）→ learned.json 不存在或 entries 为空；`state.state_snapshot()["learned"]==[]` |
| `test_record_retired`（test_learned.py，改写 T-02 的 `test_record_manual_counts_one_vote`） | `hasattr(ls, "record") is False`；seed_learned 构造的票目 apply 后逐字节不变 |
| `test_apply_records_nothing_at_all`（test_flow.py，改写 T-02 的 `test_apply_manual_override_records_no_votes`） | 确认单元也不记票：apply 后 learned.json 无新增键 |
| `test_prune_drops_covered_keeps_rest`（test_learned.py，新，seed_learned 播种） | 「武侠」（被库名覆盖）与「西部」（未覆盖）→ prune → 仅剩西部，返回 1；二次调用返回 0（幂等） |
| `test_prune_empty_entry_removed`（test_learned.py，新） | entry 全部 libs 为空壳 → prune 清掉空 entries 项 |
| `test_prune_triggered_by_scan`（test_flow.py，新） | 预置含 covered 键的 learned.json → start_scan → 文件仅剩未覆盖键、日志含「旧票迁移」 |
| `test_learning_disabled_gates_suggestions`（test_planner.py，新） | enabled=False + seed_learned 播票 → build_plan 无 learned 级单元（建议门控钉） |
| `test_config_tab_learning_texts`（test_config_tab.py，新，离屏） | 静态断言新 tooltip/标签含「仅作建议」、不含「自动生效」 |
| `test_replay_closure_zero_after_a1`（test_replay_metrics.py，新，seed_learned 播种） | post-留痕确认+改判会话触及对票数恒 0 → 不一致对 == 0 |

## 四、验收命令（以下命令均在项目根目录执行；测试解释器用 G:/python/python.exe）

1. conftest 加 `seed_learned` helper + 按表改写/新增 9 项测试（红）：`G:/python/python.exe -m pytest tests/test_learned.py tests/test_flow.py tests/test_planner.py tests/test_config_tab.py tests/test_replay_metrics.py -q` → 表内 9 项 fail（record 退役后既有播种调用同步换 helper）。
2. 最小实现四处：jobs 删 record 块+run_scan 接 prune；learned 删 record/增 prune_legacy；classifier 增 covered_keys；planner:86 enabled 门控。
3. 跑绿定向：上述命令 → all passed。
4. GUI/README 文案替换；ruff 改动文件 0 项；`G:/python/python.exe -m mypy app` → ≤149（不得新增）；全量 `QT_QPA_PLATFORM=offscreen G:/python/python.exe -m pytest -q` → **422 passed**（实测前基线 411=Task-06 收口数 +11 净增：+6 新 −改写归零不变）。
5. 重放核对：`G:/python/python.exe tools/replay_metrics.py config.toml` → **learned.json 新增人工票数==0（风险 #6 验证项）**、票数闭合不一致对数==0、自动生效 0；其余指标与 Task-06 收口基线逐项一致，差异即停并回报。实机 prune 条数在复测轮核对（本卡不跑真扫描）。
6. commit：`feat(classify): A-1 学习票停记+旧票迁移+learning.enabled 改义`；正文 `verify:` 全量 411→422 + 风险#6 验证值 + 「GUI 已验证（离屏）」+ `Refs: D-20261125-05`。中文提交信息写 UTF-8 文件后 `git commit -F <文件>`。

## 五、提交与约束

- 显式列文件 add；永不 `git add -A`、永不 `--no-verify`；只 commit 不 push。
- 同工作树 ≤1 卡（本卡独占执行）；禁触 `app/__init__.py`、`installer/installer.iss`（他人未提交改动，勿动勿收）。
- **learned 数据安全**：除 A-1 的幂等 prune 与 GUI 既有「忘记」外，任何任务不得删除/改写票目；prune 必须幂等（二次运行返回 0）；测试全走 tmp_path，不碰真 runtime。
- 不新建持久层文件、不新建配置键；GUI 按离屏协议，不引入新依赖。
- 执行纪律：卡面外发现的问题只记录回报，不擅自扩范围。

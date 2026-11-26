# Task-09 卡面：B(ii)——跨扫描记忆从会话日志派生（无 GUI，注记走既有 notes 渲染）

- 决策真值：`docs/decision-log.md` **D-20261125-05** ｜ 实施计划：`docs/plans/2026-11-25-classify-adjustments.md` Task-09（含 §2.2-6 B(ii) 定读，已批准）
- 卡状态：待执行 ｜ 依赖：Task-04（留痕五字段，已完成）；十卡串行第 9 卡

## 一、根因与目标

从 journals 派生「同作品人工改判」记忆（键同 B(i)=规范化片名+年份），扫描建计划时给命中单元**注记建议**（不 override、不默认勾选）；只认留痕上线后的执行（旧格式 done 天然跳过）；被回滚的会话不得派生（风险 #4，单测钉死）；同一作品多会话不一致时最近会话胜出。不新建持久层文件——记忆从会话日志派生。

## 二、改动文件与落点（行号为写卡时锚，实施前 grep 复核）

- `app/core/journal.py`：顶部 `from .nfo import normalize_key`；新增 `derive_memory(journals_dir: Path) -> dict[tuple[str, int | None], dict]`——undo 会话（header meta.undoes）取 done unit_id 集为回滚排除集；apply 会话按 header ts 升序，done 记录须**同时含 `title` 与 `manual` 字段**（留痕上线前旧格式天然跳过）、`manual is True`、unit_id 不在排除集 → `mem[(normalize_key(title), year)] = {"lib": target_lib, "sid": header sid, "ts": header ts}`（后到会话覆盖）。
- `app/core/planner.py`：import `derive_memory`；build_plan（:86-87 附近）`memory = derive_memory(cfg.runtime_dir / "journals")`；循环内（:125-161 plan_units.append 前）：命中（键=（normalize_key(u.title), u.year)）→ `unotes.append(f"跨扫描记忆：该片此前人工改判归入『{hit['lib']}』（会话 {hit['sid']}），可在详情面板改判采纳")` 且 plan 单元新增字段 `"memory_lib": hit["lib"]`（未命中单元**不写该键**）。
- **不改 viewmodel/plan_tab**（notes 既渲染、改判既交互）。

**Interfaces**：Consumes=留痕五字段（Task-04）+ `normalize_key`；Produces=`journal.derive_memory(journals_dir) -> dict[(str, int|None), {"lib","sid","ts"}]`、plan 单元可选字段 `memory_lib` + notes 注记。

## 三、先红后绿回归测试（新增 8，基线只增不减）

| 测试名（文件） | 断言 |
|---|---|
| `test_derive_manual_only`（test_journal.py，新） | manual=False 的 done 记录 → 不派生 |
| `test_derive_skips_pre_trace_entries`（test_journal.py，新） | done 无 title/manual 字段（留痕前旧格式）→ 跳过不炸 |
| `test_derive_excludes_undone`（test_journal.py，新） | apply 会话 + 对应 undo 会话 → 该 unit 不派生（风险 #4 钉） |
| `test_derive_partial_undo`（test_journal.py，新） | 3 单元 apply、undo 回滚 1 → 其余 2 派生 |
| `test_derive_last_session_wins`（test_journal.py，新） | 两 apply 同作品不同库 → ts 较后者胜 |
| `test_plan_memory_note_no_side_effects`（test_planner.py，新） | 命中单元：notes 含「跨扫描记忆」、`memory_lib=="动作"`、target_lib 不变、default_selected 不变；未命中单元无 memory_lib 键 |
| `test_plan_memory_key_normalization`（test_planner.py，新） | 会话片名「Ｔｅｓｔ Ｍｏｖｉｅ」vs 新单元「Test Movie」同年 → 命中（全半角键钉） |
| `test_rescan_new_batch_suggests_memory`（test_flow.py，新） | 改判执行→源重建同 title/year 新副本目录→重扫 → 新单元带记忆注记（同作品后续批次命中面） |

## 四、验收命令（以下命令均在项目根目录执行；测试解释器用 G:/python/python.exe）

1. 写 8 测试（红）：`G:/python/python.exe -m pytest tests/test_journal.py tests/test_planner.py tests/test_flow.py -q` → 新 8 fail。
2. 最小实现 journal.derive_memory + planner 注记；跑绿定向 → all passed。
3. ruff 改动文件 0 项；`G:/python/python.exe -m mypy app` → ≤149（不得新增）；全量 `QT_QPA_PLATFORM=offscreen G:/python/python.exe -m pytest -q` → **430 passed**（实测前基线 422=Task-08 收口数 +8）。
4. 重放核对：`G:/python/python.exe tools/replay_metrics.py config.toml` → 与 Task-08 收口基线逐项一致（memory 只加注记不改判定）；差异即停。真 runtime 零写入核验同前。
5. commit：`feat(core): B(ii) 跨扫描记忆从会话日志派生（回滚排除/留痕前跳过）`；正文 `verify:` 全量 422→430 + `Refs: D-20261125-05`。中文提交信息写 UTF-8 文件后 `git commit -F <文件>`。

## 五、提交与约束

- 显式列文件 add；永不 `git add -A`、永不 `--no-verify`；只 commit 不 push。
- 同工作树 ≤1 卡（本卡独占执行）；禁触 `app/__init__.py`、`installer/installer.iss`（他人未提交改动，勿动勿收）。
- **不新建持久层文件**（B(ii) 从会话日志派生）；「回滚后重扫」命中面仅在存在未回滚同作品会话时成立——纯被回滚会话本身不派生（§2.2-6 定读已披露，测试表已钉）。
- learned 数据安全：本卡不动票目；测试全走 tmp_path，不碰真 runtime。
- 执行纪律：卡面外发现的问题只记录回报，不擅自扩范围。

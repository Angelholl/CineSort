# Task-04 卡面：留痕——done 日志追加五字段（无 GUI）

- 决策真值：`docs/decision-log.md` **D-20261125-05** ｜ 实施计划：`docs/plans/2026-11-25-classify-adjustments.md` Task-04
- 卡状态：待执行 ｜ 依赖：Task-02（已完成）；十卡串行第 4 卡

## 一、根因与目标

执行会话的每条 done 记录携带 `provider / manual / orig_lib / title / year`，成为 B(i) 一致性门与 B(ii) 派生的唯一数据地基。旧记录无新字段 → 天然按「留痕上线前」判别跳过。

## 二、改动文件与落点（行号为写卡时锚，实施前 grep 复核，漂移以函数/锚文本定位）

- `app/core/jobs.py:138-141`（run_apply 内、:159 改写循环**前**）：`orig_lib = {u["id"]: u["target_lib"] for u in units}`——必须先于 :160-174 的 in-place 改写截取。
- `app/core/jobs.py:242-244`（jr.done 调用）追加：`provider=u.get("provider"), manual=u["id"] in overrides, orig_lib=orig_lib[u["id"]], title=u.get("title"), year=u.get("year")`。
- `app/core/journal.py`：**无签名变更**（done 为 **kw 透传）；仅补 docstring 说明五字段语义。

**Interfaces**：Consumes=既有 done 记录字段（src_dir/dst_dir/kind/mode/files/bytes/target_lib）；Produces=post-留痕 done 记录 = 旧字段 + 五新字段；旧格式记录不受影响。

## 三、先红后绿回归测试（新增 4，基线只增不减）

| 测试名（文件） | 断言 |
|---|---|
| `test_done_entry_carries_override_trace`（test_journal.py，新） | apply 单元改判「科幻」→动作 → done 记录 manual is True、orig_lib=="科幻"、target_lib=="动作"、provider=="tmdb:…"、title/year 与单元一致 |
| `test_done_entry_confirm_trace`（test_journal.py，新） | 无改判执行 → manual is False、orig_lib==target_lib |
| `test_apply_journal_trace_flow`（test_flow.py，新） | 全链路 apply 后 `done_entries` 首条含五字段（回滚链路不回归） |
| `test_old_journal_still_readable`（test_journal.py，新） | 手工旧格式 jsonl（无新字段）→ read_entries 正常、list_sessions 不炸 |

## 四、验收命令（以下命令均在项目根目录执行；测试解释器用 G:/python/python.exe）

1. 写 4 测试（红）：`G:/python/python.exe -m pytest tests/test_journal.py tests/test_flow.py -q` → 新 4 项 fail。
2. 最小实现：jobs.py 两处（截取 orig_lib + done 追加五字段）；journal.py docstring。
3. 跑绿定向：同步骤 1 命令 → all passed。
4. `G:/python/python.exe -m ruff check app/core/jobs.py app/core/journal.py tests/test_journal.py tests/test_flow.py` → 0 项；`G:/python/python.exe -m mypy app` → errors ≤149（不得新增）。
5. 全量：`G:/python/python.exe -m pytest -q` → **388→392 passed**（实测前基线 388=Task-02 收口数；计划账户净增 +4）。
6. 重放核对：`G:/python/python.exe tools/replay_metrics.py config.toml` → 与当前基线逐项一致：自动生效 **0**、胜出依据 **priority=152、plot=0、decl_order=0、votes=0、unexpected=0**、默认勾选 **181**、票数闭合不一致 **0**、最大占比 **22.3%**（C-1 重排后合法值）；本卡不触分类路径，任何差异即停并回报。

## 五、提交与约束

- commit：`feat(journal): done 留痕五字段（provider/人工/原判定库/片名/年份）`；正文 `verify:` 全量 388→392 + 四指标一致值 + `Refs: D-20261125-05`。中文提交信息写 UTF-8 文件后 `git commit -F <文件>`。
- 显式列文件 add（jobs.py、journal.py、tests/test_journal.py、tests/test_flow.py）；永不 `git add -A`、永不 `--no-verify`；只 commit 不 push。
- 同工作树 ≤1 卡（本卡独占执行）；禁触 `app/__init__.py`、`installer/installer.iss`（他人未提交改动，勿动勿收）。
- 不新建持久层文件；runtime/（learned.json/journals）不入库。
- learned 数据安全：本卡不动票目。
- 执行纪律：卡面外发现的问题只记录回报，不擅自扩范围。

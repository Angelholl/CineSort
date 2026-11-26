# Task-08 卡面：D——别名扫描分析对话框「提升建议」页（被 A-1 门控；涉 GUI 对话框）

- 决策真值：`docs/decision-log.md` **D-20261125-05** ｜ 实施计划：`docs/plans/2026-11-25-classify-adjustments.md` Task-08（含 §2.2-7 D 定读，已批准）
- 卡状态：待执行 ｜ 依赖：Task-07（A-1，已完成）；十卡串行第 8 卡

## 一、根因与目标

对话框新增第三个 tab「提升建议」：列出 A-1 迁移幸存、票数 ≥ `learning.min_votes`、未被别名表/库名覆盖、目标库仍存在的**真实题材信号**（§2.2-7 门），一键提升为强/弱别名（走既有分拣→统一保存管线）；当前实机满足条件为 **0 对**（决策原文口径），功能以空态上线、后续按数据自然生长。

## 二、改动文件与落点（行号为写卡时锚，实施前 grep 复核）

- `app/core/alias_scan.py`：新增 `promotion_candidates(learned: dict, cfg: Config) -> list[dict]`（bar=`max(cfg.learning.min_votes,1)`；过滤 covered（复用 Task-07 `covered_keys`）、`lib not in cfg.libraries`、votes<bar；行 `{genre, key, lib, votes, manual}`，按 (-votes, genre) 排序）。
- `app/core/alias_scan.py scan_alias_candidates`（:43-93）：返回 dict 增键 `"promotions": promotion_candidates(learned_store.load(cfg.runtime_dir), cfg)`（load 幂等只读；learned_store 经 alias_scan 顶部 import）。
- `app/ui/config_tab.py:479-491`：无需新调用（promotions 随 candidates 透传）；`filter_covered`（:96-106）**不得误伤 promotions 键**（其只处理 "genres"——回归断言钉）。
- `app/ui/alias_scan_dialog.py`：新增第三个 tab「提升建议」（QTableWidget：题材/目标库/票数/人工次数 + 按钮「提升为强别名」「提升为弱别名」→ 选中行写入既有 `tbl_staged`（候选=题材原样、目标库=行内 lib、表别=强/弱）；空列表 → 页内 QLabel 空态：「当前无满足条件的提升建议（真实题材信号票数达阈值且未被别名表覆盖）」）。

**Interfaces**：Consumes=`learned.load`（entries→libs→votes/manual 形态）、`classifier.covered_keys`、既有 staged 清单与 `_save_all` 管线（alias_scan_dialog.py:163-179）；Produces=`alias_scan.promotion_candidates(learned, cfg) -> list[dict]`、candidates dict 新键 `promotions`。

## 三、先红后绿回归测试（新增 5，基线只增不减）

| 测试名（文件） | 断言 |
|---|---|
| `test_promotion_candidates_filters`（test_alias_scan.py，新，seed_learned 播种） | 播票（covered 键 / votes<bar / 悬空库 / 正常票）→ 仅正常票行返回，字段与排序正确 |
| `test_promotion_candidates_empty_store`（test_alias_scan.py，新） | learned 空 → `[]`（当前实机 0 对的形态钉） |
| `test_scan_alias_candidates_carries_promotions`（test_alias_scan.py，新） | scan_alias_candidates 返回含 promotions 键；`filter_covered` 后 promotions 不受影响 |
| `test_dialog_promotions_empty_hint`（test_alias_scan_dialog.py，新，离屏） | promotions=[] → 第三 tab 空态文案在场 |
| `test_dialog_promotion_stages_into_list`（test_alias_scan_dialog.py，新，离屏） | 合成 promotions 2 行 → 选中→「提升为强别名」→ tbl_staged 增 2 行（表别=强）→ 统一保存回调收到对应行 |

## 四、验收命令（以下命令均在项目根目录执行；测试解释器用 G:/python/python.exe）

1. 写 5 测试（红）：`G:/python/python.exe -m pytest tests/test_alias_scan.py tests/test_alias_scan_dialog.py -q` → 新 5 fail。
2. 最小实现 core（promotion_candidates + scan 键）；跑绿 test_alias_scan。
3. 对话框 UI（tab+空态+提升按钮接线既有 staged 管线）；离屏跑绿 test_alias_scan_dialog：`QT_QPA_PLATFORM=offscreen G:/python/python.exe -m pytest tests/test_alias_scan_dialog.py -q` → all passed。
4. ruff 改动文件 0 项；`G:/python/python.exe -m mypy app` → ≤149（不得新增）；全量 `QT_QPA_PLATFORM=offscreen G:/python/python.exe -m pytest -q` → **422 passed**（实测前基线 417=Task-07 收口数 +5）。
5. 重放核对：四指标与 Task-07 收口基线逐项一致；实机重放记录 promotions==0（决策原文口径）——若此前已发生真扫描致数字合法漂移，只记录回报不判错。
6. commit：`feat(ui): D 别名扫描分析新增提升建议页（A-1 门控，真实题材信号）`；正文 `verify:` 全量 417→422 + promotions 实测数 + 「GUI 已验证（离屏）」+ `Refs: D-20261125-05`。中文提交信息写 UTF-8 文件后 `git commit -F <文件>`。

## 五、提交与约束

- 显式列文件 add；永不 `git add -A`、永不 `--no-verify`；只 commit 不 push。
- 同工作树 ≤1 卡（本卡独占执行）；禁触 `app/__init__.py`、`installer/installer.iss`（他人未提交改动，勿动勿收）。
- GUI 按离屏协议（viewmodel/对话框级逻辑零 Qt 单测 + offscreen widget 驱动），不引入新依赖；实机黑盒留统一复测轮。
- learned 数据安全：本卡只读票目（load 幂等）；提升动作走既有分拣→统一保存管线，不绕过既有确认。
- 不新建持久层文件、不新建配置键（min_votes 自 T-07 起获 D 消费方）。
- 执行纪律：卡面外发现的问题只记录回报，不擅自扩范围。

# Task-06 卡面：B(i) 会话内同作品套用改判（片名+年份键，id 一致性门；涉 GUI 提示）

- 决策真值：`docs/decision-log.md` **D-20261125-05** ｜ 实施计划：`docs/plans/2026-11-25-classify-adjustments.md` Task-06（按 2026-11-25 前置核实修正函实现）
- 卡状态：待执行 ｜ 依赖：Task-04（留痕五字段，已完成）；十卡串行第 6 卡

## 一、根因与目标

详情面板对单元 X 改判到库 L 时，同片名+同年份的兄弟单元自动写同一 override（**不自动勾选**；id 不一致/已执行/复合/硬冲突/落点互撞者不套用）。套用键=规范化片名+年份；provider id 仅作一致性门。

## 二、改动文件与落点（行号为写卡时锚，实施前 grep 复核）

- `app/ui/viewmodel.py`：顶部 `from app.core.nfo import normalize_key`；import 行（:16-22）补 `ST_MULTI`；新增模块级 `_work_key(u) -> tuple[str, int | None]`；`PlanViewModel` 新增 `sibling_overrides(unit_id: str, lib: str) -> list[str]`；`set_override`（:243-250）尾部套用并**返回 int（套用数，原返回 None 向后兼容）**。
- `app/ui/plan_tab.py:702-706` `_on_override_changed`：接收返回值，>0 时 `self.toast(f"已套用到 {n} 部同作品单元（不自动勾选）")`；:295 hint 在现有文案后追加「同片名+同年份单元自动套用改判」。
- 兄弟资格（钉死）：`u["id"] != unit_id` 且 `_work_key(u)==_work_key(me)`；`status in (READY, ST_MULTI)`；id 一致性门 `u.get("provider") is None or me.get("provider") is None or u["provider"]==me["provider"]`；落点互撞门 `key=(lib, u.get("actress"), u.get("dst_name"))` 组内去重。`set_override_many`（批量改判）不触发套用；`lib=None` 撤销改判不联动撤销兄弟。

**Interfaces**：Consumes=plan 单元 `title/year/provider/status/actress/dst_name`（planner.py:125-161 既有字段）；Produces=`PlanViewModel.sibling_overrides(unit_id, lib) -> list[str]`、`set_override(...) -> int`。

## 三、先红后绿回归测试（新增 11，基线只增不减）

| 测试名（文件） | 断言 |
|---|---|
| `test_sibling_apply_same_title_year_id`（test_viewmodel.py，新） | 3 同作品单元（同 title/year/provider）→ set_override(u1,"科幻") → u2/u3 override 生效、返回 2、**不在 checked**、effective_target_lib=="科幻" |
| `test_sibling_provider_mismatch_not_applied`（test_viewmodel.py，新） | 同 title/year、provider 不同（分集/剧集反例）→ 返回 0、无 override（负例钉） |
| `test_sibling_bare_id_none_consistent`（test_viewmodel.py，新） | 双方 provider 均为 None → 套用（片名+年份键独立成立） |
| `test_sibling_applied_and_composite_excluded`（test_viewmodel.py，新） | 兄弟 status=applied / composite(ST_BATCH) → 不套用（「假同 id 不得跨成因套用」负例钉） |
| `test_sibling_stmulti_receives_unchecked`（test_viewmodel.py，新） | 兄弟 ST_MULTI → 套用且不在 checked（多版本主场景） |
| `test_sibling_dst_collision_skipped`（test_viewmodel.py，新） | 两兄弟同 (lib,actress,dst_name) → 第二个跳过（落点冲突不套用） |
| `test_sibling_conflict_status_skipped`（test_viewmodel.py，新） | 兄弟 ST_CONFLICT/ST_PLACED/ST_INCOMPLETE → 不套用 |
| `test_clear_override_no_propagation`（test_viewmodel.py，新） | 撤销 u1 改判 → 兄弟 override 保留（不联动撤销） |
| `test_set_override_many_no_expansion`（test_viewmodel.py，新） | 批量改判仅作用于给定 id 集，不外扩 |
| `test_fullwidth_title_key_normalized`（test_viewmodel.py，新） | 「Ｔｅｓｔ Ｍｏｖｉｅ ２」与「Test Movie 2」同年份 → 同键互套（normalize_key 全半角钉） |
| `test_override_applies_sibling_toast`（test_plan_tab.py，新，离屏） | widget 驱动 d_override 选库 → toast 文案 + 兄弟行目标库列显示改判库 |

## 四、验收命令（以下命令均在项目根目录执行；测试解释器用 G:/python/python.exe）

1. 写 11 测试（红）：`G:/python/python.exe -m pytest tests/test_viewmodel.py tests/test_plan_tab.py -q` → 新 11 fail。
2. 最小实现 viewmodel（import 补齐/_work_key/sibling_overrides/set_override 返回值）；跑绿。
3. plan_tab 接线（toast+hint）；离屏跑绿 test_plan_tab：`QT_QPA_PLATFORM=offscreen G:/python/python.exe -m pytest tests/test_viewmodel.py tests/test_plan_tab.py -q` → all passed。
4. ruff 改动文件 0 项；`G:/python/python.exe -m mypy app` → ≤149；全量 `G:/python/python.exe -m pytest -q`（QT_QPA_PLATFORM=offscreen）→ **411 passed**（实测前基线 400=Task-05 收口数 +11）。
5. 重放核对：`G:/python/python.exe tools/replay_metrics.py config.toml` → 与当前基线逐项一致：自动生效 **0**、胜出依据 **priority=152、plot=0、decl_order=0、votes=0、unexpected=0**、默认勾选 **181**、票数闭合不一致 **0**、最大占比 **22.3%**（B(i) 不触分类路径），差异即停。
6. commit：`feat(ui): B(i) 同作品（片名+年份）会话内套用改判（id 一致性门）`；正文 `verify:` 全量 400→411 + 「GUI 已验证（离屏）」+ `Refs: D-20261125-05`。中文提交信息写 UTF-8 文件后 `git commit -F <文件>`。

## 五、提交与约束

- 显式列文件 add；永不 `git add -A`、永不 `--no-verify`；只 commit 不 push。
- 同工作树 ≤1 卡（本卡独占执行）；禁触 `app/__init__.py`、`installer/installer.iss`（他人未提交改动，勿动勿收）。
- GUI 按离屏协议（viewmodel 级零 Qt 单测 + offscreen widget 驱动），不引入新依赖；实机黑盒留统一复测轮。
- set_override 返回类型变更属向后兼容（原 None）；不改批量改判/撤销既有语义。
- learned 数据安全：本卡不动票目；不新建持久层文件、不新建配置键。
- 执行纪律：卡面外发现的问题只记录回报，不擅自扩范围。

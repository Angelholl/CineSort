# 卡 C9：`ST_BATCH` 状态、兜底率新口径、撤销修复与执行门禁（计划 Task-10，特性 C-2 核心）

规格：`docs/design/2026-11-09-classification-quality.md` §4.2、§4.3　计划：`docs/plans/2026-11-09-classification-quality.md` Task-10
决策依据：`docs/decision-log.md` D-20261109-01　前置：Task-05（`5e95334`）、Task-09（`1373792`）
测试基线：**252 passed**（本卡净增 7，收口应 259）；全仓 ruff 基线 **10 项**（只降不增）

## 一、本卡为什么是安全卡（必须先做）

上一卡让 43 个复合目录变成了整目录单元。主审实测当前中间态：

```
复合单元 43 | 分类层级 {'rule': 41, 'title': 1, 'fallback': 1} | high 置信 41
```

这 41 个 high 置信判定各自只依据**目录里某一部影片的 NFO**（实测例：`#未知女优` 用 `[GOV-004]` 的 NFO → 判"合集长篇"；`伊藤舞雪` 用 `CAWD-876-C` 的 NFO → 判"按摩"；`三澄寧々` 用 `IPZZ-748-C` 的 NFO → 判"乱交"）。一个装 2–43 部不同影片的目录被单张 NFO 决定去向，且默认勾选——**这正是 decision-critic 提 [HIGH_RISK_OBJECTION] 时警告的形态**。本卡把复合单元钉成 `ST_BATCH`：不进 fallback 分母、永不默认勾选、**没有人工改判就不能执行**，并修掉 `mark_undone` 会把复合单元错误恢复成 READY 的缺陷。

## 二、改动文件（只许改这四个）

| 文件 | 动作 | 落点 |
|---|---|---|
| `app/core/planner.py` | Modify | 状态常量（:27 后）与 `STATUS_LABELS`（:32-35）；`build_plan` 循环（:76-140）；统计（:157-179）；`_refresh_stats`（:242-252）；`mark_undone`（:269-279） |
| `app/ui/viewmodel.py` | Modify | `LEVEL_FILTERS`（:21）、`LEVEL_BADGES`（:26-31）、`checked_not_ready`/`can_apply`（:188-194）新增 `_executable` |
| `tests/test_planner.py` | Test | 末尾追加 6 个 |
| `tests/test_viewmodel.py` | Test | 末尾追加 1 个 |

不动 `scanner.py`、`classifier.py`、`jobs.py`、`preflight.py`、`config.py`、`plan_tab.py`（执行链与 UI 是下一卡）。现有测试 0 删 0 改。

## 三、改法（照抄执行）

1. `ST_BATCH = "batch_target"`；`STATUS_LABELS` 加 `ST_BATCH: "整目录待改判"`。
2. `build_plan` 循环首：`is_composite = getattr(u, "composite", False)`；照旧 classify（保留占位证据），随后对复合单元覆写 `status = ST_BATCH`、`level = "composite"`；**冲突检测（:84-104）若得出更硬状态（ST_CONFLICT / ST_INCOMPLETE / ST_PLACED）优先于 ST_BATCH**；单元 dict 加 `"composite": is_composite`，`"level"` 写 `"composite" if is_composite else dec.level`；`default_selected` 追加 `and not is_composite`（复合单元恒 False）。
3. 多版本分组（:144-146）本就是 READY-only，复合单元天然被排除——**只加一行注释说明**，不改逻辑。
4. 统计：`composite_count = sum(1 for pu in plan_units if pu["composite"])`；`stats["composite"] = composite_count`；兜底率改 `denom = total - composite_count` → `"fallback_ratio": (fb / denom) if denom else 0.0`。`_refresh_stats` 用同一口径（按 `pu.get("composite")` 计数，不随 ST_APPLIED 漂移）。
5. `mark_undone`：`pu["status"] = ST_BATCH if pu.get("composite") else READY`。
6. `viewmodel.py`：`LEVEL_FILTERS` 追加 `"composite"`；`LEVEL_BADGES` 加 `"composite": ("整目录", "rule")`（复用既有色值，**不得新增颜色**）；新增

```python
    def _executable(self, u: dict) -> bool:
        if u["status"] == READY:
            return True
        return u["status"] == ST_BATCH and bool(self.overrides.get(u["id"]))
```

`checked_not_ready` 返回 `_executable` 为 False 的已勾选单元；`can_apply` 复用 `_executable`；顶部 import 补 `ST_BATCH`。

## 四、先红后绿的回归测试（7 个）

`tests/test_planner.py` 末尾 6 个（复合单元用既有 `make_movie` 造 2 个不同 base）：

| 测试名 | 断言 |
|---|---|
| `test_plan_composite_status_and_level` | `status == ST_BATCH`、`level == "composite"`、`default_selected is False`、`target_lib == "兜底库"`（占位）、`unit["composite"] is True` |
| `test_plan_composite_out_of_fallback_ratio` | 1 个普通 fallback 单元 + 1 个复合单元 → `stats["fallback_ratio"] == 0.5`（分母 2 而非 3） |
| `test_plan_stats_composite_count` | `stats["composite"] == 1`；`stats["by_status"]` 含 `batch_target` |
| `test_refresh_stats_keeps_denominator` | 复合单元执行后 `mark_applied` → `_refresh_stats` 的 fallback_ratio 分母仍排除 composite |
| `test_mark_undone_restores_batch_status` | 已执行的复合单元 `mark_undone` 后 `status == ST_BATCH`（**不得**变 READY） |
| `test_composite_conflict_detection` | 兜底库预置同名目录 → 复合单元 `status == ST_CONFLICT`（硬状态优先于 ST_BATCH） |

`tests/test_viewmodel.py` 末尾 1 个：`test_composite_gate_requires_override` —— ST_BATCH 且无 override：`checked_not_ready` 含该单元、`can_apply` 为 False；`set_override` 后 `_executable` 为 True、`can_apply` 为 True。

## 五、验收命令（以下命令均在项目根目录执行，cwd 即仓库根）

1. 红：`python -m pytest tests/test_planner.py tests/test_viewmodel.py -q`（7 个新测试先失败）
2. 绿：`python -m ruff check app/core/planner.py app/ui/viewmodel.py tests/test_planner.py tests/test_viewmodel.py` 必须 **0 项**（四个文件全列）；`python -m pytest tests/test_planner.py tests/test_viewmodel.py -q` 全绿（**实测现有 8 + 28 = 36**，加 7 新 = **43**）
3. 全量不回归：`python -m pytest tests -q` → **0 failed，用例总数 = 259**（252 + 7）
4. 全仓 lint 不增：`python -m ruff check . 2>&1 | grep "^Found"` → 必须 **≤ 10 errors**
5. 真实数据只读自检（**必须贴原样输出**）：
   `py -3.12 -c "import sys,collections;sys.path.insert(0,'.');from app.core.config import load_config;from app.core.scanner import scan_source_root;from app.core.planner import build_plan;cfg=load_config(r'D:/CineSort-beta/CineSort/config.toml');us,ns=scan_source_root(cfg);p=build_plan(cfg,us,ns);st=p['stats'];u=p['units'];c=[x for x in u if x.get('composite')];print('units=',len(u),'composite=',st.get('composite'));print('status=',dict(collections.Counter(x['status'] for x in u)));print('fallback_ratio=',st['fallback_ratio']);print('composite_default_selected_true=',sum(1 for x in c if x['default_selected']));print('composite_ready=',sum(1 for x in c if x['status']=='ready'))"`
   → 期望：`composite= 43`、`composite_default_selected_true= 0`、`composite_ready= 0`、`fallback_ratio` 约 0.02（分母 97 而非 140）。**四个数字必须逐个贴出。**

## 六、约束

- 只改卡面四个文件；现有测试 0 删 0 改；不得为变绿放宽断言。
- 不得改 `scanner.py` 的复合目录判定与单元生成；不得改 `classifier.py` 任何判定；不得改 `jobs.py`/`preflight.py`（下一卡）。
- 不得新增颜色常量；不得改 `default_selected` 对非复合单元的既有规则。
- 禁止任何物理文件操作；不得写 `D:\CineSort\config.toml`、`D:\CineSort-beta\CineSort\config.toml`、`config.example.toml` 或 `E:\已刮削` 下任何文件（真实盘只读）。
- 不得联网。卡外问题即停，在回报里单列，不得顺手改。
- 读大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 `pointerize` / `read_pointer` / `read_diff_only`，禁止整读文件全文。
- 完成后 `git commit`（Conventional 前缀 + 中文描述，正文 `verify:` 写实测结果与 `Refs: D-20261109-01`），**不得 push**，不得 `git add -A`、不得 `--no-verify`。

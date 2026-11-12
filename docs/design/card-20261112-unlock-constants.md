# 卡：改判解锁白名单收敛为 planner.UNLOCKABLE_STATUSES 单点（v0.6.1 评审记账项）

## ① 背景与目标

v0.6.1 push 前 code-review（Standards 轴）记账项：「ST_BATCH/ST_MULTI + overrides 解锁」领域规则以裸元组散落 5 处，下次新增可解锁状态仍是散点改。本卡收敛为 planner 单点常量，**纯重构、行为零变化**（322 基线须全绿）。

## ② 改动文件

源码（4）：`app/core/planner.py`、`app/core/jobs.py`、`app/core/preflight.py`、`app/ui/viewmodel.py`
测试（1）：`tests/test_viewmodel.py`（新增 1 个架构钉）

## ③ 改法

### 3.1 app/core/planner.py 常量定义

在 status 常量块（:23-29 `READY = "ready"` … `ST_BATCH = "batch_target"`）之后新增：

```python
# 人工改判可解锁状态：整目录待改判 / 多版本需确认（执行门+体检+快照白名单共享）
UNLOCKABLE_STATUSES = (ST_BATCH, ST_MULTI)
```

`check_plan_freshness`（:241）改为：

```python
        if pu["status"] not in (READY, *UNLOCKABLE_STATUSES):
            continue
```

planner 内 ST_BATCH/ST_MULTI 的赋值逻辑（:116-120/:169）不动，仍直引常量。

### 3.2 app/core/jobs.py run_apply 门（:148-153）

```python
    # 整目录待改判/多版本需确认仅在人工指定目标库后放行（白名单=UNLOCKABLE_STATUSES）
    bad = [u["id"] for u in units
           if u["status"] != READY
           and not (u["status"] in UNLOCKABLE_STATUSES
                    and overrides.get(u["id"]))]
```

planner import 块补 `UNLOCKABLE_STATUSES`；改后 grep 确认 ST_BATCH/ST_MULTI 在本文件无其余引用则从 import 移除（防 ruff F401），有引用则保留。

### 3.3 app/core/preflight.py 两处白名单（:84 磁盘、:123 长路径）

```python
        units = [u for u in plan["units"] if u["status"] in (READY, *UNLOCKABLE_STATUSES) and
                 (selected_ids is None or u["id"] in selected_ids)]
```

```python
            if u["status"] not in (READY, *UNLOCKABLE_STATUSES):
                continue
```

import 按同规则处理：改为 `from .planner import READY, UNLOCKABLE_STATUSES`，grep 确认 ST_BATCH/ST_MULTI 无其余引用后移除。

### 3.4 app/ui/viewmodel.py

planner import 补 `UNLOCKABLE_STATUSES`；`_executable`（:200-204）与 `blocked_toast`（unlockable/hard 两行）的裸元组全部换用 `UNLOCKABLE_STATUSES`；改后同规则清理不再使用的 ST_BATCH/ST_MULTI 导入（STATUS_LABELS 仍被 blocked_toast 使用，保留）。docstring 文字不动。

## ④ 回归测试（先红后绿：架构钉红→实现转绿；322 基线须全绿不减）

tests/test_viewmodel.py 末尾追加（若文件未导入 Path 则补 `from pathlib import Path`）：

```python
def test_unlock_statuses_single_point():
    """架构钉：改判解锁白名单收敛于 planner.UNLOCKABLE_STATUSES（v0.6.1 评审记账项）。"""
    import app.core.jobs as jobs_mod

    for src in (Path(jobs_mod.__file__).read_text(encoding="utf-8"),
                Path(vm.__file__).read_text(encoding="utf-8")):
        assert "in (ST_BATCH, ST_MULTI)" not in src      # 散点裸元组清零
        assert "UNLOCKABLE_STATUSES" in src
```

先红预期：钉子红于 jobs/viewmodel 源仍含 `in (ST_BATCH, ST_MULTI)`；落 3.1-3.4 后转绿，且全量 322 例无回归（本卡无行为变化）。

## ⑤ 验收命令（以下命令均在项目根目录执行）

```bash
py -3.12 -m ruff check app/core/planner.py app/core/jobs.py app/core/preflight.py app/ui/viewmodel.py tests/test_viewmodel.py
py -3.12 -m pytest tests/test_viewmodel.py tests/test_flow.py tests/test_plan_tab.py -q
py -3.12 -m pytest -q
```

全部须通过（本机仅 py -3.12 环境装有 pytest/ruff）。

## ⑥ 约束

- 只动 ② 所列 5 个文件；禁止改任何行为语义（状态赋值、文案、门槛判定结果须与现状逐位一致）；禁止顺手做其他 smell 收敛。
- 不 commit、不 push：自测全绿后报告即止，主审验收后统一提交。
- test_flow.py 保持无 Qt 依赖，勿在其中加 import。

# 卡：不可执行拦截 toast 点名单元与真实原因（2026-11-12 用户反馈跟进）

## ① 根因

`app/ui/plan_tab.py:444` 拦截 toast 文案 `有 N 部不可执行（冲突/残留）` 是对所有 blocked 状态的笼统措辞——多版本待确认/整目录待改判也被说成「冲突/残留」，误导用户（owner 已确认要改为点名具体单元+真实原因）。

真值源：`STATUS_LABELS`（app/core/planner.py:33-37）已含全部中文状态名；可改判解锁的=ST_BATCH/ST_MULTI（card-20261112-multi-version-unlock 语义），硬阻断=ST_CONFLICT/ST_PLACED/ST_INCOMPLETE。

## ② 改动文件

- `app/ui/viewmodel.py`（新增纯函数）
- `app/ui/plan_tab.py`（toast 调用处换文案）
- `tests/test_viewmodel.py`、`tests/test_plan_tab.py`（回归测试）

## ③ 改法

### 3.1 app/ui/viewmodel.py 模块级纯函数（置于 PlanViewModel 类之前、override_libs 同层）

```python
def blocked_toast(units: list[dict], max_show: int = 2) -> str:
    """执行被拦时点名单元与真实原因，替代笼统的「冲突/残留」措辞。

    可改判解锁的（ST_BATCH/ST_MULTI）给改判指引；硬阻断（同名冲突/
    已在位/半成品残留）提示处理或取消勾选；混合时两种指引都给。
    超出 max_show 个单元折叠为「等 N 部」。
    """
    def _name(u: dict) -> str:
        reason = STATUS_LABELS.get(u["status"], u["status"])
        return f"《{u['label']}》{reason}"

    names = "、".join(_name(u) for u in units[:max_show])
    if len(units) > max_show:
        names += f" 等 {len(units)} 部"
    head = f"有 {len(units)} 部不可执行：" if len(units) > 1 else "不可执行："
    unlockable = any(u["status"] in (ST_BATCH, ST_MULTI) for u in units)
    hard = any(u["status"] not in (ST_BATCH, ST_MULTI) for u in units)
    if unlockable and hard:
        tail = "——可改判的请在详情面板指定目标库，其余请处理或取消勾选"
    elif unlockable:
        tail = "——请在详情面板改判指定目标库"
    else:
        tail = "——请先处理或取消勾选"
    return head + names + tail
```

viewmodel.py 已 import STATUS_LABELS/ST_BATCH/ST_MULTI，无需新增导入。

### 3.2 app/ui/plan_tab.py

- viewmodel 导入块（:54-61 `from .viewmodel import (...)`）按字母序补 `blocked_toast,`。
- `_apply_selected`（:442-445）改为：

```python
        bad = self.vm.checked_not_ready()
        if bad:
            self.toast(blocked_toast(bad))
            return
```

### 3.3 禁改项

筛选 chip「冲突/残留」标签（plan_tab.py:122）是分类名非原因声称，保持不动；STATUS_LABELS、`can_apply`、按钮禁用逻辑均不动。

## ④ 回归测试（先红后绿）

### 4.1 tests/test_viewmodel.py 末尾追加（make_unit/vm/planner 均已有导入）

```python
# ---------------- 不可执行 toast 点名真实原因（2026-11-12 反馈） ----------------

def test_blocked_toast_names_unlockable_units():
    """改判可解：点名单元+真实原因+改判指引，不再笼统称「冲突/残留」。"""
    u1 = make_unit("A 片", level="title", status=planner.ST_MULTI,
                   lib="兜底库", default_selected=False, genres=())
    msg = vm.blocked_toast([u1])
    assert msg == "不可执行：《A 片》多版本需确认——请在详情面板改判指定目标库"
    assert "冲突/残留" not in msg


def test_blocked_toast_mixed_and_fold():
    """混合原因给双指引；超过 2 个折叠为「等 N 部」；硬阻断只给处理指引。"""
    u1 = make_unit("A 片", level="title", status=planner.ST_MULTI,
                   lib="兜底库", default_selected=False, genres=())
    u2 = make_unit("B 片", level="composite", status=planner.ST_BATCH,
                   lib="兜底库", default_selected=False, genres=())
    u3 = make_unit("C 片", level="rule", status=planner.ST_CONFLICT,
                   lib="兜底库", default_selected=False, genres=())
    u4 = make_unit("D 片", level="rule", status=planner.ST_INCOMPLETE,
                   lib="兜底库", default_selected=False, genres=())
    msg = vm.blocked_toast([u1, u2, u3, u4])
    assert msg.startswith("有 4 部不可执行：")
    assert "《A 片》多版本需确认" in msg and "《B 片》整目录待改判" in msg
    assert "等 4 部" in msg
    assert "可改判的请在详情面板指定目标库" in msg and "取消勾选" in msg
    hard = vm.blocked_toast([u3])
    assert hard == "不可执行：《C 片》同名冲突——请先处理或取消勾选"
```

### 4.2 tests/test_plan_tab.py 末尾追加（紧邻 test_multi_version_override_passes_apply_gate）

```python
def test_blocked_toast_names_unit_and_reason(qapp):
    """回归（2026-11-12 反馈）：拦截 toast 点名单元与真实原因，替代笼统措辞。"""
    units = fake_units(1, seed=9)
    for u in units:
        u["status"] = "multi_version"
        u["default_selected"] = False

    class GateStubState:
        def plan(self):
            return {"units": units}

        def start_preflight(self, ids):
            raise AssertionError("门未拦截，不应走到体检")

    toasts: list[str] = []
    tab = PlanTab(GateStubState(), None, toast=toasts.append)
    try:
        u = tab.vm.rows()[0]
        tab.vm.checked.add(u["id"])
        tab._apply_selected()
        assert len(toasts) == 1
        assert f"《{u['label']}》多版本需确认" in toasts[0]
        assert "请在详情面板改判指定目标库" in toasts[0]
        assert "冲突/残留" not in toasts[0]
    finally:
        tab.deleteLater()
```

先红预期：4.1 两例红于 `AttributeError: ... no attribute 'blocked_toast'`；4.2 红于 toast 仍为笼统文案（断言不匹配）。实现后全绿。

## ⑤ 验收命令（以下命令均在项目根目录执行）

```bash
py -3.12 -m ruff check app/ui/viewmodel.py app/ui/plan_tab.py tests/test_viewmodel.py tests/test_plan_tab.py
py -3.12 -m pytest tests/test_viewmodel.py tests/test_plan_tab.py -q
py -3.12 -m pytest -q
```

全部须通过（本机仅 py -3.12 环境装有 pytest/ruff）。

## ⑥ 约束

- 只动 ② 所列 4 个文件；文案逐字按卡面（含全角书名号/破折号）；禁止顺手改筛选 chip、按钮逻辑、STATUS_LABELS。
- 不 commit、不 push：自测全绿后报告即止，主审验收后统一提交。
- offscreen 由 test_plan_tab.py 模块头保证。

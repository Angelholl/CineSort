# 卡：多版本单元（ST_MULTI）人工改判后放行执行（2026-11-12 用户反馈）

## ① 根因

多版本单元 status=`ST_MULTI`（`app/core/planner.py:169`，同 provider id 多副本组，人工确认通道=详情面板「改判目标库」下拉），但「人工改判解锁执行」白名单只认 `ST_BATCH`，共 5 处同判：

1. `app/ui/viewmodel.py:203` `_executable` → 改判后 UI 仍判不可执行
2. `app/ui/plan_tab.py:442-445` `_apply_selected` 用 `checked_not_ready()` 弹 toast「有 N 部不可执行（冲突/残留），请先处理或取消勾选」（该文案是所有 blocked 的笼统措辞，与 status 无映射）
3. `app/core/jobs.py:152` run_apply 门 → 放行后会被 RuntimeError「不在可执行状态」再拒
4. `app/core/preflight.py:84`（磁盘空间）与 `:123`（超长路径）白名单 → ST_MULTI 被体检跳过
5. `app/core/planner.py:241` `check_plan_freshness` 白名单 → ST_MULTI 被源快照校验跳过

仅修 1 会让用户在 apply 侧被 3 再拦；仅修 1+3 会让多版本单元失去磁盘/长路径体检与源快照保护。故 5 处须原子同步。

注：本卡改动 4 源文件+3 测试文件，超「一卡一两个文件」常规粒度——因同一解锁语义在架构上分散 5 处判定点，拆卡会产生中间不一致状态，故合卡执行。

## ② 改动文件

源码（4）：`app/ui/viewmodel.py`、`app/core/jobs.py`、`app/core/preflight.py`、`app/core/planner.py`
测试（3）：`tests/test_viewmodel.py`、`tests/test_flow.py`、`tests/test_plan_tab.py`

## ③ 改法

### 3.1 app/ui/viewmodel.py

:18 的 planner import 补 `ST_MULTI`；`_executable`（:200-203）改为：

```python
    def _executable(self, u: dict) -> bool:
        """单元是否可执行：READY 直接可执行；ST_BATCH（整目录）/ST_MULTI
        （多版本需确认）须人工改判指定目标库后解锁。"""
        if u["status"] == READY:
            return True
        return (u["status"] in (ST_BATCH, ST_MULTI)
                and bool(self.overrides.get(u["id"])))
```

### 3.2 app/core/jobs.py

:16 的 planner import 补 `ST_MULTI`；run_apply 门（:149-152）改为：

```python
    # ST_BATCH（整目录待改判）/ST_MULTI（多版本需确认）仅在人工指定目标库后放行
    bad = [u["id"] for u in units
           if u["status"] != READY
           and not (u["status"] in (ST_BATCH, ST_MULTI)
                    and overrides.get(u["id"]))]
```

### 3.3 app/core/preflight.py

:15 `from .planner import READY, ST_BATCH, ST_MULTI`；:84 与 :123 两处元组改为 `(READY, ST_BATCH, ST_MULTI)`。其余逻辑不动。

### 3.4 app/core/planner.py

`check_plan_freshness`（:241）改为：

```python
        if pu["status"] not in (READY, ST_BATCH, ST_MULTI):
            continue
```

### 3.5 禁改项

STATUS_LABELS 文案、状态徽章、`select_visible_ready`、学习沉淀逻辑、`planner.py:303` 均不动。「多版本+已改判后状态徽章仍显示需确认」为已知外观项，不在本卡范围。

## ④ 回归测试（先红后绿）

先只加测试跑一轮，确认下述 4 个红点失败原因符合预期，再落 3.1-3.4 转绿。

### 4.1 tests/test_viewmodel.py（镜像 :372 test_composite_gate_requires_override）

```python
def test_multi_version_gate_requires_override():
    """ST_MULTI 多版本单元：无人工改判不得执行，改判后解锁（2026-11-12 反馈）。"""
    u = make_unit("G 多版本", level="title", status=planner.ST_MULTI,
                  lib="兜底库", default_selected=False, genres=())
    model = vm.PlanViewModel([u])
    model.checked.add(u["id"])
    assert u["id"] in {x["id"] for x in model.checked_not_ready()}
    assert model.can_apply() is False
    assert model._executable(u) is False
    model.set_override(u["id"], "科幻")
    assert model._executable(u) is True
    assert model.checked_not_ready() == []
    assert model.can_apply() is True
```

### 4.2 tests/test_flow.py 新段（镜像 :370 「放行 ST_BATCH」段的 AppState+wait_job 模式）

文件导入区按既有风格补缺：`from types import SimpleNamespace`、`import shutil`、`from app.core.planner import check_plan_freshness`。

```python
# ---------------- 放行 ST_MULTI：多版本人工确认后执行（2026-11-12 反馈） ----------------

def _make_multi_version(cfg, base):
    """同 provider id 两个版本/副本 → planner 组为 ST_MULTI（默认不勾选）。"""
    make_movie(cfg.source_root, base, title=base, genres=("西部",),
               plot="乡村爱情", tmdb="77")
    make_movie(cfg.source_root, base + " (扩展版)", title=base + " (扩展版)",
               genres=("西部",), plot="乡村爱情", tmdb="77")


def test_plan_groups_same_provider_as_multi_version(tmp_path):
    """多版本分组钉：同 tmdb 两副本 → ST_MULTI + default_selected=False。"""
    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    _make_multi_version(cfg, "Same Movie")
    units, notes = scanner.scan_source_root(cfg)
    plan = build_plan(cfg, units, notes)
    assert [u["status"] for u in plan["units"]] == ["multi_version", "multi_version"]
    assert all(u["default_selected"] is False for u in plan["units"])


def test_apply_multi_version_requires_override(tmp_path):
    """负控：多版本未人工确认不得执行（与 ST_BATCH 同门）。"""
    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    _make_multi_version(cfg, "Same Movie")
    state = AppState(cfg_path)
    state.start_scan()
    wait_job(state)
    ids = [u["id"] for u in state.plan()["units"]]
    state.start_apply(ids, {"jellyfin_running"}, {})
    st = wait_job(state)
    assert st["status"] == "failed"
    assert "不在可执行状态" in st["error"]
    assert (cfg.source_root / "Same Movie").is_dir()      # 源未动


def test_apply_multi_version_after_override_moves(tmp_path):
    """回归（2026-11-12 反馈）：改判后放行，仅搬改判的那一部，另一部不动。"""
    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    _make_multi_version(cfg, "Same Movie")
    scifi = cfg.libraries["科幻"].path
    state = AppState(cfg_path)
    state.start_scan()
    wait_job(state)
    ids = sorted(u["id"] for u in state.plan()["units"])
    state.start_apply([ids[0]], {"jellyfin_running"}, {ids[0]: "科幻"})
    st = wait_job(state)
    assert st["status"] == "done", st["log"]
    assert st["result"]["moved"] == 1
    assert (scifi / ids[0]).is_dir()
    assert not (cfg.source_root / ids[0]).exists()
    assert (cfg.source_root / ids[1]).is_dir()


def test_preflight_and_freshness_cover_multi_version(tmp_path, monkeypatch):
    """回归：多版本单元纳入长路径/磁盘体检与 apply 前源快照校验（修复前全部跳过）。"""
    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    _make_multi_version(cfg, "混" * 165)
    state = AppState(cfg_path)
    state.start_scan()
    wait_job(state)
    plan = state.plan()
    ids = sorted(u["id"] for u in plan["units"])

    items = preflight.run_preflight(cfg, plan)
    lp = [i for i in items if i["code"] == "long_paths"]
    assert lp and any(ids[0] in d for d in lp[0]["detail"])

    usage = SimpleNamespace(total=1 << 30, used=1 << 30, free=0)
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda p: usage)
    items = preflight.run_preflight(cfg, plan)
    assert any(i["code"] == "disk_space" for i in items)

    shutil.rmtree(cfg.source_root / ids[0])
    problems = check_plan_freshness(cfg, plan)
    assert any("源已不存在" in p for p in problems)
```

### 4.3 tests/test_plan_tab.py（toast 路径 widget 级回归；导入区已有 fake_units/PlanTab）

```python
def test_multi_version_override_passes_apply_gate(qapp):
    """回归（2026-11-12 反馈）：多版本单元改判后不再被「不可执行（冲突/残留）」拦截。"""
    units = fake_units(2, seed=3)
    for u in units:
        u["status"] = "multi_version"
        u["default_selected"] = False

    class GateStubState:
        def __init__(self):
            self.preflight_ids = None

        def plan(self):
            return {"units": units}

        def start_preflight(self, ids):
            self.preflight_ids = ids

    stub = GateStubState()
    toasts: list[str] = []
    tab = PlanTab(stub, None, toast=toasts.append)
    try:
        ids = [u["id"] for u in tab.vm.rows()]
        for i in ids:
            tab.vm.checked.add(i)
            tab.vm.set_override(i, "科幻")
        assert tab.vm.can_apply() is True           # 修复前 False（拦截源）
        tab._apply_selected()
        assert "不可执行" not in "".join(toasts)     # 修复前正是这条 toast
        assert stub.preflight_ids == ids            # 走到体检而非拦截
    finally:
        tab.deleteLater()
```

先红预期：`test_multi_version_gate_requires_override`、`test_apply_multi_version_after_override_moves`、`test_preflight_and_freshness_cover_multi_version`、`test_multi_version_override_passes_apply_gate` 红；`test_plan_groups_same_provider_as_multi_version`、`test_apply_multi_version_requires_override` 为基线钉（修前即绿）。

## ⑤ 验收命令（以下命令均在项目根目录执行）

```bash
py -3.12 -m ruff check app/ui/viewmodel.py app/core/jobs.py app/core/preflight.py app/core/planner.py tests/test_viewmodel.py tests/test_flow.py tests/test_plan_tab.py
py -3.12 -m pytest tests/test_viewmodel.py tests/test_flow.py tests/test_plan_tab.py -q
py -3.12 -m pytest -q
```

全部须通过（本机仅 py -3.12 环境装有 pytest/ruff）。

## ⑥ 约束

- 只动 ② 所列 7 个文件；禁止顺手重构（不抽公共 helper，5 处判定点原地改）；禁止改 STATUS_LABELS/徽章/学习逻辑。
- 不 commit、不 push：自测全绿后报告即止，主审验收后统一提交。
- offscreen 由 test_plan_tab.py 模块头保证；test_flow.py 为纯后端流，无 Qt 依赖。

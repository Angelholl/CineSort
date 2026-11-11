# 卡：改判候选库改为「配置全量库 ∪ 计划内命中库」（2026-11-12 用户反馈）

## ① 根因

`app/ui/plan_tab.py:630-635` `_fill_libs` 的改判候选取自**当前可见行**的 target_lib 去重集合：

```python
libs = sorted({unit["target_lib"] for unit in self._rows} - {"兜底库"})
```

某库本次扫描零命中（或其行被筛选/搜索隐藏）时该库不在候选中，用户无从改判入该库——即「应改判 A，但候选只有 BCDEF 和兜底」。全量真值源 `Config.libraries`（`app/core/config.py:82`，name→Library，保持声明顺序）未被使用。

## ② 改动文件（仅此两个）

- `app/ui/plan_tab.py`
- `tests/test_plan_tab.py`

## ③ 改法

### 3.1 plan_tab.py 导入区

在 `from ..core.planner import plan_digest`（约 :40）之前按字母序插入：

```python
from ..core.config import load_config
```

### 3.2 plan_tab.py 模块级纯函数（置于 `class PlanTab` 之前、导入区之后）

```python
def override_libs(rows: list[dict], config_libs: list[str] | None) -> list[str]:
    """改判候选库：配置全量库 ∪ 计划内命中库（均不含兜底库）。

    历史缺陷：仅取当前可见行 target_lib 去重集合，某库本次扫描零命中
    （或行被筛选/搜索隐藏）时下拉框无该库，无从改判入内（2026-11-12 反馈）。
    config_libs 为 None（演示模式/配置不可读）时回退纯计划内集合。
    """
    libs = {u["target_lib"] for u in rows} - {"兜底库"}
    if config_libs:
        libs |= set(config_libs) - {"兜底库"}
    return sorted(libs)
```

### 3.3 PlanTab 新增私有方法 + `_fill_libs` 改造

`_fill_libs`（约 :630）改为：

```python
    def _config_libs(self) -> list[str] | None:
        """全量配置库名；演示模式或配置不可读时返回 None（回退计划内集合）。

        逐次读盘而非缓存：config.toml 很小、触发频率为人工点击量级，
        缓存反而需引入 hash 失效逻辑（config_hash 本身也要解析配置）。
        """
        if self.state is None:
            return None
        try:
            return list(load_config(self.state.config_path).libraries)
        except Exception:      # 配置缺失/损坏/stub 无 config_path → 优雅降级
            return None

    def _fill_libs(self) -> None:
        libs = override_libs(self._rows, self._config_libs())
        if libs != self._libs:
            self._libs = libs
            self.d_override.clear()
            self.d_override.addItems(["（不改判）"] + libs + ["兜底库"])
```

保持既有 `sorted()` 排序语义；「兜底库」仍由 addItems 显式追加，不进 `override_libs` 返回值。`_fill_libs` 之外的行为（`_show_detail` 信号屏蔽、`_on_override_changed`）一律不动。

## ④ 回归测试（先红后绿）

`tests/test_plan_tab.py`：导入区补 `from conftest import build_env`（参照 test_flow.py:13 风格）；文件末尾追加（fake_units 文件已有导入）：

```python
# ---------------- 改判候选=配置全量库（2026-11-12 用户反馈） ----------------

class _LibsStubState:
    """带 plan/config_hash/config_path 的最小 stub：改判候选回归测试用。"""

    def __init__(self, cfg_path, plan=None):
        self.config_path = cfg_path
        self._plan = plan

    def plan(self):
        return self._plan

    def config_hash(self):
        return (self._plan or {}).get("config_hash", "hash-new")


def _override_items(tab) -> list[str]:
    return [tab.d_override.itemText(i) for i in range(tab.d_override.count())]


def test_override_candidates_cover_all_config_libs(qapp, tmp_path):
    """回归（2026-11-12 反馈）：改判候选应含配置全量库，而非仅计划内命中过的库。

    旧行为：候选=当前可见行 target_lib 去重集合——某库本次扫描零命中
    （或行被筛选/搜索隐藏）时下拉框中无该库，无从改判入内。
    """
    cfg_path = build_env(tmp_path)              # 科幻/动作 两库 + 兜底
    units = fake_units(3, seed=5)
    for u in units:
        u["target_lib"] = "动作"                 # 计划内只命中 动作
    state = _LibsStubState(cfg_path, plan={"units": units, "config_hash": "hash-new"})
    tab = PlanTab(state, None, toast=lambda m: None)
    try:
        tab.table.selectRow(0)                   # 走真实路径触发 _fill_libs
        items = _override_items(tab)
        assert "科幻" in items and "动作" in items
        assert items[0] == "（不改判）" and items[-1] == "兜底库"
    finally:
        tab.deleteLater()


def test_override_candidates_demo_mode_falls_back_to_plan_libs(tab):
    """演示模式（state=None）保持旧行为：候选=计划内去重集合。"""
    tab, _ = tab
    tab.table.selectRow(0)
    expect = ["（不改判）"] + sorted(
        {u["target_lib"] for u in tab._rows} - {"兜底库"}) + ["兜底库"]
    assert _override_items(tab) == expect


def test_override_candidates_fallback_when_config_unreadable(qapp, tmp_path):
    """配置不可读（缺失/损坏）时优雅降级：候选=计划内派生集合。"""
    units = fake_units(3, seed=5)
    for u in units:
        u["target_lib"] = "动作"
    state = _LibsStubState(tmp_path / "missing.toml",
                           plan={"units": units, "config_hash": "hash-new"})
    tab = PlanTab(state, None, toast=lambda m: None)
    try:
        tab.table.selectRow(0)
        items = _override_items(tab)
        assert "科幻" not in items and "动作" in items
    finally:
        tab.deleteLater()
```

先红步骤：先只加测试跑用例 1，确认失败原因=「科幻」缺失（而非其他报错），再落 3.1–3.3 实现转绿。

## ⑤ 验收命令（以下命令均在项目根目录执行）

```bash
py -3.12 -m ruff check app/ui/plan_tab.py tests/test_plan_tab.py
py -3.12 -m pytest tests/test_plan_tab.py -q
py -3.12 -m pytest tests/test_viewmodel.py tests/test_planner.py -q
```

全部须通过（本机仅 py -3.12 环境装有 pytest/ruff）。

## ⑥ 约束

- 只动上列两个文件；禁止顺手重构、禁止改排序语义、禁止动 viewmodel.py。
- 不 commit、不 push：自测全绿后报告即止，主审验收后统一提交。
- offscreen 测试环境已由 test_plan_tab.py 模块头 `QT_QPA_PLATFORM=offscreen` 保证，勿另设。

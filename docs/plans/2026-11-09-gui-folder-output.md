# 实现计划：GUI 目录浏览 + 本次输出目录（会话级覆盖）+ 按类别子文件夹

- 日期：2026-11-09
- 基线版本：v0.5.1（本文所有 `文件:行号` 均为当前基线，施工时若行号漂移，以符号定位为准）
- 需求来源：owner 已拍板三条（配置页目录浏览 / 计划页本次输出目录 / 按类别子文件夹开关）
- 计划真值：本文件（拆解与验收口径），实现交给编程执行者

---

## 0. 现状核实（已逐一读取确认）

| 关注点 | 位置 | 现状 |
|---|---|---|
| 配置页三个路径手填框 | `app/ui/config_tab.py:73-75` | `f_source_root` / `f_fallback_path` / `f_staging_dir`，QLineEdit，无浏览按钮 |
| 表单行布局 | `app/ui/config_tab.py:95-116` | `rows` 列表 + QGridLayout，复合控件已有 `_hbox` 先例（config_tab.py:208-216） |
| 库表添加按钮 | `app/ui/config_tab.py:136-137` | `btn_add.clicked.connect(self._add_library_row)`，总是插入空行 |
| `_add_library_row` 程序化复用 | `app/ui/config_tab.py:278,283-288` | `_fill_form` 用它回填库行——签名 `(values=None)` 不得改 |
| dirty 机制 | `app/ui/config_tab.py:133,188-190` | `itemChanged`/`textChanged` → `_mark_dirty`（`_loading` 期间豁免） |
| 演示模式禁用清单 | `app/ui/config_tab.py:229-237` | `_set_form_enabled` 枚举控件，新控件须加入 |
| 计划页底部操作条 | `app/ui/plan_tab.py:155-175` | summary + stretch + 4 按钮（全选/清空/扫描/执行）；`btn_clear` 已被「清空选择」占用（plan_tab.py:166-167） |
| 计划页执行链 | `app/ui/plan_tab.py:371-409` | `_apply_selected` → 体检 → `BlockConfirmDialog` → `_start_apply` → `state.start_apply(ids, acks, overrides)`（plan_tab.py:405） |
| 计划页 busy 禁用 | `app/ui/plan_tab.py:346-348` | `_set_busy` 枚举 4 按钮 |
| 演示模式禁用 | `app/ui/plan_tab.py:78-81` | 仅 `btn_scan`/`btn_apply` |
| 计划页刷新重建 vm | `app/ui/plan_tab.py:243-263` | digest 不变复用 vm；digest 变/force 重建 `PlanViewModel`（demo 分支 249-252） |
| viewmodel（纯逻辑零 Qt） | `app/ui/viewmodel.py:90-209` | `overrides`/`effective_target_lib`（viewmodel.py:196-206）先例：会话级状态挂 vm |
| 目标目录组合规则 | `app/core/planner.py:70` | `dst_dir = Path(dec.target_path) / u.dst_name`；unit 落盘字段 `dst_name`/`target_root`/`target_lib`（planner.py:105-108） |
| 人工改判执行通道 | `app/core/jobs.py:156-171` | run_apply 内存改写 `target_lib`/`target_root`/`dst_dir`，**不写 plan.json**（本卡输出覆盖复用同一通道） |
| run_apply 现顺序 | `app/core/jobs.py:135-171` | freshness(141) → 预检(144) → 阻断门(145-148) → 过滤/状态检查(149-154) → 改判循环(156-171)；freshness 只读源侧字段（planner.py:202-231） |
| staging 根推导 | `app/core/fsops.py:35-37` | `staging_for_root(root) = Path(root).parent / ".nfo-sorter-staging"` |
| 传输语义 | `app/core/fsops.py:80-134` | `transfer_dir` 同卷 `os.rename`（**不建父目录**，fsops.py:88-90）；`transfer_loose` 自建 `dst_dir.mkdir(parents=True)`（fsops.py:134） |
| 预检 | `app/core/preflight.py:49-141` | 磁盘空间按 `u["dst_dir"]` 分盘（preflight.py:87）；staging 残留扫 `staging_roots_for(cfg)`（preflight.py:104-112，根集合 preflight.py:38-46） |
| 互不嵌套校验语义 | `app/core/config.py:116-122` | `_check_overlap`：相等拒绝 + 双向 `is_sub_path`（大小写不敏感，config.py:28-37） |
| 类别（决策 target） | `app/core/classifier.py:27-34` | `Decision.target` = 库名（含“兜底库”）；库名禁止 `/`、`\`（config.py:153）→ 可安全做文件夹名 |
| start_apply 调用方 | `app/state.py:92-96`、`app/ui/plan_tab.py:405`、`tests/test_flow.py:55,90,142` | 无 HTTP 层残留；默认参数扩展可全兼容 |
| 测试范式 | `tests/conftest.py:35-72`、`tests/test_config_tab.py:116-136`、`tests/test_plan_tab.py:23-35` | offscreen + duck-typing StubState + `build_env` 完整环境；`fake_units` 无 `dst_name` 键（vm 新方法不得依赖它） |
| Qt-free 守卫 | `tests/test_viewmodel.py:56-63` | viewmodel 不得拖入 PySide6；新增 `pathlib` 导入无碍 |

全仓库确认无 `QFileDialog` 使用（需求 1 为首例）。现有测试数（已逐一数过）：test_config.py 11、test_viewmodel.py 21、test_flow.py 6、test_state.py 2、test_config_tab.py 14、test_plan_tab.py 9。

---

## 1. 设计决策（实施者必须照此执行，不得自行变更）

- **D1 优先级：本次输出目录 > 单元改判 > 计划库路径。**
  输出目录开启时，所有勾选单元的实际目标根一律为输出目录；改判仍保留 `target_lib` 语义——它决定按类别模式下的子文件夹名与自学习沉淀（jobs.py:228-234 用 `target_lib` 记票）。
- **D2 「按类别建子文件夹」默认开启。**
  依据仓库惯例：`plot.enabled`/`learning.enabled` 的加载默认均为开启（config.py:182-186、191-194），配置页复选框直接映射这些默认；且产品核心语义是“归类”，平铺输出是例外场景，取消勾选即可平铺。
- **D3 会话级生命周期：** 输出目录与按类别开关只存在内存（`PlanViewModel`），不写 config.toml、不写 plan.json；重新扫描重建 vm 时自动清空（与“改判”同生命周期口径）。
- **D4 校验位置：** 权威校验在 `jobs.run_apply`（后台线程）调用新增纯函数 `check_session_root`；UI 选目录时**不做**同步磁盘校验（D-20261102-01 线程纪律：UI 线程不读配置）。校验失败发生在任何文件操作之前 → 任务失败，无副作用。
- **D5 planner 不改：** 计划冻结/freshness 纪律不动；`planner.py:70` 的 `target_root/dst_name` 组合规则在 jobs 覆盖通道原样复用，不新增命名逻辑。
- **D6 类别名 = `effective_target_lib`（改判后的目标库名，含“兜底库”）。** 库名已禁分隔符（config.py:153），可直接作文件夹名。

### 待 owner 复核的拍板点（不阻塞实施，按 D1 默认执行）

1. D1 中“输出目录压过逐单元改判”的解释取舍——若 owner 希望“改判单元仍进原库”，只需在 jobs 输出循环跳过 `overrides` 命中的单元，改动点已隔离在单处循环内。

---

## 2. 签名变更总表（验收时逐条比对）

| 符号 | 现签名 | 新签名 | 兼容性 |
|---|---|---|---|
| `AppState.start_apply` (state.py:92-96) | `(ids, acks, overrides)` | `(ids, acks, overrides, output_root: str \| None = None, group_by_category: bool = True)` | 默认参数，`tests/test_flow.py` 现有 3 参调用不变 |
| `jobs.run_apply` (jobs.py:135-136) | `(state, job, ids, acks, overrides)` | 追加 `output_root: str \| None = None, group_by_category: bool = True` | 同上 |
| `preflight.run_preflight` (preflight.py:49-50) | `(cfg, plan=None, selected_ids=None)` | 追加 `extra_staging_roots: list[Path] \| None = None` | state.py:135-139、jobs.py:101-114 现调用不变 |
| `ConfigTab._add_library_row` (config_tab.py:283) | `(values=None)` | **不变**（`_fill_form` 仍调用） | — |
| 新增 `config.check_session_root` | — | `(output_root: Path \| str, cfg: Config) -> str \| None`（None=合法，str=错误文案） | 纯函数零 Qt |
| 新增 `PlanViewModel.output_root` / `group_by_category` / `set_output_root(path: str \| None)` / `effective_output_root(unit: dict) -> str \| None` | — | 见 Task-02 | 纯逻辑零 Qt |

---

## 3. 任务板

> 每任务收尾必须跑该任务的验证命令且全绿；步骤粒度 2-5 分钟。新增测试 31 个（6+5+1+5+1+6+7），现有测试一律不改不删（回归基线只增不减）。

### 基线动作（Task-00，开工前 2 分钟）

- 操作：运行 `python -m pytest --collect-only -q 2>&1 | tail -1`，把收集到的测试总数记录到本文件末尾「实施记录」节（`基线=N`）。
- 验收：`docs/plans/2026-11-09-gui-folder-output.md` 末尾出现 `基线=<数字>`。收尾时断言 `新总数 >= N + 31`。

---

### Task-01 `check_session_root` 纯函数（需求 2 的校验语义）

- 目标文件：`app/core/config.py`（修改）、`tests/test_config.py`（新增测试）
- 操作类型：修改 + 新增测试
- 依赖：无

步骤：
1. 在 `app/core/config.py` 的 `_check_overlap`（config.py:116-122）之后新增函数，镜像其三段语义（相等 / 单向嵌套 / 反向嵌套），复用 `normcase`（config.py:28-29）与 `is_sub_path`（config.py:32-37）：

   ```python
   def check_session_root(output_root: Path | str, cfg: Config) -> str | None:
       """本次输出目录校验（会话级，不进 config.toml）：必须存在，且与
       源根 / 库根 / 兜底库互不嵌套（镜像 _check_overlap 语义）。
       返回错误文案；None = 合法。"""
       p = Path(output_root)
       if not p.is_dir():
           return f"输出目录不存在或不是目录：{p}"
       roots: list[tuple[str, Path]] = [("源目录", cfg.source_root)]
       roots += [(f"媒体库[{name}]", lib.path)
                 for name, lib in cfg.libraries.items()]
       roots.append(("兜底库", cfg.fallback_path))
       for name, root in roots:
           if normcase(p) == normcase(root):
               return f"输出目录与{name}不能是同一个目录：{root}"
           if is_sub_path(p, root):
               return f"输出目录（{p}）不能位于{name}（{root}）内部"
           if is_sub_path(root, p):
               return f"{name}（{root}）不能位于输出目录（{p}）内部"
       return None
   ```

2. 在 `tests/test_config.py` 末尾新增 6 个测试（沿用 `build_env`，其布局：`src=tmp/src`、库=`tmp/libs/{科幻,动作}`、兜底=`tmp/未分类`）：

   | 测试名 | 输入 | 断言要点 |
   |---|---|---|
   | `test_session_root_accepts_sibling_dir` | `(tmp_path/"out")` 已 mkdir | 返回 `None` |
   | `test_session_root_missing_dir_rejected` | `tmp_path/"ghost"` 不创建 | 文案含 `"不存在"` |
   | `test_session_root_same_as_source_rejected` | `str(cfg.source_root)` | 文案含 `"不能是同一个目录"` 且含 `"源目录"` |
   | `test_session_root_inside_source_rejected` | `cfg.source_root/"sub"`（mkdir） | 文案含 `"不能位于源目录"` |
   | `test_session_root_containing_library_rejected` | `tmp_path/"libs"`（库的父目录） | 文案含 `"媒体库[科幻]不能位于输出目录内部"`（双向嵌套分支） |
   | `test_session_root_inside_fallback_rejected` | `cfg.fallback_path/"sub"`（mkdir） | 文案含 `"不能位于兜底库内部"` |

   断言写法：`err = check_session_root(p, cfg); assert err is not None and "关键词" in err`。

验证命令：`python -m pytest tests/test_config.py -q`（现有 11 个 + 新 6 个，全绿）

---

### Task-02 PlanViewModel 会话级输出状态（需求 2/3 的决策逻辑归位）

- 目标文件：`app/ui/viewmodel.py`（修改）、`tests/test_viewmodel.py`（新增测试）
- 操作类型：修改 + 新增测试
- 依赖：无

步骤：
1. `viewmodel.py` 顶部加 `from pathlib import Path`（注意：Qt-free 守卫 `test_viewmodel_importable_without_qt` 只禁 PySide6，pathlib 合规）。
2. `PlanViewModel.__init__`（viewmodel.py:93-100）在 `self.query` 之后追加：

   ```python
   self.output_root: str | None = None   # 本次输出目录（会话级）
   self.group_by_category: bool = True   # 输出目录下按类别建子文件夹（D2 默认开）
   ```

3. 在 `effective_target_lib`（viewmodel.py:205-206）附近新增两个方法：

   ```python
   def set_output_root(self, path: str | None) -> None:
       """本次输出目录（会话级）；None/空串 = 撤销，回到计划库路径。"""
       self.output_root = (path or "").strip() or None

   def effective_output_root(self, unit: dict) -> str | None:
       """该单元本次实际目标根；未设输出目录时 None（沿用计划库根）。
       类别 = 改判后的目标库名（effective_target_lib，含「兜底库」）。"""
       if not self.output_root:
           return None
       root = Path(self.output_root)
       if self.group_by_category:
           root = root / self.effective_target_lib(unit)
       return str(root)
   ```

   注意：不得在本层读取 `unit["dst_name"]`（demo_units 无此键）；dst 组合留在 jobs。

4. `tests/test_viewmodel.py` 新增 5 个测试（复用现有 `make_unit`/`units` 夹具，make_unit 无 `dst_name`，恰好验证不依赖）：

   | 测试名 | 断言要点 |
   |---|---|
   | `test_output_root_defaults_none_and_group_true` | `model.output_root is None`；`model.group_by_category is True` |
   | `test_set_output_root_blank_clears` | `set_output_root("  ")`、`set_output_root("")`、`set_output_root(None)` 后均 `output_root is None`；`set_output_root("E:/out")` 后 == `"E:/out"` |
   | `test_effective_output_root_groups_by_effective_lib` | `set_output_root(r"E:\out")`：A（科幻）→ 含 `"科幻"`；D（兜底库）→ `rf"E:\out\兜底库"`；再 `set_override("A 规则", "喜剧")` 后 A 变 `rf"E:\out\喜剧"`（改判决定类别） |
   | `test_effective_output_root_flat_when_group_off` | `group_by_category = False` 后任意 unit → `"E:\\out"`，不含库名 |
   | `test_effective_output_root_none_without_output` | 未设输出目录时 `effective_output_root(unit) is None`（即使改判过） |

验证命令：`python -m pytest tests/test_viewmodel.py -q`（现有 21 个 + 新 5 个，全绿；`test_viewmodel_importable_without_qt` 必须仍绿）

---

### Task-03 preflight 支持额外 staging 根（需求 2 的残留检测延伸）

- 目标文件：`app/core/preflight.py`（修改）、`tests/test_flow.py`（新增 1 个测试）
- 操作类型：修改 + 新增测试
- 依赖：无

步骤：
1. `run_preflight` 签名（preflight.py:49-50）追加 `extra_staging_roots: list[Path] | None = None`。
2. staging 残留检查（preflight.py:105）由 `find_staging_leftovers(staging_roots_for(cfg))` 改为：

   ```python
   roots = set(staging_roots_for(cfg))
   for p in extra_staging_roots or ():
       roots.add(Path(p))
   leftovers = find_staging_leftovers(sorted(roots, key=str))
   ```

3. `tests/test_flow.py` 新增 `test_preflight_extra_staging_roots_block`：
   - `cfg_path = build_env(tmp_path)`；`cfg = load_config(cfg_path)`；
   - 造残留：`(tmp_path/"out"/".nfo-sorter-staging"/"some-session").mkdir(parents=True)`，并在其中写文件 `".incomplete-20261109"`（`find_staging_leftovers` 语义：staging 根下一级目录内含 `.incomplete-*` 文件即残留，fsops.py:192-213）；
   - `items = preflight.run_preflight(cfg, None, extra_staging_roots=[tmp_path/"out"/".nfo-sorter-staging"])`；
   - 断言：存在 `{"level": "block", "code": "staging_leftover"}` 项；对照组——同一残留不传 `extra_staging_roots` 时不报（证明参数生效、不影响默认行为）。

验证命令：`python -m pytest tests/test_flow.py -q`

---

### Task-04 jobs.run_apply 输出覆盖通道（需求 2 核心）

- 目标文件：`app/core/jobs.py`（修改）、`tests/test_flow.py`（新增 5 个测试）
- 操作类型：修改 + 新增测试
- 依赖：Task-01、Task-03

步骤：
1. **签名**（jobs.py:135-136）：`def run_apply(state, job: Job, ids: list[str], acks: set[str], overrides: dict[str, str], output_root: str | None = None, group_by_category: bool = True) -> None`。导入 `check_session_root`（加入 jobs.py:12 `from .config import load_config` 处）。
2. **顺序重排**：把现状“改判循环”（jobs.py:156-171，含 `# 逐行覆盖目标库` 注释）从预检之后**整体前移**到状态检查（jobs.py:149-154）之后、预检（现 144 行）之前。语义依据：改判/输出改写的是内存 dict 的 `target_lib/target_root/dst_dir`，而 `check_plan_freshness` 只读源侧字段（planner.py:202-231），提前不产生任何行为差异；前移后预检的磁盘空间检查（preflight.py:87 读 `u["dst_dir"]`）才能按**输出盘**核算——这是本任务的核心正确性动机。
3. **输出覆盖块**（插在改判循环之后、`run_preflight` 调用之前，只计算不改盘）：

   ```python
   extra_roots = None
   if output_root:
       err = check_session_root(output_root, cfg)
       if err:
           raise RuntimeError(f"输出目录不可用：{err}")   # 先于任何文件操作
       out = Path(output_root)
       for u in units:
           root = out / u["target_lib"] if group_by_category else out
           u["target_root"] = str(root)
           u["dst_dir"] = str(root / u["dst_name"])   # 复用 planner.py:70 组合规则
           u["evidence"] = list(u["evidence"]) + ["本次输出目录（会话级，不改全局配置）"]
       extra_roots = sorted({fsops.staging_for_root(Path(u["target_root"]))
                             for u in units}, key=str)
       job.log(f"本次输出目录：{output_root}"
               + ("（按类别建子文件夹）" if group_by_category else "（平铺）"))
   ```

4. **预检调用**（jobs.py:144）改为 `preflight.run_preflight(cfg, plan, selected_ids=set(ids), extra_staging_roots=extra_roots)`。
5. **建父目录**（插在阻断门 `raise RuntimeError("预检未通过…")` 之后、`job.total = len(units)` 之前）——必须在阻断门之后，避免被阻断时留下空类别目录：

   ```python
   if output_root:
       for root in sorted({u["target_root"] for u in units}):
           Path(root).mkdir(parents=True, exist_ok=True)   # transfer_dir 同卷 rename 不建父目录
   ```

6. `tests/test_flow.py` 新增 5 个集成测试（全部沿用 `env_state` 夹具：两部影片 → 科幻/动作；跨盘 copy 或同卷 rename 均被覆盖）：

   | 测试名 | 步骤要点 | 断言要点 |
   |---|---|---|
   | `test_apply_session_output_flat` | 扫描→`out=tmp_path/"本次输出"` mkdir→`state.start_apply(list(units), {"jellyfin_running"}, {}, output_root=str(out), group_by_category=False)`→wait_job | `result["moved"]==2`；`(out/"Space War (2021)").is_dir()`；`(out/"Gun Fight (2022)").is_dir()`；源目录两单元消失 |
   | `test_apply_session_output_group_by_category` | 同上但 `group_by_category=True` | `(out/"科幻"/"Space War (2021)").is_dir()`；`(out/"动作"/"Gun Fight (2022)").is_dir()` |
   | `test_apply_session_output_not_persisted_to_plan` | 执行 flat 输出后读 `state.plan()` | 所有 `unit["dst_dir"]` 仍指向原库路径（不含“本次输出”）——会话覆盖不落盘；`config.toml` 文本不含输出路径 |
   | `test_apply_session_output_rejects_invalid_root` | `output_root=str(tmp_path/"ghost")`（不存在） | `status=="failed"`、`"输出目录不可用" in error`；两部影片仍在源目录（零副作用） |
   | `test_apply_session_output_inside_source_rejected` | `out=env.source_root/"out"` mkdir 后作为 output_root | 同上断言失败与零副作用（互不嵌套语义在执行通道生效） |

   注意 acks 传 `{"jellyfin_running"}`（沿用 test_flow.py:55 惯例）；wait_job 复用现有辅助。

验证命令：`python -m pytest tests/test_flow.py -q`（现有 6 个 + 新 6 个，全绿）

---

### Task-05 AppState.start_apply 透传（需求 2 接线）

- 目标文件：`app/state.py`（修改）、`tests/test_state.py`（新增 1 个测试）
- 操作类型：修改 + 新增测试
- 依赖：Task-04

步骤：
1. state.py:92-96 改为：

   ```python
   def start_apply(self, ids: list[str], acks: set[str],
                   overrides: dict[str, str], output_root: str | None = None,
                   group_by_category: bool = True) -> dict:
       self.jobs.start("apply", lambda job: jobs_mod.run_apply(
           self, job, ids, acks, overrides, output_root, group_by_category))
       return {"ok": True}
   ```

2. `tests/test_state.py` 新增 `test_start_apply_passes_output_params`：monkeypatch `app.core.jobs.run_apply` 为记录参数的 fake（state.py 经 `jobs_mod.run_apply` 属性在调用期解析，monkeypatch 生效）；`AppState(tmp_path/"config.toml")` 后调 `state.start_apply(["a"], {"jellyfin_running"}, {}, output_root="E:/out", group_by_category=False)`；由于 `JobManager.start` 立即起线程，轮询（0.05s 间隔、5s 超时）直到捕获非空，断言捕获参数 == `(["a"], {"jellyfin_running"}, {}, "E:/out", False)`。

验证命令：`python -m pytest tests/test_state.py -q`（现有 2 个 + 新 1 个，全绿）

---

### Task-06 配置页目录浏览（需求 1）

- 目标文件：`app/ui/config_tab.py`（修改）、`tests/test_config_tab.py`（新增 6 个测试）
- 操作类型：修改 + 新增测试
- 依赖：无

步骤：
1. imports（config_tab.py:17-34）加 `QFileDialog`；文件头加 `from pathlib import Path`。
2. 新增两个小工具方法（放在 `_hbox` 附近，config_tab.py:206-216 区域）：

   ```python
   def _path_row(self, edit: QLineEdit, caption: str, attr: str) -> QWidget:
       """路径行：输入框(伸展) + 「浏览…」按钮；按钮以 attr 名存为实例属性。"""
       w = QWidget()
       h = QHBoxLayout(w)
       h.setContentsMargins(0, 0, 0, 0)
       h.setSpacing(8)
       h.addWidget(edit, 1)
       btn = QPushButton("浏览…")
       btn.clicked.connect(lambda _=False, e=edit, c=caption: self._browse_dir(e, c))
       setattr(self, attr, btn)
       h.addWidget(btn)
       return w

   def _browse_dir(self, edit: QLineEdit, caption: str) -> None:
       chosen = QFileDialog.getExistingDirectory(self, caption, edit.text().strip())
       if chosen:
           edit.setText(chosen)   # textChanged → _mark_dirty（config_tab.py:188-190 自动生效）
   ```

3. `rows`（config_tab.py:95-110）中三行改为（三个按钮属性名固定，供测试与禁用清单引用）：

   ```python
   ("源目录", self._path_row(self.f_source_root, "选择源目录", "btn_browse_source")),
   ("兜底库", self._path_row(self.f_fallback_path, "选择兜底库目录", "btn_browse_fallback")),
   ("暂存目录", self._path_row(self.f_staging_dir, "选择暂存目录（可留空）", "btn_browse_staging")),
   ```

   其余行不动；`grid.setColumnStretch(1, 1)`（config_tab.py:116）配合 `_path_row` 内 `addWidget(edit, 1)` 使输入框仍伸展。
4. 库表添加按钮（config_tab.py:136-137）：`btn_add` 提升为 `self.btn_add`（与 `btn_save`/`btn_reload` 命名风格一致），connect 改为 `self._on_add_library_clicked`，新增方法：

   ```python
   def _on_add_library_clicked(self) -> None:
       """添加库 = 浏览选目录；取消则不插行（语义变化：旧版总是插空行）。"""
       chosen = QFileDialog.getExistingDirectory(self, "选择库目录", "")
       if not chosen:
           return
       self._add_library_row([Path(chosen).name, str(chosen), "", ""])
   ```

   `_add_library_row(values=None)`（config_tab.py:283-288）签名与实现**不得改动**（`_fill_form` 在 config_tab.py:278 仍调用）；新行插入触发 `itemChanged`（config_tab.py:133）自动置 dirty，无需手动标记。库名冲突/非法名不在此拦截，交由保存时的 ConfigError 横幅（既有语义）。
5. 演示模式：`_set_form_enabled`（config_tab.py:229-237）的枚举元组追加 `self.btn_browse_source, self.btn_browse_fallback, self.btn_browse_staging`。
6. `tests/test_config_tab.py` 新增 6 个测试（monkeypatch 静态方法：`monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: <返回值>)`，必须在 click 之前打补丁；offscreen 下不会弹原生对话框）：

   | 测试名 | 步骤与断言要点 |
   |---|---|
   | `test_browse_source_fills_field_and_marks_dirty` | 补丁返回 `"E:/pick/src"` → `tab.btn_browse_source.click()` → `f_source_root.text()=="E:/pick/src"`、`tab._dirty is True` |
   | `test_browse_cancel_keeps_field` | 补丁返回 `""` → click 后 text 不变、`_dirty` 保持 False（初态未动过） |
   | `test_browse_fallback_and_staging_wired` | 分别补丁返回 `"E:/fb"`、`"E:/st"` → 点 `btn_browse_fallback`/`btn_browse_staging` → 两个 lineEdit 文本各自更新 |
   | `test_add_library_via_dialog_prefills_row` | 初态 2 行（describe 回填）→ 补丁返回 `"E:/media/新库"` → `tab.btn_add.click()` → `lib_table.rowCount()==3`、`item(2,0).text()=="新库"`、`item(2,1).text()=="E:/media/新库"`、`item(2,2).text()==""`、`_dirty is True` |
   | `test_add_library_dialog_cancel_adds_nothing` | 补丁返回 `""` → `tab.btn_add.click()` → `rowCount()==2`、`_dirty is False` |
   | `test_demo_mode_disables_browse_controls` | `ConfigTab(None, ...)` → 三个 `btn_browse_*` `isEnabled() is False` |

   既有回归必须原样通过：`test_demo_mode_disables_all`、`test_form_filled_from_describe`（验证 `_fill_form`→`_add_library_row` 复用未破坏）、`test_main_window_static_wiring`。

验证命令：`python -m pytest tests/test_config_tab.py -q`（现有 14 个 + 新 6 个，全绿）

---

### Task-07 计划页本次输出目录 + 按类别开关（需求 2/3 的 UI）

- 目标文件：`app/ui/plan_tab.py`（修改）、`tests/test_plan_tab.py`（新增 7 个测试）
- 操作类型：修改 + 新增测试
- 依赖：Task-02、Task-05

步骤：
1. imports（plan_tab.py:11-33）加 `QFileDialog`（`QCheckBox/QLabel/QLineEdit/QPushButton` 已导入）。
2. `_build` 底部条（plan_tab.py:155-175）：在 `bl.addStretch(1)`（plan_tab.py:163）之后、`btn_all` 循环（plan_tab.py:173-174）之前插入：

   ```python
   self.lbl_out = QLabel("本次输出")
   self.lbl_out.setProperty("dim", True)
   self.lbl_out.setToolTip("仅对本次执行生效，不写入全局配置；重新扫描后自动清空")
   self.f_out_dir = QLineEdit()
   self.f_out_dir.setReadOnly(True)
   self.f_out_dir.setPlaceholderText("未选择（按计划库路径输出）")
   self.f_out_dir.setFixedWidth(220)
   self.btn_browse_out = QPushButton("浏览…")
   self.btn_browse_out.clicked.connect(self._browse_output_dir)
   self.btn_clear_out = QPushButton("清除")
   self.btn_clear_out.setEnabled(False)
   self.btn_clear_out.clicked.connect(self._clear_output_dir)
   self.chk_by_category = QCheckBox("按类别建子文件夹")
   self.chk_by_category.setChecked(True)          # D2 默认开
   self.chk_by_category.toggled.connect(self._on_category_toggled)
   for w in (self.lbl_out, self.f_out_dir, self.btn_browse_out,
             self.btn_clear_out, self.chk_by_category):
       bl.addWidget(w)
   ```

   命名红线：不得复用既有 `self.btn_clear`（「清空选择」，plan_tab.py:166-167）。
3. 新增交互方法（放在 `_start_apply` 附近）：

   ```python
   def _browse_output_dir(self) -> None:
       if self.state is None or self.vm is None:
           return
       chosen = QFileDialog.getExistingDirectory(
           self, "选择本次输出目录", self.vm.output_root or "")
       if not chosen:
           return
       self.vm.set_output_root(chosen)
       self._sync_output_controls()
       self.toast(f"本次输出目录已设置（仅对下次执行生效）：{chosen}")

   def _clear_output_dir(self) -> None:
       if self.vm is None:
           return
       self.vm.set_output_root(None)
       self._sync_output_controls()

   def _on_category_toggled(self, on: bool) -> None:
       if self.vm is not None:
           self.vm.group_by_category = on

   def _sync_output_controls(self) -> None:
       if self.vm is None:
           return
       self.f_out_dir.setText(self.vm.output_root or "")
       self.chk_by_category.setChecked(self.vm.group_by_category)
       has = bool(self.vm.output_root)
       self.btn_clear_out.setEnabled(has)
       self.chk_by_category.setEnabled(has)
   ```

4. 演示模式禁用（plan_tab.py:78-81）：循环改为 `(self.btn_scan, self.btn_apply, self.btn_browse_out, self.btn_clear_out)` 并补 `self.f_out_dir.setEnabled(False)`、`self.chk_by_category.setEnabled(False)`（tooltip 同现有文案）。注意 init 顺序：`refresh(force=True)`（plan_tab.py:77）先于演示禁用（plan_tab.py:78），禁用不被 `_sync_output_controls` 冲掉。
5. busy 禁用（plan_tab.py:346-348）：`_set_busy` 追加一段，把 `(self.btn_browse_out, self.btn_clear_out, self.chk_by_category, self.f_out_dir)` 设为 `not busy and self.state is not None`（任务运行中禁止改会话参数；任务结束 `_on_job_finished → refresh(force=True) → _sync_output_controls` 恢复 has-root 语义）。
6. vm 重建同步：`refresh()`（plan_tab.py:243-263）在 `self._update_summary()`（plan_tab.py:263）之后追加 `self._sync_output_controls()`——重扫重建 vm 后输出选择自动清空回显（D3）。
7. 提交透传：`_start_apply`（plan_tab.py:402-409）改为：

   ```python
   self.state.start_apply(ids, acks, overrides,
                          output_root=self.vm.output_root,
                          group_by_category=self.vm.group_by_category)
   ```

8. `tests/test_plan_tab.py` 新增 7 个测试（`tab` 夹具 = 演示模式 PlanTab）：

   | 测试名 | 步骤与断言要点 |
   |---|---|
   | `test_output_controls_initial_state` | `f_out_dir.text()==""` 且 placeholder 含 `"未选择"`；`chk_by_category.isChecked() is True`；`btn_clear_out.isEnabled() is False` |
   | `test_browse_output_sets_vm_and_clear_enabled` | 补丁 QFileDialog 返回 `"E:/out"` → `tab.btn_browse_out.click()` → `tab.vm.output_root=="E:/out"`、`f_out_dir.text()=="E:/out"`、`btn_clear_out.isEnabled() is True`、`chk_by_category.isEnabled() is True` |
   | `test_clear_output_resets` | 先浏览置值，再 `tab.btn_clear_out.click()` → `vm.output_root is None`、文本空、清除钮与复选框回到禁用 |
   | `test_category_checkbox_syncs_vm` | `tab.chk_by_category.setChecked(False)` → `tab.vm.group_by_category is False` |
   | `test_output_controls_disabled_in_demo` | `tab` 夹具即演示模式：browse/clear/`f_out_dir`/chk 全部 `isEnabled() is False` |
   | `test_output_controls_reset_after_rebuild` | 浏览置值后 `tab.refresh(force=True)`（demo 分支重建 vm，plan_tab.py:249-252）→ `vm.output_root is None`、`f_out_dir.text()==""`、chk 回到勾选态 |
   | `test_start_apply_forwards_output_params` | 文件内定义 `class ApplyStubState`：`plan()` 返回 `{"units": fake_units(5, seed=1)}`；`start_apply(ids, acks, overrides, output_root=None, group_by_category=True)` 记录调用。`PlanTab(stub, None, toast=...)` → `tab.vm.set_output_root("E:/out")` → `tab._start_apply(["u1"], set(), {})` → 断言记录 `(["u1"], set(), {}, "E:/out", True)` |

   既有回归必须原样通过：`test_renders_all_demo_rows`、`test_demo_mode_disables_job_buttons`、`test_main_window_demo_builds_and_closes` 等（新控件不得影响渲染路径）。

验证命令：`python -m pytest tests/test_plan_tab.py -q`（现有 9 个 + 新 7 个，全绿）

---

### Task-08 全量回归 + GUI 冒烟 + 基线核对（收口）

- 目标文件：无新改动；只验证
- 依赖：Task-01~07 全部完成

步骤：
1. `python -m pytest -q` 全量（必须 0 failed；用例总数 ≥ 基线 + 31）。
2. GUI 冒烟（offscreen 截图，不真扫盘）：
   `python -m app.ui.main_window --demo --screenshot artifacts/2026-11-09-plan-tab.png --tab 0`
   —— 验收：截图生成成功、计划页底部出现「本次输出 / 未选择（按计划库路径输出）/ 浏览… / 清除 / 按类别建子文件夹」控件且演示模式下浏览/清除禁用带 tooltip。
3. 手工黑盒走查（真实环境，若具备）：`python -m app.ui.main_window`——配置页三个浏览按钮各选一次目录并保存配置成功；计划页浏览选一个**不在源/库内**的目录 → 执行 1 部 → 结果落在「输出目录/类别/片名 (年份)」；再选一个**源目录内**的目录 → 任务失败 toast，文件未被移动。
4. 按 GUI 变更提交规则做提交前目验（GUI 已验证/未验证须写入提交信息）。
5. 在本文件末尾「实施记录」补一行：`收尾=<新总数>`。

验证命令：见步骤 1-2。

---

## 4. 边界输入清单（验收时逐条核对）

| 边界 | 行为 | 由谁保证 |
|---|---|---|
| 浏览取消（返回空串） | 不改值、不置 dirty、不插行 | Task-06 步骤 2/4 + 测试 |
| 输出目录为空串/纯空白 | `set_output_root` 归一为 None（回退库路径） | Task-02 测试 |
| 输出目录不存在（对话框理论不产生，防御 jobs） | `check_session_root` →「不存在」，任务失败零副作用 | Task-01/04 测试 |
| 输出目录 == 源目录 / 在源目录内 / 包含任一库根 / 在兜底库内 | 全部拒绝（镜像 config.py:116-122 语义，大小写/斜杠不敏感） | Task-01 测试 |
| 兜底单元按类别输出 | 落「输出目录/兜底库/片名 (年份)」 | Task-02/04 测试 |
| 改判单元按类别输出 | 类别 = 改判后库名；自学习仍记改判库 | Task-02 测试 + D1 |
| 任务运行中改控件 | 控件禁用 | Task-07 步骤 5 |
| 重扫/重建 vm | 输出选择清空（chk 复位 True） | Task-07 步骤 6 + 测试 |
| 被预检阻断 | 不留空类别目录（mkdir 在阻断门之后） | Task-04 步骤 5 |
| 输出盘空间不足 | 预检磁盘检查按输出盘 dst_dir 核算（顺序重排动机） | Task-04 步骤 2 |
| 输出 staging 半成品残留 | `extra_staging_roots` 使预检/执行门报 `staging_leftover`（硬阻断） | Task-03/04 |
| plan.json / config.toml | 不含输出路径（会话级不落盘） | Task-04 `test_apply_session_output_not_persisted_to_plan` |
| 同名冲突/半成品等计划状态 | 输出模式不重算计划状态（计划冻结纪律 D5）；目标占用靠执行期 `dst.exists()` 终检（jobs.py 现有 TOCTOU 逻辑） | 既有代码 + 已知边界 #6 |

---

## 5. 已知边界与明确不做（记录在案，验收不得当作缺陷）

1. PlanTab 首次体检（`state.start_preflight`）不携带输出参数，其弹窗不扫输出 staging 根；权威拦截在 `run_apply` 内置预检（`staging_leftover` 不可越过），不影响安全性。
2. 按类别模式下跨盘搬运的 staging 目录为 `输出目录/.nfo-sorter-staging`（隐藏目录，位于输出目录内）；成功后内容自清，空壳可能留存。
3. `load_config` 仍要求全部配置目录存在：输出模式不豁免 `paths_missing`（配置校验语义不变）。
4. 库名含 Windows 非法文件夹字符（如半角冒号）时按类别建目录会失败 → 该单元 aborted 可回滚；v1 不做库名消毒（改名库 + 重扫即可恢复）。
5. 输出目录选择不持久化（重启/重扫即清空）；不做“记住上次目录”。
6. 计划期冲突状态基于库路径判定；输出模式下这些单元仍不可执行（状态机不变）。
7. `on_conflict=rename` 的改名建议在计划期基于库路径计算；输出模式执行期不做 rename（与库模式现状一致：执行期同名即 aborted）。

---

## 6. 计划自查（五查结论）

1. **规格覆盖**：需求 1 → Task-06；需求 2 → Task-01/02/03/04/05/07（校验/决策/预检/执行/接线/UI 六层贯通，覆盖 coordinator 点名的 planner.py:70 与 jobs.py:156-171 组合规则的复用）；需求 3 → Task-02（默认值与语义）+ Task-07（开关 UI）。三条需求全部有对应任务与测试。
2. **步骤唯一性**：每个文件每处修改只归属一个任务（jobs.run_apply 仅 Task-04；plan_tab 仅 Task-07；config_tab 仅 Task-06；preflight 仅 Task-03；state 仅 Task-05），无重叠编辑区；顺序重排与新增块分别给出行号锚点与符号锚点。
3. **签名一致性**：见第 2 节总表——三个签名扩展全部默认参数，现有调用（tests/test_flow.py:55,90,142、state.py:135-139、jobs.py:101-114）零改动；`_add_library_row(values=None)` 显式冻结。
4. **边界输入**：第 4 节 13 条逐条有归属（代码点 + 测试名）。
5. **基线**：现有测试 0 删 0 改（仅新增），新增 31 个；Task-00/08 用收集数核对「只增不减」。

## 7. 验证命令汇总

```bash
# 基线
python -m pytest --collect-only -q
# 定向（每任务收尾）
python -m pytest tests/test_config.py -q
python -m pytest tests/test_viewmodel.py -q
python -m pytest tests/test_flow.py -q
python -m pytest tests/test_state.py -q
python -m pytest tests/test_config_tab.py -q
python -m pytest tests/test_plan_tab.py -q
# 全量（Task-08）
python -m pytest -q
# GUI 冒烟截图
python -m app.ui.main_window --demo --screenshot artifacts/2026-11-09-plan-tab.png --tab 0
```

## 8. 实施记录（执行者填写）

- 基线=165（2026-11-09，165 passed）
- 收尾=196（基线 165 + 新增 31，196 passed）

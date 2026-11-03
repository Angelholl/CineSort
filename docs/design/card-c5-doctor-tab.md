# C5 — 「④ 体检页」：系统体检报告 + 半成品残留清理 + 门禁白名单对齐

## 一、背景与根因

主窗第 ④ 页仍是占位。职责：随时手动体检（配置目录存在性 / Jellyfin 进程 / 磁盘空间 / staging 半成品残留 / 超长路径 / 兜底占比），发现 `staging_leftover` 时一键清理，并把计划页阻断对话框的「可勾越过」白名单与网页版对齐。语义真值源=旧网页版 `#tab-doctor`（btn-doctor → POST /api/preflight {} → renderDoctor：badge b-{level} + message + detail 折叠列表）与 `renderPreflight` 的清理按钮语义（`staging_leftover` 出现 →「清理半成品残留」→ POST /api/cleanup_staging → toast「已清理 N 处残留」→ 重新体检）。

**门禁白名单拍板（本卡语义变更）**：网页版可勾越过仅 `jellyfin_running`、`fallback_ratio`；`paths_missing`、`disk_space`、`staging_leftover` 为硬阻断。现状 `app/ui/plan_tab.py:525` 的 `BlockConfirmDialog.NON_ACKABLE = {"paths_missing"}` 过宽（staging_leftover/disk_space 会被落到可勾分支）。core 侧 `run_apply` 只看 `code not in acks`，故 UI 层收紧即生效。本卡将 `NON_ACKABLE` 改为 `frozenset({"paths_missing", "disk_space", "staging_leftover"})`，staging_leftover 的不可越过文案注明「请在 ④ 体检页清理残留」。

线程纪律（D-20261102-01）：体检经 `state.start_preflight(ids)` 走 JobManager 后台线程（`tasklist` 子进程最长 15s + 磁盘遍历，**严禁 UI 线程直调 `preflight_items`**）；DoctorTab 不自建线程/QTimer；快 tick 喂 `on_job_tick(snap)`（读内存快照收结果）；`cleanup_staging` 是 staging 目录内小遍历（仅 `.incomplete-*` 目录，量级小），允许 UI 线程同步调。

## 二、改动文件与改法（只允许动这些）

允许：**新建** `app/ui/doctor_tab.py`、`tests/test_doctor_tab.py`；**修改** `app/ui/main_window.py`（接线）、`app/ui/plan_tab.py`（仅 NON_ACKABLE 一处 + staging 文案）。其余不碰。

### 1. 新建 `app/ui/doctor_tab.py`

`class DoctorTab(QWidget): def __init__(self, state: AppState | None, toast=None, parent=None)`。

- **布局**（单 QFrame[card]）：
  - 操作行：QPushButton `btn_doctor`「运行系统体检」（role=primary）+ stretch + dim 说明「体检含进程探测（最长 15 秒），后台运行不卡界面」+ QPushButton `btn_cleanup`「清理半成品残留」（role=danger，默认隐藏）。
  - 结果区 QTreeWidget `result_tree`（两列 root：0 列放「level 徽章文案 + message」，1 列留空；detail 作为子节点逐条 dim）：列头 `["检查项", ""]`、`header().setStretchLastSection(True)`、`setAlternatingRowColors(False)`、根节点不可折叠展开由代码控制（有 detail 的默认展开）。level→颜色：block=theme.BAD、warn=theme.WARN、info=theme.OK（根节点 0 列文字染对应色，前缀【阻断】【提醒】【通过】）。
  - 空态：dim 居中提示「尚未体检。点击上方按钮开始」。
- **`_run_check()`**：`state is None` → toast「演示模式（假数据），不连接真实配置」；否则 `state.start_preflight(None)`（全量体检），`BusyError` → toast 原文；成功 → toast「体检已开始」+ busy 态（btn_doctor/btn_cleanup 禁用，空态文案改「体检运行中…」）。
- **`on_job_tick(snap)`**（快 tick 喂，复刻 exec_tab 的结束沿模式 `_job_seen_running`/`_last_job_id`）：
  - `snap["kind"] != "preflight"` 的快照**直接忽略**（本页只关心体检任务；running 判定须同时看 kind，避免把扫描/搬运任务误当体检忙态）。
  - 体检 running：busy 态。
  - 结束沿（kind=preflight 且 status 非 running）：busy 解除；`status=="done"` → `result["items"]` 渲染（item 字段 `{level, code, message, detail}`）：根节点=【级别】message，detail 逐条子节点；`items` 里存在 `code=="staging_leftover"`（不论 level）→ `btn_cleanup` 显示；无阻断项时顶部加一条汇总「✓ 未发现阻断项」用 theme.OK；`status=="failed"` → 汇总「体检任务失败：{error}」红染。
- **`_cleanup()`**：`state.cleanup_staging()` → int N → toast f"已清理 N 处残留" → 自动 `_run_check()` 重新体检（等价网页版 `S.preflight=null` 重检语义）；异常不吞（转 toast）。
- demo 降级：两按钮禁用 + tooltip「演示模式（假数据），不连接真实配置」+ 空态文案同。

### 2. 改 `app/ui/plan_tab.py`（仅两处）

- `NON_ACKABLE = frozenset({"paths_missing", "disk_space", "staging_leftover"})`。
- 不可越过项的文案前缀逻辑处：`code=="staging_leftover"` 的 detail/tooltip 追加「可在 ④ 体检页一键清理」。其余（勾选门禁 `_sync`、`acked_codes`）一字不动——收紧后 `jellyfin_running`/`fallback_ratio` 仍走原可勾分支。

### 3. 改 `app/ui/main_window.py`

- import DoctorTab；占位循环删除（`("④ 体检",)` 循环整段移除）；`self.doctor_tab = DoctorTab(self.state, toast=self.toast)`；`addTab(self.doctor_tab, "④ 体检")`（顺序 ①②③④ 不变）。
- `_fast_tick` 把 snap 喂给 `self.doctor_tab.on_job_tick(snap)`（快照本就取出，零新增磁盘读）。
- 慢 tick **不喂**本页（体检报告只在任务结束时更新，无需轮询磁盘）。

### 4. 新建 `tests/test_doctor_tab.py`（先红后绿；克隆 test_exec_tab.py 范式）

文件头 offscreen + qapp fixture。StubState（duck-typing）：

```python
class StubState:
    def __init__(self, items=()):
        self._items = list(items)
        self.started = 0
        self.cleaned = 0
    def start_preflight(self, ids):
        self.started += 1
        return {"ok": True}
    def cleanup_staging(self):
        self.cleaned += 1
        return 3
```

用例（≥9）：

1. `test_demo_mode_disables`：`DoctorTab(None)` → 两按钮禁用 + tooltip 含「演示模式」。
2. `test_idle_empty_state`：初始空态文案含「尚未体检」。
3. `test_run_check_starts_and_busy`：真 StubState 点 `_run_check`（直接调方法或 btn_doctor.click()）→ started==1、btn_doctor 禁用、提示含「体检运行中」。
4. `test_run_check_busy_error`：StubState.start_preflight 抛 `BusyError("已有任务在运行")` → 不崩、toast 含原文、不进 busy。
5. `test_tick_ignores_other_kinds`：喂 kind=apply running 快照 → 不进 busy（btn_doctor 仍可用）。
6. `test_preflight_done_renders_items`：喂 kind=preflight running → 再喂同 id done、`result={"items":[block(paths_missing, detail 2 条), warn(long_paths, detail 1 条), info(jellyfin_ok, detail [])]}` → 树 3 根、根 0 文本含级别前缀与 message、block 根有 2 子、info 根无子；btn_cleanup 隐藏；按钮恢复可用。
7. `test_staging_leftover_shows_cleanup`：done result 含 `staging_leftover` item → btn_cleanup 可见。
8. `test_cleanup_runs_and_reruns`：先完成一次含 staging 的体检 → `_cleanup()` → cleaned==1、toast 含「已清理 3 处」、started 增至 2（自动重检）。
9. `test_preflight_failed_shows_error`：kind=preflight status=failed error="超时" → 汇总含「体检任务失败」与「超时」。
10. `test_non_ackable_whitelist_static`：读 app/ui/plan_tab.py 源码断言 `NON_ACKABLE = frozenset({"paths_missing", "disk_space", "staging_leftover"})`（逐字）且 doctor_tab 已接线（`DoctorTab(`、`"④ 体检"`、`self.doctor_tab.on_job_tick`）。

**另**：`tests/test_plan_tab.py` 既有 `test_block_dialog_gate_semantics` 若断言了旧白名单（仅 paths_missing 不可勾）须同步更新断言到新白名单（用例数不减，断言强度不降：至少断言 disk_space 与 staging_leftover 的复选框 setEnabled(False) 及 jellyfin_running 可勾）。

## 三、验收命令（以下命令均在项目根目录执行；Python 用 `py -3.12`）

```bash
py -3.12 -m ruff check app/ui/doctor_tab.py app/ui/plan_tab.py app/ui/main_window.py tests/test_doctor_tab.py tests/test_plan_tab.py
py -3.12 -m pytest tests/test_doctor_tab.py tests/test_plan_tab.py -q   # 先红后绿
py -3.12 -m pytest tests -q                                             # ≥165 passed，零失败（基线 156 只增不减）
py -3.12 -m app.ui.main_window --demo --rows 200 --screenshot Temp/doctor-demo-100.png --width 1280 --height 800 --tab 3
py -3.12 -m app.ui.main_window --demo --rows 200 --screenshot Temp/doctor-demo-150.png --scale 1.5 --width 1280 --height 800 --tab 3
```

- ruff 改动文件 0 项；全量数字写进提交 verify:（156 → 实际数）。
- 截图落 Temp/（gitignore）：④ 页为当前 tab、空态/按钮可见、150% 无裁字重叠。

## 四、约束

- 只 commit 不 push；提交信息 Conventional 前缀 + 中文描述，正文 `verify:` 写 ruff 0 项 + pytest 全量数（156→N）+ 截图路径，注明「GUI 已验证：offscreen 截图 + 视图逻辑单测」；`Refs: D-20261102-01, D-20261102-02`。
- 显式 `git add app/ui/doctor_tab.py tests/test_doctor_tab.py app/ui/plan_tab.py app/ui/main_window.py docs/design/card-c5-doctor-tab.md`；永不 `git add -A`；永不 `--no-verify`。
- DoctorTab 内禁止线程/QTimer/HTTP import；`preflight_items`（同步版）**禁止**在 UI 任何地方调用；不吞异常。
- 卡外问题即停回报。执行中读取大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 pointerize/read_pointer/read_diff_only，禁止整读全文。

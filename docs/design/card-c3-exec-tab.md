# C3 — 「② 执行 / 回滚」页：进度条 / 日志 / 取消 / 会话清单 / 两击回滚确认

## 一、背景与根因

主窗壳（d4efd2f）已就位：快慢双 tick、关窗守卫、计划页接真实数据。但「② 执行 / 回滚」仍是占位 QWidget。计划页发起搬运后 toast 明说「进度见『② 执行 / 回滚』」，该页却不存在——执行反馈与回滚入口断链。工作树已备好本卡地基（**未提交**）：`app/state.py` 新增 `sessions()`（慢 tick 读 journals）、`app/ui/theme.py` 新增 QProgressBar 样式（tone=done/failed 属性变体）。本卡把该页补齐，语义复刻旧网页版 `app/static/index.html` 的执行视图（renderExec/renderSessions/previewUndo），实现后网页版删除卡才有前提。

线程纪律（D-20261102-01）：ExecTab **不建线程、不建 QTimer**——快 tick 由 MainWindow 喂 `on_job_tick(snap)`（只读内存快照），慢 tick 喂 `refresh_sessions()`（唯一允许调 `state.sessions()` 的地方）；`undo_preview` 单会话文件量级小，允许 UI 线程调用。GUI 验收协议按 D-20261102-02：视图逻辑单测（offscreen）+ UI 源码静态断言 + 截图存 Temp/。

## 二、改动文件与改法（只允许动这些）

允许：**新建** `app/ui/exec_tab.py`、`tests/test_exec_tab.py`；**修改** `app/ui/main_window.py`。
`app/state.py` 与 `app/ui/theme.py` 的既有未提交改动属本卡地基，**随本卡一并提交但禁止再改**（发现缺口即停报）。其余一律不碰（`app/core/**`、`app/server.py`、`app/static/**`、`tests/` 其他文件、`run.py`、`app/main_gui.py`、打包脚本）。

### 1. 新建 `app/ui/exec_tab.py`

```python
class ExecTab(QWidget):
    def __init__(self, state: AppState | None, toast=None, parent: QWidget | None = None):
```

`toast` 可调用注入（默认 no-op lambda），与 PlanTab 同款。`state=None` 即演示模式。内部结构：

**运行区**（QFrame[card]）：
- 状态行：QLabel `job_label`（空闲时「空闲」；running 时 f"{KIND_CN[kind]}：{label or ''}"，KIND_CN = `{"scan": "扫描中", "apply": "执行中", "undo": "回滚中"}`）+ stretch + QProgressBar `bar` + QLabel `pos_label`（f"{cur}/{total}"，total<=0 时显示「…」）+ QPushButton `btn_cancel`（text「取消任务」，`role="danger"` 属性）。
- 进度条语义：`bar.setRange(0, max(total, 1))`，running 时 `setValue(cur)`；结束时 apply/undo/scan 均 `setValue(maximum)`；tone 属性 running→移除 tone、done→`"done"`、failed→`"failed"`，每次改后 `style().unpolish(bar); style().polish(bar)`。total<=0（scan 无逐条进度）时 setValue(0)，靠文案表达进行中。
- `btn_cancel` 仅 running 时 enabled。点击：`cancelled = state.cancel_job()`；`toast("已请求取消，将在当前单元完成后停止" if cancelled else "当前没有正在运行的任务")`；BusyError 不可能（cancel 不 start），其他异常捕获后 toast 原文。

**日志区**：QPlainTextEdit `log_view`，objectName 不加但设属性 `log=True`（命中既有 QSS `QPlainTextEdit[log]`），`setReadOnly(True)`。快 tick 中若 `snap["log"]` 与上次渲染文本不同才 `setPlainText("\n".join(snap["log"]))`（防 300ms 重排闪烁），并保持滚动到底部（`verticalScrollBar().setValue(maximum())`，仅内容变化时）。

**结果区**：QLabel `result_label`（wordWrap=True）。任务结束沿（见 on_job_tick）填：
- kind=apply 且 status=done：`f"移动 {result.get('moved', 0)} 部，失败 {result.get('failed', 0)} 部"`；`result.get("failures")` 非空则逐条换行附 `✗ {str(x)}`（最多 10 条，超出附「…等共 N 条」）；末尾附 f"已写入回滚会话 {result.get('session')}，可在下方一键回滚"（session 缺省则不附）。
- kind=undo 且 status=done：`f"还原 {result.get('restored', 0)}，跳过 {result.get('skipped', 0)}，失败 {result.get('failed', 0)}"`。
- kind=scan 且 status=done：`f"扫描完成：就绪 {result.get('ready', '?')} 部"`（stats 键缺失即显示 ?，不得猜键）。
- status=failed：`f"任务失败：{snap.get('error')}"`。
- done/failed 的富文本着色：failed 用 `<span style="color:{theme.BAD}">`，成功数字不染色。样式常量从 `. import theme` 取（theme.BAD 等）。

**回滚区**：
- 标题行 QLabel「回滚会话」+ 右侧 dim 说明「按时间倒序，仅显示有已完成操作的会话」。
- QTableWidget `session_table`：列头 `["会话", "类型", "时间", "成功", "中止", "关联计划", ""]`；`setEditTriggers(QAbstractItemView.NoEditTriggers)`、`setSelectionBehavior(QAbstractItemView.SelectRows)`、`setSelectionMode(QAbstractItemView.SingleSelection)`、`verticalHeader().setVisible(False)`、`setWordWrap(False)`。
- `refresh_sessions(force: bool = False)`：state=None 直接显示空态文案「演示模式（假数据），不连接真实配置」（dim、居中，占满表格区域——可用单行 QLabel 覆盖或把表格设 0 行后 `setCornerWidget` 之外的方式，实现自定，语义即可）；真模式调 `state.sessions()`（**只准本方法调**），过滤 `s["done"] > 0`（对齐网页版），按返回序（已倒序）填充：会话=file、类型=kind（"apply"→"执行"、"undo"→"回滚"，其他原样）、时间=ts、成功=done、中止=aborted（>0 时红染色）、关联计划=plan_id or undoes or "-"；末列每行 `setCellWidget` 放 QPushButton「预览回滚」，clicked 经 lambda 捕获 file 调 `_open_undo_preview(file)`。空列表显示空态：表格 0 行 + 表格上方 dim QLabel「暂无可回滚会话」可见/隐藏切换。
- 行双击 `cellDoubleClicked` 同样触发 `_open_undo_preview`。

**`_open_undo_preview(fname)`**：`ValueError` → toast 原文并 return；否则弹 `UndoPreviewDialog(ops, fname, parent=self)`；`exec()` 返回 Accepted 后 `state.start_undo(fname)`，`BusyError` → toast 原文；成功 toast f"已开始回滚 {fname}，进度见上方"。demo 模式（state=None）按钮点击 → toast「演示模式（假数据），不连接真实配置」并 return。

**`UndoPreviewDialog(QDialog)`**（同文件）：
- 构造：`def __init__(self, ops: list[dict], file: str, parent=None)`；窗口标题 f"回滚预览：{file}"，最小宽 720。
- 顶部 QLabel 摘要 f"共 {len(ops)} 条操作，将按逆序还原"。
- QTableWidget 列头 `["影片", "从", "还原到", "状态"]`，行字段 unit_id / dst_dir / src_dir / state；state 映射 `CANON = {"ok": "将还原", "skip_target_missing": "目标不存在→跳过", "skip_src_exists": "源已存在→跳过"}`（缺键原样）；skip_* 行整行文字用 theme.DIM 色。
- 底部：QDialogButtonBox 或自排——QPushButton「取消」（reject）+ QPushButton `confirm_btn`「执行回滚」（`role="danger"`）。**两击防误触**（照抄网页语义）：第一次 click → `self._armed = True`、按钮文案改「⚠ 再点一次确认执行回滚」、不关窗；第二次 click → `self.accept()`。`_armed=False` 初始。

**`on_job_tick(snap: dict | None)`**（MainWindow 快 tick 每 300ms 调，签名与 PlanTab 同款）：
复刻 PlanTab 的结束沿模式（`_job_seen_running` / `_last_job_id` 两实例变量）：
- snap 存在且 status=="running"：置 `_job_seen_running=True`，更新 job_label / bar / pos_label / btn_cancel(True) / 日志；return。
- 否则 `_job_seen_running` 为 True 且 `snap.get("id") != self._last_job_id`：结束沿——记 `_last_job_id`、复位 `_job_seen_running`、填结果区、tone、btn_cancel(False)、日志最后刷一次、`refresh_sessions(force=True)`。
- 快照为 None（无任务）：仅在从未 running 过时保持初始空态，不得误清结果区（结束沿已消费快照后才允许清进度文案——实现上结束沿之后 snap 仍非 None（同一 job 对象），None 只出现在进程级无 job，此时保留上次结果区即可）。

**demo 模式其余降级**：btn_cancel disabled + setToolTip「演示模式（假数据），不连接真实配置」。

### 2. 改 `app/ui/main_window.py`

- import ExecTab；`_build` 中占位循环改为只剩 `("③ 配置", "④ 体检")`；`self.exec_tab = ExecTab(self.state, toast=self.toast)`，`tabs.addTab(self.exec_tab, "② 执行 / 回滚")`（顺序：①计划、②执行/回滚、③配置、④体检）。
- 快 tick `_fast_tick`：取 snap 后除喂 plan_tab 外加 `self.exec_tab.on_job_tick(snap)`。
- 慢 tick 定时器 lambda 改为：`self.plan_tab.refresh(); self.exec_tab.refresh_sessions()`。
- `main()` argparse 增加 `--tab`（type=int, default=0）；`--screenshot` 分支 shoot() 内 `app.processEvents()` 前 `if args.tab: win.tabs.setCurrentIndex(args.tab)`——为此需把 `_build` 里局部变量 `tabs` 提升为 `self.tabs`。
- 其余（关窗守卫、pill、demo 链路）一字不动。

### 3. 先红后绿

先写 `tests/test_exec_tab.py` 跑出红（ImportError 即红），再实现转绿。文件 docstring：`"""「② 执行 / 回滚」页视图逻辑单测（offscreen，零磁盘、零线程）：克隆 test_plan_tab.py 范式（D-20261102-02 协议第 1/2/4 条）。"""`

模式（照抄 tests/test_plan_tab.py）：`os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`、模块级/fixture `qapp`（QApplication.instance() or QApplication([])）。**不使用 pytest-qt，不 exec() 事件循环**；对话框用例直接 `.click()` 按钮并断言 isVisible()/result()。

用例（≥11，全须通过）：

1. `test_demo_mode_disables_controls`：`ExecTab(None)` → btn_cancel 不可用且 toolTip 含「演示模式」；会话区显示演示文案。
2. `test_idle_initial_state`：真模式（传入满足 duck-typing 的 StubState，见 9）初始未 tick → 进度条 value 0、结果区空、btn_cancel 禁用、job_label「空闲」。
3. `test_running_apply_updates_progress`：tick `{"id":"a1","kind":"apply","status":"running","total":5,"cur":2,"label":"Space War (2021)","log":["x"],"error":None,"result":{}}` → bar.value()==2、maximum()==5、pos_label 含 "2/5"、job_label 含 "执行中" 与 "Space War"、btn_cancel 可用。
4. `test_running_scan_zero_total`：kind=scan、total=0、cur=0 → 不崩、job_label 含「扫描中」、pos_label 为「…」或等价。
5. `test_finished_apply_shows_result`：先 tick 3 的 running 快照，再 tick 同 id、status=done、`result={"moved":3,"failed":1,"failures":["E1"],"session":"apply-x"}` → 结果区含「移动 3 部」「失败 1 部」「E1」「apply-x」、bar tone 属性=="done"、btn_cancel 禁用、job_label 含「空闲」。
6. `test_finished_undo_shows_result`：同构造，kind=undo、result={"restored":2,"skipped":1,"failed":0,"session":"u1"} → 结果区含「还原 2」「跳过 1」。
7. `test_failed_job_shows_error`：status=failed、error="源目录已漂移" → 结果区含该文本、tone 属性=="failed"。
8. `test_log_updates_only_on_change`：tick log=["a","b"] 两次 → log_view 文本=="a\nb"（第二次不闪烁即文本不变）；再 tick log=["a","b","c"] → 变 "a\nb\nc"。
9. `test_sessions_table_renders`：StubState `sessions()` 返回两条（apply done=3 aborted=0 plan_id="p1"；undo done=0）→ refresh_sessions() 后表格 1 行（done>0 过滤生效）、各列文本正确（类型列「执行」、关联计划 "p1"）、行内含「预览回滚」按钮；StubState 换 undo 行（kind=undo →「回滚」、aborted=2 红色语义即单元格文本 "2"）。
10. `test_undo_preview_dialog_two_click_arm`：`UndoPreviewDialog(ops=[{"unit_id":"U1","kind":"move","src_dir":"s","dst_dir":"d","state":"ok"},{"unit_id":"U2","kind":"move","src_dir":"s2","dst_dir":"d2","state":"skip_target_missing"}], file="apply-1.jsonl")`（不 exec）→ 表格 2 行、状态列含「将还原」与「目标不存在→跳过」；confirm_btn.click() 一次 → dialog.isVisible() 为 True 且按钮文案含「再点一次」；再 click() → result()==QDialog.Accepted。
11. `test_main_window_static_wiring`：读 `app/ui/main_window.py` 源码文本断言：`"② 执行 / 回滚"` 以 ExecTab 实例注册（`ExecTab(` 出现且 addTab 用 self.exec_tab）、`_fast_tick` 内含 `self.exec_tab.on_job_tick`、慢 tick 含 `self.exec_tab.refresh_sessions`、`--tab` 参数存在。本用例不做 Qt 断言（纯文本），放同文件末尾。

StubState 定义（duck-typing，勿 import AppState 以免碰盘）：

```python
class StubState:
    def __init__(self, sessions=()):
        self._sessions = list(sessions)
    def sessions(self):
        return list(self._sessions)
    def cancel_job(self):
        return False
```

## 三、验收命令（以下命令均在项目根目录执行；Python 用 `py -3.12`，勿用裸 `python`——PATH 可能指向无关解释器）

```bash
py -3.12 -m ruff check app/ui/exec_tab.py app/ui/main_window.py tests/test_exec_tab.py app/state.py app/ui/theme.py
py -3.12 -m pytest tests/test_exec_tab.py -q        # 定向：先红后绿
py -3.12 -m pytest tests/test_plan_tab.py tests/test_flow.py -q   # 相邻不回归
py -3.12 -m pytest tests -q                          # 全量 ≥142 passed，零失败（基线 131 只增不减）
py -3.12 -m app.ui.main_window --demo --rows 200 --screenshot Temp/exec-demo-100.png --width 1280 --height 800 --tab 1
py -3.12 -m app.ui.main_window --demo --rows 200 --screenshot Temp/exec-demo-150.png --scale 1.5 --width 1280 --height 800 --tab 1
```

- ruff：改动文件必须 0 项（全仓既有基线不追溯）。
- 全量用例数写进提交信息 verify:（131 → 实际数）。
- 两张截图必须成功落盘 Temp/（gitignore 内，不入库），执行记录写明路径；生成后目验截图：执行页为当前 tab、进度条/日志/回滚区可见、150% 无裁字重叠。

## 四、约束

- 只 commit 不 push；提交信息 Conventional 前缀 + 中文描述，正文 `verify:` 写 ruff 0 项 + pytest 全量数（131→N）+ 截图路径，并注明「GUI 已验证：offscreen 截图 + 视图逻辑单测」；`Refs: D-20261102-01, D-20261102-02`。
- 永不 `git add -A`：显式 `git add app/ui/exec_tab.py app/ui/main_window.py tests/test_exec_tab.py app/state.py app/ui/theme.py`。
- 永不 `--no-verify`。
- ExecTab 内禁止创建线程 / QTimer / 时间轮询；禁止 import HTTP 模块（app.server / requests 等）。
- 不吞异常：BusyError/ValueError 转 toast，其他异常不得裸 except Pass 隐藏。
- 不引入任何新依赖（PySide6 已有；QTest 可用但不强制）。
- 卡外问题即停回报，不得顺手修。
- 执行中读取大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 pointerize/read_pointer/read_diff_only，禁止整读文件全文。

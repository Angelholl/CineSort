# C4 — 「③ 配置页」：配置表单（校验保存）+ 自学习映射管理

## 一、背景与根因

主窗第 ③ 页仍是占位。职责（D-20261101-03 拍板）：查看/编辑配置并通过校验保存；自学习映射清单（题材/库/票数/人工次数/最近）与逐条「忘记」。语义真值源=旧网页版 `app/static/index.html` 的 `#tab-config` 视图（renderConfig/collectConfig/renderLearned），本卡复刻为 PySide6。数据源全部已在 `AppState`：`config_describe() -> (dict|None, str|None)`（配置非法时 raw_describe 兜底 + 错误文案）、`save_config(data) -> describe`（ConfigError 原样上抛，内部已 invalidate_plan）、`learned_forget(key, lib) -> items`。

describe() 返回字段全集（config.py:249-270）：`source_root, fallback_path, strategy(smart|priority|genre_only), on_conflict(skip|rename), staging_dir, warn_fallback_ratio, block_fallback_ratio, plot{enabled,min_score,normalize}, learning{enabled,min_votes}, genre_priority(list[str]), genre_aliases(dict 别名→标准库名), libraries(list[{name,path,keywords(list[str]),keywords_weighted}])`。

线程纪律（D-20261102-01）：ConfigTab 不建线程/QTimer；慢 tick 喂 `refresh()`（唯一调 `config_describe()`/`learned 读` 的地方）；保存走 `state.save_config`（同步写候选→校验→原子替换，本地小文件，UI 线程可接受——与网页版同步 fetch 等价）。快 tick 不喂本页（保存不进 JobManager）。

## 二、改动文件与改法（只允许动这些）

允许：**新建** `app/ui/config_viewmodel.py`（零 Qt 导入）、`app/ui/config_tab.py`、`tests/test_config_tab.py`；**修改** `app/ui/main_window.py`（接线）。其余不碰。

### 1. 新建 `app/ui/config_viewmodel.py`（零 Qt，逻辑层单测主体）

纯函数集（D-20261102-02 协议第 1 条）：

- `describe_to_form(desc: dict) -> dict`：拍平为表单初值 dict——`source_root/fallback_path/staging_dir`→str；`strategy/on_conflict`→str；`warn/block/plot_min_score`→float（None 安全取 0.0）；`plot_enabled/plot_normalize/learning_enabled`→bool；`learning_min_votes`→int（缺省 2）；`priority_text`→`"、".join(genre_priority)`；`alias_text`→每行 `别名=标准库名`（保序换行拼接）；`library_rows`→list[list[str]]（每行 name/path/keywords 逗号 join/keywords_weighted 按 `词=权重` 逗号 join，权重 `float` 去 trailing 0 格式化如 `1.5`/`2`）。
- `form_to_body(form: dict, library_rows: list[list[str]]) -> dict`：逆操作并做轻量归一——数值转 float/int（`plot.min_score` float、`learning.min_votes` int、`warn/block` float）；`genre_priority` 按 `[、,，]` 拆分去空白去空串；`genre_aliases` 逐行 split(`=`)（无 `=` 或空 key/value 的行跳过）；`libraries` 每行 `{name,path,keywords:[...],keywords_weighted:{词: float}}`（keywords 按 `[、,，]` 拆；weighted 按 `词=权重` 拆，权重 float()，解析失败的词条跳过）。**不做事务性校验**（枚举/路径存在性/嵌套等归 `save_config` 的 ConfigError），只保证形状正确。行级缺失 name 的库行跳过。
- `learned_rows(items: list[dict]) -> list[tuple]`：learned item 键 `{key, genre, lib, votes, manual, last}` → 行 `(genre, lib, votes, manual, last, key, lib)` 末两列供忘记按钮捕获。

### 2. 新建 `app/ui/config_tab.py`

`class ConfigTab(QWidget): def __init__(self, state: AppState | None, toast=None, parent=None)`。

- **布局**（上下两块 QFrame[card]）：
  - 表单卡：标题「基础配置」+ QGridLayout 两列。行：源目录 `f_source_root`（QLineEdit）、兜底库 `f_fallback_path`（QLineEdit）、暂存目录 `f_staging_dir`（QLineEdit）、策略 `f_strategy`（QComboBox smart/priority/genre_only）、冲突处理 `f_on_conflict`（QComboBox skip/rename）、兜底提醒阈值 `f_warn`（QDoubleSpinBox 0~1 step0.05 two decimals）、兜底阻断阈值 `f_block`（同上）、剧情简介 `f_plot_enabled`（QCheckBox 启用）+ `f_plot_min_score`（QDoubleSpinBox 0~1）+ `f_plot_normalize`（QCheckBox 清洗）、自学习 `f_learning_enabled`（QCheckBox）+ `f_learning_min_votes`（QSpinBox 1~99）、库优先级 `f_priority_text`（QLineEdit，顿号/逗号分隔，留空=无显式优先级）、别名表 `f_alias_text`（QPlainTextEdit，每行 `别名=标准库名`，限高 ~96px）。
  - 库表卡：标题「库」+ QTableWidget `lib_table` 4 列（库名/目录/关键词/加权词）`setEditTriggers(NoEditTriggers 之外须可编辑——用 DoubleClicked|EditKeyPressed)`、末行下 QPushButton「＋ 添加库」追加空行、「－ 删除选中库」删当前行（行号随 QTableWidget.selectionModel().currentRow()）。
  - 操作行：QPushButton「保存配置」（role=primary）+「重载」（恢复 describe 初值）+ QLabel `cfg_msg`（默认隐藏，校验失败时显示原文，红色染 `theme.BAD`）。
  - 自学习卡：标题「自学习映射（达阈值自动生效）」+ QTableWidget `learned_table` 6 列（题材/归入库/票数/其中人工/最近/""），行末 setCellWidget QPushButton「忘记」（role=danger）；空态 dim 文案「暂无自学习记录」。
- **`refresh(force: bool = False)`**（慢 tick 唯一入口）：`state is None` → 表单全禁用 + 自学习区显示「演示模式（假数据），不连接真实配置」+ 保存/重载禁用，return。真模式：`(desc, err) = state.config_describe()`；err 非 None → `cfg_msg` 显示 f"当前配置无效，展示的是兜底值，保存前请先修正：\n{err}"（不隐藏）；`describe_to_form` 填表（**仅在表单未处于"用户已编辑且未保存"状态时覆盖**——实现取巧：仅在 `force=True` 或「上次渲染以来无任何输入修改」时覆盖；用一个 dirty 标记在所有控件 `textChanged/valueChanged/changed` 时置位、保存或重载成功后清位，避免慢 tick 打字被刷掉）；learned 区 `learned_rows(state 端 learned)`——从 `state` 读：用 `state_snapshot()` 太重，直接调 `learned_store.items(learned_store.load(state.runtime_dir()))`？**不允许**（UI 不得 import core 写盘层）——改为 `AppState` 现成面：`state.learned_forget(key, lib)` 只能删不能读。故卡面定：**允许 ConfigTab 调 `state.state_snapshot()["learned"]`**（慢 tick 内、快照含该键，无新 State 方法；2s 一次的 learned.json 读取量级小）。
- **保存**：`form_to_body(...)` → `state.save_config(body)`；`ConfigError` → `cfg_msg` 显示 f"校验失败：\n{exc}"；成功 → 清 dirty、`cfg_msg` 隐藏、`toast("配置已保存并通过校验，请重新扫描生成新计划")`、`refresh(force=True)` 回填 describe。其他异常不吞。
- **忘记**：按钮 lambda 捕获 `(key, lib)` → `state.learned_forget(key, lib)` → toast「已忘记该映射」→ 刷新 learned 区（直接用返回的 items 重渲，不等慢 tick）。
- **demo 降级**：如上。

### 3. 改 `app/ui/main_window.py`

- import ConfigTab；占位循环改 `for name in ("④ 体检",)`；`self.config_tab = ConfigTab(self.state, toast=self.toast)`，`addTab(self.config_tab, "③ 配置")`（顺序 ①②③④ 不变，`--tab 2` 即本页）。
- `_slow_tick` 增加 `self.config_tab.refresh()`。
- 快 tick 不喂本页。

### 4. 新建 `tests/test_config_tab.py`（先红后绿）

文件头 `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`；qapp fixture 克隆 test_exec_tab.py。分两段：

**纯逻辑段（零 Qt 实例化，直接调 config_viewmodel 函数，≥6 例）**：
1. `test_describe_to_form_roundtrip`：构造完整 describe → describe_to_form → form_to_body → 断言与原 describe 逐键等值（libraries 的 keywords_weighted 数值等值、genre_aliases 顺序无关、genre_priority 保序）。
2. `test_alias_parse_skips_bad_lines`：alias_text 含 `A=B`、空行、`无等号`、`=X`、`Y=` → 只收 `{"A": "B"}`。
3. `test_weighted_parse`：`"太空=2, 机甲=1.5, 坏行"` → `{"太空": 2.0, "机甲": 1.5}`。
4. `test_priority_split`：`"科幻、动作，奇幻"` → `["科幻","动作","奇幻"]`；空串 → `[]`。
5. `test_numeric_normalization`：min_score "0.75"→0.75、min_votes "3"→3（int）、warn/block float。
6. `test_library_rows_skip_nameless`：name 空白行被跳过。

**widget 段（offscreen，≥6 例）**：
7. `test_demo_mode_disables_all`：`ConfigTab(None)` → 保存/重载禁用、表单控件禁用、自学习区含「演示模式」。
8. `test_form_filled_from_describe`：StubState 返回固定 describe → refresh() → 各控件值匹配（source_root 文本、strategy 当前项、warn 数值）。
9. `test_config_error_banner`：StubState `config_describe()` 返回 `(desc, "第 3 行：库目录不存在")` → cfg_msg 可见且含该文案。
10. `test_save_success_and_failure`：StubState.save_config 正常 → toast 含「重新扫描」且 cfg_msg 隐藏；StubState.save_config 抛 `ConfigError("源目录不存在")` → cfg_msg 含「校验失败」与原文（StubState 从 app.core.config import ConfigError 抛）。
11. `test_learned_table_and_forget`：StubState `state_snapshot()` 返回 `{"learned": [item dict]}` → 表 1 行、「忘记」点击 → StubState 记录到 forget 调用参数为 (key, lib) 且 toast「已忘记」。
12. `test_dirty_form_not_clobbered_by_refresh`：refresh 后改 `f_source_root` 文本 → 再 refresh()（force=False）→ 编辑值保留；refresh(force=True) → 覆盖回 describe 值。
13. `test_main_window_static_wiring`：读 app/ui/main_window.py 源码断言 `ConfigTab(`、`"③ 配置"`、`self.config_tab.refresh`、`("④ 体检",)` 占位。

StubState（duck-typing，勿 import AppState）：

```python
class StubState:
    def __init__(self, desc=None, err=None, learned=None):
        self.desc, self.err, self._learned = desc, err, list(learned or [])
        self.saved, self.forgotten = [], []
    def config_describe(self):
        return self.desc, self.err
    def save_config(self, data):
        self.saved.append(data)
        return self.desc
    def state_snapshot(self):
        return {"learned": list(self._learned)}
    def learned_forget(self, key, lib):
        self.forgotten.append((key, lib))
        return []
```

## 三、验收命令（以下命令均在项目根目录执行；Python 用 `py -3.12`，勿用裸 `python`）

```bash
py -3.12 -m ruff check app/ui/config_viewmodel.py app/ui/config_tab.py app/ui/main_window.py tests/test_config_tab.py
py -3.12 -m pytest tests/test_config_tab.py -q        # 先红后绿
py -3.12 -m pytest tests -q                           # ≥155 passed，零失败（基线 142 只增不减）
py -3.12 -m app.ui.main_window --demo --rows 200 --screenshot Temp/config-demo-100.png --width 1280 --height 800 --tab 2
py -3.12 -m app.ui.main_window --demo --rows 200 --screenshot Temp/config-demo-150.png --scale 1.5 --width 1280 --height 800 --tab 2
```

- ruff 改动文件 0 项；全量数字写进提交 verify:（142 → 实际数）。
- 两张截图落 Temp/（gitignore，不入库）：③ 页为当前 tab、表单/库表/自学习区可见、150% 无裁字重叠。

## 四、约束

- 只 commit 不 push；提交信息 Conventional 前缀 + 中文描述，正文 `verify:` 写 ruff 0 项 + pytest 全量数（142→N）+ 截图路径，注明「GUI 已验证：offscreen 截图 + 视图逻辑单测」；`Refs: D-20261102-01, D-20261102-02`。
- 显式 `git add app/ui/config_viewmodel.py app/ui/config_tab.py tests/test_config_tab.py app/ui/main_window.py docs/design/card-c4-config-tab.md`；永不 `git add -A`；永不 `--no-verify`。
- ConfigTab 内禁止线程/QTimer/HTTP import；不吞异常（ConfigError 须转展示，其他不得裸 except 静默）；不新增第三方依赖。
- 表单数值控件用 QDoubleSpinBox/QSpinBox（theme 已有 QAbstractSpinBox 样式）；QCheckBox 无专门 QSS 属预期（palette 兜底）。
- 卡外问题即停回报。执行中读取大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 pointerize/read_pointer/read_diff_only，禁止整读全文。

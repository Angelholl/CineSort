# 卡 C5：配置页「弱别名表」编辑框（计划 Task-06）

规格：`docs/design/2026-11-09-classification-quality.md` §3.1　计划：`docs/plans/2026-11-09-classification-quality.md` Task-06
决策依据：`docs/decision-log.md` D-20261109-01　前置：Task-04（`dfddf1a`）、Task-05（`5e95334`）已合入
测试基线：**226 passed**（本卡净增 4，收口应 230）；全仓 ruff 基线 **10 项**（只降不增）

## 一、本卡要解决的问题

`[weak_genre_aliases]` 目前只能手改 TOML，配置页没有编辑入口——owner 要在实跑一轮后按需扩缩弱标记集（`人妻` 族、职业族是否加入），**必须能在 GUI 里直接改这张表**，否则护栏不可运营。本卡把弱别名表接进配置页的表单往返链：`describe_to_form` → `QPlainTextEdit` → `_collect_form` → `form_to_body` → `dump_config_text`。

现有强别名表就是这个形状（`config_viewmodel.py` 的 `describe_to_form`/`form_to_body` + `config_tab.py` 的 `f_alias_text`），弱表**镜像照做**，不引入新交互范式。

## 二、改动文件（只许改这三个）

| 文件 | 动作 | 落点 |
|---|---|---|
| `app/ui/config_viewmodel.py` | Modify | `describe_to_form`（:52-53 之后）、`form_to_body`（:60-67 解析循环复用、:110 旁写入 body） |
| `app/ui/config_tab.py` | Modify | 控件创建（:94-96 旁）、`rows` 布局（:116）、控件枚举/禁用清单（:196 区域）、演示禁用清单（:258-262）、表单回填（:301 旁）、聚合出口（:352 旁） |
| `tests/test_config_tab.py` | Test | 末尾追加 4 个测试 |

不动 `classifier.py`、`planner.py`、`config.py`、`plan_tab.py`、`main_window.py`。

## 三、改法（照抄执行）

1. `describe_to_form` 在别名表那行之后加：

```python
        "weak_alias_text": "\n".join(
            f"{k}={v}" for k, v in (desc.get("weak_genre_aliases") or {}).items()),
```

2. `form_to_body`：复用现有"每行 `k=v`"解析循环（不要另写一套解析），解析 `weak_alias_text` → 在 body 里 `genre_aliases` 写入处旁边加 `"weak_genre_aliases": weak_aliases`。空行与无 `=` 的行按现有强表的同一规则忽略。
3. `config_tab.py`：
   - 控件创建处新增 `self.f_weak_alias_text = QPlainTextEdit()`，`setFixedHeight(72)`，placeholder 逐字用：`每行：别名=标准库名（弱信号：唯一命中时低置信、默认不勾选）`
   - `rows` 列表在 `("别名表", self.f_alias_text)` 之后插入 `("弱别名表", self.f_weak_alias_text)`
   - 该文件所有"表单控件枚举"清单逐一接线（:196 区域的禁用/只读清单、:258-262 演示模式禁用清单、:301 旁回填 `setPlainText(form["weak_alias_text"])`、:352 旁聚合 `"weak_alias_text": self.f_weak_alias_text.toPlainText()`）——**先 grep 出全部枚举点再改，漏一处即为缺陷**
4. 旧配置（无 weak 节）在 GUI 里必须显示为空文本框、保存后仍为空表，不得报错。

## 四、先红后绿的回归测试（4 个）

| 测试名 | 构造 | 断言 |
|---|---|---|
| `test_weak_alias_form_round_trip` | `describe_to_form(desc)`（desc 的 weak 表含两对）→ `form_to_body(form, ...)` | `form["weak_alias_text"]` 含两行 `k=v`；body `["weak_genre_aliases"]` 与原 dict 逐键相等；空行与无 `=` 行被忽略且不抛异常 |
| `test_weak_alias_textarea_populated` | 用 `build_env` 造一份 weak 含 `护士=动作` 的真实配置驱动 ConfigTab | `tab.f_weak_alias_text.toPlainText()` 含 `"护士=动作"` |
| `test_weak_alias_edit_flows_to_body` | `tab.f_weak_alias_text.setPlainText("护士=动作\n\n坏行")` → 走该页现行聚合入口 | 聚合结果里 weak 表 `== {"护士": "动作"}` |
| `test_demo_mode_disables_weak_alias_box` | 演示模式构造 ConfigTab（沿用该文件现有的 demo 构造方式） | `tab.f_weak_alias_text.isEnabled() is False` |

现有 20 个测试 0 删 0 改。

## 五、验收命令（以下命令均在项目根目录执行，cwd 即仓库根）

1. 红：`python -m pytest tests/test_config_tab.py -q`（4 个新测试先失败）
2. 绿：`python -m ruff check app/ui/config_viewmodel.py app/ui/config_tab.py tests/test_config_tab.py` 必须 **0 项**（三个文件全列）；`python -m pytest tests/test_config_tab.py -q` 全绿（20 现有 + 4 新 = 24）
3. 全量不回归：`python -m pytest tests -q` → **0 failed，用例总数 = 230**（226 + 4）
4. 全仓 lint 不增：`python -m ruff check . 2>&1 | grep "^Found"` → 必须 **≤ 10 errors**
5. GUI 目验（本卡是 GUI 改动，必须交截图）：`QT_QPA_PLATFORM=offscreen py -3.12 -m app.ui.main_window --demo --screenshot artifacts/2026-11-09-c5-config-tab.png --tab 2`（此命令主审已实测可跑通）→ 产出文件存在且非空；提交正文里写明 `GUI 已验证`，并把这张截图留在 `artifacts/`（主审会目验"弱别名表"行与 placeholder 文案是否出现在别名表之后）

## 六、约束

- 只改卡面三个文件；现有测试 0 删 0 改；不得为变绿放宽断言。
- 不得改强别名表（`genre_aliases`）的任何既有解析/往返行为；弱表复用同一解析函数，不得复制粘贴出第二套解析逻辑。
- 不得写 `D:\CineSort\config.toml`、`D:\CineSort-beta\CineSort\config.toml`、`config.example.toml`（已知坏文件）或 `E:\已刮削` 下任何文件。
- 不得联网；不得改 `main_window.py` 的启动链或 `--screenshot/--tab` 参数语义。
- 不得 `git add` 截图以外的新产物到 `artifacts/`（该目录既有内容不动）。
- 卡外问题即停，在回报里单列，不得顺手改。
- 读大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 `pointerize` / `read_pointer` / `read_diff_only`，禁止整读文件全文。
- 完成后 `git commit`（Conventional 前缀 + 中文描述，正文 `verify:` 写实测结果、`GUI 已验证/未验证`、`Refs: D-20261109-01`），**不得 push**，不得 `git add -A`、不得 `--no-verify`。

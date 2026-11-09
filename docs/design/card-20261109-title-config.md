# 卡 C6：`[title]` 配置节 + 配置页镜像组（计划 Task-07）

规格：`docs/design/2026-11-09-classification-quality.md` §5.2　计划：`docs/plans/2026-11-09-classification-quality.md` Task-07
决策依据：`docs/decision-log.md` D-20261109-01　前置：Task-04（`dfddf1a`）、Task-05（`5e95334`）、Task-06（`c55bb57`）已合入
测试基线：**231 passed**（本卡净增 7，收口应 238）；全仓 ruff 基线 **10 项**（只降不增）

## 一、本卡要解决的问题

特性 D（标题文本弱评分）需要一张独立的阈值配置：标题文本短、`score_plot` 的 `normalize` 用 `len**0.5` 会把短文本分数放大，所以**不能复用 `[plot].min_score`**，必须有自己的 `[title] enabled / min_score`。本卡只做配置层与配置页承载，**不做评分逻辑（下一卡 Task-08）**，也不改任何人的实机 config.toml。

`[plot]` 已经是这条链的现成范式（`PlotOptions` → `load_config` → `config_hash` → `describe`/`raw_describe` → `dump_config_text` → `config_viewmodel` 表单 → `config_tab` 控件）。title 全部照 plot 镜像，不发明新形状。

## 二、改动文件（只许改这五个）

| 文件 | 动作 | 落点 |
|---|---|---|
| `app/core/config.py` | Modify | `PlotOptions`（:56-60）旁新增 `TitleOptions`；`Config`（:70-84）加字段；`config_hash`（:93-103）；`load_config` 解析（:202-209 之后）与返回构造（:251-265）；`describe`（:270-291）；`raw_describe`（:294-326）；`dump_config_text`（:346-350 之后） |
| `app/ui/config_viewmodel.py` | Modify | `describe_to_form`（:23-55 区）、`form_to_body`（:92-112 区） |
| `app/ui/config_tab.py` | Modify | plot 三控件行区旁镜像 title 控件；回填 / 聚合 / `_set_form_enabled` / 演示禁用清单逐处接线 |
| `tests/test_config.py` | Test | 末尾追加 5 个 |
| `tests/test_config_tab.py` | Test | 末尾追加 2 个 |

不动 `classifier.py`、`planner.py`、`scanner.py`、`plan_tab.py`、`main_window.py`。现有测试 0 删 0 改。

## 三、改法（照抄执行）

1. `PlotOptions` 之后新增：

```python
@dataclass
class TitleOptions:
    """标题文本弱评分（特性 D）：独立阈值，不复用 plot.min_score。"""
    enabled: bool = True
    min_score: float = 1.0
```

`Config` 在 `plot` 字段旁加 `title: TitleOptions = field(default_factory=TitleOptions)`。
2. `load_config`：plot 解析块之后镜像——`title_data = data.get("title") or {}`；`enabled=bool(title_data.get("enabled", True))`、`min_score=float(title_data.get("min_score", 1.0))`；`min_score < 0` → `raise ConfigError("title.min_score 不能为负数")`；返回构造里传入 `title=TitleOptions(...)`。
3. `config_hash` payload 加 `"title": {"enabled": self.title.enabled, "min_score": self.title.min_score}`。
4. `describe` / `raw_describe` 各加 `"title": {"enabled": …, "min_score": …}`（缺节时默认 True / 1.0）。
5. `dump_config_text` 在 `[plot]` 块之后加 `[title]` 节两行，格式与 plot 完全一致。
6. `config_viewmodel`：`describe_to_form` 加 `title_enabled` / `title_min_score`；`form_to_body` 加 `"title": {"enabled": bool(...), "min_score": float(...)}`（数值归一复用该文件现有的数值解析助手，不要新写一套）。
7. `config_tab`：照 plot 三件的现成接线逐处镜像，控件属性名 `f_title_enabled` / `f_title_min_score`。**先 grep 出 plot 控件出现的全部位置再逐处镜像，漏一处即为缺陷。**
8. 旧配置（无 `[title]` 节）必须零迁移：加载默认 True/1.0，GUI 显示默认值，保存后写出 `[title]` 节且不报错。

## 四、先红后绿的回归测试（7 个）

`tests/test_config.py` 末尾 5 个：

| 测试名 | 构造 | 断言 |
|---|---|---|
| `test_title_options_loaded_defaults` | `build_env()`（无 title 节） | `cfg.title.enabled is True` 且 `cfg.title.min_score == 1.0` |
| `test_title_min_score_negative_rejected` | overrides 写 `title.min_score = -0.5` | 抛 `ConfigError` 且文案含 `"title.min_score"` |
| `test_dump_round_trips_title` | `describe` → `dump_config_text` → 写临时 toml → `load_config` | `enabled`/`min_score` 两字段逐一相等（GUI 保存不丢） |
| `test_describe_raw_describe_title` | 两函数输出 | 都存在 `title` 键且为含 `enabled`/`min_score` 的 dict |
| `test_config_hash_changes_with_title` | 两份配置仅 title 不同 | `config_hash()` 不相等 |

`tests/test_config_tab.py` 末尾 2 个：

| 测试名 | 构造 | 断言 |
|---|---|---|
| `test_title_form_round_trip` | `describe_to_form` → 控件回填 → `_collect_form` → `form_to_body` | `body["title"] == {"enabled": <改后的值>, "min_score": <改后的值>}`；且必须**真的改动过**控件（不许原样往返糊过去） |
| `test_title_controls_rendered_next_to_plot_group` | 复用本文件已有的 `_label_row(tab, 文本)` 辅助 | title 两个控件所在行与 plot 组同栅格、且紧邻其后；`itemAtPosition(row, 1).widget()` 分别 `is tab.f_title_enabled` / `is tab.f_title_min_score` |

（第二条是主审要求的**视觉断言程序化**：本会话主审模型无图像输入，视觉顺序必须由布局断言钉，不能只写在提交措辞里。）

## 五、验收命令（以下命令均在项目根目录执行，cwd 即仓库根）

1. 红：`python -m pytest tests/test_config.py tests/test_config_tab.py -q`（7 个新测试先失败）
2. 绿：`python -m ruff check app/core/config.py app/ui/config_viewmodel.py app/ui/config_tab.py tests/test_config.py tests/test_config_tab.py` 必须 **0 项**（五个文件全列）；`python -m pytest tests/test_config.py tests/test_config_tab.py -q` 全绿（**实测现有 23 + 25 = 48**，加 7 新 = **55**）
3. 全量不回归：`python -m pytest tests -q` → **0 failed，用例总数 = 238**（231 + 7）
4. 全仓 lint 不增：`python -m ruff check . 2>&1 | grep "^Found"` → 必须 **≤ 10 errors**
5. GUI 目验（本卡改配置页，必须交截图）：`QT_QPA_PLATFORM=offscreen py -3.12 -m app.ui.main_window --demo --screenshot artifacts/2026-11-09-c6-config-tab.png --tab 2` → 文件存在且非空；提交正文写 `GUI 已验证` 并注明截图路径

## 六、约束

- 只改卡面五个文件；现有测试 0 删 0 改；不得为变绿放宽断言。
- 不得改 `[plot]` 的任何既有解析、默认值、校验文案或 GUI 接线行为（title 只做镜像）。
- 不得改 `score_plot`、`classifier.py` 任何判定逻辑——本卡不接入标题评分。
- 不得写 `D:\CineSort\config.toml`、`D:\CineSort-beta\CineSort\config.toml`、`config.example.toml`（已知坏文件）或 `E:\已刮削` 下任何文件。
- 不得联网；不得改 `main_window.py` 启动链或 `--screenshot/--tab` 参数语义。
- 卡外问题即停，在回报里单列，不得顺手改。
- 读大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 `pointerize` / `read_pointer` / `read_diff_only`，禁止整读文件全文。
- 完成后 `git commit`（Conventional 前缀 + 中文描述，正文 `verify:` 写实测结果、`GUI 已验证/未验证`、`Refs: D-20261109-01`），**不得 push**，不得 `git add -A`、不得 `--no-verify`。

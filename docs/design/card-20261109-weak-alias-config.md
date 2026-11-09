# 卡 C3：`[weak_genre_aliases]` 配置层全链（计划 Task-04）

规格：`docs/design/2026-11-09-classification-quality.md` §3.1　计划：`docs/plans/2026-11-09-classification-quality.md` Task-04
决策依据：`docs/decision-log.md` D-20261109-01　测试基线：**213 passed**（本卡净增 6，收口应 219）

## 一、根因与本卡定位（不得重新调查、不得扩大范围）

弱标签护栏（特性 B）需要一张与 `genre_aliases` 同形状的独立表：`[weak_genre_aliases]`（片源 NFO 标签词 → 库名，但命中只作低置信、默认不勾选）。owner 已定初始集 6 条（`护士`、`看护妇・ナース`→医护；`女同性戀`、`女同性恋`、`女同接吻`、`レズキス`→百合），**但本卡只做配置层承载与往返，不做判定语义（下一卡 Task-05），也不改任何人的实机 config.toml**。

现状 `app/core/config.py` 里 `genre_aliases` 有六处触点：字段声明、`load_config` 校验（值必须指向已定义库）、`config_hash` payload、`describe`、`raw_describe`、`dump_config_text`。weak 表必须六处全部镜像，否则 GUI 保存会静默丢掉这张表（`dump_config_text` 现写法是单行 inline table，weak 照同一写法即可，tomllib 可往返解析）。

## 二、改动文件（只许改这两个）

| 文件 | 动作 | 落点 |
|---|---|---|
| `app/core/config.py` | Modify | `Config` 字段（:76 之后）、`config_hash`（:94-101）、`load_config` 校验（:195-200 之后）、返回构造（:251-265）、`describe`（:289 后）、`raw_describe`（:324 后）、`dump_config_text`（:343-344 之后） |
| `tests/test_config.py` | Test | 末尾追加 6 个测试 |

不动 `classifier.py`、`planner.py`、`scanner.py`、UI（`config_tab.py` 是 Task-06）。

## 三、改法（照抄执行）

1. `Config` 在 `genre_aliases` 字段之后加：`weak_genre_aliases: dict[str, str] = field(default_factory=dict)`。
2. `load_config`：紧接 genre_aliases 校验块之后镜像一段——读 `data.get("weak_genre_aliases") or {}`，每个值必须是已定义库名，否则 `raise ConfigError(f"weak_genre_aliases[{k!r}] 指向未定义的库：{v}")`；并在返回的 `Config(...)` 构造里传入。
3. `config_hash` payload 加 `"weak_genre_aliases": dict(sorted(self.weak_genre_aliases.items()))`。
4. `describe` 加 `"weak_genre_aliases": dict(cfg.weak_genre_aliases)`；`raw_describe` 加 `{str(k): str(v) for k, v in (data.get("weak_genre_aliases") or {}).items()}`。
5. `dump_config_text` 在 genre_aliases 那行之后加：

```python
    weak_items = [f"{js(k)} = {js(v)}" for k, v in (d.get("weak_genre_aliases") or {}).items()]
    lines.append("weak_genre_aliases = { " + ", ".join(weak_items) + " }")
```

6. 旧配置（无该节）必须零迁移可用：默认空 dict，`load_config` 不报错。

## 四、先红后绿的回归测试（6 个；沿用既有 `build_env` 夹具，overrides 传 `"weak_genre_aliases": {...}` 形状）

| 测试名 | 构造 | 断言 |
|---|---|---|
| `test_weak_genre_aliases_loaded` | `build_env(overrides={"weak_genre_aliases": {"护士": "动作"}})` → `load_config` | `cfg.weak_genre_aliases == {"护士": "动作"}` |
| `test_weak_alias_unknown_lib_rejected` | weak 值指向未定义库 `{"护士": "不存在"}` 写进 toml 后 `load_config` | 抛 `ConfigError` 且文案含 `"weak_genre_aliases"` |
| `test_weak_alias_defaults_empty` | `build_env()`（无 weak 节） | `cfg.weak_genre_aliases == {}`（旧配置零迁移） |
| `test_dump_round_trips_weak_aliases` | `describe(cfg)` → `dump_config_text` → 写临时 toml → `load_config` | weak 表逐键相等（GUI 保存不丢这张表） |
| `test_describe_and_raw_describe_include_weak` | 两函数输出 | 键 `weak_genre_aliases` 存在且值为 dict |
| `test_config_hash_changes_with_weak` | 两份配置仅 weak 表不同 | 两个 `config_hash()` 不相等 |

## 五、验收命令（以下命令均在项目根目录执行，cwd 即仓库根）

1. 红：`python -m pytest tests/test_config.py -q`（新测试先失败）
2. 绿：`python -m ruff check app/core/config.py tests/test_config.py` 必须 **0 项**（**两个文件都要 0 项**，含本卡改到的测试文件）；`python -m pytest tests/test_config.py -q` 全绿（17 现有 + 6 新 = 23）
3. 全量不回归：`python -m pytest tests -q` → **0 failed，用例总数 = 219**（213 + 6）
4. 往返自检（只在系统临时目录写，不落任何真实配置；此命令的形状主审已实测可用）：

```bash
py -3.12 - <<'EOF'
import sys, tempfile, pathlib
sys.path.insert(0, '.')
from app.core.config import load_config, describe, dump_config_text
base = pathlib.Path(tempfile.mkdtemp())
for n in ("src", "fb", "lib1"):
    base.joinpath(n).mkdir()
(base / "c3.toml").write_text(
    f"source_root = '{base}/src'\nfallback_path = '{base}/fb'\n\n"
    f"[[library]]\nname = '动作'\npath = '{base}/lib1'\n", encoding="utf-8")
c = load_config(base / "c3.toml")
d = describe(c)
d["weak_genre_aliases"] = {"护士": "动作"}
(base / "c3b.toml").write_text(dump_config_text(d), encoding="utf-8")
print(load_config(base / "c3b.toml").weak_genre_aliases)
EOF
```

期望输出 `{'护士': '动作'}`。

**已知陷阱（主审已实证，不得自行绕道或顺手修）**：仓库根的 `config.example.toml` **本身就通不过项目校验**（`ConfigError: genre_aliases['thriller'] 指向未定义的库：惊悚`），因此本卡任何命令都不许拿它当输入；这是卡外既有缺陷，只在回报里单列，不得改动该文件。

## 六、约束

- 只改卡面两个文件；现有测试 0 删 0 改；不得为变绿放宽断言。
- 不得改 `genre_aliases`（强表）的任何既有行为、校验文案或顺序。
- 不得写 `D:\CineSort\config.toml`、`D:\CineSort-beta\CineSort\config.toml` 或 `E:\已刮削` 下任何文件（第 5 节自检只在系统临时目录里写、且用完即删）。
- 不得联网。卡外问题即停，在回报里单列，不得顺手改。
- 读大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 `pointerize` / `read_pointer` / `read_diff_only`，禁止整读文件全文。
- 完成后 `git commit`（Conventional 前缀 + 中文描述，正文 `verify:` 写实测结果与 `Refs: D-20261109-01`），**不得 push**，不得 `git add -A`、不得 `--no-verify`。

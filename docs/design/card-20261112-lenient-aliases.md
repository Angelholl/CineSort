# 卡：悬空库引用宽容降级（2026-11-12 beta 热修复 1/2）

## ① 任务与范围（根因）

`app/core/config.py` 把 genre_priority / genre_aliases / weak_genre_aliases 中「指向未定义库」的条目当硬错误（config.py:209、:218、:225 `raise ConfigError`）。而 `config.example.toml:37` 自带 `'thriller' = '惊悚'`、`'musical' = '音乐'` 两对悬空别名（13 个 [[library]] :48-124 无此二库），首跑 `app/ui/main_window.py:215-221` 把 example 原样拷成 config.toml → `load_config` 必炸；GUI 兜底（app/state.py:57-71 raw_describe 回填）把非法别名原样填回表单，用户不改别名框（app/ui/config_tab.py:96-98）就永远保存失败（保存链唯一卡点 = config.py:428 `save_config_dict` → `load_config(candidate)`），且红横幅（config_tab.py:308-311）不指明问题在别名框。

**owner 拍板方案**：悬空引用宽容降级——不再报错，丢弃并收集警告（Config 携带 warnings 列表）；GUI 加载后橙色横幅列出被忽略条目；保存含悬空条目的表单必须成功（写盘透明，下次加载再警告）；example 两对悬空别名删除。

范围 = 下列 5 个文件，其余一律不动。已知消费方（只需兼容、不需改动）：`load_config` 调用点 app/core/jobs.py:108,121,141,275、app/state.py:53,59,148,153、app/ui/plan_tab.py:654；`Config` 关键字构造点 tests/test_classifier.py:20、tests/test_learned.py:18、tests/test_scanner.py:11——Config 尾部追加带默认值字段对它们零影响（已核实）。classifier 只读 `cfg.genre_aliases`（app/core/classifier.py:42）、`cfg.weak_genre_aliases`（:50）、`cfg.genre_priority`（:152-153），被丢弃条目自然不参与映射。

## ② 改动文件与改法（签名级）

### 2.1 app/core/config.py

1. 模块 docstring（:8）规则行 `- genre_priority / genre_aliases 引用的库名必须存在。` 改为：
   `- genre_priority / genre_aliases / weak_genre_aliases 指向未定义库的条目一律降级为 warnings（宽容降级），不再抛错；重复库名仍报错。`
2. `Config` dataclass 末尾（:94 `weak_genre_aliases` 之后）追加字段：
   ```python
   warnings: list[str] = field(default_factory=list)  # 宽容降级：被忽略的悬空条目清单
   ```
3. `load_config`：在 `genre_priority_raw = ...`（:204）之前加一行 `warnings: list[str] = []`；三处校验循环改为收集+跳过（**重复库名 ConfigError 保留不动**）：
   ```python
       for name in genre_priority_raw:
           name = str(name).strip()
           if name not in libraries:
               warnings.append(f"genre_priority 引用了未定义的库：{name}，已忽略")
               continue
           if name in genre_priority:
               raise ConfigError(f"genre_priority 中库名重复：{name}")
           genre_priority.append(name)
   ```
   genre_aliases 循环（:214-219）同型：`if v not in libraries:` 分支改为 `warnings.append(f"genre_aliases[{k!r}] 指向未定义的库：{v}，已忽略")` + `continue`；weak_genre_aliases 循环（:221-226）同型，文案前缀 `weak_genre_aliases[{k!r}]`。
4. `return Config(...)`（:285-301）末尾追加关键字参数 `warnings=warnings,`。
5. `describe()`（:306-332）返回 dict 中 `"weak_genre_aliases": ...` 之后新增键：`"warnings": list(cfg.warnings),`。`raw_describe()` 不改。

### 2.2 config.example.toml（:37 单行 inline table）

删除 `'thriller' = '惊悚', `（含尾随空格）与 `, 'musical' = '音乐'`（含前导空格），行内其余键值对原样保留。

### 2.3 app/ui/config_tab.py（refresh，:302-317）

`desc, err = self.state.config_describe()` 之后、原 if/else 之前加 `warnings = (desc or {}).get("warnings") or []`；原二分支改三分支，优先级 error > warning > 隐藏：

```python
        if err is not None:
            self.cfg_msg.setText(
                f"当前配置无效，展示的是兜底值，保存前请先修正：\n{err}")
            self.cfg_msg.setStyleSheet(f"color:{theme.BAD};")
            self.cfg_msg.show()
        elif warnings:
            self.cfg_msg.setText(
                "配置已加载，但以下无效条目已被忽略"
                "（保存会原样写盘，建议修正后重新保存）：\n" + "\n".join(warnings))
            self.cfg_msg.setStyleSheet(f"color:{theme.WARN};")
            self.cfg_msg.show()
        else:
            self.cfg_msg.hide()   # 配置已恢复有效（如外部修正），横幅随之消失
```

`theme.WARN` 已存在（app/ui/theme.py:21）。`_on_save`（:398-413）不动——保存成功后 `refresh(force=True)` 自然以橙横幅接替。

## ③ 先红后绿回归测试

### 3.1 tests/test_config.py——改写 3 例（原地换语义，测试数量不减）+ 新增 5 例

顶部 import 补：`from pathlib import Path`、`import tomllib`、导入块加 `save_config_dict`（与现有 `from app.core.config import (...)` 合并；这些名字实现前均已存在，import 不炸，红相全部来自异常/断言本身）。

改写（文件 :58-65、:141-145）：

```python
def test_unknown_priority_downgraded_to_warning(tmp_path):
    cfg = load_config(build_env(tmp_path, overrides={
        "genre_priority": ["不存在", "科幻"]}))
    assert cfg.genre_priority == ["科幻"]            # 悬空条目被丢弃、合法条目保留
    assert len(cfg.warnings) == 1
    assert "genre_priority" in cfg.warnings[0] and "不存在" in cfg.warnings[0]


def test_unknown_alias_downgraded_to_warning(tmp_path):
    cfg = load_config(build_env(tmp_path, overrides={
        "genre_aliases": {"Sci-Fi": "科幻", "x": "不存在"}}))
    assert cfg.genre_aliases == {"Sci-Fi": "科幻"}
    assert any("genre_aliases" in w and "不存在" in w for w in cfg.warnings)


def test_weak_alias_unknown_downgraded_to_warning(tmp_path):
    cfg = load_config(build_env(
        tmp_path, overrides={"weak_genre_aliases": {"护士": "不存在"}}))
    assert cfg.weak_genre_aliases == {}
    assert any("weak_genre_aliases" in w and "不存在" in w for w in cfg.warnings)
```

新增（文件末尾追加）：

```python
# ---------------- 悬空引用宽容降级（卡 card-20261112-lenient-aliases） ----------------

def test_dangling_entries_excluded_from_config_hash(tmp_path):
    """被忽略的悬空条目不得进 config_hash，否则计划页误报配置漂移。"""
    h1 = load_config(build_env(tmp_path)).config_hash()
    h2 = load_config(build_env(
        tmp_path / "b", overrides={"genre_aliases": {"僵尸": "不存在"}})).config_hash()
    assert h1 == h2


def test_describe_includes_warnings(tmp_path):
    cfg = load_config(build_env(
        tmp_path, overrides={"genre_aliases": {"x": "不存在"}}))
    assert describe(cfg)["warnings"] == cfg.warnings
    assert cfg.warnings                              # 非空


def test_describe_warnings_empty_when_clean(tmp_path):
    assert describe(load_config(build_env(tmp_path)))["warnings"] == []


def test_save_config_dict_accepts_dangling_aliases(tmp_path):
    """含悬空别名的表单保存必须成功：写盘透明 + 返回的 Config 带警告。"""
    cfg_path = build_env(tmp_path)
    d = describe(load_config(cfg_path))
    d["genre_aliases"] = {"幽灵": "不存在"}
    new_cfg = save_config_dict(cfg_path, d)
    assert any("幽灵" in w for w in new_cfg.warnings)
    assert "幽灵" in cfg_path.read_text(encoding="utf-8")     # 原样写盘
    assert not (tmp_path / "runtime" / "config.candidate.toml").exists()  # 原子替换完成


def test_example_config_aliases_are_self_consistent():
    """example 的别名/优先级必须全部指向 example 自带的库（tomllib 裸解析——
    example 路径指向不存在的盘符，走完整 load_config 会卡在 _require_dir）。"""
    root = Path(__file__).resolve().parents[1]
    with open(root / "config.example.toml", "rb") as fh:
        data = tomllib.load(fh)
    names = {lib["name"] for lib in data.get("library", [])}
    assert "thriller" not in (data.get("genre_aliases") or {})
    assert "musical" not in (data.get("genre_aliases") or {})
    assert all(v in names for v in (data.get("genre_aliases") or {}).values())
    assert all(v in names for v in (data.get("weak_genre_aliases") or {}).values())
    assert all(n in names for n in data.get("genre_priority", []))
```

先红预期（实现前跑一轮，tests/test_config.py 8 红）：3 例改写与 `test_dangling_entries_excluded_from_config_hash`、`test_describe_includes_warnings`、`test_save_config_dict_accepts_dangling_aliases` 共 6 例红于悬空条目仍被拒——测试体直接冒出 `ConfigError: genre_priority 引用了未定义的库：不存在`（genre_aliases / weak 同型文案）；`test_describe_warnings_empty_when_clean` 红于 `KeyError: 'warnings'`；`test_example_config_aliases_are_self_consistent` 红于 `assert 'thriller' not in ...` 失败。

### 3.2 tests/test_config_tab.py——新增 3 例（widget 段末尾追加）

顶部 import 补 `from app.ui import theme`。

```python
# ---------------- 宽容降级警告横幅（卡 card-20261112-lenient-aliases） ----------------

def test_warnings_banner_lists_ignored_entries(qapp):
    desc = full_describe()
    desc["warnings"] = ["genre_aliases['x'] 指向未定义的库：不存在，已忽略"]
    tab = ConfigTab(StubState(desc), toast=lambda m: None)
    assert not tab.cfg_msg.isHidden()
    assert "已忽略" in tab.cfg_msg.text()
    assert theme.WARN in tab.cfg_msg.styleSheet()
    tab.deleteLater()


def test_error_banner_wins_over_warnings(qapp):
    desc = full_describe()
    desc["warnings"] = ["genre_aliases['x'] 指向未定义的库：不存在，已忽略"]
    tab = ConfigTab(StubState(desc, err="第 3 行：库目录不存在"), toast=lambda m: None)
    assert "当前配置无效" in tab.cfg_msg.text()
    assert theme.BAD in tab.cfg_msg.styleSheet()
    assert theme.WARN not in tab.cfg_msg.styleSheet()
    tab.deleteLater()


def test_clean_config_keeps_banner_hidden(qapp):
    tab = ConfigTab(StubState(full_describe()), toast=lambda m: None)
    assert tab.cfg_msg.isHidden()
    tab.deleteLater()
```

先红预期：仅 `test_warnings_banner_lists_ignored_entries` 红（`assert not tab.cfg_msg.isHidden()` 失败——旧逻辑无 warnings 分支恒隐藏）；`test_error_banner_wins_over_warnings` 与 `test_clean_config_keeps_banner_hidden` 钉的是既有行为，实现前即绿，允许。

跑法（先红后绿各一轮）：`py -3.12 -m pytest tests/test_config.py tests/test_config_tab.py -q`。

## ④ 验收命令（以下命令均在项目根目录执行）

```bash
py -3.12 -m ruff check app/core/config.py app/ui/config_tab.py tests/test_config.py tests/test_config_tab.py
py -3.12 -m pytest tests/test_config.py tests/test_config_tab.py -q
py -3.12 -m pytest -q
QT_QPA_PLATFORM=offscreen py -3.12 -m app --demo --screenshot artifacts/card1-config-tab.png --tab 2
```

全部须通过；ruff 0 项；全量 passed ≥ 动工前基线（动工第一步实测记录 N0）。GUI 冒烟输出 `screenshot ->` 且进程自退。

## ⑤ 约束

- 只动 ① 所列 5 个文件；警告/横幅文案逐字按卡面（含全角标点）；重复库名 ConfigError、`raw_describe`、`config_hash` 字段集、`_on_save`、`config_viewmodel.py` 一律不动。
- 仓库根 `config.toml` 与 `dist/` 下任何 config.toml 禁碰（真实用户配置）。
- 测试基线只增不减：只允许按 ③ 改写指定 3 例，禁止删除/skip 任何既有用例。
- 读取大于 4KB 文件或查看改动时，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 pointerize/read_pointer/read_diff_only 分段读，禁止整读全文。
- 只 commit 不 push。提交信息：`fix: 悬空库引用宽容降级为 warnings 并清理 example 悬空别名`，正文含 `verify: pytest 全绿 passed≥N0+8；ruff 0 项` 与 `GUI 已验证（offscreen 截图冒烟）`（GUI 变更须注明）。
- 卡外问题即停待裁决，不自行扩大范围。

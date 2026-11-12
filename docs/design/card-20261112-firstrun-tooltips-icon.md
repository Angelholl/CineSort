# 卡：首跑自洽 + 配置页 tooltip + 图标缺失告警（2026-11-12 beta 热修复 2/2）

**前置：卡 card-20261112-lenient-aliases 已验收合入**（本卡与其共改 app/core/config.py、app/ui/config_tab.py、tests/test_config.py、tests/test_config_tab.py，必须串行；本文行号为卡1 合入后基线，若漂移以符号定位为准）。

## ① 任务与范围（根因）

三处独立缺陷：
1. **首跑必炸**：`app/ui/main_window.py:215-221` 首跑把 config.example.toml 原样拷成 config.toml，拷来的 example 含 G:\ 死路径与悬空别名（卡1 已把悬空降级为警告，但 G:\ 死路径仍必然触发「source_root 不存在」ConfigError）——owner 拍板：不再拷 example，改为生成**可通过 load_config 全量校验**的最小初始配置并自动建目录。
2. **配置复杂度**：`app/ui/config_tab.py:104-126` 14 个表单行标签 2-6 字、零 tooltip；库表 4 表头（:143）同样无说明。文案从 README.md:70-131 提炼（本卡已写死，见 ③3.3）。
3. **图标静默降级**：`main_window.py:205-209` `if icon_path.exists(): setWindowIcon(...)`——缺失时一声不吭（beta 包 `_internal/assets` 整体缺失即此症状）。项目无任何 logging 设施（全 app/ 无 import logging），owner 授权最小引入，本卡拍板 stdlib logging 方案（见 ③3.2）。

范围 = 下列 6 个文件，其余一律不动。`paths.default_config_path()`（app/paths.py:41-59）已保证返回路径的父目录存在（exe 可写→exe 旁；不可写→%APPDATA%/CineSort；legacy 迁移同理），首跑落点跟着 config.toml 走即可。

## ② 改动文件清单

- Modify `app/core/config.py`（文件尾新增 `ensure_first_run_config`）
- Modify `app/ui/main_window.py`（imports :10-32、常量区 :34-38、main() 图标块、首跑块）
- Modify `app/ui/config_tab.py`（_build rows 列表与循环、lib 表头、小工具区）
- Test Modify `tests/test_config.py`（新增 3 例）
- Test Modify `tests/test_entry.py`（新增 2 例）
- Test Modify `tests/test_config_tab.py`（新增 1 例）

## ③ 改法（签名级）

### 3.1 app/core/config.py——文件尾（save_config_dict 之后）新增

```python
def ensure_first_run_config(cfg_path: Path) -> bool:
    """cfg_path 不存在时生成最小自洽初始配置并建好所需目录；已存在则不动。

    返回是否新建。目录落点跟 config.toml 走：<cfg 目录>/data/{待整理,电影,未分类}
    ——便携 exe=exe 旁 data/，安装不可写=%APPDATA%/CineSort/data（default_config_path
    已保证 cfg 目录可写）。三个目录互为兄弟，过 overlap 校验；TOML 内一律写绝对
    路径（load_config 对相对路径按进程 CWD resolve，禁止依赖 CWD）。
    生成内容必须能通过 load_config 全量校验——这是首跑不炸的硬承诺。
    """
    cfg_path = Path(cfg_path)
    if cfg_path.exists():
        return False
    base = cfg_path.parent / "data"
    inbox = base / "待整理"
    lib = base / "电影"
    fb = base / "未分类"
    for p in (inbox, lib, fb):
        p.mkdir(parents=True, exist_ok=True)
    body = {
        "source_root": str(inbox),
        "fallback_path": str(fb),
        "strategy": "smart",
        "on_conflict": "skip",
        "staging_dir": "",
        "warn_fallback_ratio": 0.15,
        "block_fallback_ratio": 0.30,
        "plot": {"enabled": True, "min_score": 2.0, "normalize": False},
        "title": {"enabled": True, "min_score": 1.0},
        "learning": {"enabled": True, "min_votes": 2},
        "genre_priority": [],
        "genre_aliases": {},
        "weak_genre_aliases": {},
        "libraries": [{"name": "电影", "path": str(lib),
                       "keywords": [], "keywords_weighted": {}}],
    }
    cfg_path.write_text(dump_config_text(body), encoding="utf-8")
    return True
```

（`dump_config_text` 为现有函数；三个数据目录的 `mkdir(parents=True)` 已顺带建好 cfg 目录，无需额外 mkdir。）

### 3.2 app/ui/main_window.py

1. stdlib 导入区（:10-11 `import sys` 之前）加 `import logging`；项目导入区在 `from ..state import AppState`（:27）之前加 `from ..core.config import ensure_first_run_config`。
2. 常量区 `SLOW_MS = 2000`（:35）之后加一行：
   ```python
   log = logging.getLogger("cinesort")
   ```
3. `main()` 内 `args = parser.parse_args(argv)`（:195）之后加：
   ```python
       logging.basicConfig(level=logging.INFO,
                           format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
   ```
   （root 已有 handler 时 basicConfig 为 no-op，幂等。）
4. 图标块（:205-209）改为：
   ```python
       icon_path = resource_root() / "assets" / "icon" / "cinesort.ico"
       if icon_path.exists():
           app.setWindowIcon(QIcon(str(icon_path)))
       else:
           log.warning("应用图标缺失：%s（窗口使用系统默认图标，请检查安装完整性）",
                       icon_path)
   ```
5. 首跑块（:215-221 的 `if not cfg_path.exists(): ...` 五行）整段替换为一行：
   ```python
           ensure_first_run_config(cfg_path)
   ```
   （`from ..paths import default_config_path, resource_root` 局部导入保留不动。）

### 3.3 app/ui/config_tab.py

1. 小工具区（`_hbox` 前后任意相邻位置）新增：
   ```python
    def _apply_tip(self, w: QWidget, tip: str) -> None:
        """行 tooltip：容器与其全部子控件同文案（覆盖 _path_row/_hbox 复合行）。"""
        w.setToolTip(tip)
        for child in w.findChildren(QWidget):
            child.setToolTip(tip)
   ```
2. `_build` 的 `rows` 列表（:104-126）从二元组扩为三元组，循环（:127-131）改为：
   ```python
        for r, (label, w, tip) in enumerate(rows):
            cap = QLabel(label)
            cap.setProperty("dim", True)
            cap.setToolTip(tip)
            self._apply_tip(w, tip)
            grid.addWidget(cap, r, 0)
            grid.addWidget(w, r, 1)
   ```
   14 行 tooltip 文案逐字钉死（widget 仍为原对象，仅加第三元）：
   - `("源目录", <原 _path_row>, "待归类影片的源根目录。工具扫描其下的影片文件夹（含两层嵌套），扫描只读；点「执行选中」后才会把影片文件夹搬进各媒体库")`
   - `("兜底库", <原>, "兜底库目录：题材未映射、摘要/标题预判和自学习都无法判定时的落点。目录必须已存在，可与源根同盘")`
   - `("暂存目录", <原>, "跨盘搬运的暂存目录（可选）。默认自动放在目标库所在盘、库根之外（目录名 .nfo-sorter-staging）：先整目录暂存并逐文件校验，再原子改名进库")`
   - `("策略", self.f_strategy, "smart：多库命中时先用摘要评分择优，评分不足以区分再按优先级表（推荐）；priority：严格按优先级表，摘要只用于题材完全未映射时的预判；genre_only：只看题材规则，完全不用摘要")`
   - `("冲突处理", self.f_on_conflict, "目标库已有同名影片文件夹时：skip 跳过并写冲突报告（推荐）；rename 加 \" (2)\" 后缀，要求 NFO 带 tmdb/imdb id，否则自动仍按跳过")`
   - `("兜底提醒阈值", self.f_warn, "落入兜底库的影片比例超过此值时提醒——这是规则（别名表+优先级）质量的直观指标")`
   - `("兜底阻断阈值", self.f_block, "超过此值默认阻断执行，需在确认框中逐项显式越过；通常说明别名表覆盖不足或优先级排布不当")`
   - `("剧情简介", <原 _hbox 复合行>, "摘要关键词预判：「启用」为开关（关闭后未映射题材一律进兜底库）；「阈值」= Σ(关键词权重×出现次数) 达到才采纳；「清洗」= 按摘要长度平方根归一，摘要普遍很长时开启")`
   - `("标题启用", self.f_title_enabled, "标题弱评分开关（词表=库名+全部别名）：只在题材、摘要、自学习都判不出时作最后尝试；命中行置信度恒为低、默认不勾选")`
   - `("标题阈值", self.f_title_min_score, "标题评分采纳阈值（独立于摘要阈值，不复用 plot.min_score）")`
   - `("自学习", <原 _hbox>, "人工改判记 2 票、人工确认记 1 票，沉淀为「题材→库」映射（runtime/learned.json）；票数达「阈值」自动生效；自学习永远让位于显式规则，兜底库不参与学习")`
   - `("库优先级", self.f_priority_text, "题材优先级表：影片命中多个已映射题材时排前面的优先。建议「身份类」题材排前、「高频通用」题材排后，否则通用题材会把影片成批吸走。留空 = 无显式优先级")`
   - `("别名表", self.f_alias_text, "每行一条：别名=标准库名。NFO 题材写法→标准库名；匹配不区分大小写、全半角与多余空格；不做繁简转换，繁简两种写法各写一条。别名覆盖度直接决定规则命中率")`
   - `("弱别名表", self.f_weak_alias_text, "同别名表但属弱信号：仅当影片没有任何强命中时、唯一命中才采纳，且置信度降为低、计划行默认不勾选，永不压过强别名")`
3. lib 表创建（`self.lib_table.setHorizontalHeaderLabels(...)`，:143）之后加：
   ```python
        for col, tip in enumerate((
                "标准题材名，同时是库优先级表与两张别名表里的参照名；不得含 / 或 \\",
                "Jellyfin/Emby 媒体库目录，必须已存在；库之间不得嵌套、不得与源目录重叠（保存时自动校验）",
                "摘要预判关键词，摘要中每命中一次 +1 分；不配置关键词的库不参与摘要预判",
                "加权关键词，每项 词=权重：分 = 权重 × 出现次数，用于突出强指示词")):
            self.lib_table.horizontalHeaderItem(col).setToolTip(tip)
   ```

## ④ 先红后绿回归测试

### 4.1 tests/test_config.py 新增 3 例（顶部 import 块补 `ensure_first_run_config`）

```python
# ---------------- 首跑自洽（卡 card-20261112-firstrun-tooltips-icon） ----------------

def test_first_run_bootstrap_creates_valid_config(tmp_path):
    cfg_path = tmp_path / "cfg" / "config.toml"
    assert ensure_first_run_config(cfg_path) is True
    cfg = load_config(cfg_path)                       # 必须全量校验通过（首跑不炸的硬承诺）
    assert list(cfg.libraries) == ["电影"]
    base = cfg_path.parent / "data"
    assert cfg.source_root == (base / "待整理").resolve()
    assert cfg.fallback_path == (base / "未分类").resolve()
    assert (base / "待整理").is_dir() and (base / "电影").is_dir() \
        and (base / "未分类").is_dir()


def test_first_run_bootstrap_is_idempotent(tmp_path):
    cfg_path = tmp_path / "config.toml"
    assert ensure_first_run_config(cfg_path) is True
    text = cfg_path.read_text(encoding="utf-8")
    assert ensure_first_run_config(cfg_path) is False
    assert cfg_path.read_text(encoding="utf-8") == text


def test_first_run_bootstrap_independent_of_cwd(tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    cfg_path = tmp_path / "cfg" / "config.toml"
    ensure_first_run_config(cfg_path)
    cfg = load_config(cfg_path)
    assert cfg.source_root == (cfg_path.parent / "data" / "待整理").resolve()
```

### 4.2 tests/test_entry.py 新增 2 例（文件末尾追加）

```python
def test_first_run_bootstrap_wired_in_main():
    """首跑不再拷 example：main() 改调 ensure_first_run_config。"""
    src = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert "ensure_first_run_config(cfg_path)" in src
    assert "from ..core.config import ensure_first_run_config" in src
    assert "config.example.toml" not in src           # 拷贝 example 的旧路径退场


def test_icon_missing_warns_via_logging():
    """图标缺失从静默降级改为显式日志告警（beta 包缺 _internal/assets 的教训）。"""
    src = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert "logging.basicConfig" in src
    assert 'log.warning("应用图标缺失' in src
```

### 4.3 tests/test_config_tab.py 新增 1 例（widget 段末尾追加）

```python
# ---------------- 配置页全字段 tooltip（卡 card-20261112-firstrun-tooltips-icon） ----------------

def test_config_fields_have_tooltips(qapp):
    tab = ConfigTab(StubState(full_describe()), toast=lambda m: None)
    expects = {
        "f_source_root": "扫描只读",
        "f_fallback_path": "必须已存在",
        "f_staging_dir": ".nfo-sorter-staging",
        "f_strategy": "genre_only",
        "f_on_conflict": "rename",
        "f_warn": "直观指标",
        "f_block": "阻断执行",
        "f_plot_enabled": "平方根",
        "f_title_enabled": "最后尝试",
        "f_title_min_score": "不复用",
        "f_learning_enabled": "learned.json",
        "f_priority_text": "吸走",
        "f_alias_text": "繁简",
        "f_weak_alias_text": "永不压过",
    }
    for attr, needle in expects.items():
        tip = getattr(tab, attr).toolTip()
        assert needle in tip, f"{attr} tooltip 缺「{needle}」"
    headers = [tab.lib_table.horizontalHeaderItem(c).toolTip() for c in range(4)]
    assert "标准题材名" in headers[0]
    assert "不得嵌套" in headers[1]
    assert "+1 分" in headers[2]
    assert "权重 × 出现次数" in headers[3]
    tab.deleteLater()
```

先红预期（实现前跑一轮，共 6 例红）：tests/test_config.py 因顶部 import 不存在的 `ensure_first_run_config` **整模块收集失败**（`ImportError: cannot import name 'ensure_first_run_config'`，4.1 的 3 例随之全部呈现为红，属预期形态）；tests/test_entry.py 2 例红于 `assert "ensure_first_run_config(cfg_path)" in src` / `assert "logging.basicConfig" in src` 失败；tests/test_config_tab.py 1 例红于断言消息 `f_source_root tooltip 缺「扫描只读」`。

跑法（先红后绿各一轮）：`py -3.12 -m pytest tests/test_config.py tests/test_entry.py tests/test_config_tab.py -q`。

## ⑤ 验收命令（以下命令均在项目根目录执行）

```bash
py -3.12 -m ruff check app/core/config.py app/ui/main_window.py app/ui/config_tab.py tests/test_config.py tests/test_entry.py tests/test_config_tab.py
py -3.12 -m pytest tests/test_config.py tests/test_entry.py tests/test_config_tab.py -q
py -3.12 -m pytest -q
QT_QPA_PLATFORM=offscreen py -3.12 -m app --demo --screenshot artifacts/card2-demo.png --tab 2
```

全部须通过；ruff 0 项；全量 passed ≥ 卡前基线（动工第一步实测记录 N1）。GUI 冒烟输出 `screenshot ->` 且进程自退。首跑端到端有效性由 4.1 单测（tmp_path 全量 load_config）证明；exe 真首跑由部署任务（主模型亲执）在 dist 重建后覆盖，本卡不做。

## ⑥ 约束

- 只动 ② 所列 6 个文件；tooltip/警告/日志文案逐字按卡面；`dump_config_text`、`default_config_path`、`resource_root`、慢 tick/dirty 机制、`_on_save` 一律不动；learned 表头不加 tooltip（超范围）。
- 仓库根 `config.toml` 与 `dist/` 下任何 config.toml 禁碰（真实用户配置）；本卡 GUI 冒烟仅用 `--demo` 模式，不读真实配置。
- 测试基线只增不减：禁止删除/skip 任何既有用例。
- 读取大于 4KB 文件或查看改动时，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 pointerize/read_pointer/read_diff_only 分段读，禁止整读全文。
- 只 commit 不 push。提交信息：`feat: 首跑生成自洽最小配置；配置页全字段 tooltip；图标缺失显式告警`，正文含 `verify: pytest 全绿 passed≥N1+6；ruff 0 项` 与 `GUI 已验证（offscreen 截图冒烟）`（GUI 变更须注明）。
- 卡外问题即停待裁决，不自行扩大范围。

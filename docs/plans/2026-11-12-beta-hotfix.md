# Beta 热修复实现计划：配置宽容降级 + 首跑自洽 + tooltip + 图标告警

- 日期：2026-11-12
- 基线：I:\CineSort 当前 HEAD（本文 `文件:行号` 均为该基线，施工若漂移以符号定位为准）
- **规格来源：owner 口述拍板（2026-11-12 会话，原文见本文「2. 规格」）；docs/decision-log.md 截至 D-20261112-01 尚无对应条目，收口后由主模型补登记。**
- 计划真值：本文件（拆解与验收口径）；实现交编程执行者（卡1、卡2 各一张卡面，顺序执行）；任务3 部署由主模型亲执，不制卡。
- 执行卡面：`docs/design/card-20261112-lenient-aliases.md`（任务1）、`docs/design/card-20261112-firstrun-tooltips-icon.md`（任务2，前置=卡1 已验收合入）。

## 1. 目标与架构

**目标：** 消灭「首跑必炸」的悬空别名 ConfigError（改为宽容降级+警告横幅），首跑改为生成自洽最小配置，配置页全字段 tooltip，图标缺失显式日志告警，最后重建 dist/安装器交付。

**架构：** 三处改动互不纠缠——①校验层（app/core/config.py）把「指向未定义库」从硬错误降级为 `Config.warnings` 清单，GUI 慢 tick 处以橙色横幅呈现；②入口层（app/ui/main_window.py）首跑用确定性生成器替代 example 拷贝；③展示层（app/ui/config_tab.py）静态 tooltip。classifier/planner 对降级后的 cfg 零改动（悬空条目被丢弃后自然不参与映射，app/core/classifier.py:42,50,152-153 只读字典）。

## 2. 规格（owner 口述拍板，逐条）

1. **修复A（任务1）**：load_config 对 genre_aliases / weak_genre_aliases / genre_priority 中指向未定义库的条目不再报错——丢弃并收集警告（Config 携带 warnings 列表）；GUI 加载后显示橙/黄色警告横幅列出被忽略条目；保存含悬空条目的表单必须成功（写盘透明，下次加载再警告）。config.example.toml:37 的 `'thriller' = '惊悚'`、`'musical' = '音乐'` 两对悬空别名删除（示例自洽）。回归测试基线只增不减。
2. **修复B（任务2）**：①配置页每个字段加 tooltip（文案从 README.md:70-131 提炼）；②首跑不再拷 example，改为生成可通过 load_config 全量校验的最小初始配置（自动建目录，落点见 D2）；③main_window.py:205-209 图标缺失从静默降级改为显式日志告警（日志设施见 D4）。
3. **任务3（部署，主模型亲执）**：跑 tools/build_exe.ps1 重建 dist + tools/build_installer.ps1 出安装器；验证新 exe 内嵌图标与 `_internal/assets` 在位（ExtractAssociatedIcon 抽图对比）；提醒用户重装后桌面图标可能需刷新图标缓存。

## 3. 现状核实（code-reader 结论已逐条读码复核）

| 关注点 | 位置 | 核实结果 |
|---|---|---|
| 悬空别名 | config.example.toml:37 | 13 个 [[library]]（:48-124）无「惊悚」「音乐」；`'thriller' = '惊悚'`、`'musical' = '音乐'` 在列，首跑拷贝即悬空 |
| 硬校验三点 | app/core/config.py:209, 214-219, 221-226 | genre_priority / genre_aliases / weak_genre_aliases 未定义库均 `raise ConfigError`；重复库名仍报错（:211），保留 |
| 首跑拷贝 | app/ui/main_window.py:215-221 | `cfg_path.write_text(example.read_text())` 原样拷贝 |
| 保存链 | app/core/config.py:422-431 | save_config_dict 写 candidate→load_config 校验（:428，悬空在此炸）→os.replace |
| GUI 兜底 | app/state.py:57-71；app/ui/config_tab.py:302-313 | ConfigError 时 raw_describe 回填表单；红横幅 cfg_msg 用 `theme.BAD`（config_tab.py:310） |
| 别名解析器 | app/ui/config_viewmodel.py:23-33 | `_parse_alias_lines` 无校验，form_to_body 原样透传——保存链唯一卡点就是 :428，宽容降级后无阻 |
| 图标 | main_window.py:205-209 | `if icon_path.exists(): setWindowIcon`——缺失即静默跳过 |
| 警告色 | app/ui/theme.py:21 | `WARN = "#e5a83b"` 现成可用 |
| 便携/APPDATA | app/paths.py:41-59 | exe 可写→exe 旁 config.toml；不可写→%APPDATA%/CineSort/config.toml（含 legacy 迁移）；两条路径的父目录均已保证存在 |
| 相对路径语义 | app/core/config.py:130-132, 261-267 | `_abs()` 不 resolve，`.resolve()` 统一相对**进程 CWD**——首跑配置必须写绝对路径 |
| logging | 全 app/ grep 无 `logging`/`getLogger` | 项目零日志设施，需最小引入 |
| 测试设施 | tests/ | 无 pytest-qt；GUI 测试 offscreen+`QApplication.instance() or QApplication([])`（tests/test_config_tab.py:12,138-141）；config 域挂 tests/test_config.py（29 例，conftest.build_env overrides 范式 :35-72）；无任何测试断言 example 内容/首跑拷贝 |
| Config 构造点 | config.py:285 + tests/test_classifier.py:20 / test_learned.py:18 / test_scanner.py:11 | 全部关键字传参——尾部追加带默认值字段零破坏 |
| load_config 调用点 | app/core/jobs.py:108,121,141,275；app/state.py:53,59,148,153；app/ui/plan_tab.py:654 | 只读 cfg 字段，签名不变即可 |
| 构建链 | tools/build_exe.ps1:16-21 与 CineSort.spec:8,35 含 icon+assets | `.github/workflows/release.yml:39-43` **未含** `--icon/--add-data assets`——云端产物必缺图标（beta 缺图标最可能根因），本计划不改 CI，登记待办 |
| 用户实机 | 仓库根 config.toml | 已是自洽真实配置（E 盘库），卡内步骤禁碰；dist/CineSort/config.toml 同禁（部署任务3 备份规则见步骤 3.1） |

## 4. 设计决策（实施者必须照此执行，不得自行变更）

- **D1 warnings 载体**：`Config` dataclass **末尾**追加 `warnings: list[str] = field(default_factory=list)`；load_config 内收集；`describe()`（config.py:306-332）返回 dict 新增键 `"warnings": list(cfg.warnings)`；`raw_describe()` **不改**（兜底形状无 warnings，GUI 用 `.get("warnings") or []` 容忍缺键）。`config_hash()` **不含** warnings 与被丢弃条目（哈希稳定，计划页不误报漂移）。警告文案逐字钉死：
  - `f"genre_priority 引用了未定义的库：{name}，已忽略"`
  - `f"genre_aliases[{k!r}] 指向未定义的库：{v}，已忽略"`
  - `f"weak_genre_aliases[{k!r}] 指向未定义的库：{v}，已忽略"`
- **D2 首跑落点与路径语义**（写死）：首跑目录一律跟 config.toml 走——`<config.toml 所在目录>/data/{待整理,电影,未分类}` 三个兄弟目录（互不嵌套，过 overlap 校验）。便携 exe=exe 旁 data/；安装不可写=%APPDATA%/CineSort/data；legacy 迁移路径=旧目录 data/。生成的 TOML 一律写**绝对路径**（相对路径会被 resolve 到进程 CWD，禁止使用）。
- **D3 首跑生成器签名**：新函数 `ensure_first_run_config(cfg_path: Path) -> bool` 落 app/core/config.py（save_config_dict 之后）；`cfg_path.exists()` 即返回 False 不动文件（幂等）；否则 mkdir 三个数据目录 + 用现有 `dump_config_text()` 序列化内置 dict 写盘，返回 True。初始配置内容钉死：strategy=smart、on_conflict=skip、阈值 0.15/0.30、plot/title/learning 全默认开启、`genre_priority=[]`、两张别名表空、唯一库 `name="电影"`（keywords 空）。main_window.py:215-221 整段替换为 `ensure_first_run_config(cfg_path)` 一行。首跑生成的端到端有效性由单测（tmp_path 全量 load_config）证明；exe 真首跑由任务3 步骤 3.6 覆盖（dist 重建后 config.toml 不存在）。
- **D4 图标告警**：main_window.py 引入 stdlib logging——模块级 `log = logging.getLogger("cinesort")`；`main()` 开头 `logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")`（幂等，已有 handler 时 no-op）；图标缺失走 `log.warning("应用图标缺失：%s（窗口使用系统默认图标，请检查安装完整性）", icon_path)`。
- **D5 警告横幅**：复用 cfg_msg（config_tab.py:169-174）单横幅，优先级 error > warning > 隐藏（config_tab.py refresh :302-317 三分支）。警告文案钉死：`"配置已加载，但以下无效条目已被忽略（保存会原样写盘，建议修正后重新保存）：\n" + "\n".join(warnings)`，样式 `setStyleSheet(f"color:{theme.WARN};")`。`_on_save` 成功分支不改（refresh(force=True) 自然以橙横幅接替）。
- **D6 tooltip 机制**：config_tab.py `_build` 的 `rows` 列表（:104-126）从二元组扩为 `(label, widget, tooltip)` 三元组；新增小工具 `_apply_tip(w, tip)`（setToolTip 于容器 + `findChildren(QWidget)` 全部子控件，覆盖 _path_row/_hbox 复合行）；行标签 cap 同步 `setToolTip(tip)`。库表 4 个表头 `horizontalHeaderItem(c).setToolTip(...)`（README.md:117-124 提炼）。tooltip 文案逐字见卡2。learned 表头不加（超范围）。
- **D7 测试基线账（数字已核）**：test_config.py 现有 29 例；卡1 改写 3 例（test_unknown_priority_rejected / test_unknown_alias_rejected / test_weak_alias_unknown_lib_rejected 原地换语义，数量不减）+ 新增 5 例；卡1 GUI（test_config_tab.py，现 32 例）新增 3 例 → 卡1 净 +8。卡2 新增 test_config 3 例 + test_entry 2 例 + test_config_tab 1 例 → 净 +6。**总计净 +14**（收尾全量基线 ≥ 卡前 N0+14）。**禁止删除或 skip 任何既有用例**；执行者第一步实测记录全量 passed 数 N0。
- **D8 example 自洽测试**：tomllib 裸解析断言（**不走 load_config**——example 路径指向不存在盘符，完整校验会卡在 `_require_dir`，与别名自洽性无关）。
- **D9 验收命令口径**（承 docs/decision-log.md D-20261102-02 与卡-20261112 系列先例）：`py -3.12 -m ruff check <本卡改动文件>` 0 项；`py -3.12 -m pytest <定向> -q`；`py -3.12 -m pytest -q` 全量。项目无 pyproject.toml/ruff 配置，ruff 走默认规则 + 改动文件零项纪律。
- **D10 卡内冒烟只用 `--demo`**：仓库根 config.toml 是用户真实配置，执行者不得以无 `--config` 的真实模式跑 GUI（会加载真实配置且可能生成 runtime 锁）；真实首跑冒烟只在任务3 的 dist 里做（重建后 config.toml 不存在，才是真首跑）。

## 5. 全局约束

- 测试基线只增不减（D7 账目）；修 bug 必带回归测试。
- 不重构无关代码；GUI 变更提交信息注明「GUI 已验证/未验证」。
- 仓库根 config.toml、dist/ 下任何 config.toml、用户实机配置（旧 beta 机，D-20261112-01 已删除其目录）**卡内步骤一律禁碰**；部署任务3 对 dist/CineSort/config.toml 的处置按步骤 3.1 备份规则执行。
- 执行者只 commit 不 push；Conventional 前缀+中文描述；只动卡面所列文件。
- 步骤与卡面不出现真实用户绝对路径。
- 卡2 前置 = 卡1 已验收合入（两卡均动 config.py / config_tab.py / test_config.py / test_config_tab.py，必须串行）。

## 6. 任务1（=卡 card-20261112-lenient-aliases.md）：宽容降级 + example 自洽

**文件：**
- Modify `app/core/config.py`（docstring :8；Config :94 尾部；load_config :204-226；构造 :285-301；describe :306-332）
- Modify `config.example.toml`（:37 删两对别名）
- Modify `app/ui/config_tab.py`（refresh :302-317）
- Test Modify `tests/test_config.py`（改写 :58-60, :63-65, :141-145；新增 5 例）
- Test Modify `tests/test_config_tab.py`（新增 3 例）

**接口：** Consumes 无新增。Produces：`Config.warnings: list[str]`；`describe(cfg)["warnings"] -> list[str]`（任务2 的横幅测试与部署冒烟消费）。

**步骤：**
- [ ] 1. 基线：`py -3.12 -m pytest -q` 全绿，记录 passed 总数 N0（收尾核对用）。核对输出无 failed/error。
- [ ] 2. 红（核心层）：按卡1 §3.1 改写 3 例 + 新增 5 例写入 tests/test_config.py（含 from pathlib import Path / tomllib / save_config_dict / describe 导入补齐）。
- [ ] 3. 跑 `py -3.12 -m pytest tests/test_config.py -q`：预期 8 红——6 例红于悬空条目仍被拒（测试体直接冒出 `ConfigError: genre_priority 引用了未定义的库：不存在` 等）、`test_describe_warnings_empty_when_clean` 红于 `KeyError: 'warnings'`、example 自洽例红于 `assert 'thriller' not in ...` 失败。
- [ ] 4. 绿（核心层）：按卡1 §2.1 修改 app/core/config.py（docstring、warnings 字段、三处降级、构造尾部、describe 键、`warnings: list[str] = []` 初始化），同步按卡1 §2.2 删 config.example.toml:37 的 `'thriller' = '惊悚', ` 与 `, 'musical' = '音乐'`。
- [ ] 5. 跑 `py -3.12 -m pytest tests/test_config.py -q`：全绿（29+5=34 例）。
- [ ] 6. 红（GUI 层）：按卡1 §3.2 在 tests/test_config_tab.py 新增 3 例（import theme 补入）。
- [ ] 7. 跑 `py -3.12 -m pytest tests/test_config_tab.py -q`：预期 1 红（warnings 横幅例 `assert not cfg_msg.isHidden()` 失败）+2 绿（error 优先级例与 clean 隐藏例钉的是既有行为，实现前即绿，允许）。
- [ ] 8. 绿（GUI 层）：按卡1 §2.3 改 config_tab.py refresh 三分支。
- [ ] 9. 跑 `py -3.12 -m pytest tests/test_config_tab.py -q`：全绿（32+3=35 例）。
- [ ] 10. 静态：`py -3.12 -m ruff check app/core/config.py app/ui/config_tab.py tests/test_config.py tests/test_config_tab.py` → 0 项。
- [ ] 11. 全量：`py -3.12 -m pytest -q` → 全绿且 passed ≥ N0+8。
- [ ] 12. GUI 冒烟：`QT_QPA_PLATFORM=offscreen py -3.12 -m app --demo --screenshot artifacts/card1-config-tab.png --tab 2` → stdout 出现 `screenshot ->` 且进程自退；截图存在（页面正常渲染即算过，横幅断言由单测覆盖）。
- [ ] 13. commit（只 commit 不 push）：`fix: 悬空库引用宽容降级为 warnings 并清理 example 悬空别名`，正文 `verify: pytest 全绿 passed≥N0+8；ruff 0 项` + `GUI 已验证（offscreen 截图冒烟）`。

## 7. 任务2（=卡 card-20261112-firstrun-tooltips-icon.md）：首跑自洽 + tooltip + 图标告警

**前置：任务1 已验收合入（行号以其后的工作树为准，按符号定位；config_tab.py 行号不受卡1 影响——卡1 只改 refresh 区 :302-317，rows 区 :104-131 行号不变；config.py 行号在 :204 之后漂移，按符号定位）。**

**文件：**
- Modify `app/core/config.py`（文件尾 save_config_dict 之后新增 ensure_first_run_config）
- Modify `app/ui/main_window.py`（import :10-32 区、常量 :34-38 区、main() 图标块 :205-209、首跑块 :215-221）
- Modify `app/ui/config_tab.py`（_build rows :104-131、lib 表头 :142-148、小工具区 :224 起新增 _apply_tip）
- Test Modify `tests/test_config.py`（新增 3 例）
- Test Modify `tests/test_entry.py`（新增 2 例）
- Test Modify `tests/test_config_tab.py`（新增 1 例）

**接口：** Consumes `dump_config_text(d: dict) -> str`（config.py:376，任务1 后仍在）、`Config.warnings`（任务1 Produces）。Produces：`ensure_first_run_config(cfg_path: Path) -> bool`（任务3 部署冒烟消费：exe 首跑自动生成合法配置）。

**步骤：**
- [ ] 1. 基线：`py -3.12 -m pytest -q` 全绿，记录 passed 总数 N1（=任务1 收尾值）。
- [ ] 2. 红（首跑）：按卡2 §4.1 在 tests/test_config.py 新增 3 例（import 块补 ensure_first_run_config）。
- [ ] 3. 红（入口/tooltip）：按卡2 §4.2 在 tests/test_entry.py 新增 2 例、按卡2 §4.3 在 tests/test_config_tab.py 新增 1 例。
- [ ] 4. 跑 `py -3.12 -m pytest tests/test_config.py tests/test_entry.py tests/test_config_tab.py -q`：预期 6 例红——tests/test_config.py 因顶部 import 不存在的名字**整模块收集失败**（`ImportError: cannot import name 'ensure_first_run_config'`，3 例随之呈红，属预期形态）；test_entry 2 例红于 `assert "ensure_first_run_config(cfg_path)" in src` / `assert "logging.basicConfig" in src` 失败；test_config_tab 1 例红于 `f_source_root tooltip 缺「扫描只读」` 断言消息。
- [ ] 5. 绿（首跑）：按卡2 §3.1 在 app/core/config.py 新增 ensure_first_run_config（内置 dict + dump_config_text，D2/D3 钉死内容）。
- [ ] 6. 绿（入口）：按卡2 §3.2 改 main_window.py（logging 引入 + basicConfig + 图标 else 分支 log.warning + 首跑一行化）。
- [ ] 7. 绿（tooltip）：按卡2 §3.3 改 config_tab.py（rows 三元组 + _apply_tip + 表头 tooltip，文案逐字照卡2）。
- [ ] 8. 跑 `py -3.12 -m pytest tests/test_config.py tests/test_entry.py tests/test_config_tab.py -q`：全绿。
- [ ] 9. 静态：`py -3.12 -m ruff check app/core/config.py app/ui/main_window.py app/ui/config_tab.py tests/test_config.py tests/test_entry.py tests/test_config_tab.py` → 0 项。
- [ ] 10. 全量：`py -3.12 -m pytest -q` → 全绿且 passed ≥ N1+6（即总基线 N0+14）。
- [ ] 11. GUI 冒烟：`QT_QPA_PLATFORM=offscreen py -3.12 -m app --demo --screenshot artifacts/card2-demo.png --tab 2` → stdout 出现 `screenshot ->` 且进程自退。**禁止真实模式冒烟（D10）**；首跑端到端由步骤 2-5 单测（tmp_path 全量 load_config）证明，exe 真首跑由任务3 步骤 3.6 覆盖。
- [ ] 12. commit（只 commit 不 push）：`feat: 首跑生成自洽最小配置；配置页全字段 tooltip；图标缺失显式告警`，正文 `verify: pytest 全绿 passed≥N1+6；ruff 0 项` + `GUI 已验证（offscreen 截图冒烟）`。

## 8. 任务3（部署，主模型亲执，不制卡）

**前置：** 任务1、任务2 均已验收合入，`py -3.12 -m pytest -q` 全绿。以下命令均在项目根目录执行（PowerShell/pwsh 7；build 脚本 `#requires` 7.0）。

- [ ] 3.1 备份 dist 内旧配置（build 会重建 dist）：`if (Test-Path dist/CineSort/config.toml) { Copy-Item dist/CineSort/config.toml artifacts/dist-config-backup-20261112.toml }`。**处置规则（写死）**：备份文件 source_root 指向**存在**的目录→判定用户真实配置，第 3.6 步后恢复回 dist；指向不存在盘符（如历史 G:\ 模板）→留档不恢复。
- [ ] 3.2 重建 onedir：`pwsh -File tools/build_exe.ps1` → 末行绿字 `构建完成: dist\CineSort\CineSort.exe`；`Test-Path dist/CineSort/_internal/assets/icon/cinesort.ico` 为 True。
- [ ] 3.3 核对 example 已自洽进入包：`Select-String -Path dist/CineSort/_internal/config.example.toml -Pattern "thriller|musical"` → 无匹配。
- [ ] 3.4 内嵌图标抽验：`pwsh -NoProfile -Command "Add-Type -AssemblyName System.Drawing; [System.Drawing.Icon]::ExtractAssociatedIcon((Join-Path (Get-Location) 'dist/CineSort/CineSort.exe')).ToBitmap().Save((Join-Path (Get-Location) 'artifacts/exe-icon.png'))"` → 目验 artifacts/exe-icon.png 为「入架」图标（D-20261106-01）非通用图标。
- [ ] 3.5 安装器：`pwsh -File tools/build_installer.ps1` → `installer/Output/CineSort-setup-<ver>.exe` 生成且 >20MB。**分支规则（写死）**：本机无 ISCC（脚本 exit 1）→ 不阻塞，交付 onedir 目录 dist/CineSort/，并在完成通知注明。
- [ ] 3.6 首跑冒烟（同时验证任务2 真首跑，此时 dist 内无 config.toml）：`./dist/CineSort/CineSort.exe --screenshot artifacts/dist-firstrun.png --tab 2`（截图后进程自退；30s 未退则 `taskkill /F /IM CineSort.exe`）→ 核对 `dist/CineSort/config.toml` 已自动生成、`dist/CineSort/data/{待整理,电影,未分类}` 三目录存在；截图目验配置页无红/橙横幅。随后按 3.1 处置规则决定是否用备份覆盖该生成配置。
- [ ] 3.7 收口：`git status` 确认 dist/installer/artifacts 未混入提交（.gitignore 口径）；完成通知附：①产物路径与 SHA256（`Get-FileHash installer/Output/CineSort-setup-*.exe`）；②用户提醒——重装后桌面快捷方式图标可能需刷新图标缓存（`ie4uinit.exe -show` 或重启 explorer/注销重登）；③登记决策日志（D-20261112-02 宽容降级、D-20261112-03 首跑自洽/告警，规格=本文 §2）；④登记 CI 待办——`.github/workflows/release.yml:39-43` 云端构建缺 `--icon` 与 `--add-data "assets/icon/cinesort.ico;assets/icon"`，云端产物必缺图标，后续卡补齐。

## 9. 自审五查记录（writing-plans，已就地修两处）

1. **规格覆盖**：owner §2 规格逐条落位——宽容降级/横幅/example（任务1 D1/D5/步骤1-13）、tooltip/首跑/图标告警（任务2 D3/D4/D6/步骤1-12）、重建+抽图+缓存提醒（任务3）。无缺口。
2. **步骤扫描**：每步一个动作+可核对结果；测试步带测试名+断言子串；签名与内容逐字钉死（D1 警告文案、D2 目录名、D3 初始 dict、D6 tooltip 文案在卡2 内嵌）。**就地修**：①任务2 原步骤 11 误设「仓库根真实模式首跑冒烟」——仓库根 config.toml 是用户真实配置（ensure 会返回 False 不触发首跑，且有触碰真实配置之险），已改为 demo-only 冒烟并新增 D10 禁令，真首跑验证归任务3 步骤 3.6；②卡1 新增测试数原记 6 例实为 5 例（config），净增 +14 而非 +15，D7/步骤/卡面三处数字已对齐。
3. **类型一致**：`ensure_first_run_config(cfg_path: Path) -> bool` 在 D3、任务2 接口/步骤、卡2、入口静态断言四处同名同签名；`Config.warnings`/`describe()["warnings"]` 在 D1、卡1、卡2 横幅测试一致。
4. **隐含输入**：①悬空+合法混合条目（改写例覆盖）；②悬空条目保存写盘透明（save_config_dict 例覆盖）；③幂等二次首跑（idempotent 例覆盖）；④--config 指定缺失路径（首跑同样生效——generate 路径与 CWD 无关）；⑤CWD 相对性（independent_of_cwd 例覆盖）；⑥error 与 warnings 并存时横幅优先级（error_banner_wins 例覆盖）。
5. **比例**：本文为决策+核对表，未抄实现体；函数体仅在卡面以「签名级+关键实现」给出（house 卡面范式），计划正文无代码块堆叠。

# C6 — 启动链切换 PySide6 + 彻底删除网页版（server / static / main_gui / test_api）

## 一、背景与根因

四页 GUI 已齐（C3/C4/C5），但用户双击 `启动媒体分类工具.cmd` 进来的仍是网页版：启动链 `run.py` / `app/__main__.py` / `scripts/start_gui.ps1` / `scripts/start_debug.ps1` 全部指向 `app.main_gui`（HTTP 服务 + 浏览器）。D-20261102-01 已拍板：网页版彻底删除、只保留 PySide6 原生窗口。本卡完成切换与删除。

**关键迁移项**：单实例锁 `_acquire_lock`（原 `app/main_gui.py:23-40`，`runtime/app.lock` msvcrt/fcntl 非阻塞锁，失败弹窗退出码 1）只存在于 main_gui.py，`app/ui/main_window.py` 无锁——删 main_gui 前必须把锁迁入 `app/ui/main_window.py` 的 `main()`，否则丢单实例保护。

## 二、改动清单（只允许动这些）

### 删除（4 文件）
- `app/server.py`（122 行）
- `app/main_gui.py`
- `app/static/index.html`（611 行；`app/static/` 目录若空则一并删目录）
- `tests/test_api.py`（5 用例——全链路证据已 1:1 由 `tests/test_flow.py` 承接，净口径见 D-20261102-02）

### 修改
1. **`app/ui/main_window.py`**：从 main_gui.py 迁入锁——模块级函数 `_acquire_lock(runtime_dir: Path) -> bool`（原实现原样搬：`runtime/app.lock` 打开 + msvcrt.locking 非阻塞 try，Windows 外回退 fcntl——项目仅 Windows，保留 msvcrt 分支与 try/except ImportError 兜底即可）；`main()` 里非 demo 模式下、建 AppState 前：锁失败 → `QMessageBox.critical(None, "CineSort", "已有 CineSort 实例在运行（锁文件：runtime/app.lock）。")` + `return 1`。demo 模式不抢锁。锁文件句柄保持持有到进程退出（main_gui 同款，全局变量或 main 内变量存句柄）。
2. **`app/__main__.py`**：`from .ui.main_window import main`（替换 main_gui）。
3. **`run.py`**：`from app.ui.main_window import main`（exe 打包入口）。
4. **`scripts/start_gui.ps1`**：`pythonw -m app.ui.main_window`（后台起原生窗口）；Write-Host 文案改为「CineSort 原生窗口已启动，关闭窗口即退出。」（删"浏览器自动打开/托盘结束进程"语义）。
5. **`scripts/start_debug.ps1`**：`python -m app.ui.main_window @args`（前台带控制台，便于看 stderr/traceback）。
6. **`tests/test_state.py`**：`from app.server import AppState as S2` 的 re-export 同一性断言删除（server 已不存在），其余断言保留；文件 docstring 如提 HTTP 同步措辞。用例数不减（2 例仍在）。
7. **`app/ui/theme.py:10` 附近注释**：提及 static/index.html 的措辞改为「原生 QSS，无 HTML」或直接删该行残留（只动注释）。
8. **`CineSort.spec`**：`datas` 移除 `('app/static', 'app/static')` 项（runtime/ 等其他项保留）。
9. **`JellyfinNFOSorter.spec`**：**整文件删除**（更名前残留，CineSort.spec 是唯一正主；其 datas 同样含 static，已无存在意义）。
10. **`tools/build_exe.ps1`**：`--add-data "app\static;app\static"` 参数移除。
11. **`README.md`**：三处——`:35` 附近 `python -m app.main_gui --port 8790 --no-browser` 启动方式改为 `python -m app`（或 `python -m app.ui.main_window`）；`:91` 附近 main_gui.py 入口描述改为 `app/ui/main_window.py`（PySide6 原生窗口）；`:93` 附近"static/index.html 单页 GUI"描述改为 PySide6 界面。顺带把过时的"零第三方依赖"表述改为「运行时仅 PySide6 一项第三方依赖」（若 README 有此表述，D-20261102-01 已拍板措辞）。
12. **新增测试 `tests/test_entry.py`**（3 例，零 Qt 实例化不需要 qapp）：
    - `test_entry_has_no_http_references`：读 `run.py`、`app/__main__.py`、`app/ui/main_window.py` 源码文本，断言均不含 `main_gui`、`app.server`、`create_server`、`serve_forever`、`static/index.html`。
    - `test_acquire_lock_excludes_second_instance`：`tmp_path` 下 `_acquire_lock(tmp_path)` 首次 True、同目录二次调用 False；不同 `tmp_path2` 再 True（锁按目录隔离）。
    - `test_deleted_files_gone`：断言 `app/server.py`、`app/main_gui.py`、`app/static/index.html`、`tests/test_api.py`、`JellyfinNFOSorter.spec` 均不存在（`Path(...).exists() is False`，防回归复活）。

### 明确不改
- `docs/decision-log.md` 与 card-c1/c2/c3/c4/c5 历史文档中对网页版的记载（历史记录不动）；`installer/installer.iss`（只引用 dist\CineSort.exe，无直接引用）；`app/core/**` 一律不碰。

## 三、验收命令（以下命令均在项目根目录执行；Python 用 `py -3.12`）

```bash
py -3.12 -m ruff check app/ui/main_window.py app/__main__.py run.py tests/test_entry.py tests/test_state.py
py -3.12 -m pytest tests/test_entry.py tests/test_state.py tests/test_flow.py -q   # 定向：入口/锁/全链路
py -3.12 -m pytest tests -q                                                        # 全量 = 165 passed 零失败（净口径：改前 167 − 5[test_api，D-20261102-02 预批删除，由 test_flow 1:1 承接] + 3[test_entry 新增] = 165；test_state 2 例保持已含在 167 内）
py -3.12 -m app --demo --rows 200 --screenshot Temp/entry-smoke.png --width 1280 --height 800   # 经 __main__ 新入口启动冒烟
py -3.12 -c "import ast,sys; [ast.parse(open(f,encoding='utf-8').read(),f) for f in ['scripts/start_gui.ps1']] " 2>/dev/null || pwsh -NoProfile -Command "[void][System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path scripts/start_gui.ps1).Path, [ref]$null, [ref]$null); 'ps1-parse-ok'"
pwsh -NoProfile -Command "& { \$p = Start-Process pwsh -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/start_gui.ps1' -PassThru; Start-Sleep -Seconds 6; if (Get-Process pythonw -ErrorAction SilentlyContinue) { 'GUI-LAUNCHED' } else { 'GUI-NOT-DETECTED' }; Stop-Process -Name pythonw -Force -ErrorAction SilentlyContinue; Stop-Process -Id \$p.Id -Force -ErrorAction SilentlyContinue }"
```

- 全量口径：删除 test_api.py（-5）后，`tests/test_flow.py` 6 例必须全绿（承接证据）；验收下限 **≥165**（净口径 +3 相对 162 的非 API 基线，只增不减）。
- GUI-LAUNCHED 必须出现（.cmd 同链冒烟）；该步会短暂启动真实窗口并关闭。

## 四、约束

- 只 commit 不 push；提交信息 Conventional 前缀 + 中文描述，正文 `verify:` 写 ruff 0 项 + pytest 全量数（167 → N，注明 -5/+3 口径）+ GUI-LAUNCHED + 截图路径，注明「GUI 已验证：真实启动冒烟 + 截图」；`Refs: D-20261102-01, D-20261102-02`。
- 显式 `git add`：删除用 `git rm app/server.py app/main_gui.py app/static/index.html tests/test_api.py JellyfinNFOSorter.spec`，新增/修改逐个 `git add app/ui/main_window.py app/__main__.py run.py scripts/start_gui.ps1 scripts/start_debug.ps1 tests/test_entry.py tests/test_state.py app/ui/theme.py CineSort.spec tools/build_exe.ps1 README.md docs/design/card-c6-native-launch.md`；永不 `git add -A`；永不 `--no-verify`。
- `app/core/**` 不碰；历史文档（decision-log、card-c1~c5）不改；锁迁移必须保留原语义（非阻塞、句柄持存、失败退出码 1、demo 不抢锁）。
- 卡外问题即停回报。执行中读取大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 pointerize/read_pointer/read_diff_only，禁止整读全文。

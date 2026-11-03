# C7 — 发版链迁移：PySide6 onedir 安装版 + v0.5.0（D-20261102-01 拍板形态）

## 一、背景与根因

GUI 阶段已收口（origin/main = af38a42），但发版链仍是 stdlib onefile 老链：release.yml 只 `pip install pyinstaller`（**无 PySide6**，exe 起不来）、`--add-data "app\static;app\static"` 引用**已删除**的目录（CI 必红）、onefile 形态违背 D-20261102-01（只保留安装版 onedir + Inno Setup）。远程无任何 tag，从未发过版。本卡把链迁齐并出 v0.5.0。

**解释器探测第 3 例**：build_exe.ps1 现用裸 `python`（PATH 首个可能无 PySide6，与 start_gui.ps1 陷阱同源）。按"第 3 例固化"惯例，抽共享探测脚本 `scripts/_pyside_probe.ps1`，三处（start_gui/start_debug/build_exe）dot-source 复用。

## 二、改动清单（只允许动这些）

1. **`scripts/_pyside_probe.ps1`（新建）**：定义函数 `Select-PySide6Interpreter`，返回 `$null` 或 `@($exe, $ver)`（`$ver` 为 `''` 表示裸 python）；探测逻辑与候选顺序（`py -3.12` 优先、再 `python`）从 start_gui.ps1 原样抽出。
2. **`scripts/start_gui.ps1` / `scripts/start_debug.ps1`**：删除内联探测，改为 `. (Join-Path $PSScriptRoot '_pyside_probe.ps1')` + `$chosen = Select-PySide6Interpreter`，其余行为逐字不变（start_gui 的 pythonw 窗口化、start_debug 的前台透传 @args）。
3. **`tools/build_exe.ps1`**：dot-source 探测选定解释器；PyInstaller 参数 `--onedir --windowed --name CineSort --add-data "config.example.toml;." run.py`（**删** `--onefile` 与 app\static add-data）；完成文案改 `dist\CineSort\CineSort.exe`。用选定解释器跑 `& $exe $ver -m PyInstaller ...`。
4. **`tools/build_installer.ps1`**：存在性检查改 `dist\CineSort\CineSort.exe`；便携版提示文案同步（无 ISCC 时提示云端 CI 构建）。
5. **`installer/installer.iss`**：`[Files]` 首条改 `Source: "..\dist\CineSort\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createSubdiris`（onedir 全目录）；config.example.toml 与 README.md 两条保留；`#define version "0.4.0"` 兜底改 `"0.5.0"`；头注释 onefile 措辞改 onedir。
6. **`.github/workflows/release.yml`**（先读全文再改）：`pip install pyinstaller PySide6==6.12.0`；PyInstaller 步骤改 onedir（同 build_exe.ps1 参数，经 `python -m PyInstaller`）；"校验安装包非空壳"及后续产物路径若引用 dist\CineSort.exe 一并改 onedir 路径（`dist\CineSort\CineSort.exe`，体积断言可提到 >40MB——Qt 体量）；其余步骤（ISCC、SHA256SUMS、上传、发布）路径核对后按需微调。
7. **`app/__init__.py`**：`__version__ = "0.5.0"`。
8. **`README.md`**：若正文有 onefile/便携版残留措辞，改为 onedir 安装版（grep 核对）；版本号字样若有提及同步 0.5.0。

## 三、验收命令（以下命令均在项目根目录执行；Python 用 `py -3.12`）

```bash
pwsh -NoProfile -Command "foreach ($f in 'scripts/start_gui.ps1','scripts/start_debug.ps1','tools/build_exe.ps1','tools/build_installer.ps1') { $e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $f).Path, [ref]$null, [ref]$e); if ($e) { "$f PARSE-FAIL" } else { "$f parse-ok" } }"
py -3.12 -m ruff check app/__init__.py
tools\build_exe.ps1                                   # pwsh 实跑，产出 dist\CineSort\CineSort.exe
dist\CineSort\CineSort.exe --demo --rows 100 --screenshot Temp/exe-smoke.png --width 1280 --height 800   # exe 真实冒烟（工作目录=仓库根）
tools\build_installer.ps1                             # 本机有 ISCC 则出安装包；无则以提示文案退出码 1（属预期，记录即可）
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/start_gui.ps1; Start-Sleep 6; if (Get-Process pythonw -ErrorAction SilentlyContinue) { 'GUI-LAUNCHED' } else { 'GUI-NOT-DETECTED' }; Stop-Process -Name pythonw -Force -ErrorAction SilentlyContinue   # 重构后垫片回归
py -3.12 -m pytest tests -q                           # 全量 165 passed 零失败（版本号断言若有须同步）
```

- exe-smoke.png 必须落盘且目验（demo 计划页渲染）；GUI-LAUNCHED 必须出现。
- exe 体积记录进执行报告（PySide6 onedir 预期 80~200MB）。
- 本机无 Inno Setup 时 build_installer 以提示退出属预期（CI 云端补位），不装新软件。

## 四、约束

- 只 commit 不 push（**含打标签也不做**——tag 由规划员验收后统一打）；提交信息 Conventional 前缀 + 中文描述，正文 `verify:` 写 parse-ok×4 / exe 冒烟截图 / GUI-LAUNCHED / pytest 165 / exe 体积，`Refs: D-20261102-01`。
- 显式 `git add scripts/_pyside_probe.ps1 scripts/start_gui.ps1 scripts/start_debug.ps1 tools/build_exe.ps1 tools/build_installer.ps1 installer/installer.iss .github/workflows/release.yml app/__init__.py README.md docs/design/card-c7-release-chain.md`；永不 `git add -A`；永不 `--no-verify`。
- dist/、installer/Output/ 为构建产物（gitignore），不入库。
- release.yml 其余步骤（SHA256SUMS/上传/release 发布）只在路径失效时最小修改，不得重构流程。
- 卡外问题即停回报。读取大于 4KB 的文件用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 read_pointer，禁止整读全文。

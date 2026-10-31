# 决策记录 — Jellyfin NFO 影片归类器

## D-20261031-01 交互形态：本地 Web GUI（替代 CLI）
- 背景：初版推荐 CLI，用户明确要求 GUI、不考虑纯命令行。
- 决策：Python 标准库 `http.server` + 单页前端，仅绑定 127.0.0.1，双击 bat 启动并自动打开浏览器；保持零第三方运行依赖。
- 备选驳回：tkinter（表格/交互能力弱）、PySide6（重依赖）。Web GUI 兼顾零依赖、可黑盒测试（web-gui-tester）与交付质量。

## D-20261031-02 摘要预判：三级决策链 + smart 策略
- 背景：用户要求利用 NFO `<plot>` 摘要对多题材/未映射题材做预判。
- 决策：决策链 = ①题材优先级表 → ②plot 关键词评分（可解释证据：命中词×次数×权重，阈值 min_score）→ ③兜底库。
  策略可配：`smart`（多题材命中多个候选库时用摘要评分择优，评分不足回退优先级表）/ `priority`（严格按优先级表，摘要仅用于题材完全未映射时）/ `genre_only`（不用摘要）。
- 驳回备选：ML 分类器（需训练数据与第三方依赖、不可解释）；LLM API（隐私 + 外部依赖）。

## D-20261031-03 [HIGH_RISK_OBJECTION] HR-1 处置：采纳（C5 部分采纳）
- HR-1 子项1（跨盘移动非原子 + 无校验 + skip 组合会产生静默不完整）：**采纳**。落为构建需求：
  - C2：库外 staging 暂存 → 文件数/逐文件字节校验 → 同卷原子 rename → 才删源；中断留 `.incomplete-*` 标记，绝不按 skip 放过。
  - C3：apply 只消费冻结 plan.json（含配置哈希 + 每单元文件快照），配置或源漂移即拒绝。
  - C6：磁盘空间预检（留 10% 余量，不足即阻断）；每会话独立 JSONL 日志 + fsync；undo 双步确认。
  - C7：冲突三分 —— 同名异片（skip+报告）/ 已在位（同 provider id，判源冗余不移动）/ 半成品残留（阻断）。
- HR-1 子项2（"移动后观看状态可保留"为未验证假设）：**采纳降级**。文档不再断言观看状态可保留，改为风险提示 + canary 流程（先勾选 1~2 部执行并人工核对观看状态与条目数）。C5 工具侧闭环：preflight 检测 Jellyfin 进程 → apply 前置阻断门（可显式确认越过）+ README runbook（停服务→执行→启动→全库扫描→条目数比对）。用户侧真实 canary 因无法访问用户实时环境，由用户执行，记为遗留项。
- C1（nfo.py 独立 + ≥12 变体 fixture 单测）、C4（库根必须预先存在/两两互异/与源根不重叠）：直接落为构建需求。

## D-20261031-04 冲突与特殊结构的默认安全策略
- 同名异片：默认 skip + 冲突报告；`rename` 仅显式开启且要求 NFO 带 provider id。
- 已在位（同 provider id 已在目标库）：不移动，报告"源冗余"提示人工清理。
- 半成品残留（含 `.incomplete-*` 标记）：阻断，不按 skip 放过，需人工清理（GUI 提供清理按钮）。
- 多版本（同 provider id 多个目录）：默认不选入批量执行，需人工确认。
- 复合目录（一个目录多部影片）：整目录排除并报告。
- HTML 独立报告：延后不做（GUI 即报告界面）——采纳评议意见。
- junction / 复制方案：维持驳回（用户目标为唯一归类）。

## D-20261031-05 文件移动语义与散装文件
- 全程不使用 `shutil.move` 目录语义（规避"搬进已存在目录内部"的经典坑）；同卷一律 `os.rename` 原子改名。
- 散装视频文件：归位时包一层 `<文件名>/` 文件夹再整体迁移（统一冲突/日志/回滚语义）；回滚按快照逐文件还原。

## D-20261101-01 已刮削文件夹整目录迁移（用户反馈加固）
- 现状确认：目录型影片单元本就整目录迁移（快照覆盖全部文件：NFO/海报/字幕/extras/子目录）。
- 修复四个误伤边界：① 散落花絮/预告视频（`- Behind The Scenes` / `- Trailer 2` 等，尾部锚定正则 RE_SUPPLEMENT）不再把已刮削文件夹误判为复合目录；② 『片名 - Extras』等包含式子目录不参与正片识别但随整目录迁移；③ 源根散落的 `trailer.mkv`/`sample.mp4` 不再成为影片单元；④ 正片名含 Shorts/Scenes 等词形时回退保护（无正片才回退为单元）。
- GUI 行内新增「文件数 · 体积」展示；提示文案注明整目录迁移语义。
- 回归测试 +5（基线 73→82）；GUI 复验 + 整目录迁移/回滚磁盘实证通过。

## D-20261101-02 exe 分发形态（用户拍板：参考 subtrans 独立可执行形式）
- PyInstaller `--onefile --windowed` → `dist/JellyfinNFOSorter.exe`（约 9.5 MB，双击即用，自动开浏览器）；入口为根目录 `run.py`（规避相对导入在冻结态失效）。
- 冻结路径（app/paths.py）：只读资源走 `_MEIPASS`（app/static、config.example.toml）；配置默认放 exe 旁（便携），目录不可写（如装进 Program Files）自动回退 `%APPDATA%\JellyfinNFOSorter`。
- 安装向导：`installer/installer.iss` + `tools/build_installer.bat`（Inno Setup 6）。本机未装 Inno Setup，未擅自安装第三方软件；用户安装后一键打包。
- 备选驳回：PyQt 原生窗口改写（成本高、浏览器 GUI 已验收）；onedir+zip（分发不如单文件直观）。
- exe 冒烟：v0.2.0 冻结态 API/静态页/扫描/便携配置生成/整目录迁移全部通过。

## D-20261101-03 自学习层（用户需求：多影片同类标签的历史归类自动外推）
- 决策：执行完成后按结果沉淀「题材 → 库」映射到 `runtime/learned.json`——人工改判记 2 票（强信号）、确认规则/预判结果记 1 票；同一题材票数 ≥ `learning.min_votes`（默认 2，可配可关）后按「自学习」级自动生效（默认勾选、置信 medium），未达阈值作低置信建议。
- 决策层级：显式规则（优先级表/别名表）> 自学习（达阈值）> 摘要预判 > 自学习建议 > 兜底；未列入优先级表的库之间以历史票数破平手（显式优先级永远赢过自学习）。
- 安全边界：兜底库不参与学习（防短路规则与预判）；学习数据跟配置位置走、不进用户手写 config.toml；GUI 配置页提供映射清单（题材/库/票数/人工次数）与逐条「忘记」。
- 顺带修复 v0.1 潜伏的证据文案 bug（rule_pick 中 map_genres 返回列表被直接插值，evidence 显示 `['武侠']`）。
- 回归测试 +9（基线 82→91）；端到端实证：兜底 → 人工改判沉淀 2 票 → 重扫自动命中「自学习」；GUI 截图验收（徽章/筛选/清单/忘记）通过；v0.3.0 exe 重构冒烟通过。

## D-20261101-04 打包链与 SubTrans 对照（code-reader 调研 D:\SubTrans）
- 调研结论：SubTrans = PyInstaller 6.x onedir（`packaging/SubTrans.spec`，SubTrans.exe + subtrans-cli.exe）→ Inno Setup 6（`packaging/setup.iss`）→ `SubTrans-setup-<版本>.exe`；CI（release.yml）用 `choco install innosetup` 在云端构建机装 ISCC 后 `/Dversion` 注入版本。
- 结论：我们的链（PyInstaller → Inno Setup 6）与 SubTrans 同构；"本机装 Inno Setup"的原因 = ISCC.exe 是安装包编译器（非 Python 库，pip 不可装），SubTrans 本机不用装是因其把编译放云端。
- 对齐改进：installer.iss 改为 `#ifndef version` + ISCC `/Dversion` 注入（build_installer.bat 自动从 app/__init__.py 读版本）。
- 差异保留：本项目以 onefile 便携 exe 为主产物（纯 stdlib 启动快、单文件分发直观）；SubTrans 用 onedir（WebView2/pythonnet 启动考虑）。Setup.exe 产出三路径：本机装 Inno Setup（官网/winget JRSoftware.InnoSetup/choco）→ 跑 build_installer.bat；或仿 SubTrans 建 CI 云端构建（需 git 仓库）。

## D-20261101-05 项目更名 CineSort + 复刻 SubTrans 云端发布流水线（用户拍板）
- 命名：用户否决 Jelly 前缀（"太特定项目化"）；通用化三轮后定为 **CineSort**（Cine+Sort，SubTrans 同款构词法）。GitHub 查重：19 个同名仓库全部 0 星个人项目，无占坑。
- 更名范围：GUI 标题/日志/弹窗、argparse prog、exe 与安装包产物名（CineSort.exe / CineSort-setup-<ver>.exe）、Inno AppName/组名/目录（{autopf}\CineSort）、APPDATA 回退目录（%APPDATA%\CineSort）、README；版本升 0.4.0。
- 云端 CI：`.github/workflows/release.yml` 复刻 SubTrans release.yml——workflow_dispatch(填版本) + `v*` 标签双触发 → setup-python 3.12 + pip pyinstaller → onefile 打包 → `choco install innosetup` → `ISCC /Dversion` 编译 → 空壳校验（>2MB）→ SHA256SUMS.txt → artifact 上传 → 标签触发 softprops/action-gh-release 发布。
- git：本机 init（main 分支）、显式暂存 41 文件（永不 git add -A）；提交署名留待用户设定（不伪造作者身份），提交+推送命令打包交用户执行。
- 验证：pytest 91 passed（含更名后页面标题断言）；CineSort.exe 本地冒烟（v0.4.0/自学习数据/页面标题）通过。

## D-20261101-06 本地脚本环境转 PowerShell 7（用户要求，弃用 bash/cmd 逻辑）
- 决策：所有本地脚本逻辑统一 PowerShell 7（pwsh，本机 7.6.9），`.ps1` 为唯一逻辑载体；根目录 `.cmd` 仅作双击垫片（`pwsh -NoProfile -ExecutionPolicy Bypass -File …`，因 ps1 双击默认进编辑器）。
- 替换：启动媒体分类工具.bat/启动调试控制台.bat → .cmd 垫片 + `scripts\start_gui.ps1`/`start_debug.ps1`；tools\build_exe.bat/build_installer.bat → `tools\build_exe.ps1`/`build_installer.ps1`（版本号 Select-String 解析；ISCC 探测含 ProgramFiles(x86)，StrictMode 安全）。
- CI 同步：release.yml 全部步骤 `shell: pwsh`（defaults.run.shell），版本解析/空壳校验/SHA256SUMS 均改 pwsh 实现（Get-FileHash/Get-Item），git-bash 依赖清零。
- 验证：4 个 .ps1 解析器 0 语法错；build_exe.ps1 实跑产出 dist\CineSort.exe；start_debug.ps1 冒烟（8796 端口响应）；pytest 91 passed。
- 教训：项目迁 D:\CineSort 后，曾有一次写文件仍落旧 G 盘路径（已归位并清残）；跨驱器迁移后所有写操作必须先核对目标根。

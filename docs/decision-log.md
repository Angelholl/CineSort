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

## D-20261102-01 交互形态再审：PySide6 原生桌面 GUI（supersedes D-20261031-01）
- 背景：用户明确要求"项目做成 GUI 形式，不要这种网页版本"。属需求变更，非 D-20261031-01 当时判断失误（当时约束是"要 GUI、零第三方依赖"，未提原生窗口）。
- 用户拍板三项（AskUserQuestion 明确选择）：① 技术栈 = PySide6（Qt），已被告知体积/启动代价后仍选；② 现有网页版（server.py + static/index.html）= 彻底删除；③ 分发 = 只保留安装版（onedir + Inno Setup），不再出便携 onefile。
- 决策：主界面改为 PySide6 进程内原生窗口，不再有 HTTP 服务与端口；core 十模块原样复用，仅 jobs.py 做薄适配；分发链改 PyInstaller onedir → Inno Setup。
- [HIGH_RISK_OBJECTION]（decision-critic）处置：**部分采纳、部分驳回**。
  - 异议内容：反对删除 `app/server.py` / `app/static/index.html` / 重写 `tests/test_api.py`——这是唯一"扫描→执行→回滚"磁盘级全链路集成证据与唯一回退路径，不可逆。
  - **采纳其实质关切**：删除 HTTP 层之前，先把 `test_api.py` 的 5 个用例（含 `test_scan_apply_undo_flow`）迁移为不依赖 HTTP 的 core 级集成测试（直接驱动 AppState + JobManager），测试基线只增不减（91 → ≥96）。全链路磁盘证据不消失。
  - **驳回"保留一个版本周期"**：用户已明确拍板彻底删除；且评议员自己列的 R8（双 UI 维护负担）正是保留的代价。迁移后集成覆盖等价，保留 stdlib HTTP 层 + 610 行 HTML 只留维护债。
- 驳回 decision-critic 的"选 tkinter 不选 Qt"建议：技术栈由用户拍板（不可委托项）。评议员对 A 的两项最重指控——onefile 解包 Qt 插件的静默失败模式、1.5~4 s 启动——已被用户"只保留安装版/onedir"的决定消解（onedir 下 Qt 启动为原生级）。"零第三方依赖"原则的失效由用户显式接受。评议员实测 ttk.Treeview 2 万行 0.12 s 成立，但 Qt 的单元格内控件/主题/DPI 一致性是本项目长期方向。
- **采纳并列为硬性施工纪律**（写进各施工卡）：
  1. `preflight.run_preflight()` 必须离开 UI 线程（内部 `tasklist` subprocess 最长 15 s + `disk_usage` + staging 目录遍历，同步调用即白屏）。
  2. 任务运行中关闭窗口必须显式确认（`closeEvent` 拦截），避免迁移中断留 `.incomplete-*`。
  3. 快慢双 tick：快 tick（约 300 ms）只读 `job.snapshot()`；`state_snapshot()`（读 journals 目录 + learned.json）放慢 tick（约 2 s）。
  4. `AppState` 从 `server.py` 抽到 `app/state.py`（UI 层不得依赖 HTTP 模块）。
  5. DPI 感知前置（`SetProcessDpiAwarenessContext` + Qt 高 DPI），150% 缩放下不裁字不重叠列为验收项。
  6. **Phase-0 样式门禁**：先只做计划页 + 假数据样机，出 100%/150% 截图交用户签字，签字后才展开其余三页。不接受"先做完全部再调样式"。
- [MATERIAL_CONFLICT] 裁定：`app/paths.py:40` 的 APPDATA 回退目录名以 **`CineSort`** 为准（D-20261101-05 与 installer.iss 注释为意图，代码属漏改）。改安装版分发后 Program Files 不可写 → APPDATA 回退从边缘情况变为主路径，必须修，并加旧 `%APPDATA%\JellyfinNFOSorter` 只读迁移兜底 + 回归测试。
- 验收协议变更（**待 owner 批准**，规则变更不可委托）：项目规则"GUI 变更提交前 web-gui-tester 黑盒验证"对 Qt 桌面窗口物理不适用（那是浏览器自动化）。替代协议：① view-model 单测（`app/ui/viewmodel.py` 零 Qt 导入）+ widget 级驱动测试（`QT_QPA_PLATFORM=offscreen` + `QTest`，不引入 pytest-qt）② 冻结 exe 真实启动冒烟 ③ 100%/150% DPI 截图存档（延续 `gui-test-screenshots/` 惯例）④ 5000 行计划规模冒烟。
- 连带失效：D-20261101-01 / D-20261101-04 的"onefile 便携 exe 为主产物"结论被本条取代；README"零第三方依赖"价值主张改为"运行时仅 PySide6 一项"。文档漂移顺带修：README:104 "73 个用例" 实际 91。

## D-20261102-02 GUI 验收协议：对齐 SubTrans 范式（owner 批准"SubTrans 用的那套"）
- 背景：owner 就"web-gui-tester 不适用于原生窗口后换哪套协议"答复"SubTrans 用的哪套"。先调研 D:\SubTrans 实际做法（code-reader，只读），再据其映射。
- SubTrans 实测范式（证据）：GUI = pywebview + pythonnet(WebView2) 内嵌 HTML/JS。三层验收——① 后端 API 层单测不启窗口（`tests/test_gui_api.py` 375 例 + `test_gui_api_gaps.py` 53 例，`object.__new__` 绕开 `__init__` 副作用，`pytest.mark.gui` + `importorskip("webview")` 未装 extra 即 skip）；② 前端源码静态断言（`test_gui_js_static.py` 246 例 + `node --check`；`test_ui_phase3_redlines.py` 9 例 UI 红线静态钉）；③ 一次性黑盒台架（`Temp/gui-blackbox-*/`：HTTP 伺服生产 assets + `stub_bridge.js` 桩桥 + puppeteer-core 驱动本机 Edge headless 真实点击 + 只读 DOM 断言 + 截图，产物落 gitignore 的 Temp/ 不入库）。每卡验证链原文见 `docs/design/d1013-S6复议-布局表面卷.md:194`（file:// 走查 → computed-style 抽样 → 截图 diff 100%/125%/150% → 暗色专项 → 断点 → AA 复测 → web-gui-tester 黑盒）；未跑黑盒者提交信息按规注明「GUI 未验证」（同文件 :182）。CI：`ci.yml` ruff → mypy baseline gate → pytest（GUI 用例 skip）；`gui-probe.yml` 月级 schedule 探针（非 required）；`release.yml` 只做产物存在性/体积断言（安装器 ≥20MB 防空壳）+ CLI 无头语义冒烟，**GUI exe 明确不做 CI 冒烟**（:125-127 注释"GUI 真机验收归安装反馈轮"）。dev 依赖仅 pytest/pytest-cov/mypy/ruff，**无 pytest-qt/FlaUI/WinAppDriver/Playwright**。
- 映射到 CineSort（PySide6）后的协议，替换原"web-gui-tester 黑盒"条目：
  1. **逻辑层单测为主证据**：`app/ui/viewmodel.py` 零 Qt 导入，承载选择集/筛选/改判 overrides/ack 门禁/体积汇总/会话状态等全部决策，穷举单测不启动窗口（对应 SubTrans test_gui_api.py 范式；这是把逻辑推出 UI 层的核心可测试性前提）。
  2. **UI 源码静态断言 + 红线钉**：对 Qt UI 源码做静态断言（tab 齐备、按钮文案、`closeEvent` 有守卫、UI 线程无同步 preflight 调用等），对应 SubTrans `test_gui_js_static.py` / `test_ui_phase3_redlines.py`。
  3. **截图走查 100%/125%/150% DPI**：产物落 `Temp/`（gitignore），路径写进卡面执行记录存档，不入库（对齐 SubTrans，不再新增 `gui-test-screenshots/` 入库惯例；既有目录保留不动）。
  4. **不引入任何新的 dev/测试依赖**：widget 级驱动测试用 PySide6 自带 `QTest` + `QT_QPA_PLATFORM=offscreen`，零新增包（此项为超出 SubTrans 对等面的补充——Qt 免费提供该能力，SubTrans 的 HTML 面靠 puppeteer 才有黑盒，故补一条等价物）。
  5. **CI**：产物存在性/体积断言 + 无头冒烟；GUI exe 真机验收归人工安装轮，不做 CI 冒烟（windowed 子系统无 stdout 可断言）。
  6. 提交信息仍按规注明「GUI 已验证 / GUI 未验证」，未验证时完成通知追加同句。
- 静态检查环节补配：CineSort 此前无 linter（验证链第一环空转）。本机已有 ruff 0.16.7，全仓既有基线 42 项（不追溯清理）；自 D-20261102-01 起每卡验证链第一环 = `python -m ruff check <本卡改动文件>`，**改动文件必须 0 项**，全仓基线只降不增。
- 测试基线口径澄清：C1 后基线 93。C2 移植 `test_api.py` 4 个非页面用例 + 新增 1 条 BusyError 用例 → 98。后续删除网页版卡移除 `test_api.py`（5 例）→ 93，**净覆盖相对迁移前基线不降**（删除的 5 例已 1:1 由 test_flow.py 承接，页面用例由 Qt 窗口标题断言承接）。"只增不减"按此净口径执行并在提交信息 verify: 中写明前后数。

## D-20261104-01 GUI 阶段收口：四页全齐 + 网页版删除（owner 拍板"完整桌面成品"档）
- 阶段收口定义（owner AskUserQuestion 拍板）：③ 配置页 + ④ 体检页补齐 → 启动链切换原生窗口 → 彻底删网页版；安装包（onedir + Inno Setup）不在本阶段。
- 流水：C3 执行/回滚页（eefff2d+a9f3928，tests +11）→ C4 配置页（bac3be7+95b55c5，+14）→ C5 体检页（5408302+2065162，+11）→ C6 启动链+删网页版（f70a6dd+c1ae440，+3/−5）；全程 opencode 免费模型配额耗尽僵死，改派 ZCode code-Executor 执行者通道。
- 门禁白名单拍板（规划员）：`BlockConfirmDialog.NON_ACKABLE` 扩为 {paths_missing, disk_space, staging_leftover}（可勾越过仅 jellyfin_running/fallback_ratio，与网页版白名单一致，core run_apply 只看 code not in acks 故 UI 收紧即生效）；staging_leftover 文案引导至④页清理。
- C6 基线净口径裁决：卡面 ≥167/≥168 系算术错误，正确净口径 165 = 167 − 5（test_api，D-20261102-02 预批删除、test_flow 1:1 承接）+ 3（test_entry）；test_state 2 例保持。净口径相对 162 的非 API 基线 +3。
- 启动垫片陷阱（C6 执行者发现、规划员验收修正）：PATH 首个 pythonw 落在无 PySide6 的 conda 环境（J:\whisperjav 3.13），双击 .cmd 静默失败；start_gui/start_debug.ps1 改为逐候选真实 import 探测（py -3.12 优先），窗口化取所选解释器同目录 pythonw.exe；.cmd 同链真启动 GUI-LAUNCHED 实证。
- 单实例锁 `_acquire_lock` 自 main_gui.py 迁入 app/ui/main_window.py（非阻塞/句柄持存/失败弹窗退出码 1/demo 不抢锁），test_entry 钉语义。
- 删除面：app/server.py、app/main_gui.py、app/static/index.html、tests/test_api.py、JellyfinNFOSorter.spec（后者 *.spec 被 .gitignore 忽略从未跟踪，磁盘 rm；CineSort.spec 同属 ignore 磁盘维护 datas，不入库——spec 文件版本控制缺失为既有事实）。
- 全量测试基线：131（C2 后）→ 165（C6 后）。GUI 已验证：offscreen 截图（100%/150%）+ 视图逻辑单测 + .cmd 同链真启动冒烟。
- 遗留延后项：QTableWidget 样板三处重复（UI 打磨卡）；会话表 2s 全量重渲选中态保持；③ 页配置横幅/④ 页空态提示等小瑕疵已验收期修；安装包链（onedir + Inno Setup + CI）未启动。

## D-20261104-02 v0.5.0 发版：链路迁移与三轮 CI 排障（owner 令"push发版"）
- 发版链迁移（C7 卡，b40bca7）：onefile stdlib 老链（引用已删除的 app\static，CI 必红）→ PySide6==6.12.0 + onedir + ISCC 安装版；解释器探测第 3 例固化 scripts/_pyside_probe.ps1（start_gui/start_debug/build_exe 共用）；版本 0.4.0→0.5.0。
- Run#2 失败：空壳校验 40MB 阈值系未实测拍脑袋——本地 lzma2（xz preset6）实证 122MB onedir 压缩后仅 33.3MB。修正为分层断言：安装包 ≥20MB（10 倍余量）+ 启动器 ≥1.5MB + onedir ≥80MB（与压缩率解耦）。**教训：断言阈值必须先本地实证再写进卡面。**
- Run#3 失败：打包/校验/SHA256/上传全过，发布 Release 403——新仓库 GITHUB_TOKEN 默认只读，工作流缺 permissions 块。补 `permissions: contents: write`。
- Run#4 success：Release v0.5.0 发布 CineSort-setup-0.5.0.exe（33.7MB）+ SHA256SUMS.txt。
- 远程 tag 重打流程：删远程 tag → 修 yml → 同名 tag 重推触发新 run（无发布产物的失败 tag 可安全重打）。
- gh CLI 本机不可用：CI 状态经 GitHub 公共 API（actions/runs、jobs、releases/latest）步骤级定位，无需认证。

## D-20261106-01 应用图标定稿：A「入架」二元色（owner 拍板，B 方案备选落选）
- 抉择过程：A「入架」/ B「分流」双方案展示页比选 → owner 先定二元色纪律（弃多色书脊/徽章色族：书色统一深灰偏黑墨色，仅两色构图），再定底色逐版提亮（#F2EEE6 → #F2F4F8 → #F8FAFC），最终选 A 配图。
- 定稿规范：墨色 #2C2F36 + 浅底 #F8FAFC 圆角方块（r56@256）；构图=双层书架 + 主角书 -18° 斜插顶格（书脊三齿孔）+ 层板 + 底排三册 + 单根动势弧线；母版 assets/icon/cinesort-icon-a.svg，小尺寸简化 glyph cinesort-icon-a-small.svg（32/16 档专用：去动势线与落书、加粗线条）。
- 产物链：tools/make_icon.py（cairosvg+Pillow，256/64/48 用主版、32/16 用简化版）→ cinesort.ico（5 档）；窗口图标 main_window.py main() 设 app.setWindowIcon（resource_root() 解析，源码=项目 assets / 冻结=_MEIPASS）；打包接入点为 tools/build_exe.ps1 --icon + --add-data（CineSort.spec 系 gitignore 陈旧产物，构建链不走它，review 发现后回退其改动）；installer.iss SetupIconFile 同源。
- code-review 两轴结论：无硬违规；采纳意见=删 B 方案遗留资产与全部 preview PNG（可由 make_icon 复现）、合并重复局部导入、ico 补 48 档、生成脚本入库保可追溯。驳回项=无。
- 验证：py_compile 过；demo 冒烟截图正常；全量 165 passed（基线不增不减）；GUI 未做黑盒全流程（图标仅资源级变更，窗口标题栏图标由 OS 绘制，截图链不含）。

## D-20261109-01 分类质量立项：配置层定稿 + 代码四特性（owner 拍板）
- 背景实测（源 `E:\已刮削\待整理`，用项目自身 scanner+classifier 跑 owner 实机配置 `D:\CineSort-beta\CineSort\config.toml`）：97 单元 rule 60.8% / fallback 39.2%，已越 `block_fallback_ratio=0.30`。根因不是算法：片源 NFO 是刮削器标签云（192 个不同词，繁简混排 + 技术标签），与 40 个自设库名只有 5 词同名；`genre_aliases={}` + `plot.enabled=false` → 兜底主因；`strategy=smart` 因库无 keywords 而空转（多候选恒回退优先级表）。
- 配置层定稿（已生效，原文件备份 `config.toml.bak-20261109-1756`）：56 条 alias（繁简双写）+ genre_priority 重排（具体题材在前、通用标签靠后）→ rule 97.9% / fallback 2.1% / 24 库命中。owner 定案：`3P/4P`→多飞、`多P/滥交/濫交`→乱交、`熟女`/`美熟女` 不归人妻、新增 `口交` 库、审计驱动补 `亂倫`族→义父。
- 撤回一项假设：撤掉 `出軌→寝取` 后 13 个真 NTR 单元（标题明写 寝取らせ/NTR，标签只有 出軌 无 寝取）错分到人妻/中出/痴女，寝取命中 15→2，覆盖率不变而精度下降 → 映射保留。**教训：精度审计必须逐例读标题，不能只看兜底率。**
- 精度审计（30 例按库分层抽样、人工核对标题与标签）：严格 22/30≈73%、宽松 26/30≈87%，低于 decision-critic 设定的"默认勾选需 ≥90%"门槛。错例成因三分：标签与标题语义冲突、线索只在标题里（标签无）、源标签本身错。
- decision-critic 评议 `[HIGH_RISK_OBJECTION]`（针对"复合目录自动拆分为独立单元"）：**处置=采纳**。立项不含自动拆分；复合目录以整目录为单位进计划视图，状态 `ST_BATCH`、默认不勾、不进现有 `fallback_ratio` 分子分母（新口径 `fb/(total−composite)`），避免 147 个无 NFO 单元把兜底率顶到 (2+147)/244≈61% 造成 preflight 常态阻断。
- 同轮评议另一结论采纳：摘要分析在本数据集是低杠杆（97 单元仅 50 个有日文 plot，且已被 alias 覆盖到 97.9%；147 个视频无 NFO 即无摘要可吃）→ 不做 40 套手工 keywords、不做 TF-IDF 自动关键词、不做外部 LLM；文本信号只以「标题弱评分」形态进入（low 置信、默认不选、独立阈值）。
- 15 个 NFO 解析失败根因定位：JavDB 写出 `<7mmtvid>`，元素名以数字开头违反 XML NameStartChar，`ET.fromstring` 报 not well-formed；regex 兜底已抓到全部 genres/title/plot（信息未丢，只多 15 条告警）。修法 `re.sub(r"<(/?)(\d[^\s>/]*)", r"<\1_\2", text)` 实测 15/15 恢复 XML 正常路径且逐字段与 regex 路径一致。附带发现：`<javdbid>` 未纳入 provider id（uniqueids 空）→ planner 的 same_id 去重对这些单元失效，立项特性 A 补齐。
- owner 两项取舍拍板：①复合目录即使翻出带题材 NFO 也强制 `ST_BATCH` 永不自动执行（多影片目录按单一 NFO 归库必错位）；②弱标签护栏不自动修对任何错例、只把可疑命中降为人工复核，初始弱标记集收窄为 `护士`/`看护妇・ナース` + `女同性戀`/`女同性恋`/`女同接吻`/`レズキス` 两族 6 条，`人妻` 族与职业族暂缓——实跑一轮看默认不勾的行数再扩集（扩集是纯配置改动，不动代码）。
- 产物：规格 `docs/design/2026-11-09-classification-quality.md`、计划 `docs/plans/2026-11-09-classification-quality.md`（13 任务、新增 70 测试）。测试基线本轮实测 `197 passed`（collect-only 亦 197，与规划员静态计数一致），收口目标 ≥267。
- 遗留：43 复合目录 / 147 视频按「逻辑归集 + 目录级批量改判」处理，不做物理搬移、不改目录名；GUI `dump_config_text` 把 genre_aliases 写成单行 inline table（往返不丢条目但丢注释）——本轮不动 dump 逻辑，如需保注释另开卡。
- **更正（2026-11-10，卡 C8 验收期主审探针）**：上述"147 视频"的前提描述有误。原结论"147 个视频全部无 NFO"来自我的探针只 `glob('*.nfo')` 查顶层目录，漏了嵌套层。递归实测真实结构为 `待整理\<女优或未知>\<番号>\{1 视频 + 1 NFO + 附件}`：43 个复合目录内含 **148 个内层影片目录，147 个各恰 1 个视频，其中 145 个自带 NFO**；复合目录根下直接躺的视频数 = 0。后果：①特性 D「只能靠文件名」的动机被削弱（145/148 有 NFO）；②C8 产出的 43 个整目录单元里 41 个被判 rule/high，依据只是目录内某一部影片的 NFO（实测 `#未知女优`→合集长篇、`伊藤舞雪`→按摩、`三澄寧々`→乱交），故卡 C9（ST_BATCH 门禁）作为安全网照做；③更对症的方案是「识别嵌套影片目录、把每个 `<番号>` 目录当独立单元」——它们本就是完整单片目录、自带 NFO、有题材标签，56 条 alias 可直接命中。该路径是否立项待 owner 拍板。教训：**对目录树做测量必须递归，顶层 glob 会系统性漏数**。

## D-20261110-01 嵌套影片目录与三层布局立项（owner 四项拍板）
- 结构事实补充：题材库根与源根**同构**——实测 `E:\已刮削\按摩\一乃あおい\JUR-439-C`、`E:\已刮削\按摩\#未知女优`、`E:\已刮削\合集长篇\JULIA`，即库内本就有女优层，影片住在第三层。卡 C9 真实计划数字里 22 个 `conflict_name` 中 **12 个是普通影片单元**，撞的是**女优层目录名**而非同一部影片，`on_conflict=skip` 把本可自动归位的片子卡住。
- **owner 拍板四项**：①**保留女优层**——目标路径组合为 `库\<女优>\<影片>`，不压平（与现有库内布局一致）；②**撞名语义改为合并**——目标存在同名女优目录时合并进去，不再判 `conflict_name`、不再 skip；③**先出规格与计划**（嵌套识别），现有计划的剩余四卡（Task-11 执行链放行 / Task-12 计划页 UI / Task-13 收口）**押后**，由新计划明确哪些被取代、哪些仍需做；④wrapper 限流签名补丁获授权。
- 工具变更（已执行并验证）：`~/.zcode/tools/exec_wrapper.py` 的 `RATE_LIMIT_SIG` 增 `r"Free usage limit reached"`。依据=卡 C6 实证该文案不匹配任何签名，致 exit 1 且 `rotations=[]`、链内轮转完全未触发。落盘后验证：真实错误文案 `match_any → True`；四条普通输出（截图行 / `219 passed` / `Found 10 errors.` / 裸 `1308` 文本）全部 `False`；`py_compile` 通过；签名数 5→6。假阳性残余与代价写进代码注释（锚定整句、一轮制有界）。按 config-write 纪律执行：TICKS 打点 → 写前 mtime+哈希快照 → 编辑 → 落盘重验 → 一体命令 `BACKUP-BASELINE-REFRESHED`（锚点 lines=91、六文件哈希在场、锁在场）。
- 暂停派卡的安全性核对：`jobs.py:147` `bad = [u["id"] for u in units if u["status"] != READY]` —— ST_BATCH 单元当前天然进不了执行链，停在 C9 不会造成误移动。
- 本轮已合入的 9 张卡（C1-C9，测试基线 197 → **259 passed**，全仓 ruff 15 → **10 项**）不被新方案作废：NFO 容错、`javdbid`→provider id、弱标签护栏、标题弱评分、复合单元与 ST_BATCH 门禁均保留，其中复合/ST_BATCH 降级为"真正混合目录"的兜底路径。

## D-20261112-01 项目目录迁移收尾（G/D 盘 → I:\CineSort，仓库卫生）
- 迁移事实：项目根现位于 `I:\CineSort`（历经 G: → D:\CineSort → I: 两次迁移）；代码层核验无任何硬编码旧盘符路径（`app/` 与 README 干净），无需代码改动。
- 仓库卫生：`.zcode/`（仅 config.json，autoresearch 插件开关，无敏感信息）、`.pytest_cache/`、`.ruff_cache/` 此前未入忽略清单，长期挂未跟踪 → 补入 `.gitignore`，本项目内按本地工件处理、不入库。
- 教训复用（承 D-20261101-04 line74）：跨驱器迁移后所有写操作先核对目标根——本轮起执行。
- 文档残留：decision-log 与历史计划中的 `D:\CineSort-beta\CineSort\config.toml` 实测路径为历史记录，不改写；如需复跑探针，以本机实际路径为准。
- 迁移范围外：老 Task-12（计划页 chips/批量改判对话框，`docs/plans/2026-11-10-nested-unit-layout.md` 遗留卡）为功能卡，不属迁移收尾，仍挂起待派。
- 迁移深查补录（同日，owner 令"从 D 盘迁移重查"）：全仓盘符清查结论——代码层/启动脚本/installer/CI 干净；残留全在不入库工件与演示数据。处置：①`demo/`（D 盘时代 config.toml + plan.json 6 处 D:\CineSort 路径）删除后经 `tools/make_demo_env.py` 重建，新产物全落 I:；②`build/`（PyInstaller 缓存满篇 D:\CineSort 与 G:\python site-packages）删除，重打包前须在 I: 重建；③`app/ui/demo_data.py` 演示假数据 D:\ 改 I:\（纯 UI 展示字符串，无测试断言盘符）；④`config.toml` 根配置 source_root/媒体库仍指 G:\Media——媒体是否仍在 G 盘属 owner 实机事实，未代改；⑤`dist/` 旧盘构建产物未删（含 config 副本），重发包时删后重建；⑥docs/ 卡面历史探针路径为叙事记录不改写，复跑时换本机路径。
- 深查验证：全量 323 passed（基线只增不减）；ruff 全仓 All checks passed（优于既有 10 项基线）。
- 旧盘清理终局（同日三轮，owner 令"旧盘清掉、I: 重建"）：①**实机配置扶正**——`D:\CineSort-beta\CineSort\config.toml`（D-20261109 精调版，56 条 alias，指向 `E:\已刮削\待整理`，E 盘目录实证存在）复制为根 `config.toml`；原根配置系指向已不存在的 `G:\Media\_incoming` 的死模板，备份为 `config.toml.bak-20261112`（.gitignore 补 `config.toml.bak-*`）；②**dist 在 I: 重建**——删旧盘 dist 后 `tools/build_exe.ps1`（须 pwsh 7，脚本 `#requires` 拒 5.1）重建成功，exe 冒烟启动实证（进程在场后 taskkill）；③**D 盘副本清除**——`D:\CineSort`（git 克隆，落后本地 2 提交、工作区干净、无独有内容，config 与 I: 逐字一致）与 `D:\CineSort-beta`（127M，实机配置已抢救后删）双双删除并复核不存在；`G:\zcode` 仅含 zcode-token-bar 与本项目无关，不动。至本地盘符清查闭环：活代码/配置/工件零 D 盘引用。

## D-20261112-02 beta 热修一：悬空库引用宽容降级（owner 拍板"宽容降级"）
- 根因：`config.example.toml` 自带 `'thriller'='惊悚'`、`'musical'='音乐'` 两对悬空别名（13 库无此二库），首跑原样拷成 config.toml 后 `load_config` 必炸；GUI 兜底把非法别名原样回填表单、报错横幅不指明问题在别名框 → 用户「添加/删除库都保存失败」的体验性死锁。
- 决策（owner 2026-11-12 会话四项拍板之一）：指向未定义库的 genre_priority / genre_aliases / weak_genre_aliases 条目不再报错，丢弃并收进 `Config.warnings`；重复库名仍报错；含悬空条目的表单保存必成功（写盘透明）；GUI 横幅三分支 error > 橙色警告 > 隐藏；example 同步清理两对悬空别名。
- 实现：卡 `card-20261112-lenient-aliases`（commit dd49893）；`config_hash` 不含被丢弃条目（计划页不误报漂移）。
- 测试：323→331（3 例原地改写语义不减量+5 例新增，含 example 自洽 tomllib 裸解析防复发钉）；ruff 0 项；offscreen 冒烟过。
- 执行注记：opencode free 链两轮全限流（CHAIN_EXHAUSED），按派卡纪律「所有轮转均限流→主审兜底亲执」由主模型亲执；卡面 dangling_hash 例存在设计缺陷（换根目录连路径哈希一起变），验收期就地修正为同根目录重写比对。

## D-20261112-03 beta 热修二：首跑自洽 + 全字段 tooltip + 图标缺失告警 + dist 重建交付
- 三缺陷：①首跑拷含 G:\ 死路径的 example 必触发「source_root 不存在」；②配置页 14 字段零 tooltip（README 有 100% 文档但 GUI 不展示）；③图标缺失静默降级（beta 实机包缺 `_internal/assets` 无任何提示）。
- 实现：卡 `card-20261112-firstrun-tooltips-icon`（commit ca2305c）——`ensure_first_run_config()` 生成可通过全量校验的最小配置+自动建 `data/{待整理,电影,未分类}`（跟 config.toml 走）；main() 接入 stdlib logging，图标缺失 `log.warning`；14 字段+库表 4 表头 tooltip 文案自 README 提炼。
- 测试：331→337（首跑自洽 3/入口接线 2/tooltip 1）；ruff 0 项；offscreen 冒烟过。
- 部署（主模型亲执）：dist 于 I: 重建；包内 example 无 thriller/musical 残留；内嵌图标抽验目验为设计图标；本机无 ISCC→按分支规则交付 onedir `dist\CineSort\`（exe SHA256 `420CEF5D…A7B9FB`）；dist 真首跑冒烟全过（config 自动生成、三目录就位、配置页零横幅）；dist 旧 G:\ 模板配置备份 `artifacts/dist-config-backup-20261112.toml`，按处置规则留档不恢复（其 source_root 指向不存在目录）。
- CI 待办（后续卡）：`.github/workflows/release.yml:39-43` 云端构建缺 `--icon` 与 `--add-data "assets/icon/cinesort.ico;assets/icon"`——云端产物必缺图标，此为 owner 实机 beta（2026-11-11 安装包）缺图标的真源；补齐前 beta 分发一律以本机重建的 dist 为准。
- owner 重装提醒：重装后桌面/任务栏若仍显旧图标，跑 `ie4uinit.exe -show` 或重启 explorer 刷图标缓存。

## D-20261112-04 v0.7.0 小版本发版：CI 图标收口 + beta 三问题热修上云（owner 令"github推送，版号为小版本更新"）
- 版本判定：热修含宽容降级（校验语义变更）、首跑自洽生成器、全字段 tooltip、图标告警——特性级改动，按次版本号 0.6.1→0.7.0；`app/__init__.py` 与 `installer.iss` 兜底默认值同步（iss 实际版本仍由 build 脚本/CI /Dversion 注入）。
- CI 待办收口（承 D-20261112-03）：`release.yml` PyInstaller 步骤补 `--icon "assets/icon/cinesort.ico"` 与 `--add-data "assets/icon/cinesort.ico;assets/icon"`（与本地 build_exe.ps1 逐字对齐），云端产物自此带设计图标。
- 发版实证：tag v0.7.0（aee67df）触发 Release 工作流 success（run 43222087781，继 v0.6.0/v0.6.1 后同链第三轮绿）；Release 已发布 [v0.7.0]：`CineSort-setup-0.7.0.exe` 35,321,056 bytes + `SHA256SUMS.txt`（0584832a3032ea4bf5878409ec61ea375f4ced588e41a080ec627e2d3791d28f）。
- 发版前本地验证：全量 337 passed；两笔提交 7c57667（ci）/ aee67df（release）。
- owner 安装建议：直接装云端 `CineSort-setup-0.7.0.exe`（内嵌+窗口图标均齐），替代手工拷贝 dist；装后旧图标残留刷缓存同前。
- 版本号调整补录（同日，owner 令"版号调整为 v0.6.X"）：0.7.0 判定被 owner 驳回，改 **0.6.2**（0.6.1→0.6.2 修订号递增）；v0.7.0 Release（id 442947892）经 API 删除（HTTP 204）+ 远端/本地 tag 双删；`app/__init__.py` 与 iss 兜底值改 0.6.2（1f40c1c）；tag v0.6.2 重建云端构建 success（run 43223861645），Release [v0.6.2] 已发布：`CineSort-setup-0.6.2.exe` 35,313,404 bytes，SHA256 `22708ae3…0c130d`。v0.7.0 安装包自发布至删除期间约十余分钟，若已有人下载以 v0.6.2 为准（两者代码内容仅版本号字符串之差）。

## D-20261113-01 无 NFO 内容预判方向：先测量后定（decision-critic 评议 + owner 拍板）
- 背景：owner 提出参考 GitHub rea-video（JuneYaooo，逐镜逆向复刻工具）的「逐镜拆回提示词」思路，叠加剧情自摘要，为无 NFO 影片做内容预判。主模型调研结论：逐镜粒度对「归类预判」任务过配，可借鉴的是证据分级/降级可用/外部脚本解耦三思想，不搬全量管线；CineSort 现状为零第三方依赖、无任何多媒体代码（code-reader 实证）。
- decision-critic 评议（反对原草案 Phase 0「字幕→plot 链」，主审逐条复核）：①40 库 keywords 全空（config.toml:24-259）→ plot 评分恒 0（classifier.py:92-101），「喂 plot 链」现配置产出为零——证实；②`[HIGH_RISK_OBJECTION]`「帧画面上云 + 预判进自动迁移」采纳：目标语料下云 VLM 内容政策拒绝属功能失效级风险（非单纯隐私偏好），四放行条件全采纳（先测量、云默认关+本地默认、输出带来源+置信+默认不勾选、50 部真值集 precision/弃权率达标才开自动勾选）；③`[INFO_GAP]` 采纳：番号/文件名→在线元数据查询（urllib 标准库，只发番号不送画面）为草案漏选项；④rea-video 修正为逐镜 **11 类**（docs/what-it-detects.md；主稿「三分类」与评议「五类」均不准），其 99% 属制作方式分类（帧率/噪点/AIGC 标识等硬证据），与剧情→库别无同构证据源，不得作准确率锚点（采纳）。
- 番号歧义四层消歧（owner 问询后补定，作为 Step B 前提设计）：①多源交叉验证（≥2 站点一致才自动采用）②辅助信号二次匹配（片长最有效，出演者/系列/CD 去重）③置信分级+歧义队列（低置信不写入，复用「默认不勾选+计划页人工确认」既有交互）④失败优雅降级（不猜，维持兜底）。残留风险如实披露：无番号素人片不覆盖；番号错配不能归零。
- 与既有决策的约束披露：D-20261109-01 已定「不做外部 LLM、不做手工 keywords」——Step B（在线查询）/Step C（本地 VLM）立项前须 owner 明示修订该条；且 D-20261110-01 更正实测 148 个内层影片 145 自带 NFO，真正无 NFO 残差规模存疑，须先实证。
- owner 拍板（AskUserQuestion 2026-11-13）：**先测量后定**——先跑零依赖测量脚本（含番号可提取率统计），数据出来后再议 Step B/C 是否立项；原 Phase 0「字幕→plot 链」降级为可选（需 owner 预置词表才有效果）。
- 产物：卡 `docs/design/card-20261113-measure-no-nfo.md`（tools/measure_no_nfo.py，双口径递归测量：production 单元视角 + 深查递归视角，递归铁律承 D-20261109-01 更正教训「顶层 glob 系统性漏数」；报告脱敏落 artifacts/ 不入库）。
- 隐私纪律：一切测量/预判输出不得含完整文件名/女优名/路径成分；云 VLM 默认关闭；预判结果如立项须标注来源与置信、默认不勾选。
- 测量结果补录（2026-11-13，卡 A1 `b22d926`，opencode 执行 + 主审验收链亲跑复核：ruff 改动文件 0 项且全仓 All checks passed / 定向 10 passed / 全量 **347 passed** / 冒烟复现 / JSON 键清单核对无文件名泄漏）：`待整理` 池当日快照实测 **production 单元 243 = 深查视频 243，无 NFO 残差 0**；伴随字幕 0（文本/位图皆无）；番号可提取 163/243（无分片需去重）。结论：D-20261110-01 更正成立，本库无 NFO 残差已清零，**Step B/C 对本库当前无立项对象**；四层消歧设计与 [HIGH_RISK_OBJECTION] 放行条件归档备用，未来出现新残差片源时再议。注意池为活水（整理进行中），数字仅代表 2026-11-13 快照。


## D-20261125-01 老 Task-12 批量改判 UI 补齐（owner 令"现在补齐，然后 push 发版"）
- 锚点重核结论：押后卡 Task-04/05（freshness/preflight/jobs 放行 ST_BATCH+override）已被 v0.6.1 的 `UNLOCKABLE_STATUSES=(ST_BATCH, ST_MULTI)` 白名单收敛（10cebda/fbb66fa）完整覆盖——planner:244、preflight:84/:123、jobs:149-153、viewmodel:115/230 五处门全部就位，无需重做；实际残留仅老 Task-12 的 UI 面。
- 拆两卡串行执行（同工作树 ≤1 卡）：`card-20261125-batch-badge.md`（T12a 徽章链）与 `card-20261125-batch-rejudge-ui.md`（T12b 批量改判：viewmodel `set_override_many` + 右键菜单「批量改判目标库…」作用于当前勾选集 + demo 复合行）。
- 通道偏差与 owner 扩令：T12a 系主审失误未跑 `dispatch_guard --check` 即默认派 ZCode Agent（该卡属 hy4 窗口白名单卡型「UI 静态文本微调」，应派 opencode）；卡在飞后按纪律不中断，跑完验收。T12b 派卡前经 owner AskUserQuestion 扩白名单（新交互功能卡暂入 opencode/hy4-flash-free，窗口期 2026-12-02 前有效），guard 通过、artifacts 台账已记、契约无 flags、逐行 diff 审通过。到期（2026-12-02 24:00）后本扩令自动作废，恢复白名单口径。
- T12a 验收：执行者 57ebb50 先红后绿；其卡外发现经主审复核属实——`status_badge` 直出原始状态码，`BADGE_COLORS["batch"]` 实际不被消费，配色落 DIM 灰。主审一行修正 7d5ba15 补 `"batch_target": WARN` 别名键并钉真实渲染链断言；补记已写入卡面验收补记。
- T12b 验收：713206e；ruff 全仓 0 项、定向 71 passed、全量 **352 passed**（基线 348 只增不减）、collect-only 一致；离屏冒烟 demo 40 行含 2 复合行、批量改判 28 部生效后 `can_apply` 转 True；离屏目验复合行徽章呈警示橙描边。
- code-review 双轴（fixed point 58517b8）：Standards 无硬违规，5 条判断性提示（1/2 函数签名多模式与 None 双语义、3 demo 五处同步的 shotgun 苗头、4 徽章键双命名空间、5 vm 为 None 时批量项静默返回）——1/2/4/5 记账不阻塞，0 勾选时 toast「已生效 0 部」为可接受行为；Spec 无缺失，theme 补键确认为有依据卡外修正（已补记卡面）。
- 老分类质量计划自此全部收口：C1-C9 + 老 Task-11（=嵌套计划 T04/05 白名单收敛）+ 老 Task-12（=T12a/b）+ 老 Task-13（被嵌套计划 T08 取代）；嵌套计划仅余 demo 样式走查类遗留给后续实机验证。

## D-20261125-02 v0.6.3 发版 [PROXY-DECISION]
- 背景：owner 令"现在补齐，然后 push 发版"；版号 AskUserQuestion 呈报后 owner 缺位未决，decision-proxy 四门代决为 **0.6.3**（依据=owner 既有 0.6.x 系列偏好、0.7.0 曾于 D-20261112-04 被驳回；本次内容=老 Task-12 批量改判 UI 补齐，修订号递增口径从宽从 owner 先例）。owner 事后驳回优先，届时按 D-20261112-04 先例删 Release/重建 tag。
- 变更面：`app/__init__.py` 与 `installer/installer.iss` 兜底默认值 0.6.2→0.6.3。

## D-20261125-03 死锁修复 DIR-01 + 添加库关键词预填 LIB-01（owner 拍板立卡）
- 背景：owner 实机反馈「全新安装仍删不掉库」。调研（code-reader 全链取证）结论：非 D-20261112-02 回归——悬空别名已宽容化，但 source_root 路径存在性仍是硬校验，实机遗留旧 config.toml 指向 G:\Media\_incoming 不存在 → 保存全量校验第一关抛错、原子写零落盘 → 库增删重载即复原，鸡生蛋死锁；首跑自洽生成只在 config.toml 缺失时触发，升级安装保留旧非法配置故复现。
- 卡 DIR-01（01c30c8）：目录存在性校验宽容降级——source_root/fallback_path/库路径不存在改 warnings（同 D-20261112-02 模式：结构错误硬拦、事实性错误降级），config_hash 不含 warnings，GUI 零改动（橙警告横幅分支现成）；测试 352→354（含死锁解除直钉与重复库名护栏钉，3 例原地改写清单见提交正文）。主审实机场景冒烟：全悬空路径加载不抛错、warnings 三条齐。
- 卡 LIB-01（20b1b34）：添加库时关键词列同步预填文件夹名（owner 两项拍板：库名=文件夹名已有、关键词同步预填；加权词仍空）。一行改动+回归；旧测试 :340 断言随语义同步（必然连带，非扩范围）。测试 354→355。
- GUI 目验：离屏回归+冒烟通过（离屏无中文字体，真机不受影响）；提交注明 GUI 已验证（离屏）。
- 遗留观察：路径宽容化后扫描器对不存在 source_root 将产出空计划（preflight 另有兜底阈值告警），如实机出现再议是否提升回硬拦或补扫描前体检。

## D-20261125-04 source_root 在媒体库内部放行 + 零库宽容 + 扫描添加子文件夹（owner 反馈三项）
- 背景：owner 实机反馈①删除电影库名仍失败（截图：校验失败「source_root(已删除待整理) 不能位于 媒体库(已删除) 内部」）②该嵌套是真实合法场景③添加库希望支持扫描父目录批量登记子文件夹。
- 根因（code-reader 取证）：`_check_overlap`（config.py）对全部根两两硬拦无豁免；且「至少需要定义一个 [[library]]」构成第二层死锁——删光库后保存永远失败，库永远删不掉。目录名"已删除"与判定无关。
- 规则变更（owner 已确认场景合法性）：①source_root 位于媒体库**内部**这一方向放行为 warnings（反向"媒体库在源内"仍硬拦，防库内容被当待整理源扫描）②零库从硬拦降为 warnings「未定义任何媒体库：所有整理文件将落入兜底库」；结构错误（同目录/库名重复/库间嵌套/媒体库在源内/staging 校验）保持硬拦。
- 新功能：配置页新增「🔍 扫描添加子文件夹」——选父目录，直接子文件夹（跳过隐藏目录与文件）逐行登记为库，库名/关键词预填文件夹名，已存在路径跳过并 toast 汇总。
- 验证：ruff 0 项；mypy 回基线 150（新增 union-attr 1 处已收窄修复）；全量 361 passed（基线 355 只增不减，新增 6 例：嵌套放行警告钉、删库后保存直钉、零库警告钉、扫描添加/去重/取消与空目录）；GUI=离屏 widget 驱动测试通过（真机未目验，offscreen 无中文字体与 D-20261125-03 同口径）。
- 双轴审查整改（821cf3c）：Spec 轴发现①全已存在仍置脏②相等情形被连带放行，Standards 轴发现标签前缀匹配脆弱——三项均采纳修复：相等恢复硬拦（放行仅限真实嵌套）、豁免判定改显式 kind 三元组、全已存在不置脏；记账不阻塞项：check_session_root 未镜像豁免（会话输出目录语义不同，维持现状）、扫描器对"源嵌于库内"是否会扫入库内容待实机观察。
- 第三层死锁补记（537765c，owner 实机反馈"依旧无法删除/所有库都无法删除"触发）：前两层修复后实机仍删不掉，无头驱动真实 ConfigTab+AppState 取证抓到真凶——`_del_library_row` 误用 Qt5 旧 API `selectionModel().currentRow()`（PySide6 无此方法），槽内 AttributeError 被 Qt 静默吞掉，删除按钮自始至终没删过任何行（零测试覆盖故漏网）。教训：①UI 槽内异常静默吞没，按钮类交互必须有 widget 级驱动测试；②"修了校验≠删得掉"，删库链路应整链无头复验而非只测后端。改用 `QTableWidget.currentRow()`，mypy 基线 150→149，全量 365 passed。

- 表头全选补记（860aa33，owner 2026-11-25 实测反馈）：分类计划页表头√列点击=全选/全不选切换（未全勾→全选，已全勾→全取消，部分勾选→全选），复用 viewmodel 既有 select_all_visible（此前定义了但 UI 从未接线）；全仓首个 header sectionClicked 用法。全量 367 passed。
- 别名扫描分析立项补记（11978cc，owner 2026-11-25 实测反馈驱动）：owner 提出"别名表和弱别名表应引入扫描分析"并核对历史记录后拍板数据源=NFO 未映射题材+影片名切词、建议=人工逐条指定目标库、优先级表不动（人工运维）。方案=把 D-20261109-01 人工审计四步（跑指标→标签云频次→人工逐例定映射→复跑验证）工具化为配置页「🔍 别名扫描分析」对话框：审计摘要行+双频次榜+勾选指定库+追加进编辑框（不自动落盘）。关键语义核对：库名 normalize 后天然强命中（alias_map 库名入表），别名表只叠加上去。与被否决方案边界：无 TF-IDF 自动关键词、无外部 LLM、无自动写配置。
- 已覆盖候选过滤补记（5a728b8，owner 2026-11-25 反馈"加入别名表后应不再被扫描出"）：扫描分析题材榜按 normalize_key 归一比对已覆盖键（已落盘强/弱别名 ∪ 编辑框待保存行），追加后未保存重开对话框即不再列出，保存后依然成立；词频榜不受影响。
- 批量分拣迭代补记（ca80ac2，owner 2026-11-25 反馈"单个选择保存过繁琐"）：对话框改「加入清单（强/弱）→跨榜多库连续分拣→✓统一保存（按强/弱一次性聚合追加）」三段式，带清单关闭需确认；分拣阶段不触发宿主回调。另记录 .mypy_cache 损坏致 INTERNAL ERROR 偶因，清缓存即愈。

## D-20261125-05 分类机制五项调整（A 含 D / B 两层 / C-1 / E）[已拍板]
- **原决策**：
  - 候选四项：A 元数据标签退出自动分类信号域、B 手工改判持久化、C 多题材择优语义、D 高频学习提升建议工具化。
  - 评议中 C 拆为 C-1 填充优先级表与 C-2 择优语义修正，并新增 E（库名预填触发摘要择优偏向场面词）。
  - 排期经 owner 拍板为全部一起做，落地后统一实机复测；每卡验收用重放量尺离线核对四项指标（自动生效单元数/多候选胜出依据分布/默认勾选数/票数闭合不一致对数），实机复测放最后。
- **我的异议**：
  1. [HIGH_RISK_OBJECTION] A-2 推翻 D-20261101-03 的自学习自动生效承诺与人工改判记 2 票。
  2. [HIGH_RISK_OBJECTION] "源在库内会重扫已归位内容"与代码冲突：扫描根是 source_root（`I:\CineSort\app\core\scanner.py:296-299`），"库在源内"方向仍硬拦（`I:\CineSort\app\core\config.py:284-293`）。
  3. [HIGH_RISK_OBJECTION] E 改 smart 择优顺序触及 D-20261031-02。
  4. [HIGH_RISK_OBJECTION] B(ii) 新建记忆文件属新持久层。
  5. [HIGH_RISK_OBJECTION] C-1 与 D-20261125-04"优先级表不动"的关系需 owner 确认。
  - 另纠正"基准反转"：32 条分布在 12 个会话，只有最后两个会话的 8 条能与冻结计划对账。
  - 另指出：最后计划的 7 条直证是幸存者偏差样本；C-2 反对立项；80% 的改判落点不在标签候选内。
- **主模型最终决定**：全部采纳。
  - #1 owner 拍板批准，A-2 施工（人工票只作建议不自动生效、人工改判不再按题材记 2 票）。
  - #2 B(ii) 的前提改写为两条成立的命中面：同作品后续批次的副本或分集；回滚后重扫。
  - #3 E 走新增策略值，旧 smart 行为不变。
  - #4 B(ii) 从会话日志派生，不新建记忆文件。
  - #5 owner 拍板批准按类全量填表，排序由 owner 定（"不动"语义修订为允许手工填写）。
  - 排期"全部一起做"为 owner 拍板，评议方提示窗口期风险（每执行一批人工改判就多一批单片票；A-2 本可先行发布），执行层面服从。
  - 置信度诚实化确认在 E 卡范围内（主模型明确评议口径#4：只改择优不降置信会把默认勾选从 157 推到 182–199）。
- **条件是否已闭环**：A、B、C-1、E 的前提条件均已闭环。施工后的重放验证待执行卡完成。
- **是否 [PRESSURE-OVERRIDE]**：否。
- **数据口径**：
  - 32 条执行 = 29 条人工改判 + 3 条确认。其中 25 条人工为重放直证，4 条由票数闭合反推（引用时不写"32/32 可重放"）。
  - 被否决的 25 条按通道：自学习自动生效 12、规则级高置信 9（其中文件夹名顺序裁决 6）、摘要择优 4。
  - 重放与 owner 陈述不独立，不表述为对它的证实；稳健下限口径 Σ(votes−2×manual)=21→约 3 片确认。
- **后续风险跟踪**：
  1. E 默认不生效，owner 需切换实机 `strategy` 到新值。验证：实机配置的取值。
  2. 人工票和确认票退出多候选择优须由代码保证，不能依赖 owner 填全表（漏填一个库，票数就在未列入的库之间重新接管）。验证：重放后多候选胜出依据不含票数。
  3. C-1 不得按默认顺序全填（会让最大粗桶占比从 41% 升到 58%），单库垫底会把判定转移给另一行为类库（20→48）；纯配置不经代码验证链，验收项含"填表后重放核对"。
  4. B(ii) 只对留痕上线后的执行生效（现有日志无 provider id/人工标记），被回滚的会话不得派生；当前池可确定套用的 3 个单元需历史迁移才覆盖。验证：单测。
  5. 同 provider id 多单元的成因未核实（实机已有同 id 人工落点不一致反例），B 开工前补查。
  6. 窗口期继续批量执行会累积单片票，A-2 可先行发布。验证：learned.json 的新增人工票数。
  7. 手工操作量预计不减少（80% 落点不在候选内）；若要降低需另立信号源议题并复议 D-20261109-01。owner 知情拍板。
  8. 界面口径（代码读法"无跨会话移动级行集视图"与 owner 截图不符）留终验 GUI 黑盒验证；若证实跨会话累积则评议方更正读法。
  9. 证据文案"优先级第 1 位"待修（`I:\CineSort\app\core\classifier.py:238`、:244）。

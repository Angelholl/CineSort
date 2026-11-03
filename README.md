# CineSort

按 NFO 元数据把影片自动归入题材媒体库（Jellyfin / Emby 等）。读取每部影片 NFO 中的题材（`<genre>`）与摘要（`<plot>`），把影片文件夹归类移动到对应媒体库目录。**一部电影命中多个题材时，按可解释的决策链挑选唯一归属**，全程只读预览 → 确认 → 执行 → 可回滚，并带自学习。

- 运行时仅 PySide6 一项第三方依赖：Python 3.11+，界面为 PySide6 原生窗口
- **已刮削文件夹整目录迁移**：NFO/海报/海报集/字幕/extras/花絮/预告一个不少（计划行内显示文件数与体积）
- **自学习**：人工改判与确认结果沉淀为「题材 → 库」映射，多次确认后自动外推
- **事务安全**：冻结计划 + 漂移检测 + 库外暂存校验 + 原子改名 + 逐会话 fsync 日志 + 一键回滚
- **分发**：与 SubTrans 同链（PyInstaller → Inno Setup 6），推送 `v*` 标签即云端产出 `CineSort-setup-*.exe` 安装包 + SHA256 清单

## 快速开始

### 方式一：exe（推荐，参考 subtrans 的独立可执行分发）

直接运行 `dist\CineSort.exe`：单文件、免 Python 环境，双击即打开原生窗口。
首次启动会在 exe 旁生成 `config.toml`（便携模式）；若放在无写权限的目录（如
Program Files）则自动改用 `%APPDATA%\CineSort\config.toml`。

自己构建：`pip install pyinstaller` 后运行 `tools\build_exe.ps1`（PowerShell 7）。
安装向导版：与 SubTrans 同链（PyInstaller → Inno Setup 6）。本机安装 Inno Setup 6
（[官网](https://jrsoftware.org/isdl.php) / `winget install JRSoftware.InnoSetup` /
`choco install innosetup`）后运行 `tools\build_installer.ps1`，脚本自动从源码读版本号
（`ISCC /Dversion` 注入），生成 `installer\Output\CineSort-setup-*.exe`
（含开始菜单/桌面快捷方式与卸载器）。也可直接推送 GitHub，由云端流水线构建。

### 方式二：源码运行

1. 复制 `config.example.toml` 为 `config.toml`，改成你的实际目录（也可直接在 GUI「配置」页填写保存，保存时自动校验）。
2. 双击 `启动媒体分类工具.cmd`（后台起原生窗口）；或 `启动调试控制台.cmd` 看日志；或 PowerShell 7 里 `pwsh scripts\start_debug.ps1`。双击垫片需要 PowerShell 7（`winget install Microsoft.PowerShell`）。
3. PySide6 原生窗口自动弹出，关闭窗口即退出。
4. 工作流：**③ 配置 → ① 分类计划（扫描/勾选）→ ② 执行 / 回滚（体检→执行）**；④ 体检页随时诊断。

想先试玩：`python tools/make_demo_env.py` 生成 `demo/` 演示媒体库，然后
`python -m app --demo --config demo/config.toml`（或 `python -m app.ui.main_window --demo`）。

## 分类决策链（多题材择优）

对每部影片依次尝试：

1. **题材规则**：NFO `<genre>` 经别名表（`genre_aliases`，不区分大小写/全半角/`&amp;` 实体/组合写法）映射到媒体库；
   - `smart` 策略：命中多个候选库时，用摘要评分在候选中**择优**，评分不足以区分再按 `genre_priority` 优先级表；
   - `priority` 策略：严格按优先级表；
   - `genre_only`：不用摘要。
2. **摘要预判**：题材全部未映射/缺失时，用 `<plot>` 关键词评分（分 = 关键词权重 × 出现次数，阈值 `plot.min_score`）预判归属；每个判定都展示命中词×次数证据。
3. **自学习**（v0.3）：你的人工改判记 2 票、确认规则/预判结果记 1 票，沉淀为「题材 → 库」映射（`runtime/learned.json`）。同一题材累计票数 ≥ `learning.min_votes`（默认 2）后，之后带该题材的影片**自动**归入你历史选择的库（计划行标注青色「自学习」徽章与票数证据，默认勾选）；未达阈值时作为低置信建议显示。自学习永远让位于你的显式规则（优先级表/别名表），兜底库不参与学习；可在「③ 配置」页的「自学习映射」清单随时遗忘，或整体关闭。
4. **兜底库**：以上全部失败，落入 `fallback_path`；兜底占比超过阈值会提醒/阻断（这是规则质量的直观指标）。

每行计划都标注判定等级（规则 / 摘要预判 / 兜底）、置信度与依据，摘要预判与兜底默认不勾选，可逐行人工改判目标库。

## 安全机制

- **整目录迁移**：目录型单元按扫描快照整目录搬运（快照包含 NFO/海报/字幕/extras/花絮/预告等全部文件并逐一校验）；散落的花絮/预告视频不会把已刮削文件夹误判成"多部影片"。
- **只读预览**：扫描不碰文件；执行需显式点击并二次确认越过阻断项。
- **冻结计划**：执行只消费扫描时生成的 `runtime/plan.json`（含配置哈希与逐文件快照），配置或源文件漂移即拒绝执行。
- **迁移原语**：同卷一律 `os.rename` 原子改名；跨卷先复制到目标盘「库根之外」的 `.nfo-sorter-staging` 暂存，逐文件校验大小后原子改名进库，最后才删源；中断残留带 `.incomplete-*` 标记，绝不静默当成功（体检页可见、可一键清理）。
- **冲突三分**：同名异片 → 跳过并报告；同 provider id 已在目标库 → 判「已在位」提示清理冗余；半成品残留 → 阻断。
- **多版本/复合目录**：同 provider id 多个版本、一个目录多部影片 → 默认排除出批量执行，需人工确认。
- **事务日志**：每次执行独立 `runtime/journals/*.jsonl`，逐行 fsync；回滚只依据日志快照，不受当前配置影响，先预览再两步确认。
- **空间预检**：目标盘剩余空间（留 10% 余量）不足即阻断。
- **单实例锁**：重复启动直接提示。

## Jellyfin 注意事项（执行前 runbook）

1. **建议先停止 Jellyfin 服务**（服务版 `Stop-Service JellyfinServer`，托盘版退出进程）或关闭相关媒体库的「实时监控」。工具的执行前体检会自动检测正在运行的 Jellyfin 进程并阻断，确认已停止/关闭后可勾选越过。
2. **观看状态（已看/进度/收藏）不保证保留**：跨库移动在 Jellyfin 里是「删旧建新」，UserData 可能丢失。建议第一次先勾选 1~2 部试跑（canary），执行后核对：条目是否正确识别、观看状态是否保留、然后「扫描所有媒体库」并比对前后条目数。
3. 移动后触发一次全库扫描；NFO 含 `<uniqueid>`（tmdb/imdb）时可按 provider id 重新识别。
4. 建议在 Jellyfin 库设置中启用 Nfo 元数据下载/保存器，让后续刮削持续维护 NFO。

## 配置速查

| 键 | 说明 |
|---|---|
| `source_root` | 待归类影片的源根目录（工具会移动其下的影片文件夹） |
| `[[library]]` | 媒体库：`name`（标准题材名）+ `path`（库目录，必须已存在）+ 摘要关键词 |
| `fallback_path` | 兜底库目录 |
| `genre_priority` | 题材优先级（排前面的优先） |
| `genre_aliases` | 题材别名 → 标准库名（Sci-Fi/動作/Action & Adventure…） |
| `strategy` | `smart` / `priority` / `genre_only` |
| `plot` | 摘要预判开关、评分阈值、长度归一 |
| `learning` | 自学习开关与自动生效票数（默认开、2 票） |
| `on_conflict` | 同名冲突：`skip`（推荐）/ `rename`（需 NFO 带 provider id） |
| `staging_dir` | 跨盘暂存目录（默认自动放在目标库所在盘库根旁） |

约束：库根必须预先存在；库根之间不得嵌套、不得与源目录重叠（配置保存时自动校验）。

## 目录结构

```
app/
  ui/main_window.py  启动入口（PySide6 原生窗口 / 单实例锁）
  core/
    config.py        配置加载与校验
    nfo.py           NFO 解析（编码链/实体/命名空间/组合题材容错）
    scanner.py       影片单元识别（多CD/光碟/散装/extras 排除）
    classifier.py    决策引擎（规则→摘要评分→兜底）
    planner.py       计划冻结/冲突三分/漂移检测
    fsops.py         迁移原语（staging+校验+原子改名）
    journal.py       事务日志（fsync/回滚）
    preflight.py     执行前体检
    jobs.py          后台任务编排
tests/               73 个用例（含故障注入与 API 全链路集成）
docs/decision-log.md 设计决策记录
```

## 开发与测试

```powershell
python -m pytest tests -q          # 全量测试
python tools/make_demo_env.py      # 生成演示环境
```

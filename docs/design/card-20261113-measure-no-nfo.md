# 卡 A1：无 NFO 残差测量脚本（决策 D-20261113-01 Step A）

决策依据：`docs/decision-log.md` D-20261113-01（owner 拍板「先测量后定」）
测试基线：**337 passed**（D-20261112-04 实测；本卡净增 10 → 收口应 **347**）；全仓 ruff 基线 **0 项**（D-20261112-01 后全仓 All checks passed），改动文件必须 0 项
既有教训钉：D-20261109-01 更正——对目录树做测量**必须递归**，顶层 glob 会系统性漏数（曾致「147 个视频全部无 NFO」误判，递归实测 148 内层影片 145 自带 NFO）

## 一、本卡要解决的问题

无 NFO 内容预判方向是否立项，取决于两个实证数字：**真正无 NFO 的影片有多少**（残差规模）与**无 NFO 单元里可提取的信号有多少**（伴随文本字幕 / 位图字幕 / 文件名番号）。本卡产出一个一次性零依赖测量脚本，对 `config.toml` 的 `source_root` 做只读测量，产出脱敏报告，供 owner 决定 Step B（番号在线查询）/ Step C（本地 VLM）是否立项。

测量采用**双口径**并报告差值：
- **production 视角**：复用 `app.core.scanner.scan_source_root`（与主流程同语义，含复合/ST_BATCH 单元），逐单元记录有无 NFO；
- **深查视角**：独立递归遍历全树，逐视频文件判定 NFO 共位、伴随字幕类目、番号提取——不受单元语义漂移影响，是 D-20261110-01 更正那样的地面真值。

## 二、改动文件（只许改这两个）

| 文件 | 动作 |
|---|---|
| `tools/measure_no_nfo.py` | Add |
| `tests/test_measure_no_nfo.py` | Test |

不动 `app/` 下任何文件（只允许 import）；报告产物落 `artifacts/`（**不入库**，git 不 add）。

## 三、改法（四点不得偏离；其余结构可微调）

1. **双口径与不变式**：production 视角用 `load_config`（项目根 `config.toml`，`--config` 可覆盖）+ `scan_source_root`；深查视角用 `os.walk`/`pathlib` 递归全树。不变式：深查视频文件数 ≥ production 单元数（写进测试钉）。
2. **字幕分类**：`TEXT_SUBS = {".srt", ".ass", ".ssa", ".vtt"}`，`BITMAP_SUBS = {".sub", ".sup"}`；大小写不敏感；判定对象=视频同目录及一层的伴随文件。
3. **番号提取（保守基线，必须被测试钉住）**：先剥除前导 `【】[]` 字幕组/站点标记，再按序匹配：`FC2-PPV-` 前缀 + 6-8 位数字；`[A-Za-z]{2,6}[-_ ]?\d{2,5}` 标准番号（允许尾缀 `-[A-Za-z]`、`CD\d` 分片标记）；分隔符 `[-_. ]` 宽容、大小写不敏感；同一父目录内同番号多分片（CD1/CD2）**去重计 1 部**。匹配不到返回 None，不得猜。
4. **脱敏红线**：Markdown 报告与 JSON 明细**均不得含**完整文件名、目录名、女优名、根路径之外的路径成分；样本区只允许出现番号与扩展名类目；汇总数字不受限。CLI：`python tools/measure_no_nfo.py [--config PATH] [--root PATH] [--out DIR]`，`--out` 默认 `artifacts/measure-no-nfo-<YYYYMMDD>`，产出 `<name>.md` 摘要 + `<name>.json` 明细（明细同样脱敏）。脚本对 `--root`（默认取 config 的 source_root）不存在时明确报错退出，绝不写任何被测目录。

## 四、先红后绿的回归测试（10 个，构造 tmp_path 假树，绝不触真实库）

| 测试名 | 构造 | 断言（逐字段钉） |
|---|---|---|
| `test_deep_walk_finds_nested` | `a/b/c/v.mp4` 三层嵌套 | 深查视角发现该文件（递归钉） |
| `test_nfo_colocation` | 同目录有/无 `.nfo` 两例 | `has_nfo` 判定正确 |
| `test_subtitle_classification` | `.srt`→text、`.sup`→bitmap、`.SRT` 大写 | 类目正确、大小写不敏感 |
| `test_code_extraction_standard` | `ABP-123.mp4`、`JUR-439-C.mp4` | 番号含尾缀：`ABP-123`、`JUR-439-C` |
| `test_code_extraction_fc2` | `FC2-PPV-1234567.mp4` | 番号完整提取 |
| `test_code_prefix_strip` | `【某字幕组】ABP-123.mp4` | 番号 = `ABP-123`（前缀剥除） |
| `test_code_dedupe_cd` | 同目录 `ABP-123 CD1.mp4`/`CD2.mp4` | 该番号计 **1** 部 |
| `test_no_code_chinese` | 纯中文文件名视频 | 番号 = None（不猜） |
| `test_report_masking` | 假树文件名含可识别串（如 `女优某某`） | 报告 `.md` 与 `.json` 文本均**不含**该串，只含番号/类目/数字 |
| `test_walk_ge_production` | 构造含视频+字幕+无 NFO 的小树 | 深查视频数 ≥ production 单元数（不变式钉） |

## 五、验收命令（以下命令均在项目根目录执行，cwd 即仓库根）

1. 红：`python -m pytest tests/test_measure_no_nfo.py -q`（10 个新测试先失败）
2. 绿：`python -m ruff check tools/measure_no_nfo.py tests/test_measure_no_nfo.py` → **0 项**；`python -m pytest tests/test_measure_no_nfo.py -q` 全绿（10 passed）
3. 全量不回归：`python -m pytest tests -q` → **0 failed，用例总数 = 347**（337 + 10）
4. 真实数据只读自检：`py -3.12 tools/measure_no_nfo.py --out artifacts/measure-no-nfo-20261113` → 把 Markdown 汇总（production 单元总数 / 无 NFO 单元数 / 深查视频总数 / 无 NFO 视频数 / 文本字幕 / 位图字幕 / 番号可提取数 / 同番号分片去重数）**原样贴进回报**，不许只说"符合预期"

## 六、约束

- 纯标准库 + 项目既有 dev 依赖（pytest/ruff）；**不得新增任何第三方依赖、不得联网**。
- 只读被测目录：不写 `config.toml` / `config.example.toml` / `E:\已刮削` 下任何文件；脚本任何分支不得产生写入被测树的行为。
- 报告/JSON 不入 git（不 add `artifacts/`）；脱敏红线（三.4）做不到 = 卡失败，如实回报，**不许静默降级为"含文件名但说不发布"**。
- 现有测试 0 删 0 改；不得为变绿放宽断言。
- 卡外问题即停，回报里单列，不得顺手改。
- 读大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 `pointerize` / `read_pointer` / `read_diff_only`，禁止整读文件全文。
- 完成后 `git commit`（`feat(tools): 无NFO残差双口径测量脚本` 风格，正文 `verify:` 写实测数字 + `Refs: D-20261113-01`），**不得 push**，不得 `git add -A`、不得 `--no-verify`。

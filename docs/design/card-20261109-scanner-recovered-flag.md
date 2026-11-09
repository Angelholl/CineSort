# 卡 C2：scanner 容错恢复 flag 与告警语义收窄（计划 Task-03）

规格：`docs/design/2026-11-09-classification-quality.md` §2　计划：`docs/plans/2026-11-09-classification-quality.md` Task-03
决策依据：`docs/decision-log.md` D-20261109-01　前置：Task-01/02 已合入（`7d843e8`+`094ceff`，`NfoInfo.recovery` 已存在）
测试基线：**210 passed**（本卡净增 3，收口后应 213）

## 一、根因（已实测定位，不得重新调查）

上一卡已让 15 个 JavDB NFO 走 XML 正常路径（`parse_error = None`、`recovery` 记录恢复方式）。但 `scanner.py:171-174` 目前只在 `info.parse_error` 非空时挂 `nfo_parse_warning`，**没有任何 flag 表达"这份 NFO 是被容错救回来的"**，计划页与体检页也就无法区分"硬失败"与"已恢复"。本卡把 flag 语义拆成两档：硬失败 → `nfo_parse_warning`（不变），已恢复 → 新 flag `nfo_recovered`。扫描阶段的 warn note（scanner.py:244-246 只认 `parse_error`）**不改**——恢复类单元不再产生 warn note 正是本卡的修复目标。

## 二、改动文件（只许改这两个）

| 文件 | 动作 | 落点 |
|---|---|---|
| `app/core/scanner.py` | Modify | :171-174（`_analyze_dir` 内 nfo 解析与 flag 段） |
| `tests/test_scanner.py` | Test | 末尾追加 3 个测试 |

## 三、改法（照抄执行）

`scanner.py:171-174` 改为：

```python
    nfo_path = find_nfo(d, vids, multi_cd)
    info = parse_nfo_file(nfo_path) if nfo_path else None
    if info and info.parse_error:
        flags.append("nfo_parse_warning")
    elif info and info.recovery:
        flags.append("nfo_recovered")
```

不改 `_analyze_loose`（散装文件档，:191-217）、不改 warn note 生成段、不改 `find_nfo`、不改 `EXCLUDED_DIRS` 与复合目录排除逻辑。

## 四、先红后绿的回归测试（3 个；用既有 `build_env` + `make_movie` 夹具，NFO 内容手工替换）

| 测试名 | 构造 | 断言 |
|---|---|---|
| `test_recovered_nfo_flags_without_warning` | movie.nfo 内含 `<7mmtvid>x</7mmtvid>`（其余正常） | 该单元 `flags == ["nfo_recovered"]`；`scan_source_root` 返回的 notes 中**没有**该 path 的 warn |
| `test_broken_nfo_keeps_warning` | movie.nfo 为残片 `<movie><genre>恐怖</genre>`（无闭合，落 regex 档） | flags 含 `nfo_parse_warning`；notes 存在同 path 的 warn |
| `test_clean_nfo_has_no_nfo_flags` | 既有 `nfo_xml()` 正常内容 | 该单元 `flags == []` |

## 五、验收命令（以下命令均在项目根目录执行，cwd 即仓库根）

1. 红：`python -m pytest tests/test_scanner.py -q`（3 个新测试先失败）
2. 绿：`python -m ruff check app/core/scanner.py` 必须 **0 项**；`python -m pytest tests/test_scanner.py -q` 全绿（14 现有 + 3 新 = 17）
3. 全量不回归：`python -m pytest tests -q` → **0 failed，用例总数 = 213**（基线 210 + 3）
4. 真实数据只读自检（不得写 E: 盘任何文件）：
   `python -c "import sys;sys.path.insert(0,'.');from app.core.config import load_config;from app.core.scanner import scan_source_root;cfg=load_config(r'D:/CineSort-beta/CineSort/config.toml');us,ns=scan_source_root(cfg);print('recovered=',sum(1 for u in us if 'nfo_recovered' in u.flags),'warn=',sum(1 for u in us if 'nfo_parse_warning' in u.flags),'warn_notes=',sum(1 for n in ns if 'XML' in str(n.get('reason'))))"`
   → 期望 `recovered= 15 warn= 0 warn_notes= 0`

## 六、约束

- 只改卡面两个文件；`nfo.py`、`classifier.py`、`planner.py`、`preflight.py`、UI 一律不动。
- 现有测试 0 删 0 改；不得为了变绿放宽断言。
- 不得联网；对 `E:\已刮削` 与 `D:\CineSort-beta` 只读，禁止任何写入或移动。
- 卡外发现的问题：即停，在回报里单列，不得顺手改。
- 读大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 `pointerize` / `read_pointer` / `read_diff_only`，禁止整读文件全文。
- 完成后 `git commit`（Conventional 前缀 + 中文描述，正文写 `verify:` 验证结果与 `Refs: D-20261109-01`），**不得 push**，不得 `git add -A`、不得 `--no-verify`。

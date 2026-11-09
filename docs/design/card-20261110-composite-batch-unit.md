# 卡 C8：复合目录 → 整目录单元（计划 Task-09，特性 C-1）

规格：`docs/design/2026-11-09-classification-quality.md` §4.1　计划：`docs/plans/2026-11-09-classification-quality.md` Task-09
决策依据：`docs/decision-log.md` D-20261109-01（owner 拍板：逻辑归集、不动文件、不拆分）　前置：Task-03（`d40c8df`）
测试基线：**248 passed**（本卡净增 4 + 1 处授权修订，收口应 252）；全仓 ruff 基线 **10 项**（只降不增）

## 一、本卡要解决的问题

实测：源根 43 个目录被 `_analyze_dir` 判为"复合目录"后 `return None, {"level": "excluded", ...}`（`scanner.py:162-164`）——它们**既不分类也不进计划视图**，只在扫描页留一行提示。这 43 个目录实为"按女优名归拢的散装视频"（147 个视频、0 个 NFO）。

owner 已定：**逻辑归集**——把这些目录作为"整目录单元"送进计划视图（默认不勾选、需目录级改判才能执行），**不物理搬移、不拆散、不改目录名**。本卡只做扫描层：复合目录不再排除，而是产出一个带 `composite=True` 的整目录单元。

**状态与执行门禁在下一卡（Task-10/11）**。本卡结束时复合单元会短暂地"能被分类"，这是预期的中间态，卡面第 5 节要求把这个中间态**如实测出来贴进回报**，不许隐瞒。

## 二、改动文件（只许改这两个）

| 文件 | 动作 | 落点 |
|---|---|---|
| `app/core/scanner.py` | Modify | `Unit` 字段（:66 `disc` 之后加 `composite: bool = False`）；`_analyze_dir` 的复合目录分支（:162-164） |
| `tests/test_scanner.py` | **修订 1 处** + Test 追加 4 个 | `test_complex_dir_excluded`（:55-64）更名重写；末尾追加 4 个 |

修订批准依据：owner 拍板 + 规格 §4.1（旧"排除"语义废止）。除这一处外现有测试 0 删 0 改。

## 三、改法（照抄执行）

1. `Unit` 在 `disc` 字段之后加 `composite: bool = False`。
2. `scanner.py:162-164` 的 `return None, {...excluded...}` 整段替换为：

```python
    if len(bases) > 1:
        vids = sorted(mains or videos, key=lambda p: p.name.lower())
        nfo_path = find_nfo(d, vids, False)
        info = parse_nfo_file(nfo_path) if nfo_path else None
        if info and info.parse_error:
            flags.append("nfo_parse_warning")
        elif info and info.recovery:
            flags.append("nfo_recovered")
        files = snapshot_dir(d)
        total, count, mx = _snapshot_stats(files)
        unit = Unit(
            id=rel_id, path=d, kind="dir", dst_name=d.name,
            videos=vids, multi_cd=False, disc=disc, composite=True,
            nfo_path=nfo_path, nfo=info,
            title=(info.title if info and info.title else d.name),
            year=(info.year if info else None),
            provider=(info.provider_id if info else None),
            files=files, total_size=total, file_count=count, max_mtime_ns=mx,
            flags=flags + ["composite"],
        )
        return unit, {"level": "info", "path": str(d),
                      "reason": f"复合目录：{len(bases)} 个疑似影片 base，"
                                "已作为整目录单元生成（需目录级改判后执行）"}
```

3. 不动的部分（红线）：`mains` 花絮过滤（:151-153）、`RE_MULTI_CD` 分组（:157-161）、`disc` 判定、正常路径 :165-166 的 `vids/multi_cd` 逻辑、`_analyze_loose`、`EXCLUDED_DIRS`。
4. **绝不拆分**：复合目录内无论几个 base、无论有无 NFO，都只产 **1 个** 整目录单元；`files` 必须是 `snapshot_dir(d)` 整目录快照（含海报/字幕/花絮），保证将来整目录迁移零遗漏。

## 四、先红后绿的回归测试（1 修订 + 4 新增）

修订：`test_complex_dir_excluded` → **更名** `test_complex_dir_becomes_batch_unit`，同输入断言改为：`len(units) == 1`、`units[0].composite is True`、`units[0].kind == "dir"`、`"composite" in units[0].flags`、notes 中**无** `level == "excluded"`、**有** `level == "info"` 且 reason 含 `"复合目录"`。

新增 4 个：

| 测试名 | 构造 | 断言 |
|---|---|---|
| `test_composite_unit_covers_whole_dir` | 目录内 2 个 base 各 1 视频 + 1 张海报 jpg | `file_count == 3` 且 `files` 覆盖全部三个文件；`videos` 为 mains 按名排序 |
| `test_composite_with_nfo_still_batch` | 复合目录 + 正常 `movie.nfo` | `composite is True`、单元带 nfo 与 provider，且**仍只有 1 个单元**（不拆分） |
| `test_composite_no_split_on_c_variant` | `[ABC-1].mp4` 与 `[ABC-1-C].mp4` 两个 base | 恰 1 个 composite 单元（钉"同番号 -C 变体不得被拆开"这条红线） |
| `test_supplement_dirs_not_composite` | 既有"片名 - Behind The Scenes"子目录场景 | 该单元 `composite is False`（花絮过滤回退保护） |

## 五、验收命令（以下命令均在项目根目录执行，cwd 即仓库根）

1. 红：`python -m pytest tests/test_scanner.py -q`（新测试与改名后的测试先失败）
2. 绿：`python -m ruff check app/core/scanner.py tests/test_scanner.py` 必须 **0 项**（两个文件全列）；`python -m pytest tests/test_scanner.py -q` 全绿（**实测现有 17**，改名不减数，加 4 新 = **21**）
3. 全量不回归：`python -m pytest tests -q` → **0 failed，用例总数 = 252**（248 + 4）
4. 全仓 lint 不增：`python -m ruff check . 2>&1 | grep "^Found"` → 必须 **≤ 10 errors**
5. 真实数据只读自检（**必须贴原样输出**，不许写"符合预期"）：
   `py -3.12 -c "import sys,collections;sys.path.insert(0,'.');from app.core.config import load_config;from app.core.scanner import scan_source_root;cfg=load_config(r'D:/CineSort-beta/CineSort/config.toml');us,ns=scan_source_root(cfg);c=[u for u in us if getattr(u,'composite',False)];print('units=',len(us),'composite=',len(c));print('notes=',collections.Counter(n.get('level') for n in ns));print('vids=',sum(len(u.videos) for u in c),'files=',sum(u.file_count for u in c))"`
   → 期望 `units= 140 composite= 43`、notes 里 `excluded` 归零、`info` 为 43、`vids` 约 147、`files` 为这些目录的文件总数

## 六、约束

- 只改卡面两个文件；除 `test_complex_dir_excluded` 那一处更名重写外，现有测试 0 删 0 改；不得为变绿放宽断言。
- **禁止任何物理文件操作**：不得移动/改名/删除 `E:\已刮削` 下任何东西；不得写 `D:\CineSort\config.toml`、`D:\CineSort-beta\CineSort\config.toml`、`config.example.toml`。本卡只读真实盘。
- 不得改 `planner.py`、`classifier.py`、`jobs.py`、`preflight.py`、UI（那是 Task-10/11/12）。
- 不得联网。卡外问题即停，在回报里单列，不得顺手改。
- 读大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 `pointerize` / `read_pointer` / `read_diff_only`，禁止整读文件全文。
- 完成后 `git commit`（Conventional 前缀 + 中文描述，正文 `verify:` 写实测结果与 `Refs: D-20261109-01`），**不得 push**，不得 `git add -A`、不得 `--no-verify`。

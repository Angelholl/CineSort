# 卡 C1：NFO 数字开头元素名容错 + 裸 id 纳入 provider id（计划 Task-01 + Task-02 合并）

规格：`docs/design/2026-11-09-classification-quality.md` §2　计划：`docs/plans/2026-11-09-classification-quality.md` Task-01 / Task-02
决策依据：`docs/decision-log.md` D-20261109-01　测试基线：**197 passed**（已实测回填，收口断言 ≥267 由收口卡负责，本卡净增 10 个测试）

## 一、根因（已实测定位，不得重新调查）

1. 片源 15 个 NFO 解析失败，全部同一成因：JavDB 刮削器在 `<movie>` 末尾写出 `<7mmtvid>https://…</7mmtvid>`，**元素名以数字开头违反 XML NameStartChar**，`ET.fromstring` 报 `not well-formed (invalid token): line N, column 3`。现有三级容错（movie 块截取、裸 `&` 转义）都救不了它，最终落到 regex 兜底档：genres/title/plot 信息没丢，但单元带 `nfo_parse_warning` 且界面出 15 条无意义告警。
   已验证修法：`re.sub(r"<(/?)(\d[^\s>/]*)", r"<\1_\2", text)` 使 15/15 恢复走 XML 正常路径，且 genres/title/plot 与 regex 路径逐字段一致。
2. 这些 NFO 的 `<javdbid>wKV281</javdbid>` 是**无属性的裸 id 元素**，现有 `_fill_from_xml` 只认 `<uniqueid type=…>` 与 `<id moviedb=…>`，故 `uniqueids` 为空 → `NfoInfo.provider_id` 为 None → planner 的 same_id 去重（"目标库已存在同一部影片，不移动"）对这批单元完全失效。

## 二、改动文件（只许改这四个，其余一律不动）

| 文件 | 动作 | 落点 |
|---|---|---|
| `app/core/nfo.py` | Modify | 正则区（:29 `_STRIP_TAGS` 旁）、`NfoInfo`（:42 `parse_error` 之后）、`parse_nfo_text`（:183-195 第 3 级之后）、`_fill_from_xml`（:112-135）、`_fill_from_regex`（:156-163） |
| `app/core/planner.py` | Modify | :118 `"evidence": dec.evidence,` 一行扩展 |
| `tests/test_nfo.py` | Test | 末尾追加 9 个测试 |
| `tests/test_planner.py` | Test | 末尾追加 1 个测试 |

## 三、改法（照抄执行，不得自行变更设计）

**A-1 第 4 级容错 + recovery 字段**

1. 正则区新增 `_RE_DIGIT_TAG = re.compile(r"<(/?)(\d[^\s>/]*)")`；`NfoInfo` 在 `parse_error` 字段之后加 `recovery: str = ""`。
2. `parse_nfo_text` 在第 3 级（裸 `&` 转义）失败之后、`if root is not None:` 之前插入第 4 级：

```python
if root is None:                              # 数字开头元素名（JavDB <7mmtvid>）
    rewritten = _RE_DIGIT_TAG.sub(r"<\1_\2", _RE_BARE_AMP.sub("&amp;", text))
    if rewritten != text:
        for cand in (rewritten,):
            try:
                root = ET.fromstring(cand)
                err = None
                info.recovery = "重写数字开头元素名（如 <7mmtvid> → <_7mmtvid>）"
            except ET.ParseError:
                m = _RE_MOVIE_BLOCK.search(rewritten)
                if m:
                    try:
                        root = ET.fromstring(m.group(0))
                        err = None
                        info.recovery = "重写数字开头元素名 + 截取 movie 块"
                    except ET.ParseError as exc:
                        err = f"{err}; {exc}"
```

3. 既有三级容错补 recovery 标记（**行为兼容**：movie 块截取成功 → `info.recovery = "截取 movie 块"`；裸 `&` 转义成功 → `info.recovery = "转义裸 &"`）。`parse_error` 语义**不变**——仍只在 regex 兜底档（`root is None`）时非空，成功容错一律 `parse_error = None`，不新增任何告警。
4. `planner.py:118` 改为：

```python
"evidence": list(dec.evidence) + ([f"NFO 已容错恢复：{u.nfo.recovery}"] if (u.nfo and u.nfo.recovery) else []),
```

**A-2 裸 id 元素纳入 provider id**

5. 正则区新增 `_RE_BARE_ID_TAG = re.compile(r"<([A-Za-z][A-Za-z0-9_]*id)>([^<]*)</\1\s*>", re.I)`（只匹配无属性裸 id 元素；带属性的 `uniqueid`/`id` 不命中）。
6. `_fill_from_xml`：循环前加 `bare_ids: dict[str, str] = {}`；循环内在 `t == "uniqueid"` / `t == "id"` 两分支**之后**追加：

```python
elif t.endswith("id") and len(t) > 2 and not el.attrib and text:
    scheme = t[:-2].lower()
    if scheme:
        bare_ids.setdefault(scheme, text)
```

循环后、去重语句（`info.genres = list(dict.fromkeys(info.genres))`）之前加 `for s, v in bare_ids.items(): info.uniqueids.setdefault(s, v)`（显式 `<uniqueid>` 条目优先）。
7. `_fill_from_regex` 末尾追加：

```python
for m in _RE_BARE_ID_TAG.finditer(text):
    name, val = m.group(1), m.group(2).strip()
    scheme = name[:-2].lower() if len(name) > 3 else ""
    if scheme and val:
        info.uniqueids.setdefault(scheme, val)
```

## 四、先红后绿的回归测试（先写测试跑红，再实现跑绿；共 10 个）

`tests/test_nfo.py` 末尾 9 个：

| 测试名 | 输入 | 断言 |
|---|---|---|
| `test_digit_leading_tag_recovers_via_xml` | `<movie><title>T</title><genre>动作</genre><plot>p</plot><7mmtvid>wKV281</7mmtvid></movie>` | `parse_mode=="xml"`；`parse_error is None`；genres/title/plot 逐字段正确 |
| `test_digit_tag_recovery_recorded` | 同上 | `info.recovery` 含 `"数字开头"` |
| `test_digit_rewrite_leaves_wellformed_untouched` | 既有 `nfo_xml()` 正常文本 | `parse_mode=="xml"` 且 `recovery == ""` 且 `parse_error is None`（零行为变化） |
| `test_digit_tag_xml_and_regex_paths_agree` | 同测试 1 文本，分别走 `parse_nfo_text` 与手工 `_fill_from_regex(NfoInfo(), text)` | genres/title/plot 三字段相等（信息零丢失） |
| `test_bare_javdbid_becomes_provider` | `<movie><title>T</title><genre>动作</genre><javdbid>wKV281</javdbid></movie>` | `uniqueids == {"javdb": "wKV281"}`；`provider_id == "javdb:wKV281"` |
| `test_bare_tmdbid_merges_scheme` | `<movie><tmdbid>42</tmdbid></movie>` | `provider_id == "tmdb:42"` |
| `test_uniqueid_attr_beats_bare_id` | `<movie><uniqueid type="tmdb">1</uniqueid><tmdbid>2</tmdbid></movie>` | `uniqueids["tmdb"] == "1"` |
| `test_bare_id_regex_path` | 破损文本 `<movie><genre>恐怖</genre><javdbid>wKV281</javdbid>`（无闭合，走 regex 档） | `parse_mode=="regex"` 且 `uniqueids == {"javdb": "wKV281"}` |
| `test_bare_id_ignores_empty_and_plain_id` | `<movie><id>plain</id><javdbid></javdbid></movie>` | `uniqueids == {}`（无空 scheme、空值跳过） |

`tests/test_planner.py` 末尾 1 个：

| 测试名 | 输入 | 断言 |
|---|---|---|
| `test_plan_evidence_notes_recovery` | 用既有 `make_movie` 造单元后，把 movie.nfo 内容替换为含 `<7mmtvid>x</7mmtvid>` 的变体 | `build_plan` 该单元 `evidence` 中存在以 `"NFO 已容错恢复"` 开头的行 |

## 五、验收命令（以下命令均在项目根目录执行，cwd 即仓库根）

1. 红：`python -m pytest tests/test_nfo.py tests/test_planner.py -q`（新测试先失败）
2. 绿：`python -m ruff check app/core/nfo.py app/core/planner.py` 必须 **0 项**；`python -m pytest tests/test_nfo.py tests/test_planner.py -q` 全绿（nfo 15+9=24、planner 6+1=7）
3. 全量不回归：`python -m pytest tests -q` → **0 failed，用例总数 ≥ 207**（基线 197 + 本卡 10）
4. 真实数据自检（只读，不得写 E: 盘任何文件）：`python -c "import sys;sys.path.insert(0,'.');from app.core.nfo import parse_nfo_file;from pathlib import Path;p=Path(r'E:/已刮削/待整理/一乃あおい/JUR-568-C/JUR-568-C.nfo');i=parse_nfo_file(p);print(i.parse_mode,i.parse_error,i.recovery,i.provider_id,len(i.genres))"` → 期望 `xml None <含"数字开头"的 recovery> javdb:wKV281 7`

## 六、约束

- 只改卡面四个文件；`app/core/scanner.py`、`config.py`、`classifier.py`、UI 一律不动（scanner 告警语义是下一卡）。
- 现有测试 0 删 0 改（本卡不需要任何修订）。
- 不得联网、不得调用任何外部 API；不得读写 `E:\已刮削` 下任何文件（第 5 节命令只读）。
- 不得改 `parse_error` 的既有语义、不得新增告警文案、不得动 `provider_id` 的 tmdb/imdb/tvdb 优先顺序（裸 id 只作为新增 scheme 落入 `uniqueids`）。
- 卡外发现的问题：即停，在回报里单列，不得顺手改。
- 读大于 4KB 的文件或查看改动，用 `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的 `pointerize` / `read_pointer` / `read_diff_only`，禁止整读文件全文。
- 完成后 `git commit`（Conventional 前缀 + 中文描述，正文写 `verify:` 验证结果与 `Refs: D-20261109-01`），**不得 push**，不得 `git add -A`、不得 `--no-verify`。

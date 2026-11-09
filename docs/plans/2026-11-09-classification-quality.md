# 实现计划：分类质量四特性（A NFO 容错+provider id / B 弱标签护栏 / C 复合目录归集 / D 标题弱评分）

- 日期：2026-11-09
- 基线版本：当前 main（GUI 目录浏览卡收尾后；本文 `文件:行号` 为当前基线，施工行号漂移以符号定位为准）
- 需求来源：owner 拍板三项立项 + "不拆分"边界；规格真值 = `docs/design/2026-11-09-classification-quality.md`
- 计划真值：本文件（拆解与验收口径），实现交给编程执行者；**禁止 git commit（由 owner 统一收口）**

## 目标

1. 15 类 JavDB NFO（数字开头元素名）走 XML 正常路径且不再告警；`<javdbid>` 等裸 id 元素纳入 provider id，same_id 去重恢复生效。
2. 弱标签命中降级为低置信、默认不勾，且永不压过强标签命中；配置/GUI/往返/hash 全链贯通。
3. 43 个复合目录成为"整目录待改判"单元（默认不选、不进兜底率口径），支持目录级批量改判并整目录执行/回滚，不写 learned。
4. 标题文本弱评分作为兜底前的低置信建议（词表与别名表统一），证据可区分"标题命中/摘要命中"。

## 架构

- 数据流不变：scanner（识别+NFO 解析）→ classifier（决策）→ planner（冻结计划+统计）→ jobs（执行）→ UI（viewmodel 纯逻辑 + plan_tab 渲染）。
- 特性 A/B/D 全部落在 classifier/config/nfo 层，planner 仅动 default_selected 门与统计口径；特性 C 横切 scanner/planner/jobs/preflight/UI 五层。
- 复合目录仍是一个 dir 单元（`composite=True`），新状态 `ST_BATCH`，不改单元/计划 schema 的其余形状；viewmodel 保持零 Qt（架构守卫测试继续钉）。

## 规格

`docs/design/2026-11-09-classification-quality.md`（行为定义、默认值、置信语义、GUI 语义、非目标、验收口径 A1-D3 与全局项，本文任务全部从它论证）。

## 全局约束（违反即 FAIL）

1. 不拆分复合目录；复合目录仍以目录为单位，不产生 file 单元（owner 拍板）。
2. scanner 既有排除语义（extras/花絮/sample/RE_SUPPLEMENT 回退/多 CD 合并）零改动；唯一修订 = 复合目录由"排除"改"整目录单元"。
3. 兜底率口径：复合单元不进分子（level 非 fallback）也不进分母（`total − composite`）；title 级非 fallback。preflight 阈值行为不变。
4. 弱信号一律 `confidence="low"` + `default_selected=False`；弱信号永不覆盖强规则命中。
5. 测试基线只增不减：本计划新增 70 个测试；**行为变更所需修订仅 2 处**（Task-09 的 `test_complex_dir_excluded`、Task-05 的 `test_viewmodel.make_unit` 复刻规则），逐条注明 owner 批准依据（规格 §1 约束 2、§3.2）。除此之外现有测试 0 删 0 改。
6. 每卡验证链：`python -m ruff check <本卡改动文件>`（0 项，D-20261102-02）→ 定向 pytest → 全量 pytest；GUI 卡加 offscreen 冒烟截图。
7. 执行者只 commit 不 push？——本计划**不 commit**，全部改动留工作区交 owner 核验。

---

## 0. 现状核实（已逐一读取确认）

| 关注点 | 位置 | 现状 |
|---|---|---|
| NfoInfo 字段 | `app/core/nfo.py:33-42` | `parse_mode`(41)/`parse_error`(42)，无 recovery 字段 |
| provider_id 优先级 | `app/core/nfo.py:44-53` | tmdb/imdb/tvdb → 其他任意；uniqueids 只来自 uniqueid/id 带属性元素 |
| XML 容错链 | `app/core/nfo.py:166-207` | 1 原文 → 2 movie 块截取(176-182) → 3 裸 & 转义(183-195)；成功即 `err=None`（199-200 的"已容错恢复"分支实际只覆盖截取路径且 err 已被重置为 None） |
| 正则兜底 | `app/core/nfo.py:138-163` | `_fill_from_regex` 抓 genres/title/plot/uniqueid/id(带属性) |
| scanner 复合目录排除 | `app/core/scanner.py:162-164` | bases>1 → `return None, {"level": "excluded", …}`；mains 过滤在 151-153（先于分组） |
| scanner 告警 flag | `app/core/scanner.py:171-174` | `parse_error` 非空即 `flags.append("nfo_parse_warning")`；note 在 244-246 |
| Unit 结构 | `app/core/scanner.py:57-75` | 无 composite 字段；flags:75 |
| alias 表 | `app/core/classifier.py:37-43` | `alias_map`：库自身名 + genre_aliases（用户优先） |
| map_genres | `app/core/classifier.py:46-58` | 返回 (mapped, unmapped)；planner.py:82 消费 unmapped |
| score_plot 归一 | `app/core/classifier.py:81-82` | `score / len(plot)**0.5`——短文本放大，title 不得复用 |
| rule_pick | `app/core/classifier.py:151-176` | mapped 内按 `_rank`(88-92)+票数+声明序裁决，conf 恒 "high"(176) |
| 决策分支 | `app/core/classifier.py:178-201` | 无题材：plot→soft→fallback(178-183)；全未映射：auto→plot→soft→fallback(194-201) |
| 弱规则缺位 | `app/core/classifier.py` | 无 weak 概念；`Decision.confidence` 默认 high(34) |
| Config 字段 | `app/core/config.py:70-84` | genre_aliases:76；无 weak/title |
| config_hash | `app/core/config.py:93-103` | payload 含 genre_aliases(98)，无 weak/title |
| 校验 | `app/core/config.py:195-200` | genre_aliases 值必须是已定义库 |
| describe/raw_describe | `app/core/config.py:270-291, 294-326` | genre_aliases:289/324；无 weak/title |
| dump_config_text | `app/core/config.py:329-365` | genre_aliases inline table(343-344)；[plot] 346-350 |
| default_selected | `app/core/planner.py:132-134` | `READY and (rule or (learned and medium))`——不看 confidence |
| 统计 | `app/core/planner.py:157-179` | `fallback_ratio = fb/total`(175)；无 composite |
| _refresh_stats | `app/core/planner.py:242-252` | apply 后重算同口径(252) |
| freshness 跳过条件 | `app/core/planner.py:219-220` | 仅 READY 被快照校验 |
| mark_undone | `app/core/planner.py:269-279` | 无条件回 READY（复合单元需修） |
| preflight READY 过滤 | `app/core/preflight.py:83-84, 121-124` | 磁盘/长路径只看 READY |
| preflight 兜底阈值 | `app/core/preflight.py:131-144` | 读 `stats.fallback_ratio`（口径修正后无需改） |
| run_apply 状态门 | `app/core/jobs.py:146-151` | 非 READY 全拒 |
| override 通道 | `app/core/jobs.py:153-168` | 内存改写 target_lib/root/dst_dir；`__fallback__`→兜底库 |
| 自学习沉淀 | `app/core/jobs.py:254-260` | `learned.record(genres,…)`；genres 空 → learned.py:45 空转 |
| 执行原语 | `app/core/fsops.py:80-123` | `transfer_dir` 快照校验+原子改名（复合目录整目录迁移可直接复用） |
| viewmodel 过滤/徽章 | `app/ui/viewmodel.py:17-31` | FILTERS(22)/LEVEL_FILTERS(21)/LEVEL_BADGES(26-31) |
| viewmodel 门禁 | `app/ui/viewmodel.py:188-194` | `checked_not_ready`：status != READY 全挡 |
| viewmodel 改判 | `app/ui/viewmodel.py:198-205` | `set_override` 单行 |
| plan_tab chips | `app/ui/plan_tab.py:102-111` | 硬编码 8 个 chip |
| plan_tab 底部条 | `app/ui/plan_tab.py:161-199` | summary/输出目录/全选/清空/扫描/执行 |
| plan_tab 详情改判 | `app/ui/plan_tab.py:252-262, 559-564` | 单行下拉 + `_fill_libs`（排除"兜底库"占位） |
| 状态徽章映射 | `app/ui/table_cells.py:19-26` | STATUS_BADGES 现有 6 键（测试未钉，可扩） |
| 徽章配色 | `app/ui/theme.py:35-44` | BADGE_COLORS 现有键 |
| 配置页别名框 | `app/ui/config_tab.py:94-96, 116` | `f_alias_text` QPlainTextEdit；演示禁用清单 258-262 区域；表单聚合 352 |
| 配置 viewmodel | `app/ui/config_viewmodel.py:23-55, 58-112` | alias_text 往返(52-53, 60-67)；body 组装(92-112) |
| demo 数据 | `app/ui/demo_data.py:36-85` | `fake_units` 四级 _LEVELS(31)，default_selected 复刻(80-81) |
| GUI 冒烟入口 | `app/ui/main_window.py:190-194, 233-246` | `--screenshot` + `--tab` |
| 测试夹具 | `tests/conftest.py:10-72` | `nfo_xml`/`make_movie`/`build_env` |
| 待修订测试 1 | `tests/test_scanner.py:55-64` | `test_complex_dir_excluded` 钉"排除"旧语义 |
| 待修订测试 2 | `tests/test_viewmodel.py:16-40` | `make_unit` 复刻 default_selected 规则(24-26) |

**测试基线**：`def test_` 静态计数 **197**（17 个文件：test_viewmodel 27、test_config_tab 20、test_config 17、test_nfo 15、test_scanner 14、test_classifier 14、test_plan_tab 16、test_flow 12、test_exec_tab 11、test_doctor_tab 11、test_learned 9、test_fsops 8、test_paths 6、test_planner 6、test_journal 5、test_entry 3、test_state 3）。Task-00 以 collect-only 实测回填（前一计划记录"收尾=196"与现状差 1，以实测为准）。

---

## 1. 设计决策（实施者必须照此执行，不得自行变更）

- **DA1（A-容错）**：数字开头元素重写只作为容错链**第 4 级**（前三级全失败才走）；正常 NFO 零接触。`recovery` 字段对三级容错统一记录，但 scanner 告警只认 `parse_error`（行为：15 类单元告警消失，既有裸 & 单元从"无告警"变"无告警+证据行"，无回归面）。
- **DA2（A-provider）**：裸 id 元素 = 无属性 + 名以 id 结尾 + 名长>2 + 文本非空；scheme = 去尾 id 后 casefold；显式 uniqueid/id 属性条目优先（暂存 dict + 循环后 setdefault 合并）。provider 优先级链不改。
- **DB1（B-配置）**：独立 `[weak_genre_aliases]` 表（驳回"值带语法"方案：三处微语法回归面大）；强表同名键胜出，不做跨表互斥校验。
- **DB2（B-裁决）**：候选集 = 强命中集，空则弱命中集——弱与强**结构上不同台**，"弱不压强"不需要比较逻辑；弱候选内部仍走优先级表/票数（rule_pick 复用）。弱 rule 单元 conf="low"；planner default_selected 增补 `conf != "low"` 门。
- **DC1（C-单元）**：复合目录 = 一个 dir 单元（composite=True），level="composite"，status=ST_BATCH，目标恒占位兜底库，**即使翻出带题材 NFO 也永不自动执行**。
- **DC2（C-口径）**：`stats["composite"]` 按单元字段计数（不随状态漂移）；`fallback_ratio = fb / (total − composite)`，`build_plan` 与 `_refresh_stats` 两处同步；`mark_undone` 复合单元回 ST_BATCH（修既有潜在 bug，钉回归）。
- **DC3（C-执行）**：执行门槛 = "READY，或 ST_BATCH 且带 override"；freshness/preflight 磁盘/长路径的放行集 = (READY, ST_BATCH)；整目录 `transfer_dir`、目录名不变、learned 因 genres=[] 天然空转（显式钉测试防未来回归）。
- **DD1（D-词表）**：`score_title` 词表 = 强别名 ∪ 弱别名 ∪ 库自身名，`normalize_key` 归一后子串计数，键长 <2 跳过；**不做长度归一**（score_plot 的 len**0.5 在短文本放大分数，显式不复用）。
- **DD2（D-位置）**：title_pick 只插在两个兜底分支的 fallback 之前、soft_hits 之后；plot 评分/多候选择优/规则命中路径零接触。conf 恒 low；planner 无需改（title 级不在 default_selected 规则内）。
- **DD3（D-门槛）**：30 例抽样精度 ≥80% 保留，否则 owner 置 `title.enabled=false`（不新增"仅展示"模式开关——low+默认不选已是该语义）。
- **DU1（UI）**：viewmodel 保持零 Qt；plan_tab 只做渲染与转发；批量改判 = viewmodel `set_override_many` + 薄对话框；徽章配色键 "batch"（整目录）与 "title" 复用现有色板（WARN/PLOT），不新增色值。

---

## 2. 签名与形状变更总表（验收时逐条比对）

| 符号 | 现状 | 变更 | 兼容性 |
|---|---|---|---|
| `NfoInfo`（nfo.py:33-42） | 无 recovery | + `recovery: str = ""` | 默认值，全兼容 |
| `parse_nfo_text` | 3 级容错 | 追加第 4 级（数字开头重写），签名不变 | 行为追加 |
| `_fill_from_xml` / `_fill_from_regex` | 无裸 id | 各加裸 id 暂存收集，签名不变 | 行为追加 |
| `Config`（config.py:70-84） | — | + `weak_genre_aliases: dict[str,str] = field(default_factory=dict)`、`title: TitleOptions = field(default_factory=TitleOptions)` | load_config 显式构造，旧配置零迁移 |
| 新增 `TitleOptions` | — | `(enabled: bool = True, min_score: float = 1.0)`，锚点 config.py:56-60 PlotOptions 旁 | 新增 |
| `config_hash`（config.py:93-103） | 无 weak/title | payload + `weak_genre_aliases`(排序) + `title` 两键 | 旧 plan.json 失效→重扫即愈（预期） |
| `alias_map` / `map_genres` | — | **签名不变**；新增 `weak_alias_map(cfg)`、`map_genres_ex(cfg, genres) -> (strong, weak, unmapped)`；`map_genres` 变 wrapper | planner.py:82 零改动 |
| 新增 `score_title` | — | `(text: str, cfg: Config) -> list[tuple[str, float, list[str]]]` | 新增 |
| `classify` | — | 签名不变；弱降级 + title_pick 插入；强命中路径逐字节不变 | 行为追加 |
| `LEVEL_*`（classifier.py:18-24） | 4 级 | + `LEVEL_TITLE = "title"`，LEVEL_LABELS + "标题预判" | 追加 |
| planner 常量（:23-35） | 6 状态 | + `ST_BATCH = "batch_target"`、STATUS_LABELS["batch_target"]="整目录待改判" | 追加（table_cells.STATUS_BADGES 同步加键） |
| planner 统计 | `fb/total` | `fb/(total−composite)` + `stats["composite"]` | 口径修正 |
| `Unit`（scanner.py:57-75） | — | + `composite: bool = False` | 默认值 |
| `check_plan_freshness`（:219-220） | 仅 READY | 放行 `(READY, ST_BATCH)` | 收紧为更安全 |
| `run_preflight` | 签名不变 | 磁盘(:83-84)/长路径(:121-124)过滤含 ST_BATCH | 行为追加 |
| `run_apply` | 签名不变 | 状态门(:147-149)放行"ST_BATCH 且有 override" | 行为追加 |
| `PlanViewModel` | — | + `set_override_many(ids, lib)`；`checked_not_ready` 放行"ST_BATCH+有 override"；LEVEL_FILTERS/LEVEL_BADGES + "composite"/"title" | 追加 |
| `describe/raw_describe/dump_config_text` | — | + weak_genre_aliases、title 三处 | GUI 保存往返必需 |

---

## 3. 任务板（顺序 = 派卡顺序；同文件多卡时区域互不重叠、 strictly 串行派卡）

> 每任务收尾必须跑该任务验证命令且全绿 + `python -m ruff check <本卡改动文件>` 0 项。新增测试 70 个（4+5+3+6+7+4+6+9+5+7+5+9），修订 2 处（Task-05/09，已注明批准依据）。

### Task-00 基线复核（开工前 2 分钟）

- [ ] 运行 `python -m pytest --collect-only -q 2>&1 | tail -3`，把实测总数写进本文件末尾「实施记录」（`基线=N`；预期 ≈197）。
- [ ] 验收：数字已回填；收口时断言 `新总数 ≥ N + 70`。

---

### Task-01 nfo：数字开头元素重写 + recovery 语义（特性 A-1，bug fix）

- 文件：`app/core/nfo.py`（Modify：33-42 / 17-30 / 166-207）、`app/core/planner.py`（Modify：118-119 一行扩展）、`tests/test_nfo.py`（Test：末尾追加）、`tests/test_planner.py`（Test：末尾追加 1 个）
- 操作：修改 + 新增测试
- 接口：Consumes 现有容错链（nfo.py:166-195）；Produces `NfoInfo.recovery: str`、第 4 级容错、planner 证据行
- 依赖：无

步骤：
- [ ] 1. nfo.py:29（`_STRIP_TAGS` 旁）新增 `_RE_DIGIT_TAG = re.compile(r"<(/?)(\d[^\s>/]*)")`；NfoInfo（:42 `parse_error` 之后）加字段 `recovery: str = ""`。
- [ ] 2. `parse_nfo_text`（:183-195 的第 3 级失败后、`if root is not None` 之前）插入第 4 级：

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

- [ ] 3. 既有三级容错补 recovery 标记（行为兼容： movie 块截取 → `info.recovery = "截取 movie 块"`；裸 & 转义 → `info.recovery = "转义裸 &"`；**不**新增告警，`parse_error` 语义不变——仍仅 regex 模式非空）。
- [ ] 4. planner.py:118 `"evidence": dec.evidence,` 改为 `"evidence": list(dec.evidence) + ([f"NFO 已容错恢复：{u.nfo.recovery}"] if (u.nfo and u.nfo.recovery) else []),`。
- [ ] 5. `tests/test_nfo.py` 末尾新增 4 个测试：

  | 测试名 | 输入 | 断言 |
  |---|---|---|
  | `test_digit_leading_tag_recovers_via_xml` | `<movie><title>T</title><genre>动作</genre><plot>p</plot><7mmtvid>wKV281</7mmtvid></movie>` | `parse_mode=="xml"`；`parse_error is None`；genres/title/plot 逐字段正确 |
  | `test_digit_tag_recovery_recorded` | 同上 | `info.recovery` 含 `"数字开头"` |
  | `test_digit_rewrite_leaves_wellformed_untouched` | `nfo_xml()` 正常文本 | `parse_mode=="xml"` 且 `recovery == ""` 且 parse_error None（零行为变化） |
  | `test_digit_tag_xml_and_regex_paths_agree` | 同测试 1 文本，分别走 `parse_nfo_text`（新路径）与手工 `_fill_from_regex(NfoInfo(), text)` | genres/title/plot 三字段相等（信息零丢失） |

- [ ] 6. `tests/test_planner.py` 末尾新增 `test_plan_evidence_notes_recovery`：`make_movie` 后把 movie.nfo 内容替换为含 `<7mmtvid>x</7mmtvid>` 的变体 → `build_plan` 该单元 `evidence` 存在以 `"NFO 已容错恢复"` 开头的行。
- [ ] 7. 验证：`python -m ruff check app/core/nfo.py app/core/planner.py` 0 项；`python -m pytest tests/test_nfo.py tests/test_planner.py -q` 全绿（15+6 现有 + 新 5）。

---

### Task-02 nfo：裸 id 元素纳入 provider id（特性 A-2，bug fix）

- 文件：`app/core/nfo.py`（Modify：24-30 正则区 / 112-135 / 138-163）、`tests/test_nfo.py`（Test：末尾追加）
- 操作：修改 + 新增测试
- 接口：Consumes uniqueids dict（nfo.py:39）；Produces 裸 id → `uniqueids[scheme]` → `provider_id`
- 依赖：Task-01（同文件串行）

步骤：
- [ ] 1. 正则区（:29 附近）新增 `_RE_BARE_ID_TAG = re.compile(r"<([A-Za-z][A-Za-z0-9_]*id)>([^<]*)</\1\s*>", re.I)`（只匹配无属性裸 id 元素；带属性 uniqueid/id 不命中）。
- [ ] 2. `_fill_from_xml`（:112-135）：循环前 `bare_ids: dict[str, str] = {}`；循环内新增分支（置于 `t == "uniqueid"` / `t == "id"` 两分支**之后**）：

  ```python
  elif t.endswith("id") and len(t) > 2 and not el.attrib and text:
      scheme = t[:-2].lower()
      if scheme:
          bare_ids.setdefault(scheme, text)
  ```

  循环后（:134 去重之前）`for s, v in bare_ids.items(): info.uniqueids.setdefault(s, v)`（显式条目优先）。
- [ ] 3. `_fill_from_regex`（:156-163 附近）末尾追加：

  ```python
  for m in _RE_BARE_ID_TAG.finditer(text):
      name, val = m.group(1), m.group(2).strip()
      scheme = name[:-2].lower() if len(name) > 3 else ""
      if scheme and val:
          info.uniqueids.setdefault(scheme, val)
  ```

- [ ] 4. `tests/test_nfo.py` 末尾新增 5 个测试：

  | 测试名 | 输入 | 断言 |
  |---|---|---|
  | `test_bare_javdbid_becomes_provider` | `<movie><title>T</title><genre>动作</genre><javdbid>wKV281</javdbid></movie>` | `uniqueids == {"javdb": "wKV281"}`；`provider_id == "javdb:wKV281"` |
  | `test_bare_tmdbid_merges_scheme` | `<movie><tmdbid>42</tmdbid></movie>` | `provider_id == "tmdb:42"` |
  | `test_uniqueid_attr_beats_bare_id` | `<uniqueid type="tmdb">1</uniqueid><tmdbid>2</tmdbid>` | `uniqueids["tmdb"] == "1"` |
  | `test_bare_id_regex_path` | 破损文本 `<movie><genre>恐怖</genre><javdbid>wKV281</javdbid>`（regex 模式） | `parse_mode=="regex"` 且 `uniqueids == {"javdb": "wKV281"}` |
  | `test_bare_id_ignores_empty_and_plain_id` | `<movie><id>plain</id><javdbid></javdbid></movie>` | `uniqueids == {}`（无 "" scheme、空值跳过） |

- [ ] 5. 验证：`python -m ruff check app/core/nfo.py` 0 项；`python -m pytest tests/test_nfo.py -q` 全绿（15+4+5）。

---

### Task-03 scanner：容错恢复 flag 与告警语义（特性 A-3）

- 文件：`app/core/scanner.py`（Modify：171-174）、`tests/test_scanner.py`（Test：末尾追加）
- 操作：修改 + 新增测试
- 接口：Consumes `NfoInfo.recovery/parse_error`（Task-01）；Produces flags `nfo_recovered`（新）与 `nfo_parse_warning`（语义收窄：仅硬失败）
- 依赖：Task-01

步骤：
- [ ] 1. scanner.py:171-174 改为：

  ```python
  nfo_path = find_nfo(d, vids, multi_cd)
  info = parse_nfo_file(nfo_path) if nfo_path else None
  if info and info.parse_error:
      flags.append("nfo_parse_warning")
  elif info and info.recovery:
      flags.append("nfo_recovered")
  ```

  （扫描告警 note :244-246 只认 parse_error，**不改**——恢复类单元不再出 warn note 即为修复目标。）
- [ ] 2. `tests/test_scanner.py` 末尾新增 3 个测试（用 `build_env`+`make_movie`，NFO 内容手工替换）：

  | 测试名 | 步骤 | 断言 |
  |---|---|---|
  | `test_recovered_nfo_flags_without_warning` | movie.nfo 含 `<7mmtvid>x</7mmtvid>` | 单元 flags == `["nfo_recovered"]`；scan notes 无该 path 的 warn |
  | `test_broken_nfo_keeps_warning` | movie.nfo 为残片 `<movie><genre>恐怖</genre>` | flags 含 `nfo_parse_warning`；notes 有同 path warn |
  | `test_clean_nfo_has_no_nfo_flags` | 正常 nfo_xml | flags == [] |

- [ ] 3. 验证：`python -m ruff check app/core/scanner.py` 0 项；`python -m pytest tests/test_scanner.py -q` 全绿（14 现有 + 3）。

---

### Task-04 config：weak_genre_aliases 配置层（特性 B-1）

- 文件：`app/core/config.py`（Modify：70-84 / 93-103 / 195-200 后 / 251-265 / 270-291 / 294-326 / 329-365）、`tests/test_config.py`（Test：末尾追加）
- 操作：修改 + 新增测试
- 接口：Consumes TOML `[weak_genre_aliases]`；Produces `Config.weak_genre_aliases` + 校验 + describe/raw_describe/dump 往返 + config_hash 纳入
- 依赖：无

步骤：
- [ ] 1. `Config`（:76 之后）加字段 `weak_genre_aliases: dict[str, str] = field(default_factory=dict)`。
- [ ] 2. `load_config`：genre_aliases 校验块（:195-200）后镜像一段——读 `data.get("weak_genre_aliases") or {}`，值必须是已定义库，否则 `ConfigError(f"weak_genre_aliases[{k!r}] 指向未定义的库：{v}")`；返回值（:251-265）传入。
- [ ] 3. `config_hash`（:94-101）payload 加 `"weak_genre_aliases": dict(sorted(self.weak_genre_aliases.items()))`。
- [ ] 4. `describe`（:289 后）加 `"weak_genre_aliases": dict(cfg.weak_genre_aliases)`；`raw_describe`（:324 后）加 `{str(k): str(v) for k, v in (data.get("weak_genre_aliases") or {}).items()}`。
- [ ] 5. `dump_config_text`（:343-344 之后）加：

  ```python
  weak_items = [f"{js(k)} = {js(v)}" for k, v in (d.get("weak_genre_aliases") or {}).items()]
  lines.append("weak_genre_aliases = { " + ", ".join(weak_items) + " }")
  ```

- [ ] 6. `tests/test_config.py` 末尾新增 6 个测试（沿用 `build_env`，overrides 传 `"weak_genre_aliases": {"护士": "动作"}` 形状）：

  | 测试名 | 步骤 | 断言 |
  |---|---|---|
  | `test_weak_genre_aliases_loaded` | build_env(overrides={weak 表}) → load_config | `cfg.weak_genre_aliases == {"护士": "动作"}` |
  | `test_weak_alias_unknown_lib_rejected` | weak 值指向未定义库 `{"护士": "不存在"}` → 写 toml → load_config | 抛 `ConfigError`，文案含 `"weak_genre_aliases"` |
  | `test_weak_alias_defaults_empty` | build_env()（无 weak 节） | `cfg.weak_genre_aliases == {}` |
  | `test_dump_round_trips_weak_aliases` | `describe(cfg)` → `dump_config_text` → `load_config`（写临时文件） | weak 表逐键相等（GUI 保存不丢） |
  | `test_describe_and_raw_describe_include_weak` | 两函数输出 | 键 `weak_genre_aliases` 存在且形状 dict |
  | `test_config_hash_changes_with_weak` | 两个 cfg 仅 weak 表不同 | `config_hash()` 不相等 |

- [ ] 7. 验证：`python -m ruff check app/core/config.py` 0 项；`python -m pytest tests/test_config.py -q` 全绿（17 现有 + 6）。

---

### Task-05 classifier+planner：弱标签裁决语义（特性 B-2，含 1 处测试修订）

- 文件：`app/core/classifier.py`（Modify：37-58 / 95-201）、`app/core/planner.py`（Modify：132-134）、`tests/test_classifier.py`、`tests/test_planner.py`（Test：各自末尾追加）、`tests/test_viewmodel.py`（**修订**：24-26 复刻规则，owner 批准依据 = 规格 §3.2 default_selected 语义变更）
- 操作：修改 + 新增测试 + 1 处测试修订
- 接口：Consumes `cfg.weak_genre_aliases`（Task-04）；Produces `weak_alias_map`、`map_genres_ex`、弱 rule/low Decision、default_selected 门
- 依赖：Task-04

步骤：
- [ ] 1. classifier.py:43 后新增：

  ```python
  def weak_alias_map(cfg: Config) -> dict[str, str]:
      """弱别名归一键 → 库名（弱信号：唯一命中时降级，永不压过强命中）。"""
      return {normalize_key(k): v for k, v in cfg.weak_genre_aliases.items()
              if v in cfg.libraries}
  ```

- [ ] 2. `map_genres_ex(cfg, genres) -> tuple[list[str], list[str], list[str]]`（返回强命中库、弱命中库、未映射题材；强表同名键胜出——先查 `alias_map` 再查 `weak_alias_map`）；`map_genres`（:46-58）改为 `s, _w, u = map_genres_ex(...); return s, u`（签名/返回不变，planner.py:82 零改动）。
- [ ] 3. `classify`（:100）改用 `mapped_s, mapped_w, unmapped = map_genres_ex(cfg, genres)`；`mapped = mapped_s + [w for w in mapped_w if w not in mapped_s]`（保序去重）。
- [ ] 4. `rule_pick`（:151-176）改造：`candidates = mapped_s or mapped_w`；`weak_only = bool(mapped_w) and not mapped_s`；winner 在 candidates 内按既有 `_rank`/票数/声明序裁决（:154-155 的 min 键不改，把 `mapped` 换成 `candidates`）；`conf = "low" if weak_only else "high"`（:176）；`weak_only` 时 reason 追加 `（弱标签）`，evidence 追加 `弱标签『{触发题材}』→ {winner}（弱信号，默认不勾选）`。`smart` 多候选择优分支（:186-191）判定用 `len(mapped) > 1` 保持不变（强弱并存时行为与现状一致）。
- [ ] 5. planner.py:132-134 改为：

  ```python
  "default_selected": status == READY and (
      (dec.level == "rule" and dec.confidence != "low")
      or (dec.level == "learned" and dec.confidence == "medium")),
  ```

- [ ] 6. `tests/test_viewmodel.py` **修订**（唯一授权改动点）：`make_unit` 的 :24-26 复刻规则同步补 `and conf != "low"`，docstring（:22）补一句"弱规则（low）不默认勾选"。该文件现有 27 个测试**不改不删**。
- [ ] 7. `tests/test_classifier.py` 末尾新增 6 个测试（cfg 用 `build_env`，overrides 注入 `genre_aliases`/`weak_genre_aliases`/`genre_priority`）：

  | 测试名 | 输入 | 断言 |
  |---|---|---|
  | `test_weak_only_single_hit_low_confidence` | 单元 genres=("护士",)，weak `护士→动作` | `dec.level=="rule"`；`dec.confidence=="low"`；`dec.target=="动作"`；evidence 有行含 `"弱标签"` |
  | `test_weak_cannot_beat_strong` | genres=("护士","Sci-Fi")，weak 护士→动作，强 Sci-Fi→科幻，genre_priority=["动作","科幻"]（动作在前） | winner=科幻（强胜出，优先级顺序不影响）；conf=="high" |
  | `test_multiple_weak_candidates_use_priority` | weak `护士→动作`、`空姐→科幻`，genres 两者，priority=["科幻","动作"] | winner=科幻（弱候选内部按优先级）；conf=="low" |
  | `test_strong_only_unchanged` | 强别名唯一命中（现有 build_env 默认） | conf=="high"，evidence 无"弱标签"行（回归钉） |
  | `test_same_lib_strong_and_weak_not_demoted` | 强 `Sci-Fi→科幻` + 弱 `sf2→科幻`，genres=("Sci-Fi","sf2") | conf=="high"（同库强弱并存视为强） |
  | `test_map_genres_ex_shapes` | 混合强/弱/未映射 genres | `(strong, weak, unmapped)` 三段内容与顺序正确；`map_genres` 返回值与旧契约一致 |

- [ ] 8. `tests/test_planner.py` 末尾新增 `test_plan_weak_rule_not_selected`：weak-only 单元走完整 `build_plan` → `level=="rule"`、`confidence=="low"`、`default_selected is False`、`stats.ready_levels["rule"]` 含 1（不进 fallback）。
- [ ] 9. 验证：`python -m ruff check app/core/classifier.py app/core/planner.py tests/test_viewmodel.py` 0 项；`python -m pytest tests/test_classifier.py tests/test_planner.py tests/test_viewmodel.py -q` 全绿（14+6+6+27 现有 + 新 7）。

---

### Task-06 config GUI：弱别名表编辑框（特性 B-3）

- 文件：`app/ui/config_viewmodel.py`（Modify：23-55 / 58-112）、`app/ui/config_tab.py`（Modify：94-96 旁 / 116 / 196 区域禁用清单 / 258-262 演示禁用）、`tests/test_config_tab.py`（Test：末尾追加）
- 操作：修改 + 新增测试
- 接口：Consumes `describe.weak_genre_aliases`（Task-04）；Produces 表单字段 `weak_alias_text` 往返
- 依赖：Task-04

步骤：
- [ ] 1. `describe_to_form`（:52-53 后）加 `"weak_alias_text": "\n".join(f"{k}={v}" for k, v in (desc.get("weak_genre_aliases") or {}).items())`。
- [ ] 2. `form_to_body`（:60-67 旁复用同解析循环）解析 `weak_alias_text` → body 加 `"weak_genre_aliases": weak_aliases`（:110 旁）。
- [ ] 3. config_tab.py：:94-96 旁新增 `self.f_weak_alias_text = QPlainTextEdit()`（`setFixedHeight(72)`、placeholder `"每行：别名=标准库名（弱信号：唯一命中时低置信、默认不勾选）"`）；`rows`（:116）在 ("别名表", …) 后加 `("弱别名表", self.f_weak_alias_text)`；三处控件枚举清单（:196 区域、:258-262 演示禁用、表单回填 :301 旁 `setPlainText(form["weak_alias_text"])`、聚合 :352 旁 `"weak_alias_text": self.f_weak_alias_text.toPlainText()`）逐一接线。
- [ ] 4. `tests/test_config_tab.py` 末尾新增 4 个测试：

  | 测试名 | 步骤与断言 |
  |---|---|
  | `test_weak_alias_form_round_trip` | `describe_to_form(desc)` 产生 `weak_alias_text`；`form_to_body(form, rows)["weak_genre_aliases"]` 还原 dict（含值解析、忽略空行/无 `=` 行） |
  | `test_weak_alias_textarea_populated` | 真实 `build_env` 配置（weak 含 护士=动作）驱动 ConfigTab → `f_weak_alias_text.toPlainText()` 含 `"护士=动作"` |
  | `test_weak_alias_edit_flows_to_body` | 手工 `setPlainText("护士=动作\n\n坏行")` → `tab._collect_form()`（或该页现行的聚合入口）→ body weak 表 `== {"护士": "动作"}` |
  | `test_demo_mode_disables_weak_alias_box` | `ConfigTab(None, …)` → `f_weak_alias_text.isEnabled() is False` |

- [ ] 5. 验证：`python -m ruff check app/ui/config_viewmodel.py app/ui/config_tab.py` 0 项；`python -m pytest tests/test_config_tab.py -q` 全绿（20 现有 + 4）。

---

### Task-07 config：[title] 配置节 + GUI 镜像组（特性 D-2）

- 文件：`app/core/config.py`（Modify：56-60 旁 / 70-84 / 93-103 / 202-209 后 / 251-265 / 270-291 / 294-326 / 346-350 后）、`app/ui/config_viewmodel.py`（Modify：23-55 / 92-112）、`app/ui/config_tab.py`（Modify：plot 行区 / 禁用清单）、`tests/test_config.py`、`tests/test_config_tab.py`（Test：末尾追加）
- 操作：修改 + 新增测试
- 接口：Consumes TOML `[title]`；Produces `TitleOptions` + 往返 + hash
- 依赖：Task-04（同文件串行；与 Task-06 无重叠区域）

步骤：
- [ ] 1. PlotOptions（:56-60）旁新增 `@dataclass class TitleOptions: enabled: bool = True; min_score: float = 1.0`；`Config` 加字段 `title: TitleOptions = field(default_factory=TitleOptions)`。
- [ ] 2. `load_config`：plot 解析块（:202-209）后镜像——`title_data = data.get("title") or {}`，`enabled=bool(title_data.get("enabled", True))`、`min_score=float(title_data.get("min_score", 1.0))`；`min_score < 0` → `ConfigError("title.min_score 不能为负数")`；返回值传入。
- [ ] 3. `config_hash` payload 加 `"title": {"enabled": self.title.enabled, "min_score": self.title.min_score}`。
- [ ] 4. `describe`/`raw_describe` 加 `"title": {"enabled": …, "min_score": …}`（默认 True/1.0）；`dump_config_text` 在 `[plot]` 块（:346-350）后加 `[title]` 两行（enabled/min_score，与 plot 同格式）。
- [ ] 5. config_viewmodel：`describe_to_form` 加 `title_enabled`/`title_min_score`；`form_to_body` 加 `"title": {"enabled": bool(...), "min_score": float(...)}`。
- [ ] 6. config_tab：plot 三控件行区镜像 `title` 复选框 + 阈值输入（属性名 `f_title_enabled`/`f_title_min_score`），回填/聚合/演示禁用/`_set_form_enabled` 清单接线（照 plot 三件的现成接线逐处镜像）。
- [ ] 7. `tests/test_config.py` 新增 5 个：`test_title_options_loaded_defaults`（无节 → True/1.0）、`test_title_min_score_negative_rejected`（-0.5 → ConfigError 含 `"title.min_score"`）、`test_dump_round_trips_title`（GUI 保存往返不丢）、`test_describe_raw_describe_title`（两形状含 title dict）、`test_config_hash_changes_with_title`（仅 title 不同 → hash 不同）。
- [ ] 8. `tests/test_config_tab.py` 新增 1 个：`test_title_form_round_trip`（describe_to_form → 控件回填 → 聚合 → form_to_body → body["title"] 相等）。
- [ ] 9. 验证：`python -m ruff check app/core/config.py app/ui/config_viewmodel.py app/ui/config_tab.py` 0 项；`python -m pytest tests/test_config.py tests/test_config_tab.py -q` 全绿（23+24 现有 + 6）。

---

### Task-08 classifier：score_title + 决策链插入（特性 D 核心）

- 文件：`app/core/classifier.py`（Modify：18-24 / 61-85 后新增 / 178-201）、`app/ui/viewmodel.py`（Modify：21 / 26-31）、`tests/test_classifier.py`、`tests/test_viewmodel.py`（Test：末尾追加）
- 操作：修改 + 新增测试
- 接口：Consumes `cfg.title`（Task-07）+ 别名/弱别名/库名词表（Task-04/05）；Produces `score_title`、`LEVEL_TITLE`、title_pick 决策
- 依赖：Task-05、Task-07

步骤：
- [ ] 1. :20 附近加 `LEVEL_TITLE = "title"`；LEVEL_LABELS（:23-24）加 `"title": "标题预判"`。
- [ ] 2. score_plot（:85）后新增：

  ```python
  def score_title(text: str, cfg: Config) -> list[tuple[str, float, list[str]]]:
      """标题弱评分：别名∪弱别名∪库名 词表子串计数。无长度归一（短文本
      不复用 score_plot 的 len**0.5，会放大短文本分数）。返回 [(库, 分, 命中)] 降序。"""
      t = normalize_key(text)
      if not t:
          return []
      vocab: dict[str, str] = {}
      for name in cfg.libraries:
          vocab.setdefault(normalize_key(name), name)
      for m_ in (alias_map(cfg), weak_alias_map(cfg)):
          for k, v in m_.items():
              if len(k) >= 2:
                  vocab.setdefault(k, v)
      results = []
      for key, lib in vocab.items():
          n = t.count(key)
          if n:
              results.append((lib, float(n), [f"{key}×{n}"]))
      agg: dict[str, float] = {}
      hits: dict[str, list[str]] = {}
      for lib, s, h in results:
          agg[lib] = agg.get(lib, 0.0) + s
          hits.setdefault(lib, []).extend(h)
      return sorted(((l, s, hits[l]) for l, s in agg.items()),
                    key=lambda x: (-x[1], x[0]))
  ```

  （实现可按此语义微调结构，但**签名、无长度归一、键长<2 跳过、命中明细格式**四点不得偏离。）
- [ ] 3. `classify`：`title_scoring = score_title(" ".join(x for x in ((nfo.title if nfo else "") or "", getattr(unit, "title", "") or "") if x), cfg) if cfg.title.enabled else []`（置于 :116 `scoring` 之后）；`fallback()`（:119-132）签名改 `fallback(reason, title_ok=True)`：`title_ok and cfg.title.enabled and title_scoring and title_scoring[0][1] >= cfg.title.min_score` 时返回 title_pick 而非兜底——title_pick 内联构造：`Decision(name, str(cfg.libraries[name].path), LEVEL_TITLE, f"标题弱命中『{name}』{sc:g} 分（低置信，默认不勾选）", [f"标题命中：{h}" for h in hits[:8]], "low")`；两处 fallback 调用点（:183、:201）保持"最后手段"语义。**强/弱规则命中、plot 达标、learned 命中路径全部不经过 title**（:185-192、:195-200 不动）。
- [ ] 4. viewmodel.py:21 `LEVEL_FILTERS = ("rule", "plot", "learned", "fallback", "title")`；LEVEL_BADGES（:26-31）加 `"title": ("标题预判", "plot")`（复用 plot 紫色，不新增色值）。
- [ ] 5. `tests/test_classifier.py` 新增 8 个：

  | 测试名 | 步骤与断言 |
  |---|---|
  | `test_score_title_counts_alias_hits` | weak `マジックミラー号→科幻库`（建名"科幻"的库），text 含该词 → 首项 `(科幻, ≥1.0, hits)`，hits 含词×次数 |
  | `test_score_title_no_length_normalization` | 20 字短文本命中 1 次 → score 恰为 1.0（不被 len**0.5 放大） |
  | `test_score_title_skips_short_keys` | 构造单键长 1（如库名 "P" 或弱别名 "P"）→ 不产生命中 |
  | `test_title_pick_no_genres` | 无 genres、无 plot、标题含别名词 → `level=="title"`、`confidence=="low"`、reason 含 `"标题"` |
  | `test_title_pick_after_soft_learned` | 无 genres + learned 软建议存在（votes=1）+ 标题命中 → 仍 `learned`（title 不越位） |
  | `test_title_never_overrides_rule` | 强规则命中 + 标题含他库词 → 目标=规则库；evidence 无 `"标题命中"` 行 |
  | `test_title_disabled_by_config` | `title.enabled=False` → 同输入走 fallback |
  | `test_title_evidence_label_distinct` | plot 单元 evidence 首行前缀 `"摘要命中"`；title 单元 `"标题命中"` |

- [ ] 6. `tests/test_viewmodel.py` 新增 1 个：`test_title_badge_and_filter`（`LEVEL_BADGES["title"]` 存在；`set_filter("title")` 后 rows 只含 title 单元）。
- [ ] 7. 验证：`python -m ruff check app/core/classifier.py app/ui/viewmodel.py` 0 项；`python -m pytest tests/test_classifier.py tests/test_viewmodel.py -q` 全绿（20+28 现有 + 9）。

---

### Task-09 scanner：复合目录 → 整目录单元（特性 C-1，含 1 处测试修订）

- 文件：`app/core/scanner.py`（Modify：57-75 加字段 / 162-164）、`tests/test_scanner.py`（**修订** :55-64 + 末尾追加 4 个）
- 操作：修改 + 新增测试 + 1 处测试修订
- 接口：Consumes `_analyze_dir` 既有 mains/bases 逻辑；Produces `Unit.composite`、flags `["composite"]`、info 级扫描 note
- 依赖：Task-03（同文件串行）

步骤：
- [ ] 1. `Unit`（:66 `disc` 后）加字段 `composite: bool = False`。
- [ ] 2. :162-164 的 `return None, {"level": "excluded", …}` 改为：

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

  （既有 mains 过滤 :151-153、RE_MULTI_CD 分组 :157-161、disc 判定不动；后续正常路径 :165-166 的 `vids/multi_cd` 逻辑保持。）
- [ ] 3. **修订** `tests/test_scanner.py::test_complex_dir_excluded`（:55-64）→ 更名 `test_complex_dir_becomes_batch_unit`：同输入断言 `len(units)==1`、`units[0].composite is True`、`units[0].kind=="dir"`、`"composite" in units[0].flags`、notes 无 `level=="excluded"` 且有 `level=="info"` 且 reason 含 `"复合目录"`。（批准依据：owner 拍板 1 + 规格 §4.1；旧"排除"语义废止。）
- [ ] 4. 新增 4 个测试：

  | 测试名 | 步骤与断言 |
  |---|---|
  | `test_composite_unit_covers_whole_dir` | 目录内 2 base 各 1 视频 + 海报 jpg → `file_count`/`files` 覆盖全部文件；`videos` 为 mains 排序 |
  | `test_composite_with_nfo_still_batch` | 复合目录 + movie.nfo（正常 XML）→ 仍 `composite=True`、单元有 nfo/provider，**不**拆分 |
  | `test_composite_no_split_on_c_variant` | `[ABC-1].mp4` 与 `[ABC-1-C].mp4` 两 base → 1 个 composite 单元（钉"不拆分"红线） |
  | `test_supplement_dirs_not_composite` | 既有 `Film - Behind The Scenes` 子目录场景 → 非 composite（RE_SUPPLEMENT 回退保护回归钉） |

- [ ] 5. 验证：`python -m ruff check app/core/scanner.py` 0 项；`python -m pytest tests/test_scanner.py -q` 全绿（17+3 现有 + 新 4，修订 1 处改名不減数）。

---

### Task-10 planner：ST_BATCH / 统计口径 / 撤销修复（特性 C-2 核心）

- 文件：`app/core/planner.py`（Modify：23-35 / 72-140 / 142-155 旁 / 157-179 / 242-252 / 269-279）、`app/ui/viewmodel.py`（Modify：21 / 26-31 / 188-194）、`tests/test_planner.py`、`tests/test_viewmodel.py`（Test：末尾追加）
- 操作：修改 + 新增测试
- 接口：Consumes `Unit.composite`（Task-09）；Produces `ST_BATCH`、level="composite"、`stats["composite"]`、口径修正、`mark_undone` 修复、viewmodel 门禁语义
- 依赖：Task-05、Task-09

步骤：
- [ ] 1. :27 后加 `ST_BATCH = "batch_target"`；STATUS_LABELS（:32-35）加 `ST_BATCH: "整目录待改判"`。
- [ ] 2. `build_plan` 循环（:76-140）：循环首加 `is_composite = getattr(u, "composite", False)`；classify 照跑（占位证据）后，复合单元覆写 `status = ST_BATCH`（初值，冲突检测 :84-104 可再覆写为更硬状态）、`level = "composite"`；单元 dict（:106-140）加 `"composite": is_composite`；`"level": "composite" if is_composite else dec.level`；`default_selected`（:132-134）对复合单元恒 False（`and not is_composite`）。
- [ ] 3. 多版本分组（:144-146）条件已是 READY-only，复合单元天然排除——**加一行断言注释**即可，不改逻辑。
- [ ] 4. 统计（:157-179）：`composite_count = sum(1 for pu in plan_units if pu["composite"])`；stats 加 `"composite": composite_count`；:175 改 `denom = total - composite_count; "fallback_ratio": (fb / denom) if denom else 0.0`。`_refresh_stats`（:242-252）同步同口径（`composite` 按 `pu.get("composite")` 计数）。
- [ ] 5. `mark_undone`（:277）改 `pu["status"] = ST_BATCH if pu.get("composite") else READY`。
- [ ] 6. viewmodel.py：LEVEL_FILTERS 加 `"composite"`（接 Task-08 的 title 之后）；LEVEL_BADGES 加 `"composite": ("整目录", "rule")`；`checked_not_ready`（:188-191）改：

  ```python
  def _executable(self, u: dict) -> bool:
      if u["status"] == READY:
          return True
      return u["status"] == ST_BATCH and bool(self.overrides.get(u["id"]))
  ```

  `checked_not_ready` 返回 `_executable` 为 False 的勾选单元；`can_apply`（:193-194）复用 `_executable`；顶部 import 加 `ST_BATCH`。
- [ ] 7. `tests/test_planner.py` 新增 6 个（复合单元用 `make_movie`×2 base 构造）：

  | 测试名 | 断言 |
  |---|---|
  | `test_plan_composite_status_and_level` | status==ST_BATCH、level=="composite"、default_selected False、target_lib=="兜底库"（占位）、unit["composite"] is True |
  | `test_plan_composite_out_of_fallback_ratio` | 1 个普通 fallback 单元 + 1 个复合单元 → `stats["fallback_ratio"] == 0.5`（分母=2 非 3） |
  | `test_plan_stats_composite_count` | `stats["composite"]==1`；`stats["by_status"]` 含 batch_target |
  | `test_refresh_stats_keeps_denominator` | `mark_applied`（复合单元执行后）→ `_refresh_stats` 后 fallback_ratio 分母仍排除 composite（按字段计数不随 ST_APPLIED 漂移） |
  | `test_mark_undone_restores_batch_status` | applied 复合单元 → `mark_undone` → status==ST_BATCH（非 READY） |
  | `test_composite_conflict_detection` | 兜底库预置同名目录 → 复合单元 status==ST_CONFLICT（硬状态优先） |

- [ ] 8. `tests/test_viewmodel.py` 新增 1 个：`test_composite_gate_requires_override`（ST_BATCH 无 override → `checked_not_ready` 含它、`can_apply` False；`set_override` 后 `_executable` True、`can_apply` True）。
- [ ] 9. 验证：`python -m ruff check app/core/planner.py app/ui/viewmodel.py` 0 项；`python -m pytest tests/test_planner.py tests/test_viewmodel.py -q` 全绿（12+29 现有 + 7）。

---

### Task-11 执行链：复合单元放行与保护（特性 C-3）

- 文件：`app/core/planner.py`（Modify：219-220）、`app/core/preflight.py`（Modify：83-84 / 121-124）、`app/core/jobs.py`（Modify：147-149）、`tests/test_planner.py`、`tests/test_flow.py`（Test：末尾追加）
- 操作：修改 + 新增测试
- 接口：Consumes ST_BATCH（Task-10）；Produces freshness/preflight/apply 三处放行语义
- 依赖：Task-10

步骤：
- [ ] 1. planner.py:219-220：`if pu["status"] not in (READY, ST_BATCH): continue`（复合单元纳入源漂移快照校验）。
- [ ] 2. preflight.py：磁盘过滤（:83-84）与长路径过滤（:121-124）的 `u["status"] == READY` 均改 `u["status"] in (READY, ST_BATCH)`。兜底占比检查（:131-144）**不动**（口径已在 stats 修正）。
- [ ] 3. jobs.py:147-149 改：

  ```python
  bad = [u["id"] for u in units
         if u["status"] != READY
         and not (u["status"] == ST_BATCH and u["id"] in overrides
                  and overrides[u["id"]])]
  ```

  （import 处 :14-23 加 ST_BATCH；override 循环 :153-168 与 learned :254-260 零改动——复合单元 genres=[] → learned 空转。）
- [ ] 4. `tests/test_planner.py` 新增 `test_freshness_covers_batch_units`：复合单元入计划后改动源目录（新增文件）→ `check_plan_freshness` 对其 id 报 `"源内容自扫描后已变化"`。
- [ ] 5. `tests/test_flow.py` 新增 4 个集成测试（`env_state` 夹具 + 手工造复合目录）：

  | 测试名 | 步骤 | 断言 |
  |---|---|---|
  | `test_apply_composite_requires_override` | 扫描（源含复合目录）→ `start_apply([复合id], {"jellyfin_running"}, {})` | 任务 failed，error 含 `"不在可执行状态"`；源目录未动 |
  | `test_apply_composite_whole_dir_moves` | 同上但 overrides `{复合id: "科幻"}` | 目标 `(科幻库/原目录名).is_dir()` 且目录名不变、整目录文件全数落位；`learned.json` 不存在或 entries 为空 |
  | `test_apply_composite_undo_restores` | 执行成功后对会话 `run_undo` | 整目录回源位、`mark_undone` 后该单元 status 回 ST_BATCH |
  | `test_preflight_covers_batch_units` | 复合单元 dst_dir 置 >240 字符场景（或直接单测 `run_preflight(cfg, plan)`） | items 含 `long_paths` warn 且 detail 引用复合单元 id |

- [ ] 6. 验证：`python -m ruff check app/core/planner.py app/core/preflight.py app/core/jobs.py` 0 项；`python -m pytest tests/test_planner.py tests/test_flow.py -q` 全绿（13+13 现有 + 5）。

---

### Task-12 计划页 UI：徽章/chips/批量改判/统计卡/演示数据（特性 C-4 + D-UI）

- 文件：`app/ui/table_cells.py`（Modify：19-26）、`app/ui/theme.py`（Modify：35-44）、`app/ui/viewmodel.py`（Modify：70-87 card_tones / 新增 set_override_many）、`app/ui/plan_tab.py`（Modify：102-111 / 161-199 / 新增对话框）、`app/ui/demo_data.py`（Modify：21-33 / 36-85）、`tests/test_viewmodel.py`、`tests/test_plan_tab.py`（Test：末尾追加）
- 操作：修改 + 新增测试
- 接口：Consumes level "composite"/"title"、ST_BATCH（Task-08/10）；Produces UI 呈现与批量改判交互
- 依赖：Task-08、Task-10、Task-11

步骤：
- [ ] 1. table_cells.py:19-26 `STATUS_BADGES` 加 `"batch_target": "batch"`；theme.py BADGE_COLORS（:40 旁）加 `"batch": WARN,`（复用警示橙，不新增色值）。
- [ ] 2. viewmodel.py 新增（set_override :205 后）：

  ```python
  def set_override_many(self, unit_ids, lib: str | None) -> int:
      """批量改判：对给定 id 集合写/清 override，返回生效条数。"""
      n = 0
      for uid in unit_ids:
          if uid in self._by_id:
              self.set_override(uid, lib)
              n += 1
      return n
  ```

  card_tones（:76-87）rows 在 "兜底" 后插入 `(stats.get("composite", 0), "整目录待改判", "bad")` 与 `(stats.get("title", 0), "标题预判", "plot")`（stats() :143-154 需初始化这两个键，`out.get` 聚合已兼容新 level）。
- [ ] 3. plan_tab.py：chips 元组（:103-106）插入 `("composite", "整目录")` 与 `("title", "标题")`（置于 "blocked" 之前）；底部条（:188 `btn_all` 旁）新增 `self.btn_batch = QPushButton("整目录改判…")`，`clicked.connect(self._batch_override)`，初始 `setEnabled(False)`，`_update_summary`（:519-524）里随勾选数启停；`_set_busy`（:372-377）把 `btn_batch` 纳入禁用枚举。
- [ ] 4. 新增 `BatchOverrideDialog(QDialog)`（文件内 BlockConfirmDialog 旁）：构造 `(libs: list[str], parent=None)`，QComboBox（首项"（选择目标库）"）+ 确认/取消；`chosen_lib() -> str | None`（未选返回 None）。`_batch_override`：`libs = sorted({u["target_lib"] for u in self.vm.rows()} - {"兜底库"})`；`lib = BatchOverrideDialog(libs, self).chosen()`；`lib` 非空则 `n = self.vm.set_override_many(self.vm.checked_ids(), lib)`；toast `已对 {n} 部写改判（含整目录单元）`；`_rebuild_table()`。
- [ ] 5. demo_data.py：`_LEVELS`（:31）加 `"composite"`、`"title"`（weights 调 `[56, 15, 10, 8, 6, 5]`）；`_EVIDENCE` 加两键（composite：`"复合目录：3 个疑似影片 base（含番号文件名），需目录级改判"`；title：`"标题命中：マジックミラー号×1 → 魔镜号（低置信）"`）；conf 映射（:60-61）补 `"composite": "low", "title": "low"`；level=="composite" 时单元 dict 补 `"composite": True` 且 status 强制 `ST_BATCH` 等价字符串 `"batch_target"`（:53 choices 扩 `"batch_target"` 权重并入 composite）；`default_selected`（:80-81）复刻 Task-05/10 新规则（rule 且 conf≠low）。
- [ ] 6. `tests/test_viewmodel.py` 新增 3 个：

  | 测试名 | 断言 |
  |---|---|
  | `test_set_override_many_writes_and_clears` | 3 id 批量写 → overrides 3 条；传 None 清除 → 0 条；未知 id 不计入返回值 |
  | `test_card_tones_include_new_levels` | stats 含 composite/title 键；0 值时 tone 落 "dim"（红色 0 空警讯纪律） |
  | `test_select_visible_ready_excludes_composite` | READY 过滤下勾选集不含 ST_BATCH 单元（既有 select_visible_ready 逻辑回归钉） |

- [ ] 7. `tests/test_plan_tab.py` 新增 6 个（offscreen，demo 单元夹具注入 composite/title 行）：

  | 测试名 | 断言 |
  |---|---|
  | `test_new_chips_render_and_filter` | chips 含 "整目录"/"标题"；点击后 `vm.filter` 对应、rows 只含对应 level |
  | `test_batch_button_disabled_without_selection` | 无勾选 → `btn_batch.isEnabled() is False`；勾选 1 行 → True |
  | `test_batch_dialog_applies_to_checked` | monkeypatch `BatchOverrideDialog.chosen` 返回 "科幻" → `_batch_override()` → vm.overrides 覆盖全部勾选 id |
  | `test_batch_dialog_cancel_writes_nothing` | chosen 返回 None → overrides 不变 |
  | `test_can_apply_blocks_unoverridden_composite` | 勾选未改判 composite 行 → `vm.can_apply() is False`；详情区状态徽章文案 "整目录待改判" |
  | `test_demo_units_include_composite_and_title` | `fake_units(40)` 输出含 level=="composite"（status=="batch_target"）与 level=="title" 的行，且字段结构与 planner 同构 |

- [ ] 8. 验证：`python -m ruff check app/ui/table_cells.py app/ui/theme.py app/ui/viewmodel.py app/ui/plan_tab.py app/ui/demo_data.py` 0 项；`python -m pytest tests/test_viewmodel.py tests/test_plan_tab.py -q` 全绿（32+22 现有 + 9）。

---

### Task-13 收口：全量回归 + GUI 冒烟 + 基线核对

- 文件：无新改动；只验证
- 依赖：Task-01~12 全部完成

步骤：
- [ ] 1. `python -m pytest tests -q` 全量 0 failed；用例总数 ≥ 基线 + 70（Task-00 回填的 N）。修订清单核对：仅 `test_complex_dir_excluded`（更名）与 `test_viewmodel.make_unit`（复刻规则）两处，其余 0 删 0 改。
- [ ] 2. `python -m ruff check app/core/nfo.py app/core/scanner.py app/core/config.py app/core/classifier.py app/core/planner.py app/core/preflight.py app/core/jobs.py app/ui/` 0 项。
- [ ] 3. GUI 冒烟截图（offscreen，不真扫盘）：
  `python -m app.ui.main_window --demo --screenshot artifacts/2026-11-09-quality-plan-tab.png --tab 0`
  —— 验收：截图生成；计划页出现"整目录/标题"chips、"整目录改判…"按钮、整目录行状态徽章"整目录待改判"、统计卡含"整目录待改判/标题预判"且演示数据里有对应行；配置页（`--tab 2` 再截一张）出现"弱别名表"与 [title] 启用/阈值控件。
- [ ] 4. 按 D-20261102-02 协议在完成通知注明「GUI 已验证（offscreen 截图）/黑盒未做」。
- [ ] 5. 在本文件末尾「实施记录」补：`收尾=<新总数>`、修订清单、四特性验收口径（规格 §7 A1-D3）逐项勾选结果。
- [ ] 6. **不 commit、不 push**：全部改动留工作区，交 owner 按验收口径核验后自行收口提交。

---

## 4. 边界输入清单（五类最易咬人输入，验收逐条核对）

| 边界 | 行为 | 归属 |
|---|---|---|
| 正常 NFO（well-formed） | 第 4 级容错零接触、recovery=""、告警无变化 | Task-01 `test_digit_rewrite_leaves_wellformed_untouched` |
| 带 CDATA 的 NFO | 第 4 级只在失败后触发，CDATA 内 `<数字` 不被误改（正常解析根本不进第 4 级） | Task-01 安全性论证 + 既有 15 个 nfo 测试回归 |
| 复合目录翻出带题材 NFO | 仍 ST_BATCH 永不自动执行（不按 NFO 归库） | Task-09 `test_composite_with_nfo_still_batch` + Task-10 占位断言 |
| 复合目录执行时真实目标同名 | 计划期占位检查不覆盖 → 执行期 TOCTOU 终检 aborted、可回滚 | Task-11 集成 + 既有 jobs.py:216-223 |
| 同名键同时出现在强/弱表 | 强表胜出，弱表该键不生效；不做跨表校验报错 | Task-05 `test_map_genres_ex_shapes` |
| 空标题/无 NFO 复合单元 | score_title 空文本返回 []，title 不参与，走兜底 | Task-08 `test_score_title_*` 输入构造覆盖 |
| 单字符别名键 | 不参与标题评分（防单字误命中） | Task-08 `test_score_title_skips_short_keys` |
| 旧 config.toml（无 weak/title 节） | 默认空 dict / True+1.0，零迁移 | Task-04/07 defaults 测试 |
| GUI 保存丢字段回归 | dump 往返钉死 weak/title | Task-04/07 round-trip 测试 |
| 复合单元执行后撤销 | 状态回 ST_BATCH 而非 READY（修既有 mark_undone 缺陷） | Task-10 `test_mark_undone_restores_batch_status` |

## 5. 已知边界与明确不做（记录在案，验收不得当作缺陷）

1. 复合单元计划期冲突检查基于占位目标（兜底库/目录名）；改判后真实目标的同名冲突由执行期终检拦截（aborted 可回滚），不做改判后二次计划。
2. `provider_id` 恢复后，javdb 同 id 的重复副本单元将按既有 D-20261031-04 进 ST_MULTI 默认不选——是修复效果，不是回归。
3. config_hash 变更使既有 runtime/plan.json 全部失效，重扫即愈。
4. 弱标记集本身是 owner 配置决策：标记过宽 → 更多行默认不勾（人工量上升），不会错位入库；计划只交付代码与示例，不改动 owner 实机 config.toml。
5. 标题评分词表质量取决于别名表覆盖（如 `NTR→寝取`、`マジックミラー号→魔镜号` 需 owner 补录）；代码不做任何内置词表。
6. 批量改判作用于全部勾选单元（含普通单元），不限定复合单元——这是通用能力而非特化限制。
7. 不拆分、不搬移、不改名、不做目录内番号识别（规格 §4.5）。

## 6. 计划自查（五查结论）

1. **规格覆盖**：A→Task-01/02/03；B→Task-04/05/06；C→Task-09/10/11/12；D→Task-07/08（+12 UI）。规格 §7 验收口径 A1-D3 与全局项每条可追溯到测试名。
2. **步骤唯一可写**：同文件多卡严格串行且区域不重叠（nfo：T1 容错链/T2 裸 id；scanner：T3 flags/T9 复合分支；config：T4 weak/T7 title；classifier：T5 弱裁决/T8 title；planner：T5 一行门/T10 状态统计/T11 一行放行；viewmodel：T8 title 徽章/T10 门禁/T12 批量与卡片；plan_tab/config_tab/demo_data/table_cells/theme 各归单卡）。
3. **签名一致**：见第 2 节总表；对现有调用方零破坏（map_genres 签名不变、run_apply/run_preflight/check_plan_freshness 签名不变、Config 新字段全默认值）。
4. **边界输入**：第 4 节 10 条逐条有代码点 + 测试名。
5. **比例**：计划约 470 行 / 预估改动约 600 行代码 + 70 测试，未超比例；无 TBD/“处理边界情况”死行。

## 7. 验证命令汇总

```bash
# 基线（Task-00）
python -m pytest --collect-only -q
# 定向（每任务收尾，ruff 先行）
python -m ruff check <本卡改动文件>
python -m pytest tests/test_nfo.py -q            # Task-01/02
python -m pytest tests/test_scanner.py -q        # Task-03/09
python -m pytest tests/test_config.py -q         # Task-04/07
python -m pytest tests/test_classifier.py -q     # Task-05/08
python -m pytest tests/test_planner.py -q        # Task-05/10/11
python -m pytest tests/test_config_tab.py -q     # Task-06/07
python -m pytest tests/test_viewmodel.py -q      # Task-05/08/10/12
python -m pytest tests/test_flow.py -q           # Task-11
python -m pytest tests/test_plan_tab.py -q       # Task-12
# 全量（Task-13）
python -m pytest tests -q
# GUI 冒烟截图（Task-13）
python -m app.ui.main_window --demo --screenshot artifacts/2026-11-09-quality-plan-tab.png --tab 0
python -m app.ui.main_window --demo --screenshot artifacts/2026-11-09-quality-config-tab.png --tab 2
```

## 8. 实施记录（执行者填写）

- 基线=197（Task-00 由主审 2026-11-09 实测回填：`--collect-only` 197、`pytest tests -q` → 197 passed）
- 收尾=<新总数>
- 测试修订清单：<应仅两处，见全局约束 5>

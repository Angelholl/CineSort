# 规格：分类质量四特性（NFO 容错 / 弱标签护栏 / 复合目录归集 / 标题弱评分）

- 日期：2026-11-09
- 状态：规格定稿（owner 已拍板三项立项与"不拆分"边界），实现拆解见
  `docs/plans/2026-11-09-classification-quality.md`
- 实测依据：2026-11-09 源 `E:\已刮削\待整理`，用项目自带 scanner+classifier 跑
  owner 实机配置（40 库 / 56 条 genre_aliases / genre_priority 重排 / plot.enabled=false）
- 关联决策：D-20261031-02（三级决策链）、D-20261031-03（C7 冲突三分）、
  D-20261031-04（复合目录整目录排除——本规格对其"呈现方式"做 owner 批准的修订）、
  D-20261031-05（移动语义）、D-20261101-03（自学习）

---

## 0. 实测基线（为什么做）

| 指标 | 数值 | 含义 |
|---|---|---|
| 可判定单元 | 97 | 配置层定稿后 rule 97.9% / fallback 2.1% |
| 严格精度 | 22/30 ≈ 73% | 30 例分层人工核对，低于 90% 验收线 |
| 宽松精度 | 26/30 ≈ 87% | 允许"可疑但进了人工可救状态"的口径 |
| 复合目录 | 43 个被整体排除 | 内含 147 视频、0 NFO，文件名全含番号+完整日文标题（按女优归拢的散装视频） |
| NFO plot 覆盖 | 50/97 | 日文摘要中位 216 字 |
| NFO 解析失败 | 15/97，同一成因 | JavDB 写出 `<7mmtvid>…</7mmtvid>`（元素名数字开头违反 XML NameStartChar），`ET.fromstring` 报 not well-formed；regex 兜底已抓全 genres/title/plot，但单元带 `nfo_parse_warning` 且界面告警 |
| 附带发现 | 15 个同一批 NFO | `<javdbid>wKV281</javdbid>` 未被识别为 provider id → planner same_id 去重对这些单元完全失效 |

判错成因三类：① 标签与标题语义冲突（ABF-312 标题 NTR 但`护士`标签更"具体"→判医护；JUR-555 标题不倫NTR 但源标签`女同性戀`→判百合）；② 只有标题有线索（SDJS-348 标题含 マジックミラー号，应进 魔镜号）；③ 源数据自己打错标签（JUR-058 是 DEBUT 作品却带`人妻`标签）。

---

## 1. 全局约束（四特性共同遵守，违反任何一条即 FAIL）

1. **不拆分复合目录**：复合目录永远以"目录"为单位呈现与执行，不产生 file 单元，
   不按番号拆成独立影片单元（decision-critic [HIGH_RISK_OBJECTION] 已采纳：
   `-C` 变体误拆会造成库内重复 + provider id 去重失效 + 多 CD 误拆 + 兜底率恶化到 ≈61%）。
2. **不改 scanner 复合目录的"排除"实质语义的另一半**：extras/花絮/系统目录剔除、
   RE_SUPPLEMENT 回退保护、多 CD 合并等既有识别规则全部不动（D-20261101-01）。
   唯一修订：复合目录从"整体排除+报告"改为"整目录单元+待改判状态"（owner 拍板 1）。
3. **兜底率口径不被污染**：复合目录单元不进 `fallback_ratio` 的分子（level 不是
   fallback），也不进分母（分母 = 总单元 − 复合目录单元）；标题预判单元不是
   fallback（独立 level）。preflight 阈值行为不变，修正后 43 个复合目录不触发常态阻断。
4. **弱信号一律低置信 + 默认不选**：弱标签命中、标题预判命中 confidence 恒为
   `"low"`、`default_selected=False`；弱信号永不覆盖强规则命中（强别名命中存在时
   决策与现状完全一致）。
5. **原始目录不动**：逻辑归集阶段不做任何物理搬移、不拆散、不改目录名；执行=
   整目录迁移且目录名保持不变。
6. **测试基线只增不减**；行为变更所必需的测试修订（预计 2 处）必须在计划中逐条
   记录并说明 owner 批准依据；修 bug（特性 A 属 bug fix）必带回归测试。
7. **验证链**：每卡 `python -m ruff check <改动文件>` 0 项 → 定向 pytest → 全量
   pytest → GUI 冒烟截图（GUI 变更）。工具链以项目现状为准（无 pyproject/pytest.ini，
   直接 `python -m pytest tests -q`；GUI 冒烟 `python -m app.ui.main_window --demo
   --screenshot <png> --tab <n>`）。

---

## 2. 特性 A：NFO 容错 + provider id（bug fix + 回归测试）

### 2.1 数字开头元素名重写（已验证修法）

- 行为定义：`parse_nfo_text`（nfo.py:166-207）容错链在"裸 & 转义"之后追加第 4 级：
  `re.sub(r"<(/?)(\d[^\s>/]*)", r"<\1_\2", text)`，把 `<7mmtvid>`/`</7mmtvid>` 重写为
  `<_7mmtvid>`/`</_7mmtvid>` 后重走 XML 解析（含 movie 块截取重试）。
- 安全性论证（写死，不重新论证）：任何**well-formed** XML 中 `<` 后紧跟数字不可能出现
  （元素名禁止数字开头，文本/属性中的 `<` 必须转义，CDATA 内的 `<数字` 是唯一理论例外，
  故重写只作为解析失败后的兜底级，绝不作用于一次解析成功的输入）→ 对现有 82 个正常
  解析单元零行为变化。
- parse_error 语义变化（本规格拍板）：
  - `parse_error` 只在**彻底失败**（parse_mode=="regex"）时非空 —— 与现状一致；
  - 新增 `NfoInfo.recovery: str`（默认空串）记录走过的容错级（"截取 movie 块"/
    "转义裸 &"/"重写数字开头元素名"）。容错恢复**不再出 warning**：scanner 的
    `nfo_parse_warning` flag（scanner.py:173-174）与扫描告警 note（scanner.py:244-246）
    继续只挂 `parse_error`，因此 15 个 JavDB 单元的告警自然消失；
  - "已容错恢复"提示保留但降级为**证据行**：planner 把 `recovery` 以
    `NFO 已容错恢复：<描述>` 追加进单元 evidence（planner.py:118-119 处），GUI 详情
    面板正常展示，不进 notes（notes 前缀是 ⚠，语义不符）。

### 2.2 裸 id 元素纳入 provider id

- 行为定义：`_fill_from_xml`（nfo.py:112-135）与 `_fill_from_regex`（nfo.py:138-163）
  新增"裸 id 元素"收集：元素局部名匹配 `^(.+?id)$`（即以 id 结尾、整体名长 >2）、
  **无任何属性**、文本非空 → `uniqueids[name去尾id并casefold] = text`。
  例：`<javdbid>wKV281</javdbid>` → `uniqueids["javdb"]="wKV281"`；
  `<tmdbid>42</tmdbid>` → `uniqueids["tmdb"]="42"`。
- 优先级与冲突：显式 `<uniqueid type=…>` / `<id moviedb=…>` 条目**优先**于同名裸 id
  （裸 id 先收进暂存 dict，循环结束后用 `setdefault` 合并）；裸 `<id>`（去尾得空串）
  跳过；空文本跳过。XML 与 regex 两条路径语义一致。
- scheme 命名与去重语义：scheme = 元素名去掉尾部 `id` 后 casefold（javdbid→javdb、
  dmmid→dmm、mgstageid→mgstage）。`provider_id`（nfo.py:44-53）优先级链不变
  （tmdb/imdb/tvdb → 其他任意），javdb 自然落在"其他"档。
  连带效果：planner 的 same_id 已在位/多版本检测（planner.py:91-95、142-155）对这
  15 类单元恢复生效；若同 id 真有重复副本，将按既有 D-20261031-04 语义进 ST_MULTI
  默认不选——这是修复而非回归。

### 2.3 特性 A 非目标

- 不做 XML schema 校验、不修 JavDB 刮削器本身、不重写 NFO 文件、不新增 provider
  优先级配置项。

---

## 3. 特性 B：弱标签护栏

### 3.1 配置形态（拍板）

- 新增独立 TOML 表 `[weak_genre_aliases]`，形状与 `[genre_aliases]` 完全一致
  （`别名 = 标准库名`）。**不采用**"alias 值带语法"（`护士~医护`）方案：值带语法会让
  config.py 校验、GUI 文本框解析、dump 往返三处各自发明微语法，回归面大。
- `Config` 新增字段 `weak_genre_aliases: dict[str, str]`（默认空 dict，旧配置零迁移）。
  校验与 genre_aliases 同规则：值必须是已定义库名，否则 `ConfigError`（报错文案含
  `weak_genre_aliases`）。
- `describe()` / `raw_describe()` / `dump_config_text()`（config.py:270-365）全部带上
  weak 表；`dump_config_text` 输出 `weak_genre_aliases = { … }` inline table（与
  genre_aliases 同款单行形态），**GUI 保存往返不得丢字段**（回归测试钉住）。
- `config_hash()`（config.py:93-103）payload 纳入 weak 表与特性 D 的 title 节
  （它们影响分类结果；旧 plan.json 因此失效，重扫即愈，属预期）。
- 同名键同时出现在强/弱两表时**强表胜出**（classifier 先查强表），配置层不做跨表
  互斥校验（校验错误留给真正的引用错误）。
- GUI：配置页在"别名表"下方新增多行文本框"弱别名表"，placeholder
  `每行：别名=标准库名（弱信号：唯一命中时低置信、默认不勾选）`；演示模式纳入禁用
  清单；config_viewmodel 的 `describe_to_form` / `form_to_body` 增加
  `weak_alias_text` 往返。

### 3.2 判定语义（拍板）

- `alias_map`（classifier.py:37-43）不动；新增 `weak_alias_map(cfg)` 与
  `map_genres_ex(cfg, genres) -> (mapped_strong, mapped_weak, unmapped)`；
  `map_genres` 保留原签名与返回值，内部改为 `map_genres_ex` 的 wrapper
  （planner.py:82 的 unmapped 用法零改动）。
- 候选库裁决：
  1. 候选集 = 强命中库集合；**仅当强集合为空**时候选集 = 弱命中库集合（弱永不与强同台
     竞争，"弱标签不得赢过强标签"由此结构性保证，优先级表只在候选集内部裁决）；
  2. 唯一命中且该命中来自弱标签 → `Decision.level="rule"`、`confidence="low"`、
     reason 追加`（弱标签）`、evidence 追加 `弱标签『护士』→ 医护（弱信号，默认不勾选）`；
  3. 多个弱候选 → 仍按 `genre_priority` / 历史倾向在弱候选内裁决（classifier.py:88-92、
     151-176 既有逻辑复用），confidence 恒 low；
  4. 同一库同时被强、弱别名命中 → 视为强命中，不受降级；
  5. 强命中存在时的整条决策路径（含 smart 摘要择优、evidence 文案）与现状**逐字节一致**。
- `default_selected`（planner.py:132-134）规则修订为：
  `status == READY and ((dec.level == "rule" and dec.confidence != "low")
  or (dec.level == "learned" and dec.confidence == "medium"))`。
  plot/title/fallback/弱 rule 一律默认不选。摘要预判（plot）现状本就默认不选，不变。
- 与自学习互不干扰：弱标签命中单元执行确认后照常按 genres 记票（learned.record），
  自学习映射不受弱标记影响。

### 3.3 审计实例的诚实边界（必须原样写进 GUI 提示与验收口径）

| 实例 | 特性 B 能做到 | 特性 B 做不到 | 谁来补 |
|---|---|---|---|
| ABF-312（标题 NTR，标签`护士`） | `护士`标记弱后：医护降为低置信、默认不勾，进入人工复核 | 不会自动改判到 寝取 | 标题词`NTR/寝取`进弱别名表后由特性 D 给 寝取 低置信建议，人工确认 |
| JUR-555（标题不倫NTR，标签`女同性戀`） | 百合降为低置信、默认不勾 | 同上，不自动改判 | 同上 |
| JUR-058（DEBUT 误带`人妻`标签） | `人妻`族标记弱后：降级人工 | 无文本线索时无法自动纠正 | 人工改判（顺带自学习记票） |
| SDJS-348（仅标题含 マジックミラー号） | 无题材线索，B 无参与 | — | 特性 D（补弱别名`マジックミラー号`=`魔镜号`） |

结论表述：**B 不自动修对任何一例，它把"标签与标题冲突/源标签错误"类的可疑命中从
"高置信直接进库"降为"低置信人工复核"**。宽松精度（可疑但可救）因此可望从 87% 提升；
严格精度提升依赖人工确认闭环 + 特性 D。

**初始弱标记集（owner 2026-11-09 拍板，D-20261109-01）**：只标两个冲突高发族——
`护士`、`看护妇・ナース`（→ 医护）、`女同性戀`、`女同性恋`、`女同接吻`、`レズキス`（→ 百合）。
`人妻` 族 5 条与 `OL`/`职业装`/`各種職業`/`各种职业` **本轮不标**：owner 先实跑一轮观察
默认不勾的行数与人工确认量，再决定是否扩集（扩集是纯配置改动，不需要改代码）。
标记过宽的代价是更多行默认不勾（人工量上升），不会产生错位入库。

### 3.4 特性 B 非目标

- 不引入"中置信"档、不做标题↔标签冲突的自动仲裁（那是 D+人工的活）、不改 56 条
  强别名表的任何现有映射。

---

## 4. 特性 C：复合目录逻辑归集 + 目录级批量改判

### 4.1 扫描层（scanner.py:162-164 的修订）

- 复合目录不再 `return None, note`，改为生成一个**整目录单元**：
  `Unit(kind="dir", composite=True, flags=["composite", …原有 flag], videos=mains
  按名排序, nfo=find_nfo(...), title=目录名, provider=NFO 有则取（实测 0 NFO）,
  files=snapshot_dir 整目录快照)`。新增 `Unit.composite: bool = False` 字段。
- 扫描 note 从 `{"level": "excluded", reason: "复合目录…"}` 改为
  `{"level": "info", reason: "复合目录已作为整目录单元生成（N 个疑似影片），需目录级改判后执行"}`。
- RE_SUPPLEMENT 回退、extras 剔除、多 CD 合并等先行逻辑全部不变（先算 mains 再判
  bases>1 的既有顺序保持，复合判定仍发生在最后）。

### 4.2 计划层（planner.py）

- 新状态常量 `ST_BATCH = "batch_target"`，`STATUS_LABELS[ST_BATCH] = "整目录待改判"`。
- 复合单元在 build_plan：**仍调用 classify** 但其结果仅作占位与证据——目标恒为占位
  兜底库，`level="composite"`，`status=ST_BATCH`，`default_selected=False`，
  单元 dict 新增 `"composite": True`。即使复合目录里翻出了带题材的 NFO（实测没有，
  但代码要稳），也**永不自动执行**——多影片目录按单一 NFO 自动归库必然错位，这是
  owner"先逻辑归集、后目录级批量改判"的直译。
- 既有冲突检测照跑（planner.py:84-104）：占位目标（兜底库/目录名）上检出
  `.incomplete` 残留 → ST_INCOMPLETE；同 provider id 已在位 → ST_PLACED（仅当复合
  目录带 NFO+id）；同名 → ST_CONFLICT。这些硬状态优先于 ST_BATCH。
- 多版本分组（planner.py:142-155）只扫 READY，复合单元天然不参与。
- **统计口径**（planner.py:157-179 与 _refresh_stats:242-252 两处同步改）：
  - 新增 `stats["composite"]` = 复合单元数（按单元字段 `composite` 计数，不随状态
    变化，执行/撤销后口径稳定）；
  - `fallback_ratio = fallback_ready数 / (total − composite数)`（分母为 0 时取 0）；
  - 实测效果：97 可判定 + 43 复合 → 分母仍 97，2.1% 不变，preflight 不阻断。
- `mark_undone`（planner.py:269-278）修复：复合单元撤销后状态回 `ST_BATCH`
  （现状会错误回 READY——借此任务一并钉回归测试）。

### 4.3 执行链（jobs/preflight/planner.freshness）

- `check_plan_freshness`（planner.py:219-220）：快照校验从"仅 READY"扩为
  `status in (READY, ST_BATCH)`（复合目录同样受源漂移保护）。
- `run_preflight`（preflight.py）：磁盘空间（:83-84）与超长路径（:121-124）的单元
  过滤同样扩为 `(READY, ST_BATCH)`。
- `run_apply`（jobs.py:147-149）：不可执行名单改为"status 非 READY 且非 ST_BATCH，
  或 ST_BATCH 但无 override"。即：**复合单元必须先整目录改判才能执行**；改判目标
  沿用既有 override 通道（jobs.py:153-168，内存改写，不写 plan.json）。
- 执行 = 整目录迁移：`kind=="dir"` 走既有 `fsops.transfer_dir`（快照校验+原子改名，
  fsops.py:80-123），`dst_dir = 改判库根/目录名`，**目录名不变**；TOCTOU 终检
  （jobs.py:216-223）在真实目标上拦截同名冲突 → aborted 可回滚。计划期冲突检查基于
  占位目标的局限由此兜底（记录为已知边界）。
- 自学习：复合单元 `genres=[]` → `learned.record`（learned.py:45）天然空转，
  **整目录改判不写 learned**——防止目录名/番号污染题材词表（显式钉测试）。
- 回滚：journals `kind="dir"`，undo 整目录还原，既有语义零改动。

### 4.4 GUI 语义（计划页）

- 复合单元是普通行（一行=一个目录），判定徽章"整目录"，状态徽章"整目录待改判"，
  证据区显示：视频数、疑似影片 base 列表（截断展示）、文件名含番号的提示文案。
- 筛选 chips 增加"整目录"（filter key=`composite`）。
- 批量改判：底部操作条新增"整目录改判…"按钮（仅当有勾选时启用）→ 弹出目标库选择
  对话框（列出现身行中的库 + 兜底库，复用 `_fill_libs` 数据）→ 确认后对**全部勾选
  单元**写 override（新增 viewmodel `set_override_many(ids, lib)`，单行改判下拉保持
  原样）。改判本身不落盘（与既有会话级 override 口径一致），执行成功后由
  mark_applied 落状态。
- "整目录全选"= 勾选该行即整目录选中（单元即目录，无需树形分组）；"全选可执行"
  维持只勾 READY，不勾复合单元。
- `can_apply`：勾选集中存在"未改判复合单元" → 禁用执行并在提示区说明。

### 4.5 特性 C 非目标（owner 拍板，验收不得当缺陷）

- 不自动拆分为独立单元（含 `-C` 变体）、不做物理搬移/预搬移、不改目录名、
  不为复合目录新增 preflight 阈值、不写 learned、不做目录内番号识别。

---

## 5. 特性 D：标题文本弱评分

### 5.1 文本源与词表

- 文本源：`NFO title`（有则拼入）+ 单元标题（目录名 / 散装文件 stem，scanner 已兜底
  为 `unit.title`）。两者空格拼接去重后参与匹配。**不含 plot**（plot 是特性既有
  score_plot 的领域，owner 实机 plot.enabled=false，互不牵动）。
- 词表 = 强别名表 ∪ 弱别名表 ∪ 库自身名（三者共用 `normalize_key` 归一后做子串计数），
  即 owner 在别名表里加一条 `マジックミラー号 = 魔镜号`，标签映射、标题评分同时生效
  ——**一张词表喂 tags/title/plot 三处，不新造任何 per-库 keywords**。
  长度 <2 的键不参与（防单字误命中）。
- 评分：`score_title(text, cfg) -> list[(库名, 分, 命中明细)]`，分 = Σ(键命中次数)，
  阈值独立 `title.min_score`（默认 1.0，即命中 1 个词即成建议）。**不做长度归一**
  ——score_plot 的 `len**0.5` 归一在短文本上会放大分数（216 字摘要 vs 十几字标题
  不可复用同一把尺），这是显式设计差异，不是遗漏。

### 5.2 配置

- 新增 `[title]` 节：`TitleOptions(enabled: bool = True, min_score: float = 1.0)`；
  校验 `min_score ≥ 0`；describe/raw_describe/dump_config_text/config_hash 全带
  （与特性 B 同一批往返与 hash 规则）；GUI 配置页在 [plot] 区块旁镜像一组
  （启用复选框 + 阈值输入）。
- 默认 enabled=true 的依据：title 建议恒为低置信+默认不选，开启它只增加"证据与建议"，
  无自动化风险；owner 不想看可一键关。

### 5.3 决策链位置与语义

- 新判定级 `LEVEL_TITLE = "title"`（中文"标题预判"），置信恒 `"low"`，
  `default_selected=False`（planner 既有规则天然覆盖，无需改 planner）。
- **只在原本要兜底的路上出现**，两个插入点都在"fallback 之前、soft_hits（自学习低票
  建议）之后"：
  1. 无题材分支（classifier.py:178-183）：plot 达标 → learned 软建议 → **标题预判** → 兜底；
  2. 题材全未映射分支（classifier.py:194-201）：learned 自动 → plot 达标 → learned 软
     建议 → **标题预判** → 兜底。
- 弱信号永不覆盖规则：存在强/弱规则命中时 title 评分根本不参与裁决
  （smart 多候选择优仍只用 plot 评分，classifier.py:185-192 不动）。
- 证据文案强制可区分：标题命中行前缀 `标题命中：词×次数`；摘要命中保持既有
  `摘要命中：…` 前缀。GUI 判定徽章"标题预判"（新 badge 键），筛选 chips 增加"标题"。

### 5.4 验收精度门槛（拍板）

- 保留条件：对 30 例分层样本，标题预判给出的建议目标人工核对精度 ≥80%（建议本身
  默认不选，故此门槛决定的是"功能保留与否"，不是放行条件）。
- 不达标处置：owner 将 `[title] enabled` 置 false 即降级为"仅展示不自动选"的更弱形态
  （实际上 enabled=false 就是完全不参与，效果等价且无需新模式开关）。
- 不为 D 单设 preflight 指标：title 级单元不是 fallback，`fallback_ratio` 不受污染；
  `ready_levels` 将出现 `title` 键，GUI 统计卡新增"标题预判"卡。

### 5.5 特性 D 非目标

- 不做分词/NLP、不做英文番号解析、不改 score_plot 与 plot 配置、不把标题命中用于
  smart 多候选择优、不自动勾选。

---

## 6. 非目标汇总（四特性之外明确不做）

1. 不拆分复合目录、不搬移、不改名（§4.5）。
2. 不改 scanner 既有排除语义（extras/sample/系统目录等）。
3. 不动 56 条强别名表与 genre_priority 现值（owner 已定稿生效）。
4. 不引入 ML/LLM/外部服务；全部纯本地词表逻辑。
5. 不改 JavDB 刮削器、不重写用户 NFO 文件。
6. 不为弱信号新增置信档位（保持 high/medium/low 三档）。
7. 不新增 preflight 阈值项（仅修正复合目录的统计口径）。

## 7. 验收口径汇总

| # | 验收项 | 口径 |
|---|---|---|
| A1 | 15 类数字开头元素 NFO | XML 正常路径解析，genres/title/plot 与 regex 路径逐字段一致，无 warning |
| A2 | 裸 javdbid | provider_id=`javdb:wKV281` 型，same_id 去重恢复生效 |
| A3 | 正常 NFO 回归 | 解析结果与容错标记零变化（recovery 为空） |
| B1 | 弱标签唯一命中 | level=rule、conf=low、默认不勾、evidence 含"弱标签" |
| B2 | 弱不压强 | 强弱同场时强胜，决策与现状逐字节一致 |
| B3 | 配置往返 | GUI 保存后 weak/title 字段零丢失，config_hash 随之变化 |
| C1 | 43 复合目录 | 43 个整目录单元，status=ST_BATCH、默认不勾、不进 fallback 分子分母 |
| C2 | 目录级改判执行 | 整目录落 `改判库/原名`，文件数/体积不变，可 undo，learned 零写入 |
| C3 | 未改判不可执行 | 无 override 的复合单元执行被拒 |
| D1 | 标题命中建议 | level=title、conf=low、默认不勾、证据前缀"标题命中" |
| D2 | 词表统一 | 同一别名条目同时驱动标签映射与标题评分 |
| D3 | 精度门槛 | 30 例抽样标题建议精度 ≥80% 保留，否则 owner 关 [title] |
| 全局 | 回归 | 全量 pytest 通过，基线只增不减（修订逐条记录）；GUI 冒烟截图；ruff 0 项 |

# 分类机制五项调整实现计划（A 含 D / B 两层 / C-1 / E）

- 日期：2026-11-25 ｜ 决策真值：`docs/decision-log.md` **D-20261125-05**（引用 D-20261101-03 / D-20261031-02 / D-20261125-04）
- 测试基线：**367 passed**（decision-log 最后数字；后续补记未载新数，实测高于 367 时以实测为基线，只增不减）
- mypy 基线：**149**（D-20261125-04 收敛后）；ruff：改动文件必须 0 项
- 本计划只拆解与验收，方案取舍不重新论证（已拍板）。数据口径、风险跟踪全部以 D-20261125-05 条目为准。
- 计划正文使用库名真实名称（仅限本文档；对外工件沿用 `%TEMP%\cinesort_analysis\codes.md` 的 lib-XX / item-XX 代号）。
- **状态：owner 已批准开工（2026-11-26，新会话执行）**。§2.2 三处定读照写确认；Task-03 排序原则 owner 已定=题材定位型在前、行为/元数据泛用型靠后；首卡=Task-01。

---

## 1 目标

按 D-20261125-05 落地五项调整，使分类机制的自动信号域收缩为「显式规则 + 摘要择优（可配）」，人工改判信号全部转为「建议 / 记忆」形态并全程留痕：

1. **A-2**：自学习不再自动生效（人工票只作建议）；人工改判不再按题材记 2 票；**票数退出多候选择优由代码保证**（classifier 破平手路径删除 votes 项，不依赖优先级表填全）。
2. **C-1**：优先级表按类全量填充（owner 纯配置任务，计划留占位步骤+重放核对；警示：按默认顺序全填会让最大粗桶占比 41%→58%，单库垫底会把判定转移给另一行为类库 20→48）。
3. **留痕**：done 日志记录追加 provider id / 是否人工 / 原判定库（B 层与 B(ii) 的数据地基）。
4. **E**：摘要择优新增策略值（旧 smart 行为不变，不触发 D-20261031-02 复议），含**置信度诚实化**（不做则默认勾选数从 157 升到 182–199）；顺带修证据文案「优先级第 1 位」。
5. **B(i)**：会话内同作品套用改判——不自动勾选、落点冲突不套用（套用键按 2026-11-25 前置核实修正：规范化片名+年份，provider id 降级为一致性门）。
6. **B(ii)**：跨扫描记忆从会话日志派生，不新建持久层文件；只对留痕上线后的执行生效；被回滚的会话不得派生；需单测。
7. **A-1**：元数据标签不记学习票 + 旧票迁移（必须在 C-1 与 E 之后）。
8. **D**：并入别名扫描分析对话框的「提升建议」，仅对真实题材信号、被 A-1 门控（当前满足条件的为 0 对）。

## 2 架构与规格（真值 = D-20261125-05；含计划定读标注）

### 2.1 信号域架构（调整后）

```
自动分类信号域（收缩后）＝ 显式规则（别名表+优先级表）＋ 摘要择优（策略值可选，E）＋ 摘要/标题预判（既有）
建议/记忆域（不自动生效）＝ 自学习票（legacy，仅低置信建议）＋ 跨扫描记忆（B(ii)）＋ 会话内套用（B(i)）
人工信号记录 ＝ 会话日志 done 留痕字段（provider id / 是否人工 / 原判定库 / 片名 / 年份）→ 派生 B(ii)
```

- 决策层级（推翻 D-20261101-03 的自动生效层）：显式规则 > 摘要预判 > 自学习建议 > 兜底；多候选择优 = 优先级表位次 →（表内并列时）声明顺序，**无票数参与**。
- `runtime/learned.json`（D-20261101-03）保留为 legacy 建议数据：只读展示、逐条忘记、A-1 旧票迁移后冻结；不再有任何新票写入。

### 2.2 规格定读（决策文本 → 施工语义的逐条落法）

以下带 ★ 的条目为计划层定读（决策文本未逐字给出实现细节处，依据=条目原文+任务函；owner 评审可改写，改写只动本节与对应任务面，不动架构）：

1. **A-2 定读**：①`classify` 删除「票数 ≥ min_votes 自动生效」分支——所有自学习命中一律为低置信建议；②多候选择优键由 `(*优先级位次, -票数, 声明顺序)` 改为 `(*优先级位次, 声明顺序)`（classifier.py:234-237）；③`planner.default_selected` 删除 learned 子句（结构性保证：任何自学习行永不默认勾选）；④执行侧：人工改判单元不再调 `learned.record`（人工信号移入会话留痕）；⑤`record()` 权重改为一律 +1（`manual` 只计数不加权），供 A-2→A-1 窗口期确认票沿用。依据：D-20261125-05 行 247、风险 #2/#6。
2. **留痕字段定读**：owner 点名三字段 = `provider / manual / orig_lib`；★追加 `title / year` 两个技术字段——依据=2026-11-25 前置核实修正函（B 套用键改为规范化片名+年份，B(ii) 派生需同键；旧 done 记录无此二字段即天然不参与派生）。
3. **A-1 定读**：①「元数据标签不记学习票」=执行侧**全面停记**题材键票（确认票一并停记，`record()` 退役删除）；②「旧票迁移」=一次性幂等 `prune`：凡 normalize_key 已被强/弱别名表或库名覆盖的票目（classify 只对未映射题材咨询 learned，此部分为死重量）删除，其余保留为 legacy 建议；③`[learning].enabled` 改义为「自学习建议门控」（关=classify 不咨询 learned），使开关保持诚实语义；④`[learning].min_votes` 改作 D 的提升阈值（字段获新消费方，不删配置键）。依据：行 247、风险 #6（验证=learned.json 新增人工票数为 0）。
4. **E 定读**：★新策略值定名 **`smart_weighted`**：多候选择优评分只取 `keywords_weighted`（owner 手工维护），普通 keywords（库名预填所在地）不参与——直击「库名预填偏向场面词」病灶；择优胜出行按摘要判（level=plot，默认不勾）；加权词判不出时回退优先级表且**置信度诚实化=低**（多候选无法由摘要区分，默认不勾）。旧 `smart` 全链路行为不变。默认不生效（实机 `strategy` 仍为 smart，owner 复测轮自行切换，风险 #1）。依据：行 236/249/253、任务函「不做则 157→182–199」＝把择优胜出标成高置信可勾选的失败模式，回归测试钉死。
5. **B(i) 定读**（按前置核实修正函）：套用键 = `(normalize_key(title), year)`；provider id 为一致性门——兄弟单元与触发单元 id 不一致（含裸 `<xxxid>` 三级容错产的假同 id、分集/剧集）→ 不套用（逐单元确认）；可收状态仅 `ready / multi_version`；落点冲突不套用（组内改判后 `(库, 女优段, dst_name)` 互撞、或已执行/复合/硬冲突状态）；不自动勾选；`set_override_many`（批量改判）不触发套用；撤销改判不联动撤销兄弟。
6. **B(ii) 定读**：`journal.derive_memory` 只取**带留痕字段**的 apply 会话中 `manual=true` 的 done 记录（键同 B(i)）；undo 会话回滚过的 unit_id 排除（风险 #4 明令，单测钉死）；★「回滚后重扫」命中面仅在存在未回滚同作品会话时成立——纯被回滚会话本身不派生（定读已在 §6 披露）。同一作品多会话不一致时最近会话胜出。
7. **D 定读**：「真实题材信号」门 = A-1 prune 幸存（未被别名表/库名覆盖）且 `votes ≥ learning.min_votes` 且目标库仍存在；当前实机满足条件为 0 对（决策原文），功能以空态上线、后续按数据自然生长。
8. **重放量尺定读**（四指标，见 §4）：自动生效单元数（level=learned 且默认勾选）/ 多候选胜出依据分布（priority / plot / decl_order / votes）/ 默认勾选数 / 票数闭合不一致对数（被留痕后会话触及、且票数与该会话推演票数不符的对数；未被触及的历史对不计）。

## 3 全局约束（每卡逐条自检）

1. **同工作树 ≤1 卡**：Task-01→Task-10 严格串行（依赖序即卡序），超卡即退回。
2. **执行者只 commit 不 push**；提交信息 = Conventional 前缀 + 中文描述，正文 `verify:`（全量前后数 + 四指标前后数）+ `Refs: D-20261125-05`；永不 `--no-verify`；永不 `git add -A`（显式列文件）。
3. **验证链硬序**：ruff（改动文件 0 项）→ 定向测试 → 全量测试（≥367 只增不减）→ 冒烟 → 离线重放四指标核对；任一环失败即停。
4. **禁触文件**：`app/__init__.py`、`installer/installer.iss`（owner 未提交改动）——任何任务不得触碰；本计划不 bump 版本、不发版、不动 CI。
5. **GUI 任务**（Task-02 / 05 / 06 / 07 / 08 涉 GUI 文本或控件）：按 D-20261102-02 协议执行——viewmodel 级逻辑零 Qt 单测 + `QT_QPA_PLATFORM=offscreen` widget 驱动测试，不引入新依赖；提交注明「GUI 已验证（离屏）」。
6. **每卡验收含离线重放四指标核对**：`python tools/replay_metrics.py <实机 config 路径>`（Task-01 交付）；实机池不可达时以夹具复放核对方向性并在 verify: 注明 `[INFO_GAP] 实机数`，绝对数（157 等）留 owner 统一实机复测轮。
7. **不新建持久层文件**（B(ii) 从会话日志派生）；**不新建配置键**（E 仅扩 `strategy` 枚举值）；`runtime/`（learned.json/journals）不入库（.gitignore 已覆盖）。
8. **learned 数据安全**：除 A-1 的幂等 prune 与 GUI 既有「忘记」外，任何任务不得删除/改写票目；prune 必须幂等（二次运行返回 0）。
9. **执行纪律**：卡面外发现的问题只记录回报，不擅自扩范围；步骤行号以实施前 grep 复核为准（行号漂移以函数/锚文本定位）。

## 4 四指标重放量尺（Task-01 交付，全局引用）

```text
python tools/replay_metrics.py <config.toml> [--strategy smart|smart_weighted|...] [--json]
```

| 指标 | 定义 | 本轮基线（T-01 实测填入） | 认可方向 |
|---|---|---|---|
| 自动生效单元数 | level=learned 且 default_selected 的单元数 | **0** | A-2 后恒为 **0** |
| 多候选胜出依据分布 | 映射候选>1 的单元按 {priority, plot, decl_order, votes, unexpected} 归类 | priority=152、plot=0、decl_order=0、votes=0、unexpected=0 | A-2 后 **votes=0**；C-1 后 decl_order→0 |
| 默认勾选数 | default_selected 单元数 | **181**（实机 smart；分析口径 157） | E 上线后 smart_weighted 重放 **≈157**（诚实化失败模式=182–199，禁出现） |
| 票数闭合不一致对数 | 留痕后会话可触及、且票数与会话推演不符的 (题材键, 库) 对 | **0** | 只减不增；A-1 后恒为 0 |
| 最大目标库占比（辅） | plan 内最大 target_lib 单元占比（C-1 验收用） | **19.0%**（40/211；分析口径 41%） | C-1 后不得高于 41%（58% 方向即回退重排） |

T-01 实测（2026-11-26）：实机 `config.toml`（strategy=smart，源池 `E:\已刮削\待整理` 可达）只读重放；`--json` 同值复核；未写 plan.json / learned.json。

T-03 C-1 后实测（2026-11-26，owner 授权主审按拍板原则执行两组序重排：题材定位型在前、行为/元数据泛用型靠后，组内保持原相对序；config.toml 已备份 .bak-20261126）：门槛核对 decl_order=0 ✓、votes=0 ✓（代码保证生效于全表填充）、最大占比 19.0%→**22.3%**（≤41% 基线，远离 58% 失败方向；新头名 人妻=47/211，次位 中出=31、乱交=24、痴女=15）、默认勾选 **181 无变动**、自动生效/票数闭合=0 ✓。config 哈希变化 → plan.json freshness 失效，实机需重新扫描（owner 亲为）。

T-10 收口终值（2026-11-26，实机 smart 腿 + `--strategy` 双跑对照；runtime 零写入哈希核验通过）：自动生效 **0** ✓ ／胜出依据 priority=152、plot=0、decl_order=0、votes=0、unexpected=0 ✓（风险 #2 验证值）／默认勾选 smart **181** vs smart_weighted 双跑 **46**——硬断言「smart_weighted ≤ smart(实测181)」通过，失败带 182–199 未触发（分析锚 157 已漂移，按计划规则以实测为准）／票数闭合不一致 **0** ✓（风险 #6：实机无 learned.json=新增人工票恒 0，平凡成立；量尺算法恒零裁定见 decision-log 补记）／最大占比 **22.3%** ✓。风险 #1 记录：实机 strategy 当前值=smart，切换权留 owner 统一复测轮。

只读承诺：重放全程不写 plan.json / learned.json（build_plan 不 save；工具无任何 save 调用）。

## 5 任务总览（每任务=一卡）

| 任务 | 项 | 一句话 | 涉 GUI | 测试（新/改写） | 依赖 | 状态 |
|---|---|---|---|---|---|---|
| Task-01 | 量尺 | 离线重放四指标工具 tools/replay_metrics.py | 否 | 新 6 | 无 | ✅ |
| Task-02 | A-2 | 自学习去自动生效+票数退出破平手+人工改判停记票 | 是(文案) | 新 3 / 改写 5 | T-01 | ✅ |
| Task-03 | C-1 | owner 全量填优先级表（占位步骤+重放核对） | 否 | 0 | T-02 | ✅ |
| Task-04 | 留痕 | done 记录追加 provider/manual/orig_lib/title/year | 否 | 新 4 | T-02 | ✅ |
| Task-05 | E | 新策略值 smart_weighted+置信度诚实化+证据文案修正 | 是(下拉) | 新 8 | T-01 | ✅ |
| Task-06 | B(i) | 会话内同作品（片名+年份键）套用改判 | 是(提示) | 新 11 | T-04 | ✅ |
| Task-07 | A-1 | 学习票全面停记+旧票迁移+enabled 改义 | 是(文案) | 新 6 / 改写 3 | T-03, T-05 | ✅ |
| Task-08 | D | 别名扫描对话框「提升建议」（A-1 门控） | 是(对话框) | 新 5 | T-07 | ✅ |
| Task-09 | B(ii) | 跨扫描记忆派生（journal→plan 注记） | 否 | 新 8 | T-04 | ✅ |
| Task-10 | 收口 | 全量回归+四指标终值快照+文档扫尾 | 否 | 0 | T-01..09 | ✅（本卡） |

依赖序核对：A-2/C-1（T-02/T-03）→ 留痕/E（T-04/T-05）→ B(i)/A-1（T-06/T-07）→ D（T-08）；B(ii) 挂留痕后（T-09）；A-1 在 C-1 与 E 之后。✓

---

## Task-01 重放四指标量尺工具（无 GUI）

**目标**：交付 §4 量尺，使后续每卡验收有统一命令与可比数字。
**文件**：新增 `tools/replay_metrics.py`（模块级纯函数，CLI 入口 `main()`）；新增 `tests/test_replay_metrics.py`。
**Interfaces**：
- Consumes：`app.core.config.load_config`、`app.core.scanner.scan_source_root`、`app.core.planner.build_plan`（不 save）、`app.core.classifier.map_genres_ex / score_plot / _rank`（私有 `_rank` 导入，文件内注释说明允许）、`app.core.learned.load / votes_for`、`app.core.journal.read_entries / list_sessions`。
- Produces：`replay_metrics(cfg) -> dict`（五键：`auto_effective_units`、`winner_basis`、`default_selected`、`vote_closure_inconsistencies`、`top_target_share`）；`main(argv) -> int`。
- CLI：`--strategy` 覆盖 cfg.strategy 后再 build_plan（what-if 对比，不改配置文件）；`--json` 机器可读输出。

**票数闭合算法（钉死）**：读 journals——undo 会话（header meta.undoes）取其 done unit_id 集 = 回滚排除集；apply 会话按 header ts 升序，done 记录**含 title 且含 manual 字段**（留痕上线后）且 unit_id 未被回滚、且能按 unit_id（退 src_dir）对账当前冻结 plan 单元 → 取该单元 genres；`expected[(normalize_key(g), target_lib)] += 0 if manual else 1`。触及对 = expected>0 或存在 manual 触及；不一致对 = 触及对中 learned.json 实际票数 ≠ expected。未被留痕后会话触及的历史票目不计（`legacy_pairs` 另行输出不判错）。
**胜出依据算法（钉死）**：对 `len(set(强命中∪弱命中去重))>1` 的单元——level=plot → `plot`；否则分别计算无票键 `min(cand, key=(*_rank, decl))` 与带票键 `min(cand, key=(*_rank, -votes, decl))`：实际目标≠无票键且=带票键 → `votes`；实际目标=无票键且胜者表内位次并列 → `decl_order`，否则 `priority`；兜底 `unexpected`。

**测试表（tests/test_replay_metrics.py，importlib 挂载同 test_measure_no_nfo.py:8-14 范式）**：

| 测试名 | 输入 | 断言 |
|---|---|---|
| `test_replay_writes_nothing` | build_env+make_movie×2，无 plan.json 起跑 | 跑前后 learned.json/plan.json 均不存在或逐字节相同 |
| `test_replay_auto_effective_matches_plan` | learned 播 2 票人工票（`record(genres=["戏曲"], "科幻", manual=True)`），min_votes=2 | 输出 auto_effective_units == 1 == plan 中 learned 级 default_selected 数 |
| `test_replay_winner_basis_detects_votes` | 两库均未列入优先级表，learned 给喜剧 4 票 | 输出 winner_basis["votes"] ≥ 1（当前代码语义；Task-02 改写为 ==0） |
| `test_replay_default_selected_count` | 常规 2 库配置 | 输出 == plan["units"] 中 default_selected 计数 |
| `test_replay_closure_flags_manual_leak` | 手工造 post-留痕 done 记录（manual=true、title/genres 可对账）+ learned.json 同对有票 | vote_closure_inconsistencies == 1；`legacy_pairs` 分开计数 |
| `test_replay_strategy_override` | 同环境 `--strategy genre_only` | plan 全部 rule/fallback，无 plot 级（覆盖生效且未写配置文件） |

**步骤**：
- [x] 1. 新建 tests/test_replay_metrics.py 按上表写 6 个测试（红）：`python -m pytest tests/test_replay_metrics.py -q` → `6 failed`（模块不存在）。
- [x] 2. 实现 tools/replay_metrics.py：`replay_metrics(cfg: Config) -> dict`、`_winner_basis(...) -> str`、`_closure(...) -> dict`、`main(argv: list[str]) -> int`（argparse：config 路径/--strategy/--json；打印 §4 中文报表）。落点：文件顶部 sys.path 注入 PROJECT（同 tools/measure_no_nfo.py 范式）。
- [x] 3. 跑绿：`python -m pytest tests/test_replay_metrics.py -q` → `6 passed`。
- [x] 4. ruff/mypy：`python -m ruff check tools/replay_metrics.py tests/test_replay_metrics.py` → 0 项；`python -m mypy tools/replay_metrics.py` → errors 0（不超基线 149）。
- [x] 5. 全量：`python -m pytest -q` → `373 passed`（367+6）。
- [x] 6. 实机基线实测：`python tools/replay_metrics.py I:\CineSort\config.toml`（E 盘不可达则夹具跑 + verify: 标 `[INFO_GAP] 实机数`）→ 把四指标+占比填进 §4 基线列（commit 本文件）。
- [x] 7. commit：`feat(tools): 离线重放四指标量尺（D-20261125-05 每卡验收用）`，verify: 全量 367→373；Refs: D-20261125-05。显式 add 两文件。

---

## Task-02 A-2：自学习不再自动生效 + 票数退出破平手（涉 GUI 文案）

**目标**：classify 永不因票数自动生效/择优；人工改判不再记题材票；建议形态全面低置信；GUI/README 文案同步。
**文件与落点**（行号为当前锚，实施前复核）：
- `app/core/classifier.py:15`（import 去 votes_for）、`:164`（min_votes 变量退役）、`:166-181`（auto/soft 分流合并为 soft_hits 单路）、`:210`（兜底建议文案）、`:222-229` learned_pick（置信恒 "low"）、`:234-237`（破平手键删 votes）、`:252-254`（删「历史倾向」证据块）、`:282-289`（未映射路径序=摘要→建议→兜底，auto_hits 分支删除）。
- `app/core/planner.py:153-155`：default_selected 删 learned 子句 → `(dec.level == "rule" and dec.confidence != "low")`。
- `app/core/learned.py:43-60`：`record` 权重 `+= 2 if manual else 1` → `+= 1`（manual 仍计数）；模块 docstring 改「一律 +1 票，仅作建议」。
- `app/core/jobs.py:261-269`：`if cfg.learning.enabled:` 块内 record 调用改为**跳过人工改判单元**：`if u["id"] in overrides: continue`，其余确认单元 `manual=False` 记 1 票（A-1 落地前窗口期）。
- GUI 文案：`app/ui/plan_tab.py:295` hint → 「改判不再记自学习票；「执行选中」按改判后的目标库搬运。」；`app/ui/config_tab.py:150-154` tooltip 与 `:236` 标签 → 「自学习映射（仅作建议）」口径。
- `README.md:46`、`:114-115`：自学习段改为建议口径（不再「自动生效/默认勾选」）。
- `tests/test_viewmodel.py:15-26` make_unit 的 default_selected 缺省复刻删 learned 分支（原地改写，随 planner 同步）。

**Interfaces**：
- Consumes：`learned.best_for`（不变）；`learned.votes_for` 保留（replay 工具消费，classifier 不再 import）。
- Produces：`classify` 未映射路径输出建议 Decision（level=learned、confidence 恒 "low"）；`plan` 单元 default_selected 对 learned 级恒 False。

**测试表（8 项 = 5 改写 + 3 新增）**：

| 测试名（文件） | 断言 |
|---|---|
| `test_record_manual_counts_one_vote`（test_learned.py，改写 `test_record_votes_and_manual_weight`） | manual=False 后 manual=True 两次 record → votes==2、manual==1 |
| `test_learned_never_auto_effective_at_any_votes`（test_learned.py，改写 `test_learned_auto_hit_threshold`） | 2 票达标 → classify → level=="learned" 且 confidence=="low" 且 target=="武侠" |
| `test_multi_candidate_ignores_votes_decl_order_decides`（test_learned.py，改写 `test_smart_tie_break_by_votes_among_unprioritized`） | 两库未列入表、喜剧 4 票 → 胜者=武侠（声明顺序），evidence 无「历史倾向」 |
| `test_plan_learned_level_never_default_selected`（test_planner.py，新） | 播 2 票人工票 → build_plan 单元 level=="learned"、default_selected is False、status=="ready" |
| `test_apply_manual_override_records_no_votes`（test_flow.py，新） | 独有题材「戏曲」单元改判到科幻并 apply → learned.json 无「戏曲」键；同批无改判的确认单元仍记 1 票（窗口期语义，T-07 再改写归零） |
| `test_rule_evidence_no_votes_lines`（test_classifier.py，新） | 多候选+票数在场 → evidence 不含「历史倾向」且不含「票」行 |
| `test_replay_winner_basis_no_votes_after_a2`（test_replay_metrics.py，改写 `test_replay_winner_basis_detects_votes`） | 同种子 → winner_basis["votes"] == 0 且 decl_order ≥ 1 |
| `test_replay_auto_effective_zero_after_a2`（test_replay_metrics.py，改写 `test_replay_auto_effective_matches_plan`） | 2 票人工票 → auto_effective_units == 0 |

（test_learned.py:58-65 `test_learned_soft_below_threshold_loses_to_plot`、:82-88 `test_explicit_priority_beats_votes`、test_classifier.py:282-290 失效库建议、test_flow.py:71-76 确认沉淀断言——语义兼容保留，跑绿即证。）

**步骤**：
- [x] 1. 按表改写+新增 8 个测试（红）：`python -m pytest tests/test_learned.py tests/test_classifier.py tests/test_planner.py tests/test_flow.py tests/test_replay_metrics.py -q` → 表内 8 项 fail，其余绿。
- [x] 2. 最小实现，按落点清单逐处修改：classifier.py 八处（import/min_votes 退役/分流合并/兜底文案/learned_pick 置信/破平手键/删历史倾向块/未映射路径重排）+ planner.py:153-155 + learned.py 权重 + jobs.py 跳过改判单元 + test_viewmodel.make_unit 同步。
- [x] 3. 跑绿定向：同步骤 1 命令 → `all passed`。
- [x] 4. GUI 文案四处（plan_tab/config_tab×2/README×2 行段）替换。
- [x] 5. ruff 改动文件 0 项；`python -m pytest -q` → `376 passed`（373+3 净新增）。
- [x] 6. 离屏复验：`$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_config_tab.py tests/test_plan_tab.py -q` → all passed（钉旧文案者原地改写，不减量）。
- [x] 7. 重放核对：`python tools/replay_metrics.py I:\CineSort\config.toml` → 自动生效 0、winner_basis 无 votes；默认勾选数较 T-01 基线的变动记录进 verify:。
- [x] 8. commit：`feat(classify): A-2 自学习只作建议、票数退出多候选择优（owner 拍板）`；verify: 全量 373→376 + 四指标前后值；GUI 已验证（离屏）；Refs: D-20261125-05。

---

## Task-03 C-1：优先级表按类全量填充（owner 纯配置任务，无代码）

**目标**：owner 把全部库名填入实机 `genre_priority`（排序 owner 定），使多候选择优全部走显式位次；本卡零代码、零 commit（config.toml 不入库，.gitignore:10）。
**文件**：owner 实机 config.toml（I:\CineSort\config.toml 或实机安装位，owner 指认其一）；本计划 §4 基线表（数据回填不 commit 代码）。

**步骤**：
- [x] 1. 跑基线：`python tools/replay_metrics.py <owner 实机 config>` → 记录默认勾选数 / 最大目标库占比（当前 41% 口径）/ decl_order 数。
- [x] 2. **[owner 占位步骤] owner 填表**：把 genre_priority 填到全部现存库名。两条警示必须先行呈报（呈 owner 时以选项形式逐项呈报并附后果）：①不得按默认顺序全填——最大粗桶占比会 41%→58%；②单库垫底会把判定转移给另一行为类库（20→48）。排序原则 owner 定，执行者不得代拟顺序。**owner 已拍板（2026-11-26）：题材定位型在前、行为/元数据泛用型靠后——按此填表即可免再问；两条警示仍适用，填完跑步骤 3 核对。**
- [x] 3. 重放核对：同命令 → 断言 `winner_basis` 中 `decl_order == 0`、`votes == 0`；`最大目标库占比 ≤ 41% 基线`（若向 58% 方向 → 回退 owner 重排，重跑本步）；默认勾选数变动记录。
- [x] 4. 确认无代码面改动：`git status` → 除本计划文档数据列外无源码差异（config.toml 未跟踪，不入库）。
- [x] 5. 卡面记录：填表后配置哈希变化会使旧计划过期（`check_plan_freshness` 拒执行），属预期——提示 owner 需重新扫描，不代跑。

---

## Task-04 留痕：done 日志追加五字段（无 GUI）

**目标**：执行会话的每条 done 记录携带 `provider / manual / orig_lib / title / year`，成为 B(i) 一致性门与 B(ii) 派生的唯一数据地基。
**文件与落点**：
- `app/core/jobs.py:138-141`（run_apply 内、:159 改写循环前）：`orig_lib = {u["id"]: u["target_lib"] for u in units}`（必须先于 :160-174 的 in-place 改写截取）。
- `app/core/jobs.py:242-244`（jr.done 调用）追加：`provider=u.get("provider"), manual=u["id"] in overrides, orig_lib=orig_lib[u["id"]], title=u.get("title"), year=u.get("year")`。
- `app/core/journal.py`：无签名变更（done 为 **kw 透传）；仅补 docstring 说明五字段语义。

**Interfaces**：
- Consumes：既有 done 记录字段（src_dir/dst_dir/kind/mode/files/bytes/target_lib）。
- Produces：post-留痕 done 记录 = 旧字段 + 五新字段；旧记录无 title/manual 字段 → B(ii)/量尺按「留痕上线前」判别（天然跳过）。

**测试表**：

| 测试名（文件） | 断言 |
|---|---|
| `test_done_entry_carries_override_trace`（test_journal.py，新） | apply 单元改判「科幻」→动作 → done 记录 manual is True、orig_lib=="科幻"、target_lib=="动作"、provider=="tmdb:…"、title/year 与单元一致 |
| `test_done_entry_confirm_trace`（test_journal.py，新） | 无改判执行 → manual is False、orig_lib==target_lib |
| `test_apply_journal_trace_flow`（test_flow.py，新） | 全链路 apply 后 `done_entries` 首条含五字段（回滚链路不回归） |
| `test_old_journal_still_readable`（test_journal.py，新） | 手工旧格式 jsonl（无新字段）→ read_entries 正常、list_sessions 不炸 |

**步骤**：
- [x] 1. 写 4 测试（红）：`python -m pytest tests/test_journal.py tests/test_flow.py -q` → 新 4 项 fail。
- [x] 2. 最小实现：jobs.py 两处（截取 orig_lib + done 追加五字段）；journal.py docstring。
- [x] 3. 跑绿定向 → all passed。
- [x] 4. ruff 改动文件 0；全量 `python -m pytest -q` → `380 passed`（376+4）。
- [x] 5. 重放核对：`python tools/replay_metrics.py <实机 config>` → 四指标与 T-02 后基线逐项一致（本卡不触分类路径），差异即停并回报。
- [x] 6. commit：`feat(journal): done 留痕五字段（provider/人工/原判定库/片名/年份）`；verify: 全量 376→380 + 四指标一致；Refs: D-20261125-05。

---

## Task-05 E：摘要择优新策略值 smart_weighted + 置信度诚实化 + 证据文案修正（涉 GUI 下拉）

**目标**：新增 `strategy="smart_weighted"`——多候选择优只信加权词；胜出与回退判定均默认不勾（诚实化）；修「优先级第 1 位」文案；旧 smart 行为逐字不变。
**文件与落点**：
- `app/core/config.py:20`：`STRATEGIES = ("smart", "smart_weighted", "priority", "genre_only")`。
- `app/core/classifier.py`：
  - `:83` `score_plot(plot, cfg, weighted_only=False)`（默认 False=旧行为；True 时只累计 `keywords_weighted`，命中明细带「加权」前缀）。
  - `:183` 后新增一行：`mc_weighted = score_plot(plot, cfg, weighted_only=True) if (cfg.plot.enabled and cfg.strategy == "smart_weighted") else []`。
  - `:214` `plot_pick(prefix, top=None)`：`name, sc, hits = top or best`（smart 传 None=旧行为逐字不变）。
  - `:273-279` 多候选分支：条件改 `cfg.strategy in ("smart", "smart_weighted")`；评分源 = `scoring`（smart）/`mc_weighted`（smart_weighted）；达标且领先≥1.0 → `plot_pick(..., top=cand[0])`（理由后缀「（仅加权词）」）；否则 → `rule_pick("多题材候选，摘要评分不足以区分，按优先级表", force_low=(strategy=="smart_weighted"), mc_scores=mc_weighted)`。
  - `:231` `rule_pick(extra="", force_low=False, mc_scores=None)`；`:260` `conf = "low" if (weak_only or force_low) else "high"`；`:257-259` 摘要评分证据行数据源改 `(mc_scores if mc_scores is not None else scoring)`。
  - `:238-244` 文案修正：胜者表内 → `（优先级第 {rank[1]+1} 位）`；表外 → `（未列入优先级表）`（weak 行 :249 与其余不变）。
- GUI：`app/ui/config_tab.py:84` combo 追加 `"smart_weighted"`（序=smart 之后）；`:127-130` 策略 tooltip 追加一句「smart_weighted：多库命中时只用加权关键词评分择优（普通关键词不参与，避免库名预填偏向场面词）；判不出时按优先级表且默认不勾选」。
- 文档：`config.example.toml:12-13` 策略注释块加一行；`README.md:42`、`:88` 同步。

**Interfaces**：
- Consumes：`Library.keywords_weighted`（既有）；`cfg.strategy` 新枚举值。
- Produces：`score_plot(plot, cfg, weighted_only=False)`；`plot_pick(prefix, top=None)`；`rule_pick(extra, force_low, mc_scores)`。plan 端无新字段（smart_weighted 下胜出行 level=plot 或 confidence=low，default_selected 自然 False）。

**测试表**：

| 测试名（文件） | 断言 |
|---|---|
| `test_strategy_accepts_smart_weighted`（test_config.py，新） | `strategy="smart_weighted"` 加载通过；`"bogus"` 仍 ConfigError（既有断言不减） |
| `test_smart_weighted_ignores_plain_keywords`（test_classifier.py，新） | plot 含普通关键词命中（库名词）但无加权词 → 不择优 → rule 且 confidence=="low" |
| `test_smart_weighted_weighted_word_decides`（test_classifier.py，新） | 加权词独高分 → level=="plot"、target=加权库、证据含「仅加权词」 |
| `test_smart_weighted_margin_discipline`（test_classifier.py，新） | 候选间加权分差 0.9 → 回退 rule/low；分差恰 1.0 → 择优（阈值两侧边界钉） |
| `test_smart_weighted_default_not_selected`（test_planner.py，新） | 两路径（plot 胜出/低置信回退）build_plan 后 default_selected 均 False（157 红线的结构性钉） |
| `test_smart_unchanged_full_path`（test_classifier.py，新） | smart+普通关键词择优 → plot_pick 用全局 best（旧行为快照：多候选含非候选库高分时 smart 仍选全局 top——现状快照钉，防顺手「修」） |
| `test_evidence_priority_text_fixed`（test_classifier.py，新） | 胜者未列入表 → 证据无「优先级第」字样、含「未列入优先级表」；列入 → 「优先级第 2 位」位次正确 |
| `test_config_tab_strategy_items`（test_config_tab.py，新，离屏） | combo items == ["smart","smart_weighted","priority","genre_only"] |

**步骤**：
- [x] 1. 写 8 测试（红）：`python -m pytest tests/test_config.py tests/test_classifier.py tests/test_planner.py tests/test_config_tab.py -q` → 新 8 fail。
- [x] 2. 最小实现，按落点清单：config.py:20 + classifier.py 六处（score_plot 参数/plot_pick 参数/rule_pick 参数与 conf/多候选分支/证据数据源/文案修正）。
- [x] 3. 跑绿定向 → all passed；补 GUI combo + tooltip + example/README 文案。
- [x] 4. ruff 改动文件 0；mypy ≤149；全量 → `388 passed`（380+8）。
- [x] 5. 离屏复验（GUI）：`$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_config_tab.py -q` → all passed。
- [x] 6. 重放核对（157 红线）：`python tools/replay_metrics.py <实机 config> --strategy smart_weighted` 与 `--strategy smart` 双跑 → 两口径默认勾选数一致（≈157；实机不可达则以夹具断言「smart_weighted ≤ smart」+ verify: 标注）；若出现 182–199 方向立即停卡回报（诚实化失败模式）。
- [x] 7. commit：`feat(classify): E 新策略值 smart_weighted+置信度诚实化（旧 smart 不变）`；verify: 全量 380→388 + 双口径默认勾选数；GUI 已验证（离屏）；Refs: D-20261125-05。

---

## Task-06 B(i)：会话内同作品套用改判（套用键=片名+年份，id 一致性门；涉 GUI 提示）

**目标**：详情面板对单元 X 改判到库 L 时，同片名+同年份的兄弟单元自动写同一 override（不自动勾选；id 不一致/已执行/复合/硬冲突/落点互撞者不套用），据前置核实修正函实现。
**文件与落点**：
- `app/ui/viewmodel.py`：顶部 `from app.core.nfo import normalize_key`；import 行（:16-22）补 `ST_MULTI`；新增模块级 `_work_key(u) -> tuple[str, int | None]`；`PlanViewModel` 新增 `sibling_overrides(unit_id: str, lib: str) -> list[str]`；`set_override`（:243-250）尾部套用并**返回 int（套用数，原返回 None 向后兼容）**。
- `app/ui/plan_tab.py:702-706` `_on_override_changed`：接收返回值，>0 时 `self.toast(f"已套用到 {n} 部同作品单元（不自动勾选）")`；:295 hint 在 T-02 文案后追加「同片名+同年份单元自动套用改判」。
- 兄弟资格（钉死）：`u["id"] != unit_id` 且 `_work_key(u)==_work_key(me)`；`status in (READY, ST_MULTI)`；id 一致性门 `u.get("provider") is None or me.get("provider") is None or u["provider"]==me["provider"]`；落点互撞门 `key=(lib, u.get("actress"), u.get("dst_name"))` 组内去重。`set_override_many` 不触发；`lib=None` 撤销不联动。

**Interfaces**：
- Consumes：plan 单元 `title/year/provider/status/actress/dst_name`（planner.py:125-161 既有字段）。
- Produces：`PlanViewModel.sibling_overrides(unit_id, lib) -> list[str]`；`set_override(...) -> int`。

**测试表**：

| 测试名（文件） | 断言 |
|---|---|
| `test_sibling_apply_same_title_year_id`（test_viewmodel.py，新） | 3 同作品单元（同 title/year/provider）→ set_override(u1,"科幻") → u2/u3 override 生效、返回 2、**不在 checked**、effective_target_lib=="科幻" |
| `test_sibling_provider_mismatch_not_applied`（test_viewmodel.py，新） | 同 title/year、provider 不同（分集/剧集反例）→ 返回 0、无 override（负例钉） |
| `test_sibling_bare_id_none_consistent`（test_viewmodel.py，新） | 双方 provider 均为 None → 套用（片名+年份键独立成立） |
| `test_sibling_applied_and_composite_excluded`（test_viewmodel.py，新） | 兄弟 status=applied / composite(ST_BATCH) → 不套用（「假同 id 不得跨成因套用」负例钉） |
| `test_sibling_stmulti_receives_unchecked`（test_viewmodel.py，新） | 兄弟 ST_MULTI → 套用且不在 checked（多版本主场景） |
| `test_sibling_dst_collision_skipped`（test_viewmodel.py，新） | 两兄弟同 (lib,actress,dst_name) → 第二个跳过（落点冲突不套用） |
| `test_sibling_conflict_status_skipped`（test_viewmodel.py，新） | 兄弟 ST_CONFLICT/ST_PLACED/ST_INCOMPLETE → 不套用 |
| `test_clear_override_no_propagation`（test_viewmodel.py，新） | 撤销 u1 改判 → 兄弟 override 保留（不联动撤销） |
| `test_set_override_many_no_expansion`（test_viewmodel.py，新） | 批量改判仅作用于给定 id 集，不外扩 |
| `test_fullwidth_title_key_normalized`（test_viewmodel.py，新） | 「Ｔｅｓｔ Ｍｏｖｉｅ ２」与「Test Movie 2」同年份 → 同键互套（normalize_key 全半角钉） |
| `test_override_applies_sibling_toast`（test_plan_tab.py，新，离屏） | widget 驱动 d_override 选库 → toast 文案 + 兄弟行目标库列显示改判库 |

**步骤**：
- [x] 1. 写 11 测试（红）：`python -m pytest tests/test_viewmodel.py tests/test_plan_tab.py -q` → 新 11 fail。
- [x] 2. 最小实现 viewmodel（import 补齐/_work_key/sibling_overrides/set_override 返回值）；跑绿。
- [x] 3. plan_tab 接线（toast+hint）；离屏跑绿 test_plan_tab。
- [x] 4. ruff 改动文件 0；mypy ≤149；全量 → `399 passed`（388+11）。
- [x] 5. 重放核对：四指标与 T-05 后基线逐项一致（B(i) 不触分类路径），差异即停。
- [x] 6. commit：`feat(ui): B(i) 同作品（片名+年份）会话内套用改判（id 一致性门）`；verify: 全量 388→399；GUI 已验证（离屏）；Refs: D-20261125-05。

---

## Task-07 A-1：学习票全面停记 + 旧票迁移 + enabled 改义（必须在 C-1、E 之后；涉 GUI 文案）

**目标**：执行侧不再向 learned.json 记任何题材键票（人工/确认一并停记）；旧票一次性幂等迁移（prune 掉已被别名表/库名覆盖的死键）；`[learning].enabled` 改义为建议门控；`min_votes` 转作 D 的提升阈值。
**文件与落点**：
- `app/core/jobs.py:258-269`：删除整个 `if cfg.learning.enabled:` record 块（注释改「A-1 起停记；人工信号在会话留痕」）。
- `app/core/learned.py`：删除 `record()`（:43-60）；新增 `prune_legacy(runtime_dir: Path, covered: set[str]) -> int`（load→按 normalize_key 删 covered 键的 entries→空 entries 项一并删→save→返回删除数；幂等=二次调用返回 0）；模块 docstring 改 legacy 口径。
- `app/core/classifier.py`：新增 `covered_keys(cfg) -> set[str]` = `set(alias_map(cfg)) | set(weak_alias_map(cfg))`。
- `app/core/jobs.py run_scan`（:120-135 尾部，save_plan 之后）：`n = learned_store.prune_legacy(cfg.runtime_dir, covered_keys(cfg))` + `job.log(f"旧票迁移：清理已被别名表覆盖的学习票 {n} 条")`。
- `app/core/planner.py:86`：`learned = learned_store.load(cfg.runtime_dir) if cfg.learning.enabled else {}`（enabled 改义=建议门控）。
- GUI/文档：`app/ui/config_tab.py:150-154` tooltip 改「自学习建议开关：历史学习票仅作低置信建议展示，不再自动生效、不再记新票；阈值用于『提升建议』」；`:236` 标签 → 「自学习映射（仅作建议，不再记新票）」；`README.md:110-115` 同口径。
- 测试播种改造：`tests/conftest.py` 新增 `seed_learned(tmp_path, entries: dict)`（用 `learned_store.save` 直写构造票目）；本卡把 tests 内所有 `learned.record(...)` 播种调用改为该 helper（原地改写不减量——record 退役后唯一播种路径）。

**Interfaces**：
- Consumes：既有 load/save/items/forget/best_for/votes_for（全部保留——GUI 清单与量尺仍消费）。
- Produces：`learned.prune_legacy(runtime_dir, covered) -> int`；`classifier.covered_keys(cfg) -> set[str]`；learned.json 冻结（无新票写入路径）；`tests/conftest.py seed_learned(tmp_path, entries)`。

**测试表（9 项 = 3 改写 + 6 新增）**：

| 测试名（文件） | 断言 |
|---|---|
| `test_record_retired_no_votes_written`（test_flow.py，改写 test_flow.py:71-76 沉淀断言） | 全链路 apply（确认+改判）→ learned.json 不存在或 entries 为空；`state.state_snapshot()["learned"]==[]` |
| `test_record_retired`（test_learned.py，改写 `test_record_manual_counts_one_vote`） | `hasattr(ls, "record") is False`；seed_learned 构造的票目 apply 后逐字节不变 |
| `test_apply_records_nothing_at_all`（test_flow.py，改写 T-02 的 `test_apply_manual_override_records_no_votes`） | 确认单元也不记票：apply 后 learned.json 无新增键 |
| `test_prune_drops_covered_keeps_rest`（test_learned.py，新，seed_learned 播种） | 「武侠」（被库名覆盖）与「西部」（未覆盖）→ prune → 仅剩西部，返回 1；二次调用返回 0（幂等） |
| `test_prune_empty_entry_removed`（test_learned.py，新） | entry 全部 libs 为空壳 → prune 清掉空 entries 项 |
| `test_prune_triggered_by_scan`（test_flow.py，新） | 预置含 covered 键的 learned.json → start_scan → 文件仅剩未覆盖键、日志含「旧票迁移」 |
| `test_learning_disabled_gates_suggestions`（test_planner.py，新） | enabled=False + seed_learned 播票 → build_plan 无 learned 级单元（建议门控钉） |
| `test_config_tab_learning_texts`（test_config_tab.py，新，离屏） | 静态断言新 tooltip/标签含「仅作建议」、不含「自动生效」 |
| `test_replay_closure_zero_after_a1`（test_replay_metrics.py，新，seed_learned 播种） | post-留痕确认+改判会话触及对票数恒 0 → 不一致对 == 0 |

**步骤**：
- [x] 1. conftest 加 `seed_learned` helper + 按表改写/新增 9 项测试（红）：`python -m pytest tests/test_learned.py tests/test_flow.py tests/test_planner.py tests/test_config_tab.py tests/test_replay_metrics.py -q` → 表内 9 项 fail（record 退役后既有播种调用同步换 helper）。
- [x] 2. 最小实现四处：jobs 删 record 块+run_scan 接 prune；learned 删 record/增 prune_legacy；classifier 增 covered_keys；planner:86 enabled 门控。
- [x] 3. 跑绿定向：上述命令 → all passed。
- [x] 4. GUI/README 文案替换；ruff 改动文件 0；mypy ≤149；全量 → `405 passed`（399+6）。
- [x] 5. 重放核对：learned.json 新增人工票数==0（风险 #6 验证项）；票数闭合不一致对数==0；自动生效 0；实机 prune 条数在实机复测轮核对。
- [x] 6. commit：`feat(classify): A-1 学习票停记+旧票迁移+learning.enabled 改义`；verify: 全量 399→405 + 风险#6 验证值；GUI 已验证（离屏）；Refs: D-20261125-05。

---

## Task-08 D：别名扫描分析对话框「提升建议」（被 A-1 门控；涉 GUI 对话框）

**目标**：对话框新增「提升建议」页：列出 A-1 迁移幸存、票数 ≥ `learning.min_votes`、未被别名表/库名覆盖、目标库仍存在的真实题材信号，一键提升为强/弱别名（走既有分拣→统一保存管线）；当前实机满足条件为 0 对，空态文案上线。
**文件与落点**：
- `app/core/alias_scan.py`：新增 `promotion_candidates(learned: dict, cfg: Config) -> list[dict]`（bar=`max(cfg.learning.min_votes,1)`；过滤 covered（复用 Task-07 `covered_keys`）、`lib not in cfg.libraries`、votes<bar；行 `{genre, key, lib, votes, manual}`，按 (-votes, genre) 排序）。
- `app/core/alias_scan.py scan_alias_candidates`（:43-93）：返回 dict 增键 `"promotions": promotion_candidates(learned_store.load(cfg.runtime_dir), cfg)`（load 幂等只读；learned_store 经 alias_scan 顶部 import）。
- `app/ui/config_tab.py:479-491`：无需新调用（promotions 随 candidates 透传）；`filter_covered`（:96-106）不得误伤 promotions 键（其只处理 "genres"——回归断言钉）。
- `app/ui/alias_scan_dialog.py`：新增第三个 tab「提升建议」（QTableWidget：题材/目标库/票数/人工次数 + 按钮「提升为强别名」「提升为弱别名」→ 选中行写入既有 `tbl_staged`（候选=题材原样、目标库=行内 lib、表别=强/弱）；空列表 → 页内 QLabel 空态：「当前无满足条件的提升建议（真实题材信号票数达阈值且未被别名表覆盖）」。

**Interfaces**：
- Consumes：`learned.load`（entries→libs→votes/manual 形态）、`classifier.covered_keys`、既有 staged 清单与 `_save_all` 管线（alias_scan_dialog.py:163-179）。
- Produces：`alias_scan.promotion_candidates(learned, cfg) -> list[dict]`；candidates dict 新键 `promotions`。

**测试表**：

| 测试名（文件） | 断言 |
|---|---|
| `test_promotion_candidates_filters`（test_alias_scan.py，新，seed_learned 播种） | 播票（covered 键 / votes<bar / 悬空库 / 正常票）→ 仅正常票行返回，字段与排序正确 |
| `test_promotion_candidates_empty_store`（test_alias_scan.py，新） | learned 空 → `[]`（当前实机 0 对的形态钉） |
| `test_scan_alias_candidates_carries_promotions`（test_alias_scan.py，新） | scan_alias_candidates 返回含 promotions 键；`filter_covered` 后 promotions 不受影响 |
| `test_dialog_promotions_empty_hint`（test_alias_scan_dialog.py，新，离屏） | promotions=[] → 第三 tab 空态文案在场 |
| `test_dialog_promotion_stages_into_list`（test_alias_scan_dialog.py，新，离屏） | 合成 promotions 2 行 → 选中→「提升为强别名」→ tbl_staged 增 2 行（表别=强）→ 统一保存回调收到对应行 |

**步骤**：
- [x] 1. 写 5 测试（红）：`python -m pytest tests/test_alias_scan.py tests/test_alias_scan_dialog.py -q` → 新 5 fail。
- [x] 2. 最小实现 core（promotion_candidates + scan 键）；跑绿 test_alias_scan。
- [x] 3. 对话框 UI（tab+空态+提升按钮接线既有 staged 管线）；离屏跑绿 test_alias_scan_dialog。
- [x] 4. ruff 改动文件 0；全量 → `410 passed`（405+5）。
- [x] 5. 重放核对：四指标与 T-07 后基线逐项一致；实机重放记录 promotions==0（决策原文口径）。
- [x] 6. commit：`feat(ui): D 别名扫描分析新增提升建议页（A-1 门控，真实题材信号）`；verify: 全量 405→410 + promotions 实测数；GUI 已验证（离屏）；Refs: D-20261125-05。

---

## Task-09 B(ii)：跨扫描记忆从会话日志派生（无 GUI，注记走既有 notes 渲染）

**目标**：从 journals 派生「同作品人工改判」记忆（键同 B(i)），扫描建计划时给命中单元注记建议（不 override、不默认勾选）；只认留痕上线后的执行；被回滚的 unit_id 不派生。
**文件与落点**：
- `app/core/journal.py`：顶部 `from .nfo import normalize_key`；新增 `derive_memory(journals_dir: Path) -> dict[tuple[str, int | None], dict]`——undo 会话（header meta.undoes）取 done unit_id 集为回滚排除集；apply 会话按 header ts 升序，done 记录须同时含 `title` 与 `manual` 字段（旧格式天然跳过）、`manual is True`、unit_id 不在排除集 → `mem[(normalize_key(title), year)] = {"lib": target_lib, "sid": header sid, "ts": header ts}`（后到会话覆盖）。
- `app/core/planner.py`：import `derive_memory`；build_plan（:86-87 附近）`memory = derive_memory(cfg.runtime_dir / "journals")`；循环内（:125-161 plan_units.append 前）：命中（键=（normalize_key(u.title), u.year)）→ `unotes.append(f"跨扫描记忆：该片此前人工改判归入『{hit['lib']}』（会话 {hit['sid']}），可在详情面板改判采纳")` 且 plan 单元新增字段 `"memory_lib": hit["lib"]`（未命中单元不写该键）。
- 不改 viewmodel/plan_tab（notes 既渲染、改判既交互）。

**Interfaces**：
- Consumes：留痕五字段（Task-04）；`normalize_key`。
- Produces：`journal.derive_memory(journals_dir) -> dict[(str, int|None), {"lib","sid","ts"}]`；plan 单元可选字段 `memory_lib` + notes 注记。

**测试表**：

| 测试名（文件） | 断言 |
|---|---|
| `test_derive_manual_only`（test_journal.py，新） | manual=False 的 done 记录 → 不派生 |
| `test_derive_skips_pre_trace_entries`（test_journal.py，新） | done 无 title/manual 字段（留痕前旧格式）→ 跳过不炸 |
| `test_derive_excludes_undone`（test_journal.py，新） | apply 会话 + 对应 undo 会话 → 该 unit 不派生（风险 #4 钉） |
| `test_derive_partial_undo`（test_journal.py，新） | 3 单元 apply、undo 回滚 1 → 其余 2 派生 |
| `test_derive_last_session_wins`（test_journal.py，新） | 两 apply 同作品不同库 → ts 较后者胜 |
| `test_plan_memory_note_no_side_effects`（test_planner.py，新） | 命中单元：notes 含「跨扫描记忆」、`memory_lib=="动作"`、target_lib 不变、default_selected 不变；未命中单元无 memory_lib 键 |
| `test_plan_memory_key_normalization`（test_planner.py，新） | 会话片名「Ｔｅｓｔ Ｍｏｖｉｅ」vs 新单元「Test Movie」同年 → 命中（全半角键钉） |
| `test_rescan_new_batch_suggests_memory`（test_flow.py，新） | 改判执行→源重建同 title/year 新副本目录→重扫 → 新单元带记忆注记（同作品后续批次命中面） |

**步骤**：
- [x] 1. 写 8 测试（红）：`python -m pytest tests/test_journal.py tests/test_planner.py tests/test_flow.py -q` → 新 8 fail。
- [x] 2. 最小实现 journal.derive_memory + planner 注记；跑绿定向 → all passed。
- [x] 3. ruff 改动文件 0；mypy ≤149；全量 → `418 passed`（410+8）。
- [x] 4. 重放核对：四指标与 T-08 后基线逐项一致（memory 只加注记不改判定）；差异即停。
- [x] 5. commit：`feat(core): B(ii) 跨扫描记忆从会话日志派生（回滚排除/留痕前跳过）`；verify: 全量 410→418；Refs: D-20261125-05。

---

## Task-10 收口：全量回归 + 四指标终值快照 + 文档扫尾（无 GUI）

**目标**：本轮五项全部落地后的统一校验与记录；实机复测不在本卡（owner 统一安排在全部落地后）。
**步骤**：
- [x] 1. ruff 全仓：`python -m ruff check .` → `All checks passed`（不高于既有基线）。
- [x] 2. mypy：`python -m mypy app` → errors ≤ 149。
- [x] 3. 全量：`python -m pytest -q` → ≥ `418 passed`；`python -m pytest --collect-only -q` 计数一致（防收集漂移）。
- [x] 4. 离屏冒烟：`$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_plan_tab.py tests/test_config_tab.py tests/test_exec_tab.py tests/test_doctor_tab.py -q` → all passed。
- [x] 5. 四指标终值快照：`python tools/replay_metrics.py <实机 config>`（+ `--strategy smart_weighted` 对照）→ 断言：自动生效 0；winner_basis 无 votes；票数闭合不一致 0；smart_weighted 默认勾选数 ≈ smart 口径；全部终值回填 §4 基线表下一行「终值」，并核对 §6 风险列 1/2/6 的验证值（策略实机取值=风险 #1 留 owner 复测轮，记录当前值）。
- [x] 6. 文档扫尾：README 交叉核对（自学习段/策略表/自学习配置表三处口径与代码一致）；本计划 §5 表格逐卡打勾；decision-log 由主模型收口时补记（本卡不改 decision-log）。
- [x] 7. commit（仅文档/计划数据列与可能的测试注释修正）：`docs(classify): 五项调整收口快照与计划回填`；verify: 全量 N、四指标终值、ruff/mypy 基线；Refs: D-20261125-05。

---

## 6 风险与跟踪（承接 D-20261125-05 后续风险列，本计划落点）

| # | 风险条目（真值原文要义） | 本计划落点/验证 |
|---|---|---|
| 1 | E 默认不生效，owner 需切换实机 strategy | Task-05 不改默认值；Task-10 记录实机取值 |
| 2 | 票数退出多候选择优须代码保证，不依赖填全表 | Task-02 删 votes 键 + `test_multi_candidate_ignores_votes_decl_order_decides`（两库均未列入表时仍无票数参与） |
| 3 | C-1 不得按默认顺序全填（41%→58%）；纯配置不经代码验证链 | Task-03 警示前置呈报 + 重放核对（decl_order==0、占比 ≤41% 基线） |
| 4 | B(ii) 只对留痕上线后执行生效；被回滚会话不得派生；验证=单测 | Task-09 `test_derive_skips_pre_trace_entries` / `test_derive_excludes_undone` / `test_derive_partial_undo` |
| 5 | 同 provider id 多单元成因未核实，B 开工前补查 | 已核实（2026-11-25 修正函）：B(i) 键改片名+年份、id 降一致性门；负例钉于 Task-06 测试表 |
| 6 | 窗口期批量执行累积单片票；验证=learned.json 新增人工票数 | Task-02 即停人工记票；Task-07 全面停记后该数恒 0（verify: 记录） |
| 7 | 手工操作量预计不减少（80% 落点不在候选内） | 不在本计划范围；如需降须另立信号源议题并复议 D-20261109-01（owner 知情拍板） |
| 8 | 界面口径「无跨会话级行集视图」与 owner 截图不符 | 留终验 GUI 黑盒验证轮（owner 统一实机复测），本计划不动界面清单 |
| 9 | 证据文案「优先级第 1 位」 | Task-05 `test_evidence_priority_text_fixed` |

定读披露（供 owner 评审）：§2.2 之 3（A-1 停记范围=人工+确认一并）、之 4（新值命名 smart_weighted 与未区分回退降置信低）、之 6（回滚会话不派生导致「回滚后重扫」命中面仅在存在未回滚同作品会话时成立）三处为计划层落法，未逐字见于决策条目；如 owner 另有口径，改对应任务面即可，不影响其余任务。

## 7 测试基线账户

| 卡 | 前 | 后 | 净增 |
|---|---|---|---|
| Task-01 | 367 | 373 | +6 |
| Task-02 | 373 | 376 | +3（含改写 5 归零） |
| Task-04 | 376 | 380 | +4 |
| Task-05 | 380 | 388 | +8 |
| Task-06 | 388 | 399 | +11 |
| Task-07 | 399 | 405 | +6（含改写 3 归零 + conftest helper） |
| Task-08 | 405 | 410 | +5 |
| Task-09 | 410 | 418 | +8 |
| Task-10 | 418 | ≥418 | 0（收口只允许 ≥） |

全量目标 **≥ 418 passed**（367+51）；任何卡实测与本表不符时，就高不就低、只增不减口径不变，差异记 verify:。

T-10 收口实测链（分析起点锚 367 vs 实测起点 379=漂移 12，按上条规则以实测为锚）：T-01 379→385；T-02 →388；T-04 →392；T-05 →400；T-06 →411；T-07 →417；T-08 →422；T-09 →**430**；T-10 收口实测 **430 passed**，`--collect-only -q` 计数一致（无 skip/xfail）。mypy app 全程 149 持平无新增；ruff 全仓 0。

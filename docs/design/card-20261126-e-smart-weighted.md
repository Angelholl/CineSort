# Task-05 卡面：E 新策略值 smart_weighted + 置信度诚实化 + 证据文案修正（涉 GUI 下拉）

- 决策真值：`docs/decision-log.md` **D-20261125-05** ｜ 实施计划：`docs/plans/2026-11-25-classify-adjustments.md` Task-05
- 卡状态：待执行 ｜ 依赖：Task-01（量尺）✓；前置 T-02/T-03/T-04 已按串行序收口

## 一、根因与目标

新增 `strategy="smart_weighted"`——多候选择优只信加权关键词（`keywords_weighted`，owner 手工维护），普通 keywords（库名预填所在地）不参与（直击「库名预填偏向场面词」病灶）；择优胜出行按摘要判（level=plot、默认不勾）；加权词判不出时回退优先级表且**置信度诚实化=低**（默认不勾）。旧 `smart` 全链路行为逐字不变。默认不生效（实机 strategy 仍为 smart，owner 复测轮自行切换）。顺带修证据文案「优先级第 1 位」。

## 二、改动文件与落点（行号为写卡时锚，实施前 grep 复核）

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

**Interfaces**：Consumes=`Library.keywords_weighted`（既有）、`cfg.strategy` 新枚举值；Produces=`score_plot(plot, cfg, weighted_only=False)`、`plot_pick(prefix, top=None)`、`rule_pick(extra, force_low, mc_scores)`。plan 端无新字段（smart_weighted 下胜出行 level=plot 或 confidence=low，default_selected 自然 False）。

## 三、先红后绿回归测试（新增 8，基线只增不减）

| 测试名（文件） | 断言 |
|---|---|
| `test_strategy_accepts_smart_weighted`（test_config.py，新） | `strategy="smart_weighted"` 加载通过；`"bogus"` 仍 ConfigError（既有断言不减） |
| `test_smart_weighted_ignores_plain_keywords`（test_classifier.py，新） | plot 含普通关键词命中（库名词）但无加权词 → 不择优 → rule 且 confidence=="low" |
| `test_smart_weighted_weighted_word_decides`（test_classifier.py，新） | 加权词独高分 → level=="plot"、target=加权库、证据含「仅加权词」 |
| `test_smart_weighted_margin_discipline`（test_classifier.py，新） | 候选间加权分差 0.9 → 回退 rule/low；分差恰 1.0 → 择优（阈值两侧边界钉） |
| `test_smart_weighted_default_not_selected`（test_planner.py，新） | 两路径（plot 胜出/低置信回退）build_plan 后 default_selected 均 False（红线结构性钉） |
| `test_smart_unchanged_full_path`（test_classifier.py，新） | smart+普通关键词择优 → plot_pick 用全局 best（旧行为快照：多候选含非候选库高分时 smart 仍选全局 top——现状快照钉，防顺手「修」；主模型裁量维持不另立卡） |
| `test_evidence_priority_text_fixed`（test_classifier.py，新） | 胜者未列入表 → 证据无「优先级第」字样、含「未列入优先级表」；列入 → 「优先级第 2 位」位次正确 |
| `test_config_tab_strategy_items`（test_config_tab.py，新，离屏） | combo items == ["smart","smart_weighted","priority","genre_only"] |

## 四、验收命令（以下命令均在项目根目录执行；测试解释器用 G:/python/python.exe）

1. 写 8 测试（红）：`G:/python/python.exe -m pytest tests/test_config.py tests/test_classifier.py tests/test_planner.py tests/test_config_tab.py -q` → 新 8 fail。
2. 最小实现按落点清单（config.py + classifier.py 六处）。
3. 跑绿定向 → all passed；补 GUI combo + tooltip + example/README 文案。
4. ruff 改动文件 0 项；`G:/python/python.exe -m mypy app` → ≤149；全量 `G:/python/python.exe -m pytest -q` → **400 passed**（实测前基线 392=Task-04 收口数 +8）。
5. 离屏复验（GUI）：`QT_QPA_PLATFORM=offscreen G:/python/python.exe -m pytest tests/test_config_tab.py -q` → all passed。
6. 重放核对（双跑，只读）：`G:/python/python.exe tools/replay_metrics.py config.toml --strategy smart_weighted --json` 与 `--strategy smart --json`。**实测口径（主注）**：smart 基线=181（计划分析口径 ≈157 已漂移，以实测为锚）；硬断言=`smart_weighted ≤ smart`（诚实化生效方向）；若 smart_weighted 落入 **182–199** 即失败模式立即停卡回报。两口径数字都记入 verify:。
7. commit：`feat(classify): E 新策略值 smart_weighted+置信度诚实化（旧 smart 不变）`；正文 `verify:` 全量 392→400 + 双口径默认勾选数 + 「GUI 已验证（离屏）」+ `Refs: D-20261125-05`。中文提交信息写 UTF-8 文件后 `git commit -F <文件>`。

## 五、提交与约束

- 显式列文件 add；永不 `git add -A`、永不 `--no-verify`；只 commit 不 push。
- 同工作树 ≤1 卡（本卡独占执行）；禁触 `app/__init__.py`、`installer/installer.iss`（他人未提交改动，勿动勿收）。
- 默认值不改（实机 strategy 保持 smart，风险 #1：owner 复测轮自行切换）；不新建配置键（仅扩枚举值）；不 bump 版本。
- GUI 按离屏协议，不引入新依赖；实机黑盒留统一复测轮。
- learned 数据安全：本卡不动票目。
- 执行纪律：卡面外发现的问题只记录回报，不擅自扩范围。

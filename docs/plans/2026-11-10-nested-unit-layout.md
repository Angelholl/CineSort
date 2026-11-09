# 实现计划：嵌套影片目录识别 + 「库\女优\影片」三层布局

**目标：** 源根顶层纯容器目录下钻为"女优\影片"独立单元，目标路径组合为 `库\<女优>\<影片>`，女优层撞名合并、影片层沿用 provider id 三分冲突。
**架构：** 数据流不变（scanner → classifier → planner → jobs → UI）。scanner 加"下钻判定序"并把女优段挂到 `Unit.actress`；planner 新增唯一组合点 `unit_dst_dir`（`session_dst_root` 不动）；jobs 消费同一组合点 + 女优目录自动创建；UI 只加详情面板"目标路径"一行。composite/ST_BATCH 机制原样保留为混合目录兜底。
**规格：** `docs/design/2026-11-10-nested-unit-layout.md`（本文全部任务从它论证；§编号引用均指该文件）。

## 全局约束（违反即 FAIL）

1. owner 拍板三条照抄规格 §2：保留女优层不压平；女优目录撞名=合并不判冲突；老 Task-11/12/13 押后（处置见 §6）。
2. **契约变更需带回归测试且测试基线只增不减**：基线 259 passed；本计划新增 28（Task-01/02/03/06/07）+ 5（Task-04/05，owner 放行后）；**唯一授权修订 1 处**（Task-01 的 `test_complex_dir_becomes_batch_unit`，批准依据 = 规格 §4 复议 + owner 拍板 2），除此之外现有测试 0 删 0 改，不得为变绿放宽断言。收口终值：**287**（不放行 Task-04/05）或 **292**（放行）。
3. 组合单点：`planner.session_dst_root`（planner.py:66-71）零改动；新增 `planner.unit_dst_dir` 是"根+女优段+影片段"的唯一拼接处，jobs/viewmodel 只许消费。收口 grep：`rg -n "/ u\[\"dst_name\"\]|/ u\.dst_name|target_path\) / " app/` 必须 0 命中。
4. 零改动红线：classifier 全文件、nfo.py（不解析 actor）、fsops.py、preflight.py 判定逻辑（Task-04 仅扩状态过滤）、`EXCLUDED_DIRS`/`RE_MULTI_CD`/`RE_SUPPLEMENT`/`_analyze_dir` 内部逻辑、stats 公式、`STATUS_LABELS`（无新状态）、默认勾选规则、56 条 alias 配置。
5. 每卡验证链：`python -m ruff check <本卡改动文件含 tests>`（0 项，D-20261102-02）→ 定向 pytest → 全量 pytest；GUI 卡加 offscreen 截图。
6. 真实盘只读：禁止移动/改名/删除 `E:\已刮削` 下任何文件；禁止写 `D:\CineSort\config.toml`、`D:\CineSort-beta\CineSort\config.toml`、`config.example.toml`。执行者 git commit 不 push（Conventional 前缀+中文描述，正文 `verify:` 写实测结果与 `Refs: D-20261110-01`），不得 `git add -A`、不得 `--no-verify`；推送归 owner。
7. 本文 `文件:行号` 为基线 `11a9a4a` 的行号，施工行号漂移以符号定位为准。

---

## 0. 现状核实（已逐一读取确认）

| 关注点 | 位置 | 现状 |
|---|---|---|
| 顶层目录单元契约 | `app/core/scanner.py:243-272`（dir 分支 :255-256 直调 `_analyze_dir`） | 只把源根顶层当单元，无下钻 |
| Unit 字段 | `app/core/scanner.py:57-76`（composite :66） | 无 actress |
| 识别遍历/排除 | `scanner.py:79-84` / :27-33 / :49-54 | pruned 遍历 + 排除名单 |
| 多 CD/base 分组 | `scanner.py:35-36`（RE_MULTI_CD）、:156-187（bases 分组） | 复合分支 :163-185 产整目录 composite 单元 |
| 花絮过滤 | `scanner.py:39-43`（RE_SUPPLEMENT）、:150-154（mains 过滤+回退） | 已生效 |
| 快照 | `scanner.py:87-108`（_walk_files_full/snapshot_dir） | 整目录零遗漏 |
| NFO 定位 | `scanner.py:111-131`（find_nfo） | 复用，无需改 |
| 散装文件 | `scanner.py:214-240`（_analyze_loose） | 包一层迁移，无 actress |
| dst 组合 | `app/core/planner.py:81` | `Path(dec.target_path) / u.dst_name`（要改） |
| 输出根单点 | `planner.py:66-71`（session_dst_root） | 保持不动 |
| 冲突三分 | `planner.py:87-107`（_existing_dir :40-49 / marker :52-56 / provider :59-63） | 逻辑复用，落点自然变三层 |
| ST_BATCH | `planner.py:109-113`、:23-37、`mark_undone` :287-297 | C9 产物，保留 |
| 统计 | `planner.py:168-193`（fb/(total−composite) :188）、`_refresh_stats` :256-270 | 公式不动 |
| 多版本 | `planner.py:152-166` | READY-only，零改动 |
| freshness READY 过滤 | `planner.py:233-234` | 仅 READY（Task-04 扩） |
| jobs dst 改写 ×2 | `app/core/jobs.py:167`（改判）、:178-181（会话输出，注释已写"复用 planner 组合规则"） | 改经 unit_dst_dir |
| jobs 状态门 | `jobs.py:147-149` | 非 READY 全拒（Task-05 扩） |
| TOCTOU 终检 | `jobs.py:216-223`；transfer 分支 :228-241 | 保留；前插 parent mkdir |
| undo 跳过条件 | `jobs.py:290-299` | 语义不变 |
| 迁移原语 | `app/core/fsops.py:80-121`（dst 拒绝 :87）、:124-161（loose mkdir :134） | 零改动 |
| 长路径 | `app/core/preflight.py:17`（240）、:119-129 | 零改动，自动覆盖三层 |
| viewmodel 分母 | `app/ui/viewmodel.py:155` | `fb/total`，与 planner 口径分裂（修正） |
| viewmodel 预览 | `app/ui/viewmodel.py:222-229`（effective_output_root） | 加 effective_dst_dir |
| 详情面板 | `app/ui/plan_tab.py:222-241`（字段 grid）、:526-550（_show_detail） | 加"目标路径"行 |
| demo 数据 | `app/ui/demo_data.py:63-84`（dst_dir :70，无 actress/dst_name） | 补字段（其 docstring 要求同构） |
| 决策记录 | `docs/decision-log.md:23-30`（D-04，复合目录 :28）、:32-34（D-05）、:135-146（D-20261109-01，更正 :146） | 复议依据 |
| 测试夹具 | `tests/conftest.py:19-32`（make_movie，mkdir parents=True）、:35-72（build_env） | 复用 |
| 待修订测试 | `tests/test_scanner.py:56-69`（test_complex_dir_becomes_batch_unit） | 唯一修订点 |
| C9 复合测试兼容 | `tests/test_planner.py:134-140`（_make_composite：两个 base 视频直接躺目录） | R1 路径 → composite 不变，C9 测试全数存活 |

**测试基线**：`def test_` 静态计数 **259**（test_classifier 29、test_config_tab 27、test_config 28、test_nfo 27、test_viewmodel 29、test_scanner 21、test_planner 14、test_plan_tab 16、test_flow 12、test_doctor_tab 11、test_exec_tab 11、test_learned 9、test_fsops 8、test_paths 6、test_journal 5、test_entry 3、test_state 3）。全仓 ruff 基线 **10 项**（只降不增）。

---

## 1. 设计决策（实施者必须照此执行，不得自行变更）

- **DA1（判定序）**：规格 §3.1 的 R1/R2/R3 逐字实现，谓词为模块级纯函数；`is_movie_dir` **不要求 NFO**（无 NFO 内层目录仍下钻、走既有兜底/人工语义，避免一个缺 NFO 目录拖死整容器）；附件残留只 warn 不阻断下钻。
- **DA2（女优段）**：只取容器目录名逐字保留（含 `#未知女优`/`未知演员`）；NFO actor 不解析（nfo.py 零改动）；无女优段单元 actress=None → 扁平 dst（规格 §7-1 默认口径，owner 若改统一三层，只改 DA3 一行 + 修订既有 flow/planner 断言，另行授权）。
- **DA3（组合单点）**：`unit_dst_dir(target_root, actress, dst_name)` 放 planner.session_dst_root 之后；actress=None → `root/dst_name`（既有扁平语义回归钉）；`session_dst_root` 签名与逻辑零改动。
- **DA4（合并零分支）**：不在 planner 新增"检测女优目录存在"分支——三层 dst 使合并成为结构事实；冲突检测/多版本/ST_BATCH/stats 公式逐字不动。唯一口径修正 = viewmodel.stats 分母对齐 `total − composite`。
- **DA5（执行链）**：jobs 三处——import 加 `unit_dst_dir`；:167 与 :178-181 两处 dst 改写经它；transfer 分支对 kind=dir 在 TOCTOU 终检之后补 `dst.parent.mkdir(parents=True, exist_ok=True)`（loose 由 fsops.py:134 覆盖）。空女优目录残留 = 已知无害（规格 §3.4-5）。
- **DA6（UI 最小面）**：详情面板加"目标路径"一行绑 `vm.effective_dst_dir`；无新状态/徽章/chips/筛选；demo 补 actress/dst_name 维持"与 planner 产物同构"纪律。
- **DA7（修订授权）**：`tests/test_scanner.py:56-69` 更名重写为下钻语义（`test_nested_container_drills_two_units`），批准依据 = 规格 §4（D-20261031-05 复议）+ owner 拍板 2；C9 全部测试经验证存活（`_make_composite` 构造的视频直接躺目录走 R1 → composite 语义不变）。

## 2. 签名与形状变更总表（验收逐条比对）

| 符号 | 现状 | 变更 | 兼容性 |
|---|---|---|---|
| `Unit`（scanner.py:57-76） | 无 actress | + `actress: str \| None = None`（`composite` 字段之后） | 默认值，全兼容 |
| `_analyze_dir`（scanner.py:134） | `(d, rel_id)` | → `(d, rel_id, actress: str \| None = None)`；两处 Unit 构造（:173-182、:201-210）传 `actress=actress` | 默认值，全兼容 |
| scan_source_root dir 分支（:255-256） | 直调 `_analyze_dir` | 前插 R1/R2/R3 判定序；新增模块级 `_own_main_videos` / `_has_disc_structure` / `_is_movie_dir` / `_dir_has_video` / `_child_dirs` | 行为追加 |
| `planner.unit_dst_dir` | — | 新增 `(target_root: str \| Path, actress: str \| None, dst_name: str) -> Path` | 新增 |
| `build_plan`（planner.py:81、dict :115-150） | 直接拼接 | :81 改经 `unit_dst_dir`；dict + `"actress": getattr(u, "actress", None)` | schema 追加键 |
| `run_apply`（jobs.py:14-23 import；:167；:178-181；:228-241） | 两处拼接 | import + 两处改经 `unit_dst_dir` + dir 单元 parent mkdir | 行为追加 |
| `PlanViewModel`（viewmodel.py:143-156、:222-229） | ratio 用 total | stats 分母 `max(total − composite, 1)`；+ `effective_dst_dir(unit) -> str`；import 加 `unit_dst_dir` | 修正+追加 |
| `PlanTab._detail_panel` / `_show_detail`（plan_tab.py:223-225、:526-550） | 6 字段 | 字段元组 + `("dst", "目标路径")`；详情绑定 effective_dst_dir | 渲染追加 |
| `fake_units`（demo_data.py:63-84） | 无 actress/dst_name | + 两键；actress 行的 src/dst_dir 带女优段 | 数据追加 |
| `check_plan_freshness`（planner.py:233-234）/ preflight 过滤（preflight.py:83-84、:121-124）/ jobs 状态门（jobs.py:147-149） | 仅 READY | （仅 Task-04/05，owner 放行后）扩 `(READY, ST_BATCH+override)` | Task-04/05 专用 |

---

## 3. 任务板（顺序 = 派卡顺序；同文件卡严格串行）

> 每任务收尾必须跑该任务验证命令且全绿。新增测试 28 个（9+8+7+2+2），修订 1 处。

### Task-01 scanner：顶层容器下钻识别（R1/R2/R3）

- **文件**：`app/core/scanner.py`（Modify：57-76 加字段 / 134 加参 / 173-182 与 201-210 传参 / 243-272 判定序 / 新增谓词区 ：43-54 后）、`tests/test_scanner.py`（Test：**修订** ：56-69 + 末尾追加 9 个）
- **接口**：Consumes 既有 `_walk_files_pruned`/`RE_MULTI_CD`/`RE_SUPPLEMENT`/`_analyze_dir`；Produces `Unit.actress`、flags `"nested"`、下钻 info/warn notes、`_is_movie_dir`（Task-02/03 消费其产物）
- **依赖**：无

**步骤：**

- [ ] 1. （红）`tests/test_scanner.py` 末尾追加下表 9 个测试；运行 `python -m pytest tests/test_scanner.py -q` 确认新增全红、现有 21 全绿。
- [ ] 2. `Unit` 在 `composite`（:66）后加 `actress: str | None = None`；`_analyze_dir` 签名加 `actress: str | None = None`，两处 `Unit(...)` 构造各加 `actress=actress`。
- [ ] 3. 谓词区（`_is_excluded_dir` 之后）新增五个模块级函数，签名固定：

  ```python
  def _own_main_videos(d: Path) -> list[Path]:
      """T 直接子文件中的正片视频：¬RE_SAMPLE ∧ ¬RE_SUPPLEMENT（深度 1，不回退）。"""
  def _has_disc_structure(d: Path) -> bool:
      """(d/'BDMV' or d/'VIDEO_TS').is_dir() 或 own_main_videos 含 .iso。"""
  def _child_dirs(d: Path) -> list[Path]:
      """直接子目录，剔除 _is_excluded_dir 与点目录，按名排序。"""
  def _dir_has_video(d: Path) -> bool:
      """_walk_files_pruned 下存在 ≥1 个 ¬RE_SAMPLE 视频。"""
  def _is_movie_dir(d: Path) -> bool:
      """规格 §3.1 谓词：无视频 False → mains 过滤 → disc True → |bases|==1 True。"""
  ```

- [ ] 4. `scan_source_root` 的 dir 分支（:255-256）改为判定序：R1 `own or disc → _analyze_dir(entry, rel_id)`；R2 `movies and len(movies)==len(withvid)` → 逐个 `_analyze_dir(c, c.relative_to(root).as_posix(), actress=entry.name)`，`unit.flags.append("nested")` 后自行 append，notes 追加 info（文案含 `"容器目录"`、`"女优"`、子目录数），attachments（无视频子目录 + 非视频直接子文件，≤5 例）追加 warn（文案含 `"残留"`），分支尾置 `unit, note = None, None` 防循环尾重复追加；R3 其余 → `_analyze_dir(entry, rel_id)`，且 `withvid and not movies`（混合）时追加 info note（文案含 `"混合"`）。R1/R3 单元不挂 nested、actress 保持 None。
- [ ] 5. （绿）实现至全绿；`test_complex_dir_becomes_batch_unit`（:56-69）**更名重写**为 `test_nested_container_drills_two_units`（见下表第 1 行）。
- [ ] 6. 验证：`python -m ruff check app/core/scanner.py tests/test_scanner.py` 0 项；`python -m pytest tests/test_scanner.py -q` → **30 passed**；`python -m pytest tests -q` → **0 failed，268 passed**。
- [ ] 7. 真实数据只读自检（必须贴原样输出）：
  `py -3.12 -c "import sys,collections;sys.path.insert(0,'.');from app.core.config import load_config;from app.core.scanner import scan_source_root;cfg=load_config(r'D:/CineSort-beta/CineSort/config.toml');us,ns=scan_source_root(cfg);print('units=',len(us),'composite=',sum(1 for u in us if getattr(u,'composite',False)));print('nested=',sum(1 for u in us if 'nested' in u.flags),'actress=',sum(1 for u in us if getattr(u,'actress',None)));print('notes=',dict(collections.Counter(n.get('level') for n in ns)))"`
  → 期望方向：`units= 230~250`、`composite ≤3`（原 43）、`nested == actress ≥140`、notes 无 excluded。数字显著越界即停，回报不得臆测原因。

**测试表（tests/test_scanner.py，除第 1 行均为新增）：**

| 测试名 | 构造 | 断言 |
|---|---|---|
| `test_nested_container_drills_two_units`（**修订**，原 :56-69 更名重写） | `src/Pack` + `make_movie(Pack,"Film A")` + `make_movie(Pack,"Film B")` | `len(units)==2`；`{u.id}=={"Pack/Film A","Pack/Film B"}`；两单元 `actress=="Pack"`、`"nested" in flags`、`composite is False`；notes 无 `excluded`、有 `level=="info"` 且 reason 含 `"容器目录"`（批准依据 DA7） |
| `test_actress_container_drills_into_movie_units` | `src/伊藤舞雪` + `make_movie(src/"伊藤舞雪","CAWD-876",title="CAWD-876",tmdb="1")` | 恰 1 单元；`id=="伊藤舞雪/CAWD-876"`；`actress=="伊藤舞雪"`；`dst_name=="CAWD-876"`；`path == src/"伊藤舞雪"/"CAWD-876"`；nfo 解析成功；info note 含 `"伊藤舞雪"` |
| `test_drill_two_containers_actress_segments` | `一乃あおい/A-1` 与 `伊藤舞雪/B-2` 两个容器 | 2 单元；`{u.actress}=={"一乃あおい","伊藤舞雪"}` 且逐单元容器名正确；无 composite |
| `test_top_level_movie_dir_not_drilled` | `make_movie(src,"Flat Film")`（视频直接在顶层） | 1 单元 `id=="Flat Film"`、`actress is None`、`"nested" not in flags` |
| `test_disc_container_not_drilled` | `src/Bluay Set/{BDMV/STREAM/00000.m2ts, movie.nfo}` | 1 单元 `id=="Bluay Set"`、`disc is True`、`actress is None`（钉死"BDMV 子目录不得当内层影片目录"陷阱） |
| `test_mixed_container_falls_back_to_composite` | `src/混杂包/{好片A/(movie), 坏片/(两部不同 base 视频)}` | 恰 1 个 `composite is True` 单元 `id=="混杂包"`、`actress is None`；notes 有 reason 含 `"混合"` 的 info |
| `test_inner_dir_without_nfo_still_drills` | `src/一乃あおい/ABC-1/`（仅 1 视频，无 NFO） | 1 单元、`actress=="一乃あおい"`、`nfo_path is None`、`flags==["nested"]` |
| `test_inner_dir_multi_base_blocks_drill_to_composite` | `src/一乃あおい/{ABC-1/(1 视频), XYZ-9/(2 视频 2 base)}` | 恰 1 个 composite 单元 `id=="一乃あおい"`、`actress is None` |
| `test_videoless_child_dir_warn_and_left_behind` | `src/一乃あおい/{ABC-1/(movie), covers/x.jpg, poster.jpg}` | 1 个下钻单元；warn note 同时含 `"covers"` 与 `"poster.jpg"` 且含 `"残留"`；单元 files 不含 covers/poster（快照仅影片目录） |
| `test_unknown_actress_placeholder_kept_verbatim` | `src/#未知女优/GOV-004/(movie)` | `actress == "#未知女优"`（逐字，含 `#`） |

---

### Task-02 planner：`unit_dst_dir` 单点 + 三层冲突语义

- **文件**：`app/core/planner.py`（Modify：:66-71 后新增函数 / :81 组合 / :115-150 dict 加 actress 键）、`tests/test_planner.py`（Test：末尾追加 8 个）
- **接口**：Consumes `Unit.actress`（Task-01）；Produces `unit_dst_dir`（jobs/viewmodel 消费）、plan_units `"actress"` 键、三层冲突语义回归钉
- **依赖**：Task-01

**步骤：**

- [ ] 1. （红）追加下表 8 个测试，跑 `python -m pytest tests/test_planner.py -q` 确认 8 红余绿。
- [ ] 2. `session_dst_root`（:66-71）之后新增：

  ```python
  def unit_dst_dir(target_root: str | Path, actress: str | None, dst_name: str) -> Path:
      """「根 + 女优段 + 影片段」唯一组合点：build_plan / jobs 改写 / UI 预览共用。
      actress 为 None（无女优段单元）→ 根/dst_name，保持既有扁平语义（规格 §3.3）。"""
      root = Path(target_root)
      return root / actress / dst_name if actress else root / dst_name
  ```

- [ ] 3. planner.py:81 改 `dst_dir = unit_dst_dir(dec.target_path, getattr(u, "actress", None), u.dst_name)`；plan_units dict（:115-150）在 `"dst_name"` 键后加 `"actress": getattr(u, "actress", None),`。冲突块（:87-107）、ST_BATCH（:109-113）、多版本（:152-166）、stats（:168-193）**逐字不动**。
- [ ] 4. （绿）验证：`python -m ruff check app/core/planner.py tests/test_planner.py` 0 项；`python -m pytest tests/test_planner.py -q` → **22 passed**；`python -m pytest tests -q` → **276 passed**（C9 的 6 个复合测试与 `_make_composite` 全数存活即 DA7 兼容性证明）。

**测试表（tests/test_planner.py；三层单元统一用 `make_movie(cfg.source_root / "一乃あおい", "ABC-1", genres=("科幻",), tmdb=…)` 构造，科幻库根记 `scifi = cfg.libraries["科幻"].path`）：**

| 测试名 | 构造 | 断言 |
|---|---|---|
| `test_unit_dst_dir_combination_rule` | 直接调用 | `unit_dst_dir(r"E:\lib", "女优", "MOVIE") == Path(r"E:\lib\女优\MOVIE")`；`unit_dst_dir(r"E:\lib", None, "MOVIE") == Path(r"E:\lib\MOVIE")`（扁平）；`unit_dst_dir(session_dst_root("E:/out", "科幻", True), "女优", "M") == Path("E:/out/科幻/女优/M")` |
| `test_plan_drilled_unit_dst_three_layers` | 源 `一乃あおい/ABC-1`（科幻, tmdb=1） | 单元 `actress=="一乃あおい"`；`dst_dir==str(scifi/"一乃あおい"/"ABC-1")`；`status=="ready"`、`level=="rule"`、`default_selected is True` |
| `test_plan_actress_dir_exists_merges_not_conflict` | 预置 `scifi/一乃あおい/EXIST-1`（tmdb=9）；源同 actress 另片 `ABC-2` tmdb=1 | `status=="ready"`（**非 conflict_name**，owner 拍板 2 之钉）；`dst_dir==str(scifi/"一乃あおい"/"ABC-2")` |
| `test_plan_same_movie_three_layers_already_placed` | 预置 `scifi/一乃あおい/ABC-1` tmdb=1；源同 id | `status=="already_placed"`；notes 含 `"冗余副本"` |
| `test_plan_same_name_movie_three_layers_conflict` | 预置 `scifi/一乃あおい/ABC-1` tmdb=2；源 tmdb=1 | `status=="conflict_name"`（同名异片在影片层，既有语义） |
| `test_plan_movie_dir_name_equals_actress_name` | 预置 `scifi/一乃あおい/EXIST`（tmdb=9）；源 `src/一乃あおい/一乃あおい/`（影片目录名==女优名，tmdb=1） | `status=="ready"`；`dst_dir==str(scifi/"一乃あおい"/"一乃あおい")`（三层组合不与女优层撞名混淆） |
| `test_plan_actressless_unit_flat_dst_regression` | `make_movie(cfg.source_root,"Flat Film",genres=("科幻",),tmdb="5")`（顶层直接视频） | `actress is None`；`dst_dir==str(scifi/"Flat Film")`（扁平回归钉） |
| `test_plan_incomplete_marker_at_movie_level` | 预置 `scifi/一乃あおい/ABC-1/` 且内置 `.incomplete-20261110` 文件；源同路径影片 | `status=="incomplete_leftover"`（半成品检查点随 dst 升到影片层） |

---

### Task-03 jobs：执行链消费单点 + 女优目录自动创建

- **文件**：`app/core/jobs.py`（Modify：:14-23 import / :167 / :178-181 / :228-241 transfer 分支）、`tests/test_flow.py`（Test：末尾追加 7 个）
- **接口**：Consumes `unit_dst_dir`（Task-02）与 plan_units `"actress"` 键；Produces 三层落盘/回滚/会话输出/体检 warn 行为
- **依赖**：Task-02

**步骤：**

- [ ] 1. （红）追加下表 7 个测试（文件内新增辅助 `_make_actress_env(tmp_path)`：`build_env` + `load_config` + `make_movie(cfg.source_root / "一乃あおい", "ABC-1", title="ABC-1", genres=("科幻",), plot="太空宇宙", tmdb="31")` + 返回 `(AppState(cfg_path), cfg)`），跑 `python -m pytest tests/test_flow.py -q` 确认 7 红余绿。
- [ ] 2. jobs.py:14-23 的 planner import 加 `unit_dst_dir`；:167 改 `u["dst_dir"] = str(unit_dst_dir(u["target_root"], u.get("actress"), u["dst_name"]))`；:178-181 会话分支保留 `root = session_dst_root(...)`，:180 改 `u["dst_dir"] = str(unit_dst_dir(root, u.get("actress"), u["dst_name"]))`。
- [ ] 3. transfer 分支（:228-241）：`if u["kind"] == "dir":` 内、`transfer_dir` 调用之前插 `dst.parent.mkdir(parents=True, exist_ok=True)`（置于 TOCTOU 终检 :216-223 之后；loose 分支不加，fsops.py:134 已覆盖）。
- [ ] 4. （绿）验证：`python -m ruff check app/core/jobs.py tests/test_flow.py` 0 项；`python -m pytest tests/test_flow.py -q` → **19 passed**（既有 12 个含会话输出/漂移用例零修订）；`python -m pytest tests -q` → **283 passed**。

**测试表（tests/test_flow.py）：**

| 测试名 | 步骤 | 断言 |
|---|---|---|
| `test_apply_drilled_unit_three_layer_layout` | `_make_actress_env` → scan → `start_apply(["一乃あおい/ABC-1"], {"jellyfin_running"}, {})` → wait | done 且 `moved==1`；`(scifi/"一乃あおい"/"ABC-1").is_dir()`；源影片目录不存在；源女优目录 `src/"一乃あおい"` 仍存在（空壳=规格接受的残留）；plan stats `by_status["applied"]==1` |
| `test_apply_drilled_unit_creates_actress_dir` | 同构造但在源再加 `make_movie(cfg.source_root / "新人子", "XYZ-1", …)`（库内无此女优目录），apply 该单元 | 执行后 `(scifi/"新人子"/"XYZ-1").is_dir()`（parent mkdir 生效） |
| `test_apply_session_output_grouped_three_layers` | scan → `start_apply(ids, {"jellyfin_running"}, {}, output_root=str(out), group_by_category=True)` | `(out/"科幻"/"一乃あおい"/"ABC-1").is_dir()`（session_dst_root × unit_dst_dir 链） |
| `test_apply_session_output_flat_keeps_actress_layer` | 同上 `group_by_category=False` | `(out/"一乃あおい"/"ABC-1").is_dir()` 且 `(out/"科幻").exists() is False` |
| `test_undo_drilled_unit_preserves_library_siblings` | 预置 `scifi/"一乃あおい"/"KEEP-1"`（make_movie）→ scan/apply/undo | apply 后 KEEP-1 仍在；undo `restored==1` 且 `(src/"一乃あおい"/"ABC-1").is_dir()`；KEEP-1 仍在（只回滚本次部分） |
| `test_preflight_long_path_warns_on_three_layer_dst` | `make_movie(cfg.source_root / ("あ"*80), "長"*120, genres=("科幻",), tmdb="41")` → scan → `preflight.run_preflight(cfg, plan)` | items 含 `code=="long_paths"` 且 level=="warn"，detail 引用该单元 id（规格 §3.6-3：维持 warn 不升级） |
| `test_jobs_dst_combination_uses_planner_single_point` | 读 `Path(jobs_mod.__file__).read_text(encoding="utf-8")` | `"unit_dst_dir(" 出现 ≥2`（改判+会话两分支）、`"session_dst_root(" ≥1`、`'/ u["dst_name"]' not in src`（组合单点架构钉） |

---

### Task-04【押后·须 owner 放行后才可派】freshness + preflight 放行 ST_BATCH（承接老 Task-11 上半）

- **文件**：`app/core/planner.py`（Modify：:233-234）、`app/core/preflight.py`（Modify：:83-84、:121-124）、`tests/test_planner.py`（Test：+1）、`tests/test_flow.py`（Test：+1）
- **接口**：Consumes `ST_BATCH`（已合入 C9）；Produces 混合复合单元的漂移校验与体检覆盖
- **依赖**：Task-02、Task-03（同文件串行；owner 未放行则整卡跳过，不影响 Task-06/07）

**步骤：**

- [ ] 1. planner.py:233-234 改 `if pu["status"] not in (READY, ST_BATCH): continue`（import 处补 ST_BATCH）。
- [ ] 2. preflight.py 磁盘（:83-84）与长路径（:121-124）过滤改 `u["status"] in (READY, ST_BATCH)`；兜底阈值（:131-144）不动。
- [ ] 3. 测试 2 个：`test_freshness_covers_batch_units`（test_planner：`_make_composite` → 入计划后改源 → `check_plan_freshness` 对该 id 报 `"源内容自扫描后已变化"`）；`test_preflight_covers_batch_units`（test_flow：复合单元 dst_dir 置 >240 字符场景 → `run_preflight` 的 long_paths detail 引用复合 id）。
- [ ] 4. 验证：`python -m ruff check app/core/planner.py app/core/preflight.py tests/test_planner.py tests/test_flow.py` 0 项；`pytest tests/test_planner.py -q` → **23**；`pytest tests/test_flow.py -q` → **20**；全量 → **285 passed**（按本板顺序此处时点）。

### Task-05【押后·须 owner 放行后才可派】jobs 执行门放行 ST_BATCH+override（承接老 Task-11 下半）

- **文件**：`app/core/jobs.py`（Modify：:147-149）、`tests/test_flow.py`（Test：+3）
- **接口**：Consumes Task-04 的放行集；Produces 混合复合单元"改判后整目录可执行/可回滚"
- **依赖**：Task-04（同文件与语义串行）

**步骤：**

- [ ] 1. jobs.py:147-149 改 `bad = [u["id"] for u in units if u["status"] != READY and not (u["status"] == ST_BATCH and overrides.get(u["id"]))]`（import 补 ST_BATCH；override 循环与 learned 零改动——复合单元 genres=[] learned 空转）。
- [ ] 2. 测试 3 个（`_make_composite` 造含 2 base 的顶层目录，走 R1 → composite）：`test_apply_composite_requires_override`（无 override → failed，error 含 `"不在可执行状态"`，源未动）；`test_apply_composite_whole_dir_moves`（override="科幻" → 整目录落 `scifi/<原目录名>`、目录名不变、learned.json 无 entries）；`test_apply_composite_undo_restores`（undo → 整目录回源位、`mark_undone` 后 status 回 `batch_target`）。
- [ ] 3. 验证：`python -m ruff check app/core/jobs.py tests/test_flow.py` 0 项；`pytest tests/test_flow.py -q` → **23**；全量 → **288 passed**（时点值；收口终值见 Task-08）。

### Task-06 viewmodel：目标路径预览 + 兜底率分母对齐

- **文件**：`app/ui/viewmodel.py`（Modify：:14 import / :143-156 stats / :222-229 后新增 effective_dst_dir）、`tests/test_viewmodel.py`（Test：末尾追加 2 个）
- **接口**：Consumes `unit_dst_dir`（Task-02）；Produces `PlanViewModel.effective_dst_dir`（Task-07 消费）
- **依赖**：Task-02（viewmodel 保持零 Qt，架构守卫 `test_viewmodel_importable_without_qt` 继续钉）

**步骤：**

- [ ] 1. （红）追加 2 个测试（下表），跑 `python -m pytest tests/test_viewmodel.py -q` 确认 2 红。
- [ ] 2. :14 import 加 `unit_dst_dir`；stats（:155）改 `out["fallback_ratio"] = out["fallback"] / max(out["total"] - out.get("composite", 0), 1)`（DA4 唯一口径修正；`out[u["level"]]` 聚合已天然产出 composite 键）。
- [ ] 3. `effective_output_root`（:229）之后新增：

  ```python
  def effective_dst_dir(self, unit: dict) -> str:
      """该单元最终目标目录（含会话输出）。组合唯一真值 = planner.unit_dst_dir；
      dst_name 缺失时回退 dst_dir 尾段（兼容旧 demo 数据）。"""
      root = self.effective_output_root(unit) or unit["target_root"]
      name = unit.get("dst_name") or Path(unit["dst_dir"]).name
      return str(unit_dst_dir(root, unit.get("actress"), name))
  ```

  （文件头 import 补 `from pathlib import Path`。）
- [ ] 4. （绿）验证：`python -m ruff check app/ui/viewmodel.py tests/test_viewmodel.py` 0 项；`pytest tests/test_viewmodel.py -q` → **31 passed**（既有 `test_stats_full_scope_ignores_filter` 6 单元无 composite → 1/6 不变，零修订）；全量 → **285**（若 Task-04/05 未放行）/ **290**（放行）。

**测试表（tests/test_viewmodel.py；单元用 `{**make_unit(...), "actress": …, "dst_name": …}` 扩展）：**

| 测试名 | 断言 |
|---|---|
| `test_effective_dst_dir_three_layers_and_flat` | actress 单元 → `rf"D:\媒体库\科幻\一乃あおい\ABC-1"`；`set_output_root(r"E:\out")` 后 → `r"E:\out\科幻\一乃あおい\ABC-1"`；actress=None 单元两种模式均扁平 `…\科幻\Flat`；`vm.unit_dst_dir is planner.unit_dst_dir`（与既有 `test_session_dst_root_rule_shared_with_jobs` 同款单点钉） |
| `test_stats_fallback_ratio_excludes_composite` | `[composite 级 ST_BATCH 单元, fallback 级单元]` → `stats["total"]==2`、`stats["composite"]==1`、`stats["fallback_ratio"] == 1.0`（分母 1 非 2，对齐 planner 口径） |

### Task-07 计划页 UI：详情"目标路径"行 + demo 同构字段

- **文件**：`app/ui/plan_tab.py`（Modify：:223-225 字段元组 / :526-550 _show_detail）、`app/ui/demo_data.py`（Modify：:63-84）、`tests/test_plan_tab.py`（Test：末尾追加 2 个）
- **接口**：Consumes `PlanViewModel.effective_dst_dir`（Task-06）；Produces GUI 目标路径展示与同构演示数据
- **依赖**：Task-06（同区串行：plan_tab 上次被触碰是 C9 前，无冲突）

**步骤：**

- [ ] 1. （红）追加 2 个测试（下表），跑 `python -m pytest tests/test_plan_tab.py -q` 确认 2 红。
- [ ] 2. plan_tab.py:223-225 的字段元组末尾（`("status", "状态")` 后）加 `("dst", "目标路径")`（落入既有 else 分支 → 自动获得 Expanding+wordwrap 样式）；`_show_detail`（:526-550）在 `self.d_fields["lib"]` 赋值后加 `self.d_fields["dst"].setText(self.vm.effective_dst_dir(u))`。
- [ ] 3. demo_data.py `fake_units`：`actress = rnd.choice(["篠田ゆあ", "伊藤舞雪", "#未知女优", None, None])`；unit dict 加 `"dst_name": name, "actress": actress`；`src` 与 `dst_dir`（:69-70）在 actress 非空时改为 `…\{actress}\{name}` 形状（保持与 planner 产物同构）。
- [ ] 4. （绿）验证：`python -m ruff check app/ui/plan_tab.py app/ui/demo_data.py tests/test_plan_tab.py` 0 项；`pytest tests/test_plan_tab.py -q` → **18 passed**；全量 → **287 passed**（收口基线）。
- [ ] 5. GUI 截图（offscreen）：`QT_QPA_PLATFORM=offscreen py -3.12 -m app.ui.main_window --demo --screenshot artifacts/2026-11-10-nested-plan-tab.png --tab 0` → 文件生成；目验：详情面板出现"目标路径"行且演示数据含女优段路径。完成通知注明「GUI 已验证（offscreen 截图）/黑盒未做」。

**测试表（tests/test_plan_tab.py）：**

| 测试名 | 断言 |
|---|---|
| `test_detail_shows_dst_path` | `tab.table.selectRow(0)` → `tab.d_fields["dst"].text() == tab.vm.effective_dst_dir(tab._current_unit)` 且非空 |
| `test_demo_units_carry_actress_fields` | `fake_units(40, seed=7)` 每行含 `"actress"`（None 或非空串）与 `"dst_name"`；存在 actress 非空行且其 `actress in dst_dir`、`actress in src` |

### Task-08 收口：全量回归 + 组合单点 grep + 真实数据探针 + GUI

- **文件**：无新改动；只验证（Task-04/05 若被放行则先行完成）
- **依赖**：Task-01/02/03/06/07（及放行时的 04/05）

**步骤：**

- [ ] 1. `python -m pytest tests -q` → 0 failed；用例总数 = **287**（未放行 Task-04/05）或 **292**（放行）。修订清单核对：仅 `test_complex_dir_becomes_batch_unit` 更名重写 1 处，其余 0 删 0 改。
- [ ] 2. `python -m ruff check . 2>&1 | grep "^Found"` → **≤ 10 errors**（基线只降不增）。
- [ ] 3. 组合单点 grep：`rg -n "/ u\[\"dst_name\"\]|/ u\.dst_name|target_path\) / " app/` → **0 命中**；`rg -n "unit_dst_dir" app/` → ≥5 命中（planner 定义+build_plan+jobs×2+viewmodel）。
- [ ] 4. 真实数据只读探针（贴原样输出）：
  `py -3.12 -c "import sys,collections;sys.path.insert(0,'.');from app.core.config import load_config;from app.core.scanner import scan_source_root;from app.core.planner import build_plan;cfg=load_config(r'D:/CineSort-beta/CineSort/config.toml');us,ns=scan_source_root(cfg);p=build_plan(cfg,us,ns);st=p['stats'];u=p['units'];print('units=',len(u),'composite=',st['composite']);print('status=',dict(collections.Counter(x['status'] for x in u)));print('fallback_ratio=',st['fallback_ratio']);print('actress_units=',sum(1 for x in u if x.get('actress')))"`
  → 期望方向（对照基线 `units=140 composite=43 status={'conflict_name':22,'ready':85,'batch_target':33}`）：`composite ≤3`；`conflict_name ≤12`（消失的 12 个=女优层撞名转 ready）；`ready ≥150`；`fallback_ratio` 分母=total−composite；`actress_units ≥140`。
- [ ] 5. GUI 截图两张：`--tab 0`（Task-07 产物复核）与 `--tab 2`（配置页不回归）。
- [ ] 6. 本文件末尾「实施记录」回填：基线=259、收尾=<实测数>、修订清单（1 处）、规格 §6 V1-V7 逐项勾选结果。**不 push**（改动已逐卡 commit，推送归 owner）。

---

## 4. 边界输入五类（最易咬人输入，逐条有测试）

| 边界 | 行为 | 归属测试 |
|---|---|---|
| 内层目录无 NFO | 仍下钻为单元 → 无题材 → 兜底库、默认不勾、人工确认 | Task-01 `test_inner_dir_without_nfo_still_drills`（+ 既有 fallback 语义测试回归） |
| 内层目录多视频多 base | is_movie_dir=False → 容器混合 → 整目录 composite ST_BATCH | Task-01 `test_inner_dir_multi_base_blocks_drill_to_composite` |
| 影片目录名与库内女优名相同 | 三层组合天然区分：`库\女优\<同名影片>`，不误判冲突 | Task-02 `test_plan_movie_dir_name_equals_actress_name` |
| `#未知女优` 占位名 | 逐字保留（含 `#`），与库内同名占位目录合并 | Task-01 `test_unknown_actress_placeholder_kept_verbatim` + Task-02 `test_plan_actress_dir_exists_merges_not_conflict` |
| 三层路径超 240 字符 | preflight `long_paths` warn（不升级 block） | Task-03 `test_preflight_long_path_warns_on_three_layer_dst` |

次级边界（有钉，不计入五类）：BDMV 子目录陷阱（Task-01 disc 测试）；容器附件残留（Task-01 warn 测试）；顶层散装/散落花絮（既有测试零修订存活）；BDMV 光盘容器（Task-01）；`.incomplete` 在影片层（Task-02）。

## 5. 对已合入卡 C8/C9 产物的处置

| 产物 | 处置 | 依据 |
|---|---|---|
| C8：scanner composite 整目录单元分支（scanner.py:163-185） | **保留**，命中面从 43 收缩为 R1/R3 真混合目录（预期 ≤3） | 规格 §4；ST_BATCH 仍是混合目录唯一安全出路 |
| C9：planner ST_BATCH/统计分母/`mark_undone` 修复（planner.py:109-113、:188、:267-270、:287-297） | **保留，零改动** | 规格 §3.6-1 |
| C9：viewmodel `_executable` 门禁（viewmodel.py:190-194） | **保留**（本计划不改该函数） | 混合单元仍需改判解锁 |
| C9 测试 7 个（test_planner.py:134-219 + test_viewmodel.py:372-384） | **全部存活零修订**（`_make_composite` 视频直接躺目录 → R1 → composite 语义不变，Task-02 步骤 4 全量绿即证明） | DA7 |
| C8 测试 4 个（test_scanner.py:254-310） | **全部存活**（构造均为"视频直接躺目录"= R1 路径） | 同上 |
| `test_complex_dir_becomes_batch_unit`（test_scanner.py:56-69） | **唯一修订**：更名 `test_nested_container_drills_two_units` 并改断言为下钻语义 | 规格 §4（D-20261031-05 复议）+ owner 拍板 2，DA7 |
| C8 轮 Task-02 的 javdb provider id 修复 | **保留**，成为 §3.4 影片层 same-id 判定的数据基础 | 规格 §3.4-2 |

## 6. 老计划（2026-11-09-classification-quality）剩余卡合并排序处置

| 老卡 | 处置 | 排序 |
|---|---|---|
| 老 Task-11（执行链放行 ST_BATCH） | **仍需做，未被取代**（真混合目录仍需"改判→执行→回滚"通道；没有它 C9 产物只能看不能动）。拆为本计划 Task-04/05 两卡（遵守"每卡 ≤2 实现文件"），**owner 放行后才派**；行号已按新基线重核（freshness :233-234、preflight :83-84/:121-124、jobs :147-149） | 排 Task-03 之后、Task-06 之前（同文件串行：planner→T04 在 T02 后、jobs→T05 在 T03 后） |
| 老 Task-12（计划页 chips/批量改判对话框/demo 复合行） | **仍需做但价值面缩小**（43→个位数），未被取代；落点与本计划 Task-07 同文件区域（plan_tab.py:102-111 chips、底部条），且依赖 Task-05 才有意义 | **不在本计划编号内**：排在 Task-07 之后另开卡，前置 = 本计划 Task-05 + Task-07；派卡前行号重核 |
| 老 Task-13（收口） | **被本计划 Task-08 取代**（同性质：全量回归+GUI 冒烟+基线核对；老卡截图断言中"整目录/标题 chips"以老 Task-12 实际实施为准） | — |

## 7. 计划自查（五查结论）

1. **规格覆盖**：§3.1→Task-01；§3.3→Task-02/03/06；§3.4→Task-02（+既有 jobs/undo 零改动由 Task-03 集成测试钉）；§3.5→Task-03；§3.6→Task-02 步骤 4 回归 + Task-06 stats + Task-03 长路径；§3.7→Task-06/07；§6 V1→Task-08 探针、V2→Task-02/03/06+grep、V3→Task-02、V4→Task-03、V5→Task-03/06、V6→Task-08、V7→Task-07/08。规格 §7 两处含糊点按默认口径落地（DA2/DA3），owner 改判时的改动面已在 DA2/DA3 标注。
2. **步骤唯一可写**：每步一个动作+可核对结果；签名/谓词/文案关键词/测试断言均钉死；函数体仅 `unit_dst_dir`/`effective_dst_dir` 两个 2 行函数给出全文（测试无法替其定形）。无 TBD/“处理边界情况”死行。
3. **类型一致**：`unit_dst_dir` 在 Task-02 定义、Task-03/06 消费同名同签名；`actress` 键在 Task-02 产出、Task-03/06/07 以 `u.get("actress")` 消费（demo 旧数据兼容）；`effective_dst_dir` Task-06 定义、Task-07 消费；无命名漂移。
4. **边界输入**：§4 五类各一条测试 + 次级边界 6 条，均有代码点与测试名。
5. **比例**：计划约 300 行 / 预估改动约 220 行代码 + 33 测试；未超比例；同文件卡严格串行（scanner T01；planner T02→T04；jobs T03→T05；viewmodel T06；plan_tab/demo T07）。

## 8. 验证命令汇总

```bash
# 基线（开工前）
python -m pytest --collect-only -q          # 预期 259
# 定向（每卡收尾，ruff 先行且必须 0 项）
python -m ruff check <本卡改动文件含 tests>
python -m pytest tests/test_scanner.py -q    # Task-01 → 30
python -m pytest tests/test_planner.py -q    # Task-02 → 22（Task-04 后 23）
python -m pytest tests/test_flow.py -q       # Task-03 → 19（Task-04 后 20、Task-05 后 23）
python -m pytest tests/test_viewmodel.py -q  # Task-06 → 31
python -m pytest tests/test_plan_tab.py -q   # Task-07 → 18
# 全量
python -m pytest tests -q                    # 268→276→283（→285→288）→285/290→287/292
# 组合单点（Task-08）
rg -n "/ u\[\"dst_name\"\]|/ u\.dst_name|target_path\) / " app/     # 期望 0 命中
rg -n "unit_dst_dir" app/                                            # 期望 ≥5 命中
# 全仓 lint（Task-08）
python -m ruff check . 2>&1 | grep "^Found"                          # ≤10
# GUI 截图（Task-07/08）
QT_QPA_PLATFORM=offscreen py -3.12 -m app.ui.main_window --demo --screenshot artifacts/2026-11-10-nested-plan-tab.png --tab 0
QT_QPA_PLATFORM=offscreen py -3.12 -m app.ui.main_window --demo --screenshot artifacts/2026-11-10-nested-config-tab.png --tab 2
# 真实数据只读探针（Task-01 / Task-08，命令见任务板步骤 7 与 Task-08 步骤 4）
```

## 9. 实施记录（执行者填写）

- 基线=259（2026-11-10 主审实测：`pytest tests -q` → 259 passed；全仓 ruff 10 项）
- Task-04/05 是否获 owner 放行：**是**（owner 于 2026-11-10 开工会话一并放行）
- 收尾=**292**（收口新鲜复跑 `pytest tests -q` → 292 passed；全仓 ruff 10→**8**，Task-04
  顺手修复 preflight 2 项既有基线 lint——`check=False`、隐式串接加括号，行为零变化，只降不增）
- 测试修订清单：**仅 1 处**——`test_complex_dir_becomes_batch_unit` 更名重写为
  `test_nested_container_drills_two_units`（DA7 授权）；其余 0 删 0 改
- 真实数据探针原样输出（只读，D:/CineSort-beta/CineSort/config.toml）：
  - Task-01 后：`units= 244 composite= 0` / `nested= 244 actress= 244` / `notes= {'info': 140, 'warn': 2}`
  - Task-08 收口全链：`units= 244 composite= 0` /
    `status= {'ready': 205, 'multi_version': 39}` / `fallback_ratio= 0.03278688524590164` /
    `actress_units= 244`
- 计划预期偏差 3 处（均已在对应提交正文留痕）：
  1. Task-01 R3 混合 info note 条件按规格 §3.1 判定表实现为
     `len(movies) < len(withvid)`（计划步骤字面 `withvid and not movies` 与其自家测试表
     test_mixed_container_falls_back_to_composite 矛盾；测试表=验收真值）；
  2. Task-05「复合单元 genres=[] learned 空转」前提对 `_make_composite`（NFO 带 西部）不
     成立，红灯实证 learned 会被记账；按计划意图（learned.json 无 entries）落实为显式跳过
     composite 单元的 `learned_store.record`——占位分类不得为单影片 NFO 记票；
  3. Task-03 计划预期 7 红实测 5 红：长路径与 undo 兄弟保护两测由 Task-02 三层 dst_dir
     自然提前覆盖（undo 场景女优目录因 KEEP-1 预置已存在，os.rename 仅需直接父目录），
     断言照常钉住行为。
- 规格 §6 验收勾选：
  - [x] V1 识别：composite 43→0（≤3）；conflict_name 22→0（≤12）；units 140→244（≥220）；
        nested=actress=244
  - [x] V2 组合：grep `"/ u[\"dst_name\"]"|/ u\.dst_name|target_path\) / ` app/ → 0 命中；
        `unit_dst_dir` 8 命中（planner×2 + jobs×3 + viewmodel×3，≥5）；会话输出两种模式有测试钉
  - [x] V3 合并：女优目录已存在→ready（非 conflict）；同 provider id→ST_PLACED；
        异 id 同名→ST_CONFLICT；`.incomplete` 在影片层→ST_INCOMPLETE（4 测试钉）
  - [x] V4 执行/撤销：女优目录缺失自动创建；TOCTOU 终检保留；undo 后库内兄弟原样、
        影片目录回源位
  - [x] V5 统计与体检：公式不变；viewmodel 分母对齐 total−composite；
        >240 字符三层 dst → long_paths warn
  - [x] V6 测试基线：259→**292**（+28 Task-01/02/03/06/07，+5 Task-04/05 放行；修订 1 处授权）
  - [x] V7 GUI：offscreen 截图 `artifacts/2026-11-10-nested-tab0.png`（5000 行规模、详情含
        「目标路径」行）、`artifacts/2026-11-10-nested-plan-detail.png`（选中行目验：
        目标路径=库\女优\影片 三层）、`artifacts/2026-11-10-nested-tab2.png`（配置页不回归）；
        提交信息注明「GUI 已验证（offscreen 截图）/黑盒未做」
- 收口备注（给 owner 的新信号）：实测 **multi_version=39**——下钻后同 provider id
  多副本/多版本按既有语义默认不勾选、待人工确认，是 C8 轮 javdb provider id 修复后首次
  在真实数据上显形（规格 §3.4-3/§5），非回归。
- 未 push（改动逐卡 commit，共 7 个实现提交 + 本文档 1 个 docs 提交，推送归 owner）

# 规格：嵌套影片目录识别与「题材库\女优\影片」三层布局（2026-11-10）

- 状态：待 owner 批准（批准后按 `docs/plans/2026-11-10-nested-unit-layout.md` 派卡）
- 决策依据：owner 2026-11-10 三项拍板（见 §2 全局约束，不得推翻）
- 事实来源：`docs/design/research-20261110-library-layout-nesting.md`（递归探针实测，非推断）
- 关联决策：复议 `docs/decision-log.md` D-20261031-04（第 28 行"复合目录整目录排除/归集"）、
  D-20261031-05（"一个影片单元 = 源根顶层目录"）；延续 D-20261109-01 及其 2026-11-10 更正
- 前置产物基线：卡 C8（`1373792`）+ C9（`11a9a4a`）已合入；全量测试 259 passed；全仓 ruff 10 项

## 1. 问题陈述

单元契约是"一个顶层目录 = 一部影片"（`app/core/scanner.py:243-272` 只把源根顶层当单元），
而这批数据的真实组织是三层：`待整理\<女优名>\<番号>\{1 视频 + 1 NFO + 海报/字幕}`，
且源根与题材库根**同构**（库内已经是 `题材\女优\影片`）。后果：

1. 43 个顶层容器被判复合目录 → 43 次人工改判（`stats.composite=43`，实测 2026-11-10）；
2. 顶层女优目录里只有一部影片时，scanner 把**女优目录**当成影片单元，`dst_name=女优名`，
   目标 `库\<女优名>` 撞上库内既有女优目录 → 22 个 `conflict_name`，其中 12 个是本可自动归位的
   普通影片（`on_conflict=skip` 把它们卡死）；
3. 145 个内层目录自带 NFO 与题材标签，56 条 genre_aliases 可直接命中——当前契约却吃不到。

## 2. 全局约束（owner 拍板，违反即 FAIL）

1. **保留女优层**：目标路径组合为 `库\<女优>\<影片>`（与现有库内布局一致），不压平。
2. **撞名语义改为合并**：目标位置存在同名女优目录时，合并进去（把影片目录放进该女优目录），
   不再判 `conflict_name`、不再 skip。
3. 本轮只交付本规格与配套计划；老计划剩余卡（Task-11/12/13）押后，与新增任务的合并排序见计划 §6。
4. 派生约束：`session_dst_root`（`app/core/planner.py:66-71`，76344b0 收敛的输出根单点）保持不变；
   女优段组合不得开辟第二处拼接逻辑（见 §3.3）。
5. 派生约束：分类判定链（classifier）、56 条 genre_aliases、genre_priority、自学习层零改动。

## 3. 行为定义

### 3.1 单元识别与下钻判定（scanner）

复用既有原语，语义零修改：`EXCLUDED_DIRS`（scanner.py:27-33）、`_is_excluded_dir`（:49-54）、
`RE_MULTI_CD`（:35-36）、`RE_SAMPLE`（:37）、`RE_SUPPLEMENT`（:39-43）、`_walk_files_pruned`
（:79-84）、`snapshot_dir`（:95-101）、`find_nfo`（:111-131）、`_analyze_dir`（:134-211，含
composite 分支 :163-185）、`_analyze_loose`（:214-240）。新增以下纯判定函数与一个下钻分支。

**谓词定义（伪代码级，实现签名见计划 Task-01）**

```
own_main_videos(T) = T 的直接子文件中，扩展名 ∈ VIDEO_EXTS ∧ ¬RE_SAMPLE ∧ ¬RE_SUPPLEMENT
                     （不做 mains→vids 回退；回退只发生在 _analyze_dir 内部，既有行为不变）
disc_at(T)         = (T/"BDMV" 或 T/"VIDEO_TS") 是目录 ∨ own_main_videos(T) 中含 .iso
children(T)        = T 的直接子目录，剔除 _is_excluded_dir 与点目录，按名排序
video_children(T)  = { C ∈ children(T) : C 内经 _walk_files_pruned 存在 ≥1 视频 ∧ ¬RE_SAMPLE }
movie_children(T)  = { C ∈ children(T) : is_movie_dir(C) }
attachments(T)     = { C ∈ children(T) : C 不含任何视频 }  ∪  T 的直接子文件中的非视频文件

is_movie_dir(C)：
  videos = _walk_files_pruned(C) 中 视频 ∧ ¬RE_SAMPLE；为空 → False
  mains = videos 中 ¬RE_SUPPLEMENT；mains 非空则 videos = mains
  disc(C)（C/BDMV、C/VIDEO_TS 子目录或 .iso ∈ videos）→ True
  bases = { RE_MULTI_CD(C 的 stem).base 或 stem.casefold() }；|bases| == 1 → True；否则 False
  **不要求 NFO**（无 NFO 的单片目录仍是影片目录，归位时走既有兜底/人工确认语义）
```

**顶层目录判定序（对源根每个顶层条目，替换 `scanner.py:255-256` 的直调）**

```
R1  own_main_videos(T) 非空 ∨ disc_at(T)
      → 不下钻：_analyze_dir(T) 既有语义（单 base → 普通单元；多 base → composite 单元）。
        依据：容器根层直接躺正片视频或光盘结构时，T 本身就是影片目录，绝不拆。
R2  movie_children(T) 非空 ∧ |movie_children| == |video_children|
      → 下钻：每个 C 经 _analyze_dir(C, rel_id="T/C"(posix), actress=T.name) 生成独立单元，
        flags 追加 "nested"；扫描 notes 追加一条 info：
        「容器目录：内含 N 个影片目录，已按 女优\影片 拆为独立单元（女优段=T.name）」。
        attachments(T) 不迁移、留在源处，逐项（目录名/文件名 ≤5 例）追加 warn note。
R3  其余（|movie_children| < |video_children| 即混合；或全目录无视频）
      → 不下钻：_analyze_dir(T) 既有语义（混合多 base → composite 单元 = ST_BATCH 待改判）；
        混合情形追加 info note：
        「容器目录混合：M 个子目录为多 base/非单片内容，整目录回退为复合单元（待人工改判）」。
```

逐条解释（规格不许含糊，逐条给判定结果）：

| 输入形态 | 判定 |
|---|---|
| 内层目录含 NFO 且恰 1 视频 | is_movie_dir=True → 参与下钻 |
| 内层目录含 NFO 且多视频共享同一 base（多 CD/disc） | is_movie_dir=True → 参与下钻（多 CD 仍合并为一个单元） |
| 内层目录**无 NFO**、恰 1 视频 | is_movie_dir=True → 仍下钻；单元 nfo=None → 分类走既有"无题材→兜底库"、默认不勾、人工确认 |
| 内层目录多视频**多 base** | is_movie_dir=False → 若容器内还有其他单片目录 → R3 混合 → 整目录 composite；若容器内只有它 → R1/R3 → composite（与今日行为一致） |
| 内层目录只有花絮/预告视频（RE_SUPPLEMENT 命中，非排除名） | video_children 计入（有非 sample 视频）但 is_movie_dir=False → R3 混合回退。**保守取舍**：宁整目录改判，不猜归属 |
| 容器内有单片目录 + 附件（海报 jpg、纯图片子目录、杂散文件） | attachments 不阻断下钻、不随迁、warn 留源处（R2） |
| 容器根直接躺正片视频（含只有花絮视频回退 mains→vids 的目录） | R1 不下钻（`test_supplement_only_dir_still_unit` 既有钉不死：该形态 movie_children=0，走 _analyze_dir 回退为普通单元） |
| BDMV/VIDEO_TS/ISO 光盘结构（任意层） | R1 disc_at / is_movie_dir 的 disc 分支 → 整结构一个单元，绝不把 BDMV 当内层影片目录下钻 |
| 顶层散装视频文件、顶层排除目录、散落花絮文件 | 既有语义零改动（_analyze_loose / :249-252） |

**不下钻的完整条件清单**：R1（容器自身是影片目录）∨ R3（混合或无视频）。回退到整目录
composite 单元的条件：R1/R3 路径上 `_analyze_dir` 判出多 base。C8/C9 的 composite/ST_BATCH
机制**原样保留**，只是命中面从 43 收缩到"真正混合目录"（按实测预期 ≤3 个）。

### 3.2 女优段来源与占位名

1. 女优段**只取源路径结构**：下钻单元的 actress = 容器目录名（T.name），逐字保留——含
   `#未知女优`、`未知演员` 等占位名，不做归一、不改名、不去 `#`。
   依据：源根与库根同构，容器名就是 owner 自己组织时用的女优目录名；逐字保留可与库内既有
   女优目录（含 `E:\已刮削\按摩\#未知女优` 这类）直接对齐合并。
2. NFO 的 actor/performer 字段**本轮不解析**（`NfoInfo` 无 actor 字段，nfo.py 零改动）。
   "两者冲突谁赢"因此不存在比较逻辑：路径结构是唯一来源。多女优作品同理——目录名是
   owner 的物理归类事实，优先于 NFO 演员列表。
3. 无女优段单元（R1 顶层单片目录、顶层散装文件）actress=None。目标组合见 §3.3——本规格
   默认保持扁平 `库\<影片>`（不变更既有语义）。是否统一强制 `库\#未知女优\<影片>` 属于
   owner 待确认项（§7-1）；真实数据源根全三层，两种策略在当前数据上等价。
4. 占位名归一（如 `未知演员` → `#未知女优`）不做（§7-2）；同名占位目录靠合并语义自然归拢。

### 3.3 目标路径组合（唯一组合点）

1. planner 新增唯一组合函数（计划 Task-02 定签名 `unit_dst_dir`）：

   ```
   unit_dst_dir(target_root, actress, dst_name) =
       Path(target_root) / actress / dst_name   当 actress 非空
       Path(target_root) / dst_name             当 actress 为 None（既有扁平语义，回归钉）
   ```

2. `build_plan` 的 `dst_dir = Path(dec.target_path) / u.dst_name`（planner.py:81）改经
   `unit_dst_dir(dec.target_path, u.actress, u.dst_name)`；plan_units dict 新增 `"actress"` 键。
3. 会话输出根链不变：`session_dst_root(output_root, target_lib, group_by_category)` 产出根，
   再经 `unit_dst_dir(根, actress, dst_name)` 落三层。即：
   - 输出根 + 按类别：`输出根\<目标库>\<女优>\<影片>`
   - 输出根 + 平铺：`输出根\<女优>\<影片>`
   - 无输出根：`库根\<女优>\<影片>`
   `jobs.run_apply` 的两处改写（jobs.py:167 人工改判分支、:178-181 会话输出分支）与
   viewmodel 预览一律消费 `unit_dst_dir`，全仓不得再出现 `target… / dst_name` 形式的直接拼接
   （收口 grep 验证，见计划 Task-07）。
4. 冲突检测、多版本分组、staging 根推导（`fsops.staging_for_root(target_root)`）全部只看根，
   不受三层影响，零改动。

### 3.4 冲突与合并语义（planner）

合并**不新增任何分支**——三层组合天然实现（这就是选它而不是"检测到同名女优目录再合并"的原因）：

1. 目标女优目录存在与否都不产生状态：dst 是 `库\女优\影片`，女优目录只是中间路径。
   `fsops.transfer_dir` 的"目标已存在拒绝移动"防线（fsops.py:87）现在语义精确地落在
   **影片目录层**，绝不出现"把影片搬进另一个影片目录内部"。
2. 目标**影片**目录已存在（`_existing_dir` 大小写不敏感，planner.py:40-49）：
   - 半成品标记（`.incomplete-*`，:52-56）→ `ST_INCOMPLETE` 阻断（现检查点在三层 dst 上）；
   - provider id 相同（含 C8 轮修复后的 javdb 裸 id）→ `ST_PLACED`，判源冗余，不移动；
   - provider id 不同 → 既有 `on_conflict` 语义：`skip` → `ST_CONFLICT`；`rename`（有 provider id
     才可用）→ `影片名 (2)` 顺延，仍在**同一女优目录内**。
3. 同 provider id 多版本分组（planner.py:154-166）逻辑不变，天然作用于三层单元。
4. 原子性与中断：迁移原语零改动。同卷 `os.rename` 原子；跨卷走库外 staging + `.incomplete`
   标记 + 逐文件校验 + 同卷 rename（fsops.py:92-121）。中断残留由 preflight
   `staging_leftover` 阻断、④ 页清理，语义不变。
5. 撤销（undo）：按 journal 整目录回滚（jobs.py:265-325），移动粒度是**影片目录**，因此
   只回滚本次放入的部分，绝不动库内女优目录里的原有兄弟影片。已知无害残留（规格明确接受）：
   - 撤销后库内女优目录若为空则留在原地（不判断"是否本次创建"，避免误删既有目录）；
   - 源侧女优目录搬空后留空壳（源侧清理是非目标）。
   undo 的两条跳过条件（目标不存在/源已存在，jobs.py:290-299）在三层下语义不变。

### 3.5 执行链（jobs）

1. `run_apply` 逐单元：TOCTOU 终检（jobs.py:216-223）之后、`transfer_dir` 之前，对 kind=dir
   单元补 `dst.parent.mkdir(parents=True, exist_ok=True)`（女优目录不存在时自动创建）；
   kind=file 单元由 `transfer_loose` 的 `dst_dir.mkdir(parents=True)`（fsops.py:134）覆盖，零改动。
   失败残留语义：TOCTOU 失败或迁移失败时可能留下空女优目录——无害，接受（同 §3.4-5）。
2. `bad = [u for u in units if u["status"] != READY]` 门（jobs.py:147-149）本轮**不动**
   （composite 放行是老 Task-11 的事，见计划 §6）。
3. 人工改判与会话输出的 dst 改写改经 `unit_dst_dir`（§3.3-3），`journal` 记录的
   src_dir/dst_dir 自动是三层路径，undo 无需感知 actress。
4. 自学习沉淀（jobs.py:254-260）零改动： drilled 单元 genres 来自自身 NFO，照常记账。

### 3.6 统计口径、兜底与长路径

1. `stats` 公式**逐字不变**：`composite` 按字段计数；`fallback_ratio = fb / (total − composite)`
   （planner.py:188、:267-270）。变化的是数字本身（见 §6 预期）。
2. 修正既有口径分裂：`PlanViewModel.stats()` 的 `fallback_ratio` 现用 `total` 做分母
   （viewmodel.py:155），与 planner 的 `total − composite` 不一致（C9 轮遗留）。对齐为
   `fb / max(total − composite, 1)`；card_tones 阈值行为不变。
3. preflight：`LONG_PATH_WARN=240`（preflight.py:17）与长路径 warn（:119-129）、磁盘空间、
   staging 残留、兜底阈值（:131-144）逻辑零改动——它们都消费 `dst_dir`/`stats`，自动覆盖三层。
   三层 + 长日文标题会推高 `len(dst_dir)`：**维持 warn（可越过）不升级为 block**，理由：250+ 字符
   在开启 Win32 长路径的 Win10/11 上可成功迁移，且失败会走 aborted + staging 残留保护，不会静默。
4. 单元总量预期大幅上升（43 容器 → ~145 个单元）：计划页渲染与 5000 行规模冒烟既有协议覆盖
   （D-20261102-02），无需新机制。

### 3.7 UI 呈现（最小面）

1. 计划页详情面板新增"目标路径"行：显示 `viewmodel.effective_dst_dir(unit)`——无会话输出时
   `unit_dst_dir(target_root, actress, dst_name)`，设会话输出时按 §3.3-3 组合。用途：执行前
   人工核对合并落点（女优段、占位名一目了然）。
2. 表格列、chips、徽章、状态文案、默认勾选规则**零改动**（无新状态、无新 level）。
3. demo 数据按"与 planner 产物同构"纪律补 `actress`/`dst_name` 字段（demo_data.py 自身的
   docstring 要求），部分演示行带女优段以驱动新展示。

## 4. 决策复议（供 owner 归档 docs/decision-log.md，本文不得自行归档）

- **复议 D-20261031-05（部分）**："一个影片单元 = 源根下含视频文件的顶层目录"修订为：
  "影片单元 = 含恰好一部影片（单 base/单 disc）的最内层完整目录；顶层目录若为纯容器
  （根层无正片视频、全部视频内容位于单片子目录）则下钻，每个子目录一个单元，女优段取容器名"。
- **复议 D-20261031-04（部分）**："复合目录整目录排除并报告"（C8 轮已改为整目录单元）进一步
  收缩为："仅当容器混合（存在多 base 子目录或根层正片视频与子目录影片并存）时整目录
  composite（ST_BATCH 待改判）；纯容器一律下钻"。同名撞名从"目录名冲突"修正为"仅影片目录
  层冲突；女优层目录撞名 = 合并"。
- 新决策草拟编号 **D-20261110-01**（owner 批准本规格后归档）：内容 = §2 三条拍板 + §4 两条
  复议 + §3.1 判定序 + §3.3 组合单点。
- C8/C9 产物处置：`composite` 字段、`ST_BATCH`、`_executable` 门禁、统计分母、`mark_undone`
  修复**全部保留**为混合目录兜底；43→个位数是命中面收缩，不是回归。唯一测试修订授权见计划 §5。

## 5. 非目标（记录在案，验收不得当作缺陷）

1. 不做在线刮削、不做 LLM、不做任何 NFO actor 字段解析。
2. 不重排/不增删 56 条 genre_aliases、不改 genre_priority、不改 classifier 判定链与置信语义。
3. 不改 240 字符长路径的 warn 语义，不引入长路径自动启用。
4. 不清理源侧空女优目录/附件残留（只 warn 报告）；不归一占位名；不改名任何目录。
5. 不提供"压平模式"或女优层开关配置——布局策略就是 §3.3，无第二形态。
6. 不做"已在位"的全库扫描比对（仍只检查目标路径点位，与既有语义一致）。
7. 不动老计划 Task-12（批量改判 UI）——见计划 §6 的排序处置。

## 6. 验收口径（每条可测）

- **V1 识别**：真实数据只读探针（owner 实机配置）`composite` 从 43 降至 ≤3；`conflict_name`
  从 22 降至 ≤12（仅剩影片层同名异片）；`units` 从 140 升至 ≥220；`nested` flag 单元数 =
  actress 非空单元数。
- **V2 组合**：actress 单元 `dst_dir == 库根\女优\影片`；actress=None 单元 `dst_dir == 库根\影片`；
  会话输出两种模式按 §3.3-3 组合；全仓无第二处拼接（grep 证据）。
- **V3 合并**：库内预置同名女优目录 → 单元 READY（非 conflict）；同 provider id → `ST_PLACED`；
  异 id 同名影片 → `ST_CONFLICT`（skip）/rename；`.incomplete` 标记在影片层 → `ST_INCOMPLETE`。
- **V4 执行/撤销**：女优目录缺失时自动创建；TOCTOU 终检保留；undo 后库内兄弟影片原样、
  影片目录回源位。
- **V5 统计与体检**：公式不变；viewmodel 分母对齐；>240 字符三层 dst 产 `long_paths` warn。
- **V6 测试基线**：259 → 287（本计划 +28，唯一修订 1 处见计划 §5；若 owner 放行押后的 Task-04/05 则 292）。
- **V7 GUI**：offscreen 截图（计划页含目标路径行、演示数据含女优段行）。

## 7. 待 owner 确认的两处含糊点

1. **无女优段单元的目标形态**：顶层单片目录/散装文件是保持扁平 `库\<影片>`（本规格默认，
   零测试修订），还是统一强制 `库\#未知女优\<影片>`（三层绝对一致，但需修订既有 flow/planner
   断言 6-8 处，并为"未来可能识别出女优"的片子预先占坑）。当前实测源根全三层，两者在
   真实数据上暂无差异；owner 若选统一三层，只是一行策略 + 测试修订，不改架构。
2. **占位女优名是否归一**：源里同时存在 `#未知女优` 与 `未知演员` 两种占位。本规格默认逐字
   保留（与库内同名目录合并，物理零风险）。若 owner 希望归一到 `#未知女优`（跨库占位合并
   成一处），需确认：目标名、库内既有 `未知演员` 目录是否人工合并、以及归一发生在识别层
   （actress 赋值时）还是不动代码只改源目录名。

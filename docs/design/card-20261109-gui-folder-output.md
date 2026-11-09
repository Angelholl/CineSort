# 卡：GUI 添加文件夹 + 本次输出目录 + 按类别子文件夹开关

## 根因/背景
- GUI（PySide6 四标签页）源/库目录全靠手填文本框，无目录浏览对话框（全仓库 QFileDialog 零命中）。
- 分类后存放位置固定为配置中的媒体库根/兜底库，无"本次输出目录"运行时覆盖。
- 库根下按"片名 (年份)"建影片文件夹是固有行为，无"按类别建子文件夹"开关。

## 权威实现依据（唯一真值）
实现计划：`docs/plans/2026-11-09-gui-folder-output.md`（Task-01~08 逐任务执行，签名/落点/测试断言以该计划为准）。

Owner 已拍板：
- D1：指定本次输出目录后所有影片（含自学习改判单元）都进输出目录；改判仅决定类别子文件夹名。
- D2：「按类别建子文件夹」默认开启。
- D4：输出目录权威校验放 jobs 后台线程，失败=任务失败 toast、零文件副作用。

## 改法（概要）
1. config_tab.py：源目录/兜底库/暂存目录三框 + 库表添加操作接 QFileDialog.getExistingDirectory。
2. plan_tab.py：新增「浏览选择本次输出目录」控件 + 「按类别建子文件夹」复选框（默认开）。
3. jobs.py：输出目录改判循环前移到预检之前；run_apply/run_preflight 按计划扩展签名（默认参数，现有调用零改动）；阻断门后补 mkdir(parents=True)；新增 check_session_root 互不嵌套校验（config.py 镜像语义）。
4. viewmodel/state（AppState.start_apply）按计划扩展透传。
5. 严格先红后绿：每任务先写失败测试再实现；现有测试基线只增不减（计划已点数：test_config 11 / test_viewmodel 21 / test_flow 6 / test_state 2 / test_config_tab 14 / test_plan_tab 9）。

## 验收命令（均在项目根目录执行）
- `python -m pytest tests/ -q` —— 全绿，且用例总数 > 原基线（原 69：11+21+6+2+14+14+... 以计划 Task-00 记录的基线数为准，只增不减）
- `python -m pytest tests/test_config_tab.py tests/test_plan_tab.py tests/test_viewmodel.py tests/test_jobs*.py -q` —— 定向全绿
- `python -m pyflakes app/` 或项目既有静态检查配置 —— 零告警
- GUI 冒烟：`python run.py --screenshot --tab config` 与 `--tab plan` 能出图（不强制目验，主审负责）

## 约束
- 只 commit 不 push；改动范围以计划 Task-01~08 所列文件为限，超范围即停。
- 不改 plan.json 结构语义（输出目录仅 run_apply 内存改判）；输出模式不重算计划冲突状态。
- 大于 4KB 的文件读取/改动查看用 pointer_tools（pointerize/read_pointer/read_diff_only），禁止整读全文。
- 卡外问题（计划签名与实际代码冲突、测试无法红等）即停待裁决，不得自行改方案。

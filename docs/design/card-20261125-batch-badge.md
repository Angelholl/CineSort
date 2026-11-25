# 卡 T12a：计划页 ST_BATCH 行徽章链补齐（老 Task-12 残留之一）

## 一、根因

`ST_BATCH` 状态值 `"batch_target"`（planner.py:29）不在 `app/ui/table_cells.py:19` 的
`STATUS_BADGES` 映射内，`app/ui/theme.py:35` `BADGE_COLORS` 亦无 `"batch"` 键 →
计划页「整目录待改判」行不显示状态徽章，与普通行无视觉区分。planner 的
`STATUS_LABELS` 已有「整目录待改判」文案（planner.py:39），仅 UI 徽章链缺环。

## 二、改动文件

- `app/ui/table_cells.py`（Modify：19-26 STATUS_BADGES）
- `app/ui/theme.py`（Modify：35-44 BADGE_COLORS）
- `tests/test_plan_tab.py`（Test：追加徽章映射回归测试）

## 三、改法

1. `table_cells.py` `STATUS_BADGES` 追加一行：`"batch_target": "batch",`
2. `theme.py` `BADGE_COLORS` 追加一行：`"batch": WARN,`（复用警示橙 WARN，
   不新增色值——承 classification-quality 规格 DU1「不新增色值」约束）
3. `tests/test_plan_tab.py` 末尾追加回归测试：
   - `STATUS_BADGES["batch_target"] == "batch"` 且该键在 `theme.BADGE_COLORS`
   - `fake_units` 生成的单元若含 `batch_target` 状态行，徽章文案取
     planner `STATUS_LABELS`（若 fake_units 不含该状态，直接构造一条
     最小 unit dict 断言映射即可，不强改 demo_data）

## 四、验收命令（以下命令均在项目根目录执行）

```bash
python -m ruff check app/ui/table_cells.py app/ui/theme.py tests/test_plan_tab.py
python -m pytest tests/test_plan_tab.py -q     # 基线只增不减
python -m pytest -q                            # 全量，当前基线 347 passed
```

## 约束

- 先红后绿：先写测试确认红（键缺失），改完转绿。
- 不改 planner/viewmodel/plan_tab；不新增颜色令牌。
- 卡面自足；执行中读取大于 4KB 的文件或查看改动，用
  `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的
  pointerize/read_pointer/read_diff_only，禁止整读文件全文。
- 执行者只 commit 不 push；卡外问题即停待裁决。

## 验收补记（2026-11-25 主审）

- 渲染链实测 `status_badge`（viewmodel.py:55-57）直出原始状态码作徽章键，
  `"batch"` 键实际不会被消费；`batch_target` 落 DIM 兜底灰。验收期主审修正
  7d5ba15：BADGE_COLORS 补 `"batch_target": WARN` 别名键并钉回归测试——
  超卡面第 3 条范围，经复核为必要修正（code-review Spec 轴亦确认为
  「有依据的卡外修正」）。
- 遗留记账：徽章键存在「状态码/徽章键」双命名空间，长期可统一单一键空间
  消灭此类漏登记（Standards 轴判断性提示，不阻塞本卡）。

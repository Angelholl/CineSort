# 卡 T12b：计划页批量改判（set_override_many + 右键批量改判 + demo 复合行）

老 Task-12 主残留（classification-quality Task-12 经 nested-unit-layout 计划
§6 缩值后另开卡；前置 Task-05/Task-07 已由 v0.6.1 白名单收敛与 0.6.0 嵌套
布局合入覆盖）。卡 T12a（徽章链）先行合入后本卡才可执行。

## 一、根因

ST_BATCH/ST_MULTI 单元的改判目前只能逐行走详情面板下拉框
（plan_tab.py:287 `d_override`，viewmodel.py:243 `set_override`）。
真混合目录（整目录待改判）有多部影片需指向同一库时逐行操作低效；
无批量改判入口，亦无演示行支撑样式走查。

## 二、改动文件

- `app/ui/viewmodel.py`（Modify：set_override :243 附近新增 set_override_many）
- `app/ui/plan_tab.py`（Modify：_show_row_menu :540-546 扩批量项 + 新批量改判对话框）
- `app/ui/demo_data.py`（Modify：fake_units 补 1 条 batch_target 复合行）
- `tests/test_viewmodel.py`、`tests/test_plan_tab.py`（Test：追加）

## 三、改法

1. viewmodel.PlanViewModel 新增（set_override 之后）：

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

2. plan_tab 行右键菜单扩为两项：「打开影片所在目录」「批量改判目标库…」。
   选后者弹 QInputDialog.getItem（候选库 = `override_libs` 全量候选，含
   「撤销改判（回到规则判定）」空选项），对**当前勾选集**调用
   `vm.set_override_many`，toast 汇报生效条数；落点逻辑放纯函数
   `_handle_row_menu_choice` 扩展分支保持可单测；演示模式（state is None）
   只改 vm 不触发执行，行为与现有一致。
3. demo_data.fake_units 状态轮转加入一条 `batch_target` 复合行
   （composite=True 语义字段按 fake_units 现有字段形状补齐），徽章文案走
   planner.STATUS_LABELS。
4. 测试（先红后绿）：
   - test_viewmodel：set_override_many 生效条数、含未知 id 跳过、lib=None 清除；
   - test_plan_tab：菜单落点纯函数分支（批量项被选 → 触发 set_override_many
     的桩调用计数）；fake_units 含 batch_target 行且徽章文案=「整目录待改判」。

## 四、验收命令（以下命令均在项目根目录执行）

```bash
python -m ruff check app/ui/viewmodel.py app/ui/plan_tab.py app/ui/demo_data.py tests/test_viewmodel.py tests/test_plan_tab.py
python -m pytest tests/test_viewmodel.py tests/test_plan_tab.py -q
python -m pytest -q                            # 全量，基线只增不减
python -m pytest --collect-only -q | tail -1   # 与全量数字一致
```

## 约束

- viewmodel 保持零 Qt（架构守卫测试继续钉）；plan_tab 只做渲染与转发。
- 不改 planner/preflight/jobs/scanner；不新增颜色令牌（徽章色已由 T12a 补）。
- 卡面自足；执行中读取大于 4KB 的文件或查看改动，用
  `python C:/Users/57850/.zcode/tools/pointer_tools.py` 的
  pointerize/read_pointer/read_diff_only，禁止整读文件全文。
- 执行者只 commit 不 push；卡外问题即停待裁决。

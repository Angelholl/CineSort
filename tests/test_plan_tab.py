"""计划页 widget 级驱动测试（D-20261102-02 协议第 4 条）。

QT_QPA_PLATFORM=offscreen + 纯 PySide6 QTest 能力，零新增测试依赖。
覆盖：渲染行数、勾选→视图模型、筛选→重建且选择存活、改判→单元格与
视图模型联动、演示模式按钮禁用、阻断确认对话框的门禁语义。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.ui.demo_data import fake_units
from app.ui.main_window import MainWindow
from app.ui.plan_tab import BlockConfirmDialog, PlanTab
from app.ui.table_cells import COL_CHECK, COL_LIB


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def tab(qapp):
    toasts: list[str] = []
    tab = PlanTab(None, fake_units(40, seed=7), toast=toasts.append)
    yield tab, toasts
    tab.deleteLater()


def test_renders_all_demo_rows(tab):
    tab, _ = tab
    assert tab.table.rowCount() == 40
    assert tab.summary.text().endswith("共 40 部")
    assert tab.btn_apply.text() == "执行选中（0 部）" or "执行选中" in tab.btn_apply.text()


def test_demo_mode_disables_job_buttons(tab):
    tab, _ = tab
    assert tab.btn_scan.isEnabled() is False
    assert tab.btn_apply.isEnabled() is False
    assert tab.btn_scan.toolTip()             # 必须解释为什么禁用


def test_check_toggles_viewmodel_and_summary(tab):
    tab, _ = tab
    tab._clear_selection()                    # 走真实按钮路径：vm 与表格同步清空
    assert tab.vm.checked == set()
    row = next(r for r in range(tab.table.rowCount())
               if tab.table.item(r, COL_CHECK).checkState() == Qt.Unchecked)
    uid = tab._rows[row]["id"]
    # 注意：对已勾选的格重复 setCheckState(Checked) 是同值赋值，Qt 不发 itemChanged
    tab.table.item(row, COL_CHECK).setCheckState(Qt.Checked)
    assert uid in tab.vm.checked
    assert "已选 1 部" in tab.summary.text()
    tab.table.item(row, COL_CHECK).setCheckState(Qt.Unchecked)
    assert uid not in tab.vm.checked


def test_clear_button_syncs_table_and_vm(tab):
    tab, _ = tab
    assert tab.vm.checked, "demo 默认应有人物勾选"
    tab._clear_selection()
    assert tab.vm.checked == set()
    states = {tab.table.item(r, COL_CHECK).checkState()
              for r in range(tab.table.rowCount())}
    assert states == {Qt.Unchecked}


def test_filter_rebuilds_and_keeps_selection(tab):
    tab, _ = tab
    tab._clear_selection()
    row = next(r for r in range(tab.table.rowCount())
               if tab.table.item(r, COL_CHECK).checkState() == Qt.Unchecked)
    uid = tab._rows[row]["id"]
    tab.table.item(row, COL_CHECK).setCheckState(Qt.Checked)
    assert uid in tab.vm.checked
    fallback_ids = {u["id"] for u in tab.vm.rows() if u["level"] == "fallback"}
    assert fallback_ids, "demo 数据应含兜底行"
    tab.set_filter("fallback")
    assert tab.table.rowCount() == len(fallback_ids)
    assert uid in tab.vm.checked              # 选择跨筛选存活
    tab.set_filter("all")
    assert tab.table.rowCount() == 40


def test_override_updates_vm_and_cell(tab):
    tab, _ = tab
    tab.table.selectRow(0)
    u = tab._current_unit
    assert u is not None
    target = next((lib for lib in tab._libs if lib != u["target_lib"]), None)
    assert target, "demo 数据应有其他可选库"
    tab.d_override.setCurrentText(target)
    assert tab.vm.overrides[u["id"]] == target
    assert tab._rows[0]["id"] == u["id"]      # 行仍在
    cell = tab.table.item(0, COL_LIB)
    assert cell.text().endswith(" *")


def test_clear_override_via_sentinel(tab):
    tab, _ = tab
    tab.table.selectRow(0)
    u = tab._current_unit
    tab.d_override.setCurrentText("（不改判）")
    assert u["id"] not in tab.vm.overrides


def test_block_dialog_gate_semantics(qapp):
    ackable = [{"level": "block", "code": "jellyfin_running",
                "message": "检测到 Jellyfin 正在运行", "detail": ["Jellyfin.exe"]}]
    dlg = BlockConfirmDialog(ackable)
    assert dlg._ok.isEnabled() is False       # 未逐项确认前不可继续
    dlg._boxes[0][1].setChecked(True)
    assert dlg._ok.isEnabled() is True

    fatal = ackable + [{"level": "block", "code": "paths_missing",
                        "message": "配置中的目录不存在", "detail": ["D:\\nope"]}]
    dlg2 = BlockConfirmDialog(fatal)
    assert dlg2._fatal is True
    assert dlg2._ok.isEnabled() is False      # 不可越过的阻断直接禁用执行


def test_main_window_demo_builds_and_closes(qapp):
    win = MainWindow(None, demo_units=fake_units(20, seed=3))
    assert win.plan_tab.table.rowCount() == 20
    assert win.pill.text() == "空闲"
    assert win.close() is True                # 无任务运行，关窗不应被拦截
    win.deleteLater()

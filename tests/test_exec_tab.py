"""「② 执行 / 回滚」页视图逻辑单测（offscreen，零磁盘、零线程）：克隆 test_plan_tab.py 范式（D-20261102-02 协议第 1/2/4 条）。

覆盖：演示模式降级、空闲初始态、运行进度、scan 零 total、apply/undo/失败
结束沿渲染、日志防闪烁、会话清单（done>0 过滤 / 类型映射 / 预览按钮）、
回滚预览对话框两击确认、主窗接线静态断言。
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from app.ui.exec_tab import ExecTab, UndoPreviewDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class StubState:
    """duck-typing：只实现 ExecTab 会调用的方法，不 import AppState 以免碰盘。"""

    def __init__(self, sessions=()):
        self._sessions = list(sessions)

    def sessions(self):
        return list(self._sessions)

    def cancel_job(self):
        return False


def snap(**over):
    base = {"id": "a1", "kind": "apply", "status": "running", "total": 5,
            "cur": 2, "label": "Space War (2021)", "log": ["x"],
            "error": None, "result": {}}
    base.update(over)
    return base


@pytest.fixture()
def tab(qapp):
    toasts: list[str] = []
    tab = ExecTab(StubState(), toast=toasts.append)
    yield tab, toasts
    tab.deleteLater()


def test_demo_mode_disables_controls(qapp):
    toasts: list[str] = []
    tab = ExecTab(None, toast=toasts.append)
    assert tab.btn_cancel.isEnabled() is False
    assert "演示模式" in tab.btn_cancel.toolTip()
    assert "演示模式" in tab.sessions_hint.text()
    assert tab.session_table.rowCount() == 0
    tab.deleteLater()


def test_idle_initial_state(tab):
    tab, _ = tab
    assert tab.bar.value() == 0
    assert tab.result_label.text() == ""
    assert tab.btn_cancel.isEnabled() is False
    assert tab.job_label.text() == "空闲"


def test_running_apply_updates_progress(tab):
    tab, _ = tab
    tab.on_job_tick(snap())
    assert tab.bar.value() == 2
    assert tab.bar.maximum() == 5
    assert "2/5" in tab.pos_label.text()
    assert "执行中" in tab.job_label.text()
    assert "Space War" in tab.job_label.text()
    assert tab.btn_cancel.isEnabled() is True


def test_running_scan_zero_total(tab):
    tab, _ = tab
    tab.on_job_tick(snap(kind="scan", total=0, cur=0, label="D:\\media"))
    assert "扫描中" in tab.job_label.text()
    assert tab.pos_label.text() == "…"


def test_finished_apply_shows_result(tab):
    tab, _ = tab
    tab.on_job_tick(snap())
    tab.on_job_tick(snap(status="done",
                         result={"moved": 3, "failed": 1, "failures": ["E1"],
                                 "session": "apply-x"}))
    text = tab.result_label.text()
    assert "移动 3 部" in text
    assert "失败 1 部" in text
    assert "E1" in text
    assert "apply-x" in text
    assert tab.bar.property("tone") == "done"
    assert tab.btn_cancel.isEnabled() is False
    assert "空闲" in tab.job_label.text()


def test_finished_undo_shows_result(tab):
    tab, _ = tab
    tab.on_job_tick(snap(kind="undo", label="回滚 U1"))
    tab.on_job_tick(snap(kind="undo", status="done",
                         result={"restored": 2, "skipped": 1, "failed": 0,
                                 "session": "u1"}))
    text = tab.result_label.text()
    assert "还原 2" in text
    assert "跳过 1" in text


def test_failed_job_shows_error(tab):
    tab, _ = tab
    tab.on_job_tick(snap())
    tab.on_job_tick(snap(status="failed", error="源目录已漂移"))
    assert "源目录已漂移" in tab.result_label.text()
    assert tab.bar.property("tone") == "failed"


def test_log_updates_only_on_change(tab):
    tab, _ = tab
    tab.on_job_tick(snap(log=["a", "b"]))
    assert tab.log_view.toPlainText() == "a\nb"
    tab.on_job_tick(snap(log=["a", "b"]))          # 相同内容：不得变文案
    assert tab.log_view.toPlainText() == "a\nb"
    tab.on_job_tick(snap(log=["a", "b", "c"]))
    assert tab.log_view.toPlainText() == "a\nb\nc"


def test_sessions_table_renders(qapp):
    sessions = [
        {"file": "apply-1.jsonl", "kind": "apply", "ts": "2026-11-03 12:00:00",
         "done": 3, "aborted": 0, "plan_id": "p1", "undoes": None},
        {"file": "undo-1.jsonl", "kind": "undo", "ts": "2026-11-03 13:00:00",
         "done": 0, "aborted": 2, "plan_id": None, "undoes": "apply-1.jsonl"},
    ]
    toasts: list[str] = []
    tab = ExecTab(StubState(sessions), toast=toasts.append)
    tab.refresh_sessions()
    table = tab.session_table
    assert table.rowCount() == 1                   # done>0 过滤生效
    assert table.item(0, 0).text() == "apply-1.jsonl"
    assert table.item(0, 1).text() == "执行"
    assert table.item(0, 3).text() == "3"
    assert table.item(0, 4).text() == "0"
    assert table.item(0, 5).text() == "p1"
    cell = table.cellWidget(0, 6)
    assert cell is not None and cell.text() == "预览回滚"

    # 换成 undo 行（kind=undo →「回滚」、aborted 红染、关联计划回落 undoes）
    tab.state._sessions = [{"file": "undo-1.jsonl", "kind": "undo",
                            "ts": "2026-11-03 13:00:00", "done": 2, "aborted": 2,
                            "plan_id": None, "undoes": "apply-1.jsonl"}]
    tab.refresh_sessions()
    assert table.rowCount() == 1
    assert table.item(0, 1).text() == "回滚"
    assert table.item(0, 4).text() == "2"
    assert table.item(0, 5).text() == "apply-1.jsonl"
    tab.deleteLater()

    # 空列表 → 空态文案
    tab2 = ExecTab(StubState([]), toast=toasts.append)
    tab2.refresh_sessions()
    assert tab2.session_table.rowCount() == 0
    assert "暂无可回滚会话" in tab2.sessions_hint.text()
    tab2.deleteLater()


def test_undo_preview_dialog_two_click_arm(qapp):
    ops = [
        {"unit_id": "U1", "kind": "move", "src_dir": "s", "dst_dir": "d",
         "state": "ok"},
        {"unit_id": "U2", "kind": "move", "src_dir": "s2", "dst_dir": "d2",
         "state": "skip_target_missing"},
    ]
    dlg = UndoPreviewDialog(ops, "apply-1.jsonl")
    dlg.show()                                     # 不 exec()：只 show 供可见性断言
    assert dlg.table.rowCount() == 2
    texts = [dlg.table.item(r, 3).text() for r in range(2)]
    assert any("将还原" in t for t in texts)
    assert any("目标不存在→跳过" in t for t in texts)
    assert dlg._armed is False
    dlg.confirm_btn.click()                        # 第一次：武装，不关窗
    assert dlg.isVisible() is True
    assert "再点一次" in dlg.confirm_btn.text()
    dlg.confirm_btn.click()                        # 第二次：确认关闭
    assert dlg.result() == QDialog.Accepted
    assert dlg.isVisible() is False
    dlg.deleteLater()


def test_main_window_static_wiring():
    src = Path("app/ui/main_window.py").read_text(encoding="utf-8")
    assert "ExecTab(" in src
    assert 'self.exec_tab' in src and '"② 执行 / 回滚"' in src
    assert "from .exec_tab import ExecTab" in src
    assert "self.exec_tab.on_job_tick" in src       # 快 tick 喂执行页
    assert "self.exec_tab.refresh_sessions" in src  # 慢 tick 喂会话清单
    assert '"--tab"' in src or "'--tab'" in src     # argparse --tab

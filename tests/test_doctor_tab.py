"""「④ 体检」页视图逻辑单测（offscreen，零磁盘、零线程）：克隆 test_exec_tab.py 范式（D-20261102-02 协议第 1/2/4 条）。

覆盖：演示模式降级、空闲空态、体检启动与忙态、BusyError、
非 preflight 快照忽略、done 渲染（级别前缀 / detail 子节点 / 汇总）、
staging_leftover → 清理按钮、清理后自动重检、failed 汇总、
门禁白名单静态断言与主窗接线。
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.core.jobs import BusyError
from app.ui.doctor_tab import DoctorTab


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class StubState:
    """duck-typing：只实现 DoctorTab 会调用的方法，不 import AppState 以免碰盘。"""

    def __init__(self, items=()):
        self._items = list(items)
        self.started = 0
        self.cleaned = 0

    def start_preflight(self, ids):
        self.started += 1
        return {"ok": True}

    def cleanup_staging(self):
        self.cleaned += 1
        return 3


def snap(**over):
    base = {"id": "pf1", "kind": "preflight", "status": "running", "total": 0,
            "cur": 0, "label": "系统体检", "log": [], "error": None,
            "result": {}}
    base.update(over)
    return base


@pytest.fixture()
def tab(qapp):
    toasts: list[str] = []
    tab = DoctorTab(StubState(), toast=toasts.append)
    yield tab, toasts
    tab.deleteLater()


def test_demo_mode_disables(qapp):
    toasts: list[str] = []
    tab = DoctorTab(None, toast=toasts.append)
    assert tab.btn_doctor.isEnabled() is False
    assert tab.btn_cleanup.isEnabled() is False
    assert "演示模式" in tab.btn_doctor.toolTip()
    assert "演示模式" in tab.btn_cleanup.toolTip()
    assert "演示模式" in tab.empty_hint.text()
    tab.deleteLater()


def test_idle_empty_state(tab):
    tab, _ = tab
    assert "尚未体检" in tab.empty_hint.text()
    assert tab.btn_cleanup.isHidden() is True
    assert tab.result_tree.topLevelItemCount() == 0


def test_run_check_starts_and_busy(tab):
    tab, toasts = tab
    tab._run_check()
    assert tab.state.started == 1
    assert tab.btn_doctor.isEnabled() is False
    assert tab.btn_cleanup.isEnabled() is False
    assert "体检运行中" in tab.empty_hint.text()
    assert any("体检已开始" in t for t in toasts)


def test_run_check_busy_error(qapp):
    toasts: list[str] = []

    class BusyState(StubState):
        def start_preflight(self, ids):
            raise BusyError("已有任务在运行")

    tab = DoctorTab(BusyState(), toast=toasts.append)
    tab._run_check()                               # 不崩
    assert any("已有任务在运行" in t for t in toasts)
    assert tab.btn_doctor.isEnabled() is True      # 不进忙态
    tab.deleteLater()


def test_tick_ignores_other_kinds(tab):
    tab, _ = tab
    tab.on_job_tick(snap(kind="apply"))
    assert tab.btn_doctor.isEnabled() is True      # 不进 busy
    tab.on_job_tick(snap(kind="apply", status="done"))
    assert tab.btn_doctor.isEnabled() is True


def test_preflight_done_renders_items(tab):
    tab, _ = tab
    tab.on_job_tick(snap())
    items = [
        {"level": "block", "code": "paths_missing", "message": "目录不存在",
         "detail": ["D:\\nope1", "D:\\nope2"]},
        {"level": "warn", "code": "long_paths", "message": "存在超长路径",
         "detail": ["D:\\x" + "a" * 300]},
        {"level": "info", "code": "jellyfin_ok", "message": "Jellyfin 未运行",
         "detail": []},
    ]
    tab.on_job_tick(snap(status="done", result={"items": items}))
    tree = tab.result_tree
    assert tree.topLevelItemCount() == 3
    root0 = tree.topLevelItem(0)
    assert "阻断" in root0.text(0) and "目录不存在" in root0.text(0)
    assert root0.childCount() == 2
    root1 = tree.topLevelItem(1)
    assert "提醒" in root1.text(0) and "超长路径" in root1.text(0)
    assert root1.childCount() == 1
    root2 = tree.topLevelItem(2)
    assert "通过" in root2.text(0) and "Jellyfin 未运行" in root2.text(0)
    assert root2.childCount() == 0
    assert tab.btn_cleanup.isVisible() is False    # 无 staging 残留
    assert tab.btn_doctor.isEnabled() is True      # 按钮恢复可用
    assert tab.btn_cleanup.isEnabled() is True


def test_staging_leftover_shows_cleanup(tab):
    tab, _ = tab
    tab.on_job_tick(snap())
    items = [{"level": "warn", "code": "staging_leftover",
              "message": "发现半成品残留", "detail": [".incomplete-x"]}]
    tab.on_job_tick(snap(status="done", result={"items": items}))
    assert tab.btn_cleanup.isHidden() is False


def test_cleanup_runs_and_reruns(tab):
    tab, toasts = tab
    tab._run_check()
    tab.on_job_tick(snap())
    items = [{"level": "warn", "code": "staging_leftover",
              "message": "发现半成品残留", "detail": []}]
    tab.on_job_tick(snap(status="done", result={"items": items}))
    tab._cleanup()
    assert tab.state.cleaned == 1
    assert any("已清理 3 处" in t for t in toasts)
    assert tab.state.started == 2                  # 自动重检


def test_preflight_failed_shows_error(tab):
    tab, _ = tab
    tab.on_job_tick(snap())
    tab.on_job_tick(snap(status="failed", error="超时"))
    assert "体检任务失败" in tab.empty_hint.text()
    assert "超时" in tab.empty_hint.text()
    assert tab.btn_doctor.isEnabled() is True


def test_no_block_summary_added(tab):
    tab, _ = tab
    tab.on_job_tick(snap())
    items = [{"level": "info", "code": "jellyfin_ok", "message": "ok",
              "detail": []}]
    tab.on_job_tick(snap(status="done", result={"items": items}))
    assert "未发现阻断项" in tab.result_tree.topLevelItem(0).text(0)


def test_non_ackable_whitelist_static():
    src = Path("app/ui/plan_tab.py").read_text(encoding="utf-8")
    assert ('NON_ACKABLE = frozenset({"paths_missing", "disk_space", '
            '"staging_leftover"})') in src
    mw = Path("app/ui/main_window.py").read_text(encoding="utf-8")
    assert "DoctorTab(" in mw
    assert '"④ 体检"' in mw
    assert "self.doctor_tab.on_job_tick" in mw

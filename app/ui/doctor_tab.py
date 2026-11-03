"""④ 体检页：系统体检报告 + staging 半成品残留一键清理。

线程纪律（D-20261102-01）：本页不建线程、不建 QTimer、不发 HTTP——
- 体检经 state.start_preflight(ids) 走 JobManager 后台线程
  （进程探测最长 15s + 磁盘遍历，严禁 UI 线程直调 preflight_items）；
- 快 tick 由 MainWindow 喂 on_job_tick(snap)（只读内存快照收结果，
  只认 kind=preflight，扫描/搬运任务不影响本页忙态）；
- cleanup_staging 是 staging 目录内小遍历（仅 .incomplete-* 目录，
  量级小），允许 UI 线程同步调。

state=None 即演示模式：两按钮禁用 + 降级文案。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.jobs import BusyError
from ..state import AppState
from . import theme

DEMO_TEXT = "演示模式（假数据），不连接真实配置"
IDLE_TEXT = "尚未体检。点击上方按钮开始"
LEVEL_PREFIX = {"block": "【阻断】", "warn": "【提醒】", "info": "【通过】"}
LEVEL_COLOR = {"block": theme.BAD, "warn": theme.WARN, "info": theme.OK}


class DoctorTab(QWidget):
    def __init__(self, state: AppState | None, toast=None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.toast = toast or (lambda msg: None)
        self._job_seen_running = False
        self._last_job_id: str | None = None
        self._build()

    # ------------------------------------------------------------ 界面构建

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        card = QFrame()
        card.setProperty("card", True)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_doctor = QPushButton("运行系统体检")
        self.btn_doctor.setProperty("role", "primary")
        self.btn_doctor.clicked.connect(self._run_check)
        row.addWidget(self.btn_doctor)
        row.addStretch(1)
        tip = QLabel("体检含进程探测（最长 15 秒），后台运行不卡界面")
        tip.setProperty("dim", True)
        row.addWidget(tip)
        self.btn_cleanup = QPushButton("清理半成品残留")
        self.btn_cleanup.setProperty("role", "danger")
        self.btn_cleanup.setVisible(False)
        self.btn_cleanup.clicked.connect(self._cleanup)
        row.addWidget(self.btn_cleanup)
        cl.addLayout(row)

        self.result_tree = QTreeWidget()
        self.result_tree.setColumnCount(2)
        self.result_tree.setHeaderLabels(["检查项", ""])
        self.result_tree.header().setStretchLastSection(True)
        self.result_tree.setAlternatingRowColors(False)
        self.result_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        cl.addWidget(self.result_tree, 1)

        self.empty_hint = QLabel(IDLE_TEXT)
        self.empty_hint.setProperty("dim", True)
        self.empty_hint.setAlignment(Qt.AlignCenter)
        cl.addWidget(self.empty_hint)
        root.addWidget(card, 1)

        if self.state is None:                      # 演示模式降级
            self.btn_doctor.setEnabled(False)
            self.btn_cleanup.setEnabled(False)
            self.btn_doctor.setToolTip(DEMO_TEXT)
            self.btn_cleanup.setToolTip(DEMO_TEXT)
            self.empty_hint.setText(DEMO_TEXT)

    # ------------------------------------------------------------ 动作

    def _set_busy(self, busy: bool) -> None:
        self.btn_doctor.setEnabled(not busy)
        self.btn_cleanup.setEnabled(not busy)
        self.empty_hint.setStyleSheet("")
        self.empty_hint.show()
        self.empty_hint.setText("体检运行中…" if busy else IDLE_TEXT)

    def _run_check(self) -> None:
        if self.state is None:
            self.toast(DEMO_TEXT)
            return
        try:
            self.state.start_preflight(None)
        except BusyError as exc:
            self.toast(str(exc))
            return
        self.toast("体检已开始")
        self._set_busy(True)

    def _cleanup(self) -> None:
        try:
            n = self.state.cleanup_staging()
        except Exception as exc:                     # noqa: BLE001
            self.toast(str(exc))
            return
        self.toast(f"已清理 {n} 处残留")
        self._run_check()                            # 等价网页版重检语义

    # ------------------------------------------------------------ 快 tick

    def on_job_tick(self, snap: dict | None) -> None:
        """快 tick（约 300ms）转发：只读 job.snapshot()，不碰磁盘（纪律 3）。

        本页只关心 kind=preflight 的任务：其余 kind（扫描/搬运）直接忽略，
        避免把别的任务误当体检忙态。
        """
        if not snap or snap.get("kind") != "preflight":
            return
        if snap.get("status") == "running":
            self._job_seen_running = True
            self._set_busy(True)
            return
        if self._job_seen_running and snap.get("id") != self._last_job_id:
            self._last_job_id = snap.get("id")
            self._job_seen_running = False
            self._on_preflight_finished(snap)

    def _on_preflight_finished(self, snap: dict) -> None:
        self._set_busy(False)
        if snap.get("status") == "failed":
            self.empty_hint.setText(f"体检任务失败：{snap.get('error')}")
            self.empty_hint.setStyleSheet(f"color:{theme.BAD};")
            return
        self.result_tree.clear()
        items = (snap.get("result") or {}).get("items") or []
        has_block = False
        for it in items:
            level = str(it.get("level", "info"))
            code = str(it.get("code", ""))
            message = str(it.get("message", code))
            if level == "block":
                has_block = True
            prefix = LEVEL_PREFIX.get(level, "")
            color = QColor(LEVEL_COLOR.get(level, theme.DIM))
            root = QTreeWidgetItem([f"{prefix}{message}", ""])
            root.setForeground(0, color)
            detail = [str(d) for d in it.get("detail") or []]
            for d in detail:
                child = QTreeWidgetItem([d, ""])
                child.setForeground(0, QColor(theme.DIM))
                root.addChild(child)
            root.setExpanded(bool(detail))
            self.result_tree.addTopLevelItem(root)
        if not has_block:
            summary = QTreeWidgetItem(["✓ 未发现阻断项", ""])
            summary.setForeground(0, QColor(theme.OK))
            self.result_tree.insertTopLevelItem(0, summary)
        self.btn_cleanup.setVisible(
            any(str(i.get("code")) == "staging_leftover" for i in items))
        self.empty_hint.hide()   # 结果已渲染，空态提示让位

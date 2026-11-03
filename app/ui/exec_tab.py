"""② 执行 / 回滚页：进度条 / 日志 / 取消 / 会话清单 / 两击回滚确认。

线程纪律（D-20261102-01）：本页不建线程、不建 QTimer——
- 快 tick 由 MainWindow 喂 on_job_tick(snap)（只读内存快照）；
- 慢 tick 喂 refresh_sessions()（唯一允许调 state.sessions() 的地方）；
- undo_preview 单会话文件量级小，允许 UI 线程调用。

state=None 即演示模式：控制禁用 + 会话区显示降级文案。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.jobs import BusyError
from ..state import AppState
from . import theme

KIND_CN = {"scan": "扫描中", "apply": "执行中", "undo": "回滚中"}
SESSION_KIND_CN = {"apply": "执行", "undo": "回滚"}
CANON = {"ok": "将还原", "skip_target_missing": "目标不存在→跳过",
         "skip_src_exists": "源已存在→跳过"}
DEMO_TEXT = "演示模式（假数据），不连接真实配置"


def _fmt_failure(x) -> str:
    if isinstance(x, dict):
        return f"✗ {x.get('label', '?')}：{x.get('error', '')}"
    return f"✗ {x!s}"


class ExecTab(QWidget):
    def __init__(self, state: AppState | None, toast=None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.toast = toast or (lambda msg: None)
        self._job_seen_running = False
        self._last_job_id: str | None = None
        self._log_text = ""
        self._session_rows: list[dict] = []
        self._build()
        self.refresh_sessions()

    # ------------------------------------------------------------ 界面构建

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        # ---- 运行区
        card = QFrame()
        card.setProperty("card", True)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.job_label = QLabel("空闲")
        row.addWidget(self.job_label)
        row.addStretch(1)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.bar.setFixedWidth(240)
        row.addWidget(self.bar)
        self.pos_label = QLabel("…")
        row.addWidget(self.pos_label)
        self.btn_cancel = QPushButton("取消任务")
        self.btn_cancel.setProperty("role", "danger")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel)
        row.addWidget(self.btn_cancel)
        cl.addLayout(row)

        self.log_view = QPlainTextEdit()
        self.log_view.setProperty("log", True)
        self.log_view.setReadOnly(True)
        cl.addWidget(self.log_view, 1)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        cl.addWidget(self.result_label)
        root.addWidget(card, 1)

        # ---- 回滚区
        rc = QFrame()
        rc.setProperty("card", True)
        rl = QVBoxLayout(rc)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(10)
        title = QLabel("回滚会话")
        head.addWidget(title)
        head.addStretch(1)
        tip = QLabel("按时间倒序，仅显示有已完成操作的会话")
        tip.setProperty("dim", True)
        head.addWidget(tip)
        rl.addLayout(head)

        self.sessions_hint = QLabel("")
        self.sessions_hint.setProperty("dim", True)
        self.sessions_hint.setAlignment(Qt.AlignCenter)
        self.sessions_hint.hide()
        rl.addWidget(self.sessions_hint)

        self.session_table = QTableWidget(0, 7)
        self.session_table.setHorizontalHeaderLabels(
            ["会话", "类型", "时间", "成功", "中止", "关联计划", ""])
        self.session_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.session_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.session_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.session_table.verticalHeader().setVisible(False)
        self.session_table.setWordWrap(False)
        self.session_table.horizontalHeader().setStretchLastSection(True)
        self.session_table.cellDoubleClicked.connect(
            self._on_cell_double_clicked)
        rl.addWidget(self.session_table, 1)
        root.addWidget(rc, 2)

        if self.state is None:                      # 演示模式降级
            self.btn_cancel.setToolTip(DEMO_TEXT)

    def _set_tone(self, tone: str | None) -> None:
        self.bar.setProperty("tone", tone)
        st = self.bar.style()
        st.unpolish(self.bar)
        st.polish(self.bar)

    # ------------------------------------------------------------ 快 tick

    def on_job_tick(self, snap: dict | None) -> None:
        """快 tick（约 300ms）转发：只读 job.snapshot()，不碰磁盘（纪律 3）。"""
        if snap and snap.get("status") == "running":
            self._job_seen_running = True
            self._show_running(snap)
            return
        if snap and self._job_seen_running and snap.get("id") != self._last_job_id:
            self._last_job_id = snap.get("id")
            self._job_seen_running = False
            self._on_job_finished(snap)
            # 会话清单不在快 tick 刷新（纪律 3：快 tick 只读内存），
            # 慢 tick ≤2s 内自然拉到新会话。

    def _show_running(self, snap: dict) -> None:
        kind = str(snap.get("kind", ""))
        label = (snap.get("label") or "").strip()
        self.job_label.setText(f"{KIND_CN.get(kind, '任务')}：{label}")
        total = snap.get("total") or 0
        cur = snap.get("cur") or 0
        self.bar.setRange(0, max(total, 1))
        self.bar.setValue(cur if total > 0 else 0)
        self._set_tone(None)
        self.pos_label.setText(f"{cur}/{total}" if total > 0 else "…")
        self.btn_cancel.setEnabled(True)
        self._refresh_log(snap)

    def _on_job_finished(self, snap: dict) -> None:
        self._refresh_log(snap)
        self.bar.setValue(self.bar.maximum())
        self._set_tone("failed" if snap.get("status") == "failed" else "done")
        self.btn_cancel.setEnabled(False)
        self.job_label.setText("空闲")
        self.result_label.setText(self._result_text(snap))

    def _result_text(self, snap: dict) -> str:
        kind, status = snap.get("kind"), snap.get("status")
        result = snap.get("result") or {}
        lines: list[str] = []
        if status == "failed":
            return (f'<span style="color:{theme.BAD}">'
                    f"任务失败：{snap.get('error')}</span>")
        if kind == "apply":
            lines.append(f"移动 {result.get('moved', 0)} 部，"
                         f"失败 {result.get('failed', 0)} 部")
            fails = result.get("failures") or []
            for x in list(fails)[:10]:
                lines.append(_fmt_failure(x))
            if len(fails) > 10:
                lines.append(f"…等共 {len(fails)} 条")
            session = result.get("session")
            if session:
                lines.append(f"已写入回滚会话 {session}，可在下方一键回滚")
        elif kind == "undo":
            lines.append(f"还原 {result.get('restored', 0)}，"
                         f"跳过 {result.get('skipped', 0)}，"
                         f"失败 {result.get('failed', 0)}")
        elif kind == "scan":
            lines.append(f"扫描完成：就绪 {result.get('ready', '?')} 部")
        return "\n".join(lines)

    def _refresh_log(self, snap: dict) -> None:
        text = "\n".join(snap.get("log") or [])
        if text == self._log_text:
            return
        self._log_text = text
        self.log_view.setPlainText(text)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ------------------------------------------------------------ 取消

    def _on_cancel(self) -> None:
        if self.state is None:
            self.toast(DEMO_TEXT)
            return
        try:
            cancelled = self.state.cancel_job()
        except Exception as exc:                     # noqa: BLE001
            self.toast(str(exc))
            return
        self.toast("已请求取消，将在当前单元完成后停止" if cancelled
                   else "当前没有正在运行的任务")

    # ------------------------------------------------------------ 会话清单

    def refresh_sessions(self) -> None:
        """会话清单渲染（唯一允许调 state.sessions() 的地方；慢活，仅慢 tick 调）。"""
        self._session_rows = []
        self.session_table.setRowCount(0)
        if self.state is None:
            self.sessions_hint.setText(DEMO_TEXT)
            self.sessions_hint.show()
            return
        rows = [s for s in self.state.sessions() if s.get("done", 0) > 0]
        self._session_rows = rows
        if not rows:
            self.sessions_hint.setText("暂无可回滚会话")
            self.sessions_hint.show()
            return
        self.sessions_hint.hide()
        for r, s in enumerate(rows):
            kind_txt = SESSION_KIND_CN.get(str(s.get("kind")), str(s.get("kind")))
            plan_id = s.get("plan_id") or s.get("undoes") or "-"
            vals = [str(s.get("file") or ""), kind_txt, str(s.get("ts") or ""),
                    str(s.get("done", 0)), str(s.get("aborted", 0)), plan_id]
            self.session_table.insertRow(r)
            for c, text in enumerate(vals):
                it = QTableWidgetItem(text)
                if c == 4 and s.get("aborted", 0) > 0:
                    it.setForeground(QColor(theme.BAD))
                self.session_table.setItem(r, c, it)
            fname = str(s.get("file") or "")
            btn = QPushButton("预览回滚")
            btn.clicked.connect(lambda _=False, f=fname: self._open_undo_preview(f))
            self.session_table.setCellWidget(r, 6, btn)

    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._session_rows):
            self._open_undo_preview(str(self._session_rows[row].get("file") or ""))

    def _open_undo_preview(self, fname: str) -> None:
        if self.state is None:
            self.toast(DEMO_TEXT)
            return
        try:
            data = self.state.undo_preview(fname)
        except ValueError as exc:
            self.toast(str(exc))
            return
        dlg = UndoPreviewDialog(data.get("ops") or [], fname, parent=self)
        if dlg.exec() == QDialog.Accepted:
            try:
                self.state.start_undo(fname)
            except BusyError as exc:
                self.toast(str(exc))
                return
            self.toast(f"已开始回滚 {fname}，进度见上方")


class UndoPreviewDialog(QDialog):
    def __init__(self, ops: list[dict], fname: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"回滚预览：{fname}")
        self.setMinimumWidth(720)
        self._armed = False

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)
        head = QLabel(f"共 {len(ops)} 条操作，将按逆序还原")
        v.addWidget(head)

        self.table = QTableWidget(len(ops), 4)
        self.table.setHorizontalHeaderLabels(["影片", "从", "还原到", "状态"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        for r, e in enumerate(ops):
            st = str(e.get("state", ""))
            vals = [e.get("unit_id", "?"), e.get("dst_dir", ""),
                    e.get("src_dir", ""), CANON.get(st, st)]
            dim = st.startswith("skip")
            for c, text in enumerate(vals):
                it = QTableWidgetItem(str(text))
                if dim:
                    it.setForeground(QColor(theme.DIM))
                self.table.setItem(r, c, it)
        v.addWidget(self.table, 1)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        foot.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        foot.addWidget(cancel)
        self.confirm_btn = QPushButton("执行回滚")
        self.confirm_btn.setProperty("role", "danger")
        self.confirm_btn.clicked.connect(self._confirm)
        foot.addWidget(self.confirm_btn)
        v.addLayout(foot)

    def _confirm(self) -> None:
        if not self._armed:
            self._armed = True
            self.confirm_btn.setText("⚠ 再点一次确认执行回滚")
            return
        self.accept()

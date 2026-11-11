"""① 分类计划页：真数据版（Phase-0 样机毕业，接 AppState + PlanViewModel）。

本层不做业务决策：勾选/筛选/改判/汇总全部在 app/ui/viewmodel.py，
任务编排在 app/state.py 与 app/core/jobs.py；这里只做渲染与事件转发。
state=None 时进入演示模式（假数据，任务按钮禁用），供样式走查与截图。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.config import load_config
from ..core.jobs import BusyError
from ..core.planner import plan_digest
from ..state import AppState
from . import theme
from .table_cells import (
    COL_CHECK,
    COL_CONF,
    COL_FILES,
    COL_LEVEL,
    COL_LIB,
    COL_SIZE,
    COL_STATUS,
    COL_TITLE,
    CellDelegate,
)
from .viewmodel import (
    PlanViewModel,
    card_tones,
    confidence_badge,
    human_size,
    level_badge,
    status_badge,
)


def override_libs(rows: list[dict], config_libs: list[str] | None) -> list[str]:
    """改判候选库：配置全量库 ∪ 计划内命中库（均不含兜底库）。

    历史缺陷：仅取当前可见行 target_lib 去重集合，某库本次扫描零命中
    （或行被筛选/搜索隐藏）时下拉框无该库，无从改判入内（2026-11-12 反馈）。
    config_libs 为 None（演示模式/配置不可读）时回退纯计划内集合。
    """
    libs = {u["target_lib"] for u in rows} - {"兜底库"}
    if config_libs:
        libs |= set(config_libs) - {"兜底库"}
    return sorted(libs)


class PlanTab(QWidget):
    def __init__(self, state: AppState | None, units: list[dict] | None = None,
                 toast=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.demo_units = units
        self.toast = toast or (lambda msg: None)
        self.vm: PlanViewModel | None = None
        self._digest: str | None = None
        self._rows: list[dict] = []
        self._current_unit: dict | None = None
        self._libs: list[str] = []
        self._populating = True
        self._await_preflight: list[str] | None = None   # 非 None 表示正在等体检结果
        self._job_seen_running = False
        self._last_job_id: str | None = None
        self._build()
        self.refresh(force=True)
        if self.state is None:                           # 演示模式：任务按钮禁用
            for b in (self.btn_scan, self.btn_apply):
                b.setEnabled(False)
                b.setToolTip("演示模式（假数据），不连接真实配置")
            for b in (self.btn_browse_out, self.btn_clear_out):
                b.setEnabled(False)
                b.setToolTip("演示模式（假数据），不连接真实配置")
            self.f_out_dir.setEnabled(False)
            self.chk_by_category.setEnabled(False)

    # ------------------------------------------------------------ 界面构建

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        self.cards_bar = QHBoxLayout()
        self.cards_bar.setSpacing(10)
        root.addLayout(self.cards_bar)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self._chips: dict[str, QPushButton] = {}
        for key, text in (("all", "全部"), ("ready", "可执行"), ("rule", "规则"),
                          ("plot", "摘要预判"), ("learned", "自学习"),
                          ("fallback", "兜底"), ("blocked", "冲突/残留"),
                          ("applied", "已执行")):
            btn = QPushButton(text)
            btn.setProperty("fchip", "on" if key == "all" else "off")
            btn.clicked.connect(lambda _=False, k=key: self.set_filter(k))
            self._chips[key] = btn
            bar.addWidget(btn)
        bar.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索片名 / 题材 / 目标库")
        self.search.setFixedWidth(250)
        self.search.textChanged.connect(self.set_query)
        bar.addWidget(self.search)
        root.addLayout(bar)

        self.empty_hint = QLabel("尚未扫描。配置好源目录与媒体库后，点右下角「重新扫描」。")
        self.empty_hint.setProperty("dim", True)
        self.empty_hint.hide()
        root.addWidget(self.empty_hint)

        # 配置漂移横幅：计划是旧配置时代扫描的产物时提示重扫（防止拿旧
        # 判定勾选执行——执行前体检会拦，但视觉上先一步说明更直观）。
        self.stale_hint = QLabel(
            "⚠ 配置在本次扫描后有变更，下方计划仍是旧配置的判定结果"
            "——请点右下角「重新扫描」更新后再勾选执行。")
        self.stale_hint.setWordWrap(True)
        self.stale_hint.setStyleSheet(f"color:{theme.WARN};")
        self.stale_hint.hide()
        root.addWidget(self.stale_hint)

        self.splitter = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["✓", "影片", "判定", "置信", "目标库", "文件", "体积", "状态"])
        self.table.setItemDelegate(CellDelegate(self.table))
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)      # delegate 逐格填色，网格会露成列间竖缝
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setWordWrap(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setSectionResizeMode(COL_TITLE, QHeaderView.Stretch)
        for col, width in ((COL_CHECK, 40), (COL_LEVEL, 96), (COL_CONF, 62),
                           (COL_LIB, 92), (COL_FILES, 62), (COL_SIZE, 92),
                           (COL_STATUS, 110)):
            self.table.setColumnWidth(col, width)
        for col, align in ((COL_TITLE, Qt.AlignLeft), (COL_LEVEL, Qt.AlignLeft),
                           (COL_LIB, Qt.AlignLeft), (COL_STATUS, Qt.AlignLeft),
                           (COL_CONF, Qt.AlignRight), (COL_FILES, Qt.AlignRight),
                           (COL_SIZE, Qt.AlignRight)):
            head = self.table.horizontalHeaderItem(col)
            if head:
                head.setTextAlignment(align | Qt.AlignVCenter)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self._detail_panel())
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([900, 360])
        root.addWidget(self.splitter, 1)

        bottom = QFrame()
        bottom.setProperty("bottombar", True)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(14, 8, 14, 8)
        bl.setSpacing(10)
        self.summary = QLabel("")
        self.summary.setProperty("mini", True)
        bl.addWidget(self.summary)
        bl.addStretch(1)
        self.lbl_out = QLabel("本次输出")
        self.lbl_out.setProperty("dim", True)
        self.lbl_out.setToolTip("仅对本次执行生效，不写入全局配置；重新扫描后自动清空")
        self.f_out_dir = QLineEdit()
        self.f_out_dir.setReadOnly(True)
        self.f_out_dir.setPlaceholderText("未选择（按计划库路径输出）")
        self.f_out_dir.setFixedWidth(220)
        self.btn_browse_out = QPushButton("浏览…")
        self.btn_browse_out.clicked.connect(self._browse_output_dir)
        self.btn_clear_out = QPushButton("清除")
        self.btn_clear_out.setEnabled(False)
        self.btn_clear_out.clicked.connect(self._clear_output_dir)
        self.chk_by_category = QCheckBox("按类别建子文件夹")
        self.chk_by_category.setChecked(True)          # D2 默认开
        self.chk_by_category.toggled.connect(self._on_category_toggled)
        for w in (self.lbl_out, self.f_out_dir, self.btn_browse_out,
                  self.btn_clear_out, self.chk_by_category):
            bl.addWidget(w)
        self.btn_all = QPushButton("全选可执行")
        self.btn_all.clicked.connect(self._select_ready)
        self.btn_clear = QPushButton("清空选择")
        self.btn_clear.clicked.connect(self._clear_selection)
        self.btn_scan = QPushButton("重新扫描")
        self.btn_scan.clicked.connect(self._start_scan)
        self.btn_apply = QPushButton("执行选中")
        self.btn_apply.setProperty("role", "primary")
        self.btn_apply.clicked.connect(self._apply_selected)
        for b in (self.btn_all, self.btn_clear, self.btn_scan, self.btn_apply):
            bl.addWidget(b)
        root.addWidget(bottom)

    def _detail_panel(self) -> QFrame:
        panel = QFrame()
        panel.setProperty("panel", True)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        title = QLabel("选中行详情")
        title.setProperty("sectionTitle", True)
        lay.addWidget(title)
        self.d_name = QLabel("（点选左侧任一行）")
        self.d_name.setWordWrap(True)
        lay.addWidget(self.d_name)
        self.d_src = QLabel("")
        self.d_src.setProperty("dim", True)
        self.d_src.setWordWrap(True)
        lay.addWidget(self.d_src)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(5)
        self.d_fields: dict[str, QLabel] = {}
        for row, (key, label) in enumerate((
                ("level", "判定"), ("conf", "置信度"), ("lib", "当前目标库"),
                ("files", "文件数"), ("size", "体积"), ("status", "状态"),
                ("dst", "目标路径"))):
            lab = QLabel(label)
            lab.setProperty("dim", True)
            grid.addWidget(lab, row, 0)
            if key in ("level", "status"):
                w = QLabel("—")
                # 空态不挂 badge 属性：否则未选中行时 "—" 外面套着描边空胶囊，
                # 看着像有个空徽章（真数据核验 D 项）。选中后由 _set_badge 挂上。
                w.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
            else:
                w = QLabel("—")
                w.setWordWrap(True)
                w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.d_fields[key] = w
            # 显式对齐：否则徽章的 Maximum 策略会让整列退化成"标签左/值右"
            grid.addWidget(w, row, 1, Qt.AlignLeft | Qt.AlignVCenter)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        ev = QLabel("判定依据")
        ev.setProperty("sectionTitle", True)
        lay.addSpacing(6)
        lay.addWidget(ev)
        self.d_evidence = QListWidget()
        self.d_evidence.setMinimumHeight(72)
        lay.addWidget(self.d_evidence)

        lay.addSpacing(4)
        ov = QLabel("改判目标库")
        ov.setProperty("sectionTitle", True)
        lay.addWidget(ov)
        self.d_override = QComboBox()
        self.d_override.currentTextChanged.connect(self._on_override_changed)
        lay.addWidget(self.d_override)
        hint = QLabel("改判记 2 票自学习；「执行选中」按改判后的目标库搬运。")
        hint.setProperty("mini", True)
        hint.setWordWrap(True)
        lay.addWidget(hint)
        return panel

    # ------------------------------------------------------------ 数据刷新

    def refresh(self, force: bool = False) -> None:
        """慢 tick / 任务完成后的全量刷新。勾选与改判挂在 id 上，重建不丢。

        计划未变（digest 相同）时直接返回——慢 tick 每 2s 调一次，
        重建 5000 行表格既浪费也会重置滚动位置。
        """
        if self.state is None:                        # 演示模式：只建一次
            if self.vm is not None and not force:
                return
            self.vm = PlanViewModel(self.demo_units or [])
        else:
            plan = self.state.plan()
            # 过期横幅必须在 digest 早退之前更新：改配置不动 plan，
            # digest 不变时若不在这里判一次，横幅永远不亮。
            self._update_stale_hint(plan)
            digest = plan_digest(plan) if plan else None
            if not force and digest == self._digest:
                return
            self.vm = PlanViewModel(plan["units"] if plan else [])
            self._digest = digest
        self._rebuild_cards()
        self._rebuild_table()
        self.empty_hint.setVisible(not self.vm.stats()["total"])
        self._update_summary()
        self._sync_output_controls()

    def _rebuild_cards(self) -> None:
        while self.cards_bar.count():
            item = self.cards_bar.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # 配色决策在 viewmodel.card_tones（可单测），本层只渲染
        for value, label, tone in card_tones(self.vm.stats()):
            frame = QFrame()
            frame.setProperty("card", True)
            lay = QVBoxLayout(frame)
            lay.setContentsMargins(14, 8, 14, 8)
            lay.setSpacing(1)
            v = QLabel(value)
            v.setProperty("cardValue", tone)
            t = QLabel(label)
            t.setProperty("cardLabel", True)
            lay.addWidget(v)
            lay.addWidget(t)
            self.cards_bar.addWidget(frame)
        self.cards_bar.addStretch(1)

    def _rebuild_table(self) -> None:
        self._rows = self.vm.rows()
        self._populating = True
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(self._rows))
        for r, u in enumerate(self._rows):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            chk.setCheckState(Qt.Checked if u["id"] in self.vm.checked else Qt.Unchecked)
            chk.setData(Qt.UserRole, u["id"])
            self.table.setItem(r, COL_CHECK, chk)

            it = QTableWidgetItem(u["label"])
            if u["status"] not in ("ready", "applied"):
                it.setForeground(QColor(theme.FB))
            self.table.setItem(r, COL_TITLE, it)

            text, badge = level_badge(u)
            item = QTableWidgetItem(text)
            item.setData(Qt.UserRole, badge)
            self.table.setItem(r, COL_LEVEL, item)

            ctext, ctone = confidence_badge(u)
            item = QTableWidgetItem(ctext)
            item.setData(Qt.UserRole, ctone)
            item.setToolTip(f"置信等级：{u.get('confidence') or '—'}")
            self.table.setItem(r, COL_CONF, item)

            overridden = u["id"] in self.vm.overrides
            lib = QTableWidgetItem(self.vm.effective_target_lib(u)
                                   + (" *" if overridden else ""))
            lib.setForeground(QColor(theme.ACC if overridden else theme.DIM))
            if overridden:
                lib.setToolTip("目标库由人工指定")
            self.table.setItem(r, COL_LIB, lib)

            self.table.setItem(r, COL_FILES, QTableWidgetItem(str(u["file_count"])))
            self.table.setItem(r, COL_SIZE, QTableWidgetItem(human_size(u["total_size"])))

            text, badge = status_badge(u)
            item = QTableWidgetItem(text)
            item.setData(Qt.UserRole, badge)
            self.table.setItem(r, COL_STATUS, item)
        self.table.setUpdatesEnabled(True)
        self._populating = False

    # ------------------------------------------------------------ 任务联动

    def on_job_tick(self, snap: dict | None) -> None:
        """快 tick（约 300ms）转发：只读 job.snapshot()，不碰磁盘（纪律 3）。"""
        if snap and snap["status"] == "running":
            self._job_seen_running = True
            self._set_busy(True)
            return
        self._set_busy(False)
        if snap and self._job_seen_running and snap.get("id") != self._last_job_id:
            self._last_job_id = snap.get("id")
            self._job_seen_running = False
            self._on_job_finished(snap)

    def _set_busy(self, busy: bool) -> None:
        for b in (self.btn_scan, self.btn_apply, self.btn_all, self.btn_clear):
            b.setEnabled(not busy and self.state is not None)
        # 任务运行中禁止改会话输出参数（演示模式下 state 为 None 保持禁用）
        for w in (self.btn_browse_out, self.btn_clear_out,
                  self.chk_by_category, self.f_out_dir):
            w.setEnabled(not busy and self.state is not None)
        if self.vm is not None and self.state is not None and not busy:
            self._sync_output_controls()

    def _on_job_finished(self, snap: dict) -> None:
        kind, status = snap.get("kind"), snap.get("status")
        if kind in ("scan", "apply", "undo"):
            self.refresh(force=True)
        if kind == "preflight" and self._await_preflight is not None:
            ids, self._await_preflight = self._await_preflight, None
            if status != "done":
                self.toast(f"体检失败：{snap.get('error') or '未知错误'}")
                return
            self._after_preflight(ids, (snap.get("result") or {}).get("items") or [])

    def _start_scan(self) -> None:
        if self.state is None:
            return
        try:
            self.state.start_scan()
            self._job_seen_running = True
            self.toast("扫描已开始（只读预览，不碰文件）")
        except BusyError as exc:
            self.toast(str(exc))

    def _apply_selected(self) -> None:
        if self.state is None:
            return
        ids = self.vm.checked_ids()
        if not ids:
            self.toast("未勾选任何影片")
            return
        bad = self.vm.checked_not_ready()
        if bad:
            self.toast(f"有 {len(bad)} 部不可执行（冲突/残留），请先处理或取消勾选")
            return
        try:
            self.state.start_preflight(ids)
            self._await_preflight = ids
            self._job_seen_running = True
            self.toast("执行前体检中…（Jellyfin 进程 / 磁盘空间 / staging 残留）")
        except BusyError as exc:
            self.toast(str(exc))

    def _after_preflight(self, ids: list[str], items: list[dict]) -> None:
        blocks = [i for i in items if i["level"] == "block"]
        overrides = dict(self.vm.overrides)
        if not blocks:
            self._start_apply(ids, set(), overrides)
            return
        acks = BlockConfirmDialog(blocks, self).acked_codes()
        if acks is None:
            self.toast("已取消执行（预检未通过）")
            return
        self._start_apply(ids, acks, overrides)

    def _start_apply(self, ids: list[str], acks: set[str],
                     overrides: dict[str, str]) -> None:
        try:
            self.state.start_apply(ids, acks, overrides,
                                   output_root=self.vm.output_root,
                                   group_by_category=self.vm.group_by_category)
            self._job_seen_running = True
            self.toast(f"已开始搬运 {len(ids)} 部影片，进度见「② 执行 / 回滚」")
        except BusyError as exc:
            self.toast(str(exc))

    # ------------------------------------------------------ 本次输出目录

    def _browse_output_dir(self) -> None:
        if self.state is None or self.vm is None:
            return
        chosen = QFileDialog.getExistingDirectory(
            self, "选择本次输出目录", self.vm.output_root or "")
        if not chosen:
            return
        self.vm.set_output_root(chosen)
        self._sync_output_controls()
        self.toast(f"本次输出目录已设置（仅对下次执行生效）：{chosen}")

    def _clear_output_dir(self) -> None:
        if self.vm is None:
            return
        self.vm.set_output_root(None)
        self._sync_output_controls()

    def _on_category_toggled(self, on: bool) -> None:
        if self.vm is not None:
            self.vm.group_by_category = on

    def _sync_output_controls(self) -> None:
        if self.vm is None:
            return
        self.f_out_dir.setText(self.vm.output_root or "")
        self.chk_by_category.setChecked(self.vm.group_by_category)
        has = bool(self.vm.output_root)
        self.btn_clear_out.setEnabled(has)
        self.chk_by_category.setEnabled(has)

    def _update_stale_hint(self, plan: dict | None) -> None:
        """计划 config_hash 与当前配置不一致 → 计划页顶部挂过期横幅。

        计划没有哈希（旧版 plan.json / 演示数据）或配置非法（config_hash
        为 None）时不判过期也不亮横幅——宁可无提示也不误报。
        """
        if plan is None or self.state is None:
            self.stale_hint.hide()
            return
        plan_hash = plan.get("config_hash")
        if not plan_hash:
            self.stale_hint.hide()
            return
        cur = self.state.config_hash()
        self.stale_hint.setVisible(bool(cur) and plan_hash != cur)

    # ------------------------------------------------------------ 交互

    def _on_table_context_menu(self, pos) -> None:
        """右键影片行：打开影片所在目录（便于看内容辅助改判）。"""
        row = self.table.rowAt(pos.y())
        if not (0 <= row < len(self._rows)):
            return
        if row != self.table.currentRow():
            self.table.selectRow(row)      # 右键即选中，详情面板同步
        self._show_row_menu(self._rows[row],
                            self.table.viewport().mapToGlobal(pos))

    def _show_row_menu(self, u: dict, global_pos) -> None:
        menu = QMenu(self)
        act_open = menu.addAction("打开影片所在目录")
        self._handle_row_menu_choice(u, menu.exec(global_pos), act_open)

    def _handle_row_menu_choice(self, u: dict, chosen, act_open) -> None:
        """菜单选择落点（纯逻辑，可单测）：选中「打开影片所在目录」才开。"""
        if chosen is act_open:
            self._open_source_dir(u)

    def _open_source_dir(self, u: dict) -> None:
        """目录型单元=目录本身；散装文件单元=其父目录（所在目录语义）。
        单元已不在源处（如执行搬运后）不猜父级，直接提示。"""
        src = Path(u["src"])
        if u.get("kind") == "file":
            d = src.parent if src.is_file() else None
        elif src.is_dir():
            d = src
        else:
            d = None
        if d is None or not d.is_dir():
            self.toast(f"影片目录已不存在（可能已执行搬运）：{src}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def set_filter(self, key: str) -> None:
        self.vm.set_filter(key)
        for k, btn in self._chips.items():
            btn.setProperty("fchip", "on" if k == key else "off")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._rebuild_table()
        self._update_summary()

    def set_query(self, text: str) -> None:
        self.vm.set_query(text)
        self._rebuild_table()
        self._update_summary()

    def _select_ready(self) -> None:
        self.vm.select_visible_ready()
        self._sync_checkmarks()
        self._update_summary()

    def _clear_selection(self) -> None:
        self.vm.clear_selection()
        self._sync_checkmarks()
        self._update_summary()

    def _sync_checkmarks(self) -> None:
        """勾选状态以 vm 为真值源回写表格（筛选后行号与 id 不再一一对应）。"""
        self._populating = True
        for r in range(self.table.rowCount()):
            it = self.table.item(r, COL_CHECK)
            uid = it.data(Qt.UserRole)
            it.setCheckState(Qt.Checked if uid in self.vm.checked else Qt.Unchecked)
        self._populating = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._populating or item.column() != COL_CHECK:
            return
        uid = item.data(Qt.UserRole)
        if uid:
            self.vm.set_checked(uid, item.checkState() == Qt.Checked)
        self._update_summary()

    def _update_summary(self) -> None:
        checked = self.vm.checked_ids()
        self.summary.setText(
            f"已选 {len(checked):,} 部 · 合计 {human_size(self.vm.checked_bytes())}"
            f" · 列表 {len(self._rows):,} 行 / 共 {self.vm.stats()['total']:,} 部")
        self.btn_apply.setText(f"执行选中（{len(checked):,}）")

    def _show_detail(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        u = self._current_unit = self._rows[row]
        self.d_name.setText(u["label"])
        self.d_src.setText(u["src"])
        text, badge = level_badge(u)
        self._set_badge("level", text, badge)
        ctext, ctone = confidence_badge(u)
        self._set_badge("conf", ctext, ctone)
        self.d_fields["lib"].setText(self.vm.effective_target_lib(u))
        self.d_fields["dst"].setText(self.vm.effective_dst_dir(u))
        self.d_fields["files"].setText(str(u["file_count"]))
        self.d_fields["size"].setText(human_size(u["total_size"]))
        text, badge = status_badge(u)
        self._set_badge("status", text, badge)
        self.d_evidence.clear()
        for e in u.get("evidence") or ():
            self.d_evidence.addItem(QListWidgetItem(e))
        for note in u.get("notes") or ():
            self.d_evidence.addItem(QListWidgetItem("⚠ " + note))
        self.d_override.blockSignals(True)     # 重建下拉期间不触发改判
        self._fill_libs()
        self.d_override.setCurrentText(self.vm.overrides.get(u["id"]) or "（不改判）")
        self.d_override.blockSignals(False)

    def _set_badge(self, key: str, text: str, badge: str) -> None:
        w = self.d_fields[key]
        w.setText(text)
        w.setProperty("badge", badge)
        w.style().unpolish(w)
        w.style().polish(w)

    def _config_libs(self) -> list[str] | None:
        """全量配置库名；演示模式或配置不可读时返回 None（回退计划内集合）。

        逐次读盘而非缓存：config.toml 很小、触发频率为人工点击量级，
        缓存反而需引入 hash 失效逻辑（config_hash 本身也要解析配置）。
        """
        if self.state is None:
            return None
        try:
            return list(load_config(self.state.config_path).libraries)
        except Exception:      # noqa: BLE001  配置缺失/损坏/stub 无 config_path → 优雅降级
            return None

    def _fill_libs(self) -> None:
        libs = override_libs(self._rows, self._config_libs())
        if libs != self._libs:
            self._libs = libs
            self.d_override.clear()
            self.d_override.addItems(["（不改判）"] + libs + ["兜底库"])

    def _on_override_changed(self, text: str) -> None:
        u = self._current_unit
        if u is None:
            return
        self.vm.set_override(u["id"], None if text.startswith("（不改判）") else text)
        overridden = u["id"] in self.vm.overrides
        row = next((r for r, unit in enumerate(self._rows)
                    if unit["id"] == u["id"]), -1)
        if row >= 0:
            lib_item = self.table.item(row, COL_LIB)
            if lib_item:
                lib_item.setText(self.vm.effective_target_lib(u)
                                 + (" *" if overridden else ""))
                lib_item.setForeground(QColor(theme.ACC if overridden else theme.DIM))
        self.d_fields["lib"].setText(self.vm.effective_target_lib(u))


class BlockConfirmDialog(QDialog):
    """预检阻断确认：与网页版「二次确认越过阻断项」同语义。

    非 ackable（paths_missing）不可越过 → 直接禁用继续按钮；
    ackable 每项一个独立勾选，全部勾上才允许继续。
    """

    NON_ACKABLE = frozenset({"paths_missing", "disk_space", "staging_leftover"})

    def __init__(self, blocks: list[dict], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("执行前体检未通过")
        self.setModal(True)
        self.resize(560, 300)
        lay = QVBoxLayout(self)
        head = QLabel("以下阻断项需要你逐项确认后才能执行：")
        head.setProperty("sectionTitle", True)
        lay.addWidget(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        self._boxes: list[tuple[str, QCheckBox]] = []
        self._fatal = False
        for b in blocks:
            code = b.get("code", "")
            box = QCheckBox(b.get("message", code))
            detail = "；".join(str(d) for d in b.get("detail") or [])
            if detail:
                box.setToolTip(detail)
            if code in self.NON_ACKABLE:
                if code == "staging_leftover":
                    box.setText(f"【不可越过，可在 ④ 体检页一键清理】"
                                f"{b.get('message', code)}")
                else:
                    box.setText(f"【不可越过，请修正配置】{b.get('message', code)}")
                box.setEnabled(False)
                self._fatal = True
            else:
                self._boxes.append((code, box))
            bl.addWidget(box)
        bl.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("确认并执行")
        buttons.button(QDialogButtonBox.Ok).setProperty("role", "primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._ok = buttons.button(QDialogButtonBox.Ok)
        for _code, box in self._boxes:
            box.toggled.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        self._ok.setEnabled(bool(self._boxes) and not self._fatal
                            and all(box.isChecked() for _c, box in self._boxes))

    def acked_codes(self) -> set[str] | None:
        """模态弹出；接受 → 已确认的阻断码集合，取消 → None。"""
        if self.exec() != QDialog.Accepted:
            return None
        return {code for code, box in self._boxes if box.isChecked()}

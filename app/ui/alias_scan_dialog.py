"""别名扫描分析对话框（owner 2026-11-25 立项；同日迭代为批量分拣+统一保存）。

把 README 既定人工流程「计划页筛兜底→看未映射题材→手动补 alias」工具化：
展示未映射题材频次榜与影片名词频榜，人工勾选候选项、指定目标库后**先加入
待保存清单**（可跨强/弱、多库连续分拣），最后「统一保存」一次性追加进
别名表/弱别名表编辑框（只改文本不落盘，保存仍走「保存配置」全量校验）。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
)


class AliasScanDialog(QDialog):
    """candidates: app.core.alias_scan.scan_alias_candidates 的返回值；
    on_add(kind, lines)：kind ∈ {"strong","weak"}，把 `候选=库名` 行追加进
    对应编辑框（由宿主 ConfigTab 提供，只改文本不落盘）。"""

    def __init__(self, candidates: dict, lib_names: list[str],
                 on_add, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("别名扫描分析")
        self.resize(620, 560)
        self._on_add = on_add

        root = QVBoxLayout(self)
        root.setSpacing(8)
        n = candidates.get("unit_count") or 0
        strong = candidates.get("unit_strong_hit") or 0
        weak = candidates.get("unit_weak_only") or 0
        with_nfo = candidates.get("unit_with_nfo") or 0
        rest = n - strong - weak
        hint = QLabel(
            f"审计摘要（D-20261109-01 方案）：扫描 {n} 部，其中 {with_nfo} 部带题材标签。"
            f"题材规则强命中 {strong} 部、仅弱命中 {weak} 部、"
            f"未映射/无标签 {rest} 部——这部分是兜底库主力。"
            "库名自身天然命中（无需配别名）；流程：勾选候选→选目标库→加入待保存清单"
            "（可跨强/弱、多库连续分拣）→统一保存（追加进编辑框，点「保存配置」才落盘）。")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.tabs = QTabWidget()
        self.tbl_genres = self._make_table(candidates.get("genres") or [])
        self.tbl_tokens = self._make_table(candidates.get("tokens") or [])
        self.tabs.addTab(self.tbl_genres, "未映射题材榜")
        self.tabs.addTab(self.tbl_tokens, "影片名词榜")
        root.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel("目标库"))
        self.cmb_lib = QComboBox()
        for name in lib_names:
            if name:
                self.cmb_lib.addItem(name)
        row.addWidget(self.cmb_lib, 1)
        self.btn_stage_strong = QPushButton("加入清单（强别名）")
        self.btn_stage_weak = QPushButton("加入清单（弱别名）")
        self.btn_stage_strong.clicked.connect(lambda: self._stage("strong"))
        self.btn_stage_weak.clicked.connect(lambda: self._stage("weak"))
        row.addWidget(self.btn_stage_strong)
        row.addWidget(self.btn_stage_weak)
        root.addLayout(row)

        root.addWidget(QLabel("待保存清单（统一保存前可继续分拣）："))
        self.tbl_staged = QTableWidget(0, 3)
        self.tbl_staged.setHorizontalHeaderLabels(["候选", "目标库", "表别"])
        self.tbl_staged.setSelectionBehavior(QAbstractItemView.SelectRows)  # type: ignore[attr-defined]
        self.tbl_staged.setSelectionMode(QAbstractItemView.ExtendedSelection)  # type: ignore[attr-defined]
        self.tbl_staged.setEditTriggers(QAbstractItemView.NoEditTriggers)  # type: ignore[attr-defined]
        self.tbl_staged.verticalHeader().setVisible(False)
        self.tbl_staged.setWordWrap(False)
        hh = self.tbl_staged.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)  # type: ignore[attr-defined]
        root.addWidget(self.tbl_staged, 1)

        ops = QHBoxLayout()
        self.btn_unstage = QPushButton("移除选中清单项")
        self.btn_unstage.clicked.connect(self._unstage_selected)
        self.btn_save_all = QPushButton("✓ 统一保存")
        self.btn_save_all.clicked.connect(self._save_all)
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.close)
        ops.addWidget(self.btn_unstage)
        ops.addStretch(1)
        ops.addWidget(self.btn_save_all)
        ops.addWidget(self.btn_close)
        root.addLayout(ops)

    # ------------------------------------------------------------ 内部

    def _make_table(self, rows: list[tuple[str, int]]) -> QTableWidget:
        t = QTableWidget(0, 2)
        t.setHorizontalHeaderLabels(["候选", "影片数"])
        t.setSelectionBehavior(QAbstractItemView.SelectRows)  # type: ignore[attr-defined]
        t.setSelectionMode(QAbstractItemView.ExtendedSelection)  # type: ignore[attr-defined]
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)  # type: ignore[attr-defined]
        t.verticalHeader().setVisible(False)
        t.setWordWrap(False)
        t.horizontalHeader().setStretchLastSection(False)
        t.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)  # type: ignore[attr-defined]
        for text, count in rows:
            r = t.rowCount()
            t.insertRow(r)
            t.setItem(r, 0, QTableWidgetItem(text))
            item = QTableWidgetItem(str(count))
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)  # type: ignore[attr-defined]
            t.setItem(r, 1, item)
        return t

    def _current_table(self) -> QTableWidget:
        return (self.tbl_genres if self.tabs.currentWidget() is self.tbl_genres
                else self.tbl_tokens)

    def _selected_candidates(self, table: QTableWidget) -> list[str]:
        out = []
        for idx in sorted({i.row() for i in table.selectedIndexes()}):
            it = table.item(idx, 0)
            if it is not None and it.text():
                out.append(it.text())
        return out

    def _stage(self, kind: str) -> None:
        """勾选候选 → 待保存清单（不触发 on_add；同候选重复加入时跳过）。"""
        cands = self._selected_candidates(self._current_table())
        lib = self.cmb_lib.currentText()
        if not cands or not lib:
            return
        existing = set()
        for r in range(self.tbl_staged.rowCount()):
            it0 = self.tbl_staged.item(r, 0)
            it1 = self.tbl_staged.item(r, 1)
            if it0 is not None and it1 is not None:
                existing.add((it0.text(), it1.text()))
        for cand in cands:
            if (cand, lib) in existing:
                continue
            r = self.tbl_staged.rowCount()
            self.tbl_staged.insertRow(r)
            self.tbl_staged.setItem(r, 0, QTableWidgetItem(cand))
            self.tbl_staged.setItem(r, 1, QTableWidgetItem(lib))
            self.tbl_staged.setItem(
                r, 2, QTableWidgetItem("强" if kind == "strong" else "弱"))

    def _unstage_selected(self) -> None:
        for row in sorted({i.row() for i in self.tbl_staged.selectedIndexes()},
                          reverse=True):
            self.tbl_staged.removeRow(row)

    def _save_all(self) -> None:
        """清单按强/弱聚合，一次性回调宿主追加并关闭。"""
        strong: list[str] = []
        weak: list[str] = []
        for r in range(self.tbl_staged.rowCount()):
            c = self.tbl_staged.item(r, 0)
            lib = self.tbl_staged.item(r, 1)
            kind = self.tbl_staged.item(r, 2)
            if not (c and lib and kind):
                continue
            line = f"{c.text()}={lib.text()}"
            (strong if kind.text() == "强" else weak).append(line)
        if strong:
            self._on_add("strong", strong)
        if weak:
            self._on_add("weak", weak)
        self.accept()

    def closeEvent(self, ev) -> None:
        if self.tbl_staged.rowCount() > 0:
            box = QMessageBox(self)
            box.setWindowTitle("有待保存清单")
            box.setText(f"待保存清单还有 {self.tbl_staged.rowCount()} 条未统一保存，"
                        "直接关闭将丢弃这些分拣。确定关闭？")
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)  # type: ignore[attr-defined]
            if box.exec() != QMessageBox.Yes:  # type: ignore[attr-defined]
                ev.ignore()
                return
        ev.accept()

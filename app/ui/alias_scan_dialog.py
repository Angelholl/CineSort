"""别名扫描分析对话框（owner 2026-11-25 立项）。

把 README 既定人工流程「计划页筛兜底→看未映射题材→手动补 alias」工具化：
展示未映射题材频次榜与影片名词频榜，人工勾选候选项、逐条指定目标库后
追加进别名表/弱别名表编辑框（只改编辑框不落盘，保存仍走「保存配置」全量校验）。
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
        self.resize(560, 520)
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
            "库名自身天然命中（无需配别名）；勾选候选→选目标库→加入别名/弱别名表"
            "（只改编辑框，点「保存配置」才落盘）。题材榜=NFO 未映射写法；词榜=影片名切词。")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.tabs = QTabWidget()
        self.tbl_genres = self._make_table(candidates.get("genres") or [])
        self.tbl_tokens = self._make_table(candidates.get("tokens") or [])
        self.tabs.addTab(self.tbl_genres, "未映射题材榜")
        self.tabs.addTab(self.tbl_tokens, "影片名词榜")
        root.addWidget(self.tabs, 1)

        ops = QVBoxLayout()
        row = QHBoxLayout()
        row.addWidget(QLabel("目标库"))
        self.cmb_lib = QComboBox()
        for name in lib_names:
            if name:
                self.cmb_lib.addItem(name)
        row.addWidget(self.cmb_lib, 1)
        ops.addLayout(row)
        row2 = QHBoxLayout()
        self.btn_add_strong = QPushButton("加入别名表（强）")
        self.btn_add_weak = QPushButton("加入弱别名表（弱）")
        self.btn_add_strong.clicked.connect(lambda: self._add("strong"))
        self.btn_add_weak.clicked.connect(lambda: self._add("weak"))
        row2.addWidget(self.btn_add_strong)
        row2.addWidget(self.btn_add_weak)
        ops.addLayout(row2)
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

    def _selected_candidates(self, table: QTableWidget) -> list[str]:
        out = []
        for idx in sorted({i.row() for i in table.selectedIndexes()}):
            it = table.item(idx, 0)
            if it is not None and it.text():
                out.append(it.text())
        return out

    def _add(self, kind: str) -> None:
        table = (self.tbl_genres if self.tabs.currentWidget() is self.tbl_genres
                 else self.tbl_tokens)
        cands = self._selected_candidates(table)
        lib = self.cmb_lib.currentText()
        if not cands or not lib:
            return
        self._on_add(kind, [f"{c}={lib}" for c in cands])
        self.accept()

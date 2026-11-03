"""表格公共绘制层：列常量 + 状态徽章映射 + 自绘 delegate。

执行/体检页的表格与计划页共用此 delegate；徽章配色真值源是
theme.BADGE_COLORS。逐行 setCellWidget 在 5000 行规模会拖死表格
（每行一个控件），自绘 delegate 是 Qt 下既好看又扛规模的唯一解。
"""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QTableWidget

from . import theme

COL_CHECK, COL_TITLE, COL_LEVEL, COL_CONF, COL_LIB, COL_FILES, COL_SIZE, COL_STATUS = range(8)
BADGE_COLS = (COL_LEVEL, COL_STATUS, COL_CONF)

# planner 状态码 → theme 徽章键（现状为同名映射，显式写出以挡住计划外状态码）
STATUS_BADGES = {
    "ready": "ready",
    "conflict_name": "conflict_name",
    "already_placed": "already_placed",
    "incomplete_leftover": "incomplete_leftover",
    "multi_version": "multi_version",
    "applied": "applied",
}
_CONF_TONES = {"ok": theme.OK, "plot": theme.PLOT, "fb": theme.FB}


class CellDelegate(QStyledItemDelegate):
    """整表自绘：行背景 + 文本 + 圆角描边徽章 + 置信着色。"""

    def __init__(self, table: QTableWidget):
        super().__init__(table)
        self._table = table

    def paint(self, painter: QPainter, option, index) -> None:
        selected = bool(option.state & QStyle.State_Selected)
        bg = "#1f3a63" if selected else (theme.PANEL_ALT
                                         if index.row() % 2 else theme.PANEL)
        painter.fillRect(option.rect, QColor(bg))

        col = index.column()
        if col in (COL_LEVEL, COL_STATUS):
            self._paint_badge(painter, index, option)
            return
        if col == COL_CONF:
            self._paint_toned(painter, index, option,
                              _CONF_TONES, theme.DIM, align_right=True)
            return
        if col == COL_CHECK:
            super().paint(painter, option, index)
            return

        text = index.data(Qt.DisplayRole) or ""
        painter.save()
        painter.setPen(QColor(theme.DIM if col == COL_LIB else theme.FG))
        align = Qt.AlignRight | Qt.AlignVCenter if col in (COL_FILES, COL_SIZE) \
            else Qt.AlignLeft | Qt.AlignVCenter
        painter.drawText(option.rect.adjusted(10, 0, -10, -1), align, text)
        painter.restore()

    def _paint_badge(self, painter: QPainter, index, option) -> None:
        name = index.data(Qt.UserRole) or "dim"
        text = index.data(Qt.DisplayRole) or ""
        color = QColor(theme.BADGE_COLORS.get(name, theme.DIM))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        fm = painter.fontMetrics()
        h = min(option.rect.height() - 8, 21)
        w = min(fm.horizontalAdvance(text) + 16, option.rect.width() - 6)
        rect = QRect(option.rect.left() + 8,
                     option.rect.center().y() - h // 2, w, h)
        pen = QPen(color)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 5, 5)
        painter.drawText(rect, Qt.AlignCenter, text)
        painter.restore()

    def _paint_toned(self, painter: QPainter, index, option,
                     tones: dict[str, str], default: str, *,
                     align_right: bool) -> None:
        text = index.data(Qt.DisplayRole)
        if not text:
            return
        tone = index.data(Qt.UserRole) or "dim"
        painter.save()
        painter.setPen(QColor(tones.get(tone, default)))
        align = (Qt.AlignRight if align_right else Qt.AlignLeft) | Qt.AlignVCenter
        painter.drawText(option.rect.adjusted(4, 0, -6, -1), align, text)
        painter.restore()

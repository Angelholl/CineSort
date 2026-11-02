"""Phase-0 样式样机（D-20261102-01 样式门禁）：只做「分类计划」页，喂假数据。

目的不是功能，是在展开其余三页之前，让用户就"原生窗口长什么样"签字。
因此本文件不接 AppState、不读磁盘、不碰 core，全部数据由 fake_units() 生成。

    python -m app.ui.pilot                       # 开窗口看
    python -m app.ui.pilot --rows 5000 --screenshot Temp/pilot-100.png
    python -m app.ui.pilot --scale 1.5 --screenshot Temp/pilot-150.png
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme

# ------------------------------------------------------------------ 假数据

GENRES = ["科幻", "动作", "恐怖", "喜剧", "剧情", "动画", "纪录", "犯罪", "爱情"]
TITLE_A = ["太空", "深海", "午夜", "最后的", "第七", "黑色", "孤独", "狂野", "沉默的",
           "红色", "隐形", "二手", "长安", "夜航", "荒原", "边境", "雾港", "寒夜"]
TITLE_B = ["战争", "回声", "列车", "档案", "编年史", "委托", "遗产", "回声", "往事",
           "协议", "计划", "纪元", "回声", "迷城", "追缉", "名单"]
EN_TITLES = ["Silent Orbit", "The Last Ledger", "Nightfall Protocol", "Iron Meridian",
             "Paper Kingdoms", "Cold Static", "Quiet Harbor", "Nine Tails",
             "The Understudy", "Bone Cathedral", "Slow Thunder", "Glass Republic"]
EVIDENCE = {
    "rule": ["NFO <genre> 命中「{g}」→ 库「{lib}」", "别名表：Sci-Fi → 科幻",
             "genre_priority 首位候选"],
    "plot": ["摘要关键词「太空」×2 ×权重1.0 = 2.0 ≥ min_score 2.0",
             "摘要关键词「枪战」×1 ×权重1.0 = 1.0", "题材未映射，改用摘要预判"],
    "learned": ["自学习：题材「{g}」累计 3 票 → 库「{lib}」", "你于会话 7a3f9c21 人工改判（记 2 票）"],
    "fallback": ["题材全部未映射且摘要评分不足 → 兜底库", "兜底占比 18.4% 超过 warn 阈值 15%"],
}
STATUS_BADGE = {
    "ready": ("可执行", "ready"),
    "conflict_name": ("同名冲突", "conflict_name"),
    "already_placed": ("已在位", "already_placed"),
    "multi_version": ("多版本", "multi_version"),
    "incomplete_leftover": ("半成品残留", "incomplete_leftover"),
    "applied": ("已执行", "applied"),
}
LEVEL_BADGE = {
    "rule": ("规则", "rule"), "plot": ("摘要预判", "plot"),
    "learned": ("自学习", "learned"), "fallback": ("兜底", "fallback"),
}
LIBS = ["科幻", "动作", "恐怖", "喜剧", "剧情", "动画", "纪录", "犯罪"]


def fake_units(n: int, seed: int = 20261102) -> list[dict]:
    """生成 n 条贴近真实结构的计划单元（字段名对齐 planner 的 unit）。"""
    rnd = random.Random(seed)
    units: list[dict] = []
    used: set[str] = set()
    for _ in range(n):
        while True:
            if rnd.random() < 0.45:
                title = rnd.choice(TITLE_A) + rnd.choice(TITLE_B)
            else:
                title = rnd.choice(EN_TITLES)
            year = rnd.randint(1972, 2026)
            name = f"{title} ({year})"
            if name not in used:
                used.add(name)
                break
        level = rnd.choices(["rule", "plot", "learned", "fallback"],
                            weights=[62, 17, 12, 9])[0]
        status = rnd.choices(
            ["ready", "conflict_name", "already_placed", "multi_version",
             "incomplete_leftover", "applied"],
            weights=[80, 4, 5, 4, 2, 5])[0]
        if level == "fallback":
            lib, lib_root = "兜底库", r"D:\媒体库\未分类"
        else:
            lib = rnd.choice(LIBS)
            lib_root = rf"D:\媒体库\{lib}"
        genre = lib if lib != "兜底库" else rnd.choice(GENRES)
        files = rnd.randint(1, 14)
        size = rnd.randint(700, 42_000) * 1_048_576
        conf = {"rule": 1.0, "learned": 0.86, "plot": round(rnd.uniform(0.55, 0.8), 2),
                "fallback": 0.0}[level]
        units.append({
            "id": name, "label": name, "kind": "dir",
            "level": level, "status": status, "confidence": conf,
            "target_lib": lib, "target_root": lib_root,
            "src": rf"D:\待整理\{name}",
            "files": files, "total_size": size, "genres": (genre,),
            "evidence": [e.format(g=genre, lib=lib)
                         for e in rnd.sample(EVIDENCE[level],
                                             min(len(EVIDENCE[level]),
                                                 rnd.randint(1, len(EVIDENCE[level]))))],
        })
    return units


# ------------------------------------------------------------------ 自绘单元格

COL_CHECK, COL_TITLE, COL_LEVEL, COL_CONF, COL_LIB, COL_FILES, COL_SIZE, COL_STATUS = range(8)
BADGE_COLS = (COL_LEVEL, COL_STATUS)


class CellDelegate(QStyledItemDelegate):
    """整表自绘：行背景 + 文本 + 圆角徽章。

    徽章用 QSS 的 QLabel 逐行 setCellWidget 在 5000 行规模下会拖死表格
    （每行一个控件），自绘 delegate 是 Qt 下唯一既好看又扛得住规模的做法。
    """

    def paint(self, painter: QPainter, option, index) -> None:
        row = index.row()
        selected = bool(option.state & QStyle.State_Selected)
        bg = "#1f3a63" if selected else (theme.PANEL_ALT if row % 2 else theme.PANEL)
        painter.fillRect(option.rect, QColor(bg))

        col = index.column()
        if col in BADGE_COLS:
            self._paint_badge(painter, index, option)
            return
        if col == COL_CONF:
            self._paint_confidence(painter, index, option)
            return
        if col == COL_CHECK:
            super().paint(painter, option, index)
            return

        text = index.data(Qt.DisplayRole) or ""
        painter.setPen(QColor(theme.DIM if col == COL_LIB else theme.FG))
        align = Qt.AlignLeft | Qt.AlignVCenter
        if col in (COL_FILES, COL_SIZE):
            align = Qt.AlignRight | Qt.AlignVCenter
        painter.drawText(option.rect.adjusted(10, 0, -10, -1), align, text)

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

    def _paint_confidence(self, painter: QPainter, index, option) -> None:
        text = index.data(Qt.DisplayRole)
        if not text:
            return
        tone = index.data(Qt.UserRole) or "dim"
        color = {"ok": theme.OK, "plot": theme.PLOT, "fb": theme.FB}.get(tone, theme.DIM)
        painter.save()
        painter.setPen(QColor(color))
        painter.drawText(option.rect.adjusted(4, 0, -6, -1),
                         Qt.AlignRight | Qt.AlignVCenter, text)
        painter.restore()


# ------------------------------------------------------------------ 小组件

def make_card(value: str, label: str, tone: str) -> QFrame:
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
    return frame


def make_badge(name: str, text: str) -> QLabel:
    lab = QLabel(text)
    lab.setProperty("badge", name)
    # Maximum 宽度策略：让描边胶囊紧贴文字，而不是铺满整列——
    # 铺满时看起来像个只读的输入框，会被误读成可编辑字段。
    lab.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    return lab


def human_size(nbytes: int) -> str:
    """体积可读化。必须有 TB 档：整库规模轻松破 1000 GB，只到 GB
    会写出「83708.4 GB」这种没法读的数字。"""
    if nbytes <= 0:
        return "—"
    if nbytes >= 1024 ** 4:
        return f"{nbytes / 1024 ** 4:,.2f} TB"
    if nbytes >= 1024 ** 3:
        return f"{nbytes / 1024 ** 3:,.1f} GB"
    return f"{nbytes / 1024 ** 2:,.0f} MB"


# ------------------------------------------------------------------ 计划页

class PlanPilot(QWidget):
    def __init__(self, units: list[dict], parent: QWidget | None = None):
        super().__init__(parent)
        self.units = units
        self.filter = "all"
        self.query = ""
        self._rows: list[dict] = []
        self._populating = True
        self._chips: dict[str, QPushButton] = {}
        self._build()
        self._reload()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        # 统计卡片
        cards = QHBoxLayout()
        cards.setSpacing(10)
        st = self._stats()
        # 着色只给"有动作含义"的指标，其余走正文色：7 张卡 5 种颜色时，
        # 颜色就不再是信息了（Phase-0 目验 P1-2）
        for value, label, tone in (
            (f"{st['total']:,}", "影片单元", "dim"),
            (f"{st['ready']:,}", "可执行", "ok"),
            (f"{st['rule']:,}", "规则判定", "dim"),
            (f"{st['plot']:,}", "摘要预判", "plot"),
            (f"{st['learned']:,}", "自学习", "learned"),
            (f"{st['fallback']:,}", "兜底", "warn" if st["fallback_ratio"] > 0.15 else "dim"),
            (f"{st['blocked']:,}", "需人工处理", "bad"),
        ):
            cards.addWidget(make_card(value, label, tone))
        cards.addStretch(1)
        root.addLayout(cards)

        # 筛选 chips + 搜索 + 主操作
        bar = QHBoxLayout()
        bar.setSpacing(6)
        for key, text in (("all", "全部"), ("ready", "可执行"), ("rule", "规则"),
                          ("plot", "摘要预判"), ("learned", "自学习"), ("fallback", "兜底"),
                          ("blocked", "冲突/残留"), ("applied", "已执行")):
            btn = QPushButton(text)
            btn.setProperty("fchip", "on" if key == "all" else "off")
            btn.setCheckable(True)
            btn.setChecked(key == "all")
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

        # 表格 + 详情区
        self.splitter = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["✓", "影片", "判定", "置信", "目标库", "文件", "体积", "状态"])
        self.table.setItemDelegate(CellDelegate(self.table))
        self.table.setAlternatingRowColors(False)
        # 默认 showGrid=True 会在单元格之间留 1px 网格；delegate 逐格填色时
        # 选中行就露出列间竖缝，像一块块补丁（Phase-0 目验 P1-4）。
        self.table.setShowGrid(False)
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
        # 表头对齐跟随内容对齐：「影片」表头居中而内容左对齐会看着错位
        for col, align in ((COL_TITLE, Qt.AlignLeft), (COL_LEVEL, Qt.AlignLeft),
                           (COL_LIB, Qt.AlignLeft), (COL_STATUS, Qt.AlignLeft),
                           (COL_CONF, Qt.AlignRight), (COL_FILES, Qt.AlignRight),
                           (COL_SIZE, Qt.AlignRight)):
            head = self.table.horizontalHeaderItem(col)
            if head:
                head.setTextAlignment(align | Qt.AlignVCenter)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self.table.itemChanged.connect(self._on_item_changed)
        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self._detail_panel())
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([900, 340])
        root.addWidget(self.splitter, 1)

        # 底部汇总条
        bottom = QFrame()
        bottom.setProperty("bottombar", True)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(14, 8, 14, 8)
        bl.setSpacing(10)
        self.summary = QLabel("")
        self.summary.setProperty("mini", True)
        bl.addWidget(self.summary)
        bl.addStretch(1)
        for text, role in (("全选可执行", ""), ("清空选择", ""),
                           ("重新扫描", ""), ("执行选中", "primary")):
            btn = QPushButton(text)
            if role:
                btn.setProperty("role", role)
                self.btn_apply = btn      # 主按钮带计数，动作规模一眼可见
            bl.addWidget(btn)
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
        self.d_fields: dict[str, QWidget] = {}
        for row, (key, label) in enumerate((
                ("level", "判定"), ("conf", "置信度"), ("lib", "当前目标库"),
                ("files", "文件数"), ("size", "体积"), ("status", "状态"))):
            lab = QLabel(label)
            lab.setProperty("dim", True)
            grid.addWidget(lab, row, 0)
            if key in ("level", "status"):
                w = make_badge("dim", "—")
            else:
                w = QLabel("—")
                w.setWordWrap(True)
                w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.d_fields[key] = w
            # 必须显式给对齐：徽章的 Maximum 策略会让整列退化成"标签左/值右"
            # 的属性面板，标签与值之间拉出大空隙（Phase-0 复核 P2-1 副作用）。
            grid.addWidget(w, row, 1, Qt.AlignLeft | Qt.AlignVCenter)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        ev = QLabel("判定依据")
        ev.setProperty("sectionTitle", True)
        lay.addSpacing(6)
        lay.addWidget(ev)
        self.d_evidence = QListWidget()
        self.d_evidence.setMinimumHeight(96)
        lay.addWidget(self.d_evidence, 1)

        lay.addSpacing(4)
        ov = QLabel("改判目标库")
        ov.setProperty("sectionTitle", True)
        lay.addWidget(ov)
        self.d_override = QComboBox()
        self.d_override.addItems(["（不改判）"] + LIBS + ["兜底库"])
        lay.addWidget(self.d_override)
        row = QHBoxLayout()
        apply_btn = QPushButton("应用改判")
        apply_btn.setProperty("role", "primary")
        row.addWidget(apply_btn)
        confirm_btn = QPushButton("确认当前判定")
        row.addWidget(confirm_btn)
        lay.addLayout(row)
        return panel

    # --------------------------------------------------------- 数据与筛选

    def _stats(self) -> dict:
        out = {"total": len(self.units), "ready": 0, "rule": 0, "plot": 0,
               "learned": 0, "fallback": 0, "blocked": 0, "applied": 0}
        for u in self.units:
            out[u["level"]] = out.get(u["level"], 0) + 1
            if u["status"] == "ready":
                out["ready"] += 1
            elif u["status"] == "applied":
                out["applied"] += 1
            else:
                out["blocked"] += 1
        out["fallback_ratio"] = out["fallback"] / max(out["total"], 1)
        return out

    def _visible(self) -> list[dict]:
        out = []
        q = self.query.strip().lower()
        for u in self.units:
            if self.filter in ("ready", "applied") and u["status"] != self.filter:
                continue
            if self.filter == "blocked" and u["status"] in ("ready", "applied"):
                continue
            if self.filter in ("rule", "plot", "learned", "fallback") and u["level"] != self.filter:
                continue
            if q and q not in (u["label"] + u["target_lib"] + " ".join(u["genres"])).lower():
                continue
            out.append(u)
        return out

    def _reload(self) -> None:
        rows = self._visible()
        self._rows = rows
        self._populating = True
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(rows))
        for r, u in enumerate(rows):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            chk.setCheckState(Qt.Checked if u["status"] == "ready" else Qt.Unchecked)
            self.table.setItem(r, COL_CHECK, chk)

            it = QTableWidgetItem(u["label"])
            if u["status"] not in ("ready", "applied"):
                it.setForeground(QColor(theme.FB))
            self.table.setItem(r, COL_TITLE, it)

            lvl = LEVEL_BADGE[u["level"]]
            item = QTableWidgetItem(lvl[0])
            item.setData(Qt.UserRole, lvl[1])
            self.table.setItem(r, COL_LEVEL, item)

            conf = u["confidence"]
            tone = "ok" if conf >= 0.99 else ("plot" if conf > 0.5 else "fb")
            item = QTableWidgetItem("—" if conf <= 0 else f"{conf:.2f}")
            item.setData(Qt.UserRole, tone)
            self.table.setItem(r, COL_CONF, item)

            lib = QTableWidgetItem(u["target_lib"])
            lib.setForeground(QColor(theme.DIM))
            self.table.setItem(r, COL_LIB, lib)

            self.table.setItem(r, COL_FILES, QTableWidgetItem(str(u["files"])))
            self.table.setItem(r, COL_SIZE, QTableWidgetItem(human_size(u["total_size"])))

            text, badge = STATUS_BADGE[u["status"]]
            item = QTableWidgetItem(text)
            item.setData(Qt.UserRole, badge)
            self.table.setItem(r, COL_STATUS, item)
        self.table.setUpdatesEnabled(True)
        self._populating = False
        self._update_summary()

    def set_filter(self, key: str) -> None:
        self.filter = key
        for k, btn in self._chips.items():
            btn.setProperty("fchip", "on" if k == key else "off")
            btn.setChecked(k == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._reload()

    def set_query(self, text: str) -> None:
        self.query = text
        self._reload()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if getattr(self, "_populating", True) or item.column() != COL_CHECK:
            return
        self._update_summary()

    def _update_summary(self) -> None:
        checked = size = 0
        for r in range(self.table.rowCount()):
            it = self.table.item(r, COL_CHECK)
            if it and it.checkState() == Qt.Checked:
                checked += 1
                size += self._rows[r]["total_size"]
        self.summary.setText(
            f"已选 {checked:,} 部 · 合计 {human_size(size)}"
            f" · 列表 {self.table.rowCount():,} 行 / 共 {len(self.units):,} 部")
        self.btn_apply.setText(f"执行选中（{checked:,}）")

    def _show_detail(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        u = self._rows[row]
        self.d_name.setText(u["label"])
        self.d_src.setText(u["src"])
        lvl = LEVEL_BADGE[u["level"]]
        self.d_fields["level"].setText(lvl[0])
        self.d_fields["level"].setProperty("badge", lvl[1])
        self.d_fields["conf"].setText("—" if u["confidence"] <= 0
                                      else f"{u['confidence']:.2f}")
        self.d_fields["lib"].setText(u["target_lib"])
        self.d_fields["files"].setText(str(u["files"]))
        self.d_fields["size"].setText(human_size(u["total_size"]))
        text, badge = STATUS_BADGE[u["status"]]
        self.d_fields["status"].setText(text)
        self.d_fields["status"].setProperty("badge", badge)
        for key in ("level", "status"):
            w = self.d_fields[key]
            w.style().unpolish(w)
            w.style().polish(w)
        self.d_evidence.clear()
        for e in u["evidence"]:
            self.d_evidence.addItem(QListWidgetItem(e))


# ------------------------------------------------------------------ 主窗壳

class PilotWindow(QMainWindow):
    def __init__(self, units: list[dict]):
        super().__init__()
        self.setWindowTitle("CineSort 影片归类器")
        self.resize(1280, 800)

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(22, 12, 22, 12)
        hl.setSpacing(14)
        title = QLabel("CineSort 影片归类器")
        title.setObjectName("appTitle")
        hl.addWidget(title)
        pill = QLabel("空闲")
        pill.setProperty("pill", "idle")
        hl.addWidget(pill)
        hl.addStretch(1)
        cfg = QLabel(r"配置：C:\Users\me\AppData\Roaming\CineSort\config.toml")
        cfg.setObjectName("cfgPath")
        hl.addWidget(cfg)
        outer.addWidget(header)

        tabs = QTabWidget()
        self.plan_page = PlanPilot(units)
        tabs.addTab(self.plan_page, "① 分类计划")
        for name in ("② 执行 / 回滚", "③ 配置", "④ 体检"):
            ph = QWidget()
            pl = QVBoxLayout(ph)
            tip = QLabel(f"{name} —— Phase-0 样式门禁通过后再实现")
            tip.setProperty("dim", True)
            pl.addWidget(tip)
            tabs.addTab(ph, name)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(18, 10, 18, 0)
        wl.addWidget(tabs)
        outer.addWidget(wrap, 1)

        self.setCentralWidget(central)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cinesort-pilot",
                                     description="Phase-0 样式样机（假数据）")
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--scale", type=float, default=1.0,
                        help="模拟系统缩放：1.5 = 150%% DPI")
    parser.add_argument("--screenshot", default=None)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    args = parser.parse_args(argv)

    if args.scale != 1.0:
        os.environ["QT_SCALE_FACTOR"] = str(args.scale)

    # DPI：Qt 6 的默认已是 DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2，
    # 自己抢先调 SetProcessDpiAwarenessContext 会被系统拒绝并喷警告，
    # 故此处不做任何设置，只靠 150% 缩放截图验证观感。
    app = QApplication(sys.argv[:1])
    theme.apply_theme(app)

    win = PilotWindow(fake_units(args.rows))
    win.resize(args.width, args.height)
    win.show()

    if args.screenshot:
        out = Path(args.screenshot)
        out.parent.mkdir(parents=True, exist_ok=True)

        def shoot() -> None:
            # 回调内的异常会被 Qt 吞掉且不退出事件循环 —— 表现是静默挂死，
            # 所以这里必须自己兜住并显式退出。
            try:
                win.plan_page.table.setCurrentCell(3, 0)
                win.plan_page.table.scrollToItem(
                    win.plan_page.table.item(3, 0))
                app.processEvents()
                if not win.grab().save(str(out)):
                    raise RuntimeError(f"截图保存失败：{out}")
                print(f"screenshot -> {out}", flush=True)
                app.exit(0)
            except BaseException:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                app.exit(1)

        QTimer.singleShot(700, shoot)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

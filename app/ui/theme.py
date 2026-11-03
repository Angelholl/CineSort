"""设计令牌与样式：延续已验收的深色主题（原 index.html :root 变量），不另起一套。

样式令牌集中在此，QSS 由令牌生成；任何页面不得自带颜色字面量。
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# 与网页版 :root 变量一一对应（原生 QSS，无 HTML）
BG = "#0e1420"
PANEL = "#161e2d"
PANEL_ALT = "#202d42"        # 交替行：与 PANEL 的色差需肉眼可辨（斑马纹）
PANEL2 = "#1c2638"
LINE = "#28344a"
LINE_HI = "#3d4d6b"          # 未勾选复选框描边 / 滚动条滑块：比 LINE 亮一档才可发现
FG = "#dbe4f3"
DIM = "#8494ad"
ACC = "#4f8cff"
OK = "#3fbf7f"
WARN = "#e5a83b"
BAD = "#e05d5d"
PLOT = "#b07ef0"
FB = "#8a93a5"
LEARNED = "#3fc1c9"
LOG_BG = "#0a0f18"

FONT_FAMILY = '"Segoe UI","Microsoft YaHei",system-ui,sans-serif'
FONT_PT = 10                 # 网页版 14px ≈ 10.5pt，取 10pt
MONO_FAMILY = '"Cascadia Mono",Consolas,"Microsoft YaHei Mono",monospace'

# 判定/状态徽章配色：QLabel[badge="…"] 属性选择器驱动（等价网页版 .b-* 类）
# 「规则」占计划的大多数，故意用中性灰做底噪：绿色独占给「可执行」状态，
# 否则整列绿墙会把真正需要人看的红/橙异常行淹掉（Phase-0 目验 P1-1）。
BADGE_COLORS = {
    "rule": DIM, "ready": OK,
    "plot": PLOT,
    "learned": LEARNED,
    "fallback": FB,
    "conflict_name": WARN, "already_placed": WARN, "warn": WARN,
    "incomplete_leftover": BAD, "failed": BAD, "block": BAD,
    "multi_version": ACC, "applied": ACC, "info": ACC,
    "dim": DIM,
}


def build_qss() -> str:
    """由令牌生成 QSS。徽章部分用属性选择器，避免为每种颜色建一个类。"""
    badges = [(f'QLabel[badge] {{ border:1px solid {LINE}; border-radius:5px;'
               f' padding:1px 8px; color:{DIM}; font-size:9.5pt; }}')]
    for name, color in BADGE_COLORS.items():
        badges.append(f'QLabel[badge="{name}"] {{ color:{color}; border-color:{color};'
                      f' background:transparent; }}')

    return f"""
QWidget {{ color:{FG}; font-family:{FONT_FAMILY}; font-size:{FONT_PT}pt; }}
QMainWindow, QDialog {{ background:{BG}; }}

/* ---------- 顶栏 ---------- */
QWidget#header {{ background:{PANEL}; border-bottom:1px solid {LINE}; }}
QLabel#appTitle {{ font-size:13pt; font-weight:600; }}
QLabel#cfgPath {{ color:{DIM}; font-size:10pt; }}
QLabel[pill="idle"] {{ color:{DIM}; border:1px solid {LINE}; border-radius:99px;
                       padding:2px 12px; background:{PANEL2}; font-size:10pt; }}
QLabel[pill="run"]  {{ color:{ACC}; border-color:{ACC}; }}
QLabel[pill="done"] {{ color:{OK}; border-color:{OK}; }}
QLabel[pill="fail"] {{ color:{BAD}; border-color:{BAD}; }}

/* ---------- 统计卡片 ---------- */
QFrame[card] {{ background:{PANEL}; border:1px solid {LINE}; border-radius:10px; }}
QLabel[cardValue] {{ font-size:15pt; font-weight:600; }}
QLabel[cardLabel] {{ color:{DIM}; font-size:9pt; }}
QLabel[cardValue="ok"]      {{ color:{OK}; }}
QLabel[cardValue="plot"]    {{ color:{PLOT}; }}
QLabel[cardValue="learned"] {{ color:{LEARNED}; }}
QLabel[cardValue="warn"]    {{ color:{WARN}; }}
QLabel[cardValue="bad"]     {{ color:{BAD}; }}
QLabel[cardValue="acc"]     {{ color:{ACC}; }}
QLabel[cardValue="dim"]     {{ color:{FG}; }}

/* ---------- 筛选 chips ---------- */
QPushButton[fchip="off"] {{ background:transparent; border:1px solid {LINE};
  border-radius:99px; padding:3px 12px; color:{DIM}; font-size:10pt; }}
QPushButton[fchip="on"] {{ color:{FG}; border-color:{ACC}; background:transparent; }}
QPushButton[fchip]:hover {{ border-color:{ACC}; }}

/* ---------- 按钮 ---------- */
QPushButton {{ background:{PANEL2}; border:1px solid {LINE}; border-radius:8px;
  padding:6px 16px; color:{FG}; }}
QPushButton:hover {{ border-color:{ACC}; }}
QPushButton:pressed {{ background:{LINE}; }}
QPushButton:disabled {{ color:{DIM}; border-color:{PANEL2}; }}
QPushButton[role="primary"] {{ background:{ACC}; border-color:{ACC}; color:#ffffff; }}
QPushButton[role="primary"]:hover {{ background:#669bff; border-color:#669bff; }}
QPushButton[role="primary"]:disabled {{ background:{PANEL2}; color:{DIM};
  border-color:{LINE}; }}
QPushButton[role="danger"] {{ background:transparent; border-color:{BAD}; color:{BAD}; }}

/* ---------- 输入 ---------- */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QAbstractSpinBox {{
  background:{PANEL2}; border:1px solid {LINE}; border-radius:7px;
  padding:5px 10px; selection-background-color:{ACC}; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color:{ACC}; }}
/* 不覆盖 ::drop-down：Fusion 原生下拉箭头是矢量画的，一改就没了指示 */
QComboBox QAbstractItemView {{ background:{PANEL2}; border:1px solid {LINE};
  selection-background-color:{ACC}; selection-color:#ffffff; outline:none; }}

/* ---------- 表格 ---------- */
QTableWidget {{ background:{PANEL}; alternate-background-color:{PANEL_ALT};
  gridline-color:transparent; border:1px solid {LINE}; border-radius:10px;
  outline:none; }}
QTableWidget::item {{ padding:6px 10px; border-bottom:1px solid {LINE}; }}
QTableWidget::item:selected {{ background:#1f3a63; color:{FG}; }}
QHeaderView {{ background:{PANEL2}; }}
QHeaderView::section {{ background:{PANEL2}; color:{DIM}; border:none;
  border-bottom:1px solid {LINE}; padding:8px 10px; font-weight:500; }}
QTableCornerButton::section {{ background:{PANEL2}; border:none; }}
QTableView::indicator {{ width:15px; height:15px; }}

/* ---------- 详情区 ---------- */
QFrame[panel] {{ background:{PANEL}; border:1px solid {LINE}; border-radius:10px; }}
QLabel[dim] {{ color:{DIM}; }}
QLabel[sectionTitle] {{ font-size:11pt; font-weight:600; }}
QListWidget {{ background:{LOG_BG}; border:1px solid {LINE}; border-radius:8px;
  outline:none; }}
QListWidget::item {{ padding:3px 6px; border-bottom:1px solid {LINE}; }}

/* ---------- 日志 ---------- */
QPlainTextEdit[log] {{ background:{LOG_BG}; border:1px solid {LINE};
  border-radius:8px; font-family:{MONO_FAMILY}; font-size:9.5pt; }}

/* ---------- 进度条 ---------- */
QProgressBar {{ background:{PANEL2}; border:1px solid {LINE}; border-radius:99px;
  height:10px; text-align:center; color:{DIM}; font-size:9pt; }}
QProgressBar::chunk {{ background:{ACC}; border-radius:99px; }}
QProgressBar[tone="done"]::chunk {{ background:{OK}; }}
QProgressBar[tone="failed"]::chunk {{ background:{BAD}; }}

/* ---------- 标签页 ---------- */
QTabWidget::pane {{ border:1px solid {LINE}; border-radius:10px;
  background:{BG}; top:-1px; }}
QTabBar::tab {{ background:transparent; border:1px solid transparent;
  border-bottom:none; color:{DIM}; padding:8px 18px;
  border-top-left-radius:8px; border-top-right-radius:8px; }}
QTabBar::tab:selected {{ background:{BG}; color:{FG}; border-color:{LINE}; }}
QTabBar::tab:hover {{ color:{FG}; }}

/* ---------- 底部汇总条 ---------- */
QFrame[bottombar] {{ background:{PANEL}; border:1px solid {LINE}; border-radius:10px; }}
QLabel[mini] {{ color:{DIM}; font-size:9.5pt; }}

/* ---------- 滚动条（滑块必须肉眼可见，5000 行没有滚动条提示等于没有滚动条） ---------- */
QScrollBar:vertical {{ background:transparent; width:12px; margin:2px 2px 2px 0; }}
QScrollBar::handle:vertical {{ background:{LINE_HI}; border-radius:5px; min-height:32px; }}
QScrollBar::handle:vertical:hover {{ background:{DIM}; }}
QScrollBar:horizontal {{ background:transparent; height:12px; margin:0 2px 2px 0; }}
QScrollBar::handle:horizontal {{ background:{LINE_HI}; border-radius:5px; min-width:32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}

/* ---------- 分割条 ---------- */
QSplitter::handle {{ background:{LINE}; width:1px; }}
""" + "\n".join(badges)


def apply_theme(app: QApplication) -> None:
    """Fusion 风格 + 深色调色板 + 令牌化 QSS。

    必须先设 palette 再叠 QSS：复选框/下拉/滚动条这些原生控件靠 palette
    才会变深色，只写 QSS 会留一堆白底方块。
    """
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.WindowText, QColor(FG))
    pal.setColor(QPalette.Base, QColor(PANEL2))
    pal.setColor(QPalette.AlternateBase, QColor(PANEL_ALT))
    pal.setColor(QPalette.Text, QColor(FG))
    pal.setColor(QPalette.Button, QColor(PANEL2))
    pal.setColor(QPalette.ButtonText, QColor(FG))
    pal.setColor(QPalette.Highlight, QColor(ACC))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipBase, QColor(PANEL2))
    pal.setColor(QPalette.ToolTipText, QColor(FG))
    pal.setColor(QPalette.PlaceholderText, QColor(DIM))
    pal.setColor(QPalette.Link, QColor(ACC))
    # Fusion 用 Mid/Dark 画未勾选复选框的描边；留默认深色会让"可勾选"这个
    # 核心操作入口看不见（Phase-0 目验 P1-3）。
    pal.setColor(QPalette.Mid, QColor(LINE_HI))
    pal.setColor(QPalette.Dark, QColor(LINE_HI))
    pal.setColor(QPalette.Light, QColor(LINE))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(DIM))
    app.setPalette(pal)

    font = QFont("Segoe UI", FONT_PT)
    font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(font)
    app.setStyleSheet(build_qss())

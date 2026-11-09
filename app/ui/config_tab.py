"""③ 配置页：配置表单（校验保存）+ 自学习映射管理。

线程纪律（D-20261102-01）：本页不建线程、不建 QTimer——
- 慢 tick 喂 refresh()（唯一调 config_describe()/learned 读的地方）；
- 保存走 state.save_config（同步原子写，本地小文件，UI 线程可接受）；
- 快 tick 不喂本页（保存不进 JobManager）。

dirty 保护：慢 tick 回填仅在 force=True 或表单自上次渲染以来无用户修改时
覆盖，避免打字被 2s tick 刷掉。

state=None 即演示模式：表单禁用 + 自学习区显示降级文案。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.config import ConfigError
from ..state import AppState
from . import theme
from .config_viewmodel import describe_to_form, form_to_body, learned_rows

DEMO_TEXT = "演示模式（假数据），不连接真实配置"


class ConfigTab(QWidget):
    def __init__(self, state: AppState | None, toast=None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.toast = toast or (lambda msg: None)
        self._dirty = False            # 用户已编辑且未保存
        self._loading = False          # 程序化回填期间不置 dirty
        self._build()
        self.refresh()

    # ------------------------------------------------------------ 界面构建

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        # ---- 表单卡
        fc = QFrame()
        fc.setProperty("card", True)
        fl = QVBoxLayout(fc)
        fl.setContentsMargins(14, 12, 14, 12)
        fl.setSpacing(8)
        fl.addWidget(QLabel("基础配置"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.f_source_root = QLineEdit()
        self.f_fallback_path = QLineEdit()
        self.f_staging_dir = QLineEdit()
        self.f_strategy = QComboBox()
        self.f_strategy.addItems(["smart", "priority", "genre_only"])
        self.f_on_conflict = QComboBox()
        self.f_on_conflict.addItems(["skip", "rename"])

        self.f_warn = self._ratio_spin()
        self.f_block = self._ratio_spin()
        self.f_plot_enabled = QCheckBox("启用")
        self.f_plot_min_score = self._ratio_spin()
        self.f_plot_normalize = QCheckBox("清洗")
        self.f_learning_enabled = QCheckBox("启用")
        self.f_learning_min_votes = QSpinBox()
        self.f_learning_min_votes.setRange(1, 99)
        self.f_priority_text = QLineEdit()
        self.f_priority_text.setPlaceholderText("留空 = 无显式优先级")
        self.f_alias_text = QPlainTextEdit()
        self.f_alias_text.setFixedHeight(96)
        self.f_alias_text.setPlaceholderText("每行：别名=标准库名")

        rows = [
            ("源目录", self._path_row(self.f_source_root, "选择源目录",
                                      "btn_browse_source")),
            ("兜底库", self._path_row(self.f_fallback_path, "选择兜底库目录",
                                      "btn_browse_fallback")),
            ("暂存目录", self._path_row(self.f_staging_dir,
                                        "选择暂存目录（可留空）",
                                        "btn_browse_staging")),
            ("策略", self.f_strategy),
            ("冲突处理", self.f_on_conflict),
            ("兜底提醒阈值", self.f_warn),
            ("兜底阻断阈值", self.f_block),
            ("剧情简介", self._hbox(self.f_plot_enabled,
                                    self.f_plot_min_score,
                                    self.f_plot_normalize)),
            ("自学习", self._hbox(self.f_learning_enabled,
                                  self.f_learning_min_votes)),
            ("库优先级", self.f_priority_text),
            ("别名表", self.f_alias_text),
        ]
        for r, (label, w) in enumerate(rows):
            cap = QLabel(label)
            cap.setProperty("dim", True)
            grid.addWidget(cap, r, 0)
            grid.addWidget(w, r, 1)
        grid.setColumnStretch(1, 1)
        fl.addLayout(grid)

        # ---- 库表卡
        lc = QFrame()
        lc.setProperty("card", True)
        ll = QVBoxLayout(lc)
        ll.setContentsMargins(14, 12, 14, 12)
        ll.setSpacing(8)
        ll.addWidget(QLabel("库"))
        self.lib_table = QTableWidget(0, 4)
        self.lib_table.setHorizontalHeaderLabels(["库名", "目录", "关键词", "加权词"])
        self.lib_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.lib_table.verticalHeader().setVisible(False)
        self.lib_table.setWordWrap(False)
        self.lib_table.horizontalHeader().setStretchLastSection(True)
        self.lib_table.itemChanged.connect(self._mark_dirty)
        ll.addWidget(self.lib_table, 1)
        lib_btns = QHBoxLayout()
        self.btn_add = QPushButton("＋ 添加库")
        self.btn_add.clicked.connect(self._on_add_library_clicked)
        btn_del = QPushButton("－ 删除选中库")
        btn_del.clicked.connect(self._del_library_row)
        lib_btns.addWidget(self.btn_add)
        lib_btns.addWidget(btn_del)
        lib_btns.addStretch(1)
        ll.addLayout(lib_btns)

        # ---- 操作行
        ops = QHBoxLayout()
        ops.setSpacing(10)
        self.btn_save = QPushButton("保存配置")
        self.btn_save.setProperty("role", "primary")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_reload = QPushButton("重载")
        self.btn_reload.clicked.connect(lambda: self.refresh(force=True))
        self.cfg_msg = QLabel("")
        self.cfg_msg.setWordWrap(True)
        self.cfg_msg.hide()
        ops.addWidget(self.btn_save)
        ops.addWidget(self.btn_reload)
        ops.addWidget(self.cfg_msg, 1)
        ll.addLayout(ops)

        # ---- 自学习卡
        sc = QFrame()
        sc.setProperty("card", True)
        sl = QVBoxLayout(sc)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(8)
        sl.addWidget(QLabel("自学习映射（达阈值自动生效）"))
        self.learned_hint = QLabel("")
        self.learned_hint.setProperty("dim", True)
        self.learned_hint.setAlignment(Qt.AlignCenter)
        self.learned_hint.hide()
        sl.addWidget(self.learned_hint)
        self.learned_table = QTableWidget(0, 6)
        self.learned_table.setHorizontalHeaderLabels(
            ["题材", "归入库", "票数", "其中人工", "最近", ""])
        self.learned_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.learned_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.learned_table.verticalHeader().setVisible(False)
        self.learned_table.setWordWrap(False)
        self.learned_table.horizontalHeader().setStretchLastSection(True)
        sl.addWidget(self.learned_table, 1)

        root.addWidget(fc, 3)
        root.addWidget(lc, 2)
        root.addWidget(sc, 2)

        # ---- dirty 标记：所有控件修改即置位（程序化回填除外）
        for w in (self.f_source_root, self.f_fallback_path, self.f_staging_dir,
                  self.f_priority_text, self.f_alias_text):
            w.textChanged.connect(self._mark_dirty)
        for w in (self.f_strategy, self.f_on_conflict):
            w.currentIndexChanged.connect(self._mark_dirty)
        for w in (self.f_warn, self.f_block, self.f_plot_min_score):
            w.valueChanged.connect(self._mark_dirty)
        for w in (self.f_plot_enabled, self.f_plot_normalize,
                  self.f_learning_enabled):
            w.toggled.connect(self._mark_dirty)
        self.f_learning_min_votes.valueChanged.connect(self._mark_dirty)

        if self.state is None:
            self._set_form_enabled(False)
            self.learned_hint.setText(DEMO_TEXT)
            self.learned_hint.show()
            self.learned_table.setEnabled(False)

    # ------------------------------------------------------------ 小工具

    def _hbox(self, *widgets) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        for x in widgets:
            h.addWidget(x)
        h.addStretch(1)
        return w

    def _path_row(self, edit: QLineEdit, caption: str, attr: str) -> QWidget:
        """路径行：输入框(伸展) + 「浏览…」按钮；按钮以 attr 名存为实例属性。"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(edit, 1)
        btn = QPushButton("浏览…")
        btn.clicked.connect(lambda _=False, e=edit, c=caption: self._browse_dir(e, c))
        setattr(self, attr, btn)
        h.addWidget(btn)
        return w

    def _browse_dir(self, edit: QLineEdit, caption: str) -> None:
        chosen = QFileDialog.getExistingDirectory(self, caption, edit.text().strip())
        if chosen:
            edit.setText(chosen)   # textChanged → _mark_dirty 自动生效

    def _ratio_spin(self) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(0.0, 1.0)
        s.setSingleStep(0.05)
        s.setDecimals(2)
        return s

    def _mark_dirty(self, *_args) -> None:
        if not self._loading:
            self._dirty = True

    def _set_form_enabled(self, on: bool) -> None:
        for w in (self.f_source_root, self.f_fallback_path, self.f_staging_dir,
                  self.f_strategy, self.f_on_conflict, self.f_warn,
                  self.f_block, self.f_plot_enabled, self.f_plot_min_score,
                  self.f_plot_normalize, self.f_learning_enabled,
                  self.f_learning_min_votes, self.f_priority_text,
                  self.f_alias_text, self.lib_table, self.btn_save,
                  self.btn_reload, self.btn_browse_source,
                  self.btn_browse_fallback, self.btn_browse_staging):
            w.setEnabled(on)

    # ------------------------------------------------------------ 慢 tick

    def refresh(self, force: bool = False) -> None:
        """慢 tick 唯一入口：describe 回填（dirty 保护）+ 自学习清单。"""
        if self.state is None:
            return
        desc, err = self.state.config_describe()
        if err is not None:
            self.cfg_msg.setText(
                f"当前配置无效，展示的是兜底值，保存前请先修正：\n{err}")
            self.cfg_msg.setStyleSheet(f"color:{theme.BAD};")
            self.cfg_msg.show()
        else:
            self.cfg_msg.hide()   # 配置已恢复有效（如外部修正），横幅随之消失
        if force or not self._dirty:
            self._fill_form(desc or {})
        learned = (self.state.state_snapshot() or {}).get("learned") or []
        self._render_learned(learned)

    def _fill_form(self, desc: dict) -> None:
        form = describe_to_form(desc)
        self._loading = True
        try:
            self.f_source_root.setText(form["source_root"])
            self.f_fallback_path.setText(form["fallback_path"])
            self.f_staging_dir.setText(form["staging_dir"])
            self.f_strategy.setCurrentText(form["strategy"])
            self.f_on_conflict.setCurrentText(form["on_conflict"])
            self.f_warn.setValue(form["warn"])
            self.f_block.setValue(form["block"])
            self.f_plot_enabled.setChecked(form["plot_enabled"])
            self.f_plot_min_score.setValue(form["plot_min_score"])
            self.f_plot_normalize.setChecked(form["plot_normalize"])
            self.f_learning_enabled.setChecked(form["learning_enabled"])
            self.f_learning_min_votes.setValue(form["learning_min_votes"])
            self.f_priority_text.setText(form["priority_text"])
            self.f_alias_text.setPlainText(form["alias_text"])
            self.lib_table.setRowCount(0)
            for row in form["library_rows"]:
                self._add_library_row(row)
        finally:
            self._loading = False
        self._dirty = False

    def _add_library_row(self, values=None) -> None:
        r = self.lib_table.rowCount()
        self.lib_table.insertRow(r)
        vals = list(values or ["", "", "", ""])
        for c, text in enumerate(vals):
            self.lib_table.setItem(r, c, QTableWidgetItem(str(text)))

    def _on_add_library_clicked(self) -> None:
        """添加库 = 浏览选目录；取消则不插行（语义变化：旧版总是插空行）。"""
        chosen = QFileDialog.getExistingDirectory(self, "选择库目录", "")
        if not chosen:
            return
        self._add_library_row([Path(chosen).name, str(chosen), "", ""])

    def _del_library_row(self) -> None:
        row = self.lib_table.selectionModel().currentRow()
        if row >= 0:
            self.lib_table.removeRow(row)
            self._mark_dirty()

    # ------------------------------------------------------------ 保存

    def _collect_form(self) -> tuple[dict, list[list[str]]]:
        rows = []
        for r in range(self.lib_table.rowCount()):
            rows.append([
                (self.lib_table.item(r, c).text()
                 if self.lib_table.item(r, c) else "")
                for c in range(4)])
        form = {
            "source_root": self.f_source_root.text(),
            "fallback_path": self.f_fallback_path.text(),
            "staging_dir": self.f_staging_dir.text(),
            "strategy": self.f_strategy.currentText(),
            "on_conflict": self.f_on_conflict.currentText(),
            "warn": self.f_warn.value(),
            "block": self.f_block.value(),
            "plot_enabled": self.f_plot_enabled.isChecked(),
            "plot_min_score": self.f_plot_min_score.value(),
            "plot_normalize": self.f_plot_normalize.isChecked(),
            "learning_enabled": self.f_learning_enabled.isChecked(),
            "learning_min_votes": self.f_learning_min_votes.value(),
            "priority_text": self.f_priority_text.text(),
            "alias_text": self.f_alias_text.toPlainText(),
        }
        return form, rows

    def _on_save(self) -> None:
        if self.state is None:
            self.toast(DEMO_TEXT)
            return
        form, rows = self._collect_form()
        body = form_to_body(form, rows)
        try:
            self.state.save_config(body)
        except ConfigError as exc:
            self.cfg_msg.setText(f"校验失败：\n{exc}")
            self.cfg_msg.setStyleSheet(f"color:{theme.BAD};")
            self.cfg_msg.show()
            return
        self.cfg_msg.hide()
        self.toast("配置已保存并通过校验，请重新扫描生成新计划")
        self.refresh(force=True)

    # ------------------------------------------------------------ 自学习

    def _render_learned(self, items: list[dict]) -> None:
        rows = learned_rows(items)
        self.learned_table.setRowCount(0)
        if not rows:
            self.learned_hint.setText("暂无自学习记录")
            self.learned_hint.show()
            return
        self.learned_hint.hide()
        for r, row in enumerate(rows):
            genre, lib, votes, manual, last, key, keylib = row
            self.learned_table.insertRow(r)
            for c, text in enumerate((genre, lib, votes, manual, last)):
                it = QTableWidgetItem(str(text))
                if c == 4:
                    it.setForeground(QColor(theme.DIM))
                self.learned_table.setItem(r, c, it)
            btn = QPushButton("忘记")
            btn.setProperty("role", "danger")
            btn.clicked.connect(
                lambda _=False, k=key, l=keylib: self._on_forget(k, l))
            self.learned_table.setCellWidget(r, 5, btn)

    def _on_forget(self, key, lib) -> None:
        if self.state is None:
            self.toast(DEMO_TEXT)
            return
        items = self.state.learned_forget(key, lib)
        self.toast("已忘记该映射")
        self._render_learned(items)

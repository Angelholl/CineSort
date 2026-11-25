"""别名扫描分析对话框与配置页接线测试（owner 2026-11-25 立项）。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.ui.alias_scan_dialog import AliasScanDialog
from app.ui.config_tab import ConfigTab


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


CANDIDATES = {"unit_count": 3,
              "genres": [("西部", 2), ("Western", 1)],
              "tokens": [("重复词", 3), ("外卖", 1)]}


def test_dialog_lists_candidates_sorted(qapp):
    dlg = AliasScanDialog(CANDIDATES, ["科幻", "动作"], lambda k, l: None)
    assert dlg.tbl_genres.rowCount() == 2
    assert dlg.tbl_tokens.rowCount() == 2
    assert dlg.tbl_genres.item(0, 0).text() == "西部"      # 次数降序
    assert dlg.tbl_genres.item(0, 1).text() == "2"
    assert dlg.tbl_tokens.item(0, 0).text() == "重复词"
    dlg.deleteLater()


def test_dialog_add_strong_emits_lines(qapp):
    added: list[tuple[str, list[str]]] = []
    dlg = AliasScanDialog(CANDIDATES, ["科幻", "动作"],
                          lambda kind, lines: added.append((kind, lines)))
    dlg.tbl_genres.selectAll()
    dlg.cmb_lib.setCurrentText("动作")
    dlg._add("strong")
    assert added == [("strong", ["西部=动作", "Western=动作"])]
    dlg.deleteLater()


def test_dialog_add_weak_and_empty_selection_noop(qapp):
    added: list[tuple[str, list[str]]] = []
    dlg = AliasScanDialog(CANDIDATES, ["科幻"],
                          lambda kind, lines: added.append((kind, lines)))
    dlg._add("weak")                                        # 无勾选：不加
    assert added == []
    dlg.tbl_tokens.selectRow(0)
    dlg.tabs.setCurrentWidget(dlg.tbl_tokens)               # 切到词榜页再操作
    dlg._add("weak")
    assert added == [("weak", ["重复词=科幻"])]
    dlg.deleteLater()


class _StubState:
    """与 test_config_tab.StubState 同形的 duck-typing 桩（零磁盘）。"""

    def __init__(self, desc=None, err=None, learned=None):
        self.desc, self.err, self._learned = desc, err, list(learned or [])
        self.saved, self.forgotten = [], []

    def config_describe(self):
        return self.desc, self.err

    def save_config(self, data):
        self.saved.append(data)
        return self.desc

    def state_snapshot(self):
        return {"learned": list(self._learned)}

    def learned_forget(self, key, lib):
        self.forgotten.append((key, lib))
        return []


def _full_describe() -> dict:
    return {
        "source_root": "D:/media", "fallback_path": "D:/_fallback",
        "staging_dir": "D:/_staging", "strategy": "smart",
        "on_conflict": "rename", "warn_fallback_ratio": 0.15,
        "block_fallback_ratio": 0.3,
        "plot": {"enabled": True, "min_score": 0.75, "normalize": True},
        "learning": {"enabled": True, "min_votes": 3},
        "genre_priority": ["科幻", "动作"],
        "genre_aliases": {"sci-fi": "科幻"},
        "libraries": [
            {"name": "电影", "path": "D:/movies", "keywords": [],
             "keywords_weighted": {}},
            {"name": "剧集", "path": "D:/tv", "keywords": [],
             "keywords_weighted": {}},
        ],
    }


def test_append_alias_candidates_to_textareas(qapp):
    """接线钉：宿主回调只追加进编辑框并置脏/提示，不触发保存落盘。"""
    toasts: list[str] = []
    tab = ConfigTab(_StubState(_full_describe()), toast=toasts.append)
    tab._append_alias_candidates("strong", ["西部=电影", "Western=电影"])
    text = tab.f_alias_text.toPlainText()
    assert "西部=电影" in text and "Western=电影" in text
    assert tab._dirty is True
    assert tab.state.saved == []                            # 未落盘
    assert any("2 条" in m and "别名表" in m for m in toasts)
    # 整行去重语义：同键不同库=不同行，允许追加（同键后行覆盖前行，分类器语义）
    toasts.clear()
    tab._append_alias_candidates("strong", ["西部=剧集"])
    assert tab.f_alias_text.toPlainText().count("西部=") == 2
    assert any("1 条" in m for m in toasts)
    # 完全同行：已在表中，不追加
    toasts.clear()
    tab._append_alias_candidates("strong", ["西部=电影"])
    assert tab.f_alias_text.toPlainText().count("西部=电影") == 1
    assert any("已在表中" in m for m in toasts)
    # 弱表通道
    tab._append_alias_candidates("weak", ["外卖=剧集"])
    assert "外卖=剧集" in tab.f_weak_alias_text.toPlainText()
    tab.deleteLater()


def test_config_tab_alias_scan_button_exists_and_demo_disabled(qapp):
    tab_on = ConfigTab(_StubState(_full_describe()), toast=lambda m: None)
    assert tab_on.btn_alias_scan.isEnabled() is True
    tab_on.deleteLater()
    tab_demo = ConfigTab(None, toast=lambda m: None)
    assert tab_demo.btn_alias_scan.isEnabled() is False
    tab_demo.deleteLater()

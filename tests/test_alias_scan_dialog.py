"""别名扫描分析对话框与配置页接线测试（owner 2026-11-25 立项）。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

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


def test_stage_then_save_all_aggregates_by_kind(qapp):
    """批量分拣钉（owner 2026-11-25：单个保存过繁琐）：加入清单不触发 on_add；
    统一保存按强/弱各一次性聚合回调。"""
    added: list[tuple[str, list[str]]] = []
    dlg = AliasScanDialog(CANDIDATES, ["科幻", "动作"],
                          lambda kind, lines: added.append((kind, lines)))
    # 第一批：题材榜勾 1 行 → 强别名 → 清单
    dlg.tbl_genres.selectRow(0)
    dlg.cmb_lib.setCurrentText("动作")
    dlg._stage("strong")
    assert added == []                                     # 分拣阶段不落编辑框
    assert dlg.tbl_staged.rowCount() == 1
    # 第二批：词榜勾 1 行 → 弱别名 → 清单（跨榜连续分拣，换目标库）
    dlg.cmb_lib.setCurrentText("科幻")
    dlg.tbl_tokens.selectRow(0)
    dlg.tabs.setCurrentWidget(dlg.tbl_tokens)
    dlg._stage("weak")
    assert dlg.tbl_staged.rowCount() == 2
    assert dlg.tbl_staged.item(1, 2).text() == "弱"
    # 统一保存：强/弱各一次聚合回调
    dlg._save_all()
    assert added == [("strong", ["西部=动作"]), ("weak", ["重复词=科幻"])]
    dlg.deleteLater()


def test_stage_multi_rows_and_dedupe(qapp):
    added: list[tuple[str, list[str]]] = []
    dlg = AliasScanDialog(CANDIDATES, ["科幻"],
                          lambda kind, lines: added.append((kind, lines)))
    dlg.tbl_genres.selectAll()
    dlg.cmb_lib.setCurrentText("科幻")
    dlg._stage("strong")                                   # 两行一次入清单
    assert dlg.tbl_staged.rowCount() == 2
    dlg.tbl_genres.selectRow(0)
    dlg._stage("strong")                                   # 同候选同库重复加入跳过
    assert dlg.tbl_staged.rowCount() == 2
    dlg._save_all()
    assert added == [("strong", ["西部=科幻", "Western=科幻"])]
    dlg.deleteLater()


def test_unstage_and_empty_save_noop(qapp):
    added: list[tuple[str, list[str]]] = []
    dlg = AliasScanDialog(CANDIDATES, ["科幻"],
                          lambda kind, lines: added.append((kind, lines)))
    dlg.tbl_genres.selectRow(0)
    dlg._stage("strong")
    dlg.tbl_staged.selectRow(0)
    dlg._unstage_selected()
    assert dlg.tbl_staged.rowCount() == 0
    dlg._save_all()                                        # 空清单：无回调
    assert added == []
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


def test_effective_alias_keys_config_and_pending_lines(qapp, tmp_path):
    """已覆盖键 = 已落盘配置别名 ∪ 两编辑框待保存行（normalize 归一）。"""
    from conftest import build_env

    from app.core.config import load_config
    cfg_path = build_env(tmp_path, overrides={
        "genre_aliases": {"sci-fi": "科幻"}, "genre_priority": []})
    cfg = load_config(cfg_path)
    tab = ConfigTab(_StubState(_full_describe()), toast=lambda m: None)
    keys = tab._effective_alias_keys(cfg)
    assert "sci-fi" in keys                                 # 已落盘强别名
    tab.f_weak_alias_text.setPlainText("护士=剧集")
    tab.f_alias_text.setPlainText("西部=电影")
    keys = tab._effective_alias_keys(cfg)
    assert "西部" in keys and "护士" in keys                # 编辑框待保存行
    assert "" not in keys                                   # 空键剔除
    tab.deleteLater()


def test_dialog_promotions_empty_hint(qapp):
    """D 空态钉：promotions=[] → 第三页空态文案在场。"""
    dlg = AliasScanDialog({**CANDIDATES, "promotions": []},
                          ["科幻", "动作"], lambda k, l: None)
    assert dlg.tabs.count() == 3
    assert dlg.tabs.tabText(2) == "提升建议"
    texts = [w.text() for w in dlg.findChildren(QLabel)]
    assert any("当前无满足条件的提升建议" in t for t in texts)
    dlg.deleteLater()


def test_dialog_promotion_stages_into_list(qapp):
    """提升按钮接线钉：选中提升建议行 → 清单（表别=强）→ 统一保存回调。"""
    promos = [
        {"genre": "古装", "key": "古装", "lib": "科幻", "votes": 3, "manual": 1},
        {"genre": "西部", "key": "西部", "lib": "动作", "votes": 2, "manual": 0},
    ]
    added: list[tuple[str, list[str]]] = []
    dlg = AliasScanDialog({**CANDIDATES, "promotions": promos},
                          ["科幻", "动作"],
                          lambda kind, lines: added.append((kind, lines)))
    dlg.tabs.setCurrentIndex(2)
    dlg.tbl_promotions.selectAll()
    dlg.btn_promote_strong.click()
    staged = [(dlg.tbl_staged.item(r, 0).text(), dlg.tbl_staged.item(r, 1).text(),
               dlg.tbl_staged.item(r, 2).text())
              for r in range(dlg.tbl_staged.rowCount())]
    assert staged == [("古装", "科幻", "强"), ("西部", "动作", "强")]
    dlg._save_all()
    assert added == [("strong", ["古装=科幻", "西部=动作"])]
    dlg.deleteLater()

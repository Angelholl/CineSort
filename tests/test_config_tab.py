"""「③ 配置」页视图逻辑单测（offscreen，零磁盘、零线程）：克隆 test_exec_tab.py 范式。

覆盖：describe↔form 往返、别名/加权词/优先级解析、数值归一、无名库行跳过、
演示模式降级、describe 回填、无效配置横幅、保存成功/校验失败、自学习清单与
忘记、dirty 表单不被慢 tick 覆盖、主窗接线静态断言。
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.core.config import ConfigError
from app.ui.config_tab import ConfigTab
from app.ui.config_viewmodel import (
    describe_to_form,
    form_to_body,
    learned_rows,
)

# ---------------------------------------------------------------- 纯逻辑段

def full_describe() -> dict:
    return {
        "source_root": "D:/media",
        "fallback_path": "D:/_fallback",
        "staging_dir": "D:/_staging",
        "strategy": "smart",
        "on_conflict": "rename",
        "warn_fallback_ratio": 0.15,
        "block_fallback_ratio": 0.3,
        "plot": {"enabled": True, "min_score": 0.75, "normalize": True},
        "learning": {"enabled": True, "min_votes": 3},
        "genre_priority": ["科幻", "动作"],
        "genre_aliases": {"sci-fi": "科幻", "SF": "科幻"},
        "libraries": [
            {"name": "电影", "path": "D:/movies", "keywords": ["movie", "film"],
             "keywords_weighted": {"太空": 2.0, "机甲": 1.5}},
            {"name": "剧集", "path": "D:/tv", "keywords": [],
             "keywords_weighted": {}},
        ],
    }


def test_describe_to_form_roundtrip():
    desc = full_describe()
    form = describe_to_form(desc)
    body = form_to_body(
        form,
        form["library_rows"],
    )
    assert body["source_root"] == desc["source_root"]
    assert body["strategy"] == desc["strategy"]
    assert body["on_conflict"] == desc["on_conflict"]
    assert body["warn_fallback_ratio"] == pytest.approx(0.15)
    assert body["block_fallback_ratio"] == pytest.approx(0.3)
    assert body["plot"] == desc["plot"]
    assert body["learning"] == desc["learning"]
    assert body["genre_priority"] == desc["genre_priority"]     # 保序
    assert sorted(body["genre_aliases"]) == sorted(desc["genre_aliases"])
    assert body["staging_dir"] == desc["staging_dir"]
    assert len(body["libraries"]) == 2
    lib0 = body["libraries"][0]
    assert lib0["name"] == "电影"
    assert lib0["keywords"] == ["movie", "film"]
    assert lib0["keywords_weighted"] == {"太空": 2.0, "机甲": 1.5}
    assert body["libraries"][1]["keywords_weighted"] == {}


def test_alias_parse_skips_bad_lines():
    form = {"alias_text": "A=B\n\n无等号\n=X\nY=\n", "priority_text": ""}
    body = form_to_body(form, [])
    assert body["genre_aliases"] == {"A": "B"}


def test_weighted_parse():
    form = {}
    rows = [["L", "P", "", "太空=2, 机甲=1.5, 坏行"]]
    body = form_to_body(form, rows)
    assert body["libraries"][0]["keywords_weighted"] == {"太空": 2.0, "机甲": 1.5}


def test_priority_split():
    body = form_to_body({"priority_text": "科幻、动作，奇幻"}, [])
    assert body["genre_priority"] == ["科幻", "动作", "奇幻"]
    assert form_to_body({"priority_text": ""}, [])["genre_priority"] == []


def test_numeric_normalization():
    body = form_to_body({"plot_min_score": "0.75", "learning_min_votes": "3",
                         "warn": 0.2, "block": 0.45}, [])
    assert body["plot"]["min_score"] == 0.75
    assert body["learning"]["min_votes"] == 3
    assert isinstance(body["learning"]["min_votes"], int)
    assert isinstance(body["warn_fallback_ratio"], float)
    assert isinstance(body["block_fallback_ratio"], float)


def test_library_rows_skip_nameless():
    body = form_to_body({}, [["", "P", "", ""], ["OK", "P", "", ""]])
    assert [lib["name"] for lib in body["libraries"]] == ["OK"]


def test_learned_rows_shape():
    rows = learned_rows([{"key": "k1", "genre": "科幻", "lib": "电影",
                          "votes": 5, "manual": 1, "last": "2026-11-01"}])
    assert rows == [("科幻", "电影", 5, 1, "2026-11-01", "k1", "电影")]


# ---------------------------------------------------------------- widget 段

class StubState:
    """duck-typing：只实现 ConfigTab 会调用的方法，不 import AppState 以免碰盘。"""

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


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _real_tab(qapp, stub, toasts):
    tab = ConfigTab(stub, toast=toasts.append)
    yield tab
    tab.deleteLater()


def test_demo_mode_disables_all(qapp):
    toasts: list[str] = []
    tab = ConfigTab(None, toast=toasts.append)
    assert tab.btn_save.isEnabled() is False
    assert tab.btn_reload.isEnabled() is False
    assert tab.f_source_root.isEnabled() is False
    assert tab.f_strategy.isEnabled() is False
    assert tab.lib_table.isEnabled() is False
    assert "演示模式" in tab.learned_hint.text()
    tab.deleteLater()


def test_form_filled_from_describe(qapp):
    stub = StubState(full_describe())
    toasts: list[str] = []
    tab = ConfigTab(stub, toast=toasts.append)
    assert tab.f_source_root.text() == "D:/media"
    assert tab.f_strategy.currentText() == "smart"
    assert tab.f_on_conflict.currentText() == "rename"
    assert tab.f_warn.value() == pytest.approx(0.15)
    assert tab.f_block.value() == pytest.approx(0.3)
    assert tab.f_plot_min_score.value() == pytest.approx(0.75)
    assert tab.f_learning_min_votes.value() == 3
    assert tab.f_priority_text.text() == "科幻、动作"
    assert tab.lib_table.rowCount() == 2
    assert tab.lib_table.item(0, 0).text() == "电影"
    assert tab.lib_table.item(0, 3).text() == "太空=2、机甲=1.5"
    tab.deleteLater()


def test_config_error_banner(qapp):
    stub = StubState(full_describe(), err="第 3 行：库目录不存在")
    toasts: list[str] = []
    tab = ConfigTab(stub, toast=toasts.append)
    assert not tab.cfg_msg.isHidden()
    assert "当前配置无效" in tab.cfg_msg.text()
    assert "第 3 行：库目录不存在" in tab.cfg_msg.text()
    tab.deleteLater()


def test_save_success_and_failure(qapp):
    stub = StubState(full_describe())
    toasts: list[str] = []
    tab = ConfigTab(stub, toast=toasts.append)
    tab.cfg_msg.setText("旧错误")
    tab.cfg_msg.show()
    tab.btn_save.click()
    assert len(stub.saved) == 1
    assert stub.saved[0]["source_root"] == "D:/media"
    assert any("重新扫描" in t for t in toasts)
    assert tab.cfg_msg.isHidden()

    def boom(data):
        raise ConfigError("源目录不存在")

    stub2 = StubState(full_describe())
    stub2.save_config = boom
    tab2 = ConfigTab(stub2, toast=toasts.append)
    tab2.btn_save.click()
    assert "校验失败" in tab2.cfg_msg.text()
    assert "源目录不存在" in tab2.cfg_msg.text()
    assert not tab2.cfg_msg.isHidden()
    tab.deleteLater()
    tab2.deleteLater()


def test_learned_table_and_forget(qapp):
    stub = StubState(full_describe(), learned=[
        {"key": "k1", "genre": "科幻", "lib": "电影",
         "votes": 5, "manual": 1, "last": "2026-11-01"},
    ])
    toasts: list[str] = []
    tab = ConfigTab(stub, toast=toasts.append)
    table = tab.learned_table
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "科幻"
    assert table.item(0, 1).text() == "电影"
    assert table.item(0, 2).text() == "5"
    assert table.item(0, 3).text() == "1"
    btn = table.cellWidget(0, 5)
    assert btn is not None and btn.text() == "忘记"
    btn.click()
    assert stub.forgotten == [("k1", "电影")]
    assert any("已忘记" in t for t in toasts)
    assert table.rowCount() == 0                     # 忘记后立即重渲
    assert not tab.learned_hint.isHidden()           # 空态文案出现

    tab2 = ConfigTab(StubState(full_describe()), toast=toasts.append)
    assert "暂无自学习记录" in tab2.learned_hint.text()
    tab.deleteLater()
    tab2.deleteLater()


def test_dirty_form_not_clobbered_by_refresh(qapp):
    stub = StubState(full_describe())
    toasts: list[str] = []
    tab = ConfigTab(stub, toast=toasts.append)
    assert tab.f_source_root.text() == "D:/media"
    tab.f_source_root.setText("E:/changed")           # 模拟用户编辑 → dirty
    tab.refresh()                                     # 慢 tick，force=False
    assert tab.f_source_root.text() == "E:/changed"   # 编辑保留
    tab.refresh(force=True)                           # 显式重载 → 覆盖
    assert tab.f_source_root.text() == "D:/media"
    tab.deleteLater()


def test_main_window_static_wiring():
    src = Path("app/ui/main_window.py").read_text(encoding="utf-8")
    assert "ConfigTab(" in src
    assert '"③ 配置"' in src
    assert "self.config_tab.refresh" in src           # 慢 tick 喂配置页
    assert '"④ 体检"' in src                          # C5：占位循环已换成 DoctorTab
    assert "from .config_tab import ConfigTab" in src


# ------------------------------------------------------- 目录浏览（Task-06）

def test_browse_source_fills_field_and_marks_dirty(qapp, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **k: "E:/pick/src")
    tab = ConfigTab(StubState(full_describe()), toast=lambda m: None)
    tab.btn_browse_source.click()
    assert tab.f_source_root.text() == "E:/pick/src"
    assert tab._dirty is True
    tab.deleteLater()


def test_browse_cancel_keeps_field(qapp, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **k: "")
    tab = ConfigTab(StubState(full_describe()), toast=lambda m: None)
    tab.btn_browse_source.click()
    assert tab.f_source_root.text() == "D:/media"
    assert tab._dirty is False
    tab.deleteLater()


def _label_row(tab, text):
    """在 tab 的栅格布局里定位某个标签文本所在的 (layout, row)。"""
    from PySide6.QtWidgets import QGridLayout, QLabel
    for grid in tab.findChildren(QGridLayout):
        for r in range(grid.rowCount()):
            it = grid.itemAtPosition(r, 0)
            w = it.widget() if it else None
            if isinstance(w, QLabel) and w.text() == text:
                return grid, r
    raise AssertionError(f"未找到标签行：{text}")


def test_weak_alias_row_rendered_after_alias_row(qapp):
    """视觉顺序程序化钉：「弱别名表」标签行紧跟在「别名表」之后，且该行控件正是弱别名框。

    主审补钉：本会话模型无图像输入，无法目验截图，故把提交正文里"弱别名表行位于
    别名表之后"这句视觉断言改成可跑的布局断言，不靠人眼也不靠措辞。
    """
    tab = ConfigTab(StubState(full_describe()), toast=lambda m: None)
    g_alias, r_alias = _label_row(tab, "别名表")
    g_weak, r_weak = _label_row(tab, "弱别名表")
    assert g_weak is g_alias
    assert r_weak == r_alias + 1
    it = g_weak.itemAtPosition(r_weak, 1)
    assert it is not None and it.widget() is tab.f_weak_alias_text
    tab.deleteLater()


def test_browse_fallback_and_staging_wired(qapp, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    picks = {"选择兜底库目录": "E:/fb", "选择暂存目录（可留空）": "E:/st"}
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **k: picks.get(a[1] if len(a) > 1 else "", ""))
    tab = ConfigTab(StubState(full_describe()), toast=lambda m: None)
    tab.btn_browse_fallback.click()
    tab.btn_browse_staging.click()
    assert tab.f_fallback_path.text() == "E:/fb"
    assert tab.f_staging_dir.text() == "E:/st"
    tab.deleteLater()


def test_add_library_via_dialog_prefills_row(qapp, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **k: "E:/media/新库")
    tab = ConfigTab(StubState(full_describe()), toast=lambda m: None)
    assert tab.lib_table.rowCount() == 2
    tab.btn_add.click()
    assert tab.lib_table.rowCount() == 3
    assert tab.lib_table.item(2, 0).text() == "新库"
    assert tab.lib_table.item(2, 1).text() == "E:/media/新库"
    assert tab.lib_table.item(2, 2).text() == ""
    assert tab._dirty is True
    tab.deleteLater()


def test_add_library_dialog_cancel_adds_nothing(qapp, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **k: "")
    tab = ConfigTab(StubState(full_describe()), toast=lambda m: None)
    tab.btn_add.click()
    assert tab.lib_table.rowCount() == 2
    assert tab._dirty is False
    tab.deleteLater()


def test_demo_mode_disables_browse_controls(qapp):
    tab = ConfigTab(None, toast=lambda m: None)
    assert tab.btn_browse_source.isEnabled() is False
    assert tab.btn_browse_fallback.isEnabled() is False
    assert tab.btn_browse_staging.isEnabled() is False
    tab.deleteLater()


# --------------------------------------------- 弱别名表（C5 / 计划 Task-06）

def test_weak_alias_form_round_trip():
    desc = full_describe()
    desc["weak_genre_aliases"] = {"护士": "动作", "空姐": "科幻"}
    form = describe_to_form(desc)
    assert set(form["weak_alias_text"].splitlines()) == {"护士=动作", "空姐=科幻"}
    form["weak_alias_text"] += "\n\n坏行\n=X\nY="
    body = form_to_body(form, form["library_rows"])
    assert body["weak_genre_aliases"] == desc["weak_genre_aliases"]


def test_weak_alias_textarea_populated(qapp, tmp_path):
    from conftest import build_env

    from app.state import AppState
    cfg_path = build_env(
        tmp_path, overrides={"weak_genre_aliases": {"护士": "动作"}})
    tab = ConfigTab(AppState(cfg_path), toast=lambda m: None)
    assert "护士=动作" in tab.f_weak_alias_text.toPlainText()
    tab.deleteLater()


def test_weak_alias_edit_flows_to_body(qapp):
    tab = ConfigTab(StubState(full_describe()), toast=lambda m: None)
    tab.f_weak_alias_text.setPlainText("护士=动作\n\n坏行")
    form, rows = tab._collect_form()
    body = form_to_body(form, rows)
    assert body["weak_genre_aliases"] == {"护士": "动作"}
    tab.deleteLater()


def test_demo_mode_disables_weak_alias_box(qapp):
    tab = ConfigTab(None, toast=lambda m: None)
    assert tab.f_weak_alias_text.isEnabled() is False
    tab.deleteLater()


def test_title_form_round_trip(qapp):
    """title 控件回填→改动→聚合→form_to_body 全链路（不许原样往返糊过去）。"""
    tab = ConfigTab(StubState(full_describe()), toast=lambda m: None)
    form = describe_to_form(full_describe())
    tab._fill_form(form)
    tab.f_title_enabled.setChecked(False)
    tab.f_title_min_score.setValue(0.35)
    collected, rows = tab._collect_form()
    body = form_to_body(collected, rows)
    assert body["title"] == {"enabled": False, "min_score": 0.35}
    tab.deleteLater()


def test_title_controls_rendered_next_to_plot_group(qapp):
    """视觉顺序程序化钉：title 两控件各占一行，紧邻 plot 组之后，同栅格列 1。"""
    tab = ConfigTab(StubState(full_describe()), toast=lambda m: None)
    g_plot, r_plot = _label_row(tab, "剧情简介")
    g_en, r_en = _label_row(tab, "标题启用")
    g_ms, r_ms = _label_row(tab, "标题阈值")
    assert g_en is g_plot and g_ms is g_plot
    assert r_en == r_plot + 1
    assert r_ms == r_en + 1
    it_en = g_en.itemAtPosition(r_en, 1)
    assert it_en is not None and it_en.widget() is tab.f_title_enabled
    it_ms = g_ms.itemAtPosition(r_ms, 1)
    assert it_ms is not None and it_ms.widget() is tab.f_title_min_score
    tab.deleteLater()


# ------------------------------------- 慢 tick 回填不得重置滚动（GUI 反馈回归）

def test_set_text_stable_same_content_keeps_cursor(qapp):
    """_set_text_stable：内容相同时不得碰文档——setPlainText 对相同文本
    也会把光标与滚动归零，这正是「别名表自动回滚到最上面」的根因。"""
    from PySide6.QtGui import QTextCursor
    tab = ConfigTab(StubState(full_describe()), toast=lambda m: None)
    box = tab.f_alias_text
    box.moveCursor(QTextCursor.End)
    pos = box.textCursor().position()
    assert pos > 0
    tab._set_text_stable(box, box.toPlainText())      # 相同内容 → 整段跳过
    assert box.textCursor().position() == pos
    tab._set_text_stable(box, "A=科幻\nB=动作")       # 内容真变 → 更新
    assert box.toPlainText() == "A=科幻\nB=动作"
    tab.deleteLater()


def test_slow_tick_refresh_keeps_alias_view(qapp):
    """回归（GUI 反馈：别名表自动回滚到最上面）：非 dirty 慢 tick 回填
    不得重置别名框光标/滚动。别名行数多（40 行）时用户正在往下浏览。"""
    from PySide6.QtGui import QTextCursor
    desc = full_describe()
    desc["genre_aliases"] = {f"alias-{i:02d}": "科幻" for i in range(40)}
    tab = ConfigTab(StubState(desc), toast=lambda m: None)
    box = tab.f_alias_text
    box.moveCursor(QTextCursor.End)
    pos = box.textCursor().position()
    assert pos > 0
    tab.refresh()                                     # 慢 tick，force=False
    assert box.textCursor().position() == pos         # 视图原地保持
    tab.deleteLater()


def test_slow_tick_refresh_keeps_lib_table_selection(qapp):
    """库表同理：非 dirty 回填跳过内容一致的重建，选中与滚动不丢。"""
    desc = full_describe()
    desc["libraries"] = [
        {"name": f"库{i:02d}", "path": f"D:/lib{i:02d}", "keywords": [],
         "keywords_weighted": {}} for i in range(30)]
    tab = ConfigTab(StubState(desc), toast=lambda m: None)
    tab.lib_table.selectRow(7)
    tab.refresh()
    assert tab.lib_table.currentRow() == 7
    tab.deleteLater()


def test_slow_tick_refresh_keeps_learned_selection(qapp):
    """自学习清单每次慢 tick 都会渲染（不受 dirty 保护），内容一致时
    必须跳过重建，否则浏览清单时每 2s 被拽回顶部。"""
    learned = [{"key": f"k{i}", "genre": f"题{i}", "lib": "电影",
                "votes": i + 1, "manual": 0, "last": "2026-11-01"}
               for i in range(20)]
    tab = ConfigTab(StubState(full_describe(), learned=learned),
                    toast=lambda m: None)
    tab.learned_table.selectRow(3)
    tab.refresh()
    assert tab.learned_table.currentRow() == 3
    tab.deleteLater()


def test_learned_render_still_updates_on_change(qapp):
    """内容真变（忘记一条）时重建路径不受跳过优化影响。"""
    learned = [{"key": "k1", "genre": "科幻", "lib": "电影",
                "votes": 5, "manual": 1, "last": "2026-11-01"}]
    stub = StubState(full_describe(), learned=learned)
    tab = ConfigTab(stub, toast=lambda m: None)
    assert tab.learned_table.rowCount() == 1
    tab._on_forget("k1", "电影")
    assert tab.learned_table.rowCount() == 0          # 空态立即渲染
    assert not tab.learned_hint.isHidden()
    tab.deleteLater()

"""计划页 widget 级驱动测试（D-20261102-02 协议第 4 条）。

QT_QPA_PLATFORM=offscreen + 纯 PySide6 QTest 能力，零新增测试依赖。
覆盖：渲染行数、勾选→视图模型、筛选→重建且选择存活、改判→单元格与
视图模型联动、演示模式按钮禁用、阻断确认对话框的门禁语义。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from conftest import build_env
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.ui.demo_data import fake_units
from app.ui.main_window import MainWindow
from app.ui.plan_tab import BlockConfirmDialog, PlanTab
from app.ui.table_cells import COL_CHECK, COL_LIB


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def tab(qapp):
    toasts: list[str] = []
    tab = PlanTab(None, fake_units(40, seed=7), toast=toasts.append)
    yield tab, toasts
    tab.deleteLater()


def test_renders_all_demo_rows(tab):
    tab, _ = tab
    assert tab.table.rowCount() == 40
    assert tab.summary.text().endswith("共 40 部")
    assert tab.btn_apply.text() == "执行选中（0 部）" or "执行选中" in tab.btn_apply.text()


def test_demo_mode_disables_job_buttons(tab):
    tab, _ = tab
    assert tab.btn_scan.isEnabled() is False
    assert tab.btn_apply.isEnabled() is False
    assert tab.btn_scan.toolTip()             # 必须解释为什么禁用


def test_check_toggles_viewmodel_and_summary(tab):
    tab, _ = tab
    tab._clear_selection()                    # 走真实按钮路径：vm 与表格同步清空
    assert tab.vm.checked == set()
    row = next(r for r in range(tab.table.rowCount())
               if tab.table.item(r, COL_CHECK).checkState() == Qt.Unchecked)
    uid = tab._rows[row]["id"]
    # 注意：对已勾选的格重复 setCheckState(Checked) 是同值赋值，Qt 不发 itemChanged
    tab.table.item(row, COL_CHECK).setCheckState(Qt.Checked)
    assert uid in tab.vm.checked
    assert "已选 1 部" in tab.summary.text()
    tab.table.item(row, COL_CHECK).setCheckState(Qt.Unchecked)
    assert uid not in tab.vm.checked


def test_clear_button_syncs_table_and_vm(tab):
    tab, _ = tab
    assert tab.vm.checked, "demo 默认应有人物勾选"
    tab._clear_selection()
    assert tab.vm.checked == set()
    states = {tab.table.item(r, COL_CHECK).checkState()
              for r in range(tab.table.rowCount())}
    assert states == {Qt.Unchecked}


def test_filter_rebuilds_and_keeps_selection(tab):
    tab, _ = tab
    tab._clear_selection()
    row = next(r for r in range(tab.table.rowCount())
               if tab.table.item(r, COL_CHECK).checkState() == Qt.Unchecked)
    uid = tab._rows[row]["id"]
    tab.table.item(row, COL_CHECK).setCheckState(Qt.Checked)
    assert uid in tab.vm.checked
    fallback_ids = {u["id"] for u in tab.vm.rows() if u["level"] == "fallback"}
    assert fallback_ids, "demo 数据应含兜底行"
    tab.set_filter("fallback")
    assert tab.table.rowCount() == len(fallback_ids)
    assert uid in tab.vm.checked              # 选择跨筛选存活
    tab.set_filter("all")
    assert tab.table.rowCount() == 40


def test_override_updates_vm_and_cell(tab):
    tab, _ = tab
    tab.table.selectRow(0)
    u = tab._current_unit
    assert u is not None
    target = next((lib for lib in tab._libs if lib != u["target_lib"]), None)
    assert target, "demo 数据应有其他可选库"
    tab.d_override.setCurrentText(target)
    assert tab.vm.overrides[u["id"]] == target
    assert tab._rows[0]["id"] == u["id"]      # 行仍在
    cell = tab.table.item(0, COL_LIB)
    assert cell.text().endswith(" *")


def test_clear_override_via_sentinel(tab):
    tab, _ = tab
    tab.table.selectRow(0)
    u = tab._current_unit
    tab.d_override.setCurrentText("（不改判）")
    assert u["id"] not in tab.vm.overrides


def test_block_dialog_gate_semantics(qapp):
    ackable = [{"level": "block", "code": "jellyfin_running",
                "message": "检测到 Jellyfin 正在运行", "detail": ["Jellyfin.exe"]}]
    dlg = BlockConfirmDialog(ackable)
    assert dlg._ok.isEnabled() is False       # 未逐项确认前不可继续
    dlg._boxes[0][1].setChecked(True)
    assert dlg._ok.isEnabled() is True

    fatal = ackable + [{"level": "block", "code": "paths_missing",
                        "message": "配置中的目录不存在", "detail": ["D:\\nope"]}]
    dlg2 = BlockConfirmDialog(fatal)
    assert dlg2._fatal is True
    assert dlg2._ok.isEnabled() is False      # 不可越过的阻断直接禁用执行

    # 新白名单（C5）：disk_space / staging_leftover 同为硬阻断不可勾，
    # jellyfin_running / fallback_ratio 仍可勾越过
    mixed = [
        {"level": "block", "code": "disk_space", "message": "磁盘空间不足",
         "detail": []},
        {"level": "warn", "code": "staging_leftover", "message": "发现半成品残留",
         "detail": [".incomplete-x"]},
        {"level": "warn", "code": "fallback_ratio", "message": "兜底占比过高",
         "detail": []},
    ] + ackable
    dlg3 = BlockConfirmDialog(mixed)
    assert dlg3._fatal is True
    boxes = dict(dlg3._boxes)
    assert "disk_space" not in boxes and "staging_leftover" not in boxes
    assert "jellyfin_running" in boxes and "fallback_ratio" in boxes
    fatal_texts = [b.text() for b in dlg3.findChildren(type(dlg3._boxes[0][1]))
                   if not b.isEnabled()]
    assert any("④ 体检页一键清理" in t for t in fatal_texts)
    assert dlg3._ok.isEnabled() is False


def test_main_window_demo_builds_and_closes(qapp):
    win = MainWindow(None, demo_units=fake_units(20, seed=3))
    assert win.plan_tab.table.rowCount() == 20
    assert win.pill.text() == "空闲"
    assert win.close() is True                # 无任务运行，关窗不应被拦截
    win.deleteLater()


# ------------------------------------------------- 本次输出目录 UI（Task-07）

class _OutputStubState:
    """非演示 tab 用的最小 stub（浏览/清除交互需要可点击按钮）。"""

    def plan(self):
        return {"units": fake_units(5, seed=1)}


@pytest.fixture()
def live_tab(qapp):
    toasts: list[str] = []
    tab = PlanTab(_OutputStubState(), None, toast=toasts.append)
    yield tab
    tab.deleteLater()


def test_output_controls_initial_state(tab):
    tab, _ = tab
    assert tab.f_out_dir.text() == ""
    assert "未选择" in tab.f_out_dir.placeholderText()
    assert tab.chk_by_category.isChecked() is True
    assert tab.btn_clear_out.isEnabled() is False


def test_browse_output_sets_vm_and_clear_enabled(live_tab, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **k: "E:/out")
    live_tab.btn_browse_out.click()
    assert live_tab.vm.output_root == "E:/out"
    assert live_tab.f_out_dir.text() == "E:/out"
    assert live_tab.btn_clear_out.isEnabled() is True
    assert live_tab.chk_by_category.isEnabled() is True


def test_clear_output_resets(live_tab, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **k: "E:/out")
    live_tab.btn_browse_out.click()
    live_tab.btn_clear_out.click()
    assert live_tab.vm.output_root is None
    assert live_tab.f_out_dir.text() == ""
    assert live_tab.btn_clear_out.isEnabled() is False
    assert live_tab.chk_by_category.isEnabled() is False


def test_category_checkbox_syncs_vm(tab):
    tab, _ = tab
    tab.chk_by_category.setChecked(False)
    assert tab.vm.group_by_category is False


def test_output_controls_disabled_in_demo(tab):
    tab, _ = tab
    assert tab.btn_browse_out.isEnabled() is False
    assert tab.btn_clear_out.isEnabled() is False
    assert tab.f_out_dir.isEnabled() is False
    assert tab.chk_by_category.isEnabled() is False


def test_output_controls_reset_after_rebuild(live_tab, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **k: "E:/out")
    live_tab.btn_browse_out.click()
    live_tab.refresh(force=True)
    assert live_tab.vm.output_root is None
    assert live_tab.f_out_dir.text() == ""
    assert live_tab.chk_by_category.isChecked() is True


def test_start_apply_forwards_output_params(qapp):
    class ApplyStubState:
        def __init__(self):
            self.calls = []

        def plan(self):
            return {"units": fake_units(5, seed=1)}

        def start_apply(self, ids, acks, overrides,
                        output_root=None, group_by_category=True):
            self.calls.append((ids, acks, overrides, output_root,
                               group_by_category))

    stub = ApplyStubState()
    toasts: list[str] = []
    tab = PlanTab(stub, None, toast=toasts.append)
    tab.vm.set_output_root("E:/out")
    tab._start_apply(["u1"], set(), {})
    assert stub.calls == [(["u1"], set(), {}, "E:/out", True)]
    tab.deleteLater()


# ---------------- 三层布局：详情「目标路径」行与 demo 同构（D-20261110-01，Task-07） ----------------

def test_detail_shows_dst_path(tab):
    tab, _ = tab
    tab.table.selectRow(0)
    assert tab._current_unit is not None
    text = tab.d_fields["dst"].text()
    assert text
    assert text == tab.vm.effective_dst_dir(tab._current_unit)


def test_demo_units_carry_actress_fields():
    rows = fake_units(40, seed=7)
    assert all(("actress" in r and (r["actress"] is None or r["actress"]))
               for r in rows)
    assert all(r.get("dst_name") for r in rows)
    with_actress = [r for r in rows if r["actress"]]
    assert with_actress, "demo 必须存在带女优段的行以驱动新展示"
    for r in with_actress:
        assert r["actress"] in r["dst_dir"]
        assert r["actress"] in r["src"]




# ---------------- 右键打开影片所在目录 + 配置过期横幅（2026-11-11 GUI 反馈） ----------------

class _PlanStubState:
    """带 plan 与 config_hash 的最小 stub：横幅/右键测试用，不碰磁盘。"""

    def __init__(self, plan=None, config_hash="hash-new"):
        self._plan = plan
        self.hash = config_hash

    def plan(self):
        return self._plan

    def config_hash(self):
        return self.hash


def _stub_plan(config_hash="hash-old", src=None):
    units = fake_units(3, seed=5)
    if src is not None:
        for u in units:
            u["src"] = str(src)
    return {"units": units, "config_hash": config_hash}


def test_context_menu_routes_to_menu_with_selected_row(qapp, tmp_path, monkeypatch):
    """回归（GUI 反馈）：计划行右键 →「打开影片所在目录」，方便看内容改判。

    QMenu.exec 是 Shiboken 静态分发、offscreen 下模态循环不可自终止
    （monkeypatch 拦不住 C++ 路由，曾把 CI 挂死）——故单测在
    _show_row_menu 注入替身只验证行映射与选中，菜单结构与选择分支
    分别由 _handle_row_menu_choice 的纯逻辑用例覆盖，真菜单走冒烟目验。
    """
    from PySide6.QtCore import QPoint

    movie_dir = tmp_path / "影片A"
    movie_dir.mkdir()
    tab = PlanTab(_PlanStubState(_stub_plan(src=movie_dir)), None,
                  toast=lambda m: None)
    tab.refresh(force=True)
    shown: list[tuple[dict, object]] = []
    monkeypatch.setattr(tab, "_show_row_menu",
                        lambda u, pos: shown.append((u, pos)))
    tab._on_table_context_menu(QPoint(5, 16))   # 第 0 行（行高 32）
    assert len(shown) == 1
    assert shown[0][0]["src"] == str(movie_dir)
    assert tab.table.currentRow() == 0          # 右键即选中，详情面板同步
    tab.deleteLater()


def test_row_menu_choice_picked_opens_source_dir(qapp, tmp_path, monkeypatch):
    """选择分支（纯逻辑）：点中「打开影片所在目录」→ 打开目录型单元本身。"""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    movie_dir = tmp_path / "影片A"
    movie_dir.mkdir()
    tab = PlanTab(_PlanStubState(), None, toast=lambda m: None)
    opened: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        lambda url: opened.append(url))
    act = object()          # 哨兵「选中项」，等价于 menu.addAction 的返回值
    tab._handle_row_menu_choice({"src": str(movie_dir), "kind": "dir"},
                                chosen=act, act_open=act)
    assert opened == [QUrl.fromLocalFile(str(movie_dir))]
    tab.deleteLater()


def test_row_menu_choice_cancelled_does_not_open(qapp, monkeypatch):
    """取消/点了别的（exec 返回 None 或非目标项）→ 不打开。"""
    from PySide6.QtGui import QDesktopServices

    tab = PlanTab(_PlanStubState(), None, toast=lambda m: None)
    opened: list = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        lambda url: opened.append(url))
    act = object()
    tab._handle_row_menu_choice({"src": "D:/x", "kind": "dir"},
                                chosen=None, act_open=act)
    tab._handle_row_menu_choice({"src": "D:/x", "kind": "dir"},
                                chosen=object(), act_open=act)
    assert opened == []
    tab.deleteLater()


def test_open_source_dir_loose_file_uses_parent(qapp, tmp_path, monkeypatch):
    """散装文件单元「所在目录」= 父目录。"""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    video = tmp_path / "Movie.mp4"
    video.write_bytes(b"x")
    tab = PlanTab(_PlanStubState(), None, toast=lambda m: None)
    opened: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        lambda url: opened.append(url))
    tab._open_source_dir({"src": str(video), "kind": "file"})
    assert opened == [QUrl.fromLocalFile(str(tmp_path))]
    tab.deleteLater()


def test_open_source_dir_missing_toasts_and_skips(qapp, tmp_path, monkeypatch):
    """目录单元已不在源处（执行搬运后）→ 提示，不猜父级不误开。"""
    from PySide6.QtGui import QDesktopServices
    toasts: list[str] = []
    opened: list = []
    tab = PlanTab(_PlanStubState(), None, toast=toasts.append)
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        lambda url: opened.append(url))
    tab._open_source_dir({"src": str(tmp_path / "已消失"), "kind": "dir"})
    assert opened == []
    assert toasts and "已不存在" in toasts[-1]
    tab.deleteLater()


def test_context_menu_outside_rows_is_noop(qapp, monkeypatch):
    """右键空白区（行号越界）不弹菜单不报错。"""
    from PySide6.QtCore import QPoint
    tab = PlanTab(_PlanStubState(_stub_plan()), None, toast=lambda m: None)
    tab.refresh(force=True)
    shown: list = []
    monkeypatch.setattr(tab, "_show_row_menu", lambda u, pos: shown.append(u))
    tab._on_table_context_menu(QPoint(5, 10_000))   # 超出行数
    assert shown == []
    tab.deleteLater()


def test_stale_banner_shown_and_resolved(qapp):
    """回归（GUI 反馈：大量影片归于一类实为旧配置时代的计划）：
    config_hash 不一致 → 计划页顶部挂「请重新扫描」横幅；digest 未变时
    横幅也必须刷新（改配置不动 plan，早退路径不能吞掉横幅更新）。"""
    tab = PlanTab(_PlanStubState(_stub_plan("hash-old"), config_hash="hash-new"),
                  None, toast=lambda m: None)
    tab.refresh(force=True)
    assert not tab.stale_hint.isHidden()
    assert "重新扫描" in tab.stale_hint.text()
    tab.state.hash = "hash-old"        # 配置回到与计划一致
    tab.refresh()                      # force=False：digest 相同早退路径
    assert tab.stale_hint.isHidden()
    tab.deleteLater()


def test_stale_banner_absent_without_hash_or_plan(qapp):
    tab = PlanTab(_PlanStubState({"units": fake_units(2, seed=1)}), None,
                  toast=lambda m: None)               # plan 无 config_hash
    tab.refresh(force=True)
    assert tab.stale_hint.isHidden()
    tab.state._plan = None
    tab.refresh(force=True)
    assert tab.stale_hint.isHidden()
    tab.deleteLater()


# ---------------- 改判候选=配置全量库（2026-11-12 用户反馈） ----------------

class _LibsStubState:
    """带 plan/config_hash/config_path 的最小 stub：改判候选回归测试用。"""

    def __init__(self, cfg_path, plan=None):
        self.config_path = cfg_path
        self._plan = plan

    def plan(self):
        return self._plan

    def config_hash(self):
        return (self._plan or {}).get("config_hash", "hash-new")


def _override_items(tab) -> list[str]:
    return [tab.d_override.itemText(i) for i in range(tab.d_override.count())]


def test_override_candidates_cover_all_config_libs(qapp, tmp_path):
    """回归（2026-11-12 反馈）：改判候选应含配置全量库，而非仅计划内命中过的库。

    旧行为：候选=当前可见行 target_lib 去重集合——某库本次扫描零命中
    （或行被筛选/搜索隐藏）时下拉框中无该库，无从改判入内。
    """
    cfg_path = build_env(tmp_path)              # 科幻/动作 两库 + 兜底
    units = fake_units(3, seed=5)
    for u in units:
        u["target_lib"] = "动作"                 # 计划内只命中 动作
    state = _LibsStubState(cfg_path, plan={"units": units, "config_hash": "hash-new"})
    tab = PlanTab(state, None, toast=lambda m: None)
    try:
        tab.table.selectRow(0)                   # 走真实路径触发 _fill_libs
        items = _override_items(tab)
        assert "科幻" in items and "动作" in items
        assert items[0] == "（不改判）" and items[-1] == "兜底库"
    finally:
        tab.deleteLater()


def test_override_candidates_demo_mode_falls_back_to_plan_libs(tab):
    """演示模式（state=None）保持旧行为：候选=计划内去重集合。"""
    tab, _ = tab
    tab.table.selectRow(0)
    expect = ["（不改判）"] + sorted(
        {u["target_lib"] for u in tab._rows} - {"兜底库"}) + ["兜底库"]
    assert _override_items(tab) == expect


def test_override_candidates_fallback_when_config_unreadable(qapp, tmp_path):
    """配置不可读（缺失/损坏）时优雅降级：候选=计划内派生集合。"""
    units = fake_units(3, seed=5)
    for u in units:
        u["target_lib"] = "动作"
    state = _LibsStubState(tmp_path / "missing.toml",
                           plan={"units": units, "config_hash": "hash-new"})
    tab = PlanTab(state, None, toast=lambda m: None)
    try:
        tab.table.selectRow(0)
        items = _override_items(tab)
        assert "科幻" not in items and "动作" in items
    finally:
        tab.deleteLater()


def test_multi_version_override_passes_apply_gate(qapp):
    """回归（2026-11-12 反馈）：多版本单元改判后不再被「不可执行（冲突/残留）」拦截。"""
    units = fake_units(2, seed=3)
    for u in units:
        u["status"] = "multi_version"
        u["default_selected"] = False

    class GateStubState:
        def __init__(self):
            self.preflight_ids = None

        def plan(self):
            return {"units": units}

        def start_preflight(self, ids):
            self.preflight_ids = ids

    stub = GateStubState()
    toasts: list[str] = []
    tab = PlanTab(stub, None, toast=toasts.append)
    try:
        ids = [u["id"] for u in tab.vm.rows()]
        for i in ids:
            tab.vm.checked.add(i)
            tab.vm.set_override(i, "科幻")
        assert tab.vm.can_apply() is True           # 修复前 False（拦截源）
        tab._apply_selected()
        assert "不可执行" not in "".join(toasts)     # 修复前正是这条 toast
        assert stub.preflight_ids == ids            # 走到体检而非拦截
    finally:
        tab.deleteLater()


def test_blocked_toast_names_unit_and_reason(qapp):
    """回归（2026-11-12 反馈）：拦截 toast 点名单元与真实原因，替代笼统措辞。"""
    units = fake_units(1, seed=9)
    for u in units:
        u["status"] = "multi_version"
        u["default_selected"] = False

    class GateStubState:
        def plan(self):
            return {"units": units}

        def start_preflight(self, ids):
            raise AssertionError("门未拦截，不应走到体检")

    toasts: list[str] = []
    tab = PlanTab(GateStubState(), None, toast=toasts.append)
    try:
        u = tab.vm.rows()[0]
        tab.vm.checked.add(u["id"])
        tab._apply_selected()
        assert len(toasts) == 1
        assert f"《{u['label']}》多版本需确认" in toasts[0]
        assert "请在详情面板改判指定目标库" in toasts[0]
        assert "冲突/残留" not in toasts[0]
    finally:
        tab.deleteLater()

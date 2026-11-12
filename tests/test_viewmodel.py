"""计划页视图模型单测：不启动任何窗口、不导入 Qt（D-20261102-02 协议第 1 条）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.core import planner
from app.core.planner import READY, ST_APPLIED, ST_CONFLICT, ST_MULTI, STATUS_LABELS
from app.ui import viewmodel as vm


def make_unit(uid: str, *, level="rule", status=READY, lib="科幻", conf="high",
              size=1024 ** 3, genres=("科幻",), default_selected=None,
              label=None) -> dict:
    """按 planner 真实字段造 unit（只造 viewmodel 用到的键 + 少量上下文）。

    注意 status 与 level 相互独立：fallback/plot 级别的单元同样可以是 READY。
    default_selected 缺省时复刻 planner 的规则（READY 且规则级 / 自学习且中置信）。弱规则（low）不默认勾选。
    """
    if default_selected is None:
        default_selected = status == READY and (
            (level == "rule" and conf != "low")
            or (level == "learned" and conf == "medium"))
    return {
        "id": uid,
        "label": label or uid,
        "level": level,
        "status": status,
        "confidence": conf,
        "target_lib": lib,
        "target_root": rf"D:\媒体库\{lib}",
        "genres": genres,
        "total_size": size,
        "file_count": 3,
        "evidence": ["NFO <genre> 命中"],
        "default_selected": default_selected,
    }


@pytest.fixture()
def units() -> list[dict]:
    """A-D 均为 READY（等级不同），E 冲突、F 已执行。"""
    return [
        make_unit("A 规则", lib="科幻"),
        make_unit("B 摘要", level="plot", conf="medium", lib="动作",
                  genres=("动作",), default_selected=False),
        make_unit("C 自学", level="learned", conf="medium", lib="恐怖"),
        make_unit("D 兜底", level="fallback", lib="兜底库", default_selected=False),
        make_unit("E 冲突", status=ST_CONFLICT, default_selected=False),
        make_unit("F 已执行", status=ST_APPLIED, default_selected=False),
    ]


# ---------------------------------------------------------------- 架构守卫

def test_viewmodel_importable_without_qt():
    """Qt 层依赖本模块；反向依赖（或顺带拖入 PySide6）即层次失效。"""
    code = ("import sys, app.ui.viewmodel;"
            "bad=[m for m in sys.modules if m.startswith('PySide6')];"
            "print(bad);sys.exit(1 if bad else 0)")
    proc = subprocess.run([sys.executable, "-c", code], check=False,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"viewmodel 拖入了 Qt：{proc.stdout}{proc.stderr}"


# ---------------------------------------------------------------- 默认勾选

def test_default_selection_follows_planner_flag(units):
    """默认勾选照抄 planner 的 default_selected，本模块不得自作主张重算。"""
    model = vm.PlanViewModel(units)
    assert model.checked_ids() == ["A 规则", "C 自学"]


def test_default_selection_is_copied_not_aliased(units):
    """构造时必须拷贝集合，否则外部对 plan 的引用变化会静默改掉勾选。"""
    model = vm.PlanViewModel(units)
    model.checked.discard("A 规则")
    assert units[0]["default_selected"] is True


# ---------------------------------------------------------------- 筛选与搜索

def test_filter_semantics(units):
    model = vm.PlanViewModel(units)
    assert [u["id"] for u in model.rows()] == ["A 规则", "B 摘要", "C 自学",
                                               "D 兜底", "E 冲突", "F 已执行"]

    model.set_filter(vm.FILTER_READY)
    assert [u["id"] for u in model.rows()] == ["A 规则", "B 摘要", "C 自学", "D 兜底"]

    model.set_filter(vm.FILTER_BLOCKED)
    assert [u["id"] for u in model.rows()] == ["E 冲突"]

    model.set_filter(vm.FILTER_APPLIED)
    assert [u["id"] for u in model.rows()] == ["F 已执行"]

    model.set_filter("plot")
    assert [u["id"] for u in model.rows()] == ["B 摘要"]

    model.set_filter("fallback")
    assert [u["id"] for u in model.rows()] == ["D 兜底"]

    model.set_filter(vm.FILTER_ALL)
    assert len(model.rows()) == 6
    with pytest.raises(ValueError):
        model.set_filter("不存在的筛选")


def test_filter_and_search_preserve_selection_and_overrides(units):
    """筛选/搜索重建行列表后，勾选与改判必须原样存活（decision-critic R5）。"""
    model = vm.PlanViewModel(units)
    model.set_checked("B 摘要", True)
    model.set_override("C 自学", "喜剧")

    model.set_query("摘要")
    assert [u["id"] for u in model.rows()] == ["B 摘要"]
    assert "B 摘要" in model.checked
    assert model.overrides == {"C 自学": "喜剧"}

    model.set_query("")
    model.set_filter("learned")
    assert model.checked_ids() == ["A 规则", "B 摘要", "C 自学"]
    assert model.effective_target_lib(model.unit("C 自学")) == "喜剧"


def test_query_matches_label_lib_and_genre(units):
    model = vm.PlanViewModel(units)
    model.set_query("科幻")                      # A 的库、C/D/E/F 的题材命中
    assert {u["id"] for u in model.rows()} == {"A 规则", "C 自学", "D 兜底",
                                               "E 冲突", "F 已执行"}
    model.set_query("动作")                      # 只有 B 的库与题材
    assert {u["id"] for u in model.rows()} == {"B 摘要"}
    model.set_query("科幻 (")                    # 不存在的组合
    assert model.rows() == []
    model.set_query("")
    assert len(model.rows()) == 6


def test_rows_keep_plan_order_when_filter_all(units):
    model = vm.PlanViewModel(units)
    assert [u["id"] for u in model.rows()] == [u["id"] for u in units]


# ---------------------------------------------------------------- 选择集

def test_checked_ids_follow_plan_order_and_bytes(units):
    model = vm.PlanViewModel(units)
    model.clear_selection()
    model.set_checked("F 已执行", True)
    model.set_checked("A 规则", True)
    assert model.checked_ids() == ["A 规则", "F 已执行"]     # 计划顺序，非勾选顺序
    assert model.checked_bytes() == 2 * 1024 ** 3


def test_select_visible_ready_is_visibility_scoped(units):
    """「全选可执行」只作用于当前可见行：筛选切换不放大选择范围。"""
    model = vm.PlanViewModel(units)
    model.clear_selection()
    model.set_filter("plot")
    model.select_visible_ready()
    assert model.checked_ids() == ["B 摘要"]                  # 可见行里唯一的 READY

    model.set_filter(vm.FILTER_ALL)                           # 换筛选不自动扩选
    assert model.checked_ids() == ["B 摘要"]
    model.select_visible_ready()
    assert model.checked_ids() == ["A 规则", "B 摘要", "C 自学", "D 兜底"]

    model.set_filter(vm.FILTER_BLOCKED)                       # 可见行全非 READY
    model.select_visible_ready()
    assert model.checked_ids() == ["A 规则", "B 摘要", "C 自学", "D 兜底"]


def test_can_apply_and_checked_not_ready(units):
    model = vm.PlanViewModel(units)
    assert model.can_apply() is True                          # 默认勾选全 READY
    model.set_checked("E 冲突", True)
    assert [u["id"] for u in model.checked_not_ready()] == ["E 冲突"]
    assert model.can_apply() is False
    model.clear_selection()
    assert model.can_apply() is False                         # 空选择不可执行


def test_toggle_flips_and_respects_unknown_id(units):
    model = vm.PlanViewModel(units)
    model.clear_selection()
    model.toggle("A 规则")
    assert model.checked_ids() == ["A 规则"]
    model.toggle("A 规则")
    assert model.checked_ids() == []
    model.toggle("不存在")
    assert model.checked_ids() == []


# ---------------------------------------------------------------- 改判

def test_override_set_clear_and_effective_target(units):
    model = vm.PlanViewModel(units)
    model.set_override("A 规则", "喜剧")
    assert model.effective_target_lib(model.unit("A 规则")) == "喜剧"
    assert model.overridden_ids() == ["A 规则"]

    model.set_override("A 规则", None)
    assert model.effective_target_lib(model.unit("A 规则")) == "科幻"
    assert model.overridden_ids() == []

    model.set_override("不存在", "喜剧")                       # 未知 id 静默忽略
    assert model.overrides == {}
    model.set_override("A 规则", "")                          # 空串等价撤销
    assert model.overrides == {}


# ---------------------------------------------------------------- 徽章与文案

def test_status_badge_uses_planner_labels_not_a_private_copy():
    """文案唯一真值源是 planner.STATUS_LABELS；计划外状态应原样回显。"""
    assert vm.status_badge({"status": READY}) == (STATUS_LABELS[READY], READY)
    assert vm.status_badge({"status": ST_CONFLICT}) == ("同名冲突", ST_CONFLICT)
    assert vm.status_badge({"status": ST_MULTI}) == ("多版本需确认", ST_MULTI)
    assert vm.status_badge({"status": "未来状态"}) == ("未来状态", "未来状态")


def test_level_and_confidence_badges():
    assert vm.level_badge({"level": "rule"}) == ("规则", "rule")
    assert vm.level_badge({"level": "fallback"}) == ("兜底", "fallback")
    assert vm.level_badge({"level": "怪值"}) == ("未知", "dim")
    assert vm.confidence_badge({"confidence": "high"}) == ("高", "ok")
    assert vm.confidence_badge({"confidence": "medium"}) == ("中", "plot")
    assert vm.confidence_badge({"confidence": "low"}) == ("低", "fb")
    assert vm.confidence_badge({"confidence": None}) == ("—", "dim")


# ---------------------------------------------------------------- 汇总与体积

def test_stats_full_scope_ignores_filter(units):
    model = vm.PlanViewModel(units)
    model.set_filter("fallback")
    st = model.stats()                                        # 全量口径，不受筛选影响
    assert st["total"] == 6 and st["ready"] == 4 and st["applied"] == 1
    assert st["blocked"] == 1
    assert st["rule"] == 3        # A + E + F（E/F 的 level 缺省也是 rule）
    assert st["plot"] == 1 and st["learned"] == 1 and st["fallback"] == 1
    assert st["fallback_ratio"] == pytest.approx(1 / 6)


def test_stats_empty_plan():
    st = vm.PlanViewModel([]).stats()
    assert st["total"] == 0 and st["fallback_ratio"] == 0


def test_human_size_tiers():
    assert vm.human_size(0) == "—"
    assert vm.human_size(-5) == "—"
    assert vm.human_size(512 * 1024 ** 2) == "512 MB"
    assert vm.human_size(1024 ** 3) == "1.0 GB"
    assert vm.human_size(83_708.4 * 1024 ** 3) == "81.75 TB"   # 回归：曾显示 83708.4 GB
    assert vm.human_size(2 * 1024 ** 4) == "2.00 TB"
    # 回归：demo/小文件环境曾显示「0 MB」
    assert vm.human_size(20_015) == "19.5 KB"
    assert vm.human_size(1024) == "1.0 KB"


# ---------------------------------------------------------------- 卡片配色

def test_card_tones_zero_metrics_are_never_alert_colored():
    """红色 0 / 橙色 0 是空警讯（真数据核验备注）。"""
    stats = {"total": 0, "ready": 0, "rule": 0, "plot": 0, "learned": 0,
             "fallback": 0, "blocked": 0, "applied": 0, "fallback_ratio": 0.0}
    tones = {label: tone for _v, label, tone in vm.card_tones(stats)}
    assert tones["需人工处理"] == "dim"
    assert tones["兜底"] == "dim"
    assert tones["可执行"] == "dim"
    assert tones["自学习"] == "dim"
    assert tones["摘要预判"] == "dim"


def test_card_tones_nonzero_keep_semantic_colors(units):
    tones = {label: tone for _v, label, tone in vm.card_tones(
        vm.PlanViewModel(units).stats())}
    assert tones["可执行"] == "ok"
    assert tones["摘要预判"] == "plot"
    assert tones["自学习"] == "learned"
    assert tones["需人工处理"] == "bad"
    assert tones["影片单元"] == "dim"
    assert tones["规则判定"] == "dim"


def test_card_tones_fallback_alert_only_above_threshold():
    """兜底卡只在占比 > 0.15 时染橙：演示 9% 白、真扫 33% 橙，两版都对。"""
    def tones_for(fallback: int, total: int) -> str:
        stats = {"total": total, "ready": 0, "rule": 0, "plot": 0, "learned": 0,
                 "fallback": fallback, "blocked": 0, "applied": 0,
                 "fallback_ratio": fallback / total}
        return {label: tone for _v, label, tone in vm.card_tones(stats)}["兜底"]

    assert tones_for(456, 5000) == "dim"      # 9% → 白（pilot 基线）
    assert tones_for(2, 6) == "warn"          # 33% → 橙（demo 真扫描）
    assert tones_for(15, 100) == "dim"        # 恰在阈值上 → 白
    assert tones_for(16, 100) == "warn"       # 越过阈值 → 橙


def test_card_tones_shape_matches_seven_cards(units):
    rows = vm.card_tones(vm.PlanViewModel(units).stats())
    assert len(rows) == 7
    assert all(len(r) == 3 for r in rows)
    assert [label for _v, label, _t in rows] == [
        "影片单元", "可执行", "规则判定", "摘要预判", "自学习", "兜底", "需人工处理"]
    assert rows[0][0] == "6" and rows[1][0] == "4"      # 千分位前的小数值


# ------------------------------------------------------- 本次输出目录（会话级）

def test_output_root_defaults_none_and_group_true(units):
    model = vm.PlanViewModel(units)
    assert model.output_root is None
    assert model.group_by_category is True


def test_set_output_root_blank_clears(units):
    model = vm.PlanViewModel(units)
    for blank in ("  ", "", None):
        model.set_output_root(blank)
        assert model.output_root is None
    model.set_output_root("E:/out")
    assert model.output_root == "E:/out"


def test_effective_output_root_groups_by_effective_lib(units):
    model = vm.PlanViewModel(units)
    model.set_output_root(r"E:\out")
    a = units[0]                                  # 科幻
    d = units[3]                                  # 兜底库
    assert "科幻" in model.effective_output_root(a)
    assert model.effective_output_root(d) == r"E:\out\兜底库"
    model.set_override("A 规则", "喜剧")
    assert model.effective_output_root(a) == r"E:\out\喜剧"


def test_effective_output_root_flat_when_group_off(units):
    model = vm.PlanViewModel(units)
    model.set_output_root(r"E:\out")
    model.group_by_category = False
    for u in units:
        assert model.effective_output_root(u) == r"E:\out"


def test_effective_output_root_none_without_output(units):
    model = vm.PlanViewModel(units)
    model.set_override("A 规则", "喜剧")
    assert model.effective_output_root(units[0]) is None


def test_session_dst_root_rule_shared_with_jobs():
    """UI 预览与 jobs 落盘必须走同一组合规则（防两处漂移）。"""
    assert planner.session_dst_root(r"E:\out", "科幻", True) == Path(r"E:\out\科幻")
    assert planner.session_dst_root(r"E:\out", "科幻", False) == Path(r"E:\out")
    assert vm.session_dst_root is planner.session_dst_root

def test_title_badge_and_filter(units):
    """title 徽章沿用 plot 色值；level 筛选 "title" 只留 title 单元。"""
    assert "title" in vm.LEVEL_BADGES
    assert vm.LEVEL_BADGES["title"][1] == vm.LEVEL_BADGES["plot"][1]
    t = make_unit("G 标题", level="title", conf="low", lib="科幻",
                  default_selected=False)
    model = vm.PlanViewModel(units + [t])
    model.set_filter("title")
    assert [r["id"] for r in model.rows()] == ["G 标题"]


def test_composite_gate_requires_override():
    """ST_BATCH 复合单元：无人工改判不得执行，改判后解锁（card-20261110-batch-gate）。"""
    u = make_unit("G 整目录", level="composite", status=planner.ST_BATCH,
                  lib="兜底库", default_selected=False, genres=())
    model = vm.PlanViewModel([u])
    model.checked.add(u["id"])
    assert u["id"] in {x["id"] for x in model.checked_not_ready()}
    assert model.can_apply() is False
    assert model._executable(u) is False
    model.set_override(u["id"], "科幻")
    assert model._executable(u) is True
    assert model.checked_not_ready() == []
    assert model.can_apply() is True


# ---------------- 三层布局：目标路径预览与兜底率分母（D-20261110-01，Task-06） ----------------

def test_effective_dst_dir_three_layers_and_flat():
    """预览目标路径 = unit_dst_dir(有效根, actress, dst_name)；单点钉对齐 planner。"""
    u = {**make_unit("一乃あおい/ABC-1"), "actress": "一乃あおい", "dst_name": "ABC-1",
         "dst_dir": r"D:\媒体库\科幻\一乃あおい\ABC-1"}
    m = vm.PlanViewModel([u])
    assert m.effective_dst_dir(u) == r"D:\媒体库\科幻\一乃あおい\ABC-1"
    m.set_output_root(r"E:\out")
    assert m.effective_dst_dir(u) == r"E:\out\科幻\一乃あおい\ABC-1"
    flat = {**make_unit("Flat"), "actress": None, "dst_name": "Flat",
            "dst_dir": r"D:\媒体库\科幻\Flat"}
    m2 = vm.PlanViewModel([flat])
    assert m2.effective_dst_dir(flat) == r"D:\媒体库\科幻\Flat"     # 扁平回归钉
    m2.set_output_root(r"E:\out")
    assert m2.effective_dst_dir(flat) == r"E:\out\科幻\Flat"
    assert vm.unit_dst_dir is planner.unit_dst_dir   # 与 session 单点钉同款


def test_stats_fallback_ratio_excludes_composite():
    """viewmodel 兜底率分母对齐 planner：total − composite（C9 轮遗留口径分裂修正）。"""
    comp = make_unit("Comp", level="composite", status=planner.ST_BATCH,
                     lib="兜底库", default_selected=False, genres=())
    fb = make_unit("Unknown", level="fallback", conf="low", lib="兜底库",
                   default_selected=False, genres=("西部",))
    model = vm.PlanViewModel([comp, fb])
    st = model.stats()
    assert st["total"] == 2
    assert st["composite"] == 1
    assert st["fallback_ratio"] == 1.0   # 分母 1（2−1）而非 2


def test_multi_version_gate_requires_override():
    """ST_MULTI 多版本单元：无人工改判不得执行，改判后解锁（2026-11-12 反馈）。"""
    u = make_unit("G 多版本", level="title", status=planner.ST_MULTI,
                  lib="兜底库", default_selected=False, genres=())
    model = vm.PlanViewModel([u])
    model.checked.add(u["id"])
    assert u["id"] in {x["id"] for x in model.checked_not_ready()}
    assert model.can_apply() is False
    assert model._executable(u) is False
    model.set_override(u["id"], "科幻")
    assert model._executable(u) is True
    assert model.checked_not_ready() == []
    assert model.can_apply() is True


# ---------------- 不可执行 toast 点名真实原因（2026-11-12 反馈） ----------------

def test_blocked_toast_names_unlockable_units():
    """改判可解：点名单元+真实原因+改判指引，不再笼统称「冲突/残留」。"""
    u1 = make_unit("A 片", level="title", status=planner.ST_MULTI,
                   lib="兜底库", default_selected=False, genres=())
    msg = vm.blocked_toast([u1])
    assert msg == "不可执行：《A 片》多版本需确认——请在详情面板改判指定目标库"
    assert "冲突/残留" not in msg


def test_blocked_toast_mixed_and_fold():
    """混合原因给双指引；超过 2 个折叠为「等 N 部」；硬阻断只给处理指引。"""
    u1 = make_unit("A 片", level="title", status=planner.ST_MULTI,
                   lib="兜底库", default_selected=False, genres=())
    u2 = make_unit("B 片", level="composite", status=planner.ST_BATCH,
                   lib="兜底库", default_selected=False, genres=())
    u3 = make_unit("C 片", level="rule", status=planner.ST_CONFLICT,
                   lib="兜底库", default_selected=False, genres=())
    u4 = make_unit("D 片", level="rule", status=planner.ST_INCOMPLETE,
                   lib="兜底库", default_selected=False, genres=())
    msg = vm.blocked_toast([u1, u2, u3, u4])
    assert msg.startswith("有 4 部不可执行：")
    assert "《A 片》多版本需确认" in msg and "《B 片》整目录待改判" in msg
    assert "等 4 部" in msg
    assert "可改判的请在详情面板指定目标库" in msg and "取消勾选" in msg
    hard = vm.blocked_toast([u3])
    assert hard == "不可执行：《C 片》同名冲突——请先处理或取消勾选"


def test_unlock_statuses_single_point():
    """架构钉：改判解锁白名单收敛于 planner.UNLOCKABLE_STATUSES（v0.6.1 评审记账项）。"""
    import app.core.jobs as jobs_mod

    for src in (Path(jobs_mod.__file__).read_text(encoding="utf-8"),
                Path(vm.__file__).read_text(encoding="utf-8")):
        assert "in (ST_BATCH, ST_MULTI)" not in src      # 散点裸元组清零
        assert "UNLOCKABLE_STATUSES" in src

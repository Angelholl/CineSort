"""计划页视图模型：选择集 / 筛选 / 改判 / 汇总，纯逻辑、零 Qt 导入。

把全部决策逻辑推出 UI 层（D-20261102-02 验收协议第 1 条）：本模块必须能在
不创建任何 QApplication 的前提下被穷举单测，Qt 层只做渲染与事件转发。

字段口径对齐 app/core/planner.py 的真实 unit 结构（不要凭直觉假想）：
- `default_selected`：默认勾选由 planner 决定（READY 且规则级 / 自学习且中置信），
  本模块只照单全收，不得自行重算默认勾选策略；
- `confidence`：`"high" | "medium" | "low"` 字符串，不是数值；
- 状态文案统一取 planner.STATUS_LABELS，不得在此另造一套。
"""
from __future__ import annotations

from pathlib import Path

from app.core.planner import (
    READY,
    ST_BATCH,
    STATUS_LABELS,
    session_dst_root,
    unit_dst_dir,
)

# 筛选键 → 语义；UI 的 chips 顺序即此顺序
FILTER_ALL = "all"
FILTER_READY = "ready"
FILTER_APPLIED = "applied"
FILTER_BLOCKED = "blocked"
LEVEL_FILTERS = ("rule", "plot", "learned", "title", "fallback", "composite")
FILTERS = (FILTER_ALL, FILTER_READY) + LEVEL_FILTERS + (FILTER_BLOCKED, FILTER_APPLIED)

# 判定等级 → (中文, 徽章键)。徽章配色见 theme.BADGE_COLORS：
# 「规则」是大多数，故意用中性色做底噪，绿色独占给「可执行」状态。
LEVEL_BADGES = {
    "rule": ("规则", "rule"),
    "plot": ("摘要预判", "plot"),
    "learned": ("自学习", "learned"),
    "title": ("标题预判", "plot"),   # 复用 plot 色值，不新增颜色常量
    "fallback": ("兜底", "fallback"),
    "composite": ("整目录", "rule"),  # 复用 rule 色值，不新增颜色常量
}

# 置信等级 → (中文, 着色键)。high 走正文强调，medium/low 逐级弱化。
CONFIDENCE_BADGES = {
    "high": ("高", "ok"),
    "medium": ("中", "plot"),
    "low": ("低", "fb"),
}


def level_badge(unit: dict) -> tuple[str, str]:
    return LEVEL_BADGES.get(unit.get("level", ""), ("未知", "dim"))


def status_badge(unit: dict) -> tuple[str, str]:
    status = unit.get("status", "")
    return STATUS_LABELS.get(status, status or "未知"), status


def confidence_badge(unit: dict) -> tuple[str, str]:
    conf = unit.get("confidence") or ""
    return CONFIDENCE_BADGES.get(conf, ("—", "dim"))


def human_size(nbytes: int) -> str:
    """体积可读化。必须有 TB 档：整库规模轻松破 1000 GB，只到 GB
    会写出「83708.4 GB」这种没法读的数字；也要有 KB 档，否则演示/小文件
    环境会显示「0 MB」。"""
    if nbytes <= 0:
        return "—"
    if nbytes >= 1024 ** 4:
        return f"{nbytes / 1024 ** 4:,.2f} TB"
    if nbytes >= 1024 ** 3:
        return f"{nbytes / 1024 ** 3:,.1f} GB"
    if nbytes >= 1024 ** 2:
        return f"{nbytes / 1024 ** 2:,.0f} MB"
    return f"{nbytes / 1024:,.1f} KB"


def card_tones(stats: dict) -> list[tuple[str, str, str]]:
    """统计卡片的 (数值文本, 标签, 着色键)。

    着色只给"有动作含义"的指标（Phase-0 目验 P1-2）；指标为 0 时一律降为
    正文色——红色 0 是空警讯（真数据核验备注）。
    """
    fallback_tone = "warn" if stats["fallback_ratio"] > 0.15 else "dim"
    rows = (
        (stats["total"], "影片单元", "dim"),
        (stats["ready"], "可执行", "ok"),
        (stats["rule"], "规则判定", "dim"),
        (stats["plot"], "摘要预判", "plot"),
        (stats["learned"], "自学习", "learned"),
        (stats["fallback"], "兜底", fallback_tone),
        (stats["blocked"], "需人工处理", "bad"),
    )
    return [(f"{v:,}", label, tone if v else "dim")
            for v, label, tone in rows]


class PlanViewModel:
    """一次扫描对应的计划视图状态。筛选/搜索切换不得破坏勾选与改判。"""

    def __init__(self, units: list[dict]):
        self._units: list[dict] = list(units)
        self._by_id: dict[str, dict] = {u["id"]: u for u in self._units}
        self.checked: set[str] = {
            u["id"] for u in self._units if u.get("default_selected")}
        self.overrides: dict[str, str] = {}
        self.filter: str = FILTER_ALL
        self.query: str = ""
        self.output_root: str | None = None   # 本次输出目录（会话级）
        self.group_by_category: bool = True   # 输出目录下按类别建子文件夹（D2 默认开）

    # ------------------------------------------------------------- 行视图

    def set_filter(self, name: str) -> None:
        if name not in FILTERS:
            raise ValueError(f"未知筛选：{name}")
        self.filter = name

    def set_query(self, text: str) -> None:
        self.query = text or ""

    def rows(self) -> list[dict]:
        """当前筛选+搜索下的可见行（保持计划顺序）。

        每次筛选/搜索变化都重建行列表；勾选与改判挂在 unit id 上，
        因此天然跨筛选存活——UI 层重建表格时不得自行维护选择集。
        """
        q = self.query.strip().casefold()
        out: list[dict] = []
        for u in self._units:
            if self.filter in (FILTER_READY, FILTER_APPLIED) and u["status"] != self.filter:
                continue
            elif self.filter == FILTER_BLOCKED:
                if u["status"] in (READY, "applied"):
                    continue
            elif self.filter in LEVEL_FILTERS and u["level"] != self.filter:
                continue
            if q:
                genres = u.get("genres") or ()
                hay = " ".join((u["label"], u["target_lib"], *genres))
                if q not in hay.casefold():
                    continue
            out.append(u)
        return out

    def unit(self, unit_id: str) -> dict | None:
        return self._by_id.get(unit_id)

    def stats(self) -> dict:
        """统计卡片数据（全量口径，不受筛选影响）。"""
        out = {"total": len(self._units), "ready": 0, "applied": 0, "blocked": 0,
               "rule": 0, "plot": 0, "learned": 0, "fallback": 0}
        for u in self._units:
            out[u["level"]] = out.get(u["level"], 0) + 1
            if u["status"] == READY:
                out["ready"] += 1
            elif u["status"] == "applied":
                out["applied"] += 1
            else:
                out["blocked"] += 1
        # 兜底率分母与 planner 口径对齐：排除复合单元（整目录不算分母）
        out["fallback_ratio"] = out["fallback"] / max(out["total"] - out.get("composite", 0), 1)
        return out

    # ------------------------------------------------------------- 选择集

    def set_checked(self, unit_id: str, on: bool) -> None:
        if unit_id in self._by_id:
            if on:
                self.checked.add(unit_id)
            else:
                self.checked.discard(unit_id)

    def toggle(self, unit_id: str) -> None:
        self.set_checked(unit_id, unit_id not in self.checked)

    def select_visible_ready(self) -> None:
        """「全选可执行」：只勾当前可见行里的 READY 单元。"""
        for u in self.rows():
            if u["status"] == READY:
                self.checked.add(u["id"])

    def select_all_visible(self) -> None:
        for u in self.rows():
            self.checked.add(u["id"])

    def clear_selection(self) -> None:
        self.checked.clear()

    def checked_ids(self) -> list[str]:
        """按计划顺序返回勾选 id（提交给 run_apply 的 ids）。"""
        return [u["id"] for u in self._units if u["id"] in self.checked]

    def checked_bytes(self) -> int:
        return sum(u["total_size"] for u in self._units if u["id"] in self.checked)

    def _executable(self, u: dict) -> bool:
        """单元是否可执行：READY 直接可执行；ST_BATCH（整目录）须人工改判解锁。"""
        if u["status"] == READY:
            return True
        return u["status"] == ST_BATCH and bool(self.overrides.get(u["id"]))

    def checked_not_ready(self) -> list[dict]:
        """勾选了但状态不可执行的单元——UI 应禁用执行并在详情区提示。"""
        return [u for u in self._units
                if u["id"] in self.checked and not self._executable(u)]

    def can_apply(self) -> bool:
        return bool(self.checked) and not self.checked_not_ready()

    # ------------------------------------------------------------- 改判

    def set_override(self, unit_id: str, lib: str | None) -> None:
        """lib 为 None / 空串表示撤销改判，回到规则判定的目标库。"""
        if unit_id not in self._by_id:
            return
        if lib:
            self.overrides[unit_id] = lib
        else:
            self.overrides.pop(unit_id, None)

    def effective_target_lib(self, unit: dict) -> str:
        return self.overrides.get(unit["id"]) or unit["target_lib"]

    def set_output_root(self, path: str | None) -> None:
        """本次输出目录（会话级）；None/空串 = 撤销，回到计划库路径。"""
        self.output_root = (path or "").strip() or None

    def effective_output_root(self, unit: dict) -> str | None:
        """该单元本次实际目标根；未设输出目录时 None（沿用计划库根）。
        类别 = 改判后的目标库名（effective_target_lib，含「兜底库」）。"""
        if not self.output_root:
            return None
        root = session_dst_root(self.output_root, self.effective_target_lib(unit),
                                self.group_by_category)
        return str(root)

    def effective_dst_dir(self, unit: dict) -> str:
        """该单元最终目标目录（含会话输出）。组合唯一真值 = planner.unit_dst_dir；
        dst_name 缺失时回退 dst_dir 尾段（兼容旧 demo 数据）。"""
        root = self.effective_output_root(unit) or unit["target_root"]
        name = unit.get("dst_name") or Path(unit["dst_dir"]).name
        return str(unit_dst_dir(root, unit.get("actress"), name))

    def overridden_ids(self) -> list[str]:
        return [u["id"] for u in self._units if u["id"] in self.overrides]

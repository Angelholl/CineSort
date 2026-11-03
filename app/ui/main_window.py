"""主窗壳：顶栏 + 标签页 + 快慢双 tick + 关窗守卫。

线程纪律（D-20261102-01）：
- 快 tick（300ms）只读 job.snapshot()（内存快照），绝不碰磁盘；
- 慢 tick（2s）才允许走 AppState 的磁盘读取（plan 缓存 / 会话清单 / 自学习）；
- 体检/扫描/搬运永远在 JobManager 的工作线程，UI 线程只发 start 与收快照。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..state import AppState
from . import theme
from .config_tab import ConfigTab
from .exec_tab import ExecTab
from .plan_tab import PlanTab

FAST_MS = 300
SLOW_MS = 2000


class MainWindow(QMainWindow):
    def __init__(self, state: AppState | None, demo_units: list[dict] | None = None,
                 config_path: Path | None = None):
        super().__init__()
        self.state = state
        self._demo_units = demo_units
        self.setWindowTitle(f"CineSort 影片归类器 v{__version__}")
        self.resize(1280, 800)
        self._build(config_path)
        self._last_running = False

        self._fast = QTimer(self)
        self._fast.setInterval(FAST_MS)
        self._fast.timeout.connect(self._fast_tick)
        if state is not None:
            self._fast.start()
        self._slow = QTimer(self)
        self._slow.setInterval(SLOW_MS)
        self._slow.timeout.connect(self._slow_tick)
        if state is not None:
            self._slow.start()

    # ------------------------------------------------------------ 界面构建

    def _build(self, config_path: Path | None) -> None:
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
        self.pill = QLabel("空闲")
        self.pill.setProperty("pill", "idle")
        hl.addWidget(self.pill)
        hl.addStretch(1)
        if config_path is not None:
            cfg = QLabel(f"配置：{config_path}")
            cfg.setObjectName("cfgPath")
            hl.addWidget(cfg)
        outer.addWidget(header)

        self.tabs = QTabWidget()
        self.plan_tab = PlanTab(self.state,
                                self._demo_units if self.state is None else None,
                                toast=self.toast)
        self.tabs.addTab(self.plan_tab, "① 分类计划")
        self.exec_tab = ExecTab(self.state, toast=self.toast)
        self.tabs.addTab(self.exec_tab, "② 执行 / 回滚")
        self.config_tab = ConfigTab(self.state, toast=self.toast)
        self.tabs.addTab(self.config_tab, "③ 配置")
        for name in ("④ 体检",):
            ph = QWidget()
            pl = QVBoxLayout(ph)
            tip = QLabel(f"{name} —— 下一张卡实现（Phase-0 门禁已过）")
            tip.setProperty("dim", True)
            tip.setAlignment(Qt.AlignCenter)
            pl.addWidget(tip)
            self.tabs.addTab(ph, name)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(18, 10, 18, 0)
        wl.addWidget(self.tabs)
        outer.addWidget(wrap, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("")

    # ------------------------------------------------------------ tick

    def _slow_tick(self) -> None:
        self.plan_tab.refresh()
        self.exec_tab.refresh_sessions()
        self.config_tab.refresh()

    def _fast_tick(self) -> None:
        snap = self.state.job_snapshot()
        self.plan_tab.on_job_tick(snap)
        self.exec_tab.on_job_tick(snap)
        running = bool(snap and snap["status"] == "running")
        if running:
            label = (snap.get("label") or "").strip()
            kind = snap.get("kind", "")
            text = f"任务中：{label or kind}"
            if snap.get("total"):
                text += f"（{snap.get('cur', 0)}/{snap['total']}）"
            self._set_pill(text, "run")
        else:
            self._set_pill("空闲", "idle")
        # 任务刚结束：立即全量刷新，不等慢 tick
        if self._last_running and not running:
            self.plan_tab.refresh(force=True)
        self._last_running = running

    def _set_pill(self, text: str, mode: str) -> None:
        if self.pill.text() == text and self.pill.property("pill") == mode:
            return
        self.pill.setText(text)
        self.pill.setProperty("pill", mode)
        self.pill.style().unpolish(self.pill)
        self.pill.style().polish(self.pill)

    def toast(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 5000)

    # ------------------------------------------------------------ 关窗守卫

    def closeEvent(self, event) -> None:
        snap = self.state.job_snapshot() if self.state else None
        if snap and snap["status"] == "running":
            ret = QMessageBox.question(
                self, "任务正在运行",
                "扫描 / 搬运 / 体检正在进行，此时退出可能留下半成品残留"
                "（.incomplete-*，之后可在体检页清理）。\n\n确定退出？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="cinesort", description="CineSort 影片归类器")
    parser.add_argument("--config", default=None, help="config.toml 路径")
    parser.add_argument("--demo", action="store_true", help="演示模式：假数据，不读磁盘配置")
    parser.add_argument("--rows", type=int, default=5000, help="演示模式行数")
    parser.add_argument("--scale", type=float, default=1.0, help="模拟系统缩放（1.5=150%%）")
    parser.add_argument("--screenshot", default=None)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--tab", type=int, default=0, help="启动后选中的标签页索引")
    args = parser.parse_args(argv)

    if args.scale != 1.0:
        import os
        os.environ["QT_SCALE_FACTOR"] = str(args.scale)

    # DPI：Qt 6 默认已是 PER_MONITOR_AWARE_V2，自己抢先设置会被系统拒绝并喷警告。
    app = QApplication(sys.argv[:1])
    theme.apply_theme(app)

    from ..paths import default_config_path
    if args.demo:
        from .demo_data import fake_units
        state, units, cfg_path = None, fake_units(args.rows), None
    else:
        cfg_path = Path(args.config).resolve() if args.config else default_config_path()
        if not cfg_path.exists():
            from ..paths import resource_root
            example = resource_root() / "config.example.toml"
            if example.exists():
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg_path.write_text(example.read_text(encoding="utf-8"),
                                    encoding="utf-8")
        state, units = AppState(cfg_path), None

    win = MainWindow(state, demo_units=units, config_path=cfg_path)
    win.show()

    if args.screenshot:
        out = Path(args.screenshot)
        out.parent.mkdir(parents=True, exist_ok=True)

        def shoot() -> None:
            # 回调内的异常会被 Qt 吞掉且不退出事件循环——表现为静默挂死，
            # 必须自己兜住并显式退出。
            try:
                if args.tab:
                    win.tabs.setCurrentIndex(args.tab)
                app.processEvents()
                if not win.grab().save(str(out)):
                    raise RuntimeError(f"截图保存失败：{out}")
                print(f"screenshot -> {out}", flush=True)
                app.exit(0)
            except BaseException:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                app.exit(1)

        QTimer.singleShot(800, shoot)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

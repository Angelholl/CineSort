# C2 — 操作下沉到 AppState + 移植无 HTTP 的全链路集成测试

## 一、背景与根因

C1 已把 `AppState` 抽到 `app/state.py`（提交 197391f）。但真正的**操作入口**目前仍卡在 HTTP 层：`app/server.py` 的 `route_post`（第 43-80 行）里写着"启动扫描 / 启动执行 / 启动回滚 / 回滚预览 / 体检 / 清理 staging / 遗忘自学习 / 保存配置 / 取消"这 9 个操作，`undo_preview`（第 23-40 行）也是 server 模块级函数。

根因：PySide6 原生 GUI 要触发这些操作，就必须 `from app.server import route_post`——又回到"GUI 依赖 HTTP 模块"的错误层次（与 D-20261102-01 施工纪律第 4 条冲突）。同时，网页版最终要删除（用户拍板），删除后 `tests/test_api.py` 的 5 个用例——本项目**唯一**"扫描→执行→自学习→回滚"磁盘级全链路证据——会随之消失。

本卡做两件事：① 把 9 个操作从 `route_post` 下沉为 `AppState` 方法，`route_post` 退化为薄转发（HTTP 行为完全不变）；② 新建 `tests/test_flow.py`，把 `test_api.py` 的 5 个用例**逐一对应**移植成不依赖 HTTP 的 core 级集成测试，直接驱动 `AppState` + `JobManager`。这样后续删除网页版时，全链路证据已经先落地，测试基线不降。

本卡**不删除** server.py / static/index.html / test_api.py（删除在后续卡）。

## 二、改动文件与改法（只允许改这 3 个文件）

### 1. 改 `app/state.py`：新增操作方法与 `undo_preview`

把 `app/server.py:23-40` 的 `undo_preview` 函数体**原样搬入** `AppState.undo_preview(self, fname)` 作为方法（语义完全不变：非法会话名抛 `ValueError("非法的会话文件名")`，文件不存在抛 `ValueError("会话日志不存在")`，返回 `{"ops": [...], "file": fname}`，ops 元素字段为 `unit_id/kind/src_dir/dst_dir/state`，state 取值 `ok|skip_target_missing|skip_src_exists`）。

再新增下列方法，**签名必须逐字照抄**（后续 GUI 卡按这些签名调用）：

```python
    def start_scan(self) -> dict:
        """启动扫描任务。BusyError 由 JobManager 抛出，不在此吞掉。"""
        self.jobs.start("scan", lambda job: jobs_mod.run_scan(self, job))
        return {"ok": True}

    def start_apply(self, ids: list[str], acks: set[str],
                    overrides: dict[str, str]) -> dict:
        self.jobs.start("apply", lambda job: jobs_mod.run_apply(
            self, job, ids, acks, overrides))
        return {"ok": True}

    def start_undo(self, fname: str) -> dict:
        self.jobs.start("undo", lambda job: jobs_mod.run_undo(self, job, fname))
        return {"ok": True}

    def preflight_items(self, ids: set[str] | None = None) -> list[dict]:
        cfg = load_config(self.config_path)
        return preflight.run_preflight(cfg, self.plan(), selected_ids=ids or None)

    def cleanup_staging(self) -> int:
        return preflight.cleanup_staging(load_config(self.config_path))

    def learned_forget(self, key: str, lib: str) -> list[dict]:
        learned_store.forget(self.runtime_dir(), key, lib)
        return learned_store.items(learned_store.load(self.runtime_dir()))

    def save_config(self, data: dict) -> dict:
        new_cfg = save_config_dict(self.config_path, data)
        self.invalidate_plan()          # 配置已变，旧计划按哈希自动过期
        return describe(new_cfg)

    def cancel_job(self) -> bool:
        return self.jobs.cancel()

    def job_snapshot(self) -> dict | None:
        return self.jobs.job.snapshot() if self.jobs.job else None
```

要点：
- `preflight_items` / `cleanup_staging` 是**同步**方法（本卡不改变行为），但在 docstring 里写明一行注释：`# 注意：内部含 tasklist 子进程（最长 15s）与磁盘遍历，调用方不得在 UI 线程直接调用（D-20261102-01 纪律 1）`。后台化在后续卡做，本卡不动。
- state.py 需要补的 import：`from .core import preflight`、`from .core.config import save_config_dict`（其余已有）。`jobs_mod` 已有。
- 这些方法**不得**捕获 `BusyError` / `ConfigError` / `ValueError`——异常语义由调用方（HTTP 层或 GUI 层）决定，吞异常会破坏现有 409 语义。

### 2. 改 `app/server.py`：`route_post` 退化为薄转发

- 删除模块级 `undo_preview` 函数（第 23-40 行）。**先执行 `grep -rn "undo_preview" --include=*.py .` 核对**：若除 `server.py` 与 `tests/` 之外还有别的模块 import 它，则保留一个一行转发 `def undo_preview(state, fname): return state.undo_preview(fname)`；否则彻底删除。
- `route_post` 各分支改为调用对应方法，**HTTP 请求/响应结构与状态码语义一字不改**：
  - `/api/scan` → `state.start_scan()`
  - `/api/apply` → 保留原有 `ids`/`acks`/`overrides` 的 str 归一化，再 `state.start_apply(ids, acks, overrides)`
  - `/api/undo` → `state.start_undo(str(body.get("file") or ""))`
  - `/api/undo_preview` → `state.undo_preview(str(body.get("file") or ""))`
  - `/api/preflight` → `{"items": state.preflight_items({str(x) for x in (body.get("ids") or [])} or None)}`
  - `/api/cleanup_staging` → `{"removed": state.cleanup_staging()}`
  - `/api/learned_forget` → `{"learned": state.learned_forget(str(body.get("key") or ""), str(body.get("lib") or ""))}`
  - `/api/config` → `{"valid": True, "config": state.save_config(body)}`
  - `/api/cancel` → `{"cancelled": state.cancel_job()}`
- `GET /api/state` 里的 `"job"` 字段改用 `state.job_snapshot()`（返回值必须与原先逐字段一致）。
- 因搬移而变成未使用的 import 可删；仍被 handler/GET 路由使用的必须留。

### 3. 新建 `tests/test_flow.py`（先红后绿的回归测试）

**先写这个文件跑出红，再改 state.py/server.py 转绿。** 文件 docstring：`"""全链路集成测试（不经 HTTP）：扫描 → 执行 → 自学习 → 回滚，兼作冒烟。与 tests/test_api.py 逐一对应，是删除网页版后的唯一全链路证据，不得删减。"""`

公共夹具与等待器（照抄）：

```python
import json
import time

import pytest

from app.core import jobs as jobs_mod
from app.core.config import ConfigError, load_config
from app.core.journal import list_sessions
from app.state import AppState
from conftest import build_env, make_movie


def wait_job(state, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = state.jobs.job
        if job and job.status != "running":
            return job.snapshot()
        time.sleep(0.15)
    raise AssertionError("任务超时未结束")


@pytest.fixture()
def state(tmp_path):
    cfg_path = build_env(tmp_path)
    cfg = load_config(cfg_path)
    src = cfg.source_root
    make_movie(src, "Space War (2021)", title="Space War", genres=("科幻",),
               plot="太空宇宙飞船大战", tmdb="21")
    make_movie(src, "Gun Fight (2022)", title="Gun Fight", genres=("动作",),
               plot="特工枪战", tmdb="22")
    return AppState(cfg_path)
```

必须包含 5 个用例，前 4 个与 `tests/test_api.py` 的 4 个非页面用例**一一对应、断言强度不得降低**：

1. `test_scan_apply_undo_flow` ↔ `test_api.py::test_scan_apply_undo_flow`：`state.start_scan()` → `wait_job` → `assert st["status"] == "done"`；`plan = state.plan()`，断言 `plan["stats"]["ready"] == 2`、`units["Space War (2021)"]["target_lib"] == "科幻"`、`units["Gun Fight (2022)"]["target_lib"] == "动作"`；`state.start_apply(list(units), {"jellyfin_running"}, {})` → `wait_job` → `result["moved"] == 2 and result["failed"] == 0`；**磁盘断言原样保留**（两部影片已进对应库目录、源目录已消失）；`state.plan()["stats"]["by_status"]["applied"] == 2`（验证 `invalidate_plan` 生效）；`runtime/learned.json` 里 `{"科幻","动作"} <= libs_voted`；`list_sessions(state.runtime_dir()/"journals")[0]["file"]` 取会话 → `state.undo_preview(sess)` 断言 `len(ops)==2 and all(o["state"]=="ok")` → `state.start_undo(sess)` → `wait_job` → `result["restored"] == 2` → 磁盘断言原目录回来、库目录消失。
2. `test_apply_blocked_on_source_drift` ↔ 同名用例：扫描后对第一个单元 `make_movie(env.source_root, unit["id"], title="x", genres=("科幻",), tmdb="99")` 造漂移，`start_apply` 后 `wait_job` 断言 `status == "failed"` 且 `"未执行任何操作" in error`。
3. `test_config_save_validate_and_reject` ↔ 同名用例：`state.state_snapshot()["config"]["strategy"]` 可读；`state.save_config({...改 strategy=priority...})` 后再读回为 `priority`；构造 `source_root` 指向不存在目录的 dict，`pytest.raises(ConfigError)` 调 `state.save_config(bad)`，且随后读回的 `source_root` 仍是原值（未被部分写入破坏）。
4. `test_undo_preview_rejects_bad_name` ↔ 同名用例：`pytest.raises(ValueError)` 调 `state.undo_preview("../../evil.jsonl")`（原 HTTP 版断言 409，此处断言抛 ValueError，语义等价）。
5. `test_busy_error_on_concurrent_jobs`（新增，桌面 GUI 直接相关）：`state.start_scan()` 后**不等待**，立刻再调 `state.start_apply(...)`，断言 `pytest.raises(jobs_mod.BusyError)`；随后 `wait_job` 收尾。这条钉住"任务运行中重复触发必须报错"——桌面版按钮双击的前提。

注意：夹具需要 `cfg` 的 `source_root`/`libraries` 做磁盘断言，可在用例内 `load_config(state.config_path)` 重新取，或让 fixture 返回 `(state, cfg)` 元组——**选后者**，写成 `state_and_cfg` fixture 亦可，但 5 个用例都要能拿到 cfg。

## 三、验收命令

以下命令均在项目根目录执行：

```bash
python -m pytest tests/test_flow.py -q      # 定向：5 用例先红后绿
python -m pytest tests/test_api.py -q       # HTTP 层 5 用例必须一行未改仍通过
python -m pytest tests -q                   # 全量：93 + 5 = 98 passed，零失败
python -m ruff check app/state.py app/server.py tests/test_flow.py
grep -n "undo_preview\|route_post" app/server.py app/state.py
```

基线红线：全量用例数 **≥ 98**（C1 后基线 93，只增不减）；`tests/test_api.py` 必须**一行未改**且 5 个用例全通过（HTTP 行为不变的证据）。

## 四、约束

- 只允许改动 `app/state.py`、`app/server.py`，新建 `tests/test_flow.py`；`app/core/**`、`app/static/**`、`tests/` 其他文件、打包脚本、README 一律不碰。
- **不得改动 `app/core/jobs.py`**：`run_scan/run_apply/run_undo` 的 `state` 形参是 duck-typed，只用到 `state.config_path` 与 `state.invalidate_plan()`，`AppState` 天然满足，无需适配。
- 不得改动任何 HTTP 路由的路径、请求体字段、响应结构、状态码语义（`ConfigError`→200 带 error、`BusyError`/`ValueError`→409、其余→500）。
- 不得在 AppState 新方法里吞异常（`BusyError`/`ConfigError`/`ValueError` 必须原样上抛）。
- 不得删除 `app/server.py`、`app/static/index.html`、`tests/test_api.py`（删除在后续卡）。
- 只 commit 不 push；提交信息 Conventional 前缀 + 中文描述，正文 `verify:` 写明 pytest 结果与用例总数（含 test_api.py 未改动仍通过），`Refs: D-20261102-01`。
- 永不 `git add -A`（只显式 add 本卡 3 个文件路径）；永不 `--no-verify`。
- 卡外问题即停回报，不得顺手修。

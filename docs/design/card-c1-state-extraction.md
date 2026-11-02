# C1 — AppState 抽层到 app/state.py（去 HTTP 依赖的地基）

## 一、背景与根因

项目正在从"stdlib http.server + 浏览器单页 GUI"改造为 PySide6 原生桌面窗口（见 `docs/decision-log.md` D-20261102-01）。

根因：共享状态类 `AppState` 目前定义在 `app/server.py:25-77`，而 `app/server.py` 第 8 行 `from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer`。桌面 UI 层若要复用 AppState，就必须 `from app.server import AppState` —— 依赖方向变成"原生 GUI 依赖 HTTP 服务模块"，这是错的层次。本卡把 AppState 抽到无 HTTP 依赖的 `app/state.py`，为后续所有 UI 卡扫清依赖障碍。

本卡**不删除** server.py，**不改动**任何 core 业务逻辑，**不改动** `tests/test_api.py` 一行。

## 二、改动文件与改法（只允许改这 4 个文件）

### 1. 新建 `app/state.py`
把 `app/server.py` 中 `class AppState`（当前位于 `app/server.py:25-77`，从 `class AppState:` 到 `state_snapshot` 的 `return` 结束，含其 docstring）**逐行原样搬移**到 `app/state.py`，不改任何行为、不改方法名、不改返回结构。文件头 docstring 写：`"""共享应用状态：配置路径 / 计划缓存 / 任务管理器。与任何 UI 形态（HTTP 或原生窗口）无关。"""`

`app/state.py` 的 import 只允许这些（AppState 用到的全部）：
```python
from __future__ import annotations

import threading
import tomllib
from pathlib import Path

from . import __version__
from .core import jobs as jobs_mod
from .core import learned as learned_store
from .core.config import ConfigError, describe, load_config, raw_describe
from .core.journal import list_sessions
from .core.planner import load_plan, plan_digest
```
注意：搬移后 `preflight`、`done_entries`、`is_valid_session_name`、`save_config_dict`、`resource_root`、`json`、`logging` 这些 AppState 本体不用的 import **不得**带进 state.py（它们留在 server.py）。

### 2. 改 `app/server.py`
- 删除 `class AppState` 整块定义。
- 在原位置改为 re-export，保证外部 `from app.server import AppState` 继续有效（`tests/test_api.py` 依赖它）：
  ```python
  from .state import AppState  # re-export：保持既有 import 路径有效
  ```
- 其余代码（路由、handler、`create_server`、`undo_preview` 等）一律不动。若某 import 因 AppState 搬走而变成未使用，可删；但凡仍被 server.py 其他部分使用的必须保留。

### 3. 改 `app/main_gui.py`
第 17 行 `from .server import AppState, create_server` 改为两行：
```python
from .server import create_server
from .state import AppState
```

### 4. 新建 `tests/test_state.py`（先红后绿的回归测试）
必须包含以下两个用例，**先写测试跑红，再改代码跑绿**：

```python
"""AppState 必须能在完全不触碰 http.server 的前提下被导入与使用。"""
from __future__ import annotations

import subprocess
import sys

from app.state import AppState


def test_importing_state_does_not_pull_http_server():
    """架构守卫：app.state 及其全部下游依赖不得引入 http.server。
    桌面 GUI 依赖 app.state，若它把 http.server 拖进来则层次划分失效。"""
    code = (
        "import sys, app.state;"
        "bad=[m for m in sys.modules if m.startswith('http')];"
        "print(bad);sys.exit(1 if bad else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"app.state 拖进了 HTTP 模块：{proc.stdout}{proc.stderr}"


def test_state_snapshot_shape(tmp_path):
    """AppState 搬到新模块后，快照字段必须与迁移前完全一致。"""
    state = AppState(tmp_path / "config.toml")
    snap = state.state_snapshot()
    assert set(snap) == {"ok", "version", "config_path", "config", "config_error",
                         "plan", "plan_digest", "job", "sessions", "learned"}
    assert snap["ok"] is True
    assert snap["plan"] is None and snap["job"] is None
    assert snap["config_path"] == str(tmp_path / "config.toml")
    # 配置缺失时 config_error 非空、config 走示例兜底或 None，不得抛异常
    assert snap["config_error"]

    assert state.plan() is None
    state.invalidate_plan()
    assert state.runtime_dir() == tmp_path / "runtime"
```

另外加一条防回归断言：`from app.server import AppState as S2` 后 `assert S2 is AppState`（证明 re-export 未断）。

## 三、验收命令

以下命令均在项目根目录执行：

```bash
python -m pytest tests/test_state.py -q     # 定向：新增 2 用例通过
python -m pytest tests -q                   # 全量：91 + 2 = 93 passed，零失败
python -c "import ast,sys; src=open('app/state.py',encoding='utf-8').read(); tree=ast.parse(src); bad=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module and n.module.startswith('http')]+[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names if a.name.startswith('http')]; sys.exit(1 if bad else print('state.py 无 http 依赖 OK'))"
python -c "from app.server import AppState; from app.state import AppState as A; assert AppState is A; print('re-export OK')"
```

基线红线：`tests` 全量用例数必须 **≥ 93**（原 91 只增不减），且 `tests/test_api.py` 的 5 个用例必须**一行未改**地通过。

## 四、约束

- 只允许新建/修改上述 4 个文件；`app/core/**`、`app/static/**`、`tests/` 其他文件、打包脚本、README 一律不碰。
- 不得改动 AppState 任何方法的签名、返回值结构、异常语义（含 `config_describe` 的示例兜底分支）。
- 不得删除 `app/server.py` 或 `app/static/index.html`（删除在后续卡）。
- 只 commit 不 push；提交信息用 Conventional 前缀 + 中文描述，正文带 `verify:` 行写明 pytest 结果与用例数，`Refs: D-20261102-01`。
- 永不使用 `git add -A`（只显式 `git add` 本卡 4 个文件路径）；永不使用 `--no-verify`。
- 卡外发现的问题：立即停止并在回报中说明，不得顺手修。

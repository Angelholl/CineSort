"""API 集成测试：扫描 → 执行 → 回滚 全链路（兼作冒烟）。"""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from app.server import AppState, create_server
from conftest import build_env, make_movie


class Client:
    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}"

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(self, path, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.base + path, data=data,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))


@pytest.fixture()
def env(tmp_path):
    cfg_path = build_env(tmp_path)
    from app.core.config import load_config
    cfg = load_config(cfg_path)
    src = cfg.source_root
    make_movie(src, "Space War (2021)", title="Space War", genres=("科幻",),
               plot="太空宇宙飞船大战", tmdb="21")
    make_movie(src, "Gun Fight (2022)", title="Gun Fight", genres=("动作",),
               plot="特工枪战", tmdb="22")
    return cfg


@pytest.fixture()
def server(env):
    state = AppState(env.path)
    httpd = create_server(state, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield Client(httpd.server_address[1]), state
    httpd.shutdown()


def wait_job(client, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get("/api/state")
        job = st.get("job")
        if job and job["status"] != "running":
            return st
        time.sleep(0.15)
    raise AssertionError("任务超时未结束")


def test_gui_page_served(server):
    client, _ = server
    with urllib.request.urlopen(client.base + "/", timeout=10) as r:
        assert "CineSort 影片归类器" in r.read().decode("utf-8")


def test_scan_apply_undo_flow(server, env):
    client, _ = server
    client.post("/api/scan", {})
    st = wait_job(client)
    assert st["job"]["status"] == "done", st["job"]["log"]
    plan = st["plan"]
    assert plan["stats"]["ready"] == 2
    units = {u["id"]: u for u in plan["units"]}
    assert units["Space War (2021)"]["target_lib"] == "科幻"
    assert units["Gun Fight (2022)"]["target_lib"] == "动作"

    client.post("/api/apply", {"ids": list(units),
                               "acks": ["jellyfin_running"], "overrides": {}})
    st = wait_job(client)
    assert st["job"]["status"] == "done", st["job"]["log"]
    r = st["job"]["result"]
    assert r["moved"] == 2 and r["failed"] == 0
    assert (env.libraries["科幻"].path / "Space War (2021)").is_dir()
    assert (env.libraries["动作"].path / "Gun Fight (2022)").is_dir()
    assert not (env.source_root / "Space War (2021)").exists()
    assert client.get("/api/state")["plan"]["stats"]["by_status"]["applied"] == 2
    # 执行结果应沉淀为自学习映射（D-20261101-03）
    learned = json.loads((env.path.parent / "runtime" / "learned.json")
                         .read_text(encoding="utf-8"))
    libs_voted = {lib for e in learned["entries"].values() for lib in e["libs"]}
    assert {"科幻", "动作"} <= libs_voted
    assert "learned" in client.get("/api/state")

    sess = client.get("/api/state")["sessions"][0]["file"]
    prev = client.post("/api/undo_preview", {"file": sess})
    assert len(prev["ops"]) == 2 and all(o["state"] == "ok" for o in prev["ops"])
    client.post("/api/undo", {"file": sess})
    st = wait_job(client)
    assert st["job"]["status"] == "done", st["job"]["log"]
    assert st["job"]["result"]["restored"] == 2
    assert (env.source_root / "Space War (2021)").is_dir()
    assert not (env.libraries["科幻"].path / "Space War (2021)").exists()


def test_apply_blocked_on_source_drift(server, env):
    client, _ = server
    client.post("/api/scan", {})
    st = wait_job(client)
    unit = st["plan"]["units"][0]
    make_movie(env.source_root, unit["id"], title="x", genres=("科幻",), tmdb="99")
    client.post("/api/apply", {"ids": [unit["id"]], "acks": [], "overrides": {}})
    st = wait_job(client)
    assert st["job"]["status"] == "failed"
    assert "未执行任何操作" in st["job"]["error"]


def test_config_save_validate_and_reject(server, env):
    client, _ = server
    st = client.get("/api/config")
    assert st["valid"] is True
    cfg = st["config"]
    cfg["strategy"] = "priority"
    assert client.post("/api/config", cfg)["valid"] is True
    assert client.get("/api/config")["config"]["strategy"] == "priority"
    bad = dict(client.get("/api/config")["config"])
    bad["source_root"] = str(env.path.parent / "nope")
    assert "error" in client.post("/api/config", bad)
    assert client.get("/api/config")["config"]["source_root"] == str(env.source_root)


def test_undo_preview_rejects_bad_name(server):
    client, _ = server
    with pytest.raises(urllib.error.HTTPError) as ei:
        client.post("/api/undo_preview", {"file": "../../evil.jsonl"})
    assert ei.value.code == 409

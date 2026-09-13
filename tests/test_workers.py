"""เทสต์การยืมการ์ดจอ: จับคู่เครื่อง, สัญญาณชีพ, และการจ่ายงาน."""


def test_pair_code_format(user_client):
    body = user_client.post("/api/v1/workers/pair", json={"label": "Colab T4"}).json()
    code = body["pair_code"]
    assert len(code) == 9 and code[4] == "-"
    assert body["expires_in"] == 900


def test_register_worker_shows_up_online(user_client, worker):
    body = user_client.get("/api/v1/workers").json()
    assert body["summary"]["online"] == 1
    entry = body["workers"][0]
    assert entry["gpu_name"] == "Tesla T4"
    assert entry["gpu_vram_mb"] == 15360
    assert entry["status"] == "idle"


def test_pair_code_is_single_use(user_client):
    code = user_client.post("/api/v1/workers/pair", json={}).json()["pair_code"]
    first = user_client.post("/api/v1/worker/register", json={"pair_code": code})
    assert first.status_code == 200
    second = user_client.post("/api/v1/worker/register", json={"pair_code": code})
    assert second.status_code == 400


def test_bad_pair_code_rejected(client):
    resp = client.post("/api/v1/worker/register", json={"pair_code": "NOPE-NOPE"})
    assert resp.status_code == 400


def test_worker_token_required(client):
    assert client.post("/api/v1/worker/heartbeat", json={}).status_code == 401
    assert client.post(
        "/api/v1/worker/heartbeat", json={}, headers={"Authorization": "Bearer spk_fake"}
    ).status_code == 401


def test_heartbeat_updates_telemetry(user_client, worker):
    resp = user_client.post(
        "/api/v1/worker/heartbeat",
        json={"gpu_used_mb": 4096, "gpu_util": 73, "status": "busy", "drive_mounted": True},
        headers=worker["headers"],
    )
    assert resp.json()["ok"] is True
    entry = user_client.get("/api/v1/workers").json()["workers"][0]
    assert entry["gpu_used_mb"] == 4096
    assert entry["gpu_util"] == 73
    assert entry["drive_mounted"] is True
    assert entry["vram_pct"] == 26.7


def test_revoked_worker_loses_access(user_client, worker):
    assert user_client.delete(f"/api/v1/workers/{worker['id']}").json()["ok"] is True
    resp = user_client.post("/api/v1/worker/heartbeat", json={}, headers=worker["headers"])
    assert resp.status_code == 401


def test_connect_snippet_contains_pair_code(user_client):
    code = user_client.post("/api/v1/workers/pair", json={}).json()["pair_code"]
    body = user_client.get("/api/v1/connect-snippet", params={"pair_code": code}).json()
    assert code in body["one_liner"]
    assert "bootstrap.py" in body["one_liner"]


def test_bootstrap_script_is_served(client):
    resp = client.get("/colab/bootstrap.py")
    assert resp.status_code == 200
    assert "Spice Worker" in resp.text

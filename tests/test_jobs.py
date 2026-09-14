"""เทสต์คิวงาน: ส่งงาน → เครื่องรับงาน → รายงานผล."""


def _submit(client, **overrides):
    payload = {"model": "qwen2.5-7b-instruct", "prompt": "สรุปเรื่องนี้ให้หน่อย", **overrides}
    return client.post("/api/v1/jobs", json=payload)


def test_model_catalog_flags_runnable(user_client, worker):
    body = user_client.get("/api/v1/models").json()
    assert body["best_vram_mb"] == 15360
    by_id = {item["id"]: item for item in body["models"]}
    assert by_id["qwen2.5-7b-instruct"]["runnable_now"] is True   # 15GB พอดีกับ T4
    assert by_id["typhoon2-3b-instruct"]["runnable_now"] is True


def test_unknown_model_rejected(user_client):
    assert _submit(user_client, model="ไม่มีจริง").status_code == 400


def test_empty_prompt_rejected(user_client):
    assert _submit(user_client, prompt="", drive_input="").status_code == 400


def test_submit_warns_when_no_worker_online(user_client):
    body = _submit(user_client).json()
    assert body["status"] == "queued"
    assert body["online_workers"] == 0
    assert "Colab" in body["hint"]


def test_full_job_lifecycle(user_client, worker):
    job_id = _submit(user_client, title="งานทดสอบ").json()["job_id"]

    leased = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()
    assert leased["job"]["id"] == job_id
    assert leased["job"]["payload"]["repo"] == "Qwen/Qwen2.5-7B-Instruct"
    assert leased["job"]["payload"]["quantize"] == "4bit"

    user_client.post(
        f"/api/v1/worker/jobs/{job_id}/progress",
        json={"progress": 0.5, "message": "กำลังโหลดโมเดล"},
        headers=worker["headers"],
    )
    mid = user_client.get(f"/api/v1/jobs/{job_id}").json()
    assert mid["job"]["status"] == "running"
    assert mid["job"]["progress"] == 0.5
    assert any("โหลดโมเดล" in event["message"] for event in mid["log"])
    assert mid["worker"]["gpu_name"] == "Tesla T4"

    user_client.post(
        f"/api/v1/worker/jobs/{job_id}/complete",
        json={"result": "นี่คือคำตอบ", "meta": {"tokens": 42}},
        headers=worker["headers"],
    )
    done = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert done["status"] == "done"
    assert done["result"] == "นี่คือคำตอบ"
    assert done["progress"] == 1.0

    entry = user_client.get("/api/v1/workers").json()["workers"][0]
    assert entry["jobs_done"] == 1
    assert entry["status"] == "idle"


def test_job_failure_is_recorded(user_client, worker):
    job_id = _submit(user_client).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(
        f"/api/v1/worker/jobs/{job_id}/complete",
        json={"error": "ValueError: คำสั่งในงานนี้ไม่ถูกต้อง"},
        headers=worker["headers"],
    )
    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["status"] == "failed"
    assert "ไม่ถูกต้อง" in job["error"]


def test_queue_respects_priority(user_client, worker):
    low = _submit(user_client, prompt="งานไม่ด่วน", priority=9).json()["job_id"]
    high = _submit(user_client, prompt="งานด่วนมาก", priority=1).json()["job_id"]
    first = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()
    assert first["job"]["id"] == high
    second = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()
    assert second["job"]["id"] == low


def test_job_is_leased_only_once(user_client, worker):
    _submit(user_client)
    assert user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()["job"]
    assert user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()["job"] is None


def test_worker_cannot_touch_foreign_job(user_client, worker, client):
    job_id = _submit(user_client).json()["job_id"]
    resp = user_client.post(
        f"/api/v1/worker/jobs/{job_id}/complete",
        json={"result": "ขโมยงาน"},
        headers=worker["headers"],
    )
    assert resp.status_code == 404      # ยังไม่ได้ lease จึงแตะไม่ได้


def test_cancel_removes_job_from_queue(user_client, worker):
    job_id = _submit(user_client).json()["job_id"]
    assert user_client.post(f"/api/v1/jobs/{job_id}/cancel").json()["status"] == "cancelled"
    assert user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()["job"] is None


def test_stats_and_listing(user_client, worker):
    _submit(user_client)
    stats = user_client.get("/api/v1/stats").json()
    assert stats["jobs_total"] == 1
    assert stats["jobs_queued"] == 1
    assert stats["workers_online"] == 1
    listing = user_client.get("/api/v1/jobs").json()
    assert listing["counts"]["queued"] == 1
    assert "result" not in listing["jobs"][0]      # รายการย่อไม่ต้องแบกผลลัพธ์ยาว ๆ


def test_users_cannot_see_each_others_jobs(user_client, client):
    job_id = _submit(user_client).json()["job_id"]
    user_client.post("/auth/logout")
    client.post("/auth/dev", params={"email": "other@spice.local", "name": "Other"})
    assert client.get(f"/api/v1/jobs/{job_id}").status_code == 404
    assert client.get("/api/v1/jobs").json()["jobs"] == []


def test_silent_worker_loses_its_job_back_to_the_queue(user_client, worker):
    """เครื่องที่เงียบหายเกินเวลา ต้องคืนงานกลับเข้าคิวให้เครื่องอื่นทำต่อ."""
    import time as _time

    from server import db
    from server.routers import workers as workers_module

    job_id = _submit(user_client).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])

    # แกล้งให้สัญญาณล่าสุดเก่าเกินกำหนด
    db.execute(
        "UPDATE jobs SET progress_at = ?, started_at = ? WHERE id = ?",
        (_time.time() - workers_module.LEASE_TIMEOUT - 60,
         _time.time() - workers_module.LEASE_TIMEOUT - 60, job_id),
    )
    workers_module.reap_stale_jobs()
    assert user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]["status"] == "queued"


def test_slow_job_with_recent_progress_is_not_reaped(user_client, worker):
    """งานที่ยังส่งความคืบหน้าอยู่ (เช่นกำลังโหลดโมเดลนาน ๆ) ต้องไม่ถูกโยนกลับคิว."""
    import time as _time

    from server import db
    from server.routers import workers as workers_module

    job_id = _submit(user_client).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])

    # เริ่มมานานมากแล้ว แต่เพิ่งรายงานความคืบหน้าเมื่อครู่นี้
    db.execute(
        "UPDATE jobs SET started_at = ? WHERE id = ?",
        (_time.time() - workers_module.LEASE_TIMEOUT * 3, job_id),
    )
    user_client.post(
        f"/api/v1/worker/jobs/{job_id}/progress",
        json={"progress": 0.3, "message": "กำลังดาวน์โหลดน้ำหนักโมเดล"},
        headers=worker["headers"],
    )
    workers_module.reap_stale_jobs()
    assert user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]["status"] == "running"

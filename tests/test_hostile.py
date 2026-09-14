"""เทสต์แบบแกล้งระบบ — จำลองสถานการณ์ที่เครื่องทำตัวไม่ดีหรือชนกันเอง.

เทสต์พวกนี้เขียนขึ้นเพื่อ *หาบั๊ก* โดยเฉพาะ ไม่ใช่เพื่อยืนยันว่าของเดิมถูก.
"""

from server import db


def _submit(client, **overrides):
    payload = {"model": "typhoon2-3b-instruct", "prompt": "งานทดสอบ", **overrides}
    return client.post("/api/v1/jobs", json=payload).json()["job_id"]


# ── เครื่องส่งผลซ้ำสองรอบ ────────────────────────────────────
def test_sending_the_result_twice_does_not_double_count(user_client, worker):
    """เน็ตกระตุกแล้ว worker ยิง complete ซ้ำ ต้องไม่นับงานเป็นสองงาน."""
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    for _ in range(3):
        user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                         json={"result": "คำตอบที่ถูกต้อง."}, headers=worker["headers"])

    entry = user_client.get("/api/v1/workers").json()["workers"][0]
    assert entry["jobs_done"] == 1


def test_sending_the_result_twice_does_not_duplicate_the_chain(user_client, worker):
    """ยิงซ้ำบนงานที่มีลูกโซ่ ต้องไม่สร้างขั้นถัดไปซ้ำสองงาน."""
    user_client.post("/api/v1/jobs", json={
        "model": "auto", "prompt": "ถอดเสียงแล้วสรุป",
        "drive_input": "gdrive:audio/meeting.m4a",
    })
    job = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()["job"]
    for _ in range(3):
        user_client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                         json={"result": "บทถอดเสียง."}, headers=worker["headers"])

    jobs = user_client.get("/api/v1/jobs").json()["jobs"]
    assert len(jobs) == 2, f"ควรมี 2 งาน (ถอดเสียง + สรุป) แต่ได้ {len(jobs)}"


def test_a_late_result_cannot_revive_a_cancelled_job(user_client, worker):
    """ผู้ใช้กดยกเลิกแล้ว ผลที่ตามมาทีหลังต้องไม่ทำให้งานกลับมาเป็นสำเร็จ."""
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/jobs/{job_id}/cancel")

    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"result": "มาช้าไปแล้ว."}, headers=worker["headers"])

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["status"] == "cancelled"


def test_a_late_reply_cannot_be_added_to_a_conversation_twice(user_client, worker):
    thread_id = user_client.post("/api/v1/threads", json={"model": "typhoon2-3b-instruct"}).json()["id"]
    user_client.post(f"/api/v1/threads/{thread_id}/messages", json={"content": "สวัสดี"})
    job = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()["job"]
    for _ in range(3):
        user_client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                         json={"result": "สวัสดีครับ."}, headers=worker["headers"])

    messages = user_client.get(f"/api/v1/threads/{thread_id}").json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]


# ── ผลลัพธ์ที่ไม่ใช่ข้อความ ──────────────────────────────────
def test_an_image_result_is_not_judged_by_text_rules(user_client, worker):
    """ภาพเป็น base64 ยาว ๆ ห้ามเอากฎตรวจข้อความไปตัดสินว่าวนซ้ำหรือถูกตัด."""
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "sdxl-turbo", "prompt": "วาดรูปแมว", "max_tokens": 64}).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])

    # base64 จริงมีรูปแบบซ้ำ ๆ และไม่จบด้วยเครื่องหมายวรรคตอนแน่นอน
    fake_png = "data:image/png;base64," + ("AAAA" * 400)
    resp = user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                            json={"result": fake_png, "meta": {"tokens": 64}},
                            headers=worker["headers"]).json()

    assert resp["status"] == "done", f"ภาพไม่ควรถูกสั่งทำใหม่ แต่ได้ {resp}"
    assert user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]["status"] == "done"


def test_a_transcript_is_not_judged_by_sentence_endings(user_client, worker):
    """บทถอดเสียงมักไม่จบด้วยจุด ไม่ควรถูกหาว่าโดนตัดกลางคัน."""
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "whisper-large-v3-turbo", "prompt": "ถอดเสียง",
        "drive_input": "gdrive:a.m4a", "max_tokens": 4096}).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    resp = user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                            json={"result": "เอ่อ แล้วก็ ประมาณนั้นแหละครับ",
                                  "meta": {"tokens": 4096}},
                            headers=worker["headers"]).json()
    assert resp["status"] == "done"


# ── โมเดลที่ถูกลบทิ้งไปแล้ว ──────────────────────────────────
def test_deleting_a_model_does_not_break_the_heartbeat(user_client, worker, monkeypatch):
    """เคยใช้โมเดลที่ลบไปแล้ว ตัวแนะนำโหลดรอต้องไม่ทำให้สัญญาณชีพพัง."""
    from server import scheduler

    # แกล้งใส่ประวัติการใช้โมเดลที่ไม่มีอยู่ในแค็ตตาล็อกแล้ว
    db.execute(
        """INSERT INTO jobs (id, user_id, kind, model, status, created_at, started_at, finished_at)
           VALUES ('job_ghost', ?, 'text', 'hf--โมเดลที่ถูกลบไปแล้ว', 'done', ?, ?, ?)""",
        (user_client.get("/api/v1/me").json()["id"], 1, 1, 2),
    )
    row = dict(db.query_one("SELECT * FROM workers WHERE id = ?", (worker["id"],)))
    assert scheduler.suggest_preload(row) is None        # ต้องข้ามไป ไม่ใช่ระเบิด

    resp = user_client.post("/api/v1/worker/heartbeat",
                            json={"status": "idle", "gpu_vram_mb": 15360},
                            headers=worker["headers"])
    assert resp.status_code == 200


def test_using_a_deleted_model_fails_cleanly(user_client, worker):
    job_id = _submit(user_client)
    db.execute("UPDATE jobs SET model = 'hf--หายไปแล้ว' WHERE id = ?", (job_id,))
    leased = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()
    # จะจ่ายงานหรือข้ามก็ได้ แต่ต้องไม่ทำให้ API พัง
    assert leased is not None


# ── สตรีมในจังหวะที่ไม่ควรสตรีมได้ ───────────────────────────
def test_streaming_into_a_finished_job_is_rejected(user_client, worker):
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"result": "จบแล้ว."}, headers=worker["headers"])

    user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                     json={"delta": "แทรกทีหลัง"}, headers=worker["headers"])
    assert user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]["result"] == "จบแล้ว."


def test_repairing_clears_the_text_streamed_so_far(user_client, worker):
    """ถ้าสั่งทำใหม่ ข้อความที่สตรีมไปแล้วต้องถูกล้าง ไม่ใช่เอามาต่อกัน."""
    job_id = _submit(user_client, max_tokens=128)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                     json={"delta": "ข้อความรอบแรกที่ถูกตัด"}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"result": "", "meta": {"tokens": 128}}, headers=worker["headers"])

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["status"] == "queued"
    assert job["result"] == "", "ต้องล้างข้อความเดิมก่อนรันรอบใหม่"


# ── ข้อมูลนำเข้าที่ไม่น่าไว้ใจ ───────────────────────────────
def test_a_huge_batch_is_capped(user_client):
    body = user_client.post("/api/v1/batches", json={
        "prompt": "ทำ {{item}}", "items": [str(index) for index in range(500)],
        "model": "typhoon2-3b-instruct"}).json()
    assert body["total"] <= 200


def test_an_empty_message_is_rejected(user_client):
    thread_id = user_client.post("/api/v1/threads", json={}).json()["id"]
    assert user_client.post(f"/api/v1/threads/{thread_id}/messages",
                            json={"content": "   "}).status_code in (400, 422)


# ── การแยกข้อมูลระหว่างผู้ใช้และระหว่างเครื่อง ────────────────
def _second_worker(client, name="เครื่องที่สอง"):
    code = client.post("/api/v1/workers/pair", json={}).json()["pair_code"]
    data = client.post("/api/v1/worker/register", json={
        "pair_code": code, "name": name, "gpu_name": "Tesla T4",
        "gpu_vram_mb": 15360, "capabilities": ["text", "image", "audio", "embedding"],
    }).json()
    return {"id": data["worker_id"],
            "headers": {"Authorization": f"Bearer {data['worker_token']}"}}


def test_a_worker_cannot_finish_a_job_given_to_another_machine(user_client, worker):
    other = _second_worker(user_client)
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])

    resp = user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                            json={"result": "ขโมยงาน"}, headers=other["headers"])
    assert resp.status_code == 404
    assert user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]["status"] == "running"


def test_a_worker_cannot_stream_into_another_machines_job(user_client, worker):
    other = _second_worker(user_client)
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    assert user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                            json={"delta": "แทรก"}, headers=other["headers"]).status_code == 404


def test_batches_are_private(user_client, client):
    batch_id = user_client.post("/api/v1/batches", json={
        "prompt": "ทำ {{item}}", "items": ["ก"], "model": "typhoon2-3b-instruct",
    }).json()["batch_id"]

    user_client.post("/auth/logout")
    client.post("/auth/dev", params={"email": "nosy@spice.local"})
    assert client.get(f"/api/v1/batches/{batch_id}").status_code == 404
    assert client.get(f"/api/v1/batches/{batch_id}/export").status_code == 404


def _model_owned_by_someone_else(model_id: str) -> None:
    """สร้างผู้ใช้อีกคนจริง ๆ แล้วให้เขาเป็นเจ้าของโมเดลตัวนี้."""
    import time as _time

    from server import db as database

    database.execute(
        """INSERT INTO users (email, name, role, created_at, last_login_at)
           VALUES ('owner@elsewhere.local', 'คนอื่น', 'member', ?, ?)
           ON CONFLICT(email) DO NOTHING""",
        (_time.time(), _time.time()),
    )
    other_id = database.query_one(
        "SELECT id FROM users WHERE email = 'owner@elsewhere.local'")["id"]
    database.execute(
        """INSERT INTO custom_models (id, user_id, repo, label, kind, quantize,
                                      vram_mb, params_b, added_at)
           VALUES (?, ?, 'someone/private-model', 'ส่วนตัว', 'text', 'fp16', 4000, 3, 1)""",
        (model_id, other_id),
    )


def test_you_cannot_chat_with_a_model_you_do_not_own(user_client):
    """โมเดลที่คนอื่นเพิ่มไว้ ต้องใช้ในบทสนทนาของเราไม่ได้."""
    _model_owned_by_someone_else("hf--ของคนอื่น")
    thread_id = user_client.post("/api/v1/threads", json={}).json()["id"]
    resp = user_client.post(f"/api/v1/threads/{thread_id}/messages",
                            json={"content": "ทดสอบ", "model": "hf--ของคนอื่น"})
    assert resp.status_code == 400


def test_you_cannot_batch_with_a_model_you_do_not_own(user_client):
    _model_owned_by_someone_else("hf--ของคนอื่น2")
    resp = user_client.post("/api/v1/batches", json={
        "prompt": "ทำ {{item}}", "items": ["ก"], "model": "hf--ของคนอื่น2"})
    assert resp.status_code == 400


def test_cancelling_someone_elses_job_is_refused(user_client, client):
    job_id = _submit(user_client)
    user_client.post("/auth/logout")
    client.post("/auth/dev", params={"email": "nosy2@spice.local"})
    assert client.post(f"/api/v1/jobs/{job_id}/cancel").status_code == 404

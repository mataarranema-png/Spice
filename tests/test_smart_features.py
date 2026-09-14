"""เทสต์ความสามารถอัจฉริยะชุดใหม่: แคช ซ่อมผลลัพธ์ บทสนทนา งานชุด สตรีม โหลดรอ."""

import pytest

from server import cache, db


def _run(client, worker, result="คำตอบที่ถูกต้องครบถ้วน.", meta=None):
    """ให้เครื่องรับงานถัดไปแล้วทำจนเสร็จ."""
    job = client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()["job"]
    assert job is not None, "ควรมีงานให้ทำ"
    client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                json={"result": result, "meta": meta or {}}, headers=worker["headers"])
    return job


# ═══ 1. แคชผลลัพธ์ ═══════════════════════════════════════════
def test_asking_the_same_thing_twice_skips_the_gpu(user_client, worker):
    body = {"model": "typhoon2-3b-instruct", "prompt": "แปลคำว่า hello เป็นไทย",
            "temperature": 0.1, "max_tokens": 256}
    first = user_client.post("/api/v1/jobs", json=body).json()
    assert first["status"] == "queued"
    _run(user_client, worker, result="สวัสดี")

    second = user_client.post("/api/v1/jobs", json=body).json()
    assert second["status"] == "done" and second["from_cache"] is True
    job = user_client.get(f"/api/v1/jobs/{second['job_id']}").json()["job"]
    assert job["status"] == "done"            # เสร็จทันทีโดยไม่ต้องเข้าคิว
    assert job["from_cache"] is True
    assert job["result"] == "สวัสดี"
    assert user_client.post("/api/v1/worker/lease", json={},
                            headers=worker["headers"]).json()["job"] is None


def test_creative_work_is_never_cached(user_client, worker):
    body = {"model": "typhoon2-3b-instruct", "prompt": "แต่งกลอนเกี่ยวกับทะเล",
            "temperature": 0.95}
    user_client.post("/api/v1/jobs", json=body)
    _run(user_client, worker, result="กลอนบทที่หนึ่ง")

    second = user_client.post("/api/v1/jobs", json=body).json()
    assert user_client.get(
        f"/api/v1/jobs/{second['job_id']}").json()["job"]["from_cache"] is False


def test_changing_any_setting_makes_it_a_different_question(user_client, worker):
    base = {"model": "typhoon2-3b-instruct", "prompt": "สรุปสั้น ๆ", "temperature": 0.1}
    user_client.post("/api/v1/jobs", json={**base, "max_tokens": 256})
    _run(user_client, worker, result="สรุปแบบสั้น")

    longer = user_client.post("/api/v1/jobs", json={**base, "max_tokens": 2048}).json()
    assert user_client.get(
        f"/api/v1/jobs/{longer['job_id']}").json()["job"]["from_cache"] is False


def test_cache_is_private_to_each_user(user_client, client, worker):
    body = {"model": "typhoon2-3b-instruct", "prompt": "ความลับ", "temperature": 0.1}
    user_client.post("/api/v1/jobs", json=body)
    _run(user_client, worker, result="คำตอบลับ")

    user_client.post("/auth/logout")
    client.post("/auth/dev", params={"email": "other@spice.local"})
    assert cache.lookup(2, cache.fingerprint("typhoon2-3b-instruct", body)) is None


def test_cache_savings_show_up_in_stats(user_client, worker):
    body = {"model": "typhoon2-3b-instruct", "prompt": "คำถามซ้ำ", "temperature": 0.1}
    user_client.post("/api/v1/jobs", json=body)
    _run(user_client, worker, result="คำตอบ")
    user_client.post("/api/v1/jobs", json=body)

    stats = user_client.get("/api/v1/stats").json()["cache"]
    assert stats["entries"] == 1 and stats["hits"] == 1


# ═══ 2. ซ่อมผลลัพธ์ที่ใช้ไม่ได้ ═══════════════════════════════
def test_an_empty_answer_is_retried_automatically(user_client, worker):
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "typhoon2-3b-instruct", "prompt": "ช่วยตอบหน่อย"}).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    resp = user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                            json={"result": "   "}, headers=worker["headers"]).json()

    assert resp["status"] == "repairing" and resp["problem"] == "empty"
    detail = user_client.get(f"/api/v1/jobs/{job_id}").json()
    assert detail["job"]["status"] == "queued"          # กลับเข้าคิวเอง
    assert detail["job"]["repairs"][0]["problem"] == "empty"
    assert detail["job"]["payload"]["temperature"] >= 0.3


def test_a_truncated_answer_is_retried_with_more_room(user_client, worker):
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "typhoon2-3b-instruct", "prompt": "อธิบายยาว ๆ",
        "max_tokens": 256}).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"result": "เริ่มจากขั้นตอนแรกคือการเตรียม",
                           "meta": {"tokens": 256}}, headers=worker["headers"])

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["status"] == "queued"
    assert job["payload"]["max_tokens"] == 512


def test_a_good_answer_is_left_alone(user_client, worker):
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "typhoon2-3b-instruct", "prompt": "ทักทายหน่อย"}).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"result": "สวัสดีครับ ยินดีที่ได้รู้จัก."}, headers=worker["headers"])

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["status"] == "done" and job["repairs"] == []


def test_repairing_gives_up_after_a_few_tries(user_client, worker):
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "typhoon2-3b-instruct", "prompt": "ตอบหน่อย"}).json()["job_id"]
    for _ in range(4):
        leased = user_client.post("/api/v1/worker/lease", json={},
                                  headers=worker["headers"]).json()["job"]
        if leased is None:
            break
        user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                         json={"result": ""}, headers=worker["headers"])

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["status"] == "done"                 # ยอมจบ ไม่วนซ่อมไม่รู้จบ
    assert len(job["repairs"]) == 2


# ═══ 3. บทสนทนาต่อเนื่อง ═════════════════════════════════════
def test_a_conversation_remembers_what_was_said(user_client, worker):
    thread_id = user_client.post("/api/v1/threads", json={"model": "typhoon2-3b-instruct"}).json()["id"]

    user_client.post(f"/api/v1/threads/{thread_id}/messages",
                     json={"content": "ผมชื่อสมชาย"})
    _run(user_client, worker, result="สวัสดีครับคุณสมชาย")

    user_client.post(f"/api/v1/threads/{thread_id}/messages",
                     json={"content": "ผมชื่ออะไรนะ"})
    second = user_client.post("/api/v1/worker/lease", json={},
                              headers=worker["headers"]).json()["job"]

    # รอบที่สองต้องเห็นทั้งคำถามและคำตอบของรอบแรก
    conversation = second["payload"]["messages"]
    assert any("สมชาย" in item["content"] for item in conversation if item["role"] == "user")
    assert any(item["role"] == "assistant" for item in conversation)


def test_the_question_is_not_sent_to_the_model_twice(user_client, worker):
    """ข้อความของผู้ใช้ถูกบันทึกก่อนประกอบบริบท จึงต้องไม่ถูกเติมซ้ำอีกรอบ."""
    thread_id = user_client.post("/api/v1/threads", json={"model": "typhoon2-3b-instruct"}).json()["id"]
    user_client.post(f"/api/v1/threads/{thread_id}/messages", json={"content": "คำถามเดียว"})

    job = user_client.post("/api/v1/worker/lease", json={},
                           headers=worker["headers"]).json()["job"]
    conversation = job["payload"]["messages"]
    assert [item["content"] for item in conversation].count("คำถามเดียว") == 1
    assert len(conversation) == 1


def test_replies_are_saved_into_the_conversation(user_client, worker):
    thread_id = user_client.post("/api/v1/threads", json={}).json()["id"]
    user_client.post(f"/api/v1/threads/{thread_id}/messages", json={"content": "สวัสดี"})
    _run(user_client, worker, result="สวัสดีครับ มีอะไรให้ช่วยไหม")

    detail = user_client.get(f"/api/v1/threads/{thread_id}").json()
    roles = [message["role"] for message in detail["messages"]]
    assert roles == ["user", "assistant"]
    assert detail["messages"][1]["content"] == "สวัสดีครับ มีอะไรให้ช่วยไหม"


def test_the_conversation_is_named_after_the_first_message(user_client):
    thread_id = user_client.post("/api/v1/threads", json={}).json()["id"]
    user_client.post(f"/api/v1/threads/{thread_id}/messages",
                     json={"content": "ช่วยวางแผนทริปเชียงใหม่หน่อย"})
    threads = user_client.get("/api/v1/threads").json()["threads"]
    assert "เชียงใหม่" in threads[0]["title"]


def test_old_turns_are_dropped_when_the_context_fills_up(user_client):
    from server.routers.threads import build_history

    thread_id = user_client.post("/api/v1/threads", json={}).json()["id"]
    for index in range(30):
        db.execute(
            "INSERT INTO messages (thread_id, role, content, created_at) VALUES (?,?,?,?)",
            (thread_id, "user" if index % 2 == 0 else "assistant", "ก" * 2000, index),
        )
    db.execute(
        "INSERT INTO messages (thread_id, role, content, created_at) VALUES (?,?,?,?)",
        (thread_id, "user", "คำถามล่าสุด", 999),
    )
    conversation = build_history(thread_id, "")
    assert conversation[-1]["content"] == "คำถามล่าสุด"      # รอบล่าสุดต้องอยู่เสมอ
    assert len(conversation) < 31                            # ของเก่าถูกตัดทิ้ง


def test_conversations_are_private(user_client, client):
    thread_id = user_client.post("/api/v1/threads", json={}).json()["id"]
    user_client.post("/auth/logout")
    client.post("/auth/dev", params={"email": "nosy@spice.local"})
    assert client.get(f"/api/v1/threads/{thread_id}").status_code == 404


def test_auto_mode_picks_a_model_for_each_message(user_client, worker):
    thread_id = user_client.post("/api/v1/threads", json={"model": "auto"}).json()["id"]
    body = user_client.post(f"/api/v1/threads/{thread_id}/messages",
                            json={"content": "เขียนฟังก์ชัน Python หาเลขเฉพาะ"}).json()
    assert body["model"] == "qwen2.5-7b-instruct"      # งานโค้ด → โมเดลตัวใหญ่
    assert body["reason"]


# ═══ 4. งานชุด ═══════════════════════════════════════════════
def test_one_request_fans_out_into_many_jobs(user_client, worker):
    body = user_client.post("/api/v1/batches", json={
        "prompt": "สรุปหัวข้อนี้ให้หน่อย: {{item}}",
        "items": ["เศรษฐกิจไทย", "พลังงานสะอาด", "การศึกษา"],
        "model": "typhoon2-3b-instruct",
    }).json()

    assert body["total"] == 3 and len(body["job_ids"]) == 3
    jobs = user_client.get("/api/v1/jobs").json()["jobs"]
    assert len(jobs) == 3
    titles = [job["title"] for job in jobs]
    assert any("1/3" in title for title in titles)


def test_each_item_gets_its_own_prompt(user_client, worker):
    user_client.post("/api/v1/batches", json={
        "prompt": "แปลเป็นอังกฤษ: {{item}}",
        "items": ["สวัสดี", "ขอบคุณ"], "model": "typhoon2-3b-instruct",
    })
    first = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()["job"]
    assert "สวัสดี" in first["payload"]["prompt"]
    assert "{{item}}" not in first["payload"]["prompt"]


def test_batch_progress_is_tracked(user_client, worker):
    batch_id = user_client.post("/api/v1/batches", json={
        "prompt": "ทำ: {{item}}", "items": ["ก", "ข"], "model": "typhoon2-3b-instruct",
    }).json()["batch_id"]

    assert user_client.get(f"/api/v1/batches/{batch_id}").json()["batch"]["progress"] == 0
    _run(user_client, worker, result="เสร็จอันแรก.")
    body = user_client.get(f"/api/v1/batches/{batch_id}").json()["batch"]
    assert body["done"] == 1 and body["progress"] == 0.5 and body["finished"] is False

    _run(user_client, worker, result="เสร็จอันที่สอง.")
    assert user_client.get(f"/api/v1/batches/{batch_id}").json()["batch"]["finished"] is True


def test_batch_results_can_be_exported_together(user_client, worker):
    batch_id = user_client.post("/api/v1/batches", json={
        "prompt": "สรุป: {{item}}", "items": ["ก", "ข"], "model": "typhoon2-3b-instruct",
    }).json()["batch_id"]
    _run(user_client, worker, result="ผลของ ก.")
    _run(user_client, worker, result="ผลของ ข.")

    export = user_client.get(f"/api/v1/batches/{batch_id}/export").json()
    assert export["count"] == 2
    assert "ผลของ ก." in export["markdown"] and "ผลของ ข." in export["markdown"]


def test_batch_needs_a_placeholder(user_client):
    resp = user_client.post("/api/v1/batches", json={
        "prompt": "ไม่มีตัวแทนรายการ", "items": ["ก"], "model": "typhoon2-3b-instruct"})
    assert resp.status_code == 400 and "{{item}}" in resp.json()["detail"]


def test_batch_needs_items(user_client):
    assert user_client.post("/api/v1/batches", json={
        "prompt": "ทำ {{item}}", "items": []}).status_code == 400


def test_batch_eta_accounts_for_parallel_workers(user_client, worker):
    """มีหลายเครื่องช่วยกัน เวลารวมต้องสั้นลง ไม่ใช่บวกกันตรง ๆ."""
    single = user_client.post("/api/v1/batches", json={
        "prompt": "ทำ {{item}}", "items": [str(index) for index in range(6)],
        "model": "typhoon2-3b-instruct"}).json()

    code = user_client.post("/api/v1/workers/pair", json={}).json()["pair_code"]
    extra = user_client.post("/api/v1/worker/register", json={
        "pair_code": code, "name": "เครื่องที่สอง", "gpu_name": "Tesla T4",
        "gpu_vram_mb": 15360, "capabilities": ["text"]}).json()
    user_client.post("/api/v1/worker/heartbeat", json={"gpu_vram_mb": 15360},
                     headers={"Authorization": f"Bearer {extra['worker_token']}"})

    double = user_client.post("/api/v1/batches", json={
        "prompt": "ทำ {{item}}", "items": [str(index) for index in range(6)],
        "model": "typhoon2-3b-instruct"}).json()
    assert double["workers"] == 2
    assert double["eta_seconds"] < single["eta_seconds"]


# ═══ 5. สตรีมคำตอบทีละท่อน ═══════════════════════════════════
def test_partial_text_shows_up_before_the_job_finishes(user_client, worker):
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "typhoon2-3b-instruct", "prompt": "เล่าเรื่องยาว ๆ"}).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])

    for piece in ["กาลครั้งหนึ่ง", "นานมาแล้ว ", "มีชายคนหนึ่ง"]:
        resp = user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                                json={"delta": piece, "progress": 0.6},
                                headers=worker["headers"])
        assert resp.json()["ok"] is True

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["status"] == "running"
    assert job["result"] == "กาลครั้งหนึ่งนานมาแล้ว มีชายคนหนึ่ง"
    assert job["progress"] == 0.6


def test_finishing_without_a_body_keeps_the_streamed_text(user_client, worker):
    """เครื่องที่สตรีมครบแล้วส่ง result ว่างมาตอนจบได้ ต้องไม่ทำให้คำตอบหาย."""
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "typhoon2-3b-instruct", "prompt": "เล่าหน่อย"}).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                     json={"delta": "เรื่องเล่าที่จบแล้ว."}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"result": ""}, headers=worker["headers"])

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["status"] == "done" and job["result"] == "เรื่องเล่าที่จบแล้ว."


def test_a_worker_cannot_stream_into_someone_elses_job(user_client, worker):
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "typhoon2-3b-instruct", "prompt": "งาน"}).json()["job_id"]
    assert user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                            json={"delta": "แทรก"}, headers=worker["headers"]).status_code == 404


# ═══ 6. โหลดโมเดลรอไว้ตอนว่าง ════════════════════════════════
def test_an_idle_worker_is_told_what_to_preload(user_client, worker):
    from server import scheduler

    # สร้างประวัติการใช้งานให้ระบบรู้ว่าชอบโมเดลไหน
    for _ in range(3):
        user_client.post("/api/v1/jobs", json={
            "model": "typhoon2-3b-instruct", "prompt": "งานเก่า", "temperature": 0.9})
        _run(user_client, worker, result="เสร็จแล้ว.")

    row = dict(db.query_one("SELECT * FROM workers WHERE id = ?", (worker["id"],)))
    hint = scheduler.suggest_preload(row)
    assert hint["model"] == "typhoon2-3b-instruct"
    assert hint["repo"] and hint["reason"]


def test_no_preload_while_there_is_work_to_do(user_client, worker):
    from server import scheduler

    user_client.post("/api/v1/jobs", json={
        "model": "typhoon2-3b-instruct", "prompt": "งานที่รออยู่"})
    row = dict(db.query_one("SELECT * FROM workers WHERE id = ?", (worker["id"],)))
    assert scheduler.suggest_preload(row) is None


def test_no_preload_when_the_favourite_is_already_loaded(user_client, worker):
    from server import scheduler

    user_client.post("/api/v1/jobs", json={
        "model": "typhoon2-3b-instruct", "prompt": "งานเก่า", "temperature": 0.9})
    _run(user_client, worker, result="เสร็จ.")
    user_client.post("/api/v1/worker/heartbeat",
                     json={"warm_models": ["typhoon2-3b-instruct"], "gpu_vram_mb": 15360},
                     headers=worker["headers"])

    row = dict(db.query_one("SELECT * FROM workers WHERE id = ?", (worker["id"],)))
    assert scheduler.suggest_preload(row) is None


def test_heartbeat_carries_the_preload_hint(user_client, worker):
    user_client.post("/api/v1/jobs", json={
        "model": "typhoon2-3b-instruct", "prompt": "งานเก่า", "temperature": 0.9})
    _run(user_client, worker, result="เสร็จ.")

    reply = user_client.post("/api/v1/worker/heartbeat",
                             json={"status": "idle", "gpu_vram_mb": 15360},
                             headers=worker["headers"]).json()
    assert reply["preload"]["model"] == "typhoon2-3b-instruct"


def test_a_small_worker_is_never_told_to_preload_a_big_model(user_client, worker):
    from server import scheduler

    user_client.post("/api/v1/jobs", json={
        "model": "qwen2.5-7b-instruct", "prompt": "งานหนัก", "temperature": 0.9})
    _run(user_client, worker, result="เสร็จ.")

    small = dict(db.query_one("SELECT * FROM workers WHERE id = ?", (worker["id"],)))
    small["gpu_vram_mb"] = 6000
    assert scheduler.suggest_preload(small) is None

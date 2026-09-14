"""เทสต์ความสามารถอัจฉริยะชุดใหม่: แคช ซ่อมผลลัพธ์ บทสนทนา งานชุด สตรีม โหลดรอ."""

import time

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


# ═══ 7. โหวตหาคำตอบที่น่าเชื่อถือ ════════════════════════════
def test_voting_asks_the_same_question_several_times(user_client, worker):
    body = user_client.post("/api/v1/votes", json={
        "prompt": "เมืองหลวงของไทยคือที่ไหน", "model": "typhoon2-3b-instruct", "votes": 3,
    }).json()
    assert body["votes"] == 3 and len(body["job_ids"]) == 3

    temps = []
    for _ in range(3):
        job = user_client.post("/api/v1/worker/lease", json={},
                               headers=worker["headers"]).json()["job"]
        temps.append(job["payload"]["temperature"])
        user_client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                         json={"result": "กรุงเทพมหานคร"}, headers=worker["headers"])
    assert len(set(temps)) == 3, "แต่ละรอบต้องตั้งค่าต่างกัน ไม่งั้นโหวตไม่มีความหมาย"


def test_voting_picks_the_majority_answer(user_client, worker):
    group = user_client.post("/api/v1/votes", json={
        "prompt": "เมืองหลวงของไทย", "model": "typhoon2-3b-instruct", "votes": 3,
    }).json()["vote_group"]

    for answer in ["กรุงเทพมหานคร", "กรุงเทพมหานคร", "เชียงใหม่"]:
        job = user_client.post("/api/v1/worker/lease", json={},
                               headers=worker["headers"]).json()["job"]
        user_client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                         json={"result": answer}, headers=worker["headers"])

    verdict = user_client.get(f"/api/v1/votes/{group}").json()
    assert verdict["verdict"]["answer"] == "กรุงเทพมหานคร"
    assert verdict["verdict"]["confidence"] > 0.6
    assert verdict["finished"] == 3


def test_voting_is_honest_when_answers_disagree(user_client, worker):
    group = user_client.post("/api/v1/votes", json={
        "prompt": "เดาเลขหน่อย", "model": "typhoon2-3b-instruct", "votes": 3,
    }).json()["vote_group"]
    for answer in ["เจ็ด", "สิบสอง", "ยี่สิบ"]:
        job = user_client.post("/api/v1/worker/lease", json={},
                               headers=worker["headers"]).json()["job"]
        user_client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                         json={"result": answer}, headers=worker["headers"])

    body = user_client.get(f"/api/v1/votes/{group}").json()
    assert "ควรตรวจสอบเอง" in body["summary"]


def test_voting_never_answers_from_cache(user_client, worker):
    """ถ้าดึงจากแคช ทุกรอบจะได้คำตอบเดียวกัน แล้วการโหวตก็ไร้ความหมาย."""
    user_client.post("/api/v1/jobs", json={
        "model": "typhoon2-3b-instruct", "prompt": "คำถามโหวต", "temperature": 0.1})
    job = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()["job"]
    user_client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                     json={"result": "คำตอบเดิม"}, headers=worker["headers"])

    body = user_client.post("/api/v1/votes", json={
        "prompt": "คำถามโหวต", "model": "typhoon2-3b-instruct", "votes": 2}).json()
    for job_id in body["job_ids"]:
        assert user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]["from_cache"] is False


def test_votes_are_private(user_client, client):
    group = user_client.post("/api/v1/votes", json={
        "prompt": "ความลับ", "model": "typhoon2-3b-instruct", "votes": 2}).json()["vote_group"]
    user_client.post("/auth/logout")
    client.post("/auth/dev", params={"email": "nosy3@spice.local"})
    assert client.get(f"/api/v1/votes/{group}").status_code == 404


# ═══ 8. งานตั้งเวลา ══════════════════════════════════════════
def test_a_schedule_computes_its_next_run(user_client):
    body = user_client.post("/api/v1/schedules", json={
        "title": "สรุปข่าวเช้า", "prompt": "สรุปข่าวเทคโนโลยีวันนี้",
        "model": "typhoon2-3b-instruct", "every_minutes": 1440, "at_hour": 8,
    }).json()
    assert body["next_run_in_minutes"] > 0
    schedules = user_client.get("/api/v1/schedules").json()["schedules"]
    assert schedules[0]["title"] == "สรุปข่าวเช้า" and schedules[0]["enabled"] is True


def test_running_a_schedule_creates_a_real_job(user_client, worker):
    schedule_id = user_client.post("/api/v1/schedules", json={
        "prompt": "สรุปงานค้างทั้งหมด", "model": "typhoon2-3b-instruct",
    }).json()["id"]
    job_id = user_client.post(f"/api/v1/schedules/{schedule_id}/run").json()["job_id"]

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["title"].startswith("⏰")
    assert job["plan"]["scheduled"] is True

    after = user_client.get("/api/v1/schedules").json()["schedules"][0]
    assert after["runs"] == 1 and after["last_run_at"] > 0


def test_due_schedules_fire_automatically(user_client):
    from server.routers.smart import run_due_schedules

    schedule_id = user_client.post("/api/v1/schedules", json={
        "prompt": "งานที่ถึงเวลาแล้ว", "model": "typhoon2-3b-instruct",
    }).json()["id"]
    db.execute("UPDATE schedules SET next_run_at = ? WHERE id = ?", (1, schedule_id))

    assert run_due_schedules() == 1
    assert len(user_client.get("/api/v1/jobs").json()["jobs"]) == 1
    # ยิงแล้วต้องเลื่อนรอบถัดไปออกไป ไม่ใช่ยิงซ้ำไม่หยุด
    assert run_due_schedules() == 0


def test_a_disabled_schedule_does_not_fire(user_client):
    from server.routers.smart import run_due_schedules

    schedule_id = user_client.post("/api/v1/schedules", json={
        "prompt": "งานที่ปิดไว้", "model": "typhoon2-3b-instruct"}).json()["id"]
    user_client.post(f"/api/v1/schedules/{schedule_id}/toggle")
    db.execute("UPDATE schedules SET next_run_at = ? WHERE id = ?", (1, schedule_id))

    assert run_due_schedules() == 0
    assert user_client.get("/api/v1/jobs").json()["jobs"] == []


def test_one_broken_schedule_does_not_stop_the_others(user_client):
    from server.routers.smart import run_due_schedules

    good = user_client.post("/api/v1/schedules", json={
        "prompt": "งานที่ดี", "model": "typhoon2-3b-instruct"}).json()["id"]
    bad = user_client.post("/api/v1/schedules", json={
        "prompt": "งานที่พัง", "model": "typhoon2-3b-instruct"}).json()["id"]
    db.execute("UPDATE schedules SET next_run_at = 1 WHERE id IN (?, ?)", (good, bad))
    db.execute("UPDATE schedules SET model = 'โมเดลที่ไม่มีจริง' WHERE id = ?", (bad,))

    run_due_schedules()
    jobs = user_client.get("/api/v1/jobs").json()["jobs"]
    assert any("งานที่ดี" in job["title"] for job in jobs)


def test_schedules_are_private(user_client, client):
    schedule_id = user_client.post("/api/v1/schedules", json={
        "prompt": "ส่วนตัว", "model": "typhoon2-3b-instruct"}).json()["id"]
    user_client.post("/auth/logout")
    client.post("/auth/dev", params={"email": "nosy4@spice.local"})
    assert client.get("/api/v1/schedules").json()["schedules"] == []
    assert client.delete(f"/api/v1/schedules/{schedule_id}").status_code == 404


# ═══ 9. เครื่องที่พังบ่อยต้องถูกพัก ══════════════════════════
def test_a_worker_that_keeps_failing_gets_paused(user_client, worker):
    from server import scheduler

    for _ in range(3):
        user_client.post("/api/v1/jobs", json={
            "model": "typhoon2-3b-instruct", "prompt": "งาน"})
        job = user_client.post("/api/v1/worker/lease", json={},
                               headers=worker["headers"]).json()["job"]
        user_client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                         json={"error": "ไฟล์เสีย"}, headers=worker["headers"])

    entry = user_client.get("/api/v1/workers").json()["workers"][0]
    assert entry["quarantined"] is True and entry["status"] == "paused"
    assert entry["jobs_failed"] == 3

    # ระหว่างถูกพัก ต้องไม่ได้รับงานใหม่
    user_client.post("/api/v1/jobs", json={"model": "typhoon2-3b-instruct", "prompt": "งานใหม่"})
    assert user_client.post("/api/v1/worker/lease", json={},
                            headers=worker["headers"]).json()["job"] is None


def test_a_success_resets_the_failure_streak(user_client, worker):
    for outcome in [{"error": "พัง"}, {"error": "พัง"}, {"result": "สำเร็จแล้ว."}, {"error": "พัง"}]:
        user_client.post("/api/v1/jobs", json={
            "model": "typhoon2-3b-instruct", "prompt": "งาน"})
        job = user_client.post("/api/v1/worker/lease", json={},
                               headers=worker["headers"]).json()["job"]
        user_client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                         json=outcome, headers=worker["headers"])

    entry = user_client.get("/api/v1/workers").json()["workers"][0]
    assert entry["quarantined"] is False       # สำเร็จคั่นกลาง จึงยังไม่ครบ 3 ติด
    assert entry["success_rate"] == 0.25


def test_a_paused_worker_is_not_asked_to_preload(user_client, worker):
    from server import scheduler

    db.execute("UPDATE workers SET quarantined_until = ? WHERE id = ?",
               (time.time() + 600, worker["id"]))
    row = dict(db.query_one("SELECT * FROM workers WHERE id = ?", (worker["id"],)))
    assert scheduler.suggest_preload(row) is None


# ═══ 10. สถิติเชิงลึก ════════════════════════════════════════
def test_insights_show_where_the_gpu_time_went(user_client, worker):
    user_client.post("/api/v1/jobs", json={"model": "typhoon2-3b-instruct", "prompt": "งาน ก"})
    _run(user_client, worker, result="เสร็จแล้ว.")
    user_client.post("/api/v1/jobs", json={"model": "qwen2.5-7b-instruct", "prompt": "งาน ข"})
    _run(user_client, worker, result="เสร็จแล้ว.")

    body = user_client.get("/api/v1/insights").json()
    assert body["jobs"] == 2
    assert len(body["by_model"]) == 2
    assert all(entry["label"] for entry in body["by_model"])
    assert sum(entry["share"] for entry in body["by_model"]) == pytest.approx(1.0, abs=0.05)
    assert body["workers"][0]["success_rate"] == 1.0


def test_insights_count_failures_and_cache_hits(user_client, worker):
    body_in = {"model": "typhoon2-3b-instruct", "prompt": "คำถาม", "temperature": 0.1}
    user_client.post("/api/v1/jobs", json=body_in)
    _run(user_client, worker, result="คำตอบ")
    user_client.post("/api/v1/jobs", json=body_in)          # ได้จากแคช

    user_client.post("/api/v1/jobs", json={"model": "typhoon2-3b-instruct", "prompt": "งานพัง"})
    job = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()["job"]
    user_client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                     json={"error": "พัง"}, headers=worker["headers"])

    body = user_client.get("/api/v1/insights").json()
    assert body["cached_jobs"] == 1
    assert body["failed"] == 1
    assert 0 < body["failure_rate"] < 1


# ═══ 11. ความจำของบทสนทนา (ย่อรอบเก่าแทนที่จะทิ้ง) ═══════════
def _stuff_thread(thread_id: str, turns: int = 12, size: int = 1800) -> None:
    for index in range(turns):
        db.execute(
            "INSERT INTO messages (thread_id, role, content, created_at) VALUES (?,?,?,?)",
            (thread_id, "user" if index % 2 == 0 else "assistant",
             f"รอบที่ {index} " + "เนื้อหายาว " * (size // 12), index + 1),
        )


def test_a_long_conversation_gets_compressed_instead_of_forgotten(user_client, worker):
    thread_id = user_client.post("/api/v1/threads", json={"model": "typhoon2-3b-instruct"}).json()["id"]
    _stuff_thread(thread_id)

    user_client.post(f"/api/v1/threads/{thread_id}/messages", json={"content": "ถามต่อ"})

    titles = [job["title"] for job in user_client.get("/api/v1/jobs").json()["jobs"]]
    assert any("ย่อความจำ" in title for title in titles), "ควรมีงานย่อความจำเกิดขึ้น"


def test_the_memory_is_fed_back_into_later_turns(user_client, worker):
    thread_id = user_client.post("/api/v1/threads", json={"model": "typhoon2-3b-instruct"}).json()["id"]
    db.execute("UPDATE threads SET memory = ? WHERE id = ?",
               ("- ผู้ใช้ชื่อสมชาย\n- ทำงานสายข้อมูล", thread_id))

    user_client.post(f"/api/v1/threads/{thread_id}/messages", json={"content": "ผมชื่ออะไร"})
    job = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()["job"]

    system = job["payload"]["messages"][0]
    assert system["role"] == "system"
    assert "สมชาย" in system["content"]
    assert "ความจำ" in system["content"]


def test_the_compression_result_becomes_memory_not_a_chat_message(user_client, worker):
    thread_id = user_client.post("/api/v1/threads", json={"model": "typhoon2-3b-instruct"}).json()["id"]
    _stuff_thread(thread_id)
    user_client.post(f"/api/v1/threads/{thread_id}/messages", json={"content": "ถามต่อ"})

    # ทำงานทั้งหมดที่ค้างอยู่ให้เสร็จ (ทั้งคำตอบและงานย่อความจำ)
    for _ in range(4):
        leased = user_client.post("/api/v1/worker/lease", json={},
                                  headers=worker["headers"]).json()["job"]
        if leased is None:
            break
        result = ("- ผู้ใช้ถามเรื่องเดิมซ้ำ ๆ" if "ย่อความจำ" in leased["title"]
                  else "คำตอบปกติ.")
        user_client.post(f"/api/v1/worker/jobs/{leased['id']}/complete",
                         json={"result": result}, headers=worker["headers"])

    detail = user_client.get(f"/api/v1/threads/{thread_id}").json()
    assert detail["thread"]["has_memory"] is True
    # บันทึกความจำต้องไม่โผล่เป็นข้อความในแชท
    assert not any("ผู้ใช้ถามเรื่องเดิมซ้ำ" in message["content"]
                   for message in detail["messages"])


def test_compression_does_not_repeat_for_the_same_turns(user_client, worker):
    thread_id = user_client.post("/api/v1/threads", json={"model": "typhoon2-3b-instruct"}).json()["id"]
    _stuff_thread(thread_id)
    for _ in range(3):
        user_client.post(f"/api/v1/threads/{thread_id}/messages", json={"content": "ถามอีก"})

    compressions = [job for job in user_client.get("/api/v1/jobs").json()["jobs"]
                    if "ย่อความจำ" in job["title"]]
    assert len(compressions) == 1, "รอบเดิมที่ย่อไปแล้ว ต้องไม่ถูกย่อซ้ำ"

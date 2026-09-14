"""เทสต์การเขียนต่อจากจุดที่ค้าง — หัวใจของระบบที่ใช้การ์ดจอซึ่งหลุดได้ตลอด."""

import time

import pytest

from server import continuation, db
from server.routers import workers as workers_module

LONG = "เนื้อหาที่เขียนไปแล้วยาวพอสมควร " * 12      # ~380 ตัวอักษร


def _submit(client, **overrides):
    payload = {"model": "typhoon2-3b-instruct", "prompt": "เขียนเรื่องยาว ๆ", **overrides}
    return client.post("/api/v1/jobs", json=payload).json()["job_id"]


def _kill_worker_mid_job(job_id: str) -> None:
    """แกล้งให้เครื่องเงียบหายไปเลยหลังสตรีมไปแล้วบางส่วน."""
    dead = time.time() - workers_module.LEASE_TIMEOUT - 60
    db.execute("UPDATE jobs SET progress_at = ?, started_at = ? WHERE id = ?",
               (dead, dead, job_id))
    workers_module.reap_stale_jobs()


# ── การต่อข้อความ ────────────────────────────────────────────
@pytest.mark.parametrize("prefix,addition,expected", [
    ("กาลครั้งหนึ่ง ", "กาลครั้งหนึ่ง มีชายคนหนึ่ง", "กาลครั้งหนึ่ง มีชายคนหนึ่ง"),
    ("เตรียมของให้ครบ", "ให้ครบ แล้วลงมือ", "เตรียมของให้ครบ แล้วลงมือ"),
    ("เดิม", "ใหม่", "เดิม ใหม่"),
    ("", "ทั้งหมด", "ทั้งหมด"),
    ("มีแค่นี้", "", "มีแค่นี้"),
])
def test_stitching_never_repeats_the_overlap(prefix, addition, expected):
    assert continuation.stitch(prefix, addition) == expected


def test_stitching_keeps_punctuation_natural():
    assert continuation.stitch("จบประโยคแล้ว.", " ขึ้นประโยคใหม่") == "จบประโยคแล้ว. ขึ้นประโยคใหม่"


def test_only_worthwhile_partials_are_continued():
    assert continuation.can_continue("text", LONG, 0) is True
    assert continuation.can_continue("text", "สั้นมาก", 0) is False      # สั้นไป เขียนใหม่คุ้มกว่า
    assert continuation.can_continue("image", LONG, 0) is False          # ภาพต่อไม่ได้
    assert continuation.can_continue("text", LONG, 3) is False           # ต่อมาพอแล้ว


def test_the_continuation_prompt_tells_the_model_not_to_restart():
    payload = continuation.build_payload(
        {"prompt": "เขียนบทความเรื่องทะเล"}, LONG, "เครื่องหลุด")
    assert payload["original_prompt"] == "เขียนบทความเรื่องทะเล"
    assert "เขียนต่อ" in payload["prompt"]
    assert "ห้ามทวน" in payload["prompt"]
    assert payload["continue_from"].endswith(LONG[-50:])


def test_continuing_twice_keeps_the_original_question():
    first = continuation.build_payload({"prompt": "คำถามเดิม"}, LONG, "รอบแรก")
    second = continuation.build_payload(first, LONG * 2, "รอบสอง")
    assert second["original_prompt"] == "คำถามเดิม"
    assert second["prompt"].count("คำถามเดิม") == 1     # ต้องไม่ซ้อนคำสั่งเดิมทับกันไปเรื่อย ๆ


# ── เครื่องหลุดกลางทาง ───────────────────────────────────────
def test_work_already_done_survives_a_dead_worker(user_client, worker):
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                     json={"delta": LONG}, headers=worker["headers"])

    _kill_worker_mid_job(job_id)

    detail = user_client.get(f"/api/v1/jobs/{job_id}").json()
    assert detail["job"]["status"] == "queued"
    assert detail["job"]["continued"] == 1
    assert detail["job"]["kept_chars"] >= len(LONG) - 5      # ของเดิมยังอยู่ครบ
    assert any("เขียนต่อ" in event["message"] for event in detail["log"])

    # เครื่องถัดไปต้องได้คำสั่งที่บอกให้เขียนต่อ พร้อมข้อความเดิมแนบไปด้วย
    leased = user_client.post("/api/v1/worker/lease", json={},
                              headers=worker["headers"]).json()["job"]
    assert "เขียนต่อจากตรงนี้" in leased["payload"]["prompt"]
    assert leased["payload"]["continue_from"]


def test_the_final_answer_reads_as_one_piece(user_client, worker):
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                     json={"delta": LONG}, headers=worker["headers"])
    _kill_worker_mid_job(job_id)

    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                     json={"delta": "และนี่คือตอนจบของเรื่อง."}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"result": ""}, headers=worker["headers"])

    result = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]["result"]
    assert result.startswith("เนื้อหาที่เขียนไปแล้ว")
    assert result.endswith("และนี่คือตอนจบของเรื่อง.")


def test_a_worker_that_restarts_from_scratch_does_not_duplicate(user_client, worker):
    """เครื่องใหม่ไม่เชื่อฟังแล้วเขียนใหม่ทั้งหมด — ระบบต้องตัดส่วนซ้ำออกให้."""
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                     json={"delta": LONG}, headers=worker["headers"])
    _kill_worker_mid_job(job_id)

    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"result": LONG + "ตอนจบ."}, headers=worker["headers"])

    result = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]["result"]
    assert result.count("เนื้อหาที่เขียนไปแล้วยาวพอสมควร") == 12


def test_a_tiny_partial_is_thrown_away_and_restarted(user_client, worker):
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                     json={"delta": "สั้นมาก"}, headers=worker["headers"])
    _kill_worker_mid_job(job_id)

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["continued"] == 0 and job["result"] == ""      # ล้างทิ้ง ไม่ใช่เอาไปต่อ


def test_an_image_job_is_restarted_not_continued(user_client, worker):
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "sdxl-turbo", "prompt": "วาดรูป"}).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                     json={"delta": "data:image/png;base64," + "A" * 400},
                     headers=worker["headers"])
    _kill_worker_mid_job(job_id)

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["continued"] == 0 and job["result"] == ""


def test_continuing_gives_up_after_a_few_rounds(user_client, worker):
    job_id = _submit(user_client)
    for _ in range(5):
        leased = user_client.post("/api/v1/worker/lease", json={},
                                  headers=worker["headers"]).json()["job"]
        if leased is None:
            break
        user_client.post(f"/api/v1/worker/jobs/{job_id}/stream",
                         json={"delta": LONG}, headers=worker["headers"])
        _kill_worker_mid_job(job_id)

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["continued"] <= continuation.MAX_CONTINUATIONS


# ── คำตอบที่ชนเพดานโทเคน ────────────────────────────────────
def test_a_truncated_answer_is_continued_not_regenerated(user_client, worker):
    """เดิมจะสั่งใหม่ด้วยโควตาสองเท่า ซึ่งต้องเขียนส่วนเดิมซ้ำทั้งหมดก่อน."""
    job_id = _submit(user_client, max_tokens=256)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"result": LONG + "แล้วจึงนำไป", "meta": {"tokens": 256}},
                     headers=worker["headers"])

    detail = user_client.get(f"/api/v1/jobs/{job_id}").json()
    job = detail["job"]
    assert job["status"] == "queued"
    assert job["continued"] == 1
    assert job["kept_chars"] > len(LONG)                     # เก็บของเดิมไว้
    assert job["payload"]["max_tokens"] == 256               # ไม่ต้องขยายโควตา
    assert "ชนเพดาน" in " ".join(event["message"] for event in detail["log"])


def test_the_continued_answer_ends_up_complete(user_client, worker):
    job_id = _submit(user_client, max_tokens=256)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"result": LONG + "แล้วจึงนำไป", "meta": {"tokens": 256}},
                     headers=worker["headers"])

    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"result": "ต้มให้เดือดแล้วเสิร์ฟ.", "meta": {"tokens": 40}},
                     headers=worker["headers"])

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]
    assert job["status"] == "done"
    assert job["result"].endswith("ต้มให้เดือดแล้วเสิร์ฟ.")
    assert job["result"].startswith("เนื้อหาที่เขียนไปแล้ว")


# ── ระบบเรียนรู้จากความผิดพลาดของตัวเอง ──────────────────────
def test_the_same_error_gets_one_fingerprint(user_client):
    from server import diagnosis

    first = diagnosis.signature("CUDA out of memory. Tried to allocate 2.00 GiB at 0x7f3a")
    second = diagnosis.signature("CUDA out of memory. Tried to allocate 512.00 MiB at 0x91bc")
    assert first == second          # ต่างกันแค่ตัวเลข ถือเป็นปัญหาเดียวกัน


def test_a_machine_problem_is_sent_to_another_machine(user_client, worker):
    """ไลบรารีหายบนเครื่องหนึ่ง ไม่ใช่ความผิดของงาน — ต้องให้เครื่องอื่นลองแทน."""
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    resp = user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                            json={"error": "ModuleNotFoundError: No module named 'bitsandbytes'"},
                            headers=worker["headers"]).json()

    assert resp["status"] == "rerouted"
    detail = user_client.get(f"/api/v1/jobs/{job_id}").json()
    assert detail["job"]["status"] == "queued"
    assert any("ส่งให้เครื่องอื่น" in event["message"] for event in detail["log"])


def test_a_job_problem_is_not_rerouted(user_client, worker):
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"error": "ValueError: พารามิเตอร์ของงานนี้ผิด"},
                     headers=worker["headers"])
    assert user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]["status"] == "failed"


def test_the_system_explains_what_it_thinks_went_wrong(user_client, worker):
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"error": "401 Client Error: gated repo for url ..."},
                     headers=worker["headers"])

    log = user_client.get(f"/api/v1/jobs/{job_id}").json()["log"]
    assert any("ต้องขอสิทธิ์" in event["message"] for event in log)


def test_it_remembers_which_fix_actually_worked(user_client, worker):
    """แก้แล้วรอบถัดไปสำเร็จ = จดว่าวิธีนี้ใช้ได้ · ครั้งหน้าเจออีกจะมั่นใจขึ้น."""
    job_id = _submit(user_client, model="qwen2.5-7b-instruct")
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"error": "CUDA out of memory. Tried to allocate 2.00 GiB"},
                     headers=worker["headers"])

    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"result": "คราวนี้สำเร็จแล้ว."}, headers=worker["headers"])

    lessons = user_client.get("/api/v1/lessons").json()
    assert lessons["total_kinds"] >= 1
    memory = lessons["patterns"][0]
    assert memory["successes"] == 1 and memory["success_rate"] == 1.0
    assert len(lessons["proven"]) >= 1


def test_it_counts_a_fix_that_did_not_work(user_client, worker):
    job_id = _submit(user_client, model="qwen2.5-7b-instruct")
    for _ in range(2):
        user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
        user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                         json={"error": "CUDA out of memory. Tried to allocate 2.00 GiB"},
                         headers=worker["headers"])

    memory = user_client.get("/api/v1/lessons").json()["patterns"][0]
    assert memory["failures"] >= 1 and memory["occurrences"] >= 2


def test_lessons_are_private(user_client, client, worker):
    job_id = _submit(user_client)
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"error": "ValueError: ความลับ"}, headers=worker["headers"])

    user_client.post("/auth/logout")
    client.post("/auth/dev", params={"email": "nosy5@spice.local"})
    assert client.get("/api/v1/lessons").json()["patterns"] == []


# ── เครื่องที่ใกล้หมดอายุ ────────────────────────────────────
def test_a_dying_worker_is_given_short_jobs_first(user_client, worker):
    """Colab ที่รันมา 11 ชั่วโมงแล้ว ไม่ควรได้รับงานยาวไปทำค้างไว้."""
    from server import lifespan

    db.execute("UPDATE workers SET name = 'Colab · Tesla T4', created_at = ? WHERE id = ?",
               (time.time() - 11.4 * 3600, worker["id"]))
    row = dict(db.query_one("SELECT * FROM workers WHERE id = ?", (worker["id"],)))
    info = lifespan.remaining(row["user_id"], row)

    assert info["platform"] == "colab"
    assert info["running_out"] is True
    assert lifespan.can_finish(1800, info["remaining_seconds"]) is False   # งาน 30 นาที
    assert lifespan.can_finish(60, info["remaining_seconds"]) is True      # งาน 1 นาที


def test_a_fresh_worker_is_not_flagged(user_client, worker):
    from server import lifespan

    row = dict(db.query_one("SELECT * FROM workers WHERE id = ?", (worker["id"],)))
    assert lifespan.remaining(row["user_id"], row)["running_out"] is False


def test_the_dashboard_shows_how_long_a_machine_has_left(user_client, worker):
    entry = user_client.get("/api/v1/workers").json()["workers"][0]
    assert entry["life"]["remaining_seconds"] > 0
    assert entry["life_note"]


def test_out_of_memory_on_the_smallest_model_tries_a_bigger_machine(user_client, worker):
    """โมเดลเล็กสุดแล้วยังไม่พอ — ทางเดียวที่เหลือคือหาเครื่องที่ VRAM มากกว่า."""
    code = user_client.post("/api/v1/workers/pair", json={}).json()["pair_code"]
    big = user_client.post("/api/v1/worker/register", json={
        "pair_code": code, "name": "เครื่องใหญ่", "gpu_name": "A100",
        "gpu_vram_mb": 40000, "capabilities": ["text"]}).json()
    user_client.post("/api/v1/worker/heartbeat", json={"gpu_vram_mb": 40000},
                     headers={"Authorization": f"Bearer {big['worker_token']}"})

    job_id = _submit(user_client, model="typhoon2-3b-instruct")
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    resp = user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                            json={"error": "CUDA out of memory. Tried to allocate 2.00 GiB"},
                            headers=worker["headers"]).json()

    assert resp["status"] == "rerouted"
    log = user_client.get(f"/api/v1/jobs/{job_id}").json()["log"]
    assert any("VRAM มากกว่า" in event["message"] for event in log)

"""เทสต์ระบบอัจฉริยะแบบครบวงจร: วางแผน → จัดสรรเครื่อง → ลูกโซ่ → กู้คืนเอง."""

import pytest

from server import db


@pytest.fixture()
def small_worker(user_client):
    """เครื่อง VRAM น้อย — รับงานโมเดลใหญ่ไม่ไหว."""
    code = user_client.post("/api/v1/workers/pair", json={"label": "เล็ก"}).json()["pair_code"]
    data = user_client.post("/api/v1/worker/register", json={
        "pair_code": code, "name": "gtx-1060", "gpu_name": "GTX 1060",
        "gpu_vram_mb": 6000, "capabilities": ["text"],
    }).json()
    return {"id": data["worker_id"], "headers": {"Authorization": f"Bearer {data['worker_token']}"}}


# ── วางแผนก่อนรัน ────────────────────────────────────────────
def test_plan_explains_what_it_will_do(user_client, worker):
    body = user_client.post("/api/v1/plan", json={
        "prompt": "เขียนฟังก์ชัน Python หาเลขเฉพาะพร้อมเทสต์",
    }).json()
    assert len(body["steps"]) == 1
    assert body["steps"][0]["model"] == "qwen2.5-7b-instruct"
    assert body["steps"][0]["model_label"] == "Qwen2.5 7B Instruct"
    assert body["reason"]                       # ต้องบอกเหตุผลเสมอ
    assert body["intent"]["task"] == "code"
    assert body["eta_seconds"] > 0
    assert body["capacity"]["online"] == 1


def test_plan_shows_the_chain_for_audio(user_client, worker):
    body = user_client.post("/api/v1/plan", json={
        "prompt": "ถอดเสียงแล้วสรุปประเด็นสำคัญ",
        "drive_input": "gdrive:audio/meeting.m4a",
    }).json()
    assert [step["kind"] for step in body["steps"]] == ["audio", "text"]
    assert body["steps"][1]["use_previous"] is True


def test_plan_rejects_an_empty_request(user_client):
    assert user_client.post("/api/v1/plan", json={"prompt": "  "}).status_code == 400


# ── โหมดอัตโนมัติ ────────────────────────────────────────────
def test_auto_mode_picks_the_model_itself(user_client, worker):
    body = user_client.post("/api/v1/jobs", json={
        "model": "auto", "prompt": "สรุปข่าวนี้ให้หน่อย",
    }).json()
    assert body["auto"] is True
    assert body["model"] == "typhoon2-3b-instruct"      # ไทย + งานเบา
    assert body["reason"]
    assert body["eta_seconds"] > 0


def test_manual_choice_is_respected(user_client, worker):
    body = user_client.post("/api/v1/jobs", json={
        "model": "llama-3.2-3b-instruct", "prompt": "สรุปข่าวนี้",
    }).json()
    assert body["auto"] is False
    assert body["model"] == "llama-3.2-3b-instruct"


def test_auto_mode_adapts_to_the_hardware_it_has(user_client, small_worker):
    """เครื่องเล็ก → ต้องไม่เลือกโมเดลที่รันไม่ไหว."""
    body = user_client.post("/api/v1/jobs", json={
        "model": "auto", "prompt": "เขียนฟังก์ชัน Python หาเลขเฉพาะ",
    }).json()
    assert body["model"] != "qwen2.5-7b-instruct"
    job = user_client.get(f"/api/v1/jobs/{body['job_id']}").json()["job"]
    assert any("ไม่พอ" in w or "ไม่มีเครื่องไหน" in w for w in job["plan"]["warnings"])


# ── จัดสรรงานให้ตรงกับเครื่อง ────────────────────────────────
def test_worker_never_gets_a_job_kind_it_cannot_handle(user_client, small_worker):
    """เครื่องที่ประกาศว่าทำได้แต่งานข้อความ ต้องไม่ถูกยัดงานถอดเสียงมาให้."""
    user_client.post("/api/v1/jobs", json={
        "model": "whisper-large-v3-turbo", "prompt": "ถอดเสียง",
        "drive_input": "gdrive:a.m4a",
    })
    leased = user_client.post("/api/v1/worker/lease", json={},
                              headers=small_worker["headers"]).json()
    assert leased["job"] is None


def test_small_worker_never_gets_a_job_it_cannot_run(user_client, small_worker):
    user_client.post("/api/v1/jobs", json={
        "model": "qwen2.5-7b-instruct", "prompt": "งานหนัก",
    })
    leased = user_client.post("/api/v1/worker/lease", json={}, headers=small_worker["headers"]).json()
    assert leased["job"] is None          # เดิมจะรับไปแล้วพังด้วย CUDA OOM


def test_big_worker_takes_the_job_the_small_one_skipped(user_client, small_worker, worker):
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "qwen2.5-7b-instruct", "prompt": "งานหนัก",
    }).json()["job_id"]
    assert user_client.post("/api/v1/worker/lease", json={},
                            headers=small_worker["headers"]).json()["job"] is None
    taken = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()
    assert taken["job"]["id"] == job_id


def test_worker_prefers_the_job_whose_model_is_already_loaded(user_client, worker):
    """งานที่ใช้โมเดลซึ่งค้างอยู่ใน VRAM แล้ว ควรถูกหยิบก่อน แม้จะเข้าคิวทีหลัง."""
    first = user_client.post("/api/v1/jobs", json={
        "model": "qwen2.5-7b-instruct", "prompt": "งานที่เข้าคิวก่อน",
    }).json()["job_id"]
    warm_job = user_client.post("/api/v1/jobs", json={
        "model": "typhoon2-3b-instruct", "prompt": "งานที่เข้าคิวทีหลัง",
    }).json()["job_id"]

    user_client.post("/api/v1/worker/heartbeat", json={
        "warm_models": ["typhoon2-3b-instruct"], "gpu_vram_mb": 15360,
    }, headers=worker["headers"])

    leased = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()
    assert leased["job"]["id"] == warm_job
    assert first != warm_job


def test_warm_models_show_up_in_the_dashboard(user_client, worker):
    user_client.post("/api/v1/worker/heartbeat", json={
        "warm_models": ["qwen2.5-7b-instruct"], "gpu_vram_mb": 15360,
    }, headers=worker["headers"])
    entry = user_client.get("/api/v1/workers").json()["workers"][0]
    assert entry["warm_models"] == ["qwen2.5-7b-instruct"]
    assert entry["warm_labels"] == ["Qwen2.5 7B Instruct"]


def test_queued_job_explains_why_it_is_stuck(user_client, small_worker):
    body = user_client.post("/api/v1/jobs", json={
        "model": "qwen2.5-7b-instruct", "prompt": "งานหนักเกินเครื่อง",
    }).json()
    assert "ไม่มีเครื่องที่รับงานนี้ไหว" in body["hint"]
    assert "VRAM" in body["hint"]


# ── ลูกโซ่งาน ────────────────────────────────────────────────
def _run_one(client, worker, result="ผลลัพธ์ของขั้นนี้"):
    """ให้เครื่องรับงานถัดไปแล้วทำจนเสร็จ คืนข้อมูลงานที่เพิ่งทำ."""
    job = client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()["job"]
    assert job is not None, "ควรมีงานให้ทำ"
    client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                json={"result": result}, headers=worker["headers"])
    return job


def test_chain_runs_step_by_step_and_carries_the_result(user_client, worker):
    submitted = user_client.post("/api/v1/jobs", json={
        "model": "auto",
        "prompt": "ถอดเสียงแล้วสรุปให้หน่อย",
        "drive_input": "gdrive:audio/meeting.m4a",
    }).json()
    assert submitted["steps"] == 2

    first = _run_one(user_client, worker, result="สวัสดีครับ วันนี้ประชุมเรื่องงบประมาณ")
    assert first["kind"] == "audio"

    # ขั้นแรกเสร็จแล้ว ระบบต้องสร้างขั้นสองให้เองโดยไม่ต้องสั่ง
    second = _run_one(user_client, worker, result="สรุป: ประชุมเรื่องงบประมาณ")
    assert second["kind"] == "text"
    assert "งบประมาณ" in second["payload"]["prompt"]     # ผลขั้นแรกถูกส่งต่อมาจริง

    jobs = user_client.get("/api/v1/jobs").json()["jobs"]
    assert len(jobs) == 2
    assert all(job["status"] == "done" for job in jobs)
    assert any(job["parent_id"] == submitted["job_id"] for job in jobs)


def test_a_failed_step_stops_the_rest_of_the_chain(user_client, worker):
    user_client.post("/api/v1/jobs", json={
        "model": "auto", "prompt": "ถอดเสียงแล้วสรุป",
        "drive_input": "gdrive:audio/meeting.m4a",
    })
    job = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()["job"]
    user_client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                     json={"error": "ไฟล์เสียงเปิดไม่ได้"}, headers=worker["headers"])

    assert user_client.post("/api/v1/worker/lease", json={},
                            headers=worker["headers"]).json()["job"] is None
    assert len(user_client.get("/api/v1/jobs").json()["jobs"]) == 1


# ── กู้คืนเองเมื่อหน่วยความจำไม่พอ ───────────────────────────
def test_out_of_memory_is_retried_with_a_smaller_model(user_client, worker):
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "qwen2.5-7b-instruct", "prompt": "งานหนัก",
    }).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])

    resp = user_client.post(f"/api/v1/worker/jobs/{job_id}/complete", json={
        "error": "CUDA out of memory. Tried to allocate 2.00 GiB",
    }, headers=worker["headers"]).json()
    assert resp["status"] == "requeued"

    job = user_client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["job"]["status"] == "queued"            # กลับเข้าคิวเอง ไม่ใช่ล้มเหลว
    assert job["job"]["model"] != "qwen2.5-7b-instruct"
    assert job["job"]["attempt"] == 2
    assert any("ลดขนาด" in event["message"] for event in job["log"])


def test_recovery_is_tried_only_once(user_client, worker):
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "qwen2.5-7b-instruct", "prompt": "งานหนัก",
    }).json()["job_id"]
    for _ in range(2):
        user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
        user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                         json={"error": "CUDA out of memory"}, headers=worker["headers"])
    assert user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]["status"] == "failed"


def test_non_memory_errors_are_not_retried(user_client, worker):
    job_id = user_client.post("/api/v1/jobs", json={
        "model": "qwen2.5-7b-instruct", "prompt": "งานหนัก",
    }).json()["job_id"]
    user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"])
    user_client.post(f"/api/v1/worker/jobs/{job_id}/complete",
                     json={"error": "ไฟล์ต้นทางไม่มีอยู่จริง"}, headers=worker["headers"])
    assert user_client.get(f"/api/v1/jobs/{job_id}").json()["job"]["status"] == "failed"


# ── ดึงความรู้จากคลังมาช่วยตอบ (RAG) ─────────────────────────
def test_vault_context_is_injected_into_the_prompt(user_client, worker):
    user_client.post("/api/v1/vault/docs", json={
        "text": "รหัสผ่าน WiFi ของออฟฟิศคือ spice-2026-office เปลี่ยนทุกไตรมาส",
        "title": "WiFi ออฟฟิศ",
    })
    body = user_client.post("/api/v1/jobs", json={
        "model": "auto", "prompt": "รหัสผ่าน WiFi ออฟฟิศคืออะไร",
    }).json()
    assert body["uses_vault"] is True

    payload = user_client.get(f"/api/v1/jobs/{body['job_id']}").json()["job"]["payload"]
    assert "spice-2026-office" in payload["system"]
    assert "คลังความรู้" in payload["system"]


def test_no_vault_context_when_the_vault_is_empty(user_client, worker):
    body = user_client.post("/api/v1/jobs", json={
        "model": "auto", "prompt": "รหัสผ่าน WiFi ออฟฟิศคืออะไร",
    }).json()
    assert body["uses_vault"] is False


def test_vault_is_not_used_for_creative_writing(user_client, worker):
    user_client.post("/api/v1/vault/docs", json={"text": "เอกสารอะไรสักอย่าง"})
    body = user_client.post("/api/v1/jobs", json={
        "model": "auto", "prompt": "แต่งกลอนเกี่ยวกับทะเล",
    }).json()
    assert body["uses_vault"] is False

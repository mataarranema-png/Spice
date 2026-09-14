"""เทสต์การดึงโมเดลจาก Hugging Face — ส่วนที่คุยกับ HF จริงถูกจำลองไว้."""

import pytest

from server import catalog, hub

# ตัวอย่าง metadata ที่ Hugging Face ส่งกลับมาจริง (ตัดมาเฉพาะฟิลด์ที่เราใช้)
ABLITERATED_8B = {
    "modelId": "huihui-ai/Llama-3.2-3B-Instruct-abliterated",
    "pipeline_tag": "text-generation",
    "tags": ["transformers", "safetensors", "llama", "text-generation", "abliterated"],
    "safetensors": {"total": 3_212_749_824},
    "downloads": 48_213,
    "likes": 311,
    "gated": False,
    "private": False,
    "lastModified": "2026-07-02T10:00:00.000Z",
}

GATED_LLAMA = {
    "modelId": "meta-llama/Llama-3.1-8B-Instruct",
    "pipeline_tag": "text-generation",
    "tags": ["transformers", "safetensors", "llama"],
    "safetensors": {"total": 8_030_261_248},
    "gated": "manual",
    "downloads": 9_000_000,
    "likes": 3800,
}

GGUF_MODEL = {
    "modelId": "TheBloke/dolphin-2.9-llama3-8B-GGUF",
    "pipeline_tag": "text-generation",
    "tags": ["gguf", "llama"],
    "downloads": 120_000,
}


# ── ประเมิน VRAM ─────────────────────────────────────────────
def test_vram_estimates_match_reality():
    """ตัวเลขเหล่านี้เทียบกับที่วัดได้จริงตอนรันบน T4."""
    assert 4800 <= hub.estimate_vram_mb(7, "4bit") <= 6000      # 7B 4bit ≈ 5–6 GB
    assert 16000 <= hub.estimate_vram_mb(7, "fp16") <= 18000    # 7B fp16 ไม่ลง T4
    assert 7000 <= hub.estimate_vram_mb(3, "fp16") <= 8200      # 3B fp16 ≈ 7 GB


def test_bigger_models_and_lighter_quantization_move_the_right_way():
    assert hub.estimate_vram_mb(13, "fp16") > hub.estimate_vram_mb(7, "fp16")
    assert hub.estimate_vram_mb(7, "fp16") > hub.estimate_vram_mb(7, "8bit")
    assert hub.estimate_vram_mb(7, "8bit") > hub.estimate_vram_mb(7, "4bit")
    assert hub.estimate_vram_mb(0, "fp16") == 0                 # ไม่รู้ขนาด = ไม่เดามั่ว


@pytest.mark.parametrize("repo,expected", [
    ("cognitivecomputations/dolphin-2.9.4-llama3.1-8b", 8.0),
    ("huihui-ai/Llama-3.2-3B-Instruct-abliterated", 3.0),
    ("google/gemma-2-27b-it", 27.0),
    ("microsoft/Phi-3-mini-4k-instruct", 0.0),           # "4k" คือความยาวบริบท ไม่ใช่ขนาด
    ("sentence-transformers/all-MiniLM-L6-v2", 0.0),     # ไม่มีขนาดในชื่อ
    ("mistralai/Mixtral-8x7B-Instruct-v0.1", 47.6),      # MoE ต้องคูณจำนวนผู้เชี่ยวชาญ
    ("mistralai/Mistral-7B-Instruct-v0.3", 7.0),         # เลขเวอร์ชันต้องไม่ถูกนับ
])
def test_guesses_size_from_the_model_name(repo, expected):
    assert hub.params_from_name(repo) == expected


def test_prefers_real_metadata_over_guessing():
    assert hub.params_from_info(ABLITERATED_8B) == pytest.approx(3.213, abs=0.01)


def test_suggests_quantization_that_actually_fits():
    assert hub.suggest_quantize(3, 15360) == "fp16"      # เล็กพอ ไม่ต้องบีบ
    assert hub.suggest_quantize(13, 15360) == "4bit"     # ต้องบีบถึงจะลง T4
    assert hub.suggest_quantize(7, 81920) == "fp16"      # การ์ดใหญ่ ไม่ต้องบีบ


# ── อ่านชนิดงานและรูปแบบไฟล์ ─────────────────────────────────
@pytest.mark.parametrize("info,kind", [
    ({"pipeline_tag": "text-generation"}, "text"),
    ({"pipeline_tag": "text-to-image"}, "image"),
    ({"pipeline_tag": "automatic-speech-recognition"}, "audio"),
    ({"pipeline_tag": "sentence-similarity"}, "embedding"),
    ({"tags": ["diffusers", "stable-diffusion"]}, "image"),
    ({"tags": ["sentence-transformers"]}, "embedding"),
    ({}, "text"),
])
def test_detects_what_kind_of_model_it_is(info, kind):
    assert hub.detect_kind(info) == kind


def test_rejects_formats_the_worker_cannot_load():
    reason = hub.unsupported_reason(GGUF_MODEL)
    assert "GGUF" in reason and "llama.cpp" in reason
    assert hub.unsupported_reason(ABLITERATED_8B) == ""


def test_describe_produces_everything_the_ui_needs():
    described = hub.describe(ABLITERATED_8B, vram_budget_mb=15360)
    assert described["repo"] == ABLITERATED_8B["modelId"]
    assert described["kind"] == "text"
    assert described["label"] == "Llama-3.2-3B-Instruct-abliterated"
    assert described["owner"] == "huihui-ai"
    assert described["fits"] is True
    assert described["vram_by_quantize"]["4bit"] < described["vram_by_quantize"]["fp16"]
    assert described["url"].startswith("https://huggingface.co/")
    assert described["id"].startswith("hf--")


def test_big_model_is_flagged_as_not_fitting():
    described = hub.describe(GATED_LLAMA, quantize="fp16", vram_budget_mb=15360)
    assert described["fits"] is False          # 8B fp16 ไม่ลง T4
    assert described["gated"] is True


def test_slug_is_unique_and_url_safe():
    first = hub.slugify("cognitivecomputations/dolphin-2.9.4-llama3.1-8b")
    second = hub.slugify("huihui-ai/dolphin-2.9.4-llama3.1-8b")
    assert first != second                     # เจ้าของต่างกันต้องไม่ชนกัน
    assert all(char.isalnum() or char == "-" for char in first)


# ── เส้นทาง API (จำลองการคุยกับ HF) ──────────────────────────
@pytest.fixture()
def fake_hf(monkeypatch):
    """แทนที่การเรียก Hugging Face จริงด้วยข้อมูลตัวอย่าง."""
    async def fake_info(repo, token=""):
        table = {
            ABLITERATED_8B["modelId"]: ABLITERATED_8B,
            GATED_LLAMA["modelId"]: GATED_LLAMA,
            GGUF_MODEL["modelId"]: GGUF_MODEL,
        }
        if repo not in table:
            raise ValueError(f"ไม่พบโมเดล '{repo}' บน Hugging Face (สะกดถูกไหม?)")
        return table[repo]

    async def fake_search(query, kind="", limit=20, token="", vram_budget_mb=0):
        return [hub.describe(ABLITERATED_8B, vram_budget_mb=vram_budget_mb)]

    monkeypatch.setattr(hub, "model_info", fake_info)
    monkeypatch.setattr(hub, "search", fake_search)


def test_search_requires_a_query(user_client, fake_hf):
    assert user_client.get("/api/v1/hub/search?q=").status_code == 400


def test_search_marks_models_already_in_your_library(user_client, fake_hf):
    body = user_client.get("/api/v1/hub/search?q=abliterated").json()
    assert body["results"][0]["already_added"] is False

    user_client.post("/api/v1/hub/models", json={"repo": ABLITERATED_8B["modelId"]})
    body = user_client.get("/api/v1/hub/search?q=abliterated").json()
    assert body["results"][0]["already_added"] is True


def test_adding_a_model_makes_it_usable(user_client, fake_hf, worker):
    body = user_client.post(
        "/api/v1/hub/models", json={"repo": ABLITERATED_8B["modelId"]}
    ).json()
    assert body["ok"] is True
    model_id = body["model"]["id"]

    # โผล่ในรายการโมเดลที่เลือกได้
    models = user_client.get("/api/v1/models").json()
    assert any(model["id"] == model_id for model in models["models"])
    assert models["custom_count"] == 1

    # สั่งงานด้วยโมเดลนี้ได้จริง และ worker ได้ repo ที่ถูกต้อง
    job = user_client.post("/api/v1/jobs", json={"model": model_id, "prompt": "ทดสอบ"}).json()
    leased = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()
    assert leased["job"]["id"] == job["job_id"]
    assert leased["job"]["payload"]["repo"] == ABLITERATED_8B["modelId"]


def test_accepts_a_pasted_browser_link(user_client, fake_hf):
    body = user_client.post("/api/v1/hub/models", json={
        "repo": f"https://huggingface.co/{ABLITERATED_8B['modelId']}?library=transformers",
    }).json()
    assert body["model"]["repo"] == ABLITERATED_8B["modelId"]


def test_rejects_a_malformed_repo_name(user_client, fake_hf):
    assert user_client.post("/api/v1/hub/models", json={"repo": "dolphin"}).status_code == 400


def test_reports_a_model_that_does_not_exist(user_client, fake_hf):
    resp = user_client.post("/api/v1/hub/models", json={"repo": "nobody/does-not-exist"})
    assert resp.status_code == 400
    assert "ไม่พบโมเดล" in resp.json()["detail"]


def test_refuses_gguf_with_a_useful_explanation(user_client, fake_hf):
    resp = user_client.post("/api/v1/hub/models", json={"repo": GGUF_MODEL["modelId"]})
    assert resp.status_code == 400
    assert "GGUF" in resp.json()["detail"]


def test_gated_model_needs_a_token_first(user_client, fake_hf):
    resp = user_client.post("/api/v1/hub/models", json={"repo": GATED_LLAMA["modelId"]})
    assert resp.status_code == 400
    assert "ขอสิทธิ์" in resp.json()["detail"]

    user_client.put("/api/v1/hub/token", json={"token": "hf_" + "x" * 30})
    assert user_client.post(
        "/api/v1/hub/models", json={"repo": GATED_LLAMA["modelId"]}
    ).status_code == 200


def test_warns_when_the_model_will_not_fit(user_client, fake_hf, worker):
    body = user_client.put("/api/v1/hub/token", json={"token": "hf_" + "y" * 30})
    assert body.status_code == 200
    added = user_client.post("/api/v1/hub/models", json={
        "repo": GATED_LLAMA["modelId"], "quantize": "fp16",
    }).json()
    assert any("VRAM" in warning for warning in added["warnings"])


def test_trust_remote_code_carries_a_warning_and_reaches_the_worker(user_client, fake_hf, worker):
    added = user_client.post("/api/v1/hub/models", json={
        "repo": ABLITERATED_8B["modelId"], "trust_remote_code": True,
    }).json()
    assert any("trust_remote_code" in warning for warning in added["warnings"])

    user_client.post("/api/v1/jobs", json={"model": added["model"]["id"], "prompt": "ทดสอบ"})
    leased = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()
    assert leased["job"]["payload"]["trust_remote_code"] is True


def test_trust_remote_code_is_off_unless_asked_for(user_client, fake_hf, worker):
    added = user_client.post("/api/v1/hub/models", json={"repo": ABLITERATED_8B["modelId"]}).json()
    user_client.post("/api/v1/jobs", json={"model": added["model"]["id"], "prompt": "ทดสอบ"})
    leased = user_client.post("/api/v1/worker/lease", json={}, headers=worker["headers"]).json()
    assert leased["job"]["payload"]["trust_remote_code"] is False


def test_removing_a_model_takes_it_out_of_the_catalog(user_client, fake_hf):
    model_id = user_client.post(
        "/api/v1/hub/models", json={"repo": ABLITERATED_8B["modelId"]}
    ).json()["model"]["id"]
    assert user_client.delete(f"/api/v1/hub/models/{model_id}").json()["ok"] is True
    assert user_client.delete(f"/api/v1/hub/models/{model_id}").status_code == 404
    assert catalog.get(model_id) is None


def test_your_models_are_private_to_you(user_client, client, fake_hf):
    model_id = user_client.post(
        "/api/v1/hub/models", json={"repo": ABLITERATED_8B["modelId"]}
    ).json()["model"]["id"]

    user_client.post("/auth/logout")
    client.post("/auth/dev", params={"email": "someone-else@spice.local"})
    assert client.get("/api/v1/hub/models").json()["models"] == []
    # เดา id ถูกก็ใช้ไม่ได้อยู่ดี
    assert client.post(
        "/api/v1/jobs", json={"model": model_id, "prompt": "ขอใช้ของคนอื่น"}
    ).status_code == 403


# ── โทเคน Hugging Face ───────────────────────────────────────
def test_token_is_stored_encrypted_and_shown_masked(user_client):
    from server import db

    user_client.put("/api/v1/hub/token", json={"token": "hf_secrettoken1234567890"})
    stored = db.query_one("SELECT hf_token FROM user_secrets")["hf_token"]
    assert "hf_secrettoken" not in stored          # ต้องไม่เก็บเป็นข้อความเปล่า

    status = user_client.get("/api/v1/hub/token").json()
    assert status["has_token"] is True
    assert "secrettoken" not in status["masked"]


def test_rejects_something_that_is_not_a_token(user_client):
    assert user_client.put(
        "/api/v1/hub/token", json={"token": "ghp_wrongservice"}
    ).status_code == 400


def test_token_can_be_cleared(user_client):
    user_client.put("/api/v1/hub/token", json={"token": "hf_" + "z" * 30})
    assert user_client.put("/api/v1/hub/token", json={"token": ""}).json()["has_token"] is False


def test_worker_can_fetch_the_owner_token(user_client, worker):
    user_client.put("/api/v1/hub/token", json={"token": "hf_" + "w" * 30})
    body = user_client.get("/api/v1/hub/worker/token", headers=worker["headers"]).json()
    assert body["hf_token"].startswith("hf_")
    assert user_client.get("/api/v1/hub/worker/token").status_code == 401


# ── โมเดลที่เพิ่มเองเข้าร่วมการตัดสินใจอัตโนมัติ ──────────────
def test_custom_model_competes_in_automatic_selection(user_client, fake_hf, worker):
    """ผู้ใช้ดึงโมเดลไทยตัวใหม่มา ระบบควรเลือกใช้มันเองเมื่อสั่งงานภาษาไทย."""
    from server import brain

    added = user_client.post("/api/v1/hub/models", json={"repo": ABLITERATED_8B["modelId"]}).json()
    models = catalog.models_for(1) if catalog.models_for(1) else []
    assert any(model.get("custom") for model in catalog.custom_models_for(
        user_client.get("/api/v1/me").json()["id"]))

    intent = brain.analyze("สรุปข่าวนี้")
    chosen, reason, _ = brain.pick_model(
        intent, {"best_vram_mb": 15360, "online": 1},
        catalog.models_for(user_client.get("/api/v1/me").json()["id"]),
    )
    assert chosen in {model["id"] for model in catalog.models_for(
        user_client.get("/api/v1/me").json()["id"])}
    assert reason


def test_presets_include_uncensored_starting_points(user_client):
    groups = user_client.get("/api/v1/hub/presets").json()["groups"]
    names = [group["group"] for group in groups]
    assert any("เซ็นเซอร์" in name for name in names)
    assert all(model["repo"].count("/") == 1 for group in groups for model in group["models"])

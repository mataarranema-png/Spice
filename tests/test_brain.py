"""เทสต์สมองของระบบ — การอ่านเจตนา เลือกโมเดล และวางแผนเป็นลูกโซ่."""

import pytest

from server import brain


# ── อ่านภาษา ─────────────────────────────────────────────────
@pytest.mark.parametrize("text,expected", [
    ("ช่วยสรุปรายงานนี้ให้หน่อย", "th"),
    ("please summarize this report", "en"),
    ("ช่วย refactor ฟังก์ชัน handleSubmit ให้หน่อย", "th"),
    ("write a Python script", "en"),
])
def test_detect_language(text, expected):
    assert brain.detect_language(text) == expected


# ── อ่านเจตนา ────────────────────────────────────────────────
@pytest.mark.parametrize("prompt,kind,task", [
    ("วาดรูปแมวใส่ชุดอวกาศ", "image", "draw"),
    ("สร้างภาพโลโก้ร้านกาแฟ", "image", "draw"),
    ("เขียนฟังก์ชัน Python หาเลขเฉพาะ", "text", "code"),
    ("แก้บั๊กนี้ให้หน่อย error: NoneType", "text", "code"),
    ("สรุปบทความนี้", "text", "summarize"),
    ("แปลเป็นภาษาอังกฤษ", "text", "translate"),
    ("เปรียบเทียบข้อดีข้อเสียของสองแนวทาง", "text", "analyze"),
    ("แต่งกลอนเกี่ยวกับทะเล", "text", "creative"),
    ("ถอดเสียงไฟล์นี้", "audio", "transcribe"),
    ("สวัสดี วันนี้เป็นยังไงบ้าง", "text", "chat"),
])
def test_analyze_detects_task(prompt, kind, task):
    intent = brain.analyze(prompt)
    assert (intent.kind, intent.task) == (kind, task)


def test_audio_file_beats_wording():
    """ไฟล์เสียงเป็นหลักฐานหนักแน่นกว่าคำในประโยค."""
    intent = brain.analyze("เอาไฟล์นี้มาสรุปให้หน่อย", "gdrive:meeting.m4a")
    assert intent.kind == "audio"
    assert any("เสียง" in signal for signal in intent.signals)


def test_length_and_temperature_follow_the_task():
    short = brain.analyze("สรุปสั้น ๆ หน่อย")
    long_form = brain.analyze("เขียนบทความเรื่องพลังงานสะอาด")
    code = brain.analyze("เขียนสคริปต์ Python")
    creative = brain.analyze("แต่งกลอนให้หน่อย")

    assert short.max_tokens < long_form.max_tokens
    assert code.max_tokens >= 1536            # โค้ดที่ถูกตัดกลางคันใช้ไม่ได้
    assert code.temperature < creative.temperature
    assert creative.temperature > 0.8


def test_questions_want_context_from_the_vault():
    assert brain.analyze("รหัส WiFi ออฟฟิศคืออะไร").wants_context is True
    # มีไฟล์แนบมาแล้ว ไม่ต้องไปค้นคลังอีก
    assert brain.analyze("สรุปไฟล์นี้", "gdrive:a.txt").wants_context is False


# ── เลือกโมเดล ───────────────────────────────────────────────
def test_heavy_task_prefers_the_strongest_model():
    intent = brain.analyze("เขียนฟังก์ชัน Python หาเลขเฉพาะ")
    model, reason, warnings = brain.pick_model(intent, {"best_vram_mb": 15360, "online": 1})
    assert model == "qwen2.5-7b-instruct"
    assert not warnings


def test_simple_thai_task_prefers_the_fast_thai_model():
    intent = brain.analyze("สรุปข่าวนี้")
    model, _, _ = brain.pick_model(intent, {"best_vram_mb": 15360, "online": 1})
    assert model == "typhoon2-3b-instruct"


def test_downgrades_when_vram_is_short_and_says_so():
    intent = brain.analyze("เขียนฟังก์ชัน Python")
    model, _, warnings = brain.pick_model(intent, {"best_vram_mb": 7000, "online": 1})
    assert model != "qwen2.5-7b-instruct"
    assert warnings and "ไม่พอ" in warnings[0]


def test_warns_when_nothing_fits_at_all():
    intent = brain.analyze("เขียนฟังก์ชัน Python")
    model, _, warnings = brain.pick_model(intent, {"best_vram_mb": 2000, "online": 1})
    assert model == "typhoon2-3b-instruct" or model == "llama-3.2-3b-instruct"
    assert any("ไม่มีเครื่องไหน" in warning for warning in warnings)


def test_warm_model_wins_for_light_tasks():
    """โมเดลที่โหลดค้างไว้แล้วเริ่มงานได้ทันที จึงควรถูกเลือกก่อน."""
    intent = brain.analyze("hello there")          # งานเบา ภาษาอังกฤษ
    capacity = {"best_vram_mb": 15360, "online": 1, "warm": ["typhoon2-3b-instruct"]}
    model, reason, _ = brain.pick_model(intent, capacity)
    assert model == "typhoon2-3b-instruct"
    assert "โหลดค้างไว้" in reason


# ── วางแผน ───────────────────────────────────────────────────
def test_audio_plus_summary_becomes_a_two_step_chain():
    plan = brain.build_plan(
        "ถอดเสียงแล้วสรุปให้หน่อย", "gdrive:audio/meeting.m4a",
        capacity={"best_vram_mb": 15360, "online": 1},
    )
    assert len(plan.steps) == 2
    assert plan.steps[0].kind == "audio"
    assert plan.steps[1].kind == "text"
    assert plan.steps[1].use_previous is True     # ขั้นสองกินผลของขั้นหนึ่ง


def test_plain_request_is_a_single_step():
    plan = brain.build_plan("สวัสดี", capacity={"best_vram_mb": 15360, "online": 1})
    assert len(plan.steps) == 1
    assert plan.steps[0].use_previous is False


def test_asking_to_save_adds_a_drive_destination():
    plan = brain.build_plan(
        "สรุปเรื่องนี้แล้วบันทึกลง Drive ให้ด้วย",
        capacity={"best_vram_mb": 15360, "online": 1},
    )
    assert plan.steps[-1].drive_output.startswith("gdrive:")


def test_plan_warns_when_no_worker_is_online():
    plan = brain.build_plan("สวัสดี", capacity={"online": 0, "best_vram_mb": 0})
    assert any("ยังไม่มีเครื่อง" in warning for warning in plan.warnings)


def test_eta_uses_real_history_and_cold_start():
    warm_eta = brain.estimate_seconds(
        "typhoon2-3b-instruct", {"typhoon2-3b-instruct": 10.0}, {"typhoon2-3b-instruct"})
    cold_eta = brain.estimate_seconds("typhoon2-3b-instruct", {"typhoon2-3b-instruct": 10.0}, set())
    assert warm_eta == pytest.approx(10.0)        # โหลดค้างไว้แล้ว ไม่มีค่าโหลด
    assert cold_eta > warm_eta + 20               # ยังไม่โหลด ต้องบวกเวลาโหลดโมเดล


def test_eta_grows_with_queue_depth():
    alone = brain.estimate_seconds("typhoon2-3b-instruct", {}, set(), queue_ahead=0)
    crowded = brain.estimate_seconds("typhoon2-3b-instruct", {}, set(), queue_ahead=5)
    assert crowded > alone


def test_chain_eta_covers_every_step():
    history = {"whisper-large-v3-turbo": 20.0, "typhoon2-3b-instruct": 10.0}
    plan = brain.build_plan(
        "ถอดเสียงแล้วสรุป", "gdrive:a.m4a",
        capacity={"best_vram_mb": 15360, "online": 1}, history=history,
    )
    first_only = brain.estimate_seconds(plan.steps[0].model, history, set())
    assert len(plan.steps) == 2
    assert plan.eta_seconds > first_only        # เวลารวมต้องนับขั้นที่สองด้วย


def test_repeating_a_model_only_pays_the_loading_cost_once():
    """ค่าโหลดโมเดลเป็นค่าใช้จ่ายครั้งเดียว ไม่ใช่ทุกครั้งที่เรียกใช้."""
    history = {"typhoon2-3b-instruct": 10.0}
    cold = brain.estimate_seconds("typhoon2-3b-instruct", history, set())
    warm = brain.estimate_seconds("typhoon2-3b-instruct", history, {"typhoon2-3b-instruct"})
    assert cold + warm < cold * 2


# ── กู้คืนเมื่อหน่วยความจำไม่พอ ───────────────────────────────
@pytest.mark.parametrize("error,expected", [
    ("CUDA out of memory. Tried to allocate 2.0 GiB", True),
    ("torch.cuda.OutOfMemoryError", True),
    ("ModuleNotFoundError: no module named torch", False),
    ("", False),
])
def test_detects_out_of_memory(error, expected):
    assert brain.is_out_of_memory(error) is expected


def test_finds_a_smaller_model_of_the_same_kind():
    smaller = brain.smaller_alternative("qwen2.5-7b-instruct")
    assert smaller is not None
    from server import catalog
    assert catalog.get(smaller)["vram_mb"] < catalog.get("qwen2.5-7b-instruct")["vram_mb"]
    assert catalog.get(smaller)["kind"] == "text"


def test_smallest_model_has_nowhere_to_fall_back_to():
    assert brain.smaller_alternative("sdxl-turbo") is None

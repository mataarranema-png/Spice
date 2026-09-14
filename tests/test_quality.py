"""เทสต์ด่านตรวจคุณภาพ — "เสร็จแล้ว" ไม่ได้แปลว่า "ใช้ได้"."""

import pytest

from server import quality


# ── ข้อความว่าง ──────────────────────────────────────────────
@pytest.mark.parametrize("text", ["", "   ", "\n\n\t"])
def test_catches_empty_answers(text):
    verdict = quality.inspect(text)
    assert verdict.ok is False and verdict.problem == "empty"
    assert verdict.repair["temperature"] >= 0.3      # อุณหภูมิ 0 ทำให้บางโมเดลตัน


# ── วนพูดซ้ำ ─────────────────────────────────────────────────
def test_catches_a_repeating_loop():
    verdict = quality.inspect("สรุปคือ " + "ต้องทำแบบนี้ต่อไป " * 10)
    assert verdict.problem == "repetition"
    assert verdict.repair["repetition_penalty"] > 1


def test_catches_a_loop_of_just_a_few_words():
    verdict = quality.inspect("เริ่มต้นด้วยการเตรียมของ " + "ครับ ได้ ครับ ได้ " * 20)
    assert verdict.problem == "repetition"


def test_normal_repetition_is_not_a_loop():
    """รายการที่ขึ้นต้นเหมือนกันทุกข้อ เป็นเรื่องปกติ ไม่ใช่อาการวนลูป."""
    text = "\n".join(f"- ขั้นตอนที่ {index}: ทำสิ่งที่ {index} ให้เสร็จก่อน" for index in range(1, 12))
    assert quality.inspect(text).ok is True


# ── ถูกตัดกลางคัน ───────────────────────────────────────────
def test_catches_an_answer_cut_off_at_the_token_ceiling():
    verdict = quality.inspect(
        "วิธีทำคือเริ่มจากการเตรียมวัตถุดิบแล้วจึงนำไป",
        meta={"tokens": 512}, payload={"max_tokens": 512},
    )
    assert verdict.problem == "truncated"
    assert verdict.repair["max_tokens"] == 1024      # ขยายให้เป็นสองเท่า


def test_catches_an_unclosed_code_block():
    verdict = quality.inspect(
        "นี่คือโค้ด:\n```python\ndef main():\n    print('hi')",
        meta={"tokens": 256}, payload={"max_tokens": 256},
    )
    assert verdict.problem == "truncated"


def test_a_complete_answer_at_the_ceiling_is_fine():
    """ใช้โควตาหมดพอดีแต่จบประโยคเรียบร้อย ไม่ถือว่าถูกตัด."""
    verdict = quality.inspect(
        "สรุปได้ว่าวิธีนี้ใช้ได้ผลดีที่สุด.",
        meta={"tokens": 512}, payload={"max_tokens": 512},
    )
    assert verdict.ok is True


def test_a_short_answer_is_not_truncated():
    verdict = quality.inspect("ได้ครับ", meta={"tokens": 5}, payload={"max_tokens": 512})
    assert verdict.ok is True


@pytest.mark.parametrize("ending", ["เสร็จแล้ว.", "ทำได้ไหม?", "เยี่ยม!", "จบ。", "ปิดวงเล็บ)"])
def test_thai_sentence_endings_count_as_finished(ending):
    verdict = quality.inspect(
        "เนื้อหายาว ๆ ที่เขียนมาจนจบ " + ending,
        meta={"tokens": 100}, payload={"max_tokens": 100},
    )
    assert verdict.ok is True


def test_an_answer_ending_with_a_closed_code_block_is_finished():
    """คำตอบที่จบด้วยบล็อกโค้ดปิดสนิท ต้องไม่ถูกหาว่าโดนตัด."""
    verdict = quality.inspect(
        "ใช้แบบนี้ครับ\n```python\nprint('hello')\n```",
        meta={"tokens": 100}, payload={"max_tokens": 100},
    )
    assert verdict.ok is True


def test_explains_the_repair_in_plain_words():
    verdict = quality.inspect("ตัดกลางคัน", meta={"tokens": 64}, payload={"max_tokens": 64})
    message = quality.describe_repair(verdict)
    assert "โทเคน" in message and "ลองใหม่" in message

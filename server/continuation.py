"""เขียนต่อจากจุดที่ค้างไว้ แทนที่จะทิ้งงานแล้วเริ่มใหม่ทั้งหมด.

นี่คือสิ่งที่ระบบซึ่ง "ยืมการ์ดจอที่หลุดได้ตลอดเวลา" ต้องมี:

Colab ตัดการเชื่อมต่อกลางคัน คอมที่บ้านหลับ เน็ตหลุด — งานที่เขียนไปแล้ว 80%
ถ้าต้องเริ่มใหม่ตั้งแต่ต้นก็คือเผาเวลา GPU ทิ้งไปเปล่า ๆ ทั้งที่ข้อความที่
สตรีมกลับมาแล้วยังอยู่ครบในฐานข้อมูล

เราจึงเอาข้อความที่ได้มาแล้วนั้นป้อนกลับเข้าไป แล้วบอกโมเดลว่า "เขียนต่อ"
ใช้ได้กับสองสถานการณ์ที่ต่างกันแต่แก้ด้วยกลไกเดียวกัน:

* เครื่องหลุดกลางทาง → เครื่องใหม่เขียนต่อจากตรงที่ค้าง
* คำตอบชนเพดานโทเคน → เขียนต่อให้จบ แทนที่จะสั่งใหม่ด้วยโควตาสองเท่า
  (ซึ่งต้องเขียนส่วนเดิมซ้ำทั้งหมดก่อนถึงจะไปต่อได้)
"""

from __future__ import annotations

# ภาษาไทยไม่เว้นวรรค ตัวอักษรหนึ่งตัวจึงบรรจุเนื้อหามากกว่าภาษาอังกฤษ
# 120 ตัวอักษรไทยคือประโยคเต็ม ๆ สองสามประโยค ซึ่งคุ้มที่จะเก็บไว้เขียนต่อ
MIN_PARTIAL_CHARS = 120      # สั้นกว่านี้ เขียนใหม่เลยคุ้มกว่า
MAX_CONTINUATIONS = 3        # กันวนไม่รู้จบเมื่อโมเดลเขียนไม่จบสักที
TAIL_CHARS = 2_000           # ป้อนท้ายข้อความเท่านี้กลับไปเป็นจุดต่อ
OVERLAP_WINDOW = 400         # ระยะที่ใช้มองหาข้อความซ้ำตอนต่อ

CONTINUE_MARKER = "[[CONTINUE]]"


def overlap_length(prefix: str, addition: str, window: int = OVERLAP_WINDOW) -> int:
    """หาว่าส่วนต้นของข้อความใหม่ ซ้ำกับส่วนท้ายของข้อความเดิมกี่ตัวอักษร.

    โมเดลมักเขียนประโยคสุดท้ายซ้ำอีกรอบก่อนจะไปต่อ ถ้าไม่ตัดทิ้งจะได้
    ข้อความที่อ่านแล้วสะดุด.
    """
    if not prefix or not addition:
        return 0
    tail = prefix[-window:]
    limit = min(len(tail), len(addition))
    for length in range(limit, 0, -1):
        if tail.endswith(addition[:length]):
            return length
    return 0


def stitch(prefix: str, addition: str) -> str:
    """ต่อข้อความสองท่อนโดยไม่ให้ส่วนที่ซ้ำกันโผล่สองรอบ."""
    if not prefix:
        return addition
    if not addition:
        return prefix

    trimmed = addition[overlap_length(prefix, addition):]
    if not trimmed.strip():
        return prefix

    # เว้นวรรคให้เองเมื่อรอยต่อชนกันพอดีโดยไม่มีช่องว่าง
    if prefix[-1].isalnum() and trimmed[0].isalnum():
        return f"{prefix} {trimmed}"
    return prefix + trimmed


def can_continue(kind: str, partial: str, continued: int) -> bool:
    """งานนี้เขียนต่อได้ไหม — หรือควรเริ่มใหม่ให้จบ ๆ ไป."""
    return (
        kind == "text"
        and len(partial.strip()) >= MIN_PARTIAL_CHARS
        and continued < MAX_CONTINUATIONS
    )


def build_payload(payload: dict, partial: str, reason: str) -> dict:
    """ประกอบคำสั่งรอบใหม่ให้เป็น "เขียนต่อ" ไม่ใช่ "เริ่มใหม่"."""
    tail = partial[-TAIL_CHARS:]
    original = payload.get("original_prompt") or payload.get("prompt", "")

    updated = dict(payload)
    updated["original_prompt"] = original
    updated["continue_from"] = tail
    updated["prompt"] = (
        f"{original}\n\n"
        f"--- คุณเขียนคำตอบค้างไว้แค่นี้ ({reason}) ---\n"
        f"{tail}\n"
        f"--- เขียนต่อจากตรงนี้ให้จบ ---\n"
        "เขียนต่อจากคำสุดท้ายข้างบนได้เลย ห้ามทวนสิ่งที่เขียนไปแล้ว "
        "ห้ามขึ้นต้นใหม่ และห้ามเกริ่นนำ"
    )
    # บทสนทนาที่ส่ง messages มา ต้องแก้ข้อความสุดท้ายให้ตรงกันด้วย
    messages = updated.get("messages")
    if messages:
        messages = [dict(item) for item in messages]
        for item in reversed(messages):
            if item.get("role") == "user":
                item["content"] = updated["prompt"]
                break
        updated["messages"] = messages
    return updated


def describe(reason: str, partial: str, continued: int) -> str:
    return (
        f"{reason} — เก็บข้อความที่เขียนไปแล้ว {len(partial):,} ตัวอักษรไว้ "
        f"แล้วสั่งให้เขียนต่อจากจุดนั้น (ครั้งที่ {continued}) "
        "แทนที่จะทิ้งแล้วเริ่มใหม่ทั้งหมด"
    )

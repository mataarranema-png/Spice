"""ด่านตรวจคุณภาพ — จับผลลัพธ์ที่ "เสร็จแล้วแต่ใช้ไม่ได้" แล้วสั่งทำใหม่ให้เอง.

โมเดลภาษาไม่ได้ล้มเหลวแบบโยน error เสมอไป บ่อยครั้งมันคืนค่ามาเป็น
ข้อความว่าง ประโยคที่ถูกตัดกลางคัน หรือวนพูดซ้ำคำเดิมจนจบโควตา
ทั้งสามแบบนี้ระบบเดิมจะนับว่า "สำเร็จ" ทั้งที่ผู้ใช้เอาไปใช้ไม่ได้เลย

ไฟล์นี้ตรวจสามอย่างนั้น แล้วเสนอวิธีแก้ที่ตรงกับอาการ.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# เครื่องหมายที่บอกว่าข้อความ "จบ" จริง ๆ ไม่ได้ถูกตัดกลางคัน
TERMINAL_CHARS = set('.!?"\')]}»”’…', )
TERMINAL_CHARS.update("。！？、」』๚ๆฯ")

CODE_FENCE = "```"
MIN_USEFUL_CHARS = 2


@dataclass
class Verdict:
    ok: bool
    problem: str = ""          # empty | truncated | repetition
    detail: str = ""
    repair: dict | None = None  # พารามิเตอร์ที่ควรเปลี่ยนตอนลองใหม่

    def as_dict(self) -> dict:
        return {"ok": self.ok, "problem": self.problem, "detail": self.detail,
                "repair": self.repair or {}}


def _looks_empty(text: str) -> bool:
    return len(text.strip()) < MIN_USEFUL_CHARS


def _repeating_tail(text: str) -> str:
    """หาข้อความสั้น ๆ ที่ถูกพ่นซ้ำติดกันจนจบ — อาการวนลูปคลาสสิกของโมเดลภาษา."""
    tail = text.rstrip()[-1200:]
    if len(tail) < 40:
        return ""
    for length in range(4, 201):
        chunk = tail[-length:]
        if not chunk.strip():
            continue
        # ซ้ำติดกันอย่างน้อย 4 รอบถึงจะนับว่าวนลูปจริง ไม่ใช่แค่บังเอิญ
        if tail.endswith(chunk * 4):
            return chunk
    return ""


def _word_loop(text: str) -> bool:
    """ท้ายข้อความยาว ๆ ที่ใช้คำซ้ำไม่กี่คำ ก็คืออาการวนลูปเหมือนกัน."""
    words = text.split()
    if len(words) < 60:
        return False
    tail = words[-50:]
    return len(set(tail)) <= 4


def _looks_truncated(text: str, meta: dict, max_tokens: int) -> bool:
    """ถูกตัดกลางคันไหม — ดูทั้งโควตาที่ใช้หมดพอดี และตัวอักษรตัวสุดท้าย."""
    stripped = text.rstrip()
    if not stripped:
        return False

    used = meta.get("tokens")
    hit_ceiling = bool(max_tokens and isinstance(used, int) and used >= max_tokens - 1)
    if not hit_ceiling:
        return False

    fences = stripped.count(CODE_FENCE)
    if fences % 2 == 1:
        return True          # เปิดบล็อกโค้ดค้างไว้ = ยังเขียนไม่จบแน่นอน
    if fences and stripped.endswith(CODE_FENCE):
        return False         # ปิดบล็อกโค้ดเรียบร้อย ถือว่าเขียนจบแล้ว
    return stripped[-1] not in TERMINAL_CHARS


def inspect(text: str, meta: dict | None = None, payload: dict | None = None) -> Verdict:
    """ตรวจผลลัพธ์หนึ่งชิ้น คืนคำตัดสินพร้อมวิธีแก้ถ้ามีปัญหา."""
    meta = meta or {}
    payload = payload or {}
    max_tokens = int(payload.get("max_tokens", 0) or 0)
    temperature = float(payload.get("temperature", 0.6) or 0)

    if _looks_empty(text):
        return Verdict(
            ok=False, problem="empty",
            detail="โมเดลคืนข้อความว่างเปล่า",
            # อุณหภูมิ 0 เป๊ะ ๆ ทำให้บางโมเดลตันแล้วไม่พ่นอะไรออกมาเลย
            repair={"temperature": max(0.3, temperature + 0.3)},
        )

    chunk = _repeating_tail(text)
    if chunk or _word_loop(text):
        sample = (chunk or " ".join(text.split()[-6:]))[:40].replace("\n", " ")
        return Verdict(
            ok=False, problem="repetition",
            detail=f"โมเดลวนพูดซ้ำไม่หยุด (“{sample}…”)",
            repair={
                "repetition_penalty": 1.18,
                "temperature": min(1.2, max(0.5, temperature + 0.25)),
            },
        )

    if _looks_truncated(text, meta, max_tokens):
        return Verdict(
            ok=False, problem="truncated",
            detail=f"คำตอบถูกตัดกลางคันเพราะชนเพดาน {max_tokens} โทเคน",
            repair={"max_tokens": min(8192, max(512, max_tokens * 2))},
        )

    return Verdict(ok=True)


def describe_repair(verdict: Verdict) -> str:
    """ข้อความอธิบายให้ผู้ใช้อ่านรู้เรื่องว่าระบบไปแก้อะไรมา."""
    labels = {
        "max_tokens": "ขยายความยาวคำตอบเป็น {value} โทเคน",
        "temperature": "ปรับความสร้างสรรค์เป็น {value}",
        "repetition_penalty": "เพิ่มการกันพูดซ้ำเป็น {value}",
    }
    changes = [
        labels.get(key, f"{key} = {{value}}").format(value=round(value, 2))
        for key, value in (verdict.repair or {}).items()
    ]
    return f"{verdict.detail} — {' · '.join(changes)} แล้วลองใหม่ให้อัตโนมัติ"

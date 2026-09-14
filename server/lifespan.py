"""ประเมินว่าเครื่องที่ยืมมาจะอยู่กับเราได้อีกนานแค่ไหน.

เครื่องที่ยืมมามีอายุจำกัดเสมอ — Colab ฟรีตัดที่ราว 12 ชั่วโมง คอมที่บ้าน
ก็หลับหรือถูกปิด การจ่ายงานที่ใช้เวลา 1 ชั่วโมงให้เครื่องที่เหลืออายุ 10 นาที
คือการเอางานไปวางบนเครื่องที่รู้ทั้งรู้ว่าจะตายก่อนทำเสร็จ

ระบบจึงประเมินอายุที่เหลือ แล้วให้เครื่องที่ "อยู่ได้นานพอ" รับงานยาวไปก่อน
โดยเรียนรู้อายุจริงจากเครื่องรุ่นก่อน ๆ ของผู้ใช้คนนั้นเอง.
"""

from __future__ import annotations

import statistics
import time

from . import db

HOUR = 3600

# ค่าตั้งต้นก่อนจะมีสถิติของผู้ใช้เอง
DEFAULT_LIFETIME = {
    "colab": 11.5 * HOUR,      # บัญชีฟรีมักถูกตัดราว 12 ชั่วโมง
    "local": 14 * 24 * HOUR,   # คอมตัวเองอยู่ได้ยาว จนกว่าจะปิดเอง
}
MIN_SAMPLES = 2                # มีสถิติของตัวเองอย่างน้อยเท่านี้ถึงจะเชื่อ
SHORT_LIFE_SECONDS = 20 * 60   # เหลือน้อยกว่านี้ = ใกล้หมดเวลาแล้ว
SAFETY_MARGIN = 1.3            # เผื่อไว้ เพราะงานมักใช้เวลานานกว่าที่ประเมิน


def platform_of(worker: dict) -> str:
    """เครื่องนี้เป็น Colab หรือคอมของผู้ใช้เอง — ดูจากชื่อและรันไทม์ที่รายงานมา."""
    haystack = f"{worker.get('name', '')} {worker.get('runtime', '')}".lower()
    return "colab" if "colab" in haystack else "local"


def observed_lifetimes(user_id: int, platform: str) -> list[float]:
    """อายุจริงของเครื่องรุ่นก่อน ๆ ที่ตายไปแล้วของผู้ใช้คนนี้."""
    rows = db.query(
        """SELECT name, runtime, created_at, last_seen_at FROM workers
           WHERE user_id = ? AND last_seen_at > created_at AND last_seen_at < ?""",
        (user_id, time.time() - 300),      # เงียบเกิน 5 นาที ถือว่าจบรอบแล้ว
    )
    return [
        row["last_seen_at"] - row["created_at"]
        for row in rows
        if platform_of(dict(row)) == platform
        and row["last_seen_at"] - row["created_at"] > 5 * 60
    ]


def predicted_lifetime(user_id: int, worker: dict) -> tuple[float, str]:
    """อายุที่คาดว่าเครื่องแบบนี้จะอยู่ได้ พร้อมที่มาของตัวเลข."""
    platform = platform_of(worker)
    samples = observed_lifetimes(user_id, platform)
    if len(samples) >= MIN_SAMPLES:
        # ใช้ค่ากลาง ไม่ใช่ค่าเฉลี่ย เพราะเครื่องที่ตายเร็วผิดปกติหนึ่งตัว
        # ไม่ควรลากค่าประเมินทั้งหมดให้เพี้ยน
        return statistics.median(samples), f"จากอายุจริงของเครื่องก่อนหน้า {len(samples)} ตัว"
    return DEFAULT_LIFETIME[platform], (
        "ค่าประมาณของ Colab บัญชีฟรี" if platform == "colab" else "ค่าประมาณของเครื่องส่วนตัว"
    )


def remaining(user_id: int, worker: dict) -> dict:
    """เหลือเวลาอีกเท่าไหร่ก่อนเครื่องนี้น่าจะหลุด."""
    lifetime, source = predicted_lifetime(user_id, worker)
    age = max(0.0, time.time() - (worker.get("created_at") or time.time()))
    left = max(0.0, lifetime - age)
    return {
        "age_seconds": round(age),
        "lifetime_seconds": round(lifetime),
        "remaining_seconds": round(left),
        "source": source,
        "platform": platform_of(worker),
        "running_out": left < SHORT_LIFE_SECONDS,
    }


def can_finish(expected_seconds: float, remaining_seconds: float) -> bool:
    """เครื่องนี้น่าจะทำงานชิ้นนี้จบก่อนหมดอายุไหม."""
    if not expected_seconds:
        return True
    return expected_seconds * SAFETY_MARGIN <= remaining_seconds


def describe(info: dict) -> str:
    left = info["remaining_seconds"]
    if left > 3 * HOUR:
        return f"น่าจะอยู่ได้อีกหลายชั่วโมง ({info['source']})"
    if left > HOUR:
        return f"เหลืออีกราว {left / HOUR:.1f} ชั่วโมง ({info['source']})"
    if left > 60:
        return f"⚠ เหลืออีกราว {round(left / 60)} นาที — งานยาวจะถูกส่งไปเครื่องอื่นก่อน"
    return "⚠ ใกล้หมดเวลาแล้ว — ระบบจะส่งเฉพาะงานสั้นมาให้"

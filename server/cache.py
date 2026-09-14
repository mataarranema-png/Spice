"""แคชผลลัพธ์ — ถามซ้ำคำเดิม ไม่ต้องจุดการ์ดจอใหม่.

เก็บเฉพาะงานที่ "ถามเหมือนเดิมแล้วควรได้เหมือนเดิม" เท่านั้น คืองานที่ตั้ง
อุณหภูมิต่ำ เช่นแปลภาษา สรุปความ หรือเขียนโค้ด ส่วนงานสร้างสรรค์อย่าง
แต่งกลอนหรือคิดไอเดีย จะไม่ถูกแคช เพราะคนถามซ้ำก็เพราะอยากได้คำตอบใหม่.
"""

from __future__ import annotations

import hashlib
import json
import time

from . import db

# อุณหภูมิสูงกว่านี้ถือว่าผู้ใช้ตั้งใจให้ผลต่างกันทุกครั้ง
CACHEABLE_TEMPERATURE = 0.35
MAX_CACHED_RESULT = 400_000
KEEP_PER_USER = 500


def is_cacheable(payload: dict, kind: str = "text") -> bool:
    if kind not in {"text", "embedding"}:
        return False          # ภาพและเสียงมีสุ่มในตัว ไม่ควรถือว่าเหมือนเดิม
    if payload.get("drive_input"):
        return False          # ไฟล์ต้นทางอาจถูกแก้ไประหว่างนั้น
    return float(payload.get("temperature", 1.0) or 0) <= CACHEABLE_TEMPERATURE


def fingerprint(model: str, payload: dict) -> str:
    """ลายนิ้วมือของ "คำถามเดียวกัน" — ต้องครอบคลุมทุกอย่างที่เปลี่ยนคำตอบได้."""
    material = json.dumps(
        {
            "model": model,
            "prompt": (payload.get("prompt") or "").strip(),
            "system": (payload.get("system") or "").strip(),
            "temperature": round(float(payload.get("temperature", 0) or 0), 3),
            "max_tokens": int(payload.get("max_tokens", 0) or 0),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()


def lookup(user_id: int, key: str) -> dict | None:
    row = db.query_one(
        "SELECT * FROM result_cache WHERE fingerprint = ? AND user_id = ?", (key, user_id)
    )
    return dict(row) if row else None


def record_hit(key: str, saved_seconds: float) -> None:
    db.execute(
        """UPDATE result_cache
           SET hits = hits + 1, last_hit_at = ?, saved_seconds = saved_seconds + ?
           WHERE fingerprint = ?""",
        (time.time(), max(0.0, saved_seconds), key),
    )


def store(user_id: int, key: str, model: str, payload: dict, result: str,
          seconds: float = 0) -> None:
    if not result.strip() or len(result) > MAX_CACHED_RESULT:
        return
    now = time.time()
    db.execute(
        """INSERT INTO result_cache
           (fingerprint, user_id, model, preview, result, hits, saved_seconds, created_at, last_hit_at)
           VALUES (?,?,?,?,?,0,?,?,?)
           ON CONFLICT(fingerprint) DO UPDATE SET
             result = excluded.result, created_at = excluded.created_at""",
        (key, user_id, model, (payload.get("prompt") or "")[:160], result, seconds, now, now),
    )
    _trim(user_id)


def _trim(user_id: int) -> None:
    """เก็บเท่าที่จำเป็น — ทิ้งอันที่เก่าและไม่เคยถูกเรียกใช้ซ้ำก่อน."""
    total = db.query_one(
        "SELECT COUNT(*) AS n FROM result_cache WHERE user_id = ?", (user_id,)
    )["n"]
    if total <= KEEP_PER_USER:
        return
    db.execute(
        """DELETE FROM result_cache WHERE fingerprint IN (
               SELECT fingerprint FROM result_cache WHERE user_id = ?
               ORDER BY hits ASC, last_hit_at ASC LIMIT ?)""",
        (user_id, total - KEEP_PER_USER),
    )


def stats_for(user_id: int) -> dict:
    row = db.query_one(
        """SELECT COUNT(*) AS entries, COALESCE(SUM(hits), 0) AS hits,
                  COALESCE(SUM(saved_seconds), 0) AS saved
           FROM result_cache WHERE user_id = ?""",
        (user_id,),
    )
    return {
        "entries": row["entries"],
        "hits": row["hits"],
        "saved_seconds": round(row["saved"], 1),
    }


def clear_for(user_id: int) -> int:
    total = db.query_one(
        "SELECT COUNT(*) AS n FROM result_cache WHERE user_id = ?", (user_id,)
    )["n"]
    db.execute("DELETE FROM result_cache WHERE user_id = ?", (user_id,))
    return total

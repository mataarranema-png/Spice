"""อ่านข้อความ error แล้วจำว่าครั้งก่อนแก้ยังไงถึงได้ผล.

ระบบที่เจอปัญหาเดิมซ้ำ ๆ แล้วยังงง ๆ ทุกครั้ง คือระบบที่ไม่ได้เรียนรู้อะไรเลย

ไฟล์นี้ทำสองอย่าง:
1. **ย่อ error ให้เป็นลายนิ้วมือ** — ตัดเลข พาธ และที่อยู่หน่วยความจำทิ้ง
   เพื่อให้ "CUDA out of memory. Tried to allocate 2.00 GiB" กับ
   "...allocate 512.00 MiB" ถูกนับว่าเป็นปัญหาเดียวกัน
2. **จำว่าวิธีแก้ไหนได้ผลจริง** — วิธีที่แก้แล้วรอบถัดไปสำเร็จจะถูกใช้ซ้ำ
   ส่วนวิธีที่แก้แล้วยังพังอยู่จะถูกเลิกใช้ไปเอง
"""

from __future__ import annotations

import re
import time

from . import db

# สิ่งที่ต้องตัดทิ้งเพื่อให้ error เดียวกันหน้าตาเหมือนกัน
_NORMALIZERS = (
    (re.compile(r"0x[0-9a-fA-F]+"), "<addr>"),
    (re.compile(r"(/[\w.\-]+){2,}"), "<path>"),
    (re.compile(r"\b\d+(\.\d+)?\s*(GiB|MiB|KiB|GB|MB|KB|bytes)\b", re.I), "<size>"),
    (re.compile(r"\bline \d+"), "line <n>"),
    (re.compile(r"\b\d{3,}\b"), "<n>"),
)

# ความรู้ตั้งต้น — ระบบเริ่มจากตรงนี้แล้วค่อยเรียนรู้เพิ่มเอง
KNOWN_PROBLEMS = (
    ("out_of_memory",
     ("out of memory", "outofmemoryerror", "cuda oom", "not enough memory"),
     "smaller_model",
     "หน่วยความจำ GPU ไม่พอ"),
    ("needs_auth",
     ("401 client error", "403 client error", "gated repo", "authorized",
      "is not a local folder and is not a valid model identifier"),
     "needs_hf_token",
     "โมเดลนี้ต้องขอสิทธิ์ก่อน หรือชื่อโมเดลผิด"),
    ("missing_package",
     ("no module named", "modulenotfounderror", "cannot import name"),
     "retry_elsewhere",
     "เครื่องนั้นยังไม่มีไลบรารีที่ต้องใช้"),
    ("disk_full",
     ("no space left", "disk quota exceeded", "oserror: [errno 28]"),
     "retry_elsewhere",
     "พื้นที่ดิสก์ของเครื่องนั้นเต็ม"),
    ("device_fault",
     ("device-side assert", "cuda error", "illegal memory access", "nvml"),
     "retry_elsewhere",
     "การ์ดจอของเครื่องนั้นมีปัญหา"),
    ("missing_file",
     ("no such file", "filenotfounderror", "ไม่มีอยู่จริง", "เปิดไม่ได้"),
     "check_input",
     "หาไฟล์ต้นทางไม่เจอ"),
    ("network",
     ("connection", "timeout", "timed out", "temporary failure", "ssl"),
     "retry_elsewhere",
     "เครือข่ายของเครื่องนั้นมีปัญหา"),
)

REMEDY_LABELS = {
    "smaller_model": "ลดขนาดโมเดลแล้วลองใหม่",
    "retry_elsewhere": "ส่งไปให้เครื่องอื่นลองทำแทน",
    "needs_hf_token": "ต้องใส่โทเคน Hugging Face หรือแก้ชื่อโมเดล",
    "check_input": "ต้องแก้ไฟล์ต้นทางก่อน",
    "unknown": "ยังไม่รู้วิธีแก้ที่แน่นอน",
}

# วิธีแก้ที่ลองแล้วไม่เวิร์กเกินเท่านี้ครั้ง จะเลิกใช้กับปัญหานั้น
GIVE_UP_AFTER = 3
TRUST_THRESHOLD = 0.5


def signature(error: str) -> str:
    """ย่อ error ให้เหลือแก่น เพื่อให้ปัญหาเดียวกันจับคู่กันได้."""
    text = (error or "").strip().lower()[:400]
    for pattern, replacement in _NORMALIZERS:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s+", " ", text).strip()[:200]


def classify(error: str) -> tuple[str, str, str]:
    """คืน (ชนิดปัญหา, วิธีแก้ตั้งต้น, คำอธิบายภาษาคน)."""
    lowered = (error or "").lower()
    for kind, markers, remedy, explanation in KNOWN_PROBLEMS:
        if any(marker in lowered for marker in markers):
            return kind, remedy, explanation
    return "unknown", "unknown", "ยังไม่เคยเจอปัญหาแบบนี้มาก่อน"


def _row(user_id: int, key: str):
    return db.query_one(
        "SELECT * FROM failure_patterns WHERE user_id = ? AND signature = ?", (user_id, key)
    )


def observe(user_id: int, error: str) -> dict:
    """บันทึกว่าเจอปัญหานี้อีกครั้ง แล้วบอกว่าควรแก้ยังไง."""
    key = signature(error)
    kind, default_remedy, explanation = classify(error)
    now = time.time()
    row = _row(user_id, key)

    if row is None:
        db.execute(
            """INSERT INTO failure_patterns
               (user_id, signature, kind, remedy, occurrences, successes, failures,
                first_seen, last_seen, sample)
               VALUES (?,?,?,?,1,0,0,?,?,?)""",
            (user_id, key, kind, default_remedy, now, now, (error or "")[:400]),
        )
        return {"kind": kind, "remedy": default_remedy, "explanation": explanation,
                "seen_before": False, "occurrences": 1, "learned": False}

    db.execute(
        "UPDATE failure_patterns SET occurrences = occurrences + 1, last_seen = ? "
        "WHERE user_id = ? AND signature = ?",
        (now, user_id, key),
    )

    tried = row["successes"] + row["failures"]
    remedy, learned = row["remedy"], False
    if tried:
        rate = row["successes"] / tried
        if rate >= TRUST_THRESHOLD:
            learned = True                  # วิธีนี้เคยได้ผล ใช้ต่อ
        elif row["failures"] >= GIVE_UP_AFTER:
            remedy = "retry_elsewhere" if row["remedy"] != "retry_elsewhere" else "unknown"
            db.execute(
                "UPDATE failure_patterns SET remedy = ?, successes = 0, failures = 0 "
                "WHERE user_id = ? AND signature = ?",
                (remedy, user_id, key),
            )

    return {
        "kind": row["kind"], "remedy": remedy, "explanation": explanation,
        "seen_before": True, "occurrences": row["occurrences"] + 1,
        "learned": learned,
        "success_rate": round(row["successes"] / tried, 2) if tried else None,
    }


def record_outcome(user_id: int, error: str, worked: bool) -> None:
    """บอกระบบว่าวิธีที่ใช้แก้ปัญหานี้ได้ผลหรือไม่ — นี่คือส่วนที่ทำให้มันฉลาดขึ้น."""
    key = signature(error)
    column = "successes" if worked else "failures"
    db.execute(
        f"UPDATE failure_patterns SET {column} = {column} + 1 "
        "WHERE user_id = ? AND signature = ?",
        (user_id, key),
    )


def describe(diagnosis: dict) -> str:
    remedy = REMEDY_LABELS.get(diagnosis["remedy"], diagnosis["remedy"])
    if not diagnosis["seen_before"]:
        return f"{diagnosis['explanation']} — {remedy}"
    times = diagnosis["occurrences"]
    if diagnosis.get("learned"):
        rate = diagnosis.get("success_rate")
        return (f"{diagnosis['explanation']} · เคยเจอมาแล้ว {times} ครั้ง "
                f"และวิธีนี้เคยแก้ได้ {rate:.0%} — {remedy}")
    return f"{diagnosis['explanation']} · เจอเป็นครั้งที่ {times} — {remedy}"


def history_for(user_id: int, limit: int = 20) -> list[dict]:
    rows = db.query(
        """SELECT * FROM failure_patterns WHERE user_id = ?
           ORDER BY occurrences DESC, last_seen DESC LIMIT ?""",
        (user_id, limit),
    )
    return [
        {
            "kind": row["kind"],
            "remedy": REMEDY_LABELS.get(row["remedy"], row["remedy"]),
            "occurrences": row["occurrences"],
            "successes": row["successes"],
            "failures": row["failures"],
            "success_rate": (round(row["successes"] / (row["successes"] + row["failures"]), 2)
                             if row["successes"] + row["failures"] else None),
            "sample": row["sample"],
            "last_seen": row["last_seen"],
        }
        for row in rows
    ]

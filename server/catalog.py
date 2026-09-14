"""แค็ตตาล็อกโมเดล — รวมโมเดลที่มีมาให้ กับโมเดลที่ผู้ใช้ดึงมาเองจาก Hugging Face.

`get()` หาโมเดลได้จากทั้งสองแหล่ง ทุกส่วนของระบบจึงเรียกใช้เหมือนกันหมด
ไม่ว่าจะเป็นโมเดลในตัวหรือโมเดลที่ผู้ใช้เพิ่มเข้ามาเอง.
"""

from __future__ import annotations

import json
import sqlite3

MODELS: list[dict] = [
    {
        "id": "qwen2.5-7b-instruct",
        "params_b": 7.6,
        "label": "Qwen2.5 7B Instruct",
        "kind": "text",
        "repo": "Qwen/Qwen2.5-7B-Instruct",
        "vram_mb": 15000,
        "quantize": "4bit",
        "tags": ["ไทย/อังกฤษ", "ตอบทั่วไป", "เขียนโค้ด"],
        "blurb": "ตัวหลักอเนกประสงค์ โหลดแบบ 4bit แล้วพอดี T4 (16GB)",
    },
    {
        "id": "typhoon2-3b-instruct",
        "params_b": 3.2,
        "label": "Typhoon 2 3B (ไทย)",
        "kind": "text",
        "repo": "scb10x/llama3.2-typhoon2-3b-instruct",
        "vram_mb": 7000,
        "quantize": "fp16",
        "tags": ["ภาษาไทย", "เบา", "เร็ว"],
        "blurb": "โมเดลภาษาไทยขนาดเล็ก ตอบไว เหมาะกับงานสรุป/แชท",
    },
    {
        "id": "llama-3.2-3b-instruct",
        "params_b": 3.2,
        "label": "Llama 3.2 3B Instruct",
        "kind": "text",
        "repo": "meta-llama/Llama-3.2-3B-Instruct",
        "vram_mb": 7000,
        "quantize": "fp16",
        "tags": ["ทั่วไป", "เบา"],
        "blurb": "เล็ก เร็ว ประหยัด VRAM เหมาะเป็นตัวตั้งต้น",
    },
    {
        "id": "sdxl-turbo",
        "params_b": 2.6,
        "label": "SDXL Turbo (สร้างภาพ)",
        "kind": "image",
        "repo": "stabilityai/sdxl-turbo",
        "vram_mb": 9000,
        "quantize": "fp16",
        "tags": ["ภาพ", "1 step", "เร็วมาก"],
        "blurb": "สร้างภาพจากข้อความในไม่กี่วินาทีบน T4",
    },
    {
        "id": "whisper-large-v3-turbo",
        "params_b": 0.81,
        "label": "Whisper large-v3-turbo (ถอดเสียง)",
        "kind": "audio",
        "repo": "openai/whisper-large-v3-turbo",
        "vram_mb": 8000,
        "quantize": "fp16",
        "tags": ["เสียง→ข้อความ", "ไทยแม่น"],
        "blurb": "ถอดเสียงไฟล์จาก Google Drive ได้ตรง ๆ",
    },
    {
        "id": "bge-m3",
        "params_b": 0.57,
        "label": "BGE-M3 (ทำ Embedding)",
        "kind": "embedding",
        "repo": "BAAI/bge-m3",
        "vram_mb": 4000,
        "quantize": "fp16",
        "tags": ["เวกเตอร์", "หลายภาษา", "1024 มิติ"],
        "blurb": "แปลงเอกสารเป็นเวกเตอร์เข้าคลัง Vault เพื่อค้นหาเชิงความหมาย",
    },
]

BY_ID = {model["id"]: model for model in MODELS}
KINDS = sorted({model["kind"] for model in MODELS})


def _row_to_model(row) -> dict:
    try:
        tags = json.loads(row["tags"])
    except (ValueError, TypeError):
        tags = []
    return {
        "id": row["id"],
        "label": row["label"] or row["repo"].split("/")[-1],
        "kind": row["kind"],
        "repo": row["repo"],
        "vram_mb": row["vram_mb"],
        "quantize": row["quantize"],
        "tags": tags,
        "blurb": row["blurb"],
        "custom": True,
        "params_b": row["params_b"],
        "gated": bool(row["gated"]),
        "trust_remote_code": bool(row["trust_remote_code"]),
        "downloads": row["downloads"],
        "likes": row["likes"],
        "owner_id": row["user_id"],
        "url": f"https://huggingface.co/{row['repo']}",
    }


def _custom(model_id: str) -> dict | None:
    """ค้นโมเดลที่ผู้ใช้เพิ่มเอง — เงียบไว้ถ้ายังไม่มีฐานข้อมูล (เช่นตอนเทสต์ล้วน ๆ)."""
    from . import db          # นำเข้าตรงนี้เพื่อเลี่ยงการพึ่งพากันเป็นวง

    try:
        row = db.query_one("SELECT * FROM custom_models WHERE id = ?", (model_id,))
    except sqlite3.Error:
        return None
    return _row_to_model(row) if row else None


def get(model_id: str) -> dict | None:
    """หาโมเดลจากแค็ตตาล็อกในตัวก่อน แล้วค่อยหาจากที่ผู้ใช้เพิ่มเอง."""
    if model_id in BY_ID:
        return BY_ID[model_id]
    return _custom(model_id)


def custom_models_for(user_id: int) -> list[dict]:
    from . import db

    try:
        rows = db.query(
            "SELECT * FROM custom_models WHERE user_id = ? ORDER BY added_at DESC", (user_id,)
        )
    except sqlite3.Error:
        return []
    return [_row_to_model(row) for row in rows]


def models_for(user_id: int | None = None) -> list[dict]:
    """รายการโมเดลทั้งหมดที่ผู้ใช้คนนี้ใช้ได้จริง."""
    if user_id is None:
        return list(MODELS)
    return [*MODELS, *custom_models_for(user_id)]


def owns(model_id: str, user_id: int) -> bool:
    """โมเดลในตัวใช้ได้ทุกคน ส่วนโมเดลที่เพิ่มเองใช้ได้เฉพาะเจ้าของ."""
    if model_id in BY_ID:
        return True
    model = _custom(model_id)
    return bool(model) and model["owner_id"] == user_id


def fits(model_id: str, vram_mb: int) -> bool:
    model = get(model_id)
    return bool(model) and vram_mb >= model["vram_mb"]

"""แค็ตตาล็อกโมเดลที่ worker รันได้ — ใช้ทั้งหน้าเว็บและตัวตรวจสอบคำสั่งงาน."""

from __future__ import annotations

MODELS: list[dict] = [
    {
        "id": "qwen2.5-7b-instruct",
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


def get(model_id: str) -> dict | None:
    return BY_ID.get(model_id)


def fits(model_id: str, vram_mb: int) -> bool:
    model = BY_ID.get(model_id)
    return bool(model) and vram_mb >= model["vram_mb"]

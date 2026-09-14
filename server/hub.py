"""เชื่อมกับ Hugging Face Hub — ค้นหา ตรวจสเปก และประเมินว่าการ์ดจอคุณรันไหวไหม.

จุดสำคัญคือ **บอกให้รู้ก่อนดาวน์โหลด** ว่าโมเดลตัวนั้นจะลง VRAM ได้หรือไม่
เพราะการโหลดน้ำหนักโมเดลสิบกว่ากิกะไบต์มาแล้วเจอ CUDA out of memory
คือการเสียเวลาที่เจ็บที่สุดในงานสายนี้.
"""

from __future__ import annotations

import re
import unicodedata

import httpx

HF_API = "https://huggingface.co/api"
TIMEOUT = 25

# จำนวนไบต์ต่อหนึ่งพารามิเตอร์ ตามวิธีบีบอัดที่เลือก
BYTES_PER_PARAM = {
    "fp32": 4.0,
    "fp16": 2.0,
    "bf16": 2.0,
    "8bit": 1.0,
    "4bit": 0.55,      # nf4 + double quant ตามที่วัดได้จริง
}

OVERHEAD_RATIO = 1.2       # KV cache + activation ระหว่างรัน
CUDA_CONTEXT_MB = 800      # ที่ CUDA จองไว้เองเสมอ

# pipeline_tag ของ HF → ชนิดงานในระบบเรา
KIND_BY_PIPELINE = {
    "text-generation": "text",
    "text2text-generation": "text",
    "conversational": "text",
    "image-text-to-text": "text",
    "text-to-image": "image",
    "image-to-image": "image",
    "automatic-speech-recognition": "audio",
    "audio-classification": "audio",
    "feature-extraction": "embedding",
    "sentence-similarity": "embedding",
}

# รูปแบบไฟล์ที่ตัวแทนเครื่องของเรา (ใช้ transformers/diffusers) โหลดไม่ได้
UNSUPPORTED_FORMATS = {
    "gguf": "ไฟล์ GGUF ใช้กับ llama.cpp/Ollama ไม่ใช่ transformers — เลือกรุ่นที่เป็น safetensors แทน",
    "mlx": "รุ่น MLX ทำมาสำหรับชิป Apple ไม่ใช่การ์ดจอ NVIDIA",
    "openvino": "รุ่น OpenVINO ทำมาสำหรับ Intel ไม่ใช่ CUDA",
    "tflite": "รุ่น TFLite ใช้กับมือถือ ไม่ใช่การ์ดจอ",
}

SIZE_IN_NAME = re.compile(r"(\d+(?:\.\d+)?)\s*([bm])(?![a-z0-9])", re.IGNORECASE)
# รุ่น Mixture-of-Experts เขียนขนาดแบบ "8x7B" ซึ่งถ้าอ่านเป็น 7B จะพลาดมาก
MOE_IN_NAME = re.compile(r"(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*b(?![a-z0-9])", re.IGNORECASE)
MOE_SHARED_RATIO = 0.85   # ผู้เชี่ยวชาญแต่ละตัวใช้ชั้น attention ร่วมกัน จึงไม่ได้คูณเต็ม


# ── ประเมินขนาดและความต้องการ VRAM ───────────────────────────
def params_from_name(repo: str) -> float:
    """เดาจำนวนพารามิเตอร์จากชื่อโมเดล เช่น 'Llama-3-8B' → 8.0 (หน่วยพันล้าน).

    ใช้เมื่อ HF ไม่ได้บอกจำนวนพารามิเตอร์มาตรง ๆ ซึ่งเกิดขึ้นบ่อยกับ
    รุ่นที่คนทั่วไปอัปโหลดเอง — และชื่อโมเดลแทบทุกตัวบอกขนาดไว้อยู่แล้ว.
    """
    name = repo.split("/")[-1]

    # ต้องเช็ก MoE ก่อน ไม่งั้น "8x7B" จะถูกอ่านเป็น 7B แล้วบอกผู้ใช้ผิดว่าลง T4 ได้
    moe = MOE_IN_NAME.search(name)
    if moe:
        experts, size = int(moe.group(1)), float(moe.group(2))
        total = experts * size * MOE_SHARED_RATIO
        if 0.01 <= total <= 2000:
            return round(total, 1)

    best = 0.0
    for value, unit in SIZE_IN_NAME.findall(name):
        billions = float(value) / 1000 if unit.lower() == "m" else float(value)
        # ตัดเลขที่ชัดว่าไม่ใช่ขนาดโมเดล เช่น "v2.5b" หรือเลขเวอร์ชัน
        if 0.01 <= billions <= 2000:
            best = max(best, billions)
    return best


def estimate_vram_mb(params_b: float, quantize: str = "fp16") -> int:
    """ประเมิน VRAM ที่ต้องใช้ตอนรันจริง (น้ำหนักโมเดล + ที่เผื่อระหว่างรัน)."""
    if params_b <= 0:
        return 0
    per_param = BYTES_PER_PARAM.get(quantize, 2.0)
    weights_mb = params_b * 1e9 * per_param / 1024**2
    return int(weights_mb * OVERHEAD_RATIO + CUDA_CONTEXT_MB)


def suggest_quantize(params_b: float, vram_mb: int) -> str:
    """เลือกวิธีบีบอัดที่เล็กที่สุดเท่าที่ยัง 'พอดี' กับการ์ดที่มี."""
    if params_b <= 0:
        return "fp16"
    for option in ("fp16", "8bit", "4bit"):
        if not vram_mb or estimate_vram_mb(params_b, option) <= vram_mb:
            return option
    return "4bit"


def detect_kind(info: dict) -> str:
    pipeline = (info.get("pipeline_tag") or "").lower()
    if pipeline in KIND_BY_PIPELINE:
        return KIND_BY_PIPELINE[pipeline]

    tags = {str(tag).lower() for tag in info.get("tags", [])}
    if tags & {"diffusers", "stable-diffusion", "text-to-image"}:
        return "image"
    if tags & {"whisper", "automatic-speech-recognition"}:
        return "audio"
    if tags & {"sentence-transformers", "feature-extraction"}:
        return "embedding"
    return "text"


def unsupported_reason(info: dict) -> str:
    """โมเดลนี้รูปแบบใช้กับเครื่องเราไม่ได้หรือเปล่า — บอกตั้งแต่ก่อนกดเพิ่ม."""
    haystack = {str(tag).lower() for tag in info.get("tags", [])}
    haystack.add((info.get("modelId") or info.get("id") or "").lower())
    for marker, reason in UNSUPPORTED_FORMATS.items():
        if any(marker in item for item in haystack):
            return reason
    return ""


def params_from_info(info: dict) -> float:
    """จำนวนพารามิเตอร์จาก metadata ของ HF ถ้าไม่มีค่อยเดาจากชื่อ."""
    safetensors = info.get("safetensors") or {}
    total = safetensors.get("total")
    if isinstance(total, (int, float)) and total > 0:
        return round(total / 1e9, 3)

    parameters = safetensors.get("parameters")
    if isinstance(parameters, dict):
        summed = sum(value for value in parameters.values() if isinstance(value, (int, float)))
        if summed > 0:
            return round(summed / 1e9, 3)

    return params_from_name(info.get("modelId") or info.get("id") or "")


def slugify(repo: str) -> str:
    """แปลง 'owner/Model-Name' เป็น id ที่ใช้ใน URL และฐานข้อมูลได้อย่างปลอดภัย."""
    normalized = unicodedata.normalize("NFKD", repo).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return f"hf--{slug}"[:120]


def describe(info: dict, quantize: str = "", vram_budget_mb: int = 0) -> dict:
    """สรุปข้อมูลโมเดลหนึ่งตัวให้อยู่ในรูปที่ระบบเราใช้ต่อได้ทันที."""
    repo = info.get("modelId") or info.get("id") or ""
    params_b = params_from_info(info)
    kind = detect_kind(info)
    chosen = quantize or suggest_quantize(params_b, vram_budget_mb)
    vram_mb = estimate_vram_mb(params_b, chosen)
    tags = [str(tag) for tag in info.get("tags", []) if ":" not in str(tag)][:8]

    return {
        "id": slugify(repo),
        "repo": repo,
        "label": repo.split("/")[-1],
        "owner": repo.split("/")[0] if "/" in repo else "",
        "kind": kind,
        "quantize": chosen,
        "params_b": params_b,
        "vram_mb": vram_mb,
        "vram_by_quantize": {
            option: estimate_vram_mb(params_b, option) for option in ("fp16", "8bit", "4bit")
        },
        "downloads": info.get("downloads", 0),
        "likes": info.get("likes", 0),
        "gated": bool(info.get("gated")),
        "private": bool(info.get("private")),
        "tags": tags,
        "pipeline_tag": info.get("pipeline_tag", ""),
        "updated_at": info.get("lastModified", ""),
        "unsupported": unsupported_reason(info),
        "fits": bool(vram_budget_mb and vram_mb and vram_mb <= vram_budget_mb),
        "url": f"https://huggingface.co/{repo}",
    }


# ── คุยกับ Hugging Face ──────────────────────────────────────
def _headers(token: str = "") -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


async def search(
    query: str, kind: str = "", limit: int = 20, token: str = "", vram_budget_mb: int = 0
) -> list[dict]:
    """ค้นหาโมเดลบน Hugging Face แล้วแปลงผลให้อยู่ในรูปของระบบเรา."""
    params: dict = {
        "search": query,
        "limit": max(1, min(limit, 50)),
        "sort": "downloads",
        "direction": -1,
        "full": "true",
    }
    pipelines = [
        pipeline for pipeline, mapped in KIND_BY_PIPELINE.items() if mapped == kind
    ]
    if pipelines:
        params["filter"] = pipelines[0]

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{HF_API}/models", params=params, headers=_headers(token))
    response.raise_for_status()

    results = [describe(item, vram_budget_mb=vram_budget_mb) for item in response.json()]
    return [item for item in results if item["repo"]]


async def model_info(repo: str, token: str = "") -> dict:
    """ดึงรายละเอียดของโมเดลตัวเดียว (ใช้ตอนกดเพิ่มเข้าคลังของเรา)."""
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        response = await client.get(f"{HF_API}/models/{repo}", headers=_headers(token))

    if response.status_code == 404:
        raise ValueError(f"ไม่พบโมเดล '{repo}' บน Hugging Face (สะกดถูกไหม?)")
    if response.status_code in (401, 403):
        raise ValueError(
            f"โมเดล '{repo}' เป็นแบบต้องขอสิทธิ์หรือเป็นของส่วนตัว — "
            "กดยอมรับเงื่อนไขบนหน้า Hugging Face แล้วใส่ HF token ในหน้าตั้งค่าก่อน"
        )
    response.raise_for_status()
    return response.json()

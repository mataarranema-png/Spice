"""คลังโมเดลของผู้ใช้ — ค้นหาและดึงโมเดลจาก Hugging Face มาใช้เองได้ทุกตัว."""

from __future__ import annotations

import json
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, catalog, db, hub, scheduler
from ..security import decrypt, encrypt
from .workers import authed_worker

router = APIRouter(prefix="/api/v1/hub", tags=["hub"])

# จุดตั้งต้นให้คนที่ยังไม่รู้จะเริ่มจากตรงไหน — ทั้งหมดเป็นโมเดลน้ำหนักเปิด
# ที่โหลดได้ทันทีบน Colab T4 โดยไม่ต้องขอสิทธิ์
PRESETS = [
    {
        "group": "ไม่มีการเซ็นเซอร์ / ตอบตรงไปตรงมา",
        "note": "รุ่นที่ถูกถอดการปฏิเสธออก ตอบตามที่สั่งโดยไม่บ่ายเบี่ยง",
        "models": [
            {"repo": "huihui-ai/Llama-3.2-3B-Instruct-abliterated",
             "why": "เล็ก เร็ว ลง T4 สบาย เหมาะเริ่มต้น"},
            {"repo": "huihui-ai/Qwen2.5-7B-Instruct-abliterated",
             "why": "ฉลาดกว่า รองรับไทยดี ใช้ 4bit บน T4"},
            {"repo": "cognitivecomputations/dolphin-2.9.4-llama3.1-8b",
             "why": "สายทำงาน เขียนโค้ดดี ไม่ค่อยปฏิเสธ"},
            {"repo": "mlabonne/NeuralDaredevil-8B-abliterated",
             "why": "คะแนนวัดผลสูงในกลุ่มเดียวกัน"},
        ],
    },
    {
        "group": "ภาษาไทย",
        "note": "เข้าใจบริบทและสำนวนไทยได้ดีกว่าโมเดลทั่วไป",
        "models": [
            {"repo": "scb10x/llama3.2-typhoon2-3b-instruct", "why": "เล็ก เร็ว ไทยแม่น"},
            {"repo": "scb10x/llama3.1-typhoon2-8b-instruct", "why": "ไทยดีขึ้นอีก ใช้ 4bit บน T4"},
        ],
    },
    {
        "group": "เขียนโค้ด",
        "note": "ฝึกมาเพื่องานโปรแกรมโดยเฉพาะ",
        "models": [
            {"repo": "Qwen/Qwen2.5-Coder-7B-Instruct", "why": "แรงที่สุดในขนาดนี้"},
            {"repo": "deepseek-ai/deepseek-coder-6.7b-instruct", "why": "เก่งเรื่องเติมโค้ด"},
        ],
    },
    {
        "group": "สร้างภาพ",
        "note": "ทำงานได้บน T4",
        "models": [
            {"repo": "stabilityai/sdxl-turbo", "why": "เร็วมาก 1–2 step"},
            {"repo": "SG161222/Realistic_Vision_V6.0_B1_noVAE", "why": "ภาพสมจริง ไม่กรองเนื้อหา"},
        ],
    },
]


class AddModelRequest(BaseModel):
    repo: str = Field(min_length=3, max_length=200)
    quantize: str = ""
    trust_remote_code: bool = False
    label: str = Field(default="", max_length=80)


class TokenRequest(BaseModel):
    token: str = Field(default="", max_length=200)


def hf_token_for(user_id: int) -> str:
    row = db.query_one("SELECT hf_token FROM user_secrets WHERE user_id = ?", (user_id,))
    return decrypt(row["hf_token"]) if row else ""


# ── ค้นหาบน Hugging Face ─────────────────────────────────────
@router.get("/search")
async def search_models(
    q: str = "", kind: str = "", limit: int = 24, user: dict = Depends(auth.require_user)
) -> dict:
    if not q.strip():
        raise HTTPException(400, "ใส่คำค้นก่อน เช่นชื่อโมเดลหรือชื่อผู้สร้าง")

    capacity = scheduler.capacity_for(user["id"])
    try:
        results = await hub.search(
            q.strip(), kind=kind, limit=limit,
            token=hf_token_for(user["id"]), vram_budget_mb=capacity["best_vram_mb"],
        )
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"ติดต่อ Hugging Face ไม่สำเร็จ: {exc}") from exc

    owned = {model["repo"] for model in catalog.custom_models_for(user["id"])}
    builtin = {model["repo"] for model in catalog.MODELS}
    for item in results:
        item["already_added"] = item["repo"] in owned or item["repo"] in builtin

    return {
        "results": results,
        "vram_budget_mb": capacity["best_vram_mb"],
        "count": len(results),
    }


@router.get("/presets")
def presets(user: dict = Depends(auth.require_user)) -> dict:
    owned = {model["repo"] for model in catalog.custom_models_for(user["id"])}
    builtin = {model["repo"] for model in catalog.MODELS}
    groups = []
    for group in PRESETS:
        groups.append({
            **group,
            "models": [
                {**model, "already_added": model["repo"] in owned or model["repo"] in builtin}
                for model in group["models"]
            ],
        })
    return {"groups": groups}


# ── คลังโมเดลของผู้ใช้ ───────────────────────────────────────
@router.get("/models")
def list_models(user: dict = Depends(auth.require_user)) -> dict:
    capacity = scheduler.capacity_for(user["id"])
    budget = capacity["best_vram_mb"]
    models = []
    for model in catalog.custom_models_for(user["id"]):
        models.append({
            **model,
            "fits": bool(budget and model["vram_mb"] <= budget),
            "vram_by_quantize": {
                option: hub.estimate_vram_mb(model["params_b"], option)
                for option in ("fp16", "8bit", "4bit")
            },
        })
    return {
        "models": models,
        "builtin": catalog.MODELS,
        "vram_budget_mb": budget,
        "has_hf_token": bool(hf_token_for(user["id"])),
    }


@router.post("/models")
async def add_model(body: AddModelRequest, user: dict = Depends(auth.require_user)) -> dict:
    repo = body.repo.strip().strip("/")
    if repo.startswith("http"):
        # รับลิงก์ที่ก๊อปมาจากเบราว์เซอร์ได้เลย
        repo = repo.split("huggingface.co/")[-1].split("?")[0].strip("/")
    if repo.count("/") != 1:
        raise HTTPException(400, "รูปแบบต้องเป็น owner/model เช่น cognitivecomputations/dolphin-2.9.4-llama3.1-8b")

    token = hf_token_for(user["id"])
    try:
        info = await hub.model_info(repo, token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"ติดต่อ Hugging Face ไม่สำเร็จ: {exc}") from exc

    capacity = scheduler.capacity_for(user["id"])
    described = hub.describe(info, body.quantize, capacity["best_vram_mb"])

    if described["unsupported"]:
        raise HTTPException(400, described["unsupported"])
    if described["gated"] and not token:
        raise HTTPException(
            400,
            f"โมเดลนี้ต้องขอสิทธิ์ก่อน — ไปกดยอมรับเงื่อนไขที่ {described['url']} "
            "แล้วใส่ HF token ในหน้าคลังโมเดล",
        )

    now = time.time()
    blurb = (
        f"ดึงมาจาก Hugging Face · {described['params_b']}B พารามิเตอร์"
        if described["params_b"] else "ดึงมาจาก Hugging Face"
    )
    db.execute(
        """INSERT INTO custom_models
           (id, user_id, repo, label, kind, quantize, vram_mb, params_b, blurb, tags,
            gated, trust_remote_code, downloads, likes, added_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(user_id, repo) DO UPDATE SET
             quantize=excluded.quantize, vram_mb=excluded.vram_mb,
             trust_remote_code=excluded.trust_remote_code, label=excluded.label,
             params_b=excluded.params_b, tags=excluded.tags, added_at=excluded.added_at""",
        (
            described["id"], user["id"], repo, body.label.strip() or described["label"],
            described["kind"], described["quantize"], described["vram_mb"],
            described["params_b"], blurb, json.dumps(described["tags"], ensure_ascii=False),
            int(described["gated"]), int(body.trust_remote_code),
            described["downloads"], described["likes"], now,
        ),
    )
    db.log_audit(user["id"], "model.add", repo)

    warnings = []
    if not described["fits"] and capacity["best_vram_mb"]:
        warnings.append(
            f"ประเมินว่าต้องใช้ VRAM ราว {described['vram_mb']} MB แต่เครื่องที่ออนไลน์มี "
            f"{capacity['best_vram_mb']} MB — ลองเปลี่ยนเป็น 4bit หรือเชื่อมเครื่องที่ใหญ่กว่า"
        )
    if not described["params_b"]:
        warnings.append("อ่านขนาดโมเดลไม่ได้ ค่า VRAM ที่ประเมินจึงอาจคลาดเคลื่อน")
    if body.trust_remote_code:
        warnings.append(
            "เปิด trust_remote_code ไว้ — โค้ดจากผู้สร้างโมเดลจะถูกรันบนเครื่องที่ "
            "เมานต์ Google Drive ของคุณอยู่ เปิดเฉพาะกับผู้สร้างที่คุณเชื่อถือจริง ๆ"
        )

    return {"ok": True, "model": described, "warnings": warnings}


@router.delete("/models/{model_id}")
def remove_model(model_id: str, user: dict = Depends(auth.require_user)) -> dict:
    row = db.query_one(
        "SELECT repo FROM custom_models WHERE id = ? AND user_id = ?", (model_id, user["id"])
    )
    if row is None:
        raise HTTPException(404, "ไม่พบโมเดลนี้ในคลังของคุณ")
    db.execute("DELETE FROM custom_models WHERE id = ? AND user_id = ?", (model_id, user["id"]))
    db.log_audit(user["id"], "model.remove", row["repo"])
    return {"ok": True}


# ── โทเคน Hugging Face (สำหรับโมเดลที่ต้องขอสิทธิ์) ───────────
@router.get("/token")
def token_status(user: dict = Depends(auth.require_user)) -> dict:
    token = hf_token_for(user["id"])
    return {
        "has_token": bool(token),
        "masked": f"{token[:3]}…{token[-4:]}" if len(token) > 8 else "",
    }


@router.put("/token")
def save_token(body: TokenRequest, user: dict = Depends(auth.require_user)) -> dict:
    token = body.token.strip()
    now = time.time()
    if not token:
        db.execute("DELETE FROM user_secrets WHERE user_id = ?", (user["id"],))
        db.log_audit(user["id"], "hf_token.clear", "")
        return {"ok": True, "has_token": False}

    if not token.startswith("hf_"):
        raise HTTPException(400, "โทเคนของ Hugging Face ขึ้นต้นด้วย hf_ เสมอ")

    db.execute(
        """INSERT INTO user_secrets (user_id, hf_token, updated_at) VALUES (?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET hf_token=excluded.hf_token,
                                              updated_at=excluded.updated_at""",
        (user["id"], encrypt(token), now),
    )
    db.log_audit(user["id"], "hf_token.save", "")
    return {"ok": True, "has_token": True}


@router.get("/worker/token")
def worker_hf_token(worker: dict = Depends(authed_worker)) -> dict:
    """ให้เครื่องที่จับคู่แล้วดึงโทเคนของเจ้าของไปใช้โหลดโมเดลที่ต้องขอสิทธิ์."""
    return {"hf_token": hf_token_for(worker["user_id"])}

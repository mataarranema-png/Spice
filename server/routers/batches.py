"""งานชุด — สั่งครั้งเดียว แตกเป็นหลายงานวิ่งขนานกันทุกเครื่องที่มี."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, brain, catalog, db, events, pipeline, scheduler

router = APIRouter(prefix="/api/v1/batches", tags=["batches"])

MAX_ITEMS = 200
PLACEHOLDER = "{{item}}"


class BatchRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16_000)
    items: list[str] = Field(default_factory=list)
    model: str = "auto"
    title: str = Field(default="", max_length=120)
    priority: int = Field(default=6, ge=1, le=9)
    drive_output: str = Field(default="", max_length=500)
    as_drive_files: bool = False      # ถือว่าแต่ละรายการเป็นไฟล์ใน Drive


@router.post("")
def create_batch(body: BatchRequest, user: dict = Depends(auth.require_user)) -> dict:
    items = [item.strip() for item in body.items if item.strip()][:MAX_ITEMS]
    if not items:
        raise HTTPException(400, "ใส่รายการที่จะให้ทำอย่างน้อยหนึ่งอย่าง")
    if PLACEHOLDER not in body.prompt and not body.as_drive_files:
        raise HTTPException(
            400, f"ใส่ {PLACEHOLDER} ในคำสั่งเพื่อบอกว่าจะเอาแต่ละรายการไปแทนตรงไหน"
        )

    capacity = scheduler.capacity_for(user["id"])
    history = scheduler.history_for(user["id"])
    models = catalog.models_for(user["id"])

    sample = body.prompt.replace(PLACEHOLDER, items[0])
    if body.model in {"", "auto"}:
        intent = brain.analyze(sample, items[0] if body.as_drive_files else "")
        model_id, reason, _ = brain.pick_model(intent, capacity, models)
        max_tokens, temperature = intent.max_tokens, intent.temperature
    else:
        model = catalog.get(body.model)
        if model is None or not catalog.owns(body.model, user["id"]):
            raise HTTPException(400, f"ใช้โมเดล '{body.model}' ไม่ได้")
        model_id, reason = body.model, "ผู้ใช้เลือกโมเดลเอง"
        max_tokens, temperature = 1024, 0.5

    now = time.time()
    batch_id = f"bt_{uuid.uuid4().hex[:12]}"
    title = body.title.strip() or f"งานชุด {len(items)} รายการ"
    db.execute(
        "INSERT INTO batches (id, user_id, title, total, created_at) VALUES (?,?,?,?,?)",
        (batch_id, user["id"], title, len(items), now),
    )

    per_item = brain.estimate_seconds(model_id, history, set(capacity["warm"]))
    parallel = max(1, capacity["online"])
    job_ids = []
    for index, item in enumerate(items, 1):
        step = {
            "kind": catalog.get(model_id)["kind"],
            "model": model_id,
            "title": f"[{index}/{len(items)}] {item[:48]}",
            "prompt": body.prompt.replace(PLACEHOLDER, item),
            "max_tokens": max_tokens, "temperature": temperature,
            "drive_input": item if body.as_drive_files else "",
            "drive_output": body.drive_output,
        }
        job_ids.append(pipeline.create_job(
            user["id"], step, batch_id=batch_id, priority=body.priority,
            plan={"reason": reason, "steps": [step], "batch": True},
            eta_seconds=per_item,
            log_message=f"รายการที่ {index} จาก {len(items)} ของงานชุด",
        ))

    events.publish(user["id"], "batch",
                   {"action": "created", "batch_id": batch_id, "total": len(items)})
    return {
        "batch_id": batch_id,
        "total": len(items),
        "job_ids": job_ids,
        "model": model_id,
        "reason": reason,
        # หลายเครื่องช่วยกันทำ เวลารวมจึงหารตามจำนวนเครื่องที่ออนไลน์
        "eta_seconds": round(per_item * len(items) / parallel, 1),
        "workers": capacity["online"],
    }


def batch_progress(batch_id: str, user_id: int) -> dict:
    row = db.query_one(
        "SELECT * FROM batches WHERE id = ? AND user_id = ?", (batch_id, user_id)
    )
    if row is None:
        raise HTTPException(404, "ไม่พบงานชุดนี้")

    counts = {
        item["status"]: item["n"] for item in db.query(
            "SELECT status, COUNT(*) AS n FROM jobs WHERE batch_id = ? GROUP BY status",
            (batch_id,),
        )
    }
    done = counts.get("done", 0)
    failed = counts.get("failed", 0) + counts.get("cancelled", 0)
    total = row["total"] or 1
    return {
        "id": row["id"], "title": row["title"], "total": row["total"],
        "created_at": row["created_at"], "counts": counts,
        "done": done, "failed": failed,
        "progress": round((done + failed) / total, 3),
        "finished": (done + failed) >= row["total"],
    }


@router.get("")
def list_batches(user: dict = Depends(auth.require_user), limit: int = 20) -> dict:
    rows = db.query(
        "SELECT id FROM batches WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user["id"], max(1, min(limit, 100))),
    )
    return {"batches": [batch_progress(row["id"], user["id"]) for row in rows]}


@router.get("/{batch_id}")
def get_batch(batch_id: str, user: dict = Depends(auth.require_user)) -> dict:
    progress = batch_progress(batch_id, user["id"])
    jobs = db.query(
        """SELECT id, title, status, progress, result, error, from_cache
           FROM jobs WHERE batch_id = ? ORDER BY created_at""",
        (batch_id,),
    )
    return {"batch": progress, "jobs": [dict(job) for job in jobs]}


@router.get("/{batch_id}/export")
def export_batch(batch_id: str, user: dict = Depends(auth.require_user)) -> dict:
    """รวมผลลัพธ์ทั้งชุดเป็นก้อนเดียว เอาไปใช้ต่อได้ทันที."""
    batch_progress(batch_id, user["id"])
    rows = db.query(
        "SELECT title, result, status FROM jobs WHERE batch_id = ? ORDER BY created_at",
        (batch_id,),
    )
    blocks = [
        f"## {row['title']}\n\n{row['result']}"
        for row in rows if row["status"] == "done" and row["result"].strip()
    ]
    return {"markdown": "\n\n---\n\n".join(blocks), "count": len(blocks)}

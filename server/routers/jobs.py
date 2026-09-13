"""คิวงาน: ส่งงานเข้าระบบ ติดตามสถานะ ดูผลลัพธ์ และสตรีมอัปเดตสดผ่าน SSE."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import auth, catalog, db, events
from .workers import ONLINE_WINDOW, worker_public

router = APIRouter(prefix="/api/v1", tags=["jobs"])

MAX_PROMPT = 32_000


class JobRequest(BaseModel):
    model: str
    prompt: str = Field(default="", max_length=MAX_PROMPT)
    title: str = Field(default="", max_length=120)
    system: str = Field(default="", max_length=8_000)
    max_tokens: int = Field(default=512, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    priority: int = Field(default=5, ge=1, le=9)
    drive_input: str = Field(default="", max_length=500)
    drive_output: str = Field(default="", max_length=500)
    extra: dict = Field(default_factory=dict)


def job_public(row, include_result: bool = True) -> dict:
    data = {
        "id": row["id"],
        "kind": row["kind"],
        "model": row["model"],
        "title": row["title"],
        "status": row["status"],
        "progress": row["progress"],
        "priority": row["priority"],
        "worker_id": row["worker_id"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "error": row["error"],
    }
    if row["finished_at"] and row["started_at"]:
        data["duration"] = round(row["finished_at"] - row["started_at"], 2)
    if include_result:
        data["result"] = row["result"]
        data["payload"] = db.loads(row["payload"], {})
    return data


@router.get("/models")
def list_models(user: dict = Depends(auth.require_user)) -> dict:
    """แนบข้อมูลว่าแต่ละโมเดล 'ลงเครื่องที่ออนไลน์อยู่ตอนนี้ได้ไหม' ไปด้วย."""
    rows = db.query(
        "SELECT * FROM workers WHERE user_id = ? AND last_seen_at > ?",
        (user["id"], time.time() - ONLINE_WINDOW),
    )
    best_vram = max((row["gpu_vram_mb"] for row in rows), default=0)
    models = []
    for model in catalog.MODELS:
        models.append({**model, "runnable_now": bool(rows) and best_vram >= model["vram_mb"]})
    return {"models": models, "kinds": catalog.KINDS, "best_vram_mb": best_vram}


@router.post("/jobs")
def submit_job(body: JobRequest, user: dict = Depends(auth.require_user)) -> dict:
    model = catalog.get(body.model)
    if model is None:
        raise HTTPException(400, f"ไม่รู้จักโมเดล '{body.model}'")
    if not body.prompt.strip() and not body.drive_input.strip():
        raise HTTPException(400, "ต้องมีคำสั่ง (prompt) หรือไฟล์จาก Drive อย่างน้อยหนึ่งอย่าง")

    now = time.time()
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    payload = {
        "prompt": body.prompt,
        "system": body.system,
        "max_tokens": body.max_tokens,
        "temperature": body.temperature,
        "repo": model["repo"],
        "quantize": model["quantize"],
        "drive_input": body.drive_input,
        "drive_output": body.drive_output,
        **body.extra,
    }
    title = body.title.strip() or (body.prompt.strip()[:60] or model["label"])
    db.execute(
        """INSERT INTO jobs
           (id, user_id, kind, model, title, payload, status, priority, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (job_id, user["id"], model["kind"], model["id"], title,
         json.dumps(payload, ensure_ascii=False), "queued", body.priority, now),
    )
    db.execute(
        "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
        (job_id, now, "info", "เข้าคิวแล้ว รอเครื่องว่าง"),
    )
    events.publish(
        user["id"],
        "job",
        {"action": "queued", "job_id": job_id, "model": model["id"], "title": title},
    )

    online = db.query_one(
        "SELECT COUNT(*) AS n FROM workers WHERE user_id = ? AND last_seen_at > ?",
        (user["id"], now - ONLINE_WINDOW),
    )["n"]
    return {
        "job_id": job_id,
        "status": "queued",
        "online_workers": online,
        "hint": "" if online else "ยังไม่มีเครื่องออนไลน์ — เปิดโน้ตบุ๊ก Colab แล้วเชื่อมเครื่องก่อน",
    }


@router.get("/jobs")
def list_jobs(
    user: dict = Depends(auth.require_user), status: str = "", limit: int = 50
) -> dict:
    limit = max(1, min(limit, 200))
    if status:
        rows = db.query(
            "SELECT * FROM jobs WHERE user_id=? AND status=? ORDER BY created_at DESC LIMIT ?",
            (user["id"], status, limit),
        )
    else:
        rows = db.query(
            "SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user["id"], limit),
        )
    counts = {
        row["status"]: row["n"]
        for row in db.query(
            "SELECT status, COUNT(*) AS n FROM jobs WHERE user_id=? GROUP BY status",
            (user["id"],),
        )
    }
    return {
        "jobs": [job_public(row, include_result=False) for row in rows],
        "counts": counts,
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: dict = Depends(auth.require_user)) -> dict:
    row = db.query_one(
        "SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])
    )
    if row is None:
        raise HTTPException(404, "ไม่พบงานนี้")
    log = db.query(
        "SELECT ts, level, message FROM job_events WHERE job_id=? ORDER BY id", (job_id,)
    )
    worker = None
    if row["worker_id"]:
        w = db.query_one("SELECT * FROM workers WHERE id=?", (row["worker_id"],))
        worker = worker_public(w) if w else None
    return {"job": job_public(row), "log": [dict(item) for item in log], "worker": worker}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, user: dict = Depends(auth.require_user)) -> dict:
    row = db.query_one(
        "SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])
    )
    if row is None:
        raise HTTPException(404, "ไม่พบงานนี้")
    if row["status"] in {"done", "failed", "cancelled"}:
        return {"ok": True, "status": row["status"]}
    db.execute(
        "UPDATE jobs SET status='cancelled', finished_at=?, error=? WHERE id=?",
        (time.time(), "ผู้ใช้ยกเลิกงาน", job_id),
    )
    events.publish(user["id"], "job", {"action": "cancelled", "job_id": job_id})
    return {"ok": True, "status": "cancelled"}


@router.get("/stream")
async def stream(request: Request, user: dict = Depends(auth.require_user)):
    """ช่องทางอัปเดตสด (Server-Sent Events) — หน้าเว็บเปิดค้างไว้เส้นเดียวพอ."""
    queue = events.subscribe(user["id"])

    async def generator():
        try:
            yield "retry: 3000\n\n"
            yield events.format_sse(
                {"event": "hello", "ts": time.time(), "data": {"user": user["email"]}}
            )
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=20)
                    yield events.format_sse(message)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"   # กัน proxy ตัดการเชื่อมต่อ
        finally:
            events.unsubscribe(user["id"], queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.get("/stats")
def stats(user: dict = Depends(auth.require_user)) -> dict:
    uid = user["id"]
    now = time.time()
    done = db.query_one(
        """SELECT COUNT(*) AS n, COALESCE(AVG(finished_at - started_at), 0) AS avg_s
           FROM jobs WHERE user_id=? AND status='done' AND started_at IS NOT NULL""",
        (uid,),
    )
    return {
        "jobs_total": db.query_one("SELECT COUNT(*) AS n FROM jobs WHERE user_id=?", (uid,))["n"],
        "jobs_done": done["n"],
        "avg_seconds": round(done["avg_s"], 2),
        "jobs_queued": db.query_one(
            "SELECT COUNT(*) AS n FROM jobs WHERE user_id=? AND status='queued'", (uid,)
        )["n"],
        "jobs_running": db.query_one(
            "SELECT COUNT(*) AS n FROM jobs WHERE user_id=? AND status='running'", (uid,)
        )["n"],
        "jobs_24h": db.query_one(
            "SELECT COUNT(*) AS n FROM jobs WHERE user_id=? AND created_at > ?",
            (uid, now - 86400),
        )["n"],
        "vault_docs": db.query_one(
            "SELECT COUNT(*) AS n FROM vault_docs WHERE user_id=?", (uid,)
        )["n"],
        "workers_online": db.query_one(
            "SELECT COUNT(*) AS n FROM workers WHERE user_id=? AND last_seen_at > ?",
            (uid, now - ONLINE_WINDOW),
        )["n"],
    }

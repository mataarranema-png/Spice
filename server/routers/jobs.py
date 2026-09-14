"""คิวงาน: ส่งงานเข้าระบบ ติดตามสถานะ ดูผลลัพธ์ และสตรีมอัปเดตสดผ่าน SSE."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import auth, brain, catalog, db, events, pipeline, scheduler, vault
from .workers import ONLINE_WINDOW, worker_public

router = APIRouter(prefix="/api/v1", tags=["jobs"])

MAX_PROMPT = 32_000


class PlanRequest(BaseModel):
    """คำสั่งภาษาคนหนึ่งก้อน ให้ระบบคิดแผนให้เอง."""

    prompt: str = Field(default="", max_length=MAX_PROMPT)
    drive_input: str = Field(default="", max_length=500)
    drive_output: str = Field(default="", max_length=500)
    priority: int = Field(default=5, ge=1, le=9)
    use_vault: bool | None = None      # None = ให้ระบบตัดสินเอง


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
        "attempt": row["attempt"],
        "parent_id": row["parent_id"],
        "eta_seconds": row["eta_seconds"],
        "chain_left": len(db.loads(row["chain"], [])),
    }
    if row["finished_at"] and row["started_at"]:
        data["duration"] = round(row["finished_at"] - row["started_at"], 2)
    if include_result:
        data["result"] = row["result"]
        data["payload"] = db.loads(row["payload"], {})
        data["plan"] = db.loads(row["plan"], {})
    return data


def _capacity_and_history(user_id: int) -> tuple[dict, dict]:
    return scheduler.capacity_for(user_id), scheduler.history_for(user_id)


def _vault_context(user_id: int, query: str, limit: int = 3) -> tuple[str, list[dict]]:
    """ดึงเอกสารที่เกี่ยวข้องจากคลังความรู้มาเป็นบริบท (RAG)."""
    hits = vault.search(user_id, query, top_k=limit)
    if not hits:
        return "", []
    blocks = [
        f"[{index}] {hit['title']}\n{hit['text'][:1500]}"
        for index, hit in enumerate(hits, 1)
    ]
    return "\n\n".join(blocks), hits


@router.get("/models")
def list_models(user: dict = Depends(auth.require_user)) -> dict:
    """แนบข้อมูลว่าแต่ละโมเดล 'ลงเครื่องที่ออนไลน์อยู่ตอนนี้ได้ไหม' ไปด้วย."""
    rows = db.query(
        "SELECT * FROM workers WHERE user_id = ? AND last_seen_at > ?",
        (user["id"], time.time() - ONLINE_WINDOW),
    )
    best_vram = max((row["gpu_vram_mb"] for row in rows), default=0)
    available = catalog.models_for(user["id"])
    models = [
        {**model, "runnable_now": bool(rows) and best_vram >= model["vram_mb"]}
        for model in available
    ]
    return {
        "models": models,
        "kinds": sorted({model["kind"] for model in available}),
        "best_vram_mb": best_vram,
        "custom_count": len([model for model in available if model.get("custom")]),
    }


@router.post("/plan")
def make_plan(body: PlanRequest, user: dict = Depends(auth.require_user)) -> dict:
    """คิดแผนให้ดูก่อน ยังไม่รัน — หน้าเว็บใช้แสดงว่า "ระบบจะทำอะไร เพราะอะไร"."""
    if not body.prompt.strip() and not body.drive_input.strip():
        raise HTTPException(400, "บอกมาก่อนว่าอยากได้อะไร")

    capacity, history = _capacity_and_history(user["id"])
    vault_count = db.query_one(
        "SELECT COUNT(*) AS n FROM vault_docs WHERE user_id = ?", (user["id"],)
    )["n"]

    plan = brain.build_plan(
        prompt=body.prompt,
        drive_input=body.drive_input,
        drive_output=body.drive_output,
        capacity=capacity,
        history=history,
        vault_available=vault_count,
        models=catalog.models_for(user["id"]),
    )
    data = plan.as_dict()

    # ผู้ใช้สั่งทับการตัดสินใจเรื่องคลังความรู้ได้
    if body.use_vault is not None:
        data["uses_vault"] = bool(body.use_vault) and bool(vault_count)

    if data["uses_vault"]:
        _, hits = _vault_context(user["id"], body.prompt)
        data["vault_hits"] = [
            {"title": hit["title"], "score": hit["score"]} for hit in hits
        ]
        data["uses_vault"] = bool(hits)

    # ขยายรายละเอียดโมเดลให้หน้าเว็บแสดงได้เลย
    for step in data["steps"]:
        model = catalog.get(step["model"]) or {}
        step["model_label"] = model.get("label", step["model"])
        step["vram_mb"] = model.get("vram_mb", 0)
        step["warm"] = step["model"] in capacity["warm"]

    data["capacity"] = capacity
    return data


@router.post("/jobs")
def submit_job(body: JobRequest, user: dict = Depends(auth.require_user)) -> dict:
    """ส่งงานเข้าคิว — เลือกโมเดลเองก็ได้ หรือใส่ model='auto' ให้ระบบเลือกให้."""
    if not body.prompt.strip() and not body.drive_input.strip():
        raise HTTPException(400, "ต้องมีคำสั่ง (prompt) หรือไฟล์จาก Drive อย่างน้อยหนึ่งอย่าง")

    capacity, history = _capacity_and_history(user["id"])
    auto = body.model.strip().lower() in {"auto", "", "อัตโนมัติ"}

    if auto:
        vault_count = db.query_one(
            "SELECT COUNT(*) AS n FROM vault_docs WHERE user_id = ?", (user["id"],)
        )["n"]
        plan = brain.build_plan(
            prompt=body.prompt, drive_input=body.drive_input,
            drive_output=body.drive_output, capacity=capacity, history=history,
            vault_available=vault_count, models=catalog.models_for(user["id"]),
        )
        steps = [step.as_dict() for step in plan.steps]
        plan_data = plan.as_dict()
        uses_vault = plan.uses_vault
        # คำสั่งขั้นสูงจากผู้ใช้ยังมีสิทธิ์ทับค่าที่ระบบคิดไว้
        if body.system:
            steps[0]["system"] = body.system
    else:
        model = catalog.get(body.model)
        if model is None:
            raise HTTPException(400, f"ไม่รู้จักโมเดล '{body.model}'")
        if not catalog.owns(body.model, user["id"]):
            raise HTTPException(403, "โมเดลนี้ไม่ได้อยู่ในคลังของคุณ")
        steps = [{
            "kind": model["kind"], "model": model["id"],
            "title": body.title.strip() or body.prompt.strip()[:60] or model["label"],
            "prompt": body.prompt, "system": body.system,
            "max_tokens": body.max_tokens, "temperature": body.temperature,
            "drive_input": body.drive_input, "drive_output": body.drive_output,
        }]
        plan_data = {"reason": "ผู้ใช้เลือกโมเดลเอง", "steps": steps, "manual": True}
        uses_vault = False
        plan_data["eta_seconds"] = round(
            brain.estimate_seconds(model["id"], history, set(capacity["warm"]),
                                   capacity["queue_ahead"]), 1)

    if body.title.strip():
        steps[0]["title"] = body.title.strip()

    context = ""
    if uses_vault:
        context, hits = _vault_context(user["id"], body.prompt)
        plan_data["vault_hits"] = [
            {"title": hit["title"], "score": hit["score"]} for hit in hits
        ]

    first, rest = steps[0], steps[1:]
    eta = plan_data.get("eta_seconds", 0)
    job_id = pipeline.create_job(
        user["id"], first, chain=rest, plan=plan_data, priority=body.priority,
        eta_seconds=eta, context=context,
        log_message=(
            f"เข้าคิวแล้ว · {plan_data.get('reason', '')[:180]}"
            if auto else "เข้าคิวแล้ว รอเครื่องว่าง"
        ),
    )

    events.publish(
        user["id"], "job",
        {"action": "queued", "job_id": job_id, "model": first["model"],
         "title": first.get("title", ""), "steps": len(steps)},
    )

    # ไม่มีเครื่องเลย = บอกวิธีแก้ที่ทำได้จริงก่อน ค่อยว่ากันเรื่องเครื่องไม่พอทีหลัง
    if not capacity["online"]:
        hint = "ยังไม่มีเครื่องออนไลน์ — เปิดโน้ตบุ๊ก Colab แล้วเชื่อมเครื่องก่อน"
    else:
        hint = scheduler.blocked_reason(user["id"], first["model"], first["kind"])
    return {
        "job_id": job_id,
        "status": "queued",
        "model": first["model"],
        "steps": len(steps),
        "auto": auto,
        "reason": plan_data.get("reason", ""),
        "eta_seconds": eta,
        "uses_vault": bool(context),
        "online_workers": capacity["online"],
        "hint": hint,
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
    capacity = scheduler.capacity_for(uid)
    return {
        "capacity": capacity,
        "warm_labels": [
            (catalog.get(model) or {}).get("label", model) for model in capacity["warm"]
        ],
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

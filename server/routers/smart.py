"""ฟังก์ชันอัจฉริยะเพิ่มเติม: โหวตหาคำตอบที่น่าเชื่อถือ, งานตั้งเวลา, และสถิติเชิงลึก."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, brain, catalog, consensus, db, events, pipeline, scheduler

router = APIRouter(prefix="/api/v1", tags=["smart"])

MAX_VOTES = 5
MIN_INTERVAL_MINUTES = 15


# ═══ โหวตหาคำตอบที่น่าเชื่อถือที่สุด ═════════════════════════
class VoteRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16_000)
    model: str = "auto"
    votes: int = Field(default=3, ge=2, le=MAX_VOTES)
    max_tokens: int = Field(default=768, ge=64, le=4096)


@router.post("/votes")
def create_vote(body: VoteRequest, user: dict = Depends(auth.require_user)) -> dict:
    """ถามคำถามเดียวกันหลายรอบ แล้วดูว่าคำตอบไหนสอดคล้องกับพวกมากที่สุด.

    ใช้กับคำถามที่ต้องการความถูกต้อง — โมเดลภาษาตอบต่างกันได้ทุกครั้ง
    การถามรอบเดียวจึงเท่ากับเชื่อการสุ่มครั้งเดียว.
    """
    capacity = scheduler.capacity_for(user["id"])
    models = catalog.models_for(user["id"])

    if body.model in {"", "auto"}:
        intent = brain.analyze(body.prompt)
        model_id, reason, _ = brain.pick_model(intent, capacity, models)
    else:
        if catalog.get(body.model) is None or not catalog.owns(body.model, user["id"]):
            raise HTTPException(400, f"ใช้โมเดล '{body.model}' ไม่ได้")
        model_id, reason = body.model, "ผู้ใช้เลือกโมเดลเอง"

    group = f"vg_{uuid.uuid4().hex[:12]}"
    job_ids = []
    for index in range(body.votes):
        step = {
            "kind": "text", "model": model_id,
            "title": f"[โหวต {index + 1}/{body.votes}] {body.prompt[:44]}",
            "prompt": body.prompt,
            "max_tokens": body.max_tokens,
            # ต้องให้แต่ละรอบต่างกันบ้าง ไม่งั้นได้คำตอบเดิมเป๊ะทุกรอบแล้วโหวตไม่มีความหมาย
            "temperature": round(0.45 + index * 0.12, 2),
        }
        job_ids.append(pipeline.create_job(
            user["id"], step, priority=5,
            plan={"reason": reason, "steps": [step], "vote": True},
            use_cache=False,          # แคชจะทำให้ทุกรอบได้คำตอบเดียวกัน
            log_message=f"รอบที่ {index + 1} จาก {body.votes} ของการโหวต",
        ))
    db.execute(
        f"UPDATE jobs SET vote_group = ? WHERE id IN ({','.join('?' * len(job_ids))})",
        (group, *job_ids),
    )
    return {"vote_group": group, "votes": body.votes, "model": model_id,
            "reason": reason, "job_ids": job_ids}


@router.get("/votes/{group}")
def get_vote(group: str, user: dict = Depends(auth.require_user)) -> dict:
    rows = db.query(
        """SELECT id, status, result, payload FROM jobs
           WHERE vote_group = ? AND user_id = ? ORDER BY created_at""",
        (group, user["id"]),
    )
    if not rows:
        raise HTTPException(404, "ไม่พบการโหวตนี้")

    finished = [row for row in rows if row["status"] == "done"]
    answers = [row["result"] for row in finished]
    verdict = consensus.pick_consensus(answers) if answers else {}

    return {
        "group": group,
        "total": len(rows),
        "finished": len(finished),
        "pending": len([row for row in rows if row["status"] in ("queued", "running")]),
        "verdict": verdict,
        "summary": consensus.describe(verdict) if verdict else "ยังไม่มีคำตอบ",
        "answers": [
            {"job_id": row["id"], "status": row["status"], "result": row["result"],
             "temperature": db.loads(row["payload"], {}).get("temperature")}
            for row in rows
        ],
    }


# ═══ งานตั้งเวลา ═════════════════════════════════════════════
class ScheduleRequest(BaseModel):
    title: str = Field(default="", max_length=120)
    prompt: str = Field(min_length=1, max_length=16_000)
    model: str = "auto"
    every_minutes: int = Field(default=1440, ge=MIN_INTERVAL_MINUTES, le=60 * 24 * 30)
    at_hour: int = Field(default=8, ge=0, le=23)
    at_minute: int = Field(default=0, ge=0, le=59)
    drive_input: str = Field(default="", max_length=500)
    drive_output: str = Field(default="", max_length=500)


def compute_next_run(every_minutes: int, at_hour: int, at_minute: int,
                     after: float | None = None) -> float:
    """เวลาที่ควรทำรอบถัดไป — รอบวันยึดเวลาที่ตั้งไว้ รอบสั้นนับจากตอนนี้."""
    now = after or time.time()
    if every_minutes < 1440:
        return now + every_minutes * 60

    local = time.localtime(now)
    target = time.struct_time((
        local.tm_year, local.tm_mon, local.tm_mday, at_hour, at_minute, 0,
        local.tm_wday, local.tm_yday, -1,
    ))
    stamp = time.mktime(target)
    days = max(1, round(every_minutes / 1440))
    while stamp <= now:
        stamp += days * 86400
    return stamp


@router.post("/schedules")
def create_schedule(body: ScheduleRequest, user: dict = Depends(auth.require_user)) -> dict:
    if body.model not in {"", "auto"} and (
        catalog.get(body.model) is None or not catalog.owns(body.model, user["id"])
    ):
        raise HTTPException(400, f"ใช้โมเดล '{body.model}' ไม่ได้")

    now = time.time()
    schedule_id = f"sc_{uuid.uuid4().hex[:12]}"
    next_run = compute_next_run(body.every_minutes, body.at_hour, body.at_minute)
    db.execute(
        """INSERT INTO schedules
           (id, user_id, title, prompt, model, drive_input, drive_output,
            every_minutes, at_hour, at_minute, enabled, next_run_at, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)""",
        (schedule_id, user["id"], body.title.strip() or body.prompt[:60],
         body.prompt, body.model, body.drive_input, body.drive_output,
         body.every_minutes, body.at_hour, body.at_minute, next_run, now),
    )
    return {"id": schedule_id, "next_run_at": next_run,
            "next_run_in_minutes": round((next_run - now) / 60)}


@router.get("/schedules")
def list_schedules(user: dict = Depends(auth.require_user)) -> dict:
    rows = db.query(
        "SELECT * FROM schedules WHERE user_id = ? ORDER BY next_run_at", (user["id"],)
    )
    return {"schedules": [
        {**dict(row), "enabled": bool(row["enabled"]),
         "next_run_in_minutes": round((row["next_run_at"] - time.time()) / 60)}
        for row in rows
    ]}


@router.post("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: str, user: dict = Depends(auth.require_user)) -> dict:
    row = db.query_one(
        "SELECT * FROM schedules WHERE id = ? AND user_id = ?", (schedule_id, user["id"])
    )
    if row is None:
        raise HTTPException(404, "ไม่พบงานตั้งเวลานี้")
    enabled = 0 if row["enabled"] else 1
    next_run = compute_next_run(row["every_minutes"], row["at_hour"], row["at_minute"])
    db.execute(
        "UPDATE schedules SET enabled = ?, next_run_at = ? WHERE id = ?",
        (enabled, next_run, schedule_id),
    )
    return {"ok": True, "enabled": bool(enabled)}


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: str, user: dict = Depends(auth.require_user)) -> dict:
    row = db.query_one(
        "SELECT id FROM schedules WHERE id = ? AND user_id = ?", (schedule_id, user["id"])
    )
    if row is None:
        raise HTTPException(404, "ไม่พบงานตั้งเวลานี้")
    db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    return {"ok": True}


@router.post("/schedules/{schedule_id}/run")
def run_schedule_now(schedule_id: str, user: dict = Depends(auth.require_user)) -> dict:
    row = db.query_one(
        "SELECT * FROM schedules WHERE id = ? AND user_id = ?", (schedule_id, user["id"])
    )
    if row is None:
        raise HTTPException(404, "ไม่พบงานตั้งเวลานี้")
    return {"job_id": fire_schedule(dict(row)), "ok": True}


def fire_schedule(schedule: dict) -> str:
    """สร้างงานจริงจากงานตั้งเวลาหนึ่งรายการ."""
    user_id = schedule["user_id"]
    capacity = scheduler.capacity_for(user_id)
    models = catalog.models_for(user_id)

    if schedule["model"] in {"", "auto"}:
        intent = brain.analyze(schedule["prompt"], schedule["drive_input"])
        model_id, reason, _ = brain.pick_model(intent, capacity, models)
        max_tokens, temperature = intent.max_tokens, intent.temperature
        kind = intent.kind
    else:
        model = catalog.get(schedule["model"])
        model_id, reason = schedule["model"], "ผู้ใช้เลือกโมเดลไว้กับงานตั้งเวลานี้"
        max_tokens, temperature, kind = 1024, 0.5, model["kind"]

    step = {
        "kind": kind, "model": model_id,
        "title": f"⏰ {schedule['title']}",
        "prompt": schedule["prompt"],
        "drive_input": schedule["drive_input"],
        "drive_output": schedule["drive_output"],
        "max_tokens": max_tokens, "temperature": temperature,
    }
    job_id = pipeline.create_job(
        user_id, step, priority=6,
        plan={"reason": reason, "steps": [step], "scheduled": True},
        log_message=f"เกิดจากงานตั้งเวลา “{schedule['title']}”",
    )
    now = time.time()
    db.execute(
        """UPDATE schedules
           SET last_run_at = ?, runs = runs + 1, next_run_at = ?
           WHERE id = ?""",
        (now, compute_next_run(schedule["every_minutes"], schedule["at_hour"],
                               schedule["at_minute"], now), schedule["id"]),
    )
    db.execute("UPDATE jobs SET schedule_id = ? WHERE id = ?", (schedule["id"], job_id))
    events.publish(user_id, "schedule",
                   {"action": "fired", "schedule_id": schedule["id"], "job_id": job_id})
    return job_id


def run_due_schedules() -> int:
    """ยิงงานตั้งเวลาที่ถึงกำหนดแล้วทั้งหมด — เรียกจากลูปเบื้องหลัง."""
    rows = db.query(
        "SELECT * FROM schedules WHERE enabled = 1 AND next_run_at <= ?", (time.time(),)
    )
    for row in rows:
        try:
            fire_schedule(dict(row))
        except Exception as exc:      # งานตั้งเวลาอันหนึ่งพัง ต้องไม่ลากอันอื่นล้มตาม
            db.log_audit(row["user_id"], "schedule.error", f"{row['id']}: {exc}")
            db.execute(
                "UPDATE schedules SET next_run_at = ? WHERE id = ?",
                (time.time() + row["every_minutes"] * 60, row["id"]),
            )
    return len(rows)


# ═══ สถิติเชิงลึก ════════════════════════════════════════════
@router.get("/insights")
def insights(user: dict = Depends(auth.require_user), days: int = 7) -> dict:
    """ดูว่าเวลาการ์ดจอหมดไปกับอะไร และระบบช่วยประหยัดไปเท่าไหร่."""
    from .. import cache

    uid = user["id"]
    days = max(1, min(days, 90))
    since = time.time() - days * 86400

    by_model = db.query(
        """SELECT model, COUNT(*) AS runs,
                  COALESCE(SUM(finished_at - started_at), 0) AS seconds,
                  COALESCE(AVG(finished_at - started_at), 0) AS avg_seconds
           FROM jobs
           WHERE user_id = ? AND status = 'done' AND from_cache = 0
             AND started_at IS NOT NULL AND finished_at IS NOT NULL AND created_at > ?
           GROUP BY model ORDER BY seconds DESC""",
        (uid, since),
    )
    totals = db.query_one(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                  SUM(CASE WHEN from_cache = 1 THEN 1 ELSE 0 END) AS cached
           FROM jobs WHERE user_id = ? AND created_at > ?""",
        (uid, since),
    )
    slowest = db.query(
        """SELECT id, title, model, (finished_at - started_at) AS seconds
           FROM jobs
           WHERE user_id = ? AND status = 'done' AND started_at IS NOT NULL
             AND finished_at IS NOT NULL AND created_at > ?
           ORDER BY seconds DESC LIMIT 5""",
        (uid, since),
    )
    workers = db.query("SELECT * FROM workers WHERE user_id = ?", (uid,))
    repaired = db.query_one(
        "SELECT COUNT(*) AS n FROM jobs WHERE user_id = ? AND repairs != '[]' AND created_at > ?",
        (uid, since),
    )["n"]

    gpu_seconds = sum(row["seconds"] for row in by_model)
    total_jobs = totals["total"] or 0
    return {
        "days": days,
        "gpu_seconds": round(gpu_seconds, 1),
        "jobs": total_jobs,
        "failed": totals["failed"] or 0,
        "failure_rate": round((totals["failed"] or 0) / total_jobs, 3) if total_jobs else 0,
        "cached_jobs": totals["cached"] or 0,
        "repaired_jobs": repaired,
        "cache": cache.stats_for(uid),
        "by_model": [
            {"model": row["model"],
             "label": (catalog.get(row["model"]) or {}).get("label", row["model"]),
             "runs": row["runs"], "seconds": round(row["seconds"], 1),
             "avg_seconds": round(row["avg_seconds"], 1),
             "share": round(row["seconds"] / gpu_seconds, 3) if gpu_seconds else 0}
            for row in by_model
        ],
        "slowest": [
            {"id": row["id"], "title": row["title"], "model": row["model"],
             "seconds": round(row["seconds"], 1)} for row in slowest
        ],
        "workers": [
            {"id": row["id"], "name": row["name"], "jobs_done": row["jobs_done"],
             **scheduler.health_of(dict(row))} for row in workers
        ],
    }

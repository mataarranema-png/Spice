"""ยืมพลัง GPU: จับคู่เครื่อง (Colab T4 ฯลฯ), รับ telemetry, จ่ายงานให้ worker."""

from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .. import (auth, brain, cache, catalog, continuation, db, diagnosis, events,
                lifespan, pipeline, scheduler)
from ..security import hash_token, new_pair_code, new_worker_token

router = APIRouter(prefix="/api/v1", tags=["workers"])

PAIR_CODE_TTL = 15 * 60      # รหัสจับคู่มีอายุ 15 นาที
ONLINE_WINDOW = 75           # ไม่ส่งสัญญาณเกินเท่านี้ = ออฟไลน์
LEASE_TIMEOUT = 15 * 60      # ไม่มีสัญญาณจาก worker นานเกินนี้ถือว่าเครื่องหลุด


# ── โมเดลข้อมูลเข้า ───────────────────────────────────────────
class PairRequest(BaseModel):
    label: str = Field(default="Colab T4", max_length=60)


class RegisterRequest(BaseModel):
    pair_code: str
    name: str = Field(default="colab-worker", max_length=60)
    gpu_name: str = ""
    gpu_vram_mb: int = 0
    driver: str = ""
    runtime: str = ""
    capabilities: list[str] = Field(default_factory=list)


class HeartbeatRequest(BaseModel):
    gpu_used_mb: int = 0
    gpu_util: int = 0
    gpu_name: str = ""
    gpu_vram_mb: int = 0
    drive_mounted: bool = False
    status: str = "idle"
    warm_models: list[str] = Field(default_factory=list)   # โมเดลที่ค้างอยู่ใน VRAM


class ProgressRequest(BaseModel):
    progress: float = 0
    message: str = ""
    level: str = "info"


class StreamRequest(BaseModel):
    delta: str = Field(default="", max_length=20_000)
    progress: float = 0


class CompleteRequest(BaseModel):
    result: str = ""
    error: str = ""
    meta: dict = Field(default_factory=dict)


# ── ตัวช่วย ───────────────────────────────────────────────────
def worker_status(row) -> str:
    if time.time() - row["last_seen_at"] > ONLINE_WINDOW:
        return "offline"
    if scheduler.is_quarantined(dict(row)):
        return "paused"
    return row["status"] if row["status"] in {"busy", "idle"} else "idle"


def worker_public(row) -> dict:
    status = worker_status(row)
    vram = row["gpu_vram_mb"] or 0
    warm = db.loads(row["warm_models"], [])
    return {
        "warm_models": warm,
        "warm_labels": [
            (catalog.get(model) or {}).get("label", model) for model in warm
        ],
        "id": row["id"],
        "name": row["name"],
        "status": status,
        "gpu_name": row["gpu_name"] or "ไม่ทราบรุ่น",
        "gpu_vram_mb": vram,
        "gpu_used_mb": row["gpu_used_mb"],
        "gpu_util": row["gpu_util"],
        "vram_pct": round(row["gpu_used_mb"] * 100 / vram, 1) if vram else 0,
        "driver": row["driver"],
        "runtime": row["runtime"],
        "capabilities": db.loads(row["capabilities"], []),
        "drive_mounted": bool(row["drive_mounted"]),
        "jobs_done": row["jobs_done"],
        **scheduler.health_of(dict(row)),
        "life": lifespan.remaining(row["user_id"], dict(row)),
        "life_note": lifespan.describe(lifespan.remaining(row["user_id"], dict(row))),
        "last_seen_at": row["last_seen_at"],
        "seconds_since_seen": round(time.time() - row["last_seen_at"], 1),
        "created_at": row["created_at"],
    }


def authed_worker(authorization: str = Header(default="")) -> dict:
    """ยืนยันตัว worker ด้วย Bearer token (เก็บฝั่งเซิร์ฟเวอร์เป็นแฮชเท่านั้น)."""
    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith("spk_"):
        raise HTTPException(401, "ต้องมี worker token")
    row = db.query_one("SELECT * FROM workers WHERE token_hash = ?", (hash_token(token),))
    if row is None:
        raise HTTPException(401, "worker token ไม่ถูกต้องหรือถูกเพิกถอนแล้ว")
    return dict(row)


def reap_stale_jobs() -> None:
    """งานที่ worker รับไปแล้วเงียบหาย → คืนกลับคิว *พร้อมข้อความที่เขียนไปแล้ว*.

    นับจาก progress_at (สัญญาณล่าสุด) ไม่ใช่ started_at — งานที่ใช้เวลานาน
    เช่นดาวน์โหลดน้ำหนักโมเดลครั้งแรก จึงไม่ถูกโยนกลับเข้าคิวทั้งที่ยังทำอยู่.

    ถ้ามีข้อความที่สตรีมกลับมาแล้วมากพอ จะไม่ทิ้งของเดิม แต่สั่งให้เครื่องถัดไป
    *เขียนต่อ* จากตรงนั้น — Colab หลุดตอนงานไปแล้ว 80% จึงไม่ต้องเริ่มใหม่หมด.
    """
    cutoff = time.time() - LEASE_TIMEOUT
    stale = db.query(
        """SELECT * FROM jobs
           WHERE status='running'
             AND COALESCE(progress_at, started_at) IS NOT NULL
             AND COALESCE(progress_at, started_at) < ?""",
        (cutoff,),
    )
    for row in stale:
        pipeline.requeue_for_continuation(row, "เครื่องที่รับงานไปเงียบหาย")


# ── ฝั่งผู้ใช้ (ล็อกอินด้วย Google) ────────────────────────────
@router.post("/workers/pair")
def create_pair_code(body: PairRequest, user: dict = Depends(auth.require_user)) -> dict:
    now = time.time()
    db.execute("DELETE FROM pair_codes WHERE expires_at < ?", (now,))
    code = new_pair_code()
    db.execute(
        "INSERT INTO pair_codes (code, user_id, label, created_at, expires_at) VALUES (?,?,?,?,?)",
        (code, user["id"], body.label, now, now + PAIR_CODE_TTL),
    )
    db.log_audit(user["id"], "pair_code.create", body.label)
    return {"pair_code": code, "expires_in": PAIR_CODE_TTL, "label": body.label}


@router.get("/workers")
def list_workers(user: dict = Depends(auth.require_user)) -> dict:
    rows = db.query(
        "SELECT * FROM workers WHERE user_id = ? ORDER BY last_seen_at DESC", (user["id"],)
    )
    workers = [worker_public(row) for row in rows]
    online = [w for w in workers if w["status"] != "offline"]
    return {
        "workers": workers,
        "summary": {
            "total": len(workers),
            "online": len(online),
            "busy": len([w for w in online if w["status"] == "busy"]),
            "vram_total_mb": sum(w["gpu_vram_mb"] for w in online),
            "jobs_done": sum(w["jobs_done"] for w in workers),
        },
    }


@router.delete("/workers/{worker_id}")
def revoke_worker(worker_id: str, user: dict = Depends(auth.require_user)) -> dict:
    row = db.query_one(
        "SELECT id FROM workers WHERE id = ? AND user_id = ?", (worker_id, user["id"])
    )
    if row is None:
        raise HTTPException(404, "ไม่พบเครื่องนี้")
    db.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
    db.log_audit(user["id"], "worker.revoke", worker_id)
    events.publish(user["id"], "worker", {"action": "revoked", "worker_id": worker_id})
    return {"ok": True}


# ── ฝั่ง worker (Colab / เครื่องที่บ้าน) ───────────────────────
@router.post("/worker/register")
def register_worker(body: RegisterRequest) -> dict:
    now = time.time()
    code = body.pair_code.strip().upper()
    row = db.query_one("SELECT * FROM pair_codes WHERE code = ?", (code,))
    if row is None or row["used_at"] is not None or row["expires_at"] < now:
        raise HTTPException(400, "รหัสจับคู่ไม่ถูกต้อง หมดอายุ หรือถูกใช้ไปแล้ว")

    token = new_worker_token()
    worker_id = f"wk_{uuid.uuid4().hex[:12]}"
    db.execute(
        """INSERT INTO workers
           (id, user_id, name, token_hash, status, gpu_name, gpu_vram_mb, driver,
            runtime, capabilities, created_at, last_seen_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            worker_id,
            row["user_id"],
            body.name or row["label"] or "worker",
            hash_token(token),
            "idle",
            body.gpu_name,
            body.gpu_vram_mb,
            body.driver,
            body.runtime,
            json.dumps(body.capabilities),
            now,
            now,
        ),
    )
    db.execute("UPDATE pair_codes SET used_at = ? WHERE code = ?", (now, code))
    db.log_audit(row["user_id"], "worker.register", f"{worker_id} {body.gpu_name}")
    events.publish(
        row["user_id"],
        "worker",
        {"action": "joined", "worker_id": worker_id, "gpu_name": body.gpu_name},
    )
    return {
        "worker_id": worker_id,
        "worker_token": token,
        "owner_email": db.query_one(
            "SELECT email FROM users WHERE id = ?", (row["user_id"],)
        )["email"],
        "heartbeat_interval": 20,
    }


@router.post("/worker/heartbeat")
def heartbeat(body: HeartbeatRequest, worker: dict = Depends(authed_worker)) -> dict:
    now = time.time()
    db.execute(
        """UPDATE workers SET last_seen_at=?, status=?, gpu_used_mb=?, gpu_util=?,
                  drive_mounted=?, warm_models=?,
                  gpu_name=COALESCE(NULLIF(?, ''), gpu_name),
                  gpu_vram_mb=CASE WHEN ? > 0 THEN ? ELSE gpu_vram_mb END
           WHERE id=?""",
        (
            now,
            body.status if body.status in {"idle", "busy"} else "idle",
            body.gpu_used_mb,
            body.gpu_util,
            int(body.drive_mounted),
            json.dumps(body.warm_models[:12]),
            body.gpu_name,
            body.gpu_vram_mb,
            body.gpu_vram_mb,
            worker["id"],
        ),
    )
    fresh = db.query_one("SELECT * FROM workers WHERE id = ?", (worker["id"],))
    events.publish(worker["user_id"], "worker", {"action": "beat", **worker_public(fresh)})
    pending = db.query_one(
        "SELECT COUNT(*) AS n FROM jobs WHERE user_id = ? AND status = 'queued'",
        (worker["user_id"],),
    )["n"]
    response = {"ok": True, "queued_jobs": pending, "server_time": now}

    # ว่างอยู่และไม่มีงานค้าง — ใช้เวลาว่างโหลดโมเดลที่น่าจะได้ใช้ต่อไปรอไว้
    if body.status == "idle" and not pending:
        preload = scheduler.suggest_preload(dict(fresh))
        if preload:
            response["preload"] = preload
    return response


@router.post("/worker/lease")
def lease_job(worker: dict = Depends(authed_worker)) -> dict:
    """รับงานที่ *เหมาะกับเครื่องนี้ที่สุด* ไม่ใช่แค่งานที่มาก่อน.

    ตัวจัดสรรจะข้ามงานที่ VRAM ของเครื่องนี้ไม่พอ และให้น้ำหนักกับงานที่ใช้
    โมเดลซึ่งโหลดค้างอยู่ในเครื่องแล้ว เพราะเริ่มรันได้ทันทีโดยไม่ต้องโหลดใหม่.
    """
    reap_stale_jobs()
    row, reason = scheduler.claim_next_job(worker)
    if row is None:
        return {"job": None}

    now = time.time()
    db.execute(
        "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
        (row["id"], now, "info", f"เครื่อง {worker['name']} รับงานแล้ว — {reason}"),
    )
    events.publish(
        worker["user_id"],
        "job",
        {"action": "started", "job_id": row["id"], "worker": worker["name"], "reason": reason},
    )
    return {
        "job": {
            "id": row["id"],
            "kind": row["kind"],
            "model": row["model"],
            "title": row["title"],
            "payload": db.loads(row["payload"], {}),
        }
    }


@router.post("/worker/jobs/{job_id}/progress")
def report_progress(
    job_id: str, body: ProgressRequest, worker: dict = Depends(authed_worker)
) -> dict:
    row = db.query_one(
        "SELECT * FROM jobs WHERE id = ? AND worker_id = ?", (job_id, worker["id"])
    )
    if row is None:
        raise HTTPException(404, "ไม่พบงานนี้ หรือไม่ได้ถูกมอบหมายให้เครื่องนี้")
    progress = max(0.0, min(1.0, float(body.progress)))
    db.execute(
        "UPDATE jobs SET progress = ?, progress_at = ? WHERE id = ?",
        (progress, time.time(), job_id),
    )
    if body.message:
        db.execute(
            "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
            (job_id, time.time(), body.level, body.message[:2000]),
        )
    events.publish(
        worker["user_id"],
        "job",
        {
            "action": "progress",
            "job_id": job_id,
            "progress": progress,
            "message": body.message,
            "level": body.level,
        },
    )
    return {"ok": True}


@router.post("/worker/jobs/{job_id}/stream")
def stream_tokens(
    job_id: str, body: StreamRequest, worker: dict = Depends(authed_worker)
) -> dict:
    """รับคำตอบทีละท่อนระหว่างที่โมเดลกำลังพิมพ์ แล้วส่งต่อขึ้นหน้าเว็บทันที.

    เก็บลงคอลัมน์ result ไปเรื่อย ๆ ด้วย เผื่อผู้ใช้รีเฟรชหน้ากลางคัน
    จะได้เห็นส่วนที่พิมพ์มาแล้ว ไม่ใช่หน้าว่าง.
    """
    row = db.query_one(
        "SELECT id, progress, status FROM jobs WHERE id = ? AND worker_id = ?",
        (job_id, worker["id"]),
    )
    if row is None:
        raise HTTPException(404, "ไม่พบงานนี้ หรือไม่ได้ถูกมอบหมายให้เครื่องนี้")
    if row["status"] != "running":
        # ข้อความที่มาถึงช้ากว่าที่งานจบหรือถูกยกเลิก ต้องไม่ไปต่อท้ายผลลัพธ์
        return {"ok": True, "ignored": True, "status": row["status"]}
    if not body.delta:
        return {"ok": True}

    progress = max(row["progress"], min(0.99, float(body.progress or 0)))
    db.execute(
        "UPDATE jobs SET result = result || ?, progress = ?, progress_at = ? WHERE id = ?",
        (body.delta, progress, time.time(), job_id),
    )
    events.publish(
        worker["user_id"], "job",
        {"action": "token", "job_id": job_id, "delta": body.delta, "progress": progress},
    )
    return {"ok": True}


@router.post("/worker/jobs/{job_id}/complete")
def complete_job(
    job_id: str, body: CompleteRequest, worker: dict = Depends(authed_worker)
) -> dict:
    row = db.query_one(
        "SELECT * FROM jobs WHERE id = ? AND worker_id = ?", (job_id, worker["id"])
    )
    if row is None:
        raise HTTPException(404, "ไม่พบงานนี้ หรือไม่ได้ถูกมอบหมายให้เครื่องนี้")

    # งานที่ไม่ได้กำลังรันอยู่ ห้ามถูกเขียนทับ — กันสองกรณีที่เกิดจริง:
    # เครื่องยิงผลซ้ำเพราะเน็ตกระตุก และผลที่มาถึงหลังผู้ใช้กดยกเลิกไปแล้ว
    if row["status"] != "running":
        return {"ok": True, "status": row["status"], "ignored": True}

    now = time.time()
    db.execute("UPDATE workers SET status='idle' WHERE id=?", (worker["id"],))
    health = scheduler.record_outcome(worker["id"], succeeded=not body.error)
    if health.get("quarantined"):
        db.log_audit(worker["user_id"], "worker.quarantine", worker["id"])
        events.publish(
            worker["user_id"], "worker",
            {"action": "quarantined", "worker_id": worker["id"],
             "name": worker["name"], "reason": health["reason"]},
        )

    # ── ล้มเหลว: วินิจฉัยก่อน แล้วค่อยลองแก้ตามที่เคยได้ผล ──────
    if body.error:
        diag = diagnosis.observe(worker["user_id"], body.error)
        db.execute(
            "UPDATE jobs SET last_error = ? WHERE id = ?", (body.error[:2000], job_id))
        db.execute(
            "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
            (job_id, now, "warn", "🔎 " + diagnosis.describe(diag)),
        )

        remedy = diag["remedy"]
        if remedy == "smaller_model":
            fallback = pipeline.maybe_recover(row, body.error)
            if fallback:
                return {"ok": True, "status": "requeued", "fallback_model": fallback,
                        "diagnosis": diag["kind"]}
            # เล็กกว่านี้ไม่มีแล้ว — ยังเหลือทางเดียวคือหาเครื่องที่ VRAM มากกว่า
            bigger = db.query_one(
                """SELECT id FROM workers
                   WHERE user_id = ? AND id != ? AND gpu_vram_mb > ? AND last_seen_at > ?""",
                (worker["user_id"], worker["id"], worker["gpu_vram_mb"] or 0,
                 now - ONLINE_WINDOW),
            )
            if bigger:
                remedy = "retry_elsewhere"
                db.execute(
                    "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
                    (job_id, now, "warn",
                     "ไม่มีโมเดลที่เล็กกว่านี้แล้ว — ลองส่งไปเครื่องที่ VRAM มากกว่าแทน"),
                )

        # ปัญหาที่เป็นของ "เครื่องนั้น" ไม่ใช่ของงาน → ให้เครื่องอื่นลองแทน
        if remedy == "retry_elsewhere" and row["attempt"] < pipeline.MAX_ATTEMPTS:
            db.execute(
                """UPDATE jobs SET status='queued', worker_id=NULL, started_at=NULL,
                       progress_at=NULL, progress=0, error='', attempt = attempt + 1
                   WHERE id=?""",
                (row["id"],),
            )
            db.execute(
                "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
                (job_id, now, "warn",
                 f"ปัญหานี้เป็นของเครื่อง {worker['name']} ไม่ใช่ของงาน — ส่งให้เครื่องอื่นลองแทน"),
            )
            events.publish(
                worker["user_id"], "job",
                {"action": "rerouted", "job_id": job_id, "kind": diag["kind"]},
            )
            return {"ok": True, "status": "rerouted", "diagnosis": diag["kind"]}

        if row["last_error"]:
            # ลองแก้ไปแล้วแต่ยังพังอยู่ — วิธีนั้นใช้ไม่ได้กับปัญหานี้
            diagnosis.record_outcome(worker["user_id"], row["last_error"], worked=False)
        db.execute(
            "UPDATE jobs SET status='failed', error=?, finished_at=? WHERE id=?",
            (body.error, now, job_id),
        )
        db.execute(
            "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
            (job_id, now, "error", body.error[:2000]),
        )
        # ลูกโซ่ที่ค้างอยู่ต้องหยุด ไม่ใช่เดินต่อด้วยข้อมูลที่ไม่มี
        if db.loads(row["chain"], []):
            db.execute(
                "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
                (job_id, now, "warn", "หยุดลูกโซ่ที่เหลือไว้ เพราะขั้นนี้ไม่สำเร็จ"),
            )
        events.publish(
            worker["user_id"],
            "job",
            {"action": "finished", "job_id": job_id, "status": "failed",
             "duration": round(now - (row["started_at"] or now), 2), "meta": body.meta},
        )
        return {"ok": True, "status": "failed"}

    # เครื่องที่สตรีมมาแล้วส่ง result ว่างมาตอนจบได้ ให้ใช้ของที่สะสมไว้แทน
    # แล้วต่อเข้ากับข้อความจากรอบก่อน (ถ้างานนี้เป็นการเขียนต่อ)
    attempt_text = body.result or row["result"]
    final_result = continuation.stitch(row["result_prefix"], attempt_text)

    # ── ด่านตรวจคุณภาพ: "เสร็จ" ไม่ได้แปลว่า "ใช้ได้" ───────────
    verdict = pipeline.maybe_repair(row, final_result, body.meta)
    if verdict is not None:
        return {"ok": True, "status": "repairing", "problem": verdict.problem}

    # ── สำเร็จจริง ────────────────────────────────────────────
    db.execute(
        """UPDATE jobs SET status='done', result=?, error='', progress=1.0, finished_at=?
           WHERE id=?""",
        (final_result, now, job_id),
    )
    db.execute(
        "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
        (job_id, now, "success", "ทำงานเสร็จสมบูรณ์"),
    )

    payload = db.loads(row["payload"], {})
    duration = now - (row["started_at"] or now)
    if cache.is_cacheable(payload, row["kind"]):
        cache.store(worker["user_id"], cache.fingerprint(row["model"], payload),
                    row["model"], payload, final_result, duration)

    # งานนี้เคยพังแล้วกลับมาสำเร็จ = วิธีที่ระบบเลือกใช้ได้ผลจริง จดไว้
    if row["last_error"]:
        diagnosis.record_outcome(worker["user_id"], row["last_error"], worked=True)
        db.execute("UPDATE jobs SET last_error = '' WHERE id = ?", (job_id,))

    fresh = db.query_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if fresh["thread_id"]:
        from .threads import append_reply

        append_reply(fresh)
    next_job_id = pipeline.advance_chain(fresh)

    events.publish(
        worker["user_id"],
        "job",
        {
            "action": "finished",
            "job_id": job_id,
            "status": "done",
            "duration": round(now - (row["started_at"] or now), 2),
            "meta": body.meta,
            "next_job_id": next_job_id,
        },
    )
    return {"ok": True, "status": "done", "next_job_id": next_job_id}

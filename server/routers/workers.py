"""ยืมพลัง GPU: จับคู่เครื่อง (Colab T4 ฯลฯ), รับ telemetry, จ่ายงานให้ worker."""

from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .. import auth, db, events
from ..security import hash_token, new_pair_code, new_worker_token

router = APIRouter(prefix="/api/v1", tags=["workers"])

PAIR_CODE_TTL = 15 * 60      # รหัสจับคู่มีอายุ 15 นาที
ONLINE_WINDOW = 75           # ไม่ส่งสัญญาณเกินเท่านี้ = ออฟไลน์
LEASE_TIMEOUT = 15 * 60      # งานที่ค้างเกินนี้ถือว่า worker หลุด


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


class ProgressRequest(BaseModel):
    progress: float = 0
    message: str = ""
    level: str = "info"


class CompleteRequest(BaseModel):
    result: str = ""
    error: str = ""
    meta: dict = Field(default_factory=dict)


# ── ตัวช่วย ───────────────────────────────────────────────────
def worker_status(row) -> str:
    if time.time() - row["last_seen_at"] > ONLINE_WINDOW:
        return "offline"
    return row["status"] if row["status"] in {"busy", "idle"} else "idle"


def worker_public(row) -> dict:
    status = worker_status(row)
    vram = row["gpu_vram_mb"] or 0
    return {
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
    """งานที่ worker รับไปแล้วเงียบหาย → คืนกลับคิวให้เครื่องอื่นทำต่อ."""
    cutoff = time.time() - LEASE_TIMEOUT
    db.execute(
        """UPDATE jobs SET status='queued', worker_id=NULL, started_at=NULL, progress=0
           WHERE status='running' AND started_at IS NOT NULL AND started_at < ?""",
        (cutoff,),
    )


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
                  drive_mounted=?,
                  gpu_name=COALESCE(NULLIF(?, ''), gpu_name),
                  gpu_vram_mb=CASE WHEN ? > 0 THEN ? ELSE gpu_vram_mb END
           WHERE id=?""",
        (
            now,
            body.status if body.status in {"idle", "busy"} else "idle",
            body.gpu_used_mb,
            body.gpu_util,
            int(body.drive_mounted),
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
    return {"ok": True, "queued_jobs": pending, "server_time": now}


@router.post("/worker/lease")
def lease_job(worker: dict = Depends(authed_worker)) -> dict:
    """หยิบงานถัดไปจากคิวของเจ้าของเครื่อง (คิวตามลำดับความสำคัญ แล้วค่อยตามเวลา)."""
    reap_stale_jobs()
    now = time.time()
    with db.tx() as conn:
        row = conn.execute(
            """SELECT * FROM jobs
               WHERE user_id = ? AND status = 'queued'
               ORDER BY priority ASC, created_at ASC LIMIT 1""",
            (worker["user_id"],),
        ).fetchone()
        if row is None:
            return {"job": None}
        # อ้าง status เดิมใน WHERE กันสองเครื่องแย่งงานเดียวกัน
        updated = conn.execute(
            """UPDATE jobs SET status='running', worker_id=?, started_at=?, progress=0.01
               WHERE id=? AND status='queued'""",
            (worker["id"], now, row["id"]),
        )
        if updated.rowcount == 0:
            return {"job": None}
        conn.execute("UPDATE workers SET status='busy' WHERE id=?", (worker["id"],))

    db.execute(
        "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
        (row["id"], now, "info", f"เครื่อง {worker['name']} รับงานแล้ว"),
    )
    events.publish(
        worker["user_id"],
        "job",
        {"action": "started", "job_id": row["id"], "worker": worker["name"]},
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
    db.execute("UPDATE jobs SET progress = ? WHERE id = ?", (progress, job_id))
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


@router.post("/worker/jobs/{job_id}/complete")
def complete_job(
    job_id: str, body: CompleteRequest, worker: dict = Depends(authed_worker)
) -> dict:
    row = db.query_one(
        "SELECT * FROM jobs WHERE id = ? AND worker_id = ?", (job_id, worker["id"])
    )
    if row is None:
        raise HTTPException(404, "ไม่พบงานนี้ หรือไม่ได้ถูกมอบหมายให้เครื่องนี้")

    now = time.time()
    status = "failed" if body.error else "done"
    db.execute(
        """UPDATE jobs SET status=?, result=?, error=?, progress=?, finished_at=?
           WHERE id=?""",
        (status, body.result, body.error, 1.0 if status == "done" else row["progress"], now, job_id),
    )
    db.execute(
        "UPDATE workers SET status='idle', jobs_done = jobs_done + 1 WHERE id=?",
        (worker["id"],),
    )
    db.execute(
        "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
        (
            job_id,
            now,
            "error" if body.error else "success",
            body.error[:2000] if body.error else "ทำงานเสร็จสมบูรณ์",
        ),
    )
    events.publish(
        worker["user_id"],
        "job",
        {
            "action": "finished",
            "job_id": job_id,
            "status": status,
            "duration": round(now - (row["started_at"] or now), 2),
            "meta": body.meta,
        },
    )
    return {"ok": True, "status": status}

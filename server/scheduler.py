"""ตัวจัดสรรงานอัจฉริยะ — จับคู่ "งานไหน" กับ "เครื่องไหน" ให้ได้ผลเร็วที่สุด.

เดิมเครื่องไหนมาขอก่อนก็หยิบงานบนสุดของคิวไป ซึ่งมีปัญหาจริงสองข้อ:

* เครื่อง VRAM น้อยหยิบงานโมเดลใหญ่ไปแล้วพัง (CUDA out of memory)
* เครื่องที่โหลดโมเดลค้างไว้แล้ว กลับได้งานที่ต้องโหลดโมเดลใหม่ทั้งก้อน
  ทั้งที่อีกงานในคิวใช้โมเดลที่มันมีอยู่แล้ว

ตัวจัดสรรนี้จึงเลือก "งานที่เหมาะกับเครื่องนี้ที่สุด" แทนที่จะเลือกงานที่มาก่อน.
"""

from __future__ import annotations

import sqlite3
import time

from . import catalog, db

ONLINE_WINDOW = 75          # ไม่ส่งสัญญาณเกินเท่านี้ = ถือว่าออฟไลน์
QUEUE_SCAN_LIMIT = 100      # ดูคิวลึกสุดเท่านี้ก็พอ


# ── ภาพรวมกำลังประมวลผลที่มีอยู่จริงตอนนี้ ────────────────────
def capacity_for(user_id: int) -> dict:
    """สรุปว่าตอนนี้ผู้ใช้คนนี้มีกำลังเครื่องเท่าไหร่ และโมเดลไหนพร้อมรันทันที."""
    cutoff = time.time() - ONLINE_WINDOW
    rows = db.query(
        "SELECT * FROM workers WHERE user_id = ? AND last_seen_at > ?", (user_id, cutoff)
    )
    warm: set[str] = set()
    for row in rows:
        warm.update(db.loads(row["warm_models"], []))

    queued = db.query_one(
        "SELECT COUNT(*) AS n FROM jobs WHERE user_id = ? AND status = 'queued'", (user_id,)
    )["n"]

    return {
        "online": len(rows),
        "idle": len([row for row in rows if row["status"] == "idle"]),
        "best_vram_mb": max((row["gpu_vram_mb"] for row in rows), default=0),
        "total_vram_mb": sum(row["gpu_vram_mb"] for row in rows),
        "warm": sorted(warm),
        "queue_ahead": queued,
    }


def history_for(user_id: int) -> dict[str, float]:
    """เวลาเฉลี่ยจริงของแต่ละโมเดล จากงานที่เคยทำสำเร็จ (ใช้ประเมิน ETA)."""
    rows = db.query(
        """SELECT model, AVG(finished_at - started_at) AS avg_seconds, COUNT(*) AS runs
           FROM jobs
           WHERE user_id = ? AND status = 'done'
             AND started_at IS NOT NULL AND finished_at IS NOT NULL
           GROUP BY model""",
        (user_id,),
    )
    return {row["model"]: float(row["avg_seconds"]) for row in rows if row["runs"] >= 1}


# ── หัวใจ: เลือกงานที่เหมาะกับเครื่องนี้ที่สุด ─────────────────
def job_fits_worker(job_model: str, job_kind: str, worker: dict) -> tuple[bool, str]:
    """เครื่องนี้รับงานนี้ไหวไหม — คืนเหตุผลด้วยเมื่อรับไม่ไหว."""
    model = catalog.get(job_model)
    if model is None:
        return True, ""          # โมเดลนอกแค็ตตาล็อก ปล่อยให้เครื่องตัดสินเอง

    vram = worker.get("gpu_vram_mb") or 0
    if vram and model["vram_mb"] > vram:
        return False, f"ต้องใช้ VRAM {model['vram_mb']} MB แต่เครื่องนี้มี {vram} MB"

    capabilities = db.loads(worker.get("capabilities"), []) if isinstance(
        worker.get("capabilities"), str
    ) else (worker.get("capabilities") or [])
    if capabilities and job_kind not in capabilities:
        return False, f"เครื่องนี้ไม่รองรับงานชนิด {job_kind}"

    return True, ""


def rank_jobs_for_worker(rows: list[sqlite3.Row], worker: dict) -> list[sqlite3.Row]:
    """เรียงงานตามความเหมาะกับเครื่องนี้: โมเดลที่โหลดค้างไว้มาก่อน แล้วค่อยตามคิวปกติ."""
    warm = set(db.loads(worker.get("warm_models"), []) if isinstance(
        worker.get("warm_models"), str
    ) else (worker.get("warm_models") or []))

    eligible = []
    for row in rows:
        ok, _ = job_fits_worker(row["model"], row["kind"], worker)
        if ok:
            eligible.append(row)

    def sort_key(row: sqlite3.Row):
        return (
            0 if row["model"] in warm else 1,   # โหลดค้างไว้แล้ว = เริ่มได้ทันที
            row["priority"],                    # ด่วนกว่ามาก่อน
            row["created_at"],                  # แล้วค่อยมาก่อนได้ก่อน
        )

    return sorted(eligible, key=sort_key)


def claim_next_job(worker: dict) -> tuple[sqlite3.Row | None, str]:
    """จองงานถัดไปให้เครื่องนี้แบบกันแย่งกัน คืน (งาน, เหตุผลที่เลือก)."""
    now = time.time()
    with db.tx() as conn:
        rows = conn.execute(
            """SELECT * FROM jobs
               WHERE user_id = ? AND status = 'queued'
               ORDER BY priority ASC, created_at ASC
               LIMIT ?""",
            (worker["user_id"], QUEUE_SCAN_LIMIT),
        ).fetchall()

        for row in rank_jobs_for_worker(rows, worker):
            claimed = conn.execute(
                """UPDATE jobs
                   SET status='running', worker_id=?, started_at=?, progress_at=?, progress=0.01
                   WHERE id=? AND status='queued'""",
                (worker["id"], now, now, row["id"]),
            )
            if claimed.rowcount:      # ถ้าเป็น 0 แปลว่าเครื่องอื่นชิงไปแล้ว ลองตัวถัดไป
                conn.execute("UPDATE workers SET status='busy' WHERE id=?", (worker["id"],))
                warm = db.loads(worker.get("warm_models"), [])
                reason = (
                    f"เลือกงานนี้เพราะโมเดล {row['model']} ถูกโหลดค้างไว้ในเครื่องนี้อยู่แล้ว"
                    if row["model"] in warm
                    else "เลือกตามลำดับความสำคัญและเวลาที่เข้าคิว"
                )
                return row, reason

    return None, ""


def blocked_reason(user_id: int, job_model: str, job_kind: str) -> str:
    """งานค้างคิวเพราะอะไร — ใช้บอกผู้ใช้ตรง ๆ แทนที่จะปล่อยให้เดา."""
    cutoff = time.time() - ONLINE_WINDOW
    rows = db.query(
        "SELECT * FROM workers WHERE user_id = ? AND last_seen_at > ?", (user_id, cutoff)
    )
    if not rows:
        return "ยังไม่มีเครื่อง GPU ออนไลน์"

    reasons = []
    for row in rows:
        ok, why = job_fits_worker(job_model, job_kind, dict(row))
        if ok:
            return ""            # มีเครื่องที่รับไหว แค่ยังไม่ถึงคิว
        reasons.append(f"{row['name']}: {why}")
    return "ไม่มีเครื่องที่รับงานนี้ไหว — " + " · ".join(reasons[:3])


# ── โหลดโมเดลรอไว้ล่วงหน้า ───────────────────────────────────
PRELOAD_WINDOW_DAYS = 7


def suggest_preload(worker: dict) -> dict | None:
    """เครื่องว่างและคิวโล่ง — บอกให้มันโหลดโมเดลที่น่าจะถูกใช้ต่อไปรอไว้เลย.

    ค่าโหลดโมเดลครั้งแรกคือส่วนที่นานที่สุดของงานแรกในแต่ละวัน การเอาเวลาว่าง
    ที่ยังไงก็เสียเปล่าไปโหลดรอไว้ ทำให้งานแรกที่สั่งจริงเริ่มได้ทันที.
    """
    warm = set(db.loads(worker.get("warm_models"), []) if isinstance(
        worker.get("warm_models"), str) else (worker.get("warm_models") or []))

    pending = db.query_one(
        "SELECT COUNT(*) AS n FROM jobs WHERE user_id = ? AND status IN ('queued','running')",
        (worker["user_id"],),
    )["n"]
    if pending:
        return None          # มีงานค้างอยู่ อย่าไปแย่ง VRAM กับงานจริง

    since = time.time() - PRELOAD_WINDOW_DAYS * 86400
    rows = db.query(
        """SELECT model, COUNT(*) AS uses FROM jobs
           WHERE user_id = ? AND created_at > ? AND model != ''
           GROUP BY model ORDER BY uses DESC LIMIT 5""",
        (worker["user_id"], since),
    )
    for row in rows:
        if row["model"] in warm:
            return None      # ตัวที่ใช้บ่อยที่สุดอยู่ในเครื่องแล้ว ไม่ต้องทำอะไร
        ok, _ = job_fits_worker(row["model"], (catalog.get(row["model"]) or {}).get("kind", "text"), worker)
        if ok:
            model = catalog.get(row["model"])
            return {
                "model": row["model"],
                "repo": model["repo"],
                "quantize": model["quantize"],
                "kind": model["kind"],
                "trust_remote_code": bool(model.get("trust_remote_code")),
                "reason": f"ใช้บ่อยที่สุดใน {PRELOAD_WINDOW_DAYS} วันที่ผ่านมา ({row['uses']} งาน)",
            }
    return None

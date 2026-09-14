"""ลูกโซ่งานและการกู้คืนอัตโนมัติ.

รวมที่เดียวสำหรับ "การสร้างงานหนึ่งชิ้น" เพื่อให้การส่งงานจากหน้าเว็บ และ
การต่อขั้นถัดไปของลูกโซ่ ใช้เส้นทางเดียวกันเป๊ะ ๆ.
"""

from __future__ import annotations

import json
import time
import uuid

from . import brain, catalog, db, events

MAX_CARRY_CHARS = 24_000      # ผลลัพธ์ที่ส่งต่อให้ขั้นถัดไป ยาวได้แค่ไหน
MAX_ATTEMPTS = 2              # ลองกู้อัตโนมัติได้กี่ครั้งต่อหนึ่งงาน


def build_payload(step: dict, previous_result: str = "", context: str = "") -> dict:
    """ประกอบ payload ที่ worker จะได้รับ จากขั้นตอนหนึ่งของแผน."""
    model = catalog.get(step.get("model", "")) or {}
    prompt = step.get("prompt", "")

    if step.get("use_previous") and previous_result:
        carried = previous_result[:MAX_CARRY_CHARS]
        truncated = "\n\n(ตัดมาบางส่วนเพราะยาวเกิน)" if len(previous_result) > MAX_CARRY_CHARS else ""
        prompt = f"{prompt}\n\n--- ผลลัพธ์จากขั้นก่อนหน้า ---\n{carried}{truncated}"

    system = step.get("system", "")
    if context:
        system = (
            f"{system}\n\n" if system else ""
        ) + (
            "ใช้ข้อมูลอ้างอิงต่อไปนี้จากคลังความรู้ของผู้ใช้ประกอบการตอบ "
            "ถ้าข้อมูลไม่พอให้บอกตรง ๆ อย่าเดา:\n" + context
        )

    return {
        "prompt": prompt,
        "system": system,
        "max_tokens": int(step.get("max_tokens", 768)),
        "temperature": float(step.get("temperature", 0.6)),
        "repo": model.get("repo", ""),
        "quantize": model.get("quantize", "fp16"),
        "trust_remote_code": bool(model.get("trust_remote_code")),
        "drive_input": step.get("drive_input", ""),
        "drive_output": step.get("drive_output", ""),
    }


def create_job(
    user_id: int,
    step: dict,
    *,
    chain: list[dict] | None = None,
    parent_id: str | None = None,
    plan: dict | None = None,
    priority: int = 5,
    eta_seconds: float = 0,
    previous_result: str = "",
    context: str = "",
    log_message: str = "เข้าคิวแล้ว รอเครื่องว่าง",
) -> str:
    now = time.time()
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    payload = build_payload(step, previous_result, context)
    title = (step.get("title") or payload["prompt"][:60] or "งานใหม่").strip()[:120]

    db.execute(
        """INSERT INTO jobs
           (id, user_id, kind, model, title, payload, status, priority,
            parent_id, chain, plan, attempt, eta_seconds, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            job_id, user_id, step.get("kind", "text"), step.get("model", ""), title,
            json.dumps(payload, ensure_ascii=False), "queued", priority,
            parent_id, json.dumps(chain or [], ensure_ascii=False),
            json.dumps(plan or {}, ensure_ascii=False), 1, eta_seconds, now,
        ),
    )
    db.execute(
        "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
        (job_id, now, "info", log_message),
    )
    return job_id


def advance_chain(row) -> str | None:
    """งานเสร็จแล้ว — ถ้ายังมีขั้นต่อไปในลูกโซ่ ให้สร้างงานถัดไปทันที."""
    chain = db.loads(row["chain"], [])
    if not chain:
        return None

    next_step, rest = chain[0], chain[1:]
    plan = db.loads(row["plan"], {})
    total = len(plan.get("steps", [])) or (len(chain) + 1)
    done_count = total - len(chain) + 1

    next_id = create_job(
        row["user_id"],
        next_step,
        chain=rest,
        parent_id=row["id"],
        plan=plan,
        priority=row["priority"],
        previous_result=row["result"],
        log_message=f"ขั้นที่ {done_count}/{total} ของลูกโซ่ — รับช่วงต่อจากงานก่อนหน้า",
    )
    db.execute(
        "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
        (row["id"], time.time(), "info",
         f"ส่งผลลัพธ์ต่อให้ขั้นถัดไปแล้ว: {next_step.get('title', '')}"),
    )
    events.publish(
        row["user_id"],
        "job",
        {
            "action": "chained",
            "job_id": next_id,
            "parent_id": row["id"],
            "title": next_step.get("title", ""),
            "step": done_count,
            "total": total,
        },
    )
    return next_id


def maybe_recover(row, error: str) -> str | None:
    """งานล้มเพราะ VRAM ไม่พอ → ลดขนาดโมเดลแล้วเข้าคิวใหม่ให้เอง.

    ใช้งานเดิมต่อ (ไม่สร้างงานใหม่) ผู้ใช้จึงเห็นเป็นงานเดียวที่ระบบแก้ให้เอง
    และลูกโซ่ที่ค้างอยู่ก็ยังเดินต่อได้ตามปกติ.
    """
    if not brain.is_out_of_memory(error) or row["attempt"] >= MAX_ATTEMPTS:
        return None

    fallback = brain.smaller_alternative(row["model"], catalog.models_for(row["user_id"]))
    if fallback is None:
        return None

    model = catalog.get(fallback)
    payload = db.loads(row["payload"], {})
    payload["repo"] = model["repo"]
    payload["quantize"] = model["quantize"]
    payload["trust_remote_code"] = bool(model.get("trust_remote_code"))
    now = time.time()

    db.execute(
        """UPDATE jobs
           SET status='queued', model=?, payload=?, worker_id=NULL, started_at=NULL,
               progress_at=NULL, progress=0, error='', attempt=attempt + 1
           WHERE id=?""",
        (fallback, json.dumps(payload, ensure_ascii=False), row["id"]),
    )
    message = (
        f"หน่วยความจำ GPU ไม่พอสำหรับ {catalog.get(row['model'])['label']} — "
        f"ระบบลดขนาดลงเป็น {model['label']} แล้วเข้าคิวใหม่ให้อัตโนมัติ"
    )
    db.execute(
        "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
        (row["id"], now, "warn", message),
    )
    events.publish(
        row["user_id"],
        "job",
        {"action": "recovered", "job_id": row["id"], "model": fallback, "message": message},
    )
    return fallback

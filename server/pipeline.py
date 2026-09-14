"""ลูกโซ่งานและการกู้คืนอัตโนมัติ.

รวมที่เดียวสำหรับ "การสร้างงานหนึ่งชิ้น" เพื่อให้การส่งงานจากหน้าเว็บ และ
การต่อขั้นถัดไปของลูกโซ่ ใช้เส้นทางเดียวกันเป๊ะ ๆ.
"""

from __future__ import annotations

import json
import time
import uuid

from . import brain, cache, catalog, continuation, db, events, quality

MAX_CARRY_CHARS = 24_000      # ผลลัพธ์ที่ส่งต่อให้ขั้นถัดไป ยาวได้แค่ไหน
MAX_ATTEMPTS = 2              # ลองกู้อัตโนมัติได้กี่ครั้งต่อหนึ่งงาน
MAX_REPAIRS = 2               # ซ่อมผลลัพธ์ที่ใช้ไม่ได้ได้กี่รอบ


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

    messages = step.get("messages") or []
    if messages and context:
        # แทรกบริบทจากคลังความรู้เข้าไปในคำสั่งระบบของบทสนทนา
        messages = [item for item in messages]
        if messages and messages[0].get("role") == "system":
            messages[0] = {"role": "system", "content": system}
        else:
            messages.insert(0, {"role": "system", "content": system})

    return {
        "prompt": prompt,
        "system": system,
        "messages": messages,
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
    thread_id: str | None = None,
    batch_id: str | None = None,
    use_cache: bool = True,
    log_message: str = "เข้าคิวแล้ว รอเครื่องว่าง",
) -> str:
    now = time.time()
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    kind = step.get("kind", "text")
    model = step.get("model", "")
    payload = build_payload(step, previous_result, context)
    title = (step.get("title") or payload["prompt"][:60] or "งานใหม่").strip()[:120]

    # เคยตอบคำถามนี้ไปแล้วหรือเปล่า — ถ้าเคย ก็ไม่ต้องจุดการ์ดจอใหม่
    cached = None
    key = ""
    if use_cache and cache.is_cacheable(payload, kind):
        key = cache.fingerprint(model, payload)
        cached = cache.lookup(user_id, key)

    status = "done" if cached else "queued"
    db.execute(
        """INSERT INTO jobs
           (id, user_id, kind, model, title, payload, status, priority,
            parent_id, chain, plan, attempt, eta_seconds, created_at,
            thread_id, batch_id, from_cache, result, progress, started_at, finished_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            job_id, user_id, kind, model, title,
            json.dumps(payload, ensure_ascii=False), status, priority,
            parent_id, json.dumps(chain or [], ensure_ascii=False),
            json.dumps(plan or {}, ensure_ascii=False), 1, eta_seconds, now,
            thread_id, batch_id, 1 if cached else 0,
            cached["result"] if cached else "", 1.0 if cached else 0,
            now if cached else None, now if cached else None,
        ),
    )
    db.execute(
        "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
        (job_id, now, "success" if cached else "info",
         "ตอบจากผลลัพธ์ที่เคยคำนวณไว้แล้ว — ไม่ได้ใช้ GPU เลย" if cached else log_message),
    )

    if cached:
        cache.record_hit(key, eta_seconds)
        events.publish(
            user_id, "job",
            {"action": "finished", "job_id": job_id, "status": "done",
             "from_cache": True, "duration": 0},
        )
        advance_chain(db.query_one("SELECT * FROM jobs WHERE id = ?", (job_id,)))
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


def maybe_repair(row, result: str, meta: dict) -> quality.Verdict | None:
    """ผลลัพธ์ที่ "เสร็จแล้วแต่ใช้ไม่ได้" → ปรับพารามิเตอร์แล้วสั่งทำใหม่.

    ต่างจาก maybe_recover ตรงที่งานไม่ได้โยน error ออกมาเลย มันบอกว่าสำเร็จ
    แต่สิ่งที่ได้กลับมาคือข้อความว่าง ประโยคที่ถูกตัด หรือคำที่วนซ้ำไม่จบ.
    """
    payload = db.loads(row["payload"], {})
    verdict = quality.inspect(result, meta, payload, row["kind"])
    if verdict.ok:
        return None

    repairs = db.loads(row["repairs"], [])
    if len(repairs) >= MAX_REPAIRS:
        return None

    # ถูกตัดกลางคัน = เขียนต่อได้ ไม่ต้องเผา GPU เขียนส่วนเดิมซ้ำทั้งหมด
    if verdict.problem == "truncated":
        merged = continuation.stitch(row["result_prefix"], result)
        if continuation.can_continue(row["kind"], merged, row["continued"]):
            db.execute("UPDATE jobs SET result = ? WHERE id = ?", (result, row["id"]))
            fresh = db.query_one("SELECT * FROM jobs WHERE id = ?", (row["id"],))
            if requeue_for_continuation(fresh, "คำตอบชนเพดานโทเคน"):
                return verdict

    payload.update(verdict.repair or {})
    repairs.append({"problem": verdict.problem, "detail": verdict.detail,
                    "changed": verdict.repair or {}, "at": time.time()})
    now = time.time()
    db.execute(
        """UPDATE jobs
           SET status='queued', payload=?, repairs=?, worker_id=NULL, started_at=NULL,
               progress_at=NULL, progress=0, result='', error=''
           WHERE id=?""",
        (json.dumps(payload, ensure_ascii=False),
         json.dumps(repairs, ensure_ascii=False), row["id"]),
    )
    message = quality.describe_repair(verdict)
    db.execute(
        "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
        (row["id"], now, "warn", message),
    )
    events.publish(
        row["user_id"], "job",
        {"action": "repaired", "job_id": row["id"], "problem": verdict.problem,
         "message": message},
    )
    return verdict


def requeue_for_continuation(row, reason: str) -> bool:
    """เอางานกลับเข้าคิว โดยเก็บข้อความที่เขียนไปแล้วไว้ให้เขียนต่อ.

    คืน True เมื่อเขียนต่อได้ · คืน False เมื่อสั่งเริ่มใหม่ตั้งแต่ต้น
    (ซึ่งต้องล้างข้อความเดิมทิ้ง ไม่งั้นรอบใหม่จะไปต่อท้ายของเก่าจนซ้ำกัน)
    """
    partial = continuation.stitch(row["result_prefix"], row["result"])
    now = time.time()

    if not continuation.can_continue(row["kind"], partial, row["continued"]):
        db.execute(
            """UPDATE jobs
               SET status='queued', worker_id=NULL, started_at=NULL, progress_at=NULL,
                   progress=0, result='', result_prefix='', error=''
               WHERE id=?""",
            (row["id"],),
        )
        db.execute(
            "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
            (row["id"], now, "warn", f"{reason} — เริ่มงานใหม่ตั้งแต่ต้น"),
        )
        return False

    payload = continuation.build_payload(db.loads(row["payload"], {}), partial, reason)
    continued = row["continued"] + 1
    db.execute(
        """UPDATE jobs
           SET status='queued', worker_id=NULL, started_at=NULL, progress_at=NULL,
               progress=0, payload=?, result='', result_prefix=?, continued=?, error=''
           WHERE id=?""",
        (json.dumps(payload, ensure_ascii=False), partial, continued, row["id"]),
    )
    message = continuation.describe(reason, partial, continued)
    db.execute(
        "INSERT INTO job_events (job_id, ts, level, message) VALUES (?,?,?,?)",
        (row["id"], now, "warn", message),
    )
    events.publish(
        row["user_id"], "job",
        {"action": "continued", "job_id": row["id"], "kept_chars": len(partial),
         "message": message},
    )
    return True

"""บทสนทนาต่อเนื่อง — คุยกับโมเดลได้หลายรอบโดยมันจำเรื่องที่คุยไปแล้ว."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, brain, catalog, db, events, pipeline, scheduler
from .jobs import _vault_context

router = APIRouter(prefix="/api/v1/threads", tags=["threads"])

HISTORY_BUDGET_CHARS = 12_000    # ย้อนความได้ไกลแค่ไหนก่อนจะกินบริบทหมด
MAX_TURNS = 40
KEEP_RECENT_TURNS = 8            # รอบล่าสุดเท่านี้เก็บไว้เต็ม ๆ เสมอ
MIN_STALE_CHARS = 4_000          # น้อยกว่านี้ไม่คุ้มจะเสีย GPU ไปย่อ


class ThreadRequest(BaseModel):
    title: str = Field(default="", max_length=120)
    model: str = Field(default="auto", max_length=120)
    system: str = Field(default="", max_length=8_000)
    use_vault: bool = True


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=32_000)
    model: str = ""          # เปลี่ยนโมเดลกลางบทสนทนาได้


def _thread_or_404(thread_id: str, user_id: int) -> dict:
    row = db.query_one(
        "SELECT * FROM threads WHERE id = ? AND user_id = ?", (thread_id, user_id)
    )
    if row is None:
        raise HTTPException(404, "ไม่พบบทสนทนานี้")
    return dict(row)


def _messages(thread_id: str) -> list[dict]:
    return [
        dict(row) for row in db.query(
            "SELECT id, role, content, job_id, created_at FROM messages "
            "WHERE thread_id = ? ORDER BY id", (thread_id,)
        )
    ]


def build_history(thread_id: str, system: str, memory: str = "") -> list[dict]:
    """ประกอบบทสนทนาให้โมเดล โดยตัดของเก่าทิ้งเมื่อยาวเกินงบบริบท.

    ข้อความล่าสุดของผู้ใช้ถูกบันทึกลงฐานข้อมูลไปแล้วก่อนเรียกฟังก์ชันนี้
    จึงอยู่ท้ายรายการอยู่แล้ว — ห้ามเติมซ้ำ ไม่งั้นโมเดลจะเห็นคำถามเดียวกันสองรอบ.

    รอบเก่าที่ถูกตัดออกไปไม่ได้หายไปเฉย ๆ — มันถูกย่อเป็น "บันทึกความจำ"
    (memory) แล้วแนบไปกับคำสั่งระบบแทน โมเดลจึงยังรู้เรื่องที่คุยไปนานแล้ว.
    """
    history = _messages(thread_id)[-MAX_TURNS:]

    kept: list[dict] = []
    budget = HISTORY_BUDGET_CHARS
    for message in reversed(history):          # เก็บรอบล่าสุดไว้ก่อนเสมอ
        cost = len(message["content"])
        if cost > budget and kept:
            break
        budget -= cost
        kept.append({"role": message["role"], "content": message["content"]})
    kept.reverse()

    preamble = system.strip()
    if memory.strip():
        preamble = (preamble + "\n\n" if preamble else "") + (
            "สรุปสิ่งที่คุยกันไปก่อนหน้านี้ (ใช้เป็นความจำ):\n" + memory.strip()
        )

    conversation = []
    if preamble:
        conversation.append({"role": "system", "content": preamble})
    conversation.extend(kept)
    return conversation


def needs_compression(thread_id: str, compressed_upto: int) -> list[dict]:
    """รอบเก่าที่ควรย่อเก็บไว้แล้ว — คืนว่างถ้ายังไม่ถึงเวลา.

    จังหวะที่ต้องย่อคือ *ก่อน* ที่งบบริบทจะบังคับให้ตัดของเก่าทิ้ง ไม่ใช่หลังจากนั้น
    ไม่งั้นเนื้อหาจะหายไปแล้วตั้งแต่ก่อนจะได้ย่อ.
    """
    # มีงานย่อค้างอยู่แล้ว อย่าสั่งซ้ำ — รอบนั้นจะอัปเดตความจำให้อยู่แล้ว
    pending = db.query_one(
        """SELECT id FROM jobs
           WHERE thread_id = ? AND status IN ('queued','running')
             AND plan LIKE '%"compress": true%' LIMIT 1""",
        (thread_id,),
    )
    if pending:
        return []

    messages = _messages(thread_id)
    if sum(len(message["content"]) for message in messages) < HISTORY_BUDGET_CHARS:
        return []

    stale = [
        message for message in messages[:-KEEP_RECENT_TURNS]
        if message["id"] > compressed_upto
    ]
    if sum(len(message["content"]) for message in stale) < MIN_STALE_CHARS:
        return []
    return stale


def start_compression(user_id: int, thread: dict, stale: list[dict]) -> str | None:
    """สั่งงานย่อบทสนทนาเก่าเป็นบันทึกความจำ (ทำเป็นงานเบื้องหลัง ไม่ขวางการคุย)."""
    from .. import brain, scheduler as sched

    capacity = sched.capacity_for(user_id)
    models = catalog.models_for(user_id)
    intent = brain.analyze("สรุปบทสนทนา")
    model_id, _, _ = brain.pick_model(intent, capacity, models)

    transcript = flatten([
        {"role": message["role"], "content": message["content"]} for message in stale
    ])[:40_000]
    previous = thread["memory"].strip()

    step = {
        "kind": "text", "model": model_id, "title": "ย่อความจำของบทสนทนา",
        "prompt": (
            "ย่อบทสนทนาต่อไปนี้เป็นบันทึกความจำสั้น ๆ เป็นภาษาไทย เก็บเฉพาะ "
            "ข้อเท็จจริงเกี่ยวกับผู้ใช้ สิ่งที่ตกลงกันไว้ และเรื่องที่ค้างอยู่ "
            "เขียนเป็นข้อ ๆ ไม่เกิน 12 ข้อ ห้ามแต่งเติมสิ่งที่ไม่ได้พูดถึง\n\n"
            + (f"บันทึกความจำเดิม:\n{previous}\n\n" if previous else "")
            + f"บทสนทนาที่ต้องย่อ:\n{transcript}"
        ),
        "max_tokens": 900, "temperature": 0.2,
    }
    job_id = pipeline.create_job(
        user_id, step, thread_id=thread["id"],
        plan={"reason": "ย่อรอบเก่าเป็นความจำ เพื่อให้คุยต่อได้ยาวโดยไม่ลืมเรื่องเดิม",
              "steps": [step], "compress": True},
        priority=8,     # เป็นงานเบื้องหลัง อย่าไปแย่งคิวงานที่ผู้ใช้รออยู่
        log_message="ย่อบทสนทนาเก่าเป็นบันทึกความจำ",
    )
    db.execute(
        "UPDATE threads SET compressed_upto = ? WHERE id = ?",
        (stale[-1]["id"], thread["id"]),
    )
    return job_id


def store_memory(job) -> None:
    """เก็บผลการย่อลงเป็นความจำของบทสนทนา."""
    if not job["thread_id"] or not job["result"].strip():
        return
    db.execute(
        "UPDATE threads SET memory = ? WHERE id = ?",
        (job["result"].strip()[:8_000], job["thread_id"]),
    )
    events.publish(
        job["user_id"], "thread",
        {"action": "memory", "thread_id": job["thread_id"]},
    )


def flatten(conversation: list[dict]) -> str:
    """แปลงบทสนทนาเป็นข้อความเดียว เผื่อโมเดลที่ไม่มี chat template."""
    labels = {"system": "คำสั่งระบบ", "user": "ผู้ใช้", "assistant": "ผู้ช่วย"}
    lines = [
        f"{labels.get(item['role'], item['role'])}: {item['content']}"
        for item in conversation if item["role"] != "system"
    ]
    return "\n\n".join(lines)


@router.post("")
def create_thread(body: ThreadRequest, user: dict = Depends(auth.require_user)) -> dict:
    now = time.time()
    thread_id = f"th_{uuid.uuid4().hex[:12]}"
    db.execute(
        """INSERT INTO threads (id, user_id, title, model, system, use_vault, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (thread_id, user["id"], body.title.strip() or "บทสนทนาใหม่", body.model,
         body.system, int(body.use_vault), now, now),
    )
    return {"id": thread_id, "title": body.title.strip() or "บทสนทนาใหม่"}


@router.get("")
def list_threads(user: dict = Depends(auth.require_user), limit: int = 50) -> dict:
    rows = db.query(
        """SELECT t.*, (SELECT COUNT(*) FROM messages m WHERE m.thread_id = t.id) AS turns,
                  (SELECT content FROM messages m WHERE m.thread_id = t.id
                   ORDER BY m.id DESC LIMIT 1) AS last_message
           FROM threads t WHERE t.user_id = ? ORDER BY t.updated_at DESC LIMIT ?""",
        (user["id"], max(1, min(limit, 200))),
    )
    return {
        "threads": [
            {
                "id": row["id"], "title": row["title"], "model": row["model"],
                "turns": row["turns"], "updated_at": row["updated_at"],
                "preview": (row["last_message"] or "")[:120],
            }
            for row in rows
        ]
    }


@router.get("/{thread_id}")
def get_thread(thread_id: str, user: dict = Depends(auth.require_user)) -> dict:
    thread = _thread_or_404(thread_id, user["id"])
    messages = _messages(thread_id)

    # งานที่ยังทำอยู่ของรอบล่าสุด (ใช้แสดงสถานะกำลังพิมพ์)
    pending = db.query_one(
        """SELECT id, status, progress, result FROM jobs
           WHERE thread_id = ? AND status IN ('queued','running')
             AND plan NOT LIKE '%"compress": true%'
           ORDER BY created_at DESC LIMIT 1""",
        (thread_id,),
    )
    return {
        "thread": {**thread, "use_vault": bool(thread["use_vault"]),
                   "has_memory": bool(thread["memory"].strip())},
        "messages": messages,
        "pending": dict(pending) if pending else None,
    }


@router.post("/{thread_id}/messages")
def send_message(
    thread_id: str, body: MessageRequest, user: dict = Depends(auth.require_user)
) -> dict:
    thread = _thread_or_404(thread_id, user["id"])
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "ข้อความว่างเปล่า พิมพ์อะไรสักอย่างก่อน")

    now = time.time()
    db.execute(
        "INSERT INTO messages (thread_id, role, content, created_at) VALUES (?,?,?,?)",
        (thread_id, "user", content, now),
    )

    capacity, history = scheduler.capacity_for(user["id"]), scheduler.history_for(user["id"])
    models = catalog.models_for(user["id"])
    chosen = body.model or thread["model"]

    if chosen in {"", "auto"}:
        intent = brain.analyze(content)
        model_id, reason, _ = brain.pick_model(intent, capacity, models)
        max_tokens, temperature = intent.max_tokens, intent.temperature
    else:
        if not catalog.owns(chosen, user["id"]) or catalog.get(chosen) is None:
            raise HTTPException(400, f"ใช้โมเดล '{chosen}' ไม่ได้")
        model_id, reason = chosen, "ผู้ใช้เลือกโมเดลไว้กับบทสนทนานี้"
        max_tokens, temperature = 1024, 0.6

    conversation = build_history(thread_id, thread["system"], thread["memory"])

    context = ""
    if thread["use_vault"]:
        context, _ = _vault_context(user["id"], content)

    step = {
        "kind": "text", "model": model_id,
        "title": content[:60] or "ข้อความใหม่",
        "prompt": flatten(conversation),
        "system": thread["system"],
        "max_tokens": max_tokens, "temperature": temperature,
        "messages": conversation,
    }
    job_id = pipeline.create_job(
        user["id"], step, thread_id=thread_id,
        plan={"reason": reason, "steps": [step], "chat": True},
        eta_seconds=brain.estimate_seconds(model_id, history, set(capacity["warm"])),
        context=context,
        log_message=f"ข้อความในบทสนทนา · {reason[:120]}",
    )

    # ตอบจากแคชได้ทันที ก็บันทึกคำตอบลงบทสนทนาเลย
    job = db.query_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if job["status"] == "done":
        append_reply(job)

    # บทสนทนายาวขึ้นเรื่อย ๆ — ย่อรอบเก่าเก็บไว้เป็นความจำแทนที่จะทิ้ง
    stale = needs_compression(thread_id, thread["compressed_upto"])
    if stale:
        start_compression(user["id"], thread, stale)

    db.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id))
    if len(_messages(thread_id)) <= 2 and thread["title"] == "บทสนทนาใหม่":
        db.execute("UPDATE threads SET title = ? WHERE id = ?", (content[:60], thread_id))

    return {"job_id": job_id, "model": model_id, "reason": reason,
            "from_cache": bool(job["from_cache"])}


def append_reply(job) -> None:
    """เก็บคำตอบของโมเดลเข้าบทสนทนา — เรียกเมื่องานเสร็จ."""
    if not job["thread_id"] or not job["result"].strip():
        return
    if db.loads(job["plan"], {}).get("compress"):
        store_memory(job)       # งานย่อความจำ ไม่ใช่คำตอบที่ผู้ใช้ต้องเห็น
        return
    already = db.query_one(
        "SELECT id FROM messages WHERE job_id = ?", (job["id"],)
    )
    if already:
        return          # กันบันทึกซ้ำเมื่อ worker ส่งผลมาสองรอบ
    now = time.time()
    db.execute(
        "INSERT INTO messages (thread_id, role, content, job_id, created_at) VALUES (?,?,?,?,?)",
        (job["thread_id"], "assistant", job["result"], job["id"], now),
    )
    db.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, job["thread_id"]))
    events.publish(
        job["user_id"], "thread",
        {"action": "reply", "thread_id": job["thread_id"], "job_id": job["id"]},
    )


@router.delete("/{thread_id}")
def delete_thread(thread_id: str, user: dict = Depends(auth.require_user)) -> dict:
    _thread_or_404(thread_id, user["id"])
    db.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
    return {"ok": True}

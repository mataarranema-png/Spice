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


def build_history(thread_id: str, system: str) -> list[dict]:
    """ประกอบบทสนทนาให้โมเดล โดยตัดของเก่าทิ้งเมื่อยาวเกินงบบริบท.

    ข้อความล่าสุดของผู้ใช้ถูกบันทึกลงฐานข้อมูลไปแล้วก่อนเรียกฟังก์ชันนี้
    จึงอยู่ท้ายรายการอยู่แล้ว — ห้ามเติมซ้ำ ไม่งั้นโมเดลจะเห็นคำถามเดียวกันสองรอบ.
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

    conversation = []
    if system.strip():
        conversation.append({"role": "system", "content": system.strip()})
    conversation.extend(kept)
    return conversation


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
           ORDER BY created_at DESC LIMIT 1""",
        (thread_id,),
    )
    return {
        "thread": {**thread, "use_vault": bool(thread["use_vault"])},
        "messages": messages,
        "pending": dict(pending) if pending else None,
    }


@router.post("/{thread_id}/messages")
def send_message(
    thread_id: str, body: MessageRequest, user: dict = Depends(auth.require_user)
) -> dict:
    thread = _thread_or_404(thread_id, user["id"])
    now = time.time()
    content = body.content.strip()

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

    conversation = build_history(thread_id, thread["system"])

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

    db.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id))
    if len(_messages(thread_id)) <= 2 and thread["title"] == "บทสนทนาใหม่":
        db.execute("UPDATE threads SET title = ? WHERE id = ?", (content[:60], thread_id))

    return {"job_id": job_id, "model": model_id, "reason": reason,
            "from_cache": bool(job["from_cache"])}


def append_reply(job) -> None:
    """เก็บคำตอบของโมเดลเข้าบทสนทนา — เรียกเมื่องานเสร็จ."""
    if not job["thread_id"] or not job["result"].strip():
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

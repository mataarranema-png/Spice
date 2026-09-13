"""บัสเหตุการณ์ในหน่วยความจำ สำหรับส่งอัปเดตสดไปหน้าเว็บผ่าน SSE."""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from typing import Any

_subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)
_MAX_QUEUE = 256


def subscribe(user_id: int) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE)
    _subscribers[user_id].add(queue)
    return queue


def unsubscribe(user_id: int, queue: asyncio.Queue) -> None:
    _subscribers[user_id].discard(queue)
    if not _subscribers[user_id]:
        _subscribers.pop(user_id, None)


def publish(user_id: int, event: str, data: dict[str, Any]) -> None:
    """ส่งแบบไม่บล็อก — ผู้ฟังที่ช้าเกินไปจะถูกข้าม ไม่ทำให้ worker ค้าง."""
    message = {"event": event, "data": data, "ts": time.time()}
    for queue in list(_subscribers.get(user_id, ())):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass


def format_sse(message: dict[str, Any]) -> str:
    payload = json.dumps(
        {"ts": message["ts"], **message["data"]}, ensure_ascii=False, default=str
    )
    return f"event: {message['event']}\ndata: {payload}\n\n"


def subscriber_count(user_id: int) -> int:
    return len(_subscribers.get(user_id, ()))

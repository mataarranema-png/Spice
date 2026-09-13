"""Vector Vault — คลังความรู้ของ Spice เก็บใน SQLite ค้นด้วย cosine.

โหมดการค้นมีสองระดับ:

1. **ค้นเชิงความหมายเต็มรูปแบบ** — เมื่อส่ง embedding จากโมเดลจริง (เช่น BGE-M3
   ที่รันบนเครื่อง GPU) เข้ามาพร้อมเอกสารและคำค้น จะเข้าใจคำที่ความหมาย
   ใกล้กันแม้สะกดไม่เหมือนกันเลย
2. **ค้นแบบใกล้เคียงตัวอักษร (ตัวสำรองในเครื่อง)** — ใช้ hashing ของ
   character n-gram ทำงานได้ทันทีโดยไม่ต้องมี GPU และเหมาะกับภาษาไทยที่ไม่
   เว้นวรรค แต่จับได้เฉพาะความคล้ายของตัวอักษร ไม่ใช่ความหมาย
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid

import numpy as np

from . import db

LOCAL_DIM = 512
_WORD = re.compile(r"[A-Za-z0-9]+")


def _tokens(text: str) -> list[str]:
    """ผสมคำอังกฤษ/ตัวเลข กับ 3-gram ของตัวอักษร (รองรับไทยที่ไม่เว้นวรรค)."""
    text = text.lower().strip()
    grams = [text[i : i + 3] for i in range(max(0, len(text) - 2))]
    return _WORD.findall(text) + grams


def local_embed(text: str, dim: int = LOCAL_DIM) -> np.ndarray:
    vector = np.zeros(dim, dtype=np.float32)
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


def to_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32, count=dim)


def normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


def add_document(
    user_id: int,
    text: str,
    title: str = "",
    collection: str = "default",
    meta: str = "{}",
    embedding: list[float] | None = None,
) -> dict:
    vector = normalize(np.asarray(embedding, dtype=np.float32)) if embedding else local_embed(text)
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    db.execute(
        """INSERT INTO vault_docs
           (id, user_id, collection, title, text, meta, dim, embedding, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            doc_id,
            user_id,
            collection,
            title or text[:60],
            text,
            meta,
            len(vector),
            to_blob(vector),
            time.time(),
        ),
    )
    return {"id": doc_id, "dim": len(vector), "source": "model" if embedding else "local"}


SUBSTRING_BOOST = 0.35
MIN_SCORE = 0.02


def search(
    user_id: int,
    query: str,
    collection: str = "",
    top_k: int = 5,
    query_embedding: list[float] | None = None,
) -> list[dict]:
    semantic = bool(query_embedding)
    needle = (
        normalize(np.asarray(query_embedding, dtype=np.float32))
        if semantic
        else local_embed(query)
    )
    needle_text = query.lower().strip()

    sql = "SELECT * FROM vault_docs WHERE user_id = ?"
    params: tuple = (user_id,)
    if collection:
        sql += " AND collection = ?"
        params += (collection,)

    scored = []
    for row in db.query(sql, params):
        if row["dim"] != len(needle):
            continue  # ข้ามเอกสารที่ทำ embedding ด้วยโมเดลคนละมิติ
        score = float(np.dot(from_blob(row["embedding"], row["dim"]), needle))
        # โหมดตัวสำรอง: ถ้าคำค้นปรากฏตรง ๆ ในเอกสาร ให้ถือว่าตรงมาก
        if not semantic and needle_text and needle_text in row["text"].lower():
            score = min(1.0, score + SUBSTRING_BOOST)
        if score < MIN_SCORE:
            continue          # ตัดเอกสารที่ไม่เกี่ยวทิ้ง ดีกว่าโชว์คะแนนติดลบ
        scored.append(
            {
                "id": row["id"],
                "title": row["title"],
                "text": row["text"],
                "collection": row["collection"],
                "score": round(score, 4),
                "created_at": row["created_at"],
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[: max(1, min(top_k, 50))]

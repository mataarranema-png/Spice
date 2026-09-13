"""เส้นทาง API ของคลังความรู้ (Vault)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, db, vault

router = APIRouter(prefix="/api/v1/vault", tags=["vault"])


class DocRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    title: str = Field(default="", max_length=200)
    collection: str = Field(default="default", max_length=60)
    meta: dict = Field(default_factory=dict)
    embedding: list[float] | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4_000)
    collection: str = ""
    top_k: int = Field(default=5, ge=1, le=50)


@router.post("/docs")
def add_doc(body: DocRequest, user: dict = Depends(auth.require_user)) -> dict:
    result = vault.add_document(
        user_id=user["id"],
        text=body.text,
        title=body.title,
        collection=body.collection,
        meta=json.dumps(body.meta, ensure_ascii=False),
        embedding=body.embedding,
    )
    return {"ok": True, **result}


@router.post("/search")
def search_docs(body: SearchRequest, user: dict = Depends(auth.require_user)) -> dict:
    hits = vault.search(user["id"], body.query, body.collection, body.top_k)
    return {"hits": hits, "count": len(hits)}


@router.get("/collections")
def collections(user: dict = Depends(auth.require_user)) -> dict:
    rows = db.query(
        """SELECT collection, COUNT(*) AS docs, MAX(created_at) AS updated_at
           FROM vault_docs WHERE user_id = ? GROUP BY collection ORDER BY docs DESC""",
        (user["id"],),
    )
    return {"collections": [dict(row) for row in rows]}


@router.delete("/docs/{doc_id}")
def delete_doc(doc_id: str, user: dict = Depends(auth.require_user)) -> dict:
    row = db.query_one(
        "SELECT id FROM vault_docs WHERE id = ? AND user_id = ?", (doc_id, user["id"])
    )
    if row is None:
        raise HTTPException(404, "ไม่พบเอกสารนี้")
    db.execute("DELETE FROM vault_docs WHERE id = ?", (doc_id,))
    return {"ok": True}

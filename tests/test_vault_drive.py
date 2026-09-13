"""เทสต์คลังความรู้ (Vault) และการเชื่อม Google Drive / rclone."""

import json
import time

from server import db, vault
from server.security import decrypt, encrypt, sign_state, verify_state


# ── Vault ────────────────────────────────────────────────────
def test_add_and_search_thai_documents(user_client):
    docs = [
        "วิธีเมานต์ Google Drive ด้วย rclone บน Colab ให้เร็วที่สุด",
        "สูตรทำแกงเขียวหวานไก่ใส่มะเขือพวง",
        "การตั้งค่า Tesla T4 ให้โหลดโมเดล 7B แบบ 4bit",
    ]
    for text in docs:
        assert user_client.post("/api/v1/vault/docs", json={"text": text}).json()["ok"] is True

    hits = user_client.post(
        "/api/v1/vault/search", json={"query": "rclone เมานต์ไดรฟ์", "top_k": 3}
    ).json()["hits"]
    assert hits[0]["text"] == docs[0]              # เอกสารเรื่อง rclone ต้องมาอันดับหนึ่ง
    assert hits[0]["score"] > hits[-1]["score"]


def test_search_scoped_by_collection(user_client):
    user_client.post("/api/v1/vault/docs", json={"text": "บันทึกประชุม", "collection": "meetings"})
    user_client.post("/api/v1/vault/docs", json={"text": "บันทึกประชุม", "collection": "notes"})
    hits = user_client.post(
        "/api/v1/vault/search", json={"query": "ประชุม", "collection": "meetings"}
    ).json()["hits"]
    assert len(hits) == 1 and hits[0]["collection"] == "meetings"


def test_collections_summary_and_delete(user_client):
    doc_id = user_client.post(
        "/api/v1/vault/docs", json={"text": "เอกสารเดียว", "collection": "solo"}
    ).json()["id"]
    collections = user_client.get("/api/v1/vault/collections").json()["collections"]
    assert collections[0]["collection"] == "solo" and collections[0]["docs"] == 1
    assert user_client.delete(f"/api/v1/vault/docs/{doc_id}").json()["ok"] is True
    assert user_client.delete(f"/api/v1/vault/docs/{doc_id}").status_code == 404


def test_model_embeddings_are_accepted(user_client):
    body = user_client.post(
        "/api/v1/vault/docs", json={"text": "เวกเตอร์จากโมเดลจริง", "embedding": [0.3] * 1024}
    ).json()
    assert body["dim"] == 1024 and body["source"] == "model"


def test_local_embedding_is_normalized_and_stable():
    first = vault.local_embed("ทดสอบความเสถียร")
    second = vault.local_embed("ทดสอบความเสถียร")
    assert (first == second).all()
    assert abs(float((first * first).sum()) - 1.0) < 1e-5


def test_vault_is_private_per_user(user_client, client):
    user_client.post("/api/v1/vault/docs", json={"text": "ความลับของฉัน"})
    user_client.post("/auth/logout")
    client.post("/auth/dev", params={"email": "nosy@spice.local"})
    assert client.post("/api/v1/vault/search", json={"query": "ความลับ"}).json()["hits"] == []


# ── Drive / rclone ───────────────────────────────────────────
def test_drive_status_reports_not_connected(user_client):
    body = user_client.get("/api/v1/drive/status").json()
    assert body["connected"] is False


def test_rclone_config_requires_drive_grant(user_client):
    assert user_client.get("/api/v1/drive/rclone.conf").status_code == 400


def _grant_drive(email: str = "pilot@spice.local") -> int:
    """จำลองว่าผู้ใช้กดอนุญาตสิทธิ์ Drive แล้ว."""
    user_id = db.query_one("SELECT id FROM users WHERE email = ?", (email,))["id"]
    db.execute(
        """INSERT OR REPLACE INTO google_tokens
           (user_id, refresh_token, access_token, expires_at, scopes, updated_at)
           VALUES (?,?,?,?,?,?)""",
        (
            user_id,
            encrypt("1//fake-refresh-token"),
            encrypt("ya29.fake-access-token"),
            time.time() + 3600,
            "openid email profile https://www.googleapis.com/auth/drive",
            time.time(),
        ),
    )
    return user_id


def test_rclone_config_is_valid_for_rclone(user_client):
    _grant_drive()
    text = user_client.get("/api/v1/drive/rclone.conf").text
    assert text.startswith("[gdrive]")
    assert "type = drive" in text
    assert "scope = drive" in text
    token_line = [line for line in text.splitlines() if line.startswith("token = ")][0]
    token = json.loads(token_line.removeprefix("token = "))
    assert token["refresh_token"] == "1//fake-refresh-token"
    assert token["token_type"] == "Bearer"
    assert token["expiry"].endswith("Z")          # rclone ต้องการเวลาแบบ RFC3339


def test_rclone_preview_hides_secrets(user_client):
    _grant_drive()
    body = user_client.get("/api/v1/drive/rclone/preview").json()
    assert "••••" in body["config_masked"]
    assert "fake-refresh-token" not in body["config_masked"]
    assert any("rclone mount" in item["cmd"] for item in body["commands"])


def test_worker_can_fetch_owner_rclone_config(user_client, worker):
    _grant_drive()
    body = user_client.get("/api/v1/worker/rclone", headers=worker["headers"]).json()
    assert body["remote"] == "gdrive"
    assert "[gdrive]" in body["conf"]


def test_worker_without_token_cannot_fetch_config(client):
    assert client.get("/api/v1/worker/rclone").status_code == 401


# ── ความปลอดภัยพื้นฐาน ───────────────────────────────────────
def test_tokens_are_encrypted_at_rest(user_client):
    user_id = _grant_drive()
    raw = db.query_one("SELECT refresh_token FROM google_tokens WHERE user_id=?", (user_id,))
    assert "1//fake-refresh-token" not in raw["refresh_token"]
    assert decrypt(raw["refresh_token"]) == "1//fake-refresh-token"


def test_worker_tokens_are_never_stored_in_plain_text(user_client, worker):
    stored = db.query_one("SELECT token_hash FROM workers WHERE id=?", (worker["id"],))
    assert worker["token"] not in stored["token_hash"]
    assert len(stored["token_hash"]) == 64        # sha256 hex


def test_oauth_state_signature_and_expiry():
    state = sign_state("1|/app")
    assert verify_state(state) == "1|/app"
    assert verify_state(state + "x") is None
    assert verify_state(state, max_age=-1) is None

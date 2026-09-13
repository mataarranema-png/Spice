"""ตั้งค่าสภาพแวดล้อมสำหรับเทสต์ — ใช้ฐานข้อมูลชั่วคราวแยกจากของจริง."""

import os
import tempfile

import pytest

TMP_DB = os.path.join(tempfile.mkdtemp(prefix="spice-test-"), "test.db")
os.environ.update(
    SPICE_DB_PATH=TMP_DB,
    SPICE_SECRET_KEY="test-secret-key-for-pytest-only-0123456789",
    SPICE_DEV_LOGIN="1",
    SPICE_BASE_URL="http://testserver",
    GOOGLE_CLIENT_ID="test-client-id.apps.googleusercontent.com",
    GOOGLE_CLIENT_SECRET="test-client-secret",
    SPICE_ALLOWED_EMAILS="",
    SPICE_ALLOWED_DOMAINS="",
)

from fastapi.testclient import TestClient  # noqa: E402

from server import db  # noqa: E402
from server.main import app  # noqa: E402


@pytest.fixture()
def client():
    db.init_db()
    with TestClient(app) as test_client:
        yield test_client
    for table in ("job_events", "jobs", "vault_docs", "pair_codes", "workers",
                  "google_tokens", "audit_log", "users"):
        db.execute(f"DELETE FROM {table}")


@pytest.fixture()
def user_client(client):
    """ไคลเอนต์ที่ล็อกอินแล้ว (ผ่านทางลัดโหมดพัฒนา)."""
    resp = client.post("/auth/dev", params={"email": "pilot@spice.local", "name": "Pilot"})
    assert resp.status_code == 204
    return client


@pytest.fixture()
def worker(user_client):
    """เครื่อง worker ที่จับคู่เรียบร้อย พร้อม header สำหรับเรียก API."""
    code = user_client.post("/api/v1/workers/pair", json={"label": "Colab T4"}).json()["pair_code"]
    data = user_client.post(
        "/api/v1/worker/register",
        json={
            "pair_code": code,
            "name": "colab-t4",
            "gpu_name": "Tesla T4",
            "gpu_vram_mb": 15360,
            "driver": "535.104",
            "capabilities": ["text", "image"],
        },
    ).json()
    return {
        "id": data["worker_id"],
        "token": data["worker_token"],
        "headers": {"Authorization": f"Bearer {data['worker_token']}"},
    }

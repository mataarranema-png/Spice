"""เทสต์การเข้าสู่ระบบและการป้องกันเส้นทางที่ต้องล็อกอิน."""

import server.config as config


def test_health(client):
    body = client.get("/healthz").json()
    assert body["ok"] is True
    assert body["google_login"] is True


def test_protected_routes_require_login(client):
    for path in ("/api/v1/me", "/api/v1/workers", "/api/v1/jobs", "/api/v1/stats"):
        assert client.get(path).status_code == 401, path


def test_landing_redirects_when_logged_in(user_client):
    resp = user_client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/app"


def test_dev_login_creates_owner(user_client):
    me = user_client.get("/api/v1/me").json()
    assert me["email"] == "pilot@spice.local"
    assert me["role"] == "owner"        # ผู้ใช้คนแรกของระบบได้สิทธิ์สูงสุด
    assert me["drive_connected"] is False


def test_logout_clears_session(user_client):
    assert user_client.post("/auth/logout").json()["ok"] is True
    assert user_client.get("/api/v1/me").status_code == 401


def test_google_login_redirects_to_consent(client):
    resp = client.get("/auth/google/login", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "access_type=offline" in location          # ต้องได้ refresh token มาให้ rclone
    assert "drive" in location                        # ขอสิทธิ์ Drive ไปพร้อมกัน


def test_callback_rejects_forged_state(client):
    resp = client.get(
        "/auth/google/callback", params={"code": "x", "state": "forged"}, follow_redirects=False
    )
    assert resp.headers["location"] == "/?error=bad_state"


def test_allowlist_blocks_outsiders():
    settings = config.Settings(
        secret_key="k", google_client_id="", google_client_secret="",
        base_url="http://x", db_path=config.ROOT, dev_login=False,
        allowed_emails=["boss@corp.com"], allowed_domains=["corp.com"],
    )
    assert settings.email_allowed("boss@corp.com")
    assert settings.email_allowed("anyone@corp.com")
    assert not settings.email_allowed("stranger@gmail.com")


def test_empty_allowlist_lets_everyone_in():
    settings = config.Settings(
        secret_key="k", google_client_id="", google_client_secret="",
        base_url="http://x", db_path=config.ROOT, dev_login=False,
    )
    assert settings.email_allowed("anyone@anywhere.com")

"""เส้นทางสำหรับเข้าสู่ระบบ / ออกจากระบบ / ดูข้อมูลบัญชีตัวเอง."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from .. import auth, db
from ..config import get_settings
from ..security import (
    SESSION_COOKIE,
    SESSION_TTL,
    issue_session,
    sign_state,
    verify_state,
)

router = APIRouter(tags=["auth"])


def _set_session_cookie(response: Response, user: dict) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(user["id"], user["email"]),
        max_age=SESSION_TTL,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        path="/",
    )


@router.get("/auth/config")
def auth_config() -> dict:
    """หน้าเว็บใช้ข้อมูลนี้ตัดสินใจว่าจะแสดงปุ่มไหน."""
    settings = get_settings()
    return {
        "google_enabled": settings.google_enabled,
        "dev_login": settings.dev_login,
        "base_url": settings.base_url,
        "restricted": bool(settings.allowed_emails or settings.allowed_domains),
    }


@router.get("/auth/google/login")
def google_login(drive: int = 1, next: str = "/app") -> RedirectResponse:
    settings = get_settings()
    if not settings.google_enabled:
        raise HTTPException(
            503,
            "ยังไม่ได้ตั้งค่า GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET ในไฟล์ .env",
        )
    # state พก 2 อย่าง: ขอสิทธิ์ Drive ไหม และจะเด้งกลับไปหน้าไหน
    safe_next = next if next.startswith("/") else "/app"
    state = sign_state(f"{int(bool(drive))}|{safe_next}")
    return RedirectResponse(auth.build_authorize_url(state, bool(drive)), status_code=302)


@router.get("/auth/google/callback")
async def google_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
) -> RedirectResponse:
    if error:
        return RedirectResponse(f"/?error={error}", status_code=302)
    payload = verify_state(state)
    if payload is None:
        return RedirectResponse("/?error=bad_state", status_code=302)
    if not code:
        return RedirectResponse("/?error=missing_code", status_code=302)

    _, _, next_url = payload.partition("|")
    token_data = await auth.exchange_code(code)
    profile = await auth.fetch_userinfo(token_data.get("access_token", ""))

    email = (profile.get("email") or "").lower()
    if not get_settings().email_allowed(email):
        db.log_audit(None, "login_denied", email)
        return RedirectResponse("/?error=not_allowed", status_code=302)

    user = auth.upsert_user(profile)
    auth.store_google_tokens(user["id"], token_data)

    response = RedirectResponse(next_url or "/app", status_code=302)
    _set_session_cookie(response, user)
    return response


@router.post("/auth/dev")
def dev_login(email: str = "demo@spice.local", name: str = "Demo Pilot") -> Response:
    """ทางลัดสำหรับนักพัฒนา เปิดได้ด้วย SPICE_DEV_LOGIN=1 เท่านั้น."""
    if not get_settings().dev_login:
        raise HTTPException(403, "โหมดเดโมปิดอยู่ (ตั้ง SPICE_DEV_LOGIN=1 เพื่อเปิด)")
    user = auth.upsert_user({"email": email, "name": name, "sub": f"dev:{email}"})
    response = Response(status_code=204)
    _set_session_cookie(response, user)
    return response


@router.post("/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/api/v1/me")
def me(user: dict = Depends(auth.require_user)) -> dict:
    token_row = db.query_one(
        "SELECT scopes, expires_at, refresh_token FROM google_tokens WHERE user_id = ?",
        (user["id"],),
    )
    workers = db.query_one(
        "SELECT COUNT(*) AS n FROM workers WHERE user_id = ? AND status != 'offline'",
        (user["id"],),
    )["n"]
    jobs = db.query_one(
        "SELECT COUNT(*) AS n FROM jobs WHERE user_id = ?", (user["id"],)
    )["n"]
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "picture": user["picture"],
        "role": user["role"],
        "member_since": user["created_at"],
        "drive_connected": bool(token_row and token_row["refresh_token"]),
        "drive_scopes": (token_row["scopes"].split() if token_row else []),
        "drive_token_fresh": bool(token_row and token_row["expires_at"] > time.time()),
        "active_workers": workers,
        "total_jobs": jobs,
    }

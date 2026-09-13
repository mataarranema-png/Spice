"""ล็อกอินด้วยบัญชี Google (OAuth 2.0 Authorization Code) + ตัวช่วยตรวจสิทธิ์."""

from __future__ import annotations

import time
import urllib.parse

import httpx
from fastapi import Depends, HTTPException, Request, status

from . import db
from .config import get_settings
from .security import SESSION_COOKIE, decrypt, encrypt, read_session

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

BASE_SCOPES = ["openid", "email", "profile"]
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


def build_authorize_url(state: str, with_drive: bool) -> str:
    settings = get_settings()
    scopes = list(BASE_SCOPES)
    if with_drive:
        scopes.append(DRIVE_SCOPE)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "access_type": "offline",      # ขอ refresh_token เพื่อให้ rclone ใช้ต่อได้
        "include_granted_scopes": "true",
        "prompt": "consent select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(400, f"แลกโทเคนกับ Google ไม่สำเร็จ: {resp.text[:300]}")
    return resp.json()


async def fetch_userinfo(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
    if resp.status_code != 200:
        raise HTTPException(400, "อ่านข้อมูลผู้ใช้จาก Google ไม่สำเร็จ")
    return resp.json()


async def refresh_access_token(user_id: int) -> str:
    """ต่ออายุ access token ให้เอง เมื่อของเดิมหมดอายุ."""
    row = db.query_one("SELECT * FROM google_tokens WHERE user_id = ?", (user_id,))
    if row is None:
        raise HTTPException(400, "ยังไม่ได้เชื่อมบัญชี Google Drive")

    if row["expires_at"] > time.time() + 60:
        token = decrypt(row["access_token"])
        if token:
            return token

    refresh_token = decrypt(row["refresh_token"])
    if not refresh_token:
        raise HTTPException(400, "ไม่มี refresh token — กรุณาเชื่อม Google Drive อีกครั้ง")

    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(400, f"ต่ออายุโทเคนไม่สำเร็จ: {resp.text[:200]}")

    data = resp.json()
    access_token = data.get("access_token", "")
    expires_at = time.time() + float(data.get("expires_in", 3600))
    db.execute(
        "UPDATE google_tokens SET access_token = ?, expires_at = ?, updated_at = ? WHERE user_id = ?",
        (encrypt(access_token), expires_at, time.time(), user_id),
    )
    return access_token


def upsert_user(profile: dict) -> dict:
    """สร้างหรืออัปเดตผู้ใช้จากโปรไฟล์ Google; คนแรกของระบบได้สิทธิ์ owner."""
    now = time.time()
    email = (profile.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "บัญชี Google นี้ไม่มีอีเมล")

    existing = db.query_one("SELECT * FROM users WHERE email = ?", (email,))
    if existing is None:
        is_first = db.query_one("SELECT COUNT(*) AS n FROM users")["n"] == 0
        cur = db.execute(
            """INSERT INTO users (google_sub, email, name, picture, role, created_at, last_login_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                profile.get("sub", ""),
                email,
                profile.get("name", "") or email.split("@")[0],
                profile.get("picture", ""),
                "owner" if is_first else "member",
                now,
                now,
            ),
        )
        user_id = cur.lastrowid
    else:
        user_id = existing["id"]
        db.execute(
            """UPDATE users SET google_sub = ?, name = ?, picture = ?, last_login_at = ?
               WHERE id = ?""",
            (
                profile.get("sub", existing["google_sub"]),
                profile.get("name", existing["name"]),
                profile.get("picture", existing["picture"]),
                now,
                user_id,
            ),
        )

    db.log_audit(user_id, "login", email)
    return dict(db.query_one("SELECT * FROM users WHERE id = ?", (user_id,)))


def store_google_tokens(user_id: int, token_data: dict) -> None:
    now = time.time()
    existing = db.query_one("SELECT * FROM google_tokens WHERE user_id = ?", (user_id,))
    # Google ส่ง refresh_token มาเฉพาะครั้งแรก — ของเดิมต้องไม่ถูกเขียนทับด้วยค่าว่าง
    refresh = token_data.get("refresh_token", "")
    refresh_enc = encrypt(refresh) if refresh else (existing["refresh_token"] if existing else "")
    payload = (
        refresh_enc,
        encrypt(token_data.get("access_token", "")),
        now + float(token_data.get("expires_in", 3600)),
        token_data.get("scope", ""),
        now,
    )
    if existing is None:
        db.execute(
            """INSERT INTO google_tokens
               (user_id, refresh_token, access_token, expires_at, scopes, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (user_id, *payload),
        )
    else:
        db.execute(
            """UPDATE google_tokens
               SET refresh_token=?, access_token=?, expires_at=?, scopes=?, updated_at=?
               WHERE user_id=?""",
            (*payload, user_id),
        )


def current_user_optional(request: Request) -> dict | None:
    claims = read_session(request.cookies.get(SESSION_COOKIE, ""))
    if not claims:
        return None
    row = db.query_one("SELECT * FROM users WHERE id = ?", (int(claims["sub"]),))
    return dict(row) if row else None


def require_user(request: Request) -> dict:
    user = current_user_optional(request)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "ต้องเข้าสู่ระบบก่อน",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return user


CurrentUser = Depends(require_user)

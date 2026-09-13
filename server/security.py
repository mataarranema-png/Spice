"""เครื่องมือด้านความปลอดภัย: เซสชัน JWT, เข้ารหัสโทเคน, แฮชคีย์ของ worker."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

import jwt
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

SESSION_COOKIE = "spice_session"
SESSION_TTL = 60 * 60 * 24 * 14  # 14 วัน


def _fernet() -> Fernet:
    """คีย์เข้ารหัสได้มาจาก SECRET_KEY จึงไม่ต้องเก็บคีย์เพิ่มอีกชุด."""
    digest = hashlib.sha256(get_settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


def issue_session(user_id: int, email: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + SESSION_TTL,
        "iss": "spice",
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm="HS256")


def read_session(token: str) -> dict | None:
    if not token:
        return None
    try:
        return jwt.decode(
            token, get_settings().secret_key, algorithms=["HS256"], issuer="spice"
        )
    except jwt.PyJWTError:
        return None


def sign_state(payload: str = "") -> str:
    """state ของ OAuth: nonce + ลายเซ็น HMAC + เวลา กันการปลอมและกันหมดอายุ."""
    nonce = secrets.token_urlsafe(16)
    stamp = str(int(time.time()))
    body = f"{nonce}.{stamp}.{payload}"
    sig = hmac.new(get_settings().secret_key.encode(), body.encode(), hashlib.sha256)
    return f"{body}.{sig.hexdigest()[:32]}"


def verify_state(state: str, max_age: int = 900) -> str | None:
    """คืนค่า payload เมื่อ state ถูกต้องและยังไม่หมดอายุ, มิฉะนั้นคืน None."""
    parts = state.split(".")
    if len(parts) != 4:
        return None
    nonce, stamp, payload, sig = parts
    body = f"{nonce}.{stamp}.{payload}"
    expected = hmac.new(
        get_settings().secret_key.encode(), body.encode(), hashlib.sha256
    ).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        if time.time() - int(stamp) > max_age:
            return None
    except ValueError:
        return None
    return payload


def new_worker_token() -> str:
    return "spk_" + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def token_matches(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)


def new_pair_code() -> str:
    """รหัสจับคู่อ่านง่าย 8 ตัว เช่น 'K7QD-2M9X' (ตัดตัวอักษรที่สับสน)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"

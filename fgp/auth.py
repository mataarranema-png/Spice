"""ล็อกอิน / session / สิทธิ์การใช้งาน (stdlib ล้วน)"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets

from . import db

ITERATIONS = 120_000
SESSION_DAYS = 7

ROLE_RANK = {"viewer": 0, "operator": 1, "leader": 2, "manager": 3, "admin": 4}


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = stored.split("$")
        if algo != "pbkdf2":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(calc.hex(), digest)
    except Exception:
        return False


def login(username: str, password: str) -> dict | None:
    user = db.one("SELECT * FROM users WHERE username=? AND active=1", (username.strip(),))
    if not user or not verify_password(password, user["pwd"]):
        return None
    token = secrets.token_urlsafe(32)
    expires = (dt.datetime.now() + dt.timedelta(days=SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO sessions(token,user_id,created_at,expires_at) VALUES(?,?,?,?)",
               (token, user["id"], db.now(), expires))
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (db.now(),))
    log(user["id"], "login", "session")
    return {"token": token, "user": public_user(user)}


def logout(token: str) -> None:
    db.execute("DELETE FROM sessions WHERE token=?", (token,))


def user_from_token(token: str | None) -> dict | None:
    if not token:
        return None
    row = db.one(
        "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token=? AND s.expires_at > ? AND u.active=1", (token, db.now()))
    return row


def public_user(user: dict) -> dict:
    return {"id": user["id"], "username": user["username"], "name": user["name"],
            "role": user["role"], "emp_code": user["emp_code"]}


def can(user: dict | None, minimum: str) -> bool:
    if not user:
        return False
    return ROLE_RANK.get(user["role"], 0) >= ROLE_RANK.get(minimum, 99)


def log(user_id, action: str, target: str = "", detail: str = "") -> None:
    db.execute("INSERT INTO audit(user_id,action,target,detail,created_at) VALUES(?,?,?,?,?)",
               (user_id, action, target, detail, db.now()))

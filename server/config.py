"""การตั้งค่าทั้งหมดของ Spice อ่านจาก environment (.env)."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


def _split(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    secret_key: str
    google_client_id: str
    google_client_secret: str
    base_url: str
    db_path: Path
    dev_login: bool
    allowed_emails: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def redirect_uri(self) -> str:
        return f"{self.base_url.rstrip('/')}/auth/google/callback"

    @property
    def secure_cookies(self) -> bool:
        return self.base_url.startswith("https://")

    def email_allowed(self, email: str) -> bool:
        """ไม่ตั้งค่า allowlist = เปิดให้ทุกคน; ตั้งแล้ว = ต้องผ่านอย่างน้อยหนึ่งเงื่อนไข."""
        if not self.allowed_emails and not self.allowed_domains:
            return True
        email = email.strip().lower()
        if email in self.allowed_emails:
            return True
        domain = email.rpartition("@")[2]
        return bool(domain) and domain in self.allowed_domains


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    secret = os.getenv("SPICE_SECRET_KEY", "").strip()
    if not secret or secret.startswith("change-me"):
        # ใช้คีย์ชั่วคราวเพื่อให้รันได้ทันที (เซสชันจะหลุดเมื่อรีสตาร์ท)
        secret = secrets.token_urlsafe(48)

    db_path = Path(os.getenv("SPICE_DB_PATH", ROOT / "data" / "spice.db")).expanduser()
    if not db_path.is_absolute():
        db_path = (ROOT / db_path).resolve()

    return Settings(
        secret_key=secret,
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        base_url=os.getenv("SPICE_BASE_URL", "http://localhost:8000").strip(),
        db_path=db_path,
        dev_login=_flag("SPICE_DEV_LOGIN"),
        allowed_emails=_split(os.getenv("SPICE_ALLOWED_EMAILS", "")),
        allowed_domains=_split(os.getenv("SPICE_ALLOWED_DOMAINS", "")),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
    )

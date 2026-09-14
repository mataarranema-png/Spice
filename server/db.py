"""ชั้นฐานข้อมูล SQLite ของ Spice (ไฟล์เดียว ไม่ต้องติดตั้งเซิร์ฟเวอร์ DB)."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import get_settings

_local = threading.local()

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    google_sub    TEXT UNIQUE,
    email         TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL DEFAULT '',
    picture       TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT 'member',
    created_at    REAL NOT NULL,
    last_login_at REAL NOT NULL
);

-- โทเคน OAuth ของ Google (เก็บแบบเข้ารหัส) ใช้ต่อยอดกับ Drive และ rclone
CREATE TABLE IF NOT EXISTS google_tokens (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    refresh_token TEXT NOT NULL DEFAULT '',
    access_token  TEXT NOT NULL DEFAULT '',
    expires_at    REAL NOT NULL DEFAULT 0,
    scopes        TEXT NOT NULL DEFAULT '',
    updated_at    REAL NOT NULL
);

-- เครื่องที่ "ยืมการ์ดจอ" มาให้ระบบ (เช่น Colab T4, เครื่องที่บ้าน)
CREATE TABLE IF NOT EXISTS workers (
    id            TEXT PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          TEXT NOT NULL DEFAULT 'worker',
    token_hash    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'offline',
    gpu_name      TEXT NOT NULL DEFAULT '',
    gpu_vram_mb   INTEGER NOT NULL DEFAULT 0,
    gpu_used_mb   INTEGER NOT NULL DEFAULT 0,
    gpu_util      INTEGER NOT NULL DEFAULT 0,
    driver        TEXT NOT NULL DEFAULT '',
    runtime       TEXT NOT NULL DEFAULT '',
    capabilities  TEXT NOT NULL DEFAULT '[]',
    warm_models   TEXT NOT NULL DEFAULT '[]',   -- โมเดลที่ค้างอยู่ใน VRAM พร้อมรันทันที
    drive_mounted INTEGER NOT NULL DEFAULT 0,
    jobs_done     INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    last_seen_at  REAL NOT NULL DEFAULT 0
);

-- รหัสจับคู่แบบใช้ครั้งเดียว สำหรับให้ Colab ล็อกอินเข้าบัญชีเจ้าของ
CREATE TABLE IF NOT EXISTS pair_codes (
    code       TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label      TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    used_at    REAL
);

CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    worker_id   TEXT REFERENCES workers(id) ON DELETE SET NULL,
    kind        TEXT NOT NULL DEFAULT 'generate',
    model       TEXT NOT NULL DEFAULT '',
    title       TEXT NOT NULL DEFAULT '',
    payload     TEXT NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'queued',
    progress    REAL NOT NULL DEFAULT 0,
    result      TEXT NOT NULL DEFAULT '',
    error       TEXT NOT NULL DEFAULT '',
    priority    INTEGER NOT NULL DEFAULT 5,
    parent_id   TEXT,                          -- งานนี้เกิดจากผลลัพธ์ของงานไหน
    chain       TEXT NOT NULL DEFAULT '[]',    -- ขั้นตอนที่เหลือของลูกโซ่
    plan        TEXT NOT NULL DEFAULT '{}',    -- แผนและเหตุผลที่สมองเลือกไว้
    attempt     INTEGER NOT NULL DEFAULT 1,    -- ครั้งที่เท่าไหร่ (ใช้กับการลองใหม่อัตโนมัติ)
    eta_seconds REAL NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL,
    started_at  REAL,
    progress_at REAL,          -- สัญญาณล่าสุดจาก worker ใช้ตัดสินว่างานค้างจริงไหม
    finished_at REAL
);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_queue ON jobs(status, priority, created_at);

CREATE TABLE IF NOT EXISTS job_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id  TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    ts      REAL NOT NULL,
    level   TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_job_events ON job_events(job_id, id);

-- คลังความรู้ (Vector Vault) — เก็บ embedding เป็น blob แล้วค้นด้วย cosine
CREATE TABLE IF NOT EXISTS vault_docs (
    id         TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    collection TEXT NOT NULL DEFAULT 'default',
    title      TEXT NOT NULL DEFAULT '',
    text       TEXT NOT NULL,
    meta       TEXT NOT NULL DEFAULT '{}',
    dim        INTEGER NOT NULL DEFAULT 0,
    embedding  BLOB,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vault ON vault_docs(user_id, collection);

-- โมเดลที่ผู้ใช้ดึงมาเองจาก Hugging Face (นอกเหนือจากแค็ตตาล็อกในตัว)
CREATE TABLE IF NOT EXISTS custom_models (
    id                TEXT PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    repo              TEXT NOT NULL,
    label             TEXT NOT NULL DEFAULT '',
    kind              TEXT NOT NULL DEFAULT 'text',
    quantize          TEXT NOT NULL DEFAULT 'fp16',
    vram_mb           INTEGER NOT NULL DEFAULT 0,
    params_b          REAL NOT NULL DEFAULT 0,
    blurb             TEXT NOT NULL DEFAULT '',
    tags              TEXT NOT NULL DEFAULT '[]',
    gated             INTEGER NOT NULL DEFAULT 0,
    trust_remote_code INTEGER NOT NULL DEFAULT 0,
    downloads         INTEGER NOT NULL DEFAULT 0,
    likes             INTEGER NOT NULL DEFAULT 0,
    added_at          REAL NOT NULL,
    UNIQUE (user_id, repo)
);
CREATE INDEX IF NOT EXISTS idx_custom_models ON custom_models(user_id, added_at DESC);

-- ความลับอื่น ๆ ของผู้ใช้ (เก็บแบบเข้ารหัสทั้งหมด) เช่นโทเคน Hugging Face
CREATE TABLE IF NOT EXISTS user_secrets (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    hf_token   TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    user_id INTEGER,
    action  TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT ''
);
"""


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def get_conn() -> sqlite3.Connection:
    """หนึ่งคอนเนกชันต่อหนึ่งเธรด (SQLite ชอบแบบนี้ที่สุด)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    return conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# คอลัมน์ที่เพิ่มมาทีหลัง — เติมให้ฐานข้อมูลเดิมที่สร้างไว้ก่อนหน้าโดยไม่ต้องลบทิ้ง
MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("workers", "warm_models", "TEXT NOT NULL DEFAULT '[]'"),
    ("jobs", "parent_id", "TEXT"),
    ("jobs", "chain", "TEXT NOT NULL DEFAULT '[]'"),
    ("jobs", "plan", "TEXT NOT NULL DEFAULT '{}'"),
    ("jobs", "attempt", "INTEGER NOT NULL DEFAULT 1"),
    ("jobs", "eta_seconds", "REAL NOT NULL DEFAULT 0"),
    ("jobs", "progress_at", "REAL"),
)


def migrate() -> list[str]:
    """เติมคอลัมน์ที่ขาดให้ฐานข้อมูลเดิม คืนรายชื่อที่เพิ่งเพิ่มไป."""
    conn = get_conn()
    added = []
    for table, column, definition in MIGRATIONS:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue          # ยังไม่มีตารางนี้ — SCHEMA จะสร้างให้เองอยู่แล้ว
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            added.append(f"{table}.{column}")
    conn.commit()
    return added


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    migrate()


def reset_connection() -> None:
    """ใช้ในเทสต์: ปิดคอนเนกชันของเธรดนี้."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return get_conn().execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return get_conn().execute(sql, params).fetchone()


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    with tx() as conn:
        return conn.execute(sql, params)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def log_audit(user_id: int | None, action: str, detail: str = "") -> None:
    execute(
        "INSERT INTO audit_log (ts, user_id, action, detail) VALUES (?,?,?,?)",
        (time.time(), user_id, action, detail),
    )


def loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return fallback

"""
Myfxbook Earning System - ชั้นฐานข้อมูล (SQLite, ใช้เฉพาะไลบรารีมาตรฐานของ Python)

เก็บทุกอย่างไว้ในไฟล์เดียวที่โฟลเดอร์ data/ ของโปรแกรม ไม่ส่งข้อมูลออกไปที่อื่น
รันครั้งแรกจะสร้างฐานข้อมูลพร้อมพอร์ตตัวอย่าง (โหมดสาธิต) ให้ลองใช้ได้ทันที
"""

import math
import os
import random
import sqlite3
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "earning.db")

# สกุลเงินที่ใช้บ่อย พร้อมอัตราเริ่มต้นเทียบ 1 หน่วย -> USD (แก้ได้ในหน้าตั้งค่า)
DEFAULT_RATES = {
    "USD": 1.0,
    "THB": 0.0275,
    "EUR": 1.08,
    "GBP": 1.27,
    "JPY": 0.0064,
    "AUD": 0.66,
    "SGD": 0.74,
}

# ค่าตั้งต้นของระบบ
DEFAULT_SETTINGS = {
    "base_currency": "USD",
    "period_kind": "MONTH",          # รอบคิดส่วนแบ่ง: MONTH หรือ WEEK
    "default_share_pct": "30",       # ส่วนแบ่งกำไรเริ่มต้นของพอร์ตใหม่
    "default_hwm": "1",              # ใช้ High-Water Mark เป็นค่าเริ่มต้น
    "dd_warn_pct": "10",             # เตือนเมื่อ drawdown เกินกี่ %
    "dd_crit_pct": "20",
    "stale_sync_hours": "24",        # เตือนเมื่อไม่ได้ซิงก์เกินกี่ชั่วโมง
    "demo_mode": "1",
    "mfb_email": "",
    "mfb_session": "",
    "mfb_session_at": "",
    "last_sync_at": "",
}

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS accounts (
    id             INTEGER PRIMARY KEY,
    mfb_id         TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    account_no     TEXT NOT NULL DEFAULT '',
    broker         TEXT NOT NULL DEFAULT '',
    platform       TEXT NOT NULL DEFAULT '',
    currency       TEXT NOT NULL DEFAULT 'USD',
    owner          TEXT NOT NULL DEFAULT '',
    balance        REAL NOT NULL DEFAULT 0,
    equity         REAL NOT NULL DEFAULT 0,
    profit         REAL NOT NULL DEFAULT 0,
    gain_pct       REAL NOT NULL DEFAULT 0,
    drawdown_pct   REAL NOT NULL DEFAULT 0,
    deposits       REAL NOT NULL DEFAULT 0,
    withdrawals    REAL NOT NULL DEFAULT 0,
    first_trade_at TEXT NOT NULL DEFAULT '',
    last_update    TEXT NOT NULL DEFAULT '',
    is_demo        INTEGER NOT NULL DEFAULT 0,
    tracked        INTEGER NOT NULL DEFAULT 1,
    source         TEXT NOT NULL DEFAULT 'DEMO',
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily (
    id         INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    day        TEXT NOT NULL,
    balance    REAL NOT NULL DEFAULT 0,
    equity     REAL NOT NULL DEFAULT 0,
    profit     REAL NOT NULL DEFAULT 0,
    pips       REAL NOT NULL DEFAULT 0,
    lots       REAL NOT NULL DEFAULT 0,
    growth_pct REAL NOT NULL DEFAULT 0,
    UNIQUE (account_id, day)
);

CREATE INDEX IF NOT EXISTS idx_daily_day ON daily(day);

CREATE TABLE IF NOT EXISTS rules (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL UNIQUE REFERENCES accounts(id) ON DELETE CASCADE,
    label       TEXT NOT NULL DEFAULT 'ส่วนแบ่งกำไร',
    share_pct   REAL NOT NULL DEFAULT 30,
    use_hwm     INTEGER NOT NULL DEFAULT 1,
    min_profit  REAL NOT NULL DEFAULT 0,
    fixed_fee   REAL NOT NULL DEFAULT 0,
    active      INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accruals (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    period_key  TEXT NOT NULL,
    start_day   TEXT NOT NULL,
    end_day     TEXT NOT NULL,
    gross       REAL NOT NULL DEFAULT 0,
    base        REAL NOT NULL DEFAULT 0,
    hwm_before  REAL NOT NULL DEFAULT 0,
    hwm_after   REAL NOT NULL DEFAULT 0,
    share_pct   REAL NOT NULL DEFAULT 0,
    earning     REAL NOT NULL DEFAULT 0,
    currency    TEXT NOT NULL DEFAULT 'USD',
    computed_at TEXT NOT NULL,
    UNIQUE (account_id, period_key)
);

CREATE TABLE IF NOT EXISTS payouts (
    id         INTEGER PRIMARY KEY,
    account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
    period_key TEXT NOT NULL DEFAULT '',
    amount     REAL NOT NULL,
    currency   TEXT NOT NULL DEFAULT 'USD',
    method     TEXT NOT NULL DEFAULT 'โอนธนาคาร',
    payee      TEXT NOT NULL DEFAULT '',
    note       TEXT NOT NULL DEFAULT '',
    paid_at    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    id         INTEGER PRIMARY KEY,
    period_key TEXT NOT NULL UNIQUE,
    target     REAL NOT NULL,
    note       TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fx_rates (
    code       TEXT PRIMARY KEY,
    to_usd     REAL NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_log (
    id          INTEGER PRIMARY KEY,
    started_at  TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT '',
    ok          INTEGER NOT NULL DEFAULT 0,
    mode        TEXT NOT NULL DEFAULT 'LIVE',
    accounts_n  INTEGER NOT NULL DEFAULT 0,
    days_n      INTEGER NOT NULL DEFAULT 0,
    detail      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS alert_ack (
    key    TEXT PRIMARY KEY,
    actor  TEXT NOT NULL DEFAULT '',
    ts     TEXT NOT NULL
);
"""


def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now_iso():
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def init_db(reset=False):
    os.makedirs(DATA_DIR, exist_ok=True)
    if reset:
        for suffix in ("", "-wal", "-shm"):
            path = DB_PATH + suffix
            if os.path.exists(path):
                os.remove(path)

    fresh = not os.path.exists(DB_PATH)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        stamp = now_iso()
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
        for code, rate in DEFAULT_RATES.items():
            conn.execute(
                "INSERT OR IGNORE INTO fx_rates(code, to_usd, updated_at) VALUES (?, ?, ?)",
                (code, rate, stamp),
            )
        conn.commit()
        if fresh or reset:
            seed_demo(conn)
            conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------- ตัวช่วย settings

def get_settings(conn):
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    data = dict(DEFAULT_SETTINGS)
    data.update({r["key"]: r["value"] for r in rows})
    return data


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, "" if value is None else str(value)),
    )


def get_setting(conn, key, default=""):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return DEFAULT_SETTINGS.get(key, default)
    return row["value"]


# -------------------------------------------------------------------- ข้อมูลสาธิต

DEMO_ACCOUNTS = [
    {
        "mfb_id": "demo-1",
        "name": "Spice Core · Swing",
        "account_no": "510233",
        "broker": "IC Markets",
        "platform": "MT5",
        "currency": "USD",
        "owner": "พอร์ตหลัก",
        "start": 25000.0,
        "drift": 0.0016,
        "vol": 0.011,
        "share": 30.0,
    },
    {
        "mfb_id": "demo-2",
        "name": "Gold Scalper A1",
        "account_no": "774812",
        "broker": "Exness",
        "platform": "MT4",
        "currency": "USD",
        "owner": "ทีมทอง",
        "start": 12000.0,
        "drift": 0.0032,
        "vol": 0.021,
        "share": 40.0,
    },
    {
        "mfb_id": "demo-3",
        "name": "พอร์ตนักลงทุน คุณเอ",
        "account_no": "902155",
        "broker": "FBS",
        "platform": "MT5",
        "currency": "THB",
        "owner": "ลูกค้า",
        "start": 800000.0,
        "drift": 0.0009,
        "vol": 0.008,
        "share": 25.0,
    },
]

DEMO_DAYS = 210


def seed_demo(conn):
    """สร้างพอร์ตตัวอย่างพร้อมเส้นกราฟรายวัน เพื่อให้เปิดโปรแกรมมาแล้วเห็นภาพทันที"""
    if conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone():
        return

    rnd = random.Random(20240117)
    stamp = now_iso()
    today = date.today()

    for spec in DEMO_ACCOUNTS:
        first_day = today - timedelta(days=DEMO_DAYS)
        cur = conn.execute(
            """INSERT INTO accounts
               (mfb_id, name, account_no, broker, platform, currency, owner,
                balance, equity, profit, gain_pct, drawdown_pct, deposits, withdrawals,
                first_trade_at, last_update, is_demo, tracked, source, created_at)
               VALUES (?,?,?,?,?,?,?,0,0,0,0,0,?,0,?,?,1,1,'DEMO',?)""",
            (
                spec["mfb_id"], spec["name"], spec["account_no"], spec["broker"],
                spec["platform"], spec["currency"], spec["owner"],
                spec["start"], first_day.isoformat(), stamp, stamp,
            ),
        )
        account_id = cur.lastrowid
        conn.execute(
            """INSERT INTO rules (account_id, label, share_pct, use_hwm, min_profit, fixed_fee, active, updated_at)
               VALUES (?,?,?,1,0,0,1,?)""",
            (account_id, "ส่วนแบ่งกำไร", spec["share"], stamp),
        )

        balance = spec["start"]
        peak = balance
        max_dd = 0.0
        rows = []
        for offset in range(DEMO_DAYS + 1):
            day = first_day + timedelta(days=offset)
            if day.weekday() >= 5:      # ตลาดปิดเสาร์อาทิตย์
                continue
            shock = rnd.gauss(spec["drift"], spec["vol"])
            # เพิ่มช่วงย่อตัวให้กราฟดูสมจริง ไม่ใช่ขึ้นอย่างเดียว
            if rnd.random() < 0.07:
                shock -= abs(rnd.gauss(0, spec["vol"] * 2.4))
            profit = round(balance * shock, 2)
            balance = round(balance + profit, 2)
            peak = max(peak, balance)
            max_dd = max(max_dd, (peak - balance) / peak * 100 if peak else 0)
            pips = round(profit / max(balance, 1) * 8000, 1)
            rows.append((
                account_id, day.isoformat(), balance, balance, profit, pips,
                round(abs(rnd.gauss(1.2, 0.5)), 2),
                round(profit / max(balance - profit, 1) * 100, 4),
            ))

        conn.executemany(
            """INSERT OR REPLACE INTO daily
               (account_id, day, balance, equity, profit, pips, lots, growth_pct)
               VALUES (?,?,?,?,?,?,?,?)""",
            rows,
        )
        total_profit = round(balance - spec["start"], 2)
        conn.execute(
            """UPDATE accounts SET balance=?, equity=?, profit=?, gain_pct=?, drawdown_pct=?,
                                   last_update=? WHERE id=?""",
            (
                balance, balance, total_profit,
                round(total_profit / spec["start"] * 100, 2),
                round(max_dd, 2), stamp, account_id,
            ),
        )

    # เป้าหมายรายได้ของเดือนนี้และเดือนที่แล้ว ให้เห็นหน้าเป้าหมายมีข้อมูล
    this_month = today.strftime("%Y-%m")
    prev_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    for key, target in ((prev_month, 400.0), (this_month, 500.0)):
        conn.execute(
            "INSERT OR IGNORE INTO goals(period_key, target, note, updated_at) VALUES (?,?,?,?)",
            (key, target, "เป้าหมายรายได้ส่วนแบ่ง (USD)", stamp),
        )

    conn.execute(
        """INSERT INTO sync_log (started_at, finished_at, ok, mode, accounts_n, days_n, detail)
           VALUES (?,?,1,'DEMO',?,?,?)""",
        (stamp, stamp, len(DEMO_ACCOUNTS),
         conn.execute("SELECT COUNT(*) c FROM daily").fetchone()["c"],
         "สร้างข้อมูลสาธิตครั้งแรก"),
    )


def fx_map(conn):
    rows = conn.execute("SELECT code, to_usd FROM fx_rates").fetchall()
    data = dict(DEFAULT_RATES)
    data.update({r["code"]: float(r["to_usd"]) for r in rows})
    return data


def to_base(amount, currency, rates, base_currency):
    """แปลงจำนวนเงินจากสกุลของพอร์ตไปเป็นสกุลกลางที่ผู้ใช้เลือก"""
    if amount is None:
        return 0.0
    src = rates.get((currency or "USD").upper())
    dst = rates.get((base_currency or "USD").upper())
    if not src or not dst:
        return float(amount)
    usd = float(amount) * src
    value = usd / dst
    return 0.0 if math.isnan(value) or math.isinf(value) else round(value, 2)

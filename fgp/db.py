"""ฐานข้อมูล SQLite สำหรับระบบ FGP Production (ไม่พึ่ง library ภายนอก)"""

from __future__ import annotations

import datetime as dt
import os
import random
import sqlite3
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "fgp.db")

_local = threading.local()
_init_lock = threading.Lock()

SHIFTS = ("A", "B")
SHIFT_HOURS = 8

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    pwd TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'operator',
    emp_code TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    section TEXT NOT NULL DEFAULT 'FGP',
    std_manpower INTEGER NOT NULL DEFAULT 8,
    std_cycle_sec REAL NOT NULL DEFAULT 30,
    leader_id INTEGER REFERENCES users(id),
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    family TEXT NOT NULL DEFAULT 'FGP',
    cycle_sec REAL NOT NULL DEFAULT 30,
    std_manpower INTEGER NOT NULL DEFAULT 8,
    target_yield REAL NOT NULL DEFAULT 99.0,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emp_code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    section TEXT NOT NULL DEFAULT 'FGP',
    position TEXT NOT NULL DEFAULT 'Operator',
    shift TEXT NOT NULL DEFAULT 'A',
    active INTEGER NOT NULL DEFAULT 1,
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    line_id INTEGER NOT NULL REFERENCES lines(id) ON DELETE CASCADE,
    level INTEGER NOT NULL DEFAULT 1,
    UNIQUE(employee_id, line_id)
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_date TEXT NOT NULL,
    shift TEXT NOT NULL,
    line_id INTEGER NOT NULL REFERENCES lines(id) ON DELETE CASCADE,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    target_qty INTEGER NOT NULL,
    priority INTEGER NOT NULL DEFAULT 2,
    status TEXT NOT NULL DEFAULT 'open',
    note TEXT DEFAULT '',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plans_date ON plans(plan_date, shift);

CREATE TABLE IF NOT EXISTS production (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rec_date TEXT NOT NULL,
    shift TEXT NOT NULL,
    hour INTEGER NOT NULL,
    line_id INTEGER NOT NULL REFERENCES lines(id) ON DELETE CASCADE,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    ok_qty INTEGER NOT NULL DEFAULT 0,
    ng_qty INTEGER NOT NULL DEFAULT 0,
    downtime_min INTEGER NOT NULL DEFAULT 0,
    downtime_reason TEXT DEFAULT '',
    manpower INTEGER NOT NULL DEFAULT 0,
    recorded_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    UNIQUE(rec_date, shift, hour, line_id)
);
CREATE INDEX IF NOT EXISTS idx_prod_date ON production(rec_date, shift);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_date TEXT NOT NULL,
    shift TEXT NOT NULL,
    line_id INTEGER NOT NULL REFERENCES lines(id) ON DELETE CASCADE,
    required_qty INTEGER NOT NULL DEFAULT 1,
    skill_min INTEGER NOT NULL DEFAULT 1,
    reason TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    requested_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_book_date ON bookings(book_date, shift);

CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    score REAL NOT NULL DEFAULT 0,
    method TEXT NOT NULL DEFAULT 'auto',
    created_at TEXT NOT NULL,
    UNIQUE(booking_id, employee_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    detail TEXT DEFAULT '',
    line_id INTEGER REFERENCES lines(id) ON DELETE SET NULL,
    assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    priority INTEGER NOT NULL DEFAULT 2,
    status TEXT NOT NULL DEFAULT 'open',
    due_date TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    done_at TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    detail TEXT DEFAULT '',
    line_id INTEGER REFERENCES lines(id) ON DELETE SET NULL,
    ref_date TEXT,
    created_at TEXT NOT NULL,
    ack_by INTEGER REFERENCES users(id),
    ack_at TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    target TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return dt.date.today().isoformat()


def connect() -> sqlite3.Connection:
    """คืน connection ประจำ thread (ThreadingHTTPServer เรียกหลาย thread)"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=8000")
        _local.conn = conn
    return conn


def query(sql: str, args=()) -> list[dict]:
    cur = connect().execute(sql, args)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows


def one(sql: str, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql: str, args=()) -> int:
    conn = connect()
    cur = conn.execute(sql, args)
    conn.commit()
    rid = cur.lastrowid
    cur.close()
    return rid


def executemany(sql: str, seq) -> None:
    conn = connect()
    conn.executemany(sql, seq)
    conn.commit()


def init_db(seed: bool = True) -> None:
    with _init_lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = connect()
        conn.executescript(SCHEMA)
        conn.commit()
        if seed and not one("SELECT id FROM users LIMIT 1"):
            _seed()


# ---------------------------------------------------------------- seed data

LINE_SEED = [
    ("FGP-01", "FGP Assembly Line 1", 10, 26.0),
    ("FGP-02", "FGP Assembly Line 2", 10, 28.0),
    ("FGP-03", "FGP Sub Assembly", 8, 34.0),
    ("FGP-04", "FGP Final Inspection", 6, 22.0),
    ("FGP-05", "FGP Packing", 6, 18.0),
]

MODEL_SEED = [
    ("FG-A100", "Fan Motor A100", 26.0, 10, 99.2),
    ("FG-A200", "Fan Motor A200", 29.0, 10, 99.0),
    ("FG-B310", "Blower Unit B310", 34.0, 8, 98.6),
    ("FG-C450", "Compressor Kit C450", 41.0, 8, 98.2),
    ("FG-D120", "Duct Set D120", 19.0, 6, 99.4),
]

FIRST = ["สมชาย", "สมหญิง", "วิชัย", "ปรีชา", "อรทัย", "นภา", "ธนกร", "กิตติ", "พรทิพย์",
         "สุชาติ", "มานพ", "ศิริพร", "อนุชา", "ยุพิน", "ณัฐพล", "จิราพร", "เอกชัย", "บุญมี",
         "รัตนา", "วีระ", "สายฝน", "ประเสริฐ", "มาลี", "ธีระ", "กนกวรรณ", "ชูชาติ", "พิมพ์ใจ",
         "สุริยา", "อำนาจ", "เพ็ญศรี"]
LAST = ["ใจดี", "ทองคำ", "แสงทอง", "บุญเรือง", "ศรีสุข", "พงษ์ไพร", "วงศ์คำ", "มั่นคง",
        "เจริญสุข", "รักไทย", "สินธุ์ทอง", "ก้าวหน้า", "ดวงแก้ว", "พูลผล", "ยิ่งยง"]

DOWNTIME_REASONS = ["เครื่องจักรขัดข้อง", "รอวัตถุดิบ", "เปลี่ยนรุ่น (Change over)",
                    "ปรับตั้งเครื่อง", "ไฟฟ้าขัดข้อง", "ขาดกำลังคน", "QC hold"]


def _seed() -> None:
    from .auth import hash_password

    ts = now()
    rnd = random.Random(20250817)

    users = [
        ("admin", "ผู้ดูแลระบบ FGP", "Admin@123", "admin", "FGP-000"),
        ("manager", "หัวหน้าแผนก FGP", "Manager@123", "manager", "FGP-001"),
        ("leader1", "หัวหน้าไลน์ 1", "Leader@123", "leader", "FGP-101"),
        ("leader2", "หัวหน้าไลน์ 2", "Leader@123", "leader", "FGP-102"),
        ("operator", "พนักงานบันทึกยอด", "Operator@123", "operator", "FGP-201"),
    ]
    for username, name, pwd, role, code in users:
        execute(
            "INSERT INTO users(username,name,pwd,role,emp_code,created_at) VALUES(?,?,?,?,?,?)",
            (username, name, hash_password(pwd), role, code, ts),
        )

    for code, name, mp, cycle in LINE_SEED:
        execute(
            "INSERT INTO lines(code,name,section,std_manpower,std_cycle_sec) VALUES(?,?,?,?,?)",
            (code, name, "FGP", mp, cycle),
        )

    for code, name, cycle, mp, ty in MODEL_SEED:
        execute(
            "INSERT INTO models(code,name,family,cycle_sec,std_manpower,target_yield) "
            "VALUES(?,?,?,?,?,?)",
            (code, name, "FGP", cycle, mp, ty),
        )

    line_ids = [r["id"] for r in query("SELECT id FROM lines ORDER BY id")]
    model_ids = [r["id"] for r in query("SELECT id FROM models ORDER BY id")]

    # พนักงาน 64 คน + skill matrix
    used = set()
    emp_rows = []
    for i in range(1, 65):
        while True:
            nm = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
            if nm not in used:
                used.add(nm)
                break
        shift = "A" if i % 3 else "B"
        pos = "Leader" if i % 16 == 0 else ("Senior Operator" if i % 5 == 0 else "Operator")
        emp_rows.append((f"FGP-{2000 + i}", nm, "FGP", pos, shift, 1, ""))
    executemany(
        "INSERT INTO employees(emp_code,name,section,position,shift,active,note) "
        "VALUES(?,?,?,?,?,?,?)", emp_rows)

    emp_ids = [r["id"] for r in query("SELECT id FROM employees ORDER BY id")]
    skill_rows = []
    for eid in emp_ids:
        for lid in rnd.sample(line_ids, rnd.choice([2, 2, 3, 3, 4])):
            skill_rows.append((eid, lid, rnd.choice([1, 2, 2, 3, 3, 4])))
    executemany("INSERT OR IGNORE INTO skills(employee_id,line_id,level) VALUES(?,?,?)", skill_rows)

    # แผน + ยอดผลิตย้อนหลัง 30 วัน
    start = dt.date.today() - dt.timedelta(days=29)
    plan_rows, prod_rows = [], []
    for d in range(30):
        day = start + dt.timedelta(days=d)
        if day.weekday() == 6:
            continue
        ds = day.isoformat()
        for shift in SHIFTS:
            for idx, lid in enumerate(line_ids):
                mid = model_ids[(d + idx) % len(model_ids)]
                cycle = MODEL_SEED[(d + idx) % len(MODEL_SEED)][2]
                target = int(round(SHIFT_HOURS * 3600 / cycle * rnd.uniform(0.86, 0.97) / 10) * 10)
                plan_rows.append((ds, shift, lid, mid, target, 2, "closed" if day < dt.date.today() else "open", "", 2, ts))
                base = target / SHIFT_HOURS
                hours = SHIFT_HOURS if day < dt.date.today() else max(1, min(SHIFT_HOURS, dt.datetime.now().hour - 7))
                if day == dt.date.today() and shift == "B":
                    hours = 0
                for h in range(1, hours + 1):
                    perf = rnd.gauss(0.97, 0.09)
                    perf = max(0.55, min(1.12, perf))
                    ok = int(base * perf)
                    ng_rate = abs(rnd.gauss(0.011, 0.008))
                    if rnd.random() < 0.05:
                        ng_rate *= rnd.uniform(3, 6)
                    ng = int(ok * ng_rate)
                    dtm = 0
                    reason = ""
                    if rnd.random() < 0.18:
                        dtm = rnd.choice([5, 8, 12, 15, 20, 25, 35])
                        reason = rnd.choice(DOWNTIME_REASONS)
                    prod_rows.append((ds, shift, h, lid, mid, ok, ng, dtm, reason,
                                      LINE_SEED[idx][2] - rnd.choice([0, 0, 1]), 5, ts))
    executemany(
        "INSERT INTO plans(plan_date,shift,line_id,model_id,target_qty,priority,status,note,created_by,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)", plan_rows)
    executemany(
        "INSERT OR IGNORE INTO production(rec_date,shift,hour,line_id,model_id,ok_qty,ng_qty,"
        "downtime_min,downtime_reason,manpower,recorded_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        prod_rows)

    # แผนล่วงหน้า 7 วัน
    fut_rows = []
    for d in range(1, 8):
        day = dt.date.today() + dt.timedelta(days=d)
        if day.weekday() == 6:
            continue
        for shift in SHIFTS:
            for idx, lid in enumerate(line_ids):
                mid = model_ids[(d + idx) % len(model_ids)]
                cycle = MODEL_SEED[(d + idx) % len(MODEL_SEED)][2]
                target = int(round(SHIFT_HOURS * 3600 / cycle * rnd.uniform(0.88, 1.05) / 10) * 10)
                fut_rows.append((day.isoformat(), shift, lid, mid, target,
                                 rnd.choice([1, 2, 2, 3]), "open", "", 2, ts))
    executemany(
        "INSERT INTO plans(plan_date,shift,line_id,model_id,target_qty,priority,status,note,created_by,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)", fut_rows)

    # คิวจองคนล่วงหน้า
    for d in range(0, 4):
        day = (dt.date.today() + dt.timedelta(days=d)).isoformat()
        for lid in rnd.sample(line_ids, 3):
            execute(
                "INSERT INTO bookings(book_date,shift,line_id,required_qty,skill_min,reason,status,"
                "requested_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (day, rnd.choice(SHIFTS), lid, rnd.choice([2, 3, 4, 5]), rnd.choice([1, 2, 3]),
                 rnd.choice(["เพิ่มกำลังผลิตเร่งด่วน", "ทดแทนคนลา", "รองรับรุ่นใหม่", "OT เสริมไลน์"]),
                 "pending", 3, ts))

    # งานที่กระจายให้ leader
    task_seed = [
        ("ตรวจเช็ค jig ไลน์ 1 ก่อนเริ่มกะ", "รอบเช้าก่อน 07:45", 1, 3, 1),
        ("สรุปสาเหตุ NG รุ่น FG-B310", "ทำ 5 Why ส่งภายในวันนี้", 3, 3, 1),
        ("อบรม OJT พนักงานใหม่ 3 คน", "ไลน์ Packing", 5, 4, 2),
        ("เตรียม change over รุ่น FG-C450", "กะ B", 2, 3, 2),
        ("เช็คสต็อกอะไหล่สำรอง", "ร่วมกับฝ่ายซ่อมบำรุง", 4, 4, 3),
    ]
    for title, detail, lid_idx, assignee, pri in task_seed:
        execute(
            "INSERT INTO tasks(title,detail,line_id,assignee_id,priority,status,due_date,created_by,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (title, detail, line_ids[lid_idx - 1], assignee, pri, "open", today(), 2, ts))

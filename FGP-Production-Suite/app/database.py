"""
FGP Production Suite - ชั้นฐานข้อมูล (SQLite, ใช้เฉพาะไลบรารีมาตรฐานของ Python)
สร้างไฟล์ฐานข้อมูลและใส่ข้อมูลตัวอย่างให้อัตโนมัติในการรันครั้งแรก
"""

import os
import random
import sqlite3
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "fgp.db")

STAGES = [
    "รับงาน",
    "เตรียมตัวอย่าง",
    "ทดสอบ Chamber",
    "วัด/วิเคราะห์",
    "สรุปผล",
    "ปิดงาน",
]

# ชั่วโมงมาตรฐานที่ใช้ในแต่ละขั้นตอน (ใช้คำนวณวันคาดเสร็จ)
STAGE_HOURS = {
    "รับงาน": 4,
    "เตรียมตัวอย่าง": 8,
    "ทดสอบ Chamber": 24,
    "วัด/วิเคราะห์": 12,
    "สรุปผล": 6,
    "ปิดงาน": 2,
}

MACHINE_TYPES = {
    "CHAMBER": "Chamber",
    "XRF": "XRF",
    "MEASURE": "เครื่องมือวัด",
    "TESTER": "เครื่องทดสอบ",
}

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS models (
    id       INTEGER PRIMARY KEY,
    code     TEXT NOT NULL UNIQUE,
    name     TEXT NOT NULL,
    line     TEXT NOT NULL,
    cycle_s  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    team      TEXT NOT NULL,
    role      TEXT NOT NULL,
    skill     TEXT NOT NULL,
    hours_cap REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id         INTEGER PRIMARY KEY,
    plan_date  TEXT NOT NULL,
    model_id   INTEGER NOT NULL REFERENCES models(id),
    shift      TEXT NOT NULL,
    plan_qty   INTEGER NOT NULL,
    actual_qty INTEGER,
    note       TEXT DEFAULT '',
    UNIQUE (plan_date, model_id, shift)
);

CREATE TABLE IF NOT EXISTS machines (
    id        INTEGER PRIMARY KEY,
    code      TEXT NOT NULL UNIQUE,
    name      TEXT NOT NULL,
    mtype     TEXT NOT NULL,
    location  TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'READY',
    open_hour INTEGER NOT NULL DEFAULT 8,
    close_hour INTEGER NOT NULL DEFAULT 20
);

CREATE TABLE IF NOT EXISTS bookings (
    id         INTEGER PRIMARY KEY,
    machine_id INTEGER NOT NULL REFERENCES machines(id),
    job_no     TEXT NOT NULL DEFAULT '',
    owner      TEXT NOT NULL,
    team       TEXT NOT NULL DEFAULT '',
    purpose    TEXT NOT NULL DEFAULT '',
    book_date  TEXT NOT NULL,
    start_hour REAL NOT NULL,
    end_hour   REAL NOT NULL,
    status     TEXT NOT NULL DEFAULT 'BOOKED',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY,
    job_no      TEXT NOT NULL UNIQUE,
    model_id    INTEGER NOT NULL REFERENCES models(id),
    qty         INTEGER NOT NULL,
    stage       TEXT NOT NULL,
    owner_id    INTEGER REFERENCES members(id),
    priority    TEXT NOT NULL DEFAULT 'NORMAL',
    status      TEXT NOT NULL DEFAULT 'OPEN',
    customer    TEXT NOT NULL DEFAULT '',
    started_at  TEXT NOT NULL,
    stage_at    TEXT NOT NULL,
    due_date    TEXT NOT NULL,
    closed_at   TEXT
);

CREATE TABLE IF NOT EXISTS job_events (
    id      INTEGER PRIMARY KEY,
    job_id  INTEGER NOT NULL REFERENCES jobs(id),
    kind    TEXT NOT NULL,
    detail  TEXT NOT NULL,
    actor   TEXT NOT NULL DEFAULT 'ระบบ',
    ts      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kpi_daily (
    kpi_date     TEXT PRIMARY KEY,
    output_qty   INTEGER NOT NULL,
    target_qty   INTEGER NOT NULL,
    ot_hours     REAL NOT NULL,
    manpower     INTEGER NOT NULL,
    run_min      INTEGER NOT NULL,
    plan_min     INTEGER NOT NULL,
    good_qty     INTEGER NOT NULL,
    total_qty    INTEGER NOT NULL,
    perf_rate    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_ack (
    alert_key TEXT NOT NULL,
    ack_date  TEXT NOT NULL,
    actor     TEXT NOT NULL DEFAULT 'ผู้ใช้',
    ts        TEXT NOT NULL,
    PRIMARY KEY (alert_key, ack_date)
);
"""


def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def iso(d):
    return d.strftime("%Y-%m-%d")


def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- seeding

MODELS = [
    ("FG-A100", "Panel Assembly A100", "Line 1", 42.0),
    ("FG-B220", "Panel Assembly B220", "Line 1", 55.0),
    ("FG-C310", "Housing Module C310", "Line 2", 38.0),
    ("FG-D440", "Sensor Pack D440", "Line 2", 61.0),
    ("FG-E550", "Control Unit E550", "Line 3", 74.0),
]

MEMBERS = [
    ("สมชาย ภักดี", "Team A", "Leader", "Chamber", 8),
    ("ณัฐพล วงศ์ดี", "Team A", "Operator", "Chamber", 8),
    ("กมลชนก ศรีสุข", "Team A", "Operator", "XRF", 8),
    ("ธนกร ใจงาม", "Team A", "Technician", "เครื่องมือวัด", 8),
    ("ปิยะดา แก้วมณี", "Team B", "Leader", "เครื่องมือวัด", 8),
    ("อนุชา พงษ์ทอง", "Team B", "Operator", "Chamber", 8),
    ("ศิริพร ทองดี", "Team B", "Operator", "เครื่องมือวัด", 8),
    ("วีระ สมบูรณ์", "Team B", "Technician", "เครื่องทดสอบ", 8),
    ("จิราพร ชัยมงคล", "Team C", "Leader", "XRF", 8),
    ("ภาณุพงศ์ รักไทย", "Team C", "Operator", "XRF", 8),
    ("อรทัย บุญมี", "Team C", "Operator", "เครื่องทดสอบ", 8),
    ("ทศพล เจริญสุข", "Team C", "Technician", "Chamber", 8),
]

MACHINES = [
    ("CH-01", "Temp & Humidity Chamber 1", "CHAMBER", "Lab A", 8, 20),
    ("CH-02", "Temp & Humidity Chamber 2", "CHAMBER", "Lab A", 8, 20),
    ("CH-03", "Thermal Shock Chamber", "CHAMBER", "Lab A", 8, 20),
    ("CH-04", "Salt Spray Chamber", "CHAMBER", "Lab B", 8, 18),
    ("XRF-01", "XRF Analyzer 1", "XRF", "Lab B", 8, 18),
    ("XRF-02", "XRF Analyzer 2", "XRF", "Lab B", 8, 18),
    ("CMM-01", "CMM 3D Measuring", "MEASURE", "Metrology", 8, 18),
    ("PRJ-01", "Profile Projector", "MEASURE", "Metrology", 8, 18),
    ("MIC-01", "Digital Microscope", "MEASURE", "Metrology", 8, 18),
    ("VIB-01", "Vibration Tester", "TESTER", "Lab C", 8, 18),
    ("TS-01", "Tensile Strength Tester", "TESTER", "Lab C", 8, 18),
]

CUSTOMERS = ["PANA-TH", "PANA-JP", "AEC Group", "Nichi Motor", "Siam Denki"]


def seeded(conn):
    row = conn.execute("SELECT COUNT(*) AS c FROM models").fetchone()
    return row["c"] > 0


def seed(conn):
    """ใส่ข้อมูลตัวอย่างที่อ้างอิงกับ 'วันนี้' เสมอ ข้อมูลจึงดูสดใหม่ทุกครั้งที่ติดตั้ง"""
    rng = random.Random(20260817)
    today = date.today()
    cur = conn.cursor()

    cur.executemany(
        "INSERT INTO models (code, name, line, cycle_s) VALUES (?,?,?,?)", MODELS
    )
    cur.executemany(
        "INSERT INTO members (name, team, role, skill, hours_cap) VALUES (?,?,?,?,?)",
        MEMBERS,
    )
    cur.executemany(
        "INSERT INTO machines (code, name, mtype, location, open_hour, close_hour)"
        " VALUES (?,?,?,?,?,?)",
        MACHINES,
    )
    conn.commit()

    model_ids = [r["id"] for r in cur.execute("SELECT id FROM models ORDER BY id")]
    member_rows = cur.execute("SELECT * FROM members ORDER BY id").fetchall()

    # ---- แผนผลิต: ย้อนหลัง 21 วัน ถึงล่วงหน้า 7 วัน
    base_plan = {0: 1000, 1: 500, 2: 720, 3: 380, 4: 260}
    plans = []
    for offset in range(-21, 8):
        d = today + timedelta(days=offset)
        if d.weekday() == 6:  # อาทิตย์หยุด
            continue
        for idx, mid in enumerate(model_ids):
            for shift in ("กะเช้า", "กะดึก"):
                base = base_plan[idx]
                qty = int(base * (0.55 if shift == "กะดึก" else 1.0))
                qty = int(qty * rng.uniform(0.9, 1.12))
                actual = None
                if offset < 0:
                    ratio = rng.uniform(0.86, 1.06)
                    if rng.random() < 0.12:
                        ratio = rng.uniform(0.62, 0.8)  # วันที่มีปัญหา
                    actual = int(qty * ratio)
                elif offset == 0 and shift == "กะเช้า":
                    actual = int(qty * rng.uniform(0.72, 0.94))  # กะเช้ายังเดินอยู่
                plans.append((iso(d), mid, shift, qty, actual, ""))
    cur.executemany(
        "INSERT INTO plans (plan_date, model_id, shift, plan_qty, actual_qty, note)"
        " VALUES (?,?,?,?,?,?)",
        plans,
    )

    # ---- KPI รายวัน ย้อนหลัง 21 วัน
    kpis = []
    for offset in range(-20, 1):
        d = today + timedelta(days=offset)
        if d.weekday() == 6:
            continue
        target = 2600 + rng.randint(-120, 120)
        factor = rng.uniform(0.88, 1.04)
        if offset == 0:
            factor = 0.66  # ยังไม่จบวัน
        output = int(target * factor)
        total = output + rng.randint(20, 70)
        good = int(total * rng.uniform(0.965, 0.995))
        plan_min = 600
        run_min = int(plan_min * rng.uniform(0.82, 0.95))
        kpis.append(
            (
                iso(d),
                output,
                target,
                round(rng.uniform(4, 26), 1),
                rng.randint(28, 36),
                run_min,
                plan_min,
                good,
                total,
                round(rng.uniform(0.9, 1.0), 3),
            )
        )
    cur.executemany(
        "INSERT INTO kpi_daily (kpi_date, output_qty, target_qty, ot_hours, manpower,"
        " run_min, plan_min, good_qty, total_qty, perf_rate)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        kpis,
    )

    # ---- งาน WIP
    purposes = [
        "Temp Cycle 85C/85RH",
        "Thermal Shock 100 cycles",
        "RoHS Screening",
        "Dimension Check",
        "Salt Spray 48h",
        "Vibration Sweep",
        "Tensile Test",
    ]
    jobs = []
    for i in range(26):
        started = today - timedelta(days=rng.randint(0, 11))
        stage_idx = rng.randint(0, 4)
        # งานที่เริ่มมานานมีโอกาสอยู่ขั้นท้าย ๆ มากกว่า
        age = (today - started).days
        stage_idx = min(4, max(0, int(age / 2.2) + rng.randint(-1, 1)))
        stage = STAGES[stage_idx]
        stage_at = today - timedelta(days=rng.randint(0, max(0, min(age, 5))))
        due = started + timedelta(days=rng.randint(7, 16))
        priority = "URGENT" if rng.random() < 0.22 else "NORMAL"
        owner = rng.choice(member_rows)["id"]
        jobs.append(
            (
                "FGP-%s-%03d" % (today.strftime("%y%m"), 101 + i),
                rng.choice(model_ids),
                rng.choice([20, 30, 50, 80, 100, 120]),
                stage,
                owner,
                priority,
                "OPEN",
                rng.choice(CUSTOMERS),
                iso(started),
                iso(stage_at),
                iso(due),
                None,
            )
        )
    # งานที่ปิดแล้วในสัปดาห์นี้ (ไว้ให้กราฟรอบเวลาเสร็จมีข้อมูล)
    for i in range(8):
        started = today - timedelta(days=rng.randint(8, 18))
        closed = started + timedelta(days=rng.randint(4, 9))
        jobs.append(
            (
                "FGP-%s-%03d" % (today.strftime("%y%m"), 201 + i),
                rng.choice(model_ids),
                rng.choice([30, 50, 80]),
                "ปิดงาน",
                rng.choice(member_rows)["id"],
                "NORMAL",
                "CLOSED",
                rng.choice(CUSTOMERS),
                iso(started),
                iso(closed),
                iso(closed + timedelta(days=1)),
                iso(closed),
            )
        )
    cur.executemany(
        "INSERT INTO jobs (job_no, model_id, qty, stage, owner_id, priority, status,"
        " customer, started_at, stage_at, due_date, closed_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        jobs,
    )

    for row in cur.execute("SELECT id, job_no, started_at FROM jobs").fetchall():
        cur.execute(
            "INSERT INTO job_events (job_id, kind, detail, actor, ts) VALUES (?,?,?,?,?)",
            (row["id"], "CREATE", "เปิดงาน %s" % row["job_no"], "ระบบ", row["started_at"] + " 08:00:00"),
        )

    # ---- การจองเครื่อง วันนี้ ถึง อีก 6 วัน
    machine_rows = cur.execute("SELECT * FROM machines ORDER BY id").fetchall()
    job_rows = cur.execute("SELECT job_no FROM jobs WHERE status='OPEN'").fetchall()
    bookings = []
    for offset in range(0, 7):
        d = today + timedelta(days=offset)
        if d.weekday() == 6:
            continue
        for m in machine_rows:
            # Chamber ถูกจองหนักกว่าเครื่องอื่นโดยตั้งใจ เพื่อให้เห็น Alert จริง
            load = 0.85 if m["mtype"] == "CHAMBER" else 0.38
            load *= 1.0 if offset < 2 else rng.uniform(0.4, 0.9)
            hour = m["open_hour"]
            while hour < m["close_hour"]:
                block = rng.choice([2, 2, 3, 4])
                if hour + block > m["close_hour"]:
                    break
                if rng.random() < load:
                    person = rng.choice(member_rows)
                    bookings.append(
                        (
                            m["id"],
                            rng.choice(job_rows)["job_no"] if job_rows else "",
                            person["name"],
                            person["team"],
                            rng.choice(purposes),
                            iso(d),
                            float(hour),
                            float(hour + block),
                            "BOOKED",
                            now_iso(),
                        )
                    )
                hour += block
    cur.executemany(
        "INSERT INTO bookings (machine_id, job_no, owner, team, purpose, book_date,"
        " start_hour, end_hour, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        bookings,
    )

    # เครื่องหนึ่งตัวเสีย เพื่อให้หน้าจอมีสถานะจริงครบ
    cur.execute("UPDATE machines SET status='MAINT' WHERE code='PRJ-01'")
    conn.commit()


def init_db(reset=False):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    if not seeded(conn):
        seed(conn)
    conn.close()
    return DB_PATH

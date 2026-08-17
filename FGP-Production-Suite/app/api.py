"""
FGP Production Suite - ตรรกะทางธุรกิจทั้งหมด
ทุกฟังก์ชันคืนค่าเป็น dict/list ธรรมดา เพื่อให้ server.py แปลงเป็น JSON ได้ตรง ๆ
"""

import math
from datetime import date, datetime, timedelta

from .database import (
    MACHINE_TYPES,
    STAGE_HOURS,
    STAGES,
    connect,
    iso,
    now_iso,
)

WORK_HOURS_PER_DAY = 8.0


def today():
    return date.today()


def parse_date(text, fallback=None):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback if fallback is not None else today()


def pct(part, whole):
    if not whole:
        return 0.0
    return round(part * 100.0 / whole, 1)


# ---------------------------------------------------------------- แผนผลิต


def plan_board(from_date=None, to_date=None):
    d_from = parse_date(from_date, today() - timedelta(days=6))
    d_to = parse_date(to_date, today())
    conn = connect()
    rows = conn.execute(
        "SELECT p.*, m.code AS model_code, m.name AS model_name, m.line"
        " FROM plans p JOIN models m ON m.id = p.model_id"
        " WHERE p.plan_date BETWEEN ? AND ?"
        " ORDER BY p.plan_date DESC, m.code, p.shift",
        (iso(d_from), iso(d_to)),
    ).fetchall()
    conn.close()

    items = []
    by_day = {}
    by_model = {}
    for r in rows:
        actual = r["actual_qty"]
        item = {
            "id": r["id"],
            "date": r["plan_date"],
            "model_id": r["model_id"],
            "model": r["model_code"],
            "model_name": r["model_name"],
            "line": r["line"],
            "shift": r["shift"],
            "plan": r["plan_qty"],
            "actual": actual,
            "achievement": pct(actual, r["plan_qty"]) if actual is not None else None,
            "gap": (actual - r["plan_qty"]) if actual is not None else None,
        }
        items.append(item)

        day = by_day.setdefault(
            r["plan_date"],
            {"date": r["plan_date"], "plan": 0, "actual": 0, "plan_started": 0, "has_actual": False},
        )
        day["plan"] += r["plan_qty"]
        if actual is not None:
            day["actual"] += actual
            day["plan_started"] += r["plan_qty"]
            day["has_actual"] = True

        mod = by_model.setdefault(
            r["model_code"], {"model": r["model_code"], "name": r["model_name"], "plan": 0, "actual": 0}
        )
        mod["plan"] += r["plan_qty"]
        mod["actual"] += actual or 0

    days = sorted(by_day.values(), key=lambda x: x["date"])
    for d in days:
        # เทียบกับแผนของกะที่เริ่มแล้วเท่านั้น วันที่กะดึกยังไม่เริ่มจึงไม่ถูกนับว่าตกแผน
        d["achievement"] = pct(d["actual"], d["plan_started"]) if d["has_actual"] else None
    models = sorted(by_model.values(), key=lambda x: -x["plan"])
    for m in models:
        m["achievement"] = pct(m["actual"], m["plan"])

    total_plan = sum(d["plan"] for d in days)
    total_actual = sum(d["actual"] for d in days)
    # เทียบเฉพาะกะที่เริ่มไปแล้ว ไม่งั้นตอนกลางวันจะดูตกแผนทุกวันเพราะกะดึกยังไม่เริ่ม
    started = [i for i in items if i["actual"] is not None]
    plan_started = sum(i["plan"] for i in started)
    actual_started = sum(i["actual"] for i in started)

    # สรุปรายสัปดาห์ (จันทร์เป็นวันแรก)
    weeks = {}
    for d in days:
        dd = parse_date(d["date"])
        wk = dd - timedelta(days=dd.weekday())
        w = weeks.setdefault(
            iso(wk), {"week_start": iso(wk), "plan": 0, "actual": 0, "plan_started": 0, "has_actual": False}
        )
        w["plan"] += d["plan"]
        w["actual"] += d["actual"]
        if d["has_actual"]:
            w["has_actual"] = True
            w["plan_started"] += d["plan_started"]
    week_list = sorted(weeks.values(), key=lambda x: x["week_start"])
    for w in week_list:
        # สัปดาห์ที่ยังไม่มีผลจริงเลย ไม่ควรโชว์ 0% เพราะยังไม่ถึงเวลาผลิต
        w["achievement"] = pct(w["actual"], w["plan_started"]) if w["has_actual"] else None

    return {
        "from": iso(d_from),
        "to": iso(d_to),
        "items": items,
        "days": days,
        "models": models,
        "weeks": week_list,
        "summary": {
            "plan": total_plan,
            "actual": total_actual,
            "achievement": pct(total_actual, total_plan),
            "gap": total_actual - total_plan,
            "plan_started": plan_started,
            "actual_started": actual_started,
            "achievement_started": pct(actual_started, plan_started),
            "shifts_started": len(started),
            "shifts_total": len(items),
        },
    }


def update_actual(plan_id, actual_qty):
    conn = connect()
    row = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if row is None:
        conn.close()
        return {"ok": False, "error": "ไม่พบรายการแผนนี้"}
    conn.execute("UPDATE plans SET actual_qty = ? WHERE id = ?", (actual_qty, plan_id))
    conn.commit()
    conn.close()
    return {"ok": True, "id": plan_id, "actual": actual_qty}


def create_plan(payload):
    plan_date = payload.get("date") or iso(today())
    model_id = int(payload.get("model_id") or 0)
    shift = payload.get("shift") or "กะเช้า"
    plan_qty = int(payload.get("plan_qty") or 0)
    if not model_id or plan_qty <= 0:
        return {"ok": False, "error": "กรุณาเลือกรุ่นและใส่จำนวนแผนให้ถูกต้อง"}
    conn = connect()
    dup = conn.execute(
        "SELECT id FROM plans WHERE plan_date=? AND model_id=? AND shift=?",
        (plan_date, model_id, shift),
    ).fetchone()
    if dup:
        conn.execute("UPDATE plans SET plan_qty=? WHERE id=?", (plan_qty, dup["id"]))
        conn.commit()
        conn.close()
        return {"ok": True, "id": dup["id"], "updated": True}
    cur = conn.execute(
        "INSERT INTO plans (plan_date, model_id, shift, plan_qty, actual_qty, note)"
        " VALUES (?,?,?,?,NULL,'')",
        (plan_date, model_id, shift, plan_qty),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"ok": True, "id": new_id, "updated": False}


# ---------------------------------------------------------------- จองเครื่อง


def _free_slots(open_hour, close_hour, taken):
    """คืนช่วงเวลาว่างจากรายการที่ถูกจองไปแล้ว"""
    slots = []
    cursor = float(open_hour)
    for s, e in sorted(taken):
        if s > cursor:
            slots.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < close_hour:
        slots.append((cursor, float(close_hour)))
    return [{"start": s, "end": e} for s, e in slots if e - s >= 0.5]


def capacity_board(book_date=None, mtype=None):
    d = parse_date(book_date, today())
    conn = connect()
    machines = conn.execute("SELECT * FROM machines ORDER BY mtype, code").fetchall()
    bookings = conn.execute(
        "SELECT * FROM bookings WHERE book_date = ? AND status != 'CANCELLED'"
        " ORDER BY machine_id, start_hour",
        (iso(d),),
    ).fetchall()
    conn.close()

    grouped = {}
    for b in bookings:
        grouped.setdefault(b["machine_id"], []).append(b)

    out = []
    type_stat = {}
    for m in machines:
        if mtype and m["mtype"] != mtype:
            continue
        rows = grouped.get(m["id"], [])
        open_h, close_h = float(m["open_hour"]), float(m["close_hour"])
        window = close_h - open_h
        used = sum(min(b["end_hour"], close_h) - max(b["start_hour"], open_h) for b in rows)
        used = max(0.0, used)
        available = m["status"] == "READY"
        free = _free_slots(open_h, close_h, [(b["start_hour"], b["end_hour"]) for b in rows]) if available else []
        next_free = free[0] if free else None
        util = pct(used, window) if available else 100.0

        out.append(
            {
                "id": m["id"],
                "code": m["code"],
                "name": m["name"],
                "type": m["mtype"],
                "type_label": MACHINE_TYPES.get(m["mtype"], m["mtype"]),
                "location": m["location"],
                "status": m["status"],
                "open_hour": open_h,
                "close_hour": close_h,
                "used_hours": round(used, 1),
                "free_hours": round(max(0.0, window - used), 1) if available else 0.0,
                "utilization": util,
                "next_free": next_free,
                "free_slots": free,
                "bookings": [
                    {
                        "id": b["id"],
                        "job_no": b["job_no"],
                        "owner": b["owner"],
                        "team": b["team"],
                        "purpose": b["purpose"],
                        "start": b["start_hour"],
                        "end": b["end_hour"],
                        "status": b["status"],
                    }
                    for b in rows
                ],
            }
        )

        st = type_stat.setdefault(
            m["mtype"],
            {"type": m["mtype"], "label": MACHINE_TYPES.get(m["mtype"], m["mtype"]), "machines": 0, "window": 0.0, "used": 0.0, "down": 0},
        )
        st["machines"] += 1
        if available:
            st["window"] += window
            st["used"] += used
        else:
            st["down"] += 1

    stats = []
    for st in type_stat.values():
        st["utilization"] = pct(st["used"], st["window"])
        st["free_hours"] = round(max(0.0, st["window"] - st["used"]), 1)
        st["used"] = round(st["used"], 1)
        st["window"] = round(st["window"], 1)
        stats.append(st)
    stats.sort(key=lambda x: -x["utilization"])

    return {"date": iso(d), "machines": out, "types": stats}


def create_booking(payload):
    machine_id = int(payload.get("machine_id") or 0)
    book_date = payload.get("date") or iso(today())
    try:
        start = float(payload.get("start_hour"))
        end = float(payload.get("end_hour"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "เวลาเริ่มหรือเวลาจบไม่ถูกต้อง"}
    owner = (payload.get("owner") or "").strip()
    if not machine_id or not owner:
        return {"ok": False, "error": "กรุณาเลือกเครื่องและใส่ชื่อผู้จอง"}
    if end <= start:
        return {"ok": False, "error": "เวลาจบต้องมากกว่าเวลาเริ่ม"}

    conn = connect()
    m = conn.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()
    if m is None:
        conn.close()
        return {"ok": False, "error": "ไม่พบเครื่องนี้"}
    if m["status"] != "READY":
        conn.close()
        return {"ok": False, "error": "เครื่อง %s ปิดซ่อมอยู่ จองไม่ได้" % m["code"]}
    if start < m["open_hour"] or end > m["close_hour"]:
        conn.close()
        return {
            "ok": False,
            "error": "เครื่อง %s เปิดให้จอง %02d:00 ถึง %02d:00 เท่านั้น"
            % (m["code"], m["open_hour"], m["close_hour"]),
        }

    clash = conn.execute(
        "SELECT * FROM bookings WHERE machine_id=? AND book_date=? AND status!='CANCELLED'"
        " AND start_hour < ? AND end_hour > ? LIMIT 1",
        (machine_id, book_date, end, start),
    ).fetchone()
    if clash:
        conn.close()
        return {
            "ok": False,
            "error": "ช่วงเวลานี้ชนกับคิวของ %s (%s - %s)"
            % (clash["owner"], hhmm(clash["start_hour"]), hhmm(clash["end_hour"])),
        }

    cur = conn.execute(
        "INSERT INTO bookings (machine_id, job_no, owner, team, purpose, book_date,"
        " start_hour, end_hour, status, created_at) VALUES (?,?,?,?,?,?,?,?,'BOOKED',?)",
        (
            machine_id,
            (payload.get("job_no") or "").strip(),
            owner,
            (payload.get("team") or "").strip(),
            (payload.get("purpose") or "").strip(),
            book_date,
            start,
            end,
            now_iso(),
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"ok": True, "id": new_id}


def cancel_booking(booking_id):
    conn = connect()
    row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if row is None:
        conn.close()
        return {"ok": False, "error": "ไม่พบคิวจองนี้"}
    conn.execute("UPDATE bookings SET status='CANCELLED' WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "id": booking_id}


def hhmm(value):
    h = int(value)
    m = int(round((value - h) * 60))
    return "%02d:%02d" % (h, m)


# ---------------------------------------------------------------- WIP


def _job_row(r, ref_date):
    stage_at = parse_date(r["stage_at"], ref_date)
    started = parse_date(r["started_at"], ref_date)
    due = parse_date(r["due_date"], ref_date)
    idx = STAGES.index(r["stage"]) if r["stage"] in STAGES else 0
    # ชั่วโมงที่เหลือ = ส่วนที่ยังไม่เสร็จของขั้นปัจจุบัน บวกขั้นที่เหลือทั้งหมด
    spent = max(0, (ref_date - stage_at).days) * WORK_HOURS_PER_DAY
    remain_current = max(2.0, STAGE_HOURS[STAGES[idx]] - spent)
    remain_hours = remain_current + sum(STAGE_HOURS[s] for s in STAGES[idx + 1:])
    eta = ref_date + timedelta(days=max(1, int(math.ceil(remain_hours / WORK_HOURS_PER_DAY))))
    if r["status"] == "CLOSED":
        eta = parse_date(r["closed_at"], due)
    days_late = (eta - due).days
    return {
        "id": r["id"],
        "job_no": r["job_no"],
        "model": r["model_code"],
        "customer": r["customer"],
        "qty": r["qty"],
        "stage": r["stage"],
        "stage_index": idx,
        "stage_count": len(STAGES),
        "progress": round((idx) * 100.0 / (len(STAGES) - 1), 0),
        "owner_id": r["owner_id"],
        "owner": r["owner_name"],
        "team": r["owner_team"],
        "priority": r["priority"],
        "status": r["status"],
        "started_at": r["started_at"],
        "age_days": (ref_date - started).days,
        "stage_days": (ref_date - stage_at).days,
        "due_date": r["due_date"],
        "due_in_days": (due - ref_date).days,
        "eta": iso(eta),
        "risk": "LATE" if days_late > 0 else ("WATCH" if days_late == 0 else "OK"),
    }


def wip_board(stage=None, team=None, owner_id=None):
    ref = today()
    conn = connect()
    rows = conn.execute(
        "SELECT j.*, m.code AS model_code, mb.name AS owner_name, mb.team AS owner_team"
        " FROM jobs j JOIN models m ON m.id = j.model_id"
        " LEFT JOIN members mb ON mb.id = j.owner_id"
        " WHERE j.status = 'OPEN' ORDER BY j.due_date, j.job_no"
    ).fetchall()
    conn.close()

    jobs = [_job_row(r, ref) for r in rows]
    if stage:
        jobs = [j for j in jobs if j["stage"] == stage]
    if team:
        jobs = [j for j in jobs if j["team"] == team]
    if owner_id:
        jobs = [j for j in jobs if j["owner_id"] == int(owner_id)]

    lanes = []
    for s in STAGES[:-1]:
        in_stage = [j for j in jobs if j["stage"] == s]
        lanes.append(
            {
                "stage": s,
                "count": len(in_stage),
                "qty": sum(j["qty"] for j in in_stage),
                "late": len([j for j in in_stage if j["risk"] == "LATE"]),
                "avg_days": round(
                    sum(j["stage_days"] for j in in_stage) / len(in_stage), 1
                )
                if in_stage
                else 0,
                "jobs": in_stage,
            }
        )

    return {
        "jobs": jobs,
        "lanes": lanes,
        "stages": STAGES,
        "summary": {
            "open": len(jobs),
            "late": len([j for j in jobs if j["risk"] == "LATE"]),
            "urgent": len([j for j in jobs if j["priority"] == "URGENT"]),
            "stuck": len([j for j in jobs if j["stage_days"] >= 3]),
            "avg_age": round(sum(j["age_days"] for j in jobs) / len(jobs), 1) if jobs else 0,
        },
    }


def advance_job(job_id, actor="Leader"):
    conn = connect()
    r = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if r is None:
        conn.close()
        return {"ok": False, "error": "ไม่พบงานนี้"}
    idx = STAGES.index(r["stage"]) if r["stage"] in STAGES else 0
    if idx >= len(STAGES) - 1:
        conn.close()
        return {"ok": False, "error": "งานนี้ปิดแล้ว"}
    new_stage = STAGES[idx + 1]
    closed = new_stage == STAGES[-1]
    conn.execute(
        "UPDATE jobs SET stage=?, stage_at=?, status=?, closed_at=? WHERE id=?",
        (
            new_stage,
            iso(today()),
            "CLOSED" if closed else "OPEN",
            iso(today()) if closed else None,
            job_id,
        ),
    )
    conn.execute(
        "INSERT INTO job_events (job_id, kind, detail, actor, ts) VALUES (?,?,?,?,?)",
        (job_id, "STAGE", "%s ไป %s" % (r["stage"], new_stage), actor, now_iso()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "stage": new_stage, "closed": closed}


def assign_job(job_id, member_id, actor="Leader"):
    conn = connect()
    j = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    m = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    if j is None or m is None:
        conn.close()
        return {"ok": False, "error": "ไม่พบงานหรือไม่พบพนักงาน"}
    conn.execute("UPDATE jobs SET owner_id = ? WHERE id = ?", (member_id, job_id))
    conn.execute(
        "INSERT INTO job_events (job_id, kind, detail, actor, ts) VALUES (?,?,?,?,?)",
        (job_id, "ASSIGN", "โยกงานให้ %s (%s)" % (m["name"], m["team"]), actor, now_iso()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "owner": m["name"], "team": m["team"]}


def job_detail(job_id):
    ref = today()
    conn = connect()
    r = conn.execute(
        "SELECT j.*, m.code AS model_code, mb.name AS owner_name, mb.team AS owner_team"
        " FROM jobs j JOIN models m ON m.id = j.model_id"
        " LEFT JOIN members mb ON mb.id = j.owner_id WHERE j.id = ?",
        (job_id,),
    ).fetchone()
    if r is None:
        conn.close()
        return {"ok": False, "error": "ไม่พบงานนี้"}
    events = conn.execute(
        "SELECT * FROM job_events WHERE job_id = ? ORDER BY ts DESC, id DESC", (job_id,)
    ).fetchall()
    bookings = conn.execute(
        "SELECT b.*, mc.code AS machine_code FROM bookings b"
        " JOIN machines mc ON mc.id = b.machine_id"
        " WHERE b.job_no = ? AND b.status != 'CANCELLED' ORDER BY b.book_date, b.start_hour",
        (r["job_no"],),
    ).fetchall()
    conn.close()
    data = _job_row(r, ref)
    data["events"] = [
        {"kind": e["kind"], "detail": e["detail"], "actor": e["actor"], "ts": e["ts"]}
        for e in events
    ]
    data["bookings"] = [
        {
            "machine": b["machine_code"],
            "date": b["book_date"],
            "start": b["start_hour"],
            "end": b["end_hour"],
            "purpose": b["purpose"],
        }
        for b in bookings
    ]
    data["ok"] = True
    return data


# ---------------------------------------------------------------- KPI


def kpi_board(days=14):
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM kpi_daily ORDER BY kpi_date DESC LIMIT ?", (int(days),)
    ).fetchall()
    conn.close()
    series = []
    for r in reversed(rows):
        availability = pct(r["run_min"], r["plan_min"]) / 100.0
        quality = (r["good_qty"] / r["total_qty"]) if r["total_qty"] else 0
        oee = availability * r["perf_rate"] * quality
        series.append(
            {
                "date": r["kpi_date"],
                "output": r["output_qty"],
                "target": r["target_qty"],
                "achievement": pct(r["output_qty"], r["target_qty"]),
                "ot_hours": r["ot_hours"],
                "manpower": r["manpower"],
                "productivity": round(r["output_qty"] / (r["manpower"] * 8.0), 1),
                "utilization": round(availability * 100, 1),
                "yield": round(quality * 100, 2),
                "performance": round(r["perf_rate"] * 100, 1),
                "oee": round(oee * 100, 1),
            }
        )
    if not series:
        return {"series": [], "today": None, "avg": {}}

    latest = series[-1]
    prev = series[-2] if len(series) > 1 else latest
    keys = ["output", "productivity", "ot_hours", "utilization", "yield", "oee", "achievement"]
    avg = {k: round(sum(s[k] for s in series) / len(series), 1) for k in keys}
    delta = {k: round(latest[k] - prev[k], 1) for k in keys}
    return {"series": series, "today": latest, "avg": avg, "delta": delta}


# ---------------------------------------------------------------- ทีมงาน


def team_board():
    ref = today()
    conn = connect()
    members = conn.execute("SELECT * FROM members ORDER BY team, role DESC, name").fetchall()
    rows = conn.execute(
        "SELECT j.*, m.code AS model_code, mb.name AS owner_name, mb.team AS owner_team"
        " FROM jobs j JOIN models m ON m.id = j.model_id"
        " LEFT JOIN members mb ON mb.id = j.owner_id WHERE j.status = 'OPEN'"
    ).fetchall()
    bookings = conn.execute(
        "SELECT owner, SUM(end_hour - start_hour) AS hrs FROM bookings"
        " WHERE book_date = ? AND status != 'CANCELLED' GROUP BY owner",
        (iso(ref),),
    ).fetchall()
    conn.close()

    booked = {b["owner"]: b["hrs"] or 0 for b in bookings}
    jobs = [_job_row(r, ref) for r in rows]

    people = []
    for m in members:
        mine = [j for j in jobs if j["owner_id"] == m["id"]]
        # ภาระงานต่อวัน = เวลาที่งานในมือกินไปวันนี้ บวกเวลาที่ต้องเฝ้าเครื่องที่จองไว้
        # หารด้วย 12 เพราะขั้นตอนหนึ่งกินเวลาหลายวัน ไม่ได้ลงแรงทั้งก้อนในวันเดียว
        # คูณ 0.6 กับเวลาจองเครื่อง เพราะไม่ต้องยืนเฝ้าตลอดช่วงที่จอง
        job_hours = sum(STAGE_HOURS[j["stage"]] for j in mine) / 12.0
        load_hours = job_hours + booked.get(m["name"], 0) * 0.6
        load = pct(load_hours, m["hours_cap"])
        people.append(
            {
                "id": m["id"],
                "name": m["name"],
                "team": m["team"],
                "role": m["role"],
                "skill": m["skill"],
                "jobs": len(mine),
                "urgent": len([j for j in mine if j["priority"] == "URGENT"]),
                "late": len([j for j in mine if j["risk"] == "LATE"]),
                "booked_hours": round(booked.get(m["name"], 0), 1),
                "load": load,
                "state": "OVER" if load > 110 else ("BUSY" if load >= 70 else ("FREE" if load < 40 else "OK")),
                "job_list": sorted(mine, key=lambda x: x["due_date"])[:6],
            }
        )

    teams = {}
    for p in people:
        t = teams.setdefault(p["team"], {"team": p["team"], "people": 0, "jobs": 0, "load": 0.0, "late": 0, "leader": ""})
        t["people"] += 1
        t["jobs"] += p["jobs"]
        t["load"] += p["load"]
        t["late"] += p["late"]
        if p["role"] == "Leader":
            t["leader"] = p["name"]
    team_list = []
    for t in teams.values():
        t["load"] = round(t["load"] / t["people"], 1) if t["people"] else 0
        team_list.append(t)
    team_list.sort(key=lambda x: x["team"])

    over = [p for p in people if p["state"] == "OVER"]
    free = [p for p in people if p["state"] == "FREE"]
    moves = []
    for o in over:
        for f in free:
            if f["skill"] == o["skill"] and len(moves) < 5:
                job = o["job_list"][0] if o["job_list"] else None
                if job:
                    moves.append(
                        {
                            "job_id": job["id"],
                            "job_no": job["job_no"],
                            "from_name": o["name"],
                            "from_load": o["load"],
                            "to_id": f["id"],
                            "to_name": f["name"],
                            "to_load": f["load"],
                            "skill": f["skill"],
                            "cross_team": f["team"] != o["team"],
                        }
                    )
                break

    return {
        "people": people,
        "teams": team_list,
        "suggestions": moves,
        "summary": {
            "headcount": len(people),
            "over": len(over),
            "free": len(free),
            "avg_load": round(sum(p["load"] for p in people) / len(people), 1) if people else 0,
        },
    }


# ---------------------------------------------------------------- Alert


def alerts_board():
    ref = today()
    cap = capacity_board(iso(ref))
    wip = wip_board()
    team = team_board()
    plan = plan_board(iso(ref), iso(ref))
    kpi = kpi_board(7)

    conn = connect()
    acked = {
        r["alert_key"]
        for r in conn.execute("SELECT alert_key FROM alert_ack WHERE ack_date = ?", (iso(ref),)).fetchall()
    }
    conn.close()

    out = []

    def add(key, level, title, detail, action, hint):
        out.append(
            {
                "key": key,
                "level": level,
                "title": title,
                "detail": detail,
                "action": action,
                "hint": hint,
                "acked": key in acked,
            }
        )

    # 1. เครื่องเต็ม / เหลือน้อย
    for t in cap["types"]:
        if t["utilization"] >= 90:
            add(
                "cap-full-%s" % t["type"],
                "critical",
                "%s เต็มแล้ว" % t["label"],
                "ใช้ไป %.0f%% ของเวลาเปิดวันนี้ เหลือว่างอีก %.1f ชั่วโมง" % (t["utilization"], t["free_hours"]),
                "#/capacity",
                "เลื่อนคิวที่ไม่ด่วนไปวันพรุ่งนี้ หรือขอเปิดเครื่องนอกเวลา",
            )
        elif t["utilization"] >= 80:
            add(
                "cap-low-%s" % t["type"],
                "warn",
                "%s เหลือน้อยกว่า 20%%" % t["label"],
                "ว่างอีก %.1f ชั่วโมงจากทั้งหมด %.1f ชั่วโมง" % (t["free_hours"], t["window"]),
                "#/capacity",
                "จองล่วงหน้าให้งานด่วนก่อนคิวเต็ม",
            )
    for m in cap["machines"]:
        if m["status"] != "READY":
            add(
                "machine-down-%s" % m["code"],
                "warn",
                "%s ปิดซ่อมอยู่" % m["code"],
                "%s ที่ %s ยังไม่พร้อมใช้งาน" % (m["name"], m["location"]),
                "#/capacity",
                "ย้ายงานไปเครื่องประเภทเดียวกันที่ยังว่าง",
            )

    # 2. งานเลย Due Date หรือใกล้เลย
    late = [j for j in wip["jobs"] if j["due_in_days"] < 0]
    risky = [j for j in wip["jobs"] if j["due_in_days"] >= 0 and j["risk"] == "LATE"]
    if late:
        add(
            "job-overdue",
            "critical",
            "งานเลยกำหนดส่งแล้ว %d ใบ" % len(late),
            "งานเก่าสุดคือ %s เลยมา %d วัน" % (late[0]["job_no"], -late[0]["due_in_days"]),
            "#/wip",
            "ดันงานเหล่านี้ขึ้นก่อน แล้วแจ้งลูกค้าเรื่องวันส่งใหม่",
        )
    if risky:
        add(
            "job-risk",
            "warn",
            "งานเสี่ยงส่งไม่ทัน %d ใบ" % len(risky),
            "คาดว่าจะเสร็จหลังวันครบกำหนด ถ้าเดินงานด้วยจังหวะเดิม",
            "#/wip",
            "เพิ่มคนหรือจองเครื่องให้งานกลุ่มนี้ก่อน",
        )
    stuck = [j for j in wip["jobs"] if j["stage_days"] >= 4]
    if stuck:
        add(
            "job-stuck",
            "warn",
            "งานค้างขั้นตอนเดิมเกิน 4 วัน %d ใบ" % len(stuck),
            "ค้างนานสุด %d วัน ที่ขั้นตอน %s" % (max(j["stage_days"] for j in stuck), stuck[0]["stage"]),
            "#/wip",
            "เช็กว่าติดที่เครื่อง ติดที่คน หรือรอผลจากหน่วยอื่น",
        )

    # 3. กำลังคน
    if team["summary"]["over"]:
        add(
            "manpower-over",
            "critical" if team["summary"]["over"] >= 3 else "warn",
            "คนงานล้น %d คน" % team["summary"]["over"],
            "ภาระงานเฉลี่ยทั้งฝ่าย %.0f%% ของกำลังที่มี" % team["summary"]["avg_load"],
            "#/leader",
            "ใช้คำแนะนำโยกงานในหน้า Leader Control Tower",
        )
    if team["summary"]["avg_load"] >= 95:
        add(
            "manpower-short",
            "warn",
            "กำลังคนไม่พอทั้งฝ่าย",
            "ภาระงานเฉลี่ย %.0f%% แปลว่าไม่เหลือที่รับงานแทรก" % team["summary"]["avg_load"],
            "#/leader",
            "ขอ OT หรือขอยืมคนจากทีมอื่นล่วงหน้า",
        )

    # 4. แผนผลิตวันนี้ เทียบเฉพาะกะที่เริ่มไปแล้ว
    s = plan["summary"]
    if s["plan_started"] and s["achievement_started"] < 85:
        add(
            "plan-behind",
            "warn",
            "ผลผลิตวันนี้ต่ำกว่าแผน",
            "กะที่เริ่มแล้วทำได้ %s จากแผน %s ชิ้น คิดเป็น %.0f%%"
            % (f"{s['actual_started']:,}", f"{s['plan_started']:,}", s["achievement_started"]),
            "#/plan",
            "ดูว่ารุ่นไหนตกแผน แล้วเติมกำลังที่ไลน์นั้น",
        )

    # 5. คุณภาพและ OEE
    if kpi["today"]:
        if kpi["today"]["yield"] < 97:
            add(
                "yield-low",
                "warn",
                "Yield ต่ำกว่าเป้า",
                "วันนี้ %.2f%% เทียบค่าเฉลี่ย 7 วันที่ %.1f%%" % (kpi["today"]["yield"], kpi["avg"]["yield"]),
                "#/kpi",
                "ตรวจของเสียตามรุ่น หาสาเหตุที่ขั้นตอนเดียวกัน",
            )
        if kpi["today"]["oee"] < 65:
            add(
                "oee-low",
                "info",
                "OEE ต่ำกว่า 65%",
                "วันนี้ %.1f%% มาจาก Utilization %.0f%% และ Yield %.1f%%"
                % (kpi["today"]["oee"], kpi["today"]["utilization"], kpi["today"]["yield"]),
                "#/kpi",
                "ไล่ดู downtime ของเครื่องที่ใช้บ่อยที่สุด",
            )

    rank = {"critical": 0, "warn": 1, "info": 2}
    out.sort(key=lambda a: (a["acked"], rank.get(a["level"], 3), a["title"]))
    return {
        "alerts": out,
        "counts": {
            "critical": len([a for a in out if a["level"] == "critical" and not a["acked"]]),
            "warn": len([a for a in out if a["level"] == "warn" and not a["acked"]]),
            "info": len([a for a in out if a["level"] == "info" and not a["acked"]]),
            "acked": len([a for a in out if a["acked"]]),
        },
    }


def ack_alert(key, actor="ผู้ใช้"):
    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO alert_ack (alert_key, ack_date, actor, ts) VALUES (?,?,?,?)",
        (key, iso(today()), actor, now_iso()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "key": key}


def unack_alert(key):
    conn = connect()
    conn.execute("DELETE FROM alert_ack WHERE alert_key = ? AND ack_date = ?", (key, iso(today())))
    conn.commit()
    conn.close()
    return {"ok": True, "key": key}


# ---------------------------------------------------------------- ภาพรวม


def overview():
    ref = today()
    plan = plan_board(iso(ref - timedelta(days=6)), iso(ref))
    # เทียบรุ่นเฉพาะวันที่จบแล้ว วันนี้ยังผลิตไม่ครบจะทำให้ทุกรุ่นดูตกเป้าทั้งที่ยังไม่จบวัน
    done_plan = plan_board(iso(ref - timedelta(days=7)), iso(ref - timedelta(days=1)))
    today_plan = plan_board(iso(ref), iso(ref))
    cap = capacity_board(iso(ref))
    wip = wip_board()
    kpi = kpi_board(14)
    team = team_board()
    al = alerts_board()

    chamber = next((t for t in cap["types"] if t["type"] == "CHAMBER"), None)
    return {
        "date": iso(ref),
        "generated_at": now_iso(),
        "cards": {
            "output_today": today_plan["summary"]["actual"],
            "plan_today": today_plan["summary"]["plan"],
            "plan_started": today_plan["summary"]["plan_started"],
            "achievement_today": today_plan["summary"]["achievement_started"],
            "shifts_started": today_plan["summary"]["shifts_started"],
            "shifts_total": today_plan["summary"]["shifts_total"],
            "wip_open": wip["summary"]["open"],
            "wip_late": wip["summary"]["late"],
            "chamber_util": chamber["utilization"] if chamber else 0,
            "chamber_free": chamber["free_hours"] if chamber else 0,
            "oee": kpi["today"]["oee"] if kpi["today"] else 0,
            "yield": kpi["today"]["yield"] if kpi["today"] else 0,
            "ot_hours": kpi["today"]["ot_hours"] if kpi["today"] else 0,
            "avg_load": team["summary"]["avg_load"],
            "over_people": team["summary"]["over"],
            "free_people": team["summary"]["free"],
        },
        "trend": [
            {"date": d["date"], "plan": d["plan"], "actual": d["actual"], "achievement": d["achievement"]}
            for d in plan["days"]
        ],
        "kpi_series": kpi["series"][-10:],
        "models": done_plan["models"],
        "lanes": [{"stage": l["stage"], "count": l["count"], "late": l["late"]} for l in wip["lanes"]],
        "machine_types": cap["types"],
        "teams": team["teams"],
        "alerts": al["alerts"][:5],
        "alert_counts": al["counts"],
        "hot_jobs": sorted(wip["jobs"], key=lambda j: (j["due_in_days"], -j["stage_days"]))[:6],
    }


def reference():
    conn = connect()
    models = conn.execute("SELECT id, code, name, line FROM models ORDER BY code").fetchall()
    members = conn.execute("SELECT id, name, team, role, skill FROM members ORDER BY team, name").fetchall()
    machines = conn.execute(
        "SELECT id, code, name, mtype, location, status, open_hour, close_hour FROM machines ORDER BY code"
    ).fetchall()
    conn.close()
    return {
        "models": [dict(r) for r in models],
        "members": [dict(r) for r in members],
        "machines": [dict(r) for r in machines],
        "stages": STAGES,
        "machine_types": MACHINE_TYPES,
    }

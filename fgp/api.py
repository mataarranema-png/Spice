"""REST API ของระบบ FGP — ลงทะเบียนเส้นทางด้วย decorator เล็กๆ"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re

from . import auth, db, smart

ROUTES: list[tuple[str, re.Pattern, str | None, callable]] = []


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class Ctx:
    """ข้อมูลของแต่ละคำขอ"""

    def __init__(self, user, body, query, params):
        self.user = user
        self.body = body or {}
        self.query = query or {}
        self.params = params or {}

    def arg(self, key, default=None):
        v = self.query.get(key)
        return v if v not in (None, "") else default

    def need(self, key):
        v = self.body.get(key)
        if v in (None, ""):
            raise ApiError(f"ต้องระบุข้อมูล: {key}")
        return v

    def int_arg(self, key, default=None):
        v = self.arg(key, default)
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    @property
    def uid(self):
        return self.user["id"] if self.user else None


def route(method: str, pattern: str, role: str | None = "viewer"):
    regex = re.compile("^" + re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern) + "$")

    def deco(fn):
        ROUTES.append((method.upper(), regex, role, fn))
        return fn

    return deco


def dispatch(method: str, path: str, user, body, query):
    matched_path = False
    for m, regex, role, fn in ROUTES:
        match = regex.match(path)
        if not match:
            continue
        matched_path = True
        if m != method:
            continue
        if role and not auth.can(user, role):
            raise ApiError("ไม่มีสิทธิ์ใช้งานส่วนนี้", 403 if user else 401)
        return fn(Ctx(user, body, query, match.groupdict()))
    raise ApiError("ไม่พบเส้นทางนี้", 405 if matched_path else 404)


def _today(ctx) -> str:
    return ctx.arg("date", db.today())


def _shift(ctx) -> str:
    return ctx.arg("shift", smart.current_shift())


# ------------------------------------------------------------------- auth

@route("POST", "/api/auth/login", role=None)
def api_login(ctx):
    res = auth.login(str(ctx.need("username")), str(ctx.need("password")))
    if not res:
        raise ApiError("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", 401)
    return {"ok": True, "user": res["user"], "_set_token": res["token"]}


@route("POST", "/api/auth/logout", role=None)
def api_logout(ctx):
    return {"ok": True, "_clear_token": True}


@route("GET", "/api/me", role=None)
def api_me(ctx):
    if not ctx.user:
        raise ApiError("ยังไม่ได้เข้าสู่ระบบ", 401)
    return {"user": auth.public_user(ctx.user)}


@route("GET", "/api/bootstrap")
def api_bootstrap(ctx):
    return {
        "user": auth.public_user(ctx.user),
        "today": db.today(),
        "shift": smart.current_shift(),
        "shifts": list(db.SHIFTS),
        "shift_hours": db.SHIFT_HOURS,
        "lines": db.query("SELECT * FROM lines WHERE active=1 ORDER BY code"),
        "models": db.query("SELECT * FROM models WHERE active=1 ORDER BY code"),
        "leaders": db.query("SELECT id,name,username,role FROM users WHERE active=1 "
                            "AND role IN ('leader','manager','admin') ORDER BY name"),
        "server_time": db.now(),
    }


# -------------------------------------------------------------- dashboard

@route("GET", "/api/dashboard")
def api_dashboard(ctx):
    date_str, shift = _today(ctx), _shift(ctx)
    day = db.one(
        "SELECT COALESCE(SUM(ok_qty),0) AS ok, COALESCE(SUM(ng_qty),0) AS ng, "
        "COALESCE(SUM(downtime_min),0) AS dtm FROM production WHERE rec_date=?", (date_str,))
    target = db.one("SELECT COALESCE(SUM(target_qty),0) AS t FROM plans WHERE plan_date=?",
                    (date_str,))["t"]
    yesterday = (dt.date.fromisoformat(date_str) - dt.timedelta(days=1)).isoformat()
    prev = db.one("SELECT COALESCE(SUM(ok_qty),0) AS ok FROM production WHERE rec_date=?",
                  (yesterday,))["ok"]
    fc = smart.forecast(date_str, shift)
    return {
        "date": date_str, "shift": shift,
        "kpi": {
            "ok": day["ok"], "ng": day["ng"], "target": target,
            "achievement": smart.pct(day["ok"], target),
            "yield": smart.pct(day["ok"], day["ok"] + day["ng"]),
            "downtime": day["dtm"],
            "vs_yesterday": round(day["ok"] - prev),
            "vs_yesterday_pct": smart.pct(day["ok"] - prev, prev) if prev else 0.0,
        },
        "oee": smart.oee(date_str, shift),
        "forecast": fc,
        "projected_total": sum(f["projected"] for f in fc),
        "hourly": smart.hourly_curve(date_str, shift),
        "trend": smart.daily_trend(14),
        "lines": smart.line_ranking(date_str),
        "advice": smart.advisor(date_str, shift)[:6],
        "manpower": smart.manpower_gap(date_str, shift),
        "open_tasks": db.one("SELECT COUNT(*) AS c FROM tasks WHERE status<>'done'")["c"],
        "pending_bookings": db.one(
            "SELECT COUNT(*) AS c FROM bookings WHERE status='pending' AND book_date>=?",
            (db.today(),))["c"],
        "alerts": db.query("SELECT a.*, l.code AS line_code FROM alerts a "
                           "LEFT JOIN lines l ON l.id=a.line_id WHERE a.ack_at IS NULL "
                           "ORDER BY a.id DESC LIMIT 8"),
    }


@route("GET", "/api/andon")
def api_andon(ctx):
    date_str, shift = _today(ctx), _shift(ctx)
    return {
        "date": date_str, "shift": shift, "time": db.now(),
        "lines": smart.forecast(date_str, shift),
        "oee": smart.oee(date_str, shift),
        "advice": [a for a in smart.advisor(date_str, shift) if a["severity"] == "high"][:5],
    }


# ------------------------------------------------------------- production

@route("GET", "/api/production")
def api_production_list(ctx):
    where, args = ["p.rec_date=?"], [_today(ctx)]
    if ctx.arg("shift"):
        where.append("p.shift=?")
        args.append(ctx.arg("shift"))
    if ctx.int_arg("line_id"):
        where.append("p.line_id=?")
        args.append(ctx.int_arg("line_id"))
    rows = db.query(
        "SELECT p.*, l.code AS line_code, m.code AS model_code FROM production p "
        "JOIN lines l ON l.id=p.line_id JOIN models m ON m.id=p.model_id "
        f"WHERE {' AND '.join(where)} ORDER BY l.code, p.shift, p.hour", args)
    return {"items": rows}


@route("POST", "/api/production", role="operator")
def api_production_save(ctx):
    b = ctx.body
    rec_date = b.get("rec_date") or db.today()
    hour = int(ctx.need("hour"))
    if not 1 <= hour <= db.SHIFT_HOURS:
        raise ApiError(f"ชั่วโมงต้องอยู่ระหว่าง 1 ถึง {db.SHIFT_HOURS}")
    ok, ng = int(b.get("ok_qty") or 0), int(b.get("ng_qty") or 0)
    if ok < 0 or ng < 0:
        raise ApiError("จำนวนต้องไม่ติดลบ")
    db.execute(
        "INSERT INTO production(rec_date,shift,hour,line_id,model_id,ok_qty,ng_qty,downtime_min,"
        "downtime_reason,manpower,recorded_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(rec_date,shift,hour,line_id) DO UPDATE SET model_id=excluded.model_id,"
        "ok_qty=excluded.ok_qty,ng_qty=excluded.ng_qty,downtime_min=excluded.downtime_min,"
        "downtime_reason=excluded.downtime_reason,manpower=excluded.manpower,"
        "recorded_by=excluded.recorded_by",
        (rec_date, b.get("shift") or smart.current_shift(), hour, int(ctx.need("line_id")),
         int(ctx.need("model_id")), ok, ng, int(b.get("downtime_min") or 0),
         b.get("downtime_reason") or "", int(b.get("manpower") or 0), ctx.uid, db.now()))
    auth.log(ctx.uid, "production.save", f"{rec_date} H{hour}")
    smart.refresh_alerts(rec_date, b.get("shift") or smart.current_shift())
    return {"ok": True}


@route("DELETE", "/api/production/<pid>", role="leader")
def api_production_delete(ctx):
    db.execute("DELETE FROM production WHERE id=?", (int(ctx.params["pid"]),))
    return {"ok": True}


# ------------------------------------------------------------------ plans

@route("GET", "/api/plans")
def api_plans(ctx):
    where, args = [], []
    if ctx.arg("from") and ctx.arg("to"):
        where.append("pl.plan_date BETWEEN ? AND ?")
        args += [ctx.arg("from"), ctx.arg("to")]
    else:
        where.append("pl.plan_date=?")
        args.append(_today(ctx))
    if ctx.arg("shift"):
        where.append("pl.shift=?")
        args.append(ctx.arg("shift"))
    rows = db.query(
        "SELECT pl.*, l.code AS line_code, l.name AS line_name, m.code AS model_code, "
        "m.name AS model_name, m.cycle_sec, "
        "(SELECT COALESCE(SUM(ok_qty),0) FROM production p WHERE p.rec_date=pl.plan_date "
        " AND p.shift=pl.shift AND p.line_id=pl.line_id) AS actual_qty "
        "FROM plans pl JOIN lines l ON l.id=pl.line_id JOIN models m ON m.id=pl.model_id "
        f"WHERE {' AND '.join(where)} ORDER BY pl.plan_date, pl.shift, l.code", args)
    for r in rows:
        r["achievement"] = smart.pct(r["actual_qty"], r["target_qty"])
    return {"items": rows}


@route("POST", "/api/plans", role="leader")
def api_plan_create(ctx):
    b = ctx.body
    pid = db.execute(
        "INSERT INTO plans(plan_date,shift,line_id,model_id,target_qty,priority,note,created_by,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (b.get("plan_date") or db.today(), b.get("shift") or "A", int(ctx.need("line_id")),
         int(ctx.need("model_id")), int(ctx.need("target_qty")), int(b.get("priority") or 2),
         b.get("note") or "", ctx.uid, db.now()))
    auth.log(ctx.uid, "plan.create", str(pid))
    return {"ok": True, "id": pid}


@route("PUT", "/api/plans/<pid>", role="leader")
def api_plan_update(ctx):
    b = ctx.body
    db.execute(
        "UPDATE plans SET plan_date=COALESCE(?,plan_date), shift=COALESCE(?,shift), "
        "line_id=COALESCE(?,line_id), model_id=COALESCE(?,model_id), "
        "target_qty=COALESCE(?,target_qty), priority=COALESCE(?,priority), "
        "status=COALESCE(?,status), note=COALESCE(?,note) WHERE id=?",
        (b.get("plan_date"), b.get("shift"), b.get("line_id"), b.get("model_id"),
         b.get("target_qty"), b.get("priority"), b.get("status"), b.get("note"),
         int(ctx.params["pid"])))
    return {"ok": True}


@route("DELETE", "/api/plans/<pid>", role="leader")
def api_plan_delete(ctx):
    db.execute("DELETE FROM plans WHERE id=?", (int(ctx.params["pid"]),))
    return {"ok": True}


@route("POST", "/api/plans/copy", role="leader")
def api_plan_copy(ctx):
    src, dst = str(ctx.need("from")), str(ctx.need("to"))
    rows = db.query("SELECT * FROM plans WHERE plan_date=?", (src,))
    if not rows:
        raise ApiError("วันต้นทางไม่มีแผนให้คัดลอก")
    ts = db.now()
    db.executemany(
        "INSERT INTO plans(plan_date,shift,line_id,model_id,target_qty,priority,note,created_by,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        [(dst, r["shift"], r["line_id"], r["model_id"], r["target_qty"], r["priority"],
          r["note"], ctx.uid, ts) for r in rows])
    return {"ok": True, "copied": len(rows)}


# --------------------------------------------------------------- masters

@route("GET", "/api/lines")
def api_lines(ctx):
    return {"items": db.query(
        "SELECT l.*, u.name AS leader_name FROM lines l LEFT JOIN users u ON u.id=l.leader_id "
        "ORDER BY l.code")}


@route("POST", "/api/lines", role="manager")
def api_line_create(ctx):
    b = ctx.body
    lid = db.execute(
        "INSERT INTO lines(code,name,section,std_manpower,std_cycle_sec,leader_id) VALUES(?,?,?,?,?,?)",
        (str(ctx.need("code")).upper(), ctx.need("name"), b.get("section") or "FGP",
         int(b.get("std_manpower") or 8), float(b.get("std_cycle_sec") or 30),
         b.get("leader_id") or None))
    return {"ok": True, "id": lid}


@route("PUT", "/api/lines/<lid>", role="manager")
def api_line_update(ctx):
    b = ctx.body
    db.execute("UPDATE lines SET name=COALESCE(?,name), std_manpower=COALESCE(?,std_manpower), "
               "std_cycle_sec=COALESCE(?,std_cycle_sec), leader_id=?, active=COALESCE(?,active) "
               "WHERE id=?",
               (b.get("name"), b.get("std_manpower"), b.get("std_cycle_sec"),
                b.get("leader_id") or None, b.get("active"), int(ctx.params["lid"])))
    return {"ok": True}


@route("GET", "/api/models")
def api_models(ctx):
    return {"items": db.query("SELECT * FROM models ORDER BY code")}


@route("POST", "/api/models", role="manager")
def api_model_create(ctx):
    b = ctx.body
    mid = db.execute(
        "INSERT INTO models(code,name,family,cycle_sec,std_manpower,target_yield) VALUES(?,?,?,?,?,?)",
        (str(ctx.need("code")).upper(), ctx.need("name"), b.get("family") or "FGP",
         float(b.get("cycle_sec") or 30), int(b.get("std_manpower") or 8),
         float(b.get("target_yield") or 99)))
    return {"ok": True, "id": mid}


@route("PUT", "/api/models/<mid>", role="manager")
def api_model_update(ctx):
    b = ctx.body
    db.execute("UPDATE models SET name=COALESCE(?,name), cycle_sec=COALESCE(?,cycle_sec), "
               "std_manpower=COALESCE(?,std_manpower), target_yield=COALESCE(?,target_yield), "
               "active=COALESCE(?,active) WHERE id=?",
               (b.get("name"), b.get("cycle_sec"), b.get("std_manpower"), b.get("target_yield"),
                b.get("active"), int(ctx.params["mid"])))
    return {"ok": True}


# ------------------------------------------------------------- employees

@route("GET", "/api/employees")
def api_employees(ctx):
    where, args = ["e.active=1"], []
    if ctx.arg("shift"):
        where.append("e.shift=?")
        args.append(ctx.arg("shift"))
    if ctx.arg("q"):
        where.append("(e.name LIKE ? OR e.emp_code LIKE ?)")
        args += [f"%{ctx.arg('q')}%"] * 2
    rows = db.query(f"SELECT * FROM employees e WHERE {' AND '.join(where)} ORDER BY e.emp_code", args)
    skills = db.query("SELECT s.employee_id, s.line_id, s.level, l.code FROM skills s "
                      "JOIN lines l ON l.id=s.line_id")
    smap: dict[int, list] = {}
    for s in skills:
        smap.setdefault(s["employee_id"], []).append(
            {"line_id": s["line_id"], "code": s["code"], "level": s["level"]})
    for r in rows:
        r["skills"] = sorted(smap.get(r["id"], []), key=lambda x: -x["level"])
        r["skill_avg"] = round(sum(s["level"] for s in r["skills"]) / len(r["skills"]), 1) \
            if r["skills"] else 0
    return {"items": rows}


@route("POST", "/api/employees", role="leader")
def api_employee_create(ctx):
    b = ctx.body
    eid = db.execute(
        "INSERT INTO employees(emp_code,name,section,position,shift,note) VALUES(?,?,?,?,?,?)",
        (str(ctx.need("emp_code")).upper(), ctx.need("name"), b.get("section") or "FGP",
         b.get("position") or "Operator", b.get("shift") or "A", b.get("note") or ""))
    return {"ok": True, "id": eid}


@route("PUT", "/api/employees/<eid>", role="leader")
def api_employee_update(ctx):
    b = ctx.body
    db.execute("UPDATE employees SET name=COALESCE(?,name), position=COALESCE(?,position), "
               "shift=COALESCE(?,shift), active=COALESCE(?,active), note=COALESCE(?,note) WHERE id=?",
               (b.get("name"), b.get("position"), b.get("shift"), b.get("active"),
                b.get("note"), int(ctx.params["eid"])))
    return {"ok": True}


@route("POST", "/api/employees/<eid>/skill", role="leader")
def api_employee_skill(ctx):
    level = int(ctx.need("level"))
    if not 0 <= level <= 4:
        raise ApiError("ระดับทักษะต้องอยู่ระหว่าง 0 ถึง 4")
    eid, lid = int(ctx.params["eid"]), int(ctx.need("line_id"))
    if level == 0:
        db.execute("DELETE FROM skills WHERE employee_id=? AND line_id=?", (eid, lid))
    else:
        db.execute("INSERT INTO skills(employee_id,line_id,level) VALUES(?,?,?) "
                   "ON CONFLICT(employee_id,line_id) DO UPDATE SET level=excluded.level",
                   (eid, lid, level))
    return {"ok": True}


@route("GET", "/api/skill-matrix")
def api_skill_matrix(ctx):
    lines = db.query("SELECT id, code FROM lines WHERE active=1 ORDER BY code")
    emps = db.query("SELECT id, emp_code, name, shift, position FROM employees "
                    "WHERE active=1 ORDER BY emp_code")
    grid = {(s["employee_id"], s["line_id"]): s["level"]
            for s in db.query("SELECT employee_id, line_id, level FROM skills")}
    for e in emps:
        e["levels"] = [grid.get((e["id"], l["id"]), 0) for l in lines]
    coverage = []
    for idx, l in enumerate(lines):
        levels = [e["levels"][idx] for e in emps]
        coverage.append({"code": l["code"], "line_id": l["id"],
                         "can_run": sum(1 for v in levels if v >= 2),
                         "experts": sum(1 for v in levels if v >= 4),
                         "trainees": sum(1 for v in levels if v == 1)})
    return {"lines": lines, "employees": emps, "coverage": coverage}


# --------------------------------------------------------------- bookings

@route("GET", "/api/bookings")
def api_bookings(ctx):
    where, args = [], []
    if ctx.arg("from") and ctx.arg("to"):
        where.append("b.book_date BETWEEN ? AND ?")
        args += [ctx.arg("from"), ctx.arg("to")]
    elif ctx.arg("date"):
        where.append("b.book_date=?")
        args.append(ctx.arg("date"))
    else:
        where.append("b.book_date >= ?")
        args.append(db.today())
    if ctx.arg("status"):
        where.append("b.status=?")
        args.append(ctx.arg("status"))
    rows = db.query(
        "SELECT b.*, l.code AS line_code, l.name AS line_name, u.name AS requester "
        "FROM bookings b JOIN lines l ON l.id=b.line_id LEFT JOIN users u ON u.id=b.requested_by "
        f"WHERE {' AND '.join(where)} ORDER BY b.book_date, b.shift, l.code", args)
    assigns = db.query(
        "SELECT a.*, e.name, e.emp_code, e.position FROM assignments a "
        "JOIN employees e ON e.id=a.employee_id")
    amap: dict[int, list] = {}
    for a in assigns:
        amap.setdefault(a["booking_id"], []).append(a)
    for r in rows:
        r["assigned"] = amap.get(r["id"], [])
        r["filled"] = len(r["assigned"])
    return {"items": rows}


@route("POST", "/api/bookings", role="leader")
def api_booking_create(ctx):
    b = ctx.body
    bid = db.execute(
        "INSERT INTO bookings(book_date,shift,line_id,required_qty,skill_min,reason,requested_by,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (b.get("book_date") or db.today(), b.get("shift") or "A", int(ctx.need("line_id")),
         int(ctx.need("required_qty")), int(b.get("skill_min") or 1), b.get("reason") or "",
         ctx.uid, db.now()))
    auth.log(ctx.uid, "booking.create", str(bid))
    return {"ok": True, "id": bid}


@route("PUT", "/api/bookings/<bid>", role="leader")
def api_booking_update(ctx):
    b = ctx.body
    db.execute("UPDATE bookings SET status=COALESCE(?,status), required_qty=COALESCE(?,required_qty), "
               "skill_min=COALESCE(?,skill_min), reason=COALESCE(?,reason) WHERE id=?",
               (b.get("status"), b.get("required_qty"), b.get("skill_min"), b.get("reason"),
                int(ctx.params["bid"])))
    return {"ok": True}


@route("DELETE", "/api/bookings/<bid>", role="leader")
def api_booking_delete(ctx):
    db.execute("DELETE FROM bookings WHERE id=?", (int(ctx.params["bid"]),))
    return {"ok": True}


@route("GET", "/api/bookings/<bid>/suggest")
def api_booking_suggest(ctx):
    return {"items": smart.suggest_people(int(ctx.params["bid"]), limit=12)}


@route("POST", "/api/bookings/<bid>/auto", role="leader")
def api_booking_auto(ctx):
    res = smart.auto_assign(int(ctx.params["bid"]))
    if not res.get("ok"):
        raise ApiError(res.get("error", "จัดคนอัตโนมัติไม่สำเร็จ"))
    auth.log(ctx.uid, "booking.auto", ctx.params["bid"], res.get("message", ""))
    return res


@route("POST", "/api/bookings/<bid>/assign", role="leader")
def api_booking_assign(ctx):
    bid = int(ctx.params["bid"])
    eid = int(ctx.need("employee_id"))
    bk = db.one("SELECT * FROM bookings WHERE id=?", (bid,))
    if not bk:
        raise ApiError("ไม่พบคิวจองนี้", 404)
    clash = db.one(
        "SELECT a.id FROM assignments a JOIN bookings b ON b.id=a.booking_id "
        "WHERE a.employee_id=? AND b.book_date=? AND b.shift=? AND b.id<>?",
        (eid, bk["book_date"], bk["shift"], bid))
    if clash:
        raise ApiError("พนักงานคนนี้ถูกจองในวันและกะนี้แล้ว")
    db.execute("INSERT OR IGNORE INTO assignments(booking_id,employee_id,score,method,created_at) "
               "VALUES(?,?,?,?,?)", (bid, eid, 0, "manual", db.now()))
    filled = db.one("SELECT COUNT(*) AS c FROM assignments WHERE booking_id=?", (bid,))["c"]
    db.execute("UPDATE bookings SET status=? WHERE id=?",
               ("assigned" if filled >= bk["required_qty"] else "partial", bid))
    return {"ok": True, "filled": filled}


@route("DELETE", "/api/assignments/<aid>", role="leader")
def api_assignment_delete(ctx):
    aid = int(ctx.params["aid"])
    row = db.one("SELECT booking_id FROM assignments WHERE id=?", (aid,))
    db.execute("DELETE FROM assignments WHERE id=?", (aid,))
    if row:
        bk = db.one("SELECT * FROM bookings WHERE id=?", (row["booking_id"],))
        filled = db.one("SELECT COUNT(*) AS c FROM assignments WHERE booking_id=?",
                        (row["booking_id"],))["c"]
        db.execute("UPDATE bookings SET status=? WHERE id=?",
                   ("assigned" if bk and filled >= bk["required_qty"]
                    else ("partial" if filled else "pending"), row["booking_id"]))
    return {"ok": True}


# ------------------------------------------------------------------ tasks

@route("GET", "/api/tasks")
def api_tasks(ctx):
    where, args = [], []
    if ctx.arg("status"):
        where.append("t.status=?")
        args.append(ctx.arg("status"))
    if ctx.int_arg("assignee_id"):
        where.append("t.assignee_id=?")
        args.append(ctx.int_arg("assignee_id"))
    sql = ("SELECT t.*, l.code AS line_code, u.name AS assignee_name FROM tasks t "
           "LEFT JOIN lines l ON l.id=t.line_id LEFT JOIN users u ON u.id=t.assignee_id")
    if where:
        sql += " WHERE " + " AND ".join(where)
    return {"items": db.query(sql + " ORDER BY t.status='done', t.priority DESC, t.due_date", args)}


@route("POST", "/api/tasks", role="leader")
def api_task_create(ctx):
    b = ctx.body
    tid = db.execute(
        "INSERT INTO tasks(title,detail,line_id,assignee_id,priority,due_date,created_by,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (ctx.need("title"), b.get("detail") or "", b.get("line_id") or None,
         b.get("assignee_id") or None, int(b.get("priority") or 2),
         b.get("due_date") or db.today(), ctx.uid, db.now()))
    return {"ok": True, "id": tid}


@route("PUT", "/api/tasks/<tid>", role="operator")
def api_task_update(ctx):
    b = ctx.body
    tid = int(ctx.params["tid"])
    done_at = db.now() if b.get("status") == "done" else None
    db.execute("UPDATE tasks SET title=COALESCE(?,title), detail=COALESCE(?,detail), "
               "status=COALESCE(?,status), priority=COALESCE(?,priority), "
               "assignee_id=COALESCE(?,assignee_id), due_date=COALESCE(?,due_date), "
               "done_at=COALESCE(?,done_at) WHERE id=?",
               (b.get("title"), b.get("detail"), b.get("status"), b.get("priority"),
                b.get("assignee_id"), b.get("due_date"), done_at, tid))
    return {"ok": True}


@route("DELETE", "/api/tasks/<tid>", role="leader")
def api_task_delete(ctx):
    db.execute("DELETE FROM tasks WHERE id=?", (int(ctx.params["tid"]),))
    return {"ok": True}


# ----------------------------------------------------------------- alerts

@route("GET", "/api/alerts")
def api_alerts(ctx):
    return {"items": db.query(
        "SELECT a.*, l.code AS line_code, u.name AS ack_name FROM alerts a "
        "LEFT JOIN lines l ON l.id=a.line_id LEFT JOIN users u ON u.id=a.ack_by "
        "ORDER BY a.ack_at IS NOT NULL, a.id DESC LIMIT 100")}


@route("POST", "/api/alerts/refresh", role="operator")
def api_alerts_refresh(ctx):
    n = smart.refresh_alerts(_today(ctx), _shift(ctx))
    return {"ok": True, "created": n}


@route("POST", "/api/alerts/<aid>/ack", role="operator")
def api_alert_ack(ctx):
    db.execute("UPDATE alerts SET ack_by=?, ack_at=? WHERE id=?",
               (ctx.uid, db.now(), int(ctx.params["aid"])))
    return {"ok": True}


# ------------------------------------------------------------ smart tools

@route("GET", "/api/smart/forecast")
def api_smart_forecast(ctx):
    return {"items": smart.forecast(_today(ctx), _shift(ctx))}


@route("GET", "/api/smart/advisor")
def api_smart_advisor(ctx):
    return {"items": smart.advisor(_today(ctx), _shift(ctx))}


@route("GET", "/api/smart/anomaly")
def api_smart_anomaly(ctx):
    return {"items": smart.anomaly_scan(ctx.int_arg("days", 14))}


@route("GET", "/api/smart/bottleneck")
def api_smart_bottleneck(ctx):
    data = smart.bottleneck(_today(ctx), _shift(ctx))
    data["moves"] = smart.rebalance(_today(ctx), _shift(ctx))
    return data


@route("GET", "/api/smart/capacity")
def api_smart_capacity(ctx):
    return {"outlook": smart.capacity_outlook(ctx.int_arg("days", 7)),
            "manpower": smart.manpower_gap(_today(ctx), _shift(ctx)),
            "bottleneck": smart.bottleneck(_today(ctx), _shift(ctx))}


@route("GET", "/api/smart/pareto")
def api_smart_pareto(ctx):
    return {"items": smart.downtime_pareto(ctx.int_arg("days", 7))}


@route("GET", "/api/smart/oee")
def api_smart_oee(ctx):
    return smart.oee(_today(ctx), ctx.arg("shift"), ctx.int_arg("line_id"))


# ---------------------------------------------------------------- reports

@route("GET", "/api/reports/summary")
def api_report_summary(ctx):
    d_from = ctx.arg("from", (dt.date.today() - dt.timedelta(days=6)).isoformat())
    d_to = ctx.arg("to", db.today())
    by_day = db.query(
        "SELECT rec_date AS d, SUM(ok_qty) AS ok, SUM(ng_qty) AS ng, SUM(downtime_min) AS dtm "
        "FROM production WHERE rec_date BETWEEN ? AND ? GROUP BY rec_date ORDER BY rec_date",
        (d_from, d_to))
    plan_by_day = {r["d"]: r["t"] for r in db.query(
        "SELECT plan_date AS d, SUM(target_qty) AS t FROM plans WHERE plan_date BETWEEN ? AND ? "
        "GROUP BY plan_date", (d_from, d_to))}
    for r in by_day:
        r["target"] = plan_by_day.get(r["d"], 0)
        r["achievement"] = smart.pct(r["ok"], r["target"])
        r["yield"] = smart.pct(r["ok"], r["ok"] + r["ng"])
    by_line = db.query(
        "SELECT l.code, SUM(p.ok_qty) AS ok, SUM(p.ng_qty) AS ng, SUM(p.downtime_min) AS dtm "
        "FROM production p JOIN lines l ON l.id=p.line_id WHERE p.rec_date BETWEEN ? AND ? "
        "GROUP BY l.id ORDER BY ok DESC", (d_from, d_to))
    by_model = db.query(
        "SELECT m.code, m.name, SUM(p.ok_qty) AS ok, SUM(p.ng_qty) AS ng "
        "FROM production p JOIN models m ON m.id=p.model_id WHERE p.rec_date BETWEEN ? AND ? "
        "GROUP BY m.id ORDER BY ok DESC", (d_from, d_to))
    for r in by_line + by_model:
        r["yield"] = smart.pct(r["ok"], r["ok"] + r["ng"])
    total_ok = sum(r["ok"] for r in by_day)
    total_ng = sum(r["ng"] for r in by_day)
    return {
        "from": d_from, "to": d_to, "by_day": by_day, "by_line": by_line, "by_model": by_model,
        "pareto": smart.downtime_pareto(max((dt.date.fromisoformat(d_to) -
                                             dt.date.fromisoformat(d_from)).days, 1)),
        "totals": {"ok": total_ok, "ng": total_ng,
                   "target": sum(r["target"] for r in by_day),
                   "yield": smart.pct(total_ok, total_ok + total_ng),
                   "downtime": sum(r["dtm"] for r in by_day),
                   "achievement": smart.pct(total_ok, sum(r["target"] for r in by_day))},
    }


@route("GET", "/api/export/production.csv")
def api_export_production(ctx):
    d_from = ctx.arg("from", (dt.date.today() - dt.timedelta(days=6)).isoformat())
    d_to = ctx.arg("to", db.today())
    rows = db.query(
        "SELECT p.rec_date, p.shift, p.hour, l.code AS line_code, m.code AS model_code, "
        "p.ok_qty, p.ng_qty, p.downtime_min, p.downtime_reason, p.manpower "
        "FROM production p JOIN lines l ON l.id=p.line_id JOIN models m ON m.id=p.model_id "
        "WHERE p.rec_date BETWEEN ? AND ? ORDER BY p.rec_date, p.shift, l.code, p.hour",
        (d_from, d_to))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["วันที่", "กะ", "ชั่วโมง", "ไลน์", "รุ่น", "ยอดดี", "ของเสีย",
                     "เวลาหยุด(นาที)", "สาเหตุ", "กำลังคน"])
    for r in rows:
        writer.writerow([r["rec_date"], r["shift"], r["hour"], r["line_code"], r["model_code"],
                         r["ok_qty"], r["ng_qty"], r["downtime_min"], r["downtime_reason"],
                         r["manpower"]])
    return {"_raw": ("﻿" + buf.getvalue()).encode("utf-8"),
            "_content_type": "text/csv; charset=utf-8",
            "_filename": f"fgp-production-{d_from}-to-{d_to}.csv"}


# ------------------------------------------------------------------ users

@route("GET", "/api/users", role="admin")
def api_users(ctx):
    return {"items": db.query("SELECT id,username,name,role,emp_code,active,created_at "
                              "FROM users ORDER BY id")}


@route("POST", "/api/users", role="admin")
def api_user_create(ctx):
    b = ctx.body
    if db.one("SELECT id FROM users WHERE username=?", (b.get("username"),)):
        raise ApiError("มีชื่อผู้ใช้นี้อยู่แล้ว")
    pwd = str(ctx.need("password"))
    if len(pwd) < 6:
        raise ApiError("รหัสผ่านต้องยาวอย่างน้อย 6 ตัวอักษร")
    uid = db.execute(
        "INSERT INTO users(username,name,pwd,role,emp_code,created_at) VALUES(?,?,?,?,?,?)",
        (str(ctx.need("username")).strip(), ctx.need("name"), auth.hash_password(pwd),
         b.get("role") or "operator", b.get("emp_code") or "", db.now()))
    auth.log(ctx.uid, "user.create", str(uid))
    return {"ok": True, "id": uid}


@route("PUT", "/api/users/<uid>", role="admin")
def api_user_update(ctx):
    b = ctx.body
    uid = int(ctx.params["uid"])
    if b.get("password"):
        db.execute("UPDATE users SET pwd=? WHERE id=?", (auth.hash_password(b["password"]), uid))
    db.execute("UPDATE users SET name=COALESCE(?,name), role=COALESCE(?,role), "
               "active=COALESCE(?,active) WHERE id=?",
               (b.get("name"), b.get("role"), b.get("active"), uid))
    return {"ok": True}


@route("POST", "/api/me/password", role="viewer")
def api_change_password(ctx):
    if not auth.verify_password(str(ctx.need("current")), ctx.user["pwd"]):
        raise ApiError("รหัสผ่านเดิมไม่ถูกต้อง")
    new = str(ctx.need("password"))
    if len(new) < 6:
        raise ApiError("รหัสผ่านใหม่ต้องยาวอย่างน้อย 6 ตัวอักษร")
    db.execute("UPDATE users SET pwd=? WHERE id=?", (auth.hash_password(new), ctx.uid))
    return {"ok": True}


@route("GET", "/api/audit", role="manager")
def api_audit(ctx):
    return {"items": db.query(
        "SELECT a.*, u.name FROM audit a LEFT JOIN users u ON u.id=a.user_id "
        "ORDER BY a.id DESC LIMIT 200")}

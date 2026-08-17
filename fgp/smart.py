"""FGP Intelligence — เครื่องมือวิเคราะห์อัจฉริยะของระบบ

ทุกฟังก์ชันคำนวณจากข้อมูลจริงใน SQLite ด้วย Python มาตรฐาน ไม่ต้องต่อเน็ต
ไม่ต้องลง library เพิ่ม และอธิบายเหตุผลของทุกคำแนะนำได้เสมอ
"""

from __future__ import annotations

import datetime as dt
import statistics as stats

from . import db

SHIFT_HOURS = db.SHIFT_HOURS
SHIFT_MINUTES = SHIFT_HOURS * 60


# ------------------------------------------------------------------ helpers

def _f(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def pct(part: float, whole: float) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def current_shift() -> str:
    """กะ A 08:00-19:59 / กะ B 20:00-07:59"""
    return "A" if 8 <= dt.datetime.now().hour < 20 else "B"


def elapsed_hours(date_str: str, shift: str) -> int:
    """ชั่วโมงที่เดินไปแล้วของกะนั้น (1..8) ใช้ประเมินความคืบหน้า"""
    if date_str != db.today():
        return SHIFT_HOURS
    h = dt.datetime.now().hour
    passed = (h - 8) if shift == "A" else ((h - 20) % 24)
    return int(clamp(passed + 1, 0, SHIFT_HOURS))


# --------------------------------------------------------------------- OEE

def oee(date_str: str, shift: str | None = None, line_id: int | None = None) -> dict:
    """OEE = Availability x Performance x Quality ตามสูตร Nakajima"""
    where = ["p.rec_date = ?"]
    args: list = [date_str]
    if shift:
        where.append("p.shift = ?")
        args.append(shift)
    if line_id:
        where.append("p.line_id = ?")
        args.append(line_id)
    rows = db.query(
        "SELECT p.*, m.cycle_sec FROM production p JOIN models m ON m.id=p.model_id "
        f"WHERE {' AND '.join(where)}", args)
    if not rows:
        return {"oee": 0.0, "availability": 0.0, "performance": 0.0, "quality": 0.0,
                "ok": 0, "ng": 0, "downtime": 0, "records": 0}

    planned_min = len(rows) * 60.0
    downtime = sum(_f(r["downtime_min"]) for r in rows)
    run_min = max(planned_min - downtime, 1.0)
    ok = sum(int(r["ok_qty"]) for r in rows)
    ng = sum(int(r["ng_qty"]) for r in rows)
    ideal_sec = sum(int(r["ok_qty"]) * _f(r["cycle_sec"], 30) for r in rows)

    availability = clamp(run_min / planned_min * 100, 0, 100)
    performance = clamp(ideal_sec / 60.0 / run_min * 100, 0, 130)
    quality = pct(ok, ok + ng) if (ok + ng) else 0.0
    return {
        "oee": round(availability * performance * quality / 10000, 1),
        "availability": round(availability, 1),
        "performance": round(performance, 1),
        "quality": round(quality, 1),
        "ok": ok, "ng": ng, "downtime": int(downtime), "records": len(rows),
    }


# ---------------------------------------------------------------- forecast

def forecast(date_str: str, shift: str) -> list[dict]:
    """พยากรณ์ยอดจบกะรายไลน์

    ใช้ค่าเฉลี่ยถ่วงน้ำหนัก: ชั่วโมงล่าสุดมีน้ำหนักมากกว่า (weight = i+1)
    แล้วปรับด้วยแนวโน้ม (trend) จากผลต่างครึ่งแรก/ครึ่งหลังของกะ
    """
    plans = db.query(
        "SELECT pl.*, l.code AS line_code, l.name AS line_name, m.code AS model_code, "
        "m.cycle_sec FROM plans pl JOIN lines l ON l.id=pl.line_id "
        "JOIN models m ON m.id=pl.model_id WHERE pl.plan_date=? AND pl.shift=? ORDER BY l.code",
        (date_str, shift))
    elapsed = elapsed_hours(date_str, shift)
    out = []
    for p in plans:
        recs = db.query(
            "SELECT hour, ok_qty, ng_qty, downtime_min FROM production "
            "WHERE rec_date=? AND shift=? AND line_id=? ORDER BY hour",
            (date_str, shift, p["line_id"]))
        actual = sum(r["ok_qty"] for r in recs)
        ng = sum(r["ng_qty"] for r in recs)
        target = int(p["target_qty"])
        remain_h = max(SHIFT_HOURS - len(recs), 0)

        if recs:
            weights = list(range(1, len(recs) + 1))
            wavg = sum(r["ok_qty"] * w for r, w in zip(recs, weights)) / sum(weights)
            half = max(len(recs) // 2, 1)
            trend = (stats.fmean([r["ok_qty"] for r in recs[half:]]) -
                     stats.fmean([r["ok_qty"] for r in recs[:half]])) if len(recs) >= 4 else 0.0
            rate = max(wavg + trend * 0.35, 0.0)
        else:
            wavg = rate = trend = target / SHIFT_HOURS
            trend = 0.0
        projected = int(actual + rate * remain_h)
        gap = projected - target
        achieve = pct(projected, target)

        # ความมั่นใจ: ข้อมูลยิ่งเยอะ + ยิ่งนิ่ง ยิ่งมั่นใจ
        if len(recs) >= 2:
            spread = stats.pstdev([r["ok_qty"] for r in recs]) / max(wavg, 1)
            confidence = int(clamp(55 + len(recs) * 5 - spread * 90, 35, 96))
        else:
            confidence = 40

        risk = "green"
        if achieve < 92:
            risk = "red"
        elif achieve < 99:
            risk = "amber"

        out.append({
            "line_id": p["line_id"], "line_code": p["line_code"], "line_name": p["line_name"],
            "model_code": p["model_code"], "target": target, "actual": actual, "ng": ng,
            "hours_done": len(recs), "hours_left": remain_h, "elapsed": elapsed,
            "rate_per_hour": round(rate, 1), "trend": round(trend, 1),
            "projected": projected, "gap": gap, "achievement": achieve,
            "confidence": confidence, "risk": risk,
            "need_rate": round(max(target - actual, 0) / remain_h, 1) if remain_h else 0.0,
        })
    return out


# --------------------------------------------------------------- anomalies

def anomaly_scan(days: int = 14) -> list[dict]:
    """ตรวจจับความผิดปกติด้วย z-score (NG rate, downtime, ยอดตก)"""
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    rows = db.query(
        "SELECT p.*, l.code AS line_code FROM production p JOIN lines l ON l.id=p.line_id "
        "WHERE p.rec_date >= ? ORDER BY p.rec_date, p.hour", (since,))
    if len(rows) < 20:
        return []

    by_line: dict[int, list[dict]] = {}
    for r in rows:
        by_line.setdefault(r["line_id"], []).append(r)

    found = []
    recent_cut = (dt.date.today() - dt.timedelta(days=2)).isoformat()
    for lid, recs in by_line.items():
        ng_rates = [r["ng_qty"] / max(r["ok_qty"] + r["ng_qty"], 1) * 100 for r in recs]
        outs = [r["ok_qty"] for r in recs]
        dts = [r["downtime_min"] for r in recs]
        if len(recs) < 12:
            continue
        mu_ng, sd_ng = stats.fmean(ng_rates), stats.pstdev(ng_rates) or 0.001
        mu_ok, sd_ok = stats.fmean(outs), stats.pstdev(outs) or 0.001
        mu_dt, sd_dt = stats.fmean(dts), stats.pstdev(dts) or 0.001
        for r, ngr in zip(recs, ng_rates):
            if r["rec_date"] < recent_cut:
                continue
            z_ng = (ngr - mu_ng) / sd_ng
            z_ok = (r["ok_qty"] - mu_ok) / sd_ok
            z_dt = (r["downtime_min"] - mu_dt) / sd_dt
            if z_ng >= 2.2 and ngr > 1.5:
                found.append(_anom(r, "quality", "NG สูงผิดปกติ",
                                   f"ของเสีย {ngr:.1f}% สูงกว่าค่าปกติของไลน์ ({mu_ng:.1f}%) "
                                   f"อยู่ {z_ng:.1f} เท่าของส่วนเบี่ยงเบน", z_ng))
            if z_ok <= -2.0:
                found.append(_anom(r, "output", "ยอดผลิตตกผิดปกติ",
                                   f"ได้ {r['ok_qty']} ชิ้น ต่ำกว่าค่าเฉลี่ย {mu_ok:.0f} ชิ้น/ชม.", abs(z_ok)))
            if z_dt >= 2.2 and r["downtime_min"] >= 15:
                found.append(_anom(r, "downtime", "เครื่องหยุดนานผิดปกติ",
                                   f"หยุด {r['downtime_min']} นาที ({r['downtime_reason'] or 'ไม่ระบุสาเหตุ'})", z_dt))
    found.sort(key=lambda x: (-x["score"], x["date"]))
    return found[:40]


def _anom(r, kind, title, detail, score) -> dict:
    return {"kind": kind, "title": title, "detail": detail,
            "line_id": r["line_id"], "line_code": r["line_code"], "date": r["rec_date"],
            "shift": r["shift"], "hour": r["hour"], "score": round(float(score), 2),
            "severity": "high" if score >= 3 else "medium"}


# -------------------------------------------------------------- bottleneck

def bottleneck(date_str: str, shift: str) -> dict:
    """หาไลน์คอขวด: เทียบภาระงาน (นาทีที่ต้องใช้) กับเวลาที่มีจริง"""
    plans = db.query(
        "SELECT pl.*, l.code AS line_code, l.name AS line_name, l.std_manpower, "
        "m.code AS model_code, m.cycle_sec FROM plans pl JOIN lines l ON l.id=pl.line_id "
        "JOIN models m ON m.id=pl.model_id WHERE pl.plan_date=? AND pl.shift=?",
        (date_str, shift))
    items = []
    for p in plans:
        load_min = p["target_qty"] * _f(p["cycle_sec"], 30) / 60.0
        dtm = db.one("SELECT COALESCE(SUM(downtime_min),0) AS d FROM production "
                     "WHERE rec_date=? AND shift=? AND line_id=?",
                     (date_str, shift, p["line_id"]))["d"]
        avail_min = SHIFT_MINUTES - _f(dtm)
        util = pct(load_min, avail_min)
        items.append({
            "line_id": p["line_id"], "line_code": p["line_code"], "line_name": p["line_name"],
            "model_code": p["model_code"], "target": p["target_qty"],
            "load_min": round(load_min), "available_min": round(avail_min),
            "downtime_min": int(_f(dtm)), "utilization": util,
            "headroom": round(avail_min - load_min),
            "status": "overload" if util > 100 else ("tight" if util > 92 else "ok"),
        })
    items.sort(key=lambda x: -x["utilization"])
    return {
        "items": items,
        "constraint": items[0] if items else None,
        "overloaded": [i for i in items if i["status"] == "overload"],
        "spare": [i for i in items if i["utilization"] < 85],
    }


def rebalance(date_str: str, shift: str) -> list[dict]:
    """ข้อเสนอย้ายยอดจากไลน์ที่ล้นไปไลน์ที่ยังว่าง"""
    b = bottleneck(date_str, shift)
    moves = []
    spare = sorted(b["spare"], key=lambda x: x["utilization"])
    for over in b["overloaded"]:
        excess_min = over["load_min"] - over["available_min"]
        for sp in spare:
            if excess_min <= 0 or sp["headroom"] <= 10:
                continue
            take = min(excess_min, sp["headroom"] * 0.8)
            cyc = max(over["load_min"] * 60 / max(over["target"], 1), 1)
            qty = int(take * 60 / cyc)
            if qty < 5:
                continue
            moves.append({
                "from": over["line_code"], "to": sp["line_code"], "qty": qty,
                "model_code": over["model_code"],
                "reason": f"{over['line_code']} โหลด {over['utilization']}% เกินกำลัง "
                          f"ส่วน {sp['line_code']} ใช้เพียง {sp['utilization']}%",
            })
            excess_min -= take
            sp["headroom"] -= take
    return moves


# ------------------------------------------------- manpower auto allocation

def _employee_pool(date_str: str, shift: str, exclude_booking: int | None = None) -> set[int]:
    """คนที่ถูกจองไปแล้วในวัน/กะเดียวกัน"""
    rows = db.query(
        "SELECT a.employee_id FROM assignments a JOIN bookings b ON b.id=a.booking_id "
        "WHERE b.book_date=? AND b.shift=?" + (" AND b.id<>?" if exclude_booking else ""),
        (date_str, shift, exclude_booking) if exclude_booking else (date_str, shift))
    return {r["employee_id"] for r in rows}


def suggest_people(booking_id: int, limit: int | None = None) -> list[dict]:
    """จัดคนเข้าคิวจองแบบอัจฉริยะ

    คะแนน = ทักษะตรงไลน์ (0-40) + ตรงกะ (0-20) + ความว่าง (0-20)
            + ความเป็นธรรมของภาระงาน (0-12) + ประสบการณ์ตำแหน่ง (0-8)
    """
    bk = db.one("SELECT b.*, l.code AS line_code FROM bookings b JOIN lines l ON l.id=b.line_id "
                "WHERE b.id=?", (booking_id,))
    if not bk:
        return []
    busy = _employee_pool(bk["book_date"], bk["shift"], exclude_booking=booking_id)
    since = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    load = {r["employee_id"]: r["c"] for r in db.query(
        "SELECT a.employee_id, COUNT(*) AS c FROM assignments a JOIN bookings b ON b.id=a.booking_id "
        "WHERE b.book_date >= ? GROUP BY a.employee_id", (since,))}
    max_load = max(load.values()) if load else 1

    emps = db.query(
        "SELECT e.*, COALESCE(s.level,0) AS level FROM employees e "
        "LEFT JOIN skills s ON s.employee_id=e.id AND s.line_id=? WHERE e.active=1",
        (bk["line_id"],))
    ranked = []
    for e in emps:
        if e["id"] in busy:
            continue
        if e["level"] < bk["skill_min"]:
            continue
        reasons = []
        score = e["level"] * 10.0
        reasons.append(f"ทักษะไลน์ {bk['line_code']} ระดับ {e['level']}/4")
        if e["shift"] == bk["shift"]:
            score += 20
            reasons.append(f"อยู่กะ {e['shift']} ตรงกับงาน")
        else:
            score += 4
            reasons.append(f"ปกติอยู่กะ {e['shift']} ต้องสลับกะ")
        score += 20
        if e["position"] in ("Leader", "Senior Operator"):
            score += 8
            reasons.append(f"ตำแหน่ง {e['position']}")
        fairness = 12 * (1 - load.get(e["id"], 0) / max(max_load, 1))
        score += fairness
        if load.get(e["id"], 0) == 0:
            reasons.append("ยังไม่ถูกจองในรอบ 30 วัน")
        ranked.append({
            "employee_id": e["id"], "emp_code": e["emp_code"], "name": e["name"],
            "position": e["position"], "shift": e["shift"], "level": e["level"],
            "recent_bookings": load.get(e["id"], 0),
            "score": round(min(score, 100), 1), "reasons": reasons,
        })
    ranked.sort(key=lambda x: (-x["score"], x["recent_bookings"], x["emp_code"]))
    return ranked[:limit] if limit else ranked


def auto_assign(booking_id: int) -> dict:
    """เลือกคนอันดับต้นตามจำนวนที่ขอ แล้วบันทึกลงระบบ"""
    bk = db.one("SELECT * FROM bookings WHERE id=?", (booking_id,))
    if not bk:
        return {"ok": False, "error": "ไม่พบคิวจองนี้"}
    already = db.query("SELECT employee_id FROM assignments WHERE booking_id=?", (booking_id,))
    need = int(bk["required_qty"]) - len(already)
    if need <= 0:
        return {"ok": True, "assigned": [], "message": "จัดคนครบตามจำนวนแล้ว"}
    picks = [p for p in suggest_people(booking_id)
             if p["employee_id"] not in {a["employee_id"] for a in already}][:need]
    ts = db.now()
    for p in picks:
        db.execute("INSERT OR IGNORE INTO assignments(booking_id,employee_id,score,method,created_at) "
                   "VALUES(?,?,?,?,?)", (booking_id, p["employee_id"], p["score"], "auto", ts))
    status = "assigned" if len(already) + len(picks) >= bk["required_qty"] else "partial"
    db.execute("UPDATE bookings SET status=? WHERE id=?", (status, booking_id))
    return {"ok": True, "assigned": picks, "status": status,
            "message": f"จัดคนอัตโนมัติ {len(picks)} คน จากที่ขอ {bk['required_qty']} คน"}


def manpower_gap(date_str: str, shift: str) -> dict:
    """เทียบคนที่ต้องใช้ตามมาตรฐานไลน์ กับคนที่มีในกะ"""
    plans = db.query(
        "SELECT pl.line_id, l.code AS line_code, l.std_manpower, m.std_manpower AS model_mp "
        "FROM plans pl JOIN lines l ON l.id=pl.line_id JOIN models m ON m.id=pl.model_id "
        "WHERE pl.plan_date=? AND pl.shift=?", (date_str, shift))
    available = db.one("SELECT COUNT(*) AS c FROM employees WHERE active=1 AND shift=?",
                       (shift,))["c"]
    required = sum(max(p["std_manpower"], p["model_mp"]) for p in plans)
    booked = db.one(
        "SELECT COALESCE(SUM(required_qty),0) AS c FROM bookings "
        "WHERE book_date=? AND shift=? AND status<>'rejected'", (date_str, shift))["c"]
    return {
        "required": required, "available": available, "booked": booked,
        "gap": available - required,
        "coverage": pct(available, required) if required else 100.0,
        "lines": len(plans),
    }


# ------------------------------------------------------------ advisor / KPI

def downtime_pareto(days: int = 7) -> list[dict]:
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    rows = db.query(
        "SELECT downtime_reason AS reason, SUM(downtime_min) AS minutes, COUNT(*) AS times "
        "FROM production WHERE rec_date >= ? AND downtime_min > 0 AND downtime_reason <> '' "
        "GROUP BY downtime_reason ORDER BY minutes DESC", (since,))
    total = sum(r["minutes"] for r in rows) or 1
    acc = 0.0
    for r in rows:
        acc += r["minutes"]
        r["share"] = pct(r["minutes"], total)
        r["cumulative"] = pct(acc, total)
    return rows


def advisor(date_str: str, shift: str) -> list[dict]:
    """รวมทุกสัญญาณเป็นคำแนะนำที่ลงมือทำได้ พร้อมเหตุผลกำกับ"""
    tips: list[dict] = []
    fc = forecast(date_str, shift)

    for f in fc:
        if f["risk"] == "red" and f["hours_left"] > 0:
            tips.append({
                "severity": "high", "icon": "alert", "line": f["line_code"],
                "title": f"{f['line_code']} เสี่ยงไม่ถึงเป้า {f['achievement']}%",
                "detail": f"ตอนนี้ทำได้ {f['rate_per_hour']:.0f} ชิ้น/ชม. "
                          f"แต่ต้องได้ {f['need_rate']:.0f} ชิ้น/ชม. ในอีก {f['hours_left']} ชั่วโมง",
                "action": "เพิ่มคน 1-2 คน หรือขอ OT ต่อท้ายกะ",
            })
        elif f["risk"] == "amber" and f["hours_left"] > 0:
            tips.append({
                "severity": "medium", "icon": "watch", "line": f["line_code"],
                "title": f"{f['line_code']} จบกะประมาณ {f['achievement']}% ของเป้า",
                "detail": f"ขาดอีก {abs(min(f['gap'], 0))} ชิ้น ถ้าอัตราคงเดิม",
                "action": "เฝ้าดูอีก 1 ชั่วโมง ถ้าไม่ขึ้นให้เสริมกำลัง",
            })
        if f["trend"] <= -8 and f["hours_done"] >= 4:
            tips.append({
                "severity": "medium", "icon": "trend", "line": f["line_code"],
                "title": f"{f['line_code']} อัตราผลิตกำลังลดลง",
                "detail": f"ครึ่งหลังของกะช้าลง {abs(f['trend']):.0f} ชิ้น/ชม. เทียบครึ่งแรก",
                "action": "เช็คความล้าของพนักงาน สลับตำแหน่ง หรือตรวจเครื่องจักร",
            })

    bn = bottleneck(date_str, shift)
    for o in bn["overloaded"]:
        tips.append({
            "severity": "high", "icon": "capacity", "line": o["line_code"],
            "title": f"{o['line_code']} รับงานเกินกำลัง {o['utilization']}%",
            "detail": f"ต้องใช้ {o['load_min']} นาที แต่มีเวลาจริง {o['available_min']} นาที",
            "action": "ย้ายยอดบางส่วนไปไลน์ที่ว่าง หรือเพิ่มกะ",
        })
    for mv in rebalance(date_str, shift)[:3]:
        tips.append({
            "severity": "medium", "icon": "shuffle", "line": mv["from"],
            "title": f"ย้าย {mv['qty']} ชิ้น จาก {mv['from']} ไป {mv['to']}",
            "detail": mv["reason"], "action": "ปรับแผนแล้วแจ้ง leader ทั้งสองไลน์",
        })

    mg = manpower_gap(date_str, shift)
    if mg["gap"] < 0:
        tips.append({
            "severity": "high", "icon": "people", "line": "-",
            "title": f"กำลังคนกะ {shift} ขาด {abs(mg['gap'])} คน",
            "detail": f"ต้องใช้ {mg['required']} คน มีจริง {mg['available']} คน "
                      f"(ครอบคลุม {mg['coverage']}%)",
            "action": "เปิดคิวจองคนจากกะอื่น หรือจัดลำดับความสำคัญของแผน",
        })

    for a in anomaly_scan(10)[:4]:
        tips.append({
            "severity": "high" if a["severity"] == "high" else "medium",
            "icon": "anomaly", "line": a["line_code"],
            "title": f"{a['line_code']}: {a['title']}",
            "detail": f"{a['detail']} (วันที่ {a['date']} กะ {a['shift']} ชม.ที่ {a['hour']})",
            "action": "ให้ leader ตรวจหน้างานและบันทึกสาเหตุ",
        })

    par = downtime_pareto(7)
    if par and par[0]["share"] >= 30:
        tips.append({
            "severity": "medium", "icon": "stop", "line": "-",
            "title": f"สาเหตุหยุดเครื่องอันดับ 1: {par[0]['reason']}",
            "detail": f"กิน {par[0]['minutes']} นาทีใน 7 วัน คิดเป็น {par[0]['share']}% ของเวลาหยุดทั้งหมด",
            "action": "ตั้งทีมแก้ปัญหาเฉพาะเรื่องนี้ ลดได้มากที่สุดต่อแรงที่ลง",
        })

    o = oee(date_str, shift)
    if o["records"] and o["oee"] < 65:
        weakest = min(("availability", o["availability"]), ("performance", o["performance"]),
                      ("quality", o["quality"]), key=lambda x: x[1])
        label = {"availability": "เวลาเดินเครื่อง", "performance": "ความเร็วการผลิต",
                 "quality": "คุณภาพ"}[weakest[0]]
        tips.append({
            "severity": "medium", "icon": "oee", "line": "-",
            "title": f"OEE วันนี้ {o['oee']}% ต่ำกว่าเกณฑ์ 65%",
            "detail": f"ตัวฉุดหลักคือ{label} ที่ {weakest[1]}%",
            "action": f"โฟกัสแก้{label}ก่อน จะดัน OEE ขึ้นเร็วที่สุด",
        })

    rank = {"high": 0, "medium": 1, "low": 2}
    tips.sort(key=lambda t: rank.get(t["severity"], 3))
    return tips


def refresh_alerts(date_str: str, shift: str) -> int:
    """เขียนคำเตือนระดับสูงลงตาราง alerts (กันซ้ำภายในวันเดียวกัน)"""
    created = 0
    for t in advisor(date_str, shift):
        if t["severity"] != "high":
            continue
        dup = db.one("SELECT id FROM alerts WHERE title=? AND ref_date=?", (t["title"], date_str))
        if dup:
            continue
        line = db.one("SELECT id FROM lines WHERE code=?", (t["line"],))
        db.execute(
            "INSERT INTO alerts(kind,severity,title,detail,line_id,ref_date,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (t["icon"], t["severity"], t["title"], f"{t['detail']} | แนะนำ: {t['action']}",
             line["id"] if line else None, date_str, db.now()))
        created += 1
    return created


# ------------------------------------------------------------------ trends

def daily_trend(days: int = 14) -> list[dict]:
    since = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
    prod = db.query(
        "SELECT rec_date AS d, SUM(ok_qty) AS ok, SUM(ng_qty) AS ng, SUM(downtime_min) AS dtm "
        "FROM production WHERE rec_date >= ? GROUP BY rec_date ORDER BY rec_date", (since,))
    plan = {r["d"]: r["t"] for r in db.query(
        "SELECT plan_date AS d, SUM(target_qty) AS t FROM plans WHERE plan_date >= ? "
        "GROUP BY plan_date", (since,))}
    for r in prod:
        r["target"] = plan.get(r["d"], 0)
        r["achievement"] = pct(r["ok"], r["target"])
        r["yield"] = pct(r["ok"], r["ok"] + r["ng"])
    return prod


def line_ranking(date_str: str) -> list[dict]:
    rows = db.query(
        "SELECT l.id, l.code, l.name, COALESCE(SUM(p.ok_qty),0) AS ok, "
        "COALESCE(SUM(p.ng_qty),0) AS ng, COALESCE(SUM(p.downtime_min),0) AS dtm "
        "FROM lines l LEFT JOIN production p ON p.line_id=l.id AND p.rec_date=? "
        "WHERE l.active=1 GROUP BY l.id ORDER BY ok DESC", (date_str,))
    targets = {r["line_id"]: r["t"] for r in db.query(
        "SELECT line_id, SUM(target_qty) AS t FROM plans WHERE plan_date=? GROUP BY line_id",
        (date_str,))}
    for r in rows:
        r["target"] = targets.get(r["id"], 0)
        r["achievement"] = pct(r["ok"], r["target"])
        r["yield"] = pct(r["ok"], r["ok"] + r["ng"])
        o = oee(date_str, None, r["id"])
        r["oee"] = o["oee"]
    return rows


def hourly_curve(date_str: str, shift: str) -> list[dict]:
    rows = db.query(
        "SELECT hour, SUM(ok_qty) AS ok, SUM(ng_qty) AS ng, SUM(downtime_min) AS dtm "
        "FROM production WHERE rec_date=? AND shift=? GROUP BY hour ORDER BY hour",
        (date_str, shift))
    total_target = db.one("SELECT COALESCE(SUM(target_qty),0) AS t FROM plans "
                          "WHERE plan_date=? AND shift=?", (date_str, shift))["t"]
    per_hour = total_target / SHIFT_HOURS if total_target else 0
    acc = 0
    for r in rows:
        acc += r["ok"]
        r["cumulative"] = acc
        r["target_hour"] = round(per_hour)
        r["target_cumulative"] = round(per_hour * r["hour"])
    return rows


def capacity_outlook(days: int = 7) -> list[dict]:
    """กำลังผลิตล่วงหน้า: ความต้องการเทียบกับกำลังที่มี รายวัน"""
    out = []
    for d in range(days):
        day = (dt.date.today() + dt.timedelta(days=d)).isoformat()
        rows = db.query(
            "SELECT pl.shift, pl.target_qty, m.cycle_sec, l.id AS line_id "
            "FROM plans pl JOIN models m ON m.id=pl.model_id JOIN lines l ON l.id=pl.line_id "
            "WHERE pl.plan_date=?", (day,))
        lines = db.one("SELECT COUNT(*) AS c FROM lines WHERE active=1")["c"]
        demand_min = sum(r["target_qty"] * _f(r["cycle_sec"], 30) / 60 for r in rows)
        shifts = len({r["shift"] for r in rows}) or 1
        capacity_min = lines * SHIFT_MINUTES * shifts
        out.append({
            "date": day,
            "weekday": ["จ", "อ", "พ", "พฤ", "ศ", "ส", "อา"][dt.date.fromisoformat(day).weekday()],
            "demand_min": round(demand_min), "capacity_min": capacity_min,
            "utilization": pct(demand_min, capacity_min),
            "target_qty": sum(r["target_qty"] for r in rows),
            "shifts": shifts,
        })
    return out

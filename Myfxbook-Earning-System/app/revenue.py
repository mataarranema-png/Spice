"""
Myfxbook Earning System - เครื่องหาเงินที่ตกหล่น

ไฟล์นี้ไม่ได้บอกว่าควรเทรดอะไร และไม่ได้สัญญาว่าจะทำกำไรได้เท่าไร
สิ่งที่ทำคือคำนวณจากข้อมูลจริงในระบบว่า ตอนนี้มีเงินที่ควรได้แต่ยังไม่ได้อยู่ตรงไหนบ้าง

ห้าแหล่งที่ระบบหาให้
    1. เงินค้างเก็บ            คิดส่วนแบ่งแล้วแต่ยังไม่ได้เก็บ แยกตามอายุหนี้
    2. เพดานที่ตั้งต่ำไป       ทุกหนึ่งเปอร์เซ็นต์ของส่วนแบ่งมีค่าเท่าไรต่อเดือน
    3. รอบเก็บเงิน             เก็บรายสัปดาห์กับรายเดือน ย้อนหลังจริงต่างกันเท่าไร
    4. เงื่อนไขที่กินรายได้     ขั้นต่ำที่ตั้งไว้ทำให้เสียรายได้ไปเท่าไร
    5. พอร์ตที่ไม่คุ้มแบก       พอร์ตที่ไม่เคยสร้างรายได้แต่ยังกินความเสี่ยงชื่อเสียง

ข้อสำคัญที่ต้องเข้าใจก่อนใช้
    อัตราส่วนแบ่งและรอบเก็บเงินเป็นเงื่อนไขในสัญญา ไม่ใช่ปุ่มที่กดเปลี่ยนเองได้
    ตัวเลขในหน้านี้มีไว้ใช้เป็นข้อมูลประกอบการเจรจากับเจ้าของเงิน
    การเปลี่ยนโดยไม่บอกเจ้าของเงินคือการผิดสัญญา
"""

from datetime import date, datetime

from . import earnings
from .database import connect, fx_map, get_settings, to_base

# ช่วงอายุหนี้ที่ใช้จัดกลุ่มเงินค้างเก็บ หน่วยเป็นวันนับจากวันสิ้นรอบ
AGING_BUCKETS = [
    (0, 30, "ไม่เกิน 30 วัน"),
    (31, 60, "31 ถึง 60 วัน"),
    (61, 90, "61 ถึง 90 วัน"),
    (91, 10 ** 6, "เกิน 90 วัน"),
]


def _ctx(conn):
    settings = get_settings(conn)
    rates = fx_map(conn)
    base = (settings.get("base_currency") or "USD").upper()
    kind = settings.get("period_kind") or earnings.MONTH
    return settings, rates, base, kind


def _days_since(day):
    try:
        return (date.today() - datetime.strptime(day, "%Y-%m-%d").date()).days
    except (TypeError, ValueError):
        return 0


def _months_covered(conn, account_id):
    """จำนวนเดือนที่มีข้อมูลจริงของพอร์ตนี้ ใช้เฉลี่ยรายได้ต่อเดือน"""
    row = conn.execute(
        "SELECT MIN(day) a, MAX(day) b FROM daily WHERE account_id = ?", (account_id,)
    ).fetchone()
    if not row or not row["a"]:
        return 0.0
    span = _days_since(row["a"]) - _days_since(row["b"])
    return max(span / 30.44, 0.0)


# ============================================================ 1. เงินค้างเก็บ

def receivables(conn):
    """เงินที่คิดส่วนแบ่งไว้แล้วแต่ยังไม่ได้เก็บ แยกตามอายุนับจากวันสิ้นรอบ"""
    settings, rates, base, kind = _ctx(conn)

    paid = {}
    for r in conn.execute(
        "SELECT account_id, period_key, COALESCE(SUM(amount), 0) v "
        "FROM payouts GROUP BY account_id, period_key"
    ).fetchall():
        paid[(r["account_id"], r["period_key"])] = float(r["v"])

    items = []
    for r in conn.execute(
        """SELECT k.*, a.name FROM accruals k JOIN accounts a ON a.id = k.account_id
           WHERE k.earning > 0 ORDER BY k.end_day"""
    ).fetchall():
        outstanding = float(r["earning"]) - paid.get((r["account_id"], r["period_key"]), 0.0)
        if outstanding <= 0.009:
            continue
        age = max(0, _days_since(r["end_day"]))
        bucket = next(label for lo, hi, label in AGING_BUCKETS if lo <= age <= hi)
        items.append({
            "account_id": r["account_id"],
            "name": r["name"],
            "period_key": r["period_key"],
            "period_label": earnings.period_label(r["period_key"]),
            "end_day": r["end_day"],
            "currency": r["currency"],
            "outstanding": round(outstanding, 2),
            "outstanding_base": to_base(outstanding, r["currency"], rates, base),
            "age_days": age,
            "bucket": bucket,
        })

    buckets = []
    for lo, hi, label in AGING_BUCKETS:
        group = [i for i in items if i["bucket"] == label]
        buckets.append({
            "label": label,
            "count": len(group),
            "total": round(sum(i["outstanding_base"] for i in group), 2),
        })

    items.sort(key=lambda i: i["outstanding_base"], reverse=True)
    overdue = [i for i in items if i["age_days"] > 30]
    return {
        "items": items,
        "buckets": buckets,
        "total": round(sum(i["outstanding_base"] for i in items), 2),
        "overdue_total": round(sum(i["outstanding_base"] for i in overdue), 2),
        "overdue_count": len(overdue),
        "oldest_days": max([i["age_days"] for i in items], default=0),
    }


# ================================================= 2-4. ทดลองเปลี่ยนเงื่อนไข

def _total_earning(conn, kind, override=None, only_account=None):
    """
    รวมรายได้ย้อนหลังทั้งหมดในสกุลกลาง โดยจำลองด้วยเงื่อนไขที่กำหนด

    override เป็น dict ที่ทับค่าในเงื่อนไขจริง เช่น {"share_pct": 35} หรือ {"use_hwm": False}
    ใช้ earnings.simulate ตัวเดียวกับการคิดเงินจริง ตัวเลขจึงเทียบกันได้ตรง ๆ
    """
    settings, rates, base, _ = _ctx(conn)
    total = 0.0
    rows = conn.execute(
        "SELECT id, currency FROM accounts WHERE tracked = 1"
        + (" AND id = ?" if only_account else ""),
        (only_account,) if only_account else (),
    ).fetchall()
    for acc in rows:
        rule = earnings.rule_of(conn, acc["id"])
        if override:
            rule.update(override)
        periods = earnings.simulate(earnings.daily_rows(conn, acc["id"]), kind, **rule)
        earned = sum(p["earning"] for p in periods)
        total += to_base(earned, acc["currency"], rates, base)
    return round(total, 2)


def pricing_power(conn):
    """
    ทุกหนึ่งเปอร์เซ็นต์ของส่วนแบ่งมีค่าเท่าไร

    รายได้เป็นสัดส่วนตรงกับอัตราส่วนแบ่ง การบวกหนึ่งเปอร์เซ็นต์จึงคิดได้ตรงไปตรงมา
    ตัวเลขนี้มีไว้ตอบคำถามว่า ควรเสียเวลาเจรจาขอปรับอัตราหรือไม่
    """
    settings, rates, base, kind = _ctx(conn)
    out = []
    for acc in conn.execute(
        "SELECT id, name, currency FROM accounts WHERE tracked = 1 ORDER BY name"
    ).fetchall():
        rule = earnings.rule_of(conn, acc["id"])
        if not rule["active"] or rule["share_pct"] <= 0:
            continue
        current = _total_earning(conn, kind, only_account=acc["id"])
        plus_one = _total_earning(conn, kind, {"share_pct": rule["share_pct"] + 1},
                                  only_account=acc["id"])
        months = _months_covered(conn, acc["id"])
        per_point = round(plus_one - current, 2)
        out.append({
            "account_id": acc["id"],
            "name": acc["name"],
            "share_pct": rule["share_pct"],
            "history_total": current,
            "per_point": per_point,
            "per_point_monthly": round(per_point / months, 2) if months >= 1 else None,
            "months": round(months, 1),
        })
    out.sort(key=lambda x: x["per_point"], reverse=True)
    return out


def billing_period_compare(conn):
    """
    เก็บเงินรายสัปดาห์กับรายเดือน ย้อนหลังจริงต่างกันเท่าไร

    รอบสั้นกว่าทำให้สัปดาห์ที่กำไรไม่ถูกหักล้างด้วยสัปดาห์ที่ขาดทุนในเดือนเดียวกัน
    ผู้จัดการพอร์ตจึงเก็บได้มากกว่า แต่นั่นแปลว่าเจ้าของเงินจ่ายมากขึ้นสำหรับผลลัพธ์สุทธิเท่าเดิม
    เป็นเงื่อนไขที่ต้องตกลงกัน ไม่ใช่สิ่งที่เปลี่ยนฝ่ายเดียวได้
    """
    settings, rates, base, kind = _ctx(conn)
    monthly = _total_earning(conn, earnings.MONTH)
    weekly = _total_earning(conn, earnings.WEEK)
    current = monthly if kind == earnings.MONTH else weekly
    best = max(monthly, weekly)
    return {
        "current_kind": kind,
        "monthly": monthly,
        "weekly": weekly,
        "current": current,
        "gain": round(best - current, 2),
        "better": earnings.WEEK if weekly > monthly else earnings.MONTH,
    }


def rule_drag(conn):
    """เงื่อนไขที่ตั้งไว้กินรายได้ไปเท่าไร เทียบกับถ้าไม่มีเงื่อนไขนั้น"""
    settings, rates, base, kind = _ctx(conn)
    current = _total_earning(conn, kind)
    no_min = _total_earning(conn, kind, {"min_profit": 0.0})
    no_hwm = _total_earning(conn, kind, {"use_hwm": False})
    return {
        "current": current,
        "min_profit_cost": round(no_min - current, 2),
        "hwm_cost": round(no_hwm - current, 2),
    }


# ================================================= 5. พอร์ตที่ไม่คุ้มแบก

def efficiency(conn):
    """
    รายได้ที่แต่ละพอร์ตสร้างจริง เทียบกับทุนที่ใช้และความเสี่ยงที่ต้องแบก
    ใช้ตอบว่าควรทุ่มเวลาให้พอร์ตไหน และพอร์ตไหนแบกไว้แล้วไม่คุ้ม
    """
    settings, rates, base, kind = _ctx(conn)
    out = []
    for acc in conn.execute(
        "SELECT * FROM accounts WHERE tracked = 1 ORDER BY name"
    ).fetchall():
        earned = conn.execute(
            "SELECT COALESCE(SUM(earning), 0) v FROM accruals WHERE account_id = ?",
            (acc["id"],),
        ).fetchone()["v"]
        earned_base = to_base(earned, acc["currency"], rates, base)
        balance_base = to_base(acc["balance"], acc["currency"], rates, base)
        months = _months_covered(conn, acc["id"])
        per_month = round(earned_base / months, 2) if months >= 1 else None
        dd = float(acc["drawdown_pct"])
        out.append({
            "account_id": acc["id"],
            "name": acc["name"],
            "currency": acc["currency"],
            "balance_base": balance_base,
            "earned_base": round(earned_base, 2),
            "per_month": per_month,
            "months": round(months, 1),
            # รายได้ต่อทุนหนึ่งพันหน่วยต่อเดือน ใช้เทียบพอร์ตที่ขนาดต่างกันได้
            "yield_per_1k": round(per_month / balance_base * 1000, 2)
                            if per_month and balance_base > 0 else None,
            # รายได้ต่อหนึ่งหน่วยความเสี่ยง พอร์ตที่ได้เงินน้อยแต่เสี่ยงมากจะโผล่ขึ้นมา
            "earn_per_risk": round(per_month / dd, 2) if per_month and dd > 0 else None,
            "drawdown_pct": dd,
            "never_earned": earned_base <= 0.009,
        })
    out.sort(key=lambda x: (x["yield_per_1k"] is None, -(x["yield_per_1k"] or 0)))
    return out


def capital_plan(conn, target_monthly=None):
    """
    อยากได้รายได้เท่านี้ต่อเดือน ต้องบริหารทุนประมาณเท่าไร

    คิดจากสถิติจริงของพอร์ตที่มีอยู่ ไม่ใช่ตัวเลขในฝัน
    ใช้ค่ากลางของรายได้ต่อทุนหนึ่งหน่วยต่อเดือน แล้วแสดงช่วงดีและช่วงแย่ประกอบ
    เพื่อไม่ให้เข้าใจผิดว่าเป็นตัวเลขที่การันตีได้
    """
    settings, rates, base, kind = _ctx(conn)
    eff = [e for e in efficiency(conn) if e["yield_per_1k"] is not None]
    if not eff:
        return {"enough": False}

    ratios = sorted(e["yield_per_1k"] for e in eff)
    n = len(ratios)
    median = ratios[n // 2] if n % 2 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2
    low = ratios[0]
    high = ratios[-1]

    if target_monthly is None:
        goal = conn.execute(
            "SELECT target FROM goals WHERE period_key = ?",
            (earnings.current_period(kind),),
        ).fetchone()
        target_monthly = float(goal["target"]) if goal else 0.0

    def capital_for(rate):
        return round(target_monthly / rate * 1000, 2) if rate > 0 else None

    current_capital = round(sum(e["balance_base"] for e in eff), 2)
    current_monthly = round(sum(e["per_month"] or 0 for e in eff), 2)

    return {
        "enough": True,
        "target_monthly": round(target_monthly, 2),
        "median_yield_per_1k": round(median, 2),
        "low_yield_per_1k": round(low, 2),
        "high_yield_per_1k": round(high, 2),
        "capital_median": capital_for(median),
        "capital_pessimistic": capital_for(low),
        "capital_optimistic": capital_for(high),
        "current_capital": current_capital,
        "current_monthly": current_monthly,
        "capital_gap": round((capital_for(median) or 0) - current_capital, 2)
                       if target_monthly > 0 else None,
        "accounts_n": len(eff),
    }


# ================================================== รวมเป็นรายการโอกาส

def opportunities(conn):
    """รวมทุกแหล่งเป็นรายการเดียว เรียงตามจำนวนเงินที่ได้เพิ่ม"""
    settings, rates, base, kind = _ctx(conn)
    rec = receivables(conn)
    price = pricing_power(conn)
    period = billing_period_compare(conn)
    drag = rule_drag(conn)
    eff = efficiency(conn)

    items = []

    # เงินค้างเก็บทั้งหมดเก็บได้โดยไม่ต้องเจรจาอะไรใหม่ จึงนับรวมเป็นก้อนเดียว
    # ส่วนที่ค้างนานเกิน 30 วันเอาไปบอกในรายละเอียดเพื่อบอกความเร่งด่วน
    if rec["total"] > 0:
        if rec["overdue_total"] > 0:
            detail = ("เป็นเงินที่คิดส่วนแบ่งไว้แล้วและควรได้อยู่แล้ว ไม่ต้องเจรจาอะไรใหม่ "
                      "ในจำนวนนี้ค้างเกิน 30 วันอยู่ %s %s รวม %d รอบ ค้างนานที่สุด %d วัน "
                      "หนี้ยิ่งเก่ายิ่งเก็บยาก ควรตามก้อนนี้ก่อน"
                      % (_m(rec["overdue_total"]), base, rec["overdue_count"], rec["oldest_days"]))
        else:
            detail = ("เป็นเงินที่คิดส่วนแบ่งไว้แล้วและควรได้อยู่แล้ว ยังไม่มีรอบไหนค้างเกิน 30 วัน "
                      "แต่ควรตามเก็บก่อนจะกลายเป็นหนี้เก่า")
        items.append({
            "key": "due",
            "kind": "เก็บเงินที่ค้าง",
            "amount": rec["total"],
            "effort": "ทำได้ทันที",
            "title": "มีเงินค้างเก็บรวม %s %s จาก %d รอบ" % (_m(rec["total"]), base, len(rec["items"])),
            "detail": detail,
            "route": "/payouts",
        })

    if period["gain"] > 0:
        label = "รายสัปดาห์" if period["better"] == earnings.WEEK else "รายเดือน"
        items.append({
            "key": "period",
            "kind": "เงื่อนไขในสัญญา",
            "amount": period["gain"],
            "effort": "ต้องตกลงกับเจ้าของเงิน",
            "title": "เก็บเป็นรอบ%sจะได้มากกว่า" % label,
            "detail": "จากข้อมูลย้อนหลังทั้งหมด รอบ%sให้ %s %s ส่วนรอบปัจจุบันให้ %s %s "
                      "ต่างกัน %s %s รอบที่สั้นกว่าทำให้สัปดาห์ที่กำไรไม่ถูกหักล้างด้วยสัปดาห์ที่ขาดทุน "
                      "แต่แปลว่าเจ้าของเงินจ่ายมากขึ้นสำหรับผลลัพธ์สุทธิเท่าเดิม จึงต้องคุยกันก่อนเปลี่ยน"
                      % (label, _m(max(period["monthly"], period["weekly"])), base,
                         _m(period["current"]), base, _m(period["gain"]), base),
            "route": "/connect",
        })

    top_price = price[0] if price else None
    if top_price and top_price["per_point"] > 0:
        total_point = round(sum(p["per_point"] for p in price), 2)
        items.append({
            "key": "pricing",
            "kind": "เงื่อนไขในสัญญา",
            "amount": total_point,
            "effort": "ต้องเจรจา",
            "title": "ทุก 1%% ของส่วนแบ่ง มีค่า %s %s ต่อข้อมูลย้อนหลังทั้งหมด" % (_m(total_point), base),
            "detail": "พอร์ตที่คุ้มเจรจาที่สุดคือ %s ปัจจุบันคิด %s%% ถ้าขึ้นอีก 1%% จะได้เพิ่ม %s %s "
                      "หรือราวเดือนละ %s เป็นข้อมูลไว้ประกอบการคุย ไม่ใช่สิ่งที่เปลี่ยนฝ่ายเดียวได้"
                      % (top_price["name"], _m(top_price["share_pct"]), _m(top_price["per_point"]),
                         base, _m(top_price["per_point_monthly"] or 0)),
            "route": "/accounts",
        })

    if drag["min_profit_cost"] > 0:
        items.append({
            "key": "min_profit",
            "kind": "เงื่อนไขที่ตั้งเอง",
            "amount": drag["min_profit_cost"],
            "effort": "แก้ได้เอง แต่ควรบอกเจ้าของเงิน",
            "title": "ขั้นต่ำที่ตั้งไว้ทำให้เสียรายได้ %s %s" % (_m(drag["min_profit_cost"]), base),
            "detail": "มีรอบที่ทำกำไรได้จริงแต่ไม่ถึงขั้นต่ำที่ตั้งไว้ จึงไม่ได้คิดส่วนแบ่งเลย "
                      "ถ้าขั้นต่ำนี้ไม่ได้มาจากข้อตกลงกับเจ้าของเงิน การลดลงมาจะได้รายได้ส่วนนี้คืน",
            "route": "/accounts",
        })

    dead = [e for e in eff if e["never_earned"]]
    for d in dead:
        items.append({
            "key": "dead-%d" % d["account_id"],
            "kind": "ตัดสิ่งที่ไม่คุ้ม",
            "amount": 0.0,
            "effort": "ต้องตัดสินใจ",
            "title": "%s ไม่เคยสร้างรายได้เลยใน %s เดือน" % (d["name"], _m(d["months"])),
            "detail": "ทุน %s %s และรับความเสี่ยงขาดทุนสะสมถึง %s%% โดยไม่ได้ส่วนแบ่งกลับมาเลย "
                      "ควรตัดสินใจว่าจะแก้เงื่อนไข ปรับกลยุทธ์ หรือเลิกแบกพอร์ตนี้"
                      % (_m(d["balance_base"]), base, _m(d["drawdown_pct"])),
            "route": "/account?id=%d" % d["account_id"],
        })

    weak = [e for e in eff if e["earn_per_risk"] is not None and e["earn_per_risk"] < 1
            and not e["never_earned"]]
    for w in weak:
        items.append({
            "key": "weak-%d" % w["account_id"],
            "kind": "ตัดสิ่งที่ไม่คุ้ม",
            "amount": 0.0,
            "effort": "ควรทบทวน",
            "title": "%s ได้เงินน้อยเมื่อเทียบกับความเสี่ยงที่แบก" % w["name"],
            "detail": "ได้เดือนละ %s %s แต่เคยขาดทุนสะสมลึกถึง %s%% "
                      "เทียบกันแล้วได้รายได้เพียง %s ต่อหนึ่งหน่วยความเสี่ยง"
                      % (_m(w["per_month"] or 0), base, _m(w["drawdown_pct"]),
                         _m(w["earn_per_risk"])),
            "route": "/account?id=%d" % w["account_id"],
        })

    items.sort(key=lambda x: x["amount"], reverse=True)
    return {
        "items": items,
        "total_now": round(sum(i["amount"] for i in items if i["effort"] == "ทำได้ทันที"), 2),
        "total_negotiable": round(sum(i["amount"] for i in items
                                      if i["effort"] != "ทำได้ทันที"), 2),
    }


def _m(value):
    return "{:,.2f}".format(float(value or 0))


def board(target_monthly=None):
    """ข้อมูลทั้งหมดของหน้าเครื่องหาเงิน"""
    conn = connect()
    try:
        settings, rates, base, kind = _ctx(conn)
        return {
            "ok": True,
            "base_currency": base,
            "period_kind": kind,
            "opportunities": opportunities(conn),
            "receivables": receivables(conn),
            "pricing": pricing_power(conn),
            "billing": billing_period_compare(conn),
            "drag": rule_drag(conn),
            "efficiency": efficiency(conn),
            "capital": capital_plan(conn, target_monthly),
        }
    finally:
        conn.close()

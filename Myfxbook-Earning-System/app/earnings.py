"""
Myfxbook Earning System - เครื่องคิดรายได้ส่วนแบ่ง

หลักการ
    กำไรรายวันของแต่ละพอร์ตถูกรวมเป็นรอบ (รายเดือนหรือรายสัปดาห์)
    แล้วคิดส่วนแบ่งด้วยหลัก High-Water Mark คือ
    "คิดส่วนแบ่งเฉพาะกำไรส่วนที่ทำจุดสูงสุดใหม่เท่านั้น"
    ถ้าพอร์ตขาดทุนแล้วไต่กลับ ช่วงที่ไต่กลับจะยังไม่คิดส่วนแบ่ง
    จนกว่าจะผ่านจุดสูงสุดเดิม ผู้ลงทุนจึงไม่ต้องจ่ายซ้ำสำหรับกำไรก้อนเดิม
"""

from datetime import date, datetime, timedelta

from .database import get_settings, now_iso

MONTH = "MONTH"
WEEK = "WEEK"


# ------------------------------------------------------------------ รอบเวลา

def period_key(day, kind=MONTH):
    d = _as_date(day)
    if d is None:
        return ""
    if kind == WEEK:
        iso_year, iso_week, _ = d.isocalendar()
        return "%04d-W%02d" % (iso_year, iso_week)
    return d.strftime("%Y-%m")


def period_bounds(key):
    """คืนวันแรกและวันสุดท้ายของรอบ ตามรูปแบบคีย์ที่ period_key สร้าง"""
    if not key:
        return "", ""
    if "W" in key:
        year, week = key.split("-W")
        start = date.fromisocalendar(int(year), int(week), 1)
        return start.isoformat(), (start + timedelta(days=6)).isoformat()
    year, month = (int(x) for x in key.split("-"))
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def period_label(key):
    """ชื่อรอบแบบอ่านง่ายเป็นภาษาไทย"""
    if not key:
        return "-"
    months = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
              "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    if "W" in key:
        year, week = key.split("-W")
        return "สัปดาห์ที่ %s ปี %s" % (int(week), int(year) + 543)
    year, month = (int(x) for x in key.split("-"))
    return "%s %s" % (months[month - 1], str(year + 543)[2:])


def current_period(kind=MONTH):
    return period_key(date.today(), kind)


def shift_period(key, steps):
    """เลื่อนรอบไปข้างหน้าหรือย้อนหลังตามจำนวนที่กำหนด"""
    start, end = period_bounds(key)
    if not start:
        return key
    if "W" in key:
        base = _as_date(start) + timedelta(weeks=steps)
        return period_key(base, WEEK)
    d = _as_date(start)
    total = d.year * 12 + (d.month - 1) + steps
    return "%04d-%02d" % (total // 12, total % 12 + 1)


# --------------------------------------------------------------- คิดส่วนแบ่ง

def bucket_by_period(rows, kind=MONTH):
    """รวมกำไรรายวันเป็นก้อนตามรอบ คืน dict ของ คีย์รอบ -> กำไรรวมในรอบ"""
    buckets = {}
    for row in rows:
        key = period_key(row["day"], kind)
        if not key:
            continue
        buckets[key] = buckets.get(key, 0.0) + float(row["profit"] or 0.0)
    return buckets


def simulate(rows, kind=MONTH, share_pct=0.0, use_hwm=True,
             min_profit=0.0, fixed_fee=0.0, active=True):
    """
    แกนกลางของการคิดส่วนแบ่ง เป็นฟังก์ชันบริสุทธิ์ ไม่แตะฐานข้อมูล

    ทั้งการคิดเงินจริงและการทดลองว่า "ถ้าเปลี่ยนเงื่อนไขแล้วจะได้เท่าไร"
    ต่างเรียกฟังก์ชันนี้ตัวเดียวกัน ตัวเลขที่เอาไปคุยกับลูกค้าจึงตรงกับที่เก็บจริงเสมอ
    """
    buckets = bucket_by_period(rows, kind)
    cum = 0.0
    hwm = 0.0
    out = []
    for key in sorted(buckets):
        gross = round(buckets[key], 2)
        cum_end = round(cum + gross, 2)
        hwm_before = hwm

        if use_hwm:
            base = round(max(0.0, cum_end - hwm_before), 2)
            base = min(base, gross) if gross > 0 else 0.0
        else:
            base = max(0.0, gross)

        earning = 0.0
        if active and base > 0 and base >= min_profit:
            earning = round(base * share_pct / 100.0 + fixed_fee, 2)

        hwm_after = round(max(hwm_before, cum_end), 2)
        start_day, end_day = period_bounds(key)
        out.append({
            "period_key": key, "start_day": start_day, "end_day": end_day,
            "gross": gross, "base": base,
            "hwm_before": hwm_before, "hwm_after": hwm_after,
            "share_pct": share_pct, "earning": earning,
        })
        cum = cum_end
        hwm = hwm_after
    return out


def rule_of(conn, account_id):
    """อ่านเงื่อนไขส่วนแบ่งของพอร์ตออกมาเป็น dict ที่ simulate ใช้ได้ทันที"""
    row = conn.execute("SELECT * FROM rules WHERE account_id = ?", (account_id,)).fetchone()
    if row is None:
        return {"share_pct": 0.0, "use_hwm": True, "min_profit": 0.0,
                "fixed_fee": 0.0, "active": False}
    return {
        "share_pct": float(row["share_pct"]),
        "use_hwm": bool(row["use_hwm"]),
        "min_profit": float(row["min_profit"]),
        "fixed_fee": float(row["fixed_fee"]),
        "active": bool(row["active"]),
    }


def daily_rows(conn, account_id):
    return conn.execute(
        "SELECT day, profit FROM daily WHERE account_id = ? ORDER BY day", (account_id,)
    ).fetchall()


def recompute_account(conn, account_id, kind=MONTH):
    """
    คิดส่วนแบ่งใหม่ทั้งเส้นเวลาของพอร์ตหนึ่งแล้วบันทึกลงตาราง accruals
    ต้องคิดใหม่ทั้งเส้นเสมอ เพราะ High-Water Mark ของรอบหลังขึ้นกับรอบก่อนหน้า
    """
    account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if account is None:
        return []

    periods = simulate(daily_rows(conn, account_id), kind, **rule_of(conn, account_id))

    conn.execute("DELETE FROM accruals WHERE account_id = ?", (account_id,))
    stamp = now_iso()
    for p in periods:
        conn.execute(
            """INSERT INTO accruals
               (account_id, period_key, start_day, end_day, gross, base,
                hwm_before, hwm_after, share_pct, earning, currency, computed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (account_id, p["period_key"], p["start_day"], p["end_day"], p["gross"], p["base"],
             p["hwm_before"], p["hwm_after"], p["share_pct"], p["earning"],
             account["currency"], stamp),
        )
    return periods


def recompute_all(conn, kind=None):
    if kind is None:
        kind = get_settings(conn).get("period_kind", MONTH)
    total = 0
    for row in conn.execute("SELECT id FROM accounts").fetchall():
        total += len(recompute_account(conn, row["id"], kind))
    return total


# ------------------------------------------------------------------ สรุปยอด

def account_ledger(conn, account_id):
    """ยอดรายได้สะสม ยอดที่จ่ายไปแล้ว และยอดค้างจ่ายของพอร์ตเดียว (สกุลเงินของพอร์ต)"""
    accrued = conn.execute(
        "SELECT COALESCE(SUM(earning), 0) v FROM accruals WHERE account_id = ?", (account_id,)
    ).fetchone()["v"]
    paid = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) v FROM payouts WHERE account_id = ?", (account_id,)
    ).fetchone()["v"]
    return {
        "accrued": round(float(accrued), 2),
        "paid": round(float(paid), 2),
        "outstanding": round(float(accrued) - float(paid), 2),
    }


def period_status(earning, paid):
    """สถานะของรอบหนึ่ง ใช้ทาสีในตาราง"""
    if earning <= 0:
        return "NONE"
    if paid <= 0:
        return "DUE"
    if paid + 0.009 < earning:
        return "PARTIAL"
    return "PAID"


STATUS_LABEL = {
    "NONE": "ไม่มีส่วนแบ่ง",
    "DUE": "ค้างจ่าย",
    "PARTIAL": "จ่ายบางส่วน",
    "PAID": "จ่ายครบแล้ว",
}


# ------------------------------------------------------------------ ตัวช่วย

def _as_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None

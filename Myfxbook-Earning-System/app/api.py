"""
Myfxbook Earning System - ชั้น API

ทุกฟังก์ชันในไฟล์นี้คืนค่าเป็น dict ที่แปลงเป็น JSON ได้ทันที
และมีคีย์ "ok" เสมอ เพื่อให้ชั้นเซิร์ฟเวอร์ตัดสินใจรหัสสถานะได้
"""

from datetime import date, datetime, timedelta

from . import analytics, earnings, myfxbook
from .database import (
    connect, fx_map, get_setting, get_settings, now_iso, set_setting, to_base,
)

DEMO_PREFIX = "demo-"


# =============================================================== ตัวช่วยภายใน

def _ctx(conn):
    """ข้อมูลพื้นฐานที่เกือบทุก endpoint ต้องใช้: ค่าตั้งค่า อัตราแลกเปลี่ยน สกุลกลาง"""
    settings = get_settings(conn)
    rates = fx_map(conn)
    base = (settings.get("base_currency") or "USD").upper()
    kind = settings.get("period_kind") or earnings.MONTH
    return settings, rates, base, kind


def _acc_row(row, rates, base):
    """แปลงแถวพอร์ตเป็น dict พร้อมยอดที่แปลงเป็นสกุลกลางแล้ว"""
    return {
        "id": row["id"],
        "mfb_id": row["mfb_id"],
        "name": row["name"],
        "account_no": row["account_no"],
        "broker": row["broker"],
        "platform": row["platform"],
        "currency": row["currency"],
        "owner": row["owner"],
        "balance": round(float(row["balance"]), 2),
        "equity": round(float(row["equity"]), 2),
        "profit": round(float(row["profit"]), 2),
        "gain_pct": round(float(row["gain_pct"]), 2),
        "drawdown_pct": round(float(row["drawdown_pct"]), 2),
        "balance_base": to_base(row["balance"], row["currency"], rates, base),
        "profit_base": to_base(row["profit"], row["currency"], rates, base),
        "first_trade_at": row["first_trade_at"],
        "last_update": row["last_update"],
        "is_demo": bool(row["is_demo"]),
        "tracked": bool(row["tracked"]),
        "source": row["source"],
    }


def _rule_row(row):
    if row is None:
        return None
    return {
        "label": row["label"],
        "share_pct": round(float(row["share_pct"]), 2),
        "use_hwm": bool(row["use_hwm"]),
        "min_profit": round(float(row["min_profit"]), 2),
        "fixed_fee": round(float(row["fixed_fee"]), 2),
        "active": bool(row["active"]),
        "updated_at": row["updated_at"],
    }


def _paid_map(conn):
    """ยอดที่จ่ายไปแล้ว แยกตามพอร์ตและรอบ"""
    rows = conn.execute(
        "SELECT account_id, period_key, COALESCE(SUM(amount), 0) v "
        "FROM payouts GROUP BY account_id, period_key"
    ).fetchall()
    return {(r["account_id"], r["period_key"]): float(r["v"]) for r in rows}


def _float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _clamp(value, low, high):
    return max(low, min(high, value))


# ===================================================================== ภาพรวม

def overview(days=90):
    conn = connect()
    try:
        settings, rates, base, kind = _ctx(conn)
        accounts = conn.execute(
            "SELECT * FROM accounts WHERE tracked = 1 ORDER BY name"
        ).fetchall()
        acc_list = [_acc_row(a, rates, base) for a in accounts]
        acc_currency = {a["id"]: a["currency"] for a in accounts}

        today = date.today()
        since = (today - timedelta(days=int(days))).isoformat()

        # ---- เส้นกราฟกำไรรวมรายวัน (แปลงเป็นสกุลกลางก่อนบวกกัน)
        rows = conn.execute(
            "SELECT account_id, day, profit FROM daily WHERE day >= ? ORDER BY day", (since,)
        ).fetchall()
        by_day = {}
        for r in rows:
            cur = acc_currency.get(r["account_id"])
            if cur is None:
                continue
            value = to_base(r["profit"], cur, rates, base)
            by_day[r["day"]] = round(by_day.get(r["day"], 0.0) + value, 2)
        series = [{"day": d, "profit": by_day[d]} for d in sorted(by_day)]
        running = 0.0
        for point in series:
            running = round(running + point["profit"], 2)
            point["cum"] = running

        # ---- ยอดรวมของพอร์ต
        equity_total = round(sum(a["balance_base"] for a in acc_list), 2)
        profit_total = round(sum(a["profit_base"] for a in acc_list), 2)

        # ---- รายได้ส่วนแบ่ง
        this_key = earnings.current_period(kind)
        prev_key = earnings.shift_period(this_key, -1)
        accrual_rows = conn.execute("SELECT * FROM accruals").fetchall()
        earn_this = earn_prev = earn_all = 0.0
        for r in accrual_rows:
            value = to_base(r["earning"], r["currency"], rates, base)
            earn_all += value
            if r["period_key"] == this_key:
                earn_this += value
            elif r["period_key"] == prev_key:
                earn_prev += value

        paid_rows = conn.execute("SELECT amount, currency, paid_at FROM payouts").fetchall()
        paid_all = 0.0
        paid_this = 0.0
        for r in paid_rows:
            value = to_base(r["amount"], r["currency"], rates, base)
            paid_all += value
            if earnings.period_key(r["paid_at"], kind) == this_key:
                paid_this += value

        outstanding = round(earn_all - paid_all, 2)

        # ---- เป้าหมายของรอบนี้
        goal = conn.execute("SELECT * FROM goals WHERE period_key = ?", (this_key,)).fetchone()
        target = float(goal["target"]) if goal else 0.0
        start_day, end_day = earnings.period_bounds(this_key)
        span = max(1, (datetime.strptime(end_day, "%Y-%m-%d").date()
                       - datetime.strptime(start_day, "%Y-%m-%d").date()).days + 1)
        elapsed = _clamp((today - datetime.strptime(start_day, "%Y-%m-%d").date()).days + 1, 1, span)

        # ---- พอร์ตที่ทำรายได้ดีที่สุดในรอบนี้
        top = []
        for r in accrual_rows:
            if r["period_key"] != this_key:
                continue
            acc = next((a for a in acc_list if a["id"] == r["account_id"]), None)
            if acc is None:
                continue
            top.append({
                "id": acc["id"],
                "name": acc["name"],
                "currency": acc["currency"],
                "gross": round(float(r["gross"]), 2),
                "earning": round(float(r["earning"]), 2),
                "earning_base": to_base(r["earning"], r["currency"], rates, base),
            })
        top.sort(key=lambda x: x["earning_base"], reverse=True)

        alert_data = alerts_board()
        return {
            "ok": True,
            "base_currency": base,
            "period": {
                "key": this_key,
                "label": earnings.period_label(this_key),
                "kind": kind,
                "start": start_day,
                "end": end_day,
                "elapsed": elapsed,
                "span": span,
            },
            "kpi": {
                "equity_total": equity_total,
                "profit_total": profit_total,
                "accounts_n": len(acc_list),
                "earning_period": round(earn_this, 2),
                "earning_prev": round(earn_prev, 2),
                "earning_all": round(earn_all, 2),
                "paid_all": round(paid_all, 2),
                "paid_period": round(paid_this, 2),
                "outstanding": outstanding,
                "target": round(target, 2),
                "target_pct": round(earn_this / target * 100, 1) if target > 0 else None,
                "pace_pct": round(elapsed / span * 100, 1),
            },
            "series": series,
            "top": top[:6],
            "accounts": acc_list,
            "alerts": alert_data["counts"],
            "demo_mode": settings.get("demo_mode") == "1",
            "connected": bool(settings.get("mfb_session")),
            "last_sync_at": settings.get("last_sync_at") or "",
        }
    finally:
        conn.close()


# ===================================================================== พอร์ต

def accounts_board():
    conn = connect()
    try:
        settings, rates, base, kind = _ctx(conn)
        rows = conn.execute("SELECT * FROM accounts ORDER BY tracked DESC, name").fetchall()
        rules = {r["account_id"]: r for r in conn.execute("SELECT * FROM rules").fetchall()}
        out = []
        for row in rows:
            item = _acc_row(row, rates, base)
            item["rule"] = _rule_row(rules.get(row["id"]))
            item["ledger"] = earnings.account_ledger(conn, row["id"])
            item["ledger_base"] = {
                k: to_base(v, row["currency"], rates, base) for k, v in item["ledger"].items()
            }
            last = conn.execute(
                "SELECT day, profit FROM daily WHERE account_id = ? ORDER BY day DESC LIMIT 14",
                (row["id"],),
            ).fetchall()
            item["spark"] = [round(float(r["profit"]), 2) for r in reversed(last)]
            out.append(item)
        return {"ok": True, "accounts": out, "base_currency": base, "period_kind": kind}
    finally:
        conn.close()


def account_detail(account_id, days=180):
    conn = connect()
    try:
        settings, rates, base, kind = _ctx(conn)
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            return {"ok": False, "error": "ไม่พบพอร์ตนี้"}
        rule = conn.execute("SELECT * FROM rules WHERE account_id = ?", (account_id,)).fetchone()
        since = (date.today() - timedelta(days=int(days))).isoformat()
        daily = conn.execute(
            "SELECT day, balance, equity, profit, pips, lots FROM daily "
            "WHERE account_id = ? AND day >= ? ORDER BY day",
            (account_id, since),
        ).fetchall()
        paid = _paid_map(conn)
        accruals = []
        for r in conn.execute(
            "SELECT * FROM accruals WHERE account_id = ? ORDER BY period_key DESC", (account_id,)
        ).fetchall():
            paid_amount = paid.get((account_id, r["period_key"]), 0.0)
            accruals.append({
                "period_key": r["period_key"],
                "label": earnings.period_label(r["period_key"]),
                "start_day": r["start_day"],
                "end_day": r["end_day"],
                "gross": round(float(r["gross"]), 2),
                "base": round(float(r["base"]), 2),
                "hwm_before": round(float(r["hwm_before"]), 2),
                "hwm_after": round(float(r["hwm_after"]), 2),
                "share_pct": round(float(r["share_pct"]), 2),
                "earning": round(float(r["earning"]), 2),
                "paid": round(paid_amount, 2),
                "status": earnings.period_status(float(r["earning"]), paid_amount),
            })
        payouts = [dict(r) for r in conn.execute(
            "SELECT * FROM payouts WHERE account_id = ? ORDER BY paid_at DESC, id DESC",
            (account_id,),
        ).fetchall()]

        item = _acc_row(row, rates, base)
        item["rule"] = _rule_row(rule)
        item["ledger"] = earnings.account_ledger(conn, account_id)
        return {
            "ok": True,
            "account": item,
            "daily": [
                {
                    "day": r["day"],
                    "balance": round(float(r["balance"]), 2),
                    "equity": round(float(r["equity"]), 2),
                    "profit": round(float(r["profit"]), 2),
                    "pips": round(float(r["pips"]), 1),
                    "lots": round(float(r["lots"]), 2),
                }
                for r in daily
            ],
            "accruals": accruals,
            "payouts": payouts,
            "base_currency": base,
        }
    finally:
        conn.close()


def save_rule(account_id, body):
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            return {"ok": False, "error": "ไม่พบพอร์ตนี้"}
        share = _clamp(_float(body.get("share_pct"), 0), 0, 100)
        label = (body.get("label") or "ส่วนแบ่งกำไร").strip()[:60]
        use_hwm = 1 if body.get("use_hwm") in (True, 1, "1", "true", "on") else 0
        min_profit = max(0.0, _float(body.get("min_profit"), 0))
        fixed_fee = max(0.0, _float(body.get("fixed_fee"), 0))
        active = 1 if body.get("active") in (True, 1, "1", "true", "on", None) else 0
        stamp = now_iso()
        conn.execute(
            """INSERT INTO rules (account_id, label, share_pct, use_hwm, min_profit, fixed_fee, active, updated_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(account_id) DO UPDATE SET
                 label=excluded.label, share_pct=excluded.share_pct, use_hwm=excluded.use_hwm,
                 min_profit=excluded.min_profit, fixed_fee=excluded.fixed_fee,
                 active=excluded.active, updated_at=excluded.updated_at""",
            (account_id, label, share, use_hwm, min_profit, fixed_fee, active, stamp),
        )
        kind = get_setting(conn, "period_kind", earnings.MONTH)
        earnings.recompute_account(conn, account_id, kind)
        conn.commit()
        analytics.invalidate()
        return {"ok": True, "message": "บันทึกเงื่อนไขส่วนแบ่งและคิดรายได้ใหม่แล้ว"}
    finally:
        conn.close()


def set_tracked(account_id, tracked):
    conn = connect()
    try:
        conn.execute("UPDATE accounts SET tracked = ? WHERE id = ?", (1 if tracked else 0, account_id))
        conn.commit()
        return {"ok": True, "tracked": bool(tracked)}
    finally:
        conn.close()


# ================================================================== รายได้

def earnings_board(period_key=None):
    conn = connect()
    try:
        settings, rates, base, kind = _ctx(conn)
        keys = [r["period_key"] for r in conn.execute(
            "SELECT DISTINCT period_key FROM accruals ORDER BY period_key DESC"
        ).fetchall()]
        if not keys:
            keys = [earnings.current_period(kind)]
        selected = period_key if period_key in keys else keys[0]

        paid = _paid_map(conn)
        rows = conn.execute(
            """SELECT k.*, a.name, a.owner, a.currency AS acc_currency
               FROM accruals k JOIN accounts a ON a.id = k.account_id
               WHERE k.period_key = ? ORDER BY k.earning DESC""",
            (selected,),
        ).fetchall()
        items = []
        totals = {"gross": 0.0, "base": 0.0, "earning": 0.0, "paid": 0.0}
        for r in rows:
            paid_amount = paid.get((r["account_id"], r["period_key"]), 0.0)
            earning = float(r["earning"])
            items.append({
                "account_id": r["account_id"],
                "name": r["name"],
                "owner": r["owner"],
                "currency": r["currency"],
                "gross": round(float(r["gross"]), 2),
                "base": round(float(r["base"]), 2),
                "hwm_before": round(float(r["hwm_before"]), 2),
                "hwm_after": round(float(r["hwm_after"]), 2),
                "share_pct": round(float(r["share_pct"]), 2),
                "earning": round(earning, 2),
                "paid": round(paid_amount, 2),
                "due": round(earning - paid_amount, 2),
                "earning_base": to_base(earning, r["currency"], rates, base),
                "gross_base": to_base(r["gross"], r["currency"], rates, base),
                "status": earnings.period_status(earning, paid_amount),
            })
            totals["gross"] += to_base(r["gross"], r["currency"], rates, base)
            totals["base"] += to_base(r["base"], r["currency"], rates, base)
            totals["earning"] += to_base(earning, r["currency"], rates, base)
            totals["paid"] += to_base(paid_amount, r["currency"], rates, base)

        history = []
        for key in keys[:12]:
            sub = conn.execute(
                "SELECT earning, currency FROM accruals WHERE period_key = ?", (key,)
            ).fetchall()
            history.append({
                "period_key": key,
                "label": earnings.period_label(key),
                "earning": round(sum(to_base(s["earning"], s["currency"], rates, base) for s in sub), 2),
            })
        history.reverse()

        return {
            "ok": True,
            "periods": [{"key": k, "label": earnings.period_label(k)} for k in keys],
            "selected": selected,
            "selected_label": earnings.period_label(selected),
            "items": items,
            "totals": {k: round(v, 2) for k, v in totals.items()},
            "history": history,
            "base_currency": base,
            "period_kind": kind,
        }
    finally:
        conn.close()


def recompute():
    conn = connect()
    try:
        kind = get_setting(conn, "period_kind", earnings.MONTH)
        n = earnings.recompute_all(conn, kind)
        conn.commit()
        analytics.invalidate()
        return {"ok": True, "periods": n, "message": "คิดรายได้ใหม่ทั้งหมด %d รอบ" % n}
    finally:
        conn.close()


# ================================================================== การจ่ายเงิน

def payouts_board(limit=200):
    conn = connect()
    try:
        settings, rates, base, kind = _ctx(conn)
        rows = conn.execute(
            """SELECT p.*, a.name AS account_name FROM payouts p
               LEFT JOIN accounts a ON a.id = p.account_id
               ORDER BY p.paid_at DESC, p.id DESC LIMIT ?""",
            (int(limit),),
        ).fetchall()
        items = []
        for r in rows:
            items.append({
                "id": r["id"],
                "account_id": r["account_id"],
                "account_name": r["account_name"] or "ไม่ระบุพอร์ต",
                "period_key": r["period_key"],
                "period_label": earnings.period_label(r["period_key"]) if r["period_key"] else "-",
                "amount": round(float(r["amount"]), 2),
                "currency": r["currency"],
                "amount_base": to_base(r["amount"], r["currency"], rates, base),
                "method": r["method"],
                "payee": r["payee"],
                "note": r["note"],
                "paid_at": r["paid_at"],
            })

        due = []
        paid = _paid_map(conn)
        for r in conn.execute(
            """SELECT k.*, a.name FROM accruals k JOIN accounts a ON a.id = k.account_id
               WHERE k.earning > 0 ORDER BY k.period_key DESC"""
        ).fetchall():
            paid_amount = paid.get((r["account_id"], r["period_key"]), 0.0)
            remain = round(float(r["earning"]) - paid_amount, 2)
            if remain <= 0.009:
                continue
            due.append({
                "account_id": r["account_id"],
                "name": r["name"],
                "period_key": r["period_key"],
                "period_label": earnings.period_label(r["period_key"]),
                "currency": r["currency"],
                "earning": round(float(r["earning"]), 2),
                "paid": round(paid_amount, 2),
                "due": remain,
                "due_base": to_base(remain, r["currency"], rates, base),
            })

        return {
            "ok": True,
            "payouts": items,
            "due": due,
            "total_due": round(sum(d["due_base"] for d in due), 2),
            "total_paid": round(sum(i["amount_base"] for i in items), 2),
            "base_currency": base,
        }
    finally:
        conn.close()


def create_payout(body):
    conn = connect()
    try:
        amount = _float(body.get("amount"), 0)
        if amount <= 0:
            return {"ok": False, "error": "จำนวนเงินต้องมากกว่า 0"}
        account_id = body.get("account_id")
        account_id = int(account_id) if account_id not in (None, "", "0") else None
        currency = (body.get("currency") or "").upper()
        if account_id:
            row = conn.execute("SELECT currency FROM accounts WHERE id = ?", (account_id,)).fetchone()
            if row is None:
                return {"ok": False, "error": "ไม่พบพอร์ตนี้"}
            currency = currency or row["currency"]
        currency = currency or get_setting(conn, "base_currency", "USD")
        paid_at = (body.get("paid_at") or date.today().isoformat())[:10]
        stamp = now_iso()
        conn.execute(
            """INSERT INTO payouts (account_id, period_key, amount, currency, method, payee, note, paid_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                account_id,
                (body.get("period_key") or "").strip(),
                round(amount, 2), currency,
                (body.get("method") or "โอนธนาคาร").strip()[:40],
                (body.get("payee") or "").strip()[:80],
                (body.get("note") or "").strip()[:200],
                paid_at, stamp,
            ),
        )
        conn.commit()
        return {"ok": True, "message": "บันทึกการจ่ายเงินแล้ว"}
    finally:
        conn.close()


def delete_payout(payout_id):
    conn = connect()
    try:
        cur = conn.execute("DELETE FROM payouts WHERE id = ?", (payout_id,))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "ไม่พบรายการจ่ายเงินนี้"}
        return {"ok": True, "message": "ลบรายการจ่ายเงินแล้ว"}
    finally:
        conn.close()


# ================================================================== เป้าหมาย

def goals_board():
    conn = connect()
    try:
        settings, rates, base, kind = _ctx(conn)
        earned = {}
        for r in conn.execute("SELECT period_key, earning, currency FROM accruals").fetchall():
            earned[r["period_key"]] = round(
                earned.get(r["period_key"], 0.0) + to_base(r["earning"], r["currency"], rates, base), 2
            )
        rows = conn.execute("SELECT * FROM goals ORDER BY period_key DESC").fetchall()
        keys = sorted(set(list(earned) + [r["period_key"] for r in rows]), reverse=True)
        goals = {r["period_key"]: r for r in rows}
        items = []
        for key in keys[:18]:
            target = float(goals[key]["target"]) if key in goals else 0.0
            actual = earned.get(key, 0.0)
            items.append({
                "period_key": key,
                "label": earnings.period_label(key),
                "target": round(target, 2),
                "actual": actual,
                "diff": round(actual - target, 2),
                "pct": round(actual / target * 100, 1) if target > 0 else None,
                "note": goals[key]["note"] if key in goals else "",
            })
        return {"ok": True, "items": items, "base_currency": base,
                "current": earnings.current_period(kind)}
    finally:
        conn.close()


def save_goal(body):
    key = (body.get("period_key") or "").strip()
    if not key:
        return {"ok": False, "error": "ต้องระบุรอบที่ต้องการตั้งเป้า"}
    target = _float(body.get("target"), 0)
    if target < 0:
        return {"ok": False, "error": "เป้าหมายต้องไม่ติดลบ"}
    conn = connect()
    try:
        conn.execute(
            """INSERT INTO goals (period_key, target, note, updated_at) VALUES (?,?,?,?)
               ON CONFLICT(period_key) DO UPDATE SET
                 target=excluded.target, note=excluded.note, updated_at=excluded.updated_at""",
            (key, round(target, 2), (body.get("note") or "").strip()[:160], now_iso()),
        )
        conn.commit()
        return {"ok": True, "message": "บันทึกเป้าหมายแล้ว"}
    finally:
        conn.close()


# ================================================================== แจ้งเตือน

def alerts_board():
    conn = connect()
    try:
        settings, rates, base, kind = _ctx(conn)
        dd_warn = _float(settings.get("dd_warn_pct"), 10)
        dd_crit = _float(settings.get("dd_crit_pct"), 20)
        stale_hours = _float(settings.get("stale_sync_hours"), 24)

        acked = {r["key"]: r for r in conn.execute("SELECT * FROM alert_ack").fetchall()}
        items = []

        def add(key, level, title, detail, route="/"):
            items.append({
                "key": key, "level": level, "title": title, "detail": detail,
                "route": route, "acked": key in acked,
                "acked_by": acked[key]["actor"] if key in acked else "",
            })

        accounts = conn.execute("SELECT * FROM accounts WHERE tracked = 1").fetchall()
        for a in accounts:
            dd = float(a["drawdown_pct"])
            if dd >= dd_crit:
                add("dd-%d" % a["id"], "critical", "%s ขาดทุนสะสมลึก" % a["name"],
                    "Drawdown สูงสุด %.2f%% เกินเพดานวิกฤต %.0f%% ควรทบทวนขนาดความเสี่ยง" % (dd, dd_crit),
                    "/accounts")
            elif dd >= dd_warn:
                add("dd-%d" % a["id"], "warn", "%s ขาดทุนสะสมเริ่มสูง" % a["name"],
                    "Drawdown สูงสุด %.2f%% เกินเพดานเตือน %.0f%%" % (dd, dd_warn), "/accounts")

            streak = conn.execute(
                "SELECT profit FROM daily WHERE account_id = ? ORDER BY day DESC LIMIT 5", (a["id"],)
            ).fetchall()
            if len(streak) == 5 and all(float(s["profit"]) < 0 for s in streak):
                loss = sum(float(s["profit"]) for s in streak)
                add("streak-%d" % a["id"], "warn", "%s ขาดทุนติดกัน 5 วัน" % a["name"],
                    "รวม %.2f %s ในห้าวันทำการล่าสุด" % (loss, a["currency"]), "/accounts")

            # พอร์ตที่ยังอยู่ใต้ High-Water Mark จะยังไม่เกิดรายได้ส่วนแบ่ง
            last = conn.execute(
                "SELECT hwm_after FROM accruals WHERE account_id = ? ORDER BY period_key DESC LIMIT 1",
                (a["id"],),
            ).fetchone()
            cum = conn.execute(
                "SELECT COALESCE(SUM(profit), 0) v FROM daily WHERE account_id = ?", (a["id"],)
            ).fetchone()["v"]
            if last and float(last["hwm_after"]) - float(cum) > 0.01:
                gap = float(last["hwm_after"]) - float(cum)
                add("hwm-%d" % a["id"], "info", "%s ยังอยู่ใต้จุดสูงสุดเดิม" % a["name"],
                    "ต้องทำกำไรอีก %.2f %s จึงจะเริ่มคิดส่วนแบ่งรอบใหม่" % (gap, a["currency"]),
                    "/earnings")

        last_sync = settings.get("last_sync_at") or ""
        if settings.get("demo_mode") == "1":
            add("demo-mode", "info", "กำลังใช้โหมดสาธิต",
                "ข้อมูลที่เห็นเป็นพอร์ตตัวอย่าง เชื่อมต่อบัญชี Myfxbook จริงได้ที่หน้าเชื่อมต่อ", "/connect")
        elif last_sync:
            try:
                delta = datetime.now() - datetime.strptime(last_sync, "%Y-%m-%d %H:%M:%S")
                if delta.total_seconds() / 3600 > stale_hours:
                    add("stale-sync", "warn", "ข้อมูลเก่าเกินไป",
                        "ซิงก์ล่าสุดเมื่อ %s ควรกดซิงก์ใหม่" % last_sync, "/connect")
            except ValueError:
                pass
        else:
            add("never-sync", "warn", "ยังไม่เคยซิงก์ข้อมูล",
                "เชื่อมต่อ Myfxbook แล้วกดซิงก์เพื่อดึงผลการเทรดจริง", "/connect")

        # ดึงเรื่องร้ายแรงจากศูนย์วิเคราะห์มาเตือนด้วย ใช้ผลที่แคชไว้จึงไม่ถ่วงการเปลี่ยนหน้า
        try:
            for flag in intelligence().get("flags", []):
                if flag["level"] == "info":
                    continue
                key = "intel-%s-%s" % (flag["level"], flag.get("account_id") or "all")
                add(key, "critical" if flag["level"] == "critical" else "warn",
                    flag["title"], flag["detail"], "/intel")
        except Exception:
            pass    # ศูนย์วิเคราะห์ล้มต้องไม่ทำให้หน้าแจ้งเตือนทั้งหน้าใช้ไม่ได้

        due_total = payouts_due_total(conn, rates, base)
        if due_total > 0:
            add("payout-due", "warn", "มีรายได้ค้างจ่าย",
                "รวม %s %s ที่คิดส่วนแบ่งแล้วแต่ยังไม่ได้บันทึกการจ่าย" % (_money(due_total), base),
                "/payouts")

        order = {"critical": 0, "warn": 1, "info": 2}
        items.sort(key=lambda x: (x["acked"], order.get(x["level"], 3), x["title"]))
        counts = {
            "critical": sum(1 for i in items if i["level"] == "critical" and not i["acked"]),
            "warn": sum(1 for i in items if i["level"] == "warn" and not i["acked"]),
            "info": sum(1 for i in items if i["level"] == "info" and not i["acked"]),
        }
        return {"ok": True, "items": items, "counts": counts}
    finally:
        conn.close()


def payouts_due_total(conn, rates, base):
    paid = _paid_map(conn)
    total = 0.0
    for r in conn.execute("SELECT * FROM accruals WHERE earning > 0").fetchall():
        remain = float(r["earning"]) - paid.get((r["account_id"], r["period_key"]), 0.0)
        if remain > 0.009:
            total += to_base(remain, r["currency"], rates, base)
    return round(total, 2)


def ack_alert(key, actor):
    if not key:
        return {"ok": False, "error": "ไม่ได้ระบุการแจ้งเตือน"}
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO alert_ack(key, actor, ts) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET actor=excluded.actor, ts=excluded.ts",
            (key, actor or "ผู้ใช้", now_iso()),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def unack_alert(key):
    conn = connect()
    try:
        conn.execute("DELETE FROM alert_ack WHERE key = ?", (key,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def _money(value):
    return "{:,.2f}".format(value)


# ========================================================== ศูนย์วิเคราะห์

def intelligence(runs=analytics.DEFAULT_RUNS, force=False):
    """
    รวมทุกอย่างที่วิเคราะห์ได้จากข้อมูลที่มีอยู่แล้ว
    พยากรณ์รายได้สิ้นรอบ คะแนนสุขภาพรายพอร์ต ความเสี่ยงซ่อนเร้น และโอกาสโผล่พ้น HWM
    ผลถูกเก็บแคชไว้สองนาที เพราะหน้าแจ้งเตือนก็เรียกใช้ชุดเดียวกัน
    """
    return analytics.cached(lambda: _intelligence(runs), force=force)


def _intelligence(runs):
    conn = connect()
    try:
        settings, rates, base, kind = _ctx(conn)
        fc = analytics.forecast(conn, runs=runs)

        items = []
        for row in conn.execute("SELECT * FROM accounts WHERE tracked = 1 ORDER BY name").fetchall():
            series = analytics.daily_series(conn, row["id"])
            metrics = analytics.risk_metrics(series)
            hidden = analytics.hidden_risk(series, metrics)
            recovery = analytics.recovery_outlook(conn, row["id"])
            health = analytics.health_score(metrics, hidden, recovery)
            items.append({
                "id": row["id"],
                "name": row["name"],
                "currency": row["currency"],
                "owner": row["owner"],
                "balance_base": to_base(row["balance"], row["currency"], rates, base),
                "health": health,
                "risk": metrics,
                "hidden": hidden,
                "recovery": recovery,
            })

        # เรียงพอร์ตที่น่าห่วงที่สุดขึ้นก่อน คนใช้งานจะได้เห็นเรื่องสำคัญทันที
        items.sort(key=lambda x: (x["health"]["score"] if x["health"]["score"] is not None else 999))

        flags = _build_flags(items, fc, base)
        return {
            "ok": True,
            "base_currency": base,
            "forecast": fc,
            "accounts": items,
            "flags": flags,
            "period_kind": kind,
        }
    finally:
        conn.close()


def _build_flags(items, fc, base):
    """สรุปเรื่องที่ต้องรู้จากผลวิเคราะห์ เรียงตามความรุนแรง"""
    flags = []
    for it in items:
        hidden = it["hidden"]
        if hidden.get("enough") and hidden["level"] == "crit":
            hits = [s["label"] for s in hidden["signals"] if s["hit"]]
            flags.append({
                "level": "critical", "account_id": it["id"],
                "title": "%s มีลายเซ็นกลยุทธ์เสี่ยงพังทีเดียว" % it["name"],
                "detail": "คะแนนความเสี่ยงซ่อนเร้น %d จาก 100 · %s · "
                          "พอร์ตแบบนี้มักกำไรสม่ำเสมอจนถึงวันที่เสียเงินต้นทั้งก้อนในวันเดียว"
                          % (hidden["score"], ", ".join(hits)),
            })
        elif hidden.get("enough") and hidden["level"] == "warn":
            flags.append({
                "level": "warn", "account_id": it["id"],
                "title": "%s มีพฤติกรรมที่ต้องเฝ้าดู" % it["name"],
                "detail": "คะแนนความเสี่ยงซ่อนเร้น %d จาก 100" % hidden["score"],
            })

        rec = it["recovery"]
        if rec.get("under_water"):
            if rec["prob_90"] < 25:
                flags.append({
                    "level": "warn", "account_id": it["id"],
                    "title": "%s มีโอกาสน้อยที่จะกลับมาสร้างรายได้ใน 90 วัน" % it["name"],
                    "detail": "ต้องทำกำไรอีก %s %s จึงพ้นจุดสูงสุดเดิม โอกาสภายใน 90 วันทำการเพียง %s%%"
                              % (_money(rec["gap"]), it["currency"], rec["prob_90"]),
                })

    if fc.get("enough"):
        if fc["prob_below_current"] >= 25:
            flags.append({
                "level": "warn", "account_id": None,
                "title": "ยังไม่ควรจ่ายส่วนแบ่งของรอบนี้ตอนนี้",
                "detail": "มีโอกาส %s%% ที่รายได้สิ้นรอบจะต่ำกว่ายอดที่คิดได้วันนี้ "
                          "ถ้าจ่ายตามยอดปัจจุบันแล้วพอร์ตขาดทุนต่อ จะจ่ายเกินเฉลี่ย %s %s "
                          "และต้องไปตามเก็บคืนภายหลัง"
                          % (fc["prob_below_current"], _money(fc["avg_overpay"]), base),
            })
        if fc.get("prob_hit_target") is not None and fc["prob_hit_target"] < 35:
            flags.append({
                "level": "info", "account_id": None,
                "title": "เป้าหมายรอบนี้มีโอกาสไม่ถึง",
                "detail": "จากการจำลอง %s เส้นทาง มีโอกาสถึงเป้าเพียง %s%% "
                          "ค่ากลางที่คาดว่าจะได้คือ %s %s"
                          % (fc["runs"], fc["prob_hit_target"], _money(fc["p50"]), base),
            })

    order = {"critical": 0, "warn": 1, "info": 2}
    flags.sort(key=lambda f: order.get(f["level"], 3))
    return flags


# ================================================================== ตั้งค่า

ALLOWED_SETTINGS = {
    "base_currency": lambda v: str(v).upper()[:5],
    "period_kind": lambda v: earnings.WEEK if str(v).upper() == earnings.WEEK else earnings.MONTH,
    "default_share_pct": lambda v: str(_clamp(_float(v, 30), 0, 100)),
    "default_hwm": lambda v: "1" if v in (True, 1, "1", "true", "on") else "0",
    "dd_warn_pct": lambda v: str(_clamp(_float(v, 10), 0, 100)),
    "dd_crit_pct": lambda v: str(_clamp(_float(v, 20), 0, 100)),
    "stale_sync_hours": lambda v: str(_clamp(_float(v, 24), 1, 720)),
}


def save_settings(body):
    conn = connect()
    try:
        before_kind = get_setting(conn, "period_kind", earnings.MONTH)
        touched = []
        for key, clean in ALLOWED_SETTINGS.items():
            if key in body:
                set_setting(conn, key, clean(body[key]))
                touched.append(key)
        if not touched:
            return {"ok": False, "error": "ไม่มีค่าที่ต้องบันทึก"}
        after_kind = get_setting(conn, "period_kind", earnings.MONTH)
        if after_kind != before_kind:
            # เปลี่ยนรอบคิดส่วนแบ่งแล้วต้องคิดใหม่ทั้งหมด ไม่งั้นคีย์รอบเก่าจะค้าง
            earnings.recompute_all(conn, after_kind)
        conn.commit()
        return {"ok": True, "message": "บันทึกการตั้งค่าแล้ว", "changed": touched}
    finally:
        conn.close()


def save_rate(body):
    code = (body.get("code") or "").strip().upper()[:5]
    rate = _float(body.get("to_usd"), 0)
    if not code:
        return {"ok": False, "error": "ต้องระบุสกุลเงิน"}
    if rate <= 0:
        return {"ok": False, "error": "อัตราแลกเปลี่ยนต้องมากกว่า 0"}
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO fx_rates(code, to_usd, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET to_usd=excluded.to_usd, updated_at=excluded.updated_at",
            (code, rate, now_iso()),
        )
        conn.commit()
        return {"ok": True, "message": "บันทึกอัตราแลกเปลี่ยน %s แล้ว" % code}
    finally:
        conn.close()


def export_csv(kind="earnings"):
    """ส่งออกเป็นข้อความ CSV ให้ผู้ใช้ดาวน์โหลดไปทำบัญชีต่อได้"""
    conn = connect()
    try:
        lines = []
        if kind == "payouts":
            lines.append("วันที่จ่าย,พอร์ต,รอบ,จำนวน,สกุลเงิน,ช่องทาง,ผู้รับ,หมายเหตุ")
            for r in conn.execute(
                """SELECT p.*, a.name FROM payouts p LEFT JOIN accounts a ON a.id = p.account_id
                   ORDER BY p.paid_at DESC"""
            ).fetchall():
                lines.append(",".join(_csv(x) for x in (
                    r["paid_at"], r["name"] or "", r["period_key"], r["amount"],
                    r["currency"], r["method"], r["payee"], r["note"],
                )))
        else:
            lines.append("รอบ,พอร์ต,สกุลเงิน,กำไรในรอบ,ฐานคิดส่วนแบ่ง,HWM ก่อน,HWM หลัง,ส่วนแบ่ง %,รายได้")
            for r in conn.execute(
                """SELECT k.*, a.name FROM accruals k JOIN accounts a ON a.id = k.account_id
                   ORDER BY k.period_key DESC, a.name"""
            ).fetchall():
                lines.append(",".join(_csv(x) for x in (
                    r["period_key"], r["name"], r["currency"], r["gross"], r["base"],
                    r["hwm_before"], r["hwm_after"], r["share_pct"], r["earning"],
                )))
        return "\n".join(lines)
    finally:
        conn.close()


def _csv(value):
    text = "" if value is None else str(value)
    if any(ch in text for ch in ',"\n'):
        return '"%s"' % text.replace('"', '""')
    return text

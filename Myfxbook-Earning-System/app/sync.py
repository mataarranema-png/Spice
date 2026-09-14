"""
Myfxbook Earning System - การเชื่อมต่อบัญชีและการซิงก์ข้อมูล

โหมดการทำงานมีสองแบบ
    โหมดสาธิต  ใช้พอร์ตตัวอย่างในเครื่อง ไม่ต้องต่ออินเทอร์เน็ต เหมาะกับการลองใช้
    โหมดจริง   เข้าสู่ระบบ Myfxbook แล้วดึงพอร์ตและกำไรรายวันจริงมาเก็บในเครื่อง

รหัสผ่านของ Myfxbook ไม่ถูกบันทึกลงฐานข้อมูล เก็บเฉพาะ session ที่ได้กลับมาเท่านั้น
"""

import random
from datetime import date, datetime, timedelta

from . import earnings, myfxbook
from .database import connect, get_setting, get_settings, now_iso, set_setting

DEFAULT_SYNC_DAYS = 365


# ------------------------------------------------------------------ สถานะ

def status():
    conn = connect()
    try:
        settings = get_settings(conn)
        counts = conn.execute(
            "SELECT COUNT(*) total, COALESCE(SUM(tracked), 0) tracked FROM accounts"
        ).fetchone()
        logs = [dict(r) for r in conn.execute(
            "SELECT * FROM sync_log ORDER BY id DESC LIMIT 12"
        ).fetchall()]
        rates = [dict(r) for r in conn.execute(
            "SELECT code, to_usd, updated_at FROM fx_rates ORDER BY code"
        ).fetchall()]
        return {
            "ok": True,
            "demo_mode": settings.get("demo_mode") == "1",
            "connected": bool(settings.get("mfb_session")),
            "email": settings.get("mfb_email") or "",
            "session_at": settings.get("mfb_session_at") or "",
            "last_sync_at": settings.get("last_sync_at") or "",
            "accounts_total": counts["total"],
            "accounts_tracked": counts["tracked"],
            "logs": logs,
            "rates": rates,
            "settings": {
                "base_currency": settings.get("base_currency"),
                "period_kind": settings.get("period_kind"),
                "default_share_pct": settings.get("default_share_pct"),
                "default_hwm": settings.get("default_hwm"),
                "dd_warn_pct": settings.get("dd_warn_pct"),
                "dd_crit_pct": settings.get("dd_crit_pct"),
                "stale_sync_hours": settings.get("stale_sync_hours"),
            },
        }
    finally:
        conn.close()


def login(email, password):
    try:
        session = myfxbook.login(email, password)
    except myfxbook.MyfxbookError as exc:
        return {"ok": False, "error": str(exc)}
    conn = connect()
    try:
        set_setting(conn, "mfb_session", session)
        set_setting(conn, "mfb_email", (email or "").strip())
        set_setting(conn, "mfb_session_at", now_iso())
        set_setting(conn, "demo_mode", "0")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "message": "เชื่อมต่อ Myfxbook สำเร็จ กดซิงก์เพื่อดึงข้อมูลพอร์ต"}


def logout():
    conn = connect()
    try:
        session = get_setting(conn, "mfb_session", "")
        myfxbook.logout(session)
        set_setting(conn, "mfb_session", "")
        set_setting(conn, "mfb_session_at", "")
        conn.commit()
        return {"ok": True, "message": "ออกจากระบบ Myfxbook แล้ว ข้อมูลที่ซิงก์ไว้ยังอยู่ครบ"}
    finally:
        conn.close()


def set_demo(on):
    conn = connect()
    try:
        set_setting(conn, "demo_mode", "1" if on else "0")
        conn.commit()
        return {
            "ok": True,
            "demo_mode": bool(on),
            "message": "เปลี่ยนเป็นโหมดสาธิตแล้ว" if on else "เปลี่ยนเป็นโหมดข้อมูลจริงแล้ว",
        }
    finally:
        conn.close()


# ------------------------------------------------------------------- ซิงก์

def sync_now(days=DEFAULT_SYNC_DAYS):
    conn = connect()
    started = now_iso()
    try:
        settings = get_settings(conn)
        demo = settings.get("demo_mode") == "1"
        try:
            if demo:
                accounts_n, days_n, detail = _sync_demo(conn)
                mode = "DEMO"
            else:
                session = settings.get("mfb_session") or ""
                if not session:
                    return {"ok": False, "error": "ยังไม่ได้เชื่อมต่อ Myfxbook กรุณาเข้าสู่ระบบก่อน"}
                accounts_n, days_n, detail = _sync_live(conn, session, int(days))
                mode = "LIVE"
        except myfxbook.MyfxbookError as exc:
            conn.execute(
                """INSERT INTO sync_log (started_at, finished_at, ok, mode, accounts_n, days_n, detail)
                   VALUES (?,?,0,?,0,0,?)""",
                (started, now_iso(), "DEMO" if demo else "LIVE", str(exc)),
            )
            conn.commit()
            return {"ok": False, "error": str(exc)}

        kind = settings.get("period_kind") or earnings.MONTH
        periods = earnings.recompute_all(conn, kind)
        set_setting(conn, "last_sync_at", now_iso())
        conn.execute(
            """INSERT INTO sync_log (started_at, finished_at, ok, mode, accounts_n, days_n, detail)
               VALUES (?,?,1,?,?,?,?)""",
            (started, now_iso(), mode, accounts_n, days_n, detail),
        )
        conn.commit()
        return {
            "ok": True,
            "accounts": accounts_n,
            "days": days_n,
            "periods": periods,
            "mode": mode,
            "message": "ซิงก์สำเร็จ %d พอร์ต %d วัน แล้วคิดรายได้ใหม่ %d รอบ" % (accounts_n, days_n, periods),
        }
    finally:
        conn.close()


def _sync_live(conn, session, days):
    raw_accounts = myfxbook.my_accounts(session)
    try:
        raw_accounts = list(raw_accounts) + list(myfxbook.watched_accounts(session))
    except myfxbook.MyfxbookError:
        pass                      # พอร์ตที่ติดตามอยู่ดึงไม่ได้ก็ไม่เป็นไร ใช้เท่าที่มี

    seen = set()
    accounts_n = 0
    for raw in raw_accounts:
        item = myfxbook.normalize_account(raw)
        if item is None or item["mfb_id"] in seen:
            continue
        seen.add(item["mfb_id"])
        _upsert_account(conn, item)
        accounts_n += 1

    end = date.today()
    start = end - timedelta(days=max(1, days))
    days_n = 0
    rows = conn.execute(
        "SELECT id, mfb_id FROM accounts WHERE tracked = 1 AND source = 'LIVE'"
    ).fetchall()
    errors = []
    for row in rows:
        try:
            daily = myfxbook.daily_data(session, row["mfb_id"], start, end)
        except myfxbook.MyfxbookError as exc:
            errors.append("%s: %s" % (row["mfb_id"], exc))
            continue
        days_n += _store_daily(conn, row["id"], daily)
        _refresh_from_daily(conn, row["id"])

    detail = "ดึงข้อมูลจาก Myfxbook %d พอร์ต" % accounts_n
    if errors:
        detail += " (มีพอร์ตที่ดึงไม่ได้ %d รายการ: %s)" % (len(errors), "; ".join(errors[:3]))
    return accounts_n, days_n, detail


def _sync_demo(conn):
    """ต่อเส้นกราฟของพอร์ตตัวอย่างให้มาถึงวันนี้ เพื่อให้โหมดสาธิตดูมีชีวิต"""
    rnd = random.Random(int(date.today().strftime("%Y%m%d")))
    today = date.today()
    accounts = conn.execute("SELECT * FROM accounts WHERE source = 'DEMO'").fetchall()
    days_n = 0
    for acc in accounts:
        last = conn.execute(
            "SELECT day, balance FROM daily WHERE account_id = ? ORDER BY day DESC LIMIT 1",
            (acc["id"],),
        ).fetchone()
        if last is None:
            continue
        cursor = datetime.strptime(last["day"], "%Y-%m-%d").date()
        balance = float(last["balance"])
        rows = []
        while cursor < today:
            cursor += timedelta(days=1)
            if cursor.weekday() >= 5:
                continue
            shock = rnd.gauss(0.0015, 0.012)
            profit = round(balance * shock, 2)
            balance = round(balance + profit, 2)
            rows.append({
                "day": cursor.isoformat(),
                "balance": balance,
                "equity": balance,
                "profit": profit,
                "pips": round(profit / max(balance, 1) * 8000, 1),
                "lots": round(abs(rnd.gauss(1.2, 0.4)), 2),
                "growth_pct": round(profit / max(balance - profit, 1) * 100, 4),
            })
        days_n += _store_daily(conn, acc["id"], rows)
        _refresh_from_daily(conn, acc["id"])
    return len(accounts), days_n, "อัปเดตพอร์ตตัวอย่างถึงวันที่ %s" % today.isoformat()


def _upsert_account(conn, item):
    existing = conn.execute(
        "SELECT id FROM accounts WHERE mfb_id = ?", (item["mfb_id"],)
    ).fetchone()
    stamp = now_iso()
    if existing:
        conn.execute(
            """UPDATE accounts SET name=?, account_no=?, broker=?, platform=?, currency=?,
                   balance=?, equity=?, profit=?, gain_pct=?, drawdown_pct=?,
                   deposits=?, withdrawals=?, first_trade_at=?, last_update=?, is_demo=?, source='LIVE'
               WHERE id=?""",
            (
                item["name"], item["account_no"], item["broker"], item["platform"], item["currency"],
                item["balance"], item["equity"], item["profit"], item["gain_pct"], item["drawdown_pct"],
                item["deposits"], item["withdrawals"], item["first_trade_at"], item["last_update"],
                item["is_demo"], existing["id"],
            ),
        )
        return existing["id"]

    cur = conn.execute(
        """INSERT INTO accounts
           (mfb_id, name, account_no, broker, platform, currency, owner,
            balance, equity, profit, gain_pct, drawdown_pct, deposits, withdrawals,
            first_trade_at, last_update, is_demo, tracked, source, created_at)
           VALUES (?,?,?,?,?,?,'',?,?,?,?,?,?,?,?,?,?,1,'LIVE',?)""",
        (
            item["mfb_id"], item["name"], item["account_no"], item["broker"], item["platform"],
            item["currency"], item["balance"], item["equity"], item["profit"], item["gain_pct"],
            item["drawdown_pct"], item["deposits"], item["withdrawals"], item["first_trade_at"],
            item["last_update"], item["is_demo"], stamp,
        ),
    )
    account_id = cur.lastrowid
    share = float(get_setting(conn, "default_share_pct", "30") or 30)
    use_hwm = 1 if get_setting(conn, "default_hwm", "1") == "1" else 0
    conn.execute(
        """INSERT OR IGNORE INTO rules
           (account_id, label, share_pct, use_hwm, min_profit, fixed_fee, active, updated_at)
           VALUES (?,?,?,?,0,0,1,?)""",
        (account_id, "ส่วนแบ่งกำไร", share, use_hwm, stamp),
    )
    return account_id


def _store_daily(conn, account_id, rows):
    payload = [
        (
            account_id, r["day"], r.get("balance", 0), r.get("equity", 0), r.get("profit", 0),
            r.get("pips", 0), r.get("lots", 0), r.get("growth_pct", 0),
        )
        for r in rows if r.get("day")
    ]
    if not payload:
        return 0
    conn.executemany(
        """INSERT INTO daily (account_id, day, balance, equity, profit, pips, lots, growth_pct)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(account_id, day) DO UPDATE SET
             balance=excluded.balance, equity=excluded.equity, profit=excluded.profit,
             pips=excluded.pips, lots=excluded.lots, growth_pct=excluded.growth_pct""",
        payload,
    )
    return len(payload)


def _refresh_from_daily(conn, account_id):
    """คำนวณยอดคงเหลือ กำไรสะสม และ drawdown สูงสุดใหม่จากข้อมูลรายวันที่เพิ่งเก็บ"""
    rows = conn.execute(
        "SELECT day, balance, profit FROM daily WHERE account_id = ? ORDER BY day", (account_id,)
    ).fetchall()
    if not rows:
        return
    balance = float(rows[-1]["balance"])
    total_profit = round(sum(float(r["profit"]) for r in rows), 2)
    start_balance = float(rows[0]["balance"]) - float(rows[0]["profit"])
    peak = start_balance if start_balance > 0 else float(rows[0]["balance"])
    max_dd = 0.0
    for r in rows:
        value = float(r["balance"])
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak * 100)
    gain = round(total_profit / start_balance * 100, 2) if start_balance > 0 else 0.0
    conn.execute(
        """UPDATE accounts SET balance=?, equity=?, profit=?, gain_pct=?, drawdown_pct=?,
               last_update=?, first_trade_at=COALESCE(NULLIF(first_trade_at, ''), ?)
           WHERE id=?""",
        (balance, balance, total_profit, gain, round(max_dd, 2), now_iso(),
         rows[0]["day"], account_id),
    )

"""
Myfxbook Earning System - ศูนย์วิเคราะห์อัจฉริยะ

ไฟล์นี้ทำสามอย่างที่หน้าสรุปทั่วไปทำไม่ได้

1. พยากรณ์รายได้สิ้นรอบ
   สุ่มซ้ำ (bootstrap) จากผลตอบแทนรายวันจริงของแต่ละพอร์ต จำลองอนาคตหลายพันเส้นทาง
   แล้ววิ่งผ่านกติกา High-Water Mark เดิมทุกเส้นทาง จึงได้คำตอบเป็นช่วงความน่าจะเป็น
   ไม่ใช่ตัวเลขเดียวลอย ๆ และตอบได้ว่า "โอกาสถึงเป้าสิ้นเดือนกี่เปอร์เซ็นต์"

2. วัดความเสี่ยงด้วยมาตรฐานเดียวกับกองทุน
   Sharpe, Sortino, Calmar, VaR และ Expected Shortfall คำนวณจากผลตอบแทนรายวันจริง

3. จับพอร์ตที่ซ่อนระเบิด
   พอร์ตแบบ martingale หรือ grid จะมีกราฟสวยมากจนถึงวันที่พังทีเดียวหมด
   ตัวตรวจจับในไฟล์นี้ดูพฤติกรรมที่ทรยศตัวเอง เช่น เพิ่มขนาดไม้หลังวันขาดทุน
   ชนะบ่อยผิดปกติแต่วันแพ้ใหญ่กว่าวันชนะหลายเท่า และกราฟเรียบผิดธรรมชาติ

ใช้เฉพาะไลบรารีมาตรฐานของ Python ไม่ต้องติดตั้ง numpy หรืออะไรเพิ่ม
"""

import math
import random
import threading
import time
from datetime import date, datetime, timedelta

from . import earnings
from .database import fx_map, get_settings, to_base

# จำนวนวันทำการต่อปี ใช้แปลงค่าความเสี่ยงรายวันเป็นรายปี
TRADING_DAYS = 252

# จำนวนเส้นทางที่จำลอง มากขึ้นแม่นขึ้นแต่ช้าลง ค่านี้เร็วพอสำหรับเครื่องทั่วไป
DEFAULT_RUNS = 2000

# ต้องมีข้อมูลอย่างน้อยเท่านี้วันจึงจะวิเคราะห์ได้อย่างมีความหมาย
MIN_DAYS = 20

# ตัวหารที่เล็กกว่านี้ถือว่าเป็นศูนย์ กันอัตราส่วนพุ่งเป็นค่ามหาศาลจากเศษทศนิยม
EPS = 1e-12

# ผลวิเคราะห์ถูกเรียกจากหลายหน้า จึงเก็บไว้ชั่วคราวเพื่อไม่ให้คิดซ้ำทุกครั้งที่เปลี่ยนหน้า
CACHE_TTL = 120
_cache = {"at": 0.0, "value": None}
_cache_lock = threading.Lock()


def cached(builder, force=False):
    """คืนผลวิเคราะห์ล่าสุด ถ้ายังไม่เกินอายุก็ใช้ของเดิม"""
    with _cache_lock:
        fresh = _cache["value"] is not None and (time.time() - _cache["at"]) < CACHE_TTL
        if fresh and not force:
            return _cache["value"]
    value = builder()
    with _cache_lock:
        _cache["at"] = time.time()
        _cache["value"] = value
    return value


def invalidate():
    """ล้างแคชเมื่อข้อมูลเปลี่ยน เช่น ซิงก์ใหม่หรือแก้เงื่อนไขส่วนแบ่ง"""
    with _cache_lock:
        _cache["at"] = 0.0
        _cache["value"] = None


# ======================================================== ตัวช่วยทางสถิติพื้นฐาน

def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _stdev(values):
    """ส่วนเบี่ยงเบนมาตรฐานแบบตัวอย่าง (หารด้วย n-1)"""
    n = len(values)
    if n < 2:
        return 0.0
    avg = _mean(values)
    return math.sqrt(sum((v - avg) ** 2 for v in values) / (n - 1))


def _percentile(sorted_values, pct):
    """
    เปอร์เซ็นไทล์แบบเชิงเส้น รับลิสต์ที่เรียงแล้ว
    pct เป็น 0-100 เช่น 5 คือเปอร์เซ็นไทล์ที่ 5
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * (pct / 100.0)
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return sorted_values[int(pos)]
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)


def _safe_div(a, b, fallback=0.0):
    return a / b if b else fallback


def _ratio(num, den):
    """
    อัตราส่วนที่คืน None เมื่อตัวหารเล็กจนไม่มีความหมาย

    จำเป็นเพราะผลตอบแทนที่คงที่เป๊ะจะให้ส่วนเบี่ยงเบนเป็นเศษทศนิยมจิ๋ว ๆ แทนที่จะเป็นศูนย์
    ถ้าหารตรง ๆ จะได้ค่าอย่าง 2.4e16 ซึ่งไม่ใช่ความจริงและทำให้คะแนนสุขภาพเพี้ยนทั้งระบบ
    """
    if den is None or abs(den) < EPS or abs(den) <= abs(num) * 1e-9:
        return None
    return num / den


# ============================================================ ผลตอบแทนรายวัน

def daily_series(conn, account_id):
    """
    ดึงกำไรรายวันพร้อมยอดเงินต้นรอบวัน แล้วแปลงเป็นผลตอบแทนเป็นสัดส่วน

    ต้องใช้ผลตอบแทนเป็นสัดส่วน ไม่ใช่จำนวนเงิน เพราะพอร์ตที่โตขึ้นย่อมทำกำไร
    เป็นเม็ดเงินมากขึ้นโดยที่ฝีมือเท่าเดิม ถ้าสุ่มจากจำนวนเงินดิบจะพยากรณ์เพี้ยน
    """
    rows = conn.execute(
        "SELECT day, balance, profit, lots FROM daily WHERE account_id = ? ORDER BY day",
        (account_id,),
    ).fetchall()

    out = []
    for row in rows:
        profit = float(row["profit"] or 0.0)
        balance = float(row["balance"] or 0.0)
        opening = balance - profit          # ยอดเงินก่อนผลของวันนั้น
        if opening <= 0:
            continue
        out.append({
            "day": row["day"],
            "profit": profit,
            "balance": balance,
            "lots": float(row["lots"] or 0.0),
            "ret": profit / opening,
        })
    return out


# ============================================================== วัดความเสี่ยง

def risk_metrics(series):
    """ชุดตัววัดความเสี่ยงมาตรฐานที่กองทุนใช้ประเมินผู้จัดการพอร์ต"""
    if len(series) < MIN_DAYS:
        return {"enough": False, "days": len(series)}

    rets = [s["ret"] for s in series]
    profits = [s["profit"] for s in series]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]

    avg_ret = _mean(rets)
    sd = _stdev(rets)
    downside = [r for r in rets if r < 0]
    # ใช้ตัวหารเป็นจำนวนวันทั้งหมด ไม่ใช่เฉพาะวันติดลบ เป็นนิยามมาตรฐานของ Sortino
    downside_sd = math.sqrt(sum(r * r for r in downside) / len(rets)) if downside else 0.0

    # เส้นยอดเงินสะสมแบบทบต้น ใช้หา drawdown ที่ลึกที่สุดและระยะเวลาที่จมน้ำ
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    underwater = 0
    longest_underwater = 0
    for r in rets:
        equity *= (1 + r)
        if equity >= peak:
            peak = equity
            underwater = 0
        else:
            underwater += 1
            longest_underwater = max(longest_underwater, underwater)
            max_dd = max(max_dd, (peak - equity) / peak)

    years = len(rets) / TRADING_DAYS
    total_growth = equity - 1
    annual_return = ((equity ** (1 / years)) - 1) if years > 0 and equity > 0 else 0.0

    ordered = sorted(rets)
    var95 = _percentile(ordered, 5)                    # วันแย่ระดับ 1 ใน 20
    tail = [r for r in ordered if r <= var95] or [var95]
    cvar95 = _mean(tail)                               # ค่าเฉลี่ยของวันที่แย่กว่านั้น

    last_balance = series[-1]["balance"]

    sharpe = _ratio(avg_ret, sd)
    sortino = _ratio(avg_ret, downside_sd)
    calmar = _ratio(annual_return, max_dd)

    return {
        "enough": True,
        "days": len(rets),
        "sharpe": round(sharpe * math.sqrt(TRADING_DAYS), 2) if sharpe is not None else None,
        "sortino": round(sortino * math.sqrt(TRADING_DAYS), 2) if sortino is not None else None,
        "calmar": round(calmar, 2) if calmar is not None else None,
        "annual_return_pct": round(annual_return * 100, 2),
        "total_growth_pct": round(total_growth * 100, 2),
        "max_dd_pct": round(max_dd * 100, 2),
        "longest_underwater": longest_underwater,
        "volatility_pct": round(sd * math.sqrt(TRADING_DAYS) * 100, 2),
        "win_rate_pct": round(_safe_div(len(wins), len(profits)) * 100, 1),
        "profit_factor": round(_safe_div(sum(wins), abs(sum(losses))), 2) if losses else None,
        "avg_win": round(_mean(wins), 2) if wins else 0.0,
        "avg_loss": round(_mean(losses), 2) if losses else 0.0,
        "best_day": round(max(profits), 2),
        "worst_day": round(min(profits), 2),
        # VaR และ Expected Shortfall แปลงกลับเป็นเม็ดเงินตามขนาดพอร์ตปัจจุบัน
        "var95_pct": round(var95 * 100, 2),
        "var95_money": round(var95 * last_balance, 2),
        "cvar95_pct": round(cvar95 * 100, 2),
        "cvar95_money": round(cvar95 * last_balance, 2),
    }


# ==================================================== จับพอร์ตที่ซ่อนระเบิด

def hidden_risk(series, metrics):
    """
    ตรวจลายเซ็นของกลยุทธ์ที่ดูดีจนถึงวันพัง เช่น martingale และ grid

    พอร์ตพวกนี้อันตรายเป็นพิเศษกับระบบส่วนแบ่ง เพราะจะจ่ายส่วนแบ่งให้เจ้าของพอร์ต
    ไปเรื่อย ๆ หลายเดือน แล้ววันหนึ่งลูกค้าเสียเงินต้นทั้งก้อนในวันเดียว
    """
    if len(series) < MIN_DAYS or not metrics.get("enough"):
        return {"enough": False, "score": 0, "level": "unknown", "signals": []}

    signals = []
    score = 0

    # สัญญาณ 1 เพิ่มขนาดไม้หลังวันที่ขาดทุน คือหัวใจของ martingale
    pairs = [(series[i - 1]["profit"], series[i]["lots"])
             for i in range(1, len(series)) if series[i]["lots"] > 0]
    after_loss = [lot for prev, lot in pairs if prev < 0]
    after_win = [lot for prev, lot in pairs if prev > 0]
    lot_ratio = None
    if len(after_loss) >= 5 and len(after_win) >= 5:
        lot_ratio = _safe_div(_mean(after_loss), _mean(after_win), 1.0)
        hit = lot_ratio >= 1.35
        if hit:
            score += 35
        signals.append({
            "key": "lot_after_loss", "hit": hit,
            "label": "เพิ่มขนาดไม้หลังวันขาดทุน",
            "detail": "วันหลังขาดทุนเปิดไม้ใหญ่กว่าวันหลังได้กำไร %.2f เท่า" % lot_ratio
                      if hit else
                      "ขนาดไม้หลังวันขาดทุนใกล้เคียงปกติ (%.2f เท่า)" % lot_ratio,
        })

    # สัญญาณ 2 ชนะบ่อยมากแต่วันแพ้ใหญ่กว่าวันชนะหลายเท่า คือลายเซ็นของ grid
    win_rate = metrics["win_rate_pct"]
    avg_win = metrics["avg_win"]
    avg_loss = abs(metrics["avg_loss"])
    payoff = _safe_div(avg_win, avg_loss, 0.0)
    hit = win_rate >= 75 and payoff < 0.55 and avg_loss > 0
    if hit:
        score += 30
    signals.append({
        "key": "grid_shape", "hit": hit,
        "label": "ชนะบ่อยแต่แพ้หนัก",
        "detail": "ชนะ %.0f%% ของวัน แต่วันแพ้เฉลี่ยใหญ่กว่าวันชนะ %.1f เท่า"
                  % (win_rate, _safe_div(avg_loss, avg_win, 0.0))
                  if hit else
                  "อัตราส่วนกำไรต่อขาดทุนอยู่ในเกณฑ์ปกติ",
    })

    # สัญญาณ 3 วันแย่ที่สุดใหญ่กว่าวันแย่ทั่วไปมาก แปลว่าความเสี่ยงกระจุกตัว
    losses = sorted(s["profit"] for s in series if s["profit"] < 0)
    tail_ratio = None
    if len(losses) >= 8:
        typical_loss = abs(_percentile(losses, 50))
        worst = abs(losses[0])
        tail_ratio = _safe_div(worst, typical_loss, 0.0)
        hit = tail_ratio >= 8
        if hit:
            score += 20
        signals.append({
            "key": "fat_tail", "hit": hit,
            "label": "ความเสียหายกระจุกในวันเดียว",
            "detail": "วันแย่ที่สุดหนักกว่าวันขาดทุนทั่วไป %.1f เท่า" % tail_ratio,
        })

    # สัญญาณ 4 กราฟเรียบเกินจริง ผลตอบแทนแทบไม่แกว่งแต่ยังมีหางขาดทุนยาว
    smooth = None
    if metrics["volatility_pct"] > 0:
        smooth = _safe_div(abs(metrics["cvar95_pct"]), metrics["volatility_pct"] / math.sqrt(TRADING_DAYS), 0.0)
        hit = smooth >= 3.5 and win_rate >= 70
        if hit:
            score += 15
        signals.append({
            "key": "too_smooth", "hit": hit,
            "label": "กราฟเรียบผิดธรรมชาติ",
            "detail": "ความเสียหายส่วนหางใหญ่กว่าความผันผวนปกติ %.1f เท่า" % smooth,
        })

    score = min(100, score)
    level = "crit" if score >= 60 else "warn" if score >= 30 else "ok"
    return {
        "enough": True,
        "score": score,
        "level": level,
        "signals": signals,
        "lot_ratio": round(lot_ratio, 2) if lot_ratio else None,
        "tail_ratio": round(tail_ratio, 1) if tail_ratio else None,
    }


# ================================================================ พยากรณ์

def _period_state(conn, account_id, period_key, kind):
    """
    สถานะของพอร์ตในรอบปัจจุบัน ที่จำเป็นต่อการจำลองรายได้
    ต้องรู้ทั้งกำไรสะสมก่อนเข้ารอบ จุดสูงสุดเดิม และกำไรที่ทำไปแล้วในรอบนี้
    """
    start_day, end_day = earnings.period_bounds(period_key)

    before = conn.execute(
        "SELECT COALESCE(SUM(profit), 0) v FROM daily WHERE account_id = ? AND day < ?",
        (account_id, start_day),
    ).fetchone()["v"]
    so_far = conn.execute(
        "SELECT COALESCE(SUM(profit), 0) v FROM daily "
        "WHERE account_id = ? AND day >= ? AND day <= ?",
        (account_id, start_day, end_day),
    ).fetchone()["v"]

    row = conn.execute(
        "SELECT hwm_before FROM accruals WHERE account_id = ? AND period_key = ?",
        (account_id, period_key),
    ).fetchone()
    if row is not None:
        hwm_before = float(row["hwm_before"])
    else:
        # ยังไม่เคยคิดรอบนี้ จุดสูงสุดเดิมคือค่าสูงสุดที่เคยคิดไว้ในรอบก่อน ๆ
        prev = conn.execute(
            "SELECT COALESCE(MAX(hwm_after), 0) v FROM accruals "
            "WHERE account_id = ? AND period_key < ?",
            (account_id, period_key),
        ).fetchone()
        hwm_before = float(prev["v"])

    return {
        "cum_before": float(before),
        "gross_so_far": float(so_far),
        "hwm_before": hwm_before,
        "start_day": start_day,
        "end_day": end_day,
    }


def _earning_of(gross, cum_before, hwm_before, rule):
    """
    คิดรายได้ส่วนแบ่งจากกำไรของรอบ ใช้กติกาเดียวกับ earnings.recompute_account
    ทุกเส้นทางที่จำลองต้องผ่านกติกานี้ ผลพยากรณ์จึงสอดคล้องกับตัวเลขจริงที่ระบบคิด
    """
    if not rule["active"]:
        return 0.0
    if rule["use_hwm"]:
        cum_end = cum_before + gross
        base = max(0.0, cum_end - hwm_before)
        base = min(base, gross) if gross > 0 else 0.0
    else:
        base = max(0.0, gross)
    if base <= 0 or base < rule["min_profit"]:
        return 0.0
    return base * rule["share_pct"] / 100.0 + rule["fixed_fee"]


def _business_days_left(end_day):
    """นับเฉพาะวันจันทร์ถึงศุกร์ที่เหลือในรอบ ตลาดปิดเสาร์อาทิตย์"""
    today = date.today()
    end = datetime.strptime(end_day, "%Y-%m-%d").date()
    n = 0
    cursor = today
    while cursor < end:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            n += 1
    return n


def forecast(conn, runs=DEFAULT_RUNS, seed=None):
    """
    จำลองรายได้ส่วนแบ่งรวมถึงสิ้นรอบปัจจุบัน

    วิธี bootstrap: สุ่มหยิบผลตอบแทนรายวันจริงในอดีตมาเรียงใหม่แบบสุ่ม ทำซ้ำหลายพันครั้ง
    ข้อดีคือไม่ต้องสมมติว่าผลตอบแทนเป็นโค้งระฆัง ซึ่งผลตอบแทนการเทรดไม่เคยเป็น
    ทุกเส้นทางถูกคิดส่วนแบ่งผ่านกติกา High-Water Mark เดิม
    """
    rnd = random.Random(seed if seed is not None else 20260101)
    settings = get_settings(conn)
    rates = fx_map(conn)
    base_cur = (settings.get("base_currency") or "USD").upper()
    kind = settings.get("period_kind") or earnings.MONTH
    period = earnings.current_period(kind)
    start_day, end_day = earnings.period_bounds(period)
    days_left = _business_days_left(end_day)

    accounts = conn.execute("SELECT * FROM accounts WHERE tracked = 1").fetchall()
    rules = {r["account_id"]: r for r in conn.execute("SELECT * FROM rules").fetchall()}

    plans = []
    current_total = 0.0
    for acc in accounts:
        series = daily_series(conn, acc["id"])
        rule_row = rules.get(acc["id"])
        rule = {
            "share_pct": float(rule_row["share_pct"]) if rule_row else 0.0,
            "use_hwm": bool(rule_row["use_hwm"]) if rule_row else True,
            "min_profit": float(rule_row["min_profit"]) if rule_row else 0.0,
            "fixed_fee": float(rule_row["fixed_fee"]) if rule_row else 0.0,
            "active": bool(rule_row["active"]) if rule_row else False,
        }
        state = _period_state(conn, acc["id"], period, kind)
        now_earning = _earning_of(state["gross_so_far"], state["cum_before"],
                                  state["hwm_before"], rule)
        current_total += to_base(now_earning, acc["currency"], rates, base_cur)

        if len(series) >= MIN_DAYS:
            plans.append({
                "account": acc,
                "rule": rule,
                "state": state,
                "pool": [s["ret"] for s in series],
                "balance": series[-1]["balance"],
                "fx": (acc["currency"], rates, base_cur),
            })

    if not plans or days_left <= 0:
        return {
            "enough": False,
            "reason": "ข้อมูลไม่พอพยากรณ์" if not plans else "รอบนี้ไม่เหลือวันทำการแล้ว",
            "period": period, "period_label": earnings.period_label(period),
            "days_left": days_left, "current": round(current_total, 2),
            "base_currency": base_cur,
        }

    # เก็บรายได้รวมของทุกเส้นทาง และเส้นทางรายวันเพื่อวาดกราฟพัด
    totals = []
    per_day = [[] for _ in range(days_left + 1)]

    for _ in range(runs):
        day_totals = [0.0] * (days_left + 1)
        for plan in plans:
            pool = plan["pool"]
            state = plan["state"]
            balance = plan["balance"]
            gross = state["gross_so_far"]
            cur, rate_map, target = plan["fx"]

            # วันที่ 0 คือสถานะปัจจุบัน ยังไม่จำลองอะไร
            day_totals[0] += to_base(
                _earning_of(gross, state["cum_before"], state["hwm_before"], plan["rule"]),
                cur, rate_map, target)

            for d in range(1, days_left + 1):
                r = pool[rnd.randrange(len(pool))]
                profit = balance * r
                balance += profit
                gross += profit
                day_totals[d] += to_base(
                    _earning_of(gross, state["cum_before"], state["hwm_before"], plan["rule"]),
                    cur, rate_map, target)

        for d in range(days_left + 1):
            per_day[d].append(day_totals[d])
        totals.append(day_totals[days_left])

    totals.sort()

    # ความเสี่ยงของการจ่ายเงินเร็วเกินไป
    # รายได้ของรอบคิดจากกำไรทั้งรอบ ถ้าพอร์ตขาดทุนต่อจนสิ้นรอบ ยอดที่คิดได้วันนี้จะลดลง
    # ใครจ่ายตามยอดวันนี้ไปก่อน ก็มีโอกาสจ่ายเกินและต้องไปตามเก็บคืนทีหลัง
    below = [t for t in totals if t < current_total - 0.009]
    prob_below = round(len(below) / len(totals) * 100, 1)
    avg_short = round(current_total - _mean(below), 2) if below else 0.0

    goal = conn.execute("SELECT target FROM goals WHERE period_key = ?", (period,)).fetchone()
    target = float(goal["target"]) if goal else 0.0

    fan = []
    for d in range(days_left + 1):
        col = sorted(per_day[d])
        fan.append({
            "d": d,
            "p10": round(_percentile(col, 10), 2),
            "p50": round(_percentile(col, 50), 2),
            "p90": round(_percentile(col, 90), 2),
        })

    return {
        "enough": True,
        "runs": runs,
        "accounts_n": len(plans),
        "period": period,
        "period_label": earnings.period_label(period),
        "start_day": start_day,
        "end_day": end_day,
        "days_left": days_left,
        "base_currency": base_cur,
        "current": round(current_total, 2),
        "p10": round(_percentile(totals, 10), 2),
        "p25": round(_percentile(totals, 25), 2),
        "p50": round(_percentile(totals, 50), 2),
        "p75": round(_percentile(totals, 75), 2),
        "p90": round(_percentile(totals, 90), 2),
        "mean": round(_mean(totals), 2),
        "target": round(target, 2),
        "prob_hit_target": round(sum(1 for t in totals if t >= target) / len(totals) * 100, 1)
                           if target > 0 else None,
        "prob_any_earning": round(sum(1 for t in totals if t > 0.009) / len(totals) * 100, 1),
        "prob_below_current": prob_below,
        "avg_overpay": avg_short,
        "fan": fan,
    }


def recovery_outlook(conn, account_id, runs=1000, seed=None):
    """
    พอร์ตที่จมอยู่ใต้ High-Water Mark จะยังไม่สร้างรายได้ส่วนแบ่ง
    ฟังก์ชันนี้ตอบว่าโอกาสโผล่พ้นน้ำภายใน 30, 60, 90 วันทำการเป็นเท่าไร
    """
    series = daily_series(conn, account_id)
    if len(series) < MIN_DAYS:
        return {"enough": False}

    row = conn.execute(
        "SELECT hwm_after FROM accruals WHERE account_id = ? ORDER BY period_key DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    if row is None:
        return {"enough": False}

    cum = sum(s["profit"] for s in series)
    gap = float(row["hwm_after"]) - cum
    if gap <= 0.01:
        return {"enough": True, "under_water": False, "gap": 0.0}

    rnd = random.Random(seed if seed is not None else 20260202)
    pool = [s["ret"] for s in series]
    start_balance = series[-1]["balance"]
    horizons = (30, 60, 90)
    hits = {h: 0 for h in horizons}
    days_needed = []

    for _ in range(runs):
        balance = start_balance
        gained = 0.0
        reached = None
        for d in range(1, max(horizons) + 1):
            profit = balance * pool[rnd.randrange(len(pool))]
            balance += profit
            gained += profit
            if gained >= gap:
                reached = d
                break       # นับว่า "เคยแตะจุดสูงสุดเดิม" ก็พอ ไม่ต้องจำลองต่อ
        if reached is not None:
            days_needed.append(reached)
            for h in horizons:
                if reached <= h:
                    hits[h] += 1

    return {
        "enough": True,
        "under_water": True,
        "gap": round(gap, 2),
        "prob_30": round(hits[30] / runs * 100, 1),
        "prob_60": round(hits[60] / runs * 100, 1),
        "prob_90": round(hits[90] / runs * 100, 1),
        # ค่ากลางนี้คิดจากเฉพาะเส้นทางที่กลับมาได้สำเร็จ จึงต้องอ่านคู่กับความน่าจะเป็นเสมอ
        "median_days": int(_percentile(sorted(days_needed), 50)) if days_needed else None,
        "success_runs": len(days_needed),
    }


# ====================================================== คะแนนสุขภาพของพอร์ต

def health_score(metrics, hidden, recovery):
    """
    รวมทุกอย่างเป็นคะแนน 0-100 พร้อมเหตุผลเป็นภาษาคน
    ตั้งใจให้ความเสี่ยงซ่อนเร้นถ่วงคะแนนหนักที่สุด เพราะมันคือสิ่งที่ทำให้เสียเงินต้น
    """
    if not metrics.get("enough"):
        return {"score": None, "grade": "ข้อมูลไม่พอ", "tone": "mute", "reasons": []}

    reasons = []
    score = 50.0

    sharpe = metrics["sharpe"]
    if sharpe is None:
        reasons.append(("warn", "ผลตอบแทนแทบไม่แกว่งเลย วัดความเสี่ยงตามปกติไม่ได้"))
    elif sharpe >= 2:
        score += 20; reasons.append(("ok", "ผลตอบแทนต่อความเสี่ยงดีมาก (Sharpe %.2f)" % sharpe))
    elif sharpe >= 1:
        score += 12; reasons.append(("ok", "ผลตอบแทนต่อความเสี่ยงอยู่ในเกณฑ์ดี (Sharpe %.2f)" % sharpe))
    elif sharpe >= 0:
        score += 2; reasons.append(("warn", "ผลตอบแทนต่อความเสี่ยงยังไม่เด่น (Sharpe %.2f)" % sharpe))
    else:
        score -= 15; reasons.append(("crit", "ผลตอบแทนติดลบเมื่อเทียบความเสี่ยง (Sharpe %.2f)" % sharpe))

    dd = metrics["max_dd_pct"]
    if dd <= 10:
        score += 15; reasons.append(("ok", "ขาดทุนสะสมลึกสุดเพียง %.1f%%" % dd))
    elif dd <= 20:
        score += 5; reasons.append(("warn", "ขาดทุนสะสมลึกสุด %.1f%%" % dd))
    elif dd <= 35:
        score -= 10; reasons.append(("warn", "ขาดทุนสะสมลึกถึง %.1f%%" % dd))
    else:
        score -= 22; reasons.append(("crit", "ขาดทุนสะสมลึกมากถึง %.1f%%" % dd))

    pf = metrics["profit_factor"]
    if pf is not None:
        if pf >= 1.5:
            score += 10; reasons.append(("ok", "กำไรรวมมากกว่าขาดทุนรวม %.2f เท่า" % pf))
        elif pf >= 1.1:
            score += 4
        elif pf < 1:
            score -= 12; reasons.append(("crit", "ขาดทุนรวมมากกว่ากำไรรวม (Profit Factor %.2f)" % pf))

    if hidden.get("enough") and hidden["score"] > 0:
        score -= hidden["score"] * 0.45
        if hidden["level"] == "crit":
            reasons.append(("crit", "พบลายเซ็นกลยุทธ์เสี่ยงพังทีเดียว คะแนนความเสี่ยงซ่อนเร้น %d" % hidden["score"]))
        elif hidden["level"] == "warn":
            reasons.append(("warn", "มีพฤติกรรมที่ต้องเฝ้าดู คะแนนความเสี่ยงซ่อนเร้น %d" % hidden["score"]))

    if recovery.get("under_water"):
        score -= 8
        reasons.append(("warn", "ยังจมอยู่ใต้จุดสูงสุดเดิม ต้องทำกำไรอีก %.2f จึงจะกลับมาสร้างรายได้" % recovery["gap"]))

    score = max(0, min(100, round(score)))
    if score >= 75:
        grade, tone = "แข็งแรง", "ok"
    elif score >= 55:
        grade, tone = "พอใช้", "warn"
    elif score >= 35:
        grade, tone = "ต้องเฝ้าระวัง", "warn"
    else:
        grade, tone = "เสี่ยงสูง", "crit"

    order = {"crit": 0, "warn": 1, "ok": 2}
    reasons.sort(key=lambda r: order.get(r[0], 3))
    return {
        "score": score, "grade": grade, "tone": tone,
        "reasons": [{"tone": t, "text": txt} for t, txt in reasons],
    }

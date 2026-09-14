"""
Myfxbook Earning System - ตัวเชื่อมต่อ Myfxbook API

ใช้ urllib ของ Python ล้วน ๆ ไม่ต้องติดตั้งไลบรารีเพิ่ม
เอกสารอ้างอิง: https://www.myfxbook.com/api

ขั้นตอนใช้งาน
    1. login(email, password) -> session
    2. my_accounts(session)   -> รายชื่อพอร์ต
    3. daily_data(session, id, start, end) -> กำไรรายวัน
Myfxbook จะตอบ {"error": false, ...} เมื่อสำเร็จ และ {"error": true, "message": "..."} เมื่อไม่สำเร็จ
"""

import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

API_BASE = "https://www.myfxbook.com/api"
TIMEOUT = 25
USER_AGENT = "Myfxbook-Earning-System/1.0 (+local)"


class MyfxbookError(Exception):
    """ข้อผิดพลาดที่อธิบายเป็นภาษาคนได้ ส่งต่อให้หน้าเว็บแสดงได้เลย"""


def _call(endpoint, params):
    url = "%s/%s.json?%s" % (API_BASE, endpoint, urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            raw = res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise MyfxbookError("Myfxbook ตอบกลับผิดพลาด (HTTP %s)" % exc.code) from exc
    except urllib.error.URLError as exc:
        raise MyfxbookError("ต่ออินเทอร์เน็ตไปที่ Myfxbook ไม่ได้: %s" % exc.reason) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise MyfxbookError("Myfxbook ตอบช้าเกินไป ลองใหม่อีกครั้ง") from exc
    except ssl.SSLError as exc:
        raise MyfxbookError("เชื่อมต่อแบบปลอดภัยไม่สำเร็จ: %s" % exc) from exc

    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise MyfxbookError("Myfxbook ส่งข้อมูลที่อ่านไม่ออกกลับมา") from exc

    if isinstance(data, dict) and data.get("error"):
        raise MyfxbookError(data.get("message") or "Myfxbook ปฏิเสธคำขอนี้")
    return data


def login(email, password):
    """เข้าสู่ระบบแล้วคืน session id ที่ใช้กับคำสั่งอื่น ๆ"""
    email = (email or "").strip()
    if not email or not password:
        raise MyfxbookError("ต้องกรอกอีเมลและรหัสผ่านของ Myfxbook")
    data = _call("login", {"email": email, "password": password})
    session = (data or {}).get("session")
    if not session:
        raise MyfxbookError("เข้าสู่ระบบไม่สำเร็จ Myfxbook ไม่ได้ส่ง session กลับมา")
    return session


def logout(session):
    if not session:
        return True
    try:
        _call("logout", {"session": session})
    except MyfxbookError:
        return False
    return True


def my_accounts(session):
    data = _call("get-my-accounts", {"session": session})
    return (data or {}).get("accounts") or []


def watched_accounts(session):
    data = _call("get-watched-accounts", {"session": session})
    return (data or {}).get("accounts") or []


def open_trades(session, account_id):
    data = _call("get-open-trades", {"session": session, "id": account_id})
    return (data or {}).get("openTrades") or []


def daily_data(session, account_id, start, end):
    """กำไรรายวันในช่วงวันที่กำหนด (รูปแบบวันที่ของ Myfxbook คือ YYYY-MM-DD)"""
    data = _call("get-data-daily", {
        "session": session,
        "id": account_id,
        "start": _as_day(start),
        "end": _as_day(end),
    })
    return flatten_daily(data)


def flatten_daily(payload):
    """
    get-data-daily คืนค่ามาเป็นลิสต์ซ้อนลิสต์ เช่น
        {"dataDaily": [[{...}], [{...}]]}
    ฟังก์ชันนี้คลี่ให้เหลือชั้นเดียวและปรับชื่อฟิลด์ให้ตรงกับตาราง daily
    """
    rows = []
    if not isinstance(payload, dict):
        return rows
    for bucket in payload.get("dataDaily") or []:
        items = bucket if isinstance(bucket, list) else [bucket]
        for item in items:
            if not isinstance(item, dict):
                continue
            day = _as_day(item.get("date"))
            if not day:
                continue
            rows.append({
                "day": day,
                "balance": _num(item.get("balance")),
                "equity": _num(item.get("equity"), _num(item.get("balance"))),
                "profit": _num(item.get("profit")),
                "pips": _num(item.get("pips")),
                "lots": _num(item.get("lots")),
                "growth_pct": _num(item.get("growthEquity"), _num(item.get("growth"))),
            })
    rows.sort(key=lambda r: r["day"])
    return rows


def normalize_account(raw):
    """แปลงพอร์ตหนึ่งรายการจาก Myfxbook ให้อยู่ในรูปที่ตาราง accounts ใช้ได้"""
    if not isinstance(raw, dict):
        return None
    mfb_id = raw.get("id")
    if mfb_id in (None, ""):
        return None
    return {
        "mfb_id": str(mfb_id),
        "name": str(raw.get("name") or "พอร์ต %s" % mfb_id).strip(),
        "account_no": str(raw.get("accountId") or ""),
        "broker": str(raw.get("server", {}).get("name") if isinstance(raw.get("server"), dict) else raw.get("server") or ""),
        "platform": str(raw.get("platform") or ""),
        "currency": str(raw.get("currency") or "USD").upper(),
        "balance": _num(raw.get("balance")),
        "equity": _num(raw.get("equity"), _num(raw.get("balance"))),
        "profit": _num(raw.get("profit")),
        "gain_pct": _num(raw.get("gain")),
        "drawdown_pct": _num(raw.get("drawdown")),
        "deposits": _num(raw.get("deposits")),
        "withdrawals": _num(raw.get("withdrawals")),
        "first_trade_at": _as_day(raw.get("firstTradeDate")) or "",
        "last_update": str(raw.get("lastUpdateDate") or ""),
        "is_demo": 1 if raw.get("demo") in (True, "true", 1, "1") else 0,
    }


# ------------------------------------------------------------------- ตัวช่วยเล็ก ๆ

def _num(value, fallback=0.0):
    try:
        if value is None or value == "":
            return float(fallback)
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _as_day(value):
    """รับได้ทั้ง date, datetime, 'YYYY-MM-DD' และรูปแบบวันที่ที่ Myfxbook ส่งมา"""
    if value is None or value == "":
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:len(fmt) + 4] if fmt.endswith("%S") else text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # เผื่อรูปแบบแปลก ๆ ที่ยังขึ้นต้นด้วย YYYY-MM-DD
    head = text[:10]
    try:
        datetime.strptime(head, "%Y-%m-%d")
        return head
    except ValueError:
        return ""

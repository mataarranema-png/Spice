"""
Myfxbook Earning System - เว็บเซิร์ฟเวอร์

ใช้เฉพาะไลบรารีมาตรฐานของ Python จึงไม่ต้องติดตั้งอะไรเพิ่ม
ให้บริการหน้าเว็บในโฟลเดอร์ web/ และ API ทั้งหมดใต้เส้นทาง /api/
"""

import json
import mimetypes
import os
import posixpath
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import api, earnings, sync
from .database import connect, init_db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")


def json_body(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}


def _one(query, key, default=None):
    return query.get(key, [default])[0]


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


ROUTES_GET = [
    (re.compile(r"^/api/overview$"), lambda q, m: api.overview(_int(_one(q, "days"), 90))),
    (re.compile(r"^/api/accounts$"), lambda q, m: api.accounts_board()),
    (re.compile(r"^/api/accounts/(\d+)$"),
     lambda q, m: api.account_detail(int(m.group(1)), _int(_one(q, "days"), 180))),
    (re.compile(r"^/api/earnings$"), lambda q, m: api.earnings_board(_one(q, "period"))),
    (re.compile(r"^/api/payouts$"), lambda q, m: api.payouts_board(_int(_one(q, "limit"), 200))),
    (re.compile(r"^/api/goals$"), lambda q, m: api.goals_board()),
    (re.compile(r"^/api/alerts$"), lambda q, m: api.alerts_board()),
    (re.compile(r"^/api/intelligence$"),
     lambda q, m: api.intelligence(force=_one(q, "force") == "1")),
    (re.compile(r"^/api/connect$"), lambda q, m: sync.status()),
    (re.compile(r"^/api/health$"), lambda q, m: {"ok": True, "service": "Myfxbook Earning System"}),
]

ROUTES_POST = [
    (re.compile(r"^/api/connect/login$"),
     lambda b, m: sync.login(b.get("email"), b.get("password"))),
    (re.compile(r"^/api/connect/logout$"), lambda b, m: sync.logout()),
    (re.compile(r"^/api/connect/demo$"),
     lambda b, m: sync.set_demo(b.get("demo") in (True, 1, "1", "true", "on"))),
    (re.compile(r"^/api/sync$"),
     lambda b, m: sync.sync_now(_int(b.get("days"), sync.DEFAULT_SYNC_DAYS))),
    (re.compile(r"^/api/accounts/(\d+)/rule$"), lambda b, m: api.save_rule(int(m.group(1)), b)),
    (re.compile(r"^/api/accounts/(\d+)/track$"),
     lambda b, m: api.set_tracked(int(m.group(1)), b.get("tracked") in (True, 1, "1", "true", "on"))),
    (re.compile(r"^/api/earnings/recompute$"), lambda b, m: api.recompute()),
    (re.compile(r"^/api/payouts$"), lambda b, m: api.create_payout(b)),
    (re.compile(r"^/api/payouts/(\d+)/delete$"), lambda b, m: api.delete_payout(int(m.group(1)))),
    (re.compile(r"^/api/goals$"), lambda b, m: api.save_goal(b)),
    (re.compile(r"^/api/settings$"), lambda b, m: api.save_settings(b)),
    (re.compile(r"^/api/fx$"), lambda b, m: api.save_rate(b)),
    (re.compile(r"^/api/alerts/ack$"),
     lambda b, m: api.ack_alert(b.get("key") or "", b.get("actor") or "ผู้ใช้")),
    (re.compile(r"^/api/alerts/unack$"), lambda b, m: api.unack_alert(b.get("key") or "")),
]


class Handler(BaseHTTPRequestHandler):
    server_version = "MyfxbookEarning/1.0"
    protocol_version = "HTTP/1.1"

    # ปิด log รายบรรทัดของ http.server ไม่ให้รกหน้าจอผู้ใช้
    def log_message(self, fmt, *args):
        pass

    # ---------------------------------------------------------- helpers
    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text, ctype, filename=None):
        body = ("﻿" + text).encode("utf-8")   # BOM ช่วยให้ Excel อ่านภาษาไทยถูก
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % filename)
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            self.send_error(404, "Not found")
            return
        ctype, _ = mimetypes.guess_type(path)
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def safe_path(self, url_path):
        rel = unquote(url_path).lstrip("/")
        rel = posixpath.normpath(rel)
        if rel in ("", "."):
            rel = "index.html"
        if rel.startswith("..") or os.path.isabs(rel):
            return None
        full = os.path.join(WEB_DIR, *rel.split("/"))
        if not os.path.abspath(full).startswith(os.path.abspath(WEB_DIR)):
            return None
        return full

    # ---------------------------------------------------------- verbs
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/export":
            kind = _one(query, "kind", "earnings")
            try:
                text = api.export_csv(kind)
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, 500)
                return
            self.send_text(text, "text/csv; charset=utf-8", "myfxbook-%s.csv" % kind)
            return

        if path.startswith("/api/"):
            for pattern, fn in ROUTES_GET:
                m = pattern.match(path)
                if m:
                    try:
                        result = fn(query, m)
                        self.send_json(result, 200 if result.get("ok", True) else 404)
                    except Exception as exc:   # กันเซิร์ฟเวอร์ล้มจากข้อมูลแปลก ๆ
                        self.send_json({"ok": False, "error": str(exc)}, 500)
                    return
            self.send_json({"ok": False, "error": "ไม่พบ endpoint นี้"}, 404)
            return

        full = self.safe_path(path)
        if full is None:
            self.send_error(403, "Forbidden")
            return
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.exists(full):
            # หน้าเดียวจบ ทุกเส้นทางที่ไม่ใช่ไฟล์จริงให้กลับไปที่ index.html
            full = os.path.join(WEB_DIR, "index.html")
        self.send_file(full)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            self.send_json({"ok": False, "error": "ไม่รองรับ"}, 404)
            return
        body = json_body(self)
        for pattern, fn in ROUTES_POST:
            m = pattern.match(path)
            if m:
                try:
                    result = fn(body, m)
                    self.send_json(result, 200 if result.get("ok", True) else 400)
                except Exception as exc:
                    self.send_json({"ok": False, "error": str(exc)}, 500)
                return
        self.send_json({"ok": False, "error": "ไม่พบ endpoint นี้"}, 404)


def find_port(preferred=8820, tries=40):
    for offset in range(tries):
        port = preferred + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("หาพอร์ตว่างไม่ได้ ลองปิดโปรแกรมอื่นแล้วรันใหม่")


def prepare_data():
    """เปิดโปรแกรมครั้งแรกให้คิดส่วนแบ่งของข้อมูลที่มีอยู่ก่อน จะได้เห็นตัวเลขทันที"""
    init_db()
    conn = connect()
    try:
        if conn.execute("SELECT 1 FROM accruals LIMIT 1").fetchone() is None:
            earnings.recompute_all(conn)
            conn.commit()
    finally:
        conn.close()


def build_server(port=None, host="127.0.0.1"):
    prepare_data()
    port = port or find_port()
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd, port


def serve_forever(port=None, host="127.0.0.1"):
    httpd, port = build_server(port, host)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port

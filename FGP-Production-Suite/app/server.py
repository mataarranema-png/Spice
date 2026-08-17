"""
FGP Production Suite - เว็บเซิร์ฟเวอร์
ใช้เฉพาะไลบรารีมาตรฐานของ Python จึงไม่ต้องติดตั้งอะไรเพิ่มเลย
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

from . import api
from .database import init_db

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


ROUTES_GET = [
    (re.compile(r"^/api/overview$"), lambda h, q, m: api.overview()),
    (re.compile(r"^/api/reference$"), lambda h, q, m: api.reference()),
    (
        re.compile(r"^/api/plan$"),
        lambda h, q, m: api.plan_board(q.get("from", [None])[0], q.get("to", [None])[0]),
    ),
    (
        re.compile(r"^/api/capacity$"),
        lambda h, q, m: api.capacity_board(q.get("date", [None])[0], q.get("type", [None])[0]),
    ),
    (
        re.compile(r"^/api/wip$"),
        lambda h, q, m: api.wip_board(
            q.get("stage", [None])[0], q.get("team", [None])[0], q.get("owner", [None])[0]
        ),
    ),
    (re.compile(r"^/api/wip/(\d+)$"), lambda h, q, m: api.job_detail(int(m.group(1)))),
    (re.compile(r"^/api/kpi$"), lambda h, q, m: api.kpi_board(int(q.get("days", ["14"])[0]))),
    (re.compile(r"^/api/team$"), lambda h, q, m: api.team_board()),
    (re.compile(r"^/api/alerts$"), lambda h, q, m: api.alerts_board()),
    (re.compile(r"^/api/health$"), lambda h, q, m: {"ok": True, "service": "FGP Production Suite"}),
]

ROUTES_POST = [
    (re.compile(r"^/api/plan$"), lambda h, b, m: api.create_plan(b)),
    (
        re.compile(r"^/api/plan/(\d+)/actual$"),
        lambda h, b, m: api.update_actual(int(m.group(1)), int(b.get("actual") or 0)),
    ),
    (re.compile(r"^/api/bookings$"), lambda h, b, m: api.create_booking(b)),
    (re.compile(r"^/api/bookings/(\d+)/cancel$"), lambda h, b, m: api.cancel_booking(int(m.group(1)))),
    (
        re.compile(r"^/api/wip/(\d+)/advance$"),
        lambda h, b, m: api.advance_job(int(m.group(1)), b.get("actor") or "Leader"),
    ),
    (
        re.compile(r"^/api/wip/(\d+)/assign$"),
        lambda h, b, m: api.assign_job(int(m.group(1)), int(b.get("member_id") or 0), b.get("actor") or "Leader"),
    ),
    (re.compile(r"^/api/alerts/ack$"), lambda h, b, m: api.ack_alert(b.get("key") or "", b.get("actor") or "ผู้ใช้")),
    (re.compile(r"^/api/alerts/unack$"), lambda h, b, m: api.unack_alert(b.get("key") or "")),
]


class Handler(BaseHTTPRequestHandler):
    server_version = "FGP/1.0"
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
        if path.startswith("/api/"):
            query = parse_qs(parsed.query)
            for pattern, fn in ROUTES_GET:
                m = pattern.match(path)
                if m:
                    try:
                        result = fn(self, query, m)
                        self.send_json(result, 200 if result.get("ok", True) else 404)
                    except Exception as exc:  # กันเซิร์ฟเวอร์ล้มจากข้อมูลแปลก ๆ
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
                    result = fn(self, body, m)
                    self.send_json(result, 200 if result.get("ok", True) else 400)
                except Exception as exc:
                    self.send_json({"ok": False, "error": str(exc)}, 500)
                return
        self.send_json({"ok": False, "error": "ไม่พบ endpoint นี้"}, 404)


def find_port(preferred=8760, tries=40):
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


def build_server(port=None, host="127.0.0.1"):
    init_db()
    port = port or find_port()
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd, port


def serve_forever(port=None, host="127.0.0.1"):
    httpd, port = build_server(port, host)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port

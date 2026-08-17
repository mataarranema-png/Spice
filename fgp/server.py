"""HTTP server ของระบบ FGP — ใช้เฉพาะไลบรารีมาตรฐานของ Python"""

from __future__ import annotations

import http.cookies
import json
import mimetypes
import os
import socket
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import api, auth, db

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
COOKIE_NAME = "fgp_session"
MAX_BODY = 2 * 1024 * 1024

_login_hits: dict[str, list[float]] = {}
_hits_lock = threading.Lock()


def lan_ip() -> str:
    """หา IP ในวง LAN ที่เครื่องอื่นใช้เข้าถึงได้"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        s.close()


def _rate_blocked(ip: str) -> bool:
    """กันสุ่มรหัสผ่าน: ล็อกอินผิดได้ไม่เกิน 10 ครั้งต่อ 5 นาทีต่อเครื่อง

    นับเฉพาะครั้งที่ผิด เพราะเครื่องรวมหน้าไลน์อาจมีหลายคนสลับกันเข้าใช้
    """
    now = time.time()
    with _hits_lock:
        hits = [t for t in _login_hits.get(ip, []) if now - t < 300]
        _login_hits[ip] = hits
        return len(hits) >= 10


def _rate_record_failure(ip: str) -> None:
    with _hits_lock:
        _login_hits.setdefault(ip, []).append(time.time())


class Handler(BaseHTTPRequestHandler):
    server_version = "FGP/1.0"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------ plumbing

    def log_message(self, fmt, *args):
        if os.environ.get("FGP_VERBOSE"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, status: int = 200, extra: dict | None = None):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8",
                   {**(extra or {}), "Cache-Control": "no-store"})

    def _token(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        try:
            return http.cookies.SimpleCookie(raw).get(COOKIE_NAME).value
        except Exception:
            return None

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise api.ApiError("ข้อมูลที่ส่งมาใหญ่เกินไป", 413)
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {"value": data}
        except json.JSONDecodeError:
            raise api.ApiError("รูปแบบข้อมูลไม่ถูกต้อง (ต้องเป็น JSON)")

    # -------------------------------------------------------------- routes

    def do_GET(self):
        self._handle("GET")

    def do_HEAD(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    @staticmethod
    def _decode_path(raw: str) -> str:
        """BaseHTTPRequestHandler อ่าน request line เป็น latin-1 จึงต้องคืนรูปเป็น UTF-8 ก่อน"""
        try:
            return raw.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return raw

    def _handle(self, method: str):
        parsed = urlparse(self._decode_path(self.path))
        path = unquote(parsed.path)
        if path.startswith("/api/"):
            self._handle_api(method, path, parsed.query)
        elif method == "GET":
            self._handle_static(path)
        else:
            self._json({"error": "ไม่พบเส้นทางนี้"}, 404)

    def _handle_api(self, method: str, path: str, raw_query: str):
        is_login = path == "/api/auth/login" and method == "POST"
        try:
            if is_login and _rate_blocked(self.client_address[0]):
                raise api.ApiError("ใส่รหัสผ่านผิดหลายครั้งเกินไป กรุณารอ 5 นาทีแล้วลองใหม่", 429)
            query = {k: v[0] for k, v in parse_qs(raw_query).items()}
            body = self._body() if method in ("POST", "PUT", "DELETE") else {}
            user = auth.user_from_token(self._token())
            result = api.dispatch(method, path, user, body, query)

            if isinstance(result, dict) and "_raw" in result:
                self._send(200, result["_raw"], result.get("_content_type", "text/plain"),
                           {"Content-Disposition":
                            f'attachment; filename="{result.get("_filename", "export.txt")}"'})
                return

            extra = {}
            if isinstance(result, dict):
                token = result.pop("_set_token", None)
                if token:
                    extra["Set-Cookie"] = (f"{COOKIE_NAME}={token}; Path=/; HttpOnly; "
                                           f"SameSite=Lax; Max-Age={auth.SESSION_DAYS * 86400}")
                if result.pop("_clear_token", False):
                    auth.logout(self._token() or "")
                    extra["Set-Cookie"] = f"{COOKIE_NAME}=; Path=/; HttpOnly; Max-Age=0"
            self._json(result, 200, extra)

        except api.ApiError as e:
            if is_login and e.status == 401:
                _rate_record_failure(self.client_address[0])
            self._json({"error": e.message}, e.status)
        except (ValueError, TypeError) as e:
            self._json({"error": f"ข้อมูลไม่ถูกต้อง: {e}"}, 400)
        except Exception as e:  # noqa: BLE001
            if os.environ.get("FGP_VERBOSE"):
                import traceback
                traceback.print_exc()
            self._json({"error": f"ระบบขัดข้อง: {e}"}, 500)

    def _handle_static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        rel = os.path.normpath(path.lstrip("/")).replace("\\", "/")
        if rel.startswith("..") or os.path.isabs(rel):
            self._send(403, b"forbidden", "text/plain; charset=utf-8")
            return
        full = os.path.join(STATIC_DIR, rel)
        if not os.path.isfile(full):
            full = os.path.join(STATIC_DIR, "index.html")  # SPA fallback
            if not os.path.isfile(full):
                self._send(404, "ไม่พบไฟล์".encode(), "text/plain; charset=utf-8")
                return
        ctype, _ = mimetypes.guess_type(full)
        if ctype in ("text/html", "text/css", "application/javascript", "text/javascript"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            data = fh.read()
        cache = "no-cache" if full.endswith(".html") else "public, max-age=300"
        self._send(200, data, ctype or "application/octet-stream", {"Cache-Control": cache})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64


def serve(host: str = "0.0.0.0", port: int = 8080, open_browser: bool = True) -> None:
    db.init_db()
    for attempt in range(12):
        try:
            httpd = Server((host, port + attempt), Handler)
            port = port + attempt
            break
        except OSError:
            continue
    else:
        print("เปิดพอร์ตไม่สำเร็จ ลองปิดโปรแกรมที่ใช้พอร์ต 8080 แล้วเริ่มใหม่")
        return

    ip = lan_ip()
    bar = "─" * 58
    print(f"""
┌{bar}┐
   FGP PRODUCTION SYSTEM   พร้อมใช้งานแล้ว

   เครื่องนี้         http://localhost:{port}
   เครื่องอื่นในวง LAN  http://{ip}:{port}
   จอ Andon           http://{ip}:{port}/#/andon

   บัญชีเริ่มต้น   admin / Admin@123
                  manager / Manager@123
                  leader1 / Leader@123
                  operator / Operator@123

   ปิดระบบ: กด Ctrl + C
└{bar}┘
""".rstrip())

    if open_browser:
        threading.Thread(
            target=lambda: (time.sleep(1.0), __import__("webbrowser").open(f"http://localhost:{port}")),
            daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nปิดระบบเรียบร้อย ข้อมูลถูกบันทึกไว้ที่ data/fgp.db")
    finally:
        httpd.server_close()

"""Spice — เว็บแอปสั่งงาน AI ที่ยืมพลัง GPU จาก Google Colab ได้ในคำสั่งเดียว."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, auth, db
from .config import ROOT, get_settings
from .routers import auth_routes, drive, hub, jobs, vault_routes, workers

WEB_DIR = ROOT / "web"
COLAB_DIR = ROOT / "colab"
AGENT_DIR = ROOT / "agent"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="Spice",
    version=__version__,
    description="สั่งงานโมเดล AI จากเว็บ โดยยืมการ์ดจอ Tesla T4 ของ Google Colab มาเป็นแรงประมวลผล",
    lifespan=lifespan,
)

app.include_router(auth_routes.router)
app.include_router(workers.router)
app.include_router(jobs.router)
app.include_router(drive.router)
app.include_router(vault_routes.router)
app.include_router(hub.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.get("/healthz")
def healthz() -> dict:
    settings = get_settings()
    return {
        "ok": True,
        "version": __version__,
        "google_login": settings.google_enabled,
        "dev_login": settings.dev_login,
        "time": time.time(),
    }


def _text_file(path: Path, media_type: str) -> PlainTextResponse:
    if not path.exists():
        raise HTTPException(500, f"ไม่พบไฟล์ {path.name} บนเซิร์ฟเวอร์")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type=media_type)


@app.get("/agent/spice_agent.py", response_class=PlainTextResponse)
def agent_script() -> PlainTextResponse:
    """ตัวแทนเครื่อง — ใช้ได้ทั้งบน Colab และคอมพิวเตอร์ของผู้ใช้เอง."""
    return _text_file(AGENT_DIR / "spice_agent.py", "text/x-python")


@app.get("/colab/bootstrap.py", response_class=PlainTextResponse)
def colab_bootstrap() -> PlainTextResponse:
    """ทางเดิมที่โน้ตบุ๊กเก่าชี้อยู่ — ให้ไฟล์เดียวกันกับ /agent/spice_agent.py."""
    return agent_script()


@app.get("/install.sh", response_class=PlainTextResponse)
def install_sh() -> PlainTextResponse:
    """ตัวติดตั้งสำหรับ macOS และ Linux."""
    return _text_file(AGENT_DIR / "install.sh", "text/x-shellscript")


@app.get("/install.ps1", response_class=PlainTextResponse)
def install_ps1() -> PlainTextResponse:
    """ตัวติดตั้งสำหรับ Windows (PowerShell)."""
    return _text_file(AGENT_DIR / "install.ps1", "text/plain")


@app.get("/api/v1/connect-snippet")
def connect_snippet(pair_code: str, user: dict = Depends(auth.require_user)) -> dict:
    """คำสั่งเชื่อมเครื่อง แยกตามที่ที่จะเอาไปรัน."""
    base = get_settings().base_url.rstrip("/")
    code = pair_code.strip().upper()

    return {
        "pair_code": code,
        "targets": [
            {
                "id": "colab",
                "label": "Google Colab",
                "icon": "⚡",
                "blurb": "ยืมการ์ดจอ Tesla T4 ฟรี ไม่ต้องมีเครื่องแรง",
                "command": (
                    f"!curl -sSL {base}/agent/spice_agent.py -o spice_agent.py && "
                    f"pip -q install requests && "
                    f"python spice_agent.py --server {base} --pair {code}"
                ),
                "steps": [
                    "เปิด Google Colab แล้วเลือก Runtime → Change runtime type → T4 GPU",
                    "วางคำสั่งด้านล่างในเซลล์เดียว แล้วกด ▶ รัน",
                    "รอราว 10 วินาที เครื่องจะขึ้นสถานะ “ออนไลน์” ในหน้านี้เอง",
                ],
                "note": "เซลล์ต้องรันค้างไว้ ถ้าปิดแท็บเครื่องจะหลุดจากระบบ",
            },
            {
                "id": "windows",
                "label": "คอมพิวเตอร์ · Windows",
                "icon": "🪟",
                "blurb": "ใช้การ์ดจอ NVIDIA ในเครื่องตัวเอง จับคู่ครั้งเดียวจบ",
                "command": (
                    f'& ([scriptblock]::Create((irm {base}/install.ps1))) '
                    f'-Server {base} -Pair {code}'
                ),
                "steps": [
                    "กดปุ่ม Start พิมพ์ว่า PowerShell แล้วเปิดขึ้นมา",
                    "วางคำสั่งด้านล่างแล้วกด Enter",
                    "ตัวติดตั้งจะเตรียม Python และ PyTorch ให้เอง แล้วถามว่าจะให้เปิดเองทุกครั้งที่เข้าเครื่องไหม",
                ],
                "note": "ต้องมี Python 3 ในเครื่องก่อน (python.org — ตอนติดตั้งติ๊ก Add to PATH ด้วย)",
            },
            {
                "id": "unix",
                "label": "คอมพิวเตอร์ · macOS / Linux",
                "icon": "💻",
                "blurb": "รองรับทั้งการ์ด NVIDIA และชิป Apple Silicon (Metal)",
                "command": (
                    f"curl -sSL {base}/install.sh | bash -s -- "
                    f"--server {base} --pair {code}"
                ),
                "steps": [
                    "เปิดแอป Terminal",
                    "วางคำสั่งด้านล่างแล้วกด Enter",
                    "ตัวติดตั้งจะเตรียมทุกอย่างให้ แล้วถามว่าจะให้เปิดเองทุกครั้งที่เปิดเครื่องไหม",
                ],
                "note": "จับคู่ครั้งเดียว กุญแจถูกเก็บไว้ที่ ~/.spice/config.json — ครั้งหน้าต่อกลับเอง",
            },
        ],
        "notebook_url": f"{base}/colab/Spice_GPU_Bridge.ipynb",
    }


@app.get("/colab/Spice_GPU_Bridge.ipynb")
def colab_notebook() -> FileResponse:
    path = COLAB_DIR / "Spice_GPU_Bridge.ipynb"
    if not path.exists():
        raise HTTPException(404, "ไม่พบโน้ตบุ๊ก")
    return FileResponse(path, media_type="application/json", filename="Spice_GPU_Bridge.ipynb")


def _page(name: str) -> FileResponse:
    path = WEB_DIR / name
    if not path.exists():
        raise HTTPException(404, "ไม่พบหน้านี้")
    return FileResponse(path, media_type="text/html")


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    if auth.current_user_optional(request):
        return RedirectResponse("/app", status_code=302)
    return _page("index.html")


@app.get("/app", response_class=HTMLResponse)
def dashboard(request: Request):
    if auth.current_user_optional(request) is None:
        return RedirectResponse("/", status_code=302)
    return _page("app.html")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

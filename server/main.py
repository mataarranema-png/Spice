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
from .routers import auth_routes, drive, jobs, vault_routes, workers

WEB_DIR = ROOT / "web"
COLAB_DIR = ROOT / "colab"


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


@app.get("/colab/bootstrap.py", response_class=PlainTextResponse)
def colab_bootstrap() -> PlainTextResponse:
    """สคริปต์ตัวแทนเครื่อง (worker agent) — Colab ดึงไฟล์นี้ไปรันได้ตรง ๆ."""
    script = COLAB_DIR / "spice_worker.py"
    if not script.exists():
        raise HTTPException(500, "ไม่พบไฟล์ spice_worker.py บนเซิร์ฟเวอร์")
    return PlainTextResponse(script.read_text(encoding="utf-8"), media_type="text/x-python")


@app.get("/api/v1/connect-snippet")
def connect_snippet(pair_code: str, user: dict = Depends(auth.require_user)) -> dict:
    """คำสั่งบรรทัดเดียวสำหรับวางใน Colab เพื่อยืมการ์ดจอเข้าระบบ."""
    base = get_settings().base_url.rstrip("/")
    code = pair_code.strip().upper()
    one_liner = (
        f"!curl -sSL {base}/colab/bootstrap.py -o spice_worker.py && "
        f"pip -q install requests && "
        f"python spice_worker.py --server {base} --pair {code}"
    )
    return {
        "one_liner": one_liner,
        "notebook_url": f"{base}/colab/Spice_GPU_Bridge.ipynb",
        "steps": [
            "เปิด Google Colab แล้วเลือกเมนู Runtime → Change runtime type → T4 GPU",
            "วางคำสั่งด้านล่างในเซลล์เดียว แล้วกด ▶ รัน",
            "รอประมาณ 10 วินาที เครื่องจะขึ้นสถานะ 'ออนไลน์' ในหน้านี้เอง",
        ],
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

"""เชื่อม Google Drive: สร้าง rclone.conf อัตโนมัติ + ดูไฟล์/พื้นที่คงเหลือ."""

from __future__ import annotations

import datetime as dt
import json
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from .. import auth, db
from ..config import get_settings
from ..security import decrypt
from .workers import authed_worker

router = APIRouter(prefix="/api/v1", tags=["drive"])

DRIVE_API = "https://www.googleapis.com/drive/v3"
REMOTE_NAME = "gdrive"


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def build_rclone_conf(user_id: int) -> str:
    """สร้างไฟล์ตั้งค่า rclone จากโทเคน OAuth ของผู้ใช้ — เอาไปวางแล้วใช้ได้เลย."""
    settings = get_settings()
    row = db.query_one("SELECT * FROM google_tokens WHERE user_id = ?", (user_id,))
    if row is None or not decrypt(row["refresh_token"]):
        raise HTTPException(
            400,
            "ยังไม่ได้ให้สิทธิ์ Google Drive — กดปุ่ม 'เชื่อม Google Drive' แล้วล็อกอินใหม่อีกครั้ง",
        )
    if "drive" not in row["scopes"]:
        raise HTTPException(400, "โทเคนที่มีอยู่ยังไม่ครอบคลุมสิทธิ์ Drive — กรุณาเชื่อมใหม่")

    token_blob = json.dumps(
        {
            "access_token": decrypt(row["access_token"]),
            "token_type": "Bearer",
            "refresh_token": decrypt(row["refresh_token"]),
            "expiry": _iso(row["expires_at"]),
        },
        separators=(",", ":"),
    )
    return "\n".join(
        [
            f"[{REMOTE_NAME}]",
            "type = drive",
            f"client_id = {settings.google_client_id}",
            f"client_secret = {settings.google_client_secret}",
            "scope = drive",
            f"token = {token_blob}",
            "team_drive =",
            "",
        ]
    )


async def _drive_get(user_id: int, path: str, params: dict) -> dict:
    access_token = await auth.refresh_access_token(user_id)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{DRIVE_API}{path}",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"Drive API ตอบกลับผิดพลาด: {resp.text[:200]}")
    return resp.json()


@router.get("/drive/status")
async def drive_status(user: dict = Depends(auth.require_user)) -> dict:
    row = db.query_one("SELECT * FROM google_tokens WHERE user_id = ?", (user["id"],))
    if row is None or not decrypt(row["refresh_token"]):
        return {"connected": False, "reason": "ยังไม่ได้ให้สิทธิ์ Drive"}

    scopes = row["scopes"].split()
    has_drive = any("drive" in scope for scope in scopes)
    info: dict = {
        "connected": True,
        "has_drive_scope": has_drive,
        "scopes": scopes,
        "token_expires_in": max(0, round(row["expires_at"] - time.time())),
        "rclone_remote": REMOTE_NAME,
    }
    if has_drive:
        try:
            about = await _drive_get(user["id"], "/about", {"fields": "storageQuota,user"})
            quota = about.get("storageQuota", {})
            limit = int(quota.get("limit", 0) or 0)
            usage = int(quota.get("usage", 0) or 0)
            info["quota"] = {
                "limit_bytes": limit,
                "usage_bytes": usage,
                "limit_gb": round(limit / 1024**3, 1) if limit else None,
                "usage_gb": round(usage / 1024**3, 2),
                "used_pct": round(usage * 100 / limit, 1) if limit else None,
                "unlimited": limit == 0,
            }
            info["drive_user"] = about.get("user", {}).get("emailAddress", "")
        except HTTPException as exc:
            info["quota_error"] = str(exc.detail)
    return info


@router.get("/drive/files")
async def drive_files(
    q: str = "", folder: str = "root", limit: int = 30,
    user: dict = Depends(auth.require_user),
) -> dict:
    limit = max(1, min(limit, 100))
    # ค้นด้วยชื่อเมื่อมีคำค้น, ไม่งั้นไล่ดูตามโฟลเดอร์
    escaped = q.replace("'", r"\'")
    query = f"name contains '{escaped}' and trashed = false" if q else f"'{folder}' in parents and trashed = false"
    data = await _drive_get(
        user["id"],
        "/files",
        {
            "q": query,
            "pageSize": limit,
            "fields": "files(id,name,mimeType,size,modifiedTime,iconLink,webViewLink)",
            "orderBy": "folder,modifiedTime desc",
        },
    )
    files = []
    for item in data.get("files", []):
        is_folder = item["mimeType"] == "application/vnd.google-apps.folder"
        files.append(
            {
                "id": item["id"],
                "name": item["name"],
                "is_folder": is_folder,
                "mime": item["mimeType"],
                "size_mb": round(int(item.get("size", 0)) / 1024**2, 2) if item.get("size") else None,
                "modified": item.get("modifiedTime", ""),
                "link": item.get("webViewLink", ""),
                "rclone_path": f"{REMOTE_NAME}:{item['name']}",
            }
        )
    return {"files": files, "count": len(files)}


@router.get("/drive/rclone.conf", response_class=PlainTextResponse)
def download_rclone_conf(user: dict = Depends(auth.require_user)) -> PlainTextResponse:
    conf = build_rclone_conf(user["id"])
    db.log_audit(user["id"], "rclone.download", "")
    return PlainTextResponse(
        conf,
        headers={"Content-Disposition": 'attachment; filename="rclone.conf"'},
    )


@router.get("/drive/rclone/preview")
def preview_rclone(user: dict = Depends(auth.require_user)) -> dict:
    """แสดงตัวอย่างการตั้งค่าแบบปิดบังโทเคน + คำสั่งที่ใช้บ่อย."""
    conf = build_rclone_conf(user["id"])
    masked = []
    for line in conf.splitlines():
        key = line.split(" = ")[0]
        masked.append(f"{key} = ••••••••••••" if key in {"token", "client_secret"} else line)
    return {
        "remote": REMOTE_NAME,
        "config_masked": "\n".join(masked),
        "commands": [
            {
                "label": "เมานต์ Drive เข้าเครื่อง (แนะนำ)",
                "cmd": f"rclone mount {REMOTE_NAME}: ~/gdrive --vfs-cache-mode full --daemon",
            },
            {
                "label": "ก๊อปโมเดลจาก Drive ลงเครื่อง (เร็วกว่าเมานต์เวลาโหลดโมเดล)",
                "cmd": f"rclone copy {REMOTE_NAME}:models/ ./models --transfers 8 --progress",
            },
            {
                "label": "ส่งผลลัพธ์กลับขึ้น Drive",
                "cmd": f"rclone copy ./outputs {REMOTE_NAME}:spice/outputs --progress",
            },
            {
                "label": "ดูพื้นที่คงเหลือ",
                "cmd": f"rclone about {REMOTE_NAME}:",
            },
        ],
    }


@router.get("/worker/rclone")
def worker_rclone(worker: dict = Depends(authed_worker)) -> dict:
    """ให้เครื่อง worker ดึงค่าตั้ง rclone ของเจ้าของไปเมานต์ Drive ได้เอง."""
    conf = build_rclone_conf(worker["user_id"])
    db.log_audit(worker["user_id"], "rclone.worker_fetch", worker["id"])
    return {"remote": REMOTE_NAME, "conf": conf}

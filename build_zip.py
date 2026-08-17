#!/usr/bin/env python3
"""
สร้างไฟล์ zip สำหรับแจกจ่าย FGP Production Suite
รัน: python build_zip.py
ได้ไฟล์ dist/FGP-Production-Suite.zip ที่แตกแล้วกดเปิดใช้ได้ทันที
"""

import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "FGP-Production-Suite"
OUT = ROOT / "dist" / "FGP-Production-Suite.zip"

# ไม่ต้องใส่ลงซิป ฐานข้อมูลจะถูกสร้างใหม่ตอนเปิดครั้งแรกให้ตรงกับวันที่ของผู้ใช้
SKIP_DIRS = {"__pycache__", "data", ".git"}
SKIP_SUFFIX = {".pyc", ".pyo", ".db", ".db-wal", ".db-shm"}

# ไฟล์ที่ต้องรันได้ทันทีหลังแตกซิปบน macOS และ Linux
EXECUTABLE = {"start-mac.command", "start-linux.sh", "start.py"}


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()

    files = []
    for path in sorted(SRC.rglob("*")):
        if any(part in SKIP_DIRS for part in path.relative_to(SRC).parts):
            continue
        if path.suffix in SKIP_SUFFIX or not path.is_file():
            continue
        files.append(path)

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            arc = Path(SRC.name) / path.relative_to(SRC)
            info = zipfile.ZipInfo(str(arc).replace(os.sep, "/"))
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if path.name in EXECUTABLE else 0o644
            info.external_attr = mode << 16
            zf.writestr(info, path.read_bytes())

    size_kb = OUT.stat().st_size / 1024
    print("สร้างไฟล์แล้ว: %s" % OUT)
    print("ไฟล์ทั้งหมด %d ไฟล์ ขนาด %.1f KB" % (len(files), size_kb))
    for path in files:
        print("   ", path.relative_to(SRC))


if __name__ == "__main__":
    main()

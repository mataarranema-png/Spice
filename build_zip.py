#!/usr/bin/env python3
"""
สร้างไฟล์ zip สำหรับแจกจ่ายโปรแกรมในที่เก็บนี้
    python build_zip.py                     สร้างทุกโปรแกรม
    python build_zip.py FGP-Production-Suite   เลือกเฉพาะโปรแกรมที่ต้องการ
ได้ไฟล์ใน dist/ ที่แตกแล้วกดเปิดใช้ได้ทันที
"""

import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# โปรแกรมที่แจกเป็นซิปได้ ทุกตัวเปิดด้วย start.py เหมือนกัน
APPS = ["FGP-Production-Suite", "Myfxbook-Earning-System"]

# ไม่ต้องใส่ลงซิป ฐานข้อมูลจะถูกสร้างใหม่ตอนเปิดครั้งแรกให้ตรงกับวันที่ของผู้ใช้
SKIP_DIRS = {"__pycache__", "data", ".git"}
SKIP_SUFFIX = {".pyc", ".pyo", ".db", ".db-wal", ".db-shm"}

# ไฟล์ที่ต้องรันได้ทันทีหลังแตกซิปบน macOS และ Linux
EXECUTABLE = {"start-mac.command", "start-linux.sh", "start.py"}


def build(name):
    src = ROOT / name
    if not src.is_dir():
        print("ไม่พบโฟลเดอร์ %s" % name)
        return False

    out = ROOT / "dist" / ("%s.zip" % name)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    files = []
    for path in sorted(src.rglob("*")):
        if any(part in SKIP_DIRS for part in path.relative_to(src).parts):
            continue
        if path.suffix in SKIP_SUFFIX or not path.is_file():
            continue
        files.append(path)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            arc = Path(src.name) / path.relative_to(src)
            info = zipfile.ZipInfo(str(arc).replace(os.sep, "/"))
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if path.name in EXECUTABLE else 0o644
            info.external_attr = mode << 16
            zf.writestr(info, path.read_bytes())

    print("สร้างไฟล์แล้ว: %s" % out)
    print("   ไฟล์ทั้งหมด %d ไฟล์ ขนาด %.1f KB" % (len(files), out.stat().st_size / 1024))
    return True


def main():
    names = sys.argv[1:] or APPS
    ok = True
    for name in names:
        ok = build(name) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

"""จุดเริ่มโปรแกรม: python -m fgp [--port 8080] [--no-browser] [--reset]"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

from . import db, server


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fgp", description="FGP Production System")
    p.add_argument("--host", default="0.0.0.0", help="ที่อยู่ที่ผูกกับเซิร์ฟเวอร์")
    p.add_argument("--port", type=int, default=int(os.environ.get("FGP_PORT", 8080)))
    p.add_argument("--no-browser", action="store_true", help="ไม่ต้องเปิดเบราว์เซอร์อัตโนมัติ")
    p.add_argument("--reset", action="store_true", help="ล้างฐานข้อมูลแล้วสร้างข้อมูลตัวอย่างใหม่")
    p.add_argument("--empty", action="store_true", help="สร้างฐานข้อมูลเปล่า ไม่มีข้อมูลตัวอย่าง")
    args = p.parse_args(argv)

    if sys.version_info < (3, 9):
        print("ต้องใช้ Python 3.9 ขึ้นไป")
        return 1

    if args.reset and os.path.isdir(db.DATA_DIR):
        shutil.rmtree(db.DATA_DIR)
        print("ล้างฐานข้อมูลเดิมแล้ว")

    if args.empty:
        db.init_db(seed=False)

    server.serve(args.host, args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
FGP Production Suite - ตัวเปิดโปรแกรมแบบคลิกเดียว

ใช้ Python 3.8 ขึ้นไป ไม่ต้องติดตั้งไลบรารีเพิ่ม ไม่ต้องต่ออินเทอร์เน็ต
    python start.py              เปิดโปรแกรมแล้วเปิดเบราว์เซอร์ให้เอง
    python start.py --port 9000  กำหนดพอร์ตเอง
    python start.py --no-browser ไม่ต้องเปิดเบราว์เซอร์
    python start.py --reset      ล้างข้อมูลแล้วสร้างข้อมูลตัวอย่างใหม่
"""

import argparse
import os
import sys
import time
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

MIN_PYTHON = (3, 8)

BANNER = """
  ╔══════════════════════════════════════════════════════════════╗
  ║   F G P   P R O D U C T I O N   S U I T E                    ║
  ║   Production Plan · Capacity · WIP · KPI · Leader · Alert    ║
  ╚══════════════════════════════════════════════════════════════╝
"""


def main():
    if sys.version_info < MIN_PYTHON:
        print("ต้องใช้ Python %d.%d ขึ้นไป (เครื่องนี้เป็น %s)" % (MIN_PYTHON[0], MIN_PYTHON[1], sys.version.split()[0]))
        input("กด Enter เพื่อปิด...")
        return 1

    parser = argparse.ArgumentParser(description="FGP Production Suite")
    parser.add_argument("--port", type=int, default=None, help="พอร์ตที่ต้องการ")
    parser.add_argument("--host", default="127.0.0.1", help="ที่อยู่ที่ให้บริการ")
    parser.add_argument("--no-browser", action="store_true", help="ไม่ต้องเปิดเบราว์เซอร์")
    parser.add_argument("--reset", action="store_true", help="ล้างข้อมูลแล้วสร้างใหม่")
    args = parser.parse_args()

    from app.database import DB_PATH, init_db
    from app.server import serve_forever

    if args.reset:
        init_db(reset=True)
        print("  ล้างข้อมูลเดิมและสร้างข้อมูลตัวอย่างใหม่แล้ว")

    print(BANNER)
    fresh = not os.path.exists(DB_PATH)
    if fresh:
        print("  กำลังสร้างฐานข้อมูลและข้อมูลตัวอย่างครั้งแรก...")

    try:
        httpd, port = serve_forever(args.port, args.host)
    except Exception as exc:
        print("  เปิดเซิร์ฟเวอร์ไม่สำเร็จ: %s" % exc)
        input("  กด Enter เพื่อปิด...")
        return 1

    url = "http://%s:%d/" % ("localhost" if args.host == "127.0.0.1" else args.host, port)
    print("  ฐานข้อมูล : %s" % DB_PATH)
    print("  เปิดใช้งาน: %s" % url)
    print("  ปิดโปรแกรม: กด Ctrl + C ที่หน้าต่างนี้")
    print("")

    if not args.no_browser:
        time.sleep(0.6)
        try:
            webbrowser.open(url)
        except Exception:
            print("  เปิดเบราว์เซอร์อัตโนมัติไม่ได้ ให้พิมพ์ที่อยู่ข้างบนในเบราว์เซอร์เอง")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  ปิดโปรแกรมแล้ว ขอบคุณครับ")
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

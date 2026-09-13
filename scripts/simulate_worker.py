#!/usr/bin/env python3
"""เครื่องจำลอง — ใช้ทดสอบระบบทั้งหมดโดยไม่ต้องมี GPU จริงหรือเปิด Colab.

    python scripts/simulate_worker.py --server http://localhost:8000 --pair XXXX-XXXX

มันจะแกล้งเป็น Tesla T4 ส่งสัญญาณชีพ รับงานจากคิว แล้วตอบกลับด้วยข้อความจำลอง
เหมาะกับการดูหน้าจอ พัฒนา UI และทดสอบการทำงานแบบครบวงจร.
"""

from __future__ import annotations

import argparse
import random
import sys
import threading
import time
import urllib.error
import urllib.request
import json

STOP = threading.Event()


def call(server: str, path: str, payload: dict | None = None, token: str = "") -> dict:
    url = f"{server.rstrip('/')}{path}"
    data = json.dumps(payload or {}).encode()
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{path} → {exc.code}: {exc.read().decode()[:200]}") from exc


def heartbeat_loop(server: str, token: str, state: dict) -> None:
    while not STOP.is_set():
        used = random.randint(1200, 3000) if state["status"] == "idle" else random.randint(9000, 14200)
        try:
            call(server, "/api/v1/worker/heartbeat", {
                "status": state["status"],
                "gpu_used_mb": used,
                "gpu_util": random.randint(1, 8) if state["status"] == "idle" else random.randint(72, 99),
                "gpu_name": "Tesla T4",
                "gpu_vram_mb": 15360,
                "drive_mounted": True,
            }, token)
        except Exception as exc:
            print(f"  ⚠ heartbeat: {exc}")
        STOP.wait(5)


REPLY = (
    "นี่คือคำตอบจำลองจากเครื่องทดสอบ (ไม่ได้รันโมเดลจริง)\n\n"
    "• ระบบคิวงานทำงานถูกต้อง — งานถูกส่งจากหน้าเว็บมาถึงเครื่องนี้แล้ว\n"
    "• ความคืบหน้าและบันทึกการทำงานถูกส่งกลับแบบเรียลไทม์\n"
    "• เมื่อเชื่อม Colab จริง ข้อความตรงนี้จะเป็นผลลัพธ์จากโมเดลที่คุณเลือก\n\n"
    "สรุป: เส้นทางข้อมูลทั้งหมดตั้งแต่เบราว์เซอร์ → เซิร์ฟเวอร์ → เครื่อง GPU → กลับมาหน้าเว็บ ใช้งานได้ครบถ้วน"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--pair", required=True)
    parser.add_argument("--name", default="Colab จำลอง · Tesla T4")
    parser.add_argument("--speed", type=float, default=1.0, help="ตัวคูณความเร็ว (ยิ่งน้อยยิ่งเร็ว)")
    args = parser.parse_args()

    data = call(args.server, "/api/v1/worker/register", {
        "pair_code": args.pair,
        "name": args.name,
        "gpu_name": "Tesla T4",
        "gpu_vram_mb": 15360,
        "driver": "535.104.05",
        "runtime": "เครื่องจำลองสำหรับทดสอบ",
        "capabilities": ["text", "image", "audio", "embedding"],
    })
    token = data["worker_token"]
    print(f"✅ จับคู่สำเร็จ: {data['worker_id']} (บัญชี {data.get('owner_email')})")

    state = {"status": "idle"}
    threading.Thread(target=heartbeat_loop, args=(args.server, token, state), daemon=True).start()
    print("🚀 พร้อมรับงาน — กด Ctrl+C เพื่อหยุด")

    try:
        while True:
            job = call(args.server, "/api/v1/worker/lease", {}, token).get("job")
            if not job:
                time.sleep(2)
                continue

            state["status"] = "busy"
            print(f"⚙ รับงาน {job['id']} ({job['model']})")
            steps = [
                (0.15, "เตรียมสภาพแวดล้อมและตรวจการ์ดจอ"),
                (0.35, f"กำลังโหลดโมเดล {job['payload'].get('repo', '')}"),
                (0.60, "โมเดลเข้า VRAM แล้ว เริ่มประมวลผล"),
                (0.85, "กำลังสร้างคำตอบ"),
            ]
            for progress, message in steps:
                call(args.server, f"/api/v1/worker/jobs/{job['id']}/progress",
                     {"progress": progress, "message": message}, token)
                time.sleep(1.2 * args.speed)

            call(args.server, f"/api/v1/worker/jobs/{job['id']}/complete", {
                "result": REPLY,
                "meta": {"tokens": random.randint(180, 420), "tokens_per_second": round(random.uniform(18, 34), 1)},
            }, token)
            state["status"] = "idle"
            print(f"✅ ส่งผลลัพธ์ของ {job['id']} กลับแล้ว")
    except KeyboardInterrupt:
        STOP.set()
        print("\n👋 ปิดเครื่องจำลอง")
    return 0


if __name__ == "__main__":
    sys.exit(main())

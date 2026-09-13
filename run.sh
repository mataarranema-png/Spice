#!/usr/bin/env bash
# เริ่มเซิร์ฟเวอร์ Spice — ครั้งแรกจะสร้าง virtualenv และติดตั้งไลบรารีให้เอง
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "🌶️  สร้างสภาพแวดล้อม Python ครั้งแรก…"
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "📝 สร้างไฟล์ .env จากตัวอย่างแล้ว — ใส่ GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET ก่อนใช้งานจริง"
fi

PORT="${PORT:-8000}"
echo "🌶️  Spice กำลังทำงานที่ http://localhost:${PORT}"
exec .venv/bin/uvicorn server.main:app --host 0.0.0.0 --port "$PORT" "$@"

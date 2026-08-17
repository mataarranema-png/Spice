#!/bin/bash
# FGP Production Suite - เปิดโปรแกรมบน macOS (ดับเบิลคลิกไฟล์นี้ได้เลย)
cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1; then
  exec python3 start.py "$@"
elif command -v python >/dev/null 2>&1; then
  exec python start.py "$@"
else
  echo "ไม่พบ Python ในเครื่องนี้"
  echo "ติดตั้งได้ฟรีที่ https://www.python.org/downloads/"
  read -r -p "กด Enter เพื่อปิด..."
  exit 1
fi

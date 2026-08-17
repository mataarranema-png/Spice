#!/bin/bash
# FGP Production Suite - เปิดโปรแกรมบน Linux
cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1; then
  exec python3 start.py "$@"
elif command -v python >/dev/null 2>&1; then
  exec python start.py "$@"
else
  echo "ไม่พบ Python ในเครื่องนี้ ติดตั้งด้วยคำสั่ง: sudo apt install python3"
  exit 1
fi

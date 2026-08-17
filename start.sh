#!/usr/bin/env bash
# เริ่มระบบ FGP Production System (Linux / macOS)
set -euo pipefail
cd "$(dirname "$0")"

echo
echo "  ============================================================"
echo "     FGP PRODUCTION SYSTEM"
echo "     ระบบบริหารการผลิต แผนก FGP"
echo "  ============================================================"
echo

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
      PY="$candidate"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "  ไม่พบ Python 3.9 ขึ้นไปในเครื่องนี้"
  echo "  ติดตั้งก่อนแล้วรันไฟล์นี้ใหม่:"
  echo "    Ubuntu/Debian : sudo apt install python3"
  echo "    macOS         : brew install python"
  exit 1
fi

echo "  ใช้ Python: $($PY --version)"
echo "  กำลังเปิดระบบ..."
echo

exec "$PY" -m fgp "$@"

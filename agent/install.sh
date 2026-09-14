#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
#  Spice Agent · ตัวติดตั้งสำหรับ macOS และ Linux
#
#  วิธีใช้ (คัดลอกจากหน้าเว็บมาวางในเทอร์มินัลได้เลย):
#    curl -sSL https://เซิร์ฟเวอร์ของคุณ/install.sh | bash -s -- \
#         --server https://เซิร์ฟเวอร์ของคุณ --pair XXXX-XXXX
# ────────────────────────────────────────────────────────────────
set -euo pipefail

SERVER=""
PAIR=""
NAME=""
SERVICE="ask"

while [ $# -gt 0 ]; do
  case "$1" in
    --server) SERVER="$2"; shift 2 ;;
    --pair)   PAIR="$2";   shift 2 ;;
    --name)   NAME="$2";   shift 2 ;;
    --service)    SERVICE="yes"; shift ;;
    --no-service) SERVICE="no";  shift ;;
    *) echo "ไม่รู้จักตัวเลือก: $1"; exit 1 ;;
  esac
done

[ -z "$SERVER" ] && { echo "❌ ต้องใส่ --server https://..."; exit 1; }

HOME_DIR="${HOME}/.spice"
VENV="${HOME_DIR}/venv"
AGENT="${HOME_DIR}/spice_agent.py"

echo "🌶  ติดตั้ง Spice Agent ลงที่ ${HOME_DIR}"
mkdir -p "$HOME_DIR"

# ── 1. หา Python ที่ใช้ได้ ───────────────────────────────────
PY=""
for candidate in python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" > /dev/null 2>&1; then PY="$candidate"; break; fi
done
[ -z "$PY" ] && { echo "❌ ไม่พบ Python 3 — ติดตั้งก่อนที่ https://python.org"; exit 1; }
echo "🐍 ใช้ $($PY --version)"

# ── 2. เตรียมสภาพแวดล้อมแยก ไม่ไปยุ่งกับของเดิมในเครื่อง ─────
if [ ! -d "$VENV" ]; then
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q requests

# ── 3. ดึงตัวแทนเครื่องรุ่นล่าสุดจากเซิร์ฟเวอร์ของคุณเอง ─────
echo "⬇  ดาวน์โหลดตัวแทนเครื่อง"
curl -fsSL "${SERVER%/}/agent/spice_agent.py" -o "$AGENT"

# ── 4. ตรวจว่าเครื่องนี้มีอะไรให้ใช้ ────────────────────────
if command -v nvidia-smi > /dev/null 2>&1; then
  echo "⚡ พบการ์ดจอ NVIDIA:"
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
  echo "📦 ติดตั้ง PyTorch (CUDA) — ใช้เวลาสักครู่"
  "$VENV/bin/pip" install -q torch --index-url https://download.pytorch.org/whl/cu121
elif [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
  echo "🍎 พบชิป Apple Silicon — จะใช้ Metal (MPS)"
  "$VENV/bin/pip" install -q torch
else
  echo "⚠  ไม่พบการ์ดจอที่เร่งได้ — จะรันบน CPU ซึ่งช้ามาก"
  "$VENV/bin/pip" install -q torch
fi
"$VENV/bin/pip" install -q "transformers>=4.44" accelerate sentencepiece

# ── 5. จับคู่ครั้งแรก ───────────────────────────────────────
if [ -n "$PAIR" ]; then
  echo "🔗 กำลังจับคู่กับบัญชีของคุณ"
  "$VENV/bin/python" "$AGENT" --server "$SERVER" --pair "$PAIR" ${NAME:+--name "$NAME"} --no-drive &
  PAIR_PID=$!
  sleep 8
  kill "$PAIR_PID" 2> /dev/null || true
  wait "$PAIR_PID" 2> /dev/null || true
fi

# ── 6. เปิดให้ทำงานเองทุกครั้งที่เปิดเครื่อง (ถามก่อน) ───────
install_service() {
  if [ "$(uname -s)" = "Darwin" ]; then
    PLIST="$HOME/Library/LaunchAgents/com.spice.agent.plist"
    mkdir -p "$(dirname "$PLIST")"
    cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.spice.agent</string>
  <key>ProgramArguments</key>
  <array><string>${VENV}/bin/python</string><string>${AGENT}</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${HOME_DIR}/agent.log</string>
  <key>StandardErrorPath</key><string>${HOME_DIR}/agent.log</string>
</dict></plist>
PLISTEOF
    launchctl unload "$PLIST" 2> /dev/null || true
    launchctl load "$PLIST"
    echo "✅ ตั้งให้ทำงานเองแล้ว — ดูบันทึกที่ ${HOME_DIR}/agent.log"
    echo "   หยุดถาวร: launchctl unload $PLIST"
  else
    UNIT="$HOME/.config/systemd/user/spice-agent.service"
    mkdir -p "$(dirname "$UNIT")"
    cat > "$UNIT" <<UNITEOF
[Unit]
Description=Spice Agent — ยกการ์ดจอเครื่องนี้ให้ระบบ Spice
After=network-online.target

[Service]
ExecStart=${VENV}/bin/python ${AGENT}
Restart=always
RestartSec=15

[Install]
WantedBy=default.target
UNITEOF
    systemctl --user daemon-reload
    systemctl --user enable --now spice-agent.service
    loginctl enable-linger "$USER" 2> /dev/null || true
    echo "✅ ตั้งให้ทำงานเองแล้ว"
    echo "   ดูสถานะ: systemctl --user status spice-agent"
    echo "   ดูบันทึก: journalctl --user -u spice-agent -f"
    echo "   หยุดถาวร: systemctl --user disable --now spice-agent"
  fi
}

if [ "$SERVICE" = "ask" ]; then
  printf "ให้ทำงานเองทุกครั้งที่เปิดเครื่องไหม? [y/N] "
  read -r answer < /dev/tty || answer="n"
  case "$answer" in [yY]*) SERVICE="yes" ;; *) SERVICE="no" ;; esac
fi

if [ "$SERVICE" = "yes" ]; then
  install_service
else
  echo ""
  echo "✅ ติดตั้งเสร็จแล้ว — สั่งให้ทำงานด้วยคำสั่งนี้:"
  echo "   ${VENV}/bin/python ${AGENT}"
fi

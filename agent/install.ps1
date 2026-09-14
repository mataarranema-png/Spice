# ────────────────────────────────────────────────────────────────
#  Spice Agent · ตัวติดตั้งสำหรับ Windows
#
#  วิธีใช้ — เปิด PowerShell แล้ววางบรรทัดที่หน้าเว็บให้มา:
#    irm https://เซิร์ฟเวอร์ของคุณ/install.ps1 | iex
#  หรือระบุค่าเอง:
#    & ([scriptblock]::Create((irm https://.../install.ps1))) -Server https://... -Pair XXXX-XXXX
# ────────────────────────────────────────────────────────────────
param(
  [string]$Server = "",
  [string]$Pair = "",
  [string]$Name = "",
  [switch]$Service,
  [switch]$NoService
)

$ErrorActionPreference = "Stop"

if (-not $Server) { Write-Host "X ต้องใส่ -Server https://..." -ForegroundColor Red; exit 1 }

$HomeDir = Join-Path $env:USERPROFILE ".spice"
$Venv    = Join-Path $HomeDir "venv"
$Agent   = Join-Path $HomeDir "spice_agent.py"
$PyExe   = Join-Path $Venv "Scripts\python.exe"

Write-Host "* ติดตั้ง Spice Agent ลงที่ $HomeDir" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $HomeDir | Out-Null

# ── 1. หา Python ────────────────────────────────────────────
$Python = $null
foreach ($candidate in @("python", "python3", "py")) {
  try {
    $version = & $candidate --version 2>&1
    if ($version -match "Python 3\.(9|1[0-9])") { $Python = $candidate; break }
  } catch { }
}
if (-not $Python) {
  Write-Host "X ไม่พบ Python 3 — ติดตั้งจาก https://python.org/downloads แล้วลองใหม่" -ForegroundColor Red
  Write-Host "  (ตอนติดตั้งอย่าลืมติ๊ก 'Add Python to PATH')" -ForegroundColor Yellow
  exit 1
}
Write-Host "* ใช้ $(& $Python --version)" -ForegroundColor Green

# ── 2. เตรียมสภาพแวดล้อมแยก ────────────────────────────────
if (-not (Test-Path $PyExe)) { & $Python -m venv $Venv }
& $PyExe -m pip install -q --upgrade pip
& $PyExe -m pip install -q requests

# ── 3. ดึงตัวแทนเครื่องจากเซิร์ฟเวอร์ของคุณ ─────────────────
Write-Host "* ดาวน์โหลดตัวแทนเครื่อง" -ForegroundColor Cyan
Invoke-WebRequest -Uri "$($Server.TrimEnd('/'))/agent/spice_agent.py" -OutFile $Agent -UseBasicParsing

# ── 4. ตรวจการ์ดจอแล้วลง PyTorch ให้ตรงรุ่น ─────────────────
$HasNvidia = $false
try { nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | Write-Host; $HasNvidia = $true } catch { }

if ($HasNvidia) {
  Write-Host "* พบการ์ดจอ NVIDIA — ติดตั้ง PyTorch (CUDA) ใช้เวลาสักครู่" -ForegroundColor Green
  & $PyExe -m pip install -q torch --index-url https://download.pytorch.org/whl/cu121
} else {
  Write-Host "! ไม่พบการ์ดจอ NVIDIA — จะรันบน CPU ซึ่งช้ามาก" -ForegroundColor Yellow
  & $PyExe -m pip install -q torch
}
& $PyExe -m pip install -q "transformers>=4.44" accelerate sentencepiece

# ── 5. จับคู่ครั้งแรก ───────────────────────────────────────
if ($Pair) {
  Write-Host "* กำลังจับคู่กับบัญชีของคุณ" -ForegroundColor Cyan
  $pairArgs = @($Agent, "--server", $Server, "--pair", $Pair, "--no-drive")
  if ($Name) { $pairArgs += @("--name", $Name) }
  $process = Start-Process -FilePath $PyExe -ArgumentList $pairArgs -PassThru -NoNewWindow
  Start-Sleep -Seconds 8
  if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
}

# ── 6. ให้ทำงานเองทุกครั้งที่เข้าเครื่อง ────────────────────
function Install-SpiceTask {
  $action  = New-ScheduledTaskAction -Execute $PyExe -Argument "`"$Agent`""
  $trigger = New-ScheduledTaskTrigger -AtLogOn
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
  Register-ScheduledTask -TaskName "SpiceAgent" -Action $action -Trigger $trigger `
    -Settings $settings -Force | Out-Null
  Start-ScheduledTask -TaskName "SpiceAgent"
  Write-Host "* ตั้งให้ทำงานเองแล้ว (Task Scheduler: SpiceAgent)" -ForegroundColor Green
  Write-Host "  หยุดถาวร: Unregister-ScheduledTask -TaskName SpiceAgent -Confirm:`$false"
}

$wantService = $Service
if (-not $Service -and -not $NoService) {
  $answer = Read-Host "ให้ทำงานเองทุกครั้งที่เข้าเครื่องไหม? [y/N]"
  $wantService = ($answer -match "^[yY]")
}

if ($wantService) {
  Install-SpiceTask
} else {
  Write-Host ""
  Write-Host "* ติดตั้งเสร็จแล้ว — สั่งให้ทำงานด้วยคำสั่งนี้:" -ForegroundColor Green
  Write-Host "  & `"$PyExe`" `"$Agent`""
}

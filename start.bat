@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title FGP Production System
cd /d "%~dp0"

echo.
echo   ============================================================
echo      FGP PRODUCTION SYSTEM
echo      ระบบบริหารการผลิต แผนก FGP
echo   ============================================================
echo.

set "PY="

REM 1) Python แบบพกพาที่วางไว้ในโฟลเดอร์ python\ (ไม่ต้องติดตั้งอะไรเลย)
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"

REM 2) Python ที่ติดตั้งในเครื่อง
if not defined PY (
  py -3 --version >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  python --version >nul 2>&1 && set "PY=python"
)

if not defined PY (
  echo   [ ไม่พบ Python ในเครื่องนี้ ]
  echo.
  echo   วิธีแก้ เลือกทางใดทางหนึ่ง
  echo     1. ติดตั้ง Python จาก https://www.python.org/downloads/
  echo        ตอนติดตั้งให้ติ๊ก "Add Python to PATH" ด้วย
  echo     2. หรือคัดลอกโฟลเดอร์ Python แบบพกพามาวางไว้ข้างไฟล์นี้
  echo        โดยตั้งชื่อโฟลเดอร์ว่า  python
  echo.
  pause
  exit /b 1
)

echo   ใช้ Python: %PY%
echo   กำลังเปิดระบบ...
echo.

%PY% -m fgp %*

if errorlevel 1 (
  echo.
  echo   ระบบหยุดทำงานผิดปกติ กรุณาถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแลระบบ
  pause
)
endlocal

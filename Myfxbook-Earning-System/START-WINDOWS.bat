@echo off
chcp 65001 >nul
title Myfxbook Earning System
cd /d "%~dp0"

echo.
echo   กำลังเปิด Myfxbook Earning System ...
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 start.py %*
    goto :done
)

where python >nul 2>nul
if %errorlevel%==0 (
    python start.py %*
    goto :done
)

where python3 >nul 2>nul
if %errorlevel%==0 (
    python3 start.py %*
    goto :done
)

echo   ไม่พบ Python ในเครื่องนี้
echo   ติดตั้งได้ฟรีที่ https://www.python.org/downloads/
echo   ตอนติดตั้ง ให้ติ๊กช่อง "Add Python to PATH" ด้วย
echo.
pause

:done
if %errorlevel% neq 0 pause

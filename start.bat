@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === TECH4U: تجهيز وتشغيل المسجّل ===
if not exist .venv\Scripts\python.exe py -3.12 -m venv .venv
git pull --ff-only
.venv\Scripts\python.exe -m pip install -q -r requirements-record.txt
.venv\Scripts\python.exe src\launch.py
pause

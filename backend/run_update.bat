@echo off
cd /d "C:\dse analyzer\backend"

:: Start uvicorn in background if not already running
netstat -ano | findstr :8000 >nul 2>&1
if errorlevel 1 (
    start /B python -m uvicorn app.main:app > uvicorn.log 2>&1
    timeout /t 10 /nobreak >nul
)

:: Run the update
python auto_update.py

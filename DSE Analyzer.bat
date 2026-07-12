@echo off
cd /d "C:\dse analyzer\backend"
start "DSE Analyzer" python -m uvicorn app.main:app
timeout /t 3 /nobreak > nul
start "" "http://localhost:8000/dashboard"
echo DSE Analyzer started. Close this window to stop.
pause

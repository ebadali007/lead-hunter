@echo off
title Lead Hunter AI Automation System ($0/mo Zero-Cost Agency Engine)
echo ============================================================================
echo   LEAD HUNTER AI AUTOMATION SYSTEM - ONE-CLICK WINDOWS LAUNCHER
echo ============================================================================
echo.

if not exist ".venv" (
    echo [1/4] Creating Python Virtual Environment (.venv)...
    python -m venv .venv
)

echo [2/4] Activating Virtual Environment & Installing Requirements...
call .venv\Scripts\activate.bat
pip install --upgrade pip --quiet
pip install -r requirements.txt

echo [3/4] Ensuring Playwright Chromium Browser is installed...
python -m playwright install chromium

echo [4/4] Starting Lead Hunter AI Web Dashboard on http://localhost:8000 ...
start "" http://localhost:8000
python main.py
pause


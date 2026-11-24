@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || (echo Python is not installed. Install it from python.org and tick "Add to PATH". & pause & exit /b)
if not exist .venv (python -m venv .venv)
call .venv\Scripts\activate
echo Installing / checking libraries...
python -m pip install -q -r requirements.txt
echo Starting...
python app.py 2> last_error.txt
if errorlevel 1 (
  echo.
  echo ===== The program stopped with an error =====
  type last_error.txt
  echo.
  echo Send a photo of this window to Claude.
  pause
)

@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (python -m venv .venv)
call .venv\Scripts\activate
pip install -q -r requirements.txt
pyinstaller --noconfirm --windowed --name GamalAlmshrqi --icon assets\icon.ico ^
  --add-data "ui;ui" --add-data "site;site" --add-data "assets;assets" --add-data "skills;skills" app.py
echo.
echo البرنامج جاهز في: dist\GamalAlmshrqi\GamalAlmshrqi.exe
pause

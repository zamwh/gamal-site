@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || (echo Python غير مثبت. ثبته من python.org وفعّل خيار Add to PATH & pause & exit /b)
if not exist .venv (python -m venv .venv)
call .venv\Scripts\activate
pip install -q -r requirements.txt
python app.py

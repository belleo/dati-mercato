@echo off
REM Lanciato ogni sera da Utilita di pianificazione di Windows
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (set PY=.venv\Scripts\python.exe) else (set PY=python)
%PY% market_data.py --push >> log.txt 2>&1

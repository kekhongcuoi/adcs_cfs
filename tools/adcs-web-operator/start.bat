@echo off
cd /d "%~dp0"
echo ADCS Ground Station - mo trinh duyet http://127.0.0.1:8000
py -3 server.py
if errorlevel 1 python server.py
pause

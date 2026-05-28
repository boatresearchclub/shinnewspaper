@echo off
cd /d C:\Users\user\Desktop\データ収集\scripts

if not exist logs mkdir logs

python run_daily.py

if %errorlevel% == 0 (
    echo [OK] Done
) else (
    echo [NG] Error - check logs folder
)

pause

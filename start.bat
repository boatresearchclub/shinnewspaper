@echo off
cd /d "C:\Users\user\Desktop\データ収集\scripts"

start "TenjiScraper" cmd /k "cd /d C:\Users\user\Desktop\データ収集\scripts && python tenji_from_csv.py"
timeout /t 2 /nobreak > nul

start "CommentScraper" cmd /k "cd /d C:\Users\user\Desktop\データ収集\scripts && python scrape_comments.py --now"
timeout /t 2 /nobreak > nul

start "AutoPush" cmd /k "cd /d C:\Users\user\Desktop\データ収集\scripts && python auto_push.py"
timeout /t 2 /nobreak > nul

start "BoatServer" cmd /k "cd /d C:\Users\user\Desktop\データ収集\scripts && python boat_server.py"

echo.
echo URL: https://boatresearchclub.github.io/shinnewspaper/
echo Local: http://localhost:5000
echo.
pause
@echo off
cd /d C:\Users\user\Desktop\データ収集\scripts

echo [%time%] モーター情報 全会場取得開始
echo ========================================

python fetch_tenji.py --venue kiryu      --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue toda       --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue tamagawa   --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue heiwajima  --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue hamanako   --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue gamagori   --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue tokoname   --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue tsu        --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue mikuni     --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue biwako     --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue suminoe    --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue amagasaki  --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue marugame   --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue kojima     --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue tokuyama   --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue ashiya     --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue wakamatsu  --date 2026-05-06 --race 1 --motor-only
python fetch_tenji.py --venue karatsu    --date 2026-05-06 --race 1 --motor-only

echo ========================================
echo [%time%] 全会場取得完了
pause

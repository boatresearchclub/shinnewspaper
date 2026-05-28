@echo off
chcp 932 > nul
cd /d "C:\Users\user\Desktop\データ収集"

REM Python実行ファイル
SET PYTHON="C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe"

REM =============================
REM 会場コード → 会場名 変換表
REM =============================
set "JCD_01=桐生"
set "JCD_02=戸田"
set "JCD_03=江戸川"
set "JCD_04=平和島"
set "JCD_05=多摩川"
set "JCD_06=浜名湖"
set "JCD_07=蒲郡"
set "JCD_08=常滑"
set "JCD_09=津"
set "JCD_10=三国"
set "JCD_11=びわこ"
set "JCD_12=住之江"
set "JCD_13=尼崎"
set "JCD_14=鳴門"
set "JCD_15=丸亀"
set "JCD_16=児島"
set "JCD_17=宮島"
set "JCD_18=徳山"
set "JCD_19=下関"
set "JCD_20=若松"
set "JCD_21=芦屋"
set "JCD_22=福岡"
set "JCD_23=唐津"
set "JCD_24=大村"

echo ============================================================
echo  apply_ev.py  -- 展示後 EV計算 / 参戦判断更新
echo  ※ このバッチは毎日実行.bat の後、展示後に手動実行します
echo ============================================================
echo.

REM ---- 会場コード入力 ----
IF "%~1"=="" (
    echo 会場コードを入力してください
    echo 1=桐生 2=戸田 3=江戸川 4=平和島
    echo 5=多摩川 6=浜名湖 7=蒲郡 8=常滑
    echo 9=津 10=三国 11=びわこ 12=住之江
    echo 13=尼崎 14=鳴門 15=丸亀 16=児島
    echo 17=宮島 18=徳山 19=下関 20=若松
    echo 21=芦屋 22=福岡 23=唐津 24=大村
    set /p JCD=会場コード:
) ELSE (
    set JCD=%~1
)

REM ---- 1桁なら0付ける ----
if 1%JCD% LSS 110 set "JCD=0%JCD%"

REM ---- 会場名へ変換 ----
call set "VENUE=%%JCD_%JCD%%%"

if "%VENUE%"=="" (
    echo 会場コードが不正です。
    pause
    exit /b 1
)

REM ---- 日付入力（省略時: 今日） ----
IF "%~2"=="" (
    REM 今日の日付を YYYY-MM-DD 形式で取得
    for /f "tokens=1-3 delims=/ " %%a in ("%date%") do (
        set Y=%%a
        set M=%%b
        set D=%%c
    )
    set TODAY=%Y%-%M%-%D%
    echo 日付（省略時: %TODAY%）
    set /p USER_DATE=日付（YYYY-MM-DD、省略でEnter）:
    IF "%USER_DATE%"=="" (set RACE_DATE=%TODAY%) ELSE (set RACE_DATE=%USER_DATE%)
) ELSE (
    set RACE_DATE=%~2
)

REM ---- レース番号（省略時: 全レース） ----
IF "%~3"=="" (
    set /p USER_RACE=対象レース番号（全レースはEnter）:
    IF NOT "%USER_RACE%"=="" set RACE_OPT=--race %USER_RACE%
) ELSE (
    set RACE_OPT=--race %~3
)

REM ---- EV閾値（デフォルト0.0） ----
IF "%~4"=="" (
    set MIN_EV_OPT=
) ELSE (
    set MIN_EV_OPT=--min-ev %~4
)

echo.
echo ============================================================
echo  会場: %VENUE%  日付: %RACE_DATE%  %RACE_OPT%
echo  EV閾値: %MIN_EV_OPT%
echo ============================================================
echo.

REM ── EV計算・参戦判断更新 ──────────────────────────────────────────
%PYTHON% scripts\apply_ev.py --venue %VENUE% --date %RACE_DATE% %RACE_OPT% %MIN_EV_OPT%

if %errorlevel% neq 0 (
    echo [FAILED] apply_ev.py
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  参戦判断更新完了！
echo  Excel の「%VENUE%_数値」シート →「★参戦判断（EV）」行 を確認
echo  %date% %time%
echo ============================================================
echo.
pause

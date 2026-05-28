@echo off
setlocal enabledelayedexpansion
chcp 932 > nul

set "JCD_22=•Ÿ‰ª"

set /p JCD=‰ïêƒR[ƒh: 

if 1!JCD! LSS 110 set "JCD=0!JCD!"

call set "VENUE=%%JCD_!JCD!%%"

echo VENUE=[!VENUE!]
pause
@echo off
rem Post today's reviewed post (one command, no scheduler). Double-click it or run it from a terminal.
rem Safe to run twice: post.py allows one post per day and never posts the same post twice.
rem Pass "nopause" to skip the final pause (for running it from a terminal or a Run button).
chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONUTF8=1
set THREADS_LIVE=yes
python scripts\post.py --scheduled --publish --topic "AI Threads"
echo.
python scripts\post.py --status
echo.
if /i not "%~1"=="nopause" pause

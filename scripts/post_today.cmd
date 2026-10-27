@echo off
rem Post the next reviewed post: show it first, then ask before posting. One command, no scheduler.
rem Picks the first unposted post in schedule order (dates are ignored). Stops if that post is not reviewed.
rem Safe to run twice: post.py allows one post per day and never posts the same post twice.
rem Pass "nopause" to skip the final pause (for running it from a terminal or a Run button).
chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONUTF8=1
set THREADS_LIVE=yes
echo === Preview (nothing is posted yet) ===
python scripts\post.py --scheduled --topic "AI Threads"
echo.
choice /c YN /n /m "Post this now? [Y/N] "
if errorlevel 2 (
  echo Cancelled. Nothing was posted.
) else (
  python scripts\post.py --scheduled --publish --topic "AI Threads"
  echo.
  python scripts\post.py --status
)
echo.
if /i not "%~1"=="nopause" pause

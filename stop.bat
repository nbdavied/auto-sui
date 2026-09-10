@echo off
REM ============================================================
REM  auto-sui 停止服务（Windows）
REM  按端口找到「监听中」的进程并结束它。
REM ============================================================
chcp 65001 >nul
setlocal enabledelayedexpansion

if "%PORT%"=="" set "PORT=8000"

echo 正在查找监听 %PORT% 端口的进程...

set "FOUND="
REM 只取 LISTENING 行，排除 PID 0（TIME_WAIT 的连接对端也会出现该端口号）
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /C:"LISTENING" ^| findstr /C:":%PORT% "') do (
    if not "%%p"=="0" (
        echo   结束 PID %%p
        taskkill /F /PID %%p >nul 2>&1
        set "FOUND=1"
    )
)

if not defined FOUND (
    echo 没有找到监听 %PORT% 端口的进程，服务可能已经停止。
) else (
    echo 服务已停止。
)
pause

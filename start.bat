@echo off
REM ============================================================
REM  auto-sui 一键启动（Windows）
REM  双击本文件即可启动服务，浏览器会自动打开。
REM  关掉这个黑窗口 = 停止服务。
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

REM ---- 可按需修改这几项 ----
set "PORT=8000"
REM 代理：Gmail 功能需要；不用 Gmail 也可以留着，不影响记账
set "PROXY=socks5://127.0.0.1:10808"
REM 改代码自动重启。做 Gmail 授权时请保持 0，否则重启会打断授权回调
set "RELOAD=0"
REM Python 解释器
set "PY=C:\Users\nbdav\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
REM --------------------------

if not exist "%PY%" (
    echo [错误] 找不到 Python: %PY%
    echo 请打开 start.bat 修改 PY 变量为你的 Python 路径。
    pause
    exit /b 1
)

set PYTHONIOENCODING=utf-8
if not "%PROXY%"=="" (
    set "HTTPS_PROXY=%PROXY%"
    set "HTTP_PROXY=%PROXY%"
)

echo ============================================
echo  启动 auto-sui 服务
echo  地址: http://127.0.0.1:%PORT%
echo  代理: %PROXY%
echo  按 Ctrl+C 停止
echo ============================================
echo.

REM 稍等片刻再开浏览器，避免页面比服务先到
start "" /b cmd /c "timeout /t 3 >nul & start http://127.0.0.1:%PORT%/"

"%PY%" run_server.py
pause

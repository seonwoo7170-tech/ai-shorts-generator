@echo off
REM Run the dashboard as a "server" for your phone: listens on all interfaces
REM (LAN / Tailscale), password-protected, and keeps the PC awake while running.
REM Set DASHBOARD_PASSWORD in .env first (python run.py serve refuses to bind
REM 0.0.0.0 without one). Pair with Tailscale to reach it from anywhere.
cd /d "%~dp0"
chcp 65001 >nul

findstr /b /c:"DASHBOARD_PASSWORD=" .env 2>nul | findstr /v /c:"DASHBOARD_PASSWORD=$" >nul
if errorlevel 1 (
    echo [!] .env 에 DASHBOARD_PASSWORD=비밀번호 를 먼저 넣어주세요. 없으면 외부 접속을 열지 않습니다.
    pause
    exit /b 1
)

REM prevent sleep while the server runs (display may still turn off)
powercfg /change standby-timeout-ac 0 >nul 2>&1

echo Starting Shorts Studio for phone access...
start "ShortsStudio" /min cmd /c "set DASHBOARD_HOST=0.0.0.0&& python run.py serve"
timeout /t 2 /nobreak >nul

echo.
echo  PC에서:     http://127.0.0.1:5000/shop
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo  같은 와이파이: http://%%a:5000/shop
where tailscale >nul 2>&1 && for /f %%a in ('tailscale ip -4 2^>nul') do echo  Tailscale(밖에서): http://%%a:5000/shop
echo.
echo  stop.bat 으로 종료.
timeout /t 5 /nobreak >nul

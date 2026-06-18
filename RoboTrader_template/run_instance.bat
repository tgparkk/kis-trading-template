@echo off
chcp 65001 > nul
REM ============================================================
REM  실전 인스턴스 런처 — 사용법: run_instance.bat <instance>
REM    예) run_instance.bat rs_leader
REM  격리: 계좌(instances\<id>\key.ini) / 프로세스(robotrader_<id>.pid)
REM        / 토큰(token_info_<id>.json) / 로그(logs\<id>\) / DB(real_trading_<id>)
REM ============================================================

if "%~1"=="" (
    echo [오류] 인스턴스 이름을 지정하세요. 예: run_instance.bat rs_leader
    pause
    exit /b 1
)
set INSTANCE=%~1

REM 현재 디렉토리(RoboTrader_template)로 이동 — main.py 위치
cd /d "%~dp0"

if not exist "instances\%INSTANCE%\key.ini" (
    echo [오류] instances\%INSTANCE%\key.ini 가 없습니다. 계좌 키를 먼저 배치하세요.
    pause
    exit /b 1
)

REM 가상환경 활성화 (페이퍼 봇과 동일 venv 공유)
if not exist "venv" (
    echo [오류] venv 가 없습니다. 먼저 run_robotrader.bat 로 venv를 생성하세요.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

REM 인스턴스 식별 — 설정/토큰/로그/PID/테이블이 이 값 기준으로 분리됨
set KIS_INSTANCE_DIR=instances\%INSTANCE%

REM 인스턴스별 로그 디렉토리 (파이썬 핸들러도 LOG_DIR=logs/<id> 로 기록)
if not exist "logs\%INSTANCE%" mkdir "logs\%INSTANCE%"

REM stdout/stderr 리다이렉트 로그 파일명 (YYYYMMDD_HHMMSS)
for /f "tokens=1-3 delims=/- " %%a in ("%date%") do (set YYYY=%%a&set MM=%%b&set DD=%%c)
set HH=%time:~0,2%
set MN=%time:~3,2%
set SS=%time:~6,2%
set HH=%HH: =0%
set LOGFILE=logs\%INSTANCE%\robotrader_%INSTANCE%_%YYYY%%MM%%DD%_%HH%%MN%%SS%.log

echo.
echo [실전 인스턴스] %INSTANCE% 시작 중... (KIS_INSTANCE_DIR=%KIS_INSTANCE_DIR%)
echo 로그: %LOGFILE%
echo 종료하려면 Ctrl+C
echo.
set PYTHONIOENCODING=utf-8
set SCREENER_SNAPSHOT_ENABLED=true
python -X utf8 main.py %2 %3 %4 %5 1>> "%LOGFILE%" 2>&1

echo.
echo [실전 인스턴스] %INSTANCE% 종료됨. 로그: %LOGFILE%
pause

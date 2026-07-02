@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================================
echo   RoboTrader 장 마감 후 자동 분석
echo ============================================================
echo.

REM 기본: 분석만 수행 (Claude 호출 안함)
REM [2026-07-02] scripts/auto_analysis.py 는 저장소에 존재하지 않아 비활성화 (Phase1).
REM 복구 시 docs/CODE_MAP.md 의 .bat 섹션도 함께 갱신할 것.

REM 문제 발견 시 Claude와 대화
echo (auto_analysis.py 부재로 분석 스킵 — docs/CODE_MAP.md 참조)

echo.
echo ============================================================
echo   분석 완료 - reports/auto_analysis 폴더에서 결과 확인
echo ============================================================
pause

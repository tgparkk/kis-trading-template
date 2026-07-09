# 장중 급락 후 반등 발굴 — 진행 원장

- 계획: docs/superpowers/plans/2026-07-09-intraday-rebound-discovery.md
- 브랜치: feat/intraday-rebound-discovery
- 워크트리: D:/tmp/wt-intraday-rebound  (라이브 트리 D:\GIT\kis-trading-template 접촉 금지)
- 게이트: Task 4 (스펙 2.2절 재현). 실패 시 중단·사용자 보고.

## 사전 검토 수정 (실행 전)
- Task 2: `_fallback_ohlcv` 중복 제거 → groupby(floor) 단일 구현 + 라이브 변환기 동등성 테스트 추가
- 전역: 계획서의 실행 경로 26곳을 라이브 트리 → 워크트리로 교체
- Global Constraints: 워크트리 격리·시스템 파이썬 명시

## 태스크

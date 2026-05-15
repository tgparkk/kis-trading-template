# 2026-05-15 robotrader DB 테이블 정리 + 분봉 경로 단일화

## 핵심 요약
- 사장님 질문("robotrader DB 분봉 몇 년치 몇 종목")에서 출발한 인벤토리 점검
- 권한 가시성 문제로 `minute_candles`(15개월, 1,347종목, **5,116만 행**)가 처음에 숨겨져 있었음 → 권한 부여로 해소
- 부수 발견된 죽은 legacy 테이블 `stock_prices`/`minute_prices` (각 9/1만 16,625행) 양 프로젝트 코드에서 제거 + DROP

## 배경
- 처음엔 `robotrader` 사용자로 접속하여 `information_schema.tables`로 분봉 테이블 조회 → `minute_prices` 1개만 보였고 9/1 하루치 16,625행이 전부였음
- 사장님 pgAdmin에서 `minute_candles 접근 권한 없음 (42501)` 에러 → 권한 가시성 문제 단서
- `pg_class` 직접 조회로 `minute_candles`/`daily_candles`가 `postgres` 사용자 소유로 실제로 존재 확인. RoboTrader 측 분봉 수집기는 **8개월간 정상 가동 중**이었던 것 (매일 15:45 `ExpandedMinuteCollector`, `minute_candles`에 적재)

## 권한 조치
- `GRANT SELECT ON minute_candles, daily_candles TO robotrader;`
- `GRANT USAGE ON SCHEMA public TO robotrader;`

## 발견된 죽은 테이블
- `stock_prices`: 16,625행 (2025-09-01 단 하루, 44종목). 양 프로젝트가 "레거시 호환용"으로만 표기. 8개월간 신규 0건
- `minute_prices`: 동일 행수/기간. kis-template의 `PostMarketDataSaver.save_minute_data_to_db` 경로가 silent fail 중이었던 결과. 어차피 RoboTrader가 `minute_candles`에 적재하므로 단일화 결정

## 코드 정리 (직원 분담 위임)
### RoboTrader (D:\GIT\RoboTrader, commit `79ca0a0e`)
- `db/database_manager.py`: PriceRecord dataclass + DAO 6개(`save_price_data`/`save_minute_data`/`get_minute_data`/`has_minute_data`/`get_price_history`/`get_candidate_performance`) + `cleanup_old_data` 정리
- `db/schema.py`: CREATE TABLE/INDEX DDL 제거
- `scripts/migrate_duckdb_to_pg.py`: legacy 리스트 정리
- `utils/chart_cli.py`: stats 출력 한 줄 제거
- `minute_prices`는 RoboTrader 코드 0건 매칭으로 작업 대상 외
- 4 files changed, +3 / **-219**

### kis-template (D:\GIT\kis-trading-template, commit `0f55984`)
- Repository: `PriceRepository` 5개 메서드 + `get_candidate_performance` 제거
- Live 경로: `PostMarketDataSaver.save_minute_data_to_db` 메서드 + `utils/data_cache.py` + `cache_manager.py` 통째 삭제
- `utils/unified_data_loader.py`: file_cache fallback 단순화 (DB-only)
- 테스트(`test_database.py`, `healthcheck/run_healthcheck.py`, `verify_imports.py`) + 문서(`docs/DATABASE.md`, `SYSTEM_FLOW.md`) + `init-scripts/01-init.sql` 동기화
- 15 files changed, +29 / **-708**

## DROP 실행
```sql
DROP TABLE stock_prices;
DROP TABLE minute_prices;
```
- `postgres` 사용자로 실행. CASCADE 불필요 (FK 없음)

## 회귀 검증
- RoboTrader: 329 passed, 신규 실패 0건
- kis-template: 1,647 passed, 3 skipped, **신규 실패 0건** (pre-existing 1건: `test_auto_resolve_latest_screener` 스크리너 JSON 만료 — 이미 4/18 메모에 기록된 이슈)

## 잔존 참조 확인
양 프로젝트 모두 grep 결과 동명이인 매칭만 남고 실제 `stock_prices`/`minute_prices`/`PriceRecord`/`DataCache` 참조 **0건**:
- `framework/data_providers/get_minute_data` — KIS API 인터페이스 메서드 (DB 무관)
- `tests/test_network_resilience.py::test_multiple_stock_prices_partial_failure` — 영문 우연 일치
- `core/post_market_data_saver.py:save_minute_data_to_file` — 텍스트 파일 저장 (DB 무관)

## 후속 과제
- RoboTrader 측 `config/settings.py`의 `PG_USER='postgres'` + `PG_PASSWORD=''` 자격증명은 추후 정리 검토 (현재 trust 인증으로 동작 중)
- 직원이 응답 중간에 잘리는 사례 2회 발생 — 작업 위임 단위를 더 잘게 쪼개거나 task tool로 추적하는 운영 패턴 고려

## 최종 robotrader DB 분봉 현황 (정리 후)
- **`minute_candles`** (RoboTrader, postgres 소유): 1,347종목 × 15개월 ≈ **5,116만 행, 10GB** — 매일 15:45 자동 적재 중
- `daily_candles` (RoboTrader): 52K행 — 유지
- `daily_prices` (kis-template): 288종목, 7/1~5/15, 29,785행 — 매일 적재 중
- legacy `stock_prices`/`minute_prices`: **제거 완료**

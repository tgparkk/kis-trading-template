# foreign_flow → kis_template 자동 수집기 신설 + 리더 정리

> 작성 2026-06-30. 목표: 외국인 순매매량(foreign_flow)을 daily/minute/index 와 동일하게
> 신규 `kis_template` DB로 **자동 EOD 수집** + 기존 레거시 데이터 1회 백필 + 죽은 다운스트림 리더 정리.

## 배경 / 현황 (검증된 사실)

- 외국인 데이터가 존재하는 유일한 테이블: **`robotrader_quant.foreign_flow`** (122,437행 / 159종목 / max **2026-06-12**).
  - 스키마: `stock_code VARCHAR(10), date DATE, foreign_net_vol BIGINT, source VARCHAR(20), created_at TIMESTAMP`, PK(stock_code,date).
  - 소스: 네이버 금융 `finance.naver.com/item/frgn.naver` (외국인 순매매**량**, shares). KIS API에는 외국인 순매수 필드 없음(grep 확인).
- 수집 방식: `scripts/backfill_foreign_flow.py` **수동 실행만**. 자동 EOD 훅 없음 → 06-12 stale.
- 신규 `kis_template.foreign_flow`: **테이블 자체 없음**.
- 다운스트림 리더 `signals/foreign_flow.py`: `robotrader.foreign_flow_daily.net_buy_val` 참조 →
  **그 테이블/컬럼은 어느 DB에도 없음** → 외국인 시그널 사실상 죽어 있음.

## 미러링할 기존 패턴 (그대로 따름)

- DDL: `scripts/kis_db/schema.py` (`DDL_STATEMENTS` + `EXPECTED_TABLES`)
- 백필(시딩): `scripts/kis_db/seed_from_legacy.py` (`_copy` 헬퍼 재사용)
- writer: `collectors/index_writer.py` (UPSERT SQL + df→rows)
- collector + reconcile: `collectors/index_collector.py` (`collect_*` + `reconcile_*`, `new_rows==0 → FAIL` 가드)
- verdict 헬퍼: `collectors/daily_collector.py:reconcile_verdict`
- EOD 오케스트레이션: `collectors/eod_collection.py:run_data_collection`
- EOD 훅 로그: `bot/system_monitor.py:_run_data_collection` (414~425)
- 테스트: `tests/collectors/test_eod_collection.py`

## 작업 항목 (TDD — 각 항목 test-first)

### 1. 스키마 (`scripts/kis_db/schema.py`)
- `DDL_STATEMENTS` 에 `foreign_flow` 추가 — **레거시와 동일 컬럼/PK**:
  `stock_code VARCHAR NOT NULL, date DATE NOT NULL, foreign_net_vol BIGINT, source VARCHAR DEFAULT 'naver', created_at TIMESTAMP DEFAULT now(), PRIMARY KEY(stock_code,date)` + `CREATE INDEX ix_foreign_flow_date ON foreign_flow(date)`.
- `EXPECTED_TABLES` 에 `"foreign_flow"` 추가.
- 테스트: `tests/kis_db` 에 EXPECTED_TABLES 포함 검증.

### 2. writer (`collectors/foreign_flow_writer.py` 신규)
- `naver_df_to_rows(code, df) -> list[dict]`: backfill_foreign_flow.py 의 파싱 결과(date, foreign_net_vol) → 행 dict.
- `UPSERT SQL` + `upsert_foreign_rows(conn, rows) -> int` (`ON CONFLICT (stock_code,date) DO UPDATE`).
- 테스트: 파싱/UPSERT dict 형태 단위테스트.

### 3. collector (`collectors/foreign_flow_collector.py` 신규)
- `collect_foreign_flow(target_date=None, limit=None) -> dict`:
  - universe = `daily_prices` 종목코드(`load_universe` 동일 쿼리) — backfill 의 `get_stock_codes` 와 동치.
  - 종목별 `fetch_foreign_naver(code, max_pages=2)` (최근 ~40일이면 EOD 증분 충분; backfill 스크립트의 fetch 재사용 import).
  - `KisDbConnection` 으로 upsert. 반환 `{"codes": n, "rows": total}`.
- `reconcile_foreign_flow(trade_date) -> dict`:
  - 레거시 `robotrader_quant.foreign_flow` 당일 행수(real_rows)/값 vs kis(new_rows) 비교, `collection_reconciliation` dataset=`'foreign_flow'` 기록.
  - **가드**: `new_rows==0 → FAIL`(네이버 차단·스크래핑 실패 탐지).
  - **레거시 동결 처리**: 레거시는 06-12 이후 갱신 안 됨 → `real_rows==0 and new_rows>0` 이면 교차검증 불가이므로 `verdict="PASS"`(no-legacy), `value_match_rate=1.0`, `coverage=1.0` 로 별도 처리(daily verdict 와 분기). `new_rows==0` 만 FAIL.
- 테스트: collect upsert 경로(네이버 fetch monkeypatch), reconcile 3분기(정상 overlap / 레거시동결 / new=0 FAIL).

### 4. EOD 오케스트레이션 (`collectors/eod_collection.py`)
- import `collect_foreign_flow, reconcile_foreign_flow`.
- `out["foreign_flow"] = _safe(collect_foreign_flow, trade_date)`.
- grace 분기 `out["reconcile"]["foreign_flow"] = _safe(reconcile_foreign_flow, dash)`.
- 테스트(`test_eod_collection.py`): 기존 3테스트의 `calls`/`reconcile` 키에 `foreign_flow` 반영하도록 갱신 + 단계격리 테스트 유지.

### 5. EOD 훅 로그 (`bot/system_monitor.py:_run_data_collection`)
- `foreign = result.get("foreign_flow", {})` 추출 + 로그 라인에 `· 외국인수급 {foreign}` 추가. (동작 변경 없음, 로깅만.)

### 6. 리더 정리 (`signals/foreign_flow.py`)
- 소스 전환: `robotrader.foreign_flow_daily.net_buy_val` → **`kis_template.foreign_flow.foreign_net_vol`** (KisDbConnection/`KIS_DB_*` env).
- SQL: `SELECT date, foreign_net_vol FROM foreign_flow WHERE stock_code=%s AND date BETWEEN %s AND %s ORDER BY date DESC LIMIT 5`.
- 시그널 의미: `foreign_net_buy_5d_cum` = 최근 5영업일 순매매량 합. `foreign_flow_signal` 의 `val>0`(순매수 양수) 불리언 의미 보존(량 기준이어도 부호 동일). docstring 갱신(소스=네이버/순매매량, PIT shift(1) 유지).
- 호출처 계약 변경 없음(시그니처 유지). 호출처 grep 후 회귀 확인.
- 테스트: 신규 스키마 대상 리더 단위테스트(없으면 신설), 데이터 없음→NaN/False, 5일 합산, PIT end_date=scan_date-1.

### 7. 백필 시딩 (`scripts/kis_db/seed_from_legacy.py`)
- `FOREIGN_COLUMNS = ["stock_code","date","foreign_net_vol","source"]`.
- `seed_foreign_flow(apply=False)`: `_copy("robotrader_quant", sel, "foreign_flow", FOREIGN_COLUMNS, apply)`.
- `__main__` 에 추가 출력.
- 테스트: `build_*`/SELECT 구성 단위테스트(기존 시딩 테스트 패턴).

## 런타임 절차 (구현·테스트 green 이후, **사용자 확인·올바른 venv 필요**)
1. `python -m scripts.kis_db.schema` — foreign_flow 테이블 생성.
2. `python -m scripts.kis_db.seed_from_legacy --apply` — 레거시 122k행 1회 복사.
3. 봇 재기동 — 다음 EOD(15:48)부터 foreign_flow 자동 수집·reconcile.
4. 검증: `collection_reconciliation` 에 dataset='foreign_flow' PASS 확인 + 신규 행 max date 증가 확인.

## 비고 / 리스크
- 네이버 HTML 스크래핑은 차단·구조변경 리스크 → `_safe` 단계격리로 EOD 흐름 비차단(기존 설계 유지). 실패 시 reconcile FAIL 로 가시화.
- 레거시 foreign_flow 는 동결(06-12). 이후 reconcile 는 사실상 "오늘 수집 성공 여부(new_rows>0)" 가드로 동작.
- git: 브랜치 작업·로컬 커밋까지, **머지/푸시 보류**(사용자 확인).

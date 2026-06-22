# 데이터 수집 + 데이터 소유권 kis_template 전용 DB 이관 — 설계 (Spec)

**작성일**: 2026-06-22 (개정: 전용 DB 통합안 B 채택)
**상태**: 설계 승인됨 (구현 계획 대기)
**배경**: rt(`D:\GIT\RoboTrader`)·rt_quant(`D:\GIT\RoboTrader_quant`) 전략 폐기. 이 둘이 각각 분봉·일봉을 DB에 적재 중이고, kis_template는 자기 데이터(paper 원장·equity·corp_events·screener)마저 rt 소유 `robotrader` DB에, 일봉은 rt_quant 소유 `robotrader_quant` DB에 더부살이 중이다. 두 DB의 주인이 사라지므로, **kis_template 전용 DB(`kis_template`)를 신설해 수집 책임과 데이터 소유권을 모두 이관**한다. 6/19 사고(런처에서 rt 제외→분봉 수집 중단) 재발 방지 + 유예기간 병행·검증 후 안전 전환.

---

## 1. 목표 / 비목표

**목표**
- **신규 전용 DB `kis_template`** 를 만들어 kis_template 소유 데이터 전부를 이관(통합안 B).
- 봇이 **분봉(거래대금순 300)**·**일봉(전체시장 ~2,601)**·**지수 일봉**을 EOD에 수집·적재(완전 드롭인: 동일 유니버스·컬럼).
- 폐기될 `robotrader`/`robotrader_quant` DB와 **완전 단절**.
- **단계적**(A→B→C) 진행, 각 단계는 유예·검증 후 전환. 6/19식 공백 0.

**비목표 (YAGNI)**
- rt/rt_quant 코드 수정 (유예기간 내내 무수정·계속 가동).
- 장중 실시간 DB 적재 (EOD 배치만).
- 자동 전환 (전환은 수동 결재).
- 신규 KIS API 추가 (kis_template 기존 API로 완결).
- 빅뱅 전환 (단계적으로 위험 분산).

---

## 2. 타깃 상태: 새 DB `kis_template`

- 위치: localhost:5433 (기존과 동일 인스턴스, 새 database).
- 단일 연결 설정 `KIS_DB_*`(default `database=kis_template`) — 기존 robotrader/robotrader_quant **2-DB 분리를 1-DB로 통합**.
- 담을 테이블(전부 이관):

| 분류 | 테이블 | 현재 위치 | 이관 방식 |
|---|---|---|---|
| 시장데이터 | `minute_candles` | robotrader | 수집 재현(Phase A) |
| 시장데이터 | `daily_prices` | robotrader_quant | 수집 재현 + 시딩(Phase A) |
| 시장데이터 | `index_daily`(KOSPI/KOSDAQ) | robotrader | 수집 재현(Phase A) |
| 데이터(adj 소스) | `corp_events` | robotrader | 복사 + 증분 백필(Phase A) |
| 운영 | `virtual_trading_records` | robotrader | 복사 + 쓰기전환(Phase B) |
| 운영 | `paper_trading_state` | robotrader | 복사 + 쓰기전환(Phase B) |
| 운영 | `paper_strategy_equity` | robotrader | 복사 + 쓰기전환(Phase B) |
| 운영 | `screener_snapshots` | robotrader | 복사 + 쓰기전환(Phase B) |

> **섀도우 테이블 불필요**: 새 DB 자체가 유예기간의 병행본. 검증은 **교차 DB 비교**(새 DB vs 레거시 DB). 전환 = 읽기/쓰기 경로를 새 DB로 전환.

---

## 3. 설계 결정 (확정)

| # | 결정 | 선택 |
|---|---|---|
| D1 | 수집 범위 | 완전 드롭인 — 분봉 300(거래대금순), 일봉 2,601(전체시장), 지수 |
| D2 | 일봉 컬럼 | 전 컬럼(파생 포함): OHLCV+trading_value+market_cap+returns_1d/5d/20d+volatility_20d+adj_factor |
| D3 | 데이터 소유권 | **신규 전용 DB `kis_template`로 전부 이관(통합안 B)** |
| D4 | 유예·전환 | 수집은 **항상 새 DB에 적재**, 플래그 `KIS_DATA_SOURCE`(`legacy`\|`new`)가 **읽기 경로**를 제어. grace=legacy 읽기+교차비교 → N일 무결 후 **수동**으로 new 전환 |
| D5 | 실행 위치 | 봇 EOD 훅 내장(`system_monitor._handle_postmarket_tasks`, 15:35+, `asyncio.to_thread` 비차단) |
| D6 | 진행 | **단계적 A→B→C** (빅뱅 아님) |

---

## 4. 단계별 설계

### Phase A — 시장데이터 + corp_events (수집·비교·전환)
1. **새 DB·스키마 생성**: `kis_template` DB + `minute_candles`·`daily_prices`·`index_daily`·`corp_events` (레거시와 동일 스키마).
2. **일봉 시딩**: 레거시 `robotrader_quant.daily_prices` 과거분을 새 DB로 1회 복사 → 파생(returns/volatility)·adj_factor가 첫날부터 유효(윈도우 함수·adj는 이력 필요). `corp_events`도 복사 + 이후 기존 OpenDART 백필을 새 DB 대상으로 증분.
3. **EOD 수집(봇 훅)**: 수집은 **항상 새 DB에 적재**(grace/전환 무관).
   - 일봉: 전체시장 코드(FDR) → 당일 OHLCV(FHKST03010100)+시총(get_stock_market_cap) fetch → 새 DB UPSERT → `SQL_UPDATE_RETURNS`로 파생 → corp_events 기반 adj_factor 갱신.
   - 분봉: 거래대금순 top300(get_volume_rank 12콜) → 당일 전체 분봉(FHKST03010230, 4구간) → 새 DB 종목·일자 DELETE+INSERT.
   - 지수: KOSPI/KOSDAQ 당일 지수 일봉(FDR) → 새 DB.
4. **교차 DB 비교**(`reconciliation`, `KIS_DATA_SOURCE=legacy`인 grace 동안): 새 DB vs 레거시 당일분 대조 → `collection_reconciliation` 기록.
5. **전환**: ≥5거래일 무결 + 결재 → `KIS_DATA_SOURCE=new`로 변경 → kis_template **읽기 경로**(quant_daily_reader·분봉 reader)가 새 DB를 보도록 전환.

### Phase B — 운영 테이블 (복사·쓰기전환 컷오버)
- 대상: `virtual_trading_records`·`paper_trading_state`·`paper_strategy_equity`·`screener_snapshots` (봇이 매일 쓰는 라이브 데이터).
- **컷오버일 D 지정**: D-1까지 기존 행을 새 DB로 1회 복사 → 봇의 쓰기/읽기를 새 DB로 전환(D일부터) → 행수·최근일·합계 정합성 검증(예: paper_strategy_equity 현금합 = paper_trading_state 일치 유지).
- equity 훅·paper 원장 재구성 경로가 새 DB를 보도록 연결 변경.

### Phase C — 폐기
- rt/rt_quant를 `run_all_robotraders.bat`에서 제거.
- 안전기간(예: 2주) 후 레거시 테이블/DB(`robotrader`·`robotrader_quant` 내 이관분) 삭제.

---

## 5. 재사용 자산 (kis_template 기보유 — 신규 포팅 0)

| 기능 | 위치 | 비고 |
|---|---|---|
| 일봉 OHLCV fetch | `api/kis_market_api.py:101` `get_inquire_daily_itemchartprice` (FHKST03010100) | rt_quant 동일 |
| 시가총액 fetch | `api/kis_market_api.py:740` `get_stock_market_cap` (`hts_avls` 억원→원) | rt_quant 동일 방식 |
| 분봉 fetch | `api/kis_chart_api.py` (FHKST03010230, 4구간) | |
| 거래대금순 유니버스 | `api/kis_market_api.py` `get_volume_rank` (12콜) | 분봉 300 선정 |
| 전종목 마스터 | `FinanceDataReader.StockListing` | 일봉 유니버스 |
| 파생 returns/volatility | `scripts/etl_backfill_daily_prices.py` `SQL_UPDATE_RETURNS` | 멱등·PIT안전 |
| adj_factor | `scripts/10pct_strategy/p0_apply_adj_factor.py` `compute_adj_factors/update_adj_factors` | corp_events 기반 |
| corp_events 백필 | `scripts/backfill_corp_events.py` (OpenDART+KRX+FDR) | |
| OHLCV 배치 쓰기 | `db/repositories/price.py` `save_daily_prices_batch` | UPSERT |
| 지수 일봉 | `scripts/backfill_kospi_index.py` (FDR KS11/KQ11) | regime 게이트 의존 |

**시가총액 계산(rt_quant 동일)**: `get_stock_market_cap`로 현재시총·현재가 → `listed_shares = 현재시총/현재가` → 일자별 `market_cap = close × listed_shares`. `hts_avls`는 억원 단위(×1e8).

---

## 6. 연결 / 설정

- 신규 연결 설정 `KIS_DB_*`(host/port/db/user/pw, default `database=kis_template`).
- **grace 동안 다중 연결**: 새 DB(쓰기/읽기) + 레거시 DB(비교용). 각 Phase 전환 시 해당 읽기/쓰기 경로를 새 DB로 승격.
- 기존 `db/connection.py`(robotrader)·`db/quant_daily_reader.py`(robotrader_quant)는 전환 완료까지 비교/레거시용으로 유지, 전환 후 새 DB로 일원화.

---

## 7. 비교(reconciliation) 규칙

- **일봉(전체시장)**: 거의 정확 일치 기대. 행수·종목 커버리지·종가/거래량 값 일치율, 불일치 목록. 허용오차 = 부동소수 epsilon.
- **분봉(거래대금순 300)**: rt와 kis_template가 각자 독립 top300을 시점차 두고 선정 → 유니버스 비동일. 판정 = ① 커버리지 ~300 ② **교집합 종목의 바 단위 값 일치율**(완전 동일 강요 X).
- 결과: `collection_reconciliation(trade_date, dataset, real_rows, new_rows, overlap, value_match_rate, coverage, verdict)`.
- **운영데이터(Phase B)**: 복사 직후 행수·최근일·핵심합계(현금합 등) 일치 검증.

---

## 8. 에러 처리 / 안전

- 훅 전체 try/except로 EOD 흐름 비차단(equity 스냅샷 훅과 동일). grace 중엔 새 DB라 레거시 무영향.
- 멱등: 분봉 DELETE+INSERT, 일봉 UPSERT, 운영 복사 재실행 안전.
- 비차단: `asyncio.to_thread`로 ~10분 루프가 모니터 태스크 비차단.
- Rate-limit: 봇 토큰버킷 재사용. EOD 버스트 ≈ 6,400콜(~7–11분). 봇 이미 ~217K콜/일 → 쿼터 비이슈.
- 봇 생존: 마감 후 ≥18:47 가동 확인 → 수집 윈도우 충분.
- **운영데이터 컷오버 안전**: 컷오버일 봇 시작 전 복사 완료 → 1봇 1DB만 쓰도록(이중쓰기 금지). 롤백: 플래그를 레거시로 되돌리면 복구.

---

## 9. 테스트 전략

- 단위: 시총 단위변환·per-row market_cap, 분봉 idx/time 매핑, reconciliation 판정, 운영 복사 정합성 검사.
- 재사용 검증자산: 파생 SQL·adj_factor 공식 기존 검증(스팟체크·PIT 회귀) 회귀로 포함.
- 통합(dry-run): 소수 종목(예 5)으로 새 DB 적재→교차비교 e2e 1거래일. Phase B는 소수 전략 복사→정합성 e2e.

---

## 10. 미해결 (계획단계 세부, 블로커 아님)

- N(전환 무결일수) 기본 5 — 조정 가능.
- Phase B 컷오버일 지정·롤백 절차 상세.
- 분봉 4구간 시각 경계(KRX 09:00–15:30).
- corp_events 증분 갱신 주기(분할 드묾 — 주1회/이벤트 트리거).
- TimescaleDB 하이퍼테이블 여부(분봉/일봉 대용량 — 레거시와 동일 구성 따를지).

---

## 부록: 핵심 파일 레퍼런스

- rt 분봉: `D:\GIT\RoboTrader\core\expanded_minute_collector.py`, `utils/data_cache.py`(스키마·INSERT)
- rt_quant 일봉: `D:\GIT\RoboTrader_quant\core\helpers\screening_task_runner.py:217`(전종목 루프), `core/ml_data_collector.py:206`(market_cap 역산)
- kis_template 훅: `bot/system_monitor.py._handle_postmarket_tasks`
- kis_template 연결: `db/connection.py`(robotrader), `db/quant_daily_reader.py`(robotrader_quant)

# MULTIVERSE4 라이브 정합 — 유니버스(PIT) + 사이징 설계

- **작성일**: 2026-06-28
- **대상**: `scripts/multiverse4_returns_export.py` (측정 전용 하니스)
- **분류**: 측정 도구 수정 (라이브 매매 코드·DB·SSOT 무변형)
- **승인**: 사장님 승인(2026-06-28) — 범위 "유니버스 + 사이징 둘 다"

## 1. 배경 / 문제

멀티버스4 정합 감사(2026-06-28)에서 멀티버스 측정값이 라이브로 전이되지 않는 두 구조적 🔴를 확인:

1. **유니버스 미래참조/생존편향** — `_load_top_volume_daily`(`scripts/book_param_multiverse.py:176-189`)가
   `SUM(close*volume)`을 **전(全) 백테스트 기간**으로 합산해 상위 N종목을 한 번 뽑아 기간 내내 고정한다.
   → 후보 멤버십이 미래 거래대금을 참조(look-ahead)하고, 사라진 종목은 애초에 빠진다(survivorship).
   라이브는 매일 EOD에 그 시점까지 데이터로 전략별 스크리너(`base_filter`: 시총·거래대금 플로어)를 재실행한다.
   → **멀티버스 후보군 ≠ 라이브 후보군**.

2. **사이징 불일치** — 멀티버스 `MAX_PER_STOCK = 1,000,000` 고정(`scripts/multiverse4_returns_export.py:79`).
   라이브는 `자본÷K`(`main.py:212-222` → `core/virtual_trading_manager.py:228-229`):
   elder 50만(÷20)·daytrading 200만(÷5)·minervini 333만(÷3). 소스 주석(L75-79 "라이브=100만")은 stale.
   → Sharpe(레버리지 불변)는 유지되나 절대 PnL·CAGR·**MaxDD(자본대비%)**가 전이 안 됨.
   특히 minervini "MaxDD 17%"는 30%만 투자(70% 유휴현금)한 희석 결과 — 라이브 만기배포 시 DD 대폭 확대.

진입 신호 로직 자체는 미래참조 없음(bar i 판정 → i+1 시가 체결). 문제는 **유니버스 멤버십 + 사이징**에 한정.

## 2. 목표 / 비목표

**목표**: 멀티버스4가 (a) 라이브 EOD 스크리너와 동일한 PIT 유니버스, (b) 라이브와 동일한 per-stock 사이징으로
측정하도록 한다. 재실행 시 Sharpe/PnL/DD가 라이브 예측치가 된다.

**비목표**:
- 라이브 매매 코드/DB/SSOT 변경 (측정 도구만 수정).
- 진입/청산 룰 변경 (이미 1:1 정합).
- 미커밋 WIP(deep_mr 8번째 전략 추가 + 시총 정밀 백필, 브랜치 `feat/deepmr-wire-and-mcap-precision`)와는 **분리** 취급.
- 라이브 `max_candidates=10/일` 일별 컷의 정확 복제(§5 근사 참조).

## 3. 핵심 발견 — 인프라 기존재

`backtest/screener_universe.py`가 **바로 이 목적**으로 이미 구현·테스트됨(모듈 docstring 명시):
- `load_screener_universe(strategy_name, scan_date, reader=...)` → 그 날 `base_filter` 통과 종목코드.
  내부적으로 `runners._adapter_factory.build_adapter`로 어댑터를 얻어 라이브와 동일한 `base_filter`를
  `QuantDailyReader.get_universe_snapshot(scan_date)`에 적용(결측 시총 fail-closed 그대로).
- `load_screener_universe_range(strategy, start, end, reader=...)` → `{date: [codes]}`.
- `make_scan_eligible_resolver(strategy, scan_dates, reader=...)` → PIT resolver `(code, d) -> bool`
  ("가장 최근 scan_date≤d의 통과집합" 멤버십, scan_date별 1회 캐시).
- `pit_gate_signal_cache(signal_cache, data, resolver)` → 멀티버스4 `_precompute_signals` 산출 형식
  `{code: [bar_idx]}`을 그대로 PIT 게이팅.

즉 본 작업 = **새 로직 발명이 아니라 위 모듈을 `multiverse4_returns_export.py`에 배선**.

## 4. 설계

### 4.1 변경 1 — 유니버스 PIT 정합

`multiverse4_returns_export.py`:

1. **scan_dates 산정 (월별)**: `[start, end]` 구간을 월별 1개 scan_date로 근사(시총·거래대금 완만 →
   분기보다 정밀, 일별보다 가벼움 — 모듈 권장). 거래일 정렬은 `QuantDailyReader`/`screener_universe`의
   `date<=scan_date` 방어 폴백에 위임.

2. **데이터 로드 유니버스 = 스크리너 합집합 (전략별)**:
   - 현행 `_get_data(top_n)`(거래대금 top-N 공유 로드)을 **전략별** 경로로 교체.
   - `union = ∪ load_screener_universe_range(strategy, 월별 scan_dates)` → `_load_daily_adj(union, start, end)`로
     가격데이터 로드. (스크리너 통과 종목이 거래대금 top-N 밖이어도 시뮬 가능)
   - `turnover`(우선순위용)는 로드된 union 기준으로 재계산.

3. **진입 PIT 게이팅 (`run_one`)**:
   - `cache = spec.build_signals(data)` 직후
     `resolver = make_scan_eligible_resolver(spec.name, 월별_scan_dates, reader=...)`
     `cache = pit_gate_signal_cache(cache, data, resolver)`
   - 이후 `run_portfolio(... signal_cache=cache ...)`는 무변경(거래대금 우선순위는 동점 정렬로만 잔존).

4. `_load_top_volume_daily` 정적 경로는 본 산출 경로에서 제거(다른 스크립트가 import하면 보존).

### 4.2 변경 2 — 사이징 라이브 일치

1. `MAX_PER_STOCK` 전역 상수(1,000,000) 제거 또는 기본값화.
2. `run_one`(또는 `main` 루프)에서 **per-stock = `INITIAL / spec.K`** 산출해 `run_portfolio(max_per_stock=...)`로 주입.
   - elder 50만·daytrading 200만·minervini 333만·deep_mr 200만 등 자동.
3. `--max-per-stock` CLI는 유지(미지정 시 자본/K 기본; 지정 시 전 전략 고정 — 민감도용).
4. stale 주석(L75-79) 정정 — "라이브 per-stock = INITIAL/K (전략별)".

## 5. 충실도 단서 (의도적 근사 — 명시)

- **base_filter까지 일치, max_candidates 근사**: PIT 게이트는 라이브 스크리너의 시총·거래대금 플로어
  (`base_filter`) 멤버십까지 정합. 라이브의 일별 `max_candidates=10` 상위컷은 멀티버스의
  `max_positions=K + 거래대금 우선순위`로 **근사**(정확 복제 아님). 기존 모듈·정직본 baseline과 동일 방침.
- **scan 주기 월별 근사**: 일별이 아닌 월별 scan. 시총·거래대금 저빈도 변화 가정.
- **DB 의존성**: `QuantDailyReader.get_universe_snapshot` (시총 백필 완료분, 5.5년 ~99.7% 충전) 필요.
  테스트는 reader 주입으로 DB 비의존.

## 6. 테스트 (TDD)

`tests/test_multiverse4.py` 확장 (주입 reader/fake adapter로 DB 불필요):
1. **PIT 게이팅 적용**: `base_filter` 탈락 종목의 신호 bar가 `run_one` 산출에서 제거됨.
2. **PIT 시점성**: scan_date 이전 진입봉은 미적격(False), 이후는 적격.
3. **사이징**: per-stock = `INITIAL / spec.K` (elder=500k, minervini≈3.33M 등) 산출 검증.
4. **회귀 가드**: 정적 top-volume 유니버스가 산출 경로에서 미사용.

`backtest/screener_universe.py`는 기존 테스트 보유 → 신규 최소.

## 7. 산출물 영향

- 3전략(및 8전략) Sharpe/PnL/DD가 라이브 정합 수치로 재산출 — minervini DD 과소평가·daytrading 부호 재확인 가능.
- `multiverse4_portfolio_analysis.py`(상관·합성·부트스트랩 CI)는 CSV 규약 동일 → 무변경.
- 비용 민감도(`--commission/--tax/--slippage`) 경로 무변경.

## 8. 리스크 / 완화

- **성능**: 전략별 union 로드 + 월별 scan DB 조회 → 정적 top-N 대비 느림. 완화: 월별 cadence + resolver 내
  scan_date별 1회 캐시 + union 중복 종목 데이터 재사용.
- **빈 유니버스**: scan_date 스냅샷 결측 시 `load_screener_universe`가 빈 리스트(fail-closed) → 그 구간 신호 전무.
  과거 시총 결측 구간에서 거래 급감 가능 — 백필 충전율(99.7%)로 대부분 해소, 잔여 결측 구간은 로그로 가시화.
- **adapter_factory 커버리지**: `build_adapter`가 측정 대상 전 전략 지원 필요(정직본 baseline에서 검증된 경로).

# Spec: D-1 Stocks-in-Play universe (분봉 데이트레이딩)

- 작성일: 2026-05-22
- 상태: 설계 확정 (사장님 승인)
- 연관: [changelog-2026-05-21-trail-bug-orb-revival.md](changelog-2026-05-21-trail-bug-orb-revival.md) §7 (룩어헤드), [research-2026-05-20-daytrading-deep-dive.md](research-2026-05-20-daytrading-deep-dive.md) §2 (Stocks-in-Play)

## 1. 배경

분봉 토너먼트의 dynamic universe(`build_universe_for_date`, 변동성 상위 50)는 거래일 당일 종일 데이터로 종목을 선별하는 룩어헤드 버그가 있었음(changelog §7). D-1 빌드로 수정 후 재검증 스모크에서 plain ORB는 평균 -0.67%/일·승률 33%로 엣지 없음 확인 — "변동성 상위 N"이라는 universe 자체가 약한 신호임이 드러남.

research-2026-05-20 §2 결론: 단독 ORB는 죽었고 "Stocks in Play"(RVOL≥2× + 갭≥4% + 촉매) 교집합에서만 부활(Concretum 2024, Sharpe 2.81). universe를 이 방향으로 재설계한다.

## 2. 목표 / 비목표

### 목표
- 거래일 X의 universe를 **D-1 이전 데이터만으로** "어제 움직임 + 거래량이 함께 터진" 종목으로 재선별 (Stocks-in-Play D-1 프록시).
- 기존 변동성 universe와 A/B 비교 가능하게 (`dynamic` 보존).
- universe 임계값 튜닝 가능 (CLI).

### 비목표 (이번 iteration 제외)
- 갭(당일 시초가) 기반 선별 — D-1 한정 결정에 따라 제외. 2차 iteration 후보.
- 촉매(뉴스·공시) 데이터 — 미보유. RVOL 급증을 프록시로 사용.
- 합성 스코어/가중치 최적화 — A안(하드 게이트) 채택.

## 3. 선별 로직

거래일 X에 대해 `asof = D-1`(직전 거래일). 각 종목이 asof 시점 데이터로 아래 게이트를 **모두** 통과:

| 게이트 | 정의 | 기본값 | CLI |
|---|---|---|---|
| 이력 | asof 포함 이전 거래일 수 ≥ rvol_window + 1 | 21 | (rvol_window 종속) |
| RVOL | volume(asof) / mean(volume, asof 직전 rvol_window 거래일, asof 미포함) | ≥ 2.0 | `--sip-rvol-min` |
| 전일 등락 | \|close(asof) − close(asof−1)\| / close(asof−1) | ≥ 0.03 | `--sip-return-min` |
| 유동성 | amount(asof) | ≥ 1.0e10 (100억) | (함수 인자, CLI 미노출) |
| 주가 | close(asof) | ≥ 3,000 | (함수 인자, CLI 미노출) |

- 통과 종목이 top_n 초과 시 RVOL(asof) 내림차순 top_n. 기본 top_n=30 (`--sip-top-n`).
- 등락은 **절대값**(양방향). 진입 방향은 전략이 결정 (ORB·bull_flag 추세추종, reversal_*·red_to_green 역추세).
- RVOL 분모는 asof **직전** rvol_window 거래일(asof 미포함). 따라서 이력 요건 = rvol_window + 1 (분모 20일 + asof 1일; 등락에 필요한 asof−1은 분모 구간 내).

## 4. 데이터 & 구현

### 4.1 일별 집계
소스: `robotrader.minute_candles`. 분봉 → 일별 집계:
- `volume` = SUM(volume) per (stock_code, trade_date)
- `amount` = SUM(amount) per (stock_code, trade_date)
- `close` = 그 날 마지막 분봉 close = `(ARRAY_AGG(close ORDER BY datetime DESC))[1]`

전 기간 1회 벌크 집계 → DataFrame. 51M행 GROUP BY는 무거우므로 결과를 parquet 캐시(`cache/intraday_universe/_daily_agg.parquet`)에 저장하고, 있으면 재사용.

신규 함수: `load_daily_aggregates(cache_dir=None) -> pd.DataFrame`
- columns: `stock_code, trade_date, volume, amount, close`. (stock_code, trade_date) 정렬.
- cache_dir 지정 시 `_daily_agg.parquet` 우선 읽기, 없으면 DB 집계 후 저장.

### 4.2 universe 빌더
신규 함수: `build_stocks_in_play_universe(asof_date, daily_agg, *, rvol_min=2.0, abs_return_min=0.03, min_amount=1e10, min_price=3000.0, rvol_window=20, top_n=30) -> list[str]`
- `daily_agg`에서 `trade_date <= asof_date` 행만 사용 — 룩어헤드 구조적 불가.
- 각 종목: asof의 volume/amount/close, asof 직전 rvol_window일 평균 volume, asof−1의 close 추출. 이력 부족 종목 제외.
- 게이트 적용 → RVOL 내림차순 top_n → `stock_code` 리스트 반환.
- 순수 함수(daily_agg 주입) — DB 없이 단위테스트 가능.

기존 `build_universe_for_date`(변동성)는 **변경 없이 보존** (대조군).

### 4.3 토너먼트 통합
`scripts/run_intraday_tournament.py`:
- 신규 `_make_stocks_in_play_provider(cache_dir, rvol_min, abs_return_min, top_n)`. closure에서 (a) `load_daily_aggregates` 1회 lazy 로드, (b) 거래일 캘린더 1회 로드(`_load_trading_days` 재사용), (c) `_provider(trade_date)`: `_prior_trading_day`로 asof=D-1 산출 → `build_stocks_in_play_universe(asof, daily_agg, ...)`.
- `--universe`에 `sip` 추가. valid = {screener, dynamic, sip}. `run_tournament`이 `sip` 시 위 provider 생성.
- CLI 신규: `--sip-rvol-min`(기본 2.0), `--sip-return-min`(기본 0.03), `--sip-top-n`(기본 30).

## 5. 검증 계획

1. **스모크**: `--universe sip --strategies orb`, 약 30거래일(20260401~20260515), SL/TP 1~2개. universe 일별 크기·수치 정상성 확인.
2. **A/B**: 동일 전략·기간으로 `--universe sip` vs `dynamic` 비교 — sip이 손실 축소/신호 발생하는지.
3. 신호 확인 시 → 다전략 + SL/TP 그리드 확장 (별도 결재).
- 배포 기준선: 기존 합격선(일≥0.3% · 승≥50% · MDD≥−15%) 유지.
- 이번 iteration 1차 마일스톤: 비용 차감 후 ≥1 전략 +EV.

## 6. 테스트 (TDD — 실패 테스트 먼저)

`tests/test_intraday_universe.py` 추가:
- `build_stocks_in_play_universe` 순수함수 — 합성 daily_agg DataFrame으로: RVOL 게이트 / 등락 게이트 / amount·price 게이트 / top_n 랭킹 / 이력부족 종목 제외 / **asof 이후 데이터 미사용**(룩어헤드 차단) 검증.
- `load_daily_aggregates` 캐시 동작 (parquet 있으면 재사용).

## 7. 정직한 전제 / 리스크

- research의 Stocks-in-Play 핵심 3요소(RVOL+갭+촉매) 중 **RVOL+모멘텀만** 재현. 갭·촉매 부재 → 엣지의 일부만 본다. 잘 돼도 약하거나 무신호일 수 있음.
- 무신호 시 결론: "D-1 한정으론 부족 → 갭/촉매 필요" — 2차 iteration 근거. 이 또한 유효한 결과.
- 룩어헤드 재발 방지: universe 빌더가 구조적으로 `asof_date` 이하 데이터만 사용 + 단위테스트로 박제.

## 8. 영향 파일

- `utils/intraday_universe.py` — `load_daily_aggregates`, `build_stocks_in_play_universe` 추가 (기존 함수 보존)
- `scripts/run_intraday_tournament.py` — `_make_stocks_in_play_provider`, `--universe sip`, CLI 3종
- `tests/test_intraday_universe.py` — 신규 테스트
- `cache/intraday_universe/_daily_agg.parquet` — 신규 캐시 산출물 (cache/ 는 gitignore)

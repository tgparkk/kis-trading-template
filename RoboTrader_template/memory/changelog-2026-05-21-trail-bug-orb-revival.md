# 2026-05-21 trail_pct 버그 → "ORB 부활" → dynamic universe 룩어헤드 발견 (부활 무효)

> ## [정정 2026-05-21 심야] "ORB 부활" 결론 무효 — dynamic universe 룩어헤드
>
> 본문 §5의 **"plain ORB 부활(+0.45%/일·승51%·합격)"** 및 한줄 요약의 ORB 합격 결론은
> **dynamic universe 룩어헤드 편향으로 오염**되었습니다.
>
> `build_universe_for_date`가 거래일 당일의 종일 OHLCV로 universe를 선별 → 백테스트가
> "그날 크게 움직일 종목"을 미리 보고 거래한 셈. 수정(universe를 D-1로 빌드) 후 재검증
> 스모크: orb 전 설정 손실(평균 -0.67%/일, 승률 33%, 합격 0/4). **ORB는 엣지 없음.**
> 상세는 아래 §7.

## 한줄 요약

분봉 백테스트 엔진의 `trail_pct` 기본값 버그(0.5% 트레일링 스톱 강제)가 5/16~5/20의 분봉 토너먼트 4회를 전부 오염시켰음을 확증. 수정 후 같은 4~5월 구간을 trail ON/OFF로 A/B 재토너먼트한 결과 plain ORB가 부활 — 일수익률 +0.45%, 일승률 51.4%, Calmar 34.7, MDD -5.5%로 **합격선 통과**. 5/18·5/20의 "ORB 폐기" 결정은 무효 확정. 이어서 전체 168일 ORB SL/TP 그리드(72 시나리오)에 착수.

## 1. 버그

### 1.1 trail_pct 기본값 (핵심)
- `BacktestEngine.run_minute()` 시그니처가 `trail_pct: Optional[float] = 0.005` — 0.5% 트레일링 스톱이 기본값.
- `scripts/run_intraday_tournament.py`가 `trail_pct`를 단 한 번도 명시 전달하지 않음 → 모든 분봉 토너먼트가 0.5% 트레일을 강제로 뒤집어쓴 채 실행됨.
- 분봉당 변동폭 ~0.2% 종목에서 0.5% 트레일은 +4~6% TP를 사실상 도달 불가로 만들어 R:R(손익비)을 파괴.

### 1.2 equity_curve 초기자본 누락 (별도 메트릭 버그)
- `equity_curve: List[float] = []` — 초기자본이 curve[0]에 없어 1일차 수익률이 지표 계산에서 누락 (engine.py:1113 부근).

## 2. A/B 진단 — diag_trail_ab.py

trail OFF vs ON 직접 비교로 버그 확증:
- vwap_trade 8거래일: -21% → -1%
- orb: -17% → -5%
- TP 체결 횟수 약 5배 증가

## 3. 오염 범위

분봉 토너먼트 4회 전부 trail 버그를 공유 — "전략 실패" 판정이 전부 무효/보류:

| 일자 | 토너먼트 | 당시 결론 (무효) |
|---|---|---|
| 5/16 | 분봉 60시나리오 풀 토너먼트 | 합격 0 |
| 5/17 | ORB SL/TP 그리드 (30일) | ORB 우승자 발견 (trail-ON 값이라 신뢰 불가) |
| 5/18 | ORB OOS 168일 | 합격 0 → "ORB 폐기" 결정 |
| 5/20 | ORB v2 96시나리오 (32/96 중지) | "거래량+시장환경 필터 가설 기각" |

- 합격 0건이었던 공통 원인은 전략 실패가 아니라 trail 버그.
- **깨끗함**: 멀티버스 / param_optimizer (일봉 `engine.run()` 경로)는 이 버그와 무관. 일봉 자체 트레일 3% 고정상수는 별개(버그 아님).

## 4. 수정

- `backtest/engine.py`: `run_minute` `trail_pct` 기본값 `0.005` → `None`. `equity_curve` `[]` → `[initial_capital]`.
- `scripts/run_intraday_tournament.py`: `--trail` CLI 옵션 추가(none/off/숫자, 전역 단일값), `trail_pct` 결과 컬럼 기록.
- `tests/test_backtest_engine_minute.py`: equity_curve 길이 단언 1 → 2 갱신.
- `scripts/diag_trail_ab.py`: trail A/B 진단 스크립트 신규.

## 5. aprmay A/B 재토너먼트 — 확증

같은 4~5월 구간·같은 18전략을 trail ON/OFF로 1회씩 실행 (깨끗한 A/B):

| 전략 | trail ON (오염) | trail OFF (수정) |
|---|---|---|
| **orb** | -1.88%/일 · 승14% · MDD-50% | **+0.45%/일 · 승51% · MDD-5.5% · Calmar 34.7 ✅ 합격** |
| orb_v2_vr05_mkt | -1.35% | +0.08% |
| 나머지 16전략 | 전부 -1~-4% | 전부 음수 |

- trail ON run: `reports/tournament_aprmay_all/20260520_160815/` — 합격 0
- trail OFF run: `reports/tournament_aprmay_trailoff/20260520_225219/` — 합격 1 (orb)

### 발견
1. trail 버그가 ORB를 죽인 게 맞음. **"ORB 폐기"(5/18·5/20) 결정 무효 확정** — 정정 노트가 예고한 대로.
2. orb_v2 8종 전부 plain orb에 패배 (최선 vr05_mkt +0.08% ≪ orb +0.45%). 거래량+시장환경 필터 재설계 가설은 이 데이터에서 기각.
3. 단, aprmay는 5/18 scientist가 지목한 "2026-04 반등기 = ORB 우호 국면 표본편향" 그 창. 합격은 필요조건일 뿐 — 진위는 전체 168일 OOS로만 판정.

## 6. SL/TP 그리드 착수 (진행 중)

- **그리드**: orb + orb_v2_vr05_mkt × SL[1/2/3%] × TP[2/3/4/6%] × pos[3/4/5] = 72 시나리오
- **기간**: 전체 168일 (2025-09-01~2026-05-15, skip 202603), trail-OFF, dynamic universe top50
- **목적**: aprmay 합격이 국면운인지 진짜인지 판정 + trail-OFF 환경의 최적 SL/TP 재발견
- workers=16. 1차 실행이 DB 커넥션 풀(`max_conn=10`) 초과로 중지 → `run_tournament()`에 풀 사전초기화(`max_conn=max(24, workers+8)`) 추가 후 재실행.
- 결과 위치: `reports/tournament_orb_sltp_grid/20260521_085340/` — 결과는 후속 changelog에 박제 예정.

## 7. dynamic universe 룩어헤드 발견 + 수정 (이 문서의 핵심 정정)

### 7.1 발견 경위
SL/TP 그리드 토너먼트(§6) 64/72 진행 시점에 결과가 물리적으로 불가능 — orb pos3/SL2/TP6 = +13,641% 누적·승률 84.7%. 스모킹건: **TP가 높을수록 승률이 높음**(TP2 59~64% vs TP6 80~91%) — 정상이면 역(逆)이어야 함.

### 7.2 근본 원인 (코드 + 실측 확정)
- `run_minute()`이 `candidate_provider(trade_date)`를 거래 당일 날짜로 호출 (engine.py:1138·1202).
- `build_universe_for_date(X)`가 `minute_candles WHERE trade_date=X`의 그날 종일 `MAX(high)/MIN(low)/SUM(amount)`로 변동성 상위 50 선별.
- ∴ X일 09:00 트레이딩 시작 시점에 universe는 이미 "X일 종일 최고 변동성 50종목" — 명백한 룩어헤드.
- 실측(2026-04-09): universe(X) 50종목의 당일 실현 변동성 평균 16.44%(최소조차 10.64%) vs 시장 6.46%. 연속일 멤버십 공통 12~22/50 (Jaccard 0.14~0.28).

### 7.3 왜 과거 결과가 전부 오염됐나
3겹의 버그가 룩어헤드를 가리고 있었음: ① 5/16 과잉거래(비용 609%) ② 5/17~20 trail 버그 ③ 둘 다 수정 → 룩어헤드 민낯 노출. **5/16 이후 dynamic-universe 토너먼트 전부 무효** — 본문 §5 "ORB 부활" 포함.

### 7.4 수정
`scripts/run_intraday_tournament.py` `_make_dynamic_provider`: universe(X)를 직전 거래일 P(D-1) 데이터로 빌드. 순수 헬퍼 `_prior_trading_day`/`_load_trading_days` 추가. TDD red→green, 단위테스트 51 passed. 캐시(`{date}.parquet`)는 per-date 랭킹이라 그대로 유효 — 재구축 불필요. `kospi_market_up` 감사 결과 이미 정상(D-1 사용).

### 7.5 수정 후 재검증 스모크 (orb, 2026-04-01~05-15, D-1 universe)
| SL/TP | 일수익률 | 승률 | MDD | 누적 PnL |
|---|---|---|---|---|
| SL3/TP6 | -0.42% | 39.4% | -17.1% | -13.6% |
| SL2/TP6 | -0.65% | 33.3% | -24.6% | -20.0% |
| SL3/TP2 | -0.65% | 30.3% | -20.9% | -19.9% |
| SL2/TP2 | -0.96% | 27.3% | -28.6% | -27.5% |

before/after (orb pos3 SL2 TP6): **+13,641%·승84.7% → -20.0%·승33.3%**.

### 7.6 정직한 결론
- 룩어헤드 수정은 작동 확정 (4자리 % 소멸, 승률 현실화, TP-승률 역상관 해소).
- **plain ORB는 엣지가 없다** — 평균 -0.67%/일, 승률 33%, 합격 0/4. "ORB 부활"은 100% 룩어헤드였음.
- research-2026-05-20 예측과 정확히 일치: "단독 ORB는 죽었고 Stocks-in-Play(RVOL+갭+촉매) 필터와만 부활." 현 dynamic universe는 "변동성 상위 50"일 뿐 촉매/RVOL 필터 부재.
- **다음 단계**: universe를 Stocks-in-Play 방식으로 재설계 후 분봉 전략 재검증.

## 관련 문서
- [changelog-2026-05-20-orb-v2-tournament-aborted.md](changelog-2026-05-20-orb-v2-tournament-aborted.md) — 정정 노트 추가됨
- [changelog-2026-05-18-orb-oos-failure.md](changelog-2026-05-18-orb-oos-failure.md)
- [research-2026-05-20-daytrading-deep-dive.md](research-2026-05-20-daytrading-deep-dive.md)

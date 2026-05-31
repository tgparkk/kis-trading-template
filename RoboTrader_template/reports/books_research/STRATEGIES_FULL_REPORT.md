# 15개 책 전략 종합 보고서 — 매수후보 · 매수시점 · 매도시점

> 작성: 2026-05-31 · 출처: 각 책 `strategies/books/<book>/rules*.py` 코드 + run 스크립트(청산 파라미터) + `reports/books_research/<book>/report.md`(백테스트 결과). 추정 없이 코드 원문 기준.

## 이 보고서를 읽는 법
세 가지를 책·룰별로 정리한다:
- **매수후보(universe)**: 어떤 종목 풀에서 고르는가
- **매수시점**: 어떤 조건이 충족되면 진입하는가
- **매도시점**: 어떤 조건/우선순위로 청산하는가

매수후보는 **세 유형**으로 갈린다:
1. **거래대금 상위(top_volume:N)** — 기술적 전략 전부(아지즈~트레이딩의전설). 매일 거래가 활발한 N종목을 1차 후보로 받아 각 룰 조건 통과분만 진입.
2. **횡단면 팩터 순위 상위 N** — 펀더멘털 5책(린치·그린블라트·오쇼너시·문병로·홍용찬). PBR/PSR 등으로 전종목 순위 매겨 상위 N 매수.
3. **위험자산+현금 동적비중** — systrader79(자산배분). 개별주 아님.

## 15책 한눈에 보기

| # | 책 (저자) | 성격 | 매수후보 유형 | 대표 룰 | 백테스트 결론 |
|---|---|---|---|---|---|
| 1 | 아지즈 (Aziz) | 분봉 데이트레이딩 | 거래대금상위(분봉) | abcd·bull_flag | **분봉 전멸**(±0%) |
| 2 | 벨라피오레 (PlayBook) | 분봉 플레이북 | 거래대금상위(분봉) | fade_vwap | 부분양(+1.74%) but 전멸군 |
| 3 | 라쉬케 (Street Smarts) | 분봉 스윙 | 거래대금상위(분봉) | anti | 변동성 극단(Sharpe −2.27) |
| 4 | 오닐 (CANSLIM) | 일봉 돌파 | 거래대금상위 | (영속 코드 없음) | 비교표만 +7.04%/7거래 |
| 5 | 미너비니 (VCP) | 일봉 변동성수축 | 거래대금상위 | volume_dryup | **Sharpe 1.41 생존**(BULL편향) |
| 6 | 와인스타인 (Stage) | 단계분석 | 거래대금상위 | ma30w_bounce | Sharpe 0.30(BULL편향) |
| 7 | 엘더 (삼중창) | 일봉 추세눌림 | 거래대금상위 | **ema_pullback** | **Sharpe 1.22·약세장 방어 ✓ 유일 CANDIDATE** |
| 8 | 린치 (One Up) | 펀더멘털 가치 | 팩터순위 | value_balance_sheet | 데이터제약 inconclusive |
| 9 | 그린블라트 (마법공식) | 펀더멘털 | 팩터순위 | magic_formula | 6개월 단일국면 |
| 10 | 오쇼너시 (What Works) | 펀더멘털 | 팩터순위 | low_psr | 6개월 단일국면 |
| 11 | 문병로 (메트릭) | 5팩터 복합 | 팩터순위 | value_composite_kr | **Sharpe 0.09 부적격** |
| 12 | 홍용찬 (실전퀀트) | 4선 저밸류 | 팩터순위 | value4_low | **Sharpe 0.11 부적격** |
| 13 | systrader79 | 자산배분 | 위험+현금 비중 | 평균모멘텀스코어 | **MDD 19% 방어 ✓**(절대수익 패) |
| 14 | 강창권 (단기트레이딩) | 분봉+일봉 | 거래대금상위 | ma20_pullback/ma5_10 | 분봉 전멸 / 일봉 Sharpe 0.44 |
| 15 | 트레이딩의전설 | 분봉8인+일봉 | 거래대금상위 | ma5_pullback | 부적격(눌림목 재확인) |

## 큰 그림 — 4개 군으로 갈린다
- **🟢 생존군(추세추종 일봉)**: 엘더 ema_pullback(약세장까지 방어, 유일 실전 CANDIDATE)·미너비니 volume_dryup(Sharpe 1.41 but BULL편향). → **페이퍼 채택 = Elder/Minervini/강창권 ma20/Book15 ma5** ([SELECTED_STRATEGIES.md](../SELECTED_STRATEGIES.md))
- **🔴 전멸군(분봉 단타)**: 아지즈·벨라피오레·라쉬케·강창권 분봉·트레이딩의전설 분봉8인 — 거래수와 손실이 정비례, 한국 분봉 단타 백테스트 5책 전멸.
- **🟡 부적격군(펀더멘털 퀀트)**: 린치·그린블라트·오쇼너시·문병로·홍용찬 — 다년 검증 시 Sharpe 0.05~0.12 붕괴. "단순 단일 가치팩터 > 복잡 게이트" 일관 확인.
- **🔵 자산배분(systrader79)**: 성격이 달라 별도 트랙 — MDD 방어형(폭등장 노출 제한으로 절대수익은 패).

## ⚠️ 백테스트 수치 해석 주의
- **2026 봄(1~5월)은 대폭등장**이라 최근 수치는 부풀려짐. 5년 전체 per-trade는 훨씬 낮음(엘더 +0.38%·미너비니 +0.18%·강창권 ma20 +0.06%·Book15 ma5 +0.34%).
- **손익비(평균이익/평균손실)는 비교적 구조적**(생존 4전략 약 2.1~2.8), 절대 기대값은 국면 의존이 큼.
- 펀더멘털 5책은 **코드에 매도 룰 자체가 없음** — 청산은 백테스터 variant 파라미터(보유기간 만료·손절·순위이탈 리밸런싱)로만 발생.

---
*(이하 섹션: ① 기술적 일봉군 ② 분봉 단타군 ③ 펀더멘털·퀀트·자산배분군 — 각 책의 룰별 상세)*

---

# ① 기술적 일봉군 (오닐·미너비니·와인스타인·엘더·강창권 일봉·트레이딩의전설 일봉)

# 기술적 일봉 전략군 — 매수후보·매수시점·매도시점 (코드 추출)

> 출처: 각 책 `strategies/books/<book>/rules*.py`(진입 룰) + `scripts/run_<book>*.py`(유니버스·variant 청산) + `reports/books_research/<book>/report.md`(백테스트).
> 공통 유니버스: 모든 일봉책이 `daily_prices`(adj_factor 적용 수정주가) 의 기간 내 `SUM(close*volume)` 거래대금 **상위 50종목**(`top_volume:50`, 함수 `_load_top_volume_universe`). 단 trading_legends 백테스트는 report 기준 top_volume:100(99종목).
> 공통 체결: 신호 t → **다음 봉 시가** 매수, 슬리피지 0.10% 단방향, 왕복비용 ≈0.41%(수수료 0.015%×2 + 거래세 0.18% + 슬리피지 0.10%×2). 자본 99% 단일종목 투입.
> 공통 청산 우선순위(run 스크립트 simulate_one_stock): **stop_loss → take_profit → max_hold → trail(ma/ema) → (Elder만 trend_flip) → 종료시 forced_close**. 모두 종가로 트리거 판정 후 다음 봉 시가 체결.

> ⚠️ **오닐 CANSLIM 부재**: 의뢰 목록의 `strategies/books/oneil_canslim/rules.py` 는 **코드베이스에 존재하지 않음**. O'Neil(Book 6)은 초기 조사 책으로, 비교표에만 수치가 남아 있고(일봉+재무+RS, 베스트 "CANSLIM+패턴" +7.04% / 7거래 / Sharpe 미산출 — 표본 7건으로 통계 무의미) 영속화된 rules.py 가 없다. 따라서 아래는 실제 코드가 존재하는 **5책**을 다룬다.

---

## (미너비니 VCP, Mark Minervini) — SEPA 추세 템플릿 + 변동성 수축 베이스 돌파
**매수후보**: top_volume:50. RS는 universe 내부 12주(60거래일) 수익률 백분위(`compute_rs_percentile_12w`, 0~99). `rules.py`.
**청산 variant**(VARIANT_PARAMS): A = sl 8% / tp 20% / mh 35 / trail 50일MA · B = sl 8% / tp 12% / mh 20 / trail 없음.
**백테스트 기간**: 2025-07-01~2026-05-29(224거래일, BULL 71.6% 편향).

### 룰: trend_template (SEPA Trend Template 8조건)
- 매수시점: len≥220 필요. 8조건 전부 AND — (1) close > MA150 AND close > MA200, (2) MA150 > MA200, (3) MA200 > 20일전 MA200(상승), (4) MA50 > MA150 > MA200(완전 정배열), (5) close > MA50, (6) 52주 고점 대비 낙폭 ≤ 25%, (7) 52주 저점 대비 상승 ≥ 30%, (8) RS백분위 ≥ 70. confidence 72.
- 매도시점: variant A(sl8/tp20/mh35/50MA) 또는 B(sl8/tp12/mh20).
- 백테스트: **0거래**(220봉 guard로 224일 데이터에서 사실상 항상 False — 미검증).

### 룰: vcp_breakout (VCP 베이스 + 피벗 돌파)
- 매수시점: len ≥ 46(base 25 + 21). 베이스=직전 25봉(마지막 제외), pre_base=그 앞 20봉. 4조건 AND — (1) 피벗 돌파: close > base 25봉 최고가, (2) RVOL: 당봉거래량/base평균거래량 ≥ 1.5, (3) 거래량 dry-up: base평균/pre_base평균 ≤ 0.7, (4) 진폭 수축: base 후반 평균(high-low)/전반 평균 ≤ 0.6. confidence 75.
- 매도시점: variant A 또는 B.
- 백테스트: A·B 공통 **2거래** / +0.33% / Sharpe 0.07(표본 무의미).

### 룰: tight_closes (3주 종가 타이트)
- 매수시점: len ≥ 15. 최근 15봉 종가의 (max−min)/mean ≤ 0.015(1.5%). confidence 60.
- 매도시점: variant A 또는 B.
- 백테스트: **2거래** / +0.26% / Sharpe −0.02(무의미).

### 룰: volume_dryup (거래량 dry-up) ⭐ 베스트
- 매수시점: len ≥ 40. 최근 10봉 평균거래량 / 직전 30봉 평균거래량 ≤ 0.70. confidence 58.
- 매도시점: variant A(sl8/tp20/mh35/50MA) 또는 B(sl8/tp12/mh20).
- 백테스트: **B: 444→153거래 / +20.27% / Sharpe 1.41 / Calmar 2.38 / hit 62.0% / 보유 9.0일**(A: +18.17% / Sharpe 1.12 / hit 54.2% / 4.7일). 5권 중 일봉 단독 최고 Sharpe·Calmar. CANDIDATE 자격 통과(단 BULL 편향 경고).
- 국면별(B 매도일): BULL +9.95%(92T) / SIDEWAYS +8.77%(22T) / BEAR −2.29%(39T).

---

## (와인스타인 Stage Analysis, Stan Weinstein) — 주봉 Stage 2 추세 추종
**매수후보**: top_volume:50('KOSPI' 제외). 일봉→**주봉 변환**(resample) 후 평가. RS는 Mansfield RS(universe 동일가중 인덱스 대비, n=26주). MA30W·slope·stage를 ctx로 주입. `rules.py`.
**청산 variant**(VARIANT_PARAMS): A = sl8/tp30/mh20주/trail MA30W(warmup 56주 → 32주 데이터선 표본 0) · B = sl8/tp12/mh20일/trail 없음(일봉) · Light = sl8/tp20/mh10주/trail MA10W(인프라 검증용, 책 평가 아님).
**백테스트 기간**: 2025-07-01~2026-05-29(약 32주). 실질 결과는 **Variant B**만 유효.

### 룰: stage2_initial_breakout (Stage 1→2 전환 돌파)
- 매수시점: min_bars=box16+volavg4+2. 5조건 AND — (1) 직전 주 stage==1 AND 현재 stage==2, (2) close > MA30W, (3) close > 직전 16주 박스 고가(no-lookahead iloc[-17:-1] max), (4) 당주 거래량 > 직전 4주 평균거래량 × 1.5, (5) Mansfield RS ≥ 0. confidence 72.
- 매도시점: B(sl8/tp12/mh20).
- 백테스트: **7거래 / +0.38% / hit 57.1% / Sharpe 0.03 / 1.0일**(표본 극소).

### 룰: stage2_continuation_pullback (Stage 2 MA30 되돌림 재진입)
- 매수시점: 5조건 AND — (1) 현재+직전 4주 모두 stage==2, (2) 지난 5봉 중 한 번이라도 (close−MA30W)/MA30W < 0.05(MA30W 5% 이내 접근), (3) close > 직전 4주 swing high(high iloc[-5:-1] max), (4) 당주 거래량 > 직전 4주 평균 × 1.0, (5) Mansfield RS ≥ 0. confidence 68.
- 매도시점: B(sl8/tp12/mh20).
- 백테스트: **17거래 / +1.29% / hit 41.2% / Sharpe −0.11 / 1.9일**.

### 룰: ma30w_bounce (Stage 2 MA30 단순 반등) ⭐ 베스트
- 매수시점: len ≥ 32. 3조건 AND — (1) 현재 stage==2, (2) 당봉 저가 ≤ MA30W × 1.03(MA30W 3% 이내 터치) AND 양봉(close > open), (3) Mansfield RS ≥ 0. swing-high 조건 없는 완화판. confidence 60.
- 매도시점: B(sl8/tp12/mh20).
- 백테스트: **43거래 / +4.18% / hit 60.5% / Sharpe 0.30 / Calmar 1.92 / 4.3일**. 청산내역: tp 51.2%/sl 41.9%. 최대손실거래 −73.46%(갭다운 의심). 표본 43(<100), BULL 편향, CANDIDATE 미달.

---

## (엘더 삼중창, Alexander Elder) — Triple Screen(추세 방향 눌림 매수, 일봉 proxy)
**매수후보**: top_volume:50. Screen 1(주봉 추세)을 **일봉 65일 EMA 기울기>0** proxy로 종목 자기완결(지수/RS 불필요). Screen 3 진입=**전일 고가+1틱 매수스톱**(KRX 호가단위, 최대 N_TRAIL=2일 추적; 미체결 시 trigger를 최근봉 고가로 갱신, 추세 반전 시 취소). `rules.py`.
**청산 variant**(VARIANT_PARAMS): A = sl8/tp30/mh100/trail EMA13(수익 중일 때만)+ema65 추세반전(trend_flip) · B = sl8/tp12/mh20/trail 없음.
**백테스트 기간**: daily_prices 전체(2021-01~2026-05, 종목별 평균 ~142봉). 모든 룰은 len≥70 필요, screen1_uptrend(ema65[-1]>ema65[-6]) 선행 필터.

### 룰: triple_screen_force_index (정통 Triple Screen)
- 매수시점: screen1_uptrend AND (1) 일봉 MACD-Hist(12,26,9) 상승: hist[-1] > hist[-2], (2) Force Index 2일 EMA < 0. confidence 72.
- 매도시점: A(sl8/tp30/mh100/EMA13 trail+ema65 flip) 또는 B(sl8/tp12/mh20).
- 백테스트: A 48거래 / +6.05% / Sharpe 0.54 / hit 35.3% (B 45T / +4.89% / 0.52).

### 룰: triple_screen_stochastic (EMA65 상승 + 스토캐스틱 과매도 상향전환)
- 매수시점: screen1_uptrend AND Stochastic(14,3,3) %K < 30 AND %K[-1] > %D[-1]. confidence 68.
- 매도시점: A 또는 B.
- 백테스트: A 43거래 / +9.32% / Sharpe 0.91 / **Calmar 6.95(전 룰 최고)** / MaxDD 5.21% / hit 41.7% (B 41T / +8.40% / 0.99). 표본 적으나 위험대비 최우수.

### 룰: triple_screen_elder_ray (Impulse 비적색 + Bear Power 상승 + EMA13 상승)
- 매수시점: screen1_uptrend AND (1) Impulse 색상 ≠ red, (2) Bear Power(low−EMA13) < 0 AND Bear Power[-1] > Bear Power[-2](상승), (3) EMA13[-1] > EMA13[-2]. confidence 66.
- 매도시점: A 또는 B.
- 백테스트: A 73거래 / +8.66% / Sharpe 0.25 / hit 34.5% (B 76T / +3.44% / 0.19). 거래 많으나 hit 낮아 부진.

### 룰: triple_screen_ema_pullback (단순 EMA13 눌림 반등) ⭐ 베스트
- 매수시점: screen1_uptrend AND (1) 당봉 저가 ≤ EMA13 × 1.01(touch_band), (2) close > EMA13(회복). confidence 60.
- 매도시점: A(sl8/tp30/mh100/EMA13 trail+ema65 flip) 또는 B(sl8/tp12/mh20).
- 백테스트: **A: 134거래 / +23.76% / Sharpe 1.22 / Calmar 2.64 / MaxDD 13.76% / hit 56.4% / 8.6일**(B 149T / +17.72% / 1.20 / hit 57.5%). **7권 통틀어 일봉 최고 PnL**(Minervini +20.27% 상회). 5년 보정 후 Sharpe 0.68로 CANDIDATE 등록 확정(ema_pullback variant A 고정).

### 모드: all_AND (4룰 동시) — 0거래 (Force Index<0 vs EMA 회복 vs %K<30 상호 배타적).

---

## (강창권 일봉, 『주식투자 단기 트레이딩의 정석』) — A등급 일봉 7종(이평 지지·돌파·눌림)
**매수후보**: top_volume:50. 종목별 daily_prices(2021~2026) df.iloc[:i+1] 윈도우 전달. `rules_daily.py`.
**청산 variant**(VARIANT_PARAMS): A = sl8 / tp off(99%) / mh100 / trail 룰별 기본(RULE_TRAIL_MA) · B = sl8 / tp12 / mh20 / trail 없음. **A-07(daily_ma20_pullback)만 책 명시 +10% 익절 강제 override(tp=0.10)**(RULE_TP_OVERRIDE). RULE_TRAIL_MA: ma20_pull=20, ma5_10=10, ma60_doji=60, trend_240_480=240, swing=20, new_high=20, vol300=240(all_AND/미지정=DEFAULT 20).
**공통 헬퍼**: 급등이력 `_recent_surge`(직전 lookback봉 저점대비 고점 +surge_pct↑), 양봉 close>open, MA터치 |low−ma|/ma ≤ tol.

### 룰: daily_ma20_pullback (A-07, 20일선 눌림목) ⭐ Sharpe 최고
- 매수시점: 4조건 AND — (1) 직전 30일 내 +25% 급등, (2) close ≥ MA20×0.98(지지 유효), (3) 저가가 MA20 ±2% 터치, (4) 양봉. confidence 72.
- 매도시점: **tp +10% 강제** + sl8 + (A: mh100/trail 20MA · B: mh20/trail 없음).
- 백테스트: **B(tp10): 695거래 / +16.00% / Sharpe 0.44 / hit 51.8%**(위험조정 최고). A: 913T / +5.75% / 0.23.

### 룰: daily_ma5_10_follow (A-08, 5·10일선 따라가기) ⭐ 최고 PnL
- 매수시점: 5조건 AND — (1) 급등 이력(30일 +25%), (2) MA5 ≥ MA10(정배열), (3) 저가가 MA5 또는 MA10 ±2% 터치, (4) close ≥ MA10×0.98, (5) 양봉. confidence 68.
- 매도시점: sl8 + (A: mh100/trail 10MA · B: mh20/tp12).
- 백테스트: **B: 1,000거래 / +46.15% / Sharpe 0.34 / hit 48.5%**(책 최고 PnL). A: 1,073T / +13.06% / 0.24.

### 룰: daily_ma60_doji_rebound (A-12, 60일선 도지 반등)
- 매수시점: 6조건 AND — (1) 직전봉 기준 MA5<MA10<MA20 역배열(순차 이탈), (2) 저가/종가가 MA60 ±3% 부근, (3) 직전봉 도지(|c−o| ≤ range×0.1, range>0), (4) 거래량 감소(최근 5봉 평균 ≤ 직전 5봉 평균 × 0.8), (5) 양봉, (6) close ≥ MA60×0.98. confidence 66.
- 매도시점: sl8 + (A: mh100/trail 60MA · B: mh20/tp12).
- 백테스트: B 46거래 / −0.93% / Sharpe −0.07 / hit 19.5%(표본 부족·부진). A 46T / +1.79%.

### 룰: daily_trend_filter_240_480 (A-14, 240·480일선 추세 필터/진입)
- 매수시점: 4조건 AND — (1) close ≥ MA480, (2) close ≥ MA240, (3) 저가가 MA240 또는 MA480 ±3% 터치(장기선 지지반등), (4) 양봉. len ≥ 482. confidence 64.
- 매도시점: sl8 + (A: mh100/trail 240MA · B: mh20/tp12).
- 백테스트: B 288거래 / +8.64% / Sharpe 0.11 / hit 33.1%. A 278T / +22.40% / 0.16 / hit 19.1%.

### 룰: daily_swing_pullback (A-02, 직장인 스윙)
- 매수시점: 6조건 AND — (1) 급등 이력(30일 +25%), (2) 기간조정: 직전 30봉 고점이 최소 3봉 전(days_since_high ≥ 3), (3) 거래량 감소(최근 5봉 ≤ 직전 5봉 × 0.85), (4) 저가가 MA20 또는 MA60 ±2.5% 터치, (5) 양봉, (6) close ≥ 지지이평×0.98. confidence 70.
- 매도시점: sl8 + (A: mh100/trail 20MA · B: mh20/tp12).
- 백테스트: B 482거래 / +11.55% / Sharpe 0.35 / hit 48.5%. A 628T / +6.81% / 0.13.

### 룰: daily_new_high_breakout (A-03, 신고가 돌파)
- 매수시점: 3조건 AND — (1) 신고가 돌파: prev_close ≤ prior_high < close(hist_window=None→역사적 전체 고가, 마지막봉 제외), (2) close ≥ MA20, (3) 양봉. confidence 70.
- 매도시점: sl8 + (A: mh100/trail 20MA · B: mh20/tp12).
- 백테스트: B 285거래 / +19.99% / Sharpe 0.32 / hit 38.1%. **A 177T / +22.29% / 0.33 / hit 44.1%**(A/B 모두 +20%대).

### 룰: daily_vol300_longma_break (A-06, 거래량 +300% + 장기이평 돌파)
- 매수시점: 3조건 AND — (1) 당봉 거래량 ≥ 직전 20일 평균 × 3.0(+300%), (2) MA240 또는 MA480 종가 돌파(prev_close ≤ ma < close), (3) 양봉. confidence 67.
- 매도시점: sl8 + (A: mh100/trail 240MA · B: mh20/tp12).
- 백테스트: B 115거래 / +1.29% / Sharpe 0.01 / hit 25.1%(부진). A 110T / +7.53%.

### 모드: all_AND — 0거래(진입 이평/조건 혼재로 동시 충족 불가).
> 책 종합: 일봉 6/7 양(+) PnL. Sharpe 베스트 0.44(ma20_pullback B)는 Elder(0.68)·Minervini(0.64) 미달, 펀더멘털(~0.1) 상회 — **중간, CANDIDATE 부적격**.

---

## (트레이딩의 전설, 키움영웅전 9인) — 일봉 환원 6종(종가매매·상따·돌파·눌림·바닥)
**매수후보**: top_volume:50(함수) / 백테스트 report는 **top_volume:100(99종목)**. daily_prices 2021~2026. `rules_daily.py`. 헬퍼: 등락률 `_change_pct`(close/prev_close−1).
**청산 variant**(VARIANT_PARAMS): A = sl8 / tp off(99%) / mh100 / trail 룰별 · B = sl8 / tp12 / mh20 / trail 없음 · **O(오버나이트) = sl5 / tp off / mh1(익일 청산) / trail 없음**. **limit_up_follow만 책 명시 -3% 손절 강제 override(sl=0.03)**(RULE_SL_OVERRIDE). RULE_TRAIL_MA: close_momentum=5, new_high=20, prev_limitup=10, ma5_pull=5, bottom=20, limit_up=5.

### 룰: close_momentum_breakout (종가매매, 신정재+청사진) — 오버나이트
- 매수시점: 3조건 AND — (1) 당일 등락률 ≥ +5%, (2) close ≥ 직전 20일 신고가(high iloc[-21:-1] max), (3) 양봉. confidence 70. variant O(mh1) 권장.
- 매도시점: O(sl5/tp off/mh1=익일 시가 청산) 또는 A(trail 5MA)/B.
- 백테스트: **O: 1,456거래 / −3.95% / Sharpe −0.15 / hit 40.6% / MaxDD 25.0%**(책 시그니처지만 실패). A: 1,154T / −0.37% / 0.11.

### 룰: limit_up_follow (상따, 뭐라도되겠지) — 저DD 니치
- 매수시점: 3조건 AND — (1) 당일 등락률 ≥ +25%(상한가권), (2) 양봉, (3) close > open(명시적 재확인). confidence 72.
- 매도시점: **sl -3% 강제** + (O: tp off/mh1 · A/B 가능). trail 5MA.
- 백테스트: **O: 139거래 / +3.44% / Sharpe 0.05 / Calmar 1.25 / MaxDD 7.46%(전 룰 최저) / hit 21.1%**. 저DD 흥미롭지만 표본·승률 부족.

### 룰: new_high_breakout (전고점 돌파, 불개미+캐리)
- 매수시점: 2조건 AND — (1) close ≥ 직전 60일 신고가(high iloc[-61:-1] max), (2) 당봉 거래량 ≥ 직전 20일 평균 × 2.0. confidence 70.
- 매도시점: A(sl8/tp off/mh100/trail 20MA) 또는 B(sl8/tp12/mh20).
- 백테스트: **A: 607거래 / +3.56% / Sharpe 0.06 / hit 31.0% / MaxDD 26.0%**. 국면별 entry BEAR +1.21(97T)로 약세장 양수.

### 룰: prev_limitup_pullback (전날 상한가 익일 눌림, 캐리)
- 매수시점: 3조건 AND — (1) 전일 등락률 ≥ +25%(전날 상한가권), (2) 당일 저가 ≤ 전일 종가(눌림), (3) 양봉 AND close > 전일 종가(반등 마감). confidence 68.
- 매도시점: A(trail 10MA) 또는 B/O.
- 백테스트: A 37거래 / +1.24% / Sharpe −0.06 / hit 9.5% / MaxDD 3.8%(표본 극소).

### 룰: ma5_pullback (눌림목, 방배동선수+신정재) ⭐ 베스트
- 매수시점: 4조건 AND — (1) 최근 20일 내 +20% 급등, (2) 당일 저가가 MA5 ±2% 터치, (3) close ≥ MA5×0.98, (4) 양봉. confidence 68.
- 매도시점: B(sl8/tp12/mh20) 또는 A(trail 5MA).
- 백테스트: **B: 2,520거래 / +33.66% / Sharpe 0.63 / Calmar 1.57 / hit 49.1% / MaxDD 37.3%**(책 최강). 단 Book14 눌림목 패턴 재확인일 뿐 신규 알파 아님. A: 3,844T / +0.25% / 0.12.

### 룰: bottom_first_bull (바닥권 첫 양봉, 불개미)
- 매수시점: 3조건 AND — (1) 직전봉 종가 ≤ 직전 60일 저점 × 1.05(바닥권), (2) 당일 첫 양봉, (3) 당봉 거래량 ≥ 직전 20일 평균 × 1.5. confidence 66.
- 매도시점: A(sl8/tp off/mh100/trail 20MA) 또는 B/O.
- 백테스트: A 791거래 / −0.20% / Sharpe −0.03 / hit 24.9% / MaxDD 13.5%. 국면별 entry BEAR +0.81(328T) 양수.

> 책 종합: 시그니처 종가매매(close_momentum O) **백테스트 실패**(−3.95%). 유일 강세 ma5_pullback B(+33.66%/0.63)는 Book14 눌림목 재확인. **CANDIDATE 부적격**.

---

### 부록: 5책 베스트 룰 한눈에
| 책 | 베스트 룰 | variant | 거래 | PnL% | Sharpe | hit% |
|---|---|---|---|---|---|---|
| 미너비니 | volume_dryup | B | 153 | +20.27 | 1.41 | 62.0 |
| 와인스타인 | ma30w_bounce | B | 43 | +4.18 | 0.30 | 60.5 |
| 엘더 | triple_screen_ema_pullback | A | 134 | +23.76 | 1.22 | 56.4 |
| 강창권 | daily_ma5_10_follow / daily_ma20_pullback | B | 1,000 / 695 | +46.15 / +16.00 | 0.34 / **0.44** | 48.5 / 51.8 |
| 트레이딩의 전설 | ma5_pullback | B | 2,520 | +33.66 | 0.63 | 49.1 |

*(오닐 CANSLIM은 rules.py 부재 — 비교표 잔존 수치만: +7.04% / 7거래.)*

---

# ② 분봉 단타군 (아지즈·벨라피오레·라쉬케·강창권 분봉·트레이딩의전설 분봉8인)

# 섹션: 분봉 단타 전략군 — 매수후보·매수시점·매도시점

> 코드/문서 직접 추출(추정 없음). 출처 파일은 각 항목에 명시.
> 대상 4책(아지즈·벨라피오레·라쉬케·강창권 분봉) + 카탈로그 1건(트레이딩의 전설 분봉군).
> **핵심 결론**: 분봉 단타는 4책 전부 백테스트 전멸(대부분 음수/0). 유일 예외는 변동성 극단인 raschke `anti`(절대 PnL은 크나 평균 Sharpe −2.27)와 bellafiore `fade_vwap`(유일한 양 평균 Sharpe +0.37).

---

## 0. 공통 인프라 (모든 분봉 책 공유)

### 매수후보 (universe)
출처: `scripts/run_books_research.py`, `scripts/run_haru_silijeon_minute.py`
- **데이터 소스**: `robotrader.minute_candles` 테이블 (1,347종목 · 318일 · 5,116만행). 컬럼 `datetime, open, high, low, close, volume`.
- **시간프레임**: **1분봉** (장 09:00~15:30, ~390봉/일).
- **유니버스 선택 (2가지)**:
  - `all`: 해당 기간 minute_candles에 데이터가 있는 전 종목 (`_load_universe`, 503~581종목 규모).
  - `top_volume:N`: 기간 거래대금 `SUM(close*volume)` 상위 N종목 (`_load_top_volume_universe`). **분봉 책 표준 = `top_volume:50`** (강창권은 기본 `top_volume:50`, 아지즈/벨라/라쉬케 "책 의도 복원" 런도 top_volume:50).
- **기간 3종**: 2025-10, 2026-04, 2026-05 (`PERIODS` 상수). 모두 폭등장 구간.
- 강창권 CK480/240·480분선 룰은 멀티데이 480분 이평 warmup 위해 기간 시작 전 `LOOKBACK_DAYS=5`일 분봉 추가 로드.

### 매도시점 (청산 공통 엔진)
출처: `backtest/book_backtester.py` (`BookBacktester.run_single`)
- 신호 발생 봉 **다음 봉 시가**에 체결 (no-lookahead). 매수 슬리피지 +0.1%, 매도 −0.1%.
- 보유 중 매 봉 청산 조건 순차 체크 (종가 기준 수익률 `ret`):
  1. `ret <= -stop_loss_pct` → **손절** (기본 sl 0.02~0.03)
  2. `ret >= take_profit_pct` → **익절** (기본 tp 0.02~0.05)
  3. `hold_bars >= max_hold_bars` → **시간청산** (분봉 기본 mh 30~120봉)
  4. `eod_liquidate and i == n-2` → **EOD 강제청산** (분봉 마지막 봉 다음에서 청산; `eod_liquidate=True` 기본)
  - 루프 종료 후에도 포지션 남으면 마지막 봉 종가로 `forced_close`.
- 비용: 수수료 0.015%, 세금 0.18%, 왕복 ~0.21% + 슬리피지 0.1% 단방향.
- **개별 룰에는 매도 로직이 없음** — 모든 분봉 룰은 `side="buy"`(top_reversal만 sell) 진입 신호만 내고, 청산은 전적으로 BookBacktester의 sl/tp/mh/EOD가 담당.

---

## 1. 아지즈 — How to Day Trade for a Living
출처: `strategies/books/aziz_day_trade/rules.py`, 결과: `reports/books_research/index.md`

매수후보: 공통 인프라(minute_candles 1분봉). 베이스런 universe=all(503~581종목), 복원런 top_volume:50.
매도시점: 8룰 전부 BookBacktester 공통 청산(베이스 sl2%/tp3%/mh60, 복원 sl3%/tp5%/mh120) + EOD 강제청산. 개별 매도 로직 없음(top_reversal만 sell 신호).

### 룰별 매수시점 (evaluate 진입 조건 원문)
| 룰 | side | 매수시점 (진입 조건) |
|---|---|---|
| `abcd` | buy | 직전 15봉을 3등분 → A고가/B저가/C고가 산출. A>B and C>B(유효 패턴) + 마지막 종가 > C고가 **and** > A고가 (D 돌파). |
| `bull_flag` | buy | 직전 spike(폴 직전종가 대비 flag고가 +4%↑) + 깃발 3봉 range ≤2% + 마지막 종가 > 깃발 고가. |
| `vwap_reversal` | buy | 누적 VWAP 계산. 최근 20봉 중 VWAP×(1−0.5%) 아래로 dip 이력 **and** 마지막 종가 > 마지막 VWAP (회복). |
| `orb` (opening_range_breakout) | buy | 첫 5봉 고가(ORB high) 산출 → 마지막 종가 > ORB high. |
| `red_to_green` | buy | 첫 봉 시가 < 전일종가×0.998 (적자 출발) **and** 마지막 종가 ≥ 전일종가 (그린 전환). prev_close 없으면 첫 시가×1.01 근사. |
| `top_reversal` | **sell** | 마지막 봉 도지(몸통 ≤0.1%) **and** 거래량 < 직전봉×0.5 (거래량 급감). 유일한 매도 신호. |
| `support_resistance` | buy | 직전 60봉 최저가 대비 마지막 저가 ±0.3% 근접(지지 터치) **and** 마지막 봉 양봉. |
| `ma_trend` | buy | 누적 VWAP 위 + 마지막 봉 양봉 + 마지막 저가가 9EMA 또는 20EMA ±1% 터치(룩어헤드 방지 위해 EMA는 마지막 봉 제외 계산). |

### 백테스트 결과 (전멸)
- **베이스런(universe=all)**: 8룰 중 7룰이 −3.9~−29.6% 손실, top_reversal/all_AND는 0거래. 거래수와 손실이 정비례(abcd/orb/ma_trend는 4~4.8만 거래에 −15~−30%).
- **베스트 = `bull_flag`**: 3기간 평균 **−0.04%**, 거래수 평균 32회뿐(진입이 빡빡해 거의 안 일어남) = break-even.
- **복원런(top_volume:50 + sl3%/tp5%/mh120)**: 2025-10 한정 abcd **+9.49%**, orb +7.14%, red_to_green +6.56%가 양수로 전환되나 Sharpe는 전부 음수(−0.27~−1.36), MaxDD 18~20%. 2026-04/05는 여전히 손실. → "책이 사기는 아니나 일관 작동 미확정".

---

## 2. 벨라피오레 — One Good Trade / The PlayBook
출처: `strategies/books/bellafiore_playbook/rules.py`, 결과: `reports/books_research/index.md`

매수후보: 공통 인프라. 결과 비교런은 top_volume:50. (Tape Reading 의존 4셋업 — Opening Drive/Pullback/Trade2Hold/Intraday RS — 은 코드화 제외.)
매도시점: 6룰 전부 BookBacktester 공통 청산(sl3%/tp5%/mh120) + EOD. 개별 매도 로직 없음(전부 buy).

### 룰별 매수시점
| 룰 | 매수시점 (진입 조건) |
|---|---|
| `second_day_play` | 첫 30봉을 D-1 근사. 첫 30봉 (마지막종가−첫시가)/첫시가 ≥ +5% **and** 마지막 종가 > 첫 30봉 고가(돌파). |
| `bull_flag_bellafiore` | 폴 2봉 +1%↑ 상승 + 깃발 5봉 range ≤1.5% + 마지막 종가 > 깃발 고가. (아지즈보다 폴 짧고 박스 길다.) |
| `range_trade` | 직전 90봉 range 식별, range_pct ≥1%(충분히 넓음) + 마지막 저가가 range 하단 ±0.3% 근접 + 마지막 봉 양봉. |
| **`fade_vwap`** ⭐ | 누적 VWAP 하단 −2%↑ 이격 (`(vwap−close)/vwap ≥ 0.02`) **and** RSI(2) < 10 (과매도). long-only fade. |
| `opening_consolidation_breakout` | 첫 10봉 박스 range ≤1.5% + 박스 후반 거래량 < 전반(감소 추세) + 마지막 종가 > 박스 고가. |
| `catalyst_gap` | 첫 시가가 첫 30봉 평균종가 +3%↑(갭업 근사) + 누적 RVOL proxy ≥2배 + 마지막 종가 > 첫 시가. (조건 빡빡 → 0거래) |

### 백테스트 결과
- **베스트 = `fade_vwap`**: 3기간 평균 PnL **+1.74%**, 평균 Sharpe **+0.37** (책 통틀어 유일한 양 평균 Sharpe), 964거래. 2025-10 단독 **+11.71%, Sharpe 2.82, Calmar 3.22, Hit 60.3%** (539거래) — VWAP −2% + RSI(2)<10 평균회귀가 유의미한 알파.
- 나머지: opening_consolidation +1.65%(Sharpe −0.52), bull_flag_bellafiore −0.59%, second_day_play −1.62%, range_trade −1.73%, catalyst_gap/all_AND 0거래.

---

## 3. 린다 라쉬케 — Street Smarts
출처: 분봉 `strategies/books/raschke_street_smarts/rules.py` (Phase 1), 일봉 `rules_daily.py` (Phase 2), 결과: `reports/books_research/index.md`

매수후보: 분봉 Phase 1은 공통 인프라(top_volume:50). 일봉 Phase 2(`rules_daily.py`)는 daily 데이터.
매도시점: 분봉 5룰 BookBacktester 공통 청산(sl3%/tp5%/mh120) + EOD. 개별 매도 로직 없음(전부 buy).

### Phase 1 — 분봉 5룰 매수시점
| 룰 | 매수시점 (진입 조건) |
|---|---|
| `holy_grail` | ADX(14) > 30 **and** ADX 상승(last>prev) + 종가 > 20EMA + 직전 봉 저가가 20EMA ±0.5% 터치(첫 풀백) + 마지막 종가 > 직전 봉 고가(돌파). Raschke 본인 추천. |
| **`anti`** ⭐ | 종가 > 20EMA(롱 필터) + 직전 5봉 ±0.5%↑ 임펄스 + %D(10) 상승(d[-1]>d[-3]) + %K(7) 훅업(k[-2]<k[-3] **and** k[-1]>k[-2]). 스토캐스틱 훅. |
| `gimmee_bar` | 볼린저(20,2σ) MA 기울기 ≤0.1%(횡보) + 밴드 하단 터치(현/직전 저가 ≤ 하단×1.001) + 마지막 봉 양봉 + 종가 < 중심선. |
| `nr4_breakout` | 직전 4봉 중 마지막 봉이 최소 range(NR4) **and** 마지막 종가 > NR4봉 고가(돌파). (일봉 NR4를 30분 윈도우로 변형.) |
| `momentum_pinball` | 첫 60봉(1시간) LBR/RSI = RSI(3) of ROC(1) < 30 + 마지막 종가 > 첫 60봉 고가(돌파). |

### 백테스트 결과
- **베스트 = `anti`**: 3기간 평균 PnL **+10.24%** (3책 통틀어 최대 절대 PnL), 1,860거래. 2025-10 단독 **+59.05%, Calmar 7.59, Hit 49.6%** (1,561거래).
- **단, 평균 Sharpe −2.27** + 다른 기간 −11~−17% → 시장/국면 의존성 극단. 변동성 필터 추가 검증 필요.
- 나머지: momentum_pinball +2.60%, gimmee_bar +1.39%, nr4_breakout −4.12%, **holy_grail −6.87%** (Raschke 본인 추천이 1분봉엔 부적합).

### (참고) Phase 2 일봉 5룰 — `rules_daily.py`
분봉 아님(daily). 매수시점만: `turtle_soup`(20일 신저점 후 직전저점 위 종가), `turtle_soup_plus_one`(D-1 신저점+종가<직전저점 → D 직전저점 위 종가), `rule_80_20`(전일 대형봉 시가상위20%·종가하위20% → 당일 전일저점 위), `adx_gapper`(ADX(12)>30 +DI>−DI + 갭다운 → 전일저점 위 회복), `two_period_roc`(2일 ROC 음→양 전환). 매도는 daily BookBacktester 청산.

---

## 4. 강창권 — 주식투자 단기 트레이딩의 정석 (분봉 6룰)
출처: `strategies/books/haru_silijeon/rules.py`, 실행 `scripts/run_haru_silijeon_minute.py`, 결과 `reports/books_research/haru_silijeon/report.md`

매수후보: 공통 인프라. **기본 universe=top_volume:50**, LOOKBACK_DAYS=5 추가 로드(480분선 warmup).
매도시점: 6룰 BookBacktester 공통 청산 **sl2%/tp2%/mh30봉** + EOD. 개별 매도 로직 없음(전부 buy). CK480은 책 권장 tp2%/sl2% 반영. ma20선 하향이탈 청산은 sl/tp로 근사.

### 룰별 매수시점 (전자책 원문 기준 코드화)
| 룰 | 매수시점 (진입 조건) |
|---|---|
| **`ck480`** (시그니처 ★) | ①당일 장중 고가 등락률 ≥ +15%(급등주) ②시간 12:00~14:30(점심~) ③480분선(멀티데이) 위, 종가≥ma480(역배열 추격 금지) ④직전 15봉이 480선 ±1% 부근 지지 횡보 ⑤마지막 봉 양봉 재상승. |
| `ma_5_10_pullback` | 직전 20봉 +2%↑ 상승추세(run) + 마지막 저가가 5분/10분선 ±0.5% 터치(눌림) + 마지막 봉 양봉 + 종가 ≥ min(ma5,ma10). |
| `ma20_pullback` | 종가≥20분선 **and** 직전종가≥ma20×(1−0.5%) (정배열) + 마지막 저가 20분선 ±0.5% 터치 + 마지막 봉 양봉. |
| `ma_240_480_support` | 종가≥480분선(저항 통과) + 마지막 저가 240/480분선 ±0.8% 터치 + 거래량 회복(마지막 vol ≥ 직전20봉 평균×1.2) + 양봉. |
| `prev_high_break` | 윈도우에 전일 봉 존재 + 직전종가 ≤ 전일고가 < 마지막종가(돌파 순간) + 거래량 급증(≥직전20봉 평균×2) + 양봉. (VI는 데이터 없어 거래량으로 근사.) |
| `open_two_red_then_green` | 개장 후 30봉 이내(시초가) + 당일 직전 2봉 모두 음봉 + 마지막 봉 강한 양봉(몸통 ≥0.3%) + 거래량 급증(≥직전10봉 평균×1.5). |
| (스킵) A-05 이틀연속 20분선 패턴 — 복잡도로 v1 제외. |

### 백테스트 결과 (전멸) — top_volume:50, sl2%/tp2%/mh30
| 룰 | 2025-10 (T/PnL) | 2026-04 | 2026-05 | 판정 |
|---|---|---|---|---|
| `ck480` (시그니처) | 7 / **−0.12%** | 44 / −0.57% | 40 / −0.52% | 표본부족(7~44T), 전부 소폭 음수 |
| `open_two_red_then_green` | 89 / **+0.10%** | 204 / −0.63% | 222 / −1.55% | 중립(2025-10만 양수) |
| `prev_high_break` | 468 / −2.19% | 559 / −2.87% | 468 / −1.98% | 전 기간 −2~3% |
| `ma_5_10_pullback` | 1,583 / −6.75% | 2,976 / −23.32% | 2,988 / −26.55% | 과매매 손실 |
| `ma_240_480_support` | 5,035 / −29.84% | 3,690 / −23.06% | 3,014 / −18.36% | 장기 이평 무력 |
| `ma20_pullback` | 12,070 / **−50.13%** | 10,968 / −52.85% | 9,945 / −52.55% | **과매매 참사**(1만+ 거래) |
| all_AND | 0 / 0% | 0 / 0% | 0 / 0% | 동시 충족 불가 |

**관찰**: 거래수와 손실이 정확히 비례. 분봉 이평을 단순 이탈=청산으로 코드화하면 한국 분봉 휩쏘에 매 봉 손절당해 거래 폭증(ma20 1만+) → −50%대 누적. 시그니처 ck480은 진입조건이 빡빡해 7~44건뿐 = 통계적 무의미. **강창권의 가치는 분봉이 아니라 일봉**(같은 룰셋 일봉 이식 시 6/7 양 PnL: daily_ma5_10 +46.15%, daily_ma20_pullback Sharpe 0.44/hit51.8%, daily_new_high_breakout +19.99%).

---

## 5. 트레이딩의 전설 — 분봉/호가창 스캘핑군 (그룹 B, 코드화 안 됨 = 카탈로그)
출처: `reports/books_research/trading_legends/report.md` §2 그룹 B

> **명시**: 아래는 코드(rules.py)가 아니라 **카탈로그 기록**이다. 키움영웅전 9인 인터뷰집의 분봉/호가창 스캘퍼 4인 기법으로, **4권(아지즈/벨라/라쉬케/강창권) 분봉 전멸 선례 때문에 코드화·백테스트를 생략**했다. 매수후보·매수시점은 인터뷰 구어체 노하우 요약이며 정량 룰·백테스트 수치 없음.

| 닉네임 | 기법 (B 번호) | 매수후보 | 매수시점 (구어체) | 매도시점 |
|---|---|---|---|---|
| 만쥬 | B1. 1분 스캘핑 + 짝짓기 | 대장주-부대장주 짝 | 대장주 수급 유입 순간 부대장주 매수, 0.5~1% 무한반복, 보조지표 미사용 | **1분 내 미상승 시 즉시 손절** |
| 바른다른 | B2. VI 시차 짝짓기 | 조건검색(거래량 급증) 1·2등주 | 1등주 1차 VI → 2등주 반 추종, 1등주 2차 VI → 2등주 1차 VI | 짧은 익절 |
| 월억언제해보나 | B3. 1분 1% 감지 + 마킹 | 조건검색 "1분내 1%↑" 전종목 | 의미있는 가격대 선별 매수, 마킹(관심종목 1주씩), 20분 지수이평·프로그램수급 | (구어체, 미명시) |
| 캐리 | B4. 호가창 콘돈 | 5천만↑ 체결 색상 종목 | 전고돌파 + 낙주(매물벽 아래 반등), VI 직전 강한 양봉 | **전고돌파 실패 시 즉시 손절** |

**카탈로그 결론(report.md §6)**: 그룹 B는 4권 전멸 선례로 코드화 생략(기록만). 트레이딩의 전설에서 코드화·백테스트된 것은 **일봉/오버나이트 그룹 A**(종가매매 −3.95% 실패, 상따 +3.44%/MaxDD7.46% 니치, ma5_pullback B +33.66%는 Book14 눌림목 재확인일 뿐). 책 전체 판정 = **CANDIDATE 부적격**.

---

## 6. 분봉 단타 전멸 — 종합

| 책 | 베스트 분봉 룰 | 3기간 평균 PnL | 평균 Sharpe | 표본 |
|---|---|---|---|---|
| 아지즈 | bull_flag | **−0.04%** | −0.11 | 32T (조건 빡빡, break-even) |
| 벨라피오레 | fade_vwap | +1.74% | **+0.37** (유일 양 Sharpe) | 964T |
| 라쉬케 | anti | **+10.24%** (2025-10 +59%) | **−2.27** (변동성 극단) | 1,860T |
| 강창권 | open_two_red_then_green | ≈0%(2025-10 +0.10%) | (음/중립) | 89~222T |
| 트레이딩의전설 (B) | — (코드화 안 됨) | — | — | — |

- **모든 책의 분봉 룰이 음수 또는 0에 수렴.** 양 PnL은 (a)bellafiore fade_vwap만 평균 Sharpe 양수(+0.37), (b)raschke anti는 절대 PnL 최대지만 평균 Sharpe −2.27로 리스크조정 후 실패, (c)나머지는 break-even(거래 극소) 아니면 과매매 −50%대.
- **공통 패턴**: 진입을 빡빡하게 거른 룰(bull_flag, ck480, top_reversal, catalyst_gap)은 거래 극소 → 통계 무의미(0~수십 거래). 단순 이평/돌파 룰은 한국 분봉 휩쏘에 거래 폭증(수천~수만) → 손실이 거래수에 정비례.
- **데이터 한계**: 분봉 3기간 모두 2025-10/2026-04/05 폭등장 구간(1년3개월). 그럼에도 분봉 단타는 손실 → "분봉 단타는 한국 시장에서 어렵다"가 4책 + 카탈로그 1건으로 일관 확인.
- **대안 방향**: 동일 패턴(이평 눌림·돌파)을 **일봉 해상도**로 옮기면 양 PnL(강창권 daily_ma5_10 +46%, Elder ema_pullback +23.76% Sharpe 1.22). 분봉 단타가 아니라 일봉 추세추종이 한국 시장에서 생존.

---

# ③ 펀더멘털·퀀트·자산배분군 (린치·그린블라트·오쇼너시·문병로·홍용찬·systrader79)

# 펀더멘털·퀀트·자산배분 전략군 (6책) — 매수후보 / 매수시점 / 매도시점

> 출처: 각 책의 실제 `rules.py`(진입 룰) + `backtest/allocation_backtester.py`(systrader79) + `reports/books_research/<book>/report.md`(백테스트 수치). 추정 아님 — 코드 Read 확인.

## 공통 구조 (펀더멘털 5책)

- **모든 룰은 롱·매수 전용**(`RuleResult.side="buy"`). **매도 룰이 코드에 존재하지 않는다** → 청산은 전적으로 백테스터의 **파라미터(sl/tp/mh)와 리밸런싱 교체**로만 일어난다.
- **매수후보(universe)는 횡단면 팩터 순위**다. 룰은 DB를 재조회하지 않고, **run 스크립트가 거래일 i마다 사전계산한 순위·재무를 `ctx`로 주입**(예: `pbr_rank`, `vc_rank`, `magic_rank`, `fund` dict). 룰의 `evaluate()`는 `ctx` 값만 읽고 `rank <= top_n`(기본 20) + `n_eligible >= min_eligible`(기본 10)을 확인한다.
- **순위 산식**: 거래일별로 적격 종목을 팩터별 백분위/오름차순 정렬 → 합산/평균 → dense ordinal 순위(1 = 가장 저평가/최우량). 적격 = 해당 팩터들이 모두 유효(NULL/<=0 가드 통과)한 교집합.
- 재무는 **point-in-time, 105일 lag, no-lookahead**. 일봉 해상도. 거래비용 왕복 ~0.41%.
- **청산 variant 규약** (모든 펀더멘털 책 공통, report.md 표 헤더에서 추출):
  - **Variant A**: sl 12~20% / tp off(또는 50%) / mh 120거래일 — 장기보유
  - **Variant K**: sl 17.5~20% / tp off / mh 250거래일 — 연 1회 보유(가치투자 기본)
  - **Variant B**: sl 8% / tp 12% / mh 20거래일 — 빠른 청산
  - **Variant Q**(홍용찬만): sl 20% / mh 63거래일 — 분기보유
  - mh = max holding(보유 상한, 거래일 단위). 도달 시 강제청산(mh-exit). tp/sl/mh 중 먼저 닿는 것으로 청산, 아니면 데이터 종료 시 forced_close.
- **성격**: "횡단면 순위 상위 N 매수 · 보유기간 만료/손절·리밸런싱 교체 매도"의 정기 리밸런싱형. 시점은 종목 타이밍이 아니라 순위 진입.

---

## 1. 피터 린치 (lynch_one_up) — Book 8

펀더멘털 단독 진입, 5책 중 유일하게 **횡단면 순위가 아닌 per-stock 절대 임계값**(fund dict 직접 조건). 4룰 모두 `ctx["fund"]`만 읽음.

### 매수후보(universe)
- universe = **fundamentals:131**(재무 보유 종목; top_volume:50과 교집합 부족으로 전 재무종목 사용). psr·dividend_yield 100% NULL → 자산주(PSR)·PEGY(배당) 룰은 대체 룰로 발상만 구현.

### 룰별 매수시점 (rule.evaluate 진입 조건)
| 룰 | 매수 조건 (전부 AND) |
|---|---|
| **rule_fast_grower** (Lynch 최애) | PEG<1.0 AND g_ni∈[20,50]% AND debt_ratio<80% AND roe>10% AND net_income>0 AND prior_ni>0. 옵션: RSI(14)<50(계산 가능할 때만 게이트, 불가하면 펀더멘털만으로 통과). |
| **rule_stalwart** (대형우량) | g_ni∈[10,20]% AND PEG<1.5 AND roe>10% AND debt_ratio<100% AND net_margin>0 (배당 NULL → net_margin 품질 프록시) |
| **rule_value_balance_sheet** (자산주 대체) ⭐ | PBR<1.0 AND debt_ratio<50% AND 0<PER<12 AND net_income>0 (PSR<1 불가 → 저PBR+저PER+저부채로 자산주 발상) |
| **rule_garp_combo** (PEGY 대체) | PEG<1.2 AND g_ni>15% AND roe>12% AND debt_ratio<120% AND operating_margin>5% |

PEG = per/g_ni. fund 또는 필수 키가 None/NaN이면 미진입.

### 매도시점
- 매도 룰 없음. Variant A(sl 12% / tp 50% / mh 120) 또는 Variant B(sl 8% / tp 12% / mh 20)의 손절·익절·보유만료로만 청산.

### 백테스트 (report.md, per-trade)
- 베스트 = **value_balance_sheet** (유일하게 표본 견고). Variant B 114거래 per-trade 승률 **52.6%, 평균 +2.84%/거래** (A 34거래 +11.51%이나 forced_close 15건이 견인). fast_grower·stalwart는 1~6거래로 통계 무의미. all_AND = 0거래(가치 vs 고성장 상호배타).
- 결론: "단순 가치 스크린이 복잡한 GARP를 앞섬." **데이터 제약(연간·극소 universe·NULL)으로 inconclusive, CANDIDATE 부적격**.

---

## 2. 그린블라트 마법공식 (greenblatt_magic) — Book 9

### 매수후보(universe)
- universe = **magic:79**(market_cap 보유). run 스크립트가 거래일별 **EY(이익수익률 EBIT/EV) rank + ROC(자본수익률) rank 합산** → dense ordinal `magic_rank` 주입. 적격 universe 평균 66종목.

### 룰별 매수시점
| 룰 | 매수 조건 |
|---|---|
| **rule_magic_formula_top** (주력) ⭐ | magic_rank ≤ top_n(20) AND n_eligible ≥ 10. 순위 상위 20 매수. |
| rule_magic_formula_threshold | EY>0.10 AND ROC>0.25 (절대 임계) |
| rule_high_roc_value | EY>0.08 AND ROC>0.40 (품질 틸트) |

### 매도시점
- 매도 룰 없음. Variant A/B의 sl/tp/mh + 익일 순위 이탈 시 리밸런싱 교체.

### 백테스트
- **순위 룰만 작동, 절대 임계값 룰은 전멸(0거래)** — 한국 대형주 ROC max=24.7%로 ROC>25% 도달 불가(미국 캘리브레이션 부적합). Magic Formula 본질 = 상대 순위.
- 6개월 창: magic_formula_top B 197거래 per-trade 승률 61.4% +4.88%/거래(펀더멘털 책 최고 표본).
- **다년(2021~2026) 재검증: Sharpe 0.41→0.12 붕괴, per-trade 승률 84%→50.7%(동전)**. 6개월 숫자는 단일 BULL 거품. **CANDIDATE 부적격**.

---

## 3. 오쇼너시 What Works (oshaughnessy / osullivan_what_works) — Book 10

### 매수후보(universe)
- universe = **factor:79**. run 스크립트가 `vc_rank`(VC1식 4팩터=PSR+PE+PB+EV/EBIT 백분위 평균), `tv_rank`(가치복합 상위 40% 게이트 ∩ 3개월 모멘텀 내림차순), `psr_rank`(PSR 오름차순)를 거래일별 주입.

### 룰별 매수시점
| 룰 | 매수 조건 |
|---|---|
| **rule_value_composite** (주력) | vc_rank ≤ 20 AND n_eligible ≥ 10. 4팩터 가치복합 상위. |
| rule_trending_value (플래그십) | tv_rank ≤ 20. 저평가 게이트 ∩ 모멘텀 상위. |
| **rule_low_psr** (시그니처) ⭐ | psr_rank ≤ 20 AND n_eligible ≥ 10. 저PSR 상위. |

### 매도시점
- 매도 룰 없음. Variant A/B sl/tp/mh + 순위 이탈 교체.

### 백테스트
- **단일 저PSR(low_psr)이 4팩터 복합·Trending Value를 앞섬** → "PSR = 가치 팩터의 왕" 확인. 6개월: low_psr B 200거래 승률 54.5% +4.63%/거래.
- **다년 재검증: Sharpe 0.36→0.11 붕괴, 승률 84%→48%**. low_psr은 다년에서도 오쇼너시 베스트 유지(PSR 명제 재확인)하나 risk-adjusted 엣지 미미. **CANDIDATE 부적격**.

---

## 4. 문병로 메트릭 스튜디오 (moonbyungro_metric) — Book 11 (한국 저자 1호)

**펀더멘털 책 최초로 다년(2021~2026, 1,241거래일, 2022 BEAR 포함) 다국면 검증** — market_cap 5년 백필 + PCR(영업현금흐름) DART 백필 덕분.

### 매수후보(universe)
- universe = **factor_kr:131**. 5팩터 모두 cheap=low: PBR, PER, PSR=(mc/1e8)/revenue, POR=(mc/1e8)/operating_profit, **PCR=(mc/1e8)/operating_cash_flow**. n_eligible median 52. run 스크립트가 `pbr_rank`, `vc_rank`(5팩터 백분위 평균), `smallvalue_rank`(시총 하위 40% 게이트 ∩ 5팩터 복합) 주입.
- **PCR NULL 처리**: vc_rank/smallvalue_rank는 5팩터 전부 유효한 교집합 → OCF 부재 종목은 부적격(4팩터 fallback 아님). pbr_rank는 PBR만 보므로 PCR과 독립.

### 룰별 매수시점
| 룰 | 매수 조건 |
|---|---|
| **rule_low_pbr** (시그니처) | pbr_rank ≤ 20 AND n_eligible ≥ 10. "한국=저PBR 민감" 명제 검증용. |
| **rule_value_composite_kr** (주력) ⭐ | vc_rank ≤ 20 AND n_eligible ≥ 10. 5팩터 가치복합 상위. |
| rule_small_value (플래그십) | smallvalue_rank ≤ 20. 소형주(시총 하위40%)×가치. |

### 매도시점
- 매도 룰 없음. **Variant K (sl 17.5% / tp off / mh 250)** = 문병로 -17.5% 손절 + 연1회 보유. Variant A(sl 20% / mh 120), B(sl 8% / tp 12% / mh 20), +4월 리밸런싱 게이트(연 1회 교체).

### 백테스트 (다년)
- 베스트 = **value_composite_kr** K +13.68% **Sharpe 0.09** (per-trade 승률 40.4%). small_value K +6.99%, **low_pbr 시그니처는 K +3.29%(승률 36.7%)로 3룰 중 최하**.
- **핵심 발견**: ① 5팩터 복합 > 저PBR 단독 → 문병로 "한국=저PBR 민감" 명제 **부분 반박**(가치는 복합으로 써야 함). ② 장기보유(K/A) > 단기청산(B). ③ 4월 게이트(연1회)로도 상시 신호와 유사 PnL.
- **Sharpe 0.09 = 펀더멘털 4책째 붕괴**. CAGR ~2.4%. **CANDIDATE 부적격**.
- 국면 분해: 가치룰은 BEAR 국면 안에서 버는 방어가 아니라(exit-BEAR 전부 음수) **BEAR 저가 진입→BULL 청산 역발상 매수**(entry-BEAR 양수). 저PBR BEAR 방어는 긴 보유(K +1.28%)에서만 양수, 짧은 보유(A −1.68%) 붕괴.

---

## 5. 홍용찬 실전 퀀트투자 (hongyongchan) — Book 12 (한국 저자 2호)

계량/시스템 퀀트. 문병로(Book 11) 인프라 85% 재활용, universe 131 동일(책간 직접 A/B 가능). **배당 전략 제외(사장님 방침)**.

### 매수후보(universe)
- universe = **factor_kr:131**. **4선 저밸류 = PER+PBR+PCR+PSR**(문병로 5팩터에서 POR 제외) 백분위 평균. run 스크립트가 `v4_rank`(4선 복합), `smallv4_rank`(시총 하위 **20%** 게이트 ∩ 4선), `hong_rank`(소형주20% ∩ 흑자 ∩ 성장YoY>0 ∩ 마진/부채 게이트 ∩ 4선) 주입. 게이트 지표는 skip-missing(데이터 있으면 적용, 없으면 통과). n_eligible median 55, hong_gate median 7/date.

### 룰별 매수시점
| 룰 | 매수 조건 |
|---|---|
| **rule_value4_low** (시그니처) ⭐ | v4_rank ≤ 20 AND n_eligible ≥ 10. 4선 저밸류 복합 상위. 문병로 5팩터 직접 대조군. |
| rule_small_value4 (플래그십) | smallv4_rank ≤ 20. 소형주20%×4선. |
| rule_hong_combo (주력·완전체) | hong_rank ≤ 20. 밸류×성장×퀄리티 게이트. |

### 매도시점
- 매도 룰 없음. **Variant K (sl 17.5% / mh 250)** 문병로와 동일(직접 비교용), Variant Q (sl 20% / mh 63 분기보유), B (sl 8% / tp 12% / mh 20), +분기/4월 리밸런싱 게이트.

### 백테스트 (다년)
- 베스트 = **value4_low** K +12.87% **Sharpe 0.11** (승률 42.7%). small_value4(소형20%) +12.53%, hong_combo(게이트) +8.93%.
- **핵심 발견 3가지**: ① 4선 ≈ 5팩터(문병로 value_composite_kr +13.68%와 거의 동급 — 밸류 4개나 5개나 차이 없음). ② **성장/마진/부채 게이트가 알파를 못 더한다**(hong_combo +8.93% < 순수 4선 +12.87% → 책 핵심 주장 부분 반박, "단순>복잡" 패턴). ③ **소형주 20% > 40%**(홍 +12.53% > 문 +6.99%).
- **Sharpe 0.11 = 펀더멘털 5책째 붕괴**. CAGR ~2.3%. **CANDIDATE 부적격**.

---

## 6. systrader79 평균모멘텀스코어 자산배분 (allocation/systrader79_avgmom) — Book 13

**개별주 아닌 자산배분/시계열 모멘텀** — "위험자산에 몇 % 노출할까"의 **연속 비중** 전략. 전용 트랙 `backtest/allocation_backtester.py`(book_backtester는 연속비중 표현 불가).

### 매수후보 = 자산 비중 (universe 개념이 다름)
- 위험자산 = **KOSPI 지수**, 안전자산 = **현금(연 0.0%)**. 종목 선택이 아니라 두 자산의 동적 비중. 월간 리밸런싱.

### 매수시점 = 평균모멘텀스코어 산식 (월말 비중 결정)
- 월말 종가 P[m]에 대해: `score[m] = (1/12)·Σ_{k=1..12} 1[P[m] >= P[m-k]]` (0~1 연속). 즉 현재가가 1~12개월 전 월말 종가보다 높은 개수 ÷ 12.
- **위험자산 목표비중 w_risk[m] = score[m]**, 안전자산 = 1 - score[m].
- 워밍업 12개월 필요(첫 12개월 미산출). no-lookahead: score[m]은 P[m]…P[m-12]만 사용. 백테스터가 w[m]을 m→m+1 수익에 적용(월말 신호 → 익월 보유).

### 매도시점 = 비중 축소 규칙 (연속)
- 별도 매도 시점 없음. **score 하락 시 위험자산 비중 자동 축소**(현금 비중 증가)가 곧 부분 매도. 매월 리밸런싱으로 w_target과 드리프트 비중 차이만큼 회전. 왕복 리밸런싱 비용 30bp(백테스터 기본 round_trip_bps).
- 비중 드리프트 처리: 보유 후 가치변동으로 이동한 비중을 다음 달 목표와 비교해 turnover 계산.

### 백테스트 (52개월, 2022-01~2026-05)
| 지표 | 평균모멘텀스코어 | KOSPI b&h |
|---|---:|---:|
| CAGR | +24.44% | +30.62% |
| Sharpe | 0.918 | 0.983 |
| MaxDD | **19.08%** | 21.84% |
| 위험자산 평균노출 | 55.8% | 100% |

- **MDD 방어 성공**(19.1% < 21.8%, 낮은 MDD 우상향), Sharpe는 미개선(0.92 < 0.98), **절대수익은 b&h에 패**(폭등장 노출 56% 제한 대가). 연도별 비중: 2022 BEAR 10.4% → 2025~26 폭등장 74~96%로 자동 추종.
- systrader79 테제(MDD 낮추며 우상향) **성립**. 단 단일자산 MVP·단일 국면(2025~26 대폭등 편향). Elder 포트폴리오와 동일 패턴(방어형은 폭등장서 절대수익 짐). **CANDIDATE 등록은 아니나 MDD 방어 입증**.

---

## 종합

- **펀더멘털 5책(린치·그린블라트·오쇼너시·문병로·홍용찬)**: 전부 "횡단면 팩터 순위 상위 N(기본 20) 매수 · 보유기간 만료(mh)/손절(sl)·순위 이탈 리밸런싱 교체 매도"의 정기 리밸런싱형. **매도 룰은 코드에 없고 청산은 variant 파라미터로만**. 다년 검증 시 전부 **Sharpe 0.05~0.12로 붕괴 → 5책 연속 CANDIDATE 부적격**. 6개월 단일 BULL 숫자(승률 54~61%)는 거품, 다년 승률 40~50%(동전).
- 반복 패턴: **단순/단일 가치 팩터(value_balance_sheet, low_psr, value4_low/5팩터 복합)가 복잡한 멀티팩터·성장 게이트(garp_combo, trending_value, hong_combo)를 표본·성과에서 앞섬**. 절대 임계값(그린블라트 ROC>25%)은 미국 캘리브레이션이라 한국서 전멸 → 상대 순위만 이식 가능.
- **systrader79(자산배분)**: 성격이 다름 — 개별주 순위가 아니라 KOSPI+현금 **연속 비중**. 평균모멘텀스코어로 노출 결정, 비중 축소가 곧 매도. **MDD 방어는 입증(19.1%)하나 폭등장 절대수익은 b&h에 패**.

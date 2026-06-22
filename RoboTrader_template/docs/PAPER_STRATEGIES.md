# 가상매매(페이퍼) 운영 전략 — 정본 문서

> SSOT: `config/trading_config.json` `strategies[]` (이 문서는 그 스냅샷의 해설).
> 최종 갱신: 2026-06-13 · 상태: **8전략 활성 (`paper_trading: true`)** · 사이징=A안 균등 K분할 발효(2026-06-12).

## 0. 운영 개요

### 0.1 무엇을 하는가
- KIS API 기반 자동매매 프레임워크 위에서 **8개의 독립 매수 전략을 동시에 페이퍼(가상) 운영**한다.
- 목적은 단일 "최고 전략" 찾기가 아니라, **성격이 다른 전략군(추세·돌파·눌림목·평균회귀·RS)을 격리 자본으로 병렬 관찰**하여 라이브 거동을 실증하는 것. 전략끼리 자본을 나눠 쓰지 않으므로 한 전략의 부진이 다른 전략에 영향을 주지 않는다.
- `paper_trading: true` → 실제 주문은 나가지 않고, 체결을 시뮬레이션해 전략별 원장에 기록한다.

### 0.2 데이터 소스 (SSOT)
- **일봉 = `robotrader_quant.daily_prices`** (2,601종목 · 매일 2,487행 · market_cap 완비, close는 이미 수정주가).
  - ⚠️ `adj_factor`를 **곱하지 말 것** — quant close는 이미 조정됨(곱하면 분할일 가짜 절벽 → 거짓 99% MaxDD).
  - ⚠️ `daily_prices.date`가 text 컬럼이라 손상값 행이 섞임 → coerce/dropna 필수.
- **분봉 = `robotrader.minute_candles`** (quant엔 분봉 테이블 없음). 현재 8전략은 전부 **일봉 기반**이라 분봉은 보조용.
- **EOD 매수후보 스크리너는 전부 quant(클린)로 산정.**
- **라이브 진입 평가 데이터**:
  - `book_envelope_200d`만 200영업일이 필요해 `QuantDailyReader`(quant SSOT)에서 **230봉 직접 조회**(클린).
  - 나머지 7전략은 프레임워크 일봉 피드(robotrader, ~85봉, sparse·거래량 quant 대비 ~13% 차이) 사용 → 거래량 룰에 미세한 품질 영향(파국 아님).

### 0.3 공통 매매 경로
- **진입**: `BaseStrategy.on_tick(ctx)` → `ctx.get_daily_data`(`_drop_unconfirmed_today_bar` 적용 = 당일 미확정봉 제외, 확정봉만) → `generate_signal()` → `ctx.buy()`(서킷브레이커·VI·시장방향 가드 내장).
- **전 전략 진입 룰은 백테스트 룰을 1:1 재사용** (`strategies/books/**/rules*.py`, `scripts/rs_leader/rule.py`, `scripts/discovery/rules.py`를 직접 import) → 백테스트↔라이브 동등성 보장.
- **전 전략 `holding_period = "swing"`** → EOD 일괄청산을 건너뛰고 각 전략의 청산 룰(sl/tp/trail/max_hold)로만 빠진다.

### 0.4 자본·사이징 모델 (A안 균등 K분할, 2026-06-12 발효)
- **전략별 독립 가상자본 = 1,000만원** (`VIRTUAL_CAPITAL_PER_STRATEGY`, `config/constants.py:124`). 8전략 × 1,000만 = **총 8,000만원** 가상.
- **종목당 매수금액 = 가상자본 ÷ K(`max_positions`) 균등분할** (`main.py::_allocate_strategy_capital`). K는 yaml `risk_management.max_positions`에서 직접 읽는다.
  - 단, yaml에 `paper_investment_per_stock`이 명시되면 그 값이 K분할 기본값을 **덮어쓴다**(사이징 시나리오 검증값 적용 — 현재 `deep_mr_dev20`만 사용).
- **결과 종목당 금액**: elder 50만 / envelope 200만 / daytrading 200만 / minervini 333만 / ma20 200만 / ma5 200만 / rs_leader 100만 / deep_mr 200만.
- ⚠️ `max_capital_pct`(아래 표)는 **별개 레이어**(`FundManager` 실계좌 reserve 비율)로, 가상매매의 전략별 1,000만 격리·종목당 금액과는 **무관**하다. 페이퍼 손익은 폴더키별 격리 원장으로만 집계된다.

### 0.5 두 개의 regime(국면) 레이어 (혼동 주의)
| 필드 | 의미 | 소스 |
|---|---|---|
| `regime_index` | **시장방향 급락 검사**용 지수 (장중 `ctx.buy` 가드) | KIS 실시간지수 (KOSPI 0001 / KOSDAQ 1001) |
| `regime_gate` | **국면 매수차단** (BEAR/비BULL 진입 차단, EOD 1회 캐시 PIT) | `core/regime/regime_gate.py`, `daily_prices` KOSPI/KOSDAQ + `classify_daily` |

## 1. 활성 전략 한눈표

| # | 전략 (폴더키) | 출처 | 진입 핵심 | 청산 (sl / tp / trail / maxhold) | regime idx/gate | K | 종목당 | 유니버스 |
|---|---|---|---|---|---|---|---|---|
| 1 | `elder_ema_pullback` | Elder 삼중창 (Var A) | EMA65 상승 + EMA13 눌림회복 + 전일고가 돌파 | -8% / +30% / EMA13 trail·EMA65 추세반전 / 100일 | KOSPI / none | 20 | 50만 | 대형(시총≥5천억)·거래대금≥50억 |
| 2 | `book_envelope_200d` | Book19 트레이딩 전략서 | 200일 신고가 + Envelope(10,10) 상단 +10% 돌파 (A~I) | -8% / +10% / 없음 / 10일 | KOSPI / none | 5 | 200만 | 거래대금≥10억 (진입평가 quant 230봉) |
| 3 | `daytrading_3methods_breakout` | 유지윤 3대 타법 (Var B) | 직전15봉 전고점 돌파 + 거래량×2 + 양봉 | -10% / +10% / 없음 / 10일 | KOSDAQ / none | 5 | 200만 | 중소형(시총<5천억)·거래량배수순 |
| 4 | `minervini_volume_dryup` | Minervini VCP (Var B) | 최근10봉 평균거래량 ≤ 직전30봉의 70% (dry-up) | -8% / +12% / 없음 / 20일 | KOSPI / none | 3 | 333만 | 시총≥3천억·거래대금≥30억 |
| 5 | `book_pullback_ma20` | 강창권 단기트레이딩 A-07 | 30일내 +25% 급등 + 20일선 눌림 지지 양봉 | -8% / +10% / MA20 trail / 50일 | KOSPI / exclude_bear | 5 | 200만 | 중소형(시총≤3조)·KOSPI+KOSDAQ |
| 6 | `book_pullback_ma5` | 트레이딩의 전설 (Book15) | 20일내 +20% 급등 + 5일선 눌림 지지 양봉 | **-3%** / +15% / MA5 trail / 30일 | KOSPI / exclude_bear | 5 | 200만 | 중소형(시총≤3조)·KOSPI+KOSDAQ |
| 7 | `rs_leader` | 횡보장 RS 리더 (derived) | 절대상승추세 + 횡단면 RS 랭킹(스크리너) | -8% / +15%(거의무효) / **MA20 trail(무조건)** / 30일 | KOSPI / exclude_bear | 10 | 100만 | 절대상승추세 통과 → 120일수익률 RS topK |
| 8 | `deep_mr_dev20` | 발굴 파이프라인 배치3 | MA20 대비 -20% 폭락 + RSI(14)<30 | -7% / +12% / MA20×0.9 회복 / 7일 | KOSPI / none | 5 | 200만 | 거래대금≥100억 (top300 근사)·폭락깊이순 |

> 스크리너는 8전략 공통으로 `max_candidates=10`을 score 내림차순 정렬해 topK 후보를 만든다. `target_stocks: []`(전부 비움)이면 EOD 스크리너 후보를 사용한다.

## 2. 전략별 상세

### 1. elder_ema_pullback — Elder 삼중창 (Variant A)
- **의도**: 상승추세 종목의 단기 눌림을 사서 추세를 길게 먹는 정통 추세추종. 8전략 중 백테스트 최강 생존군.
- **진입** (`rule_triple_screen_ema_pullback`): ① Screen1 = EMA65 상승(5바 전 대비 기울기>0) ② Screen2 = `low[-1] ≤ EMA13×1.02` AND `close[-1] > EMA13`(눌림 회복) ③ Screen3 = 전일고가+1틱 매수스톱(metadata로 전달, 실전 체결은 시장가 기준이라 백테스트 stop-fill과 차이).
- **청산**: sl -8% / tp +30% / 수익 중 EMA13 하향이탈 trailing / EMA65 추세반전(5바 전 대비 하락) 청산 / max_hold 100일.
- **유니버스**: 대형(시총≥5천억) · 거래대금≥50억.
- **평판**: 정본 재측정 최강 — K20 Sharpe 1.55 / MaxDD 20% / +269% / alpha +22%. 약세장 방어도 상대 양호(단 깊은약세 2022 K3는 KOSPI 하회). gate=none(증거기반: elder는 게이트 무수혜).

### 2. book_envelope_200d — Book19 트레이딩 전략서
- **의도**: 200일 신고가를 막 돌파하는 강세 모멘텀을 추격. OOS 홀드아웃에서 cross-period 강건이 확인된 유일 신규 엣지.
- **진입** (`rule_envelope_200d_high`, 책 A~I verbatim): 200일 종가신고가 + Envelope(MA10)×1.10 상단 돌파 + 양봉 + 거래량 전일대비↑ + 종가>이등분선 + 5일 평균거래대금≥50억 + 갭상승/직전급등 제외 + 당일 시초대비 +3%.
- **청산**: sl -8% / tp +10% / max_hold 10거래일 / trailing 없음.
- **★데이터 특이**: 200일 신고가는 200영업일 필요 → 라이브 robotrader 피드(~85봉)로는 부족 → **진입평가용 일봉을 QuantDailyReader(quant SSOT)에서 230봉 직접조회**. 청산은 현재가·보유일만 필요해 프레임워크 일봉 사용.
- **평판**: OOS train 1.20 / test 1.82. 워크포워드=조건부 통과(엣지는 랠리 이전부터 일관·양수 8/11이나 alpha가 비강세장 한정, 메가불장 −85% 하회, 깊은약세 2022H1 −4.33). 페이퍼 관찰에 적합.

### 3. daytrading_3methods_breakout — 유지윤 데이트레이딩 3대 타법 (Variant B)
- **의도**: 거래량 동반 전고점 돌파를 빠르게 먹고 빠지는 돌파 타법. 약한 Sharpe라 탐색·관찰용.
- **진입** (`rule_breakout_prev_high`, high_window=15): 종가≥직전15봉 전고점 + 당일거래량≥15봉평균×2.0 + 양봉.
- **청산**: sl -10% / tp +10% / max_hold 10거래일 / trailing 없음(돌파 타법=고정 손익절).
- **유니버스**: 중소형(시총<5천억) · KOSDAQ regime_index · 거래량 배수순.
- **평판**: 백테스트 706T / +5.90% / Sharpe 0.17 / hit 46.7% — 약함. 일봉 게이트는 분봉 성격이라 부적합 → gate=none.

### 4. minervini_volume_dryup — Minervini VCP (Variant B)
- **의도**: 변동성 수축(거래량 dry-up) 후 매집 구간을 포착. Minervini의 알파 원천이 VCP가 아닌 dryup임이 확인됨.
- **진입** (`rule_volume_dryup`): 최근10봉 평균거래량 ≤ 직전30봉 평균의 70% (거래량 dry-up). confidence=58.
- **청산**: sl -8% / tp +12% / max_hold 20거래일. **trail 없음, trend_flip 없음** (Variant A와 차이).
- **유니버스**: 시총≥3천억 · 거래대금≥30억.
- **평판**: 정본상 평범(KOSPI 하회 −7%), K풀스윕서 K3만 생존(K10/20 MaxDD≈100%). gate=none(게이트 역효과).

### 5. book_pullback_ma20 — 강창권 『단기 트레이딩의 정석』 A-07
- **의도**: 급등 후 20일선까지 눌린 종목의 지지 반등을 노리는 눌림목.
- **진입** (`rule_daily_ma20_pullback`): ① 직전30일 내 +25% 급등 이력 ② 종가 ≥ MA20×(1−below_tol) (지지 유효) ③ 마지막 봉 저가가 20일선 ±touch_tol 터치 ④ 마지막 봉 양봉.
- **청산**: sl -8% / tp +10%(책 명시 유일 익절) / 수익 중 종가<MA20 trailing / max_hold 50거래일.
- **유니버스**: 중소형(시총≤3조) · KOSPI+KOSDAQ 모두(눌림목은 시장 무관). gate=exclude_bear(눌림목은 게이트 진짜 수혜 — MaxDD 대폭↓).
- **평판**: Sharpe 0.44 / +16%. OOS 부진(−21~97%)이나 격리자본 페이퍼 관찰로 라이브 검증 유지.

### 6. book_pullback_ma5 — 『트레이딩의 전설』(Book15) ma5_pullback
- **의도**: 급등 후 5일선까지의 짧은 눌림을 타이트 손절로 잡는 단기 트레이더형 눌림목.
- **진입** (`rule_ma5_pullback`): ① 최근20일 내 +20% 급등 이력 ② 마지막 봉 저가가 5일선 ±touch_tol 터치 ③ 종가 ≥ MA5×(1−below_tol) ④ 마지막 봉 양봉.
- **청산**: **sl -3%(타이트, 단기 트레이더 손절)** / tp +15% / 수익 중 종가<MA5 trailing / max_hold 30거래일.
- **유니버스**: 중소형(시총≤3조) · KOSPI+KOSDAQ. gate=exclude_bear(진짜 수혜).
- **평판**: Sharpe 0.63이나 **BULL 청산 의존 리스크**(OOS −87% 장기 전소). 페이퍼 관찰로 유지.

### 7. rs_leader — 횡보장 RS 리더 (derived 전략, 페이퍼 관찰 전용)
- **의도**: 시장이 안 좋을 때 상대적으로 강한(횡단면 RS 상위) 절대상승 종목을 매수. 횡보장에서 강건.
- **진입**: 절대상승추세(`RSLeaderRule(ma_short=20, ma_long=60, abs_lb=60)`: 종가>MA60 · MA20>MA60 · 60일수익>0)를 per-stock 재확인 후 매수. **횡단면 RS 랭킹은 EOD 스크리너가 담당**(절대상승추세 통과 종목의 120일 수익률을 score로 → 정렬+topK = RS 랭킹).
- **청산**: 종가<MA20 하향이탈(**무조건**) / sl -8% / tp +15%(추세추종이라 거의 무효, 트레일이 주청산) / max_hold 30거래일.
- **유니버스**: 거래대금≥10억 · 시총 컷 없음. gate=exclude_bear(깊은약세 미입증이라 약세장 매수 차단).
- **평판**: 검증 조건부(횡보장 5/5 config 강건 +5~8%·OOS 양수 ✅ / 깊은약세 부호반전·per-trade Sharpe 0.08~0.19 ❌). **Book20이 아니라 derived 전략**. 현 백테스트는 강세장 순풍 왜곡(2026-04/05 +8.5/+6.8%는 KOSPI +30/+28% 덕).

### 8. deep_mr_dev20 — MA20 -20% 폭락 평균회귀 (발굴 파이프라인 배치3 졸업)
- **의도**: -20% 깊은 폭락 + 과매도 종목을 매수해 MA20 회복까지 반등을 먹는 평균회귀. 자체 발굴 파이프라인 22변형 중 유일하게 품질 전관문(G2~G5)을 통과한 8번째 전략.
- **진입** (`MeanReversionMA20Rule`, 백테스트 단일소스): ① (종가−MA20)/MA20 ≤ -20% (깊은 폭락) ② RSI(14) < 30 (과매도).
- **청산** (`MAReversionExitAdapter` 우선순위 1:1): sl -7% → tp +12% → MA20×0.9 회복 → max_hold 7거래일.
- **유니버스**: 거래대금≥100억(top300 근사 — top500+ 확장 시 엣지 소멸 확인) · 폭락 깊이(|이탈|)순. 거래량 폴백 비허용(희소조건 전략).
- **사이징**: yaml `paper_investment_per_stock: 2,000,000` 명시(S2 시나리오 = 자본/K=200만 스위트스팟, CAGR +14.2% / Sharpe 0.79 / P(DD≥30%)=11%).
- **평판**: +51.8% / Sharpe 0.73 / MaxDD 16.2% / 거래당 그로스 +1.81% / 월 6.0회. 부트스트랩 Sharpe p05 +0.22 · 워크포워드 8/11(최악 -4.8%) · 섭동(-16~-24%) 전부 양수 · OOS train 0.93/test 0.30. ⚠️ 성격=승률 49%·중앙값 -0.33%·우꼬리 의존(+17~49%)의 "자주 조금 잃고 가끔 크게 먹는" 희소 저격형.

## 3. 운영 메모 / 잔여

- **봇 재시작 시 반영**: config 변경(전략 추가·사이징·gate)은 1회 로드라 봇 재시작 시 발효된다. deep_mr_dev20 등록 + A안 균등 K분할 사이징은 2026-06-12 적용분.
- **정식 leaderboard.parquet 등재**: envelope·rs_leader·deep_mr 등 신규/관찰 전략은 **페이퍼 실적 누적 후** 판정(지시). 현 백테스트 수치는 강세장 순풍·in-sample 편향이 섞여 라이브 실증이 필요.
- **성격 분포**: 추세(elder=강·minervini=평범) / 돌파(envelope=비강세장 alpha·유지윤=약함) / 눌림목(ma20·ma5=게이트 수혜·OOS 부진) / RS(rs_leader=횡보장 관찰) / 평균회귀(deep_mr=폭락 저격). 강세장을 이기는 게 목적이 아닌 전략이 다수 — 격리자본이라 상호 무영향.
- **데이터 버그 주의**: `daily_prices.date`가 text라 손상값 행 존재(coerce/dropna 필수). adj_factor는 quant close가 이미 조정됐으므로 **곱하지 말 것**(분할일 가짜절벽 → 거짓 99% MaxDD).

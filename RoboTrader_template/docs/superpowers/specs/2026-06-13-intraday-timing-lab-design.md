# Intraday Timing Lab (Phase 1) 설계

> 작성: 2026-06-13 · 상태: 설계 확정(사장님 위임) → 구현 계획 대기
> Feature Edge Lab(Phase 0, 종목선택 측정)의 확장 — **매수/매도 타이밍**에 새 데이터 조합(분봉)을
> 적용해 개선 여부를 **측정만** 한다. 모델학습·라이브배선·전략변경 없음.

## 1. 배경 / 동기

Phase 0는 "어떤 종목"(횡단면 선택)을 측정했다. 사장님 지시로 이번엔 "언제 사고/언제 파나"(타이밍)에
미사용 데이터(분봉)를 조합해 개선 가능성을 측정한다. 타이밍은 횡단면 IC가 아니라 **신호/포지션
조건부 측정**(대안 타이밍 하의 트레이드 결과를 baseline과 비교)이다.

메모리 교훈 "청산 충실도가 유니버스만큼 중요"([[remeasure-2026-06-05-live5-quant]]: 근사 청산이
Elder 거짓붕괴·haru 과장 유발)에 따라 청산 타이밍 레버리지가 특히 크다.

## 2. 범위 (YAGNI)

**포함**: 분봉 기반 매수·매도 타이밍 룰을 3전략 신호에 조건부 적용 → baseline 대비 델타 측정
(per-trade 평균·승률·per-trade Sharpe·MFE/MAE), 부트스트랩 p05·기간내 OOS·gross/net(비용) 리포트.

**제외**: ML, 라이브 배선, 전략 룰 변경, 국면강건성 주장(분봉이 단일국면이라 불가).

## 3. 데이터 실사 (2026-06-13)

- **분봉 `robotrader.minute_candles`**: 53.2M행, 1388종목, **2025-02-24 ~ 2026-06-12 (~1.3년),
  하루 ~300종목**. 컬럼 `stock_code, trade_date(YYYYMMDD str), time, open, high, low, close,
  volume, amount(거래대금), datetime`. **`amount` 로 진짜 VWAP = Σamount/Σvolume 장중 PIT 계산 가능.**
- **★단일국면 제약**: 2025-02 이후 = 강세/횡보뿐, 2022/2024 약세 부재 → 타이밍 엣지는 **탐색적**, 국면강건 주장 금지.
- 일봉(청산 baseline·전략 신호 워밍업): `robotrader_quant.daily_prices`(QuantDailyReader, 5년).
- 전략 신호: 기존 `scripts/feature_edge/signals.py` + `build_adapter` 재사용.

## 4. 아키텍처 / 컴포넌트

신규 `scripts/feature_edge/timing/` (Phase 0 모듈 재사용):

1. **`intraday_loader.py`** — minute_candles 에서 (stock, trade_date) 분봉 df(오름차순, time 인덱스).
   bulk 조회·캐시. 커버 종목/일자 집합 제공.
2. **`intraday_features.py`** (순수함수, PIT) — 누적 VWAP(Σamount/Σvolume, 각 봉 t까지), 오프닝레인지
   (첫 N분 고/저), 시가갭(D+1 open / D close − 1), 장중 트레일(당일 누적 고점), 장중 N분 수익률.
3. **`buy_rules.py`** — `(signal, intraday_d1) -> EntryDecision(price, time) | SKIP`. v1 룰 §5.
4. **`sell_rules.py`** — `(position, intraday_bars_over_hold, daily_exit) -> ExitDecision(price, date, time)`.
   일봉 청산과 **먼저 닿는 것**으로 오버레이. v1 룰 §5.
5. **`trade_sim.py`** — 신호 D + 일봉 + 분봉공급자 → baseline 트레이드(D+1 시가 진입 + 전략 일봉청산)
   와 대안타이밍 트레이드를 시뮬레이션해 각 결과(수익률·보유봉·MFE/MAE) 반환. **gross/net 둘 다**
   (net = 진입·청산 각 side 슬리피지 가정 차감, 기본 0.10%/side, config).
6. **`timing_metrics.py`** — baseline 대비 룰별 델타(평균수익·승률·per-trade Sharpe), 델타에
   블록 부트스트랩 p05(>0 요구), 기간내 OOS(train 2025-02~2025-12 / test 2026-01~2026-06) 부호 안정성.
   `scripts/multiverse4_portfolio_analysis.block_bootstrap_metrics` 철학 재사용.
7. **`run_timing_lab.py`** — 3전략 신호 순회 → trades.parquet + timing_report.md.

테스트: `tests/feature_edge/timing/test_{intraday_features,buy_rules,sell_rules,trade_sim,timing_metrics}.py`.

## 5. 룰 메뉴 v1 (확정)

**매수 타이밍** (D+1 분봉에 적용; baseline = D+1 시가):
- `vwap_entry` — 시가 대신 당일 첫 VWAP 터치가에 진입
- `gap_skip(x=0.05)` — D+1 갭업 > x 면 진입 스킵(고점 추격 회피)
- `opening_range_breakout(n=30)` — 첫 30분 고가 돌파 시 그 가격에 진입, 미돌파 스킵
- `pullback_to_vwap` — 갭 후 장중 VWAP 하향 터치 시 진입
- `first30_strength` — 첫 30분 종가>시가일 때만 진입(아니면 스킵)

**매도 타이밍** (보유기간 분봉에 적용; 일봉 청산과 먼저 닿는 것):
- `vwap_break_exit` — 보유 중 종가가 당일 VWAP 하향이탈 시 당일 청산
- `intraday_trail(k=0.03)` — 당일 장중 고점 대비 −k 이탈 청산
- `time_exit(hhmm="14:30")` — 해당 시각까지 미청산 시 청산
- `intraday_momentum_loss(n=30)` — 직전 n분 수익률 음전환 시 청산
- `atr_scaled_stop(k=2.0)` — 고정 −% 대신 장중 ATR×k 손절

## 6. PIT (룩어헤드 0) 규약

- 진입은 **D+1**(신호일 D의 종가로 D에 결정, 체결은 D+1). 분봉 결정은 해당 봉 t까지만.
- VWAP·오프닝레인지·트레일은 **당일 t까지 누적/창**만 사용. 당일 종가로 장중 판단 금지.
- 매도 오버레이: 보유일 d의 분봉 결정은 d의 t봉까지만. 일봉 청산은 d 종가 기준(기존 충실도 유지).
- 슬리피지는 결정가에 보수적으로 가산(매수 +, 매도 −).

## 7. 반-과적합 / 다중검정

- **단일국면(1.3년 강세/횡보) 명시** — 모든 결론은 탐색적, 국면강건 주장 금지.
- **단일룰 먼저 → 통과분만 매수×매도 조합**(조합 폭발 금지). 델타 부트스트랩 p05>0 요구.
- **gross & net 둘 다 보고** — 타이밍 엣지는 비용에 잘 먹힘, net 기준이 진짜.
- 기간내 OOS 부호 안정성 병기. 측정 조합 수 리포트(우연통과 주의).
- **표본 명시**: 신호 ∩ 분봉커버(~300종목/일)라 전략별 트레이드 수가 적을 수 있음 →
  per-strategy n 병기, 묵시적 절단 금지(no silent truncation).

## 8. 산출물 / 성공 기준

- `reports/discovery/timing_lab/{trades.parquet, timing_report.md}`.
- 리포트: 전략별 × 룰별 baseline-델타(gross/net)·부트스트랩 p05·OOS부호·표본수 랭킹.
- 성공 = "어떤 분봉 타이밍 오버레이가 어떤 전략의 트레이드를 (특히 net 기준) 개선하는지/못하는지를
  증거로 말할 수 있는 상태". 라이브 반영은 별도 결정(범위 밖).

## 9. 스코프 / 재사용

- **시작 3전략**: `daytrading_3methods_breakout`(돌파=장중네이티브)·`deep_mr_dev20`(폭락주 변동 큼)·
  `book_envelope_200d`(돌파). 결과 보고 확대.
- 재사용: `signals.py`(진입신호)·`loaders.py`(일봉/유니버스)·exit 어댑터(있으면)·부트스트랩 헬퍼.

## 10. 리스크 / 미해결

- 단일국면(약세 부재) → 타이밍 엣지 일반화 불가, 탐색적 한정.
- `deep_mr` 폭락주는 D+1 하한가로 분봉 체결 불가 가능 → trade_sim 에서 체결불가 플래그·표본서 제외 명시.
- 슬리피지는 가정값(실측 호가스프레드 아님) → net 결과는 가정 민감, 여러 슬리피지로 민감도 병기 권장.
- 분봉 커버 종목과 전략 유니버스(예: envelope 대형주) 교집합이 작으면 표본부족 → n 병기.
- 비교 기준선(전략 일봉청산)은 Phase 0/라이브와 동일 룰 유지(충실도).

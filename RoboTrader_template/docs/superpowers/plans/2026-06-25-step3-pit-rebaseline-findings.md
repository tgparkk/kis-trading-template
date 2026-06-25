# Step 3 — 5.5년·전 전략·PIT 정본 재측정 결과

> 측정 전용(라이브 코드/config 무수정). 영구룰: 숫자 검증·추정 금지 — 아래 수치는
> `scripts/step3_pit_rebaseline.py` 실행 산출(워킹트리).

## 측정 설정
- 기간: **2021-01-12 ~ 2026-06-25**
- scan 빈도(PIT/union): **monthly** — scan_date 67개 (2021-01-12 .. 2026-06-25)
- 비용/사이징: 정본 동일 (commission 0.015% / tax 0.18% / slippage 0.10%, max_per_stock=100만)
- sim·진입룰·청산·warmup·K: 정본 harness(`scripts/multiverse4_returns_export.py` SPECS) 그대로.
  **U2_PIT = run_one 로직을 스크립트에서 재구성(build_signals → pit_gate_signal_cache → run_portfolio).**

## 3-유니버스 비교표 (전략 × 유니버스)

| strategy | universe | uni_size | loaded | n_signals | n_trades | sharpe | pnl | maxdd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| elder_ema_pullback | U0_topvol | 50 | 50 | 12819 | 1357 | 0.605 | +188.10% | 48.01% |
| elder_ema_pullback | U1_union | 1795 | 1787 | 358121 | 2289 | 0.581 | +206.99% | 58.94% |
| elder_ema_pullback | U2_PIT | 1795 | 1787 | 93743 | 2260 | 0.567 | +167.58% | 61.58% |
| book_envelope_200d | U0_topvol | 50 | 50 | 472 | 297 | 0.717 | +55.20% | 14.62% |
| book_envelope_200d | U1_union | 2447 | 2431 | 6186 | 885 | 0.130 | -31.10% | 71.92% |
| book_envelope_200d | U2_PIT | 2447 | 2431 | 5547 | 873 | 0.088 | -36.73% | 78.51% |
| daytrading_3methods_breakout | U0_topvol | 50 | 50 | 1725 | 618 | 0.502 | +71.71% | 32.35% |
| daytrading_3methods_breakout | U1_union | 2428 | 2412 | 62351 | 921 | 0.690 | +84.79% | 21.28% |
| daytrading_3methods_breakout | U2_PIT | 2428 | 2412 | 24516 | 983 | 0.291 | +26.22% | 30.60% |
| minervini_volume_dryup | U0_topvol | 50 | 50 | 14557 | 300 | 0.286 | +18.37% | 22.21% |
| minervini_volume_dryup | U1_union | 1918 | 1906 | 874680 | 302 | 0.321 | +21.71% | 21.67% |
| minervini_volume_dryup | U2_PIT | 1918 | 1906 | 205012 | 326 | 0.578 | +46.29% | 17.15% |
| book_pullback_ma20 | U0_topvol | 50 | 50 | 2473 | 922 | 0.060 | -16.52% | 51.72% |
| book_pullback_ma20 | U1_union | 2445 | 2429 | 112754 | 1398 | -0.146 | -62.69% | 67.30% |
| book_pullback_ma20 | U2_PIT | 2445 | 2429 | 54941 | 1442 | -0.041 | -55.82% | 70.45% |
| book_pullback_ma5 | U0_topvol | 50 | 50 | 6696 | 1802 | -0.069 | -65.41% | 76.58% |
| book_pullback_ma5 | U1_union | 2445 | 2429 | 260523 | 2303 | -0.035 | -93.30% | 95.84% |
| book_pullback_ma5 | U2_PIT | 2445 | 2429 | 132672 | 2347 | 0.280 | -84.99% | 97.77% |
| rs_leader | U0_topvol | 300 | 300 | 65607 | 3177 | 0.592 | +205.14% | 54.41% |
| rs_leader | U1_union | 2447 | 2431 | 396579 | 3346 | 0.481 | +146.65% | 64.44% |
| rs_leader | U2_PIT | 2447 | 2431 | 277989 | 3346 | 0.482 | +147.41% | 64.41% |


- `U0_topvol` = 거래량 상위 top_n(대형주). top_n 별 실제 크기: {50: 50, 300: 300}
- `U1_union` = 스크리너 base_filter union (기간 내 scan_date 합집합; 데이터=union, 진입=union 전체)
- `U2_PIT` = 데이터=union(warmup 확보) + 진입신호를 진입봉 시점 스크리너 멤버십으로 게이팅
- `uni_size` = 유니버스 코드 수(요청), `loaded` = 일봉 30행+ 확보돼 실제 로딩된 종목 수

## 전략별 델타 (U0 → U1 → U2)

- **elder_ema_pullback**: pnl +188.10% → +206.99% (union) → +167.58% (PIT); sharpe 0.60 → 0.58 → 0.57; trades 1357 → 2289 → 2260; PIT signals 93743 (union 358121)
- **book_envelope_200d**: pnl +55.20% → -31.10% (union) → -36.73% (PIT); sharpe 0.72 → 0.13 → 0.09; trades 297 → 885 → 873; PIT signals 5547 (union 6186)
- **daytrading_3methods_breakout**: pnl +71.71% → +84.79% (union) → +26.22% (PIT); sharpe 0.50 → 0.69 → 0.29; trades 618 → 921 → 983; PIT signals 24516 (union 62351)
- **minervini_volume_dryup**: pnl +18.37% → +21.71% (union) → +46.29% (PIT); sharpe 0.29 → 0.32 → 0.58; trades 300 → 302 → 326; PIT signals 205012 (union 874680)
- **book_pullback_ma20**: pnl -16.52% → -62.69% (union) → -55.82% (PIT); sharpe 0.06 → -0.15 → -0.04; trades 922 → 1398 → 1442; PIT signals 54941 (union 112754)
- **book_pullback_ma5**: pnl -65.41% → -93.30% (union) → -84.99% (PIT); sharpe -0.07 → -0.04 → 0.28; trades 1802 → 2303 → 2347; PIT signals 132672 (union 260523)
- **rs_leader**: pnl +205.14% → +146.65% (union) → +147.41% (PIT); sharpe 0.59 → 0.48 → 0.48; trades 3177 → 3346 → 3346; PIT signals 277989 (union 396579)

## 유니버스 구성 (union 크기 vs 전체시장 2486종목)

- **elder_ema_pullback**: union 1795 종목 (= 전체시장 2486의 72%)
- **book_envelope_200d**: union 2447 종목 (= 전체시장 2486의 98%)
- **daytrading_3methods_breakout**: union 2428 종목 (= 전체시장 2486의 98%)
- **minervini_volume_dryup**: union 1918 종목 (= 전체시장 2486의 77%)
- **book_pullback_ma20**: union 2445 종목 (= 전체시장 2486의 98%)
- **book_pullback_ma5**: union 2445 종목 (= 전체시장 2486의 98%)
- **rs_leader**: union 2447 종목 (= 전체시장 2486의 98%)

> ⚠️ **union 퇴화**: 풀기간(5.5년) union 은 base_filter 가 느슨한 전략에서 전체시장에
> 근접(Step2 findings 참조). U2_PIT 는 진입봉 시점 멤버십만 인정해 이 퇴화를 우회한다 →
> U1→U2 의 signals/trades/pnl 감소분이 "정적 union 낙관편향"의 크기다.

## harness 미배선
- **deep_mr_dev20**: multiverse4 `SPECS` 에 미배선 → 본 스크립트로 측정 불가.
  (build_signals/adapter spec 부재. 별도 배선 필요.)

## 한계
- **PIT 월별 근사**: 라이브 스크리너는 일별이나 본 측정은 monthly scan_date 멤버십으로
  근사. 시총·거래대금이 완만해 월별이 분기보다 정밀하나, 월 중 신규 진입/이탈 종목의
  멤버십 전환 시점은 ±수주 오차 가능.
- **union 데이터 로딩 비용**: 풀기간 union(코드 1000~2000+)을 _batch_load_daily(ANY(%s)
  단일쿼리)로 1회 적재하나, build_signals(_precompute_signals)는 종목·봉 루프라 union 이
  클수록 무겁다(전 전략 풀런은 수십분 단위 — 백그라운드 권장).
- **정본 출처**: U0 자체가 정본(top-volume) 재현 시도. U0 가 기존 PAPER_STRATEGIES 수치와
  다르면 그 정본은 다른 기간/사이징 출처.

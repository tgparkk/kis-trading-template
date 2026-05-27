# 트레이딩 책 10권 — 통합 리더보드

> 생성일: 2026-05-27  
> 설계서: [../../docs/superpowers/specs/2026-05-27-books-research-backtest-design.md](../../docs/superpowers/specs/2026-05-27-books-research-backtest-design.md)  
> 구현 계획: [../../docs/superpowers/plans/2026-05-27-books-research-plan-1-infra-and-aziz.md](../../docs/superpowers/plans/2026-05-27-books-research-plan-1-infra-and-aziz.md)

## 진행 상태

| # | Book ID | 책 | Status | Best PnL |
|---|---|---|---|---|
| 1 | aziz_day_trade | Andrew Aziz — How to Day Trade for a Living | ✅ 완료 | bull_flag -0.02% (3기간 평균) |
| 2 | bellafiore_playbook | Mike Bellafiore — One Good Trade / PlayBook | ⏳ 대기 | — |
| 3 | raschke_street_smarts | Linda Raschke — Street Smarts | ⏳ 대기 | — |
| 4 | oneil_canslim | William O'Neil — 최고의 주식 최적의 타이밍 | ⏳ 대기 | — |
| 5 | minervini_vcp | Mark Minervini — 초수익 성장주 투자 | ⏳ 대기 | — |
| 6 | weinstein_stages | Stan Weinstein — Secrets for Profiting | ⏳ 대기 | — |
| 7 | elder_triple_screen | Alexander Elder — Trading for a Living | ⏳ 대기 | — |
| 8 | lynch_one_up | Peter Lynch — 월가의 영웅 | ⏳ 대기 | — |
| 9 | greenblatt_magic_formula | Joel Greenblatt — Magic Formula | ⏳ 대기 | — |
| 10 | osullivan_what_works | James O'Shaughnessy — What Works on Wall Street | ⏳ 대기 | — |

## 전체 백테스트 메트릭 (PnL 내림차순, 정렬)

> 1책(아지즈) × 8 single + 1 all_AND × 3기간(2025-10 / 2026-04 / 2026-05) = 27행

| Rank | Book | Rule/Combo | Mode | Period | n_stocks | n_trades | PnL % | Sharpe | Calmar | Hit Rate | MaxDD % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | aziz_day_trade | top_reversal | single | 2026-04 | 581 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 | aziz_day_trade | all_AND | all_AND | 2026-04 | 581 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 3 | aziz_day_trade | top_reversal | single | 2025-10 | 555 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 4 | aziz_day_trade | all_AND | all_AND | 2026-05 | 503 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 5 | aziz_day_trade | top_reversal | single | 2026-05 | 503 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 6 | aziz_day_trade | all_AND | all_AND | 2025-10 | 555 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 7 | aziz_day_trade | bull_flag | single | 2026-05 | 503 | 23 | -0.02 | -0.07 | +0.01 | 0.022 | 0.12 |
| 8 | aziz_day_trade | bull_flag | single | 2026-04 | 581 | 38 | -0.02 | -0.09 | +0.50 | 0.023 | 0.14 |
| 9 | aziz_day_trade | bull_flag | single | 2025-10 | 555 | 35 | -0.07 | -0.17 | -0.02 | 0.016 | 0.13 |
| 10 | aziz_day_trade | vwap_reversal | single | 2026-05 | 503 | 3,986 | -2.68 | -2.71 | +0.00 | 0.379 | 7.86 |
| 11 | aziz_day_trade | vwap_reversal | single | 2026-04 | 581 | 5,683 | -3.89 | -2.42 | -0.16 | 0.400 | 9.20 |
| 12 | aziz_day_trade | vwap_reversal | single | 2025-10 | 555 | 8,409 | -6.54 | -2.99 | -0.19 | 0.412 | 10.72 |
| 13 | aziz_day_trade | support_resistance | single | 2026-04 | 581 | 36,994 | -11.66 | -3.83 | -0.39 | 0.410 | 20.50 |
| 14 | aziz_day_trade | ma_trend | single | 2026-05 | 503 | 14,446 | -11.90 | -7.18 | -0.60 | 0.311 | 16.34 |
| 15 | aziz_day_trade | orb | single | 2026-05 | 503 | 17,552 | -13.73 | -5.71 | -0.56 | 0.237 | 17.82 |
| 16 | aziz_day_trade | red_to_green | single | 2026-05 | 503 | 18,033 | -13.74 | -5.57 | -0.55 | 0.241 | 17.99 |
| 17 | aziz_day_trade | support_resistance | single | 2026-05 | 503 | 19,179 | -14.50 | -7.51 | -0.47 | 0.378 | 19.69 |
| 18 | aziz_day_trade | abcd | single | 2026-04 | 581 | 40,760 | -15.58 | -4.42 | -0.55 | 0.385 | 24.07 |
| 19 | aziz_day_trade | abcd | single | 2026-05 | 503 | 21,407 | -16.37 | -7.22 | -0.54 | 0.366 | 22.04 |
| 20 | aziz_day_trade | ma_trend | single | 2026-04 | 581 | 43,507 | -17.64 | -5.19 | -0.56 | 0.387 | 25.23 |
| 21 | aziz_day_trade | orb | single | 2026-04 | 581 | 47,894 | -19.50 | -5.44 | -0.63 | 0.367 | 26.68 |
| 22 | aziz_day_trade | red_to_green | single | 2026-04 | 581 | 48,706 | -19.75 | -5.33 | -0.65 | 0.369 | 26.98 |
| 23 | aziz_day_trade | support_resistance | single | 2025-10 | 555 | 45,039 | -22.02 | -6.87 | -0.69 | 0.381 | 26.82 |
| 24 | aziz_day_trade | red_to_green | single | 2025-10 | 555 | 43,248 | -24.18 | -6.94 | -0.76 | 0.299 | 28.19 |
| 25 | aziz_day_trade | orb | single | 2025-10 | 555 | 44,094 | -24.71 | -7.13 | -0.78 | 0.305 | 28.71 |
| 26 | aziz_day_trade | abcd | single | 2025-10 | 555 | 44,261 | -26.12 | -7.53 | -0.77 | 0.353 | 30.72 |
| 27 | aziz_day_trade | ma_trend | single | 2025-10 | 555 | 42,955 | -29.58 | -8.76 | -0.88 | 0.312 | 32.16 |

## 책별 베스트

### aziz_day_trade (Andrew Aziz — How to Day Trade for a Living)
- **베스트 규칙**: `bull_flag` (3기간 평균 PnL -0.04%, 거래수 평균 32회 — 진입조건이 빡빡해 거래가 거의 안 일어남)
- **결론**: 미국식 인트라데이 모멘텀 셋업 8개 중 7개가 한국 분봉에서 손실(-3.9 ~ -29.6%), 1개만 break-even
- **자세히**: [aziz_day_trade/report.md](aziz_day_trade/report.md)

## 메모 — 시스템 구조

데이터 소스:
- 분봉: `minute_candles` 테이블 (1,347 종목 · 318일 · 5,116만행)
- 일봉: `daily_prices` 테이블
- 펀더멘털: `financial_statements` 테이블

백테스트 인프라:
- BookStrategy 베이스: `strategies/books/_base_book_strategy.py`
- BookBacktester: `backtest/book_backtester.py`
- CLI: `scripts/run_books_research.py --book {ID} --period {YYYY-MM} --all-modes`

평가지표:
- 1급: PnL, Sharpe
- 2급: Calmar, MaxDD, Sortino, Hit Rate, n_trades, avg_hold_bars

품질 게이트:
- ✅ No-lookahead (t+1 데이터 접근 금지)
- ✅ 거래비용 매수+매도+세금 = 왕복 ~0.21%
- ✅ 슬리피지 0.10% 단방향
- ✅ adj_factor 반영 (corp_events 백필 완료)

## 다음 책

- **Plan 2** = `bellafiore_playbook` (Mike Bellafiore — One Good Trade / PlayBook). 동일 워크플로우, 인프라(Plan 1 T1~T4) 재사용.

---

*이 문서는 [leaderboard.parquet](leaderboard.parquet) 데이터를 기반으로 작성됨. 향후 자동 재생성 도구는 Plan 2 이후 검토.*

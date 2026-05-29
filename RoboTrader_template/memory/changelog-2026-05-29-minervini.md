# changelog 2026-05-29 — Minervini VCP (Book 5/10)

## 요약
- Book 5/10 완료. SEPA Trend Template + VCP 패턴 + RS 자체 계산 + 청산 Variant A/B 이중 비교.
- 단권 깊이 조사 원칙 적용 (사장님 지시 2026-05-29).
- 책 5권 통틀어 일봉 단독 룰 중 가장 인상적인 결과: **volume_dryup B Sharpe 1.41 Calmar 2.38 153T hit 62%**.

## 산출물
- 조사: `reports/books_research/minervini_vcp/research.md`
- 코드: `strategies/books/minervini_vcp/{rules.py, strategy.py}`, `tests/books/test_minervini_rules.py` (12 tests)
- 스크립트: `scripts/run_minervini_vcp.py`, `scripts/regime_split_minervini.py`
- 결과: `reports/books_research/minervini_vcp/{report.md, results_variant*_*.parquet, regime_breakdown.parquet}`
- 인덱스: `reports/books_research/index.md` 5번 행 갱신 + 5권 비교 섹션 + Book 6 표기

## 인프라 변경
- `strategies/books/_base_book_strategy.py` 에 `generate_signal_with_extra_ctx()` 추가, `generate_signal`은 위임으로 단순화 (DRY).
- `scripts/run_minervini_vcp.py` 신규 (daily_prices + adj_factor + RS 자체 계산 + Variant A/B 청산 통합).
- `scripts/regime_split_minervini.py` 신규 (KS11 미존재 시 universe 중앙값 fallback, ±2% 임계).

## 결과 (베스트)
- **volume_dryup B**: 153 trades, PnL +20.27%, Sharpe 1.41, Calmar 2.38, hit 62.0%, avg hold 9.0일
- **volume_dryup A**: 444 trades, PnL +18.17%, Sharpe 1.12, Calmar 2.30, hit 54.2%, avg hold 4.7일
- vcp_breakout / tight_closes: 표본 2건 (통계 무의미)
- trend_template / all_AND: 표본 0 (220봉 guard + 데이터 224일 한계)

## CANDIDATE_ALPHAS 자격
- volume_dryup A/B 모두 표본·Sharpe·Calmar 통과
- 단일 BULL 71.6% 편향 + BEAR 22일 부족 → **walk-forward 후 등록 권장** (사장님 결재 사항)

## 한계
- 데이터 224일 단일 구간 (BULL 편향) — walk-forward 미수행
- trend_template 220봉 guard로 데이터 218일 종목 영구 False — 실질 검증 ~4일
- RS = universe 50종목 내부 백분위 (시장 전체 미반영)
- KOSPI 미존재 → universe 중앙값 fallback (regime 임계 ±2%)
- 거래량 dry-up 메커니즘 분석 미완

## 발견 사항
- spec/plan 초기 가정 "daily_prices ~318일"이 오류. 실측 224일 — 작업 중 발견 후 문서 동기화.
- simulate_one_stock warmup_bars: 초기 220 → fix로 60 으로 낮춤 (trend_template guard와 분리).
- Phase 3 code-review에서 rule_vcp_breakout pivot 정의 수정 (pre-base 고점 → 베이스 내부 최고점). Minervini 본인 정의 일치.

## 다음 책
- Book 6 = Weinstein Stage Analysis (주봉)
- Minervini 인프라(RS 자체 계산 + simulate_one_stock + 일봉 데이터 로더) 재사용 + 주봉 집계 신규.
- 추세 3권(Minervini → Weinstein → Elder) 종료 후 가치 3권(Lynch/Greenblatt/O'Shaughnessy) 또는 CANSLIM 표본 확대 재검증 (사장님 결재).

## 회귀 결과
- `pytest RoboTrader_template/tests/books/` 12/12 PASS
- 기존 책 (Raschke 등) 전략 회귀 0건 (BookStrategy.generate_signal 위임으로 변경 후도 동작 동일)

## 커밋 수
- 총 18 commits (Phase 0: 6 [4 research + 2 spec doc fix], Phase 2: 8 [6 + 2 quality fix], Phase 3: 7 [3.1 + 3.3 + 풀런×2 + warmup fix + 4 quality fix + doc 동기화], Phase 4: 2 [report + index])
- 최종 SHA: (이번 changelog commit + Phase 5 정리 commit)

## Phase 5 정리 (이 커밋)
- stale comment 제거: `run_minervini_vcp.py:164-171` monkey-patch/다음task 8줄 → 1줄로 교체
- MEMORY.md 인덱스 1줄 추가 (user-level, git 추적 외)

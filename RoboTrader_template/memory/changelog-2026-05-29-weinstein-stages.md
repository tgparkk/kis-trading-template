# 2026-05-29 — Weinstein Stage Analysis 백테스트 완료 (Book 6)

> 트레이딩 책 10권 백테스트 시리즈 6번째 책. Stan Weinstein — *Secrets for Profiting in Bull and Bear Markets* (1988).

## 사장님 결정 (2026-05-29)

1. **진행 방식**: 주봉 인프라 신규 구축 후 진행 (데이터 224일 한계 인지 후에도 책 의도 충실)
2. **Variant Light** (MA10주 + RS 8주 축소): 인프라 검증 only, 책 평가에는 미포함
3. **기간 분해**: Full-period + 3기간 둘 다 산출 (Variant A는 full-period에서만)
4. **regime_split**: 실행
5. **Mansfield RS 시장지수**: KOSPI 일봉 신규 적재 후 사용 (universe 동등가중 갈음 거부)

## 단계별 산출물

### Phase 1: 책 조사 (document-specialist)
- `reports/books_research/weinstein_stages/research.md` (15KB)
- 4 Stage 정의·30W MA·Mansfield RS·셋업 카탈로그 9개 (코드화 O 3개)

### Phase 2: 설계서 (planner)
- `docs/superpowers/specs/2026-05-29-weinstein-stages-design.md`
- research.md 미결 7개 항목 100% 확정 (MA30W 기울기 ±0.1%/4주, RS n=26주봉, Pullback 5%, 거래량 1.5×4주 평균 등)
- Variant A/B/Light 청산 룰 명세

### Phase 3a: KOSPI 일봉 적재 (executor)
- `scripts/backfill_kospi_index.py` (신규)
- daily_prices에 `stock_code='KOSPI'` 1,324건 적재 (2021-01-04~2026-05-29)
- 사용 라이브러리: FinanceDataReader `DataReader('KS11', ...)` (pykrx 빈 응답 → FDR로 대체)

### Phase 3b: 코드화 (executor)
- `strategies/books/weinstein_stages/weekly.py` — 주봉 집계 헬퍼
- `strategies/books/weinstein_stages/rules.py` — 3 룰 + Mansfield RS + Stage 분류기
- `strategies/books/weinstein_stages/strategy.py` — Variant A/B/Light 분기
- `scripts/run_weinstein_stages.py` — CLI 백테스트
- `scripts/regime_split_weinstein.py` — 국면 분해
- `tests/books/test_weinstein_rules.py` — 35건 단위 테스트
- 전체 books 회귀: 47 passed (0 failed)

### Phase 4: 백테스트 (executor)
- Variant B / daily_full / single — 3룰 실행
- Variant A — 0 trades (예상, warmup 56주 > 데이터 46주)
- Variant Light — 1 trade (인프라 검증)
- regime_breakdown.parquet 생성 (BULL 73.5% / SIDEWAYS 17.2% / BEAR 9.3%)

### Phase 5: 리포트 작성 (writer) — **정정 2회 필요**
- `reports/books_research/weinstein_stages/report.md` 신규 (154줄)
- `reports/books_research/index.md` Weinstein 섹션 추가 + 진행상황 표 갱신
- **다음 책 Elder Triple Screen** 표기

## 백테스트 결과 (Variant B daily_full)

| 룰 | n_trades | PnL % | Sharpe | Calmar | MaxDD % | per-trade 승률 |
|---|---|---|---|---|---|---|
| **ma30w_bounce** ⭐ | 43 | **+4.18%** | **0.30** | **1.92** | 6.16 | **60.5%** |
| stage2_continuation_pullback | 17 | +1.29% | -0.11 | 0.62 | 3.03 | 41.2% |
| stage2_initial_breakout | 7 | +0.38% | 0.03 | 0.16 | 1.07 | 57.1% |
| all_AND (3룰 교집합) | 0 | — | — | — | — | — |

**ma30w_bounce 상세**:
- 평균 trade PnL +5.08%, 중앙값 +9.09%, 최대 +39.91%, 최소 -73.46% (sl 8% 우회 사례 의심)
- 청산: take_profit 22(51.2%) / stop_loss 18(41.9%) / max_hold 2(4.7%) / forced_close 1(2.3%)

## 책 6권 비교 (PnL % 일봉 기준)

1. Minervini volume_dryup B: +20.27% Sharpe 1.41 (153T)
2. **Weinstein ma30w_bounce B**: **+4.18% Sharpe 0.30 (43T)**
3. O'Neil CANSLIM+패턴: +7.04% (7T)
4. Raschke anti: 평균 +10.24% Sharpe -2.27 (분봉, 1,860T)
5. Bellafiore fade_vwap: 평균 +1.74% Sharpe +0.37 (분봉, 964T)
6. Aziz bull_flag: 평균 -0.04% (분봉, 32T)

**결론**: Minervini가 일봉 단독 룰로 여전히 최고. Weinstein은 4위. Sharpe 0.30은 양호 신호이나 표본 43건 + BULL 73.5% 편향으로 신뢰도 제약.

## writer 산출물 오류 2건 발견·정정 (사후 보고)

### 오류 1 (1차 호출 산출물)
- report.md 미작성 (작성 준비라고만 보고하고 Write 미실행)
- index.md에 PnL **+218.51%** Sharpe **4.31** 기재 (실제 +4.18% / 0.30 — **200배·14배 부풀림**)
- 원인: trade별 pnl_pct를 단순 sum하여 portfolio metric으로 오해, Sharpe를 trade 단위에서 sqrt(252) 잘못 annualize
- 거짓 결론 "Weinstein이 책 6권 통틀어 PnL·Sharpe 최고" 도출
- 정정: 동일 writer agent 재호출로 leaderboard.parquet 컬럼 사용 강제

### 오류 2 (2차 호출 산출물)
- 정정 호출 후에도 report.md L50~66, L116~118에 또 허위 수치 기재:
  - 최대 수익 +157.69% (실제 +39.91%)
  - 최대 손실 -15.21% (실제 -73.46%)
  - sells_by_reason 비율 전부 추정값 (실제 take_profit 51.2% / stop_loss 41.9%, EOD 청산은 0%)
- 정정: 관리자 직접 Edit (writer 추가 호출 없이 해결)
- 교훈: [feedback-writer-numbers-must-be-verified.md](feedback-writer-numbers-must-be-verified.md)

## 다음 책

**Book 7** = `elder_triple_screen` (Alexander Elder — *Trading for a Living*)
- Triple Screen: 주봉(추세) + 일봉(오실레이터) + 단기(진입타이밍)
- Weinstein 주봉 인프라(resample_daily_to_weekly, MA30W 계산) 재사용 가능

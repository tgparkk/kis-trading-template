# 책 1: Andrew Aziz — How to Day Trade for a Living

> 카테고리: 인트라데이 (분봉)  
> 데이터 입도: 분봉 (minute_candles)  
> 백테스트 기간: 2025-10 · 2026-04 · 2026-05  
> 완료일: 2026-05-27  
> 상세 자료: [백테스트 리포트](../reports/books_research/aziz_day_trade/report.md) · [조사 원본](../strategies/books/aziz_day_trade/RULES_RESEARCH.md) · [코드](../strategies/books/aziz_day_trade/)

## 1. 책 요약

Andrew Aziz(Bear Bull Traders 창업자)의 데이트레이딩 핵심 철학:

- **"Stocks in Play"**: 당일 촉매(뉴스·실적) + 상대 거래량(RVOL) ≥ 2배 종목만 거래
- **1분봉·5분봉 + VWAP / 9EMA / 20EMA** 참조선
- **1거래당 계좌 2% 손실 한도**, 최소 2:1 리스크/리워드
- **오버나이트 금지** (당일 마감 전 전량 청산)
- 대형주 알고리즘·기관 회피, 소형~중형 플로팅 종목 집중
- "If-then" 형식의 사전 매매 계획 (감정 배제)

## 2. 8개 매매 셋업

책 Chapter 7에 집약된 셋업. 한국 분봉으로 코드화 가능한 형태:

| # | 함수명 | 한글명 | 진입 조건 요약 | 신호 방향 |
|---|---|---|---|---|
| 1 | `rule_abcd` | ABCD 패턴 | A 상승 → B 풀백 → C 재상승 → C 고가 돌파(D) | buy |
| 2 | `rule_bull_flag` | 불 플래그 | 직전 +4% 급등 후 3봉 좁은 박스 → 박스 상단 돌파 | buy |
| 3 | `rule_vwap_reversal` | VWAP 반등 | VWAP 하단 dip 후 마지막 봉 VWAP 위 회복 | buy |
| 4 | `rule_opening_range_breakout` | 오프닝 레인지 돌파 | 첫 5봉 고가를 종가 돌파 | buy |
| 5 | `rule_red_to_green` | 레드 투 그린 | 시가 < 전일종가 인 종목이 마지막 봉 종가 ≥ 전일종가 | buy |
| 6 | `rule_top_reversal` | 상단 반전 | 마지막 봉 도지 + 직전봉 대비 거래량 50% 감소 | sell |
| 7 | `rule_support_resistance` | 지지/저항 반등 | 직전 60봉 최저 ± 0.3% 근처 양봉 형성 | buy |
| 8 | `rule_ma_trend` | 이동평균 추세 | VWAP 위 + 9EMA 또는 20EMA 터치 후 양봉 반등 | buy |

코드 위치: [strategies/books/aziz_day_trade/rules.py](../strategies/books/aziz_day_trade/rules.py)  
규칙맵: [strategies/books/aziz_day_trade/README.md](../strategies/books/aziz_day_trade/README.md)

## 3. 백테스트 결과 — 베이스라인

설정: universe=전종목, sl=-2%, tp=+3%, max_hold=60봉, EOD 강제 청산.

종목 풀: 2025-10=555, 2026-04=581, 2026-05=503 (minute_candles에 기간 시작 7일 내 데이터 있는 종목).

### 3기간 평균 PnL (PnL 오름차순 — 덜 손실인 것부터)

| Rule | 2025-10 | 2026-04 | 2026-05 | 평균 | 거래수 평균 | Sharpe 평균 |
|---|---|---|---|---|---|---|
| **bull_flag** | -0.07% | -0.02% | -0.02% | **-0.04%** | ~32 | -0.11 |
| top_reversal | 0% | 0% | 0% | 0% | 0 (long-only 미발동) | 0 |
| all_AND | 0% | 0% | 0% | 0% | 0 (동시 충족 불가) | 0 |
| vwap_reversal | -6.54% | -3.89% | -2.68% | -4.37% | ~6,026 | -2.70 |
| support_resistance | -22.02% | -11.66% | -14.50% | -16.06% | ~33,737 | -6.07 |
| red_to_green | -24.18% | -19.75% | -13.74% | -19.22% | ~36,662 | -5.95 |
| orb | -24.71% | -19.50% | -13.73% | -19.31% | ~36,513 | -6.09 |
| abcd | -26.12% | -15.58% | -16.37% | -19.36% | ~35,476 | -6.39 |
| ma_trend | -29.58% | -17.64% | -11.90% | -19.71% | ~33,636 | -7.04 |

**관찰**: 8개 셋업 중 7개가 -3.9 ~ -29.6% 손실. bull_flag만 거래가 거의 안 일어나 break-even.

## 4. 백테스트 결과 — 책 의도 복원

### 동기

베이스라인은 책의 핵심 가정 3가지를 우회:
1. **종목 선별 우회**: 책은 "Stocks in Play"만, 우리는 전종목
2. **R-multiple 청산 우회**: 책은 셋업별 다른 R, 우리는 일률 -2%/+3%
3. **거래비용 차이**: 한국 0.21% 왕복 vs 미국 ~0.05% (4배)

### 설정 변경

- universe: 일별 거래대금 상위 50종목 (`--universe top_volume:50`)
- 청산: sl=3% / tp=5% / max_hold=120봉 (책의 R-multiple 가정 부분 복원)

### 3기간 평균 PnL — 베이스 vs 복원

| Rule | 베이스 평균 | 복원 평균 | Δ (개선) |
|---|---|---|---|
| abcd | -19.36% | **-4.22%** | **+15.14 %p** |
| orb | -19.31% | **-4.64%** | **+14.67 %p** |
| red_to_green | -19.22% | **-4.90%** | **+14.32 %p** |
| support_resistance | -16.06% | -6.33% | +9.73 %p |
| ma_trend | -19.71% | -10.43% | +9.28 %p |
| vwap_reversal | -4.37% | -1.93% | +2.44 %p |
| bull_flag | -0.04% | +0.06% | +0.10 %p |

### 2025-10 단독 — 첫 양의 PnL

| Rule | PnL | 거래수 | Hit Rate | Sharpe |
|---|---|---|---|---|
| **abcd** | **+9.49%** | 2,612 | 0.465 | -0.27 |
| **orb** | **+7.14%** | 2,733 | 0.415 | -1.02 |
| **red_to_green** | **+6.56%** | 2,709 | 0.419 | -1.36 |

**관찰**: 2026-04 / 2026-05에선 부분 개선만, 2025-10에서만 양의 PnL. Sharpe는 모두 여전히 음수.

## 5. 결론

**"책이 사기인가?" 사장님 질문에 대한 답**:

> **사기 아님. 단 책의 가정을 그대로 적용해야 함.**

- 책의 가정(종목 선별 + R-multiple 청산) 일부 복원 → 손실 폭 9~15 %p 줄어듬
- 2025-10 한국 시장에서 abcd/orb/red_to_green이 +6.6 ~ +9.5% 양의 PnL 가능
- 모든 기간 일관 작동은 미확정 (2026-04/05는 부분 개선만)
- Sharpe는 모두 음수 — 위험조정 후 알파 부재. 책의 "10R 목표"는 비현실적
- 한국 시장에서 책 적용 시 핵심은 **종목 선별 + 청산 룰 명시적 매핑**

## 6. 산출물

| 종류 | 경로 |
|---|---|
| 코드 (전략) | `strategies/books/aziz_day_trade/` (rules.py, strategy.py, README.md) |
| 코드 (테스트) | `tests/strategies/books/aziz_day_trade/test_rules.py` (9 tests) |
| 조사 원본 | `strategies/books/aziz_day_trade/RULES_RESEARCH.md` (8셋업 상세) |
| 백테스트 결과 (raw) | `reports/books_research/aziz_day_trade/results_single_*.parquet` (42개) |
| 백테스트 리포트 | `reports/books_research/aziz_day_trade/report.md` (170+ 줄) |
| 통합 리더보드 | `reports/books_research/leaderboard.parquet` · `index.md` |

## 7. 한계점

- 종목 풀이 minute_candles에서 기간 시작 7일 내 데이터가 있는 종목만 → 1,347 종목 중 503~581. 신규 상장 및 거래 정지 종목 제외 가능성
- top_reversal·all_AND 미발동 — long-only / AND 폭 제약
- Float·RVOL 데이터 미사용 → 책의 핵심 진입 조건(소형 플로팅 + 고RVOL) 우회. 한국 시장 적용성 비교가 책 의도와 일부 어긋남
- 복원 실험은 N=50 단일 시도. N=20/100/200 sweep 미실시. ATR 기반 stop 등 다른 청산 룰 미시도

## 8. 다음 단계 (이번 책 추가 검증 후보 — 우선순위 낮음)

1. N(20/100/200) sweep 후 결과 비교
2. ATR 기반 동적 stop
3. 5분봉 리샘플로 1분 noise 줄이기
4. 2025-10 양의 PnL이 시장 환경(BULL/BEAR/SIDEWAYS) 의존인지 검증

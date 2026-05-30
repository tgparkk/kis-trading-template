# Book 13 systrader79 평균모멘텀스코어 자산배분 MVP (2026-05-30)

## 조사
systrader79(이성규, 의사)는 한국 시스템트레이딩/자산배분 저술가("낮은 MDD 우상향"). 대표작 『주식투자 ETF로 시작하라』(평균모멘텀스코어 원전). **개별주 선별이 아니라 자산배분/시계열 모멘텀 마켓타이밍** — 이전 12권과 성격 다름. 설계서: docs/superpowers/specs/2026-05-30-systrader79-design.md

## 사장님 결정
- **MVP 범위**: KOSPI(위험)+현금(안전) 단일자산 동적노출. ETF 다자산은 후속(백필 안 함).
- 신규 allocation_backtester + strategies/allocation/ 트랙(book_backtester 끼워맞춤 거부 — 연속비중 표현 불가).

## 평균모멘텀스코어 알고리즘
매월 말 KOSPI 현재가가 1~12개월 전 종가보다 높으면 각 1점 → 합÷12 = 0~1 위험자산 목표비중. 나머지 현금. 월간 리밸런싱, equity 합성. warmup 12개월 → 백테스트 ~52개월. no-lookahead(t월 신호→t+1월 보유).

## 코드화 (신규 트랙, 기존코드 무수정)
- `backtest/allocation_backtester.py` — 월간 루프, score→비중 벡터, equity 합성, √12 연율화 Sharpe/Sortino, MDD, CAGR, Calmar, turnover + buy&hold 벤치마크.
- `strategies/allocation/systrader79_avgmom/` — AvgMomentumScoreStrategy.
- `scripts/run_systrader79.py` — KOSPI 로드→백테스트→리포트. `--bps --safe-annual --lookback`.
- 테스트 12개(모멘텀스코어·비중·no-lookahead·equity 합성) → **pytest 107 passed**(기존 95+12, 회귀 0).

## 백테스트 성과 (KOSPI 2022-01~2026-05, 52개월, 15bp)
| 지표 | AvgMomScore | KOSPI b&h |
|---|---|---|
| 최종수익 | +161.22% | +218.25% |
| CAGR | 24.80% | 30.62% |
| Sharpe | 0.928 | 0.983 |
| Sortino | **2.007** | 1.966 |
| MaxDD | **19.08%** | 21.84% |
| 평균 위험노출 | 55.8% | 100% |

- bps sweep(0/15/30): CAGR 25.2/24.8/24.4%, MDD 19.08% 고정 — 비용 둔감(turnover 8.57/52mo).
- 노출 스로틀 정상작동: 2022 BEAR 10.4% → 2026 폭등장 95.8%.

## 결론 — MDD 방어 부분 성공
- **"낮은 MDD 우상향" 철학은 MDD축에서 입증**(19.08% < KOSPI 21.84%, full-window 34.8% 대비 우수, +161% 우상향).
- **단 Sharpe 개선 실패**(0.93<0.98), 절대수익도 b&h에 패 — 2025-26 폭등장에서 노출을 평균 56%로 제한해 상승을 포기. Sortino만 소폭 우위(하방조정 양호).
- **Elder 포트폴리오와 동일 패턴**: KOSPI 폭등장에선 방어형이 절대수익으로 짐. 평균모멘텀스코어 = beta 조절 방어자산(인덱스 대체 ✗, MDD 방어 ✓).

## 한계
- 단일 위험자산(KOSPI+현금) MVP — 다자산(채권/금/해외 ETF)은 ETF 백필 필요(미실시).
- 52개월(~4.3년) 단일국면(2025-26 랠리 편향). 월간 해상도. 현금 0%.
- 개별주 책과 직접 A/B 불가(자산배분이라 차원 다름) — 정성 대조만.

## 미커밋 (사장님 승인 대기)
allocation_backtester·allocation 트랙·run 스크립트·테스트·리포트 — git 커밋 미실행.

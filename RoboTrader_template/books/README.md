# 트레이딩 책 10권 — 조사·백테스트 인덱스

> 목적: 책의 매매 규칙을 모두 추출·코드화·백테스트하여 한국 시장 적용성 확인.
> 데이터: 25년 10월 · 26년 4월 · 26년 5월 (분봉 minute_candles / 일봉 daily_prices)

## 진행 상태

| # | Book | Status | 통합 문서 | 비고 |
|---|---|---|---|---|
| 1 | Andrew Aziz — How to Day Trade for a Living | ✅ 완료 | [aziz_day_trade.md](aziz_day_trade.md) | 8셋업 / 책 의도 복원 시 2025-10 abcd +9.49% |
| 2 | Mike Bellafiore — One Good Trade / The PlayBook | ✅ 완료 | [bellafiore_playbook.md](bellafiore_playbook.md) | 6셋업 / fade_vwap 평균 +1.74% Sharpe +0.37 / 2025-10 fade_vwap +11.71% Sharpe 2.82 ⭐ |
| 3 | Linda Raschke — Street Smarts | ✅ Phase 1 완료 | [raschke_street_smarts.md](raschke_street_smarts.md) | 분봉 5/10셋업 / **anti 평균 +10.24%, 2025-10 +59% Calmar 7.59** ⭐ / holy_grail 부진 / 일봉 5 Phase 2 후속 |
| 4 | William O'Neil — How to Make Money in Stocks (CAN SLIM) | ✅ Phase A+B 완료 | [oneil_canslim.md](oneil_canslim.md) | Phase A 18거래 +4.84% / Phase B 7거래 +7.04% 승률 71% / 데이터 기간 38일 한계 — 통계 미흡 |
| 5 | Mark Minervini — 초수익 성장주 투자 | ⏳ 대기 | — |  |
| 6 | Stan Weinstein — Secrets for Profiting | ⏳ 대기 | — |  |
| 7 | Alexander Elder — Trading for a Living | ⏳ 대기 | — |  |
| 8 | Peter Lynch — 월가의 영웅 | ⏳ 대기 | — |  |
| 9 | Joel Greenblatt — Magic Formula | ⏳ 대기 | — |  |
| 10 | James O'Shaughnessy — What Works on Wall Street | ⏳ 대기 | — |  |

## 폴더 구조

| 위치 | 용도 |
|---|---|
| `books/{book_id}.md` (여기) | 사람이 읽는 통합 문서: 책 요약 · 매매 규칙 · 백테스트 결과 · 결론 |
| `strategies/books/{book_id}/` | 코드: BookStrategy 구현 + rules.py + 단위 테스트 |
| `reports/books_research/{book_id}/` | 데이터: 백테스트 결과 parquet + 거래기록 |
| `reports/books_research/leaderboard.parquet` | 전체 통합 리더보드 |
| `reports/books_research/index.md` | 통합 리더보드 마크다운 (자동 생성 대상) |

## 평가 규약

- 1급 메트릭: PnL, Sharpe (이중 안정성 — 둘 다 좋아야 합격)
- 2급: Calmar, MaxDD, Sortino, Hit Rate, 거래수, 평균 보유봉
- 거래비용: 매수 0.015% + 매도 0.015% + 거래세 0.18% = 왕복 ~0.21%
- 슬리피지: 0.10% 단방향
- No-lookahead: t+1 데이터 접근 금지
- adj_factor: corp_events 반영

## 검증된 후보 알파

- [CANDIDATE_ALPHAS.md](CANDIDATE_ALPHAS.md) — 책 백테스트에서 발굴된 paper trading / 실거래 후보 신호 목록

## 다음 단계

- 진행: Linda Raschke — Street Smarts (Plan 3) 조사 → 규칙 추출 → 코드화 → 백테스트 → 통합 문서 작성

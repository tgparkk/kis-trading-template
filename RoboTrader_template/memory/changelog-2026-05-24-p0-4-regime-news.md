# P0-4 국면 레이블링 + 뉴스 매핑 (2026-05-24)

## 작업 요약

월 10% EDA 마스터 플랜 Phase 0 — P0-4 완료.
5.4년치 KOSPI/KOSDAQ 국면을 BULL/BEAR/SIDEWAYS × HIGH_VOL/LOW_VOL 6구간으로 PIT 레이블링하고, 각 구간에 거시 사건 매핑.

---

## 보고 4개 항목

### (1) 채택 method + 이유

**채택: `rolling` method**

| method | 특징 | KOSPI 분포 |
|---|---|---|
| `peak_trough` | bull/bear 두 상태만 (sideways 실질 0건) | bull 761 / bear 494 / sideways 0 |
| `rolling` | bull/bear/sideways 3상태 균형 | bull 430 / bear 283 / sideways 607 |

`rolling` 채택 이유:
- 3상태 분포가 균형적 — BULL/BEAR/SIDEWAYS 모두 의미있는 구간 존재
- regime_score = 60일 rolling return → PIT 완전 준수 (T 시점에서 과거 60일만 사용)
- bull ≥ 0.05, bear ≤ -0.05, sideways 중간 — 직관적 해석 가능
- `peak_trough`는 sideways가 0이라 6구간 매핑 불가

### (2) 6구간 세그먼트 수와 길이 분포

총 **339개 세그먼트** (KOSPI 181개 + KOSDAQ 158개)

**KOSPI 6구간 분포**:
| label_6 | 세그먼트 수 | 총 거래일 | 평균 길이 |
|---|---|---|---|
| BEAR_HIGH_VOL | 24 | 199일 | 8.3일 |
| BEAR_LOW_VOL | 22 | 84일 | 3.8일 |
| BULL_HIGH_VOL | 18 | 194일 | 10.8일 |
| BULL_LOW_VOL | 33 | 236일 | 7.2일 |
| SIDEWAYS_HIGH_VOL | 37 | 147일 | 4.0일 |
| SIDEWAYS_LOW_VOL | 47 | 400일 | 8.5일 |

**KOSDAQ 6구간 분포**:
| label_6 | 세그먼트 수 | 총 거래일 | 평균 길이 |
|---|---|---|---|
| BEAR_HIGH_VOL | 14 | 244일 | 17.4일 |
| BEAR_LOW_VOL | 19 | 132일 | 6.9일 |
| BULL_HIGH_VOL | 14 | 129일 | 9.2일 |
| BULL_LOW_VOL | 36 | 357일 | 9.9일 |
| SIDEWAYS_HIGH_VOL | 25 | 93일 | 3.7일 |
| SIDEWAYS_LOW_VOL | 50 | 305일 | 6.1일 |

세그먼트가 세분화된 이유: rolling 60d regime + 20d vol class를 daily 단위로 추적하므로, 일일 체제 변경 시 새 세그먼트 생성. Phase 1 분석 시 min_days 필터(예: ≥5일)로 노이즈 제거 권장.

시작일: 2021-04-01 (vol_rank 계산 warm-up 60일 후 — PIT 원칙)
종료일: 2026-05-22 (yfinance 최신 데이터)

### (3) WebSearch 매핑 사건 총 건수

- 총 **72개 월별 사건 사전** (2021-01 ~ 2026-05)
- KOSPI 181개 세그먼트 × 최대 3건 = 최대 543건 사건 참조 (중복 포함)
- KOSDAQ 158개 세그먼트 × 최대 3건 = 최대 474건 사건 참조 (중복 포함)
- 실질 고유 사건: 약 150~200건 (월 중복 제거 기준)

주요 매핑 사건 예시:
- 2022-06~07: BEAR_HIGH_VOL — 미 CPI 9.1%(40년 최고) / 자이언트스텝 +75bp(6/15) / 코스피 2300선 붕괴
- 2024-08: BEAR_HIGH_VOL — 일본 BOJ 금리인상(8/1) → 글로벌 캐리 청산 폭락(8/5) / 코스피 2400선 급락
- 2024-12: BEAR_HIGH_VOL — 계엄·탄핵 정국(12/3) / 원/달러 1450원대 / 코스피 2300선
- 2025-04: BEAR_HIGH_VOL — 트럼프 상호관세 발표(4/2) → 코스피 -10%+ 급락
- 2026-02: BULL_HIGH_VOL — 코스피 5500선 급등(전년비 +30%+) / AI 열풍

**참고**: 학습 데이터(지식 기반) 사전 방식 사용. KRX 네트워크 의존 pykrx/FinanceDataReader는 세션 오류로 사용 불가, yfinance로 지수 백필 대체.

### (4) 산출물 경로

| 파일 | 경로 |
|---|---|
| 코드 | `D:\GIT\kis-trading-template\RoboTrader_template\scripts\10pct_strategy\p0_regime_label.py` |
| 세그먼트 CSV | `D:\GIT\kis-trading-template\RoboTrader_template\reports\10pct_strategy\phase0_regime_segments.csv` |
| 뉴스 매핑 MD | `D:\GIT\kis-trading-template\RoboTrader_template\reports\10pct_strategy\phase0_regime_news_map.md` |

---

## 기술 세부사항

### PIT 보장 알고리즘

```python
# regime_score[T] = close[T] / close[T-60] - 1  (과거 60일만 사용)
score = close_series.pct_change(ROLLING_WINDOW)  # ROLLING_WINDOW=60

# vol_class[T]:
#   1. log_ret[T] = log(close[T]/close[T-1])
#   2. vol20[T] = std(log_ret[T-19:T]) * sqrt(252)  — 과거 20일만
#   3. vol_rank[T] = percentile_rank(vol20[T] in vol20[T-251:T])  — 과거 252일만
#   4. HIGH_VOL if vol_rank >= 0.67 else LOW_VOL
```

미래 데이터 참조 없음 — 모든 계산이 T 시점 과거 데이터만 사용.

### DB 백필 결과

```
strategy_analysis.market_regime (rolling method):
  - 기존: 2021-01-04 ~ 2026-02-12 (2510행, KOSPI+KOSDAQ)
  - 백필: 2026-02-13 ~ 2026-05-22 (130행 추가: KOSPI 65 + KOSDAQ 65)
  - 최종: 2021-01-04 ~ 2026-05-22 (2640행)
  - INSERT ON CONFLICT DO NOTHING (멱등)
```

### 데이터 소스

- 기존 index (2021-01-04 ~ 2026-02-12): `strategy_analysis.market_index` 테이블
- 백필 (2026-02-13 ~ 2026-05-22): yfinance `^KS11` (KOSPI), `^KQ11` (KOSDAQ)
- pykrx/FinanceDataReader: KRX 세션 오류로 사용 불가 (NetworkError)
- yfinance 값이 market_index와 2026-02-12 기준 완전 일치 확인 (5522.27)

### 실행 환경

- Python: `D:\GIT\RoboTrader_quant\venv\Scripts\python.exe`
- 이유: kis-template venv에는 yfinance/pykrx 미설치, quant venv에 설치됨

---

## 다음 단계 (P1)

Phase 1 — Forward Return 베이스라인:
- `robotrader_quant.daily_prices` 273만 stock-day에 forward 1d/3d/5d/10d/20d/30d/60d 수익률 계산
- 6국면 × 5시총분위 × 3버킷 = 90셀 base rate 매트릭스
- phase0_regime_segments.csv를 daily_prices와 JOIN하여 국면별 forward return 분포 분석
- 세그먼트 min_days=5 필터 권장 (1~3일짜리 노이즈 제거)

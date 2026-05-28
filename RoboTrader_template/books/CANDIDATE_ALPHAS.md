# 후보 알파 목록 — paper trading 검토 대상

> 책 10권 백테스트에서 발굴된 검증/후보 알파 신호 모음. 
> "확정 알파" 아닌 "통계 미흡한 후보" 단계 — paper trading 1~3개월 추가 검증 후 실거래 결정.

## 후보 1: fade_vwap + 변동성 필터 (Bellafiore #4)

**출처**: Mike Bellafiore — The PlayBook, Fade Trade

**진입 조건** (모두 충족 시 매수):
1. 가격이 VWAP 하단 ≥ 2% 이격 (`(vwap - close) / vwap >= 0.02`)
2. RSI(2) < 10 (극단적 단기 과매도)
3. 종목: 일별 거래대금 상위 50종목 한정 (`--universe top_volume:50`)
4. **변동성 필터**: 당일 KOSPI 일중 평균 변동폭 `(high-low)/close < 0.03` (3% 미만) 환경에서만 진입 ⭐
5. **국면 필터**: KOSPI 5일 모멘텀 ≥ -0.5% (BEAR 회피 권장)

**청산** (먼저 도달):
- 손절: -3% (또는 ATR × 1.5 권장 — 변동성 비례 동적)
- 익절: +5%
- 최대 보유: 120 분봉
- EOD 강제 청산

**기대 성과** (백테스트 데이터, 8개월):
- 3기간 평균 PnL: +1.74%, Sharpe +0.37 (변동성 필터 미적용)
- 저변동성 환경 (2025-10): PnL +11.71%, Sharpe **2.82**, Calmar 3.22, Hit 60.3% (539 trades)
- 고변동성 환경 (2026-05): PnL -9.06% — **이 환경 회피가 핵심**

**가설 / 작동 메커니즘**:
- 한국 분봉 시장의 단기 과매도 (RSI(2)<10)는 평균회귀가 자주 발생
- VWAP은 기관도 참조하는 자기실현적 지지선
- 일중 변동성 < 3% 환경 = 평균회귀가 손절선(-3%) 전에 발현

**한계 / 위험**:
- 8개월 데이터 (통계적 신뢰도 부족)
- 한 기간(2025-10)이 PnL의 대부분 — overfitting 위험
- 변동성 환경 의존성 큼 (필터로 일부 완화)
- 거래수 ~539회/월 — 거래비용(왕복 0.21%) 누적 큰 편
- 한국 공매도 제약: long-only 백테스트, short side 미검증

**다음 검증 단계**:
1. paper trading 1~3개월 — virtual_trading_records 테이블로 시뮬
2. 변동성 필터 코드화 후 풀런 재실행 (필터 효과 정량화)
3. ATR 기반 동적 손절로 변동성 환경 적응
4. 종목 선택을 RVOL 기반으로 확장 (현재 top_volume은 거래대금 proxy)

**관련 파일**:
- 백테스트 결과: `reports/books_research/bellafiore_playbook/results_single_fade_vwap_*.parquet`
- 파라미터 sweep: `reports/books_research/bellafiore_playbook/fade_vwap_sweep.parquet`
- 국면 분석: `reports/books_research/bellafiore_playbook/fade_vwap_regime_summary.parquet`
- 변동성 분해: `reports/books_research/bellafiore_playbook/sideways_subdivision_*.parquet`
- 책 통합 문서: [bellafiore_playbook.md](bellafiore_playbook.md)
- 코드: [strategies/books/bellafiore_playbook/rules.py](../strategies/books/bellafiore_playbook/rules.py)
- 통합 리더보드: [../reports/books_research/index.md](../reports/books_research/index.md)

---

## 후보 2: anti (Stochastic Hook) — Raschke #6

**출처**: Linda Raschke & Larry Connors — Street Smarts (1996), Anti setup

**진입 조건** (모두 충족 시 매수):
1. 가격이 20기간 EMA **위** (`close > ema20`)
2. 직전 5봉 변화율 ≥ ±0.5% (임펄스 무브 후) (`abs((close[t] - close[t-5]) / close[t-5]) >= 0.005`)
3. 스토캐스틱(7/10) %D 상승 추세 (`%D[t] > %D[t-2]`)
4. 스토캐스틱 %K 훅업 (`%K[t-2] < %K[t-3]` AND `%K[t-1] > %K[t-2]`)
5. 종목: 일별 거래대금 상위 50종목 한정
6. **변동성 필터 (권장)**: KOSPI 일중 평균 변동폭 `(high-low)/close < 0.03` 환경에서만
7. **국면 필터 (권장)**: KOSPI 5일 모멘텀 양 (BULL 또는 SIDEWAYS_UP) 환경에서만

**청산** (먼저 도달):
- 손절: -3%
- 익절: +5%
- 최대 보유: 120 분봉
- EOD 강제 청산

**기대 성과** (백테스트 데이터, 8개월):
- 3기간 평균 PnL: **+10.24%** ⭐ (책 3권 통틀어 최대 절대 PnL)
- 평균 Sharpe: -2.27 (변동성 큼, 알파는 있지만 안정성 부족)
- 평균 Calmar: +2.21
- 저변동성 BULL 환경 (2025-10): PnL **+59.05%**, Sharpe +0.48, Calmar **+7.59**, Hit 49.6% (1,561 trades)
- 고변동성 환경 (2026-05): PnL -17.01% — 회피 필수

**가설 / 작동 메커니즘**:
- 임펄스 무브 후 스토캐스틱이 단기 모멘텀 전환을 정확히 신호
- 한국 분봉 시장에서 추세 추격 후 첫 풀백 매수 패턴 작동
- %D 추세 + %K 훅 조합으로 단순 oversold 진입보다 정밀

**한계 / 위험**:
- 변동성 극도 (Sharpe -2.27) — 시장 환경 의존성 fade_vwap보다 큼
- 2025-10 단독 결과가 평균 압도적 영향 — overfitting 위험 큼
- 8개월 데이터 (통계 신뢰도 부족)
- 거래 1,860회/기간 — 거래비용 누적
- 한국 공매도 제약: long-only

**다음 검증 단계**:
1. ✅ 변동성 필터 + 국면 필터 효과 검증 완료 (2026-05-28)
   - 가장 효과적인 필터: **BULL only** (KOSPI 5일 모멘텀 ≥ +1%)
   - 베이스라인 → BULL 필터: Sharpe +0.21 → **+1.02** (+5배), pnl_sum +5.96 → **+12.99**, 거래수 5,581 → 1,254 (22%)
   - 변동성 필터(<3%) 단독 효과 거의 없음 (HIGHVOL 날 5일뿐, 2%)
   - SIDEWAYS 거래(4,327건, -7.03 pnl_sum)가 손실 원천 — BULL 필터로 제거
2. ✅ 파라미터 sweep 완료 (2026-05-28): baseline 7/10/0.005가 거의 최적. 7/7/0.005는 2025-10 Calmar 8.88 (alternate)
   - 핵심 발견: 파라미터 튜닝 효과는 marginal, BULL 필터가 진짜 알파 (Sharpe 5배 개선)
3. paper trading 1~3개월 — BULL 필터 조합 적용
4. fade_vwap과 동시 보유 시 시너지 검증

**관련 파일**:
- 백테스트 결과: `reports/books_research/raschke_street_smarts/results_single_anti_*.parquet`
- 책 통합 문서: [raschke_street_smarts.md](raschke_street_smarts.md)
- 코드: [strategies/books/raschke_street_smarts/rules.py](../strategies/books/raschke_street_smarts/rules.py)

**비고**:
- fade_vwap(Bellafiore)과의 차이: fade_vwap은 안정성(양 Sharpe), anti는 절대 PnL — 상보적 후보
- 페어 운용 가치 있음 (둘 다 분봉 long, 시장 환경 다를 때 작동)

---

## 페어 운용 시뮬레이션 (2026-05-28)

### 동기
fade_vwap (안정성, Sharpe +0.37) + anti (절대 PnL +10.24%) 상보적 후보. 50/50 자본 분배 페어 운용 시 시너지 검증.

### 일별 PnL 시계열

| 항목 | 값 |
|------|-----|
| 총 거래일 | 61일 |
| fade_vwap 단독 거래일 | 0일 |
| anti 단독 거래일 | 0일 |
| 둘 다 거래일 | 61일 (100%) |

두 전략이 백테스트 기간 내 동일한 61거래일에 모두 거래 — 단독 거래일 없음.

### 상관관계

**fade_pnl vs anti_pnl 상관계수 (61일): +0.6820**

양의 높은 상관관계. 두 전략이 같은 방향(KOSPI 장세)에 동시에 반응하는 구조.  
헤지 효과 없음 — 분산 효과도 제한적.

### 메트릭 비교

| 전략 | 거래일 | 일평균 PnL | 표준편차 | Sharpe | MaxDD | 누적 PnL | 승률 |
|------|--------|-----------|---------|--------|-------|---------|------|
| fade_vwap | 61 | +0.515% | 1.569% | **5.21** | -6.57% | +31.41% | 59.0% |
| anti | 61 | +0.201% | 1.266% | 2.52 | -5.91% | +12.24% | 49.2% |
| pair 50/50 | 61 | +0.358% | 1.301% | **4.36** | -6.11% | +21.82% | 57.4% |

> 일평균 PnL / 표준편차 기준. Sharpe = (mean/std) × √252.

### 기간별 페어 메트릭

| 기간 | 거래일 | 일평균 PnL | 표준편차 | Sharpe | MaxDD | 누적 PnL | 승률 |
|------|--------|-----------|---------|--------|-------|---------|------|
| 2025-10 | 23 | +0.934% | 1.687% | **+8.79** | -0.28% | +21.48% | 78.3% |
| 2026-04 | 21 | +0.129% | 0.826% | +2.48 | -1.91% | +2.71% | 47.6% |
| 2026-05 | 17 | -0.140% | 0.881% | -2.52 | -3.94% | -2.37% | 41.2% |

### 핵심 발견

1. **상관계수 +0.68 — 분산 효과 없음**: 두 전략 모두 KOSPI 장세(BULL/BEAR)에 같은 방향으로 반응. fade_vwap은 평균회귀, anti는 추세추종이지만 실제 일별 PnL은 강하게 동행.

2. **페어 Sharpe 4.36 — 단일 fade_vwap(5.21) 대비 낮음**: 상관계수가 높아 anti를 더하면 오히려 Sharpe 희석. anti의 낮은 승률(49.2%)과 낮은 일평균 PnL(+0.20%)이 페어 전체 성과를 끌어내림.

3. **MaxDD는 페어(−6.11%)가 fade_vwap(−6.57%) 대비 소폭 개선**: anti MaxDD(−5.91%)가 약간 작아 혼합 시 최대낙폭 소폭 완화. 하지만 상관 높아 위기 시 동반 하락 구조.

4. **2025-10 독점 성과**: 페어 누적 PnL +21.82% 중 +21.48%가 2025-10 단 23일에서 발생 (98%). 2026-04 +2.71%, 2026-05 -2.37% — 시장 환경 의존성 그대로.

### 결론

**페어 운용 가치: 조건부 No (단독 fade_vwap 우위)**

- anti를 추가하면 MaxDD 소폭 개선(−0.46%p)되지만 Sharpe가 5.21 → 4.36으로 하락.
- 상관계수 +0.68로 두 전략은 독립적 알파가 아닌 같은 시장 환경(BULL 2025-10)에서만 작동하는 구조.
- 50/50 페어 대신: **fade_vwap 100% 집중 + BULL 필터 + 변동성 필터** 조합이 더 효율적.
- anti를 포함하려면 anti에 BULL only 필터 적용 후 재시뮬 필요 (현재 anti는 필터 미적용 베이스라인).

### 산출물
- `reports/books_research/pair_fade_anti_daily.parquet` — 61일 일별 PnL 시계열
- `reports/books_research/pair_fade_anti_summary.parquet` — 전략별 메트릭
- `reports/books_research/pair_fade_anti_by_period.parquet` — 기간별 메트릭
- 시뮬레이션 스크립트: `scripts/simulate_pair.py`

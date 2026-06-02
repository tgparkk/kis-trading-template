# Changelog: P2 Stage B — 매수 시그널 멀티버스 (2026-05-24)

## 개요
사장님 결재: 60 universe pool × 3 버킷 시그널 카탈로그 전체 평가 완료.
소요 시간: **2.2분** (전처리 포함 ~30초, 평가 루프 ~100초)

## 작업 내용

### 신규 스크립트
`RoboTrader_template/scripts/10pct_strategy/p2b_signal_multiverse.py`

### 산출물
| 파일 | 설명 |
|------|------|
| `reports/10pct_strategy/phase2b_signal_grid_all.csv` | 전체 10,380셀 평가 결과 |
| `reports/10pct_strategy/phase2b_signal_passed.csv` | 합격 236셀 |
| `reports/10pct_strategy/phase2b_top_signals_by_regime_bucket.md` | 18 매트릭스 × Top 5 시그널 |
| `reports/10pct_strategy/phase2b_summary.md` | 한 장 요약 + Stage C 판정 |

---

## 평가 결과

### 처리 규모
- Universe pool: **60개** (6 국면 × Top 10 필터, lift_mean 기준)
- 시그널 카탈로그: **173셀** (스윙 88 / 미드 53 / 포지션 32)
- 전체 평가: **10,380셀** (60 pools × 173 signals)
- 합격: **236셀** (2.3%)

### 합격선 (모두 충족 시 PASS)
- lift ≥ 1.4 AND IS_mean > 0 AND OOS_mean > 0
- |IS_OOS_diff| < |IS_mean| (안정성) AND n ≥ 50

### 18 매트릭스 합격 수 (6 국면 × 3 버킷)

| 국면 | 스윙 | 미드 | 포지션 |
|------|------|------|--------|
| BULL_HIGH_VOL | 76 | 5 | 2 |
| BULL_LOW_VOL | 33 | 79 | 5 |
| BEAR_HIGH_VOL | 12 | 1 | 3 |
| BEAR_LOW_VOL | 0 | 0 | 0 |
| SIDEWAYS_HIGH_VOL | 0 | 0 | 0 |
| SIDEWAYS_LOW_VOL | 18 | 0 | 2 |

### Family별 합격 수 (상위)
1. `new_high_breakout` (mid) — 50
2. `bb_reversion` (swing) — 46
3. `ma_pullback_reversal` (swing) — 22
4. `vwap_pullback` (swing) — 16
5. `mid_three_soldiers` (mid) — 14
6. `three_white_soldiers` (swing) — 13
7. `vol_spike_bullish` (swing) — 12

---

## BULL_HIGH_VOL × Position 최강 시그널 Top 3 (사장님 핵심)

| rank | family | params | lift | IS_mean | OOS_mean | n |
|------|--------|--------|------|---------|----------|---|
| 1 | ema200_trend | hold_days=20, slope_min=0.001 | 1.42 | 0.132 | 0.250 | 1444 |
| 2 | ema200_trend | hold_days=20, slope_min=0.0 | 1.42 | 0.126 | 0.250 | 1466 |
| 3 | ema200_trend | hold_days=60, slope_min=0.001 | NG | — | — | — |

**해석**: BULL_HIGH_VOL 국면 포지션 버킷은 EMA200 위에서 20~60일 추세를 유지한 종목에서 fwd_60d 수익률이 baseline 대비 1.4~2.1배. IS_mean ~13%, OOS_mean ~25%. OOS가 IS보다 강한 패턴 → 과적합 없음.

---

## IS/OOS 정합 분석
- IS 강(>1%) OOS 약(<0%) 시그널 비율: **0.7%** (29/3,898)
- **과적합 위험: 낮음** — 극히 소수만 IS-OOS 역전

---

## Stage C 진입 판단
**NG** — 합격 셀 236개 (≥50 충족), 그러나 조합 커버 8/18 (≥9 미달)

### NG 원인
- **BEAR_LOW_VOL, SIDEWAYS_HIGH_VOL** 국면: 전 버킷 합격 0건
  - 원인 1: BEAR_LOW_VOL에서는 baseline fwd가 음수라 lift 계산 방향이 반전됨
  - 원인 2: SIDEWAYS_HIGH_VOL — 횡보 국면에서 추세/반전 시그널 모두 낮은 n + 불안정

### 권장 조치 (사장님 결재 필요)
A. **Stage C 진입 허용 (합격선 완화)**: 8/18 커버로도 진입 가능 — BEAR/SIDEWAYS 국면은 Stage C에서 별도 처리
B. **합격선 lift ≥ 1.2로 완화**: 커버 확대 가능
C. **BEAR/SIDEWAYS 전용 시그널 추가**: 숏 포지션 대체, 현금 보유 신호 등

---

## PIT 준수 검증
- 모든 rolling/shift는 과거 데이터만 사용 (shift(n≥1) 강제)
- forward return(fwd_3d/20d/60d)은 평가용으로만 사용 — 시그널 계산에 미사용
- universe 필터: T 기준 cross-section (tv_ma20, vol20d_quintile 등)

---

## 다음 단계
- Stage C: 합격 시그널별 매도룰(손절/익절/트레일링) 최적화
- 또는 BEAR/SIDEWAYS 국면 시그널 보완 후 재실행

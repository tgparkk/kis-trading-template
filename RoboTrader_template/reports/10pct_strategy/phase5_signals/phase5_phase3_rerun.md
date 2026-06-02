# Phase 5 — Phase 3 Rerun (트리플 결합 + Walk-Forward 6-window)

생성일: 2026-05-26 (v2-patched 재실행)

---

## 1차 (Phase 3) vs 2차 (v2-patched) 비교표

| 지표 | 1차 (Phase 3) | 2차 v2-patched | 변화 |
|------|--------------|---------------|------|
| 합격 트리플 수 | 20 | **0** | -20 |
| 월평균 수익률 | +0.23% | N/A (트리플 없음) | - |
| Sharpe | 0.3837 | N/A | - |
| MDD | -6.55% | N/A | - |
| 양수 WF 윈도우 | 3/6 (50%) | 0/6 (미실행) | - |
| Calmar | - | N/A | - |
| 트리플 상관 r (mean) | 0.94 | N/A | - |

---

## 트리플 수 / 카테고리 분포

2차 합격 트리플: **0개** (WF 미실행)

### 탈락 경로 요약

| 단계 | 셀/트리플 수 | 탈락 원인 |
|------|------------|----------|
| Stage A/B/C 전체 셀 | 972 | - |
| P2 통과 (n_is>=10, n_oos>=10) | 324 | BULL_HIGH_VOL n_is=5, BEAR_HIGH_VOL n_oos=0 |
| + mean_pnl > 0 | 78 | OBV IS 기간 음수 alpha |
| + sharpe > 0.3 | 68 | - |
| + IS_mean > 0 | **0** | IS_mean 전부 음수 (2021~2024 OBV alpha 미존재) |
| 합격 트리플 | **0** | - |

---

## 1차 (0.23%) vs 2차 월 수익률

| 항목 | 1차 | 2차 |
|------|-----|-----|
| 월평균 | +0.23% | **N/A** |
| 목표 10% 대비 진척 | 2.3% | 0% |

2차 월 수익률 산출 불가: 합격 트리플이 0개이므로 WF 포트폴리오 시뮬 미실행.

---

## 목표 10%/월 대비 진척률

- 1차: +0.23% → **2.3% 진척**
- 2차: N/A → **진척 없음**

---

## cross_section_alpha vs trade-level pnl 정합성

| 구분 | 값 | 비고 |
|------|-----|------|
| 단독 OBV WF OOS gross | +20.24bps/window | cross-section alpha, 전체 universe |
| 통합 OBV cross_section_alpha | -9.6bps | P3 swing_pass 필터 후 축소 pool |
| 통합 OBV trade-level mean_pnl | -0.43% | SL/TP 시뮬 포함 |
| 갭 (단독 - 통합 CSA) | +29.8bps | Universe 불일치로 인한 alpha 소실 |
| 갭 (CSA - trade-level) | +33.4bps | SL/TP exit rule이 갉아먹는 alpha |

**결론**: 단독 +20bps cross-section alpha가 통합에서 -9.6bps로 반전된 것은 ROE Q4+ ∩ swing_pass pool 교집합으로 인한 universe 축소 문제. SL/TP 완화(P1)만으로는 해결 불가.

---

## Family/Regime 분포 (best 셀 기준, n_is>=5)

합격 셀은 없지만, 패치 후 최고 성과 셀 분포:

| Rank | Regime | Family | SL | TP | TM | mean_pnl | n_is | n_oos | IS_mean | OOS_mean |
|------|--------|--------|----|----|----|---------|------|-------|---------|----------|
| 1 | BULL_HIGH_VOL | OBV_OR_VWAP | -10% | 10% | 5d | +1.94% | 5 | 94 | NaN | +2.18% |
| 2 | BULL_HIGH_VOL | OBV_OR_VWAP | -10% | 10% | 3d | +1.42% | 5 | 94 | NaN | +1.59% |
| 3 | BULL_HIGH_VOL | OBV_OR_VWAP | -7% | 10% | 5d | +1.42% | 5 | 94 | NaN | +1.63% |
| 4 | SIDEWAYS_LOW_VOL | OBV_OR_VWAP | -5% | 10% | 5d | +1.20% | 42 | 69 | -0.74% | +2.39% |
| 5 | BULL_LOW_VOL | OBV | -10% | 10% | 5d | +1.07% | 87 | 410 | -1.56% | +1.63% |

모두 **IS_mean 음수** 또는 **n_is < 10**으로 pass 게이트 미통과.

---

## VWAP 분봉 제약 영향

- VWAP 분봉 최초 가용일: 2025-02-24
- VWAP IS 기간(2025-01 이전) 트레이드: **n_is=0** (전 셀)
- VWAP P2 게이트 통과: **0/324** (n_is>=10 조건 전부 탈락)
- VWAP family는 OOS(2025-01~2026-05)에서만 평가 가능 — IS/OOS 분리 검증 구조 자체 불가

---

## 5선 게이트 최종 판정

| 게이트 | 판정 | 근거 |
|--------|------|------|
| 1. IS p-value 비의존 | FAIL | IS_mean 게이트에서 전부 탈락 |
| 2. OOS Net>0 AND 양수윈도우>60% | FAIL | WF 미실행 (트리플 0) |
| 3. 합격 트리플 존재 | FAIL | 0개 |
| 4. Sharpe>0 | FAIL | 합격 트리플 없음 |
| 5. Top 트리플 존재 | FAIL | 0개 |

**0/5 통과**

---

## 판정 및 다음 단계

**Phase 4 paper 진입 불가. 재설계 필요.**

### 재설계 권고 (v2_diagnosis.md Section 3-b)

`p5_obv_swing_walkforward.py` 신설:
- Stage A 단순화: market cap top 500 + trading value > 1B (ROE 교집합 제거)
- Stage B: OBV 1d signal만 (lb=5, thr=1.0std)
- Stage C: SL -5/-7/-10%, TP +3/+5/+10%, TM 1/3/5d (P1 그리드 유지)
- WF: 252/63 rolling 16 windows (단독 WF 구조 그대로)
- 추가: trade-by-trade portfolio simulation 누적 (단독 cross-section → portfolio 전환)
- 목표: cross_section_alpha(단독 +20bps)가 실제 trade-level에서 얼마나 유지되는지 측정

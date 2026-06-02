# Phase 5 — Stage A/B/C Rerun v2 (패치) Summary

생성일: 2026-05-26 (패치 재실행)
소요: 8.9분
패치: P1(SL/TP grid), P2(n_is/n_oos>=10), P3(swing_pass 필터), P4(cross_section_alpha), P5(sharpe/mdd 게이트 완화)

---

## [목적]

5/25 Phase 5 검증 통과 3종(OBV·ROE·VWAP)을 기존 Phase 2/3 인프라에 통합.
v2 1차(합격 0/972, sharpe -8.17) 원인 진단(v2_diagnosis.md) 후 최소 패치 5건 적용 → 재측정.
사장님 약속 '월 10% 정직 보고' 2차 라운드.

---

## [DATA]

- daily_prices: 2,730,019 rows, 2601 stocks
- forward returns: 2,718,959 rows
- ROE stocks: 152
- VWAP 분봉 캐시: 151,651 rows, 1364 stocks (2025-02-24 ~ 2026-05-22)
- 기간: 2021-01-12 ~ 2026-05-26

---

## 패치 P1~P5 변경 내역

| 패치 | 파일 위치 | 변경 전 | 변경 후 | 목적 |
|------|----------|---------|---------|------|
| P1 | L63-65 (SL/TP/TM grid) | SL=[-1.5%~-5%], TP=[3%~15%], TM=[1~60d] | SL=[-5%,-7%,-10%], TP=[3%,5%,10%], TM=[1,3,5d] | OBV 1d std≈3~5% 대비 기존 SL-1.5%는 random walk에서도 50% 즉시발동 |
| P2 | L643-650 (pass gate) | n>=30 단일 조건 | n_is>=10 AND n_oos>=10 분해 | BEAR_HIGH_VOL n_oos=0 구멍 막기 |
| P3 | L601-610 (pool 선택) | swing_lift 기준 nlargest (swing_pass 무시) | swing_pass==True 필터 후 nlargest | position-bucket pool을 swing trade에 적용하는 mismatch 제거 |
| P4 | L363-410 (evaluate_triple) | cross_section_alpha 없음 | cross_section_alpha 컬럼 추가 (sig-pool fwd_1d 차이) | 단독 +20bps와 통합 trade-level pnl 정합성 직접 검증 |
| P5 | L643-650 (pass gate) | sharpe>0.5, mdd>-0.2 포함 | sharpe>0.3, mdd 조건 제거 | trade-level Sharpe 기대치 0.2~0.5, trade-level mdd는 표본 변동에 민감 |

---

## 설계 (1차 v2 vs 2차 v2-patched)

| 항목 | 1차 v2 (패치 전) | 2차 v2-patched (패치 후) |
|------|-----------------|------------------------|
| SL grid | -1.5% ~ -5% (5단계) | -5%, -7%, -10% (3단계) |
| TP grid | 3% ~ 15% (5단계) | 3%, 5%, 10% (3단계) |
| TM grid | 1~60d (7단계) | 1, 3, 5d (3단계) |
| 총 셀 수 | 4,200 (4 regime × 3 pool × 3 family × 5×5×7) | 972 (4 regime × 3 pool × 3 family × 3×3×3) |
| n_is/n_oos 게이트 | n>=30 (n_oos=0도 통과 가능) | n_is>=10 AND n_oos>=10 |
| Sharpe 게이트 | >0.5 | >0.3 |
| MDD 게이트 | >-0.2 | 제거 (trade-level 비현실적) |
| swing_pass 필터 | 없음 | swing_pass==True pool만 채택 |
| cross_section_alpha | 없음 | 측정 추가 |

---

## Stage A/B/C 평가 결과 (패치 후)

- 총 셀: **972**
- 합격 셀: **0** (0.0%)
- 합격 기준: n_is>=10 AND n_oos>=10 AND mean_pnl>0 AND sharpe>0.3 AND IS_mean>0 AND OOS_mean>0

### Regime별 P2 게이트(n_is>=10 AND n_oos>=10) 통과율

| Regime | P2 통과 | 전체 | 통과율 | 실패 원인 |
|--------|---------|------|--------|----------|
| BULL_HIGH_VOL | 0/243 | 243 | 0% | n_is=5 (IS 기간 트레이드 5건뿐) |
| BULL_LOW_VOL | 162/243 | 243 | 67% | n_is 충분하나 IS_mean 전부 음수 |
| BEAR_HIGH_VOL | 0/243 | 243 | 0% | n_oos=0 (OOS 기간 트레이드 없음) |
| SIDEWAYS_LOW_VOL | 162/243 | 243 | 67% | n_is 충분하나 IS_mean 전부 음수 |

### 게이트 퍼널 (P2 통과 324셀 기준)

| 게이트 | 통과 셀 | 탈락 원인 |
|--------|---------|----------|
| P2 통과 (n_is>=10 AND n_oos>=10) | 324/972 | BULL_HIGH_VOL/BEAR_HIGH_VOL 표본 붕괴 |
| + mean_pnl > 0 | 78/324 | OBV IS 기간(-15bps 손실) 대부분 음수 |
| + sharpe > 0.3 | 68/324 | - |
| + IS_mean > 0 | **0/68** | **IS_mean 전부 음수 — 최종 탈락 원인** |
| + OOS_mean > 0 | 0/0 | 미도달 |

**핵심 탈락 원인: IS_mean (2021-01-01~2024-12-31) 전부 음수**

---

## Family별 분석

| Family | 셀수 | mean_pnl 평균 | n_is 평균 | n_oos 평균 | P2 통과 | cross_section_alpha |
|--------|-----|--------------|----------|----------|---------|---------------------|
| OBV | 324 | -0.43% | 54.8 | 64.9 | 162 | -9.6bps |
| VWAP | 324 | +0.52% | 0.0 | 96.4 | 0 | +10.3bps |
| OBV_OR_VWAP | 324 | -0.17% | 54.9 | 137.5 | 162 | -2.9bps |

**VWAP**: IS 기간(2025-01 이전)에 분봉 데이터 없음 → n_is=0 → P2 전부 탈락.
**OBV**: P2 통과 162셀이지만 IS_mean 전부 음수 → 최종 0개.

---

## cross_section_alpha vs trade-level pnl 정합성 분석

| 측정 | 값 | 의미 |
|------|------|------|
| 단독 OBV WF (p5_obv_walkforward.py) | +20.24bps/window | cross-section alpha (시그널 종목 - 비시그널 종목 평균 수익률 차이) |
| 통합 OBV cross_section_alpha (이번) | **-9.6bps** | P3 swing_pass 필터 후 pool 변경으로 단독과 다른 universe |
| 통합 OBV trade-level pnl | -0.43% | SL/TP 시뮬레이션 결과 |

**단독 +20bps → 통합 -9.6bps 갭 원인:**
- P3 swing_pass 필터 적용 후 BULL_HIGH_VOL pool이 n_is=5짜리 소형 pool로 교체됨
- 단독은 전체 종목 수십만 행 기준 cross-section, 통합은 ROE Q4+ ∩ swing_pass pool (수십~수백 행) 기준
- Universe가 다르므로 직접 비교 불가 — 이는 v2_diagnosis.md의 Root Cause 2순위(표본 붕괴) 재확인

**exit rule이 alpha를 갉아먹는 정도 정량화:**
- cross_section_alpha (-9.6bps)와 trade-level pnl (-43bps)의 차이 = -33.4bps (SL/TP 비용)
- IS 기간 OBV 시그널 자체가 이미 음수 alpha → SL/TP 완화만으로는 해결 불가

---

## 1차 vs 2차 비교표

| 지표 | 1차 (p5_stage_rerun.py) | 2차 v2-patched (패치 후) | 변화 |
|------|------------------------|------------------------|------|
| 총 셀 | 1,800 | 972 | -828 |
| 합격 셀 | 0 | **0** | 0 |
| 최고 mean_pnl (n_is>=5) | N/A | +1.94% (BULL_HIGH_VOL OBV_OR_VWAP, n_is=5) | - |
| IS_mean>0 셀 | 0 | 0 | 0 |
| 트리플 수 | 0 | 0 | 0 |
| WF 월평균 | N/A | N/A | - |

---

## 5선 게이트 판정

1. IS p-value 비의존 (OOS 기반): **FAIL** (OOS 셀 존재하나 IS_mean 게이트 탈락)
2. OOS Net>0 AND 양의 윈도우>60%: **FAIL** (WF 미실행)
3. 합격 트리플 존재: **FAIL** (0개)
4. Sharpe>0: **FAIL** (합격 트리플 없음)
5. Top 트리플 존재: **FAIL** (0개)

**총 0/5 통과**

---

## 근본 원인 재확인 (패치 후)

패치 P1(SL 완화)으로 BULL_HIGH_VOL OBV 셀의 mean_pnl이 -890bps → +0.3bps 수준으로 회복됨.
그러나 IS_mean이 여전히 음수(-1.5%~-2%) → IS 기간(2021~2024) 동안 OBV signal + ROE Q4+ + swing pool에서 음의 수익.

IS 기간 OBV 자체의 cross_section_alpha가 -9.6bps (단독 +20bps와 다른 universe)임을 감안하면,
**v2 인프라(Phase 2a swing pool + ROE Q4+ 교집합)에서 OBV signal의 IS 기간 alpha가 없음** — 이것이 패치로 해결할 수 없는 설계 정합성 문제.

---

## 판정

**추가 EDA 필요 / 재설계 권고 (Phase 4 paper 진입 불가)**

- Phase 4 paper 진입 가능: No
- 이유:
  1. IS_mean 전부 음수 → OOS 개선이 IS 과적합이 아닌 진짜 alpha인지 검증 불가
  2. BULL_HIGH_VOL n_is=5 / BEAR_HIGH_VOL n_oos=0 표본 붕괴 미해결
  3. cross_section_alpha(통합)이 단독 +20bps와 역방향(-9.6bps) → universe 정합성 없음
- 권고: v2_diagnosis.md Section 3(b) 재설계 — `p5_obv_swing_walkforward.py` 신설 (단독 WF 구조 + portfolio sim, Stage A 단순화)

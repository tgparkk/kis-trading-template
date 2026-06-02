> **[2026-05-26 정정 노트]**
> 본 보고서의 "Stage B 즉시 채택" 권고는 **cross-section alpha 측정 결과**에 기반.
> Stage A pool 통합 + SL/TP 적용 시 trade-level pnl은 별도 검증 필요.
> Phase 5 `p5_stage_rerun_v2.py` 통합 결과 + 패치 진행 중 (`v2_diagnosis.md` 참조).

# Phase 5 — OBV (On-Balance Volume) Walk-Forward + 레짐 검증

**판정: 무조건 채택 — 5/5 PASS** (TOM 방법론 일반화 첫 번째 통과 사례)

## 요약

OBV는 TOM 시그널 검증 후 일반화된 5선 방법론을 모두 통과한 첫 시그널. OOS Net @0.3% +1.7236pp/window, 양의 윈도우 비율 100% (16/16). 모든 레짐에서 양수, 시총 클수록 효과 증폭. TOM이 -0.232pp/window로 실패한 것과 정반대.

## 데이터

- robotrader_quant.daily_prices 2,666,387 행 / 2,596 종목 / 2021-01-13 ~ 2026-05-22
- Winsorize: 1~99% ([-12.3439%, +15.2795%])
- 레짐: market_regime 테이블 미존재 → proxy로 derive (bull/bear × high/low_vol 4분류)
- 시총 분위: Q1~Q5 cross-sectional median

## 검증 1: Walk-Forward OOS (16 windows, 252/63 rolling)

### 9-파라미터 그리드 결과

| lb | thr_type | OOS_gross_pp | OOS_net_A_pp (fee=0.3%) | pct_positive |
|---|---|---|---|---|
| **5** | **1.0std** | **+2.0236** | **+1.7236** | **100%** |
| 5 | 0.5std | +1.8742 | +1.5742 | 100% |
| 5 | 0 | +1.2782 | +0.9782 | 100% |
| 10 | 0 | +0.5378 | +0.2378 | 100% |
| 10 | 0.5std | +0.4790 | +0.1790 | 87.5% |
| 10 | 1.0std | +0.4326 | +0.1326 | 68.75% |
| 20 | 0 | +0.1988 | -0.1012 | 6.25% |
| 20 | 0.5std | +0.0049 | -0.2951 | 6.25% |
| 20 | 1.0std | -0.0423 | -0.3423 | 6.25% |

**Best: lb=5, thr=1.0std** (OOS Net @0.3% +1.7236pp, 16/16 양수)

### 손익분기점
- OOS gross diff = +20.236bps
- KIS 비용 ~30bps → net +17.236bps
- **TOM은 gross 6.84bps였음 (KIS 비용 미달)**, OBV는 6.7배 큰 효과

## 검증 2: 레짐 조건부 효과 분해 (full-sample IS, lb=5/thr=1.0std)

| Regime | OBV diff (pp) | 판정 |
|---|---|---|
| **bull_high_vol** | **+0.9957** | 강한 양수 |
| bull_low_vol | +0.7601 | 양수 |
| bear_high_vol | +0.7351 | 양수 |
| bear_low_vol | +0.6457 | 양수 |
| unknown | +0.7614 | 양수 |

**모든 레짐에서 양수** (TOM은 bear_low_vol에서 강한 역효과였음). OBV는 무조건 채택 가능.

## 검증 3: 시총 × 레짐 cross

OBV diff (pp) 매트릭스:

| Mcap Q | bear_high_vol | bear_low_vol | bull_high_vol | bull_low_vol | unknown |
|---|---|---|---|---|---|
| Q1 (소형) | +1.7267 | +1.5366 | +1.8809 | +1.3633 | +1.7933 |
| Q2 | +1.8555 | +1.6089 | +2.1258 | +1.6868 | +1.8758 |
| Q3 | +2.1681 | +1.9956 | +2.4205 | +1.9905 | +1.9615 |
| Q4 | +2.2217 | +2.2747 | +2.5889 | +2.2116 | +2.0065 |
| Q5 (대형) | +2.3773 | +2.3295 | **+2.6390** | +2.5042 | +2.2158 |

- **모든 셀 양수** (25/25)
- **Q5 × bull_high_vol +2.6390pp 최강** — P1 Top 5 셀(bull_high_vol × Q5/Q1 × position)과 일치
- **시총 클수록 효과 증폭** — TOM 패턴과 동일하지만 절대값 4~5배 크다

## 5선 방법론 평가

| 항목 | 결과 |
|---|---|
| 1. IS p-value 의존 금지 | ✓ OOS 검증 통과 |
| 2. OOS Net @0.3% > 0pp + 양의 비율 > 60% | ✓ +1.72pp / 100% |
| 3. 레짐 조건부 가능성 | ✓ 모든 레짐 양수, 무조건 채택 가능 |
| 4. 파라미터 안정성 | ✓ Best 외에도 lb=5 전체 100% |
| 5. 레짐 + 시총 결합 | ✓ Q5×bull_high_vol +2.64pp |

**5/5 PASS — 무조건 채택**

## TOM과의 비교

| 지표 | OBV (lb=5,1.0std) | TOM (N=2,M=3) |
|---|---|---|
| OOS gross diff | +20.24bps | +6.84bps |
| OOS Net @0.3% | **+17.24bps** | **-23.16bps** |
| 양의 OOS 비율 | 100% | 31% |
| 레짐 통과 | 5/5 | 3/6 (bear_low_vol 역효과) |
| 5선 방법론 | **5/5 PASS** | 0/5 FAIL |

## 권고

### Stage B 즉시 채택
- **lb=5, thr=1.0std (또는 0.5std)** 무조건 매수 시그널
- 5일 OBV slope이 1σ 이상 상승 → T+1 시초 진입 → 1일 보유
- 거래비용 0.3% 차감 후도 1.72pp 양수, 16/16 윈도우 안정

### Stage A 시총 필터 결합
- ROE Q4+ + 시총 Q4+ + OBV signal 결합 시 효과 농축 (Q5×bull_high_vol +2.64pp)
- Stage A 9차원 LHS에 OBV signal을 1차원 추가

### Stage C 매도 룰
- OBV 보유 기간 검증 필요 (1일 vs 5일 vs 20일) — 별도 분석
- 현재 그리드는 1일 보유 가정

## 산출물

- 분석 스크립트: `scripts/10pct_strategy/p5_obv_walkforward.py`
- 시각화 (3개): `.omc/scientist/figures/obv_*.png`
  - obv_wf_oos.png
  - obv_regime.png
  - obv_mcap_regime.png

## 한계

1. **레짐 derive proxy**: market_regime 테이블 미존재로 proxy 사용. P0-4 레짐 segment 직접 연결 시 정확도 향상 가능 (TOM 직원과 동일 한계)
2. **1일 보유 가정**: 다른 holding period (5d/20d) 검증 필요
3. **OBV positive divergence** 외 다른 OBV 변형 (OBV/MA 비율, 다이버전스 패턴) 미검증

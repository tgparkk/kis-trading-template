# changelog-2026-05-23-phase1-relabel-v2.md
## Phase 1 재재측정 — +1% 익절 목표 (사장님 결재 2026-05-23)

---

## 배경 / 이전 시도 요약

**이전 시도 (Phase 1 relabel, +2% 익절 / stop 0.8~2.0%):**
- base_2pct_rate (단순 도달): 37.9%
- base_2pct_safe_stop10 (기존 최우수): 25.4%
- 가장 강한 신호 ("ret_20d>=25 AND atr_20d>=8")로도 expectancy 음수
- 결론: +2%/−1% 파라미터 조합 자체가 비용을 커버 불가

**사장님 결재 (2026-05-23):**
- +1% 익절로 낮춰서 빈도 우선 재측정
- 목표: "매매당 +1% 이상이라도 안정적으로"

---

## +1% 익절 라벨 정의 (4종)

| 라벨 | 익절 목표 | 손절선 |
|------|-----------|--------|
| label_1pct_safe_stop03 | +1.0% | -0.3% |
| label_1pct_safe_stop05 | +1.0% | -0.5% |
| label_1pct_safe_stop07 | +1.0% | -0.7% |
| label_1pct_safe_stop10 | +1.0% | -1.0% |

- 진입가: close_0930 (09:30:00 봉 close)
- 분봉 09:31~15:30 시간순 순회
- 동시 발생 → 보수적 손절 우선 (0)
- 비용 가정: 0.41% (슬리피지+수수료+거래세)

---

## 분석 결과

### Base Rate

| 라벨 | base_rate | expectancy |
|------|-----------|------------|
| base_2pct (단순, 참고) | 37.9% | - |
| base_2pct_safe_stop10 (기존) | 25.4% | -0.65% |
| **base_1pct_safe_stop03** | **20.7%** | **-0.44%** |
| **base_1pct_safe_stop05** | **29.3%** | **-0.47%** |
| **base_1pct_safe_stop07** | **35.4%** | **-0.51%** |
| **base_1pct_safe_stop10** | **43.0%** | **-0.55%** |

### Top 5 룰 (expectancy_stop05 기준)

| 룰 | n | safe05 | exp_03 | exp_05 | exp_07 | exp_10 |
|----|---|--------|--------|--------|--------|--------|
| ma20_dist_pct>=20 | 496 | 36.1% | -0.37% | -0.37% | -0.38% | -0.39% |
| atr_20d_pct>=10 | 180 | 34.4% | -0.40% | -0.39% | -0.41% | -0.39% |
| ma20_dist_pct>=15 | 792 | 33.5% | -0.42% | -0.41% | -0.42% | -0.42% |
| ma20_dist_pct>=10 | 1,347 | 33.1% | -0.41% | -0.41% | -0.43% | -0.46% |
| m30_close_vs_open>=1.5 | 1,047 | 33.0% | -0.39% | -0.42% | -0.44% | -0.43% |

### Expectancy 양수 룰 개수

| stop | 양수 룰 수 | 전체 룰 수 |
|------|-----------|-----------|
| stop03 (-0.3%) | **0개** | 34 |
| stop05 (-0.5%) | **0개** | 34 |
| stop07 (-0.7%) | **0개** | 34 |
| stop10 (-1.0%) | **0개** | 34 |

---

## 핵심 결론: Expectancy 전 구간 음수

**34개 룰 × 4개 stop 조합 전부 expectancy 음수.**

원인 분석:
- 비용 0.41%가 너무 크다. +1% 익절에서 순수익은 +0.59%에 불과.
- safe rate가 expectancy 손익분기점을 넘으려면:
  - stop03(-0.3%): safe_rate > 0.41/(0.59+0.71) = **54.6%** 필요 → 현재 최대 36.1%
  - stop05(-0.5%): safe_rate > 0.41/(0.59+0.91) = **49.3%** 필요 → 현재 최대 36.1%
  - stop07(-0.7%): safe_rate > 0.41/(0.59+1.11) = **44.2%** 필요 → 현재 최대 36.1%
  - stop10(-1.0%): safe_rate > 0.41/(0.59+1.41) = **40.1%** 필요 → 현재 최대 43.0%
- **stop10(-1.0%)의 경우 base rate 43.0%로 분기점(40.1%)을 겨우 초과하지만**, 개별 룰(필터링 후)에서는 43% 이상이 나오지 않음 (최강 룰 "ma20_dist>=20"도 stop10 기준 38.7%)

---

## 게이트 판정

**[FAIL]** expectancy_stop05 양수 룰 0개 → 사장님께 추가 결재 필요

---

## 권고 (다음 결재 사항)

1. **비용 재검토**: 실제 슬리피지가 0.41%보다 낮을 경우 (예: 0.2%) expectancy 개선 가능
   - stop10(-1.0%) 기준 cost 0.2%이면 분기점 ≈ 37.5% → base rate 43.0% > 초과 → PASS 가능성
2. **익절 목표 재논의**: +1%에서도 비용 커버 불가 → +0.5%는 더 악화 (비율 개선되지 않음)
   - 오히려 익절 목표를 높이면서 stop을 넓히는 방향이 구조적으로 유리
3. **진입 시점 변경**: 09:30 갭을 피하고 모멘텀 확인 후 09:45~10:00 진입 시 유리한지 재측정 필요
4. **비용 절감**: 증권사 수수료 협의, 거래세 0.2% 절감 불가하나 슬리피지 제어 (지정가 주문) 여부 검토

---

## 산출물

| 파일 | 내용 |
|------|------|
| `D:\GIT\kis-trading-template\RoboTrader_template\scripts\signal_combo_phase1_relabel_v2.py` | 신규 스크립트 |
| `D:\GIT\kis-trading-template\RoboTrader_template\reports\signal_combo_aprmay\cases_v4.csv` | cases_v3 + 1pct safe 4종 (7,200행) |
| `D:\GIT\kis-trading-template\RoboTrader_template\reports\signal_combo_aprmay\reach_1pct_analysis.csv` | 34룰 × safe rate + expectancy 4종 |
| `D:\GIT\kis-trading-template\RoboTrader_template\reports\signal_combo_aprmay\label_comparison_v2.csv` | 2pct + 1pct 전체 base rate 통합 비교 |

실행 시간: 14.2초

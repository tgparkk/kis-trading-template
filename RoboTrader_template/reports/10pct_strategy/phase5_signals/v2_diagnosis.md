# Phase 5 v2.py — Walk-Forward 갭 진단 보고서

> 작성일: 2026-05-26  
> 작성자: architect (READ-ONLY)  
> 대상: `scripts/10pct_strategy/p5_stage_rerun_v2.py`  
> 비교 기준: `scripts/10pct_strategy/p5_obv_walkforward.py` (5/25 5/5 PASS)

---

## 핵심 모순

| 지표 | OBV (lb=5, thr=1.0σ) Best 셀 |
|---|---|
| 5/25 `p5_obv_walkforward.py` — OOS Net@0.3% | **+1.7236pp/window**, 16/16 양수 (100%), 모든 레짐 양수 |
| 5/26 `p5_stage_rerun_v2.py` BULL_HIGH_VOL/OBV 베스트 | **mean_pnl -0.89%, sharpe -8.17, mdd -94.4%, win_rate 21%, n_is 24, n_oos 290** |

→ **+172bps → -890bps**, 1,062bps 갭. v2는 동일 OBV 시그널을 평가했음에도 정반대.

---

## 1. 가설 검증 결과표

| # | 가설 | 판정 | 증거 |
|---|------|------|------|
| H1 | Walk-Forward 윈도우 설계 오류 | **부분 채택** | v2는 252/63 6 windows로 가져가지만 *Stage A/B/C 그리드 평가*는 WF 윈도우와 무관하게 IS/OOS=2025-01-01 단일 컷오프 하나만 사용. WF는 top_triples 선택 후에만 적용되는데, top_triples=0이라 사실상 WF 미실행. |
| H2 | Stage A pool 통과 종목군 편향 | **CRITICAL 채택** | n=314 (BULL_HIGH_VOL pool1), 77 (BULL_LOW_VOL pool1), 44 (BEAR_HIGH_VOL pool1, n_oos=0!), 83 (SIDEWAYS_LOW_VOL pool1). 단독은 N≈수십만 행에서 OBV signal cross-section 비교 vs v2는 ROE 152종목 ∩ pool top-N ∩ OBV → 표본이 수천 배 축소되어 노이즈 지배. |
| H3 | 매수 진입 타이밍 왜곡 | 기각 | `simulate_exit` 진입가가 `ohlc[0,0]` (T+1 open), 단독과 동일 PIT. |
| H4 | 거래비용 차감 위치 오류 | **HIGH 채택 (산식 의미 차이)** | v2 L402: 개별 trade pnl마다 fee 차감 후 평균/Sharpe/MDD 산출. 단독은 cross-section diff에서 fee 차감. 두 산식은 다른 의미 측정. |
| H5 | OBV holding period 불일치 | 기각 (그러나 그리드 무의미) | tm 1~60에서 결과 거의 동일은 SL=-1.5%가 너무 좁아 1~2일 안에 거의 모든 trade가 SL 청산되기 때문. SL=-1.5% 셀에서 tm=1과 tm=60의 mean_pnl/n이 동일(CSV L2~L8) — 결정적 증거. |
| H6 | forward return PIT 위반 | 기각 | obv_slope, obv_slope_std는 모두 rolling (min_periods 보장). PIT 안전. |
| H7 | SL/TP 그리드 자체가 OBV 분포와 불일치 | **CRITICAL — 1순위 원인** | OBV 1d 평균 cross-section alpha 단독: +20bps gross. v2 SL grid 최소 -1.5%, TP grid 최소 +3%. 1d intraday low가 -1.5% 이하인 종목 다수 → SL 즉시 발동. OBV 효과는 entry direction은 맞히지만 단기 노이즈에 의한 강제 청산으로 평균 -150bps 손실 누적. |
| H8 신규 | Stage A pool param 미스매치 | **MEDIUM 채택** | phase2a_filter_passed.csv는 swing/mid/position 버킷별 통과 셀. v2 L604-610는 swing_lift 기준 nlargest, 그러나 BULL_HIGH_VOL cell 4는 swing_lift=0.99(미통과)/position_lift=1.52(통과)인 position-bucket 후보. swing trade(1d) 적용 시 horizon mismatch. |
| H9 신규 | OBV signal 계산 미세 차이 | 기각 | _obv_single 함수, slope 계산식, threshold(1.0*std) 모두 단독과 동일. |

---

## 2. Root Cause 분해 (정량적 인과 사슬)

### Root Cause 1순위 — Exit grid가 OBV signal 분포와 부정합 (H7)

증거 1 — TM 무의미 패턴 (stage_a_rerun.csv L2-L8):
```
BULL_HIGH_VOL,1,OBV,-0.015,0.03,1,  n=314, mean=-0.00887, mdd=-0.9443
BULL_HIGH_VOL,1,OBV,-0.015,0.03,5,  n=314, mean=-0.00883, mdd=-0.9434
BULL_HIGH_VOL,1,OBV,-0.015,0.03,10~60, 동일값
```
tm 1d와 60d 결과가 같음 → simulate_exit(v2.py L314-327)에서 SL이 거의 모든 trade에서 1d 안에 발동되므로 timeout(tm) 무의미. 단독 검증(p5_obv_walkforward.py L186-204)은 단순 1-bar return(ret_w) 평균 비교라 SL/TP 시뮬 자체가 없음.

증거 2 — 단독 검증 산식 (p5_obv_walkforward.py L186-198):
```python
oos_sig = ov[sc] > thr
osr = ov.loc[oos_sig,"ret_w"].mean()     # 시그널 종목군 1d 수익률
onr = ov.loc[~oos_sig,"ret_w"].mean()    # 비시그널 종목군 1d 수익률
oos_gross = (osr-onr)*100
```
cross-sectional 차이가 +20.24bps이지 "OBV 매수 절대수익률 +172bps"가 아님. OBV signal 종목군 절대수익률은 시장 평균 대비 +20bps 우위일 뿐, 매매 시뮬레이션 결과 아님.

증거 3 — n_is=24의 의미:
- IS = date < 2025-01-01인 trade 수.
- BULL_HIGH_VOL pool1에서 ROE Q4+(152종목) ∩ vol_quintile=5 ∩ mcap top 300 ∩ trading_value>=1B ∩ price>=5K ∩ candle_health>=0.4 ∩ regime==BULL_HIGH_VOL + OBV signal=1인 사건이 2021~2024 전체 4년 동안 24건.
- 단독은 동일 기간 수십만 건 OBV signal로 평균 비교.
- v2는 24건이라는 통계 무의미 표본에 SL=-1.5%/TP=+3% 시뮬 → 극단 분포가 mean_pnl/sharpe/mdd 왜곡.

코드 라인 책임:
- `p5_stage_rerun_v2.py:63-65` — SL_GRID/TP_GRID/TM_GRID. OBV 1d cross-section std ≈ 3~5% 대비 SL=-1.5%는 1σ 이내 → random walk에서도 50% 확률 발동.
- `p5_stage_rerun_v2.py:314-327` — simulate_exit가 SL 먼저 체크. OBV 효과(+20bps cross-section alpha) 발현 전 청산.

### Root Cause 2순위 — Stage A pool 표본 붕괴 (H2 + H8)

증거 4 — regime별 표본 (stage_a_rerun.csv 전수):
| Regime | pool_rank 1 | pool_rank 2 | pool_rank 3 |
|---|---|---|---|
| BULL_HIGH_VOL | n=314 | n=96 | **n=0** |
| BULL_LOW_VOL | n=77 | (확인됨) | (확인됨) |
| BEAR_HIGH_VOL | n=44 (n_oos=0!) | - | - |
| SIDEWAYS_LOW_VOL | n=83 | - | - |

BEAR_HIGH_VOL pool1은 OOS=0건 → OOS_mean=NaN → pass=False 강제. 합격 0개의 직접 원인.

증거 5 — Stage A pool 부적합 (phase2a_filter_passed.csv L2):
BULL_HIGH_VOL cell 4 첫 row 통과 버킷은 position (long-hold 5~20d). swing 버킷은 swing_lift=0.99/swing_pass=False. v2는 이 pool을 1d 보유 OBV swing 트레이드에 적용 → universe-horizon 부정합.

코드 라인 책임:
- `p5_stage_rerun_v2.py:599-619` — phase2a top-3 pools 선택. swing_lift 기준 정렬이나 swing_pass=False 포함.
- `p5_stage_rerun_v2.py:282-302` — apply_pool_filter. 6중 필터 + ROE Q4+(L305-311) → universe 한 자릿수로 붕괴.

### Root Cause 3순위 — 단독↔통합 평가 의미 불일치

단독: "OBV 시그널 종목군 평균 - 비시그널 종목군 평균" (cross-sectional alpha).
v2: "OBV signal 발생 시 T+1 시초 매수 → SL/TP 청산 → trade-by-trade pnl 평균" (실전 매매 시뮬).

두 산식은 같은 OBV signal을 다른 질문에 대답.
- 단독은 "OBV가 알파 시그널인가?" → Yes (+20bps cross-section).
- v2는 "OBV signal로 SL=-1.5%/TP=+3% 매매하면 수익 나는가?" → No (-150bps trade).

알파 시그널이 있더라도 SL/TP 룰이 부적합하면 매매 손실. v2는 이 사실을 발견했지만 진단 미흡으로 시스템 버그처럼 보일 뿐.

---

## 3. 수정 권고

### (a) 최소 패치 — 즉시 처리 가능 (executor 1시간 이내)

**P1. SL/TP grid 재조정** (`p5_stage_rerun_v2.py:63-65`):
```python
# 변경 전
SL_GRID = [-0.015, -0.02, -0.03, -0.04, -0.05]
TP_GRID = [0.03, 0.05, 0.07, 0.10, 0.15]
TM_GRID = [1, 5, 10, 20, 30, 45, 60]

# 변경 후 — OBV 1d signal 분포(±5%) 대비 비대칭 노이즈 흡수
SL_GRID = [-0.05, -0.07, -0.10]
TP_GRID = [0.03, 0.05, 0.10]
TM_GRID = [1, 3, 5]
```
효과 예상: BULL_HIGH_VOL pool1 SL 즉시 청산률 감소. mean_pnl -150bps → -50~0bps 근방 회복 예상 (단독 +172bps에는 못 미침).

**P2. n_oos < 10 셀은 pass 게이트 전 reject** (`p5_stage_rerun_v2.py:643-650`):
```python
row["pass"] = (
    res["n_oos"] >= 10 and        # 추가
    res["n_is"]  >= 10 and        # 추가
    pd.notna(res["mean_pnl"]) and res["mean_pnl"] > 0 and
    ...
)
```
효과: BEAR_HIGH_VOL pool1(n_oos=0)이 무의미하게 NaN fail되는 노이즈 제거.

**P3. swing_pass=True pool만 채택** (`p5_stage_rerun_v2.py:601-610`):
```python
sub = filters_df[
    (filters_df["regime"]==regime) &
    (filters_df["swing_pass"]==True)
].copy()
```
효과: position-bucket pool이 swing trade에 적용되는 mismatch 제거.

**P4. cross_section_alpha 컬럼 병기** (`p5_stage_rerun_v2.py:363-410`):
evaluate_triple 반환에 `cross_section_alpha = sig_df["fwd_1d"].mean() - pool_df["fwd_1d"].mean()` 추가. 단독 +20bps이 통합에서도 동일 측정되는지 확인. SL/TP 시뮬 결과와의 차이가 "exit rule이 알파를 얼마나 갉아먹는가" 정량.

### (b) 대안 — 재설계 권고

위 패치는 v2.py 본질 문제를 회피하지 않음. 본질은 p2a swing/mid/position 3-bucket 인프라가 OBV 1d signal과 horizon mismatch.

- **v3 분리**: `p5_obv_swing_walkforward.py` 신설. 단독 검증의 252/63 16-window 구조 유지하면서 portfolio simulation(trade-by-trade pnl 누적) 추가. Stage A 단순화(market cap top 500 + trading value > 1B). Stage B OBV 1d signal만. Stage C OBV-fit grid(SL -5/-7/-10%, TP +3/+5%, TM 1/3/5d).
- **v2.py는 폐기 또는 sandbox 격리**: phase2a swing/mid/position bucket이 OBV+VWAP/ROE multi-signal에 적용되는 통합 구조 자체가 미검증. p2b/p2c 기존 통합 검증은 swing buy signal(MA cross 류)을 가정한 인프라.

---

## 4. 재실행 후 예상 결과

| 시나리오 | 예상 mean_pnl (BULL_HIGH_VOL OBV best) | sharpe |
|---|---|---|
| 패치 없음 (현재) | -890bps | -8.17 |
| P1 최소 패치 (SL widen) | -100 ~ +30bps | -1 ~ +0.5 |
| P1+P2+P3 풀패치 | +20 ~ +80bps | +0.3 ~ +1.0 |
| (b) 재설계 + portfolio sim | +50 ~ +150bps | +0.8 ~ +1.5 |

핵심: 단독 +172bps에는 도달 못 함. 단독은 cross-section alpha의 이상치(KIS 거래비용 0.3% 차감 후 16/16 양수)이고, 통합 매매 시뮬은 trade-by-trade라 alpha 실현 과정에서 SL/TP 룰이 alpha의 30~80% 갉아먹는 것이 정상.

---

## 5. 5선 게이트 기준 적정성 평가

현재 gate (`p5_stage_rerun_v2.py:643-650`):
```
mean_pnl - 0.3% > 0  AND  sharpe > 0.5  AND  mdd > -0.2
AND  IS > 0  AND  OOS > 0  AND  n >= 30
```

| 게이트 | 평가 | 권고 |
|---|---|---|
| mean_pnl-fee > 0 | 적정 | 유지 |
| sharpe > 0.5 | **너무 빡빡** (단일 시그널 trade-level Sharpe 기대치 0.2~0.5) | 0.3으로 완화 |
| mdd > -0.2 | **현 시뮬에서 비현실적** (n=24 trade의 cumulative MDD는 표본 변동에 민감, -50~-90%가 정상) | trade-level에선 제외, portfolio level에서만 적용 |
| IS > 0 AND OOS > 0 | 적정 | 유지 |
| n >= 30 | **n_is/n_oos 각 10 이상**으로 분해 | n_is>=10 AND n_oos>=10 (현재는 합계 30이라 n_oos=0이어도 통과 가능한 구멍 존재) |

결론: 5게이트 중 2개(sharpe, mdd)가 trade-level 통계 특성을 무시한 portfolio-level 임계값으로 설정됨. 합격 0개는 시그널이 약해서가 아니라 게이트가 trade-level과 portfolio-level을 혼동했기 때문이기도 함.

---

## 6. 결론 요약

- v2.py는 코드 버그(crash, off-by-one, PIT 위반)는 **없음**.
- 결함은 **설계 정합성**: (1) p2a swing/mid/position 인프라를 OBV swing 1d trade에 그대로 적용, (2) SL/TP grid가 OBV 1d signal 분포와 비대칭, (3) cross-section alpha 산식과 trade-level pnl 산식의 의미를 혼동하여 단독 결과를 통합 결과와 직접 비교.
- 단독 +172bps는 cross-sectional alpha 측정값일 뿐 매매 수익률 예측치가 아님. 1차 보고서의 "Stage B 즉시 채택, lb=5/thr=1.0std, T+1 시초 진입 → 1일 보유" 권고도 trade-level 검증 없이 cross-section alpha만으로 도출된 추정.
- 최소 패치(P1-P3)로 합격 셀 1~5개 수준 복구 가능. 정확한 trade-level 수익 예측은 재설계(b) 필요.

---

## 산출물 및 참고

- 진단 대상: `scripts/10pct_strategy/p5_stage_rerun_v2.py:1-1003`
- 비교 기준: `scripts/10pct_strategy/p5_obv_walkforward.py:1-521`
- 1차 단독 보고: `reports/10pct_strategy/phase5_signals/obv_walkforward.md`
- 2차 통합 결과: `reports/10pct_strategy/phase5_signals/phase5_stage_rerun_summary.md`
- 결과 CSV 표본: `reports/10pct_strategy/phase5_signals/stage_a_rerun.csv:1-6300`

# 2026-05-17 SL/TP 그리드 토너먼트 — ORB 우승자 발견

## 핵심 결과
- **합격 시나리오 2건 (10전략 600+ 시나리오 중 처음으로 합격선 통과)**
- **우승자: ORB / dynamic universe / SL 3% / TP 6% (R/R 2:1)**

### 합격 시나리오
| 순위 | 전략 | universe | pos | SL | TP | 일수익률 | 일승률 | Calmar | MDD |
|---|---|---|---|---|---|---|---|---|---|
| **1** | **ORB** | dynamic | 4 | 3% | 6% | **+0.442%** | **59.4%** | 22.6 | -6.8% |
| **2** | **ORB** | dynamic | 5 | 3% | 6% | +0.359% | 62.5% | 20.6 | -5.4% |

**의미**: 일수익률 0.442% × 30일 단순합 13.2%/월 — 사장님 목표(일 0.5~1.5%) 하한 근접. 일승률 59~62%로 매매 절반 이상 양수. MDD -7% 수준 안전, Calmar 22.6 매우 우수.

## 토너먼트 사양 (사장님 결재)
- **기간**: 2026-04-01 ~ 2026-05-15 (약 30거래일, 2026-03 제외)
- **전략 (4)**: vwap_trade, orb, reversal_vwap, red_to_green (이전 풀 토너먼트 양수 후보)
- **SL × TP 그리드**: 4×4 = 16조합 (SL 0.5/1/2/3% × TP 1/2/4/6%)
- **Universe × pos**: 2 (screener/dynamic) × 3 (3/4/5) = 6
- **총 시나리오: 384**
- **소요**: 약 11.5h (12:19 → 23:41)
- **결과 위치**: `RoboTrader_template/reports/tournament_grid/20260517_121928/`

## 이전 단계 누적 회귀 결과
- **회귀 1,921 passed**, 1 pre-existing fail (test_screener_pipeline)
- Phase 1A~E 완료, Phase 2 코드+속도 개선 완료

## 핵심 인사이트
1. **ORB + 손익비 2:1 + 큰 폭(3%/6%)** = 데이트레이딩 적합 조합 — 분봉 노이즈 흡수 + 큰 움직임 포착
2. **dynamic universe (변동성 상위 50)** 가 ORB에 유리 — screener universe는 ORB도 trades 거의 없음
3. ORB 96 시나리오 평균 일승률 13% (다른 전략 5~10% 대비 우수) — 구조적으로 SL/TP 조합에 둔감
4. 이전 디폴트(SL 1%/TP 2%)는 분봉 노이즈에 부적합 — 600+ 시나리오 합격 0건

## 미흡한 점
- 30일 표본만으로 우승자 결정 — **overfit 가능성 큼**
- 168일 풀 데이터 OOS 검증 미실시
- 페이퍼 트레이딩 검증 미실시
- ORB 파라미터(box_minutes=30 고정) 세부 튜닝 미실시

## 다음 세션 (Phase 3) 권고 — 우선순위 순

### Phase 3-A: OOS 검증 (필수, 1~2h)
ORB / dynamic / SL 3% / TP 6% / pos 4·5 만으로 168일 풀 데이터 백테스트.
```powershell
cd D:\GIT\kis-trading-template
python RoboTrader_template/scripts/run_intraday_tournament.py `
    --start 20250901 --end 20260515 --skip 202603 `
    --capital 10000000 `
    --max-positions 4 5 `
    --universe dynamic `
    --strategies orb `
    --sl-grid 0.03 --tp-grid 0.06 `
    --eod 15:20 --slip-bps 5 `
    --workers 8 `
    --dynamic-top-n 50 --dynamic-rank-by volatility_pct `
    --out RoboTrader_template/reports/tournament_orb_oos `
    --log-level INFO
```
- 시나리오 4개(2pos × 1sl × 1tp)만 → 168일 × 4 = ~30분 예상
- 합격선(일0.3%/승률50%/MDD15%) 유지 시 → 우승 확정. overfit 아님.
- 합격선 미달 시 → 30일이 운 좋은 표본이었음. Phase 3-B로 후퇴

### Phase 3-B: 멀티버스 파라미터 튜닝 (1~2일)
ORB 내부 파라미터 세부 그리드:
- `box_minutes`: [15, 20, 30, 45]
- `entry_buffer_pct`: [0.000, 0.001, 0.002]
- `trail_pct`: [0.005, 0.010, 0.015, None]
- SL/TP는 [3%/6%]로 고정 또는 ±1단계 확대
- `backtest/multiverse.py:323-900` 재사용 (mode=minute 분기 필요 시 추가)

### Phase 3-C: 양수 그러나 합격 미달 시나리오 검토
- `orb / dynamic / pos=3 / SL=3% / TP=6%` = +0.39%/일, 일승률 46.9%, MDD -11.7% (합격선 -15% 통과지만 일승률 미달)
- `orb / dynamic / pos=4 / SL=3% / TP=4%` = +0.27%, 일승률 56.25%
- 이들도 후보로 함께 OOS 검증 고려

### Phase 4: 페이퍼 트레이딩 (5+ 영업일)
- OOS 통과한 우승 파라미터를 `strategies/config.py`에 등록
- `multiverse_paper` 러너로 가상매매
- 백테스트 PnL과 ±10% 일치성 검증

## 핵심 파일 경로 (Phase 3 시작 전 참고)
- 토너먼트 러너: `RoboTrader_template/scripts/run_intraday_tournament.py`
- 분봉 엔진: `RoboTrader_template/backtest/engine.py` (`run_minute(...)`)
- 멀티버스 엔진: `RoboTrader_template/backtest/multiverse.py:323-900`
- ORB 전략: `RoboTrader_template/strategies/intraday/orb/strategy.py`
- ORB config: `RoboTrader_template/strategies/intraday/orb/config.yaml`
- 분봉 universe 빌더: `RoboTrader_template/utils/intraday_universe.py`
- 분봉 지표: `RoboTrader_template/utils/intraday_indicators.py`
- 평가 지표: `RoboTrader_template/backtest/tournament_metrics.py`

## 결과 파일 (앞으로 참고용)
- 우승 결과: `RoboTrader_template/reports/tournament_grid/20260517_121928/tournament_round1_summary.md`
- 30일 일반 토너먼트: `RoboTrader_template/reports/tournament_recent/20260517_102421/`
- 168일 풀 토너먼트: `RoboTrader_template/reports/tournament_round1/20260516_232527/`

## 미체결 합격선 결재 (다음 세션 사장님 확인)
- 합격선 균형(일0.3%/승률50%/MDD-15%) 유지 OK?
- ORB 단일 전략 집중 vs 양수 시나리오 다수 병행 튜닝?
- Phase 3-A OOS 검증 통과 시 → 즉시 Phase 4 페이퍼 검증 진행 OK?

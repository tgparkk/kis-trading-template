# 2026-05-18 ORB OOS 검증 실패 — 폐기 + 재설계 결정

> ## [정정 2026-05-20] 이 문서의 "ORB 폐기" 결론은 보류됨 — 엔진 버그로 결과 오염
>
> 이 문서의 모든 OOS 결과는 **분봉 백테스트 엔진 버그로 오염**되었습니다.
>
> **버그**: `BacktestEngine.run_minute()`의 `trail_pct` 기본값이 `0.005`(0.5% 트레일링 스톱)이고, `scripts/run_intraday_tournament.py`가 이 값을 한 번도 명시적으로 넘기지 않음. 결과적으로 이 문서의 모든 ORB 토너먼트(5/16 60시나리오 풀, 5/17 30일 그리드, 5/18 OOS 8시나리오)가 **0.5% 트레일링 스톱을 강제로 뒤집어쓴 채** 실행됨. (`run_intraday_tournament.py` git 이력에 "trail" 언급 0건으로 확정.)
>
> **영향**: 분봉당 변동폭 ~0.2%인 변동성 상위 종목에서 0.5% 트레일은 +2~6% TP를 도달 불가능하게 만들어 수익:손실 비율(R:R)을 파괴함. A/B 진단(2026-05-20, orb 8거래일): trail OFF -4.59% vs trail ON -17.13%, TP 체결 85건 vs 17건. 이 문서의 "OOS MDD -58%", "일승률 34.6%"는 거의 전부 트레일 인공물로 추정됨.
>
> **결론**: 본문 §61의 **"분봉 ORB 폐기 확정"** 결정은 **무효/보류**. trail 버그 수정(2026-05-20: `run_minute` 기본값 0.005→None, 토너먼트에 `--trail` 옵션 추가) 후 ORB를 trail-OFF 정상 조건에서 재검증하기 전까지 ORB 사망 판정은 성립하지 않음.
>
> **단, 본문 §37-40의 "거래비용이 EV 잠식"(왕복 0.44%/거래) 진단은 여전히 유효** — 과매수(고회전) 문제는 trail과 별개로 남아 있음.
>
> 상세: [research-2026-05-20-daytrading-deep-dive.md](research-2026-05-20-daytrading-deep-dive.md), trail-OFF 재토너먼트 결과는 후속 changelog 참조.
>
> ---

## 한줄 요약
5/17 30일 우승자(ORB/dynamic/SL3%/TP6%) Phase 3-A·3-C 8개 시나리오 168일 OOS **전부 실패**. 168일 풀 토너먼트 60 시나리오도 합격 0 재확인. 분봉 ORB 폐기, 거래량 필터 + 시장환경 필터로 ORB v2 재설계 결재.

## Phase 3-A 결과 — 우승자 직접 OOS (2 시나리오)
| pos | SL | TP | 30일 일수익 | 168일 OOS 일수익 | 30일 승률 | OOS 승률 | OOS MDD |
|---|---|---|---|---|---|---|---|
| 4 | 3% | 6% | **+0.442%** | **-0.425%** | 59.4% | 34.6% | -58.0% |
| 5 | 3% | 6% | +0.359% | -0.376% | 62.5% | 35.8% | -52.5% |

- 결과: `RoboTrader_template/reports/tournament_orb_oos/20260518_073805/`
- 일승률 -25%p, MDD 7배 악화, Calmar 22.6 → -1.16
- **합격 0/2**

## Phase 3-C 결과 — 양수 시나리오 확장 OOS (6 시나리오)
| pos | SL | TP | 30일 일수익 | OOS 일수익 | OOS 승률 | OOS MDD |
|---|---|---|---|---|---|---|
| 3 | 3% | 4% | (음수) | **-0.753%** | 29.6% | -74.4% |
| 3 | 3% | 6% | +0.390% | -0.626% | 34.0% | -69.7% |
| 4 | 3% | 4% | +0.268% | -0.534% | 31.5% | -62.3% |
| 4 | 3% | 6% | +0.442% | -0.425% | 34.6% | -58.0% |
| 5 | 3% | 4% | +0.217% | -0.457% | 33.3% | -56.2% |
| 5 | 3% | 6% | +0.359% | -0.376% | 35.8% | -52.5% |

- 결과: `RoboTrader_template/reports/tournament_orb_oos_phase3c/20260518_082743/`
- 중복 2건(pos4,5 / SL3 TP6) Phase 3-A와 정확 일치 — **재현성 OK**
- 일승률 전부 BEP(33.3%) 근처/이하
- **합격 0/6**

## 30일 → 168일 표본 편향 진단 (scientist 에이전트)

### 원인 1: 시장 국면 편향
- 30일 IS(2026-04-01~05-15) = 관세전쟁 급락 후 **반등기**, ORB 패턴 우호
- WR 95% CI: IS [56.3%, 62.4%] vs OOS [33.2%, 35.9%] — 신뢰구간 겹침 없음

### 원인 2: 거래비용이 이론 EV 잠식 (핵심)
- OOS 이론 EV ≈ +0.11%/거래
- 왕복 비용 = slip 5bps + 수수료 0.03% + 거래세 0.18% ≈ **0.44%/거래**
- 실질 EV ≈ -0.33%/거래 × 5,007 거래 → 누적 -50% 손실 설명

### Phase 3-B SKIP 권고
1. SL/TP는 30일 384 그리드에서 이미 최적 도출 — 파라미터 공간 탐색 완료
2. 문제는 `box_minutes` 등 파라미터가 아니라 **진입 로직 자체** (`close > or_high` = 고점 진입 → 되돌림 내포)
3. 의미 있으려면 단순 튜닝이 아닌 재설계: 거래량 필터 / 시장환경 필터

## 168일 풀 토너먼트 재해석 (60 시나리오, 5/17 결과)
`RoboTrader_template/reports/tournament_round1/20260516_232527/`

| 전략 (dynamic) | 일수익 | 승률 |
|---|---|---|
| red_to_green | -0.33%/일 | 7.1% |
| support_resistance | -0.52%/일 | 2.2% |
| orb | -0.85%/일 | 3.1% |
| reversal_vwap | -1.01%/일 | 1.2% |
| vwap_trade | -1.19%/일 | 1.3% |
| 나머지 5종 | -1.3%~-1.5%/일 | 0~0.8% |

**현재 풀(10전략 × 2 universe × 3 pos = 60)에서 +EV 분봉 전략 0개**. screener universe는 거래량 부족 노이즈.

## 결재 사항 (사장님)
1. **분봉 ORB 폐기 확정**
2. **다음 단계: A. ORB 재설계 우선** (Scientist 권고 채택)
   - 거래량 필터: 돌파 시 전일 평균 3배 이상
   - 시장환경 필터: 당일 KOSPI 상승세 확인 후 ORB 가동
   - 보류된 옵션: 일봉 전략 강화 / 비용 구조 재검토 / 휴식
3. Changelog 작성 (이 문서)

## 신뢰성 한계 (Scientist 명시)
- skip_dates=202603(3월 전체 제거)의 이유 불명확 → OOS 선택 편향 가능성
- 월별 WR 분해 미실시 — 어느 달이 특히 나빴는지 미확인
- 30일 sells_by_reason 분포(TP/SL/EOD) 미확인

## 다음 세션 (Phase 4 — ORB v2)
- ORB v2 설계서 작성
- 거래량 필터 + 시장환경 필터 구현 → 신규 전략 `intraday/orb_v2/`
- 30일 + 168일 동시 평가 그리드 (overfit 차단)
- 통과 시 페이퍼, 미통과 시 ORB 자체 폐기 + 일봉 전략 전환

## 핵심 파일 경로
- ORB 전략: `RoboTrader_template/strategies/intraday/orb/strategy.py`
- ORB config: `RoboTrader_template/strategies/intraday/orb/config.yaml`
- 토너먼트 러너: `RoboTrader_template/scripts/run_intraday_tournament.py`
- 분봉 엔진: `RoboTrader_template/backtest/engine.py` (`run_minute(...)`)
- 평가 지표: `RoboTrader_template/backtest/tournament_metrics.py`

## 결과 파일
- Phase 3-A: `tournament_orb_oos/20260518_073805/tournament_round1_summary.md`
- Phase 3-C: `tournament_orb_oos_phase3c/20260518_082743/tournament_round1_summary.md`
- 5/17 30일 그리드: `tournament_grid/20260517_121928/tournament_round1_summary.md`
- 5/16 168일 풀: `tournament_round1/20260516_232527/tournament_round1_summary.md`

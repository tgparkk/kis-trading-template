# Elder Triple Screen — 백테스트 결과 리포트 (Book 7)

> Book: Alexander Elder — *Trading for a Living* (1993) / *The New Trading for a Living* (2014)
> 조사: [research.md](research.md) · 설계: [../../../docs/superpowers/specs/2026-05-29-elder-triple-screen-design.md](../../../docs/superpowers/specs/2026-05-29-elder-triple-screen-design.md)
> 실행: 2026-05-29 · universe top_volume:50 (49종목 로드) · 기간 daily_prices 전체(2021-01-04 ~ 2026-05-29, 종목별 평균 ~142봉)

---

## 1. 요약

Elder의 Triple Screen(3중 시간프레임 필터)을 한국 일봉 시장에 적응 구현. Screen 1(주봉 추세)을 **일봉 65일 EMA proxy**로, Screen 2(일봉 오실레이터)를 4개 변형(Force Index / Stochastic / Elder-Ray / EMA 눌림)으로, Screen 3(진입)을 **전일 고가+1틱 매수스톱(Approx A, 2일 trailing)**으로 코드화. 롱 전용(한국 공매도 제약).

**최고 룰: `triple_screen_ema_pullback` (Variant A)** — 134거래, **PnL +23.76%, Sharpe 1.22, Calmar 2.64, hit 56.4%**. 일봉 단독 룰 중 PnL은 Minervini volume_dryup(+20.27%)도 상회.

핵심 발견: **가장 단순한 셋업(EMA65 상승 + EMA13 터치 반등)이 정통 다지표 Triple Screen(Force Index·Elder-Ray)을 크게 앞섰다.** Minervini에서 단순 volume_dryup이 8조건 trend_template를 이긴 것과 같은 패턴 — 한국 BULL 구간에서는 복잡한 confluence보다 단순 추세-눌림이 우월.

---

## 2. 전체 결과 (Variant A/B × 4 single + all_AND)

### Variant A (sl 8% / tp 30% / EMA13 trail + ema65 추세반전 / mh 100)

| Rank | Rule | 거래 | PnL % | Sharpe | Calmar | MaxDD % | Hit | AvgHold |
|---|---|---|---|---|---|---|---|---|
| 1 | **triple_screen_ema_pullback** ⭐ | 134 | **+23.76** | **1.22** | 2.64 | 13.76 | 56.4% | 8.6 |
| 2 | triple_screen_stochastic | 43 | +9.32 | 0.91 | **6.95** | 5.21 | 41.7% | 5.0 |
| 3 | triple_screen_elder_ray | 73 | +8.66 | 0.25 | 1.01 | 10.00 | 34.5% | 6.5 |
| 4 | triple_screen_force_index | 48 | +6.05 | 0.54 | 1.26 | 7.86 | 35.3% | 5.7 |
| 5 | all_AND | 0 | 0.00 | — | — | — | — | — |

### Variant B (sl 8% / tp 12% / trail 없음 / mh 20)

| Rank | Rule | 거래 | PnL % | Sharpe | Calmar | MaxDD % | Hit | AvgHold |
|---|---|---|---|---|---|---|---|---|
| 1 | **triple_screen_ema_pullback** ⭐ | 149 | **+17.72** | **1.20** | 2.46 | 12.06 | 57.5% | 6.4 |
| 2 | triple_screen_stochastic | 41 | +8.40 | 0.99 | 4.39 | 5.33 | 45.6% | 5.0 |
| 3 | triple_screen_force_index | 45 | +4.89 | 0.52 | 1.17 | 7.82 | 34.9% | 5.3 |
| 4 | triple_screen_elder_ray | 76 | +3.44 | 0.19 | 1.15 | 9.20 | 37.5% | 5.2 |
| 5 | all_AND | 0 | 0.00 | — | — | — | — | — |

---

## 3. 룰별 분석

### triple_screen_ema_pullback (최고) ⭐
- **셋업**: EMA65(주봉 proxy) 상승 + 일봉 저가가 EMA13 1% 이내 터치 후 종가가 EMA13 위 회복 → 전일 고가 돌파 진입.
- A/B 모두 Sharpe 1.2+, hit 56~58%, 표본 충분(134~149). Variant A(tp30·trail)가 B(tp12)보다 PnL +6%p 우위 — Elder 추세추종 의도(수익 길게)가 적중.
- Triple Screen의 *정신*(추세 방향 눌림 매수)을 가장 간결히 구현한 형태가 최고 성과.

### triple_screen_stochastic
- 표본 적으나(41~43) Sharpe 0.9~1.0, **Calmar 최고(A 6.95)** — 위험 대비 보상 우수. MaxDD 5%대로 가장 방어적.
- 과매도(%K<30) + 상향 전환 진입이 깔끔한 눌림목 포착. 표본만 늘면 유망.

### triple_screen_force_index / triple_screen_elder_ray
- 정통 Elder 지표 조합이나 PnL 3~9%, Sharpe 0.2~0.5로 부진. elder_ray는 거래 많지만(73~76) hit 34~37%로 낮음.
- 다지표 동시 충족이 한국 BULL 구간에서 오히려 진입 타이밍을 늦추거나 노이즈 유입.

### all_AND = 0거래
- 4개 셋업 동시 충족은 사실상 불가(Force Index<0 눌림 vs EMA 회복 vs Stochastic<30 상호 배타적). 다른 책과 동일 현상.

---

## 4. 책 7권 통합 비교 (일봉 기준 베스트)

| 책 | 데이터 | 베스트 | PnL | Sharpe | 표본 |
|---|---|---|---|---|---|
| 아지즈 | 분봉 | bull_flag | -0.04% | -0.11 | 32T |
| Bellafiore | 분봉 | fade_vwap | +1.74% | +0.37 | 964T |
| Raschke | 분봉 | anti | +10.24% | -2.27 | 1,860T |
| O'Neil | 일봉+재무 | CANSLIM+패턴 | +7.04% | — | 7T |
| Minervini | 일봉 | volume_dryup B | +20.27% | **+1.41** | 153T |
| Weinstein | 주봉 | ma30w_bounce B | +4.18% | +0.30 | 43T |
| **Elder** | **일봉(주봉 proxy)** | **ema_pullback A** | **+23.76%** | **+1.22** | **134T** |

- **PnL**: Elder ema_pullback A(+23.76%) > Minervini(+20.27%) — 7권 일봉 최고 PnL.
- **Sharpe**: Minervini(1.41) > Elder(1.22) — 위험조정은 Minervini 우위.
- Elder는 지수 불필요·종목 자기완결로 구현 부담이 가장 적으면서 PnL 최상위.

---

## 5. 한계 및 주의

- **단일 BULL 구간 편향(최대 리스크)**: 종목별 유효기간 평균 ~142봉, 대부분 상승 구간. 롱 전용 추세추종이 과대평가될 수밖에 없음. **하락장 방어 미검증.**
- **표본 희소**: top_volume:50 종목 커버리지 불균등(13~100봉 종목 다수). 정통 셋업(stochastic 41~43T)은 표본 부족으로 신뢰구간 넓음.
- **적응판(adaptation)**: Screen 1을 일봉 65일 EMA proxy로 대체, 주봉 26주 EMA 미사용 — Elder 원전과 다름. "Triple Screen의 정신을 일봉으로 구현"한 것이지 원전 그대로가 아님.
- **Screen 3 근사**: 전일 고가+1틱 매수스톱을 일봉 Approx A(2일 trailing)로 시뮬 — 장중 실제 체결과 ~1틱 오차. minute_candles 정밀 체결은 미적용.
- **all_AND·force_index·elder_ray 부진**: 다지표 confluence가 이 데이터에서 알파를 내지 못함.

---

## 6. 결론

Elder Triple Screen의 *핵심 사상*(긴 추세 방향으로 짧은 눌림을 산다)을 가장 단순하게 구현한 `ema_pullback`이 7권 통틀어 일봉 최고 PnL(+23.76%)과 양호한 Sharpe(1.22)·hit(56%)를 동시에 달성. 다만 정통 다지표 셋업(Force Index·Elder-Ray)은 부진해, **"Triple Screen은 복잡할수록 좋지 않다"**는 역설적 교훈. BULL 편향·표본 희소·적응판 한계로 walk-forward 및 하락장 검증 후 CANDIDATE_ALPHAS 등록 검토 권장.

---

*leaderboard.parquet 기반. 결과 parquet: results_variant{A,B}_single_{rule}.parquet (8개).*

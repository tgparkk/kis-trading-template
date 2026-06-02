# 생존군(채택) 구현 충실도 감사 — Elder Triple Screen · Minervini VCP

> 감사일: 2026-06-02 · 감사 범위: 채택된 2책의 원문 대비 구현 정합성 4축 (매수후보 / 보유종목수 / 매수타이밍 / 매도타이밍)
> 대상: `strategies/books/{elder_triple_screen,minervini_vcp}` (백테스트) + `strategies/{elder_ema_pullback,minervini_volume_dryup}` (라이브) + `scripts/portfolio_sim_elder.py` + `scripts/exit_multiverse/`
> 범례: ✅ 충실 · ⚠️ 적응판/주의 · ❌ 불일치

---

## 1. Elder Triple Screen (채택: ema_pullback Variant A)

원문: Alexander Elder *Trading for a Living* / *The New Trading for a Living*. 3중 시간프레임 — Screen 1(주봉 추세) → Screen 2(일봉 오실레이터 역행 눌림) → Screen 3(장중 trailing buy-stop).

| 축 | 판정 | 근거 (1줄) |
|---|---|---|
| 매수후보(유니버스) | ⚠️ | Elder Screen 1은 "종목 자신의 주봉 추세"라 지수 불필요·종목 자기완결 → top_volume:50 풀은 책이 강제하지 않는 외부 필터(유동성 확보 목적), 책 후보정의와 직교하나 모순 아님. |
| 보유종목수(포트폴리오 K) | ✅ | `portfolio_sim_elder.py`가 단일계좌·max-K(종목당 균등비중)로 K=5/10/20 스윕 검증 완료(K=5 −7.5%→K=20 +93.3%, 분산도 극민감 확인). 라이브 config `max_capital_pct=0.20`+strategy `max_positions=5`로 한정자본 반영. |
| 매수타이밍(진입) | ⚠️ | 채택룰 ema_pullback은 Screen1(EMA65 상승)+Screen2(EMA13 눌림 회복)의 **단순화 적응판** — 정통 다지표(Force Index/Elder-Ray/Stochastic)가 아님. 주봉 26주 EMA→일봉 65일 EMA proxy, Screen3 "전일고가+1틱 매수스톱"은 백테스트에 충실(2일 trailing)하나 **라이브는 메타데이터로만 전달**(현재가 진입). 리포트가 한계로 명시함. |
| 매도타이밍(청산) | ✅ | Variant A = sl8/tp30/max_hold100/EMA13 trail(수익중)/EMA65 추세반전. 백테스트(`_elder_exit_reason`)·라이브(`evaluate_sell_conditions`)·exit_multiverse가 우선순위까지 1:1 일치. tp30은 책에 명시 익절 없는 "백스톱"임을 research가 정직히 기록. |

### Elder 핵심 지적
- **❗ touch_band 라이브-백테스트 드리프트**: 라이브 config `touch_band=1.02`(2026-06-02 멀티버스 적용) vs `report.md`/`research.md`는 여전히 **1.01** 기준 서술. 코드는 정합(config 1.02 = strategy default 1.02 = rule default 1.01을 인자로 오버라이드)이나, **리포트 문서가 1.01로 stale** → 1.02 근거(멀티버스 OOS) 반영 갱신 필요.
- 라이브 진입 체결 경로(현재가) ≠ 백테스트 매수스톱(stop-fill) — strategy docstring이 "미결 항목"으로 인정. 진입 신호 자체는 rule 직접 import로 1:1, 체결 정밀도만 차이.
- "Triple Screen의 정신을 일봉으로 구현"한 명시적 적응판 — 정통 confluence(force_index/elder_ray)는 부진해 미채택. 원문 그대로(주봉/장중 3프레임)는 아니나 사상은 보존, 한계 전면 표기 ✅.

---

## 2. Minervini VCP (채택: volume_dryup Variant B)

원문: Mark Minervini *Trade Like a Stock Market Wizard*. SEPA = Trend Template(8조건) + RS + VCP(변동성 수축) 패턴 + 펀더멘털.

| 축 | 판정 | 근거 (1줄) |
|---|---|---|
| 매수후보(유니버스) | ⚠️ | 책 SEPA는 Trend Template 8조건+RS≥70으로 후보를 강하게 게이팅. 라이브 채택룰(volume_dryup)은 **이 게이트 없이** top_volume:50 풀 전체에 거래량수축만 적용 → 책 후보정의의 부분집합/완화판. RS·TT는 백테스트 rules.py엔 구현되나 0~2거래로 사실상 무발사. |
| 보유종목수(포트폴리오 K) | ⚠️ | `portfolio_sim_elder.py --with-minervini`가 K=10 단일계좌 검증(+10.0%/Sharpe0.19/MaxDD52%) — **K 스윕은 K=10 한 점만**(Elder는 5/10/20 풀스윕). 라이브 config는 한정자본(max_capital_pct0.20, max_positions5) 반영. K 민감도 검증은 Elder 대비 얕음. |
| 매수타이밍(진입) | ❌→⚠️ | 책 시그니처 진입 = **VCP 베이스+피벗 돌파+RVOL≥1.5**(rule_vcp_breakout). 그러나 백테스트에서 vcp_breakout 2거래(통계무의미)로 무너지고, **채택된 것은 volume_dryup**(최근10봉 거래량≤직전30봉×0.7)뿐 — 피벗 돌파·RVOL·진폭 수축 단계 전부 빠진 **VCP의 일부 신호(dry-up)만** 채택. "VCP 구현"이라기보다 "거래량 수축 단독". 리포트가 이를 명시하므로 ⚠️로 완화하나, 책 핵심패턴 미구현은 사실. |
| 매도타이밍(청산) | ⚠️ | 채택 Variant B = sl8/tp12/max_hold20, **trail·trend_flip 없음**. 백테스트(`_minervini_exit_reason`)·라이브 1:1 일치 ✅. 단 책 의도(Variant A: tp≈2.5R/50MA trail/mh35)와 다른 "책간 획일" 청산을 채택 — 책 청산철학(R-multiple·50MA trail) 미반영. Sharpe B0.64 vs A0.03로 variant 의존 극심(strategy docstring 경고). |

### Minervini 핵심 지적
- **채택룰이 책 시그니처(VCP 돌파)가 아니라 보조신호(volume dry-up) 단독** — 원문 충실도가 Elder보다 낮음. report.md가 "trend_template 220봉 guard로 영구 False, vcp/tight 2거래"라고 정직히 한계 기록.
- 청산 Variant B는 책 의도(A)가 아닌 책간 비교용 획일값 — 성과 좋은 쪽(B) 선택은 합리적이나 "Minervini 본인 청산"은 아님. docstring·config 경고 충실.
- 단일 BULL 71.6% 편향·BEAR 39거래만 — 약세장 미검증, 리포트·docstring 모두 경고 ✅.

---

## 결론

**생존군은 포트폴리오 K 모델로 검증됐다 — 단, Elder만 충실(K=5/10/20 풀스윕), Minervini는 K=10 단일점에 그쳐 얕음.** 두 라이브 전략 모두 진입은 백테스트 rule을 직접 import해 신호 1:1 정합·한정자본(max_positions5/max_capital_pct0.20) 반영. 충실도 우려 2건: (a) Elder 리포트가 touch_band 1.01로 stale(코드는 1.02), (b) Minervini 채택룰이 책 시그니처 VCP 돌파가 아닌 volume dry-up 보조신호 단독 — 원문 패턴 핵심 미구현(리포트가 정직히 명시).

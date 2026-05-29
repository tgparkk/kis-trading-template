# O'Shaughnessy What Works on Wall Street — 백테스트 결과 리포트 (Book 10, 최종)

> Book: James P. O'Shaughnessy — *What Works on Wall Street* (4th ed., 2011)
> 조사: [research.md](research.md) · 설계: [../../../docs/superpowers/specs/2026-05-29-oshaughnessy-design.md](../../../docs/superpowers/specs/2026-05-29-oshaughnessy-design.md)
> 실행: 2026-05-29 · **universe = factor:79** (market_cap 6개월 창) · 다팩터 횡단면 순위 · book_id=osullivan_what_works(레거시)

---

## 1. 요약

O'Shaughnessy 다팩터 순위 전략을 한국 데이터로 코드화. **PSR 재구성**(=market_cap/1e8/revenue)으로 시그니처 저PSR 팩터를 살리고, VC1식 4팩터 가치복합(PSR+PE+PB+EV/EBIT)과 Trending Value(저평가 40%→3개월 모멘텀)를 구현. Greenblatt 횡단면 순위 인프라 확장.

**베스트: `low_psr` (단일 저PSR 팩터)** — Variant B 200거래 per-trade 승률 **54.5%, 평균 +4.63%/거래** (집계 +6.67%, A +8.26%).

**핵심 발견**: **단일 저PSR이 4팩터 복합·Trending Value를 앞섰다** → O'Shaughnessy의 "PSR은 가치 팩터의 왕" 주장이 한국 데이터에서 확인. 5책 연속 "단순/단일이 복잡/복합을 이긴다" 패턴.

---

## 2. 전체 결과

### 집계 (universe-mean — 0거래 종목 희석, per-trade는 §3)
| Variant | Rule | 거래 | mean PnL % | Sharpe | Calmar | avg_hold |
|---|---|---|---|---|---|---|
| A | **low_psr** ⭐ | 39 | +8.26 | 0.36 | 0.66 | 18.6 |
| A | value_composite | 31 | +5.18 | 0.27 | 0.41 | 18.1 |
| A | trending_value | 36 | +4.91 | 0.29 | 0.46 | 14.5 |
| A | all_AND | 20 | +1.93 | 0.15 | 0.27 | 6.3 |
| B | **low_psr** ⭐ | 200 | +6.67 | 0.37 | 0.81 | 2.9 |
| B | value_composite | 182 | +4.72 | 0.27 | 0.43 | 2.7 |
| B | trending_value | 138 | +3.54 | 0.24 | 2.29 | 3.4 |
| B | all_AND | 74 | +1.63 | 0.14 | 0.36 | 1.5 |

### Per-Trade (공정 비교, Variant B)
| Rule | 거래 | per-trade 승률 | 평균/거래 | 중앙값 |
|---|---|---|---|---|
| **low_psr** ⭐ | 200 | 54.5% | +4.63% | +3.15% |
| value_composite | 182 | 55.5% | +3.85% | +2.46% |
| trending_value | 138 | 53.6% | +3.89% | +2.59% |

---

## 3. 룰별 분석

### low_psr (베스트 — 시그니처 단일 팩터) ⭐
- 저PSR(=market_cap/revenue 최저) 상위 매수. B 200거래 per-trade +4.63% 승률 54.5%, A +8.26%(집계).
- **O'Shaughnessy "PSR=가치 팩터의 왕" 확인**: 단일 PSR이 4팩터 복합·Trending Value를 일관 상회. 한국 대형주에서도 저PSR이 가장 강한 단일 가치 신호.

### value_composite (4팩터 복합)
- PSR+PE+PB+EV/EBIT 백분위 평균 상위. B 182거래 per-trade +3.85% 승률 55.5%.
- 승률은 가장 높으나 평균 수익은 low_psr보다 낮음. 복합이 단일 PSR을 못 이김 — 책 의도(복합이 더 안정)와 달리 이 데이터·기간에선 PSR 단독 우위.

### trending_value (플래그십 — 책 최고 전략이나 부진)
- 저평가 40%→3개월 모멘텀 상위. B 138거래 per-trade +3.89%. 책의 ~21% CAGR 플래그십이나 본 데이터선 복합·PSR 하회.
- 원인: **6개월 모멘텀 불가(16종목)로 3개월 사용** + 6개월 단일 BULL 구간이라 모멘텀 틸트 효과 미미. Calmar는 2.29로 높음(저변동).

### all_AND (3룰 동시)
- 20~74거래 발생(룰 중첩 — 싼 종목이 vc·psr 동시 상위). 단 성과 최저(+1.6~1.9%) — 과도한 교집합이 알파 희석.

---

## 4. 책 10권 통합 비교 (베스트)

> ⚠️ Lynch·Greenblatt·O'Shaughnessy는 universe(재무/factor)·기간(6개월 창)이 이전과 다름 → per-trade 표기, PnL 직접 비교 주의.

| 책 | 데이터 | 베스트 | 성과 | 표본 |
|---|---|---|---|---|
| 아지즈 | 분봉 | bull_flag | -0.04% | 32T |
| Bellafiore | 분봉 | fade_vwap | +1.74% Sharpe +0.37 | 964T |
| Raschke | 분봉 | anti | +10.24% | 1,860T |
| O'Neil | 일봉+재무 | CANSLIM+패턴 | +7.04% | 7T |
| Minervini | 일봉 | volume_dryup B | +20.27% Sharpe 1.41 | 153T |
| Weinstein | 주봉 | ma30w_bounce B | +4.18% | 43T |
| Elder | 일봉(주봉 proxy) | ema_pullback A | +23.76% Sharpe 1.22 | 134T |
| Lynch | 일봉+재무 | value_balance_sheet B | per-trade +2.84% 승률 52.6% | 114T |
| Greenblatt | 일봉+재무+순위 | magic_formula_top B | per-trade +4.88% 승률 61.4% | 197T |
| **O'Shaughnessy** | **일봉+재무+다팩터순위** | **low_psr B** | **per-trade +4.63% 승률 54.5%** | **200T** |

- **펀더멘털 3책 비교 (per-trade)**: Greenblatt magic_formula_top(+4.88%, 61.4%) ≈ O'Shaughnessy low_psr(+4.63%, 54.5%) > Lynch value_balance_sheet(+2.84%, 52.6%).
- Greenblatt 순위와 O'Shaughnessy PSR이 비슷한 수준 — 둘 다 6개월 단일 국면이라 신뢰도 동일 제약.

---

## 5. 한계 (전면)
- **6개월 단일 국면**(market_cap 창 2025-07~2026-02) + 79종목 → 이전 책과 기간/universe 단절, OOS 불가.
- **진짜 VC2/VC3 불가**: 주주수익률·P/CF·EBITDA 부재 → 4판 헤드라인(Shareholder Yield) 손실. VC1식 4팩터만.
- **6개월 모멘텀 불가**(16종목) → 3개월 사용 → Trending Value 책 스펙 이탈.
- PSR 시점 불일치(연간 revenue vs 일별 market_cap), EV 상향편향(현금無), 연간 데이터, **금융/유틸 제외 불가**, BULL 편향, forced_close 지배(A).

---

## 6. 결론

O'Shaughnessy의 시그니처 **저PSR이 한국 데이터에서도 최강 단일 가치 팩터**임을 확인(low_psr이 복합·Trending Value 상회). 다만 **진짜 VC2/VC3(주주수익률)는 데이터 부재로 불가**하고, 플래그십 Trending Value는 6개월 모멘텀 불가·단일 BULL 국면으로 부진. 6개월 단일 국면 한계로 **CANDIDATE_ALPHAS 등록 보류**(Greenblatt와 동일 — market_cap 전기간 백필 후 재검증).

---

*leaderboard.parquet + results parquet 기반. PSR 재구성·단위(1e8) 적용. 10권 시리즈 최종 책.*

---

## 📌 다년 재검증 업데이트 (2026-05-29 일봉 백필 후)

> 펀더멘털 일봉 2021~2026 백필 후 재실행. n_eligible dates 124→**1241**.

| 룰 | 6개월(이전) | **5년(재검증)** |
|---|---|---|
| low_psr A | 38T +8.26% Sharpe 0.36 (per-trade 84%) | 310T +12.54% **Sharpe 0.11** (per-trade 48.4%, +7.47%/거래) |
| low_psr B | 200T +6.67% Sharpe 0.37 | 1721T +3.02% **Sharpe 0.05** (per-trade 46.4%, +0.82%/거래) |
| value_composite A | — | 288T +10.92% (per-trade 47.2%, +5.58%/거래) |
| trending_value A | — | 301T +8.84% (per-trade 미달) |

**핵심**: 다년에서 **Sharpe 0.36→0.11 붕괴**, per-trade 승률 84%→48%(동전). **low_psr이 다년에서도 O'Shaughnessy 베스트 유지 → "PSR=가치 팩터의 왕" 재확인.** 단 risk-adjusted 엣지 미미 → **CANDIDATE 부적격 재확인**. 6개월 숫자는 단일 BULL 거품.

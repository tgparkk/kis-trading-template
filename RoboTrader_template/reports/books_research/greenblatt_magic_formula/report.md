# Greenblatt Magic Formula — 백테스트 결과 리포트 (Book 9)

> Book: Joel Greenblatt — *The Little Book That (Still) Beats the Market* (2006/2010)
> 조사: [research.md](research.md) · 설계: [../../../docs/superpowers/specs/2026-05-29-greenblatt-magic-design.md](../../../docs/superpowers/specs/2026-05-29-greenblatt-magic-design.md)
> 실행: 2026-05-29 · **universe = magic:79** (market_cap 보유, 6개월 창) · 일봉 + 분기재무 PIT(105일 lag) + 횡단면 순위

---

## 1. 요약

Greenblatt Magic Formula(이익수익률 EBIT/EV + 자본수익률 ROC, 순위 합산 상위 N 매수)를 한국 재무 데이터로 코드화. **횡단면 순위**(Minervini RS 주입 + Lynch PIT 조인 결합).

**베스트: `magic_formula_top` (순위 상위 20)** — Variant B 197거래 per-trade 승률 **61.4%, 평균 +4.88%/거래**. **펀더멘털 2책(Lynch·Greenblatt) 통틀어 최고 표본·per-trade 성과.**

**핵심 발견 2가지**:
1. **순위(상대) 룰은 작동, 절대 임계값 룰은 사망**: magic_formula_top(순위)는 197거래 양호하나, threshold(EY>0.10 AND ROC>0.25)·high_roc_value(ROC>0.40)는 **0거래** — Greenblatt 미국 기준 ROC>25%가 한국 대형주 universe에서 도달 불가(ROC max 24.7%). → Magic Formula의 본질인 **상대 순위**가 절대 임계값보다 이식성 우월.
2. **6개월 단일 국면 한계**: market_cap이 2025-07-31~2026-02-02만 존재 → 순위 변형은 6개월·79종목만.

---

## 2. 전체 결과

> ⚠️ market_cap 단위 버그(원 vs 억원 1e8배) 수정 후 결과. 수정 전 EY≈0으로 순위가 ROC 단독이었음 → 수정으로 EY 정상 반영(p50 5.2%, p90 11.7%).

### 집계 (universe-mean — 0거래 종목 희석, per-trade는 §3)
| Variant | Rule | 거래 | mean PnL % | Sharpe | Calmar | MaxDD % | avg_hold |
|---|---|---|---|---|---|---|---|
| A | magic_formula_top | 38 | +10.04 | 0.41 | 0.70 | 4.13 | 18.1 |
| B | magic_formula_top | 197 | +8.07 | 0.36 | 0.64 | 3.86 | 3.0 |
| A/B | magic_formula_threshold | 0 | — | — | — | — | — |
| A/B | high_roc_value | 0 | — | — | — | — | — |
| A/B | all_AND | 0 | — | — | — | — | — |

### Per-Trade (공정 비교)
| Variant | Rule | 거래 | per-trade 승률 | 평균/거래 | 중앙값 | 청산 분포 |
|---|---|---|---|---|---|---|
| **B** | **magic_formula_top** ⭐ | 197 | 61.4% | +4.88% | +4.18% | TP 79·SL 47·mh 43·forced 28 |
| A | magic_formula_top | 38 | 84.2% | +32.29% | +23.11% | **forced 31**·mh 3·TP 3·SL 1 |

---

## 3. 룰별 분석

### magic_formula_top (순위 기반 — 유일 작동, 베스트) ⭐
- EY·ROC 각 순위 합산 상위 20 매수. 일자별 적격 universe 평균 66종목(min 26)에서 순위 → 충분.
- **Variant B (197거래)**: per-trade 승률 61.4%, 평균 +4.88%, 중앙값 +4.18%. 청산 균형(TP 79/SL 47/mh 43) → 신뢰도 높음. **펀더멘털 책 최고 표본.**
- **Variant A (38거래)**: per-trade 승률 84.2%, 평균 +32.29% — 그러나 **forced_close 31/38**(상승장에서 데이터 종료까지 보유, tp 0.99로 사실상 매도 안 함). BULL 윈도 + 짧은 이력의 buy-and-hold 베타에 가까움 → 과대평가 주의. mh 120이 데이터 경계에 막힘.

### magic_formula_threshold / high_roc_value (0거래 — 절대 임계값 사망)
- EY>0.10 AND ROC>0.25 동시 충족 0건. **ROC max=0.2473** (한국 대형주 영업이익/(총자산−유동부채)가 25% 미만) → Greenblatt 미국 기준 ROC>25%가 구조적으로 도달 불가.
- EY>0.10은 1,310 bars 존재하나 ROC>0.25가 0이라 교집합 0. high_roc_value(ROC>0.40)는 더 불가.
- **결론: 절대 임계값은 미국 캘리브레이션이라 한국 대형주에 부적합. 상대 순위만 이식 가능.**

### all_AND = 0거래 (3룰 동시 불가)

---

## 4. 책 9권 통합 비교 (베스트)

> ⚠️ Greenblatt·Lynch는 universe(재무/magic) 및 기간(6개월 창)이 이전 책과 다름 → PnL 직접 비교 주의. per-trade 표기.

| 책 | 데이터 | 베스트 | 성과 | 표본 |
|---|---|---|---|---|
| 아지즈 | 분봉 | bull_flag | -0.04% | 32T |
| Bellafiore | 분봉 | fade_vwap | +1.74% Sharpe +0.37 | 964T |
| Raschke | 분봉 | anti | +10.24% | 1,860T |
| O'Neil | 일봉+재무 | CANSLIM+패턴 | +7.04% | 7T |
| Minervini | 일봉 | volume_dryup B | +20.27% Sharpe 1.41 | 153T |
| Weinstein | 주봉 | ma30w_bounce B | +4.18% | 43T |
| Elder | 일봉(주봉 proxy) | ema_pullback A | +23.76% Sharpe 1.22 | 134T |
| Lynch | 일봉+재무(PIT) | value_balance_sheet B | per-trade +2.84% 승률 52.6% | 114T |
| **Greenblatt** | **일봉+재무+순위(6개월)** | **magic_formula_top B** | **per-trade +4.88% 승률 61.4%** | **197T** |

- **펀더멘털 2책 비교**: Greenblatt magic_formula_top B(per-trade +4.88%, 승률 61.4%, 197T) > Lynch value_balance_sheet B(+2.84%, 52.6%, 114T). 횡단면 순위가 Lynch 단일 스크린보다 우월.
- 단 Greenblatt는 6개월 단일 국면(market_cap 창) → 신뢰도 제약.

---

## 5. 한계 (전면)

- **6개월 단일 국면**: market_cap 2025-07-31~2026-02-02만 → 순위 변형 124일·79종목. 이전 8권과 기간/universe 비교성 단절.
- **EV 상향 편향**: 현금 컬럼 없음 → EV=시총+총부채, 현금 미차감 → EY 과소(현금부자 종목 불리).
- **단위 버그 수정**: market_cap(원) vs 재무(억원) 1e8배 불일치를 발견·수정(/1e8). 수정 전 EY≈0이라 순위가 ROC 단독이었음.
- **절대 임계값 미국 캘리브레이션**: ROC>25%/EY>10% 한국 대형주 부적합(0거래).
- **영업권/무형자산 ROC 분모 포함**(Greenblatt는 제외) → ROC 하향. **금융·유틸 제외 불가**(섹터 컬럼 없음) → 순위 오염 가능.
- **Variant A forced_close 지배**(31/38): 짧은 이력 + BULL → buy-and-hold 베타. A의 +32%/거래 과대.
- 연간 데이터(15개월 stale 가능), 생존편향, BULL 편향.

---

## 6. 결론

Magic Formula의 **횡단면 순위**(magic_formula_top)는 한국 데이터에서 작동 — Variant B 197거래 per-trade +4.88% 승률 61.4%로 **펀더멘털 책 최고 표본·성과**. 반면 **절대 임계값 룰은 미국 기준이라 전멸**(ROC>25% 도달 불가) → "Magic Formula의 본질은 절대 기준이 아닌 상대 순위"임을 한국 데이터가 입증.

다만 **6개월 단일 국면**(market_cap 창) + EV 상향편향 + 연간 데이터로 신뢰도 제약. market_cap 전 기간 백필 + 현금/섹터 컬럼 확보 후 재검증 필요. **CANDIDATE_ALPHAS 등록 보류**(6개월·단일국면 — Lynch보다는 유망하나 기간 부족).

---

*leaderboard.parquet(집계) + results_variant{A,B}_single_*.parquet(per-trade) 기반. market_cap 단위 수정 후 재실행.*

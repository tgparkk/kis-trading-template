# 문병로 메트릭 스튜디오 — 백테스트 리포트 (Book 11, 한국 저자 1호)

> 작성 2026-05-30 · 한국 시장 특화 가치투자(첫 한국 저자 책)
> 다팩터 횡단면 순위 + 소형주 틸트. O'Shaughnessy(Book 10) 인프라 확장(book_id=`moonbyungro_metric`).
> **펀더멘털 책 최초로 다년(2021~2026)·다국면 검증** — market_cap 5년 백필 + PCR(영업현금흐름) Phase 0 백필 덕분.

---

## 1. 데이터 / 설정

- **기간**: 2021-01-04 ~ 2026-05-29 (1,241 거래일, 5.4년 — BEAR 2022 포함)
- **universe**: factor_kr:131 (financial_statements 보유 종목, market_cap 128종목)
- **5팩터** (모두 cheap=low, 단위 억원 1e8 환산):
  - PBR=pbr, PER=per, PSR=(mc/1e8)/revenue, POR=(mc/1e8)/operating_profit, **PCR=(mc/1e8)/operating_cash_flow**
  - op>0·ocf>0·revenue>0·mc>0 가드 + POR/PCR 캡 100
- **5팩터 적격 교집합**: 거래일별 n_eligible min=12 / median=52 / max=65 (6개월 창 대비 대폭 개선)
- **PCR 반영 표본**: 63,833 (code,date) — 전 적격 표본에 PCR 반영
- 팩터 분포(정상): PSR median 0.43, POR median 6.57, PCR median 5.21
- PIT 재무조인 105일 lag, no-lookahead, 거래비용 왕복 0.41%, 롱 전용

---

## 2. 결과 — variant × 룰 (집계 PnL = 종목별 equity 평균, Sharpe 동일 척도)

### Variant K (sl 17.5% / tp off / mh 250 — 문병로 -17.5% 손절 + 연1회 보유)

| 룰 | 거래 | 집계 PnL | Sharpe | per-trade 승률 | per-trade 평균 |
|---|---|---|---|---|---|
| **value_composite_kr** ⭐ | 218 | **+13.68%** | **0.09** | 40.4% | +0.10% |
| small_value | 213 | +6.99% | 0.06 | 39.0% | +0.09% |
| low_pbr (시그니처) | 166 | +3.29% | 0.04 | 36.7% | +0.06% |
| all_AND | 41 | +1.68% | 0.01 | — | — |

### Variant A (sl 20% / tp off / mh 120)

| 룰 | 거래 | 집계 PnL | Sharpe | per-trade 승률 | per-trade 평균 |
|---|---|---|---|---|---|
| **value_composite_kr** ⭐ | 301 | **+13.37%** | **0.09** | 46.8% | +0.06% |
| small_value | 289 | +6.26% | 0.06 | 46.0% | +0.06% |
| low_pbr | 250 | +3.07% | 0.04 | 46.4% | +0.03% |
| all_AND | 50 | +0.68% | 0.01 | — | — |

### Variant B (sl 8% / tp 12% / mh 20 — 빠른 청산)

| 룰 | 거래 | 집계 PnL | Sharpe |
|---|---|---|---|
| value_composite_kr | 1,670 | +4.46% | 0.02 |
| low_pbr | 1,578 | -1.09% | 0.01 |
| small_value | 1,703 | -0.13% | 0.01 |
| all_AND | 258 | +0.46% | 0.00 |

### Variant K + 4월 리밸런싱 게이트 (--april-only)

| 룰 | 거래 | 집계 PnL | Sharpe |
|---|---|---|---|
| low_pbr | 102 | +5.36% | 0.04 |
| value_composite_kr | 99 | +7.63% | 0.03 |
| small_value | 100 | +4.78% | 0.03 |
| all_AND | 15 | +0.44% | 0.00 |

---

## 3. 핵심 발견

1. **5팩터 복합(value_composite_kr)이 문병로 베스트** — K +13.68% / A +13.37%. 저PBR 단독·소형주를 모두 압도. 다년 펀더멘털 책 중 양호한 절대 PnL.
2. **문병로 시그니처 명제 "한국=저PBR 민감"은 다년 검증 시 약함** — low_pbr 단독이 K +3.29%(승률 36.7%)로 3룰 중 최하. 6개월 단일 BULL이 아닌 5.4년 다국면에서는 **저PBR 단독 엣지가 5팩터 복합에 크게 밀린다**. 명제 **부분 반박**: 가치는 복합으로 써야 하고 저PBR 단독으로는 부족.
3. **소형주×가치(small_value)는 중간** — K +6.99%. 진성 마이크로캡 부재(최소 시총 587억)로 소형주 효과가 약화됐을 가능성.
4. **장기보유(K/A) > 단기청산(B)** — 펀더멘털은 mh 120~250이 mh 20보다 우월(B는 -1~+4%로 부진). 가치투자 = 장기보유 확인.
5. **4월 게이트는 PnL을 낮추지 않음** — 연 1회 리밸런싱(99~102거래)으로도 상시 신호와 유사 PnL → 회전율 절감 여지.

## 4. ⚠️ Sharpe 붕괴 — 펀더멘털 4책째 동일 결론

- **모든 룰 Sharpe 0.01~0.09**. 기술적 베스트 Elder ema_pullback A(0.68)·Minervini volume_dryup B(0.64)에 **크게 미달**.
- **per-trade 승률 40~47%**(다년) — 6개월 창의 펀더멘털 책들(O'Shaughnessy low_psr 54.5%, Greenblatt 61.4%)보다 낮음. **단일 BULL 6개월 숫자가 거품이었다는 패턴 재확인**(backfill-revalidation 교훈과 동일).
- 절대 PnL +13%는 5.4년 누적 → CAGR ~2.4%로 미미. 위험조정 후 사실상 무엣지.

## 5. 결론

- **문병로 5팩터 복합은 한국 다년 데이터에서 양(+) 절대 PnL을 내지만 risk-adjusted 엣지는 미미**(Sharpe 0.09). 펀더멘털 단독 책(Lynch/Greenblatt/O'Shaughnessy)에 이은 **4책째 동일 결론** — 가치 팩터는 방향성은 맞으나 다국면에서 Sharpe가 붕괴한다.
- **문병로 핵심 명제(저PBR 민감)는 단독으로는 다년 검증을 통과하지 못함** — 5팩터 복합으로만 의미 있는 PnL. 한국 첫 저자책의 시그니처 주장이 데이터로 부분 반박된 것이 이 책의 가장 큰 발견.
- **CANDIDATE_ALPHAS 등록 부적격** — Sharpe 0.09. 기술적 추세추종(Elder/Minervini)만 다년 Sharpe 0.6대로 생존한다는 시리즈 결론을 한 번 더 굳힘.

## 6. 한계

- PCR은 2015+만(DART XBRL 한계), 2014 이하는 4팩터 fallback — 다만 적격 교집합 median 52로 충분.
- 진성 마이크로캡 부재(최소 시총 587억) → 소형주 효과 약화 가능.
- 이자보상배율 필터 불가(이자비용 컬럼 부재) — 문병로 필터 1개 제외.
- 4월 리밸런싱은 캘린더 근사(종목별 실제 공시일 미반영), 연간 재무(분기 아님) 105일 lag 근사.
## 7. 국면 분해 (BULL/BEAR/SIDEWAYS, 2026-05-30 추가)

> KOSPI 20일±2% 라벨(Elder/Minervini 동일). BULL 39.3%/BEAR 29.3%/SIDEWAYS 31.4%(1,304일), 2022=BEAR. 가치룰은 보유 176~210일로 다국면 횡단 → **entry 기준**(진입 국면)과 **exit 기준**(청산 국면) 모두 산출. 상세: [regime_split.md](regime_split.md)

### BEAR per-trade (핵심 질문 — 저PBR/소형주의 약세장 방어)
| 룰 | entry-BEAR | exit-BEAR |
|---|---|---|
| value_composite_kr K | +5.00% (98) | −8.38% (110) |
| low_pbr K (시그니처) | +1.28% (88) | −6.36% (89) |
| small_value K | +7.66% (104) | −9.03% (110) |
| low_pbr A | **−1.68%** (86) | −9.14% (84) |

- **결론 — 방어의 성격이 Elder와 다름**: 문병로 가치룰은 BEAR 국면 *안에서* 버는 방어(exit-BEAR 전부 음수)가 아니라, **BEAR에 싸게 진입→BULL에 청산하는 역발상 매수 우위**(entry-BEAR 양수). Elder ema_pullback A는 BEAR 국면 내 자기완결 +3.01%(진짜 약세장 방어)인 반면, 문병로는 **장기보유 전제에서만** 약세장 진입이 보상된다.
- **저PBR 명제의 조건부 반박**: low_pbr의 BEAR entry 방어는 **긴 보유(variant K) +1.28%에서만 양수, 짧은 보유(variant A) −1.68%로 붕괴**. 저PBR의 약세장 방어는 "충분히 오래 들고 갈 때만" 성립하는 조건부 명제.

## 8. 한계
- PCR은 2015+만(DART XBRL 한계), 2014 이하는 4팩터 fallback — 적격 교집합 median 52로 충분.
- 진성 마이크로캡 부재(최소 시총 587억) → 소형주 효과 약화 가능.
- 이자보상배율 필터 불가(이자비용 컬럼 부재).
- 4월 리밸런싱은 캘린더 근사, 연간 재무(분기 아님) 105일 lag 근사.

---

상세 데이터: `results_variant{K,A,B}[_apr]_{mode}_{rule}.parquet` (17파일) · 공통 `../leaderboard.parquet`
Phase 0(OCF 백필): [phase0_ocf_backfill.md](phase0_ocf_backfill.md)

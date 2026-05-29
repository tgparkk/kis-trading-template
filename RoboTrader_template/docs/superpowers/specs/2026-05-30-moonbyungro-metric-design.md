# 문병로 메트릭 스튜디오 — 백테스트 설계서 (Book 11, 한국 저자 1호)

> 조사: [reports/books_research/moonbyungro_metric/research.md](../../../reports/books_research/moonbyungro_metric/research.md) (작성 예정)
> 작성: 2026-05-30 · 한국 시장 특화 가치투자(첫 한국 저자 책)
> O'Shaughnessy(Book 10) 횡단면 순위 인프라 확장. book_id=`moonbyungro_metric`.
> **결정사항(사장님)**: PCR 백필 후 **5팩터 완전체**로 진행. market_cap은 5년 백필(2021~2026) 확보됨 → 다년·다국면 검증 가능(펀더멘털 책 최초).

---

## 0. 설계 원칙

1. **다팩터 횡단면 순위 + 소형주 틸트** — O'Shaughnessy `run_oshaughnessy_value.py` 복제·확장(80% 재사용). `_build_cross_sectional_ranks`에 POR·소형주 순위 추가.
2. **문병로 핵심 명제 검증**: "한국 시장은 특히 저PBR에 민감" — `rule_low_pbr` 단독 성과를 다년 데이터로 직접 검증/반박.
3. **5팩터 완전체**(PBR·PER·PSR·POR·PCR). PSR/POR/PCR은 재구성. **PCR은 영업현금흐름 백필(Phase 0) 선행 필요**.
4. **소형주 효과** — market_cap 횡단면 하위 게이트를 명시적 팩터로(O'Shaughnessy엔 없던 축).
5. **연 1회 4월 리밸런싱** — 진입을 4월 영업일로 게이트(전년 재무 공시 반영). 상시 신호 버전과 둘 다 측정해 비교.
6. PIT 재무조인(105일 lag, `_build_fund_by_idx`), 롱 전용, 거래비용 동일(왕복 0.41%).

---

## Phase 0. 데이터 선행작업 — PCR 백필 (필수, 코드화 전)

PCR(주가/영업현금흐름)은 현재 DB에 **영업현금흐름 컬럼이 전무**(`financial_statements`·`financial_data` 모두 information_schema 0건). 5팩터 완전체를 위해 백필 선행.

1. **컬럼 추가**: `financial_statements.operating_cash_flow numeric(20,2)` (또는 별도 테이블).
2. **소스**: DART 전자공시 OpenAPI(현금흐름표 영업활동현금흐름) 또는 KIS 재무 API. universe 131종목 × 연간(2004~2025) report_date 매칭.
3. **백필 스크립트**: `scripts/backfill_operating_cash_flow.py` 신규. 멱등(INSERT/UPDATE, 기존 행 NULL만 채움), report_date 정합.
4. **검증**: ocf NULL 비율·종목 커버리지·값 범위. ocf>0 비율 확인(영업현금흐름 음수 기업 가드).
5. **막히면**: DART에 일부 종목/연도 부재 시 그 구간 PCR만 NULL 처리(4팩터로 fallback) — design 한계에 명시. 전면 부재면 사장님께 재보고.

> Phase 0 미완 시 PBR/PER/PSR/POR 4팩터로 먼저 코드화 가능하나, 사장님 결정은 5팩터 완전체이므로 Phase 0을 코드화 1단계로 둔다.

---

## 1. 팩터 (가용 컬럼 + 백필)

```
PBR  = pbr                                     # 직접, 61% non-null, pbr>0
PER  = per                                     # 직접, 54% non-null, per>0
PSR  = (market_cap/1e8) / revenue              # 재구성. revenue>0 (99.9% present)
POR  = (market_cap/1e8) / operating_profit     # 재구성. op>0 가드(음수 285건 제외) + 캡
PCR  = (market_cap/1e8) / operating_cash_flow  # 재구성. Phase 0 백필 후. ocf>0 가드 + 캡
small_cap = market_cap 오름차순                # 소형주 틸트(하위 게이트)
```
- 5팩터 모두 cheap=low. 가드 위반 시 해당 팩터/종목 부적격.
- POR/PCR 분모 작을 때 캡(O'Shaughnessy EV/EBIT 캡 패턴 재사용).
- 단위 환산 1e8(원→억원) 필수 — 기존 책들과 동일(market_cap 단위버그 주의).

---

## 2. 횡단면 순위 (`_build_cross_sectional_ranks` 확장)

거래일 D마다, 5팩터 모두 유효한 적격 교집합에서:
1. 각 팩터 백분위(cheap=high): `pct_f = 1 - (rank_asc-1)/(N-1)`.
2. `vc_score = mean(pct_pbr, pct_per, pct_psr, pct_por, pct_pcr)`.  # 5팩터 가치복합
3. `vc_rank` = vc_score 내림차순 dense ordinal(1=최저평가).
4. `pbr_rank` = PBR 오름차순(1=최저) — 문병로 시그니처.
5. `smallvalue_rank`: market_cap 하위 40% 게이트 → 그 부분집합에서 vc_score 내림차순 dense ordinal.
6. `n_eligible` = 적격 수. MIN_ELIGIBLE=10.

주입: `ctx_extra = {"fund":fund_by_idx[i], "vc_rank":..., "pbr_rank":..., "smallvalue_rank":..., "n_eligible":...}`
- no-lookahead: 거래일 D의 PIT fund(105일 lag) + 당일 market_cap + close[..D]만.

---

## 3. 룰 3종 (확정)

### rule_low_pbr (시그니처, conf 72, top_n=20, min_eligible=10)
```
pbr_rank is not None AND n_eligible>=min_eligible AND pbr_rank<=top_n
```
> 문병로 핵심 명제("한국=저PBR 민감") 직접 검증.

### rule_value_composite_kr (주력, conf 75, top_n=20)
```
vc_rank is not None AND n_eligible>=min_eligible AND vc_rank<=top_n
```
> 5팩터(PBR+PER+PSR+POR+PCR) 가치복합.

### rule_small_value (플래그십, conf 78, top_n=20)
```
smallvalue_rank is not None AND smallvalue_rank<=top_n
```
> 소형주×가치 — 문병로 소형주 효과.

```
ALL_RULES = [rule_low_pbr, rule_value_composite_kr, rule_small_value]
```

---

## 4. 청산 Variant

| Variant | sl | tp | trail | mh | 비고 |
|---------|-----|-----|-------|-----|------|
| **K** | **0.175** | 0.99(off) | 없음 | 250 | 문병로 -17.5% 손절 + 연 1회 보유 |
| A | 0.20 | 0.99(off) | 없음 | 120 | 기존 책 비교용 |
| B | 0.08 | 0.12 | 없음 | 20 | 빠른 청산 비교용 |

- warmup 20. forced_close 지배 명시.
- **4월 리밸런싱 게이트**(옵션 `--april-only`): 진입 신호를 4월 영업일에만 허용. 기본은 상시 신호 + 게이트 버전 둘 다 측정.

---

## 5. 코드 산출물

```
strategies/books/moonbyungro_metric/
├── __init__.py
├── rules.py      # _num + 룰 3종(low_pbr/value_composite_kr/small_value) + ALL_RULES
└── strategy.py   # MoonByungroMetricStrategy(BookStrategy) + BOOK_META + build_strategy
scripts/backfill_operating_cash_flow.py   # Phase 0: 영업현금흐름 백필(DART/KIS)
scripts/run_moonbyungro_metric.py         # O'Shaughnessy 복제 + POR/PCR/소형주 + sl0.175 + 4월 게이트
```

- strategy.py: holding_period="swing". BOOK_META id="moonbyungro_metric", name="문병로 메트릭 스튜디오", category="fundamental_factor_rank_kr", data_granularity="daily".
- run 스크립트(O'Shaughnessy 복제 후 확장):
  - `_load_fundamentals_universe`(131), `_load_daily_adj`(+market_cap 비조정), `_build_fund_by_idx` 확장(_FS_NUM_COLS에 operating_profit·operating_cash_flow·per·pbr·revenue; fund에 pbr/per/psr/por/pcr + market_cap).
  - `_build_cross_sectional_ranks` 확장: vc_rank(5팩터)/pbr_rank/smallvalue_rank/n_eligible.
  - simulate ctx_extra 4키 주입. warmup 20. `--april-only` 게이트.
  - **run-script 주석의 "6개월 창" 경고 삭제** — market_cap 5년 백필(median 1,215일) 확보됨.
  - leaderboard book_id="moonbyungro_metric", universe=f"factor_kr:{n_with_mc}", period="daily_full", reports-dir "reports/books_research/moonbyungro_metric".
- **실행 RoboTrader_template/ cwd**.

---

## 6. 백테스트 실행
```
# Phase 0 선행
python scripts/backfill_operating_cash_flow.py
# 본 백테스트
python scripts/run_moonbyungro_metric.py --variant K --all-modes
python scripts/run_moonbyungro_metric.py --variant K --all-modes --april-only
python scripts/run_moonbyungro_metric.py --variant A --all-modes
python scripts/run_moonbyungro_metric.py --variant B --all-modes
```

## 7. 검증
- pytest tests/books/ 통과. no-lookahead: 순위가 D 데이터만. n_eligible·forced_close·per-trade 기록.
- **다년 검증 핵심**: 펀더멘털 3책처럼 단일 BULL이 아니라 2021~2026 다국면 → 4월 리밸런싱·소형주·저PBR이 BEAR(2022)에서도 작동하는지 확인. Sharpe 붕괴 여부를 Elder/Minervini와 같은 잣대로 평가.
- PCR 백필 정합성: ocf 커버리지·NULL 비율·5팩터 적격 종목수.

## 8. 한계 (전면)
- **PCR은 Phase 0 백필 성공 시에만 5팩터** — DART 부재 구간은 4팩터 fallback.
- **이자보상배율 필터 불가** — 이자비용 컬럼 부재(문병로 필터 1개 제외).
- 131종목 한정 universe, 금융/유틸 제외 불가(industry 컬럼 financial_statements에 없음).
- 진성 마이크로캡 부재(최소 시총 587억) — 소형주 효과 약화 가능.
- 4월 리밸런싱은 캘린더 근사(종목별 실제 공시일 미반영).
- 연간 재무(분기 아님) — 공시 시차 105일 lag 근사.

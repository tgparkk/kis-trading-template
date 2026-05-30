# Book 11 문병로 Phase 1+2 — 5팩터 코드화 + 다년 백테스트 (2026-05-30)

## Phase 1 — 코드화
- 신규 `strategies/books/moonbyungro_metric/{__init__,rules,strategy}.py` — 룰 3종(rule_low_pbr/value_composite_kr/small_value, ctx 주입 순위만 읽음) + MoonByungroMetricStrategy(holding_period="swing").
- 신규 `scripts/run_moonbyungro_metric.py` — O'Shaughnessy 복제·확장. 5팩터(PSR/POR/PCR 재구성, 1e8 억원, op>0·ocf>0 가드 + 캡100) + vc_rank/pbr_rank/smallvalue_rank/n_eligible 횡단면 순위 + variant K/A/B + `--april-only` 게이트.
- 신규 테스트 `tests/books/test_moonbyungro_rules.py` 21개 → **pytest tests/books/ 69 passed**(회귀 0). base API 정합 검증 완료(무수정).
- 파일럿 검증 통과: 신호 발생, n_eligible>0, PCR 반영, 단위 정상.

## Phase 2 — 다년 백테스트 (2021-01-04 ~ 2026-05-29, 1,241일, universe 131)
> 풀 백테스트는 서브에이전트가 백그라운드 유지 못해(Phase 0에서 확인) **매니저가 하니스 run_in_background로 4종 순차 실행**. 전부 exit 0.
> n_eligible median 52(6개월 창 대비 대폭↑), PCR 반영 63,833 (code,date). PSR med 0.43 / POR 6.57 / PCR 5.21(정상).

### 룰별 결과 (집계 PnL = 종목별 equity 평균)
| variant | 룰 | 거래 | PnL | Sharpe | per-trade 승률 |
|---|---|---|---|---|---|
| K | **value_composite_kr** ⭐ | 218 | **+13.68%** | **0.09** | 40.4% |
| K | small_value | 213 | +6.99% | 0.06 | 39.0% |
| K | low_pbr(시그니처) | 166 | +3.29% | 0.04 | 36.7% |
| A | value_composite_kr | 301 | +13.37% | 0.09 | 46.8% |
| A | low_pbr | 250 | +3.07% | 0.04 | 46.4% |
| A | small_value | 289 | +6.26% | 0.06 | 46.0% |
| B | value_composite_kr | 1670 | +4.46% | 0.02 | — |
| B | low_pbr | 1578 | -1.09% | 0.01 | — |
| K_apr | value_composite_kr | 99 | +7.63% | 0.03 | — |

## 핵심 결론
1. **5팩터 복합(value_composite_kr)이 문병로 베스트** — K +13.68%, 저PBR 단독·소형주 압도.
2. **문병로 시그니처 명제 "한국=저PBR 민감" 다년 검증 시 약함(부분 반박)** — low_pbr 단독이 3룰 중 최하(+3.29%, 승률 36.7%). 한국 첫 저자책의 시그니처 주장이 데이터로 부분 반박된 것이 최대 발견.
3. **Sharpe 0.01~0.09 붕괴** — Elder(0.68)·Minervini(0.64)에 크게 미달. per-trade 승률 40~47%(다년)로 6개월 펀더멘털 책(54~61%)보다 낮음 → **단일 BULL 6개월 거품 재확인**.
4. 장기보유(K/A) > 단기청산(B). 4월 게이트는 PnL 유지하며 회전율 절감.
5. **CANDIDATE_ALPHAS 등록 부적격**(Sharpe 0.09) — 펀더멘털 4책째(Lynch/Greenblatt/O'Shaughnessy 이어) 동일 결론. 기술적 추세추종만 다년 Sharpe 0.6대 생존.

## 산출물
- `reports/books_research/moonbyungro_metric/report.md`(리포트) + phase0_ocf_backfill.md + results_*.parquet 17개.
- `reports/books_research/index.md` Book 11 섹션·진행표 갱신. 공통 leaderboard.parquet 기록됨.

## Phase 3 — 국면 분해 (완료, scripts/regime_split_moonbyungro.py)
> KOSPI 20일±2% 라벨(Elder/Minervini 동일). BULL 39.3%/BEAR 29.3%/SIDEWAYS 31.4%, 2022=BEAR. 가치룰 보유 176~210일로 다국면 횡단 → entry/exit 기준 둘 다 산출.

### BEAR per-trade (저PBR/소형주 약세장 방어 검증)
| 룰 | entry-BEAR | exit-BEAR |
|---|---|---|
| value_composite_kr K | +5.00%(98) | −8.38%(110) |
| low_pbr K(시그니처) | +1.28%(88) | −6.36%(89) |
| small_value K | +7.66%(104) | −9.03%(110) |
| low_pbr A | **−1.68%**(86) | −9.14%(84) |

- **방어 성격이 Elder와 다름**: 문병로 가치룰은 BEAR 국면 안에서 버는 방어(exit-BEAR 전부 음수)가 아니라 **BEAR에 싸게 진입→BULL에 청산하는 역발상 매수 우위**(entry-BEAR 양수). Elder ema_pullback A는 BEAR 내 자기완결 +3.01%(진짜 방어).
- **저PBR 명제 조건부 반박**: low_pbr BEAR entry 방어가 긴 보유(K) +1.28%만 양수, 짧은 보유(A) −1.68% 붕괴. "충분히 오래 들고 갈 때만" 성립.
- 상세: reports/books_research/moonbyungro_metric/regime_split.md

## 다음
- **책조사 11권 완료.** 한국책 2순위 홍용찬 착수 예정·3순위 systrader79.

## 미커밋 (사장님 승인 대기)
Phase 0+1+2 전체 — 스키마 ALTER·신규 스크립트 2개·전략 패키지·테스트·리포트 3종·index 갱신. git 커밋 미실행.

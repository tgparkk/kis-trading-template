# Lynch One Up on Wall Street — 백테스트 결과 리포트 (Book 8)

> Book: Peter Lynch — *One Up on Wall Street* (1989) / *Beating the Street* (1993)
> 조사: [research.md](research.md) · 설계: [../../../docs/superpowers/specs/2026-05-29-lynch-one-up-design.md](../../../docs/superpowers/specs/2026-05-29-lynch-one-up-design.md)
> 실행: 2026-05-29 · **universe = fundamentals:131** (top_volume:50 아님 — §5) · 일봉 + 분기재무 point-in-time(105일 lag)

---

## 1. 요약

Peter Lynch의 펀더멘털 GARP 방법론(6카테고리·PEG)을 가용 재무 컬럼으로 매핑한 4룰로 코드화. **psr·dividend_yield 100% NULL**이라 자산주(psr)·PEGY(배당) 룰은 대체 룰로 발상만 표현. **universe는 재무 보유 131종목**(사장님 승인 — top_volume:50 교집합 10종목 불가).

**표본이 견고한 유일 룰: `value_balance_sheet`** (저PBR<1.0 + 저PER<12 + 저부채<50%). Variant B 114거래 per-trade 승률 **52.6%, 평균 +2.84%/거래**.

**핵심 발견 (3회 연속 패턴)**: 가장 단순한 **가치 스크린**(value_balance_sheet)이 복잡한 GARP·고성장 룰(fast_grower/garp_combo)을 표본·안정성에서 앞섬. Minervini(volume_dryup>trend_template)·Elder(ema_pullback>다지표)에 이은 동일 교훈.

**그러나 데이터 제약이 심각해 결론은 inconclusive** — 연간 데이터, 극소 universe, 종목당 ~124봉, NULL 다수. fast_grower/stalwart는 1~6거래로 통계 무의미.

---

## 2. 집계 결과 (universe-mean — 희석 주의)

> ⚠️ pnl_pct/hit_rate는 131종목 평균이라 **거래 0건 종목들이 평균을 희석**. 이전 7권(top_volume:50, 대부분 거래)과 직접 비교 불가. 공정 비교는 §3 per-trade.

### Variant A (sl 12% / tp 50% / mh 120)
| Rule | 거래 | mean PnL % | Sharpe | Calmar | MaxDD % |
|---|---|---|---|---|---|
| value_balance_sheet | 34 | +2.59 | 0.12 | 0.20 | 2.39 |
| garp_combo | 10 | +0.60 | 0.05 | 0.05 | 0.75 |
| stalwart | 1 | +0.49 | — | — | — |
| fast_grower | 3 | +0.46 | — | — | — |
| all_AND | 0 | — | — | — | — |

### Variant B (sl 8% / tp 12% / mh 20)
| Rule | 거래 | mean PnL % | Sharpe |
|---|---|---|---|
| value_balance_sheet | 114 | +2.08 | 0.10 |
| garp_combo | 32 | +0.35 | 0.04 |
| fast_grower | 6 | +0.26 | — |
| stalwart | 3 | +0.10 | — |

---

## 3. Per-Trade 결과 (공정 비교 — 거래 단위)

> 결과 parquet에서 거래별 손익 직접 집계. 표본 충분한 룰만 의미.

### Variant A
| Rule | 거래 | per-trade 승률 | 평균/거래 | 중앙값 | 청산 분포 |
|---|---|---|---|---|---|
| **value_balance_sheet** ⭐ | 34 | 50.0% | **+11.51%** | +0.84% | forced 15·SL 10·TP 8·mh 1 |
| garp_combo | 10 | 50.0% | +9.67% | +2.19% | forced 4·SL 4·TP 2 |
| fast_grower | 3 | 66.7% | +21.60% | +26.61% | (N=3 무의미) |
| stalwart | 1 | 100% | +65.70% | — | (N=1 무의미) |

### Variant B
| Rule | 거래 | per-trade 승률 | 평균/거래 | 중앙값 | 청산 분포 |
|---|---|---|---|---|---|
| **value_balance_sheet** ⭐ | 114 | 52.6% | +2.84% | +1.28% | mh 35·TP 34·SL 33·forced 12 |
| garp_combo | 32 | 56.2% | +2.06% | +3.79% | mh 11·SL 11·TP 9 |
| fast_grower | 6 | 83.3% | +5.84% | +5.57% | mh 3·TP 2·SL 1 |
| stalwart | 3 | 100% | +4.42% | +3.34% | mh 3 |

---

## 4. 룰별 분석

### value_balance_sheet (유일하게 견고) ⭐
- 저PBR(<1.0) + 저PER(0<per<12) + 저부채(<50%) = 가치주 스크린. 6카테고리 중 자산주 발상의 대체 구현.
- 표본 충분(A 34 / B 114). per-trade 승률 50~53%, 평균 +2.8~11.5%. Variant A 평균 +11.51%는 forced_close 15건(상승장 데이터 종료까지 보유)이 견인 — 멀티배거 의도 일부 작동하나 짧은 이력 탓.
- per/pbr 가용성이 가장 높은 컬럼 조합이라 표본도 가장 큼 → 데이터 친화적이면서 성과도 최상.

### fast_grower / stalwart (표본 부족)
- fast_grower 3~6거래, stalwart 1~3거래 — per-trade 승률은 높으나(67~100%) N이 너무 작아 통계 무의미.
- 원인: PEG<1.0 + 성장 20~50% + 저부채 + ROE>10 동시 충족 종목이 연간·131종목 데이터에서 극소.

### garp_combo (중간)
- 10~32거래, 승률 50~56%, 평균 +2~9.7%. value_balance_sheet 다음으로 표본 있으나 성과는 열위.

### all_AND = 0거래
- 4룰 동시 충족 불가(value 스크린 vs 고성장 상호 배타).

---

## 5. 책 8권 통합 비교 (일봉 기준 베스트)

> ⚠️ Lynch는 **universe가 다름**(fundamentals:131 vs 이전 7권 top_volume:50) + 집계 PnL 희석 → 아래 표 PnL 직접 비교 주의. Lynch는 per-trade 기준 표기.

| 책 | 데이터 | 베스트 | 성과 | 표본 |
|---|---|---|---|---|
| 아지즈 | 분봉 | bull_flag | -0.04% | 32T |
| Bellafiore | 분봉 | fade_vwap | +1.74% Sharpe +0.37 | 964T |
| Raschke | 분봉 | anti | +10.24% | 1,860T |
| O'Neil | 일봉+재무 | CANSLIM+패턴 | +7.04% | 7T |
| Minervini | 일봉 | volume_dryup B | +20.27% Sharpe 1.41 | 153T |
| Weinstein | 주봉 | ma30w_bounce B | +4.18% | 43T |
| Elder | 일봉(주봉 proxy) | ema_pullback A | +23.76% Sharpe 1.22 | 134T |
| **Lynch** | **일봉+재무(PIT)** | **value_balance_sheet B** | **per-trade +2.84% 승률 52.6%** | **114T** |

- Lynch는 펀더멘털 단독 책 중 표본 확보(114거래)에 성공했으나 per-trade 수익(+2.84%)은 기술적 베스트들 대비 낮음.
- 데이터 제약(연간·극소 universe·NULL) 때문에 Lynch 방법론의 진짜 잠재력은 본 데이터로 평가 불가.

---

## 6. 한계 및 주의 (전면)

- **universe 비교성 단절**: fundamentals:131 ≠ 이전 7권 top_volume:50. 집계 PnL/hit_rate는 0거래 종목 희석으로 과소 → per-trade로만 해석.
- **연간 데이터**: report_date 91% 12월, fiscal_quarter 공란. 신호 최대 ~15개월 stale.
- **극소 N**: per 보유 79종목, ≥120봉 46종목. fast_grower/stalwart 1~6거래 무의미.
- **짧은 이력 + 105일 lag + YoY warmup**: 종목당 live 적격 창 수개월. forced_close 다수(A value 15/34).
- **NULL**: psr·dividend_yield 100% → 자산주(psr)·PEGY 룰 제외(대체 구현). per/roe ~45% NULL.
- **생존편향**: 131종목은 관심종목 위주 적재 추정 → 상폐 누락 → PnL 낙관.
- **BULL 편향**: 2021~2026 랠리 포함.
- **적응판**: Lynch 13속성·정성 스토리·내부자/자사주 신호 미반영(데이터 부재). 정량 4룰만.

---

## 7. 결론

Lynch 펀더멘털 GARP를 한국 재무 데이터로 코드화한 결과, **표본이 견고한 건 단순 가치 스크린(value_balance_sheet) 뿐**이며 per-trade +2.84%(B, 114거래, 승률 52.6%)로 약한 양(+)의 엣지. 고성장(fast_grower)·대형우량(stalwart) 룰은 데이터 극소로 통계 무의미. **Minervini·Elder에 이어 "단순 가치/추세가 복잡한 다지표를 앞선다"는 패턴 재확인.**

다만 연간 데이터·극소 universe·NULL 다수·짧은 이력으로 **Lynch 방법론 자체의 평가는 inconclusive** — 분기 재무 + 배당/PSR 백필 + 더 넓은 종목 적재 후 재검증 필요. CANDIDATE_ALPHAS 등록 부적격(표본·데이터 신뢰도 미달).

---

*leaderboard.parquet(집계) + results_variant{A,B}_single_{rule}.parquet(per-trade) 기반.*

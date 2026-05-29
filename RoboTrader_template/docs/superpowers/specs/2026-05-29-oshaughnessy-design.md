# O'Shaughnessy What Works on Wall Street — 백테스트 설계서 (Book 10, 최종)

> 조사: [reports/books_research/osullivan_what_works/research.md](../../../reports/books_research/osullivan_what_works/research.md)
> 작성: 2026-05-29 · 끝까지 자동 진행
> Greenblatt(Book 9) 횡단면 순위 인프라 확장. book_id=`osullivan_what_works`(레거시 표기 유지).

---

## 0. 설계 원칙

1. **다팩터 횡단면 순위** — Greenblatt `run_greenblatt_magic.py` 복제·확장. `_build_cross_sectional_ranks`가 vc_rank·tv_rank·psr_rank·n_eligible 산출 → ctx 주입.
2. **VC1식 4팩터 가치복합**(PSR+PE+PB+EV/EBIT). 진짜 VC2/VC3 불가(주주수익률·P/CF·EBITDA 부재).
3. **PSR 재구성** = (market_cap/1e8)/revenue. 단위 환산 필수(Greenblatt와 동일 1e8).
4. **3개월 모멘텀**(63봉) — 6개월(140봉)은 16종목만 가용.
5. PIT 재무조인(105일 lag, Lynch `_build_fund_by_idx`), 롱 전용, 거래비용 동일.

---

## 1. 팩터 (가용 컬럼)

```
PSR     = (market_cap/1e8) / revenue           # 재구성. revenue>0, mc>0
PE      = per                                   # 54% non-null, per>0
PB      = pbr                                   # 61% non-null, pbr>0
EV/EBIT = (market_cap/1e8 + total_liabilities) / operating_profit   # op>0, ev>0
mom63   = close[i] / close[i-63] - 1            # 3개월 모멘텀
```
- 모두 cheap=low(모멘텀은 high=good). 가드 위반 시 해당 팩터/종목 부적격.
- EV/EBIT 분모 작을 때 캡(Greenblatt ROC_CAP 패턴).

---

## 2. 횡단면 순위 (run 스크립트 `_build_cross_sectional_ranks` 확장)

거래일 D마다, 4팩터 모두 유효한 적격 교집합에서:
1. 각 팩터 백분위(cheap=high): `pct_f = 1 - (rank_asc-1)/(N-1)`.
2. `vc_score = mean(pct_psr, pct_pe, pct_pb, pct_evebit)`.
3. `vc_rank` = vc_score 내림차순 dense ordinal(1=최저평가).
4. `psr_rank` = PSR 오름차순(1=최저).
5. `tv_rank`: vc_score 상위 40% 게이트 → 그 부분집합에서 mom63(≥63봉) 내림차순 dense ordinal.
6. `n_eligible` = 적격 수. MIN_ELIGIBLE=10.

주입: `ctx_extra = {"fund":fund_by_idx[i], "vc_rank":..., "tv_rank":..., "psr_rank":..., "n_eligible":...}`
- no-lookahead: 거래일 D의 PIT fund(105일 lag) + 당일 market_cap + close[..D]만.

---

## 3. 룰 3종 (확정)

### rule_value_composite (conf 75, top_n=20, min_eligible=10)
```
vc_rank is not None AND n_eligible>=min_eligible AND vc_rank<=top_n
```

### rule_trending_value (플래그십, conf 78, top_n=20)
```
tv_rank is not None AND tv_rank<=top_n
```

### rule_low_psr (시그니처, conf 70, top_n=20, min_eligible=10)
```
psr_rank is not None AND n_eligible>=min_eligible AND psr_rank<=top_n
```

```
ALL_RULES = [rule_value_composite, rule_trending_value, rule_low_psr]
```

---

## 4. 청산 Variant (Greenblatt와 동일)

| Variant | sl | tp | trail | mh |
|---------|-----|-----|-------|-----|
| A | 0.20 | 0.99(off) | 없음 | 120 |
| B | 0.08 | 0.12 | 없음 | 20 |

- warmup 20. forced_close 지배 명시.

---

## 5. 코드 산출물

```
strategies/books/oshaughnessy_value/
├── __init__.py
├── rules.py      # _num + 룰 3종 + ALL_RULES
└── strategy.py   # OShaughnessyValueStrategy(BookStrategy) + BOOK_META + build_strategy
scripts/run_oshaughnessy_value.py   # Greenblatt 복제 + PSR/PE/PB/EV-EBIT/mom63 + vc/tv/psr 순위
```

- strategy.py: holding_period="swing". BOOK_META id="osullivan_what_works", name="O'Shaughnessy What Works on Wall Street", category="fundamental_factor_rank", data_granularity="daily".
- run 스크립트:
  - `_load_fundamentals_universe`(131), `_load_daily_adj`(+market_cap 비조정), `_build_fund_by_idx` 확장(_FS_NUM_COLS에 per/pbr/revenue 추가; fund에 psr/pe/pb/evebit + market_cap).
  - `_build_cross_sectional_ranks` 확장: vc_rank/tv_rank/psr_rank/n_eligible. mom63은 종목 close에서 계산(run 단에서 df별 미리).
  - simulate ctx_extra 4키 주입. warmup 20.
  - leaderboard book_id="osullivan_what_works", universe=f"factor:{n_with_mc}", period="daily_full_mcwindow", reports-dir "reports/books_research/osullivan_what_works".
- **실행 RoboTrader_template/ cwd**.

---

## 6. 백테스트 실행
```
python scripts/run_oshaughnessy_value.py --variant A --all-modes
python scripts/run_oshaughnessy_value.py --variant B --all-modes
```

## 7. 검증
- pytest tests/books/ 통과. no-lookahead: 순위가 D 데이터만. n_eligible·forced_close·per-trade 기록.

## 8. 한계 (전면)
- 6개월 단일 국면, 79종목, 6개월 모멘텀→3개월 이탈, **진짜 VC2/VC3 불가**(주주수익률 부재), PSR 시점 불일치, EV 상향편향, 금융/유틸 제외 불가, BULL.

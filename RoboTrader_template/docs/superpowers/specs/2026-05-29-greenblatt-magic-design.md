# Greenblatt Magic Formula — 백테스트 설계서 (Book 9)

> 조사: [reports/books_research/greenblatt_magic_formula/research.md](../../../reports/books_research/greenblatt_magic_formula/research.md)
> 작성: 2026-05-29 · 끝까지 자동 진행
> universe는 데이터 강제(magic:79, market_cap 6개월 창). 종목별 독립 평가가 아닌 **횡단면 순위** 전략.

---

## 0. 설계 원칙

1. **횡단면 순위 합산** — EY·ROC 각각 순위 매겨 합산, 상위 N 매수. run 스크립트가 일자별 순위 precompute → ctx 주입(Minervini `compute_rs_percentile_12w`→`ctx["rs_value"]`와 동일 패턴).
2. **point-in-time 재무** — Lynch `_build_fund_by_idx` 재사용, 105일 lag. report_date VARCHAR → `::date` 캐스팅 + 정규식 필터.
3. **market_cap** — daily_prices에서 point-in-time(거래일) 사용, **adj_factor 미적용**(이미 레벨값). 2025-07-31~2026-02-02 (~124일)만 존재.
4. **롱 전용**, 거래비용 Minervini 동일.

---

## 1. 지표 (가용 컬럼)

```
EBIT       := operating_profit                       # ~100% non-null
EV         := market_cap + total_liabilities         # 현금 컬럼 없음 → 상향 편향(EY 과소). 명시.
Earnings Yield (EY) := operating_profit / EV
ROC        := operating_profit / (total_assets − current_liabilities)   # = NWC + 순고정자산 (대수 확인)
```

**가드 (부적격 → 순위 제외 / 미트리거)**:
- operating_profit ≤ 0
- market_cap 없음/≤0, EV ≤ 0
- (total_assets − current_liabilities) ≤ 0
- total_assets/current_liabilities/total_liabilities/market_cap 중 NULL
- ROC > 5.0 (작은 분모 폭주 캡)

---

## 2. 횡단면 순위 precompute (run 스크립트)

거래일 D마다:
1. 적격 집합 = PIT fund(D) 가드 통과 AND market_cap(D) 존재 종목.
2. EY=op/EV, ROC=op/(TA−CL) 계산.
3. ey_rank = rank(EY desc, 1=best), roc_rank = rank(ROC desc, 1=best), combined = ey_rank+roc_rank, 오름차순 정렬.
4. `magic_rank[D][code]` = 정렬 후 순위(1=best, dense ordinal), `n_eligible[D]` 기록.
5. 종목별 df 각 행 i에 대응하는 `magic_rank`(int 또는 None), `n_eligible`(int) 사전계산.

주입:
```
ctx_extra = {"fund": fund_by_idx[i], "magic_rank": rank_by_idx[i], "n_eligible": n_elig_by_idx[i]}
```
- `MIN_ELIGIBLE=10`: n_eligible<10이면 순위 신호 억제(현 데이터에선 미발동, 이식성용).

---

## 3. 룰 3종 (확정)

### rule_magic_formula_top (순위 기반, 주력, conf 75)
```
mr=ctx["magic_rank"]; ne=ctx["n_eligible"]
mr is not None AND ne>=10 AND mr<=top_n   (top_n 기본 20)
```

### rule_magic_formula_threshold (per-stock, conf 70)
```
fund + market_cap으로 EY/ROC 계산, 가드 후
EY > 0.10  AND  ROC > 0.25
```
> EY는 market_cap 필요 → 6개월 창 내에서만 발동. magic_rank 불요.

### rule_high_roc_value (품질 틸트, conf 68)
```
EY > 0.08  AND  ROC > 0.40
```

```
ALL_RULES = [rule_magic_formula_top, rule_magic_formula_threshold, rule_high_roc_value]
```

> threshold/high_roc_value도 EY 계산에 market_cap 필요 → run 스크립트가 fund에 market_cap·EV·EY·ROC를 미리 넣어 주입하거나, ctx에 별도 키로 전달. **권장: run 스크립트가 fund dict에 `market_cap`,`ey`,`roc`를 계산해 포함** → 룰은 ctx["fund"]["ey"]/["roc"] 읽기. magic_rank는 별도 키.

---

## 4. 청산 Variant

| Variant | sl | tp | trail | mh |
|---------|-----|-----|-------|-----|
| **A** (Greenblatt) | 0.20 | 0.99(off) | 없음 | 120 |
| **B** (획일) | 0.08 | 0.12 | 없음 | 20 |

- warmup_bars=20. forced_close가 지배적 청산 사유일 것 → 리포트 비중 명시.

---

## 5. 코드 산출물

```
strategies/books/greenblatt_magic/
├── __init__.py
├── rules.py      # _num 헬퍼(Lynch 재사용) + 룰 3종 + ALL_RULES
└── strategy.py   # GreenblattMagicStrategy(BookStrategy) + BOOK_META + build_strategy
scripts/run_greenblatt_magic.py   # Lynch run 복제 + market_cap 로드 + 횡단면 순위 precompute
```

- strategy.py: holding_period="swing". BOOK_META id="greenblatt_magic", name="Greenblatt Magic Formula (The Little Book That Beats the Market)", category="fundamental_quality_value", data_granularity="daily".
- run 스크립트:
  - universe = `_load_fundamentals_universe()` (Lynch와 동일, 131).
  - `_load_daily_adj`에 market_cap 추가 SELECT(레벨, adj 미적용) → wide market_cap 프레임.
  - `_build_fund_by_idx` 확장: fund에 operating_profit/total_assets/total_liabilities/current_liabilities + 그날 market_cap + 계산된 ey/roc 포함. Lynch의 YoY/PEG 로직 제거.
  - 횡단면 순위 precompute 패스 → rank_by_idx, n_elig_by_idx.
  - simulate에 ctx_extra={"fund","magic_rank","n_eligible"} 주입. warmup 20.
  - leaderboard book_id="greenblatt_magic", universe=f"magic:{n_with_mc}", period="daily_full(mc_window)", reports-dir "reports/books_research/greenblatt_magic_formula".
- **실행은 RoboTrader_template/ cwd에서** (상대경로).

---

## 6. 백테스트 실행

```
python scripts/run_greenblatt_magic.py --variant A --all-modes
python scripts/run_greenblatt_magic.py --variant B --all-modes
```
- top_n sweep는 시간 허용 시 별도(--rule magic_formula_top 기본 N=20). 1차는 기본값.

---

## 7. 검증
- pytest tests/books/ 통과 유지. no-lookahead: 순위 precompute가 거래일 D의 PIT fund + 당일 market_cap만 사용하는지.
- n_trades·forced_close 비중·순위 변형 신호 기간(6개월) 기록.

---

## 8. 한계 (리포트 전면)
- **6개월 단일 국면**(market_cap 창) + 79종목만 순위 → 이전 8권과 기간/universe 비교성 단절.
- EV 상향 편향(현금無), 연간 데이터, 영업권 ROC 하향, **금융·유틸 제외 불가**, 생존편향, BULL 편향, forced_close 지배.

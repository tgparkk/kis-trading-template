# Lynch One Up on Wall Street — 백테스트 설계서 (Book 8)

> 조사: [reports/books_research/lynch_one_up/research.md](../../../reports/books_research/lynch_one_up/research.md)
> 작성: 2026-05-29
> 결정(사장님 승인): universe = **재무 보유 종목** / 끝까지 자동 진행

---

## 0. 설계 원칙

1. **펀더멘털 단독 진입** — 6카테고리를 가용 재무 컬럼으로 매핑한 4룰. psr·dividend_yield 100% NULL이라 자산주(psr)·PEGY(배당) 룰 제외.
2. **universe = 재무 보유 종목** (top_volume:50 ∩ 재무 = 10종목이라 사용 불가). `financial_statements`의 DISTINCT stock_code(131, 모두 일봉 보유). 룰이 per/pbr 가용성으로 자연 필터. leaderboard tag `universe="fundamentals:131"`. **이전 7권(top_volume:50)과 비교성 깨짐 — 리포트 명시.**
3. **point-in-time no-lookahead** — report_date=회계기말. 한국 사업보고서 90일 내 공시 → **LAG 105일** 후에야 사용. fs_curr = effective_date(=report_date+105d) ≤ 거래일 中 최신.
4. **성장률 = YoY net_income** (연간, ~365일 전 보고서 대비), operating_profit fallback. 가드 필수.
5. **거래비용** — Minervini와 동일(왕복 ≈0.41%).

---

## 1. 재무 데이터 조인 (run 스크립트)

### universe 로드
```sql
SELECT DISTINCT stock_code FROM financial_statements
-- 131종목, 전부 daily_prices 보유. (옵션: per 보유 79로 축소 가능)
```

### 종목별 재무 시계열 로드
```sql
SELECT report_date, per, pbr, roe, debt_ratio, net_margin, operating_margin,
       net_income, operating_profit, revenue
FROM financial_statements WHERE stock_code = %s ORDER BY report_date ASC
```

### point-in-time fund 계산 (거래일 D 기준)
```
effective_date(row) = report_date + 105일
fs_curr  = effective_date ≤ D 인 행 中 report_date 최대          # 가장 최근 "공시된" 보고서
fs_prior = report_date가 fs_curr.report_date − 365일 근처([−400, −330]) 행
g_ni = (fs_curr.net_income - fs_prior.net_income) / abs(fs_prior.net_income) * 100
PEG  = fs_curr.per / g_ni        # fs_curr.per 사용 (이미 point-in-time)
```

### 성장 유효성 가드 (PEG 불안정 — NI≤0 18%)
다음 중 하나라도면 그 거래일 해당 종목 부적격(fund=None 또는 g_ni=NaN):
- fs_prior.net_income ≤ 0  (부호반전 → 쓰레기 성장률; 예 000050 −135→+236)
- fs_curr.net_income ≤ 0
- |g_ni| > 300  (작은 분모 폭발 캡)
- fs_curr.per ≤ 0 또는 NULL

### 주입
run 스크립트가 종목별로 df 각 행 i에 대응하는 `fund` dict를 사전계산:
```
fund = {per, pbr, roe, debt_ratio, net_margin, operating_margin, g_ni, net_income, prior_net_income}
```
`generate_signal_with_extra_ctx(code, window, "daily", {"fund": fund_by_idx[i]})` 로 전달. 룰은 `ctx["fund"]`만 읽음(재조회 금지). fund None이면 미트리거.

---

## 2. 룰 4종 (확정 — psr/dividend_yield 제외)

> 모두 `ctx["fund"]` 사용. fund 또는 필수 키 None이면 RuleResult(triggered=False). side="buy".
> 옵션 RSI 타이밍은 df["close"]로 계산(rule 내부). debt_ratio·roe는 % 단위.

### rule_fast_grower (conf 78)
```
per>0, g_ni 유효, net_income>0, prior_net_income>0
PEG = per/g_ni < 1.0
g_ni in [20, 50]
debt_ratio < 80
roe > 10
(옵션) RSI(14) < 50
```

### rule_stalwart (conf 70)
```
per>0, g_ni 유효
g_ni in [10, 20]
PEG < 1.5
roe > 10
debt_ratio < 100
net_margin > 0     # dividend_yield 100% NULL → 품질 프록시 대체
```

### rule_value_balance_sheet (conf 65)
```
pbr 보유, per 보유, net_income>0
pbr < 1.0
debt_ratio < 50
0 < per < 12
```

### rule_garp_combo (conf 72)
```
per>0, g_ni 유효
PEG = per/g_ni < 1.2
g_ni > 15
roe > 12
debt_ratio < 120
operating_margin > 5
```

```
ALL_RULES = [rule_fast_grower, rule_stalwart, rule_value_balance_sheet, rule_garp_combo]
```

---

## 3. 청산 Variant

| Variant | sl | tp | trail | mh | 비고 |
|---------|-----|-----|-------|-----|------|
| **A** (Lynch 의도) | 0.12 | 0.50 | 없음 | 120 | 멀티배거 허용, 운영 lynch와 정합 |
| **B** (획일) | 0.08 | 0.12 | 없음 | 20 | 책간 비교 |

- warmup_bars = **20** (재무가 논지, RSI(14)만 warmup). forced_close 비중 높을 것 → 리포트 명시.

---

## 4. 코드 산출물

```
strategies/books/lynch_one_up/
├── __init__.py
├── rules.py      # 룰 4종 + PEG/유효성 헬퍼 + ALL_RULES
└── strategy.py   # LynchOneUpStrategy(BookStrategy) + BOOK_META + build_strategy
scripts/run_lynch_one_up.py   # Minervini 복제 + 재무 universe + point-in-time fund 조인 + warmup 20
```

- strategy.py: holding_period="swing". BOOK_META id="lynch_one_up", name="Lynch One Up on Wall Street", category="fundamental_garp", data_granularity="daily".
- run 스크립트: `_load_fundamentals_universe()`(top_volume 대체), `_load_fundamentals_timeseries()`(종목별 재무), `_build_fund_by_idx(df, fs_rows)`(point-in-time + 가드), simulate에 ctx_extra={"fund":...} 주입, warmup_bars=20. leaderboard book_id="lynch_one_up", universe="fundamentals:131", reports-dir "reports/books_research/lynch_one_up". argparse Minervini와 동일.
- **실행은 반드시 `RoboTrader_template/` cwd에서** (상대경로 — Elder에서 겪은 이슈).

---

## 5. 백테스트 실행

```
# RoboTrader_template/ 에서
python scripts/run_lynch_one_up.py --variant A --all-modes
python scripts/run_lynch_one_up.py --variant B --all-modes
```

---

## 6. 검증

- pytest tests/books/ 통과 유지.
- no-lookahead 수동 점검: fund 조인이 effective_date(report_date+105d) ≤ 거래일만 사용하는지.
- 거래수·forced_close 비중 기록. n_trades<15 룰은 순위 보류.

---

## 7. 한계 (리포트 전면)

- universe 교체로 **책간 비교성 깨짐** (top_volume:50 ↔ fundamentals:131).
- 극소 N(per 79, ≥120봉 46), 연간 데이터, 종목당 ~124봉, 105일 lag+YoY warmup → live 적격 창 수개월, forced_close 지배.
- psr/dividend_yield 100% NULL → 자산주·PEGY 룰 제외(대체 룰로 발상만 표현).
- 생존편향(관심종목 적재 추정), BULL 편향.

# 사전등록 — 과거 재스캔 후보 원장 (candidate_ledger · A ③-b)

- 상태: **v0.2 · critic 1패스 반영 · 동결 대기(2026-09-24)** · 브랜치 `research/candidate-ledger` · 기준 main `2274895`
- 🔒 이 문서는 **결과를 보기 «전»에 커밋으로 동결**한다. 다음 단계 `run.py` 구현은 이 문서를 **그대로** 따른다.
  `🔒` 표시 절(창·전략·룰 경로·진입·밴드·사이징·청산·열·플래그·검증)은 **결과를 본 뒤 바꿀 수 없다**.
  바꿔야 하면 결과 개봉 «전»에 개정문(`PREREG_amendment_<날짜>.md`)을 따로 커밋한다.
- 작성 중 조회: 코드 grep/부분 read · DB **SELECT 만**(거래일 수·스냅샷 날짜 범위·분봉 날짜 범위). **전방 수익률·청산 결과 조회 0회.**

## 0. 목적 (사장님 말 그대로)

> 「제가 자금한도를 없애자고 한건 현재 로직으로 산 다음에 나중에 추가 데이터나 수치를 조절해서 매수후보 로직 품질을 높이고 싶은 겁니다」 (2026-09-24)

⇒ 목적 = **룰이 고른 것 «전부»의 표본을 과거 재스캔으로 «지금» 만든다.**
라이브는 2026-09-28 07:40 부터 스크리너 전수 저장(`df8e8fe`)이 시작되지만 표본이 쌓이려면 수개월이 걸린다.
그래서 과거 창을 **라이브 스크리너 어댑터 그대로** 재스캔해 「관측 원장」을 만든다.

🔴 **관측 원장이다 · 판정 근거가 아니다 · 룰 변경 근거로 인용 금지**(3전략 룰 라이브 변경 0건 ~2026-10-16 · 계획서 v3).

## 1. 이 문서가 «아닌» 것

- 특징 연구(B ④)가 아니다 — 별도 사전등록. 여기서는 **열 구조만** 정한다.
- 라이브 변경 0줄 · DB 쓰기 0건 · 라이브 코드는 import 만.
- 가설 검정 0건(§9 H-후보는 «적어 두기»만).

## 2. 창 · 달력 🔒

| 항목 | 값 | 근거 |
|---|---|---|
| 스캔 창 | **2024-03-13 ~ 2026-09-23** (scan_date = D) | 시총 절벽: `market_cap>0` 비율 2024-03-12 = 1.41% → 2024-03-13 = 99.57% (`docs/superpowers/specs/2026-09-14-candidate-ledger-replayer-design.md:134`) · 재현기 창 시작 `replayer/run.py:44 W0` |
| 달력 SSOT | `daily_prices` 의 `stock_code='KOSPI'` 행 | `replayer/loader.py:32 CALENDAR_TICKER` · `:205 load_trading_calendar` |
| 거래일 수(실측 SELECT) | **617일** (2024-03-13 ~ 2026-09-23) | 참고: `005930` 은 618일 — 차이 1일 = **2026-01-11(일요일) 가짜 행**. 종목행 달력을 쓰면 안 되는 실례 |
| 부분창 참고 | 2024-03-13~2026-05-31 = 537일(재현기 판정 창과 동일) · 2026-06-05~09-22 = 76일 | 같은 SELECT |
| 가격 적재 시작 | **2023-01-02**(워밍업 · minervini 창 260봉 확보) | `minervini_volume_dryup/screener.py:49 _TT_LOOKBACK=260` |

- D+1 = 달력에서 D 다음 거래일. **scan_date = 2026-09-23 의 D+1(09-28)은 아직 없다** ⇒ 그날 행은 `no_next_day` 로 남긴다(버리지 않는다).
- 보유 경로 끝 = 2026-09-23. 그때까지 안 닫힌 로트는 `exit_reason=open`(마지막 종가 평가 · exitsim8 `mark_to_market`).

## 3. 전략 · 스캔 경로 🔒

전략 3개(라이브 이름 그대로): `book_pullback_ma20` · `minervini_volume_dryup` · `daytrading_3methods_breakout`.

| 전략 | 어댑터 | lookback | base_filter (라이브 기본값) | score(정렬 키) |
|---|---|---|---|---|
| ma20 | `BookPullbackMa20ScreenerAdapter` | 90 | 시총 ≤ 3조(포함) · 거래대금 ≥ 10억 | 20일 평균 거래량(`screener.py:43`) |
| minervini | `MinerviniVolumeDryupScreenerAdapter` | 260 | 시총 ≥ 3,000억 · 거래대금 ≥ 30억 | 30일 평균 거래량(`screener.py` match) |
| daytrading | `Daytrading3MethodsBreakoutScreenerAdapter` | 60 | 시총 < 5,000억 · 거래대금 ≥ 10억 | 당일 거래량 ÷ 평균 거래량(`screener.py:53`) |

재사용(재현기 · 코드 0줄 변경):
1. **가격**: `loader.load_prices`(:160 · 의사티커 제외 · `volume × COALESCE(adj_factor,1)` · 🔴 가격엔 adj 곱하지 않음).
2. **유니버스**: `loader.build_universe`(:254 · `market_cap IS NOT NULL` · 거래대금 = close × adj 거래량) → `scan.eligible_for_dates`(:68 · **`date = max(date ≤ D)` 폴백** `loader.universe_snapshot` :274).
   🔴 **배제 없음** — 재현기 `loader.classify_exclusions`(:81 · 우선주·외국·리츠·스팩·ETF)를 **배제에 쓰지 않는다**. 라이브 `db/quant_daily_reader.py:90-96` 는 거르지 않으므로
   「룰이 고른 것 전부」·`rank`·`n_passed`·minervini RS 유니버스가 라이브와 같아야 한다. 분류값은 `excl_class` 열로 **표시만**(§7).
   2026-08-05 우선주 67종목 불연속도 이 열로 구분된다.
3. **룰 평가**: 라이브 어댑터의 `match()` 를 «그대로» 부른다. ma20·daytrading 은 `scan.scan_strategy`(:142) 그대로.
4. **minervini = 2패스(라이브 `_rule_screener_base.py:113-127` 재현)** — 재현기는 minervini 를 **지원하지 않는다**(`replayer/run.py:48-59 STRATEGIES` 에 ma20·daytrading 뿐 · `scan_strategy` 는 `match(win, params)` 2인자만 부름).
   ⇒ `run.py` 가 스캔일마다 ① 라이브 `_rule_screener_base.py:118-124` 와 같은 frames = **기준 필터 통과 ∧ 데이터 있음(`date ≤ D` 봉 ≥1) ∧ 불가능봉 가드 통과**(D 봉 없는 종목도 RS 컨텍스트에 «포함») 의 260봉 창을 모으고 ② `adapter.build_context(frames, D)`(RS 12주 백분위 · 유니버스 = 그 frames 집합 · `screener.py:97-128`) ③ `adapter.match(win, params, ctx.get(code) or {})`.
   `TT_FILTER_MODE = "on"`(`screener.py:42`) 그대로 — dry-up ∧ TT 통과만 행이 된다. 「D 봉 존재」 조건은 ③ **룰 평가 행 생성** 쪽에만 둔다(재현기 규약 · 아래 알려진 차이).
5. **불가능봉 가드 창**: 라이브는 `sanity_window` 가 있으면 끝 N봉만 본다(`_rule_screener_base.py:178`). minervini `sanity_window=90`(`screener.py:53` 상수 · `:59` 속성) · ma20·daytrading = None(창 전체).
   🔴 재현기 `scan.is_impossible(win)`(:45)은 `sanity_window` 를 **안 본다** ⇒ `run.py` 는 minervini 에 한해 `win.iloc[-90:]` 로 가드한다(과배제 방지).
   가드에 걸린 종목-일은 라이브처럼 **룰 평가 전 제외**(행 없음) — 날짜별 `n_impossible` 을 summary 에 인쇄.
6. **순위 · 절단 없음 경로**: `scan.rank_and_truncate(scored, max_candidates=None)` 를 **`count_boundary_tie=False`(기본)** 로 부른다.
   이때 `ordered[:None]` = 전수 반환(절단 없음). 🔴 `count_boundary_tie=True` 로 부르면 `len(ordered) > None` 에서 TypeError — 금지.
   정렬 = score 내림차순 · 동점 `stock_code` 오름차순(재현기 :108). 라이브 스크리너의 None 가드는 `_rule_screener_base.py:108`(`max_candidates = None if mc is None`).
   `rank` = 이 정렬의 1부터 순번 · `n_passed` = 그날 그 전략 룰 통과 수(= 그날 행 수).
- 알려진 차이(인쇄만): 라이브 동점 순서는 비결정적(`get_universe_snapshot` ORDER BY 없음) · 라이브는 D 봉이 없는 종목도 과거 봉으로 평가할 수 있으나 재현기는 D 봉 없는 종목을 평가하지 않는다(`n_no_bar_at_d` · 행 생성만 해당 · minervini RS 유니버스에는 포함하므로 RS 값은 라이브와 같다).
- 주 스캔은 빈티지 보정 없음(`vintage_vol=None`).

## 4. 진입 · 밴드 🔒

- 진입 = **D+1 시가**(`daily_prices.open` · adj 미적용). 체결 시각 = D+1 09:00 으로 둔다(exitsim8 `BASIS_D_OPEN`).
- 기준가 `ref` = **D 종가**(= 라이브 on_tick 이 D+1 에 보는 D 확정봉 종가 · 각 `strategy.py` 의 `current_price = data["close"].iloc[-1]`).
- 밴드 = `strategies/base.py:668-688 _entry_band(ref, down_pct, up_pct)` 그대로: `lo = ref×(1−down)`(down None ⇒ 하한 없음) · `hi = ref×(1+up)`(up None ⇒ 상한 없음).

| 전략 | down_pct | up_pct | 밴드 | 출처(yaml 에 `entry_band_*` 키 없음 ⇒ 코드 기본값) |
|---|---|---|---|---|
| ma20 | 0.08 (= `stop_loss_pct`) | 0.01 | **[ref×0.92, ref×1.01]** | `book_pullback_ma20/strategy.py:89-93` · 호출 :274-275 |
| minervini | None | 0.03 | **(−∞, ref×1.03]** | `minervini_volume_dryup/strategy.py:111-115` · :301-302 |
| daytrading | None | 0.03 | **(−∞, ref×1.03]** | `daytrading_3methods_breakout/strategy.py:82-86` · :273-274 |

- `band_ok` = `lo ≤ open ≤ hi`(경계 포함 · None 쪽 열림). **밴드 밖 행도 버리지 않고 `band_out` 플래그를 단다**(행 삭제 금지).
- 🔒 **밴드 밖 행도 청산 시뮬을 돌린다**(관리자 결정 2026-09-24): 목적이 「룰이 고른 것 전부의 표본」이므로 후보 층(스크리너)의 결과는 타이밍 층(밴드)과 무관하게 전부 관측한다. `band_ok=False` 행의 `qty`~`pnl_won` 은 「밴드가 없었다면」의 가상 로트 값이며, 라이브 근사 집계는 반드시 `band_ok=True` 로 걸러서 본다. `summary.md` 는 전략별 `band_ok` 비율을 인쇄한다.
- D+1 에 그 종목 봉이 없거나 시가 결측/≤0 ⇒ `no_open` 미진입. D+1 이 달력에 없으면 `no_next_day`.
- 미진입 행(`no_open`·`no_next_day`)만 `qty`~`pnl_won` 이 빈칸이다. `entry_date`(있으면)·`entry_price`(관측 시가, 있으면)는 채운다.
- 한계: 라이브는 09:0x 실시간가로 밴드를 본다 — 여기선 **시가 근사**(§8).

## 5. 사이징 — B1 로트 독립 🔒

- `ledger8/sizing.py:67 arm_b_qty(price, per_stock=1_000_000) -> Qty(qty, basis, notional, per_stock, note)` 재사용.
  `qty = max(1, floor(1_000_000 / entry_price))` · `qty_basis` ∈ {`amount`, `one_share`(주가 > 100만원)}.
- 자본·K·일일 체결 한도·종목당 상한 **전부 없음**. 같은 종목이 전략 간/같은 전략 다른 날에 겹쳐도 **별도 로트**.
- `notional = qty × entry_price`(원) · 자본 분모 없음 ⇒ 총자산·누적수익률 계산 금지(`sizing.py:3`).

## 6. 청산 — 일봉 · exitsim8 🔒

재사용: `ledger8/exitsim8.py` — `ExitRules(tp, sl, max_hold_days, source)`(:67) · `Pos(code, entry_date, entry_time, entry_price, qty, entry_basis, touch_bar=None)`(:75) · `simulate_lot(pos, rules, path, probe) -> ExitOut`(:175 · path = `[(k, day, Bar|None)]`, path[0] = 진입일 k=0).
tp/sl 는 `ledger8/sellprobe8.py:45 resolve_live_tp_sl(folder, strategy)`(라이브 엔진 경로로 얻음) · 데이터 청산(보유기간·trail)은 `sellprobe8.SellProbe(folder, strategy, window_fn)`(:67) — `window_fn(code, day)` 는 벌크 로드 `px` 에서 만든다(DB 왕복 0).
🔒 **`window_fn` 계약**: `window_fn(code, day)` = 벌크 `px` 중 **`date < day`(마지막 봉 = day−1)** 인 최근 N봉 — 라이브 on_tick 과 동일 · **당일 봉 포함 금지(룩어헤드)**.
⇒ ma20 `trail_ma` = D+k−1 종가 < MA20(D+k−1 까지) 이면 **D+k 시가** 청산.

| 전략 | tp | sl | max_hold(거래일) | trail | 출처 |
|---|---|---|---|---|---|
| ma20 | +10% | −8% | 50 | MA20 — 수익 중 종가 < MA20 이면 청산(`trail_ma`) | `config.yaml:31-34` · `strategy.py:85-86`(max_holding_days) · :241-255(_check_sell) |
| minervini | +12% | −8% | 20 | 없음 | `config.yaml:31-33` · `strategy.py:104-105` · :256-257 |
| daytrading | +10% | −10% | 10 | 없음(`trail_ma: null`) | `config.yaml:30,38-41` · `strategy.py:76-78` · :240 |

- 🔒 `run.py` 는 위 값을 하드코딩하지 않고 `resolve_live_tp_sl` 로 얻은 뒤 **이 표와 다르면 중단**한다(동결 대조).
- 하루 판정 순서(exitsim8 docstring :3-13 그대로): [보유기간 → 갭 익절(시가)] → [데이터 청산(시가)] → [갭 손절] → 장중 고저 터치.
- **같은 봉에서 손절·익절 동시 도달 ⇒ 손절 우선**(보수적 · `cap_skip_ledger/sim.py:17,115,145` · 플래그 `sl_tp_same_bar(손절 우선)` exitsim8 :50).
- 진입일(k=0)은 D+1 봉 전체 고저로 터치 판정(`BASIS_D_OPEN`).
- 결측 봉은 건너뛰고 `bar_missing:<날짜>` · 결측 중 보유기간 도달이면 다음 봉 시가 청산 `max_hold_deferred(...)`.
- `exit_reason` ∈ {`tp`, `sl`, `max_hold`, `trail_ma`, 그 밖 전략 데이터 청산 코드, `open`}.

## 7. 출력 🔒

`backtest/concept_axes/candidate_ledger/results/`
- **`ledger.csv` — 1행 = 1로트(스캔 통과 종목-일-전략 1개)** · 정렬 = strategy, scan_date, rank · 열(순서 동결):

| # | 열 | 정의 |
|---|---|---|
| 1 | strategy | 라이브 폴더명 |
| 2 | scan_date | D (YYYY-MM-DD) |
| 3 | stock_code | 6자리 |
| 4 | rank | §3-6 순번(1~) |
| 5 | score | 어댑터 score 원값 |
| 6 | n_passed | 그날 그 전략 룰 통과 수 |
| 7 | reason | 어댑터 `match()` 사유 문자열(minervini 는 `tt=1` 포함) |
| 8 | n_bars | 룰이 본 창 봉 수 |
| 9 | ref_close | D 종가(밴드 기준가) |
| 10 | market_cap | 기준 필터에 쓴 값(`universe_eff_date` 행) |
| 11 | trading_value | 기준 필터에 쓴 값(`universe_eff_date` 행 · close × adj 거래량) |
| 12 | d_volume | D 봉 거래량(adj 적용 · 빈티지 전 값) |
| 13 | rs_value | minervini RS 백분위(ctx · 나머지 전략 빈칸) |
| 14 | excl_class | `classify_exclusions` 분류(`pref`/`foreign`/`reit`/`spac`/`etf` `;` 구분 · 해당 없으면 빈칸 · 배제 안 함) |
| 15 | entry_date | D+1 (없으면 빈칸) |
| 16 | entry_price | D+1 시가 (관측값 · 없으면 빈칸) |
| 17 | band_lo | §4 밴드 하한(없으면 빈칸) |
| 18 | band_hi | §4 밴드 상한(없으면 빈칸) |
| 19 | band_ok | True/False (시가 없으면 빈칸) |
| 20~22 | qty · qty_basis · notional | §5 (시가가 있는 행 전부 · `band_ok=False` 는 가상 로트 · §4) |
| 23~25 | exit_date · exit_price · exit_reason | `ExitOut.exit_date/price/reason` |
| 26 | exit_phase | `ExitOut.phase`(`open0900`/`after0902`/`entry_day`) |
| 27 | hold_days | `ExitOut.hold_days`(k · 진입일 = 0) |
| 28 | ret_pct | `ExitOut.ret_pct`(% · gross) |
| 29 | pnl_won | `round(qty × (exit_price − entry_price))`(원 정수 · gross) |
| 30 | flags | `;` 구분 |

- **flags 어휘(동결)**:
  - `band_out` — 시가가 밴드 밖(가상 로트 · 라이브라면 미진입) · `no_open` — D+1 봉/시가 없음(미진입) · `no_next_day` — D+1 이 달력에 없음(미진입)
  - `impossible_bar` — 보유 경로(entry_date~exit_date)에 `replayer/flags.compute_bar_flags` 의 패딩·상하한 고정·절벽 봉 존재
  - `vintage_m4` — scan_date < `OVERTIME_MIN_DATE = "2026-07-03"`(`loader.py:177` · 시간외 거래량 원본 없음 ⇒ 보정 원리적 불가)
  - `corp_event` — `loader.load_corp_events`(:235 · bonus_issue/split/rights_issue)의 event_date 가 [scan_date, exit_date(미청산이면 2026-09-23)] 안
  - `minute_avail` — `minute_candles` 에 (stock_code, `trade_date` = D+1 `YYYYMMDD` · PK 컬럼 · varchar) 행 존재. 분봉 범위 실측 **20250224~20260923(407일)** ⇒ 그 전은 항상 없음
  - `survivor_universe` — **모든 행**(상수 · 생존자 유니버스 표시 · 필터로 지우지 말 것)
  - exitsim8 플래그 원문 그대로 이어 붙임(`gap_tp_open` · `sl_tp_same_bar(손절 우선)` · `bar_missing:<d>` · `max_hold_deferred(...)` · `mark_to_market(마지막 종가)` 등)
- `summary.md` — 전략별 행수 · 진입 행수·진입율 · 미진입 사유 분포 · exit_reason 분포 · 스캔 거래일 수 · 날짜별 n_passed 분포(최소/중앙/최대) · n_impossible 합 · 실행시간 · git sha · §10 V1~V5 결과.
- **`scan_diag.csv`** — 날짜별 진단(행 없는 날도 1행): `strategy, scan_date, universe_eff_date, n_universe, n_eligible, n_evaluated, n_impossible, n_no_bar_at_d, n_matched, secs`.
- `run_meta.json` — git sha · 창 · 전략별 params_hash(재현기 `params_hash`) · tp/sl/max_hold · 달력 일수 · 행수 · 시작/끝 시각 · **`loader.db_fingerprint`(:317)**.
- 체크포인트: `results/parts/<strategy>_<YYYY-MM>.csv` + 완료 표식 `.done`(git sha·DB 지문 기록) — 재시작 시 `.done` 있는 파트는 건너뛰되 **git sha·지문이 현재와 같을 때만 이어 단다(다르면 중단)**. 청산 경로가 월을 넘으므로 파트는 **scan_date 월** 기준.
- 🔒 실행 전 가드: `strategies/{3전략}/screener.py`·`strategy.py`·`config.yaml` · `strategies/base.py` · `strategies/_rule_screener_base.py` 의 blob 해시가 `2274895` 와 다르면 **실행 중단**.

## 8. 한계 선언 🔒

1. **빈티지(M4)** — 지금 DB 의 D 봉 ≠ 라이브가 D+1 09:00 에 읽은 D 봉(시간외 거래량 등). `OVERTIME_MIN_DATE`(2026-07-03) 이전은 보정 불가 · 주 스캔은 보정 안 함.
2. **생존자 유니버스** — 지금 `daily_prices` 에 남은 종목만.
3. **장중 익절/손절 미재현** — 일봉 고저 터치 근사. 분봉은 거래대금 상위 300 만 · 2025-02-24 이후뿐(`minute_avail` 로 표시만).
4. **밴드 근사 = 시가 기준** — 라이브는 09:0x 실시간가.
5. **gross** — 수수료·세금 0.
6. **자원 제약 없음** — 라이브 체결 집합과 다르다(그것이 목적).
7. **원장 = 관측** · 판정 근거 아님 · 룰 변경 근거 인용 금지.
8. **`corp_event` 플래그는 2026-07 이전 거의 안 걸린다** — 수집 변경으로 06→07 6배 점프(`loader.py:238`) · 플래그 없음 ≠ 이벤트 없음.
9. **on_tick `evaluate_entry` 재평가 미재현** — `band_ok=True` 도 «체결 근사»다.
10. **daytrading 도 일봉 on_tick 전략**이라 근사 방식(D+1 시가·일봉 청산)은 나머지 2전략과 같다.

## 9. H-후보 (검정하지 않는다)

- ③-a 탐색(라이브 트리 `RoboTrader_template/scratchpad/candidate_rank_check_20260924/REPORT.md` · gitignore 된 미추적 파일 · 라이브 스냅샷 2026-06-05~09-22 73일): **ma20 1~10위가 11~20위보다 나쁨(p 0.011)** — 사전등록 없음·미검증.
- 이 원장에서는 **검정하지 않는다**. 검정은 B ④ 특징 연구 사전등록에서, 이 원장의 열(rank·score·n_passed)을 입력으로.
- 🔴 `summary.md` 에 순위 구간별 수익 비교표를 넣지 않는다(탐색 재현 = 사후적합 유혹 차단).

## 10. 검증 (verifier 가 확인) 🔒

- **V1 스냅샷 일치율** — 창 2026-06-05~09-22(달력 76일 · `screener_snapshots` 는 3전략 모두 **73일** 실측)에서 스냅샷이 있는 날마다
  `|재스캔 rank 1~10 집합 ∩ 라이브 rank_in_snapshot ≤ 10 집합| ÷ 그날 라이브 rank ≤ 10 행수`(스냅샷은 하루 ≤ 20행 · `config/constants.py:200`) → 전략별 평균·분포 인쇄.
  **`params_hash` 구간별로 따로 인쇄**(daytrading `high_window` 20→15 = 06-22/23 · minervini TT on = 08-25 `86ff02d`) · **현행 파라미터 구간만 대표값**.
  **문턱 없음 · 값만** · 재현기 M1 판정과 별개. 스냅샷 없는 3일은 날짜를 적는다.
- **V2** 전략별 행수 = 스캔일별 n_passed 합 · 날짜별 `n_passed` = `scan_diag.n_matched`(독립 경로) 대조.
- **V3** 시가가 있는 행 전부 `qty × entry_price = notional`(부동소수 허용오차 1원) · `band_ok` 와 §4 밴드식의 재계산 일치.
- **V4** 청산 행 `exit_date ≥ entry_date` · `hold_days ≤ max_hold` — 단 `max_hold_deferred` 행은 예외로 따로 세어 인쇄.
- **V5** 층화 5행(시드 20260924 고정 · 전략별 1행 ×3 + `exit_reason=trail_ma` 1행 + `band_out` 1행) 손계산 대조 — D 종가·밴드·D+1 시가·qty·청산일/가·pnl 을 DB SELECT 로 다시 계산.

## 11. 규모 · 비용 상한 🔒

- 행 수 추정 ≈ (35 + 14 + 27)/일 × 617일 ≈ 4.7만 행(관리자 추정 일평균 · 실제는 summary 에).
- 실행 추정 3~6초 × 3전략 × 617일 ≈ 1.5~3시간(백그라운드).
- 청산 시뮬 비용: `SellProbe` 가 로트 × 보유일마다 `generate_signal` 1회(최대 로트당 max_hold 회 · ma20 50) — 스캔보다 클 수 있다.
- 🔒 **1개월 파일럿(scan_date 2024-03) 먼저** — 스캔·청산 시간을 재서 전체 예상(617/파일럿 일수 배)이 **4시간 초과면 본 실행 전 중단·보고**.
- **상한: 실행 4시간 초과 시 중단하고 보고**(체크포인트까지 저장).
- DB: SELECT 전용 · `kis_template` · 접속 = `db/connection.py` 기본값(port 5433).

## 12. 구현 범위

- 새 코드 = `candidate_ledger/run.py` 하나 + `candidate_ledger/tests/`(밴드·절단 없음·minervini 2패스·sanity_window·qty 항등 단위 테스트).
- 재사용: `ledger8/{sizing,exitsim8,sellprobe8}.py`(`arms.py` 제외) · `replayer/{loader,scan,flags}.py` · 라이브 스크리너 어댑터 3개 · `db/quant_daily_reader.py`(라이브 유니버스 정의 대조용 · 벌크 경로는 loader).
  🔒 `ledger8/arms.py` 의 `run_lots` 는 **쓰지 않는다** — B1 로트 독립은 `simulate_lot` 직접 호출로 충분(라이브 체결 fills 모델 불필요).
- 라이브 트리에서 실행 금지 · 워크트리에서만.

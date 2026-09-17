# 데이터 → 전략 도달·변형 경로 검수 (Part 2-B)

> 대상 4전략: `daytrading_3methods_breakout` · `minervini_volume_dryup` · `elder_ema_pullback` · `book_pullback_ma5`
> 방법: 코드 독해 + `kis_template` SQL + 라이브 로그(8/18·19·20·21) grep. **코드 수정 0줄.**
> 기준일: 2026-08-23 작성. 라이브 실측은 **2026-08-21 세션**(최신 가동일) 기준.

---

## §0 한줄 결론

> 🔎 **독립 검증(2026-08-23, 별도 verifier)**: D3·D5·D6 전건 확증(D6 은 901/901 행이 당일 close 와 정확 일치 — **elder 편 보고서가 틀렸고 이 보고서가 맞다**; D5 는 `042660` 신호가 84,500·체결 84,600 같은 초 ⇒ 프레임 마지막 종가 판정 확정) · 손계산 4/4 재현 · D7·D8·D9 정확. 정정 반영: §1-7 가드 창 표(15/20/22/25 → **30/36/38/41**, 방향 반전) · D1 분모 274→277 · 창 B 기점 04-23(10,471/405) · D9 패딩 4→14행 · §5 매수 78→46건 · 분봉 프레임은 ≈13초 폴링.

**두 창은 같은 데이터를 보지 않는다** — 창 A(스크리너)는 «행 수»로, 창 B(라이브 재검사)는 «달력일 120일»로 창을 자르고,
그 결과 봉 수(A: 60/60/160/260 vs B: 78~84)·위생가드 범위·EMA 워밍업이 전부 갈린다.
volume 의 adj_factor 곱셈만 두 경로가 «같고»(양쪽 SQL 모두 적용, 가격엔 어느 쪽도 안 곱함), 나머지는 전부 다르다.
가장 무거운 것은 **정지 패딩 행(volume=0)이 거래량 룰의 분모를 20봉 중 18봉까지 0으로 채운 채 라이브 매수신호를 실제로 발생시킨 사례**(090150, 8/20)다.

---

## §1 4전략 × 항목 표

### 1-1. 창 A / 창 B 의 봉 수·창 정의

| 전략 | 룰 최소 봉 수 | 창 A 봉 수(=행) | 창 B 봉 수 | A 위생가드 창 | B 위생가드 창 |
|---|---|---|---|---|---|
| `daytrading_3methods_breakout` | 17 (high_window 15+2) · 거래량 21봉 사용 | **60행** (`screener.py:14`) | **78~84봉** (실측 8/21 = 80) | 60행 (sanity_window=None) | 80봉 |
| `minervini_volume_dryup` | 40 (recent 10 + base 30) · TT 는 **220** | **260행** (`screener.py:58`) | **78~84봉** | **90행** (`screener.py:59`) | 80봉 |
| `elder_ema_pullback` | 70 (`rules.py:245`) · EMA65 + 5봉 | **160행** (`screener.py:14`) | **78~84봉** | 160행 (sanity_window=None) | 80봉 |
| `book_pullback_ma5` | 22 (surge_lookback 20+2) · MA5 | **60행** (`screener.py:14`) | **78~84봉** | 60행 (sanity_window=None) | 80봉 |

- 창 B 의 「80봉」 실측: 2026-08-21 로그에서 `일봉 80건` **1,194회**, `일봉 36건` 36회(ma20 의 475040 한 종목뿐), 그 외 값 **0회**.
  (`logs/robotrader_template_20260821_074007.log`, `logs/trading_20260821.log` — 두 파일 수치 동일)
- 「78~84」의 근거: `daily_prices` 의 거래일 달력으로 2026년 각 거래일 T 에 대해 (T-120일, T] 구간의 거래일 수를 세면
  **78일 15회 · 79일 22회 · 80일 54회 · 81일 43회 · 82일 16회 · 83일 1회 · 84일 6회**. 창 B 는 «고정 80봉이 아니다».
- 창 A 의 라이브 실측(8/21 09:00): minervini `유니버스 371 → 평가 365 … 220봉충족 357` (`screener.py:187` 진단 로그).

### 1-2. 부족하면 룰이 어떻게 반응하나

| 전략 | 봉 부족 시 | 파일:라인 | 로그 |
|---|---|---|---|
| 공통(창 B) | len(data) < min_len → 평가 스킵 | `strategies/base.py:615` | `[신호없음] … 일봉 N건 < min_len=M` (10분 throttle, `base.py:549`) |
| daytrading | len(df) < high_window+2 → 조용히 triggered=False | `books/daytrading_3methods/rules.py:283-284` | **없음** |
| minervini(dryup) | len(df) < 40 → 조용히 False | `books/minervini_vcp/rules.py:322-323` | **없음** |
| minervini(TT) | len(df) < 220 → 조용히 False · rs_value 없으면 조용히 False | `rules.py:55-56`, `:69-70` | **룰엔 없음**. 어댑터가 finalize_scan 에서 집계 ERROR (`screener.py:196-213`) |
| elder | len(df) < 70 → 조용히 False · screen1_uptrend 는 len(ema65)<6 이면 False | `books/elder_triple_screen/rules.py:245-246`, `:108-110` | **없음** |
| ma5 | len(df) < 22 → 조용히 False · _ma 가 len<5/NaN/≤0 이면 None → False | `books/trading_legends/rules_daily.py:276-280`, `:39-46` | **없음** |

- 창 A 에는 min_daily_bars 가 «없다» — 룰 자체 가드만 걸린다. 창 B 는 min_len(base.on_tick) + min_daily_bars(evaluate_entry) **이중**이라
  daytrading·ma5 는 **25봉**, minervini 는 **40봉**, elder 는 **70봉**을 요구한다 ⇒ 17~24봉짜리 신규상장은 **A 는 통과, B 는 차단**.

### 1-3. 당일 미확정봉

| | 창 A | 창 B |
|---|---|---|
| 마지막 봉 | **D-1 확정봉** — scan_date = get_previous_trading_day(now) (`bot/liquidation_handler.py:604`) + SQL `date <= scan_date` (`quant_daily_reader.py:177`) + 재확인 `df[df["date"].dt.date <= scan_date]` (`_rule_screener_base.py:169`) | **D-1 확정봉** — SQL 에 상한이 «없어» 당일 행까지 읽고 _drop_unconfirmed_today_bar 로 1행 제거 (`core/trading_context.py:143-174`, 호출 `:197`) |
| 09:05 | 스캔은 09:00 에 «1회». 이후 재스캔 없음 | 당일 행 존재 → 제거 → D-1 |
| 15:20 | 동일(그날 09:00 결과 그대로) | 당일 행 존재 → 제거 → D-1 |

- **둘은 같은 「마지막 봉」을 본다** — 09:05 와 15:20 에서 동일. 실측 근거 3중:
  1. 8/21 로그의 `일봉 N건` 이 09:02~15:xx 내내 **80 고정**(1,194회 전부).
  2. DB 실측 `050120` 의 [2026-04-23, 2026-08-21] 행 수 = **81**, 그중 2026-08-21 행 존재 ⇒ raw 81 → drop → **80**.
  3. 봇이 **09:00~09:01 에 일봉 103봉을 재수집·DB 저장**(로그 `일봉 데이터 수집 완료: 103개` 07시 30건 + 09시 50건, `일봉 데이터 DB 저장 완료` 80건) ⇒ 장중에도 당일 행이 실재한다.
- 🔑 창 A 가 당일 행에 오염되지 않는 이유는 드롭이 아니라 **SQL 상한 + scan_date=D-1** 이다. 창 B 는 **드롭 하나에만** 의존한다
  (드롭이 무력화되는 조건: 날짜 컬럼이 없거나 파싱 실패 시 **원본 그대로 반환** — `trading_context.py:166-171`).

### 1-4. volume 조정 — **양 경로 모두 곱한다** (일치)

| 경로 | SQL | 파일:라인 |
|---|---|---|
| 창 A (일봉) | `(volume * COALESCE(adj_factor, 1))::double precision AS volume` | `db/quant_daily_reader.py:157-159` |
| 창 A (유니버스 거래대금) | `close * (volume * COALESCE(adj_factor,1))` | `db/quant_daily_reader.py:90-92` |
| 창 B (일봉) | `(volume * COALESCE(adj_factor, 1))::double precision AS volume` | `db/repositories/price.py:129` |
| 창 B (최신 1봉) | 동일 | `db/repositories/price.py:291` |

⇒ **dryup·거래량배수 룰은 두 창에서 같은 단위를 본다.** (단 §3 의 손계산 4건은 창 안 adj_factor 가 전부 1 이라 수치로는 판별 못 함 — §5 한계)

### 1-5. 가격 조정 — **어느 경로에도 곱셈이 없다** (일치, 규약대로)

- 창 A: `SELECT date, open, high, low, close, (volume*…)` — 가격 4컬럼은 그대로 (`quant_daily_reader.py:157-159`)
- 창 B: 동일 (`price.py:128-133`)
- 유일한 곱셈은 volume 에만. 「가격에 adj_factor 를 곱하면 가짜 절벽」 규약은 **양 경로 모두 지켜지고 있다**.

### 1-6. NaN / 결손

| 항목 | 창 A | 창 B | 실측 |
|---|---|---|---|
| date text 손상행 | `pd.to_datetime(format="mixed", errors="coerce")` → dropna (`quant_daily_reader.py:196-197`) | `pd.to_datetime(df["date"])` — **coerce 없음**, 파싱 실패 시 예외 (`price.py:145`) | DB 실측: ISO 형식 위반 행 **0행** (현재 손상행 없음) |
| 정지 패딩(OHLC 고정 + volume 0) | **통과** — 가드는 하락만 본다 | **통과** | 창 B 구간(04-23~08-21) volume=0 **10,471행 / 405종목**(초안 10,108/400 은 04-25 기점 — 검증 정정), 그 **100%가 OHLC 4값 동일** |
| 일봉 결손 | LIMIT n 이라 **더 과거까지 채운다**(창이 넓어짐) | `date >= now-120d` 라 **봉이 줄어든다**(창이 좁아짐) | 8/20 유니버스 중 창 B 봉수 <80 = **274종목**, 그중 **80종목은 신규상장이 아니다**(2026-04-23 이전 이력 보유) |
| close NULL/≤0 | `close.where(close>0)` 로 NaN 처리 + `pct_change(fill_method=None)` (`utils/data_sanity.py:77-81`) | 동일 함수 | 창 B 구간 close NULL 0행 · ≤0 0행 · OHL NULL 0행 |
| 불가능봉 가드 | `describe_impossible_drop(sane_view)` (`_rule_screener_base.py:177-183`) | `describe_impossible_drop(data)` (`strategies/base.py:645-659`) | **8/21: A 81회 발화 / B 0회** |

### 1-7. 위생 가드 창 — 제외 집합이 갈리는 구조 (실측)

2026-08-20 기준, market_cap 이 채워진 유니버스 **2,763종목**에서 「마지막 N봉 안에 −35% 미만 하루」가 있는 종목 수:

| 가드 창 | 제외 종목 수 (🔎검증 정정) | 누구의 창인가 |
|---|---|---|
| 60봉 | **30** (초안 15) | daytrading·ma5 의 창 A |
| 80봉(달력 120일) | **36** (초안 20) | **전 전략의 창 B** |
| 90봉 | **38** (초안 22) | minervini 의 창 A |
| 160봉 | **41** (초안 25) | elder 의 창 A |

> 🔎 초안은 2024-02-29→2026-06-15 데이터 구멍이 있는 16종목을 빠뜨렸는데, 가드는 그 종목들에도 실제로 발화한다(로그 `[book_envelope_200d] 041190: 불가능봉 1건 @2026-06-15 최대 -42.2%`). 검증자의 가드 재현은 elder 8/21 로그 발화 6건 = 예측 6건으로 교정됨.
> 🔑 A 와 B 는 **포함 관계가 아니다**(창의 «모양»이 다르다 — 행 수 vs 달력일) ⇒ 크기 차가 아니라 **집합 차**로 봐야 한다:

⇒ **daytrading·ma5**: A\B = **16종목**(스크리너는 뺐는데 진입은 통과) · B\A = **6종목**(후보는 되는데 진입에서 막힘) — 초안의 「A 가 느슨」은 **방향이 반대**였다
⇒ **elder**: A\B = **21** · B\A = **0**
⇒ **minervini**: A\B = **18** · B\A = **0**

「다른 경로」는 실재한다: 거래량 폴백 풀은 base_filter(시총·거래대금)**만** 적용하고 _prepare_frame(가드)·match(룰)를 **안 탄다**
(`bot/candidate_loader.py:240-310`). 그 종목의 유일한 가드가 창 B 의 80봉이다.

---

## §2 경로 상세 — 조정 지점을 한 번에 보여주는 호출 사슬

### 창 A (후보 선정, 09:00 · D-1 종가)

```
bot/liquidation_handler.py:604      scan_date = get_previous_trading_day(now_kst()).date()   # D-1
  └ strategies/_rule_screener_base.py:105  scan(scan_date, params)
      ├ :108  base_filter(self._load_universe(scan_date))
      │   └ :187 → db/quant_daily_reader.py:56  get_universe_snapshot(scan_date)
      │        SQL:  SELECT stock_code, COALESCE(market_cap,0),
      │              COALESCE((close * (volume * COALESCE(adj_factor,1))),0) AS trading_value   <-- volume 조정
      │              WHERE date = (SELECT max(date) … date <= scan_date AND market_cap IS NOT NULL)
      ├ :129/:118  _prepare_frame(code, scan_date, stats)
      │   ├ :195 → db/quant_daily_reader.py:161  get_daily_prices(code, end_date=scan_date, days=lookback_days)
      │   │        SQL:  SELECT date, open, high, low, close,                          <-- 가격 무조정
      │   │              (volume * COALESCE(adj_factor,1))::double precision AS volume <-- volume 조정
      │   │              WHERE stock_code=%s AND date <= %s ORDER BY date DESC LIMIT %s <-- 창 = 행 수
      │   ├ :169  df = df[df["date"].dt.date <= scan_date]
      │   └ :177  sane_view = df  or  df.iloc[-sanity_window:]      <-- 가드 창 (None=전체)
      │      :178  describe_impossible_drop(sane_view)  → 걸리면 후보 제외 + WARNING
      ├ :136  match(df, merged[, ctx])      <-- 전략별 룰
      └ :150  finalize_scan(diag)
   ⇒ screener_snapshots (strategy, scan_date, stock_code, score, rank_in_snapshot)
   ⇒ core/screener_snapshot_provider.py:71  _provider(strategy, scan_date)   <-- 「없다」와 「고장」을 가른다
```

### 창 B (라이브 진입 / 일봉 청산 재검사)

```
strategies/base.py:593  on_tick(ctx)
  ├ :606  min_len = get_min_data_length()      # daytrading 25 · minervini 40 · elder 70 · ma5 25
  ├ :614  data = await ctx.get_daily_data(code)
  │   └ core/trading_context.py:176  get_daily_data(code, days=None)
  │       :193  days = OHLCV_LOOKBACK_DAYS (=120, config/constants.py:19)     <-- 달력일
  │       :196 → db/repositories/price.py:113  get_daily_prices(code, days=120)
  │              start_date = now_kst() - timedelta(days=120)                  (price.py:124)
  │              SQL:  SELECT date, open, high, low, close,                    <-- 가격 무조정
  │                    (volume * COALESCE(adj_factor,1))::double precision     <-- volume 조정
  │                    WHERE stock_code=%s AND date >= %s ORDER BY date ASC    <-- 상한 없음
  │       :197  _drop_unconfirmed_today_bar(data)  (:143-174)  <-- 마지막 행 date==오늘(KST) 이면 1행 제거
  ├ :615  len(data) < min_len → 스킵 (+ throttle 로그)
  ├ :645  describe_impossible_drop(data)        <-- 가드 창 = 창 B 전체(80봉 고정)
  └ :660  generate_signal(code, data, timeframe="daily")
        → _check_buy → evaluate_entry(df, …) → books/*/rules*.py 의 룰 «그대로»
```

### 창 C (청산) — 두 갈래

```
[C-1 일봉]  strategies/base.py:691-713   for stock in ctx.get_positions():
              :694  exit_timeframe=="daily" → ctx.get_daily_data()   <-- 창 B 와 동일 프레임 (D-1 확정 종가)
              :701  generate_signal(code, data, timeframe="daily")

[C-2 장중]  core/trading/position_monitor.py:200  _analyze_sell_for_stock
              :206  current_price = await _get_current_price(code)   <-- 실시간 (API → 캐시 → data_collector, :373-409)
              :217  profit_rate = (current_price - buy_price)/buy_price   <-- STALE·trailing·max_hold 판정
              :359  signal = strategy.generate_signal(code, intraday_df, timeframe="intraday")
                    ★ exit_timeframe 을 «보지 않는다» — 무조건 intraday 로 넘긴다
```

**timeframe 가드 위치가 4전략 중 2전략에만 «선행»한다** (핵심):

| 전략 | 가드 위치 | 결과 |
|---|---|---|
| `book_pullback_ma5` | `strategy.py:133-134` — positions 분기 **앞** | 분봉 청산 **차단** |
| `elder_ema_pullback` | `strategy.py:163-164` — positions 분기 **앞** | 분봉 청산 **차단** |
| `daytrading_3methods_breakout` | `strategy.py:138-139` — positions 분기 **뒤**(`:129-130` 이 먼저) | 분봉 청산 **열림** |
| `minervini_volume_dryup` | `strategy.py:161-162` — positions 분기 **뒤**(`:152-153` 이 먼저) | 분봉 청산 **열림** |

커밋 `a736065` = 「분봉 매도경로 whipsaw 차단 — **rs_leader·ma20·ma5** timeframe 가드 선행」
⇒ daytrading·minervini 는 그 수정에 포함되지 않았다.

---

## §3 손계산 대조 (전략당 1건) — **4/4 일치**

기준: `virtual_trading_records`(is_test=true, action=BUY) 의 reason = 창 B 의 코드 출력.
SQL 재계산은 매수 시점의 마지막 «확정» 봉(= 2026-08-20)으로 맞췄다.

### ① daytrading_3methods_breakout — 050120 (2026-08-21 09:02:22)

| 값 | 코드 출력(원장 reason) | SQL 재계산 | 판정 |
|---|---|---|---|
| close | 3710.00 | 3710 | ✅ |
| prior high (15봉, 현재봉 제외) | 3505.00 | 3505 | ✅ |
| last volume | 370793 | 370793 | ✅ |
| avg volume (20봉, 현재봉 제외) | 13304 | 13304.25 | ✅ (`%.0f`) |
| 양봉 | — | open 3445 < close 3710 | ✅ |

원장 문자열: `breakout_prev_high close=3710.00 prior20_high=3505.00 vol=370793/13304`

⚠️ **라벨 오기**: `prior20_high` 로 찍히지만 실효 창은 **15봉**(`config.yaml:32 high_window: 15` → `strategy.py:71` → `rules.py:288`).
문자열은 `rules.py:299` 에 `prior20_high` 가 하드코딩돼 있다. 「코드 출력만 보고 20봉이라고 인용하면 틀린다」.

### ② minervini_volume_dryup — 475150 (2026-08-21 09:28:25)

| 값 | 코드 출력 | SQL 재계산 | 판정 |
|---|---|---|---|
| recent 10봉 평균 volume | — | 4,231,013.10 | — |
| base 30봉 평균 volume | — | 7,378,057.17 | — |
| ratio | **0.57** | **0.5735** | ✅ |

원장 문자열: `volume_dryup recent/base=0.57 ≤ 0.70`
(창 안 adj_factor 가 전부 1 ⇒ volume 과 volume×adj_factor 가 동일값. **이 건은 조정 여부를 판별하지 못한다**)

### ③ book_pullback_ma5 — 025860 (2026-08-21 09:29:42)

| 조건 | 코드 출력 | SQL 재계산 | 판정 |
|---|---|---|---|
| MA5 | 5940.00 | 5940.00 | ✅ |
| last low | 5980.00 | 5980 | ✅ |
| last close | 6030.00 | 6030 | ✅ |
| ① surge (20봉 저-고) ≥ 20% | — | (6700−5250)/5250 = **27.62%** | ✅ |
| ② touch (저가와 MA5 의 상대거리) ≤ 2% | — | 0.673% | ✅ |
| ③ above: close ≥ ma5×0.98 | — | 6030 ≥ 5821.2 | ✅ |
| ④ 양봉 | — | open 5980 < close 6030 | ✅ |

원장 문자열: `ma5_pullback ma5=5940.00 low=5980.00 close=6030.00`

🔎 관찰: 이 봉의 저가는 MA5 «위» 0.67% 다. `_touch_ma`(`rules_daily.py:65-69`)가 절댓값이라
**MA5 를 위에서 스치지 않은 봉도 「터치」로 센다**(별도 등록된 결함 후보와 같은 자리).

### ④ elder_ema_pullback — 278470 (2026-08-21 13:59:19)

| 값 | 코드 출력 | SQL 재계산(80봉, ewm adjust=False) | 판정 |
|---|---|---|---|
| last low | 367500 | 367500 | ✅ |
| last close | 386000 | 386000 | ✅ |
| **EMA13** | **380881** | **380880.6** | ✅ (`%.0f`) |
| touched: low ≤ EMA13×1.02 | — | 367500 ≤ 388499.2 | ✅ |
| recovered: close > EMA13 | — | 386000 > 380880.6 | ✅ |
| screen1: EMA65[-1] > EMA65[-6] | — | 384426.6 > 383334.8 | ✅ |

원장 문자열: `triple_screen_ema_pullback low=367500<=ema13*1.02 close=386000>ema13=380881`

🔑 같은 EMA13 을 **160봉**(창 A)으로 계산하면 **380880.4** — 차이 0.2원. **EMA13 은 창에 사실상 불변**이다.
그러나 EMA65 는 그렇지 않다 → §4 D1.

---

## §4 결함 후보 (결정은 사장님 몫)

### D1 🔴 elder — 창 B(78~84봉)는 EMA65 워밍업에 못 미친다 · 영향: elder

- `screen1_uptrend`(`books/elder_triple_screen/rules.py:105-110`)는 `ewm(span=65, adjust=False)`.
  pandas 는 y0 = x0 로 시드하므로 **80봉 후 시드 잔존 가중치 = (64/66)^79 = 8.8%**, 160봉이면 **0.75%**.
- 실측(2026-08-20, elder base_filter 통과 **277종목** — 초안 274 는 D7 의 수를 잘못 복사): 80봉 EMA65 기울기와 160봉 EMA65 기울기의 판정이
  **9종목(3.2%)** 에서 갈린다(9종목 코드·방향은 검증에서 행 수 창·달력 창 양쪽으로 **정확히 재현**).
  - A(160)=상승 / B(80)=하락 → **8종목**: `005930` `010170` `060250` `083650` `095340` `347700` `403870` `483650`
  - A(160)=하락 / B(80)=상승 → **1종목**: `174900`
- **고치면 무엇이 바뀌나**: elder 의 「후보 → 진입」 전환율이 바뀐다(8/9 가 「후보인데 진입 거절」 방향).
  ⚠️ `OHLCV_LOOKBACK_DAYS`(=120)를 올리면 **8전략 전부의 창이 같이 커진다** — 「한 번에 한 축만」 위반.
  `get_daily_data(code, days=…)` 는 이미 인자를 받으므로(`trading_context.py:176`) 전략별로 넘기는 편이 축을 좁힌다.

### D2 🔴 위생 가드 창이 A·B 에서 달라 제외 집합이 갈린다 · 영향: 4전략 전부

- 수치는 §1-7 표. daytrading·ma5 는 **B 가 더 엄격**(5종목), elder·minervini 는 **A 가 더 엄격**(5·2종목).
- 8/21 실측: 창 A 가드 **81회 발화**
  (`book_envelope_200d` 17 · `rs_leader` 16 · `book_pullback_ma20` 14 · `book_pullback_ma5` 11 ·
  `daytrading_3methods_breakout` 7 · `elder_ema_pullback` 6 · `minervini_volume_dryup` 6 · `deep_mr_dev20` 4),
  창 B 가드 **0회**. throttle 이 있어도 «첫» 발화는 항상 로그되므로 0 은 신뢰할 수 있다.
- **고치면 무엇이 바뀌나**: 가드 창을 한쪽으로 통일하면 두 창의 제외 집합이 같아진다.
  단 **후보 집합이 즉시 바뀐다** — elder 는 최대 5종목이 새로 통과, daytrading·ma5 는 최대 5종목이 새로 차단.

### D3 🔴🔴 정지 패딩 행이 거래량 룰 분모를 0으로 채운다 — **라이브 발화 확인** · 영향: daytrading 최우선, minervini·ma5

- 창 B 구간(2026-04-23~08-21) volume=0 행 **10,471행 / 405종목**(초안 04-25 기점 10,108/400 — 검증 정정), 그 **100%가 OHLC 4값 동일**(패딩).
- 8/21 라이브 워치리스트 80종목 중 **8종목(10%)** 이 창 B 안에 패딩 보유:
  `090150`(18행) `227950`(16) `193250`(15) `011090`(15) `054940`(15) `049080`(13) `001210`(11) `079650`(2).
- **실측 사례 090150**: 2026-07-22~08-14 **18봉 연속 패딩**(OHLC 전부 499원 · volume 0) → 08-18 에 5,200원(+942%)으로 재개.

  | 2026-08-19 시점 daytrading 룰 입력 | 값 |
  |---|---|
  | last volume | 315,332 |
  | avg 20봉 (그중 **18봉이 volume=0**) | **23,198.9** |
  | vol_ratio | **13.59** (문턱 2.0) |
  | 0을 뺀 실봉 2개 평균 → 비율 | 231,988.5 → **1.36** (미발화) |
  | 정지 «이전» 20봉 평균 → 비율 | 141,192.9 → **2.23** (경계 발화) |

  로그 원문:
  `2026-08-20 09:02:11 … [PAPER] 매수 시그널: 090150 @ 6,760 … breakout_prev_high close=6760.00 prior20_high=5470.00 vol=315332/23199`
  — SQL 재계산 315332 / 23198.85 와 **정확히 일치**.
  결과: daytrading 매수는 쿨다운으로 스킵(`[진입억제] 090150 … 쿨다운 59초`), 2분 뒤(09:04:28) `rs_leader` 가 6,760원에 신호를 내고 16분 뒤(09:18:39) 6,190원에 체결 →
  8/21 10:55 **−8.24% 손절**(원장 `virtual_trading_records` 확인).
- 가드가 못 잡는 이유: `describe_impossible_drop` 은 **하락만** 본다(설계 명시, `utils/data_sanity.py:29-31`).
  창 B 구간에서 **+35% 초과 상승 238건/232종목** vs **−35% 미만 하락 54건/32종목** ⇒ 가드가 덮는 쪽이 소수다.
- **고치면 무엇이 바뀌나**: 거래량 평균에서 volume=0 행을 빼거나 패딩 구간을 통째로 배제하면
  daytrading 의 「20봉 평균 ×2」가 정지 해제 직후 종목에서 **가짜로 성립하는 경로가 닫힌다**.
  ⚠️ 읽기 계층에서 손대면 dryup 비율·ma5 score·minervini score 도 같이 움직인다 — 축이 둘이다.

### D4 🔴 minervini — TT 는 창 B 에서 «원리적으로» 평가 불가 · 영향: minervini

- `rule_trend_template` 은 `len(df) < 220 → False`(`books/minervini_vcp/rules.py:55-56`). 창 B 는 **78~84봉**.
- 지금은 무해하다 — `evaluate_entry`(`strategy.py:197-217`)가 `rule_volume_dryup` 만 부르고 TT 를 «안 부른다».
- 그러나 `TT_FILTER_MODE`(`screener.py:42`)를 on 으로 올리면 TT 는 **스크리너 전용 게이트**가 되고,
  폴백·재검사로 들어온 종목은 여전히 D(dryup 단독)로 매매된다. `accepts_volume_fallback=False`(`strategy.py:76`)가
  그 구멍의 절반을 막아뒀지만, **창 B 자체가 TT 를 재현할 수 없다**는 사실은 그대로다.
- **고치면 무엇이 바뀌나**: 창 B 를 260봉으로 늘려야 TT 재검사가 가능해진다(= D1 과 같은 축, 같은 수정으로 해결 가능).

### D5 🔴 창 C — timeframe 가드가 4전략 중 2전략에만 선행 · 영향: daytrading·minervini

- 위치는 §2 표. **daytrading·minervini 는 분봉 청산 경로가 열려 있다.**
- 실측: `2026-08-21 09:27:07 | core.trading.position_monitor | INFO | 042660 전략 매도 신호: 손절 도달 (-8.1%)`
  — 042660 은 그날 `MinerviniVolumeDryupStrategy` 보유(`sync_positions … [042660, 279570, 100090]`).
  `evaluate_sell_conditions` 의 `close.iloc[-1]`(`strategy.py:246-247`)이 **분봉 종가**였다.
- 같은 경로의 과거 발화 47건 중에는 `100090 전략 매도 신호: MA5 trailing 이탈 (종가 16580 < MA5 16590)`(2026-06-16)처럼
  **분봉 MA5** 로 trailing 을 판정한 사례도 있다 — ma5 의 가드는 그 뒤(`a736065`)에 들어갔다.
- **고치면 무엇이 바뀌나**:
  - 가드를 **선행**시키면 → minervini·daytrading 의 손절 판정이 「장중 분봉 종가」에서 「D-1 확정 일봉 종가」로 바뀐다.
    백테스트 정합↑, 손절 반응은 하루 느려진다. `position_monitor` 의 `stop_loss_rate` 백스톱(`:327-334`)은 그대로 남는다.
  - 반대로 가드를 **제거**하는 방향으로 통일하면 → ma5 의 `trail_ma=5` 가 다시 **분봉 MA5** 가 된다(위 2026-06-16 사례 재현).

### D6 🟡 elder 스크리너의 score 가 «주가»다 · 영향: elder

- `strategies/elder_ema_pullback/screener.py:41`:
  `score = float(df["trading_value"].iloc[-1]) if "trading_value" in df else float(df["close"].iloc[-1])`
- 그런데 `QuantDailyReader._SELECT_OHLCV`(`quant_daily_reader.py:157-159`)는 **6컬럼(date/open/high/low/close/volume)만** 반환한다.
  trading_value 는 `daily_prices` 의 실재 컬럼이고 `get_universe_snapshot` 은 계산까지 하지만, **일봉 프레임엔 없다**.
  ⇒ 항상 close 폴백. **조용히**(로그 없음).
- 실측 `screener_snapshots` 2026-08-20 elder 상위 6:
  **1,574,000 / 1,397,000 / 1,396,000 / 787,000 / 507,000 / 487,500** = 그날 종가 그대로.
  후보 랭킹 = **「주가 비싼 순」**.
- 방증: 8/18~8/21 elder 매수 4건이 전부 **1주** — 278470 @388,500 · 010060 @294,000 · 140860 @279,000 · 000815 @411,000.
  (수량 산출 자체는 별건이라 인과로 단정하지 않는다)
- 다른 3전략은 폴백 없음: daytrading `last_vol/avg20`(`screener.py:51-53`) · ma5 5봉 평균 거래량(`screener.py:43`) ·
  minervini 30봉 평균 거래량(`screener.py:156`).
- **고치면 무엇이 바뀌나**: elder 후보 10종목의 **명단이 바뀐다**(순서가 아니라 상위 절단이 달라진다).

### D7 🟡 A 는 «행 수», B 는 «달력일» — 결손이 있으면 창이 **반대로** 움직인다 · 영향: 4전략 전부

- A: `ORDER BY date DESC LIMIT n` ⇒ 결손이 있으면 **더 과거까지 간다**(창이 넓어짐, 지표가 오래된 구간을 먹는다).
- B: `date >= now-120d` ⇒ 결손이 있으면 **봉이 줄어든다**(창이 좁아짐, 워밍업이 더 부족해진다).
- 실측: 2026-08-20 유니버스 중 창 B 봉수 <80 인 종목 **274개**, 그중 **80개는 신규상장이 아니다**(2026-04-23 이전 이력 보유) ⇒ 결손.
  전체 2,785종목 기준 <25봉 198 · <40봉 203 · <70봉 290 · <80봉 294.
- 어느 쪽도 **로그가 없다**. B 는 min_len 미달일 때만 `[신호없음] … 일봉 N건 < min_len=M` 을 찍는다(`base.py:627-630`).

### D8 🟡 daily_prices 에 일요일 행이 «딱 하나» 있다 — 005930 2026-01-11 · 영향: elder 후보 선정

| date | open | high | low | close | volume | adj_factor | market_cap |
|---|---|---|---|---|---|---|---|
| 2026-01-09 | 136000 | 140700 | 135200 | 139000 | 29,520,566 | 1 | 812.6조 |
| **2026-01-11 (일)** | 68000 | 69000 | 67500 | **68500** | **1,200,000** | **NULL** | **NULL** |
| 2026-01-12 | 69000 | 70000 | 68500 | 69500 | 1,100,000 | 1 | 811.5조 |
| 2026-01-13 | 70000 | 71000 | 69500 | 70500 | 1,000,000 | 1 | 804.4조 |
| 2026-01-14 | 137000 | 140300 | 136800 | 140300 | 18,444,394 | 1 | 820.2조 |

- 2026 전체에서 **일요일 행은 이 1건뿐**(Mon 73,508 / Tue 78,763 / Wed 78,978 / Thu 83,961 / Fri 81,364 / **Sun 1**).
- 3행 모두 종가가 직전·직후의 «절반», volume 이 **1,200,000 / 1,100,000 / 1,000,000** 라운드 숫자, adj_factor·market_cap 결측.
  실제 시세로 만들어질 수 없는 모양이다.
- 효과: elder 스크리너가 매일 005930 을 제외한다(`불가능봉 1건 @2026-01-11 최대 -50.7%`).
  창 B(80봉)엔 안 들어가므로 **라이브 진입 경로는 이 행을 못 본다** — D2 의 「A 가 더 엄격」 5종목 중 하나가 바로 이 케이스다.
- **고치면 무엇이 바뀌나**: 3행을 걷어내면 005930 이 elder 후보 풀에 복귀한다(단 D1 에서 80봉 screen1 은 «하락» 판정).

### D9 🟡 adj_factor 경계와 실제 가격 이벤트 날짜가 어긋난 사례 — 001510 · 영향: 거래량 비율 룰 전반

- adj_factor=0.5 구간 = 2021-01-12 ~ **2026-04-24**, =1 구간 = 2026-04-27~.
- 그런데 가격 사건은 **두 개**이고 둘 다 그 경계와 다르다:
  - 2026-02-09: 1,715 → 903 (**−47.3%**) ← 스크리너 가드가 잡는 봉
  - 2026-04-07~24: **volume=0 · 1,863원 고정 패딩 14행**(초안 「4행」 정정) → 04-27 **4,845원(+160%)**
- ⇒ 2026-02-09~04-24 구간은 「가격은 이미 사건을 반영했는데 adj_factor 는 여전히 0.5」 ⇒
  읽기 계층이 그 구간 volume 을 **절반**으로 준다.
- 규모: adj_factor ≠ 1 종목 전체 **100개**, 그중 **35개**가 창 B 구간(2026-04-25~) 안에 ≠1 행을 아직 갖고 있다.
- **고치면 무엇이 바뀌나**: A·B **양쪽 동시에** 거래량 값이 바뀐다(두 경로가 같은 SQL 을 쓰므로 «차이»는 안 생기고 «수준»이 바뀐다)
  ⇒ dryup 비율·거래량 배수·ma5 score·minervini score 가 전부 재계산 대상.
  **사전등록 없이 손대면 후보 집합이 조용히 이동한다.**

---

## §5 한계

1. **손계산 4건 모두 창 안 adj_factor 가 전부 1** ⇒ 「읽기 계층이 volume 에 곱한다」를 **수치로 판별하지 못했다**.
   양 경로가 곱한다는 것은 SQL 문자열 대조로만 확인했다(`quant_daily_reader.py:157-159` · `price.py:129` · `price.py:291`).
   수치 판별을 하려면 창 안에 adj_factor≠1 이 남은 35종목 중 한 건이 매수된 사례가 필요하다 — 8/14~8/21 매수 **46건**(초안 78 정정)에는 4전략 범위 안에선 없었다(`054940`(adj_factor 0.2) 이 8/20 에 매수됐으나 `rs_leader` 이고 reason 에 거래량이 안 찍혀 판별 불가).
2. **창 B 의 78~84봉은 거래일 «달력» 실측**이고, 종목별 결손으로 인한 추가 감소는 별도다(D7).
3. **D3 의 반사실 두 값(1.36 / 2.23)은 어느 쪽도 실제 시세가 아니다.**
   확정적인 것은 「분모 20개 중 18개가 0이었다」와 「로그 값이 SQL 로 정확히 재현된다」 두 가지뿐이다.
   **「패딩이 없었으면 안 샀다」는 주장이 아니라 한 가지 계산이다.**
4. **창 C 의 분봉 프레임 간격을 코드에서 확인하지 않았다.**
   `data_collector.get_stock().ohlcv_data`(`position_monitor.py:343-346`)는 🔎검증 실측 **~140행/30분 ≈ 12.8초당 1행, 상한 1000행**의 폴링 버퍼다 — 3분봉이 아니다.
   ⇒ D5 는 초안보다 **더 심하다**: 이 프레임 위의 `trail_ma=5` 는 「5폴(≈64초) 평균」이다.
5. `position_monitor` 의 STALE·trailing·max_holding 경로(`:227-334`)는 이번 범위 밖 — 「현재가 기준」이라는 사실만 확인했다.
6. **8/22 로그가 없다**(파일 부재). 라이브 실측은 8/18·8/19·8/20·8/21 기준.
7. D1 의 「9종목 flip」은 **EMA65 기울기 조건 단독** 비교다.
   elder 룰 전체(터치·회복 포함)의 최종 판정이 몇 건 갈리는지는 재지 않았다.
8. `describe_impossible_drop` 이 **상승**을 안 보는 것은 설계 문서에 명시된 «의도»다(오탐 위험).
   D3 는 그 의도를 뒤집자는 주장이 아니라, 그 결과로 **가드 밖에 남은 표본이 더 크다**(232 vs 32종목)는 관측이다.
9. 창 A 의 「행 수」와 창 B 의 「봉 수」를 비교할 때, A 의 lookback_days 는 **DB 행 수**이고 B 의 120 은 **달력일**이다.
   같은 이름(days)이 두 경로에서 다른 뜻이라는 점 자체가 이 검수의 출발점이었다.

---

## 부록 — 재현 명령

로그(bash):

```
grep -o "일봉 [0-9]*건" logs/robotrader_template_20260821_074007.log | sort | uniq -c
grep "미조정 기업행위 의심, 후보 제외" logs/robotrader_template_20260821_074007.log | wc -l
grep -c "진입 제외" logs/robotrader_template_20260821_074007.log
grep -h "전략 매도 신호" logs/robotrader_template_*.log | tail -8
```

SQL (`PGPASSWORD=1234 psql -h 127.0.0.1 -p 5433 -U robotrader -d kis_template`):

```sql
-- 창 B 안 패딩 행  → 10108 | 400
SELECT count(*), count(DISTINCT stock_code) FROM daily_prices
WHERE date>='2026-04-25' AND date<='2026-08-21' AND volume=0
  AND open=high AND high=low AND low=close;

-- 090150 daytrading 룰 입력 (2026-08-19)  → 6760 | 5470 | 315332 | 23198.85 | 18
WITH w AS (SELECT date, open, high, low, close,
       (volume*COALESCE(adj_factor,1))::double precision v,
       row_number() OVER (ORDER BY date DESC) rn
       FROM daily_prices WHERE stock_code='090150' AND date<='2026-08-19')
SELECT (SELECT close FROM w WHERE rn=1) c,
       (SELECT max(high) FROM w WHERE rn BETWEEN 2 AND 16) ph15,
       (SELECT v FROM w WHERE rn=1) vol,
       (SELECT avg(v) FROM w WHERE rn BETWEEN 2 AND 21) avg20,
       (SELECT count(*) FROM w WHERE rn BETWEEN 2 AND 21 AND v=0) zeros;

-- minervini 475150 dryup (2026-08-20)  → 4231013.10 | 7378057.17 | 0.5735
WITH w AS (SELECT (volume*COALESCE(adj_factor,1))::double precision v,
       row_number() OVER (ORDER BY date DESC) rn
       FROM daily_prices WHERE stock_code='475150' AND date<='2026-08-20')
SELECT (SELECT avg(v) FROM w WHERE rn BETWEEN 1 AND 10) recent10,
       (SELECT avg(v) FROM w WHERE rn BETWEEN 11 AND 40) base30,
       (SELECT avg(v) FROM w WHERE rn BETWEEN 1 AND 10)
        / (SELECT avg(v) FROM w WHERE rn BETWEEN 11 AND 40) ratio;

-- elder 278470 EMA13 (80봉, adjust=False)  → 380880.6
WITH RECURSIVE src AS (SELECT date, close,
       row_number() OVER (ORDER BY date DESC) rr
       FROM daily_prices WHERE stock_code='278470' AND date<='2026-08-20'),
b AS (SELECT date, close, 81-rr i FROM src WHERE rr<=80),
e AS (SELECT i, close::double precision ema FROM b WHERE i=1
      UNION ALL
      SELECT b.i, (2.0/14.0)*b.close+(12.0/14.0)*e.ema FROM b JOIN e ON b.i=e.i+1)
SELECT ema FROM e ORDER BY i DESC LIMIT 1;

-- 가드 창별 제외 종목 수 (2026-08-20 유니버스) → 60/80/90/160 = 15/20/22/25
-- 일요일 행 전수                                → Sun 1건 (005930 2026-01-11)
```

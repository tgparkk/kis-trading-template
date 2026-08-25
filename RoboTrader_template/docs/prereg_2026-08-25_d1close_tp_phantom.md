# 「D-1 종가 익절 환영」 결함 — 사전등록 (전략 고유 tp/sl 의 가격 소스 불일치)

> 작성 2026-08-25 · **코드 0줄** · 대상 8전략(발화 6) · 이 문서는 실행 «전»에 동결된다.
> 🔎 **검증 이력: 초안 → verifier 정정 9건 반영(2026-08-25)** · 작성자 재확인에서 **정정의 정정 3건** 추가(§2 주 인용 경로 · §2 `book_backtester` 라인 · §5 브랜치).

---

## §0. 무엇이 일어났나 (실측)

2026-08-25 장 초반, **0초 왕복** 매도가 2건 나왔다(`virtual_trading_records` SELL · hold `00:00:00` · 실손익 0).

| 종목 | 전략 | D-1 종가 | 체결가 | 사유 |
|---|---|---|---|---|
| `008930` | `book_envelope_200d` | 56,500 (8/24, **+25.7% 급등일**) | 49,250 @09:01:34 | 익절 도달 (+14.7%) |
| `253840` | `daytrading_3methods_breakout` | 4,830 | 4,185 @09:06:36 | 익절 도달 (+15.4%) |

산술: `56,500 / 49,250 = 1.147` · `4,830 / 4,185 = 1.154`.
⇒ 「+14.7% 익절」은 **오늘 오른 값이 아니라 D-1 종가와 오늘 체결가의 비**다.

**이력** — DB 전체에서 `익절 도달%` 사유 ∧ 보유 10분 미만은 **이 2건뿐**(첫 발화).
60초 내 왕복은 그 외 **10건**이 있고, ***셋 다 뿌리가 다르다***:

| 갈래 | 건수 | 성격 |
|---|---|---|
| 이 문서 (D-1 종가 tp) | 2 | 전략 고유 경로 · 가격 소스 불일치 |
| 룰 겹침 | 8 | MA 이탈·trailing 등 매수·매도 룰 동시 참 (`rs_leader` `049080` 등) |
| **범용 경로 tp 산정 결함** | **2** | `089030`·`089970` (2026-06-12 09:07·09:09) — **음수 tp 버그** |

세 번째 갈래는 `core/trading/position_monitor.py:311-315` 주석이 스스로 기록한 결함이다 —
*「갭업 체결 등으로 `target_profit_rate` 가 음수로 산정되면 "profit_rate >= 음수" 가 매수 직후 즉시 참이 된다 (089970 2026-06-12)」*.
실제 `089970` 의 reason 은 `0.84% >= -1.88%` 다. ***이 문서의 대상이 아니다.***

### 0-1. 갭 노출 (2026-08-07 이후 매수 117건 · 체결가 ÷ 직전 일봉 close − 1 · `daily_prices` 기준)

| 전략 | n | 평균% | 최소% | −5%↓ | −10%↓ |
|---|---|---|---|---|---|
| `daytrading_3methods_breakout` | 23 | −1.67 | −13.35 | 3 | 1 |
| `book_pullback_ma5` | 22 | −0.66 | −2.93 | 0 | 0 |
| `book_envelope_200d` | 18 | −1.97 | −12.83 | 1 | 1 |
| `rs_leader` | 18 | −3.00 | −12.21 | 6 | 1 |
| `elder_ema_pullback` | 14 | **+3.05** | +0.65 | 0 | 0 |
| `book_pullback_ma20` | 13 | −1.93 | −5.94 | 2 | 0 |
| `minervini_volume_dryup` | 8 | −2.15 | −7.86 | 1 | 0 |
| `deep_mr_dev20` | 1 | +0.45 | +0.45 | 0 | 0 |

−5% 이하 갭 체결 **13/117 = 11.1%**.
⚠️ `elder` 의 +3% 초과 6건은 **매수스톱(돌파가) 기준 밴드**라 D-1 종가 대비 상방이 정상이다
(`elder_ema_pullback/strategy.py:350` `entry_max = buy_stop_price * (1 + up_pct)`) — **결함이 아니다.**

### 0-2. 전략별 tp/sl (레코드 `target_profit_rate` / `stop_loss_rate` · 08-07 이후)

| 전략 | tp | sl | | 전략 | tp | sl |
|---|---|---|---|---|---|---|
| `book_envelope_200d` | 0.10 | 0.08 | | `deep_mr_dev20` | 0.12 | 0.07 |
| `book_pullback_ma20` | 0.10 | 0.08 | | `elder_ema_pullback` | 0.30 | 0.08 |
| `book_pullback_ma5` | 0.15 | 0.03 | | `minervini_volume_dryup` | 0.12 | 0.08 |
| `daytrading_3methods_breakout` | 0.10 | 0.10 | | `rs_leader` | 0.15 | 0.08 |

---

## §1. 메커니즘 (코드 인용 — 전부 확인됨)

**(1) 전략 고유 청산 루프가 일봉을 읽는다.**
`strategies/base.py:693-695` — `on_tick` 이 `exit_timeframe == 'daily'` 면 `ctx.get_daily_data()` 를 부른다.

**(2) 그 일봉의 마지막 봉은 D-1 이다.**
`core/trading_context.py:143-172` `_drop_unconfirmed_today_bar()` 가 당일(장중 형성 중) 봉을 제거한다.
`get_daily_data` 의 docstring(`:186-187`)이 이유를 적어 두었다 — *「일봉 룰이 미확정 거래량/종가로 오동작하지 않도록」*.
⇒ 장중 내내 `df.close.iloc[-1]` = **D-1 종가**.
🔑 ***이 제거 자체는 의도된 정상 동작이다*** (no-lookahead 보증). 결함은 그 값을 **손익률 판정에 쓰는 쪽**에 있다.

**(3) 8전략 전부가 그 D-1 종가로 sl/tp 를 판정한다.**
공통 형태 — `cur_close = float(close.iloc[-1])` → `ret = (cur_close - entry_price) / entry_price` → `ret <= -sl` / `ret >= tp`.
`entry_price` 는 **라이브 체결가**다.

| 전략 | `cur_close` | sl/tp 분기 | `_check_sell` 호출 |
|---|---|---|---|
| `book_envelope_200d` | `:208` | `:211-214` | `:313` |
| `daytrading_3methods_breakout` | `:226` | `:230-234` | `:309` |
| `book_pullback_ma20` | `:228` | `:232-236` | `:309` |
| `book_pullback_ma5` | `:228` | `:232-236` | `:309` |
| `elder_ema_pullback` | `:262` | `:266-270` | `:386` |
| `minervini_volume_dryup` | `:247` | `:251-255` | `:337` |
| `rs_leader` | `:138` | `:140-143` | `:183` |
| `deep_mr_dev20` | `:145` | `:147-150` | `:192` |

**(4) 범용 경로는 «현재가»로 같은 문턱을 본다.**
`core/trading/position_monitor.py:200-335` `_analyze_sell_for_stock` —
`:206` API 현재가 → `:314-316` `profit_rate >= target_profit_rate` → `:327-328` `profit_rate <= -stop_loss_rate`. 3초 폴링.
문턱은 전략 config → `Signal.target_profit_rate` / `stop_loss_rate` 로 전달돼 **08-07 이후 레코드 기준 양 경로 동일값**이다.
⚠️ **항상 동일한 것은 아니다** — 2026-06-12 `089970` 의 `target_profit_rate` 는 **−1.88%** 로 실재했다(§0 세 번째 갈래).

**(5) 진입 밴드는 하방을 막지 않는다.**
`entry_band_up_pct` — 돌파형(`envelope:88` · `daytrading:84` · `minervini:113` · `rs_leader:58`) **0.03** ·
`elder:117` **0.02**(매수스톱 기준) · 눌림형(`ma20:91` · `ma5:91` · `deep_mr:60`) **0.01**.
`entry_band_down_pct` — 돌파형 4종은 **`None`(하한 없음)**(`envelope:89-90` 등) · 눌림형은 `sl_pct` 를 기본값으로 받는다(`ma20:92-93` 등).

🔴 **8/25 밴드 거절 「0건」이라 말할 수 없다** — 밴드 거절은 **로그에 기록되지 않는다.**
`core/trading_decision_engine.py:411-416` 은 거절 사유를 **반환만** 하고(`return False, (f"…진입가 밴드 하회 — 스킵…"), empty`),
전체 로그 grep 결과 그 문구는 **0회** 등장한다. ⇒ ***발화 여부 미확인 · 계기 부재.***

### 🔑 결론

> **가격 소스 불일치**다 — 판정은 **D-1 일봉 종가**, 체결은 **틱**.
> 갭하락 매수 직후 `entry_price` 가 D-1 종가보다 크게 낮으면 `ret` 이 **매수 순간에 이미 tp 를 넘는다.**
> 하한 밴드가 `None` 이라 −12.8% 밑 체결까지 허용된다.

---

## §2. 🔴 판정 기준 — **백테스트는 이 함수를 부르지 않는다**

### 2-1. 주 근거 — 호출자 전수 조사 (구조적 사실)

```
grep -rn "evaluate_sell_conditions" --include=*.py .   (def 정의·tests 제외)
```

비-테스트 호출자는 **전부 전략 클래스 자신의 `_check_sell`** 이다(§1 표 4열) —
그 외는 레거시 `bb_reversion:416` · `bb_reversion_or:417` · `lynch:429` 와 `archive/scripts/` 2건뿐.

> 🔴 ***`backtest/` 와 `scripts/` 안에 `evaluate_sell_conditions` 호출은 「0건」이다.***
> 유일한 등장은 **주석 한 줄**(`scripts/multiverse4_returns_export.py:198`)이다.

**8전략 백테의 정본 경로**는 `backtest/engine.py` 가 아니라

```
scripts/multiverse4_returns_export.py  (StrategySpec :160-203)
  → scripts/exit_multiverse/portfolio_sim.py:34  run_portfolio
      → :79  adapter.exit_reason(df, i, position, params)
          → scripts/exit_multiverse/adapters.py:21-35
              → exits.exit_reason_simple_ma / exit_reason_elder   ← 별도 «재구현»
```

⇒ ***라이브 `evaluate_sell_conditions` 는 백테에서 호출조차 되지 않는다.***
🔑 백테와 라이브는 **같은 코드를 공유하는 것이 아니라 같은 «파라미터»만 공유**한다.

### 2-2. 보조 근거 A — `BookBacktester` 도 부르지 않는다

개념축 프로그램의 러너 `backtest/book_backtester.py` 는 `run_single` 에서
`generate_signal` 을 **`if position is None:`(`:227`) 안에서만** 부른다(`:228`).
⇒ 보유 중에는 전략에 아무것도 묻지 않고, 청산은 자체 close 기반 사슬로 처리한다
(`:195-196` `stop_loss` · `:197-198` `take_profit`).

### 2-3. 보조 근거 B — `backtest/engine.py` 는 실행 경로가 아니다

- 실인스턴스화는 프로덕션에서 `scripts/run_intraday_tournament.py:484` 와 `backtest/multiverse.py:494` 뿐이다
  (그 외는 `archive/scripts/diag_trail_ab.py:208` 과 `tests/`).
- 8전략을 `engine.py` 로 돌려도 **AttributeError 로 죽는다** — `_check_sell` 이 `on_init` 전용 속성을 쓴다
  (`book_envelope_200d/strategy.py:302` `_check_sell` → `:319` `self._max_hold_days`(설정처 `:77`) · `:332` `self._paper_trading`(설정처 `:92`)).
- 그럼에도 **터치 선점 논증**은 성립한다(참고용): 엔진 청산은
  1 손절 = 당일 **low** 터치(`:233-235`) · 2 trailing = low 터치(`:242`) · 3 보유기간 초과(`:246-263`) · 4 익절 = 당일 **high** 터치(`:265-268`) ·
  5 전략 신호 → 그날 종가(`:272-276`) · 6 EOD(`:279-281`). 문턱 출처는 `:119-122` → `:191-192`.
  전략 tp/sl 은 **같은 문턱을 종가로** 보고 `low ≤ 종가 ≤ high` 이므로 **1·2·3·4 에 선점된다.**
  ⚠️ **반례 가능** — `high`/`low` 가 NaN 인 봉은 우선순위 4 를 건너뛸 수 있다. **미측정.**
  ⚠️ **순서도 다르다** — 엔진 `sl → trailing → max_hold → tp` vs 전략 `sl → tp → max_hold` ⇒ **`max_hold` 와 `tp` 의 선후가 뒤집혀 있다.**

⇒ `book_envelope_200d/strategy.py:203` 의 docstring — *「청산 조건 평가 — 백테스트 우선순위 1:1 복제」* — 은 **두 가지 뜻 모두에서 사실과 다르다**(경로가 다르고, 순서도 다르다).

### 2-4. 대응표

| 백테스트 | 라이브 | 판정 |
|---|---|---|
| 어댑터 sl/tp (`adapters.py:21-35`) | `position_monitor` 현재가 sl/tp (`:314-316`, `:327-328`) | **정합** (문턱 기준) |
| 어댑터 trail/`max_hold` | 전략 고유 규칙 청산 (MA·EMA·`max_hold`) | 관례 차이는 있으나 **결함 아님** |
| `rs_leader` `take_profit_pct=**99.0**` (`multiverse4_returns_export.py:193`) | `rs_leader` tp **0.15** | 🔴 **불일치** — 백테에 tp 가 사실상 없다 |
| (호출 자체가 없음) | 전략 고유 **tp/sl** — D-1 종가 vs 라이브 체결가 | 🔴 **이 문서의 대상** |

---

## §3. 3안

| 안 | 내용 | 백테 대응 | 비용 / 부작용 |
|---|---|---|---|
| **(1)** | `on_tick` 루프에 `ctx.get_current_price()`(`trading_context.py:242` 실재) 를 주입해 **전략 tp/sl 만** 라이브가로 판정 | **백테에 짝이 없음** — 검증할 대조군이 없다 | 같은 일을 하는 경로가 **둘 유지** · 8전략 시그니처 변경 |
| **(2) 추천** | 8전략 `evaluate_sell_conditions` 의 **sl/tp 분기 삭제** → 범용 경로에 위임. 규칙 청산(MA·EMA·`max_hold`)은 그대로 | ◎ **백테 경로가 이 함수를 호출하지 않는다** ⇒ *결과 불변은 구조적으로 참* | 2026-08-25 정상 익절 2건(`161890`·`257720`)은 **전부 범용 경로**였다 |
| **(3)** | `entry_band_down_pct` 를 설정 | × 백테에 밴드가 없다 | **증상만 차단** · 진입 품질은 **별도 축** — 이 문서에서 섞지 않는다 |

---

## §4. 사전등록 예측 — **2안 채택 시 · 실행 «전» 동결**

### P1 (백테)

> **실행 대상**: `python scripts/multiverse4_returns_export.py`
> **예측**: 수정 전후 산출물 **diff = 0**.

🔴 **P1 통과의 의미를 오해하지 말 것** — 그 경로는 §2-1 대로 `evaluate_sell_conditions` 를 **애초에 부르지 않는다.**
⇒ P1 은 **「전제 확인」이 아니라 「부수효과 없음」 확인**이다. diff 가 0 이어도 그것은 2안의 근거가 «되지» 않는다(근거는 §2-1 자체다).
diff 가 0 이 «아니면» 삭제가 의도치 않은 곳을 건드린 것 ⇒ **중단·재조사.**

### P2 (테스트)

> 워크트리에서 전체 스위트 A/B(gate4 방식 — **같은 cwd · 같은 Python**), 실패 **«집합» 양방향 차분**.

**선별 기준 (동결)** — 이름이 아니라 **행위** 기준:
> `evaluate_sell_conditions` 를 **직접 호출**하거나, `exit_reason in {stop_loss, take_profit}` 을 **단언**하는 테스트.
> 확정 명령: `grep -rn 'exit_reason.*== "stop_loss"\|== "take_profit"' tests/`

**예측 집합 P2 (동결) — 26건**

| 파일 | 테스트 |
|---|---|
| `tests/test_book_envelope_200d.py` | `:33` `test_evaluate_sell_priority_sl_tp_mh` |
| `tests/test_daytrading_3methods_breakout.py` | `:162` `test_stop_loss_minus10pct` · `:172` `test_stop_loss_boundary_minus8pct_no_sell` · `:182` `test_take_profit_plus10pct` · `:212` `test_priority_sl_over_max_hold` · **`:312` `test_generate_signal_sell_branch_for_holding`**(단언 `:324`) |
| `tests/test_strategy/test_book_pullback_ma20_consistency.py` | `:162` `test_stop_loss_first` · `:172` `test_take_profit` · `:182` `test_take_profit_threshold_is_10pct` · `:232` `test_priority_sl_over_max_hold` · **`:300` `test_generate_signal_sell_branch_for_holding`**(`:312`) |
| `tests/test_strategy/test_book_pullback_ma5_consistency.py` | `:160` `test_stop_loss_tight_3pct` · `:170` `test_stop_loss_boundary_minus2pct_no_sell` · `:183` `test_take_profit` · `:218` `test_priority_sl_over_max_hold` · **`:286` `test_generate_signal_sell_branch_for_holding`**(`:298`) |
| `tests/test_strategy/test_elder_ema_pullback_consistency.py` | `:154` `test_stop_loss_first` · `:164` `test_take_profit` · `:210` `test_priority_sl_over_tp` |
| `tests/test_strategy/test_minervini_volume_dryup_consistency.py` | `:143` `test_stop_loss_first` · `:153` `test_take_profit` · `:195` `test_priority_sl_over_max_hold` · **`:246` `test_generate_signal_sell_when_holding`**(`:261`) |
| `tests/strategies/rs_leader/test_strategy.py` | `:65` `test_sell_stop_loss` |
| `tests/strategies/deep_mr_dev20/test_strategy.py` | `:46` `test_sell_stop_loss_first` · `:53` `test_sell_take_profit` |

**합계 26건.** 굵은 4건은 **오직 `stop_loss` 로 SELL 을 유도하는 테스트**라 삭제 시 **반드시 실패**한다
(넷 다 단언이 `assert sig.metadata["exit_reason"] == "stop_loss"`).

#### 🔴 판정 규칙 (동결)

> **예측 집합 P2 = 위 26건 ⊇ 실제 실패 집합.**
> 위 목록 **«밖»의 실패가 1건이라도 있으면 부수효과다 ⇒ 중단.**

⚠️ **포함 관계이지 등호가 아니다** — 단언이 **부정형**인 **3건**은 삭제 후에도 통과할 수 있다:
`daytrading:172`(`assert sell is False`) · `ma5:170`(`assert sell is False`) · `ma20:182` `test_take_profit_threshold_is_10pct`(`assert reason != "take_profit"`).
⇒ 26건 «안»에서 생기는 차이는 **예측 오차로 기록**하고, 그것을 근거로 중단하지 않는다.

### P3 (라이브 · 발효 후 5거래일)

> 전략 고유 경로 `reason` 에 「익절 도달」·「손절 도달」 **5거래일 연속 0건**.

🔴 **기준선 동결 (필수)** — 이 예측은 기준선 없이는 판별력이 없다.
고유 경로 sl/tp 발화 이력 = **9건 / 54거래일 / 7일**(06-12·15·16, 08-18·19·21·25).
- **전 기간 비율(7/54)로 잡으면** 5거래일 0건은 무수정으로도 **≈50%** 확률 ⇒ ***그 기준선은 쓰지 않는다.***
- **동결 기준선 = 최근 6거래일 중 4일 발화(4/6).** 이 기준선에서 **5거래일 연속 0건이면 p ≈ 0.004.**

부수 예측 — **0초 익절 왕복 0건** · 규칙 청산(MA·EMA·`max_hold`) 발화 수가 수정 전 5일과 **같은 자릿수**(굶김 악화 없음).

### P4 (개입률 판별자)

고유 경로가 **규칙 청산만** 남으므로 EOD 점검표의 개입률 정의를 갱신해야 한다. **점검표 문서 갱신은 후속 작업**이다.

---

## §5. 절차

1. 사장님이 **안 선택**
2. **워크트리** 생성 (🔴 라이브 트리에서 수정·테스트 금지)
3. 8전략 수정 — **한 커밋**
4. **P1 · P2 실행 및 기록**
5. 머지 → 봇 재시작
6. **P3 5거래일 관측** (기준선 4/6 대비)
7. 판정

### 5-1. 미머지 브랜치 `fix/rs-leader-entry-exit-overlap`

merge-base **`a0be826`** 기준 변경 파일 5개 —
`rs_leader/README.md` · `config.yaml` · `rule.py`(+22) · **`strategy.py`(+4/−1)** · `test_entry_exit_overlap.py`(신규 181줄).

- `strategy.py` 의 hunk 는 `_check_abs_trend` 의 **이유 문자열**(`:125-131` 부근)이고, **sl/tp 블록(`:138-150`)은 건드리지 않는다.**
- ⚠️ 다만 그 hunk 가 **sl/tp 블록 «위»에 순증 3줄**을 넣어 **줄 번호가 밀린다.**
- ⇒ ***「충돌 없음」은 미확인이다*** — 실제 머지를 시도해 보지 않았다. 4단계 전에 확인한다.

---

## §6. 이 문서가 답하지 «않는» 것

- **하한 밴드**(`entry_band_down_pct`) — 진입 품질 축. 별도 문서. **밴드 발화 계기부터 만들어야 한다**(§1-5).
- **규칙 청산이 D-1 종가로 판정되는 것** — 백테 어댑터와 같은 관례다. 결함이 아니다.
- **범용 경로의 음수 tp 버그**(§0 세 번째 갈래, `position_monitor.py:311-315`) — 별건.
- **`rs_leader` 백테 tp = 99.0** (§2-4) — 백테 설정 축. 별건.
- **`position_monitor` 가 먼저 팔아 고유 청산이 굶는 문제** — `docs/2026-07_전략고유청산_공백_재해석.md` 가설 A.

---

## §7. 실행 기록 (2026-08-25 저녁 · 동결 «후»)

**환경** — 베이스라인 워크트리 `D:/tmp/kis-wt-tpsl-base`(detached `86ff02d`) · 수정 워크트리 `D:/tmp/kis-wt-gate4` 브랜치 `fix/strategy-tpsl-delegate`(base `86ff02d`) · VS 번들 Python · cwd = 각 워크트리 루트. 🔴 **라이브 트리 실행 0.**

**코드 (2안)** — 8전략 `strategies/<name>/strategy.py` 의 sl/tp 분기 삭제. **8 files +42/−74** · `tests/`·`core/` 무변경 · 시그니처 유지 · docstring 「백테스트 우선순위 1:1 복제」 **8/8 정정**.

### 7-1. P2 ✅ — 예측 집합 안에서만 깨졌다

| 실행 | 결과 | 소요 |
|---|---|---|
| **A** 베이스라인 | 11 failed / 4,802 passed / 4 skipped / 1 xfailed | 195.7s |
| **B** 수정 후 (테스트 미수정) | 34 failed / 4,779 passed | 186.2s |

- `A − B` = **0** · `B − A` = **23건, 전부 예측 26건 «안»** · **목록 «밖» 실패 0** ⇒ §4 P2 판정 규칙 충족.
- 부정형 단언 3건(`daytrading:172` · `ma5:170` · `ma20:182`)은 **예측대로 통과**했다(26 − 23 = 3).

### 7-2. 테스트 갱신 — 삭제가 아니라 «새 동작 단언»으로 대체

- 23건을 `*_delegated_to_position_monitor` 로 개명해 위임 동작을 단언.
- `test_generate_signal_sell_*` 4건은 픽스처를 **+3% · `entry_time` 200일 전**으로 바꿔 `max_hold` 로 SELL 을 유도 ⇒ **`_check_sell` 경로 커버리지 유지.**
- 🔑 **부수 발견** — `test_generate_signal_intraday_held_no_sell` **2건(ma20·ma5)**이 sl 삭제로 **항진명제**가 됐다(옛 픽스처는 일봉 경로도 `None` 을 반환). 같은 방식으로 판별력을 복원하고 일봉 `max_hold` 전제 단언을 추가했다.
- `tests/` **8 files +224/−117**.

### 7-3. C ✅ — 코드 + 테스트 갱신 후 전체 스위트

**11 failed / 4,802 passed (207.6s)** — 실패 «집합»이 A 와 **양방향 차분 0**. ⇒ 회귀 없음.

### 7-4. P1 ✅ — 백테 산출물 불변

`scripts/multiverse4_returns_export.py --smoke --start 2024-03-13 --end 2026-05-31`(등록부 공통 창) 수정 전후 —
**18파일 바이트 동일**(`diff -rq` 0 · `summary.tsv` md5 동일).

거래 수: `elder` 842 · `envelope` 271 · `daytrading` 469 · `minervini` 139 · `ma20` 564 · `ma5` 913 · `rs_leader` 1,018 · `deep_mr` 207.

⚠️ **첫 실행은 측정으로 쓰지 않았다** — `--smoke` 기본 창(2021-01-04~)은 시작 `scan_date` 가 `market_cap` 커버리지(2024-03-13) «이전»이라 유니버스가 비어 **8전략 전부 signals = 0** 인 **공허한 통과**였다.

🔑 **§4 P1 그대로** — 이 통과는 **「부르지 않는다」의 부수효과 없음** 확인이지 **전제 확인이 아니다.**

### 7-5. 🔴 부수효과 — 실행 중 발견, **사전등록 «밖»**

**(가) 09:00~09:05 손절 스킵.** `core/trading/position_monitor.py:219-224` 의 `is_before_rebalancing` 이 그 창에서 **손절만 건너뛴다**(익절은 판정).
지금까지는 이 창에서 **전략 고유 sl** 이 발화할 수 있었다 — 전 이력 고유 sl 5건 중 **이 창 2건**(8/18 `041830` · 8/19 `096530`, 둘 다 D-1 종가 기준 이미 −8% 초과).
2안 후에는 **09:05 범용 손절이 잡는다** ⇒ 영향 = **54거래일 중 2건 · 최대 5분 지연**. ⬜ **사장님 판단 항목.**

**(나) 죽은 가드 계열.** `position_monitor.py:314-315`(tp) · `:327-328`(sl) 은 `hasattr` + truthy 가드라
`target_profit_rate` / `stop_loss_rate` 가 `None` 또는 `0` 이면 **sl/tp 판정이 조용히 건너뛰어진다.**
08-07 이후 레코드엔 전부 값이 있다. ⬜ **별건 백로그.**

### 7-6. 남은 것

| 항목 | 상태 |
|---|---|
| **P3** — 발효 후 5거래일 라이브 관측 (기준선 4/6 · p ≈ 0.004) | ⬜ 미착수 |
| **P4** — EOD 점검표 개입률 정의 갱신 | ⬜ 미착수 |
| 커밋 · 머지 · 봇 재시작 | ⬜ **사장님 확인 후** |

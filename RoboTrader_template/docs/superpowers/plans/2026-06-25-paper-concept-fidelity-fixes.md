# 가상매매 컨셉-구현 갭 교정 (8전략) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-06-25 행동검증(audit-2026-06-25-paper-concept-fidelity-8strategies)에서 드러난 청산/실행 레이어 공통갭 A~F를 교정해, 8전략의 컨셉이 가상매매에서 백테스트와 동등하게 발사되도록 만든다.

**Architecture:** 진입 신호·룰 코드는 이미 8/8 충실 — 손대지 않는다. 수정은 전부 **봇 실행 레이어**(`main.py` 후보배정, `core/trading/position_monitor.py` 청산경로, `core/trading_context.py` 진입게이트, `core/trading_decision_engine.py` 손절률 결정, 재시작/리밸런싱 청산경로). 각 수정은 백테스트 룰을 SSOT로 두고 실행경로를 거기에 맞춘다. 모든 변경은 TDD + 전체 스위트(3258+ passed) green 유지.

**Tech Stack:** Python 3.9, pytest, PostgreSQL 16(robotrader@5433), pandas. 봇은 async asyncio 루프.

## Global Constraints

- 테스트 SSOT: `cd RoboTrader_template && python -m pytest tests/ -q` 전체 green(현재 3258 passed 기준, 회귀 0).
- 데이터 SSOT: 일봉=`robotrader_quant.daily_prices`(close 이미 수정주가, adj_factor 곱하지 말 것, date text coerce). 분봉=`robotrader.minute_candles`.
- 진입 룰 코드(`strategies/books/**/rules*.py`, `scripts/rs_leader/rule.py`, `scripts/discovery/rules.py`)는 백테스트↔라이브 SSOT — **수정 금지**(이번 범위 아님).
- 권한: 코드 편집·테스트=직원 에이전트 수행. git commit/push=사장님 확인 필요. DB는 SELECT만.
- 숫자·메커니즘은 반드시 데이터/코드로 검증(추정 금지). 미확정은 스파이크로 먼저 확정.
- 8전략 전부 `holding_period="swing"` + `exit_timeframe="daily"`. 청산은 **확정 일봉 기준**이 원칙(분봉 평가는 컨셉 위반).

---

## 의존성·우선순위 한눈

| 순서 | Task | 상태 | 의존 |
|---|---|---|---|
| 0 | A 메커니즘 확정 스파이크 (09:00 일괄청산 출처) | ✅ 완료 → A=B 확정 | — |
| 1 | E: daytrading 유니버스 폴백 누수 차단 | 🟢 TDD 준비됨 | 없음 |
| 2 | C: elder 매수스톱 게이트 실행레이어 강제 | 🟢 TDD 준비됨 | 없음 |
| 3 | ~~A-fix~~ → **Task 4로 통합(해소)** | ✅ A=B 동일근본 | — |
| 4 | B(+A): 전략-소유 daily 포지션 청산 분봉평가 제거 | 🟡 PR#8 정리 동반 | — |
| 5 | D: 손절률 Signal역산/FLOOR 전략별 정합 검증 | 🟡 검증→결정 | 없음 |
| 6 | F: ma5 sl·minervini 집중 (설계결정) | 🟢 사장님 결재 | 측정 |

> **Task 0 결과(2026-06-25-A-mechanism-findings.md)**: A(06-22 09:00 일괄청산)는 강제청산/리밸런싱/EOD 버그가 **아님**. `position_monitor.py`의 tp/sl 체크(L307-327)가 전략-소유 daily 포지션을 **분봉 첫틱가로 평가·실행**(H3) = 그 자체가 **B**. 198440 +68.9%는 06-18 tp 미발사(고가 1,859>tp 1,573) + **06-19 봇 조기종료(기존 사고 diag-2026-06-19)** + 주말 = 4일 평가공백이 증폭. ⇒ **A-fix는 Task 4(B)가 흡수**. 06-19 운영중단은 이미 별건 처리됨.
> Task 1·2는 독립이라 병렬 착수 가능. Task 4는 PR#8 정리 동반. Task 5·6은 언제든.

---

### Task 0: A 메커니즘 확정 스파이크 (코드/로그 트레이싱)

**목적:** 06-18(목) 매수 → 06-22(월) 09:00 일괄청산(envelope·daytrading; 198440 +68.9%·073190 −26.6% 무차별)의 **정확한 코드 경로**를 확정한다. `bot/liquidation_handler.py`는 EOD(15:00)만 담당이라 09:00 출처가 아님 → `rebalancing_mode:true`(config) + 봇 재시작 경로가 유력하나 **미확정**. 이 스파이크 없이는 A-fix의 TDD 코드를 지어낼 수 없다.

**Files (조사 대상, 수정 없음):**
- Read: `RoboTrader_template/main.py` (run_daily_cycle, 리밸런싱/재시작 청산 호출부)
- Read: `RoboTrader_template/bot/state_restorer.py` (재시작 포지션 복원 + 복원 후 청산여부)
- Read: `RoboTrader_template/core/trading/position_monitor.py:230-345` (is_before_rebalancing 분기, max_hold·tp·sl)
- Read: `RoboTrader_template/logs/` 의 2026-06-22 봇 로그 (09:00~09:10 매도 사유 문자열)
- DB: `SELECT timestamp, stock_code, price, profit_loss FROM virtual_trading_records WHERE source='kis_template' AND action='SELL' AND timestamp::date='2026-06-22' AND timestamp::time < '09:30' ORDER BY timestamp;`

- [ ] **Step 1: 06-22 09:00 매도 레코드 전수 추출** — 위 SQL로 종목·체결가·pnl·정확 시각 확보. envelope 6 + daytrading 4 등 일괄 여부 확인.
- [ ] **Step 2: 해당 시각 봇 로그의 매도 사유 문자열 grep** — `position_monitor`의 "보유기간…초과"/"손절 신호"/"익절 신호"/"트레일링" 중 무엇인지, 아니면 `liquidation_handler`/리밸런싱/StateRestorer 경로인지 식별. 로그 없으면 그 사실을 기록.
- [ ] **Step 3: 코드 경로 확정** — Step 2 사유 문자열을 코드에서 역추적해 **정확한 파일:라인**과 트리거 조건을 특정. `rebalancing_mode` 진입 시 장초 일괄정리 루틴이 있으면 그 위치.
- [ ] **Step 4: 산출물 작성** — `docs/superpowers/plans/2026-06-25-A-mechanism-findings.md`에 (경로·트리거·왜 sl/tp 우회했는지·재현 테스트 설계)를 적는다. 이 문서가 Task 3의 입력.

**Deliverable:** A의 확정 코드경로 + 재현 테스트 설계. (코드 변경 0, 커밋 0 — 조사 산출물만.)

---

### Task 1: E — daytrading 유니버스 폴백 누수 차단

**근본원인(확정):** `main.py:653-670` `should_use_volume_fallback()`가 후보 0인 전략 발생 시 거래량순 폴백 풀을 `accepts_volume_fallback=True`(기본) 첫 전략에 배정하는데, 이 폴백 풀은 **스크리너 base_filter(거래대금≥10억·시총<5천억)를 거치지 않는다**. 결과 daytrading 8/26(30.8%) 유니버스 위반. 스크리너 자체(`strategies/daytrading_3methods_breakout/screener.py` base_filter)는 정상.

**설계 결정:** 폴백 배정 시에도 **수용 전략의 스크리너 base_filter를 폴백 풀에 적용**한다(가장 안전·DRY). 전략 어댑터는 이미 `base_filter(universe)`를 가지므로 재사용.

**Files:**
- Modify: `RoboTrader_template/main.py:653-670` (폴백 배정 직전 base_filter 통과)
- Test: `RoboTrader_template/tests/test_phase_e6_candidate_pool_per_strategy.py` (기존 파일에 케이스 추가)

**Interfaces:**
- Consumes: 전략 스크리너 어댑터의 `base_filter(self, universe: List[Dict]) -> List[Dict]` (거래대금·시총 컷). daytrading 어댑터=`Daytrading3MethodsBreakoutScreenerAdapter`.
- Produces: 폴백 풀이 base_filter 통과분만 포함 → 진입 유니버스 위반 0.

- [ ] **Step 1: 실패 테스트 작성** — 거래대금 5억(컷 10억 미만)·시총 6천억(컷 5천억 초과) 종목이 섞인 거래량 폴백 풀을 만들고, daytrading에 배정된 최종 pool에 그 종목들이 **빠져야** 함을 단언.

```python
def test_volume_fallback_respects_strategy_base_filter():
    # given: 폴백 후보에 필터 위반 종목 포함
    fallback = [
        _cand(code="000001", trading_value=500_000_000, market_cap=600_000_000_000),  # 위반(거래대금<10억·시총>5천억)
        _cand(code="000002", trading_value=2_000_000_000, market_cap=300_000_000_000),  # 통과
    ]
    pool = apply_volume_fallback_with_filter("daytrading_3methods_breakout", fallback, strategy_instance)
    codes = {c.code for c in pool}
    assert "000002" in codes
    assert "000001" not in codes  # base_filter가 폴백에도 적용
```

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_phase_e6_candidate_pool_per_strategy.py::test_volume_fallback_respects_strategy_base_filter -v` → FAIL.
- [ ] **Step 3: 최소 구현** — `main.py` 폴백 배정 블록에서, 수용 전략의 screener 어댑터를 얻어 `base_filter`로 폴백 풀을 거른 뒤 배정. 어댑터 미존재 전략은 기존 동작 유지(보수적). (정확 코드는 main.py:653-670 구조에 맞춰 작성 — base_filter는 dict 리스트를 받으므로 Candidate→dict 변환 후 통과 코드만 잔류.)
- [ ] **Step 4: 통과 확인** — 위 테스트 PASS + `python -m pytest tests/test_phase_e6_candidate_pool_per_strategy.py -q` 회귀 0.
- [ ] **Step 5: 전체 스위트** — `cd RoboTrader_template && python -m pytest tests/ -q` green.
- [ ] **Step 6: 커밋(사장님 확인 후)** — `fix(universe): 거래량 폴백 풀에 전략 base_filter 적용 — daytrading 유니버스 누수 차단`.

---

### Task 2: C — elder 매수스톱 게이트 실행레이어 강제

**근본원인(확정):** `core/trading_context.py`에 `entry_min_price`/`buy_stop` 참조 0건. PR 3629d13이 `Signal.metadata`/entry_min에 매수스톱(전일고가+1틱)을 세팅했으나 **실행레이어(`TradingContext.buy()`)가 그 값을 게이트로 쓰지 않는다**. 결과 elder 31건 중 17건이 당일 고가가 buy_stop 미도달인데 체결(돌파 게이트 미작동 → 백테스트 stop-fill 정합 훼손).

**설계 결정:** `TradingContext.buy()`(또는 그 직전 실행경로)에서 **실시간 현재가 < entry_min_price면 주문 미제출**(스킵+로그). 백테스트는 stop 돌파 시에만 체결되므로, 라이브도 현재가가 매수스톱 이상일 때만 진입. 게이트 값 소스는 Signal이 전달하는 entry_min(=buy_stop). 다른 전략은 entry_min 미설정이면 무조건 통과(기존 동작 보존).

**Files:**
- Modify: `RoboTrader_template/core/trading_context.py` (`buy()` — entry_min 게이트 추가)
- Read(확인): `RoboTrader_template/strategies/elder_ema_pullback/strategy.py` (Signal에 매수스톱을 어떤 키로 싣는지 — entry_min_price / metadata['buy_stop'])
- Test: `RoboTrader_template/tests/test_strategy/test_elder_ema_pullback_consistency.py` 또는 신규 `tests/test_trading_context_entry_gate.py`

**Interfaces:**
- Consumes: `Signal.entry_min_price`(또는 strategy.py가 쓰는 실제 키 — Step 1에서 확정). 실시간가=`ctx`/broker 현재가.
- Produces: 현재가<entry_min이면 `buy()`가 주문 없이 False/None 반환 + "매수스톱 미도달 스킵" 로그.

- [ ] **Step 1: Signal 키 확정** — `strategies/elder_ema_pullback/strategy.py`에서 매수스톱을 싣는 정확한 필드명 확인(`entry_min_price` vs `metadata['buy_stop']`). 테스트·구현 모두 이 키 사용.
- [ ] **Step 2: 실패 테스트 작성** — 현재가가 entry_min보다 낮은 BUY 요청 시 주문이 제출되지 않음(미체결)을 단언. 현재가≥entry_min이면 정상 제출.

```python
def test_buy_skipped_when_price_below_entry_min():
    ctx = _make_ctx(current_price=10_000)
    sig = _signal(stock="005930", entry_min_price=10_100)  # 매수스톱 미도달
    ok = ctx.buy(sig)            # 또는 실제 호출 시그니처
    assert ok is False
    assert _no_order_submitted()

def test_buy_proceeds_when_price_at_or_above_entry_min():
    ctx = _make_ctx(current_price=10_200)
    sig = _signal(stock="005930", entry_min_price=10_100)
    ok = ctx.buy(sig)
    assert ok is True
```

- [ ] **Step 3: 실패 확인** — `python -m pytest tests/test_trading_context_entry_gate.py -v` → FAIL.
- [ ] **Step 4: 최소 구현** — `TradingContext.buy()` 진입부에서 entry_min 존재 시 실시간 현재가와 비교, 미달이면 로그 남기고 주문 경로 미진입. entry_min None이면 통과.
- [ ] **Step 5: 통과 확인 + 회귀** — 위 테스트 PASS, elder consistency 테스트 + 전체 스위트 green.
- [ ] **Step 6: 커밋(확인 후)** — `fix(elder): 매수스톱(entry_min) 게이트를 TradingContext.buy 실행레이어에서 강제 — 돌파 게이트 정합`.

---

### Task 3: ~~A-fix~~ → Task 4(B)로 통합·해소 ✅

**Task 0 결론(`2026-06-25-A-mechanism-findings.md`):** A는 별도 강제청산 경로가 **아니다**. 06-22 09:00 일괄청산은 `position_monitor._analyze_sell_for_stock`의 정상 동작이었고, 근본은 **전략-소유 daily 포지션의 tp/sl을 분봉 첫틱가로 평가·실행(H3)** = Task 4(B)와 동일. 추가로 `is_before_rebalancing=(hour==9 and minute<5)`가 09:05까지 **손절만 억제하고 익절은 허용** → 갭상승 승자는 09:00~03 시가 갭에 익절, 갭하락 패자는 09:05 손절로 무차별 처분된 구조.

**증거(검증값):** 198440 일봉 06-17 close 1430 → 06-18 high 1859(tp 1573 이미 돌파) → 06-19 close 2415 → 06-22 open 2830. 충실한 청산이면 06-18에 +10~30% 청산이어야 했으나, 06-18 tp 미발사 + 06-19 봇 조기종료(diag-2026-06-19) + 주말 평가공백이 +68.9%까지 방치.

**조치:** 별도 코드 없음. **Task 4가 흡수** — daily 포지션 청산을 확정 일봉(또는 백테스트 체결모델) 기준으로 환원하면 갭 첫틱 극단체결이 사라진다. `is_before_rebalancing`의 익절/손절 비대칭도 Task 4에서 함께 검토.

---

### Task 4: B(+A) — 전략-소유 daily 포지션의 분봉 청산평가 제거

> **이 task가 A를 흡수한다.** 추가로 `position_monitor.py:221-224`의 `is_before_rebalancing=(hour==9 and minute<5)`가 09:05까지 **손절만 억제·익절 허용**하는 비대칭이 갭장초 무차별 청산에 기여 → Step에서 함께 검토(daily SSOT 환원 시 익절도 분봉가 평가에서 빠지면 비대칭 자연 해소).

**근본원인(확정):** `core/trading/position_monitor.py` — 공통 트레일링만 :288(`if strategy_for_sell is None`)에서 스킵되고, **tp/sl(:307-327)와 전략 generate_signal 청산(:329+)은 전략-소유 포지션에도 분봉 current_price/intraday 데이터로 평가**된다. 8전략 전부 `exit_timeframe="daily"`이므로 청산은 확정 일봉 기준이어야 하나, 분봉 평가가 같은날 조기청산·whipsaw·주말 갭 첫틱 극단체결을 유발. 미머지 PR#8(a736065)이 generate_signal 경로(:329+) 가드를 다룸 — 본 task는 그것을 정리·머지하고 **tp/sl(:307-327) 분봉평가까지** exit_timeframe 가드로 확장한다.

**Files:**
- Modify: `RoboTrader_template/core/trading/position_monitor.py:283-344`
- Read: PR#8(a736065) diff — 기존 가드 재사용/확장
- Test: `RoboTrader_template/tests/` (분봉 whipsaw 가드 테스트 — PR#8 테스트 확장)

**설계 결정(확정 전 검증 필요):** 전략-소유 + exit_timeframe="daily" 포지션은 tp/sl/trail/generate_signal 청산을 **확정 일봉 종가 기준**으로만 평가. 단, 백테스트가 tp/sl을 일중 high/low(스톱주문)로 모델링하면 그에 맞춰야 하므로, **백테스트 엔진의 tp/sl 체결모델을 먼저 확인**(`backtest/engine.py`)해 라이브를 거기에 정합시킨다(이게 진짜 SSOT).

- [ ] **Step 1:** `backtest/engine.py`에서 tp/sl 체결모델 확인 — 일중 터치(high/low) vs 종가 기준. 이 결과가 라이브 청산 평가시점의 SSOT.
- [ ] **Step 2:** PR#8(a736065) 정리·리베이스 후 generate_signal 가드 머지 가능 상태 확인.
- [ ] **Step 3:** 실패 테스트 — 전략-소유 daily 포지션이 분봉 wick으로 조기청산되지 않음(Step1 모델에 맞춰). 주말 갭 첫틱에 sl이 일봉SSOT와 다른 가격으로 실행되지 않음.
- [ ] **Step 4~7:** 실패확인 → position_monitor 가드 확장 구현 → 통과/회귀(전체 스위트) → 커밋(확인 후).

> Task 0 결과 A가 (c)분봉 첫틱 경로로 판명되면 Task 3·4를 통합한다.

---

### Task 5: D — 손절률 Signal역산/FLOOR 전략별 정합 검증

**근본원인(부분확정):** `core/trading_decision_engine.py:537-540` — Signal.stop_loss(절대가)→비율 변환이 config(3순위, :542-553)보다 **우선**. 전략이 Signal에 룰기반 stop을 실으면 config sl(−7/−8%)과 분기 가능. `:578-581` STOP_LOSS_FLOOR 3%는 8전략엔 대체로 무해(ma5 −3%=경계). → 버그인지 의도인지 **전략별 실측 검증 후 결정**(추정 금지).

**Files:**
- Read: 8전략 strategy.py — generate_signal이 `Signal.stop_loss`/`target_price`를 세팅하는지, 세팅값이 config와 일치하는지
- DB: 각 전략 진입 레코드의 실제 적용 sl률(있으면 trading_stock/DB) vs config 비교
- Test: (분기 발견 시) `tests/test_decision_engine.py` 확장

- [ ] **Step 1:** 8전략 strategy.py 전수 — Signal에 stop_loss/target_price를 싣는 전략 목록화. 싣는 값이 config risk_management와 같은지/다른지 표로 정리.
- [ ] **Step 2:** 다르면(분기) → 어느 쪽이 백테스트 SSOT인지 확인 후 우선순위 교정(전략 의도가 config면 :537-540에서 config 우선, Signal이 의도면 문서화). 같으면 → 무해, 변경 없음(문서화만).
- [ ] **Step 3:** FLOOR 3%가 어떤 전략 진입에서 실제 binding 됐는지 DB/로그로 확인. ma5 외 binding 있으면 전략 sl 명시 시 FLOOR 면제 검토.
- [ ] **Step 4:** 교정 필요 시 TDD(실패테스트→구현→회귀) → 커밋(확인 후). 불필요 시 findings만 기록.

---

### Task 6: F — ma5 sl·minervini 집중 (설계결정, 사장님 결재)

**근본원인:** (F1) ma5 `sl −3%` + exit_timeframe=daily + 스윙보유 → 갭다운이 −3% 관통(SL관통 7/19, 평균 초과손실 4.2%p). 구조적. (F2) minervini volume_dryup이 동일종목(001510)을 매일 통과 → 7회 반복진입으로 K=3 슬롯 점유 + 1주 미니랏 이상체결 1건.

**성격:** 코드버그가 아니라 **전략 파라미터/정책 결정** → 멀티버스 측정 후 사장님 결재. 본 plan에서는 옵션만 제시하고 ②개선 단계로 이관.

- [ ] **Step 1(F1 측정):** ma5 sl ∈ {−3%(현), −5%, −6%} 백테스트 비교(net Sharpe·MaxDD·SL관통율). 멀티버스 1셀.
- [ ] **Step 2(F1 결정):** 사장님 결재 후 config 반영(TDD config 테스트).
- [ ] **Step 3(F2):** minervini 동일종목 재진입 쿨다운(예: 보유중/최근청산 종목 N일 재진입 금지) 설계안 제시 → 결재 후 TDD. 1주 미니랏 체결경로는 Task 0/4 로그에서 같이 추적.

---

## Self-Review

**Spec(audit A~F) 커버리지:** A→Task0+3, B→Task4, C→Task2, D→Task5, E→Task1, F→Task6. 진입/유니버스 충실(검증완료)은 변경 없음. 전부 매핑됨.

**Placeholder 스캔:** A-fix(Task3)·D·F의 일부 코드는 의도적으로 비움 — **미확정 메커니즘/미결정 정책에 가짜 코드를 넣지 않기 위함**(plan 원칙: 추정 금지). 각 task에 "선행 산출물/결재 후 코드 확정" 게이트 명시. C·E는 완전 TDD.

**타입 일관성:** Task1 `base_filter(List[Dict])→List[Dict]`, Task2 `Signal.entry_min_price`(Step1에서 실제 키 확정) — 후속 참조 일치.

**리스크:** Task 3·4는 position_monitor/재시작 경로라 회귀범위 큼 → 반드시 PR#8 테스트 + 전체 스위트 green. Task 0가 전체 신뢰의 핵심.

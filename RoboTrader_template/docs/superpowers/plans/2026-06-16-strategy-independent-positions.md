# 전략별 독립 포지션(완전 격리) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 두 개 이상의 전략이 동일 종목을 각자의 독립 자본으로 동시에 보유·운용할 수 있게 하여, 전략별 성과를 dedup 오염 없이 측정한다.

**Architecture:** 핵심 상태저장소 `StockStateManager`를 종목코드 단일키에서 `(owner_strategy_name, stock_code)` **복합키**로 전환한다. 단, `get_trading_stock(stock_code)` 등 기존 103개 호출부의 대량 수정을 피하기 위해 **하위호환 해소 규칙**(strategy 미지정 시 종목코드 단일 매칭으로 폴백, 충돌 시 경고)을 둔다. 충돌을 *생성*하는 경로(후보 dedup, 매수 등록·소유권 가드, 전략별 순회, 복원)만 명시적으로 strategy를 넘기도록 수정한다. 시세/주문실행 층(가격·KIS 주문=종목 단위)은 불변. DB는 이미 `strategy` 컬럼 보유·stock_code 유니크 제약 없음 → 스키마 변경 없음.

**Tech Stack:** Python 3.8+, pytest, PostgreSQL/TimescaleDB(localhost:5433), asyncio.

**근거 spec:** `docs/superpowers/specs/2026-06-16-strategy-independent-positions-scope.md`

**테스트 실행 기준선:** 전체 스위트의 사전존재 실패 32건(DB/오염 관련, main 베이스라인 동일)은 무시. 각 단계는 **순회귀 0** + 신규 테스트 GREEN을 확인한다.

```bash
cd /d/GIT/kis-trading-template/RoboTrader_template
python -m pytest <대상> -q
```

---

## 파일 구조 (생성/수정 맵)

| 파일 | 책임 | 변경 |
|---|---|---|
| `core/trading/stock_state_manager.py` | 종목 상태 저장소 | 복합키 전환 + 하위호환 해소 |
| `core/candidate_selector.py` | 전략별 후보 풀 | cross-strategy dedup 제거 |
| `core/trading_context.py` | 전략용 매수/매도 API | ② 소유권 가드 완화(동일전략만 차단) |
| `bot/state_restorer.py` | 오버나잇 복원 | (strategy, stock_code) 복원 |
| `core/trading/order_completion_handler.py` | 체결 콜백 | 다전략 통지 라우팅(order_id→owner) |
| `tests/test_strategy_independent_positions.py` | 신규 통합 테스트 | 생성 |
| `tests/test_trading/test_stock_state_manager_composite.py` | 상태저장소 단위 테스트 | 생성 |

---

## Phase 0 — 안전망 & 특성화

### Task 0.1: 현재 "동일종목 2전략 차단" 동작을 고정하는 특성화 테스트

**Files:**
- Test: `tests/test_trading/test_stock_state_manager_composite.py` (생성)

- [ ] **Step 1: 현재 동작(차단)을 명시하는 특성화 테스트 작성**

```python
# tests/test_trading/test_stock_state_manager_composite.py
import pytest
from core.trading.stock_state_manager import StockStateManager
from core.models import TradingStock, StockState


def _mk(stock_code: str, owner: str, state: StockState = StockState.POSITIONED) -> TradingStock:
    ts = TradingStock(stock_code=stock_code, stock_name=stock_code)
    ts.owner_strategy_name = owner
    ts.state = state
    return ts


def test_characterization_single_key_blocks_second_owner():
    """[특성화] 현재 구현: 동일 종목 2번째 POSITIONED 등록은 거부된다.

    이 테스트는 Phase 2에서 의도적으로 반대로 바뀐다(독립 허용).
    지금은 현재 동작을 못박아 회귀 기준점을 만든다.
    """
    mgr = StockStateManager()
    assert mgr.register_stock(_mk("010170", "minervini")) is True
    # 현재는 두 번째 전략의 동일종목 등록이 거부됨
    assert mgr.register_stock(_mk("010170", "rs_leader")) is False
```

- [ ] **Step 2: 실패가 아닌 통과를 확인 (현재 동작 고정)**

Run: `python -m pytest tests/test_trading/test_stock_state_manager_composite.py::test_characterization_single_key_blocks_second_owner -q`
Expected: **PASS** (현재 구현이 이 동작을 가짐). 통과하지 않으면 가정이 틀린 것 — 멈추고 재조사.

- [ ] **Step 3: 커밋**

```bash
git add tests/test_trading/test_stock_state_manager_composite.py
git commit -m "test(state): 동일종목 2전략 차단 현행동작 특성화 (Phase0 기준점)"
```

---

## Phase 1 — 후보 dedup 제거 (저위험)

### Task 1.1: `select_candidates_per_strategy`의 cross-strategy dedup 제거

**Files:**
- Modify: `core/candidate_selector.py:855-878`
- Test: `tests/test_candidate_selector_independent.py` (생성)

- [ ] **Step 1: RED — 두 전략 후보에 동일 종목이 모두 남는지 검증하는 실패 테스트**

```python
# tests/test_candidate_selector_independent.py
from unittest.mock import MagicMock
from core.candidate_selector import CandidateSelector
from db.repositories.candidate import CandidateStock  # 실제 import 경로는 기존 코드 따라 조정


def _cand(code):
    c = MagicMock(spec=CandidateStock)
    c.code = code
    c.name = code
    return c


def test_same_stock_kept_for_multiple_strategies(monkeypatch):
    selector = CandidateSelector.__new__(CandidateSelector)
    selector.logger = MagicMock()
    # 두 전략 모두 010170을 후보로 반환하도록 _fetch를 스텁
    def fake_fetch(strategy_name, max_candidates):
        return [_cand("010170"), _cand(f"{strategy_name}_only")]
    selector._fetch_candidates_for_strategy = fake_fetch

    result = selector.select_candidates_per_strategy(
        {"minervini": MagicMock(), "rs_leader": MagicMock()}, max_per_strategy=10
    )
    minv_codes = {c.code for c in result["minervini"]}
    rs_codes = {c.code for c in result["rs_leader"]}
    # 핵심: 010170이 두 전략 모두에 남아야 한다 (현재는 rs_leader에서 제거됨)
    assert "010170" in minv_codes
    assert "010170" in rs_codes
```

- [ ] **Step 2: RED 확인**

Run: `python -m pytest tests/test_candidate_selector_independent.py -q`
Expected: FAIL — `assert "010170" in rs_codes`에서 실패(현재 dedup이 제거함).

- [ ] **Step 3: GREEN — dedup 로직 제거**

`core/candidate_selector.py:855-878`을 다음으로 교체:

```python
        result: Dict[str, List[CandidateStock]] = {}

        # 전략별 자본이 독립이므로 종목 중복을 허용한다.
        # (과거 cross-strategy dedup은 공유 자본풀 시절의 잔재 — 독립 자본에선
        #  뒤 순서 전략의 신호를 부당하게 굶겨 성과 측정을 오염시켰다.)
        for strategy_name in strategies:
            raw = self._fetch_candidates_for_strategy(strategy_name, max_per_strategy)
            result[strategy_name] = raw
            self.logger.info(
                f"[E6] {strategy_name}: 후보 {len(raw)}종목"
            )

        return result
```

- [ ] **Step 4: GREEN 확인 + 회귀**

Run: `python -m pytest tests/test_candidate_selector_independent.py -q && python -m pytest tests/ -q -k "candidate or selector"`
Expected: 신규 PASS, 기존 candidate/selector 테스트 순회귀 0.

- [ ] **Step 5: 커밋**

```bash
git add core/candidate_selector.py tests/test_candidate_selector_independent.py
git commit -m "feat(candidate): cross-strategy 종목 dedup 제거 — 전략별 후보 독립 (Phase1)"
```

> ⚠️ Phase 1 종료 시점엔 ② 매수 가드가 살아있어 매수단에선 여전히 1전략만 보유한다. 부분 개선이며 롤백이 쉽다. Phase 2에서 본격 해소.

---

## Phase 2 — 상태저장소 복합키화 (코어)

### Task 2.1: `StockStateManager` 복합키 + 하위호환 해소

**Files:**
- Modify: `core/trading/stock_state_manager.py`
- Test: `tests/test_trading/test_stock_state_manager_composite.py` (Task 0.1 파일에 추가)

**설계:** 내부 저장소 키를 `(owner, stock_code)` 튜플로 변경. 공개 메서드는 `strategy: Optional[str] = None` 인자를 추가하되, **미지정 시 종목코드로 단일 매칭 폴백**(충돌 0건이면 기존 103 호출부 무수정 동작). `owner`는 `trading_stock.owner_strategy_name` 사용(빈 문자열이면 `"__legacy__"` 센티넬).

- [ ] **Step 1: RED — 독립 보유 + 폴백 해소 테스트 추가**

`tests/test_trading/test_stock_state_manager_composite.py`에 추가:

```python
def test_two_strategies_hold_same_stock_independently():
    """Phase2 목표: 동일 종목을 두 전략이 각자 POSITIONED로 보유한다."""
    mgr = StockStateManager()
    assert mgr.register_stock(_mk("010170", "minervini")) is True
    assert mgr.register_stock(_mk("010170", "rs_leader")) is True  # 이제 허용
    positioned = mgr.get_stocks_by_state(StockState.POSITIONED)
    owners = sorted(ts.owner_strategy_name for ts in positioned if ts.stock_code == "010170")
    assert owners == ["minervini", "rs_leader"]


def test_same_strategy_same_stock_still_blocked():
    """동일 전략이 같은 종목을 두 번 POSITIONED 등록하는 것은 여전히 차단."""
    mgr = StockStateManager()
    assert mgr.register_stock(_mk("010170", "minervini")) is True
    assert mgr.register_stock(_mk("010170", "minervini")) is False


def test_get_trading_stock_legacy_fallback_unique():
    """strategy 미지정 시 종목코드 단일 매칭이면 그 객체를 반환(하위호환)."""
    mgr = StockStateManager()
    mgr.register_stock(_mk("010170", "minervini"))
    ts = mgr.get_trading_stock("010170")
    assert ts is not None and ts.owner_strategy_name == "minervini"


def test_get_trading_stock_explicit_strategy():
    """strategy 지정 시 정확히 그 전략 소유 객체를 반환."""
    mgr = StockStateManager()
    mgr.register_stock(_mk("010170", "minervini"))
    mgr.register_stock(_mk("010170", "rs_leader"))
    ts = mgr.get_trading_stock("010170", strategy="rs_leader")
    assert ts is not None and ts.owner_strategy_name == "rs_leader"
```

- [ ] **Step 2: RED 확인**

Run: `python -m pytest tests/test_trading/test_stock_state_manager_composite.py -q`
Expected: `test_two_strategies...`, `test_get_trading_stock_explicit_strategy` FAIL. `test_characterization_single_key_blocks_second_owner`도 이제 깨질 것 → Step 3에서 그 특성화 테스트를 삭제/갱신한다(의도된 동작 반전).

- [ ] **Step 3: GREEN — 복합키 구현**

`stock_state_manager.py`를 다음 핵심 변경으로 수정:

(a) 키 헬퍼 + 저장소 타입:
```python
from typing import Dict, List, Optional, Any, Tuple

_LEGACY_OWNER = "__legacy__"

def _key(owner: Optional[str], stock_code: str) -> Tuple[str, str]:
    return ((owner or _LEGACY_OWNER), stock_code)
```

(b) `__init__`:
```python
        self.trading_stocks: Dict[Tuple[str, str], TradingStock] = {}
        self.stocks_by_state: Dict[StockState, Dict[Tuple[str, str], TradingStock]] = {
            state: {} for state in StockState
        }
```

(c) 종목코드로 모든 소유자 객체 찾는 내부 헬퍼:
```python
    def _find_by_code(self, stock_code: str, strategy: Optional[str] = None) -> List[TradingStock]:
        if strategy is not None:
            ts = self.trading_stocks.get(_key(strategy, stock_code))
            return [ts] if ts is not None else []
        return [ts for (own, code), ts in self.trading_stocks.items() if code == stock_code]
```

(d) `register_stock` — 동일 (owner, code) 충돌만 차단:
```python
    def register_stock(self, trading_stock: TradingStock) -> bool:
        with self._lock:
            owner = trading_stock.owner_strategy_name
            k = _key(owner, trading_stock.stock_code)
            existing = self.trading_stocks.get(k)
            if existing is not None and existing.state in (
                StockState.POSITIONED, StockState.BUY_PENDING
            ):
                self.logger.info(
                    f"[중복등록거부] {trading_stock.stock_code} owner={owner} "
                    f"state={existing.state.name} — 동일 전략 중복"
                )
                return False
            if existing is not None:
                old_state = existing.state
                self.stocks_by_state[old_state].pop(k, None)
            state = trading_stock.state
            self.trading_stocks[k] = trading_stock
            self.stocks_by_state[state][k] = trading_stock
            return True
```

(e) `get_trading_stock` — 하위호환 해소:
```python
    def get_trading_stock(self, stock_code: str, strategy: Optional[str] = None) -> Optional[TradingStock]:
        with self._lock:
            matches = self._find_by_code(stock_code, strategy)
            if not matches:
                return None
            if len(matches) > 1:
                self.logger.warning(
                    f"[모호조회] {stock_code} 다중 소유({len(matches)}) — strategy 인자 필요. "
                    f"첫 소유자 반환: {matches[0].owner_strategy_name}"
                )
            return matches[0]
```

(f) `unregister_stock`, `change_stock_state`, `update_current_order` — `strategy: Optional[str] = None` 인자 추가 후 `_find_by_code(stock_code, strategy)`로 대상 객체를 찾고, 그 객체의 `owner_strategy_name`으로 `_key`를 구성해 `trading_stocks`/`stocks_by_state`에서 조작하도록 변경. 예 `change_stock_state`:
```python
    def change_stock_state(self, stock_code: str, new_state: StockState,
                           reason: str = "", strategy: Optional[str] = None) -> None:
        with self._lock:
            matches = self._find_by_code(stock_code, strategy)
            if not matches:
                return
            if len(matches) > 1:
                self.logger.warning(
                    f"[모호상태변경] {stock_code} 다중 소유 — strategy 미지정, 첫 소유자 적용"
                )
            trading_stock = matches[0]
            k = _key(trading_stock.owner_strategy_name, stock_code)
            old_state = trading_stock.state
            valid_next_states = _VALID_TRANSITIONS.get(old_state, [])
            if new_state not in valid_next_states:
                self.logger.warning(
                    f"[비정상 상태전이] {stock_code} {old_state.value} → {new_state.value} "
                    f"(허용: {[s.value for s in valid_next_states]}) | 사유: {reason}"
                )
            self.stocks_by_state[old_state].pop(k, None)
            trading_stock.change_state(new_state, reason)
            self.stocks_by_state[new_state][k] = trading_stock
            self._log_detailed_state_change(trading_stock, old_state, new_state, reason)
```

`get_stocks_by_state`/`get_portfolio_summary`는 `.values()` 순회라 키 변경에 영향 없음(그대로).

- [ ] **Step 4: 특성화 테스트 갱신**

Task 0.1의 `test_characterization_single_key_blocks_second_owner`를 삭제(동작이 의도적으로 반전됨). 커밋 메시지에 명시.

- [ ] **Step 5: GREEN 확인 + 광범위 회귀**

Run:
```bash
python -m pytest tests/test_trading/test_stock_state_manager_composite.py -q
python -m pytest tests/ -q
```
Expected: 신규 4 PASS. 전체 스위트 사전존재 32 실패 외 **순회귀 0**. 새로 깨지는 테스트가 있으면 그 호출부가 strategy 인자를 필요로 하는 곳 — Task 2.2에서 처리.

- [ ] **Step 6: 커밋**

```bash
git add core/trading/stock_state_manager.py tests/test_trading/test_stock_state_manager_composite.py
git commit -m "feat(state): trading_stocks 복합키화 (전략,종목) + 하위호환 해소 (Phase2)"
```

### Task 2.2: 회귀로 드러난 모호조회 호출부에 strategy 배선

**Files:**
- Modify: Task 2.1 Step 5에서 `[모호조회]`/`[모호상태변경]` 경고 또는 실패가 난 호출부 (예상: `core/trading/order_completion_handler.py`, `core/trading/position_monitor.py`, `bot/liquidation_handler.py`)
- Test: 해당 호출부의 기존 테스트

- [ ] **Step 1: 모호조회 발생 지점 수집**

Run: 라이브 e2e 대신, 통합 테스트(Task 3.1)와 전체 스위트 로그에서 `모호조회`/`모호상태변경` 경고를 grep.
```bash
python -m pytest tests/ -q 2>&1 | grep -i "모호" || echo "모호조회 없음"
```

- [ ] **Step 2: 각 지점에 owner 전략 전달**

호출부가 이미 `trading_stock` 객체를 들고 있으면 `change_stock_state(ts.stock_code, new_state, reason, strategy=ts.owner_strategy_name)` 형태로 명시. order 콜백은 order_id로 찾은 `trading_stock`의 owner를 사용. 각 수정마다 해당 파일의 기존 테스트 실행해 GREEN 유지.

- [ ] **Step 3: 커밋**

```bash
git add -A
git commit -m "fix(state): 다중소유 모호조회 지점에 owner 전략 명시 배선 (Phase2)"
```

### Task 2.3: `trading_context.buy()` ② 소유권 가드 완화

**Files:**
- Modify: `core/trading_context.py:331-346`
- Test: `tests/test_strategy_independent_positions.py` (생성)

- [ ] **Step 1: RED — 다른 전략이 동일 보유종목을 매수할 수 있는지 검증**

```python
# tests/test_strategy_independent_positions.py
# ctx.buy의 소유권 가드만 단위 검증 — 다른 전략은 통과, 동일 전략은 차단.
# (decision_engine/analyzer는 MagicMock으로 격리)
```
(테스트 본문은 기존 `tests/`의 trading_context 테스트 패턴을 따라 작성: `existing.state=POSITIONED, owner="minervini"`인 상태에서 `_current_strategy_name="rs_leader"`의 buy가 가드에서 `return None` 되지 않고 진행되는지 확인. 동일 owner면 차단 유지.)

- [ ] **Step 2: RED 확인** — 현재 가드는 owner 무관 차단이므로 rs_leader도 거부됨 → FAIL.

- [ ] **Step 3: GREEN — 가드를 "동일 전략 보유 시에만 차단"으로 변경**

`core/trading_context.py:336-346`을 수정:
```python
                existing = stock_state_mgr.get_trading_stock(
                    stock_code, strategy=self._current_strategy_name
                )
                if existing is not None and existing.state in (
                    StockState.POSITIONED, StockState.BUY_PENDING
                ):
                    self.logger.info(
                        f"매수 거부: {stock_code}는 이미 {self._current_strategy_name} "
                        f"보유/대기중 (state={existing.state.name}) — 동일 전략 중복 방지"
                    )
                    return None
```
(핵심: `strategy=self._current_strategy_name`로 조회 → 다른 전략 보유는 가드에 안 걸림.)

- [ ] **Step 4: GREEN 확인 + 회귀**
```bash
python -m pytest tests/test_strategy_independent_positions.py -q
python -m pytest tests/ -q -k "context or buy"
```

- [ ] **Step 5: 커밋**
```bash
git add core/trading_context.py tests/test_strategy_independent_positions.py
git commit -m "feat(buy): 소유권 가드를 동일전략 중복만 차단으로 완화 — 다전략 동일종목 허용 (Phase2)"
```

---

## Phase 3 — 체결 콜백 & 복원 라우팅

### Task 3.1: state_restorer 복합키 복원

**Files:**
- Modify: `bot/state_restorer.py` (홀딩 복원 루프, ~line 375-412)
- Test: `tests/test_state_restorer_multistrategy.py` (생성)

- [ ] **Step 1: RED — DB에 동일종목 2전략 보유가 있을 때 둘 다 복원되는지**

DB holdings 목록에 `{stock_code:"010170", strategy:"minervini"}`, `{stock_code:"010170", strategy:"rs_leader"}` 2건이 있을 때, 복원 후 `get_stocks_by_state(POSITIONED)`에 010170이 owner별로 2건 존재하는지 검증(가능한 한 실제 코드, DB는 fixture/mock).

- [ ] **Step 2: RED 확인** — 현재는 단일키라 1건만 살아남음 → FAIL.

- [ ] **Step 3: GREEN — 복원 시 owner 전달**

복원 루프에서 `TradingStock` 생성 시 `owner_strategy_name=db_strategy`를 먼저 세팅하고 `register_stock`(복합키) 호출. `get_trading_stock(stock_code)` 조회를 `get_trading_stock(stock_code, strategy=db_strategy)`로 변경(line ~406).

- [ ] **Step 4: GREEN 확인 + 회귀**
```bash
python -m pytest tests/test_state_restorer_multistrategy.py -q
python -m pytest tests/ -q -k "restor"
```

- [ ] **Step 5: 커밋**
```bash
git add bot/state_restorer.py tests/test_state_restorer_multistrategy.py
git commit -m "feat(restore): 오버나잇 복원을 (전략,종목) 복합키로 — 다전략 동일종목 보존 (Phase3)"
```

### Task 3.2: 체결 콜백 다전략 통지 검증

**Files:**
- Inspect/Modify: `core/trading/order_completion_handler.py:100-154` (order_id 매칭), `set_strategy`(line 46)
- Test: `tests/test_order_completion_multistrategy.py` (생성)

- [ ] **Step 1: RED — order_id가 다른 두 포지션의 체결이 각각 올바른 전략 포지션으로 귀속되는지**

동일 종목 010170을 minervini(order_id=A), rs_leader(order_id=B)가 보유. 체결 보고가 order_id=B로 올 때 rs_leader의 TradingStock만 POSITIONED→상태전이 되는지 검증.

- [ ] **Step 2: RED 확인** — 매칭 루프가 `stock_code`만 비교하면 첫 매치(minervini)가 잘못 전이될 수 있음 → FAIL. (line 107-108은 order_id도 비교하므로 통과할 수도 있음 → 통과 시 이 태스크는 "확인됨"으로 종료하고 회귀 테스트만 남긴다.)

- [ ] **Step 3: GREEN — 필요 시 매칭을 order_id 우선으로 정렬 + change_stock_state에 owner 전달**

매칭 루프가 `.values()` 순회 시 `order.order_id == ts.current_order_id`를 1차 키로 하고, 상태전이 호출에 `strategy=ts.owner_strategy_name` 명시.

- [ ] **Step 4: GREEN 확인 + 회귀**
```bash
python -m pytest tests/test_order_completion_multistrategy.py -q
python -m pytest tests/ -q -k "completion or order"
```

- [ ] **Step 5: 커밋**
```bash
git add core/trading/order_completion_handler.py tests/test_order_completion_multistrategy.py
git commit -m "feat(fill): 체결 콜백 order_id→owner 전략 귀속 보장 (Phase3)"
```

---

## Phase 4 — Equity 정합 & 라이브 검증

### Task 4.1: paper_strategy_equity 다전략 동일종목 정합 확인

**Files:**
- Inspect: `scripts/paper_strategy_equity.py`
- Test: 기존 `tests/`의 equity 관련 테스트

- [ ] **Step 1: 리플레이가 (strategy, stock_code)로 포지션을 구분하는지 코드 확인**

`paper_strategy_equity.py`는 이미 strategy별 그룹 리플레이(메모리 기록). 동일종목 다전략 케이스에서 각 전략 포지션이 독립 평가되는지 단위 테스트로 못박는다. 안 되면 그룹키에 stock_code까지 포함.

- [ ] **Step 2: 백필 재실행 + 교차검증 차이 확인**
```bash
python scripts/paper_strategy_equity.py 2>&1 | tail -20
```
Expected: 전략별 리더보드 정상 출력, 교차검증 차이가 기존 수준 유지(악화 없음).

- [ ] **Step 3: 커밋(필요 시)**
```bash
git add scripts/paper_strategy_equity.py tests/...
git commit -m "test(equity): 다전략 동일종목 독립 평가 회귀 고정 (Phase4)"
```

### Task 4.2: 전체 회귀 + 라이브 e2e + 봇 재시작 준비

- [ ] **Step 1: 전체 스위트**
```bash
python -m pytest tests/ -q 2>&1 | tail -15
```
Expected: 사전존재 32 외 순회귀 0.

- [ ] **Step 2: 라이브 e2e 드라이런** (장 종료 후, DB 연결 상태)
실제 후보→매수→상태저장→복원 경로에서 동일종목 다전략 케이스가 정상 동작하는지 dry-run 또는 다음 거래일 관찰 체크리스트 작성:
  - [ ] 후보 단계: 동일종목이 2전략 풀에 모두 존재
  - [ ] 매수: 2전략이 각자 체결, `매수 거부: 동일 전략` 외 거부 없음
  - [ ] EOD: 2전략 포지션 독립 집계, equity 분리
  - [ ] 익일 복원: `전략 원장 재구성 완료` 로그에 동일종목 2건

- [ ] **Step 3: 메모리 업데이트 + 봇 재시작 안내**

`design-2026-06-16-strategy-independent-positions.md`에 구현 완료·커밋 해시 기록. 봇 재시작 시 반영.

---

## Self-Review 체크

- **Spec 커버리지:** §2 레이어①→Phase1, 레이어②→Task2.3, §3 복합키→Task2.1, §4.3 위험지점(체결콜백·복원)→Phase3, equity→Phase4. ✅
- **하위호환:** `get_trading_stock`/`change_stock_state` 등에 `strategy` 기본값 None + 단일매칭 폴백 → 103 호출부 중 충돌 없는 곳은 무수정. Task2.2가 모호조회 잔여만 처리. ✅
- **타입 일관성:** `_key(owner, stock_code) -> Tuple[str,str]`, `strategy: Optional[str]=None` 시그니처 전 메서드 통일. ✅
- **미해결 결정:** 실전 단일풀 회귀(§6.1) — 본 plan은 페이퍼 기준. 실전 전환 시 dedup 재도입을 플래그로 가드하는 별도 작업 필요(범위 외, spec §6에 기록).

---

## Execution Handoff

구현은 **subagent-driven-development**(태스크별 신규 subagent + 2단계 리뷰) 권장. Phase 단위로 리뷰 체크포인트.

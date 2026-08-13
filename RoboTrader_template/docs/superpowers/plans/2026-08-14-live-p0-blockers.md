# 실매매 P0 blocker 4건 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실전 전환을 막는 확증 결함 4건(D1 총자금 상수·D2 복원 불능·D3 EOD 매도실패 무음·D4 크래시 복구 공백)을 fail-closed 로 고치고, mock 이 브로커 계약을 발명하지 못하게 실계약 fixture 로 못박는다.

**Architecture:** 수정 축은 **A안(호출부 수정)** — 브로커·KIS 파싱 계층은 불변이고, 틀린 키를 기대한 호출부 두 곳을 실존 계약(`total_balance` 키·`get_holdings()`)에 맞춘다. 모든 실전 기동 실패는 전용 예외 `LiveStartupAbort` 하나로 수렴해 「조용히 계속하는 경로」를 없앤다.

**Tech Stack:** Python 3.8+ · pytest · `unittest.mock` · PostgreSQL 16(`kis_template`, port 5433)

**Spec:** `docs/superpowers/specs/2026-08-14-live-p0-blockers-design.md` (커밋 `dc68cb6`, 흐름도 정정 1건은 이 계획과 함께 커밋)

## Global Constraints

- **페이퍼 매매 동작 0줄.** D1·D2·D3 은 실전 분기(`paper_trading=False`)에만, D4(a-c) 는 실전 전용 신설. 유일한 페이퍼 영향 = D4(d) 종료 경로 정상화(스펙 §5 명시).
- 🔴 **라이브 트리에서 테스트 금지.** 워크트리에서 작업(`superpowers:using-git-worktrees`). 전체 스위트는 repo 루트 + VS 번들 Python 에서만 완주 → 메모리 [[reference-pytest-full-suite-invocation]].
- **실패를 조용히 삼키지 말 것.** 실전 기동 경로의 조회 실패·불일치는 전부 `LiveStartupAbort` — 기본값 폴백·경고 후 계속 금지. 단 **빈 결과 ≠ 실패**(스펙 §2 D2(a) 판별 규칙).
- **브로커·KIS 파싱 계층 불변**(결정 7). 예외: `KISBroker.get_pending_orders` **신설**(기존 메서드 수정 아님). 신설 메서드는 실패 `None` / 없음 `[]` 를 구분한다(`get_holdings` 의 오류 삼킴 교훈).
- **테스트 mock 은 Task 1 의 실계약 fixture(`tests/broker_contract.py`)에서만 파생.** 손으로 dict 를 만들지 말 것 — 이번 결함 4건 전부 「mock 이 계약을 발명」해 숨었다.
- **로거** `utils.logger.setup_logger(__name__)` · **시간** `utils.korean_time.now_kst()`.
- 커밋 메시지는 이 레포 관례(한국어 서술형 제목)를 따르고 끝에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` 트레일러.

## File Structure

| 파일 | 변경 | 책임 |
|---|---|---|
| `tests/broker_contract.py` | 신설 | 실계약 fixture(계좌요약 키 9종·보유항목 키 8종) — 모든 mock 의 유일한 출처 |
| `tests/test_live_broker_contract.py` | 신설 | 실브로커 반환 키 = fixture 키 동일성 고정 |
| `utils/exceptions.py` | 신설 | `LiveStartupAbort` |
| `core/models.py` | +2줄 | `TradingConfig.real_total_funds_cap` |
| `bot/initializer.py` | 실전 분기 교체 + 1줄 | D1 총자금 min(cap, 총평가) · D4(d) disconnect |
| `bot/state_restorer.py` | 실전 복원부 | D2 get_holdings 결선·합산·fail-closed 대사 · D4(b,c) 기동 취소·SELL_PENDING 폴백 제거 |
| `config/constants.py` | −1줄 | `STATE_RESTORATION_AUTO_RECONCILE` 소멸 |
| `framework/broker.py` | +1 메서드 | `get_pending_orders()` |
| `bot/liquidation_handler.py` | 2곳 | D3 실매도 반환값 검사 |
| `main.py` | +6줄 | `LiveStartupAbort` 최상위 처리(텔레그램 best-effort + exit) |
| `tests/test_live_p0_*.py` | 신설 4파일 | 스펙 §4 테스트 16개 |
| `tests/test_state_restorer_live_real_table.py` | 수정 | 은폐 mock → 실계약 fixture (스펙 테스트 13) |

---

## Task 1: 실계약 fixture + contract test (스펙 테스트 12)

**Files:**
- Create: `tests/broker_contract.py`
- Create: `tests/test_live_broker_contract.py`

**Interfaces:**
- Consumes: `framework/broker.py:280-290`(요약 dict 리터럴) · `api/kis_market_api.py:711-720`(보유항목 dict 리터럴)
- Produces: `ACCOUNT_BALANCE_KEYS: frozenset` · `HOLDING_ITEM_KEYS: frozenset` · `make_account_balance(**overrides) -> dict` · `make_holding(**overrides) -> dict` — **이후 모든 Task 의 테스트가 이것만 쓴다**

- [ ] **Step 1: fixture 모듈 작성**

```python
# tests/broker_contract.py
"""KISBroker 실계약 fixture — 모든 브로커 mock 의 유일한 출처.

2026-08-14 P0 스펙: 결함 4건 전부 「mock 이 실브로커에 없는 키(positions,
account_balance)를 발명」해 테스트가 green 인 채 숨었다. 이 모듈의 키 집합은
test_live_broker_contract.py 가 실브로커 반환과 동일함을 고정한다.
손으로 브로커 dict 를 만들지 말 것.
"""
from typing import Dict, List

# framework/broker.py get_account_balance() 반환 dict 의 전체 키 (:280-290)
ACCOUNT_BALANCE_KEYS = frozenset({
    'total_balance', 'available_cash', 'invested_amount',
    'total_profit_loss', 'total_profit_loss_rate', 'deposit_total',
    'next_day_amount', 'total_stocks', 'inquiry_time',
})

# api/kis_market_api.py get_account_balance()['stocks'] 항목 키 (:711-720)
# = KISBroker.get_holdings() 항목 키 (get_existing_holdings 가 그대로 반환)
HOLDING_ITEM_KEYS = frozenset({
    'stock_code', 'stock_name', 'quantity', 'avg_price',
    'current_price', 'eval_amount', 'profit_loss', 'profit_loss_rate',
})


def make_account_balance(**overrides) -> Dict:
    base = {
        'total_balance': 5_000_000,
        'available_cash': 4_000_000,
        'invested_amount': 1_000_000,
        'total_profit_loss': 0,
        'total_profit_loss_rate': 0.0,
        'deposit_total': 4_000_000,
        'next_day_amount': 4_000_000,
        'total_stocks': 0,
        'inquiry_time': '2026-08-14 08:00:00',
    }
    unknown = set(overrides) - ACCOUNT_BALANCE_KEYS
    if unknown:
        raise KeyError(f"실계약에 없는 키: {unknown}")
    base.update(overrides)
    return base


def make_holding(**overrides) -> Dict:
    base = {
        'stock_code': '005930', 'stock_name': '삼성전자',
        'quantity': 10, 'avg_price': 100_000.0,
        'current_price': 101_000.0, 'eval_amount': 1_010_000,
        'profit_loss': 10_000, 'profit_loss_rate': 1.0,
    }
    unknown = set(overrides) - HOLDING_ITEM_KEYS
    if unknown:
        raise KeyError(f"실계약에 없는 키: {unknown}")
    base.update(overrides)
    return base
```

- [ ] **Step 2: contract test 작성 (red 확인 대상은 없음 — 계약 «고정»이 목적)**

```python
# tests/test_live_broker_contract.py
"""실브로커 반환 키 = fixture 키 동일성 고정 (스펙 §4 테스트 12)."""
from unittest.mock import Mock

from framework.broker import KISBroker
from tests.broker_contract import (
    ACCOUNT_BALANCE_KEYS, HOLDING_ITEM_KEYS,
    make_account_balance, make_holding,
)


def _bare_broker(api_mock):
    """생성자 부작용 없이 실메서드만 실행하는 KISBroker."""
    b = object.__new__(KISBroker)
    b._connected = True
    b.logger = Mock()
    b._kis_market_api = api_mock
    return b


def _api_level_balance(stocks):
    # api/kis_market_api.get_account_balance() 가 실제로 만드는 형태 (:661-733)
    return {
        'total_stocks': len(stocks), 'total_value': 5_000_000,
        'total_profit_loss': 0, 'total_profit_loss_rate': 0.0,
        'available_amount': 4_000_000, 'cash_balance': 4_000_000,
        'purchase_amount': 1_000_000, 'next_day_amount': 4_000_000,
        'deposit_total': 4_000_000, 'stocks': stocks,
        'inquiry_time': '2026-08-14 08:00:00',
    }


class TestAccountBalanceContract:
    def test_real_broker_keys_equal_fixture_keys(self):
        api = Mock()
        api.get_account_balance.return_value = _api_level_balance([make_holding()])
        result = _bare_broker(api).get_account_balance()
        assert set(result.keys()) == ACCOUNT_BALANCE_KEYS

    def test_invented_keys_are_absent(self):
        """이번 사고의 발명 키 2종이 실계약에 없음을 «양방향»으로 고정."""
        api = Mock()
        api.get_account_balance.return_value = _api_level_balance([])
        result = _bare_broker(api).get_account_balance()
        assert 'positions' not in result
        assert 'account_balance' not in result

    def test_fixture_is_self_consistent(self):
        assert set(make_account_balance().keys()) == ACCOUNT_BALANCE_KEYS


class TestHoldingsContract:
    def test_get_holdings_item_keys_equal_fixture_keys(self):
        api = Mock()
        api.get_existing_holdings.return_value = [make_holding()]
        result = _bare_broker(api).get_holdings()
        assert len(result) == 1
        assert set(result[0].keys()) == HOLDING_ITEM_KEYS

    def test_fixture_is_self_consistent(self):
        assert set(make_holding().keys()) == HOLDING_ITEM_KEYS
```

- [ ] **Step 3: 실행 — 5개 전부 PASS 확인**

Run: `pytest tests/test_live_broker_contract.py -v`
Expected: 5 passed. (실패하면 fixture 키를 코드에 맞춘다 — **코드를 fixture 에 맞추지 말 것**, 브로커 불변이 결정 7 이다.)

⚠️ `_bare_broker` 가 동작하지 않으면(예: `get_account_balance` 가 `self._kis_market_api` 외의 속성을 요구) `framework/broker.py:256-294` 를 읽고 요구 속성만 추가로 세팅한다. `KISBroker()` 정식 생성은 인증을 시도할 수 있으므로 금지.

- [ ] **Step 4: Commit**

```bash
git add tests/broker_contract.py tests/test_live_broker_contract.py
git commit -m "test(contract): 브로커 실계약 fixture — mock 이 계약을 발명하지 못하게 키 집합을 고정한다"
```

---

## Task 2: `LiveStartupAbort` + main 최상위 처리

**Files:**
- Create: `utils/exceptions.py`
- Modify: `main.py:688-692`
- Test: `tests/test_live_p0_startup_abort.py`

**Interfaces:**
- Produces: `LiveStartupAbort(reason: str, details: str = "")` — 이후 모든 Task 의 실전 기동 실패가 이 예외를 raise. `str(exc)` = `"{reason} | {details}"`.

- [ ] **Step 1: 예외 정의**

```python
# utils/exceptions.py
"""프로젝트 공용 예외.

LiveStartupAbort: 실전 기동을 «중단»해야 하는 상태(잔고 조회 실패·계좌-DB
불일치·미체결 취소 실패 등). 2026-08-14 P0 스펙 결정 5·6 — 실전 기동
경로에는 「경고 후 계속」이 존재하지 않는다. 페이퍼 경로에서는 raise 금지.
"""


class LiveStartupAbort(Exception):
    def __init__(self, reason: str, details: str = ""):
        self.reason = reason
        self.details = details
        super().__init__(f"{reason} | {details}" if details else reason)
```

- [ ] **Step 2: 실패하는 테스트 작성**

```python
# tests/test_live_p0_startup_abort.py
import pytest

from utils.exceptions import LiveStartupAbort


def test_abort_carries_reason_and_details():
    exc = LiveStartupAbort("잔고 조회 실패", "get_account_balance()={}")
    assert exc.reason == "잔고 조회 실패"
    assert "잔고 조회 실패" in str(exc) and "get_account_balance" in str(exc)


def test_abort_is_not_swallowed_by_generic_handler_contract():
    """LiveStartupAbort 는 Exception 파생 — main 최상위 except 가 잡되
    전용 분기가 먼저 잡아 exit code 2 로 구분한다(아래 main.py 수정)."""
    assert issubclass(LiveStartupAbort, Exception)
```

- [ ] **Step 3: 실행 — import 실패로 red 확인 후 Step 1 파일 저장, PASS 확인**

Run: `pytest tests/test_live_p0_startup_abort.py -v`
Expected: (파일 저장 전) FAIL `ModuleNotFoundError` → (저장 후) 2 passed

- [ ] **Step 4: main.py 결선**

`main.py:690-692` 를 다음으로 교체 (텔레그램은 best-effort — D1 시점엔 텔레그램이 아직 미초기화일 수 있다, `initializer.py:586` 이 `:593` 보다 먼저):

```python
    # 시스템 초기화 — LiveStartupAbort 는 실전 기동 중단(스펙 2026-08-14 P0)
    try:
        if not await bot.initialize():
            sys.exit(1)
    except LiveStartupAbort as e:
        logging.getLogger(__name__).critical(f"🚨 실전 기동 중단: {e}")
        try:
            if getattr(bot, 'telegram', None):
                await bot.telegram.send_notification(f"🚨 실전 기동 중단\n{e}")
        except Exception:
            pass  # 경보 실패가 exit 를 막지 않는다
        sys.exit(2)
```

파일 상단 import 에 `from utils.exceptions import LiveStartupAbort` 추가.

- [ ] **Step 5: Commit**

```bash
git add utils/exceptions.py main.py tests/test_live_p0_startup_abort.py
git commit -m "feat(live): LiveStartupAbort — 실전 기동 실패는 조용히 계속하지 않고 경보 후 종료한다"
```

---

## Task 3: D1 — 총자금 `min(설정 상한, 실계좌 총평가)` (스펙 테스트 1·2·3)

**Files:**
- Modify: `core/models.py:373-374`(필드) · `:410-411`(from_json)
- Modify: `bot/initializer.py:673-685`
- Test: `tests/test_live_p0_fund_init.py`

**Interfaces:**
- Consumes: Task 1 `make_account_balance` · Task 2 `LiveStartupAbort`
- Produces: `TradingConfig.real_total_funds_cap: Optional[float]`(기본 None) — Task 9 진입점 테스트가 사용

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_live_p0_fund_init.py
"""D1: 실전 총자금 = min(real_total_funds_cap, 실계좌 total_balance). 무언 폴백 금지."""
import asyncio
from unittest.mock import Mock

import pytest

from tests.broker_contract import make_account_balance
from utils.exceptions import LiveStartupAbort
from bot.initializer import BotInitializer


def _init_with(cap, balance_return):
    bot = Mock()
    bot.config.real_total_funds_cap = cap
    bot.config.paper_trading = False
    bot.broker.get_account_balance.return_value = balance_return
    init = BotInitializer(bot)
    return bot, init


def _run(init):
    asyncio.run(init._initialize_fund_manager())


class TestRealFundInit:
    def test_uses_total_balance_key_not_invented_account_balance(self):
        """red 재현: 현행은 없는 키 account_balance 를 읽어 상수 1천만원."""
        bot, init = _init_with(cap=100_000_000,
                               balance_return=make_account_balance(total_balance=5_000_000))
        _run(init)
        bot.fund_manager.update_total_funds.assert_called_once_with(5_000_000.0)

    def test_cap_wins_when_smaller(self):
        bot, init = _init_with(cap=3_000_000,
                               balance_return=make_account_balance(total_balance=5_000_000))
        _run(init)
        bot.fund_manager.update_total_funds.assert_called_once_with(3_000_000.0)

    @pytest.mark.parametrize("bad_balance", [{}, make_account_balance(total_balance=0)])
    def test_query_failure_or_zero_aborts(self, bad_balance):
        """red 재현: 현행은 조용히 1천만원 폴백."""
        bot, init = _init_with(cap=3_000_000, balance_return=bad_balance)
        with pytest.raises(LiveStartupAbort):
            _run(init)
        bot.fund_manager.update_total_funds.assert_not_called()

    @pytest.mark.parametrize("bad_cap", [None, 0, -1])
    def test_missing_cap_aborts(self, bad_cap):
        bot, init = _init_with(cap=bad_cap,
                               balance_return=make_account_balance(total_balance=5_000_000))
        with pytest.raises(LiveStartupAbort):
            _run(init)


def test_paper_mode_unchanged():
    """라이브 불변: 페이퍼 분기는 이 Task 가 건드리지 않는다."""
    bot = Mock()
    bot.config.paper_trading = True
    init = BotInitializer(bot)
    asyncio.run(init._initialize_fund_manager())
    bot.broker.get_account_balance.assert_not_called()
```

⚠️ `BotInitializer` 생성자·`_initialize_fund_manager` 의 페이퍼 분기 조건은 `bot/initializer.py:659-672` 를 읽고 맞춘다(페이퍼 판별이 `config.paper_trading` 직접이 아니면 그 실제 조건으로 Mock 세팅).

- [ ] **Step 2: 실행 — red 확인**

Run: `pytest tests/test_live_p0_fund_init.py -v`
Expected: `test_uses_total_balance...`·`test_query_failure...` FAIL (현행: `update_total_funds(10000000)` 호출됨)

- [ ] **Step 3: 구현**

`core/models.py` — `:374` 뒤에 필드, `:411` 뒤에 파싱:

```python
    real_total_funds_cap: Optional[float] = None  # 실전 총자금 상한(원). 실전 모드 필수 — 미설정 시 기동 중단(2026-08-14 P0)
```
```python
            real_total_funds_cap=json_data.get('real_total_funds_cap', None),
```

`bot/initializer.py:673-685` else(실전) 분기 교체:

```python
        else:
            from utils.exceptions import LiveStartupAbort
            cap = getattr(self.bot.config, 'real_total_funds_cap', None)
            if cap is None or float(cap) <= 0:
                raise LiveStartupAbort(
                    "실전 총자금 상한 미설정",
                    "trading_config.json 에 real_total_funds_cap(원)을 설정해야 실전 기동이 가능합니다")
            balance_info = self.bot.broker.get_account_balance()
            if isinstance(balance_info, dict):
                total_eval = float(balance_info.get('total_balance', 0) or 0)
            else:
                # KISAPIManager 경로: AccountInfo.account_balance (kis_api_manager.py:222)
                total_eval = float(getattr(balance_info, 'account_balance', 0) or 0)
            if total_eval <= 0:
                raise LiveStartupAbort(
                    "실계좌 잔고 조회 실패 또는 0원",
                    f"get_account_balance() 반환 요약={str(balance_info)[:200]}")
            total_funds = float(min(float(cap), total_eval))
            self.bot.fund_manager.update_total_funds(total_funds)
            self.logger.info(
                f"자금 관리자 초기화 완료(실전): min(상한 {float(cap):,.0f}, 총평가 {total_eval:,.0f}) = {total_funds:,.0f}원")
```

- [ ] **Step 4: 실행 — 전부 PASS + Task 1·2 테스트 재확인**

Run: `pytest tests/test_live_p0_fund_init.py tests/test_live_broker_contract.py tests/test_live_p0_startup_abort.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add core/models.py bot/initializer.py tests/test_live_p0_fund_init.py
git commit -m "fix(live): 실전 총자금이 상수 1천만원이었다 — 없는 키 대신 total_balance 를 읽고 min(상한,총평가)로"
```

---

## Task 4: D2(a)(c) — 보유 조회 결선 + 분할매수 합산 + 은폐 mock 교정 (스펙 테스트 4·6·7·7b·13)

**Files:**
- Modify: `bot/state_restorer.py:780-790`(조회) · `:796-819`(합산)
- Modify: `tests/test_state_restorer_live_real_table.py:129-136`
- Test: `tests/test_live_p0_restore.py`

**Interfaces:**
- Consumes: Task 1 fixture · Task 2 `LiveStartupAbort`
- Produces: 실전 복원이 `broker.get_holdings()` 사용 — Task 9 진입점 테스트가 호출 순서를 단언

- [ ] **Step 1: 실패하는 테스트 작성**

기존 `tests/test_state_restorer_live_real_table.py` 의 `_make_restorer`·`_wire_trading_manager`·`_holdings_df` 헬퍼를 재사용한다(먼저 그 파일 1-95줄을 읽고 시그니처를 맞출 것).

```python
# tests/test_live_p0_restore.py
"""D2: 실전 복원 — get_holdings 결선·빈/실패 판별·분할매수 합산."""
import asyncio
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

from tests.broker_contract import make_account_balance, make_holding
from utils.exceptions import LiveStartupAbort
from tests.test_state_restorer_live_real_table import (
    _make_restorer, _wire_trading_manager, _holdings_df,
)
from utils.korean_time import now_kst
from datetime import timedelta


def _real_broker_mock(holdings, total_stocks=None):
    broker = Mock()
    n = len(holdings) if total_stocks is None else total_stocks
    broker.get_account_balance.return_value = make_account_balance(total_stocks=n)
    broker.get_holdings.return_value = holdings
    broker.get_pending_orders.return_value = []   # Task 6 전까지는 소비자 없음(무해)
    return broker


def _restorer_with(db, broker, strat):
    r = _make_restorer(db, strategies={'stratA': strat}, paper_trading=False, broker=broker)
    _wire_trading_manager(r)
    r._sync_fund_manager_for_position = Mock(return_value=0.0)
    r._apply_stale_position_check = Mock(return_value=(0.05, 0.03))
    return r


class TestHoldingsWiring:
    def test_restore_uses_get_holdings_and_restores(self):
        """red 재현: 현행은 요약 dict 의 없는 키 positions 를 읽어 0건 복원."""
        buy_time = now_kst() - timedelta(days=20)
        db = Mock()
        db.get_real_open_positions.return_value = _holdings_df(buy_time)
        strat = Mock()
        broker = _real_broker_mock([make_holding()])
        r = _restorer_with(db, broker, strat)
        asyncio.run(r._restore_holdings_from_real_account())
        broker.get_holdings.assert_called()
        strat.sync_positions.assert_called_once()

    def test_summary_says_n_but_list_empty_aborts(self):
        """7b: total_stocks>0 인데 목록 0건 = 조회 실패 (get_holdings 오류 삼킴 대응)."""
        db = Mock(); db.get_real_open_positions.return_value = pd.DataFrame()
        broker = _real_broker_mock([], total_stocks=2)
        r = _restorer_with(db, broker, Mock())
        with pytest.raises(LiveStartupAbort):
            asyncio.run(r._restore_holdings_from_real_account())

    def test_truly_empty_account_starts_normally(self):
        """7: 요약 0 & 목록 0 & DB 0 = 신규 계좌, 정상."""
        db = Mock(); db.get_real_open_positions.return_value = pd.DataFrame()
        broker = _real_broker_mock([])
        r = _restorer_with(db, broker, Mock())
        asyncio.run(r._restore_holdings_from_real_account())  # no raise

    def test_summary_query_failure_aborts_no_db_fallback(self):
        """조회 실패 시 「DB 폴백으로 계속」 제거 확인."""
        db = Mock(); db.get_real_open_positions.return_value = pd.DataFrame()
        broker = Mock(); broker.get_account_balance.return_value = {}
        r = _restorer_with(db, broker, Mock())
        r._restore_holdings_from_db = AsyncMock()
        with pytest.raises(LiveStartupAbort):
            asyncio.run(r._restore_holdings_from_real_account())
        r._restore_holdings_from_db.assert_not_called()


class TestSplitBuyAggregation:
    def test_two_buy_rows_same_code_are_summed(self):
        """6: 분할매수 BUY 2행이 수량 SUM·가중평균으로 합산돼 불일치 오탐 0."""
        buy_time = now_kst() - timedelta(days=5)
        rows = pd.DataFrame([
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 6,
             'buy_price': 100_000.0, 'buy_time': buy_time, 'strategy': 'stratA'},
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 4,
             'buy_price': 110_000.0, 'buy_time': buy_time, 'strategy': 'stratA'},
        ])
        db = Mock(); db.get_real_open_positions.return_value = rows
        strat = Mock()
        broker = _real_broker_mock([make_holding(quantity=10, avg_price=104_000.0)])
        r = _restorer_with(db, broker, strat)
        asyncio.run(r._restore_holdings_from_real_account())  # 수량 10=10 → 불일치 없음 → no raise
        strat.sync_positions.assert_called_once()
```

⚠️ `_holdings_df` 의 실제 컬럼(특히 `buy_price` vs `price`)은 파일 1-95줄에서 확인해 `TestSplitBuyAggregation` 의 DataFrame 컬럼을 **`get_real_open_positions` 실반환 컬럼**(`db/repositories/trading.py:429-466`)과 일치시킨다.

- [ ] **Step 2: 실행 — red 확인**

Run: `pytest tests/test_live_p0_restore.py -v`
Expected: `test_restore_uses_get_holdings...` FAIL(get_holdings 미호출·sync 0회), `test_summary_says_n...` FAIL(예외 없이 통과)

- [ ] **Step 3: 구현 — 조회 교체**

`bot/state_restorer.py:779-790` 교체:

```python
            # 1. 실전 잔고 — 요약(총평가·종목수)과 보유 목록을 분리 조회 후 교차검증.
            #    get_holdings() 는 실패를 빈 리스트로 삼키므로(broker.py:313,326)
            #    요약 total_stocks 와 대조해야 「빈 계좌」와 「조회 실패」가 갈린다.
            #    (2026-08-14 P0 — 종전 코드는 요약 dict 의 없는 키 'positions' 를
            #     읽어 실보유가 항상 0건이었다)
            from utils.exceptions import LiveStartupAbort
            account_info = self.broker.get_account_balance()
            if not account_info or not isinstance(account_info, dict):
                raise LiveStartupAbort(
                    "실계좌 요약 조회 실패",
                    f"get_account_balance()={str(account_info)[:200]}")
            summary_stock_count = int(account_info.get('total_stocks', 0) or 0)
            real_holdings = self.broker.get_holdings()
            if summary_stock_count > 0 and not real_holdings:
                raise LiveStartupAbort(
                    "실계좌 보유 목록 조회 실패",
                    f"요약 total_stocks={summary_stock_count} 인데 get_holdings() 0건 — 오류 삼킴 의심")
            logger.info(f"📊 [실전매매] 실제 계좌 보유 종목: {len(real_holdings)}개")
```

종전 `:782-785` 의 `_restore_holdings_from_db()` 폴백 호출은 삭제한다(조회 실패 = 기동 중단).

- [ ] **Step 4: 구현 — 합산**

`:811-819` 의 `db_holdings_dict[row['stock_code']] = {...}` 를 합산으로 교체:

```python
                    code = row['stock_code']
                    if code in db_holdings_dict:
                        # 분할매수 합산: 수량 SUM · 매입가 가중평균.
                        # ORDER BY timestamp DESC 라 첫 행이 최신 — strategy/tp/sl/buy_time 은 최신 행 유지.
                        prev = db_holdings_dict[code]
                        add_qty = int(row['quantity'])
                        new_qty = prev['quantity'] + add_qty
                        if new_qty > 0:
                            prev['buy_price'] = (
                                prev['buy_price'] * prev['quantity']
                                + float(row['buy_price']) * add_qty) / new_qty
                        prev['quantity'] = new_qty
                    else:
                        db_holdings_dict[code] = {
                            'stock_name': row['stock_name'],
                            'quantity': int(row['quantity']),
                            'buy_price': float(row['buy_price']),
                            'buy_time': row.get('buy_time'),
                            'strategy': row.get('strategy', ''),
                            'target_profit_rate': tp_rate,
                            'stop_loss_rate': sl_rate,
                        }
```

- [ ] **Step 5: 은폐 mock 교정 (스펙 테스트 13)**

`tests/test_state_restorer_live_real_table.py:129-136` 을 실계약 fixture 로 교체:

```python
        from tests.broker_contract import make_account_balance, make_holding

        broker = Mock()
        broker.get_account_balance.return_value = make_account_balance(total_stocks=1)
        broker.get_holdings.return_value = [make_holding(
            stock_code='005930', stock_name='삼성전자',
            quantity=10, avg_price=100_000.0,
        )]
        broker.get_pending_orders.return_value = []
```

- [ ] **Step 6: 실행 — 전부 PASS**

Run: `pytest tests/test_live_p0_restore.py tests/test_state_restorer_live_real_table.py -v`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add bot/state_restorer.py tests/test_live_p0_restore.py tests/test_state_restorer_live_real_table.py
git commit -m "fix(live): 실전 복원이 항상 0건이었다 — 없는 키 positions 대신 get_holdings 결선 + 요약 교차검증 + 분할매수 합산"
```

---

## Task 5: D2(b) — fail-closed 대사, 자동 대사 소멸 (스펙 테스트 5)

**Files:**
- Modify: `bot/state_restorer.py:823-824`(호출부) · `:977-1037`(_detect_holdings_mismatch) · `:1039-1150`(_reconcile_mismatches 삭제) · `:16`(import)
- Modify: `config/constants.py:168`(삭제)
- Test: `tests/test_live_p0_restore.py` 에 클래스 추가

**Interfaces:**
- Consumes: Task 4 의 복원 경로
- Produces: `_detect_holdings_mismatch(...) -> List[str]` (종전 None) — 불일치 메시지 목록 반환, **호출부가 raise**

- [ ] **Step 1: 실패하는 테스트 추가**

```python
class TestFailClosedMismatch:
    def test_mismatch_aborts_startup(self):
        """5: 불일치 1건이면 LiveStartupAbort. 자동 대사(0원 INSERT)는 코드째 소멸."""
        buy_time = now_kst() - timedelta(days=5)
        db = Mock()
        db.get_real_open_positions.return_value = _holdings_df(buy_time)  # DB 에 1종목
        broker = _real_broker_mock([])                                    # 실계좌 0종목
        r = _restorer_with(db, broker, Mock())
        with pytest.raises(LiveStartupAbort):
            asyncio.run(r._restore_holdings_from_real_account())
        db.save_real_sell.assert_not_called()   # 0원 매도 INSERT 불가
        db.save_real_buy.assert_not_called()

    def test_reconcile_machinery_is_gone(self):
        from bot import state_restorer as mod
        import config.constants as consts
        r = _restorer_with(Mock(), _real_broker_mock([]), Mock())
        assert not hasattr(r, '_reconcile_mismatches')
        assert not hasattr(consts, 'STATE_RESTORATION_AUTO_RECONCILE')
```

- [ ] **Step 2: 실행 — red 확인** (`pytest tests/test_live_p0_restore.py::TestFailClosedMismatch -v` → FAIL)

- [ ] **Step 3: 구현**

`_detect_holdings_mismatch`: 시그니처를 `-> List[str]` 로. 불일치 수집(`:980-1014`)은 유지, `:1016-1037` 을 다음으로 교체 — **자동 보정·예외 삼킴 제거**:

```python
            if mismatches:
                logger.warning(f"🚨 [실전매매] 계좌-DB 불일치 감지: {len(mismatches)}건")
                for m in mismatches:
                    logger.warning(m)
                if self.telegram:
                    alert_msg = f"🚨 계좌-DB 불일치 {len(mismatches)}건 — 실전 기동 중단\n\n"
                    for m in mismatches[:10]:
                        alert_msg += f"• {m}\n"
                    if len(mismatches) > 10:
                        alert_msg += f"... 외 {len(mismatches)-10}건"
                    await self.telegram.send_notification(alert_msg)
            else:
                logger.info("✅ [실전매매] 계좌-DB 보유 종목 일치 확인")
            return mismatches
```

함수 전체를 감싸던 `try/except`(`:979`·`:1036-1037`)를 제거한다(대사 자체의 예외도 위로 전파 — 조용한 계속 금지). `reconcile_tasks` 수집 코드와 `_reconcile_mismatches` 함수 본문(`:1039-1150`), `config/constants.py:168`, `state_restorer.py:16` 의 import 를 삭제.

호출부 `:823-824` 교체:

```python
            # 3. 계좌-DB 대사 — 불일치는 기동 중단(fail-closed, 2026-08-14 P0 결정 5)
            mismatches = await self._detect_holdings_mismatch(real_holdings, db_holdings_dict)
            if mismatches:
                raise LiveStartupAbort(
                    f"계좌-DB 불일치 {len(mismatches)}건 — 수동 확인 후 재기동 필요",
                    " / ".join(mismatches[:5]))
```

- [ ] **Step 4: 실행 — PASS + grep 소멸 확인**

Run: `pytest tests/test_live_p0_restore.py -v` → all passed
Run: `grep -rn "STATE_RESTORATION_AUTO_RECONCILE\|_reconcile_mismatches" --include="*.py" .` (연구 디렉토리 제외) → **0건**

- [ ] **Step 5: Commit**

```bash
git add bot/state_restorer.py config/constants.py tests/test_live_p0_restore.py
git commit -m "fix(live): 불일치는 경고가 아니라 기동 중단이다 — 0원 매도 INSERT 자동 대사를 코드째 없앤다"
```

---

## Task 6: D4(a,b,c) — `get_pending_orders` 신설 + 기동 시 전량 취소 (스펙 테스트 9·10)

**Files:**
- Modify: `framework/broker.py`(get_order_status 뒤에 메서드 추가)
- Modify: `bot/state_restorer.py:826-841`(SELL_PENDING 폴백 → 취소 단계) + `:913-919` 부근(pending_sell_codes 소비처 제거)
- Test: `tests/test_live_p0_pending_orders.py`

**Interfaces:**
- Consumes: `api/kis_order_api.get_inquire_psbl_rvsecncl_lst()`(`kis_order_api.py:168-213`, DataFrame·페이징 내장) · `KISBroker.cancel_order(order_id, stock_code)`(`broker.py:660-753`, `{'success': bool, ...}` 반환)
- Produces: `KISBroker.get_pending_orders() -> Optional[List[dict]]` — **실패 `None` / 없음 `[]` 구분.** 항목은 KIS 원컬럼 dict(`odno` 주문번호·`pdno` 종목코드·`sll_buy_dvsn_cd` 01매도/02매수 등). `StateRestorer._cancel_all_pending_orders_on_startup()`.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_live_p0_pending_orders.py
"""D4(a,b): 기동 시 미체결 전량 취소 — 전날/크래시 잔존 주문의 고아·중복매도 차단."""
import asyncio
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from framework.broker import KISBroker
from utils.exceptions import LiveStartupAbort


def _bare_broker():
    b = object.__new__(KISBroker)
    b._connected = True
    b.logger = Mock()
    return b


class TestGetPendingOrders:
    def test_returns_records_list(self):
        df = pd.DataFrame([{'odno': '0001', 'pdno': '005930', 'sll_buy_dvsn_cd': '02'}])
        with patch('api.kis_order_api.get_inquire_psbl_rvsecncl_lst', return_value=df):
            result = _bare_broker().get_pending_orders()
        assert result == [{'odno': '0001', 'pdno': '005930', 'sll_buy_dvsn_cd': '02'}]

    def test_failure_is_none_and_empty_is_list(self):
        """실패 None / 없음 [] 구분 — get_holdings 오류 삼킴의 교훈."""
        with patch('api.kis_order_api.get_inquire_psbl_rvsecncl_lst', return_value=None):
            assert _bare_broker().get_pending_orders() is None
        with patch('api.kis_order_api.get_inquire_psbl_rvsecncl_lst', return_value=pd.DataFrame()):
            assert _bare_broker().get_pending_orders() == []


class TestStartupCancelAll:
    def _restorer(self, broker):
        from tests.test_live_p0_restore import _restorer_with
        from unittest.mock import Mock as M
        db = M(); db.get_real_open_positions.return_value = pd.DataFrame()
        return _restorer_with(db, broker, M())

    def test_cancels_all_then_proceeds(self):
        from tests.broker_contract import make_account_balance
        broker = Mock()
        broker.get_account_balance.return_value = make_account_balance()
        broker.get_holdings.return_value = []
        broker.get_pending_orders.side_effect = [
            [{'odno': '0001', 'pdno': '005930', 'sll_buy_dvsn_cd': '02'}],  # 발견
            [],                                                              # 취소 후 재확인
        ]
        broker.cancel_order.return_value = {'success': True}
        r = self._restorer(broker)
        asyncio.run(r._restore_holdings_from_real_account())
        broker.cancel_order.assert_called_once_with('0001', '005930')

    def test_cancel_failure_aborts(self):
        broker = Mock()
        broker.get_pending_orders.return_value = [{'odno': '0001', 'pdno': '005930', 'sll_buy_dvsn_cd': '01'}]
        broker.cancel_order.return_value = {'success': False, 'message': 'rejected'}
        r = self._restorer(broker)
        with pytest.raises(LiveStartupAbort):
            asyncio.run(r._restore_holdings_from_real_account())

    def test_query_failure_aborts(self):
        broker = Mock()
        broker.get_pending_orders.return_value = None
        r = self._restorer(broker)
        with pytest.raises(LiveStartupAbort):
            asyncio.run(r._restore_holdings_from_real_account())
```

- [ ] **Step 2: 실행 — red 확인** (`get_pending_orders` AttributeError / 취소 단계 부재)

- [ ] **Step 3: 구현 — 브로커 메서드**

`framework/broker.py` `get_order_status` 뒤에:

```python
    def get_pending_orders(self) -> Optional[List[dict]]:
        """미체결(정정취소가능) 주문 전량 조회.

        Returns:
            None  = 조회 실패 (호출자가 구분해야 한다 — 빈 리스트로 뭉개지 말 것)
            []    = 미체결 없음
            [dict]= KIS 원컬럼 그대로 (odno 주문번호 · pdno 종목코드 ·
                    sll_buy_dvsn_cd 01매도/02매수 등, TTTC8036R)
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return None
        try:
            from api import kis_order_api
            df = kis_order_api.get_inquire_psbl_rvsecncl_lst()
            if df is None:
                return None
            if df.empty:
                return []
            return df.to_dict('records')
        except Exception as e:
            self.logger.error(f"Error getting pending orders: {e}")
            return None
```

- [ ] **Step 4: 구현 — 기동 취소 단계**

두 동작을 분리해서 한다: ①`:826-841`(SELL_PENDING 폴백 블록)은 **삭제**. ②아래 호출을
`_restore_holdings_from_real_account` 의 **가장 앞**(Task 4 Step 3 에서 넣은 잔고 요약 조회 블록 «앞»)에 **삽입**:

```python
            # 0. 기동 시 미체결 전량 취소 (2026-08-14 P0 결정 6) — 취소가 잔고
            #    조회보다 먼저여야 부분체결분이 확정 반영된 잔고로 복원한다.
            #    취소 후 종전 SELL_PENDING 복원은 불필요(항상 미체결 0 에서 시작).
            await self._cancel_all_pending_orders_on_startup()
```

같은 파일에 메서드 신설 + 취소 발생 시 잔고 재조회:

```python
    async def _cancel_all_pending_orders_on_startup(self) -> bool:
        """실전 기동 시 미체결 전량 취소. 취소가 1건 이상이면 True(잔고 재조회 필요)."""
        from utils.exceptions import LiveStartupAbort
        pending = self.broker.get_pending_orders()
        if pending is None:
            raise LiveStartupAbort("미체결 주문 조회 실패", "get_pending_orders() = None")
        if not pending:
            logger.info("✅ [실전매매] 미체결 주문 없음")
            return False
        logger.warning(f"⚠️ [실전매매] 미체결 {len(pending)}건 발견 — 전량 취소 후 기동")
        for po in pending:
            odno = str(po.get('odno', ''))
            code = str(po.get('pdno', ''))
            result = self.broker.cancel_order(odno, code)
            if not result.get('success'):
                raise LiveStartupAbort(
                    f"미체결 취소 실패: {code} 주문 {odno}",
                    str(result.get('message', '')))
            logger.info(f"🧹 [실전매매] 미체결 취소: {code} 주문 {odno}")
        remain = self.broker.get_pending_orders()
        if remain is None or remain:
            raise LiveStartupAbort(
                "취소 후 미체결 잔존 확인 실패",
                f"재조회 결과={('실패' if remain is None else f'{len(remain)}건 잔존')}")
        return True
```

호출 위치는 **잔고 요약 조회(Task 4 Step 3 블록) «앞»** 으로 이동한다(취소→잔고→대조→복원). `pending_sell_codes` 변수와 그 소비처(SELL_PENDING 분기, `:913-919` 부근 — 실제 줄은 grep `pending_sell_codes` 로 확정)를 제거해 복원은 항상 POSITIONED 로 통일.

- [ ] **Step 5: 실행 — 전부 PASS** (`pytest tests/test_live_p0_pending_orders.py tests/test_live_p0_restore.py tests/test_state_restorer_live_real_table.py -v`)

- [ ] **Step 6: Commit**

```bash
git add framework/broker.py bot/state_restorer.py tests/test_live_p0_pending_orders.py
git commit -m "feat(live): 크래시 후 미체결은 고아가 된다 — 기동 시 전량 취소하고 깨끗한 잔고에서 복원한다"
```

---

## Task 7: D3 — EOD 실매도 반환값 검사 (스펙 테스트 8)

**Files:**
- Modify: `bot/liquidation_handler.py:305-315`(본청산) · `:415-432`(재시도)
- Test: `tests/test_live_p0_eod_sell.py`

**Interfaces:**
- Consumes: `trading_manager.execute_sell_order(...) -> bool`(기존, `core/trading/order_execution.py:319`)
- Produces: 실매도 실패가 `failed_stocks`/`still_failed` 에 `(stock_code, owner)` 로 적재 — 기존 재시도·강제완료 체인이 그대로 소비

- [ ] **Step 1: 실패하는 테스트 작성**

기존 `tests/test_bot_liquidation.py` 의 헬퍼(핸들러 생성·슬롯 세팅)를 먼저 읽고 재사용한다. 골자:

```python
# tests/test_live_p0_eod_sell.py
"""D3: EOD 실매도 실패는 무음이 아니라 failed_stocks 적재다 (페이퍼 브랜치와 대칭)."""
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest


class TestEodRealSellFailureCaptured:
    def test_sell_returning_false_is_added_to_failed(self, liquidation_setup):
        """red 재현: 현행 :310 은 반환값을 버려 failed_stocks 에 안 들어간다."""
        handler, bot = liquidation_setup            # is_virtual_mode=False 로 구성
        bot.trading_manager.move_to_sell_candidate.return_value = True
        bot.trading_manager.execute_sell_order = AsyncMock(return_value=False)
        failed = asyncio.run(handler.execute_end_of_day_liquidation())
        # 검증 축: 실패 종목이 재시도 대상에 남아 있어야 한다.
        assert handler._eod_failed_stocks, "실매도 False 가 무음으로 사라졌다"

    def test_sell_returning_true_is_not_failed(self, liquidation_setup):
        handler, bot = liquidation_setup
        bot.trading_manager.move_to_sell_candidate.return_value = True
        bot.trading_manager.execute_sell_order = AsyncMock(return_value=True)
        asyncio.run(handler.execute_end_of_day_liquidation())
        assert not handler._eod_failed_stocks
```

⚠️ `liquidation_setup` fixture 는 `tests/test_bot_liquidation.py` 의 기존 구성 방식을 복제해 작성한다(진입 함수명·`_eod_failed_stocks` 실제 속성명은 그 파일과 `bot/liquidation_handler.py:157-330` 을 읽고 맞출 것 — 다르면 **테스트를 실제 이름에 맞추고 이 계획서의 이름을 고친다**).

- [ ] **Step 2: 실행 — red 확인** (실패 적재 assert 가 FAIL)

- [ ] **Step 3: 구현**

`:309-314` 교체 (본청산):

```python
                            sell_ok = False
                            if moved:
                                sell_ok = await self.bot.trading_manager.execute_sell_order(
                                    stock_code, quantity, current_price,
                                    f"{time_label} 시장가 일괄매도", market=True,
                                    force=True, strategy=owner_name
                                )
                            if not sell_ok:
                                # 페이퍼 브랜치(:294-303)와 대칭 — 실패는 재시도 대상 (2026-08-14 P0 D3)
                                self.logger.warning(
                                    f"{stock_code} 실매도 실패({'주문 거부' if moved else '후보 전환 실패'}) - 재시도 대상에 추가")
                                failed_stocks.append((stock_code, owner_name))
```

(기존 `if moved:` 성공 로그는 `sell_ok` 참일 때만 남긴다.) `:421-427` 재시도 브랜치도 동일 패턴으로 — `sell_ok` False 면 `still_failed.append((stock_code, resolved_owner))`.

- [ ] **Step 4: 실행 — PASS + 기존 청산 테스트 회귀 0**

Run: `pytest tests/test_live_p0_eod_sell.py tests/test_bot_liquidation.py tests/test_liquidation_eod_owner_pairing.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add bot/liquidation_handler.py tests/test_live_p0_eod_sell.py
git commit -m "fix(live): EOD 실매도 실패가 조용히 삼켜졌다 — 반환값을 검사해 페이퍼와 대칭으로 재시도 체인에 태운다"
```

---

## Task 8: D4(d) — 종료 경로 교정 (스펙 테스트 11)

**Files:**
- Modify: `bot/initializer.py:708`
- Test: `tests/test_live_p0_shutdown.py`

**Interfaces:**
- Consumes: `KISBroker.disconnect()`(async, `framework/broker.py:239`)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_live_p0_shutdown.py
"""D4(d): shutdown 이 존재하지 않는 broker.shutdown() 을 불러 후반부(PID 삭제)가 상시 스킵됐다."""
import asyncio
from unittest.mock import AsyncMock, Mock

from framework.broker import KISBroker
from bot.initializer import BotInitializer


def test_shutdown_reaches_pid_cleanup():
    bot = Mock()
    bot.telegram.shutdown = AsyncMock()
    bot.broker = Mock(spec=KISBroker)          # spec: 실브로커에 없는 메서드는 AttributeError
    bot.broker.disconnect = AsyncMock()
    bot.pid_file.exists.return_value = True
    init = BotInitializer(bot)
    init._flush_state_to_db = Mock()
    init._cancel_pending_orders = AsyncMock()
    asyncio.run(init.shutdown())
    bot.broker.disconnect.assert_awaited_once()
    bot.pid_file.unlink.assert_called_once()   # red: 현행은 AttributeError 로 미도달
```

- [ ] **Step 2: 실행 — red 확인** (`unlink` 미호출로 FAIL)

- [ ] **Step 3: 구현** — `bot/initializer.py:707-708` 교체:

```python
            # API 매니저 종료 (KISBroker 에 shutdown 은 없다 — disconnect 가 정식 경로, 2026-08-14 P0 D4d)
            await self.bot.broker.disconnect()
```

- [ ] **Step 4: 실행 — PASS** (`pytest tests/test_live_p0_shutdown.py -v`)

- [ ] **Step 5: Commit**

```bash
git add bot/initializer.py tests/test_live_p0_shutdown.py
git commit -m "fix: 종료가 매번 AttributeError 로 잘렸다 — 없는 broker.shutdown 대신 disconnect 를 부른다 (페이퍼 발효는 재기동 후)"
```

---

## Task 9: 진입점 순서·라이브 불변·전체 회귀 (스펙 테스트 14·15 + 완료 판정)

**Files:**
- Test: `tests/test_live_p0_entrypoint.py`
- Modify: `docs/superpowers/plans/2026-08-14-live-p0-blockers.md`(체크박스 갱신)

- [ ] **Step 1: 진입점 순서 테스트 (스펙 테스트 14 — 소스 문자열 단언 금지)**

```python
# tests/test_live_p0_entrypoint.py
"""실전 복원 진입점을 실제로 돌려 호출 «순서»를 단언한다.
소스 문자열 단언은 죽은 경로에서도 통과한 전례가 있다(재사용 규칙)."""
import asyncio
from unittest.mock import Mock

import pandas as pd

from tests.broker_contract import make_account_balance
from tests.test_live_p0_restore import _restorer_with


def test_real_restore_call_order_cancel_then_balance_then_holdings():
    calls = []
    broker = Mock()
    broker.get_pending_orders.side_effect = lambda: calls.append('pending') or []
    broker.get_account_balance.side_effect = (
        lambda: calls.append('balance') or make_account_balance())
    broker.get_holdings.side_effect = lambda: calls.append('holdings') or []
    db = Mock(); db.get_real_open_positions.return_value = pd.DataFrame()
    r = _restorer_with(db, broker, Mock())
    asyncio.run(r._restore_holdings_from_real_account())
    assert calls[0] == 'pending', f"미체결 취소가 첫 단계가 아니다: {calls}"
    assert calls.index('balance') < calls.index('holdings')


def test_paper_restore_never_touches_real_broker_apis():
    """스펙 테스트 15(라이브 불변): 페이퍼 복원은 실전용 브로커 API 를 호출하지 않는다."""
    from tests.test_state_restorer_live_real_table import _make_restorer, _wire_trading_manager
    broker = Mock()
    db = Mock(); db.get_virtual_open_positions.return_value = pd.DataFrame()
    r = _make_restorer(db, strategies={}, paper_trading=True, broker=broker)
    _wire_trading_manager(r)
    asyncio.run(r._restore_holdings_from_db())
    broker.get_pending_orders.assert_not_called()
    broker.get_holdings.assert_not_called()
    broker.cancel_order.assert_not_called()
```

- [ ] **Step 2: 실행 — PASS** (`pytest tests/test_live_p0_entrypoint.py -v`)

- [ ] **Step 3: 신규 테스트 전체 일괄 실행**

Run: `pytest tests/test_live_broker_contract.py tests/test_live_p0_startup_abort.py tests/test_live_p0_fund_init.py tests/test_live_p0_restore.py tests/test_live_p0_pending_orders.py tests/test_live_p0_eod_sell.py tests/test_live_p0_shutdown.py tests/test_live_p0_entrypoint.py tests/test_state_restorer_live_real_table.py -v`
Expected: all passed

- [ ] **Step 4: 전체 스위트 회귀 — 실패 «집합» 차분**

메모리 [[reference-pytest-full-suite-invocation]] 의 방법(repo 루트 + VS 번들 Python)으로:
1. 작업 트리 상태로 전체 스위트 → 실패 목록 A 저장
2. `git stash` 로 베이스라인 복원 → 전체 스위트 → 실패 목록 B 저장 → `git stash pop`
3. **A − B = ∅** 이어야 한다(신규 실패 0). B 에만 있는 실패는 기존 결함 — 건드리지 않는다.

- [ ] **Step 5: Commit (계획서 체크박스 갱신 포함)**

```bash
git add docs/superpowers/plans/2026-08-14-live-p0-blockers.md
git commit -m "test(live): P0 진입점 순서·페이퍼 불변 고정 + 전체 스위트 회귀 0 확인"
```

---

## 완료 후 (executor 범위 밖 — 관리자·사장님)

- 워크트리 → main 병합은 **superpowers:finishing-a-development-branch** 로, 병합·푸시는 사장님 확인.
- 스펙 §6 완료 판정 2(페이퍼 재기동 후 종료 로그)·4(실전 경보 체인 리허설)는 운영 확인 사항 — 병합 후 NEXT_SESSION 에 등재.
- `real_total_funds_cap` 실제 값·실전 인스턴스 셋업(계좌·앱키·전략 선정)은 별건 결정.

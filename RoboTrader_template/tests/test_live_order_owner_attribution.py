"""실주문이 «소유 전략» 을 싣고 다니는지 — 2전략 대칭 회귀.

배경 (2026-08-14 실매매 전환 감사 Fix 2):
  실전 DB 기록 경로 `core/orders/order_db_handler._get_strategy_name_for_order`
  는 `trading_manager.get_trading_stock(stock_code)` 를 **strategy 인자 없이**
  불렀다. 두 전략이 같은 종목을 보유하면 `stock_state_manager:310-315` 가
  `[모호조회]` 를 찍고 `matches[0]`(임의 소유자)을 돌려준다 → 실전 체결이
  남의 전략 이름으로 DB 에 기록된다. 같은 형태가
  `order_db_handler:95`·`:101`, `order_completion_handler:258` 에도 있었다.

  근본 원인은 「주문에 소유 전략이 안 실려 있다」다 —
  `order_monitor.py:361-369` 주석이 이미 그렇게 적어 두었다
  ("Order 에 소유 전략 필드가 없고 ... 실전 전환 전에 주문→소유 전략 연결을
  만들어 owner 를 전달해야 한다").

  ⚠️ real_trading_records 의 BUY 112행 중 해석 가능한 전략키를 가진 행은
  0건이다(스크리너 사유 문자열·삭제된 전략 macd_cross). 이 경로는 프로덕션
  실행 이력이 사실상 없다 ⇒ **테스트가 유일한 방어선**이고, 모든 단언은
  2전략 대칭이어야 한다.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.models import (
    Order, OrderStatus, OrderType, StockState, TradingStock,
)
from core.trading.order_completion_handler import OrderCompletionHandler
from core.trading.order_execution import OrderExecution
from core.trading.stock_state_manager import StockStateManager
from utils.korean_time import now_kst


KEY_A, CLS_A = 'rs_leader', 'RSLeaderStrategy'
KEY_B, CLS_B = 'elder_ema_pullback', 'ElderEmaPullbackStrategy'
CODE = '005930'


# ---------------------------------------------------------------------------
# 0. Order 가 owner 를 싣는다
# ---------------------------------------------------------------------------

class TestOrderCarriesOwner:
    def test_order_model_has_owner_field(self):
        o = Order(order_id='X', stock_code=CODE, order_type=OrderType.BUY,
                  price=1000.0, quantity=1, timestamp=now_kst(),
                  owner_strategy=KEY_A)
        assert o.owner_strategy == KEY_A

    def test_order_owner_defaults_to_empty(self):
        """레거시 생성자(owner 미지정)는 종전대로 동작 — 빈 표기."""
        o = Order(order_id='X', stock_code=CODE, order_type=OrderType.BUY,
                  price=1000.0, quantity=1, timestamp=now_kst())
        assert o.owner_strategy == ""


# ---------------------------------------------------------------------------
# 1. 실주문 실행이 owner 를 주문에 심는다 (place_buy_order / place_sell_order)
# ---------------------------------------------------------------------------

def _order_manager(paper=False):
    from core.order_manager import OrderManager
    config = Mock()
    config.paper_trading = paper
    config.order_management.buy_timeout_seconds = 300
    config.order_management.sell_timeout_seconds = 120
    broker = Mock()
    om = OrderManager(config=config, broker=broker,
                      telegram_integration=None, db_manager=None)
    om.telegram = None
    om._get_stock_name = Mock(return_value='삼성전자')
    return om


def _ok_result(order_id):
    return {'success': True, 'order_id': order_id, 'message': '',
            'error_code': '', 'data': None}


class TestRealOrderStampsOwner:
    def _patch_market(self, monkeypatch):
        import config.market_hours as mh
        monkeypatch.setattr(mh.MarketHours, 'can_place_order',
                            staticmethod(lambda *a, **k: True))
        cb = Mock()
        cb.is_market_halted.return_value = False
        cb.is_vi_active.return_value = False
        monkeypatch.setattr(mh, 'get_circuit_breaker_state', lambda: cb)

    def test_real_buy_order_carries_owner(self, monkeypatch):
        self._patch_market(monkeypatch)
        om = _order_manager()
        om.broker.place_buy_order = Mock(return_value=_ok_result('OID-A'))

        oid = asyncio.run(om.place_buy_order(
            CODE, 10, 70_000.0, owner_strategy=KEY_A))

        assert oid == 'OID-A'
        assert om.pending_orders['OID-A'].owner_strategy == KEY_A
        # 대칭: 다른 전략 표기는 절대 실리지 않는다
        assert om.pending_orders['OID-A'].owner_strategy != KEY_B

    def test_real_sell_order_carries_owner(self, monkeypatch):
        self._patch_market(monkeypatch)
        om = _order_manager()
        om.broker.place_sell_order = Mock(return_value=_ok_result('OID-B'))
        del om.broker.get_sellable_quantity  # 조회 미지원 브로커 경로

        oid = asyncio.run(om.place_sell_order(
            CODE, 10, 70_000.0, owner_strategy=KEY_B))

        assert oid == 'OID-B'
        assert om.pending_orders['OID-B'].owner_strategy == KEY_B
        assert om.pending_orders['OID-B'].owner_strategy != KEY_A


# ---------------------------------------------------------------------------
# 2. 호출부가 실제로 owner 를 넘긴다 (기본값 falsy 인자는 안 넘기면 죽는다)
# ---------------------------------------------------------------------------

def _execution_with_two_owners(state_manager):
    om = Mock()
    om.place_buy_order = AsyncMock(return_value='OID-1')
    om.place_sell_order = AsyncMock(return_value='OID-2')
    ex = OrderExecution(
        state_manager=state_manager,
        intraday_manager=Mock(),
        data_collector=Mock(),
        order_manager=om,
    )
    fm = Mock()
    fm.is_sell_cooldown_active.return_value = False
    fm.can_add_position.return_value = True
    ex.set_fund_manager(fm)
    return ex, om


def _two_owner_slots(state_manager, state=StockState.SELECTED,
                     owner_a=KEY_A, owner_b=KEY_B, with_position=False):
    made = {}
    for owner in (owner_a, owner_b):
        ts = TradingStock(stock_code=CODE, stock_name='삼성전자', state=state,
                          selected_time=now_kst(), owner_strategy_name=owner)
        if with_position:
            ts.set_position(10, 60_000.0)
        state_manager.register_stock(ts)
        made[owner] = ts
    return made


class TestCallersThreadOwner:
    def test_execute_buy_order_passes_owner_to_order_manager(self):
        sm = StockStateManager()
        _two_owner_slots(sm)
        ex, om = _execution_with_two_owners(sm)

        ok = asyncio.run(ex.execute_buy_order(
            CODE, 10, 70_000.0, reason='테스트', strategy=KEY_A))

        assert ok is True
        _args, kwargs = om.place_buy_order.call_args
        assert kwargs.get('owner_strategy') == KEY_A
        assert kwargs.get('owner_strategy') != KEY_B

    def test_execute_sell_order_passes_owner_to_order_manager(self):
        sm = StockStateManager()
        slots = _two_owner_slots(sm, state=StockState.POSITIONED,
                                 with_position=True)
        ex, om = _execution_with_two_owners(sm)
        # SELL_CANDIDATE 로 전이한 뒤 매도 주문
        sm.change_stock_state(CODE, StockState.SELL_CANDIDATE, '테스트',
                              strategy=KEY_B)
        assert slots[KEY_B].state == StockState.SELL_CANDIDATE

        ok = asyncio.run(ex.execute_sell_order(
            CODE, 10, 70_000.0, reason='테스트', strategy=KEY_B))

        assert ok is True
        _args, kwargs = om.place_sell_order.call_args
        assert kwargs.get('owner_strategy') == KEY_B
        assert kwargs.get('owner_strategy') != KEY_A


# ---------------------------------------------------------------------------
# 3. 실전 DB 기록이 «주문 자신의» owner 로 저장된다
# ---------------------------------------------------------------------------

def _db_order_manager_with_two_owners(slot_owner_a=KEY_A, slot_owner_b=KEY_B):
    om = _order_manager(paper=False)
    sm = StockStateManager()
    _two_owner_slots(sm, state=StockState.POSITIONED, with_position=True,
                     owner_a=slot_owner_a, owner_b=slot_owner_b)
    tm = Mock()
    tm.get_trading_stock.side_effect = sm.get_trading_stock
    om.trading_manager = tm
    db = Mock()
    db.save_real_buy.return_value = 42
    db.save_real_sell.return_value = True
    db.get_last_open_real_buy.return_value = None
    om.db_manager = db
    return om, db


def _real_order(owner, side=OrderType.BUY, order_id='OID'):
    return Order(order_id=order_id, stock_code=CODE, order_type=side,
                 price=70_000.0, quantity=10, timestamp=now_kst(),
                 status=OrderStatus.FILLED, remaining_quantity=0,
                 stock_name='삼성전자', owner_strategy=owner)


class TestRealDbRecordAttribution:
    @pytest.mark.parametrize('owner,other', [(KEY_A, KEY_B), (KEY_B, KEY_A)])
    def test_buy_record_uses_orders_own_owner(self, owner, other):
        om, db = _db_order_manager_with_two_owners()

        asyncio.run(om._save_real_trade_to_db(_real_order(owner), 70_000.0))

        _a, kwargs = db.save_real_buy.call_args
        assert kwargs['strategy'] == owner
        assert kwargs['strategy'] != other

    @pytest.mark.parametrize('owner,other', [(KEY_A, KEY_B), (KEY_B, KEY_A)])
    def test_sell_record_uses_orders_own_owner(self, owner, other):
        om, db = _db_order_manager_with_two_owners()

        asyncio.run(om._save_real_trade_to_db(
            _real_order(owner, side=OrderType.SELL), 71_000.0))

        _a, kwargs = db.save_real_sell.call_args
        assert kwargs['strategy'] == owner
        assert kwargs['strategy'] != other

    def test_owner_resolution_does_not_depend_on_code_only_lookup(self):
        """조회가 종목코드 단독이면 두 owner 가 같은 값으로 붕괴한다."""
        om, db = _db_order_manager_with_two_owners()

        asyncio.run(om._save_real_trade_to_db(_real_order(KEY_A), 70_000.0))
        first = db.save_real_buy.call_args[1]['strategy']
        db.save_real_buy.reset_mock()
        asyncio.run(om._save_real_trade_to_db(_real_order(KEY_B), 70_000.0))
        second = db.save_real_buy.call_args[1]['strategy']

        assert first != second, "두 전략의 기록이 같은 이름으로 붕괴했다"
        assert {first, second} == {KEY_A, KEY_B}


# ---------------------------------------------------------------------------
# 4. 체결 콜백이 «주문 owner» 의 슬롯만 건드린다 (동일 종목 2 owner)
# ---------------------------------------------------------------------------

class TestFillCallbackPicksOwnersSlot:
    def _handler_with_two_owner_slots(self, slot_owner_a, slot_owner_b):
        sm = StockStateManager()
        om = Mock()
        om.config.paper_trading = False
        h = OrderCompletionHandler(state_manager=sm, order_manager=om)
        a = Mock(); a.name = CLS_A
        b = Mock(); b.name = CLS_B
        h.set_strategy(b)
        h.set_strategies({KEY_A: a, KEY_B: b})

        slots = {}
        for key, owner, strat in ((KEY_A, slot_owner_a, a),
                                  (KEY_B, slot_owner_b, b)):
            ts = TradingStock(stock_code=CODE, stock_name='삼성전자',
                              state=StockState.BUY_PENDING,
                              selected_time=now_kst(),
                              owner_strategy_name=owner)
            ts.owner_strategy = strat
            ts.current_order_id = f'OID-{key}'
            sm.register_stock(ts)
            slots[key] = ts
        return h, a, b, slots

    def test_fill_positions_only_the_owners_slot_class_name_notation(self):
        """라이브 매수 형상: 슬롯 owner=클래스명, 주문 owner=폴더키."""
        h, a, b, slots = self._handler_with_two_owner_slots(CLS_A, CLS_B)

        asyncio.run(h.on_order_filled(
            _real_order(KEY_A, order_id='OID-rs_leader')))

        assert slots[KEY_A].state == StockState.POSITIONED
        assert slots[KEY_B].state == StockState.BUY_PENDING
        a.on_order_filled.assert_called_once()
        b.on_order_filled.assert_not_called()

    def test_fill_positions_only_the_owners_slot_folder_key_notation(self):
        """복원 형상: 슬롯 owner=폴더키, 주문 owner=폴더키."""
        h, a, b, slots = self._handler_with_two_owner_slots(KEY_A, KEY_B)

        asyncio.run(h.on_order_filled(
            _real_order(KEY_B, order_id='OID-elder_ema_pullback')))

        assert slots[KEY_B].state == StockState.POSITIONED
        assert slots[KEY_A].state == StockState.BUY_PENDING
        b.on_order_filled.assert_called_once()
        a.on_order_filled.assert_not_called()

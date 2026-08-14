"""실전 매도가 «자기 전략의» 매수행에 붙는지 — 2전략 대칭 회귀.

배경 (2026-08-14 리뷰 R3 — Fix 2 의 매도 반쪽):
  `db/repositories/trading.py:190` `get_last_open_real_buy(stock_code)` 에는
  전략 술어가 없다. 두 전략이 한 종목을 보유하면 A 의 SELL 이 B 의 BUY 행에
  붙어 **B 의 행이 닫히고 A 의 행이 열린 채 남는다.**

  그리고 이 경로는 우회로가 없다 — `order_db_handler.py:112-118` 은
  `save_real_buy` 가 돌려준 id 를 **로그만 찍고 슬롯에 안 넣었다**. 그래서
  실전 모드에서 `_virtual_buy_record_id` 는 «항상» None 이고
  `get_last_open_real_buy` 가 모든 실매도의 buy_record_id 유일 공급원이다.

  🔴 왜 이 브랜치와 함께 나가야 하나: 오귀속이 일어나도 다음 기동에서 수량은
  맞아떨어지므로 `_detect_holdings_mismatch` 는 아무것도 보고하지 않는다 —
  Fix 3 이 기대는 fail-closed 게이트가 이 결함에 **구조적으로 눈이 멀었다**.
  그 상태로 Fix 3 이 살아남은 수량을 «틀린 owner» 로 복원하고, Fix 2 는 그
  틀린 소유권을 청산 라우팅의 근거로 만든다.

  두 반쪽 다 필요하다:
   - 세션 내: 매수 체결이 받은 id 를 소유 슬롯에 적재
   - 재기동 후: 복원은 id 를 다시 채우지 않으므로 쿼리에 전략 술어가 필요
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.models import Order, OrderStatus, OrderType, StockState, TradingStock
from core.trading.stock_state_manager import StockStateManager
from utils.korean_time import now_kst

KEY_A = 'rs_leader'
KEY_B = 'elder_ema_pullback'
CODE = '005930'


def _om_with_two_owner_slots():
    from core.order_manager import OrderManager
    config = Mock()
    config.paper_trading = False
    config.order_management.buy_timeout_seconds = 300
    om = OrderManager(config=config, broker=Mock(),
                      telegram_integration=None, db_manager=None)
    om.telegram = None

    sm = StockStateManager()
    slots = {}
    # B 를 먼저 등록 — 종목코드 단독 조회는 matches[0] 을 돌려주므로 이 순서라야
    # 「임의 소유자를 집는다」가 실제로 틀린 답을 낸다.
    for owner in (KEY_B, KEY_A):
        ts = TradingStock(stock_code=CODE, stock_name='삼성전자',
                          state=StockState.POSITIONED, selected_time=now_kst(),
                          owner_strategy_name=owner)
        ts.set_position(10, 70_000.0)
        sm.register_stock(ts)
        slots[owner] = ts
    # ⚠️ 맨 Mock 은 hasattr 이 무조건 True 라 find_owned_stock 이 Mock 을 돌려준다
    # (계약을 발명한 mock). 실제 해석 규칙에 위임한다.
    from core.trading.order_completion_handler import OrderCompletionHandler
    a = Mock(); a.name = 'RSLeaderStrategy'
    b = Mock(); b.name = 'ElderEmaPullbackStrategy'
    handler = OrderCompletionHandler(state_manager=sm, order_manager=om)
    handler.set_strategies({KEY_A: a, KEY_B: b})

    tm = Mock()
    tm.get_trading_stock.side_effect = sm.get_trading_stock
    tm.find_owned_stock.side_effect = handler._find_owned_stock
    om.trading_manager = tm

    db = Mock()
    db.save_real_buy.return_value = 4242
    db.save_real_sell.return_value = True
    db.get_last_open_real_buy.return_value = None
    om.db_manager = db
    return om, db, slots


def _order(side, owner, order_id='OID'):
    return Order(order_id=order_id, stock_code=CODE, order_type=side,
                 price=70_000.0, quantity=10, timestamp=now_kst(),
                 status=OrderStatus.FILLED, remaining_quantity=0,
                 stock_name='삼성전자', owner_strategy=owner)


# ---------------------------------------------------------------------------
# 1. 세션 내 — 매수 체결이 받은 buy_record_id 를 «소유» 슬롯에 적재한다
# ---------------------------------------------------------------------------

class TestBuyRecordIdIsStashedOnOwnersSlot:
    def test_buy_stashes_id_on_owner_slot_only(self):
        om, db, slots = _om_with_two_owner_slots()

        asyncio.run(om._save_real_trade_to_db(
            _order(OrderType.BUY, KEY_A), 70_000.0))

        assert slots[KEY_A]._virtual_buy_record_id == 4242
        # 대칭: 남의 슬롯은 건드리지 않는다
        assert slots[KEY_B]._virtual_buy_record_id is None

    def test_sell_uses_stashed_id_without_touching_db_lookup(self):
        om, db, slots = _om_with_two_owner_slots()
        asyncio.run(om._save_real_trade_to_db(
            _order(OrderType.BUY, KEY_A), 70_000.0))

        asyncio.run(om._save_real_trade_to_db(
            _order(OrderType.SELL, KEY_A, 'OID-S'), 71_000.0))

        assert db.save_real_sell.call_args[1]['buy_record_id'] == 4242
        db.get_last_open_real_buy.assert_not_called()

    def test_other_owners_sell_does_not_inherit_the_id(self):
        """대칭: A 의 매수 id 가 B 의 매도에 새어 들어가면 안 된다."""
        om, db, slots = _om_with_two_owner_slots()
        asyncio.run(om._save_real_trade_to_db(
            _order(OrderType.BUY, KEY_A), 70_000.0))
        db.get_last_open_real_buy.return_value = 777

        asyncio.run(om._save_real_trade_to_db(
            _order(OrderType.SELL, KEY_B, 'OID-S'), 71_000.0))

        assert db.save_real_sell.call_args[1]['buy_record_id'] != 4242
        assert db.save_real_sell.call_args[1]['buy_record_id'] == 777


# ---------------------------------------------------------------------------
# 2. 재기동 후 — 조회에 전략 술어가 실린다
# ---------------------------------------------------------------------------

class TestRepositoryQueryCarriesStrategy:
    def _repo(self, rows):
        """cursor.execute 를 가로채 SQL·파라미터를 그대로 캡처한다."""
        from db.repositories.trading import TradingRepository
        captured = []

        cursor = Mock()

        def _execute(sql, params=None):
            captured.append((sql, params))
            cursor.fetchone.return_value = rows.pop(0) if rows else None
        cursor.execute.side_effect = _execute

        conn = Mock()
        conn.cursor.return_value = cursor
        ctx = Mock()
        ctx.__enter__ = Mock(return_value=conn)
        ctx.__exit__ = Mock(return_value=False)

        repo = TradingRepository.__new__(TradingRepository)
        repo.logger = Mock()
        repo._get_connection = Mock(return_value=ctx)
        repo._real_table = 'real_trading_records'
        return repo, captured

    def test_strategy_is_passed_as_a_query_predicate(self):
        repo, captured = self._repo([(11,)])

        result = repo.get_last_open_real_buy(CODE, strategy=KEY_A)

        assert result == 11
        sql, params = captured[0]
        assert 'strategy' in sql, "전략 술어가 SQL 에 없다"
        assert KEY_A in params
        # 대칭: 남의 전략 이름은 파라미터에 들어가지 않는다
        assert KEY_B not in params

    def test_no_strategy_keeps_legacy_query(self):
        """회귀: 미지정 호출은 종전 쿼리 그대로(전략 술어 없음, 경고 없음)."""
        repo, captured = self._repo([(11,)])

        result = repo.get_last_open_real_buy(CODE)

        assert result == 11
        assert len(captured) == 1
        sql, params = captured[0]
        assert 'strategy' not in sql
        repo.logger.warning.assert_not_called()

    def test_falls_back_to_code_only_when_owner_has_no_open_buy(self):
        """레거시 행(다른 표기)이 남아 있어도 짝을 잃지 않는다 — 단, 시끄럽게."""
        repo, captured = self._repo([None, (99,)])

        result = repo.get_last_open_real_buy(CODE, strategy=KEY_A)

        assert result == 99
        assert len(captured) == 2, "전략 조회 실패 후 폴백 조회가 없다"
        assert 'strategy' in captured[0][0]
        assert 'strategy' not in captured[1][0]
        repo.logger.warning.assert_called_once()


# ---------------------------------------------------------------------------
# 3. 호출부가 실제로 owner 를 넘긴다 (기본값 falsy 인자는 안 넘기면 죽는다)
# ---------------------------------------------------------------------------

class TestCallerThreadsStrategy:
    def test_db_handler_passes_order_owner_to_lookup(self):
        om, db, _slots = _om_with_two_owner_slots()
        db.get_last_open_real_buy.return_value = 5

        asyncio.run(om._save_real_trade_to_db(
            _order(OrderType.SELL, KEY_A, 'OID-S'), 71_000.0))

        _args, kwargs = db.get_last_open_real_buy.call_args
        passed = list(_args) + list(kwargs.values())
        assert KEY_A in passed
        assert KEY_B not in passed

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
from unittest.mock import AsyncMock, Mock

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


def _real_trading_manager(sm, strategies_by_key):
    """진짜 TradingStockManager facade 를 만들어 실제 해석 규칙을 태운다.

    ⚠️ 맨 Mock 으로 find_owned_stock 을 흉내내면 «계약을 발명한 mock» 이 되고
    (hasattr 이 항상 True), 프로덕션이 isinstance 로 실체를 검사하므로 그 가짜는
    이제 조용히 무시된다 — 그래서 실물을 쓴다(2026-08-14 리뷰 F5).
    """
    from core.trading_stock_manager import TradingStockManager
    intraday = Mock()
    intraday.add_selected_stock = AsyncMock(return_value=True)
    tm = TradingStockManager(intraday_manager=intraday, data_collector=Mock(),
                             order_manager=Mock())
    tm._state_manager = sm
    tm._completion_handler.state_manager = sm
    tm.set_strategies(strategies_by_key)
    return tm


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
    a = Mock(); a.name = 'RSLeaderStrategy'
    b = Mock(); b.name = 'ElderEmaPullbackStrategy'
    om.trading_manager = _real_trading_manager(sm, {KEY_A: a, KEY_B: b})

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


# ---------------------------------------------------------------------------
# 4. 라벨은 «체결 시점의 슬롯» 에서 — 접수 스냅샷을 쓰면 BUY/SELL 이 갈린다 (F1)
# ---------------------------------------------------------------------------

class TestDbLabelComesFromTheSlotAtFillTime:
    """리뷰 F1: `order.owner_strategy` 를 1순위로 쓰면 원장이 쪼개진다.

    그 값은 «주문 접수 시점» 스냅샷(=폴더키)인데 `trading_context.py:529` 가
    매수 성공 직후 슬롯 라벨을 클래스명으로 뒤집는다. 체결은 그 «뒤»에 온다.

        ca1ba2d : BUY 'RSLeaderStrategy'  SELL 'RSLeaderStrategy'   일관
        24f2f16 : BUY 'rs_leader'         SELL 'RSLeaderStrategy'   ***분열***

    슬롯마다 «첫 매수»에서 무조건 발생하므로 전략별 손익·일일 리포트가 갈린다.
    게다가 이 브랜치는 두 표기가 «같은 포지션에 공존»하게 만들어, 표기를 접지
    않는 유일한 소비자인 get_last_open_real_buy 의 R3 결함을 되살린다.

    ⇒ 라벨의 단일 진실원천은 «체결 시점의 슬롯» 이다
      (order_monitor.py:373 이 이미 같은 규칙을 쓴다).
    """

    def _fill_with_flip(self, om, side, order_owner, slot, slot_label_at_fill):
        """접수(주문에 폴더키가 실림) → :529 라벨 뒤집힘 → 체결 순서를 재현."""
        order = _order(side, order_owner, order_id=f'OID-{side}')
        slot.owner_strategy_name = slot_label_at_fill   # trading_context:529
        asyncio.run(om._save_real_trade_to_db(order, 70_000.0))
        return order

    def test_buy_and_sell_rows_carry_the_same_label(self):
        om, db, slots = _om_with_two_owner_slots()
        slot = slots[KEY_A]

        self._fill_with_flip(om, OrderType.BUY, KEY_A, slot, 'RSLeaderStrategy')
        buy_label = db.save_real_buy.call_args[1]['strategy']

        self._fill_with_flip(om, OrderType.SELL, 'RSLeaderStrategy', slot,
                             'RSLeaderStrategy')
        sell_label = db.save_real_sell.call_args[1]['strategy']

        assert buy_label == sell_label, (
            f"같은 포지션의 BUY/SELL 이 다른 라벨로 기록됐다: "
            f"{buy_label!r} vs {sell_label!r}"
        )
        assert buy_label == 'RSLeaderStrategy'

    def test_label_follows_the_slot_not_the_order_snapshot(self):
        om, db, slots = _om_with_two_owner_slots()
        slot = slots[KEY_A]

        self._fill_with_flip(om, OrderType.BUY, KEY_A, slot, 'RSLeaderStrategy')

        label = db.save_real_buy.call_args[1]['strategy']
        assert label == 'RSLeaderStrategy'
        assert label != KEY_A, "접수 시점 스냅샷(폴더키)이 기록됐다"

    def test_other_owners_label_never_leaks(self):
        """대칭: A 의 체결이 B 의 라벨로 기록되지 않는다."""
        om, db, slots = _om_with_two_owner_slots()

        self._fill_with_flip(om, OrderType.BUY, KEY_A, slots[KEY_A],
                             'RSLeaderStrategy')

        label = db.save_real_buy.call_args[1]['strategy']
        assert label == 'RSLeaderStrategy'
        assert label not in (KEY_B, 'ElderEmaPullbackStrategy')

    def test_falls_back_to_order_label_when_slot_is_gone(self):
        """대칭: 슬롯이 없으면(청산 후 등) 주문이 실어온 표기로 폴백한다."""
        om, db, _slots = _om_with_two_owner_slots()
        om.trading_manager = None

        asyncio.run(om._save_real_trade_to_db(
            _order(OrderType.BUY, KEY_A), 70_000.0))

        assert db.save_real_buy.call_args[1]['strategy'] == KEY_A

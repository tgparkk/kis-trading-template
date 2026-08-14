"""실체결의 보유 레지스트리 등록/해제가 owner 를 싣는지 — 2 owner 대칭 회귀.

배경 (2026-08-14 리뷰 R2):
  `order_monitor._handle_full_fill` 는 owner 를 하나도 넘기지 않았다.
    :370  fund_manager.add_position(order.stock_code)          → owner=None
    :396  fund_manager.release_investment(..., stock_code=...)  → remove_position(code, None)

  해악은 `can_add_position` 부풀리기가 **아니다** — 그건 distinct code 를 세므로
  (fund_manager.current_position_codes 는 FrozenSet[str]) (code, None) 이 끼어도
  숫자가 늘지 않는다. 진짜 해악은 **모호 제거 교착**이다:

    1) 아침 복원이 (code, 'rs_leader') 를 등록한다
       (_sync_fund_manager_for_position 은 owner 를 넘긴다)
    2) 장중 같은 종목 재매수 체결이 :370 에서 (code, None) 을 «추가로» 등록한다
    3) 매도 체결이 :396 에서 owner 없이 제거를 요청한다
       → fund_manager:645 `[모호제거] … 제거 요청을 보류합니다`
       → **제거가 영구히 보류된다**

  그 종목은 남은 세션 내내 current_position_codes 한 칸을 점유한다 —
  실탄으로 신규 진입을 굶기는 직행 경로다.

  Fix 2 로 Order 가 owner 를 싣게 됐으므로 두 곳 다 그대로 넘기면 된다.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fund_manager import FundManager
from core.models import Order, OrderStatus, OrderType
from utils.korean_time import now_kst

KEY_A = 'rs_leader'
KEY_B = 'elder_ema_pullback'
CODE = '005930'


def _order_manager(fund_manager):
    from core.order_manager import OrderManager
    config = Mock()
    config.paper_trading = False
    config.order_management.buy_timeout_seconds = 300
    om = OrderManager(config=config, broker=Mock(),
                      telegram_integration=None, db_manager=None)
    om.telegram = None
    om.db_manager = None
    om.trading_manager = None
    om.set_fund_manager(fund_manager)
    return om


def _order(side, owner, order_id='OID', quantity=10, price=70_000.0):
    o = Order(order_id=order_id, stock_code=CODE, order_type=side,
              price=price, quantity=quantity, timestamp=now_kst(),
              status=OrderStatus.PENDING, remaining_quantity=quantity,
              stock_name='삼성전자', owner_strategy=owner)
    return o


def _status(quantity=10, price=70_000.0):
    return {'ord_qty': str(quantity), 'avg_prvs': str(int(price)),
            'cncl_yn': 'N', 'actual_unfilled': False}


def _fill(om, order, quantity=10, price=70_000.0):
    om.pending_orders[order.order_id] = order
    asyncio.run(om._handle_full_fill(
        order.order_id, order, _status(quantity, price), quantity))


# ---------------------------------------------------------------------------
# 1. 매수 체결이 owner 와 함께 등록한다
# ---------------------------------------------------------------------------

class TestBuyFillRegistersOwner:
    def test_buy_fill_registers_entry_under_orders_owner(self):
        fm = FundManager(initial_funds=10_000_000)
        om = _order_manager(fm)
        fm.reserve_funds('OID-A', 700_000)

        _fill(om, _order(OrderType.BUY, KEY_A, 'OID-A'))

        assert (CODE, KEY_A) in fm._position_entries
        # 대칭: 남의 것도, 무기명도 만들지 않는다
        assert (CODE, KEY_B) not in fm._position_entries
        assert (CODE, None) not in fm._position_entries

    def test_two_owners_get_two_entries_one_code(self):
        fm = FundManager(initial_funds=10_000_000)
        om = _order_manager(fm)
        fm.reserve_funds('OID-A', 700_000)
        fm.reserve_funds('OID-B', 700_000)

        _fill(om, _order(OrderType.BUY, KEY_A, 'OID-A'))
        _fill(om, _order(OrderType.BUY, KEY_B, 'OID-B'))

        assert (CODE, KEY_A) in fm._position_entries
        assert (CODE, KEY_B) in fm._position_entries
        # 보유 «종목 수» 는 distinct code 라 1 (한도 부풀리기는 없다)
        assert fm.current_position_codes == frozenset({CODE})


# ---------------------------------------------------------------------------
# 2. 매도 체결이 owner 의 엔트리만 지운다 — 그리고 교착이 안 생긴다
# ---------------------------------------------------------------------------

class TestSellFillRemovesOwnersEntry:
    def test_sell_fill_removes_only_the_owners_entry(self):
        fm = FundManager(initial_funds=10_000_000)
        om = _order_manager(fm)
        fm.add_position(CODE, KEY_A)
        fm.add_position(CODE, KEY_B)
        fm.invested_funds = 1_400_000

        _fill(om, _order(OrderType.SELL, KEY_A, 'OID-S'))

        assert (CODE, KEY_A) not in fm._position_entries
        # 대칭: B 의 보유는 그대로 남는다
        assert (CODE, KEY_B) in fm._position_entries

    def test_restore_then_rebuy_then_sell_does_not_deadlock(self):
        """리뷰 R2 의 교착 시나리오 — 재현 후 해소를 단언한다.

        복원(owner 있음) → 장중 재매수 체결 → 매도 체결.
        종전에는 재매수가 (code, None) 을 만들어 owner 2개가 되고, owner 없는
        제거가 [모호제거] 로 «영구 보류» 되어 슬롯이 세션 내내 점유됐다.
        """
        fm = FundManager(initial_funds=10_000_000)
        om = _order_manager(fm)

        # 1) 아침 복원 — owner 를 실어 등록 (_sync_fund_manager_for_position 상당)
        fm.add_position(CODE, KEY_A)

        # 2) 장중 같은 종목 재매수 체결
        fm.reserve_funds('OID-A2', 700_000)
        _fill(om, _order(OrderType.BUY, KEY_A, 'OID-A2'))
        assert fm._position_entries == {(CODE, KEY_A)}, \
            f"재매수가 무기명 엔트리를 만들었다: {fm._position_entries}"

        # 3) 매도 체결 — 제거가 실제로 «일어나야» 한다
        _fill(om, _order(OrderType.SELL, KEY_A, 'OID-S'))

        assert CODE not in fm.current_position_codes, \
            "매도 후에도 슬롯이 점유돼 있다 (모호제거 교착)"

    def test_owner_less_legacy_order_still_removes_single_entry(self):
        """회귀: owner 없는 레거시 주문은 종전대로 단일 엔트리를 지운다."""
        fm = FundManager(initial_funds=10_000_000)
        om = _order_manager(fm)
        fm.add_position(CODE, None)
        fm.invested_funds = 700_000

        _fill(om, _order(OrderType.SELL, "", 'OID-S'))

        assert CODE not in fm.current_position_codes


# ---------------------------------------------------------------------------
# 3. 매도 원가(buy_cost)도 owner 슬롯에서 읽는다
# ---------------------------------------------------------------------------

class TestSellCostBasisUsesOwnersSlot:
    def test_release_amount_uses_owners_avg_price(self):
        """:396 이 회수하는 금액은 :380 이 고른 슬롯의 평단에서 나온다."""
        from core.trading.stock_state_manager import StockStateManager
        from core.models import StockState, TradingStock

        sm = StockStateManager()
        # B 를 «먼저» 등록한다 — 종목코드 단독 조회는 matches[0] 을 돌려주므로
        # 이 순서라야 「임의 소유자를 집는다」가 실제로 틀린 답을 낸다.
        # (A 를 먼저 등록하면 깨진 구현도 우연히 통과한다)
        for owner, avg in ((KEY_B, 90_000.0), (KEY_A, 50_000.0)):
            ts = TradingStock(stock_code=CODE, stock_name='삼성전자',
                              state=StockState.POSITIONED,
                              selected_time=now_kst(),
                              owner_strategy_name=owner)
            ts.set_position(10, avg)
            sm.register_stock(ts)

        fm = FundManager(initial_funds=10_000_000)
        om = _order_manager(fm)
        tm = Mock()
        tm.get_trading_stock.side_effect = sm.get_trading_stock
        om.trading_manager = tm
        fm.add_position(CODE, KEY_A)
        fm.add_position(CODE, KEY_B)
        fm.invested_funds = 1_400_000
        before = fm.invested_funds

        _fill(om, _order(OrderType.SELL, KEY_A, 'OID-S'), price=70_000.0)

        released = before - fm.invested_funds
        assert released == pytest.approx(500_000.0)   # A 의 평단 50,000 × 10
        assert released != pytest.approx(900_000.0)   # B 의 평단이 아니다

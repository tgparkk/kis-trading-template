"""실체결의 보유 레지스트리 등록/해제가 owner 를 싣는지 — 2 owner 대칭 회귀.

배경 (2026-08-14 리뷰 R2):
  `order_monitor._handle_full_fill` 는 owner 를 하나도 넘기지 않았다.
    :370  fund_manager.add_position(order.stock_code)          → owner=None
    :396  fund_manager.release_investment(..., stock_code=...)  → remove_position(code, None)

  해악은 `can_add_position` 부풀리기가 **아니다** — 그건 distinct code 를 세므로
  (`current_position_codes` 는 FrozenSet[str]) (code, None) 이 끼어도 숫자가
  늘지 않는다. 진짜 해악은 **모호 제거 교착**이다:

    1) 아침 복원이 (code, 'rs_leader') 를 등록한다
       (_sync_fund_manager_for_position 은 owner 를 넘긴다)
    2) 장중 같은 종목 재매수 체결이 :370 에서 (code, None) 을 «추가로» 등록한다
    3) 매도 체결이 :396 에서 owner 없이 제거를 요청한다
       → fund_manager `[모호제거] … 제거 요청을 보류합니다`
       → **제거가 영구히 보류된다**

  그 종목은 남은 세션 내내 보유 슬롯을 점유한다 — 실탄으로 신규 진입을 굶기는
  직행 경로다.

🔴 owner 의 «출처» 가 핵심이다 (2026-08-14 자체 검증에서 확인):
  주문이 실어온 `Order.owner_strategy` 를 그대로 쓰면 새 누수가 생긴다. 그
  값은 «주문 접수 시점의» 슬롯 스냅샷(=폴더키)인데, 매수 성공 직후
  `trading_context.py:529` 가 슬롯 owner 를 **클래스명** 으로 덮어써서 나중의
  매도 주문은 클래스명을 싣는다 ⇒ add/remove 표기가 갈려 엔트리가 영구 잔류.
  `test_multiowner_partial_sell_replay.TestOwnerNotationInvariance` 가
  「표기가 다르면 잔류한다」를 의도된 no-op 으로 못박아 두었고, 안전성의 근거를
  *등록과 해제가 **같은 슬롯 객체의** owner_strategy_name 을 읽기 때문* 이라고
  적어 두었다. 실주문 경로도 그 불변식을 따라야 한다.
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
from core.models import Order, OrderStatus, OrderType, StockState, TradingStock
from core.trading.order_completion_handler import OrderCompletionHandler
from core.trading.stock_state_manager import StockStateManager
from utils.korean_time import now_kst

KEY_A, CLS_A = 'rs_leader', 'RSLeaderStrategy'
KEY_B, CLS_B = 'elder_ema_pullback', 'ElderEmaPullbackStrategy'
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


def _slots(sm, *owners, avg_price=70_000.0):
    """(code, owner) 슬롯을 실제 StockStateManager 에 등록한다."""
    made = {}
    for owner in owners:
        ts = TradingStock(stock_code=CODE, stock_name='삼성전자',
                          state=StockState.POSITIONED, selected_time=now_kst(),
                          owner_strategy_name=owner)
        ts.set_position(10, avg_price)
        sm.register_stock(ts)
        made[owner] = ts
    return made


def _wire(om, sm, strategies_by_key):
    """실배선 재현 — trading_manager 는 표기-불변 조회를 «실제로» 제공한다.

    ⚠️ 맨 Mock 을 쓰면 hasattr 이 무조건 True 라 find_owned_stock 이 Mock 을
    돌려주고, 계약을 발명한 mock 위에서 테스트가 green 이 된다
    (tests/broker_contract.py 가 경고하는 그 형태다). 그래서 실제
    OrderCompletionHandler 의 해석 규칙에 위임한다.
    """
    handler = OrderCompletionHandler(state_manager=sm, order_manager=om)
    handler.set_strategies(strategies_by_key)

    tm = Mock()
    tm.get_trading_stock.side_effect = sm.get_trading_stock
    tm.find_owned_stock.side_effect = handler._find_owned_stock
    om.trading_manager = tm
    return tm


def _strategies():
    a = Mock(); a.name = CLS_A
    b = Mock(); b.name = CLS_B
    return a, b


def _order(side, owner, order_id='OID', quantity=10, price=70_000.0):
    return Order(order_id=order_id, stock_code=CODE, order_type=side,
                 price=price, quantity=quantity, timestamp=now_kst(),
                 status=OrderStatus.PENDING, remaining_quantity=quantity,
                 stock_name='삼성전자', owner_strategy=owner)


def _status(quantity=10, price=70_000.0):
    return {'ord_qty': str(quantity), 'avg_prvs': str(int(price)),
            'cncl_yn': 'N', 'actual_unfilled': False}


def _fill(om, order, quantity=10, price=70_000.0):
    om.pending_orders[order.order_id] = order
    asyncio.run(om._handle_full_fill(
        order.order_id, order, _status(quantity, price), quantity))


def _setup(*slot_owners, strategies=None):
    a, b = _strategies()
    fm = FundManager(initial_funds=10_000_000)
    om = _order_manager(fm)
    sm = StockStateManager()
    made = _slots(sm, *slot_owners)
    _wire(om, sm, strategies if strategies is not None else {KEY_A: a, KEY_B: b})
    return fm, om, made, a, b


# ---------------------------------------------------------------------------
# 1. 매수 체결이 owner 와 함께 등록한다
# ---------------------------------------------------------------------------

class TestBuyFillRegistersOwner:
    def test_buy_fill_registers_entry_under_the_owning_slot(self):
        fm, om, _made, _a, _b = _setup(KEY_A, KEY_B)
        fm.reserve_funds('OID-A', 700_000)

        _fill(om, _order(OrderType.BUY, KEY_A, 'OID-A'))

        assert (CODE, KEY_A) in fm._position_entries
        # 대칭: 남의 것도, 무기명도 만들지 않는다
        assert (CODE, KEY_B) not in fm._position_entries
        assert (CODE, None) not in fm._position_entries

    def test_two_owners_get_two_entries_one_code(self):
        fm, om, _made, _a, _b = _setup(KEY_A, KEY_B)
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
        fm, om, _made, _a, _b = _setup(KEY_A, KEY_B)
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
        fm, om, _made, _a, _b = _setup(KEY_A)

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

    def test_owner_less_legacy_slot_still_removes_single_entry(self):
        """회귀: 무기명 슬롯은 종전대로 (code, None) 로 등록·제거된다."""
        fm, om, _made, _a, _b = _setup("")
        fm.add_position(CODE, None)
        fm.invested_funds = 700_000

        _fill(om, _order(OrderType.SELL, "", 'OID-S'))

        assert CODE not in fm.current_position_codes


# ---------------------------------------------------------------------------
# 3. 매도 원가(buy_cost)도 owner 슬롯에서 읽는다
# ---------------------------------------------------------------------------

class TestSellCostBasisUsesOwnersSlot:
    def test_release_amount_uses_owners_avg_price(self):
        """회수 금액은 «소유» 슬롯의 평단에서 나와야 한다."""
        a, b = _strategies()
        fm = FundManager(initial_funds=10_000_000)
        om = _order_manager(fm)
        sm = StockStateManager()
        # B 를 «먼저» 등록한다 — 종목코드 단독 조회는 matches[0] 을 돌려주므로
        # 이 순서라야 「임의 소유자를 집는다」가 실제로 틀린 답을 낸다.
        _slots(sm, KEY_B, avg_price=90_000.0)
        _slots(sm, KEY_A, avg_price=50_000.0)
        _wire(om, sm, {KEY_A: a, KEY_B: b})

        fm.add_position(CODE, KEY_A)
        fm.add_position(CODE, KEY_B)
        fm.invested_funds = 1_400_000
        before = fm.invested_funds

        _fill(om, _order(OrderType.SELL, KEY_A, 'OID-S'), price=70_000.0)

        released = before - fm.invested_funds
        assert released == pytest.approx(500_000.0)   # A 의 평단 50,000 × 10
        assert released != pytest.approx(900_000.0)   # B 의 평단이 아니다


# ---------------------------------------------------------------------------
# 4. 등록·해제는 «같은 슬롯 객체» 에서 owner 를 읽는다 (표기 드리프트 차단)
# ---------------------------------------------------------------------------

class TestRegistryOwnerComesFromTheSlotNotTheOrder:
    """레지스트리 키는 주문의 «스냅샷» 이 아니라 슬롯의 «현재» owner 여야 한다."""

    def test_buy_fill_registers_under_the_slots_current_label(self):
        """주문은 폴더키를 싣고 있어도 등록 키는 슬롯의 클래스명이어야 한다."""
        fm, om, _made, _a, _b = _setup(CLS_A)
        fm.reserve_funds('OID-A', 700_000)

        _fill(om, _order(OrderType.BUY, KEY_A, 'OID-A'))

        assert (CODE, CLS_A) in fm._position_entries
        # 대칭: 주문이 실어온 폴더키로는 등록되지 않는다 (그 키로는 아무도 안 지운다)
        assert (CODE, KEY_A) not in fm._position_entries
        assert (CODE, None) not in fm._position_entries

    def test_buy_then_sell_releases_the_slot_despite_notation_drift(self):
        fm, om, _made, _a, _b = _setup(CLS_A)

        fm.reserve_funds('OID-A', 700_000)
        _fill(om, _order(OrderType.BUY, KEY_A, 'OID-A'))        # 주문=폴더키
        _fill(om, _order(OrderType.SELL, CLS_A, 'OID-S'))       # 주문=클래스명

        assert CODE not in fm.current_position_codes, \
            "표기 드리프트로 엔트리가 잔류했다 (슬롯 점유)"

    def test_two_owners_each_register_under_their_own_slot(self):
        """대칭: 두 소유자가 각자 자기 슬롯 표기로 등록된다."""
        fm, om, _made, _a, _b = _setup(CLS_A, CLS_B)
        fm.reserve_funds('OID-A', 700_000)
        fm.reserve_funds('OID-B', 700_000)

        _fill(om, _order(OrderType.BUY, KEY_A, 'OID-A'))
        _fill(om, _order(OrderType.BUY, KEY_B, 'OID-B'))

        assert (CODE, CLS_A) in fm._position_entries
        assert (CODE, CLS_B) in fm._position_entries

    def test_sell_releases_only_its_own_owner_under_drift(self):
        """대칭: 드리프트가 있어도 남의 보유는 안 지운다."""
        fm, om, _made, _a, _b = _setup(CLS_A, CLS_B)
        fm.add_position(CODE, CLS_A)
        fm.add_position(CODE, CLS_B)
        fm.invested_funds = 1_400_000

        _fill(om, _order(OrderType.SELL, KEY_A, 'OID-S'))   # 주문=폴더키

        assert (CODE, CLS_A) not in fm._position_entries
        assert (CODE, CLS_B) in fm._position_entries

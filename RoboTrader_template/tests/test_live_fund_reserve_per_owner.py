"""자금 예약 ID 가 소유 전략을 싣는지 — 2전략 대칭 회귀.

배경 (2026-08-14 실매매 전환 감사 Fix 4):
  `bot/trading_analyzer.py:146` 은 `_reserve_id = stock_code` 로 예약했다.
  `core/fund_manager.py:292-294` 는 같은 id 의 2차 예약을 거부하므로, 두
  전략이 같은 종목을 사려 하면 뒤에 온 쪽이 «자금 예약 실패 - 매수 스킵» 으로
  탈락한다. 페이퍼는 가상체결이 동기라 충돌 창이 사실상 0 이지만, 실전은
  주문 접수~예약 이전(transfer) 사이가 API 왕복(최대 35초)만큼 열려 있다.

  ⚠️ 기존 재키잉 기계(order_executor:83-86 `has_reservation` →
  :192 `_transfer_temp_reserve`)는 정상 동작이므로 **깨뜨리면 안 된다**.
  예약 키를 바꾸면 `has_reservation(stock_code)` 가 miss 해 2차 예약이
  생기고 1차가 영구 누수된다(BLOCKER #7 재발). 그래서 예약 측과 감지 측이
  **같은 함수**로 id 를 만들게 한다.

  검증은 예약 → 이전 → 확정/취소 전 구간에서 reserved_funds 가 새지 않는지
  까지 본다.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fund_manager import FundManager, make_reserve_id

KEY_A = 'rs_leader'
KEY_B = 'elder_ema_pullback'
CODE = '005930'


def _fm(initial=10_000_000):
    return FundManager(initial_funds=initial)


# ---------------------------------------------------------------------------
# 1. FundManager — 두 전략이 같은 종목을 각자 예약할 수 있다
# ---------------------------------------------------------------------------

class TestTwoStrategiesReserveSameCode:
    def test_both_owners_can_reserve_the_same_code(self):
        fm = _fm()
        id_a = make_reserve_id(CODE, KEY_A)
        id_b = make_reserve_id(CODE, KEY_B)

        ok_a = fm.reserve_funds(id_a, 1_000_000)
        ok_b = fm.reserve_funds(id_b, 1_000_000)

        # 대칭: A 가 잡았다 AND B 도 잡았다
        assert ok_a is True
        assert ok_b is True
        assert fm.reserved_funds == 2_000_000
        assert set(fm.order_reservations) == {id_a, id_b}

    def test_same_owner_same_code_is_still_rejected(self):
        """대칭: 진짜 중복(같은 전략·같은 종목)은 종전대로 거부."""
        fm = _fm()
        id_a = make_reserve_id(CODE, KEY_A)

        assert fm.reserve_funds(id_a, 1_000_000) is True
        assert fm.reserve_funds(id_a, 1_000_000) is False
        assert fm.reserved_funds == 1_000_000

    def test_cancelling_one_owner_leaves_the_other_intact(self):
        fm = _fm()
        id_a = make_reserve_id(CODE, KEY_A)
        id_b = make_reserve_id(CODE, KEY_B)
        fm.reserve_funds(id_a, 1_000_000)
        fm.reserve_funds(id_b, 1_000_000)

        fm.cancel_order(id_a)

        assert fm.has_reservation(id_a) is False
        assert fm.has_reservation(id_b) is True
        assert fm.reserved_funds == 1_000_000

    def test_reserve_id_without_owner_is_the_bare_code(self):
        """레거시(무기명) 호출은 종전 키를 그대로 쓴다 — 동작 불변."""
        assert make_reserve_id(CODE, "") == CODE
        assert make_reserve_id(CODE, None) == CODE
        assert make_reserve_id(CODE, KEY_A) != CODE


# ---------------------------------------------------------------------------
# 2. trading_analyzer 가 owner 를 예약 ID 에 싣는다
# ---------------------------------------------------------------------------

def _make_bot(is_virtual=True):
    bot = Mock()
    bot.trading_manager.get_stocks_by_state.return_value = []
    bot.trading_manager.get_trading_stock.return_value = None
    bot.trading_manager._change_stock_state = Mock()
    bot.db_manager.price_repo.get_daily_prices.return_value = pd.DataFrame({
        'date': [f'202401{i + 1:02d}' for i in range(25)],
        'close': [50000] * 25,
    })
    bot.strategies = {}
    bot.decision_engine.is_virtual_mode = is_virtual
    bot.decision_engine.analyze_buy_decision = AsyncMock(return_value=(
        True, '테스트 매수신호',
        {'buy_price': 50000, 'quantity': 10, 'max_buy_amount': 500000,
         'signal': None},
    ))
    bot.decision_engine.execute_virtual_buy = AsyncMock(return_value=True)
    bot.decision_engine.execute_real_buy = AsyncMock(return_value=True)
    bot.fund_manager.get_status.return_value = {
        'total_funds': 10_000_000, 'available_funds': 1_000_000}
    bot.fund_manager.get_max_buy_amount.return_value = 1_000_000
    bot.fund_manager.reserve_funds.return_value = True
    bot.intraday_manager.get_cached_current_price.return_value = None
    return bot


def _stock(owner):
    from core.models import TradingStock, StockState
    from utils.korean_time import now_kst
    return TradingStock(stock_code=CODE, stock_name='삼성전자',
                        state=StockState.SELECTED, selected_time=now_kst(),
                        owner_strategy_name=owner)


def _reserve_id_used(bot):
    return bot.fund_manager.reserve_funds.call_args[0][0]


class TestAnalyzerReserveIdCarriesOwner:
    @pytest.mark.parametrize('virtual', [True, False])
    def test_reserve_id_differs_between_owners(self, virtual):
        from bot.trading_analyzer import TradingAnalyzer

        bot_a = _make_bot(is_virtual=virtual)
        asyncio.run(TradingAnalyzer(bot_a).analyze_buy_decision(
            _stock(KEY_A), available_funds=1_000_000, strategy_name=KEY_A))
        bot_b = _make_bot(is_virtual=virtual)
        asyncio.run(TradingAnalyzer(bot_b).analyze_buy_decision(
            _stock(KEY_B), available_funds=1_000_000, strategy_name=KEY_B))

        id_a, id_b = _reserve_id_used(bot_a), _reserve_id_used(bot_b)
        assert id_a == make_reserve_id(CODE, KEY_A)
        assert id_b == make_reserve_id(CODE, KEY_B)
        assert id_a != id_b, "두 전략의 예약 ID 가 같으면 뒤에 온 쪽이 탈락한다"

    def test_confirm_and_cancel_use_the_same_id(self):
        """예약/확정/취소가 같은 키를 써야 reserved 가 새지 않는다."""
        from bot.trading_analyzer import TradingAnalyzer

        bot = _make_bot(is_virtual=True)
        asyncio.run(TradingAnalyzer(bot).analyze_buy_decision(
            _stock(KEY_A), available_funds=1_000_000, strategy_name=KEY_A))

        assert bot.fund_manager.confirm_order.call_args[0][0] == \
            make_reserve_id(CODE, KEY_A)

        bot2 = _make_bot(is_virtual=True)
        bot2.decision_engine.execute_virtual_buy = AsyncMock(return_value=False)
        asyncio.run(TradingAnalyzer(bot2).analyze_buy_decision(
            _stock(KEY_B), available_funds=1_000_000, strategy_name=KEY_B))

        assert bot2.fund_manager.cancel_order.call_args[0][0] == \
            make_reserve_id(CODE, KEY_B)


# ---------------------------------------------------------------------------
# 3. 예약 → 이전 → 확정/취소 전 구간에서 자금이 새지 않는다 (실전 경로)
# ---------------------------------------------------------------------------

def _order_manager(monkeypatch):
    from core.order_manager import OrderManager
    import config.market_hours as mh
    monkeypatch.setattr(mh.MarketHours, 'can_place_order',
                        staticmethod(lambda *a, **k: True))
    cb = Mock()
    cb.is_market_halted.return_value = False
    cb.is_vi_active.return_value = False
    monkeypatch.setattr(mh, 'get_circuit_breaker_state', lambda: cb)

    config = Mock()
    config.paper_trading = False
    config.order_management.buy_timeout_seconds = 300
    om = OrderManager(config=config, broker=Mock(),
                      telegram_integration=None, db_manager=None)
    om.telegram = None
    om._get_stock_name = Mock(return_value='삼성전자')
    return om


class TestReserveTransferLifecycle:
    def test_existing_reservation_is_transferred_not_duplicated(self, monkeypatch):
        """analyzer 가 잡아둔 owner-키 예약을 place_buy_order 가 «찾아서» 이전한다."""
        om = _order_manager(monkeypatch)
        fm = _fm()
        om.set_fund_manager(fm)
        om.broker.place_buy_order = Mock(return_value={
            'success': True, 'order_id': 'OID-A', 'message': '',
            'error_code': '', 'data': None})

        rid = make_reserve_id(CODE, KEY_A)
        assert fm.reserve_funds(rid, 700_000) is True

        asyncio.run(om.place_buy_order(CODE, 10, 70_000.0,
                                       owner_strategy=KEY_A))

        # 2차 예약이 생기지 않았다 = 누수 없음
        assert fm.reserved_funds == 700_000
        assert set(fm.order_reservations) == {'OID-A'}

    def test_other_owner_reservation_is_untouched_by_transfer(self, monkeypatch):
        """대칭: A 의 이전이 B 의 예약을 건드리지 않는다."""
        om = _order_manager(monkeypatch)
        fm = _fm()
        om.set_fund_manager(fm)
        om.broker.place_buy_order = Mock(return_value={
            'success': True, 'order_id': 'OID-A', 'message': '',
            'error_code': '', 'data': None})

        fm.reserve_funds(make_reserve_id(CODE, KEY_A), 700_000)
        fm.reserve_funds(make_reserve_id(CODE, KEY_B), 700_000)

        asyncio.run(om.place_buy_order(CODE, 10, 70_000.0,
                                       owner_strategy=KEY_A))

        assert fm.has_reservation(make_reserve_id(CODE, KEY_B)) is True
        assert fm.has_reservation('OID-A') is True
        assert fm.reserved_funds == 1_400_000

    def test_failed_order_releases_owners_reservation_only(self, monkeypatch):
        om = _order_manager(monkeypatch)
        fm = _fm()
        om.set_fund_manager(fm)
        om.broker.place_buy_order = Mock(return_value={
            'success': False, 'order_id': '', 'message': '거부',
            'error_code': 'X', 'data': None})

        fm.reserve_funds(make_reserve_id(CODE, KEY_A), 700_000)
        fm.reserve_funds(make_reserve_id(CODE, KEY_B), 700_000)

        oid = asyncio.run(om.place_buy_order(CODE, 10, 70_000.0,
                                             owner_strategy=KEY_A))

        assert oid is None
        assert fm.has_reservation(make_reserve_id(CODE, KEY_A)) is False
        assert fm.has_reservation(make_reserve_id(CODE, KEY_B)) is True
        assert fm.reserved_funds == 700_000

    def test_temp_reservation_id_carries_owner(self, monkeypatch):
        """analyzer 예약이 없을 때(가격정정 재주문 등) 만드는 임시 ID 도 owner 를 싣는다.

        임시 ID 는 `RESERVE-{code}-{초단위 timestamp}` 라 같은 초에 두 전략이
        들어오면 충돌한다. owner 를 넣어 그 창을 없앤다.
        """
        temp_ids = []

        def _capture(owner):
            om = _order_manager(monkeypatch)
            fm = _fm()
            real_reserve = fm.reserve_funds

            def _spy(order_id, amount, **kw):
                temp_ids.append(order_id)
                return real_reserve(order_id, amount, **kw)
            fm.reserve_funds = _spy
            om.set_fund_manager(fm)
            om.broker.place_buy_order = Mock(return_value={
                'success': True, 'order_id': f'OID-{owner}', 'message': '',
                'error_code': '', 'data': None})
            asyncio.run(om.place_buy_order(CODE, 10, 70_000.0,
                                           owner_strategy=owner))
            return fm

        fm_a = _capture(KEY_A)
        _capture(KEY_B)

        assert len(temp_ids) == 2
        assert KEY_A in temp_ids[0]
        assert KEY_B in temp_ids[1]
        assert temp_ids[0] != temp_ids[1]
        # 이전 완료 — 임시 키는 남지 않는다
        assert set(fm_a.order_reservations) == {f'OID-{KEY_A}'}

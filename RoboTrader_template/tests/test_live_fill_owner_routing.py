"""실매매 체결이 «진짜 소유 전략» 에게 라우팅되는지 — 2전략 대칭 회귀.

배경 (2026-08-14 실매매 전환 감사):
  전략 정체성은 서로 바꿔 쓸 수 없는 **세 개의 키**로 표기된다.
    - 폴더키   : 'rs_leader'          (strategies dict 의 키)
    - 클래스명 : 'RSLeaderStrategy'   (strategy.name 속성)
    - None
  `core/trading_context.py:64-67` 은 클래스명을 «dict 키로는 절대 사용 금지»
  라고 못박아 놓고, 정작 :528-530 이 매수 성공 직후
  `trading_stock.owner_strategy_name = self._current_strategy_name`(=클래스명)
  을 쓴다. 체결 시 그 값이 `OrderCompletionHandler._resolve_owner_strategy` 로
  넘어가는데 그 안의 조회는 `strategies_by_key`(=**폴더키** 맵)이라 항상 miss
  하고, 조용히 `self.strategy`(=config 첫 전략) 로 폴백했다.

  2전략 실매매에서의 결과:
    - 첫 전략이 유령 포지션을 받아 K/daily_trades 를 잠식
    - 진짜 owner 는 보유 사실을 모르므로 자기 청산(trail/max_hold/trend_flip)이
      영영 발동하지 않는다 = «자기 전략이 팔 수 없는 포지션»

  ⚠️ 이 경로는 프로덕션에서 한 번도 실행된 적이 없다(페이퍼는 pending_orders 를
  만들지 않아 실주문 코드가 0줄 실행). 그래서 «A 가 받았다» 단독 단언은 전략이
  1개일 때 깨진 구현에서도 통과한다. 모든 검증은 반드시 **2전략 대칭**
  (A 가 받았다 AND B 는 못 받았다)으로 한다.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.trading.order_completion_handler import OrderCompletionHandler
from core.trading.stock_state_manager import StockStateManager
from core.models import OrderType, StockState, TradingStock
from utils.korean_time import now_kst


# 폴더키 ≠ 클래스명 — 실제 배포 형상(rs_leader / RSLeaderStrategy)을 그대로 쓴다.
KEY_A, CLS_A = 'rs_leader', 'RSLeaderStrategy'
KEY_B, CLS_B = 'elder_ema_pullback', 'ElderEmaPullbackStrategy'


def _order(stock_code='005930', side=OrderType.BUY, order_id='ORD-1'):
    o = Mock()
    o.order_type = side
    o.order_id = order_id
    o.stock_code = stock_code
    o.quantity = 10
    o.get_filled_price.return_value = 70_000.0
    return o


def _strategies():
    """(A, B) — B 가 config 첫 전략(=레거시 폴백 대상)."""
    a = Mock(); a.name = CLS_A
    b = Mock(); b.name = CLS_B
    return a, b


def _handler(state_manager=None):
    om = Mock()
    om.config.paper_trading = False  # 실매매 경로
    h = OrderCompletionHandler(
        state_manager=state_manager or Mock(), order_manager=om)
    return h


def _wired_handler(state_manager=None):
    """main.py 배선 재현: self.strategy = 첫 전략(B), 맵은 폴더키."""
    h = _handler(state_manager)
    a, b = _strategies()
    h.set_strategy(b)                       # main.py:239 — config 첫 전략
    h.set_strategies({KEY_A: a, KEY_B: b})  # 폴더키 맵
    return h, a, b


class TestResolveOwnerByEitherNotation:
    """owner 표기가 폴더키든 클래스명이든 «진짜 owner» 에게만 간다."""

    def test_class_name_owner_routes_to_true_owner_not_first_strategy(self):
        """🔴 핵심: trading_context:529 가 쓰는 «클래스명» 으로도 해석돼야 한다."""
        h, a, b = _wired_handler()

        h._notify_strategy_order_filled(_order(), owner_name=CLS_A)

        a.on_order_filled.assert_called_once()
        b.on_order_filled.assert_not_called()

    def test_folder_key_owner_routes_to_true_owner(self):
        """복원 포지션(owner=폴더키) 경로도 대칭으로 유지."""
        h, a, b = _wired_handler()

        h._notify_strategy_order_filled(_order(), owner_name=KEY_A)

        a.on_order_filled.assert_called_once()
        b.on_order_filled.assert_not_called()

    def test_instance_wins_over_any_name(self):
        """인스턴스가 실려 오면 이름 표기를 아예 거치지 않는다."""
        h, a, b = _wired_handler()

        # 이름은 비어 있고(무기명 레거시 슬롯) 인스턴스만 있다.
        h._notify_strategy_order_filled(_order(), owner_name='', owner_strategy=a)

        a.on_order_filled.assert_called_once()
        b.on_order_filled.assert_not_called()

    def test_instance_wins_even_if_name_points_elsewhere(self):
        """이름과 인스턴스가 어긋나면 인스턴스(=실제 소유자)가 이긴다."""
        h, a, b = _wired_handler()

        h._notify_strategy_order_filled(
            _order(), owner_name=CLS_B, owner_strategy=a)

        a.on_order_filled.assert_called_once()
        b.on_order_filled.assert_not_called()


class TestUnresolvedOwnerNeverGuesses:
    """다전략에서 미해석 owner 는 «아무에게도» 통보하지 않는다."""

    def test_unresolved_owner_notifies_nobody_in_multi_strategy(self):
        h, a, b = _wired_handler()

        h._notify_strategy_order_filled(_order(), owner_name='ghost_strategy')

        a.on_order_filled.assert_not_called()
        b.on_order_filled.assert_not_called()

    def test_unresolved_owner_logs_error(self):
        h, a, b = _wired_handler()
        h.logger = Mock()

        h._notify_strategy_order_filled(_order(), owner_name='ghost_strategy')

        assert h.logger.error.called, "미해석 owner 는 조용히 넘어가면 안 된다"

    def test_single_strategy_fallback_preserved(self):
        """전략이 1개 이하면 모호성이 없으므로 레거시 폴백을 보존한다."""
        h = _handler()
        only = Mock(); only.name = CLS_A
        h.set_strategy(only)
        h.set_strategies({KEY_A: only})

        h._notify_strategy_order_filled(_order(), owner_name='ghost_strategy')

        only.on_order_filled.assert_called_once()


class TestRealEntryPointRouting:
    """진입점(on_order_filled)을 실제로 돌려 호출열을 단언한다.

    소스 문자열·내부 헬퍼 단독 호출은 «죽은 경로» 에서도 통과한 전례가 있어
    실제 StockStateManager 와 TradingStock 으로 배선한다.
    """

    def _positioned_pair(self):
        sm = StockStateManager()
        h, a, b = _wired_handler(sm)

        ts_a = TradingStock(
            stock_code='005930', stock_name='A종목',
            state=StockState.BUY_PENDING, selected_time=now_kst(),
            owner_strategy_name=CLS_A,   # 라이브 매수 후 표기 = 클래스명
        )
        ts_a.owner_strategy = a
        ts_a.current_order_id = 'ORD-A'
        ts_b = TradingStock(
            stock_code='000660', stock_name='B종목',
            state=StockState.BUY_PENDING, selected_time=now_kst(),
            owner_strategy_name=CLS_B,
        )
        ts_b.owner_strategy = b
        ts_b.current_order_id = 'ORD-B'
        sm.register_stock(ts_a)
        sm.register_stock(ts_b)
        return h, a, b, ts_a, ts_b

    def test_buy_fill_callback_routes_to_owner_only(self):
        h, a, b, ts_a, _ = self._positioned_pair()

        asyncio.run(h.on_order_filled(
            _order(stock_code='005930', order_id='ORD-A')))

        a.on_order_filled.assert_called_once()
        b.on_order_filled.assert_not_called()
        assert ts_a.state == StockState.POSITIONED

    def test_other_owners_fill_routes_to_the_other_owner_only(self):
        """대칭: 반대편 종목 체결은 B 에게만 간다."""
        h, a, b, _, ts_b = self._positioned_pair()

        asyncio.run(h.on_order_filled(
            _order(stock_code='000660', order_id='ORD-B')))

        b.on_order_filled.assert_called_once()
        a.on_order_filled.assert_not_called()
        assert ts_b.state == StockState.POSITIONED

    def test_sell_fill_callback_routes_to_owner_only(self):
        sm = StockStateManager()
        h, a, b = _wired_handler(sm)
        ts = TradingStock(
            stock_code='005930', stock_name='A종목',
            state=StockState.SELL_PENDING, selected_time=now_kst(),
            owner_strategy_name=CLS_A,
        )
        ts.owner_strategy = a
        ts.set_position(10, 60_000.0)
        ts.current_order_id = 'ORD-A'
        sm.register_stock(ts)

        asyncio.run(h.on_order_filled(
            _order(stock_code='005930', side=OrderType.SELL, order_id='ORD-A')))

        a.on_order_filled.assert_called_once()
        b.on_order_filled.assert_not_called()


class TestUnnamedOwnerDoesNotFallBack:
    """owner 표기가 «비어 있을» 때도 다전략에서는 추측하지 않는다.

    리뷰 R4: `if owner_name and self.strategies_by_key:` 가 ERROR·무통보 블록
    전체를 감싸고 있어, owner_name 이 ''/None 이면 그 블록을 통째로 건너뛰고
    `return self.strategy` 로 떨어졌다 — ERROR 한 줄 없는 조용한 오귀속이다.

    도달 경로: 복원 슬롯은 owner_strategy_name 만 세팅하고 owner_strategy
    (인스턴스)는 세팅하지 않으므로, DB 라벨이 공백인 행이 그대로 여기로 온다.
    """

    def test_blank_owner_notifies_nobody_in_multi_strategy(self):
        h, a, b = _wired_handler()

        h._notify_strategy_order_filled(_order(), owner_name='')

        a.on_order_filled.assert_not_called()
        b.on_order_filled.assert_not_called()

    def test_none_owner_notifies_nobody_in_multi_strategy(self):
        h, a, b = _wired_handler()

        h._notify_strategy_order_filled(_order(), owner_name=None)

        a.on_order_filled.assert_not_called()
        b.on_order_filled.assert_not_called()

    def test_blank_owner_logs_error(self):
        h, _a, _b = _wired_handler()
        h.logger = Mock()

        h._notify_strategy_order_filled(_order(), owner_name='')

        assert h.logger.error.called, "무기명 체결이 ERROR 없이 지나갔다"

    def test_blank_owner_still_falls_back_with_one_strategy(self):
        """대칭: 전략 1개면 모호성이 없으므로 레거시 폴백을 보존한다."""
        h = _handler()
        only = Mock(); only.name = CLS_A
        h.set_strategy(only)
        h.set_strategies({KEY_A: only})

        h._notify_strategy_order_filled(_order(), owner_name='')

        only.on_order_filled.assert_called_once()

    def test_blank_owner_with_instance_still_routes(self):
        """대칭: 인스턴스가 실려 있으면 이름이 없어도 정상 통보된다."""
        h, a, b = _wired_handler()

        h._notify_strategy_order_filled(_order(), owner_name='', owner_strategy=a)

        a.on_order_filled.assert_called_once()
        b.on_order_filled.assert_not_called()

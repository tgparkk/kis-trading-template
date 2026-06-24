"""OrderCompletionHandler 실매매 체결 콜백 owner 라우팅 회귀.

배경 (사전-실전 감사 BLOCKER #2, 2026-06-24):
  실매매 체결 콜백은 OrderCompletionHandler._notify_strategy_order_filled 가
  담당하는데, 고정된 self.strategy(=첫 전략, 보통 Elder)의 on_order_filled 만
  호출했다. owner-aware 라우팅(strategies_by_key)은 가상매매 경로(decision_engine)
  에만 적용되고 실매매 완료 핸들러엔 누락 → 실전에서 모든 전략의 체결이 Elder 의
  daily_trades/positions 를 오염(2026-06-11 매수 마비 재현) + 실제 owner 전략의
  self.positions 기반 청산(max_hold/trailing) 미발동.

  페이퍼 모드는 이 핸들러를 거치지 않아(가상 체결은 decision_engine 이 합성)
  결함이 가려져 있었다.

검증:
  1. 체결이 owner 전략에게 라우팅되고 첫 전략은 호출되지 않는다.
  2. owner 미해석 시 self.strategy(레거시 단일전략)로 폴백한다.
"""
import sys
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.trading.order_completion_handler import OrderCompletionHandler
from core.models import OrderType


def _order(stock_code='005930', side=OrderType.BUY):
    o = Mock()
    o.order_type = side
    o.order_id = 'ORD-1'
    o.stock_code = stock_code
    o.quantity = 10
    o.get_filled_price.return_value = 70_000.0
    return o


def _handler():
    return OrderCompletionHandler(state_manager=Mock(), order_manager=Mock())


class TestOwnerRouting:
    def test_fill_routed_to_owner_not_first_strategy(self):
        h = _handler()
        strat_a = Mock(); strat_a.name = 'stratA'
        strat_b = Mock(); strat_b.name = 'stratB'
        h.set_strategy(strat_a)  # 레거시 단일(첫 전략) 연결
        h.set_strategies({'stratA': strat_a, 'stratB': strat_b})

        h._notify_strategy_order_filled(_order(), owner_name='stratB')

        strat_b.on_order_filled.assert_called_once()
        strat_a.on_order_filled.assert_not_called()

    def test_unresolved_owner_falls_back_to_single_strategy(self):
        h = _handler()
        strat_a = Mock(); strat_a.name = 'stratA'
        h.set_strategy(strat_a)
        h.set_strategies({'stratA': strat_a})

        h._notify_strategy_order_filled(_order(), owner_name='unknown')

        strat_a.on_order_filled.assert_called_once()

    def test_no_map_uses_legacy_single_strategy(self):
        """strategies_by_key 미설정(레거시) — 종전대로 self.strategy 호출."""
        h = _handler()
        strat_a = Mock(); strat_a.name = 'stratA'
        h.set_strategy(strat_a)

        h._notify_strategy_order_filled(_order(), owner_name='stratA')

        strat_a.on_order_filled.assert_called_once()

"""프레임워크 공통 트레일링 — 전략-소유 포지션 게이트 (2026-06-24, 사장님 결정).

배경:
  core/trading/position_monitor.py 의 _analyze_sell_for_stock 는 모든 보유종목에
  공통 트레일링 스톱(+5% 활성화 → 최고가 -3% 시 매도)을 적용했고, 이 트레일링은
  전략별 익절(tp)·손절(sl)보다 우선순위가 높았다(stale>max_holding>trailing>tp>sl).
  결과적으로 전략별 손익비(멀티버스 백테스트로 검증한 tp/sl·고유 청산)가 라이브에서
  공통 트레일링에 의해 선점됐다(특히 고tp Elder).

결정:
  "전략별 손익비가 더 우선" — 전략-소유 포지션(owner_strategy 또는 self._strategy 가
  governing)에는 공통 트레일링을 적용하지 않고, 전략의 tp/sl/max_hold/고유 청산이
  governing 하도록 한다(멀티버스 정합). 비전략(레거시) 포지션은 종전대로 트레일링 유지.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from strategies.base import BaseStrategy


def _make_trading_stock(avg_price=10_000, highest=11_000, days_held=0):
    from core.models import TradingStock, StockState, Position
    ts = TradingStock(
        stock_code="005930", stock_name="테스트",
        state=StockState.POSITIONED, selected_time=datetime.now(),
    )
    ts.position = Position(stock_code="005930", quantity=10, avg_price=avg_price)
    ts.is_selling = False
    ts.trailing_stop_activated = False
    ts.highest_price_since_buy = highest
    ts.target_profit_rate = None      # tp 블록 비활성
    ts.stop_loss_rate = None          # sl 블록 비활성
    ts.days_held = days_held
    ts.is_stale = False
    return ts


def _make_position_monitor():
    from core.trading.position_monitor import PositionMonitor
    pm = PositionMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    pm._paper_trading = True
    pm.fund_manager = MagicMock()
    pm.fund_manager.is_sell_cooldown_active = MagicMock(return_value=False)
    pm.decision_engine = AsyncMock()
    # 전략 매도신호 경로가 간섭하지 않도록 장중데이터 없음
    pm.data_collector.get_stock = MagicMock(return_value=None)
    return pm


def _make_strategy(max_days=100):
    class _Stub(BaseStrategy):
        name = "StubSwing"
        holding_period = "swing"

        def generate_signal(self, stock_code, data, timeframe="daily"):
            return None
    s = _Stub()
    s.max_holding_days = max_days
    return s


async def _run(pm, ts, current_price):
    reasons = []

    async def capture_sell(trading_stock, price, reason):
        reasons.append(reason)
        trading_stock.is_selling = False

    with patch.object(pm, '_execute_sell', side_effect=capture_sell):
        with patch.object(pm, '_get_current_price', new_callable=AsyncMock,
                          return_value=current_price):
            await pm._analyze_sell_for_stock(ts)
    return reasons


# current=10,500 / avg=10,000 → +5% 활성화, 최고가 11,000 → 트레일선 10,670,
# 10,500 <= 10,670 → 종전 코드라면 트레일링 매도 발동.

class TestFrameworkTrailingStrategyGate:
    @pytest.mark.asyncio
    async def test_strategy_owned_position_skips_framework_trailing(self):
        """전략-소유 포지션은 공통 트레일링으로 매도하지 않는다(전략 손익비 우선)."""
        pm = _make_position_monitor()
        pm._strategy = _make_strategy(max_days=100)  # strategy_for_sell 존재
        ts = _make_trading_stock()

        reasons = await _run(pm, ts, current_price=10_500.0)

        assert not any("트레일링" in r for r in reasons), (
            f"전략-소유 포지션은 공통 트레일링 매도 금지여야 함. 실제: {reasons}")
        assert reasons == [], f"트레일링 외 트리거 없어 매도 0건이어야 함. 실제: {reasons}"

    @pytest.mark.asyncio
    async def test_legacy_position_still_uses_framework_trailing(self):
        """비전략(레거시) 포지션은 종전대로 공통 트레일링이 작동한다(회귀)."""
        pm = _make_position_monitor()
        pm._strategy = None            # strategy_for_sell = None (레거시)
        ts = _make_trading_stock()
        ts.owner_strategy = None

        reasons = await _run(pm, ts, current_price=10_500.0)

        assert any("트레일링" in r for r in reasons), (
            f"레거시 포지션은 공통 트레일링이 발동해야 함. 실제: {reasons}")

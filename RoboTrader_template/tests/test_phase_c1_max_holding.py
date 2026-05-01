"""
Phase C1: max_holding_days 프레임워크 통합 테스트
================================================

C1: BaseStrategy.max_holding_days + PositionMonitor 트리거 + BacktestEngine 시뮬

테스트 목록:
- test_max_holding_days_triggers_sell: days_held >= max → 매도
- test_max_holding_days_none_no_trigger: None이면 시간 청산 없음
- test_max_holding_priority_below_stop_loss: 손절이 동시 충족 시 손절 우선
- test_backtest_engine_max_holding_sim: 백테스트에서 max_holding 사유로 매도
- test_backtest_engine_max_holding_priority_over_take_profit: max_holding은 take_profit보다 우선
- test_backtest_engine_max_holding_none_no_trigger: max_holding_days=None이면 미발동
- test_momentum_max_holding_days_set: MomentumStrategy가 프레임워크 속성 사용
"""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from strategies.base import BaseStrategy, Signal, SignalType


# ============================================================================
# 헬퍼
# ============================================================================

def _make_trading_stock(stock_code: str = "005930", avg_price: float = 10_000,
                        days_held: int = 0):
    """TradingStock with Position — days_held 속성도 주입."""
    from core.models import TradingStock, StockState, Position
    ts = TradingStock(
        stock_code=stock_code,
        stock_name="테스트",
        state=StockState.POSITIONED,
        selected_time=datetime.now(),
    )
    ts.position = Position(stock_code=stock_code, quantity=10, avg_price=avg_price)
    ts.is_selling = False
    ts.trailing_stop_activated = False
    ts.highest_price_since_buy = avg_price
    ts.target_profit_rate = None
    ts.stop_loss_rate = None
    ts.days_held = days_held
    ts.is_stale = False
    return ts


def _make_position_monitor():
    """의존성 전부 Mock인 PositionMonitor 생성."""
    from core.trading.position_monitor import PositionMonitor
    pm = PositionMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    pm._paper_trading = True
    pm.fund_manager = MagicMock()
    pm.fund_manager.is_sell_cooldown_active = MagicMock(return_value=False)
    return pm


def _make_strategy_with_max_holding(max_days: "int | None"):
    """max_holding_days가 설정된 최소 전략 스텁."""
    class _Stub(BaseStrategy):
        name = "StubSwing"
        holding_period = "swing"

        def generate_signal(self, stock_code, data, timeframe="daily"):
            return None

    s = _Stub()
    s.max_holding_days = max_days
    return s


# ============================================================================
# BacktestEngine 헬퍼
# ============================================================================

def _make_ohlcv(dates, closes=None, highs=None, lows=None):
    n = len(dates)
    closes = closes or [10_000] * n
    highs = highs or closes
    lows = lows or closes
    return pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [100_000] * n,
    })


def _make_engine(strategy, **kwargs):
    from backtest.engine import BacktestEngine
    defaults = dict(
        initial_capital=1_000_000,
        max_positions=1,
        position_size_pct=1.0,
        commission_rate=0.0,
        tax_rate=0.0,
    )
    defaults.update(kwargs)
    return BacktestEngine(strategy=strategy, **defaults)


class _BuyOnceSwing(BaseStrategy):
    """첫 날 매수, 이후 신호 없음 — 리스크/시간 청산에만 의존."""
    name = "BuyOnceSwing"
    holding_period = "swing"

    def get_min_data_length(self) -> int:
        return 1

    def generate_signal(self, stock_code, data, timeframe="daily"):
        if stock_code not in self.positions:
            return Signal(signal_type=SignalType.BUY, stock_code=stock_code,
                          confidence=90, reasons=["test"])
        return None


# ============================================================================
# C1-A: PositionMonitor max_holding_days 트리거 테스트
# ============================================================================

class TestMaxHoldingDaysPositionMonitor:
    """PositionMonitor._analyze_sell_for_stock에서 max_holding_days 트리거 검증."""

    @pytest.mark.asyncio
    async def test_max_holding_days_triggers_sell(self):
        """days_held >= max_holding_days → 매도 실행."""
        pm = _make_position_monitor()
        strategy = _make_strategy_with_max_holding(max_days=5)
        pm._strategy = strategy

        # days_held=5, 한도=5 → 트리거
        ts = _make_trading_stock(days_held=5)

        mock_engine = AsyncMock()
        mock_engine.execute_virtual_sell = AsyncMock(return_value=True)
        pm.decision_engine = mock_engine

        sold_reason = {}

        async def capture_sell(trading_stock, price, reason):
            sold_reason['reason'] = reason
            trading_stock.is_selling = False

        with patch.object(pm, '_execute_sell', side_effect=capture_sell):
            with patch.object(pm, '_get_current_price', new_callable=AsyncMock,
                              return_value=10_100.0):
                await pm._analyze_sell_for_stock(ts)

        assert 'reason' in sold_reason, "매도가 실행되어야 함"
        assert "5일 초과" in sold_reason['reason']
        assert "한도: 5일" in sold_reason['reason']

    @pytest.mark.asyncio
    async def test_max_holding_days_not_reached_no_sell(self):
        """days_held < max_holding_days → 시간 청산 안 함."""
        pm = _make_position_monitor()
        strategy = _make_strategy_with_max_holding(max_days=10)
        pm._strategy = strategy

        ts = _make_trading_stock(days_held=4)
        pm.decision_engine = AsyncMock()

        sell_called = []

        async def capture_sell(trading_stock, price, reason):
            sell_called.append(reason)

        with patch.object(pm, '_execute_sell', side_effect=capture_sell):
            with patch.object(pm, '_get_current_price', new_callable=AsyncMock,
                              return_value=10_100.0):
                await pm._analyze_sell_for_stock(ts)

        # max_holding 사유 매도는 없어야 함
        for r in sell_called:
            assert "초과" not in r or "장기보유" in r

    @pytest.mark.asyncio
    async def test_max_holding_days_none_no_trigger(self):
        """max_holding_days=None이면 시간 청산 없음."""
        pm = _make_position_monitor()
        strategy = _make_strategy_with_max_holding(max_days=None)
        pm._strategy = strategy

        ts = _make_trading_stock(days_held=100)
        pm.decision_engine = AsyncMock()

        sell_called = []

        async def capture_sell(trading_stock, price, reason):
            sell_called.append(reason)

        with patch.object(pm, '_execute_sell', side_effect=capture_sell):
            with patch.object(pm, '_get_current_price', new_callable=AsyncMock,
                              return_value=10_100.0):
                await pm._analyze_sell_for_stock(ts)

        # max_holding 사유 매도 없음
        for r in sell_called:
            assert "초과" not in r or "장기보유" in r

    @pytest.mark.asyncio
    async def test_max_holding_priority_over_stop_loss(self):
        """max_holding이 stop_loss_rate보다 우선 실행됨.

        실제 우선순위: stale > max_holding > trailing > stop_loss_rate
        days_held=5(한도=5)이면 stop_loss_rate 도달 여부와 무관하게 max_holding이 먼저 트리거.
        """
        pm = _make_position_monitor()
        strategy = _make_strategy_with_max_holding(max_days=5)
        pm._strategy = strategy

        # stop_loss_rate 설정: avg_price=10000, current=9000 → profit_rate=-10%
        ts = _make_trading_stock(avg_price=10_000, days_held=5)
        ts.stop_loss_rate = 0.05  # 5% 손절 조건도 동시에 충족
        pm.decision_engine = AsyncMock()

        sell_reasons = []

        async def capture_sell(trading_stock, price, reason):
            sell_reasons.append(reason)
            trading_stock.is_selling = False

        with patch.object(pm, '_execute_sell', side_effect=capture_sell):
            with patch.object(pm, '_get_current_price', new_callable=AsyncMock,
                              return_value=9_000.0):  # -10% → 손절 조건도 충족
                await pm._analyze_sell_for_stock(ts)

        assert len(sell_reasons) == 1, "매도는 1회만 실행돼야 함"
        # max_holding이 stop_loss_rate보다 먼저 체크되므로 "초과" 사유여야 함
        assert "초과" in sell_reasons[0], (
            f"max_holding이 우선 실행돼야 함 (실제 우선순위: stale>max_holding>trailing>stop_loss). "
            f"실제: {sell_reasons[0]}"
        )


# ============================================================================
# C1-B: BacktestEngine max_holding_days 시뮬 테스트
# ============================================================================

class TestBacktestEngineMaxHolding:
    """BacktestEngine.run() 에서 max_holding_days 매도 시뮬 검증."""

    def test_backtest_engine_max_holding_sim(self):
        """max_holding_days=3, 4일째 → max_holding 매도."""
        strategy = _BuyOnceSwing()
        strategy.max_holding_days = 3
        strategy._stop_loss_pct = 0.50   # 손절 안 걸리게
        strategy._take_profit_pct = 2.00  # 익절 안 걸리게
        engine = _make_engine(strategy)

        # Day1: 매수, Day2+3: 보유, Day4: 3일 초과 → max_holding
        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            closes=[10_000] * 4,
        )

        result = engine.run(["A"], {"A": data})

        assert result.sells_by_reason.get("max_holding", 0) >= 1, (
            f"max_holding 매도 기대. sells_by_reason={result.sells_by_reason}"
        )

    def test_backtest_engine_max_holding_none_no_trigger(self):
        """max_holding_days=None이면 EOD 없는 swing 전략은 강제청산까지 보유."""
        strategy = _BuyOnceSwing()
        strategy.max_holding_days = None
        strategy._stop_loss_pct = 0.50
        strategy._take_profit_pct = 2.00
        engine = _make_engine(strategy)

        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            closes=[10_000] * 4,
        )

        result = engine.run(["A"], {"A": data})

        assert result.sells_by_reason.get("max_holding", 0) == 0, (
            f"max_holding=None이면 시간 청산 없어야 함. sells={result.sells_by_reason}"
        )
        # 강제청산(forced_exit)으로 종료돼야 함
        assert result.sells_by_reason.get("forced_exit", 0) == 1

    def test_backtest_engine_max_holding_stop_loss_priority(self):
        """max_holding_days=1 이지만 손절이 동일 봉에서 먼저 트리거 → stop_loss 우선."""
        strategy = _BuyOnceSwing()
        strategy.max_holding_days = 1  # 1일 뒤 트리거
        strategy._stop_loss_pct = 0.05   # 5% 손절
        strategy._take_profit_pct = 2.00  # 익절 안 걸리게
        engine = _make_engine(strategy)

        entry_price = 10_000
        stop_price = entry_price * 0.95  # 9,500

        # Day1: 매수, Day2: low=9,499 (손절 도달, 또한 1일 초과)
        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03"],
            closes=[entry_price, entry_price - 100],
            highs=[entry_price, entry_price],
            lows=[entry_price, stop_price - 1],
        )

        result = engine.run(["A"], {"A": data})

        # 손절이 max_holding보다 우선 (우선순위 1 < 3)
        assert result.sells_by_reason.get("stop_loss", 0) >= 1, (
            f"손절 우선 기대. sells={result.sells_by_reason}"
        )
        assert result.sells_by_reason.get("max_holding", 0) == 0


# ============================================================================
# C1-C: MomentumStrategy 프레임워크 위임 검증
# ============================================================================

class TestMomentumMaxHoldingDelegation:
    """MomentumStrategy가 self.max_holding_days를 BaseStrategy 속성으로 설정하는지."""

    def test_momentum_max_holding_days_set_from_config(self):
        """config에 max_holding_days=7 설정 시 전략 속성에 반영."""
        from strategies.momentum.strategy import MomentumStrategy
        cfg = {
            "parameters": {"max_holding_days": 7},
            "risk_management": {},
        }
        s = MomentumStrategy(config=cfg)
        s.on_init(MagicMock(), MagicMock(), MagicMock())
        assert s.max_holding_days == 7

    def test_momentum_max_holding_days_default(self):
        """config 없을 때 기본값 10."""
        from strategies.momentum.strategy import MomentumStrategy
        s = MomentumStrategy()
        s.on_init(MagicMock(), MagicMock(), MagicMock())
        assert s.max_holding_days == 10

    def test_momentum_sell_signal_holding_days_reason(self):
        """_check_sell이 holding_days >= max_holding_days 시 SELL 반환.

        generate_signal 직접 호출 경로(테스트/결정엔진)에서도 동작해야 하므로
        전략 내부에 보유기간 초과 체크가 있어야 함.
        프레임워크(PositionMonitor/BacktestEngine)는 추가 안전망으로도 동작.
        """
        from strategies.momentum.strategy import MomentumStrategy
        s = MomentumStrategy()
        s.on_init(MagicMock(), MagicMock(), MagicMock())
        s.positions["005930"] = {
            "entry_price": 10_000,
            "entry_time": datetime.now() - timedelta(days=20),
            "holding_days": 20,  # max_holding_days 기본값 10 초과
        }

        data = pd.DataFrame({
            "close": [10_000] * 10,
            "high": [10_000] * 10,
            "low": [10_000] * 10,
        })

        signal = s._check_sell("005930", 10_000.0, data)
        # holding_days=20 >= max_holding_days=10 → SELL 반환
        assert signal is not None, "보유기간 초과 시 SELL 신호 반환해야 함"
        assert signal.is_sell
        assert any("보유기간 초과" in r for r in signal.reasons)

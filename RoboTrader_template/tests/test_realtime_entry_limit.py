"""실시간 체결가 + 전략별 진입 지정가 밴드 (2026-06-15 설계).

근본 버그: 페이퍼 매수가 실시간가 미확보 시 '마지막 확정 일봉 종가'로 체결을
날조 → 갭/상한가 종목에서 허수 이익(079650 +597K, 06-15). 매도(position_monitor)는
온디맨드 실시간가를 정확히 받으므로 비대칭.

해결:
  A. 매수도 실시간가만 신뢰. 미확보 시 일봉종가 fallback 삭제 → 진입 보류(다음 틱 재시도).
  B. Signal에 진입 밴드(entry_min_price/entry_max_price) 신설. 실시간가가 밴드 밖이면 스킵
     (지정가 주문 의미론). 눌림목=기준가 이하, 돌파=트리거~+N%.
"""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
import pytest

from core.models import TradingStock, StockState
from strategies.base import Signal, SignalType


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def engine():
    with patch('core.trading_decision_engine.setup_logger'), \
         patch('core.virtual_trading_manager.setup_logger'):
        from core.trading_decision_engine import TradingDecisionEngine
        e = TradingDecisionEngine(
            db_manager=Mock(),
            telegram_integration=None,
            trading_manager=None,
            broker=None,
            config=Mock(paper_trading=True),
        )
    e.check_market_direction = Mock(return_value=(False, ""))
    return e


@pytest.fixture
def daily_data():
    periods = 30
    base = datetime(2026, 6, 1, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    closes = [1500.0 + 10 * i for i in range(periods)]  # 마지막 종가 1790
    return pd.DataFrame({
        'datetime': [base + timedelta(days=i) for i in range(periods)],
        'open': closes,
        'high': [c * 1.01 for c in closes],
        'low': [c * 0.99 for c in closes],
        'close': closes,
        'volume': [100000] * periods,
    })


def _live_price_manager(price):
    """온디맨드 실시간가를 반환하는 intraday_manager 목."""
    im = Mock()
    im.get_current_price_for_sell.return_value = {'current_price': price}
    im.get_cached_current_price.return_value = {'current_price': price}
    return im


def _buy_owner_signal(min_price=None, max_price=None):
    return Signal(
        signal_type=SignalType.BUY,
        stock_code="079650",
        confidence=68.0,
        reasons=["breakout_prev_high"],
        entry_min_price=min_price,
        entry_max_price=max_price,
    )


# ---------------------------------------------------------------------------
# Phase 1: Signal 진입 밴드 필드
# ---------------------------------------------------------------------------
class TestSignalEntryBandFields:
    def test_signal_accepts_entry_band(self):
        sig = Signal(
            signal_type=SignalType.BUY,
            stock_code="079650",
            entry_min_price=1653.0,
            entry_max_price=1736.0,
        )
        assert sig.entry_min_price == 1653.0
        assert sig.entry_max_price == 1736.0

    def test_entry_band_defaults_none(self):
        sig = Signal(signal_type=SignalType.BUY, stock_code="005930")
        assert sig.entry_min_price is None
        assert sig.entry_max_price is None


# ---------------------------------------------------------------------------
# Phase 2: 엔진 — 실시간가만 신뢰(미확보 시 보류) + 진입 밴드 검증
# ---------------------------------------------------------------------------
class TestEngineLivePriceEntry:
    def _stock(self):
        return TradingStock(stock_code="079650", stock_name="079650",
                            state=StockState.SELECTED, selected_time=datetime.now())

    def test_no_live_price_defers_entry(self, engine, daily_data):
        """실시간가 미확보(캐시/브로커 전부 None) → 일봉종가 날조 대신 진입 보류."""
        engine.intraday_manager = None
        engine.broker = None
        engine.virtual_trading = None
        engine.fund_manager = Mock()
        engine.fund_manager.get_max_buy_amount.return_value = 500000

        ok, reason, info = _run(engine.analyze_buy_decision(
            self._stock(), daily_data, owner_signal=_buy_owner_signal()))

        assert ok is False, "실시간가 없으면 체결하지 않고 보류해야 함"
        assert "보류" in reason or "미확보" in reason
        assert info['buy_price'] == 0

    def test_fills_at_live_price_not_daily_close(self, engine, daily_data):
        """온디맨드 실시간가(1700)로 체결 — 일봉 마지막 종가(1790)가 아니라."""
        engine.intraday_manager = Mock()
        engine.intraday_manager.get_current_price_for_sell.return_value = {'current_price': 1700}
        engine.intraday_manager.get_cached_current_price.return_value = None
        engine.broker = None
        engine.virtual_trading = None
        engine.fund_manager = Mock()
        engine.fund_manager.get_max_buy_amount.return_value = 500000

        ok, reason, info = _run(engine.analyze_buy_decision(
            self._stock(), daily_data, owner_signal=_buy_owner_signal()))

        assert ok is True
        assert info['buy_price'] == 1700, f"실시간가 1700으로 체결해야 함 (일봉 1790 아님), got {info['buy_price']}"

    def test_live_price_above_band_skips(self, engine, daily_data):
        """실시간가가 진입 밴드 상한 초과(갭/추격) → 스킵."""
        engine.intraday_manager = _live_price_manager(2195)
        engine.broker = None
        engine.virtual_trading = None
        engine.fund_manager = Mock()
        engine.fund_manager.get_max_buy_amount.return_value = 500000

        ok, reason, info = _run(engine.analyze_buy_decision(
            self._stock(), daily_data,
            owner_signal=_buy_owner_signal(max_price=1736)))

        assert ok is False, "밴드 상한 초과 시 스킵해야 함"
        assert "밴드" in reason or "이탈" in reason

    def test_live_price_below_band_skips(self, engine, daily_data):
        """실시간가가 진입 밴드 하한 미만 → 스킵."""
        engine.intraday_manager = _live_price_manager(1500)
        engine.broker = None
        engine.virtual_trading = None
        engine.fund_manager = Mock()
        engine.fund_manager.get_max_buy_amount.return_value = 500000

        ok, reason, info = _run(engine.analyze_buy_decision(
            self._stock(), daily_data,
            owner_signal=_buy_owner_signal(min_price=1650)))

        assert ok is False, "밴드 하한 미만 시 스킵해야 함"
        assert "밴드" in reason or "하회" in reason

    def test_live_price_within_band_fills(self, engine, daily_data):
        """실시간가가 밴드 안 → 실시간가로 체결."""
        engine.intraday_manager = _live_price_manager(1700)
        engine.broker = None
        engine.virtual_trading = None
        engine.fund_manager = Mock()
        engine.fund_manager.get_max_buy_amount.return_value = 500000

        ok, reason, info = _run(engine.analyze_buy_decision(
            self._stock(), daily_data,
            owner_signal=_buy_owner_signal(min_price=1650, max_price=1750)))

        assert ok is True
        assert info['buy_price'] == 1700

    def test_079650_limit_up_regression(self, engine, daily_data):
        """06-15 회귀: 상한가 락 2195가 돌파 밴드(트리거~+N%) 상단을 넘으면 스킵.
        허수 +597K의 원천(스테일 1690 진입 + 2195 청산) 차단."""
        engine.intraday_manager = _live_price_manager(2195)
        engine.broker = None
        engine.virtual_trading = None
        engine.fund_manager = Mock()
        engine.fund_manager.get_max_buy_amount.return_value = 500000

        # breakout: 트리거 1653, +5% 추격한도 → 상한 약 1736
        ok, reason, info = _run(engine.analyze_buy_decision(
            self._stock(), daily_data,
            owner_signal=_buy_owner_signal(min_price=1653, max_price=1736)))

        assert ok is False, "상한가 락(+30%)은 추격 한도를 넘으므로 스킵돼야 함"


# ---------------------------------------------------------------------------
# Phase 3: BaseStrategy._entry_band 헬퍼 (전략별 밴드 산출 공통화)
# ---------------------------------------------------------------------------
class TestEntryBandHelper:
    def _strat(self):
        from strategies.base import BaseStrategy

        class _Dummy(BaseStrategy):
            name = "dummy"

            def generate_signal(self, stock_code, data, timeframe='daily'):
                return None

        return _Dummy(config={})

    def test_band_both_sides(self):
        lo, hi = self._strat()._entry_band(1000.0, down_pct=0.05, up_pct=0.03)
        assert lo == pytest.approx(950.0)
        assert hi == pytest.approx(1030.0)

    def test_band_up_only(self):
        """돌파형: 하한 없음(None), 상한만 추격 한도."""
        lo, hi = self._strat()._entry_band(1690.0, down_pct=None, up_pct=0.03)
        assert lo is None
        assert hi == pytest.approx(1740.7)

    def test_band_down_only(self):
        """눌림형: 상한=기준가(추격 금지), 하한만."""
        lo, hi = self._strat()._entry_band(1000.0, down_pct=0.08, up_pct=0.0)
        assert lo == pytest.approx(920.0)
        assert hi == pytest.approx(1000.0)

    def test_band_invalid_ref_returns_none(self):
        assert self._strat()._entry_band(0, down_pct=0.05, up_pct=0.05) == (None, None)
        assert self._strat()._entry_band(None, down_pct=0.05, up_pct=0.05) == (None, None)

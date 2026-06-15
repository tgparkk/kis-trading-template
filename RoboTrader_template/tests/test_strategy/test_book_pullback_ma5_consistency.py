"""
Book Pullback MA5 (트레이딩의 전설 Book15) 실전 전략 ↔ 백테스트 룰 일치 검증
============================================================================

신규 실전 전략(strategies/book_pullback_ma5)의 진입/청산 판단이
백테스트 검증판(strategies/books/trading_legends/rules_daily.py
rule_ma5_pullback)과 동일한지 검증.

핵심 검증:
  1. evaluate_entry()가 백테스트 rule_ma5_pullback.evaluate()와
     동일한 triggered 결과를 낸다 (trigger/no-trigger 여러 합성 시점).
  2. generate_signal() 분기: 보유→매도, 미보유 daily→매수, intraday→None.
  3. config 로드 (StrategyLoader).
  4. 청산 우선순위(sl→tp→max_hold→trail_ma) 동작 — 특히 sl=-3% 타이트 확인.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.books.trading_legends.rules_daily import _ma, rule_ma5_pullback
from strategies.book_pullback_ma5.strategy import BookPullbackMa5Strategy


# ----------------------------------------------------------------------------- #
# 합성 일봉 생성기 — 결정론적
# ----------------------------------------------------------------------------- #
def _make_df(closes, highs=None, lows=None, opens=None):
    closes = list(closes)
    if highs is None:
        highs = [c * 1.01 for c in closes]
    if lows is None:
        lows = [c * 0.99 for c in closes]
    if opens is None:
        opens = list(closes)
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2025-01-01", periods=n, freq="D"),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1_000_000] * n,
    })


def _surge_pull_closes():
    """급등(+25%) 후 5일선 부근으로 회귀하는 종가 시퀀스.

    seg(직전 20봉)에 급등 고점(12500)과 조정 저점이 함께 들어가
    _recent_surge(+20%)를 만족시킨다.
    """
    base = [10000.0] * 8
    surge = list(np.linspace(10000, 12500, 8))    # +25% 급등
    pull = list(np.linspace(12500, 11600, 14))    # 조정 → 5일선 부근
    return base + surge + pull


def _ma5_pullback_df():
    """급등 후 5일선 눌림 지지 양봉 형태 (진입 트리거 기대)."""
    df = _make_df(_surge_pull_closes())
    ma5 = _ma(df, 5)
    df.loc[df.index[-1], "low"] = ma5 * 1.005
    df.loc[df.index[-1], "open"] = ma5 * 1.005
    df.loc[df.index[-1], "close"] = ma5 * 1.02
    df.loc[df.index[-1], "high"] = ma5 * 1.03
    return df


def _no_surge_df():
    """급등 이력 없는 완만한 횡보 (surge 실패 → 진입 없음 기대)."""
    closes = list(np.linspace(10000, 10200, 30))  # +2% 미미
    df = _make_df(closes)
    ma5 = _ma(df, 5)
    df.loc[df.index[-1], "low"] = ma5 * 1.005
    df.loc[df.index[-1], "open"] = ma5 * 1.005
    df.loc[df.index[-1], "close"] = ma5 * 1.02
    df.loc[df.index[-1], "high"] = ma5 * 1.03
    return df


def _no_touch_df():
    """급등은 있으나 마지막 봉이 5일선과 멀리 떨어져 터치 실패 (진입 없음)."""
    df = _make_df(_surge_pull_closes())
    ma5 = _ma(df, 5)
    df.loc[df.index[-1], "low"] = ma5 * 1.15
    df.loc[df.index[-1], "open"] = ma5 * 1.16
    df.loc[df.index[-1], "close"] = ma5 * 1.20
    df.loc[df.index[-1], "high"] = ma5 * 1.21
    return df


# ----------------------------------------------------------------------------- #
# 1. 진입 신호 일치: 실전 evaluate_entry ↔ 백테스트 rule
# ----------------------------------------------------------------------------- #
class TestEntrySignalConsistency:

    @pytest.mark.parametrize("df_factory", [
        _ma5_pullback_df,
        _no_surge_df,
        _no_touch_df,
    ])
    def test_entry_matches_backtest_rule(self, df_factory):
        """실전 evaluate_entry의 triggered가 백테스트 rule.evaluate와 동일."""
        df = df_factory()
        rule = rule_ma5_pullback()
        backtest_res = rule.evaluate(df, {})

        live_triggered, live_reasons, live_meta = BookPullbackMa5Strategy.evaluate_entry(
            df, min_daily_bars=25
        )

        assert live_triggered == backtest_res.triggered, (
            f"진입 불일치: live={live_triggered} backtest={backtest_res.triggered} "
            f"(form={df_factory.__name__})"
        )
        if backtest_res.triggered:
            assert live_reasons == list(backtest_res.reasons)
            assert live_meta == dict(backtest_res.metadata)

    def test_pullback_triggers(self):
        """급등+5일선 눌림 지지 양봉은 반드시 진입 트리거."""
        df = _ma5_pullback_df()
        triggered, _, meta = BookPullbackMa5Strategy.evaluate_entry(df)
        assert triggered is True
        assert "ma5" in meta

    def test_no_surge_no_entry(self):
        """급등 이력 없으면 진입 없음."""
        df = _no_surge_df()
        triggered, _, _ = BookPullbackMa5Strategy.evaluate_entry(df)
        assert triggered is False

    def test_insufficient_bars_no_entry(self):
        """min_daily_bars 미만이면 진입 없음."""
        df = _make_df(list(np.linspace(10000, 12500, 15)))
        triggered, _, _ = BookPullbackMa5Strategy.evaluate_entry(df, min_daily_bars=25)
        assert triggered is False


# ----------------------------------------------------------------------------- #
# 2. 청산 우선순위 일치 — 특히 sl=-3% 타이트
# ----------------------------------------------------------------------------- #
class TestSellConditionConsistency:

    def _trend_df(self, last_close=None):
        # 완만한 상승 추세 → 종가가 5일선 위 (trail 미발동 보장)
        closes = list(np.linspace(10000, 13000, 30))
        if last_close is not None:
            closes[-1] = last_close
        return _make_df(closes)

    def test_stop_loss_tight_3pct(self):
        """-3% 이하면 stop_loss (타이트 손절 — ma5 핵심 특성)."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 0.96  # 현재가 -4%
        sell, _, reason = BookPullbackMa5Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5,
        )
        assert sell is True
        assert reason == "stop_loss"

    def test_stop_loss_boundary_minus2pct_no_sell(self):
        """-2%는 sl 미충족(임계 -3% 확인)."""
        df = self._trend_df()
        cur = float(df["close"].iloc[-1])
        ma5 = _ma(df, 5)
        assert cur >= ma5  # trail 미발동 전제
        entry = cur / 0.98  # -2%
        sell, _, reason = BookPullbackMa5Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5, max_hold_days=30,
        )
        assert sell is False
        assert reason == ""

    def test_take_profit(self):
        """+15% 이상이면 take_profit."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 1.18  # +18%
        sell, _, reason = BookPullbackMa5Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5,
        )
        assert sell is True
        assert reason == "take_profit"

    def test_max_hold(self):
        """보유 거래일이 max_hold_days 이상이면 max_hold."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 1.05  # +5% (tp 미충족)
        sell, _, reason = BookPullbackMa5Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=30, max_hold_days=30,
        )
        assert sell is True
        assert reason == "max_hold"

    def test_trail_ma_only_in_profit(self):
        """수익 중(ret>0) 종가가 5일선 아래면 trail_ma 청산."""
        closes = list(np.linspace(10000, 13000, 29))
        closes += [13000 * 0.96]  # 마지막 봉 급락 → 5일선 밑 (단 -3% sl 안 걸리게 entry 조정)
        df = _make_df(closes)
        cur = float(df["close"].iloc[-1])
        ma5 = _ma(df, 5)
        assert cur < ma5  # 전제
        entry = cur / 1.02  # 여전히 +2% 수익 (sl -3% 미충족)
        sell, _, reason = BookPullbackMa5Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5, trail_ma=5,
        )
        assert sell is True
        assert reason == "trail_ma"

    def test_priority_sl_over_max_hold(self):
        """sl이 max_hold보다 먼저 평가."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 0.80  # -20%
        sell, _, reason = BookPullbackMa5Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=200, max_hold_days=30,
        )
        assert reason == "stop_loss"


# ----------------------------------------------------------------------------- #
# 3. generate_signal 분기 + StrategyLoader
# ----------------------------------------------------------------------------- #
class TestStrategyLoaderIntegration:

    def test_loader_discovers_strategy(self, monkeypatch):
        from strategies.config import StrategyLoader
        monkeypatch.chdir(ROOT)
        discovered = StrategyLoader.discover_strategies()
        assert "book_pullback_ma5" in discovered

    def test_loader_loads_strategy(self, monkeypatch):
        from strategies.config import StrategyLoader
        monkeypatch.chdir(ROOT)
        strat = StrategyLoader.load_strategy("book_pullback_ma5")
        assert strat.__class__.__name__ == "BookPullbackMa5Strategy"
        assert strat.holding_period == "swing"
        risk = strat.config.get("risk_management", {})
        assert risk["take_profit_pct"] == 0.15
        assert risk["stop_loss_pct"] == 0.03
        assert risk["max_hold_days"] == 30
        assert risk["trail_ma"] == 5

    def _build(self, monkeypatch):
        monkeypatch.setattr(
            "strategies.book_pullback_ma5.strategy.MarketHours.is_market_open",
            staticmethod(lambda market="KRX": True),
        )
        strat = BookPullbackMa5Strategy({
            "parameters": {"min_daily_bars": 25},
            "risk_management": {
                "take_profit_pct": 0.15, "stop_loss_pct": 0.03,
                "max_hold_days": 30, "trail_ma": 5,
            },
            "paper_trading": True,
        })
        strat.on_init(broker=None, data_provider=None, executor=None)
        return strat

    def test_generate_signal_buy_on_pullback(self, monkeypatch):
        """미보유+daily+눌림 형태 → BUY (target/stop 비율 확인)."""
        from strategies.base import SignalType
        strat = self._build(monkeypatch)
        df = _ma5_pullback_df()
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is not None
        assert sig.signal_type == SignalType.BUY
        cur = float(df["close"].iloc[-1])
        assert abs(sig.target_price - cur * 1.15) < 1.0
        assert abs(sig.stop_loss - cur * 0.97) < 1.0  # -3% 타이트 손절

    def test_generate_signal_intraday_no_buy(self, monkeypatch):
        """미보유 종목은 intraframe(분봉)에서 신규 진입 안 함."""
        strat = self._build(monkeypatch)
        df = _ma5_pullback_df()
        sig = strat.generate_signal("005930", df, timeframe="minute")
        assert sig is None

    def test_generate_signal_sell_branch_for_holding(self, monkeypatch):
        """보유 종목은 매도 분기로 진입(타이트 -3% 손절 발동)."""
        from strategies.base import SignalType
        strat = self._build(monkeypatch)
        df = _make_df(list(np.linspace(10000, 13000, 30)))
        cur = float(df["close"].iloc[-1])
        strat.positions["005930"] = {
            "quantity": 10, "entry_price": cur / 0.95, "entry_time": None,  # -5%
        }
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is not None
        assert sig.signal_type == SignalType.SELL
        assert sig.metadata["exit_reason"] == "stop_loss"


# ----------------------------------------------------------------------------- #
# 4. 진입 밴드 (2026-06-15) — 눌림형: up=0%, down=stop_loss_pct(0.03)
# ----------------------------------------------------------------------------- #
class TestEntryBand:

    def _build(self, monkeypatch):
        monkeypatch.setattr(
            "strategies.book_pullback_ma5.strategy.MarketHours.is_market_open",
            staticmethod(lambda market="KRX": True),
        )
        strat = BookPullbackMa5Strategy({
            "parameters": {"min_daily_bars": 25},
            "risk_management": {
                "take_profit_pct": 0.15, "stop_loss_pct": 0.03,
                "max_hold_days": 30, "trail_ma": 5,
            },
            "paper_trading": False,
        })
        strat.on_init(broker=None, data_provider=None, executor=None)
        return strat

    def test_buy_signal_has_pullback_band(self, monkeypatch):
        """BUY 신호에 눌림형 밴드(max=cur, min=cur*(1-0.03))가 담긴다."""
        strat = self._build(monkeypatch)
        df = _ma5_pullback_df()
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is not None
        from strategies.base import SignalType
        assert sig.signal_type == SignalType.BUY
        cur = float(df["close"].iloc[-1])
        sl = 0.03
        assert sig.entry_max_price == pytest.approx(cur * 1.01)  # 눌림형 +1% 여유
        assert sig.entry_min_price == pytest.approx(cur * (1 - sl))

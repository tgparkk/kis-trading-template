"""
Book Pullback MA20 (강창권 A-07) 실전 전략 ↔ 백테스트 룰 일치 검증
=================================================================

신규 실전 전략(strategies/book_pullback_ma20)의 진입/청산 판단이
백테스트 검증판(strategies/books/haru_silijeon/rules_daily.py
rule_daily_ma20_pullback)과 동일한지 검증.

핵심 검증:
  1. evaluate_entry()가 백테스트 rule_daily_ma20_pullback.evaluate()와
     동일한 triggered 결과를 낸다 (trigger/no-trigger 여러 합성 시점).
  2. generate_signal() 분기: 보유→매도, 미보유 daily→매수, intraday→None.
  3. config 로드 (StrategyLoader).
  4. 청산 우선순위(sl→tp→max_hold→trail_ma) 동작.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.books.haru_silijeon.rules_daily import _ma, rule_daily_ma20_pullback
from strategies.book_pullback_ma20.strategy import BookPullbackMa20Strategy


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
    """급등(+50%) 후 깊은 조정 → 20일선 부근 회귀하는 종가 시퀀스.

    seg(직전 30봉)에 급등 고점(15000)과 조정 저점(~11800)이 함께 들어가
    _recent_surge(+25%)를 만족시킨다.
    """
    base = [10000.0] * 8
    surge = list(np.linspace(10000, 15000, 8))    # +50% 급등
    pull = list(np.linspace(15000, 11800, 33))    # 깊은 조정 → 20일선 부근
    return base + surge + pull


def _ma20_pullback_df():
    """급등 후 20일선 눌림 지지 양봉 형태 (진입 트리거 기대)."""
    df = _make_df(_surge_pull_closes())
    ma20 = _ma(df, 20)
    # 마지막 봉: 저가가 20일선 터치, 종가는 20일선 위, 양봉(close>open)
    df.loc[df.index[-1], "low"] = ma20 * 1.005
    df.loc[df.index[-1], "open"] = ma20 * 1.005
    df.loc[df.index[-1], "close"] = ma20 * 1.025
    df.loc[df.index[-1], "high"] = ma20 * 1.03
    return df


def _no_surge_df():
    """급등 이력 없는 완만한 횡보 (surge 실패 → 진입 없음 기대)."""
    closes = list(np.linspace(10000, 10200, 49))  # +2% 미미
    df = _make_df(closes)
    ma20 = _ma(df, 20)
    df.loc[df.index[-1], "low"] = ma20 * 1.005
    df.loc[df.index[-1], "open"] = ma20 * 1.005
    df.loc[df.index[-1], "close"] = ma20 * 1.025
    df.loc[df.index[-1], "high"] = ma20 * 1.03
    return df


def _no_touch_df():
    """급등은 있으나 마지막 봉이 20일선과 멀리 떨어져 터치 실패 (진입 없음)."""
    df = _make_df(_surge_pull_closes())
    ma20 = _ma(df, 20)
    # 저가를 20일선보다 한참 위로 → 터치 실패
    df.loc[df.index[-1], "low"] = ma20 * 1.15
    df.loc[df.index[-1], "open"] = ma20 * 1.16
    df.loc[df.index[-1], "close"] = ma20 * 1.20
    df.loc[df.index[-1], "high"] = ma20 * 1.21
    return df


# ----------------------------------------------------------------------------- #
# 1. 진입 신호 일치: 실전 evaluate_entry ↔ 백테스트 rule
# ----------------------------------------------------------------------------- #
class TestEntrySignalConsistency:

    @pytest.mark.parametrize("df_factory", [
        _ma20_pullback_df,
        _no_surge_df,
        _no_touch_df,
    ])
    def test_entry_matches_backtest_rule(self, df_factory):
        """실전 evaluate_entry의 triggered가 백테스트 rule.evaluate와 동일."""
        df = df_factory()
        rule = rule_daily_ma20_pullback()
        backtest_res = rule.evaluate(df, {})

        live_triggered, live_reasons, live_meta = BookPullbackMa20Strategy.evaluate_entry(
            df, min_daily_bars=35
        )

        assert live_triggered == backtest_res.triggered, (
            f"진입 불일치: live={live_triggered} backtest={backtest_res.triggered} "
            f"(form={df_factory.__name__})"
        )
        if backtest_res.triggered:
            assert live_reasons == list(backtest_res.reasons)
            assert live_meta == dict(backtest_res.metadata)

    def test_pullback_triggers(self):
        """급등+20일선 눌림 지지 양봉은 반드시 진입 트리거."""
        df = _ma20_pullback_df()
        triggered, _, meta = BookPullbackMa20Strategy.evaluate_entry(df)
        assert triggered is True
        assert "ma20" in meta

    def test_no_surge_no_entry(self):
        """급등 이력 없으면 진입 없음."""
        df = _no_surge_df()
        triggered, _, _ = BookPullbackMa20Strategy.evaluate_entry(df)
        assert triggered is False

    def test_insufficient_bars_no_entry(self):
        """min_daily_bars 미만이면 진입 없음."""
        df = _make_df(list(np.linspace(10000, 14000, 20)))
        triggered, _, _ = BookPullbackMa20Strategy.evaluate_entry(df, min_daily_bars=35)
        assert triggered is False


# ----------------------------------------------------------------------------- #
# 2. 청산 우선순위 일치
# ----------------------------------------------------------------------------- #
class TestSellConditionConsistency:

    def _trend_df(self, last_close=None):
        # 완만한 상승 추세 → 종가가 20일선 위 (trail 미발동 보장)
        closes = list(np.linspace(10000, 14000, 49))
        if last_close is not None:
            closes[-1] = last_close
        return _make_df(closes)

    def test_stop_loss_first(self):
        """-8% 이하면 stop_loss (최우선)."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 0.90  # 현재가 -10%
        sell, _, reason = BookPullbackMa20Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5,
        )
        assert sell is True
        assert reason == "stop_loss"

    def test_take_profit(self):
        """+10% 이상이면 take_profit (A-07 익절)."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 1.12  # 현재가 +12%
        sell, _, reason = BookPullbackMa20Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5,
        )
        assert sell is True
        assert reason == "take_profit"

    def test_take_profit_threshold_is_10pct(self):
        """+9%는 tp 미충족(임계 +10% 확인)."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 1.09  # +9%
        sell, _, reason = BookPullbackMa20Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5, max_hold_days=50,
        )
        # tp 미충족 → trail_ma 또는 no-sell (max_hold 미충족)
        assert reason != "take_profit"

    def test_max_hold(self):
        """보유 거래일이 max_hold_days 이상이면 max_hold."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 1.05  # +5% (tp 미충족)
        sell, _, reason = BookPullbackMa20Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=50, max_hold_days=50,
        )
        assert sell is True
        assert reason == "max_hold"

    def test_trail_ma_only_in_profit(self):
        """수익 중(ret>0) 종가가 20일선 아래면 trail_ma 청산."""
        closes = list(np.linspace(10000, 15000, 16))
        closes += list(np.linspace(15000, 12200, 32))
        closes += [12200 * 0.93]  # 마지막 봉 급락 → 20일선 밑
        df = _make_df(closes)
        cur = float(df["close"].iloc[-1])
        ma20 = _ma(df, 20)
        assert cur < ma20  # 전제
        entry = cur / 1.02  # 여전히 +2% 수익
        sell, _, reason = BookPullbackMa20Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5, trail_ma=20,
        )
        assert sell is True
        assert reason == "trail_ma"

    def test_no_sell_when_holding(self):
        """sl/tp/max_hold/trail 모두 미충족이면 매도 없음."""
        df = self._trend_df()
        cur = float(df["close"].iloc[-1])
        ma20 = _ma(df, 20)
        # 종가가 20일선 위여야 trail 미발동
        assert cur >= ma20
        entry = cur / 1.05  # +5%
        sell, _, reason = BookPullbackMa20Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5, max_hold_days=50,
        )
        assert sell is False
        assert reason == ""

    def test_priority_sl_over_max_hold(self):
        """sl이 max_hold보다 먼저 평가."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 0.80  # -20%
        sell, _, reason = BookPullbackMa20Strategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=200, max_hold_days=50,
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
        assert "book_pullback_ma20" in discovered

    def test_loader_loads_strategy(self, monkeypatch):
        from strategies.config import StrategyLoader
        monkeypatch.chdir(ROOT)
        strat = StrategyLoader.load_strategy("book_pullback_ma20")
        assert strat.__class__.__name__ == "BookPullbackMa20Strategy"
        assert strat.holding_period == "swing"
        risk = strat.config.get("risk_management", {})
        assert risk["take_profit_pct"] == 0.10
        assert risk["stop_loss_pct"] == 0.08
        assert risk["max_hold_days"] == 50
        assert risk["trail_ma"] == 20

    def _build(self, monkeypatch):
        monkeypatch.setattr(
            "strategies.book_pullback_ma20.strategy.MarketHours.is_market_open",
            staticmethod(lambda market="KRX": True),
        )
        strat = BookPullbackMa20Strategy({
            "parameters": {"min_daily_bars": 35},
            "risk_management": {
                "take_profit_pct": 0.10, "stop_loss_pct": 0.08,
                "max_hold_days": 50, "trail_ma": 20,
            },
            "paper_trading": True,
        })
        strat.on_init(broker=None, data_provider=None, executor=None)
        return strat

    def test_generate_signal_buy_on_pullback(self, monkeypatch):
        """미보유+daily+눌림 형태 → BUY (target/stop 비율 확인)."""
        from strategies.base import SignalType
        strat = self._build(monkeypatch)
        df = _ma20_pullback_df()
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is not None
        assert sig.signal_type == SignalType.BUY
        cur = float(df["close"].iloc[-1])
        assert abs(sig.target_price - cur * 1.10) < 1.0
        assert abs(sig.stop_loss - cur * 0.92) < 1.0

    def test_generate_signal_intraday_no_buy(self, monkeypatch):
        """미보유 종목은 intraframe(분봉)에서 신규 진입 안 함."""
        strat = self._build(monkeypatch)
        df = _ma20_pullback_df()
        sig = strat.generate_signal("005930", df, timeframe="minute")
        assert sig is None

    def test_generate_signal_sell_branch_for_holding(self, monkeypatch):
        """보유 종목은 매도 분기로 진입(손절 발동)."""
        from strategies.base import SignalType
        strat = self._build(monkeypatch)
        df = self._trend_df_for_sell()
        cur = float(df["close"].iloc[-1])
        strat.positions["005930"] = {
            "quantity": 10, "entry_price": cur / 0.90, "entry_time": None,
        }
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is not None
        assert sig.signal_type == SignalType.SELL
        assert sig.metadata["exit_reason"] == "stop_loss"

    def _trend_df_for_sell(self):
        closes = list(np.linspace(10000, 14000, 18))
        closes += list(np.linspace(14000, 13000, 22))
        return _make_df(closes)


# ----------------------------------------------------------------------------- #
# 4. 진입 밴드 (2026-06-15) — 눌림형: up=0%, down=stop_loss_pct(0.08)
# ----------------------------------------------------------------------------- #
def test_exit_timeframe_daily():
    # 일봉 swing 전략 — 분봉 청산 whipsaw 방지 (2026-06-18 점검). intraday 상속 회귀 방지.
    assert BookPullbackMa20Strategy.exit_timeframe == "daily"


class TestEntryBand:

    def _build(self, monkeypatch):
        monkeypatch.setattr(
            "strategies.book_pullback_ma20.strategy.MarketHours.is_market_open",
            staticmethod(lambda market="KRX": True),
        )
        strat = BookPullbackMa20Strategy({
            "parameters": {"min_daily_bars": 35},
            "risk_management": {
                "take_profit_pct": 0.10, "stop_loss_pct": 0.08,
                "max_hold_days": 50, "trail_ma": 20,
            },
            "paper_trading": False,
        })
        strat.on_init(broker=None, data_provider=None, executor=None)
        return strat

    def test_buy_signal_has_pullback_band(self, monkeypatch):
        """BUY 신호에 눌림형 밴드(max=cur, min=cur*(1-0.08))가 담긴다."""
        strat = self._build(monkeypatch)
        df = _ma20_pullback_df()
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is not None
        from strategies.base import SignalType
        assert sig.signal_type == SignalType.BUY
        cur = float(df["close"].iloc[-1])
        sl = 0.08
        assert sig.entry_max_price == pytest.approx(cur * 1.01)  # 눌림형 +1% 여유
        assert sig.entry_min_price == pytest.approx(cur * (1 - sl))

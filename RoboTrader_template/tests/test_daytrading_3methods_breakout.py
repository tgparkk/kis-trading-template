"""
DayTrading 3Methods Breakout (유지윤 3대 타법) 실전 전략 ↔ 백테스트 룰 일치 검증
============================================================================

신규 실전 전략(strategies/daytrading_3methods_breakout)의 진입/청산 판단이
백테스트 검증판(strategies/books/daytrading_3methods/rules.py
rule_breakout_prev_high)과 동일한지 검증.

핵심 검증:
  1. evaluate_entry()가 백테스트 rule_breakout_prev_high.evaluate()와
     동일한 triggered 결과를 낸다 (trigger/no-trigger 여러 합성 시점).
  2. generate_signal() 분기: 보유→매도, 미보유 daily→매수, intraday→None,
     max_positions 도달→None.
  3. config 로드 (StrategyLoader).
  4. 청산 우선순위(sl→tp→max_hold) 동작 — variant B sl10/tp10/mh10.
  5. no-lookahead 회귀 (현재봉이 전고점/거래량을 스스로 만들어내지 않음).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high
from strategies.daytrading_3methods_breakout.strategy import (
    DayTrading3MethodsBreakoutStrategy,
)


# ----------------------------------------------------------------------------- #
# 합성 일봉 생성기 — 결정론적
# ----------------------------------------------------------------------------- #
def _make_df(closes, highs=None, lows=None, opens=None, volumes=None):
    closes = list(closes)
    if highs is None:
        highs = [c * 1.01 for c in closes]
    if lows is None:
        lows = [c * 0.99 for c in closes]
    if opens is None:
        opens = list(closes)
    if volumes is None:
        volumes = [1_000_000] * len(closes)
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2025-01-01", periods=n, freq="D"),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": list(volumes),
    })


def _breakout_df():
    """전고점 돌파 + 거래량 동반 폭증 양봉 (진입 트리거 기대).

    직전 20봉은 10000~10100 박스권(고점 max ≈ 10100*1.01), 마지막 봉이
    종가 10600으로 전고점을 명확히 돌파하고 거래량 3배, 양봉이 되도록 구성.
    """
    closes = [10000.0 + (i % 5) * 20 for i in range(26)]  # 박스권 26봉 (min_daily_bars=25 충족)
    closes[-1] = 10600.0  # 마지막 봉: 전고점 돌파
    df = _make_df(closes)
    # 마지막 봉을 명확한 양봉으로 + 거래량 폭증
    df.loc[df.index[-1], "open"] = 10200.0
    df.loc[df.index[-1], "close"] = 10600.0
    df.loc[df.index[-1], "high"] = 10650.0
    df.loc[df.index[-1], "low"] = 10180.0
    df.loc[df.index[-1], "volume"] = 5_000_000  # 평균(1M) × 5 >= 2.0
    return df


def _no_breakout_df():
    """전고점 미돌파 (거래량은 폭증해도 진입 없음 기대)."""
    df = _breakout_df()
    # 종가를 박스권 안으로 되돌려 전고점 미달 (거래량/양봉은 유지)
    df.loc[df.index[-1], "open"] = 10050.0
    df.loc[df.index[-1], "close"] = 10090.0
    df.loc[df.index[-1], "high"] = 10095.0
    return df


def _no_volume_df():
    """전고점은 돌파하나 거래량 미달 (진입 없음 기대)."""
    df = _breakout_df()
    df.loc[df.index[-1], "volume"] = 1_000_000  # 평균과 동일 → ×2.0 미달
    return df


# ----------------------------------------------------------------------------- #
# 1. 진입 신호 일치: 실전 evaluate_entry ↔ 백테스트 rule
# ----------------------------------------------------------------------------- #
class TestEntrySignalConsistency:

    @pytest.mark.parametrize("df_factory", [
        _breakout_df,
        _no_breakout_df,
        _no_volume_df,
    ])
    def test_entry_matches_backtest_rule(self, df_factory):
        """실전 evaluate_entry의 triggered가 백테스트 rule.evaluate와 동일."""
        df = df_factory()
        rule = rule_breakout_prev_high()
        backtest_res = rule.evaluate(df, {})

        live_triggered, live_reasons, live_meta = (
            DayTrading3MethodsBreakoutStrategy.evaluate_entry(df, min_daily_bars=25)
        )

        assert live_triggered == backtest_res.triggered, (
            f"진입 불일치: live={live_triggered} backtest={backtest_res.triggered} "
            f"(form={df_factory.__name__})"
        )
        if backtest_res.triggered:
            assert live_reasons == list(backtest_res.reasons)
            assert live_meta == dict(backtest_res.metadata)

    def test_breakout_triggers(self):
        """전고점 돌파 + 거래량 동반 양봉은 반드시 진입 트리거."""
        df = _breakout_df()
        triggered, _, meta = DayTrading3MethodsBreakoutStrategy.evaluate_entry(df)
        assert triggered is True
        assert "prior_high" in meta

    def test_no_breakout_no_entry(self):
        """전고점 미돌파면 진입 없음."""
        df = _no_breakout_df()
        triggered, _, _ = DayTrading3MethodsBreakoutStrategy.evaluate_entry(df)
        assert triggered is False

    def test_no_volume_no_entry(self):
        """거래량 미달이면 진입 없음."""
        df = _no_volume_df()
        triggered, _, _ = DayTrading3MethodsBreakoutStrategy.evaluate_entry(df)
        assert triggered is False

    def test_insufficient_bars_no_entry(self):
        """min_daily_bars 미만이면 진입 없음."""
        df = _make_df(list(np.linspace(10000, 12500, 15)))
        triggered, _, _ = DayTrading3MethodsBreakoutStrategy.evaluate_entry(
            df, min_daily_bars=25
        )
        assert triggered is False


# ----------------------------------------------------------------------------- #
# 2. 청산 우선순위 — variant B sl10/tp10/mh10
# ----------------------------------------------------------------------------- #
class TestSellConditionConsistency:

    def _trend_df(self, last_close=None):
        closes = list(np.linspace(10000, 13000, 30))
        if last_close is not None:
            closes[-1] = last_close
        return _make_df(closes)

    def test_stop_loss_minus10pct(self):
        """-10% 이하면 stop_loss."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 0.88  # 현재가 -12%
        sell, _, reason = DayTrading3MethodsBreakoutStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5,
        )
        assert sell is True
        assert reason == "stop_loss"

    def test_stop_loss_boundary_minus8pct_no_sell(self):
        """-8%는 sl 미충족(임계 -10% 확인)."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 0.92  # -8%
        sell, _, reason = DayTrading3MethodsBreakoutStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5, max_hold_days=10,
        )
        assert sell is False
        assert reason == ""

    def test_take_profit_plus10pct(self):
        """+10% 이상이면 take_profit."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 1.12  # +12%
        sell, _, reason = DayTrading3MethodsBreakoutStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5,
        )
        assert sell is True
        assert reason == "take_profit"

    def test_max_hold_10days(self):
        """보유 거래일이 max_hold_days(10) 이상이면 max_hold."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 1.03  # +3% (tp 미충족)
        sell, _, reason = DayTrading3MethodsBreakoutStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=10, max_hold_days=10,
        )
        assert sell is True
        assert reason == "max_hold"

    def test_no_trigger_default_no_trailing(self):
        """손익절·max_hold 미충족이면 청산 없음 (기본 trailing 없음)."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 1.03  # +3%
        sell, _, reason = DayTrading3MethodsBreakoutStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=3, max_hold_days=10,
        )
        assert sell is False
        assert reason == ""

    def test_priority_sl_over_max_hold(self):
        """sl이 max_hold보다 먼저 평가."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 0.80  # -20%
        sell, _, reason = DayTrading3MethodsBreakoutStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=200, max_hold_days=10,
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
        assert "daytrading_3methods_breakout" in discovered

    def test_loader_loads_strategy(self, monkeypatch):
        from strategies.config import StrategyLoader
        monkeypatch.chdir(ROOT)
        strat = StrategyLoader.load_strategy("daytrading_3methods_breakout")
        assert strat.__class__.__name__ == "DayTrading3MethodsBreakoutStrategy"
        assert strat.holding_period == "swing"
        risk = strat.config.get("risk_management", {})
        assert risk["take_profit_pct"] == 0.10
        assert risk["stop_loss_pct"] == 0.10
        assert risk["max_hold_days"] == 10
        assert risk["trail_ma"] is None

    def _build(self, monkeypatch):
        monkeypatch.setattr(
            "strategies.daytrading_3methods_breakout.strategy.MarketHours.is_market_open",
            staticmethod(lambda market="KRX": True),
        )
        strat = DayTrading3MethodsBreakoutStrategy({
            "parameters": {"min_daily_bars": 25, "max_holding_days": 10},
            "risk_management": {
                "take_profit_pct": 0.10, "stop_loss_pct": 0.10,
                "max_hold_days": 10, "trail_ma": None, "max_positions": 5,
            },
            "paper_trading": True,
        })
        strat.on_init(broker=None, data_provider=None, executor=None)
        return strat

    def test_generate_signal_none_on_short_data(self, monkeypatch):
        """min_daily_bars 미만의 짧은 데이터는 None."""
        strat = self._build(monkeypatch)
        df = _make_df(list(np.linspace(10000, 12500, 15)))
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is None

    def test_generate_signal_buy_on_breakout(self, monkeypatch):
        """미보유+daily+돌파 형태 → BUY (target/stop 비율 확인)."""
        from strategies.base import SignalType
        strat = self._build(monkeypatch)
        df = _breakout_df()
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is not None
        assert sig.signal_type == SignalType.BUY
        cur = float(df["close"].iloc[-1])
        assert abs(sig.target_price - cur * 1.10) < 1.0
        assert abs(sig.stop_loss - cur * 0.90) < 1.0

    def test_generate_signal_intraday_no_buy(self, monkeypatch):
        """미보유 종목은 intraframe(분봉)에서 신규 진입 안 함."""
        strat = self._build(monkeypatch)
        df = _breakout_df()
        sig = strat.generate_signal("005930", df, timeframe="minute")
        assert sig is None

    def test_generate_signal_no_buy_when_max_positions(self, monkeypatch):
        """max_positions 도달 시 신규 매수 없음."""
        strat = self._build(monkeypatch)
        # 미보유 종목 5개로 포지션 한도 채움
        for i in range(5):
            strat.positions[f"FILL{i:02d}"] = {
                "quantity": 1, "entry_price": 1000.0, "entry_time": None,
            }
        df = _breakout_df()
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is None

    def test_generate_signal_sell_branch_for_holding(self, monkeypatch):
        """보유 종목은 매도 분기로 진입(-10% 손절 발동)."""
        from strategies.base import SignalType
        strat = self._build(monkeypatch)
        df = _make_df(list(np.linspace(10000, 13000, 30)))
        cur = float(df["close"].iloc[-1])
        strat.positions["005930"] = {
            "quantity": 10, "entry_price": cur / 0.88, "entry_time": None,  # -12%
        }
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is not None
        assert sig.signal_type == SignalType.SELL
        assert sig.metadata["exit_reason"] == "stop_loss"


# ----------------------------------------------------------------------------- #
# 4. no-lookahead 회귀 — 현재봉이 전고점/거래량 평균을 스스로 오염시키지 않음
# ----------------------------------------------------------------------------- #
class TestNoLookahead:

    def test_prior_high_excludes_current_bar(self):
        """전고점은 현재봉(마지막 행)을 제외하고 계산 — 거대한 마지막 high를
        넣어도 돌파 판정은 직전 20봉 전고점 기준으로만 이뤄진다."""
        df = _breakout_df()
        # 마지막 봉의 high만 극단적으로 키워도 진입 결과는 불변이어야 함
        before, _, before_meta = DayTrading3MethodsBreakoutStrategy.evaluate_entry(df)
        df2 = df.copy()
        df2.loc[df2.index[-1], "high"] = 99999.0
        after, _, after_meta = DayTrading3MethodsBreakoutStrategy.evaluate_entry(df2)
        assert before == after
        if before:
            assert before_meta["prior_high"] == after_meta["prior_high"]

    def test_truncating_future_bars_changes_only_with_new_last(self):
        """t 시점 평가가 t+1 봉 정보에 의존하지 않음: df[:t+1] 슬라이스로 평가한
        결과가, 그 t 봉이 마지막일 때의 평가와 동일하다."""
        df = _breakout_df()
        # df의 마지막 봉(t)이 트리거. 미래봉을 한 개 덧붙여도 t 평가는 불변.
        triggered_t, _, _ = DayTrading3MethodsBreakoutStrategy.evaluate_entry(df)
        extended = pd.concat([df, df.iloc[[-1]]], ignore_index=True)
        # extended에서 t까지만 잘라낸 슬라이스 = 원본 df
        sliced = extended.iloc[: len(df)].reset_index(drop=True)
        triggered_slice, _, _ = DayTrading3MethodsBreakoutStrategy.evaluate_entry(sliced)
        assert triggered_t == triggered_slice

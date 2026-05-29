"""
Elder EMA Pullback (Variant A) 실전 전략 ↔ 백테스트 룰 일치 검증
=================================================================

신규 실전 전략(strategies/elder_ema_pullback)의 진입/청산 판단이
백테스트 검증판(strategies/books/elder_triple_screen/rules.py +
scripts/run_elder_triple_screen.py Variant A 청산 로직)과 동일한지 검증.

핵심 검증:
  1. evaluate_entry()가 백테스트 rule_triple_screen_ema_pullback.evaluate()와
     동일한 triggered 결과를 낸다 (여러 합성 시점 샘플).
  2. evaluate_sell_conditions()가 백테스트 simulate_one_stock의 청산 우선순위
     (sl→tp→max_hold→trail_ema→trend_flip)와 일치한다.
  3. StrategyLoader가 신규 전략을 정상 로드한다.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.books.elder_triple_screen.rules import (
    ema,
    rule_triple_screen_ema_pullback,
    screen1_uptrend,
)
from strategies.elder_ema_pullback.strategy import ElderEmaPullbackStrategy


# ----------------------------------------------------------------------------- #
# 합성 일봉 생성기 — 다양한 시장 형태를 결정론적으로 생성
# ----------------------------------------------------------------------------- #
def _make_df(closes, highs=None, lows=None, n_pad=80):
    """close 리스트로 OHLCV DataFrame 생성. high/low 미지정 시 close 기준 근사."""
    closes = list(closes)
    if highs is None:
        highs = [c * 1.01 for c in closes]
    if lows is None:
        lows = [c * 0.99 for c in closes]
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2025-01-01", periods=n, freq="D"),
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1_000_000] * n,
    })


def _uptrend_pullback_df():
    """EMA65 상승 + 마지막 봉 EMA13 눌림 후 회복 형태 (진입 트리거 기대)."""
    # 완만한 상승 추세 90바
    base = np.linspace(10000, 16000, 90)
    closes = list(base)
    df = _make_df(closes)
    ema13 = ema(df["close"].astype(float), 13)
    last_ema13 = float(ema13.iloc[-1])
    # 마지막 봉: low가 EMA13을 살짝 터치(<=ema13*1.01)하고 close는 EMA13 위에서 마감
    df.loc[df.index[-1], "low"] = last_ema13 * 1.005
    df.loc[df.index[-1], "close"] = last_ema13 * 1.02
    df.loc[df.index[-1], "high"] = last_ema13 * 1.03
    return df


def _downtrend_df():
    """EMA65 하락 추세 (Screen1 실패 → 진입 없음 기대)."""
    base = np.linspace(16000, 10000, 90)
    return _make_df(list(base))


def _flat_no_pullback_df():
    """상승 추세지만 마지막 봉이 눌림 터치 없이 EMA13 위에서 급등 (Screen2 실패)."""
    base = np.linspace(10000, 16000, 90)
    closes = list(base)
    df = _make_df(closes)
    ema13 = ema(df["close"].astype(float), 13)
    last_ema13 = float(ema13.iloc[-1])
    # low를 EMA13보다 한참 위로 → 눌림 터치 실패
    df.loc[df.index[-1], "low"] = last_ema13 * 1.10
    df.loc[df.index[-1], "close"] = last_ema13 * 1.15
    df.loc[df.index[-1], "high"] = last_ema13 * 1.16
    return df


# ----------------------------------------------------------------------------- #
# 1. 진입 신호 일치: 실전 evaluate_entry ↔ 백테스트 rule
# ----------------------------------------------------------------------------- #
class TestEntrySignalConsistency:

    @pytest.mark.parametrize("df_factory", [
        _uptrend_pullback_df,
        _downtrend_df,
        _flat_no_pullback_df,
    ])
    def test_entry_matches_backtest_rule(self, df_factory):
        """실전 evaluate_entry의 triggered가 백테스트 rule.evaluate와 동일."""
        df = df_factory()
        rule = rule_triple_screen_ema_pullback(touch_band=1.01)
        backtest_res = rule.evaluate(df, {})

        live_triggered, live_reasons, live_meta = ElderEmaPullbackStrategy.evaluate_entry(
            df, touch_band=1.01, min_daily_bars=70
        )

        assert live_triggered == backtest_res.triggered, (
            f"진입 불일치: live={live_triggered} backtest={backtest_res.triggered} "
            f"(form={df_factory.__name__})"
        )
        if backtest_res.triggered:
            # 트리거 시 reasons/metadata도 동일 소스에서 나와야 함
            assert live_reasons == list(backtest_res.reasons)
            assert live_meta == dict(backtest_res.metadata)

    def test_uptrend_pullback_triggers(self):
        """상승추세+눌림회복 형태는 반드시 진입 트리거."""
        df = _uptrend_pullback_df()
        # 전제 검증: Screen1 상승이 실제로 성립
        assert screen1_uptrend(df["close"].astype(float)) is True
        triggered, _, _ = ElderEmaPullbackStrategy.evaluate_entry(df)
        assert triggered is True

    def test_downtrend_no_entry(self):
        """하락추세는 Screen1 실패로 진입 없음."""
        df = _downtrend_df()
        triggered, _, _ = ElderEmaPullbackStrategy.evaluate_entry(df)
        assert triggered is False

    def test_insufficient_bars_no_entry(self):
        """70바 미만이면 진입 없음 (rules.py len(df)<70 가드와 동일)."""
        df = _make_df(list(np.linspace(10000, 12000, 50)))
        triggered, _, _ = ElderEmaPullbackStrategy.evaluate_entry(df, min_daily_bars=70)
        assert triggered is False


# ----------------------------------------------------------------------------- #
# 2. 청산 우선순위 일치: 백테스트 simulate_one_stock 분기 1:1
# ----------------------------------------------------------------------------- #
class TestSellConditionConsistency:

    def _trend_df(self, last_close=None):
        base = np.linspace(10000, 16000, 90)
        closes = list(base)
        if last_close is not None:
            closes[-1] = last_close
        return _make_df(closes)

    def test_stop_loss_first(self):
        """-8% 이하면 stop_loss (최우선)."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 0.90  # 현재가가 진입가 대비 -10%
        sell, _, reason = ElderEmaPullbackStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5,
        )
        assert sell is True
        assert reason == "stop_loss"

    def test_take_profit(self):
        """+30% 이상이면 take_profit."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 1.35  # 현재가가 진입가 대비 +35%
        sell, _, reason = ElderEmaPullbackStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5,
        )
        assert sell is True
        assert reason == "take_profit"

    def test_max_hold(self):
        """보유일이 max_hold_days 이상이면 max_hold (sl/tp 미충족 시)."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 1.05  # +5% (tp 미충족, sl 미충족)
        sell, _, reason = ElderEmaPullbackStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=100, max_hold_days=100,
        )
        assert sell is True
        assert reason == "max_hold"

    def test_trail_ema_only_in_profit(self):
        """수익 중(ret>0) 종가가 EMA13 아래면 trail_ema 청산."""
        # 상승 후 마지막 봉이 EMA13 밑으로 꺾인 형태
        base = list(np.linspace(10000, 16000, 89))
        df = _make_df(base + [base[-1] * 0.97])  # 마지막 봉 -3% 하락
        cur = float(df["close"].iloc[-1])
        ema13 = float(ema(df["close"].astype(float), 13).iloc[-1])
        # 전제: 종가가 EMA13 아래
        assert cur < ema13
        entry = cur / 1.02  # 여전히 +2% 수익 중
        sell, _, reason = ElderEmaPullbackStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5, trail_ema=13,
        )
        assert sell is True
        assert reason == "trail_ema"

    def test_no_sell_when_holding(self):
        """sl/tp/max_hold/trail/flip 모두 미충족이면 매도 없음."""
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 1.05  # +5%, 상승추세 유지
        sell, _, reason = ElderEmaPullbackStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5, max_hold_days=100,
        )
        assert sell is False
        assert reason == ""

    def test_priority_sl_over_tp(self):
        """동시 충족 불가하나 우선순위 코드 경로 확인: sl이 tp보다 먼저 평가."""
        # ret 음수면 sl, 양수면 tp — 상호배타. 여기선 sl 경로만 재확인.
        df = self._trend_df()
        entry = float(df["close"].iloc[-1]) / 0.80  # -20%
        sell, _, reason = ElderEmaPullbackStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=200,  # max_hold도 충족하지만 sl 우선
        )
        assert reason == "stop_loss"


# ----------------------------------------------------------------------------- #
# 3. StrategyLoader 로드 검증
# ----------------------------------------------------------------------------- #
class TestStrategyLoaderIntegration:

    def test_loader_discovers_strategy(self, monkeypatch):
        from strategies.config import StrategyLoader
        monkeypatch.chdir(ROOT)
        discovered = StrategyLoader.discover_strategies()
        assert "elder_ema_pullback" in discovered

    def test_loader_loads_strategy(self, monkeypatch):
        from strategies.config import StrategyLoader
        monkeypatch.chdir(ROOT)
        strat = StrategyLoader.load_strategy("elder_ema_pullback")
        assert strat.__class__.__name__ == "ElderEmaPullbackStrategy"
        assert strat.holding_period == "swing"
        # config 값이 백테스트 Variant A와 일치
        risk = strat.config.get("risk_management", {})
        assert risk["take_profit_pct"] == 0.30
        assert risk["stop_loss_pct"] == 0.08
        assert risk["max_hold_days"] == 100

    def test_generate_signal_buy_on_pullback(self, monkeypatch):
        """on_init 후 generate_signal이 눌림 형태에서 BUY를 낸다 (장중 가드 우회)."""
        from strategies.base import SignalType
        monkeypatch.setattr(
            "strategies.elder_ema_pullback.strategy.MarketHours.is_market_open",
            staticmethod(lambda market="KRX": True),
        )
        strat = ElderEmaPullbackStrategy({
            "parameters": {"min_daily_bars": 70},
            "risk_management": {
                "take_profit_pct": 0.30, "stop_loss_pct": 0.08,
                "max_hold_days": 100, "trail_ema": 13, "trend_flip_exit": True,
            },
            "paper_trading": True,
        })
        strat.on_init(broker=None, data_provider=None, executor=None)
        df = _uptrend_pullback_df()
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is not None
        assert sig.signal_type == SignalType.BUY
        assert sig.stop_loss is not None and sig.target_price is not None
        # target/stop이 백테스트 비율과 일치
        cur = float(df["close"].iloc[-1])
        assert abs(sig.target_price - cur * 1.30) < 1.0
        assert abs(sig.stop_loss - cur * 0.92) < 1.0

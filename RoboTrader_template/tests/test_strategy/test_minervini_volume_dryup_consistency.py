"""
Minervini Volume Dry-up (Variant B) 실전 전략 ↔ 백테스트 룰 일치 검증
====================================================================

신규 페이퍼 전략(strategies/minervini_volume_dryup)의 진입/청산 판단이
백테스트 검증판(strategies/books/minervini_vcp/rules.py rule_volume_dryup +
Variant B 청산 로직 sl/tp/max_hold)과 동일한지 검증.

핵심 검증:
  1. evaluate_entry()가 백테스트 rule_volume_dryup.evaluate()와 동일한 triggered
     결과를 낸다 (여러 합성 시점 샘플 — trigger / no-trigger).
  2. generate_signal()이 보유중엔 청산·미보유엔 진입 분기.
  3. config 로드 (StrategyLoader).
  4. 청산 우선순위(sl → tp → max_hold) 동작 (Variant B: trail/trend_flip 없음).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.books.minervini_vcp.rules import rule_volume_dryup
from strategies.minervini_volume_dryup.strategy import MinerviniVolumeDryupStrategy


# ----------------------------------------------------------------------------- #
# 합성 일봉 생성기 — 거래량 dry-up 형태를 결정론적으로 생성
# ----------------------------------------------------------------------------- #
def _make_df(closes, volumes):
    """close / volume 리스트로 OHLCV DataFrame 생성."""
    closes = list(closes)
    volumes = list(volumes)
    n = len(closes)
    assert len(volumes) == n
    return pd.DataFrame({
        "datetime": pd.date_range("2025-01-01", periods=n, freq="D"),
        "open": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": volumes,
    })


def _dryup_df():
    """최근 10봉 평균 거래량 << 직전 30봉 평균 (dry-up 트리거 기대).

    40봉: 앞 30봉 거래량 1,000,000 / 뒤 10봉 거래량 400,000 → ratio 0.4 <= 0.7.
    """
    closes = list(np.linspace(10000, 12000, 40))
    volumes = [1_000_000] * 30 + [400_000] * 10
    return _make_df(closes, volumes)


def _no_dryup_df():
    """최근 10봉 거래량이 base와 동일 (ratio ≈ 1.0 → no-trigger)."""
    closes = list(np.linspace(10000, 12000, 40))
    volumes = [1_000_000] * 40
    return _make_df(closes, volumes)


def _surge_df():
    """최근 10봉 거래량이 base보다 급증 (ratio > 1 → no-trigger)."""
    closes = list(np.linspace(10000, 12000, 40))
    volumes = [1_000_000] * 30 + [3_000_000] * 10
    return _make_df(closes, volumes)


# ----------------------------------------------------------------------------- #
# 1. 진입 신호 일치: 실전 evaluate_entry ↔ 백테스트 rule
# ----------------------------------------------------------------------------- #
class TestEntrySignalConsistency:

    @pytest.mark.parametrize("df_factory", [
        _dryup_df,
        _no_dryup_df,
        _surge_df,
    ])
    def test_entry_matches_backtest_rule(self, df_factory):
        """실전 evaluate_entry의 triggered가 백테스트 rule.evaluate와 동일."""
        df = df_factory()
        rule = rule_volume_dryup()
        backtest_res = rule.evaluate(df, {})

        live_triggered, live_reasons, live_meta = MinerviniVolumeDryupStrategy.evaluate_entry(
            df, min_daily_bars=40
        )

        assert live_triggered == backtest_res.triggered, (
            f"진입 불일치: live={live_triggered} backtest={backtest_res.triggered} "
            f"(form={df_factory.__name__})"
        )
        if backtest_res.triggered:
            # 트리거 시 reasons/metadata도 동일 소스에서 나와야 함
            assert live_reasons == list(backtest_res.reasons)
            assert live_meta == dict(backtest_res.metadata)

    def test_dryup_triggers(self):
        """거래량 dry-up 형태는 반드시 진입 트리거 + confidence 58."""
        df = _dryup_df()
        triggered, reasons, _ = MinerviniVolumeDryupStrategy.evaluate_entry(df)
        assert triggered is True
        assert any("volume_dryup" in r for r in reasons)

    def test_no_dryup_no_entry(self):
        """거래량 평탄(ratio≈1.0)이면 진입 없음."""
        df = _no_dryup_df()
        triggered, _, _ = MinerviniVolumeDryupStrategy.evaluate_entry(df)
        assert triggered is False

    def test_volume_surge_no_entry(self):
        """거래량 급증(ratio>1)이면 진입 없음."""
        df = _surge_df()
        triggered, _, _ = MinerviniVolumeDryupStrategy.evaluate_entry(df)
        assert triggered is False

    def test_insufficient_bars_no_entry(self):
        """40봉 미만이면 진입 없음 (recent10+base30 가드와 동일)."""
        closes = list(np.linspace(10000, 12000, 30))
        volumes = [1_000_000] * 20 + [400_000] * 10
        df = _make_df(closes, volumes)
        triggered, _, _ = MinerviniVolumeDryupStrategy.evaluate_entry(df, min_daily_bars=40)
        assert triggered is False


# ----------------------------------------------------------------------------- #
# 2. 청산 우선순위 일치 (Variant B): sl → tp → max_hold, trail/trend_flip 없음
# ----------------------------------------------------------------------------- #
class TestSellConditionConsistency:

    def _df(self, last_close=11000.0):
        closes = list(np.linspace(10000, 12000, 40))
        closes[-1] = last_close
        volumes = [1_000_000] * 30 + [400_000] * 10
        return _make_df(closes, volumes)

    def test_stop_loss_first(self):
        """-8% 이하면 stop_loss (최우선)."""
        df = self._df()
        entry = float(df["close"].iloc[-1]) / 0.90  # 현재가가 진입가 대비 -10%
        sell, _, reason = MinerviniVolumeDryupStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=3,
        )
        assert sell is True
        assert reason == "stop_loss"

    def test_take_profit(self):
        """+12% 이상이면 take_profit."""
        df = self._df()
        entry = float(df["close"].iloc[-1]) / 1.15  # 현재가가 진입가 대비 +15%
        sell, _, reason = MinerviniVolumeDryupStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=3,
        )
        assert sell is True
        assert reason == "take_profit"

    def test_max_hold(self):
        """보유 거래일이 max_hold_days 이상이면 max_hold (sl/tp 미충족 시)."""
        df = self._df()
        entry = float(df["close"].iloc[-1]) / 1.05  # +5% (tp 미충족, sl 미충족)
        sell, _, reason = MinerviniVolumeDryupStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=20, max_hold_days=20,
        )
        assert sell is True
        assert reason == "max_hold"

    def test_no_sell_when_flat(self):
        """sl/tp/max_hold 모두 미충족이면 매도 없음."""
        df = self._df()
        entry = float(df["close"].iloc[-1]) / 1.05  # +5%
        sell, _, reason = MinerviniVolumeDryupStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5, max_hold_days=20,
        )
        assert sell is False
        assert reason == ""

    def test_no_trail_or_trend_flip(self):
        """Variant B는 trail/trend_flip 없음 — 수익 중 EMA 이탈에도 매도 안 함."""
        # 마지막 봉 급락(EMA13 하향 이탈 상황) but sl/tp/max_hold 미충족 → 보유 유지
        df = self._df(last_close=11000.0 * 0.97)
        cur = float(df["close"].iloc[-1])
        entry = cur / 1.02  # 여전히 +2% 수익 중 (Variant A라면 trail_ema 청산)
        sell, _, reason = MinerviniVolumeDryupStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=5, max_hold_days=20,
        )
        assert sell is False
        assert reason == ""

    def test_priority_sl_over_max_hold(self):
        """sl과 max_hold 동시 충족 시 sl 우선."""
        df = self._df()
        entry = float(df["close"].iloc[-1]) / 0.80  # -20%
        sell, _, reason = MinerviniVolumeDryupStrategy.evaluate_sell_conditions(
            df=df, entry_price=entry, hold_days=99, max_hold_days=20,
        )
        assert reason == "stop_loss"


# ----------------------------------------------------------------------------- #
# 3. generate_signal 분기 + StrategyLoader 로드
# ----------------------------------------------------------------------------- #
class TestGenerateSignalBranching:

    def _strat(self, monkeypatch):
        monkeypatch.setattr(
            "strategies.minervini_volume_dryup.strategy.MarketHours.is_market_open",
            staticmethod(lambda market="KRX": True),
        )
        strat = MinerviniVolumeDryupStrategy({
            "parameters": {"min_daily_bars": 40},
            "risk_management": {
                "take_profit_pct": 0.12, "stop_loss_pct": 0.08, "max_hold_days": 20,
            },
            "paper_trading": True,
        })
        strat.on_init(broker=None, data_provider=None, executor=None)
        return strat

    def test_generate_signal_buy_when_not_holding(self, monkeypatch):
        """미보유 + dry-up 형태에서 BUY (장중 가드 우회)."""
        from strategies.base import SignalType
        strat = self._strat(monkeypatch)
        df = _dryup_df()
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is not None
        assert sig.signal_type == SignalType.BUY
        assert sig.confidence == 58.0
        # target/stop이 Variant B 비율과 일치
        cur = float(df["close"].iloc[-1])
        assert abs(sig.target_price - cur * 1.12) < 1.0
        assert abs(sig.stop_loss - cur * 0.92) < 1.0

    def test_generate_signal_no_buy_when_no_dryup(self, monkeypatch):
        """미보유 + dry-up 아님이면 신호 없음."""
        strat = self._strat(monkeypatch)
        df = _no_dryup_df()
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is None

    def test_generate_signal_sell_when_holding(self, monkeypatch):
        """보유중이면 청산 분기 (sl 충족 시 SELL)."""
        from strategies.base import SignalType
        strat = self._strat(monkeypatch)
        df = _dryup_df()
        cur = float(df["close"].iloc[-1])
        # 보유 등록: 진입가를 현재가 대비 +20%로 두면 -16.7% → stop_loss
        strat.positions["005930"] = {
            "quantity": 10,
            "entry_price": cur / 0.80,
            "entry_time": None,
        }
        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is not None
        assert sig.signal_type == SignalType.SELL
        assert sig.metadata["exit_reason"] == "stop_loss"

    def test_generate_signal_no_entry_intraday(self, monkeypatch):
        """미보유 + timeframe != daily 면 신규 진입 안 함."""
        strat = self._strat(monkeypatch)
        df = _dryup_df()
        sig = strat.generate_signal("005930", df, timeframe="minute")
        assert sig is None


class TestStrategyLoaderIntegration:

    def test_loader_discovers_strategy(self, monkeypatch):
        from strategies.config import StrategyLoader
        monkeypatch.chdir(ROOT)
        discovered = StrategyLoader.discover_strategies()
        assert "minervini_volume_dryup" in discovered

    def test_loader_loads_strategy(self, monkeypatch):
        from strategies.config import StrategyLoader
        monkeypatch.chdir(ROOT)
        strat = StrategyLoader.load_strategy("minervini_volume_dryup")
        assert strat.__class__.__name__ == "MinerviniVolumeDryupStrategy"
        assert strat.holding_period == "swing"
        # config 값이 백테스트 Variant B와 일치
        risk = strat.config.get("risk_management", {})
        assert risk["take_profit_pct"] == 0.12
        assert risk["stop_loss_pct"] == 0.08
        assert risk["max_hold_days"] == 20

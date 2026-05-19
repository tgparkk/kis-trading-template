"""OrbV2Strategy + set_daily_context 단위 테스트."""
import pytest

from strategies.intraday._base_intraday import IntradayBaseStrategy


class _DummyIntraday(IntradayBaseStrategy):
    name = "Dummy"
    version = "0.0.0"

    def generate_signal(self, stock_code, data, timeframe="minute"):
        return None


class TestSetDailyContext:
    def test_default_is_noop_storing_dict(self):
        strat = _DummyIntraday({})
        strat.set_daily_context("20260401", {"prev_day_volume": {"005930": 1000.0}})
        assert strat._daily_ctx == {"prev_day_volume": {"005930": 1000.0}}
        assert strat._daily_ctx_date == "20260401"

    def test_overwrites_on_each_call(self):
        strat = _DummyIntraday({})
        strat.set_daily_context("20260401", {"a": 1})
        strat.set_daily_context("20260402", {"b": 2})
        assert strat._daily_ctx == {"b": 2}
        assert strat._daily_ctx_date == "20260402"

    def test_none_ctx_resets_to_empty_dict(self):
        strat = _DummyIntraday({})
        strat.set_daily_context("20260401", None)
        assert strat._daily_ctx == {}


import pandas as pd
from datetime import datetime, timedelta

from strategies.base import SignalType
from strategies.intraday.orb_v2.strategy import OrbV2Strategy


def _make_minute_df(or_high=10100.0, breakout_close=10200.0, n_box=30, volumes_box=None, volumes_after=None):
    """ORB 시뮬용 분봉 DF — 09:00부터 N+5 분봉. 마지막 봉이 돌파 봉."""
    start = pd.Timestamp("2026-04-01 09:00:00")
    rows = []
    box_vols = volumes_box if volumes_box is not None else [100] * n_box
    after_vols = volumes_after if volumes_after is not None else [100, 100, 100, 100, 100]

    # 박스 구간: high를 or_high 직전까지만
    for i, v in enumerate(box_vols):
        rows.append({
            "datetime": start + timedelta(minutes=i),
            "open": 10000.0, "high": or_high - 10, "low": 9990.0, "close": 10000.0,
            "volume": float(v),
        })
    # 박스 직후
    for i, v in enumerate(after_vols[:-1]):
        rows.append({
            "datetime": start + timedelta(minutes=n_box + i),
            "open": 10050.0, "high": 10080.0, "low": 10040.0, "close": 10050.0,
            "volume": float(v),
        })
    # 돌파 봉
    rows.append({
        "datetime": start + timedelta(minutes=n_box + len(after_vols) - 1),
        "open": 10100.0, "high": breakout_close + 50, "low": 10090.0, "close": breakout_close,
        "volume": float(after_vols[-1]),
    })
    return pd.DataFrame(rows)


class TestOrbV2Strategy:
    def _cfg(self, vol_ratio=1.0, use_market=False):
        return {
            "parameters": {
                "box_minutes": 30,
                "volume_ratio_threshold": vol_ratio,
                "use_market_filter": use_market,
            },
            "risk_management": {"stop_loss_pct": 0.03, "take_profit_pct": 0.06},
        }

    def test_volume_filter_blocks_when_below_threshold(self):
        strat = OrbV2Strategy(self._cfg(vol_ratio=1.0))
        # 누적 거래량 = 30*100 + 5*100 = 3500. 전일 = 10000. 비율 = 0.35 < 1.0
        strat.set_daily_context("20260401", {"prev_day_volume": {"005930": 10000.0}})
        df = _make_minute_df()
        sig = strat.generate_signal("005930", df, "minute")
        assert sig is None

    def test_volume_filter_allows_when_above_threshold(self):
        strat = OrbV2Strategy(self._cfg(vol_ratio=0.3))
        # 누적 거래량 3500 / 10000 = 0.35 > 0.3
        strat.set_daily_context("20260401", {"prev_day_volume": {"005930": 10000.0}})
        df = _make_minute_df()
        sig = strat.generate_signal("005930", df, "minute")
        assert sig is not None
        assert sig.signal_type == SignalType.BUY

    def test_volume_filter_skipped_when_prev_zero(self):
        """전일 데이터 결손 fallback — 필터 미적용, 통과."""
        strat = OrbV2Strategy(self._cfg(vol_ratio=10.0))  # 매우 높은 임계값
        strat.set_daily_context("20260401", {"prev_day_volume": {"005930": 0.0}})
        df = _make_minute_df()
        sig = strat.generate_signal("005930", df, "minute")
        assert sig is not None  # fallback 통과

    def test_volume_filter_skipped_when_code_missing(self):
        strat = OrbV2Strategy(self._cfg(vol_ratio=10.0))
        strat.set_daily_context("20260401", {"prev_day_volume": {}})  # 005930 없음
        df = _make_minute_df()
        sig = strat.generate_signal("005930", df, "minute")
        assert sig is not None  # fallback 통과

    def test_market_filter_blocks_when_kospi_down(self):
        """전일 KOSPI 일봉 하락(kospi_market_up=False) → 진입 차단."""
        strat = OrbV2Strategy(self._cfg(vol_ratio=0.0, use_market=True))
        strat.set_daily_context("20260401", {
            "prev_day_volume": {"005930": 10000.0},
            "kospi_market_up": False,
        })
        df = _make_minute_df()
        sig = strat.generate_signal("005930", df, "minute")
        assert sig is None

    def test_market_filter_allows_when_kospi_up(self):
        """전일 KOSPI 일봉 상승(kospi_market_up=True) → 진입 허용."""
        strat = OrbV2Strategy(self._cfg(vol_ratio=0.0, use_market=True))
        strat.set_daily_context("20260401", {
            "prev_day_volume": {"005930": 10000.0},
            "kospi_market_up": True,
        })
        df = _make_minute_df()
        sig = strat.generate_signal("005930", df, "minute")
        assert sig is not None

    def test_market_filter_skipped_when_kospi_missing(self):
        """KOSPI 일봉 결손(kospi_market_up 키 없음) → fallback 통과."""
        strat = OrbV2Strategy(self._cfg(vol_ratio=0.0, use_market=True))
        strat.set_daily_context("20260401", {
            "prev_day_volume": {"005930": 10000.0},
            # kospi_market_up 키 없음
        })
        df = _make_minute_df()
        sig = strat.generate_signal("005930", df, "minute")
        assert sig is not None

    def test_market_filter_disabled_ignores_kospi(self):
        """use_market_filter=False일 때 kospi_market_up=False도 무시."""
        strat = OrbV2Strategy(self._cfg(vol_ratio=0.0, use_market=False))
        strat.set_daily_context("20260401", {
            "prev_day_volume": {"005930": 10000.0},
            "kospi_market_up": False,  # 하락이지만 무시
        })
        df = _make_minute_df()
        sig = strat.generate_signal("005930", df, "minute")
        assert sig is not None

    def test_no_ctx_set_uses_safe_defaults(self):
        """set_daily_context 호출 전이라도 안전하게 동작."""
        strat = OrbV2Strategy(self._cfg(vol_ratio=10.0, use_market=True))
        df = _make_minute_df()
        sig = strat.generate_signal("005930", df, "minute")
        # ctx 없으면 두 필터 모두 fallback → 통과
        assert sig is not None

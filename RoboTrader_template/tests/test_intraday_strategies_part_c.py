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

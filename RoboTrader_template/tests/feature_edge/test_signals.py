import pandas as pd
from scripts.feature_edge.signals import generate_entry_signals


class _FakeAdapter:
    strategy_name = "fake"
    lookback_days = 5

    def default_params(self):
        return {"thr": 100.0}

    def match(self, df, params):
        if float(df["close"].iloc[-1]) > params["thr"]:
            return (1.0, "above thr")
        return None


def test_generates_signal_dates():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    daily = pd.DataFrame({"date": dates, "open": [99]*6, "high":[99]*6,
                          "low":[99]*6, "close": [99, 99, 101, 99, 102, 99],
                          "volume":[1]*6})
    supplier = {"S1": daily}
    sigs = generate_entry_signals(_FakeAdapter(), ["S1"], supplier, min_bars=2)
    got = sorted(d.strftime("%Y-%m-%d") for d in sigs["date"])
    assert "2024-01-03" in got
    assert "2024-01-05" in got
    assert "2024-01-02" not in got
    assert (sigs["strategy"] == "fake").all()

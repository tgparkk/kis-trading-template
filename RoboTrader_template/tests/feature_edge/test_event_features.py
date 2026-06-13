import pandas as pd
from scripts.feature_edge.event_features import compute_event_flags


def test_within_window_flag():
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    daily = pd.DataFrame({"date": dates})
    events = [(pd.Timestamp("2024-01-05"), "rights_issue")]
    out = compute_event_flags(daily, events, window=2)
    flags = dict(zip(out["date"], out["event_within_n"]))
    assert flags[pd.Timestamp("2024-01-03")] == 1
    assert flags[pd.Timestamp("2024-01-07")] == 1
    assert flags[pd.Timestamp("2024-01-08")] == 0
    assert flags[pd.Timestamp("2024-01-01")] == 0


def test_no_events_all_zero():
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    out = compute_event_flags(pd.DataFrame({"date": dates}), [], window=3)
    assert (out["event_within_n"] == 0).all()

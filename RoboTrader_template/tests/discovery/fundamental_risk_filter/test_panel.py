import os
import sys

import pandas as pd

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import p3_panel as p3  # noqa: E402


def _panel(rows):
    return pd.DataFrame(rows, columns=["stock_code", "date", "crash",
                                       "window_full", "bsns_year"])


def test_usable_requires_both_full_window_and_financials():
    df = _panel([
        ("A", "2022-01-03", True, True, "2020"),    # 남는다
        ("B", "2022-01-03", True, False, "2020"),   # 부분 창
        ("C", "2022-01-03", True, True, None),      # 재무 없음
    ])
    out = p3.usable(df)
    assert list(out["stock_code"]) == ["A"]


def test_usable_does_not_mutate_input():
    df = _panel([("A", "2022-01-03", True, True, "2020")])
    before = len(df)
    p3.usable(df)
    assert len(df) == before


def test_monthly_rates_keys_on_year_month():
    df = _panel([
        ("A", "2022-01-03", True, True, "2020"),
        ("B", "2022-01-04", False, True, "2020"),
        ("C", "2022-02-03", True, True, "2020"),
    ])
    r = p3.monthly_rates(p3.usable(df)).set_index("ym")
    assert list(r.index) == ["2022-01", "2022-02"]
    assert r.loc["2022-01", "n"] == 2
    assert abs(r.loc["2022-01", "crash_rate"] - 0.5) < 1e-9
    assert abs(r.loc["2022-02", "crash_rate"] - 1.0) < 1e-9


def test_monthly_rates_on_empty_input_is_empty_not_error():
    r = p3.monthly_rates(_panel([]).assign(crash=[]))
    assert len(r) == 0

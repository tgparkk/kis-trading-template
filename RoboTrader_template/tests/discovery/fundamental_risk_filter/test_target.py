import os
import sys

import pandas as pd

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import p1_target as p1  # noqa: E402


def _df(rows):
    return pd.DataFrame(rows, columns=["stock_code", "date", "close",
                                       "fwd_min", "fwd_n"])


def test_constants_match_the_measured_window():
    assert p1.WINDOW == 60
    assert p1.DROP == -0.30
    assert p1.DATE_MIN == "2021-01-04"
    assert p1.DATE_MAX == "2026-05-12"


def test_exactly_minus_30_percent_counts_as_crash():
    """경계는 포함이다 — 정확히 −30% 는 폭락으로 센다."""
    out = p1.crash_flags(_df([("005930", "2022-01-03", 1000.0, 700.0, 60)]))
    assert abs(out["ret_min"].iloc[0] - (-0.30)) < 1e-10
    assert bool(out["crash"].iloc[0]) is True


def test_just_above_threshold_is_not_a_crash():
    out = p1.crash_flags(_df([("005930", "2022-01-03", 1000.0, 700.1, 60)]))
    assert bool(out["crash"].iloc[0]) is False


def test_partial_window_is_flagged_not_dropped():
    """🔴 부분 창은 폭락률을 과소 측정한다. 버리지 말고 «표시»해서 하류가 고르게 한다."""
    out = p1.crash_flags(_df([("005930", "2026-05-11", 1000.0, 900.0, 17)]))
    assert bool(out["window_full"].iloc[0]) is False
    assert bool(out["crash"].iloc[0]) is False   # 값 자체는 계산한다


def test_full_window_is_flagged_full():
    out = p1.crash_flags(_df([("005930", "2022-01-03", 1000.0, 900.0, 60)]))
    assert bool(out["window_full"].iloc[0]) is True


def test_missing_forward_min_yields_nan_not_zero():
    """🔴 결측을 0 으로 만들면 −100% 폭락으로 둔갑한다."""
    out = p1.crash_flags(_df([("005930", "2026-05-12", 1000.0, None, 0)]))
    assert pd.isna(out["ret_min"].iloc[0])
    assert bool(out["crash"].iloc[0]) is False


def test_zero_close_yields_nan_not_division_error():
    out = p1.crash_flags(_df([("005930", "2022-01-03", 0.0, 700.0, 60)]))
    assert pd.isna(out["ret_min"].iloc[0])
    assert bool(out["crash"].iloc[0]) is False


def test_sql_excludes_pseudo_tickers_and_computes_window_size():
    """SQL 이 의사티커를 빼고 창 «크기»도 함께 세는지 문자열 수준에서 고정한다."""
    for t in ("KOSPI", "KOSDAQ", "KS11", "KQ11"):
        assert t in p1.TARGET_SQL
    assert "ROWS BETWEEN 1 FOLLOWING AND 60 FOLLOWING" in p1.TARGET_SQL
    assert "count(" in p1.TARGET_SQL.lower()      # fwd_n 산출
    assert "adj_factor" not in p1.TARGET_SQL      # 곱하지 않는다

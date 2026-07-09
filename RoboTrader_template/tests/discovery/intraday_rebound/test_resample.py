import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.resample import resample_ohlcv


def _minute_df(rows):
    """rows: list of (HH:MM, o, h, l, c, vol, amt)"""
    return pd.DataFrame([
        {
            "datetime": pd.Timestamp(f"2026-06-01 {t}:00"),
            "open": o, "high": h, "low": lo, "close": c,
            "volume": v, "amount": a,
        }
        for (t, o, h, lo, c, v, a) in rows
    ])


def test_three_minute_bucket_aggregates_ohlcv_amount_and_count():
    df = _minute_df([
        ("09:00", 100, 105, 99, 104, 10, 1000),
        ("09:01", 104, 110, 103, 108, 20, 2000),
        ("09:02", 108, 109, 101, 102, 30, 3000),
    ])
    out = resample_ohlcv(df, 3)

    assert len(out) == 1
    row = out.iloc[0]
    assert row["datetime"] == pd.Timestamp("2026-06-01 09:00:00")
    assert row["open"] == 100
    assert row["high"] == 110
    assert row["low"] == 99
    assert row["close"] == 102
    assert row["volume"] == 60
    assert row["amount"] == 6000
    assert row["bar_count"] == 3


def test_missing_minutes_do_not_create_bars():
    """09:03~09:05 구간에 1분봉이 없으면 그 3분봉은 존재하지 않는다 (ffill 금지)."""
    df = _minute_df([
        ("09:00", 100, 100, 100, 100, 1, 100),
        ("09:01", 100, 100, 100, 100, 1, 100),
        ("09:02", 100, 100, 100, 100, 1, 100),
        # 09:03, 09:04, 09:05 없음
        ("09:06", 200, 200, 200, 200, 1, 200),
        ("09:07", 200, 200, 200, 200, 1, 200),
        ("09:08", 200, 200, 200, 200, 1, 200),
    ])
    out = resample_ohlcv(df, 3)

    assert len(out) == 2
    assert list(out["datetime"]) == [
        pd.Timestamp("2026-06-01 09:00:00"),
        pd.Timestamp("2026-06-01 09:06:00"),
    ]
    assert out["close"].tolist() == [100, 200]


def test_partial_bucket_keeps_bar_with_lower_bar_count():
    """버킷에 1분봉이 일부만 있으면 봉은 생기되 bar_count가 3 미만이다."""
    df = _minute_df([
        ("09:00", 100, 101, 99, 100, 5, 500),
        ("09:02", 100, 103, 100, 103, 5, 500),
    ])
    out = resample_ohlcv(df, 3)

    assert len(out) == 1
    assert out.iloc[0]["bar_count"] == 2
    assert out.iloc[0]["high"] == 103


def test_fifteen_minute_bucket_boundaries_align_to_clock():
    rows = [(f"09:{m:02d}", 100, 100, 100, 100, 1, 10) for m in range(0, 30)]
    out = resample_ohlcv(_minute_df(rows), 15)
    assert list(out["datetime"]) == [
        pd.Timestamp("2026-06-01 09:00:00"),
        pd.Timestamp("2026-06-01 09:15:00"),
    ]


def test_empty_input_returns_empty_frame_with_columns():
    out = resample_ohlcv(pd.DataFrame(columns=[
        "datetime", "open", "high", "low", "close", "volume", "amount"
    ]), 3)
    assert out.empty
    assert "bar_count" in out.columns


@pytest.mark.parametrize("tf", [3, 5, 15])
def test_matches_live_converter_on_a_full_session(tf):
    """드리프트 감시: 우리 구현의 OHLCV 는 라이브 TimeFrameConverter 와 같아야 한다.

    리샘플 로직을 두 벌 두지 않는 대신, 두 구현이 어긋나면 여기서 잡는다.
    """
    from core.timeframe_converter import TimeFrameConverter

    rng = np.random.default_rng(0)
    n = 390                                   # 09:00~15:29 정규장 1분봉
    close = 10000 + np.cumsum(rng.normal(0, 5, n))
    df = pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=n, freq="1min"),
        "open": close + rng.normal(0, 1, n),
        "high": close + rng.uniform(0, 10, n),
        "low": close - rng.uniform(0, 10, n),
        "close": close,
        "volume": rng.integers(1, 1000, n).astype(float),
        "amount": rng.integers(1, 10**6, n).astype(float),
    })

    ours = resample_ohlcv(df, tf)
    theirs = TimeFrameConverter.convert_to_timeframe(df, tf)

    pd.testing.assert_frame_equal(
        ours[["datetime", "open", "high", "low", "close", "volume"]]
            .reset_index(drop=True),
        theirs[["datetime", "open", "high", "low", "close", "volume"]]
            .reset_index(drop=True),
        check_dtype=False,
    )

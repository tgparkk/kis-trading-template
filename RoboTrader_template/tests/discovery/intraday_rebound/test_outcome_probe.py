import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.features import FEATURE_NAMES
from scripts.discovery.intraday_rebound.outcome_probe import (
    _add_atr_quintile,
    _assemble_event_row,
    _rank_segments,
    _split_segments,
    _summarize,
)


def _feature_row(seed=0):
    rng = np.random.default_rng(seed)
    return pd.Series({name: float(rng.normal()) for name in FEATURE_NAMES})


# ---------------------------------------------------------------------------
# _assemble_event_row: 순수 행-조립 헬퍼 (DB 무관)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("outcome, expected", [
    ("up", (True, False)),
    ("down", (False, True)),
    ("ambiguous", (False, False)),
    ("none", (False, False)),
])
def test_assemble_event_row_hit_flags_from_outcome(outcome, expected):
    row = _assemble_event_row(
        _feature_row(), trade_date="20260601", stock_code="000001",
        is_full_lookback=True, atr14_pct=0.02, outcome=outcome, terminal_ret=0.01,
    )
    assert (row["hit_up"], row["hit_down"]) == expected


def test_assemble_event_row_carries_all_18_features_and_context_fields():
    row = _assemble_event_row(
        _feature_row(), trade_date="20260601", stock_code="000001",
        is_full_lookback=False, atr14_pct=0.035, outcome="up", terminal_ret=0.021,
    )
    for name in FEATURE_NAMES:
        assert name in row
    assert row["trade_date"] == "20260601"
    assert row["stock_code"] == "000001"
    assert row["is_full_lookback"] is False
    assert row["atr14_pct"] == pytest.approx(0.035)
    assert row["terminal_ret"] == pytest.approx(0.021)
    assert row["outcome"] == "up"


# ---------------------------------------------------------------------------
# _add_atr_quintile
# ---------------------------------------------------------------------------

def test_atr_quintile_has_at_most_5_distinct_values_and_no_nan_when_atr_varies():
    rng = np.random.default_rng(1)
    events = pd.DataFrame({"atr14_pct": rng.uniform(0.01, 0.10, 500)})
    out = _add_atr_quintile(events)
    assert out["atr_quintile"].isna().sum() == 0
    assert out["atr_quintile"].nunique() <= 5


# ---------------------------------------------------------------------------
# _split_segments / _summarize / _rank_segments: DB 없이 손으로 만든 이벤트 표로
# ---------------------------------------------------------------------------

def _fake_events(n_full=400, n_partial=300, seed=7):
    rng = np.random.default_rng(seed)

    def _block(n, is_full):
        data = {name: rng.normal(0, 1, n) for name in FEATURE_NAMES}
        data["trade_date"] = [f"2026060{1 + (i % 5)}" for i in range(n)]
        data["stock_code"] = [f"{i % 20:06d}" for i in range(n)]
        data["is_full_lookback"] = [is_full] * n
        data["atr14_pct"] = rng.uniform(0.01, 0.1, n)
        data["outcome"] = rng.choice(["up", "down", "none"], n)
        data["terminal_ret"] = rng.normal(0, 0.01, n)
        return pd.DataFrame(data)

    full = _block(n_full, True)
    partial = _block(n_partial, False)
    events = pd.concat([full, partial], ignore_index=True)
    events["hit_up"] = events["outcome"] == "up"
    events["hit_down"] = events["outcome"] == "down"
    events = _add_atr_quintile(events)
    return events, n_full, n_partial


def test_split_segments_never_pools_full_and_partial():
    events, n_full, n_partial = _fake_events()
    segments = _split_segments(events)

    assert len(segments["full"]) == n_full
    assert len(segments["partial"]) == n_partial
    assert len(segments["full"]) + len(segments["partial"]) == len(events)
    assert segments["full"]["is_full_lookback"].all()
    assert not segments["partial"]["is_full_lookback"].any()

    def _keys(df):
        return set(zip(df["stock_code"], df["trade_date"], df["atr14_pct"].round(9)))

    # 두 세그먼트가 서로의 행을 하나도 포함하지 않는다 (풀링되지 않았다는 증거).
    assert _keys(segments["full"]).isdisjoint(_keys(segments["partial"]))


def test_summarize_returns_one_row_with_n_pct_up_pct_down_n_dates():
    events, n_full, _ = _fake_events()
    full = events[events["is_full_lookback"]].reset_index(drop=True)
    out = _summarize(full)

    assert len(out) == 1
    assert list(out.columns) == ["n", "pct_up", "pct_down", "n_dates"]
    assert out.loc[0, "n"] == n_full
    assert out.loc[0, "n_dates"] == full["trade_date"].nunique()
    assert out.loc[0, "pct_up"] == pytest.approx(100.0 * full["hit_up"].mean(), abs=0.01)
    assert out.loc[0, "pct_down"] == pytest.approx(100.0 * full["hit_down"].mean(), abs=0.01)


def test_rank_segments_never_pools_and_returns_one_row_per_feature():
    events, _, _ = _fake_events()
    out = _rank_segments(events, n_boot=20, seed=1)

    assert set(out.keys()) == {"full", "partial", "full_summary", "partial_summary"}
    for seg in ("full", "partial"):
        assert len(out[seg]) == len(FEATURE_NAMES)
        assert set(out[seg]["feature"]) == set(FEATURE_NAMES)
        assert len(out[f"{seg}_summary"]) == 1

    # 세그먼트가 풀링되지 않았다는 것을 요약 행수로도 확인한다.
    assert out["full_summary"].loc[0, "n"] + out["partial_summary"].loc[0, "n"] == len(events)

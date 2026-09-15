"""flags.py 단위 — 설계서 §3 · §8-10 · `_defs/flag_cliff.sql` 동치."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.replayer import flags


def _series(n=30, close=100.0, vol=1000.0, adj=1.0):
    """정상 일봉 n행 (등락 없음)."""
    return pd.DataFrame({
        "stock_code": ["000001"] * n,
        "date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": [close] * n,
        "high": [close] * n,
        "low": [close] * n,
        "close": [close] * n,
        "volume": [vol] * n,          # 이미 adj 적용된 값 (로더 규약)
        "adj_factor": [adj] * n,
    })


def _apply(df):
    return flags.compute_bar_flags(df)


# ── flag_cliff — 정본 = _defs/flag_cliff.sql ─────────────────────────────────

def test_cliff_hits_when_gap_dominates_and_volume_flat():
    """(1) −18% 이하 ∧ (2) 갭이 하락을 지배 ∧ (3) 거래량 무증가 → flag_cliff."""
    df = _series(30)
    i = 25
    df.loc[i, ["open", "high", "low", "close"]] = [50.0, 51.0, 49.0, 50.0]   # −50%
    out = _apply(df)
    assert bool(out["flag_cliff"].iloc[i]) is True
    assert bool(out["flag_cliff"].drop(index=i).any()) is False


def test_cliff_rejects_upward_gap_v05_sign_fix():
    """🔒 v0.5 부호 정정 — 시가 갭«업» 후 종가 −18% 는 절벽이 아니다."""
    df = _series(30)
    i = 25
    # close −20%(-0.20), open +15% → 구안(절댓값)은 0.15 >= 0.8*0.20 으로 «통과»했다.
    df.loc[i, ["open", "high", "low", "close"]] = [115.0, 116.0, 79.0, 80.0]
    out = _apply(df)
    assert bool(out["flag_cliff"].iloc[i]) is False


def test_cliff_rejects_volume_surge():
    """거래량이 20봉 평균의 2.0배를 넘으면 패닉 매도 — 절벽 아님."""
    df = _series(30)
    i = 25
    df.loc[i, ["open", "high", "low", "close"]] = [50.0, 51.0, 49.0, 50.0]
    df.loc[i, "volume"] = 1000.0 * 2.5
    out = _apply(df)
    assert bool(out["flag_cliff"].iloc[i]) is False


def test_cliff_unknown_when_prior_bars_lt_20():
    """직전 20봉이 «다» 있을 때만 판정 — 그 밖은 「모른다」."""
    df = _series(30)
    i = 10                                   # n_prior = 10 < 20
    df.loc[i, ["open", "high", "low", "close"]] = [50.0, 51.0, 49.0, 50.0]
    out = _apply(df)
    assert bool(out["flag_cliff"].iloc[i]) is False
    assert bool(out["cliff_unknown_nprior"].iloc[i]) is True


def test_cliff_unknown_when_adj_steps_in_window():
    """🔒 창 안 adj 계단이면 「없다」가 아니라 「모른다」 (critic C1)."""
    df = _series(30)
    i = 25
    df.loc[i, ["open", "high", "low", "close"]] = [50.0, 51.0, 49.0, 50.0]
    df.loc[20:, "adj_factor"] = 2.0          # 창 t−20..t 안에서 변함
    out = _apply(df)
    assert bool(out["flag_cliff"].iloc[i]) is False
    assert bool(out["cliff_unknown_adjstep"].iloc[i]) is True


def test_cliff_null_adj_is_coalesced_to_one():
    """adj_factor NULL 은 COALESCE(...,1) — 계단으로 세지 않는다."""
    df = _series(30)
    df["adj_factor"] = np.nan
    i = 25
    df.loc[i, ["open", "high", "low", "close"]] = [50.0, 51.0, 49.0, 50.0]
    out = _apply(df)
    assert bool(out["flag_cliff"].iloc[i]) is True
    assert bool(out["cliff_unknown_adjstep"].iloc[i]) is False


# ── 잠김봉 · 패딩봉 (§8-10 1·2) ──────────────────────────────────────────────

def test_locked_limit_vs_padding_are_different_columns():
    df = _series(30)
    df.loc[5, "volume"] = 0.0                 # OHLC 동일 ∧ vol=0 → 패딩
    out = _apply(df)
    assert bool(out["flag_padding"].iloc[5]) is True
    assert bool(out["flag_locked_limit"].iloc[5]) is False
    assert bool(out["flag_locked_limit"].iloc[6]) is True     # OHLC 동일 ∧ vol>0
    assert bool(out["flag_padding"].iloc[6]) is False


# ── 파생 (기준일 «이하» 정보만) ──────────────────────────────────────────────

def test_ret_5d_is_backward_only():
    df = _series(10)
    df["close"] = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    out = _apply(df)
    assert out["ret_5d"].iloc[7] == pytest.approx(107 / 102 - 1)
    assert pd.isna(out["ret_5d"].iloc[4])       # 5봉 전이 없다


def test_no_forward_looking_columns():
    """🔴 원장 파생 컬럼에 «미래» 정보가 섞이지 않았는지 — 마지막 행을 바꿔도 앞 행 불변."""
    df = _series(30)
    base = _apply(df)
    df2 = df.copy()
    df2.loc[29, ["open", "high", "low", "close"]] = [1.0, 1.0, 1.0, 1.0]
    out2 = _apply(df2)
    cols = ["flag_cliff", "flag_padding", "flag_locked_limit", "ret_5d"]
    pd.testing.assert_frame_equal(base[cols].iloc[:29], out2[cols].iloc[:29])

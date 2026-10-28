"""[ma20-왕복-shadow] 로그 (10-29 창구 묶음 A ② · 동작 변화 0).

진입 밴드(close ≥ MA20×0.98)와 청산 trail_ma(ret>0 ∧ close<MA20)가 겹쳐 «매수 직후 매도»(3/97).
본 수정(11-05) 전에 MA20 trailing 이탈 매도 신호마다 보유 초를 남긴다 — 매도 신호는 그대로.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import numpy as np
import pandas as pd

import strategies.book_pullback_ma20.strategy as mod
from strategies.base import SignalType
from strategies.book_pullback_ma20.strategy import BookPullbackMa20Strategy

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 30, 10, 0, 0, tzinfo=KST)
CODE = "041190"


def _trail_df():
    """MA20 ≈ 11,000 · 마지막 종가 10,500 (진입 10,000 대비 +5% = 수익 중) → trail_ma 참."""
    closes = np.r_[np.full(40, 11000.0), [10500.0]]
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2026-08-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": np.full(n, 100000.0),
    })


def _make(monkeypatch, entry_time):
    monkeypatch.setattr(mod, "now_kst", lambda: NOW)
    s = BookPullbackMa20Strategy({"paper_trading": True})
    s.on_init(None, None, None)
    s.logger = Mock()
    s.positions[CODE] = {"quantity": 10, "entry_price": 10000.0, "entry_time": entry_time}
    return s


def _shadow(s):
    return [c.args[0] for c in s.logger.info.call_args_list
            if c.args and "[ma20-왕복-shadow]" in str(c.args[0])]


def test_quick_roundtrip_would_block(monkeypatch):
    s = _make(monkeypatch, NOW - timedelta(seconds=42))
    sig = s._check_sell(CODE, _trail_df())
    assert sig is not None and sig.signal_type == SignalType.SELL
    assert sig.metadata["exit_reason"] == "trail_ma"
    assert _shadow(s) == [f"[ma20-왕복-shadow] {CODE} held_sec=42 would_block=1"]


def test_long_hold_would_not_block(monkeypatch):
    s = _make(monkeypatch, NOW - timedelta(days=3, seconds=5))
    sig = s._check_sell(CODE, _trail_df())
    assert sig is not None
    (line,) = _shadow(s)
    assert line.endswith("would_block=0")
    assert f"held_sec={3 * 86400 + 5}" in line


def test_missing_entry_time_logs_unknown(monkeypatch):
    s = _make(monkeypatch, None)
    sig = s._check_sell(CODE, _trail_df())
    assert sig is not None
    assert _shadow(s) == [f"[ma20-왕복-shadow] {CODE} held_sec=- would_block=0"]


def test_non_trail_exit_no_shadow(monkeypatch):
    """max_hold 청산 등 다른 사유는 줄을 안 찍는다."""
    s = _make(monkeypatch, NOW - timedelta(days=200))
    sig = s._check_sell(CODE, _trail_df())
    assert sig is not None and sig.metadata["exit_reason"] == "max_hold"
    assert _shadow(s) == []


def test_signal_identical_with_and_without_shadow_failure(monkeypatch):
    """동작 불변: 보유초 계산이 깨져도(시계 예외) 같은 매도 신호 · WARNING 1회."""
    s1 = _make(monkeypatch, NOW - timedelta(seconds=42))
    good = s1._check_sell(CODE, _trail_df())
    s2 = _make(monkeypatch, NOW - timedelta(seconds=42))
    calls = {"n": 0}

    def _clock():
        calls["n"] += 1
        if calls["n"] > 1:  # 1번째 = hold_days 계산(기존) · 2번째 = shadow
            raise RuntimeError("clock boom")
        return NOW
    monkeypatch.setattr(mod, "now_kst", _clock)
    weird = s2._check_sell(CODE, _trail_df())
    assert weird is not None
    assert (good.signal_type, good.reasons, good.metadata) == (weird.signal_type, weird.reasons, weird.metadata)
    assert _shadow(s2) == []
    assert s2.logger.warning.call_count == 1

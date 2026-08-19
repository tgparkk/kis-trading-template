"""문서 5(PREREG_BREAKOUT.md) — 돌파 축 실행기."""
import importlib

import numpy as np
import pytest

RUN = importlib.import_module("backtest.concept_axes.minervini.run")


def _series(n=30, high=100.0, vol=1000.0):
    return (np.full(n, high), np.full(n, vol), np.full(n, high - 1.0))


class TestBreakoutFlags:
    def test_frozen_params(self):
        assert RUN.PIVOT_WIN == 25
        assert RUN.RVOL_MIN == 1.5
        assert RUN.S_BREAKOUT == 100
        assert RUN.GATE_MIN_SELECTED == 1500

    def test_insufficient_bars_returns_false(self):
        h, v, c = _series(30)
        # i = 24 -> base 는 [-1, 24) 가 되어 26봉 미만. 사양 §2 가드.
        assert RUN.breakout_flags(h, v, c, 24) == (False, False)

    def test_exactly_26_bars_is_allowed(self):
        h, v, c = _series(30)
        h[:25] = 100.0
        c[25] = 101.0          # 돌파
        v[:25] = 1000.0
        v[25] = 1600.0         # RVOL 1.6
        assert RUN.breakout_flags(h, v, c, 25) == (True, True)

    def test_pivot_uses_base_high_excluding_current_bar(self):
        h, v, c = _series(40)
        h[:30] = 100.0
        h[30] = 999.0          # «현재봉» 고가는 피벗에 들어가면 안 된다
        c[30] = 101.0
        v[:30] = 1000.0
        v[30] = 2000.0
        ok_p, ok_q = RUN.breakout_flags(h, v, c, 30)
        assert ok_p is True, "현재봉 high 가 피벗에 섞이면 돌파가 False 가 된다"

    def test_close_equal_to_pivot_is_not_breakout(self):
        h, v, c = _series(40)
        h[:30] = 100.0
        c[30] = 100.0          # 초과가 아니라 «같음»
        v[:30] = 1000.0
        v[30] = 2000.0
        ok_p, _ = RUN.breakout_flags(h, v, c, 30)
        assert ok_p is False

    def test_rvol_boundary_is_inclusive(self):
        h, v, c = _series(40)
        h[:30] = 100.0
        c[30] = 101.0
        v[:30] = 1000.0
        v[30] = 1500.0         # 정확히 1.5배
        _, ok_q = RUN.breakout_flags(h, v, c, 30)
        assert ok_q is True

    def test_zero_base_volume_is_false(self):
        h, v, c = _series(40)
        h[:30] = 100.0
        c[30] = 101.0
        v[:30] = 0.0
        v[30] = 5000.0
        _, ok_q = RUN.breakout_flags(h, v, c, 30)
        assert ok_q is False

    def test_flags_are_independent(self):
        """P(돌파만)·Q(거래량만) 분해가 가능해야 한다."""
        h, v, c = _series(40)
        h[:30] = 100.0
        c[30] = 101.0          # 돌파 O
        v[:30] = 1000.0
        v[30] = 1000.0         # RVOL 1.0 -> X
        assert RUN.breakout_flags(h, v, c, 30) == (True, False)

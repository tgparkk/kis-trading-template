"""트레이딩의 전설 (키움영웅전 9인) — 일봉 룰 단위 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# 공통 헬퍼: 일봉 OHLCV 생성 (haru 테스트와 동일 시그니처)
# ---------------------------------------------------------------------------

def _make_df(close, *, open_=None, high=None, low=None, volume=None):
    close = np.asarray(close, dtype=float)
    n = len(close)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    open_ = close.copy() if open_ is None else np.asarray(open_, dtype=float)
    high = (np.maximum(open_, close) * 1.005) if high is None else np.asarray(high, dtype=float)
    low = (np.minimum(open_, close) * 0.995) if low is None else np.asarray(low, dtype=float)
    volume = np.full(n, 1_000.0) if volume is None else np.asarray(volume, dtype=float)
    return pd.DataFrame({
        "datetime": dates,
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


# ---------------------------------------------------------------------------
# T1: rule_close_momentum_breakout (종가매매, 오버나이트)
# ---------------------------------------------------------------------------

class TestRuleCloseMomentumBreakout:
    def _surge_close_df(self):
        """박스권 후 마지막 봉 +8% 급등 + 20일 신고가 갱신 양봉."""
        base = np.full(30, 10_000.0)
        df = _make_df(base)
        prev_close = float(df["close"].iloc[-2])  # 10000
        # 마지막 봉: prev_close 대비 +8%, 박스권 고가(~10050) 상회 신고가, 양봉
        df.loc[df.index[-1], "open"] = prev_close * 1.001
        df.loc[df.index[-1], "close"] = prev_close * 1.08
        df.loc[df.index[-1], "high"] = prev_close * 1.085
        df.loc[df.index[-1], "low"] = prev_close * 1.0
        return df

    def test_triggers_on_strong_up_new_high(self):
        from strategies.books.trading_legends.rules_daily import rule_close_momentum_breakout
        df = self._surge_close_df()
        res = rule_close_momentum_breakout().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.side == "buy"
        assert "change_pct" in res.metadata

    def test_fails_without_strong_up(self):
        from strategies.books.trading_legends.rules_daily import rule_close_momentum_breakout
        df = _make_df(np.full(30, 10_000.0))  # 평탄 = 등락률 ~0
        res = rule_close_momentum_breakout().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T2: rule_limit_up_follow (상따)
# ---------------------------------------------------------------------------

class TestRuleLimitUpFollow:
    def test_triggers_on_limit_up_bullish(self):
        from strategies.books.trading_legends.rules_daily import rule_limit_up_follow
        df = _make_df(np.full(10, 10_000.0))
        prev_close = float(df["close"].iloc[-2])  # 10000
        # +27% 상한가권, 양봉, 종가>시가
        df.loc[df.index[-1], "open"] = prev_close * 1.05
        df.loc[df.index[-1], "close"] = prev_close * 1.27
        df.loc[df.index[-1], "high"] = prev_close * 1.29
        df.loc[df.index[-1], "low"] = prev_close * 1.04
        res = rule_limit_up_follow().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.side == "buy"

    def test_fails_on_modest_gain(self):
        from strategies.books.trading_legends.rules_daily import rule_limit_up_follow
        df = _make_df(np.full(10, 10_000.0))
        prev_close = float(df["close"].iloc[-2])
        df.loc[df.index[-1], "open"] = prev_close * 1.001
        df.loc[df.index[-1], "close"] = prev_close * 1.05  # +5% < +25%
        res = rule_limit_up_follow().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T3: rule_new_high_breakout (전고점 돌파 + 거래량)
# ---------------------------------------------------------------------------

class TestRuleNewHighBreakout:
    def test_triggers_on_60d_high_vol_surge(self):
        from strategies.books.trading_legends.rules_daily import rule_new_high_breakout
        base = np.full(65, 10_000.0)
        vol = np.full(65, 1_000.0)
        df = _make_df(base, volume=vol)
        # 마지막 봉: 60일 신고가(박스 고가 ~10050 상회), 거래량 3배(>=2배)
        df.loc[df.index[-1], "open"] = 10_010.0
        df.loc[df.index[-1], "close"] = 10_300.0  # 신고가
        df.loc[df.index[-1], "high"] = 10_320.0
        df.loc[df.index[-1], "volume"] = 3_000.0
        res = rule_new_high_breakout().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert "prior_high" in res.metadata

    def test_fails_without_vol_surge(self):
        from strategies.books.trading_legends.rules_daily import rule_new_high_breakout
        base = np.full(65, 10_000.0)
        df = _make_df(base, volume=np.full(65, 1_000.0))
        df.loc[df.index[-1], "close"] = 10_300.0  # 신고가지만
        df.loc[df.index[-1], "high"] = 10_320.0
        df.loc[df.index[-1], "volume"] = 1_100.0  # 거래량 급증 없음
        res = rule_new_high_breakout().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T4: rule_prev_limitup_pullback (전날 상한가 익일 눌림)
# ---------------------------------------------------------------------------

class TestRulePrevLimitupPullback:
    def test_triggers_on_prev_limitup_then_rebound(self):
        from strategies.books.trading_legends.rules_daily import rule_prev_limitup_pullback
        # ...t-2=10000, t-1=상한가 12700(+27%), t=눌림 후 반등 양봉
        close = np.concatenate([np.full(8, 10_000.0), np.array([12_700.0, 13_000.0])])
        df = _make_df(close)
        prev_close = 12_700.0
        # 당일: 저가가 전일 종가 이하로 눌림, 양봉, 종가 > 전일 종가
        df.loc[df.index[-1], "open"] = prev_close * 0.99
        df.loc[df.index[-1], "low"] = prev_close * 0.97   # <= prev_close
        df.loc[df.index[-1], "close"] = prev_close * 1.024  # > prev_close, 양봉
        df.loc[df.index[-1], "high"] = prev_close * 1.03
        res = rule_prev_limitup_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert "prev_close" in res.metadata

    def test_fails_without_prev_limitup(self):
        from strategies.books.trading_legends.rules_daily import rule_prev_limitup_pullback
        # 전일 상승이 약함(+3%) → 트리거 안 됨
        close = np.concatenate([np.full(8, 10_000.0), np.array([10_300.0, 10_400.0])])
        df = _make_df(close)
        prev_close = 10_300.0
        df.loc[df.index[-1], "open"] = prev_close * 0.99
        df.loc[df.index[-1], "low"] = prev_close * 0.97
        df.loc[df.index[-1], "close"] = prev_close * 1.01
        res = rule_prev_limitup_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T5: rule_ma5_pullback (눌림목)
# ---------------------------------------------------------------------------

class TestRuleMa5Pullback:
    def test_triggers_on_surge_then_ma5_support(self):
        from strategies.books.trading_legends.rules_daily import rule_ma5_pullback
        # 최근 20일 내 +20% 급등 후 5일선 터치 양봉
        base = np.concatenate([
            np.full(10, 10_000.0),             # warmup
            np.linspace(10_000, 12_500, 10),   # +25% 급등 (최근 20일 윈도우 내)
            np.linspace(12_500, 12_300, 5),    # 완만 조정 (5일선 근처)
        ])
        df = _make_df(base)
        ma5 = pd.Series(df["close"]).rolling(5).mean().iloc[-1]
        df.loc[df.index[-1], "low"] = ma5 * 1.0     # 5일선 터치
        df.loc[df.index[-1], "open"] = ma5 * 1.001
        df.loc[df.index[-1], "close"] = ma5 * 1.01  # 5일선 위 양봉
        df.loc[df.index[-1], "high"] = ma5 * 1.015
        res = rule_ma5_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert "ma5" in res.metadata

    def test_fails_without_surge(self):
        from strategies.books.trading_legends.rules_daily import rule_ma5_pullback
        df = _make_df(np.full(30, 10_000.0))  # 급등 없음
        res = rule_ma5_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T6: rule_bottom_first_bull (바닥권 첫 양봉)
# ---------------------------------------------------------------------------

class TestRuleBottomFirstBull:
    def test_triggers_on_bottom_vol_bull(self):
        from strategies.books.trading_legends.rules_daily import rule_bottom_first_bull
        # 60일 하락 → 직전 봉이 바닥권(60일 저점 부근) → 당일 거래량 동반 양봉
        base = np.concatenate([
            np.linspace(15_000, 9_000, 62),   # 장기 하락 (저점 9000 부근)
            np.array([9_000.0, 9_000.0]),     # 직전 봉 placeholder
        ])
        vol = np.full(64, 1_000.0)
        df = _make_df(base, volume=vol)
        # 직전 봉(반등 전) 종가 = 60일 저점 부근(바닥권)
        df.loc[df.index[-2], "close"] = 9_050.0
        # 마지막 봉: 양봉 + 거래량 2배(>=1.5배)
        df.loc[df.index[-1], "open"] = 9_050.0
        df.loc[df.index[-1], "close"] = 9_400.0   # 양봉 반등
        df.loc[df.index[-1], "high"] = 9_450.0
        df.loc[df.index[-1], "low"] = 9_000.0
        df.loc[df.index[-1], "volume"] = 2_000.0
        res = rule_bottom_first_bull().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert "prior_low" in res.metadata

    def test_fails_when_not_at_bottom(self):
        from strategies.books.trading_legends.rules_daily import rule_bottom_first_bull
        # 저점에서 충분히 상승한 상태 → 바닥권 아님(prev_close가 60일 저점 +5% 초과)
        base = np.concatenate([
            np.linspace(9_000, 13_000, 62),  # 상승 추세 (저점 9000)
            np.array([13_000.0, 13_000.0]),
        ])
        df = _make_df(base, volume=np.full(64, 1_000.0))
        df.loc[df.index[-2], "close"] = 13_000.0   # 저점 9000 대비 +44% → 바닥권 아님
        df.loc[df.index[-1], "open"] = 13_000.0
        df.loc[df.index[-1], "close"] = 13_300.0   # 양봉
        df.loc[df.index[-1], "volume"] = 2_000.0   # 거래량 동반
        res = rule_bottom_first_bull().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T7: ALL_DAILY_RULES / build_strategy_daily / BOOK_META_DAILY
# ---------------------------------------------------------------------------

def test_all_daily_rules_export_has_6_rules():
    from strategies.books.trading_legends import rules_daily as rd
    assert len(rd.ALL_DAILY_RULES) == 6
    names = [cls().name for cls in rd.ALL_DAILY_RULES]
    assert set(names) == {
        "close_momentum_breakout", "limit_up_follow", "new_high_breakout",
        "prev_limitup_pullback", "ma5_pullback", "bottom_first_bull",
    }


def test_build_strategy_daily_single_mode():
    from strategies.books.trading_legends.strategy_daily import build_strategy_daily
    strat = build_strategy_daily(mode="single", target_rule="limit_up_follow")
    assert strat.name == "TradingLegendsDailyStrategy"
    assert strat.holding_period == "swing"
    assert strat.target_rule == "limit_up_follow"


def test_build_strategy_daily_all_and_mode():
    from strategies.books.trading_legends.strategy_daily import build_strategy_daily
    strat = build_strategy_daily(mode="all_AND")
    assert strat.mode == "all_AND"
    assert len(strat.rules) == 6


def test_book_meta_daily():
    from strategies.books.trading_legends.strategy_daily import BOOK_META_DAILY
    assert BOOK_META_DAILY["id"] == "trading_legends_daily"
    assert BOOK_META_DAILY["data_granularity"] == "daily"
    assert BOOK_META_DAILY["category"] == "swing"


def test_generate_signal_daily_returns_signal():
    from strategies.books.trading_legends.strategy_daily import build_strategy_daily
    strat = build_strategy_daily(mode="single", target_rule="limit_up_follow")
    df = _make_df(np.full(10, 10_000.0))
    prev_close = float(df["close"].iloc[-2])
    df.loc[df.index[-1], "open"] = prev_close * 1.05
    df.loc[df.index[-1], "close"] = prev_close * 1.27
    df.loc[df.index[-1], "high"] = prev_close * 1.29
    df.loc[df.index[-1], "low"] = prev_close * 1.04
    sig = strat.generate_signal("TEST", df, "daily")
    assert sig is not None
    assert sig.signal_type.name in ("BUY", "STRONG_BUY")


# ---------------------------------------------------------------------------
# T8: run 스크립트 청산 파라미터 해석 (상따 -3% sl override, variant O)
# ---------------------------------------------------------------------------

class TestResolveExitParams:
    def test_limit_up_sl_override_to_3pct(self):
        from scripts.run_trading_legends_daily import _resolve_exit_params
        sl, tp, mh, trail = _resolve_exit_params("O", "single", "limit_up_follow")
        assert sl == pytest.approx(0.03)   # 상따 -3% 타이트 손절
        assert mh == 1                     # variant O 익일 청산
        assert trail is None               # variant O 는 trail 없음

    def test_limit_up_sl_override_even_in_variant_a(self):
        from scripts.run_trading_legends_daily import _resolve_exit_params
        sl, tp, mh, trail = _resolve_exit_params("A", "single", "limit_up_follow")
        assert sl == pytest.approx(0.03)   # variant 무관 강제 override
        assert trail == 5                  # limit_up_follow trail_ma=5 (variant A)

    def test_variant_o_params(self):
        from scripts.run_trading_legends_daily import _resolve_exit_params
        sl, tp, mh, trail = _resolve_exit_params("O", "single", "close_momentum_breakout")
        assert sl == pytest.approx(0.05)
        assert tp == pytest.approx(0.99)
        assert mh == 1
        assert trail is None

    def test_other_rule_variant_a_defaults(self):
        from scripts.run_trading_legends_daily import _resolve_exit_params
        sl, tp, mh, trail = _resolve_exit_params("A", "single", "new_high_breakout")
        assert sl == pytest.approx(0.08)   # variant A 기본
        assert tp == pytest.approx(0.99)
        assert trail == 20                 # new_high_breakout trail_ma=20

    def test_trail_ma_per_rule(self):
        from scripts.run_trading_legends_daily import _resolve_exit_params
        _, _, _, trail5 = _resolve_exit_params("A", "single", "ma5_pullback")
        assert trail5 == 5
        _, _, _, trail10 = _resolve_exit_params("A", "single", "prev_limitup_pullback")
        assert trail10 == 10

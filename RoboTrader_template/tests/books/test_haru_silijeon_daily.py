"""강창권 단기 트레이딩의 정석 — 일봉 룰 단위 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# 공통 헬퍼: 일봉 OHLCV 생성
# ---------------------------------------------------------------------------

def _make_df(close, *, open_=None, high=None, low=None, volume=None, n_days=None):
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
# T1: rule_daily_ma20_pullback (A-07, +10% 익절 명시)
# ---------------------------------------------------------------------------

class TestRuleDailyMa20Pullback:
    def _surge_then_pullback_to_ma20(self):
        """급등 후 20일선까지 조정 → 마지막 봉 20일선 지지 양봉.

        surge_lookback=30 윈도우(마지막 봉 제외 직전 30봉) 안에 급등 고점과 조정 저점이
        모두 들어오도록 압축 배치(+40% 이력). 앞쪽 15봉은 warmup(ma20).
        """
        base = np.concatenate([
            np.full(15, 10_000.0),             # warmup
            np.linspace(10_000, 14_000, 15),   # 급등 +40% (최근 윈도우 내)
            np.linspace(14_000, 12_500, 15),   # 조정
        ])
        df = _make_df(base)
        ma20 = pd.Series(df["close"]).rolling(20).mean().iloc[-1]
        # 마지막 봉: 저가가 20일선 터치, 양봉 반등, 종가 20일선 위
        df.loc[df.index[-1], "low"] = ma20 * 1.0
        df.loc[df.index[-1], "open"] = ma20 * 1.002
        df.loc[df.index[-1], "close"] = ma20 * 1.01
        df.loc[df.index[-1], "high"] = ma20 * 1.015
        return df

    def test_triggers_on_ma20_support_after_surge(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_ma20_pullback
        df = self._surge_then_pullback_to_ma20()
        res = rule_daily_ma20_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.side == "buy"
        assert "ma20" in res.metadata

    def test_fails_without_surge(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_ma20_pullback
        df = _make_df(np.full(60, 10_000.0))  # 평탄 = 급등 없음
        res = rule_daily_ma20_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_fails_when_below_ma20(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_ma20_pullback
        df = self._surge_then_pullback_to_ma20()
        ma20 = pd.Series(df["close"]).rolling(20).mean().iloc[-1]
        df.loc[df.index[-1], "close"] = ma20 * 0.90  # 20일선 크게 이탈
        res = rule_daily_ma20_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T2: rule_daily_ma5_10_follow (A-08)
# ---------------------------------------------------------------------------

class TestRuleDailyMa510Follow:
    def test_triggers_on_ma5_10_support(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_ma5_10_follow
        base = np.concatenate([
            np.full(15, 10_000.0),             # warmup
            np.linspace(10_000, 14_000, 15),   # 급등 (최근 윈도우 내)
            np.linspace(14_000, 14_500, 15),   # 완만 상승 지속 (정배열 유지)
        ])
        df = _make_df(base)
        ma5 = pd.Series(df["close"]).rolling(5).mean().iloc[-1]
        df.loc[df.index[-1], "low"] = ma5 * 1.0     # 5일선 터치
        df.loc[df.index[-1], "open"] = ma5 * 1.001
        df.loc[df.index[-1], "close"] = ma5 * 1.01
        res = rule_daily_ma5_10_follow().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.side == "buy"

    def test_fails_on_no_trend(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_ma5_10_follow
        df = _make_df(np.full(60, 10_000.0))
        res = rule_daily_ma5_10_follow().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T3: rule_daily_ma60_doji_rebound (A-12)
# ---------------------------------------------------------------------------

class TestRuleDailyMa60DojiRebound:
    def _doji_rebound_df(self):
        """긴 베이스로 ma60≈현재가 근처 → 순차 조정(5<10<20) 후 60일선 부근 도지+반등.

        ma60 이 현재가보다 약간 위(약 +4~5%)에 위치해야 60일선까지 반등 터치가 현실적.
        """
        base = np.concatenate([
            np.full(40, 12_000.0),              # 긴 베이스 → ma60 ~ 12600
            np.linspace(12_000, 13_500, 10),    # 완만 상승
            np.linspace(13_500, 12_050, 38),    # 순차 조정 (5<10<20 역배열)
            np.array([12_020.0, 12_030.0]),     # 도지/반등 placeholder (override)
        ])
        # 거래량 감소: 직전 5봉(2000) 대비 최근 5봉(600) → recent <= prior×0.8
        vol = np.concatenate([np.full(85, 2_000.0), np.full(5, 600.0)])
        df = _make_df(base, volume=vol)
        ma60 = pd.Series(df["close"]).rolling(60).mean().iloc[-1]
        # 직전 봉 = 도지 (몸통 거의 0, range 존재), 60일선 부근
        df.loc[df.index[-2], "open"] = ma60 * 0.999
        df.loc[df.index[-2], "close"] = ma60 * 0.999
        df.loc[df.index[-2], "high"] = ma60 * 1.012
        df.loc[df.index[-2], "low"] = ma60 * 0.985
        # 마지막 봉 = 반등 양봉, 60일선 부근/위
        df.loc[df.index[-1], "low"] = ma60 * 0.99
        df.loc[df.index[-1], "open"] = ma60 * 0.995
        df.loc[df.index[-1], "close"] = ma60 * 1.005
        df.loc[df.index[-1], "high"] = ma60 * 1.01
        return df, ma60

    def test_triggers_on_60_doji_rebound(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_ma60_doji_rebound
        df, _ = self._doji_rebound_df()
        res = rule_daily_ma60_doji_rebound().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert "ma60" in res.metadata

    def test_fails_without_doji(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_ma60_doji_rebound
        df, ma60 = self._doji_rebound_df()
        # 직전 봉을 큰 몸통 음봉으로 (도지 아님)
        df.loc[df.index[-2], "open"] = ma60 * 1.05
        df.loc[df.index[-2], "close"] = ma60 * 0.95
        res = rule_daily_ma60_doji_rebound().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T4: rule_daily_trend_filter_240_480 (A-14)
# ---------------------------------------------------------------------------

class TestRuleDailyTrendFilter240480:
    def test_triggers_on_long_ma_support(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_trend_filter_240_480
        # 500봉 완만 상승 → 종가가 240/480선 위, 저가가 240선 터치 양봉
        base = np.linspace(10_000, 16_000, 500)
        df = _make_df(base)
        ma240 = pd.Series(df["close"]).rolling(240).mean().iloc[-1]
        df.loc[df.index[-1], "low"] = ma240 * 1.0       # 240선 터치
        df.loc[df.index[-1], "open"] = ma240 * 1.005
        df.loc[df.index[-1], "close"] = ma240 * 1.02    # 240선 위 양봉
        df.loc[df.index[-1], "high"] = ma240 * 1.025
        res = rule_daily_trend_filter_240_480().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert "ma480" in res.metadata

    def test_fails_below_480(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_trend_filter_240_480
        # 하락 추세 → 종가가 480선 아래
        base = np.linspace(16_000, 10_000, 500)
        df = _make_df(base)
        res = rule_daily_trend_filter_240_480().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T5: rule_daily_swing_pullback (A-02)
# ---------------------------------------------------------------------------

class TestRuleDailySwingPullback:
    def test_triggers_on_consolidation_then_ma_bounce(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_swing_pullback
        # 급등 → 고점 후 며칠 기간조정 → 20일선 지지 반등.
        # 길이 >=72 필요(max(60,30)+10+2). surge_lookback=30 윈도우 안에 급등 고점+조정 압축.
        base = np.concatenate([
            np.full(50, 10_000.0),             # warmup (ma60 + 길이 확보)
            np.linspace(10_000, 14_000, 12),   # 급등 (고점 형성, 최근 윈도우 내)
            np.linspace(14_000, 12_600, 13),   # 기간 조정 (고점이 충분히 과거)
        ])
        # 거래량 감소: 최근 5봉(800) <= 직전 5봉(3000)×0.85
        df = _make_df(base, volume=np.concatenate([
            np.full(70, 3_000.0),
            np.full(5, 800.0),
        ]))
        ma20 = pd.Series(df["close"]).rolling(20).mean().iloc[-1]
        df.loc[df.index[-1], "low"] = ma20 * 1.0      # 20일선 터치
        df.loc[df.index[-1], "open"] = ma20 * 1.002
        df.loc[df.index[-1], "close"] = ma20 * 1.012  # 양봉 반등
        df.loc[df.index[-1], "high"] = ma20 * 1.018
        res = rule_daily_swing_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert "ma20" in res.metadata

    def test_fails_without_volume_drop(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_swing_pullback
        base = np.concatenate([
            np.full(50, 10_000.0),
            np.linspace(10_000, 14_000, 12),
            np.linspace(14_000, 12_600, 13),
        ])
        df = _make_df(base, volume=np.full(75, 3_000.0))  # 거래량 일정 (감소 없음)
        ma20 = pd.Series(df["close"]).rolling(20).mean().iloc[-1]
        df.loc[df.index[-1], "low"] = ma20 * 1.0
        df.loc[df.index[-1], "close"] = ma20 * 1.012
        res = rule_daily_swing_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T6: rule_daily_new_high_breakout (A-03)
# ---------------------------------------------------------------------------

class TestRuleDailyNewHighBreakout:
    def test_triggers_on_historical_new_high(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_new_high_breakout
        # 박스권 후 마지막 봉이 역사적 신고가 돌파
        base = np.concatenate([
            np.full(40, 10_000.0),            # 박스권 (고가 ~10050)
            np.array([10_020.0]),             # 직전 봉 (신고가 아래)
        ])
        df = _make_df(base)
        prior_high = float(df["high"].iloc[:-1].max())
        df.loc[df.index[-1], "open"] = prior_high * 1.001
        df.loc[df.index[-1], "close"] = prior_high * 1.02   # 신고가 돌파
        df.loc[df.index[-1], "high"] = prior_high * 1.025
        res = rule_daily_new_high_breakout().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert "prior_high" in res.metadata

    def test_fails_when_no_breakout(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_new_high_breakout
        df = _make_df(np.full(40, 10_000.0))  # 신고가 없음
        res = rule_daily_new_high_breakout().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T7: rule_daily_vol300_longma_break (A-06)
# ---------------------------------------------------------------------------

class TestRuleDailyVol300LongMaBreak:
    def test_triggers_on_vol_spike_and_ma240_break(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_vol300_longma_break
        # 280봉(>=242 필요): 바닥권 횡보(240선 아래) → 마지막 봉 거래량 급증 + 240선 종가 돌파
        base = np.concatenate([
            np.linspace(12_000, 9_000, 240),  # 장기 하락 (240선 위→현재가 아래)
            np.full(40, 9_000.0),             # 바닥권 횡보
        ])
        df = _make_df(base, volume=np.full(280, 1_000.0))
        ma240 = pd.Series(df["close"]).rolling(240).mean().iloc[-1]
        # 직전 봉 종가 240선 아래, 마지막 봉 240선 돌파 + 거래량 3배 + 양봉
        df.loc[df.index[-2], "close"] = ma240 * 0.99
        df.loc[df.index[-1], "open"] = ma240 * 0.995
        df.loc[df.index[-1], "close"] = ma240 * 1.02
        df.loc[df.index[-1], "high"] = ma240 * 1.025
        df.loc[df.index[-1], "volume"] = 5_000.0   # 평균 1000 대비 5배 (>=3배)
        res = rule_daily_vol300_longma_break().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.metadata["broken"] in ("ma240", "ma480")

    def test_fails_without_volume_spike(self):
        from strategies.books.haru_silijeon.rules_daily import rule_daily_vol300_longma_break
        base = np.concatenate([np.linspace(12_000, 9_000, 240), np.full(40, 9_000.0)])
        df = _make_df(base, volume=np.full(280, 1_000.0))
        ma240 = pd.Series(df["close"]).rolling(240).mean().iloc[-1]
        df.loc[df.index[-2], "close"] = ma240 * 0.99
        df.loc[df.index[-1], "close"] = ma240 * 1.02
        df.loc[df.index[-1], "volume"] = 1_100.0  # 거래량 급증 없음
        res = rule_daily_vol300_longma_break().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T8: ALL_DAILY_RULES / build_strategy_daily / BOOK_META_DAILY
# ---------------------------------------------------------------------------

def test_all_daily_rules_export_has_7_rules():
    from strategies.books.haru_silijeon import rules_daily as rd
    assert len(rd.ALL_DAILY_RULES) == 7
    names = [cls().name for cls in rd.ALL_DAILY_RULES]
    assert set(names) == {
        "daily_ma20_pullback", "daily_ma5_10_follow", "daily_ma60_doji_rebound",
        "daily_trend_filter_240_480", "daily_swing_pullback",
        "daily_new_high_breakout", "daily_vol300_longma_break",
    }


def test_build_strategy_daily_single_mode():
    from strategies.books.haru_silijeon.strategy_daily import build_strategy_daily
    strat = build_strategy_daily(mode="single", target_rule="daily_ma20_pullback")
    assert strat.name == "HaruSilijeonDailyStrategy"
    assert strat.holding_period == "swing"
    assert strat.target_rule == "daily_ma20_pullback"


def test_build_strategy_daily_all_and_mode():
    from strategies.books.haru_silijeon.strategy_daily import build_strategy_daily
    strat = build_strategy_daily(mode="all_AND")
    assert strat.mode == "all_AND"
    assert len(strat.rules) == 7


def test_book_meta_daily():
    from strategies.books.haru_silijeon.strategy_daily import BOOK_META_DAILY
    assert BOOK_META_DAILY["id"] == "haru_silijeon_daily"
    assert BOOK_META_DAILY["data_granularity"] == "daily"
    assert BOOK_META_DAILY["category"] == "swing"


def test_minute_strategy_untouched():
    """분봉 BOOK_META(id=haru_silijeon, minute)가 일봉 추가로 깨지지 않았는지 회귀 가드."""
    from strategies.books.haru_silijeon.strategy import BOOK_META as MIN_META
    from strategies.books.haru_silijeon.rules import ALL_RULES as MIN_RULES
    assert MIN_META["id"] == "haru_silijeon"
    assert MIN_META["data_granularity"] == "minute"
    assert len(MIN_RULES) == 6


def test_generate_signal_daily_returns_signal():
    from strategies.books.haru_silijeon.strategy_daily import build_strategy_daily
    strat = build_strategy_daily(mode="single", target_rule="daily_ma20_pullback")
    df = TestRuleDailyMa20Pullback()._surge_then_pullback_to_ma20()
    sig = strat.generate_signal("TEST", df, "daily")
    assert sig is not None
    assert sig.signal_type.name in ("BUY", "STRONG_BUY")


# ---------------------------------------------------------------------------
# T9: run 스크립트 청산 파라미터 해석 (A-07 +10% 익절 override)
# ---------------------------------------------------------------------------

class TestResolveExitParams:
    def test_a07_tp_override_to_10pct(self):
        from scripts.run_haru_silijeon_daily import _resolve_exit_params
        sl, tp, mh, trail = _resolve_exit_params("A", "single", "daily_ma20_pullback")
        assert tp == pytest.approx(0.10)   # A-07 +10% 명시 익절
        assert trail == 20                 # 20일선 이탈 청산

    def test_a07_tp_override_even_in_variant_b(self):
        from scripts.run_haru_silijeon_daily import _resolve_exit_params
        sl, tp, mh, trail = _resolve_exit_params("B", "single", "daily_ma20_pullback")
        assert tp == pytest.approx(0.10)   # variant 무관 강제 override
        assert trail is None               # variant B 는 trail 없음

    def test_other_rule_uses_variant_default(self):
        from scripts.run_haru_silijeon_daily import _resolve_exit_params
        sl, tp, mh, trail = _resolve_exit_params("A", "single", "daily_new_high_breakout")
        assert tp == pytest.approx(0.99)   # variant A tp off
        assert trail == 20

    def test_trail_ma_per_rule(self):
        from scripts.run_haru_silijeon_daily import _resolve_exit_params
        _, _, _, trail60 = _resolve_exit_params("A", "single", "daily_ma60_doji_rebound")
        assert trail60 == 60
        _, _, _, trail240 = _resolve_exit_params("A", "single", "daily_vol300_longma_break")
        assert trail240 == 240

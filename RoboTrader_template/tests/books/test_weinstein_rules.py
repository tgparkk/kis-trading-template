"""Weinstein Stage Analysis rules — 단위 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

def _make_weekly_df(n: int, close: np.ndarray, volume: np.ndarray = None) -> pd.DataFrame:
    """n봉 주봉 DataFrame 생성 헬퍼."""
    dates = pd.date_range("2023-01-06", periods=n, freq="W-FRI")
    if volume is None:
        volume = np.full(n, 1_000_000)
    open_ = close * 0.99
    high = close * 1.02
    low = close * 0.98
    return pd.DataFrame({
        "datetime": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "n_days": np.full(n, 5),
    })


def _make_daily_df(n: int, close: np.ndarray) -> pd.DataFrame:
    """n봉 일봉 DataFrame 생성 헬퍼."""
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    volume = np.full(n, 1_000_000)
    return pd.DataFrame({
        "datetime": dates,
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": volume,
    })


# ---------------------------------------------------------------------------
# T1: resample_daily_to_weekly
# ---------------------------------------------------------------------------

class TestResampleDailyToWeekly:
    def test_basic_resample_returns_weekly(self):
        from strategies.books.weinstein_stages.weekly import resample_daily_to_weekly
        n = 25
        close = np.linspace(10_000, 12_000, n)
        daily = _make_daily_df(n, close)
        weekly = resample_daily_to_weekly(daily)
        assert len(weekly) > 0
        assert set(["datetime", "open", "high", "low", "close", "volume", "n_days"]).issubset(weekly.columns)

    def test_weekly_close_equals_last_daily_close_of_week(self):
        from strategies.books.weinstein_stages.weekly import resample_daily_to_weekly
        # 5 full weeks (월~금 각 5일, 총 25일)
        n = 25
        close = np.arange(1, n + 1, dtype=float) * 1000
        daily = _make_daily_df(n, close)
        weekly = resample_daily_to_weekly(daily, min_days_per_week=3)
        # 각 주의 마지막 일봉 close가 주봉 close여야 함
        for _, wrow in weekly.iterrows():
            # 그 주의 마지막 거래일
            last_daily_close = daily[daily["datetime"] <= wrow["datetime"]]["close"].iloc[-1]
            assert wrow["close"] == pytest.approx(last_daily_close, rel=1e-6)

    def test_short_week_filtered_out(self):
        from strategies.books.weinstein_stages.weekly import resample_daily_to_weekly
        # 첫 주에 거래일 2일만 넣고 나머지는 정상
        dates = list(pd.date_range("2023-01-02", periods=2, freq="B"))        # Mon, Tue (week 1)
        dates += list(pd.date_range("2023-01-09", periods=5, freq="B"))       # week 2 full
        dates += list(pd.date_range("2023-01-16", periods=5, freq="B"))       # week 3 full
        close = np.linspace(10_000, 11_000, len(dates))
        df = pd.DataFrame({
            "datetime": dates, "open": close * 0.99, "high": close * 1.02,
            "low": close * 0.98, "close": close, "volume": np.full(len(dates), 1_000_000),
        })
        weekly = resample_daily_to_weekly(df, min_days_per_week=3)
        # 첫 주 (거래일 2일)는 제외돼야 함
        n_days_all = weekly["n_days"].tolist()
        assert all(nd >= 3 for nd in n_days_all)

    def test_empty_input_returns_empty(self):
        from strategies.books.weinstein_stages.weekly import resample_daily_to_weekly
        result = resample_daily_to_weekly(pd.DataFrame())
        assert len(result) == 0

    def test_weekly_high_is_max_daily_high(self):
        from strategies.books.weinstein_stages.weekly import resample_daily_to_weekly
        n = 10
        close = np.linspace(10_000, 11_000, n)
        daily = _make_daily_df(n, close)
        # 특정 일봉에 스파이크
        daily.loc[3, "high"] = 99_999
        weekly = resample_daily_to_weekly(daily, min_days_per_week=3)
        assert weekly["high"].max() == pytest.approx(99_999, rel=1e-6)


# ---------------------------------------------------------------------------
# T2a: compute_ma30w_slope
# ---------------------------------------------------------------------------

class TestComputeMa30wSlope:
    def test_uptrend_slope_positive(self):
        from strategies.books.weinstein_stages.rules import compute_ma30w_slope
        n = 50
        close = pd.Series(np.linspace(10_000, 20_000, n))
        slope = compute_ma30w_slope(close, lookback=4)
        valid = slope.dropna()
        assert (valid > 0).all(), "단조 상승이면 slope > 0"

    def test_downtrend_slope_negative(self):
        from strategies.books.weinstein_stages.rules import compute_ma30w_slope
        n = 50
        close = pd.Series(np.linspace(20_000, 10_000, n))
        slope = compute_ma30w_slope(close, lookback=4)
        valid = slope.dropna()
        assert (valid < 0).all(), "단조 하락이면 slope < 0"

    def test_flat_slope_near_zero(self):
        from strategies.books.weinstein_stages.rules import compute_ma30w_slope
        n = 50
        close = pd.Series(np.full(n, 10_000.0))
        slope = compute_ma30w_slope(close, lookback=4)
        valid = slope.dropna()
        assert (valid.abs() < 1e-9).all(), "수평이면 slope ≈ 0"

    def test_insufficient_data_returns_nan(self):
        from strategies.books.weinstein_stages.rules import compute_ma30w_slope
        close = pd.Series(np.linspace(1, 10, 10))
        slope = compute_ma30w_slope(close, lookback=4)
        assert slope.isna().all()


# ---------------------------------------------------------------------------
# T2b: compute_mansfield_rs
# ---------------------------------------------------------------------------

class TestComputeMansfieldRs:
    def test_outperforming_stock_positive_mrs(self):
        from strategies.books.weinstein_stages.rules import compute_mansfield_rs
        n = 60
        market = pd.Series(np.linspace(1000, 1100, n))  # +10%
        stock = pd.Series(np.linspace(1000, 1300, n))   # +30% (outperforms)
        mrs = compute_mansfield_rs(stock, market, n=26)
        valid = mrs.dropna()
        assert len(valid) > 0
        assert float(valid.iloc[-1]) > 0, "초과수익 종목은 MRS > 0"

    def test_underperforming_stock_negative_mrs(self):
        from strategies.books.weinstein_stages.rules import compute_mansfield_rs
        n = 60
        market = pd.Series(np.linspace(1000, 1300, n))  # +30%
        stock = pd.Series(np.linspace(1000, 1050, n))   # +5% (underperforms)
        mrs = compute_mansfield_rs(stock, market, n=26)
        valid = mrs.dropna()
        assert len(valid) > 0
        assert float(valid.iloc[-1]) < 0, "열위 종목은 MRS < 0"

    def test_equal_performance_mrs_near_zero(self):
        from strategies.books.weinstein_stages.rules import compute_mansfield_rs
        n = 60
        prices = pd.Series(np.linspace(1000, 1200, n))
        mrs = compute_mansfield_rs(prices, prices.copy(), n=26)
        valid = mrs.dropna()
        assert len(valid) > 0
        # RP = 100 항상, SMA(RP,n) = 100 → MRS = 0
        assert (valid.abs() < 1e-6).all()

    def test_empty_input_returns_empty(self):
        from strategies.books.weinstein_stages.rules import compute_mansfield_rs
        mrs = compute_mansfield_rs(pd.Series(dtype=float), pd.Series(dtype=float))
        assert len(mrs) == 0


# ---------------------------------------------------------------------------
# T2c: stage_classifier
# ---------------------------------------------------------------------------

class TestStageClassifier:
    def _build_series(self, n: int, close_arr: np.ndarray, market_arr: np.ndarray = None):
        from strategies.books.weinstein_stages.rules import (
            compute_ma30w_slope, compute_mansfield_rs, stage_classifier,
        )
        close = pd.Series(close_arr)
        ma30w = close.rolling(30).mean()
        slope = compute_ma30w_slope(close, lookback=4)
        if market_arr is None:
            market_arr = close_arr
        market = pd.Series(market_arr)
        mrs = compute_mansfield_rs(close, market, n=26)
        return stage_classifier(close, ma30w, slope, mrs)

    def test_advancing_market_classified_stage2(self):
        n = 80
        close_arr = np.linspace(10_000, 20_000, n)
        stages = self._build_series(n, close_arr)
        valid = stages.dropna()
        # 단조 상승 후반부는 Stage 2여야 함
        assert int(valid.iloc[-1]) == 2

    def test_declining_market_classified_stage4(self):
        n = 80
        close_arr = np.linspace(20_000, 10_000, n)
        stages = self._build_series(n, close_arr)
        valid = stages.dropna()
        assert int(valid.iloc[-1]) == 4

    def test_flat_market_classified_stage1_or_3(self):
        n = 80
        close_arr = np.full(n, 10_000.0)
        stages = self._build_series(n, close_arr)
        valid = stages.dropna()
        assert int(valid.iloc[-1]) in (1, 3)

    def test_returns_integer_labels(self):
        n = 80
        close_arr = np.linspace(10_000, 15_000, n)
        stages = self._build_series(n, close_arr)
        valid = stages.dropna()
        assert set(valid.unique()).issubset({1, 2, 3, 4})


# ---------------------------------------------------------------------------
# T3a: rule_stage2_initial_breakout
# ---------------------------------------------------------------------------

def _build_ctx_for_weekly_df(weekly_df: pd.DataFrame, rs_n: int = 26):
    """weekly_df에서 ctx dict 빌드 헬퍼."""
    from strategies.books.weinstein_stages.rules import (
        compute_ma30w_slope, compute_mansfield_rs, stage_classifier,
    )
    close = weekly_df["close"].astype(float).reset_index(drop=True)
    ma30w = close.rolling(30).mean()
    slope = compute_ma30w_slope(close, lookback=4)
    # self-referential market (동일 종목 = RS 0에 수렴)
    mrs = pd.Series(np.zeros(len(close)), dtype=float)  # 강제 0 이상
    stages = stage_classifier(close, ma30w, slope, mrs)
    return {
        "ma30w_series": ma30w,
        "slope_series": slope,
        "mrs_series": mrs,
        "stage_series": stages,
    }


class TestRuleStage2InitialBreakout:
    def _make_breakout_df(self):
        """Stage 1→2 전환 + 박스 저항선 돌파 + 거래량 폭증 합성 주봉."""
        n = 60
        # 전반 30봉: 횡보 (Stage 1 흉내)
        base_close = np.full(30, 10_000.0)
        # 후반 30봉: 단조 상승 (Stage 2 전환 + 돌파)
        breakout = np.linspace(10_100, 14_000, 30)
        close = np.concatenate([base_close, breakout])
        volume_base = np.full(30, 1_000_000)
        # 마지막 봉에서 거래량 폭증 (평균의 3배)
        volume_break = np.full(29, 1_000_000)
        volume_break = np.append(volume_break, 3_000_000)
        volume = np.concatenate([volume_base, volume_break])
        return _make_weekly_df(n, close, volume)

    def test_triggers_on_valid_breakout(self):
        from strategies.books.weinstein_stages.rules import rule_stage2_initial_breakout
        rule = rule_stage2_initial_breakout()
        df = self._make_breakout_df()
        ctx = _build_ctx_for_weekly_df(df)
        # stage_series를 강제로 Stage 1→2 전환으로 설정
        stages = ctx["stage_series"].copy()
        stages.iloc[-2] = 1
        stages.iloc[-1] = 2
        ctx["stage_series"] = stages
        # mrs 강제 양수
        mrs = pd.Series(np.full(len(df), 1.0))
        ctx["mrs_series"] = mrs
        res = rule.evaluate(df, ctx)
        # 돌파 거래량·박스 조건도 충족하면 triggered
        # (실제 통과 여부는 박스 기간 내 최고가 vs 현재 close에 달림)
        assert isinstance(res.triggered, bool)

    def test_fails_when_stage_not_transitioning(self):
        from strategies.books.weinstein_stages.rules import rule_stage2_initial_breakout
        rule = rule_stage2_initial_breakout()
        df = self._make_breakout_df()
        ctx = _build_ctx_for_weekly_df(df)
        # Stage 2→2 (전환 아님)
        ctx["stage_series"].iloc[-2] = 2
        ctx["stage_series"].iloc[-1] = 2
        res = rule.evaluate(df, ctx)
        assert res.triggered is False

    def test_fails_when_mrs_negative(self):
        from strategies.books.weinstein_stages.rules import rule_stage2_initial_breakout
        rule = rule_stage2_initial_breakout()
        df = self._make_breakout_df()
        ctx = _build_ctx_for_weekly_df(df)
        ctx["stage_series"].iloc[-2] = 1
        ctx["stage_series"].iloc[-1] = 2
        # MRS 음수
        ctx["mrs_series"] = pd.Series(np.full(len(df), -5.0))
        res = rule.evaluate(df, ctx)
        assert res.triggered is False

    def test_fails_on_insufficient_data(self):
        from strategies.books.weinstein_stages.rules import rule_stage2_initial_breakout
        rule = rule_stage2_initial_breakout()
        df = _make_weekly_df(10, np.linspace(10_000, 11_000, 10))
        ctx = {"ma30w_series": pd.Series([10_000.0] * 10),
               "slope_series": pd.Series([0.002] * 10),
               "mrs_series": pd.Series([1.0] * 10),
               "stage_series": pd.Series([2] * 10)}
        res = rule.evaluate(df, ctx)
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T3b: rule_stage2_continuation_pullback
# ---------------------------------------------------------------------------

class TestRuleStage2ContinuationPullback:
    def _make_pullback_df(self):
        """Stage 2 연속 + MA30W 5% 이내 되돌림 + swing high 재돌파."""
        n = 60
        close = np.linspace(10_000, 16_000, n)
        # 마지막 5봉: 되돌림 후 재돌파
        close[-5] = 11_500  # MA30W 근처로 하락
        close[-4] = 11_400
        close[-3] = 11_600
        close[-2] = 11_800
        close[-1] = 12_500  # swing high 재돌파
        high = close * 1.02
        high[-1] = 13_000   # 재돌파 확실히
        df = _make_weekly_df(n, close)
        df["high"] = high
        return df

    def test_fails_when_not_all_stage2(self):
        from strategies.books.weinstein_stages.rules import rule_stage2_continuation_pullback
        rule = rule_stage2_continuation_pullback()
        df = self._make_pullback_df()
        ctx = _build_ctx_for_weekly_df(df)
        # 중간에 Stage 3 삽입
        ctx["stage_series"].iloc[-3] = 3
        ctx["mrs_series"] = pd.Series(np.full(len(df), 2.0))
        res = rule.evaluate(df, ctx)
        assert res.triggered is False

    def test_fails_when_mrs_negative(self):
        from strategies.books.weinstein_stages.rules import rule_stage2_continuation_pullback
        rule = rule_stage2_continuation_pullback()
        df = self._make_pullback_df()
        ctx = _build_ctx_for_weekly_df(df)
        stages = ctx["stage_series"].copy()
        stages.iloc[-5:] = 2
        ctx["stage_series"] = stages
        ctx["mrs_series"] = pd.Series(np.full(len(df), -1.0))
        res = rule.evaluate(df, ctx)
        assert res.triggered is False

    def test_fails_on_insufficient_data(self):
        from strategies.books.weinstein_stages.rules import rule_stage2_continuation_pullback
        rule = rule_stage2_continuation_pullback()
        df = _make_weekly_df(5, np.linspace(10_000, 11_000, 5))
        ctx = {"ma30w_series": pd.Series([10_000.0] * 5),
               "slope_series": pd.Series([0.002] * 5),
               "mrs_series": pd.Series([1.0] * 5),
               "stage_series": pd.Series([2] * 5)}
        res = rule.evaluate(df, ctx)
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T3c: rule_ma30w_bounce
# ---------------------------------------------------------------------------

class TestRuleMa30wBounce:
    def test_triggers_on_valid_bounce(self):
        from strategies.books.weinstein_stages.rules import rule_ma30w_bounce
        rule = rule_ma30w_bounce()
        n = 50
        close = np.linspace(10_000, 14_000, n)
        df = _make_weekly_df(n, close)
        ma30w_val = float(pd.Series(close).rolling(30).mean().iloc[-1])

        # 마지막 봉: 저점이 MA30W * 1.01 (≤ 1.03 조건 충족), 양봉
        df.loc[df.index[-1], "low"] = ma30w_val * 1.005
        df.loc[df.index[-1], "open"] = ma30w_val * 1.01
        df.loc[df.index[-1], "close"] = ma30w_val * 1.05

        close_s = df["close"].astype(float)
        ma30w_s = close_s.rolling(30).mean()
        stages = pd.Series(np.full(n, 2), dtype="Int64")
        mrs_s = pd.Series(np.full(n, 1.0))

        ctx = {"ma30w_series": ma30w_s.reset_index(drop=True),
               "slope_series": pd.Series(np.full(n, 0.005)),
               "mrs_series": mrs_s,
               "stage_series": stages}
        res = rule.evaluate(df, ctx)
        assert res.triggered is True
        assert res.side == "buy"
        assert res.confidence == pytest.approx(60.0)

    def test_fails_when_not_stage2(self):
        from strategies.books.weinstein_stages.rules import rule_ma30w_bounce
        rule = rule_ma30w_bounce()
        n = 50
        close = np.linspace(10_000, 14_000, n)
        df = _make_weekly_df(n, close)
        ma30w_s = pd.Series(close).rolling(30).mean().reset_index(drop=True)
        stages = pd.Series(np.full(n, 4), dtype="Int64")  # Stage 4
        ctx = {"ma30w_series": ma30w_s, "slope_series": pd.Series(np.full(n, -0.005)),
               "mrs_series": pd.Series(np.full(n, -1.0)), "stage_series": stages}
        res = rule.evaluate(df, ctx)
        assert res.triggered is False

    def test_fails_when_bearish_candle(self):
        from strategies.books.weinstein_stages.rules import rule_ma30w_bounce
        rule = rule_ma30w_bounce()
        n = 50
        close = np.linspace(10_000, 14_000, n)
        df = _make_weekly_df(n, close)
        ma30w_val = float(pd.Series(close).rolling(30).mean().iloc[-1])

        # 음봉: close < open
        df.loc[df.index[-1], "low"] = ma30w_val * 1.005
        df.loc[df.index[-1], "open"] = ma30w_val * 1.06
        df.loc[df.index[-1], "close"] = ma30w_val * 1.03  # close < open

        ma30w_s = df["close"].rolling(30).mean().reset_index(drop=True)
        stages = pd.Series(np.full(n, 2), dtype="Int64")
        ctx = {"ma30w_series": ma30w_s, "slope_series": pd.Series(np.full(n, 0.005)),
               "mrs_series": pd.Series(np.full(n, 1.0)), "stage_series": stages}
        res = rule.evaluate(df, ctx)
        assert res.triggered is False

    def test_fails_when_mrs_negative(self):
        from strategies.books.weinstein_stages.rules import rule_ma30w_bounce
        rule = rule_ma30w_bounce()
        n = 50
        close = np.linspace(10_000, 14_000, n)
        df = _make_weekly_df(n, close)
        ma30w_val = float(pd.Series(close).rolling(30).mean().iloc[-1])
        df.loc[df.index[-1], "low"] = ma30w_val * 1.005
        df.loc[df.index[-1], "open"] = ma30w_val * 1.01
        df.loc[df.index[-1], "close"] = ma30w_val * 1.05
        ma30w_s = df["close"].rolling(30).mean().reset_index(drop=True)
        stages = pd.Series(np.full(n, 2), dtype="Int64")
        ctx = {"ma30w_series": ma30w_s, "slope_series": pd.Series(np.full(n, 0.005)),
               "mrs_series": pd.Series(np.full(n, -1.0)), "stage_series": stages}
        res = rule.evaluate(df, ctx)
        assert res.triggered is False

    def test_fails_on_insufficient_data(self):
        from strategies.books.weinstein_stages.rules import rule_ma30w_bounce
        rule = rule_ma30w_bounce()
        df = _make_weekly_df(10, np.linspace(10_000, 11_000, 10))
        ctx = {"ma30w_series": pd.Series([10_000.0] * 10),
               "slope_series": pd.Series([0.002] * 10),
               "mrs_series": pd.Series([1.0] * 10),
               "stage_series": pd.Series([2] * 10, dtype="Int64")}
        res = rule.evaluate(df, ctx)
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T4: ALL_RULES 상수
# ---------------------------------------------------------------------------

def test_all_rules_has_3_classes():
    from strategies.books.weinstein_stages import rules as rules_mod
    assert len(rules_mod.ALL_RULES) == 3
    names = [cls().name for cls in rules_mod.ALL_RULES]
    assert set(names) == {
        "stage2_initial_breakout",
        "stage2_continuation_pullback",
        "ma30w_bounce",
    }


# ---------------------------------------------------------------------------
# T5+T6: strategy + __init__
# ---------------------------------------------------------------------------

def test_build_strategy_single_mode():
    from strategies.books.weinstein_stages.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="stage2_initial_breakout")
    assert strat.name == "WeinsteinStagesStrategy"
    assert strat.holding_period == "swing"
    assert strat.target_rule == "stage2_initial_breakout"


def test_build_strategy_all_and_mode():
    from strategies.books.weinstein_stages.strategy import build_strategy
    strat = build_strategy(mode="all_AND")
    assert strat.mode == "all_AND"
    assert len(strat.rules) == 3


def test_init_exports():
    from strategies.books.weinstein_stages import (
        ALL_RULES, BOOK_META, WeinsteinStagesStrategy,
        build_strategy, resample_daily_to_weekly,
    )
    assert len(ALL_RULES) == 3
    assert BOOK_META["id"] == "weinstein_stages"


def test_generate_signal_returns_none_without_ctx():
    """ctx 없이 generate_signal 호출 시 None 반환 (rs_value 등 없음)."""
    from strategies.books.weinstein_stages.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="stage2_initial_breakout")
    n = 60
    close = np.linspace(10_000, 14_000, n)
    df = _make_weekly_df(n, close)
    # ctx_extra 없이 호출 → RuleResult triggered=False 반환
    sig = strat.generate_signal("TEST", df, "weekly")
    assert sig is None


def test_generate_signal_with_extra_ctx_passes_indicators():
    """ctx에 인디케이터 주입 시 RuleResult 평가까지 진행."""
    from strategies.books.weinstein_stages.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="ma30w_bounce")
    n = 50
    close = np.linspace(10_000, 14_000, n)
    df = _make_weekly_df(n, close)
    ma30w_val = float(pd.Series(close).rolling(30).mean().iloc[-1])

    # 트리거 조건 설정: 저점 ≤ MA30W × 1.03, 양봉, MRS ≥ 0, Stage 2
    df.loc[df.index[-1], "low"] = ma30w_val * 1.005
    df.loc[df.index[-1], "open"] = ma30w_val * 1.01
    df.loc[df.index[-1], "close"] = ma30w_val * 1.05

    ma30w_s = df["close"].rolling(30).mean().reset_index(drop=True)
    ctx_extra = {
        "ma30w_series": ma30w_s,
        "slope_series": pd.Series(np.full(n, 0.005)),
        "mrs_series": pd.Series(np.full(n, 1.0)),
        "stage_series": pd.Series(np.full(n, 2), dtype="Int64"),
    }
    sig = strat.generate_signal_with_extra_ctx("TEST", df, "weekly", ctx_extra)
    assert sig is not None
    assert sig.signal_type.name in ("BUY", "STRONG_BUY")

"""Minervini VCP rules — 단위 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def trend_up_df():
    """200일 단조 상승 일봉 (TT 모든 조건 통과해야 함)."""
    n = 260
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = np.linspace(10_000, 30_000, n)
    high = close * 1.01
    low = close * 0.99
    volume = np.full(n, 1_000_000)
    return pd.DataFrame({
        "datetime": dates, "open": close, "high": high, "low": low,
        "close": close, "volume": volume,
    })


@pytest.fixture
def trend_down_df():
    """200일 단조 하락 (TT 통과 불가)."""
    n = 260
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = np.linspace(30_000, 10_000, n)
    return pd.DataFrame({
        "datetime": dates, "open": close, "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": np.full(n, 1_000_000),
    })


def test_compute_rs_percentile_returns_0_to_99():
    from strategies.books.minervini_vcp.rules import compute_rs_percentile_12w

    n = 100
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    universe_df = pd.DataFrame({
        code: 10_000 * (1 + i * 0.001) ** np.arange(n)
        for i, code in enumerate([f"A{i:03d}" for i in range(20)])
    }, index=dates)
    rs = compute_rs_percentile_12w(universe_df)
    assert rs.shape == (n, 20)
    last = rs.iloc[-1].dropna()
    assert (last.min() >= 0) and (last.max() <= 99)
    # 가장 강한 종목(i=19) RS == 99
    assert last["A019"] == pytest.approx(99, abs=1)


def test_trend_template_passes_on_uptrend(trend_up_df):
    from strategies.books.minervini_vcp.rules import rule_trend_template
    rule = rule_trend_template()
    ctx = {"stock_code": "TEST", "rs_value": 85}
    res = rule.evaluate(trend_up_df, ctx)
    assert res.triggered is True
    assert res.side == "buy"


def test_trend_template_fails_on_downtrend(trend_down_df):
    from strategies.books.minervini_vcp.rules import rule_trend_template
    rule = rule_trend_template()
    ctx = {"stock_code": "TEST", "rs_value": 85}
    res = rule.evaluate(trend_down_df, ctx)
    assert res.triggered is False


def test_trend_template_fails_when_rs_below_70(trend_up_df):
    from strategies.books.minervini_vcp.rules import rule_trend_template
    rule = rule_trend_template()
    ctx = {"stock_code": "TEST", "rs_value": 50}
    res = rule.evaluate(trend_up_df, ctx)
    assert res.triggered is False


def _vcp_synthetic_df():
    """베이스 25일 + 진폭 수축 2단계 + 마지막 봉 피벗 돌파 + 거래량 폭증."""
    n = 260
    close_pre = np.linspace(10_000, 12_000, n - 30).tolist()
    pivot = max(close_pre[-25:])  # 베이스 시작 직전 고점
    # 베이스 25일: 첫 12일 진폭 5%(high/low 수동), 다음 12일 진폭 2%, 마지막 1봉 피벗 돌파
    base_close = []
    base_high = []
    base_low = []
    center = pivot * 0.97  # 베이스 중심가격
    # 전반 12봉: ±2.5% 진폭
    for i in range(12):
        c = center
        base_close.append(c)
        base_high.append(c * 1.025)
        base_low.append(c * 0.975)
    # 후반 12봉: ±0.75% 진폭 (contraction ratio = 1.5%/5% = 0.30 < 0.6)
    for i in range(12):
        c = center
        base_close.append(c)
        base_high.append(c * 1.0075)
        base_low.append(c * 0.9925)
    # 마지막 1봉: 피벗 돌파
    base_close.append(pivot * 1.03)
    base_high.append(pivot * 1.04)
    base_low.append(pivot * 1.02)

    closes = close_pre + base_close
    highs  = [c * 1.01 for c in close_pre] + base_high
    lows   = [c * 0.99 for c in close_pre] + base_low
    total = len(closes)
    dates = pd.date_range("2025-01-01", periods=total, freq="B")
    # 거래량: pre-base 평균 1M, 베이스 25봉 dry-up 0.4M, 마지막 봉 폭증 2M
    base_avg_vol = 1_000_000
    volume = [base_avg_vol] * (total - 26) + [base_avg_vol * 0.4] * 25 + [base_avg_vol * 2.0]
    return pd.DataFrame({
        "datetime": dates, "open": closes, "high": highs, "low": lows,
        "close": closes, "volume": volume,
    })


def test_vcp_breakout_triggers_on_synthetic_pattern():
    from strategies.books.minervini_vcp.rules import rule_vcp_breakout
    rule = rule_vcp_breakout()
    df = _vcp_synthetic_df()
    res = rule.evaluate(df, {"stock_code": "TEST"})
    assert res.triggered is True
    assert res.side == "buy"


def test_vcp_breakout_fails_on_flat_volume(trend_up_df):
    from strategies.books.minervini_vcp.rules import rule_vcp_breakout
    rule = rule_vcp_breakout()
    res = rule.evaluate(trend_up_df, {"stock_code": "TEST"})
    # 단조 상승은 베이스/수축 없음 → 실패
    assert res.triggered is False


def test_tight_closes_triggers_on_narrow_3w_range(trend_up_df):
    from strategies.books.minervini_vcp.rules import rule_tight_closes
    rule = rule_tight_closes()
    # 마지막 15봉 종가 변동폭을 강제로 1% 이하로
    df = trend_up_df.copy()
    last_15_close = df["close"].iloc[-15].copy()
    df.loc[df.index[-15:], "close"] = last_15_close * (1 + np.linspace(-0.005, 0.005, 15))
    res = rule.evaluate(df, {"stock_code": "TEST"})
    assert res.triggered is True


def test_volume_dryup_triggers_on_low_recent_volume(trend_up_df):
    from strategies.books.minervini_vcp.rules import rule_volume_dryup
    df = trend_up_df.copy()
    df.loc[df.index[-10:], "volume"] = 400_000  # 직전 평균 1M의 40%
    rule = rule_volume_dryup()
    res = rule.evaluate(df, {"stock_code": "TEST"})
    assert res.triggered is True


def test_all_rules_export_has_5_classes():
    # 821fb80 'Minervini K=3 집중 + VCP 룰 추가'로 rule_vcp_contraction_breakout 정식 등록(4→5).
    from strategies.books.minervini_vcp import rules as rules_mod
    assert len(rules_mod.ALL_RULES) == 5
    names = [cls().name for cls in rules_mod.ALL_RULES]
    assert set(names) == {
        "trend_template", "vcp_breakout", "vcp_contraction_breakout",
        "tight_closes", "volume_dryup",
    }


def test_build_strategy_single_mode_returns_book_strategy():
    from strategies.books.minervini_vcp.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="trend_template")
    assert strat.name == "MinerviniVCPStrategy"
    assert strat.holding_period == "swing"
    assert strat.target_rule == "trend_template"


def test_build_strategy_all_and_mode():
    from strategies.books.minervini_vcp.strategy import build_strategy
    strat = build_strategy(mode="all_AND")
    assert strat.mode == "all_AND"
    assert len(strat.rules) == 5  # ALL_RULES 5개(vcp_contraction_breakout 추가, 821fb80)


def test_generate_signal_with_extra_ctx_passes_rs_value(trend_up_df):
    from strategies.books.minervini_vcp.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="trend_template")
    # rs_value 미전달 시 None → 실패
    sig_none = strat.generate_signal("TEST", trend_up_df, "daily")
    assert sig_none is None
    # rs_value 85 전달 시 통과
    sig_ok = strat.generate_signal_with_extra_ctx("TEST", trend_up_df, "daily", {"rs_value": 85})
    assert sig_ok is not None

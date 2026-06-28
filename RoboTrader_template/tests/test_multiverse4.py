"""MULTIVERSE4 (7전략 합성·워크포워드·부트스트랩·비용) 테스트.

대상:
  scripts/multiverse4_returns_export.py  — 전략 스펙 레지스트리(라이브 정합) + 비용 패치
  scripts/multiverse4_portfolio_analysis.py — 합성/상관/워크포워드/부트스트랩 헬퍼
DB 불요(순수 함수 + 토이 데이터). 실데이터 검증은 스모크/풀런에서 별도.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.multiverse4_returns_export import SPECS, _patch_costs  # noqa: E402
from scripts.multiverse4_portfolio_analysis import (  # noqa: E402
    block_bootstrap_metrics,
    combine_equal_weight_rebal,
    combine_sum_of_equities,
    corr_matrix,
    maxdd_from_returns,
    tail_coloss_lift,
)

LIVE_8 = {
    "elder_ema_pullback", "book_envelope_200d", "daytrading_3methods_breakout",
    "minervini_volume_dryup", "book_pullback_ma20", "book_pullback_ma5", "rs_leader",
    "deep_mr_dev20",
}


# ---------------------------------------------------------------------------
# 스펙 레지스트리 — 라이브 config.yaml 값과 1:1 (드리프트 가드)
# ---------------------------------------------------------------------------

def test_specs_cover_live_8():
    assert set(SPECS.keys()) == LIVE_8


@pytest.mark.parametrize("name,sl,tp,mh,k", [
    ("elder_ema_pullback", 0.08, 0.30, 100, 20),
    ("book_envelope_200d", 0.08, 0.10, 10, 5),
    ("daytrading_3methods_breakout", 0.10, 0.10, 10, 5),
    ("minervini_volume_dryup", 0.08, 0.12, 20, 3),
    ("book_pullback_ma20", 0.08, 0.10, 50, 5),
    ("book_pullback_ma5", 0.03, 0.15, 30, 5),
    ("rs_leader", 0.08, 99.0, 30, 10),  # tp99=무효(추세추종, 트레일이 주청산)
    ("deep_mr_dev20", 0.07, 0.12, 7, 5),  # sl7/tp12/max_hold7 = config.yaml risk_management 1:1
])
def test_specs_match_live_exit_params(name, sl, tp, mh, k):
    spec = SPECS[name]
    assert spec.params["stop_loss_pct"] == pytest.approx(sl)
    assert spec.params["take_profit_pct"] == pytest.approx(tp)
    assert spec.params["max_hold_bars"] == mh
    assert spec.K == k


def test_specs_trailing_exits_match_live():
    # 라이브 trail: ma20=20, ma5=5, elder=EMA13+trend_flip, rs_leader=MA20트레일 어댑터
    assert SPECS["book_pullback_ma20"].params.get("trail_ma") == 20
    assert SPECS["book_pullback_ma5"].params.get("trail_ma") == 5
    assert SPECS["elder_ema_pullback"].params.get("trail_ema") == 13
    assert SPECS["elder_ema_pullback"].params.get("trend_flip_exit") is True
    assert type(SPECS["rs_leader"].adapter).__name__ == "MA20TrailExitAdapter"
    # deep_mr: MA20×0.9 회복 청산 어댑터 (라이브 evaluate_sell_conditions ma_recovery 정합)
    dm = SPECS["deep_mr_dev20"].adapter
    assert type(dm).__name__ == "MAReversionExitAdapter"
    assert dm.ma == 20 and dm.recovery_ratio == pytest.approx(0.9)
    # 고정 sl/tp/mh 전략(라이브 트레일 없음)은 범용 어댑터
    for name in ("book_envelope_200d", "daytrading_3methods_breakout"):
        assert type(SPECS[name].adapter).__name__ == "_SLTPMHAdapter"


# ---------------------------------------------------------------------------
# 비용 패치 (축4) — portfolio_sim 모듈 상수 패치가 실제 체결가/수수료에 반영되는지
# ---------------------------------------------------------------------------

def _toy_market_run(initial=10_000_000.0):
    """1종목 토이: i=2 신호 → i=3 시가 진입 → tp 즉시충족 → i=4 시가 청산."""
    from scripts.book_portfolio_multiverse import _SLTPMHAdapter
    from scripts.exit_multiverse.portfolio_sim import run_portfolio
    n = 8
    df = pd.DataFrame({
        "datetime": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": [100.0] * 3 + [100.0, 120.0, 120.0, 120.0, 120.0],
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.0] * 3 + [120.0, 120.0, 120.0, 120.0, 120.0],
        "volume": [1000.0] * n,
    })
    data = {"TOY": df}
    cache = {"TOY": [2]}
    params = dict(stop_loss_pct=0.5, take_profit_pct=0.10, max_hold_bars=99)
    return run_portfolio(data=data, signal_cache=cache, adapter=_SLTPMHAdapter(),
                         params=params, turnover={"TOY": 1.0},
                         initial_capital=initial, max_positions=1,
                         max_per_stock=initial)


def test_patch_costs_zero_beats_default():
    import scripts.exit_multiverse.portfolio_sim as ps
    base = _toy_market_run()["equity_curve"][-1]
    with _patch_costs(commission=0.0, tax=0.0, slippage=0.0):
        free = _toy_market_run()["equity_curve"][-1]
    # 패치 복원 확인
    assert ps.COMMISSION_RATE == 0.00015 and ps.TAX_RATE == 0.0018 and ps.SLIPPAGE_RATE == 0.001
    assert free > base


# ---------------------------------------------------------------------------
# 합성 포트폴리오 헬퍼 (축1)
# ---------------------------------------------------------------------------

def _toy_returns():
    idx = pd.date_range("2024-01-01", periods=4, freq="D")
    a = pd.Series([0.10, 0.0, 0.0, 0.0], index=idx)
    b = pd.Series([0.0, 0.10, 0.0, 0.0], index=idx)
    return {"A": a, "B": b}


def test_combine_sum_of_equities_no_rebalance():
    # 라이브 모델: 전략별 독립 1천만 계좌 합산(리밸런스 없음).
    rets = _toy_returns()
    combined = combine_sum_of_equities(rets, initial_per_strategy=10_000_000.0)
    eq = 10_000_000.0 * 2 * (1.0 + combined).cumprod()
    # day1: A만 +10% → 총 21M, day2: B만 +10% → 22M (각 계좌 독립)
    assert eq.iloc[0] == pytest.approx(21_000_000.0)
    assert eq.iloc[1] == pytest.approx(22_000_000.0)
    assert eq.iloc[-1] == pytest.approx(22_000_000.0)


def test_combine_equal_weight_rebal_is_mean():
    rets = _toy_returns()
    combined = combine_equal_weight_rebal(rets)
    assert combined.iloc[0] == pytest.approx(0.05)
    assert combined.iloc[1] == pytest.approx(0.05)


def test_corr_matrix_symmetric_diag1():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-01", periods=200, freq="D")
    rets = {k: pd.Series(rng.normal(0, 0.01, 200), index=idx) for k in "ABC"}
    m = corr_matrix(rets)
    assert np.allclose(m.values, m.values.T, equal_nan=True)
    assert np.allclose(np.diag(m.values), 1.0)


def test_tail_coloss_lift_perfect_overlap():
    idx = pd.date_range("2024-01-01", periods=100, freq="D")
    base = pd.Series(np.linspace(-0.05, 0.05, 100), index=idx)
    lift = tail_coloss_lift(base, base.copy(), q=0.10)
    assert lift == pytest.approx(1.0 / 0.10)  # 동일 시리즈 → 조건부확률 1.0 → lift=10


def test_maxdd_from_returns():
    r = pd.Series([0.10, -0.50, 0.0])
    assert maxdd_from_returns(r) == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# 부트스트랩 (축5) — seed 재현성 + 출력 스키마
# ---------------------------------------------------------------------------

def test_block_bootstrap_deterministic_and_sane():
    rng_idx = pd.date_range("2024-01-01", periods=300, freq="D")
    rets = pd.Series(np.random.default_rng(1).normal(0.001, 0.01, 300), index=rng_idx)
    m1 = block_bootstrap_metrics(rets, n_iter=50, block=21, seed=42)
    m2 = block_bootstrap_metrics(rets, n_iter=50, block=21, seed=42)
    assert m1 == m2
    for key in ("sharpe_p05", "sharpe_p50", "sharpe_p95",
                "maxdd_p05", "maxdd_p50", "maxdd_p95"):
        assert key in m1
    assert m1["sharpe_p05"] <= m1["sharpe_p50"] <= m1["sharpe_p95"]
    assert m1["maxdd_p05"] <= m1["maxdd_p50"] <= m1["maxdd_p95"]


# ---------------------------------------------------------------------------
# _monthly_scan_dates 헬퍼 (PIT 스크리너 캐던스)
# ---------------------------------------------------------------------------

def test_monthly_scan_dates_basic():
    from scripts.multiverse4_returns_export import _monthly_scan_dates
    out = _monthly_scan_dates("2024-01-15", "2024-04-10")
    assert out[0] == "2024-01-15"
    assert "2024-02-29" in out          # 2024 윤년 2월 말일
    assert "2024-03-31" in out
    assert out[-1] == "2024-04-10"
    assert out == sorted(out)
    assert len(out) == len(set(out))    # 중복 없음

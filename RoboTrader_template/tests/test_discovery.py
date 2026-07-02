"""전략 발굴 파이프라인 배치1 테스트 (spec: docs/superpowers/specs/2026-06-11-strategy-discovery-pipeline.md).

대상:
  scripts/discovery/rules.py         — 후보 4종 진입룰 (no-lookahead, 트리거 단위검증)
  scripts/discovery/exit_adapters.py — 후보 청산 어댑터 (run_portfolio 규약)
  scripts/strategy_gate.py           — 게이트 판정 순수함수 + 후보 레지스트리
DB 불요 (전부 합성 토이 데이터).
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

from scripts.discovery.exit_adapters import (  # noqa: E402
    BBReversionExitAdapter,
    CloseAboveMAExitAdapter,
    MAReversionExitAdapter,
)
from scripts.discovery.rules import (  # noqa: E402
    BBReversionRule,
    MeanReversionMA20Rule,
    NDownVolSurgeRule,
    OversoldRSI2Rule,
    RSI2PureRule,
    StrengthClose1DRule,
    ThreeDownBounceRule,
    TurnOfMonthRule,
    _is_last_trading_day,
    _trading_ordinal,
)
from scripts.strategy_gate import (  # noqa: E402
    CANDIDATES,
    GATE_THRESHOLDS,
    evaluate_gates,
)
from strategies.base import SignalType  # noqa: E402


# ---------------------------------------------------------------------------
# 토이 데이터 헬퍼
# ---------------------------------------------------------------------------

def _df(close, high=None, low=None, open_=None, volume=None):
    n = len(close)
    close = pd.Series(close, dtype=float)
    return pd.DataFrame({
        "datetime": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": open_ if open_ is not None else close,
        "high": high if high is not None else close * 1.01,
        "low": low if low is not None else close * 0.99,
        "close": close,
        "volume": volume if volume is not None else [1000.0] * n,
    })


def _no_lookahead(rule, df):
    """미래봉 절단 불변성: 윈도우 [:i+1] 평가가 그 뒤 데이터와 무관."""
    i = len(df) - 3
    full_window = df.iloc[: i + 1]
    sig_a = rule.generate_signal("TOY", full_window)
    mutated = df.copy()
    mutated.loc[mutated.index[-1], "close"] = 1.0  # 미래봉 변조
    sig_b = rule.generate_signal("TOY", mutated.iloc[: i + 1])
    assert (sig_a is None) == (sig_b is None)


# ---------------------------------------------------------------------------
# ① oversold_rsi2 — Connors RSI-2 (RSI(2)<10 AND close>SMA200)
# ---------------------------------------------------------------------------

def _connors_df(dip=True):
    # 210봉 완만 상승(SMA200 위) 후 마지막 2봉 급락 → RSI(2) 과락
    n = 212
    base = np.linspace(100, 160, n)
    if dip:
        base[-2] = base[-3] * 0.97
        base[-1] = base[-2] * 0.97
    return _df(base)


def test_rsi2_triggers_on_dip_above_sma200():
    rule = OversoldRSI2Rule()
    sig = rule.generate_signal("TOY", _connors_df(dip=True))
    assert sig is not None and sig.signal_type == SignalType.BUY


def test_rsi2_no_trigger_without_dip():
    rule = OversoldRSI2Rule()
    assert rule.generate_signal("TOY", _connors_df(dip=False)) is None


def test_rsi2_no_trigger_below_sma200():
    # 하락추세(종가 < SMA200)에선 과락이어도 미발사
    n = 212
    base = np.linspace(200, 100, n)
    base[-1] = base[-2] * 0.95
    rule = OversoldRSI2Rule()
    assert rule.generate_signal("TOY", _df(base)) is None


def test_rsi2_no_lookahead():
    _no_lookahead(OversoldRSI2Rule(), _connors_df(dip=True))


# ---------------------------------------------------------------------------
# ② strength_close_1d — 강세마감(양봉+레인지상단25%+거래량1.5x) 익일보유
# ---------------------------------------------------------------------------

def _strength_df(strong=True):
    n = 30
    close = np.full(n, 100.0)
    vol = np.full(n, 1000.0)
    open_ = np.full(n, 100.0)
    high = np.full(n, 101.0)
    low = np.full(n, 99.0)
    if strong:
        open_[-1], low[-1], high[-1], close[-1] = 100.0, 99.5, 110.0, 109.0  # 상단 25% 양봉
        vol[-1] = 2000.0
    return _df(close, high=high, low=low, open_=open_, volume=vol)


def test_strength_triggers():
    rule = StrengthClose1DRule()
    sig = rule.generate_signal("TOY", _strength_df(strong=True))
    assert sig is not None and sig.signal_type == SignalType.BUY


def test_strength_no_trigger_weak_close():
    df = _strength_df(strong=True)
    df.loc[df.index[-1], "close"] = 101.0  # 레인지 하단 마감
    assert StrengthClose1DRule().generate_signal("TOY", df) is None


def test_strength_no_trigger_low_volume():
    df = _strength_df(strong=True)
    df.loc[df.index[-1], "volume"] = 1100.0  # < 1.5x
    assert StrengthClose1DRule().generate_signal("TOY", df) is None


def test_strength_no_lookahead():
    _no_lookahead(StrengthClose1DRule(), _strength_df(strong=True))


# ---------------------------------------------------------------------------
# ③ bb_reversion — 템플릿 verbatim (BB하단+RSI14<40+ADX14<20+vol1.2x)
# ---------------------------------------------------------------------------

def _bb_df():
    # 횡보(저ADX) 후 마지막 봉 하단 이탈 + 거래량 증가
    # 진폭 1.5→0.5로 축소: ADX14가 임계값(20) 근처 경계선(21.28, 마진 -1.28)에
    # 걸리던 취약 픽스처를 확실한 횡보(ADX≈11, 마진 ~9)로 강화 (4조건 전부 여유 확보).
    n = 60
    rng = np.random.default_rng(7)
    close = 100.0 + np.sin(np.linspace(0, 12, n)) * 0.5 + rng.normal(0, 0.3, n)
    close[-1] = close[:-1].min() - 4.0  # BB 하단 관통 + RSI 급락
    vol = np.full(n, 1000.0)
    vol[-1] = 1500.0
    return _df(close, volume=vol)


def test_bb_reversion_triggers():
    sig = BBReversionRule().generate_signal("TOY", _bb_df())
    assert sig is not None and sig.signal_type == SignalType.BUY


def test_bb_reversion_no_trigger_above_band():
    df = _bb_df()
    df.loc[df.index[-1], "close"] = 100.0  # 밴드 안
    assert BBReversionRule().generate_signal("TOY", df) is None


def test_bb_reversion_no_lookahead():
    _no_lookahead(BBReversionRule(), _bb_df())


# ---------------------------------------------------------------------------
# ④ mean_reversion_ma20 — 템플릿 verbatim (MA20 -10% 이탈 + RSI14<30)
# ---------------------------------------------------------------------------

def _mr_df(deviation=-0.12):
    n = 30
    close = np.full(n, 100.0)
    # 마지막 3봉 연속 하락으로 RSI<30 + MA 이탈 동시 충족
    close[-3] = 96.0
    close[-2] = 92.0
    close[-1] = 100.0 * (1.0 + deviation) * (20.0 + 1 + deviation) / 21.0  # 근사 — 정확값은 룰이 판정
    close[-1] = 87.0 if deviation <= -0.10 else 95.0
    return _df(close)


def test_mean_reversion_triggers():
    sig = MeanReversionMA20Rule().generate_signal("TOY", _mr_df(deviation=-0.12))
    assert sig is not None and sig.signal_type == SignalType.BUY


def test_mean_reversion_no_trigger_small_deviation():
    assert MeanReversionMA20Rule().generate_signal("TOY", _mr_df(deviation=-0.05)) is None


def test_mean_reversion_no_lookahead():
    _no_lookahead(MeanReversionMA20Rule(), _mr_df(deviation=-0.12))


# ---------------------------------------------------------------------------
# 청산 어댑터 (run_portfolio 규약: exit_reason(df, i, position, params))
# ---------------------------------------------------------------------------

def test_close_above_ma_exit():
    # 진입 후 종가가 SMA5 위로 → 청산. 그 전엔 보유.
    close = [100, 100, 100, 100, 100, 90, 91, 120]
    df = _df(close)
    ad = CloseAboveMAExitAdapter(ma=5)
    pos = {"entry_idx": 5, "entry_price": 90.0}
    params = dict(stop_loss_pct=99.0, take_profit_pct=99.0, max_hold_bars=20)
    assert ad.exit_reason(df, 6, pos, params) is None       # 91 < SMA5
    assert ad.exit_reason(df, 7, pos, params) == "ma_recovery"  # 120 > SMA5


def test_ma_reversion_exit_recovery():
    # 회복 청산: close >= MA20 × 0.9
    close = [100.0] * 25
    close[-1] = 91.0  # MA20≈99.5 → 0.9×MA=89.6 → 91>=89.6 청산
    df = _df(close)
    ad = MAReversionExitAdapter(ma=20, recovery_ratio=0.9)
    pos = {"entry_idx": 20, "entry_price": 85.0}
    params = dict(stop_loss_pct=0.07, take_profit_pct=0.12, max_hold_bars=7)
    assert ad.exit_reason(df, len(df) - 1, pos, params) == "ma_recovery"


def test_bb_exit_priority_stop_loss_first():
    close = [100.0] * 45
    close[-1] = 80.0
    df = _df(close)
    ad = BBReversionExitAdapter()
    pos = {"entry_idx": 40, "entry_price": 100.0}
    params = dict(stop_loss_pct=0.03, take_profit_pct=0.05, max_hold_bars=15)
    assert ad.exit_reason(df, len(df) - 1, pos, params) == "stop_loss"


# ---------------------------------------------------------------------------
# 게이트 판정 (순수함수) — spec G2~G5 임계값
# ---------------------------------------------------------------------------

def _passing_metrics():
    return dict(
        pnl=0.5, sharpe=0.6, n_trades=200, monthly_trades=15.0,  # G2 (+월10회 제약)
        corr_combo=0.3, tail_lift_combo=1.8, delta_sharpe=0.05,  # G3
        wf_pos=8, wf_total=11, wf_worst=-0.10,                   # G4-1
        boot_sharpe_p05=0.1,                                     # G4-2
        cost30_pnl=0.2,                                          # G4-3
        perturb_pnls=[0.3, 0.4, 0.5, 0.45, 0.35],                # G5-1
        oos_train_sharpe=0.5, oos_test_sharpe=0.7,               # G5-2
    )


def test_evaluate_gates_all_pass():
    res = evaluate_gates(_passing_metrics())
    assert all(ok for ok, _ in res.values()), res


@pytest.mark.parametrize("key,bad,gate", [
    ("sharpe", 0.3, "G2"),
    ("n_trades", 50, "G2"),
    ("pnl", -0.1, "G2"),
    ("monthly_trades", 7.0, "G2"),
    ("corr_combo", 0.6, "G3"),
    ("tail_lift_combo", 3.0, "G3"),
    ("delta_sharpe", -0.01, "G3"),
    ("wf_pos", 5, "G4_walkforward"),
    ("wf_worst", -0.30, "G4_walkforward"),
    ("boot_sharpe_p05", -0.05, "G4_bootstrap"),
    ("cost30_pnl", -0.10, "G4_cost"),
    ("perturb_pnls", [0.3, -0.1, 0.5, 0.4, 0.3], "G5_perturb"),
    ("oos_test_sharpe", -0.2, "G5_oos"),
])
def test_evaluate_gates_single_failure(key, bad, gate):
    m = _passing_metrics()
    m[key] = bad
    res = evaluate_gates(m)
    assert not res[gate][0], f"{gate} should FAIL when {key}={bad}"
    others = {g: v for g, v in res.items() if g != gate}
    assert all(ok for ok, _ in others.values()), f"only {gate} should fail: {res}"


BATCH1 = {"oversold_rsi2", "strength_close_1d", "bb_reversion", "mean_reversion_ma20"}
BATCH2 = {f"{c}_{h}" for c in ("three_down_bounce", "rsi2_pure", "turn_of_month")
          for h in ("h1", "h2")}
BATCH3 = ({f"deep_down_n{n}_{h}" for n in (4, 5, 6, 7) for h in ("h1", "h2")}
          | {"deep_mr_dev12", "deep_mr_dev15", "deep_mr_dev20", "confluence_n4vol2_h2"})


def test_candidates_registry():
    assert BATCH1 | BATCH2 | BATCH3 <= set(CANDIDATES.keys())
    for name, spec in CANDIDATES.items():
        assert spec.K == 5, name
        assert len(spec.perturb) == 5, f"{name} 섭동 5점"
        assert callable(spec.build_signals)


def test_batch3_specs():
    # spec 부록A: top300 · G3=dsharpe_only · 보유/청산 사양
    for name in BATCH3:
        spec = CANDIDATES[name]
        assert spec.top_n == 300, name
        assert spec.g3_mode == "dsharpe_only", name
    assert CANDIDATES["deep_down_n5_h1"].params["max_hold_bars"] == 0
    assert CANDIDATES["deep_down_n5_h2"].params["max_hold_bars"] == 1
    assert CANDIDATES["confluence_n4vol2_h2"].params["max_hold_bars"] == 1
    # B는 템플릿 verbatim 청산 (MA회복)
    assert CANDIDATES["deep_mr_dev15"].params["stop_loss_pct"] == pytest.approx(0.07)
    assert type(CANDIDATES["deep_mr_dev15"].adapter).__name__ == "MAReversionExitAdapter"


def test_batch2_hold_semantics():
    # h1 = mh0 (시가→익일시가 1거래일), h2 = mh1 (2거래일). 순수 시간청산(sl/tp 무효).
    for c in ("three_down_bounce", "rsi2_pure", "turn_of_month"):
        s1, s2 = CANDIDATES[f"{c}_h1"], CANDIDATES[f"{c}_h2"]
        assert s1.params["max_hold_bars"] == 0 and s2.params["max_hold_bars"] == 1
        for s in (s1, s2):
            assert s.params["stop_loss_pct"] == 99.0
            assert s.params["take_profit_pct"] == 99.0


# ---------------------------------------------------------------------------
# 배치2 ⑤ three_down_bounce — N일 연속 종가 하락 → 익일 시가 매수
# ---------------------------------------------------------------------------

def _down_df(n_down=3):
    n = 30
    close = np.full(n, 100.0)
    for k in range(n_down):
        close[-(n_down - k)] = close[-(n_down - k) - 1] * 0.99
    return _df(close)


def test_three_down_triggers():
    sig = ThreeDownBounceRule().generate_signal("TOY", _down_df(3))
    assert sig is not None and sig.signal_type == SignalType.BUY


def test_three_down_no_trigger_two_down():
    assert ThreeDownBounceRule().generate_signal("TOY", _down_df(2)) is None


def test_three_down_no_lookahead():
    df = _down_df(3)
    # 마지막 3봉이 하락이도록 i 위치를 트리거 지점에 맞춤
    i = len(df) - 1
    full = df.iloc[: i + 1]
    rule = ThreeDownBounceRule()
    sig_a = rule.generate_signal("TOY", full)
    df2 = pd.concat([df, df.tail(1)], ignore_index=True)
    df2.loc[df2.index[-1], "close"] = 1.0
    sig_b = rule.generate_signal("TOY", df2.iloc[: i + 1])
    assert (sig_a is None) == (sig_b is None)


# ---------------------------------------------------------------------------
# 배치2 ⑥ rsi2_pure — RSI(2)<10 (추세필터 없음 — 배치1 corr 0.89 가설 검정)
# ---------------------------------------------------------------------------

def test_rsi2_pure_triggers_even_below_sma200():
    # 하락추세(close<SMA200)에서도 과락이면 발사 — 배치1 oversold_rsi2 와의 차이점
    n = 212
    base = np.linspace(200, 100, n)
    base[-2] = base[-3] * 0.95
    base[-1] = base[-2] * 0.95
    sig = RSI2PureRule().generate_signal("TOY", _df(base))
    assert sig is not None and sig.signal_type == SignalType.BUY


def test_rsi2_pure_no_trigger_on_rise():
    assert RSI2PureRule().generate_signal("TOY", _connors_df(dip=False)) is None


# ---------------------------------------------------------------------------
# 배치2 ⑦ turn_of_month — 체결일(익일)이 월초/월말 거래일
# ---------------------------------------------------------------------------

def test_calendar_helpers():
    import datetime as dt
    # 2024-01-31(수)=1월 마지막 거래일, 2024-02-01(목)=2월 1번째 거래일
    assert _is_last_trading_day(dt.date(2024, 1, 31))
    assert not _is_last_trading_day(dt.date(2024, 1, 30))
    assert _trading_ordinal(dt.date(2024, 2, 1)) == 1
    assert _trading_ordinal(dt.date(2024, 2, 2)) == 2


def _dated_df(end_date: str, n: int = 30):
    dates = pd.bdate_range(end=end_date, periods=n)
    close = np.full(n, 100.0)
    return pd.DataFrame({"datetime": dates, "open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close, "volume": [1000.0] * n})


def test_tom_offset0_triggers_before_month_first_day():
    # 신호봉=2024-01-31 → 체결일 2024-02-01 = 월 1번째 거래일 (offset 0)
    rule = TurnOfMonthRule(entry_offset=0)
    sig = rule.generate_signal("TOY", _dated_df("2024-01-31"))
    assert sig is not None and sig.signal_type == SignalType.BUY
    assert rule.generate_signal("TOY", _dated_df("2024-01-30")) is None


def test_tom_offset_minus1_triggers_before_last_day():
    # 신호봉=2024-01-30 → 체결일 2024-01-31 = 월 마지막 거래일 (offset -1)
    rule = TurnOfMonthRule(entry_offset=-1)
    assert rule.generate_signal("TOY", _dated_df("2024-01-30")) is not None
    assert rule.generate_signal("TOY", _dated_df("2024-01-31")) is None


def test_gate_thresholds_match_spec():
    t = GATE_THRESHOLDS
    assert t["g2_sharpe_min"] == 0.4 and t["g2_trades_min"] == 100
    assert t["g2_monthly_trades_min"] == 10.0       # 배치3 사장님 지시
    assert t["g3_corr_max"] == 0.5 and t["g3_lift_max"] == 2.5
    assert t["g4_wf_pos_min_ratio"] == pytest.approx(7 / 11)
    assert t["g4_wf_worst_min"] == -0.15
    assert t["g4_cost_slippage"] == 0.003
    assert t["edge_gross_adopt"] == 0.005 and t["edge_gross_etf"] == 0.002


def test_g3_dsharpe_only_mode():
    # 단기보유 모드: corr/lift 가 높아도 ΔSharpe>0 이면 G3 PASS (spec 부록A)
    m = _passing_metrics()
    m.update(corr_combo=0.9, tail_lift_combo=4.0, delta_sharpe=0.02, g3_mode="dsharpe_only")
    res = evaluate_gates(m)
    assert res["G3"][0], res["G3"]
    m["delta_sharpe"] = -0.01
    assert not evaluate_gates(m)["G3"][0]


def test_g2_monthly_optional_for_legacy():
    # monthly_trades 미제공(배치1·2 레거시 메트릭)이면 빈도 게이트 미적용
    m = _passing_metrics()
    del m["monthly_trades"]
    assert evaluate_gates(m)["G2"][0]


# ---------------------------------------------------------------------------
# 사이징 시나리오 헬퍼 (scripts/discovery/sizing_scenarios.py)
# ---------------------------------------------------------------------------

def test_bootstrap_dd_probs_deterministic_and_schema():
    from scripts.discovery.sizing_scenarios import bootstrap_dd_probs
    idx = pd.date_range("2024-01-01", periods=300, freq="D")
    rets = pd.Series(np.random.default_rng(3).normal(0.0, 0.02, 300), index=idx)
    a = bootstrap_dd_probs(rets, n_iter=50, seed=42)
    b = bootstrap_dd_probs(rets, n_iter=50, seed=42)
    assert a == b
    for k in ("maxdd_p50", "maxdd_p95", "p_dd_ge_30", "p_dd_ge_50"):
        assert k in a
    assert 0.0 <= a["p_dd_ge_30"] <= 1.0
    assert a["maxdd_p50"] <= a["maxdd_p95"]
    assert a["p_dd_ge_50"] <= a["p_dd_ge_30"]  # 단조: 깊은 DD 확률이 더 작거나 같다


def test_periodic_stats_monthly_compound():
    from scripts.discovery.sizing_scenarios import periodic_stats
    # 매 거래일 +0.2% → 월 ~+4% (전 월 +3% 초과), 주 ~+1% (3% 미달)
    idx = pd.bdate_range("2024-01-01", periods=260)
    s = periodic_stats(pd.Series(0.002, index=idx))
    assert s["p_mon_ge3"] > 0.9
    assert s["p_week_ge3"] == 0.0
    assert s["p_mon_le_m5"] == 0.0


# ---------------------------------------------------------------------------
# 배치3 ⑧ confluence — N일 연속하락 AND 거래량 급증
# ---------------------------------------------------------------------------

def _ndown_vol_df(n_down=4, surge=True):
    n = 30
    close = np.full(n, 100.0)
    for k in range(n_down):
        close[-(n_down - k)] = close[-(n_down - k) - 1] * 0.99
    vol = np.full(n, 1000.0)
    if surge:
        vol[-1] = 2500.0
    return _df(close, volume=vol)


def test_ndown_volsurge_triggers():
    sig = NDownVolSurgeRule(n_down=4, vol_mult=2.0).generate_signal("TOY", _ndown_vol_df(4, True))
    assert sig is not None and sig.signal_type == SignalType.BUY


def test_ndown_volsurge_no_trigger_without_surge():
    assert NDownVolSurgeRule(n_down=4, vol_mult=2.0).generate_signal(
        "TOY", _ndown_vol_df(4, False)) is None


def test_ndown_volsurge_no_trigger_short_streak():
    assert NDownVolSurgeRule(n_down=4, vol_mult=2.0).generate_signal(
        "TOY", _ndown_vol_df(3, True)) is None


def test_ndown_volsurge_no_lookahead():
    _no_lookahead(NDownVolSurgeRule(n_down=4, vol_mult=2.0), _ndown_vol_df(4, True))

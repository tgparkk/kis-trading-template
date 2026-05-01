"""Phase 3 ComposableStrategy + ParamSet 회귀 테스트."""
from __future__ import annotations

import pytest
from dataclasses import fields

from RoboTrader_template.multiverse.composable import ParamSet


# ============================================================ #
# Helper — 유효 ParamSet 1개를 fixture로
# ============================================================ #


@pytest.fixture
def valid_paramset() -> ParamSet:
    """모든 제약을 만족하는 유효 ParamSet."""
    return ParamSet(
        # A
        w_value=0.25, w_quality=0.25, w_momentum=0.25, w_growth=0.25,
        # B
        factor_top_n=50,
        # C
        ma_short=5, ma_mid=20, ma_long=60,
        ma_regime=200, ma_regime_filter_enabled=True, ma_alignment_mode="bullish_only",
        # D (5개 True — 최소 2 만족)
        sig_trend_align=True, sig_pullback=True, sig_breakout=True,
        sig_volume=True, sig_flow=True, sig_bb_bounce=False, sig_macd=False,
        # E
        sig_trend_weight=0.20, sig_pullback_weight=0.15, sig_breakout_weight=0.20,
        sig_volume_weight=0.10, sig_flow_weight=0.10,
        sig_bb_weight=0.15, sig_macd_weight=0.10,
        # F
        tech_score_threshold=0.5, final_score_factor_w=0.4,
        # G
        entry_vol_filter_enabled=True, entry_vol_min_ratio=1.5, entry_vol_ma_period=20,
        # H
        entry_candle_filter_enabled=True, entry_candle_body_ratio=0.5,
        entry_candle_upper_wick_max=0.5,
        entry_candle_type="bullish", entry_prev_candle_check="none",
        # I
        entry_gap_filter="none", entry_close_position="upper_half",
        entry_consecutive_down=0, entry_ma_distance_max=1.10,
        # J
        entry_above_ma_mid=True, entry_ma_cross="none", entry_ma_slope_check="mid_rising",
        # K
        prev_kospi_return_filter="not_crash_2pct",
        prev_kosdaq_return_filter="not_crash_2pct",
        kospi_kosdaq_divergence="none",
        # L
        prev_sp500_filter="not_crash_1pct", prev_nasdaq_filter="not_crash_1pct",
        prev_vix_filter="below_25", overnight_futures="not_negative_1pct",
        # M
        sp500_trend="above_ma50", global_risk_mode="risk_on",
        # N
        atr_period=14, atr_multiplier=2.0,
        # O
        hard_stop_pct=-0.07, portfolio_pause_pct=-0.02, portfolio_stop_pct=-0.05,
        # P
        exit_tech_score_threshold=0.3, exit_signal_count=2, exit_rsi_overbought=75,
        # Q
        exit_below_ma_mid=True, exit_ma_dead_cross="short_cross_mid_down",
        # R
        max_positions=7, max_weight_per_stock=0.25, sizing_method="equal",
        # S (18개)
        dynamic_rr_enabled=True, initial_reward_atr_mult=2.5,
        vol_regime_adjustment="atr_pct_based", score_based_adjustment=True,
        breakeven_trigger=0.03, lock_step_1_trigger=0.07, lock_step_1_stop=0.02,
        lock_step_2_trigger=0.12, lock_step_2_stop=0.06,
        tech_score_target_adjust=True, volume_target_adjust=True,
        adx_trend_adjust=True, adx_exit_threshold=15,
        time_decay_enabled=True, time_decay_rate=0.01,
        partial_tp_enabled=True, partial_tp_trigger=0.07, partial_tp_ratio=0.5,
        # T
        rebalance_frequency="weekly",
        # U
        holding_max_days=20,
    )


# ============================================================ #
# C1: ParamSet 필드 수
# ============================================================ #


def test_paramset_has_84_fields():
    """ParamSet은 정확히 84개 필드를 가져야 함."""
    assert len(fields(ParamSet)) == 84


# ============================================================ #
# C2: 팩터 가중치 합
# ============================================================ #


def test_validate_factor_weights_sum(valid_paramset):
    """w_* 합 != 1.0이면 ValueError."""
    valid_paramset.validate()  # 정상

    from dataclasses import replace
    invalid = replace(valid_paramset, w_value=0.5)  # 합 1.25
    with pytest.raises(ValueError):
        invalid.validate()


# ============================================================ #
# C3: 시그널 최소 2개 True
# ============================================================ #


def test_validate_min_two_signals(valid_paramset):
    from dataclasses import replace
    invalid = replace(
        valid_paramset,
        sig_trend_align=False, sig_pullback=False, sig_breakout=False,
        sig_volume=False, sig_flow=False, sig_bb_bounce=True, sig_macd=False,
    )  # True 1개
    with pytest.raises(ValueError):
        invalid.validate()


# ============================================================ #
# C4: MA 순서
# ============================================================ #


def test_validate_ma_order(valid_paramset):
    from dataclasses import replace
    invalid = replace(valid_paramset, ma_short=10, ma_mid=10)  # short>=mid
    with pytest.raises(ValueError):
        invalid.validate()


# ============================================================ #
# C5: Round-trip
# ============================================================ #


def test_paramset_roundtrip(valid_paramset):
    """from_dict(to_dict(p)) == p."""
    d = valid_paramset.to_dict()
    restored = ParamSet.from_dict(d)
    assert restored == valid_paramset


# ============================================================ #
# C6: config_hash 안정성
# ============================================================ #


def test_config_hash_deterministic(valid_paramset):
    """같은 ParamSet은 항상 같은 config_hash."""
    h1 = valid_paramset.config_hash()
    h2 = valid_paramset.config_hash()
    assert h1 == h2
    assert len(h1) == 16  # hex digest 16자
    assert h1 == valid_paramset.paramset_id()

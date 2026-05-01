"""멀티버스 스모크 그리드 CLI.

사용법:
  python scripts/run_multiverse_smoke.py --persona quant --start 2025-01-01 --end 2026-01-01

옵션:
  --persona  quant|swing|long_term|intraday|all (기본 all)
  --start    YYYY-MM-DD
  --end      YYYY-MM-DD
  --n-variants  기본 5
  --output   기본 RoboTrader_template/output/smoke_<timestamp>
  --capital  기본 10_000_000
  --symbols  쉼표 구분 종목코드 (기본 005930,000660,035720,051910,005380)
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from RoboTrader_template.multiverse.composable import ParamSet
from RoboTrader_template.multiverse.runner.smoke import run_smoke, run_smoke_all_personas


def _make_default_paramset() -> ParamSet:
    """conftest valid_paramset과 동일한 유효 ParamSet 생성."""
    return ParamSet(
        # A
        w_value=0.25, w_quality=0.25, w_momentum=0.25, w_growth=0.25,
        # B
        factor_top_n=50,
        # C
        ma_short=5, ma_mid=20, ma_long=60,
        ma_regime=200, ma_regime_filter_enabled=True, ma_alignment_mode="bullish_only",
        # D
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
        # S
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


def main() -> None:
    parser = argparse.ArgumentParser(description="멀티버스 스모크 그리드 실행")
    parser.add_argument(
        "--persona", default="all",
        choices=["quant", "swing", "long_term", "intraday", "all"],
    )
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-01-01")
    parser.add_argument("--n-variants", type=int, default=5)
    parser.add_argument("--output", default=None)
    parser.add_argument("--capital", type=float, default=10_000_000.0)
    parser.add_argument("--symbols", default="005930,000660,035720,051910,005380")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    candidates = args.symbols.split(",")

    if args.output:
        out = Path(args.output)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path("RoboTrader_template/output") / f"smoke_{ts}"

    base = _make_default_paramset()

    if args.persona == "all":
        results = run_smoke_all_personas(
            base_paramset=base,
            candidate_symbols=candidates,
            start_date=start,
            end_date=end,
            output_dir=out,
            n_variants=args.n_variants,
            initial_capital=args.capital,
        )
        for persona, (result, md) in results.items():
            print(
                f"[{persona}] cells={result.n_cells_evaluated} "
                f"dsr_pass={result.n_cells_passed_dsr} md={md}"
            )
    else:
        result, md = run_smoke(
            persona=args.persona,
            base_paramset=base,
            candidate_symbols=candidates,
            start_date=start,
            end_date=end,
            output_dir=out / args.persona,
            n_variants=args.n_variants,
            initial_capital=args.capital,
        )
        print(
            f"[{args.persona}] cells={result.n_cells_evaluated} "
            f"dsr_pass={result.n_cells_passed_dsr} md={md}"
        )


if __name__ == "__main__":
    main()

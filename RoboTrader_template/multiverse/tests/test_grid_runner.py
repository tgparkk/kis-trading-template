"""Phase 5b: GridRunner + IS/OOS/WF + Markdown 리포트 회귀 테스트 (7개) +
spike_precursor 페르소나 candidate_symbols 주입 검증 (5개)."""
import pytest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import asdict

from RoboTrader_template.multiverse.runner import (
    GridRunConfig,
    run_grid,
    write_markdown_report,
    filter_passed_dsr,
    sort_by_primary_metric,
)
from RoboTrader_template.multiverse.engine.portfolio_engine import (
    PortfolioBacktestResult,
)


@pytest.fixture
def mock_portfolio_result():
    """단순한 PortfolioBacktestResult mock factory."""
    def _make(initial_capital=10000.0, days=400):
        equity_series = [
            (date(2026, 1, 1) + timedelta(days=i), initial_capital * (1 + 0.0005 * i))
            for i in range(days)
        ]
        return PortfolioBacktestResult(
            start_date=equity_series[0][0],
            end_date=equity_series[-1][0],
            initial_capital=initial_capital,
            final_equity=equity_series[-1][1],
            daily_equity=equity_series,
            trades=[],
            skipped_signals=[],
            rebalance_dates=[],
            paramset_id="mock",
            paused_until=None,
        )
    return _make


@pytest.fixture
def make_paramset():
    """다양한 valid ParamSet 생성 헬퍼."""
    from RoboTrader_template.multiverse.composable import ParamSet

    def _make(w_value=0.25):
        w_growth = round(1.0 - w_value - 0.25 - 0.25, 10)
        return ParamSet(
            w_value=w_value, w_quality=0.25, w_momentum=0.25, w_growth=w_growth,
            factor_top_n=50, ma_short=5, ma_mid=20, ma_long=60,
            ma_regime=200, ma_regime_filter_enabled=True, ma_alignment_mode="bullish_only",
            sig_trend_align=True, sig_pullback=True, sig_breakout=True,
            sig_volume=False, sig_flow=False, sig_bb_bounce=False, sig_macd=False,
            sig_trend_weight=0.20, sig_pullback_weight=0.15, sig_breakout_weight=0.20,
            sig_volume_weight=0.10, sig_flow_weight=0.10,
            sig_bb_weight=0.15, sig_macd_weight=0.10,
            tech_score_threshold=0.5, final_score_factor_w=0.4,
            entry_vol_filter_enabled=True, entry_vol_min_ratio=1.5, entry_vol_ma_period=20,
            entry_candle_filter_enabled=True, entry_candle_body_ratio=0.5,
            entry_candle_upper_wick_max=0.5,
            entry_candle_type="bullish", entry_prev_candle_check="none",
            entry_gap_filter="none", entry_close_position="upper_half",
            entry_consecutive_down=0, entry_ma_distance_max=1.10,
            entry_above_ma_mid=True, entry_ma_cross="none", entry_ma_slope_check="mid_rising",
            prev_kospi_return_filter="not_crash_2pct",
            prev_kosdaq_return_filter="not_crash_2pct",
            kospi_kosdaq_divergence="none",
            prev_sp500_filter="not_crash_1pct", prev_nasdaq_filter="not_crash_1pct",
            prev_vix_filter="below_25", overnight_futures="not_negative_1pct",
            sp500_trend="above_ma50", global_risk_mode="risk_on",
            atr_period=14, atr_multiplier=2.0,
            hard_stop_pct=-0.07, portfolio_pause_pct=-0.02, portfolio_stop_pct=-0.05,
            exit_tech_score_threshold=0.3, exit_signal_count=2, exit_rsi_overbought=75,
            exit_below_ma_mid=True, exit_ma_dead_cross="short_cross_mid_down",
            max_positions=7, max_weight_per_stock=0.25, sizing_method="equal",
            dynamic_rr_enabled=True, initial_reward_atr_mult=2.5,
            vol_regime_adjustment="atr_pct_based", score_based_adjustment=True,
            breakeven_trigger=0.03, lock_step_1_trigger=0.07, lock_step_1_stop=0.02,
            lock_step_2_trigger=0.12, lock_step_2_stop=0.06,
            tech_score_target_adjust=True, volume_target_adjust=True,
            adx_trend_adjust=True, adx_exit_threshold=15,
            time_decay_enabled=True, time_decay_rate=0.01,
            partial_tp_enabled=True, partial_tp_trigger=0.07, partial_tp_ratio=0.5,
            rebalance_frequency="weekly", holding_max_days=20,
        )
    return _make


def _strategy_factory(ps):
    """mock 전략 — MagicMock으로 ComposableStrategy 모사."""
    s = MagicMock()
    s.paramset = ps
    return s


# ---------------------------------------------------------------------------
# 테스트 1: WF IS 윈도우 하한 가드
# ---------------------------------------------------------------------------

def test_walkforward_window_guard(tmp_path, make_paramset):
    """WF IS<252d → ValueError."""
    cfg = GridRunConfig(
        mode="walkforward", start_date=date(2025, 1, 1), end_date=date(2026, 1, 1),
        initial_capital=10000.0, candidate_symbols=["TEST"], output_dir=tmp_path,
        is_window_days=100, oos_window_days=63, n_windows=6, n_jobs=1,
    )
    with pytest.raises(ValueError, match="IS"):
        run_grid(config=cfg, paramsets=[make_paramset()], strategy_factory=_strategy_factory)


# ---------------------------------------------------------------------------
# 테스트 2: WF 윈도우 개수 하한 가드
# ---------------------------------------------------------------------------

def test_walkforward_min_windows(tmp_path, make_paramset):
    """WF n_windows<6 → ValueError."""
    cfg = GridRunConfig(
        mode="walkforward", start_date=date(2025, 1, 1), end_date=date(2026, 1, 1),
        initial_capital=10000.0, candidate_symbols=["TEST"], output_dir=tmp_path,
        is_window_days=252, oos_window_days=63, n_windows=3, n_jobs=1,
    )
    with pytest.raises(ValueError, match="윈도우"):
        run_grid(config=cfg, paramsets=[make_paramset()], strategy_factory=_strategy_factory)


# ---------------------------------------------------------------------------
# 테스트 3: plain 모드 1 paramset → 1 cell
# ---------------------------------------------------------------------------

def test_plain_mode_runs(tmp_path, make_paramset, mock_portfolio_result):
    """plain 모드 — 1 paramset → 1 cell."""
    with patch(
        "RoboTrader_template.multiverse.runner.grid_runner.run_portfolio_backtest",
        return_value=mock_portfolio_result(),
    ):
        cfg = GridRunConfig(
            mode="plain", start_date=date(2025, 1, 1), end_date=date(2026, 1, 1),
            initial_capital=10000.0, candidate_symbols=["TEST"], output_dir=tmp_path, n_jobs=1,
        )
        result = run_grid(config=cfg, paramsets=[make_paramset()], strategy_factory=_strategy_factory)
        assert result.n_cells_evaluated == 1


# ---------------------------------------------------------------------------
# 테스트 4: oos_split 모드 1 paramset → 2 cells (IS + OOS)
# ---------------------------------------------------------------------------

def test_oos_split_creates_two_windows(tmp_path, make_paramset, mock_portfolio_result):
    """oos_split 모드 — 1 paramset → 2 cell (IS + OOS)."""
    with patch(
        "RoboTrader_template.multiverse.runner.grid_runner.run_portfolio_backtest",
        return_value=mock_portfolio_result(),
    ):
        cfg = GridRunConfig(
            mode="oos_split", start_date=date(2025, 1, 1), end_date=date(2026, 1, 1),
            initial_capital=10000.0, candidate_symbols=["TEST"], output_dir=tmp_path, n_jobs=1,
        )
        result = run_grid(config=cfg, paramsets=[make_paramset()], strategy_factory=_strategy_factory)
        assert result.n_cells_evaluated == 2


# ---------------------------------------------------------------------------
# 테스트 5: walkforward 모드 1 paramset, n_windows=6 → 6 cells
# ---------------------------------------------------------------------------

def test_walkforward_creates_n_windows(tmp_path, make_paramset, mock_portfolio_result):
    """walkforward 모드 — 1 paramset, n_windows=6 → 6 cells."""
    with patch(
        "RoboTrader_template.multiverse.runner.grid_runner.run_portfolio_backtest",
        return_value=mock_portfolio_result(),
    ):
        cfg = GridRunConfig(
            mode="walkforward", start_date=date(2024, 1, 1), end_date=date(2027, 1, 1),
            initial_capital=10000.0, candidate_symbols=["TEST"], output_dir=tmp_path,
            is_window_days=252, oos_window_days=63, n_windows=6, n_jobs=1,
        )
        result = run_grid(config=cfg, paramsets=[make_paramset()], strategy_factory=_strategy_factory)
        assert result.n_cells_evaluated == 6


# ---------------------------------------------------------------------------
# 테스트 6: run_grid 후 parquet_path 파일 존재
# ---------------------------------------------------------------------------

def test_parquet_file_created(tmp_path, make_paramset, mock_portfolio_result):
    """run_grid 후 parquet_path 존재."""
    with patch(
        "RoboTrader_template.multiverse.runner.grid_runner.run_portfolio_backtest",
        return_value=mock_portfolio_result(),
    ):
        cfg = GridRunConfig(
            mode="plain", start_date=date(2025, 1, 1), end_date=date(2026, 1, 1),
            initial_capital=10000.0, candidate_symbols=["TEST"], output_dir=tmp_path, n_jobs=1,
        )
        result = run_grid(config=cfg, paramsets=[make_paramset()], strategy_factory=_strategy_factory)
        assert result.parquet_path.exists()


# ---------------------------------------------------------------------------
# 테스트 7: write_markdown_report → 파일 생성 + 내용 검증
# ---------------------------------------------------------------------------

def test_markdown_report_generated(tmp_path, make_paramset, mock_portfolio_result):
    """write_markdown_report → 파일 생성 및 Multiverse Report 포함."""
    with patch(
        "RoboTrader_template.multiverse.runner.grid_runner.run_portfolio_backtest",
        return_value=mock_portfolio_result(),
    ):
        cfg = GridRunConfig(
            mode="plain", start_date=date(2025, 1, 1), end_date=date(2026, 1, 1),
            initial_capital=10000.0, candidate_symbols=["TEST"], output_dir=tmp_path, n_jobs=1,
        )
        result = run_grid(config=cfg, paramsets=[make_paramset()], strategy_factory=_strategy_factory)
        md_path = write_markdown_report(result, top_n=5)
        assert md_path.exists()
        content = md_path.read_text(encoding="utf-8")
        assert "Multiverse Report" in content


# ---------------------------------------------------------------------------
# spike_precursor 페르소나 candidate_symbols 주입 검증 (5건)
# 5/3 빌드 에러 재발 방지: build_spike_precursor_strategy(ps, candidate_symbols)
# strategy_factory 클로저가 candidate_symbols 를 올바르게 캡처해야 한다.
# ---------------------------------------------------------------------------

@pytest.fixture
def make_spike_paramset():
    """spike_precursor 용 유효한 ParamSet 생성 헬퍼."""
    from RoboTrader_template.multiverse.composable.personas._grid import (
        expand_grid_spike_precursor,
    )

    def _make():
        grid = expand_grid_spike_precursor()
        assert grid, "expand_grid_spike_precursor()가 빈 리스트를 반환"
        return grid[0]

    return _make


def test_spike_precursor_factory_builds_without_error(make_spike_paramset):
    """build_spike_precursor_strategy(ps, candidate_symbols) 빌드 에러 없음."""
    from RoboTrader_template.multiverse.composable.personas import (
        build_spike_precursor_strategy,
    )

    ps = make_spike_paramset()
    symbols = ["005930", "000660"]
    strategy = build_spike_precursor_strategy(ps, symbols)
    assert strategy is not None


def test_spike_precursor_factory_captures_candidate_symbols(make_spike_paramset):
    """strategy_factory 클로저가 candidate_symbols 을 올바르게 캡처한다."""
    from RoboTrader_template.multiverse.composable.personas import (
        build_spike_precursor_strategy,
    )

    ps = make_spike_paramset()
    symbols = ["005930", "000660", "035420"]

    # 클로저 패턴 — run_multiverse_grid.py 및 run_spike_precursor_poc.py 와 동일
    _syms = symbols

    def _factory(paramset):
        return build_spike_precursor_strategy(paramset, _syms)

    strategy = _factory(ps)
    # universe 내부의 candidates 리스트가 주입된 symbols 와 일치해야 한다
    assert strategy.universe.candidates == symbols


def test_spike_precursor_factory_missing_candidate_symbols_raises(make_spike_paramset):
    """candidate_symbols 없이 build_spike_precursor_strategy 호출 시 TypeError 발생 확인."""
    from RoboTrader_template.multiverse.composable.personas import (
        build_spike_precursor_strategy,
    )

    ps = make_spike_paramset()
    with pytest.raises(TypeError):
        build_spike_precursor_strategy(ps)  # candidate_symbols 인자 누락 → TypeError


def test_spike_precursor_grid_runner_plain_1cell(
    tmp_path, make_spike_paramset, mock_portfolio_result
):
    """spike_precursor 1개 ParamSet으로 plain 모드 grid_runner 1회 실행 — 빌드 에러 없이 완료."""
    from RoboTrader_template.multiverse.composable.personas import (
        build_spike_precursor_strategy,
    )

    ps = make_spike_paramset()
    symbols = ["005930", "000660"]
    _syms = symbols

    def _factory(paramset):
        return build_spike_precursor_strategy(paramset, _syms)

    with patch(
        "RoboTrader_template.multiverse.runner.grid_runner.run_portfolio_backtest",
        return_value=mock_portfolio_result(),
    ):
        cfg = GridRunConfig(
            mode="plain",
            start_date=date(2025, 1, 2),
            end_date=date(2025, 12, 30),
            initial_capital=100_000_000.0,
            candidate_symbols=symbols,
            output_dir=tmp_path,
            n_jobs=1,
        )
        result = run_grid(config=cfg, paramsets=[ps], strategy_factory=_factory)
        assert result.n_cells_evaluated == 1


def test_all_5_personas_factory_candidate_symbols_injection(
    tmp_path, make_paramset, make_spike_paramset, mock_portfolio_result
):
    """5 페르소나 모두 strategy_factory 클로저가 candidate_symbols 를 정상 주입한다.

    run_multiverse_grid.py 의 _run_persona() 클로저 패턴 그대로 재현.
    """
    from RoboTrader_template.multiverse.composable.personas import (
        build_quant_strategy,
        build_long_term_strategy,
        build_swing_strategy,
        build_intraday_strategy,
        build_spike_precursor_strategy,
    )

    symbols = ["005930", "000660"]
    generic_ps = make_paramset()
    spike_ps = make_spike_paramset()

    persona_cases = [
        ("quant",           build_quant_strategy,           generic_ps),
        ("long_term",       build_long_term_strategy,        generic_ps),
        ("swing",           build_swing_strategy,            generic_ps),
        ("intraday",        build_intraday_strategy,         generic_ps),
        ("spike_precursor", build_spike_precursor_strategy,  spike_ps),
    ]

    for persona_name, factory_fn, ps in persona_cases:
        _syms = symbols

        def _factory(paramset, _fn=factory_fn, _s=_syms):
            return _fn(paramset, _s)

        with patch(
            "RoboTrader_template.multiverse.runner.grid_runner.run_portfolio_backtest",
            return_value=mock_portfolio_result(),
        ):
            cfg = GridRunConfig(
                mode="plain",
                start_date=date(2025, 1, 2),
                end_date=date(2025, 3, 31),
                initial_capital=10_000_000.0,
                candidate_symbols=symbols,
                output_dir=tmp_path / persona_name,
                n_jobs=1,
            )
            result = run_grid(config=cfg, paramsets=[ps], strategy_factory=_factory)
            assert result.n_cells_evaluated == 1, (
                f"{persona_name}: n_cells_evaluated={result.n_cells_evaluated} (기대 1)"
            )

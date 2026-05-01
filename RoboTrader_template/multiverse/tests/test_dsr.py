"""multiverse.runner.dsr 회귀 테스트 (5개)."""
import pytest

from RoboTrader_template.multiverse.runner.dsr import deflated_sharpe_ratio, passes_dsr


def test_dsr_single_trial_returns_one():
    """n_trials=1이면 보정 불필요 → 1.0."""
    assert deflated_sharpe_ratio(sharpe=1.5, n_trials=1, n_observations=252) == 1.0


def test_dsr_high_sharpe_low_trials_passes():
    """Sharpe 3.0, n_trials=10, 252 obs → DSR > 0.5.

    n_trials=100이면 sr_expected≈5.36으로 Sharpe 3.0보다 높아 DSR≈0이 올바른 결과.
    n_trials=10이면 sr_expected≈2.50이므로 Sharpe 3.0 > sr_expected → DSR > 0.5.
    """
    dsr = deflated_sharpe_ratio(sharpe=3.0, n_trials=10, n_observations=252)
    assert dsr > 0.5


def test_dsr_low_sharpe_high_trials_fails():
    """Sharpe 0.5, 10000 trials → DSR 낮음 (< 0.5)."""
    dsr = deflated_sharpe_ratio(sharpe=0.5, n_trials=10000, n_observations=252)
    assert dsr < 0.5


def test_dsr_short_observations_returns_zero():
    """n_observations < 2 → 0.0."""
    assert deflated_sharpe_ratio(sharpe=1.0, n_trials=10, n_observations=1) == 0.0


def test_passes_dsr_threshold():
    """passes_dsr 임계값 경계 테스트."""
    assert passes_dsr(0.96, 0.95) is True
    assert passes_dsr(0.94, 0.95) is False

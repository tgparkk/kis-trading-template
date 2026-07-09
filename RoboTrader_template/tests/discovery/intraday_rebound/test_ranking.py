import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.ranking import (
    date_block_bootstrap_ci,
    directional_auc,
    rank_features,
    stratified_auc,
)


def test_stratified_auc_perfect_separation_is_one():
    score = np.array([1.0, 2.0, 3.0, 4.0])
    label = np.array([0, 0, 1, 1])
    strata = np.zeros(4)
    assert stratified_auc(score, label, strata) == pytest.approx(1.0)


def test_stratified_auc_ignores_strata_without_both_classes():
    score = np.array([1.0, 2.0, 3.0, 4.0, 9.0, 9.5])
    label = np.array([0, 0, 1, 1, 1, 1])       # stratum 1 has only positives
    strata = np.array([0, 0, 0, 0, 1, 1])
    assert stratified_auc(score, label, strata) == pytest.approx(1.0)


def test_stratified_auc_cancels_a_pure_volatility_proxy():
    """층 안에서는 무작위, 층 간에만 분리되는 점수는 층화 AUC가 0.5로 붕괴한다."""
    rng = np.random.default_rng(0)
    n = 2000
    strata = rng.integers(0, 2, n)
    # 점수는 층을 그대로 반영, 라벨도 층에 따라 확률이 다름
    score = strata + rng.normal(0, 0.01, n)
    label = (rng.random(n) < np.where(strata == 1, 0.4, 0.1)).astype(int)

    naive = stratified_auc(score, label, np.zeros(n))
    strat = stratified_auc(score, label, strata)
    assert naive > 0.65          # 층화하지 않으면 잘 맞히는 것처럼 보인다
    assert abs(strat - 0.5) < 0.05  # 층화하면 힘을 잃는다


def test_directional_auc_is_zero_for_symmetric_volatility_signal():
    rng = np.random.default_rng(1)
    n = 4000
    score = rng.normal(0, 1, n)
    p = 1 / (1 + np.exp(-score))         # 점수가 크면 위아래로 다 잘 간다
    hit_up = (rng.random(n) < p).astype(int)
    hit_down = (rng.random(n) < p).astype(int)
    strata = np.zeros(n)
    d = directional_auc(score, hit_up, hit_down, strata)
    assert abs(d) < 0.03


def test_directional_auc_positive_for_true_up_only_signal():
    rng = np.random.default_rng(2)
    n = 4000
    score = rng.normal(0, 1, n)
    p_up = 1 / (1 + np.exp(-score))
    hit_up = (rng.random(n) < p_up).astype(int)
    hit_down = (rng.random(n) < 0.3).astype(int)   # 점수와 무관
    d = directional_auc(score, hit_up, hit_down, np.zeros(n))
    assert d > 0.15


def test_date_block_bootstrap_ci_brackets_the_point_estimate():
    rng = np.random.default_rng(3)
    dates = np.repeat(np.arange(50), 20)

    def fn(idx):
        return float(np.mean(idx % 7 == 0))

    lo, hi = date_block_bootstrap_ci(fn, dates, n_boot=200, seed=7)
    point = fn(np.arange(len(dates)))
    assert lo <= point <= hi


def test_rank_features_shuffled_labels_collapse_to_zero():
    """셔플 테스트: 라벨을 날짜 블록 안에서 섞으면 방향성 AUC가 0으로 무너진다."""
    rng = np.random.default_rng(4)
    n = 3000
    dates = rng.integers(0, 60, n)
    df = pd.DataFrame({
        "trade_date": dates,
        "atr_quintile": rng.integers(0, 5, n),
        "is_full_lookback": rng.integers(0, 2, n).astype(bool),
        "feat_a": rng.normal(0, 1, n),
    })
    df["hit_up"] = rng.integers(0, 2, n)
    df["hit_down"] = rng.integers(0, 2, n)

    out = rank_features(df, ["feat_a"])
    assert abs(float(out.loc[0, "directional_auc"])) < 0.06
    assert out.loc[0, "ci_lo"] < 0 < out.loc[0, "ci_hi"]

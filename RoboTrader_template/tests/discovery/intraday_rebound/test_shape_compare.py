import numpy as np
import pytest

from scripts.discovery.intraday_rebound.shape_compare import (
    K,
    MAX_SHIFT,
    _dtw_distance_matrix,
    _shift,
    dtw,
    euclidean_kmeans,
    kmedoids,
    kshape_cluster,
    make_blocks,
    omnibus_test,
    sbd,
)

N = 20  # LOOKBACK_BARS


def _wave(offset=0.0, amp=1.0, phase=0.0, n=N):
    t = np.arange(n)
    return offset + amp * np.sin(2 * np.pi * (t + phase) / n) + 0.05 * t


# ---------------------------------------------------------------------------
# sbd
# ---------------------------------------------------------------------------

def test_sbd_self_distance_is_zero():
    rng = np.random.default_rng(1)
    x = rng.normal(size=N)
    assert sbd(x, x) == pytest.approx(0.0, abs=1e-9)


def test_sbd_small_shift_near_zero_large_shift_clearly_bigger():
    rng = np.random.default_rng(2)
    x = rng.normal(size=N)

    small_shift = _shift(x, 3)   # within MAX_SHIFT=5
    big_shift = _shift(x, 15)    # far beyond MAX_SHIFT=5

    d_small = sbd(x, small_shift)
    d_big = sbd(x, big_shift)

    assert d_small < 0.15
    assert d_big > d_small + 0.2


def test_sbd_invariant_to_scale_and_offset():
    # Positive-slope affine transforms only -- z-normalization removes any
    # a>0, b (a*x+b), but a negative slope flips the shape itself (peaks
    # become troughs), which is a genuinely different shape, not an
    # invariance sbd is expected to have.
    rng = np.random.default_rng(3)
    x = rng.normal(size=N)
    y = rng.normal(size=N)

    base = sbd(x, y)
    scaled_offset = sbd(3.0 * x + 7.0, 2.0 * y - 4.0)

    assert scaled_offset == pytest.approx(base, abs=1e-9)


# ---------------------------------------------------------------------------
# dtw
# ---------------------------------------------------------------------------

def test_dtw_self_distance_is_zero():
    rng = np.random.default_rng(4)
    x = rng.normal(size=N)
    assert dtw(x, x) == pytest.approx(0.0, abs=1e-9)


def test_dtw_time_stretch_much_smaller_than_reversed():
    x = _wave()
    # Time-stretch: repeat every other value to slow it down, then resample
    # back to length N (a genuine speed change of the same shape).
    stretched_long = np.repeat(x, 2)[:2 * N - 1]
    idx = np.linspace(0, len(stretched_long) - 1, N).round().astype(int)
    stretched = stretched_long[idx]

    reversed_x = x[::-1].copy()

    d_stretch = dtw(x, stretched)
    d_reversed = dtw(x, reversed_x)

    assert d_stretch < d_reversed * 0.5


def test_banded_dtw_matches_naive_reference_on_random_pairs():
    def dtw_naive(x, y, radius):
        n, m = len(x), len(y)
        D = np.full((n + 1, m + 1), np.inf)
        D[0, 0] = 0.0
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                if abs((i - 1) - (j - 1)) > radius:
                    continue
                cost = (x[i - 1] - y[j - 1]) ** 2
                D[i, j] = cost + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
        return D[n, m]

    rng = np.random.default_rng(5)
    radius = 3
    for _ in range(8):
        x = rng.normal(size=N)
        y = rng.normal(size=N)
        expected = dtw_naive(x, y, radius)
        actual = dtw(x, y, radius=radius)
        assert actual == pytest.approx(expected, rel=1e-9, abs=1e-9)


def test_dtw_distance_matrix_matches_pairwise_dtw_and_is_symmetric():
    rng = np.random.default_rng(6)
    X = rng.normal(size=(6, N))
    D = _dtw_distance_matrix(X, radius=3, chunk_size=4)

    np.testing.assert_allclose(D, D.T)
    np.testing.assert_allclose(np.diag(D), 0.0, atol=1e-9)
    for i in range(6):
        for j in range(6):
            assert D[i, j] == pytest.approx(dtw(X[i], X[j], radius=3), abs=1e-9)


# ---------------------------------------------------------------------------
# k-medoids determinism
# ---------------------------------------------------------------------------

def test_kmedoids_deterministic_for_fixed_seed():
    rng = np.random.default_rng(7)
    m = 40
    pts = rng.normal(size=(m, 3))
    # symmetric euclidean distance matrix (any symmetric matrix works for k-medoids).
    D = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2)

    labels1, medoids1 = kmedoids(D, k=4, seed=99)
    labels2, medoids2 = kmedoids(D, k=4, seed=99)

    np.testing.assert_array_equal(labels1, labels2)
    np.testing.assert_array_equal(medoids1, medoids2)


def test_kmedoids_recovers_well_separated_clusters():
    rng = np.random.default_rng(8)
    centers = np.array([[0, 0], [50, 0], [0, 50], [50, 50]], dtype=float)
    pts = np.concatenate([c + rng.normal(scale=0.5, size=(20, 2)) for c in centers])
    D = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2)

    labels, _ = kmedoids(D, k=4, seed=1)
    # each of the 4 known blocks of 20 points should end up as a single label.
    for block in range(4):
        block_labels = labels[block * 20:(block + 1) * 20]
        assert len(set(block_labels)) == 1


# ---------------------------------------------------------------------------
# k-shape / euclidean smoke
# ---------------------------------------------------------------------------

def test_euclidean_kmeans_matches_direct_sklearn_call():
    from sklearn.cluster import KMeans
    rng = np.random.default_rng(9)
    Z = rng.normal(size=(60, N))
    expected = KMeans(n_clusters=8, n_init=10, random_state=42).fit_predict(Z)
    actual = euclidean_kmeans(Z, k=8, seed=42)
    np.testing.assert_array_equal(actual, expected)


def test_kshape_cluster_returns_labels_covering_all_events_within_k_range():
    rng = np.random.default_rng(10)
    Z = rng.normal(size=(80, N))
    labels = kshape_cluster(Z, k=K, max_shift=MAX_SHIFT, seed=42, max_iter=5)

    assert labels.shape == (80,)
    assert labels.min() >= 0
    assert labels.max() < K
    assert len(labels) == 80


# ---------------------------------------------------------------------------
# omnibus scorer
# ---------------------------------------------------------------------------

def _fake_events(n=600, seed=11, n_dates=20):
    rng = np.random.default_rng(seed)
    trade_date = rng.integers(0, n_dates, size=n).astype(str)
    pre_vol = rng.uniform(0.3, 3.0, size=n)
    return trade_date, pre_vol, rng


def test_omnibus_perfectly_associated_labels_give_large_T():
    trade_date, pre_vol, rng = _fake_events(n=800, seed=11)
    k = 8
    # cluster "type" drives a skewed up/down probability -> real association
    # between cluster label and outcome, without any degenerate (all-up or
    # all-down) cluster.
    true_type = rng.integers(0, k, size=len(trade_date))
    p_up_by_type = np.linspace(0.15, 0.85, k)
    outcomes = np.array([
        "up" if rng.random() < p_up_by_type[t] else "down" for t in true_type
    ])

    result, _, _ = omnibus_test(true_type, outcomes, pre_vol, k=k, B=400, seed=13)
    assert result["T_obs"] > result["null_p95"]
    assert result["p"] < 0.05


def test_omnibus_random_labels_give_T_near_null_median():
    trade_date, pre_vol, rng = _fake_events(n=800, seed=12)
    k = 8
    outcomes = rng.choice(["up", "down"], size=len(trade_date), p=[0.4, 0.6])
    random_labels = rng.integers(0, k, size=len(trade_date))

    result, _, _ = omnibus_test(random_labels, outcomes, pre_vol, k=k, B=400, seed=13)

    lo = 0.2 * result["null_median"]
    hi = result["null_p95"] * 1.5
    assert lo <= result["T_obs"] <= hi


def test_omnibus_reuses_precomputed_perm_masks_for_identical_result():
    trade_date, pre_vol, rng = _fake_events(n=300, seed=14)
    k = 4
    labels = rng.integers(0, k, size=len(trade_date))
    outcomes = rng.choice(["up", "down", "none"], size=len(trade_date), p=[0.3, 0.3, 0.4])
    blocks = make_blocks(trade_date, pre_vol)

    result_a, perm_up, perm_down = omnibus_test(labels, outcomes, pre_vol, k=k,
                                                 blocks=blocks, B=200, seed=5)
    result_b, _, _ = omnibus_test(labels, outcomes, pre_vol, k=k,
                                  perm_up=perm_up, perm_down=perm_down)

    assert result_a["T_obs"] == result_b["T_obs"]
    assert result_a["p"] == result_b["p"]


def test_make_blocks_permutation_preserves_within_block_up_down_counts():
    from scripts.discovery.intraday_rebound.shape_compare import _permutation_null_masks

    trade_date, pre_vol, rng = _fake_events(n=300, seed=15)
    outcomes = rng.choice(["up", "down", "none"], size=len(trade_date), p=[0.3, 0.3, 0.4])
    blocks = make_blocks(trade_date, pre_vol)

    perm_up, perm_down = _permutation_null_masks(outcomes, blocks, B=50, seed=1)

    for block_id in np.unique(blocks):
        pos = np.where(blocks == block_id)[0]
        orig_up = int((outcomes[pos] == "up").sum())
        orig_down = int((outcomes[pos] == "down").sum())
        for b in range(50):
            assert int(perm_up[b, pos].sum()) == orig_up
            assert int(perm_down[b, pos].sum()) == orig_down

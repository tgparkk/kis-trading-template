# scripts/discovery/intraday_rebound/shape_compare.py
"""20봉 궤적 모양 클러스터링 3종 비교: 유클리드(베이스라인) vs phase-invariant
(k-Shape) vs speed-invariant(DTW k-medoids).

유클리드 KMeans 는 봉 대 봉으로 뻣뻣하게 비교한다 — 같은 모양이 다른 위상
(bar 12 대 bar 15 의 반등 고점)이거나 다른 속도(8봉 슬라이드 대 20봉
슬라이드)면 못 맞춘다. 이 모듈은 그 invariance 를 허용했을 때 (shape_events.py
가 만든) 20봉 궤적-outcome 연관 신호가 강해지는지 약해지는지만 측정한다.

세 방법 모두 입력은 동일한 행별 z-정규화 행렬 ``Z`` (shape_events.zscore_rows
재사용, flat 행 -> 0) 이고, 스코어링(옴니버스 순열검정)도 세 방법에 동일하게
적용한다 — 클러스터링 방식만 바뀐다.

방법:
  A. 유클리드 KMeans(k=8) — 기존 shape_events.py 와 동일 파라미터로 재현.
  B. k-Shape (phase-invariant) — 처음부터 구현. SBD(shape-based distance) =
     1 - max NCC, lag 를 |lag|<=MAX_SHIFT=5 로 제한한다(마지막 봉이 급락
     직전 anchor 이므로 무제한 shift 는 그 정보를 버린다).
  C. DTW k-medoids (speed-invariant) — Sakoe-Chiba band(r=3) 제곱유클리드
     DTW. 4323^2 전체는 느려서 1200 표본으로 거리행렬을 만들고 k-medoids 로
     8개 medoid 를 찾은 뒤, 4323건 전부를 그 medoid 에 DTW 로 재배정한다
     (세 방법의 스코어링 표본을 동일하게 유지하기 위해).

스코어링(옴니버스 순열검정): 클러스터별 log_ratio_k = log(n_up/n_down)
(up 또는 down 이 0인 클러스터는 제외). 귀무분포는 outcome 라벨을
(trade_date, pre_vol quintile) 블록 내에서만 섞어서(B=3000) 만든다 — 블록
구조는 클러스터링과 무관하므로 세 방법이 정확히 같은 B=3000 개 순열 초안
(permuted outcome mask)을 공유한다. 클러스터마다 귀무 평균/표준편차가
다르므로(클러스터 크기·pre_vol 이 다름) 먼저 그 귀무분포로 표준화한 뒤
T = sum(z_k^2) 로 합산한다(옴니버스). p = mean(T_null >= T_obs).

이것은 백테스트가 아니고 해석도 하지 않는다 — 세 방법의 T_obs/p/best-edge 숫자만 낸다.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from .shape_events import CACHE_DIR, EVENTS_PARQUET, W_COLS, zscore_rows

K = 8
SEED = 42

MAX_SHIFT = 5          # k-Shape: 최대 lag(봉 단위). 마지막 봉은 anchor.
KSHAPE_MAX_ITER = 30

DTW_RADIUS = 3          # Sakoe-Chiba band 반경(봉 단위)
DTW_SUBSAMPLE_N = 1200
DTW_SUBSAMPLE_SEED = 42
DTW_CHUNK_SIZE = 300
DTW_MAX_ITER = 50

B_PERM = 3000
PERM_SEED = 13

COMPARE_JSON = CACHE_DIR / "shape_compare.json"
LABELS_PARQUET = CACHE_DIR / "shape_compare_labels.parquet"


def _zscore1d(v: np.ndarray) -> np.ndarray:
    """1개 벡터 z-정규화. zscore_rows(matrix) 와 동일 규칙(flat -> 0)을 재사용한다."""
    v = np.asarray(v, dtype=float)
    return zscore_rows(v.reshape(1, -1))[0]


# ---------------------------------------------------------------------------
# Method A: 유클리드 KMeans (베이스라인, 그대로 재현)
# ---------------------------------------------------------------------------

def euclidean_kmeans(Z: np.ndarray, k: int = K, seed: int = SEED) -> np.ndarray:
    return KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(Z)


# ---------------------------------------------------------------------------
# Method B: k-Shape (phase-invariant), 처음부터 구현
# ---------------------------------------------------------------------------

def _cross_corr_batch(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """``X`` (m,n) 의 각 행과 단일 기준 ``y`` (n,) 의 교차상관, 2n 으로
    zero-pad 한 FFT 로 계산한다. 반환 (m, 2n-1); 열 i -> lag = i-(n-1).
    ``cc[k, i]`` 가 최대인 lag=L 은 ``X[k] ~= shift(y, L)`` (X[k] 가 y 를 L 만큼
    지연시킨 것)을 뜻한다 — 부호는 스크래치 검증으로 고정했다(아래 _shift_rows
    와 짝을 이뤄야 함: 정렬하려면 member 를 ``shift(member, -L)``).
    """
    m, n = X.shape
    fft_size = 2 * n
    fX = np.fft.fft(X, fft_size, axis=1)
    fy = np.fft.fft(y, fft_size)
    cc = np.fft.ifft(fX * np.conj(fy)[None, :], axis=1).real
    return np.concatenate([cc[:, -(n - 1):], cc[:, :n]], axis=1)


def _sbd_batch(X: np.ndarray, y: np.ndarray,
               max_shift: int) -> tuple[np.ndarray, np.ndarray]:
    """``X`` 의 각 행 대 단일 기준 ``y`` 의 SBD 거리 + 최적 lag(|lag|<=max_shift)."""
    m, n = X.shape
    Xz = zscore_rows(X)
    yz = _zscore1d(y)
    cc = _cross_corr_batch(Xz, yz)

    denom = np.linalg.norm(Xz, axis=1) * np.linalg.norm(yz)
    denom = np.where(denom == 0, 1.0, denom)
    ncc = cc / denom[:, None]

    lags = np.arange(-(n - 1), n)
    mask = np.abs(lags) <= max_shift
    ncc_b = ncc[:, mask]
    lags_b = lags[mask]

    best_idx = np.argmax(ncc_b, axis=1)
    best_ncc = ncc_b[np.arange(m), best_idx]
    best_lag = lags_b[best_idx]
    return 1.0 - best_ncc, best_lag


def sbd_with_lag(x: np.ndarray, y: np.ndarray, max_shift: int = MAX_SHIFT) -> tuple[float, int]:
    """단일 쌍 SBD + 최적 lag. x 를 ``shift(x, -lag)`` 하면 y 에 가장 잘 맞는다."""
    x = np.asarray(x, dtype=float)
    d, lag = _sbd_batch(x.reshape(1, -1), np.asarray(y, dtype=float), max_shift)
    return float(d[0]), int(lag[0])


def sbd(x: np.ndarray, y: np.ndarray, max_shift: int = MAX_SHIFT) -> float:
    return sbd_with_lag(x, y, max_shift)[0]


def _shift_rows(X: np.ndarray, lags: np.ndarray) -> np.ndarray:
    """행마다 다른 lag 로 zero-fill shift. lag>0 은 오른쪽(지연), lag<0 은 왼쪽."""
    m, n = X.shape
    out = np.zeros_like(X, dtype=float)
    for lag in np.unique(lags):
        rows = lags == lag
        lag = int(lag)
        if lag == 0:
            out[rows] = X[rows]
        elif lag > 0:
            out[rows, lag:] = X[rows, :n - lag]
        else:
            out[rows, :n + lag] = X[rows, -lag:]
    return out


def _shift(x: np.ndarray, lag: int) -> np.ndarray:
    return _shift_rows(np.asarray(x, dtype=float).reshape(1, -1), np.array([lag]))[0]


def _extract_centroid(members: np.ndarray, prev_centroid: np.ndarray | None,
                      max_shift: int) -> np.ndarray:
    """k-Shape shape extraction: member 들을 prev_centroid 에 최적 lag 로
    정렬(zero-fill shift) -> 재정규화 -> S=Q^T A^T A Q 의 최대고유벡터 ->
    z-정규화. prev_centroid 가 없으면(첫 반복) 정렬을 건너뛴다. 부호는
    prev_centroid 와의 거리가 작은 쪽으로 고른다(없으면 멤버 평균과 내적이
    양수인 쪽 — 결정론적 기본값).
    """
    n = members.shape[1]
    if prev_centroid is None:
        aligned = members
    else:
        _, lags = _sbd_batch(members, prev_centroid, max_shift)
        aligned = _shift_rows(members, -lags)

    aligned = zscore_rows(aligned)
    Q = np.eye(n) - np.ones((n, n)) / n
    gram = aligned.T @ aligned
    S = Q.T @ gram @ Q
    _, eigvecs = np.linalg.eigh(S)
    p = eigvecs[:, -1]

    if prev_centroid is None:
        ref = aligned.mean(axis=0)
        if np.dot(p, ref) < 0:
            p = -p
    else:
        d_pos = float(np.sum((p - prev_centroid) ** 2))
        d_neg = float(np.sum((-p - prev_centroid) ** 2))
        if d_neg < d_pos:
            p = -p

    return _zscore1d(p)


def kshape_cluster(Z: np.ndarray, k: int = K, max_shift: int = MAX_SHIFT,
                   seed: int = SEED, max_iter: int = KSHAPE_MAX_ITER,
                   verbose: bool = False) -> np.ndarray:
    m, n = Z.shape
    rng = np.random.default_rng(seed)
    labels = rng.integers(0, k, size=m)
    centroids: list[np.ndarray | None] = [None] * k

    for iteration in range(max_iter):
        new_centroids = []
        for c in range(k):
            members = Z[labels == c]
            if members.shape[0] == 0:
                new_centroids.append(centroids[c] if centroids[c] is not None
                                     else np.zeros(n))
                continue
            new_centroids.append(_extract_centroid(members, centroids[c], max_shift))
        centroids = new_centroids

        dists = np.stack(
            [_sbd_batch(Z, centroids[c], max_shift)[0] for c in range(k)], axis=1)
        new_labels = np.argmin(dists, axis=1)

        changed = int(np.sum(new_labels != labels))
        if verbose:
            print(f"kshape iter {iteration + 1}/{max_iter} changed={changed}")
        stop = changed == 0
        labels = new_labels
        if stop:
            break

    return labels


# ---------------------------------------------------------------------------
# Method C: DTW k-medoids (speed-invariant), 처음부터 구현
# ---------------------------------------------------------------------------

def _dtw_batch(x: np.ndarray, Y: np.ndarray, radius: int) -> np.ndarray:
    """단일 ``x`` (n,) 대 ``Y`` (batch,n) 의 각 행의 밴디드 DTW 거리(제곱유클리드
    로컬비용, Sakoe-Chiba 반경 ``radius``). DP 를 행(i=0..n-1) 단위로 채우되
    batch 축 전체는 벡터화한다(양쪽 축 모두 파이썬 루프 없음).
    """
    x = np.asarray(x, dtype=float)
    Y = np.asarray(Y, dtype=float)
    n = len(x)
    batch = Y.shape[0]

    D = np.full((batch, n + 1, n + 1), np.inf)
    D[:, 0, 0] = 0.0
    for i in range(1, n + 1):
        lo = max(1, i - radius)
        hi = min(n, i + radius)
        xi = x[i - 1]
        cost_row = (Y[:, lo - 1:hi] - xi) ** 2
        for offset, j in enumerate(range(lo, hi + 1)):
            c = cost_row[:, offset]
            best_prev = np.minimum(np.minimum(D[:, i - 1, j], D[:, i, j - 1]),
                                   D[:, i - 1, j - 1])
            D[:, i, j] = c + best_prev

    return D[:, n, n]


def dtw(x: np.ndarray, y: np.ndarray, radius: int = DTW_RADIUS) -> float:
    return float(_dtw_batch(x, np.asarray(y, dtype=float).reshape(1, -1), radius)[0])


def _dtw_distance_matrix(X: np.ndarray, radius: int, chunk_size: int = DTW_CHUNK_SIZE,
                         verbose: bool = False) -> np.ndarray:
    """대칭 (m,m) 밴디드 DTW 거리행렬. 기준 series 하나씩(m 회) 돌되, 나머지와의
    거리는 ``chunk_size`` 단위로 배치 벡터화한다(_dtw_batch) — 양쪽 축 모두
    파이썬 페어 루프는 없다. i<=j 대칭성으로 계산량을 절반으로 줄인다.
    """
    m = X.shape[0]
    D = np.zeros((m, m))
    for i in range(m):
        x = X[i]
        for start in range(i, m, chunk_size):
            end = min(start + chunk_size, m)
            d = _dtw_batch(x, X[start:end], radius)
            D[i, start:end] = d
            D[start:end, i] = d
        if verbose and (i + 1) % 100 == 0:
            print(f"dtw matrix row {i + 1}/{m}")
    return D


def _kmedoids_pp_init(D: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    m = D.shape[0]
    medoids = [int(rng.integers(0, m))]
    for _ in range(1, k):
        dist_to_nearest = np.min(D[:, medoids], axis=1)
        d2 = dist_to_nearest ** 2
        total = float(d2.sum())
        if total <= 0:
            remaining = [i for i in range(m) if i not in medoids]
            nxt = int(rng.choice(remaining))
        else:
            probs = d2 / total
            nxt = int(rng.choice(m, p=probs))
        medoids.append(nxt)
    return np.array(medoids, dtype=int)


def kmedoids(D: np.ndarray, k: int = K, seed: int = SEED,
            max_iter: int = DTW_MAX_ITER) -> tuple[np.ndarray, np.ndarray]:
    """사전계산된 거리행렬 ``D`` (m,m) 위에서 k-medoids++ 초기화 + 교대최적화.
    ``D`` 와 ``seed`` 만으로 결정론적(다른 난수원 없음).
    """
    rng = np.random.default_rng(seed)
    medoids = _kmedoids_pp_init(D, k, rng)
    labels = np.argmin(D[:, medoids], axis=1)

    for _ in range(max_iter):
        new_medoids = medoids.copy()
        for c in range(k):
            members = np.where(labels == c)[0]
            if len(members) == 0:
                continue
            sub = D[np.ix_(members, members)]
            costs = sub.sum(axis=1)
            new_medoids[c] = members[int(np.argmin(costs))]

        new_labels = np.argmin(D[:, new_medoids], axis=1)
        stable = np.array_equal(new_labels, labels) and np.array_equal(new_medoids, medoids)
        medoids = new_medoids
        labels = new_labels
        if stable:
            break

    return labels, medoids


def dtw_cluster(Z: np.ndarray, k: int = K, seed: int = SEED,
                sub_n: int = DTW_SUBSAMPLE_N, sub_seed: int = DTW_SUBSAMPLE_SEED,
                radius: int = DTW_RADIUS, chunk_size: int = DTW_CHUNK_SIZE,
                max_iter: int = DTW_MAX_ITER, verbose: bool = False) -> np.ndarray:
    n_total = Z.shape[0]
    rng_sub = np.random.default_rng(sub_seed)
    sub_idx = rng_sub.choice(n_total, size=sub_n, replace=False)
    X_sub = Z[sub_idx]

    if verbose:
        print(f"dtw: building {sub_n}x{sub_n} distance matrix (radius={radius})...")
    D = _dtw_distance_matrix(X_sub, radius, chunk_size=chunk_size, verbose=verbose)

    if verbose:
        print("dtw: running k-medoids...")
    labels_sub, medoid_local_idx = kmedoids(D, k=k, seed=seed, max_iter=max_iter)
    medoid_series = X_sub[medoid_local_idx]

    if verbose:
        print(f"dtw: assigning all {n_total} events to nearest medoid...")
    dists = np.stack([_dtw_batch(medoid_series[c], Z, radius) for c in range(k)], axis=1)
    return np.argmin(dists, axis=1)


# ---------------------------------------------------------------------------
# 스코어링: 옴니버스 블록-순열 검정 (세 방법 공통)
# ---------------------------------------------------------------------------

def make_blocks(trade_date: np.ndarray, pre_vol: np.ndarray) -> np.ndarray:
    """(trade_date, pre_vol quintile) 블록 id 정수 배열. quintile 은
    pd.qcut(pre_vol, 5, labels=False, duplicates='drop') 로 낸다.
    """
    quintile = pd.qcut(pd.Series(pre_vol), 5, labels=False, duplicates="drop")
    key = pd.Series(trade_date).astype(str) + "_" + quintile.astype(str)
    return key.factorize(sort=True)[0]


def _permutation_null_masks(outcomes: np.ndarray, blocks: np.ndarray, B: int,
                            seed: int) -> tuple[np.ndarray, np.ndarray]:
    """블록 내부에서만 outcome 을 섞은 B 개 순열의 is_up/is_down 마스크
    (B,n) 을 벡터화로 만든다(블록마다 (B, block_size) 난수키 argsort — B 위
    파이썬 루프 없음, 블록 개수만큼만 파이썬 루프).
    """
    outcomes = np.asarray(outcomes)
    is_up = outcomes == "up"
    is_down = outcomes == "down"
    n = len(outcomes)

    rng = np.random.default_rng(seed)
    perm_up = np.empty((B, n), dtype=bool)
    perm_down = np.empty((B, n), dtype=bool)

    for block_id in np.unique(blocks):
        pos = np.where(blocks == block_id)[0]
        msize = len(pos)
        if msize <= 1:
            perm_up[:, pos] = is_up[pos]
            perm_down[:, pos] = is_down[pos]
            continue
        keys = rng.random((B, msize))
        order = np.argsort(keys, axis=1)
        perm_up[:, pos] = is_up[pos][order]
        perm_down[:, pos] = is_down[pos][order]

    return perm_up, perm_down


def _log_ratio(n_up: np.ndarray, n_down: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """log(n_up/n_down); n_up 또는 n_down 이 0 인 곳은 valid=False, ratio=NaN."""
    valid = (n_up > 0) & (n_down > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.log(n_up / n_down)
    return np.where(valid, ratio, np.nan), valid


def omnibus_test(labels: np.ndarray, outcomes: np.ndarray, pre_vol: np.ndarray,
                 k: int = K, perm_up: np.ndarray | None = None,
                 perm_down: np.ndarray | None = None,
                 blocks: np.ndarray | None = None, trade_date: np.ndarray | None = None,
                 B: int = B_PERM, seed: int = PERM_SEED) -> dict:
    """클러스터별 log_ratio_k=log(up/down) (0 건 클러스터 제외) 를, 블록-내부
    순열(B 회, perm_up/perm_down 재사용 가능)로 낸 귀무 평균/표준편차로
    표준화 -> 옴니버스 T=sum(z_k^2), p=mean(T_null>=T_obs).
    """
    labels = np.asarray(labels)
    n = len(labels)
    onehot = np.zeros((n, k), dtype=float)
    onehot[np.arange(n), labels] = 1.0

    is_up = (np.asarray(outcomes) == "up").astype(float)
    is_down = (np.asarray(outcomes) == "down").astype(float)
    n_up_obs = is_up @ onehot
    n_down_obs = is_down @ onehot
    log_ratio_obs, valid_obs = _log_ratio(n_up_obs, n_down_obs)

    if perm_up is None or perm_down is None:
        if blocks is None:
            blocks = make_blocks(trade_date, pre_vol)
        perm_up, perm_down = _permutation_null_masks(outcomes, blocks, B, seed)

    n_up_perm = perm_up.astype(float) @ onehot   # (B,k)
    n_down_perm = perm_down.astype(float) @ onehot
    log_ratio_perm, _ = _log_ratio(n_up_perm, n_down_perm)

    null_mean = np.nanmean(log_ratio_perm, axis=0)
    null_sd = np.nanstd(log_ratio_perm, axis=0)

    usable = valid_obs & (null_sd > 0) & ~np.isnan(null_mean)
    idx = np.where(usable)[0]

    z_obs_full = np.full(k, np.nan)
    z_obs_full[idx] = (log_ratio_obs[idx] - null_mean[idx]) / null_sd[idx]
    T_obs = float(np.nansum(z_obs_full[idx] ** 2)) if idx.size else 0.0

    z_perm = np.zeros((B, idx.size))
    if idx.size:
        z_perm = (log_ratio_perm[:, idx] - null_mean[idx]) / null_sd[idx]
        z_perm = np.nan_to_num(z_perm, nan=0.0)
    T_null = np.sum(z_perm ** 2, axis=1) if idx.size else np.zeros(B)

    p = float(np.mean(T_null >= T_obs))

    clusters = []
    for c in range(k):
        n_c = int(onehot[:, c].sum())
        pct_up = round(100.0 * n_up_obs[c] / n_c, 3) if n_c else None
        pct_dn = round(100.0 * n_down_obs[c] / n_c, 3) if n_c else None
        edge_pp = round(pct_up - pct_dn, 3) if n_c else None
        z_val = float(z_obs_full[c]) if not np.isnan(z_obs_full[c]) else None
        mask_c = labels == c
        mean_pre_vol = round(float(np.mean(pre_vol[mask_c])), 4) if n_c else None
        clusters.append({
            "cluster": c, "n": n_c, "pct_up": pct_up, "pct_dn": pct_dn,
            "edge_pp": edge_pp, "z": round(z_val, 4) if z_val is not None else None,
            "pre_vol": mean_pre_vol,
        })

    return {
        "T_obs": round(T_obs, 4),
        "null_median": round(float(np.median(T_null)), 4),
        "null_p95": round(float(np.percentile(T_null, 95)), 4),
        "p": round(p, 6),
        "n_clusters_used": int(idx.size),
        "clusters": clusters,
    }, perm_up, perm_down


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("loading events...")
    events = pd.read_parquet(EVENTS_PARQUET)
    n_total = len(events)
    print(f"n_total={n_total}")

    W = events[W_COLS].to_numpy(dtype=float)
    Z = zscore_rows(W)
    outcomes = events["outcome"].to_numpy()
    pre_vol = events["pre_vol"].to_numpy(dtype=float)
    trade_date = events["trade_date"].to_numpy()

    blocks = make_blocks(trade_date, pre_vol)
    print(f"n_blocks={len(np.unique(blocks))}")

    print(f"building shared permutation null (B={B_PERM}, seed={PERM_SEED})...")
    perm_up, perm_down = _permutation_null_masks(outcomes, blocks, B_PERM, PERM_SEED)

    results: dict = {}
    labels_out: dict[str, np.ndarray] = {}

    print("method A: euclidean kmeans...")
    t0 = time.time()
    labels_a = euclidean_kmeans(Z, k=K, seed=SEED)
    res_a, _, _ = omnibus_test(labels_a, outcomes, pre_vol, k=K,
                               perm_up=perm_up, perm_down=perm_down)
    print(f"  done in {time.time() - t0:.1f}s  T_obs={res_a['T_obs']} p={res_a['p']}")
    results["euclid"] = res_a
    labels_out["euclid"] = labels_a

    print("method B: k-shape (phase-invariant)...")
    t0 = time.time()
    labels_b = kshape_cluster(Z, k=K, max_shift=MAX_SHIFT, seed=SEED,
                              max_iter=KSHAPE_MAX_ITER, verbose=True)
    res_b, _, _ = omnibus_test(labels_b, outcomes, pre_vol, k=K,
                               perm_up=perm_up, perm_down=perm_down)
    print(f"  done in {time.time() - t0:.1f}s  T_obs={res_b['T_obs']} p={res_b['p']}")
    results["kshape"] = res_b
    labels_out["kshape"] = labels_b

    print("method C: dtw k-medoids (speed-invariant)...")
    t0 = time.time()
    labels_c = dtw_cluster(Z, k=K, seed=SEED, sub_n=DTW_SUBSAMPLE_N,
                           sub_seed=DTW_SUBSAMPLE_SEED, radius=DTW_RADIUS,
                           chunk_size=DTW_CHUNK_SIZE, max_iter=DTW_MAX_ITER,
                           verbose=True)
    res_c, _, _ = omnibus_test(labels_c, outcomes, pre_vol, k=K,
                               perm_up=perm_up, perm_down=perm_down)
    print(f"  done in {time.time() - t0:.1f}s  T_obs={res_c['T_obs']} p={res_c['p']}")
    results["dtw"] = res_c
    labels_out["dtw"] = labels_c

    out = {
        "n_total": n_total,
        "k": K,
        "params": {
            "max_shift": MAX_SHIFT, "dtw_radius": DTW_RADIUS,
            "dtw_subsample_n": DTW_SUBSAMPLE_N, "dtw_subsample_seed": DTW_SUBSAMPLE_SEED,
            "B_perm": B_PERM, "perm_seed": PERM_SEED, "seed": SEED,
        },
        "methods": results,
    }
    with open(COMPARE_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=True, indent=2)
    print(f"wrote {COMPARE_JSON}")

    labels_df = pd.DataFrame({
        "euclid": labels_out["euclid"],
        "kshape": labels_out["kshape"],
        "dtw": labels_out["dtw"],
    })
    labels_df.to_parquet(LABELS_PARQUET, index=False)
    print(f"wrote {LABELS_PARQUET}")


if __name__ == "__main__":
    main()

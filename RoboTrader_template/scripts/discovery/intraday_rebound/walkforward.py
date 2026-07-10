# scripts/discovery/intraday_rebound/walkforward.py
"""워크포워드 평가: 규칙 탐색을 학습 폴드 안에 가둔다.

사전등록: ``.superpowers/sdd/walkforward-preregistration.md`` (커밋 c4851f2,
결과를 보기 전에 커밋됨). 이 파일은 그 계약의 구현이다. 사전등록과 이 코드가
어긋나면 사전등록이 아니라 이 코드가 틀린 것이다.

3단계:
  1) extract  -- DB에서 이벤트를 한 번 추출해 ``_cache/wf_events.parquet`` 에 저장.
  2) 순수함수 -- outcome_from_path / expectancy / make_folds (DB 무관, 결정적).
  3) 탐색/평가 -- search_config 는 학습 폴드 안에서만 그리드를 탐색한다.
                 evaluate_config 는 그 결과(확정된 절대값)를 평가 폴드에
                 그대로 적용할 뿐, 절대 분위수를 재계산하거나 KMeans 를
                 재적합하지 않는다 -- 이것이 이 모듈 전체의 존재 이유다.

이것은 백테스트가 아니다. 확장창(expanding window) 워크포워드로, 각 평가
폴드는 그 시점까지의 학습 폴드에서 선택된 설정 단 하나로만 채점된다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from .db import MINUTE_DB, read_sql
from .resample import resample_ohlcv
from .shape_events import zscore_rows
from .universe import load_frozen_universe

# ---------------------------------------------------------------------------
# 추출 파라미터 (사전등록 고정값)
# ---------------------------------------------------------------------------
TFS = (3, 5)
PRE_BARS = 20
FWD_BARS = 20
DROP_PCT_EXTRACT = 0.04
LOOKBACK_MIN = 60
MIN_LOOKBACK_MIN = 15
START_DATE = "20250401"
END_DATE = "20260630"

REGULAR_OPEN = pd.Timestamp("09:00:00").time()
REGULAR_CLOSE = pd.Timestamp("15:30:00").time()

CACHE_DIR = Path(__file__).parent / "_cache"
EVENTS_PARQUET = CACHE_DIR / "wf_events.parquet"

P_COLS = [f"p{i}" for i in range(PRE_BARS)]
FH_COLS = [f"fh{i}" for i in range(FWD_BARS)]
FL_COLS = [f"fl{i}" for i in range(FWD_BARS)]
FC_COLS = [f"fc{i}" for i in range(FWD_BARS)]

EVENT_COLUMNS = [
    "tf", "stock_code", "trade_date", "entry_time", "entry_close", "drop_pct",
    "close_pos_in_day", "lower_wick_ratio", "pre_vol",
    *P_COLS, *FH_COLS, *FL_COLS, *FC_COLS,
]

_DAYS_SQL = """
SELECT DISTINCT trade_date FROM minute_candles
WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date
"""

_BARS_SQL = """
SELECT stock_code, datetime, open, high, low, close, volume, amount
FROM minute_candles
WHERE trade_date = %s AND stock_code = ANY(%s)
ORDER BY stock_code, datetime
"""

# ---------------------------------------------------------------------------
# 탐색 공간 (사전등록 고정값) -- search_config 가 학습 폴드 안에서 훑는다.
# ---------------------------------------------------------------------------
TF_GRID = (3, 5)
D_GRID = (0.04, 0.06, 0.08)
THETA_UP_GRID = (0.02, 0.03, 0.04)
THETA_DN_GRID = (0.02, 0.03)
FORWARD_GRID = (30, 60)
Q_GRID = (0.2, 0.4)
CLUSTER_KS = (6, 8, 10)

MIN_TRADES_PER_DAY = 0.5

ROUND_TRIP_COST = 0.0021


def _filter_regular_session(df: pd.DataFrame) -> pd.DataFrame:
    t = df["datetime"].dt.time
    return df[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]


# ---------------------------------------------------------------------------
# 이벤트 특징 (단일 봉 인덱스 기준, DB 무관 순수 함수)
# ---------------------------------------------------------------------------

def _close_pos_in_day(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                      idx: int) -> float:
    day_high = float(np.max(high[: idx + 1]))
    day_low = float(np.min(low[: idx + 1]))
    rng = day_high - day_low
    if rng == 0:
        return float("nan")
    return (float(close[idx]) - day_low) / rng


def _lower_wick_ratio(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                      idx: int) -> float:
    rng = float(high[idx] - low[idx])
    if rng == 0:
        return float("nan")
    return (float(close[idx]) - float(low[idx])) / rng


def _pre_vol(window_closes: np.ndarray) -> float:
    """21개 종가(idx-20..idx)로부터 20개 로그수익률의 (모집단) 표준편차를 %로."""
    log_rets = np.diff(np.log(window_closes))
    return float(np.std(log_rets)) * 100.0


# ---------------------------------------------------------------------------
# 이벤트 추출 (Step 1)
# ---------------------------------------------------------------------------

def find_first_event_idx(bars: pd.DataFrame, tf: int,
                         pre_bars: int = PRE_BARS, fwd_bars: int = FWD_BARS,
                         drop_pct: float = DROP_PCT_EXTRACT) -> int | None:
    """순수 함수 (DB 무관): 한 종목-일을 ``tf`` 분봉으로 리샘플한 ``bars`` 에서
    조건을 만족하는 첫 봉의 위치 인덱스를 찾는다. 없으면 ``None``.

    조건: prior_high = rolling(60//tf, min_periods=15//tf).max().shift(1) 대비
    -drop_pct 이하 하락(=full lookback, idx>=60//tf 를 함의) AND idx>=pre_bars
    (p0..p19 20개 사전 종가를 채울 수 있음) AND idx+fwd_bars<=n-1 (fwd_bars 개
    순방향 봉이 남아 있음).
    """
    n = len(bars)
    if n == 0:
        return None

    L = LOOKBACK_MIN // tf
    min_periods = MIN_LOOKBACK_MIN // tf

    high = bars["high"].to_numpy(dtype=float)
    close = bars["close"].to_numpy(dtype=float)

    prior_high = (
        pd.Series(high)
        .rolling(L, min_periods=min_periods)
        .max()
        .shift(1)
        .to_numpy()
    )

    bar_idx = np.arange(n)
    lookback_used = np.minimum(bar_idx, L)
    is_full = lookback_used == L
    is_valid = ~np.isnan(prior_high)

    with np.errstate(invalid="ignore", divide="ignore"):
        drop_actual = close / prior_high - 1.0
    is_candidate = drop_actual <= -drop_pct

    has_pre = bar_idx >= pre_bars
    has_fwd = bar_idx + fwd_bars <= (n - 1)

    qualifies = is_valid & is_full & is_candidate & has_pre & has_fwd
    idxs = np.where(qualifies)[0]
    if idxs.size == 0:
        return None
    return int(idxs[0])


def build_event_row(bars: pd.DataFrame, idx: int, tf: int, trade_date: str,
                    stock_code: str) -> dict:
    """순수 함수 (DB 무관): 후보 봉 1개 -> 이벤트 행 dict."""
    high = bars["high"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    close = bars["close"].to_numpy(dtype=float)

    L = LOOKBACK_MIN // tf
    min_periods = MIN_LOOKBACK_MIN // tf
    prior_high_series = (
        pd.Series(high).rolling(L, min_periods=min_periods).max().shift(1)
    )
    prior_high = float(prior_high_series.iloc[idx])
    entry_close = float(close[idx])
    drop_pct = entry_close / prior_high - 1.0

    p = close[idx - PRE_BARS: idx]
    fh = high[idx + 1: idx + 1 + FWD_BARS]
    fl = low[idx + 1: idx + 1 + FWD_BARS]
    fc = close[idx + 1: idx + 1 + FWD_BARS]
    window_closes = close[idx - PRE_BARS: idx + 1]

    row: dict = {
        "tf": tf,
        "stock_code": stock_code,
        "trade_date": trade_date,
        "entry_time": bars["datetime"].iloc[idx],
        "entry_close": entry_close,
        "drop_pct": drop_pct,
        "close_pos_in_day": _close_pos_in_day(high, low, close, idx),
        "lower_wick_ratio": _lower_wick_ratio(high, low, close, idx),
        "pre_vol": _pre_vol(window_closes),
    }
    for i in range(PRE_BARS):
        row[f"p{i}"] = float(p[i])
    for i in range(FWD_BARS):
        row[f"fh{i}"] = float(fh[i])
        row[f"fl{i}"] = float(fl[i])
        row[f"fc{i}"] = float(fc[i])
    return row


def build_events(start: str = START_DATE, end: str = END_DATE) -> pd.DataFrame:
    """day -> stock(정규장) -> tf(3,5) 루프. 한 번의 패스로 두 tf 모두 추출한다."""
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()

    rows: list[dict] = []
    for i, day in enumerate(days):
        raw = read_sql(_BARS_SQL, (day, codes), MINUTE_DB)
        if raw.empty:
            continue
        raw["datetime"] = pd.to_datetime(raw["datetime"])
        raw = _filter_regular_session(raw)
        if raw.empty:
            continue

        for code, g in raw.groupby("stock_code", sort=False):
            for tf in TFS:
                bars = resample_ohlcv(g, tf)
                if len(bars) < PRE_BARS + FWD_BARS + 2:
                    continue
                idx = find_first_event_idx(bars, tf)
                if idx is None:
                    continue
                rows.append(build_event_row(bars, idx, tf, day, code))

        if (i + 1) % 20 == 0:
            print(f"day {i + 1}/{len(days)} {day} events_so_far={len(rows)}")

    if not rows:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


# ---------------------------------------------------------------------------
# Step 2: 순수 함수 (DB 무관, 결정적)
# ---------------------------------------------------------------------------

def outcome_from_path(fh, fl, fc, entry: float, theta_up: float, theta_dn: float,
                      F: int) -> tuple[str, float]:
    """순방향 봉 0..F-1 을 스캔한다. 배리어를 먼저 건드린 봉이 결과를 정한다.

    "up": fh[j] >= entry*(1+theta_up) 이고 그 봉의 fl[j] > entry*(1-theta_dn)
    "down": fl[j] <= entry*(1-theta_dn) 이고 그 봉의 fh[j] < entry*(1+theta_up)
    "ambiguous": 그 봉이 양쪽을 다 건드림
    "none": F 봉 안에 아무것도 못 건드림

    terminal_ret = fc[F-1]/entry - 1 (항상 계산 -- none 버킷에 쓰임).
    """
    fh = np.asarray(fh, dtype=float)
    fl = np.asarray(fl, dtype=float)
    fc = np.asarray(fc, dtype=float)

    F = min(F, len(fh), len(fl), len(fc))
    up_target = entry * (1.0 + theta_up)
    dn_target = entry * (1.0 - theta_dn)

    outcome = "none"
    for j in range(F):
        up_touch = fh[j] >= up_target
        dn_touch = fl[j] <= dn_target
        if up_touch and dn_touch:
            outcome = "ambiguous"
        elif up_touch:
            outcome = "up"
        elif dn_touch:
            outcome = "down"
        else:
            continue
        break

    terminal_ret = float(fc[F - 1]) / entry - 1.0
    return outcome, terminal_ret


def expectancy(outcomes, terminal_rets, theta_up: float, theta_dn: float) -> dict:
    """gross = p_up*theta_up - (p_down+p_ambiguous)*theta_dn + p_none*mean_terminal_none.

    net = gross - ROUND_TRIP_COST. mean_terminal_none 이 정의되지 않을 때(=none
    표본이 0개)는 그 항을 0으로 취급한다(0 * NaN 오염 방지, first_touch.py
    _aggregate 와 동일한 관례).
    """
    outcomes = np.asarray(outcomes)
    terminal_rets = np.asarray(terminal_rets, dtype=float)
    n = len(outcomes)

    if n == 0:
        return {
            "gross": float("nan"), "net": float("nan"),
            "p_up": float("nan"), "p_down": float("nan"),
            "p_ambiguous": float("nan"), "p_none": float("nan"),
            "mean_terminal_none": float("nan"), "n": 0,
        }

    counts = pd.Series(outcomes).value_counts()
    p_up = counts.get("up", 0) / n
    p_down = counts.get("down", 0) / n
    p_ambiguous = counts.get("ambiguous", 0) / n
    p_none = counts.get("none", 0) / n

    none_mask = outcomes == "none"
    if none_mask.sum() > 0:
        mean_terminal_none = float(terminal_rets[none_mask].mean())
        none_term = p_none * mean_terminal_none
    else:
        mean_terminal_none = float("nan")
        none_term = 0.0

    gross = p_up * theta_up - (p_down + p_ambiguous) * theta_dn + none_term
    net = gross - ROUND_TRIP_COST

    return {
        "gross": float(gross), "net": float(net),
        "p_up": float(p_up), "p_down": float(p_down),
        "p_ambiguous": float(p_ambiguous), "p_none": float(p_none),
        "mean_terminal_none": mean_terminal_none, "n": int(n),
    }


def make_folds(trade_dates: np.ndarray, n_folds: int = 8) -> list[np.ndarray]:
    """정렬된 유니크 거래일을 ``n_folds`` 개의 연속·근등분 그룹으로 나눈다.

    나머지가 있으면 앞쪽 폴드들이 1개씩 더 받는다(크기 차이 <=1).
    """
    days = np.array(sorted(set(trade_dates)))
    n = len(days)
    base = n // n_folds
    rem = n % n_folds

    folds: list[np.ndarray] = []
    start = 0
    for i in range(n_folds):
        size = base + (1 if i < rem else 0)
        folds.append(days[start:start + size])
        start += size
    return folds


# ---------------------------------------------------------------------------
# Step 3: 폴드 내 탐색 -- 학습에서만 분위수/KMeans 를 계산한다.
# ---------------------------------------------------------------------------

def _quantile_filters(sub_d: pd.DataFrame) -> list[dict]:
    """학습 부분집합에서만 분위수 임계값을 계산한다 (절대값으로 고정)."""
    filters: list[dict] = [{"type": "none"}]
    for q in Q_GRID:
        filters.append({
            "type": "close_pos_in_day", "q": q,
            "threshold": float(sub_d["close_pos_in_day"].quantile(q)),
        })
    for q in Q_GRID:
        filters.append({
            "type": "lower_wick_ratio", "q": q,
            "threshold": float(sub_d["lower_wick_ratio"].quantile(q)),
        })
    filters.append({
        "type": "both", "q": 0.2,
        "close_pos_in_day_threshold": float(sub_d["close_pos_in_day"].quantile(0.2)),
        "lower_wick_ratio_threshold": float(sub_d["lower_wick_ratio"].quantile(0.2)),
    })
    return filters


def _nearest_centroid_labels(z: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    """fit 없이 최근접 중심점에만 배정한다 (평가 시 재학습 절대 금지)."""
    diffs = z[:, None, :] - centroids[None, :, :]
    dists = np.sum(diffs ** 2, axis=2)
    return np.argmin(dists, axis=1)


def _apply_filter_mask(df: pd.DataFrame, filt: dict) -> np.ndarray:
    """``filt`` 는 이미 확정된 절대값(threshold/centroids)만 담는다.

    이 함수는 절대 분위수를 다시 계산하지 않고 KMeans 를 절대 fit 하지
    않는다 -- 학습 채점과 평가(test) 양쪽에서 동일하게 재사용해 누수를
    구조적으로 막는다.
    """
    n = len(df)
    ftype = filt["type"]
    if ftype == "none":
        return np.ones(n, dtype=bool)
    if ftype == "close_pos_in_day":
        vals = df["close_pos_in_day"].to_numpy(dtype=float)
        return vals <= filt["threshold"]
    if ftype == "lower_wick_ratio":
        vals = df["lower_wick_ratio"].to_numpy(dtype=float)
        return vals <= filt["threshold"]
    if ftype == "both":
        cpid = df["close_pos_in_day"].to_numpy(dtype=float)
        lwr = df["lower_wick_ratio"].to_numpy(dtype=float)
        return ((cpid <= filt["close_pos_in_day_threshold"])
                & (lwr <= filt["lower_wick_ratio_threshold"]))
    if ftype == "cluster":
        if not filt["accepted"]:
            return np.zeros(n, dtype=bool)
        p_matrix = df[P_COLS].to_numpy(dtype=float)
        z = zscore_rows(p_matrix)
        centroids = np.asarray(filt["centroids"], dtype=float)
        labels = _nearest_centroid_labels(z, centroids)
        return np.isin(labels, list(filt["accepted"]))
    raise ValueError(f"unknown filter type: {ftype!r}")


def _fit_kmeans(sub_d: pd.DataFrame, k: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """학습 구간에서만 호출한다. z-정규화된 p0..p19 위에서 KMeans 를 적합한다."""
    p_matrix = sub_d[P_COLS].to_numpy(dtype=float)
    z = zscore_rows(p_matrix)
    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    labels = km.fit_predict(z)
    return labels, km.cluster_centers_


def _accepted_clusters(labels: np.ndarray, outcomes: np.ndarray, k: int) -> list[int]:
    """학습 edge_pp(=100*(p_up-p_down)) > 0 인 클러스터만 채택한다."""
    accepted = []
    for c in range(k):
        mask = labels == c
        if int(mask.sum()) == 0:
            continue
        sub_outcomes = outcomes[mask]
        p_up = float(np.mean(sub_outcomes == "up"))
        p_down = float(np.mean(sub_outcomes == "down"))
        if (p_up - p_down) > 0:
            accepted.append(c)
    return accepted


def _compute_outcomes_array(sub_d: pd.DataFrame, F: int, theta_up: float,
                            theta_dn: float) -> tuple[np.ndarray, np.ndarray]:
    entries = sub_d["entry_close"].to_numpy(dtype=float)
    fh = sub_d[FH_COLS].to_numpy(dtype=float)
    fl = sub_d[FL_COLS].to_numpy(dtype=float)
    fc = sub_d[FC_COLS].to_numpy(dtype=float)
    n = len(sub_d)
    outcomes = np.empty(n, dtype=object)
    terms = np.empty(n, dtype=float)
    for i in range(n):
        outcome, term = outcome_from_path(fh[i], fl[i], fc[i], entries[i],
                                          theta_up, theta_dn, F)
        outcomes[i] = outcome
        terms[i] = term
    return outcomes, terms


def _score_candidate(tf: int, D: float, theta_up: float, theta_dn: float,
                     forward_min: int, filt: dict, mask: np.ndarray,
                     outcomes: np.ndarray, terms: np.ndarray,
                     train_days: int) -> dict | None:
    n_trades = int(mask.sum())
    if n_trades == 0:
        return None
    exp = expectancy(outcomes[mask], terms[mask], theta_up, theta_dn)
    return {
        "tf": tf, "D": D, "theta_up": theta_up, "theta_dn": theta_dn,
        "forward_min": forward_min, "filter": filt,
        "n_trades": n_trades, "trades_per_day": n_trades / train_days,
        "net": exp["net"], "gross": exp["gross"],
        "p_up": exp["p_up"], "p_down": exp["p_down"],
        "p_ambiguous": exp["p_ambiguous"], "p_none": exp["p_none"],
        "mean_terminal_none": exp["mean_terminal_none"],
    }


def _better(a: dict, b: dict) -> bool:
    """목적함수: 학습 net 최대화. 동점이면 거래수 많은 쪽."""
    if a["net"] != b["net"]:
        return a["net"] > b["net"]
    return a["n_trades"] > b["n_trades"]


def search_config(train_df: pd.DataFrame, seed: int = 42) -> dict:
    """사전등록된 그리드를 학습 폴드 안에서만 전수 탐색한다.

    ``train_df`` 에는 이미 tf in {3,5} 모두와(추출 시 drop_pct<=-0.04 로 걸린)
    모든 이벤트가 섞여 있다고 가정한다. train_days = train_df 안의 유니크
    trade_date 개수 -- 시그니처가 train_df 하나로 고정돼 있어 별도의 거래일
    달력을 받을 수 없다(거의 매일 -4% 이벤트가 나온다는 사실상 보장 하의
    근사치, D 임계값이 커질수록 분모는 그대로 유지된다 -- 의도된 동작).

    제약: 학습 거래/학습일 >= 0.5 를 만족하는 후보 중 net 최대. 만족하는
    후보가 하나도 없으면 제약 없는 최적을 반환하고 constraint_met=False.
    """
    train_days = int(train_df["trade_date"].nunique())
    if train_days == 0:
        raise ValueError("search_config: empty training set")

    best: dict | None = None
    fallback_best: dict | None = None

    for tf in TF_GRID:
        sub_tf = train_df[train_df["tf"] == tf]
        if sub_tf.empty:
            continue
        for D in D_GRID:
            sub_d = sub_tf[sub_tf["drop_pct"] <= -D]
            n_d = len(sub_d)
            if n_d == 0:
                continue

            static_filters = _quantile_filters(sub_d)

            cluster_fits: dict[int, tuple[np.ndarray, np.ndarray]] = {}
            for k in CLUSTER_KS:
                if n_d < k:
                    continue
                cluster_fits[k] = _fit_kmeans(sub_d, k, seed)

            for forward_min in FORWARD_GRID:
                F = forward_min // tf
                for theta_up in THETA_UP_GRID:
                    for theta_dn in THETA_DN_GRID:
                        outcomes, terms = _compute_outcomes_array(
                            sub_d, F, theta_up, theta_dn)

                        candidates = []
                        for filt in static_filters:
                            mask = _apply_filter_mask(sub_d, filt)
                            candidates.append(_score_candidate(
                                tf, D, theta_up, theta_dn, forward_min, filt,
                                mask, outcomes, terms, train_days))

                        for k, (labels, centroids) in cluster_fits.items():
                            accepted = _accepted_clusters(labels, outcomes, k)
                            filt = {
                                "type": "cluster", "k": k, "seed": seed,
                                "centroids": centroids.tolist(),
                                "accepted": accepted,
                            }
                            mask = _apply_filter_mask(sub_d, filt)
                            candidates.append(_score_candidate(
                                tf, D, theta_up, theta_dn, forward_min, filt,
                                mask, outcomes, terms, train_days))

                        for cand in candidates:
                            if cand is None:
                                continue
                            if fallback_best is None or _better(cand, fallback_best):
                                fallback_best = cand
                            if (cand["trades_per_day"] >= MIN_TRADES_PER_DAY
                                    and (best is None or _better(cand, best))):
                                best = cand

    chosen = best if best is not None else fallback_best
    if chosen is None:
        raise ValueError("search_config: no candidate produced any trades")

    result = dict(chosen)
    result["constraint_met"] = best is not None
    return result


def evaluate_config(df: pd.DataFrame, config: dict, n_days: int) -> dict:
    """``config`` 를 그대로(재적합/재분위수화 없이) 평가 구간에 적용해 채점한다."""
    tf = config["tf"]
    D = config["D"]
    theta_up = config["theta_up"]
    theta_dn = config["theta_dn"]
    forward_min = config["forward_min"]
    F = forward_min // tf

    sub = df[(df["tf"] == tf) & (df["drop_pct"] <= -D)]
    outcomes, terms = _compute_outcomes_array(sub, F, theta_up, theta_dn)
    mask = _apply_filter_mask(sub, config["filter"])

    filt_outcomes = outcomes[mask]
    filt_terms = terms[mask]
    n_trades = int(len(filt_outcomes))
    exp = expectancy(filt_outcomes, filt_terms, theta_up, theta_dn)

    return {
        "n_trades": n_trades,
        "trades_per_day": (n_trades / n_days) if n_days else float("nan"),
        **exp,
    }


def _pooled_row(df: pd.DataFrame) -> dict:
    """거래 가중 합산 행."""
    total_trades = int(df["n_trades"].sum())
    total_test_days = int(df["test_days"].sum())

    if total_trades == 0:
        return {
            "fold": "pooled", "train_days": np.nan, "test_days": total_test_days,
            "config": None, "n_trades": 0, "trades_per_day": np.nan,
            "pct_up": np.nan, "pct_down": np.nan, "pct_ambiguous": np.nan,
            "pct_none": np.nan, "mean_terminal_none": np.nan,
            "gross_pct": np.nan, "net_pct": np.nan,
        }

    w = df["n_trades"]

    def _wavg(col: str) -> float:
        return float((df[col] * w).sum() / total_trades)

    none_weight = df["n_trades"] * (df["pct_none"] / 100.0)
    total_none = float(none_weight.sum())
    if total_none > 0:
        mean_terminal_none = float(
            (df["mean_terminal_none"].fillna(0.0) * none_weight).sum() / total_none)
    else:
        mean_terminal_none = float("nan")

    return {
        "fold": "pooled",
        "train_days": np.nan,
        "test_days": total_test_days,
        "config": None,
        "n_trades": total_trades,
        "trades_per_day": total_trades / total_test_days if total_test_days else np.nan,
        "pct_up": _wavg("pct_up"),
        "pct_down": _wavg("pct_down"),
        "pct_ambiguous": _wavg("pct_ambiguous"),
        "pct_none": _wavg("pct_none"),
        "mean_terminal_none": mean_terminal_none,
        "gross_pct": _wavg("gross_pct"),
        "net_pct": _wavg("net_pct"),
    }


def run(events_path=EVENTS_PARQUET, n_folds: int = 8) -> pd.DataFrame:
    """확장창(expanding): fold k 는 fold 1..k 로 학습, fold k+1 로 평가 (k=1..n_folds-1)."""
    events = pd.read_parquet(events_path)
    trade_dates = events["trade_date"].unique()
    folds = make_folds(trade_dates, n_folds)

    rows = []
    for k in range(1, n_folds):
        train_days_arr = np.concatenate(folds[:k])
        test_days_arr = folds[k]

        train_df = events[events["trade_date"].isin(train_days_arr)]
        test_df = events[events["trade_date"].isin(test_days_arr)]

        config = search_config(train_df)
        result = evaluate_config(test_df, config, n_days=len(test_days_arr))

        rows.append({
            "fold": k,
            "train_days": int(len(train_days_arr)),
            "test_days": int(len(test_days_arr)),
            "config": json.dumps(config, default=str, ensure_ascii=False),
            "n_trades": result["n_trades"],
            "trades_per_day": result["trades_per_day"],
            "pct_up": result["p_up"] * 100.0,
            "pct_down": result["p_down"] * 100.0,
            "pct_ambiguous": result["p_ambiguous"] * 100.0,
            "pct_none": result["p_none"] * 100.0,
            "mean_terminal_none": result["mean_terminal_none"],
            "gross_pct": result["gross"] * 100.0,
            "net_pct": result["net"] * 100.0,
        })

    result_df = pd.DataFrame(rows)
    pooled = _pooled_row(result_df)
    return pd.concat([result_df, pd.DataFrame([pooled])], ignore_index=True)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--extract-only", action="store_true",
                    help="Build _cache/wf_events.parquet and exit (no walk-forward).")
    ap.add_argument("--run", action="store_true",
                    help="Run the walk-forward on the cached events parquet.")
    ap.add_argument("--n-folds", type=int, default=8)
    args = ap.parse_args()

    if args.extract_only:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        print("building events...")
        events = build_events()
        events.to_parquet(EVENTS_PARQUET, index=False)
        n = len(events)
        n_tf3 = int((events["tf"] == 3).sum()) if n else 0
        n_tf5 = int((events["tf"] == 5).sum()) if n else 0
        n_dates = int(events["trade_date"].nunique()) if n else 0
        print(f"events: {n} | tf3: {n_tf3} | tf5: {n_tf5} | dates: {n_dates}")
        return

    if args.run:
        result_df = run(n_folds=args.n_folds)
        print(result_df.to_string(index=False))
        return

    print("nothing to do: pass --extract-only or --run")


if __name__ == "__main__":
    main()

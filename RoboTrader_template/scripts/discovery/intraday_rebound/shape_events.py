# scripts/discovery/intraday_rebound/shape_events.py
"""딥드롭 이벤트의 20봉 궤적 모양: 반등(up)과 지속하락(down)이 다른 모양인가.

이벤트 정의(고정 그리드포인트): tf=3, lookback=60분(20봉), min_lookback=15분
(5봉), drop_pct=6%, forward=60분(20봉), theta=3%. 종목-일당 이벤트는 최대
1개 — 조건을 만족하는 첫 봉(반드시 idx>=20, 즉 전체 룩백을 채운 봉)만 쓴다.

라벨러(labeler.compute_labels)를 재사용하지 않고 prior_high 를 직접
계산한다(labeler 와 동일한 규칙: rolling(20, min_periods=5).max().shift(1)).
first-touch 판정만 first_touch.first_touch_outcome 을 그대로 재사용한다.

이것은 백테스트가 아니고 매매 룰을 만들지 않는다. 20봉 궤적의 모양(z-정규화)이
up/down 사이에 실제로 다른지를 중앙값/사분위/클러스터로 기술할 뿐이다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from .db import MINUTE_DB, read_sql
from .first_touch import first_touch_outcome
from .resample import resample_ohlcv
from .universe import load_frozen_universe

TF = 3
LOOKBACK_MIN = 60
MIN_LOOKBACK_MIN = 15
DROP_PCT = 0.06
FORWARD_MIN = 60
THETA = 0.03

LOOKBACK_BARS = LOOKBACK_MIN // TF          # 20
MIN_LOOKBACK_BARS = MIN_LOOKBACK_MIN // TF  # 5
FORWARD_BARS = FORWARD_MIN // TF            # 20

START_DATE = "20250401"
END_DATE = "20260630"

REGULAR_OPEN = pd.Timestamp("09:00:00").time()
REGULAR_CLOSE = pd.Timestamp("15:30:00").time()

CACHE_DIR = Path(__file__).parent / "_cache"
EVENTS_PARQUET = CACHE_DIR / "shape_events_d6.parquet"
STATS_JSON = CACHE_DIR / "shape_stats.json"

W_COLS = [f"w{i}" for i in range(LOOKBACK_BARS)]

EVENT_COLUMNS = [
    "trade_date", "stock_code", "outcome", *W_COLS,
    "entry_close", "pre_vol", "close_pos_in_day", "lower_wick_ratio", "window",
]

OUTCOME_LABELS = ["up", "down", "ambiguous", "none"]

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


def _filter_regular_session(df: pd.DataFrame) -> pd.DataFrame:
    t = df["datetime"].dt.time
    return df[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]


def _window_label(trade_date: str) -> str:
    if trade_date <= "20250930":
        return "W1"
    if trade_date <= "20260131":
        return "W2"
    if trade_date <= "20260531":
        return "W3"
    return "W4"


def find_first_event_idx(bars: pd.DataFrame,
                         lookback_bars: int = LOOKBACK_BARS,
                         min_lookback_bars: int = MIN_LOOKBACK_BARS,
                         drop_pct: float = DROP_PCT) -> int | None:
    """순수 함수 (DB 무관): 한 종목-일 ``bars`` 에서 조건을 만족하는 첫 봉의
    위치 인덱스를 찾는다. 없으면 ``None`` (그 종목-일은 통째로 스킵).

    조건: prior_high 대비 -drop_pct 이하 하락 AND 전체 룩백
    (lookback_bars_used == lookback_bars, 이는 idx >= lookback_bars 를
    함의한다) AND 순방향 봉이 최소 1개 이상 남아 있음(idx < n-1).

    prior_high 는 labeler.compute_labels 와 동일한 규칙으로 직접 계산한다:
    ``rolling(lookback_bars, min_periods=min_lookback_bars).max().shift(1)``.
    """
    n = len(bars)
    if n == 0:
        return None

    high = bars["high"].to_numpy(dtype=float)
    close = bars["close"].to_numpy(dtype=float)

    prior_high = (
        pd.Series(high)
        .rolling(lookback_bars, min_periods=min_lookback_bars)
        .max()
        .shift(1)
        .to_numpy()
    )

    bar_idx = np.arange(n)
    lookback_used = np.minimum(bar_idx, lookback_bars)
    is_full = lookback_used == lookback_bars
    is_valid = ~np.isnan(prior_high)

    with np.errstate(invalid="ignore", divide="ignore"):
        drop_actual = close / prior_high - 1.0
    is_candidate = drop_actual <= -drop_pct

    has_forward = bar_idx < (n - 1)

    qualifies = is_valid & is_full & is_candidate & has_forward
    idxs = np.where(qualifies)[0]
    if idxs.size == 0:
        return None
    return int(idxs[0])


def _pre_vol(window_closes: np.ndarray) -> float:
    """21개 종가(idx-20..idx, w0..w19 + entry_close)로부터 20개 로그수익률의
    (모집단) 표준편차를 백분율로 낸다.
    """
    log_rets = np.diff(np.log(window_closes))
    return float(np.std(log_rets)) * 100.0


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


def build_event_row(bars: pd.DataFrame, idx: int, trade_date: str,
                    stock_code: str) -> dict:
    """순수 함수 (DB 무관): 후보 봉 1개 -> 이벤트 행 dict."""
    high = bars["high"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    close = bars["close"].to_numpy(dtype=float)

    outcome, _ = first_touch_outcome(bars, close_idx=idx,
                                     forward_bars=FORWARD_BARS, theta=THETA)

    w = close[idx - LOOKBACK_BARS: idx]
    entry_close = float(close[idx])
    window_closes = close[idx - LOOKBACK_BARS: idx + 1]

    row: dict = {
        "trade_date": trade_date,
        "stock_code": stock_code,
        "outcome": outcome,
    }
    for i in range(LOOKBACK_BARS):
        row[f"w{i}"] = float(w[i])
    row["entry_close"] = entry_close
    row["pre_vol"] = _pre_vol(window_closes)
    row["close_pos_in_day"] = _close_pos_in_day(high, low, close, idx)
    row["lower_wick_ratio"] = _lower_wick_ratio(high, low, close, idx)
    row["window"] = _window_label(trade_date)
    return row


def build_events(start: str = START_DATE, end: str = END_DATE) -> pd.DataFrame:
    """day -> stock(정규장) 루프. 종목-일당 조건을 만족하는 첫 봉만 이벤트로 남긴다."""
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
            bars = resample_ohlcv(g, TF)
            if len(bars) < MIN_LOOKBACK_BARS + 2:
                continue

            idx = find_first_event_idx(bars)
            if idx is None:
                continue

            rows.append(build_event_row(bars, idx, day, code))

        if (i + 1) % 20 == 0:
            print(f"day {i + 1}/{len(days)} {day} events_so_far={len(rows)}")

    if not rows:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def zscore_rows(matrix: np.ndarray) -> np.ndarray:
    """행 단위 z-정규화. 평탄한(std=0) 행은 전부 0 (NaN 아님)."""
    mean = matrix.mean(axis=1, keepdims=True)
    std = matrix.std(axis=1, keepdims=True)
    centered = matrix - mean
    return np.divide(centered, std, out=np.zeros_like(centered), where=std != 0)


def compute_separation(z: np.ndarray, outcomes: np.ndarray) -> dict:
    """순수 함수 (DB 무관): z-정규화 행렬 + outcome 라벨 배열 -> separation 지표.

    ``pooled_sd_last_bar`` 는 outcome 과 무관하게 전체 이벤트로 계산한다.
    ``median_abs_gap``/``gap_last_bar_in_sd`` 는 up/down 두 그룹 모두 존재할
    때만 정의된다(둘 중 하나라도 비어 있으면 NaN).
    """
    outcomes = np.asarray(outcomes)
    pooled_sd_last_bar = float(np.std(z[:, -1])) if len(z) else float("nan")

    up_mask = outcomes == "up"
    down_mask = outcomes == "down"
    if up_mask.sum() > 0 and down_mask.sum() > 0:
        median_up = np.median(z[up_mask], axis=0)
        median_down = np.median(z[down_mask], axis=0)
        median_abs_gap = float(np.mean(np.abs(median_up - median_down)))
        gap_last_bar_in_sd = (
            abs(float(median_up[-1] - median_down[-1])) / pooled_sd_last_bar
            if pooled_sd_last_bar != 0 else float("nan")
        )
    else:
        median_abs_gap = float("nan")
        gap_last_bar_in_sd = float("nan")

    return {
        "median_abs_gap": round(median_abs_gap, 4),
        "pooled_sd_last_bar": round(pooled_sd_last_bar, 4),
        "gap_last_bar_in_sd": round(gap_last_bar_in_sd, 4),
    }


def _by_outcome_stats(z: np.ndarray, events: pd.DataFrame) -> dict:
    out: dict = {}
    for outcome in OUTCOME_LABELS:
        mask = (events["outcome"] == outcome).to_numpy()
        n = int(mask.sum())
        if n == 0:
            out[outcome] = {"n": 0, "median": [], "q25": [], "q75": [],
                            "mean_pre_vol": None}
            continue
        sub = z[mask]
        out[outcome] = {
            "n": n,
            "median": [round(float(x), 4) for x in np.median(sub, axis=0)],
            "q25": [round(float(x), 4) for x in np.percentile(sub, 25, axis=0)],
            "q75": [round(float(x), 4) for x in np.percentile(sub, 75, axis=0)],
            "mean_pre_vol": round(float(events.loc[mask, "pre_vol"].mean()), 4),
        }
    return out


def _cluster_stats(z: np.ndarray, events: pd.DataFrame, k: int,
                   seed: int) -> list[dict]:
    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    labels = km.fit_predict(z)

    clusters = []
    for c in range(k):
        mask = labels == c
        n_c = int(mask.sum())
        centroid = [round(float(x), 4) for x in km.cluster_centers_[c]]
        if n_c == 0:
            clusters.append({
                "cluster": c, "n": 0, "pct_up": None, "pct_down": None,
                "up_over_down": None, "mean_pre_vol": None, "centroid": centroid,
            })
            continue

        sub_outcomes = events.loc[mask, "outcome"]
        pct_up = round(100.0 * float((sub_outcomes == "up").mean()), 2)
        pct_down = round(100.0 * float((sub_outcomes == "down").mean()), 2)
        up_over_down = round(pct_up / pct_down, 4) if pct_down != 0 else None
        mean_pre_vol = round(float(events.loc[mask, "pre_vol"].mean()), 4)

        clusters.append({
            "cluster": c, "n": n_c, "pct_up": pct_up, "pct_down": pct_down,
            "up_over_down": up_over_down, "mean_pre_vol": mean_pre_vol,
            "centroid": centroid,
        })
    return clusters


def compute_stats(events: pd.DataFrame, cluster_k: int = 8, seed: int = 42) -> dict:
    """순수 함수 (DB 무관): 완성된 이벤트 표 -> shape_stats.json 이 될 dict."""
    n_total = len(events)
    n_dates = int(events["trade_date"].nunique()) if n_total else 0

    vc = events["outcome"].value_counts()
    counts = {k: int(vc.get(k, 0)) for k in OUTCOME_LABELS}

    w_matrix = events[W_COLS].to_numpy(dtype=float)
    z = zscore_rows(w_matrix)
    outcomes = events["outcome"].to_numpy()

    return {
        "n_total": n_total,
        "n_dates": n_dates,
        "counts": counts,
        "bar_index": list(range(LOOKBACK_BARS)),
        "by_outcome": _by_outcome_stats(z, events),
        "separation": compute_separation(z, outcomes),
        "clusters": _cluster_stats(z, events, cluster_k, seed),
        "cluster_k": cluster_k,
    }


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("building events...")
    events = build_events()
    print(f"events built: n={len(events)}")
    events.to_parquet(EVENTS_PARQUET, index=False)
    print(f"wrote {EVENTS_PARQUET}")

    stats = compute_stats(events)
    with open(STATS_JSON, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"wrote {STATS_JSON}")


if __name__ == "__main__":
    main()

# scripts/discovery/intraday_rebound/stability_scan.py
"""무조건적 딥드롭 진입의 그리드 셀 (TF, N, D, M) 이 서로 겹치지 않는 시간
구간에서도 부호(pct_up - pct_down)가 안정적인지 스캔한다.

한 셀이 2026-06(up>down) 과 2026-02..05(down>up) 사이에서 이미 부호를
뒤집은 적이 있다. 여기서 찾는 것은 "가장 수익성 좋은 셀"이 아니라 "절대
뒤집히지 않는 셀"이다 — 수익성은 이 스캔의 관심사가 아니다.

성능: 셀마다 compute_labels/first_touch_outcome 을 재호출하는 나이브 루프는
종목-일당 108번 재스캔한다 (~2.5시간). 대신 (종목-일, TF) 당 딱 한 번만
first_up_off/first_dn_off 를 스캔하고, N/D/M 은 그 결과에서 파생한다
(재스캔 없음). 자세한 근거는 ``compute_first_touch_offsets`` / ``_scan_stock_day``
docstring 참고.

이것은 백테스트가 아니고 매매 룰을 만들지 않는다.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from .db import MINUTE_DB, read_sql
from .resample import resample_ohlcv
from .universe import load_frozen_universe

TFS = (3, 5, 15)
NS = (30, 60, 120)
DS = (0.025, 0.04, 0.06, 0.08)
MS = (30, 60, 120)
THETA = 0.03

# 라벨러와 동일한 최소 룩백 (labeler.LabelParams 기본값). N//tf 가 이보다
# 작을 일은 NS/TFS 조합상 없지만(가장 작은 조합 30//15=2 >= 15//15=1),
# 방어적으로 고정해 둔다.
MIN_LOOKBACK_MIN = 15

# 가장 긴 순방향 윈도우 (bars 단위 환산은 tf 로 나눠서 셀마다 계산).
MAX_FORWARD_MIN = max(MS)

WINDOWS: dict[str, tuple[str, str]] = {
    "W1_2025H1": ("20250401", "20250930"),
    "W2_2025H2": ("20251001", "20260131"),
    "W3_2026a": ("20260201", "20260531"),
    "W4_2026Jun": ("20260601", "20260630"),
}

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

REGULAR_OPEN = pd.Timestamp("09:00:00").time()
REGULAR_CLOSE = pd.Timestamp("15:30:00").time()

OUT_COLUMNS = [
    "window", "tf", "n_lookback", "drop_pct", "m_forward",
    "n", "n_dates", "pct_up", "pct_down", "pct_ambiguous", "pct_none", "edge_pp",
]

CELL_COLS = ["tf", "n_lookback", "drop_pct", "m_forward"]


def _filter_regular_session(df: pd.DataFrame) -> pd.DataFrame:
    t = df["datetime"].dt.time
    return df[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]


def compute_first_touch_offsets(bars: pd.DataFrame, theta: float,
                                f_max: int) -> tuple[np.ndarray, np.ndarray]:
    """(종목-일, TF) 당 단 한 번의 스캔.

    반환: (first_up_off, first_dn_off), 각각 길이 len(bars) 인 정수 배열.
    ``first_up_off[t]`` = ``high[t+k] >= close[t]*(1+theta)`` 를 만족하는
    가장 작은 ``k in 1..f_max``, 없으면 ``-1``. ``first_dn_off`` 는 대칭
    (low/하방 배리어). 오프셋 스캔은 세션의 마지막 봉에서 잘린다 — ``t+k``
    가 ``len(bars)-1`` 을 넘어서는 ``k`` 는 절대 조회하지 않는다(설령
    ``f_max`` 가 더 허용하더라도).

    루프는 ``t`` 가 아니라 ``k`` (최대 ``f_max`` 회) 위로 돈다 — 매 반복이
    전체 ``t`` 배열에 대해 벡터화돼 있으므로 O(f_max * n) 이지만 파이썬
    레벨 t-루프는 없다.
    """
    high = bars["high"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    close = bars["close"].to_numpy(dtype=float)
    n = len(bars)

    first_up_off = np.full(n, -1, dtype=int)
    first_dn_off = np.full(n, -1, dtype=int)
    if n == 0:
        return first_up_off, first_dn_off

    up_target = close * (1.0 + theta)
    dn_target = close * (1.0 - theta)

    max_k = min(f_max, n - 1)
    for k in range(1, max_k + 1):
        t_idx = np.arange(0, n - k)  # t+k 가 세션 안에 있는 t 들만.

        up_pending = first_up_off[t_idx] == -1
        up_touch = up_pending & (high[t_idx + k] >= up_target[t_idx])
        first_up_off[t_idx[up_touch]] = k

        dn_pending = first_dn_off[t_idx] == -1
        dn_touch = dn_pending & (low[t_idx + k] <= dn_target[t_idx])
        first_dn_off[t_idx[dn_touch]] = k

    return first_up_off, first_dn_off


def classify_outcomes(up_off: np.ndarray, dn_off: np.ndarray, f: int) -> np.ndarray:
    """first_touch.first_touch_outcome 의 판정 규칙과 동등한 벡터화 버전.

    ``up_in``/``dn_in`` 은 각 배리어가 순방향 창 ``f`` 봉 안에서 터치됐는지.
    둘 다 터치됐으면 어느 오프셋이 더 작은지로 승부(같으면 ambiguous — 같은
    봉이 양쪽을 다 건드렸다는 뜻, first_touch_outcome 과 동일한 정의).
    """
    up_in = (up_off > 0) & (up_off <= f)
    dn_in = (dn_off > 0) & (dn_off <= f)

    outcome = np.full(up_off.shape, "none", dtype=object)
    outcome[up_in & ~dn_in] = "up"
    outcome[dn_in & ~up_in] = "down"

    both = up_in & dn_in
    outcome[both & (up_off < dn_off)] = "up"
    outcome[both & (up_off > dn_off)] = "down"
    outcome[both & (up_off == dn_off)] = "ambiguous"
    return outcome


def _scan_stock_day(bars: pd.DataFrame, tf: int) -> dict[tuple[int, float, int], np.ndarray]:
    """순수 함수 (DB 무관): 한 종목-일을 ``tf`` 분봉으로 리샘플한 ``bars`` 에서
    모든 (n_lookback, drop_pct, m_forward) 그리드 셀의 outcome 배열을 단 한
    번의 first-touch 스캔으로 파생시킨다.

    ``full`` 룩백 구간만 포함한다 (``lookback_bars_used == n_lookback // tf``).
    반환값의 각 배열은 그 셀의 후보 봉들에 대한 outcome 문자열이며(봉 인덱스
    오름차순), 후보가 없으면 길이 0 배열.
    """
    n_bars = len(bars)
    empty = np.empty(0, dtype=object)
    out: dict[tuple[int, float, int], np.ndarray] = {}

    if n_bars == 0:
        for n_lookback in NS:
            for drop_pct in DS:
                for m_forward in MS:
                    out[(n_lookback, drop_pct, m_forward)] = empty
        return out

    f_max = max(1, MAX_FORWARD_MIN // tf)
    first_up_off, first_dn_off = compute_first_touch_offsets(bars, THETA, f_max)

    high = bars["high"].to_numpy(dtype=float)
    close = bars["close"].to_numpy(dtype=float)
    bar_idx = np.arange(n_bars)
    min_periods = max(1, MIN_LOOKBACK_MIN // tf)

    for n_lookback in NS:
        L = max(1, n_lookback // tf)
        prior_high = (
            pd.Series(high).rolling(L, min_periods=min_periods).max().shift(1).to_numpy()
        )
        lookback_used = np.minimum(bar_idx, L)
        full_mask = lookback_used == L
        with np.errstate(invalid="ignore", divide="ignore"):
            drop_actual = close / prior_high - 1.0
        valid_mask = full_mask & ~np.isnan(prior_high)

        for drop_pct in DS:
            cand_idx = np.where(valid_mask & (drop_actual <= -drop_pct))[0]
            if cand_idx.size == 0:
                for m_forward in MS:
                    out[(n_lookback, drop_pct, m_forward)] = empty
                continue

            up_off = first_up_off[cand_idx]
            dn_off = first_dn_off[cand_idx]
            for m_forward in MS:
                f = max(1, m_forward // tf)
                out[(n_lookback, drop_pct, m_forward)] = classify_outcomes(up_off, dn_off, f)

    return out


def _build_row(window: str, tf: int, n_lookback: int, drop_pct: float,
              m_forward: int, n: int, n_dates: int, counts: dict) -> dict:
    """순수 함수 (DB 무관): 누적된 outcome 카운트 -> 표 한 행.

    pct_none 은 나머지로 강제한다 (asym_grid/first_touch 와 동일 패턴) —
    넷을 독립적으로 반올림하면 합이 100 을 벗어날 수 있다. edge_pp 는 반올림된
    pct_up/pct_down 의 차이로 정의한다(스펙 그대로) — 반올림 전 원값이 아니다.
    """
    if n == 0:
        nan = float("nan")
        return {
            "window": window, "tf": tf, "n_lookback": n_lookback, "drop_pct": drop_pct,
            "m_forward": m_forward, "n": 0, "n_dates": n_dates,
            "pct_up": nan, "pct_down": nan, "pct_ambiguous": nan, "pct_none": nan,
            "edge_pp": nan,
        }

    pct_up = round(100.0 * counts.get("up", 0) / n, 3)
    pct_down = round(100.0 * counts.get("down", 0) / n, 3)
    pct_ambiguous = round(100.0 * counts.get("ambiguous", 0) / n, 3)
    pct_none = round(100.0 - pct_up - pct_down - pct_ambiguous, 3)
    edge_pp = round(pct_up - pct_down, 3)

    return {
        "window": window, "tf": tf, "n_lookback": n_lookback, "drop_pct": drop_pct,
        "m_forward": m_forward, "n": n, "n_dates": n_dates,
        "pct_up": pct_up, "pct_down": pct_down, "pct_ambiguous": pct_ambiguous,
        "pct_none": pct_none, "edge_pp": edge_pp,
    }


def scan(windows: dict[str, tuple[str, str]] = WINDOWS) -> pd.DataFrame:
    """window -> day -> stock -> tf 루프. (종목-일, tf) 당 first-touch 오프셋을
    한 번만 스캔하고, 108 개 (N, D, M) 셀 전부를 재스캔 없이 파생시켜 누적한다.
    """
    codes = load_frozen_universe()

    counts: dict[tuple, Counter] = {}
    dates: dict[tuple, set] = {}

    for window_name, (start, end) in windows.items():
        days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
        for day in days:
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
                    if len(bars) < 2:
                        continue
                    per_cell = _scan_stock_day(bars, tf)
                    for (n_lb, d, m), outcomes in per_cell.items():
                        if outcomes.size == 0:
                            continue
                        key = (window_name, tf, n_lb, d, m)
                        counts.setdefault(key, Counter()).update(outcomes.tolist())
                        dates.setdefault(key, set()).add(day)

    rows = []
    for window_name in windows:
        for tf in TFS:
            for n_lb in NS:
                for d in DS:
                    for m in MS:
                        key = (window_name, tf, n_lb, d, m)
                        c = counts.get(key, Counter())
                        n = sum(c.values())
                        n_dates = len(dates.get(key, set()))
                        rows.append(_build_row(window_name, tf, n_lb, d, m, n, n_dates, c))

    return pd.DataFrame(rows, columns=OUT_COLUMNS)


def summarize(df: pd.DataFrame) -> dict:
    """순수 함수 (DB 무관): scan() 출력을 셀별 부호 안정성으로 요약한다.

    ``stable_positive``/``stable_negative``/``flipped`` 는 각각 실제 셀
    식별자(dict, tf/n_lookback/drop_pct/m_forward + min_n_across_windows)의
    리스트다 — 개수만이 아니다. 어떤 윈도우에서든 데이터가 없는(n=0 ->
    edge_pp NaN) 셀은 안정적이라 판단할 근거가 없으므로 flipped 로 분류한다.
    """
    per_window_median_edge = {
        window: round(float(g["edge_pp"].median()), 3)
        for window, g in df.groupby("window")
    }

    windows = sorted(df["window"].unique())
    min_n_across_windows: dict[tuple, int] = {}
    stable_positive: list[dict] = []
    stable_negative: list[dict] = []
    flipped: list[dict] = []

    for cell_key, g in df.groupby(CELL_COLS, sort=True):
        edge_by_window = dict(zip(g["window"], g["edge_pp"]))
        n_by_window = dict(zip(g["window"], g["n"]))
        min_n = int(min(n_by_window.get(w, 0) for w in windows))
        min_n_across_windows[cell_key] = min_n

        cell_dict = dict(zip(CELL_COLS, cell_key))
        cell_dict["min_n_across_windows"] = min_n

        edges = [edge_by_window.get(w) for w in windows]
        if any(e is None or (isinstance(e, float) and np.isnan(e)) for e in edges):
            flipped.append(cell_dict)
        elif all(e > 0 for e in edges):
            stable_positive.append(cell_dict)
        elif all(e < 0 for e in edges):
            stable_negative.append(cell_dict)
        else:
            flipped.append(cell_dict)

    return {
        "per_window_median_edge": per_window_median_edge,
        "stable_positive": stable_positive,
        "stable_negative": stable_negative,
        "flipped": flipped,
        "min_n_across_windows": min_n_across_windows,
    }


if __name__ == "__main__":
    result_df = scan()
    print(result_df.to_string(index=False))
    summary = summarize(result_df)
    print("per_window_median_edge:", summary["per_window_median_edge"])
    print("stable_positive:", len(summary["stable_positive"]))
    print("stable_negative:", len(summary["stable_negative"]))
    print("flipped:", len(summary["flipped"]))

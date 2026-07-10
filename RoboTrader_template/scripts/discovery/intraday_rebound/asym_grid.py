# scripts/discovery/intraday_rebound/asym_grid.py
"""비대칭 배리어(TP != SL) in-sample 그리드.

symmetric ±3% 배리어에서 deep-drop 진입의 gross expectancy(+0.09%)가 왕복비용
(0.21%)을 넘지 못한다는 사실은 이미 알려져 있다. 두 특징(close_pos_in_day,
lower_wick_ratio)이 승/패를 가르지만 — 패율을 깎을 뿐 승률은 올리지 않는다
(pct_down 12.89% -> 9.48%). 손절을 좁히면 바로 그 효과가 증폭되어야 한다.
이 모듈은 그것을 in-sample 그리드로 측정한다.

첫 통과(first-touch) 기계는 그대로다 (first_touch.first_touch_outcome). 이
모듈이 하는 일은 하루 루프 안에서 (theta_up, theta_dn) 그리드 전체를 후보 봉
1개당 여러 번 재스캔하는 것뿐이다 — DB는 그리드 셀마다가 아니라 날짜당 한 번만
읽는다.

이것은 백테스트가 아니고 매매 룰을 만들지 않는다.
"""
from __future__ import annotations

import pandas as pd

from .db import DAILY_DB, MINUTE_DB, read_sql
from .features import compute_features
from .first_touch import first_touch_outcome
from .labeler import LabelParams, compute_labels
from .outcome_probe import (
    MIN_DAILY_ROWS,
    _daily_ctx_for_stock_day,
    _filter_regular_session,
    _trade_date_to_dash,
)
from .resample import resample_ohlcv
from .universe import load_frozen_universe

# 2026-06 하위 5분위 컷 (feature-probe 결과). 라이브 룰이 아니다 — in-sample
# 그리드에서 이 컷을 통과한 부분집합이 손절을 좁혔을 때 어떻게 반응하는지 볼
# 뿐이다.
FILTER_CLOSE_POS_MAX = 0.043
FILTER_LOWER_WICK_MAX = 0.083

# 수수료 0.015% x2(매수+매도) + 거래세 0.18%(매도시만) = 0.21% (config/constants.py:118-119)
ROUND_TRIP_COST = 0.0021

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

_DAILY_SQL = """
WITH ranked AS (
    SELECT stock_code, date, open, high, low, close, market_cap,
           ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY date DESC) AS rn
    FROM daily_prices
    WHERE stock_code = ANY(%s) AND date < %s
)
SELECT stock_code, date, open, high, low, close, market_cap
FROM ranked WHERE rn <= %s
ORDER BY stock_code, date
"""

ROWS_COLUMNS = [
    "theta_up", "theta_dn", "segment", "trade_date",
    "close_pos_in_day", "lower_wick_ratio", "outcome", "terminal_ret",
]

OUT_COLUMNS = [
    "theta_up", "theta_dn", "segment", "filt", "n", "n_dates",
    "pct_up", "pct_down", "pct_ambiguous", "n_ambiguous", "pct_none",
    "mean_terminal_none", "gross_pct", "net_pct", "rr",
]


def _filtered_mask(df: pd.DataFrame) -> pd.Series:
    return ((df["close_pos_in_day"] <= FILTER_CLOSE_POS_MAX)
            & (df["lower_wick_ratio"] <= FILTER_LOWER_WICK_MAX))


def _aggregate_one(df: pd.DataFrame, theta_up: float, theta_dn: float,
                   segment: str, filt: str) -> dict | None:
    n = len(df)
    if n == 0:
        return None

    known = {"up", "down", "ambiguous", "none"}
    unknown = set(df["outcome"]) - known
    assert not unknown, f"unknown outcome labels: {unknown}"

    counts = df["outcome"].value_counts()
    p_up = counts.get("up", 0) / n
    p_down = counts.get("down", 0) / n
    p_amb = counts.get("ambiguous", 0) / n
    p_none = counts.get("none", 0) / n

    none_ret = df.loc[df["outcome"] == "none", "terminal_ret"]
    if len(none_ret) > 0:
        mean_terminal_none = float(none_ret.mean())
        none_term = p_none * mean_terminal_none
    else:
        mean_terminal_none = float("nan")
        none_term = 0.0

    # ambiguous 는 보수적으로 근접 손절(theta_dn)에서 청산된 것으로 취급한다
    # — 한 봉이 양쪽을 다 건드리면 가까운 쪽(대개 손절)이 먼저 체결됐을
    # 가능성이 높다.
    gross = p_up * theta_up - p_down * theta_dn - p_amb * theta_dn + none_term
    net = gross - ROUND_TRIP_COST

    pct_up = round(p_up * 100, 3)
    pct_down = round(p_down * 100, 3)
    pct_ambiguous = round(p_amb * 100, 3)
    n_ambiguous = int(counts.get("ambiguous", 0))
    # pct_none 은 나머지로 강제한다 — 넷을 독립적으로 반올림하면 합이 100 을
    # 벗어날 수 있다.
    pct_none = round(100.0 - pct_up - pct_down - pct_ambiguous, 3)

    n_dates = int(df["trade_date"].nunique())

    return {
        "theta_up": theta_up,
        "theta_dn": theta_dn,
        "segment": segment,
        "filt": filt,
        "n": n,
        "n_dates": n_dates,
        "pct_up": pct_up,
        "pct_down": pct_down,
        "pct_ambiguous": pct_ambiguous,
        "n_ambiguous": n_ambiguous,
        "pct_none": pct_none,
        "mean_terminal_none": round(mean_terminal_none * 100, 3),
        "gross_pct": round(gross * 100, 3),
        "net_pct": round(net * 100, 3),
        "rr": theta_up / theta_dn,
    }


def _aggregate_grid(rows_df: pd.DataFrame) -> pd.DataFrame:
    """순수 함수 (DB 무관): (theta_up, theta_dn, segment, filt) 별 원시 행을 집계한다."""
    if rows_df.empty:
        return pd.DataFrame(columns=OUT_COLUMNS)

    filtered_mask = _filtered_mask(rows_df)

    records = []
    group_cols = ["theta_up", "theta_dn", "segment"]
    for (theta_up, theta_dn, segment), g in rows_df.groupby(group_cols, sort=True):
        mask_g = filtered_mask.loc[g.index]
        for filt, sub in (("all", g), ("filtered", g[mask_g])):
            rec = _aggregate_one(sub, theta_up, theta_dn, segment, filt)
            if rec is not None:
                records.append(rec)

    return pd.DataFrame(records, columns=OUT_COLUMNS)


def _build_grid_rows(start: str, end: str, theta_ups: tuple[float, ...],
                     theta_dns: tuple[float, ...], tf: int, lookback_min: int,
                     drop_pct: float, forward_min: int) -> pd.DataFrame:
    """day -> stock(정규장) 루프. 후보 봉마다 필터 특징을 한 번 계산하고,
    그리드 전체 (theta_up, theta_dn) 쌍에 대해 first_touch_outcome 을
    재스캔한다 (DB 는 날짜당 한 번만 읽는다).
    """
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
    # theta 는 compute_labels 내부의 hit_up/hit_down/mae/hit_close 계산에만
    # 쓰이는데, 이 모듈은 그 컬럼들을 소비하지 않는다(is_candidate/forward_bars/
    # prior_high/is_full_lookback 만 사용) — 어떤 값을 넣어도 결과에 영향이 없다.
    params = LabelParams(timeframe_minutes=tf, lookback_min=lookback_min,
                         drop_pct=drop_pct, forward_min=forward_min, theta=0.03)

    rows: list[dict] = []
    for day in days:
        raw = read_sql(_BARS_SQL, (day, codes), MINUTE_DB)
        if raw.empty:
            continue
        raw["datetime"] = pd.to_datetime(raw["datetime"])
        raw = _filter_regular_session(raw)
        if raw.empty:
            continue

        resampled: dict[str, pd.DataFrame] = {}
        norm_returns: dict[str, pd.Series] = {}
        for code, g in raw.groupby("stock_code", sort=False):
            bars = resample_ohlcv(g, params.timeframe_minutes)
            if bars.empty:
                continue
            resampled[code] = bars
            close_by_dt = bars.set_index("datetime")["close"]
            norm_returns[code] = close_by_dt / close_by_dt.iloc[0] - 1.0

        if not resampled:
            continue

        # 시장 프록시: 종목별 정규화 수익률의 매 타임스탬프 중앙값.
        median_ret = pd.concat(norm_returns, axis=1).median(axis=1, skipna=True)

        daily_raw = read_sql(_DAILY_SQL, (codes, _trade_date_to_dash(day),
                                          MIN_DAILY_ROWS), DAILY_DB)

        for code, bars in resampled.items():
            if len(bars) < params.min_lookback_bars + 2:
                continue

            g_daily = daily_raw[daily_raw["stock_code"] == code]
            day_open = float(bars["open"].iloc[0])
            ctx = _daily_ctx_for_stock_day(g_daily, day_open)
            if ctx is None:
                continue

            lab = compute_labels(bars, params)
            cand = lab[lab["is_candidate"] & lab["is_valid"] & (lab["forward_bars"] > 0)]
            if cand.empty:
                continue

            mret = median_ret.reindex(bars["datetime"]).to_numpy()
            feat = compute_features(bars, lab["prior_high"], ctx, mret,
                                    lookback_bars=params.lookback_bars)

            for idx, lab_row in cand.iterrows():
                segment = "full" if lab_row["is_full_lookback"] else "partial"
                close_pos = float(feat.loc[idx, "close_pos_in_day"])
                lower_wick = float(feat.loc[idx, "lower_wick_ratio"])
                fwd = int(lab_row["forward_bars"])

                for theta_up in theta_ups:
                    for theta_dn in theta_dns:
                        outcome, terminal_ret = first_touch_outcome(
                            bars, close_idx=idx, forward_bars=fwd,
                            theta=theta_up, theta_dn=theta_dn)
                        rows.append({
                            "theta_up": theta_up,
                            "theta_dn": theta_dn,
                            "segment": segment,
                            "trade_date": day,
                            "close_pos_in_day": close_pos,
                            "lower_wick_ratio": lower_wick,
                            "outcome": outcome,
                            "terminal_ret": terminal_ret,
                        })

    return pd.DataFrame(rows, columns=ROWS_COLUMNS)


def analyze_grid(start: str, end: str,
                 theta_ups: tuple[float, ...] = (0.02, 0.03, 0.04),
                 theta_dns: tuple[float, ...] = (0.010, 0.015, 0.020, 0.030),
                 tf: int = 3, lookback_min: int = 60, drop_pct: float = 0.04,
                 forward_min: int = 60) -> pd.DataFrame:
    """(theta_up, theta_dn) 전체 그리드를 하루 루프 안에서 계산해 집계한다."""
    rows_df = _build_grid_rows(start, end, theta_ups, theta_dns, tf,
                               lookback_min, drop_pct, forward_min)
    return _aggregate_grid(rows_df)


def analyze_single(start: str, end: str, theta_up: float, theta_dn: float,
                   tf: int = 3, lookback_min: int = 60, drop_pct: float = 0.04,
                   forward_min: int = 60) -> pd.DataFrame:
    """정확히 한 (theta_up, theta_dn) 셀에 대해 analyze_grid 와 동일한 표를 낸다.

    그리드를 받지 않는다 — out-of-sample 검증 실행이 정확히 한 지점만 재현할
    때 쓰는 진입점이다.
    """
    rows_df = _build_grid_rows(start, end, (theta_up,), (theta_dn,), tf,
                               lookback_min, drop_pct, forward_min)
    return _aggregate_grid(rows_df)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20260601")
    ap.add_argument("--end", default="20260630")
    args = ap.parse_args()
    print(analyze_grid(args.start, args.end).to_string(index=False))

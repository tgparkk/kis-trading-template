# scripts/discovery/intraday_rebound/first_touch.py
"""선착 접촉(first-touch, triple-barrier) 분석.

deep-drop 바가 +3%/-3% 를 얼마나 자주 '독립적으로' 건드리는지는 이미 측정됐다
(up 17.76%, down 13.18%, ratio 1.348). 하지만 TP+3%/SL-3% 룰에서는 어느 쪽을
먼저 건드리는지가 손익 전부다 — 이 모듈은 그 순서를 분봉 해상도에서 재구성한다.

이것은 백테스트가 아니고 매매 룰을 만들지 않는다. 파라미터 그리드 백테스트
("멀티버스")를 벌일 가치가 있는지 판단하기 위한 선행 분석일 뿐이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .db import MINUTE_DB, read_sql
from .labeler import LabelParams, compute_labels
from .resample import resample_ohlcv
from .universe import load_frozen_universe

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
    "segment", "n", "pct_up", "pct_down", "pct_ambiguous", "n_ambiguous",
    "pct_none", "mean_terminal_none", "gross_expectancy_pct",
    "gross_expectancy_optimistic_pct", "breakeven_cost_pct",
]


def _filter_regular_session(df: pd.DataFrame) -> pd.DataFrame:
    t = df["datetime"].dt.time
    return df[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]


def first_touch_outcome(bars: pd.DataFrame, close_idx: int, forward_bars: int,
                        theta: float, theta_dn: float | None = None) -> tuple[str, float]:
    """Scan bars close_idx+1 .. close_idx+forward_bars (clipped to the last bar).

    ``theta`` is the up barrier. ``theta_dn`` is the down barrier; it defaults
    to ``theta`` (symmetric barriers, today's behavior) when omitted.

    Returns (outcome, terminal_ret) where outcome is one of:
      "up"        first bar whose high >= entry*(1+theta), and that bar's low
                  stays above entry*(1-theta_dn)
      "down"      first bar whose low <= entry*(1-theta_dn), and that bar's
                  high stays below entry*(1+theta)
      "ambiguous" the first barrier-touching bar touches BOTH barriers within
                  its own high/low
      "none"      neither barrier touched within the window

    terminal_ret = close[end]/entry - 1, always computed (used for the "none"
    bucket). entry = close[close_idx].
    """
    if theta_dn is None:
        theta_dn = theta
    assert bars.index.equals(pd.RangeIndex(len(bars))), \
        "first_touch_outcome expects positional RangeIndex bars"
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)

    n = len(bars)
    entry = float(closes[close_idx])
    end = min(close_idx + forward_bars, n - 1)

    up_target = entry * (1.0 + theta)
    dn_target = entry * (1.0 - theta_dn)

    outcome = "none"
    for j in range(close_idx + 1, end + 1):
        hi = highs[j]
        lo = lows[j]
        up_touch = hi >= up_target
        dn_touch = lo <= dn_target
        if up_touch and dn_touch:
            outcome = "ambiguous"
        elif up_touch:
            outcome = "up"
        elif dn_touch:
            outcome = "down"
        else:
            continue
        break

    terminal_ret = float(closes[end]) / entry - 1.0
    return outcome, terminal_ret


def _aggregate(df: pd.DataFrame, theta: float) -> pd.DataFrame:
    """segment 별 outcome/terminal_ret 원시 행을 집계해 리포트 표를 만든다."""
    records = []
    for segment, g in df.groupby("segment", sort=True):
        n = len(g)

        known = {"up", "down", "ambiguous", "none"}
        unknown = set(g["outcome"]) - known
        assert not unknown, f"unknown outcome labels: {unknown}"

        counts = g["outcome"].value_counts()
        p_up = counts.get("up", 0) / n
        p_down = counts.get("down", 0) / n
        p_amb = counts.get("ambiguous", 0) / n
        p_none = counts.get("none", 0) / n

        none_ret = g.loc[g["outcome"] == "none", "terminal_ret"]
        if len(none_ret) > 0:
            mean_terminal_none = float(none_ret.mean())
            none_term = p_none * mean_terminal_none
        else:
            mean_terminal_none = float("nan")
            none_term = 0.0

        # ambiguous 는 보수적으로 손실로 취급한다.
        gross = p_up * theta - (p_down + p_amb) * theta + none_term
        # ambiguous 를 승리로 취급하면 낙관적 상한이 된다.
        gross_optimistic = (p_up + p_amb) * theta - p_down * theta + none_term

        pct_up = round(p_up * 100, 2)
        pct_down = round(p_down * 100, 2)
        pct_ambiguous = round(p_amb * 100, 2)
        n_ambiguous = int(counts.get("ambiguous", 0))
        # pct_none 은 나머지로 강제한다 — 넷을 독립적으로 반올림하면 합이 100 을
        # 벗어날 수 있다(예: 42.86+28.57+14.29+14.29=100.01).
        pct_none = round(100.0 - pct_up - pct_down - pct_ambiguous, 2)

        gross_expectancy_pct = round(gross * 100, 2)
        gross_expectancy_optimistic_pct = round(gross_optimistic * 100, 2)
        # 손익분기 비용 = gross_expectancy_pct 를 0 으로 만드는 왕복비용.
        # gross 가 양수일 때만 정의된다(그 값과 같다); 아니면 NaN.
        breakeven_cost_pct = (gross_expectancy_pct if gross_expectancy_pct > 0
                              else np.nan)

        records.append({
            "segment": segment,
            "n": n,
            "pct_up": pct_up,
            "pct_down": pct_down,
            "pct_ambiguous": pct_ambiguous,
            "n_ambiguous": n_ambiguous,
            "pct_none": pct_none,
            "mean_terminal_none": round(mean_terminal_none * 100, 2),
            "gross_expectancy_pct": gross_expectancy_pct,
            "gross_expectancy_optimistic_pct": gross_expectancy_optimistic_pct,
            "breakeven_cost_pct": breakeven_cost_pct,
        })

    return pd.DataFrame(records, columns=OUT_COLUMNS)


def analyze(start: str, end: str, tf: int = 3, lookback_min: int = 60,
           drop_pct: float = 0.04, forward_min: int = 60,
           theta: float = 0.03) -> pd.DataFrame:
    """day -> stock(정규장) 루프로 first-touch 순서를 재구성해 segment 별로 집계한다."""
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
    params = LabelParams(timeframe_minutes=tf, lookback_min=lookback_min,
                         drop_pct=drop_pct, forward_min=forward_min, theta=theta)

    rows = []
    for day in days:
        raw = read_sql(_BARS_SQL, (day, codes), MINUTE_DB)
        if raw.empty:
            continue
        raw["datetime"] = pd.to_datetime(raw["datetime"])
        raw = _filter_regular_session(raw)

        for code, g in raw.groupby("stock_code", sort=False):
            bars = resample_ohlcv(g, tf)
            if len(bars) < params.min_lookback_bars + 2:
                continue
            lab = compute_labels(bars, params)
            cand = lab[lab["is_candidate"] & lab["is_valid"] & (lab["forward_bars"] > 0)]
            for idx, row in cand.iterrows():
                outcome, terminal_ret = first_touch_outcome(
                    bars, close_idx=idx, forward_bars=int(row["forward_bars"]),
                    theta=theta)
                segment = "full" if row["is_full_lookback"] else "partial"
                rows.append({
                    "segment": segment,
                    "outcome": outcome,
                    "terminal_ret": terminal_ret,
                })

    all_rows = pd.DataFrame(rows, columns=["segment", "outcome", "terminal_ret"])
    return _aggregate(all_rows, theta)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20260601")
    ap.add_argument("--end", default="20260630")
    args = ap.parse_args()
    print(analyze(args.start, args.end).to_string(index=False))

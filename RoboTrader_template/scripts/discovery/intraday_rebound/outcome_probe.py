# scripts/discovery/intraday_rebound/outcome_probe.py
"""단일 그리드포인트 특징 탐침: 사전-진입 특징이 "먼저 +3%" 대 "먼저 -3%" 를 가르는가.

전체 그리드(20시간 예상)를 돌리기 전에, 고정 그리드포인트
(tf=3, lookback=60분, drop=4%, forward=60분, theta=3%) 하나에서 신호 여부를
먼저 확인한다. 무조건적 급락 진입의 gross expectancy(+0.09%)가 왕복비용(0.21%)을
넘지 못한다는 사실은 이미 알려져 있다 — 남은 질문은 "부분집합"이 다른가이다.

이 모듈은 판단(에지 유무)을 내리지 않는다. 랭킹 표만 만든다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .db import DAILY_DB, MINUTE_DB, read_sql
from .features import FEATURE_NAMES, compute_features
from .first_touch import first_touch_outcome
from .labeler import LabelParams, compute_labels
from .ranking import rank_features
from .resample import resample_ohlcv
from .universe import load_frozen_universe

# 고정 그리드포인트 (스펙에 명시된 값). 전체 그리드 탐색은 별도 작업이다.
TF = 3
LOOKBACK_MIN = 60
DROP_PCT = 0.04
FORWARD_MIN = 60
THETA = 0.03
MIN_DAILY_ROWS = 21

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

# daily_prices.date < 오늘 인 행 중 최근 21개만 (종목별). 전체 이력을 매번
# 끌어오면 21거래일 루프에서 불필요하게 느려진다.
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

REGULAR_OPEN = pd.Timestamp("09:00:00").time()
REGULAR_CLOSE = pd.Timestamp("15:30:00").time()

EVENT_CONTEXT_COLUMNS = [
    "trade_date", "stock_code", "is_full_lookback", "atr14_pct",
    "outcome", "terminal_ret", "hit_up", "hit_down",
]
EVENT_COLUMNS = FEATURE_NAMES + EVENT_CONTEXT_COLUMNS + ["atr_quintile"]


def _filter_regular_session(df: pd.DataFrame) -> pd.DataFrame:
    t = df["datetime"].dt.time
    return df[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]


def _trade_date_to_dash(trade_date: str) -> str:
    """'YYYYMMDD' (minute_candles) -> 'YYYY-MM-DD' (daily_prices)."""
    return f"{trade_date[0:4]}-{trade_date[4:6]}-{trade_date[6:8]}"


def _daily_ctx_for_stock_day(g_daily: pd.DataFrame, day_open: float) -> dict | None:
    """21행(직전 거래일까지) daily_prices 로 스칼라 컨텍스트를 만든다.

    행이 21개 미만이거나 atr14_pct 가 유한하지 않으면 None (스킵 신호).
    """
    if len(g_daily) < MIN_DAILY_ROWS:
        return None

    c = g_daily["close"].to_numpy(dtype=float)
    h = g_daily["high"].to_numpy(dtype=float)
    l = g_daily["low"].to_numpy(dtype=float)

    prev_close = c[-1]
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    atr14 = float(np.mean(tr[-14:]))
    ma20 = float(np.mean(c[-20:]))
    atr14_pct = atr14 / prev_close

    if not np.isfinite(atr14_pct):
        return None

    return {
        "gap_pct": day_open / prev_close - 1.0,
        "ret_5d": prev_close / c[-6] - 1.0,
        "ret_20d": prev_close / c[-21] - 1.0,
        "dev_ma20": prev_close / ma20 - 1.0,
        "atr14_pct": atr14_pct,
        "market_cap": float(g_daily["market_cap"].iloc[-1] or 0.0),
    }


def _assemble_event_row(feature_row: pd.Series, trade_date: str, stock_code: str,
                        is_full_lookback: bool, atr14_pct: float,
                        outcome: str, terminal_ret: float) -> dict:
    """순수 함수 (DB 무관): 후보 봉 1개의 특징행 + 컨텍스트 -> 이벤트 행 dict.

    hit_up/hit_down 은 first-touch outcome 에서 파생한다 (독립 라벨 아님).
    """
    row = dict(feature_row)
    row["trade_date"] = trade_date
    row["stock_code"] = stock_code
    row["is_full_lookback"] = bool(is_full_lookback)
    row["atr14_pct"] = float(atr14_pct)
    row["outcome"] = outcome
    row["terminal_ret"] = float(terminal_ret)
    row["hit_up"] = outcome == "up"
    row["hit_down"] = outcome == "down"
    return row


def _add_atr_quintile(events: pd.DataFrame) -> pd.DataFrame:
    events = events.copy()
    events["atr_quintile"] = pd.qcut(events["atr14_pct"], 5, labels=False,
                                     duplicates="drop")
    return events


def _split_segments(events: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """is_full_lookback 으로 나눈다. 절대 섞지 않는다 (별도 모집단)."""
    full = events[events["is_full_lookback"]].reset_index(drop=True)
    partial = events[~events["is_full_lookback"]].reset_index(drop=True)
    return {"full": full, "partial": partial}


def _summarize(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    pct_up = round(100.0 * df["hit_up"].mean(), 2) if n else float("nan")
    pct_down = round(100.0 * df["hit_down"].mean(), 2) if n else float("nan")
    n_dates = int(df["trade_date"].nunique()) if n else 0
    return pd.DataFrame([{"n": n, "pct_up": pct_up, "pct_down": pct_down,
                          "n_dates": n_dates}])


def _rank_segments(events: pd.DataFrame, n_boot: int = 200,
                   seed: int = 42) -> dict[str, pd.DataFrame]:
    """DB 무관: 완성된 이벤트 표를 받아 세그먼트별 랭킹 + 요약을 낸다."""
    segments = _split_segments(events)
    out: dict[str, pd.DataFrame] = {}
    for name, seg_df in segments.items():
        out[name] = rank_features(seg_df, FEATURE_NAMES, n_boot=n_boot, seed=seed)
        out[f"{name}_summary"] = _summarize(seg_df)
    return out


def build_events(start: str, end: str) -> pd.DataFrame:
    """day -> stock 루프로 후보 봉마다 특징 + first-touch 결과를 모은다."""
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
    params = LabelParams(timeframe_minutes=TF, lookback_min=LOOKBACK_MIN,
                         drop_pct=DROP_PCT, forward_min=FORWARD_MIN, theta=THETA)

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

        # 시장 프록시: 종목별 정규화 수익률의 매 타임스탬프 중앙값. 코드 전체를
        # 리샘플한 뒤 하루 한 번만 계산한다.
        median_ret = pd.concat(norm_returns, axis=1).median(axis=1, skipna=True)

        # 그날 종목별 총 체결대금의 유니버스 내 백분위 순위.
        amount_rank_map = raw.groupby("stock_code")["amount"].sum().rank(pct=True)

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
            ctx["amount_rank"] = float(amount_rank_map.get(code, np.nan))

            lab = compute_labels(bars, params)
            cand = lab[lab["is_candidate"] & lab["is_valid"] & (lab["forward_bars"] > 0)]
            if cand.empty:
                continue

            mret = median_ret.reindex(bars["datetime"]).to_numpy()
            feat = compute_features(bars, lab["prior_high"], ctx, mret,
                                    lookback_bars=params.lookback_bars)

            for idx, lab_row in cand.iterrows():
                outcome, terminal_ret = first_touch_outcome(
                    bars, close_idx=idx, forward_bars=int(lab_row["forward_bars"]),
                    theta=THETA)
                rows.append(_assemble_event_row(
                    feat.loc[idx], trade_date=day, stock_code=code,
                    is_full_lookback=bool(lab_row["is_full_lookback"]),
                    atr14_pct=ctx["atr14_pct"], outcome=outcome,
                    terminal_ret=terminal_ret))

    if not rows:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    events = pd.DataFrame(rows)
    return _add_atr_quintile(events)


def probe(start: str, end: str, n_boot: int = 200, seed: int = 42) -> dict[str, pd.DataFrame]:
    """진입 지점: 이벤트 표를 만들고 세그먼트별로(절대 풀링하지 않고) 랭킹한다."""
    events = build_events(start, end)
    return _rank_segments(events, n_boot=n_boot, seed=seed)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20260601")
    ap.add_argument("--end", default="20260630")
    ap.add_argument("--n-boot", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    result = probe(args.start, args.end, n_boot=args.n_boot, seed=args.seed)
    for seg, df in result.items():
        print("=====", seg, "=====")
        print(df.to_string(index=False))

"""반등 직전 시점의 특징. 시점 t까지의 정보만 사용한다.

모든 rolling/expanding 은 과거 방향이다. shift(-k) 를 쓰면 누수다.
test_time_truncation_no_lookahead 가 이를 기계적으로 강제한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_NAMES = [
    "drop_pct", "drop_over_atr", "drop_speed", "consec_down", "range_expansion",
    "lower_wick_ratio", "body_ratio", "close_pos_in_day",
    "vol_z", "vol_ratio_drop", "log_amount_cum",
    "minutes_since_open",
    "gap_pct", "ret_5d", "ret_20d", "dev_ma20",
    "market_ret", "rel_drop",
]

_EPS = 1e-12


def _safe_div(a, b):
    b = np.where(np.abs(b) < _EPS, np.nan, b)
    return a / b


def _bars_since_prior_high(high: pd.Series, lookback_bars: int) -> pd.Series:
    """직전 lookback_bars 봉 중 최고가가 몇 봉 전이었는지 (자기 봉 제외).

    동률(tie)일 경우 np.argmax/nanargmax 는 가장 오래된(가장 앞쪽) 발생 인덱스를
    반환한다 → "몇 봉 전"이 최대로 계산된다. 의도된 동작이다.
    """
    def _idx(window: np.ndarray) -> float:
        if np.all(np.isnan(window)):
            return np.nan
        masked = np.where(np.isnan(window), -np.inf, window)
        idx = int(np.nanargmax(masked))
        return float(len(window) - idx)

    return high.shift(1).rolling(lookback_bars, min_periods=1).apply(_idx, raw=True)


def _consec_down(close: pd.Series, open_: pd.Series) -> pd.Series:
    # bar 0 은 이전 종가가 없으므로 시가와 비교한다(이음매).
    # bar 1 이후는 직전 종가와 비교한다.
    prev_close = close.shift(1)
    prev_close.iloc[0] = open_.iloc[0]
    bearish = (close < prev_close).to_numpy()
    out = np.zeros(len(bearish))
    run = 0
    for i, b in enumerate(bearish):
        run = run + 1 if b else 0
        out[i] = run
    return pd.Series(out, index=close.index)


def compute_features(bars: pd.DataFrame,
                     prior_high: pd.Series,
                     daily_ctx: dict,
                     market_ret: pd.Series,
                     lookback_bars: int) -> pd.DataFrame:
    b = bars.reset_index(drop=True)
    prior_high = pd.Series(prior_high).reset_index(drop=True)
    market_ret = pd.Series(market_ret).reset_index(drop=True)

    o, h, l, c = b["open"], b["high"], b["low"], b["close"]
    vol, amt = b["volume"], b["amount"]

    rng = (h - l).to_numpy(dtype=float)

    drop_pct = pd.Series(_safe_div(c.to_numpy(dtype=float),
                                   prior_high.to_numpy(dtype=float)) - 1.0)
    atr = float(daily_ctx["atr14_pct"])
    drop_over_atr = drop_pct / atr if abs(atr) > _EPS else pd.Series(np.nan, index=b.index)

    bars_since = _bars_since_prior_high(h, lookback_bars)
    drop_speed = pd.Series(_safe_div(drop_pct.to_numpy(dtype=float),
                                     bars_since.to_numpy(dtype=float)))

    consec_down = _consec_down(c, o)

    avg_range_so_far = pd.Series(rng).expanding(min_periods=1).mean()
    recent_range = pd.Series(rng).rolling(3, min_periods=1).mean()
    range_expansion = pd.Series(_safe_div(recent_range.to_numpy(),
                                          avg_range_so_far.to_numpy()))

    lower_wick_ratio = pd.Series(_safe_div((c - l).to_numpy(dtype=float), rng))
    body_ratio = pd.Series(_safe_div((c - o).abs().to_numpy(dtype=float), rng))

    day_high = h.expanding(min_periods=1).max()
    day_low = l.expanding(min_periods=1).min()
    close_pos_in_day = pd.Series(_safe_div(
        (c - day_low).to_numpy(dtype=float),
        (day_high - day_low).to_numpy(dtype=float),
    ))

    vol_mean = vol.expanding(min_periods=1).mean()
    vol_std = vol.expanding(min_periods=2).std()
    vol_z = pd.Series(_safe_div((vol - vol_mean).to_numpy(dtype=float),
                                vol_std.to_numpy(dtype=float)))

    vol_recent = vol.rolling(3, min_periods=1).mean()
    vol_ratio_drop = pd.Series(_safe_div(vol_recent.to_numpy(), vol_mean.to_numpy()))

    log_amount_cum = np.log1p(amt.cumsum())

    # KRX 정규장 시작(09:00) 기준으로 앵커링한다. 해당 종목의 첫 체결/봉이 아니다.
    # 예: 첫 봉이 09:07 이면 minutes_since_open 은 0 이 아니라 7.0 이다(의도된 동작).
    session_open = b["datetime"].iloc[0].normalize() + pd.Timedelta(hours=9)
    minutes_since_open = (b["datetime"] - session_open).dt.total_seconds() / 60.0

    n = len(b)
    out = pd.DataFrame({
        "drop_pct": drop_pct,
        "drop_over_atr": drop_over_atr,
        "drop_speed": drop_speed,
        "consec_down": consec_down,
        "range_expansion": range_expansion,
        "lower_wick_ratio": lower_wick_ratio,
        "body_ratio": body_ratio,
        "close_pos_in_day": close_pos_in_day,
        "vol_z": vol_z,
        "vol_ratio_drop": vol_ratio_drop,
        "log_amount_cum": log_amount_cum,
        "minutes_since_open": minutes_since_open,
        "gap_pct": np.full(n, daily_ctx["gap_pct"]),
        "ret_5d": np.full(n, daily_ctx["ret_5d"]),
        "ret_20d": np.full(n, daily_ctx["ret_20d"]),
        "dev_ma20": np.full(n, daily_ctx["dev_ma20"]),
        "market_ret": market_ret,
    })
    out["rel_drop"] = out["drop_pct"] - out["market_ret"]
    return out[FEATURE_NAMES]

"""봉(bar) 플래그·파생 — 설계서 §3(스키마) · §8-10(한국 시장 고유 봉 3종).

🔴 **재현기는 어느 것도 «고치지 않는다» — 표시만 한다.**
🔴 **여기서 만드는 값은 전부 「기준일 D «이하»」 정보다.** 전방 수익률·꼬리 값은 없다.

`flag_cliff` 의 **정본은 `backtest/concept_axes/_defs/flag_cliff.sql`**
(= `FD1` §3-4-b 규약 1-b). 이 모듈은 그 SQL 과 **같은 식**을 pandas 로 옮긴 것이고,
`tests/test_flag_cliff_sql_parity.py` 가 DB 에서 두 결과를 대조한다.
문턱(−18% · 갭 80% · 거래량 2.0×)을 **이 파일에서 고치지 않는다.**
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

# 🔒 `_defs/flag_cliff.sql` 과 «같은» 문턱. 결과를 본 뒤 바꾸지 않는다.
CLIFF_RET_MAX = -0.18       # (1) close_t/close_{t-1} - 1 <= -18%
CLIFF_GAP_FRAC = 0.80       # (2) open/prev-1 <= 0.80 x (close/prev-1)  (양변 음수)
CLIFF_VOL_MULT = 2.0        # (3) volume_t <= 2.0 x mean(volume_{t-20..t-1})
CLIFF_PRIOR_BARS = 20       # 직전 20봉이 «다» 있을 때만 판정

# §8-4 — x5 merge 절벽 잔존 4종목. 고치지 않고 인쇄만 한다.
MERGE_SUSPECT_CODES = frozenset({"196450", "297570", "332290", "083640"})

RET_5D_LAG = 5


def _one_stock(g: pd.DataFrame) -> pd.DataFrame:
    """한 종목의 오름차순 일봉에 플래그를 붙인다. `volume` 은 이미 adj 적용값."""
    close = g["close"].astype(float)
    open_ = g["open"].astype(float)
    high = g["high"].astype(float)
    low = g["low"].astype(float)
    vol = g["volume"].astype(float)
    adj = (g["adj_factor"].astype(float) if "adj_factor" in g.columns
           else pd.Series(1.0, index=g.index)).fillna(1.0)

    # §8-10 1·2 — 잠김봉 / 패딩봉 (OHLC 4값 동일 · volume 으로 가른다)
    flat = (open_ == high) & (high == low) & (low == close)
    flag_locked_limit = flat & (vol > 0)
    flag_padding = flat & (vol <= 0)

    # ── flag_cliff — `_defs/flag_cliff.sql` 과 같은 식 ──────────────────────
    prev_close = close.shift(1)
    # SQL: COUNT(*) OVER (ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) = 행 수
    n_prior = pd.Series(np.minimum(np.arange(len(g)), CLIFF_PRIOR_BARS), index=g.index)
    vol_ma20_prior = vol.shift(1).rolling(CLIFF_PRIOR_BARS,
                                         min_periods=CLIFF_PRIOR_BARS).mean()
    # SQL: MIN/MAX(COALESCE(adj_factor,1)) OVER (ROWS BETWEEN 20 PRECEDING AND CURRENT ROW)
    w21 = CLIFF_PRIOR_BARS + 1
    adj_min21 = adj.rolling(w21, min_periods=1).min()
    adj_max21 = adj.rolling(w21, min_periods=1).max()

    prev_ok = prev_close.notna() & (prev_close > 0)
    ret_close = close / prev_close - 1.0
    gap = open_ / prev_close - 1.0

    adj_flat = adj_min21 == adj_max21
    judgeable = prev_ok & (n_prior == CLIFF_PRIOR_BARS) & adj_flat
    # NULLIF(vol_ma20_prior,0) — 0 이면 SQL 이 NULL 이라 조건이 성립하지 않는다.
    vol_ok = (vol_ma20_prior > 0) & (vol <= CLIFF_VOL_MULT * vol_ma20_prior)

    flag_cliff = (judgeable
                  & (ret_close <= CLIFF_RET_MAX)
                  & (gap <= CLIFF_GAP_FRAC * ret_close)
                  & vol_ok).fillna(False)

    # 「없다」와 「모른다」를 가른다(§8-10-b · FD1 §3-4-b 규약 2·3).
    cliff_unknown_nprior = prev_ok & (n_prior < CLIFF_PRIOR_BARS)
    cliff_unknown_adjstep = prev_ok & (n_prior == CLIFF_PRIOR_BARS) & (~adj_flat)

    out = pd.DataFrame({
        "flag_locked_limit": flag_locked_limit.fillna(False).to_numpy(),
        "flag_padding": flag_padding.fillna(False).to_numpy(),
        "flag_cliff": flag_cliff.to_numpy(),
        "cliff_unknown_nprior": cliff_unknown_nprior.fillna(False).to_numpy(),
        "cliff_unknown_adjstep": cliff_unknown_adjstep.fillna(False).to_numpy(),
        "ret_1d": ret_close.to_numpy(),
        "gap_open": gap.to_numpy(),
        "ret_5d": (close / close.shift(RET_5D_LAG) - 1.0).to_numpy(),
        "adj_step_in_window": (~adj_flat).fillna(False).to_numpy(),
    }, index=g.index)
    return out


def compute_bar_flags(px: pd.DataFrame) -> pd.DataFrame:
    """종목별로 플래그를 붙인 프레임을 돌려준다(입력 행 순서·인덱스 보존).

    입력은 `(stock_code, date)` 오름차순이어야 한다(로더가 보장).
    """
    if px.empty:
        cols = ["flag_locked_limit", "flag_padding", "flag_cliff",
                "cliff_unknown_nprior", "cliff_unknown_adjstep",
                "ret_1d", "gap_open", "ret_5d", "adj_step_in_window"]
        return pd.DataFrame({c: pd.Series(dtype="float64") for c in cols})
    parts = [_one_stock(g) for _, g in px.groupby("stock_code", sort=False)]
    out = pd.concat(parts).reindex(px.index)
    for c in ("flag_locked_limit", "flag_padding", "flag_cliff",
              "cliff_unknown_nprior", "cliff_unknown_adjstep", "adj_step_in_window"):
        out[c] = out[c].astype(bool)
    return out


def is_merge_suspect(code: str) -> bool:
    """§8-4 — x5 merge 절벽 4종목. **고치지 않고 표시만 한다.**"""
    return code in MERGE_SUSPECT_CODES


def flag_counts_by_year(px: pd.DataFrame, fl: pd.DataFrame) -> pd.DataFrame:
    """V6-5 — 패딩·잠김·절벽을 **연도별 «거래일당»** 으로 인쇄하기 위한 집계."""
    year = pd.to_datetime(px["date"]).dt.year
    n_days = px.groupby(year)["date"].nunique()
    agg = pd.DataFrame({
        "n_padding": fl["flag_padding"].groupby(year).sum(),
        "n_locked_limit": fl["flag_locked_limit"].groupby(year).sum(),
        "n_cliff": fl["flag_cliff"].groupby(year).sum(),
        "n_cliff_unknown_nprior": fl["cliff_unknown_nprior"].groupby(year).sum(),
        "n_cliff_unknown_adjstep": fl["cliff_unknown_adjstep"].groupby(year).sum(),
        "n_trading_days": n_days,
    })
    agg["padding_per_day"] = agg["n_padding"] / agg["n_trading_days"]
    return agg


def preferred_month_counts(px: pd.DataFrame) -> pd.DataFrame:
    """V6-4 — 우선주 종목-일 수를 **월별** 인쇄.

    🔑 V6 문안의 `right(stock_code,1) <> '0'` 은 **거친 진단식**이다. 배제 규칙의
    정본은 §1-2-b 1(6번째 자리 `[5-9]`∨`[K-M]`)이고, 두 식이 갈리는 종목 수를 함께 센다.
    """
    from backtest.concept_axes.replayer.loader import is_preferred
    code = px["stock_code"].astype(str)
    month = pd.to_datetime(px["date"]).dt.to_period("M").astype(str)
    canon = code.map(is_preferred)
    rough = code.str[-1] != "0"
    return pd.DataFrame({
        "n_pref_canonical": canon.groupby(month).sum(),
        "n_pref_rough": rough.groupby(month).sum(),
        "n_disagree": (canon != rough).groupby(month).sum(),
    })

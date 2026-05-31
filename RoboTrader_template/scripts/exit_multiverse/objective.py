"""목적함수: 국면별 Sharpe 분해 → 국면최악 → DSR."""
from __future__ import annotations
import math
from typing import Dict
import numpy as np
import pandas as pd

from backtest.regime_analysis import MarketRegime
from multiverse.runner.dsr import deflated_sharpe_ratio

_ANNUAL = math.sqrt(252)


def _sharpe(rets: np.ndarray) -> float:
    rets = rets[np.isfinite(rets)]
    if len(rets) < 2 or rets.std() == 0:
        return 0.0
    return float(rets.mean() / rets.std() * _ANNUAL)


def regime_sharpes(daily_returns: pd.Series, regime_series: pd.Series,
                   min_obs: int = 20) -> Dict[str, float]:
    """일별 수익률을 그날의 국면 라벨로 분류해 국면별 연환산 Sharpe.

    min_obs 미만 표본 국면은 worst 계산에서 제외하되 값은 보고(신뢰 부족 표기는 report 책임).
    'worst' = min(표본 충분한 국면 Sharpe). 충분한 국면이 없으면 0.0.
    반환 dict: BULL, BEAR, SIDEWAYS, worst, _counts.
    """
    reg_map = {pd.Timestamp(str(k)[:10]): (v.value.upper() if isinstance(v, MarketRegime) else "SIDEWAYS")
               for k, v in regime_series.items()}
    out: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for label in ("BULL", "BEAR", "SIDEWAYS"):
        mask = daily_returns.index.map(lambda d: reg_map.get(pd.Timestamp(str(d)[:10])) == label)
        vals = daily_returns[np.asarray(mask, dtype=bool)].to_numpy()
        out[label] = _sharpe(vals)
        counts[label] = len(vals)
    eligible = [out[l] for l in ("BULL", "BEAR", "SIDEWAYS") if counts[l] >= min_obs]
    out["worst"] = float(min(eligible)) if eligible else 0.0
    out["_counts"] = counts
    return out


def compute_dsr(daily_returns: pd.Series, n_trials: int) -> float:
    """전체 일별수익률 기준 DSR. n_trials=그리드 조합 수."""
    rets = daily_returns.to_numpy()
    rets = rets[np.isfinite(rets)]
    if len(rets) < 2:
        return 0.0
    sharpe = _sharpe(rets)
    from scipy.stats import skew as _skew, kurtosis as _kurt
    sk = float(_skew(rets)) if len(rets) > 2 else 0.0
    ek = float(_kurt(rets, fisher=True)) if len(rets) > 3 else 0.0
    return deflated_sharpe_ratio(sharpe=sharpe, n_trials=n_trials,
                                 n_observations=len(rets), skew=sk, excess_kurt=ek)

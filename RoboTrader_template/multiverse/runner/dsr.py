"""Deflated Sharpe Ratio (López de Prado 2014).

다중비교 보정 후 Sharpe의 통계적 유의성을 0~1 확률로 반환.
>= 0.95면 1급 후보 자격 (보수적 95% 신뢰).
"""
from __future__ import annotations

import math

from scipy.stats import norm  # type: ignore


def deflated_sharpe_ratio(
    sharpe: float,
    n_trials: int,
    n_observations: int,
    skew: float = 0.0,
    excess_kurt: float = 0.0,
) -> float:
    """DSR — 다중비교 보정 후 Sharpe.

    Parameters
    ----------
    sharpe:
        관측된 Sharpe Ratio (연환산).
    n_trials:
        시도한 파라미터 조합 수 (그리드 셀 수).
    n_observations:
        수익률 관측 수 (거래일 수 T).
    skew:
        수익률 왜도 (return_skew).
    excess_kurt:
        수익률 초과첨도 (return_kurt, 정규분포=0).

    Returns
    -------
    float
        0~1. >= 0.95면 통과.

    Notes
    -----
    공식 (López de Prado 2014):
      SR_expected = (1 - γ + γ * Φ⁻¹(1 - 1/N)) * sqrt(2 * ln(N))
        γ = Euler-Mascheroni constant ≈ 0.5772156649
      DSR = Φ((SR - SR_expected) * sqrt(T-1) /
                sqrt(1 - skew*SR + (kurt-1)/4 * SR²))
        T = n_observations
    """
    if n_trials <= 1:
        return 1.0  # 비교군 없으면 보정 불필요

    if n_observations < 2:
        return 0.0

    GAMMA = 0.5772156649015329

    sr_expected = (
        (1 - GAMMA + GAMMA * norm.ppf(1 - 1 / n_trials))
        * math.sqrt(2 * math.log(n_trials))
    )

    denom = 1 - skew * sharpe + ((excess_kurt + 1) / 4) * (sharpe ** 2)
    if denom <= 0:
        return 0.0

    z = (sharpe - sr_expected) * math.sqrt(n_observations - 1) / math.sqrt(denom)
    return float(norm.cdf(z))


def passes_dsr(dsr: float, threshold: float = 0.95) -> bool:
    """DSR 통과 여부 (1급 후보 자격).

    Parameters
    ----------
    dsr:
        deflated_sharpe_ratio() 반환값.
    threshold:
        통과 기준 (기본 0.95).
    """
    return dsr >= threshold

"""
Backtest Metrics
================

성과 지표(MDD/샤프/칼마/소르티노) 순수 계산 함수. `backtest/engine.py`에서 분리
(2026-07-02 Phase2 god-file split). 원래는 `BacktestEngine`의 static 메서드였으며
(`_calc_mdd` 등), 이름의 선행 언더스코어만 제거해 모듈 함수로 이동했습니다(본문 verbatim).
`backtest/engine.py`는 하위호환을 위해 `_calc_mdd = staticmethod(metrics.calc_mdd)` 형태의
별칭을 클래스 내부에 유지합니다.
"""

from __future__ import annotations

from typing import List

import numpy as np


def calc_mdd(equity_curve: List[float]) -> float:
    """최대 낙폭(MDD) 계산. 양수로 반환 (예: 0.15 = 15% 낙폭)."""
    if len(equity_curve) < 2:
        return 0.0
    arr = np.array(equity_curve, dtype=float)
    peak = np.maximum.accumulate(arr)
    drawdowns = (peak - arr) / peak
    return float(np.max(drawdowns))


def calc_sharpe(equity_curve: List[float], risk_free_rate: float = 0.0) -> float:
    """일별 수익률 기반 샤프 비율 계산 (연율화, 무위험수익률 기본 0%)."""
    if len(equity_curve) < 2:
        return 0.0
    arr = np.array(equity_curve, dtype=float)
    daily_returns = np.diff(arr) / arr[:-1]
    excess = daily_returns - risk_free_rate / 252
    if excess.std() == 0:
        return 0.0
    return float(excess.mean() / excess.std() * np.sqrt(252))


def calc_calmar(total_return: float, mdd: float, n_days: int) -> float:
    """칼마 비율 계산 (연환산 수익률 / MDD).

    Args:
        total_return: 누적 수익률 (예: 0.12 = +12%).
        mdd: 최대 낙폭 (양수, 예: 0.15 = 15%).
        n_days: 백테스트 일수 (연율화 기준).

    Returns:
        CAGR / MDD. MDD가 0이면 0 반환.
    """
    if mdd <= 0 or n_days <= 0:
        return 0.0
    years = n_days / 252.0
    # 복리 연환산: (1 + total_return)^(1/years) - 1
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0
    return float(cagr / mdd)


def calc_sortino(equity_curve: List[float], risk_free_rate: float = 0.0) -> float:
    """소르티노 비율 계산 (하방 편차 기반, 연율화, 무위험률 기본 0%).

    하방 편차 = 음수 초과 수익률의 표준편차.
    """
    if len(equity_curve) < 2:
        return 0.0
    arr = np.array(equity_curve, dtype=float)
    daily_returns = np.diff(arr) / arr[:-1]
    excess = daily_returns - risk_free_rate / 252
    downside = excess[excess < 0]
    if len(downside) == 0:
        # 손실 일자 없으면 무한대 → 실용상 큰 값 반환
        return float(excess.mean() * np.sqrt(252)) if excess.mean() > 0 else 0.0
    downside_std = float(np.std(downside))
    if downside_std == 0:
        return 0.0
    return float(excess.mean() / downside_std * np.sqrt(252))

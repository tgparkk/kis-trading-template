"""동적 손익비 멀티버스 오케스트레이터 (측정 전용).

전략별: 베이스라인(고정) + 동적 그리드 셀 → run_portfolio → metrics → ΔSharpe.
OOS 게이트/train-test 는 Task 7 에서 추가.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from scripts.exit_multiverse.portfolio_sim import run_portfolio
from scripts.book_portfolio_multiverse import _SLTPMHAdapter
from scripts.book_param_multiverse import _daily_metrics

_INITIAL = 10_000_000


def build_grid() -> List[dict]:
    """베이스라인 포함 전체 그리드 셀 목록을 반환한다."""
    cells: List[dict] = [{"ref_type": "fixed"}]
    for ref in ("box", "atr", "bollinger"):
        for n in (10, 20):
            for sl_mult in (1.0, 1.5, 2.0):
                for rr in (1.0, 1.5, 2.0, 3.0):
                    cells.append(
                        {"ref_type": ref, "n": n, "sl_mult": sl_mult,
                         "rr": rr, "buffer": 0.0, "bb_k": 2.0}
                    )
    return cells


GRID = build_grid()


def _make_turnover(signals: Dict[str, list]) -> Dict[str, float]:
    """signals 딕셔너리의 종목코드로 uniform turnover 맵을 만든다."""
    return {code: 1.0 for code in signals}


def _metrics_for(
    data: Dict[str, pd.DataFrame],
    signals: Dict[str, list],
    base_params: dict,
    dyn: Optional[dict],
    max_positions: int = 5,
) -> dict:
    """run_portfolio 실행 후 _daily_metrics 로 지표를 계산한다."""
    turnover = _make_turnover(signals)
    res = run_portfolio(
        data, signals, _SLTPMHAdapter(), base_params, turnover,
        max_positions=max_positions, dyn=dyn,
    )
    equity = res["equity_curve"]  # confirmed key
    m = _daily_metrics(_INITIAL, equity, res["trades"])
    sells = [t for t in res["trades"] if t.get("side") == "sell"]
    m["n_trades"] = len(sells)
    m["clamp_frac"] = (
        sum(1 for t in sells if t.get("tp_clamped")) / len(sells)
        if sells else 0.0
    )
    return m


def run_strategy_grid(
    name: str,
    data: Dict[str, pd.DataFrame],
    signals: Dict[str, list],
    base_params: dict,
    grid: Optional[List[dict]] = None,
    max_positions: int = 5,
) -> List[dict]:
    """전략 하나에 대해 그리드 전체를 돌려 ΔSharpe 행 목록을 반환한다.

    Parameters
    ----------
    name:         전략 이름 (행에 기록됨)
    data:         종목코드 → OHLCV DataFrame
    signals:      종목코드 → 진입 바 인덱스 리스트
    base_params:  고정 sl/tp/mh 파라미터 (베이스라인)
    grid:         그리드 셀 목록; None 이면 GRID 전체 사용
    max_positions: 동시 최대 포지션 수
    """
    grid = grid if grid is not None else GRID
    base_m = _metrics_for(data, signals, base_params, dyn=None,
                          max_positions=max_positions)
    base_sharpe = float(base_m.get("sharpe", 0.0))  # confirmed key: "sharpe"

    rows: List[dict] = []
    for cell in grid:
        dyn = None if cell.get("ref_type") == "fixed" else cell
        m = _metrics_for(data, signals, base_params, dyn=dyn,
                         max_positions=max_positions)
        cell_sharpe = float(m.get("sharpe", 0.0))
        rows.append({
            "strategy": name,
            **cell,
            "sharpe": cell_sharpe,
            "calmar": float(m.get("calmar", 0.0)),
            "max_dd": float(m.get("max_dd", 0.0)),
            "pnl": float(m.get("pnl", 0.0)),
            "n_trades": int(m.get("n_trades", 0)),
            "clamp_frac": float(m.get("clamp_frac", 0.0)),
            "delta_sharpe": cell_sharpe - base_sharpe,
        })
    return rows

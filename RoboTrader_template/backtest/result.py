"""
Backtest Result
===============

백테스트 결과 요약 데이터클래스. `backtest/engine.py`에서 분리 (2026-07-02 Phase2 god-file split).
`BacktestResult`는 `backtest.engine`에서 verbatim 이동되었으며, `backtest/engine.py`는
`from backtest.result import BacktestResult  # noqa: F401`로 재수출해 기존 참조 표면을 보존합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


# ============================================================================
# 결과 데이터클래스
# ============================================================================

@dataclass
class BacktestResult:
    """백테스트 결과 요약.

    Attributes:
        total_return: 총 수익률 (예: 0.12 = +12%)
        win_rate: 승률 (수익 거래 / 전체 거래)
        avg_profit: 평균 수익률 (거래당)
        max_drawdown: 최대 낙폭 (MDD, 양수: 예 0.15 = -15%)
        sharpe_ratio: 샤프 비율 (무위험 수익률 0% 기준)
        calmar_ratio: 칼마 비율 (연환산 수익률 / MDD). MDD=0이면 0.
        sortino_ratio: 소르티노 비율 (하방 편차 기반, 무위험률 0% 가정).
        profit_loss_ratio: 손익비 (평균 수익 / 평균 손실)
        total_trades: 완료된 왕복 거래 수 (매수→매도 쌍)
        trades: 개별 거래 기록 리스트
        equity_curve: 일별 자산 변화 곡선 (초기 자본 기준)
    """
    total_return: float
    win_rate: float
    avg_profit: float
    max_drawdown: float
    sharpe_ratio: float
    calmar_ratio: float
    sortino_ratio: float
    profit_loss_ratio: float
    total_trades: int
    trades: List[Dict]
    equity_curve: List[float]
    sells_by_reason: Dict[str, int] = field(default_factory=dict)
    candidate_pool_hits: int = 0  # 후보 풀이 적용된 일자 수 (candidate_provider 사용 시)

    def summary(self) -> str:
        """결과 요약 문자열 반환."""
        reason_str = ""
        if self.sells_by_reason:
            parts = [f"{k}={v}" for k, v in sorted(self.sells_by_reason.items())]
            reason_str = f"  매도사유=({','.join(parts)})"
        pool_str = f"  후보풀적용={self.candidate_pool_hits}일" if self.candidate_pool_hits > 0 else ""
        return (
            f"총수익률={self.total_return:+.2%}  "
            f"승률={self.win_rate:.1%}  "
            f"평균수익={self.avg_profit:+.2%}  "
            f"MDD={self.max_drawdown:.2%}  "
            f"샤프={self.sharpe_ratio:.2f}  "
            f"칼마={self.calmar_ratio:.2f}  "
            f"소르티노={self.sortino_ratio:.2f}  "
            f"손익비={self.profit_loss_ratio:.2f}  "
            f"거래={self.total_trades}건"
            f"{reason_str}"
            f"{pool_str}"
        )

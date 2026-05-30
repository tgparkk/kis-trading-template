"""평균모멘텀스코어(Average Momentum Score) 비중 산출.

월말 종가 시계열 P[m] 에 대해:
    score[m] = (1/12) * Σ_{k=1..12} 1[ P[m] >= P[m-k] ]     # 0 ~ 1 연속
    w_risk[m] = score[m]      (위험자산 목표비중)
    w_safe[m] = 1 - score[m]  (안전자산=현금)

워밍업: 최소 12개월 히스토리 필요(첫 12개월은 score 미산출).
no-lookahead: score[m] 은 P[m], P[m-1] ... P[m-12] 만 사용(미래 종가 불참조).
백테스터가 w[m] 을 m→m+1 수익에 적용하여 시점규약을 강제한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class AvgMomentumScoreStrategy:
    """평균모멘텀스코어 비중 산출기.

    lookback_months: 평균낼 모멘텀 룩백 개수(systrader79 기본 12).
    """

    lookback_months: int = 12

    def momentum_score(self, monthly_close: pd.Series) -> pd.Series:
        """월말 종가 시계열 → 평균모멘텀스코어(0~1) 시계열.

        앞 lookback_months 개 월은 NaN(워밍업, 히스토리 부족).
        index 는 입력 그대로(월말 Timestamp).
        """
        s = monthly_close.sort_index()
        n = len(s)
        L = self.lookback_months
        scores = pd.Series(np.nan, index=s.index, dtype=float)
        vals = s.values
        for m in range(L, n):
            cur = vals[m]
            hits = 0
            for k in range(1, L + 1):
                if cur >= vals[m - k]:
                    hits += 1
            scores.iloc[m] = hits / L
        return scores

    def risk_weights(self, monthly_close: pd.Series) -> pd.Series:
        """위험자산 목표비중 = 평균모멘텀스코어 (NaN 워밍업 구간 제거).

        반환: index=월말 Timestamp, value=w_risk(0~1). 워밍업 월은 제외.
        """
        scores = self.momentum_score(monthly_close)
        return scores.dropna()

"""systrader79 — 평균모멘텀스코어 동적 자산배분.

위험자산(KOSPI)의 1~12개월 시계열 모멘텀을 평균낸 0~1 스코어를
그대로 위험자산 목표비중으로 사용(나머지는 현금). 월간 리밸런싱.
"""

from .strategy import AvgMomentumScoreStrategy

__all__ = ["AvgMomentumScoreStrategy"]

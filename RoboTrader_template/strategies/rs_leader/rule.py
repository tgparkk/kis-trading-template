"""RS 리더 진입룰 — 절대 상승추세 (per-stock, no-lookahead).

선정 룰(스펙 §3-2 절대 상승추세 + 2026-08-22 진입/청산 교집합 수정):
  종가 > MA(ma_short) AND 종가 > MA(ma_long) AND MA(ma_short) > MA(ma_long)
  AND abs_lb일 수익률 > 0.
횡단면 RS 랭크는 이 룰이 아니라 apply_entry_filter(filt="rs_rank") 가 담당한다.

no-lookahead: generate_signal 은 호출자가 넘긴 window(=df.iloc[:i+1]) 만 본다.
rolling 은 전부 trailing(center 미사용)이라 미래 봉 무관.

⚠️ 진입 조건에 `종가 > MA(ma_short)`(2026-08-22 추가): 청산 ma_break(strategy.py
evaluate_sell_conditions)가 "종가 < MA(ma_short 과 동일 기간의 trail_ma)"를 무조건
발동시키는데, 이 조건이 없으면 진입은 MA(ma_long) 만 넘으면 됐다 — 즉 진입 영역
(종가 > MA(ma_long)) 과 청산 영역(종가 < MA(ma_short))의 교집합
(MA(ma_long) < 종가 < MA(ma_short), MA(ma_short) > MA(ma_long) 조건상 이 구간은
원리적으로 항상 비어있지 않다)이 매수 직후 매도(whipsaw)를 만들었다. 실측(2026-08-22):
후보풀의 26.5%, 라이브 매수 71건 중 17건(23.94%)이 이 겹침 상태였고 마스킹 결함이
걷힌 뒤로는 2/2 = 100% 가 1초 만에 왕복 체결됐다. 전문가 3인 검토 결정.
이 룰은 screener.py 가 재사용(단일 소스)하므로 스크리너 후보풀도 함께 좁아진다
(의도된 동작) — 실측: 후보풀 404.3→295.0/일, top10 평균 120일수익 +742.8%→+659.8%,
top10 의 풀 내 백분위 2.99%→4.61%.
"""
from __future__ import annotations

import pandas as pd

from strategies.base import Signal, SignalType


class RSLeaderRule:
    name = "rs_leader"

    def __init__(self, ma_short: int = 20, ma_long: int = 60, abs_lb: int = 60):
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.abs_lb = abs_lb

    def generate_signal(self, stock_code: str, df: pd.DataFrame, timeframe: str = "daily"):
        if df is None or len(df) < self.ma_long + 1 or len(df) <= self.abs_lb:
            return None
        close = df["close"].astype(float)
        ma_s = close.rolling(self.ma_short, min_periods=self.ma_short).mean().iloc[-1]
        ma_l = close.rolling(self.ma_long, min_periods=self.ma_long).mean().iloc[-1]
        if pd.isna(ma_s) or pd.isna(ma_l):
            return None
        c = float(close.iloc[-1])
        ref = float(close.iloc[-1 - self.abs_lb])
        if ref <= 0:
            return None
        ret = c / ref - 1.0
        # c > ma_s(2026-08-22 추가): 청산 ma_break 가 "종가 < MA(ma_short)"를 무조건
        # 발동시키므로, 이 조건이 없으면 진입영역(종가>MA(ma_long))과 청산영역이
        # 항상 겹친다 — 모듈 docstring 참조.
        if c > ma_s and c > ma_l and ma_s > ma_l and ret > 0:
            return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60)
        return None

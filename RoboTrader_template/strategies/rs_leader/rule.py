"""RS 리더 진입룰 — 절대 상승추세 (per-stock, no-lookahead).

선정 룰(스펙 §3-2 절대 상승추세):
  종가 > MA(ma_long) AND MA(ma_short) > MA(ma_long) AND abs_lb일 수익률 > 0.
횡단면 RS 랭크는 이 룰이 아니라 apply_entry_filter(filt="rs_rank") 가 담당한다.

no-lookahead: generate_signal 은 호출자가 넘긴 window(=df.iloc[:i+1]) 만 본다.
rolling 은 전부 trailing(center 미사용)이라 미래 봉 무관.
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
        if c > ma_l and ma_s > ma_l and ret > 0:
            return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60)
        return None

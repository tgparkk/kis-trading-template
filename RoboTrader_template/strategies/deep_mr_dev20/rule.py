"""deep_mr_dev20 진입룰 — MA20 이탈 평균회귀 (scripts/discovery/rules.py 에서 승격).

원 정의: scripts/discovery/rules.py (2026-07-02 Phase1 승격, 동작 무변경).
"""
from __future__ import annotations

import pandas as pd

from strategies.base import Signal, SignalType
from utils.indicators import calculate_rsi


class MeanReversionMA20Rule:
    """④ MA20 이탈 평균회귀 — strategies/mean_reversion 템플릿 verbatim 재활용.

    진입: (close-MA20)/MA20×100 <= entry_deviation_pct AND RSI14 < 30.
    청산: MAReversionExitAdapter (sl7/tp12/MA20×0.9 회복/mh7 — 템플릿 verbatim).

    ⚠️ 아래 `entry_deviation_pct` 기본값은 **-10.0**(템플릿 유래)이지만, 라이브 `deep_mr_dev20` 은
       config.yaml 에서 **-20.0** 으로 오버라이드한다(전략명 "dev20" 이 그 -20 이다). 게이트 검증도
       -20 기준이다 — **코드 기본값만 보고 -10 으로 인용하지 말 것**(감사 2026-08-15).
    """
    name = "mean_reversion_ma20"

    def __init__(self, ma_period: int = 20, entry_deviation_pct: float = -10.0,
                 rsi_period: int = 14, rsi_oversold: float = 30.0,
                 use_rsi_filter: bool = True):
        self.ma_period = ma_period
        self.entry_deviation_pct = entry_deviation_pct
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.use_rsi_filter = use_rsi_filter

    def generate_signal(self, stock_code: str, df: pd.DataFrame, timeframe: str = "daily"):
        need = max(self.ma_period, self.rsi_period) + 10
        if df is None or len(df) < need:
            return None
        close = df["close"].astype(float).iloc[-need:]
        c = float(close.iloc[-1])
        ma = float(close.rolling(self.ma_period, min_periods=self.ma_period).mean().iloc[-1])
        if pd.isna(ma) or ma <= 0:
            return None
        deviation_pct = (c - ma) / ma * 100.0
        if deviation_pct > self.entry_deviation_pct:
            return None
        if self.use_rsi_filter:
            r = float(calculate_rsi(close, self.rsi_period).iloc[-1])
            if pd.isna(r) or r >= self.rsi_oversold:
                return None
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60,
                      reasons=[f"MA{self.ma_period} 이탈 {deviation_pct:.1f}%"])

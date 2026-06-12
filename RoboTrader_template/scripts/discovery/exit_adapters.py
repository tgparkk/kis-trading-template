"""발굴 배치1 청산 어댑터 (run_portfolio 규약: exit_reason(df, i, position, params)).

규약은 scripts/rs_leader/exit_adapter.MA20TrailExitAdapter 와 동일.
판정은 bar i 종가 기준, 체결은 run_portfolio 가 bar i+1 시가로 수행 (no-lookahead).
청산 우선순위는 각 docstring 에 명시 (드라이버 자의 가정 — 출처 사양에 순위 없음).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


def _ret_hold(df: pd.DataFrame, i: int, position: dict):
    entry_price = position["entry_price"]
    cur_close = float(df.iloc[i]["close"])
    return cur_close, (cur_close - entry_price) / entry_price, i - position["entry_idx"]


class CloseAboveMAExitAdapter:
    """Connors RSI-2 청산: 종가 > SMA(ma) 회복 시 청산. 우선순위 sl→tp→ma_recovery→mh.

    출처 사양엔 손익절 없음 → params 의 sl/tp 는 99(무효)로 호출하는 것이 verbatim.
    """
    entry_mechanism = "market"

    def __init__(self, ma: int = 5):
        self.ma = ma

    def exit_reason(self, df: pd.DataFrame, i: int, position: dict, params: dict) -> Optional[str]:
        cur_close, ret, hold_bars = _ret_hold(df, i, position)
        if ret <= -params["stop_loss_pct"]:
            return "stop_loss"
        if ret >= params["take_profit_pct"]:
            return "take_profit"
        if i + 1 >= self.ma:
            sma = float(df["close"].iloc[i - self.ma + 1: i + 1].astype(float).mean())
            if cur_close > sma:
                return "ma_recovery"
        if hold_bars >= params["max_hold_bars"]:
            return "max_hold"
        return None


class MAReversionExitAdapter:
    """mean_reversion 템플릿 청산 verbatim: sl→tp→회복(close>=MA×ratio)→mh."""
    entry_mechanism = "market"

    def __init__(self, ma: int = 20, recovery_ratio: float = 0.9):
        self.ma = ma
        self.recovery_ratio = recovery_ratio

    def exit_reason(self, df: pd.DataFrame, i: int, position: dict, params: dict) -> Optional[str]:
        cur_close, ret, hold_bars = _ret_hold(df, i, position)
        if ret <= -params["stop_loss_pct"]:
            return "stop_loss"
        if ret >= params["take_profit_pct"]:
            return "take_profit"
        if i + 1 >= self.ma:
            ma_val = float(df["close"].iloc[i - self.ma + 1: i + 1].astype(float).mean())
            if cur_close >= ma_val * self.recovery_ratio:
                return "ma_recovery"
        if hold_bars >= params["max_hold_bars"]:
            return "max_hold"
        return None


class BBReversionExitAdapter:
    """bb_reversion 템플릿 청산 verbatim: sl→tp→BB중심(close>=SMA20)→ADX>30→mh."""
    entry_mechanism = "market"

    def __init__(self, bb_period: int = 20, adx_period: int = 14, adx_exit: float = 30.0):
        self.bb_period = bb_period
        self.adx_period = adx_period
        self.adx_exit = adx_exit

    def exit_reason(self, df: pd.DataFrame, i: int, position: dict, params: dict) -> Optional[str]:
        from strategies.bb_reversion.strategy import BBReversionStrategy
        cur_close, ret, hold_bars = _ret_hold(df, i, position)
        if ret <= -params["stop_loss_pct"]:
            return "stop_loss"
        if ret >= params["take_profit_pct"]:
            return "take_profit"
        if i + 1 >= self.bb_period:
            mid = float(df["close"].iloc[i - self.bb_period + 1: i + 1].astype(float).mean())
            if cur_close >= mid:
                return "bb_middle"
        lo = max(0, i + 1 - (self.adx_period + 25))  # EWM 안정화 여유
        tail = df.iloc[lo: i + 1]
        adx = BBReversionStrategy.calculate_adx(
            tail["high"].astype(float), tail["low"].astype(float),
            tail["close"].astype(float), self.adx_period)
        adx_val = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
        if adx_val > self.adx_exit:
            return "adx_breakout"
        if hold_bars >= params["max_hold_bars"]:
            return "max_hold"
        return None

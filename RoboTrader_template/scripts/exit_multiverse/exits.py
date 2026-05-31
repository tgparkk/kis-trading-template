"""청산 판정 순수 함수 — 기존 simulate_one_stock 청산 분기 1:1 이식."""
from __future__ import annotations
from typing import Optional
import pandas as pd
from strategies.books.elder_triple_screen.rules import ema


def exit_reason_simple_ma(df, i, position, stop_loss_pct, take_profit_pct,
                          max_hold_bars, trail_ma) -> Optional[str]:
    """minervini/ma20/ma5 공통 청산. run_haru_silijeon_daily.py:166-181 이식.
    우선순위: stop_loss → take_profit → max_hold → trail_ma. 판정 기준은 bar i 종가."""
    entry_price = position["entry_price"]
    cur_close = float(df.iloc[i]["close"])
    ret = (cur_close - entry_price) / entry_price
    hold_bars = i - position["entry_idx"]
    if ret <= -stop_loss_pct:
        return "stop_loss"
    if ret >= take_profit_pct:
        return "take_profit"
    if hold_bars >= max_hold_bars:
        return "max_hold"
    if trail_ma is not None and i + 1 >= trail_ma:
        ma = df["close"].iloc[i - trail_ma + 1:i + 1].mean()
        if pd.notna(ma) and cur_close < float(ma):
            return "trail_ma"
    return None


def exit_reason_elder(df, i, position, stop_loss_pct, take_profit_pct,
                      max_hold_bars, trail_ema, trend_flip_exit) -> Optional[str]:
    """elder 청산. run_elder_triple_screen.py:145-164 이식.
    우선순위: stop_loss → take_profit → max_hold → trail_ema(수익중&종가<EMA13) → trend_flip(ema65 하락)."""
    entry_price = position["entry_price"]
    cur_close = float(df.iloc[i]["close"])
    ret = (cur_close - entry_price) / entry_price
    hold_bars = i - position["entry_idx"]
    exit_reason = None
    if ret <= -stop_loss_pct:
        exit_reason = "stop_loss"
    elif ret >= take_profit_pct:
        exit_reason = "take_profit"
    elif hold_bars >= max_hold_bars:
        exit_reason = "max_hold"
    elif trail_ema is not None and ret > 0:
        ema_trail = ema(df["close"].iloc[: i + 1].astype(float), trail_ema)
        if cur_close < float(ema_trail.iloc[-1]):
            exit_reason = "trail_ema"
    if exit_reason is None and trend_flip_exit and i >= 5:
        ema65 = ema(df["close"].iloc[: i + 1].astype(float), 65)
        if float(ema65.iloc[-1]) < float(ema65.iloc[-6]):
            exit_reason = "trend_flip"
    return exit_reason

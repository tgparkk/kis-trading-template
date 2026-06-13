"""트레이드 시뮬레이터: baseline(D+1 시가+일봉청산) vs 분봉 타이밍 오버레이. gross/net."""
from __future__ import annotations

from collections import namedtuple
from typing import Callable, Optional

import pandas as pd

Trade = namedtuple("Trade", ["filled", "entry_price", "exit_price", "ret_gross",
                             "ret_net", "hold_days", "mfe", "mae", "exit_reason"])

_UNFILLED = Trade(False, float("nan"), float("nan"), float("nan"), float("nan"),
                  0, float("nan"), float("nan"), "skip")


def _dkey(date) -> str:
    """일봉 date(Timestamp 또는 str)를 intraday_by_date 키(ISO 'YYYY-MM-DD')로 정규화."""
    return pd.Timestamp(date).strftime("%Y-%m-%d")


_EPS = 1e-9  # floating-point tolerance for threshold comparisons


class FixedExitAdapter:
    """고정 청산: sl → tp → max_hold (종가 기준). 돌파/돌파류 baseline."""
    def exit_reason(self, daily: pd.DataFrame, i: int, position: dict, params: dict) -> Optional[str]:
        entry = position["entry_price"]
        ret = float(daily["close"].iloc[i]) / entry - 1.0
        if ret <= -params["stop_loss_pct"] + _EPS:
            return "stop_loss"
        if ret >= params["take_profit_pct"] - _EPS:
            return "take_profit"
        if i - position["entry_idx"] >= params["max_hold_bars"]:
            return "max_hold"
        return None


def simulate_trade(signal_idx: int, daily: pd.DataFrame, intraday_by_date: dict,
                   exit_adapter, exit_params: dict,
                   buy_rule: Optional[Callable], sell_rule: Optional[Callable],
                   buy_params: dict, sell_params: dict, slippage: float) -> Trade:
    e = signal_idx + 1
    if e >= len(daily):
        return _UNFILLED
    d1 = daily.iloc[e]
    baseline_open = float(d1["open"])
    intra_d1 = intraday_by_date.get(_dkey(d1["date"]))

    if buy_rule is not None:
        bp = dict(buy_params)
        bp.setdefault("prev_close", float(daily["close"].iloc[signal_idx]))
        fill = buy_rule(intra_d1, baseline_open, bp)
        if fill is None:
            return _UNFILLED
        entry_price = float(fill.price)
    else:
        entry_price = baseline_open

    # 불량가(0/음수/NaN: 데이터 결함·NaN VWAP 체결) → 체결 불가 처리(ZeroDivision 방지).
    if not (entry_price > 0):
        return _UNFILLED

    position = {"entry_price": entry_price, "entry_idx": e}
    exit_price, reason, hold = None, None, 0
    last = min(e + exit_params["max_hold_bars"], len(daily) - 1)
    mfe, mae = float("-inf"), float("inf")
    for i in range(e, last + 1):
        day = daily.iloc[i]
        mfe = max(mfe, float(day["high"]) / entry_price - 1.0)
        mae = min(mae, float(day["low"]) / entry_price - 1.0)
        intra = intraday_by_date.get(_dkey(day["date"]))
        if sell_rule is not None and intra is not None:
            xi = sell_rule(intra, entry_price, sell_params)
            if xi is not None:
                exit_price, reason, hold = float(xi.price), xi.reason, i - e
                break
        r = exit_adapter.exit_reason(daily, i, position, exit_params)
        if r is not None:
            exit_price, reason, hold = float(day["close"]), r, i - e
            break
    if exit_price is None:
        exit_price, reason, hold = float(daily["close"].iloc[last]), "max_hold", last - e

    ret_gross = exit_price / entry_price - 1.0
    ret_net = (exit_price * (1 - slippage)) / (entry_price * (1 + slippage)) - 1.0
    return Trade(True, entry_price, exit_price, ret_gross, ret_net, hold, mfe, mae, reason)

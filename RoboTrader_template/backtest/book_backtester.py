"""책 전략 전용 백테스트 러너.

기존 backtest/engine.py와 별도로, 책의 Rule 인터페이스에 맞춰 단순화된 시뮬레이터.
신호 발생 봉 다음 봉의 시가에 체결 / EOD 강제 청산 / 수수료·세금·슬리피지 반영.

usage:
    bt = BookBacktester(strategy=AzizDayTradeStrategy(mode="single", target_rule="abcd"))
    result = bt.run_single("005930", minute_df)
    result.pnl_pct, result.sharpe, ...
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from strategies.base import SignalType
from strategies.books._base_book_strategy import BookStrategy


@dataclass
class BookBacktestResult:
    n_trades: int
    pnl_pct: float
    sharpe: float
    calmar: float
    sortino: float
    max_dd_pct: float
    hit_rate: float
    avg_hold_bars: float
    trades: List[Dict[str, Any]] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)


class BookBacktester:
    """단순화된 책 전략 백테스터.

    한 종목의 DataFrame을 받아 신호 발생 봉의 다음 봉 시가에 체결.
    EOD(분봉 마지막 봉) 도달 시 강제 청산.
    """

    def __init__(
        self,
        strategy: BookStrategy,
        initial_capital: float = 1_000_000,
        commission_rate: float = 0.00015,
        tax_rate: float = 0.0018,
        slippage_rate: float = 0.001,
        eod_liquidate: bool = True,
        warmup_bars: int = 20,
        stop_loss_pct: float = 0.02,
        take_profit_pct: float = 0.03,
        max_hold_bars: int = 60,
    ):
        self.strategy = strategy
        self.initial_capital = float(initial_capital)
        self.commission_rate = commission_rate
        self.tax_rate = tax_rate
        self.slippage_rate = slippage_rate
        self.eod_liquidate = eod_liquidate
        self.warmup_bars = warmup_bars
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_hold_bars = max_hold_bars

    def run_single(self, stock_code: str, df: pd.DataFrame) -> BookBacktestResult:
        if df is None or len(df) < self.warmup_bars + 2:
            return _empty_result()

        df = df.reset_index(drop=True).copy()
        n = len(df)
        position: Optional[Dict[str, Any]] = None
        cash = self.initial_capital
        equity_curve: List[float] = []
        trades: List[Dict[str, Any]] = []

        for i in range(self.warmup_bars, n - 1):
            window = df.iloc[: i + 1]
            bar_now = df.iloc[i]
            bar_next = df.iloc[i + 1]

            # 1. 보유 중이면 청산 조건 체크
            if position is not None:
                entry_price = position["entry_price"]
                hold_bars = i - position["entry_idx"]
                cur_close = float(bar_now["close"])
                ret = (cur_close - entry_price) / entry_price
                exit_reason = None
                if ret <= -self.stop_loss_pct:
                    exit_reason = "stop_loss"
                elif ret >= self.take_profit_pct:
                    exit_reason = "take_profit"
                elif hold_bars >= self.max_hold_bars:
                    exit_reason = "max_hold"
                elif self.eod_liquidate and i == n - 2:
                    exit_reason = "eod"
                if exit_reason is not None:
                    fill = float(bar_next["open"]) * (1 - self.slippage_rate)
                    proceeds = position["qty"] * fill
                    fee = proceeds * (self.commission_rate + self.tax_rate)
                    cash += proceeds - fee
                    pnl = (fill - entry_price) / entry_price
                    trades.append({
                        "stock_code": stock_code,
                        "side": "sell",
                        "idx": i + 1,
                        "datetime": str(bar_next.get("datetime", "")),
                        "price": fill,
                        "qty": position["qty"],
                        "reason": exit_reason,
                        "entry_price": entry_price,
                        "pnl_pct": pnl,
                    })
                    position = None
                    equity_curve.append(cash)
                    continue

            # 2. 무포지션이면 신호 평가
            if position is None:
                signal = self.strategy.generate_signal(stock_code, window, timeframe="intraday")
                if signal is not None and signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                    fill = float(bar_next["open"]) * (1 + self.slippage_rate)
                    qty = math.floor((cash * 0.99) / fill)
                    if qty > 0:
                        cost = qty * fill
                        fee = cost * self.commission_rate
                        cash -= cost + fee
                        position = {
                            "entry_idx": i + 1,
                            "entry_price": fill,
                            "qty": qty,
                        }
                        trades.append({
                            "stock_code": stock_code,
                            "side": "buy",
                            "idx": i + 1,
                            "datetime": str(bar_next.get("datetime", "")),
                            "price": fill,
                            "qty": qty,
                            "reason": ", ".join(signal.reasons),
                            "entry_price": fill,
                            "pnl_pct": 0.0,
                        })

            # mark-to-market equity
            mtm = cash
            if position is not None:
                mtm += position["qty"] * float(bar_now["close"])
            equity_curve.append(mtm)

        # 강제 마감 청산
        if position is not None:
            last = df.iloc[-1]
            fill = float(last["close"]) * (1 - self.slippage_rate)
            proceeds = position["qty"] * fill
            fee = proceeds * (self.commission_rate + self.tax_rate)
            cash += proceeds - fee
            entry_price = position["entry_price"]
            trades.append({
                "stock_code": stock_code,
                "side": "sell",
                "idx": n - 1,
                "datetime": str(last.get("datetime", "")),
                "price": fill,
                "qty": position["qty"],
                "reason": "forced_close",
                "entry_price": entry_price,
                "pnl_pct": (fill - entry_price) / entry_price,
            })
            equity_curve.append(cash)
            position = None

        return _compute_metrics(self.initial_capital, equity_curve, trades)


def _empty_result() -> BookBacktestResult:
    return BookBacktestResult(
        n_trades=0, pnl_pct=0.0, sharpe=0.0, calmar=0.0, sortino=0.0,
        max_dd_pct=0.0, hit_rate=0.0, avg_hold_bars=0.0, trades=[], equity_curve=[],
    )


def _compute_metrics(initial: float, equity: List[float], trades: List[Dict[str, Any]]) -> BookBacktestResult:
    if not equity:
        return _empty_result()
    eq = np.array(equity, dtype=float)
    final = eq[-1]
    pnl_pct = (final - initial) / initial

    rets = np.diff(eq) / eq[:-1]
    rets = rets[np.isfinite(rets)]
    if len(rets) > 1 and rets.std() > 0:
        sharpe = float(rets.mean() / rets.std() * math.sqrt(252 * 390))  # 분봉 가정
    else:
        sharpe = 0.0

    downside = rets[rets < 0]
    if len(downside) > 1 and downside.std() > 0:
        sortino = float(rets.mean() / downside.std() * math.sqrt(252 * 390))
    else:
        sortino = 0.0

    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd_pct = float(-dd.min()) if len(dd) else 0.0
    calmar = float(pnl_pct / max_dd_pct) if max_dd_pct > 1e-9 else 0.0

    sell_trades = [t for t in trades if t["side"] == "sell"]
    wins = sum(1 for t in sell_trades if t["pnl_pct"] > 0)
    hit_rate = wins / len(sell_trades) if sell_trades else 0.0

    holds: List[int] = []
    buy_idx: Optional[int] = None
    for t in trades:
        if t["side"] == "buy":
            buy_idx = t["idx"]
        elif t["side"] == "sell" and buy_idx is not None:
            holds.append(t["idx"] - buy_idx)
            buy_idx = None
    avg_hold = float(np.mean(holds)) if holds else 0.0

    return BookBacktestResult(
        n_trades=len(sell_trades),
        pnl_pct=pnl_pct,
        sharpe=sharpe,
        calmar=calmar,
        sortino=sortino,
        max_dd_pct=max_dd_pct,
        hit_rate=hit_rate,
        avg_hold_bars=avg_hold,
        trades=trades,
        equity_curve=list(map(float, eq.tolist())),
    )

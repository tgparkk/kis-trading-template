"""포트폴리오 시뮬레이터 — 자금·슬롯 제약 하에서 4전략 공통 체결.

진입/청산 판정은 어댑터(=기존 rules.py/청산함수)에 위임. 이 파일은 자금관리만.
no-lookahead: 판정은 bar i, 체결은 bar i+1 시가. 비용 상수는 기존 run_*.py 와 동일.
"""
from __future__ import annotations
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from strategies.books.elder_triple_screen.rules import krx_tick, screen1_uptrend

COMMISSION_RATE = 0.00015
TAX_RATE = 0.0018
SLIPPAGE_RATE = 0.001
N_TRAIL = 2  # elder 매수스톱 추적일 (run_elder_triple_screen.py:36)


def _build_master_dates(data: Dict[str, pd.DataFrame]) -> List[pd.Timestamp]:
    s = set()
    for df in data.values():
        s.update(pd.to_datetime(df["datetime"]).tolist())
    return sorted(s)


def run_portfolio(data, signal_cache, adapter, params, turnover,
                  initial_capital=10_000_000, max_positions=5,
                  max_per_stock=3_000_000, unconstrained=False) -> dict:
    """날짜축 포트폴리오 시뮬레이션.

    반환: {equity_curve, daily_returns(pd.Series, index=date), trades,
           max_concurrent_positions, n_trades, n_skipped}
    """
    idx_by_date: Dict[str, Dict[pd.Timestamp, int]] = {}
    for code, df in data.items():
        idx_by_date[code] = {pd.Timestamp(d): k for k, d in enumerate(df["datetime"])}
    signal_set = {code: set(v) for code, v in signal_cache.items()}

    master = _build_master_dates(data)
    cash = initial_capital
    positions: Dict[str, dict] = {}
    pending: Dict[str, dict] = {}
    trades: List[dict] = []
    equity_dates: List[pd.Timestamp] = []
    equity_vals: List[float] = []
    max_concurrent = 0
    n_skipped = 0
    entered_codes: set = set()

    cash_by_code: Dict[str, float] = {code: initial_capital for code in data} if unconstrained else {}

    for d in master:
        # ---- 1) 청산 판정 + 체결 ----
        for code in list(positions.keys()):
            df = data[code]
            i = idx_by_date[code].get(d)
            if i is None or i + 1 >= len(df):
                continue
            reason = adapter.exit_reason(df, i, positions[code], params)
            if reason is not None:
                nxt_open = float(df.iloc[i + 1]["open"])
                if nxt_open <= 0:
                    continue
                fill = nxt_open * (1 - SLIPPAGE_RATE)
                pos = positions.pop(code)
                proceeds = pos["qty"] * fill
                fee = proceeds * (COMMISSION_RATE + TAX_RATE)
                if unconstrained:
                    cash_by_code[code] += proceeds - fee
                else:
                    cash += proceeds - fee
                trades.append({"stock_code": code, "side": "sell",
                               "datetime": str(df.iloc[i + 1]["datetime"]),
                               "entry_price": pos["entry_price"], "price": fill,
                               "qty": pos["qty"], "reason": reason,
                               "pnl_pct": (fill - pos["entry_price"]) / pos["entry_price"],
                               "entry_date": pos["entry_date"]})

        # ---- 2) 진입 후보 수집 ----
        candidates = []
        for code, df in data.items():
            if code in positions:
                continue
            if unconstrained and code in entered_codes:
                continue
            i = idx_by_date[code].get(d)
            if i is None or i + 1 >= len(df):
                continue
            if adapter.entry_mechanism == "market":
                if i in signal_set.get(code, ()):
                    candidates.append((code, i))
            else:
                if i in signal_set.get(code, ()) and code not in pending:
                    pending[code] = {"trigger_high_idx": i, "days_left": N_TRAIL}

        if adapter.entry_mechanism == "stop":
            for code in list(pending.keys()):
                if code in positions:
                    pending.pop(code, None); continue
                df = data[code]; i = idx_by_date[code].get(d)
                if i is None or i + 1 >= len(df):
                    continue
                prior_high = float(df.iloc[pending[code]["trigger_high_idx"]]["high"])
                trigger = prior_high + krx_tick(prior_high)
                nxt_open = float(df.iloc[i + 1]["open"]); nxt_high = float(df.iloc[i + 1]["high"])
                fill = None
                if nxt_open >= trigger:
                    fill = nxt_open * (1 + SLIPPAGE_RATE)
                elif nxt_high >= trigger:
                    fill = trigger * (1 + SLIPPAGE_RATE)
                if fill is not None:
                    candidates.append((code, i, fill))
                else:
                    pending[code]["days_left"] -= 1
                    pending[code]["trigger_high_idx"] = i
                    wclose = df["close"].iloc[: i + 2].astype(float)
                    if pending[code]["days_left"] <= 0 or not screen1_uptrend(wclose):
                        pending.pop(code, None)

        # ---- 3) 우선순위 정렬 후 진입 체결 ----
        candidates.sort(key=lambda c: turnover.get(c[0], 0.0), reverse=True)
        for cand in candidates:
            code, i = cand[0], cand[1]
            df = data[code]
            if not unconstrained and len(positions) >= max_positions:
                n_skipped += 1; continue
            if adapter.entry_mechanism == "stop":
                fill = cand[2]
            else:
                nxt_open = float(df.iloc[i + 1]["open"])
                if nxt_open <= 0:
                    continue
                fill = nxt_open * (1 + SLIPPAGE_RATE)
            avail = cash_by_code[code] if unconstrained else min(cash, max_per_stock)
            qty = int((avail * 0.99) // fill) if fill > 0 else 0
            if qty <= 0:
                n_skipped += 1; continue
            cost = qty * fill; fee = cost * COMMISSION_RATE
            if unconstrained:
                cash_by_code[code] -= cost + fee
            else:
                cash -= cost + fee
            positions[code] = {"entry_idx": i + 1, "entry_price": fill, "qty": qty,
                               "entry_date": str(df.iloc[i + 1]["datetime"])}
            if adapter.entry_mechanism == "stop":
                pending.pop(code, None)
            if unconstrained:
                entered_codes.add(code)
            trades.append({"stock_code": code, "side": "buy",
                           "datetime": str(df.iloc[i + 1]["datetime"]),
                           "entry_price": fill, "price": fill, "qty": qty,
                           "reason": "signal", "pnl_pct": 0.0,
                           "entry_date": str(df.iloc[i + 1]["datetime"])})

        max_concurrent = max(max_concurrent, len(positions))

        # ---- 4) 일별 equity ----
        if unconstrained:
            mtm = sum(cash_by_code.values())
        else:
            mtm = cash
        for code, pos in positions.items():
            i = idx_by_date[code].get(d)
            if i is not None:
                mtm += pos["qty"] * float(data[code].iloc[i]["close"])
        equity_dates.append(d); equity_vals.append(mtm)

    eq = pd.Series(equity_vals, index=pd.to_datetime(equity_dates))
    daily_returns = eq.pct_change().dropna()
    return {"equity_curve": equity_vals, "daily_returns": daily_returns,
            "trades": trades, "max_concurrent_positions": max_concurrent,
            "n_trades": sum(1 for t in trades if t["side"] == "sell"),
            "n_skipped": n_skipped}

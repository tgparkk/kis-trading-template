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
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
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


@dataclass
class UniverseBacktestResult:
    n_stocks: int
    n_trades: int
    pnl_pct: float          # 종목별 PnL의 균등가중 평균
    sharpe: float
    calmar: float
    sortino: float
    max_dd_pct: float
    hit_rate: float
    avg_hold_bars: float
    per_stock: Dict[str, BookBacktestResult] = field(default_factory=dict)


# 청산 기준선 — `concept_axes/ma5_exit/PREREG.md` §2-1 LINE 계열이 쓰는 선 «전부».
# 값 = (종류, 기간). 이 표 밖의 이름은 `BookBacktester.__init__` 이 거부한다.
_EXIT_LINE_SPECS: Dict[str, tuple] = {
    "SMA5": ("sma", 5),
    "SMA10": ("sma", 10),
    "SMA20": ("sma", 20),
    "SMA60": ("sma", 60),
    "EMA13": ("ema", 13),
    "EMA65": ("ema", 65),
}


class BookBacktester:
    """단순화된 책 전략 백테스터.

    한 종목의 DataFrame을 받아 신호 발생 봉의 다음 봉 시가에 체결.
    EOD(분봉 마지막 봉) 도달 시 강제 청산.

    청산 규칙은 선택 파라미터로 확장할 수 있다(`concept_axes/ma5_exit/PREREG.md`).
    **전부 기본값이면 동작은 확장 이전과 완전히 동일하다** — 판정은 확정 봉 종가,
    체결은 다음 봉 시가라는 구조도 그대로다.

    우선순위 (PREREG §2-3 동결분):
        1) disaster_stop   (설정 시 항상 최우선 — 마지노선)
        2) random_exit     (귀무 `R_exit` 전용 arm)
        3) stop_loss → take_profit   (None 이면 각각 비활성)
        4) line_break      (exit_line 설정 시)
        5) max_hold
        6) eod
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
        stop_loss_pct: Optional[float] = 0.02,
        take_profit_pct: Optional[float] = 0.03,
        max_hold_bars: int = 60,
        exit_line: Optional[str] = None,
        disaster_stop_pct: Optional[float] = None,
        random_exit_seed: Optional[int] = None,
        random_exit_max_bars: int = 30,
    ):
        if exit_line is not None and exit_line not in _EXIT_LINE_SPECS:
            raise ValueError(
                f"exit_line must be one of {sorted(_EXIT_LINE_SPECS)}, got {exit_line!r}"
            )
        # 🔴 `random.randint(1, k)` 는 `k < 1` 에서 죽는다 — 가드가 없으면 그 죽음이
        #    «첫 진입 봉»까지 미뤄져 「생성은 됐는데 나중에 터지는」 형태가 된다.
        if int(random_exit_max_bars) < 1:
            raise ValueError(
                f"random_exit_max_bars must be >= 1, got {random_exit_max_bars!r}"
            )
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
        self.exit_line = exit_line
        self.disaster_stop_pct = disaster_stop_pct
        self.random_exit_seed = random_exit_seed
        self.random_exit_max_bars = int(random_exit_max_bars)

    def _exit_line_value(self, window: pd.DataFrame) -> float:
        """확정 봉까지의 `close` 만으로 기준선의 «마지막» 값을 낸다 (룩어헤드 없음).

        `window = df.iloc[: i + 1]` 이므로 i+1 봉 이후는 애초에 보이지 않는다.
        워밍업이 모자라면 `NaN` 이 나오고, 그 처리는 `_is_line_broken` 이 한다.
        """
        kind, span = _EXIT_LINE_SPECS[self.exit_line]
        closes = window["close"].astype(float)
        if kind == "sma":
            line = closes.rolling(span).mean()
        else:
            line = closes.ewm(span=span, adjust=False).mean()
        return float(line.iloc[-1])

    def _is_line_broken(self, window: pd.DataFrame, cur_close: float) -> bool:
        """`close_t < line_t` 면 True. 🔴 선이 `NaN` 이면 «미발동».

        `NaN` 비교가 항상 False 라는 성질에 기대지 않고 명시적으로 가드한다 —
        부등호를 뒤집어 쓰는 순간(`not (close >= line)`) 워밍업 부족 구간이
        전부 청산 신호로 뒤집히기 때문이다.
        """
        line = self._exit_line_value(window)
        if pd.isna(line):
            return False
        return cur_close < line

    def _random_exit_bars(self, stock_code: str, entry_idx: int) -> int:
        """그 포지션의 청산 예정 보유봉수 `k ~ U{1..random_exit_max_bars}`.

        🔴 전역 RNG 를 쓰지 않는다. 키가 `(seed, stock_code, entry_idx)` 뿐이므로
        ***종목 순회 순서가 바뀌어도, 종목을 따로 돌려도 같은 `k`*** 가 나온다.
        재현 게이트의 요건이다.
        """
        rng = random.Random(f"{self.random_exit_seed}|{stock_code}|{entry_idx}")
        return rng.randint(1, self.random_exit_max_bars)

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
                random_bars = position.get("random_exit_bars")
                # PREREG §2-3 동결 우선순위. 새 파라미터가 전부 기본값이면
                # 아래 사슬은 stop_loss → take_profit → max_hold → eod 로 축약된다.
                if self.disaster_stop_pct is not None and ret <= -self.disaster_stop_pct:
                    exit_reason = "disaster_stop"
                elif random_bars is not None and hold_bars >= random_bars:
                    exit_reason = "random_exit"
                elif self.stop_loss_pct is not None and ret <= -self.stop_loss_pct:
                    exit_reason = "stop_loss"
                elif self.take_profit_pct is not None and ret >= self.take_profit_pct:
                    exit_reason = "take_profit"
                elif self.exit_line is not None and self._is_line_broken(window, cur_close):
                    exit_reason = "line_break"
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
                            # 진입 시점에 «그 포지션의» 청산 보유봉수를 뽑아 고정한다.
                            "random_exit_bars": (
                                self._random_exit_bars(stock_code, i + 1)
                                if self.random_exit_seed is not None
                                else None
                            ),
                        }
                        reason_str = ", ".join(signal.reasons) if signal.reasons else (
                            getattr(self.strategy, "target_rule", None) or "signal"
                        )
                        trades.append({
                            "stock_code": stock_code,
                            "side": "buy",
                            "idx": i + 1,
                            "datetime": str(bar_next.get("datetime", "")),
                            "price": fill,
                            "qty": qty,
                            "reason": reason_str,
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

    def run_universe(self, data: Dict[str, pd.DataFrame]) -> UniverseBacktestResult:
        per_stock: Dict[str, BookBacktestResult] = {}
        for code, df in data.items():
            per_stock[code] = self.run_single(code, df)

        n_stocks = len(per_stock)
        if n_stocks == 0:
            return UniverseBacktestResult(
                n_stocks=0, n_trades=0, pnl_pct=0.0, sharpe=0.0, calmar=0.0,
                sortino=0.0, max_dd_pct=0.0, hit_rate=0.0, avg_hold_bars=0.0,
            )

        pnls = np.array([r.pnl_pct for r in per_stock.values()])
        sharpes = np.array([r.sharpe for r in per_stock.values()])
        calmars = np.array([r.calmar for r in per_stock.values()])
        sortinos = np.array([r.sortino for r in per_stock.values()])
        dds = np.array([r.max_dd_pct for r in per_stock.values()])
        hits = np.array([r.hit_rate for r in per_stock.values()])
        holds = np.array([r.avg_hold_bars for r in per_stock.values()])
        trades_total = int(sum(r.n_trades for r in per_stock.values()))

        return UniverseBacktestResult(
            n_stocks=n_stocks,
            n_trades=trades_total,
            pnl_pct=float(pnls.mean()),
            sharpe=float(sharpes.mean()),
            calmar=float(calmars.mean()),
            sortino=float(sortinos.mean()),
            max_dd_pct=float(dds.mean()),
            hit_rate=float(hits.mean()),
            avg_hold_bars=float(holds.mean()),
            per_stock=per_stock,
        )


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


def append_leaderboard(path, row: Dict[str, Any]) -> None:
    """리더보드 parquet에 한 행 append.

    파일이 없으면 새로 생성. 있으면 읽어서 concat 후 저장.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(row)
    row.setdefault("run_at", datetime.utcnow().isoformat())
    new_df = pd.DataFrame([row])
    if path.exists():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_parquet(path, index=False)

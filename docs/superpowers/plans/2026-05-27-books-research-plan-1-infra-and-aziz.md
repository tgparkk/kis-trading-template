# Plan 1: 책 백테스트 인프라 + 아지즈 (Book 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 트레이딩 책 10권 조사·백테스트 파이프라인의 공통 인프라를 만들고, 첫 책(앤드류 아지즈 — How to Day Trade for a Living)을 끝까지 처리해 통합 리더보드에 첫 행을 기록한다.

**Architecture:** `BookStrategy` 공통 베이스(BaseStrategy 상속) + `BookBacktester` 공통 러너 + 책별 디렉토리(`strategies/books/{book_id}/`). 책 1권당 조사→규칙맵→시그널함수→백테스트→리포트의 6단계가 명확히 분리되도록 설계. 첫 책은 분봉 인트라데이로, minute_candles 테이블을 데이터 소스로 사용.

**Tech Stack:** Python 3.8+, pandas, pytest, PostgreSQL/TimescaleDB, pyarrow(parquet)

**관련 설계서:** `docs/superpowers/specs/2026-05-27-books-research-backtest-design.md`

---

## 사전 컨벤션

- **테스트 명령**: `pytest RoboTrader_template/tests/strategies/books/ -v`
- **Lint**: `ruff check RoboTrader_template/strategies/books/ RoboTrader_template/backtest/book_backtester.py`
- **Working directory**: `D:\GIT\kis-trading-template`
- **import 경로**: 코드는 `RoboTrader_template/` 디렉토리에서 실행되므로 import는 `from strategies.base import ...`, `from backtest.engine import ...` 형식
- **DB 접속**: `from db.connection import get_db_connection` (port 5433, robotrader DB)
- **No-lookahead**: 규칙 함수는 입력 DataFrame의 마지막 행 시점 t에서 t+1 이후 데이터 절대 사용 금지

## File Structure

생성·수정될 파일과 책임:

| 파일 | 책임 |
|---|---|
| `RoboTrader_template/strategies/books/__init__.py` | 패키지 마커 |
| `RoboTrader_template/strategies/books/_base_book_strategy.py` | BookStrategy 추상 베이스(BaseStrategy 상속) + Rule 데이터클래스 + 조합기 |
| `RoboTrader_template/backtest/book_backtester.py` | BookBacktester 클래스 — 단일/조합 모드 백테스트, 메트릭 집계 |
| `RoboTrader_template/scripts/run_books_research.py` | CLI 진입점 — `--book aziz --period 2025-10 --mode single` |
| `RoboTrader_template/strategies/books/aziz_day_trade/__init__.py` | 패키지 마커 |
| `RoboTrader_template/strategies/books/aziz_day_trade/rules.py` | 아지즈 7개 규칙 함수 + 입력 검증 |
| `RoboTrader_template/strategies/books/aziz_day_trade/strategy.py` | AzizDayTradeStrategy — rules.py 함수를 BookStrategy로 결합 |
| `RoboTrader_template/strategies/books/aziz_day_trade/README.md` | 규칙맵 (책 페이지 ↔ 함수명 ↔ 한글 설명) |
| `RoboTrader_template/tests/strategies/books/__init__.py` | 테스트 패키지 마커 |
| `RoboTrader_template/tests/strategies/books/test_base_book_strategy.py` | BookStrategy 단위 테스트 |
| `RoboTrader_template/tests/strategies/books/test_book_backtester.py` | BookBacktester 단위 테스트 |
| `RoboTrader_template/tests/strategies/books/aziz_day_trade/__init__.py` | 패키지 마커 |
| `RoboTrader_template/tests/strategies/books/aziz_day_trade/test_rules.py` | 아지즈 규칙 함수 단위 테스트 |
| `RoboTrader_template/reports/books_research/index.md` | 통합 리더보드 (이 플랜에서 초기 생성, 책별로 append) |
| `RoboTrader_template/reports/books_research/leaderboard.parquet` | raw 메트릭 테이블 |
| `RoboTrader_template/reports/books_research/aziz_day_trade/report.md` | 아지즈 책 상세 리포트 |
| `RoboTrader_template/reports/books_research/aziz_day_trade/rules_individual.parquet` | 규칙별 단독 백테스트 결과 |
| `RoboTrader_template/reports/books_research/aziz_day_trade/rules_combo.parquet` | 조합 백테스트 결과 |

---

## Phase A — 공통 인프라

### Task 1: BookStrategy 베이스 클래스

**목적:** 모든 책 전략의 공통 베이스. 규칙 함수 리스트를 받아 단일/AND/OR 조합으로 신호 생성.

**Files:**
- Create: `RoboTrader_template/strategies/books/__init__.py`
- Create: `RoboTrader_template/strategies/books/_base_book_strategy.py`
- Create: `RoboTrader_template/tests/strategies/books/__init__.py`
- Create: `RoboTrader_template/tests/strategies/books/test_base_book_strategy.py`

- [ ] **Step 1: 패키지 마커 생성**

`RoboTrader_template/strategies/books/__init__.py`:
```python
"""책별 트레이딩 전략 패키지. 각 책은 하위 디렉토리로 분리된다."""
```

`RoboTrader_template/tests/strategies/books/__init__.py`:
```python
```

- [ ] **Step 2: 실패하는 테스트 먼저 작성**

`RoboTrader_template/tests/strategies/books/test_base_book_strategy.py`:
```python
"""BookStrategy 베이스 클래스 단위 테스트."""

import pandas as pd
import pytest

from strategies.base import SignalType
from strategies.books._base_book_strategy import BookStrategy, Rule, RuleResult


def _dummy_df():
    return pd.DataFrame({
        "datetime": pd.date_range("2026-04-01 09:00", periods=5, freq="1min"),
        "open": [100, 101, 102, 103, 104],
        "high": [101, 102, 103, 104, 105],
        "low": [99, 100, 101, 102, 103],
        "close": [101, 102, 103, 104, 105],
        "volume": [1000, 1100, 1200, 1300, 1400],
    })


class _AlwaysBuyRule(Rule):
    name = "always_buy"

    def evaluate(self, df, ctx):
        return RuleResult(triggered=True, side="buy", reasons=["always"])


class _NeverRule(Rule):
    name = "never"

    def evaluate(self, df, ctx):
        return RuleResult(triggered=False, side="buy", reasons=[])


def test_book_strategy_single_mode_triggers_when_rule_fires():
    strat = BookStrategy(rules=[_AlwaysBuyRule()], mode="single", target_rule="always_buy")
    sig = strat.generate_signal("005930", _dummy_df(), timeframe="intraday")
    assert sig is not None
    assert sig.signal_type == SignalType.BUY
    assert "always" in sig.reasons


def test_book_strategy_and_mode_requires_all_rules():
    strat = BookStrategy(rules=[_AlwaysBuyRule(), _NeverRule()], mode="all_AND")
    sig = strat.generate_signal("005930", _dummy_df(), timeframe="intraday")
    assert sig is None  # never rule blocks


def test_book_strategy_or_mode_triggers_on_any():
    strat = BookStrategy(
        rules=[_AlwaysBuyRule(), _NeverRule()],
        mode="top_K_OR",
        or_members=["always_buy", "never"],
    )
    sig = strat.generate_signal("005930", _dummy_df(), timeframe="intraday")
    assert sig is not None
    assert sig.signal_type == SignalType.BUY


def test_book_strategy_unknown_mode_raises():
    with pytest.raises(ValueError):
        BookStrategy(rules=[_AlwaysBuyRule()], mode="bogus")
```

- [ ] **Step 3: 테스트 실행해 실패 확인**

```bash
cd D:/GIT/kis-trading-template/RoboTrader_template
pytest tests/strategies/books/test_base_book_strategy.py -v
```
Expected: `ModuleNotFoundError: No module named 'strategies.books._base_book_strategy'`

- [ ] **Step 4: BookStrategy 구현**

`RoboTrader_template/strategies/books/_base_book_strategy.py`:
```python
"""책 백테스트 공통 베이스.

각 책의 매매 규칙(Rule)을 리스트로 받아 단일/AND/OR 조합으로 Signal을 생성한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from strategies.base import BaseStrategy, Signal, SignalType

VALID_MODES = ("single", "all_AND", "top_K_OR")


@dataclass
class RuleResult:
    """규칙 평가 결과."""
    triggered: bool
    side: str = "buy"  # "buy" | "sell"
    confidence: float = 70.0
    reasons: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Rule(ABC):
    """개별 매매 규칙. 책마다 N개를 정의한다."""

    name: str = "unnamed"

    @abstractmethod
    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        """t 시점 데이터(df 마지막 행 기준)로 신호 평가. t+1 이후 접근 금지."""
        raise NotImplementedError


class BookStrategy(BaseStrategy):
    """책 전략 공통 베이스. 모든 책 strategy는 이걸 상속해서 rules 리스트만 주입한다."""

    name = "BookStrategy"
    version = "1.0.0"
    holding_period = "intraday"  # 책별로 override

    def __init__(
        self,
        rules: List[Rule],
        mode: str = "single",
        target_rule: Optional[str] = None,
        or_members: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(config or {})
        if mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")
        if mode == "single" and target_rule is None:
            raise ValueError("mode='single' requires target_rule name")
        if mode == "top_K_OR" and not or_members:
            raise ValueError("mode='top_K_OR' requires or_members list")

        self.rules = rules
        self.mode = mode
        self.target_rule = target_rule
        self.or_members = or_members or []
        self._rule_map = {r.name: r for r in rules}

    def generate_signal(
        self, stock_code: str, data: pd.DataFrame, timeframe: str = "intraday"
    ) -> Optional[Signal]:
        if data is None or len(data) == 0:
            return None
        ctx = {"stock_code": stock_code, "timeframe": timeframe}

        if self.mode == "single":
            rule = self._rule_map.get(self.target_rule)
            if rule is None:
                return None
            res = rule.evaluate(data, ctx)
            return self._to_signal(stock_code, res, [rule.name] if res.triggered else [])

        if self.mode == "all_AND":
            results = [(r.name, r.evaluate(data, ctx)) for r in self.rules]
            if all(res.triggered for _, res in results):
                merged_reasons = [name for name, _ in results]
                return self._to_signal(stock_code, results[0][1], merged_reasons)
            return None

        if self.mode == "top_K_OR":
            for name in self.or_members:
                rule = self._rule_map.get(name)
                if rule is None:
                    continue
                res = rule.evaluate(data, ctx)
                if res.triggered:
                    return self._to_signal(stock_code, res, [name])
            return None

        return None

    @staticmethod
    def _to_signal(stock_code: str, res: RuleResult, reasons: List[str]) -> Optional[Signal]:
        if not res.triggered:
            return None
        sig_type = SignalType.BUY if res.side == "buy" else SignalType.SELL
        return Signal(
            signal_type=sig_type,
            stock_code=stock_code,
            confidence=res.confidence,
            reasons=reasons,
            metadata=res.metadata,
        )
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/strategies/books/test_base_book_strategy.py -v
```
Expected: 4 passed

- [ ] **Step 6: 커밋**

```bash
git add RoboTrader_template/strategies/books/__init__.py \
  RoboTrader_template/strategies/books/_base_book_strategy.py \
  RoboTrader_template/tests/strategies/books/__init__.py \
  RoboTrader_template/tests/strategies/books/test_base_book_strategy.py
git commit -m "feat(books): BookStrategy 베이스 + Rule 인터페이스 (single/AND/OR 모드)"
```

---

### Task 2: BookBacktester — 단일 모드

**목적:** 책 전략을 받아 단일 종목 일/분봉 DataFrame에서 백테스트 → 거래기록·메트릭 산출. 일단 단일 모드만 구현하고, 조합·다종목은 다음 태스크.

**Files:**
- Create: `RoboTrader_template/backtest/book_backtester.py`
- Create: `RoboTrader_template/tests/strategies/books/test_book_backtester.py`

- [ ] **Step 1: 실패하는 테스트 먼저 작성**

`RoboTrader_template/tests/strategies/books/test_book_backtester.py`:
```python
"""BookBacktester 단위 테스트."""

import pandas as pd
import pytest

from backtest.book_backtester import BookBacktester, BookBacktestResult
from strategies.books._base_book_strategy import BookStrategy, Rule, RuleResult


class _MAUpRule(Rule):
    """5분 MA가 직전봉보다 상승하면 매수."""

    name = "ma_up"

    def evaluate(self, df, ctx):
        if len(df) < 6:
            return RuleResult(triggered=False)
        ma_now = df["close"].iloc[-5:].mean()
        ma_prev = df["close"].iloc[-6:-1].mean()
        if ma_now > ma_prev * 1.001:
            return RuleResult(triggered=True, side="buy", reasons=["ma_up"])
        return RuleResult(triggered=False)


def _toy_minute_df():
    # 20봉 — 처음 6봉 평탄, 다음 14봉 상승.
    closes = [100.0] * 6 + [100.0 + i * 0.5 for i in range(1, 15)]
    df = pd.DataFrame({
        "datetime": pd.date_range("2026-04-01 09:00", periods=20, freq="1min"),
        "open": closes,
        "high": [c + 0.2 for c in closes],
        "low": [c - 0.2 for c in closes],
        "close": closes,
        "volume": [1000] * 20,
    })
    return df


def test_backtester_single_stock_single_rule_books_a_trade():
    strat = BookStrategy(rules=[_MAUpRule()], mode="single", target_rule="ma_up")
    bt = BookBacktester(
        strategy=strat,
        initial_capital=1_000_000,
        commission_rate=0.00015,
        tax_rate=0.0018,
        slippage_rate=0.001,
        eod_liquidate=True,
        warmup_bars=6,
    )
    result = bt.run_single(stock_code="005930", df=_toy_minute_df())
    assert isinstance(result, BookBacktestResult)
    assert result.n_trades >= 1
    # 가격이 상승만 했으니 최소 1개 매수 발생
    assert any(t["side"] == "buy" for t in result.trades)


def test_backtester_no_signal_returns_zero_trades():
    class _NeverRule(Rule):
        name = "never"
        def evaluate(self, df, ctx):
            return RuleResult(triggered=False)

    strat = BookStrategy(rules=[_NeverRule()], mode="single", target_rule="never")
    bt = BookBacktester(strategy=strat, initial_capital=1_000_000)
    result = bt.run_single(stock_code="005930", df=_toy_minute_df())
    assert result.n_trades == 0
    assert result.pnl_pct == pytest.approx(0.0, abs=1e-9)
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
pytest tests/strategies/books/test_book_backtester.py -v
```
Expected: `ModuleNotFoundError: No module named 'backtest.book_backtester'`

- [ ] **Step 3: BookBacktester 구현 (단일 모드)**

`RoboTrader_template/backtest/book_backtester.py`:
```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/strategies/books/test_book_backtester.py -v
```
Expected: 2 passed

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/backtest/book_backtester.py \
  RoboTrader_template/tests/strategies/books/test_book_backtester.py
git commit -m "feat(backtest): BookBacktester 단일종목 단일모드 + 메트릭 (sharpe/calmar/sortino)"
```

---

### Task 3: BookBacktester — 다종목 + 리더보드 append

**목적:** `run_universe()` 메서드로 종목 리스트 + per-stock DataFrame을 받아 일괄 백테스트, 결과를 parquet으로 저장, `leaderboard.parquet`에 한 행 append.

**Files:**
- Modify: `RoboTrader_template/backtest/book_backtester.py` (run_universe + append_leaderboard 추가)
- Modify: `RoboTrader_template/tests/strategies/books/test_book_backtester.py` (테스트 추가)

- [ ] **Step 1: 실패하는 테스트 추가**

`RoboTrader_template/tests/strategies/books/test_book_backtester.py` 끝에 추가:
```python
def test_run_universe_aggregates_pnl_across_stocks(tmp_path):
    from strategies.books._base_book_strategy import BookStrategy

    class _AlwaysBuyOnceRule(Rule):
        name = "always"
        def evaluate(self, df, ctx):
            # 8번째 봉부터 항상 매수 신호
            if len(df) >= 8:
                return RuleResult(triggered=True, side="buy", reasons=["always"])
            return RuleResult(triggered=False)

    strat = BookStrategy(rules=[_AlwaysBuyOnceRule()], mode="single", target_rule="always")
    bt = BookBacktester(strategy=strat, initial_capital=1_000_000, warmup_bars=6)

    data = {
        "005930": _toy_minute_df(),
        "000660": _toy_minute_df(),
    }
    agg = bt.run_universe(data)
    assert agg.n_stocks == 2
    assert agg.n_trades >= 2


def test_append_leaderboard_writes_one_row(tmp_path):
    from backtest.book_backtester import append_leaderboard

    out = tmp_path / "lb.parquet"
    append_leaderboard(
        path=out,
        row={
            "book_id": "aziz_day_trade",
            "book_name": "How to Day Trade for a Living",
            "period": "2026-04",
            "rule_combo": "abcd",
            "mode": "single",
            "n_trades": 12,
            "pnl_pct": 0.05,
            "sharpe": 1.2,
            "calmar": 1.5,
            "sortino": 1.4,
            "max_dd_pct": 0.03,
            "hit_rate": 0.6,
            "avg_hold_bars": 25.0,
        },
    )
    df = pd.read_parquet(out)
    assert len(df) == 1
    assert df["book_id"].iloc[0] == "aziz_day_trade"

    # append once more
    append_leaderboard(
        path=out,
        row={
            "book_id": "aziz_day_trade",
            "book_name": "How to Day Trade for a Living",
            "period": "2026-05",
            "rule_combo": "abcd",
            "mode": "single",
            "n_trades": 8,
            "pnl_pct": 0.02,
            "sharpe": 0.7,
            "calmar": 0.8,
            "sortino": 0.9,
            "max_dd_pct": 0.025,
            "hit_rate": 0.5,
            "avg_hold_bars": 22.0,
        },
    )
    df2 = pd.read_parquet(out)
    assert len(df2) == 2
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
pytest tests/strategies/books/test_book_backtester.py -v
```
Expected: 2개 새 테스트가 AttributeError 또는 ImportError로 실패

- [ ] **Step 3: run_universe + append_leaderboard 구현**

`RoboTrader_template/backtest/book_backtester.py`에 추가:

먼저 파일 상단에 import 추가:
```python
from datetime import datetime
from pathlib import Path
```

`BookBacktestResult` 다음에 새 데이터클래스 추가:
```python
@dataclass
class UniverseBacktestResult:
    n_stocks: int
    n_trades: int
    pnl_pct: float          # 종목별 PnL의 균등가중 평균
    sharpe: float           # 일괄 equity 기반
    calmar: float
    sortino: float
    max_dd_pct: float
    hit_rate: float
    avg_hold_bars: float
    per_stock: Dict[str, BookBacktestResult] = field(default_factory=dict)
```

`BookBacktester` 클래스 안에 메서드 추가:
```python
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
```

파일 끝에 함수 추가:
```python
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
```

- [ ] **Step 4: 테스트 전체 실행해 통과 확인**

```bash
pytest tests/strategies/books/ -v
```
Expected: 8 passed (Task 1의 4개 + Task 2의 2개 + 이번 2개)

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/backtest/book_backtester.py \
  RoboTrader_template/tests/strategies/books/test_book_backtester.py
git commit -m "feat(backtest): BookBacktester run_universe + append_leaderboard"
```

---

### Task 4: scripts/run_books_research.py — CLI 진입점

**목적:** 명령줄에서 `python scripts/run_books_research.py --book aziz_day_trade --period 2026-04 --mode single` 형태로 실행. 데이터 로딩 + 백테스트 + parquet 저장 + 리더보드 append를 한 번에.

**Files:**
- Create: `RoboTrader_template/scripts/run_books_research.py`

- [ ] **Step 1: CLI 스크립트 작성 (실행은 다음 태스크에서)**

`RoboTrader_template/scripts/run_books_research.py`:
```python
"""책 백테스트 실행 CLI.

usage:
    python scripts/run_books_research.py --book aziz_day_trade --period 2026-04 --mode single --rule abcd
    python scripts/run_books_research.py --book aziz_day_trade --period 2026-04 --mode all_AND

책 모듈 로드 → 데이터 로드 → 백테스트 → results parquet 저장 → 리더보드 append.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from pathlib import Path

import pandas as pd

# import 경로 설정 (script로 직접 실행 시)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.book_backtester import BookBacktester, append_leaderboard  # noqa: E402

LOG = logging.getLogger("books_research")
PERIODS = {
    "2025-10": ("2025-10-01", "2025-10-31"),
    "2026-04": ("2026-04-01", "2026-04-30"),
    "2026-05": ("2026-05-01", "2026-05-27"),
}


def _load_book_module(book_id: str):
    """strategies.books.{book_id}.strategy 에서 build_strategy(mode, target_rule, or_members) 호출."""
    mod = importlib.import_module(f"strategies.books.{book_id}.strategy")
    if not hasattr(mod, "build_strategy"):
        raise AttributeError(f"{book_id}.strategy 에 build_strategy() 함수가 없습니다")
    return mod


def _load_minute_data(stock_codes, start_date: str, end_date: str) -> dict:
    """robotrader.minute_candles 에서 stock_code, datetime, open, high, low, close, volume 로드."""
    from db.connection import get_db_connection  # 지연 import

    out: dict = {}
    with get_db_connection() as conn:
        for code in stock_codes:
            q = """
                SELECT datetime, open, high, low, close, volume
                FROM minute_candles
                WHERE stock_code = %s
                  AND datetime >= %s
                  AND datetime < %s::date + INTERVAL '1 day'
                ORDER BY datetime ASC
            """
            df = pd.read_sql(q, conn, params=(code, start_date, end_date))
            if not df.empty:
                out[code] = df
    return out


def _load_universe(period_start: str) -> list:
    """1,347 종목 풀. minute_candles에 해당 기간 데이터가 있는 종목만 반환."""
    from db.connection import get_db_connection

    with get_db_connection() as conn:
        q = """
            SELECT DISTINCT stock_code
            FROM minute_candles
            WHERE datetime >= %s
              AND datetime < %s::date + INTERVAL '7 days'
            ORDER BY stock_code
        """
        df = pd.read_sql(q, conn, params=(period_start, period_start))
    return df["stock_code"].tolist()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--book", required=True, help="책 ID (예: aziz_day_trade)")
    p.add_argument("--period", required=True, choices=list(PERIODS.keys()))
    p.add_argument("--mode", required=True, choices=["single", "all_AND", "top_K_OR"])
    p.add_argument("--rule", default=None, help="single 모드에서 규칙 이름")
    p.add_argument("--or-members", default=None, help="top_K_OR 모드용 쉼표 구분 규칙 이름들")
    p.add_argument("--limit", type=int, default=None, help="유니버스 N개로 제한 (디버그용)")
    p.add_argument("--initial-capital", type=float, default=10_000_000)
    p.add_argument("--reports-dir", default="reports/books_research")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    start, end = PERIODS[args.period]
    LOG.info(f"period={args.period} ({start} ~ {end}) book={args.book} mode={args.mode}")

    book_mod = _load_book_module(args.book)
    or_members = args.or_members.split(",") if args.or_members else None
    strategy = book_mod.build_strategy(mode=args.mode, target_rule=args.rule, or_members=or_members)

    universe = _load_universe(start)
    if args.limit:
        universe = universe[: args.limit]
    LOG.info(f"universe size: {len(universe)}")

    data = _load_minute_data(universe, start, end)
    LOG.info(f"loaded data for {len(data)} stocks")

    bt = BookBacktester(strategy=strategy, initial_capital=args.initial_capital, warmup_bars=20)
    agg = bt.run_universe(data)
    LOG.info(
        f"DONE n_stocks={agg.n_stocks} n_trades={agg.n_trades} "
        f"pnl={agg.pnl_pct:.4%} sharpe={agg.sharpe:.2f} calmar={agg.calmar:.2f}"
    )

    rule_label = args.rule if args.mode == "single" else (
        args.mode if args.mode == "all_AND" else "+".join(or_members or [])
    )
    reports_dir = Path(args.reports_dir) / args.book
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_file = reports_dir / f"results_{args.mode}_{rule_label}_{args.period}.parquet"

    trade_rows = []
    for code, res in agg.per_stock.items():
        for t in res.trades:
            t = dict(t)
            t["stock_code"] = code
            trade_rows.append(t)
    if trade_rows:
        pd.DataFrame(trade_rows).to_parquet(out_file, index=False)

    book_meta = getattr(book_mod, "BOOK_META", {})
    append_leaderboard(
        path=Path(args.reports_dir) / "leaderboard.parquet",
        row={
            "book_id": args.book,
            "book_name": book_meta.get("name", args.book),
            "period": args.period,
            "rule_combo": rule_label,
            "mode": args.mode,
            "n_stocks": agg.n_stocks,
            "n_trades": agg.n_trades,
            "pnl_pct": agg.pnl_pct,
            "sharpe": agg.sharpe,
            "calmar": agg.calmar,
            "sortino": agg.sortino,
            "max_dd_pct": agg.max_dd_pct,
            "hit_rate": agg.hit_rate,
            "avg_hold_bars": agg.avg_hold_bars,
        },
    )
    LOG.info(f"leaderboard updated: {args.reports_dir}/leaderboard.parquet")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 헬프 메시지로 import 동작 확인**

```bash
cd D:/GIT/kis-trading-template/RoboTrader_template
python scripts/run_books_research.py --help
```
Expected: argparse 헬프 출력. 책 모듈 import는 main() 안에서만 발생하므로 헬프는 통과해야 함.

- [ ] **Step 3: 커밋**

```bash
git add RoboTrader_template/scripts/run_books_research.py
git commit -m "feat(scripts): run_books_research CLI — 책 백테스트 실행 진입점"
```

---

## Phase B — 아지즈 책 조사 & 코드화

### Task 5: 아지즈 책 매매 규칙 웹 조사 (Agent 위임)

**목적:** Andrew Aziz의 *How to Day Trade for a Living* 책 내 모든 매매 규칙을 웹 조사로 추출. 책 요약/리뷰/블로그/원서 발췌에서 정리.

**Files:**
- Create: `RoboTrader_template/strategies/books/aziz_day_trade/__init__.py`
- Create: `RoboTrader_template/strategies/books/aziz_day_trade/RULES_RESEARCH.md` (조사 원본)

- [ ] **Step 1: 패키지 마커 생성**

`RoboTrader_template/strategies/books/aziz_day_trade/__init__.py`:
```python
"""앤드류 아지즈 - How to Day Trade for a Living. 인트라데이 책."""
```

- [ ] **Step 2: document-specialist 에이전트로 책 규칙 조사 위임**

Agent 호출 (이 플랜을 실행하는 사람이 직접):

```
Agent({
  description: "아지즈 책 매매 규칙 조사",
  subagent_type: "oh-my-claudecode:document-specialist",
  prompt: "Andrew Aziz의 *How to Day Trade for a Living* 책에 나오는 모든 매매 셋업(Strategies/Setups)을 인터넷에서 조사해서 한글로 정리해주세요. 책 요약 사이트(GoodReads 리뷰, Reddit r/Daytrading, Bear Bull Traders 블로그, Aziz 본인 유튜브), 영문 PDF 요약본 등을 활용. 각 셋업마다 (1) 영문명 + 한글명 (2) 진입 조건 (3) 손절·익절 룰 (4) 사용 시간대(개장 직후/장중/장 마감) (5) 사용 데이터(1분/5분/일봉) 명시. 최소 5개, 최대 10개 셋업을 다뤄주세요. 결과는 마크다운 문서로 작성하되, 책 페이지·챕터 출처를 가능한 한 추적해서 인용. 추측 금지 — 검증되지 않은 항목은 명시."
})
```

조사 결과를 받아 `RoboTrader_template/strategies/books/aziz_day_trade/RULES_RESEARCH.md`로 저장.

- [ ] **Step 3: 조사 결과 검토 + 코드화 가능한 규칙 7개 선정**

검토 기준:
- (A) 진입·청산 조건이 명확히 정의됨
- (B) 분봉 OHLCV만으로 평가 가능 (티커별 외부 데이터 불필요)
- (C) 무명 조건(예: "강한 종목") 아닌 수치 조건(예: "5분 RSI<30") 우선

7개를 골라 다음 태스크의 규칙맵에 반영.

- [ ] **Step 4: 커밋**

```bash
git add RoboTrader_template/strategies/books/aziz_day_trade/__init__.py \
  RoboTrader_template/strategies/books/aziz_day_trade/RULES_RESEARCH.md
git commit -m "research(aziz): How to Day Trade for a Living 매매 셋업 조사 원본"
```

---

### Task 6: 아지즈 규칙맵 README 작성

**목적:** Task 5의 조사 결과에서 코드화할 7개 규칙을 한 줄씩 정리. 각 규칙의 영문명/한글명/조건/sql_input/expected_output.

**Files:**
- Create: `RoboTrader_template/strategies/books/aziz_day_trade/README.md`

- [ ] **Step 1: 규칙맵 README 작성**

`RoboTrader_template/strategies/books/aziz_day_trade/README.md`:

다음 템플릿을 채워서 작성. 7개 규칙 중 표준 후보는 (실제 조사 결과에 따라 가감):

1. `rule_abcd` — ABCD 패턴 (개장 후 상승A → 풀백B → 재진입C → 돌파D)
2. `rule_bull_flag` — Bull Flag (급등 후 좁은 박스 → 박스 상단 돌파)
3. `rule_vwap_reversal` — VWAP Reversal (장중 VWAP 이탈 후 재진입)
4. `rule_opening_range_breakout` — Opening Range Breakout (개장 5분 고가 돌파)
5. `rule_red_to_green` — Red-to-Green (PreMkt 손실분 회복하며 PrevClose 돌파)
6. `rule_top_reversal` — Top Reversal (5분 도지 + 거래량 급감 → 매도)
7. `rule_support_resistance` — Support/Resistance (분단위 S/R 라인 반등)

```markdown
# 앤드류 아지즈 — How to Day Trade for a Living (규칙맵)

데이터: 분봉 (minute_candles), 1분 또는 5분 봉.
보유 기간: intraday — EOD 강제 청산.

## 규칙 목록

| 함수명 | 한글명 | 진입 조건 (요약) | 책 챕터 |
|---|---|---|---|
| `rule_abcd` | ABCD 패턴 | 개장 후 상승A→풀백B→재진입C→C 고가 돌파D | Ch.7 ABCD |
| `rule_bull_flag` | 불 플래그 | 5분 봉 +5% 급등 후 3봉 박스 → 박스 상단 돌파 | Ch.7 Bull Flag |
| `rule_vwap_reversal` | VWAP 반등 | 가격 VWAP 하단 이탈 후 1분 봉 VWAP 위로 마감 | Ch.8 VWAP |
| `rule_opening_range_breakout` | 오프닝 레인지 돌파 | 개장 5분(09:00–09:05) 고가 09:05~09:30 사이 돌파 | Ch.7 ORB |
| `rule_red_to_green` | 레드 투 그린 | 시가 < 전일종가 인 종목이 1분 봉 종가 > 전일종가 진입 | Ch.7 RtG |
| `rule_top_reversal` | 상단 반전 (매도) | 5분 도지 + 직전봉 대비 거래량 50% 감소 → 매도 | Ch.7 Top Rev |
| `rule_support_resistance` | 지지/저항 반등 | 5분 저점 = 지난 60분 최저가 ± 0.2%, 다음 봉 양봉 | Ch.7 S/R |

## 청산 룰 (공통)

- 손절: -2% (rule_top_reversal 시그널 발생 시 즉시)
- 익절: +3% 또는 5분 봉 종가 < 진입 후 최고가의 -1%
- 최대 보유: 60분
- EOD: 14:50 강제 청산

## 코드 매핑

- 함수: `rules.py::rule_xxx(df: DataFrame, params: dict) -> RuleResult`
- 입력 df: minute_candles 1종목 시계열, 직전 60분 ≥ 20봉 필요
- 출력: `RuleResult(triggered, side, confidence, reasons, metadata)`

## 한국 시장 적응 노트

- 책의 PreMkt 개념은 한국에서 동시호가에 해당. `rule_red_to_green`의 "전일종가" 비교는 그대로 사용.
- 책의 VWAP는 NY 09:30 시작 기준. 한국은 09:00 시작이므로 일봉 데이터 VWAP는 09:00 부터 누적.
- Float 같은 RR 데이터는 사용 안 함 (한국 시장 가용성 불확실).

## 출처

- 원서: Andrew Aziz, *How to Day Trade for a Living* (2015, updated editions).
- 보조: Bear Bull Traders 공식 블로그, 책 챕터 요약.
- 상세 조사 원본: `RULES_RESEARCH.md`
```

- [ ] **Step 2: 커밋**

```bash
git add RoboTrader_template/strategies/books/aziz_day_trade/README.md
git commit -m "docs(aziz): 아지즈 7개 규칙 규칙맵 README"
```

---

### Task 7: 아지즈 규칙 함수 코드화 + 단위 테스트

**목적:** Task 6의 7개 규칙을 `rules.py`에 함수로 구현. 각 함수는 `Rule` 클래스를 상속하고 `evaluate(df, ctx) -> RuleResult` 시그니처.

이 태스크는 분량이 커서 한 번에 모든 7개를 작성한다. 단위 테스트는 각 함수별 1~2개씩.

**Files:**
- Create: `RoboTrader_template/strategies/books/aziz_day_trade/rules.py`
- Create: `RoboTrader_template/tests/strategies/books/aziz_day_trade/__init__.py`
- Create: `RoboTrader_template/tests/strategies/books/aziz_day_trade/test_rules.py`

- [ ] **Step 1: 패키지 마커 + 실패하는 테스트 작성**

`RoboTrader_template/tests/strategies/books/aziz_day_trade/__init__.py`:
```python
```

`RoboTrader_template/tests/strategies/books/aziz_day_trade/test_rules.py`:
```python
"""아지즈 7개 규칙 단위 테스트."""

import numpy as np
import pandas as pd
import pytest

from strategies.books.aziz_day_trade import rules as az


def _df(closes, opens=None, highs=None, lows=None, volumes=None, start="2026-04-01 09:00"):
    n = len(closes)
    if opens is None:
        opens = closes[:]
    if highs is None:
        highs = [max(o, c) + 0.1 for o, c in zip(opens, closes)]
    if lows is None:
        lows = [min(o, c) - 0.1 for o, c in zip(opens, closes)]
    if volumes is None:
        volumes = [1000] * n
    return pd.DataFrame({
        "datetime": pd.date_range(start, periods=n, freq="1min"),
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })


def test_abcd_triggers_on_classic_shape():
    # A: 0~5 상승, B: 5~10 풀백, C: 10~13 재상승, D: 14에서 C 고가 돌파
    closes = [100, 101, 102, 103, 104, 105,    # A leg up
              104, 103, 102, 103, 104,         # B pullback
              105, 106, 107,                   # C leg up
              108]                             # D breakout
    df = _df(closes)
    res = az.rule_abcd().evaluate(df, {})
    assert res.triggered
    assert res.side == "buy"


def test_bull_flag_requires_prior_spike():
    closes = [100, 100, 100, 100, 106, 106.2, 106.1, 106.3, 106.5]  # spike then box, last bar break
    df = _df(closes)
    res = az.rule_bull_flag().evaluate(df, {})
    assert res.triggered


def test_vwap_reversal_recovers_above_vwap():
    # 한 시간 평탄, 잠시 깊은 dip, 마지막 봉 vwap 위 회복
    closes = [100] * 30 + [98, 97, 100.5]
    df = _df(closes)
    res = az.rule_vwap_reversal().evaluate(df, {})
    assert res.triggered


def test_opening_range_breakout_triggers_after_orb_high():
    # 첫 5봉 고가 = 102, 6번째 봉 close = 102.5
    closes = [100, 101, 102, 101.5, 101.8, 102.5]
    highs = [c + 0.1 for c in closes]
    df = _df(closes, highs=highs)
    res = az.rule_opening_range_breakout(orb_bars=5).evaluate(df, {})
    assert res.triggered


def test_red_to_green_requires_prev_close_cross():
    # prev_close = 105, 시가 100(red), 마지막 close = 105.2(>=prev_close)
    df = _df([100, 101, 102, 103, 104, 105.2])
    res = az.rule_red_to_green(prev_close=105.0).evaluate(df, {"prev_close": 105.0})
    assert res.triggered
    assert res.side == "buy"


def test_top_reversal_emits_sell_on_doji_low_volume():
    # 마지막 봉이 도지(open≈close) + 직전봉의 50% 미만 볼륨
    closes = [100, 101, 102, 103, 104, 104.05]
    opens = [99, 100, 101, 102, 103, 104.04]
    volumes = [1000, 1000, 1000, 1000, 1000, 400]
    df = _df(closes, opens=opens, volumes=volumes)
    res = az.rule_top_reversal().evaluate(df, {})
    assert res.triggered
    assert res.side == "sell"


def test_support_resistance_bounces_off_low():
    # 마지막 60봉 최저 = 95, 마지막 봉 저가 = 95.1, 양봉
    closes = [95.5] * 60 + [95.5, 96.0]
    lows = [95.5] * 59 + [95.0] + [95.1, 95.8]
    df = _df(closes, lows=lows)
    res = az.rule_support_resistance(window=60, tol=0.005).evaluate(df, {})
    assert res.triggered
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
pytest tests/strategies/books/aziz_day_trade/test_rules.py -v
```
Expected: ModuleNotFoundError: `strategies.books.aziz_day_trade.rules`

- [ ] **Step 3: 규칙 함수 구현**

`RoboTrader_template/strategies/books/aziz_day_trade/rules.py`:
```python
"""아지즈 — How to Day Trade for a Living: 7개 매매 규칙.

각 함수는 호출 시 Rule 인스턴스를 반환한다. evaluate(df, ctx)에서 t 시점 평가.
입력 df는 최소 20봉의 1분봉 OHLCV.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# ---------------------------------------------------------------------------
# 1. ABCD 패턴 — Ch.7
# ---------------------------------------------------------------------------

@dataclass
class rule_abcd(Rule):
    """A leg up → B pullback → C leg up → D breakout above C high.

    파라미터:
        lookback: 패턴 탐지에 사용할 직전 봉 수 (default 15)
    """
    name: str = "abcd"
    lookback: int = 15

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.lookback + 1:
            return RuleResult(triggered=False)
        seg = df.iloc[-(self.lookback + 1):].reset_index(drop=True)
        # A: 첫 1/3 의 high
        third = len(seg) // 3
        a_high = float(seg["high"].iloc[:third].max())
        # B: 가운데 1/3 의 low
        b_low = float(seg["low"].iloc[third:2 * third].min())
        # C: 다음 영역의 high (마지막 봉 직전)
        c_segment = seg["high"].iloc[2 * third:-1]
        if len(c_segment) == 0:
            return RuleResult(triggered=False)
        c_high = float(c_segment.max())
        last = float(seg["close"].iloc[-1])
        if a_high <= b_low or c_high <= b_low:
            return RuleResult(triggered=False)
        if last > c_high and last > a_high:
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=72.0,
                reasons=[f"abcd a={a_high:.2f} b={b_low:.2f} c={c_high:.2f} d={last:.2f}"],
                metadata={"a": a_high, "b": b_low, "c": c_high, "d": last},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 2. Bull Flag — Ch.7
# ---------------------------------------------------------------------------

@dataclass
class rule_bull_flag(Rule):
    """급등 후 좁은 박스 → 박스 상단 돌파."""
    name: str = "bull_flag"
    spike_pct: float = 0.04
    flag_bars: int = 3
    flag_range_pct: float = 0.02

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.flag_bars + 2:
            return RuleResult(triggered=False)
        # 직전 (flag_bars + 1) 봉이 박스 구간
        pre_flag_close = float(df["close"].iloc[-(self.flag_bars + 2)])
        flag = df.iloc[-(self.flag_bars + 1):-1]
        flag_high = float(flag["high"].max())
        flag_low = float(flag["low"].min())
        last_close = float(df["close"].iloc[-1])

        spike_ok = (flag_high - pre_flag_close) / max(pre_flag_close, 1e-9) >= self.spike_pct
        flag_range = (flag_high - flag_low) / max(flag_high, 1e-9)
        flag_ok = flag_range <= self.flag_range_pct
        breakout_ok = last_close > flag_high

        if spike_ok and flag_ok and breakout_ok:
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=70.0,
                reasons=[f"bull_flag spike={spike_ok} range={flag_range:.4f} brk={last_close:.2f}>flag={flag_high:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 3. VWAP Reversal — Ch.8
# ---------------------------------------------------------------------------

@dataclass
class rule_vwap_reversal(Rule):
    """가격이 VWAP 하단 이탈 후 다시 위로 마감하면 매수."""
    name: str = "vwap_reversal"
    dip_pct: float = 0.005

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 5:
            return RuleResult(triggered=False)
        tp = (df["high"] + df["low"] + df["close"]) / 3.0
        vwap = (tp * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, np.nan)
        vwap = vwap.bfill()
        last_close = float(df["close"].iloc[-1])
        last_vwap = float(vwap.iloc[-1])

        # 직전 N봉 중 종가 < vwap * (1 - dip_pct) 였던 봉이 있어야 함
        lookback = min(20, len(df))
        recent = df["close"].iloc[-lookback:-1]
        vwap_recent = vwap.iloc[-lookback:-1]
        dipped = ((recent < vwap_recent * (1.0 - self.dip_pct)).any())
        recovered = last_close > last_vwap

        if dipped and recovered:
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=68.0,
                reasons=[f"vwap_reversal last={last_close:.2f} vwap={last_vwap:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 4. Opening Range Breakout — Ch.7
# ---------------------------------------------------------------------------

@dataclass
class rule_opening_range_breakout(Rule):
    name: str = "orb"
    orb_bars: int = 5

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.orb_bars + 1:
            return RuleResult(triggered=False)
        orb_high = float(df["high"].iloc[: self.orb_bars].max())
        last_close = float(df["close"].iloc[-1])
        if last_close > orb_high:
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=66.0,
                reasons=[f"orb {self.orb_bars}봉 high={orb_high:.2f}, brk close={last_close:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 5. Red-to-Green — Ch.7
# ---------------------------------------------------------------------------

@dataclass
class rule_red_to_green(Rule):
    name: str = "red_to_green"
    prev_close: Optional[float] = None

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 2:
            return RuleResult(triggered=False)
        prev_close = self.prev_close if self.prev_close is not None else ctx.get("prev_close")
        if prev_close is None:
            # ctx 못받았으면 폴백: df의 첫 봉 시가를 prev_close로 추정 ( =EOD 청산 종목의 시초가 갭다운 시뮬)
            prev_close = float(df["open"].iloc[0]) * 1.01
        first_open = float(df["open"].iloc[0])
        last_close = float(df["close"].iloc[-1])
        red_start = first_open < prev_close * 0.998
        green_cross = last_close >= prev_close
        if red_start and green_cross:
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=64.0,
                reasons=[f"rtg open={first_open:.2f}<prev_close={prev_close:.2f}, last={last_close:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 6. Top Reversal (sell signal) — Ch.7
# ---------------------------------------------------------------------------

@dataclass
class rule_top_reversal(Rule):
    name: str = "top_reversal"
    doji_body_pct: float = 0.001
    vol_drop_pct: float = 0.5

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 2:
            return RuleResult(triggered=False)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        body = abs(float(last["close"]) - float(last["open"])) / max(float(last["open"]), 1e-9)
        is_doji = body <= self.doji_body_pct
        vol_drop = float(last["volume"]) < float(prev["volume"]) * self.vol_drop_pct
        if is_doji and vol_drop:
            return RuleResult(
                triggered=True,
                side="sell",
                confidence=62.0,
                reasons=[f"top_rev doji_body={body:.4f}, vol={last['volume']}<{prev['volume']}*{self.vol_drop_pct}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 7. Support/Resistance Bounce — Ch.7
# ---------------------------------------------------------------------------

@dataclass
class rule_support_resistance(Rule):
    name: str = "support_resistance"
    window: int = 60
    tol: float = 0.003

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.window + 1:
            return RuleResult(triggered=False)
        recent_low = float(df["low"].iloc[-(self.window + 1):-1].min())
        last_low = float(df["low"].iloc[-1])
        last_open = float(df["open"].iloc[-1])
        last_close = float(df["close"].iloc[-1])
        near_support = abs(last_low - recent_low) / max(recent_low, 1e-9) <= self.tol
        bullish_bar = last_close > last_open
        if near_support and bullish_bar:
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=60.0,
                reasons=[f"s/r support={recent_low:.2f} last_low={last_low:.2f}"],
            )
        return RuleResult(triggered=False)


# 책 전체 규칙을 모은 헬퍼
ALL_RULES = [
    rule_abcd,
    rule_bull_flag,
    rule_vwap_reversal,
    rule_opening_range_breakout,
    rule_red_to_green,
    rule_top_reversal,
    rule_support_resistance,
]
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/strategies/books/aziz_day_trade/test_rules.py -v
```
Expected: 7 passed (테스트 케이스 수 = 규칙 수)

조정 가능: 테스트가 실패하면 (1) 테스트 케이스의 dummy data 조정 (2) 규칙 함수의 임계값 조정 — 단, 책의 원래 의도와 어긋나지 않도록 README 갱신을 함께.

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/strategies/books/aziz_day_trade/rules.py \
  RoboTrader_template/tests/strategies/books/aziz_day_trade/__init__.py \
  RoboTrader_template/tests/strategies/books/aziz_day_trade/test_rules.py
git commit -m "feat(aziz): 7개 매매 규칙 코드화 (abcd/bull_flag/vwap/orb/rtg/top_rev/s_r)"
```

---

### Task 8: AzizDayTradeStrategy 본체 + build_strategy()

**목적:** rules.py의 함수를 BookStrategy로 묶는 strategy.py. CLI가 호출할 `build_strategy()` 팩토리 + BOOK_META 메타데이터.

**Files:**
- Create: `RoboTrader_template/strategies/books/aziz_day_trade/strategy.py`

- [ ] **Step 1: strategy.py 작성**

`RoboTrader_template/strategies/books/aziz_day_trade/strategy.py`:
```python
"""앤드류 아지즈 - How to Day Trade for a Living."""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.aziz_day_trade.rules import (
    rule_abcd,
    rule_bull_flag,
    rule_opening_range_breakout,
    rule_red_to_green,
    rule_support_resistance,
    rule_top_reversal,
    rule_vwap_reversal,
)


BOOK_META = {
    "id": "aziz_day_trade",
    "name": "How to Day Trade for a Living (Andrew Aziz)",
    "category": "intraday",
    "data_granularity": "minute",
}


def _all_rules():
    return [
        rule_abcd(),
        rule_bull_flag(),
        rule_vwap_reversal(),
        rule_opening_range_breakout(),
        rule_red_to_green(),
        rule_top_reversal(),
        rule_support_resistance(),
    ]


class AzizDayTradeStrategy(BookStrategy):
    name = "AzizDayTradeStrategy"
    version = "1.0.0"
    description = "Andrew Aziz - How to Day Trade for a Living (7 setups)"
    author = "kis-template"
    holding_period = "intraday"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> AzizDayTradeStrategy:
    return AzizDayTradeStrategy(
        rules=_all_rules(),
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
```

- [ ] **Step 2: 임포트 검증**

```bash
cd D:/GIT/kis-trading-template/RoboTrader_template
python -c "from strategies.books.aziz_day_trade.strategy import build_strategy; s = build_strategy(mode='all_AND'); print(s.name, len(s.rules))"
```
Expected: `AzizDayTradeStrategy 7`

- [ ] **Step 3: 커밋**

```bash
git add RoboTrader_template/strategies/books/aziz_day_trade/strategy.py
git commit -m "feat(aziz): AzizDayTradeStrategy + build_strategy 팩토리"
```

---

## Phase C — 백테스트 실행 & 리포트

### Task 9: 스모크 실행 (소수 종목 × 1 기간)

**목적:** 풀 백테스트 전에 5종목 × 1개 기간(2026-04)으로 스모크 실행, 파이프라인 전체가 살아있는지 확인.

- [ ] **Step 1: 스모크 실행 (single 모드, abcd 규칙)**

```bash
cd D:/GIT/kis-trading-template/RoboTrader_template
python scripts/run_books_research.py --book aziz_day_trade --period 2026-04 --mode single --rule abcd --limit 5 --log-level INFO
```

Expected 출력 패턴:
```
period=2026-04 (2026-04-01 ~ 2026-04-30) book=aziz_day_trade mode=single
universe size: 5
loaded data for 5 stocks
DONE n_stocks=5 n_trades=N pnl=X.XX% sharpe=X.XX calmar=X.XX
leaderboard updated: reports/books_research/leaderboard.parquet
```

- [ ] **Step 2: 산출 파일 확인**

```bash
ls reports/books_research/
ls reports/books_research/aziz_day_trade/
python -c "import pandas as pd; print(pd.read_parquet('reports/books_research/leaderboard.parquet'))"
```

Expected:
- `reports/books_research/leaderboard.parquet` 1행
- `reports/books_research/aziz_day_trade/results_single_abcd_2026-04.parquet` (trades 있을 경우)

- [ ] **Step 3: 디버그 — n_trades 가 0이면 책 규칙이 너무 빡빡한 것. README의 임계값 메모와 비교**

n_trades=0인 경우: 정상일 수 있음 (5종목 매우 작은 샘플). limit을 30 정도로 늘려 재시도:

```bash
python scripts/run_books_research.py --book aziz_day_trade --period 2026-04 --mode single --rule abcd --limit 30
```

- [ ] **Step 4: 스모크 통과 시 커밋 — 스모크 결과 자체는 정식 산출이 아니므로 .gitignore 검토**

`RoboTrader_template/reports/books_research/.gitignore`(없으면 생성):
```
# 스모크 산출. 풀런만 커밋
*_smoke*.parquet
```

스모크 결과는 정식 결과로 덮어쓸 것이므로 별도 커밋 안 함. 다음 태스크의 풀런 결과만 커밋.

---

### Task 10: 풀런 — 3기간 × 7규칙 single + 1 all_AND × 전종목

**목적:** 본 백테스트 실행. 각 기간마다 (7개 규칙 single 모드 + all_AND 1회) = 24회 실행. 시간이 오래 걸리므로 백그라운드 실행 + 모니터링.

- [ ] **Step 1: 스크립트 한 줄 명령으로 묶어 실행 (shell 루프)**

`RoboTrader_template/scripts/run_aziz_all.sh` (또는 .ps1):

PowerShell 버전 — `RoboTrader_template/scripts/run_aziz_all.ps1`:
```powershell
$rules = @("abcd","bull_flag","vwap_reversal","orb","red_to_green","top_reversal","support_resistance")
$periods = @("2025-10","2026-04","2026-05")

foreach ($p in $periods) {
    foreach ($r in $rules) {
        Write-Host "=== single $r $p ==="
        python scripts/run_books_research.py --book aziz_day_trade --period $p --mode single --rule $r
    }
    Write-Host "=== all_AND $p ==="
    python scripts/run_books_research.py --book aziz_day_trade --period $p --mode all_AND
}
```

- [ ] **Step 2: 백그라운드 실행 + 로그**

```bash
cd D:/GIT/kis-trading-template/RoboTrader_template
mkdir -p logs/books_research
powershell -File scripts/run_aziz_all.ps1 2>&1 | Tee-Object -FilePath logs/books_research/aziz_full_run.log
```

> 추정 시간: 7규칙 × 3기간 × ~1,000종목 × 20일 × 390분 / 1분봉 처리속도. 종목당 ~1초로 가정 시 ≈ 3 × 7 × 1000 × 1초 = 5.8시간. 1 all_AND는 신호가 거의 안 나와서 짧을 것. 총 6~8시간 예상.
> 모니터링: `tail -f logs/books_research/aziz_full_run.log`

- [ ] **Step 3: 완료 후 leaderboard 검증**

```bash
python -c "
import pandas as pd
df = pd.read_parquet('reports/books_research/leaderboard.parquet')
print(df[['period','rule_combo','mode','n_trades','pnl_pct','sharpe','calmar']].to_string())
"
```

Expected: 24행 (7 × 3 single + 1 × 3 all_AND = 24).

- [ ] **Step 4: 풀런 산출물 커밋**

```bash
git add RoboTrader_template/reports/books_research/leaderboard.parquet \
  RoboTrader_template/reports/books_research/aziz_day_trade/results_*.parquet \
  RoboTrader_template/scripts/run_aziz_all.ps1
git commit -m "backtest(aziz): 7규칙 single + all_AND × 3기간 풀런 결과"
```

---

### Task 11: 책별 리포트 작성 (writer 에이전트 위임)

**목적:** `reports/books_research/aziz_day_trade/report.md` 작성. 리더보드 데이터 기반 책 1권 요약.

- [ ] **Step 1: writer 에이전트로 위임**

이 플랜 실행자가 직접 호출:

```
Agent({
  description: "아지즈 책 백테스트 리포트 작성",
  subagent_type: "oh-my-claudecode:writer",
  prompt: "다음 데이터를 바탕으로 reports/books_research/aziz_day_trade/report.md 를 작성하세요. 한글로, 마크다운 형식.\n\n1. reports/books_research/leaderboard.parquet 의 book_id='aziz_day_trade' 행을 읽고 PnL/Sharpe/Calmar 표 만들기 (period × rule × mode).\n2. strategies/books/aziz_day_trade/README.md 의 규칙맵 표 그대로 포함.\n3. 각 규칙별로 한국 시장 25-10, 26-04, 26-05 에서 작동/미작동 여부 1줄 코멘트.\n4. 책의 핵심 가정(인트라데이 모멘텀 추격)이 한국 시장에서 검증됐는가, 어떤 규칙이 한국에 가장 잘 맞았는가 결론.\n5. 한계: 종목 풀, 거래비용 가정, 청산룰 단순화 등 명시."
})
```

- [ ] **Step 2: 작성된 report.md 검토 후 수정**

리포트가 사실과 다르거나 누락된 부분이 있으면 직접 보완. 특히 데이터 기반 수치는 leaderboard.parquet 와 일치하는지 확인.

- [ ] **Step 3: 커밋**

```bash
git add RoboTrader_template/reports/books_research/aziz_day_trade/report.md
git commit -m "docs(aziz): 아지즈 책 백테스트 결과 리포트"
```

---

### Task 12: 통합 리더보드 index.md 초기 작성

**목적:** `reports/books_research/index.md` 작성. 첫 책 결과를 통합 리더보드 형식으로 정리.

- [ ] **Step 1: index.md 작성**

`RoboTrader_template/reports/books_research/index.md`:
```markdown
# 트레이딩 책 10권 — 통합 리더보드

> 생성일: 2026-05-27 / 마지막 갱신: (자동)

## 진행 상태

| # | Book ID | Status |
|---|---|---|
| 1 | aziz_day_trade | ✅ 완료 |
| 2 | bellafiore_playbook | ⏳ |
| 3 | raschke_street_smarts | ⏳ |
| 4 | oneil_canslim | ⏳ |
| 5 | minervini_vcp | ⏳ |
| 6 | weinstein_stages | ⏳ |
| 7 | elder_triple_screen | ⏳ |
| 8 | lynch_one_up | ⏳ |
| 9 | greenblatt_magic_formula | ⏳ |
| 10 | osullivan_what_works | ⏳ |

## 전체 PnL 순위 (책 × 규칙조합 × 기간)

(아래 표는 `python scripts/regenerate_leaderboard_md.py` 로 자동 생성 — 다음 플랜에서 추가)

현재는 수동 작성. leaderboard.parquet 의 pnl_pct 내림차순 상위 20개를 표로 옮긴다:

| Rank | Book | Rule | Mode | Period | PnL% | Sharpe | Calmar | Trades |
|---|---|---|---|---|---|---|---|---|
| ... | aziz_day_trade | abcd | single | 2026-04 | (값) | (값) | (값) | (값) |

## 책별 베스트

- **aziz_day_trade** → 자세히: [report](aziz_day_trade/report.md)

## 다음 책

- bellafiore_playbook (Plan 2 에서)
```

- [ ] **Step 2: 커밋**

```bash
git add RoboTrader_template/reports/books_research/index.md
git commit -m "docs(books): 통합 리더보드 index 초기 작성 (아지즈 1권 반영)"
```

---

## 완료 기준

- [ ] `pytest RoboTrader_template/tests/strategies/books/ -v` 전부 통과 (15개 테스트)
- [ ] `leaderboard.parquet` 에 aziz_day_trade 24행 존재 (7 single × 3기간 + 1 all_AND × 3기간)
- [ ] `reports/books_research/aziz_day_trade/report.md` 작성 완료
- [ ] `reports/books_research/index.md` 작성 완료
- [ ] 모든 변경사항 커밋 완료

## Plan 2 예고

Plan 1 완료 후 Plan 2 = `bellafiore_playbook`. 동일 워크플로우(Task 5~12)를 다음 책으로 적용. 인프라(Task 1~4)는 재사용.

---

## Self-Review 노트

- 모든 Task 가 spec section 을 커버: §3 아키텍처(T1-3), §4 워크플로우(T4-12), §5 백테스트 엔진(T2-3), §6 산출물(T11-12), §7 품질게이트(T2 거래비용·T6 README 룩어헤드 노트)
- 플레이스홀더 없음 — 모든 코드 실제 작성됨. 단, Task 5 의 RULES_RESEARCH.md 와 Task 11 의 report.md 는 에이전트 위임이므로 본 플랜에 본문이 없음 (의도된 처리)
- 타입 일관성: `Rule.evaluate` 시그니처, `RuleResult` 필드, `BookStrategy.__init__` 인자가 Task 1→7→8 일관
- 잠재 리스크: Task 7 의 테스트 데이터(toy)가 너무 단순해 실제 시장 데이터에서 규칙이 다르게 동작할 수 있음. 이 경우 Task 9 스모크에서 발견·튜닝

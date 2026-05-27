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
    # 단조 상승 데이터 → 수수료·세금 차감 후에도 양의 PnL 이어야 함
    assert result.pnl_pct > 0, "Monotonically rising data should yield positive PnL"
    # 모든 매도가 수익이어야 hit_rate=1.0
    assert result.hit_rate == pytest.approx(1.0)


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

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


def test_book_strategy_and_mode_empty_rules_returns_none():
    """HIGH bug regression: all_AND with empty rules must return None, not raise IndexError."""
    strat = BookStrategy(rules=[], mode="all_AND")
    sig = strat.generate_signal("005930", _dummy_df(), timeframe="intraday")
    assert sig is None


def test_book_strategy_duplicate_rule_names_raises():
    """Duplicate rule names should be rejected at construction."""
    class _Dup1(Rule):
        name = "dup"
        def evaluate(self, df, ctx):
            return RuleResult(triggered=False)

    class _Dup2(Rule):
        name = "dup"
        def evaluate(self, df, ctx):
            return RuleResult(triggered=False)

    with pytest.raises(ValueError, match="Duplicate rule names"):
        BookStrategy(rules=[_Dup1(), _Dup2()], mode="single", target_rule="dup")


def test_book_strategy_invalid_side_raises():
    """RuleResult.side must be 'buy' or 'sell' — anything else triggers ValueError on signal generation."""
    class _BadSideRule(Rule):
        name = "bad_side"
        def evaluate(self, df, ctx):
            return RuleResult(triggered=True, side="short")  # type: ignore[arg-type]

    strat = BookStrategy(rules=[_BadSideRule()], mode="single", target_rule="bad_side")
    with pytest.raises(ValueError, match="side must be"):
        strat.generate_signal("005930", _dummy_df(), timeframe="intraday")

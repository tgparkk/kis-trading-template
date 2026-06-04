from unittest.mock import Mock
from core.trading_context import TradingContext


def _stock(code, owner):
    s = Mock(); s.stock_code = code; s.strategy_name = owner
    return s


def _ctx(strategy_key, stocks):
    ctx = TradingContext.__new__(TradingContext)
    ctx.logger = Mock()
    ctx._strategy_key = strategy_key
    tm = Mock(); tm.get_stocks_by_state.return_value = stocks
    ctx._trading_manager = tm
    return ctx


def test_returns_only_own_and_unowned():
    stocks = [_stock("A", "elder_ema_pullback"), _stock("B", "minervini_volume_dryup"), _stock("C", None)]
    ctx = _ctx("elder_ema_pullback", stocks)
    assert [s.stock_code for s in ctx.get_selected_stocks()] == ["A", "C"]


def test_explicit_owner_arg_overrides():
    stocks = [_stock("A", "elder_ema_pullback"), _stock("B", "minervini_volume_dryup")]
    ctx = _ctx("elder_ema_pullback", stocks)
    assert [s.stock_code for s in ctx.get_selected_stocks(owner="minervini_volume_dryup")] == ["B"]


def test_legacy_no_strategy_key_returns_all():
    stocks = [_stock("A", "elder_ema_pullback"), _stock("B", None)]
    ctx = _ctx(None, stocks)   # _strategy_key=None
    assert [s.stock_code for s in ctx.get_selected_stocks()] == ["A", "B"]

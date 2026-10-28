"""엔진 매수 판단의 관측 로그 2종 (10-29 창구 묶음 A ⑥⑦ · 동작 변화 0).

- [자투리-shadow]: 수량 산정 뒤 max_amt < 종목당 예산 × SCRAP_BUY_SHADOW_RATIO(0.5) → INFO.
  실전 종목당 예산 = fund_manager.total_funds × max_position_ratio · 가상 = 전략 원장의 종목당 예산.
  주문은 그대로 나간다.
- [주문가-괴리]: 신호 참조가(signal.price → metadata['close'] → 사유의 close=)가 있으면 INFO 1줄.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from core.models import StockState, TradingStock
from strategies.base import Signal, SignalType


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def engine():
    with patch('core.trading_decision_engine.setup_logger'), \
         patch('core.virtual_trading_manager.setup_logger'):
        from core.trading_decision_engine import TradingDecisionEngine
        e = TradingDecisionEngine(
            db_manager=Mock(), telegram_integration=None, trading_manager=None,
            broker=None, config=Mock(paper_trading=True),
        )
    e.check_market_direction = Mock(return_value=(False, ""))
    e.logger = Mock()
    return e


@pytest.fixture
def daily_data():
    base = datetime(2026, 6, 1, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    closes = [1500.0 + 10 * i for i in range(30)]
    return pd.DataFrame({
        'datetime': [base + timedelta(days=i) for i in range(30)],
        'open': closes, 'high': closes, 'low': closes, 'close': closes,
        'volume': [100000] * 30,
    })


def _im(price):
    im = Mock()
    im.get_current_price_for_sell.return_value = {'current_price': price}
    im.get_cached_current_price.return_value = {'current_price': price}
    return im


def _signal(metadata=None, reasons=None):
    return Signal(signal_type=SignalType.BUY, stock_code="078520", confidence=68.0,
                  reasons=reasons or ["breakout"], metadata=metadata or {})


def _stock():
    return TradingStock(stock_code="078520", stock_name="078520",
                        state=StockState.SELECTED, selected_time=datetime.now())


def _infos(engine, tag):
    return [c.args[0] for c in engine.logger.info.call_args_list
            if c.args and tag in str(c.args[0])]


def _real_mode(engine, total_funds, max_amt, price):
    engine.is_virtual_mode = False
    engine.virtual_trading = None
    engine.intraday_manager = _im(price)
    fm = Mock()
    fm.total_funds = total_funds
    fm.max_position_ratio = 0.09
    fm.get_max_buy_amount.return_value = max_amt
    engine.fund_manager = fm


# ---------------------------------------------------------------------------
# [자투리-shadow]
# ---------------------------------------------------------------------------

def test_scrap_ratio_constant():
    from config.constants import SCRAP_BUY_SHADOW_RATIO
    assert SCRAP_BUY_SHADOW_RATIO == 0.5


def test_scrap_shadow_real_logs_and_order_unchanged(engine, daily_data):
    """078520 꼴: 종목당 450,000(5,000,000×0.09) 인데 잔여 85,190 → would_skip=1, 주문은 7주 그대로."""
    _real_mode(engine, total_funds=5_000_000, max_amt=85_190, price=12_170)
    ok, reason, info = _run(engine.analyze_buy_decision(_stock(), daily_data, owner_signal=_signal()))
    assert ok is True
    assert info['quantity'] == 7 and info['buy_price'] == 12_170
    lines = _infos(engine, "[자투리-shadow]")
    assert lines == ["[자투리-shadow] would_skip=1 078520 amount=85,190 target=450,000 ratio=0.19"]


def test_scrap_shadow_real_no_log_when_full_size(engine, daily_data):
    _real_mode(engine, total_funds=5_000_000, max_amt=450_000, price=12_170)
    ok, _, info = _run(engine.analyze_buy_decision(_stock(), daily_data, owner_signal=_signal()))
    assert ok is True and info['quantity'] == 36
    assert _infos(engine, "[자투리-shadow]") == []


def test_scrap_shadow_virtual_uses_ledger_per_stock(engine, daily_data):
    from core.virtual_trading_manager import VirtualTradingManager
    with patch('core.virtual_trading_manager.setup_logger'):
        vtm = VirtualTradingManager.__new__(VirtualTradingManager)
    vtm.logger = Mock()
    vtm._strategy_balances = {"s": 300_000.0}
    vtm._strategy_investment_amounts = {"s": 1_000_000.0}
    vtm._strategy_max_per_stock = {}
    vtm.virtual_balance = 300_000.0
    vtm.virtual_investment_amount = 1_000_000.0
    vtm._has_strategy_ledger = lambda name="": name in vtm._strategy_balances
    engine.is_virtual_mode = True
    engine.virtual_trading = vtm
    engine.intraday_manager = _im(10_000)
    engine.fund_manager = None
    ok, _, info = _run(engine.analyze_buy_decision(
        _stock(), daily_data, owner_signal=_signal(), strategy_name="s"))
    assert ok is True and info['quantity'] == 30
    assert _infos(engine, "[자투리-shadow]") == [
        "[자투리-shadow] would_skip=1 078520 amount=300,000 target=1,000,000 ratio=0.30"]


def test_scrap_shadow_exception_never_breaks_buy(engine, daily_data):
    _real_mode(engine, total_funds=5_000_000, max_amt=85_190, price=12_170)
    engine.fund_manager.total_funds = "not-a-number"
    ok, _, info = _run(engine.analyze_buy_decision(_stock(), daily_data, owner_signal=_signal()))
    assert ok is True and info['quantity'] == 7


# ---------------------------------------------------------------------------
# [주문가-괴리]
# ---------------------------------------------------------------------------

def test_order_price_gap_from_metadata_close(engine, daily_data):
    """097520 꼴: 신호가(전일 종가) 21,450 · 주문가 20,100 → −6.29%."""
    _real_mode(engine, total_funds=5_000_000, max_amt=450_000, price=20_100)
    ok, _, info = _run(engine.analyze_buy_decision(
        _stock(), daily_data, owner_signal=_signal(metadata={"close": 21_450.0})))
    assert ok is True and info['buy_price'] == 20_100
    assert _infos(engine, "[주문가-괴리]") == ["[주문가-괴리] 078520 신호가=21,450 주문가=20,100 -6.29%"]


def test_order_price_gap_from_reason_close(engine, daily_data):
    _real_mode(engine, total_funds=5_000_000, max_amt=450_000, price=10_100)
    _run(engine.analyze_buy_decision(
        _stock(), daily_data, owner_signal=_signal(reasons=["돌파 close=10,000 vol x3"])))
    assert _infos(engine, "[주문가-괴리]") == ["[주문가-괴리] 078520 신호가=10,000 주문가=10,100 +1.00%"]


def test_order_price_gap_absent_reference_no_log(engine, daily_data):
    _real_mode(engine, total_funds=5_000_000, max_amt=450_000, price=10_100)
    _run(engine.analyze_buy_decision(_stock(), daily_data, owner_signal=_signal()))
    assert _infos(engine, "[주문가-괴리]") == []


def test_signal_ref_price_extraction():
    from core.trading_decision_engine import signal_reference_price
    assert signal_reference_price(None) is None
    assert signal_reference_price(_signal()) is None
    assert signal_reference_price(_signal(metadata={"close": 123.0})) == 123.0
    assert signal_reference_price(_signal(reasons=["x close=1,234.5 y"])) == 1234.5
    s = _signal(metadata={"close": 1.0})
    s.price = 99.0  # 신호 객체에 price 가 있으면 그쪽이 우선
    assert signal_reference_price(s) == 99.0
    assert signal_reference_price(_signal(metadata={"close": "bad"})) is None


# ---------------------------------------------------------------------------
# 동작 불변: 로그 경로를 통째로 깨뜨려도 반환이 같다
# ---------------------------------------------------------------------------

def test_behaviour_identical_when_shadow_helpers_fail(engine, daily_data):
    _real_mode(engine, total_funds=5_000_000, max_amt=85_190, price=12_170)
    sig = _signal(metadata={"close": 12_000.0})
    baseline = _run(engine.analyze_buy_decision(_stock(), daily_data, owner_signal=sig))
    with patch('core.trading_decision_engine.signal_reference_price', side_effect=RuntimeError("x")):
        engine.fund_manager.max_position_ratio = object()
        broken = _run(engine.analyze_buy_decision(_stock(), daily_data, owner_signal=sig))
    assert baseline[0] == broken[0] and baseline[1] == broken[1]
    assert {k: v for k, v in baseline[2].items() if k != 'signal'} == \
        {k: v for k, v in broken[2].items() if k != 'signal'}

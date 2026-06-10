"""전략별 일별 equity 트래커 — 순수 리플레이/평가 로직 테스트.

virtual_trading_records 를 전략별로 리플레이해 일별 (cash, positions, equity)를
만든다. 수수료 모델은 봇(virtual_trading_manager)과 동일:
  BUY:  cash -= qty*price*(1+COMMISSION_RATE)
  SELL: cash += qty*price*(1-COMMISSION_RATE-SECURITIES_TAX_RATE)
평가: 보유포지션은 해당일 종가(closes)로 mark-to-market, 종가 없으면 매수가 fallback.
"""
from datetime import date

import pytest

from scripts.paper_strategy_equity import replay_strategy_equity

COMM = 0.00015
TAX = 0.0018


def _rec(d, action, code, qty, price, strategy="s1"):
    return {
        "trade_date": d, "action": action, "stock_code": code,
        "quantity": qty, "price": float(price), "strategy": strategy,
    }


def test_buy_deducts_cash_with_fee_and_opens_position():
    rows = replay_strategy_equity(
        records=[_rec(date(2026, 6, 8), "BUY", "A", 10, 1000)],
        initial_capital=10_000_000,
        dates=[date(2026, 6, 8)],
        closes={("A", date(2026, 6, 8)): 1000.0},
    )
    r = rows[0]
    assert r["trade_date"] == date(2026, 6, 8)
    assert r["cash"] == pytest.approx(10_000_000 - 10 * 1000 * (1 + COMM))
    assert r["position_value"] == pytest.approx(10 * 1000)
    assert r["n_open"] == 1
    assert r["equity"] == pytest.approx(r["cash"] + r["position_value"])


def test_sell_credits_net_and_accumulates_realized():
    rows = replay_strategy_equity(
        records=[
            _rec(date(2026, 6, 8), "BUY", "A", 10, 1000),
            _rec(date(2026, 6, 9), "SELL", "A", 10, 1100),
        ],
        initial_capital=10_000_000,
        dates=[date(2026, 6, 8), date(2026, 6, 9)],
        closes={("A", date(2026, 6, 8)): 1000.0},
    )
    d2 = rows[1]
    expected_cash = (10_000_000
                     - 10 * 1000 * (1 + COMM)
                     + 10 * 1100 * (1 - COMM - TAX))
    assert d2["cash"] == pytest.approx(expected_cash)
    assert d2["n_open"] == 0
    assert d2["position_value"] == 0
    assert d2["equity"] == pytest.approx(expected_cash)
    # 실현손익(gross): (1100-1000)*10 = 1000
    assert d2["realized_pnl_cum"] == pytest.approx(1000.0)


def test_open_position_marked_to_market_across_days():
    rows = replay_strategy_equity(
        records=[_rec(date(2026, 6, 8), "BUY", "A", 10, 1000)],
        initial_capital=10_000_000,
        dates=[date(2026, 6, 8), date(2026, 6, 9)],
        closes={("A", date(2026, 6, 8)): 1000.0, ("A", date(2026, 6, 9)): 1200.0},
    )
    assert rows[1]["position_value"] == pytest.approx(10 * 1200)
    assert rows[1]["equity"] > rows[0]["equity"]  # 평가익 반영


def test_missing_close_falls_back_to_buy_price():
    rows = replay_strategy_equity(
        records=[_rec(date(2026, 6, 8), "BUY", "A", 10, 1000)],
        initial_capital=10_000_000,
        dates=[date(2026, 6, 8)],
        closes={},
    )
    assert rows[0]["position_value"] == pytest.approx(10 * 1000)


def test_records_before_epoch_dates_are_ignored():
    # dates 가 에포크(06-08~)만 포함하면 그 이전 레코드는 무시
    rows = replay_strategy_equity(
        records=[
            _rec(date(2026, 6, 1), "BUY", "Z", 5, 500),
            _rec(date(2026, 6, 8), "BUY", "A", 10, 1000),
        ],
        initial_capital=10_000_000,
        dates=[date(2026, 6, 8)],
        closes={("A", date(2026, 6, 8)): 1000.0},
    )
    assert rows[0]["n_open"] == 1  # Z 미포함
    assert rows[0]["cash"] == pytest.approx(10_000_000 - 10 * 1000 * (1 + COMM))


def test_no_trade_day_carries_state_forward():
    rows = replay_strategy_equity(
        records=[_rec(date(2026, 6, 8), "BUY", "A", 10, 1000)],
        initial_capital=10_000_000,
        dates=[date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10)],
        closes={("A", date(2026, 6, 8)): 1000.0,
                ("A", date(2026, 6, 9)): 1000.0,
                ("A", date(2026, 6, 10)): 1000.0},
    )
    assert len(rows) == 3
    assert rows[1]["cash"] == rows[0]["cash"]
    assert rows[2]["equity"] == pytest.approx(rows[0]["equity"])

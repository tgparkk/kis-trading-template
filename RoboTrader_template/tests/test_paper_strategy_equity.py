"""전략별 일별 equity 트래커 — 순수 리플레이/평가 로직 테스트.

virtual_trading_records 를 전략별로 리플레이해 일별 (cash, positions, equity)를
만든다. 수수료 모델은 봇(virtual_trading_manager)과 동일:
  BUY:  cash -= qty*price*(1+COMMISSION_RATE)
  SELL: cash += qty*price*(1-COMMISSION_RATE-SECURITIES_TAX_RATE)
평가: 보유포지션은 해당일 종가(closes)로 mark-to-market, 종가 없으면 매수가 fallback.
"""
from datetime import date

import pandas as pd
import pytest

from scripts.paper_strategy_equity import replay_strategy_equity, _load_closes

COMM = 0.00015
TAX = 0.0018


class _FakeReader:
    """get_daily_prices(code, end_date, days) → 오름차순 DataFrame(date, close).

    closes_by_code: {code: {date: close}}. 없는 종목은 빈 DataFrame.
    """

    def __init__(self, closes_by_code):
        self._data = closes_by_code

    def get_daily_prices(self, stock_code, end_date=None, days=120):
        series = self._data.get(str(stock_code))
        if not series:
            return pd.DataFrame()
        rows = [{"date": pd.Timestamp(d), "close": float(c)} for d, c in series.items()]
        df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        return df


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


def test_oversold_sell_credits_full_cash_unconditionally():
    # 라이브 누적 재구성과 동일: 매도는 추적 포지션 유무·수량과 무관하게
    # 전량(qty) 현금 반영. 포지션 qty 는 0 으로 clamp(현금 이중반영 없음).
    rows = replay_strategy_equity(
        records=[
            _rec(date(2026, 6, 8), "BUY", "A", 10, 1000),
            _rec(date(2026, 6, 9), "SELL", "A", 25, 1100),  # 보유 10인데 25 매도
        ],
        initial_capital=10_000_000,
        dates=[date(2026, 6, 8), date(2026, 6, 9)],
        closes={("A", date(2026, 6, 8)): 1000.0},
    )
    d2 = rows[1]
    expected_cash = (10_000_000
                     - 10 * 1000 * (1 + COMM)
                     + 25 * 1100 * (1 - COMM - TAX))  # 전량 25 반영
    assert d2["cash"] == pytest.approx(expected_cash)
    assert d2["n_open"] == 0          # 포지션은 0으로 clamp
    assert d2["position_value"] == 0


def test_realized_uses_profit_loss_column_when_present():
    # 레코드에 봇의 실제 profit_loss 가 있으면 avg_cost 추정 대신 그 값을 누적(권위).
    sell = _rec(date(2026, 6, 9), "SELL", "A", 10, 1100)
    sell["profit_loss"] = 888.0
    rows = replay_strategy_equity(
        records=[_rec(date(2026, 6, 8), "BUY", "A", 10, 1000), sell],
        initial_capital=10_000_000,
        dates=[date(2026, 6, 8), date(2026, 6, 9)],
        closes={("A", date(2026, 6, 8)): 1000.0},
    )
    assert rows[1]["realized_pnl_cum"] == pytest.approx(888.0)


def test_final_cash_equals_live_reconstruction_formula():
    # 라이브 restore_strategy_ledger_from_records 와 바이트 동일한 현금 공식:
    #   cash = initial - Σbuy_gross*(1+c) + Σsell_gross*(1-c-t)
    recs = [
        _rec(date(2026, 6, 8), "BUY", "A", 10, 1000),
        _rec(date(2026, 6, 9), "BUY", "B", 5, 2000),
        _rec(date(2026, 6, 10), "SELL", "A", 10, 1050),
    ]
    rows = replay_strategy_equity(
        records=recs, initial_capital=10_000_000,
        dates=[date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10)],
        closes={},
    )
    buy_gross = 10 * 1000 + 5 * 2000
    sell_gross = 10 * 1050
    expected_cash = (10_000_000
                     - buy_gross * (1 + COMM)
                     + sell_gross * (1 - COMM - TAX))
    assert rows[-1]["cash"] == pytest.approx(expected_cash)


def test_sell_then_rebuy_nets_to_true_inventory_no_phantom():
    # 매도가 보유보다 먼저/초과로 처리된 뒤 재매수해도 net(Σ매수-Σ매도)로 수렴해야
    # 한다. 구버전은 매도시 포지션을 조기 pop 해 재매수가 유령 포지션을 남겼다.
    # 여기선 A 를 10 사고 → 15 팔고(net -5) → 5 다시 사서 net 0(보유 없음)이어야 함.
    rows = replay_strategy_equity(
        records=[
            _rec(date(2026, 6, 8), "BUY", "A", 10, 1000),
            _rec(date(2026, 6, 9), "SELL", "A", 15, 1100),
            _rec(date(2026, 6, 10), "BUY", "A", 5, 1050),
        ],
        initial_capital=10_000_000,
        dates=[date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10)],
        closes={("A", date(2026, 6, 10)): 1050.0},
    )
    last = rows[-1]
    assert last["n_open"] == 0           # net 0 → 유령 포지션 없음
    assert last["position_value"] == 0


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


# ── 평가 소스 선택 (T-close vs T-1 stale) ──────────────────────────────────
# 버그(2026-06-25): 15:35 EOD 스냅샷이 보유를 robotrader_quant(외부 ETL) 종가로
# 평가하는데, 15:35 시점엔 당일(T) 공식종가가 quant 에 아직 없어 전일(T-1) 종가로
# 폴백 → equity 가 하루 밀려 기록됨. 봇은 step6 에서 당일종가를 자체 DB(kis_template)
# 로 직접 수집하므로, _load_closes 는 kis_template 을 1순위로 써야 T-close 로 평가된다.

D_T1 = date(2026, 6, 24)
D_T = date(2026, 6, 25)


def test_load_closes_prefers_primary_reader_for_today_close():
    """1순위 리더(kis_template)에 당일종가가 있으면 그 값을 쓴다(2순위 stale 무시)."""
    # quant(2순위)는 당일종가가 없고 전일(T-1)만 있는 stale 상태 재현
    quant = _FakeReader({"A": {D_T1: 1000.0}})
    # kis_template(1순위)은 step6 수집으로 당일종가 1200 보유
    kis = _FakeReader({"A": {D_T1: 1000.0, D_T: 1200.0}})
    closes = _load_closes(["A"], [D_T1, D_T], readers=[kis, quant])
    assert closes[("A", D_T)] == pytest.approx(1200.0)  # T-close (stale 아님)
    assert closes[("A", D_T1)] == pytest.approx(1000.0)


def test_load_closes_stale_when_only_fallback_has_t1_close():
    """1순위에 당일종가가 없고 2순위(quant)도 T-1 까지만 있으면 (A,T) 키는 없다.

    이 경우 replay 의 보유평가는 last_close(=T-1) 로 폴백 → stale equity (현 버그 재현).
    """
    quant = _FakeReader({"A": {D_T1: 1000.0}})  # T-1 까지만
    kis = _FakeReader({"A": {D_T1: 1000.0}})     # 아직 step6 미수집 → T 없음
    closes = _load_closes(["A"], [D_T1, D_T], readers=[kis, quant])
    assert (("A", D_T) not in closes)  # 당일종가 소스에 없음

    # replay 에 이 closes 를 주면 보유평가가 T-1(1000) 로 stale 평가됨
    rows = replay_strategy_equity(
        records=[_rec(D_T1, "BUY", "A", 10, 1000)],
        initial_capital=10_000_000,
        dates=[D_T1, D_T],
        closes=closes,
    )
    assert rows[-1]["position_value"] == pytest.approx(10 * 1000.0)  # stale = T-1


def test_load_closes_falls_back_to_secondary_when_primary_missing_code():
    """1순위에 종목이 아예 없으면 2순위(quant) 종가로 폴백한다."""
    quant = _FakeReader({"B": {D_T1: 500.0, D_T: 550.0}})
    kis = _FakeReader({})  # B 없음
    closes = _load_closes(["B"], [D_T1, D_T], readers=[kis, quant])
    assert closes[("B", D_T)] == pytest.approx(550.0)


def test_load_closes_resnapshot_uses_t_close_after_collection():
    """step6(당일종가 수집) 후 재평가하면 보유가 T-close 로 평가됨(버그 수정 검증)."""
    # 수집 후: kis_template(1순위)에 당일종가 1200 존재
    quant = _FakeReader({"A": {D_T1: 1000.0}})
    kis = _FakeReader({"A": {D_T1: 1000.0, D_T: 1200.0}})
    closes = _load_closes(["A"], [D_T1, D_T], readers=[kis, quant])
    rows = replay_strategy_equity(
        records=[_rec(D_T1, "BUY", "A", 10, 1000)],
        initial_capital=10_000_000,
        dates=[D_T1, D_T],
        closes=closes,
    )
    assert rows[-1]["position_value"] == pytest.approx(10 * 1200.0)  # T-close

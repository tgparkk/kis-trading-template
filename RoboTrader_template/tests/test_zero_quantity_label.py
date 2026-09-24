"""D-1 게이트 관측 번들 ④ — `수량부족` 사유 라벨(현금부족 / 단가초과 / 둘 다).

사전등록: docs/prereg_2026-09-24_gate_observability_bundle.md §2-④ · §4-1 ④ · §10-4.

「지갑이 비었다」와 「1주가 종목당 예산보다 비싸다」는 처방이 정반대인데 한 문자열
(`{code} 수량부족`)이었다. 엔진 `qty <= 0` 분기 «안»에서만 VTM 읽기 전용 메서드
`describe_zero_quantity` 로 접미를 붙인다 — 제어 흐름·qty·buy_info 불변, 접두 유지.

이 파일이 단언하는 것:
  ① 격자(budget·per_stock·cap(None·0·음수·양수)·price)에서 `get_max_quantity == 0` ⇔ 라벨 ≠ ""
  ② 3라벨 각각의 정확한 문구(금액 `{:,.0f}`)
  ③ 메서드 예외·Mock 반환(비문자열) → 정확히 `"{code} 수량부족"` · 실전 경로 불변
  ④ 스로틀 키가 라벨별로 갈리고 `logscan8.reject_gate` 는 셋 다 G_QTY
"""
import copy
import itertools
import re
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from strategies.base import Signal, SignalType

NAME = "stratA"
E4 = re.compile(r"\[매수거절\] [0-9A-Z]{6} 수량부족( 외 [0-9]+회)?$")


def _make_vtm():
    with patch("core.virtual_trading_manager.setup_logger"):
        from core.virtual_trading_manager import VirtualTradingManager
        return VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)


def _vtm(budget, per_stock, cap, *, ledger=True):
    vtm = _make_vtm()
    if ledger:
        vtm._strategy_balances[NAME] = budget
        vtm._strategy_investment_amounts[NAME] = per_stock
    else:
        vtm._strategy_balances.clear()
        vtm.virtual_balance = budget
        vtm.virtual_investment_amount = per_stock
    if cap is not None:
        vtm._strategy_max_per_stock[NAME] = cap
    return vtm


# ── ① 격자 ──────────────────────────────────────────────────────────────────

BUDGETS = [-1_000, 0, 398, 5_649, 5_650, 484_000, 4_000_000]
PER_STOCKS = [0, 5_000, 5_650, 435_786, 1_668_815]
CAPS = [None, 0, -5, 5_000, 5_650, 3_000_000]
PRICES = [1, 5_650, 7_777.0, 484_000]   # 엔진 price = round_to_tick(실시간가) > 0


@pytest.mark.parametrize("ledger", [True, False])
def test_zero_quantity_iff_label_nonempty_on_grid(ledger):
    checked = 0
    for budget, per_stock, cap, price in itertools.product(BUDGETS, PER_STOCKS, CAPS, PRICES):
        vtm = _vtm(budget, per_stock, cap, ledger=ledger)
        qty = vtm.get_max_quantity(price, NAME)
        label = vtm.describe_zero_quantity(price, NAME)
        assert (qty == 0) == (label != ""), (budget, per_stock, cap, price, qty, label)
        if label:
            eff = min(per_stock, cap) if (cap is not None and 0 < cap) else per_stock
            assert ("현금부족" in label) == (budget < price)
            assert ("단가초과" in label) == (eff < price)
        checked += 1
    assert checked == len(BUDGETS) * len(PER_STOCKS) * len(CAPS) * len(PRICES)


def test_nonpositive_price_is_unlabelled_like_g1_early_return():
    """G1 은 price <= 0 이면 계산 없이 0 — 라벨도 계산하지 않는다(엔진 price 는 항상 > 0)."""
    vtm = _vtm(1_000_000, 1_000_000, None)
    assert vtm.get_max_quantity(0, NAME) == 0
    assert vtm.describe_zero_quantity(0, NAME) == ""
    assert vtm.describe_zero_quantity(-1, NAME) == ""


# ── ② 3라벨 문구 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("budget,per_stock,cap,price,expected", [
    (398, 1_668_815, 3_000_000, 5_650,
     "·현금부족 (전략잔여 398원 · 종목당 1,668,815원 · 1주 5,650원)"),
    (4_000_000, 435_786, 3_000_000, 484_000,
     "·단가초과 (전략잔여 4,000,000원 · 종목당 435,786원 · 1주 484,000원)"),
    (100, 1_000, None, 5_000,
     "·현금부족+단가초과 (전략잔여 100원 · 종목당 1,000원 · 1주 5,000원)"),
    # cap 이 per_stock 보다 작으면 「종목당」 = cap (G1 과 같은 min)
    (4_000_000, 1_668_815, 400_000, 484_000,
     "·단가초과 (전략잔여 4,000,000원 · 종목당 400,000원 · 1주 484,000원)"),
    # 금액은 원 단위 정수 표기
    (398.4, 1_668_815.6, None, 5_650,
     "·현금부족 (전략잔여 398원 · 종목당 1,668,816원 · 1주 5,650원)"),
])
def test_three_labels_exact_text(budget, per_stock, cap, price, expected):
    vtm = _vtm(budget, per_stock, cap)
    assert vtm.get_max_quantity(price, NAME) == 0
    assert vtm.describe_zero_quantity(price, NAME) == expected


def test_describe_is_read_only():
    vtm = _vtm(398, 1_668_815, 3_000_000)
    before = copy.deepcopy((vtm._strategy_balances, vtm._strategy_investment_amounts,
                            vtm._strategy_max_per_stock, vtm.virtual_balance,
                            vtm.virtual_investment_amount))
    vtm.describe_zero_quantity(5_650, NAME)
    after = (vtm._strategy_balances, vtm._strategy_investment_amounts,
             vtm._strategy_max_per_stock, vtm.virtual_balance, vtm.virtual_investment_amount)
    assert after == before


def test_describe_swallows_internal_errors():
    vtm = _vtm(398, 1_668_815, 3_000_000)
    vtm._strategy_max_per_stock = None           # .get 에서 AttributeError
    assert vtm.describe_zero_quantity(5_650, NAME) == ""


# ── ③ 엔진 경로 ─────────────────────────────────────────────────────────────

def _engine(*, virtual=True, vtm=None, price=5_650.0):
    from core.trading_decision_engine import TradingDecisionEngine
    eng = TradingDecisionEngine.__new__(TradingDecisionEngine)
    eng.logger = Mock()
    eng.strategy = None
    eng.is_virtual_mode = virtual
    eng.virtual_trading = vtm
    eng.check_market_direction = Mock(return_value=(False, ""))
    eng._get_live_price = Mock(return_value=price)
    return eng


def _stock():
    st = Mock()
    st.stock_code = "088350"
    return st


def _daily():
    return pd.DataFrame({"close": [5_650.0] * 30})


def _signal():
    return Signal(signal_type=SignalType.BUY, stock_code="088350", reasons=["dryup"])


async def _decide(eng, strategy_name=NAME):
    with patch("core.regime.market_classifier.resolve_regime_index", return_value="none"):
        return await eng.analyze_buy_decision(
            _stock(), _daily(), regime_index="none", owner_signal=_signal(),
            strategy_name=strategy_name)


@pytest.mark.asyncio
async def test_engine_virtual_mode_appends_label():
    ok, reason, info = await _decide(_engine(vtm=_vtm(398, 1_668_815, 3_000_000)))
    assert ok is False
    assert reason == "088350 수량부족·현금부족 (전략잔여 398원 · 종목당 1,668,815원 · 1주 5,650원)"
    assert info == {"buy_price": 0, "quantity": 0, "max_buy_amount": 0}


@pytest.mark.asyncio
async def test_engine_passes_ledger_key_fallback_to_strategy_name():
    """strategy_name 이 비면 엔진 fallback(self.strategy.name)이 원장 키 — 라벨도 같은 키로 읽는다."""
    vtm = _vtm(398, 1_668_815, None)
    eng = _engine(vtm=vtm)
    eng.strategy = Mock()
    eng.strategy.name = NAME
    vtm.describe_zero_quantity = Mock(wraps=vtm.describe_zero_quantity)
    ok, reason, _ = await _decide(eng, strategy_name="")
    vtm.describe_zero_quantity.assert_called_once_with(5_650.0, strategy_name=NAME)
    assert reason.startswith("088350 수량부족·현금부족 (")


@pytest.mark.asyncio
@pytest.mark.parametrize("describe", [
    Mock(side_effect=RuntimeError("boom")),   # 메서드 예외
    Mock(return_value=Mock()),                # Mock VTM 기본 반환(비문자열)
    Mock(return_value=None),
    Mock(return_value=""),
])
async def test_engine_falls_back_to_plain_reason(describe):
    vtm = Mock()
    vtm.get_max_quantity.return_value = 0
    vtm.describe_zero_quantity = describe
    ok, reason, info = await _decide(_engine(vtm=vtm))
    assert (ok, reason) == (False, "088350 수량부족")
    assert info == {"buy_price": 0, "quantity": 0, "max_buy_amount": 0}


@pytest.mark.asyncio
async def test_engine_real_mode_reason_unchanged():
    vtm = Mock()
    eng = _engine(virtual=False, vtm=vtm)
    eng._get_max_buy_amount = Mock(return_value=1_000.0)
    ok, reason, _ = await _decide(eng)
    assert (ok, reason) == (False, "088350 수량부족")
    vtm.describe_zero_quantity.assert_not_called()


@pytest.mark.asyncio
async def test_engine_positive_quantity_untouched():
    """I4 — qty > 0 이면 라벨 메서드를 부르지 않고 buy_info 도 그대로."""
    vtm = _vtm(10_000_000, 1_668_815, 3_000_000)
    vtm.describe_zero_quantity = Mock(wraps=vtm.describe_zero_quantity)
    ok, reason, info = await _decide(_engine(vtm=vtm))
    assert ok is True and reason == "dryup"
    assert info["quantity"] == int(1_668_815 / 5_650) and info["buy_price"] == 5_650.0
    vtm.describe_zero_quantity.assert_not_called()


# ── ④ 스로틀 키 · 연구 파서 호환 ─────────────────────────────────────────────

LABELLED = [
    "088350 수량부족·현금부족 (전략잔여 398원 · 종목당 1,668,815원 · 1주 5,650원)",
    "088350 수량부족·단가초과 (전략잔여 4,000,000원 · 종목당 435,786원 · 1주 484,000원)",
    "088350 수량부족·현금부족+단가초과 (전략잔여 100원 · 종목당 1,000원 · 1주 5,000원)",
]


def test_throttle_key_splits_by_label_and_ignores_amounts():
    from bot.trading_analyzer import format_reject_log, reject_throttle_key
    keys = [reject_throttle_key("088350", r) for r in LABELLED]
    assert keys == [("088350", "수량부족·현금부족"), ("088350", "수량부족·단가초과"),
                    ("088350", "수량부족·현금부족+단가초과")]
    other_amount = LABELLED[0].replace("398원", "1,203원")
    assert reject_throttle_key("088350", other_amount) == keys[0]
    # E4(§4-3): 라벨 붙은 줄은 「라벨 없는 수량부족」 정규식에 안 걸리고, 옛 문구는 걸린다
    assert not any(E4.search(format_reject_log("088350", r)) for r in LABELLED)
    assert E4.search(format_reject_log("088350", "088350 수량부족"))
    assert E4.search(format_reject_log("088350", "088350 수량부족") + " 외 3회")


@pytest.mark.parametrize("reason", LABELLED + ["088350 수량부족"])
def test_logscan8_reject_gate_is_still_qty(reason):
    from backtest.concept_axes.ledger8 import logscan8 as L
    text = reason.split(" ", 1)[1]              # `[매수거절] CODE 사유` 의 사유
    assert L.reject_gate(text) == L.G_QTY
    assert L.reject_gate(text + " 외 13회") == L.G_QTY

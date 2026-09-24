"""D-1 게이트 관측 번들 ⑥ — `수량부족` 스로틀 요약 「… 외 N회」.

사전등록: docs/prereg_2026-09-24_gate_observability_bundle.md §2-⑥ · §4-1 ⑥ · §10-6.

10분 스로틀(REJECT_LOG_INTERVAL) 때문에 09-21 `수량부족` 은 로그 514줄 대 실제 ≈1,023회였다.
억제된 횟수를 세어 «다음» INFO 줄 끝에 ` 외 N회` 를 붙인다(새 줄 0). 의미 = 같은 키의
직전 INFO 이후 억제 횟수. 창·억제 판정·DEBUG 줄 불변 · `수량부족` 외 사유는 접미 0.

🔑 `_should_log_reject` 는 결정당 «정확히 1회» — 부를 때마다 `_reject_log_times` 를
   갱신하므로 두 번 부르면 스스로 억제된다.

⚠️ caplog 함정(propagate=False)은 tests/bot/test_buy_rejection_visibility.py 와 같은 방식으로 푼다.
"""
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

KST = timezone(timedelta(hours=9))

QTY_CASH = "088350 수량부족·현금부족 (전략잔여 398원 · 종목당 1,668,815원 · 1주 5,650원)"
QTY_CASH_2 = "088350 수량부족·현금부족 (전략잔여 1,203원 · 종목당 1,668,815원 · 1주 5,700원)"
QTY_UNIT = "088350 수량부족·단가초과 (전략잔여 4,000,000원 · 종목당 435,786원 · 1주 484,000원)"
QTY_PLAIN = "088350 수량부족"
CRASH = "088350 시장급락 매수차단 (KOSPI -5.29%)"
NO_CONDITION = "088350 조건미충족"


def _bot(buy_signal, reason):
    bot = Mock()
    bot.trading_manager.get_stocks_by_state.return_value = []
    bot.db_manager.price_repo.get_daily_prices.return_value = pd.DataFrame(
        {"date": [f"202401{i + 1:02d}" for i in range(25)], "close": [5650] * 25})
    bot.decision_engine.set_fund_manager = Mock()
    bot.decision_engine.is_virtual_mode = True
    bot.decision_engine.analyze_buy_decision = AsyncMock(return_value=(
        buy_signal, reason,
        {"buy_price": 5650, "quantity": 10, "max_buy_amount": 56500, "signal": None}
        if buy_signal else {"buy_price": 0, "quantity": 0, "max_buy_amount": 0}))
    bot.decision_engine.execute_virtual_buy = AsyncMock(return_value=True)
    bot.fund_manager.reserve_funds.return_value = True
    bot.strategies = {}
    return bot


def _stock():
    from core.models import StockState, TradingStock
    st = TradingStock(stock_code="088350", stock_name="테스트", state=StockState.SELECTED,
                      selected_time=datetime.now(KST))
    st.is_buy_cooldown_active = Mock(return_value=False)
    st.set_buy_time = Mock()
    return st


class _Clock:
    def __init__(self, monkeypatch):
        import bot.trading_analyzer as ta
        self.base = datetime(2026, 9, 28, 10, 0, 0)
        self.now = self.base
        monkeypatch.setattr(ta, "_reject_now", lambda: self.now)


async def _decide(analyzer, caplog, reason, buy_signal=False):
    analyzer.bot = _bot(buy_signal, reason)
    analyzer.logger._logger.propagate = True
    try:
        with caplog.at_level(logging.DEBUG, logger=analyzer.logger._logger.name):
            await analyzer.analyze_buy_decision(_stock(), available_funds=1_000_000)
    finally:
        analyzer.logger._logger.propagate = False


def _analyzer():
    from bot.trading_analyzer import TradingAnalyzer
    return TradingAnalyzer(_bot(False, QTY_CASH))


def _infos(caplog):
    return [r.getMessage() for r in caplog.records
            if r.levelno == logging.INFO and "[매수거절]" in r.getMessage()]


@pytest.mark.asyncio
async def test_three_in_window_then_one_after_gives_tail_on_second_info(caplog, monkeypatch):
    """창 안 3회(INFO 1 + 억제 2) + 창 뒤 1회 → 두 번째 INFO 끝에 ` 외 2회`."""
    import bot.trading_analyzer as ta
    clock = _Clock(monkeypatch)
    an = _analyzer()
    for sec in (0, 60, 120):
        clock.now = clock.base + timedelta(seconds=sec)
        await _decide(an, caplog, QTY_CASH if sec != 60 else QTY_CASH_2)
    clock.now = clock.base + ta.REJECT_LOG_INTERVAL
    await _decide(an, caplog, QTY_CASH_2)

    assert _infos(caplog) == [
        f"[매수거절] {QTY_CASH}",
        f"[매수거절] {QTY_CASH_2} 외 2회",
    ]
    # 억제된 2건은 DEBUG 로 그대로 남는다(불변)
    debug = [r.getMessage() for r in caplog.records
             if r.levelno == logging.DEBUG and "매수 판단 결과" in r.getMessage()]
    assert len(debug) == 2
    assert an._reject_suppressed == {}


@pytest.mark.asyncio
async def test_no_tail_when_nothing_was_suppressed(caplog, monkeypatch):
    import bot.trading_analyzer as ta
    clock = _Clock(monkeypatch)
    an = _analyzer()
    await _decide(an, caplog, QTY_CASH)
    clock.now = clock.base + ta.REJECT_LOG_INTERVAL
    await _decide(an, caplog, QTY_CASH)
    assert _infos(caplog) == [f"[매수거절] {QTY_CASH}"] * 2


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [CRASH])
async def test_other_reasons_never_get_tail(reason, caplog, monkeypatch):
    """⑥ 대상은 `수량부족` 만 — 다른 사유는 억제돼도 세지 않는다."""
    import bot.trading_analyzer as ta
    clock = _Clock(monkeypatch)
    an = _analyzer()
    for sec in (0, 30, 60):
        clock.now = clock.base + timedelta(seconds=sec)
        await _decide(an, caplog, reason)
    clock.now = clock.base + ta.REJECT_LOG_INTERVAL
    await _decide(an, caplog, reason)
    assert _infos(caplog) == [f"[매수거절] {reason}"] * 2
    assert an._reject_suppressed == {}


@pytest.mark.asyncio
async def test_counters_are_per_key_label(caplog, monkeypatch):
    """④ 라벨별로 키가 갈리므로 카운터도 키별 — 서로 섞이지 않는다(옛 무라벨 문구도 수량부족)."""
    import bot.trading_analyzer as ta
    clock = _Clock(monkeypatch)
    an = _analyzer()
    seq = [QTY_CASH, QTY_UNIT, QTY_PLAIN, QTY_CASH, QTY_CASH, QTY_UNIT, QTY_PLAIN]
    for i, r in enumerate(seq):
        clock.now = clock.base + timedelta(seconds=i)
        await _decide(an, caplog, r)
    assert an._reject_suppressed == {
        ("088350", "수량부족·현금부족"): 2,
        ("088350", "수량부족·단가초과"): 1,
        ("088350", "수량부족"): 1,
    }
    caplog.clear()
    clock.now = clock.base + ta.REJECT_LOG_INTERVAL + timedelta(seconds=10)
    for r in (QTY_UNIT, QTY_CASH, QTY_PLAIN):
        await _decide(an, caplog, r)
    assert _infos(caplog) == [
        f"[매수거절] {QTY_UNIT} 외 1회",
        f"[매수거절] {QTY_CASH} 외 2회",
        f"[매수거절] {QTY_PLAIN} 외 1회",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("buy_signal,reason,expected_calls", [
    (False, QTY_CASH, 1),          # 거절 = 결정당 정확히 1회
    (False, CRASH, 1),
    (False, NO_CONDITION, 0),      # 고빈도 사유는 기존대로 스로틀 미호출
    (True, "dryup", 0),            # 매수 성공도 기존대로 미호출
])
async def test_should_log_reject_called_exactly_once_per_decision(
        buy_signal, reason, expected_calls, caplog, monkeypatch):
    _Clock(monkeypatch)
    an = _analyzer()
    real = an._should_log_reject
    an._should_log_reject = Mock(side_effect=real)
    for _ in range(3):
        an._should_log_reject.reset_mock()
        await _decide(an, caplog, reason, buy_signal=buy_signal)
        assert an._should_log_reject.call_count == expected_calls

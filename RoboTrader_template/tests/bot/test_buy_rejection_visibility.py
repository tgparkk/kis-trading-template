"""매수 거절 사유가 로그 파일(INFO)에 남는가 — 계기(instrumentation) 회귀 고정.

배경(2026-08-27): ``core/trading_decision_engine.analyze_buy_decision`` 이 돌려주는
거절 사유(진입가 밴드 하회/이탈, 수량부족, 현재가 미확보, 데이터부족, 시장급락)는
``bot/trading_analyzer.py`` 의 **DEBUG 한 줄**로만 남았다. 로그 파일 레벨은 INFO 라
***거절이 로그에 한 줄도 남지 않았다*** — 2026-08-25 「진입 밴드 거절」 조사에서
계기 부재로 확인이 불가능했던 바로 그 자리다.

예외 하나: ``조건미충족`` 은 «종목 × 틱»마다 나오는 고빈도 사유라 INFO 로 올리면
로그가 그 한 줄로 덮인다 → DEBUG 유지. 그래서 이 파일은 **대칭 단언**을 쓴다:
올라가야 하는 사유는 INFO 로 잡히고, 고빈도 사유와 매수 성공은 잡히지 않는다.

⚠️ caplog 함정: ``utils.logger.setup_logger`` 가 ``propagate=False`` 를 건다(로거는
   analyzer **생성 시점**에 만들어진다). 기존 관례
   (tests/test_bot_trading_analyzer.py:430)대로 대상 로거의 propagate 를 한시적으로
   켜서 잡는다.
"""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

KST = timezone(timedelta(hours=9))

# 엔진이 실제로 돌려주는 거절 사유 문자열(core/trading_decision_engine.py:356-429).
# 문자열 자체는 이 변경으로 건드리지 않는다 — 다른 코드/문서가 참조한다.
REASON_BAND_BELOW = "005930 진입가 밴드 하회 — 스킵 (현재가 49,000 < 하한 50,000)"
REASON_BAND_ABOVE = "005930 진입가 밴드 이탈 — 스킵 (현재가 55,000 > 상한 52,000)"
REASON_QTY = "005930 수량부족"
REASON_NO_PRICE = "005930 현재가 미확보 — 진입 보류"
REASON_DATA = "005930 데이터부족"
REASON_CRASH = "005930 시장급락 매수차단 (KOSPI -5.29%)"
REASON_NO_CONDITION = "005930 조건미충족"


def _make_daily_df(n=25):
    """일봉 DataFrame (CANDIDATE_MIN_DAILY_DATA=22 이상)"""
    return pd.DataFrame({
        "date": [f"202401{i + 1:02d}" for i in range(n)],
        "close": [50000] * n,
    })


def _make_trading_stock(stock_code="005930"):
    from core.models import StockState, TradingStock
    return TradingStock(
        stock_code=stock_code,
        stock_name="삼성전자",
        state=StockState.SELECTED,
        selected_time=datetime.now(KST),
    )


def _make_bot(buy_signal, buy_reason):
    """analyze_buy_decision 이 (buy_signal, buy_reason) 을 돌려주는 최소 bot mock."""
    bot = Mock()
    bot.trading_manager.get_stocks_by_state.return_value = []
    bot.trading_manager.get_trading_stock.return_value = None
    bot.db_manager.price_repo.get_daily_prices.return_value = _make_daily_df()

    bot.decision_engine.set_fund_manager = Mock()
    bot.decision_engine.is_virtual_mode = True
    bot.decision_engine.analyze_buy_decision = AsyncMock(
        return_value=(
            buy_signal,
            buy_reason,
            {"buy_price": 50000, "quantity": 10, "max_buy_amount": 500000,
             "signal": None} if buy_signal else
            {"buy_price": 0, "quantity": 0, "max_buy_amount": 0},
        )
    )
    bot.decision_engine.execute_virtual_buy = AsyncMock(return_value=True)

    bot.fund_manager.get_status.return_value = {
        "total_funds": 10_000_000, "available_funds": 1_000_000}
    bot.fund_manager.get_max_buy_amount.return_value = 1_000_000
    bot.fund_manager.reserve_funds.return_value = True
    bot.fund_manager.confirm_order = Mock()
    bot.fund_manager.cancel_order = Mock()
    bot.fund_manager.add_position = Mock()

    bot.intraday_manager.get_combined_chart_data.return_value = None
    bot.intraday_manager.get_cached_current_price.return_value = None
    bot.strategies = {}
    return bot


async def _run(buy_signal, buy_reason, caplog):
    """analyzer 를 만들고 매수판단을 1회 돌린 뒤 캡처된 로그 레코드를 돌려준다."""
    from bot.trading_analyzer import TradingAnalyzer

    bot = _make_bot(buy_signal, buy_reason)
    stock = _make_trading_stock()
    stock.is_buy_cooldown_active = Mock(return_value=False)
    stock.set_buy_time = Mock()

    # 로거는 __init__ 에서 만들어진다 — propagate 조작은 «생성 뒤»여야 그 인스턴스에 걸린다.
    analyzer = TradingAnalyzer(bot)
    analyzer.logger._logger.propagate = True
    try:
        with caplog.at_level(logging.DEBUG, logger=analyzer.logger._logger.name):
            await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)
    finally:
        analyzer.logger._logger.propagate = False
    return list(caplog.records)


def _reject_infos(records):
    return [r for r in records
            if r.levelno == logging.INFO and "[매수거절]" in r.getMessage()]


# ── 양성: INFO 로 올라와야 하는 거절 사유 ─────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [
    REASON_BAND_BELOW, REASON_BAND_ABOVE, REASON_QTY,
    REASON_NO_PRICE, REASON_DATA, REASON_CRASH,
])
async def test_engine_rejection_is_logged_at_info(reason, caplog):
    """엔진 거절 사유는 [매수거절] 태그와 함께 INFO 로 남아야 한다."""
    records = _reject_infos(await _run(False, reason, caplog))
    assert records, f"거절 사유가 INFO 로 안 남았다(로그 파일 레벨=INFO): {reason}"
    joined = " ".join(r.getMessage() for r in records)
    assert reason in joined, "사유 문자열이 그대로 보여야 사후 추적이 된다"
    assert "005930" in joined


@pytest.mark.asyncio
async def test_band_rejection_info_carries_stable_tag(caplog):
    """태그는 grep 가능한 고정 문자열이어야 한다 — `[매수거절] {code} {reason}`.

    엔진 사유가 이미 `"{code} ..."` 로 시작하므로 코드가 두 번 찍히면 안 된다.
    """
    records = _reject_infos(await _run(False, REASON_BAND_BELOW, caplog))
    assert len(records) == 1, "거절 한 건당 정확히 한 줄"
    assert records[0].getMessage() == f"[매수거절] {REASON_BAND_BELOW}"
    assert "005930 005930" not in records[0].getMessage()


@pytest.mark.asyncio
async def test_reason_without_stock_code_still_gets_code(caplog):
    """코드가 없는 사유(예외 경로 str(e))에도 종목코드가 붙어야 추적이 된다."""
    records = _reject_infos(await _run(False, "매수판단 오류: boom", caplog))
    assert len(records) == 1
    assert records[0].getMessage() == "[매수거절] 005930 매수판단 오류: boom"


# ── 음성: INFO 로 올리면 안 되는 경우(로그 폭발·오탐) ──────────────────────

@pytest.mark.asyncio
async def test_condition_not_met_stays_debug(caplog):
    """'조건미충족' 은 종목×틱마다 발생하는 고빈도 사유 — INFO 로 올리면 안 된다."""
    records = await _run(False, REASON_NO_CONDITION, caplog)
    assert _reject_infos(records) == [], (
        "고빈도 사유가 INFO 로 올라가면 로그가 그 한 줄로 덮인다"
    )
    # DEBUG 계기 자체는 남아 있어야 한다(조용히 사라지면 그것도 계기 손실).
    debug_msgs = [r.getMessage() for r in records if r.levelno == logging.DEBUG]
    assert any("조건미충족" in m for m in debug_msgs)


@pytest.mark.asyncio
async def test_successful_signal_emits_no_rejection_log(caplog):
    """매수 신호가 True 면 [매수거절] 은 한 줄도 없어야 한다."""
    records = await _run(True, "MA 골든크로스", caplog)
    assert _reject_infos(records) == []


# ── 스로틀: 같은 (종목, 사유) 는 10분 1회 ─────────────────────────────────
#
# 왜 마커 목록만으로는 부족한가 — 라이브 실측(2026-08-19): '시장급락 매수차단' 이
# 하루 ~2,900회 발생했다. 반대로 '조건미충족' 은 라이브에서 도달 불가다
# (TradingContext.buy 는 BUY 신호일 때만 부른다). 즉 «무엇이 폭주할지»는 사전에
# 알 수 없으므로 창 기반 스로틀이 일반해다.
# 선례: strategies/base.py:549 `_should_log_ontick` (동일 간격·동일 키 구조).

REASON_CRASH_2 = "005930 시장급락 매수차단 (KOSPI -5.31%)"


async def _run_many(reasons, caplog, stock_codes=None, analyzer=None):
    """한 analyzer 로 연속 매수판단을 돌려 (analyzer, 캡처 레코드) 를 돌려준다."""
    from bot.trading_analyzer import TradingAnalyzer

    codes = stock_codes or ["005930"] * len(reasons)
    if analyzer is None:
        analyzer = TradingAnalyzer(_make_bot(False, reasons[0]))
    analyzer.logger._logger.propagate = True
    try:
        with caplog.at_level(logging.DEBUG, logger=analyzer.logger._logger.name):
            for reason, code in zip(reasons, codes):
                bot = _make_bot(False, reason)
                analyzer.bot = bot
                stock = _make_trading_stock(code)
                stock.is_buy_cooldown_active = Mock(return_value=False)
                await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)
    finally:
        analyzer.logger._logger.propagate = False
    return analyzer, list(caplog.records)


@pytest.mark.asyncio
async def test_second_rejection_within_window_is_suppressed(caplog):
    """같은 종목·같은 사유의 두 번째 거절은 INFO 로 안 나온다."""
    _, records = await _run_many([REASON_CRASH, REASON_CRASH_2], caplog)
    assert len(_reject_infos(records)) == 1, (
        "급락게이트가 하루 2,900회 도는데 매번 INFO 면 로그가 그걸로 덮인다"
    )
    # 억제돼도 DEBUG 로는 남아야 한다(조용한 손실 금지)
    assert sum(1 for r in records
               if r.levelno == logging.DEBUG and "시장급락" in r.getMessage()) == 1


@pytest.mark.asyncio
async def test_first_occurrence_always_passes(caplog):
    """창의 «첫» 발생은 반드시 통과 — 표본이 없으면 사후에 셀 수 없다."""
    _, records = await _run_many([REASON_CRASH], caplog)
    assert len(_reject_infos(records)) == 1


@pytest.mark.asyncio
async def test_rejection_logs_again_after_window(caplog, monkeypatch):
    """10분 창이 지나면 다시 INFO 로 나온다."""
    import bot.trading_analyzer as ta

    base = datetime(2026, 8, 27, 10, 0, 0)
    clock = {"now": base}
    monkeypatch.setattr(ta, "_reject_now", lambda: clock["now"])

    analyzer, _ = await _run_many([REASON_CRASH], caplog)
    caplog.clear()

    clock["now"] = base + ta.REJECT_LOG_INTERVAL - timedelta(seconds=1)
    _, records = await _run_many([REASON_CRASH], caplog, analyzer=analyzer)
    assert _reject_infos(records) == [], "창 안이면 억제"

    caplog.clear()
    clock["now"] = base + ta.REJECT_LOG_INTERVAL
    _, records = await _run_many([REASON_CRASH], caplog, analyzer=analyzer)
    assert len(_reject_infos(records)) == 1, "창이 지나면 다시 나와야 한다"


@pytest.mark.asyncio
async def test_different_stock_is_not_suppressed(caplog):
    """스로틀은 종목별이다 — 한 종목이 다른 종목의 거절을 삼키면 안 된다."""
    _, records = await _run_many(
        ["005930 시장급락 매수차단 (KOSPI -5.29%)",
         "000660 시장급락 매수차단 (KOSPI -5.29%)"],
        caplog, stock_codes=["005930", "000660"])
    msgs = [r.getMessage() for r in _reject_infos(records)]
    assert len(msgs) == 2, msgs
    assert any("005930" in m for m in msgs) and any("000660" in m for m in msgs)


@pytest.mark.asyncio
async def test_different_reason_same_stock_is_not_suppressed(caplog):
    """같은 종목이라도 사유가 다르면 별개 — 밴드 거절이 급락 거절에 먹히면 안 된다."""
    _, records = await _run_many([REASON_CRASH, REASON_BAND_BELOW], caplog)
    assert len(_reject_infos(records)) == 2


def test_throttle_key_ignores_variable_price_part():
    """키는 «괄호 앞» 까지다 — 가격이 1틱 달라질 때마다 새 키가 되면 스로틀이 죽는다."""
    from bot.trading_analyzer import reject_throttle_key
    k1 = reject_throttle_key(
        "005930", "005930 진입가 밴드 하회 — 스킵 (현재가 49,000 < 하한 50,000)")
    k2 = reject_throttle_key(
        "005930", "005930 진입가 밴드 하회 — 스킵 (현재가 48,950 < 하한 50,000)")
    assert k1 == k2 == ("005930", "진입가 밴드 하회 — 스킵")

    k3 = reject_throttle_key("005930", "005930 시장급락 매수차단 (KOSPI -5.29%)")
    assert k3 == ("005930", "시장급락 매수차단")
    assert k3 != k1


def test_throttle_key_is_bounded_for_freeform_reasons():
    """예외 경로 str(e) 처럼 긴 자유문도 키가 무한히 커지지 않는다."""
    from bot.trading_analyzer import reject_throttle_key
    code, head = reject_throttle_key("005930", "x" * 500)
    assert code == "005930" and len(head) <= 60

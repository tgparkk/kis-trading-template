"""[재매수-shadow] 로그 (10-29 창구 묶음 A ⑤ · 동작 변화 0).

10-22 패널 「측정 먼저」: 판 종목을 다시 사는 건을 «기록만» 한다.
- 직전 매도 = 같은 종목의 가장 최근 SELL(어떤 전략이든) · 최근 5 KOSPI 거래일 안.
- 🔒 SR1: 손절 뒤 재매수는 매수가비 칸을 비운다(«-»).
- 캐시: (종목, 오늘) — 틱마다 DB 를 때리지 않는다.
- env REBUY_SHADOW=off|0|false → 조회·로그 전부 끔.
- 예외는 1회 WARNING 후 무시 — 매수 판단은 그대로 진행.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

from core.models import StockState, TradingStock

KST = timezone(timedelta(hours=9))
CODE = "458350"
DT_KEY = "daytrading_3methods_breakout"
DT_CLASS = "DayTrading3MethodsBreakoutStrategy"
RS_KEY = "rs_leader"

TODAY = date(2026, 10, 30)
# 오늘 이전 KOSPI 거래일 5개(내림차순)
TRADING_DATES = [date(2026, 10, 29), date(2026, 10, 28), date(2026, 10, 27),
                 date(2026, 10, 26), date(2026, 10, 23)]


def _sell(strategy=DT_KEY, reason="목표 익절 도달 (10.00% >= 10.00%)",
          ts=datetime(2026, 10, 28, 10, 5), price=4150.0, profit_loss=40000.0):
    return {"strategy": strategy, "reason": reason, "timestamp": ts,
            "price": price, "profit_loss": profit_loss,
            "trading_dates": list(TRADING_DATES)}


def _make_bot(last_sell=None, is_virtual=True, cached_price=4297.0):
    strat = Mock()
    strat.name = DT_CLASS
    strat.regime_index = "both"
    bot = Mock()
    bot.strategies = {DT_KEY: strat}
    bot.trading_manager.get_stocks_by_state = Mock(return_value=[])
    bot.db_manager.price_repo.get_daily_prices.return_value = pd.DataFrame(
        {"date": [f"2024{i:04d}" for i in range(30)], "close": [10000] * 30})
    bot.db_manager.trading_repo.get_last_sell_within_trading_days = Mock(return_value=last_sell)
    bot.decision_engine.is_virtual_mode = is_virtual
    bot.decision_engine.intraday_manager.get_cached_current_price = Mock(
        return_value={"current_price": cached_price} if cached_price else None)
    # 엔진은 거절을 돌려준다 — 매수 실행 경로를 타지 않게(shadow 는 엔진 호출 «전»)
    bot.decision_engine.analyze_buy_decision = AsyncMock(return_value=(False, f"{CODE} 조건미충족", {}))
    return bot


def _stock():
    return TradingStock(stock_code=CODE, stock_name="테스트", state=StockState.SELECTED,
                        selected_time=datetime.now(KST), owner_strategy_name=DT_KEY)


@pytest.fixture
def analyzer_factory(monkeypatch):
    import bot.trading_analyzer as ta
    monkeypatch.delenv("REBUY_SHADOW", raising=False)
    clock = {"now": datetime(2026, 10, 30, 9, 30, tzinfo=KST)}
    monkeypatch.setattr(ta, "_rebuy_shadow_now", lambda: clock["now"])

    def _make(bot):
        a = ta.TradingAnalyzer(bot)
        return a
    _make.clock = clock
    return _make


async def _call(analyzer, caplog, strategy_name=DT_KEY):
    analyzer.logger._logger.propagate = True
    try:
        with caplog.at_level(logging.DEBUG, logger=analyzer.logger._logger.name):
            return await analyzer.analyze_buy_decision(_stock(), strategy_name=strategy_name)
    finally:
        analyzer.logger._logger.propagate = False


def _shadow_lines(caplog):
    return [r.getMessage() for r in caplog.records if "[재매수-shadow]" in r.getMessage()]


# ---------------------------------------------------------------------------
# 순수 함수
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reason,kind", [
    ("손절 실행 (-8.11% <= -8.00%)", "손절"),
    ("손절 도달 (-3.1%)", "손절"),
    ("목표 익절 도달 (10.00% >= 10.00%)", "익절"),
    ("익절 도달 (+10.2%)", "익절"),
    ("MA20 trailing 이탈 (종가 4100 < MA20 4150)", "MA20 이탈"),
    ("MA20 이탈 (종가 4100 < MA 4150)", "MA20 이탈"),
    ("EMA20 trailing 이탈 (종가 4100 < EMA20 4150)", "EMA 이탈"),
    ("EMA65 추세반전 청산", "EMA 이탈"),
    ("보유기간 10일 초과 (한도: 10일)", "기타"),
    ("실전매매", "기타"),
    (None, "기타"),
])
def test_classify_sell_reason(reason, kind):
    from bot.trading_analyzer import classify_sell_reason
    assert classify_sell_reason(reason) == kind


def test_trading_days_ago():
    from bot.trading_analyzer import rebuy_trading_days_ago
    assert rebuy_trading_days_ago(TODAY, TODAY, TRADING_DATES) == 0
    assert rebuy_trading_days_ago(date(2026, 10, 29), TODAY, TRADING_DATES) == 1
    assert rebuy_trading_days_ago(date(2026, 10, 28), TODAY, TRADING_DATES) == 2
    assert rebuy_trading_days_ago(date(2026, 10, 23), TODAY, TRADING_DATES) == 5
    # 주말 매도(거래일 아님) → 그 뒤 첫 거래일(10-26)과 같은 차
    assert rebuy_trading_days_ago(date(2026, 10, 25), TODAY, TRADING_DATES) == 4
    assert rebuy_trading_days_ago(date(2026, 10, 26), TODAY, TRADING_DATES) == 4


def test_format_line_take_profit_has_price_ratio():
    from bot.trading_analyzer import format_rebuy_shadow_line
    line = format_rebuy_shadow_line(CODE, DT_KEY, _sell(), TODAY, buy_price=4297.0,
                                    same_strategy=True)
    assert line == (f"[재매수-shadow] {CODE} {DT_KEY} 직전매도={DT_KEY}/익절/2026-10-28 10:05 "
                    f"거래일차=2 같은전략=Y 매수가비=+3.54%")


def test_format_line_stop_loss_blanks_price_ratio_sr1():
    """🔒 SR1: 손절 뒤 재매수 → 가격 비율 칸 «-» (매도 뒤 가격을 계산하지 않는다)."""
    from bot.trading_analyzer import format_rebuy_shadow_line
    sell = _sell(reason="손절 실행 (-8.11% <= -8.00%)", profit_loss=-50000.0)
    line = format_rebuy_shadow_line(CODE, RS_KEY, sell, TODAY, buy_price=4297.0,
                                    same_strategy=False)
    assert line.endswith("같은전략=N 매수가비=-")
    assert "/손절/" in line


def test_format_line_unclassified_loss_blanks_price_ratio():
    """실전 표 reason 은 '실전매매' 뿐 — 손실 매도면 손절 여부를 모르므로 보수적으로 비운다."""
    from bot.trading_analyzer import format_rebuy_shadow_line
    sell = _sell(strategy=DT_CLASS, reason="실전매매", profit_loss=-12000.0)
    line = format_rebuy_shadow_line(CODE, DT_KEY, sell, TODAY, buy_price=4297.0,
                                    same_strategy=True)
    assert line.endswith("매수가비=-")
    assert "/기타/" in line


def test_format_line_no_buy_price_dash():
    from bot.trading_analyzer import format_rebuy_shadow_line
    line = format_rebuy_shadow_line(CODE, DT_KEY, _sell(), TODAY, buy_price=None,
                                    same_strategy=True)
    assert line.endswith("매수가비=-")


# ---------------------------------------------------------------------------
# analyze_buy_decision 통합
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shadow_line_logged_before_engine_call(analyzer_factory, caplog):
    bot = _make_bot(last_sell=_sell())
    a = analyzer_factory(bot)
    await _call(a, caplog)
    lines = _shadow_lines(caplog)
    assert lines == [f"[재매수-shadow] {CODE} {DT_KEY} 직전매도={DT_KEY}/익절/2026-10-28 10:05 "
                     f"거래일차=2 같은전략=Y 매수가비=+3.54%"]
    repo = bot.db_manager.trading_repo.get_last_sell_within_trading_days
    repo.assert_called_once()
    args, kwargs = repo.call_args
    assert args[0] == CODE and args[1] == TODAY
    assert kwargs.get("is_virtual") is True
    bot.decision_engine.analyze_buy_decision.assert_awaited_once()


@pytest.mark.asyncio
async def test_same_strategy_matches_class_name(analyzer_factory, caplog):
    """실전 표 strategy 칸은 클래스명 — 폴더키 호출과 같은 전략으로 본다."""
    bot = _make_bot(last_sell=_sell(strategy=DT_CLASS), is_virtual=False)
    a = analyzer_factory(bot)
    await _call(a, caplog)
    (line,) = _shadow_lines(caplog)
    assert "같은전략=Y" in line
    assert bot.db_manager.trading_repo.get_last_sell_within_trading_days.call_args.kwargs[
        "is_virtual"] is False


@pytest.mark.asyncio
async def test_no_recent_sell_no_log(analyzer_factory, caplog):
    bot = _make_bot(last_sell=None)
    a = analyzer_factory(bot)
    await _call(a, caplog)
    assert _shadow_lines(caplog) == []


@pytest.mark.asyncio
async def test_cache_per_code_and_day_avoids_repeat_queries(analyzer_factory, caplog):
    bot = _make_bot(last_sell=_sell())
    a = analyzer_factory(bot)
    await _call(a, caplog)
    analyzer_factory.clock["now"] += timedelta(seconds=9)
    await _call(a, caplog)
    await _call(a, caplog, strategy_name=RS_KEY)
    assert bot.db_manager.trading_repo.get_last_sell_within_trading_days.call_count == 1
    # 같은 (종목, 전략, 직전매도) 는 한 번만 — 다른 전략은 자기 줄 1개
    lines = _shadow_lines(caplog)
    assert len(lines) == 2
    assert f" {DT_KEY} 직전매도" in lines[0] and f" {RS_KEY} 직전매도" in lines[1]


@pytest.mark.asyncio
async def test_cache_refreshes_on_new_day(analyzer_factory, caplog):
    bot = _make_bot(last_sell=None)
    a = analyzer_factory(bot)
    await _call(a, caplog)
    analyzer_factory.clock["now"] += timedelta(days=1)
    await _call(a, caplog)
    assert bot.db_manager.trading_repo.get_last_sell_within_trading_days.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("val", ["off", "0", "false", "OFF"])
async def test_env_off_disables_query_and_log(analyzer_factory, caplog, monkeypatch, val):
    monkeypatch.setenv("REBUY_SHADOW", val)
    bot = _make_bot(last_sell=_sell())
    a = analyzer_factory(bot)
    await _call(a, caplog)
    bot.db_manager.trading_repo.get_last_sell_within_trading_days.assert_not_called()
    assert _shadow_lines(caplog) == []


@pytest.mark.asyncio
async def test_repo_exception_warns_once_and_buy_flow_continues(analyzer_factory, caplog):
    bot = _make_bot()
    bot.db_manager.trading_repo.get_last_sell_within_trading_days.side_effect = RuntimeError("db down")
    a = analyzer_factory(bot)
    await _call(a, caplog)
    analyzer_factory.clock["now"] += timedelta(hours=1)
    await _call(a, caplog)
    warns = [r for r in caplog.records
             if r.levelno == logging.WARNING and "[재매수-shadow]" in r.getMessage()]
    assert len(warns) == 1
    assert bot.decision_engine.analyze_buy_decision.await_count == 2


@pytest.mark.asyncio
async def test_behaviour_unchanged_with_and_without_shadow(analyzer_factory, caplog, monkeypatch):
    """동작 불변: shadow on/off 에서 엔진 호출 인자·반환이 같다."""
    results = []
    for env in ("on", "off"):
        monkeypatch.setenv("REBUY_SHADOW", env)
        bot = _make_bot(last_sell=_sell())
        bot.decision_engine.analyze_buy_decision = AsyncMock(return_value=(
            True, "돌파", {"buy_price": 4297, "quantity": 10, "max_buy_amount": 42970}))
        bot.decision_engine.execute_virtual_buy = AsyncMock(return_value=True)
        bot.fund_manager.reserve_funds.return_value = True
        a = analyzer_factory(bot)
        stock = _stock()
        executed = await a.analyze_buy_decision(stock, strategy_name=DT_KEY)
        call = bot.decision_engine.analyze_buy_decision.await_args
        results.append((executed, call.kwargs, bot.decision_engine.execute_virtual_buy.await_count))
    assert results[0] == results[1]
    assert results[0][0] is True

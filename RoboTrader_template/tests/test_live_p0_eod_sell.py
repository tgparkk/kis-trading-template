"""D3: EOD 실매도 실패는 무음이 아니라 failed_stocks 적재다 (페이퍼 브랜치와 대칭).

배경 (2026-08-14 P0 D3):
    bot/liquidation_handler.py 의 실매매 브랜치 — 본청산(execute_end_of_day_liquidation
    :305-323 부근)과 재시도(retry_failed_eod_liquidation :415-432 부근) — 는
    `await self.bot.trading_manager.execute_sell_order(...)` 의 반환값(bool)을
    버리고, `move_to_sell_candidate()` 가 True 이기만 하면 무조건 성공 로그를
    남겼다. 실매도 자체가 거부돼도(브로커 거부·잔고 부족 등) `_eod_failed_stocks`
    에 실리지 않아 재시도 체인(최대 3회)·강제완료·CRITICAL 텔레그램 알림이 전부
    발동하지 않는다 — 장 마감 후 야간 무보호 포지션이 생긴다.

    가상매매 브랜치(:289-303 본청산, :392-414 재시도)는 이미
    `execute_virtual_sell()` 의 반환값(`result`)을 검사해 실패를 `failed_stocks`/
    `still_failed` 에 적재한다 — 이 파일은 그 대칭을 실매매 브랜치에도 세운다.

fixture·속성 실명 노트 (brief 자리표시와의 차이):
    - brief 골자는 `liquidation_setup` 이라는 fixture 를 가정했지만, 이 저장소의
      청산 테스트(test_bot_liquidation.py·test_liquidation_eod_owner_pairing.py)는
      전부 pytest fixture 가 아니라 **모듈 수준 헬퍼 함수**(`_make_bot`,
      `_make_trading_stock`, `_make_handler`) 를 각 테스트 파일이 로컬로 복제해
      쓰는 관례다(교차 임포트 없음 — test_liquidation_eod_owner_pairing.py 의
      주석에도 "프로덕션 헬퍼에 의존하지 않는다" 로 명시). 이 파일도 동일 관례를
      따라 `_make_real_mode_bot`/`_make_trading_stock`/`_make_handler` 를 로컬로
      정의한다. fixture 는 쓰지 않는다.
    - `handler._eod_failed_stocks` 는 brief 자리표시와 실제 속성명이 **일치**한다
      (bot/liquidation_handler.py:54) — 이름을 바꿀 필요가 없었다.
    - 실패 항목은 (종목코드, owner) 쌍이다(다중 소유 병합 방지, 2026-07-29 감사).
      `_make_trading_stock` 이 `owner_strategy_name` 을 지정하지 않으면
      `core/models.py:169` 기본값 `""`(무기명) 이 쓰이므로, 기대값은
      `("005930", "")` 다 — test_bot_liquidation.py 의 동일 패턴과 일치.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

KST = timezone(timedelta(hours=9))


def _now():
    return datetime.now(KST)


def _make_trading_stock(stock_code="005930", avg_price=50000, quantity=10):
    from core.models import Position, StockState, TradingStock
    stock = TradingStock(
        stock_code=stock_code,
        stock_name="삼성전자",
        state=StockState.POSITIONED,
        selected_time=_now(),
    )
    stock.position = Position(stock_code=stock_code, quantity=quantity, avg_price=avg_price)
    stock.clear_position = Mock()
    stock.is_selling = False
    return stock


def _make_real_mode_bot(positioned_stocks, move_result=True, sell_order_result=True):
    """실매매(is_virtual_mode=False) 봇 mock. execute_sell_order 반환값을 제어한다."""
    bot = Mock()
    stocks = positioned_stocks

    bot.trading_manager.get_stocks_by_state.return_value = stocks

    def _get_trading_stock(code, strategy=None):
        matches = [s for s in stocks if s.stock_code == code]
        if strategy is not None:
            matches = [s for s in matches if s.owner_strategy_name == strategy]
        return matches[0] if matches else None

    bot.trading_manager.get_trading_stock.side_effect = _get_trading_stock
    bot.trading_manager.move_to_sell_candidate.return_value = move_result
    bot.trading_manager.execute_sell_order = AsyncMock(return_value=sell_order_result)
    bot.trading_manager._change_stock_state = Mock()

    # 실매매 모드 — 가상매도 경로는 타지 않아야 한다.
    bot.decision_engine.is_virtual_mode = False
    bot.decision_engine.execute_virtual_sell = AsyncMock()

    strategy = Mock()
    strategy.should_liquidate_eod.return_value = True
    bot.decision_engine.strategy = strategy

    bot.intraday_manager.get_combined_chart_data.return_value = None
    bot.broker.get_current_price.return_value = 51000

    bot.fund_manager.release_investment = Mock()
    bot.fund_manager.adjust_pnl = Mock()
    bot.fund_manager.remove_position = Mock()

    bot.telegram = None
    return bot


def _make_handler(bot):
    from bot.liquidation_handler import LiquidationHandler
    return LiquidationHandler(bot)


async def _run_eod(handler):
    with patch('bot.liquidation_handler.MarketHours') as mock_mh:
        mock_mh.get_market_hours.return_value = {
            'eod_liquidation_hour': 15,
            'eod_liquidation_minute': 20,
        }
        await handler.execute_end_of_day_liquidation()


# ---------------------------------------------------------------------------
# 본청산 — execute_end_of_day_liquidation 의 실매매 브랜치
# ---------------------------------------------------------------------------

class TestEodRealSellFailureCaptured:
    """본청산(:305-323 부근) — execute_sell_order 반환값 검사"""

    @pytest.mark.asyncio
    async def test_sell_returning_false_is_added_to_failed(self):
        """red 재현: 현행은 execute_sell_order 반환값을 버려 failed_stocks 에 안 들어간다."""
        stock = _make_trading_stock("005930")
        bot = _make_real_mode_bot([stock], move_result=True, sell_order_result=False)
        handler = _make_handler(bot)

        await _run_eod(handler)

        assert handler._eod_failed_stocks, "실매도 False 가 무음으로 사라졌다"
        assert ("005930", "") in handler._eod_failed_stocks

    @pytest.mark.asyncio
    async def test_sell_returning_true_is_not_failed(self):
        stock = _make_trading_stock("005930")
        bot = _make_real_mode_bot([stock], move_result=True, sell_order_result=True)
        handler = _make_handler(bot)

        await _run_eod(handler)

        assert not handler._eod_failed_stocks

    @pytest.mark.asyncio
    async def test_move_to_sell_candidate_failure_is_still_captured(self):
        """moved=False(매도 후보 전환 실패)도 실패 목록에 들어간다 — 회귀 고정.

        execute_sell_order 는 moved 가 False 일 때 애초에 호출되면 안 된다
        (주문 자체를 넣을 수 없는 상태이므로).
        """
        stock = _make_trading_stock("005930")
        bot = _make_real_mode_bot([stock], move_result=False, sell_order_result=True)
        handler = _make_handler(bot)

        await _run_eod(handler)

        assert ("005930", "") in handler._eod_failed_stocks
        bot.trading_manager.execute_sell_order.assert_not_called()


# ---------------------------------------------------------------------------
# 재시도 — retry_failed_eod_liquidation 의 실매매 브랜치
# ---------------------------------------------------------------------------

class TestEodRealSellRetryFailureCaptured:
    """재시도(:415-432 부근) — execute_sell_order 반환값 검사"""

    @pytest.mark.asyncio
    async def test_retry_sell_returning_false_stays_in_failed(self):
        """red 재현: 현행은 재시도 매도도 반환값을 버려 still_failed 에 안 들어간다."""
        stock = _make_trading_stock("005930")
        bot = _make_real_mode_bot([stock], move_result=True, sell_order_result=False)
        handler = _make_handler(bot)
        handler._eod_failed_stocks = {("005930", "")}
        handler._eod_retry_count = 0

        result = await handler.retry_failed_eod_liquidation()

        assert result is False
        assert ("005930", "") in handler._eod_failed_stocks

    @pytest.mark.asyncio
    async def test_retry_sell_returning_true_clears_failed(self):
        stock = _make_trading_stock("005930")
        bot = _make_real_mode_bot([stock], move_result=True, sell_order_result=True)
        handler = _make_handler(bot)
        handler._eod_failed_stocks = {("005930", "")}
        handler._eod_retry_count = 0

        result = await handler.retry_failed_eod_liquidation()

        assert result is True
        assert not handler._eod_failed_stocks

    @pytest.mark.asyncio
    async def test_retry_move_to_sell_candidate_failure_is_still_captured(self):
        """재시도에서도 moved=False 는 여전히 still_failed 에 남는다 — 회귀 고정."""
        stock = _make_trading_stock("005930")
        bot = _make_real_mode_bot([stock], move_result=False, sell_order_result=True)
        handler = _make_handler(bot)
        handler._eod_failed_stocks = {("005930", "")}
        handler._eod_retry_count = 0

        result = await handler.retry_failed_eod_liquidation()

        assert result is False
        assert ("005930", "") in handler._eod_failed_stocks
        bot.trading_manager.execute_sell_order.assert_not_called()

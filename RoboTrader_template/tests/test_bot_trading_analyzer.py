"""
TradingAnalyzer 유닛 테스트

테스트 대상: bot/trading_analyzer.py
- analyze_buy_decision: 매수 판단 (자금, 보유 여부, 쿨다운, 데이터 부족, 가상/실전 분기)
- analyze_sell_decision: 매도 판단 (가상/실전 분기, 실패 복원)
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(KST)


def _make_daily_df(n=25):
    """일봉 DataFrame (CANDIDATE_MIN_DAILY_DATA=22 이상)"""
    return pd.DataFrame({
        'date': [f'202401{i+1:02d}' for i in range(n)],
        'close': [50000] * n,
    })


def _make_trading_stock(stock_code="005930", state_name="SELECTED"):
    """TradingStock Mock 생성"""
    from core.models import TradingStock, StockState, Position
    stock = TradingStock(
        stock_code=stock_code,
        stock_name="삼성전자",
        state=StockState[state_name],
        selected_time=_now(),
    )
    return stock


def _make_positioned_stock(stock_code="005930", buy_price=50000, quantity=10):
    """포지션 있는 TradingStock"""
    from core.models import TradingStock, StockState, Position
    stock = TradingStock(
        stock_code=stock_code,
        stock_name="삼성전자",
        state=StockState.POSITIONED,
        selected_time=_now(),
    )
    stock.position = Position(
        stock_code=stock_code,
        quantity=quantity,
        avg_price=buy_price,
    )
    return stock


def _make_bot(
    daily_data=None,
    positioned_stocks=None,
    buy_cooldown=False,
    buy_signal=True,
    buy_info=None,
    is_virtual=True,
    reserve_ok=True,
    fund_status=None,
    available_funds=1_000_000,
):
    """bot Mock 조립"""
    bot = Mock()

    # TradingManager
    bot.trading_manager.get_stocks_by_state.return_value = positioned_stocks or []
    bot.trading_manager.get_trading_stock.return_value = None
    bot.trading_manager._change_stock_state = Mock()
    bot.trading_manager.move_to_sell_candidate.return_value = True

    # DB
    bot.db_manager.price_repo.get_daily_prices.return_value = (
        daily_data if daily_data is not None else _make_daily_df()
    )

    # DecisionEngine
    bot.decision_engine.set_fund_manager = Mock()
    bot.decision_engine.is_virtual_mode = is_virtual
    bot.decision_engine.analyze_buy_decision = AsyncMock(
        return_value=(
            buy_signal,
            "MA 골든크로스",
            buy_info or {
                'buy_price': 50000,
                'quantity': 10,
                'max_buy_amount': 500000,
                'signal': None,
            },
        )
    )
    bot.decision_engine.analyze_sell_decision = AsyncMock(
        return_value=(True, "손절")
    )
    bot.decision_engine.execute_virtual_buy = AsyncMock()
    bot.decision_engine.execute_virtual_sell = AsyncMock(return_value=True)
    bot.decision_engine.execute_real_buy = AsyncMock(return_value=True)
    bot.decision_engine.execute_real_sell = AsyncMock(return_value=True)

    # FundManager
    bot.fund_manager.get_status.return_value = fund_status or {
        'total_funds': 10_000_000,
        'available_funds': available_funds,
    }
    bot.fund_manager.get_max_buy_amount.return_value = available_funds
    bot.fund_manager.reserve_funds.return_value = reserve_ok
    bot.fund_manager.confirm_order = Mock()
    bot.fund_manager.cancel_order = Mock()
    bot.fund_manager.add_position = Mock()
    bot.fund_manager.release_investment = Mock()
    bot.fund_manager.adjust_pnl = Mock()
    bot.fund_manager.remove_position = Mock()

    # IntradayManager
    bot.intraday_manager.get_combined_chart_data.return_value = None
    bot.intraday_manager.get_cached_current_price.return_value = None

    return bot


def _make_analyzer(bot=None):
    """TradingAnalyzer 인스턴스 (set_fund_manager 호출 없이)"""
    from bot.trading_analyzer import TradingAnalyzer
    b = bot or _make_bot()
    # fund_manager / decision_engine attribute 보장
    if not hasattr(b, 'fund_manager'):
        b.fund_manager = Mock()
    if not hasattr(b, 'decision_engine'):
        b.decision_engine = Mock()
        b.decision_engine.set_fund_manager = Mock()
    analyzer = TradingAnalyzer(b)
    return analyzer


# ---------------------------------------------------------------------------
# analyze_buy_decision
# ---------------------------------------------------------------------------

class TestAnalyzeBuyDecision:
    """매수 판단 분석 테스트"""

    @pytest.mark.asyncio
    async def test_skips_buy_when_stock_already_positioned(self):
        """이미 보유 중인 종목에 대해 매수 신호가 와도 무시한다"""
        stock = _make_trading_stock("005930")
        positioned = _make_positioned_stock("005930")

        bot = _make_bot(positioned_stocks=[positioned])
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        # execute_virtual_buy가 호출되지 않아야 한다
        bot.decision_engine.execute_virtual_buy.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_buy_when_cooldown_is_active(self):
        """매수 쿨다운 활성화 상태에서는 매수 판단을 스킵한다"""
        stock = _make_trading_stock("005930")
        stock.is_buy_cooldown_active = Mock(return_value=True)
        stock.get_remaining_cooldown_minutes = Mock(return_value=20)

        bot = _make_bot()
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        bot.decision_engine.execute_virtual_buy.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_buy_when_daily_data_is_none(self):
        """일봉 데이터가 None이면 매수 판단을 스킵한다"""
        stock = _make_trading_stock("005930")
        bot = _make_bot(daily_data=None)
        bot.db_manager.price_repo.get_daily_prices.return_value = None
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        bot.decision_engine.execute_virtual_buy.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_buy_when_daily_data_insufficient(self):
        """일봉 데이터가 CANDIDATE_MIN_DAILY_DATA(22)보다 적으면 스킵한다"""
        stock = _make_trading_stock("005930")
        # 21개 — 최솟값(22) 미만
        bot = _make_bot(daily_data=_make_daily_df(n=21))
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        bot.decision_engine.execute_virtual_buy.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_virtual_buy_when_all_conditions_met(self):
        """모든 조건 충족 시 가상 매수 실행"""
        stock = _make_trading_stock("005930")
        stock.is_buy_cooldown_active = Mock(return_value=False)
        stock.set_buy_time = Mock()

        bot = _make_bot(is_virtual=True, buy_signal=True, reserve_ok=True)
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        bot.decision_engine.execute_virtual_buy.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_buy_when_fund_reservation_fails(self):
        """자금 예약 실패 시 매수를 스킵한다"""
        stock = _make_trading_stock("005930")
        stock.is_buy_cooldown_active = Mock(return_value=False)

        bot = _make_bot(reserve_ok=False)
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        bot.decision_engine.execute_virtual_buy.assert_not_called()

    @pytest.mark.asyncio
    async def test_adjusts_quantity_when_required_amount_exceeds_max_buy(self):
        """필요 금액이 max_buy_amount 초과 시 수량을 줄여 매수 시도한다"""
        stock = _make_trading_stock("005930")
        stock.is_buy_cooldown_active = Mock(return_value=False)
        stock.set_buy_time = Mock()

        # buy_price=50000, quantity=10 → 필요금액 500,000원
        # available_funds=300,000 → 6주만 살 수 있음
        bot = _make_bot(
            is_virtual=True,
            buy_signal=True,
            reserve_ok=True,
            available_funds=300_000,
            buy_info={
                'buy_price': 50000,
                'quantity': 10,
                'max_buy_amount': 300_000,
                'signal': None,
            },
            fund_status={'total_funds': 10_000_000, 'available_funds': 300_000},
        )
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_buy_decision(stock, available_funds=300_000)

        # 수량이 조정되어 execute_virtual_buy 호출됨
        bot.decision_engine.execute_virtual_buy.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancels_fund_reservation_when_virtual_buy_raises_exception(self):
        """가상 매수 중 예외 발생 시 자금 예약을 취소한다"""
        stock = _make_trading_stock("005930")
        stock.is_buy_cooldown_active = Mock(return_value=False)
        stock.set_buy_time = Mock()

        bot = _make_bot(is_virtual=True, reserve_ok=True)
        bot.decision_engine.execute_virtual_buy.side_effect = RuntimeError("네트워크 오류")
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        bot.fund_manager.cancel_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_executes_real_buy_in_real_mode(self):
        """실전 모드에서 execute_real_buy가 호출된다"""
        stock = _make_trading_stock("005930")
        stock.is_buy_cooldown_active = Mock(return_value=False)

        bot = _make_bot(is_virtual=False, buy_signal=True, reserve_ok=True)
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        bot.decision_engine.execute_real_buy.assert_called_once()
        bot.decision_engine.execute_virtual_buy.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancels_reservation_when_real_buy_fails(self):
        """실전 매수 실패 시 자금 예약을 취소한다"""
        stock = _make_trading_stock("005930")
        stock.is_buy_cooldown_active = Mock(return_value=False)

        bot = _make_bot(is_virtual=False, buy_signal=True, reserve_ok=True)
        bot.decision_engine.execute_real_buy.return_value = False
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        bot.fund_manager.cancel_order.assert_called_once()


# ---------------------------------------------------------------------------
# analyze_sell_decision
# ---------------------------------------------------------------------------

class TestAnalyzeSellDecision:
    """매도 판단 분석 테스트"""

    @pytest.mark.asyncio
    async def test_executes_virtual_sell_when_signal_is_true_in_virtual_mode(self):
        """가상 모드에서 매도 신호 발생 시 가상 매도가 실행된다"""
        stock = _make_positioned_stock("005930", buy_price=50000)

        bot = _make_bot(is_virtual=True)
        bot.decision_engine.analyze_sell_decision.return_value = (True, "손절")
        bot.decision_engine.execute_virtual_sell.return_value = True
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_sell_decision(stock)

        bot.decision_engine.execute_virtual_sell.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_sell_when_signal_is_false(self):
        """매도 신호가 False이면 매도를 실행하지 않는다"""
        stock = _make_positioned_stock("005930")

        bot = _make_bot(is_virtual=True)
        bot.decision_engine.analyze_sell_decision.return_value = (False, "홀드")
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_sell_decision(stock)

        bot.decision_engine.execute_virtual_sell.assert_not_called()

    @pytest.mark.asyncio
    async def test_restores_positioned_state_when_virtual_sell_fails(self):
        """가상 매도 실패 시 POSITIONED 상태로 복원한다"""
        from core.models import StockState
        stock = _make_positioned_stock("005930")

        bot = _make_bot(is_virtual=True)
        bot.decision_engine.analyze_sell_decision.return_value = (True, "손절")
        bot.decision_engine.execute_virtual_sell.return_value = False
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_sell_decision(stock)

        # POSITIONED로 복원 호출 확인
        bot.trading_manager._change_stock_state.assert_called_once_with(
            "005930", StockState.POSITIONED, "가상 매도 실패 복원"
        )

    @pytest.mark.asyncio
    async def test_executes_real_sell_in_real_mode(self):
        """실전 모드에서 execute_real_sell이 호출된다"""
        stock = _make_positioned_stock("005930")

        bot = _make_bot(is_virtual=False)
        bot.decision_engine.analyze_sell_decision.return_value = (True, "익절")
        bot.decision_engine.execute_real_sell.return_value = True
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_sell_decision(stock)

        bot.decision_engine.execute_real_sell.assert_called_once()
        bot.decision_engine.execute_virtual_sell.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_current_price_from_intraday_manager_for_virtual_sell(self):
        """가상 매도 시 intraday_manager의 현재가를 매도가로 사용한다"""
        stock = _make_positioned_stock("005930", buy_price=50000)

        bot = _make_bot(is_virtual=True)
        bot.decision_engine.analyze_sell_decision.return_value = (True, "손절")
        bot.decision_engine.execute_virtual_sell.return_value = True
        bot.intraday_manager.get_cached_current_price.return_value = {
            'current_price': 48000
        }
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_sell_decision(stock)

        call_args = bot.decision_engine.execute_virtual_sell.call_args
        # 두 번째 인자(sell_price)가 현재가 48000이어야 함
        assert call_args[0][1] == 48000.0

    @pytest.mark.asyncio
    async def test_does_not_raise_when_outer_exception_occurs(self):
        """외부 예외 발생 시 예외를 전파하지 않고 로깅만 한다"""
        stock = _make_positioned_stock("005930")

        bot = _make_bot(is_virtual=True)
        bot.decision_engine.analyze_sell_decision.side_effect = RuntimeError("비정상 오류")
        analyzer = _make_analyzer(bot)

        # 예외가 전파되지 않아야 한다
        await analyzer.analyze_sell_decision(stock)

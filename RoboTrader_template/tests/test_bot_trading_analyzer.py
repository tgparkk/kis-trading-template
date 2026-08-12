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
    async def test_forwards_owner_signal_to_decision_engine(self):
        """on_tick이 넘긴 전략 신호를 decision_engine 매수판단에 owner_signal로 전달한다.

        2026-06-09 ④ 수정: 미전달 시 decision_engine이 단일 고정전략(Elder)으로
        재판정 → 6/7 전략 매수 불가. 호출 전략의 signal을 반드시 전달해야 한다.
        """
        from unittest.mock import MagicMock
        stock = _make_trading_stock("005930")
        stock.is_buy_cooldown_active = Mock(return_value=False)
        bot = _make_bot(buy_signal=False)  # 결과 무관, 전달 인자만 검증
        analyzer = _make_analyzer(bot)
        sig = MagicMock()

        await analyzer.analyze_buy_decision(stock, available_funds=1_000_000, signal=sig)

        _, kwargs = bot.decision_engine.analyze_buy_decision.call_args
        assert kwargs.get("owner_signal") is sig, "owner_signal로 전략 신호를 전달해야 함"

    # ── 반환값: 실제 체결 여부 (2026-06-09 쿨다운 무조건 갱신 버그 수정) ──────────
    @pytest.mark.asyncio
    async def test_returns_true_on_successful_virtual_buy(self):
        """가상 매수가 실제 체결되면 True를 반환한다 (호출자 쿨다운 무장 판단용)."""
        stock = _make_trading_stock("005930")
        stock.is_buy_cooldown_active = Mock(return_value=False)
        stock.set_buy_time = Mock()

        bot = _make_bot(is_virtual=True, buy_signal=True, reserve_ok=True)
        analyzer = _make_analyzer(bot)

        result = await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_already_positioned(self):
        """이미 보유 중이라 매수를 스킵하면 False(거부)를 반환한다."""
        stock = _make_trading_stock("005930")
        positioned = _make_positioned_stock("005930")
        bot = _make_bot(positioned_stocks=[positioned])
        analyzer = _make_analyzer(bot)

        result = await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        assert not result

    @pytest.mark.asyncio
    async def test_returns_false_when_fund_reservation_fails(self):
        """자금 예약 실패로 체결 못하면 False를 반환한다 (쿨다운 무장 금지)."""
        stock = _make_trading_stock("005930")
        stock.is_buy_cooldown_active = Mock(return_value=False)
        bot = _make_bot(reserve_ok=False)
        analyzer = _make_analyzer(bot)

        result = await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        assert not result

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

        # POSITIONED로 복원 호출 확인 (owner 전략 배선: strategy 키워드 전달)
        bot.trading_manager._change_stock_state.assert_called_once_with(
            "005930", StockState.POSITIONED, "가상 매도 실패 복원", strategy=""
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
    async def test_does_not_fall_back_to_avg_price_when_cache_has_no_price(self):
        """캐시 미스 시 원가(avg_price)로 매도하지 않고 falsy 값을 전달해
        execute_virtual_sell 자체 폴백 체인(캐시→브로커→거부)이 돌게 한다.

        2026-08-12: intraday_manager 캐시는 구조적으로 항상 비어 있다
        (rebalancing_mode=true 라 유일한 writer 가 호출되지 않음). 종전 코드는
        sell_price 를 avg_price 로 미리 채워 execute_virtual_sell 의 자체 가드
        (`not sell_price or sell_price <= 0`)를 무력화 → 매수가로 매도되어
        실현손익이 항상 0으로 왜곡됐다.
        """
        stock = _make_positioned_stock("005930", buy_price=50000)

        bot = _make_bot(is_virtual=True)
        bot.decision_engine.analyze_sell_decision.return_value = (True, "손절")
        bot.decision_engine.execute_virtual_sell.return_value = True
        bot.intraday_manager.get_cached_current_price.return_value = None  # 캐시 미스 (상시)
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_sell_decision(stock)

        call_args = bot.decision_engine.execute_virtual_sell.call_args
        sell_price = call_args[0][1]
        assert sell_price != stock.position.avg_price, (
            "원가(avg_price)를 매도가로 전달하면 손익이 0%로 왜곡된다"
        )
        assert not sell_price, (
            "캐시 미스 시 falsy 값을 넘겨 execute_virtual_sell 자체 폴백 체인이 실행돼야 한다"
        )

    @pytest.mark.asyncio
    async def test_does_not_raise_when_outer_exception_occurs(self):
        """외부 예외 발생 시 예외를 전파하지 않고 로깅만 한다"""
        stock = _make_positioned_stock("005930")

        bot = _make_bot(is_virtual=True)
        bot.decision_engine.analyze_sell_decision.side_effect = RuntimeError("비정상 오류")
        analyzer = _make_analyzer(bot)

        # 예외가 전파되지 않아야 한다
        await analyzer.analyze_sell_decision(stock)


# ---------------------------------------------------------------------------
# analyze_sell_decision — Signal 전달 (D2: 매도신호 패스스루)
# ---------------------------------------------------------------------------

class TestAnalyzeSellDecisionWithSignal:
    """전략이 일봉으로 이미 내린 매도 결정을 signal 인자로 전달하는 경로.

    combined_data(1분봉)는 rebalancing_mode=true라 구조적으로 항상 None —
    이 상태에서 decision_engine.analyze_sell_decision을 거치면 영구 False가
    되어(트리거 3,727회 vs 매도패스스루 로그 0회) 매도가 실행되지 않았다.
    """

    @pytest.mark.asyncio
    async def test_sell_executes_when_combined_data_none_but_sell_signal_supplied(self):
        """combined_data=None(프로덕션 실측) + SELL Signal 공급 → 매도가 실행된다.

        decision_engine.analyze_sell_decision은 재판단하지 않고(호출 안 됨),
        Signal의 결정을 그대로 신뢰해 가상 매도 경로가 실행돼야 한다.
        """
        from strategies.base import Signal, SignalType

        stock = _make_positioned_stock("005930", buy_price=50000)
        bot = _make_bot(is_virtual=True)
        bot.intraday_manager.get_combined_chart_data.return_value = None  # 구조적 None
        bot.decision_engine.execute_virtual_sell.return_value = True
        analyzer = _make_analyzer(bot)

        sell_signal = Signal(
            signal_type=SignalType.SELL,
            stock_code="005930",
            reasons=["MA20 이탈"],
        )

        await analyzer.analyze_sell_decision(stock, signal=sell_signal)

        bot.decision_engine.execute_virtual_sell.assert_called_once()
        bot.decision_engine.analyze_sell_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_sell_when_combined_data_none_and_no_signal(self):
        """combined_data=None인 동일 조건에서 Signal 미공급 시 매도가 실행되지
        않는다 (기존 결함 재현 — 위 테스트와 대칭시켜 신호 유무만이 결과를
        가른다는 것을 증명한다).
        """
        stock = _make_positioned_stock("005930", buy_price=50000)
        bot = _make_bot(is_virtual=True)
        bot.intraday_manager.get_combined_chart_data.return_value = None
        # combined_data=None일 때 decision_engine.analyze_sell_decision의
        # 실제 게이트(core/trading_decision_engine.py:458)는 항상 False를 반환한다.
        bot.decision_engine.analyze_sell_decision.return_value = (False, "")
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_sell_decision(stock)  # signal 미전달

        bot.decision_engine.execute_virtual_sell.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_sell_when_signal_is_buy_type(self):
        """매수성 Signal(BUY)이 매도 경로에 들어와도 매도를 유발해선 안 된다."""
        from strategies.base import Signal, SignalType

        stock = _make_positioned_stock("005930", buy_price=50000)
        bot = _make_bot(is_virtual=True)
        bot.intraday_manager.get_combined_chart_data.return_value = None
        analyzer = _make_analyzer(bot)

        buy_signal = Signal(
            signal_type=SignalType.BUY,
            stock_code="005930",
            reasons=["오신호"],
        )

        await analyzer.analyze_sell_decision(stock, signal=buy_signal)

        bot.decision_engine.execute_virtual_sell.assert_not_called()
        bot.decision_engine.analyze_sell_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_sell_reason_built_from_signal_reasons(self):
        """Signal.reasons가 있으면 sell_reason은 그 reasons를 조합한 문자열이다."""
        from strategies.base import Signal, SignalType

        stock = _make_positioned_stock("005930", buy_price=50000)
        bot = _make_bot(is_virtual=True)
        bot.intraday_manager.get_combined_chart_data.return_value = None
        bot.decision_engine.execute_virtual_sell.return_value = True
        analyzer = _make_analyzer(bot)

        sell_signal = Signal(
            signal_type=SignalType.SELL,
            stock_code="005930",
            reasons=["MA20 이탈", "RSI 과매수"],
        )

        await analyzer.analyze_sell_decision(stock, signal=sell_signal)

        call_args = bot.decision_engine.execute_virtual_sell.call_args
        sell_reason = call_args[0][2]
        assert sell_reason == "MA20 이탈, RSI 과매수"


# ---------------------------------------------------------------------------
# BaseStrategy.on_tick — 매도신호 발생 시 ctx.sell에 signal 전달 (D2)
# ---------------------------------------------------------------------------

class TestOnTickPassesSellSignal:
    """strategies/base.py:687 — on_tick이 SELL Signal 발생 시 ctx.sell을
    signal= 키워드와 함께 호출해야 한다(기존에는 reason만 전달돼 신호가
    소실됐다 — ctx.sell이 **kwargs를 받아 조용히 삼켰다)."""

    @pytest.mark.asyncio
    async def test_ontick_calls_ctx_sell_with_non_none_signal(self):
        from strategies.base import BaseStrategy, Signal, SignalType

        class _SellStrategy(BaseStrategy):
            name = "SellTestStrategy"
            version = "1.0.0"
            exit_timeframe = "daily"  # 일봉 기준 매도판단(D2 결함 재현 시나리오)

            def get_min_data_length(self):
                return 1

            def generate_signal(self, stock_code, data, timeframe="daily"):
                return Signal(
                    signal_type=SignalType.SELL,
                    stock_code=stock_code,
                    reasons=["MA20 이탈"],
                )

        strategy = _SellStrategy({})

        pos = MagicMock()
        pos.stock_code = "005930"

        ctx = MagicMock()
        ctx.tracer = None
        ctx.get_selected_stocks.return_value = []
        ctx.get_positions.return_value = [pos]

        async def _get_daily(code, days=60):
            return _make_daily_df(30)

        ctx.get_daily_data = _get_daily
        ctx.sell = AsyncMock(return_value="005930")

        await strategy.on_tick(ctx)

        ctx.sell.assert_awaited_once()
        _, call_kwargs = ctx.sell.call_args
        assert call_kwargs.get("signal") is not None, (
            f"ctx.sell이 signal 없이 호출됨: {ctx.sell.call_args}"
        )
        assert call_kwargs["signal"].signal_type == SignalType.SELL


class TestLiveBuyFundReservationKey:
    """실전 매수 자금 예약 키 정합 (사전-실전 감사 BLOCKER #7, 2026-06-24).

    place_buy_order 의 H4 중복방지는 has_reservation(stock_code)(맨 종목코드)를
    확인한다. 그러나 분석기가 _reserve_id = f"{code}_{timestamp}" 로 예약하면
    키가 어긋나 place_buy_order 가 2차 예약을 생성하고, 1차(_reserve_id)는
    체결 확인 경로(OrderMonitor=2차만 확정)서 영영 해제되지 않아 reserved_funds
    가 매수마다 영구 누수 → 몇 건 후 '자금부족'으로 인스턴스 매수 정지.
    예약 키를 맨 stock_code 로 정렬해 2차 예약 자체가 안 생기게 한다.
    """

    @pytest.mark.asyncio
    async def test_live_buy_reserves_under_bare_stock_code(self):
        stock = _make_trading_stock("005930")
        stock.is_buy_cooldown_active = Mock(return_value=False)
        stock.set_buy_time = Mock()
        bot = _make_bot(is_virtual=False, reserve_ok=True)
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        bot.fund_manager.reserve_funds.assert_called_once()
        reserved_key = bot.fund_manager.reserve_funds.call_args[0][0]
        # place_buy_order 의 has_reservation(stock_code) 가 감지하도록 키 = 맨 종목코드
        assert reserved_key == "005930"

    @pytest.mark.asyncio
    async def test_live_buy_failure_cancels_same_reservation_key(self):
        """실전 매수 실패 시 예약했던 것과 동일한 키로 취소한다(누수·오취소 방지)."""
        stock = _make_trading_stock("005930")
        stock.is_buy_cooldown_active = Mock(return_value=False)
        stock.set_buy_time = Mock()
        bot = _make_bot(is_virtual=False, reserve_ok=True)
        bot.decision_engine.execute_real_buy = AsyncMock(return_value=False)
        analyzer = _make_analyzer(bot)

        await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        reserved_key = bot.fund_manager.reserve_funds.call_args[0][0]
        bot.fund_manager.cancel_order.assert_called_once_with(reserved_key)

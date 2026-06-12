"""
다중전략 체결 파이프라인 수정 테스트 (2026-06-11 진단)

근본원인(라이브 로그 + virtual_trading_records 포렌식):
1. 유령 체결 — trading_analyzer가 execute_virtual_buy 성공 여부를 확인하지 않고
   무조건 confirm_order → VTM이 "전략 가상 잔고 부족"으로 거부해도 FundManager
   invested에 확정(06-11 하루 7건 ≈ 43.3M 오염, EOD 정합성 CRITICAL 원인).
2. 잔편 매수 — decision_engine.analyze_buy_decision이 전략 원장 대신 FundManager
   집계(총자금 9%/90% 한도)로 수량을 재계산 → 유령 invested로 capacity 붕괴 시
   1~10주 체결(06-11 9건). 전략 원장(VTM)이 수량 산정의 SSOT여야 한다.
3. 콜백 오귀속 — 체결 통보가 소유 전략이 아닌 엔진 고정 self.strategy(=Elder)로만
   전달 → Elder daily_trades가 타전략 체결로 오염 → max_daily_trades=5 도달로
   매일 09시 초반 Elder 매수 마비.
4. A안(균등 K분할) — 종목당 기본 예산 = 전략 초기자본 / max_positions
   (백테스트 균등복리 K분할 정합). yaml paper_investment_per_stock이 우선.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock

KST = timezone(timedelta(hours=9))


def _now():
    return datetime.now(KST)


def _make_daily_df(n=25, close=50000):
    return pd.DataFrame({
        'date': [f'202401{i+1:02d}' for i in range(n)],
        'close': [close] * n,
    })


def _make_trading_stock(stock_code="005930", state_name="SELECTED"):
    from core.models import TradingStock, StockState
    return TradingStock(
        stock_code=stock_code,
        stock_name="테스트종목",
        state=StockState[state_name],
        selected_time=_now(),
    )


def _make_bot(buy_info=None, is_virtual=True, available_funds=1_000_000):
    """bot Mock (tests/test_bot_trading_analyzer.py 패턴 축약)"""
    bot = Mock()
    bot.trading_manager.get_stocks_by_state.return_value = []
    bot.trading_manager.get_trading_stock.return_value = None
    bot.trading_manager._change_stock_state = Mock()
    bot.db_manager.price_repo.get_daily_prices.return_value = _make_daily_df()
    bot.strategies = {}

    bot.decision_engine.set_fund_manager = Mock()
    bot.decision_engine.is_virtual_mode = is_virtual
    bot.decision_engine.analyze_buy_decision = AsyncMock(
        return_value=(
            True,
            "테스트 매수신호",
            buy_info or {'buy_price': 50000, 'quantity': 10,
                         'max_buy_amount': 500000, 'signal': None},
        )
    )
    bot.decision_engine.execute_virtual_buy = AsyncMock(return_value=True)
    bot.decision_engine.execute_real_buy = AsyncMock(return_value=True)

    bot.fund_manager.get_status.return_value = {
        'total_funds': 10_000_000, 'available_funds': available_funds,
    }
    bot.fund_manager.get_max_buy_amount.return_value = available_funds
    bot.fund_manager.reserve_funds.return_value = True
    bot.fund_manager.confirm_order = Mock()
    bot.fund_manager.cancel_order = Mock()
    bot.fund_manager.add_position = Mock()

    bot.intraday_manager.get_cached_current_price.return_value = None
    return bot


def _make_analyzer(bot):
    from bot.trading_analyzer import TradingAnalyzer
    return TradingAnalyzer(bot)


def _make_engine():
    """가상모드 실엔진 (db/broker 없이)"""
    from core.trading_decision_engine import TradingDecisionEngine
    return TradingDecisionEngine(config=None)  # config None → is_virtual_mode=True


def _make_buy_signal(stock_code="005930", price=6810):
    from strategies.base import Signal, SignalType
    return Signal(
        signal_type=SignalType.BUY, stock_code=stock_code, confidence=60.0,
        target_price=price * 1.06, stop_loss=price * 0.92, reasons=["테스트룰"],
    )


# ---------------------------------------------------------------------------
# 1. 유령 체결 차단 (trading_analyzer)
# ---------------------------------------------------------------------------

class TestGhostFillPrevention:
    @pytest.mark.asyncio
    async def test_rejected_virtual_buy_cancels_reservation_without_confirm(self):
        """VTM 거부(False) 시: confirm_order 미호출 + 예약 취소 + 상태 비전이."""
        bot = _make_bot()
        bot.decision_engine.execute_virtual_buy = AsyncMock(return_value=False)
        analyzer = _make_analyzer(bot)
        stock = _make_trading_stock()

        result = await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        bot.fund_manager.confirm_order.assert_not_called()
        bot.fund_manager.add_position.assert_not_called()
        bot.fund_manager.cancel_order.assert_called_once()
        bot.trading_manager._change_stock_state.assert_not_called()
        assert not result

    @pytest.mark.asyncio
    async def test_successful_virtual_buy_confirms_funds(self):
        """성공(True) 시: 기존대로 confirm_order + 상태 전이."""
        bot = _make_bot()
        bot.decision_engine.execute_virtual_buy = AsyncMock(return_value=True)
        analyzer = _make_analyzer(bot)
        stock = _make_trading_stock()

        result = await analyzer.analyze_buy_decision(stock, available_funds=1_000_000)

        bot.fund_manager.confirm_order.assert_called_once()
        bot.fund_manager.cancel_order.assert_not_called()
        assert result is True


# ---------------------------------------------------------------------------
# 2. 원장 기준 사이징 (잔편 매수 차단)
# ---------------------------------------------------------------------------

class TestLedgerBasedSizing:
    @pytest.mark.asyncio
    async def test_virtual_mode_does_not_downsize_by_fund_manager(self):
        """가상모드: FM 집계 가용이 잔편 수준이어도 수량 재조정(2주化) 금지."""
        bot = _make_bot(buy_info={'buy_price': 6810, 'quantity': 440,
                                  'max_buy_amount': 2_996_400, 'signal': None})
        bot.fund_manager.get_max_buy_amount.return_value = 15_000  # 붕괴된 집계
        analyzer = _make_analyzer(bot)
        stock = _make_trading_stock()

        await analyzer.analyze_buy_decision(stock)  # available_funds=None 경로

        bot.decision_engine.execute_virtual_buy.assert_called_once()
        _, kwargs = bot.decision_engine.execute_virtual_buy.call_args
        assert kwargs['quantity'] == 440  # 원장 산정 수량 유지 (현행: 2주로 붕괴)

    @pytest.mark.asyncio
    async def test_analyzer_threads_strategy_name_to_engine(self):
        """analyzer → engine.analyze_buy_decision에 strategy_name 전달."""
        bot = _make_bot()
        analyzer = _make_analyzer(bot)
        stock = _make_trading_stock()

        await analyzer.analyze_buy_decision(
            stock, available_funds=1_000_000, strategy_name="rs_leader")

        _, kwargs = bot.decision_engine.analyze_buy_decision.call_args
        assert kwargs.get('strategy_name') == "rs_leader"

    @pytest.mark.asyncio
    async def test_engine_virtual_sizing_uses_strategy_ledger(self):
        """엔진 가상모드 수량 = VTM.get_max_quantity(전략 원장), FM 집계 미사용."""
        engine = _make_engine()
        engine.virtual_trading = Mock()
        engine.virtual_trading.get_max_quantity = Mock(return_value=440)
        fm = Mock()
        fm.get_max_buy_amount = Mock(return_value=6_300_000)
        engine.set_fund_manager(fm)

        stock = _make_trading_stock()
        sig = _make_buy_signal()
        df = _make_daily_df(n=25, close=6810)

        ok, _reason, buy_info = await engine.analyze_buy_decision(
            stock, df, regime_index="none", owner_signal=sig,
            strategy_name="rs_leader")

        assert ok is True
        assert buy_info['quantity'] == 440
        engine.virtual_trading.get_max_quantity.assert_called_once()
        _args, _kwargs = engine.virtual_trading.get_max_quantity.call_args
        assert _kwargs.get('strategy_name') == "rs_leader"
        fm.get_max_buy_amount.assert_not_called()


# ---------------------------------------------------------------------------
# 3. 체결 콜백 owner 라우팅 (Elder 오염 차단)
# ---------------------------------------------------------------------------

class TestOwnerCallbackRouting:
    def _owner_and_elder(self, engine):
        elder = Mock()
        elder.name = "ElderEmaPullbackStrategy"
        owner = Mock()
        owner.name = "RSLeaderStrategy"
        engine.set_strategy(elder)
        engine.set_strategies({"rs_leader": owner})
        return owner, elder

    @pytest.mark.asyncio
    async def test_buy_fill_notifies_owner_not_default_strategy(self):
        engine = _make_engine()
        owner, elder = self._owner_and_elder(engine)
        engine.virtual_trading = Mock()
        engine.virtual_trading.execute_virtual_buy = Mock(return_value=123)
        stock = _make_trading_stock()

        ok = await engine.execute_virtual_buy(
            stock, None, "테스트 매수",
            buy_price=10_000, quantity=10,
            target_profit_rate=0.06, stop_loss_rate=0.05,
            strategy_name="rs_leader")

        assert ok is True
        assert owner.on_order_filled.call_count == 1
        elder.on_order_filled.assert_not_called()
        assert stock.owner_strategy is owner
        assert stock.owner_strategy_name == "RSLeaderStrategy"

    @pytest.mark.asyncio
    async def test_rejected_buy_returns_false_and_no_callback(self):
        """VTM 거부(rid=None) → False 반환 + 어느 전략에도 콜백 없음."""
        engine = _make_engine()
        owner, elder = self._owner_and_elder(engine)
        engine.virtual_trading = Mock()
        engine.virtual_trading.execute_virtual_buy = Mock(return_value=None)
        stock = _make_trading_stock()

        ok = await engine.execute_virtual_buy(
            stock, None, "테스트 매수",
            buy_price=10_000, quantity=10,
            target_profit_rate=0.06, stop_loss_rate=0.05,
            strategy_name="rs_leader")

        assert ok is False
        owner.on_order_filled.assert_not_called()
        elder.on_order_filled.assert_not_called()

    @pytest.mark.asyncio
    async def test_sell_fill_notifies_owner_not_default_strategy(self):
        engine = _make_engine()
        owner, elder = self._owner_and_elder(engine)
        engine.virtual_trading = Mock()
        engine.virtual_trading.execute_virtual_sell = Mock(return_value=True)
        stock = _make_trading_stock(state_name="POSITIONED")
        stock.set_virtual_buy_info(123, 10_000, 10)
        stock.strategy_name = "rs_leader"

        ok = await engine.execute_virtual_sell(stock, 11_000, "익절")

        assert ok is True
        assert owner.on_order_filled.call_count == 1
        elder.on_order_filled.assert_not_called()


# ---------------------------------------------------------------------------
# 4. A안 — 종목당 기본 예산 = 초기자본 / max_positions
# ---------------------------------------------------------------------------

class TestEqualSlotBudget:
    def _vtm(self):
        from core.virtual_trading_manager import VirtualTradingManager
        return VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)

    def test_allocate_with_max_positions_sets_slot_budget(self):
        """allocate(1천만, K=20) → 종목당 50만 → 1만원 종목 50주."""
        vtm = self._vtm()
        vtm.allocate_strategy_capital("elder_ema_pullback", 10_000_000,
                                      max_positions=20)
        assert vtm.get_max_quantity(10_000, strategy_name="elder_ema_pullback") == 50

    def test_yaml_per_stock_override_wins_over_slot_budget(self):
        """yaml paper_investment_per_stock(이후 호출)이 K분할 기본값을 덮어씀."""
        vtm = self._vtm()
        vtm.allocate_strategy_capital("deep_mr_dev20", 10_000_000, max_positions=20)
        vtm.set_strategy_investment_amount("deep_mr_dev20", 2_000_000)
        assert vtm.get_max_quantity(10_000, strategy_name="deep_mr_dev20") == 200


# ---------------------------------------------------------------------------
# 5. K분할 라이프사이클 (2026-06-12 진단) — 할당은 DayTradingBot.__init__,
#    _max_positions는 각 전략 on_init()에서 설정 → getattr가 항상 None
#    → 균등 K분할 전면 미적용(06-12 라이브: 전 전략 기본 1M/종목 체결 역산).
#    yaml config의 risk_management.max_positions를 직접 읽어야 한다.
# ---------------------------------------------------------------------------

class TestAllocationLifecycle:
    def _run_allocation(self, strategies):
        import tests._mock_modules  # noqa: F401 — telegram 등 외부모듈 스텁 (main import 전)
        import main
        from types import SimpleNamespace
        from core.virtual_trading_manager import VirtualTradingManager
        vtm = VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)
        bot = SimpleNamespace(
            decision_engine=SimpleNamespace(virtual_trading=vtm, is_virtual_mode=True),
            strategies=strategies,
            logger=Mock(),
        )
        main.DayTradingBot._allocate_strategy_capital(bot)
        return vtm

    def test_k_split_from_config_before_on_init(self):
        """on_init 이전(_max_positions 속성 부재)에도 yaml K로 균등분할 적용."""
        from types import SimpleNamespace
        strat = SimpleNamespace(config={"risk_management": {"max_positions": 20}})
        assert not hasattr(strat, "_max_positions")  # on_init 이전 상태 재현
        vtm = self._run_allocation({"elder_ema_pullback": strat})
        # 10M / K20 = 50만 → 1만원 종목 50주 (버그 시 기본 1M → 100주)
        assert vtm.get_max_quantity(10_000, strategy_name="elder_ema_pullback") == 50

    def test_yaml_per_stock_still_overrides_k_split(self):
        """paper_investment_per_stock 명시 전략(deep_mr_dev20)은 K분할보다 우선 유지."""
        from types import SimpleNamespace
        strat = SimpleNamespace(config={"risk_management": {
            "max_positions": 5, "paper_investment_per_stock": 2_000_000}})
        vtm = self._run_allocation({"deep_mr_dev20": strat})
        assert vtm.get_max_quantity(10_000, strategy_name="deep_mr_dev20") == 200

    def test_missing_max_positions_no_k_split(self):
        """yaml에 max_positions 없으면 K분할 미적용(기본 종목당 투자금 유지·무예외)."""
        from types import SimpleNamespace
        strat = SimpleNamespace(config={"risk_management": {}})
        vtm = self._run_allocation({"legacy": strat})
        assert vtm._strategy_investment_amounts.get("legacy") is None

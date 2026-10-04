"""실전 주문·종료·복원 경로 결함 6건 수정 — 회귀 고정 (2026-10-04).

근거: `docs/audit_2026-10-04_real_daytrading_flow.md` · 검수 CRITIC_verify §2 최소 수정 집합.
대상: NEW-B1 · NEW-C1 · NEW-B3(+P1-6) · NEW-B2 · NEW-C2 · NEW-A1.

원칙: **페이퍼 8전략 동작 0 변경.** 각 수정은 실전 전용 호출 경로(execute_real_* ·
실브로커 · 실전 복원)거나, 페이퍼에서 도달하지 않는 분기(텔레그램 disabled)에만 있다.
KIS·네트워크·DB 에 닿지 않는다 — 전부 페이크/모의 객체. 공허 통과를 막기 위해
페이크가 «실제로 불렸는지» 를 함께 단언한다.
"""
import sys
import types
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mock_modules  # noqa: F401,E402

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from core.models import Order, OrderStatus, OrderType, StockState, TradingConfig, TradingStock  # noqa: E402
from utils.korean_time import now_kst  # noqa: E402

DT_KEY = "daytrading_3methods_breakout"


# =============================================================================
# 공통 헬퍼
# =============================================================================
def _api_pkg():
    """broker 가 `from api import kis_order_api` 로 «패키지 속성» 을 읽으므로 거기를 바꾼다.

    다른 테스트가 sys.modules['api'] 를 교체해 두는 경우가 있어(dryrun 등) 모듈 경로
    문자열 patch 는 broker 가 실제로 쓰는 객체를 못 맞출 수 있다 — 지금 시점의
    sys.modules 엔트리에 직접 붙인다.
    """
    import api  # noqa: F401
    return sys.modules["api"]


def _fake_order_api(**fns):
    mod = types.SimpleNamespace()
    for name, fn in fns.items():
        setattr(mod, name, fn)
    return mod


def _connected_broker():
    from framework.broker import KISBroker
    b = KISBroker()
    b._connected = True
    return b


def _pending_df(odno="0000012345", code="005930"):
    return pd.DataFrame([{
        "odno": odno, "pdno": code, "krx_fwdg_ord_orgno": "06010",
        "ord_qty": "10", "tot_ccld_qty": "3", "psbl_qty": "7",
    }])


def _cancel_ok_df(new_odno="0010239000"):
    # 실측 형태(형제 레포 로그): body.output 만 담긴 행 — rt_cd·msg1 은 없다.
    return pd.DataFrame([{
        "KRX_FWDG_ORD_ORGNO": "06010", "ODNO": new_odno, "ORD_TMD": "100501", "SOR_ODNO": "",
    }])


def _make_om(paper=False, broker=None, telegram=None, db=None):
    from core.order_manager import OrderManager
    config = TradingConfig.from_json({
        "paper_trading": paper,
        "order_management": {"buy_timeout_seconds": 300, "sell_timeout_seconds": 180},
    })
    if telegram is None:
        telegram = AsyncMock()
    if db is None:
        db = Mock()
        db.save_real_buy.return_value = 1
        db.save_real_sell.return_value = True
        db.get_last_open_real_buy.return_value = None
    return OrderManager(config, broker if broker is not None else Mock(), telegram, db)


def _inject(om, order_id="0000012345", code="005930", otype=OrderType.BUY,
            price=70000, qty=10, age_sec=0, owner=DT_KEY, timeout_sec=300):
    ts = now_kst() - timedelta(seconds=age_sec)
    order = Order(order_id=order_id, stock_code=code, order_type=otype, price=price,
                  quantity=qty, timestamp=ts, status=OrderStatus.PENDING,
                  remaining_quantity=qty, owner_strategy=owner)
    om.pending_orders[order_id] = order
    om.order_timeouts[order_id] = ts + timedelta(seconds=timeout_sec)
    return order


def _daytrading_strategy():
    from strategies.daytrading_3methods_breakout.strategy import DayTrading3MethodsBreakoutStrategy
    strat = DayTrading3MethodsBreakoutStrategy({
        "parameters": {"min_daily_bars": 25, "max_holding_days": 10},
        "risk_management": {"take_profit_pct": 0.10, "stop_loss_pct": 0.10,
                            "max_hold_days": 10, "trail_ma": None,
                            "max_positions": 10, "max_daily_trades": 5},
        "paper_trading": False,
    })
    strat.on_init(broker=None, data_provider=None, executor=None)
    return strat


def _real_tsm(om, strategies=None):
    """실체 TradingStockManager(facade) — 슬롯 조회·전략 통보 라우팅을 진짜로 탄다."""
    from core.trading_stock_manager import TradingStockManager
    tsm = TradingStockManager(MagicMock(), MagicMock(), om, None)
    if strategies:
        tsm.set_strategies(strategies)
    return tsm


def _register_slot(tsm, code="005930", owner=DT_KEY, state=StockState.BUY_PENDING):
    ts = TradingStock(stock_code=code, stock_name=f"N{code}", state=state,
                      selected_time=now_kst(), selection_reason="t", owner_strategy_name=owner)
    tsm._register_stock(ts)
    return tsm.get_trading_stock(code, strategy=owner)


# =============================================================================
# NEW-B1 — 취소 성공을 «실패» 로 읽던 결함
# =============================================================================
class TestB1CancelSuccessByOdno:
    """framework/broker.py cancel_order: 성공 = 응답 행 존재 + ODNO(rt_cd 는 isOK 가 이미 검사)."""

    def _run(self, cancel_return):
        broker = _connected_broker()
        fake = _fake_order_api(
            get_inquire_psbl_rvsecncl_lst=Mock(return_value=_pending_df()),
            get_order_rvsecncl=Mock(return_value=cancel_return),
        )
        with patch.object(_api_pkg(), "kis_order_api", fake, create=True):
            result = broker.cancel_order("0000012345", "005930")
        fake.get_order_rvsecncl.assert_called_once()  # 공허 통과 방지
        return result

    def test_output_row_with_odno_is_success(self):
        result = self._run(_cancel_ok_df())
        assert result["success"] is True
        assert result["order_id"] == "0000012345"  # 원주문번호를 돌려준다(새 번호는 data 에)
        assert result["data"]["ODNO"] == "0010239000"

    def test_output_row_without_odno_is_failure(self):
        result = self._run(pd.DataFrame([{"ODNO": "", "ORD_TMD": "100501"}]))
        assert result["success"] is False

    def test_no_response_is_failure(self):
        result = self._run(None)
        assert result["success"] is False

    def test_kis_api_manager_cancel_same_rule(self):
        """같은 계열(api/kis_api_manager.py) — 운영 호출자 0 이지만 함께 정리."""
        from api.kis_api_manager import KISAPIManager
        mgr = KISAPIManager()
        mgr._call_api_with_retry = Mock(side_effect=[_pending_df(), _cancel_ok_df()])
        with patch("utils.korean_time.is_before_market_open", return_value=False):
            res = mgr.cancel_order("0000012345", "005930")
        assert mgr._call_api_with_retry.call_count == 2
        assert res.success is True


class TestB1PartialFillTimeoutLedger:
    """B1 수정으로 처음 사는 `_handle_partial_fill_timeout` 성공 분기 — owner·전략 통보(F5)."""

    @pytest.mark.asyncio
    async def test_partial_buy_reflected_in_cap_strategy_and_funds(self):
        from core.fund_manager import FundManager

        broker = _connected_broker()
        fake = _fake_order_api(
            get_inquire_psbl_rvsecncl_lst=Mock(return_value=_pending_df()),
            get_order_rvsecncl=Mock(return_value=_cancel_ok_df()),
        )
        telegram = AsyncMock()
        om = _make_om(broker=broker, telegram=telegram)
        fm = FundManager(initial_funds=10_000_000)
        om.set_fund_manager(fm)
        assert fm.reserve_funds("0000012345", 700_000)

        strat = _daytrading_strategy()
        tsm = _real_tsm(om, {DT_KEY: strat})
        slot = _register_slot(tsm)
        slot.is_buying = True

        order = _inject(om)
        order.filled_quantity = 3

        with patch.object(_api_pkg(), "kis_order_api", fake, create=True):
            await om._handle_partial_fill_timeout("0000012345", order, 3)
        fake.get_order_rvsecncl.assert_called_once()

        # 자금 장부: 체결분만 투자, 나머지 예약 환불, 보유 레지스트리는 (code, owner)
        assert fm.invested_funds == pytest.approx(210_000)
        assert fm.reserved_funds == pytest.approx(0)
        assert ("005930", DT_KEY) in fm._position_entries
        assert ("005930", None) not in fm._position_entries
        # 슬롯: 체결분 POSITIONED
        assert slot.state == StockState.POSITIONED
        assert slot.position.quantity == 3
        assert slot.is_buying is False
        # 전략: 일일 캡 +1 · 포지션 3주 (F5)
        assert strat.daily_trades == 1
        assert strat.positions["005930"]["quantity"] == 3
        assert strat.positions["005930"]["entry_price"] == pytest.approx(70000)
        # 원장 기록 = 체결분
        om.db_manager.save_real_buy.assert_called_once()
        assert om.db_manager.save_real_buy.call_args.kwargs["quantity"] == 3
        # 「잔여취소 실패 - 수동 확인 필요」 분기로 가지 않았다
        msgs = " ".join(str(c.args[0]) for c in telegram.notify_system_status.call_args_list)
        assert "수동 확인 필요" not in msgs


# =============================================================================
# NEW-C1 — Ctrl+C(is_running=False) 뒤 텔레그램 태스크가 안 끝나 shutdown() 미도달
# =============================================================================
def _telegram_integration(bot, enabled=True, interval_minutes=30):
    from core.telegram_integration import TelegramIntegration
    ti = TelegramIntegration.__new__(TelegramIntegration)
    ti.logger = MagicMock()
    ti.trading_bot = bot
    ti.is_enabled = enabled
    ti.notifier = _polling_notifier(bot) if enabled else None
    ti.notification_settings = {"periodic_status": True, "interval_minutes": interval_minutes}
    ti.notify_system_status = AsyncMock()
    return ti


def _polling_notifier(bot):
    """start_polling 본체를 그대로 돌리되 PTB Application 은 모의 객체."""
    from utils.telegram.telegram_notifier import TelegramNotifier
    n = TelegramNotifier.__new__(TelegramNotifier)
    n.logger = MagicMock()
    n.is_initialized = True
    n.is_polling = False
    n.trading_bot_ref = bot
    n.bot = MagicMock()
    n.bot.delete_webhook = AsyncMock()
    app = MagicMock()
    app.initialize = AsyncMock()
    app.start = AsyncMock()
    app.stop = AsyncMock()
    app.shutdown = AsyncMock()
    app.updater.start_polling = AsyncMock()
    app.updater.stop = AsyncMock()
    app.updater.running = False
    n.application = app
    return n


class _FastSleep:
    """모듈이 참조하는 asyncio 를 «짧게 자는» 대역으로 — 2초·1초 대기를 테스트에서 줄인다."""

    def __init__(self):
        import asyncio as _real
        self._real = _real

    def __getattr__(self, name):
        return getattr(self._real, name)

    async def sleep(self, _seconds):
        await self._real.sleep(0.01)


class TestC1TelegramTasksStopOnShutdownSignal:

    @pytest.mark.asyncio
    async def test_periodic_status_task_ends_after_is_running_false(self):
        import asyncio
        bot = types.SimpleNamespace(is_running=True)
        ti = _telegram_integration(bot, enabled=True, interval_minutes=30)
        with patch("core.telegram_integration.asyncio", _FastSleep()):
            task = asyncio.ensure_future(ti.periodic_status_task())
            await asyncio.sleep(0.05)
            assert not task.done(), "실행 중에는 계속 돌아야 한다(조기 종료 아님)"
            bot.is_running = False
            await asyncio.wait_for(task, timeout=2)
        ti.notify_system_status.assert_not_awaited()  # 30분 주기 전 종료

    @pytest.mark.asyncio
    async def test_periodic_status_task_still_notifies_while_running(self):
        """대기 쪼개기가 주기 알림 자체를 죽이지 않았음(공허 통과 방지)."""
        import asyncio
        bot = types.SimpleNamespace(is_running=True)
        ti = _telegram_integration(bot, enabled=True, interval_minutes=0.001)  # 0.06초
        task = asyncio.ensure_future(ti.periodic_status_task())
        await asyncio.sleep(0.3)
        bot.is_running = False
        await asyncio.wait_for(task, timeout=3)
        assert ti.notify_system_status.await_count >= 1

    @pytest.mark.asyncio
    async def test_polling_loop_ends_after_is_running_false(self):
        import asyncio
        bot = types.SimpleNamespace(is_running=True)
        n = _polling_notifier(bot)
        with patch("utils.telegram.telegram_notifier.asyncio", _FastSleep()):
            task = asyncio.ensure_future(n.start_polling())
            await asyncio.sleep(0.1)
            assert not task.done()
            n.application.updater.start_polling.assert_awaited_once()  # 폴링까지 실제 진입
            bot.is_running = False
            await asyncio.wait_for(task, timeout=2)
        assert n.is_polling is False
        n.application.stop.assert_awaited_once()      # finally 정리 경로
        n.application.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notifier_shutdown_skips_stop_when_already_stopped(self):
        """폴링 finally 가 먼저 멈춘 뒤의 shutdown() — stop() 의 not-running 오류 줄을 안 낸다."""
        n = _polling_notifier(types.SimpleNamespace(is_running=False))
        n.send_system_stop = AsyncMock()
        n.application.running = False
        await n.shutdown()
        n.application.stop.assert_not_awaited()
        n.application.shutdown.assert_awaited_once()
        n.logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_paper_disabled_telegram_returns_immediately_unchanged(self):
        """페이퍼(텔레그램 disabled): 두 태스크는 루프에 들어가기 전에 끝난다 — 종전과 동일."""
        import asyncio
        bot = types.SimpleNamespace(is_running=True)
        ti = _telegram_integration(bot, enabled=False)
        await asyncio.wait_for(ti.periodic_status_task(), timeout=0.5)
        await asyncio.wait_for(ti.start_telegram_bot(), timeout=0.5)
        ti.notify_system_status.assert_not_awaited()


@pytest.fixture
def daytrading_bot():
    """DayTradingBot 을 외부 의존성 Mock 으로 생성(tests/test_main_loop.py 와 같은 방식)."""
    with patch("main.KISBroker") as mock_broker_cls, \
         patch("main.DatabaseManager") as mock_db_cls, \
         patch("main.TelegramIntegration"), \
         patch("main.check_duplicate_process"), \
         patch("main.load_config") as mock_load_config, \
         patch("main.StrategyLoader") as mock_loader:
        mock_load_config.return_value = MagicMock(
            rebalancing_mode=False,
            strategy={"name": "sample", "enabled": False},
            paper_trading=True,
        )
        mock_db_cls.return_value.db_path = ":memory:"
        mock_broker_cls.return_value.connect = AsyncMock(return_value=True)
        mock_loader.load_strategy.side_effect = FileNotFoundError("test")
        from main import DayTradingBot
        yield DayTradingBot()


class TestC1RunDailyCycleReachesShutdown:

    @pytest.mark.asyncio
    async def test_sigint_with_enabled_telegram_reaches_shutdown(self, daytrading_bot):
        """종료 신호 → 메인 루프 종료 → 텔레그램 두 태스크 종료 → finally: shutdown() 1회."""
        import asyncio
        bot = daytrading_bot
        bot.telegram = _telegram_integration(bot, enabled=True, interval_minutes=30)
        bot.system_monitor.run_system_monitoring_task = AsyncMock()
        bot.bot_initializer.shutdown = AsyncMock()

        async def fake_main_loop():
            await asyncio.sleep(0.05)
            bot._signal_handler(2, None)  # Ctrl+C 와 같은 효과(is_running=False 만)

        bot._main_trading_loop = fake_main_loop
        with patch("core.telegram_integration.asyncio", _FastSleep()), \
             patch("utils.telegram.telegram_notifier.asyncio", _FastSleep()):
            await asyncio.wait_for(bot.run_daily_cycle(), timeout=5)

        bot.bot_initializer.shutdown.assert_awaited_once()
        bot.telegram.notifier.application.updater.start_polling.assert_awaited_once()

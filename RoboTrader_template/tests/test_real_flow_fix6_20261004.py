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


# =============================================================================
# NEW-B3 + P1-6 — 조회 «실패» 와 «목록에 없음» 구분 · 상태 불명을 취소 없이 닫지 않음
# =============================================================================
def _daily_row(odno="0000012345", qty="10", ccld="10", rmn="0", cncl="N", avg="70000"):
    return pd.DataFrame([{"odno": odno, "pdno": "005930", "ord_qty": qty, "tot_ccld_qty": ccld,
                          "rmn_qty": rmn, "cncl_yn": cncl, "avg_prvs": avg}])


class TestB3OrderStatusFailureVsAbsent:

    def _status(self, pending, daily):
        broker = _connected_broker()
        fake = _fake_order_api(
            get_inquire_psbl_rvsecncl_lst=Mock(return_value=pending),
            get_inquire_daily_ccld_lst=Mock(return_value=daily),
        )
        with patch.object(_api_pkg(), "kis_order_api", fake, create=True):
            result = broker.get_order_status("0000012345")
        fake.get_inquire_psbl_rvsecncl_lst.assert_called_once()
        fake.get_inquire_daily_ccld_lst.assert_called_once()
        return result

    def test_daily_query_failure_is_none_not_unknown(self):
        # 체결된 주문: 정정취소가능 목록(성공·빈 목록)에 없음 + 체결조회 실패(CB OPEN 등)
        assert self._status(pd.DataFrame(), None) is None

    def test_pending_query_failure_and_daily_absent_is_none(self):
        assert self._status(None, pd.DataFrame()) is None

    def test_both_ok_and_absent_is_status_unknown(self):
        res = self._status(pd.DataFrame(), pd.DataFrame())
        assert res["status_unknown"] is True

    def test_pending_failure_but_daily_has_row_returns_executed(self):
        res = self._status(None, _daily_row())
        assert res["_status"] == "executed" and res["tot_ccld_qty"] == "10"


class TestB3NoFalsePositiveRestoreOnQueryFailure:
    """감사 예시 ③: 매도 체결 뒤 체결조회 1회 실패 → «미체결» 오탐 부활 → 같은 매도 이중 처리."""

    @pytest.mark.asyncio
    async def test_filled_sell_not_revived_by_failed_or_unknown_lookup(self):
        broker = _connected_broker()
        om = _make_om(broker=broker)
        order = _inject(om, otype=OrderType.SELL, price=0, qty=10)
        order.status = OrderStatus.FILLED
        order.filled_price = 71000.0
        om._move_to_completed(order.order_id)
        assert order in om.completed_orders

        lst = Mock(return_value=pd.DataFrame())     # 체결 주문은 정정취소가능 목록에 없다
        daily = Mock(return_value=None)             # 체결조회 실패(CB 30초 차단 등)
        fake = _fake_order_api(get_inquire_psbl_rvsecncl_lst=lst, get_inquire_daily_ccld_lst=daily)
        with patch.object(_api_pkg(), "kis_order_api", fake, create=True):
            await om._check_false_positive_filled_orders(now_kst())
            om._last_false_positive_check = None
            daily.return_value = pd.DataFrame()     # 두 조회 성공 + 어디에도 없음 = 상태 불명
            await om._check_false_positive_filled_orders(now_kst())
        assert daily.call_count == 2                 # 실제로 두 번 다 조회했다(공허 통과 방지)

        assert order.order_id not in om.pending_orders, "조회 실패·상태 불명으로 체결 주문을 되살렸다"
        assert order.status == OrderStatus.FILLED
        om.telegram.notify_system_status.assert_not_awaited()  # 「오탐 복구」 경보 없음

    @pytest.mark.asyncio
    async def test_genuinely_unfilled_still_restored(self):
        """대칭 단언: 체결조회가 «미체결» 을 명시하면 오탐 복구는 종전대로 동작한다."""
        broker = _connected_broker()
        om = _make_om(broker=broker)
        order = _inject(om, otype=OrderType.BUY, qty=10)
        order.status = OrderStatus.FILLED
        om._move_to_completed(order.order_id)

        fake = _fake_order_api(
            get_inquire_psbl_rvsecncl_lst=Mock(return_value=pd.DataFrame()),
            get_inquire_daily_ccld_lst=Mock(return_value=_daily_row(ccld="0", rmn="10")),
        )
        with patch.object(_api_pkg(), "kis_order_api", fake, create=True):
            await om._check_false_positive_filled_orders(now_kst())
        assert order.order_id in om.pending_orders


class TestB3UnknownTimeoutGoesThroughCancel:
    """P1-6: 상태 불명 5분 초과를 «취소 없이 장부만 TIMEOUT» 하지 않는다 → 취소 경로 + 슬롯 복구 + 경보."""

    @pytest.mark.asyncio
    async def test_unknown_over_timeout_attempts_cancel_then_force_cleanup_with_alert(self):
        broker = Mock()
        broker.get_order_status.return_value = {
            "odno": "0000012345", "_status": "unknown", "status_unknown": True, "cncl_yn": "N"}
        broker.cancel_order.return_value = {
            "success": False, "order_id": "0000012345",
            "message": "Order 0000012345 not found in cancellable list", "data": None}
        telegram = AsyncMock()
        om = _make_om(broker=broker, telegram=telegram)
        om.trading_manager = AsyncMock()
        order = _inject(om, age_sec=400, timeout_sec=300)  # 접수 400초 전 · 타임아웃 100초 지남

        with patch("core.orders.order_timeout.ORDER_CANCEL_RETRY_INTERVAL", 0):
            await om._monitor_pending_orders()

        assert broker.cancel_order.call_count >= 1, "취소를 한 번도 시도하지 않고 닫았다"
        assert order.order_id not in om.pending_orders
        assert order.status == OrderStatus.TIMEOUT
        om.trading_manager.handle_order_timeout.assert_awaited()       # 슬롯 BUY_PENDING 고착 방지
        msgs = " ".join(str(c.args[0]) for c in telegram.notify_system_status.call_args_list)
        assert "수동 확인 필요" in msgs


# =============================================================================
# NEW-B2 — 잔고 조회 실패를 «매도가능 0주» 로 읽어 손절이 안 나가던 결함
# =============================================================================
class TestB2SellableQuantityFailureIsNone:

    def _broker(self, balance):
        b = _connected_broker()
        b._kis_market_api = Mock()
        b._kis_market_api.get_account_balance = Mock(return_value=balance)
        return b

    def test_balance_failure_returns_none(self):
        b = self._broker(None)
        assert b.get_sellable_quantity("005930") is None
        b._kis_market_api.get_account_balance.assert_called_once()

    def test_held_returns_quantity(self):
        b = self._broker({"total_stocks": 1, "stocks": [{"stock_code": "005930", "quantity": 7}]})
        assert b.get_sellable_quantity("005930") == 7

    def test_not_held_returns_zero(self):
        b = self._broker({"total_stocks": 0, "stocks": []})
        assert b.get_sellable_quantity("005930") == 0

    def test_get_holdings_contract_unchanged(self):
        """다른 소비자가 있는 get_holdings 는 종전대로 실패를 [] 로 준다(바꾸지 않음)."""
        b = _connected_broker()
        b._kis_market_api = Mock()
        b._kis_market_api.get_existing_holdings = Mock(return_value=None)
        assert b.get_holdings() == []


class TestB2SellProceedsWhenBalanceLookupFails:

    @pytest.mark.asyncio
    async def test_stop_loss_sell_sent_with_internal_quantity(self):
        broker = _connected_broker()
        broker._kis_market_api = Mock()
        broker._kis_market_api.get_account_balance = Mock(return_value=None)  # 조회 실패(CB 차단 등)
        broker.place_sell_order = Mock(return_value={
            "success": True, "order_id": "0000055555", "message": "", "data": {}})
        om = _make_om(broker=broker)

        oid = await om._execute_real_sell_order("005930", 10, 0, 180, True, DT_KEY)

        broker._kis_market_api.get_account_balance.assert_called_once()
        broker.place_sell_order.assert_called_once()
        assert broker.place_sell_order.call_args.args[1] == 10   # 내부 수량 그대로
        assert oid == "0000055555" and oid in om.pending_orders

    @pytest.mark.asyncio
    async def test_zero_holding_still_blocks(self):
        """대칭 단언: 조회 «성공» + 실보유 0 이면 종전대로 미발송."""
        broker = _connected_broker()
        broker._kis_market_api = Mock()
        broker._kis_market_api.get_account_balance = Mock(return_value={"total_stocks": 0, "stocks": []})
        broker.place_sell_order = Mock()
        om = _make_om(broker=broker)

        oid = await om._execute_real_sell_order("005930", 10, 0, 180, True, DT_KEY)
        assert oid is None
        broker.place_sell_order.assert_not_called()


# =============================================================================
# NEW-C2 — 실전 아침 복원에서 등록 실패 보유가 조용히 빠지던 결함
# =============================================================================
def _restore_fixture(intraday_add):
    """실체 TradingStockManager + StateRestorer(실전) — KIS·DB 는 모의."""
    from bot.state_restorer import StateRestorer
    from tests.broker_contract import make_account_balance, make_holding

    intraday = MagicMock()
    intraday.add_selected_stock = intraday_add
    data_collector = MagicMock()
    data_collector.get_stock.return_value = None   # 장중 데이터 미등록 상태
    om = MagicMock()
    from core.trading_stock_manager import TradingStockManager
    tsm = TradingStockManager(intraday, data_collector, om, None)

    db = Mock()
    db.get_real_open_positions.return_value = pd.DataFrame([{
        "id": 1, "stock_code": "005930", "stock_name": "삼성전자", "quantity": 10,
        "buy_price": 100_000.0, "buy_time": now_kst() - timedelta(days=3),
        "strategy": "stratA", "target_profit_rate": 0.10, "stop_loss_rate": 0.10,
    }])
    broker = Mock()
    broker.get_pending_orders.return_value = []
    broker.get_account_balance.return_value = make_account_balance(total_stocks=1)
    broker.get_holdings.return_value = [make_holding(quantity=10, avg_price=100_000.0)]
    strat = Mock()
    telegram = Mock()
    telegram.notify_urgent_signal = AsyncMock()
    config = Mock()
    config.paper_trading = False
    r = StateRestorer(
        trading_manager=tsm, db_manager=db, telegram_integration=telegram, config=config,
        get_previous_close_callback=lambda code: 100_000.0, broker=broker, fund_manager=None,
        virtual_trading_manager=None, strategies={"stratA": strat},
    )
    r._sync_fund_manager_for_position = Mock(return_value=1_000_000.0)
    return r, tsm, intraday, telegram, strat


class TestC2RealRestoreNoSilentDrop:

    @pytest.mark.asyncio
    async def test_intraday_registration_fails_then_slot_positioned_with_alert(self):
        r, tsm, intraday, telegram, strat = _restore_fixture(AsyncMock(return_value=False))
        with patch("bot.state_restorer.REAL_RESTORE_RETRY_SEC", 0):
            await r._restore_holdings_from_real_account()

        assert intraday.add_selected_stock.await_count == 3        # 재시도 3회
        slot = tsm.get_trading_stock("005930", strategy="stratA")
        assert slot is not None and slot.state == StockState.POSITIONED
        assert slot.position.quantity == 10 and slot.position.avg_price == pytest.approx(100_000.0)
        assert slot.stop_loss_rate == pytest.approx(0.10) and slot.target_profit_rate == pytest.approx(0.10)
        r._sync_fund_manager_for_position.assert_called_once()     # 자금 장부도 반영
        (positions,) = strat.sync_positions.call_args[0]
        assert positions["005930"]["quantity"] == 10                # 전략 포지션 주입
        telegram.notify_urgent_signal.assert_awaited_once()
        assert "005930" in telegram.notify_urgent_signal.call_args.args[0]

    @pytest.mark.asyncio
    async def test_retry_succeeds_no_alert(self):
        r, tsm, intraday, telegram, _ = _restore_fixture(AsyncMock(side_effect=[False, True]))
        with patch("bot.state_restorer.REAL_RESTORE_RETRY_SEC", 0):
            await r._restore_holdings_from_real_account()
        assert intraday.add_selected_stock.await_count == 2
        assert tsm.get_trading_stock("005930", strategy="stratA").state == StockState.POSITIONED
        telegram.notify_urgent_signal.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_slot_registration_impossible_aborts(self):
        from utils.exceptions import LiveStartupAbort
        r, tsm, intraday, telegram, _ = _restore_fixture(AsyncMock(return_value=False))
        tsm._register_stock = Mock(side_effect=RuntimeError("boom"))
        with patch("bot.state_restorer.REAL_RESTORE_RETRY_SEC", 0), \
             pytest.raises(LiveStartupAbort) as ei:
            await r._restore_holdings_from_real_account()
        assert "005930" in str(ei.value)
        tsm._register_stock.assert_called_once()

    @pytest.mark.asyncio
    async def test_degraded_slot_gets_stop_loss_and_take_profit_from_position_monitor(self):
        """폴백 슬롯(장중 데이터 미등록)도 현재가 기반 손절·익절 백스톱을 받는다 — 예외 없음."""
        r, tsm, intraday, _, _ = _restore_fixture(AsyncMock(return_value=False))
        with patch("bot.state_restorer.REAL_RESTORE_RETRY_SEC", 0):
            await r._restore_holdings_from_real_account()
        slot = tsm.get_trading_stock("005930", strategy="stratA")

        pm = tsm._position_monitor
        pm.set_decision_engine(Mock())
        pm._execute_sell = AsyncMock()
        fixed = now_kst().replace(hour=10, minute=30, second=0, microsecond=0)
        with patch("core.trading.position_monitor.now_kst", return_value=fixed):
            intraday.get_current_price_for_sell = Mock(return_value={"current_price": 89_000.0})
            await pm._check_positioned_stocks_for_sell()
            assert pm._execute_sell.await_count == 1
            assert pm._execute_sell.call_args.args[0] is slot
            assert "손절" in pm._execute_sell.call_args.args[2]

            pm._execute_sell.reset_mock()
            intraday.get_current_price_for_sell = Mock(return_value={"current_price": 111_000.0})
            await pm._check_positioned_stocks_for_sell()
            assert pm._execute_sell.await_count == 1
            assert "익절" in pm._execute_sell.call_args.args[2]
        intraday.get_current_price_for_sell.assert_called_with("005930")


# =============================================================================
# NEW-A1 — on_tick 30초 타임아웃이 진행 중인 주문 호출을 취소(고아 주문·슬롯 고착·예약 누수)
# =============================================================================
async def _settle(predicate, limit=300):
    import asyncio
    for _ in range(limit):
        if predicate():
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.02)  # done-callback 이 돌 틈


class _CB:
    def is_market_halted(self):
        return False

    def is_vi_active(self, _code):
        return False


class TestA1OrderCallSurvivesOnTickTimeout:

    @pytest.mark.asyncio
    async def test_buy_registered_not_orphaned_when_on_tick_times_out(self):
        """실전 OrderManager 전 구간: KIS 응답이 on_tick 타임아웃보다 늦어도 주문이 추적된다."""
        import asyncio
        import threading
        from config.market_hours import MarketHours
        from core.fund_manager import FundManager, make_reserve_id

        gate = threading.Event()
        cancelled_inside = []

        def slow_place(code, qty, price, order_type="00"):
            gate.wait(5)  # KIS 해시키+주문 응답 지연
            return {"success": True, "order_id": "0000077777", "message": "", "data": {}}

        broker = Mock()
        broker.place_buy_order = Mock(side_effect=slow_place)
        om = _make_om(broker=broker)
        fm = FundManager(initial_funds=10_000_000)
        om.set_fund_manager(fm)
        tsm = _real_tsm(om, {DT_KEY: _daytrading_strategy()})
        tsm.set_fund_manager(fm)
        slot = _register_slot(tsm, state=StockState.SELECTED)
        rid = make_reserve_id("005930", DT_KEY)
        assert fm.reserve_funds(rid, 700_000)  # trading_analyzer 가 잡는 예약

        with patch.object(MarketHours, "can_place_order", return_value=True), \
             patch("config.market_hours.get_circuit_breaker_state", return_value=_CB()):
            try:
                await asyncio.wait_for(
                    tsm.execute_buy_order("005930", 10, 70000, "돌파", strategy=DT_KEY), timeout=0.2)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:  # pragma: no cover - 방어
                cancelled_inside.append(True)
            else:
                pytest.fail("주문이 on_tick 타임아웃보다 먼저 끝났다 — 시나리오가 재현되지 않음")
            gate.set()  # 그 사이 KIS 가 접수 응답
            await _settle(lambda: slot.current_order_id is not None)

        broker.place_buy_order.assert_called_once()
        assert "0000077777" in om.pending_orders, "KIS 접수 주문을 봇이 모른다(고아 주문)"
        assert fm.has_reservation("0000077777") and not fm.has_reservation(rid), "예약이 주문ID로 이전 안 됨"
        assert slot.current_order_id == "0000077777"
        assert slot.state == StockState.BUY_PENDING  # 체결·타임아웃은 주문 모니터가 처리
        assert not cancelled_inside

    @pytest.mark.asyncio
    async def test_buy_failure_after_cancel_restores_slot_and_reservation(self):
        import asyncio
        from core.fund_manager import FundManager, make_reserve_id

        release = asyncio.Event()
        om = MagicMock()

        async def place_buy_order(code, qty, price, owner_strategy=""):
            await release.wait()
            return None  # 접수 실패(예외 경로처럼 예약을 스스로 안 푼 경우)

        om.place_buy_order = place_buy_order
        fm = FundManager(initial_funds=10_000_000)
        tsm = _real_tsm(om)
        tsm.set_fund_manager(fm)
        slot = _register_slot(tsm, state=StockState.SELECTED)
        rid = make_reserve_id("005930", DT_KEY)
        assert fm.reserve_funds(rid, 700_000)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                tsm.execute_buy_order("005930", 10, 70000, "돌파", strategy=DT_KEY), timeout=0.05)
        assert slot.state == StockState.BUY_PENDING and slot.is_buying is True  # 아직 결과 대기
        release.set()
        await _settle(lambda: slot.state != StockState.BUY_PENDING)

        assert slot.state == StockState.SELECTED and slot.is_buying is False
        assert not fm.has_reservation(rid), "취소 뒤 실패한 매수의 예약이 남았다(누수)"

    @pytest.mark.asyncio
    async def test_sell_after_cancel_success_links_order_and_failure_restores_positioned(self):
        import asyncio
        for outcome in ("0000088888", None):
            release = asyncio.Event()
            om = MagicMock()

            async def place_sell_order(code, qty, price, market=False, force=False,
                                       owner_strategy="", _out=outcome, _ev=release):
                await _ev.wait()
                return _out

            om.place_sell_order = place_sell_order
            tsm = _real_tsm(om)
            slot = _register_slot(tsm, state=StockState.POSITIONED)
            slot.set_position(10, 70000)
            assert tsm.move_to_sell_candidate("005930", "손절", strategy=DT_KEY)

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    tsm.execute_sell_order("005930", 10, 0, "손절", market=True, strategy=DT_KEY),
                    timeout=0.05)
            assert slot.state == StockState.SELL_PENDING
            release.set()
            if outcome:
                await _settle(lambda: slot.current_order_id is not None)
                assert slot.current_order_id == outcome and slot.state == StockState.SELL_PENDING
            else:
                await _settle(lambda: slot.state != StockState.SELL_PENDING)
                assert slot.state == StockState.POSITIONED and slot.is_selling is False

    @pytest.mark.asyncio
    async def test_no_cancel_path_unchanged(self):
        """취소가 없으면 종전과 같다: 결과를 그대로 돌려주고 슬롯에 주문ID 연결."""
        om = MagicMock()
        om.place_buy_order = AsyncMock(return_value="0000099999")
        tsm = _real_tsm(om)
        slot = _register_slot(tsm, state=StockState.SELECTED)
        assert await tsm.execute_buy_order("005930", 10, 70000, "돌파", strategy=DT_KEY) is True
        om.place_buy_order.assert_awaited_once_with("005930", 10, 70000, owner_strategy=DT_KEY)
        assert slot.current_order_id == "0000099999" and slot.state == StockState.BUY_PENDING

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
        cancelled = []
        fake = _fake_order_api(
            # 잔량 취소 접수 뒤에는 8036R 에서 사라지고 0081R 원주문 행(잔량 0)만 남는다(10-08 실측형)
            get_inquire_psbl_rvsecncl_lst=Mock(
                side_effect=lambda *a, **k: pd.DataFrame() if cancelled else _pending_df()),
            get_order_rvsecncl=Mock(side_effect=lambda *a, **k: cancelled.append(1) or _cancel_ok_df()),
            get_inquire_daily_ccld_lst=Mock(return_value=pd.DataFrame([{
                "odno": "0000012345", "ord_qty": "10", "tot_ccld_qty": "3", "rmn_qty": "0",
                "cncl_yn": "", "cncl_cfrm_qty": "0", "avg_prvs": "70000"}])),
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

        with patch.object(_api_pkg(), "kis_order_api", fake, create=True), _no_settle_wait():
            await om._handle_partial_fill_timeout("0000012345", order, 3)
        fake.get_order_rvsecncl.assert_called_once()
        assert fake.get_inquire_daily_ccld_lst.call_count == 2      # 확정 재조회 연속 2회(N1·N2)

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


# =============================================================================
# 리뷰 반영(2026-10-04 · APPROVE-WITH-NOTES) — 중요1·중요2·사소3·사소4
# =============================================================================
def _executed_row(qty=10, ccld=10, rmn=0, avg="70000"):
    return {"odno": "0000012345", "_status": "executed", "ord_qty": str(qty),
            "tot_ccld_qty": str(ccld), "rmn_qty": str(rmn), "cncl_yn": "N", "avg_prvs": avg}


_NOT_FOUND = {"success": False, "order_id": "0000012345",
              "message": "Order 0000012345 not found in cancellable list", "data": None}
_CANCEL_OK = {"success": True, "order_id": "0000012345", "message": "Order cancelled",
              "data": {"ODNO": "0010239000"}}


class TestReview1DeferCloseWhenStatusQueryFails:
    """중요1: CB OPEN 중(체결조회 차단) 타임아웃 → 체결 여부를 모르는 채 TIMEOUT 으로 닫지 않는다."""

    def _om(self):
        broker = Mock()
        broker.get_order_status.return_value = None       # 0081R 차단 → 조회 실패
        broker.cancel_order.return_value = _NOT_FOUND      # 이미 체결돼 정정취소가능 목록에 없음
        telegram = AsyncMock()
        om = _make_om(broker=broker, telegram=telegram)
        om.trading_manager = AsyncMock()
        order = _inject(om, age_sec=400, timeout_sec=300)
        return om, broker, telegram, order

    @staticmethod
    def _manual_alerts(telegram):
        return [c for c in telegram.notify_system_status.call_args_list if "수동 확인 필요" in str(c.args[0])]

    @pytest.mark.asyncio
    async def test_query_failure_defers_then_fill_is_recognised(self):
        om, broker, telegram, order = self._om()
        with patch("core.orders.order_timeout.ORDER_CANCEL_RETRY_INTERVAL", 0):
            await om._monitor_pending_orders()

        assert broker.cancel_order.call_count == 3                 # 취소는 시도했다
        assert order.order_id in om.pending_orders, "조회 실패인데 TIMEOUT 으로 닫았다(고아 위험)"
        assert order.status != OrderStatus.TIMEOUT
        assert om._timeout_defer_counts[order.order_id] == 1
        assert (om.order_timeouts[order.order_id] - now_kst()).total_seconds() > 30
        om.trading_manager.handle_order_timeout.assert_not_awaited()   # 슬롯 COMPLETED 아님
        assert not self._manual_alerts(telegram)

        # CB 가 닫혀 체결조회 성공 → 체결로 인식(손절 감시 대상이 된다)
        broker.get_order_status.return_value = _executed_row()
        await om._monitor_pending_orders()
        assert order.order_id not in om.pending_orders
        assert order.status == OrderStatus.FILLED
        om.trading_manager.on_order_filled.assert_awaited_once()
        assert order.order_id not in om._timeout_defer_counts       # 연기 표식 정리

    @pytest.mark.asyncio
    async def test_defer_limit_then_close_with_single_alert(self):
        from config.constants import ORDER_TIMEOUT_DEFER_MAX
        om, broker, telegram, order = self._om()
        with patch("core.orders.order_timeout.ORDER_CANCEL_RETRY_INTERVAL", 0):
            for _ in range(ORDER_TIMEOUT_DEFER_MAX):
                await om._handle_timeout(order.order_id)
                assert order.order_id in om.pending_orders
            assert not self._manual_alerts(telegram)
            await om._handle_timeout(order.order_id)                 # 상한 초과 → 종결

        assert order.status == OrderStatus.TIMEOUT and order.order_id not in om.pending_orders
        om.trading_manager.handle_order_timeout.assert_awaited_once()
        assert len(self._manual_alerts(telegram)) == 1
        timeouts = [c for c in telegram.notify_system_status.call_args_list if "주문 타임아웃" in str(c.args[0])]
        assert len(timeouts) == 1                                    # 연기 재처리마다 반복 발송 안 함

    @pytest.mark.asyncio
    async def test_query_ok_closes_as_before(self):
        """대칭: 재확인 조회가 «성공»(어디에도 없음)이면 종전대로 강제 정리 + 경보."""
        om, broker, telegram, order = self._om()
        broker.get_order_status.return_value = {
            "odno": order.order_id, "_status": "unknown", "status_unknown": True, "cncl_yn": "N"}
        with patch("core.orders.order_timeout.ORDER_CANCEL_RETRY_INTERVAL", 0):
            await om._handle_timeout(order.order_id)
        assert order.status == OrderStatus.TIMEOUT
        assert len(self._manual_alerts(telegram)) == 1


class TestReview2FillBetweenPrecheckAndCancel:
    """중요2: 사전 조회 체결 0 → 1~2초 사이 일부 체결 → 잔량 취소 성공 → 체결분이 장부 밖에 남던 경합."""

    def _setup(self, statuses):
        from core.fund_manager import FundManager
        broker = Mock()
        broker.get_order_status.side_effect = list(statuses)
        broker.cancel_order.return_value = _CANCEL_OK
        telegram = AsyncMock()
        om = _make_om(broker=broker, telegram=telegram)
        fm = FundManager(initial_funds=10_000_000)
        om.set_fund_manager(fm)
        assert fm.reserve_funds("0000012345", 700_000)
        strat = _daytrading_strategy()
        tsm = _real_tsm(om, {DT_KEY: strat})
        slot = _register_slot(tsm)
        slot.is_buying = True
        order = _inject(om, age_sec=400, timeout_sec=300)
        return om, broker, fm, strat, slot, order

    @staticmethod
    def _pending_row(ccld=0):
        return {"odno": "0000012345", "_status": "pending", "ord_qty": "10",
                "tot_ccld_qty": str(ccld), "psbl_qty": str(10 - ccld)}

    @pytest.mark.asyncio
    async def test_late_partial_fill_after_cancel_is_accounted(self):
        om, broker, fm, strat, slot, order = self._setup([
            self._pending_row(0),                         # 사전 조회: 체결 0
            _executed_row(ccld=3, rmn=0, avg="70100"),    # 취소 뒤 재조회: 3주 체결돼 있었다
            _executed_row(ccld=3, rmn=0, avg="70100"),    # 연속 2회 같은 체결수 = 확정(N2)
        ])
        with _no_settle_wait():
            await om._handle_timeout(order.order_id)

        assert broker.get_order_status.call_count == 3 and broker.cancel_order.call_count == 1
        assert order.status == OrderStatus.FILLED and order.quantity == 3
        assert order.order_id not in om.pending_orders
        assert [o.order_id for o in om.completed_orders].count(order.order_id) == 1
        assert fm.invested_funds == pytest.approx(3 * 70100)
        assert fm.reserved_funds == pytest.approx(0)
        assert ("005930", DT_KEY) in fm._position_entries
        assert slot.state == StockState.POSITIONED and slot.position.quantity == 3
        assert strat.daily_trades == 1 and strat.positions["005930"]["quantity"] == 3
        assert om.db_manager.save_real_buy.call_args.kwargs["quantity"] == 3

    @pytest.mark.asyncio
    async def test_requery_failure_reopens_defers_then_resolves_without_recancel(self):
        om, broker, fm, strat, slot, order = self._setup([
            self._pending_row(0),                         # 사전 조회
            None,                                         # 취소 직후 재조회 실패(CB OPEN)
            _executed_row(ccld=3, rmn=0, avg="70000"),    # 연기 뒤 재조회 성공
            _executed_row(ccld=3, rmn=0, avg="70000"),    # 연속 2회 같은 체결수 = 확정(N2)
        ])
        with _no_settle_wait():
            await om._handle_timeout(order.order_id)
        # 닫지 않고 되살려 연기 — 예약 복원·슬롯 BUY_PENDING 유지
        assert order.order_id in om.pending_orders and order.order_id in om._cancel_confirmed_ids
        assert fm.has_reservation(order.order_id) and fm.reserved_funds == pytest.approx(700_000)
        assert slot.state == StockState.BUY_PENDING
        # 그사이 메인 루프 1단계 상태 조회는 이 주문을 건드리지 않는다(취소 확인 주문)
        assert await om._check_order_status(order.order_id) is True
        assert broker.get_order_status.call_count == 2

        with _no_settle_wait():
            await om._handle_timeout(order.order_id)      # 연기 시한 도래
        assert broker.cancel_order.call_count == 1        # 취소 API 재호출 없음
        assert order.status == OrderStatus.FILLED and order.quantity == 3
        assert fm.invested_funds == pytest.approx(210_000) and fm.reserved_funds == pytest.approx(0)
        assert slot.state == StockState.POSITIONED and strat.daily_trades == 1
        assert order.order_id not in om._cancel_confirmed_ids

    @pytest.mark.asyncio
    async def test_zero_fill_after_cancel_keeps_previous_behaviour(self):
        om, broker, fm, strat, slot, order = self._setup([
            self._pending_row(0), _executed_row(ccld=0, rmn=0), _executed_row(ccld=0, rmn=0)])
        with _no_settle_wait():
            await om._handle_timeout(order.order_id)
        assert order.status == OrderStatus.CANCELLED
        assert fm.reserved_funds == pytest.approx(0) and fm.invested_funds == pytest.approx(0)
        assert slot.state == StockState.COMPLETED and strat.daily_trades == 0


class TestReview3ShutdownWaitsInflightOrders:

    @pytest.mark.asyncio
    async def test_wait_returns_after_background_order_registers(self):
        import asyncio
        release = asyncio.Event()
        om = MagicMock()

        async def place_buy_order(code, qty, price, owner_strategy=""):
            await release.wait()
            return "0000077777"

        om.place_buy_order = place_buy_order
        tsm = _real_tsm(om)
        slot = _register_slot(tsm, state=StockState.SELECTED)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                tsm.execute_buy_order("005930", 10, 70000, "돌파", strategy=DT_KEY), timeout=0.05)
        asyncio.get_event_loop().call_later(0.05, release.set)
        left = await tsm.wait_inflight_orders(timeout=2)
        assert left == 0
        await asyncio.sleep(0.01)
        assert slot.current_order_id == "0000077777"
        assert await tsm.wait_inflight_orders(timeout=2) == 0      # 빈 집합 즉시 반환(페이퍼와 같은 경로)

    @pytest.mark.asyncio
    async def test_shutdown_waits_before_cancelling_pending(self):
        from bot.initializer import BotInitializer
        calls = []
        bot = MagicMock()
        bot.telegram.shutdown = AsyncMock(side_effect=lambda: calls.append("telegram"))
        bot.trading_manager.wait_inflight_orders = AsyncMock(
            side_effect=lambda timeout: calls.append(("wait", timeout)) or 0)
        bot.broker.disconnect = AsyncMock()
        bot.pid_file.exists.return_value = False
        init = BotInitializer(bot)
        init._flush_state_to_db = Mock()
        init._cancel_pending_orders = AsyncMock(side_effect=lambda: calls.append("cancel"))
        await init.shutdown()
        assert calls == ["telegram", ("wait", 40.0), "cancel"]


class TestReview4StartupCancelRecheck:

    def _restorer(self, broker):
        from tests.test_live_p0_restore import _restorer_with
        db = Mock()
        db.get_real_open_positions.return_value = pd.DataFrame()
        return _restorer_with(db, broker, Mock())

    @pytest.mark.asyncio
    async def test_lagging_remaining_order_then_clear_proceeds(self):
        from tests.broker_contract import make_account_balance
        po = {"odno": "0001", "pdno": "005930", "sll_buy_dvsn_cd": "02"}
        broker = Mock()
        broker.get_account_balance.return_value = make_account_balance()
        broker.get_holdings.return_value = []
        broker.get_pending_orders.side_effect = [[po], [po], None, []]   # 발견 → 지연 잔존 → 조회 실패 → 0건
        broker.cancel_order.return_value = {"success": True}
        r = self._restorer(broker)
        with patch("bot.state_restorer.STARTUP_CANCEL_RECHECK_SEC", 0):
            await r._restore_holdings_from_real_account()
        assert broker.get_pending_orders.call_count == 4

    @pytest.mark.asyncio
    async def test_still_remaining_after_rechecks_aborts(self):
        from utils.exceptions import LiveStartupAbort
        po = {"odno": "0001", "pdno": "005930", "sll_buy_dvsn_cd": "02"}
        broker = Mock()
        broker.get_pending_orders.return_value = [po]
        broker.cancel_order.return_value = {"success": True}
        r = self._restorer(broker)
        with patch("bot.state_restorer.STARTUP_CANCEL_RECHECK_SEC", 0), \
             pytest.raises(LiveStartupAbort):
            await r._restore_holdings_from_real_account()
        assert broker.get_pending_orders.call_count == 1 + 3        # 발견 1 + 재확인 3


# =============================================================================
# N1 묶음(2026-10-08) — DELTA_REVIEW_1007 N1·N2·N3·N4·N6 + 10-08 실측(PROBE_RESULT_1008)
# =============================================================================
def _gone_row(ccld=0, rmn=0, avg="0"):
    """10-08 실측형 0081R 원주문 행(취소 접수 +2초): cncl_yn 빈 문자열 · cncl_cfrm_qty "0"."""
    return {"odno": "0000012345", "_status": "executed", "ord_qty": "10",
            "tot_ccld_qty": str(ccld), "rmn_qty": str(rmn), "cncl_yn": "",
            "cncl_cfrm_qty": "0", "rjct_qty": "0", "avg_prvs": avg}


def _live_row(ccld=0):
    """8036R(정정취소가능) 행 — 취소가 아직 반영되지 않은 주문."""
    return {"odno": "0000012345", "_status": "pending", "ord_qty": "10",
            "tot_ccld_qty": str(ccld), "psbl_qty": str(10 - ccld)}


_UNKNOWN_ROW = {"odno": "0000012345", "_status": "unknown", "status_unknown": True, "cncl_yn": "N"}


def _no_settle_wait():
    return patch("core.orders.order_timeout.ORDER_CANCEL_SETTLE_WAIT_SECONDS", 0)


def _ledger_setup(statuses):
    """실 FundManager·TSM·전략 + 순서대로 응답하는 get_order_status(목록 소진 뒤 None = 조회 실패)."""
    from core.fund_manager import FundManager
    seq = list(statuses)
    broker = Mock()
    broker.get_order_status.side_effect = lambda oid: seq.pop(0) if seq else None
    broker.cancel_order.return_value = _CANCEL_OK
    telegram = AsyncMock()
    om = _make_om(broker=broker, telegram=telegram)
    fm = FundManager(initial_funds=10_000_000)
    om.set_fund_manager(fm)
    assert fm.reserve_funds("0000012345", 700_000)
    strat = _daytrading_strategy()
    tsm = _real_tsm(om, {DT_KEY: strat})
    slot = _register_slot(tsm)
    slot.is_buying = True
    order = _inject(om, age_sec=400, timeout_sec=300)
    return om, broker, telegram, fm, strat, slot, order


def _alerts(telegram, text):
    return [c for c in telegram.notify_system_status.call_args_list if text in str(c.args[0])]


class TestN1PartialCancelRequery:
    """N1: 사전조회 부분체결 → 잔량 취소 성공 → 재조회 없이 사전조회 수량으로 회계하던 경합."""

    @pytest.mark.asyncio
    async def test_fill_between_precheck_and_partial_cancel_is_accounted(self):
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([
            _live_row(3),                                            # 사전조회: 3/10 체결
            _gone_row(5, avg="70100"), _gone_row(5, avg="70100"),    # 잔량 취소 뒤 연속 2회: 5주
        ])
        with _no_settle_wait():
            await om._handle_timeout(order.order_id)

        assert broker.cancel_order.call_count == 1 and broker.get_order_status.call_count == 3
        assert order.status == OrderStatus.FILLED and order.quantity == 5, "추가 체결 2주가 장부 밖"
        assert order.order_id not in om.pending_orders
        assert fm.invested_funds == pytest.approx(5 * 70100) and fm.reserved_funds == pytest.approx(0)
        assert slot.state == StockState.POSITIONED and slot.position.quantity == 5
        assert strat.daily_trades == 1 and strat.positions["005930"]["quantity"] == 5
        assert om.db_manager.save_real_buy.call_args.kwargs["quantity"] == 5

    @pytest.mark.asyncio
    async def test_requery_failure_marks_confirmed_defers_and_keeps_precheck_floor(self):
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([
            _live_row(3), None,                  # 잔량 취소 뒤 재조회 실패(CB OPEN 등)
            _gone_row(2), _gone_row(2),          # 연기 뒤 0081R 이 사전조회보다 작게 보임
        ])
        with _no_settle_wait():
            await om._handle_timeout(order.order_id)
            assert order.order_id in om.pending_orders and order.order_id in om._cancel_confirmed_ids
            assert om._timeout_defer_counts[order.order_id] == 1
            assert fm.reserved_funds == pytest.approx(700_000) and fm.invested_funds == pytest.approx(0)
            om.db_manager.save_real_buy.assert_not_called()
            await om._handle_timeout(order.order_id)                 # 연기 시한 → _resolve_cancel_confirmed

        assert broker.cancel_order.call_count == 1                   # 잔량 취소 재호출 없음
        assert order.status == OrderStatus.FILLED and order.quantity == 3   # max(사전 3, 재조회 2)
        assert fm.invested_funds == pytest.approx(3 * 70000) and fm.reserved_funds == pytest.approx(0)
        assert slot.position.quantity == 3 and order.order_id not in om._cancel_confirmed_ids


class TestN2CancelAcceptedIsNotFinal:
    """N2(10-08 실측): 취소 접수 직후 조회는 «최종»이 아니다.

    대기 ≥2초 · 8036R 잔존/불명/rmn_qty>0 이면 연기 · «8036R 부재 ∧ 0081R rmn_qty==0» 이 연속 2회
    같은 체결수일 때만 확정 · cncl_yn·cncl_cfrm_qty 는 판정에 쓰지 않는다(실측 '' · '0').
    """

    @pytest.mark.asyncio
    async def test_waits_before_requery_and_needs_two_matching_reads(self):
        from config.constants import ORDER_CANCEL_SETTLE_WAIT_SECONDS
        assert ORDER_CANCEL_SETTLE_WAIT_SECONDS >= 2
        om, broker, telegram, fm, strat, slot, order = _ledger_setup(
            [_live_row(0), _gone_row(0), _gone_row(0)])
        events = []
        status_fn = broker.get_order_status.side_effect
        broker.get_order_status.side_effect = lambda oid: events.append("조회") or status_fn(oid)
        broker.cancel_order.side_effect = lambda *a, **k: events.append("취소") or _CANCEL_OK

        async def fake_sleep(sec, *a, **k):
            events.append(("대기", sec))

        with patch("core.orders.order_timeout.asyncio.sleep", fake_sleep):
            await om._handle_timeout(order.order_id)

        w = ("대기", ORDER_CANCEL_SETTLE_WAIT_SECONDS)
        assert events == ["조회", "취소", w, "조회", w, "조회"]
        assert order.status == OrderStatus.CANCELLED and order.order_id not in om.pending_orders
        assert fm.reserved_funds == pytest.approx(0) and slot.state == StockState.COMPLETED

    @pytest.mark.asyncio
    async def test_still_in_cancellable_list_after_cancel_defers(self):
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([_live_row(0), _live_row(0)])
        with _no_settle_wait():
            await om._handle_timeout(order.order_id)
        assert order.status != OrderStatus.CANCELLED, "8036R 에 살아 있는 주문을 체결 0 으로 닫았다"
        assert order.order_id in om.pending_orders and order.order_id in om._cancel_confirmed_ids
        assert om._timeout_defer_counts[order.order_id] == 1
        assert fm.reserved_funds == pytest.approx(700_000)           # 예약 복원
        assert slot.state == StockState.BUY_PENDING
        assert broker.get_order_status.call_count == 2

    @pytest.mark.asyncio
    async def test_single_zero_read_is_not_final_and_failure_breaks_the_chain(self):
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([
            _live_row(0), _gone_row(0), None,      # 후보 1회 뒤 조회 실패 → 미확정
            _gone_row(0), _gone_row(0),            # 연기 뒤 새로 연속 2회
        ])
        with _no_settle_wait():
            await om._handle_timeout(order.order_id)
            assert order.order_id in om.pending_orders and order.status != OrderStatus.CANCELLED
            await om._handle_timeout(order.order_id)
        assert broker.get_order_status.call_count == 5
        assert order.status == OrderStatus.CANCELLED and fm.reserved_funds == pytest.approx(0)
        assert slot.state == StockState.COMPLETED and strat.daily_trades == 0

    @pytest.mark.asyncio
    async def test_reads_must_agree_on_fill_count(self):
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([
            _live_row(0), _gone_row(0), _gone_row(2, avg="70050"),   # 0 → 2 불일치 = 미확정
            _gone_row(2, avg="70050"),                               # 연기 뒤: 직전 후보 2 와 일치 → 확정
        ])
        with _no_settle_wait():
            await om._handle_timeout(order.order_id)
            assert order.order_id in om.pending_orders and order.status != OrderStatus.CANCELLED
            await om._handle_timeout(order.order_id)
        assert broker.get_order_status.call_count == 4
        assert order.status == OrderStatus.FILLED and order.quantity == 2
        assert fm.invested_funds == pytest.approx(2 * 70050) and fm.reserved_funds == pytest.approx(0)

    @pytest.mark.asyncio
    async def test_remaining_qty_still_shown_after_partial_cancel_defers(self):
        om, broker, telegram, fm, strat, slot, order = _ledger_setup(
            [_live_row(3), _gone_row(3, rmn=7), _gone_row(3, rmn=7)])   # 같은 값 2회여도 잔량>0 이면 미확정
        with _no_settle_wait():
            await om._handle_timeout(order.order_id)
        assert broker.get_order_status.call_count == 2                  # 후보 아님 → 곧바로 연기
        assert order.order_id in om.pending_orders and order.order_id in om._cancel_confirmed_ids
        assert order.status != OrderStatus.FILLED and fm.invested_funds == pytest.approx(0)
        om.db_manager.save_real_buy.assert_not_called()
    # 연기 소진(8036R 행 ×20 → CANCELLED) 테스트는 I1 결정으로 기대가 바뀌어
    # TestI1ResendCancelOnceWhenStillCancellable 로 옮겼다(같은 입력 · 예약 유지 + 경보).


class TestN3DeferCountNotResetByCancel:
    """N3: 경로 A(조회 실패 연기) 도중 취소가 성공해도 연기 횟수를 처음부터 다시 세지 않는다(합산 ≤5)."""

    @pytest.mark.asyncio
    async def test_path_a_count_carries_into_path_b(self):
        from config.constants import ORDER_TIMEOUT_DEFER_MAX
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([None, None, None, _live_row(0)])
        broker.cancel_order.side_effect = [_NOT_FOUND] * 3 + [_CANCEL_OK]
        with patch("core.orders.order_timeout.ORDER_CANCEL_RETRY_INTERVAL", 0), _no_settle_wait():
            await om._handle_timeout(order.order_id)        # 경로 A: 취소 실패 + 재확인 실패 → 연기 1
            assert om._timeout_defer_counts[order.order_id] == 1
            await om._handle_timeout(order.order_id)        # 취소 성공 → 재조회 실패 → 경로 B 연기
            assert order.order_id in om._cancel_confirmed_ids
            assert om._timeout_defer_counts[order.order_id] == 2, "취소 성공이 연기 횟수를 지웠다"
            calls = 2
            while order.order_id in om.pending_orders and calls < 20:
                await om._handle_timeout(order.order_id)
                calls += 1
        assert calls == ORDER_TIMEOUT_DEFER_MAX + 1          # 합산 연기 5회 + 종결 1회
        assert len(_alerts(telegram, "수동 확인 필요")) == 1


class TestN4ViGuardSkipsCancelConfirmed:
    """N4: 확인 표식 주문에 VI 가 걸려도 매 루프 「[종목 VI] … 취소」 경보 + 종결 지연을 만들지 않는다."""

    @pytest.mark.asyncio
    async def test_vi_on_confirmed_order_alerts_once_and_still_resolves(self):
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([_live_row(0), None])
        with _no_settle_wait():
            await om._handle_timeout(order.order_id)        # 취소 접수 · 재조회 실패 → 확인 표식 + 연기
        assert order.order_id in om._cancel_confirmed_ids
        cb = Mock()
        cb.is_market_halted.return_value = False
        cb.is_vi_active.return_value = True
        with patch("config.market_hours.get_circuit_breaker_state", return_value=cb), _no_settle_wait():
            for _ in range(5):
                await om._monitor_pending_orders()
            assert len(_alerts(telegram, "[종목 VI]")) == 1
            assert broker.cancel_order.call_count == 1
            # 연기 시한 도래 → VI 가 켜져 있어도 종결 경로(_resolve_cancel_confirmed)가 돈다
            broker.get_order_status.side_effect = lambda oid: _gone_row(0)
            om.order_timeouts[order.order_id] = now_kst() - timedelta(seconds=1)
            await om._monitor_pending_orders()
        assert order.order_id not in om.pending_orders and order.status == OrderStatus.CANCELLED
        assert len(_alerts(telegram, "[종목 VI]")) == 1
        # m3: 취소를 보내지 않으므로 「진행 중 매수 주문 취소」 가 아니라 확정 대기 문구
        assert len(_alerts(telegram, "취소 접수 주문에 VI — 확정 대기")) == 1
        assert not _alerts(telegram, "진행 중 매수 주문 취소")


class TestN6StatusUnknownAfterCancelDefers:
    """N6: 취소 뒤 «두 조회 성공 · 어디에도 없음»(status_unknown)을 체결 0 으로 닫지 않는다(B3)."""

    @pytest.mark.asyncio
    async def test_unknown_after_cancel_is_not_zero_fill(self):
        om, broker, telegram, fm, strat, slot, order = _ledger_setup(
            [_live_row(0), _UNKNOWN_ROW, _UNKNOWN_ROW])
        with _no_settle_wait():
            await om._handle_timeout(order.order_id)
            assert order.status != OrderStatus.CANCELLED and order.order_id in om.pending_orders
            assert order.order_id in om._cancel_confirmed_ids
            assert fm.reserved_funds == pytest.approx(700_000)
            await om._handle_timeout(order.order_id)        # 연기 뒤에도 불명 → 다시 연기
        assert order.order_id in om.pending_orders and om._timeout_defer_counts[order.order_id] == 2
        assert slot.state == StockState.BUY_PENDING and not _alerts(telegram, "수동 확인 필요")
        assert broker.cancel_order.call_count == 1, "불명(status_unknown)인데 취소를 재전송했다"   # m-b


# =============================================================================
# 리뷰 REVIEW_N1_1008 I1·m2 (🔒 사장님 10-08 「I1 재취소 1회 추가 뒤 머지」)
# =============================================================================
class TestI1ResendCancelOnceWhenStillCancellable:
    """I1: 취소 접수 뒤 연기 재처리에서도 8036R(정정취소가능) 행이 보이면 취소를 딱 1회 재전송 →
    다시 대기 + 연속 2회 규칙. 연기 합산 상한은 그대로 · 소진 때도 8036R 행이면 CANCELLED 로 닫지 않고
    예약 유지 + 「수동 확인」 경보 1회 · 아는 체결분 회계는 그대로."""

    @pytest.mark.asyncio
    async def test_resend_once_then_gone_settles_as_cancelled(self):
        from config.constants import ORDER_CANCEL_SETTLE_WAIT_SECONDS
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([
            _live_row(0),                  # 사전조회
            _live_row(0),                  # 취소 접수 +2초: 8036R 잔존 → 연기 1
            _live_row(0),                  # 연기 뒤 재처리: 또 8036R → 취소 재전송
            _gone_row(0), _gone_row(0),    # 재전송 뒤 대기 + 연속 2회 = 확정(체결 0)
        ])
        events = []
        status_fn = broker.get_order_status.side_effect
        broker.get_order_status.side_effect = lambda oid: events.append("조회") or status_fn(oid)
        broker.cancel_order.side_effect = lambda *a, **k: events.append("취소") or _CANCEL_OK

        async def fake_sleep(sec, *a, **k):
            events.append(("대기", sec))

        with patch("core.orders.order_timeout.asyncio.sleep", fake_sleep):
            await om._handle_timeout(order.order_id)
            assert order.order_id in om._cancel_confirmed_ids
            assert om._timeout_defer_counts[order.order_id] == 1
            await om._handle_timeout(order.order_id)          # 연기 시한 → 재처리

        w = ("대기", ORDER_CANCEL_SETTLE_WAIT_SECONDS)
        assert events == ["조회", "취소", w, "조회",              # 취소 접수 → 8036R 잔존 → 연기
                          "조회", "취소", w, "조회", w, "조회"]   # 또 8036R → 재전송 1회 → 대기 + 연속 2회
        assert broker.cancel_order.call_count == 2
        assert order.status == OrderStatus.CANCELLED and order.order_id not in om.pending_orders
        assert fm.reserved_funds == pytest.approx(0) and slot.state == StockState.COMPLETED
        assert strat.daily_trades == 0 and not _alerts(telegram, "수동 확인 필요")
        assert order.order_id not in getattr(om, "_cancel_resent_ids", set())   # 종결 때 표식 정리

    @pytest.mark.asyncio
    @pytest.mark.parametrize("resend_reply", [_CANCEL_OK, _NOT_FOUND], ids=["resend_ok", "resend_fail"])
    async def test_still_cancellable_to_the_end_keeps_reservation_with_single_alert(self, resend_reply):
        """옛 `test_defer_exhausted_closes_with_single_manual_alert`(같은 입력 → CANCELLED)를 대체 — 기대 반전."""
        from config.constants import ORDER_TIMEOUT_DEFER_MAX
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([_live_row(0)] * 30)
        broker.cancel_order.side_effect = [_CANCEL_OK, resend_reply]
        with patch("core.orders.order_timeout.ORDER_CANCEL_RETRY_INTERVAL", 0), _no_settle_wait():
            for _ in range(ORDER_TIMEOUT_DEFER_MAX):
                await om._handle_timeout(order.order_id)
                assert order.order_id in om.pending_orders
            assert not _alerts(telegram, "수동 확인 필요")
            await om._handle_timeout(order.order_id)          # 연기 합산 상한 소진
        assert broker.cancel_order.call_count == 2, "재전송은 주문당 정확히 1회(실패해도 다시 안 보냄)"
        assert order.status != OrderStatus.CANCELLED and order.order_id in om.pending_orders
        assert fm.has_reservation(order.order_id) and fm.reserved_funds == pytest.approx(700_000)
        assert slot.state == StockState.BUY_PENDING and strat.daily_trades == 0
        alerts = _alerts(telegram, "수동 확인 필요")
        assert len(alerts) == 1 and "예약 유지" in str(alerts[0].args[0])
        # 자동 처리 정지 — 연기 폭(45초)이 몇 번 지나도 재취소·재조회·경보 반복 없음
        # (종료 시 미체결 일괄 취소 대상으로 남는다)
        queries = broker.get_order_status.call_count
        later = now_kst() + timedelta(minutes=10)
        with patch("core.orders.order_monitor.now_kst", return_value=later), _no_settle_wait():
            for _ in range(3):
                await om._monitor_pending_orders()
        assert broker.cancel_order.call_count == 2 and broker.get_order_status.call_count == queries
        assert len(_alerts(telegram, "수동 확인 필요")) == 1
        assert order.order_id in om.pending_orders

    @pytest.mark.asyncio
    async def test_known_partial_fill_still_accounted_when_remainder_stays_cancellable(self):
        from config.constants import ORDER_TIMEOUT_DEFER_MAX
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([_live_row(3)] * 30)
        with _no_settle_wait():
            for _ in range(ORDER_TIMEOUT_DEFER_MAX + 1):
                await om._handle_timeout(order.order_id)
        assert broker.cancel_order.call_count == 2                     # 잔량 취소 1 + 재전송 1
        assert order.status == OrderStatus.FILLED and order.quantity == 3
        assert fm.invested_funds == pytest.approx(3 * 70000)
        assert slot.state == StockState.POSITIONED and slot.position.quantity == 3
        assert strat.daily_trades == 1
        assert len(_alerts(telegram, "수동 확인 필요")) == 1


class TestM2CancelConfirmQtyIsNotFillQty:
    """m2: 0081R `cncl_cfrm_qty`(취소확인수량)는 체결수량 대체 후보가 아니다."""

    def test_cncl_cfrm_qty_alone_is_not_read_as_filled(self):
        from api.kis_api_manager import KISAPIManager
        mgr = KISAPIManager()
        daily = pd.DataFrame([{"odno": "0000012345", "ord_qty": "10", "cncl_cfrm_qty": "10",
                               "pdno": "005930", "ord_dvsn": "00", "sll_buy_dvsn_cd": "02"}])
        mgr._call_api_with_retry = Mock(side_effect=[pd.DataFrame(), daily])
        status = mgr.get_order_status("0000012345")
        assert mgr._call_api_with_retry.call_count == 2
        assert status["tot_ccld_qty"] == "0", "취소확인수량 10 을 체결 10 으로 읽었다"


# =============================================================================
# 델타 리뷰 bc7f569..9ccf51c A·m-a·m-b (2026-10-08 저녁)
# =============================================================================
class TestDeltaReviewSellNotHeldAndResendGuards:
    """A: 소진 보류(예약·슬롯 유지)는 매수만 — 매도는 종전처럼 닫아 «보유 중» 복귀(손절·장마감 청산 대상) + 경보 1회.
    m-a: 재전송 없이 곧장 보류되지 않는다(상한 예외로 연기 1회 더 → 재전송 1회 먼저).
    m-b: 연기 재처리 조회가 실패(None)면 8036R 잔존을 모르므로 재전송 0."""

    @pytest.mark.asyncio
    async def test_sell_order_still_cancellable_closes_back_to_positioned_with_single_alert(self):
        from config.constants import ORDER_TIMEOUT_DEFER_MAX
        seq = [_live_row(0)] * 30
        broker = Mock()
        broker.get_order_status.side_effect = lambda oid: seq.pop(0) if seq else None
        broker.cancel_order.return_value = _CANCEL_OK
        telegram = AsyncMock()
        om = _make_om(broker=broker, telegram=telegram)
        tsm = _real_tsm(om, {DT_KEY: _daytrading_strategy()})
        slot = _register_slot(tsm, state=StockState.SELL_PENDING)
        slot.set_position(10, 70000)
        slot.is_selling = True
        order = _inject(om, otype=OrderType.SELL, age_sec=400, timeout_sec=180)
        with _no_settle_wait():
            for _ in range(ORDER_TIMEOUT_DEFER_MAX):
                await om._handle_timeout(order.order_id)
                assert order.order_id in om.pending_orders
            assert not _alerts(telegram, "매도 취소 미반영")
            await om._handle_timeout(order.order_id)          # 연기 합산 상한 소진
        assert broker.cancel_order.call_count == 2                 # 취소 1 + 재전송 1
        assert order.status == OrderStatus.CANCELLED and order.order_id not in om.pending_orders, \
            "매도 주문을 보류해 슬롯이 «매도 주문 중»에 고정됐다(손절·청산 밖)"
        assert order.order_id not in om._cancel_confirmed_ids
        assert slot.state == StockState.POSITIONED and slot.is_selling is False
        assert slot.position.quantity == 10
        assert len(_alerts(telegram, "매도 취소 미반영(8036R 잔존) — HTS 확인")) == 1
        assert not _alerts(telegram, "예약 유지")

    @pytest.mark.asyncio
    async def test_path_a_exhausted_then_cancel_ok_resends_once_before_hold(self):
        from config.constants import ORDER_TIMEOUT_DEFER_MAX
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([])
        path_a = {"on": True}       # 경로 A: 체결조회 실패(CB OPEN 등) + 취소 실패(목록에 없음)
        broker.get_order_status.side_effect = lambda oid: None if path_a["on"] else _live_row(0)
        broker.cancel_order.side_effect = lambda *a, **k: _NOT_FOUND if path_a["on"] else _CANCEL_OK
        with patch("core.orders.order_timeout.ORDER_CANCEL_RETRY_INTERVAL", 0), _no_settle_wait():
            for _ in range(ORDER_TIMEOUT_DEFER_MAX):
                await om._handle_timeout(order.order_id)
            assert om._timeout_defer_counts[order.order_id] == ORDER_TIMEOUT_DEFER_MAX
            path_a["on"] = False
            before = broker.cancel_order.call_count
            await om._handle_timeout(order.order_id)          # 취소 성공 → +2초 8036R 잔존 · 상한 이미 소진
            assert broker.cancel_order.call_count == before + 1
            assert order.order_id in om.pending_orders and order.order_id in om.order_timeouts, \
                "재전송 없이 곧장 보류했다"
            assert not _alerts(telegram, "수동 확인 필요")
            await om._handle_timeout(order.order_id)          # 상한 예외 1회 → 취소 재전송 1회
        assert broker.cancel_order.call_count == before + 2, "재전송이 정확히 1회가 아니다"
        assert order.status != OrderStatus.CANCELLED and order.order_id in om.pending_orders
        assert order.order_id not in om.order_timeouts            # 재전송 뒤에도 8036R → 보류(자동 처리 정지)
        assert fm.reserved_funds == pytest.approx(700_000) and slot.state == StockState.BUY_PENDING
        alerts = _alerts(telegram, "수동 확인 필요")
        assert len(alerts) == 1 and "예약 유지" in str(alerts[0].args[0])

    @pytest.mark.asyncio
    async def test_requery_failure_on_reprocess_does_not_resend(self):
        om, broker, telegram, fm, strat, slot, order = _ledger_setup(
            [_live_row(0), _live_row(0)])                     # 이후 조회 = None(실패)
        with _no_settle_wait():
            await om._handle_timeout(order.order_id)          # 취소 접수 → +2초 8036R 잔존 → 연기 1
            await om._handle_timeout(order.order_id)          # 연기 재처리: 조회 실패
        assert broker.cancel_order.call_count == 1, "조회 실패인데 취소를 재전송했다"
        assert order.order_id not in om._cancel_resent_ids
        assert order.order_id in om.pending_orders and om._timeout_defer_counts[order.order_id] == 2
        assert fm.reserved_funds == pytest.approx(700_000) and slot.state == StockState.BUY_PENDING
        assert not _alerts(telegram, "수동 확인 필요")


# =============================================================================
# 델타 리뷰 9ccf51c..cf3cbca N-1·m-2 (2026-10-08 저녁)
# =============================================================================
def _sell_setup(get_status):
    """매도 10주 주문(슬롯 SELL_PENDING · 보유 10주) + 주어진 get_order_status 응답 함수."""
    broker = Mock()
    broker.get_order_status.side_effect = get_status
    broker.cancel_order.return_value = _CANCEL_OK
    telegram = AsyncMock()
    om = _make_om(broker=broker, telegram=telegram)
    tsm = _real_tsm(om, {DT_KEY: _daytrading_strategy()})
    slot = _register_slot(tsm, state=StockState.SELL_PENDING)
    slot.set_position(10, 70000)
    slot.is_selling = True
    order = _inject(om, otype=OrderType.SELL, age_sec=400, timeout_sec=180)
    return om, broker, telegram, slot, order


class TestDeltaReviewN1LingeringSeenThenQueryFails:
    """N-1: 취소 접수 뒤 8036R 에서 본 적 있는 주문은 소진 회차(및 m-a 예외 회차) 조회가 실패(None)여도
    «8036R 잔존»으로 취급 — 매수 = 보류(예약·슬롯 유지 + 경보 1회) · 매도 = 종결(«보유 중» 복귀) + 매도 경보.
    m-a 예외는 재전송 표식과 다른 별도 표식으로 주문당 1회. m-2: 매도 + 경로 A 소진 → 예외 → 재전송 → 종결."""

    @pytest.mark.asyncio
    async def test_px_exception_round_query_failure_keeps_buy_held(self):
        from config.constants import ORDER_TIMEOUT_DEFER_MAX
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([])
        path_a = {"on": True}       # 경로 A: 체결조회 실패 + 취소 실패
        after = [_live_row(0), _live_row(0)]   # 사전조회 · 취소 접수 +2초 8036R 잔존 → 그 뒤 조회 실패
        broker.get_order_status.side_effect = (
            lambda oid: None if path_a["on"] else (after.pop(0) if after else None))
        broker.cancel_order.side_effect = lambda *a, **k: _NOT_FOUND if path_a["on"] else _CANCEL_OK
        with patch("core.orders.order_timeout.ORDER_CANCEL_RETRY_INTERVAL", 0), _no_settle_wait():
            for _ in range(ORDER_TIMEOUT_DEFER_MAX):
                await om._handle_timeout(order.order_id)
            path_a["on"] = False
            before = broker.cancel_order.call_count
            await om._handle_timeout(order.order_id)          # 취소 성공 → 8036R 잔존 → 상한 예외 1회
            assert order.order_id in om.order_timeouts and not _alerts(telegram, "수동 확인 필요")
            await om._handle_timeout(order.order_id)          # 예외 회차: 조회 실패(None)
        assert broker.cancel_order.call_count == before + 1, "조회 실패인데 취소를 재전송했다"
        assert order.status != OrderStatus.CANCELLED and order.order_id in om.pending_orders, \
            "예외 회차 조회 실패로 매수를 종결했다(예약 해제·슬롯 COMPLETED)"
        assert order.order_id not in om.order_timeouts              # 보류 = 자동 처리 정지
        assert fm.has_reservation(order.order_id) and fm.reserved_funds == pytest.approx(700_000)
        assert slot.state == StockState.BUY_PENDING and strat.daily_trades == 0
        alerts = _alerts(telegram, "수동 확인 필요")
        assert len(alerts) == 1 and "예약 유지" in str(alerts[0].args[0])
        assert not _alerts(telegram, "체결수량 확인 불가")

    @pytest.mark.asyncio
    async def test_py_buy_exhaustion_round_query_failure_after_repeated_8036r_is_held(self):
        from config.constants import ORDER_TIMEOUT_DEFER_MAX
        # 8036R 7행 = 사전조회·접수 뒤(연기 1) · 재처리·재전송 뒤(연기 2) · 연기 3·4·5 → 소진 회차 조회 실패
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([_live_row(0)] * 7)
        with _no_settle_wait():
            for _ in range(ORDER_TIMEOUT_DEFER_MAX):
                await om._handle_timeout(order.order_id)
                assert order.order_id in om.pending_orders
            assert broker.get_order_status.call_count == 7
            await om._handle_timeout(order.order_id)          # 소진 회차: 조회 실패(None)
        assert broker.get_order_status.call_count == 8 and broker.cancel_order.call_count == 2
        assert order.status != OrderStatus.CANCELLED and order.order_id in om.pending_orders, \
            "8036R 반복 뒤 소진 회차 조회 실패로 매수를 종결했다"
        assert order.order_id not in om.order_timeouts
        assert fm.has_reservation(order.order_id) and fm.reserved_funds == pytest.approx(700_000)
        assert slot.state == StockState.BUY_PENDING and strat.daily_trades == 0
        alerts = _alerts(telegram, "수동 확인 필요")
        assert len(alerts) == 1 and "예약 유지" in str(alerts[0].args[0])
        assert not _alerts(telegram, "체결수량 확인 불가")

    @pytest.mark.asyncio
    async def test_py_sell_exhaustion_round_query_failure_after_repeated_8036r_closes(self):
        from config.constants import ORDER_TIMEOUT_DEFER_MAX
        seq = [_live_row(0)] * 7
        om, broker, telegram, slot, order = _sell_setup(lambda oid: seq.pop(0) if seq else None)
        with _no_settle_wait():
            for _ in range(ORDER_TIMEOUT_DEFER_MAX):
                await om._handle_timeout(order.order_id)
                assert order.order_id in om.pending_orders
            await om._handle_timeout(order.order_id)          # 소진 회차: 조회 실패(None)
        assert broker.get_order_status.call_count == 8 and broker.cancel_order.call_count == 2
        assert order.status == OrderStatus.CANCELLED and order.order_id not in om.pending_orders
        assert slot.state == StockState.POSITIONED and slot.is_selling is False
        assert slot.position.quantity == 10
        assert len(_alerts(telegram, "매도 취소 미반영(8036R 잔존) — HTS 확인")) == 1
        assert not _alerts(telegram, "체결수량 확인 불가") and not _alerts(telegram, "예약 유지")
        assert order.order_id not in om._cancel_lingering_seen_ids     # 종결 때 표식 정리

    @pytest.mark.asyncio
    async def test_m2_sell_path_a_exhausted_exception_resend_then_closes(self):
        from config.constants import ORDER_TIMEOUT_DEFER_MAX
        path_a = {"on": True}
        om, broker, telegram, slot, order = _sell_setup(
            lambda oid: None if path_a["on"] else _live_row(0))
        broker.cancel_order.side_effect = lambda *a, **k: _NOT_FOUND if path_a["on"] else _CANCEL_OK
        with patch("core.orders.order_timeout.ORDER_CANCEL_RETRY_INTERVAL", 0), _no_settle_wait():
            for _ in range(ORDER_TIMEOUT_DEFER_MAX):
                await om._handle_timeout(order.order_id)
            assert om._timeout_defer_counts[order.order_id] == ORDER_TIMEOUT_DEFER_MAX
            path_a["on"] = False
            before = broker.cancel_order.call_count
            await om._handle_timeout(order.order_id)          # 취소 성공 → 8036R 잔존 → 상한 예외 1회
            assert broker.cancel_order.call_count == before + 1
            assert order.order_id in om.pending_orders and order.order_id in om.order_timeouts
            assert not _alerts(telegram, "매도 취소 미반영")
            await om._handle_timeout(order.order_id)          # 재전송 1회 → 그래도 8036R → 종결
        assert broker.cancel_order.call_count == before + 2, "재전송이 정확히 1회가 아니다"
        assert order.status == OrderStatus.CANCELLED and order.order_id not in om.pending_orders
        assert slot.state == StockState.POSITIONED and slot.is_selling is False
        assert slot.position.quantity == 10
        assert len(_alerts(telegram, "매도 취소 미반영(8036R 잔존) — HTS 확인")) == 1
        assert not _alerts(telegram, "예약 유지") and not _alerts(telegram, "체결수량 확인 불가")
        assert order.order_id not in om._cancel_lingering_seen_ids     # 종결 때 표식 정리
        assert order.order_id not in om._defer_extra_used_ids


# =============================================================================
# 10-19 전 후속 묶음(2026-10-09 · fix/real-flow-7) — 델타 리뷰 cf3cbca..dffa87b W-1
# =============================================================================
def _w1_row():
    """8036R 조회만 실패 + 0081R 성공일 때 broker 가 주는 꼴: 0081R 원주문 행(_status executed) ·
    체결 0 · 잔량 10(취소 미반영) — «8036R 에 없음»과 구분되지 않는다(framework/broker.py)."""
    return _gone_row(0, rmn=10)


class TestW1PendingQueryFailsButDailyRowShowsOpen:
    """W-1: 취소 접수 뒤 8036R 에서 본 적 있는 매수 주문의 소진 회차 조회가 «0081R 행(체결 0 ∧ 잔량>0)»으로
    오면(8036R 조회만 실패한 꼴) None 과 같이 «8036R 잔존»으로 취급 → 보류(예약·슬롯 유지 + 경보 1회).
    관측 표식이 없으면 종전대로 «확인 불가» 종결(N3 불변)."""

    @pytest.mark.asyncio
    async def test_seen_in_8036r_then_daily_open_row_on_exhaustion_is_held(self):
        from config.constants import ORDER_TIMEOUT_DEFER_MAX
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([_live_row(0)] * 7 + [_w1_row()])
        with _no_settle_wait():
            for _ in range(ORDER_TIMEOUT_DEFER_MAX):
                await om._handle_timeout(order.order_id)
                assert order.order_id in om.pending_orders
            await om._handle_timeout(order.order_id)          # 소진 회차: 0081R 행(체결 0 · 잔량 10)
        assert broker.get_order_status.call_count == 8 and broker.cancel_order.call_count == 2
        assert order.status != OrderStatus.CANCELLED and order.order_id in om.pending_orders, \
            "8036R 조회 실패 꼴(0081R 잔량>0)을 «8036R 에 없음»으로 읽고 매수를 종결했다"
        assert order.order_id not in om.order_timeouts
        assert fm.has_reservation(order.order_id) and fm.reserved_funds == pytest.approx(700_000)
        assert slot.state == StockState.BUY_PENDING and strat.daily_trades == 0
        alerts = _alerts(telegram, "수동 확인 필요")
        assert len(alerts) == 1 and "예약 유지" in str(alerts[0].args[0])
        assert not _alerts(telegram, "체결수량 확인 불가")

    @pytest.mark.asyncio
    async def test_daily_open_row_without_8036r_observation_closes_as_before(self):
        from config.constants import ORDER_TIMEOUT_DEFER_MAX
        om, broker, telegram, fm, strat, slot, order = _ledger_setup([_live_row(0)] + [_w1_row()] * 10)
        with _no_settle_wait():
            for _ in range(ORDER_TIMEOUT_DEFER_MAX + 1):
                await om._handle_timeout(order.order_id)
        assert broker.cancel_order.call_count == 1                 # 8036R 행을 못 봤으니 재전송 0
        assert order.order_id not in om._cancel_lingering_seen_ids
        assert order.status == OrderStatus.CANCELLED and order.order_id not in om.pending_orders
        assert fm.reserved_funds == pytest.approx(0) and slot.state == StockState.COMPLETED
        assert len(_alerts(telegram, "체결수량 확인 불가")) == 1
        assert not _alerts(telegram, "예약 유지")

    def test_open_row_shape_is_only_unfilled_with_remaining_on_daily_row(self):
        from core.orders.order_timeout import OrderTimeoutMixin as M
        assert M._executed_row_still_open(_w1_row()) is True
        assert M._executed_row_still_open(_gone_row(0)) is False          # 잔량 0 = 취소 반영(확정 후보)
        assert M._executed_row_still_open(_gone_row(3, rmn=7)) is False   # 체결 있음 = 아는 체결분 경로
        assert M._executed_row_still_open(_live_row(0)) is False          # 8036R 행은 _still_cancellable 이 본다
        assert M._executed_row_still_open(_UNKNOWN_ROW) is False
        assert M._executed_row_still_open(None) is False

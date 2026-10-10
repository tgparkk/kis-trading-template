"""
[기업행위 의심] 기준가 불연속 경보 — 실전 전용 · 판정 불변 (2026-10-10 사장님 (a′))

근거: 페이퍼 000500 2026-06-30 09:05:11 «손절 실행 (-37.52%)» — 무상증자 권리락으로
기준가가 343,000 → ≈233,500 으로 조정됐는데 평단(346,500)은 그대로라 가짜 손절이 났다.

검증 축:
  1) detect_base_price_gap 임계(정확히 2% 미경보 · 2.01% 경보 · 이상값 None)
  2) DailyOnceAlerter 하루 1번 · 날짜 바뀌면 다시
  3) 페이퍼(True·없음) → 즉시 반환: DB 조회 0 · 로그 0 · 상태 생성 0
  4) 킬 스위치 off → 같은 무동작
  5) 훅 안의 예외 → 밖으로 안 샌다 · 매도 흐름 동일
  6) 회귀: 같은 표본 포지션의 매도 판단(호출 인자)이 훅 on/off 에서 같다
DB·KIS·텔레그램은 전부 mock 이다.
"""
import asyncio
import math
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pandas as pd
import pytest

import core.trading.position_monitor as pm_mod
from core.models import Position, StockState, TradingStock
from core.trading.corp_action_price_alert import (
    ALERT_PREFIX,
    KILL_SWITCH_ENV,
    CorpActionPriceAlertHook,
    DailyOnceAlerter,
    detect_base_price_gap,
    is_alert_enabled,
)
from core.trading.position_monitor import PositionMonitor

KST = timezone(timedelta(hours=9))
# 2026-10-13(화) 10:00 — 직전 거래일 = 10-12(월). 09:00~09:05 손절 유예 밖.
FIXED_NOW = datetime(2026, 10, 13, 10, 0, 0, tzinfo=KST)
TRADE_DATE = FIXED_NOW.date()
PREV_TRADING_DAY = date(2026, 10, 12)


# ---------------------------------------------------------------------------
# 1) 순수 함수 · 킬 스위치
# ---------------------------------------------------------------------------

class TestDetectBasePriceGap:
    def test_exactly_two_percent_does_not_alert(self):
        assert detect_base_price_gap(102, 100) is None
        assert detect_base_price_gap(98, 100) is None
        assert detect_base_price_gap(102_000, 100_000) is None

    def test_just_over_two_percent_alerts(self):
        r_up = detect_base_price_gap(102.01, 100)
        r_dn = detect_base_price_gap(97.99, 100)
        assert r_up == pytest.approx(1.0201)
        assert r_dn == pytest.approx(0.9799)

    def test_000500_like_exrights_ratio(self):
        # 06-29 종가 343,000 · 06-30 시가 240,000 대 기준가(≈조정값) 233,500 가정
        assert detect_base_price_gap(233_500, 343_000) == pytest.approx(233_500 / 343_000)

    @pytest.mark.parametrize("base, prev", [
        (0, 100), (100, 0), (-1, 100), (100, -5), (None, 100), (100, None),
        ("abc", 100), (float("nan"), 100), (100, float("inf")),
    ])
    def test_invalid_prices_return_none(self, base, prev):
        assert detect_base_price_gap(base, prev) is None

    def test_custom_threshold(self):
        assert detect_base_price_gap(104, 100, threshold=0.05) is None
        assert detect_base_price_gap(106, 100, threshold=0.05) == pytest.approx(1.06)


class TestKillSwitch:
    @pytest.mark.parametrize("raw, expected", [
        (None, True), ("on", True), ("ON", True), ("", True), ("garbage", True),
        ("off", False), (" OFF ", False), ("Off", False),
    ])
    def test_values(self, raw, expected):
        env = {} if raw is None else {KILL_SWITCH_ENV: raw}
        assert is_alert_enabled(env) is expected


class TestDailyOnceAlerter:
    def test_once_per_day_per_stock(self):
        a = DailyOnceAlerter()
        d = date(2026, 10, 13)
        assert a.should_fire(d, "000500") is True
        assert a.should_fire(d, "000500") is False
        assert a.should_fire(d, "475460") is True   # 다른 종목은 별개
        assert a.should_fire(d, "475460") is False

    def test_day_rollover_fires_again_and_prunes(self):
        a = DailyOnceAlerter()
        d1, d2 = date(2026, 10, 13), date(2026, 10, 14)
        assert a.should_fire(d1, "000500") is True
        assert a.should_fire(d2, "000500") is True
        assert a.should_fire(d2, "000500") is False
        assert all(k[0] == d2 for k in a._fired)   # 지난 날 키는 정리됨


# ---------------------------------------------------------------------------
# 2) 훅(상태·DB 캐시·경보) — 이벤트 루프 위에서
# ---------------------------------------------------------------------------

def _daily_df(prev_close, last_date=PREV_TRADING_DAY):
    return pd.DataFrame({
        "date": pd.to_datetime([last_date - timedelta(days=1), last_date]),
        "open": [prev_close, prev_close], "high": [prev_close, prev_close],
        "low": [prev_close, prev_close], "close": [prev_close * 0.99, prev_close],
        "volume": [1000.0, 1000.0],
    })


async def _drain(hook, timeout=2.0):
    """executor 조회·텔레그램 태스크가 끝날 때까지 양보."""
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while hook._pending and loop.time() < end:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0)


def _check_kwargs(**over):
    kw = dict(trade_date=TRADE_DATE, stock_code="000500", stock_name="가온전선",
              quantity=1, avg_price=346_500, profit_rate=(210_500 - 346_500) / 346_500,
              stop_loss_rate=0.10, target_profit_rate=0.10)
    kw.update(over)
    return kw


def _warnings(logger):
    return [c.args[0] for c in logger.warning.call_args_list]


class TestHook:
    async def test_gap_alerts_once_with_telegram_and_exit_hint(self):
        logger = Mock()
        repo = Mock()
        repo.get_daily_prices = Mock(return_value=_daily_df(343_000))
        tg = Mock()
        tg.notify_system_status = AsyncMock()
        hook = CorpActionPriceAlertHook(logger)
        hook.remember_base_price("000500", 233_500, TRADE_DATE)

        # 첫 틱: DB 조회는 루프 밖에서 진행 중 → 판정 보류(None)
        assert hook.check(**_check_kwargs(price_repo=repo, telegram=tg)) is None
        await _drain(hook)
        ratio = hook.check(**_check_kwargs(price_repo=repo, telegram=tg))
        await _drain(hook)
        assert ratio == pytest.approx(233_500 / 343_000)

        w = _warnings(logger)
        assert len(w) == 2
        assert w[0].startswith(ALERT_PREFIX) and "000500" in w[0]
        assert "233,500" in w[0] and "343,000" in w[0] and "보유 1주" in w[0] and "346,500" in w[0]
        assert w[1].startswith(ALERT_PREFIX)
        assert "손절/익절 판정이 기업행위 때문일 수 있음 — 수동 확인" in w[1]
        assert tg.notify_system_status.await_count == 2

        # 같은 날 반복 틱: 추가 경보 0 · DB 재조회 0
        for _ in range(3):
            hook.check(**_check_kwargs(price_repo=repo, telegram=tg))
        await _drain(hook)
        assert len(_warnings(logger)) == 2
        assert tg.notify_system_status.await_count == 2
        assert repo.get_daily_prices.call_count == 1

    async def test_no_gap_no_alert(self):
        logger = Mock()
        repo = Mock(get_daily_prices=Mock(return_value=_daily_df(343_000)))
        hook = CorpActionPriceAlertHook(logger)
        hook.remember_base_price("000500", 343_000, TRADE_DATE)
        hook.check(**_check_kwargs(price_repo=repo, telegram=None))
        await _drain(hook)
        assert hook.check(**_check_kwargs(price_repo=repo, telegram=None)) is None
        logger.warning.assert_not_called()

    async def test_gap_without_exit_condition_only_gap_alert(self):
        logger = Mock()
        repo = Mock(get_daily_prices=Mock(return_value=_daily_df(10_000)))
        hook = CorpActionPriceAlertHook(logger)
        hook.remember_base_price("000500", 10_500, TRADE_DATE)   # +5% (병합 아닌 작은 조정 가정)
        kw = _check_kwargs(avg_price=10_000, profit_rate=0.03)
        hook.check(**kw, price_repo=repo, telegram=None)
        await _drain(hook)
        assert hook.check(**kw, price_repo=repo, telegram=None) == pytest.approx(1.05)
        w = _warnings(logger)
        assert len(w) == 1 and "손절/익절" not in w[0]

    async def test_stale_db_date_skips_without_alert(self):
        logger = Mock()
        # DB 최근일이 10-08 (직전 거래일 10-12 아님) → 비교 생략
        repo = Mock(get_daily_prices=Mock(return_value=_daily_df(343_000, last_date=date(2026, 10, 8))))
        hook = CorpActionPriceAlertHook(logger)
        hook.remember_base_price("000500", 233_500, TRADE_DATE)
        hook.check(**_check_kwargs(price_repo=repo, telegram=None))
        await _drain(hook)
        assert hook.check(**_check_kwargs(price_repo=repo, telegram=None)) is None
        logger.warning.assert_not_called()
        infos = [c.args[0] for c in logger.info.call_args_list]
        assert len(infos) == 1 and "기준가 점검 생략" in infos[0]

    async def test_db_error_is_cached_and_not_raised(self):
        logger = Mock()
        repo = Mock(get_daily_prices=Mock(side_effect=RuntimeError("db down")))
        hook = CorpActionPriceAlertHook(logger)
        hook.remember_base_price("000500", 233_500, TRADE_DATE)
        for _ in range(3):
            hook.check(**_check_kwargs(price_repo=repo, telegram=None))
            await _drain(hook)
        assert repo.get_daily_prices.call_count == 1
        logger.warning.assert_not_called()

    async def test_day_rollover_realerts_and_drops_old_base(self):
        logger = Mock()
        hook = CorpActionPriceAlertHook(logger)
        repo1 = Mock(get_daily_prices=Mock(return_value=_daily_df(343_000)))
        hook.remember_base_price("000500", 233_500, TRADE_DATE)
        hook.check(**_check_kwargs(price_repo=repo1, telegram=None))
        await _drain(hook)
        hook.check(**_check_kwargs(price_repo=repo1, telegram=None))
        assert len(_warnings(logger)) == 2

        next_day = date(2026, 10, 14)
        # 다음 날: 어제 기준가는 버려져 보관 전엔 판정 0
        assert hook.check(**_check_kwargs(trade_date=next_day, price_repo=repo1, telegram=None)) is None
        repo2 = Mock(get_daily_prices=Mock(return_value=_daily_df(240_000, last_date=TRADE_DATE)))
        hook.remember_base_price("000500", 120_000, next_day)
        hook.check(**_check_kwargs(trade_date=next_day, price_repo=repo2, telegram=None))
        await _drain(hook)
        hook.check(**_check_kwargs(trade_date=next_day, price_repo=repo2, telegram=None))
        assert len(_warnings(logger)) == 4

    async def test_telegram_failure_does_not_raise(self):
        logger = Mock()
        repo = Mock(get_daily_prices=Mock(return_value=_daily_df(343_000)))
        tg = Mock()
        tg.notify_system_status = AsyncMock(side_effect=RuntimeError("tg down"))
        hook = CorpActionPriceAlertHook(logger)
        hook.remember_base_price("000500", 233_500, TRADE_DATE)
        hook.check(**_check_kwargs(price_repo=repo, telegram=tg))
        await _drain(hook)
        hook.check(**_check_kwargs(price_repo=repo, telegram=tg))
        await _drain(hook)
        assert len(_warnings(logger)) == 2   # 로그는 남는다


# ---------------------------------------------------------------------------
# 3) PositionMonitor 연결 — 페이퍼 무동작 · 킬 스위치 · 예외 격리 · 판정 불변
# ---------------------------------------------------------------------------

def _positioned_stock(avg_price=346_500, qty=1, sl=0.10, tp=0.10):
    st = TradingStock(stock_code="000500", stock_name="가온전선",
                      state=StockState.POSITIONED, selected_time=FIXED_NOW)
    st.position = Position(stock_code="000500", quantity=qty, avg_price=avg_price)
    st.stop_loss_rate = sl
    st.target_profit_rate = tp
    return st


def _make_monitor(paper_flag, config_paper, current=210_500, base=233_500, prev_close=343_000):
    intraday = Mock()
    intraday.get_current_price_for_sell = Mock(return_value={
        "stock_code": "000500", "current_price": float(current), "prev_close": float(base)})
    intraday.get_cached_current_price = Mock(return_value=None)
    collector = Mock()
    collector.get_stock = Mock(return_value=None)
    mon = PositionMonitor(Mock(), Mock(), intraday, collector)
    mon.logger = Mock()
    mon._paper_trading = paper_flag
    engine = Mock()
    engine.config = config_paper
    engine.virtual_trading = None
    engine.db_manager = Mock()
    engine.db_manager.price_repo.get_daily_prices = Mock(return_value=_daily_df(prev_close))
    engine.telegram = Mock()
    engine.telegram.notify_system_status = AsyncMock()
    mon.decision_engine = engine
    mon._execute_sell = AsyncMock()
    return mon


async def _run_ticks(mon, stock, n=2):
    for _ in range(n):
        await mon._analyze_sell_for_stock(stock)
        hook = getattr(mon, "_corp_action_alert", None)
        if hook is not None:
            await _drain(hook)


def _prefixed_warnings(mon):
    return [c.args[0] for c in mon.logger.warning.call_args_list
            if c.args and str(c.args[0]).startswith(ALERT_PREFIX)]


REAL = SimpleNamespace(paper_trading=False)


@pytest.fixture
def fixed_now(monkeypatch):
    monkeypatch.setattr(pm_mod, "now_kst", lambda: FIXED_NOW)
    monkeypatch.delenv(KILL_SWITCH_ENV, raising=False)


class TestPositionMonitorWiring:
    async def test_real_instance_alerts(self, fixed_now):
        mon = _make_monitor(False, REAL)
        await _run_ticks(mon, _positioned_stock())
        w = _prefixed_warnings(mon)
        assert len(w) == 2
        assert mon.decision_engine.db_manager.price_repo.get_daily_prices.call_count == 1
        assert mon.decision_engine.telegram.notify_system_status.await_count == 2

    @pytest.mark.parametrize("paper_flag, config", [
        (True, SimpleNamespace(paper_trading=True)),       # 페이퍼
        (True, SimpleNamespace()),                         # 값 없음 → 페이퍼
        (False, SimpleNamespace()),                        # 플래그 False 여도 config 값 없음 → 페이퍼
        (False, SimpleNamespace(paper_trading=True)),      # config True → 페이퍼
        (False, None),                                     # config 자체 없음 → 페이퍼
        (True, REAL),                                      # 매도 경로 플래그가 페이퍼 → 페이퍼
    ])
    async def test_paper_or_missing_is_noop(self, fixed_now, paper_flag, config):
        mon = _make_monitor(paper_flag, config)
        await _run_ticks(mon, _positioned_stock())
        mon.decision_engine.db_manager.price_repo.get_daily_prices.assert_not_called()
        assert _prefixed_warnings(mon) == []
        mon.logger.debug.assert_not_called()
        mon.decision_engine.telegram.notify_system_status.assert_not_called()
        assert getattr(mon, "_corp_action_alert", None) is None

    async def test_kill_switch_off_is_noop(self, fixed_now, monkeypatch):
        monkeypatch.setenv(KILL_SWITCH_ENV, "off")
        mon = _make_monitor(False, REAL)
        await _run_ticks(mon, _positioned_stock())
        mon.decision_engine.db_manager.price_repo.get_daily_prices.assert_not_called()
        assert _prefixed_warnings(mon) == []
        assert getattr(mon, "_corp_action_alert", None) is None

    async def test_hook_exception_does_not_propagate(self, fixed_now):
        mon = _make_monitor(False, REAL)
        with patch.object(CorpActionPriceAlertHook, "check", side_effect=RuntimeError("boom")), \
                patch.object(CorpActionPriceAlertHook, "remember_base_price",
                             side_effect=RuntimeError("boom2")):
            price = await mon._get_current_price("000500")
            assert price == 210_500.0
            stock = _positioned_stock()
            await mon._analyze_sell_for_stock(stock)
        # 손절은 평소처럼 1번 실행 — 오류 로그(매도 분석 오류) 없음
        mon._execute_sell.assert_awaited_once()
        assert "손절 실행" in mon._execute_sell.await_args.args[2]
        mon.logger.error.assert_not_called()

    async def test_remember_base_does_not_change_return_value(self, fixed_now):
        mon = _make_monitor(False, REAL)
        assert await mon._get_current_price("000500") == 210_500.0
        mon_paper = _make_monitor(True, SimpleNamespace(paper_trading=True))
        assert await mon_paper._get_current_price("000500") == 210_500.0


class TestSellDecisionUnchanged:
    """같은 표본 포지션 — 훅 on(실전·경보 발생) vs off(킬 스위치) 매도 판단이 같다."""

    @pytest.mark.parametrize("current, avg, base, prev", [
        (210_500, 346_500, 233_500, 343_000),   # 권리락 가짜 손절(000500 재현) — 갭 있음
        (2_700, 2_400, 2_900, 8_290),            # 큰 하락 기준가 + 익절 영역(+12.5% · 475460 유사 가정)
        (100_000, 100_000, 100_000, 100_000),    # 갭 없음 · 판정 없음
        (95_000, 100_000, 120_000, 100_000),     # 갭(+20%) · 판정 없음(-5%)
    ])
    async def test_on_vs_off(self, fixed_now, monkeypatch, current, avg, base, prev):
        def run(env_value):
            monkeypatch.setenv(KILL_SWITCH_ENV, env_value)
            mon = _make_monitor(False, REAL, current=current, base=base, prev_close=prev)
            stock = _positioned_stock(avg_price=avg)
            return mon, stock

        mon_on, st_on = run("on")
        await _run_ticks(mon_on, st_on, n=3)
        mon_off, st_off = run("off")
        await _run_ticks(mon_off, st_off, n=3)

        on_calls = [(c.args[1], c.args[2]) for c in mon_on._execute_sell.await_args_list]
        off_calls = [(c.args[1], c.args[2]) for c in mon_off._execute_sell.await_args_list]
        assert on_calls == off_calls
        # 판정 대상 상태(평단·수량·손익절률)도 훅이 건드리지 않는다
        assert (st_on.position.avg_price, st_on.position.quantity,
                st_on.stop_loss_rate, st_on.target_profit_rate) == \
               (st_off.position.avg_price, st_off.position.quantity,
                st_off.stop_loss_rate, st_off.target_profit_rate)
        gap = detect_base_price_gap(base, prev)
        assert (len(_prefixed_warnings(mon_on)) > 0) == (gap is not None)
        assert _prefixed_warnings(mon_off) == []

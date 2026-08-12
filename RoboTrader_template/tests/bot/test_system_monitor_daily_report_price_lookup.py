"""EOD 일일 매매 리포트에 **in-memory 현재가 조회자가 실제로 배선되는지** 검증.

tools/daily_trading_summary.py 의 3단계 해석이 단위테스트로 green 이어도,
호출부(bot/system_monitor.py)가 조회자를 안 넘기면 리포트는 영원히 2·3단계만
탄다 — 이 프로젝트에서 「단위는 green 인데 호출부가 안 거치는」 사고가 이미
났다(2026-08-03 리뷰 발견 2). 여기서는 `_handle_postmarket_tasks` 를 끝까지
돌려 리포트가 **무엇을 받았는지**를 직접 본다.

조회자의 출처는 `trading_manager.get_stocks_by_state(POSITIONED)` 의
`position.current_price` 다. `IntradayStockManager.get_cached_current_price`
는 프로덕션에서 writer 가 0건이라(=항상 None) 쓰지 않는다 —
`_build_current_price_lookup` docstring 참조.

⚠️ DB·네트워크 미접촉: EOD 하위 단계는 전부 스텁으로 덮는다.
"""
import asyncio
import types
from datetime import datetime

from core.models import Position, StockState

import bot.system_monitor as sm


_EOD_TIME = datetime(2026, 8, 12, 15, 36, 0)


class _FakeTradingManager:
    """TradingStockManager.get_stocks_by_state 만 흉내낸다 (순수 메모리)."""

    def __init__(self, positioned):
        self._positioned = positioned
        self.states_asked = []

    def get_stocks_by_state(self, state):
        self.states_asked.append(state)
        return list(self._positioned) if state == StockState.POSITIONED else []


def _stock(code, current_price, quantity=10, avg_price=1000.0):
    """position.current_price 가 채워진 최소 TradingStock 대역."""
    position = Position(stock_code=code, quantity=quantity, avg_price=avg_price)
    if current_price is not None:
        position.current_price = current_price
    return types.SimpleNamespace(stock_code=code, position=position)


class _RecLogger:
    def __init__(self):
        self.error = []
        self.warning = []
        self.info = []

    def ns(self):
        def _mk(sink):
            def _log(msg, *a, **k):
                sink.append(str(msg))
            return _log

        return types.SimpleNamespace(
            info=_mk(self.info), warning=_mk(self.warning), error=_mk(self.error)
        )


def _make_monitor(monkeypatch, bot, received):
    """EOD 하위 단계를 무해한 스텁으로 덮고, 리포트가 받은 인자를 기록한다."""
    monkeypatch.setattr(sm, "is_holiday", lambda t: False, raising=False)

    def _capture_report(price_lookup=None):
        received.append(price_lookup)

    monkeypatch.setattr(sm, "print_today_trading_summary", _capture_report, raising=False)

    rec = _RecLogger()
    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)  # __init__ 우회(봇 의존성 최소화)
    mon.bot = bot
    mon.logger = rec.ns()
    mon._last_daily_report_date = None
    mon._last_regime_index_summary_date = None

    def _noop(*a, **k):
        return None

    mon._verify_eod_fund_integrity = _noop
    mon._verify_screener_snapshot = _noop
    mon._run_equity_snapshot = _noop
    mon._run_regime_index_refresh = _noop
    mon._log_regime_index_resolution = _noop

    async def _collect(current_time):
        return None

    mon._run_data_collection = _collect
    return mon, rec


def _run_eod(mon):
    asyncio.run(mon._handle_postmarket_tasks(_EOD_TIME))


def test_eod_report_receives_lookup_backed_by_position_prices(monkeypatch):
    """봇에 trading_manager 가 있으면 리포트는 POSITIONED 포지션의
    in-memory 현재가를 읽는 조회자를 받는다."""
    tm = _FakeTradingManager([_stock("005930", 12345.0)])
    bot = types.SimpleNamespace(trading_manager=tm)
    received = []

    mon, rec = _make_monitor(monkeypatch, bot, received)
    _run_eod(mon)

    assert rec.error == [], f"EOD 에러 발생: {rec.error}"
    assert len(received) == 1, "리포트가 정확히 1회 호출돼야 함"
    lookup = received[0]
    assert callable(lookup), "리포트가 조회자를 못 받음 — 배선 누락"
    assert lookup("005930") == 12345.0
    assert StockState.POSITIONED in tm.states_asked


def test_lookup_returns_none_for_stock_without_position_price(monkeypatch):
    """보유 목록에 없는 종목은 None → 리포트가 2단계(당일 일봉)로 내려간다."""
    tm = _FakeTradingManager([_stock("005930", 12345.0)])
    bot = types.SimpleNamespace(trading_manager=tm)
    received = []

    mon, _ = _make_monitor(monkeypatch, bot, received)
    _run_eod(mon)

    assert received[0]("111770") is None


def test_uninitialized_position_price_is_not_reported_as_zero(monkeypatch):
    """`position.current_price` 가 초기값 0.0 인 종목(모니터 루프가 아직 못
    갱신)은 스냅샷에 담지 않는다.

    0 을 그대로 넘기면 리포트가 평가금액 0 을 찍을 위험을 조회자 쪽에도 남기게
    된다. 여기서 빼면 리포트는 곧바로 2단계(당일 일봉)를 탄다."""
    tm = _FakeTradingManager([_stock("031440", 0.0), _stock("005930", 700.0)])
    bot = types.SimpleNamespace(trading_manager=tm)
    received = []

    mon, _ = _make_monitor(monkeypatch, bot, received)
    _run_eod(mon)

    assert received[0]("031440") is None, "0.0 이 현재가로 새어나감"
    assert received[0]("005930") == 700.0  # 대칭: 정상값은 통과


def test_injection_is_optional_when_bot_has_no_trading_manager(monkeypatch):
    """주입 불가(참조 없음)면 None 을 넘겨 리포트가 CLI 와 같은 경로를 탄다.

    여기서 예외가 나면 EOD 리포트가 통째로 죽으므로 «선택적» 이 아니게 된다."""
    bot = types.SimpleNamespace()
    received = []

    mon, rec = _make_monitor(monkeypatch, bot, received)
    _run_eod(mon)

    assert rec.error == [], f"EOD 에러 발생: {rec.error}"
    assert received == [None]


def test_lookup_build_failure_does_not_kill_the_report(monkeypatch):
    """스냅샷 생성이 터져도 리포트는 돌아야 한다(주입은 부가기능이다)."""

    class _Exploding:
        def get_stocks_by_state(self, state):
            raise RuntimeError("state manager exploded")

    bot = types.SimpleNamespace(trading_manager=_Exploding())
    received = []

    mon, rec = _make_monitor(monkeypatch, bot, received)
    _run_eod(mon)

    assert received == [None], "리포트가 호출되지 않음"
    assert rec.error == [], f"EOD 에러로 승격됨: {rec.error}"
    assert any("스냅샷" in w for w in rec.warning), rec.warning


def test_eod_latch_still_set_after_report_with_lookup(monkeypatch):
    """리포트 성공 시 `_last_daily_report_date` 래치가 그대로 걸려야 한다
    (배선 변경이 EOD 블록 재진입 동작을 바꾸면 안 된다)."""
    tm = _FakeTradingManager([])
    bot = types.SimpleNamespace(trading_manager=tm)
    received = []

    mon, _ = _make_monitor(monkeypatch, bot, received)
    _run_eod(mon)
    assert mon._last_daily_report_date == _EOD_TIME.date()

    _run_eod(mon)
    assert len(received) == 1, "래치가 안 걸려 EOD 블록이 재진입함"

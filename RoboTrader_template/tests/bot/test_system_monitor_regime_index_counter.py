"""EOD 에 급락게이트 지수 해석 집계가 **실제로 찍히는지** — 배선 테스트.

`market_classifier` 단위 테스트(tests/regime/test_regime_index_resolution_counter.py)
가 통과해도, EOD 흐름이 그걸 부르지 않으면 로그에는 아무것도 안 남는다.
이 프로젝트에서 「단위는 green 인데 호출부가 안 거치는」 사고가 이미 났다
(2026-08-03 리뷰 발견 2 — 그래서 tests/regime/test_crash_gate_market_scope.py 가
배선을 따로 본다). 여기서는 `_handle_postmarket_tasks` 를 **끝까지 돌려**
로거에 태그 줄이 남는지를 본다.

⚠️ DB·네트워크 미접촉: EOD 하위 단계(리포트·자금정합성·스크리너·equity·
   regime 갱신·데이터수집)를 전부 인스턴스 속성 스텁으로 덮는다.
"""
import asyncio
import types
from datetime import datetime

import pytest

import bot.system_monitor as sm
import core.regime.market_classifier as mc


class _RecLogger:
    def __init__(self):
        self.info = []
        self.warning = []
        self.error = []

    def _mk(self, sink):
        def _log(msg, *a, **k):
            sink.append(str(msg))
        return _log

    def ns(self):
        return types.SimpleNamespace(
            info=self._mk(self.info),
            warning=self._mk(self.warning),
            error=self._mk(self.error),
        )


@pytest.fixture(autouse=True)
def _isolate_counts():
    mc.reset_resolution_counts()
    yield
    mc.reset_resolution_counts()


def _make_monitor(monkeypatch, order=None, holiday=False):
    """EOD 하위 단계를 전부 무해한 스텁으로 덮은 SystemMonitor."""
    monkeypatch.setattr(sm, "is_holiday", lambda t: holiday, raising=False)
    monkeypatch.setattr(sm, "get_holiday_name", lambda t: "테스트휴장", raising=False)
    monkeypatch.setattr(sm, "print_today_trading_summary", lambda: None, raising=False)

    rec = _RecLogger()
    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)  # __init__ 우회(봇 의존성 없음)
    mon.logger = rec.ns()
    mon._last_daily_report_date = None
    mon._last_regime_index_summary_date = None

    def _mark(name):
        def _fn(*a, **k):
            if order is not None:
                order.append(name)
        return _fn

    mon._verify_eod_fund_integrity = _mark("fund")
    mon._verify_screener_snapshot = _mark("screener")
    mon._run_equity_snapshot = _mark("equity")
    mon._run_regime_index_refresh = _mark("regime_refresh")

    async def _collect(current_time):
        if order is not None:
            order.append("collect")

    mon._run_data_collection = _collect
    return mon, rec


_T = datetime(2026, 8, 4, 15, 36, 2)


def _run_eod(mon, when=_T):
    asyncio.run(mon._handle_postmarket_tasks(when))


# =========================================================================
# 배선 — EOD 가 실제로 줄을 남기는가
# =========================================================================

def test_eod_emits_resolution_summary_line(monkeypatch):
    """오늘(전부 non-auto) 상태에서도 EOD 에 판정 가능한 줄이 남아야 한다."""
    mon, rec = _make_monitor(monkeypatch)
    for _ in range(11):
        mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")

    _run_eod(mon)

    tagged = [m for m in rec.info if mc.RESOLUTION_LOG_TAG in m]
    assert tagged, f"EOD 에 집계 줄이 없다: {rec.info}"
    # 🔴 `"11" in tagged[0]` 은 거짓 음성이다 — 다른 숫자 필드의 부분문자열로도
    #    만족된다. 라벨을 포함해 단언한다.
    assert "총 11건" in tagged[0], f"건수가 안 보인다: {tagged[0]}"
    assert rec.error == []


def test_eod_emits_line_even_when_nothing_was_resolved(monkeypatch):
    """0건도 신호다 — 침묵으로 만들면 배선 단절과 구분되지 않는다."""
    mon, rec = _make_monitor(monkeypatch)
    _run_eod(mon)
    assert any(mc.RESOLUTION_LOG_TAG in m for m in rec.info)


def test_eod_resets_counter_so_next_day_starts_clean(monkeypatch):
    """리셋은 출력 시점에 한다 — 전날 건수가 다음 거래일로 이월되면 안 된다."""
    mon, _ = _make_monitor(monkeypatch)
    for _ in range(4):
        mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")
    _run_eod(mon)
    assert mc.get_resolution_counts() == {}

    mon2, rec2 = _make_monitor(monkeypatch)
    _run_eod(mon2)
    tagged = [m for m in rec2.info if mc.RESOLUTION_LOG_TAG in m]
    assert "총 0건" in tagged[0], f"전날 건수가 이월됐다: {tagged[0]}"


def test_summary_is_emitted_before_data_collection(monkeypatch):
    """배치 근거의 실증.

    ① 수집은 수분짜리 단계다 — 그 뒤에 두면 수집 중 프로세스가 죽는 날의
       증거가 통째로 사라진다.
    ② `eod_collection.run_data_collection` 은 끝에서 매핑 캐시를 리셋한다.
       '오늘의 게이트 동작'과 '내일 쓸 매핑 재적재'가 로그에서 섞이면 오독된다.
    """
    order = []
    mon, _ = _make_monitor(monkeypatch, order=order)

    def _spy(log=None):
        order.append("counter")
        return {}

    monkeypatch.setattr(mc, "log_resolution_summary", _spy, raising=False)
    _run_eod(mon)

    assert "counter" in order and "collect" in order, order
    assert order.index("counter") < order.index("collect"), order


def test_counter_failure_does_not_break_the_rest_of_eod(monkeypatch):
    """집계 출력이 터져도 뒤따르는 EOD 단계가 계속 돌아야 한다."""
    order = []
    mon, rec = _make_monitor(monkeypatch, order=order)

    def _boom(log=None):
        raise RuntimeError("summary exploded")

    monkeypatch.setattr(mc, "log_resolution_summary", _boom, raising=False)
    _run_eod(mon)

    assert "collect" in order, f"집계 실패가 EOD 를 끊었다: {order}"
    assert any("summary exploded" in m for m in rec.error), rec.error


def test_holiday_skips_emit(monkeypatch):
    """휴장일엔 매수 평가가 없다 — 0건 줄을 매일 찍으면 노이즈다."""
    mon, rec = _make_monitor(monkeypatch, holiday=True)
    _run_eod(mon)
    assert not any(mc.RESOLUTION_LOG_TAG in m for m in rec.info), rec.info


def test_emit_happens_once_per_trading_day(monkeypatch):
    """5초 루프가 15:35~15:59 내내 돈다 — 매 루프 출력하면 로그가 폭주한다."""
    mon, rec = _make_monitor(monkeypatch)
    for _ in range(5):
        _run_eod(mon)
    tagged = [m for m in rec.info if mc.RESOLUTION_LOG_TAG in m]
    assert len(tagged) == 1, f"거래일당 1회여야 한다: {len(tagged)}회"


def test_emit_is_once_even_when_the_daily_report_keeps_failing(monkeypatch):
    """🔴 기존 래치에 얹으면 안 되는 이유 — **거짓 음성**이 만들어진다.

    `_last_daily_report_date` 는 `print_today_trading_summary()` **성공 후에만**
    세팅된다. 리포트가 예외를 내면 래치가 안 걸려 15:35~15:59 창(5초 루프)에서
    이 블록이 ~300회 재진입한다. 그때 **첫 줄에 전량이 담기고 나머지는 전부
    `총 0건`**(출력 시점 리셋) — 증거 소실은 아니지만 **tail 로 읽는 사람은
    「auto 가 안 돌았다」로 읽는다.**

    그래서 이 카운터는 **자체 날짜 래치**를 갖는다. 기존 래치와 독립임을
    같은 실행에서 단언한다(리포트는 계속 실패 = 기존 래치 미설정).
    """
    mon, rec = _make_monitor(monkeypatch)

    def _boom():
        raise RuntimeError("report exploded")

    monkeypatch.setattr(sm, "print_today_trading_summary", _boom, raising=False)
    for _ in range(3):
        mc.resolve_regime_index("KOSPI", "005930", strategy_name="elder")

    for _ in range(5):
        _run_eod(mon)

    # 상세 줄도 같은 태그를 달고 나오므로 **헤드라인만** 센다(태그 개수를 세면
    # 건수가 있는 날엔 상세 줄 때문에 항상 >1 이 되어 판별력이 없다).
    heads = [m for m in rec.info if mc.RESOLUTION_LOG_TAG in m and "총 " in m]
    assert len(heads) == 1, f"리포트 실패로 {len(heads)}회 재진입했다: {heads}"
    assert "총 3건" in heads[0], f"첫 줄에 전량이 안 담겼다: {heads[0]}"
    # 독립성의 직접 증거: 기존 래치는 끝까지 안 걸렸는데도 1회로 눌렸다.
    assert mon._last_daily_report_date is None, "기존 래치가 걸려버려 판별력이 없다"
    assert any("report exploded" in m for m in rec.error), rec.error

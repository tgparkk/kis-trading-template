"""`[게이트지수해석-프로브]` — P1 판정용 후보 분포를 EOD 에 인쇄한다.

배경(2026-09-15 결정 패널 §F-1 / §F-5 ⑤): 09-14·09-15 EOD 에서 daytrading 의
P1·P2 가 **판정 불가**였다. 그날 daytrading 후보가 전부 KOSDAQ 이었는지,
KOSPI 후보가 있었는데 신호가 0이었는지를 로그만으로 가릴 수 없었기 때문이다.
프로브는 그 분모(후보의 시장 분포)를 매일 한 줄로 박제한다.

🔴 **§D-1 — 프로브가 P1 증거를 자기오염시키면 안 된다.**
`resolve_regime_index` 는 순수 함수가 아니다(`market_classifier.py` 가
`_count_resolution` 으로 모듈 전역 `_resolution_counts` 를 변경하고 EOD 요약이
바로 그 카운터를 읽는다). 후보 전건을 프로브로 훑으면 **라이브 해석 집계에
합성 건수가 주입**돼 P1 의 분모가 오염된다. 그래서 `count=False` 우회를 뚫고,
이 파일이 그 우회를 **실측으로** 지킨다.

이 파일이 단언하는 것:
  ① `count=False` 는 `_resolution_counts` 를 한 건도 안 늘린다(반환값은 동일)
  ② 프로브 호출 후 카운터가 **호출 전과 완전히 동일**하다
  ③ 프로브 줄의 5개 수치가 후보 분포와 일치한다
  ④ 프로브가 터져도 EOD 요약·나머지 단계가 안 죽는다
  ⑤ 🟡 `설정=` 은 전략에 **실제로 심긴** regime_index 다 — 리터럴 "auto" 를
     박으면 설정이 KOSDAQ 인 날에도 auto 인 척하는 줄이 남는다
  ⑥ 🟡 `기준=` 모집단 꼬리표가 붙는다 — 이 줄을 P1 분모로 오용하지 못하게
"""
import asyncio
import types
from datetime import datetime
from unittest.mock import Mock

import pytest

import bot.system_monitor as sm
import core.regime.market_classifier as mc
from core.models import StockState

PROBE_TAG = "[게이트지수해석-프로브]"
DAYTRADING_KEY = "daytrading_3methods_breakout"

MARKET_OF = {
    "005930": "KOSPI",
    "000660": "KOSPI",
    "035720": "KOSDAQ",
    "247540": "KOSDAQ",
    "091990": "KOSDAQ",
    "999999": None,  # 미매핑 → both
}


@pytest.fixture(autouse=True)
def _isolate_counts():
    mc.reset_resolution_counts()
    yield
    mc.reset_resolution_counts()


# =========================================================================
# ① 카운터 우회 — market_classifier 단위
# =========================================================================

def test_count_false_does_not_touch_the_counter():
    before = mc.get_resolution_counts()
    assert before == {}

    out = mc.resolve_regime_index(
        "auto", "005930", market_lookup=MARKET_OF.get,
        strategy_name=DAYTRADING_KEY, count=False,
    )

    assert out == "KOSPI"  # 반환값은 집계 여부와 무관
    assert mc.get_resolution_counts() == {}


def test_count_true_is_still_the_default():
    mc.resolve_regime_index(
        "auto", "005930", market_lookup=MARKET_OF.get, strategy_name=DAYTRADING_KEY,
    )
    assert sum(mc.get_resolution_counts().values()) == 1


def test_probe_scan_leaves_live_counter_byte_identical():
    """라이브 해석 3건 뒤에 후보 6건을 프로브로 훑어도 집계는 3건 그대로."""
    for code in ("005930", "035720", "247540"):
        mc.resolve_regime_index(
            "auto", code, market_lookup=MARKET_OF.get, strategy_name=DAYTRADING_KEY,
        )
    snapshot = mc.get_resolution_counts()

    for code in MARKET_OF:
        mc.resolve_regime_index(
            "auto", code, market_lookup=MARKET_OF.get,
            strategy_name=DAYTRADING_KEY, count=False,
        )

    assert mc.get_resolution_counts() == snapshot


# =========================================================================
# ③④ 배선 — EOD 가 실제로 줄을 남기는가
# =========================================================================

class _RecLogger:
    def __init__(self):
        self.info, self.warning, self.error = [], [], []

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


def _selected(code, owner=DAYTRADING_KEY):
    s = Mock()
    s.stock_code = code
    s.strategy_name = owner
    return s


def _make_monitor(monkeypatch, selected=(), order=None, configured="auto"):
    monkeypatch.setattr(sm, "is_holiday", lambda t: False, raising=False)
    monkeypatch.setattr(sm, "get_holiday_name", lambda t: "테스트휴장", raising=False)
    monkeypatch.setattr(sm, "print_today_trading_summary", lambda *a, **k: None,
                        raising=False)
    monkeypatch.setattr(mc, "get_stock_market", MARKET_OF.get, raising=False)

    rec = _RecLogger()
    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)
    mon.logger = rec.ns()
    mon._last_daily_report_date = None
    mon._last_regime_index_summary_date = None

    tm = Mock()
    tm.get_stocks_by_state.side_effect = (
        lambda state: list(selected) if state == StockState.SELECTED else []
    )
    strat = Mock()
    strat.regime_index = configured
    mon.bot = types.SimpleNamespace(
        trading_manager=tm, strategies={DAYTRADING_KEY: strat},
    )

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


def _run_eod(mon, when=datetime(2026, 9, 15, 15, 36, 2)):
    asyncio.run(mon._handle_postmarket_tasks(when))


def test_probe_line_counts_match_candidate_markets(monkeypatch):
    selected = [
        _selected("005930"), _selected("000660"),          # KOSPI 2
        _selected("035720"), _selected("247540"),          # KOSDAQ 2
        _selected("091990"),                               # KOSDAQ 1
        _selected("999999"),                               # 미매핑 → both 1
        _selected("068270", owner="book_pullback_ma20"),   # 타 전략 — 제외
    ]
    mon, rec = _make_monitor(monkeypatch, selected=selected)

    _run_eod(mon)

    lines = [m for m in rec.info if PROBE_TAG in m]
    assert len(lines) == 1, rec.info
    line = lines[0]
    assert "daytrading" in line
    assert "설정=auto" in line, line
    assert "KOSPI후보=2" in line, line
    assert "KOSDAQ후보=3" in line, line
    assert "auto→KOSPI=2" in line, line
    assert "auto→KOSDAQ=3" in line, line
    assert "both=1" in line, line
    assert rec.error == []


def test_probe_does_not_pollute_the_eod_summary(monkeypatch):
    """§D-1 의 핵심 — 프로브가 돈 뒤 EOD 요약 총 건수가 라이브 건수 그대로."""
    selected = [_selected(c) for c in MARKET_OF]
    mon, rec = _make_monitor(monkeypatch, selected=selected)

    for code in ("005930", "035720"):
        mc.resolve_regime_index(
            "auto", code, market_lookup=MARKET_OF.get, strategy_name=DAYTRADING_KEY,
        )

    _run_eod(mon)

    tagged = [m for m in rec.info
              if mc.RESOLUTION_LOG_TAG in m and PROBE_TAG not in m]
    assert tagged, rec.info
    assert "총 2건" in tagged[0], f"프로브가 집계를 오염시켰다: {tagged[0]}"


def test_probe_failure_does_not_break_eod(monkeypatch):
    order = []
    mon, rec = _make_monitor(monkeypatch, selected=[_selected("005930")], order=order)
    mon.bot.trading_manager.get_stocks_by_state.side_effect = RuntimeError("boom")

    _run_eod(mon)

    assert "collect" in order, order
    tagged = [m for m in rec.info
              if mc.RESOLUTION_LOG_TAG in m and PROBE_TAG not in m]
    assert tagged, "프로브 실패가 EOD 요약을 삼켰다"


def test_probe_emits_zero_line_when_no_candidates(monkeypatch):
    """후보 0 도 신호다 — 침묵이면 「배선 단절」과 구분되지 않는다."""
    mon, rec = _make_monitor(monkeypatch, selected=[])
    _run_eod(mon)
    lines = [m for m in rec.info if PROBE_TAG in m]
    assert len(lines) == 1
    assert "KOSPI후보=0" in lines[0]


# =========================================================================
# ⑤⑥ 리뷰 후속 — 설정값 실측 · 모집단 꼬리표
# =========================================================================

def test_configured_value_is_read_not_assumed(monkeypatch):
    """설정이 KOSDAQ 이면 `설정=KOSDAQ` 이고 auto→ 수치를 **지어내지 않는다**."""
    selected = [
        _selected("005930"), _selected("000660"),   # KOSPI 2
        _selected("035720"),                         # KOSDAQ 1
        _selected("999999"),                         # 미매핑
    ]
    mon, rec = _make_monitor(monkeypatch, selected=selected, configured="KOSDAQ")

    _run_eod(mon)

    line = [m for m in rec.info if PROBE_TAG in m][0]
    assert "설정=KOSDAQ" in line, line
    assert "설정=auto" not in line, line
    # 소속 시장 집계는 설정과 무관하게 유효하다
    assert "KOSPI후보=2" in line, line
    assert "KOSDAQ후보=1" in line, line
    # auto 해석이 «일어나지 않은» 날이므로 전부 0 이어야 한다
    assert "auto→KOSPI=0" in line, line
    assert "auto→KOSDAQ=0" in line, line
    assert "both=0" in line, line
    assert rec.error == []


def test_probe_line_carries_population_qualifier(monkeypatch):
    """모집단 꼬리표 — P1 분모로 오용되지 않게 줄 스스로 정의를 들고 다닌다."""
    mon, rec = _make_monitor(monkeypatch, selected=[_selected("005930")])
    _run_eod(mon)
    line = [m for m in rec.info if PROBE_TAG in m][0]
    assert "기준=미매수SELECTED@15:35(매수체결분 제외)" in line, line


def test_missing_strategy_instance_falls_back_to_class_default(monkeypatch):
    """전략 인스턴스가 없어도(형상 이상) 줄은 남고 EOD 는 안 죽는다."""
    mon, rec = _make_monitor(monkeypatch, selected=[_selected("005930")])
    mon.bot.strategies = {}

    _run_eod(mon)

    line = [m for m in rec.info if PROBE_TAG in m][0]
    assert "설정=both" in line, line
    assert rec.error == []

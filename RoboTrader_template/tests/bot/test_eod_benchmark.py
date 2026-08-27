"""EOD 벤치마크 한 줄 — 포맷 순수함수 + system_monitor 배선 회귀 고정.

왜 필요한가(2026-08-25 전문가 3인 자문): 페이퍼 기간 KOSPI 가 -23.6% 인데 로그
어디에도 시장 대비 성과가 없었다 — 「-20% 누적」이 알파인지 베타인지 로그만으로는
판별 불가였다. 이 줄이 그 계기다.

설계 요점 두 가지를 여기서 고정한다:
  ① 포맷은 **순수함수** — DB·API 없이 숫자만으로 검증 가능해야 한다(n/a 경로 포함).
  ② 예외는 EOD 흐름을 **절대** 막지 않는다 — WARNING 한 줄로 끝나고 전파 없음.
"""

import asyncio
import datetime as dt
import types

import pytest

import bot.eod_benchmark as bm
import bot.system_monitor as sm


# ── ① 포맷 순수함수 ────────────────────────────────────────────────────────

def _sample(**over):
    base = dict(
        total=63_540_499,
        base=80_000_000,
        day_return=-0.0016,
        kospi_level=6879.87,
        kospi_day=0.0123,
        kospi_cum=-0.2360,
        kosdaq_level=834.39,
        kosdaq_day=-0.0045,
        kosdaq_cum=-0.1912,
        epoch_label="2026-06-01",
    )
    base.update(over)
    return base


def test_format_full_line():
    """전 항목이 있는 정상 한 줄 — 문자 그대로 고정한다."""
    assert bm.format_benchmark_line(**_sample()) == (
        "[벤치마크] 포트 총자금 63,540,499원 · 누적 -20.57%(기준 80,000,000원) · "
        "당일(equity원장) -0.16% "
        "| KOSPI 6,880 당일 +1.23% · 2026-06-01 이후 -23.60% "
        "| KOSDAQ 834 당일 -0.45% · 2026-06-01 이후 -19.12%"
    )


def test_day_return_label_names_its_ledger():
    """당일은 «어느 원장에서 나온 비율인지» 가 줄에 박혀 있어야 한다.

    2026-08-27 코드리뷰: 분자 FundManager / 분모 equity 원장이 섞여 하루 0.6~1.5%
    가짜 등락이 찍혔다. 라벨은 그 재발을 사람이 즉시 알아채게 하는 표식이다.
    """
    assert "당일(equity원장) " in bm.format_benchmark_line(**_sample())


def test_index_level_is_printed_next_to_its_returns():
    """지수 «레벨» 이 같이 찍혀야 실시간 API vs 일봉 스케일 어긋남이 보인다."""
    line = bm.format_benchmark_line(**_sample())
    assert "KOSPI 6,880 당일" in line
    assert "KOSDAQ 834 당일" in line


def test_index_level_na_when_missing():
    line = bm.format_benchmark_line(**_sample(kospi_level=None))
    assert "KOSPI n/a 당일" in line


def test_cum_is_derived_from_total_and_base():
    """누적은 total/base-1 로 «파생»된다 — 별도 입력이 아니다(두 값이 어긋날 여지 제거)."""
    line = bm.format_benchmark_line(**_sample(total=88_000_000))
    assert "누적 +10.00%(기준 80,000,000원)" in line


def test_day_return_na_when_previous_total_missing():
    """전 거래일 equity 를 못 구하면 당일은 n/a — 0% 로 위장하지 않는다."""
    line = bm.format_benchmark_line(**_sample(day_return=None))
    assert "· 당일(equity원장) n/a |" in line
    assert "누적 -20.57%" in line, "당일이 없다고 나머지까지 죽으면 안 된다"


def test_index_na_paths():
    """지수 조회 실패 시 해당 칸만 n/a."""
    line = bm.format_benchmark_line(
        **_sample(kospi_level=None, kospi_day=None, kospi_cum=None, kosdaq_cum=None))
    assert "KOSPI n/a 당일 n/a · 2026-06-01 이후 n/a" in line
    assert "KOSDAQ 834 당일 -0.45% · 2026-06-01 이후 n/a" in line


def test_total_and_base_na_paths():
    """총자금/기준자본을 못 구해도 줄은 나온다(누적도 n/a)."""
    line = bm.format_benchmark_line(**_sample(total=None, base=None))
    assert "포트 총자금 n/a원" in line
    assert "누적 n/a(기준 n/a원)" in line


def test_zero_base_does_not_raise():
    """전략 0개(기준자본 0)에서 ZeroDivision 이 나면 EOD 가 죽는다."""
    line = bm.format_benchmark_line(**_sample(base=0))
    assert "누적 n/a" in line


def test_line_starts_with_stable_tag():
    assert bm.format_benchmark_line(**_sample()).startswith("[벤치마크] ")


# ── 기준자본 = 할당 SSOT(VirtualTradingManager._strategy_initial) 합계 ────

def _bot_with_allocation(allocated, strategies=None):
    """할당 원장을 든 bot 스텁. strategies 는 «다르게» 둘 수 있다(가지치기 재현)."""
    vtm = types.SimpleNamespace(_strategy_initial=dict(allocated))
    return types.SimpleNamespace(
        decision_engine=types.SimpleNamespace(virtual_trading=vtm),
        strategies=strategies if strategies is not None else dict(allocated),
    )


def test_base_capital_sums_allocated_initial_capital():
    """8전략 배정 → 80,000,000. 상수를 박지 않고 배정액 합에서 나온다."""
    from config.constants import VIRTUAL_CAPITAL_PER_STRATEGY
    allocated = {f"s{i}": float(VIRTUAL_CAPITAL_PER_STRATEGY) for i in range(8)}
    caps = bm.fetch_strategy_initial_capitals(_bot_with_allocation(allocated))
    assert len(caps) == 8
    assert sum(caps.values()) == 80_000_000.0


def test_base_capital_survives_pruned_strategies_dict():
    """on_init 실패로 bot.strategies 가 7개로 깎여도 기준자본은 8천만이어야 한다.

    main.py 가 실패 전략을 strategies dict 에서 지운다 — 거기서 세면 기준이 조용히
    7천만이 되고 누적 수익률이 부풀어 보인다(2026-08-27 코드리뷰 지적).
    """
    allocated = {f"s{i}": 10_000_000.0 for i in range(8)}
    pruned = {f"s{i}": object() for i in range(7)}   # 한 개 가지치기됨
    bot = _bot_with_allocation(allocated, strategies=pruned)
    caps = bm.fetch_strategy_initial_capitals(bot)
    assert sum(caps.values()) == 80_000_000.0, "가지치기된 dict 를 세면 안 된다"


def test_base_capital_empty_when_no_allocation():
    """실전 모드 등 할당이 없으면 빈 dict → 기준·당일 모두 n/a."""
    assert bm.fetch_strategy_initial_capitals(types.SimpleNamespace()) == {}
    empty = _bot_with_allocation({})
    assert bm.fetch_strategy_initial_capitals(empty) == {}


# ── 지수 스냅샷: 퍼센트 → 비율 변환 ───────────────────────────────────────

def test_index_snapshot_converts_percent_to_ratio(monkeypatch):
    """KIS 는 전일대비율을 «퍼센트»로 준다 — 비율로 바꿔야 +1.23% 로 찍힌다."""
    monkeypatch.setattr(
        bm, "_get_index_data",
        lambda code: {"bstp_nmix_prpr": "2500.05", "bstp_nmix_prdy_ctrt": "1.23"})
    level, day = bm.fetch_index_snapshot("0001")
    assert level == pytest.approx(2500.05)
    assert day == pytest.approx(0.0123)


def test_index_snapshot_none_on_api_failure(monkeypatch):
    monkeypatch.setattr(bm, "_get_index_data", lambda code: None)
    assert bm.fetch_index_snapshot("0001") == (None, None)


# ── 수집 조립: 파생값과 «불필요한 조회 안 함» ─────────────────────────────

_ALLOCATED_8 = {f"s{i}": 10_000_000.0 for i in range(8)}


def _patch_fetchers(monkeypatch, *, total=63_540_499, day_return=-0.0016,
                    allocated=None, kospi=(2500.0, 0.0123), kosdaq=(700.0, -0.0045),
                    kospi_epoch=3000.0, kosdaq_epoch=800.0, calls=None):
    calls = {} if calls is None else calls
    allocated = _ALLOCATED_8 if allocated is None else allocated

    def _count(name):
        calls[name] = calls.get(name, 0) + 1

    def _rec(name, value):
        def _f(*a, **k):
            _count(name)
            return value
        return _f

    def _index(code):
        _count("index")
        return kospi if code == "0001" else kosdaq

    def _epoch(ticker):
        _count("epoch")
        return kospi_epoch if ticker == "KOSPI" else kosdaq_epoch

    def _day(today, expected):
        _count("day")
        calls["expected"] = expected
        return day_return

    monkeypatch.setattr(bm, "fetch_total_funds", _rec("total", total))
    monkeypatch.setattr(bm, "fetch_strategy_initial_capitals",
                        _rec("caps", dict(allocated)))
    monkeypatch.setattr(bm, "fetch_equity_ledger_day_return", _day)
    monkeypatch.setattr(bm, "fetch_index_snapshot", _index)
    monkeypatch.setattr(bm, "fetch_epoch_close", _epoch)
    return calls


def test_collect_composes_derived_returns(monkeypatch):
    """기준=배정합, 당일=equity원장, 에포크이후=현재지수/에포크종가."""
    _patch_fetchers(monkeypatch)
    out = bm.collect_benchmark_inputs(object(), today=dt.date(2026, 8, 27))
    assert out["total"] == 63_540_499
    assert out["base"] == 80_000_000.0
    assert out["day_return"] == pytest.approx(-0.0016)
    assert out["kospi_level"] == 2500.0
    assert out["kospi_cum"] == pytest.approx(2500.0 / 3000.0 - 1.0)
    assert out["kosdaq_level"] == 700.0
    assert out["kosdaq_cum"] == pytest.approx(700.0 / 800.0 - 1.0)
    assert out["epoch_label"] == "2026-06-01"
    # format 인자와 정확히 짝이 맞아야 한다(키 하나 어긋나면 EOD 에서만 터진다)
    assert bm.format_benchmark_line(**out).startswith("[벤치마크] ")


def test_collect_day_return_does_not_use_fund_manager_total(monkeypatch):
    """🔴 당일은 FundManager 총자금과 «무관» 해야 한다 — 원장 혼용 회귀 고정.

    총자금을 크게 흔들어도 당일 값은 그대로여야 한다. 예전 구현은 분자를
    FundManager 에서 가져와 하루 0.6~1.5% 의 가짜 등락을 만들었다.
    """
    _patch_fetchers(monkeypatch, total=63_540_499)
    a = bm.collect_benchmark_inputs(object(), today=dt.date(2026, 8, 27))
    _patch_fetchers(monkeypatch, total=99_999_999)
    b = bm.collect_benchmark_inputs(object(), today=dt.date(2026, 8, 27))
    assert a["day_return"] == b["day_return"]
    assert a["total"] != b["total"]


def test_collect_passes_allocated_strategy_count_as_row_guard(monkeypatch):
    """행수 가드의 기대값은 «배정 전략 수» 다(기준자본과 같은 출처)."""
    calls = _patch_fetchers(monkeypatch)
    bm.collect_benchmark_inputs(object(), today=dt.date(2026, 8, 27))
    assert calls["expected"] == 8


def test_collect_skips_day_return_query_when_no_allocation(monkeypatch):
    """할당 원장이 비면 DB 를 치지 않고 당일·기준 모두 n/a."""
    calls = _patch_fetchers(monkeypatch, allocated={})
    out = bm.collect_benchmark_inputs(object(), today=dt.date(2026, 8, 27))
    assert out["day_return"] is None and out["base"] is None
    assert "day" not in calls


def test_collect_skips_epoch_close_query_when_index_missing(monkeypatch):
    """지수 조회가 실패하면 에포크 종가 DB 조회도 하지 않는다."""
    calls = _patch_fetchers(monkeypatch, kospi=(None, None), kosdaq=(None, None))
    out = bm.collect_benchmark_inputs(object(), today=dt.date(2026, 8, 27))
    assert out["kospi_cum"] is None and out["kosdaq_cum"] is None
    assert "epoch" not in calls


def test_collect_survives_missing_day_return(monkeypatch):
    """당일을 못 구해도(부분 적재·직전일 없음) 나머지는 그대로 나온다."""
    _patch_fetchers(monkeypatch, day_return=None)
    out = bm.collect_benchmark_inputs(object(), today=dt.date(2026, 8, 27))
    assert out["day_return"] is None
    assert out["total"] == 63_540_499


# ── equity 원장 당일 수익률: 행수 가드 ────────────────────────────────────

class _FakeCursor:
    """paper_strategy_equity 를 흉내내는 최소 커서 (DB 미접촉)."""

    def __init__(self, rows_by_date):
        self.rows_by_date = rows_by_date   # {date: [equity, ...]}
        self._result = None

    def execute(self, sql, params):
        if "MAX(trade_date)" in sql:
            _src, today = params
            earlier = [d for d in self.rows_by_date if d < today]
            self._result = (max(earlier),) if earlier else (None,)
            return
        if sql.startswith("SELECT COUNT(*)"):       # 가드 실패 시 진단 조회
            _src, trade_date = params
            self._result = (len(self.rows_by_date.get(trade_date, [])),)
            return
        _src, trade_date, expected = params
        rows = self.rows_by_date.get(trade_date, [])
        # HAVING COUNT(*) = expected → 불일치면 «행 없음»
        self._result = (sum(rows),) if len(rows) == int(expected) else None

    def fetchone(self):
        return self._result

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_conn(monkeypatch, rows_by_date):
    import contextlib

    cur = _FakeCursor(rows_by_date)
    conn = types.SimpleNamespace(cursor=lambda: cur)

    @contextlib.contextmanager
    def _get_connection():
        yield conn

    import db.connection as dbconn
    monkeypatch.setattr(dbconn.DatabaseConnection, "get_connection",
                        staticmethod(_get_connection))
    return cur


_TODAY = dt.date(2026, 8, 27)
_PREV = dt.date(2026, 8, 26)


def test_equity_day_return_uses_both_sums_from_same_ledger(monkeypatch):
    _patch_conn(monkeypatch, {_PREV: [10.0] * 8, _TODAY: [11.0] * 8})
    assert bm.fetch_equity_ledger_day_return(_TODAY, 8) == pytest.approx(0.1)


def test_equity_day_return_na_when_today_partially_loaded(monkeypatch):
    """오늘 7행뿐(부분 적재) → n/a. 없는 전략을 0 으로 세면 -12% 가 찍힌다."""
    _patch_conn(monkeypatch, {_PREV: [10.0] * 8, _TODAY: [10.0] * 7})
    assert bm.fetch_equity_ledger_day_return(_TODAY, 8) is None


def test_equity_day_return_na_when_prev_partially_loaded(monkeypatch):
    """직전일이 부분 적재여도 n/a — 가드는 «양쪽» 에 걸린다."""
    _patch_conn(monkeypatch, {_PREV: [10.0] * 6, _TODAY: [10.0] * 8})
    assert bm.fetch_equity_ledger_day_return(_TODAY, 8) is None


def test_equity_day_return_na_when_today_row_absent(monkeypatch):
    """스냅샷 전이면 오늘 행이 없다 → n/a (호출 순서 사고를 조용히 넘기지 않는다)."""
    _patch_conn(monkeypatch, {_PREV: [10.0] * 8})
    assert bm.fetch_equity_ledger_day_return(_TODAY, 8) is None


def test_equity_day_return_na_when_no_earlier_date(monkeypatch):
    """에포크 첫날 — 직전 거래일이 없으면 n/a."""
    _patch_conn(monkeypatch, {_TODAY: [10.0] * 8})
    assert bm.fetch_equity_ledger_day_return(_TODAY, 8) is None


def test_equity_day_return_ignores_same_day_as_previous(monkeypatch):
    """직전일 판정은 «엄격 부등호» 다 — 오늘을 직전일로 주워오면 항상 0% 가 된다."""
    _patch_conn(monkeypatch, {_PREV: [10.0] * 8, _TODAY: [12.0] * 8})
    assert bm.fetch_equity_ledger_day_return(_TODAY, 8) == pytest.approx(0.2)


def test_equity_day_return_na_without_expected_count(monkeypatch):
    """배정 전략 수를 모르면 DB 를 치지 않는다."""
    assert bm.fetch_equity_ledger_day_return(_TODAY, 0) is None


def test_row_count_mismatch_is_diagnosable(monkeypatch, caplog):
    """행수 가드가 걸리면 «왜» 인지 DEBUG 로 남아야 한다.

    안 남기면 「당일 n/a」가 영구히 찍히는데 원인을 알 길이 없다 — 조용한 계기
    고장은 이 프로젝트의 반복 실패 유형이다.
    """
    import logging

    _patch_conn(monkeypatch, {_PREV: [10.0] * 8, _TODAY: [10.0] * 7})
    bm.logger.propagate = True
    try:
        with caplog.at_level(logging.DEBUG, logger=bm.logger.name):
            assert bm.fetch_equity_ledger_day_return(_TODAY, 8) is None
    finally:
        bm.logger.propagate = False

    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    hit = [m for m in msgs if "행수 불일치" in m]
    assert hit, msgs
    assert "기대=8" in hit[0] and "실제=7" in hit[0], hit[0]


# ── 행수 가드 기대값의 «출처» ─────────────────────────────────────────

def test_collect_prefers_snapshot_row_count_over_allocation(monkeypatch):
    """기대 행수는 «스냅샷이 실제로 쓴 전략 수» 가 1순위다.

    할당 원장 수를 쓰면, 갓 배정돼 아직 체결이 없는 전략에서 두 수가 영구히
    어긋나 당일이 영원히 n/a 가 된다(스냅샷 writer 는 체결 기록 있는 전략만 쓴다).
    """
    calls = _patch_fetchers(monkeypatch, allocated={f"s{i}": 10_000_000.0
                                                    for i in range(9)})
    out = bm.collect_benchmark_inputs(object(), today=dt.date(2026, 8, 27),
                                      expected_strategies=8)
    assert calls["expected"] == 8, "스냅샷 행수(8)가 이겨야 한다"
    # 기준자본은 «항상» 할당 원장 합 — 폴백과 무관하다
    assert out["base"] == 90_000_000.0


def test_collect_falls_back_to_allocation_count(monkeypatch):
    """스냅샷 행수를 모르면(첫 기동·스킵) 할당 원장 수로 폴백한다."""
    for missing in (None, 0):
        calls = _patch_fetchers(monkeypatch)
        bm.collect_benchmark_inputs(object(), today=dt.date(2026, 8, 27),
                                    expected_strategies=missing)
        assert calls["expected"] == 8

# ── ② system_monitor 배선 ─────────────────────────────────────────────────

class _RecLogger:
    def __init__(self):
        self.info, self.warning, self.error = [], [], []

    def _mk(self, sink):
        def _log(msg, *a, **k):
            sink.append(str(msg))
        return _log


def _make_monitor():
    rec = _RecLogger()
    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)  # __init__ 우회(DB·대시보드 미접촉)
    mon.bot = types.SimpleNamespace(strategies={})
    mon.logger = types.SimpleNamespace(
        info=rec._mk(rec.info),
        warning=rec._mk(rec.warning),
        error=rec._mk(rec.error),
    )
    return mon, rec


_NOW = dt.datetime(2026, 8, 27, 15, 35)


def test_monitor_emits_one_info_line(monkeypatch):
    monkeypatch.setattr(bm, "collect_benchmark_inputs",
                        lambda bot, today=None, expected_strategies=None: _sample())
    mon, rec = _make_monitor()

    mon._log_eod_benchmark(_NOW)

    assert len(rec.info) == 1, "EOD 한 줄이어야 한다"
    assert rec.info[0].startswith("[벤치마크] ")
    assert "KOSPI 6,880 당일 +1.23%" in rec.info[0]
    assert rec.warning == [] and rec.error == []


def test_monitor_passes_today_to_collector(monkeypatch):
    """전 거래일 조회 기준일은 EOD 시각의 날짜다(테스트 결정론 확보)."""
    seen = {}

    def _collect(bot, today=None, expected_strategies=None):
        seen["today"] = today
        seen["expected"] = expected_strategies
        return _sample()

    monkeypatch.setattr(bm, "collect_benchmark_inputs", _collect)
    mon, _ = _make_monitor()
    mon._log_eod_benchmark(_NOW)
    assert seen["today"] == dt.date(2026, 8, 27)


def test_monitor_swallows_exception_as_single_warning(monkeypatch):
    """어떤 예외도 EOD 흐름을 막지 않는다 — WARNING 한 줄, 전파 없음."""
    def _boom(bot, today=None, expected_strategies=None):
        raise RuntimeError("DB down")

    monkeypatch.setattr(bm, "collect_benchmark_inputs", _boom)
    mon, rec = _make_monitor()

    mon._log_eod_benchmark(_NOW)  # 예외가 새면 여기서 테스트가 죽는다

    assert rec.info == []
    assert len(rec.warning) == 1
    assert rec.warning[0] == "[벤치마크] 계산 실패: DB down"


def test_monitor_warns_when_formatting_fails(monkeypatch):
    """수집이 아니라 포맷에서 터져도 같은 경로로 흡수된다."""
    monkeypatch.setattr(bm, "collect_benchmark_inputs",
                        lambda bot, today=None, expected_strategies=None: {"bogus": 1})
    mon, rec = _make_monitor()

    mon._log_eod_benchmark(_NOW)

    assert rec.info == []
    assert len(rec.warning) == 1
    assert rec.warning[0].startswith("[벤치마크] 계산 실패: ")


# ── ③ EOD 흐름 통합: 실제로 «불리는가» + «순서» ───────────────────────────

def test_postmarket_flow_emits_benchmark_after_equity_snapshot(monkeypatch):
    """_handle_postmarket_tasks 를 통째로 돌려 벤치마크 줄이 실제로 나오는지 본다.

    유닛으로 `_log_eod_benchmark` 만 직접 부르면 **호출 배선의 결함을 못 잡는다**.
    실제로 이 테스트가 잡은 결함: 같은 함수 안 뒤쪽의 함수-지역 `import asyncio` 가
    asyncio 를 함수 전체의 지역 이름으로 만들어, 그보다 «앞» 에 있는
    `await asyncio.to_thread(...)` 가 UnboundLocalError 로 죽었다.

    순서도 함께 고정한다 — 벤치마크는 오늘자 equity 행을 읽으므로 첫 스냅샷 «뒤»
    여야 한다.
    """
    order = []

    monkeypatch.setattr(sm, "print_today_trading_summary",
                        lambda *a, **k: order.append("summary"))
    monkeypatch.setattr(bm, "collect_benchmark_inputs",
                        lambda bot, today=None, expected_strategies=None: _sample())

    mon, rec = _make_monitor()
    mon._last_daily_report_date = None
    mon._last_regime_index_summary_date = None
    mon._build_current_price_lookup = lambda: None
    mon._verify_eod_fund_integrity = lambda: order.append("fund")
    mon._log_regime_index_resolution = lambda ct: order.append("regime_summary")
    mon._verify_screener_snapshot = lambda: order.append("screener")
    mon._run_equity_snapshot = lambda: order.append("equity")
    mon._run_regime_index_refresh = lambda: order.append("regime_refresh")

    async def _fake_dc(ct):
        order.append("data_collection")

    mon._run_data_collection = _fake_dc

    original_info = mon.logger.info

    def _info(msg, *a, **k):
        if str(msg).startswith("[벤치마크] "):
            order.append("benchmark")
        original_info(msg, *a, **k)

    mon.logger.info = _info

    asyncio.run(mon._handle_postmarket_tasks(
        dt.datetime(2026, 8, 27, 15, 36, 0)))

    bench_lines = [m for m in rec.info if m.startswith("[벤치마크] ")]
    assert len(bench_lines) == 1, f"벤치마크 줄이 안 나왔다: {order}"
    assert rec.warning == [], rec.warning
    assert "benchmark" in order and "equity" in order
    assert order.index("equity") < order.index("benchmark"), (
        f"벤치마크는 오늘자 equity 스냅샷 «뒤» 여야 한다: {order}")
    assert order.index("data_collection") < order.index("benchmark"), (
        f"당일 종가 수집 «뒤» 여야 보유평가가 T 종가다: {order}")
    # 재스냅샷(2번째 equity)까지 끝난 «뒤» 여야 한다 — 1차 스냅샷 값은 보유분이
    # D-1 종가로 평가돼 있어 당일 수익률이 구조적으로 치우친다(≈ -0.7%p 실측).
    assert order.count("equity") == 2, order
    second_equity = len(order) - 1 - order[::-1].index("equity")
    assert second_equity < order.index("benchmark"), (
        f"벤치마크는 재스냅샷 «뒤» 여야 한다: {order}")
    assert order.index("benchmark") == len(order) - 1, (
        f"벤치마크는 EOD 블록의 마지막 단계다: {order}")


def test_postmarket_flow_continues_when_benchmark_raises(monkeypatch):
    """벤치마크가 터져도 뒤 단계(데이터 수집·재스냅샷)는 그대로 돈다."""
    order = []

    def _boom(bot, today=None, expected_strategies=None):
        raise RuntimeError("DB down")

    monkeypatch.setattr(sm, "print_today_trading_summary", lambda *a, **k: None)
    monkeypatch.setattr(bm, "collect_benchmark_inputs", _boom)

    mon, rec = _make_monitor()
    mon._last_daily_report_date = None
    mon._last_regime_index_summary_date = None
    mon._build_current_price_lookup = lambda: None
    mon._verify_eod_fund_integrity = lambda: None
    mon._log_regime_index_resolution = lambda ct: None
    mon._verify_screener_snapshot = lambda: None
    mon._run_equity_snapshot = lambda: order.append("equity")
    mon._run_regime_index_refresh = lambda: None

    async def _fake_dc(ct):
        order.append("data_collection")

    mon._run_data_collection = _fake_dc

    asyncio.run(mon._handle_postmarket_tasks(
        dt.datetime(2026, 8, 27, 15, 36, 0)))

    assert "data_collection" in order, "벤치마크 실패가 EOD 를 끊으면 안 된다"
    assert order.count("equity") == 2, "재스냅샷까지 도달해야 한다"
    assert any(m == "[벤치마크] 계산 실패: DB down" for m in rec.warning), rec.warning


# ── ④ 행수 기대값 래치: 스냅샷 → 벤치마크 배선 ───────────────────────────

def test_snapshot_latches_row_count_for_benchmark(monkeypatch):
    """`_run_equity_snapshot` 이 쓴 전략 행 수가 벤치마크 기대값으로 흘러야 한다."""
    import contextlib

    import tools.paper_strategy_equity as pse

    mon, rec = _make_monitor()
    mon._resave_paper_trading_state = lambda: None

    @contextlib.contextmanager
    def _conn():
        yield object()

    import db.connection as dbconn
    monkeypatch.setattr(dbconn.DatabaseConnection, "get_connection",
                        staticmethod(_conn))
    monkeypatch.setattr(pse, "run_daily_equity_snapshot", lambda conn: {
        "ok": True, "trade_date": dt.date(2026, 8, 27), "n_strategies": 8,
        "total_cash": 1.0, "eod_balance": 1.0, "cash_match": True,
    })

    mon._run_equity_snapshot()
    assert mon._last_equity_n_strategies == 8

    seen = {}

    def _collect(bot, today=None, expected_strategies=None):
        seen["expected"] = expected_strategies
        return _sample()

    monkeypatch.setattr(bm, "collect_benchmark_inputs", _collect)
    mon._log_eod_benchmark(_NOW)
    assert seen["expected"] == 8


def test_benchmark_survives_absent_latch(monkeypatch):
    """스냅샷이 스킵돼 래치가 없어도 벤치마크는 돈다(폴백은 eod_benchmark 몫)."""
    seen = {}

    def _collect(bot, today=None, expected_strategies=None):
        seen["expected"] = expected_strategies
        return _sample()

    monkeypatch.setattr(bm, "collect_benchmark_inputs", _collect)
    mon, rec = _make_monitor()      # __init__ 우회 → 래치 속성 자체가 없다
    mon._log_eod_benchmark(_NOW)
    assert seen["expected"] is None
    assert rec.warning == [] and len(rec.info) == 1

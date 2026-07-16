import asyncio
import datetime
import types
import bot.system_monitor as sm


def test_run_data_collection_invokes_orchestrator(monkeypatch):
    captured = {}
    def fake_run(td):
        captured["td"] = td
        return {"daily": {"rows": 1}, "minute": {"rows": 2}, "index": {"KOSPI": 1}, "reconcile": {}}
    monkeypatch.setattr(sm, "run_data_collection", fake_run, raising=False)

    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)   # __init__ 우회
    mon.logger = types.SimpleNamespace(info=lambda *a, **k: None, error=lambda *a, **k: None,
                                       warning=lambda *a, **k: None)

    class _T:
        def strftime(self, f): return "20260623"
    asyncio.run(mon._run_data_collection(_T()))
    assert captured["td"] == "20260623"


def test_run_regime_index_refresh_invokes_with_price_repo(monkeypatch):
    """EOD regime 지수 갱신이 봇 price_repo 로 refresh_regime_indices 를 호출한다
    (게이트 SSOT daily_prices KOSPI/KOSDAQ 자동 신선화, 2026-06-24)."""
    import core.regime.index_refresh as ir
    captured = {}
    def fake_refresh(repo, **kw):
        captured["repo"] = repo
        return {"KOSPI": 5, "KOSDAQ": 5}
    monkeypatch.setattr(ir, "refresh_regime_indices", fake_refresh)

    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)
    mon.logger = types.SimpleNamespace(info=lambda *a, **k: None,
                                       warning=lambda *a, **k: None,
                                       error=lambda *a, **k: None)
    sentinel_repo = object()
    mon.bot = types.SimpleNamespace(
        db_manager=types.SimpleNamespace(price_repo=sentinel_repo))

    res = mon._run_regime_index_refresh()
    assert captured["repo"] is sentinel_repo
    assert res == {"KOSPI": 5, "KOSDAQ": 5}  # 결과 dict 반환(EOD 호환·장전 가드용)


def _mk_monitor():
    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)
    logs = {"info": [], "warning": [], "error": []}
    mon.logger = types.SimpleNamespace(
        info=lambda *a, **k: logs["info"].append(a),
        warning=lambda *a, **k: logs["warning"].append(a),
        error=lambda *a, **k: logs["error"].append(a),
    )
    mon.bot = types.SimpleNamespace(
        db_manager=types.SimpleNamespace(price_repo=object()))
    return mon, logs


def test_run_regime_index_refresh_warns_on_zero_rows(monkeypatch):
    """어떤 지수든 0행이면 INFO 대신 WARNING(stale 우려), dict 반환."""
    import core.regime.index_refresh as ir
    monkeypatch.setattr(ir, "refresh_regime_indices",
                        lambda repo, **kw: {"KOSPI": 5, "KOSDAQ": 0})
    mon, logs = _mk_monitor()
    res = mon._run_regime_index_refresh()
    assert res == {"KOSPI": 5, "KOSDAQ": 0}
    assert logs["warning"] and not logs["info"]


def test_run_regime_index_refresh_info_when_all_positive(monkeypatch):
    """전부 >0 이면 INFO 유지, dict 반환."""
    import core.regime.index_refresh as ir
    monkeypatch.setattr(ir, "refresh_regime_indices",
                        lambda repo, **kw: {"KOSPI": 5, "KOSDAQ": 5})
    mon, logs = _mk_monitor()
    res = mon._run_regime_index_refresh()
    assert res == {"KOSPI": 5, "KOSDAQ": 5}
    assert logs["info"] and not logs["warning"]


def test_premarket_regime_refresh_sets_guard_on_success():
    """성공(값>0)이면 가드 설정·중복호출 시 재실행 안 함."""
    mon, logs = _mk_monitor()
    calls = {"n": 0}

    def fake_refresh():
        calls["n"] += 1
        return {"KOSPI": 5, "KOSDAQ": 5}
    mon._run_regime_index_refresh = fake_refresh

    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 1
    assert getattr(mon, "_regime_index_refreshed_date", None) is not None
    # 같은 날 중복호출 → 재실행 안 함(하루 1회 가드)
    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 1


class _FakeClock:
    """주입 가능한 결정론적 시계 — now_kst 대체."""

    def __init__(self, start: datetime.datetime):
        self.t = start

    def __call__(self) -> datetime.datetime:
        return self.t

    def advance(self, **kw) -> None:
        self.t = self.t + datetime.timedelta(**kw)


def _mk_throttled_monitor(clock, refresh_result):
    """throttle 검증용: 주입 시계 + 카운팅 fake refresh + DB 부재(스킵 안 함) 모니터."""
    mon, logs = _mk_monitor()
    mon._clock = clock
    calls = {"n": 0}

    def fake_refresh():
        calls["n"] += 1
        return dict(refresh_result)
    mon._run_regime_index_refresh = fake_refresh
    return mon, logs, calls


def test_premarket_regime_refresh_cooldown_blocks_immediate_retry():
    """0행(실패) 반환 시 쿨다운 내 재호출이 일어나지 않음(루프 여러 번 돌려도 1회)."""
    clock = _FakeClock(datetime.datetime(2026, 6, 29, 8, 30, 0))
    mon, logs, calls = _mk_throttled_monitor(clock, {"KOSPI": 0, "KOSDAQ": 0})

    # 첫 시도 → 실패(가드 미설정)
    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 1
    assert getattr(mon, "_regime_index_refreshed_date", None) is None
    assert logs["warning"]

    # 같은 시각/쿨다운 내 여러 번 루프 돌아도 재호출 금지
    for _ in range(5):
        clock.advance(seconds=9)  # 모니터 루프 주기
        asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 1  # 첫 백오프(1분) 미경과 → 추가 호출 0


def test_premarket_regime_refresh_backoff_increases():
    """연속 실패 시 백오프 간격이 증가(1→2→5→15분)."""
    clock = _FakeClock(datetime.datetime(2026, 6, 29, 8, 30, 0))
    mon, logs, calls = _mk_throttled_monitor(clock, {"KOSPI": 0, "KOSDAQ": 0})

    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 1

    # 1분 미만 경과 → 차단
    clock.advance(seconds=59)
    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 1
    # 1분 경과 → 2번째 시도
    clock.advance(seconds=1)
    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 2

    # 다음 간격은 2분 — 1분 경과로는 부족
    clock.advance(minutes=1)
    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 2
    clock.advance(minutes=1)
    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 3

    # 다음 간격은 5분 — 4분으론 부족, 5분이면 허용
    clock.advance(minutes=4)
    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 3
    clock.advance(minutes=1)
    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 4


def test_premarket_regime_refresh_daily_cap_then_reset():
    """일일 캡 초과 후 그날 추가 호출 없음, 다음 거래일 리셋."""
    clock = _FakeClock(datetime.datetime(2026, 6, 29, 8, 30, 0))
    mon, logs, calls = _mk_throttled_monitor(clock, {"KOSPI": 0, "KOSDAQ": 0})

    # 캡까지 시도 소진(매 시도 사이 백오프 상한 이상 경과)
    for _ in range(sm._REGIME_REFRESH_MAX_ATTEMPTS_PER_DAY + 5):
        clock.advance(minutes=20)
        asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == sm._REGIME_REFRESH_MAX_ATTEMPTS_PER_DAY

    # 다음 거래일 → 카운터 리셋, 다시 시도 가능
    clock.t = datetime.datetime(2026, 6, 30, 8, 30, 0)
    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == sm._REGIME_REFRESH_MAX_ATTEMPTS_PER_DAY + 1


def test_premarket_regime_refresh_skips_when_db_present():
    """오늘자 KOSPI/KOSDAQ 일봉이 이미 DB에 있으면 FDR 호출 0회(멱등 스킵)·가드 설정."""
    clock = _FakeClock(datetime.datetime(2026, 6, 29, 8, 30, 0))
    mon, logs, calls = _mk_throttled_monitor(clock, {"KOSPI": 0, "KOSDAQ": 0})

    today = clock().date()

    class _Repo:
        def get_latest_daily_price(self, code):
            return {"date": today, "close": 3000.0}
    mon.bot = types.SimpleNamespace(
        db_manager=types.SimpleNamespace(price_repo=_Repo()))

    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 0  # FDR 미호출
    assert getattr(mon, "_regime_index_refreshed_date", None) == today


def test_premarket_regime_refresh_success_stops_for_day():
    """성공 1회 후 그날 추가 호출 없음."""
    clock = _FakeClock(datetime.datetime(2026, 6, 29, 8, 30, 0))
    mon, logs, calls = _mk_throttled_monitor(clock, {"KOSPI": 5, "KOSDAQ": 5})

    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 1
    assert getattr(mon, "_regime_index_refreshed_date", None) == clock().date()

    for _ in range(3):
        clock.advance(minutes=30)
        asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# 휴장일 EOD 게이트 (2026-07-17 제헌절 — 컷오버 후 첫 평일 공휴일)
#
# _handle_postmarket_tasks 는 15:35 를 시각만으로 판정해 휴장일에도 EOD 후속작업을
# 전부 돌렸다. 최대 위험은 _run_data_collection → minute_writer.replace_minute_day 로,
# KIS 가 휴장일 요청에 직전 거래일(T-1) 봉을 반환하면 T-1 분봉을 DELETE 후 재적재해
# 부분 재fetch 시 조용히 절단된다. 아래 테스트가 휴장일 스킵/거래일 실행을 고정한다.
# ---------------------------------------------------------------------------

def _mk_postmarket_monitor(monkeypatch):
    """_handle_postmarket_tasks 호출용 — 하위작업 전부 카운팅 스텁으로 대체."""
    mon, logs = _mk_monitor()
    mon._last_daily_report_date = None
    calls = {"summary": 0, "fund": 0, "screener": 0,
             "equity": 0, "regime": 0, "data_collection": 0}

    def _bump(key, ret=None):
        def _f(*a, **k):
            calls[key] += 1
            return ret
        return _f

    async def _fake_dc(ct):
        calls["data_collection"] += 1

    monkeypatch.setattr(sm, "print_today_trading_summary", _bump("summary"))
    mon._verify_eod_fund_integrity = _bump("fund")
    mon._verify_screener_snapshot = _bump("screener")
    mon._run_equity_snapshot = _bump("equity")
    mon._run_regime_index_refresh = _bump("regime", {"KOSPI": 1, "KOSDAQ": 1})
    mon._run_data_collection = _fake_dc
    return mon, logs, calls


def test_postmarket_skips_all_tasks_on_weekend(monkeypatch):
    """주말(토) 15:35 → EOD 후속작업 전부 미실행.

    실달력 사용(is_holiday 미목킹). 토요일은 is_weekend 가 먼저 성립하므로
    holidays 라이브러리/KIS 캐시 파일(cwd 의존) 유무와 무관하게 결정적이다.
    """
    mon, logs, calls = _mk_postmarket_monitor(monkeypatch)
    saturday = datetime.datetime(2026, 7, 18, 15, 36, 0)

    asyncio.run(mon._handle_postmarket_tasks(saturday))

    assert calls["data_collection"] == 0, "휴장일에 EOD 데이터수집이 돌면 T-1 분봉이 DELETE 된다"
    assert calls == {"summary": 0, "fund": 0, "screener": 0,
                     "equity": 0, "regime": 0, "data_collection": 0}, calls


def test_postmarket_runs_all_tasks_on_trading_day(monkeypatch):
    """거래일(목) 15:35 → EOD 후속작업 정상 실행.

    게이트가 과잉(평일까지 차단)이 아님을 고정한다. is_market_open() 을 게이트로
    쓰면 15:35 는 장마감 후라 False → 매일 수집이 죽는다(이 테스트가 그 회귀를 잡음).
    """
    mon, logs, calls = _mk_postmarket_monitor(monkeypatch)
    thursday = datetime.datetime(2026, 7, 16, 15, 36, 0)

    asyncio.run(mon._handle_postmarket_tasks(thursday))

    assert calls["data_collection"] == 1
    assert calls == {"summary": 1, "fund": 1, "screener": 1,
                     "equity": 2, "regime": 1, "data_collection": 1}, calls


def test_postmarket_skips_when_calendar_says_holiday(monkeypatch):
    """평일 공휴일(제헌절 등) → 스킵.

    2026-07-17 의 휴장 사실은 KIS 캐시(holiday_kis_cache.json)에만 있고 그 로드가
    cwd 의존이라 실달력을 그대로 쓰면 테스트가 실행위치에 좌우된다. 여기서는
    달력 정확성이 아니라 '달력이 휴장이라 하면 스킵한다'는 게이트 배선만 고정한다.
    """
    mon, logs, calls = _mk_postmarket_monitor(monkeypatch)
    monkeypatch.setattr(sm, "is_holiday", lambda d: True)

    asyncio.run(mon._handle_postmarket_tasks(datetime.datetime(2026, 7, 17, 15, 36, 0)))

    assert calls["data_collection"] == 0
    assert sum(calls.values()) == 0, calls


def test_postmarket_holiday_skip_logs_info_once(monkeypatch):
    """스킵 시 INFO 1회만 — 5초 루프마다 반복 로깅하지 않음(하루 1회 래치 재사용)."""
    mon, logs, calls = _mk_postmarket_monitor(monkeypatch)
    monkeypatch.setattr(sm, "is_holiday", lambda d: True)

    base = datetime.datetime(2026, 7, 17, 15, 36, 0)
    for i in range(5):   # 모니터 루프 반복
        asyncio.run(mon._handle_postmarket_tasks(base + datetime.timedelta(seconds=5 * i)))

    assert calls["data_collection"] == 0
    skip_logs = [a for a in logs["info"] if a and "휴장일" in str(a[0])]
    assert len(skip_logs) == 1, f"스킵 INFO 는 하루 1회여야 함: {logs['info']}"

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

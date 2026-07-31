"""_verify_screener_snapshot 날짜 기준 정합성 테스트 (2026-07-31).

배경: run_screener_snapshot_hook(bot/liquidation_handler.py)은
scan_date=get_previous_trading_day(now_kst()).date() (D-1 거래일)로 저장하는데
(당일 일봉은 quant 에 ~15:35 적재되므로 당일 키를 쓰면 빈 유니버스가 됨),
검증 쿼리(_verify_screener_snapshot)는 CURRENT_DATE(당일)로 카운트를 세고 있었다.
결과: 훅이 정상 저장해도 검증은 구조적으로 항상 0건을 반환하고, "0건은 후보 없음"
문구가 붙어 정상처럼 보이는 거짓 안심 채널이 됐다(2026-07-31 로그로 실증:
같은 날 훅이 8전략 저장 성공 로그를 남겼는데 검증은 0건 보고).
"""
import datetime
import types

import bot.system_monitor as sm
import db.connection as dbconn


def _mk_monitor():
    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)  # __init__ 우회
    logs = {"info": [], "warning": [], "error": []}
    mon.logger = types.SimpleNamespace(
        info=lambda *a, **k: logs["info"].append(a),
        warning=lambda *a, **k: logs["warning"].append(a),
        error=lambda *a, **k: logs["error"].append(a),
    )
    return mon, logs


class _FakeCursor:
    def __init__(self, captured, row):
        self._captured = captured
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        self._captured["query"] = query
        self._captured["params"] = params

    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self, captured, row):
        self._captured = captured
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _FakeCursor(self._captured, self._row)


class _FakeConnCtx:
    def __init__(self, captured, row):
        self._captured = captured
        self._row = row

    def __enter__(self):
        return _FakeConn(self._captured, self._row)

    def __exit__(self, *a):
        return False


def _patch_fake_db(monkeypatch, captured, row=(20,)):
    def fake_get_connection(cls=None):
        return _FakeConnCtx(captured, row)
    monkeypatch.setattr(dbconn.DatabaseConnection, "get_connection", classmethod(fake_get_connection))


def _mk_monitor_with_hook_done(today):
    mon, logs = _mk_monitor()
    mon.bot = types.SimpleNamespace(
        liquidation_handler=types.SimpleNamespace(_snapshot_done_date=today))
    return mon, logs


def test_verify_screener_snapshot_queries_same_date_hook_saved_with(monkeypatch):
    """검증 쿼리가 훅이 실제로 저장에 쓴 scan_date(D-1 거래일)를 바인딩해야 한다.

    훅의 scan_date 계산과 100% 동일한 산식(get_previous_trading_day(now_kst()).date())
    으로 기대값을 뽑아 비교한다 — 날짜를 하드코딩하면 우연히 맞아떨어질 수 있어
    판별력이 없다.
    """
    # SCREENER_SNAPSHOT_ENABLED 는 _verify_screener_snapshot 내부에서
    # `from config.constants import SCREENER_SNAPSHOT_ENABLED` 로 매 호출마다
    # 다시 읽으므로, 패치 대상은 sm 모듈 속성이 아니라 config.constants 뿐이다
    # (sm.SCREENER_SNAPSHOT_ENABLED 패치는 no-op, 2026-07-31 리뷰 지적).
    import config.constants as consts
    monkeypatch.setattr(consts, "SCREENER_SNAPSHOT_ENABLED", True)

    fixed_now = datetime.datetime(2026, 7, 31, 15, 40, 0)
    monkeypatch.setattr(sm, "now_kst", lambda: fixed_now)

    # 훅과 동일한 산식으로 기대 scan_date 계산 (liquidation_handler.py:595 과 동형)
    expected_scan_date = sm.get_previous_trading_day(fixed_now).date()

    captured = {}
    _patch_fake_db(monkeypatch, captured)

    mon, logs = _mk_monitor_with_hook_done(fixed_now.date())
    mon._verify_screener_snapshot()

    assert captured.get("params") == (expected_scan_date,), (
        f"검증 쿼리가 훅과 다른 날짜를 조회함: expected params=({expected_scan_date},), "
        f"got={captured.get('params')!r} (query={captured.get('query')!r})"
    )


def test_verify_screener_snapshot_log_includes_queried_date(monkeypatch):
    """정상(count>0)일 땐 조용해야 한다 — INFO 로 D-1 날짜만 남기고 WARNING 은 없어야 한다.

    무조건 WARNING 을 찍는 구현도 "로그에 날짜가 있는지"만 보면 통과해버리므로
    (2026-07-31 리뷰 지적), count>0 케이스에서 WARNING 이 없다는 것까지 고정한다.
    """
    # SCREENER_SNAPSHOT_ENABLED 는 _verify_screener_snapshot 내부에서
    # `from config.constants import SCREENER_SNAPSHOT_ENABLED` 로 매 호출마다
    # 다시 읽으므로, 패치 대상은 sm 모듈 속성이 아니라 config.constants 뿐이다
    # (sm.SCREENER_SNAPSHOT_ENABLED 패치는 no-op, 2026-07-31 리뷰 지적).
    import config.constants as consts
    monkeypatch.setattr(consts, "SCREENER_SNAPSHOT_ENABLED", True)

    fixed_now = datetime.datetime(2026, 7, 31, 15, 40, 0)
    monkeypatch.setattr(sm, "now_kst", lambda: fixed_now)
    expected_scan_date = sm.get_previous_trading_day(fixed_now).date()

    captured = {}
    _patch_fake_db(monkeypatch, captured, row=(20,))

    mon, logs = _mk_monitor_with_hook_done(fixed_now.date())
    mon._verify_screener_snapshot()

    all_msgs = [str(a) for a in logs["info"] + logs["warning"]]
    assert any(str(expected_scan_date) in m for m in all_msgs), (
        f"로그에 조회 날짜({expected_scan_date})가 없음: {all_msgs}"
    )
    assert not logs["warning"], (
        f"정상(count>0)인데 WARNING 이 찍힘 — 무조건 WARNING 구현도 통과시키면 안 됨: {logs['warning']}"
    )


def test_verify_screener_snapshot_zero_count_is_warning_not_reassurance(monkeypatch):
    """DB 저장 0건은 더 이상 '후보 없음'으로 조용히 넘어가지 않고 WARNING이어야 한다.

    검증 쿼리가 훅과 같은 날짜를 조회하게 된 이상, 0건은 진짜 이상 신호다
    (원래 문구 "0건은 후보 없음"은 날짜 불일치로 인한 구조적 0건을 정상으로
    위장시켰다).
    """
    # SCREENER_SNAPSHOT_ENABLED 는 _verify_screener_snapshot 내부에서
    # `from config.constants import SCREENER_SNAPSHOT_ENABLED` 로 매 호출마다
    # 다시 읽으므로, 패치 대상은 sm 모듈 속성이 아니라 config.constants 뿐이다
    # (sm.SCREENER_SNAPSHOT_ENABLED 패치는 no-op, 2026-07-31 리뷰 지적).
    import config.constants as consts
    monkeypatch.setattr(consts, "SCREENER_SNAPSHOT_ENABLED", True)

    fixed_now = datetime.datetime(2026, 7, 31, 15, 40, 0)
    monkeypatch.setattr(sm, "now_kst", lambda: fixed_now)

    captured = {}
    _patch_fake_db(monkeypatch, captured, row=(0,))

    mon, logs = _mk_monitor_with_hook_done(fixed_now.date())
    mon._verify_screener_snapshot()

    assert logs["warning"], f"0건인데 WARNING 이 없음: info={logs['info']}"
    assert not any("후보 없음" in str(a) for a in logs["info"]), (
        "0건을 여전히 '후보 없음'으로 INFO 처리해 거짓 안심을 주고 있음"
    )

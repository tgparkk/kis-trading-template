# tests/test_repair_cli.py
"""`scripts/repair_corp_action_prices.py` — 이 CLI 의 «첫» 커밋된 테스트.

🔴🔴 안전 요구사항 (편의가 아니다) — 이 파일은:
  - 진짜 DB 접속을 만들지 않는다. 전부 가짜 `conn`/`cursor`.
  - 네트워크·KIS API 를 호출하지 않는다.
  - `api.kis_auth` 를 «진짜로» import 하거나 `auth()` 를 호출하지 않는다.
    `_run()` 안의 `from api.kis_auth import auth` 가 진짜 모듈에 닿지 않도록
    `sys.modules["api"]`/`sys.modules["api.kis_auth"]`/`sys.modules["api.kis_market_api"]`
    를 매 테스트마다 새 가짜 모듈로 «완전히 교체»한다(레포의 `api/__init__.py` 는
    자기 안에서 `from . import kis_auth` 를 하므로, `api` 패키지째 교체하지 않으면
    다른 테스트 파일이 이미 real `api` 를 import 해 둔 경우 `getattr(api, "kis_auth")`
    가 fallback 없이 곧장 real 모듈을 돌려준다 — 그래서 패키지 객체 자체를 새로 만든다).
  - `scripts/repair_corp_action_prices.py` · `collectors/adj_repair.py` ·
    `db/adj_backup.py` 를 수정하지 않는다. 발견한 결함은 고치지 않고 보고한다
    (붉게 만들어야 하면 `xfail(strict=True)`).

가짜로 대체하는 것: `api.kis_auth`·`api.kis_market_api`(위험/네트워크 — 항상 가짜) ·
`conn`(항상 가짜 — 진짜 DB 접속 자체가 금지). 실물을 그대로 쓰는 것:
`collectors.adj_repair`(순수 로직, DB·네트워크 미접근) · `db.adj_backup`(SQL 문자열
빌더, 가짜 conn 위에서만 실행) · `config.constants`(상수뿐) — 이래야 CLI 와 그
아래 실물 모듈들의 «배선»까지 검증한다(모든 걸 두껍게 mock 하면 결함이 mock 뒤에
숨는다 — 이 저장소의 전례).
"""
import argparse
import re
import sys
import types
from datetime import datetime

import pandas as pd
import pytest

import collectors as collectors_pkg
import collectors.adj_repair as real_R
import collectors.daily_adj as daily_adj
import scripts.repair_corp_action_prices as cli


# ============================================================================
# 가짜 api.* 설치 — 안전 요구사항의 핵심 (위 모듈 docstring 참고)
# ============================================================================
def _install_fake_api(monkeypatch, *, auth_return=True, auth_side_effect=None,
                      fetch_fn=None):
    """`api`·`api.kis_auth`·`api.kis_market_api` 를 «새 가짜 모듈 객체»로 완전 교체.

    실물 `api/__init__.py` 를 절대 실행하지 않는다 — `sys.modules["api"]` 를
    직접 새 `types.ModuleType` 으로 바꿔치기하므로, `from api.kis_auth import auth`
    도 `from api import kis_market_api` 도 이 가짜만 본다.
    """
    fake_api = types.ModuleType("api")
    fake_kis_auth = types.ModuleType("api.kis_auth")
    fake_kis_market = types.ModuleType("api.kis_market_api")

    auth_mock = _Recorder(return_value=auth_return, side_effect=auth_side_effect)
    fake_kis_auth.auth = auth_mock

    fetch_mock = _Recorder(side_effect=fetch_fn) if fetch_fn is not None else _Recorder()
    fake_kis_market.get_inquire_daily_itemchartprice_extended = fetch_mock

    fake_api.kis_auth = fake_kis_auth
    fake_api.kis_market_api = fake_kis_market

    monkeypatch.setitem(sys.modules, "api", fake_api)
    monkeypatch.setitem(sys.modules, "api.kis_auth", fake_kis_auth)
    monkeypatch.setitem(sys.modules, "api.kis_market_api", fake_kis_market)
    return auth_mock, fetch_mock


class _Recorder:
    """아주 작은 call-recording stub — `unittest.mock.Mock` 대체 (의존 최소화)."""

    def __init__(self, return_value=None, side_effect=None):
        self.return_value = return_value
        self.side_effect = side_effect
        self.calls = []
        self.call_count = 0

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        self.call_count += 1
        if self.side_effect is not None:
            if callable(self.side_effect):
                return self.side_effect(*args, **kwargs)
            raise self.side_effect
        return self.return_value


def _install_fake_needs_repair(monkeypatch, fake_needs_repair):
    """`collectors.adj_repair` 를 «부분 가짜»로 교체 — `needs_repair` 만 바꿔치기.

    `_run` 은 `from collectors import adj_repair as R` (package-attribute 폼)를
    쓰므로, 다른 테스트 파일이 이미 real `collectors.adj_repair` 를 import 해서
    `collectors_pkg.adj_repair` 속성이 이미 real 모듈을 가리키고 있을 수 있다
    (예: `test_adj_repair.py`). `sys.modules` 만 바꿔서는 그 속성을 못 이긴다 —
    패키지 객체의 속성 자체도 같이 바꾼다.
    """
    fake_R = types.ModuleType("collectors.adj_repair")
    for name in vars(real_R):
        if not name.startswith("__"):
            setattr(fake_R, name, getattr(real_R, name))
    fake_R.needs_repair = fake_needs_repair
    monkeypatch.setattr(collectors_pkg, "adj_repair", fake_R)
    monkeypatch.setitem(sys.modules, "collectors.adj_repair", fake_R)


# ============================================================================
# 가짜 conn/cursor — SQL 문자열의 «내용»으로 분기한다(진짜 스키마 강제 없음)
# ============================================================================
class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self._result = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        s = sql.strip()
        if "FROM corp_events" in sql:
            code = params[0] if params else None
            self._result = [(1,)] if code in self.conn.split_event_codes else []
        elif "SELECT date" in sql and "FROM daily_prices" in sql:
            code = params[0] if params else None
            rows = self.conn.db_rows.get(code, {})
            self._result = [(d,) + tuple(v) for d, v in sorted(rows.items())]
        elif s.upper().startswith("CREATE TABLE"):
            self.conn.ensure_table_calls += 1
            self._result = []
        elif "INSERT INTO daily_prices_preadj_backup" in sql:
            self.conn.backup_calls.append(params)
            n = self.conn.backup_rowcount_override
            self.rowcount = n if n is not None else len(params["dates"])
            self._result = []
        elif s.upper().startswith("UPDATE DAILY_PRICES DP SET"):
            self.conn.restore_calls.append(params)
            self.rowcount = 1
            self._result = []
        elif s.upper().startswith("INSERT INTO DAILY_PRICES "):
            self.conn.upsert_calls.append(params)
            self._result = []
        else:
            raise AssertionError("FakeCursor: unrecognised SQL — {!r}".format(sql[:80]))

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return self._result


class FakeConn:
    def __init__(self, db_rows=None, split_event_codes=(), backup_rowcount_override=None):
        self.db_rows = db_rows or {}
        self.split_event_codes = set(split_event_codes)
        self.backup_rowcount_override = backup_rowcount_override
        self.executed = []
        self.backup_calls = []
        self.upsert_calls = []
        self.restore_calls = []
        self.ensure_table_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


def _args(**kw):
    base = dict(apply=False, codes=None, limit=None, restore=None)
    base.update(kw)
    return argparse.Namespace(**base)


def _kis_row(date_iso, close, vol, o=None, h=None, l=None):
    d8 = date_iso.replace("-", "")
    o = close if o is None else o
    h = close if h is None else h
    l = close if l is None else l
    return {"stck_bsop_date": d8, "stck_oprc": o, "stck_hgpr": h, "stck_lwpr": l,
            "stck_clpr": close, "acml_vol": vol}


def _feed_df(rows):
    cols = ["stck_bsop_date", "stck_oprc", "stck_hgpr", "stck_lwpr", "stck_clpr", "acml_vol"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


def _fetcher_from_feeds(feeds):
    """feeds: {(code, adj_prc): [row, ...] | None} → 실제 kis_market_api 시그니처 흉내."""
    def fetch(div_code, itm_no, inqr_strt_dt, inqr_end_dt, period_code, adj_prc, max_count):
        key = (itm_no, adj_prc)
        assert key in feeds, "no feed configured for {}".format(key)
        rows = feeds[key]
        if rows is None:
            return None
        return _feed_df(rows)
    return fetch


# ============================================================================
# A. 종료코드 계약
# ============================================================================
def test_exit_codes_are_five_distinct_values_and_fetch_differs_from_ok():
    """🔴 핵심 계약 — EXIT_FETCH 가 EXIT_OK 와 «다른 값»이어야 브로커 장애가
    정상 완료로 안 보인다."""
    codes = {cli.EXIT_OK, cli.EXIT_AUTH, cli.EXIT_ABORT, cli.EXIT_FETCH, cli.EXIT_INPUT}
    assert len(codes) == 5
    assert cli.EXIT_OK == 0
    assert cli.EXIT_FETCH != cli.EXIT_OK


# ============================================================================
# B. 안전 게이트 — --apply 경로에서 「쓰지 않고 중단」하는 5가지
# ============================================================================
def test_gate1_impossible_bars_increase_aborts_without_writing(monkeypatch):
    """게이트 1 — 불가능봉이 늘면(before < after) 그 종목은 쓰지 않는다."""
    code = "G1CODE"
    db_rows = {
        "2026-05-28": (1000.0, 1000.0, 1000.0, 1000.0, 100, 1.0),
        "2026-05-29": (1010.0, 1010.0, 1010.0, 1010.0, 100, 1.0),
    }
    # 조정피드 close=5000 → 병합하면 1000→5000 (+400%) 가 새로 생긴다.
    feeds = {
        (code, "1"): [_kis_row("2026-05-29", 1010, 100)],
        (code, "0"): [_kis_row("2026-05-29", 5000, 100)],
    }
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))
    conn = FakeConn(db_rows={code: db_rows})
    a = _args(apply=True, codes=code)

    rc = cli._run(a, conn)

    assert rc == cli.EXIT_ABORT
    assert conn.upsert_calls == []
    assert conn.backup_calls == []


def test_gate1_removed_lets_the_bad_write_through(monkeypatch):
    """이빨 검증 — 게이트 1 을 빼면 같은 시나리오가 실제로 UPSERT 까지 간다."""
    code = "G1CODE"
    db_rows = {
        "2026-05-28": (1000.0, 1000.0, 1000.0, 1000.0, 100, 1.0),
        "2026-05-29": (1010.0, 1010.0, 1010.0, 1010.0, 100, 1.0),
    }
    feeds = {
        (code, "1"): [_kis_row("2026-05-29", 1010, 100)],
        (code, "0"): [_kis_row("2026-05-29", 5000, 100)],
    }
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))
    conn = FakeConn(db_rows={code: db_rows})
    a = _args(apply=True, codes=code)

    mutated_run = _mutated_run(remove="""        if after > before:
            return _abort(batch_id, code, n_committed,
                          f"불가능봉이 늘었다({before}->{after}) — 이 종목은 쓰지 않았다")
""")
    rc = mutated_run(a, conn)

    assert rc != cli.EXIT_ABORT
    assert conn.upsert_calls != [], "가드를 빼면 정말로 UPSERT 까지 간다는 걸 못 보임 — 이빨 없음"


def test_gate2_volume_value_change_aborts_without_writing(monkeypatch):
    """게이트 2 — 기존 volume 이 있는데 값이 바뀌면 중단한다."""
    code = "G2CODE"
    db_rows = {"2026-05-29": (760.0, 760.0, 760.0, 760.0, 1000, 1.0)}
    feeds = {
        (code, "1"): [_kis_row("2026-05-29", 760, 5000)],   # volume 1000 -> 5000
        (code, "0"): [_kis_row("2026-05-29", 760, 5000)],
    }
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))
    conn = FakeConn(db_rows={code: db_rows})
    a = _args(apply=True, codes=code)

    rc = cli._run(a, conn)

    assert rc == cli.EXIT_ABORT
    assert conn.upsert_calls == []
    assert conn.backup_calls == []


def test_gate3_null_existing_volume_aborts_without_writing(monkeypatch):
    """게이트 3 — 기존 volume 이 NULL 이면 「검증 불가」를 「이상 없음」으로 접지 않는다."""
    code = "G3CODE"
    db_rows = {"2026-05-29": (760.0, 760.0, 760.0, 760.0, None, 1.0)}
    feeds = {
        (code, "1"): [_kis_row("2026-05-29", 760, 5000)],
        (code, "0"): [_kis_row("2026-05-29", 760, 5000)],
    }
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))
    conn = FakeConn(db_rows={code: db_rows})
    a = _args(apply=True, codes=code)

    rc = cli._run(a, conn)

    assert rc == cli.EXIT_ABORT
    assert conn.upsert_calls == []
    assert conn.backup_calls == []


def test_gate2and3_removed_lets_the_volume_violation_through(monkeypatch):
    """이빨 검증 — volume 불변 게이트(2·3 은 같은 `if` 한 줄)를 빼면 UPSERT 까지 간다."""
    code = "G2CODE"
    db_rows = {"2026-05-29": (760.0, 760.0, 760.0, 760.0, 1000, 1.0)}
    feeds = {
        (code, "1"): [_kis_row("2026-05-29", 760, 5000)],
        (code, "0"): [_kis_row("2026-05-29", 760, 5000)],
    }
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))
    conn = FakeConn(db_rows={code: db_rows})
    a = _args(apply=True, codes=code)

    mutated_run = _mutated_run(remove="""        if vol_diff or vol_null:
            return _abort(batch_id, code, n_committed,
                          f"volume 이 바뀐다(값 변경 {vol_diff}건 · 기존 NULL {vol_null}건) — "
                          f"「기존도 원본, 새것도 원본」이라는 전제가 틀렸다는 뜻이다"
                          f"(사양 §6-4). 이 종목은 쓰지 않았다")
""")
    rc = mutated_run(a, conn)

    assert rc != cli.EXIT_ABORT
    assert conn.upsert_calls != [], "가드를 빼면 정말로 UPSERT 까지 간다는 걸 못 보임 — 이빨 없음"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "발견한 결함(고치지 않고 보고) — needs_repair 가 계약을 어기고 DB 에 없는 "
        "날짜를 돌려주면, 그 뒤의 「absent 게이트」(사양 §6-3의 4번째 방어선)가 "
        "실행되기도 «전에» vol_diff/vol_null 계산의 무가드 `db[r[\"date\"]]` 색인이 "
        "KeyError 로 먼저 죽는다. dry-run 여부와도 무관하다 — 그 줄은 "
        "`if not a.apply or not todo: continue` 보다도 앞에 있다. 즉 이 코드 경로로는 "
        "absent 게이트가 «도달 불가능»하다."
    ),
)
def test_gate4_absent_date_from_needs_repair_is_rejected_cleanly(monkeypatch):
    """게이트 4 의 «의도된» 계약 — needs_repair 가 DB 에 없는 날짜를 돌려줘도
    CLI 가 그걸 다시 걸러 EXIT_ABORT 로 깔끔히 중단해야 한다(사양이 말하는 대로).
    실제로는 KeyError 로 죽는다 — xfail(strict=True) 로 고정, 위 reason 참고.
    """
    code = "G4CODE"
    db_rows = {"2026-05-29": (100.0, 100.0, 100.0, 100.0, 500, 1.0)}
    feeds = {
        (code, "1"): [_kis_row("2026-05-29", 100, 500)],
        (code, "0"): [_kis_row("2026-05-29", 100, 500)],
    }
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))

    def fake_needs_repair(db, new_rows):
        # DB 에 «전혀 없는» 날짜를 하나 섞어 돌려준다 — needs_repair 의 계약 위반을
        # 시뮬레이션해 CLI 자체 재검증(§6-3 4번째 게이트)이 잡아내는지를 본다.
        return [{"stock_code": code, "date": "1999-01-01", "open": 100.0, "high": 100.0,
                 "low": 100.0, "close": 100.0, "volume": 500, "adj_factor": 1.0}]

    _install_fake_needs_repair(monkeypatch, fake_needs_repair)
    conn = FakeConn(db_rows={code: db_rows})
    a = _args(apply=True, codes=code)

    rc = cli._run(a, conn)

    assert rc == cli.EXIT_ABORT
    assert conn.upsert_calls == []


def test_gate4_absent_date_actually_crashes_with_keyerror_current_reality(monkeypatch):
    """🔴 위 xfail 의 짝 — «현재 실제 동작»을 양성 테스트로 고정해 둔다(회귀 감시용).

    이 테스트가 실패하게 되면(=더 이상 KeyError 가 안 나면) 위 xfail(strict=True)
    테스트가 XPASS 로 터져서 누군가 반드시 알아채게 설계돼 있다.
    """
    code = "G4CODE"
    db_rows = {"2026-05-29": (100.0, 100.0, 100.0, 100.0, 500, 1.0)}
    feeds = {
        (code, "1"): [_kis_row("2026-05-29", 100, 500)],
        (code, "0"): [_kis_row("2026-05-29", 100, 500)],
    }
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))

    def fake_needs_repair(db, new_rows):
        return [{"stock_code": code, "date": "1999-01-01", "open": 100.0, "high": 100.0,
                 "low": 100.0, "close": 100.0, "volume": 500, "adj_factor": 1.0}]

    _install_fake_needs_repair(monkeypatch, fake_needs_repair)
    conn = FakeConn(db_rows={code: db_rows})
    a = _args(apply=True, codes=code)

    with pytest.raises(KeyError):
        cli._run(a, conn)
    assert conn.upsert_calls == []   # 어느 쪽이든(죽거나 abort 하거나) 쓰기는 없다


def test_gate5_backup_row_count_mismatch_aborts_without_upserting(monkeypatch):
    """게이트 5 — 백업 확인은 «등호». 기대(len(todo))보다 적어도(0) 위반이다."""
    code = "G5CODE"
    db_rows = {"2026-05-29": (760.0, 760.0, 760.0, 760.0, 1000, 1.0)}
    feeds = {
        (code, "1"): [_kis_row("2026-05-29", 800, 1000)],
        (code, "0"): [_kis_row("2026-05-29", 800, 1000)],
    }
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))
    conn = FakeConn(db_rows={code: db_rows}, backup_rowcount_override=0)
    a = _args(apply=True, codes=code)

    rc = cli._run(a, conn)

    assert rc == cli.EXIT_ABORT
    assert conn.backup_calls != []          # 백업 시도는 했다(등호 확인 위해)
    assert conn.upsert_calls == []          # 그러나 UPSERT 는 안 갔다


def test_gate5_removed_lets_the_unverified_backup_through(monkeypatch):
    """이빨 검증 — 백업 등호 게이트를 빼면 확인 안 된 백업 위에 그대로 UPSERT 한다."""
    code = "G5CODE"
    db_rows = {"2026-05-29": (760.0, 760.0, 760.0, 760.0, 1000, 1.0)}
    feeds = {
        (code, "1"): [_kis_row("2026-05-29", 800, 1000)],
        (code, "0"): [_kis_row("2026-05-29", 800, 1000)],
    }
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))
    conn = FakeConn(db_rows={code: db_rows}, backup_rowcount_override=0)
    a = _args(apply=True, codes=code)

    mutated_run = _mutated_run(remove="""        if n_backed != len(todo):
            return _abort(batch_id, code, n_committed,
                          f"백업 확인 실패 — 기대 {len(todo)}건, 실제 {n_backed}건. "
                          f"이 종목은 쓰지 않았다")
""")
    rc = mutated_run(a, conn)

    assert rc != cli.EXIT_ABORT
    assert conn.upsert_calls != [], "가드를 빼면 정말로 UPSERT 까지 간다는 걸 못 보임 — 이빨 없음"


# ============================================================================
# C. dry-run 이 정말 아무것도 안 쓴다
# ============================================================================
def test_dry_run_never_calls_ensure_table_backup_or_upsert_even_with_real_diffs(monkeypatch):
    """`--apply` 없이 돌리면 커밋이 «전혀» 없다 — 고칠 거리가 실재해도."""
    code = "DRYCODE"
    db_rows = {"2026-05-29": (760.0, 760.0, 760.0, 760.0, 1000, 1.0)}
    feeds = {
        (code, "1"): [_kis_row("2026-05-29", 800, 1000)],   # 실제로 고칠 게 있다
        (code, "0"): [_kis_row("2026-05-29", 800, 1000)],
    }
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))
    conn = FakeConn(db_rows={code: db_rows})
    a = _args(apply=False, codes=code)

    rc = cli._run(a, conn)

    assert rc == cli.EXIT_OK
    assert conn.commit_calls == 0
    assert conn.ensure_table_calls == 0
    assert conn.backup_calls == []
    assert conn.upsert_calls == []


def test_dry_run_guard_removed_lets_a_write_happen(monkeypatch):
    """이빨 검증 — per-stock dry-run 가드(`if not a.apply or not todo: continue`)를
    빼면 dry-run 인데도 UPSERT 까지 간다."""
    code = "DRYCODE"
    db_rows = {"2026-05-29": (760.0, 760.0, 760.0, 760.0, 1000, 1.0)}
    feeds = {
        (code, "1"): [_kis_row("2026-05-29", 800, 1000)],
        (code, "0"): [_kis_row("2026-05-29", 800, 1000)],
    }
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))
    conn = FakeConn(db_rows={code: db_rows})
    a = _args(apply=False, codes=code)

    mutated_run = _mutated_run(
        remove="if not a.apply or not todo:\n            continue",
        add="if not todo:\n            continue",
    )
    rc = mutated_run(a, conn)

    assert conn.upsert_calls != [], "가드를 빼면 dry-run 인데도 UPSERT 까지 간다는 걸 못 보임 — 이빨 없음"


# ============================================================================
# D. 진입 전제
# ============================================================================
def test_resolve_targets_with_explicit_codes_ignores_the_queue_entirely():
    a = _args(codes="000001, 000002 ,000003")
    got = cli._resolve_targets(a, real_R)
    assert got == ["000001", "000002", "000003"]


def test_resolve_targets_returns_none_not_empty_list_when_queue_file_is_absent(monkeypatch, tmp_path):
    """🔴 큐 파일이 없으면 조용한 `[]` 가 아니라 `None`(→ EXIT_INPUT)."""
    monkeypatch.setattr(cli, "REPO", tmp_path)   # tmp_path 엔 logs/ 자체가 없다
    a = _args(codes=None)
    got = cli._resolve_targets(a, real_R)
    assert got is None


def test_resolve_targets_with_queue_present_delegates_to_load_targets(monkeypatch, tmp_path):
    import json
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    qp = logs_dir / "corp_action_refetch_queue.jsonl"
    qp.write_text(
        json.dumps({"stock_code": "999999", "eligible_after": "2000-01-01",
                    "status": "pending"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "REPO", tmp_path)
    a = _args(codes=None)

    got = cli._resolve_targets(a, real_R)

    assert "999999" in got
    for extra in real_R.EXTRA_CODES:
        assert extra in got


def test_run_returns_exit_input_when_targets_cannot_be_resolved(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "REPO", tmp_path)
    auth_mock, _ = _install_fake_api(monkeypatch)
    conn = FakeConn()
    a = _args(codes=None)

    rc = cli._run(a, conn)

    assert rc == cli.EXIT_INPUT
    assert auth_mock.call_count == 0     # 큐가 없으면 인증조차 시도하지 않는다
    assert conn.executed == []


def test_main_aborts_before_connecting_when_db_name_does_not_match_resolver(monkeypatch):
    """`main()` 의 fail-closed — DB 이름이 resolver 와 다르면 접속도 하기 전에 중단."""
    connect_calls = []

    class FakeKisDbConnection:
        @classmethod
        def get_config(cls):
            return {"host": "h", "port": 1, "database": "definitely_not_kis_template",
                    "user": "u", "password": "p"}

        @classmethod
        def get_connection(cls):
            connect_calls.append(1)
            raise AssertionError("get_connection() 이 호출되면 안 된다 — fail-closed 실패")

        @classmethod
        def close_all(cls):
            pass

    fake_module = types.ModuleType("db.kis_db_connection")
    fake_module.KisDbConnection = FakeKisDbConnection
    monkeypatch.setitem(sys.modules, "db.kis_db_connection", fake_module)
    monkeypatch.setattr(sys, "argv", ["repair_corp_action_prices.py"])

    rc = cli.main()

    assert rc == cli.EXIT_INPUT
    assert connect_calls == []


def test_run_returns_exit_auth_and_makes_no_further_queries_when_auth_fails(monkeypatch):
    auth_mock, fetch_mock = _install_fake_api(monkeypatch, auth_return=False)
    conn = FakeConn()
    a = _args(codes="000001")

    rc = cli._run(a, conn)

    assert rc == cli.EXIT_AUTH
    assert auth_mock.call_count == 1
    assert fetch_mock.call_count == 0
    assert conn.executed == []           # has_split_event/_db_rows 도 전혀 안 갔다


# ============================================================================
# E. 흐름 제어
# ============================================================================
def test_restore_path_skips_target_resolution_auth_and_queries(monkeypatch):
    auth_mock, fetch_mock = _install_fake_api(monkeypatch)
    conn = FakeConn()
    a = _args(restore="BATCH-XYZ")

    rc = cli._run(a, conn)

    assert rc == cli.EXIT_OK
    assert conn.ensure_table_calls == 1
    assert len(conn.restore_calls) == 1
    assert conn.restore_calls[0]["batch_id"] == "BATCH-XYZ"
    assert auth_mock.call_count == 0
    assert fetch_mock.call_count == 0
    assert conn.upsert_calls == []


def test_feed_fetch_error_on_one_stock_is_skipped_but_final_exit_code_is_fetch(monkeypatch):
    """한 종목만 실패해도 «전체» 실행이 EXIT_FETCH — 다른 종목이 성공해도 못 가린다."""
    feeds = {
        ("OKCODE", "1"): [],     # 정상 응답인데 그냥 봉이 없음 (factors=0 → SKIP)
        ("OKCODE", "0"): [],
        ("BADCODE", "1"): None,  # 첫 페이지 요청 자체가 실패 → FeedFetchError
    }
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))
    conn = FakeConn(db_rows={})
    a = _args(apply=False, codes="OKCODE,BADCODE")

    rc = cli._run(a, conn)

    assert rc == cli.EXIT_FETCH
    assert conn.upsert_calls == []


def test_limit_zero_processes_zero_targets_not_unlimited(monkeypatch):
    """🔴 하드닝 — `--limit 0` 은 「제한 없음」이 아니라 「0건」이다."""
    _, fetch_mock = _install_fake_api(monkeypatch)
    conn = FakeConn()
    a = _args(codes="000001,000002,000003", limit=0)

    rc = cli._run(a, conn)

    assert rc == cli.EXIT_OK
    assert fetch_mock.call_count == 0   # 세 종목 중 «한 번도» 조회를 시도 안 했다


def test_limit_none_processes_all_given_targets(monkeypatch):
    """대조군 — `limit=None` 이면 위와 달리 실제로 다 돈다."""
    feeds = {(c, p): [] for c in ("000001", "000002", "000003") for p in ("1", "0")}
    _, fetch_mock = _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))
    conn = FakeConn()
    a = _args(codes="000001,000002,000003", limit=None)

    rc = cli._run(a, conn)

    assert rc == cli.EXIT_OK
    codes_fetched = {call[1]["itm_no"] for call in fetch_mock.calls}
    assert codes_fetched == {"000001", "000002", "000003"}


def test_batch_id_suffix_differs_between_apply_and_dry_run(monkeypatch, capsys):
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds({("X", "1"): [], ("X", "0"): []}))
    conn = FakeConn()
    cli._run(_args(apply=True, codes="X"), conn)
    apply_batch = _extract_batch_id(capsys.readouterr().out)

    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds({("X", "1"): [], ("X", "0"): []}))
    conn2 = FakeConn()
    cli._run(_args(apply=False, codes="X"), conn2)
    dry_batch = _extract_batch_id(capsys.readouterr().out)

    assert apply_batch.endswith("-apply")
    assert dry_batch.endswith("-dry")
    assert apply_batch != dry_batch


def test_batch_id_is_unique_across_two_apply_runs_in_the_same_mode(monkeypatch, capsys):
    """같은 모드(apply)로 두 번 실행해도, 시각이 다르면 batch_id 도 다르다."""
    class _FakeDatetime:
        _seq = [datetime(2026, 8, 20, 10, 0, 0), datetime(2026, 8, 20, 10, 0, 1)]

        @classmethod
        def now(cls):
            return cls._seq.pop(0)

    monkeypatch.setattr(cli, "datetime", _FakeDatetime)
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds({("X", "1"): [], ("X", "0"): []}))
    conn1 = FakeConn()
    cli._run(_args(apply=True, codes="X"), conn1)
    b1 = _extract_batch_id(capsys.readouterr().out)

    conn2 = FakeConn()
    cli._run(_args(apply=True, codes="X"), conn2)
    b2 = _extract_batch_id(capsys.readouterr().out)

    assert b1 != b2
    assert b1 == "repair-20260820-100000-apply"
    assert b2 == "repair-20260820-100001-apply"


def _extract_batch_id(stdout_text):
    m = re.search(r"batch (\S+) ·", stdout_text)
    assert m, "요약 줄에서 batch_id 를 못 찾음: {!r}".format(stdout_text)
    return m.group(1)


def test_rollback_is_called_once_per_stock_plus_once_after_the_loop(monkeypatch):
    feeds = {(c, p): [] for c in ("A1", "A2") for p in ("1", "0")}
    _install_fake_api(monkeypatch, fetch_fn=_fetcher_from_feeds(feeds))
    conn = FakeConn()
    a = _args(apply=False, codes="A1,A2")

    cli._run(a, conn)

    assert conn.rollback_calls == 3   # 종목 2개 × 루프 시작 1번 + 루프 끝 1번


# ============================================================================
# F. 순수 헬퍼
# ============================================================================
def test_close_seq_drops_none_and_nonpositive_close_and_sorts_ascending():
    rows = {
        "2026-05-30": (0, 0, 0, None, 10, 1.0),   # None close → 빠짐
        "2026-05-28": (0, 0, 0, 100.0, 10, 1.0),
        "2026-05-31": (0, 0, 0, 0.0, 10, 1.0),    # 0 close → 빠짐
        "2026-05-29": (0, 0, 0, 105.0, 10, 1.0),
    }
    out = cli._close_seq(rows)
    assert out == [("2026-05-28", 100.0), ("2026-05-29", 105.0)]


def test_kis_fetcher_raises_feedfetcherror_when_first_page_request_fails(monkeypatch):
    _install_fake_api(monkeypatch, fetch_fn=lambda **kw: None)
    with pytest.raises(cli.FeedFetchError):
        cli._kis_fetcher("054940", "20210101", "20260820", "1")


def test_kis_fetcher_returns_empty_list_when_response_is_an_empty_dataframe(monkeypatch):
    _install_fake_api(monkeypatch, fetch_fn=lambda **kw: _feed_df([]))
    assert cli._kis_fetcher("054940", "20210101", "20260820", "1") == []


def test_kis_fetcher_returns_list_of_dicts_and_passes_through_expected_kwargs(monkeypatch):
    _, fetch_mock = _install_fake_api(
        monkeypatch, fetch_fn=lambda **kw: _feed_df([_kis_row("2026-05-29", 3800, 71465)]))

    out = cli._kis_fetcher("054940", "20210101", "20260820", "0")

    assert out == [_kis_row("2026-05-29", 3800, 71465)]
    (_, kwargs), = fetch_mock.calls
    assert kwargs == dict(div_code="J", itm_no="054940", inqr_strt_dt="20210101",
                          inqr_end_dt="20260820", period_code="D", adj_prc="0", max_count=2000)


class _SqlCapture:
    def __init__(self, fetchone_result=None, fetchall_result=None):
        self.sql = None
        self.params = None
        self._fetchone = fetchone_result
        self._fetchall = [] if fetchall_result is None else fetchall_result

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._fetchall


class _ConnCapture:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def commit(self):
        pass


def _where_conditions(sql):
    m = re.search(r"\bWHERE\b(.*?)(\bORDER BY\b|\bLIMIT\b|$)", sql, re.DOTALL | re.IGNORECASE)
    assert m, "no WHERE clause found in: {!r}".format(sql)
    out = []
    for cond in re.split(r"\bAND\b", m.group(1), flags=re.IGNORECASE):
        cond = re.sub(r"\s+", " ", cond).strip()
        if cond:
            out.append(cond)
    return out


def test_has_split_event_predicate_matches_daily_adj_load_split_events_predicate():
    """`has_split_event` 의 술어가 `daily_adj.load_split_events` 의 WHERE 절과
    같은 조건인지 «구조적으로»(정규식 파싱, 부분문자열 아님) 검사한다. 어긋나면
    「다음 EOD 에 덮어써진다」 경고가 엉뚱한 종목에 뜬다(사양 §7-1)."""
    cur_a = _SqlCapture(fetchone_result=None)
    cli.has_split_event(_ConnCapture(cur_a), "005930")
    cur_b = _SqlCapture(fetchall_result=[])
    daily_adj.load_split_events(_ConnCapture(cur_b))

    conds_a = {c.strip() for c in _where_conditions(cur_a.sql)}
    conds_b = {c.strip() for c in _where_conditions(cur_b.sql)}

    # has_split_event 는 종목 하나로 스코프를 좁히는 조건이 «추가»로 있을 뿐,
    # split 탐지 술어 자체(event_type='split' AND meta->>'split_factor' IS NOT NULL)
    # 는 두 곳에서 동일해야 한다.
    extra_scope = {"stock_code = %s"}
    assert conds_a - extra_scope == conds_b, (
        "has_split_event 의 split 탐지 술어가 daily_adj.load_split_events 와 다르다: "
        "{} vs {}".format(sorted(conds_a), sorted(conds_b))
    )


def test_where_condition_comparison_detects_a_dropped_predicate():
    """이빨 검증 — 술어 비교 로직 자체가 진짜로 판별하는지, 합성 SQL로 증명한다
    (실물 모듈은 안 건드린다)."""
    good = "SELECT 1 FROM corp_events WHERE event_type = 'split' AND meta->>'split_factor' IS NOT NULL"
    dropped = "SELECT 1 FROM corp_events WHERE event_type = 'split'"   # split_factor 조건 소실
    conds_good = {c.strip() for c in _where_conditions(good)}
    conds_dropped = {c.strip() for c in _where_conditions(dropped)}
    assert conds_good != conds_dropped


# ---------------------------------------------------------------------------
# UPSERT 상수 — 구조적 파싱(위치별 대응), 부분문자열 검사가 아니다
# ---------------------------------------------------------------------------
_DATA_COLUMNS = ("open", "high", "low", "close", "volume", "adj_factor")


def _parse_upsert_insert_columns(sql):
    m = re.search(r"INSERT INTO daily_prices\s*\(([^)]*)\)", sql)
    assert m, "no INSERT column list found"
    return [c.strip() for c in m.group(1).split(",") if c.strip()]


def _parse_upsert_set_pairs(sql):
    m = re.search(r"\bDO UPDATE SET\b(.*)$", sql, re.DOTALL)
    assert m, "no SET clause found"
    pairs = {}
    for chunk in m.group(1).strip().split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        key, sep, value = chunk.partition("=")
        assert sep, "malformed SET assignment: {!r}".format(chunk)
        pairs[key.strip()] = value.strip()
    return pairs


def test_upsert_inserts_into_daily_prices_with_conflict_target_on_stock_code_and_date():
    assert cli.UPSERT.strip().upper().startswith("INSERT INTO DAILY_PRICES")
    assert "ON CONFLICT (stock_code, date) DO UPDATE" in cli.UPSERT


def test_upsert_set_clause_maps_each_data_column_to_its_own_excluded_value():
    """스왑(예: high=EXCLUDED.low)이나 의도치 않은 컬럼이 섞이면 잡아낸다."""
    pairs = _parse_upsert_set_pairs(cli.UPSERT)
    for col in _DATA_COLUMNS:
        assert pairs.get(col) == "EXCLUDED.{}".format(col), (
            "expected `{0} = EXCLUDED.{0}`, found `{0} = {1}`".format(col, pairs.get(col))
        )
    assert pairs.get("updated_at") == "now()"


def test_upsert_set_clause_never_touches_the_conflict_key_columns():
    """PK(stock_code, date)는 SET 절에 나오면 안 된다 — 나오면 충돌행을 다른 키로
    바꿔치기하는 사고다."""
    pairs = _parse_upsert_set_pairs(cli.UPSERT)
    assert "stock_code" not in pairs
    assert "date" not in pairs


def test_upsert_column_list_check_detects_a_swapped_set_pair():
    """이빨 검증 — 로컬 사본을 일부러 스왑해서 위 체크가 실제로 잡는지 증명한다."""
    mutated = cli.UPSERT.replace(
        "high=EXCLUDED.high, low=EXCLUDED.low",
        "high=EXCLUDED.low, low=EXCLUDED.high",
    )
    assert mutated != cli.UPSERT, "fixture 가 실제로 안 바뀜 — mutation 이 헛돔"
    pairs = _parse_upsert_set_pairs(mutated)
    assert pairs.get("high") != "EXCLUDED.high"


# ============================================================================
# 소스 mutation 헬퍼 — «이빨» 테스트용. 실물 스크립트 파일은 절대 안 바꾼다.
# `inspect.getsource(cli._run)` 로 뽑은 텍스트에서 지정한 조각을 지운(또는 다른
# 텍스트로 바꾼) «로컬 사본»을 만들어 exec 하고, 그 결과 함수 객체를 돌려준다.
# ============================================================================
def _mutated_run(remove, add=""):
    import inspect

    src = inspect.getsource(cli._run)
    assert remove in src, "fixture 가 실제 소스와 어긋났다(스크립트가 바뀌었나?): {!r}".format(remove[:60])
    mutated_src = src.replace(remove, add, 1)
    assert mutated_src != src, "mutation 이 실제로 아무것도 안 바꿈 — 테스트가 공허해진다"

    ns = dict(vars(cli))
    exec(compile(mutated_src, "<mutated _run>", "exec"), ns)
    return ns["_run"]

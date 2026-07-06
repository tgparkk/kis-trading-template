import pandas as pd
from datetime import date

import collectors.foreign_flow_collector as ffc


# ── DB mock helpers (test_index_collector 패턴 미러) ──────────────────────────

class _MockCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _MockConn:
    def __init__(self, *cursors_rows):
        self._queue = [_MockCursor(r) for r in cursors_rows]
        self._pos = 0

    def cursor(self):
        if self._pos >= len(self._queue):
            return _MockCursor()  # 큐 소진 후(upsert 등)엔 빈 커서 반환
        c = self._queue[self._pos]
        self._pos += 1
        return c

    def commit(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _CM:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *a):
        pass


# ── collect_foreign_flow ──────────────────────────────────────────────────────

def test_collect_foreign_flow_upserts_universe(monkeypatch):
    """universe 종목별 네이버 fetch → upsert. 반환 {codes, rows}."""
    # load_universe → 2종목
    monkeypatch.setattr(ffc, "load_universe", lambda conn: ["005930", "000660"])

    captured = {}

    def _fake_fetch(code, max_pages=2):
        captured.setdefault("codes", []).append(code)
        captured.setdefault("pages", []).append(max_pages)
        return pd.DataFrame({
            "date": [date(2026, 6, 12), date(2026, 6, 11)],
            "foreign_net_vol": [100, -50],
        })

    monkeypatch.setattr(ffc, "fetch_foreign_naver", _fake_fetch)
    monkeypatch.setattr(ffc.KisDbConnection, "get_connection", lambda: _CM(_MockConn()))

    out = ffc.collect_foreign_flow("20260612")
    assert out == {"codes": 2, "rows": 4}
    assert captured["codes"] == ["005930", "000660"]
    # EOD 증분: 최근 ~40일 충분 → max_pages=2
    assert all(p == 2 for p in captured["pages"])


def test_collect_foreign_flow_respects_limit(monkeypatch):
    monkeypatch.setattr(ffc, "load_universe", lambda conn: ["005930", "000660", "035420"])
    monkeypatch.setattr(
        ffc, "fetch_foreign_naver",
        lambda code, max_pages=2: pd.DataFrame({"date": [date(2026, 6, 12)], "foreign_net_vol": [1]}),
    )
    monkeypatch.setattr(ffc.KisDbConnection, "get_connection", lambda: _CM(_MockConn()))
    out = ffc.collect_foreign_flow(limit=1)
    assert out == {"codes": 1, "rows": 1}


def test_collect_foreign_flow_skips_empty(monkeypatch):
    monkeypatch.setattr(ffc, "load_universe", lambda conn: ["005930"])
    monkeypatch.setattr(
        ffc, "fetch_foreign_naver",
        lambda code, max_pages=2: pd.DataFrame(columns=["date", "foreign_net_vol"]),
    )
    monkeypatch.setattr(ffc.KisDbConnection, "get_connection", lambda: _CM(_MockConn()))
    out = ffc.collect_foreign_flow()
    assert out == {"codes": 1, "rows": 0}


# ── reconcile_foreign_flow ────────────────────────────────────────────────────

def _patch_dbs(monkeypatch, legacy_rows, new_rows):
    legacy_conn = _MockConn(legacy_rows)
    # new DB: 첫 cursor = SELECT foreign_flow, 두 번째 cursor = INSERT no-op
    new_conn = _MockConn(new_rows, [])
    monkeypatch.setattr(ffc.psycopg2, "connect", lambda **kw: legacy_conn)
    monkeypatch.setattr(ffc.KisDbConnection, "get_connection", lambda: _CM(new_conn))


def test_reconcile_foreign_flow_overlap_match_pass(monkeypatch):
    """(a) 레거시·새 DB 모두 값 존재 + 정확일치 → PASS."""
    _patch_dbs(
        monkeypatch,
        legacy_rows=[("005930", 100), ("000660", -50)],
        new_rows=[("005930", 100), ("000660", -50)],
    )
    result = ffc.reconcile_foreign_flow("2026-06-12")
    assert result["verdict"] == "PASS"
    assert result["real_rows"] == 2
    assert result["new_rows"] == 2
    assert result["value_match"] == 2


def test_reconcile_foreign_flow_legacy_frozen_no_legacy_pass(monkeypatch):
    """(b) 레거시 동결(real_rows=0) + 새 수집 성공(new_rows>0) → PASS(no-legacy)."""
    _patch_dbs(
        monkeypatch,
        legacy_rows=[],
        new_rows=[("005930", 100), ("000660", -50)],
    )
    result = ffc.reconcile_foreign_flow("2026-06-30")
    assert result["verdict"] == "PASS"
    assert result["real_rows"] == 0
    assert result["new_rows"] == 2
    assert result["value_match_rate"] == 1.0
    assert result["coverage"] == 1.0


def test_reconcile_foreign_flow_no_new_data_fail(monkeypatch):
    """(c) 새 수집 0행(new_rows=0) → FAIL(네이버 차단/스크래핑 실패 탐지)."""
    _patch_dbs(
        monkeypatch,
        legacy_rows=[("005930", 100)],
        new_rows=[],
    )
    result = ffc.reconcile_foreign_flow("2026-06-30")
    assert result["verdict"] == "FAIL"
    assert result["new_rows"] == 0


def test_reconcile_foreign_flow_no_new_data_fail_even_when_legacy_empty(monkeypatch):
    """new_rows==0 은 레거시가 비어 있어도 FAIL (수집 실패가 우선)."""
    _patch_dbs(monkeypatch, legacy_rows=[], new_rows=[])
    result = ffc.reconcile_foreign_flow("2026-06-30")
    assert result["verdict"] == "FAIL"
    assert result["new_rows"] == 0


# ── Item 1: T→T-1 reconcile (네이버 T+1 게시 지연 대응) ────────────────────────

def test_prev_trading_day_skips_weekend():
    # 2026-06-29 은 월요일 → 직전 거래일은 금요일 2026-06-26
    assert ffc._prev_trading_day("2026-06-29") == "2026-06-26"
    # 화요일 → 직전 거래일은 월요일
    assert ffc._prev_trading_day("2026-06-30") == "2026-06-29"
    # compact 형식도 허용
    assert ffc._prev_trading_day("20260629") == "2026-06-26"


class _DateAwareCursor:
    """date 파라미터별로 다른 행을 돌려주는 커서 (T vs T-1 검증용)."""

    def __init__(self, rows_by_date):
        self._rows_by_date = rows_by_date
        self._last = []

    def execute(self, sql, params=None):
        if params and "SELECT" in sql.upper():
            self._last = self._rows_by_date.get(params[0], [])
        else:
            self._last = []

    def fetchall(self):
        return self._last

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _DateAwareConn:
    def __init__(self, rows_by_date):
        self._rows_by_date = rows_by_date

    def cursor(self):
        return _DateAwareCursor(self._rows_by_date)

    def commit(self):
        pass

    def close(self):
        pass


def _patch_date_aware(monkeypatch, legacy_by_date, new_by_date):
    monkeypatch.setattr(ffc.psycopg2, "connect", lambda **kw: _DateAwareConn(legacy_by_date))
    monkeypatch.setattr(ffc.KisDbConnection, "get_connection", lambda: _CM(_DateAwareConn(new_by_date)))


def test_reconcile_checks_prev_trading_day_not_today(monkeypatch):
    """T 는 네이버 T+1 지연으로 항상 비어 있어도(정상), T-1 데이터가 있으면 FALSE-FAIL 안 함."""
    # T=2026-06-30(화) → T-1=2026-06-29(월). new DB 는 T-1 만 채워져 있음.
    _patch_date_aware(
        monkeypatch,
        legacy_by_date={},  # 레거시 동결
        new_by_date={"2026-06-29": [("005930", 100), ("000660", -50)]},  # T-1 존재, T 없음
    )
    result = ffc.reconcile_foreign_flow("2026-06-30")
    assert result["check_date"] == "2026-06-29"
    assert result["new_rows"] == 2
    assert result["verdict"] == "PASS"  # no-legacy PASS, 더 이상 거짓 FAIL 없음


def test_reconcile_genuine_prev_day_gap_fails(monkeypatch):
    """T-1 데이터가 실제로 비어 있으면(진짜 네이버 장애) FAIL."""
    _patch_date_aware(
        monkeypatch,
        legacy_by_date={"2026-06-29": [("005930", 100)]},
        new_by_date={"2026-06-30": [("005930", 100)]},  # T 는 있으나 T-1 은 비어 있음
    )
    result = ffc.reconcile_foreign_flow("2026-06-30")
    assert result["check_date"] == "2026-06-29"
    assert result["new_rows"] == 0
    assert result["verdict"] == "FAIL"

# tests/collectors/test_index_collector.py
import collectors.index_collector as ic
from collectors.index_collector import INDEX_TICKERS


def test_index_tickers_map():
    assert INDEX_TICKERS == {"KOSPI": "KS11", "KOSDAQ": "KQ11"}


# ── DB mock helpers ────────────────────────────────────────────────────────────

class _MockCursor:
    """단일 fetchall 반환값을 가진 커서 mock."""
    def __init__(self, rows=None):
        self._rows = rows or []

    def execute(self, *a, **kw):
        pass

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _MockConn:
    """cursor() 호출 순서대로 _cursors 큐에서 반환하는 연결 mock."""
    def __init__(self, *cursors_rows):
        # cursors_rows: 각 cursor() 호출에서 fetchall()이 반환할 rows 목록
        self._queue = [_MockCursor(r) for r in cursors_rows]
        self._pos = 0

    def cursor(self):
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
    """KisDbConnection.get_connection() 반환값 mock (context manager)."""
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *a):
        pass


def _patch_dbs(monkeypatch, legacy_rows, new_rows):
    """legacy_conn(SELECT 1회)과 new_conn(SELECT + INSERT 2회) 패치 헬퍼."""
    legacy_conn = _MockConn(legacy_rows)
    # new DB: 첫 cursor = SELECT index_daily, 두 번째 cursor = INSERT no-op
    new_conn = _MockConn(new_rows, [])
    monkeypatch.setattr(ic.psycopg2, "connect", lambda **kw: legacy_conn)
    monkeypatch.setattr(ic.KisDbConnection, "get_connection", lambda: _CM(new_conn))


# ── reconcile_index 테스트 케이스 ──────────────────────────────────────────────

def test_reconcile_index_exact_match_pass(monkeypatch):
    """(a) KOSPI·KOSDAQ 양쪽 정확일치 → verdict PASS."""
    _patch_dbs(
        monkeypatch,
        legacy_rows=[("KS11", "2650.0"), ("KQ11", "850.0")],
        new_rows=[("KOSPI", "2650.0"), ("KOSDAQ", "850.0")],
    )
    result = ic.reconcile_index("2026-06-26")
    assert result["verdict"] == "PASS"
    assert result["real_rows"] == 2
    assert result["new_rows"] == 2
    assert result["value_match"] == 2


def test_reconcile_index_no_new_data_fail(monkeypatch):
    """(b) index_daily에 당일 데이터 없음(new_rows=0) → FAIL.
    이번 FDR 미설치 버그 재현: 레거시는 정상이지만 새 DB 수집이 조용히 실패한 케이스."""
    _patch_dbs(
        monkeypatch,
        legacy_rows=[("KS11", "2650.0"), ("KQ11", "850.0")],
        new_rows=[],
    )
    result = ic.reconcile_index("2026-06-26")
    assert result["verdict"] == "FAIL"
    assert result["new_rows"] == 0
    assert result["real_rows"] == 2


def test_reconcile_index_provisional_within_1pct_pass(monkeypatch):
    """(c) 당일 잠정치 차이가 상대오차 1% 이내 → PASS.
    예: KOSPI 8411 vs 레거시 8361 ≈ 0.60%, KOSDAQ 804 vs 800 = 0.50% → 모두 허용."""
    _patch_dbs(
        monkeypatch,
        legacy_rows=[("KS11", "8361.0"), ("KQ11", "800.0")],
        new_rows=[("KOSPI", "8411.0"), ("KOSDAQ", "804.0")],
    )
    result = ic.reconcile_index("2026-06-26")
    assert result["verdict"] == "PASS"
    assert result["value_match"] == 2


def test_reconcile_index_large_discrepancy_fail(monkeypatch):
    """(d) 상대오차 1% 초과 엉뚱한 값 → FAIL.
    예: KOSPI 2300 vs 레거시 2650 ≈ 13.2%, KOSDAQ 800 vs 850 ≈ 5.9% → 모두 불일치."""
    _patch_dbs(
        monkeypatch,
        legacy_rows=[("KS11", "2650.0"), ("KQ11", "850.0")],
        new_rows=[("KOSPI", "2300.0"), ("KOSDAQ", "800.0")],
    )
    result = ic.reconcile_index("2026-06-26")
    assert result["verdict"] == "FAIL"
    assert result["value_match"] == 0

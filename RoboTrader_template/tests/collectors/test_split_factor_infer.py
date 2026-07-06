"""Item 3: split_factor 가격갭 추론 테스트 (synthetic daily_prices)."""
from datetime import date

import collectors.split_factor_infer as sfi


# ── _first_clean_gap 단위 ─────────────────────────────────────────────────────

def test_first_clean_gap_detects_2for1_split():
    # 100→100→50(권리락) → ratio 2.0, effective_date = 갭이 난 날
    prices = [
        ("2026-05-04", 100.0),
        ("2026-05-06", 100.0),
        ("2026-05-07", 50.0),
        ("2026-05-08", 51.0),
    ]
    assert sfi._first_clean_gap(prices) == ("2026-05-07", 2)


def test_first_clean_gap_detects_5for1():
    prices = [("2026-05-04", 500.0), ("2026-05-07", 100.0)]
    assert sfi._first_clean_gap(prices) == ("2026-05-07", 5)


def test_first_clean_gap_rejects_normal_moves():
    # 일반 등락(10% 하락)은 갭 아님
    prices = [("2026-05-04", 100.0), ("2026-05-07", 90.0), ("2026-05-08", 88.0)]
    assert sfi._first_clean_gap(prices) is None


def test_first_clean_gap_rejects_non_integer_ratio():
    # ratio 1.7 → round=2 이지만 |1.7-2|=0.3 not < 0.3 → 거부
    prices = [("2026-05-04", 170.0), ("2026-05-07", 100.0)]
    assert sfi._first_clean_gap(prices) is None


def test_first_clean_gap_takes_first_qualifying():
    prices = [
        ("2026-05-04", 100.0),
        ("2026-05-05", 100.0),
        ("2026-05-06", 33.0),   # ratio ~3.03 첫 갭
        ("2026-05-07", 16.0),   # 이후 갭은 무시
    ]
    assert sfi._first_clean_gap(prices) == ("2026-05-06", 3)


# ── infer_and_stamp_split_factors (mock DB) ──────────────────────────────────

class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(sql.upper().split())
        if s.startswith("SELECT STOCK_CODE, EVENT_TYPE, EVENT_DATE FROM CORP_EVENTS"):
            self._rows = list(self.conn.events)
        elif "FROM DAILY_PRICES" in s:
            self._rows = self.conn.prices.get(params[0], [])
        elif s.startswith("UPDATE CORP_EVENTS"):
            self.conn.updates.append(params)
            self._rows = []
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _Conn:
    def __init__(self, events, prices):
        self.events = events
        self.prices = prices
        self.updates = []
        self.committed = 0
        self.rolledback = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolledback += 1


def test_infer_stamps_factor_and_moves_event_date():
    conn = _Conn(
        events=[("005930", "split", date(2026, 5, 1))],  # 공시일
        prices={
            "005930": [
                ("2026-05-01", 100.0),  # 공시일
                ("2026-05-20", 100.0),
                ("2026-05-21", 50.0),   # 권리락(갭)
                ("2026-05-22", 51.0),
            ]
        },
    )
    n = sfi.infer_and_stamp_split_factors(conn)
    assert n == 1
    assert len(conn.updates) == 1
    eff_date, meta_json, sc, etype, old_date = conn.updates[0]
    assert eff_date == "2026-05-21"          # 유효 권리락일로 이동
    assert old_date == date(2026, 5, 1)      # WHERE 는 원 공시일
    assert sc == "005930" and etype == "split"
    import json
    patch = json.loads(meta_json)
    assert patch["split_factor"] == 2
    assert patch["effective_date"] == "2026-05-21"
    assert patch["split_factor_inferred"] is True
    assert conn.committed == 1


def test_infer_skips_when_no_gap_yet_idempotent():
    """권리락 전(갭 없음) → 스탬프 안 함, 재실행해도 동일(멱등)."""
    conn = _Conn(
        events=[("000660", "bonus_issue", date(2026, 5, 1))],
        prices={"000660": [("2026-05-01", 100.0), ("2026-05-02", 99.0)]},
    )
    assert sfi.infer_and_stamp_split_factors(conn) == 0
    assert conn.updates == []
    # 재실행도 0
    assert sfi.infer_and_stamp_split_factors(conn) == 0


def test_infer_handles_bonus_issue_type():
    conn = _Conn(
        events=[("012345", "bonus_issue", date(2026, 3, 10))],
        prices={"012345": [("2026-03-10", 300.0), ("2026-03-25", 100.0)]},  # 3:1
    )
    assert sfi.infer_and_stamp_split_factors(conn) == 1
    _, meta_json, _, etype, _ = conn.updates[0]
    assert etype == "bonus_issue"
    import json
    assert json.loads(meta_json)["split_factor"] == 3

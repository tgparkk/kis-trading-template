# tests/collectors/test_daily_adj.py
from datetime import date

import collectors.daily_adj as dadj
from collectors.daily_adj import _adj_update_rows


# ── R4: 자가치유 — 전체 상태(1.0 포함) 재기록 ────────────────────────────────

def test_adj_update_rows_writes_full_state_including_unity_for_reset():
    """R4: != 1.0 만 쓰던 예전 필터는 이벤트가 정정돼도 잘못된 값을 원복하지
    못했다(자가치유 불가). 이제는 이벤트가 있는 종목의 전 날짜를 완전히
    재기록(1.0 포함)해 정정 시 자동으로 원복되도록 한다."""
    adj_map = {"A": {"2022-01-03": 5.0, "2022-05-02": 1.0}}
    rows = _adj_update_rows(adj_map)
    assert rows == [(5.0, "A", "2022-01-03"), (1.0, "A", "2022-05-02")]


# ── R1(cont.)/R2: load_split_events — COALESCE(effective_date, event_date) + dedupe ──

class _RawCorpEventsCursor:
    """실제 SQL의 COALESCE(effective_date, event_date) + event_type='split' 필터를
    파이썬으로 충실히 재현하는 fake 커서(raw corp_events 행에서 직접 계산)."""

    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(sql.upper().split())
        if "FROM CORP_EVENTS" in s:
            out = []
            for stock_code, event_type, event_date, meta in self.conn.raw_events:
                if event_type != "split":
                    continue
                meta = meta or {}
                sf = meta.get("split_factor")
                if sf is None:
                    continue
                eff_iso = meta.get("effective_date")
                eff_date = date.fromisoformat(eff_iso) if eff_iso else event_date
                out.append((stock_code, eff_date, float(sf), meta.get("direction")))
            out.sort(key=lambda r: (r[0], r[1]))
            self._rows = out
        elif "FROM DAILY_PRICES" in s:
            self._rows = self.conn.stock_dates_rows
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _RawConn:
    def __init__(self, raw_events, stock_dates_rows=None):
        self.raw_events = raw_events  # [(stock_code, event_type, event_date, meta_dict), ...]
        self.stock_dates_rows = stock_dates_rows or []
        self.committed = 0

    def cursor(self):
        return _RawCorpEventsCursor(self)

    def commit(self):
        self.committed += 1


def test_load_split_events_uses_effective_date_when_present():
    """새 DART 스탬프 행(effective_date=권리락일)은 event_date(공시일 PK)가 아니라
    effective_date 로 조정 시점이 해석돼야 한다."""
    conn = _RawConn(raw_events=[
        ("001130", "split", date(2026, 3, 12),
         {"split_factor": 11, "effective_date": "2026-05-18"}),
    ])
    events = dadj.load_split_events(conn)
    assert events["001130"] == [(date(2026, 5, 18), 11.0)]  # 공시일(03-12) 아님


def test_load_split_events_falls_back_to_event_date_for_legacy_pykrx_rows():
    """effective_date 가 없는 레거시 pykrx 백필 105건은 event_date(이미 ex-date로
    적재됨)를 그대로 사용해야 한다."""
    conn = _RawConn(raw_events=[
        ("005930", "split", date(2021, 1, 15), {"split_factor": 50}),  # effective_date 없음
    ])
    events = dadj.load_split_events(conn)
    assert events["005930"] == [(date(2021, 1, 15), 50.0)]


def test_load_split_events_dedupes_duplicate_rows_same_effective_date():
    """R2: 동일 (종목, 권리락일)에 대해 중복 행(공시일-PK 행 + 과거 코드가 PK를 이미
    이동시켜 만든 ex-date-PK 행)이 있어도 팩터를 한 번만 반영 — 이중조정(11×11=121)
    방지."""
    conn = _RawConn(raw_events=[
        # 신규 수집(disclosure-date PK, effective_date meta로 05-18 가리킴)
        ("001130", "split", date(2026, 3, 12),
         {"split_factor": 11, "effective_date": "2026-05-18"}),
        # 과거 버전 코드가 이미 PK를 이동시켜 만든 행(event_date=eff_date 자체)
        ("001130", "split", date(2026, 5, 18), {"split_factor": 11}),
    ])
    events = dadj.load_split_events(conn)
    assert events["001130"] == [(date(2026, 5, 18), 11.0)]  # 1건만 — 제곱 아님


def test_dedupe_prevents_double_adjustment_end_to_end(monkeypatch):
    """R2: 중복 corp_events 행이 있어도 update_adj_factors 최종 계산이 factor^2(121)
    아닌 단일 factor(11)여야 한다."""
    captured_batches = []
    monkeypatch.setattr(
        dadj.psycopg2.extras, "execute_batch",
        lambda cur, sql, rows, page_size=1000: captured_batches.append(list(rows)))
    conn = _RawConn(
        raw_events=[
            ("001130", "split", date(2026, 3, 12),
             {"split_factor": 11, "effective_date": "2026-05-18"}),
            ("001130", "split", date(2026, 5, 18), {"split_factor": 11}),
        ],
        stock_dates_rows=[("001130", "2026-05-01")],  # 권리락 이전 날짜 → 조정 대상
    )
    dadj.update_adj_factors(conn)
    rows = captured_batches[-1]
    assert rows == [(11.0, "001130", "2026-05-01")]  # 121.0 아님


# ── R4: 자가치유 통합 테스트 — 잘못된 스탬프가 정정되면 1.0 으로 원복 ─────────

def test_update_adj_factors_self_heals_when_event_corrected(monkeypatch):
    """R4: 이벤트가 잘못 스탬프된 뒤 정정되면, 더 이상 커버되지 않는 날짜의
    adj_factor 가 다음 실행에서 1.0 으로 자동 원복돼야 한다(과거엔 != 1.0 만 써서
    원복이 안 됐음)."""
    captured_batches = []
    monkeypatch.setattr(
        dadj.psycopg2.extras, "execute_batch",
        lambda cur, sql, rows, page_size=1000: captured_batches.append(list(rows)))

    stock_dates_rows = [
        ("BAD1", "2024-01-01"),
        ("BAD1", "2024-06-01"),
        ("BAD1", "2024-12-01"),
    ]

    # Run 1: 잘못된 effective_date(2024-12-31, 실제보다 늦음) → 12-01 까지 과다조정
    conn1 = _RawConn(
        raw_events=[("BAD1", "split", date(2024, 1, 1),
                     {"split_factor": 5, "effective_date": "2024-12-31"})],
        stock_dates_rows=stock_dates_rows,
    )
    n1 = dadj.update_adj_factors(conn1)
    run1 = captured_batches[-1]
    assert set(run1) == {
        (5.0, "BAD1", "2024-01-01"),
        (5.0, "BAD1", "2024-06-01"),
        (5.0, "BAD1", "2024-12-01"),  # 과다조정(버그) — 정정 대상
    }

    # Run 2: 이벤트 정정(effective_date → 2024-06-15, 실제 권리락일)
    conn2 = _RawConn(
        raw_events=[("BAD1", "split", date(2024, 1, 1),
                     {"split_factor": 5, "effective_date": "2024-06-15"})],
        stock_dates_rows=stock_dates_rows,
    )
    n2 = dadj.update_adj_factors(conn2)
    run2 = captured_batches[-1]
    assert (5.0, "BAD1", "2024-01-01") in run2
    assert (5.0, "BAD1", "2024-06-01") in run2
    assert (1.0, "BAD1", "2024-12-01") in run2  # 자가치유: 1.0 으로 원복
    assert n1 == 3 and n2 == 3  # 전체 상태 재기록(1.0 포함) — stock_dates 개수와 동일


# ── 2026-08-03: 액면병합 방향 부호 ───────────────────────────────────────────

def test_directional_factor_inverts_merge_but_not_split():
    """meta.split_factor 는 병합에도 >1 이다(실측: 011930 1:10 병합 sf=10.0 ==
    058430 10:1 분할 sf=10.0). 규약 adj_close = raw_close / adj_factor 에서
    병합은 계수가 뒤집혀야 한다 — 안 뒤집으면 과거 가격이 정반대로 sf**2 만큼 틀어진다."""
    assert dadj._directional_factor(10.0, "split") == 10.0
    assert dadj._directional_factor(10.0, None) == 10.0      # 레거시 = 정방향 해석
    assert dadj._directional_factor(10.0, "merge") == 0.1
    assert dadj._directional_factor(2.5, "merge") == 0.4


def test_directional_factor_guards_nonpositive():
    assert dadj._directional_factor(0.0, "merge") == 1.0


def test_load_split_events_inverts_merge_factor():
    """011930 실사례(2026-05-15 1:10 액면병합, 정지 동결가 3,995 → 재개 39,950).
    병합 전 원시가를 현재 스케일로 올리려면 계수는 0.1 이어야 한다(3,995/0.1=39,950)."""
    conn = _RawConn(raw_events=[
        ("011930", "split", date(2026, 5, 15),
         {"split_factor": 10, "direction": "merge"}),
    ])
    events = dadj.load_split_events(conn)
    assert events["011930"] == [(date(2026, 5, 15), 0.1)]


def test_merge_and_split_same_factor_produce_opposite_adjustment(monkeypatch):
    """같은 sf=10 이라도 방향이 다르면 adj_factor 가 반대로 나와야 한다 —
    이 대칭이 깨지면 병합 종목의 과거 시세가 100배(10**2) 틀어진다."""
    captured = []
    monkeypatch.setattr(
        dadj.psycopg2.extras, "execute_batch",
        lambda cur, sql, rows, page_size=1000: captured.append(list(rows)))

    conn_split = _RawConn(
        raw_events=[("AAA", "split", date(2026, 5, 15),
                     {"split_factor": 10, "direction": "split"})],
        stock_dates_rows=[("AAA", "2026-05-01")])
    dadj.update_adj_factors(conn_split)
    assert captured[-1] == [(10.0, "AAA", "2026-05-01")]

    conn_merge = _RawConn(
        raw_events=[("AAA", "split", date(2026, 5, 15),
                     {"split_factor": 10, "direction": "merge"})],
        stock_dates_rows=[("AAA", "2026-05-01")])
    dadj.update_adj_factors(conn_merge)
    assert captured[-1] == [(0.1, "AAA", "2026-05-01")]


def test_update_adj_factors_returns_zero_and_untouched_when_no_events(monkeypatch):
    """R4: 이벤트가 아예 없는 종목은 손대지 않는다(조기 반환, DB 쓰기 없음)."""
    captured = []
    monkeypatch.setattr(
        dadj.psycopg2.extras, "execute_batch",
        lambda cur, sql, rows, page_size=1000: captured.append(rows))
    conn = _RawConn(raw_events=[], stock_dates_rows=[("OTHER", "2024-01-01")])
    n = dadj.update_adj_factors(conn)
    assert n == 0
    assert captured == []

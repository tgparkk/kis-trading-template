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


# ── R3: 캘린더 간격 가드 (거래정지 허용, 장기결측 거부) ─────────────────────────

def test_first_clean_gap_accepts_001130_real_halt_across_weekend():
    """실제 001130 사례(2026-07-06 라이브 DB 조회값): 4일 거래정지(거래량0, 종가동결)
    후 금(05-15)→월(05-18) 재개 시 종가 156500→14300 (ratio~10.94→11). 캘린더 간격
    3일(주말 포함)은 정상 거래재개 패턴이므로 반드시 허용돼야 한다(회귀 방지)."""
    prices = [
        ("2026-05-08", 156500.0),
        ("2026-05-11", 156500.0),
        ("2026-05-12", 156500.0),
        ("2026-05-13", 156500.0),
        ("2026-05-14", 156500.0),
        ("2026-05-15", 156500.0),   # 거래정지 마지막 날(금)
        ("2026-05-18", 14300.0),    # 재개(월) — 진짜 갭
        ("2026-05-19", 13410.0),
        ("2026-05-20", 12830.0),
    ]
    assert sfi._first_clean_gap(prices) == ("2026-05-18", 11)


def test_first_clean_gap_rejects_multiweek_hole():
    """비율은 그럴듯해도(2.0) 캘린더 간격이 19일이면 거래정지가 아니라 장기 데이터
    결측/미상장 구간일 가능성이 높다 — 분할 갭으로 오인해선 안 된다."""
    prices = [("2026-01-01", 100.0), ("2026-01-20", 50.0)]
    assert sfi._first_clean_gap(prices) is None


def test_first_clean_gap_skips_rejected_hole_then_finds_valid_gap():
    """장기 결측 쌍은 거부하고 계속 스캔해 이후의 진짜(간격 정상) 갭을 찾아야 한다."""
    prices = [
        ("2026-01-01", 100.0),
        ("2026-01-25", 50.0),   # 24일 간격, ratio 2.0 — 거부(계속 스캔)
        ("2026-01-26", 50.0),   # ratio 1.0 — 갭 아님
        ("2026-01-27", 25.0),   # 1일 간격, ratio 2.0 — 채택
    ]
    assert sfi._first_clean_gap(prices) == ("2026-01-27", 2)


# ── infer_and_stamp_split_factors (mock DB) ──────────────────────────────────

class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(sql.upper().split())
        if s.startswith("SELECT STOCK_CODE, EVENT_TYPE, EVENT_DATE FROM CORP_EVENTS"):
            # R5: 프로덕션 SQL 이 event_type='split' 만 조회하므로 목도 동일하게 필터링
            # (실제 DB WHERE 절을 충실히 모사 — bonus_issue 는 여기서 걸러진다).
            self._rows = [e for e in self.conn.events if e[1] == "split"]
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


def test_infer_stamps_factor_without_moving_event_date():
    """R1: event_date(PK, 공시일)는 절대 변경하지 않는다 — meta 병합만.

    PK 이동은 (a) 같은 슬롯 재수집 시 새 행이 다시 들어와 이중스탬프 위험,
    (b) 기존 pykrx 백필 105건과 PK 충돌 여지를 낳는 근본원인이었다(2026-07-06 code
    review). 유효 권리락일은 meta.effective_date 에만 기록한다.
    """
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
    meta_json, sc, etype, where_date = conn.updates[0]   # SET 절에 event_date 없음(4개 파라미터만)
    assert where_date == date(2026, 5, 1)     # WHERE 는 원 공시일 그대로(불변)
    assert sc == "005930" and etype == "split"
    import json
    patch = json.loads(meta_json)
    assert patch["split_factor"] == 2
    assert patch["effective_date"] == "2026-05-21"   # 유효 권리락일은 meta 에만 기록
    assert patch["split_factor_inferred"] is True
    assert conn.committed == 1


def test_infer_001130_real_case_stamps_11_event_date_preserved():
    """001130 실사례 end-to-end 회귀(2026-07-06 code review 하드닝) — 원 공시일
    (rcept_dt=2026-03-12)에서 출발해 +90일 창 안의 진짜 halt 갭(05-15→05-18, 실측
    156500→14300)을 찾아 factor 11 을 스탬프하되, event_date(PK)는 공시일 그대로
    보존해야 한다(이 회귀가 code review 에서 지적된 원인 — 과거엔 PK를 05-18 로
    이동시켰음)."""
    conn = _Conn(
        events=[("001130", "split", date(2026, 3, 12))],  # 실제 DART rcept_dt
        prices={
            "001130": [
                ("2026-03-12", 156500.0),
                ("2026-04-15", 156500.0),
                ("2026-05-08", 156500.0),
                ("2026-05-11", 156500.0),
                ("2026-05-12", 156500.0),
                ("2026-05-13", 156500.0),
                ("2026-05-14", 156500.0),
                ("2026-05-15", 156500.0),   # 거래정지 마지막 날(금)
                ("2026-05-18", 14300.0),    # 재개(월) — 실측 갭
                ("2026-05-19", 13410.0),
                ("2026-05-20", 12830.0),
            ]
        },
    )
    n = sfi.infer_and_stamp_split_factors(conn)
    assert n == 1
    meta_json, sc, etype, where_date = conn.updates[0]
    assert where_date == date(2026, 3, 12)   # PK 불변 — 공시일 그대로
    assert sc == "001130" and etype == "split"
    import json
    patch = json.loads(meta_json)
    assert patch["split_factor"] == 11
    assert patch["effective_date"] == "2026-05-18"


def test_infer_skips_when_no_gap_yet_idempotent():
    """권리락 전(갭 없음) → 스탬프 안 함, 재실행해도 동일(멱등)."""
    conn = _Conn(
        events=[("000660", "split", date(2026, 5, 1))],
        prices={"000660": [("2026-05-01", 100.0), ("2026-05-02", 99.0)]},
    )
    assert sfi.infer_and_stamp_split_factors(conn) == 0
    assert conn.updates == []
    # 재실행도 0
    assert sfi.infer_and_stamp_split_factors(conn) == 0


def test_infer_scopes_to_split_only_bonus_issue_excluded():
    """R5: bonus_issue 는 더 이상 스탬프 대상이 아니다 — daily_adj 가 'split'만
    소비하므로 bonus_issue 를 추론·스탬프하는 것은 낭비(매일 밤 불필요한 UPDATE)이자
    실제로 쓰이지 않는 조용한 divergence 였다(2026-07-06 code review). corp_events
    캡처(Item 2)는 유지하되 가격조정 스탬프만 하지 않는다 — bonus_issue 가격조정은
    의도적인 후속 과제."""
    conn = _Conn(
        events=[
            ("005930", "split", date(2026, 5, 1)),
            ("012345", "bonus_issue", date(2026, 3, 10)),
        ],
        prices={
            "005930": [("2026-05-01", 100.0), ("2026-05-20", 100.0), ("2026-05-21", 50.0)],
            "012345": [("2026-03-10", 300.0), ("2026-03-12", 100.0)],  # 3:1 갭 있어도 무시돼야 함
        },
    )
    n = sfi.infer_and_stamp_split_factors(conn)
    assert n == 1   # split만 스탬프
    stamped_codes = {u[1] for u in conn.updates}   # (meta_json, sc, etype, event_date)
    assert stamped_codes == {"005930"}

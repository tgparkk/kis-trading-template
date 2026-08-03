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
    assert sfi._first_clean_gap(prices) == ("2026-05-07", 2.0, "split")


def test_first_clean_gap_detects_5for1():
    prices = [("2026-05-04", 500.0), ("2026-05-07", 100.0)]
    assert sfi._first_clean_gap(prices) == ("2026-05-07", 5.0, "split")


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
    assert sfi._first_clean_gap(prices) == ("2026-05-06", 3.0, "split")


# ── 2026-08-03: 액면병합(역방향) 탐지 ────────────────────────────────────────

def test_first_clean_gap_detects_merge_011930_real_case():
    """011930 실사례(2026-05-15 1:10 액면병합). 정지 중 종가가 3,995 로 동결됐다가
    재개일 39,950 — 옛 코드는 c_prev/c_cur(=0.1)만 봐서 이 갭을 통째로 흘렸다."""
    prices = [
        ("2026-05-13", 3995.0),
        ("2026-05-14", 3995.0),   # 거래정지 마지막 날
        ("2026-05-15", 39950.0),  # 재개 — 실측 갭
        ("2026-05-18", 32800.0),
    ]
    assert sfi._first_clean_gap(prices) == ("2026-05-15", 10.0, "merge")


def test_first_clean_gap_detects_merge_1for2():
    prices = [("2026-05-04", 1000.0), ("2026-05-07", 2000.0)]
    assert sfi._first_clean_gap(prices) == ("2026-05-07", 2.0, "merge")


def test_first_clean_gap_rejects_limit_up_contaminated_merge_115160():
    """🔑 115160 실사례(2026-04-30 1:10 병합): 재개일이 +30% 상한에 붙어
    9,370/721 = 12.996 이 된다. round=13 이고 오차가 0.004 라 '정수 근처' 기준은
    tol 을 0.01 로 조여도 뚫린다 — 그래서 배수 13 이라는 **틀린 값**을 조용히 스탬프한다.
    액면가 비율 화이트리스트는 12.996 이 10 에서 30% 벗어났다고 보고 거부해야 한다.

    (정답지 105건 실측: 정수근처 대칭확장 TP=6/FP=6, 화이트리스트 TP=4/FP=0)"""
    prices = [("2026-04-29", 721.0), ("2026-04-30", 9370.0)]
    assert sfi._first_clean_gap(prices) is None


def test_first_clean_gap_rejects_limit_up_contaminated_merge_039980():
    """039980(2026-04-29 1:5 병합) 재개일 +30% 상한 → 9,630/1,481 = 6.502.
    5 도 7 도 아니므로 거부돼야 한다."""
    prices = [("2026-04-28", 1481.0), ("2026-04-29", 9630.0)]
    assert sfi._first_clean_gap(prices) is None


def test_first_clean_gap_rejects_single_day_limit_moves_both_ways():
    """급락 구분 1 — KRX 일일 제한이 ±30% 라 정상 하루 등락은 비율이 최대 1/0.7=1.43.
    _RATIO_MIN=1.5 에 못 미쳐 양방향 모두 걸러진다."""
    assert sfi._first_clean_gap([("2026-05-04", 100.0), ("2026-05-07", 70.0)]) is None   # 하한
    assert sfi._first_clean_gap([("2026-05-04", 100.0), ("2026-05-07", 130.0)]) is None  # 상한


def test_first_clean_gap_does_not_compound_consecutive_limit_days():
    """급락 구분 2 — 연속 하한가는 *인접 쌍끼리만* 비교되므로 누적되지 않는다.
    100→70→49 는 각 쌍이 1.4286 이라 둘 다 거부된다(1.5 미만)."""
    prices = [("2026-05-04", 100.0), ("2026-05-07", 70.0), ("2026-05-08", 49.0)]
    assert sfi._first_clean_gap(prices) is None


def test_first_clean_gap_accepts_single_bar_move_too_large_for_price_limits():
    """한 봉 만에 -50% 는 가격제한 아래선 불가능하다 — 정지 해제(기업행위)의 지문이다.
    따라서 채택되는 것이 맞다.

    ⚠️ 잔여 위험: 정리매매는 가격제한이 없어 하루 -80% 가 가능하고, 그 값이 우연히
    액면비율(5.0)에 3% 이내로 붙으면 오탐이 된다. 현재는 스캔 모집단이
    'corp_events 에 분할·병합 공시가 있는 종목의 공시일 +90일' 로 제한돼 있어
    (=_load_events_needing_factor) 상장폐지만 진행 중인 종목은 스캔되지 않는다는
    점이 완화책이다. 거래량 0(정지) 런을 추가 조건으로 요구하면 더 강해지지만
    이번 범위에서는 넣지 않았다."""
    prices = [("2026-05-04", 100.0), ("2026-05-07", 50.0)]
    assert sfi._first_clean_gap(prices) == ("2026-05-07", 2.0, "split")


def test_snap_to_face_ratio_boundary_is_relative_not_absolute():
    """상대오차 3% 경계 — 절대오차(정수근처)와 달리 큰 배수에서도 같은 비율로 조인다."""
    assert sfi._snap_to_face_ratio(10.0) == 10.0
    assert sfi._snap_to_face_ratio(10.29) == 10.0    # 2.9% → 채택
    assert sfi._snap_to_face_ratio(10.4) is None     # 4.0% → 거부
    assert sfi._snap_to_face_ratio(12.996) is None   # 115160 오염값
    assert sfi._snap_to_face_ratio(1.2) is None      # _RATIO_MIN 미만


# ── R3: 캘린더 간격 가드 (거래정지 허용, 장기결측 거부) ─────────────────────────

def test_first_clean_gap_allows_weekend_halt_gap():
    """캘린더 간격 가드 회귀 — 금→월(3일, 주말 포함) 재개는 반드시 허용돼야 한다.
    (원래 001130 케이스가 지키던 성질. 배수 판정과 분리해 깨끗한 비율로 검증한다.)"""
    prices = [
        ("2026-05-14", 100000.0),
        ("2026-05-15", 100000.0),   # 거래정지 마지막 날(금)
        ("2026-05-18", 10000.0),    # 재개(월) — 3일 간격, 정확히 10배
    ]
    assert sfi._first_clean_gap(prices) == ("2026-05-18", 10.0, "split")


def test_first_clean_gap_refuses_001130_because_ratio_is_not_a_face_value_ratio():
    """🔴 001130 은 이 추론기의 **생애 유일한 스탬프**였고, 그 값이 틀렸다.

    실측(kis_template): 정지 중 156,500 동결 → 재개일(2026-05-18) 시가 15,400 / 종가 14,300.
    DART report_nm='주식분할결정'. 10:1 분할이면 기준가는 15,650 이고 시가 15,400 은
    거기서 -1.6% 다 — 즉 **진짜 배수는 10**이다. 그런데 옛 규칙은 종가로 재서
    156,500/14,300 = 10.94 → round=11, |오차|=0.06 < 0.3 → **11 을 스탬프했다**.
    그 값이 지금도 corp_events.meta.split_factor=11 로 남아 있다.

    재개봉은 기준가에서 자유롭게 움직이므로(그날 종가는 기준가 대비 -8.6%) 종가비는
    배수의 신뢰할 수 있는 추정치가 아니다. 화이트리스트는 10.94 가 10 에서 9.4%
    벗어났다고 보고 **스탬프를 거부**한다 — 틀린 배수를 남기는 것보다 낫다.
    (기존 DB 행은 이 변경으로 바뀌지 않는다: split_factor 가 이미 있으면 재추론 대상이 아니다.)
    """
    prices = [
        ("2026-05-14", 156500.0),
        ("2026-05-15", 156500.0),   # 거래정지 마지막 날(금)
        ("2026-05-18", 14300.0),    # 재개(월) — 종가는 기준가 대비 -8.6%
    ]
    assert sfi._first_clean_gap(prices) is None


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
    assert sfi._first_clean_gap(prices) == ("2026-01-27", 2.0, "split")


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
    assert patch["direction"] == "split"
    assert conn.committed == 1


def test_infer_merge_stamps_direction_and_preserves_event_date():
    """액면병합 end-to-end — event_date(PK, 공시일)는 불변이고 meta 에
    direction='merge' 가 반드시 실려야 한다. 이 필드가 없으면 daily_adj 가 정방향으로
    오해석해 과거 시세를 sf**2 만큼 반대로 틀어 버린다."""
    conn = _Conn(
        events=[("011930", "split", date(2026, 2, 20))],  # 실제 DART rcept_dt
        prices={
            "011930": [
                ("2026-02-20", 3995.0),
                ("2026-05-13", 3995.0),
                ("2026-05-14", 3995.0),   # 거래정지 마지막 날
                ("2026-05-15", 39950.0),  # 재개 — 실측 1:10 병합 갭
                ("2026-05-18", 32800.0),
            ]
        },
    )
    n = sfi.infer_and_stamp_split_factors(conn)
    assert n == 1
    meta_json, sc, etype, where_date = conn.updates[0]
    assert where_date == date(2026, 2, 20)   # PK 불변 — 공시일 그대로
    assert sc == "011930" and etype == "split"
    import json
    patch = json.loads(meta_json)
    assert patch["split_factor"] == 10.0
    assert patch["direction"] == "merge"
    assert patch["effective_date"] == "2026-05-15"


def test_infer_001130_no_longer_stamps_wrong_factor_11():
    """회귀 방지 — 옛 규칙이 유일하게 남긴 스탬프가 틀린 값(11)이었다.
    이제는 스탬프하지 않는다(근거는 _first_clean_gap 쪽 테스트 주석)."""
    conn = _Conn(
        events=[("001130", "split", date(2026, 3, 12))],
        prices={
            "001130": [
                ("2026-03-12", 156500.0),
                ("2026-05-14", 156500.0),
                ("2026-05-15", 156500.0),
                ("2026-05-18", 14300.0),
                ("2026-05-19", 13410.0),
            ]
        },
    )
    assert sfi.infer_and_stamp_split_factors(conn) == 0
    assert conn.updates == []


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

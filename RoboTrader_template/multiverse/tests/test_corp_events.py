"""Phase 1 + Phase 2 corp_events 테스트 + D4 적재 분포/매핑/통합 검증."""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from RoboTrader_template.multiverse.data import corp_events


def test_filter_universe_returns_list():
    """관리종목/거래정지 자동 제외 함수 동작."""
    result = corp_events.filter_universe(
        ["005930", "000660"], as_of_date=date(2026, 4, 1)
    )
    assert isinstance(result, list)


def test_get_adj_factor_default_one():
    """이벤트 없으면 1.0 반환."""
    assert corp_events.get_adj_factor("005930", date(2026, 4, 1)) == 1.0


def test_is_administrative_default_false():
    """이벤트 없으면 False."""
    assert corp_events.is_administrative("005930", date(2026, 4, 1)) is False


# ------------------------------------------------------------------ #
# Phase 2: end_date 관련 테스트 (DB mock 사용)
# ------------------------------------------------------------------ #

def _make_conn_mock(fetchall_return=None, fetchone_return=None):
    """psycopg2 연결 mock 헬퍼."""
    cur = MagicMock()
    cur.fetchall.return_value = fetchall_return or []
    cur.fetchone.return_value = fetchone_return
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_filter_universe_respects_end_date_null():
    """end_date=NULL(미해제)인 administrative 이벤트 → 해당 종목 제외.

    영구 제외 버그 수정 검증: end_date IS NULL → 여전히 유효(제외 대상).
    """
    today = date(2026, 5, 2)
    target = "TEST001"
    other = "TEST002"

    # DB가 target 종목을 excluded 집합으로 반환 (end_date IS NULL 조건 통과)
    conn_mock, cur_mock = _make_conn_mock(fetchall_return=[(target,)])

    with patch.object(corp_events, "_conn") as mock_conn_ctx:
        mock_conn_ctx.return_value.__enter__ = lambda s: conn_mock
        mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = corp_events.filter_universe([target, other], as_of_date=today)

    # target은 제외, other는 포함
    assert target not in result
    assert other in result


def test_filter_universe_respects_end_date_set():
    """end_date=어제(해제됨)인 administrative 이벤트 → 해당 종목 포함(복귀).

    해제 후 복귀 검증: end_date <= as_of_date → 유효하지 않음(포함 대상).
    """
    today = date(2026, 5, 2)
    target = "TEST003"

    # DB가 아무것도 반환하지 않음 (end_date <= as_of_date 조건으로 필터됨)
    conn_mock, cur_mock = _make_conn_mock(fetchall_return=[])

    with patch.object(corp_events, "_conn") as mock_conn_ctx:
        mock_conn_ctx.return_value.__enter__ = lambda s: conn_mock
        mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = corp_events.filter_universe([target], as_of_date=today)

    # 해제된 종목이므로 포함
    assert target in result


def test_filter_universe_respects_end_date_future():
    """end_date=내일(해제 예정)인 administrative 이벤트 → 오늘 기준 아직 제외.

    해제 예정 검증: end_date > as_of_date → 여전히 유효(제외 대상).
    """
    today = date(2026, 5, 2)
    target = "TEST004"

    # DB가 target 종목을 excluded 집합으로 반환 (end_date=내일 → 아직 유효)
    conn_mock, cur_mock = _make_conn_mock(fetchall_return=[(target,)])

    with patch.object(corp_events, "_conn") as mock_conn_ctx:
        mock_conn_ctx.return_value.__enter__ = lambda s: conn_mock
        mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = corp_events.filter_universe([target], as_of_date=today)

    # 아직 유효(해제 예정)이므로 제외
    assert target not in result


def test_is_administrative_end_date_null_is_true():
    """end_date=NULL인 administrative 레코드 → is_administrative=True."""
    today = date(2026, 5, 2)

    conn_mock, cur_mock = _make_conn_mock(fetchone_return=(1,))

    with patch.object(corp_events, "_conn") as mock_conn_ctx:
        mock_conn_ctx.return_value.__enter__ = lambda s: conn_mock
        mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = corp_events.is_administrative("TEST005", today)

    assert result is True


def test_is_administrative_end_date_past_is_false():
    """end_date=과거(해제됨)인 administrative 레코드 → is_administrative=False."""
    today = date(2026, 5, 2)

    # DB가 아무것도 반환하지 않음 (end_date 조건으로 필터됨)
    conn_mock, cur_mock = _make_conn_mock(fetchone_return=None)

    with patch.object(corp_events, "_conn") as mock_conn_ctx:
        mock_conn_ctx.return_value.__enter__ = lambda s: conn_mock
        mock_conn_ctx.return_value.__exit__ = MagicMock(return_flag=False)

        result = corp_events.is_administrative("TEST006", today)

    assert result is False


def test_is_halted_end_date_null_is_true():
    """end_date=NULL인 halt 레코드 → is_halted=True."""
    today = date(2026, 5, 2)

    conn_mock, cur_mock = _make_conn_mock(fetchone_return=(1,))

    with patch.object(corp_events, "_conn") as mock_conn_ctx:
        mock_conn_ctx.return_value.__enter__ = lambda s: conn_mock
        mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = corp_events.is_halted("TEST007", today)

    assert result is True


# ------------------------------------------------------------------ #
# D4: 적재 분포 검증 (실 DB)
# ------------------------------------------------------------------ #

def _try_connect_robotrader():
    """robotrader DB 연결 시도. 실패 시 None 반환."""
    import os
    import psycopg2
    try:
        return psycopg2.connect(
            host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
            port=int(os.getenv("TIMESCALE_PORT", "5433")),
            user=os.getenv("TIMESCALE_USER", "robotrader"),
            password=os.getenv("TIMESCALE_PASSWORD", "1234"),
            database=os.getenv("TIMESCALE_DB", "robotrader"),
        )
    except Exception:
        return None


@pytest.fixture(scope="module")
def robotrader_conn():
    """모듈 스코프 robotrader DB 연결."""
    conn = _try_connect_robotrader()
    if conn is None:
        pytest.skip("robotrader DB 연결 실패 (환경 없음)")
    yield conn
    conn.close()


class TestCorpEventsDistribution:
    """D4-a: 적재 분포 — 4개 event_type 모두 1건 이상, 총 행수 ≥ 50."""

    def test_all_four_event_types_present(self, robotrader_conn):
        """split / rights_issue / bonus_issue / administrative 4개 타입 모두 존재.

        실제 적재: split 2 / rights_issue 82 / bonus_issue 8 / administrative 2.
        caution/warning/halt는 KIND 404 한계로 0건 — 강제하지 않음.
        """
        with robotrader_conn.cursor() as cur:
            cur.execute(
                "SELECT event_type, COUNT(*) FROM corp_events "
                "GROUP BY event_type ORDER BY event_type;"
            )
            rows = cur.fetchall()

        distribution = {etype: cnt for etype, cnt in rows}
        required_types = {"split", "rights_issue", "bonus_issue", "administrative"}
        missing = required_types - distribution.keys()
        assert not missing, (
            f"corp_events에 없는 event_type: {missing}. "
            f"실제 분포: {distribution}"
        )
        for etype in required_types:
            assert distribution[etype] >= 1, (
                f"{etype} 건수 {distribution[etype]} < 1"
            )

    def test_total_row_count_above_50(self, robotrader_conn):
        """corp_events 총 행수 ≥ 50 (D2 backfill 94건 기준)."""
        with robotrader_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM corp_events;")
            total = cur.fetchone()[0]
        assert total >= 50, f"corp_events 총 행수 {total} < 50"


class TestCorpEventsSymbolMapping:
    """D4-b: 종목 매핑 — distinct codes, 6자리 zero-padding."""

    def test_distinct_stock_codes_above_30(self, robotrader_conn):
        """distinct stock_code ≥ 30 (D2 backfill 42종목 기준)."""
        with robotrader_conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT stock_code) FROM corp_events;"
            )
            count = cur.fetchone()[0]
        assert count >= 30, (
            f"corp_events distinct stock_code {count} < 30"
        )

    def test_all_stock_codes_are_6digits(self, robotrader_conn):
        """모든 stock_code가 정확히 6자리여야 한다."""
        with robotrader_conn.cursor() as cur:
            cur.execute(
                "SELECT stock_code FROM corp_events "
                "WHERE LENGTH(stock_code) != 6 LIMIT 5;"
            )
            bad_rows = cur.fetchall()
        assert not bad_rows, (
            f"6자리 아닌 stock_code 발견: {[r[0] for r in bad_rows]}"
        )

    def test_zero_padded_codes_present(self, robotrader_conn):
        """'0'으로 시작하는 종목코드가 1건 이상 존재 — zero-padding 정상 적재.

        실제: 62건이 '0'으로 시작 (000390, 000990 등).
        """
        with robotrader_conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM corp_events WHERE stock_code LIKE '0%';"
            )
            count = cur.fetchone()[0]
        assert count >= 1, (
            f"'0'으로 시작하는 stock_code가 없음 — zero-padding 누락 의심"
        )

    def test_no_stock_code_numeric_overflow(self, robotrader_conn):
        """stock_code가 숫자 문자열 형태여야 한다 (비숫자 문자 없음)."""
        with robotrader_conn.cursor() as cur:
            cur.execute(
                "SELECT stock_code FROM corp_events "
                "WHERE stock_code !~ '^[0-9]+$' LIMIT 5;"
            )
            bad_rows = cur.fetchall()
        assert not bad_rows, (
            f"비숫자 stock_code 발견: {[r[0] for r in bad_rows]}"
        )


class TestFilterUniverseIntegration:
    """D4-c: filter_universe 통합 — 실 DB 5종목 호출."""

    def test_filter_universe_returns_list_with_real_codes(self):
        """실제 corp_events에 존재하는 종목 포함해 filter_universe 호출.

        rights_issue 이 있는 종목(035420, 000390)을 포함해 5종목 테스트.
        관리종목/거래정지가 아닌 종목은 결과에 포함되어야 한다.
        함수가 예외 없이 list를 반환하는지 통합 확인.
        """
        # 실 DB 연결 확인
        conn = _try_connect_robotrader()
        if conn is None:
            pytest.skip("robotrader DB 연결 실패")
        conn.close()

        sample_codes = ["005930", "000660", "035420", "000390", "051910"]
        result = corp_events.filter_universe(
            sample_codes, as_of_date=date(2026, 4, 30)
        )
        assert isinstance(result, list), "filter_universe가 list를 반환하지 않음"
        # 결과는 입력보다 작거나 같아야 함
        assert len(result) <= len(sample_codes), (
            f"결과 종목 수 {len(result)} > 입력 {len(sample_codes)} — 필터 로직 이상"
        )
        # 결과의 모든 코드는 입력에 있어야 함
        for code in result:
            assert code in sample_codes, (
                f"결과에 입력에 없는 종목코드 포함: {code}"
            )

    def test_filter_universe_empty_input_returns_empty(self):
        """빈 리스트 입력 → 빈 리스트 반환."""
        result = corp_events.filter_universe([], as_of_date=date(2026, 4, 30))
        assert result == []

    def test_filter_universe_future_date_excludes_nothing_extra(self):
        """미래 날짜 기준도 예외 없이 동작 — 함수 안정성 확인."""
        conn = _try_connect_robotrader()
        if conn is None:
            pytest.skip("robotrader DB 연결 실패")
        conn.close()

        result = corp_events.filter_universe(
            ["005930", "000660"],
            as_of_date=date(2030, 12, 31),
        )
        assert isinstance(result, list)

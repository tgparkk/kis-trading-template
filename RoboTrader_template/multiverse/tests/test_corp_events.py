"""Phase 1 + Phase 2 corp_events 테스트."""
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
        mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

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

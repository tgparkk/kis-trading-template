"""Phase 1 corp_events 테스트."""
import pytest
from datetime import date
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

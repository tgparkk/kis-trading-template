# tests/test_screener_universe.py
"""스크리너-정합 백테스트 유니버스 로더 테스트.

가짜 reader(get_universe_snapshot)를 주입해 DB 없이, 로더가 어댑터 base_filter 를
적용한 종목코드만 반환함을 단언한다.
"""
from backtest.screener_universe import (
    load_screener_universe,
    load_screener_universe_range,
)


class FakeReader:
    """get_universe_snapshot(scan_date) 만 제공하는 최소 reader 스텁."""

    def __init__(self, snapshot, trading_dates=None):
        self._snapshot = snapshot
        self._trading_dates = trading_dates
        self.calls = []

    def get_universe_snapshot(self, scan_date):
        self.calls.append(scan_date)
        return list(self._snapshot)

    def get_trading_dates(self, start, end):
        return list(self._trading_dates or [])


def _mixed_snapshot():
    """시총·거래대금이 섞인 스냅샷(라이브 get_universe_snapshot 형태)."""
    return [
        # 소형(<5천억) + 거래대금 충족 → 통과
        {"stock_code": "SMALL", "market_cap": 3e11, "trading_value": 2e9},
        # 대형(>=5천억) → max_market_cap 위반, 제외
        {"stock_code": "BIG", "market_cap": 1e12, "trading_value": 5e9},
        # 거래대금 미달(<10억) → 제외
        {"stock_code": "THIN", "market_cap": 2e11, "trading_value": 1e8},
        # 시총 미상(0) → fail-closed 제외(상한 컷을 우회하던 회귀 방지)
        {"stock_code": "UNK", "market_cap": 0, "trading_value": 3e9},
    ]


def test_load_returns_only_base_filter_passers():
    """daytrading_3methods_breakout: 5천억·10억 필터 통과 종목만 반환(시총 미상 제외)."""
    reader = FakeReader(_mixed_snapshot())
    codes = load_screener_universe(
        "daytrading_3methods_breakout", "2026-06-24", reader=reader
    )
    assert set(codes) == {"SMALL"}
    assert "BIG" not in codes      # 대형 시총 위반 제외
    assert "THIN" not in codes     # 거래대금 미달 제외
    assert "UNK" not in codes      # 시총 미상(0) → fail-closed 제외
    assert reader.calls == ["2026-06-24"]


def test_market_cap_unknown_excluded_fail_closed():
    """시총 0(미상)이면 거래대금이 충족돼도 fail-closed 제외(컨셉 검증 불가)."""
    reader = FakeReader([
        {"stock_code": "UNK", "market_cap": 0, "trading_value": 3e9},
    ])
    codes = load_screener_universe(
        "daytrading_3methods_breakout", "2026-06-24", reader=reader
    )
    assert codes == []


def test_empty_snapshot_returns_empty(caplog):
    """스냅샷 빈 경우 빈 리스트 + 경고."""
    import logging

    reader = FakeReader([])
    with caplog.at_level(logging.WARNING):
        codes = load_screener_universe(
            "daytrading_3methods_breakout", "2026-06-24", reader=reader
        )
    assert codes == []
    assert any("스냅샷" in r.message for r in caplog.records)


def test_unknown_strategy_returns_empty(caplog):
    """알 수 없는 전략 → 어댑터 없음 → 빈 리스트 + 경고."""
    import logging

    reader = FakeReader(_mixed_snapshot())
    with caplog.at_level(logging.WARNING):
        codes = load_screener_universe("__no_such_strategy__", "2026-06-24", reader=reader)
    assert codes == []
    assert any("어댑터" in r.message for r in caplog.records)


def test_range_wrapper_maps_dates_to_universes():
    """range 로더: 거래일별 유니버스 dict 반환(thin wrapper)."""
    reader = FakeReader(_mixed_snapshot(), trading_dates=["2026-06-23", "2026-06-24"])
    result = load_screener_universe_range(
        "daytrading_3methods_breakout", "2026-06-23", "2026-06-24", reader=reader
    )
    assert set(result.keys()) == {"2026-06-23", "2026-06-24"}
    for codes in result.values():
        assert set(codes) == {"SMALL"}

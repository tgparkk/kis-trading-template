# tests/test_data_completeness.py
"""백테스트 데이터완전성 가드(market_cap 채움률) 테스트.

가짜 reader(get_universe_snapshot)를 주입해 DB 없이, 측정 구간 snapshot 의
market_cap 채움률을 점검하고 임계 미만이면 실패/경고함을 단언한다.
"""
import logging

import pytest

from backtest.data_completeness import (
    DataCompletenessError,
    assert_market_cap_coverage,
    market_cap_coverage,
)


class _FakeReader:
    """get_universe_snapshot(scan_date) 만 제공. 날짜별 snapshot 주입."""

    def __init__(self, snapshots):
        self._snapshots = snapshots          # {date_str: [snapshot dict...]}
        self.calls = []

    def get_universe_snapshot(self, scan_date):
        key = scan_date if isinstance(scan_date, str) else scan_date.strftime("%Y-%m-%d")
        self.calls.append(key)
        return list(self._snapshots.get(key, []))


def _snap(filled, missing):
    """filled 개는 market_cap>0, missing 개는 market_cap=0(=COALESCE 결측)."""
    rows = [{"stock_code": f"F{i}", "market_cap": 3e11, "trading_value": 2e9}
            for i in range(filled)]
    rows += [{"stock_code": f"M{i}", "market_cap": 0, "trading_value": 2e9}
             for i in range(missing)]
    return rows


def test_coverage_full_is_ok():
    reader = _FakeReader({"2025-01-31": _snap(100, 0), "2025-02-28": _snap(98, 2)})
    rep = market_cap_coverage(reader, ["2025-01-31", "2025-02-28"], min_coverage=0.8)
    assert rep.total_rows == 200
    assert rep.filled_rows == 198
    assert rep.coverage == pytest.approx(0.99)
    assert rep.ok is True


def test_coverage_low_is_not_ok():
    """2021–23 처럼 결측 지배 → ok False."""
    reader = _FakeReader({"2022-06-30": _snap(0, 100), "2022-07-29": _snap(1, 99)})
    rep = market_cap_coverage(reader, ["2022-06-30", "2022-07-29"], min_coverage=0.8)
    assert rep.coverage == pytest.approx(0.005)
    assert rep.ok is False
    assert rep.per_date["2022-06-30"] == pytest.approx(0.0)


def test_empty_snapshots_not_ok():
    reader = _FakeReader({})
    rep = market_cap_coverage(reader, ["2022-01-31"], min_coverage=0.8)
    assert rep.total_rows == 0
    assert rep.ok is False


def test_assert_strict_raises_below_threshold():
    reader = _FakeReader({"2022-06-30": _snap(0, 100)})
    with pytest.raises(DataCompletenessError):
        assert_market_cap_coverage(reader, ["2022-06-30"], min_coverage=0.8, strict=True)


def test_assert_warn_only_does_not_raise(caplog):
    reader = _FakeReader({"2022-06-30": _snap(0, 100)})
    with caplog.at_level(logging.WARNING):
        rep = assert_market_cap_coverage(
            reader, ["2022-06-30"], min_coverage=0.8, strict=False
        )
    assert rep.ok is False
    assert any("market_cap" in r.message for r in caplog.records)


def test_assert_passes_silently_when_ok(caplog):
    reader = _FakeReader({"2025-01-31": _snap(100, 0)})
    with caplog.at_level(logging.WARNING):
        rep = assert_market_cap_coverage(
            reader, ["2025-01-31"], min_coverage=0.8, strict=True
        )
    assert rep.ok is True
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)

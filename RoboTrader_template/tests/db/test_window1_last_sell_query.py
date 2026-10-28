"""TradingRepository.get_last_sell_within_trading_days (10-29 창구 A ⑤ · 읽기 전용 SELECT).

- 거래일 = daily_prices 의 KOSPI 행 날짜(오늘 이전 N개).
- 페이퍼 = virtual_trading_records(is_test=true · source=kis_template) · 실전 = 인스턴스 표.
- 기존 커넥션 풀(_get_connection) 재사용 — 새 풀 0.
"""
from contextlib import contextmanager
from datetime import date, datetime

import pytest


class _Cur:
    def __init__(self, results):
        self._results = list(results)
        self.executed = []
        self._last = None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._last = self._results.pop(0)

    def fetchall(self):
        return self._last

    def fetchone(self):
        return self._last[0] if self._last else None

    def close(self):
        pass


def _repo(results, real_table="real_trading_records"):
    from db.repositories.trading import TradingRepository
    repo = TradingRepository.__new__(TradingRepository)
    from utils.logger import setup_logger
    repo.logger = setup_logger("test_window1_last_sell")
    repo._real_table = real_table
    cur = _Cur(results)

    class _Conn:
        def cursor(self):
            return cur

    @contextmanager
    def _gc():
        yield _Conn()
    repo._get_connection = _gc
    return repo, cur


DATES = [(date(2026, 10, 29),), (date(2026, 10, 28),), (date(2026, 10, 27),),
         (date(2026, 10, 26),), (date(2026, 10, 23),)]


def test_virtual_query_returns_last_sell_and_trading_dates():
    sell_row = ("rs_leader", "목표 익절 도달 (10.00% >= 10.00%)", datetime(2026, 10, 28, 10, 5), 4150, 40000)
    repo, cur = _repo([DATES, [sell_row]])
    out = repo.get_last_sell_within_trading_days("458350", date(2026, 10, 30), 5, is_virtual=True)
    assert out["strategy"] == "rs_leader"
    assert out["timestamp"] == datetime(2026, 10, 28, 10, 5)
    assert out["price"] == 4150.0 and out["profit_loss"] == 40000.0
    assert out["trading_dates"] == [d[0] for d in DATES]
    sql0, p0 = cur.executed[0]
    assert "daily_prices" in sql0 and "KOSPI" in sql0
    assert p0 == ("2026-10-30", 5)
    sql1, p1 = cur.executed[1]
    assert "virtual_trading_records" in sql1 and "is_test = true" in sql1 and "SELL" in sql1
    assert p1 == ("458350", "kis_template", "2026-10-23 00:00:00")


def test_real_query_uses_instance_table():
    sell_row = ("DayTrading3MethodsBreakoutStrategy", "실전매매", datetime(2026, 10, 29, 9, 20), 11970, -500)
    repo, cur = _repo([DATES, [sell_row]], real_table="real_trading_daytrading")
    out = repo.get_last_sell_within_trading_days("300080", date(2026, 10, 30), 5, is_virtual=False)
    assert out["reason"] == "실전매매"
    sql1, p1 = cur.executed[1]
    assert "real_trading_daytrading" in sql1 and "virtual_trading_records" not in sql1
    assert p1 == ("300080", "2026-10-23 00:00:00")


def test_no_sell_returns_none():
    repo, _ = _repo([DATES, []])
    assert repo.get_last_sell_within_trading_days("458350", date(2026, 10, 30), 5) is None


def test_no_trading_dates_returns_none_without_sell_query():
    repo, cur = _repo([[]])
    assert repo.get_last_sell_within_trading_days("458350", date(2026, 10, 30), 5) is None
    assert len(cur.executed) == 1


def test_exception_propagates_to_caller():
    """호출자(shadow 로그)가 1회 WARNING 으로 처리한다 — 여기서 삼키지 않는다."""
    from db.repositories.trading import TradingRepository
    repo = TradingRepository.__new__(TradingRepository)
    repo._real_table = "real_trading_records"

    @contextmanager
    def _boom():
        raise RuntimeError("pool down")
        yield  # pragma: no cover
    repo._get_connection = _boom
    with pytest.raises(RuntimeError):
        repo.get_last_sell_within_trading_days("458350", date(2026, 10, 30), 5)

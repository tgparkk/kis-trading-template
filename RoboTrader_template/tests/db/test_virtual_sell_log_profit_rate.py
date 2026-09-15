"""`가상 매도` 로그의 수익률 단위 — 분수를 퍼센트로 100배 해서 찍는다.

결함(2026-09-15 결정 패널 §F-5 ③ · §D-7 행번호 정정: 381 이 아니라 **383**):
`profit_rate` 는 `(price - buy_price) / buy_price` 즉 **분수**로 계산·저장되는데
(db/repositories/trading.py:367), 로그는 `{profit_rate:+.2f}%` 로 찍어
−3.35% 를 **−0.03%** 로 보여줬다. 두 자릿수 손실이 노이즈처럼 읽힌다.

이 파일이 단언하는 것:
  ① 분수 0.0306 → 로그에 `+3.06%`
  ② 저장되는 `profit_rate` 컬럼 값은 **분수 그대로**(표기만 고친다)
  ③ 손실 부호·`profit_loss` 원 표기는 불변

⚠️ DB 미접촉 — `_get_connection` 을 커서 스텁으로 갈아끼운다.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import Mock

import pytest

from db.repositories.trading import TradingRepository


class _Cursor:
    """buy_record_id 조회 → 매수단가, 중복매도 조회 → 없음."""

    def __init__(self, buy_price):
        self._buy_price = buy_price
        self._last = None
        self.inserted = None

    def execute(self, sql, params=None):
        self._last = (sql, params)
        if sql.strip().startswith("INSERT"):
            self.inserted = params

    def fetchone(self):
        sql = self._last[0]
        if "action = 'SELL'" in sql:
            return None  # 중복 매도 없음
        if "SELECT price FROM virtual_trading_records WHERE id" in sql:
            return (self._buy_price,)
        return None


def _repo(buy_price):
    repo = TradingRepository.__new__(TradingRepository)
    repo.logger = Mock()
    cursor = _Cursor(buy_price)

    conn = Mock()
    conn.cursor.return_value = cursor

    @contextmanager
    def _conn():
        yield conn

    repo._get_connection = _conn
    return repo, cursor


def _sell_line(repo):
    return [
        c.args[0]
        for c in repo.logger.info.call_args_list
        if c.args and isinstance(c.args[0], str) and c.args[0].startswith("가상 매도:")
    ]


@pytest.mark.parametrize(
    "buy_price,sell_price,expected_pct",
    [
        (10000.0, 10306.0, "+3.06%"),   # 분수 0.0306
        (10000.0, 9665.0, "-3.35%"),    # 분수 -0.0335 (09-14 실측 유형)
        (10000.0, 10000.0, "+0.00%"),
    ],
)
def test_profit_rate_printed_as_percent(buy_price, sell_price, expected_pct):
    repo, _ = _repo(buy_price)

    ok = repo.save_virtual_sell(
        stock_code="005930", stock_name="삼성전자", price=sell_price,
        quantity=10, strategy="daytrading_3methods_breakout", reason="손절",
        buy_record_id=1, timestamp=datetime(2026, 9, 15, 15, 0, 0),
    )

    assert ok is True
    lines = _sell_line(repo)
    assert len(lines) == 1, lines
    assert expected_pct in lines[0], lines[0]


def test_stored_column_stays_a_fraction():
    """표기만 고친다 — 컬럼에 들어가는 값은 분수 그대로여야 한다."""
    repo, cursor = _repo(10000.0)

    repo.save_virtual_sell(
        stock_code="005930", stock_name="삼성전자", price=10306.0,
        quantity=10, strategy="daytrading_3methods_breakout", reason="익절",
        buy_record_id=1, timestamp=datetime(2026, 9, 15, 15, 0, 0),
    )

    # INSERT 파라미터 순서: (code, name, qty, price, ts, strategy, reason,
    #                        profit_loss, profit_rate, buy_record_id, ...)
    assert cursor.inserted is not None
    profit_rate = cursor.inserted[8]
    assert profit_rate == pytest.approx(0.0306, abs=1e-9)
    profit_loss = cursor.inserted[7]
    assert profit_loss == pytest.approx(3060.0, abs=1e-6)

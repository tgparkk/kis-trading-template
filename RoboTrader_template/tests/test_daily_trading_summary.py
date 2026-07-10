"""daily_trading_summary 의 text date 컬럼 회귀 테스트.

배경(2026-07-10 라이브 로그): DB 컷오버로 kis_template.daily_prices.date 컬럼이
text('YYYY-MM-DD')다 (레거시 robotrader.daily_prices.date 는 date 타입이었음).
``WHERE date = %s::date`` 로 파라미터를 date 로 캐스팅해 비교하면 kis_template
에서 "연산자 없음: text = date" 로 실패해 일일 매매 리포트 생성 전체가 죽는다.

DB 접속 없이 cursor 를 mock 하여, text date 컬럼 스키마에서 쿼리가 예외 없이
종목수를 반환하는지 검증한다. virtual_trading_records 계열 쿼리는 진짜
timestamptz 컬럼(``(timestamp AT TIME ZONE 'Asia/Seoul')::date = %s::date``)이라
이 버그와 무관하므로 빈 결과로 통과시켜 daily_prices 쿼리 하나에 집중한다.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

from db.connection import DatabaseConnection
from tools.daily_trading_summary import print_today_trading_summary


class _TextDateSchemaCursor:
    """kis_template 스키마 시뮬레이션: daily_prices.date 는 text.

    ``date = %s::date`` 처럼 파라미터를 date 로 캐스팅해 text 컬럼과 비교하면
    실제 kis_template 에서 재현되는 psycopg2 UndefinedFunction 상당 예외를 던진다.
    ``date = %s`` (캐스팅 없음, text-대-text 비교)는 정상 처리한다.
    """

    def __init__(self, daily_price_stock_codes_by_date):
        self._by_date = daily_price_stock_codes_by_date
        self._last = None

    def execute(self, sql, params=None):
        ql = " ".join(sql.lower().split())
        params = params or ()

        if "from daily_prices" in ql and "count(distinct stock_code)" in ql:
            if "%s::date" in ql:
                raise Exception(
                    "operator does not exist: text = date\n"
                    "HINT:  No operator matches the given name and argument types."
                )
            self._last = ("daily_count", len(self._by_date.get(params[0], [])))
            return

        if "from virtual_trading_records" in ql and "coalesce(sum" in ql:
            self._last = ("agg", (0, 0, 0, 0))
        else:
            # BUY/SELL 내역, 보유종목 등 나머지 virtual_trading_records 쿼리
            self._last = ("rows", [])

    def fetchall(self):
        kind, val = self._last
        return val if kind == "rows" else []

    def fetchone(self):
        kind, val = self._last
        if kind == "agg":
            return val
        if kind == "daily_count":
            return (val,)
        return None

    def close(self):
        pass


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _patch_connection(monkeypatch, conn):
    @contextmanager
    def fake_get_connection():
        yield conn

    monkeypatch.setattr(
        DatabaseConnection, "get_connection", staticmethod(fake_get_connection)
    )


def test_daily_price_count_succeeds_against_text_date_column(monkeypatch, capsys):
    """kis_template(daily_prices.date=text) 스키마에서 리포트가 예외 없이 완주하고
    당일 종목수(2건)를 정확히 출력해야 한다."""
    cursor = _TextDateSchemaCursor({"2026-07-10": ["005930", "000660"]})
    conn = MagicMock(wraps=_FakeConn(cursor))
    conn.cursor.return_value = cursor
    _patch_connection(monkeypatch, conn)

    with patch(
        "tools.daily_trading_summary.now_kst",
        return_value=datetime(2026, 7, 10, 15, 35),
    ):
        print_today_trading_summary()

    out = capsys.readouterr().out
    assert "일봉 데이터 수집: 2개 종목 (2026-07-10)" in out

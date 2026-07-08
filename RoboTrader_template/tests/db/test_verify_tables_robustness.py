"""_verify_tables() 견고화 회귀 테스트.

근본원인(2026-07-08 컷오버 크래시): kis_template DB 에 TimescaleDB 확장이
없으면 timescaledb_information.hypertables 뷰가 부재 → 하이퍼테이블 열거 쿼리가
UndefinedTable 로 실패하고, 그 예외가 바깥 try/except 의 raise 로 전파되어
봇이 부팅 시 사망했다. kis_template 는 설계상 하이퍼테이블이 0개(평테이블)이므로
이 실패는 비치명(경고)이어야 한다.

DB 접속 없이 cursor 를 mock 하여 검증한다.
"""
from contextlib import contextmanager
from unittest.mock import MagicMock

from db.database_manager import DatabaseManager


class _FakeCursor:
    """information_schema 조회는 정상, hypertables 조회는 실패시키는 mock cursor."""

    def __init__(self, existing_tables):
        self._existing_tables = existing_tables
        self._last_query = None

    def execute(self, sql, *args, **kwargs):
        low = sql.lower()
        if "timescaledb_information.hypertables" in low:
            self._last_query = "hypertables"
            # 확장 부재 시 psycopg2.errors.UndefinedTable 상당
            raise Exception(
                'relation "timescaledb_information.hypertables" does not exist'
            )
        self._last_query = "tables"

    def fetchall(self):
        if self._last_query == "tables":
            return [(t,) for t in self._existing_tables]
        return []


def _bare_manager(logger):
    """__init__(연결 풀·repo 초기화) 를 건너뛰고 _verify_tables 만 테스트."""
    mgr = DatabaseManager.__new__(DatabaseManager)
    mgr.logger = logger
    return mgr


def _patch_connection(monkeypatch, conn):
    from db import database_manager as dm

    @contextmanager
    def fake_get_connection():
        yield conn

    monkeypatch.setattr(
        dm.DatabaseConnection, "get_connection", staticmethod(fake_get_connection)
    )


def test_verify_tables_does_not_raise_when_timescaledb_view_missing(monkeypatch):
    # 모든 필수 테이블은 존재(누락 경고 없음), 하이퍼테이블 뷰만 부재
    required = {
        "candidate_stocks", "virtual_trading_records", "real_trading_records",
        "financial_data", "quant_factors", "quant_portfolio",
        "daily_prices", "paper_trading_state",
    }
    conn = MagicMock()
    cursor = _FakeCursor(required)
    conn.cursor.return_value = cursor
    _patch_connection(monkeypatch, conn)

    logger = MagicMock()
    mgr = _bare_manager(logger)

    # 핵심: 예외를 raise 하지 않고 정상 반환해야 한다(봇 사망 방지)
    mgr._verify_tables()

    # abort 된 트랜잭션 리셋을 위해 rollback 이 호출되어야 한다
    conn.rollback.assert_called_once()

    # 경고 로깅(에러 아님) — 하이퍼테이블 확인 건너뜀
    warning_msgs = " ".join(str(c.args[0]) for c in logger.warning.call_args_list if c.args)
    assert "하이퍼테이블" in warning_msgs

    # 필수 테이블 존재 확인은 그대로 동작(모두 존재 → 완료 로그)
    info_msgs = " ".join(str(c.args[0]) for c in logger.info.call_args_list if c.args)
    assert "모든 필수 테이블 확인 완료" in info_msgs

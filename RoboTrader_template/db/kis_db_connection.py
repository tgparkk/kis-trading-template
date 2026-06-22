"""kis_template 전용 DB 연결 풀.

db/connection.py(robotrader)와 동일 패턴이나 별도 DB(kis_template)를 가리킨다.
시장데이터(분봉·일봉·지수·corp_events) + (Phase B 이후) 운영데이터의 단일 소유 DB.
"""
import os
import threading
from contextlib import contextmanager

import psycopg2.extensions
from psycopg2 import pool

from utils.logger import setup_logger

logger = setup_logger(__name__)

# NUMERIC → float (Decimal 반환 방지) — db/connection.py와 동일
_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "KIS_DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)


class KisDbConnection:
    """kis_template 전용 TimescaleDB 연결 관리자 (Singleton Pool)."""

    _pool = None
    _init_lock = threading.Lock()

    @classmethod
    def get_config(cls) -> dict:
        return {
            "host": os.getenv("KIS_DB_HOST", "localhost"),
            "port": int(os.getenv("KIS_DB_PORT", 5433)),
            "database": os.getenv("KIS_DB_NAME", "kis_template"),
            "user": os.getenv("KIS_DB_USER", "robotrader"),
            "password": os.getenv("KIS_DB_PASSWORD", "1234"),
        }

    @classmethod
    def initialize(cls, min_conn=2, max_conn=10):
        with cls._init_lock:
            if cls._pool is not None:
                return
            cfg = cls.get_config()
            cls._pool = pool.ThreadedConnectionPool(min_conn, max_conn, **cfg)
            logger.info(f"kis_template DB 연결 풀 초기화: {cfg['host']}:{cfg['port']}/{cfg['database']}")

    @classmethod
    @contextmanager
    def get_connection(cls):
        if cls._pool is None:
            cls.initialize()
        conn = cls._pool.getconn()
        try:
            if conn.closed:
                cls._pool.putconn(conn, close=True)
                conn = cls._pool.getconn()
            yield conn
        finally:
            cls._pool.putconn(conn)

    @classmethod
    def close_all(cls):
        with cls._init_lock:
            if cls._pool is not None:
                cls._pool.closeall()
                cls._pool = None

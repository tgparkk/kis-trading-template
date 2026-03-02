"""
TimescaleDB 연결 풀 관리
"""
import os
import threading
from psycopg2 import pool
import psycopg2.extensions
from contextlib import contextmanager
from utils.logger import setup_logger

logger = setup_logger(__name__)

# PostgreSQL NUMERIC → Python float 자동 변환 (Decimal 반환 방지)
DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    'DEC2FLOAT',
    lambda value, curs: float(value) if value is not None else None
)
psycopg2.extensions.register_type(DEC2FLOAT)

class DatabaseConnection:
    """TimescaleDB 연결 관리자 (Singleton Pool)"""

    _pool = None
    _init_lock = threading.Lock()

    @classmethod
    def initialize(cls, min_conn=2, max_conn=10):
        """연결 풀 초기화"""
        with cls._init_lock:
            if cls._pool is not None:
                return

            db_config = {
                'host': os.getenv('TIMESCALE_HOST', 'localhost'),
                'port': int(os.getenv('TIMESCALE_PORT', 5433)),
                'database': os.getenv('TIMESCALE_DB', 'robotrader'),
                'user': os.getenv('TIMESCALE_USER', 'robotrader'),
                'password': os.getenv('TIMESCALE_PASSWORD', '1234')
            }

            cls._pool = pool.ThreadedConnectionPool(min_conn, max_conn, **db_config)
            logger.info(f"TimescaleDB 연결 풀 초기화: {db_config['host']}:{db_config['port']}")

    @classmethod
    @contextmanager
    def get_connection(cls):
        """연결 가져오기 (Context Manager)"""
        if cls._pool is None:
            cls.initialize()

        conn = cls._pool.getconn()
        try:
            # Health check: 끊어진 연결이면 폐기 후 새 연결 요청
            if conn.closed:
                logger.warning("풀에서 닫힌 연결 감지, 폐기 후 새 연결 요청")
                cls._pool.putconn(conn, close=True)
                conn = cls._pool.getconn()

            yield conn
            conn.commit()
        except Exception:
            # 연결 자체가 끊어진 경우 rollback도 실패할 수 있음
            if not conn.closed:
                conn.rollback()
            raise
        finally:
            # 끊어진 연결은 폐기, 정상 연결만 풀에 반환
            if conn.closed:
                logger.warning("사용 중 끊어진 연결 감지, 폐기 처리")
                cls._pool.putconn(conn, close=True)
            else:
                cls._pool.putconn(conn)

    @classmethod
    def close_all(cls):
        """모든 연결 종료"""
        if cls._pool:
            cls._pool.closeall()
            cls._pool = None

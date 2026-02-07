"""
데이터베이스 Repository 기본 클래스 (TimescaleDB)
"""
from typing import Optional
from contextlib import contextmanager
from utils.logger import setup_logger
from utils.korean_time import now_kst
from db.connection import DatabaseConnection


class BaseRepository:
    """데이터베이스 Repository 기본 클래스"""

    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: 하위 호환성을 위해 유지 (무시됨, TimescaleDB 연결 풀 사용)
        """
        self.logger = setup_logger(self.__class__.__name__)

    @contextmanager
    def _get_connection(self):
        """데이터베이스 연결 반환 (Context Manager)"""
        with DatabaseConnection.get_connection() as conn:
            yield conn

    def _get_today_range_strings(self) -> tuple:
        """KST 기준 오늘의 시작과 내일 시작 시간 문자열 반환"""
        try:
            today = now_kst().date()
            from datetime import datetime, time, timedelta
            start_dt = datetime.combine(today, time(hour=0, minute=0, second=0))
            next_dt = start_dt + timedelta(days=1)
            return (
                start_dt.strftime('%Y-%m-%d %H:%M:%S'),
                next_dt.strftime('%Y-%m-%d %H:%M:%S'),
            )
        except Exception:
            return ("1970-01-01 00:00:00", "2100-01-01 00:00:00")

    @staticmethod
    def to_float(value) -> float:
        """안전한 float 변환"""
        try:
            if value in (None, ""):
                return 0.0
            return float(str(value).replace(',', ''))
        except (ValueError, TypeError):
            return 0.0

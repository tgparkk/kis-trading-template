"""
데이터베이스 관리 모듈 (TimescaleDB)

이 모듈은 Facade 패턴을 사용하여 하위 Repository들을 통합합니다.
실제 로직은 db/repositories/ 패키지의 개별 모듈들에 구현되어 있습니다.

테이블 생성 로직은 init-scripts/01-init.sql에서 관리됩니다.
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from utils.logger import setup_logger
from utils.korean_time import now_kst
from db.connection import DatabaseConnection

# 하위 Repository 임포트
from db.repositories.candidate import CandidateRepository
from db.repositories.price import PriceRepository, PriceRecord
from db.repositories.trading import TradingRepository
from db.repositories.quant import QuantRepository


@dataclass
class CandidateRecord:
    """후보 종목 기록"""
    id: int
    stock_code: str
    stock_name: str
    selection_date: datetime
    score: float
    reasons: str
    status: str = 'active'


# 하위 호환성을 위해 export
__all__ = ['DatabaseManager', 'CandidateRecord', 'PriceRecord']


class DatabaseManager:
    """
    데이터베이스 관리자 (TimescaleDB)

    Facade 패턴으로 다음 Repository들을 통합합니다:
    - CandidateRepository: 후보 종목 관리
    - PriceRepository: 가격 데이터 관리
    - TradingRepository: 매매 기록 관리
    - QuantRepository: 퀀트 팩터/포트폴리오 관리
    """

    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: 하위 호환성을 위해 유지 (무시됨, TimescaleDB 연결 풀 사용)
        """
        self.logger = setup_logger(__name__)

        # TimescaleDB 연결 풀 초기화
        DatabaseConnection.initialize()
        self.logger.info("TimescaleDB 연결 풀 초기화 완료")

        # 테이블 존재 확인 (생성은 init-scripts에서 수행)
        self._verify_tables()

        # Repository 초기화 (db_path는 무시됨)
        self.candidate_repo = CandidateRepository()
        self.price_repo = PriceRepository()
        self.trading_repo = TradingRepository()
        self.quant_repo = QuantRepository()

    def _verify_tables(self):
        """테이블 및 hypertable 존재 확인"""
        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()

                # 핵심 테이블 존재 확인
                required_tables = [
                    'candidate_stocks',
                    'stock_prices',
                    'virtual_trading_records',
                    'real_trading_records',
                    'financial_data',
                    'quant_factors',
                    'quant_portfolio',
                    'daily_prices'
                ]

                cursor.execute('''
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                ''')
                existing_tables = {row[0] for row in cursor.fetchall()}

                missing_tables = set(required_tables) - existing_tables
                if missing_tables:
                    self.logger.warning(f"누락된 테이블: {missing_tables}")
                    self.logger.warning("init-scripts/01-init.sql을 실행하세요")
                else:
                    self.logger.info("모든 필수 테이블 확인 완료")

                # Hypertable 확인
                cursor.execute('''
                    SELECT hypertable_name FROM timescaledb_information.hypertables
                    WHERE hypertable_schema = 'public'
                ''')
                hypertables = {row[0] for row in cursor.fetchall()}

                expected_hypertables = {'stock_prices', 'daily_prices'}
                missing_hypertables = expected_hypertables - hypertables

                if missing_hypertables:
                    self.logger.warning(f"Hypertable 미설정: {missing_hypertables}")
                else:
                    self.logger.info("TimescaleDB hypertable 확인 완료")

        except Exception as e:
            self.logger.error(f"테이블 확인 실패: {e}")
            raise

    # ============================
    # 후보 종목 관련 (CandidateRepository 위임)
    # ============================

    def save_candidate_stocks(self, candidates, selection_date=None) -> bool:
        return self.candidate_repo.save_candidate_stocks(candidates, selection_date)

    def get_candidate_history(self, days: int = 30) -> pd.DataFrame:
        return self.candidate_repo.get_candidate_history(days)

    def get_candidate_performance(self, days: int = 30) -> pd.DataFrame:
        return self.candidate_repo.get_candidate_performance(days)

    def get_daily_candidate_count(self, days: int = 30) -> pd.DataFrame:
        return self.candidate_repo.get_daily_candidate_count(days)

    # ============================
    # 가격 데이터 관련 (PriceRepository 위임)
    # ============================

    def save_price_data(self, stock_code: str, price_data) -> bool:
        return self.price_repo.save_price_data(stock_code, price_data)

    def save_minute_data(self, stock_code: str, date_str: str, df_minute) -> bool:
        return self.price_repo.save_minute_data(stock_code, date_str, df_minute)

    def get_minute_data(self, stock_code: str, date_str: str):
        return self.price_repo.get_minute_data(stock_code, date_str)

    def has_minute_data(self, stock_code: str, date_str: str) -> bool:
        return self.price_repo.has_minute_data(stock_code, date_str)

    def get_price_history(self, stock_code: str, days: int = 30) -> pd.DataFrame:
        return self.price_repo.get_price_history(stock_code, days)

    # ============================
    # 매매 기록 관련 (TradingRepository 위임)
    # ============================

    def get_today_real_loss_count(self, stock_code: str) -> int:
        return self.trading_repo.get_today_real_loss_count(stock_code)

    def save_real_buy(self, stock_code: str, stock_name: str, price: float,
                      quantity: int, strategy: str = '', reason: str = '',
                      timestamp: datetime = None) -> Optional[int]:
        return self.trading_repo.save_real_buy(stock_code, stock_name, price, quantity, strategy, reason, timestamp)

    def save_real_sell(self, stock_code: str, stock_name: str, price: float,
                       quantity: int, strategy: str = '', reason: str = '',
                       buy_record_id: Optional[int] = None, timestamp: datetime = None) -> bool:
        return self.trading_repo.save_real_sell(stock_code, stock_name, price, quantity, strategy, reason, buy_record_id, timestamp)

    def get_last_open_real_buy(self, stock_code: str) -> Optional[int]:
        return self.trading_repo.get_last_open_real_buy(stock_code)

    def save_virtual_buy(self, stock_code: str, stock_name: str, price: float,
                        quantity: int, strategy: str, reason: str,
                        timestamp: datetime = None,
                        target_profit_rate: float = None,
                        stop_loss_rate: float = None) -> Optional[int]:
        return self.trading_repo.save_virtual_buy(stock_code, stock_name, price, quantity, strategy, reason, timestamp, target_profit_rate, stop_loss_rate)

    def save_virtual_sell(self, stock_code: str, stock_name: str, price: float,
                         quantity: int, strategy: str, reason: str,
                         buy_record_id: int, timestamp: datetime = None) -> bool:
        return self.trading_repo.save_virtual_sell(stock_code, stock_name, price, quantity, strategy, reason, buy_record_id, timestamp)

    def get_last_open_virtual_buy(self, stock_code: str, quantity: int = None) -> Optional[int]:
        return self.trading_repo.get_last_open_virtual_buy(stock_code, quantity)

    def get_virtual_open_positions(self) -> pd.DataFrame:
        return self.trading_repo.get_virtual_open_positions()

    def get_virtual_trading_history(self, days: int = 30, include_open: bool = True) -> pd.DataFrame:
        return self.trading_repo.get_virtual_trading_history(days, include_open)

    def get_virtual_trading_stats(self, days: int = 30) -> Dict[str, Any]:
        return self.trading_repo.get_virtual_trading_stats(days)

    def get_today_stop_loss_stocks(self, target_date: str = None) -> List[str]:
        return self.trading_repo.get_today_stop_loss_stocks(target_date)

    # ============================
    # 퀀트 관련 (QuantRepository 위임)
    # ============================

    def upsert_financial_data(self, financial_rows) -> bool:
        return self.quant_repo.upsert_financial_data(financial_rows)

    def save_quant_factors(self, calc_date: str, factor_rows) -> bool:
        return self.quant_repo.save_quant_factors(calc_date, factor_rows)

    def save_quant_portfolio(self, calc_date: str, portfolio_rows) -> bool:
        return self.quant_repo.save_quant_portfolio(calc_date, portfolio_rows)

    def get_quant_portfolio(self, calc_date: str, limit: int = 50):
        return self.quant_repo.get_quant_portfolio(calc_date, limit)

    def get_quant_factors(self, calc_date: str, stock_code: str = None):
        return self.quant_repo.get_quant_factors(calc_date, stock_code)

    # ============================
    # 유틸리티 메서드
    # ============================

    def cleanup_old_data(self, keep_days: int = 90):
        """오래된 데이터 정리"""
        try:
            cutoff_date = now_kst() - timedelta(days=keep_days)

            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM candidate_stocks WHERE selection_date < %s',
                             (cutoff_date.strftime('%Y-%m-%d %H:%M:%S'),))
                cursor.execute('DELETE FROM stock_prices WHERE date_time < %s',
                             (cutoff_date.strftime('%Y-%m-%d %H:%M:%S'),))
                conn.commit()
                self.logger.info(f"{keep_days}일 이전 데이터 정리 완료")

        except Exception as e:
            self.logger.error(f"데이터 정리 실패: {e}")

    def get_database_stats(self) -> Dict[str, int]:
        """데이터베이스 통계"""
        try:
            with DatabaseConnection.get_connection() as conn:
                cursor = conn.cursor()
                stats = {}
                tables = ['candidate_stocks', 'stock_prices', 'trading_records',
                         'virtual_trading_records', 'real_trading_records']
                for table in tables:
                    try:
                        cursor.execute(f'SELECT COUNT(*) FROM {table}')
                        stats[table] = cursor.fetchone()[0]
                    except Exception:
                        stats[table] = 0
                return stats

        except Exception as e:
            self.logger.error(f"통계 조회 실패: {e}")
            return {}

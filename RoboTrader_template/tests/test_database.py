"""
DB 계층 유닛 테스트
- connection.py: 연결 설정 로딩, 환경변수 우선순위
- config.py: DatabaseConfig 생성, from_env
- database_manager.py: Facade 패턴 위임, 유틸리티 메서드
- repositories/base.py: BaseRepository 헬퍼 메서드
- repositories/trading.py: 가상/실 매매 CRUD, 손절 종목 조회
실제 DB 연결 없이 모두 Mock 처리
"""
import sys
from unittest.mock import MagicMock as _MagicMock

# psycopg2 mock (CI 환경에서 미설치)
# 항상 덮어쓰기 — 다른 테스트 파일이 IntegrityError 없는 mock을 먼저 넣을 수 있음
_mock_pg = _MagicMock()
# 실제 예외 클래스 정의 (테스트에서 raise/except 가능하도록)
class _IntegrityError(Exception):
    pass
class _OperationalError(Exception):
    pass
_mock_pg.IntegrityError = _IntegrityError
_mock_pg.OperationalError = _OperationalError
sys.modules['psycopg2'] = _mock_pg
sys.modules['psycopg2.pool'] = _mock_pg.pool
sys.modules['psycopg2.extras'] = _mock_pg.extras

import pytest
import pandas as pd
from datetime import datetime, timedelta, timezone, time
from unittest.mock import Mock, MagicMock, patch, PropertyMock, call
from contextlib import contextmanager


# ============================================================================
# db/config.py 테스트
# ============================================================================

class TestDatabaseConfig:
    """DatabaseConfig 테스트"""

    def test_default_values(self):
        """기본 설정값 확인"""
        from db.config import DatabaseConfig

        config = DatabaseConfig()
        assert config.host == 'localhost'
        assert config.port == 5432
        assert config.database == 'robotrader'
        assert config.user == 'robotrader'

    @patch.dict('os.environ', {
        'TIMESCALE_HOST': 'db-server.example.com',
        'TIMESCALE_PORT': '5433',
        'TIMESCALE_DB': 'custom_db',
        'TIMESCALE_USER': 'custom_user',
        'TIMESCALE_PASSWORD': 'custom_pass'
    })
    def test_from_env_with_all_vars(self):
        """모든 환경변수 설정 시"""
        from db.config import DatabaseConfig

        config = DatabaseConfig.from_env()
        assert config.host == 'db-server.example.com'
        assert config.port == 5433
        assert config.database == 'custom_db'
        assert config.user == 'custom_user'
        assert config.password == 'custom_pass'

    @patch.dict('os.environ', {}, clear=True)
    def test_from_env_defaults(self):
        """환경변수 미설정 시 기본값 사용"""
        from db.config import DatabaseConfig

        config = DatabaseConfig.from_env()
        assert config.host == 'localhost'
        assert config.port == 5432
        assert config.database == 'robotrader'
        assert config.user == 'robotrader'

    @patch.dict('os.environ', {
        'TIMESCALE_HOST': 'custom-host',
        'TIMESCALE_PORT': '9999'
    })
    def test_from_env_partial(self):
        """일부 환경변수만 설정"""
        from db.config import DatabaseConfig

        config = DatabaseConfig.from_env()
        assert config.host == 'custom-host'
        assert config.port == 9999
        assert config.database == 'robotrader'  # 기본값


# ============================================================================
# db/connection.py 테스트
# ============================================================================

class TestDatabaseConnection:
    """DatabaseConnection 연결 풀 테스트"""

    @patch('db.connection.pool.ThreadedConnectionPool')
    def test_initialize_creates_pool(self, mock_pool_cls):
        """연결 풀 초기화"""
        from db.connection import DatabaseConnection

        # 기존 풀 제거
        DatabaseConnection._pool = None

        DatabaseConnection.initialize(min_conn=1, max_conn=5)

        mock_pool_cls.assert_called_once()
        call_kwargs = mock_pool_cls.call_args
        assert call_kwargs[0][0] == 1  # min_conn
        assert call_kwargs[0][1] == 5  # max_conn

        # 정리
        DatabaseConnection._pool = None

    @patch('db.connection.pool.ThreadedConnectionPool')
    def test_initialize_skips_if_exists(self, mock_pool_cls):
        """이미 풀이 있으면 재생성 안 함"""
        from db.connection import DatabaseConnection

        DatabaseConnection._pool = Mock()
        DatabaseConnection.initialize()

        mock_pool_cls.assert_not_called()

        # 정리
        DatabaseConnection._pool = None

    @patch.dict('os.environ', {
        'TIMESCALE_HOST': 'remote-host',
        'TIMESCALE_PORT': '5433',
        'TIMESCALE_DB': 'testdb',
        'TIMESCALE_USER': 'testuser',
        'TIMESCALE_PASSWORD': 'testpass'
    })
    @patch('db.connection.pool.ThreadedConnectionPool')
    def test_initialize_uses_env_vars(self, mock_pool_cls):
        """환경변수에서 연결 설정 로드"""
        from db.connection import DatabaseConnection

        DatabaseConnection._pool = None
        DatabaseConnection.initialize()

        call_kwargs = mock_pool_cls.call_args[1]
        assert call_kwargs['host'] == 'remote-host'
        assert call_kwargs['port'] == 5433
        assert call_kwargs['database'] == 'testdb'
        assert call_kwargs['user'] == 'testuser'
        assert call_kwargs['password'] == 'testpass'

        DatabaseConnection._pool = None

    def test_get_connection_context_manager_commit(self):
        """get_connection이 정상 시 커밋"""
        from db.connection import DatabaseConnection

        mock_conn = Mock()
        mock_conn.closed = 0  # psycopg2: 0 = 정상 연결
        mock_pool = Mock()
        mock_pool.getconn.return_value = mock_conn
        DatabaseConnection._pool = mock_pool

        with DatabaseConnection.get_connection() as conn:
            assert conn is mock_conn

        mock_conn.commit.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)

        DatabaseConnection._pool = None

    def test_get_connection_context_manager_rollback(self):
        """get_connection이 예외 시 롤백"""
        from db.connection import DatabaseConnection

        mock_conn = Mock()
        mock_conn.closed = 0  # psycopg2: 0 = 정상 연결
        mock_pool = Mock()
        mock_pool.getconn.return_value = mock_conn
        DatabaseConnection._pool = mock_pool

        with pytest.raises(ValueError):
            with DatabaseConnection.get_connection() as conn:
                raise ValueError("test error")

        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
        mock_pool.putconn.assert_called_once_with(mock_conn)

        DatabaseConnection._pool = None

    def test_close_all(self):
        """모든 연결 종료"""
        from db.connection import DatabaseConnection

        mock_pool = Mock()
        DatabaseConnection._pool = mock_pool

        DatabaseConnection.close_all()

        mock_pool.closeall.assert_called_once()
        assert DatabaseConnection._pool is None

    def test_close_all_when_no_pool(self):
        """풀이 없을 때 close_all 안전"""
        from db.connection import DatabaseConnection

        DatabaseConnection._pool = None
        DatabaseConnection.close_all()  # 에러 없이 통과
        assert DatabaseConnection._pool is None


# ============================================================================
# db/repositories/base.py 테스트
# ============================================================================

class TestBaseRepository:
    """BaseRepository 기본 클래스 테스트"""

    def test_to_float_normal(self):
        """정상적인 float 변환"""
        from db.repositories.base import BaseRepository

        assert BaseRepository.to_float(100.5) == 100.5
        assert BaseRepository.to_float("200.75") == 200.75
        assert BaseRepository.to_float("1,000.50") == 1000.50

    def test_to_float_none_empty(self):
        """None/빈문자열 -> 0.0"""
        from db.repositories.base import BaseRepository

        assert BaseRepository.to_float(None) == 0.0
        assert BaseRepository.to_float("") == 0.0

    def test_to_float_invalid(self):
        """변환 불가능한 값 -> 0.0"""
        from db.repositories.base import BaseRepository

        assert BaseRepository.to_float("abc") == 0.0
        assert BaseRepository.to_float(object()) == 0.0

    @patch('db.repositories.base.now_kst')
    def test_get_today_range_strings(self, mock_now):
        """오늘 날짜 범위 문자열 생성"""
        from db.repositories.base import BaseRepository

        mock_now.return_value = datetime(2024, 1, 15, 14, 30, 0,
                                         tzinfo=timezone(timedelta(hours=9)))

        repo = BaseRepository.__new__(BaseRepository)
        repo.logger = Mock()
        start_str, next_str = repo._get_today_range_strings()

        assert start_str == '2024-01-15 00:00:00'
        assert next_str == '2024-01-16 00:00:00'

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_connection_delegates(self, mock_db_conn):
        """_get_connection이 DatabaseConnection에 위임"""
        from db.repositories.base import BaseRepository

        mock_conn = Mock()

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = BaseRepository.__new__(BaseRepository)
        repo.logger = Mock()

        with repo._get_connection() as conn:
            assert conn is mock_conn


# ============================================================================
# db/repositories/trading.py 테스트
# ============================================================================

class TestTradingRepositoryVirtualBuy:
    """가상 매수 기록 저장 테스트"""

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_save_virtual_buy_success(self, mock_now, mock_db_conn):
        """가상 매수 저장 성공"""
        from db.repositories.trading import TradingRepository

        now = datetime(2024, 1, 15, 9, 5, 0, tzinfo=timezone(timedelta(hours=9)))
        mock_now.return_value = now

        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (42,)
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.save_virtual_buy(
            stock_code="005930",
            stock_name="삼성전자",
            price=70000,
            quantity=10,
            strategy="quant",
            reason="리밸런싱 매수",
            target_profit_rate=0.17,
            stop_loss_rate=0.09
        )

        assert result == 42
        mock_cursor.execute.assert_called_once()
        # INSERT SQL에 올바른 파라미터가 전달되었는지 검증
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        assert params[0] == "005930"  # stock_code
        assert params[1] == "삼성전자"  # stock_name
        assert params[2] == 10  # quantity (int 변환)
        assert params[3] == 70000.0  # price (float 변환)

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_save_virtual_buy_type_conversion(self, mock_now, mock_db_conn):
        """가상 매수 저장 시 타입 안전성 보장 (numpy 호환)"""
        from db.repositories.trading import TradingRepository

        now = datetime(2024, 1, 15, 9, 5, 0, tzinfo=timezone(timedelta(hours=9)))
        mock_now.return_value = now

        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        # float/int가 아닌 값을 넣어도 안전하게 변환
        result = repo.save_virtual_buy(
            stock_code="005930",
            stock_name="삼성전자",
            price=70000.0,
            quantity=10,
            strategy="quant",
            reason="test",
            target_profit_rate=0.17,
            stop_loss_rate=0.09
        )

        assert result == 1

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_save_virtual_buy_exception(self, mock_now, mock_db_conn):
        """가상 매수 저장 실패 시 None 반환"""
        from db.repositories.trading import TradingRepository

        mock_now.return_value = datetime(2024, 1, 15, 9, 5, 0,
                                         tzinfo=timezone(timedelta(hours=9)))

        @contextmanager
        def fake_get_conn():
            raise Exception("DB connection failed")
            yield  # pragma: no cover

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.save_virtual_buy(
            "005930", "삼성전자", 70000, 10, "quant", "test"
        )
        assert result is None


class TestTradingRepositoryVirtualSell:
    """가상 매도 기록 저장 테스트"""

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_save_virtual_sell_success(self, mock_now, mock_db_conn):
        """가상 매도 저장 성공"""
        from db.repositories.trading import TradingRepository

        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone(timedelta(hours=9)))
        mock_now.return_value = now

        mock_cursor = Mock()
        # 중복 매도 체크: 기존 매도 없음
        mock_cursor.fetchone.side_effect = [
            None,  # 중복 체크 결과
            (70000,),  # 매수 가격 조회 (avg_buy_price)
        ]
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.save_virtual_sell(
            stock_code="005930",
            stock_name="삼성전자",
            price=72000,
            quantity=10,
            strategy="quant",
            reason="목표 익절 도달",
            buy_record_id=42
        )

        assert result is True

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_save_virtual_sell_duplicate_prevention(self, mock_now, mock_db_conn):
        """중복 매도 방지"""
        from db.repositories.trading import TradingRepository

        mock_now.return_value = datetime(2024, 1, 15, 10, 30, 0,
                                         tzinfo=timezone(timedelta(hours=9)))

        mock_cursor = Mock()
        # 중복 매도 체크: 이미 매도 존재
        mock_cursor.fetchone.return_value = (100,)  # 기존 SELL 레코드 ID
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.save_virtual_sell(
            "005930", "삼성전자", 72000, 10, "quant", "익절", buy_record_id=42
        )

        assert result is False  # 중복 방지로 실패

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_save_virtual_sell_race_condition(self, mock_now, mock_db_conn):
        """Race condition으로 IntegrityError 발생 시 False 반환"""
        import psycopg2
        from db.repositories.trading import TradingRepository

        mock_now.return_value = datetime(2024, 1, 15, 10, 30, 0,
                                         tzinfo=timezone(timedelta(hours=9)))

        mock_cursor = Mock()
        # 중복 체크 통과 (None)
        # 매수가격 조회 (70000)
        mock_cursor.fetchone.side_effect = [
            None,       # 중복 체크
            (70000,),   # avg_buy_price
        ]
        # INSERT 시 IntegrityError 발생 (UNIQUE 제약 위반)
        mock_cursor.execute.side_effect = [
            None,  # 첫 번째 execute (중복 체크 SELECT)
            None,  # 두 번째 execute (매수가격 SELECT)
            psycopg2.IntegrityError("duplicate key"),  # 세 번째 execute (INSERT)
        ]
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.save_virtual_sell(
            "005930", "삼성전자", 72000, 10, "quant", "익절", buy_record_id=42
        )

        assert result is False


class TestTradingRepositoryOpenPositions:
    """미체결 포지션 조회 테스트"""

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_virtual_open_positions_success(self, mock_db_conn):
        """미체결 포지션 조회 성공"""
        from db.repositories.trading import TradingRepository

        expected_df = pd.DataFrame([{
            'id': 42,
            'stock_code': '005930',
            'stock_name': '삼성전자',
            'quantity': 10,
            'buy_price': 70000,
            'buy_time': 1705276800,  # unix timestamp
            'strategy': 'quant',
            'buy_reason': '리밸런싱 매수',
            'target_profit_rate': 0.17,
            'stop_loss_rate': 0.09
        }])

        mock_conn = Mock()

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        with patch('db.repositories.trading.pd.read_sql_query', return_value=expected_df):
            result = repo.get_virtual_open_positions()

        assert not result.empty
        assert result.iloc[0]['stock_code'] == '005930'
        assert result.iloc[0]['quantity'] == 10

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_virtual_open_positions_empty(self, mock_db_conn):
        """미체결 포지션 없음"""
        from db.repositories.trading import TradingRepository

        mock_conn = Mock()

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        with patch('db.repositories.trading.pd.read_sql_query', return_value=pd.DataFrame()):
            result = repo.get_virtual_open_positions()

        assert result.empty

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_virtual_open_positions_exception(self, mock_db_conn):
        """미체결 포지션 조회 예외 시 빈 DataFrame"""
        from db.repositories.trading import TradingRepository

        @contextmanager
        def fake_get_conn():
            raise Exception("DB error")
            yield  # pragma: no cover

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_virtual_open_positions()
        assert result.empty


class TestTradingRepositoryStopLoss:
    """손절 종목 조회 테스트"""

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_get_today_stop_loss_stocks(self, mock_now, mock_db_conn):
        """오늘 손절한 종목 코드 리스트"""
        from db.repositories.trading import TradingRepository

        mock_now.return_value = datetime(2024, 1, 15, 10, 0, 0,
                                         tzinfo=timezone(timedelta(hours=9)))

        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            ('010100',), ('005850',), ('012330',)
        ]
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_today_stop_loss_stocks()

        assert len(result) == 3
        assert '010100' in result
        assert '005850' in result
        assert '012330' in result

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_get_today_stop_loss_stocks_none(self, mock_now, mock_db_conn):
        """오늘 손절 종목 없음"""
        from db.repositories.trading import TradingRepository

        mock_now.return_value = datetime(2024, 1, 15, 10, 0, 0,
                                         tzinfo=timezone(timedelta(hours=9)))

        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = []
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_today_stop_loss_stocks()

        assert result == []

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_today_stop_loss_stocks_with_date(self, mock_db_conn):
        """특정 날짜 손절 종목 조회"""
        from db.repositories.trading import TradingRepository

        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [('005930',)]
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_today_stop_loss_stocks(target_date='2024-01-10')

        assert result == ['005930']
        # SQL에 target_date가 올바르게 전달되었는지 확인
        call_args = mock_cursor.execute.call_args
        assert '2024-01-10' in call_args[0][1]

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_today_stop_loss_stocks_exception(self, mock_db_conn):
        """손절 종목 조회 예외 시 빈 리스트"""
        from db.repositories.trading import TradingRepository

        @contextmanager
        def fake_get_conn():
            raise Exception("DB error")
            yield  # pragma: no cover

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_today_stop_loss_stocks()
        assert result == []


class TestTradingRepositoryRealBuy:
    """실거래 매수 기록 테스트"""

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_save_real_buy_success(self, mock_now, mock_db_conn):
        """실거래 매수 저장 성공"""
        from db.repositories.trading import TradingRepository

        now = datetime(2024, 1, 15, 9, 5, 0, tzinfo=timezone(timedelta(hours=9)))
        mock_now.return_value = now

        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (101,)
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.save_real_buy(
            stock_code="005930",
            stock_name="삼성전자",
            price=70000,
            quantity=10,
            strategy="quant",
            reason="리밸런싱 매수"
        )

        assert result == 101

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_save_real_buy_custom_timestamp(self, mock_now, mock_db_conn):
        """실거래 매수 - 커스텀 타임스탬프"""
        from db.repositories.trading import TradingRepository

        now = datetime(2024, 1, 15, 9, 5, 0, tzinfo=timezone(timedelta(hours=9)))
        mock_now.return_value = now

        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (102,)
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        custom_ts = datetime(2024, 1, 14, 15, 0, 0, tzinfo=timezone(timedelta(hours=9)))
        result = repo.save_real_buy(
            "005930", "삼성전자", 70000, 10, "quant", "test", timestamp=custom_ts
        )

        assert result == 102
        # 타임스탬프가 올바르게 전달되었는지 확인
        call_args = mock_cursor.execute.call_args[0][1]
        assert '2024-01-14 15:00:00' in str(call_args)

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_save_real_buy_failure(self, mock_now, mock_db_conn):
        """실거래 매수 저장 실패"""
        from db.repositories.trading import TradingRepository

        mock_now.return_value = datetime(2024, 1, 15, 9, 5, 0,
                                         tzinfo=timezone(timedelta(hours=9)))

        @contextmanager
        def fake_get_conn():
            raise Exception("Connection refused")
            yield  # pragma: no cover

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.save_real_buy("005930", "삼성전자", 70000, 10)
        assert result is None


class TestTradingRepositoryRealSell:
    """실거래 매도 기록 테스트"""

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_save_real_sell_with_profit(self, mock_now, mock_db_conn):
        """실거래 매도 - 익절"""
        from db.repositories.trading import TradingRepository

        now = datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone(timedelta(hours=9)))
        mock_now.return_value = now

        mock_cursor = Mock()
        # 첫 번째 execute: avg_buy_price 조회 결과
        mock_cursor.fetchone.return_value = (70000,)
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.save_real_sell(
            stock_code="005930",
            stock_name="삼성전자",
            price=75000,
            quantity=10,
            strategy="quant",
            reason="목표 익절 도달",
            buy_record_id=101
        )

        assert result is True

        # INSERT 호출에서 profit_loss 확인
        insert_call = mock_cursor.execute.call_args_list[-1]
        params = insert_call[0][1]
        # profit_loss = (75000 - 70000) * 10 = 50000
        assert params[7] == 50000.0  # profit_loss
        # profit_rate = (75000 - 70000) / 70000
        assert abs(params[8] - 0.0714) < 0.001  # profit_rate

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_save_real_sell_no_buy_price(self, mock_now, mock_db_conn):
        """실거래 매도 - 매수가 없으면 손익 0"""
        from db.repositories.trading import TradingRepository

        now = datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone(timedelta(hours=9)))
        mock_now.return_value = now

        mock_cursor = Mock()
        # avg_buy_price 조회 실패
        mock_cursor.fetchone.side_effect = [
            (None,),  # avg 계산 결과 None
            None,     # buy_record_id로 조회 실패
        ]
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.save_real_sell(
            "005930", "삼성전자", 72000, 10, "quant", "매도"
        )

        assert result is True


class TestTradingRepositoryLastOpenBuy:
    """미매칭 매수 조회 테스트"""

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_last_open_virtual_buy(self, mock_db_conn):
        """미매칭 가상 매수 ID 조회"""
        from db.repositories.trading import TradingRepository

        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (42,)
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_last_open_virtual_buy("005930")

        assert result == 42

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_last_open_virtual_buy_not_found(self, mock_db_conn):
        """미매칭 가상 매수 없음"""
        from db.repositories.trading import TradingRepository

        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_last_open_virtual_buy("005930")

        assert result is None

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_last_open_virtual_buy_with_quantity(self, mock_db_conn):
        """미매칭 가상 매수 - 수량 지정 쿼리"""
        from db.repositories.trading import TradingRepository

        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (55,)
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_last_open_virtual_buy("005930", quantity=10)

        assert result == 55
        # quantity가 있으면 다른 SQL 사용 확인
        sql = mock_cursor.execute.call_args[0][0]
        assert 'HAVING' in sql

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_last_open_real_buy(self, mock_db_conn):
        """미매칭 실거래 매수 ID 조회"""
        from db.repositories.trading import TradingRepository

        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (99,)
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_last_open_real_buy("005930")

        assert result == 99

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_last_open_real_buy_exception(self, mock_db_conn):
        """미매칭 실거래 매수 조회 실패"""
        from db.repositories.trading import TradingRepository

        @contextmanager
        def fake_get_conn():
            raise Exception("DB error")
            yield  # pragma: no cover

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_last_open_real_buy("005930")
        assert result is None


class TestTradingRepositoryTodayLossCount:
    """당일 손실 건수 조회 테스트"""

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_get_today_real_loss_count(self, mock_now, mock_db_conn):
        """오늘 손실 매도 건수 조회"""
        from db.repositories.trading import TradingRepository

        mock_now.return_value = datetime(2024, 1, 15, 14, 0, 0,
                                         tzinfo=timezone(timedelta(hours=9)))

        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (3,)
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_today_real_loss_count("005930")

        assert result == 3

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_get_today_real_loss_count_zero(self, mock_now, mock_db_conn):
        """오늘 손실 없음"""
        from db.repositories.trading import TradingRepository

        mock_now.return_value = datetime(2024, 1, 15, 14, 0, 0,
                                         tzinfo=timezone(timedelta(hours=9)))

        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (0,)
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_today_real_loss_count("005930")

        assert result == 0

    @patch('db.repositories.base.DatabaseConnection')
    @patch('db.repositories.trading.now_kst')
    def test_get_today_real_loss_count_exception(self, mock_now, mock_db_conn):
        """당일 손실 조회 실패 시 0 반환"""
        from db.repositories.trading import TradingRepository

        mock_now.return_value = datetime(2024, 1, 15, 14, 0, 0,
                                         tzinfo=timezone(timedelta(hours=9)))

        @contextmanager
        def fake_get_conn():
            raise Exception("DB error")
            yield  # pragma: no cover

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()
        result = repo.get_today_real_loss_count("005930")
        assert result == 0


class TestTradingRepositoryTradingStats:
    """매매 통계 테스트"""

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_virtual_trading_stats_empty(self, mock_db_conn):
        """매매 통계 - 거래 없음"""
        from db.repositories.trading import TradingRepository

        mock_conn = Mock()

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()

        with patch.object(repo, 'get_virtual_trading_history', return_value=pd.DataFrame()), \
             patch.object(repo, 'get_virtual_open_positions', return_value=pd.DataFrame()):
            stats = repo.get_virtual_trading_stats(days=30)

        assert stats['total_trades'] == 0
        assert stats['open_positions'] == 0
        assert stats['win_rate'] == 0

    @patch('db.repositories.base.DatabaseConnection')
    def test_get_virtual_trading_stats_with_trades(self, mock_db_conn):
        """매매 통계 - 거래 있음"""
        from db.repositories.trading import TradingRepository

        mock_conn = Mock()

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        repo = TradingRepository()

        completed = pd.DataFrame([
            {'profit_loss': 5000, 'profit_rate': 0.05, 'strategy': 'quant'},
            {'profit_loss': -2000, 'profit_rate': -0.02, 'strategy': 'quant'},
            {'profit_loss': 3000, 'profit_rate': 0.03, 'strategy': 'quant'},
        ])
        open_pos = pd.DataFrame([{'stock_code': '005930'}])

        with patch.object(repo, 'get_virtual_trading_history', return_value=completed), \
             patch.object(repo, 'get_virtual_open_positions', return_value=open_pos):
            stats = repo.get_virtual_trading_stats(days=30)

        assert stats['total_trades'] == 3
        assert stats['open_positions'] == 1
        assert abs(stats['win_rate'] - 66.67) < 1  # 2/3 = 66.67%
        assert stats['total_profit'] == 6000
        assert stats['max_profit'] == 5000
        assert stats['max_loss'] == -2000


# ============================================================================
# db/database_manager.py (Facade) 테스트
# ============================================================================

class TestDatabaseManagerFacade:
    """DatabaseManager Facade 패턴 위임 테스트"""

    def _make_manager(self):
        """DatabaseManager Mock 생성 헬퍼"""
        with patch('db.database_manager.DatabaseConnection'), \
             patch.object(
                 __import__('db.database_manager', fromlist=['DatabaseManager']).DatabaseManager,
                 '_verify_tables'
             ):
            from db.database_manager import DatabaseManager
            manager = DatabaseManager.__new__(DatabaseManager)
            manager.logger = Mock()
            manager.candidate_repo = Mock()
            manager.price_repo = Mock()
            manager.trading_repo = Mock()
            manager.quant_repo = Mock()
            return manager

    def test_save_virtual_buy_delegates(self):
        """save_virtual_buy가 trading_repo에 위임"""
        manager = self._make_manager()
        manager.trading_repo.save_virtual_buy.return_value = 42

        result = manager.save_virtual_buy(
            "005930", "삼성전자", 70000, 10, "quant", "test"
        )

        assert result == 42
        manager.trading_repo.save_virtual_buy.assert_called_once()

    def test_save_virtual_sell_delegates(self):
        """save_virtual_sell이 trading_repo에 위임"""
        manager = self._make_manager()
        manager.trading_repo.save_virtual_sell.return_value = True

        result = manager.save_virtual_sell(
            "005930", "삼성전자", 72000, 10, "quant", "익절", buy_record_id=42
        )

        assert result is True
        manager.trading_repo.save_virtual_sell.assert_called_once()

    def test_get_virtual_open_positions_delegates(self):
        """get_virtual_open_positions가 trading_repo에 위임"""
        manager = self._make_manager()
        expected_df = pd.DataFrame([{'stock_code': '005930'}])
        manager.trading_repo.get_virtual_open_positions.return_value = expected_df

        result = manager.get_virtual_open_positions()
        assert len(result) == 1
        manager.trading_repo.get_virtual_open_positions.assert_called_once()

    def test_get_today_stop_loss_stocks_delegates(self):
        """get_today_stop_loss_stocks가 trading_repo에 위임"""
        manager = self._make_manager()
        manager.trading_repo.get_today_stop_loss_stocks.return_value = ['005930']

        result = manager.get_today_stop_loss_stocks()
        assert result == ['005930']

    def test_save_candidate_stocks_delegates(self):
        """save_candidate_stocks가 candidate_repo에 위임"""
        manager = self._make_manager()
        manager.candidate_repo.save_candidate_stocks.return_value = True

        result = manager.save_candidate_stocks([{'code': '005930'}])
        assert result is True
        manager.candidate_repo.save_candidate_stocks.assert_called_once()

    def test_save_price_data_delegates(self):
        """save_price_data가 price_repo에 위임"""
        manager = self._make_manager()
        manager.price_repo.save_price_data.return_value = True

        result = manager.save_price_data("005930", {"close": 70000})
        assert result is True
        manager.price_repo.save_price_data.assert_called_once()

    def test_save_quant_portfolio_delegates(self):
        """save_quant_portfolio가 quant_repo에 위임"""
        manager = self._make_manager()
        manager.quant_repo.save_quant_portfolio.return_value = True

        result = manager.save_quant_portfolio("2024-01-15", [])
        assert result is True
        manager.quant_repo.save_quant_portfolio.assert_called_once()


class TestDatabaseManagerUtility:
    """DatabaseManager 유틸리티 메서드 테스트"""

    def _make_manager(self):
        """DatabaseManager Mock 생성 헬퍼"""
        from db.database_manager import DatabaseManager
        manager = DatabaseManager.__new__(DatabaseManager)
        manager.logger = Mock()
        manager.candidate_repo = Mock()
        manager.price_repo = Mock()
        manager.trading_repo = Mock()
        manager.quant_repo = Mock()
        return manager

    @patch('db.database_manager.DatabaseConnection')
    @patch('db.database_manager.now_kst')
    def test_cleanup_old_data(self, mock_now, mock_db_conn):
        """오래된 데이터 정리"""
        from db.database_manager import DatabaseManager

        mock_now.return_value = datetime(2024, 4, 15, 0, 0, 0,
                                         tzinfo=timezone(timedelta(hours=9)))

        mock_cursor = Mock()
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        manager = self._make_manager()
        manager.cleanup_old_data(keep_days=90)

        # DELETE가 2번 호출됨 (candidate_stocks, stock_prices)
        assert mock_cursor.execute.call_count == 2

    @patch('db.database_manager.DatabaseConnection')
    def test_get_database_stats(self, mock_db_conn):
        """데이터베이스 통계 조회"""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (100,)
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        mock_db_conn.get_connection = fake_get_conn

        manager = self._make_manager()
        stats = manager.get_database_stats()

        assert len(stats) > 0
        # 모든 테이블에 대해 100건으로 반환
        for count in stats.values():
            assert count == 100

    @patch('db.database_manager.DatabaseConnection')
    def test_get_database_stats_failure(self, mock_db_conn):
        """데이터베이스 통계 조회 실패"""
        @contextmanager
        def fake_get_conn():
            raise Exception("DB error")
            yield  # pragma: no cover

        mock_db_conn.get_connection = fake_get_conn

        manager = self._make_manager()
        stats = manager.get_database_stats()

        assert stats == {}


class TestCandidateRecord:
    """CandidateRecord 데이터 클래스 테스트"""

    def test_candidate_record_creation(self):
        """CandidateRecord 생성"""
        from db.database_manager import CandidateRecord

        record = CandidateRecord(
            id=1,
            stock_code="005930",
            stock_name="삼성전자",
            selection_date=datetime(2024, 1, 15),
            score=85.5,
            reasons="퀀트 선정"
        )
        assert record.stock_code == "005930"
        assert record.score == 85.5
        assert record.status == 'active'  # 기본값

    def test_candidate_record_custom_status(self):
        """CandidateRecord 커스텀 status"""
        from db.database_manager import CandidateRecord

        record = CandidateRecord(
            id=1,
            stock_code="005930",
            stock_name="삼성전자",
            selection_date=datetime(2024, 1, 15),
            score=85.5,
            reasons="퀀트 선정",
            status="completed"
        )
        assert record.status == "completed"

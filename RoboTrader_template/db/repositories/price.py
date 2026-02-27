"""
가격 데이터 Repository (TimescaleDB)
"""
import pandas as pd
from datetime import timedelta
from typing import List, Optional
from dataclasses import dataclass

from .base import BaseRepository
from utils.korean_time import now_kst


@dataclass
class PriceRecord:
    """가격 기록"""
    stock_code: str
    date_time: object
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int


class PriceRepository(BaseRepository):
    """가격 데이터 접근 클래스"""

    def save_price_data(self, stock_code: str, price_data: List[PriceRecord]) -> bool:
        """가격 데이터 저장 (stock_prices 테이블)"""
        try:
            if not price_data:
                return True

            with self._get_connection() as conn:
                cursor = conn.cursor()

                for record in price_data:
                    cursor.execute('''
                        INSERT INTO stock_prices
                        (stock_code, date_time, open_price, high_price, low_price, close_price, volume, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (stock_code, date_time) DO UPDATE SET
                            open_price = EXCLUDED.open_price,
                            high_price = EXCLUDED.high_price,
                            low_price = EXCLUDED.low_price,
                            close_price = EXCLUDED.close_price,
                            volume = EXCLUDED.volume,
                            created_at = EXCLUDED.created_at
                    ''', (
                        stock_code,
                        record.date_time.strftime('%Y-%m-%d %H:%M:%S'),
                        record.open_price,
                        record.high_price,
                        record.low_price,
                        record.close_price,
                        record.volume,
                        now_kst().strftime('%Y-%m-%d %H:%M:%S')
                    ))

                self.logger.debug(f"{stock_code} 가격 데이터 {len(price_data)}개 저장")
                return True

        except Exception as e:
            self.logger.error(f"가격 데이터 저장 실패 ({stock_code}): {e}")
            return False

    def save_minute_data(self, stock_code: str, date_str: str, df_minute: pd.DataFrame) -> bool:
        """1분봉 데이터 저장 (minute_prices 테이블)"""
        try:
            if df_minute is None or df_minute.empty:
                return True

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 기존 데이터 삭제
                start_datetime = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} 00:00:00"
                end_datetime = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} 23:59:59"

                cursor.execute('''
                    DELETE FROM minute_prices
                    WHERE stock_code = %s AND time >= %s AND time <= %s
                ''', (stock_code, start_datetime, end_datetime))

                # 배치 삽입을 위한 데이터 준비
                rows_to_insert = []
                created_at = now_kst().strftime('%Y-%m-%d %H:%M:%S')

                for _, row in df_minute.iterrows():
                    rows_to_insert.append((
                        stock_code,
                        row['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
                        row['open'], row['high'], row['low'], row['close'],
                        row['volume'],
                        created_at
                    ))

                # executemany로 배치 삽입
                cursor.executemany('''
                    INSERT INTO minute_prices
                    (stock_code, time, open, high, low, close, volume, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (stock_code, time) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        created_at = EXCLUDED.created_at
                ''', rows_to_insert)

                self.logger.debug(f"{stock_code} 1분봉 데이터 {len(df_minute)}개 저장 ({date_str})")
                return True

        except Exception as e:
            self.logger.error(f"1분봉 데이터 저장 실패 ({stock_code}, {date_str}): {e}")
            return False

    def get_minute_data(self, stock_code: str, date_str: str) -> Optional[pd.DataFrame]:
        """1분봉 데이터 조회 (minute_prices 테이블)"""
        try:
            with self._get_connection() as conn:
                start_datetime = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} 00:00:00"
                end_datetime = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} 23:59:59"

                query = '''
                    SELECT time, open, high, low, close, volume
                    FROM minute_prices
                    WHERE stock_code = %s AND time >= %s AND time <= %s
                    ORDER BY time
                '''

                df = pd.read_sql_query(query, conn, params=(stock_code, start_datetime, end_datetime))

                if df.empty:
                    return None

                df['datetime'] = pd.to_datetime(df['time'])
                df = df.drop('time', axis=1)

                self.logger.debug(f"{stock_code} 1분봉 데이터 {len(df)}개 조회 ({date_str})")
                return df

        except Exception as e:
            self.logger.error(f"1분봉 데이터 조회 실패 ({stock_code}, {date_str}): {e}")
            return None

    def has_minute_data(self, stock_code: str, date_str: str) -> bool:
        """1분봉 데이터 존재 여부 확인 (minute_prices 테이블)"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                start_datetime = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} 00:00:00"
                end_datetime = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} 23:59:59"

                cursor.execute('''
                    SELECT COUNT(1) FROM minute_prices
                    WHERE stock_code = %s AND time >= %s AND time <= %s
                ''', (stock_code, start_datetime, end_datetime))

                return cursor.fetchone()[0] > 0

        except Exception as e:
            self.logger.error(f"1분봉 데이터 존재 확인 실패 ({stock_code}, {date_str}): {e}")
            return False

    def get_price_history(self, stock_code: str, days: int = 30) -> pd.DataFrame:
        """종목별 가격 이력 조회 (stock_prices 테이블)"""
        try:
            start_date = now_kst() - timedelta(days=days)

            with self._get_connection() as conn:
                query = '''
                    SELECT date_time, open_price, high_price, low_price, close_price, volume
                    FROM stock_prices
                    WHERE stock_code = %s AND date_time >= %s
                    ORDER BY date_time ASC
                '''

                df = pd.read_sql_query(query, conn, params=(stock_code, start_date.strftime('%Y-%m-%d %H:%M:%S')))
                df['date_time'] = pd.to_datetime(df['date_time'])

                self.logger.debug(f"{stock_code} 가격 이력 {len(df)}건 조회")
                return df

        except Exception as e:
            self.logger.error(f"가격 이력 조회 실패 ({stock_code}): {e}")
            return pd.DataFrame()

    # ===== 일봉 데이터 메서드 (daily_prices 테이블) =====

    def save_daily_price(self, stock_code: str, date_str: str,
                         open_price: float, high_price: float,
                         low_price: float, close_price: float,
                         volume: int) -> bool:
        """일봉 데이터 단건 저장"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT INTO daily_prices
                    (stock_code, date, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (stock_code, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume
                ''', (stock_code, date_str, open_price, high_price, low_price, close_price, volume))

                self.logger.debug(f"{stock_code} 일봉 데이터 저장 ({date_str})")
                return True

        except Exception as e:
            self.logger.error(f"일봉 데이터 저장 실패 ({stock_code}, {date_str}): {e}")
            return False

    def save_daily_prices_batch(self, stock_code: str, df_daily: pd.DataFrame) -> bool:
        """일봉 데이터 배치 저장"""
        try:
            if df_daily is None or df_daily.empty:
                return True

            with self._get_connection() as conn:
                cursor = conn.cursor()

                rows_to_insert = []
                for _, row in df_daily.iterrows():
                    # date 컬럼이 있으면 사용, 없으면 time 컬럼 사용
                    date_val = row.get('date', row.get('time', None))
                    if date_val is None:
                        continue

                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_val)[:10]

                    rows_to_insert.append((
                        stock_code,
                        date_str,
                        row.get('open', row.get('open_price', 0)),
                        row.get('high', row.get('high_price', 0)),
                        row.get('low', row.get('low_price', 0)),
                        row.get('close', row.get('close_price', 0)),
                        int(row.get('volume', 0))
                    ))

                cursor.executemany('''
                    INSERT INTO daily_prices
                    (stock_code, date, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (stock_code, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume
                ''', rows_to_insert)

                self.logger.debug(f"{stock_code} 일봉 데이터 {len(rows_to_insert)}개 배치 저장")
                return True

        except Exception as e:
            self.logger.error(f"일봉 데이터 배치 저장 실패 ({stock_code}): {e}")
            return False

    def get_daily_prices(self, stock_code: str, days: int = 30) -> pd.DataFrame:
        """일봉 데이터 조회"""
        try:
            start_date = now_kst() - timedelta(days=days)

            with self._get_connection() as conn:
                query = '''
                    SELECT date, open, high, low, close, volume
                    FROM daily_prices
                    WHERE stock_code = %s AND date >= %s
                    ORDER BY date ASC
                '''

                df = pd.read_sql_query(query, conn, params=(stock_code, start_date.strftime('%Y-%m-%d')))
                if not df.empty:
                    df['date'] = pd.to_datetime(df['date'])

                self.logger.debug(f"{stock_code} 일봉 데이터 {len(df)}건 조회")
                return df

        except Exception as e:
            self.logger.error(f"일봉 데이터 조회 실패 ({stock_code}): {e}")
            return pd.DataFrame()

    def get_latest_daily_price(self, stock_code: str) -> Optional[dict]:
        """최신 일봉 데이터 1건 조회"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT date, open, high, low, close, volume
                    FROM daily_prices
                    WHERE stock_code = %s
                    ORDER BY date DESC
                    LIMIT 1
                ''', (stock_code,))

                row = cursor.fetchone()
                if row:
                    return {
                        'date': row[0],
                        'open': row[1],
                        'high': row[2],
                        'low': row[3],
                        'close': row[4],
                        'volume': row[5]
                    }
                return None

        except Exception as e:
            self.logger.error(f"최신 일봉 데이터 조회 실패 ({stock_code}): {e}")
            return None

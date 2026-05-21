"""
가격 데이터 Repository (TimescaleDB)
"""
import pandas as pd
from datetime import timedelta
from typing import Optional
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
                    date_val = row.get('date', row.get('time', row.get('stck_bsop_date', None)))
                    if date_val is None:
                        continue

                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_val).strip()
                        # KIS API 'YYYYMMDD' 형식 → 'YYYY-MM-DD' 변환
                        if len(date_str) == 8 and date_str.isdigit():
                            date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                        else:
                            date_str = date_str[:10]

                    rows_to_insert.append((
                        stock_code,
                        date_str,
                        float(row.get('open', row.get('open_price', row.get('stck_oprc', 0)))),
                        float(row.get('high', row.get('high_price', row.get('stck_hgpr', 0)))),
                        float(row.get('low', row.get('low_price', row.get('stck_lwpr', 0)))),
                        float(row.get('close', row.get('close_price', row.get('stck_clpr', 0)))),
                        int(row.get('volume', row.get('acml_vol', 0)))
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

                cursor = conn.cursor()
                cursor.execute(query, (stock_code, start_date.strftime('%Y-%m-%d')))
                rows = cursor.fetchall()
                if rows:
                    columns = [desc[0] for desc in cursor.description]
                    df = pd.DataFrame(rows, columns=columns)
                else:
                    df = pd.DataFrame()
                cursor.close()
                if not df.empty:
                    df['date'] = pd.to_datetime(df['date'])

                self.logger.debug(f"{stock_code} 일봉 데이터 {len(df)}건 조회")
                return df

        except Exception as e:
            self.logger.error(f"일봉 데이터 조회 실패 ({stock_code}): {e}")
            return pd.DataFrame()

    # ===== 분봉 데이터 메서드 (minute_candles 테이블) =====

    def get_minute_prices(self, stock_code: str, trade_date: str) -> pd.DataFrame:
        """minute_candles에서 단일 종목 1일치 분봉 반환 (datetime 오름차순).

        Args:
            stock_code: 종목코드 (예: '005930')
            trade_date: 거래일 YYYYMMDD 또는 YYYY-MM-DD

        Returns:
            DataFrame with columns: datetime, open, high, low, close, volume, amount
            빈 결과 시 빈 DataFrame.
        """
        try:
            # YYYY-MM-DD → YYYYMMDD 정규화 (DB 컬럼은 YYYYMMDD 문자열)
            if len(trade_date) == 10 and trade_date[4] == '-':
                trade_date = trade_date.replace('-', '')

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    SELECT stock_code, datetime, open, high, low, close, volume, amount
                    FROM minute_candles
                    WHERE stock_code = %s AND trade_date = %s
                    ORDER BY datetime
                    ''',
                    (stock_code, trade_date)
                )
                rows = cursor.fetchall()
                if rows:
                    columns = [desc[0] for desc in cursor.description]
                    df = pd.DataFrame(rows, columns=columns)
                    df['datetime'] = pd.to_datetime(df['datetime'])
                else:
                    df = pd.DataFrame()
                cursor.close()

            self.logger.debug(f"{stock_code} 분봉 데이터 {len(df)}건 조회 ({trade_date})")
            return df

        except Exception as e:
            self.logger.error(f"분봉 데이터 조회 실패 ({stock_code}, {trade_date}): {e}")
            return pd.DataFrame()

    def get_minute_prices_bulk(self, stock_codes: list, trade_date: str) -> dict:
        """다중 종목 1일치 분봉 일괄 조회 (단일 SQL IN (...) 사용).

        Args:
            stock_codes: 종목코드 리스트
            trade_date: 거래일 YYYYMMDD 또는 YYYY-MM-DD

        Returns:
            dict[stock_code -> DataFrame]. 데이터 없는 종목은 빈 DataFrame.
        """
        if not stock_codes:
            return {}

        try:
            # YYYY-MM-DD → YYYYMMDD 정규화 (DB 컬럼은 YYYYMMDD 문자열)
            if len(trade_date) == 10 and trade_date[4] == '-':
                trade_date = trade_date.replace('-', '')

            with self._get_connection() as conn:
                cursor = conn.cursor()
                # psycopg2는 list → ANY(%s) 형식 지원
                cursor.execute(
                    '''
                    SELECT stock_code, datetime, open, high, low, close, volume, amount
                    FROM minute_candles
                    WHERE stock_code = ANY(%s) AND trade_date = %s
                    ORDER BY stock_code, datetime
                    ''',
                    (list(stock_codes), trade_date)
                )
                rows = cursor.fetchall()
                if rows:
                    columns = [desc[0] for desc in cursor.description]
                    df_all = pd.DataFrame(rows, columns=columns)
                    df_all['datetime'] = pd.to_datetime(df_all['datetime'])
                else:
                    df_all = pd.DataFrame()
                cursor.close()

            # stock_code별로 분리
            result: dict = {}
            for code in stock_codes:
                if not df_all.empty and 'stock_code' in df_all.columns:
                    sub = df_all[df_all['stock_code'] == code].reset_index(drop=True)
                else:
                    sub = pd.DataFrame()
                result[code] = sub

            self.logger.debug(
                f"분봉 일괄 조회 {len(stock_codes)}종목 ({trade_date}), "
                f"총 {len(df_all)}건"
            )
            return result

        except Exception as e:
            self.logger.error(f"분봉 일괄 조회 실패 ({trade_date}): {e}")
            return {code: pd.DataFrame() for code in stock_codes}

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

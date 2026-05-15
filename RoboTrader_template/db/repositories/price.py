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

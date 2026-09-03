"""
가격 데이터 Repository (TimescaleDB)
"""
import pandas as pd
from datetime import timedelta
from typing import Optional
from dataclasses import dataclass

from .base import BaseRepository
from utils.korean_time import now_kst


# =============================================================================
# daily_prices OHLC 쓰기 SQL — 이 파일의 «유일한» 쓰기 계약이다.
#   사전등록 docs/prereg_2026-09-03_write_path_rawprice_upsert.md §6-22:
#   가드는 「살아 있는 호출자가 있는 함수」가 아니라 「그 SQL 을 실행하는 모든 함수」에
#   건다. ⇒ 문장을 여기 한 곳에만 두고, 새 쓰기 함수를 만들 때도 이 상수를 쓴다.
# =============================================================================
_DAILY_INSERT_HEAD_SQL = '''
                    INSERT INTO daily_prices
                    (stock_code, date, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
'''

# 기존 규약 — 있는 행이면 OHLCV 를 덮어쓴다.
DAILY_UPSERT_SQL = _DAILY_INSERT_HEAD_SQL + '''
                    ON CONFLICT (stock_code, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume
'''

# (E′) — 있는 행은 «절대» 안 건드리고, 없는 행만 채운다(빈 칸 채우기는 유지된다).
DAILY_INSERT_ONLY_SQL = _DAILY_INSERT_HEAD_SQL + '''
                    ON CONFLICT (stock_code, date) DO NOTHING
'''


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
    #
    # 🔴 `save_daily_price()`(단건 OHLC UPSERT, W8)는 2026-09-03 제거됐다 — 호출자 0건인데
    #    `save_daily_prices_batch` 와 «같은 파일»에 있는 쌍둥이 UPSERT 라, (E′) 가드가
    #    안 걸린 채 나중에 배선되면 원복 채널이 조용히 부활한다(사전등록 D-3 · §6-22).
    #    단건 저장이 다시 필요하면 1행짜리 DataFrame 으로 `save_daily_prices_batch` 를
    #    쓸 것 — 쓰기 문장은 이 파일 맨 위 두 상수뿐이어야 한다.

    def save_daily_prices_batch(self, stock_code: str, df_daily: pd.DataFrame,
                                past_rows_insert_only: bool = False) -> bool:
        """일봉 데이터 배치 저장.

        Args:
            past_rows_insert_only: (E′) — True 면 **오늘(KST) 이전** 날짜 행은
                `ON CONFLICT DO NOTHING` 으로 쓴다(있으면 안 건드리고, 없으면 넣는다).
                **오늘 행은 기존대로 UPSERT** 한다(최신 봉이 안 들어오면 그게 실패다).
                사전등록 `docs/prereg_2026-09-03_write_path_rawprice_upsert.md` D-1.

        🔴 기본값 False 는 «기존 호출자의 의미를 안 바꾼다»는 뜻이다 — regime 지수
           갱신(W3)·보정 도구 계열은 과거 행을 «고치는 것»이 목적이라 얼리면 안 된다.
           가드를 켜는 곳은 W1(장전 훅) 한 곳이고, 그 스위치가
           `config.constants.W1_PAST_ROWS_INSERT_ONLY` 다(롤백 = 그 값 하나).
        """
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

                if past_rows_insert_only:
                    # (E′) — 경계는 «오늘(KST)»이다. date 컬럼은 text 이고 값은 위에서
                    # 'YYYY-MM-DD' 로 정규화됐으므로 문자열 비교가 곧 날짜 비교다.
                    today_str = now_kst().strftime('%Y-%m-%d')
                    past_rows = [r for r in rows_to_insert if r[1] < today_str]
                    today_rows = [r for r in rows_to_insert if r[1] >= today_str]

                    n_filled = 0
                    if past_rows:
                        cursor.executemany(DAILY_INSERT_ONLY_SQL, past_rows)
                        rc = getattr(cursor, 'rowcount', None)
                        n_filled = rc if isinstance(rc, int) and rc > 0 else 0
                    if today_rows:
                        cursor.executemany(DAILY_UPSERT_SQL, today_rows)

                    self.logger.debug(
                        f"{stock_code} 일봉 데이터 {len(rows_to_insert)}개 배치 저장 "
                        f"(E′ 과거 {len(past_rows)}행 INSERT-only · 당일 {len(today_rows)}행 UPSERT)")
                    if n_filled:
                        # 과거 구간 «빈 칸 채우기» 실측 — 사전등록 §9 M-1 이 요구하는 값.
                        self.logger.info(
                            f"💾 {stock_code} 과거 구간 빈 칸 INSERT {n_filled}행 (E′)")
                else:
                    cursor.executemany(DAILY_UPSERT_SQL, rows_to_insert)
                    self.logger.debug(f"{stock_code} 일봉 데이터 {len(rows_to_insert)}개 배치 저장")

                return True

        except Exception as e:
            self.logger.error(f"일봉 데이터 배치 저장 실패 ({stock_code}): {e}")
            return False

    def get_daily_prices(self, stock_code: str, days: int = 30) -> pd.DataFrame:
        """일봉 데이터 조회. volume 은 **분할조정된 값**이다.

        🔑 close 는 이미 조정 저장(`adj_close = raw_close / adj_factor`)인데 volume 은
        원본이라 단위가 어긋난다 ⇒ 읽기 시점에 volume 에 adj_factor 를 곱해 맞춘다.
        안 맞추면 거래량 «비율» 룰(daytrading 20봉평균×2 · minervini dry-up)이
        분할 경계 20~40봉 동안 왜곡되고 `close×volume` 거래대금도 틀린다.
        🔴 close 에는 곱하면 «안 된다»(가짜 분할 절벽). 방향이 반대인 두 규칙이다.
        상세 → tests/test_adj_factor_volume_units.py (2026-08-15 감사)
        """
        try:
            start_date = now_kst() - timedelta(days=days)

            with self._get_connection() as conn:
                query = '''
                    SELECT date, open, high, low, close,
                           (volume * COALESCE(adj_factor, 1))::double precision AS volume
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

    def get_universe_snapshot(self, scan_date) -> list:
        """특정 일자의 (stock_code, market_cap, trading_value) 목록 — 스크리너 유니버스용.

        trading_value 가 비어있으면(0/NULL) close*volume 로 근사한다(일봉 거래대금 표준 근사).
        """
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT stock_code, COALESCE(market_cap,0), "
                    "COALESCE(NULLIF(trading_value,0), close*volume, 0) "
                    "FROM daily_prices WHERE date = %s",
                    (scan_date.strftime("%Y-%m-%d"),),
                )
                rows = cur.fetchall()
                cur.close()
                return [
                    {"stock_code": str(c), "market_cap": float(m or 0), "trading_value": float(t or 0)}
                    for c, m, t in rows
                ]
        except Exception as e:
            self.logger.warning(f"유니버스 스냅샷 조회 실패 ({scan_date}): {e}")
            return []

    def get_latest_daily_price(self, stock_code: str) -> Optional[dict]:
        """최신 일봉 데이터 1건 조회"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # volume 조정은 get_daily_prices 와 동일 규약(최신 행은 adj_factor=1 이라
                # 사실상 무변화지만, 두 경로가 «다른 단위»를 주는 일이 없도록 맞춘다).
                cursor.execute('''
                    SELECT date, open, high, low, close,
                           (volume * COALESCE(adj_factor, 1))::double precision AS volume
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

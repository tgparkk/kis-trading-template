"""
매매 기록 Repository (TimescaleDB)
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import psycopg2

from .base import BaseRepository
from utils.korean_time import now_kst
from utils.rate_limited_logger import RateLimitedLogger


class TradingRepository(BaseRepository):
    """매매 기록 데이터 접근 클래스"""

    # 전략 이름이 아닌 것으로 판단하는 패턴 (매매 사유가 strategy에 들어온 경우 감지)
    _REASON_KEYWORDS = ['매도', '매수', '수익률', '손절', '익절', '청산', '복원', '복구', '조건', '점수']

    def __init__(self, db_path: str = None):
        super().__init__(db_path)
        self.logger = RateLimitedLogger(self.logger)

    def _sanitize_strategy(self, strategy: str) -> str:
        """전략 이름 검증: 매매 사유가 잘못 들어온 경우 'unknown'으로 대체

        순수 전략 이름만 DB strategy 컬럼에 저장되어야 합니다.
        매매 사유(reason)가 strategy에 잘못 전달된 경우를 감지합니다.
        """
        if not strategy or not isinstance(strategy, str):
            return "unknown"
        strategy = strategy.strip()
        if not strategy:
            return "unknown"
        # 매매 사유 키워드가 포함된 경우 → 잘못된 값
        for keyword in self._REASON_KEYWORDS:
            if keyword in strategy:
                self.logger.warning(
                    f"strategy 컬럼에 매매사유가 감지됨 ('{strategy}') → 'unknown'으로 대체"
                )
                return "unknown"
        return strategy

    # ============================
    # 실거래 관련 메서드
    # ============================

    def get_today_real_loss_count(self, stock_code: str) -> int:
        """해당 종목의 오늘 손실 매도 건수"""
        try:
            start_str, next_str = self._get_today_range_strings()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(1) FROM real_trading_records
                    WHERE stock_code = %s AND action = 'SELL'
                      AND profit_loss < 0
                      AND timestamp >= %s AND timestamp < %s
                ''', (stock_code, start_str, next_str))
                row = cursor.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
        except Exception as e:
            self.logger.error(f"실거래 당일 손실 카운트 조회 실패({stock_code}): {e}")
            return 0

    def save_real_buy(self, stock_code: str, stock_name: str, price: float,
                      quantity: int, strategy: str = '', reason: str = '',
                      timestamp: datetime = None) -> Optional[int]:
        """실거래 매수 기록 저장"""
        try:
            strategy = self._sanitize_strategy(strategy)
            if timestamp is None:
                timestamp = now_kst()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO real_trading_records
                    (stock_code, stock_name, action, quantity, price, timestamp, strategy, reason, created_at)
                    VALUES (%s, %s, 'BUY', %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (
                    stock_code, stock_name, quantity, price,
                    timestamp.strftime('%Y-%m-%d %H:%M:%S'), strategy, reason,
                    now_kst().strftime('%Y-%m-%d %H:%M:%S')
                ))
                result = cursor.fetchone()
                rec_id = result[0] if result else None
                self.logger.info(f"실거래 매수 기록 저장: {stock_code} {quantity}주 @{price:,.0f}")
                return rec_id
        except Exception as e:
            self.logger.error(f"실거래 매수 기록 저장 실패: {e}")
            return None

    def save_real_sell(self, stock_code: str, stock_name: str, price: float,
                       quantity: int, strategy: str = '', reason: str = '',
                       buy_record_id: Optional[int] = None, timestamp: datetime = None) -> bool:
        """실거래 매도 기록 저장"""
        try:
            strategy = self._sanitize_strategy(strategy)
            if timestamp is None:
                timestamp = now_kst()

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 평균 매수가 계산
                cursor.execute('''
                    SELECT SUM(b.quantity * b.price) / NULLIF(SUM(b.quantity), 0) as avg_buy_price
                    FROM real_trading_records b
                    WHERE b.stock_code = %s AND b.action = 'BUY'
                      AND NOT EXISTS (
                          SELECT 1 FROM real_trading_records s
                          WHERE s.buy_record_id = b.id AND s.action = 'SELL'
                      )
                ''', (stock_code,))

                avg_result = cursor.fetchone()
                buy_price = float(avg_result[0]) if avg_result and avg_result[0] else None

                if not buy_price and buy_record_id:
                    cursor.execute('SELECT price FROM real_trading_records WHERE id = %s', (buy_record_id,))
                    row = cursor.fetchone()
                    buy_price = float(row[0]) if row else None

                profit_loss = (price - buy_price) * quantity if buy_price else 0.0
                profit_rate = (price - buy_price) / buy_price if buy_price and buy_price > 0 else 0.0

                cursor.execute('''
                    INSERT INTO real_trading_records
                    (stock_code, stock_name, action, quantity, price, timestamp, strategy, reason,
                     profit_loss, profit_rate, buy_record_id, created_at)
                    VALUES (%s, %s, 'SELL', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    stock_code, stock_name, quantity, price,
                    timestamp.strftime('%Y-%m-%d %H:%M:%S'), strategy, reason,
                    profit_loss, profit_rate, buy_record_id,
                    now_kst().strftime('%Y-%m-%d %H:%M:%S')
                ))
                self.logger.info(f"실거래 매도: {stock_code} 손익 {profit_loss:+,.0f}원")
                return True
        except Exception as e:
            self.logger.error(f"실거래 매도 기록 저장 실패: {e}")
            return False

    def get_last_open_real_buy(self, stock_code: str) -> Optional[int]:
        """미매칭 실거래 매수 ID 조회"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT b.id FROM real_trading_records b
                    WHERE b.stock_code = %s AND b.action = 'BUY'
                      AND NOT EXISTS (
                        SELECT 1 FROM real_trading_records s
                        WHERE s.buy_record_id = b.id AND s.action = 'SELL'
                      )
                    ORDER BY b.timestamp DESC LIMIT 1
                ''', (stock_code,))
                row = cursor.fetchone()
                return int(row[0]) if row else None
        except Exception as e:
            self.logger.error(f"실거래 미매칭 매수 조회 실패: {e}")
            return None

    # ============================
    # 가상 매매 관련 메서드
    # ============================

    def save_virtual_buy(self, stock_code: str, stock_name: str, price: float,
                        quantity: int, strategy: str, reason: str,
                        timestamp: datetime = None,
                        target_profit_rate: float = None,
                        stop_loss_rate: float = None) -> Optional[int]:
        """가상 매수 기록 저장"""
        try:
            strategy = self._sanitize_strategy(strategy)
            if timestamp is None:
                timestamp = now_kst()

            quantity = int(quantity)
            price = float(price)
            if target_profit_rate is not None:
                target_profit_rate = float(target_profit_rate)
            if stop_loss_rate is not None:
                stop_loss_rate = float(stop_loss_rate)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                created_at_str = now_kst().strftime('%Y-%m-%d %H:%M:%S')

                cursor.execute('''
                    INSERT INTO virtual_trading_records
                    (stock_code, stock_name, action, quantity, price, timestamp, strategy, reason, is_test,
                     target_profit_rate, stop_loss_rate, created_at)
                    VALUES (%s, %s, 'BUY', %s, %s, %s, %s, %s, true, %s, %s, %s)
                    RETURNING id
                ''', (stock_code, stock_name, quantity, price, timestamp_str,
                      strategy, reason, target_profit_rate, stop_loss_rate, created_at_str))

                result = cursor.fetchone()
                buy_record_id = result[0] if result else None

                self.logger.info(f"가상 매수: {stock_code} {quantity}주 @{price:,.0f}원")
                return buy_record_id

        except Exception as e:
            self.logger.error(f"가상 매수 기록 저장 실패: {e}")
            return None

    def save_virtual_sell(self, stock_code: str, stock_name: str, price: float,
                         quantity: int, strategy: str, reason: str,
                         buy_record_id: int, timestamp: datetime = None) -> bool:
        """가상 매도 기록 저장"""
        try:
            strategy = self._sanitize_strategy(strategy)
            if timestamp is None:
                timestamp = now_kst()

            buy_record_id = int(buy_record_id) if buy_record_id is not None else None
            quantity = int(quantity)
            price = float(price)

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 중복 매도 방지
                if buy_record_id is not None:
                    cursor.execute('''
                        SELECT id FROM virtual_trading_records
                        WHERE buy_record_id = %s AND action = 'SELL'
                    ''', (buy_record_id,))
                    if cursor.fetchone():
                        self.logger.warning(f"{stock_code} 중복 매도 방지")
                        return False

                # 평균 매수가 계산
                cursor.execute('''
                    SELECT SUM(b.quantity * b.price) / NULLIF(SUM(b.quantity), 0)
                    FROM virtual_trading_records b
                    WHERE b.stock_code = %s AND b.action = 'BUY' AND b.is_test = true
                      AND NOT EXISTS (
                          SELECT 1 FROM virtual_trading_records s
                          WHERE s.buy_record_id = b.id AND s.action = 'SELL'
                      )
                ''', (stock_code,))

                avg_result = cursor.fetchone()
                if not avg_result or avg_result[0] is None:
                    cursor.execute('SELECT price FROM virtual_trading_records WHERE id = %s', (buy_record_id,))
                    buy_result = cursor.fetchone()
                    if not buy_result:
                        self.logger.error(f"매수 기록을 찾을 수 없음: ID {buy_record_id}")
                        return False
                    buy_price = float(buy_result[0])
                else:
                    buy_price = float(avg_result[0])

                profit_loss = (price - buy_price) * quantity
                profit_rate = (price - buy_price) / buy_price

                timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                created_at_str = now_kst().strftime('%Y-%m-%d %H:%M:%S')

                try:
                    cursor.execute('''
                        INSERT INTO virtual_trading_records
                        (stock_code, stock_name, action, quantity, price, timestamp, strategy, reason,
                         is_test, profit_loss, profit_rate, buy_record_id, created_at)
                        VALUES (%s, %s, 'SELL', %s, %s, %s, %s, %s, true, %s, %s, %s, %s)
                    ''', (stock_code, stock_name, quantity, price, timestamp_str,
                          strategy, reason, profit_loss, profit_rate, buy_record_id, created_at_str))
                except psycopg2.IntegrityError:
                    conn.rollback()
                    self.logger.warning(f"{stock_code} Race condition 차단")
                    return False
                self.logger.info(f"가상 매도: {stock_code} 손익 {profit_loss:+,.0f}원 ({profit_rate:+.2f}%)")
                return True

        except Exception as e:
            self.logger.error(f"가상 매도 기록 저장 실패: {e}")
            return False

    def get_last_open_virtual_buy(self, stock_code: str, quantity: int = None) -> Optional[int]:
        """미매칭 가상 매수 ID 조회"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                if quantity is None:
                    cursor.execute('''
                        SELECT b.id FROM virtual_trading_records b
                        WHERE b.stock_code = %s AND b.action = 'BUY' AND b.is_test = true
                          AND NOT EXISTS (
                            SELECT 1 FROM virtual_trading_records s
                            WHERE s.buy_record_id = b.id AND s.action = 'SELL'
                          )
                        ORDER BY b.timestamp DESC LIMIT 1
                    ''', (stock_code,))
                else:
                    cursor.execute('''
                        SELECT b.id FROM virtual_trading_records b
                        LEFT JOIN virtual_trading_records s
                            ON b.id = s.buy_record_id AND s.action = 'SELL'
                        WHERE b.stock_code = %s AND b.action = 'BUY' AND b.is_test = true
                        GROUP BY b.id, b.quantity, b.timestamp
                        HAVING b.quantity - COALESCE(SUM(s.quantity), 0) > 0
                        ORDER BY b.timestamp ASC LIMIT 1
                    ''', (stock_code,))

                row = cursor.fetchone()
                return int(row[0]) if row else None
        except Exception as e:
            self.logger.error(f"가상 미매칭 매수 조회 실패: {e}")
            return None

    def get_virtual_open_positions(self) -> pd.DataFrame:
        """미체결 가상 포지션 조회"""
        try:
            with self._get_connection() as conn:
                query = '''
                    SELECT b.id, b.stock_code, b.stock_name, b.quantity,
                           b.price as buy_price, b.timestamp as buy_time,
                           b.strategy, b.reason as buy_reason,
                           b.target_profit_rate, b.stop_loss_rate
                    FROM virtual_trading_records b
                    WHERE b.action = 'BUY' AND b.is_test = true
                        AND NOT EXISTS (
                            SELECT 1 FROM virtual_trading_records s
                            WHERE s.buy_record_id = b.id AND s.action = 'SELL'
                        )
                    ORDER BY b.timestamp DESC
                '''

                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()
                if rows:
                    columns = [desc[0] for desc in cursor.description]
                    df = pd.DataFrame(rows, columns=columns)
                else:
                    df = pd.DataFrame()
                cursor.close()
                if not df.empty and 'buy_time' in df.columns:
                    df['buy_time'] = pd.to_datetime(df['buy_time'], errors='coerce')
                return df

        except Exception as e:
            self.logger.error(f"미체결 포지션 조회 실패: {e}")
            return pd.DataFrame()

    def get_virtual_trading_history(self, days: int = 30, include_open: bool = True) -> pd.DataFrame:
        """가상 매매 이력 조회"""
        try:
            start_date = now_kst() - timedelta(days=days)
            start_timestamp = start_date.strftime('%Y-%m-%d %H:%M:%S')

            with self._get_connection() as conn:
                if include_open:
                    query = '''
                        SELECT id, stock_code, stock_name, action, quantity, price,
                               timestamp, strategy, reason, profit_loss, profit_rate, buy_record_id
                        FROM virtual_trading_records
                        WHERE timestamp >= %s AND is_test = true
                        ORDER BY timestamp DESC
                    '''
                else:
                    query = '''
                        SELECT s.stock_code, s.stock_name,
                               b.price as buy_price, b.timestamp as buy_time, b.reason as buy_reason,
                               s.price as sell_price, s.timestamp as sell_time, s.reason as sell_reason,
                               s.strategy, s.quantity, s.profit_loss, s.profit_rate
                        FROM virtual_trading_records s
                        JOIN virtual_trading_records b ON s.buy_record_id = b.id
                        WHERE s.action = 'SELL' AND s.timestamp >= %s AND s.is_test = true
                        ORDER BY s.timestamp DESC
                    '''

                cursor = conn.cursor()
                cursor.execute(query, (start_timestamp,))
                rows = cursor.fetchall()
                if rows:
                    columns = [desc[0] for desc in cursor.description]
                    df = pd.DataFrame(rows, columns=columns)
                else:
                    df = pd.DataFrame()
                cursor.close()
                return df

        except Exception as e:
            self.logger.error(f"가상 매매 이력 조회 실패: {e}")
            return pd.DataFrame()

    def get_virtual_trading_stats(self, days: int = 30) -> Dict[str, Any]:
        """가상 매매 통계"""
        try:
            completed_trades = self.get_virtual_trading_history(days=days, include_open=False)
            open_positions = self.get_virtual_open_positions()

            stats = {
                'total_trades': len(completed_trades),
                'open_positions': len(open_positions),
                'win_rate': 0, 'total_profit': 0, 'avg_profit_rate': 0,
                'max_profit': 0, 'max_loss': 0, 'strategies': {}
            }

            if not completed_trades.empty:
                winning = completed_trades[completed_trades['profit_loss'] > 0]
                stats['win_rate'] = len(winning) / len(completed_trades) * 100
                stats['total_profit'] = completed_trades['profit_loss'].sum()
                stats['avg_profit_rate'] = completed_trades['profit_rate'].mean()
                stats['max_profit'] = completed_trades['profit_loss'].max()
                stats['max_loss'] = completed_trades['profit_loss'].min()

                for strategy in completed_trades['strategy'].unique():
                    strat_trades = completed_trades[completed_trades['strategy'] == strategy]
                    strat_wins = strat_trades[strat_trades['profit_loss'] > 0]
                    stats['strategies'][strategy] = {
                        'total_trades': len(strat_trades),
                        'win_rate': len(strat_wins) / len(strat_trades) * 100 if len(strat_trades) > 0 else 0,
                        'total_profit': strat_trades['profit_loss'].sum(),
                        'avg_profit_rate': strat_trades['profit_rate'].mean()
                    }

            return stats

        except Exception as e:
            self.logger.error(f"가상 매매 통계 조회 실패: {e}")
            return {}

    def update_open_position_state(
        self,
        buy_record_id: int,
        target_profit_rate: float,
        stop_loss_rate: float,
        is_virtual: bool = True,
    ) -> bool:
        """오픈 포지션 BUY 레코드의 익절/손절률 업데이트 (shutdown flush용)

        재시작 시 state_restorer가 이 값을 읽어 복원하므로 최신값 유지가 중요합니다.
        """
        table = 'virtual_trading_records' if is_virtual else 'real_trading_records'
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f'''
                    UPDATE {table}
                    SET target_profit_rate = %s,
                        stop_loss_rate = %s
                    WHERE id = %s AND action = 'BUY'
                    ''',
                    (float(target_profit_rate), float(stop_loss_rate), int(buy_record_id)),
                )
                updated = cursor.rowcount > 0
            return updated
        except Exception as e:
            self.logger.warning(f"open position 상태 업데이트 실패 (id={buy_record_id}): {e}")
            return False

    def get_losing_stocks(self, days_back: int = 5, min_losses: int = 1) -> set:
        """최근 N영업일 매도 손실 종목 코드 set 반환.

        Args:
            days_back: 과거 영업일 기준 조회 범위 (기본 5영업일)
            min_losses: 손실 매도 최소 횟수 (기본 1회 이상)

        Returns:
            손실 종목 코드 set. DB 실패 시 빈 set 반환.
        """
        try:
            from utils.korean_holidays import count_trading_days_between
            from datetime import timedelta

            # 캘린더 일 수를 늘려 영업일 days_back개를 포함하도록 넉넉하게 계산
            # 영업일 1개 ≒ 캘린더 1.4일 → 2배 마진 적용
            lookback_calendar_days = days_back * 2 + 5
            cutoff_dt = now_kst() - timedelta(days=lookback_calendar_days)
            cutoff_str = cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT stock_code, COUNT(1) as loss_count
                    FROM virtual_trading_records
                    WHERE action = 'SELL'
                      AND profit_loss < 0
                      AND timestamp >= %s
                    GROUP BY stock_code
                    HAVING COUNT(1) >= %s
                ''', (cutoff_str, min_losses))
                rows = cursor.fetchall()
                return {row[0] for row in rows}
        except Exception as e:
            self.logger.error(f"최근 손실 종목 조회 실패: {e}")
            return set()

    def get_persistently_failed_stocks(self, consecutive_losses: int = 3) -> set:
        """연속 N회 손실 종목 코드 set 반환 (영구 블랙리스트 대상).

        매도 이력을 시간순 정렬 후 마지막 consecutive_losses건이 모두 손실인 종목.

        Args:
            consecutive_losses: 연속 손실 판단 기준 횟수 (기본 3회)

        Returns:
            연속 손실 종목 코드 set. DB 실패 시 빈 set 반환.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 종목별 최근 consecutive_losses건 매도 이력 조회
                cursor.execute('''
                    SELECT DISTINCT stock_code FROM virtual_trading_records
                    WHERE action = 'SELL'
                ''')
                all_codes = [row[0] for row in cursor.fetchall()]

                persistent: set = set()
                for code in all_codes:
                    cursor.execute('''
                        SELECT profit_loss FROM virtual_trading_records
                        WHERE stock_code = %s AND action = 'SELL'
                        ORDER BY timestamp DESC
                        LIMIT %s
                    ''', (code, consecutive_losses))
                    recent = cursor.fetchall()
                    if len(recent) < consecutive_losses:
                        continue
                    if all(row[0] < 0 for row in recent):
                        persistent.add(code)

                return persistent
        except Exception as e:
            self.logger.error(f"연속 손실 종목 조회 실패: {e}")
            return set()

    def get_today_stop_loss_stocks(self, target_date: str = None) -> List[str]:
        """오늘 손절한 종목 코드 리스트"""
        try:
            if target_date is None:
                target_date = now_kst().strftime('%Y-%m-%d')

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT stock_code FROM virtual_trading_records
                    WHERE action = 'SELL'
                      AND DATE(timestamp) = %s
                      AND (reason LIKE '%%손절%%' OR reason LIKE '%%stop%%loss%%')
                ''', (target_date,))

                result = cursor.fetchall()
                return [row[0] for row in result]

        except Exception as e:
            self.logger.error(f"손절 종목 조회 실패: {e}")
            return []

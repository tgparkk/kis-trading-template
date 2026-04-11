"""
사와카미 전략 DB 매니저
======================

PostgreSQL(strategy_analysis)에 매수후보/매매 기록을 영속화.
DB 연결 실패 시에도 전략은 계속 동작 (graceful fallback).
"""

import logging
import os
from datetime import datetime, date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False
    logger.warning("psycopg2 미설치 — DB 영속화 비활성화")


class SawkamiDBManager:
    """사와카미 전략 DB CRUD"""

    def __init__(self):
        self._conn_params = dict(
            host=os.getenv('STRATEGY_DB_HOST', os.getenv('TIMESCALE_HOST', '172.23.208.1')),
            port=int(os.getenv('STRATEGY_DB_PORT', os.getenv('TIMESCALE_PORT', 5433))),
            user=os.getenv('STRATEGY_DB_USER', os.getenv('TIMESCALE_USER', 'postgres')),
            password=os.getenv('STRATEGY_DB_PASSWORD', os.getenv('TIMESCALE_PASSWORD', '')),
            dbname=os.getenv('STRATEGY_DB_NAME', 'strategy_analysis'),
        )
        self._conn = None

    # ========================================================================
    # Connection
    # ========================================================================

    def _get_conn(self):
        """연결 획득 (lazy, 끊어지면 재연결)"""
        if not HAS_PSYCOPG2:
            return None
        try:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg2.connect(**self._conn_params)
                self._conn.autocommit = True
            return self._conn
        except Exception as e:
            logger.error(f"DB 연결 실패: {e}")
            return None

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    # ========================================================================
    # Candidates (매수후보)
    # ========================================================================

    def save_candidates(self, scan_date: date, candidates: List[Dict]) -> int:
        """스크리닝 결과 저장 (upsert). 저장 건수 반환."""
        conn = self._get_conn()
        if not conn:
            return 0
        try:
            cur = conn.cursor()
            sql = """
                INSERT INTO sawkami_candidates
                    (scan_date, stock_code, stock_name, score,
                     op_income_growth, pbr, rsi, drop_from_high,
                     volume_ratio, close_price)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (scan_date, stock_code)
                DO UPDATE SET score=EXCLUDED.score, op_income_growth=EXCLUDED.op_income_growth,
                    pbr=EXCLUDED.pbr, rsi=EXCLUDED.rsi, drop_from_high=EXCLUDED.drop_from_high,
                    volume_ratio=EXCLUDED.volume_ratio, close_price=EXCLUDED.close_price,
                    stock_name=EXCLUDED.stock_name
            """
            count = 0
            for c in candidates:
                cur.execute(sql, (
                    scan_date, c.get('stock_code', ''), c.get('stock_name', ''),
                    c.get('score'), c.get('op_income_growth'), c.get('pbr'),
                    c.get('rsi'), c.get('drop_from_high'), c.get('volume_ratio'),
                    c.get('close_price'),
                ))
                count += 1
            logger.info(f"매수후보 {count}건 저장 (scan_date={scan_date})")
            return count
        except Exception as e:
            logger.error(f"매수후보 저장 실패: {e}")
            return 0

    def get_candidates(self, scan_date: date) -> List[Dict]:
        """특정 날짜 매수후보 조회 (score 내림차순)"""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM sawkami_candidates WHERE scan_date=%s ORDER BY score DESC",
                (scan_date,)
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"매수후보 조회 실패: {e}")
            return []

    # ========================================================================
    # Trades (매매)
    # ========================================================================

    def open_trade(self, stock_code: str, stock_name: str,
                   buy_date: datetime, buy_price: float,
                   buy_quantity: int, buy_reason: str = "") -> Optional[int]:
        """매수 기록. trade id 반환."""
        conn = self._get_conn()
        if not conn:
            return None
        try:
            cur = conn.cursor()
            buy_amount = buy_price * buy_quantity
            cur.execute("""
                INSERT INTO sawkami_trades
                    (stock_code, stock_name, status, buy_date, buy_price,
                     buy_quantity, buy_amount, buy_reason)
                VALUES (%s, %s, 'HOLDING', %s, %s, %s, %s, %s)
                RETURNING id
            """, (stock_code, stock_name, buy_date, buy_price,
                  buy_quantity, buy_amount, buy_reason))
            trade_id = cur.fetchone()[0]
            logger.info(f"매수 기록: {stock_name}({stock_code}) "
                        f"@ {buy_price:,.0f} x {buy_quantity} (id={trade_id})")
            return trade_id
        except Exception as e:
            logger.error(f"매수 기록 실패: {e}")
            return None

    def close_trade(self, stock_code: str, sell_date: datetime,
                    sell_price: float, sell_reason: str = "") -> bool:
        """매도 기록. HOLDING → CLOSED, PNL 자동 계산."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            # 가장 오래된 HOLDING 포지션부터 청산 (FIFO)
            cur.execute("""
                SELECT id, buy_price, buy_quantity, buy_date
                FROM sawkami_trades
                WHERE stock_code=%s AND status='HOLDING'
                ORDER BY buy_date ASC LIMIT 1
            """, (stock_code,))
            row = cur.fetchone()
            if not row:
                logger.warning(f"매도 대상 없음: {stock_code}")
                return False

            trade_id, buy_price, buy_qty, buy_dt = row
            sell_amount = sell_price * buy_qty
            pnl_amount = sell_amount - (buy_price * buy_qty)
            pnl_pct = (sell_price - buy_price) / buy_price * 100 if buy_price else 0
            hold_days = (sell_date - buy_dt).days if buy_dt else 0

            cur.execute("""
                UPDATE sawkami_trades SET
                    status='CLOSED', sell_date=%s, sell_price=%s,
                    sell_amount=%s, sell_reason=%s,
                    pnl_amount=%s, pnl_pct=%s, hold_days=%s,
                    updated_at=NOW()
                WHERE id=%s
            """, (sell_date, sell_price, sell_amount, sell_reason,
                  pnl_amount, pnl_pct, hold_days, trade_id))
            logger.info(f"매도 기록: {stock_code} @ {sell_price:,.0f} "
                        f"(PNL {pnl_pct:+.1f}%, {sell_reason})")
            return True
        except Exception as e:
            logger.error(f"매도 기록 실패: {e}")
            return False

    def get_holding_positions(self) -> List[Dict]:
        """현재 보유 포지션 조회 (재시작 복원용)"""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT stock_code, stock_name, buy_date, buy_price, buy_quantity
                FROM sawkami_trades WHERE status='HOLDING'
                ORDER BY buy_date
            """)
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"보유 포지션 조회 실패: {e}")
            return []

    def get_trade_history(self, start_date: date = None,
                         end_date: date = None) -> List[Dict]:
        """매매 이력 조회"""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            sql = "SELECT * FROM sawkami_trades WHERE 1=1"
            params = []
            if start_date:
                sql += " AND buy_date >= %s"
                params.append(start_date)
            if end_date:
                sql += " AND buy_date <= %s"
                params.append(end_date)
            sql += " ORDER BY buy_date DESC"
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"매매 이력 조회 실패: {e}")
            return []

    def get_daily_pnl(self, target_date: date) -> float:
        """일일 실현손익 합계"""
        conn = self._get_conn()
        if not conn:
            return 0.0
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT COALESCE(SUM(pnl_amount), 0)
                FROM sawkami_trades
                WHERE status='CLOSED' AND DATE(sell_date)=%s
            """, (target_date,))
            return float(cur.fetchone()[0])
        except Exception as e:
            logger.error(f"일일 PNL 조회 실패: {e}")
            return 0.0

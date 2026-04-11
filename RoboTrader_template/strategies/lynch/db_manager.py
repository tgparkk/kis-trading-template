"""
Lynch 전략 DB 매니저
====================

PostgreSQL(strategy_analysis)에 lynch_trades 테이블 자동 생성 및 CRUD.
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


class LynchDBManager:
    """Lynch 전략 DB CRUD"""

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS lynch_trades (
        id SERIAL PRIMARY KEY,
        stock_code VARCHAR(10) NOT NULL,
        stock_name VARCHAR(100) DEFAULT '',
        status VARCHAR(10) DEFAULT 'HOLDING',
        buy_date TIMESTAMP,
        buy_price NUMERIC(12,2),
        buy_quantity INTEGER,
        buy_amount NUMERIC(14,2),
        buy_reason TEXT DEFAULT '',
        sell_date TIMESTAMP,
        sell_price NUMERIC(12,2),
        sell_amount NUMERIC(14,2),
        sell_reason VARCHAR(20) DEFAULT '',
        pnl_amount NUMERIC(14,2),
        pnl_pct NUMERIC(8,4),
        hold_days INTEGER,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """

    def __init__(self):
        self._conn_params = dict(
            host=os.getenv('STRATEGY_DB_HOST', os.getenv('TIMESCALE_HOST', '172.23.208.1')),
            port=int(os.getenv('STRATEGY_DB_PORT', os.getenv('TIMESCALE_PORT', 5433))),
            user=os.getenv('STRATEGY_DB_USER', os.getenv('TIMESCALE_USER', 'postgres')),
            password=os.getenv('STRATEGY_DB_PASSWORD', os.getenv('TIMESCALE_PASSWORD', '')),
            dbname=os.getenv('STRATEGY_DB_NAME', 'strategy_analysis'),
        )
        self._conn = None
        self._ensure_table()

    def _get_conn(self):
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

    def _ensure_table(self):
        conn = self._get_conn()
        if not conn:
            return
        try:
            cur = conn.cursor()
            cur.execute(self.CREATE_TABLE_SQL)
            logger.info("lynch_trades 테이블 확인/생성 완료")
        except Exception as e:
            logger.error(f"테이블 생성 실패: {e}")

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    def open_trade(self, stock_code: str, stock_name: str,
                   buy_date: datetime, buy_price: float,
                   buy_quantity: int, buy_reason: str = "") -> Optional[int]:
        conn = self._get_conn()
        if not conn:
            return None
        try:
            cur = conn.cursor()
            buy_amount = buy_price * buy_quantity
            cur.execute("""
                INSERT INTO lynch_trades
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
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, buy_price, buy_quantity, buy_date
                FROM lynch_trades
                WHERE stock_code=%s AND status='HOLDING'
                ORDER BY buy_date ASC LIMIT 1
            """, (stock_code,))
            row = cur.fetchone()
            if not row:
                return False

            trade_id, buy_price, buy_qty, buy_dt = row
            sell_amount = sell_price * buy_qty
            pnl_amount = sell_amount - (buy_price * buy_qty)
            pnl_pct = (sell_price - buy_price) / buy_price * 100 if buy_price else 0
            hold_days = (sell_date - buy_dt).days if buy_dt else 0

            cur.execute("""
                UPDATE lynch_trades SET
                    status='CLOSED', sell_date=%s, sell_price=%s,
                    sell_amount=%s, sell_reason=%s,
                    pnl_amount=%s, pnl_pct=%s, hold_days=%s,
                    updated_at=NOW()
                WHERE id=%s
            """, (sell_date, sell_price, sell_amount, sell_reason,
                  pnl_amount, pnl_pct, hold_days, trade_id))
            return True
        except Exception as e:
            logger.error(f"매도 기록 실패: {e}")
            return False

    def get_holding_positions(self) -> List[Dict]:
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT stock_code, stock_name, buy_date, buy_price, buy_quantity
                FROM lynch_trades WHERE status='HOLDING'
                ORDER BY buy_date
            """)
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"보유 포지션 조회 실패: {e}")
            return []

"""minute_candles 로더 (읽기전용)."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Dict, Optional

import pandas as pd
import psycopg2


@contextmanager
def _conn():
    c = psycopg2.connect(host=os.getenv("TIMESCALE_HOST", "localhost"),
                         port=int(os.getenv("TIMESCALE_PORT", 5433)),
                         dbname="robotrader", user=os.getenv("TIMESCALE_USER", "robotrader"),
                         password=os.getenv("TIMESCALE_PASSWORD", "1234"))
    try:
        yield c
    finally:
        c.close()


def _norm(date: str) -> str:
    return date.replace("-", "") if "-" in date else date


def load_intraday_by_date(stock_code: str, trade_date: str) -> Optional[pd.DataFrame]:
    td = _norm(trade_date)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT time, open, high, low, close, volume, amount FROM minute_candles "
                    "WHERE stock_code=%s AND trade_date=%s ORDER BY datetime", (stock_code, td))
        rows = cur.fetchall()
    if not rows:
        return None
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume", "amount"])


def load_intraday_supplier(stock_code: str) -> Dict[str, pd.DataFrame]:
    """{ 'YYYY-MM-DD' -> 분봉df } 전체. trade_sim 의 intraday_by_date 로 사용."""
    with _conn() as conn:
        df = pd.read_sql(
            "SELECT trade_date, time, open, high, low, close, volume, amount "
            "FROM minute_candles WHERE stock_code=%s ORDER BY datetime", conn, params=(stock_code,))
    out: Dict[str, pd.DataFrame] = {}
    if len(df) == 0:
        return out
    for td, g in df.groupby("trade_date"):
        iso = f"{td[:4]}-{td[4:6]}-{td[6:8]}"
        out[iso] = g.drop(columns=["trade_date"]).reset_index(drop=True)
    return out


def covered_stock_dates() -> Dict[str, int]:
    """{ stock_code -> 분봉 보유 거래일수 } (커버 종목 식별용)."""
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT stock_code, count(distinct trade_date) FROM minute_candles GROUP BY stock_code")
        return {str(s): int(n) for s, n in cur.fetchall()}

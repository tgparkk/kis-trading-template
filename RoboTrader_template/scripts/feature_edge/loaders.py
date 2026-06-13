"""실데이터 공급자 로더 (읽기전용). 단위테스트는 가짜 공급자, 여기는 통합경로."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Dict, List

import pandas as pd

from db.quant_daily_reader import QuantDailyReader
from scripts.feature_edge import config


@contextmanager
def _conn(dbname: str):
    import psycopg2
    c = psycopg2.connect(
        host=os.getenv("TIMESCALE_HOST", "localhost"),
        port=int(os.getenv("TIMESCALE_PORT", 5433)),
        dbname=dbname, user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"))
    try:
        yield c
    finally:
        c.close()


def load_universe(scan_date: str) -> List[str]:
    rows = QuantDailyReader().get_universe_snapshot(scan_date)
    return [r["stock_code"] for r in rows
            if r["trading_value"] >= config.UNIVERSE_MIN_TRADING_VALUE]


def load_daily_supplier(codes: List[str], end_date: str, days: int = 1500
                        ) -> Dict[str, pd.DataFrame]:
    r = QuantDailyReader()
    out = {}
    for c in codes:
        df = r.get_daily_prices(c, end_date=end_date, days=days)
        if len(df):
            out[c] = df
    return out


def load_flow_supplier(codes: List[str]) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    with _conn("robotrader_quant") as conn:
        cur = conn.cursor()
        for c in codes:
            cur.execute("SELECT date, foreign_net_vol FROM foreign_flow "
                        "WHERE stock_code=%s ORDER BY date", (c,))
            rows = cur.fetchall()
            if rows:
                out[c] = pd.DataFrame(rows, columns=["date", "foreign_net_vol"])
    return out


def load_event_supplier(codes: List[str]) -> Dict[str, list]:
    out: Dict[str, list] = {}
    with _conn("robotrader") as conn:
        cur = conn.cursor()
        for c in codes:
            cur.execute("SELECT event_date, event_type FROM corp_events "
                        "WHERE stock_code=%s", (c,))
            ev = [(pd.Timestamp(d), t) for d, t in cur.fetchall()]
            if ev:
                out[c] = ev
    return out


def load_index_df(stock_code: str = "KOSPI") -> pd.DataFrame:
    """지수 일봉 (robotrader.daily_prices, stock_code='KOSPI'). date,close 오름차순."""
    with _conn("robotrader") as conn:
        cur = conn.cursor()
        cur.execute("SELECT date, close FROM daily_prices "
                    "WHERE stock_code=%s ORDER BY date", (stock_code,))
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame({"date": [], "close": []})
    df = pd.DataFrame(rows, columns=["date", "close"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna().sort_values("date").reset_index(drop=True)

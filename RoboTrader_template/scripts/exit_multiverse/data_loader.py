"""유니버스·일봉·KOSPI 종가 로더. 기존 run_*.py 의 _load_* 를 재사용."""
from __future__ import annotations
import logging
from typing import Dict, List
import pandas as pd

LOG = logging.getLogger("exit_multiverse.data_loader")


def load_top_volume_universe(start: str, end: str, top_n: int = 50) -> List[str]:
    """daily_prices 거래대금(close*volume) 합계 상위 N종목 코드."""
    # run_elder_triple_screen.py:44-58 그대로 복제
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM daily_prices
            WHERE date >= %s AND date <= %s
            GROUP BY stock_code
            ORDER BY turnover DESC, stock_code ASC
            LIMIT %s
        """, (start, end, top_n))
        rows = cur.fetchall()
    return [r[0] for r in rows]


def load_daily_adj(stock_codes: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    """종목별 daily_prices 로드 (adj_factor 수정주가 적용 + OHLC 결손 보정). 30봉 미만 종목 제외."""
    # run_elder_triple_screen.py:61-101 그대로 복제 (adj_factor 적용 + OHLC 결손 보정)
    from db.connection import DatabaseConnection
    out: Dict[str, pd.DataFrame] = {}
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        for code in stock_codes:
            cur.execute("""
                SELECT date, open, high, low, close, volume, adj_factor
                FROM daily_prices
                WHERE stock_code = %s AND date >= %s AND date <= %s
                ORDER BY date ASC
            """, (code, start, end))
            rows = cur.fetchall()
            if not rows or len(rows) < 30:
                continue
            df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "adj_factor"])
            df["date"] = pd.to_datetime(df["date"])
            for col in ["open", "high", "low", "close", "volume", "adj_factor"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["adj_factor"] = df["adj_factor"].fillna(1.0)
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col] * df["adj_factor"]
            drop_mask = df["close"].isna() | (df["close"] <= 0)
            df = df[~drop_mask].copy()
            for col in ["open", "high", "low"]:
                fill_mask = df[col].isna() | (df[col] <= 0)
                df.loc[fill_mask, col] = df.loc[fill_mask, "close"]
            df = df.dropna(subset=["open", "high", "low", "close"])
            df["datetime"] = df["date"]
            out[code] = df[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    return out


def load_turnover_rank(start: str, end: str) -> Dict[str, float]:
    """종목별 거래대금 합계 (진입 우선순위 정렬용)."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM daily_prices
            WHERE date >= %s AND date <= %s
            GROUP BY stock_code
        """, (start, end))
        rows = cur.fetchall()
    if not rows:
        raise RuntimeError("daily_prices에 거래대금 데이터가 없음")
    return {r[0]: float(r[1]) for r in rows}


def load_kospi_close(start: str, end: str) -> pd.Series:
    """daily_prices 의 KOSPI 지수 종가 (국면 라벨용). regime_split_*.py 와 동일 소스."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT date, close FROM daily_prices "
            "WHERE stock_code = 'KOSPI' AND date >= %s AND date <= %s ORDER BY date ASC",
            (start, end),
        )
        rows = cur.fetchall()
    if not rows:
        raise RuntimeError("daily_prices에 KOSPI 행이 없음")
    return pd.Series({pd.Timestamp(r[0]): float(r[1]) for r in rows}, name="kospi").sort_index()

"""태쏘 4차 검정 랩 — 데이터 로딩과 가드.

⚠️ 라이브 트리에서 실행 금지. 이 파일은 scratchpad 랩에만 둔다.
"""
from __future__ import annotations

import sys

import pandas as pd
import psycopg2

REPO = r"D:\GIT\kis-trading-template\RoboTrader_template"
if REPO not in sys.path:
    sys.path.insert(0, REPO)
from config.constants import resolve_daily_source_db  # noqa: E402
from lib.universe_filter import SQL_STOCK_ONLY  # noqa: E402

PG = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234")
OHLC = ("open", "high", "low", "close")

# 🔴 SQL_STOCK_ONLY 필수 — daily_prices 에는 지수 행(KOSPI·KOSDAQ·KS11·KQ11)이
#    종목처럼 섞여 있다. 전 패널을 그대로 로드하면 종목 수가 과대집계되고
#    거래대금·수익률 횡단면 순위가 지수에 오염된다. → lib/universe_filter.py
DAILY_SQL = f"""
    select stock_code, date, open, high, low, close,
           volume, trading_value, market_cap
    from daily_prices
    where date >= %s and date <= %s
      and {SQL_STOCK_ONLY}
    order by stock_code, date
"""


def _conn():
    return psycopg2.connect(dbname=resolve_daily_source_db(), **PG)


def drop_bad_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """OHLC 중 하나라도 0 이하이거나 NaN 이면 행을 버린다.

    close 만 검사하면 open=high=low=0 인 18,147행이 살아남아
    체결 시뮬에서 0 나누기로 결과를 파괴한다.
    """
    bad = df[list(OHLC)].isna().any(axis=1)
    for col in OHLC:
        bad = bad | (df[col] <= 0)
    return df.loc[~bad].reset_index(drop=True)


def load_daily(start: str, end: str) -> pd.DataFrame:
    """일봉 로딩. adj_factor 는 읽지 않는다.

    close 는 이미 분할조정 연속시세이므로 adj_factor 를 곱하면 분할일에
    가짜 절벽이 생기고, 그 절벽이 거짓 MaxDD 로 이어진다.
    """
    with _conn() as conn:
        df = pd.read_sql(DAILY_SQL, conn, params=(start, end))
    return drop_bad_ohlc(df)

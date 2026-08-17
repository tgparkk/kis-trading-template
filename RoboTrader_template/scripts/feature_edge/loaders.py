"""실데이터 공급자 로더 (읽기전용). 단위테스트는 가짜 공급자, 여기는 통합경로."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Dict, List

import pandas as pd

from config.constants import resolve_corp_events_source_db, resolve_daily_source_db
from db.quant_daily_reader import QuantDailyReader
from scripts.feature_edge import config


@contextmanager
def _conn(dbname: str):
    # ⚠️ user 의 'robotrader' 는 **롤명**이라 그대로 둔다(DB명과 동음이의).
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
    """외국인 순매수 — 🔴 **여기만 아직 하드코딩 `robotrader_quant`**.

    🔑 이 모듈은 2026-08-17 이후 「반쯤 살아 있는」 상태다: corp_events·지수 일봉은
      resolver(=kis_template)로 옮겼는데 이 함수만 **동결 레거시**(2026-07-10 동결)를
      읽는다. `robotrader_quant` 는 이번 `robotrader` 폐기 대상이 «아니라» 손대지
      않았을 뿐이며, 정상 상태라는 뜻이 아니다.
      ⇒ 같은 러너 안에서 **이벤트·지수는 최신 / 수급은 2026-07-10 에서 멈춘 값**이
        섞인다. 수급 축을 쓰는 결론은 그 사실을 명시할 것.
        (`foreign_flow` 를 kis_template 로 이관하는 건 별건이다.)
    """
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
    """기업이벤트 — 2026-08-17: 하드코딩 `"robotrader"` → resolver 경유.

    그 DB 는 2026-07-10 동결 레거시이고 **삭제 예정**이라, 두면 DROP 즉시 이
    경로(run_edge_lab.py · portfolio_backtest.py)가 죽는다.
    """
    out: Dict[str, list] = {}
    with _conn(resolve_corp_events_source_db()) as conn:
        cur = conn.cursor()
        for c in codes:
            cur.execute("SELECT event_date, event_type FROM corp_events "
                        "WHERE stock_code=%s", (c,))
            ev = [(pd.Timestamp(d), t) for d, t in cur.fetchall()]
            if ev:
                out[c] = ev
    return out


def load_index_df(stock_code: str = "KOSPI") -> pd.DataFrame:
    """지수 일봉 (`daily_prices`, stock_code='KOSPI'). date,close 오름차순.

    2026-08-17: 하드코딩 `"robotrader"` → **일봉 resolver** 경유. 옛 문구
    「robotrader.daily_prices」는 폐기 예정 DB 를 가리키고 있었다.
    """
    with _conn(resolve_daily_source_db()) as conn:
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

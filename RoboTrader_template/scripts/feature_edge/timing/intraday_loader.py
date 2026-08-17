"""minute_candles 로더 (읽기전용).

대상 DB: ``resolve_minute_source_db()`` = 분봉 SSOT(kis_template). env 불필요.

2026-08-17 — 하드코딩 `dbname="robotrader"` 를 걷어냈다. 그 DB 는 2026-07-10
동결 레거시이고 **삭제 예정**이다.

🔑 같은 날 한 번 `require_explicit_target_db`(TIMESCALE_DB 명시 필수)로 갔다가
  **되돌렸다**. 그 판단이 틀렸던 이유 셋:
    1) 여긴 **읽기 전용** 로더다. fail-fast 의 근거는 「실수로 라이브에 «쓰기»」인데
       읽기는 SSOT 를 오염시킬 수 없다 — 근거가 성립하지 않는다.
    2) ``TIMESCALE_DB`` 는 **라이브 운영 env**(gitignore 된 `.env` 전용)다. 연구
       읽기 경로가 이걸 요구하면 2026-07-16 통일이 고친 「연구가 라이브 env 를
       필요로 함」 상태가 그대로 되살아난다(clean checkout·워크트리·CI 에서 중단).
    3) 같은 커밋이 테스트(tests/test_minute_loader.py)에선 이미 resolver 를 썼다 —
       프로덕션과 테스트가 같은 일에 다른 관용구를 쓰고 있었다.
  ⇒ 「DB명 하드코딩 금지, 반드시 resolver 경유」라는 프로젝트 SSOT 규칙 그대로 간다.
  (쓰기 스크립트의 fail-fast 는 그대로 유효하다 — 그건 «쓰기»에 붙어야 한다.)
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Dict, Optional

import pandas as pd
import psycopg2

from config.constants import resolve_minute_source_db


@contextmanager
def _conn():
    # ⚠️ user 의 'robotrader' 는 **롤명**이라 그대로 둔다(DB명과 동음이의).
    #    해석은 import 시점이 아니라 «연결 시점»에 한다(몽키패치 가능해야 한다).
    c = psycopg2.connect(host=os.getenv("TIMESCALE_HOST", "localhost"),
                         port=int(os.getenv("TIMESCALE_PORT", 5433)),
                         dbname=resolve_minute_source_db(),
                         user=os.getenv("TIMESCALE_USER", "robotrader"),
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

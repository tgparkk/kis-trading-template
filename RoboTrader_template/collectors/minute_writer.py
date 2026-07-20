# collectors/minute_writer.py
"""분봉 df → minute_candles 행 + 새 DB 멱등 적재(DELETE+INSERT)."""
import pandas as pd

from utils.logger import setup_logger

logger = setup_logger(__name__)

_INSERT = """
INSERT INTO minute_candles
    (stock_code, trade_date, idx, date, time, close, open, high, low, volume, amount, datetime)
VALUES (%(stock_code)s, %(trade_date)s, %(idx)s, %(date)s, %(time)s, %(close)s, %(open)s,
        %(high)s, %(low)s, %(volume)s, %(amount)s, %(datetime)s)
ON CONFLICT (stock_code, datetime) DO NOTHING
"""


def df_to_minute_rows(code: str, df) -> list:
    if df is None or len(df) == 0:
        return []
    rows = []
    for idx, (_, r) in enumerate(df.iterrows()):
        d = str(r.get("date", ""))
        dt = r.get("datetime")
        # datetime 은 봉의 자연키 — ON CONFLICT (stock_code, datetime) 와 UNIQUE
        # 인덱스가 NULL 을 서로 distinct 로 취급하므로, 키 없는(NaT/누락) 봉을
        # 적재하면 영구 DB-레벨 dedup 보장에 구멍이 난다. 실측 0건이지만
        # 미래 malformed fetch 를 fail-fast 하도록 스킵 + 경고(조용한 드롭 금지).
        if not isinstance(dt, pd.Timestamp) or pd.isna(dt):
            logger.warning(
                "[minute_writer] datetime 누락/무효 봉 스킵: stock_code=%s date=%s time=%s datetime=%r",
                code, d, str(r.get("time", "")), dt,
            )
            continue
        rows.append({
            "stock_code": code,
            "trade_date": d,
            "idx": idx,
            "date": d,
            "time": str(r.get("time", "")),
            "close": float(r.get("close", 0) or 0),
            "open": float(r.get("open", 0) or 0),
            "high": float(r.get("high", 0) or 0),
            "low": float(r.get("low", 0) or 0),
            "volume": float(r.get("volume", 0) or 0),
            "amount": float(r.get("amount", 0) or 0),
            "datetime": dt.to_pydatetime(),
        })
    return rows


def replace_minute_day(conn, code: str, trade_date: str, rows) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM minute_candles WHERE stock_code=%s AND trade_date=%s",
                    (code, trade_date))
        for r in rows:
            cur.execute(_INSERT, r)
    conn.commit()
    return len(rows)

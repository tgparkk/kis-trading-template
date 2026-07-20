# collectors/minute_writer.py
"""분봉 df → minute_candles 행 + 새 DB 멱등 적재(DELETE+INSERT)."""
import pandas as pd

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
            "datetime": (dt.to_pydatetime() if isinstance(dt, pd.Timestamp) else None),
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

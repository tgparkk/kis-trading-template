"""FDR 지수 df → index_daily 행 + 새 DB UPSERT."""

_UPSERT = """
INSERT INTO index_daily (index_code, date, open, high, low, close, volume)
VALUES (%(index_code)s, %(date)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s)
ON CONFLICT (index_code, date) DO UPDATE SET
    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
    close=EXCLUDED.close, volume=EXCLUDED.volume
"""


def fdr_df_to_index_rows(index_code: str, df) -> list:
    if df is None or len(df) == 0:
        return []
    rows = []
    for idx, r in df.iterrows():
        d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        rows.append({
            "index_code": index_code, "date": d,
            "open": float(r["Open"]), "high": float(r["High"]),
            "low": float(r["Low"]), "close": float(r["Close"]),
            "volume": float(r.get("Volume", 0) or 0),
        })
    return rows


def upsert_index_rows(conn, rows) -> int:
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(_UPSERT, r)
    conn.commit()
    return len(rows)

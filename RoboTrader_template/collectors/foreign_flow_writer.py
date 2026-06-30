"""네이버 외국인 순매매량 df → foreign_flow 행 + 새 DB UPSERT."""
import pandas as pd

_UPSERT = """
INSERT INTO foreign_flow (stock_code, date, foreign_net_vol, source)
VALUES (%(stock_code)s, %(date)s, %(foreign_net_vol)s, %(source)s)
ON CONFLICT (stock_code, date) DO UPDATE SET
    foreign_net_vol=EXCLUDED.foreign_net_vol, source=EXCLUDED.source
"""


def naver_df_to_rows(code: str, df) -> list:
    """fetch_foreign_naver 결과(date, foreign_net_vol) → 행 dict 리스트.

    foreign_net_vol 이 NaN 이면 None 으로(레거시 backfill 과 동일 의미).
    """
    if df is None or len(df) == 0:
        return []
    rows = []
    for _, r in df.iterrows():
        vol = r["foreign_net_vol"]
        vol = int(vol) if pd.notna(vol) else None
        rows.append({
            "stock_code": code,
            "date": r["date"],
            "foreign_net_vol": vol,
            "source": "naver",
        })
    return rows


def upsert_foreign_rows(conn, rows) -> int:
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(_UPSERT, r)
    conn.commit()
    return len(rows)

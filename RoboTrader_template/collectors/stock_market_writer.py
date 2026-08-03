"""FDR 상장목록 df → stock_market 행 + UPSERT.

시장 라벨의 유일한 소스다. `stock_list.json`·`stock_sector` 의 market 필드는
전부 "KOSPI" 로 오염돼 있으므로 폴백으로도 쓰지 않는다(2026-08-03 실측).
"""

_UPSERT = """
INSERT INTO stock_market (stock_code, market)
VALUES (%(stock_code)s, %(market)s)
ON CONFLICT (stock_code) DO UPDATE SET
    market=EXCLUDED.market, updated_at=now()
"""


def fdr_df_to_market_rows(market: str, df) -> list:
    if df is None or len(df) == 0:
        return []
    rows = []
    for _, r in df.iterrows():
        raw = r.get("Code")
        if raw is None:
            continue
        code = str(raw).strip()
        if not code or code.lower() == "nan":
            continue
        rows.append({"stock_code": code.zfill(6), "market": market})
    return rows


def upsert_market_rows(conn, rows) -> int:
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(_UPSERT, r)
    conn.commit()
    return len(rows)

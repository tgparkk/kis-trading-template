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

_COUNT_BY_MARKET = "SELECT market, count(*) FROM stock_market GROUP BY market"


def current_market_counts(conn) -> dict:
    """현재 적재된 시장별 행수. 규모 하한 검증의 기준값이다.

    테이블이 비어 있으면 빈 dict — 호출측이 "최초 수집"으로 판정해 하한을
    적용하지 않는다(하한을 무조건 걸면 첫 수집이 영원히 불가능해진다).
    """
    with conn.cursor() as cur:
        cur.execute(_COUNT_BY_MARKET)
        return {str(m): int(n) for m, n in cur.fetchall()}


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

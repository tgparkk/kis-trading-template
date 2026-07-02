# collectors/daily_derived.py
"""파생(returns/volatility) 갱신 — 검증된 SQL_UPDATE_RETURNS 재사용, 새 DB 대상 실행."""

# returns / volatility 전체 재계산 (멱등 - 윈도우 함수 결과는 항상 동일)
SQL_UPDATE_RETURNS = """
WITH base AS (
    SELECT
        stock_code,
        date,
        close,
        LAG(close, 1)  OVER w AS prev_close_1,
        LAG(close, 5)  OVER w AS prev_close_5,
        LAG(close, 20) OVER w AS prev_close_20,
        LAG(close, 1)  OVER w AS lag1_for_vol,
        close          AS cur_for_vol
    FROM daily_prices
    WINDOW w AS (PARTITION BY stock_code ORDER BY date)
),
vol_base AS (
    SELECT
        stock_code,
        date,
        (close - prev_close_1)  / NULLIF(prev_close_1,  0) AS r1,
        (close - prev_close_5)  / NULLIF(prev_close_5,  0) AS r5,
        (close - prev_close_20) / NULLIF(prev_close_20, 0) AS r20
    FROM base
),
vol_calc AS (
    SELECT
        stock_code,
        date,
        r1,
        r5,
        r20,
        STDDEV_SAMP(
            LN(NULLIF(close, 0) / NULLIF(prev_close, 0))
        ) OVER (
            PARTITION BY stock_code
            ORDER BY date
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS vol20
    FROM (
        SELECT
            dp.stock_code,
            dp.date,
            dp.close,
            LAG(dp.close, 1) OVER (PARTITION BY dp.stock_code ORDER BY dp.date) AS prev_close,
            vb.r1,
            vb.r5,
            vb.r20
        FROM daily_prices dp
        JOIN vol_base vb USING (stock_code, date)
    ) sub
)
UPDATE daily_prices dp
SET
    returns_1d     = vc.r1,
    returns_5d     = vc.r5,
    returns_20d    = vc.r20,
    volatility_20d = vc.vol20,
    updated_at     = CURRENT_TIMESTAMP
FROM vol_calc vc
WHERE dp.stock_code = vc.stock_code
  AND dp.date       = vc.date
"""


def update_returns_volatility(conn) -> None:
    """연결된 DB의 daily_prices 전체에 returns_1d/5d/20d·volatility_20d 재계산."""
    with conn.cursor() as cur:
        cur.execute(SQL_UPDATE_RETURNS)
    conn.commit()

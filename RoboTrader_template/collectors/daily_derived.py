# collectors/daily_derived.py
"""파생(returns/volatility) 갱신 — 검증된 SQL_UPDATE_RETURNS 재사용, 새 DB 대상 실행."""
from scripts.etl_backfill_daily_prices import SQL_UPDATE_RETURNS


def update_returns_volatility(conn) -> None:
    """연결된 DB의 daily_prices 전체에 returns_1d/5d/20d·volatility_20d 재계산."""
    with conn.cursor() as cur:
        cur.execute(SQL_UPDATE_RETURNS)
    conn.commit()

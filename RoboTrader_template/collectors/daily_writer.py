# collectors/daily_writer.py
"""KIS 일봉 output2 파싱 + kis_template daily_prices UPSERT."""
from typing import Optional


def _f(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _i(v) -> int:
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def parse_kis_daily_row(item: dict, market_cap: Optional[float]) -> Optional[dict]:
    """KIS FHKST03010100 output2 1건 → daily_prices 행 dict. 0/결측 종가는 None."""
    close = _f(item.get("stck_clpr"))
    if close <= 0:
        return None
    raw_date = str(item.get("stck_bsop_date", ""))
    if len(raw_date) != 8:
        return None
    return {
        "date": f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}",
        "open": _f(item.get("stck_oprc")),
        "high": _f(item.get("stck_hgpr")),
        "low": _f(item.get("stck_lwpr")),
        "close": close,
        "volume": _i(item.get("acml_vol")),
        "trading_value": _i(item.get("acml_tr_pbmn")),
        "market_cap": float(market_cap) if market_cap is not None else None,
    }


DAILY_UPSERT_SQL = """
INSERT INTO daily_prices
    (stock_code, date, open, high, low, close, volume, trading_value, market_cap, updated_at)
VALUES (%(stock_code)s, %(date)s, %(open)s, %(high)s, %(low)s, %(close)s,
        %(volume)s, %(trading_value)s, %(market_cap)s, now())
ON CONFLICT (stock_code, date) DO UPDATE SET
    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close,
    volume=EXCLUDED.volume, trading_value=EXCLUDED.trading_value,
    market_cap=COALESCE(EXCLUDED.market_cap, daily_prices.market_cap),
    updated_at=now()
"""


def upsert_daily_rows(conn, rows) -> int:
    """rows: [{stock_code, date, open, high, low, close, volume, trading_value, market_cap}]."""
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(DAILY_UPSERT_SQL, r)
            n += 1
    conn.commit()
    return n

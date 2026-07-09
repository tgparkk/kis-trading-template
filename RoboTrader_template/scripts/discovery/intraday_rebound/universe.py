# scripts/discovery/intraday_rebound/universe.py
"""상시수집 유니버스 산출 (2025-04-01 이후 거래일의 min_coverage 이상 수집)."""
from __future__ import annotations

import json
from pathlib import Path

from .db import MINUTE_DB, read_sql

UNIVERSE_CACHE = Path(__file__).parent / "_cache" / "universe.json"

_SQL = """
WITH tot AS (
    SELECT COUNT(DISTINCT trade_date) AS d
    FROM minute_candles WHERE trade_date >= %s
),
per AS (
    SELECT stock_code, COUNT(DISTINCT trade_date) AS d
    FROM minute_candles WHERE trade_date >= %s
    GROUP BY stock_code
)
SELECT per.stock_code
FROM per, tot
WHERE per.d >= tot.d * %s
ORDER BY per.stock_code
"""


def load_universe(dbname: str = MINUTE_DB,
                  start_date: str = "20250401",
                  min_coverage: float = 0.9,
                  use_cache: bool = True) -> list[str]:
    key = f"{dbname}|{start_date}|{min_coverage}"
    if use_cache and UNIVERSE_CACHE.exists():
        cached = json.loads(UNIVERSE_CACHE.read_text(encoding="utf-8"))
        if cached.get("key") == key:
            return cached["codes"]

    df = read_sql(_SQL, (start_date, start_date, min_coverage), dbname)
    codes = sorted(df["stock_code"].tolist())

    UNIVERSE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    UNIVERSE_CACHE.write_text(
        json.dumps({"key": key, "codes": codes}, ensure_ascii=False),
        encoding="utf-8",
    )
    return codes

# scripts/discovery/intraday_rebound/universe.py
"""상시수집 유니버스 산출 (2025-04-01 이후 거래일의 min_coverage 이상 수집).

캐시하지 않는다 — by design. 쿼리 결과는 dbname/start_date/min_coverage 뿐 아니라
minute_candles 에 쌓인 거래일 총수에도 의존하는데, 이 총수는 매일 늘어난다. 같은
파라미터라도 나중에 호출하면 커버리지 멤버십이 달라질 수 있어, 캐시된 유니버스가
아무 신호 없이 조용히 stale 해진다 (이 프로젝트가 오늘 겪은 운영 사고와 동일한
실패 형태). load_universe() 는 호출마다 DB를 다시 조회한다. 파이프라인 1회 실행당
~1회만 호출되며, 인덱스 스캔에 걸린 199행은 비용이 무시할 만하다.
"""
from __future__ import annotations

from .db import MINUTE_DB, read_sql

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
                  min_coverage: float = 0.9) -> list[str]:
    df = read_sql(_SQL, (start_date, start_date, min_coverage), dbname)
    return sorted(df["stock_code"].tolist())

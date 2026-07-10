# scripts/discovery/intraday_rebound/universe.py
"""상시수집 유니버스 산출 (2025-04-01 이후 거래일의 min_coverage 이상 수집).

캐시하지 않는다 — by design. 쿼리 결과는 dbname/start_date/min_coverage 뿐 아니라
minute_candles 에 쌓인 거래일 총수에도 의존하는데, 이 총수는 매일 늘어난다. 같은
파라미터라도 나중에 호출하면 커버리지 멤버십이 달라질 수 있어, 캐시된 유니버스가
아무 신호 없이 조용히 stale 해진다 (이 프로젝트가 오늘 겪은 운영 사고와 동일한
실패 형태). load_universe() 는 호출마다 DB를 다시 조회한다. 파이프라인 1회 실행당
~1회만 호출되며, 인덱스 스캔에 걸린 199행은 비용이 무시할 만하다.

재현성을 위해서는 이 모듈의 load_universe() 를 직접 쓰지 말고
load_frozen_universe() 를 쓴다 — 데이터가 계속 쌓이면서 동일 파라미터라도
멤버십이 drift 하는 문제를, 특정 시점에 캡처한 고정 코드 목록으로 우회한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from .db import MINUTE_DB, read_sql

_SNAPSHOT_DIR = Path(__file__).parent
_DEFAULT_SNAPSHOT = "u199_20260710"

_SQL_OPEN_ENDED = """
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

_SQL_BOUNDED = """
WITH tot AS (
    SELECT COUNT(DISTINCT trade_date) AS d
    FROM minute_candles WHERE trade_date BETWEEN %s AND %s
),
per AS (
    SELECT stock_code, COUNT(DISTINCT trade_date) AS d
    FROM minute_candles WHERE trade_date BETWEEN %s AND %s
    GROUP BY stock_code
)
SELECT per.stock_code
FROM per, tot
WHERE per.d >= tot.d * %s
ORDER BY per.stock_code
"""


def load_universe(dbname: str = MINUTE_DB,
                  start_date: str = "20250401",
                  end_date: str | None = None,
                  min_coverage: float = 0.9) -> list[str]:
    """DB를 직접 조회해 커버리지 유니버스를 산출한다.

    ⚠️ end_date=None (기본값) 이면 상한 없이 "start_date 이후 전체" 를 조회한다 —
    minute_candles 에 새 거래일이 쌓일 때마다 tot.d 가 늘어나므로, 동일한
    start_date/min_coverage 라도 나중에 호출하면 결과가 조용히 달라질 수 있다
    (drift). 재현 가능한 연구 결과가 필요하면 이 열린 호출을 쓰지 말고
    load_frozen_universe() 로 고정된 코드 목록을 쓴다. end_date 를 명시하면
    tot/per 양쪽 모두 [start_date, end_date] 로 상한이 걸려 결과가 고정된다.
    """
    if end_date is None:
        df = read_sql(_SQL_OPEN_ENDED, (start_date, start_date, min_coverage), dbname)
    else:
        df = read_sql(
            _SQL_BOUNDED,
            (start_date, end_date, start_date, end_date, min_coverage),
            dbname,
        )
    return sorted(df["stock_code"].tolist())


def load_frozen_universe(name: str = _DEFAULT_SNAPSHOT) -> list[str]:
    """커밋된 스냅샷 JSON에서 고정 코드 목록을 읽는다. DB를 조회하지 않는다."""
    path = _SNAPSHOT_DIR / "universe_snapshot.json"
    with open(path, encoding="utf-8") as f:
        snapshot = json.load(f)
    if snapshot["name"] != name:
        raise ValueError(f"snapshot name mismatch: expected {name!r}, found {snapshot['name']!r}")
    return snapshot["codes"]


def verify_frozen_universe(dbname: str = MINUTE_DB, name: str = _DEFAULT_SNAPSHOT) -> dict:
    """냉동 유니버스가 현재 dbname 에서도 여전히 유효한지 확인한다.

    스냅샷 코드들 중 20250401..20260630 구간에 minute_candles 행이 0개인
    (즉 현재 DB에서 완전히 사라진) 코드를 missing 으로 보고한다.
    """
    codes = load_frozen_universe(name)
    sql = """
    SELECT DISTINCT stock_code FROM minute_candles
    WHERE trade_date BETWEEN %s AND %s AND stock_code = ANY(%s)
    """
    df = read_sql(sql, ("20250401", "20260630", codes), dbname)
    found = set(df["stock_code"].tolist())
    missing = sorted(c for c in codes if c not in found)
    return {"missing": missing, "n_expected": len(codes), "n_found": len(found)}

# tests/collectors/test_minute_writer_on_conflict.py
"""minute_writer._INSERT 의 ON CONFLICT 대상이 (stock_code, datetime) 인지 검증.

★ 버그 배경 (MEMORY / risk-2026-07-10-minute-candles-duplicate-bars):
  기존 _INSERT 는 ``ON CONFLICT (stock_code, trade_date, idx)`` 를 썼는데
  - trade_date 는 봉 날짜가 아니라 **수집일** 이고
  - idx 는 한 fetch 내 순번(봉 고유 id 아님)
  이라 같은 봉이 다른 trade_date/idx 로 재수집되면 ON CONFLICT 를 빠져나가
  **중복 봉** 이 생긴다. 봉의 진짜 자연키는 (stock_code, datetime).

★ 이 테스트가 하는 일 (실제 Postgres 필요, 없으면 skip):
  세션-로컬 TEMP TABLE ``minute_candles`` 를 만들어(같은 세션에서 unqualified
  ``minute_candles`` 는 pg_temp 가 먼저 잡히므로 실제 public.minute_candles 를
  **절대 건드리지 않는다**), writer 의 _INSERT SQL 을 그대로 실행한다.
  - 시나리오 A: 현행 프로덕션 스키마(PK 만) + **옛** ON CONFLICT 대상 → 2행(버그 재현)
  - 시나리오 B: 신규 스키마(UNIQUE(stock_code,datetime)) + **현재** _INSERT → 1행(수정 확인)
  - 시나리오 C: UNIQUE 인덱스가 없으면 _INSERT 가
      "no unique or exclusion constraint matching the ON CONFLICT specification"
    로 실패 — 배포 순서 제약(인덱스 먼저, 그다음 writer) 을 코드로 고정.

  트랜잭션은 롤백하고 TEMP 테이블은 세션 종료 시 자동 소멸 → 무해.

실행:
  TIMESCALE_DB=kis_template python -m pytest tests/collectors/test_minute_writer_on_conflict.py -v
  (DB 미도달 시 자동 skip. 실 DB 없이 검증하려면 collectors/minute_writer.py 의
   _INSERT 문자열을 육안 확인 — ON CONFLICT (stock_code, datetime) 여야 한다.)
"""
import os
from datetime import datetime

import pytest

from collectors.minute_writer import _INSERT

# 현재 코드의 ON CONFLICT 대상이 (stock_code, datetime) 인지 문자열 레벨 회귀 가드
# (DB 없이도 항상 실행됨).
def test_insert_sql_on_conflict_targets_stock_code_datetime():
    normalized = " ".join(_INSERT.split()).lower()
    assert "on conflict (stock_code, datetime) do nothing" in normalized, _INSERT
    # 옛 대상이 남아있지 않아야 한다.
    assert "on conflict (stock_code, trade_date, idx)" not in normalized


# 옛 _INSERT 를 재현(버그 시연용) — 현재 코드가 아니라 "고치기 전" SQL.
_OLD_INSERT = _INSERT.replace(
    "ON CONFLICT (stock_code, datetime) DO NOTHING",
    "ON CONFLICT (stock_code, trade_date, idx) DO NOTHING",
)

_TEMP_DDL_PK_ONLY = """
CREATE TEMP TABLE minute_candles (
    stock_code VARCHAR NOT NULL,
    trade_date VARCHAR NOT NULL,
    idx INTEGER NOT NULL,
    date VARCHAR,
    time VARCHAR,
    close DOUBLE PRECISION,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    amount DOUBLE PRECISION,
    datetime TIMESTAMP,
    PRIMARY KEY (stock_code, trade_date, idx)
) ON COMMIT DROP
"""

# 신규 스키마 = 현행 PK + Part 3 에서 추가할 UNIQUE(stock_code, datetime).
_TEMP_DDL_WITH_UNIQUE = _TEMP_DDL_PK_ONLY.rstrip()[:-len(") ON COMMIT DROP")] + \
    ",\n    UNIQUE (stock_code, datetime)\n) ON COMMIT DROP"


def _bar(idx, trade_date, dt):
    return {
        "stock_code": "005930",
        "trade_date": trade_date,
        "idx": idx,
        "date": "20260101",
        "time": "090100",
        "close": 100.0, "open": 100.0, "high": 101.0, "low": 99.0,
        "volume": 10.0, "amount": 1000.0,
        "datetime": dt,
    }


@pytest.fixture
def pg_conn():
    """실제 Postgres 연결(읽기전용 아님 — TEMP 테이블 필요). 미도달 시 skip.

    TEMP 테이블 + 롤백만 사용하므로 어떤 영속 테이블도 건드리지 않는다.
    """
    psycopg2 = pytest.importorskip("psycopg2")
    cfg = dict(
        host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
        port=int(os.getenv("TIMESCALE_PORT", "5433")),
        dbname=os.getenv("TIMESCALE_DB", "kis_template"),
        user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"),
        connect_timeout=3,
    )
    try:
        conn = psycopg2.connect(**cfg)
    except psycopg2.OperationalError as e:
        pytest.skip(f"test Postgres 미도달 ({cfg['host']}:{cfg['port']}/{cfg['dbname']}): {e}")
    try:
        yield conn
    finally:
        conn.rollback()  # TEMP 테이블/모든 변경 폐기
        conn.close()


def test_old_target_creates_duplicate_under_current_schema(pg_conn):
    """버그 재현: 현행 스키마(PK 만) + 옛 ON CONFLICT 대상 → 같은 봉이 2행."""
    dt = datetime(2026, 1, 1, 9, 1, 0)
    with pg_conn.cursor() as cur:
        cur.execute(_TEMP_DDL_PK_ONLY)
        cur.execute(_OLD_INSERT, _bar(idx=0, trade_date="20260101", dt=dt))
        # 같은 (stock_code, datetime), 다른 trade_date/idx 로 재수집
        cur.execute(_OLD_INSERT, _bar(idx=5, trade_date="20260102", dt=dt))
        cur.execute("SELECT count(*) FROM minute_candles")
        assert cur.fetchone()[0] == 2  # 중복 통과 = 버그
    pg_conn.rollback()


def test_new_target_blocks_duplicate_with_unique_index(pg_conn):
    """수정 확인: UNIQUE(stock_code,datetime) + 현재 _INSERT → 같은 봉은 1행."""
    dt = datetime(2026, 1, 1, 9, 1, 0)
    with pg_conn.cursor() as cur:
        cur.execute(_TEMP_DDL_WITH_UNIQUE)
        cur.execute(_INSERT, _bar(idx=0, trade_date="20260101", dt=dt))
        # 같은 (stock_code, datetime), 다른 trade_date/idx → ON CONFLICT DO NOTHING
        cur.execute(_INSERT, _bar(idx=5, trade_date="20260102", dt=dt))
        cur.execute("SELECT count(*) FROM minute_candles")
        assert cur.fetchone()[0] == 1  # 중복 차단 = 수정됨
    pg_conn.rollback()


def test_new_target_requires_unique_index_deploy_ordering(pg_conn):
    """배포 순서 제약: UNIQUE(datetime) 인덱스가 없으면 _INSERT 자체가 실패한다.

    → 반드시 (Part 2 dedup) → (Part 3 UNIQUE index) → (Part 1 writer) 순서여야 함을 고정.
    """
    import psycopg2
    dt = datetime(2026, 1, 1, 9, 1, 0)
    with pg_conn.cursor() as cur:
        cur.execute(_TEMP_DDL_PK_ONLY)  # UNIQUE(datetime) 없음
        with pytest.raises(psycopg2.errors.InvalidColumnReference):
            cur.execute(_INSERT, _bar(idx=0, trade_date="20260101", dt=dt))
    pg_conn.rollback()

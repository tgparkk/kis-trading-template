"""_has_adj_factor 비용 분해 — connect vs information_schema vs data query.

🔴 2026-08-03 감사: 이 스크립트는 **이미 실행 불가**다 — 측정 대상인
   pit_reader._has_adj_factor 가 제거됐다(multiverse/data/pit_reader.py:215).
   내부 SQL 의 `open * COALESCE(adj_factor, 1.0)` 도 폐기된 계산이다: close/open 은
   이미 분할조정된 연속 시세라 곱하면 분할일에 가짜 절벽이 생긴다. 다만 이 파일의
   산출물은 가격이 아니라 **소요 시간**이라 과거 결론에는 영향이 없었다.
   ⚠️ 이 SQL 패턴을 복사하지 말 것. archive 보존 원칙상 코드는 고치지 않는다.
"""
import time
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from RoboTrader_template.multiverse.data import pit_reader


@contextmanager
def _conn():
    c = psycopg2.connect(**pit_reader._DB_DEFAULTS, database=pit_reader._ROBOTRADER_DB)
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


N = 20

# 1) psycopg2 connect+close 단독
t0 = time.monotonic()
for _ in range(N):
    c = psycopg2.connect(**pit_reader._DB_DEFAULTS, database=pit_reader._ROBOTRADER_DB)
    c.close()
t1 = time.monotonic()
print(f"connect+close x{N}: {(t1-t0)*1000/N:.1f}ms each")

# 2) information_schema 쿼리만
t0 = time.monotonic()
for _ in range(N):
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='daily_prices' AND column_name='adj_factor' LIMIT 1"
            )
            cur.fetchone()
t1 = time.monotonic()
print(f"information_schema query x{N}: {(t1-t0)*1000/N:.1f}ms each")

# 3) 실제 데이터 쿼리 (open 1건)
t0 = time.monotonic()
for _ in range(N):
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT open FROM daily_prices WHERE stock_code=%s AND date=%s LIMIT 1",
                ("005930", "2024-06-01"),
            )
            cur.fetchone()
t1 = time.monotonic()
print(f"SELECT open x{N}: {(t1-t0)*1000/N:.1f}ms each")

# 4) connect + information_schema + data (= 현재 read_open 1회 비용)
t0 = time.monotonic()
for _ in range(N):
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            has_adj = pit_reader._has_adj_factor(cur)
            if has_adj:
                cur.execute(
                    "SELECT open * COALESCE(adj_factor, 1.0) AS open "
                    "FROM daily_prices WHERE stock_code=%s AND date=%s LIMIT 1",
                    ("005930", "2024-06-01"),
                )
            else:
                cur.execute(
                    "SELECT open FROM daily_prices WHERE stock_code=%s AND date=%s LIMIT 1",
                    ("005930", "2024-06-01"),
                )
            cur.fetchone()
t1 = time.monotonic()
print(f"connect + _has_adj + SELECT open x{N}: {(t1-t0)*1000/N:.1f}ms each")

# 5) _has_adj를 한 번만 캐시하면 얼마나 빠른가
t0 = time.monotonic()
with _conn() as c:
    with c.cursor() as cur:
        has_adj_cached = pit_reader._has_adj_factor(cur)  # 딱 1회만
for _ in range(N):
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if has_adj_cached:
                cur.execute(
                    "SELECT open * COALESCE(adj_factor, 1.0) AS open "
                    "FROM daily_prices WHERE stock_code=%s AND date=%s LIMIT 1",
                    ("005930", "2024-06-01"),
                )
            else:
                cur.execute(
                    "SELECT open FROM daily_prices WHERE stock_code=%s AND date=%s LIMIT 1",
                    ("005930", "2024-06-01"),
                )
            cur.fetchone()
t1 = time.monotonic()
print(f"_has_adj 1회 캐시 후 SELECT open x{N}: {(t1-t0)*1000/N:.1f}ms each")
print(f"  → 절감: {164 - (t1-t0)*1000/N:.1f}ms/call")

# 스케일 계산
cached_ms = (t1 - t0) * 1000 / N
print()
print("=== 스케일 추정 ===")
trading_days = 1261
positions_avg = 7
calls = trading_days * positions_avg * 2  # read_open + read_high_low
print(f"단일 셀 총 DB 호출: {calls:,}회")
print(f"현재 (164ms): {calls * 164 / 1000:.0f}초 = {calls * 164 / 1000 / 60:.1f}분")
print(f"캐시 후 ({cached_ms:.0f}ms): {calls * cached_ms / 1000:.0f}초 = {calls * cached_ms / 1000 / 60:.1f}분")

"""connect 비용 vs 쿼리 비용 재측정 — 연결 재사용 패턴 확인.

🔴 2026-08-03 감사: 이 스크립트는 **이미 실행 불가**다 — 호출하는
   pit_reader._has_adj_factor 가 제거됐다(multiverse/data/pit_reader.py:215).
   내부 SQL 의 `open * COALESCE(adj_factor, 1.0)` 도 폐기된 계산이다: open/close 는
   이미 분할조정된 연속 시세라 곱하면 분할일에 가짜 절벽이 생긴다. 다만 이 파일의
   산출물은 가격이 아니라 **소요 시간**이라 과거 결론에는 영향이 없었다.
   ⚠️ 이 SQL 패턴을 복사하지 말 것. archive 보존 원칙상 코드는 고치지 않는다.
"""
import time
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from RoboTrader_template.multiverse.data import pit_reader

N = 50

# --- 연결 재사용: 하나의 conn으로 N번 쿼리 ---
print("=== 연결 재사용 패턴 ===")

conn = psycopg2.connect(**pit_reader._DB_DEFAULTS, database=pit_reader._ROBOTRADER_DB)
# _has_adj 1회만
with conn.cursor() as cur:
    has_adj = pit_reader._has_adj_factor(cur)
print(f"adj_factor 컬럼 존재: {has_adj}")

t0 = time.monotonic()
for _ in range(N):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
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
elapsed = time.monotonic() - t0
conn.close()
print(f"연결 재사용 SELECT open x{N}: {elapsed*1000/N:.1f}ms each")
print(f"  (연결 1개 유지, _has_adj 0번 추가 호출)")

# --- 현재 방식: 매번 새 연결 + _has_adj ---
print()
print("=== 현재 방식 (매번 새 연결 + _has_adj) ===")
t0 = time.monotonic()
for _ in range(N):
    val = pit_reader.read_open("005930", "2024-06-01")
elapsed = time.monotonic() - t0
print(f"read_open x{N} (현재): {elapsed*1000/N:.1f}ms each")

# --- 스케일 재계산 ---
reuse_ms = 0.0
with psycopg2.connect(**pit_reader._DB_DEFAULTS, database=pit_reader._ROBOTRADER_DB) as conn2:
    with conn2.cursor() as cur:
        has_adj2 = pit_reader._has_adj_factor(cur)
    t0 = time.monotonic()
    for _ in range(N):
        with conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT open * COALESCE(adj_factor, 1.0) AS open "
                "FROM daily_prices WHERE stock_code=%s AND date=%s LIMIT 1",
                ("005930", "2024-06-01"),
            )
            cur.fetchone()
    reuse_ms = (time.monotonic() - t0) * 1000 / N

print()
print("=== 스케일 재추정 ===")
current_ms = elapsed * 1000 / N
trading_days = 1261
positions_avg = 7
calls_per_cell = trading_days * positions_avg * 2

print(f"단일 셀 DB 호출: {calls_per_cell:,}회")
print(f"현재 ({current_ms:.0f}ms/call): {calls_per_cell * current_ms / 1000:.0f}초 = {calls_per_cell * current_ms / 1000 / 60:.1f}분/셀")
print(f"연결 재사용 ({reuse_ms:.1f}ms/call): {calls_per_cell * reuse_ms / 1000:.0f}초 = {calls_per_cell * reuse_ms / 1000 / 60:.1f}분/셀")
print()
print(f"144셀 × 현재: {144 * calls_per_cell * current_ms / 1000 / 3600:.1f}시간")
print(f"144셀 × 재사용: {144 * calls_per_cell * reuse_ms / 1000 / 3600:.1f}시간")

# --- _get_portfolio_trading_dates 비용 측정 ---
print()
print("=== _get_portfolio_trading_dates 비용 (200종목 × read_daily) ===")
from datetime import date
from RoboTrader_template.multiverse.engine.portfolio_engine import _get_portfolio_trading_dates

# 200개 대신 10개로 샘플
import random
symbols_sample = ["005930", "000660", "035420", "051910", "006400",
                  "035720", "028260", "105560", "055550", "000270"]
t0 = time.monotonic()
dates = _get_portfolio_trading_dates(date(2024, 1, 2), date(2024, 3, 31), symbols_sample)
elapsed = time.monotonic() - t0
print(f"10종목 × read_daily: {elapsed:.2f}s → 200종목 추정: {elapsed*20:.1f}s = {elapsed*20/60:.1f}분")
print(f"반환 거래일 수: {len(dates)}")

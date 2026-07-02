"""
daily_prices ETL 백필 스크립트

기능:
  strategy_analysis.daily_candles (2021-01-12~2024-02-29 gap)
  → robotrader_quant.daily_prices 에 백필 후
  → returns_1d/5d/20d, volatility_20d 윈도우 함수 재계산

실행:
  python scripts/etl_backfill_daily_prices.py            # dry-run (SELECT 검증만)
  python scripts/etl_backfill_daily_prices.py --apply    # 실제 INSERT 실행

전제 조건:
  D0 ALTER 완료 (volume BIGINT, adj_factor DOUBLE PRECISION)

절대 금지:
  - DROP / TRUNCATE 없음
  - INSERT ON CONFLICT DO NOTHING 만 사용 (멱등)
  - 기존 데이터 UPDATE 없음 (returns 재계산은 전체 재계산이지만 멱등)
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

# ─────────────────────────────────────────────────────────────────────────────
# 로깅 설정
# ─────────────────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)  # 직접 실행(python scripts/...) 시 repo 루트 import 보장 (collectors 역방향 import)
_LOGS_DIR = os.path.join(_ROOT, "logs")
os.makedirs(_LOGS_DIR, exist_ok=True)

_TS = datetime.now().strftime("%Y%m%d_%H%M%S")
_LOG_FILE = os.path.join(_LOGS_DIR, f"etl_daily_prices_{_TS}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# DB 설정
# ─────────────────────────────────────────────────────────────────────────────
_DB_COMMON = dict(host="127.0.0.1", port=5433, user="postgres", password="1234")

SOURCE_DSN = dict(**_DB_COMMON, dbname="strategy_analysis")
TARGET_DSN = dict(**_DB_COMMON, dbname="robotrader_quant")

# gap 경계: 이 날짜 미만만 가져온다 (2차 백필: 2023-04-25 ~ 2024-02-29 갭 포함)
GAP_END_EXCLUSIVE = "2024-03-01"

# 배치 크기 (종목 단위 flush)
BATCH_SIZE = 500

# ─────────────────────────────────────────────────────────────────────────────
# SQL
# ─────────────────────────────────────────────────────────────────────────────
SQL_SELECT_SOURCE = """
SELECT
    stock_code,
    TO_CHAR(trade_date, 'YYYY-MM-DD')  AS date,
    open_price::double precision        AS open,
    high_price::double precision        AS high,
    low_price::double precision         AS low,
    close_price::double precision       AS close,
    volume,
    trading_value,
    market_cap::double precision        AS market_cap
FROM daily_candles
WHERE trade_date < %s
  AND open_price IS NOT NULL
  AND close_price IS NOT NULL
  AND volume IS NOT NULL
ORDER BY stock_code, trade_date
"""

SQL_INSERT = """
INSERT INTO daily_prices
    (stock_code, date, open, high, low, close,
     volume, trading_value, market_cap,
     adj_factor, created_at, updated_at)
VALUES %s
ON CONFLICT (stock_code, date) DO NOTHING
"""

# SQL_UPDATE_RETURNS 는 운영 수집기가 소유 → collectors 로 승격 (2026-07-02 Phase1).
from collectors.daily_derived import SQL_UPDATE_RETURNS  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# 검증 쿼리
# ─────────────────────────────────────────────────────────────────────────────
SQL_VERIFY_RANGE = """
SELECT
    MIN(date)   AS min_date,
    MAX(date)   AS max_date,
    COUNT(*)    AS total_rows,
    COUNT(DISTINCT stock_code) AS stock_count
FROM daily_prices
"""

SQL_VERIFY_BOUNDARY_NULLS = """
SELECT
    SUM(CASE WHEN returns_1d IS NULL THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) AS null_ratio,
    COUNT(*) AS row_count
FROM daily_prices
WHERE date BETWEEN '2023-04-20' AND '2023-04-30'
"""

SQL_VERIFY_STREAK = """
WITH gaps AS (
    SELECT
        stock_code,
        date,
        date::date - LAG(date::date) OVER (PARTITION BY stock_code ORDER BY date) AS day_gap
    FROM daily_prices
    WHERE date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
),
streaks AS (
    SELECT
        stock_code,
        MAX(day_gap) AS max_gap,
        AVG(day_gap) AS avg_gap,
        COUNT(*) AS trading_days
    FROM gaps
    WHERE day_gap IS NOT NULL
    GROUP BY stock_code
)
SELECT
    MIN(max_gap)  AS min_of_max_gap,
    MAX(max_gap)  AS max_of_max_gap,
    ROUND(AVG(max_gap)::numeric, 2) AS avg_of_max_gap,
    COUNT(*)      AS stock_count,
    SUM(CASE WHEN max_gap > 7 THEN 1 ELSE 0 END) AS stocks_with_gap_over_7d
FROM streaks
"""


# ─────────────────────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────────────────────
def _connect(dsn: dict) -> psycopg2.extensions.connection:
    return psycopg2.connect(**dsn)


def _fmt_elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s" if m else f"{s}s"


# ─────────────────────────────────────────────────────────────────────────────
# DRY-RUN: 소스 행 수 + 컬럼 매핑 샘플 확인만
# ─────────────────────────────────────────────────────────────────────────────
def run_dry_run() -> None:
    logger.info("=" * 60)
    logger.info("DRY-RUN mode -- INSERT 없음, SELECT 검증만 수행")
    logger.info("=" * 60)

    t0 = time.time()

    # 소스 DB 연결
    logger.info("[소스] strategy_analysis.daily_candles 조회 중...")
    src_conn = _connect(SOURCE_DSN)
    src_cur = src_conn.cursor()

    # 전체 gap 행 수
    src_cur.execute(
        "SELECT COUNT(*), COUNT(DISTINCT stock_code) FROM daily_candles WHERE trade_date < %s",
        (GAP_END_EXCLUSIVE,),
    )
    total_rows, total_stocks = src_cur.fetchone()
    logger.info(f"  gap 행 수: {total_rows:,}  / 종목 수: {total_stocks:,}")

    # 날짜 범위
    src_cur.execute(
        "SELECT MIN(trade_date), MAX(trade_date) FROM daily_candles WHERE trade_date < %s",
        (GAP_END_EXCLUSIVE,),
    )
    min_d, max_d = src_cur.fetchone()
    logger.info(f"  날짜 범위: {min_d} ~ {max_d}")

    # NULL 비율 (품질)
    src_cur.execute(
        """
        SELECT
            SUM(CASE WHEN open_price  IS NULL THEN 1 ELSE 0 END) AS null_open,
            SUM(CASE WHEN close_price IS NULL THEN 1 ELSE 0 END) AS null_close,
            SUM(CASE WHEN volume      IS NULL THEN 1 ELSE 0 END) AS null_vol,
            SUM(CASE WHEN market_cap  IS NULL THEN 1 ELSE 0 END) AS null_mktcap
        FROM daily_candles
        WHERE trade_date < %s
        """,
        (GAP_END_EXCLUSIVE,),
    )
    nc = src_cur.fetchone()
    logger.info(
        f"  NULL 건수 - open:{nc[0]:,} close:{nc[1]:,} volume:{nc[2]:,} market_cap:{nc[3]:,}"
    )

    # 샘플 5행 (컬럼 매핑 확인)
    src_cur.execute(
        SQL_SELECT_SOURCE + " LIMIT 5",
        (GAP_END_EXCLUSIVE,),
    )
    # SQL_SELECT_SOURCE 끝에 ORDER BY가 있으므로 LIMIT 별도 추가
    # 위 쿼리는 실제로는 원본 SQL에 LIMIT 를 붙여야 하므로 별도 실행
    src_cur.execute(
        """
        SELECT
            stock_code,
            TO_CHAR(trade_date, 'YYYY-MM-DD') AS date,
            open_price::double precision,
            high_price::double precision,
            low_price::double precision,
            close_price::double precision,
            volume,
            trading_value,
            market_cap::double precision
        FROM daily_candles
        WHERE trade_date < %s
        ORDER BY stock_code, trade_date
        LIMIT 5
        """,
        (GAP_END_EXCLUSIVE,),
    )
    rows = src_cur.fetchall()
    logger.info("  [샘플 5행] stock_code | date | open | high | low | close | volume | trading_value | market_cap")
    for r in rows:
        logger.info(f"    {r}")

    src_cur.close()
    src_conn.close()

    # 타겟 DB 현황
    logger.info("")
    logger.info("[타겟] robotrader_quant.daily_prices 현황 조회 중...")
    tgt_conn = _connect(TARGET_DSN)
    tgt_cur = tgt_conn.cursor()

    tgt_cur.execute(
        "SELECT MIN(date), MAX(date), COUNT(*), COUNT(DISTINCT stock_code) FROM daily_prices"
    )
    t_min, t_max, t_rows, t_stocks = tgt_cur.fetchone()
    logger.info(f"  현재 날짜 범위: {t_min} ~ {t_max}")
    logger.info(f"  현재 행 수: {t_rows:,}  / 종목 수: {t_stocks:,}")

    # 중복 예상 행 수 (이미 존재하는 (stock_code, date) 쌍)
    tgt_cur.execute(
        """
        SELECT COUNT(*)
        FROM daily_prices
        WHERE date < %s
        """,
        (GAP_END_EXCLUSIVE,),
    )
    (existing_in_gap,) = tgt_cur.fetchone()
    logger.info(f"  타겟에 이미 존재하는 gap 기간 행: {existing_in_gap:,}")
    logger.info(f"  예상 신규 INSERT 행: {max(0, total_rows - existing_in_gap):,} (ON CONFLICT DO NOTHING 적용)")

    tgt_cur.close()
    tgt_conn.close()

    elapsed = time.time() - t0
    logger.info("")
    logger.info(f"dry-run 완료. 소요: {_fmt_elapsed(elapsed)}")
    logger.info(f"로그 파일: {_LOG_FILE}")
    logger.info("")
    logger.info("--apply 플래그로 재실행하면 INSERT + returns 재계산을 수행합니다.")


# ─────────────────────────────────────────────────────────────────────────────
# APPLY: 실제 INSERT + returns 재계산
# ─────────────────────────────────────────────────────────────────────────────
def run_apply() -> None:
    logger.info("=" * 60)
    logger.info("APPLY mode -- INSERT 실행 (ON CONFLICT DO NOTHING)")
    logger.info("=" * 60)

    t0 = time.time()

    # ── 1. 소스 전체 로드 ─────────────────────────────────────────
    logger.info("[1/4] 소스 데이터 로드 중...")
    src_conn = _connect(SOURCE_DSN)
    src_cur = src_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    src_cur.execute(SQL_SELECT_SOURCE, (GAP_END_EXCLUSIVE,))
    source_rows = src_cur.fetchall()
    src_cur.close()
    src_conn.close()

    total_source = len(source_rows)
    logger.info(f"  로드 완료: {total_source:,}행")

    if total_source == 0:
        logger.warning("소스 데이터 없음. 종료.")
        return

    # ── 2. 종목 단위 배치 INSERT ──────────────────────────────────
    logger.info("[2/4] INSERT 시작 (배치 크기: 종목 단위, flush %d행 마다)..." % BATCH_SIZE)

    now_ts = datetime.now()

    tgt_conn = _connect(TARGET_DSN)
    tgt_conn.autocommit = False
    tgt_cur = tgt_conn.cursor()

    inserted_total = 0
    batch: list[tuple] = []
    current_stock = None
    stocks_processed = 0
    last_log_pct = -1

    try:
        for i, row in enumerate(source_rows):
            stock_code = row["stock_code"]

            if stock_code != current_stock:
                # 종목 전환 시 현재 배치 flush
                if batch:
                    psycopg2.extras.execute_values(
                        tgt_cur,
                        SQL_INSERT,
                        batch,
                        page_size=len(batch),
                    )
                    inserted_total += tgt_cur.rowcount if tgt_cur.rowcount >= 0 else 0
                    batch = []
                    stocks_processed += 1

                current_stock = stock_code

                # 진행률 10% 단위 로깅
                pct = int(i / total_source * 100)
                if pct // 10 > last_log_pct // 10:
                    elapsed = time.time() - t0
                    logger.info(
                        f"  진행: {pct}% ({i:,}/{total_source:,}행, "
                        f"{stocks_processed}종목 완료, {_fmt_elapsed(elapsed)} 경과)"
                    )
                    last_log_pct = pct

            batch.append((
                row["stock_code"],
                row["date"],
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["volume"],
                row["trading_value"],
                row["market_cap"],
                1.0,          # adj_factor
                now_ts,       # created_at
                now_ts,       # updated_at
            ))

            # 배치 크기 도달 시 flush (종목 경계와 무관하게)
            if len(batch) >= BATCH_SIZE:
                psycopg2.extras.execute_values(
                    tgt_cur,
                    SQL_INSERT,
                    batch,
                    page_size=len(batch),
                )
                inserted_total += tgt_cur.rowcount if tgt_cur.rowcount >= 0 else 0
                batch = []

        # 마지막 배치
        if batch:
            psycopg2.extras.execute_values(
                tgt_cur,
                SQL_INSERT,
                batch,
                page_size=len(batch),
            )
            inserted_total += tgt_cur.rowcount if tgt_cur.rowcount >= 0 else 0
            stocks_processed += 1

        tgt_conn.commit()
        elapsed_insert = time.time() - t0
        logger.info(
            f"  INSERT 완료: {inserted_total:,}행 신규 / {total_source:,}행 처리 "
            f"({total_source - inserted_total:,}행 DO NOTHING). "
            f"소요: {_fmt_elapsed(elapsed_insert)}"
        )

    except Exception as exc:
        tgt_conn.rollback()
        logger.error(f"INSERT 실패, ROLLBACK 완료: {exc}", exc_info=True)
        tgt_cur.close()
        tgt_conn.close()
        sys.exit(1)

    # ── 3. returns / volatility 재계산 ───────────────────────────
    logger.info("[3/4] returns_1d/5d/20d + volatility_20d 재계산 중...")
    logger.info("  (전체 재계산 - 윈도우 함수 멱등, 약 수분 소요 가능)")

    try:
        tgt_cur.execute(SQL_UPDATE_RETURNS)
        updated_rows = tgt_cur.rowcount
        tgt_conn.commit()
        elapsed_returns = time.time() - t0
        logger.info(
            f"  returns UPDATE 완료: {updated_rows:,}행. 소요: {_fmt_elapsed(elapsed_returns)}"
        )
    except Exception as exc:
        tgt_conn.rollback()
        logger.error(f"returns UPDATE 실패, ROLLBACK: {exc}", exc_info=True)
        tgt_cur.close()
        tgt_conn.close()
        sys.exit(1)

    tgt_cur.close()

    # ── 4. 검증 쿼리 ─────────────────────────────────────────────
    logger.info("[4/4] 검증 쿼리 실행 중...")
    _run_verification(tgt_conn)
    tgt_conn.close()

    total_elapsed = time.time() - t0
    logger.info("")
    logger.info(f"APPLY 완료. 총 소요: {_fmt_elapsed(total_elapsed)}")
    logger.info(f"로그 파일: {_LOG_FILE}")


# ─────────────────────────────────────────────────────────────────────────────
# 검증
# ─────────────────────────────────────────────────────────────────────────────
def _run_verification(conn: psycopg2.extensions.connection) -> None:
    cur = conn.cursor()

    logger.info("")
    logger.info("─── [검증 1] 날짜 범위 / 총 행 수 ───")
    cur.execute(SQL_VERIFY_RANGE)
    row = cur.fetchone()
    logger.info(f"  MIN date: {row[0]}")
    logger.info(f"  MAX date: {row[1]}")
    logger.info(f"  총 행수: {row[2]:,}")
    logger.info(f"  종목 수: {row[3]:,}")

    logger.info("")
    logger.info("─── [검증 2] 2023-04-20~30 경계 returns_1d NULL 비율 ───")
    cur.execute(SQL_VERIFY_BOUNDARY_NULLS)
    row = cur.fetchone()
    null_ratio = row[0] or 0.0
    logger.info(f"  NULL 비율: {null_ratio:.1%}  (행수: {row[1]:,})")
    if null_ratio > 0.5:
        logger.warning("  경계 NULL 비율 50% 초과 - returns 재계산 확인 필요")

    logger.info("")
    logger.info("─── [검증 3] 종목별 거래일 결측 streak 통계 ───")
    cur.execute(SQL_VERIFY_STREAK)
    row = cur.fetchone()
    logger.info(f"  최소 max_gap: {row[0]}일")
    logger.info(f"  최대 max_gap: {row[1]}일")
    logger.info(f"  평균 max_gap: {row[2]}일")
    logger.info(f"  종목 수: {row[3]:,}")
    logger.info(f"  7일 초과 gap 보유 종목 수: {row[4]:,}")
    if row[1] and row[1] > 30:
        logger.warning("  30일 이상 gap 종목 존재 - 상장폐지/신규상장 여부 확인 권장")

    cur.close()


# ─────────────────────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="strategy_analysis.daily_candles → robotrader_quant.daily_prices ETL 백필"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="실제 INSERT 실행. 미지정 시 dry-run (SELECT 검증만)",
    )
    args = parser.parse_args()

    if args.apply:
        run_apply()
    else:
        run_dry_run()


if __name__ == "__main__":
    main()

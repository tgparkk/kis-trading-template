"""
daily_prices 펀더멘털 유니버스 다년치 백필 스크립트

기능:
  strategy_analysis.daily_candles (2021-01-12 ~ 가용 전체)
  → robotrader.daily_prices 에 백필 (펀더멘털 유니버스 한정)
  → returns_1d/5d/20d, volatility_20d 윈도우 함수 재계산

목적:
  책 리서치 펀더멘털 전략(Greenblatt, O'Shaughnessy)이 ~6개월 윈도우에
  갇혀 있는 문제를 해소. 펀더멘털 유니버스 종목(robotrader.financial_statements의
  131개 distinct stock_code)은 daily_prices에 2025-07+ ~200일치만 있고
  market_cap도 ~124일 윈도우만 존재. 반면 strategy_analysis.daily_candles는
  2021-2026 5년치를 market_cap 100% 채워서 보유. 이를 백필하면 다년·다국면
  펀더멘털 백테스트가 가능해짐.

대상:
  robotrader.financial_statements 에 존재하는 stock_code 만 (펀더멘털 유니버스).
  daily_candles 가용 전체 날짜 범위 (2021-01-12 onward).
  이미 daily_prices 에 존재하는 (stock_code, date) 행은 ON CONFLICT DO NOTHING 으로 스킵.

실행:
  python scripts/backfill_daily_prices_fundamental.py            # dry-run (기본, SELECT 검증만)
  python scripts/backfill_daily_prices_fundamental.py --apply    # 실제 INSERT 실행

절대 금지 (기존 etl_backfill_daily_prices.py 와 동일한 안전 규칙):
  - DROP / TRUNCATE 없음
  - UPDATE of existing price rows 없음
  - INSERT ON CONFLICT DO NOTHING 만 사용 (멱등)
  - retention policy 절대 설정 안 함

market_cap 출처 (중요 — 조사 결과 반영):
  strategy_analysis.daily_candles.market_cap 컬럼은 전체 239만 행이 모두 0 (positive 0건).
  즉 daily_candles 의 market_cap 은 사용 불가. 실제 시가총액은 같은 소스 DB의
  yearly_fundamentals.market_cap_won 에 연도별 1값으로 존재 (펀더멘털 유니버스 128종목,
  연도별 124~128 커버리지). 따라서 백필 시 OHLCV 는 daily_candles 에서,
  market_cap 은 yearly_fundamentals 를 해당 일자의 연도로 매칭하여 가져온다 (LEFT JOIN).
  매칭 연도 데이터가 없으면 market_cap 은 NULL (기존 ETL 의 raw 0 삽입보다 안전).

adj_factor:
  기존 daily_prices의 펀더멘털 유니버스 행(2025-07+)은 전부 adj_factor=1.0 (검증 완료).
  daily_candles 가격은 raw/unadjusted 이며 중첩 구간 종가 98%가 기존 행과 일치(검증 완료).
  따라서 백필 행에는 adj_factor=1.0 을 부여 - 2025-07 경계에서 불연속 위험 없음.
  기존 행은 어떤 경우에도 수정하지 않음.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime

import psycopg2
import psycopg2.extras

# ─────────────────────────────────────────────────────────────────────────────
# 로깅 설정
# ─────────────────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOGS_DIR = os.path.join(_ROOT, "logs")
os.makedirs(_LOGS_DIR, exist_ok=True)

_TS = datetime.now().strftime("%Y%m%d_%H%M%S")
_LOG_FILE = os.path.join(_LOGS_DIR, f"backfill_daily_prices_fundamental_{_TS}.log")

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
TARGET_DSN = dict(**_DB_COMMON, dbname="robotrader")

# 백필 행에 부여할 adj_factor (기존 행/소스 모두 raw, 1.0 검증 완료)
BACKFILL_ADJ_FACTOR = 1.0

# 배치 크기 (flush 단위)
BATCH_SIZE = 500

# ─────────────────────────────────────────────────────────────────────────────
# SQL
# ─────────────────────────────────────────────────────────────────────────────
# 펀더멘털 유니버스 = robotrader.financial_statements 의 distinct stock_code.
# financial_statements 는 타겟 DB(robotrader)에 있으므로 종목 리스트를 먼저
# 타겟에서 읽어 소스 쿼리에 = ANY(%s) 로 바인딩한다.
SQL_FUNDAMENTAL_UNIVERSE = """
SELECT DISTINCT stock_code FROM financial_statements ORDER BY stock_code
"""

# market_cap 은 daily_candles 가 전부 0 이므로 yearly_fundamentals.market_cap_won 을
# 일자의 연도(EXTRACT YEAR)로 LEFT JOIN 하여 가져온다.
SQL_SELECT_SOURCE = """
SELECT
    dc.stock_code,
    dc.trade_date                       AS date,
    dc.open_price::double precision      AS open,
    dc.high_price::double precision      AS high,
    dc.low_price::double precision       AS low,
    dc.close_price::double precision     AS close,
    dc.volume,
    dc.trading_value,
    yf.market_cap_won::double precision  AS market_cap
FROM daily_candles dc
LEFT JOIN yearly_fundamentals yf
       ON yf.stock_code = dc.stock_code
      AND yf.year       = EXTRACT(YEAR FROM dc.trade_date)::int
      AND yf.market_cap_won > 0
WHERE dc.stock_code = ANY(%s)
  AND dc.open_price IS NOT NULL
  AND dc.close_price IS NOT NULL
  AND dc.volume IS NOT NULL
ORDER BY dc.stock_code, dc.trade_date
"""

SQL_INSERT = """
INSERT INTO daily_prices
    (stock_code, date, open, high, low, close,
     volume, trading_value, market_cap,
     adj_factor, created_at, updated_at)
VALUES %s
ON CONFLICT (stock_code, date) DO NOTHING
"""

# returns / volatility 전체 재계산 (멱등 - 윈도우 함수 결과는 항상 동일).
# 펀더멘털 유니버스 종목만 PARTITION 내에서 재계산하면 충분하지만,
# 기존 etl 과 동일하게 전체 daily_prices 를 대상으로 한다(멱등이므로 결과 동일).
# 단, 기존 비-펀더멘털 종목의 returns 까지 건드리지 않도록 펀더멘털 종목으로 한정한다.
SQL_UPDATE_RETURNS = """
WITH scope AS (
    SELECT DISTINCT stock_code FROM financial_statements
),
base AS (
    SELECT
        dp.stock_code,
        dp.date,
        dp.close,
        LAG(dp.close, 1)  OVER w AS prev_close_1,
        LAG(dp.close, 5)  OVER w AS prev_close_5,
        LAG(dp.close, 20) OVER w AS prev_close_20
    FROM daily_prices dp
    JOIN scope s USING (stock_code)
    WINDOW w AS (PARTITION BY dp.stock_code ORDER BY dp.date)
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


# ─────────────────────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────────────────────
def _connect(dsn: dict) -> "psycopg2.extensions.connection":
    return psycopg2.connect(**dsn)


def _fmt_elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s" if m else f"{s}s"


def _load_universe(tgt_conn: "psycopg2.extensions.connection") -> list[str]:
    """타겟 DB의 financial_statements 에서 펀더멘털 유니버스 stock_code 로드."""
    cur = tgt_conn.cursor()
    cur.execute(SQL_FUNDAMENTAL_UNIVERSE)
    codes = [r[0] for r in cur.fetchall()]
    cur.close()
    return codes


# ─────────────────────────────────────────────────────────────────────────────
# DRY-RUN: INSERT 없이 백필 대상 행 수 / adj_factor 검증 / 샘플만 보고
# ─────────────────────────────────────────────────────────────────────────────
def run_dry_run() -> None:
    logger.info("=" * 60)
    logger.info("DRY-RUN mode -- INSERT 없음, SELECT 검증만 수행")
    logger.info("=" * 60)

    t0 = time.time()

    # ── 타겟: 펀더멘털 유니버스 + 기존 daily_prices 현황 ───────────
    tgt_conn = _connect(TARGET_DSN)
    tgt_cur = tgt_conn.cursor()

    universe = _load_universe(tgt_conn)
    logger.info(f"[유니버스] financial_statements distinct stock_code: {len(universe):,}개")

    # 기존 daily_prices (펀더멘털 유니버스) 현황
    tgt_cur.execute(
        """
        SELECT MIN(date), MAX(date), COUNT(*), COUNT(DISTINCT stock_code)
        FROM daily_prices
        WHERE stock_code = ANY(%s)
        """,
        (universe,),
    )
    e_min, e_max, e_rows, e_stocks = tgt_cur.fetchone()
    logger.info(
        f"[기존 타겟] daily_prices(펀더멘털) 범위: {e_min} ~ {e_max}, "
        f"행수: {e_rows:,}, 종목: {e_stocks:,}"
    )

    # 기존 행 adj_factor 분포 (경계 불연속 검증용)
    tgt_cur.execute(
        """
        SELECT adj_factor, COUNT(*) AS n, COUNT(DISTINCT stock_code) AS stocks,
               MIN(date) AS min_d, MAX(date) AS max_d
        FROM daily_prices
        WHERE stock_code = ANY(%s)
        GROUP BY adj_factor
        ORDER BY n DESC
        """,
        (universe,),
    )
    adj_rows = tgt_cur.fetchall()
    logger.info("[adj_factor 검증] 기존 펀더멘털 행의 adj_factor 분포:")
    for ar in adj_rows:
        logger.info(
            f"    adj_factor={ar[0]}  행수={ar[1]:,}  종목={ar[2]:,}  범위={ar[3]}~{ar[4]}"
        )

    # 기존 (stock_code, date) 키 집합 (중복 제외용)
    tgt_cur.execute(
        "SELECT stock_code, date FROM daily_prices WHERE stock_code = ANY(%s)",
        (universe,),
    )
    existing_keys = set((r[0], r[1]) for r in tgt_cur.fetchall())
    logger.info(f"[기존 타겟] (stock_code, date) 키 수: {len(existing_keys):,}")

    tgt_cur.close()
    tgt_conn.close()

    # ── 소스: daily_candles 펀더멘털 유니버스 후보 ────────────────
    logger.info("")
    logger.info("[소스] strategy_analysis.daily_candles 조회 중...")
    src_conn = _connect(SOURCE_DSN)
    src_cur = src_conn.cursor()

    # 소스에 존재하는 펀더멘털 종목 수 (유니버스와의 차집합 보고)
    src_cur.execute(
        "SELECT DISTINCT stock_code FROM daily_candles WHERE stock_code = ANY(%s)",
        (universe,),
    )
    src_stocks = set(r[0] for r in src_cur.fetchall())
    missing = sorted(set(universe) - src_stocks)
    logger.info(
        f"[소스] daily_candles 에 존재하는 펀더멘털 종목: {len(src_stocks):,}개 "
        f"(유니버스 {len(universe):,}개 중)"
    )
    if missing:
        logger.warning(
            f"[소스] daily_candles 에 없는 펀더멘털 종목 {len(missing)}개: {missing}"
        )

    # 후보 행 전체 로드 (valid OHLCV)
    src_cur.execute(SQL_SELECT_SOURCE, (universe,))
    src_rows = src_cur.fetchall()
    logger.info(f"[소스] 유효 OHLCV 후보 행: {len(src_rows):,}")

    # 중첩 구간 종가 비교 (raw vs adjusted 검증)
    src_cur.execute(
        """
        SELECT stock_code, trade_date, close_price::double precision
        FROM daily_candles
        WHERE stock_code = ANY(%s)
          AND trade_date BETWEEN %s AND %s
        """,
        (universe, e_min, e_max) if e_min else (universe, "2025-07-01", "2026-02-10"),
    )
    src_overlap = {(r[0], r[1]): r[2] for r in src_cur.fetchall()}

    src_cur.close()
    src_conn.close()

    # ── 백필 대상 계산 (소스 - 기존 키) ───────────────────────────
    would_insert = [r for r in src_rows if (r[0], r[1]) not in existing_keys]
    n_insert = len(would_insert)
    ins_stocks = set(r[0] for r in would_insert)
    ins_dates = [r[1] for r in would_insert]
    mc_nonnull = sum(1 for r in would_insert if r[8] is not None)

    logger.info("")
    logger.info("=" * 60)
    logger.info("백필 대상 (WOULD INSERT - ON CONFLICT DO NOTHING)")
    logger.info("=" * 60)
    logger.info(f"  총 INSERT 행: {n_insert:,}")
    logger.info(f"  distinct 종목: {len(ins_stocks):,}")
    if ins_dates:
        logger.info(f"  날짜 범위: {min(ins_dates)} ~ {max(ins_dates)}")
    mc_pct = (100.0 * mc_nonnull / n_insert) if n_insert else 0.0
    logger.info(
        f"  non-null market_cap 행: {mc_nonnull:,} ({mc_pct:.1f}%) "
        f"[출처: yearly_fundamentals.market_cap_won, 일자 연도 매칭]"
    )
    logger.info(
        "  주의: daily_candles.market_cap 은 전 행 0이라 사용 안 함. "
        "연도별 매칭 실패 행은 market_cap NULL."
    )

    # ── adj_factor / 경계 불연속 검증 ─────────────────────────────
    logger.info("")
    logger.info("─── [adj_factor 처리 및 경계 불연속 평가] ───")
    logger.info(f"  백필 행에 부여할 adj_factor: {BACKFILL_ADJ_FACTOR}")
    # 중첩 구간 종가 일치율
    overlap_keys = [(r[0], r[1]) for r in src_rows if (r[0], r[1]) in existing_keys]
    # 기존 행 종가는 별도 조회 필요 -> 재연결하여 비교
    if overlap_keys:
        cmp_conn = _connect(TARGET_DSN)
        cmp_cur = cmp_conn.cursor()
        cmp_cur.execute(
            """
            SELECT stock_code, date, close::double precision
            FROM daily_prices
            WHERE stock_code = ANY(%s) AND date BETWEEN %s AND %s
            """,
            (universe, e_min, e_max),
        )
        tgt_overlap = {(r[0], r[1]): r[2] for r in cmp_cur.fetchall()}
        cmp_cur.close()
        cmp_conn.close()

        common = set(tgt_overlap) & set(src_overlap)
        match = mismatch = 0
        for k in common:
            tc = tgt_overlap[k]
            sc = src_overlap[k]
            if tc is None or sc is None:
                continue
            if abs(float(tc) - float(sc)) < 0.5:
                match += 1
            else:
                mismatch += 1
        total_cmp = match + mismatch
        if total_cmp:
            logger.info(
                f"  중첩 구간 종가 비교: 일치 {match:,} / 불일치 {mismatch:,} "
                f"(불일치율 {100.0 * mismatch / total_cmp:.2f}%)"
            )
    logger.info(
        "  판정: 기존 펀더멘털 행은 전부 adj_factor=1.0 이고 daily_candles 는 raw,"
    )
    logger.info(
        "        중첩 구간 종가가 거의 일치 -> 동일 스케일. adj_factor=1.0 부여 시"
    )
    logger.info(
        "        2025-07 경계에서 가격 점프(불연속) 위험 없음. 기존 행은 수정하지 않음."
    )

    # ── 샘플 행 (오래된 날짜 1개 + 중간 날짜 1개) ─────────────────
    logger.info("")
    logger.info("─── [샘플 행 - INSERT 될 행] ───")
    logger.info("  포맷: stock_code | date | open | high | low | close | volume | trading_value | market_cap | adj_factor")
    sample_old = next((r for r in would_insert if r[1].year == 2021), None)
    sample_mid = next((r for r in would_insert if r[1].year == 2023), None)
    for label, r in (("2021 샘플", sample_old), ("2023 샘플", sample_mid)):
        if r is None:
            logger.info(f"  [{label}] 해당 연도 백필 행 없음")
            continue
        logger.info(
            f"  [{label}] {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | "
            f"{r[5]} | {r[6]} | {r[7]} | {r[8]} | {BACKFILL_ADJ_FACTOR}"
        )

    # ── 기존 행 무수정 확인 ───────────────────────────────────────
    logger.info("")
    logger.info("─── [기존 행 보존 확인] ───")
    logger.info(
        f"  INSERT ... ON CONFLICT DO NOTHING 만 사용 -> 기존 {len(existing_keys):,}개 행 "
        f"수정/삭제 0건 (DRY-RUN 이므로 DB 미변경)"
    )

    elapsed = time.time() - t0
    logger.info("")
    logger.info(f"dry-run 완료. 소요: {_fmt_elapsed(elapsed)}")
    logger.info(f"로그 파일: {_LOG_FILE}")
    logger.info("")
    logger.info("--apply 플래그로 재실행하면 INSERT + returns 재계산을 수행합니다.")


# ─────────────────────────────────────────────────────────────────────────────
# APPLY: 실제 INSERT + returns 재계산 (사용자 명시 승인 후에만 사용)
# ─────────────────────────────────────────────────────────────────────────────
def run_apply() -> None:
    logger.info("=" * 60)
    logger.info("APPLY mode -- INSERT 실행 (ON CONFLICT DO NOTHING)")
    logger.info("=" * 60)

    t0 = time.time()

    # ── 0. 유니버스 로드 ──────────────────────────────────────────
    tgt_conn = _connect(TARGET_DSN)
    universe = _load_universe(tgt_conn)
    logger.info(f"[유니버스] 펀더멘털 종목 {len(universe):,}개")

    # ── 1. 소스 전체 로드 ─────────────────────────────────────────
    logger.info("[1/4] 소스 데이터 로드 중...")
    src_conn = _connect(SOURCE_DSN)
    src_cur = src_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    src_cur.execute(SQL_SELECT_SOURCE, (universe,))
    source_rows = src_cur.fetchall()
    src_cur.close()
    src_conn.close()

    total_source = len(source_rows)
    logger.info(f"  로드 완료: {total_source:,}행")

    if total_source == 0:
        logger.warning("소스 데이터 없음. 종료.")
        tgt_conn.close()
        return

    # ── 2. 배치 INSERT (ON CONFLICT DO NOTHING) ───────────────────
    logger.info(f"[2/4] INSERT 시작 (flush {BATCH_SIZE}행 마다)...")

    now_ts = datetime.now()

    # _load_universe()의 SELECT로 열린 묵시적 트랜잭션을 닫은 후 autocommit 설정
    tgt_conn.rollback()
    tgt_conn.autocommit = False
    tgt_cur = tgt_conn.cursor()

    inserted_total = 0
    batch: list[tuple] = []
    last_log_pct = -1

    try:
        for i, row in enumerate(source_rows):
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
                BACKFILL_ADJ_FACTOR,  # adj_factor
                now_ts,               # created_at
                now_ts,               # updated_at
            ))

            if len(batch) >= BATCH_SIZE:
                psycopg2.extras.execute_values(
                    tgt_cur, SQL_INSERT, batch, page_size=len(batch)
                )
                inserted_total += tgt_cur.rowcount if tgt_cur.rowcount >= 0 else 0
                batch = []

                pct = int(i / total_source * 100)
                if pct // 10 > last_log_pct // 10:
                    elapsed = time.time() - t0
                    logger.info(
                        f"  진행: {pct}% ({i:,}/{total_source:,}행, {_fmt_elapsed(elapsed)} 경과)"
                    )
                    last_log_pct = pct

        if batch:
            psycopg2.extras.execute_values(
                tgt_cur, SQL_INSERT, batch, page_size=len(batch)
            )
            inserted_total += tgt_cur.rowcount if tgt_cur.rowcount >= 0 else 0

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

    # ── 3. returns / volatility 재계산 (펀더멘털 종목 한정, 멱등) ──
    logger.info("[3/4] returns_1d/5d/20d + volatility_20d 재계산 중 (펀더멘털 종목 한정)...")

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

    # ── 4. 검증 ───────────────────────────────────────────────────
    logger.info("[4/4] 검증 쿼리 실행 중...")
    tgt_cur.execute(
        """
        SELECT MIN(date), MAX(date), COUNT(*), COUNT(DISTINCT stock_code)
        FROM daily_prices
        WHERE stock_code IN (SELECT DISTINCT stock_code FROM financial_statements)
        """
    )
    v_min, v_max, v_rows, v_stocks = tgt_cur.fetchone()
    logger.info(
        f"  [검증] 펀더멘털 daily_prices 범위: {v_min} ~ {v_max}, "
        f"행수: {v_rows:,}, 종목: {v_stocks:,}"
    )

    tgt_cur.close()
    tgt_conn.close()

    total_elapsed = time.time() - t0
    logger.info("")
    logger.info(f"APPLY 완료. 총 소요: {_fmt_elapsed(total_elapsed)}")
    logger.info(f"로그 파일: {_LOG_FILE}")


# ─────────────────────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "strategy_analysis.daily_candles → robotrader.daily_prices "
            "펀더멘털 유니버스 다년치 백필 (기본 dry-run)"
        )
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

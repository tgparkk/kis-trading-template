"""
KOSPI 종합지수 일봉 백필 스크립트 (Phase 3a — Weinstein Mansfield RS)

기능:
  1. FinanceDataReader(FDR) DataReader('KS11') 로 KOSPI 종합지수 일봉 수집
  2. 연도별 배치로 2021-01 ~ 현재 수집
  3. robotrader.daily_prices 에 stock_code='KOSPI' 로 INSERT ON CONFLICT DO NOTHING (멱등)

용도:
  Weinstein Stage Analysis 백테스트의 Mansfield Relative Strength 분모.
  시장 프록시가 필요한 모든 상대강도/베타 계산에 재사용 가능.

실행:
  python scripts/backfill_kospi_index.py --dry-run     # dry-run (DB 저장 없음)
  python scripts/backfill_kospi_index.py --pilot       # 2024-01 ~ 현재 (~1.5년, 빠른 확인)
  python scripts/backfill_kospi_index.py --yes         # 전체 2021-01 ~ 현재 본 적재

환경:
  .env 파일: TIMESCALE_HOST, TIMESCALE_PORT, TIMESCALE_USER, TIMESCALE_PASSWORD, TIMESCALE_DB
  finance-datareader 필요: pip install finance-datareader

절대 금지:
  - DELETE/UPDATE 없음 (INSERT ON CONFLICT DO NOTHING만)
  - DROP/TRUNCATE 없음
  - rate limit 준수: 연도별 배치 + sleep 1.0초
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime

import psycopg2
import psycopg2.extras

# ─────────────────────────────────────────────────────────────────────────────
# 프로젝트 루트를 sys.path에 추가
# ─────────────────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(_ROOT))

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT, ".env"))

# ─────────────────────────────────────────────────────────────────────────────
# 로깅
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────────────────────
TODAY = date.today()
BACKFILL_START = date(2021, 1, 4)   # 전체 백필 시작일
PILOT_START    = date(2024, 1, 2)   # 파일럿: ~1.5년

FDR_SLEEP = 1.0   # 연도별 호출 사이 sleep (rate limit)

# daily_prices 에 저장할 KOSPI 식별자
KOSPI_CODE = "KOSPI"

# FinanceDataReader KOSPI 종합지수 티커
# KS11 = KOSPI 종합지수 (Yahoo Finance / FDR 표준 코드)
FDR_TICKER = "KS11"

_DB_DEFAULTS = dict(
    host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
    port=int(os.getenv("TIMESCALE_PORT", "5433")),
    user=os.getenv("TIMESCALE_USER", "robotrader"),
    password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    database=os.getenv("TIMESCALE_DB", "robotrader"),
)


def _get_conn():
    return psycopg2.connect(**_DB_DEFAULTS)


# ─────────────────────────────────────────────────────────────────────────────
# 연도별 윈도우 생성
# ─────────────────────────────────────────────────────────────────────────────

def _yearly_windows(start: date, end: date) -> list[tuple[str, str]]:
    """start ~ end 기간을 연도별 (fromdate, todate) 윈도우로 분할."""
    windows = []
    cur_year = start.year
    while cur_year <= end.year:
        win_start = max(start, date(cur_year, 1, 1))
        win_end   = min(end,   date(cur_year, 12, 31))
        if win_start <= win_end:
            windows.append((win_start.strftime("%Y%m%d"), win_end.strftime("%Y%m%d")))
        cur_year += 1
    return windows


# ─────────────────────────────────────────────────────────────────────────────
# pykrx 데이터 수집
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_kospi_year(fromdate: str, todate: str) -> list[dict]:
    """FinanceDataReader 로 KOSPI 종합지수(KS11) 일봉 수집.

    Returns list of dicts: {trade_date, open, high, low, close, volume}
    """
    try:
        import FinanceDataReader as fdr
    except ImportError:
        logger.error("[FDR] finance-datareader 미설치 — pip install finance-datareader")
        return []

    import pandas as pd

    try:
        df = fdr.DataReader(FDR_TICKER, fromdate, todate)
    except Exception as exc:
        logger.warning("[FDR] KS11 %s~%s 조회 실패: %s", fromdate, todate, exc)
        return []

    if df is None or df.empty:
        logger.warning("[FDR] KS11 %s~%s 조회 결과 없음", fromdate, todate)
        return []

    rows = []
    for idx, row in df.iterrows():
        # DatetimeIndex → date
        if hasattr(idx, 'date'):
            trade_date = idx.date()
        elif isinstance(idx, str):
            try:
                trade_date = datetime.strptime(idx[:10], "%Y-%m-%d").date()
            except ValueError:
                logger.debug("[FDR] 날짜 파싱 실패: %s", idx)
                continue
        else:
            continue

        def _safe(col_candidates, default=None):
            for c in col_candidates:
                if c in row.index and pd.notna(row[c]):
                    return float(row[c])
            return default

        open_  = _safe(["Open", "open", "시가"])
        high   = _safe(["High", "high", "고가"])
        low    = _safe(["Low",  "low",  "저가"])
        close  = _safe(["Close", "close", "종가"])
        volume_val = None
        for c in ["Volume", "volume", "거래량"]:
            if c in row.index and pd.notna(row[c]):
                try:
                    volume_val = int(row[c])
                except (ValueError, TypeError):
                    volume_val = None
                break

        if close is None:
            logger.debug("[FDR] close 없음: %s", trade_date)
            continue

        # KOSPI 지수 상식 범위 체크 (500 ~ 15,000)
        if not (500.0 <= close <= 15000.0):
            logger.warning("[FDR] KOSPI 종가 범위 이상: %s close=%.2f (500~15000 기대)", trade_date, close)
            continue

        rows.append({
            "trade_date": trade_date,
            "open":   open_,
            "high":   high,
            "low":    low,
            "close":  close,
            "volume": volume_val,
        })

    if rows:
        logger.debug("[FDR] %s~%s: %d건 파싱 완료", fromdate, todate, len(rows))

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# DB 삽입
# ─────────────────────────────────────────────────────────────────────────────

def _insert_batch(rows: list[dict], dry_run: bool) -> int:
    """rows를 daily_prices(stock_code='KOSPI')에 INSERT ON CONFLICT DO NOTHING.

    Returns: 신규 삽입 건수 (dry-run 시 수집 건수 반환)
    """
    if not rows:
        return 0
    if dry_run:
        return len(rows)

    # daily_prices 컬럼: stock_code, date, open, high, low, close, volume, trading_value, market_cap
    # KOSPI 지수는 trading_value/market_cap 없음 → NULL
    sql = """
        INSERT INTO daily_prices
            (stock_code, date, open, high, low, close, volume)
        VALUES %s
        ON CONFLICT (stock_code, date) DO NOTHING
    """
    values = [
        (
            KOSPI_CODE,
            r["trade_date"].strftime("%Y-%m-%d"),
            r["open"],
            r["high"],
            r["low"],
            r["close"],
            r["volume"],
        )
        for r in rows
    ]
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, values, page_size=500)
            inserted = cur.rowcount
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("[DB] INSERT 실패: %s", exc)
        inserted = 0
    finally:
        conn.close()
    return inserted


# ─────────────────────────────────────────────────────────────────────────────
# 검증 SELECT
# ─────────────────────────────────────────────────────────────────────────────

def _verify_db() -> None:
    """적재 결과 검증 SELECT."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*)      AS rows,
                    MIN(date)     AS min_date,
                    MAX(date)     AS max_date,
                    AVG(close)    AS avg_close,
                    MIN(close)    AS min_close,
                    MAX(close)    AS max_close
                FROM daily_prices
                WHERE stock_code = %s
                """,
                (KOSPI_CODE,),
            )
            row = cur.fetchone()
        conn.close()
        if row:
            logger.info("")
            logger.info("[DB] daily_prices WHERE stock_code='%s' 현황:", KOSPI_CODE)
            logger.info("  rows      : %d", row[0])
            logger.info("  min_date  : %s", row[1])
            logger.info("  max_date  : %s", row[2])
            logger.info("  avg_close : %.2f", float(row[3]) if row[3] else 0.0)
            logger.info("  min_close : %.2f", float(row[4]) if row[4] else 0.0)
            logger.info("  max_close : %.2f", float(row[5]) if row[5] else 0.0)
    except Exception as exc:
        logger.warning("[DB] 검증 SELECT 실패: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="KOSPI 종합지수 일봉 백필 스크립트 (Phase 3a — Weinstein Mansfield RS)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 저장 없이 예상 건수만 출력")
    parser.add_argument("--pilot", action="store_true",
                        help="파일럿: 2024-01 ~ 현재 (~1.5년)")
    parser.add_argument("--yes", action="store_true",
                        help="전체 2021-01 ~ 현재 본 적재 확인 대화 건너뜀")
    args = parser.parse_args()

    # 기간 결정
    if args.pilot:
        start_date = PILOT_START
        mode = "파일럿 (2024-01 ~ 현재)"
    else:
        start_date = BACKFILL_START
        mode = "전체 (2021-01 ~ 현재)"

    end_date = TODAY

    # 전체 본 적재 확인
    if not args.pilot and not args.dry_run and not args.yes:
        print("=" * 60)
        print("경고: 전체 2021-01 ~ 현재 본 적재를 시도합니다.")
        print("사장님 결재 완료 후 진행하세요.")
        print("dry-run 먼저 실행하려면 --dry-run 옵션을 사용하세요.")
        print("=" * 60)
        confirm = input("계속하시겠습니까? (yes 입력): ").strip().lower()
        if confirm != "yes":
            print("취소됨.")
            return

    windows = _yearly_windows(start_date, end_date)

    logger.info("=" * 60)
    logger.info("KOSPI 종합지수 일봉 백필 시작")
    logger.info("모드: %s", mode)
    logger.info("기간: %s ~ %s (%d개 연도별 윈도우)", start_date, end_date, len(windows))
    logger.info("stock_code: '%s'", KOSPI_CODE)
    logger.info("dry-run: %s", args.dry_run)
    logger.info("=" * 60)

    est_sec = len(windows) * FDR_SLEEP
    logger.info("예상 소요 시간: %.0f초", est_sec)

    total_fetched = 0
    total_inserted = 0
    missing_years: list[str] = []

    for win_from, win_to in windows:
        logger.info("[KOSPI] %s ~ %s 수집 중...", win_from, win_to)
        rows = _fetch_kospi_year(win_from, win_to)

        if not rows:
            missing_years.append(win_from[:4])
            logger.warning("[KOSPI] %s 데이터 없음", win_from[:4])
            time.sleep(FDR_SLEEP)
            continue

        total_fetched += len(rows)
        inserted = _insert_batch(rows, dry_run=args.dry_run)
        total_inserted += inserted

        logger.info(
            "[KOSPI] %s: %d건 수집, %d건 %s (close 범위: %.2f ~ %.2f)",
            win_from[:4],
            len(rows),
            inserted,
            "(dry-run)" if args.dry_run else "삽입",
            min(r["close"] for r in rows),
            max(r["close"] for r in rows),
        )
        time.sleep(FDR_SLEEP)

    # 최종 보고
    logger.info("")
    logger.info("=" * 60)
    logger.info("KOSPI 종합지수 일봉 백필 완료")
    logger.info("=" * 60)
    logger.info("  총 수집: %d건", total_fetched)
    logger.info("  총 삽입 (신규): %d건", total_inserted)
    logger.info("  데이터 없는 연도: %d개", len(missing_years))
    if missing_years:
        for y in missing_years:
            logger.warning("    - 누락: %s", y)

    # 영업일 기준 예상 행 수 안내
    years = (end_date - start_date).days / 365.25
    est_rows = int(years * 252)
    logger.info("  예상 행 수 (참고): ~%d건 (연 252 영업일 기준)", est_rows)

    if not args.dry_run:
        _verify_db()
    else:
        logger.info("")
        logger.info("[dry-run] 실제 DB 저장은 하지 않았습니다.")
        logger.info("[dry-run] 실제 백필하려면 --pilot 또는 --yes 옵션으로 재실행하세요.")


if __name__ == "__main__":
    main()

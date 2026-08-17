# -*- coding: utf-8 -*-
"""
외국인 순매수 백필 스크립트 (Phase 5 — F-06)
============================================
소스: 네이버 금융 frgn.naver (종목별 일별 외국인 순매매량)
종목목록 **읽기**: 일봉 resolver(= kis_template).`daily_prices`
  (2026-08-17 정정 — 옛 문구 「robotrader DB daily_prices 305종목」은 폐기 예정 DB)
기간: 가능한 전체 (네이버 최대 약 40페이지 × 20일 = ~800일)
**쓰기**: `robotrader_quant.foreign_flow` — 🔴 **동결 레거시**(2026-07-10)에 쓴다.
  실행 전 `TIMESCALE_DB` 를 명시해야 한다(fail-fast, `_quant_write_dsn()` 참조).

PIT 보장:
- 외국인 순매수는 T일 마감 후 발표 → T일 데이터를 T일로 저장
- 시그널 생성 시 shift(1)로 T-1 참조 (forward-leak 없음)

실행:
    python scripts/backfill_foreign_flow.py [--pilot] [--workers N] [--max-pages N]
"""
from __future__ import annotations

import argparse
import logging
import os as _os
import sys as _sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
import psycopg2.extras
import pandas as pd

# fetch_foreign_naver 는 라이브 수집기가 소유 → collectors 로 승격 (2026-07-02 Phase1).
# 직접 실행(python scripts/backfill_foreign_flow.py) 시 sys.path[0]=scripts/ 라 collectors 가
# 안 잡히므로 역방향 import 직전에 repo 루트를 sys.path 에 부트스트랩한다.
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collectors.foreign_flow_fetcher import _make_session, fetch_foreign_naver  # noqa: E402,F401
from config.constants import (  # noqa: E402
    require_explicit_target_db, resolve_daily_source_db)

# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PILOT_CODES = ["005930", "000660", "005380", "035420", "051910"]

# 🔴 이 스크립트의 **쓰기 대상은 동결 레거시 `robotrader_quant`** 다(2026-07-10 동결,
#    형제 봇 중단). 그 사실 자체는 이번 `robotrader` 폐기 범위 «밖»이라 대상 DB 를
#    바꾸지 않는다 — 바꾸면 라이브 SSOT(kis_template)에 INSERT 가 나간다.
# ⚠️ user 의 'robotrader' 는 **롤명**이라 그대로 둔다(DB명과 동음이의).
DB_QUANT = dict(
    host="127.0.0.1", port=5433, dbname="robotrader_quant",
    user="robotrader", password="1234"
)


def _quant_write_dsn() -> dict:
    """foreign_flow **쓰기** 대상 DSN — 연결 전 fail-fast.

    🔑 2026-08-17 정정 — 가드가 «엉뚱한 연결»에 붙어 있었다:
      원래 fail-fast 는 `_rt_dsn()`(종목목록 **읽기**)에 걸려 있었다. 그런데 이
      스크립트에서 위험한 쪽은 CREATE TABLE / INSERT 를 치는 **이쪽**이다.
      읽기는 SSOT 를 오염시킬 수 없다 ⇒ 가드를 쓰기로 옮긴다.

    ⚠️ 반환값이 아니라 **전제조건**으로 쓴다. `require_explicit_target_db()` 의
      리턴(=TIMESCALE_DB 값)을 그대로 dbname 에 꽂으면, TIMESCALE_DB=kis_template
      인 셸에서 이 백필이 **라이브 SSOT 에 INSERT** 하게 된다 — 정확히 이 가드가
      막으려던 사고다. 그래서 대상은 DB_QUANT 로 고정하고, 가드는 「사람이 대상
      DB 를 의식하고 실행했는가」만 묻는다(미지정이면 SystemExit).
    """
    require_explicit_target_db(
        "foreign_flow 백필 **쓰기** 실행 확인 (실제 대상은 robotrader_quant 고정)")
    return DB_QUANT


def _rt_dsn() -> dict:
    """종목목록(`daily_prices`) **읽기** 대상 — 일봉 resolver 경유.

    2026-08-17: 하드코딩 'robotrader' → 한 번 `require_explicit_target_db` 로
    갔다가 **resolver 로 되돌렸다**. 읽기 경로에 라이브 운영 env(TIMESCALE_DB)를
    요구하면 clean checkout·워크트리·CI 에서 죽는다(2026-07-16 통일이 고친 문제).
    fail-fast 는 위 `_quant_write_dsn()` 이 맡는다.
    ⚠️ user 의 'robotrader' 는 **롤명**이라 그대로 둔다(DB명과 동음이의).
    """
    return dict(host="127.0.0.1", port=5433, user="robotrader", password="1234",
                dbname=resolve_daily_source_db())

DDL = """
CREATE TABLE IF NOT EXISTS foreign_flow (
    stock_code      VARCHAR(10) NOT NULL,
    date            DATE        NOT NULL,
    foreign_net_vol BIGINT,
    source          VARCHAR(20) DEFAULT 'naver',
    created_at      TIMESTAMP   DEFAULT NOW(),
    PRIMARY KEY (stock_code, date)
);
CREATE INDEX IF NOT EXISTS ix_foreign_flow_date ON foreign_flow (date);
"""


# ─────────────────────────────────────────────────────────────────────────────
# 네이버 금융 수집 — _make_session · fetch_foreign_naver 는
# collectors/foreign_flow_fetcher.py 로 승격 (2026-07-02 Phase1), 위 역방향 import 로 재사용.
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# DB 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def ensure_table() -> None:
    conn = psycopg2.connect(**_quant_write_dsn())
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
        logger.info("[DB] foreign_flow 테이블 준비 완료")
    finally:
        conn.close()


def get_stock_codes(pilot: bool = False) -> list[str]:
    if pilot:
        return PILOT_CODES
    conn = psycopg2.connect(**_rt_dsn())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT stock_code FROM daily_prices "
                "WHERE stock_code ~ %s ORDER BY stock_code",
                ("^[0-9]{6}$",),
            )
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def get_existing_dates(code: str) -> set:
    conn = psycopg2.connect(**_quant_write_dsn())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT date FROM foreign_flow WHERE stock_code = %s", (code,))
            return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


def upsert_rows(rows: list[tuple]) -> int:
    if not rows:
        return 0
    conn = psycopg2.connect(**_quant_write_dsn())
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO foreign_flow (stock_code, date, foreign_net_vol, source)
                VALUES %s
                ON CONFLICT (stock_code, date) DO NOTHING
                """,
                rows,
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# 종목별 수집 + 적재 (스레드 단위)
# ─────────────────────────────────────────────────────────────────────────────

def collect_and_insert(code: str, max_pages: int) -> tuple[str, int, str]:
    """단일 종목 수집 + 적재. (code, inserted, status) 반환."""
    session = _make_session()
    try:
        df = fetch_foreign_naver(code, max_pages=max_pages, session=session)
        if df.empty:
            return code, 0, "empty"

        existing = get_existing_dates(code)
        rows = []
        for _, row in df.iterrows():
            if row["date"] not in existing:
                vol = int(row["foreign_net_vol"]) if pd.notna(row["foreign_net_vol"]) else None
                rows.append((code, row["date"], vol, "naver"))

        inserted = upsert_rows(rows)
        return code, inserted, "ok"
    except Exception as e:
        return code, 0, f"error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="외국인 순매수 백필 (네이버 금융)")
    parser.add_argument("--pilot", action="store_true", help="파일럿 5종목만")
    parser.add_argument("--workers", type=int, default=5, help="병렬 스레드 수 (기본 5)")
    parser.add_argument("--max-pages", type=int, default=40, help="종목당 최대 페이지 (기본 40 ≈ 800일)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("외국인 순매수 백필 시작")
    logger.info("모드: %s | workers=%d | max_pages=%d",
                "파일럿" if args.pilot else "전체", args.workers, args.max_pages)
    logger.info("=" * 60)

    ensure_table()

    codes = get_stock_codes(pilot=args.pilot)
    logger.info("[대상] %d종목", len(codes))

    total_inserted = 0
    errors: list[tuple[str, str]] = []
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(collect_and_insert, code, args.max_pages): code for code in codes}
        done = 0
        for future in as_completed(futures):
            code, inserted, status = future.result()
            done += 1
            total_inserted += inserted
            elapsed = time.time() - t_start
            eta = elapsed / done * (len(codes) - done) if done > 0 else 0
            if "error" in status:
                errors.append((code, status))
                logger.warning("[%d/%d] %s: %s", done, len(codes), code, status)
            else:
                logger.info("[%d/%d] %s: +%d행 (%s) ETA=%.0fs",
                            done, len(codes), code, inserted, status, eta)

    elapsed_total = time.time() - t_start
    logger.info("=" * 60)
    logger.info("백필 완료: 총 %d행 삽입 / %d종목 / %.1f초", total_inserted, len(codes), elapsed_total)
    if errors:
        logger.warning("오류 %d종목: %s", len(errors), errors[:10])

    conn = psycopg2.connect(**_quant_write_dsn())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), COUNT(DISTINCT stock_code), MIN(date), MAX(date) FROM foreign_flow"
            )
            row = cur.fetchone()
        logger.info("[DB] foreign_flow: 총 %s행 / %s종목 / %s ~ %s", *row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

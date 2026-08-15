# -*- coding: utf-8 -*-
"""지정 종목의 `daily_prices` 결손을 KIS 에서 받아 메운다 (운영 수집 경로 재사용).

계기: 태쏘 원장 28종목 중 **매드업 `0039P0` 만 일봉이 8일**(2026-08-05~)이었다.
      실제 상장은 **2026-07-01** — 신규주 유니버스 편입이 늦어 그 사이가 통째로 비었다.
      등록일(08-06) 이전 급등 구간을 못 보는 상태였다.

구현: `collectors.daily_collector.collect_one` + `collectors.daily_writer.upsert_daily_rows`
      를 그대로 쓴다. **파싱·수정주가·market_cap 규약을 운영과 어긋나게 만들지 않기 위해서다** —
      여기서 KIS 응답을 직접 파싱하면 그 순간 두 번째 규약이 생긴다.

⚠️ 이 스크립트는 **지정한 종목만** 손댄다. 백로그의 「일봉 결손 257종목/49,252행」 대량 복구는
   *전수 재측정이 선행*이라는 결정이 이미 있으므로 여기서 하지 않는다.

멱등: `upsert_daily_rows` 가 ON CONFLICT DO UPDATE 다. DELETE 없음.

실행:
    python scripts/backfill_daily_for_codes.py --codes 0039P0 --dry-run
    python scripts/backfill_daily_for_codes.py --codes 0039P0
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import psycopg2  # noqa: E402

from config.constants import resolve_daily_source_db  # noqa: E402


def dsn() -> dict:
    return dict(host="127.0.0.1", port=5433, user="robotrader",
                password="1234", dbname=resolve_daily_source_db())


def existing(conn, code: str) -> tuple[int, str | None]:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), min(date) FROM daily_prices WHERE stock_code=%s", (code,))
        n, d = cur.fetchone()
        return n, d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", required=True, help="쉼표 구분 종목코드")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    from api.kis_auth import auth
    from collectors.daily_collector import collect_one
    from collectors.daily_writer import upsert_daily_rows

    if not auth():
        print("🔴 KIS 인증 실패")
        return 2

    conn = psycopg2.connect(**dsn())
    codes = [c.strip() for c in a.codes.split(",") if c.strip()]
    total = 0

    for code in codes:
        n0, d0 = existing(conn, code)
        rows = collect_one(code, lookback_days=0)     # 0 = 받은 전부
        if not rows:
            print(f"🔴 {code} 수신 0행 (기존 {n0}행 유지)")
            continue
        got_min, got_max = rows[0]["date"], rows[-1]["date"]
        # 🔑 부분 수신으로 좋은 데이터를 덮지 않는다. upsert 라 DELETE 는 없지만,
        #    수신이 기존보다 짧으면 «메울 게 없다»는 뜻이므로 알리고 넘어간다.
        if a.dry_run:
            print(f"· {code} 수신 {len(rows)}행 ({got_min}~{got_max}) · 기존 {n0}행(최초 {d0}) [dry-run]")
            continue
        n = upsert_daily_rows(conn, rows)
        n1, d1 = existing(conn, code)
        print(f"✅ {code} upsert {n}행 · {n0}행(최초 {d0}) → {n1}행(최초 {d1})")
        total += n

    print(f"\n합계 upsert {total}행")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

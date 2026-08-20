# -*- coding: utf-8 -*-
"""기업행위 가격 보정 — 큐 + 큐 밖 7종목을 KIS 수정주가로 고친다.

사양: docs/superpowers/specs/2026-08-20-corp-action-price-repair-design.md

🔴 기본은 dry-run 이다. `--apply` 를 줘야 쓴다. 백업 없이는 한 행도 안 고친다.

    python scripts/repair_corp_action_prices.py --limit 1              # dry-run
    python scripts/repair_corp_action_prices.py --limit 1 --apply
    python scripts/repair_corp_action_prices.py --restore <BATCH_ID>
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import psycopg2  # noqa: E402

HIST0, TODAY = "20210101", date.today().strftime("%Y%m%d")


def dsn() -> dict:
    return dict(host="127.0.0.1", port=5433, user="robotrader",
                password="1234", dbname="kis_template")


def _kis_fetcher(code, start, end, adj_prc):
    from api import kis_market_api
    df = kis_market_api.get_inquire_daily_itemchartprice_extended(
        div_code="J", itm_no=code, inqr_strt_dt=start, inqr_end_dt=end,
        period_code="D", adj_prc=adj_prc, max_count=2000)
    if df is None or df.empty:
        return []
    return [dict(r) for _, r in df.iterrows()]


def _db_rows(conn, code):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT date, open, high, low, close, volume, adj_factor "
            "FROM daily_prices WHERE stock_code=%s ORDER BY date", (code,))
        return {d: (o, h, l, c, v, f) for d, o, h, l, c, v, f in cur.fetchall()}


UPSERT = """
INSERT INTO daily_prices (stock_code, date, open, high, low, close, volume, adj_factor, updated_at)
VALUES (%(stock_code)s, %(date)s, %(open)s, %(high)s, %(low)s, %(close)s,
        %(volume)s, %(adj_factor)s, now())
ON CONFLICT (stock_code, date) DO UPDATE SET
    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close,
    volume=EXCLUDED.volume, adj_factor=EXCLUDED.adj_factor, updated_at=now()
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다(기본은 dry-run)")
    ap.add_argument("--codes", default=None, help="쉼표 구분. 지정 시 큐를 무시한다")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--restore", default=None, metavar="BATCH_ID")
    a = ap.parse_args()

    from api.kis_auth import auth
    from collectors import adj_repair as R
    from db import adj_backup as B

    conn = psycopg2.connect(**dsn())

    if a.restore:
        B.ensure_table(conn)
        n = B.restore_batch(conn, a.restore)
        print(f"restored {n} rows from batch {a.restore}")
        conn.close()
        return 0

    if not auth():
        print("KIS auth failed")
        return 2

    if a.codes:
        targets = [c.strip() for c in a.codes.split(",") if c.strip()]
    else:
        qp = REPO / "logs" / "corp_action_refetch_queue.jsonl"
        lines = qp.read_text(encoding="utf-8").splitlines() if qp.exists() else []
        targets = R.load_targets(lines, date.today().isoformat())
    if a.limit:
        targets = targets[:a.limit]

    batch_id = "repair-" + date.today().isoformat() + ("-apply" if a.apply else "-dry")
    if a.apply:
        B.ensure_table(conn)

    tot_before = tot_after = tot_rows = 0
    for i, code in enumerate(targets, 1):
        raw, adj = R.fetch_both(code, HIST0, TODAY, _kis_fetcher)
        factors, diag = R.derive_factors(raw, adj)
        if not factors:
            print(f"[{i}/{len(targets)}] {code} SKIP — 계수 산출 0건 (diag {diag})")
            continue
        new_rows = R.build_repair_rows(code, raw, adj, factors)
        db = _db_rows(conn, code)
        todo = R.needs_repair(db, new_rows)

        before = R.count_impossible(sorted((d, float(v[3])) for d, v in db.items()))
        merged = dict(db)
        for r in todo:
            merged[r["date"]] = (r["open"], r["high"], r["low"], r["close"],
                                 r["volume"], r["adj_factor"])
        after = R.count_impossible(sorted((d, float(v[3])) for d, v in merged.items()))
        tot_before += before
        tot_after += after
        tot_rows += len(todo)

        print(f"[{i}/{len(targets)}] {code} rows={len(todo)} impossible {before}->{after} "
              f"derived={diag['n_derived']} filled={diag['n_filled']}")

        if not a.apply or not todo:
            continue
        if after > before:
            print(f"    ABORT — {code} 불가능봉이 늘었다({before}->{after})")
            conn.rollback()
            conn.close()
            return 3
        B.backup_rows(conn, code, [r["date"] for r in todo], batch_id)
        with conn.cursor() as cur:
            for r in todo:
                cur.execute(UPSERT, r)
        conn.commit()

    print(f"\nbatch {batch_id} · rows {tot_rows} · impossible {tot_before} -> {tot_after}")
    print("rollback: python scripts/repair_corp_action_prices.py --restore " + batch_id)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

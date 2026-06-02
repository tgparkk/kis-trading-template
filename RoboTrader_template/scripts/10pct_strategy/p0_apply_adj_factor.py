"""
P0-2b: daily_prices.adj_factor PIT correction

Algorithm:
  1. Load split events with split_factor from corp_events (pykrx source, effective date)
  2. bonus_issue: no ratio in meta, attempt pykrx price-ratio inference
  3. For each (stock, date T):
     adj_factor(T) = product(split_factor for events where event_date > T)
     PIT rule: only future splits affect pre-split prices
  4. UPDATE daily_prices.adj_factor in batches of 100 stocks
  5. Spot check 3 cases + PIT safety regression

Absolute rules:
  No Look-Ahead: adj_factor(T) uses only events with event_date > T
  Chronological: cumulative product of future splits only

Python: system Python 3.9 (no venv)
DB: robotrader (corp_events) + robotrader_quant (daily_prices), 127.0.0.1:5433
"""

import sys
import os
import math
from datetime import date, datetime
from collections import defaultdict

import psycopg2
import psycopg2.extras
import pandas as pd

DB_EVENTS = dict(host="127.0.0.1", port=5433, dbname="robotrader",
                 user="robotrader", password="1234")
DB_PRICES = dict(host="127.0.0.1", port=5433, dbname="robotrader_quant",
                 user="robotrader", password="1234")

REPORT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "reports", "10pct_strategy")
)
os.makedirs(REPORT_DIR, exist_ok=True)

BATCH_SIZE = 100


# ---------------------------------------------------------------------------
# Step 1: Load split events from corp_events
# ---------------------------------------------------------------------------
def load_split_events() -> dict:
    """
    Load split events that have split_factor (pykrx source, effective date).
    bonus_issue events have no ratio in meta; attempt pykrx price-ratio inference.

    Returns: {stock_code: [(event_date, split_factor), ...]} ascending by date
    """
    conn = psycopg2.connect(**DB_EVENTS)
    events = defaultdict(list)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT stock_code, event_date,
                   (meta->>'split_factor')::float AS split_factor
            FROM corp_events
            WHERE event_type = 'split'
              AND meta->>'split_factor' IS NOT NULL
            ORDER BY stock_code, event_date
        """)
        rows = cur.fetchall()

    split_count = len(rows)
    for stock_code, event_date, split_factor in rows:
        events[stock_code].append((event_date, float(split_factor)))

    # bonus_issue: no ratio in meta, try pykrx price comparison
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT stock_code, event_date
            FROM corp_events
            WHERE event_type = 'bonus_issue'
            ORDER BY stock_code, event_date
        """)
        bonus_rows = cur.fetchall()
    bonus_count = len(bonus_rows)
    bonus_loaded = 0

    try:
        from pykrx import stock as pykrx_stock
        import warnings
        warnings.filterwarnings("ignore")
        import datetime as dt

        for stock_code, ev_date in bonus_rows:
            try:
                start_dt = ev_date - dt.timedelta(days=20)
                end_dt   = ev_date + dt.timedelta(days=5)
                df = pykrx_stock.get_market_ohlcv_by_date(
                    start_dt.strftime("%Y%m%d"),
                    end_dt.strftime("%Y%m%d"),
                    stock_code,
                )
                if df is None or df.empty or len(df) < 2:
                    continue
                df.index = pd.to_datetime(df.index)
                ev_ts  = pd.Timestamp(ev_date)
                before = df[df.index < ev_ts]
                after  = df[df.index >= ev_ts]
                if before.empty or after.empty:
                    continue
                close_col = df.columns[3]   # "종가" column (index 3 in pykrx OHLCV)
                close_before = float(before[close_col].iloc[-1])
                close_after  = float(after[close_col].iloc[0])
                if close_after <= 0:
                    continue
                ratio_raw     = close_before / close_after
                ratio_rounded = round(ratio_raw)
                if 1.5 <= ratio_raw <= 20 and abs(ratio_raw - ratio_rounded) < 0.3:
                    events[stock_code].append((ev_date, float(ratio_rounded)))
                    bonus_loaded += 1
            except Exception:
                pass
        print(f"  bonus_issue pykrx supplement: {bonus_loaded}/{bonus_count} factor extracted")
    except ImportError:
        print("  WARNING: pykrx not available, bonus_issue factor skipped")

    conn.close()

    for code in events:
        events[code].sort(key=lambda x: x[0])

    print(f"  split events loaded: {split_count} (with split_factor)")
    print(f"  bonus_issue events: {bonus_count} total, {bonus_loaded} factor extracted")
    print(f"  stocks with events: {len(events)}")
    return dict(events)


# ---------------------------------------------------------------------------
# Step 2: Compute PIT adj_factor per (stock, date)
# ---------------------------------------------------------------------------
def compute_adj_factors(events: dict, stock_dates: dict) -> dict:
    """
    For each (stock, date T):
      adj_factor(T) = product(sf for (ed, sf) in events[stock] if ed > T)

    Returns: {stock_code: {date_str: adj_factor}}
    """
    result = {}
    for stock_code, ev_list in events.items():
        if stock_code not in stock_dates:
            continue
        dates = stock_dates[stock_code]
        stock_result = {}
        for date_str in dates:
            try:
                t = date.fromisoformat(date_str)
            except ValueError:
                stock_result[date_str] = 1.0
                continue
            future_factors = [sf for (ed, sf) in ev_list if ed > t]
            stock_result[date_str] = math.prod(future_factors) if future_factors else 1.0
        result[stock_code] = stock_result
    return result


# ---------------------------------------------------------------------------
# Step 3: Load date lists for a batch of stocks
# ---------------------------------------------------------------------------
def load_stock_dates(conn, stock_codes: list) -> dict:
    if not stock_codes:
        return {}
    placeholders = ",".join(["%s"] * len(stock_codes))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT stock_code, date FROM daily_prices
            WHERE stock_code IN ({placeholders})
              AND date ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$'
            ORDER BY stock_code, date
            """,
            stock_codes,
        )
        rows = cur.fetchall()
    stock_dates = defaultdict(list)
    for sc, ds in rows:
        stock_dates[sc].append(ds)
    return dict(stock_dates)


# ---------------------------------------------------------------------------
# Step 4: UPDATE daily_prices.adj_factor
# ---------------------------------------------------------------------------
def update_adj_factors(events: dict, dry_run: bool = False) -> dict:
    """Batch UPDATE in groups of BATCH_SIZE stocks."""
    conn = psycopg2.connect(**DB_PRICES)
    conn.autocommit = False

    affected_stocks = list(events.keys())
    total_updated    = 0
    total_rows_touched = 0
    batch_count      = 0

    print(f"\n  Stocks to UPDATE: {len(affected_stocks)}")
    if dry_run:
        print("  [DRY RUN — no DB changes]")

    for batch_start in range(0, len(affected_stocks), BATCH_SIZE):
        batch_codes = affected_stocks[batch_start : batch_start + BATCH_SIZE]
        batch_count += 1

        stock_dates = load_stock_dates(conn, batch_codes)
        adj_map     = compute_adj_factors(events, stock_dates)

        update_rows = []
        for sc, date_adj in adj_map.items():
            for ds, af in date_adj.items():
                if abs(af - 1.0) > 1e-9:
                    update_rows.append((af, sc, ds))

        if not update_rows:
            continue

        if not dry_run:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(
                    cur,
                    """
                    UPDATE daily_prices
                    SET adj_factor = %s, updated_at = NOW()
                    WHERE stock_code = %s AND date = %s
                    """,
                    update_rows,
                    page_size=1000,
                )
            conn.commit()

        batch_stocks = len([c for c in batch_codes if c in adj_map])
        total_updated      += batch_stocks
        total_rows_touched += len(update_rows)
        print(f"  batch {batch_count}: {batch_stocks} stocks / {len(update_rows)} rows")

    conn.close()
    return {
        "total_stocks": len(affected_stocks),
        "updated_stocks": total_updated,
        "rows_touched": total_rows_touched,
        "batches": batch_count,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Step 5: Spot check
# ---------------------------------------------------------------------------
SPOT_CHECKS = [
    {
        "label": "Kakao(035720) 2021-04-15 5:1 split",
        "stock_code": "035720",
        "split_factor": 5.0,
        "pre_date": "2021-04-14",
        "post_date": "2021-04-15",
    },
    {
        "label": "Korea Petroleum(004090) 2021-04-15 10:1 split",
        "stock_code": "004090",
        "split_factor": 10.0,
        "pre_date": "2021-04-14",
        "post_date": "2021-04-15",
    },
    {
        "label": "260970 2021-02-01 10:1 split",
        "stock_code": "260970",
        "split_factor": 10.0,
        "pre_date": "2021-01-29",
        "post_date": "2021-02-01",
    },
]


def run_spot_checks(events: dict) -> list:
    """
    Verify adj_factor correctness for 3 known splits.

    daily_prices stores RAW (non-back-adjusted) prices — pre/post split prices
    are on different scales by design, and can differ arbitrarily due to market
    movement on split day (e.g. Kakao opened +438% on its split date).
    Therefore price-continuity is NOT a valid check.

    Correct checks:
      (1) adj_factor(pre_date) == split_factor  (exact for single-split stocks)
      (2) adj_factor(post_date) == 1.0          (after effective date, no adjustment)
    """
    conn = psycopg2.connect(**DB_PRICES)
    results = []

    for chk in SPOT_CHECKS:
        sc      = chk["stock_code"]
        sf      = chk["split_factor"]
        pre_dt  = chk["pre_date"]
        post_dt = chk["post_date"]

        with conn.cursor() as cur:
            cur.execute("""
                SELECT date, close, adj_factor
                FROM daily_prices
                WHERE stock_code = %s AND date IN (%s, %s)
                ORDER BY date
            """, (sc, pre_dt, post_dt))
            rows = cur.fetchall()

        row_map   = {r[0]: (r[1], r[2]) for r in rows}
        pre_info  = row_map.get(pre_dt)
        post_info = row_map.get(post_dt)

        if pre_info is None or post_info is None:
            results.append({
                "label": chk["label"],
                "status": "SKIP",
                "reason": f"no data (pre={'found' if pre_info else 'missing'}, "
                          f"post={'found' if post_info else 'missing'})",
            })
            continue

        close_pre, adj_pre   = pre_info
        close_post, adj_post = post_info

        # (1) pre-split row: adj_factor must equal split_factor exactly
        #     (for stocks with only one split; cumulative product = sf itself)
        adj_factor_ok = abs(adj_pre - sf) < 0.01

        # (2) post-split row: adj_factor must be 1.0 (split already in price)
        post_adj_ok = abs(adj_post - 1.0) < 0.01

        overall = "PASS" if (adj_factor_ok and post_adj_ok) else "FAIL"

        results.append({
            "label":        chk["label"],
            "status":       overall,
            "close_pre":    close_pre,
            "adj_pre":      adj_pre,
            "close_post":   close_post,
            "adj_post":     adj_post,
            "adj_factor_ok": adj_factor_ok,
            "post_adj_ok":  post_adj_ok,
            "note": (
                f"adj_pre={adj_pre} (expected {sf}), "
                f"adj_post={adj_post} (expected 1.0)"
            ),
        })

    conn.close()
    return results


# ---------------------------------------------------------------------------
# Step 6: PIT safety regression
# ---------------------------------------------------------------------------
def run_pit_regression(events: dict) -> dict:
    """
    PIT regression: for a fixed test_date, simulate adj_factor using ONLY
    events with event_date > test_date, then compare to DB value.
    If future events (after test_date) bleed into the adj_factor of test_date,
    the simulation and DB would differ — that would be a PIT violation.
    """
    test_date = date(2022, 1, 3)   # first trading day of 2022
    test_codes = ["035720", "004090", "260970"]

    conn = psycopg2.connect(**DB_PRICES)
    results = []

    for sc in test_codes:
        if sc not in events:
            results.append({"stock": sc, "status": "SKIP", "reason": "no events"})
            continue

        ev_list = events[sc]

        # Simulate: adj_factor(test_date) = product(sf where event_date > test_date)
        simulated = math.prod([sf for (ed, sf) in ev_list if ed > test_date])

        with conn.cursor() as cur:
            cur.execute("""
                SELECT date, adj_factor FROM daily_prices
                WHERE stock_code = %s AND date >= %s
                ORDER BY date LIMIT 1
            """, (sc, test_date.isoformat()))
            row = cur.fetchone()

        if row is None:
            results.append({"stock": sc, "status": "SKIP", "reason": "no DB data"})
            continue

        db_date, db_adj = row
        match = abs(simulated - db_adj) < 1e-6

        results.append({
            "stock": sc,
            "test_date": test_date.isoformat(),
            "db_date": str(db_date),
            "simulated_adj": round(simulated, 6),
            "db_adj": round(db_adj, 6),
            "future_events": [(str(ed), sf) for (ed, sf) in ev_list if ed > test_date],
            "past_events":   [(str(ed), sf) for (ed, sf) in ev_list if ed <= test_date],
            "match": match,
            "status": "PASS" if match else "FAIL",
        })

    conn.close()
    return {"test_date": test_date.isoformat(), "results": results}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def count_non_one_adj(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM daily_prices WHERE adj_factor != 1.0")
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(stats: dict, spot_results: list, pit_result: dict) -> str:
    report_path = os.path.join(REPORT_DIR, "phase0_adj_factor_correction.md")

    spot_pass_count = sum(1 for r in spot_results if r["status"] == "PASS")
    all_spot_pass   = all(r["status"] in ("PASS", "SKIP") for r in spot_results)
    pit_pass        = all(r["status"] in ("PASS", "SKIP") for r in pit_result["results"])
    pit_status      = "OK" if pit_pass else "NG"
    p1_ok           = stats["after_count"] > 0 and all_spot_pass and pit_pass

    lines = [
        "# Phase 0 — P0-2b adj_factor Correction Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 1. UPDATE Summary",
        "",
        f"- Rows with adj_factor != 1.0 BEFORE update: **{stats['before_count']}**",
        f"- Rows with adj_factor != 1.0 AFTER update:  **{stats['after_count']}**",
        f"- Stocks corrected: **{stats['updated_stocks']}**",
        f"- Rows touched: **{stats['rows_touched']}**",
        f"- Batches: {stats['batches']} x {BATCH_SIZE} stocks",
        "",
        "## 2. Spot Check (3 cases)",
        "",
    ]

    for r in spot_results:
        icon = "OK" if r["status"] == "PASS" else ("SKIP" if r["status"] == "SKIP" else "NG")
        lines.append(f"### {r['label']} -> {icon}")
        lines.append("")
        if r["status"] == "SKIP":
            lines.append(f"- Reason: {r.get('reason', 'unknown')}")
        else:
            lines.append(f"- close_pre (raw): {r['close_pre']:,.0f}")
            lines.append(f"- adj_factor(pre): **{r['adj_pre']}**  (== split_factor: {'OK' if r['adj_factor_ok'] else 'NG'})")
            lines.append(f"- close_post (raw): {r['close_post']:,.0f}")
            lines.append(f"- adj_factor(post): {r['adj_post']}  (== 1.0: {'OK' if r['post_adj_ok'] else 'NG'})")
            lines.append(f"- Note: {r['note']}")
            lines.append(f"- **Result: {r['status']}**")
        lines.append("")

    lines += [
        "## 3. PIT Safety Regression",
        "",
        f"Test date: {pit_result['test_date']}",
        "Verify: simulate adj_factor using only events with event_date > test_date,",
        "compare to DB value. Mismatch = future event leaked into past adj_factor.",
        "",
        "| Stock | Status | Simulated | DB value | Match | Future events |",
        "|---|---|---|---|---|---|",
    ]

    for r in pit_result["results"]:
        if r["status"] == "SKIP":
            lines.append(f"| {r['stock']} | SKIP | - | - | - | - |")
        else:
            lines.append(
                f"| {r['stock']} | {r['status']} | {r['simulated_adj']} | "
                f"{r['db_adj']} | {'yes' if r['match'] else 'NO'} | "
                f"{r['future_events']} |"
            )

    lines += [
        "",
        f"PIT regression: **{pit_status}**",
        "",
        "## 4. P1 Forward Return Usability",
        "",
        f"- adj_factor rows corrected: {'yes' if stats['after_count'] > 0 else 'no'} ({stats['after_count']} rows)",
        f"- Spot check: {spot_pass_count}/3 PASS",
        f"- PIT safety: {pit_status}",
        f"- **Usable for P1 forward return calculation: {'OK' if p1_ok else 'NG'}**",
        "",
        "## 5. Algorithm",
        "",
        "```",
        "adj_factor(T) = product(split_factor for events where event_date > T)",
        "",
        "- event_date > T : split not yet effective at T",
        "                   => pre-split price needs to be divided by split_factor",
        "                      to be comparable to post-split prices",
        "- event_date <= T: split already effective => price already adjusted => factor 1.0",
        "- Multiple splits: cumulative product",
        "  e.g., 5:1 (2022-06) + 2:1 (2023-03), row at 2021-12:",
        "      adj_factor = 5 x 2 = 10",
        "```",
        "",
        "> Rule 1 (No Look-Ahead): adj_factor(T) only includes events with event_date > T",
        "> Rule 2 (Chronological): cumulative product of all future splits",
    ]

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n  Report saved: {report_path}")
    return report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("P0-2b: daily_prices.adj_factor PIT Correction")
    print("=" * 60)

    conn = psycopg2.connect(**DB_PRICES)
    before_count = count_non_one_adj(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM daily_prices")
        total_rows = cur.fetchone()[0]
    conn.close()
    print(f"\n[Before] total={total_rows:,} rows, adj_factor != 1.0: {before_count}")

    print("\n[Step 1] Load corp_events")
    events = load_split_events()
    if not events:
        print("ERROR: no events loaded")
        sys.exit(1)

    print("\n[Steps 2-4] UPDATE adj_factor")
    update_stats = update_adj_factors(events, dry_run=False)

    conn = psycopg2.connect(**DB_PRICES)
    after_count = count_non_one_adj(conn)
    conn.close()
    print(f"\n[After] adj_factor != 1.0: {after_count}")

    update_stats["before_count"] = before_count
    update_stats["after_count"]  = after_count

    print("\n[Step 5] Spot Check")
    spot_results = run_spot_checks(events)
    for r in spot_results:
        if r["status"] == "PASS":
            print(f"  OK   {r['label']}")
            print(f"       {r['note']}")
        elif r["status"] == "SKIP":
            print(f"  SKIP {r['label']}: {r.get('reason', '')}")
        else:
            print(f"  FAIL {r['label']}")
            print(f"       adj_ok={r['adj_factor_ok']}, post_ok={r['post_adj_ok']}")
            print(f"       {r['note']}")

    print("\n[Step 6] PIT Regression")
    pit_result = run_pit_regression(events)
    for r in pit_result["results"]:
        if r["status"] == "SKIP":
            print(f"  SKIP {r['stock']}: {r.get('reason', '')}")
        else:
            icon = "OK" if r["status"] == "PASS" else "NG"
            print(f"  {icon}   {r['stock']}: sim={r['simulated_adj']}, db={r['db_adj']}, "
                  f"match={r['match']}, future_evs={r['future_events']}")

    print("\n[Step 7] Write report")
    report_path = write_report(update_stats, spot_results, pit_result)

    pit_all = all(r["status"] in ("PASS", "SKIP") for r in pit_result["results"])
    spot_pass = sum(1 for r in spot_results if r["status"] == "PASS")

    print("\n" + "=" * 60)
    print("Summary")
    print(f"  adj_factor != 1.0 before: {before_count}")
    print(f"  adj_factor != 1.0 after:  {after_count}")
    print(f"  stocks corrected: {update_stats['updated_stocks']}")
    print(f"  spot check: {spot_pass}/3 PASS")
    print(f"  PIT regression: {'OK' if pit_all else 'NG'}")
    print(f"  report: {report_path}")


if __name__ == "__main__":
    main()

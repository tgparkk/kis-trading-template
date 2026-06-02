"""빠른 데이터 로딩 테스트."""
import sys, os, time
import pandas as pd
import psycopg2

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports", "10pct_strategy")
P5_DIR = os.path.join(REPORT_DIR, "phase5_signals")

print("[1] forward_returns parquet...", flush=True)
t0 = time.time()
fwd = pd.read_parquet(os.path.join(REPORT_DIR, "phase1_forward_returns.parquet"))
print(f"  shape={fwd.shape}  ({time.time()-t0:.1f}s)", flush=True)

print("[2] regime_segments.csv...", flush=True)
seg = pd.read_csv(os.path.join(REPORT_DIR, "phase0_regime_segments.csv"))
print(f"  shape={seg.shape}", flush=True)

print("[3] daily_prices DB query...", flush=True)
t0 = time.time()
conn = psycopg2.connect(host="127.0.0.1", port=5433, dbname="robotrader_quant",
                        user="robotrader", password="1234")
cur = conn.cursor()
cur.execute("""SELECT stock_code, date::text AS date, open, high, low, close,
               volume, trading_value, market_cap
               FROM daily_prices WHERE close > 0
               AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
               ORDER BY stock_code, date""")
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
conn.close()
prices = pd.DataFrame(rows, columns=cols)
prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
print(f"  shape={prices.shape}  ({time.time()-t0:.1f}s)", flush=True)

print("[4] ROE financial_statements...", flush=True)
t0 = time.time()
conn2 = psycopg2.connect(host="127.0.0.1", port=5433, dbname="robotrader_quant",
                         user="robotrader", password="1234")
cur2 = conn2.cursor()
cur2.execute("SELECT stock_code, report_date::text, roe FROM financial_statements WHERE roe IS NOT NULL ORDER BY stock_code, report_date")
roe_rows = cur2.fetchall()
conn2.close()
roe_raw = pd.DataFrame(roe_rows, columns=["stock_code","report_date","roe"])
print(f"  shape={roe_raw.shape}  ({time.time()-t0:.1f}s)", flush=True)

print("[5] VWAP parquet...", flush=True)
vwap_df = pd.read_parquet(os.path.join(P5_DIR, "vwap_signal_daily.parquet"))
print(f"  shape={vwap_df.shape}", flush=True)

print("[6] phase2a_filter_passed.csv...", flush=True)
f2a = pd.read_csv(os.path.join(REPORT_DIR, "phase2a_filter_passed.csv"))
print(f"  shape={f2a.shape}  cols={f2a.columns.tolist()}", flush=True)

print("ALL LOAD OK", flush=True)

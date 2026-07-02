"""Phase 4 사전 체크: DB 구조 + 신호 케이스 수 확인"""
import psycopg2
import pandas as pd
import sys

# 1) robotrader_quant daily_prices 구조 확인
print("=== robotrader_quant.daily_prices 구조 ===")
try:
    conn = psycopg2.connect(host="127.0.0.1", port=5433, database="robotrader_quant",
                            user="robotrader", password="1234")
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name='daily_prices'
        ORDER BY ordinal_position LIMIT 20
    """)
    for r in cur.fetchall():
        print(r)
    print("---")
    cur.execute("SELECT * FROM daily_prices LIMIT 2")
    cols = [d[0] for d in cur.description]
    print("COLS:", cols)
    for r in cur.fetchall():
        print(dict(zip(cols, r)))
    # 날짜 범위
    cur.execute("SELECT MIN(date), MAX(date), COUNT(DISTINCT stock_code), COUNT(*) FROM daily_prices")
    row = cur.fetchone()
    print(f"날짜범위: {row[0]}~{row[1]}, 종목수: {row[2]}, 총행: {row[3]}")
    conn.close()
except Exception as e:
    print(f"[ERROR] {e}")

print()
print("=== cases_v4.csv 신호 A/B 케이스 수 ===")
df = pd.read_csv("reports/signal_combo_aprmay/cases_v4.csv")
df["trade_date"] = df["trade_date"].astype(str)
print("총 케이스:", len(df))

# 신호 A: ma20_dist_pct >= 20
sig_a = df[df["ma20_dist_pct"] >= 20].copy()
print(f"신호A (ma20_dist_pct>=20): {len(sig_a)}건")

# 신호 B: ret_20d_pct>=25 AND atr_20d_pct>=8
sig_b = df[(df["ret_20d_pct"] >= 25) & (df["atr_20d_pct"] >= 8)].copy()
print(f"신호B (ret20d>=25 AND atr20d>=8): {len(sig_b)}건")

for sig_name, sig_df in [("A", sig_a), ("B", sig_b)]:
    is_c = sig_df[sig_df["trade_date"].between("20260401", "20260430")]
    oos_c = sig_df[sig_df["trade_date"].between("20260501", "20260523")]
    missing_0930 = sig_df["close_0930"].isna().sum()
    print(f"  신호{sig_name}: IS={len(is_c)}, OOS={len(oos_c)}, close_0930 null={missing_0930}")

print()
print("신호A 샘플 (ma20_dist_pct 상위 3):")
print(sig_a.nlargest(3, "ma20_dist_pct")[["trade_date","stock_code","stock_name","ma20_dist_pct","ret_20d_pct","atr_20d_pct","close_0930"]])

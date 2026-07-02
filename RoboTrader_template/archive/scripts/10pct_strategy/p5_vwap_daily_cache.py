"""
p5_vwap_daily_cache.py — VWAP Pullback 일별 시그널 캐시 생성
=============================================================
사장님 결재: 분봉 5,116만 행을 종목·일자별로 처리 → 일 단위 VWAP Pullback
플래그(pb_1.0_5d 정의)만 저장. 후속 Stage rerun 통합에서 일봉 join 가능.

PIT 강제:
  - 분봉 cumsum 인과적, 일자별 리셋 (lib/signals/vwap.py와 동일 로직)
  - "pullback" = 당일 1σ 밴드 하단 터치 AND 마감 close > VWAP
  - 매수 entry = T+1 시초 (일봉), 보유 1d/5d
  - shift(-N) 절대 금지

출력:
  reports/10pct_strategy/phase5_signals/vwap_signal_daily.parquet
    - columns: stock_code, date, vwap_pb_1_0, vwap_pb_1_5, vwap_pb_2_0
"""

import sys, os, time, traceback
import numpy as np
import pandas as pd
import psycopg2

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports", "10pct_strategy")
P5_DIR     = os.path.join(REPORT_DIR, "phase5_signals")
os.makedirs(P5_DIR, exist_ok=True)

OUT_PATH = os.path.join(P5_DIR, "vwap_signal_daily.parquet")

# minute_candles는 robotrader DB
DB_MIN = dict(host="127.0.0.1", port=5433, dbname="robotrader",
              user="robotrader", password="1234")

# n_sigma 그리드
SIGMAS = [1.0, 1.5, 2.0]


def get_stocks_list():
    conn = psycopg2.connect(**DB_MIN)
    cur  = conn.cursor()
    cur.execute("SELECT DISTINCT stock_code FROM minute_candles ORDER BY stock_code")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def process_stock(stock_code, conn):
    """단일 종목 분봉 → 일자별 pullback 플래그."""
    cur = conn.cursor()
    cur.execute("""
        SELECT trade_date, datetime, close, high, low, volume
        FROM minute_candles
        WHERE stock_code = %s AND volume IS NOT NULL AND close IS NOT NULL
        ORDER BY trade_date, idx
    """, (stock_code,))
    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["trade_date","dt","close","high","low","volume"])
    df["close"]  = pd.to_numeric(df["close"], errors="coerce")
    df["high"]   = pd.to_numeric(df["high"], errors="coerce")
    df["low"]    = pd.to_numeric(df["low"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df.dropna(subset=["close","volume","trade_date"])
    if df.empty:
        return pd.DataFrame()

    # typical price
    tp  = ((df["high"].fillna(df["close"]) + df["low"].fillna(df["close"]) + df["close"]) / 3.0).values
    vol = df["volume"].values
    close_arr = df["close"].values
    dates = df["trade_date"].values

    n = len(df)
    out_rows = []

    i = 0
    while i < n:
        d = dates[i]
        j = i
        while j < n and dates[j] == d:
            j += 1
        tp_day  = tp[i:j]
        vol_day = vol[i:j]
        cls_day = close_arr[i:j]

        cum_pv  = np.cumsum(tp_day * vol_day)
        cum_vol = np.cumsum(vol_day)
        with np.errstate(invalid="ignore", divide="ignore"):
            vwap = np.where(cum_vol > 0, cum_pv / cum_vol, np.nan)

        diff_sq = (tp_day - vwap) ** 2
        cum_var_num = np.cumsum(vol_day * diff_sq)
        with np.errstate(invalid="ignore", divide="ignore"):
            cum_var = np.where(cum_vol > 0, cum_var_num / cum_vol, np.nan)
        std = np.sqrt(cum_var)

        last_close = cls_day[-1]
        last_vwap  = vwap[-1] if not np.isnan(vwap[-1]) else np.nan

        row = {"stock_code": stock_code, "date": d}
        if np.isnan(last_vwap):
            for sig in SIGMAS:
                row[f"vwap_pb_{int(sig*10)}"] = False
        else:
            # 마감 close > VWAP (반등 확인) 조건
            close_above = last_close > last_vwap
            for sig in SIGMAS:
                lower = vwap - sig * std
                # 장중 어느 분봉에서 close < lower 발생했는가
                touched = bool(np.nanmin(cls_day - lower) < 0) if not np.all(np.isnan(lower)) else False
                row[f"vwap_pb_{int(sig*10)}"] = bool(touched and close_above)
        out_rows.append(row)
        i = j

    return pd.DataFrame(out_rows)


def main():
    t0 = time.time()
    print("="*60)
    print("p5_vwap_daily_cache.py")
    print("="*60)

    print("[1] 종목 리스트 ...")
    stocks = get_stocks_list()
    print(f"  종목 수: {len(stocks)}")

    print("[2] 종목별 처리 ...")
    conn = psycopg2.connect(**DB_MIN)
    all_parts = []
    for k, sc in enumerate(stocks, 1):
        try:
            df = process_stock(sc, conn)
            if not df.empty:
                all_parts.append(df)
        except Exception as e:
            print(f"  [WARN] {sc}: {e}")
        if k % 100 == 0:
            elapsed = time.time() - t0
            print(f"  {k}/{len(stocks)} ({elapsed:.0f}s) — rows so far: {sum(len(p) for p in all_parts):,}")
    conn.close()

    if not all_parts:
        print("[ERR] 결과 없음"); sys.exit(1)

    out = pd.concat(all_parts, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"]).reset_index(drop=True)

    n_pb10 = out["vwap_pb_10"].sum()
    print(f"\n[3] 저장 ...")
    print(f"  총 행: {len(out):,}")
    print(f"  vwap_pb_1.0 트리거: {n_pb10:,} ({n_pb10/len(out)*100:.1f}%)")
    print(f"  vwap_pb_1.5 트리거: {out['vwap_pb_15'].sum():,}")
    print(f"  vwap_pb_2.0 트리거: {out['vwap_pb_20'].sum():,}")
    print(f"  기간: {out['date'].min().date()} ~ {out['date'].max().date()}")

    out.to_parquet(OUT_PATH, index=False)
    print(f"  saved: {OUT_PATH}")
    print(f"  total: {(time.time()-t0)/60:.1f}분")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[중단]"); sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL] {e}"); traceback.print_exc(); sys.exit(1)

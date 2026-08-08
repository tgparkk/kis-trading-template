"""P(1) 폭락 타겟 산출 — 전방 60거래일 최저 종가가 −30% 이하인가.

읽기 전용. DB 쓰기 0 · DART 호출 0.

🔴 윈도우는 «전체 이력»에서 계산한 뒤 타겟 창으로 자른다. 먼저 자르면
   창 끝 근처 관측의 전방 60일이 사라진다.
🔴 부분 창(fwd_n < 60)은 폭락률을 과소 측정하므로 «표시»한다. 버리지 않는 이유는
   어느 관측이 왜 빠졌는지가 기록이어야 하기 때문이다.
⚠️ `daily_prices.date` 는 TEXT 다. 문자열로 비교한다.
⚠️ `adj_factor` 를 곱하지 않는다 — close 는 이미 분할조정 연속시세다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/p1_target.py
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import OUT_DIR, db_conn  # noqa: E402

WINDOW = 60
DROP = -0.30
DATE_MIN = "2021-01-04"
DATE_MAX = "2026-05-12"

TARGET_PARQUET = os.path.join(OUT_DIR, "frf_target.parquet")

TARGET_SQL = f"""
WITH px AS (
  SELECT stock_code, date, close,
         MIN(close) OVER (PARTITION BY stock_code ORDER BY date
                          ROWS BETWEEN 1 FOLLOWING AND {WINDOW} FOLLOWING) AS fwd_min,
         count(close) OVER (PARTITION BY stock_code ORDER BY date
                            ROWS BETWEEN 1 FOLLOWING AND {WINDOW} FOLLOWING) AS fwd_n
  FROM daily_prices
  WHERE stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')
    AND close > 0
)
SELECT stock_code, date, close, fwd_min, fwd_n
FROM px
WHERE date >= %s AND date <= %s
"""


def crash_flags(df):
    """ret_min·crash·window_full 을 붙인다. 결측은 NaN/False (0 으로 채우지 않는다)."""
    out = df.copy()
    close = pd.to_numeric(out["close"], errors="coerce")
    fwd = pd.to_numeric(out["fwd_min"], errors="coerce")
    close = close.where(close > 0)
    out["ret_min"] = fwd / close - 1.0
    out["crash"] = out["ret_min"].le(DROP).fillna(False)
    out["window_full"] = pd.to_numeric(out["fwd_n"], errors="coerce").eq(WINDOW)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = db_conn()
    df = pd.read_sql(TARGET_SQL, conn, params=(DATE_MIN, DATE_MAX))
    conn.close()

    df = crash_flags(df)
    df.to_parquet(TARGET_PARQUET, index=False)

    full = df[df["window_full"]]
    yr = full.assign(y=full["date"].str[:4]).groupby("y")["crash"].agg(["size", "mean"])
    print(f"관측 {len(df):,} · 종목 {df['stock_code'].nunique():,} "
          f"· 창 완결 {len(full):,} ({100*len(full)/len(df):.2f}%)")
    print()
    print("연도별 폭락률 (창 완결분만):")
    for y, row in yr.iterrows():
        print(f"  {y}  n={int(row['size']):>9,}  {100*row['mean']:6.2f}%")
    print()
    print("🔑 2021~2025 는 관리자 실측(6.97 / 13.11 / 7.08 / 12.25 / 5.92)과")
    print("   ±0.15%p 안에서 일치해야 한다. 벗어나면 창 정의가 어긋난 것이다.")
    print(f"→ {TARGET_PARQUET}")


if __name__ == "__main__":
    main()

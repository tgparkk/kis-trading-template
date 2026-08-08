"""P(1) 폭락 타겟 산출 — 전방 60거래일 최저 종가가 −30% 이하인가.

읽기 전용. DB 쓰기 0 · DART 호출 0.

🔴 윈도우는 «전체 이력»에서 계산한 뒤 타겟 창으로 자른다. 먼저 자르면
   창 끝 근처 관측의 전방 60일이 사라진다.
🔴 부분 창(fwd_n < 60)은 «다른 처치»를 받은 관측이라 배제 대상이다.
   실측(2026-08-08): 부분 창의 폭락률이 33~67% 로 기저의 3~5배다 —
   부분 창은 종목 이력 끝에 몰려 있고 그 자리는 상장폐지·거래정지
   직전이라 실제로 폭락 중이다. 즉 「짧아서 과소 측정」이 아니라
   「폭락 중인 종목에 선택적으로 몰려 있다」가 맞다.
   버리지 않고 표시하는 이유는 어느 관측이 왜 빠졌는지가 기록이어야 하기 때문이다.
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


def is_crash(ret_min):
    """ret_min 에 문턱을 적용한다. 경계는 포함(<=)이다.

    🔴 이 함수가 따로 있는 이유: −0.30 은 IEEE754 로 정확히 표현되지 않아
       close/fwd_min 나눗셈으로는 «정확히 DROP» 인 입력을 만들 수 없다.
       그래서 나눗셈을 우회해 비교만 직접 검증한다. 이 분리가 없으면
       `.le` → `.lt` 회귀를 어떤 테스트도 잡지 못한다.
    """
    return ret_min.le(DROP).fillna(False)


def crash_flags(df):
    """ret_min·crash·window_full 을 붙인다. 결측은 NaN/False (0 으로 채우지 않는다)."""
    out = df.copy()
    close = pd.to_numeric(out["close"], errors="coerce")
    fwd = pd.to_numeric(out["fwd_min"], errors="coerce")
    # 🔴 다음 줄은 SQL 에서 이미 필터링되었으므로 죽은 코드지만 방어 차원에서 유지
    close = close.where(close > 0)
    out["ret_min"] = fwd / close - 1.0
    out["crash"] = is_crash(out["ret_min"])
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
    partial = df[~df["window_full"]]
    yr_full = full.assign(y=full["date"].str[:4]).groupby("y")["crash"].agg(["size", "mean"])
    yr_partial_stats = partial.assign(y=partial["date"].str[:4]).groupby("y")["crash"].agg(["size", "mean"])

    print(f"관측 {len(df):,} · 종목 {df['stock_code'].nunique():,} "
          f"· 창 완결 {len(full):,} ({100*len(full)/len(df):.2f}%)")
    print()
    print("연도별 폭락률 (창 완결분만):")
    for y, row in yr_full.iterrows():
        print(f"  {y}  n={int(row['size']):>9,}  {100*row['mean']:6.2f}%")
    print()
    print("부분 창 분포 (n · 비율 · 폭락률):")
    for y in sorted(yr_full.index):
        n_full = int(yr_full.loc[y, "size"])
        n_partial = yr_partial_stats.loc[y, "size"] if y in yr_partial_stats.index else 0
        n_total = n_full + int(n_partial)
        pct_partial = 100 * int(n_partial) / n_total if n_total > 0 else 0
        crash_rate_partial = 100 * yr_partial_stats.loc[y, "mean"] if y in yr_partial_stats.index else 0
        print(f"  {y}  n={int(n_partial):>9,}  ({pct_partial:5.2f}%)  {crash_rate_partial:6.2f}%")
    print()
    print("🔑 2021~2025 는 관리자 실측(6.97 / 13.11 / 7.08 / 12.25 / 5.92)과")
    print("   ±0.15%p 안에서 일치해야 한다. 벗어나면 창 정의가 어긋난 것이다.")
    print(f"→ {TARGET_PARQUET}")


if __name__ == "__main__":
    main()

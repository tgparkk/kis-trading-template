"""Look-ahead 층2 실측 — 급등봉 대비 고점 지연과 버킷 어긋남.

측정 대상 (memory: tasso-unjudged-candidates.md "실측(미재현)"):
  (1) 고점이 장대양봉(급등봉) 당일인 비율   -- 원 주장 12.1%
  (2) 고점 지연 중앙값(거래일)             -- 원 주장 7
  (3) 실시간이면 다른 버킷에 들어가는 비율  -- 원 주장 80.6%

정의는 7차 본실행(lab/run7.py + lab/segments.py find_segments_local)을 그대로 복사.
라이브 트리(RoboTrader_template)를 import 하지 않는다 -- trading_YYYYMMDD.log 오염 방지.
  · 급등봉  = 거래대금(close*volume)이 직전 60봉 rolling median의 k배 이상
  · 시작점  = 급등봉 직전봉 종가
  · 고점    = 급등봉부터 horizon 봉 내 최고 고가
  · 연속 급등봉은 첫 봉만 채택 / gain < min_gain 이면 버림
  · 8정의 = k in (5,10) x horizon in (10,20) x min_gain in (.15,.25)  [앵커오차 0]
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import psycopg2

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PG = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234",
          dbname="kis_template")               # 가격 SSOT (resolver 기본값과 동일)
SQL_STOCK_ONLY = "stock_code ~ '^[0-9]{5}[0-9A-Z]$'"   # lib/universe_filter.py 그대로
START, END = "2021-01-04", "2026-07-31"                # run7.py 그대로
K_MULTS, HORIZONS, MIN_GAINS = (5.0, 10.0), (10, 20), (0.15, 0.25)
MED_WINDOW = 60
BUCKETS_7TH = (0.20, 0.50, 1.00, 2.00, 4.00)           # lab/bands.py BUCKETS
DANAL = {"code": "064260", "start": 3930.0, "peak": 5100.0, "tol": 0.02}
DECISION_DAYS = (0, 1, 2, 3, 5)

SQL = f"""
    select stock_code, date, open, high, low, close, volume
    from daily_prices
    where date >= %s and date <= %s and {SQL_STOCK_ONLY}
    order by stock_code, date
"""


def load() -> pd.DataFrame:
    with psycopg2.connect(**PG) as conn:
        df = pd.read_sql(SQL, conn, params=(START, END))
    bad = df[["open", "high", "low", "close"]].isna().any(axis=1)
    for c in ("open", "high", "low", "close"):
        bad = bad | (df[c] <= 0)
    return df.loc[~bad].reset_index(drop=True)


def segments(df: pd.DataFrame, k_mult: float, horizon: int, min_gain: float) -> pd.DataFrame:
    """find_segments_local 과 동일한 선택 규칙 + 결정일별 running gain 기록."""
    rows = []
    for code, g in df.groupby("stock_code", sort=False):
        g = g.reset_index(drop=True)
        if len(g) < MED_WINDOW + 2:
            continue
        val = g["close"] * g["volume"]
        med = val.rolling(MED_WINDOW).median().shift(1)
        is_surge = (val >= k_mult * med) & med.notna() & (med > 0)
        hi = g["high"].to_numpy(dtype=float)
        for s in range(1, len(g)):
            if not bool(is_surge.iat[s]) or bool(is_surge.iat[s - 1]):
                continue
            start_px = float(g["close"].iat[s - 1])
            if start_px <= 0:
                continue
            w = g.iloc[s: s + horizon + 1]
            if w.empty:
                continue
            p = int(w["high"].idxmax())
            peak_px = float(hi[p])
            gain = peak_px / start_px - 1.0
            if gain < min_gain:
                continue
            rec = {"code": str(code), "start_px": start_px, "peak_px": peak_px,
                   "gain": gain, "lag": p - s, "w_len": len(w),
                   "peak_date": str(g["date"].iat[p])}
            for j in DECISION_DAYS:              # 결정일 j 까지만 보고 잰 상승폭
                end = min(s + j, s + len(w) - 1)
                rec[f"gain_{j}"] = float(hi[s:end + 1].max()) / start_px - 1.0
            rows.append(rec)
    return pd.DataFrame(rows)


def bucket_idx(gain: np.ndarray, edges) -> np.ndarray:
    return np.searchsorted(np.asarray(edges, dtype=float), gain, side="right")


def uniform_bucket(gain: np.ndarray, width: float) -> np.ndarray:
    return np.floor(gain / width).astype(int)


def main() -> None:
    bars = load()
    print(f"[data] rows={len(bars):,} codes={bars['stock_code'].nunique():,} "
          f"{bars['date'].min()}~{bars['date'].max()}")

    out = []
    for k in K_MULTS:
        for h in HORIZONS:
            for mg in MIN_GAINS:
                seg = segments(bars, k, h, mg)
                name = f"k{k:g}-h{h}-mg{mg:g}"
                if seg.empty:
                    print(f"[{name}] EMPTY")
                    continue
                # 게이트 C 재확인 -- 다날 정답 라벨이 후보 집합에 있는가
                gate_c = bool((
                    (seg.code == DANAL["code"])
                    & ((seg.start_px - DANAL["start"]).abs() / DANAL["start"] < DANAL["tol"])
                    & ((seg.peak_px - DANAL["peak"]).abs() / DANAL["peak"] < DANAL["tol"])
                ).any())

                lag = seg["lag"].to_numpy()
                gf = seg["gain"].to_numpy()
                row = {"def": name, "n": len(seg), "codes": seg.code.nunique(),
                       "gate_c_danal": gate_c,
                       "pct_lag0": 100.0 * (lag == 0).mean(),
                       "lag_median": float(np.median(lag)),
                       "lag_mean": float(lag.mean()),
                       "lag_p75": float(np.percentile(lag, 75)),
                       "gain_median": float(np.median(gf))}
                for j in DECISION_DAYS:
                    g0 = seg[f"gain_{j}"].to_numpy()
                    row[f"ident_{j}"] = 100.0 * (g0 >= mg).mean()      # 그날 이벤트로 식별되나
                    row[f"mis7_{j}"] = 100.0 * (bucket_idx(g0, BUCKETS_7TH)
                                                != bucket_idx(gf, BUCKETS_7TH)).mean()
                    row[f"mis5_{j}"] = 100.0 * (uniform_bucket(g0, 0.05)
                                                != uniform_bucket(gf, 0.05)).mean()
                    row[f"mis3_{j}"] = 100.0 * (uniform_bucket(g0, 0.03)
                                                != uniform_bucket(gf, 0.03)).mean()
                    row[f"ratio_{j}"] = float(np.median(g0 / gf))
                out.append(row)
                print(f"[{name}] n={len(seg):,} gateC={gate_c} "
                      f"lag0={row['pct_lag0']:.1f}% med_lag={row['lag_median']:.0f} "
                      f"mis7_d0={row['mis7_0']:.1f}% mis5_d0={row['mis5_0']:.1f}%")

    res = pd.DataFrame(out)
    res.to_csv("peak_lag_result.csv", index=False, encoding="utf-8")
    pd.set_option("display.width", 220, "display.max_columns", 60)
    print("\n=== summary (8 definitions) ===")
    print(res[["def", "n", "codes", "gate_c_danal", "pct_lag0", "lag_median",
               "lag_mean", "lag_p75"]].to_string(index=False))
    print("\n=== decision-day d0: identifiability & bucket mismatch ===")
    print(res[["def", "ident_0", "ratio_0", "mis7_0", "mis5_0", "mis3_0"]].to_string(index=False))
    print("\n=== mismatch vs decision day (5%p uniform ladder) ===")
    print(res[["def"] + [f"mis5_{j}" for j in DECISION_DAYS]].to_string(index=False))
    print("\n=== pooled across 8 definitions (unweighted mean) ===")
    for c in ("pct_lag0", "lag_median", "ident_0", "mis7_0", "mis5_0", "mis3_0"):
        print(f"  {c:12s} = {res[c].mean():.2f}   (min {res[c].min():.2f} / max {res[c].max():.2f})")


if __name__ == "__main__":
    main()

"""Weinstein Stage Analysis — BULL/BEAR/SIDEWAYS 국면 분해.

regime_split_minervini.py 패턴 그대로 복사 후 출력 경로만 변경.
20일 수익률 ±2% 임계 (Minervini와 통일. 설계서 §6b).

KS11(코스피) 일봉이 daily_prices에 있으면 우선 사용.
없으면 universe 중앙값 수익률로 대체.

출력: reports/books_research/weinstein_stages/regime_breakdown.parquet
컬럼: date, regime, n_stocks_up, n_stocks_down, median_ret, note
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = logging.getLogger("regime_split_weinstein")
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")

OUT_DIR = ROOT / "reports" / "books_research" / "weinstein_stages"
OUT_PATH = OUT_DIR / "regime_breakdown.parquet"


def _load_universe_close(start: str, end: str, top_n: int = 50) -> pd.DataFrame:
    """daily_prices 거래대금 상위 N종목 종가 wide DataFrame 반환."""
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM daily_prices
            WHERE date >= %s AND date <= %s
              AND stock_code != 'KOSPI'
            GROUP BY stock_code
            ORDER BY turnover DESC
            LIMIT %s
        """, (start, end, top_n))
        codes = [r[0] for r in cur.fetchall()]
        if not codes:
            return pd.DataFrame()

        placeholders = ",".join(["%s"] * len(codes))
        cur.execute(f"""
            SELECT date, stock_code, close * COALESCE(adj_factor, 1.0) AS adj_close
            FROM daily_prices
            WHERE stock_code IN ({placeholders})
              AND date >= %s AND date <= %s
            ORDER BY date ASC
        """, codes + [start, end])
        rows = cur.fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["date", "stock_code", "adj_close"])
    df["date"] = pd.to_datetime(df["date"])
    df["adj_close"] = pd.to_numeric(df["adj_close"], errors="coerce")
    wide = df.pivot_table(index="date", columns="stock_code", values="adj_close")
    return wide.sort_index()


def _try_load_ks11(start: str, end: str) -> "pd.Series | None":
    """daily_prices에서 KOSPI 지수 종가 로드 시도 (Phase 3a 적재분 포함)."""
    from db.connection import DatabaseConnection
    candidates = ["KOSPI", "KS11", "^KS11", "0001"]
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        for code in candidates:
            cur.execute("""
                SELECT date, close FROM daily_prices
                WHERE stock_code = %s AND date >= %s AND date <= %s
                ORDER BY date ASC
            """, (code, start, end))
            rows = cur.fetchall()
            if rows:
                LOG.info(f"KS11 로드 성공: stock_code={code}, rows={len(rows)}")
                s = pd.Series(
                    {pd.Timestamp(r[0]): float(r[1]) for r in rows},
                    name="ks11",
                )
                return s.sort_index()
    return None


def _classify_regime(ret_20d: float) -> str:
    """20일 수익률 기반 국면 분류 (±2% 임계)."""
    if ret_20d > 0.02:
        return "BULL"
    elif ret_20d < -0.02:
        return "BEAR"
    else:
        return "SIDEWAYS"


def build_regime_series(wide_close: pd.DataFrame, ks11: "pd.Series | None") -> pd.DataFrame:
    """날짜별 regime, n_stocks_up, n_stocks_down, median_ret 계산."""
    daily_ret = wide_close.pct_change()
    rows = []
    dates = wide_close.index.tolist()

    for i, dt in enumerate(dates):
        if i < 20:
            continue

        day_rets = daily_ret.loc[dt].dropna()
        n_up = int((day_rets > 0).sum())
        n_down = int((day_rets < 0).sum())
        median_ret = float(day_rets.median()) if len(day_rets) > 0 else 0.0

        if ks11 is not None and dt in ks11.index:
            past_dt = dates[i - 20]
            if past_dt in ks11.index:
                ret_20d = (ks11.loc[dt] - ks11.loc[past_dt]) / ks11.loc[past_dt]
                note = "ks11"
            else:
                sub = wide_close.iloc[i - 20: i + 1]
                ret_20d = float((sub.iloc[-1] / sub.iloc[0] - 1).median())
                note = "universe_median_fallback"
        else:
            sub = wide_close.iloc[i - 20: i + 1]
            ret_20d = float((sub.iloc[-1] / sub.iloc[0] - 1).median())
            note = "universe_median_fallback"

        regime = _classify_regime(ret_20d)
        rows.append({
            "date": dt,
            "regime": regime,
            "ret_20d": round(ret_20d, 6),
            "n_stocks_up": n_up,
            "n_stocks_down": n_down,
            "median_ret": round(median_ret, 6),
            "note": note,
        })

    return pd.DataFrame(rows)


def main() -> None:
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT MIN(date), MAX(date) FROM daily_prices WHERE stock_code != 'KOSPI'")
        mn, mx = cur.fetchone()
    start, end = str(mn), str(mx)
    LOG.info(f"period: {start} ~ {end}")

    ks11 = _try_load_ks11(start, end)
    if ks11 is None:
        LOG.warning("KS11/KOSPI not found in daily_prices — using universe median return as proxy")

    wide_close = _load_universe_close(start, end, top_n=50)
    if wide_close.empty:
        LOG.error("universe close data empty — aborting")
        return
    LOG.info(f"universe: {wide_close.shape[1]} stocks × {wide_close.shape[0]} days")

    regime_df = build_regime_series(wide_close, ks11)
    LOG.info(f"regime rows: {len(regime_df)}")
    LOG.info(regime_df["regime"].value_counts().to_string())

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    regime_df.to_parquet(OUT_PATH, index=False)
    LOG.info(f"saved: {OUT_PATH}")


if __name__ == "__main__":
    main()

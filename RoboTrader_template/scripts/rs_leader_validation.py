"""RS 리더 검증 스파이크 오케스트레이터.

흐름:
  유니버스/일봉 로드(robotrader_quant.daily_prices, 조정종가)
  → 종목별 RSLeaderRule 진입신호 캐시(no-lookahead, _precompute_signals)
  → rs_rank 횡단면 필터(apply_entry_filter)
  → run_portfolio(한정자본 max-K, 비용내장, sl/mh 청산)
  → 국면별 분해(_build_daily_regime_map) + 약세장 에피소드 OOS + PSR
  → reports/regime_spike/rs_leader_validation.md 작성(GO/NO-GO).

사용:
  python scripts/rs_leader_validation.py --start 2021-01-01 --end 2026-05-29 \
    --universe-top 300 --k 10 --rs-threshold 0.7 --rs-n 120 \
    --sl 0.08 --mh 30 --smoke
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import psycopg2

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.rs_leader.rule import RSLeaderRule  # noqa: E402
from scripts.book_portfolio_multiverse import _SLTPMHAdapter, _precompute_signals  # noqa: E402
from scripts.entry_filters import apply_entry_filter  # noqa: E402
from scripts.exit_multiverse.portfolio_sim import run_portfolio  # noqa: E402

DB = dict(host="localhost", port=5433, dbname="robotrader_quant",
          user="robotrader", password="robotrader_secure_pw_2024")


def load_universe_data(start: str, end: str, top_n: int, min_tv: float = 1e9):
    """유동 상위 top_n 종목의 일봉 dict + turnover 반환.

    유니버스 = 기간(start~end) 내 평균 거래대금 상위 N (결정적). df 컬럼: datetime,
    open, high, low, close, volume. 조정종가 그대로(adj_factor 미적용).
    워밍업(MA60/rs_n) 확보를 위해 start 이전 ~400 달력일을 함께 로드한다.
    """
    look_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    conn = psycopg2.connect(**DB)
    try:
        df = pd.read_sql(
            "SELECT stock_code, date, open, high, low, close, volume, trading_value "
            "FROM daily_prices WHERE stock_code NOT IN ('KS11','KQ11') "
            "AND date >= %s AND date <= %s AND close > 0 ORDER BY stock_code, date",
            conn, params=(look_start, end),
        )
    finally:
        conn.close()
    df["date"] = pd.to_datetime(df["date"])
    # 유니버스 선정: 기간(start~end) 평균 거래대금 상위 N
    in_win = df[df["date"] >= pd.Timestamp(start)]
    tv = in_win.groupby("stock_code")["trading_value"].mean()
    tv = tv[tv >= min_tv].sort_values(ascending=False).head(top_n)
    universe = list(tv.index)
    data = {}
    turnover = {}
    for code in universe:
        sub = df[df["stock_code"] == code].copy()
        sub = sub.rename(columns={"date": "datetime"})
        sub = sub.sort_values("datetime").reset_index(drop=True)
        data[code] = sub[["datetime", "open", "high", "low", "close", "volume"]]
        turnover[code] = float(tv[code])
    return data, turnover


def run_backtest(data, turnover, *, rs_threshold, rs_n, k, sl, mh,
                 initial=10_000_000, max_per_stock=3_000_000):
    """RSLeaderRule 신호 → rs_rank 필터 → 한정자본 포트폴리오 체결."""
    rule = RSLeaderRule()
    cache = _precompute_signals(data, rule, warmup_bars=65, granularity="daily")
    filtered = apply_entry_filter(data, cache, filt="rs_rank",
                                  threshold=rs_threshold, n=rs_n)
    # tp 는 추세추종이라 사실상 무효(99.0). 청산 = sl + max_hold (MA20 이탈은 1차 미모델).
    params = dict(stop_loss_pct=sl, take_profit_pct=99.0, max_hold_bars=mh)
    res = run_portfolio(data=data, signal_cache=filtered, adapter=_SLTPMHAdapter(),
                        params=params, turnover=turnover, initial_capital=initial,
                        max_positions=k, max_per_stock=max_per_stock)
    return res


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2021-01-01")
    p.add_argument("--end", default="2026-05-29")
    p.add_argument("--universe-top", type=int, default=300, dest="universe_top")
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--rs-threshold", type=float, default=0.7, dest="rs_threshold")
    p.add_argument("--rs-n", type=int, default=120, dest="rs_n")
    p.add_argument("--sl", type=float, default=0.08)
    p.add_argument("--mh", type=int, default=30)
    p.add_argument("--smoke", action="store_true", help="작은 유니버스로 파이프라인만 확인")
    args = p.parse_args()

    top = 30 if args.smoke else args.universe_top
    print(f"[load] universe top={top} {args.start}~{args.end}")
    data, turnover = load_universe_data(args.start, args.end, top)
    print(f"[load] {len(data)} stocks")
    res = run_backtest(data, turnover, rs_threshold=args.rs_threshold, rs_n=args.rs_n,
                       k=args.k, sl=args.sl, mh=args.mh)
    print(f"[bt] n_trades={res['n_trades']} max_concurrent={res['max_concurrent_positions']}")


if __name__ == "__main__":
    main()

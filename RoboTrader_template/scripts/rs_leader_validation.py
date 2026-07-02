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

from strategies.rs_leader.rule import RSLeaderRule  # noqa: E402
from scripts.rs_leader.exit_adapter import MA20TrailExitAdapter  # noqa: E402
from scripts.book_portfolio_multiverse import (  # noqa: E402
    _SLTPMHAdapter, _precompute_signals, _build_daily_regime_map,
)
from scripts.entry_filters import apply_entry_filter  # noqa: E402
from scripts.exit_multiverse.portfolio_sim import run_portfolio  # noqa: E402
from scripts.rs_leader.decompose import (  # noqa: E402
    decompose_trades_by_regime, episode_stats, probabilistic_sharpe_ratio,
)

DB = dict(host="localhost", port=5433, dbname="robotrader_quant",
          user="robotrader", password="1234")

# 약세장 에피소드(국면별 분해·OOS용) — 성격 다른 3개.
BEAR_EPISODES = [
    ("2022_deep", "2022-01-01", "2022-12-31"),
    ("2024H2_shock", "2024-07-01", "2024-12-31"),
    ("2026-03_vdrop", "2026-02-15", "2026-03-31"),
]
OOS_SPLITS = [
    ("train", "2021-01-01", "2024-06-30"),
    ("test", "2024-07-01", "2026-05-29"),
]


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
    # ★daily_prices.date 는 text형이라 손상값("2026--0-4-" 등)이 존재 → coerce 후 제거.
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    n_bad = int(df["date"].isna().sum())
    if n_bad:
        print(f"[load] 손상 날짜 {n_bad}행 제거 (daily_prices text date 아티팩트)")
        df = df.dropna(subset=["date"])
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
                 exit_mode="sltp", initial=10_000_000, max_per_stock=3_000_000):
    """RSLeaderRule 신호 → rs_rank 필터 → 한정자본 포트폴리오 체결.

    exit_mode: "sltp"(sl+max_hold 근사) 또는 "ma20"(MA20 트레일링 + sl + max_hold).
    """
    rule = RSLeaderRule()
    cache = _precompute_signals(data, rule, warmup_bars=65, granularity="daily")
    filtered = apply_entry_filter(data, cache, filt="rs_rank",
                                  threshold=rs_threshold, n=rs_n)
    # tp 는 추세추종이라 사실상 무효(99.0).
    params = dict(stop_loss_pct=sl, take_profit_pct=99.0, max_hold_bars=mh)
    adapter = MA20TrailExitAdapter() if exit_mode == "ma20" else _SLTPMHAdapter()
    res = run_portfolio(data=data, signal_cache=filtered, adapter=adapter,
                        params=params, turnover=turnover, initial_capital=initial,
                        max_positions=k, max_per_stock=max_per_stock)
    return res


def _sharpe_of_trades(trades):
    """per-trade pnl 의 Sharpe·왜도·첨도(full)·표본수. 표본<2 또는 std=0 이면 0."""
    sells = [t for t in trades if t.get("side") == "sell"]
    s = pd.Series([float(t["pnl_pct"]) for t in sells], dtype=float)
    if s.size < 2 or s.std() == 0:
        return 0.0, 0.0, 3.0, int(s.size)
    return float(s.mean() / s.std()), float(s.skew()), float(s.kurt() + 3.0), int(s.size)


def evaluate(res, regime_map):
    """백테스트 결과를 국면별·에피소드별·OOS별로 분해하고 PSR 산출."""
    trades = res["trades"]
    by_regime = decompose_trades_by_regime(trades, regime_map)
    episodes = {name: episode_stats(trades, lo, hi) for name, lo, hi in BEAR_EPISODES}
    oos = {name: episode_stats(trades, lo, hi) for name, lo, hi in OOS_SPLITS}
    sharpe, skew, kurt, n = _sharpe_of_trades(trades)
    psr = probabilistic_sharpe_ratio(sharpe, n, skew, kurt)
    return {"by_regime": by_regime, "episodes": episodes, "oos": oos,
            "trade_sharpe": sharpe, "psr": psr, "n_trades": n}


def go_verdict(ev):
    """스펙 §6 GO 기준 채점 (C1·C2·C4 자동, C3 수동검토)."""
    by, oos, eps = ev["by_regime"], ev["oos"], ev["episodes"]
    c1 = by.get("sideways", {}).get("mean_pnl", -1) > 0 and \
        all(oos[s].get("mean_pnl", -1) > 0 for s in ("train", "test"))
    c2 = by.get("bear", {}).get("mean_pnl", -1) > -0.05  # 비파국(평균 손실 -5% 이내)
    n_bear_pos = sum(1 for _, s in eps.items() if s["n"] >= 5 and s["mean_pnl"] > 0)
    c4 = n_bear_pos >= 1  # 표본있는 약세장 에피소드 중 ≥1 에서 양수
    passed = c1 and c2 and c4
    return {"GO": passed, "c1_sideways_oos": c1, "c2_bear_not_catastrophic": c2,
            "c3_benchmark": "수동검토", "c4_leave_one_bear": c4}


def write_report(path, args, ev, verdict):
    """국면분해·에피소드·OOS·GO/NO-GO 를 마크다운 리포트로 기록."""
    lines = ["# RS 리더 검증 — GO/NO-GO 리포트", "",
             f"- 기간: {args.start} ~ {args.end} / 유니버스 top {args.universe_top}",
             f"- 파라미터: K={args.k} rs_n={args.rs_n} rs_threshold={args.rs_threshold} "
             f"sl={args.sl} mh={args.mh} exit={args.exit_mode}",
             f"- 총 거래(sell): {ev['n_trades']}  거래Sharpe(per-trade): "
             f"{ev['trade_sharpe']:.3f}  PSR: {ev['psr']:.3f}",
             "", "## 국면별 절대수익 (per-trade pnl)", "",
             "| 국면 | n | 평균 | 중앙 | 승률 |", "|---|---|---|---|---|"]
    for reg in ("bull", "sideways", "bear", "unknown"):
        s = ev["by_regime"].get(reg)
        if s:
            lines.append(f"| {reg} | {s['n']} | {s['mean_pnl']*100:+.2f}% | "
                         f"{s['median_pnl']*100:+.2f}% | {s['win_rate']*100:.1f}% |")
    lines += ["", "## 약세장 에피소드", "", "| 에피소드 | n | 평균 | 승률 |", "|---|---|---|---|"]
    for name, _, _ in BEAR_EPISODES:
        s = ev["episodes"][name]
        lines.append(f"| {name} | {s['n']} | {s['mean_pnl']*100:+.2f}% | {s['win_rate']*100:.1f}% |")
    lines += ["", "## OOS 분할", "", "| 분할 | n | 평균 | 승률 |", "|---|---|---|---|"]
    for name, _, _ in OOS_SPLITS:
        s = ev["oos"][name]
        lines.append(f"| {name} | {s['n']} | {s['mean_pnl']*100:+.2f}% | {s['win_rate']*100:.1f}% |")
    lines += ["", "## GO/NO-GO (스펙 §6)", "",
              f"- C1 SIDEWAYS 절대수익+ & train/test 양수: {verdict['c1_sideways_oos']}",
              f"- C2 BEAR 비파국: {verdict['c2_bear_not_catastrophic']}",
              f"- C3 벤치마크 우위: {verdict['c3_benchmark']} (KOSPI 동구간 수치와 수동 대조)",
              f"- C4 약세장 에피소드 ≥1 양수: {verdict['c4_leave_one_bear']}",
              "", f"## 판정: {'✅ GO' if verdict['GO'] else '❌ NO-GO'}", ""]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")


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
    p.add_argument("--exit-mode", default="sltp", choices=["sltp", "ma20"], dest="exit_mode",
                   help="청산: sltp(sl+max_hold) 또는 ma20(MA20 트레일링+sl+max_hold)")
    p.add_argument("--smoke", action="store_true", help="작은 유니버스로 파이프라인만 확인")
    args = p.parse_args()

    top = 30 if args.smoke else args.universe_top
    print(f"[load] universe top={top} {args.start}~{args.end}")
    data, turnover = load_universe_data(args.start, args.end, top)
    print(f"[load] {len(data)} stocks")
    res = run_backtest(data, turnover, rs_threshold=args.rs_threshold, rs_n=args.rs_n,
                       k=args.k, sl=args.sl, mh=args.mh, exit_mode=args.exit_mode)
    print(f"[bt] exit={args.exit_mode} n_trades={res['n_trades']} "
          f"max_concurrent={res['max_concurrent_positions']}")

    if not args.smoke:
        print("[regime] building daily regime map (real KOSPI)...")
        regime_map = _build_daily_regime_map(args.start, args.end)
        ev = evaluate(res, regime_map)
        verdict = go_verdict(ev)
        suffix = "" if args.exit_mode == "sltp" else f"_{args.exit_mode}"
        out = ROOT / "reports" / "regime_spike" / f"rs_leader_validation{suffix}.md"
        write_report(out, args, ev, verdict)
        print(f"[report] {out}  ->  {'GO' if verdict['GO'] else 'NO-GO'}")


if __name__ == "__main__":
    main()

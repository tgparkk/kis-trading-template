"""dev20 사이징 시나리오 측정 — "검증된 엣지를 얼마나 세게 밟을 수 있는가".

배경(사장님 질의 "주 3%"): deep_mr_dev20(거래당 순 +1.4%, 월 6회, 품질 전관문 통과)의
계좌 수익률은 포지션 사이징의 함수다. 사이징을 키울 때 월/주 수익 분포와
드로다운·파산 확률이 어떻게 변하는지 측정해 정량 답변을 만든다.

시나리오 (K=동시보유 슬롯, mps=종목당 매수금액; 자본 1천만 고정):
  S1 K5×100만(현행 라이브) / S2 K5×200만(자본/K) / S3 K3×333만 /
  S4 K2×500만(50% 집중) / S5 K1×1000만(풀 집중)

산출(시나리오별):
  풀기간 PnL·CAGR·Sharpe·MaxDD / 월수익 분포(p05·중앙값·p95, P(월≥+3%), P(월≤-5%)) /
  주수익 P(주≥+3%) / 부트스트랩(블록21d×1000, seed42) MaxDD p50·p95,
  P(MaxDD≥30%)·P(MaxDD≥50%) [파산 근사].

주의: run_portfolio 는 고정 원화 사이징(무복리) — 계좌가 커져도 포지션이 안 커지므로
장기 수익률은 보수적 추정. 단기(월/주) 분포와 DD 위험엔 영향 작음.

usage: python scripts/discovery/sizing_scenarios.py --out reports/discovery
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from scripts.multiverse4_portfolio_analysis import maxdd_from_returns, sharpe  # noqa: E402

SCENARIOS = [
    ("S1_현행_K5x100만", 5, 1_000_000.0),
    ("S2_자본K_K5x200만", 5, 2_000_000.0),
    ("S3_K3x333만", 3, 3_333_333.0),
    ("S4_집중_K2x500만", 2, 5_000_000.0),
    ("S5_풀집중_K1x1000만", 1, 10_000_000.0),
]


def bootstrap_dd_probs(rets: pd.Series, n_iter: int = 1000, block: int = 21,
                       seed: int = 42, dd_levels=(0.30, 0.50)) -> dict:
    """이동블록 부트스트랩 — MaxDD 분포(p50/p95)와 P(MaxDD>=level).

    block_bootstrap_metrics 와 동일 재표집 방식. seed 고정 = 재현성.
    """
    x = rets.dropna().to_numpy(dtype=float)
    n = len(x)
    keys = ["maxdd_p50", "maxdd_p95"] + [f"p_dd_ge_{int(level * 100)}" for level in dd_levels]
    if n < block * 3:
        return {k: float("nan") for k in keys}
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts_max = n - block
    dds = np.empty(n_iter)
    for it in range(n_iter):
        starts = rng.integers(0, starts_max + 1, size=n_blocks)
        sample = np.concatenate([x[s:s + block] for s in starts])[:n]
        eq = np.cumprod(1.0 + sample)
        peak = np.maximum.accumulate(eq)
        dds[it] = float(-((eq - peak) / peak).min())
    out = dict(maxdd_p50=float(np.percentile(dds, 50)),
               maxdd_p95=float(np.percentile(dds, 95)))
    for level in dd_levels:
        out[f"p_dd_ge_{int(level * 100)}"] = float((dds >= level).mean())
    return out


def periodic_stats(dr: pd.Series) -> dict:
    """월/주 복리 수익 분포."""
    eq = (1.0 + dr.fillna(0.0)).cumprod()
    monthly = eq.resample("ME").last().pct_change().dropna()
    weekly = eq.resample("W").last().pct_change().dropna()
    return dict(
        mon_med=float(monthly.median()), mon_p05=float(monthly.quantile(0.05)),
        mon_p95=float(monthly.quantile(0.95)),
        p_mon_ge3=float((monthly >= 0.03).mean()),
        p_mon_le_m5=float((monthly <= -0.05).mean()),
        p_week_ge3=float((weekly >= 0.03).mean()),
    )


def run_scenarios(data, turnover, cache, spec, initial: float = 10_000_000.0,
                  n_iter: int = 1000) -> pd.DataFrame:
    from scripts.exit_multiverse.portfolio_sim import run_portfolio
    rows = []
    for name, k, mps in SCENARIOS:
        res = run_portfolio(data=data, signal_cache=cache, adapter=spec.adapter,
                            params=spec.params, turnover=turnover,
                            initial_capital=initial, max_positions=k, max_per_stock=mps)
        dr: pd.Series = res["daily_returns"]
        dr.index = pd.to_datetime(dr.index)
        dr = dr.sort_index()
        eq = (1.0 + dr).cumprod()
        years = max(0.1, (dr.index.max() - dr.index.min()).days / 365.25)
        sells = [t for t in res["trades"] if t["side"] == "sell"]
        row = dict(scenario=name, K=k, per_stock=int(mps),
                   pnl=float(eq.iloc[-1] - 1.0),
                   cagr=float(eq.iloc[-1] ** (1.0 / years) - 1.0),
                   sharpe=sharpe(dr.to_numpy()),
                   maxdd=maxdd_from_returns(dr),
                   n_trades=len(sells),
                   worst_trade_acct=float(min((t["pnl_pct"] for t in sells), default=0.0)
                                          * mps / initial))
        row.update(periodic_stats(dr))
        row.update(bootstrap_dd_probs(dr, n_iter=n_iter))
        rows.append(row)
        print(f"[done] {name}: pnl={row['pnl']:+.1%} cagr={row['cagr']:+.1%} "
              f"sharpe={row['sharpe']:.2f} maxdd={row['maxdd']:.1%} "
              f"mon_med={row['mon_med']:+.2%} P(월≥3%)={row['p_mon_ge3']:.0%} "
              f"P(DD≥30%)={row['p_dd_ge_30']:.0%}")
    return pd.DataFrame(rows)


def main(argv: Optional[List[str]] = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reports" / "discovery"))
    ap.add_argument("--top-n", type=int, default=300)
    ap.add_argument("--bootstrap-iters", type=int, default=1000)
    args = ap.parse_args(argv)

    from scripts.book_param_multiverse import (
        _daily_minmax_dates, _load_daily_adj, _load_top_volume_daily,
    )
    from scripts.strategy_gate import CANDIDATES

    spec = CANDIDATES["deep_mr_dev20"]
    mn, mx = _daily_minmax_dates()
    uni = _load_top_volume_daily(mn, mx, args.top_n)
    data = _load_daily_adj(uni, mn, mx)
    turnover = {c: float((df["close"] * df["volume"]).sum()) for c, df in data.items()}
    print(f"[load] top_n={args.top_n} loaded={len(data)}")
    cache = spec.build_signals(data)

    df = run_scenarios(data, turnover, cache, spec, n_iter=args.bootstrap_iters)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(out / "dev20_sizing_scenarios.tsv", sep="\t", index=False)
    print(f"\n[out] {out / 'dev20_sizing_scenarios.tsv'}")
    print(df.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

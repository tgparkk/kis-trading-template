"""fade_vwap + anti 페어 운용 시뮬레이션.

각 전략의 거래 parquet에서 sell pnl_pct를 일별 누적 → 두 전략 일별 PnL 시계열 비교.
50/50 자본 분배 가정으로 통합 포트폴리오 시뮬.
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

LOG = logging.getLogger("simulate_pair")

PERIODS = ["2025-10", "2026-04", "2026-05"]

FADE_DIR = Path("reports/books_research/bellafiore_playbook")
ANTI_DIR = Path("reports/books_research/raschke_street_smarts")


def _load_strategy(parquet_dir: Path, prefix: str, periods: list) -> pd.DataFrame:
    """전략별 거래기록 통합 로드 (sell만)."""
    all_dfs = []
    for p in periods:
        f = parquet_dir / f"results_single_{prefix}_{p}_top_volume50_sl030_tp050_mh120.parquet"
        if not f.exists():
            LOG.warning(f"missing {f}")
            continue
        df = pd.read_parquet(f)
        df["period"] = p
        all_dfs.append(df)
    if not all_dfs:
        return pd.DataFrame()
    df = pd.concat(all_dfs, ignore_index=True)
    df = df[df["side"] == "sell"].copy()
    df["sell_dt"] = pd.to_datetime(df["datetime"])
    df["sell_date"] = df["sell_dt"].dt.normalize()
    return df


def _daily_pnl(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """일별 평균 PnL (자본 균등 분배 가정)."""
    if df.empty:
        return pd.DataFrame(columns=["date", f"{name}_pnl", f"{name}_n_trades"])
    agg = df.groupby("sell_date").agg(
        pnl_mean=("pnl_pct", "mean"),
        n_trades=("pnl_pct", "size"),
    ).reset_index()
    agg.columns = ["date", f"{name}_pnl", f"{name}_n_trades"]
    return agg


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    LOG.info("loading fade_vwap trades")
    fade = _load_strategy(FADE_DIR, "fade_vwap", PERIODS)
    LOG.info(f"fade_vwap sell trades: {len(fade)}")

    LOG.info("loading anti trades")
    anti = _load_strategy(ANTI_DIR, "anti", PERIODS)
    LOG.info(f"anti sell trades: {len(anti)}")

    fade_daily = _daily_pnl(fade, "fade")
    anti_daily = _daily_pnl(anti, "anti")
    pair = pd.merge(fade_daily, anti_daily, on="date", how="outer").fillna(0)
    pair["both_traded"] = (pair["fade_n_trades"] > 0) & (pair["anti_n_trades"] > 0)
    # 50/50 자본 분배: 일별 PnL = (fade_pnl + anti_pnl) / 2 — 일별 평균 거래 수익 가중
    pair["pair_pnl"] = (pair["fade_pnl"] + pair["anti_pnl"]) / 2
    # 둘 중 하나라도 거래한 일자만 운영 가정
    pair = pair[(pair["fade_n_trades"] > 0) | (pair["anti_n_trades"] > 0)].copy()

    print("=== 일별 PnL 시계열 (요약) ===")
    print(f"총 일자: {len(pair)}")
    print(f"fade_vwap 단독 거래일: {((pair['fade_n_trades'] > 0) & (pair['anti_n_trades'] == 0)).sum()}")
    print(f"anti 단독 거래일: {((pair['fade_n_trades'] == 0) & (pair['anti_n_trades'] > 0)).sum()}")
    print(f"둘 다 거래일: {pair['both_traded'].sum()}")
    print()

    # 상관관계 (둘 다 거래한 날만)
    both = pair[pair["both_traded"]]
    if len(both) >= 2:
        corr = both["fade_pnl"].corr(both["anti_pnl"])
        print(f"fade_pnl vs anti_pnl 상관계수 (둘 다 거래한 {len(both)}일): {corr:.4f}")
    print()

    # 전략별 + 페어 메트릭
    def metrics(name, series):
        s = series.dropna()
        if len(s) < 2:
            return {"strategy": name, "n_days": len(s), "mean": 0, "std": 0, "sharpe": 0,
                    "max_dd": 0, "cum_pnl": 0, "hit_rate": 0}
        mean = s.mean()
        std = s.std()
        sharpe = mean / std * np.sqrt(252) if std > 0 else 0
        cum = s.cumsum()
        peak = cum.cummax()
        dd = (cum - peak)
        max_dd = dd.min()
        return {
            "strategy": name, "n_days": len(s),
            "mean": mean, "std": std, "sharpe": sharpe,
            "max_dd": max_dd, "cum_pnl": s.sum(),
            "hit_rate": (s > 0).mean(),
        }

    summary = pd.DataFrame([
        metrics("fade_vwap", pair[pair["fade_n_trades"] > 0]["fade_pnl"]),
        metrics("anti", pair[pair["anti_n_trades"] > 0]["anti_pnl"]),
        metrics("pair 50/50", pair["pair_pnl"]),
    ])
    print("=== 전략별 vs 페어 일별 PnL 메트릭 ===")
    print(summary.to_string(index=False))
    print()

    # 기간별 페어 메트릭
    def period_lookup(date):
        d = pd.Timestamp(date)
        if d < pd.Timestamp("2025-11-01"):
            return "2025-10"
        if d < pd.Timestamp("2026-05-01"):
            return "2026-04"
        return "2026-05"

    pair["period"] = pair["date"].apply(period_lookup)
    by_period = []
    for p in PERIODS:
        sub = pair[pair["period"] == p]
        by_period.append(metrics(f"pair {p}", sub["pair_pnl"]))
    by_period_df = pd.DataFrame(by_period)
    print("=== 기간별 페어 메트릭 ===")
    print(by_period_df.to_string(index=False))

    # 저장
    out_dir = Path("reports/books_research")
    pair.to_parquet(out_dir / "pair_fade_anti_daily.parquet", index=False)
    summary.to_parquet(out_dir / "pair_fade_anti_summary.parquet", index=False)
    by_period_df.to_parquet(out_dir / "pair_fade_anti_by_period.parquet", index=False)
    LOG.info(f"saved 3 parquets to {out_dir}/")


if __name__ == "__main__":
    main()

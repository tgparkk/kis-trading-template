"""MULTIVERSE4 분석 — 7전략 daily_returns 에서 미수행 3축 파생 (재백테스트 없음).

입력: multiverse4_returns_export.py 산출 디렉토리(<strategy>.csv + KOSPI.csv).
축1 합성  : 전략간 상관행렬(피어슨) + 꼬리 동시손실 lift + 합성 포트폴리오 4종
            (live_sum=독립 1천만 합산[라이브 모델 그대로] / eqw_rebal=일일 등가중 /
             inv_vol=역변동성[풀기간 σ, in-sample 주의] / elder_heavy=Elder40%+나머지10%).
축2 워크포워드: 반기(H1/H2) 윈도우 분해 — 전략×윈도우 Sharpe/PnL 매트릭스 + KOSPI 알파.
축5 부트스트랩: 이동블록 부트스트랩(블록21일, 1000회, seed42) Sharpe/MaxDD 90% CI.

출력: <out>/corr_matrix.tsv, tail_coloss.tsv, combos.tsv, walkforward_pnl.tsv,
      walkforward_sharpe.tsv, bootstrap.tsv + 콘솔 보고.

usage:
  python scripts/multiverse4_portfolio_analysis.py \
      --returns-dir reports/books_research/_mv4_returns --out reports/books_research/_mv4_analysis
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

INITIAL = 10_000_000.0


# ---------------------------------------------------------------------------
# 순수 헬퍼 (테스트 대상)
# ---------------------------------------------------------------------------

def sharpe(rets: np.ndarray) -> float:
    rets = np.asarray(rets, dtype=float)
    rets = rets[np.isfinite(rets)]
    if len(rets) <= 1 or rets.std() == 0:
        return 0.0
    return float(rets.mean() / rets.std() * math.sqrt(252))


def maxdd_from_returns(rets: pd.Series) -> float:
    eq = (1.0 + rets.fillna(0.0)).cumprod()
    peak = eq.cummax()
    dd = (eq - peak) / peak
    return float(-dd.min()) if len(dd) else 0.0


def _aligned_frame(returns: Dict[str, pd.Series]) -> pd.DataFrame:
    """전략별 시리즈를 union 날짜축 wide 프레임으로. 비거래일(상장 전 등)은 NaN 유지."""
    return pd.DataFrame(returns).sort_index()


def corr_matrix(returns: Dict[str, pd.Series]) -> pd.DataFrame:
    """피어슨 상관 (pairwise 겹치는 날짜만, min_periods=60)."""
    return _aligned_frame(returns).corr(min_periods=60)


def tail_coloss_lift(a: pd.Series, b: pd.Series, q: float = 0.10) -> float:
    """꼬리 동시손실 lift = P(b가 자기 하위 q | a가 자기 하위 q) / q.

    1.0=독립, q^-1=완전동행. 겹치는 날짜에서 각자 자신의 q-분위 임계로 판정.
    """
    df = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(df) < 60:
        return float("nan")
    ta = df["a"].quantile(q)
    tb = df["b"].quantile(q)
    in_a = df["a"] <= ta
    if in_a.sum() == 0:
        return float("nan")
    p_cond = float((df.loc[in_a, "b"] <= tb).mean())
    return p_cond / q


def combine_sum_of_equities(returns: Dict[str, pd.Series],
                            initial_per_strategy: float = INITIAL) -> pd.Series:
    """라이브 모델 그대로: 전략별 독립 계좌(각 initial) equity 합산의 일일수익률.

    각 전략은 자기 거래일에만 수익률 발생(타 전략 날짜엔 0 = 현금 보유).
    리밸런스 없음 — 잘 나가는 전략 비중이 자연 증가(라이브와 동일).
    """
    wide = _aligned_frame(returns).fillna(0.0)
    eqs = initial_per_strategy * (1.0 + wide).cumprod()
    total = eqs.sum(axis=1)
    total0 = initial_per_strategy * len(returns)
    prev = total.shift(1).fillna(total0)
    return total / prev - 1.0


def combine_equal_weight_rebal(returns: Dict[str, pd.Series]) -> pd.Series:
    """일일 등가중 리밸런스 합성 = 단순평균."""
    return _aligned_frame(returns).fillna(0.0).mean(axis=1)


def combine_weighted_rebal(returns: Dict[str, pd.Series],
                           weights: Dict[str, float]) -> pd.Series:
    wide = _aligned_frame(returns).fillna(0.0)
    w = pd.Series(weights).reindex(wide.columns).fillna(0.0)
    w = w / w.sum()
    return (wide * w).sum(axis=1)


def inv_vol_weights(returns: Dict[str, pd.Series]) -> Dict[str, float]:
    """풀기간 역변동성 가중 (in-sample — 참고용, 보고서에 명시)."""
    out = {}
    for k, s in returns.items():
        sd = float(s.dropna().std())
        out[k] = 1.0 / sd if sd > 0 else 0.0
    tot = sum(out.values())
    return {k: v / tot for k, v in out.items()} if tot > 0 else out


def semiannual_windows(start: pd.Timestamp, end: pd.Timestamp):
    wins = []
    y = start.year
    while y <= end.year:
        for half, (m0, d0, m1, d1) in (("H1", (1, 1, 6, 30)), ("H2", (7, 1, 12, 31))):
            w0 = pd.Timestamp(year=y, month=m0, day=d0)
            w1 = pd.Timestamp(year=y, month=m1, day=d1)
            if w1 < start or w0 > end:
                continue
            wins.append((f"{y}{half}", max(w0, start), min(w1, end)))
        y += 1
    return wins


def block_bootstrap_metrics(rets: pd.Series, n_iter: int = 1000, block: int = 21,
                            seed: int = 42) -> dict:
    """이동블록 부트스트랩 — Sharpe/MaxDD 의 p05/p50/p95.

    원시 일수익률에서 길이 block 의 연속 블록을 복원추출해 원길이 시계열을 재구성.
    자기상관(변동성 군집)을 블록 단위로 보존. seed 고정 = 재현성.
    """
    x = rets.dropna().to_numpy(dtype=float)
    n = len(x)
    if n < block * 3:
        return {k: float("nan") for k in
                ("sharpe_p05", "sharpe_p50", "sharpe_p95",
                 "maxdd_p05", "maxdd_p50", "maxdd_p95")}
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts_max = n - block
    sharpes = np.empty(n_iter)
    maxdds = np.empty(n_iter)
    for it in range(n_iter):
        starts = rng.integers(0, starts_max + 1, size=n_blocks)
        sample = np.concatenate([x[s:s + block] for s in starts])[:n]
        sharpes[it] = sharpe(sample)
        eq = np.cumprod(1.0 + sample)
        peak = np.maximum.accumulate(eq)
        maxdds[it] = float(-((eq - peak) / peak).min())
    return dict(
        sharpe_p05=float(np.percentile(sharpes, 5)),
        sharpe_p50=float(np.percentile(sharpes, 50)),
        sharpe_p95=float(np.percentile(sharpes, 95)),
        maxdd_p05=float(np.percentile(maxdds, 5)),
        maxdd_p50=float(np.percentile(maxdds, 50)),
        maxdd_p95=float(np.percentile(maxdds, 95)),
    )


# ---------------------------------------------------------------------------
# 로드/리포트
# ---------------------------------------------------------------------------

def load_returns(returns_dir: Path) -> Dict[str, pd.Series]:
    out = {}
    for f in sorted(returns_dir.glob("*.csv")):
        if f.stem.endswith("_trades") or f.stem == "KOSPI":
            continue
        df = pd.read_csv(f, parse_dates=["date"])
        out[f.stem] = pd.Series(df["daily_return"].to_numpy(),
                                index=df["date"]).sort_index()
    return out


def load_kospi(returns_dir: Path) -> Optional[pd.Series]:
    f = returns_dir / "KOSPI.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f, parse_dates=["date"])
    return pd.Series(df["daily_return"].to_numpy(), index=df["date"]).sort_index()


def _metrics_row(name: str, s: pd.Series) -> dict:
    eq = (1.0 + s.fillna(0.0)).cumprod()
    return dict(name=name, sharpe=round(sharpe(s.to_numpy()), 3),
                pnl=round(float(eq.iloc[-1] - 1.0), 4),
                maxdd=round(maxdd_from_returns(s), 4),
                n_days=int(s.notna().sum()),
                start=str(s.index.min().date()), end=str(s.index.max().date()))


def main(argv: Optional[List[str]] = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--returns-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bootstrap-iters", type=int, default=1000)
    args = ap.parse_args(argv)

    rdir = Path(args.returns_dir)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    returns = load_returns(rdir)
    kospi = load_kospi(rdir)
    names = list(returns.keys())
    print(f"[load] strategies={names}")

    # ---- 축1: 상관 + 꼬리 동시손실 ----
    cm = corr_matrix(returns)
    cm.to_csv(out / "corr_matrix.tsv", sep="\t")
    print("\n=== 상관행렬 (피어슨, pairwise) ===")
    print(cm.round(2).to_string())

    tail_rows = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            tail_rows.append(dict(a=a, b=b,
                                  lift=round(tail_coloss_lift(returns[a], returns[b]), 2)))
    tail_df = pd.DataFrame(tail_rows).sort_values("lift", ascending=False)
    tail_df.to_csv(out / "tail_coloss.tsv", sep="\t", index=False)
    print("\n=== 꼬리 동시손실 lift (하위10%일 동행, 1=독립, 10=완전동행) ===")
    print(tail_df.to_string(index=False))

    # ---- 축1: 합성 포트폴리오 ----
    ivw = inv_vol_weights(returns)
    elder_w = {n: (0.4 if n == "elder_ema_pullback" else 0.6 / max(1, len(names) - 1))
               for n in names}
    combos = {
        "live_sum(독립1천만·무리밸)": combine_sum_of_equities(returns),
        "eqw_rebal(등가중)": combine_equal_weight_rebal(returns),
        "inv_vol(역변동성·IS)": combine_weighted_rebal(returns, ivw),
        "elder40(Elder40%+나머지균등)": combine_weighted_rebal(returns, elder_w),
    }
    combo_rows = [_metrics_row(k, v) for k, v in combos.items()]
    for n in names:
        combo_rows.append(_metrics_row(f"단독:{n}", returns[n]))
    if kospi is not None:
        combo_rows.append(_metrics_row("KOSPI", kospi))
    combo_df = pd.DataFrame(combo_rows)
    combo_df.to_csv(out / "combos.tsv", sep="\t", index=False)
    print("\n=== 합성 포트폴리오 vs 단독 ===")
    print(combo_df.to_string(index=False))
    pd.Series(ivw).round(4).to_csv(out / "inv_vol_weights.tsv", sep="\t")

    # ---- 축2: 워크포워드 반기 매트릭스 ----
    all_start = min(s.index.min() for s in returns.values())
    all_end = max(s.index.max() for s in returns.values())
    wins = semiannual_windows(all_start, all_end)
    streams = dict(returns)
    streams["combo_live_sum"] = combos["live_sum(독립1천만·무리밸)"]
    pnl_mat = pd.DataFrame(index=[w[0] for w in wins], columns=list(streams) + ["KOSPI"],
                           dtype=float)
    sh_mat = pd.DataFrame(index=[w[0] for w in wins], columns=list(streams), dtype=float)
    for wname, w0, w1 in wins:
        for sname, s in streams.items():
            rw = s[(s.index >= w0) & (s.index <= w1)].dropna()
            if len(rw) < 20:
                continue
            pnl_mat.loc[wname, sname] = float((1.0 + rw).prod() - 1.0)
            sh_mat.loc[wname, sname] = sharpe(rw.to_numpy())
        if kospi is not None:
            kw = kospi[(kospi.index >= w0) & (kospi.index <= w1)].dropna()
            if len(kw) >= 20:
                pnl_mat.loc[wname, "KOSPI"] = float((1.0 + kw).prod() - 1.0)
    pnl_mat.to_csv(out / "walkforward_pnl.tsv", sep="\t")
    sh_mat.to_csv(out / "walkforward_sharpe.tsv", sep="\t")
    print("\n=== 워크포워드 반기 PnL ===")
    print((pnl_mat * 100).round(1).to_string())
    print("\n=== 워크포워드 반기 Sharpe ===")
    print(sh_mat.round(2).to_string())
    pos = (pnl_mat.drop(columns=["KOSPI"], errors="ignore") > 0).sum()
    tot = pnl_mat.drop(columns=["KOSPI"], errors="ignore").notna().sum()
    print("\n[양수 PnL 윈도우] " + "  ".join(f"{k}={int(pos[k])}/{int(tot[k])}" for k in pos.index))

    # ---- 축5: 부트스트랩 CI ----
    boot_rows = []
    for sname, s in streams.items():
        m = block_bootstrap_metrics(s.fillna(0.0), n_iter=args.bootstrap_iters)
        boot_rows.append(dict(name=sname, **{k: round(v, 3) for k, v in m.items()}))
    boot_df = pd.DataFrame(boot_rows)
    boot_df.to_csv(out / "bootstrap.tsv", sep="\t", index=False)
    print("\n=== 블록 부트스트랩 (block=21d, 90% CI) ===")
    print(boot_df.to_string(index=False))

    print(f"\n[out] {out}")


if __name__ == "__main__":
    main()

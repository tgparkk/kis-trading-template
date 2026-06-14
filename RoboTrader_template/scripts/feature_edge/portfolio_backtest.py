"""amihud(비유동성) 엣지의 cost-aware 분위 포트폴리오 백테스트 (측정 전용 Phase 0+).

피처 엣지 랩에서 amihud 만 게이트 통과 양의 횡단면 IC(fwd20 +0.045/IR0.51)였다.
IC(예측력)는 쟀으나 "현실 거래비용을 넣으면 살아남나"는 미검증 — 특히 amihud 상위
= 가장 비유동적 종목이라 슬리피지가 본질이다. 이 모듈이 그걸 정직하게 측정한다.

설계(사장님 결정):
 - 롱온리 상위분위(한국 개인은 공매도 제약 → 거래가능한 유일 형태)
 - 유동성 차등 비용: 보유 종목의 within-day amihud 백분위(=비유동 티어)에 비례해
   슬리피지를 키운다. 상위 amihud 바스켓은 정의상 꼬리에 몰려 near-max 비용을 낸다.

진입/청산 관행은 labelers 와 동일(T+1 시가 진입, close 청산) → IC가 측정한 것과 일치.
비용 근사: net = gross − roundtrip_cost (소액 가법근사).
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd


# ── 순수 분석 함수 ──────────────────────────────────────────────────────────
def top_quantile_codes(day: pd.DataFrame, feat: str, top_pct: float) -> List[str]:
    """하루 횡단면에서 feat 상위 top_pct 분위 종목코드(최고값=롱)."""
    sub = day[["stock_code", feat]].dropna(subset=[feat])
    n = len(sub)
    if n == 0:
        return []
    k = max(1, int(math.ceil(n * top_pct)))
    top = sub.nlargest(k, feat)
    return top["stock_code"].tolist()


def illiquidity_pct(day: pd.DataFrame, feat: str = "amihud") -> pd.Series:
    """within-day amihud 백분위(0=최유동, 1=최비유동), stock_code 색인."""
    s = day.set_index("stock_code")[feat]
    return s.rank(pct=True)


def tiered_cost(illiq_pct, fee_tax: float, slip_low: float, slip_high: float):
    """유동성 차등 왕복비용 = fee_tax + slip_low + (slip_high−slip_low)·illiq_pct.

    illiq_pct=0(최유동) → fee_tax+slip_low, =1(최비유동) → fee_tax+slip_high.
    스칼라/시리즈 모두 허용.
    """
    return fee_tax + slip_low + (slip_high - slip_low) * illiq_pct


def build_periods(merged: pd.DataFrame, feat: str, label: str, top_pct: float,
                  horizon: int, fee_tax: float, slip_low: float, slip_high: float,
                  illiq_feat: str = "amihud") -> pd.DataFrame:
    """비중첩 리밸런스별 상위분위 롱 포트폴리오의 gross/cost/net.

    merged: date, stock_code, feat, illiq_feat, label(fwd_{h}d) 보유 long DataFrame.
    리밸런스 날짜 = 정렬된 고유일자를 horizon 간격으로 비중첩 추출(중복계상 방지).
    각 리밸: 상위분위 동일가중 롱, gross=평균 label, cost=보유종목 차등비용 평균.
    """
    df = merged.copy()
    df["date"] = pd.to_datetime(df["date"])
    all_dates = np.sort(df["date"].unique())
    rebal_dates = all_dates[::max(1, horizon)]

    rows = []
    for d in rebal_dates:
        day = df[df["date"] == d]
        codes = top_quantile_codes(day, feat, top_pct)
        held = day[day["stock_code"].isin(codes)].dropna(subset=[label])
        if len(held) == 0:
            continue
        illiq = illiquidity_pct(day, illiq_feat)  # 전체 횡단면 기준 백분위
        held_illiq = illiq.reindex(held["stock_code"]).fillna(0.5).values
        costs = tiered_cost(held_illiq, fee_tax, slip_low, slip_high)
        gross = float(held[label].mean())
        cost = float(np.mean(costs))
        rows.append({"date": pd.Timestamp(d), "n_held": int(len(held)),
                     "gross": gross, "cost": cost, "net": gross - cost})
    return pd.DataFrame(rows)


def period_stats(net: pd.Series, periods_per_year: float) -> Dict[str, float]:
    """리밸런스별 net 수익률 시계열 → 평균·Sharpe·연율화·누적CAGR."""
    net = pd.Series(net).astype(float).dropna()
    n = len(net)
    if n == 0:
        return {"mean_net": float("nan"), "sharpe": float("nan"),
                "ann_return": float("nan"), "cagr": float("nan"), "n_periods": 0}
    sd = net.std(ddof=1)
    sharpe = net.mean() / sd * math.sqrt(periods_per_year) if sd and sd > 0 else float("nan")
    growth = float(np.prod(1.0 + net.values))
    years = n / periods_per_year
    cagr = growth ** (1.0 / years) - 1.0 if years > 0 and growth > 0 else float("nan")
    return {"mean_net": float(net.mean()), "sharpe": float(sharpe),
            "ann_return": float(net.mean() * periods_per_year),
            "cagr": float(cagr), "n_periods": int(n)}


# ── 통합 수집·리포트 (DB 경로, 단위테스트 제외) ─────────────────────────────
# 한국 왕복비용 구성요소: 수수료(매수+매도) ~0.03%×2 + 증권거래세(매도) ~0.18% ≈ fee_tax 0.20%.
# 슬리피지는 유동성 차등 — 시나리오로 스윕.
COST_SCENARIOS = {
    # name: (fee_tax, slip_low, slip_high)
    "optimistic":  (0.0020, 0.0005, 0.0030),
    "base":        (0.0020, 0.0010, 0.0060),
    "pessimistic": (0.0020, 0.0015, 0.0120),
}
HORIZONS = (5, 10, 20)
TOP_PCTS = (0.10, 0.20)
TRADING_DAYS_YR = 252
OOS_SPLIT = "2024-06-30"


def collect_merged_panel(limit: int = 0) -> pd.DataFrame:  # pragma: no cover (통합 DB 경로)
    """패널(amihud) + 선행수익률 라벨 병합. run_edge_lab 와 동일 소스."""
    from scripts.feature_edge import config, loaders
    from scripts.feature_edge.labelers import label_forward_returns

    codes = loaders.load_universe(config.PERIOD_END)
    if limit:
        codes = codes[:limit]
    daily = loaders.load_daily_supplier(codes, config.PERIOD_END)

    feat_parts, lab_parts = [], []
    for c, df in daily.items():
        if df is None or len(df) <= max(HORIZONS) + 2:
            continue
        from scripts.feature_edge.price_features import compute_price_features
        f = compute_price_features(df)[["date", "amihud"]]
        f["stock_code"] = c
        feat_parts.append(f)
        lr = label_forward_returns(df, HORIZONS)
        lr["stock_code"] = c
        lab_parts.append(lr)
    feat = pd.concat(feat_parts, ignore_index=True)
    labs = pd.concat(lab_parts, ignore_index=True)
    feat["date"] = pd.to_datetime(feat["date"])
    labs["date"] = pd.to_datetime(labs["date"])
    return feat.merge(labs, on=["date", "stock_code"], how="inner")


def _scenario_rows(merged: pd.DataFrame, feat: str = "amihud") -> List[dict]:  # pragma: no cover
    rows = []
    for h in HORIZONS:
        label = f"fwd_{h}d"
        ppy = TRADING_DAYS_YR / h
        for tp in TOP_PCTS:
            # gross(무비용) 참조
            g = build_periods(merged, feat, label, tp, h, 0.0, 0.0, 0.0)
            gross_stats = period_stats(g["net"], ppy)
            for sc, (ft, sl, sh) in COST_SCENARIOS.items():
                per = build_periods(merged, feat, label, tp, h, ft, sl, sh)
                st = period_stats(per["net"], ppy)
                d = pd.to_datetime(per["date"])
                tr = period_stats(per.loc[d <= OOS_SPLIT, "net"], ppy)
                te = period_stats(per.loc[d > OOS_SPLIT, "net"], ppy)
                rows.append({
                    "horizon": h, "top_pct": tp, "scenario": sc,
                    "gross_cagr": gross_stats["cagr"], "gross_sharpe": gross_stats["sharpe"],
                    "net_cagr": st["cagr"], "net_sharpe": st["sharpe"],
                    "net_ann": st["ann_return"], "mean_cost": float(per["cost"].mean()),
                    "train_sharpe": tr["sharpe"], "test_sharpe": te["sharpe"],
                    "n_periods": st["n_periods"], "avg_n_held": float(per["n_held"].mean()),
                })
    return rows


def build_report(merged: pd.DataFrame) -> str:  # pragma: no cover
    tbl = pd.DataFrame(_scenario_rows(merged))
    pct = lambda c: (tbl[c] * 100).round(2)
    show = tbl.assign(
        top_pct=(tbl["top_pct"] * 100).round(0).astype(int).astype(str) + "%",
        gross_cagr=pct("gross_cagr"), gross_sharpe=tbl["gross_sharpe"].round(2),
        net_cagr=pct("net_cagr"), net_sharpe=tbl["net_sharpe"].round(2),
        net_ann=pct("net_ann"), mean_cost=pct("mean_cost"),
        train_sharpe=tbl["train_sharpe"].round(2), test_sharpe=tbl["test_sharpe"].round(2),
        avg_n_held=tbl["avg_n_held"].round(0).astype(int),
    )[["horizon", "top_pct", "scenario", "gross_sharpe", "net_sharpe", "net_cagr",
       "net_ann", "mean_cost", "train_sharpe", "test_sharpe", "n_periods", "avg_n_held"]]
    lines = [
        "# amihud Cost-Aware 분위 포트폴리오 백테스트 (Phase 0+ — 측정 전용)", "",
        "⚠️ 횡단면 IC만 통과한 amihud(비유동성)를 **롱온리 상위분위·유동성 차등비용**으로",
        "실거래 가능성 검증. 단일시장(KR)·가법비용근사·재량청산 미모델 — 탐색적.", "",
        "- 진입 T+1 시가 / 청산 close (라벨러와 동일, IC 측정과 정합)",
        "- 비용 = fee_tax + slip_low + (slip_high−slip_low)·(within-day amihud 백분위)",
        f"- 비용 시나리오: {COST_SCENARIOS}", "",
        "## 시나리오 × 호라이즌 × 분위", "",
        show.to_markdown(index=False), "",
        "## 판독 기준",
        "- net_sharpe>0 ∧ train/test 부호일치 = cost-aware 생존 후보.",
        "- mean_cost(보유 바스켓 평균 왕복비용)가 gross 를 잠식하면 = 비유동 프리미엄이",
        "  거래비용에 먹힘(피처 엣지 랩의 '비용 민감' 경고 정량화).",
    ]
    return "\n".join(lines)


def main():  # pragma: no cover
    import argparse
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    merged = collect_merged_panel(limit=args.limit)
    report = build_report(merged)
    out = os.path.join("reports", "discovery", "feature_edge", "amihud_cost_backtest.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[amihud-bt] {out} (merged rows {len(merged)})")


if __name__ == "__main__":
    main()

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


def evenly_spaced(items: List, n: int) -> List:
    """정렬 리스트에서 양 끝 포함·균등 간격으로 n개 선택(대표성 유지 축소).

    풀의 분포(여기선 amihud 비유동 분포)를 보존한 채 개수만 줄인다.
    n>=길이면 전체 반환.
    """
    m = len(items)
    if n >= m:
        return list(items)
    if n <= 1:
        return [items[0]] if m else []
    idx = sorted(set(int(round(i)) for i in np.linspace(0, m - 1, n)))
    return [items[i] for i in idx]


def sqrt_impact(participation, coef: float):
    """제곱근충격법칙 왕복 시장충격 = 2·coef·√참여율(participation=주문/일거래대금).

    매수·매도 양측에 충격 → 왕복 2배. 참여율 0 → 0. 스칼라/배열 허용.
    """
    return 2.0 * coef * np.sqrt(np.maximum(participation, 0.0))


def build_periods(merged: pd.DataFrame, feat: str, label: str, top_pct: float,
                  horizon: int, fee_tax: float, slip_low: float, slip_high: float,
                  illiq_feat: str = "amihud", capital=None, impact_coef: float = 0.0,
                  tv_col: str = "trading_value", hold_n=None) -> pd.DataFrame:
    """비중첩 리밸런스별 상위분위 롱 포트폴리오의 gross/cost/impact/net.

    merged: date, stock_code, feat, illiq_feat, label(fwd_{h}d) 보유 long DataFrame.
    리밸런스 날짜 = 정렬된 고유일자를 horizon 간격으로 비중첩 추출(중복계상 방지).
    각 리밸: 상위분위 동일가중 롱, gross=평균 label, cost=보유종목 차등비용 평균.
    capital 지정 시(+tv_col 존재): 종목당 자본/보유수 의 거래대금 대비 참여율로
    제곱근 시장충격을 가산(수용량 분석). net = gross − cost − impact.
    """
    df = merged.copy()
    df["date"] = pd.to_datetime(df["date"])
    all_dates = np.sort(df["date"].unique())
    rebal_dates = all_dates[::max(1, horizon)]
    use_impact = capital is not None and tv_col in df.columns

    rows = []
    for d in rebal_dates:
        day = df[df["date"] == d]
        codes = top_quantile_codes(day, feat, top_pct)  # nlargest 순(비유동↓ 정렬)
        if hold_n is not None and len(codes) > hold_n:
            codes = evenly_spaced(codes, hold_n)         # 분포 보존·개수만 축소
        held = day[day["stock_code"].isin(codes)].dropna(subset=[label])
        if len(held) == 0:
            continue
        illiq = illiquidity_pct(day, illiq_feat)  # 전체 횡단면 기준 백분위
        held_illiq = illiq.reindex(held["stock_code"]).fillna(0.5).values
        costs = tiered_cost(held_illiq, fee_tax, slip_low, slip_high)
        gross = float(held[label].mean())
        cost = float(np.mean(costs))
        impact = 0.0
        if use_impact:
            n = len(held)
            dollar_per_name = float(capital) / n
            tv = held[tv_col].astype(float).replace(0, np.nan).values
            part = dollar_per_name / tv
            imp = sqrt_impact(part, impact_coef)
            impact = float(np.nanmean(imp))
        rows.append({"date": pd.Timestamp(d), "n_held": int(len(held)),
                     "gross": gross, "cost": cost, "impact": impact,
                     "net": gross - cost - impact})
    return pd.DataFrame(rows)


def decile_stats(merged: pd.DataFrame, feat: str, label: str,
                 n_bins: int = 10) -> pd.DataFrame:
    """feat 분위(전기간 풀)별 평균 label — 단조성으로 단일버킷 아티팩트 여부 점검."""
    sub = merged[[feat, label]].dropna()
    if len(sub) < n_bins:
        return pd.DataFrame(columns=["bin", "mean_label", "n"])
    # 동일빈도 분위. 중복경계는 rank 기반으로 안전 분할.
    ranks = sub[feat].rank(method="first")
    sub = sub.assign(bin=pd.qcut(ranks, n_bins, labels=False))
    g = sub.groupby("bin")[label].agg(["mean", "count"]).reset_index()
    g.columns = ["bin", "mean_label", "n"]
    return g.sort_values("bin").reset_index(drop=True)


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


def benchmark_period_returns(index_df: pd.DataFrame, rebal_dates,
                             horizon: int) -> List[float]:
    """리밸런스 날짜별 지수 보유수익률 (포트와 동일 윈도우: 진입 D+1, 청산 D+1+h).

    지수는 종가만 있어 진입을 close[D+1] 로 근사(포트는 open[D+1]). 미래봉 부족 시 NaN.
    """
    idx = index_df.copy()
    idx["date"] = pd.to_datetime(idx["date"])
    idx = idx.sort_values("date").reset_index(drop=True)
    dates = idx["date"].values
    close = idx["close"].astype(float).values
    out = []
    for d in rebal_dates:
        pos = int(np.searchsorted(dates, np.datetime64(pd.Timestamp(d))))
        # d 가 지수일자에 정확히 없으면 searchsorted 위치를 D 로 간주(다음봉=진입).
        entry, exit_ = pos + 1, pos + 1 + horizon
        if exit_ < len(close) and entry < len(close):
            out.append(float(close[exit_] / close[entry] - 1.0))
        else:
            out.append(float("nan"))
    return out


def alpha_beta(port: pd.Series, mkt: pd.Series, periods_per_year: float) -> Dict[str, float]:
    """port = alpha + beta·mkt OLS → 알파(절편)·베타·초과수익 IR·승률.

    알파 = 시장베타 제거 후 잔여수익(>0 이면 비유동성 알파). NaN 페어 제거.
    """
    p = pd.Series(port).astype(float).reset_index(drop=True)
    m = pd.Series(mkt).astype(float).reset_index(drop=True)
    mask = p.notna() & m.notna()
    p, m = p[mask].values, m[mask].values
    n = len(p)
    if n < 3:
        return {"alpha": float("nan"), "beta": float("nan"), "alpha_ann": float("nan"),
                "mean_excess": float("nan"), "excess_ir": float("nan"),
                "win_rate": float("nan"), "mkt_ann": float("nan"), "n": n}
    beta, alpha = np.polyfit(m, p, 1)   # slope, intercept
    excess = p - m
    se = excess.std(ddof=1)
    ir = excess.mean() / se * math.sqrt(periods_per_year) if se and se > 0 else float("nan")
    return {"alpha": float(alpha), "beta": float(beta),
            "alpha_ann": float(alpha * periods_per_year),
            "mean_excess": float(excess.mean()),
            "excess_ir": float(ir), "win_rate": float((p > m).mean()),
            "mkt_ann": float(m.mean() * periods_per_year), "n": int(n)}


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
        f = compute_price_features(df)[["date", "amihud"]].copy()
        f["trading_value"] = (df["close"].astype(float) * df["volume"].astype(float)).values
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


def _scenario_rows(merged: pd.DataFrame, index_df: pd.DataFrame,
                   feat: str = "amihud") -> List[dict]:  # pragma: no cover
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
                # KOSPI 알파 분해(net 수익률 기준): net = alpha + beta·mkt.
                mkt = benchmark_period_returns(index_df, per["date"].tolist(), h)
                ab = alpha_beta(per["net"], pd.Series(mkt), ppy)
                rows.append({
                    "horizon": h, "top_pct": tp, "scenario": sc,
                    "gross_cagr": gross_stats["cagr"], "gross_sharpe": gross_stats["sharpe"],
                    "net_cagr": st["cagr"], "net_sharpe": st["sharpe"],
                    "net_ann": st["ann_return"], "mean_cost": float(per["cost"].mean()),
                    "train_sharpe": tr["sharpe"], "test_sharpe": te["sharpe"],
                    "n_periods": st["n_periods"], "avg_n_held": float(per["n_held"].mean()),
                    "beta": ab["beta"], "alpha_ann": ab["alpha_ann"],
                    "excess_ir": ab["excess_ir"], "win_rate": ab["win_rate"],
                    "mkt_ann": ab["mkt_ann"],
                })
    return rows


def build_report(merged: pd.DataFrame, index_df: pd.DataFrame) -> str:  # pragma: no cover
    tbl = pd.DataFrame(_scenario_rows(merged, index_df))
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
    # KOSPI 알파 분해 테이블 (net 기준)
    alp = tbl.assign(
        top_pct=(tbl["top_pct"] * 100).round(0).astype(int).astype(str) + "%",
        net_cagr=(tbl["net_cagr"] * 100).round(2), mkt_ann=(tbl["mkt_ann"] * 100).round(2),
        alpha_ann=(tbl["alpha_ann"] * 100).round(2), beta=tbl["beta"].round(2),
        excess_ir=tbl["excess_ir"].round(2), win_rate=(tbl["win_rate"] * 100).round(0).astype(int),
    )[["horizon", "top_pct", "scenario", "net_cagr", "mkt_ann", "alpha_ann",
       "beta", "excess_ir", "win_rate"]]
    lines = [
        "# amihud Cost-Aware 분위 포트폴리오 백테스트 (Phase 0+ — 측정 전용)", "",
        "⚠️ 횡단면 IC만 통과한 amihud(비유동성)를 **롱온리 상위분위·유동성 차등비용**으로",
        "실거래 가능성 검증. 단일시장(KR)·가법비용근사·재량청산 미모델 — 탐색적.", "",
        "- 진입 T+1 시가 / 청산 close (라벨러와 동일, IC 측정과 정합)",
        "- 비용 = fee_tax + slip_low + (slip_high−slip_low)·(within-day amihud 백분위)",
        f"- 비용 시나리오: {COST_SCENARIOS}", "",
        "## 시나리오 × 호라이즌 × 분위", "",
        show.to_markdown(index=False), "",
        "## KOSPI 알파 분해 (net = alpha + beta·mkt, OLS)", "",
        "롱온리라 시장베타 내재 — 알파(절편)>0 이면 비유동성 *알파*, β≈1·alpha≈0 이면 *베타*.",
        "mkt_ann=동일윈도우 KOSPI 연율, alpha_ann=베타제거 잔여 연율, excess_ir=초과수익 IR,",
        "win_rate=리밸런스별 시장초과 비율(%).", "",
        alp.to_markdown(index=False), "",
        "## 판독 기준",
        "- net_sharpe>0 ∧ train/test 부호일치 = cost-aware 생존 후보.",
        "- mean_cost(보유 바스켓 평균 왕복비용)가 gross 를 잠식하면 = 비유동 프리미엄이",
        "  거래비용에 먹힘(피처 엣지 랩의 '비용 민감' 경고 정량화).",
        "- alpha_ann>0 ∧ excess_ir>0 = 강세장 베타가 아닌 비유동성 알파의 증거.",
    ]
    return "\n".join(lines)


# ── (1) 수용량 · (2) 강건성 ─────────────────────────────────────────────────
# 헤드라인 구성(비용+베타 동시통과 최강): h=20일·top10%·동일가중.
HEAD_H, HEAD_TP = 20, 0.10
HEAD_COST = COST_SCENARIOS["base"]                       # 수용량은 base 비용 위에 충격 가산
CAPITALS = (10e6, 30e6, 100e6, 300e6, 1e9, 3e9, 10e9)    # 1천만~100억 KRW
IMPACT_COEFS = {"low": 0.02, "mid": 0.05, "high": 0.10}  # 제곱근법칙 계수(불확실 → 스윕)


def capacity_rows(merged: pd.DataFrame) -> List[dict]:  # pragma: no cover
    ft, sl, sh = HEAD_COST
    label = f"fwd_{HEAD_H}d"
    ppy = TRADING_DAYS_YR / HEAD_H
    rows = []
    for coef_name, coef in IMPACT_COEFS.items():
        for cap in CAPITALS:
            per = build_periods(merged, "amihud", label, HEAD_TP, HEAD_H, ft, sl, sh,
                                capital=cap, impact_coef=coef)
            st = period_stats(per["net"], ppy)
            rows.append({
                "impact_coef": coef_name, "capital_krw": cap,
                "mean_impact": float(per["impact"].mean()),
                "net_cagr": st["cagr"], "net_sharpe": st["sharpe"],
                "avg_n_held": float(per["n_held"].mean()),
            })
    return rows


def yearly_alpha_rows(merged: pd.DataFrame, index_df: pd.DataFrame) -> List[dict]:  # pragma: no cover
    ft, sl, sh = HEAD_COST
    label = f"fwd_{HEAD_H}d"
    ppy = TRADING_DAYS_YR / HEAD_H
    per = build_periods(merged, "amihud", label, HEAD_TP, HEAD_H, ft, sl, sh)
    per["year"] = pd.to_datetime(per["date"]).dt.year
    rows = []
    for yr, g in per.groupby("year"):
        mkt = benchmark_period_returns(index_df, g["date"].tolist(), HEAD_H)
        ab = alpha_beta(g["net"], pd.Series(mkt), ppy)
        st = period_stats(g["net"], ppy)
        rows.append({"year": int(yr), "n_periods": st["n_periods"],
                     "net_ann": st["ann_return"], "mkt_ann": ab["mkt_ann"],
                     "alpha_ann": ab["alpha_ann"], "beta": ab["beta"],
                     "win_rate": ab["win_rate"]})
    return rows


HOLD_NS = (10, 15, 20, 30, 40, 50, None)   # None=top10% 전체(~83)
PAPER_CAPITAL = 10_000_000                  # 가상매매 전략당 1천만 가정


def holdn_rows(merged: pd.DataFrame, index_df: pd.DataFrame) -> List[dict]:  # pragma: no cover
    """보유 종목수(N) 축소가 엣지를 유지하는지 — 분포보존 균등추출 스윕."""
    ft, sl, sh = HEAD_COST
    label = f"fwd_{HEAD_H}d"
    ppy = TRADING_DAYS_YR / HEAD_H
    rows = []
    for hn in HOLD_NS:
        per = build_periods(merged, "amihud", label, HEAD_TP, HEAD_H, ft, sl, sh, hold_n=hn)
        st = period_stats(per["net"], ppy)
        mkt = benchmark_period_returns(index_df, per["date"].tolist(), HEAD_H)
        ab = alpha_beta(per["net"], pd.Series(mkt), ppy)
        avg_n = float(per["n_held"].mean())
        rows.append({"hold_n": "top10%(~83)" if hn is None else str(hn),
                     "avg_n_held": avg_n, "net_sharpe": st["sharpe"],
                     "net_cagr": st["cagr"], "alpha_ann": ab["alpha_ann"],
                     "win_rate": ab["win_rate"],
                     "krw_per_name": PAPER_CAPITAL / max(avg_n, 1)})
    return rows


def build_robustness_report(merged: pd.DataFrame, index_df: pd.DataFrame) -> str:  # pragma: no cover
    # (2) 데실 단조성 — gross fwd_20d
    dec = decile_stats(merged, "amihud", "fwd_20d", n_bins=10)
    dec_show = dec.assign(mean_label=(dec["mean_label"] * 100).round(3))

    # (2) 연도별 알파
    yr = pd.DataFrame(yearly_alpha_rows(merged, index_df))
    yr_show = yr.assign(net_ann=(yr["net_ann"] * 100).round(2),
                        mkt_ann=(yr["mkt_ann"] * 100).round(2),
                        alpha_ann=(yr["alpha_ann"] * 100).round(2),
                        beta=yr["beta"].round(2),
                        win_rate=(yr["win_rate"] * 100).round(0).astype("Int64"))

    # (1) 수용량 곡선
    cap = pd.DataFrame(capacity_rows(merged))
    cap_show = cap.assign(
        capital=(cap["capital_krw"] / 1e8).round(1).astype(str) + "억",
        mean_impact=(cap["mean_impact"] * 100).round(2),
        net_cagr=(cap["net_cagr"] * 100).round(2), net_sharpe=cap["net_sharpe"].round(2),
    )[["impact_coef", "capital", "mean_impact", "net_cagr", "net_sharpe"]]

    tv_med = float(merged.loc[merged["amihud"].notna(), "trading_value"].median()) / 1e8

    # (보너스) 보유 종목수 N 축소 스윕 — 분산 하한
    hn = pd.DataFrame(holdn_rows(merged, index_df))
    hn_show = hn.assign(
        avg_n_held=hn["avg_n_held"].round(0).astype(int),
        net_sharpe=hn["net_sharpe"].round(2),
        net_cagr=(hn["net_cagr"] * 100).round(2),
        alpha_ann=(hn["alpha_ann"] * 100).round(2),
        win_rate=(hn["win_rate"] * 100).round(0).astype(int),
        krw_per_name=(hn["krw_per_name"] / 1e4).round(0).astype(int).astype(str) + "만",
    )[["hold_n", "avg_n_held", "net_sharpe", "net_cagr", "alpha_ann", "win_rate", "krw_per_name"]]

    lines = [
        "# amihud 강건성 · 수용량 분석 (Phase 0+ — 측정 전용)", "",
        f"헤드라인 구성: h={HEAD_H}일 · top{int(HEAD_TP*100)}% · 동일가중 · base 비용.", "",
        "## (2) 데실 단조성 — gross fwd_20d 평균(%)",
        "amihud 10분위 평균 선행수익. 단조 증가면 단일버킷 아티팩트가 아닌 연속 신호.", "",
        dec_show.to_markdown(index=False), "",
        "## (2) 연도별 알파 (net base 비용, KOSPI 대비)",
        "2022(약세장) 단독에서 알파 유지 여부가 '강세장 순풍' 우려의 최종 점검.", "",
        yr_show.to_markdown(index=False), "",
        "## (1) 수용량 — 제곱근 시장충격 가산 후 net",
        f"보유 바스켓 거래대금 중앙값 ≈ {tv_med:.1f}억/일. 종목당 자본=총자본/보유수,",
        "참여율=종목당자본/거래대금, 왕복충격=2·coef·√참여율. coef 불확실 → low/mid/high 스윕.", "",
        cap_show.to_markdown(index=False), "",
        "## (보너스) 보유 종목수 N 축소 — 분산 하한 (h=20·base 비용)",
        f"top10% 풀에서 분포보존 균등추출로 개수만 축소. krw_per_name=가상자본 "
        f"{PAPER_CAPITAL/1e4:.0f}만 ÷ 보유수(사이징 현실성).", "",
        hn_show.to_markdown(index=False), "",
        "## 판독",
        "- 데실 단조 = 신호 견고(꼬리버킷만의 우연 아님).",
        "- 2022 alpha_ann>0 = 약세장에서도 비유동 알파 = 강세장 베타 아님 확정.",
        "- 수용량: net_cagr 이 0 으로 꺼지는 자본 = 실효 capacity. 그 이하만 알파 실현.",
    ]
    return "\n".join(lines)


def main():  # pragma: no cover
    import argparse
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    from scripts.feature_edge import loaders
    merged = collect_merged_panel(limit=args.limit)
    index_df = loaders.load_index_df()
    rdir = os.path.join("reports", "discovery", "feature_edge")
    os.makedirs(rdir, exist_ok=True)
    out = os.path.join(rdir, "amihud_cost_backtest.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_report(merged, index_df))
    out2 = os.path.join(rdir, "amihud_robustness_capacity.md")
    with open(out2, "w", encoding="utf-8") as f:
        f.write(build_robustness_report(merged, index_df))
    print(f"[amihud-bt] {out} / {out2} (merged rows {len(merged)})")


if __name__ == "__main__":
    main()

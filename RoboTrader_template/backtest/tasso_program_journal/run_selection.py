# -*- coding: utf-8 -*-
"""PREREG_SELECTION.md 실행 — 매수후보 선정의 「드러난 선호」와 진입 타이밍.

라이브 트리 import 0건 (psycopg2 / pandas / numpy + 표준 라이브러리).
DB 는 SELECT 만.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

from run_tests import CODES, DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
RNG = np.random.default_rng(20260815)
NREP = 2000
PSEUDO = ("KOSPI", "KOSDAQ", "KS11", "KQ11")

# 창: 등록일 특정 건은 [D−4, D]; 미특정 건은 [직전 글 발행일(또는 출시일 7/11), 글 발행일]
POST_WINDOW = {
    "224364189017": ("2026-07-13", "2026-07-31"),   # 프로그램 출시 2026-07-11 → 첫 거래일
    "224371400049": ("2026-08-03", "2026-08-07"),
    "224378680510": ("2026-08-10", "2026-08-14"),
}
REG = {  # (post_log_no, item_no) -> 등록일
    ("224371400049", "1"): "2026-07-30", ("224371400049", "2"): "2026-07-28",
    ("224378680510", "2"): "2026-07-31", ("224378680510", "3"): "2026-08-04",
    ("224378680510", "4"): "2026-08-05", ("224378680510", "5"): "2026-08-06",
    ("224378680510", "6"): "2026-08-05",
}
FEATS = ["f1_tv_mcap", "f2_tv", "f3_tv_surge", "f4_vol20", "f5_pos60",
         "f6_spikes60", "f7_mcap", "f8_ma20dev", "f9_newhigh"]


def say(s=""):
    print(s)
    OUT.append(s)


def load():
    conn = psycopg2.connect(**DSN)
    df = pd.read_sql(
        "SELECT stock_code, date, high, low, close, trading_value, market_cap "
        "FROM daily_prices WHERE date BETWEEN '2026-04-01' AND '2026-08-14' "
        "AND market_cap IS NOT NULL AND market_cap > 0 AND close > 0", conn)
    conn.close()
    df = df[~df.stock_code.isin(PSEUDO)].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["stock_code", "date"]).reset_index(drop=True)


def build_features(df):
    g = df.groupby("stock_code", sort=False)
    df["f1_tv_mcap"] = df.trading_value / df.market_cap
    df["f2_tv"] = df.trading_value
    df["f3_tv_surge"] = df.trading_value / g.trading_value.transform(
        lambda s: s.rolling(20, min_periods=10).mean())
    ret = g.close.pct_change()
    df["f4_vol20"] = ret.groupby(df.stock_code).transform(
        lambda s: s.rolling(20, min_periods=10).std())
    df["f5_pos60"] = df.close / g.high.transform(
        lambda s: s.rolling(60, min_periods=20).max())
    df["f6_spikes60"] = (ret > 0.15).groupby(df.stock_code).transform(
        lambda s: s.rolling(60, min_periods=20).sum())
    df["f7_mcap"] = df.market_cap
    df["f8_ma20dev"] = df.close / g.close.transform(
        lambda s: s.rolling(20, min_periods=10).mean()) - 1
    prev_max = g.close.transform(lambda s: s.shift(1).rolling(60, min_periods=20).max())
    df["f9_newhigh"] = (df.close >= prev_max).astype(float)
    # 일자별 백분위 (그날 유니버스 기준, 0~100)
    for f in FEATS:
        df[f + "_pct"] = df.groupby("date")[f].rank(pct=True) * 100
    return df


def window_stat(df, code, d0, d1):
    """창 안 일별 백분위의 최댓값 (특징별)."""
    m = df[(df.stock_code == code) & (df.date >= d0) & (df.date <= d1)]
    if m.empty:
        return None
    return {f: m[f + "_pct"].max() for f in FEATS}


def holm(pvals):
    idx = np.argsort(pvals)
    n = len(pvals)
    adj = np.empty(n)
    run = 0.0
    for r, i in enumerate(idx):
        run = max(run, (n - r) * pvals[i])
        adj[i] = min(1.0, run)
    return adj


def main():
    df = build_features(load())
    say("# 매수후보 선정의 「드러난 선호」 + 진입 타이밍\n")
    say(f"유니버스 {df.stock_code.nunique():,}종목 · {df.date.nunique()}거래일 "
        f"({df.date.min().date()}~{df.date.max().date()})\n")

    trades = list(csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")))
    obs, windows, losses = [], [], []
    skipped = []
    for t in trades:
        key = (t["post_log_no"], t["item_no"])
        code = CODES.get(t["stock_name"])
        if code is None:
            skipped.append(t["stock_name"])
            continue
        if key in REG:
            d1 = pd.Timestamp(REG[key])
            d0 = d1 - pd.Timedelta(days=6)
        else:
            a, b = POST_WINDOW[t["post_log_no"]]
            d0, d1 = pd.Timestamp(a), pd.Timestamp(b)
        s = window_stat(df, code, d0, d1)
        if s is None:
            skipped.append(t["stock_name"] + "(창내 데이터 없음)")
            continue
        obs.append(s)
        windows.append((d0, d1))
        losses.append(t["all_loss"] == "1")
    say(f"양성 표본 **{len(obs)}건** / 원장 {len(trades)}건 · 제외 {skipped}\n")

    # ── §3 귀무: 창 길이를 보존한 무작위 종목 ──────────────────────────────
    codes = df.stock_code.unique()
    obs_med = {f: float(np.nanmedian([o[f] for o in obs])) for f in FEATS}
    obs_nan = {f: int(np.sum(~np.isfinite([o[f] for o in obs]))) for f in FEATS}
    null_med = {f: [] for f in FEATS}
    by_code = {c: g for c, g in df.groupby("stock_code")}
    for _ in range(NREP):
        draw = {f: [] for f in FEATS}
        for d0, d1 in windows:
            for _try in range(20):
                c = codes[RNG.integers(len(codes))]
                m = by_code[c]
                m = m[(m.date >= d0) & (m.date <= d1)]
                if not m.empty:
                    for f in FEATS:
                        draw[f].append(m[f + "_pct"].max())
                    break
        for f in FEATS:
            v = np.nanmedian(draw[f]) if draw[f] else np.nan
            if np.isfinite(v):
                null_med[f].append(float(v))

    pv = []
    for f in FEATS:
        arr = np.array(null_med[f])
        pv.append(float((arr >= obs_med[f]).mean()))
    adj = holm(np.array(pv))

    say("## §3 결과 — 관측 중앙 백분위 대 귀무 (창 길이 보존 · 2,000회)\n")
    say("| 특징 | 관측 중앙 백분위 | 귀무 중앙 | 관측 결측 | p | Holm p | 판정 |")
    say("|---|---|---|---|---|---|---|")
    verdict = {}
    for i, f in enumerate(FEATS):
        ok = (adj[i] < 0.05) and (obs_med[f] >= 90)
        verdict[f] = ok
        say(f"| `{f}` | **{obs_med[f]:.1f}** | {np.median(null_med[f]):.1f} | "
            f"{obs_nan[f]}/{len(obs)} | {pv[i]:.4f} | {adj[i]:.4f} | "
            f"{'✅ 연관' if ok else '⛔ 판별력 없음'} |")
    say(f"\n**Holm 보정 후 살아남은 특징: {[f for f in FEATS if verdict[f]] or '없음'}**\n")

    # ── §4 승/패 대조 게이트 ────────────────────────────────────────────────
    say("## §4 승/패 대조 — 결과 조건화 배제 게이트\n")
    from scipy.stats import mannwhitneyu
    lo = [o for o, L in zip(obs, losses) if L]
    wi = [o for o, L in zip(obs, losses) if not L]
    say(f"전패 건 **{len(lo)}** · 나머지 **{len(wi)}**\n")
    say("| 특징 | 전패 중앙 | 나머지 중앙 | p (양측) |")
    say("|---|---|---|---|")
    fails = []
    for f in FEATS:
        a = [o[f] for o in lo if np.isfinite(o[f])]
        b = [o[f] for o in wi if np.isfinite(o[f])]
        if len(a) < 2 or len(b) < 2:
            say(f"| `{f}` | (표본 부족) | | — |")
            continue
        try:
            p = mannwhitneyu(a, b, alternative="two-sided").pvalue
        except ValueError:
            p = 1.0
        if p < 0.05:
            fails.append(f)
        say(f"| `{f}` | {np.median(a):.1f} | {np.median(b):.1f} | {p:.4f} |")
    say()
    if fails:
        say(f"🔴 **게이트 실패** ({fails}) ⇒ §3 결과를 **「선정 규칙」으로 인용 금지**. "
            "*「올라온 매매의 진입 시점 모습」* 으로만 기술한다.")
    else:
        say("🟡 **게이트 통과** — 9개 전부 승/패 차이 p ≥ 0.05. "
            f"⚠️ 단 전패 {len(lo)}건뿐이라 **검정력이 매우 낮다. 「차이 없음」이 「같음」이 아니다.**")

    # ── §5 진입 타이밍 ──────────────────────────────────────────────────────
    say("\n## §5 진입 타이밍 — 등록일이 특정된 건만\n")
    say("| 종목 | 등록일 | t1 (90일창) | t1 (20일창) | t2 = 등록일−직전 +15%봉 | t3 = 60일 고가 대비 |")
    say("|---|---|---|---|---|---|")
    t1s, t1s20, t2s = [], [], []
    for (log_no, item), d in REG.items():
        name = next(t["stock_name"] for t in trades
                    if t["post_log_no"] == log_no and t["item_no"] == item)
        code = CODES[name]
        m = by_code[code]
        D = pd.Timestamp(d)
        hist = m[(m.date <= D) & (m.date >= D - pd.Timedelta(days=90))].reset_index(drop=True)
        if hist.empty:
            continue
        di = hist.index[hist.date == D]
        if len(di) == 0:
            continue
        di = di[0]
        t1 = di - int(hist.trading_value.idxmax())
        h20 = hist.iloc[max(0, di - 19):di + 1]
        t1s20_v = (di - int(h20.trading_value.idxmax()))
        r = hist.close.pct_change()
        sp = hist.index[(r > 0.15) & (hist.index <= di)]
        t2 = di - int(sp[-1]) if len(sp) else None
        t3 = float(hist.close.iloc[di] / hist.high.max())
        t1s.append(t1)
        t1s20.append(t1s20_v)
        t2s.append(t2)
        say(f"| {name} | {d} | **{t1}** | {t1s20_v} | {t2 if t2 is not None else '—'} | "
            f"{t3*100:.1f}% |")
    say(f"\n**사전등록 기준(90일 창) t1 중앙값 = {int(np.median(t1s))}** (예측: 0 또는 1) → "
        f"{'✅ 일치' if np.median(t1s) <= 1 else '❌ 불일치'}")
    say("⚠️ **사전등록이 「거래대금 최대일」의 창을 명시하지 않았다** — 「당시」를 특정 날짜로 "
        "못박은 것과 **같은 유형의 결함 2회째**다. 기각은 기각으로 둔다.")
    say(f"사후 민감도(20일 창) t1 중앙값 = **{int(np.median(t1s20))}** — 라벨: **사후**.")
    n0 = sum(1 for x in t2s if x == 0)
    say(f"\n🔑 **t2 = 0 인 건이 {n0}/{len(t2s)}** — 즉 **등록일 당일에 +15% 이상 급등**했다.")
    say("사전등록에 t2 예측은 없었다(기술 항목) ⇒ **다음 글 예측으로 등록할 것.**")
    say("⚠️ Q1 v2 의 *「등록일이 창 최고 고가 = 4/6」* 과 **독립이 아니다** — 일관성 확인으로만 쓴다.\n")

    (BASE / "RESULTS_SELECTION.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_SELECTION.md")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()

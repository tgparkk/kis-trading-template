# -*- coding: utf-8 -*-
"""유동성이냐 룩어헤드냐 — 사전등록 `PREREG.md`(동결) 실행부.

Arm: A(정적 top50·룩어헤드) / A'(PIT 롤링 top50) / N100·N300·N500 / R(무작위 50 × 시드)
     / B(라이브) / C(B+top10/일).  **유니버스 축 하나만** 바꾼다.

룰 평가는 (code, date) 캐시를 **1회** 만들어 전 arm 이 공유한다 —
arm 간에 「룰 평가가 달랐을 가능성」을 원천 차단한다.

라이브 트리 import 0건(전략/스크리너 «모듈»만) · DB 는 SELECT 만.
"""
from __future__ import annotations

import sys
import time
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

from backtest.book_backtester import BookBacktester                                   # noqa: E402
from strategies.base import Signal, SignalType                                        # noqa: E402
from strategies.book_envelope_200d.screener import BookEnvelope200dScreenerAdapter    # noqa: E402
from strategies.deep_mr_dev20.screener import DeepMrDev20ScreenerAdapter              # noqa: E402
from strategies.rs_leader.screener import RSLeaderScreenerAdapter                     # noqa: E402

DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
STOCK_ONLY = "stock_code ~ '^[0-9]{5}[0-9A-Z]$'"
W0, W1 = "2021-01-01", "2026-05-31"          # 사전등록 §3 — W-long 하나만
HIST0 = "2019-11-28"                          # 워밍업(실데이터는 2021-01-04 부터)
PIT_LB, PIT_MINP = 120, 60                    # PIT 롤링 거래대금 창
LADDER = [50, 100, 300, 500]
CAP_PER_DAY = 10

STRATS = {
    "book_envelope_200d": dict(screener=BookEnvelope200dScreenerAdapter, sl=0.08, tp=0.10,
                               mh=10, lookback=230, warmup=202, n_seeds=20),
    "deep_mr_dev20":      dict(screener=DeepMrDev20ScreenerAdapter,      sl=0.07, tp=0.12,
                               mh=7,  lookback=35,  warmup=35,  n_seeds=20),
    "rs_leader":          dict(screener=RSLeaderScreenerAdapter,         sl=0.08, tp=0.15,
                               mh=30, lookback=130, warmup=125, n_seeds=5),   # 기술통계 — §2
}
OUT: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    OUT.append(s)


class CachedGated:
    def __init__(self, trig, allowed):
        self.trig, self.allowed = trig, allowed

    def generate_signal(self, stock_code, df, timeframe="daily"):
        d = df["datetime"].iloc[-1].date()
        if self.trig.get(stock_code, {}).get(d) is None:
            return None
        if self.allowed is not None and stock_code not in self.allowed.get(d, ()):
            return None
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60)


def load_prices(conn):
    df = pd.read_sql(f"""
        SELECT stock_code, date, open, high, low, close, volume FROM daily_prices
        WHERE {STOCK_ONLY} AND date BETWEEN '{HIST0}' AND '{W1}' ORDER BY stock_code, date
    """, conn)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["datetime"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[~(df["close"].isna() | (df["close"] <= 0) | df["datetime"].isna())].copy()
    for c in ("open", "high", "low"):                       # 원 러너와 동일 보정
        m = df[c].isna() | (df[c] <= 0)
        df.loc[m, c] = df.loc[m, "close"]
    df["volume"] = df["volume"].fillna(0).clip(lower=0)
    return df.dropna(subset=["open", "high", "low", "close"])


def pit_ladder(px):
    """PIT 롤링 거래대금 상위 N → {N: {date: set(code)}}. 미래 미사용."""
    tv = px.assign(tv=px.close * px.volume).pivot_table(
        index="datetime", columns="stock_code", values="tv", aggfunc="last").sort_index()
    roll = tv.rolling(PIT_LB, min_periods=PIT_MINP).sum()
    out = {n: {} for n in LADDER}
    wd0 = pd.Timestamp(W0)
    for d, row in roll.iterrows():
        if d < wd0:
            continue
        r = row.dropna()
        if r.empty:
            continue
        order = r.sort_values(ascending=False)
        dd = d.date()
        for n in LADDER:
            out[n][dd] = set(order.index[:n])
    return out


def live_eligible(conn, screener):
    u = pd.read_sql(f"""
        SELECT date, stock_code, COALESCE(market_cap,0) AS market_cap,
               COALESCE(NULLIF(trading_value,0), (close*volume)::numeric, 0) AS trading_value
        FROM daily_prices
        WHERE {STOCK_ONLY} AND market_cap IS NOT NULL AND date BETWEEN '{W0}' AND '{W1}'
    """, conn)
    for c in ("market_cap", "trading_value"):
        u[c] = pd.to_numeric(u[c], errors="coerce").fillna(0)
    u["d"] = pd.to_datetime(u.date, errors="coerce").dt.date
    out = {}
    for d, g in u.groupby("d"):
        recs = [{"code": c, "name": c, "market_cap": m, "trading_value": t}
                for c, m, t in zip(g.stock_code, g.market_cap, g.trading_value)]
        out[d] = {r["code"] for r in screener.base_filter(recs)}
    return out


def static_top50(conn):
    return set(pd.read_sql(f"""
        SELECT stock_code FROM daily_prices WHERE {STOCK_ONLY}
        AND date BETWEEN '{W0}' AND '{W1}' GROUP BY stock_code
        ORDER BY SUM(close*volume) DESC LIMIT 50""", conn).stock_code)


def run_arm(trig, allowed, frames, cfg, codes=None):
    """arm 별 백테스트. 「트리거가 있고 그날 허용된」 종목만 순회한다(정확·저비용).

    `codes` 를 주면 «종목 집합 제한»(Arm A = 정적 top50 50종목만, 날짜 게이트 없음 —
    원 러너가 유니버스 종목만 넘기는 방식과 동일). `allowed` 는 «날짜별» 게이트다.
    """
    if codes is not None:
        codes = {c for c in codes if trig.get(c)}
    elif allowed is None:
        codes = set(trig)
    else:
        codes = {c for c, dd in trig.items() if any(c in allowed.get(d, ()) for d in dd)}
    bt = BookBacktester(strategy=CachedGated(trig, allowed), warmup_bars=cfg["warmup"],
                        stop_loss_pct=cfg["sl"], take_profit_pct=cfg["tp"],
                        max_hold_bars=cfg["mh"], eod_liquidate=False)
    tr = []
    for c in codes:
        g = frames.get(c)
        if g is not None:
            tr += bt.run_single(c, g).trades
    b = [t for t in tr if t["side"] == "buy"]
    s = [t for t in tr if t["side"] == "sell"]
    n = min(len(b), len(s))
    if n == 0:
        return dict(n=0, mean=float("nan"))
    pnl = pd.Series([s[i]["pnl_pct"] for i in range(n)])
    hold = pd.Series([s[i]["idx"] - b[i]["idx"] for i in range(n)])
    rs = pd.Series([str(s[i]["reason"]) for i in range(n)])
    return dict(n=n, mean=pnl.mean() * 100, med=pnl.median() * 100, win=(pnl > 0).mean() * 100,
                hold=hold.median(), sl=(rs == "stop_loss").mean() * 100,
                tp=(rs == "take_profit").mean() * 100)


def main() -> int:
    conn = psycopg2.connect(**DSN)
    say("# 유동성이냐 룩어헤드냐 — 실행 결과\n")
    say("사전등록 [`PREREG.md`](PREREG.md) 동결본. 창 = **W-long 2021-01-01~2026-05-31** 하나.\n")

    t0 = time.perf_counter()
    px = load_prices(conn)
    st50 = static_top50(conn)
    pit = pit_ladder(px)
    say(f"일봉 {len(px):,}행 / {px.stock_code.nunique():,}종목 · 정적 top50 {len(st50)} · "
        f"PIT 사다리 {len(pit[50]):,}일 · 준비 {time.perf_counter()-t0:.0f}s\n")
    ever50 = set().union(*pit[50].values())
    say(f"PIT top50 에 한 번이라도 든 고유 종목 **{len(ever50)}** · "
        f"정적 50 중 PIT 미포함 **{len(st50 - ever50)}**\n")

    for name, cfg in STRATS.items():
        scr = cfg["screener"]()
        params = scr.default_params()
        say(f"\n## `{name}`\n")
        t0 = time.perf_counter()
        elig = live_eligible(conn, scr)

        # ── 룰 평가 1회 (모든 arm 의 합집합) ────────────────────────────────
        wd0 = pd.Timestamp(W0).date()
        trig = defaultdict(dict)
        frames = {}
        n_eval = 0
        for code, g in px.groupby("stock_code", sort=False):
            g = g.reset_index(drop=True)
            frames[code] = g
            in_static = code in st50
            for i in range(cfg["warmup"], len(g)):
                d = g["datetime"].iloc[i].date()
                if d < wd0:
                    continue
                if not (in_static or code in elig.get(d, ()) or code in pit[500].get(d, ())):
                    continue
                v = scr.match(g.iloc[max(0, i + 1 - cfg["lookback"]):i + 1], params)
                n_eval += 1
                if v is not None:
                    trig[code][d] = float(v[0])
        say(f"룰 평가 {n_eval:,}회 / 발화 {sum(len(v) for v in trig.values()):,}건 "
            f"/ 종목 {len(trig):,} · {time.perf_counter()-t0:.0f}s\n")

        # ── arm 정의 ────────────────────────────────────────────────────────
        by_date = defaultdict(list)
        for code, dd in trig.items():
            for d, sc in dd.items():
                if code in elig.get(d, ()):
                    by_date[d].append((sc, code))
        arms = {
            "A  정적top50(룩어헤드)": None,      # ↓ codes=st50 로 «종목 제한»
            "A' PIT top50":          pit[50],
            "N100":                  pit[100],
            "N300":                  pit[300],
            "N500":                  pit[500],
            "B  라이브":              elig,
            "C  B+top10/일":          {d: {c for _, c in sorted(v, reverse=True)[:CAP_PER_DAY]}
                                       for d, v in by_date.items()},
        }
        res = {}
        for label, allowed in arms.items():
            t1 = time.perf_counter()
            res[label] = run_arm(trig, allowed, frames, cfg,
                                 codes=st50 if label.startswith("A  ") else None)
            print(f"    {label:24} n={res[label]['n']:>6} {time.perf_counter()-t1:.0f}s", flush=True)

        # ── 귀무 R ──────────────────────────────────────────────────────────
        dates = sorted(elig)
        pool = {d: sorted(elig[d]) for d in dates}
        r_means = []
        for seed in range(cfg["n_seeds"]):
            rng = np.random.RandomState(seed)
            allowed = {d: set(rng.choice(pool[d], size=min(50, len(pool[d])), replace=False))
                       for d in dates}
            m = run_arm(trig, allowed, frames, cfg)
            r_means.append(m["mean"])
            print(f"    R seed={seed:<2} n={m['n']:>6} mean={m['mean']:+.2f}%", flush=True)
        r = pd.Series(r_means).dropna()

        # ── 표 ──────────────────────────────────────────────────────────────
        say("| Arm | 거래 | 거래당 평균 | 중앙 | 승률 | 보유 중앙 | 손절 | 익절 |")
        say("|---|---|---|---|---|---|---|---|")
        for label, m in res.items():
            if not m.get("n"):
                say(f"| {label} | 0 | — | — | — | — | — | — |")
                continue
            say(f"| {label} | {m['n']} | **{m['mean']:+.2f}%** | {m['med']:+.2f}% | {m['win']:.0f}% | "
                f"{m['hold']:.0f}일 | {m['sl']:.0f}% | {m['tp']:.0f}% |")
        say(f"| **R 귀무** (n={len(r)}추첨) | — | 중앙 **{r.median():+.2f}%** "
            f"· 최소 {r.min():+.2f}% · **최대 {r.max():+.2f}%** | | | | | |")
        say()

        A, Ap, B = res["A  정적top50(룩어헤드)"]["mean"], res["A' PIT top50"]["mean"], res["B  라이브"]["mean"]
        gap = A - B
        keep = (Ap - B) / gap if abs(gap) > 1e-9 else float("nan")
        n1 = bool(len(r) and Ap > r.max())
        say(f"- **A − B = {gap:+.2f}%p** " +
            ("🔴 (≤0.5%p → 사전등록 §5-1 에 따라 판정 제외)" if abs(gap) <= 0.5 else "") + "\n")
        say(f"- **유지율 = (A′ − B) / (A − B) = ({Ap:+.2f} − {B:+.2f}) / {gap:+.2f} = "
            f"**{keep*100:.0f}%**\n")
        say(f"- **귀무 N1**: A′ {Ap:+.2f}% vs R 최대 {r.max():+.2f}% → "
            f"{'✅ A′ 가 R 20개 전부보다 큼' if n1 else '❌ 성립 안 함'}\n")

    conn.close()
    (BASE / "RESULTS_raw.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_raw.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

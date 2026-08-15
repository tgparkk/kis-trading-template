# -*- coding: utf-8 -*-
"""라이브 유니버스 재검증 — 사전등록 `PREREG.md`(동결) 실행부.

Arm A(top_volume:50) / B(라이브 PIT 유니버스) / C(B + top10-per-day) 를
**같은 백테스터·같은 룰·같은 청산**으로 돌려 «유니버스 축 하나»만 비교한다.

설계 요지
  - 룰 평가는 **한 번만** 한다. (code, date) → score 캐시를 만든 뒤 arm 별로
    게이트만 갈아끼운다. 그래야 arm 간에 「룰 평가가 달랐을 가능성」이 원천 차단된다.
  - score 함수는 **라이브 스크리너 클래스를 그대로 import** 해서 쓴다(재구현 금지, 사전등록 §2).

usage:
  python backtest/live_universe_revalidation/run.py --window live
  python backtest/live_universe_revalidation/run.py --window long

라이브 트리 import 0건(전략/스크리너 «모듈»만 import, 봇 런타임 미기동) · DB 는 SELECT 만.
"""
from __future__ import annotations

import argparse
import sys
import time
import warnings
from collections import defaultdict
from pathlib import Path

import pandas as pd
import psycopg2

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent.parent
sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

from backtest.book_backtester import BookBacktester          # noqa: E402
from strategies.base import Signal, SignalType               # noqa: E402
from strategies.book_envelope_200d.screener import BookEnvelope200dScreenerAdapter   # noqa: E402
from strategies.deep_mr_dev20.screener import DeepMrDev20ScreenerAdapter             # noqa: E402
from strategies.rs_leader.screener import RSLeaderScreenerAdapter                    # noqa: E402

DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
STOCK_ONLY = "stock_code ~ '^[0-9]{5}[0-9A-Z]$'"
WINDOWS = {"long": ("2021-01-01", "2026-05-31"), "live": ("2026-06-01", "2026-08-14")}
TOP_N, CAP_PER_DAY = 50, 10

# 라이브 config.yaml 1:1. 🔴 BookBacktester 는 sl/tp/max_hold 만 지원한다
# (rs_leader MA20 트레일·deep_mr MA20×0.9 회복은 «표현 불가») — arm 전체에 동일 적용되므로
# arm 간 비교에는 무해하나 절대 수준은 라이브와 다르다. RESULTS 에 명시한다.
STRATS = {
    "book_envelope_200d": dict(screener=BookEnvelope200dScreenerAdapter, sl=0.08, tp=0.10,
                               mh=10, lookback=230, warmup=202),
    "rs_leader":          dict(screener=RSLeaderScreenerAdapter,         sl=0.08, tp=0.15,
                               mh=30, lookback=130, warmup=125),
    "deep_mr_dev20":      dict(screener=DeepMrDev20ScreenerAdapter,      sl=0.07, tp=0.12,
                               mh=7,  lookback=35,  warmup=35),
}
OUT: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    OUT.append(s)


class CachedGated:
    """BookBacktester 가 호출하는 strategy 셰이프. 룰 재평가 없이 캐시 조회 + arm 게이트."""

    def __init__(self, trig: dict, allowed: dict | None):
        self.trig = trig            # {code: {date: score}}
        self.allowed = allowed      # {date: set(code)} · None = 무제한

    def generate_signal(self, stock_code, df, timeframe="daily"):
        d = df["datetime"].iloc[-1].date()
        if self.trig.get(stock_code, {}).get(d) is None:
            return None
        if self.allowed is not None and stock_code not in self.allowed.get(d, ()):
            return None
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60)


# ── 데이터 ───────────────────────────────────────────────────────────────────
def load_prices(conn, start: str, end: str) -> pd.DataFrame:
    df = pd.read_sql(f"""
        SELECT stock_code, date, open, high, low, close, volume
        FROM daily_prices WHERE {STOCK_ONLY} AND date BETWEEN '{start}' AND '{end}'
        ORDER BY stock_code, date
    """, conn)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["datetime"] = pd.to_datetime(df["date"], errors="coerce")
    # 거래정지/결손 보정 — 원 러너(run_daytrading_3methods.py:99-104 등)와 «동일 절차».
    # close 불량 행은 드롭하고, OHL 의 결측/비양수는 close 로 채운다.
    # 🔴 이 보정이 없으면 open=0 봉에서 BookBacktester 가 ZeroDivisionError 로 죽는다
    #    (W-long 1차 실행에서 실제 발생 — 데이터 준비 누락이었지 사양 변경이 아니다).
    n0 = len(df)
    df = df[~(df["close"].isna() | (df["close"] <= 0) | df["datetime"].isna())].copy()
    n_fill = 0
    for c in ("open", "high", "low"):
        m = df[c].isna() | (df[c] <= 0)
        n_fill += int(m.sum())
        df.loc[m, c] = df.loc[m, "close"]
    df["volume"] = df["volume"].fillna(0).clip(lower=0)
    df = df.dropna(subset=["open", "high", "low", "close"])
    say(f"OHLC 보정: 드롭 {n0-len(df):,}행 · OHL 채움 {n_fill:,}칸 (원 러너와 동일 절차)\n")
    return df


def pit_eligible(conn, start: str, end: str, screener) -> dict:
    """라이브 `get_universe_snapshot` + `base_filter` 재현 → {date: set(code)}.

    스냅샷은 `market_cap IS NOT NULL` 행만 반환한다(라이브와 동일) — 시총 «컷» 은 안 써도
    유니버스 «소속 자격»이 시총 존재에 걸린다(사전등록 §1).
    """
    u = pd.read_sql(f"""
        SELECT date, stock_code,
               COALESCE(market_cap, 0) AS market_cap,
               COALESCE(NULLIF(trading_value, 0), (close * volume)::numeric, 0) AS trading_value
        FROM daily_prices
        WHERE {STOCK_ONLY} AND market_cap IS NOT NULL AND date BETWEEN '{start}' AND '{end}'
    """, conn)
    u["market_cap"] = pd.to_numeric(u.market_cap, errors="coerce").fillna(0)
    u["trading_value"] = pd.to_numeric(u.trading_value, errors="coerce").fillna(0)
    u["d"] = pd.to_datetime(u.date, errors="coerce").dt.date
    out: dict = {}
    for d, g in u.groupby("d"):
        recs = [{"code": c, "name": c, "market_cap": m, "trading_value": t}
                for c, m, t in zip(g.stock_code, g.market_cap, g.trading_value)]
        out[d] = {r["code"] for r in screener.base_filter(recs)}
    return out


def top_volume(conn, start: str, end: str, n: int) -> set:
    return set(pd.read_sql(f"""
        SELECT stock_code FROM daily_prices
        WHERE {STOCK_ONLY} AND date BETWEEN '{start}' AND '{end}'
        GROUP BY stock_code ORDER BY SUM(close * volume) DESC LIMIT {n}
    """, conn).stock_code)


# ── 메트릭 ───────────────────────────────────────────────────────────────────
def metrics(trades: list, months: float) -> dict:
    b = [t for t in trades if t["side"] == "buy"]
    s = [t for t in trades if t["side"] == "sell"]
    n = min(len(b), len(s))
    if n == 0:
        return dict(n=0)
    hold = pd.Series([s[i]["idx"] - b[i]["idx"] for i in range(n)])
    pnl = pd.Series([s[i]["pnl_pct"] for i in range(n)])
    rs = pd.Series([str(s[i]["reason"]) for i in range(n)])
    return dict(
        n=n, mean=pnl.mean() * 100, med=pnl.median() * 100, win=(pnl > 0).mean() * 100,
        hold_med=hold.median(), le1=(hold <= 1).mean() * 100,
        sl=(rs == "stop_loss").mean() * 100, tp=(rs == "take_profit").mean() * 100,
        mh=(rs == "max_hold").mean() * 100, permo=len(b) / months,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", choices=list(WINDOWS), required=True)
    ap.add_argument("--strategy", default=None)
    args = ap.parse_args()
    w0, w1 = WINDOWS[args.window]
    months = (pd.Timestamp(w1) - pd.Timestamp(w0)).days / 30.44

    conn = psycopg2.connect(**DSN)
    say(f"# 라이브 유니버스 재검증 — 창 `{args.window}` ({w0} ~ {w1})\n")
    say("사전등록 [`PREREG.md`](PREREG.md) 동결본 실행. **Arm A 는 「기존 검증 재현」이 아니다**"
        "(§8-2) — A·B·C **사이의 차이**만 읽을 것.\n")

    # 룰 워밍업(최대 230봉)을 채우려면 창 «이전» 히스토리가 필요하다.
    # 단 «발화(진입)는 창 안으로만» 제한한다 — 아래 `d < wd0` 스킵.
    hist0 = (pd.Timestamp(w0) - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    wd0 = pd.Timestamp(w0).date()

    t0 = time.perf_counter()
    px = load_prices(conn, hist0, w1)
    top50 = top_volume(conn, w0, w1, TOP_N)     # 유니버스 정의는 창 기준(원 러너와 동일)
    say(f"일봉 {len(px):,}행 / {px.stock_code.nunique():,}종목 "
        f"(워밍업 히스토리 {hist0}~ 포함) · `top_volume:50` {len(top50)}종목 "
        f"· 로드 {time.perf_counter()-t0:.0f}s\n")
    if pd.Timestamp(px.date.min()) > pd.Timestamp(hist0) + pd.Timedelta(days=30):
        say(f"⚠️ **워밍업 히스토리 부족** — 데이터 최소일 {px.date.min()} > 요청 {hist0}. "
            "긴 룩백 룰(envelope 202봉)은 창 «앞부분»에서 발화하지 못한다.\n")

    targets = [args.strategy] if args.strategy else list(STRATS)
    for name in targets:
        cfg = STRATS[name]
        scr = cfg["screener"]()
        params = scr.default_params()
        say(f"\n## `{name}`\n")

        t0 = time.perf_counter()
        elig = pit_eligible(conn, w0, w1, scr)
        usz = pd.Series({d: len(v) for d, v in elig.items()})
        say(f"라이브 PIT 유니버스 일별 크기: 중앙 **{usz.median():.0f}** "
            f"(최소 {usz.min()} · 최대 {usz.max()}) · 일수 {len(usz)}\n")

        # ── 룰 평가 1회 → (code, date) → score 캐시 ──────────────────────────
        trig: dict = defaultdict(dict)
        frames: dict = {}
        n_eval = 0
        for code, g in px.groupby("stock_code", sort=False):
            g = g.reset_index(drop=True)
            frames[code] = g
            in_top = code in top50
            for i in range(cfg["warmup"], len(g)):
                d = g["datetime"].iloc[i].date()
                if d < wd0:                      # 워밍업 구간 — 진입 금지(창 밖)
                    continue
                if not (in_top or code in elig.get(d, ())):
                    continue
                v = scr.match(g.iloc[max(0, i + 1 - cfg["lookback"]):i + 1], params)
                n_eval += 1
                if v is not None:
                    trig[code][d] = float(v[0])
        say(f"룰 평가 {n_eval:,}회 / 발화 {sum(len(v) for v in trig.values()):,}건 "
            f"· {time.perf_counter()-t0:.0f}s\n")

        # ── arm 별 게이트 ────────────────────────────────────────────────────
        by_date: dict = defaultdict(list)
        for code, dd in trig.items():
            for d, sc in dd.items():
                if code in elig.get(d, ()):
                    by_date[d].append((sc, code))
        allowed_C = {d: {c for _, c in sorted(v, reverse=True)[:CAP_PER_DAY]}
                     for d, v in by_date.items()}

        arms = {
            "A (top50)":      (top50, None),
            "B (라이브)":     (set(frames), elig),
            "C (B+top10/일)": (set(frames), allowed_C),
        }
        rows = {}
        for label, (codes, allowed) in arms.items():
            bt = BookBacktester(
                strategy=CachedGated(trig, allowed),
                warmup_bars=cfg["warmup"], stop_loss_pct=cfg["sl"],
                take_profit_pct=cfg["tp"], max_hold_bars=cfg["mh"],
                eod_liquidate=False,   # 🔴 arm 간 종목수가 40배 달라 강제청산은 비교를 오염시킨다
            )
            trades = []
            for code in codes:
                g = frames.get(code)
                if g is None or not trig.get(code):
                    continue
                trades += bt.run_single(code, g).trades
            rows[label] = metrics(trades, months)

        say("| Arm | 거래 | 거래당 평균 | 중앙 | 승률 | 보유 중앙 | ≤1일 | 손절 | 익절 | max_hold | 월 매수 |")
        say("|---|---|---|---|---|---|---|---|---|---|---|")
        for label, m in rows.items():
            if not m.get("n"):
                say(f"| {label} | **0** | — | — | — | — | — | — | — | — | — |")
                continue
            say(f"| {label} | {m['n']} | **{m['mean']:+.2f}%** | {m['med']:+.2f}% | {m['win']:.0f}% | "
                f"**{m['hold_med']:.0f}일** | **{m['le1']:.0f}%** | {m['sl']:.0f}% | {m['tp']:.0f}% | "
                f"{m['mh']:.0f}% | {m['permo']:.1f} |")
        say()

    conn.close()
    (BASE / f"RESULTS_{args.window}.md").write_text("\n".join(OUT), encoding="utf-8")
    print(f"\n[written] RESULTS_{args.window}.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

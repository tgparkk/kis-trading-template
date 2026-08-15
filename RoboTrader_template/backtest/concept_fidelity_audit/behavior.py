# -*- coding: utf-8 -*-
"""컨셉 충실도 감사 ④층 — 「선언」이 아니라 「실제로 어떻게 굴렀나」를 잰다.

①원전 ②백테스트룰 ③라이브구현 은 코드를 읽으면 나온다. 이 스크립트는 ④만 담당한다:
  - 진입 시각 분포 (KST)  → 「데이트레이딩인가」의 실측 답
  - 보유기간 분포          → 선언 max_hold 가 실제로 바인딩되는가
  - 청산사유 분포          → 어느 청산 다리로 빠지는가
  - 실측 발사빈도          → 백테스트 기대빈도와 몇 배 차이인가

🔑 이건 기술 통계다. 귀무가 필요한 주장은 여기서 하지 않는다.
라이브 트리 import 0건 · DB 는 SELECT 만.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd
import psycopg2

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

BASE = Path(__file__).resolve().parent
DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
D0, D1 = "2026-06-01", "2026-08-14"
OUT: list[str] = []

# 각 전략이 «선언한» 값 (config.yaml SSOT, 2026-08-15 판독)
DECLARED = {
    # key: (max_hold_days, sl%, tp%, K, trail)
    "elder_ema_pullback":            (100, 8,  30, 20, "EMA13"),
    "book_envelope_200d":            (10,  8,  10, 5,  "없음"),
    "daytrading_3methods_breakout":  (10,  10, 10, 5,  "없음"),
    "minervini_volume_dryup":        (20,  8,  12, 3,  "없음"),
    "book_pullback_ma20":            (50,  8,  10, 5,  "MA20"),
    "book_pullback_ma5":             (30,  3,  15, 5,  "MA5"),
    "rs_leader":                     (30,  8,  15, 10, "MA20"),
    "deep_mr_dev20":                 (7,   7,  12, 5,  "MA20x0.9"),
}


def say(s: str = "") -> None:
    print(s)
    OUT.append(s)


def cat(reason: str | None) -> str:
    r = reason or ""
    for k, v in (("손절", "손절"), ("목표 익절", "익절"), ("보유기간", "보유기간"),
                 ("트레일", "트레일링"), ("추적", "트레일링")):
        if k in r:
            return v
    return "기타"


def load():
    conn = psycopg2.connect(**DSN)
    tr = pd.read_sql(f"""
        SELECT s.stock_code, s.timestamp AS sell_ts, s.price AS sell_price,
               s.strategy, s.reason,
               b.timestamp AS buy_ts, b.price AS buy_price
        FROM virtual_trading_records s
        JOIN virtual_trading_records b ON b.id = s.buy_record_id
        WHERE s.action='SELL' AND s.timestamp::date BETWEEN '{D0}' AND '{D1}'
    """, conn)
    buys = pd.read_sql(f"""
        SELECT stock_code, timestamp AS buy_ts, price, strategy
        FROM virtual_trading_records
        WHERE action='BUY' AND timestamp::date BETWEEN '{D0}' AND '{D1}'
    """, conn)
    conn.close()
    for d in (tr, buys):
        for c in [c for c in ("sell_price", "buy_price", "price") if c in d.columns]:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        for c in [c for c in ("buy_ts", "sell_ts") if c in d.columns]:
            # DB 는 UTC(tz-aware) → KST 로 변환해 「몇 시에 샀나」를 사람 시간으로 읽는다.
            d[c] = pd.to_datetime(d[c], utc=True).dt.tz_convert("Asia/Seoul")
    return tr, buys


def main() -> int:
    tr, buys = load()
    tr["ret"] = tr.sell_price / tr.buy_price - 1
    tr["hold"] = (tr.sell_ts.dt.normalize() - tr.buy_ts.dt.normalize()).dt.days
    tr["cat"] = tr.reason.map(cat)
    buys["hhmm"] = buys.buy_ts.dt.strftime("%H:%M")
    months = (pd.Timestamp(D1) - pd.Timestamp(D0)).days / 30.44

    say("# ④ 실제 거동 — 실측 (2026-06-01~08-14)\n")
    say(f"매수 **{len(buys)}건** · 청산완료 **{len(tr)}건** · 관측 {months:.1f}개월 · "
        "🔴 미청산 보유분은 표본 밖.\n")

    # ── A. 진입 시각 — 「데이트레이딩인가」의 실측 답 ─────────────────────────
    say("## A. 진입 시각 분포 (KST)\n")
    say("| 전략 | 매수 | 최초 | 중앙 | 최종 | 09:00~09:05 비중 |")
    say("|---|---|---|---|---|---|")
    for st, g in buys.groupby("strategy"):
        t = g.buy_ts.dt.hour * 60 + g.buy_ts.dt.minute
        early = (t <= 9 * 60 + 5).mean() * 100
        med = int(t.median())
        say(f"| {st} | {len(g)} | {g.hhmm.min()} | {med//60:02d}:{med%60:02d} | "
            f"{g.hhmm.max()} | {early:.0f}% |")
    t_all = buys.buy_ts.dt.hour * 60 + buys.buy_ts.dt.minute
    say(f"\n전체: 최초 {buys.hhmm.min()} · 최종 {buys.hhmm.max()} · "
        f"09:00~09:05 비중 **{(t_all <= 9*60+5).mean()*100:.0f}%** · "
        f"10시 이후 {(t_all >= 10*60).mean()*100:.0f}%\n")

    # ── B. 보유기간 — 선언 max_hold 가 바인딩되는가 ──────────────────────────
    say("## B. 보유기간 — 선언 max_hold vs 실측\n")
    say("| 전략 | 선언 max_hold | 실측 중앙 | 실측 평균 | 실측 최장 | 당일청산 | ≤1일 | max_hold 도달 |")
    say("|---|---|---|---|---|---|---|---|")
    for st, g in tr.groupby("strategy"):
        mh = DECLARED.get(st, (None,))[0]
        reach = (g.cat == "보유기간").sum()
        say(f"| {st} | {mh}일 | **{g.hold.median():.0f}일** | {g.hold.mean():.1f}일 | "
            f"{g.hold.max():.0f}일 | {int((g.hold == 0).sum())} | "
            f"**{(g.hold <= 1).mean()*100:.0f}%** | {reach}건 |")
    say()

    # ── C. 청산사유 ──────────────────────────────────────────────────────────
    say("## C. 청산 사유 분포 (건수)\n")
    cats = ["손절", "익절", "트레일링", "보유기간", "기타"]
    say("| 전략 | " + " | ".join(cats) + " | 손절비중 |")
    say("|---|" + "---|" * (len(cats) + 1))
    for st, g in tr.groupby("strategy"):
        row = [str(int((g.cat == c).sum())) for c in cats]
        say(f"| {st} | " + " | ".join(row) + f" | **{(g.cat=='손절').mean()*100:.0f}%** |")
    say()

    # ── D. 손절/익절 실현폭이 선언값과 맞나 ──────────────────────────────────
    say("## D. 청산폭 정합 — 선언 sl/tp vs 실현 중앙\n")
    say("| 전략 | 선언 sl | 손절 실현중앙 | 괴리 | 선언 tp | 익절 실현중앙 | 괴리 |")
    say("|---|---|---|---|---|---|---|")
    for st, g in tr.groupby("strategy"):
        d = DECLARED.get(st)
        if not d:
            continue
        _, sl, tp, _, _ = d
        gs, gt = g[g.cat == "손절"], g[g.cat == "익절"]
        sm = gs.ret.median() * 100 if len(gs) else float("nan")
        tm = gt.ret.median() * 100 if len(gt) else float("nan")
        say(f"| {st} | −{sl}% | {sm:+.2f}% | {sm+sl:+.2f}%p | +{tp}% | {tm:+.2f}% | {tm-tp:+.2f}%p |")
    say()

    # ── E. 발사 빈도 ─────────────────────────────────────────────────────────
    say("## E. 발사 빈도 — 월 몇 회 사는가\n")
    say("| 전략 | 매수 | 월평균 | K | 매수/K (자본 회전) |")
    say("|---|---|---|---|---|")
    for st, g in buys.groupby("strategy"):
        k = DECLARED.get(st, (0, 0, 0, 0))[3]
        say(f"| {st} | {len(g)} | **{len(g)/months:.1f}회** | {k} | {len(g)/k:.1f}× |")
    say()

    (BASE / "BEHAVIOR.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] BEHAVIOR.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

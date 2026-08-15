# -*- coding: utf-8 -*-
"""8전략은 왜 전부 마이너스인가 — 1단계: 손익 «분해» (기술 통계 · 사전등록 불필요).

🔑 이 문서는 **항등식**만 다룬다: `실현손익 = 시장성분 + 초과성분`.
   예측할 것이 없으므로 사전등록하지 않는다. 귀무가 필요한 질문(「선택이 무작위보다 나쁜가」)은
   2단계에서 **사전등록 후** 잰다.

선행: `crash_gate_counterfactual`(bc9b0b7) — 게이트는 옳았다 ·
      `stoploss_counterfactual`(b6e12b8) — 청산도 옳았다. 남은 건 «사는 것»이다.

라이브 트리 import 0건 · DB 는 SELECT 만 · `utils/logger.py` 미사용.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
FEE = 0.00015 * 2 + 0.0018      # 수수료 양방향 + 거래세 ≈ 0.21%p


def say(s=""):
    print(s)
    OUT.append(s)


def load():
    conn = psycopg2.connect(**DSN)
    tr = pd.read_sql("""
        SELECT s.stock_code, s.timestamp::date AS sell_date, s.price AS sell_price,
               s.profit_rate, s.strategy, s.reason,
               b.timestamp::date AS buy_date, b.price AS buy_price
        FROM virtual_trading_records s
        JOIN virtual_trading_records b ON b.id = s.buy_record_id
        WHERE s.action='SELL' AND s.timestamp::date BETWEEN '2026-06-01' AND '2026-08-14'
    """, conn)
    buys = pd.read_sql("""
        SELECT stock_code, timestamp::date AS d, price, strategy FROM virtual_trading_records
        WHERE action='BUY' AND timestamp::date BETWEEN '2026-06-01' AND '2026-08-14'
    """, conn)
    idx = pd.read_sql("""
        SELECT stock_code, date, close FROM daily_prices
        WHERE stock_code IN ('KOSPI','KOSDAQ') AND date BETWEEN '2026-05-20' AND '2026-08-14'
    """, conn)
    mkt = pd.read_sql("SELECT stock_code, market FROM stock_market", conn)
    conn.close()
    for c in ("sell_price", "buy_price", "profit_rate"):
        tr[c] = pd.to_numeric(tr[c], errors="coerce")
    tr["buy_date"] = tr["buy_date"].astype(str)
    tr["sell_date"] = tr["sell_date"].astype(str)
    idx["close"] = pd.to_numeric(idx["close"], errors="coerce")
    ic = idx.pivot_table(index="date", columns="stock_code", values="close", aggfunc="last").sort_index()
    return tr, buys, ic, dict(zip(mkt.stock_code, mkt.market))


def main() -> int:
    tr, buys, ic, market = load()
    say("# 8전략은 왜 전부 마이너스인가 — 1단계 손익 분해\n")
    say("🔑 **이 문서는 항등식(기술 통계)이다.** 예측이 없어 사전등록하지 않았다. "
        "귀무가 필요한 질문은 2단계에서 사전등록 후 잰다.\n")
    say(f"기간 2026-06-01~08-14 · 매수 **{len(buys)}건** · **청산 완료 {len(tr)}건**"
        f"(매수-매도 짝) · 🔴 **미청산 보유분은 표본 밖**이다.\n")

    tr["ret"] = tr.sell_price / tr.buy_price - 1
    tr["net"] = tr["ret"] - FEE
    tr["mkt"] = [
        (lambda m, a, b: np.nan if m not in ic.columns or a not in ic.index or b not in ic.index
         else (ic.at[b, m] / ic.at[a, m] - 1))(market.get(r.stock_code), r.buy_date, r.sell_date)
        for r in tr.itertuples()]
    tr["exc"] = tr["ret"] - tr["mkt"]

    # ── ① 승률과 손익비 — 구조가 지는 구조인가 ──────────────────────────────
    win, loss = tr[tr.ret > 0], tr[tr.ret <= 0]
    p = len(win) / len(tr)
    aw, al = float(win.ret.mean()), float(-loss.ret.mean())
    ev = p * aw - (1 - p) * al
    need = al / (aw + al)
    say("## ① 승률 × 손익비 — 구조부터 본다\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 승률 | **{p*100:.1f}%** ({len(win)}/{len(tr)}) |")
    say(f"| 평균 이익 | +{aw*100:.2f}% |")
    say(f"| 평균 손실 | −{al*100:.2f}% |")
    say(f"| 손익비 | {aw/al:.2f} : 1 |")
    say(f"| 기대값(gross) | **{ev*100:+.2f}%** / 거래 |")
    say(f"| 기대값(net, 비용 {FEE*100:.2f}%p) | **{(ev-FEE)*100:+.2f}%** / 거래 |")
    say(f"| **손익비를 유지하며 본전 되려면 필요한 승률** | **{need*100:.1f}%** |")
    say()
    gap = (need - p) * 100
    say(f"🔑 ***승률이 필요치보다 {gap:.1f}%p 모자란다.*** "
        f"손익비 {aw/al:.2f}:1 자체는 나쁘지 않다 — **문제는 이기는 «빈도»**다.\n"
        if gap > 0 else
        f"🟢 승률이 필요치를 {-gap:.1f}%p 넘는다 — 구조는 이기는 구조다.\n")

    # ── ② 시장 성분 vs 선택 성분 (항등식) ───────────────────────────────────
    ok = tr.dropna(subset=["mkt"])
    say("## ② 손익 분해 — `실현 = 시장 + 초과` (항등식)\n")
    say(f"소속 지수 결측 **{len(tr)-len(ok)}/{len(tr)}건** 제외(조용히 빼지 않는다).\n")
    say("| 성분 | 평균 | 중앙 |")
    say("|---|---|---|")
    say(f"| 실현 수익률 | **{ok.ret.mean()*100:+.2f}%** | {ok.ret.median()*100:+.2f}% |")
    say(f"| 시장 성분(보유기간 지수) | {ok.mkt.mean()*100:+.2f}% | {ok.mkt.median()*100:+.2f}% |")
    say(f"| **초과 성분(종목 선택)** | **{ok.exc.mean()*100:+.2f}%** | {ok.exc.median()*100:+.2f}% |")
    say()
    share = ok.mkt.mean() / ok.ret.mean() * 100 if ok.ret.mean() else float("nan")
    say(f"🔑 평균 실현 {ok.ret.mean()*100:+.2f}% 중 **시장이 {ok.mkt.mean()*100:+.2f}%p**, "
        f"**종목 선택이 {ok.exc.mean()*100:+.2f}%p** 다. "
        + ("***손실의 대부분은 시장이 아니라 «선택»에서 나온다.***\n"
           if ok.exc.mean() < ok.mkt.mean() else
           "***손실의 대부분은 «시장»에서 나온다 — 선택은 오히려 시장을 이겼다.***\n"))

    # ── ③ 보유기간 ───────────────────────────────────────────────────────────
    d0 = pd.to_datetime(tr.buy_date); d1 = pd.to_datetime(tr.sell_date)
    tr["hold"] = (d1 - d0).dt.days
    say("## ③ 보유기간 — 🔴 여기가 이상하다\n")
    say(f"중앙 **{tr.hold.median():.0f}일** · 평균 {tr.hold.mean():.1f}일 · "
        f"당일청산 {int((tr.hold==0).sum())}건 · 10일 초과 {int((tr.hold>10).sum())}건\n")

    def cat0(r):
        r = r or ""
        for k, v in (("손절", "손절"), ("목표 익절", "익절"), ("보유기간", "보유기간"),
                     ("트레일", "트레일링"), ("추적", "트레일링")):
            if r.startswith(k) or k in r:
                return v
        return "기타"
    tr["cat"] = tr.reason.map(cat0)
    sl = tr[tr.cat == "손절"]
    say("**손절 건의 보유기간 분포** — 손절폭이 −8%대인데 며칠 만에 맞았나:\n")
    say("| 보유 | 건수 | 비중 | 평균 실현 |")
    say("|---|---|---|---|")
    bins = [(0, 0, "당일"), (1, 1, "1일"), (2, 3, "2~3일"), (4, 7, "4~7일"), (8, 10**6, "8일+")]
    for lo, hi, lab in bins:
        g = sl[(sl.hold >= lo) & (sl.hold <= hi)]
        if len(g):
            say(f"| {lab} | {len(g)} | {len(g)/len(sl)*100:.0f}% | {g.ret.mean()*100:+.2f}% |")
    fast = int((sl.hold <= 1).sum())
    say(f"\n🔴 ***손절 {len(sl)}건 중 {fast}건({fast/len(sl)*100:.0f}%)이 매수 후 «1일 이내»에 "
        f"−8%대를 맞았다.*** 하루 만에 8% 빠지는 건 흔치 않다 ⇒ "
        "***매수 직후 손절이 「진짜 하락」이 아니라 「매수가와 평가 기준의 불일치」일 가능성***을 "
        "먼저 의심해야 한다.")
    say("🔑 이건 새 발견이 아니라 **기존 미해결 항목과 이어진다** — 메모리의 "
        "*「whipsaw 경로 = 매수시점 ≠ 평가기준일」*(신규 매수분은 entry=당일가인데 평가는 "
        "전일 확정봉 기준이라 즉시 발화 가능). ⚠️ **여기서는 «정황»만 보였다. "
        "인과는 코드 경로를 직접 봐야 한다 — 2단계 표적.**\n")
    say("| 청산사유 | 건수 | 보유 중앙 | 1일 이내 비중 |")
    say("|---|---|---|---|")
    for c, g in tr.groupby("cat"):
        say(f"| {c} | {len(g)} | {g.hold.median():.0f}일 | {(g.hold<=1).mean()*100:.0f}% |")
    say()

    # ── ④ 전략별 ────────────────────────────────────────────────────────────
    say("## ④ 전략별 (청산 완료 기준)\n")
    say("| 전략 | 거래 | 승률 | 평균 실현 | 평균 시장 | **평균 초과** |")
    say("|---|---|---|---|---|---|")
    for st, g in ok.groupby("strategy"):
        w = (g.ret > 0).mean()
        say(f"| {st} | {len(g)} | {w*100:.0f}% | {g.ret.mean()*100:+.2f}% | "
            f"{g.mkt.mean()*100:+.2f}% | **{g.exc.mean()*100:+.2f}%** |")
    say()

    # ── ⑤ 청산 사유별 ────────────────────────────────────────────────────────
    def cat(r):
        r = r or ""
        for k, v in (("손절", "손절"), ("목표 익절", "익절"), ("보유기간", "보유기간"),
                     ("트레일", "트레일링"), ("추적", "트레일링")):
            if r.startswith(k) or k in r:
                return v
        return "기타"
    ok2 = ok.assign(cat=ok.reason.map(cat))
    say("## ⑤ 청산 사유별 기여\n")
    say("| 사유 | 건수 | 비중 | 평균 실현 | 총 기여(건수×평균) |")
    say("|---|---|---|---|---|")
    for c, g in ok2.groupby("cat"):
        say(f"| {c} | {len(g)} | {len(g)/len(ok2)*100:.0f}% | {g.ret.mean()*100:+.2f}% | "
            f"**{len(g)*g.ret.mean()*100:+.1f}%p** |")
    say()

    # ── 🏁 ───────────────────────────────────────────────────────────────────
    say("## 🏁 읽는 법과 한계\n")
    say("- 🔴 **미청산 보유분이 표본 밖이다.** 아직 안 판 포지션(평가손익)이 빠져 있어 "
        "***이 표는 「실현된 것」만의 그림***이다. 오래 버티는 손실 포지션이 있으면 실제는 더 나쁘다.")
    say("- 🔴 **한 국면이다**(2026-06~08). 일반화 금지.")
    say("- 🔴 **시장 성분은 「소속 지수 × 보유기간」 근사**다. 베타 1 을 가정한 것이고 "
        "실제 종목 베타는 다르다 ⇒ 초과 성분에 베타 오차가 섞인다.")
    say("- ⚠️ **이건 기술 통계다.** 「선택이 무작위보다 나쁘다」는 주장을 하려면 **귀무가 필요**하고, "
        "그건 2단계에서 **사전등록 후** 잰다. 이 표만으로 그 주장을 하지 말 것.")

    (BASE / "RESULTS.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

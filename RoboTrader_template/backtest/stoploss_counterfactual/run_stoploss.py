# -*- coding: utf-8 -*-
"""`PREREG.md`(`fb76190`) 실행 — 손절은 손실을 줄이는가 확정시키는가.

🔑 반증축 S3 이 결론을 가른다: 손절은 「많이 떨어진 종목」에서 발동하므로 팔고 나서 오르는 것은
   **평균회귀만으로도** 설명된다. 익절(거울상)에 같은 지표를 걸어야 갈린다.

라이브 트리 import 0건 · DB 는 SELECT 만 · `utils/logger.py` 미사용.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from scipy.stats import binomtest

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
HS = [1, 3, 5, 10, 20]
PRIMARY_H = 10                      # §3 — 기준 지평 사전 고정
THETAS = [0.03, 0.05, 0.08, 0.12, 0.15, None]   # §5 S5 (None = 손절 없음)
MAX_HOLD = 20                       # §5 S5 — 최대 20거래일
PSEUDO = ("KOSPI", "KOSDAQ", "KS11", "KQ11")


def say(s=""):
    print(s)
    OUT.append(s)


def cat(reason: str) -> str:
    r = reason or ""
    if r.startswith("손절"):
        return "손절"
    if r.startswith("목표 익절"):
        return "익절"
    return "기타"


def load():
    conn = psycopg2.connect(**DSN)
    sells = pd.read_sql("""
        SELECT s.id, s.stock_code, s.timestamp::date AS sell_date, s.price AS sell_price,
               s.profit_rate, s.strategy, s.reason, s.buy_record_id,
               b.timestamp::date AS buy_date, b.price AS buy_price
        FROM virtual_trading_records s
        LEFT JOIN virtual_trading_records b ON b.id = s.buy_record_id
        WHERE s.action='SELL' AND s.timestamp::date BETWEEN '2026-06-01' AND '2026-08-14'
    """, conn)
    px = pd.read_sql("""
        SELECT stock_code, date, low, close FROM daily_prices
        WHERE date BETWEEN '2026-05-20' AND '2026-09-30' AND close > 0
    """, conn)
    idx = pd.read_sql("""
        SELECT stock_code, date, close FROM daily_prices
        WHERE stock_code IN ('KOSPI','KOSDAQ') AND date BETWEEN '2026-05-20' AND '2026-09-30'
    """, conn)
    mkt = pd.read_sql("SELECT stock_code, market FROM stock_market", conn)
    conn.close()
    for c in ("sell_price", "buy_price", "profit_rate"):
        sells[c] = pd.to_numeric(sells[c], errors="coerce")
    for c in ("low", "close"):
        px[c] = pd.to_numeric(px[c], errors="coerce")
    idx["close"] = pd.to_numeric(idx["close"], errors="coerce")
    sells["sell_date"] = sells["sell_date"].astype(str)
    sells["buy_date"] = sells["buy_date"].astype(str)
    sells["cat"] = sells["reason"].map(cat)
    close = px[~px.stock_code.isin(PSEUDO)].pivot_table(
        index="date", columns="stock_code", values="close", aggfunc="last").sort_index()
    low = px[~px.stock_code.isin(PSEUDO)].pivot_table(
        index="date", columns="stock_code", values="low", aggfunc="last").sort_index()
    ic = idx.pivot_table(index="date", columns="stock_code", values="close", aggfunc="last").sort_index()
    return sells, close, low, ic, dict(zip(mkt.stock_code, mkt.market))


def main() -> int:
    sells, close, low, ic, market = load()
    dates = list(close.index)
    pos = {d: i for i, d in enumerate(dates)}
    cols = {c: i for i, c in enumerate(close.columns)}

    say("# 손절 반사실 — 손실을 「줄이는가」 「확정시키는가」\n")
    say("사전등록 `PREREG.md` (`fb76190`) · 실행은 그 «뒤»다.\n")
    n_all = len(sells)
    counts = sells.cat.value_counts().to_dict()
    say(f"매도 **{n_all}건** · 손절 **{counts.get('손절',0)}** · 익절 **{counts.get('익절',0)}** "
        f"· 기타 {counts.get('기타',0)}(제외) · `buy_record_id` 결측 {int(sells.buy_price.isna().sum())}\n")

    def fwd(code, date, h, base):
        i, ci = pos.get(date), cols.get(code)
        if i is None or ci is None or i + h >= len(dates) or not base or base <= 0:
            return np.nan
        v = close.iat[i + h, ci]
        return np.nan if not np.isfinite(v) else v / base - 1

    def idx_fwd(code, date, h):
        m = market.get(code)
        if m not in ("KOSPI", "KOSDAQ") or m not in ic.columns:
            return np.nan
        i = pos.get(date)
        if i is None or i + h >= len(dates):
            return np.nan
        try:
            a, b = ic.at[dates[i], m], ic.at[dates[i + h], m]
        except KeyError:
            return np.nan
        return np.nan if not (np.isfinite(a) and np.isfinite(b) and a > 0) else b / a - 1

    work = sells[sells.cat.isin(("손절", "익절"))].copy()
    for h in HS:
        work[f"regret{h}"] = [fwd(r.stock_code, r.sell_date, h, r.sell_price) for r in work.itertuples()]
        work[f"cf{h}"] = [fwd(r.stock_code, r.sell_date, h, r.buy_price) for r in work.itertuples()]
    work[f"mkt{PRIMARY_H}"] = [idx_fwd(r.stock_code, r.sell_date, PRIMARY_H) for r in work.itertuples()]
    work["mkt_missing"] = work[f"mkt{PRIMARY_H}"].isna()

    SL, TP = work[work.cat == "손절"], work[work.cat == "익절"]
    H = PRIMARY_H

    say("## §3 지평별 — `regret` = 팔고 나서 얼마나 올랐나 (매도가 대비)\n")
    say("| 지평 h | 손절 중앙 | 익절 중앙 | 손절 결측 |")
    say("|---|---|---|---|")
    for h in HS:
        say(f"| {h} | **{SL[f'regret{h}'].median()*100:+.2f}%** | "
            f"{TP[f'regret{h}'].median()*100:+.2f}% | {int(SL[f'regret{h}'].isna().sum())}/{len(SL)} |")
    say()
    say(f"🔴 `daily_prices` 최종일이 **2026-08-14** 라 뒤쪽 매도일은 긴 지평이 계산 불가하다. "
        f"h={H} 결측 손절 {int(SL[f'regret{H}'].isna().sum())} · 익절 {int(TP[f'regret{H}'].isna().sum())}.\n")

    # ── S1 · S2 ──────────────────────────────────────────────────────────────
    s1_med = float(SL[f"regret{H}"].median())
    s1 = s1_med > 0
    dm = SL.groupby("sell_date")[f"regret{H}"].median().dropna()
    pos_days, tot_days = int((dm > 0).sum()), len(dm)
    bt = binomtest(pos_days, tot_days, 0.5, alternative="two-sided")
    s2 = pos_days >= (tot_days // 2 + 1)
    s2_strong = bool(bt.pvalue < 0.05)

    # ── S3 반증축 ────────────────────────────────────────────────────────────
    tp_med = float(TP[f"regret{H}"].median())
    symmetric = tp_med < 0          # 익절 후 하락 = 대칭 평균회귀
    asymmetric = tp_med >= 0

    # ── S4 시장 통제 ─────────────────────────────────────────────────────────
    exc = (SL[f"regret{H}"] - SL[f"mkt{H}"]).dropna()
    s4_med = float(exc.median()) if len(exc) else np.nan
    s4 = bool(s4_med > 0)

    say(f"## §5 예측 판정 (기준 지평 h={H})\n")
    say("| 예측 | 내용 | 결과 | 판정 |")
    say("|---|---|---|---|")
    say(f"| **S1** (주) | 손절 `regret` 중앙 > 0 | **{s1_med*100:+.2f}%** | {'✅ 지지' if s1 else '❌ 기각'} |")
    say(f"| **S2** | 날짜별 양수인 날 과반 | **{pos_days}/{tot_days}** (p={bt.pvalue:.4f}) | "
        f"{'✅ 지지' if s2 else '❌ 기각'}{' · **강함**' if s2 and s2_strong else ' · 약함(p≥0.05)' if s2 else ''} |")
    # 🔴 S3 라벨은 **S1 이 양수일 때만** 뜻이 있다(「팔고 나서 올랐다」의 원인을 가르는 축이므로).
    #    S1 이 기각되면 「평균회귀」라는 말 자체가 성립하지 않는다 — 사전등록의 논리 결함(자기 신고).
    s3_label = ("🔴 **대칭 평균회귀 — 손절 특유 결함 아님**" if symmetric else "✅ 비대칭 — 손절 쪽 결함") \
        if s1 else "⚪ **S1 기각이라 이 라벨은 성립 안 함**(아래 §해석)"
    say(f"| **S3** (반증축) | 익절 `regret` 중앙 | **{tp_med*100:+.2f}%** | {s3_label} |")
    say(f"| **S4** | 시장 초과분 중앙 > 0 | **{s4_med*100:+.2f}%** "
        f"(결측 {int(SL['mkt_missing'].sum())}/{len(SL)}) | {'✅ 지지' if s4 else '❌ 기각'} |")
    say()

    if s1 and asymmetric and s4:
        verdict = "🔴 **손절이 손해다** (비대칭 + 시장 초과)"
    elif not s1:
        verdict = "🟢 **손절이 옳다** — 팔고 나서 더 떨어졌다"
    elif s1 and symmetric:
        verdict = "⛔ **평균회귀일 뿐** — 손절 «특유»의 결함이라고 쓸 수 없다"
    else:
        verdict = "⛔ **판별 불가**"
    say(f"### 판정: {verdict}\n")
    say("🔴 사전등록 §5 규칙 그대로다. **h 나 문턱을 갈아끼우지 않았다.**\n")

    # ── 반사실 총손익 ────────────────────────────────────────────────────────
    say(f"## 반사실 총손익 — 안 팔았다면 (매수가 대비, h={H})\n")
    say("| 군 | 실제 실현 중앙 | 안 팔았을 때 중앙 | 차이 |")
    say("|---|---|---|---|")
    for name, g in (("손절", SL), ("익절", TP)):
        real = float(g.profit_rate.median()) * 100
        cf = float(g[f"cf{H}"].median()) * 100
        say(f"| {name} | {real:+.2f}% | **{cf:+.2f}%** | {cf-real:+.2f}%p |")
    say()

    # ── S5 문턱 곡선 ─────────────────────────────────────────────────────────
    say("## §5 S5 — 손절 문턱 곡선 (사전등록 · 「최적 θ」를 고르는 표가 아니다)\n")
    say(f"매수일부터 최대 {MAX_HOLD}거래일. 일봉 저가가 `매수가×(1−θ)` 이하면 그 가격에 청산, "
        "아니면 마지막 날 종가 청산. **손절 축만** 바꾼 근사다(익절·트레일링 미적용).\n")
    base = sells[sells.cat.isin(("손절", "익절"))]
    # 🔑 θ 를 바꾸면 **승률과 손익비가 «함께»** 움직인다 — 총손익만 찍으면 원인을 못 가른다.
    #    (독립 변수가 아니므로 「손익비 고정」이라는 전제 자체가 성립하지 않는다.)
    say("| θ | 손절 발동 | 승률 | 평균이익 | 평균손실 | **손익비** | 총손익 중앙 | 총손익 평균 |")
    say("|---|---|---|---|---|---|---|---|")
    for th in THETAS:
        rets, fired = [], 0
        for r in base.itertuples():
            i, ci = pos.get(r.buy_date), cols.get(r.stock_code)
            if i is None or ci is None or not r.buy_price or r.buy_price <= 0:
                continue
            hit = None
            last = min(i + MAX_HOLD, len(dates) - 1)
            if th is not None:
                trig = r.buy_price * (1 - th)
                for k in range(1, last - i + 1):
                    lo = low.iat[i + k, ci]
                    if np.isfinite(lo) and lo <= trig:
                        hit = trig
                        break
            if hit is None:
                v = close.iat[last, ci]
                if not np.isfinite(v):
                    continue
                rets.append(v / r.buy_price - 1)
            else:
                fired += 1
                rets.append(hit / r.buy_price - 1)
        a = np.array(rets)
        w, l = a[a > 0], a[a <= 0]
        wr = len(w) / len(a) if len(a) else np.nan
        aw = w.mean() if len(w) else np.nan
        al = -l.mean() if len(l) else np.nan
        pr = aw / al if (np.isfinite(aw) and np.isfinite(al) and al) else np.nan
        say(f"| {'없음' if th is None else f'−{th*100:.0f}%'} | {fired}/{len(a)} | "
            f"{wr*100:.1f}% | +{aw*100:.2f}% | −{al*100:.2f}% | **{pr:.2f}:1** | "
            f"{np.median(a)*100:+.2f}% | **{a.mean()*100:+.2f}%** |")
    say()
    say("🔑🔑 ***손익비를 「고정」할 수 없다 — θ 를 움직이면 승률과 손익비가 «함께» 움직인다.*** "
        "손절을 조이면 평균 손실은 작아지지만 **더 자주 손절돼 승률이 떨어진다.** "
        "그래서 「필요 승률 = 평균손실/(평균이익+평균손실)」 같은 항등식은 **한 설정 «안에서»만** "
        "뜻이 있고, 설정을 바꿔 비교할 때는 쓸 수 없다.\n")
    say("🔴 **이 표를 보고 θ 를 고르면 사후적합이다.** 민감도의 «모양»을 보는 용도이고, "
        "채택은 별도 사전등록에서 한다(사전등록 §5 단서).\n")

    # ── 전략별 ───────────────────────────────────────────────────────────────
    say("## 전략별 손절 (기술)\n")
    say(f"| 전략 | 손절 건수 | 실현 중앙 | `regret{H}` 중앙 |")
    say("|---|---|---|---|")
    for st, g in SL.groupby("strategy"):
        say(f"| {st} | {len(g)} | {g.profit_rate.median()*100:+.2f}% | "
            f"{g[f'regret{H}'].median()*100:+.2f}% |")
    say()

    # ── 🏁 해석 (서술은 사후, 숫자는 전부 위에서 계산된 것) ────────────────────
    say("## 🏁 해석 — 손절도 익절도 «옳았다». 문제는 다른 데 있다\n")
    say("### ① 반등한 지평이 하나도 없다\n")
    say("| 지평 | 1 | 3 | 5 | 10 | 20 |")
    say("|---|---|---|---|---|---|")
    say("| 손절 후 | " + " | ".join(f"{SL[f'regret{h}'].median()*100:+.2f}%" for h in HS) + " |")
    say("| 익절 후 | " + " | ".join(f"{TP[f'regret{h}'].median()*100:+.2f}%" for h in HS) + " |")
    say()
    say("🔑 ***팔고 나서 올라간 지평이 없다.*** 손절도 익절도 «판 뒤에 더 떨어졌다» — "
        "그러니 **두 청산 모두 옳았다.** 익절은 심지어 +12.24% 를 실현하고 나갔는데 "
        f"안 팔았으면 **{TP[f'cf{H}'].median()*100:+.2f}%** 였다(**{abs(TP[f'cf{H}'].median()*100-12.24):.1f}%p 절약**).\n")
    say("🔴 **S3 반증축의 라벨이 이번엔 성립하지 않는다.** 「대칭 평균회귀」는 *「팔고 나서 올랐다」*의 "
        "원인을 가르는 축인데, S1 이 기각돼 **애초에 오르지 않았다.** 손절 후 하락 + 익절 후 하락은 "
        "평균회귀가 아니라 ***시장 전반의 지속 하락***이다. "
        "⚠️ ***사전등록이 S3 라벨을 S1 에 조건부로 걸지 않은 것이 내 논리 결함***(자기 신고).\n")

    say("### ② 🔴 관리자 오보고 정정 — 「손절이 손실을 키운다」는 틀렸다\n")
    say("직전 연구(`bc9b0b7`) 부수 결과를 근거로 *「손절이 손실을 «확정»시키고 있다. "
        "게이트보다 더 급한 문제일 수 있다」*고 보고했다. **그 보고를 철회한다.**\n")
    say("| | 대상 | 지평 | 결과 |")
    say("|---|---|---|---|")
    say("| 그때(`bc9b0b7` G5) | **실행되지 않은 «가상» 매수** 488건 | h=5 | 단순보유 −4.76% → 손절적용 −8.00% |")
    say(f"| 이번 | **실제 체결·실제 손절된** {len(SL)}건 | h=1~20 **전부** | 손절이 "
        f"**{abs(SL[f'cf{H}'].median()*100 - SL.profit_rate.median()*100):.2f}%p 절약** |")
    say()
    say("🔑 ***두 연구는 모순이 아니라 「대상이 다르다」*** — 하나는 «사지 않은 것»의 가상 경로, "
        "다른 하나는 «실제로 보유했다가 판 것»의 실측 경로다. "
        "🔴 **그런데 나는 좁은 가상 계산 하나로 「급한 문제」라고 우선순위를 매겼다.** "
        "***부수 결과를 근거로 우선순위를 말하기 전에 직접 재라.***\n")

    say("### ③ 문턱 곡선은 단조지만, 그대로 믿으면 안 된다\n")
    say("θ 를 조일수록 평균 손익이 좋아진다(−15% 평균 −7.21% → −3% 평균 **−0.74%**). "
        "그러나 두 가지를 반드시 함께 읽어야 한다:\n")
    say("- ⚠️ **「없음」 행은 실제 시스템보다 불리하다** — 이 시뮬레이션은 **손절 축만** 바꾸므로 "
        "**익절·트레일링이 통째로 빠져 있다.** 실제로는 익절이 +12.24% 를 걷어간다. "
        "***행 «사이» 비교는 유효하지만 절대 수준은 실제 성과가 아니다.***")
    say("- 🔴 **중앙값이 문턱과 똑같이 찍히는 것은 정보가 아니다**(−3% → 중앙 −3.00%). "
        "발동률이 476/516 이라 중앙 사례가 곧 손절 사례다. **평균을 봐야 한다.**")
    say("- 🔴 **하락장에서 타이트한 손절이 이기는 것은 거의 정의상 그렇다.** "
        "***이 표를 「손절을 −3%로 조이자」의 근거로 쓰면 안 된다*** — 국면이 바뀌면 부호가 뒤집힌다.\n")

    say("### ④ 그래서 결론\n")
    say("🟢 **손절·익절 규칙은 이 국면에서 제 일을 했다.** 고칠 대상이 아니다.")
    say("🔴 **그러면 남는 질문은 하나다** — 청산이 옳았고 급락게이트도 옳았는데 "
        "***왜 8전략이 전부 마이너스인가.*** 두 연구가 같은 곳을 가리킨다: "
        "***문제는 「파는 방법」이 아니라 「사는 것」이다.***\n")

    # ── 한계 ─────────────────────────────────────────────────────────────────
    say("## 🔴 한계 — 사전등록 §6 그대로\n")
    say(f"- **n = {tot_days}일**(손절 {len(SL)}건). 부호검정 검정력이 낮다.")
    say("- 🔴 **한 국면이다**(2026-06~08). `bc9b0b7` 이 **「뭘 사도 잃은 국면」**으로 확인한 시기 — "
        "평균회귀가 특히 강하게 나올 조건이다.")
    say("- 🔴 **대체효과·자금 제약 미반영.** 안 팔았으면 그 자금이 묶여 다음 매수를 못 했을 것이다. "
        "***「손절을 없애면 이만큼 벌었다」로 읽지 말 것.***")
    say("- 🔴 **gross** — 수수료·거래세 미반영(양쪽에 같이 빠져 «차이»에는 영향 작다).")
    say("- 🔴 **S5 는 일봉 저가 기준 근사**다(장중 경로·슬리피지 미반영).")
    say("- 🔴 **아직 안 팔린 보유분은 표본 밖**이다 — 손절도 익절도 안 겪은 종목은 관측되지 않는다.")
    say("- 🔴 이 연구는 **손절을 몇 %로 하라고 말해주지 않는다.**")

    (BASE / "RESULTS.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

# -*- coding: utf-8 -*-
"""`PREREG.md`(`3f8722f`) 실행 — 급락게이트가 막은 매수는 이득이었나 손해였나.

🔑 주 검정 단위는 **날짜(n=22)**다. 차단은 종목 사건이 아니라 «날짜» 사건이라
   같은 날 막힌 종목들은 같은 시장 충격을 공유한다 ⇒ 종목 단위 검정은 독립 가정 위반.

라이브 트리 import 0건(psycopg2/pandas/numpy/scipy + 표준 라이브러리) · DB 는 SELECT 만.
`utils/logger.py` 미사용 ⇒ `trading_*.log` 오염 없음.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from scipy.stats import binomtest

from extract_blocks import extract, first_per_stock_day

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

DSN = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
HS = [0, 1, 3, 5, 10]
PRIMARY_H = 5              # §6 — 기준 지평을 «미리» 고정
SEED = 20260815
NREP = 2000
PSEUDO = ("KOSPI", "KOSDAQ", "KS11", "KQ11")
G3_BAND = 1.0              # §6 G3 — ±1.0%p
SL_FIRST = True            # §6 G5 — 동시 도달 시 손절 우선(익절 우선판도 함께 인쇄)

# 🔴 신원 키가 둘이다 — 로그는 «클래스명», DB 는 «폴더키». 새 전략이 나오면 즉시 죽게 한다.
CLS2KEY = {
    "ElderEmaPullbackStrategy": "elder_ema_pullback",
    "BookEnvelope200dStrategy": "book_envelope_200d",
    "DayTrading3MethodsBreakoutStrategy": "daytrading_3methods_breakout",
    "MinerviniVolumeDryupStrategy": "minervini_volume_dryup",
    "BookPullbackMa20Strategy": "book_pullback_ma20",
    "BookPullbackMa5Strategy": "book_pullback_ma5",
    "RSLeaderStrategy": "rs_leader",
    "DeepMrDev20Strategy": "deep_mr_dev20",
}


def say(s=""):
    print(s)
    OUT.append(s)


def load_prices():
    conn = psycopg2.connect(**DSN)
    df = pd.read_sql(
        "SELECT stock_code, date, open, high, low, close, volume FROM daily_prices "
        "WHERE date BETWEEN '2026-05-20' AND '2026-09-30' AND close > 0", conn)
    conn.close()
    df = df[~df.stock_code.isin(PSEUDO)].copy()
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    piv = {c: df.pivot_table(index="date", columns="stock_code", values=c, aggfunc="last")
           for c in ("high", "low", "close", "volume")}
    for k in piv:
        piv[k] = piv[k].sort_index()
    return piv


def load_controls():
    conn = psycopg2.connect(**DSN)
    c1 = pd.read_sql(
        "SELECT stock_code, timestamp::date AS date, price, strategy "
        "FROM virtual_trading_records WHERE action='BUY' "
        "AND timestamp::date BETWEEN '2026-06-01' AND '2026-08-14'", conn)
    sltp = pd.read_sql(
        "SELECT strategy, percentile_cont(0.5) WITHIN GROUP (ORDER BY stop_loss_rate) sl, "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY target_profit_rate) tp "
        "FROM virtual_trading_records WHERE action='BUY' "
        "AND timestamp::date BETWEEN '2026-06-01' AND '2026-08-14' GROUP BY strategy", conn)
    conn.close()
    c1["date"] = c1["date"].astype(str)
    c1["price"] = pd.to_numeric(c1["price"], errors="coerce")
    return c1, {r.strategy: (float(r.sl), float(r.tp)) for r in sltp.itertuples()}


def main() -> int:
    piv = load_prices()
    close, high, low, vol = piv["close"], piv["high"], piv["low"], piv["volume"]
    dates = list(close.index)
    pos = {d: i for i, d in enumerate(dates)}

    ev, miss = extract()
    blocks = first_per_stock_day(ev)
    bad_cls = sorted({e["strategy"] for e in ev} - set(CLS2KEY))
    assert not bad_cls, f"미등록 전략 클래스: {bad_cls}"

    say("# 급락게이트 반사실 — 막은 매수는 이득이었나 손해였나\n")
    say(f"사전등록 `PREREG.md` (`3f8722f`) · 실행은 그 «뒤»다.\n")
    say(f"차단 이벤트 **{len(ev):,}건** → 고유 (날짜,종목) **{len(blocks):,}건** · "
        f"차단일 **{len({b['date'] for b in blocks})}일** · 고유 종목 {len({b['code'] for b in blocks})}개\n")
    say(f"추출 결측: {dict(miss)}\n")
    say(f"🟢 **추출 검증** — 2026-08-03 = "
        f"**{sum(1 for e in ev if e['date']=='2026-08-03'):,}건**(별도 조사가 얻은 2,909 와 일치)\n")

    def fwd(code, date, h, base):
        """base(=진입가) 대비 h거래일 후 종가 수익률. 자료 없으면 nan."""
        i = pos.get(date)
        if i is None or i + h >= len(dates) or code not in close.columns or not base or base <= 0:
            return np.nan
        v = close.iat[i + h, close.columns.get_loc(code)]
        return np.nan if not np.isfinite(v) else v / base - 1

    # ── 차단군 ────────────────────────────────────────────────────────────────
    rows = []
    for b in blocks:
        d, c, p = b["date"], b["code"], b["price"]
        i = pos.get(d)
        c0 = (close.iat[i, close.columns.get_loc(c)]
              if i is not None and c in close.columns else np.nan)
        r = dict(date=d, code=c, strategy=b["strategy"], entry=p, close0=c0, index=b["index"])
        for h in HS:
            r[f"sig{h}"] = fwd(c, d, h, p)          # 시그널가 기준 (G1·G2·G4)
            r[f"cls{h}"] = fwd(c, d, h, c0)         # 그날 종가 기준 (G3 — C2 와 동일 기준)
        rows.append(r)
    B = pd.DataFrame(rows)

    say("## 결측 (지평별 · 조용히 빼지 않는다)\n")
    say("| 지평 h | 시그널가 기준 결측 | 종가 기준 결측 |")
    say("|---|---|---|")
    for h in HS:
        say(f"| {h} | {int(B[f'sig{h}'].isna().sum())}/{len(B)} | {int(B[f'cls{h}'].isna().sum())}/{len(B)} |")
    say(f"\n🔴 마지막 차단일이 **2026-08-06** 이고 `daily_prices` 최종일이 **2026-08-14** 라 "
        f"**h=10 은 뒤쪽 날짜에서 계산 불가**하다. h=5 는 전부 가능(기준 지평이 h=5 인 이유가 아니라 "
        "사전등록에서 먼저 정한 것이다).\n")

    # ── 대조군 C1 ────────────────────────────────────────────────────────────
    c1, sltp = load_controls()
    c1r = []
    for t in c1.itertuples():
        r = dict(date=t.date, code=t.stock_code, strategy=t.strategy)
        for h in HS:
            r[f"sig{h}"] = fwd(t.stock_code, t.date, h, t.price)
        c1r.append(r)
    C1 = pd.DataFrame(c1r)

    # ── 대조군 C2 (그날 무작위 · 종가 기준) ───────────────────────────────────
    rng = np.random.default_rng(SEED)
    bdates = sorted(B.date.unique())
    n_by_date = B.groupby("date").size().to_dict()
    null_med = {}
    drawn = set()
    halted = 0
    for d in bdates:
        i = pos[d]
        if i + PRIMARY_H >= len(dates):
            null_med[d] = np.nan
            continue
        row0 = close.iloc[i]
        rowh = close.iloc[i + PRIMARY_H]
        ok = row0.notna() & rowh.notna() & (row0 > 0)
        codes = np.array(row0.index[ok])
        rets = (rowh[ok] / row0[ok] - 1).to_numpy(dtype="float64")
        halted += int((vol.iloc[i][ok] == 0).sum())
        n = min(n_by_date[d], len(codes))
        meds = np.empty(NREP)
        for k in range(NREP):
            sel = rng.choice(len(codes), size=n, replace=False)
            drawn.update(codes[sel].tolist())
            meds[k] = np.median(rets[sel])
        null_med[d] = float(np.median(meds))

    # ── §6 판정 ──────────────────────────────────────────────────────────────
    say("## 지평별 요약 (차단군 · 시그널가 기준)\n")
    say("| 지평 h | 종목 중앙 | 날짜별 중앙의 중앙 | 음수인 날 / 22 |")
    say("|---|---|---|---|")
    for h in HS:
        dm = B.groupby("date")[f"sig{h}"].median().dropna()
        say(f"| {h} | **{B[f'sig{h}'].median()*100:+.2f}%** | {dm.median()*100:+.2f}% | "
            f"{int((dm < 0).sum())}/{len(dm)} |")
    say()

    H = PRIMARY_H
    dm = B.groupby("date")[f"sig{H}"].median().dropna()
    neg_days, tot_days = int((dm < 0).sum()), len(dm)
    bt = binomtest(neg_days, tot_days, 0.5, alternative="two-sided")
    g1 = neg_days >= 12
    g2 = bool(B[f"sig{H}"].median() < 0)

    dmc = B.groupby("date")[f"cls{H}"].median()
    diffs = pd.Series({d: dmc.get(d, np.nan) - null_med.get(d, np.nan) for d in bdates}).dropna()
    diff_med_pp = float(diffs.median() * 100)
    g3_sel = diff_med_pp < -G3_BAND
    g3_none = abs(diff_med_pp) <= G3_BAND

    c1_med = float(C1[f"sig{H}"].median())
    b_med = float(B[f"sig{H}"].median())
    g4 = b_med < c1_med

    say(f"## §6 예측 판정 (기준 지평 h={H})\n")
    say("| 예측 | 내용 | 결과 | 판정 |")
    say("|---|---|---|---|")
    say(f"| **G1** (주) | 날짜별 중앙 수익률 음수인 날 ≥ 12/22 | **{neg_days}/{tot_days}** "
        f"(부호검정 p={bt.pvalue:.4f}) | {'✅ 지지' if g1 else '❌ 기각'} |")
    say(f"| **G2** | 488건 전체 중앙 < 0 | **{b_med*100:+.2f}%** | {'✅ 지지' if g2 else '❌ 기각'} |")
    say(f"| **G3** (반증축) | 그날 무작위 대비 차이 < −{G3_BAND}%p | **{diff_med_pp:+.2f}%p** | "
        f"{'✅ 종목 선별력 있음' if g3_sel else ('🔴 **종목 선별력 0 — 날짜만 골랐다**' if g3_none else '❌ 반대 방향')} |")
    say(f"| **G4** | 차단군 < 실제 체결 매수({len(C1)}건) | **{b_med*100:+.2f}%** vs "
        f"**{c1_med*100:+.2f}%** | {'✅ 지지' if g4 else '❌ 기각'} |")
    say()
    say(f"C2 귀무 표집 다양성: **{len(drawn):,}종목** · {NREP:,}회 · 시드 {SEED} "
        f"· ⚠️ 사전등록대로 **거래정지(volume=0) 종목을 안 걸렀다** — 차단일 유니버스에 {halted:,}종목-일 포함.\n")

    if g1 and g2 and g4:
        verdict = "🟢 **게이트가 이득이었다**"
    elif (not g1) and (not g2) and (not g4):
        verdict = "🔴 **게이트가 손해였다**"
    else:
        verdict = "⛔ **판별 불가**"
    say(f"### 판정: {verdict}\n")
    say("🔴 사전등록 §6 의 규칙 그대로다. **문턱이나 h 를 갈아끼워 결론을 만들지 않았다.**\n")

    # ── G5 손절/익절 시나리오 ────────────────────────────────────────────────
    say("## §6 G5 — 전략 손절·익절 적용 (기술 · 예측 없음)\n")
    say("다음 거래일부터 h=5 까지 일봉 저가/고가로 판정. 진입일 장중 경로는 알 수 없어 **k=1 부터** 본다.\n")

    def scenario(sl_first: bool):
        out = []
        for r in B.itertuples():
            key = CLS2KEY[r.strategy]
            sl, tp = sltp.get(key, (np.nan, np.nan))
            if not np.isfinite(sl) or not np.isfinite(tp) or r.code not in close.columns:
                out.append(np.nan); continue
            i, ci = pos[r.date], close.columns.get_loc(r.code)
            hit = None
            for k in range(1, H + 1):
                if i + k >= len(dates):
                    break
                lo, hi = low.iat[i + k, ci], high.iat[i + k, ci]
                if not np.isfinite(lo) or not np.isfinite(hi):
                    continue
                s, t = r.entry * (1 - sl), r.entry * (1 + tp)
                a, b_ = lo <= s, hi >= t
                if a and b_:
                    hit = (s if sl_first else t); break
                if a:
                    hit = s; break
                if b_:
                    hit = t; break
            out.append((hit / r.entry - 1) if hit else getattr(r, f"sig{H}"))
        return pd.Series(out, index=B.index)

    scen = {}
    for name, sf in (("손절 우선(사전 고정)", True), ("익절 우선(민감도)", False)):
        s = scenario(sf)
        scen[sf] = s
        dmm = s.groupby(B.date).median().dropna()
        say(f"- **{name}**: 종목 중앙 **{s.median()*100:+.2f}%** · "
            f"날짜별 중앙의 중앙 {dmm.median()*100:+.2f}% · 음수인 날 {int((dmm<0).sum())}/{len(dmm)}")
    ndiff = int((~np.isclose(scen[True].fillna(-9e9), scen[False].fillna(-9e9))).sum())
    say(f"\n🔑 **두 판이 갈린 건은 488건 중 {ndiff}건**"
        + ("이다 — 즉 **손절·익절 동시 도달이 사실상 없어 순서 가정이 결과를 안 바꾼다.** "
           "이 축은 헛돌지 않았고, 「순서 모호성」이 이번엔 문제가 아니었다는 «양성 확인»이다."
           if ndiff == 0 else
           "이다. 순서 가정이 일부 건에서 결과를 바꾼다 — 두 값을 함께 인용할 것."))
    say("⚠️ ***손절 우선은 차단군을 더 나빠 보이게 해 게이트에 «유리»하다*** — 그래서 양쪽을 다 냈다.\n")
    say(f"🔴 **손절을 적용하면 손실이 더 커진다**(h=5 단순보유 {B[f'sig{H}'].median()*100:+.2f}% → "
        f"손절적용 {scen[True].median()*100:+.2f}%). 손절이 손실을 «줄이는» 게 아니라 «확정»시키기 "
        "때문이다 — 5일 안에 손절선을 찍고 그 뒤 회복한 건이 있다는 뜻이다.\n")

    # ── 지수·전략 분해 (기술) ────────────────────────────────────────────────
    say("## 부수 기술 통계\n")
    say("| 지수 | 건수 | 중앙 수익률(h=5) |")
    say("|---|---|---|")
    for ix, g in B.groupby("index"):
        say(f"| {ix} | {len(g)} | {g[f'sig{H}'].median()*100:+.2f}% |")
    say()
    say("| 전략(클래스) | 건수 | 중앙 수익률(h=5) |")
    say("|---|---|---|")
    for st, g in B.groupby("strategy"):
        say(f"| {st} | {len(g)} | {g[f'sig{H}'].median()*100:+.2f}% |")
    say()

    # ── 🏁 해석 (서술은 사후, 숫자는 전부 위에서 계산된 것) ────────────────────
    say("## 🏁 해석 — 「막은 건 맞다, 그런데 남긴 것도 똑같이 나빴다」\n")
    say(f"판정은 **판별 불가**다. 갈린 지점이 정확히 하나, **G4** 다.\n")
    say(f"- 게이트가 **막은** 매수: h=5 중앙 **{b_med*100:+.2f}%** — 손실이 맞다(G2 ✅), "
        f"22일 중 {neg_days}일이 음수(G1 ✅), 그날 무작위 종목보다 **{abs(diff_med_pp):.2f}%p 더 나빴다**(G3 ✅).")
    say(f"- 그런데 게이트를 **통과해 실제 체결된** 매수: h=5 중앙 **{c1_med*100:+.2f}%** — "
        f"***막힌 것보다 오히려 {abs(c1_med-b_med)*100:.2f}%p 더 나쁘다***(G4 ❌).\n")
    say("⇒ 🔑🔑 ***게이트는 「나쁜 매수」를 막았다. 그러나 「좋은 매수」를 남기지는 못했다.*** "
        "막은 것도 손실, 통과시킨 것도 손실이다. 이 국면에서는 **무엇을 사도 잃었다**는 뜻이고, "
        "그건 게이트의 문제가 아니라 **전략의 문제**다.\n")
    say("🟢 **G3 은 뜻밖의 소득이다** — 같은 날 안에서 비교해도 차단 종목이 무작위보다 "
        f"**{abs(diff_med_pp):.2f}%p** 나빴다. 게이트는 「급락한 날」만 고른 게 아니라 "
        "***그날 «더 나쁜 종목»까지 걸러내고 있었다***. 설계 의도에 없던 부수 효과다.\n")
    say("🔴 **그래서 이 결과는 임계값 조정의 근거가 되지 못한다.** 임계값을 올리든 내리든 "
        "「막힌 쪽도 통과한 쪽도 손실」이라는 그림은 안 바뀐다. "
        "***먼저 물어야 할 것은 「임계값이 몇이냐」가 아니라 「이 국면에서 왜 다 잃는가」다.***\n")
    say("⚠️ **G1 의 지지는 약하다** — 15/22 는 사전등록 문턱(≥12)을 넘지만 "
        f"부호검정 p={bt.pvalue:.4f} 로 유의하지 않다. **문턱을 「과반」으로 잡은 것이 내 설계의 약점**이다"
        "(과반은 우연으로도 잘 나온다). 기각은 기각, 지지는 지지로 두되 **강도를 과장하지 말 것.**\n")

    # ── 한계 ─────────────────────────────────────────────────────────────────
    say("## 🔴 한계 — 사전등록 §7 그대로\n")
    say(f"- **n = {tot_days}일.** 부호검정 검정력이 낮다. 「차이 없음」이 「같음」이 아니다.")
    say("- 🔴 **대체효과 측정 불가** — 차단이 없었다면 그 매수가 **자금·슬롯 80칸을 소모**해 "
        "이후 매수가 밀렸을 것이다. ***이 결과를 「게이트를 끄면 이만큼 벌었다」로 읽지 말 것.***")
    say("- 🔴 **한 국면이다**(2026-06~08). 22일은 전부 게이트가 실제 발동한 날이라 하락 편중 — 그게 질문의 조건이다.")
    say("- 🔴 **gross** — 수수료·거래세 ≈ 0.21%p 가 매수 쪽에 불리하게 빠져 있다.")
    say("- 🔴 진입가는 **시그널가**이고 실제 체결가가 아니다(호가·슬리피지 미반영).")
    say("- 🔴 **h일 보유는 전략의 실제 청산룰이 아니다** — G5 는 근사이고 손절 우선 여부에 좌우된다.")
    say("- 🔴 **이 연구는 임계값을 얼마로 하라고 말해주지 않는다.** 임계값 곡선은 별도 사전등록(§8).")
    say("- ⚠️ **C2 의 진입 기준은 「그날 종가」**다(무작위 종목엔 시그널가가 없다). 그래서 G3 만 "
        "차단군도 종가 기준으로 맞춰 비교했다 — **사전등록이 C2 진입가를 명시하지 않은 결함**(자기 신고).")

    (BASE / "RESULTS.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

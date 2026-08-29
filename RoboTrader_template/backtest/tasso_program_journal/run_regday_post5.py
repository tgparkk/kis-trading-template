# -*- coding: utf-8 -*-
"""PREREG_REGDAY_MEASURE.md **첫 실행** — 등록일 측정자 M1~M5 + `PREREG_Q1_V2.md` §3 R2.

대상 = 5번째 글의 **코드 있는 신규 6건**(레메디 제외). 4번째 글 6건은 **같은 스냅샷에서 재계산**해
나란히 인쇄한다(post4 판정을 대체하지 않는다). 누적 12건도 참고로 낸다.

동결 문언 준수 사항:
  · M1  창 `[D−19, D]` = **D 를 포함한 직전 20거래일** · 문턱 **≥ 5/6** · 귀무 **시드 고정 20,000 반복**
        귀무는 §2 문언 *「창이 뽑은 날에 함께 이동하므로 교환가능하다」* 대로 **이동창**을 주(主)로 쓰고,
        **고정창** 변량을 민감도로 함께 인쇄한다.
  · M2  `r = C/H − 1` · 상한가형 `r ≥ −1%` · 되밀림형 `r ≤ −5%` · 중간 그 외
  · M3  되밀림형의 `(C−L)/(H−L)` 중앙값 < 0.5 (아니면 **M2 지지 취소**)
  · M4  등록일 유니버스에서 `high ≥ 전일종가 × 1.15` 인 종목 수 `n_up` + 그 집합 안 `거래대금/시총` 순위
  · M5  되밀림형 `r` 분포(중앙·최소·최대) — **기록만**

라이브 트리 import 0건. DB 는 SELECT 만.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

DB_UPTO = "2026-08-28"
WIN = 20                     # [D−19, D] = D 포함 20거래일
NREP = 20_000                # 사전등록 §4-1: 시드 고정 20,000 반복
NULL_SEED = 20260815
EPS = 1e-6
PSEUDO = ("KOSPI", "KOSDAQ", "KS11", "KQ11")
BAND_UP = 0.03               # 라이브 entry_band_up_pct (M5 병기용)

POST5 = [
    ("혜인",             "003010", "2026-08-11"),
    ("한국화장품제조",   "003350", "2026-08-12"),
    ("코데즈컴바인",     "047770", "2026-08-21"),
    ("한켐",             "457370", "2026-08-20"),
    ("삼양바이오팜",     "0120G0", "2026-08-21"),
    ("광전자",           "017900", "2026-08-05"),
]
POST4 = [
    ("이노테크",         "469610", "2026-08-13"),
    ("한켐",             "457370", "2026-08-12"),
    ("금호건설",         "002990", "2026-08-12"),
    ("지투파워",         "388050", "2026-08-13"),
    ("PS일렉트로닉스",   "332570", "2026-08-13"),
    ("코데즈컴바인",     "047770", "2026-08-19"),
]


def say(s=""):
    print(s)
    OUT.append(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def load_prices(codes):
    conn = psycopg2.connect(**DSN)
    q = ("SELECT stock_code, date, open, high, low, close, trading_value, market_cap "
         "FROM daily_prices WHERE stock_code = ANY(%s) AND date BETWEEN '2026-01-01' "
         f"AND '{DB_UPTO}' AND close > 0 ORDER BY stock_code, date")
    df = pd.read_sql(q, conn, params=(list(codes),))
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


def universe_raw_count(cur, d):
    """그날 `market_cap>0` 인 종목 수 (prev_close 필터 «전»). N7 계측용."""
    cur.execute(
        "SELECT count(*) FROM daily_prices WHERE date=%s AND close > 0 "
        "AND market_cap IS NOT NULL AND market_cap > 0 AND NOT (stock_code = ANY(%s))",
        (d, list(PSEUDO)))
    return int(cur.fetchone()[0])


def load_universe_day(cur, d):
    """등록일 유니버스 (그날 + 직전 거래일 종가). 의사티커 제외 · market_cap>0.

    🔑 `daily_prices.date` 는 **text** 컬럼이다(ISO 'YYYY-MM-DD') — 날짜 산술을 SQL 에서 하면
       `text >= timestamp` 로 죽는다. 하한을 파이썬에서 문자열로 만들어 넘긴다.
    """
    lo = (pd.Timestamp(d) - pd.Timedelta(days=20)).date().isoformat()
    cur.execute(
        "WITH u AS (SELECT stock_code, date, high, close, trading_value, market_cap, "
        "  LAG(close) OVER (PARTITION BY stock_code ORDER BY date) AS prev_close "
        "  FROM daily_prices WHERE date BETWEEN %s AND %s AND close > 0) "
        "SELECT stock_code, high, close, trading_value, market_cap, prev_close FROM u "
        "WHERE date = %s AND market_cap IS NOT NULL AND market_cap > 0 "
        "AND prev_close IS NOT NULL AND prev_close > 0 AND NOT (stock_code = ANY(%s))",
        (lo, d, d, list(PSEUDO)))
    return cur.fetchall()


def per_stock(df, code):
    m = df[df.stock_code == code].reset_index(drop=True)
    h = m.high.to_numpy(dtype=float)
    # is20h[i] = high[i] 가 «i 를 포함한 직전 20거래일» 최고 고가와 같다
    roll = pd.Series(h).rolling(WIN, min_periods=1).max().to_numpy()
    m = m.assign(is20h=(h >= roll - EPS))
    return m


def measure(df, items):
    """각 건의 등록일 측정자."""
    rows = []
    for nm, code, reg in items:
        m = per_stock(df, code)
        D = pd.Timestamp(reg)
        idx = m.index[m.date == D]
        if len(idx) == 0:
            rows.append(dict(name=nm, code=code, reg=reg, ok=False))
            continue
        i = int(idx[0])
        w0 = max(0, i - WIN + 1)
        win = m.iloc[w0:i + 1]
        o, h, l, c = (float(m.open[i]), float(m.high[i]),
                      float(m.low[i]), float(m.close[i]))
        prev_c = float(m.close[i - 1]) if i >= 1 else float("nan")
        rows.append(dict(
            name=nm, code=code, reg=reg, ok=True, i=i, nwin=len(win),
            high=h, low=l, close=c, open=o, prev_close=prev_c,
            win_max_high=float(win.high.max()),
            hit=bool(h >= float(win.high.max()) - EPS),
            r=c / h - 1.0,
            pos=(c - l) / (h - l) if h > l else float("nan"),
            ret_c=c / prev_c - 1.0 if prev_c == prev_c else float("nan"),
            ret_h=h / prev_c - 1.0 if prev_c == prev_c else float("nan"),
            win_is20h=win.is20h.to_numpy().copy(),
            win_high=win.high.to_numpy(dtype=float).copy(),
        ))
    return rows


def null_p(rows, rng, mode):
    """귀무: 각 건마다 창 안 무작위 날을 뽑아 같은 판정. mode='move'|'fixed'."""
    obs = np.mean([r["hit"] for r in rows])
    per = []
    for r in rows:
        if mode == "move":
            per.append(r["win_is20h"].astype(float))
        else:
            mx = r["win_high"].max()
            per.append((r["win_high"] >= mx - EPS).astype(float))
    ratios = np.zeros(NREP)
    for k in range(NREP):
        acc = 0.0
        for v in per:
            acc += v[rng.integers(len(v))]
        ratios[k] = acc / len(per)
    p = float((ratios >= obs - 1e-12).mean())
    return obs, p, ratios, [float(v.mean()) for v in per]


def fmt_pct(x):
    return "—" if x != x else f"{x:+.2%}"


def block(title, rows, tag):
    say(f"### {title}\n")
    say("| 종목 | 등록일 | 창봉수 | 등록일 고가 | 창 최고 고가 | **일치** | "
        "`r=C/H−1` | `(C−L)/(H−L)` | 종가 등락 | 고가 등락 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if not r["ok"]:
            say(f"| {r['name']} | {r['reg']} | — | — | — | (봉 없음) | — | — | — | — |")
            continue
        say(f"| {r['name']} | {r['reg']} | {r['nwin']} | {r['high']:,.0f} | "
            f"{r['win_max_high']:,.0f} | {'✅' if r['hit'] else '❌'} | "
            f"{r['r']:+.2%} | {r['pos']:.3f} | {fmt_pct(r['ret_c'])} | {fmt_pct(r['ret_h'])} |")
    hits = sum(1 for r in rows if r["ok"] and r["hit"])
    n = sum(1 for r in rows if r["ok"])
    say(f"\n⇒ **{tag} 일치 {hits}/{n} = {hits/n*100:.1f}%**\n")
    return hits, n


def main():
    codes = sorted({c for _n, c, _d in POST5 + POST4})
    df = load_prices(codes)

    say("# RESULTS_REGDAY_POST5_NUMBERS — 기계 생성 (수정 금지)\n")
    say("사전등록 `PREREG_REGDAY_MEASURE.md` §4 (8/22 동결) **첫 실행** + "
        "`PREREG_Q1_V2.md` §3 **R2** · 생성 `run_regday_post5.py`")
    say(f"DB `kis_template.daily_prices` 스냅샷 최신 **{df.date.max().date()}** "
        "(post4 실행 당시는 08-21 — **같은 표가 아니다**)")
    say(f"창 = `[D−19, D]` = **D 포함 직전 {WIN}거래일** · 귀무 반복 **{NREP:,}** · "
        f"시드 **{NULL_SEED}**\n")
    say("🔴 레메디(08-18 등록)는 DB 에 없다 ⇒ **분모에서 제외**. 분모 = **6건**.")
    say("🔴 한성기업·SK아이이테크놀로지는 등록일이 저자 서술로 특정되지 않았다 ⇒ "
        "사전등록 §4 문언대로 **제외**(추정 금지).")
    say("🟢 5번째 글에는 **등록일이 본문 안에서 모순되는 건이 없다** ⇒ 대안 날짜 계산 없음.\n")

    # ── R2 / M1 관측 ────────────────────────────────────────────────────────
    say("## 1. R2 · M1 — 등록일 **고가** == `[D−19, D]` 최고 고가\n")
    r5 = measure(df, POST5)
    r4 = measure(df, POST4)
    h5, n5 = block("1-1. 5번째 글 6건 (**판정 표본**)", r5, "5번째 글")
    h4, n4 = block("1-2. 4번째 글 6건 — 08-28 스냅샷 재계산 (참고)", r4, "4번째 글(재계산)")
    say(f"⇒ **누적 12건 = {h5 + h4}/{n5 + n4} = {(h5 + h4)/(n5 + n4)*100:.1f}%** (참고)\n")

    say("### 1-3. 판정\n")
    say("| 예측 | 출처 | 문언·문턱 | 관측 | 판정 |")
    say("|---|---|---|---|---|")
    obs5 = h5 / n5
    say(f"| **R2** | `PREREG_Q1_V2.md` §3 | 등록일 `exact` 건의 **≥ 50%** (비율 기록) | "
        f"**{h5}/{n5} = {obs5*100:.1f}%** | {'✅ 지지' if obs5 >= 0.50 else '❌ 불성립'} |")
    say(f"| **M1** | `PREREG_REGDAY_MEASURE.md` §4-1 | 비율 **≥ 5/6 = 83.3%** | "
        f"**{h5}/{n5} = {obs5*100:.1f}%** | {'✅ 문턱 충족' if obs5 >= 5/6 else '❌ 문턱 미달'} |")

    # ── M1 귀무 ─────────────────────────────────────────────────────────────
    say()
    say("## 2. M1 귀무 — 같은 종목 창 안 무작위 날 (시드 고정 20,000 반복)\n")
    for mode, label in (("move", "**이동창**(§2 문언 「창이 뽑은 날에 함께 이동」) — **주 판정**"),
                        ("fixed", "고정창(뽑은 날과 무관하게 `[D−19,D]` 최고) — 민감도")):
        rng = np.random.default_rng(NULL_SEED)
        obs, p, ratios, per = null_p([r for r in r5 if r["ok"]], rng, mode)
        say(f"### 2-{'1' if mode == 'move' else '2'}. {label}\n")
        say("| 종목 | 창봉수 | 그 창에서 「그날이 창 최고」인 날 비율 |")
        say("|---|---|---|")
        for r, v in zip([x for x in r5 if x["ok"]], per):
            say(f"| {r['name']} | {r['nwin']} | {v*100:.1f}% |")
        say()
        say(f"- 관측 비율 **{obs*100:.1f}%** · 귀무 평균 **{ratios.mean()*100:.1f}%** · "
            f"귀무 중앙 **{np.median(ratios)*100:.1f}%** · 귀무 최대 **{ratios.max()*100:.1f}%**")
        say(f"- **p = P(귀무 비율 ≥ 관측) = {p:.5f}** ({int(round(p*NREP)):,}/{NREP:,})")
        say(f"- 사전등록 §4-1 결정규칙 «귀무 백분위 < 5%» ⇒ "
            f"**{'✅ 지지' if p < 0.05 else '⛔ 불성립'}**\n")

    # ── M2 ─────────────────────────────────────────────────────────────────
    say("## 3. M2 — 이분성 (상한가형 `r ≥ −1%` · 되밀림형 `r ≤ −5%` · 중간 그 외)\n")

    def bucket(r):
        return "상한가형" if r >= -0.01 else ("되밀림형" if r <= -0.05 else "🔴 중간대")

    say("| 종목 | 등록일 | `r = C/H − 1` | 분류 | 🔴 중간대(−5% ~ −1%) 경계까지 여유 |")
    say("|---|---|---|---|---|")
    b5, margins = [], []
    for r in r5:
        if not r["ok"]:
            continue
        b = bucket(r["r"])
        b5.append(b)
        mg = (-0.05) - r["r"] if r["r"] <= -0.05 else (r["r"] - (-0.01))
        margins.append((r["name"], mg))
        say(f"| {r['name']} | {r['reg']} | **{r['r']:+.2%}** | {b} | **{mg*100:.2f}%p** |")
    n_ceil = b5.count("상한가형")
    n_pull = b5.count("되밀림형")
    n_mid = b5.count("🔴 중간대")
    say(f"\n⇒ 상한가형 **{n_ceil}** · 되밀림형 **{n_pull}** · 중간대 **{n_mid}**")
    m2_ok = (n_pull >= 1) and (n_mid == 0)
    say(f"⇒ 결정규칙 «되밀림형 ≥ 1 **그리고** 중간대 = 0» ⇒ "
        f"**{'✅ 지지' if m2_ok else '⛔ 불성립'}**")
    tight = min(margins, key=lambda x: x[1])
    say(f"🔴 **경계 근접도**: 가장 아슬아슬한 건은 **{tight[0]}** — 중간대 경계(−5%)까지 "
        f"**{tight[1]*100:.2f}%p** 뿐이다. ⇒ ***그만큼만 움직였어도 「중간대 0건」이 깨져 "
        "M2 는 «불성립»이 된다.***\n")
    say("### 3-1. 참고 — 4번째 글 6건 (같은 스냅샷 재계산)\n")
    say("| 종목 | 등록일 | `r` | 분류 |")
    say("|---|---|---|---|")
    b4 = []
    for r in r4:
        if not r["ok"]:
            continue
        b = bucket(r["r"])
        b4.append(b)
        say(f"| {r['name']} | {r['reg']} | {r['r']:+.2%} | {b} |")
    say(f"\n⇒ 4번째 글: 상한가형 {b4.count('상한가형')} · 되밀림형 {b4.count('되밀림형')} · "
        f"중간대 {b4.count('🔴 중간대')}")
    allb = b5 + b4
    say(f"⇒ **누적 12건**: 상한가형 {allb.count('상한가형')} · 되밀림형 {allb.count('되밀림형')} · "
        f"중간대 {allb.count('🔴 중간대')} (참고)\n")
    rs = sorted(r["r"] for r in r5 + r4 if r["ok"])
    say("### 3-2. 「빈 골짜기」 실측 — 누적 12건 `r` 오름차순\n")
    say("| 순 | `r` | 이웃 간격 |")
    say("|---|---|---|")
    for k, v in enumerate(rs):
        gap = "—" if k == 0 else f"{(v - rs[k-1])*100:.2f}%p"
        say(f"| {k+1} | {v:+.2%} | {gap} |")
    say()

    # ── M3 ─────────────────────────────────────────────────────────────────
    say("## 4. M3 (반증축) — 되밀림형의 종가 위치 `(C−L)/(H−L)` 중앙값 < 0.5\n")
    pull5 = [r for r in r5 if r["ok"] and bucket(r["r"]) == "되밀림형"]
    say("| 종목 | 고가 | 저가 | 종가 | `(C−L)/(H−L)` |")
    say("|---|---|---|---|---|")
    for r in pull5:
        say(f"| {r['name']} | {r['high']:,.0f} | {r['low']:,.0f} | {r['close']:,.0f} | "
            f"**{r['pos']:.3f}** |")
    pos5 = sorted(r["pos"] for r in pull5)
    med5 = float(np.median(pos5)) if pos5 else float("nan")
    say(f"\n⇒ 되밀림형 **{len(pull5)}건** · 중앙값 **{med5:.3f}** · "
        f"범위 [{min(pos5):.3f}, {max(pos5):.3f}]" if pos5 else "\n⇒ 되밀림형 0건")
    m3_ok = med5 < 0.5
    say(f"⇒ 결정규칙 «중앙값 < 0.5» ⇒ **{'✅ 통과' if m3_ok else '🔴 실패 ⇒ M2 지지 취소'}**")
    say(f"⇒ 0.5 이상인 건 **{sum(1 for p in pos5 if p >= 0.5)}/{len(pos5)}** "
        "(1회차 4번째 글 관측: 0.523·0.491·0.344, 중앙 0.491)\n")
    say(f"🔑 **M2·M3 종합 판정 = {'✅ M2 지지 유지' if (m2_ok and m3_ok) else '⛔ M2 지지 «취소» 또는 불성립'}**\n")

    # ── M4 ─────────────────────────────────────────────────────────────────
    say("## 5. M4 (대칭 단언) — 등록일 유니버스의 「고가 ≥ 전일종가 × 1.15」 종목 수\n")
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    say("| 종목 | 등록일 | `market_cap>0` | **검정 유니버스** | 🔴`prev_close` 없어 탈락 | "
        "**`n_up`** | 본인이 `n_up` 안에? | `n_up` 안 `거래대금/시총` 순위 | 백분위 |")
    say("|---|---|---|---|---|---|---|---|---|")
    nups, drops = [], []
    for r in r5:
        if not r["ok"]:
            continue
        raw_n = universe_raw_count(cur, r["reg"])
        rowsu = load_universe_day(cur, r["reg"])
        drop = raw_n - len(rowsu)
        drops.append((r["reg"], raw_n, len(rowsu), drop))
        up = [(sc, float(tv) / float(mc)) for sc, hi, cl, tv, mc, pc in rowsu
              if hi is not None and pc and float(hi) >= float(pc) * 1.15
              and tv is not None and mc]
        nup = len(up)
        nups.append(nup)
        up_sorted = sorted(up, key=lambda x: -x[1])
        inset = [k for k, (sc, _v) in enumerate(up_sorted) if sc == r["code"]]
        if inset:
            rk = inset[0] + 1
            pct = (nup - rk) / (nup - 1) * 100 if nup > 1 else 100.0
            rk_s, pct_s, in_s = f"**{rk} / {nup}**", f"{pct:.1f}", "✅"
        else:
            rk_s, pct_s, in_s = "—", "—", "🔴 **아니다**"
        say(f"| {r['name']} | {r['reg']} | {raw_n:,} | {len(rowsu):,} | "
            f"{'🔴 **' + format(drop, ',') + '**' if drop else '0'} | "
            f"**{nup}** | {in_s} | {rk_s} | {pct_s} |")
    say("")
    say("### 5-0. 🔴 `prev_close` 필터가 종목을 «조용히» 떨어뜨린다 (N7)")
    say("")
    say("`n_up` 은 `고가 ≥ 전일종가 × 1.15` 이므로 **직전 거래일 봉이 있어야** 판정된다. "
        "선행봉이 없는 종목은 「급등 아님」이 아니라 **검정에서 빠진다**.")
    say("")
    say("| 등록일 | `market_cap>0` | 검정 유니버스 | 탈락 | 탈락률 |")
    say("|---|---|---|---|---|")
    for _d, _raw, _kept, _drop in drops:
        say(f"| {_d} | {_raw:,} | {_kept:,} | "
            f"{'🔴 **' + format(_drop, ',') + '**' if _drop else '0'} | {_drop/_raw*100:.2f}% |")
    mx = max(drops, key=lambda x: x[3])
    say("")
    say(f"🔴🔴 **{mx[0]} 하루에만 {mx[3]}종목이 빠진다**({mx[1]:,} → {mx[2]:,}). "
        f"다른 등록일은 0~1종목이다. ⇒ ***광전자 08-05 의 `n_up` 은 {mx[2]:,}종목 기준이고, "
        "나머지 5건은 2,761~2,763종목 기준이다 — 분모가 같지 않다.***")
    say("🔑 이건 「그날 급등주가 적었다」가 아니라 **DB 선행봉 결손**이다.")
    conn.close()
    say(f"\n⇒ **`n_up` 중앙값 {int(np.median(nups))}** · 범위 [{min(nups)}, {max(nups)}]")
    say("⇒ 사전등록 §4-4: *「`n_up` 이 크면 M1 은 「저자가 급등주를 고른다」만 말하고 "
        "「어느 급등주냐」는 전혀 못 말한다 ⇒ M1 을 선정 규칙으로 인용 금지」*\n")

    # ── M5 ─────────────────────────────────────────────────────────────────
    say("## 6. M5 (기록만 · 라이브 대조) — 되밀림형 `r` 분포\n")
    r5v = sorted(r["r"] for r in pull5)
    say("| 표본 | n | 중앙 | 최소 | 최대 |")
    say("|---|---|---|---|---|")
    say(f"| 5번째 글 되밀림형 | {len(r5v)} | {np.median(r5v):+.2%} | {min(r5v):+.2%} | {max(r5v):+.2%} |")
    p4v = sorted(r["r"] for r in r4 if r["ok"] and bucket(r["r"]) == "되밀림형")
    if p4v:
        say(f"| 4번째 글 되밀림형(재계산) | {len(p4v)} | {np.median(p4v):+.2%} | "
            f"{min(p4v):+.2%} | {max(p4v):+.2%} |")
    allv = sorted(r5v + p4v)
    say(f"| 누적 | {len(allv)} | {np.median(allv):+.2%} | {min(allv):+.2%} | {max(allv):+.2%} |")
    say(f"\n라이브 `entry_band_up_pct` = **+{BAND_UP:.0%}** (그 위로 갭업하면 매수 포기).")
    say(f"저자 되밀림형 등록일 종가는 그날 고가 대비 **{np.median(r5v):+.2%}**(중앙) 자리다.")
    say("🔴 **예측 아님 · 판정에 쓰지 않는다.** 저자 프로그램의 «매수 체결가»는 아직 복원 안 됐다"
        "(`PREREG_BUYLADDER.md` L1·L2 판정 불가).\n")

    # ── 부수 ────────────────────────────────────────────────────────────────
    say("## 7. 부수 — 창 절단 (삼양바이오팜)\n")
    say("🔑 **아래 「창 봉수」는 «등록일 D 를 포함한» 셈이다** — 12봉 = 등록일 + 그 앞 11봉.\n")
    say("| 종목 | 창 요구 | 창 실제 봉수(**D 포함**) | D **이전** 봉수 | 영향 |")
    say("|---|---|---|---|---|")
    for r in r5:
        if not r["ok"]:
            continue
        note = "🔴 **창이 절단됐다** — `[D−19,D]` 가 아니라 상장 이후 전 구간" \
            if r["nwin"] < WIN else "정상"
        say(f"| {r['name']} | {WIN}봉(D 포함) | {r['nwin']} | {r['nwin'] - 1} | {note} |")
    trunc = [r for r in r5 if r["ok"] and r["nwin"] < WIN]
    if trunc:
        sub = [r for r in r5 if r["ok"] and r["nwin"] == WIN]
        hs = sum(1 for r in sub if r["hit"])
        say(f"\n민감도 — 절단 건 제외 시 M1/R2 = **{hs}/{len(sub)} = {hs/len(sub)*100:.1f}%** "
            f"(문턱 M1 ≥83.3% ⇒ {'충족' if hs/len(sub) >= 5/6 else '미달'} · "
            f"R2 ≥50% ⇒ {'지지' if hs/len(sub) >= 0.5 else '불성립'})\n")

    (BASE / "RESULTS_REGDAY_POST5_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

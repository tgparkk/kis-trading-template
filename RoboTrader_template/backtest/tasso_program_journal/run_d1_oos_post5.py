# -*- coding: utf-8 -*-
"""5번째 글 `D1`(거래대금/시총) 자가보고 재검정 — `run_d1_oos.py` 승계.

정의 = `PREREG_D1_OOS.md` §2 동결분 그대로:
  `D1 = daily_prices.trading_value / daily_prices.market_cap` (**같은 행**).
  `market_cap` 이 NULL/0 이면 그 날은 「판정 불가」로 분모에서 뺀다.
  허용오차 = 상대오차 ±20%.

🔴 문언 부류(구간·날짜명시 / 단일·날짜명시 / 구간·날짜모호)와 비교 규칙은
   `INTAKE_2026-08-29_post5.md` §3 에서 **계산 «전»** 동결된 것을 그대로 옮겨 쓴다.
   값을 보고 바꾸지 않는다.

🔴 5번째 글 문언에는 「최대」류·「당시」류가 **하나도 없다** ⇒ `RESULTS_D1_OOS.md` §5 의
   W1·W2 는 **판정 불가**. 문언을 재해석해 억지로 판정하지 않는다.

라이브 트리 import 0건 (psycopg2 + 표준 라이브러리 + 같은 폴더 `run_tests.DSN`).
DB 는 읽기만 한다(SELECT).
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

import psycopg2

from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

TOL = 0.20          # PREREG_D1_OOS.md §2 (원 사전등록 그대로 · 고치지 않는다)
N2_DEGRADE = 30     # PREREG_D1_OOS.md §4 N2
PSEUDO = ("KOSPI", "KOSDAQ", "KS11", "KQ11")

# ── 대상 (INTAKE §3 표 그대로 · 계산 전 동결) ────────────────────────────────
# kind: "single" | "range"
# rep : 자가보고. single → (v,) · range → (min, max)
# span: single → "YYYY-MM-DD" · range → ("시작", "끝")
# reg : 저자 등록일(INTAKE §1) — 민감도용 창 기준일
# prev_class: 직전 사전등록의 문언 부류 "A"(「당시」)/"B"(「최대」) — 이번 글엔 해당 없음(None)
TARGETS = [
    dict(name="혜인", code="003010", kind="range", rep=(0.63, 0.83),
         span=("2026-08-07", "2026-08-11"), reg="2026-08-11",
         wording="구간·날짜명시", prev_class=None,
         quote="8월 7~11일간 거래대금/시총 비율이 0.63배 ~ 0.83배로 증가"),
    dict(name="한국화장품제조", code="003350", kind="range", rep=(0.20, 0.30),
         span=("2026-08-11", "2026-08-12"), reg="2026-08-12",
         wording="구간·날짜명시", prev_class=None,
         quote="8월 11~12일 거래대금/시총 비율은 0.2~0.3배이나 거래대금은 양일간 1400억정도 발생"),
    dict(name="코데즈컴바인", code="047770", kind="single", rep=(0.53,),
         span="2026-08-19", reg="2026-08-21",
         wording="단일·날짜명시", prev_class=None,
         quote="8월 19일 거래대금/시총 비율이 0.53배"),
    dict(name="삼양바이오팜", code="0120G0", kind="single", rep=(0.29,),
         span="2026-08-21", reg="2026-08-21",
         wording="단일·날짜명시", prev_class=None,
         quote="8월 21일 거대래금/시총 비율이 0.29배"),
    dict(name="광전자", code="017900", kind="range", rep=(0.24, 0.38),
         span=("2026-08-03", "2026-08-07"), reg="2026-08-05",
         wording="구간·날짜모호 (「8월 초」 = 08-03~08-07, INTAKE §3 동결 매핑)",
         prev_class=None,
         quote="8월 초부터 단기 급등한 5G통신주, 거래대금/시총비율이 0.24~0.38배 수준"),
]

# 제외 — DB 에 종목 자체가 없다(INTAKE §2-6). 스크립트가 «실제로» 확인한다.
EXCLUDED_NAME = "레메디"
EXCLUDED_REP = 0.8
EXCLUDED_QUOTE = "신규주 이며, 거래대금/시총 비율이 0.8배로 높은 수준"

# 저자 부수 진술(§3 밖 · 같은 문장) — 절대 거래대금
AUX_KHJ_DAYS = ("2026-08-11", "2026-08-12")   # 한국화장품제조 「양일간 1400억」
AUX_KHJ_CLAIM = 140_000_000_000
AUX_KJ_CLAIM = 100_000_000_000                # 광전자 「거래대금 1,000억원 수준」

# 누적 집계용 과거 확정치 (문서에서 옮겨 적은 상수 · 재계산 아님)
PRIOR = [
    ("3번째 글 (`RESULTS.md` §Q2)", 1, 2, "매드업 ✅ · 솔트룩스 ❌"),
    ("4번째 글 (`RESULTS_D1_OOS.md` §0)", 3, 5, "한켐·금호·지투 ✅ · PS일렉·이노테크 ❌"),
]
PRIOR_N2_MEDIAN = 2      # RESULTS_D1_OOS.md §2 에 적힌 4번째 글 `m` 중앙값
PRIOR_W4_OVER = 2        # RESULTS_D1_OOS.md §5 W4 — 과대 (솔트룩스·이노테크)
PRIOR_W4_UNDER = 1       # RESULTS_D1_OOS.md §5 W4 — 과소 (PS일렉)


def say(s=""):
    print(s)
    OUT.append(s)


# 🔑 콘솔이 cp949 면 전각 기호에서 죽는다. 산출 «파일»은 항상 UTF-8 로 쓴다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def fmt(v, n=4):
    return "—" if v is None else f"{v:.{n}f}"


def pct(v):
    return "—" if v is None else f"{100 * v:.2f}%"


def won(v):
    """원 → 「N억」 표기."""
    return "—" if v is None else f"{v / 1e8:,.0f}억"


def series(cur, code):
    """[(date, trading_value, market_cap, close, volume, high, low, d1)] 전 계열."""
    cur.execute(
        "SELECT date, trading_value, market_cap, close, volume, high, low "
        "FROM daily_prices WHERE stock_code=%s ORDER BY date", (code,))
    out = []
    for dt, tv, mc, cl, vol, hi, lo in cur.fetchall():
        tvf = float(tv) if tv is not None else None
        mcf = float(mc) if mc is not None else None
        d1 = (tvf / mcf) if (tvf is not None and mcf is not None and mcf > 0) else None
        out.append(dict(date=dt, tv=tvf, mc=mcf, close=float(cl) if cl is not None else None,
                        vol=float(vol) if vol is not None else None,
                        high=float(hi) if hi is not None else None,
                        low=float(lo) if lo is not None else None, d1=d1))
    return out


def universe_m(cur, date, lo, hi):
    """N2: 그날 유니버스에서 [lo,hi] 안에 드는 종목 수 / 유니버스 크기."""
    cur.execute(
        "SELECT count(*) FILTER (WHERE trading_value::numeric/market_cap::numeric "
        "                        BETWEEN %s AND %s), count(*) "
        "FROM daily_prices WHERE date=%s AND market_cap>0 AND trading_value IS NOT NULL "
        "  AND stock_code <> ALL(%s)",
        (lo, hi, date, list(PSEUDO)))
    return cur.fetchone()


def rel(measured, reported):
    return None if measured is None else abs(measured - reported) / reported


def measure(ser, t, key="d1"):
    """동결 비교규칙대로 측정값을 뽑는다.

    single → (그 날짜 값, 그 날짜)
    range  → ((min, max), (min일, max일))
    """
    if t["kind"] == "single":
        row = next((r for r in ser if r["date"] == t["span"]), None)
        v = row[key] if row else None
        return (v,), (t["span"],)
    lo_d, hi_d = t["span"]
    seg = [r for r in ser if lo_d <= r["date"] <= hi_d and r[key] is not None]
    if not seg:
        return (None, None), (None, None)
    mn = min(seg, key=lambda r: r[key])
    mx = max(seg, key=lambda r: r[key])
    return (mn[key], mx[key]), (mn["date"], mx["date"])


def judge(vals, t):
    """양끝(또는 1점) 각각 상대오차 ≤ TOL 이면 재현."""
    errs = [rel(v, r) for v, r in zip(vals, t["rep"])]
    ok = all(e is not None and e <= TOL for e in errs)
    return errs, ok


def main():
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    cur.execute("SELECT max(date) FROM daily_prices")
    max_date = cur.fetchone()[0]

    say("# RESULTS_D1_OOS_POST5_NUMBERS — 기계 생성 (수정 금지)\n")
    say("정의 `PREREG_D1_OOS.md` §2 · 문언 부류 `INTAKE_2026-08-29_post5.md` §3 · "
        "생성 `run_d1_oos_post5.py`")
    say(f"`kis_template.daily_prices` 최신 봉 **{max_date}**\n")

    # ── §A 대상 (동결) ───────────────────────────────────────────────────
    say("## §A. 대상·문언 부류 (계산 «전» 동결 · INTAKE §3)\n")
    say("| 종목 | 코드 | 자가보고 | 저자 문언 | 비교 구간/날짜 | 부류 | 직전 A/B 부류 |")
    say("|---|---|---|---|---|---|---|")
    for t in TARGETS:
        rep = f"{t['rep'][0]:.2f}" if t["kind"] == "single" else f"{t['rep'][0]:.2f}~{t['rep'][1]:.2f}"
        sp = t["span"] if t["kind"] == "single" else f"{t['span'][0]}..{t['span'][1]}"
        say(f"| {t['name']} | {t['code']} | {rep} | *「{t['quote']}」* | {sp} | {t['wording']} "
            f"| {t['prev_class'] or '**해당 없음**'} |")
    say(f"| {EXCLUDED_NAME} | — | {EXCLUDED_REP:.2f} | *「{EXCLUDED_QUOTE}」* | — | "
        f"단일·날짜없음 | **해당 없음** |")
    say()

    # ── 레메디 부재 확인 ────────────────────────────────────────────────
    absent = {}
    for tbl in ("stock_info", "stock_industry"):
        cur.execute(f"SELECT stock_code, stock_name FROM {tbl} WHERE stock_name LIKE %s",
                    (f"%{EXCLUDED_NAME}%",))
        absent[tbl] = cur.fetchall()
    say(f"**{EXCLUDED_NAME} 제외 근거(실측)**: `stock_info` 이름검색 **{len(absent['stock_info'])}건** · "
        f"`stock_industry` 이름검색 **{len(absent['stock_industry'])}건** ⇒ 종목코드 확정 불가 ⇒ "
        "`daily_prices` 조회 자체가 불가능하다. **분모에서 뺀다.**\n")

    # ── §B 주 판정 ──────────────────────────────────────────────────────
    sers = {t["code"]: series(cur, t["code"]) for t in TARGETS}

    say("## §B. 주 판정 — 동결 비교규칙 (상대오차 ≤ 20%)\n")
    say("| 종목 | 자가보고 | 실측 `D1` | 실측일 | 상대오차 | 판정 |")
    say("|---|---|---|---|---|---|")
    judged = []
    for t in TARGETS:
        ser = sers[t["code"]]
        vals, dts = measure(ser, t)
        errs, ok = judge(vals, t)
        if t["kind"] == "single":
            rep_s, val_s, dt_s, err_s = f"{t['rep'][0]:.2f}", fmt(vals[0]), dts[0] or "—", pct(errs[0])
        else:
            rep_s = f"{t['rep'][0]:.2f} ~ {t['rep'][1]:.2f}"
            val_s = f"{fmt(vals[0])} ~ {fmt(vals[1])}"
            dt_s = f"{dts[0] or '—'} / {dts[1] or '—'}"
            err_s = f"{pct(errs[0])} / {pct(errs[1])}"
        say(f"| {t['name']} | {rep_s} | **{val_s}** | {dt_s} | {err_s} | "
            f"{'✅ 재현' if ok else '❌ 불일치'} |")
        judged.append((t, vals, dts, errs, ok))
    say()
    rec = sum(1 for j in judged if j[4])
    n = len(judged)
    assert rec == sum(1 for j in judged
                      if all(e is not None and e <= TOL for e in j[3])), "재현 집계 불일치"
    say(f"**5번째 글 재현 {rec}/{n}** (레메디 1건은 DB 부재로 분모 밖).\n")

    # ── §C 원시 일별값 ──────────────────────────────────────────────────
    say("## §C. 원시 일별값 — 비교 구간 전체 (`trading_value` / `market_cap` / `D1`)\n")
    for t in TARGETS:
        ser = sers[t["code"]]
        if t["kind"] == "single":
            lo_d = hi_d = t["span"]
        else:
            lo_d, hi_d = t["span"]
        seg = [r for r in ser if lo_d <= r["date"] <= hi_d]
        say(f"**{t['name']} ({t['code']}) — {lo_d}..{hi_d}**\n")
        say("| 날짜 | 거래대금 | 시총 | `D1` | 종가 | 함의 주식수 `시총/종가` |")
        say("|---|---|---|---|---|---|")
        for r in seg:
            shares = (r["mc"] / r["close"]) if (r["mc"] and r["close"]) else None
            close_s = "—" if r["close"] is None else format(r["close"], ",.0f")
            shares_s = "—" if shares is None else format(shares, ",.0f")
            say(f"| {r['date']} | {won(r['tv'])} | {won(r['mc'])} | **{fmt(r['d1'])}** | "
                f"{close_s} | {shares_s} |")
        nmiss = sum(1 for r in seg if r["d1"] is None)
        say(f"\n봉 수 **{len(seg)}** · `D1` 결측(시총 NULL/0) **{nmiss}**\n")

    # ── §D 민감도: 직전 사전등록 측정자 A/B ─────────────────────────────
    say("## §D. 민감도 — 직전 사전등록(`PREREG_D1_OOS.md` §2)의 측정자 A/B\n")
    say("🔴 **탐색적이다.** 5번째 글 문언에는 「당시」·「최대」가 없으므로 A/B 는 «판정에 쓰지 않는다».")
    say("A = 명시일(구간이면 시작일·종료일 둘 다) · B1 = `max(D1)` over `[등록일−19, 등록일+4]` · "
        "B2 = 같은 최댓값을 `[등록일−4, 등록일+4]` 로.\n")
    say("| 종목 | 등록일 | A(시작) | A(끝) | B1 | B1 최대일 | B2 | B2 최대일 | 창봉수 | 등록일 이후 봉수 | 시총결측 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    ab, offs = {}, []
    for t in TARGETS:
        ser = sers[t["code"]]
        idx = {r["date"]: i for i, r in enumerate(ser)}
        if t["reg"] not in idx:
            say(f"| {t['name']} | {t['reg']} | — | — | — | — | — | — | — | — | **등록일 봉 없음** |")
            continue
        r0 = idx[t["reg"]]

        def win(lo, hi):
            seg = [r for r in ser[max(0, r0 + lo): r0 + hi + 1] if r["d1"] is not None]
            if not seg:
                return None, None
            m = max(seg, key=lambda r: r["d1"])
            return m["d1"], m["date"]

        b1, b1d = win(-19, 4)
        b2, b2d = win(-4, 4)
        wseg = ser[max(0, r0 - 19): r0 + 5]
        miss = sum(1 for r in wseg if r["d1"] is None)
        maxoff = len(ser) - 1 - r0
        if t["kind"] == "single":
            a_s = next((r["d1"] for r in ser if r["date"] == t["span"]), None)
            a_e = a_s
        else:
            a_s = next((r["d1"] for r in ser if r["date"] == t["span"][0]), None)
            a_e = next((r["d1"] for r in ser if r["date"] == t["span"][1]), None)
        ab[t["code"]] = (b1, b1d, b2, b2d)
        say(f"| {t['name']} | {t['reg']} | {fmt(a_s)} | {fmt(a_e)} | **{fmt(b1)}** | {b1d or '—'} "
            f"| {fmt(b2)} | {b2d or '—'} | {len(wseg)} | {maxoff} | {miss} |")
        offs.append(maxoff)
    say()
    say(f"- 등록일 이후 봉 수 최소 **{min(offs)}** ⇒ 창 상단 `D+4` 는 "
        f"**{sum(1 for o in offs if o >= 4)}/{len(offs)}** 건에서 충족"
        "(직전 글은 08-22 미수집으로 잘렸다).\n")
    same = sum(1 for v in ab.values() if v[0] is not None and v[0] == v[2])
    say(f"**N3(창 민감도)**: `B1`(창 `[D−19,D+4]`) 과 `B2`(창 `[D−4,D+4]`) 가 같은 건 "
        f"**{same}/{len(ab)}** ⇒ "
        + ("✅ **창 의존 없음**" if same == len(ab) else "🔴 **창 의존 있음 — 창 선택이 값을 바꾼다**") + "\n")

    # 참고: B1 을 자가보고 max 와 견줬을 때
    say("**참고(탐색)** — 만약 B1(창 최대)을 자가보고 «최댓값»과 견줬다면:\n")
    say("| 종목 | 자가보고 최댓값 | B1 | 상대오차 | (탐색) 판정 |")
    say("|---|---|---|---|---|")
    b1hit = 0
    for t in TARGETS:
        b1 = ab.get(t["code"], (None,))[0]
        rep_hi = t["rep"][-1]
        e = rel(b1, rep_hi)
        hit = e is not None and e <= TOL
        b1hit += 1 if hit else 0
        say(f"| {t['name']} | {rep_hi:.2f} | {fmt(b1)} | {pct(e)} | {'✅' if hit else '❌'} |")
    say(f"\n- (탐색) B1 vs 자가보고 최댓값 적중 **{b1hit}/{len(TARGETS)}** — "
        "🔴 결과를 본 뒤 측정자를 고르는 것이므로 **판정으로 인용 금지**.\n")

    # ── §E 민감도: 시총 당일 vs 전일 ────────────────────────────────────
    say("## §E. 민감도 — `market_cap` 당일 vs 전일 (동결 정의는 «당일»)\n")
    say("`D1_prev(d) = trading_value(d) / market_cap(직전 거래일)`. **판정에는 쓰지 않는다.**\n")
    say("| 종목 | 당일 실측 | 당일 오차 | 전일 실측 | 전일 오차 | 당일 | 전일 |")
    say("|---|---|---|---|---|---|---|")
    rec_prev = 0
    for t in TARGETS:
        ser = sers[t["code"]]
        prev = []
        for i, r in enumerate(ser):
            mc_prev = ser[i - 1]["mc"] if i > 0 else None
            d1p = (r["tv"] / mc_prev) if (r["tv"] is not None and mc_prev and mc_prev > 0) else None
            prev.append(dict(r, d1p=d1p))
        vals_p, _ = measure(prev, t, key="d1p")
        errs_p, ok_p = judge(vals_p, t)
        vals, _ = measure(ser, t)
        errs, ok = judge(vals, t)
        rec_prev += 1 if ok_p else 0
        if t["kind"] == "single":
            say(f"| {t['name']} | {fmt(vals[0])} | {pct(errs[0])} | {fmt(vals_p[0])} | {pct(errs_p[0])} "
                f"| {'✅' if ok else '❌'} | {'✅' if ok_p else '❌'} |")
        else:
            say(f"| {t['name']} | {fmt(vals[0])}~{fmt(vals[1])} | {pct(errs[0])}/{pct(errs[1])} "
                f"| {fmt(vals_p[0])}~{fmt(vals_p[1])} | {pct(errs_p[0])}/{pct(errs_p[1])} "
                f"| {'✅' if ok else '❌'} | {'✅' if ok_p else '❌'} |")
    say()
    say(f"- 당일 시총 **{rec}/{n}** vs 전일 시총 **{rec_prev}/{n}** ⇒ "
        + ("**전일 쪽이 더 재현한다**" if rec_prev > rec else
           ("**당일 쪽이 더 재현한다**" if rec > rec_prev else "**차이 없다**"))
        + " (동결 정의는 당일 — 바꾸지 않는다).\n")

    # ── §F 반증축 N1·N2 ────────────────────────────────────────────────
    say("## §F. 반증축 (`PREREG_D1_OOS.md` §4 승계)\n")
    say("### N1 — 자릿수 (`D6 = D1 × 10`)\n")
    say("| 종목 | `D1` 판정 | `D6` 실측 | `D6` 판정 |")
    say("|---|---|---|---|")
    rec6 = 0
    for t, vals, dts, errs, ok in judged:
        v6 = tuple(None if v is None else v * 10 for v in vals)
        e6, ok6 = judge(v6, t)
        rec6 += 1 if ok6 else 0
        v6s = fmt(v6[0], 3) if t["kind"] == "single" else f"{fmt(v6[0], 3)}~{fmt(v6[1], 3)}"
        say(f"| {t['name']} | {'✅' if ok else '❌'} | {v6s} | {'✅' if ok6 else '❌'} |")
    say()
    say(f"- `D6` 재현 **{rec6}/{n}** vs `D1` **{rec}/{n}** ⇒ "
        + ("🔴 **`D6` 가 더 맞힌다 ⇒ 지지 취소**" if rec6 > rec else "✅ **미발동**") + "\n")

    say("### N2 — 판별력 (당일 유니버스 `m`)\n")
    say("| 종목 | 기준일 | 견준 값 | ±20% 대역 | 대역 내 `m` | 유니버스 |")
    say("|---|---|---|---|---|---|")
    ms = []
    for t, vals, dts, errs, ok in judged:
        pairs = ([(t["rep"][0], dts[0])] if t["kind"] == "single"
                 else [(t["rep"][0], dts[0]), (t["rep"][1], dts[1])])
        for repv, d in pairs:
            if d is None:
                say(f"| {t['name']} | — | {repv:.2f} | — | — | — |")
                continue
            lo, hi = repv * (1 - TOL), repv * (1 + TOL)
            m, tot = universe_m(cur, d, lo, hi)
            ms.append(m)
            say(f"| {t['name']} | {d} | {repv:.2f} | {lo:.3f}~{hi:.3f} | **{m}** | {tot} |")
    # 🔴 초판 결함(verifier B2): `sorted(ms)[len(ms)//2]` 는 «짝수 n 에서 상위 중앙값»을 낸다.
    #    m=[1,3,6,7,9,9,14,14] 의 참 중앙값은 8.0 인데 9 로 인쇄됐다. statistics.median 으로 고친다.
    #    🔑 강등 문턱이 30 이라 이 정정으로 판정은 바뀌지 않는다(8.0 도 9 도 30 미만).
    med = statistics.median(ms) if ms else None
    say()
    say(f"- `m` 값 {sorted(ms)} · 중앙값 **{med}** (강등 문턱 {N2_DEGRADE}) ⇒ "
        + ("🔴 **판별력 없음으로 강등**" if (med or 0) >= N2_DEGRADE
           else "**미발동 (강등 조건 불충족)**") + "\n")
    say("  🔑 동결 N2 규칙은 «강등 조건»만 정한다. 이번 글엔 선언할 G1 지지 자체가 없으므로 "
        "「판별력 있음」이라고 **단언하지 않는다** — 강등이 걸리지 않았을 뿐이다.")
    say(f"- 참고: 4번째 글의 `m` 중앙값은 **{PRIOR_N2_MEDIAN}** 이었다"
        f"(`RESULTS_D1_OOS.md` §2 에 적힌 값) ⇒ 이번이 **{med}** 로 더 크다 = 판별력이 더 약하다.\n")

    say("### W4 — 불일치 건의 부호 (기록만)\n")
    say("| 종목 | 자가보고 | 실측 | 방향 | 배수 |")
    say("|---|---|---|---|---|")
    over = under = 0
    for t, vals, dts, errs, ok in judged:
        if ok:
            continue
        pairs = ([(t["rep"][0], vals[0], "단일")] if t["kind"] == "single"
                 else [(t["rep"][0], vals[0], "하단"), (t["rep"][1], vals[1], "상단")])
        for repv, v, tag in pairs:
            if v is None or v == 0:
                say(f"| {t['name']}({tag}) | {repv:.2f} | — | — | — |")
                continue
            if repv > v:
                over += 1
            else:
                under += 1
            say(f"| {t['name']}({tag}) | {repv:.2f} | {v:.4f} | "
                f"{'자가보고 **과대**' if repv > v else '자가보고 **과소**'} | {repv / v:.2f}배 |")
    say()
    say(f"- 이번 글 과대 **{over}** · 과소 **{under}**")
    say(f"- 누계(3~5번째 글) 과대 **{PRIOR_W4_OVER + over}** · 과소 **{PRIOR_W4_UNDER + under}** "
        f"(직전 확정치 과대 {PRIOR_W4_OVER}·과소 {PRIOR_W4_UNDER} — `RESULTS_D1_OOS.md` §5 W4)\n")

    # ── §G 저자 부수 진술 ──────────────────────────────────────────────
    say("## §G. 저자 부수 진술 — 절대 거래대금\n")
    khj = sers["003350"]
    rows = [r for r in khj if r["date"] in AUX_KHJ_DAYS]
    s = sum(r["tv"] for r in rows if r["tv"] is not None)
    say(f"**한국화장품제조 「양일간 1400억」** ({' + '.join(AUX_KHJ_DAYS)})\n")
    say("| 날짜 | 거래대금 |")
    say("|---|---|")
    for r in rows:
        say(f"| {r['date']} | {won(r['tv'])} ({r['tv']:,.0f}원) |")
    say(f"| **합계** | **{won(s)}** ({s:,.0f}원) |")
    say(f"\n저자 주장 {won(AUX_KHJ_CLAIM)} 대비 상대오차 **{pct(rel(s, AUX_KHJ_CLAIM))}** ⇒ "
        f"{'✅ ±20% 안' if rel(s, AUX_KHJ_CLAIM) <= TOL else '❌ ±20% 밖'}\n")

    kj = sers["017900"]
    lo_d, hi_d = TARGETS[4]["span"]
    kseg = [r for r in kj if lo_d <= r["date"] <= hi_d]
    say(f"**광전자 「거래대금 1,000억원 수준」** ({lo_d}..{hi_d})\n")
    say("| 날짜 | 거래대금 | 1,000억 대비 상대오차 |")
    say("|---|---|---|")
    for r in kseg:
        say(f"| {r['date']} | {won(r['tv'])} ({r['tv']:,.0f}원) | {pct(rel(r['tv'], AUX_KJ_CLAIM))} |")
    kmax = max((r["tv"] for r in kseg if r["tv"] is not None), default=None)
    kmean = (sum(r["tv"] for r in kseg if r["tv"] is not None)
             / max(1, sum(1 for r in kseg if r["tv"] is not None)))
    kbest = min((r for r in kseg if r["tv"] is not None),
                key=lambda r: abs(r["tv"] - AUX_KJ_CLAIM), default=None)
    say(f"| **최댓값** | **{won(kmax)}** | {pct(rel(kmax, AUX_KJ_CLAIM))} |")
    say(f"| **평균** | **{won(kmean)}** | {pct(rel(kmean, AUX_KJ_CLAIM))} |")
    say(f"| **∃-최근접일 {kbest['date']}** | **{won(kbest['tv'])}** | "
        f"**{pct(rel(kbest['tv'], AUX_KJ_CLAIM))}** |")
    say(f"\n저자 주장 {won(AUX_KJ_CLAIM)} 대비 — 최댓값 상대오차 **{pct(rel(kmax, AUX_KJ_CLAIM))}** · "
        f"평균 상대오차 **{pct(rel(kmean, AUX_KJ_CLAIM))}**\n")

    # ── §H 삼양바이오팜 원시 시총 ───────────────────────────────────────
    say("## §H. 삼양바이오팜(`0120G0`) 원시 시총 — 신규 상장(08-05 분할 재상장)\n")
    say("| 날짜 | 종가 | 시총(원) | 함의 주식수 `시총/종가` | 거래대금 | 거래량 | 함의 평균가 `거래대금/거래량` | [저가, 고가] | `D1` |")
    say("|---|---|---|---|---|---|---|---|---|")
    for r in sers["0120G0"]:
        shares = (r["mc"] / r["close"]) if (r["mc"] and r["close"]) else None
        avg = (r["tv"] / r["vol"]) if (r["tv"] is not None and r["vol"]) else None
        inside = ("—" if (avg is None or r["low"] is None or r["high"] is None)
                  else ("✅" if r["low"] <= avg <= r["high"] else "🔴 밖"))
        shares_s = "—" if shares is None else format(shares, ",.0f")
        vol_s = "—" if r["vol"] is None else format(r["vol"], ",.0f")
        avg_s = "—" if avg is None else format(avg, ",.0f")
        say(f"| {r['date']} | {r['close']:,.0f} | {r['mc']:,.0f} | "
            f"{shares_s} | {won(r['tv'])} | {vol_s} | {avg_s} {inside} | "
            f"[{r['low']:,.0f}, {r['high']:,.0f}] | {fmt(r['d1'])} |")
    sy_all = sers["0120G0"]
    sh = [r["mc"] / r["close"] for r in sy_all if r["mc"] and r["close"]]
    inside_n = sum(1 for r in sy_all
                   if r["tv"] is not None and r["vol"] and r["low"] is not None
                   and r["high"] is not None and r["low"] <= r["tv"] / r["vol"] <= r["high"])
    say(f"\n- DB 보유 봉 **{len(sy_all)}개** (최초 {sy_all[0]['date']} ~ 최종 {sy_all[-1]['date']}) — "
        "그 이전 봉은 **없다**(분할 재상장 신규주).")
    say(f"- 함의 주식수 범위 **{min(sh):,.0f} ~ {max(sh):,.0f}** · 폭 "
        f"**{100 * (max(sh) - min(sh)) / min(sh):.3f}%** · 서로 다른 값 "
        f"**{len(set(round(x) for x in sh))}종** ⇒ 사실상 상수다.")
    say(f"- 함의 평균가 `거래대금/거래량` 이 그날 [저가, 고가] 안에 든 날 **{inside_n}/{len(sy_all)}**"
        " ⇒ 시총·거래대금이 **내부적으로는** 정합하다(주식수가 옳다는 뜻은 아니다).\n")

    # ── §I 사후 관측 ───────────────────────────────────────────────────
    say("## §I. 🔴 사후 관측 — 사전등록 «밖» (판정에 쓰지 않는다 · 다음 글 예측으로 동결)\n")
    say("### I-1. ∃-매칭 — 「구간 안 어느 날엔가 그 값이 있는가」\n")
    say("동결 규칙은 *구간의 `[min, max]`* 와 견주라고 했다. 아래는 **다른 질문**이다: "
        "저자가 적은 각 끝값에 대해 **명시 구간 안에서 상대오차가 가장 작은 날**을 찾는다.\n")
    say("| 종목 | 저자 값 | 동결규칙 실측 | 동결 오차 | ∃-최근접일 | 그날 `D1` | ∃ 오차 |")
    say("|---|---|---|---|---|---|---|")
    exists_hit = exists_tot = 0
    for t, vals, dts, errs, ok in judged:
        if t["kind"] == "single":
            lo_d = hi_d = t["span"]
        else:
            lo_d, hi_d = t["span"]
        seg = [r for r in sers[t["code"]] if lo_d <= r["date"] <= hi_d and r["d1"] is not None]
        for i, repv in enumerate(t["rep"]):
            best = min(seg, key=lambda r: abs(r["d1"] - repv)) if seg else None
            e = rel(best["d1"], repv) if best else None
            exists_tot += 1
            exists_hit += 1 if (e is not None and e <= TOL) else 0
            tag = "" if t["kind"] == "single" else ("(하단)" if i == 0 else "(상단)")
            say(f"| {t['name']}{tag} | {repv:.2f} | {fmt(vals[i])} | {pct(errs[i])} | "
                f"{best['date'] if best else '—'} | {fmt(best['d1']) if best else '—'} | {pct(e)} |")
    say()
    say(f"- 동결규칙 끝값 적중 **{sum(1 for j in judged for e in j[3] if e is not None and e <= TOL)}"
        f"/{exists_tot}** vs ∃-매칭 끝값 적중 **{exists_hit}/{exists_tot}**\n")

    say("### I-2. 삼양바이오팜 — 자가보고 0.29 가 성립하려면 시총이 얼마여야 하나\n")
    sy = next(r for r in sers["0120G0"] if r["date"] == "2026-08-21")
    need_mc = sy["tv"] / 0.29
    need_sh = need_mc / sy["close"]
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 08-21 거래대금 | {sy['tv']:,.0f}원 ({won(sy['tv'])}) |")
    say(f"| 08-21 DB 시총 | {sy['mc']:,.0f}원 ({won(sy['mc'])}) |")
    say(f"| 08-21 DB `D1` | **{sy['d1']:.4f}** |")
    say(f"| 자가보고 0.29 가 되려면 필요한 시총 | {need_mc:,.0f}원 ({won(need_mc)}) |")
    say(f"| 그때의 함의 주식수 (종가 {sy['close']:,.0f}원) | {need_sh:,.0f}주 |")
    say(f"| DB 함의 주식수 | {sy['mc'] / sy['close']:,.0f}주 |")
    say(f"| 배율 (DB ÷ 필요) | **{(sy['mc'] / need_mc):.2f}배** |")
    prev = next(r for r in sers["0120G0"] if r["date"] == "2026-08-20")
    say()
    say(f"🔑 **자릿수 우연 하나**: 직전 거래일 08-20 의 `D1` = **{prev['d1']:.4f}** 이고 "
        f"`×10 = {prev['d1'] * 10:.4f}` 로 자가보고 **0.29** 와 상대오차 "
        f"**{pct(rel(prev['d1'] * 10, 0.29))}** 다. **해석하지 않는다 — n=1 우연과 구분 불가.**\n")

    # ── §J W1/W2 ───────────────────────────────────────────────────────
    say("## §J. `RESULTS_D1_OOS.md` §5 W1·W2 — 판정 불가\n")
    n_b = sum(1 for t in TARGETS if t["prev_class"] == "B")
    n_a = sum(1 for t in TARGETS if t["prev_class"] == "A")
    say(f"- 「최대」류(B) 해당 건 **{n_b}건** · 「당시」류(A) 해당 건 **{n_a}건** (전체 {len(TARGETS)}건)")
    say("- `RESULTS_D1_OOS.md` §5 단서: *「「최대」 또는 「당시」 문언 건이 각각 3건 미만이면 그 축의 판정을 미룬다」*")
    say(f"- ⇒ **W1 판정 불가**(0 < 3) · **W2 판정 불가**(0 < 3) · **W3 판정 불가**(W1·W2 미판정)")
    say("- 🔴 문언을 「최대」·「당시」로 재해석해 판정을 만들지 «않는다».\n")

    # ── §K 누적 ────────────────────────────────────────────────────────
    say("## §K. 누적 재현 집계 (🔴 탐색적 — 어느 사전등록 문턱에도 걸려 있지 않다)\n")
    say("| 글 | 판정 대상 | 재현 | 비고 |")
    say("|---|---|---|---|")
    tr = tn = 0
    for label, r_, n_, note in PRIOR:
        tr += r_
        tn += n_
        say(f"| {label} | {n_} | **{r_}/{n_}** | {note} |")
    tr += rec
    tn += n
    say(f"| 5번째 글 (이 문서) | {n} | **{rec}/{n}** | 레메디 1건 DB 부재로 제외 |")
    say(f"| **누적** | **{tn}** | **{tr}/{tn}** ({100 * tr / tn:.1f}%) | — |")
    say()
    say("⚠️ 세 글의 **비교 규칙이 서로 다르다**(3번째: 단일 2점 · 4번째: 문언별 A/B · "
        "5번째: 단일 1점 + 구간 양끝). 합산은 **동일 검정의 반복이 아니다**.\n")

    # ── §L 데이터 점검 ─────────────────────────────────────────────────
    say("## §L. 데이터 점검 — 일자별 유니버스 크기 (`market_cap>0` 인 종목 수)\n")
    say("N2 표의 유니버스가 08-04 만 눈에 띄게 작아서 따로 센다. **판정과 무관.**\n")
    cur.execute(
        "SELECT date, count(*) FILTER (WHERE market_cap>0 AND trading_value IS NOT NULL), count(*) "
        "FROM daily_prices WHERE date BETWEEN '2026-08-03' AND '2026-08-21' "
        "  AND stock_code <> ALL(%s) GROUP BY date ORDER BY date", (list(PSEUDO),))
    say("| 날짜 | `market_cap>0` | 전체 행 |")
    say("|---|---|---|")
    urows = cur.fetchall()
    for d, ok_c, tot_c in urows:
        say(f"| {d} | {ok_c} | {tot_c} |")
    umin = min(r[1] for r in urows)
    umax = max(r[1] for r in urows)
    say(f"\n- 최소 **{umin}** · 최대 **{umax}** · 차 **{umax - umin}** — "
        f"작은 쪽은 {', '.join(r[0] for r in urows if r[1] == umin)} 뿐이다. "
        "이번 판정 대상 봉은 그 날에도 전부 존재하므로 **판정에 영향 없다**.\n")

    (BASE / "RESULTS_D1_OOS_POST5_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

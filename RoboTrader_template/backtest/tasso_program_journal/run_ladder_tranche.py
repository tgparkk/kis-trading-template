# -*- coding: utf-8 -*-
"""매수 사다리 「체결 차수 <-> 낙폭」 정렬 축 — `PREREG_LADDER_TRANCHE.md` **1회 실행**.

동결 설계(문서 §4~§5) 그대로:
  · 통계량 `V` = `N_i < N_j` 이면서 `DD_i >= DD_j` 인 쌍의 수 (동률 대역 제외 후)
  · 귀무 = 차수 다중집합을 낙폭 벡터에 무작위 재배정 (관측과 «같은 크기»)
  · `p` = `P(V <= V_obs)` 단측
  · 창5 = `[D, D+4거래일]` 을 «주»로 못 박음 · 창3·창A 는 §4-5 의 «의무» 민감도
  · 동률 대역 `delta = 1.0%p`
  · 판정 시점: 누적 비교가능 쌍 **40 이상**일 때만. 미만이면 보류.
  · T2(sigma20 정규화) · T3(경과 거래일) 반증축 «필수»

🔴 **계산 «전» 에 고정한 해석 결정** (RESULTS_LADDER_TRANCHE.md §1 에 같은 문장으로 적는다):
  B-1 창A 의 「글 발행일」 = 그 항목이 실린 글의 발행일. post4 = 2026-08-22 · post5 = 2026-08-29.
      08-29 는 토요일(휴장)이라 DB 스냅샷 최대 2026-08-28 로 절단한다.
      1회차가 쓴 `[D, 2026-08-21]` 재현행도 함께 인쇄한다.
  B-2 한켐(post5)은 §4-1 의 carve-out(「매도 쪽만 수동이면 포함」)을 적용해 **포함**한다.
      저자 문언은 *「직접 매도」* 이고 매수 쪽 수동 서술이 없다. flag 만 단다.
  B-3 `delta` 는 DD 축(%p) 의 정의다. T3 축(경과 거래일)은 %p 가 아니므로
      동률 대역 = **정확히 같은 값만 제외**(delta_E = 0).
  B-4 T2 는 §5-2 의 *「두 축 p 를 나란히 인쇄」* 요구를 지키려고 **같은 표본·같은 쌍 집합**에서
      순서만 정규화 축으로 바꾼다. sigma20 이 없는 건(삼양 — 등록일 «직전» 11봉 / 등록일 포함 12봉)은 T2 표본에서 통째로 뺀다.
      부수로 `delta_norm = 1.0%p / median(sigma20)` 를 정규화 축에 직접 적용한 민감도도 인쇄한다.
  B-5 서로 다른 배정 수가 200,000 을 넘으면 시드 고정 200,000 표본(NULL_SEED=20260815).
      `V` 는 원 정의대로 «개수»로 둔다(정규화하지 않는다). 귀무에서 비교가능 쌍 수가 변하므로
      그 분포도 함께 인쇄한다.
  B-6 경과 거래일 `E` = `[D, 발행일]` 사이 거래일 수(양끝 포함, `daily_prices` 거래일 달력).
  B-7 한켐·코데즈컴바인은 두 글에 «다른 사이클»로 나온다 — 별개 관측으로 두되,
      두 번째 사이클을 뺀 10건 민감도를 반드시 인쇄한다.
  B-8 창3·창5 의 「D+k거래일」은 «그 종목의» 봉으로 센다(거래정지 대비).

라이브 트리 import 0건. DB 는 SELECT 만. `adj_factor` 산술 0건.
"""
from __future__ import annotations

import math
import statistics
import sys
from math import factorial
from pathlib import Path

import numpy as np
import psycopg2

from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

DELTA = 1.0            # %p (동결)
NULL_SEED = 20260815
NPERM = 200_000
PAIR_THRESHOLD = 40    # §5-1
END = "2026-08-28"     # DB 스냅샷 최대

# (종목, 코드, 등록일, 차수 N, 글, 발행일, 두번째 사이클?, 비고)
ITEMS = [
    ("이노테크",       "469610", "2026-08-13", 5, "post4", "2026-08-22", False, "매도만 수동(포함)"),
    ("한켐",           "457370", "2026-08-12", 4, "post4", "2026-08-22", False, ""),
    ("금호건설",       "002990", "2026-08-12", 3, "post4", "2026-08-22", False, "본문 날짜 모순(08-12 채택·동결)"),
    ("지투파워",       "388050", "2026-08-13", 2, "post4", "2026-08-22", False, ""),
    ("PS일렉트로닉스", "332570", "2026-08-13", 4, "post4", "2026-08-22", False, ""),
    ("코데즈컴바인",   "047770", "2026-08-19", 2, "post4", "2026-08-22", False, ""),
    ("혜인",           "003010", "2026-08-11", 2, "post5", "2026-08-29", False, "프리셋 Q1~Q3(비-HDR60)"),
    ("한국화장품제조", "003350", "2026-08-12", 4, "post5", "2026-08-29", False, ""),
    ("코데즈컴바인",   "047770", "2026-08-21", 3, "post5", "2026-08-29", True,  "같은 종목 2번째 사이클"),
    ("한켐",           "457370", "2026-08-20", 2, "post5", "2026-08-29", True,  "B-2 매도만 수동(포함)·2번째 사이클"),
    ("삼양바이오팜",   "0120G0", "2026-08-21", 1, "post5", "2026-08-29", False, "first_only 후보·등록일 직전 11봉(포함 12봉)"),
    ("광전자",         "017900", "2026-08-05", 4, "post5", "2026-08-29", False, ""),
]


def say(s=""):
    print(s)
    OUT.append(s)


# ── 통계량 ────────────────────────────────────────────────────────────────
def pairset(xs, delta):
    """|x_i - x_j| > delta 인 무순서 쌍을 (큰쪽 index, 작은쪽 index) 로 돌려준다."""
    ps, dropped = [], 0
    n = len(xs)
    for i in range(n):
        for j in range(i + 1, n):
            if abs(xs[i] - xs[j]) <= delta:
                dropped += 1
                continue
            ps.append((i, j) if xs[i] > xs[j] else (j, i))
    return ps, dropped


def statV(ns, ps):
    """V = 「X 가 큰 쪽의 N 이 더 작은」 쌍 수 · comp = N 이 서로 다른 비교가능 쌍 수."""
    V = comp = 0
    for h, l in ps:
        a, b = ns[h], ns[l]
        if a == b:
            continue
        comp += 1
        if a < b:
            V += 1
    return V, comp


def permute_null(ns, ps, nperm=NPERM, seed=NULL_SEED):
    """차수 다중집합을 무작위 재배정(관측과 «같은 크기»). numpy `default_rng(seed)` · 시드 고정."""
    base = np.array(ns, dtype=np.int16)
    rng = np.random.default_rng(seed)
    M = rng.permuted(np.tile(base, (nperm, 1)), axis=1)
    if not ps:
        z = np.zeros(nperm, dtype=np.int32)
        return z, z, nperm
    hi = np.array([h for h, _ in ps], dtype=np.int32)
    lo = np.array([l for _, l in ps], dtype=np.int32)
    A, B = M[:, hi], M[:, lo]
    V = (A < B).sum(axis=1)
    C = (A != B).sum(axis=1)
    return V, C, int((V == 0).sum())


def run_axis(title, ns, xs, delta, note=""):
    ps, dropped = pairset(xs, delta)
    v_obs, comp_obs = statV(ns, ps)
    vs, comps, zero = permute_null(ns, ps)
    p = float((vs <= v_obs).mean())
    mean_v = float(vs.mean())
    say(f"| {title} | {v_obs} | {comp_obs} | {dropped} | {mean_v:.2f} | **{p:.4f}** | "
        f"{zero/len(vs):.5f} | {float(comps.mean()):.2f} |")
    return dict(title=title, V=v_obs, comp=comp_obs, dropped=dropped, p=p,
                mean=mean_v, pzero=zero / len(vs), meancomp=float(comps.mean()), note=note)


def main():
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    say("# RESULTS_LADDER_TRANCHE_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_ladder_tranche.py` · 사전등록 `PREREG_LADDER_TRANCHE.md`(2026-08-22 동결) **1회 실행**")
    say(f"`delta` = {DELTA}%p · `NULL_SEED` = {NULL_SEED} · 순열 표본 {NPERM:,} · "
        f"판정 문턱 = 누적 비교가능 쌍 {PAIR_THRESHOLD}")
    say(f"DB 스냅샷 최대 = {END} · `adj_factor` 산술 0건\n")

    # 거래일 달력 (B-6)
    cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN '2026-07-01' AND %s "
                "ORDER BY date", (END,))
    cal = [r[0] for r in cur.fetchall()]

    # ── §1. 건별 원표 (§4-5 항목 4) ────────────────────────────────────────
    say("## §1. 건별 원표 — `(종목, 글, N, H, min_low, DD)` (§4-5 의무 인쇄 4)\n")
    say("`H` = 등록일 고가 · `DD` = 1 - min(low over 창) / H\n")
    say("| # | 종목 | 글 | N | 등록일 | H | 창3 봉수 / min_low / **DD3** | "
        "창5 봉수 / min_low / **DD5** | 창A 끝 / min_low / **DD_A** | 경과거래일 E | sigma20 | 비고 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|")

    rows = []
    for idx, (nm, code, d0, N, post, pub, second, memo) in enumerate(ITEMS, 1):
        pub_eff = min(pub, END)
        cur.execute("SELECT date, high, low FROM daily_prices WHERE stock_code=%s AND date >= %s "
                    "AND date <= %s ORDER BY date", (code, d0, END))
        bars = cur.fetchall()
        H = bars[0][1]
        w3 = bars[:3]
        w5 = bars[:5]
        wa = [b for b in bars if b[0] <= pub_eff]
        dd3 = 100 * (1 - min(b[2] for b in w3) / H)
        dd5 = 100 * (1 - min(b[2] for b in w5) / H)
        dda = 100 * (1 - min(b[2] for b in wa) / H)
        # 1회차 재현용: [D, 2026-08-21]
        w21 = [b for b in bars if b[0] <= "2026-08-21"]
        dd21 = 100 * (1 - min(b[2] for b in w21) / H) if w21 else float("nan")
        E = sum(1 for d in cal if d0 <= d <= pub_eff)
        # sigma20 (A-8/B-4)
        cur.execute("SELECT close FROM (SELECT date, close FROM daily_prices WHERE stock_code=%s "
                    "AND date < %s ORDER BY date DESC LIMIT 21) t", (code, d0))
        cl = [r[0] for r in cur.fetchall()][::-1]
        sig = statistics.stdev([math.log(cl[i] / cl[i - 1]) for i in range(1, len(cl))]) \
            if len(cl) >= 21 else None
        rows.append(dict(i=idx, nm=nm, code=code, d0=d0, N=N, post=post, pub=pub_eff,
                         second=second, memo=memo, H=H, dd3=dd3, dd5=dd5, dda=dda,
                         dd21=dd21, E=E, sig=sig,
                         l3=min(b[2] for b in w3), l5=min(b[2] for b in w5),
                         la=min(b[2] for b in wa), n3=len(w3), n5=len(w5), na=len(wa)))
        say(f"| {idx} | {nm} | {post} | **{N}** | {d0} | {H:,.0f} | "
            f"{len(w3)} / {min(b[2] for b in w3):,.0f} / **{dd3:.2f}%** | "
            f"{len(w5)} / {min(b[2] for b in w5):,.0f} / **{dd5:.2f}%** | "
            f"{pub_eff} / {min(b[2] for b in wa):,.0f} / **{dda:.2f}%** | {E} | "
            f"{'—' if sig is None else f'{sig:.4f}'} | {memo} |")

    say()
    say("- 1회차 재현행(창A 를 `[D, 2026-08-21]` 로 둔 post4 정의): " + " · ".join(
        f"{r['nm']} {r['dd21']:.2f}%" for r in rows if r["post"] == "post4"))

    ns_all = [r["N"] for r in rows]
    say(f"- 차수 다중집합 = {sorted(ns_all)} · 건수 **{len(ns_all)}**")
    from collections import Counter
    cnt = Counter(ns_all)
    distinct = factorial(len(ns_all))
    for m in cnt.values():
        distinct //= factorial(m)
    say(f"- 서로 다른 배정 수 = {len(ns_all)}! / prod(m_k!) = **{distinct:,}** "
        f"⇒ {'200,000 초과 ⇒ **시드 고정 표본**' if distinct > NPERM else '전수 가능'} (B-5)")
    say(f"- N 동률로 «원리적으로» 비교 불가한 쌍 = "
        f"**{sum(m*(m-1)//2 for m in cnt.values())}** / 전체 {len(ns_all)*(len(ns_all)-1)//2}")

    # 퍼짐 — 1회차 「잡음 띠」와 비교 (§2 재점검)
    v5 = sorted(r["dd5"] for r in rows)
    v4a = sorted(r["dd21"] for r in rows if r["post"] == "post4")
    say(f"- 창5 `DD` 정렬: " + " · ".join(f"{x:.2f}" for x in v5))
    say(f"- 창5 `DD` 범위 **{v5[0]:.2f}~{v5[-1]:.2f}** · 폭 **{v5[-1]-v5[0]:.2f}%p** "
        f"(1회차 창A 6값: {v4a[0]:.2f}~{v4a[-1]:.2f} · 폭 {v4a[-1]-v4a[0]:.2f}%p "
        f"⇒ 표본 {len(v5)/len(v4a):.1f}배에 범위 {(v5[-1]-v5[0])/(v4a[-1]-v4a[0]):.2f}배)")
    q5 = statistics.quantiles(v5, n=4, method="inclusive")
    q4 = statistics.quantiles(v4a, n=4, method="inclusive")
    say(f"- 창5 사분위 `Q1`={q5[0]:.2f} · `Q2`={q5[1]:.2f} · `Q3`={q5[2]:.2f} ⇒ "
        f"**IQR {q5[2]-q5[0]:.2f}%p** (1회차 창A IQR {q4[2]-q4[0]:.2f}%p) "
        f"— 띠는 «임의로 고른 구간이 아니라» 사분위다")

    # ── §2. 주 판정 + 창 민감도 (§4-5 의무 1·2·3) ─────────────────────────
    say()
    say("## §2. `V` · 순열 귀무 — 창3 · **창5(주)** · 창A (§4-5 의무 1~3)\n")
    say("| 축 | `V_obs` | 비교가능 쌍 | delta 로 버린 쌍 | 귀무 평균 `V` | **`p = P(V<=V_obs)`** | "
        "**`P(V=0)`** | 귀무 평균 비교가능 쌍 |")
    say("|---|---|---|---|---|---|---|---|")
    a3 = run_axis("창3 `[D,D+2]`", ns_all, [r["dd3"] for r in rows], DELTA)
    a5 = run_axis("**창5 `[D,D+4]` (주)**", ns_all, [r["dd5"] for r in rows], DELTA)
    aa = run_axis("창A `[D,발행일]`", ns_all, [r["dda"] for r in rows], DELTA)
    say()
    say(f"- 🔴 §1 의 부호 반전(1회차: 창3 나쁨 / 창5·창A 나음) 재현 여부 — "
        f"p(창3)={a3['p']:.4f} · p(창5)={a5['p']:.4f} · p(창A)={aa['p']:.4f} ⇒ "
        f"**{'재현' if (a3['p'] > 0.5 and a5['p'] < 0.5) else '재현되지 않음'}**")
    say(f"- `P(V=0)` (= 「공통 사다리」가 귀무에서 나올 확률, §0 재발 방지): "
        f"창3 {a3['pzero']:.5f} · 창5 {a5['pzero']:.5f} · 창A {aa['pzero']:.5f}")

    # ── §3. 판정 시점 게이트 (§5-1) ────────────────────────────────────────
    say()
    say("## §3. 판정 시점 게이트 (§5-1) — 누적 비교가능 쌍 >= 40 인가\n")
    say(f"- 창5(주) 비교가능 쌍 = **{a5['comp']}** · 문턱 **{PAIR_THRESHOLD}** ⇒ "
        f"**{'✅ 판정 가능' if a5['comp'] >= PAIR_THRESHOLD else '⛔ 보류(판정하지 않는다)'}**")
    say(f"- 1회차(post4 6건) 는 13쌍이었다. 이번 누적 12건.")
    if a5["comp"] >= PAIR_THRESHOLD:
        if a5["p"] < 0.05:
            say(f"- ⇒ **T1 지지 후보** (`p = {a5['p']:.4f} < 0.05`) — 단 T2·T3 를 통과해야 확정.")
        else:
            say(f"- ⇒ ⛔ **T1 불성립** (`p = {a5['p']:.4f} >= 0.05`).")
    else:
        say("- ⇒ 🔴 **보류.** 사전등록이 못 박은 대로 «판정하지 않는다». 값만 기록.")

    # ── §4. T2 (반증축 · 필수) ────────────────────────────────────────────
    say()
    say("## §4. T2 (반증축 · 필수) — `DD/sigma20` 정규화 축\n")
    say("B-4: sigma20 이 없는 건은 T2 표본에서 통째로 뺀다. 두 축을 **같은 표본**에서 나란히 낸다.\n")
    sub = [r for r in rows if r["sig"] is not None]
    drop = [r["nm"] for r in rows if r["sig"] is None]
    say(f"- T2 표본 **{len(sub)}건** (제외 {len(drop)}건: {', '.join(drop) if drop else '없음'})")
    ns_s = [r["N"] for r in sub]
    dd_s = [r["dd5"] for r in sub]
    nx_s = [r["dd5"] / (100 * r["sig"]) for r in sub]
    med_sig = statistics.median([r["sig"] for r in sub])
    say(f"- median(sigma20) = **{med_sig:.4f}** ⇒ 부수 민감도용 "
        f"`delta_norm` = {DELTA}%p / (100*sigma) = **{DELTA/(100*med_sig):.4f}**\n")
    say("| 축 | `V_obs` | 비교가능 쌍 | delta 로 버린 쌍 | 귀무 평균 `V` | **`p`** | `P(V=0)` | 귀무 평균 비교가능 쌍 |")
    say("|---|---|---|---|---|---|---|---|")
    ps_dd, drop_dd = pairset(dd_s, DELTA)
    v_o, c_o = statV(ns_s, ps_dd)
    vs_o, cs_o, z_o = permute_null(ns_s, ps_dd)
    p_o = float((vs_o <= v_o).mean())
    say(f"| 원축 `DD`(같은 표본) | {v_o} | {c_o} | {drop_dd} | {float(vs_o.mean()):.2f} | "
        f"**{p_o:.4f}** | {z_o/len(vs_o):.5f} | {float(cs_o.mean()):.2f} |")
    ps_n_same = [(h, l) if nx_s[h] > nx_s[l] else (l, h) for h, l in ps_dd]
    v_n, c_n = statV(ns_s, ps_n_same)
    vs_n, cs_n, z_n = permute_null(ns_s, ps_n_same)
    p_n = float((vs_n <= v_n).mean())
    say(f"| **정규화축 `DD/sigma20`(같은 쌍 집합)** | {v_n} | {c_n} | {drop_dd} | "
        f"{float(vs_n.mean()):.2f} | **{p_n:.4f}** | {z_n/len(vs_n):.5f} | {float(cs_n.mean()):.2f} |")
    dn = DELTA / (100 * med_sig)
    ps_n2, drop_n2 = pairset(nx_s, dn)
    v_n2, c_n2 = statV(ns_s, ps_n2)
    vs_n2, cs_n2, z_n2 = permute_null(ns_s, ps_n2)
    p_n2 = float((vs_n2 <= v_n2).mean())
    say(f"| 정규화축 (부수: `delta_norm` 직접 적용) | {v_n2} | {c_n2} | {drop_n2} | "
        f"{float(vs_n2.mean()):.2f} | **{p_n2:.4f}** | {z_n2/len(vs_n2):.5f} | "
        f"{float(cs_n2.mean()):.2f} |")
    say()
    if p_n < p_o:
        say(f"- ⇒ 정규화축 `p`({p_n:.4f}) **<** 원축 `p`({p_o:.4f}) ⇒ "
            "`PREREG_BUYLADDER.md` §3 **가설 B(밴드가 종목별 스케일 비례)** 쪽 지지.")
    else:
        say(f"- ⇒ 정규화축 `p`({p_n:.4f}) **>=** 원축 `p`({p_o:.4f}) ⇒ **가설 B 는 지지 없음.**")

    # ── §5. T3 (반증축 · 필수) ────────────────────────────────────────────
    say()
    say("## §5. T3 (반증축 · 필수) — 축을 「등록일부터 발행일까지 경과 거래일」로 바꾼다\n")
    say("B-3: 경과일은 %p 가 아니므로 동률 대역 = **정확히 같은 값만 제외**(delta_E = 0).\n")
    say("| 축 | `V_obs` | 비교가능 쌍 | 동률로 버린 쌍 | 귀무 평균 `V` | **`p`** | `P(V=0)` | 귀무 평균 비교가능 쌍 |")
    say("|---|---|---|---|---|---|---|---|")
    a_t3 = run_axis("T3 `경과 거래일 E`", ns_all, [float(r["E"]) for r in rows], 0.0)
    say()
    say("- 경과일 분포: " + " · ".join(f"{r['nm']}({r['post']}) {r['E']}" for r in rows))
    if a_t3["p"] < 0.05:
        say(f"- ⇒ 🔴 **T3 에서도 `p = {a_t3['p']:.4f} < 0.05`** ⇒ 사전등록대로 "
            "***`V` 는 사다리가 아니라 「오래 들고 있으면 차수가 는다」는 시간 효과를 재고 있다*** "
            "⇒ **T1 지지를 취소한다.**")
    else:
        say(f"- ⇒ T3 `p = {a_t3['p']:.4f} >= 0.05` ⇒ 시간 효과로 대체 설명되지 않는다"
            "(T1 취소 사유 없음).")

    # ── §6. B-7 민감도 — 2번째 사이클 제외 ────────────────────────────────
    say()
    say("## §6. 민감도 (B-7) — 같은 종목 2번째 사이클(한켐 post5 · 코데즈 post5) 제외\n")
    sub2 = [r for r in rows if not r["second"]]
    say(f"- 표본 **{len(sub2)}건** · 차수 다중집합 {sorted(r['N'] for r in sub2)}\n")
    say("| 축 | `V_obs` | 비교가능 쌍 | delta 로 버린 쌍 | 귀무 평균 `V` | **`p`** | `P(V=0)` | 귀무 평균 비교가능 쌍 |")
    say("|---|---|---|---|---|---|---|---|")
    ns2 = [r["N"] for r in sub2]
    s3 = run_axis("창3", ns2, [r["dd3"] for r in sub2], DELTA)
    s5 = run_axis("**창5(주)**", ns2, [r["dd5"] for r in sub2], DELTA)
    sa = run_axis("창A", ns2, [r["dda"] for r in sub2], DELTA)
    say()
    say(f"- 창5 비교가능 쌍 {s5['comp']} (< 문턱 {PAIR_THRESHOLD}) ⇒ 이 민감도만으로는 판정하지 않는다."
        if s5["comp"] < PAIR_THRESHOLD else
        f"- 창5 비교가능 쌍 {s5['comp']} (>= 문턱 {PAIR_THRESHOLD}).")

    # ── §7. 1회차(post4 6건) 재현 ─────────────────────────────────────────
    say()
    say("## §7. 1회차(post4 6건) 재현 — 동결문서 §0·§1 숫자가 나오는가\n")
    p4 = [r for r in rows if r["post"] == "post4"]
    ns4 = [r["N"] for r in p4]
    say("| 축 | `V_obs` | 비교가능 쌍 | delta 로 버린 쌍 | 귀무 평균 `V` | **`p`** | `P(V=0)` | 귀무 평균 비교가능 쌍 |")
    say("|---|---|---|---|---|---|---|---|")
    r3d0 = run_axis("창3 (delta=0 · 1회차 조건)", ns4, [r["dd3"] for r in p4], 0.0)
    r5d0 = run_axis("창5 (delta=0 · 1회차 조건)", ns4, [r["dd5"] for r in p4], 0.0)
    rAd0 = run_axis("창A=[D,08-21] (delta=0 · 1회차 조건)", ns4, [r["dd21"] for r in p4], 0.0)
    r5dd = run_axis("창5 (delta=1.0%p · 현행 규칙)", ns4, [r["dd5"] for r in p4], DELTA)
    say()
    say(f"- 동결 문서 §1 값: 창3 위반 **8** · 창5 위반 **4** · 창A 위반 **4** · 비교가능 **13** · "
        f"`P(<=관측)` 0.772 / 0.228 / 0.228")
    say(f"- 이번 재현: 창3 {r3d0['V']}/{r3d0['comp']} p={r3d0['p']:.3f} · "
        f"창5 {r5d0['V']}/{r5d0['comp']} p={r5d0['p']:.3f} · "
        f"창A {rAd0['V']}/{rAd0['comp']} p={rAd0['p']:.3f}")
    ok = (r3d0["V"] == 8 and r5d0["V"] == 4 and rAd0["V"] == 4 and r5d0["comp"] == 13)
    say(f"- ⇒ **{'✅ 재현됨' if ok else '🔴 재현되지 않음 — 아래 차이를 그대로 적는다'}**")

    say()
    say("### §7-1. 어긋난 자리 추적 — 「1회차의 창5 는 «잘려» 있었다」\n")
    say("1회차 실행일(2026-08-22) 의 DB 최신 봉은 **2026-08-21** 이었다. "
        "그래서 등록일이 늦은 건은 `[D, D+4거래일]` 이 5봉을 못 채우고 잘렸다.\n")
    say("| 종목 | 등록일 | 08-21 까지 확보 가능한 봉수 | 그때의 창5 min_low / `DD5` | "
        "지금(08-28) 창5 봉수 / min_low / `DD5` | 값이 바뀌었나 |")
    say("|---|---|---|---|---|---|")
    for r in p4:
        cur.execute("SELECT low FROM daily_prices WHERE stock_code=%s AND date >= %s "
                    "AND date <= '2026-08-21' ORDER BY date LIMIT 5", (r["code"], r["d0"]))
        old = [x[0] for x in cur.fetchall()]
        dd_old = 100 * (1 - min(old) / r["H"])
        changed = abs(dd_old - r["dd5"]) > 1e-9
        say(f"| {r['nm']} | {r['d0']} | {len(old)} | {min(old):,.0f} / **{dd_old:.2f}%** | "
            f"{r['n5']} / {r['l5']:,.0f} / **{r['dd5']:.2f}%** | "
            f"{'🔴 **예**' if changed else '아니오'} |")
    say()
    say("- ⇒ 🔑🔑 이 자리가 재현 실패의 «전부»다. 1회차에 창5 와 창A 가 같은 `V`(=4) 를 낸 것은 "
        "**두 창이 같은 결론을 준 게 아니라, 자료가 없어 두 창이 «같은 창»이었기 때문**이다.")

    say()
    say("### §7-2. 1회차 정의를 그대로 되살린 대조 (창5 를 08-21 로 절단)\n")
    say("| 축 | `V_obs` | 비교가능 쌍 | delta 로 버린 쌍 | 귀무 평균 `V` | **`p`** | `P(V=0)` | 귀무 평균 비교가능 쌍 |")
    say("|---|---|---|---|---|---|---|---|")
    dd5_trunc = []
    for r in p4:
        cur.execute("SELECT low FROM daily_prices WHERE stock_code=%s AND date >= %s "
                    "AND date <= '2026-08-21' ORDER BY date LIMIT 5", (r["code"], r["d0"]))
        dd5_trunc.append(100 * (1 - min(x[0] for x in cur.fetchall()) / r["H"]))
    r5tr = run_axis("창5 (08-21 절단 · delta=0)", ns4, dd5_trunc, 0.0)
    say()
    say(f"- 절단본 창5: `V` = **{r5tr['V']}** · `p` = **{r5tr['p']:.3f}** ⇒ "
        f"동결 문서의 «창5 위반 4 · p 0.228» 과 "
        f"**{'일치' if r5tr['V'] == 4 else '불일치'}**")

    # ── §8. P1~P3 (§5-3) ─────────────────────────────────────────────────
    say()
    say("## §8. 개별 예측 P1~P3 (§5-3 · 값 기록 · 기각 사유 아님)\n")
    p5 = [r for r in rows if r["post"] == "post5"]
    say("- **P1** 「저자가 체결 차수를 명시」: post5 항목 9건 중 차수 명시 **7건**"
        "(혜인2·한국화장품4·코데즈3·한켐2·삼양1·광전자4·레메디5) · "
        "미명시 = 한성기업(기존 건)·SK아이이테크놀로지(레그 없음). "
        "**DB 있는 신규 6건 기준 6/6 = 100%** ⇒ ✅ 성립(4번째 글 6/6 에 이어 2연속).")
    dd5s = sorted(r["dd5"] for r in p5)
    med5 = dd5s[len(dd5s) // 2] if len(dd5s) % 2 else (dd5s[len(dd5s)//2-1] + dd5s[len(dd5s)//2]) / 2
    say(f"- **P2** 「신규 건 `DD`(창5) 중앙값이 15~35%」: 값 = "
        + " · ".join(f"{r['nm']} {r['dd5']:.2f}%" for r in p5)
        + f" ⇒ 중앙값 **{med5:.2f}%** ⇒ **{'✅ 구간 안' if 15 <= med5 <= 35 else '❌ 구간 밖'}** "
          f"(1회차 중앙 23.53%)")
    say("- **P3** 「`first_only` 건이 >= 1건」: **삼양바이오팜(1차)** 1건 ⇒ ✅ 성립. "
        "🔴 단 저자가 *「이후 추가매수 중」* 이라 **미완결**이고, "
        "`RESULTS_RECONSTRUCT_POST5` §6 에서 L1·L2 는 사전등록 규칙(3건 미만 미룸)으로 판정 보류 "
        "— 단 「신규 건」의 읽기(N3)에 따라 판정 가능해질 수 있다.")

    (BASE / "RESULTS_LADDER_TRANCHE_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    print("\n[written] RESULTS_LADDER_TRANCHE_NUMBERS.md")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())

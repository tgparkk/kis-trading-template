# -*- coding: utf-8 -*-
"""매수 사다리 「체결 차수 ↔ 낙폭」 정렬 축 — **6번째 글 누적 재계산** (`LAD-T1`·`T2`·`T3` · `LAD-P1`~`P3`).

준거(전부 동결본 · 규칙 변경 0):
  · `PREREG_LADDER_TRANCHE.md` §4(정의)·§5(예측·결정규칙)
  · `PREREG_POST6.md` §2-4(δ 1.0%p · 창5 · 게이트 40 불변 · 41쌍 → 재계산 · T3 부호 감시 ·
    DB 최신 봉 명기 · B-1·B-7 승계 · `LAD-P1` 분모 병기) · §4 표 #21~#24
  · `RESULTS_LADDER_TRANCHE.md` §1(B-1~B-8 해석 결정) · §7(절단 창5 가짜 숫자 전례) · §8 · §10
  · `PREDECISION_2026-09-04_post6.md` PD-1(창A 종료 = 발행일 09-04 · 거래일) · PD-2(후속 2건 등록일 축 제외)
    · PD-3(재진입) · PD-9(봉수 실측) · PD-11(창5 절단) · PD-12
  · `INTAKE_2026-09-04_post6.md` §1(항목·차수) · §2-4(N 분포) · §5(이 축의 대상 표본)

🔴 이 스크립트는 **동결 산출물 생성기 `run_ladder_tranche.py` 를 «수정하지 않는다»**.
   통계 핵(`pairset`·`statV`·`permute_null`)과 표 행 포맷(`run_axis`)을 그대로 **import 해 재사용**하고,
   `ITEMS` 를 **확장한 새 목록**만 이 파일에서 정의한다 ⇒ 기존 12건의 계산 경로는 한 줄도 달라지지 않는다.

계산 «전»에 고정된 해석 결정 — **전부 승계, 신설 0**:
  B-1  창A 의 「글 발행일」 = 그 항목이 실린 글의 발행일. post4 = 2026-08-22(토) · post5 = 2026-08-29(토)
       ⇒ 각각 마지막 거래일 08-21 · 08-28 에서 끝난다. **post6 = 2026-09-04(금) = 거래일**이므로
       창A = `[D, 2026-09-04]` = **발행 당일 봉 «포함»**(PD-1).
  B-2  한켐(post5)은 §4-1 carve-out(매도 쪽만 수동) ⇒ 포함. 이번 글 `MANUAL` **0건**이라 새 판단 없음.
  B-3  δ 는 DD 축(%p)의 정의다. T3 축(경과 거래일)은 **정확히 같은 값만 제외**(delta_E = 0).
  B-4  T2 는 **같은 표본·같은 쌍 집합**에서 순서만 정규화 축으로 바꾼다. sigma20 없는 건은 통째로 제외
       (이번 표본에서 sigma20 결측 = post5 삼양바이오팜 1건 — 등록일 «직전» 11봉 / 등록일 포함 12봉).
       부수로 `delta_norm = 1.0%p / median(sigma20)` 직접 적용 민감도도 인쇄.
  B-5  서로 다른 배정이 200,000 을 넘으면 시드 고정 200,000 표본(`NULL_SEED` = 20260815 — 기존 값 그대로).
  B-6  경과 거래일 E = `[D, 발행일]` 거래일 수(양끝 포함 · `daily_prices` 거래일 달력).
  B-7  같은 종목 2번째 사이클은 별개 관측으로 두되 **제외 민감도를 필수 인쇄**
       (이번 누적: 한켐 post5 · 코데즈컴바인 post5 + **지투파워 post6 · 현대약품 post6** — PD-3).
  B-8  창3·창5 의 「D+k거래일」은 **그 종목의 봉**으로 센다.
  PD-2 「기존 건 후속」 2건(광전자·삼양바이오팜)은 **등록일 축 신규 분모에서 제외**(이중계상 금지)
       ⇒ 이 축의 신규 표본은 **10건**이고, 두 종목의 post5 행은 그대로 둔다.
  PD-11 창5 `[D, D+4거래일]` 절단(09-01 등록 2건) = **분모에 넣고** 가용 봉으로 DD5 를 계산 ·
       플래그 `P6-WIN5_TRUNC`·건수·봉수 의무 인쇄 · 절단 2건 **제외 민감도**를 `LAD-T1`·`T2`·`T3`·`LAD-P2`
       전부에 인쇄 · `P6-창5절단가드-A`(절단 건 / 이번 글 신규 건 ≥ 1/3 ⇒ ⛔) ·
       `P6-창5절단가드-B`(제외 민감도가 `LAD-T1` 판정을 뒤집으면 ⇒ ⛔) · 이번 값은 **「절단 시점 값」**.

🔴 라이브 채택 대상이 아니다(`PREREG.md` §0-2). 라이브 트리 import 0건 · DB 는 SELECT 만 ·
   `adj_factor` 산술 0건 · 새 예측을 만들지 않는다 · 값 보고 규칙을 바꾸지 않는다
   (모호하면 양쪽을 인쇄하고 「모호」라 적는다).
"""
from __future__ import annotations

import math
import statistics
import sys
from collections import Counter
from math import factorial
from pathlib import Path

import psycopg2

from run_tests import DSN

# 🔴 동결 산출물 생성기에서 **통계 핵과 표 포맷을 그대로** 가져온다(수정 금지 파일).
import run_ladder_tranche as LAD
from run_ladder_tranche import (
    DELTA,            # 1.0 %p (동결)
    ITEMS as ITEMS_BASE,   # 누적 12건 (post4 6 + post5 6) — 그대로
    NPERM,            # 200,000
    NULL_SEED,        # 20260815 — 기존 값 그대로
    PAIR_THRESHOLD,   # 40 (§5-1)
    pairset,
    permute_null,
    run_axis,
    statV,
)

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
LAD.OUT = OUT      # `run_axis` 가 쓰는 `say` 의 버퍼를 이 실행의 버퍼로 잇는다(포맷 재사용).

END = "2026-09-04"          # DB 스냅샷 최대 봉 (PD-1 · 실행 시 재확인)
PUB6 = "2026-09-04"         # 6번째 글 발행일 = 거래일 (B-1 · PD-1)
CUM_PAIRS_POST5 = 41        # `RESULTS_LADDER_TRANCHE.md` §0 — 누적 비교가능 쌍(창5)
POST5_T1_V, POST5_T1_P = 21, 0.5160     # post5 판정값 (나란히 인쇄용)
TRUNC5_MIN_BARS = 5         # 창5 = D + 4거래일 = 5봉
GUARD_A_NUM, GUARD_A_DEN = 1, 3         # `P6-창5절단가드-A` 문턱 1/3 (§1-6 6번 차용 고지 승계)

# (종목, 코드, 등록일, 차수 N, 글, 발행일, 두번째 사이클?, 비고)
# `INTAKE_2026-09-04_post6.md` §1 — 신규 10건(후속 2건 = 광전자·삼양바이오팜은 PD-2 로 제외).
ITEMS_POST6_NEW = [
    ("한라캐스트",     "125490", "2026-08-21", 5, "post6", PUB6, False,
     "라벨 SL·미완결(§4-1 은 MANUAL 만 제외)"),
    ("헥토파이낸셜",   "234340", "2026-08-28", 1, "post6", PUB6, False, "first_only"),
    ("아난티",         "025980", "2026-08-19", 1, "post6", PUB6, False, "first_only·미완결"),
    ("아이티센글로벌", "124500", "2026-08-20", 3, "post6", PUB6, False, ""),
    ("현대약품",       "004310", "2026-09-01", 2, "post6", PUB6, True,
     "재진입(07-31 글 #12 · 직전 등록일 미상)·창5 절단"),
    ("원익",           "032940", "2026-08-31", 3, "post6", PUB6, False, ""),
    ("쿠콘",           "294570", "2026-08-28", 1, "post6", PUB6, False, "first_only"),
    ("지투파워",       "388050", "2026-08-26", 3, "post6", PUB6, True,
     "재진입(post4 #4 08-13)·PRIOR_CYCLE_IN_WINDOW=1"),
    ("우리기술투자",   "041190", "2026-08-25", 4, "post6", PUB6, False,
     "04-01~08-04 봉 36/85(구멍 계열)"),
    ("비에이치",       "090460", "2026-09-01", 4, "post6", PUB6, False, "창5 절단"),
]
ITEMS = list(ITEMS_BASE) + ITEMS_POST6_NEW

FIRST_ONLY_POST6 = ["헥토파이낸셜", "아난티", "쿠콘"]   # `INTAKE` §2-1 (차수 N = 1)
PRIOR_CYCLE_FLAG = {"지투파워": 1, "현대약품": 0}       # `P6-PRIOR_CYCLE_IN_WINDOW` (PD-3 표)

HDR = ("| 축 | `V_obs` | 비교가능 쌍 | 버린 쌍 | 귀무 평균 `V` | **`p = P(V<=V_obs)`** | "
       "`P(V=0)` | 귀무 평균 비교가능 쌍 |")
SEP = "|---|---|---|---|---|---|---|---|"


def say(s=""):
    print(s)
    OUT.append(s)


def median(xs):
    ys = sorted(xs)
    n = len(ys)
    return ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2


def guard_a_fires(n_trunc, n_new):
    """`P6-창5절단가드-A` (PD-11 3번): 절단 건 / **이번 글 신규 건** >= 1/3 이면 발동(판정 불가)."""
    return n_trunc / n_new >= GUARD_A_NUM / GUARD_A_DEN


def verdict_t1(res):
    """`LAD-T1` 문언(§5-2) 그대로: 게이트 40 이상 ∧ p < 0.05 이면 지지 후보, 아니면 불성립/보류."""
    if res["comp"] < PAIR_THRESHOLD:
        return "보류"
    return "지지후보" if res["p"] < 0.05 else "불성립"


def main():
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    say("# RESULTS_LADDER_TRANCHE_POST6_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_ladder_tranche_post6.py` · 통계 핵·표 포맷은 `run_ladder_tranche.py` 에서 import "
        "(그 파일은 **수정하지 않았다**)")
    say("사전등록 `PREREG_LADDER_TRANCHE.md`(2026-08-22 동결) · `PREREG_POST6.md` §2-4·§4 #21~#24 · "
        "해석 결정 `RESULTS_LADDER_TRANCHE.md` §1 B-1~B-8 + `PREDECISION_2026-09-04_post6.md` PD-1·PD-2·PD-3·PD-11")
    say(f"`delta` = {DELTA}%p · `NULL_SEED` = {NULL_SEED} · 순열 표본 {NPERM:,} · "
        f"판정 문턱 = 누적 비교가능 쌍 {PAIR_THRESHOLD} — **셋 다 동결 그대로 손대지 않았다**")

    cur.execute("SELECT max(date) FROM daily_prices")
    db_max = cur.fetchone()[0]
    say(f"**DB 최신 봉 = `{db_max}`** (스크립트 `END` = {END} · 일치 "
        f"{'✅' if str(db_max) == END else '🔴 불일치 — 아래 값 전부 무효'}) · "
        f"`adj_factor` 산술 0건 · 라이브 트리 import 0건")
    say(f"**창 종료 {PUB6} = 발행 당일 봉 «포함»** (B-1 · PD-1 — 발행일이 거래일이다. "
        "post4·post5 는 토요일 발행이라 마지막 거래일에서 끝났다)")
    say("🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2) — 이 산출물은 기록이지 전략 후보가 아니다.")
    say("🔵 라벨 접두(§0-3 규약): 이 문서의 `T1`·`T2`·`T3`·`P1`~`P3` 은 전부 **`LAD-`** 축이다"
        "(`PREREG_LADDER_TRANCHE.md` §5). 이 글에서 새로 쓰는 플래그·가드는 **`P6-`** 접두를 단다.\n")

    # 거래일 달력 (B-6)
    cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN '2026-07-01' AND %s "
                "ORDER BY date", (END,))
    cal = [r[0] for r in cur.fetchall()]

    # ── §1. 건별 원표 ─────────────────────────────────────────────────────
    say("## §1. 건별 원표 — `(종목, 글, N, H, min_low, DD)` (§4-5 의무 인쇄 4)\n")
    say("`H` = 등록일 고가 · `DD` = 1 - min(low over 창) / H · 창5 = `[D, D+4거래일]`(그 종목의 봉 · B-8)\n")
    say("| # | 종목 | 글 | N | 등록일 | H | 창3 봉수 / min_low / **DD3** | "
        "창5 봉수 / min_low / **DD5** | 창A 끝 / min_low / **DD_A** | 경과거래일 E | sigma20 | "
        "`P6-WIN5_TRUNC` | 비고 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|")

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
        trunc5 = 1 if len(w5) < TRUNC5_MIN_BARS else 0
        E = sum(1 for d in cal if d0 <= d <= pub_eff)
        cur.execute("SELECT close FROM (SELECT date, close FROM daily_prices WHERE stock_code=%s "
                    "AND date < %s ORDER BY date DESC LIMIT 21) t", (code, d0))
        cl = [r[0] for r in cur.fetchall()][::-1]
        sig = statistics.stdev([math.log(cl[i] / cl[i - 1]) for i in range(1, len(cl))]) \
            if len(cl) >= 21 else None
        rows.append(dict(i=idx, nm=nm, code=code, d0=d0, N=N, post=post, pub=pub_eff,
                         second=second, memo=memo, H=H, dd3=dd3, dd5=dd5, dda=dda, E=E, sig=sig,
                         l3=min(b[2] for b in w3), l5=min(b[2] for b in w5),
                         la=min(b[2] for b in wa), n3=len(w3), n5=len(w5), na=len(wa),
                         trunc5=trunc5))
        say(f"| {idx} | {nm} | {post} | **{N}** | {d0} | {H:,.0f} | "
            f"{len(w3)} / {min(b[2] for b in w3):,.0f} / **{dd3:.2f}%** | "
            f"{len(w5)} / {min(b[2] for b in w5):,.0f} / **{dd5:.2f}%** | "
            f"{pub_eff} / {min(b[2] for b in wa):,.0f} / **{dda:.2f}%** | {E} | "
            f"{'—' if sig is None else f'{sig:.4f}'} | {'**1**' if trunc5 else '0'} | {memo} |")

    new6 = [r for r in rows if r["post"] == "post6"]
    old = [r for r in rows if r["post"] != "post6"]
    trunc = [r for r in new6 if r["trunc5"]]

    say()
    say(f"- 표본 **{len(rows)}건** = 기존 누적 {len(old)}(post4 6 + post5 6) + **6번째 글 신규 {len(new6)}건**. "
        f"「기존 건 후속」 2건(광전자·삼양바이오팜)은 **PD-2 로 등록일 축 신규 분모 밖** — "
        "두 종목의 post5 행(#12·#11)은 그대로 둔다(이중계상 금지).")
    say(f"- 6번째 글 신규 10건의 차수 다중집합 = {sorted(r['N'] for r in new6)} "
        f"(`INTAKE` §2-4 분포 1:3 · 2:1 · 3:3 · 4:2 · 5:1 과 대조)")

    # ── §1-1. 창5 절단 (PD-11) ───────────────────────────────────────────
    say()
    say("### §1-1. 창5 절단 — `P6-WIN5_TRUNC` (PD-11 · 이 계열 최초)\n")
    say(f"- **절단 건수 = {len(trunc)}** / 이번 글 신규 {len(new6)}건 · "
        + (" · ".join(f"{r['nm']}({r['d0']} 등록 · 창5 **{r['n5']}봉** / 규정 {TRUNC5_MIN_BARS}봉 · "
                      f"DD5 = **{r['dd5']:.2f}%**)" for r in trunc) if trunc else "해당 없음"))
    say(f"- 이 값들은 **「절단 시점 값」**이다(PD-11 4번) — 다음 글에서 창5 가 완전해지면 «대체»한다.")
    say(f"- 절단 건은 **분모에 넣는다**(값을 보고 빼지 않는다 · PD-11 1번). 제외 민감도는 §6.")
    ga = len(trunc) / len(new6)
    say(f"- **`P6-창5절단가드-A`**(절단 건 / **이번 글 신규 건** ≥ 1/3 ⇒ ⛔ 판정 불가): "
        f"**{len(trunc)}/{len(new6)} = {100*ga:.1f}%** vs 문턱 {GUARD_A_NUM}/{GUARD_A_DEN} = "
        f"{100*GUARD_A_NUM/GUARD_A_DEN:.1f}% ⇒ "
        f"**{'⛔ 발동' if guard_a_fires(len(trunc), len(new6)) else '미발동'}**")
    say(f"  - 참고 병기(누적 쌍 기준 분모): 절단 {len(trunc)} / 누적 {len(rows)}건 = "
        f"{100*len(trunc)/len(rows):.1f}% — 「참고」다. 판정 분모는 **이번 글 신규 건**(§1-6 과 같은 분모).")
    say(f"  - 문턱 1/3 은 `REC-Y3` 에서 **차용**한 값이다(`PREREG_POST6.md` §1-6 6번 고지 승계) — "
        "절단 비율에 대해 검증된 값이 아니다.")
    say("- **`P6-창5절단가드-B`**(절단 2건 제외 민감도가 `LAD-T1` 판정을 뒤집으면 ⇒ ⛔ 「판정 불가(창5 절단 의존)」): §6 에서 판정.")
    say("- 🔑 전례: `RESULTS_LADDER_TRANCHE.md` §7 — 1회차의 창5 는 «잘려» 있었고 그 「위반 4」는 "
        "실재하지 않는 값이었다. **그래서 이번엔 절단을 플래그로 드러내고 제외 민감도를 함께 낸다.**")

    # ── §1-2. PD-9 재확인 ────────────────────────────────────────────────
    say()
    say("### §1-2. PD-9 재확인(참고) — 신규 10건의 `[D-19, D]` 창 봉수\n")
    say("PD-9 가 「20/20 전 건」이라 적었고 *「계산 단계에서 재확인」* 하라 했다. "
        "이 축의 판정에는 쓰이지 않는다(`P6-절단가드-A` 는 선정·등록일 축의 가드다 — 이름 분리 PD-11 3번).\n")
    say("| 종목 | 등록일 | 창 시작(달력 D-19) | 그 종목 봉수 / 20 |")
    say("|---|---|---|---|")
    short20 = 0
    for r in new6:
        cur.execute("SELECT min(date) FROM (SELECT DISTINCT date FROM daily_prices "
                    "WHERE date <= %s ORDER BY date DESC LIMIT 20) t", (r["d0"],))
        w_start = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s",
                    (r["code"], w_start, r["d0"]))
        nb = cur.fetchone()[0]
        if nb < 20:
            short20 += 1
        say(f"| {r['nm']} | {r['d0']} | {w_start} | {nb} / 20 |")
    say()
    say(f"- 20봉 미만 = **{short20}건** ⇒ PD-9 의 「분자 0」과 "
        f"**{'일치 ✅' if short20 == 0 else '🔴 불일치 — 그대로 적는다'}**")

    # ── §1-3. 배정 수 · 동률 쌍 ──────────────────────────────────────────
    ns_all = [r["N"] for r in rows]
    cnt = Counter(ns_all)
    distinct = factorial(len(ns_all))
    for m in cnt.values():
        distinct //= factorial(m)
    say()
    say("### §1-3. 귀무 배정 수 · 원리적 비교 불가 쌍\n")
    say(f"- 차수 다중집합 = {sorted(ns_all)} · 건수 **{len(ns_all)}**")
    say(f"- 서로 다른 배정 수 = {len(ns_all)}! / prod(m_k!) = **{distinct:,}** ⇒ "
        f"{'200,000 초과 ⇒ **시드 고정 표본**' if distinct > NPERM else '전수 가능'} (B-5)")
    say(f"- N 동률로 «원리적으로» 비교 불가한 쌍 = **{sum(m*(m-1)//2 for m in cnt.values())}** / "
        f"전체 {len(ns_all)*(len(ns_all)-1)//2}")

    # ── §1-4. 창5 DD 퍼짐 ────────────────────────────────────────────────
    v5 = sorted(r["dd5"] for r in rows)
    q5 = statistics.quantiles(v5, n=4, method="inclusive")
    say()
    say("### §1-4. 창5 `DD` 퍼짐 (계열 승계 · 「잡음 띠」 점검)\n")
    say("- 정렬: " + " · ".join(f"{x:.2f}" for x in v5))
    say(f"- 범위 **{v5[0]:.2f}~{v5[-1]:.2f}** · 폭 **{v5[-1]-v5[0]:.2f}%p** · "
        f"사분위 `Q1`={q5[0]:.2f} · `Q2`={q5[1]:.2f} · `Q3`={q5[2]:.2f} ⇒ **IQR {q5[2]-q5[0]:.2f}%p** "
        f"(post5 누적 12건: 범위 9.79%p · IQR 3.25%p)")

    # ── §2. 주 판정 (§4-5 의무 1~3) ──────────────────────────────────────
    say()
    say("## §2. `LAD-T1` 주 판정 + 창 민감도 — 창3 · **창5(주)** · 창A (§4-5 의무 1~3)\n")
    say(HDR)
    say(SEP)
    a3 = run_axis("창3 `[D,D+2]`", ns_all, [r["dd3"] for r in rows], DELTA)
    a5 = run_axis("**창5 `[D,D+4]` (주)**", ns_all, [r["dd5"] for r in rows], DELTA)
    aa = run_axis("창A `[D,발행일]`", ns_all, [r["dda"] for r in rows], DELTA)
    say()
    say(f"- **누적 비교가능 쌍(창5) = {a5['comp']}** · post5 누적 **{CUM_PAIRS_POST5}** ⇒ "
        f"**신규 쌍 = {a5['comp'] - CUM_PAIRS_POST5}** (「41쌍 → 재계산」 · `PREREG_POST6.md` §2-4)")
    say(f"- post5 값 나란히: `V` = {POST5_T1_V} / {CUM_PAIRS_POST5} · `p` = {POST5_T1_P:.4f} "
        f"⇒ 이번 `V` = {a5['V']} / {a5['comp']} · `p` = **{a5['p']:.4f}**")
    say(f"- `P(V=0)`(§4-5 의무 2 · 「공통 사다리」가 귀무에서 나올 확률): "
        f"창3 {a3['pzero']:.5f} · 창5 {a5['pzero']:.5f} · 창A {aa['pzero']:.5f}")
    say(f"- §1 의 부호 반전(1회차: 창3 나쁨 / 창5·창A 나음) 재현 여부 — "
        f"p(창3)={a3['p']:.4f} · p(창5)={a5['p']:.4f} · p(창A)={aa['p']:.4f} ⇒ "
        f"**{'재현' if (a3['p'] > 0.5 and a5['p'] < 0.5) else '재현되지 않음'}**")

    # ── §3. 판정 시점 게이트 ─────────────────────────────────────────────
    say()
    say("## §3. 판정 — 게이트(§5-1 누적 비교가능 쌍 >= 40) · `LAD-T1`(§5-2)\n")
    say(f"- 창5(주) 비교가능 쌍 = **{a5['comp']}** · 문턱 **{PAIR_THRESHOLD}** ⇒ "
        f"**{'게이트 열림(판정한다)' if a5['comp'] >= PAIR_THRESHOLD else '⛔ 보류(판정하지 않는다)'}**")
    v1 = verdict_t1(a5)
    if v1 == "보류":
        say("- ⇒ 🔴 **보류.** 사전등록이 못 박은 대로 «판정하지 않는다». 값만 기록.")
    elif v1 == "지지후보":
        say(f"- ⇒ **`LAD-T1` 지지 후보** (`p` = {a5['p']:.4f} < 0.05) — T2·T3 를 통과해야 확정.")
    else:
        say(f"- ⇒ ⛔ **`LAD-T1` 불성립** (`p` = {a5['p']:.4f} >= 0.05). "
            "***차수는 낙폭에 대해 무작위 배정과 구별되지 않는다.***")
    say(f"- 계열: 1회차(post4 6건) 13쌍 → post5 누적(12건) {CUM_PAIRS_POST5}쌍 · `p` {POST5_T1_P:.4f} ⛔ → "
        f"이번(22건) {a5['comp']}쌍 · `p` {a5['p']:.4f} {'⛔' if v1 == '불성립' else ''}")

    # ── §4. T2 ───────────────────────────────────────────────────────────
    say()
    say("## §4. `LAD-T2` (반증축 · 필수) — `DD/sigma20` 정규화\n")
    sub = [r for r in rows if r["sig"] is not None]
    drop = [r["nm"] for r in rows if r["sig"] is None]
    say(f"B-4: sigma20 없는 건은 T2 표본에서 통째로 제외. **표본 {len(sub)}건** "
        f"(제외 {len(drop)}건: {', '.join(drop) if drop else '없음'} — "
        "삼양바이오팜은 등록일 **직전 11봉 / 등록일 포함 12봉**이라 21종가를 못 채운다).\n")
    ns_s = [r["N"] for r in sub]
    dd_s = [r["dd5"] for r in sub]
    nx_s = [r["dd5"] / (100 * r["sig"]) for r in sub]
    med_sig = statistics.median([r["sig"] for r in sub])
    say(f"- median(sigma20) = **{med_sig:.4f}** ⇒ 부수 민감도용 `delta_norm` = "
        f"{DELTA}%p / (100*sigma) = **{DELTA/(100*med_sig):.4f}**\n")
    say(HDR)
    say(SEP)
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
        f"{float(vs_n2.mean()):.2f} | **{p_n2:.4f}** | {z_n2/len(vs_n2):.5f} | {float(cs_n2.mean()):.2f} |")
    say()
    if p_n < p_o:
        say(f"- ⇒ 정규화축 `p`({p_n:.4f}) **<** 원축 `p`({p_o:.4f}) ⇒ 문언상 "
            "`PREREG_BUYLADDER.md` §3 **가설 B(밴드가 종목별 스케일 비례)** 쪽. "
            "🔴 **부호뿐이다** — 차이 자체는 검정되지 않았다(post5 §4 단서 승계).")
    else:
        say(f"- ⇒ 정규화축 `p`({p_n:.4f}) **>=** 원축 `p`({p_o:.4f}) ⇒ **가설 B 는 지지 없음.**")
    say(f"- post5 값 나란히: 원축 0.6767 · 정규화축 0.5562 · 부수 0.5545 (표본 11건)")

    # ── §5. T3 ───────────────────────────────────────────────────────────
    say()
    say("## §5. `LAD-T3` (반증축 · 필수) — 축을 「등록일 → 발행일 경과 거래일」로\n")
    say("B-3: 경과일은 %p 가 아니므로 동률 대역 = **정확히 같은 값만 제외**(delta_E = 0).\n")
    say(HDR)
    say(SEP)
    a_t3 = run_axis("T3 `경과 거래일 E`", ns_all, [float(r["E"]) for r in rows], 0.0)
    say()
    say("- 경과일 분포: " + " · ".join(f"{r['nm']}({r['post']}) {r['E']}" for r in rows))
    if a_t3["p"] < 0.05:
        say(f"- ⇒ 🔴🔴 **T3 `p` = {a_t3['p']:.4f} < 0.05** ⇒ 사전등록(§5-2)대로 "
            "***`V` 는 사다리가 아니라 「오래 들고 있으면 차수가 는다」는 시간 효과를 재고 있다*** ⇒ "
            "**`LAD-T1` 지지를 취소한다(영구).**")
    else:
        say(f"- ⇒ T3 `p` = {a_t3['p']:.4f} >= 0.05 ⇒ 시간 효과로 대체 설명되지 않는다(T1 취소 사유 없음).")
    say(f"- **부호 감시**(`RESULTS_LADDER_TRANCHE.md` §10 승계 · post5 T3 `p` = 0.2008 < 원축 0.5160): "
        f"이번 T3 `p` = **{a_t3['p']:.4f}** vs 창5 원축 `p` = **{a5['p']:.4f}** ⇒ "
        f"T3 가 원축보다 **{'낮다 — 부호 유지' if a_t3['p'] < a5['p'] else '낮지 않다 — 부호 유지되지 않음'}**. "
        "부호가 유지되면 ***「차수는 낙폭이 아니라 보유 기간을 따라간다」*** 쪽이 유일한 살아있는 설명이 된다. "
        "`p < 0.05` 로 내려가면 **T1 은 영구 취소**(이번 판정은 위 줄).")

    # ── §6. 민감도 — 창5 절단 2건 제외 (PD-11 2번) ───────────────────────
    say()
    say("## §6. 민감도 (PD-11 2번) — **창5 절단 2건 제외** (`LAD-T1`·`T2`·`T3`·`LAD-P2` 전부)\n")
    sub_t = [r for r in rows if not r["trunc5"]]
    say(f"- 제외: {', '.join(r['nm'] for r in trunc) if trunc else '없음'} ⇒ 표본 **{len(sub_t)}건**\n")
    say(HDR)
    say(SEP)
    ns_t = [r["N"] for r in sub_t]
    t3x = run_axis("창3", ns_t, [r["dd3"] for r in sub_t], DELTA)
    t5x = run_axis("**창5(주)**", ns_t, [r["dd5"] for r in sub_t], DELTA)
    tax = run_axis("창A", ns_t, [r["dda"] for r in sub_t], DELTA)
    sub_t_sig = [r for r in sub_t if r["sig"] is not None]
    ns_ts = [r["N"] for r in sub_t_sig]
    dd_ts = [r["dd5"] for r in sub_t_sig]
    nx_ts = [r["dd5"] / (100 * r["sig"]) for r in sub_t_sig]
    ps_ts, drop_ts = pairset(dd_ts, DELTA)
    v_to, c_to = statV(ns_ts, ps_ts)
    vs_to, cs_to, z_to = permute_null(ns_ts, ps_ts)
    p_to = float((vs_to <= v_to).mean())
    say(f"| T2 원축 `DD`(sigma20 있는 {len(sub_t_sig)}건) | {v_to} | {c_to} | {drop_ts} | "
        f"{float(vs_to.mean()):.2f} | **{p_to:.4f}** | {z_to/len(vs_to):.5f} | {float(cs_to.mean()):.2f} |")
    ps_tn = [(h, l) if nx_ts[h] > nx_ts[l] else (l, h) for h, l in ps_ts]
    v_tn, c_tn = statV(ns_ts, ps_tn)
    vs_tn, cs_tn, z_tn = permute_null(ns_ts, ps_tn)
    p_tn = float((vs_tn <= v_tn).mean())
    say(f"| T2 정규화축 `DD/sigma20`(같은 쌍 집합) | {v_tn} | {c_tn} | {drop_ts} | "
        f"{float(vs_tn.mean()):.2f} | **{p_tn:.4f}** | {z_tn/len(vs_tn):.5f} | {float(cs_tn.mean()):.2f} |")
    t3e = run_axis("T3 `경과 거래일 E`(delta_E = 0)", ns_t, [float(r["E"]) for r in sub_t], 0.0)
    say()
    v1x = verdict_t1(t5x)
    say(f"- 제외본 창5: `V` = {t5x['V']} / {t5x['comp']} · `p` = **{t5x['p']:.4f}** · 게이트 "
        f"{t5x['comp']} {'>=' if t5x['comp'] >= PAIR_THRESHOLD else '<'} {PAIR_THRESHOLD} ⇒ 판정 **{v1x}**")
    say(f"- 주 판정 **{v1}** ↔ 절단 제외 **{v1x}** ⇒ **`P6-창5절단가드-B` "
        f"{'⛔ 발동 — 「판정 불가(창5 절단 의존)」' if v1x != v1 else '미발동(판정이 뒤집히지 않는다)'}**")
    say(f"- T2 부호: 제외본 정규화 `p`({p_tn:.4f}) vs 원축 `p`({p_to:.4f}) ⇒ "
        f"**{'정규화가 낮다(주 판정과 같은 부호)' if p_tn < p_to else '정규화가 낮지 않다'}** "
        f"(주 판정: {p_n:.4f} vs {p_o:.4f} ⇒ {'정규화가 낮다' if p_n < p_o else '정규화가 낮지 않다'}) ⇒ "
        f"**{'갈리지 않는다' if (p_tn < p_to) == (p_n < p_o) else '🔴 갈린다 — 「절단 의존」으로 적는다'}**")
    say(f"- T3: 제외본 `p` = **{t3e['p']:.4f}** vs 주 판정 `p` = **{a_t3['p']:.4f}** ⇒ "
        f"0.05 문턱 기준 **{'갈리지 않는다' if (t3e['p'] < 0.05) == (a_t3['p'] < 0.05) else '🔴 갈린다'}**")
    say(f"- 창3·창A 도 함께: 창3 `p` {t3x['p']:.4f} · 창A `p` {tax['p']:.4f}")
    say("- (`LAD-P2` 의 절단 제외 값은 §8 에 인쇄한다.)")

    # ── §7. 민감도 — 2번째 사이클 제외 (B-7 + PD-3) ──────────────────────
    say()
    say("## §7. 민감도 (B-7 + PD-3) — **같은 종목 2번째 사이클 제외**\n")
    sub2 = [r for r in rows if not r["second"]]
    excl2 = [r for r in rows if r["second"]]
    say("- 제외 대상: " + " · ".join(f"{r['nm']}({r['post']} · {r['d0']})" for r in excl2)
        + f" ⇒ 표본 **{len(sub2)}건**")
    say(f"- **`P6-PRIOR_CYCLE_IN_WINDOW`**(PD-3 · `[D-19, D]` 창 안에 자기 직전 사이클 등록일) 건수 = "
        f"**{sum(PRIOR_CYCLE_FLAG.values())}** / 이번 글 재진입 {len(PRIOR_CYCLE_FLAG)}건 — "
        + " · ".join(f"{k} = **{v}**" for k, v in PRIOR_CYCLE_FLAG.items())
        + " (현대약품은 직전 글 발행 07-31 < 창 시작이라 **구성상 0** · 「직전 등록일 미상」 병기)")
    say("- 🔑 지투파워는 1차 사이클(post4 08-13 · N=2)이 **표본 안**에 있고, 현대약품은 1차 사이클이 "
        "**표본 밖**(07-31 글 · 등록일 미명시)이다. 제외 민감도는 두 건 다 뺀다(PD-3 2번 · B-7).\n")
    say(HDR)
    say(SEP)
    ns2 = [r["N"] for r in sub2]
    s3 = run_axis("창3", ns2, [r["dd3"] for r in sub2], DELTA)
    s5 = run_axis("**창5(주)**", ns2, [r["dd5"] for r in sub2], DELTA)
    sa = run_axis("창A", ns2, [r["dda"] for r in sub2], DELTA)
    s_t3 = run_axis("T3 `경과 거래일 E`(delta_E = 0)", ns2, [float(r["E"]) for r in sub2], 0.0)
    say()
    v2x = verdict_t1(s5)
    say(f"- 제외본 창5 비교가능 쌍 {s5['comp']} "
        f"({'>=' if s5['comp'] >= PAIR_THRESHOLD else '<'} 문턱 {PAIR_THRESHOLD}) ⇒ 판정 **{v2x}**")
    say(f"- 주 판정 **{v1}** ↔ 재진입 제외 **{v2x}** ⇒ "
        f"**{'🔴 「재진입 의존」 — 어느 쪽도 지지로 선언하지 않는다(PD-3 2번)' if v2x != v1 and v2x != '보류' else '판정이 갈리지 않는다' if v2x == v1 else '제외본은 게이트 미달이라 이 민감도만으로 판정하지 않는다'}**")
    say(f"- T3 제외본 `p` = {s_t3['p']:.4f} (주 판정 {a_t3['p']:.4f}) · 창3 {s3['p']:.4f} · 창A {sa['p']:.4f}")

    # ── §8. LAD-P1 ~ P3 ──────────────────────────────────────────────────
    say()
    say("## §8. 개별 예측 `LAD-P1`~`P3` (§5-3 · **값 기록 · 기각 사유 아님**)\n")
    say("- **`LAD-P1`** 「저자가 체결 차수를 명시」 — 6번째 글 **항목 12건 중 차수 명시 12건**"
        "(`INTAKE` §2-4). 그중 「기존 건 후속」 2건(광전자·삼양바이오팜)은 PD-2 로 신규 분모 밖. "
        f"⇒ **분모 정의 = 「DB 있는 신규 건」 = {len(new6)}건 ⇒ {len(new6)}/{len(new6)} = 100%** "
        "(코드 12/12 DB 존재 · post5 레메디형 결손 0) ⇒ ✅ **성립 · 3글 연속**"
        "(post4 6/6 → post5 6/6 → post6 10/10).")
    dd5_new = [r["dd5"] for r in new6]
    med_new = median(dd5_new)
    say(f"- **`LAD-P2`** 「신규 건 `DD`(창5) 중앙값이 15~35%」 — 값 = "
        + " · ".join(f"{r['nm']} {r['dd5']:.2f}%" for r in new6)
        + f" ⇒ 중앙값 **{med_new:.2f}%** ⇒ **{'✅ 구간 안' if 15 <= med_new <= 35 else '❌ 구간 밖'}** "
          f"(1회차 23.53% · post5 20.34%)")
    dd5_nt = [r["dd5"] for r in new6 if not r["trunc5"]]
    med_nt = median(dd5_nt)
    say(f"  - 절단 2건 제외(PD-11 2번): {len(dd5_nt)}건 중앙값 **{med_nt:.2f}%** ⇒ "
        f"**{'✅ 구간 안' if 15 <= med_nt <= 35 else '❌ 구간 밖'}** ⇒ "
        f"**{'갈리지 않는다' if (15 <= med_new <= 35) == (15 <= med_nt <= 35) else '🔴 갈린다 — 「절단 의존」'}**")
    say(f"- **`LAD-P3`** 「`first_only`(1차만 체결) 건 >= 1」 — 6번째 글 **{len(FIRST_ONLY_POST6)}건**"
        f"({' · '.join(FIRST_ONLY_POST6)} · 전부 차수 N = 1) ⇒ ✅ **성립** "
        "(post4 0건 → post5 1건(삼양) → post6 3건). "
        "🔴 삼양바이오팜의 누적 `first_only` 지위는 **PD-12 (가) as-of-post5 유지**이며 그 민감도는 "
        "`REC-`/`P6-L` 축 산출물이 낸다 — 이 축은 「건 수」만 기록한다.")

    # ── §9. 모호 지점·한계 ───────────────────────────────────────────────
    say()
    say("## §9. 모호 지점 (양쪽 인쇄 · 「모호」 표기) · 한계\n")
    say("1. **창5 절단 2건**(현대약품·비에이치) — 「절단 시점 값」이다. 분모 포함(주)/제외(민감도) "
        "**양쪽 인쇄**했다(§1-1·§6). 가드-A 산술 미발동 · 가드-B 판정은 §6.")
    say("2. **재진입 2건**(지투파워·현대약품) — 분모 포함(주)/제외(민감도) 양쪽 인쇄(§7). "
        "현대약품의 직전 사이클 등록일은 **미상**이라 `P6-PRIOR_CYCLE_IN_WINDOW` 가 «구성상» 0 이다"
        "(관측이 0 인 것과 다르다).")
    say("3. **한라캐스트는 라벨 `SL`**, 미완결 4건(한라캐스트·아난티·지투파워·우리기술투자)도 표본에 있다 — "
        "§4-1 이 제외하는 것은 **`MANUAL` 뿐**이고 이번 글 `MANUAL` 은 0 건이다. 규칙을 넓히지도 좁히지도 않았다.")
    say("4. **우리기술투자**는 `daily_prices` 04-01~08-04 봉 36/85(191종목 구멍 계열 · INTAKE §2-10). "
        "창5·창A·`[D-19,D]` 는 완전하나 **sigma20 의 21종가 창이 달력상 연속인지 보장되지 않는다** "
        "⇒ T2 에서 이 건의 sigma20 은 「구멍을 건너뛴 21봉」일 수 있다. 값은 그대로 쓰고 사실만 적는다.")
    say("5. **`H` = 등록일 고가는 가정**이고 사전등록은 앵커 민감도를 넣지 않았다 — `REC-Z3`(앵커 붕괴) "
        "산출물과 **함께** 읽어야 한다(`PREREG_POST6.md` §4 #44).")
    say("6. `V` 는 개수이고 귀무에서 비교가능 쌍 수가 함께 흔들린다(관측 vs 귀무 평균을 같은 표에 인쇄했다). "
        "사전등록이 정규화하지 않기로 동결했으므로 그대로 뒀다.")
    say("7. **글 간 풀링이 국면을 섞는다**(post4·post5·post6 = 3주). 표본은 저자가 올리기로 «고른» 매매다"
        "(`PREREG_SELECTION.md` §0 결과 조건화 위협).")
    say("8. `N` 은 저자 서술 의존(「N차 매수된 상태」를 「N차까지 체결」로 읽었고 **총 분할 수는 모른다**).")
    say("9. **새 예측을 만들지 않았다** — δ·창5·게이트 40·시드·순열 표본 수 전부 동결값 그대로다.")

    (BASE / "RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md").write_text("\n".join(OUT) + "\n",
                                                                  encoding="utf-8")
    cur.close()
    conn.close()
    print("\n[written] RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())

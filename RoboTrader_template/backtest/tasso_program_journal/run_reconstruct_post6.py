# -*- coding: utf-8 -*-
"""평단 P 복원 — 6번째 글 (REC-Y1~Y4 · REC-Z1~Z5 · P6-L1'/L1'-N/L2'/L3' · BUY-L5 · Q1-R3 · HDR-D1 · P6-R1').

사전등록: `PREREG_POST6.md` §1-2(BUY-L1/L2 (가) · `P6-L-누적` · `P6-L-대칭`) · §1-7(`REC-Z5`)
        · §2-6(`REC-Z1`~`Z5`) · §2-7(`REC-Y1`~`Y4` · A-1~A-11 승계) · §3-3(`P6-R1'`)
        · §3-4(`P6-L1'`·`P6-L1'-N`·`P6-L2'`) · §3-5(`P6-L3'` · A-7 정식등록) · §3-6(정확 구간법 단일화)
        · §4 표 #38~#54 · §5-6(C-22)
        · `PREREG_BUYLADDER.md` §5(L1~L5) · `PREREG_HDR.md` §4(D1) · `PREREG_Q1_V2.md` §3(R1·R3)
인테이크: `PREDECISION_2026-09-04_post6.md`(PD-1·PD-2·PD-3·PD-12·PD-13) ·
        `INTAKE_2026-09-04_post6.md` §1·§2·§5 · `LABELS_2026-09-04_post6.md`

🔴 **계산 «전» 에 고정한 해석 결정** — A-1~A-11 은 `RESULTS_RECONSTRUCT_POST5.md` §1 에서 **전부 승계**하고
   (`PREREG_POST6.md` §2-7: *「A-1 ~ A-11 … 전부 승계하고 스크립트 docstring 에 같은 문장을 박는다」*)
   창 종료일(A-1)만 이번 글의 값으로 바꾼다:

  A-1 창 종료일 = **2026-09-04** (DB 스냅샷 최대 = 발행일 = 거래일 · PD-1).
      🔴 **창 종료 2026-09-04 = 발행 당일 봉 «포함»**.
  A-2 REC-Y1 은 «전칭»으로 읽는다 — 레그 4개 이상인 «모든» 건의 폭 < 3%p. 건수 비율도 병기.
  A-3 되밀림 = 등록일 종가 < 등록일 고가 · 상한가마감 = 종가 == 고가 (post4 §3 조작화 승계).
  A-4 HDR-D1 표본 = 프리셋 `HDR 60%` 인 건. (이번 글은 12/12 가 HDR60 ⇒ 변량 0건.)
      라벨 `SL`(한라캐스트)은 post4·post5 전례(`MANUAL` 포함)대로 포함하되 제외 민감도 병기.
  A-5 P6-R1': `PREREG_Q1_V2.md` §3 R1 의 합침 조항은 *「같은 글 안에 «둘 다» 없으면」* 이라
      「한쪽만 없는」 경우를 덮지 않았다 ⇒ `PREREG_POST6.md` §3-3 이 **한쪽만 없는 경우로 확장**하고
      **양쪽 각 n >= 2** 를 요구한다(그 문턱은 §3-3 에서 «처음» 선언된 것 — §18 에 적는다).
  A-6 Q1-R3 은 다차수 건의 `1-P/H` 가 「1차 밴드」가 아니라는 post4 §2 범주오류 판정을 유지한다.
  A-7 P6-L3' 실행 전제 = 「`b1` 구간 폭 / sigma20 < 격자 0.25 인 건이 과반」.
      미달이면 공통해 탐색을 «돌리지 않고» ⛔ 「전제 미달 — 미실행」으로 적는다.
      🔴 post5 에서는 사전등록 밖 자유도였고, `PREREG_POST6.md` §3-5 가 **정식 등록**했다(문언·숫자 그대로).
  A-8 sigma20 = 등록일 «직전» 20거래일 로그수익률의 표본표준편차(연율화 안 함). 21봉 미만이면 sigma 축 제외.
  A-9 「하나의 평단」 전제가 원리적으로 깨질 수 있는 건에는 flag 만 단다.
      🔴 이번 글의 후속 2건(광전자·삼양바이오팜)은 **PD-2 4번**으로 REC- 축 «밖»이다(2차 매수 후 레그).
  A-10 «해 0개» 진단의 잔차 문턱 — post5 는 0.020·0.022 양쪽 인쇄였고,
      `REC-Z5`(`PREREG_POST6.md` §1-7)가 **이번 글부터 0.022 단일 판정 · 0.020 의무 민감도**로 못 박았다.
      두 문턱이 분류를 가르면 **「문턱 민감」이라고 인쇄하되 판정은 0.022 로 선다.**
  A-11 feasible set 은 **정확 구간법**으로 푼다(유일한 방법 · 점법 폐기 — `PREREG_POST6.md` §3-6):
      `P in ( S*c/(1+(r+0.005)/100),  S*c/(1+(r-0.005)/100) ]` · 레그별 합집합 → 레그 전체 교집합.
      gross(c=1) · net(c=(1-FEE-TAX)/(1+FEE)) 둘 다 푼다.
      의무 인쇄: **구간 개수 · P 범위 · 총 측도 · 폭 · 폭/호가단위(칸)**.
      🔴 점법은 «하한»이므로 인용 시 반드시 「하한」이라 적는다. C-22(post4 정확법 재계산)는 완료됐다
      (`RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS.md`) ⇒ REC-Y3 비율은 같은 잣대로 이어 붙일 수 있다.

🔴 **PD-12 (가)**: 5번째 글 삼양바이오팜(1차)의 복원값은 **재계산하지 않는다** —
   `RESULTS_RECONSTRUCT_POST5_NUMBERS.md` 의 **보존값을 인용**한다(md5 불변 의무).
   (나) 제외 갈래는 `P6-L1'`·`P6-L2'`·`P6-L-대칭` 전부에 **의무 민감도**로 나란히 인쇄한다.

🔴 **라이브 채택 금지**(`PREREG.md` §0-2) · 라이브 트리 import 0건 · DB 는 SELECT 만 ·
   `adj_factor` 산술 0건 · **새 예측 없음**(이 스크립트는 동결된 항목만 계산한다).
"""
from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

import psycopg2

from reconstruct_prices import gross_ret, tick
from run_reconstruct_post5 import (bars, feasible_exact, feasible_pointwise, iv_max,
                                   iv_measure, iv_min, min_residual, sigma20)
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

END = "2026-09-04"          # A-1 · PD-1 (발행일 = 거래일 = DB 스냅샷 최대)
THR_MAIN = 0.022            # REC-Z5 판정 문턱 (PREREG_EXIT_V2.md §2)
THR_SENS = 0.020            # REC-Z5 의무 민감도
SEED = 20260815             # P6-L1'-N 시드 (PREREG_POST6.md §3-4)
NREP = 20000                # P6-L1'-N 반복수

# (종목, 코드, 등록일, 레그 수익률, 체결차수, 프리셋, 라벨, first_only, 재진입)
# 출처 = INTAKE_2026-09-04_post6.md §1 (신규 10건) · LABELS_2026-09-04_post6.md
# 🔴 후속 2건(광전자·삼양바이오팜)은 PD-2 4번으로 REC- 축 «밖» — TARGETS 에 없다.
TARGETS = [
    ("한라캐스트", "125490", "2026-08-21",
     [5.82, 5.72, -2.87, -2.89], 5, "HDR60", "SL", False, False),
    ("헥토파이낸셜", "234340", "2026-08-28",
     [22.24, 15.33, 8.27], 1, "HDR60", "TP", True, False),
    ("아난티", "025980", "2026-08-19",
     [10.16], 1, "HDR60", "TP", True, False),
    ("아이티센글로벌", "124500", "2026-08-20",
     [5.72, 0.50], 3, "HDR60", "TP", False, False),
    ("현대약품", "004310", "2026-09-01",
     [12.32, 2.97], 2, "HDR60", "TP", False, True),
    ("원익", "032940", "2026-08-31",
     [18.44, 16.18, 14.05, 13.09, 13.06, 9.48, 4.27], 3, "HDR60", "TP", False, False),
    ("쿠콘", "294570", "2026-08-28",
     [14.31, 10.74], 1, "HDR60", "TP", True, False),
    ("지투파워", "388050", "2026-08-26",
     [10.14, 7.36, 7.25, 5.19], 3, "HDR60", "TP", False, True),
    ("우리기술투자", "041190", "2026-08-25",
     [16.48, 13.80, 13.63, 10.19, 6.50], 4, "HDR60", "TP", False, False),
    ("비에이치", "090460", "2026-09-01",
     [11.91, 10.65, 9.63, 8.36, 7.09, 6.08, 3.70], 4, "HDR60", "TP", False, False),
]

# PD-12 (가) — post5 보존값. **재계산하지 않는다.** 출처 = RESULTS_RECONSTRUCT_POST5_NUMBERS.md
SAM = dict(
    nm="삼양바이오팜(post5 1차)", code="0120G0", d0="2026-08-21", legs=[11.50, 11.50],
    n_iv=145, pmin=46903.73, pmax=59823.31, b1_lo=10.31, b1_hi=29.68, w=19.37,
    measure=693.96, mid=19.99, bar_low=57700.0, bar_open=63500.0, bar_high=66700.0,
    bar_close=58800.0, dd=21.59, prebars=11, hmax_mid=0.500, hmax_w=1.000, cells="258.4칸(50원)",
    src="RESULTS_RECONSTRUCT_POST5_NUMBERS.md §1·§7·§8·§9·§10·§12",
)


def say(s=""):
    print(s)
    OUT.append(s)


def med(xs):
    """C-20 — 짝수 n 에서 두 가운데 값의 평균(statistics.median)."""
    return statistics.median(xs)


def fmt_pct(x, nd=2):
    return "—" if x is None else f"{x:.{nd}f}%p"


def iv_clip_measure(iv, lo, hi):
    """feasible ∩ [lo, hi] 의 측도."""
    t = 0.0
    for a, b in iv:
        x, y = max(a, lo), min(b, hi)
        if y > x:
            t += y - x
    return t


def iv_weighted_median(iv):
    """측도 가중 중앙값 — 총 측도의 절반이 되는 P (P6-L2')."""
    tot = iv_measure(iv)
    if tot <= 0:
        return None
    half, acc = tot / 2.0, 0.0
    for a, b in iv:
        if acc + (b - a) >= half:
            return a + (half - acc)
        acc += b - a
    return iv[-1][1]


def win_bars(cur, code, d0, back, fwd):
    """[D-back, D+fwd] 거래일 창의 봉 (등록일 포함). 반환 = [(date, low, high), ...]"""
    cur.execute("SELECT date, low, high FROM daily_prices WHERE stock_code=%s AND date <= %s "
                "ORDER BY date DESC LIMIT %s", (code, d0, back + 1))
    pre = list(reversed(cur.fetchall()))
    cur.execute("SELECT date, low, high FROM daily_prices WHERE stock_code=%s AND date > %s "
                "ORDER BY date ASC LIMIT %s", (code, d0, fwd))
    return pre + list(cur.fetchall())


def dd_h(cur, code, d0, d1, k):
    cur.execute("SELECT max(high) FROM (SELECT high FROM daily_prices WHERE stock_code=%s "
                "AND date <= %s ORDER BY date DESC LIMIT %s) t", (code, d0, k))
    H = cur.fetchone()[0]
    cur.execute("SELECT min(low) FROM daily_prices WHERE stock_code=%s "
                "AND date BETWEEN %s AND %s", (code, d0, d1))
    L = cur.fetchone()[0]
    return 100 * (1 - L / H)


def main() -> int:  # noqa: C901
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    say("# RESULTS_RECONSTRUCT_POST6_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_reconstruct_post6.py` · 재사용 `run_reconstruct_post5.py`"
        "(`feasible_exact`·`feasible_pointwise`·`min_residual`·`sigma20`·`bars`) + "
        "`reconstruct_prices.py`(`tick`·`grid_prices`·`gross_ret`)")
    say("사전등록 `PREREG_POST6.md` §1-2·§1-7·§2-6·§2-7·§3-3·§3-4·§3-5·§3-6·§4(#38~#54) · "
        "`PREREG_BUYLADDER.md` §5 · `PREREG_HDR.md` §4 · `PREREG_Q1_V2.md` §3")
    say("인테이크 `PREDECISION_2026-09-04_post6.md` · `INTAKE_2026-09-04_post6.md` · "
        "`LABELS_2026-09-04_post6.md`\n")

    cur.execute("SELECT max(date) FROM daily_prices")
    snap = cur.fetchone()[0]
    say("## §0. 환경 · 승계 선언\n")
    say(f"- **DB 최신 봉 = {snap}** · 창 = `[등록일, {END}]` · "
        "🔴 **창 종료 2026-09-04 = 발행 당일 봉 «포함»**(PD-1)")
    say("- **A-1 ~ A-11 전부 승계**(`PREREG_POST6.md` §2-7 · 문장은 이 스크립트 docstring 에 박혀 있다) — "
        f"A-1 의 창 종료일만 이번 글 값 **{END}** 으로 바뀐다")
    say("- **A-11 정확 구간법이 유일한 방법**(§3-6) · 점법은 **폐기** — 대조로만 인쇄하고 "
        "인용 시 **「하한」**이라 적는다")
    say("- 🟢 **C-22 확인**: post4 정확법 재계산 **완료**(`RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS.md` §2 — "
        "발표 1/6 · 오늘 점법 1/6 · **오늘 정확법 1/6**) ⇒ `REC-Y3` 비율은 **같은 잣대**로 이어 붙일 수 있다")
    say("- 🔴 **PD-2 4번**: 후속 2건(광전자·삼양바이오팜 post6 레그)은 「하나의 평단」 전제가 깨져 "
        "**REC- 축 밖**이다. 신규 **10건**만 푼다(라벨 무관 — post5 한켐 `MANUAL` 전례)")
    say("- 🔴 **PD-12 (가)**: post5 삼양바이오팜(1차) 값은 **재계산하지 않고** "
        f"보존값을 인용한다(`{SAM['src']}`). (나) 제외 갈래는 의무 민감도로 병기")
    say(f"- `REC-Z5`: 판정 **{THR_MAIN:.3f}%p 단일** · **{THR_SENS:.3f}%p 의무 민감도**"
        "(갈리면 「문턱 민감」 인쇄 · 판정은 0.022 로 선다 — §1-7)")
    say(f"- `P6-L1'-N` 귀무: 시드 **{SEED}** · **{NREP:,}회** · 창 `[D-19, D+4]`")
    say("- 🔴 **라이브 채택 금지**(`PREREG.md` §0-2) — 이 문서의 어떤 숫자도 매매 규칙으로 옮기지 않는다\n")

    # ── §1. feasible 원표 ────────────────────────────────────────────────
    say("## §1. feasible set 원표 (gross · A-11 정확 구간법) — 의무 인쇄 5칸\n")
    say("의무 인쇄(§3-6): **구간 개수 · P 범위 · 총 측도 · 폭 · 폭/호가단위(칸)**\n")
    say("| 종목 | 차수 | 라벨 | 등록일 | 레그 | 등록일 봉 [저,시,고,종] | 되밀림 | "
        "**구간 개수** | **P 범위** | **총 측도(원)** | **`1-P/H` 범위** | **폭** | "
        "**폭/호가단위(칸)** | (대조·하한) 점법 개수/폭 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    R = {}
    for nm, code, d0, legs, tr, preset, label, fo, reent in TARGETS:
        rows = bars(cur, code, d0, END)
        o0, h0, l0, c0 = rows[0][1], rows[0][2], rows[0][3], rows[0][4]
        iv = feasible_exact(rows, legs, "gross")
        pts = feasible_pointwise(rows, legs, gross_ret)
        v = dict(code=code, d0=d0, legs=legs, tr=tr, preset=preset, label=label, fo=fo,
                 reent=reent, rows=rows, o0=o0, h0=h0, l0=l0, c0=c0, pull=c0 < h0,
                 iv=iv, pts=pts, nbars=len(rows))
        R[nm] = v
        pw = f"{len(pts)} / {(max(pts)-min(pts))/h0*100:.2f}%p" if pts else "0 / —"
        bar = f"[{l0:,.0f}, {o0:,.0f}, {h0:,.0f}, {c0:,.0f}]"
        pull_s = "예" if v["pull"] else "아니오"
        if iv:
            pmin, pmax = iv_min(iv), iv_max(iv)
            w = (pmax - pmin) / h0 * 100
            t = tick(pmin)
            v.update(pmin=pmin, pmax=pmax, w=w, measure=iv_measure(iv), cells=(pmax - pmin) / t)
            say(f"| {nm} | {tr}차 | {label} | {d0} | {len(legs)} | {bar} | {pull_s} | "
                f"**{len(iv)}** | {pmin:,.2f}~{pmax:,.2f} | **{v['measure']:,.2f}** | "
                f"{100*(1-pmax/h0):+.2f}%~{100*(1-pmin/h0):+.2f}% | **{w:.2f}%p** | "
                f"**{v['cells']:.1f}칸**({t}원) | {pw} |")
        else:
            v.update(pmin=None, pmax=None, w=None, measure=0.0, cells=None)
            say(f"| {nm} | {tr}차 | {label} | {d0} | {len(legs)} | {bar} | {pull_s} | "
                f"**0** | — | **0.00** | — | — | — | {pw} |")
    say(f"| _{SAM['nm']}_ | 1차 | TP | {SAM['d0']} | 2 | "
        f"[{SAM['bar_low']:,.0f}, {SAM['bar_open']:,.0f}, {SAM['bar_high']:,.0f}, "
        f"{SAM['bar_close']:,.0f}] | 예 | "
        f"_{SAM['n_iv']}_ | _{SAM['pmin']:,.2f}~{SAM['pmax']:,.2f}_ | _{SAM['measure']:,.2f}_ | "
        f"_+{SAM['b1_lo']:.2f}%~+{SAM['b1_hi']:.2f}%_ | _{SAM['w']:.2f}%p_ | _{SAM['cells']}_ | "
        f"_145 / 19.36%p_ |")
    say()
    say("- 🔴 마지막 줄(_기울임_)은 **post5 보존값 인용**이다 — PD-12 (가) · "
        f"**재계산하지 않았다**(`{SAM['src']}`).")
    say(f"- 되밀림(A-3: 종가 < 고가) **{sum(1 for v in R.values() if v['pull'])}/{len(R)}** · "
        f"상한가마감(종가==고가) **{sum(1 for v in R.values() if not v['pull'])}/{len(R)}**")
    say("- 고가 대비 종가 되밀림 폭: " + " · ".join(
        f"{nm} {100*(v['h0']-v['c0'])/v['h0']:.2f}%" for nm, v in R.items()))
    live = [(nm, v) for nm, v in R.items() if v["iv"]]
    if live:
        say("- feasible 총 측도(정확법): " + " · ".join(
            f"{nm} {v['measure']:,.2f}원" for nm, v in live) +
            " — 🔑 *「범위 안에 든다」와 「해다」는 다른 진술이다*: 범위 대비 측도를 함께 본다.")
        dirs = " · ".join(f"{nm} {(max(v['pts'])-min(v['pts']))/v['h0']*100:.2f}→{v['w']:.2f}%p"
                          for nm, v in live if v["pts"])
        say("- 🔴 **점법 대 정확법**(A-11 *「점법 값은 전부 하한」* 방향 확인): " +
            (dirs if dirs else "해가 있는 건에 점법 해 0개"))
    fo_wide = " · ".join(
        f"{nm}(레그 {len(v['legs'])}) 측도 {v['measure']:,.2f}원 · 폭 {v['w']:.2f}%p · 구간 {len(v['iv'])}"
        for nm, v in R.items() if v["fo"] and v["iv"] and len(v["legs"]) <= 2)
    say("- 🔑 **1~2레그 `first_only` 는 제약이 적어 feasible 이 넓을 것**이라 미리 적었다 — 실측: " +
        (fo_wide if fo_wide else "해당 없음"))

    # ── §2. 해 0개 진단 · REC-Z5 ─────────────────────────────────────────
    say()
    say("## §2. 해 0개 진단 · `REC-Z5` — 판정 0.022 / 민감도 0.020\n")
    say("`Δr_min` = 서로 «다른» 인접 레그 수익률의 최소 간격(%p) · "
        "`res` = 호가 한 칸이 만드는 수익률 해상도 `100*tick(P)/P`\n")
    say("🔑 `Δr_min < res` 이면 **두 레그를 격자 위 서로 다른 매도가로 표현할 수 없다** "
        "⇒ 산술적으로 해가 0개다.\n")
    say(f"🔴 **`REC-Z5`**(§1-7): 판정 문턱 **{THR_MAIN:.3f}%p 단일**"
        "(`PREREG_EXIT_V2.md` §2 복원 잔차 상한) · "
        f"**{THR_SENS:.3f}%p 는 의무 민감도**. 두 문턱이 분류를 가르면 **「문턱 민감」이라 인쇄하되 판정은 "
        f"{THR_MAIN:.3f} 로 선다**(`TV-N3` 와 다른 처리 — Z5 는 «고르기로» 동결한 항목).\n")
    say("| 종목 | 레그 | `Δr_min` | 후보 P 범위 | `res`(P 양끝) | **`Δr_min` < `res`?** | "
        "최소잔차 적합 P | **최대 오차** | **판정 @0.022** | (민감도) @0.020 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    split = []
    for nm, v in R.items():
        legs = v["legs"]
        gaps = [abs(legs[i] - legs[i + 1]) for i in range(len(legs) - 1) if legs[i] != legs[i + 1]]
        dmin = min(gaps) if gaps else None
        lo = min(r[3] for r in v["rows"])
        hi = max(r[2] for r in v["rows"])
        pl, ph = lo * 0.7, hi
        r_lo, r_hi = 100 * tick(pl) / pl, 100 * tick(ph) / ph
        under = (dmin is not None) and dmin < max(r_lo, r_hi)
        mr = min_residual(v["rows"], legs, gross_ret)
        v["minres"], v["under"], v["dmin"] = mr, under, dmin
        diags = []
        for t in (THR_MAIN, THR_SENS):
            if v["iv"]:
                diags.append(f"해 {len(v['iv'])}구간 (진단 불필요)")
            elif mr is None:
                diags.append("🔴 적합 실패")
            elif mr[0] < t:
                diags.append("반올림으로 설명 가능")
            else:
                diags.append("🔴 **모델이 틀렸다**")
        if not v["iv"] and mr is not None and diags[0] != diags[1]:
            split.append(nm)
        say(f"| {nm} | {legs} | {'—' if dmin is None else f'{dmin:.2f}%p'} | {pl:,.0f}~{ph:,.0f} | "
            f"{r_hi:.3f}~{r_lo:.3f}%p | {'🔴 **예**' if under else '아니오'} | "
            f"{'—' if mr is None else f'{mr[1]:,.0f}'} | "
            f"{'—' if mr is None else f'**{mr[0]:.6f}%p**'} | {diags[0]} | {diags[1]} |")
    say()
    say(f"- 두 문턱에서 분류가 갈리는 건: **{len(split)}건** ({', '.join(split) if split else '없음'}) ⇒ "
        + ("🔴 **「문턱 민감」** — 판정은 0.022 로 서고 그 사실을 여기 인쇄한다."
           if split else "**문턱 민감 없음**(0.020·0.022 에서 분류 동일)"))
    say(f"- 격자 해상도 미달(`Δr_min` < `res`) 건: "
        f"**{sum(1 for v in R.values() if v['under'])}/{len(R)}** ("
        + (", ".join(nm for nm, v in R.items() if v["under"]) or "없음") + ")")
    say("- 🔑 레그가 **1개뿐인 건**(아난티)은 `Δr_min` 이 «정의되지 않는다» — 격자 미달 판정에서 빠진다"
        "(post5 삼양이 동일값 2레그라 같은 처리였던 것과 같은 종류다).")

    # ── §3. REC-Y1 ───────────────────────────────────────────────────────
    say()
    say("## §3. `REC-Y1`(핵심) — 레그 4개 이상인 건의 `b1` feasible 폭 < 3%p (전칭 · A-2)\n")
    say("| 종목 | 레그 | 구간 개수 | 총 측도(원) | 폭 | < 3%p |")
    say("|---|---|---|---|---|---|")
    y1_items, y1_ok, y1_undef = [], 0, 0
    for nm, v in R.items():
        if len(v["legs"]) < 4:
            continue
        y1_items.append(nm)
        if not v["iv"]:
            y1_undef += 1
            say(f"| {nm} | {len(v['legs'])} | **0** | 0.00 | ⛔ **미정의**(해 0개) | ⛔ |")
        else:
            ok = v["w"] < 3.0
            y1_ok += int(ok)
            say(f"| {nm} | {len(v['legs'])} | {len(v['iv'])} | {v['measure']:,.2f} | "
                f"**{v['w']:.2f}%p** | {'성립' if ok else '위반'} |")
    say()
    say(f"- 레그>=4 대상 **{len(y1_items)}건**({', '.join(y1_items)}) · 폭 측정 가능 "
        f"**{len(y1_items)-y1_undef}건** · 미정의(해 0개) **{y1_undef}건** · 최소 n **3** ⇒ "
        f"{'충족' if len(y1_items) >= 3 else '미달'}")
    if y1_undef == len(y1_items):
        y1_verdict = ("⛔ **`REC-Y1` 판정 불가** — 대상 전건의 feasible set 이 비어 폭이 "
                      "«정의되지 않는다». 「폭 0 = 3%p 미만」으로 읽으면 규칙 완화다. 읽지 않는다.")
    elif y1_undef == 0 and y1_ok == len(y1_items):
        y1_verdict = "✅ **`REC-Y1` 성립**(전칭)"
    else:
        y1_verdict = f"⛔ **`REC-Y1` 불성립(전칭)** — 성립 {y1_ok}/{len(y1_items)} · 미정의 {y1_undef}"
    say("- ⇒ " + y1_verdict)

    # ── §4. REC-Y2 ───────────────────────────────────────────────────────
    say()
    say("## §4. `REC-Y2`(반증축 · 필수) — 폭을 «호가단위 배수»로도 인쇄\n")
    say("Y2: *「레그 수와 무관하게 폭이 좁으면 원인은 레그 수가 아니라 가격대(호가단위)다」*\n")
    say("| 종목 | 레그 | 가격대 | 호가단위(P 하단) | 폭(%p) | **폭 / 호가단위(칸)** | "
        "(대조·하한) 점법 칸 |")
    say("|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        lo = min(r[3] for r in v["rows"])
        hi = max(r[2] for r in v["rows"])
        if not v["iv"]:
            say(f"| {nm} | {len(v['legs'])} | {lo:,.0f}~{hi:,.0f} | — | — | — | — |")
            continue
        t = tick(v["pmin"])
        pwc = ((max(v["pts"]) - min(v["pts"])) / tick(min(v["pts"]))) if v["pts"] else None
        say(f"| {nm} | {len(v['legs'])} | {lo:,.0f}~{hi:,.0f} | {t}원 | {v['w']:.2f}%p | "
            f"**{v['cells']:.1f}칸** | {'—' if pwc is None else f'{pwc:.1f}칸'} |")
    say()
    narrow_cells = [nm for nm, v in R.items() if v["iv"] and v["w"] < 3.0]
    say(f"- 「좁은 폭(<3%p)」 건 **{len(narrow_cells)}건**"
        f"({', '.join(narrow_cells) if narrow_cells else '없음'}) ⇒ " +
        ("Y2 가 가르려던 대상이 있다 — 위 칸 수로 「레그 수」와 「호가단위」를 구분한다."
         if narrow_cells else "🟡 **구분할 대상 없음**(좁은 폭 0건)"))

    # ── §5. REC-Y3 ───────────────────────────────────────────────────────
    say()
    say("## §5. `REC-Y3`(중단 규칙) — feasible set 이 비는 비율\n")
    empty = [nm for nm, v in R.items() if not v["iv"]]
    frac = len(empty) / len(R)
    multi = [nm for nm, v in R.items() if v["tr"] >= 2]
    empty_multi = [nm for nm in empty if R[nm]["tr"] >= 2]
    say(f"- 해 0개(정확법 · 신규 10건): **{len(empty)}/{len(R)} = {100*frac:.1f}%** "
        f"({', '.join(empty) if empty else '없음'})")
    say("- 잣대 정합 계열(**전부 정확법**): post4 **1/6 = 16.7%**"
        "(`RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS.md` §2 · C-22 재계산) → post5 **4/6 = 66.7%** → "
        f"post6 **{len(empty)}/{len(R)} = {100*frac:.1f}%**")
    say(f"- 사전등록 문턱 **>= 1/3 = 33.3%** ⇒ **{'🔴 발동' if frac >= 1/3 else '미발동'}**")
    say(f"- 다차수(2차 이상) 건 **{len(multi)}/{len(R)}** 중 해 0개 **{len(empty_multi)}** "
        f"({', '.join(empty_multi) if empty_multi else '없음'})")
    if frac >= 1 / 3:
        say("- ⇒ 🔴🔴 **「다차수 건에서 평단이 매도 중 변한다」로 읽고, 복원 기반 축"
            "(`Q1-R3`·`HDR-D1`·`P6-L3'`·`BUY-L5`)을 «다차수 건»에 적용하는 것을 중단한다.** "
            "(`RESULTS_RECONSTRUCT_POST4.md` §6 Y3 동결 문언 — 값을 보고 정한 규칙이 아니다.)")
        say("- 🔑 중단은 «다차수 건»에만 걸린다. `first_only`(1차) 건은 전제가 다르므로 남는다.")
    else:
        say("- ⇒ **중단 미발동** — 복원 기반 축을 다차수 건에도 적용한다.")

    # ── §6. REC-Y4 ───────────────────────────────────────────────────────
    say()
    say("## §6. `REC-Y4`(기록만) — net 기준(정확 구간법) 해 개수 비교\n")
    say("| 종목 | gross 구간 개수 | gross 폭 | **net 구간 개수** | net P 범위 | net 총 측도(원) | net 폭 |")
    say("|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        ivn = feasible_exact(v["rows"], v["legs"], "net")
        v["iv_net"] = ivn
        gws = fmt_pct(v["w"])
        if ivn:
            nw = (iv_max(ivn) - iv_min(ivn)) / v["h0"] * 100
            say(f"| {nm} | {len(v['iv'])} | {gws} | **{len(ivn)}** | "
                f"{iv_min(ivn):,.2f}~{iv_max(ivn):,.2f} | {iv_measure(ivn):,.2f} | {nw:.2f}%p |")
        else:
            say(f"| {nm} | {len(v['iv'])} | {gws} | **0** | — | 0.00 | — |")
    say()
    gz = sum(1 for v in R.values() if not v["iv"])
    nz = sum(1 for v in R.values() if not v["iv_net"])
    say(f"- 해 0개: gross **{gz}/{len(R)}** · net **{nz}/{len(R)}** ⇒ "
        f"**{'net 으로 바꿔도 설명되지 않는다' if nz >= gz else 'net 이 해를 되살린다 — 저자가 net 으로 적었을 가능성'}**")

    # ── §7. REC-Z1 · Z2 ──────────────────────────────────────────────────
    say()
    say("## §7. `REC-Z1`(핵심) · `REC-Z2`(반증축)\n")
    z1_n = sum(1 for v in R.values() if v["under"])
    z1_frac = z1_n / len(R)
    say(f"- **`REC-Z1`**: `Δr_min` < `res` 인 건 **{z1_n}/{len(R)} = {100*z1_frac:.1f}%** · "
        f"문턱 **>= 1/3 = 33.3%** ⇒ **{'✅ 성립' if z1_frac >= 1/3 else '⛔ 불성립'}** "
        "(post5: 2/6 = 33.3%)")
    ga = [nm for nm, v in R.items() if v["under"]]
    gb = [nm for nm, v in R.items() if not v["under"]]
    ga_z = [nm for nm in ga if not R[nm]["iv"]]
    gb_z = [nm for nm in gb if not R[nm]["iv"]]
    say()
    say("| 부류 | 건수 | 해 0개 | 비율 | 건 |")
    say("|---|---|---|---|---|")
    say(f"| 격자 미달군(`Δr_min` < `res`) | {len(ga)} | **{len(ga_z)}** | "
        f"{(100*len(ga_z)/len(ga)):.1f}% | {', '.join(ga)} |" if ga else
        "| 격자 미달군(`Δr_min` < `res`) | 0 | — | — | — |")
    say(f"| 격자 충족군(`Δr_min` >= `res` 또는 미정의) | {len(gb)} | **{len(gb_z)}** | "
        f"{(100*len(gb_z)/len(gb)):.1f}% | {', '.join(gb)} |" if gb else
        "| 격자 충족군(`Δr_min` >= `res` 또는 미정의) | 0 | — | — | — |")
    say()
    say("- **`REC-Z2`**: 두 부류의 해 0개 비율을 나란히 인쇄했다 — " +
        ("🔴 **격자 충족군에서도 해 0개가 나온다** ⇒ 원인이 격자만은 아니다(평단 변화 후보 잔존)."
         if gb_z else "격자 충족군에서 해 0개 **0건** ⇒ 「원인은 격자」쪽과 모순되지 않는다.") +
        " (post5: 미달군 2/2 · 충족군 2/4 ⇒ *「아직 안 갈린다」*)")

    # ── §8. REC-Z3 앵커 ──────────────────────────────────────────────────
    say()
    say("## §8. `REC-Z3` — `H`(등록일 고가) < 창 최고가 인 건의 비율 (건별 인쇄 의무)\n")
    say("| 종목 | `H` = 등록일 고가 | 창 최고가 `[D, 종료]` | 창 최저가 | **`H` < 창최고?** | 초과폭 |")
    say("|---|---|---|---|---|---|")
    z3_hit = []
    for nm, v in R.items():
        cur.execute("SELECT min(low), max(high) FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s", (v["code"], v["d0"], END))
        L, HI = cur.fetchone()
        v["L"], v["HI"] = L, HI
        broken = v["h0"] < HI
        if broken:
            z3_hit.append(nm)
        over = f"{100*(HI-v['h0'])/v['h0']:.2f}%" if broken else "—"
        say(f"| {nm} | {v['h0']:,.0f} | {HI:,.0f} | {L:,.0f} | "
            f"{'🔴 **예**' if broken else '아니오'} | {over} |")
    z3_frac = len(z3_hit) / len(R)
    say()
    say(f"- **`REC-Z3` = {len(z3_hit)}/{len(R)} = {100*z3_frac:.1f}%** "
        f"({', '.join(z3_hit) if z3_hit else '없음'}) · 문턱 **>= 1/2 = 50.0%** ⇒ "
        f"**{'🔴🔴 발동' if z3_frac >= 0.5 else '미발동'}** (post5: 3/6 = 50.0% — 문턱에 정확히 걸침)")
    if z3_frac >= 0.5:
        say("- ⇒ 🔴🔴 **`PREREG_HDR` 의 `h` 축과 `PREREG_LADDER_TRANCHE` 의 `DD` 축이 «같은 앵커 "
            "가정»에서 함께 무너진다 ⇒ 앵커 재설계 사전등록 «의무 발생».** "
            "(`RESULTS_RECONSTRUCT_POST5.md` §9 Z3 동결 문언 · `PREREG_POST6.md` §2-6 이 "
            "*「6번째 글에서 한 건이라도 더 나오면 앵커 재설계 사전등록이 의무 발생한다」*고 미리 적어 두었다.)")
        say("- 🔴 **`HDR-D1` 은 이 붕괴로 «무효»**(`PREREG_POST6.md` §4 #52 대칭 쌍: "
            "*「`REC-Z3` 앵커 붕괴 시 무효」*) — §14 에 그대로 적용한다.")
    else:
        say("- ⇒ 앵커 재설계 의무 **미발생**. `HDR-D1` 은 이 축으로는 무효화되지 않는다.")
    say("- 🔑 `h = (S-L)/(H-L)` 는 `H` 가 천장일 때만 「저점 대비 반등폭 비율」이다 — "
        "천장이 뚫린 건에서는 `h_max` 가 1 을 넘고 HDR 틀 자체가 성립하지 않는다.")

    # ── §9. REC-Z4 ───────────────────────────────────────────────────────
    say()
    say("## §9. `REC-Z4` — `first_only` ∧ 서로 «다른» 값 레그 >= 3\n")
    say("| 종목 | first_only | 레그 | 서로 다른 값 개수 | Z4 발동 |")
    say("|---|---|---|---|---|")
    z4 = []
    for nm, v in R.items():
        if not v["fo"]:
            continue
        d = len(set(v["legs"]))
        hit = d >= 3
        if hit:
            z4.append(nm)
        say(f"| {nm} | 예 | {v['legs']} | **{d}** | {'🟢 **발동**' if hit else '아니오'} |")
    say(f"| _{SAM['nm']}_ | _예(post5)_ | _{SAM['legs']}_ | _1_ | _아니오(동일값 2레그)_ |")
    say()
    say(f"- **`REC-Z4` 발동 건: {len(z4)}건** ({', '.join(z4) if z4 else '없음'}) ⇒ "
        + ("🟢 **`P6-L1'`·`P6-L2'`·`BUY-L5` 를 «즉시» 판정한다**"
           "(누적 3건을 기다리지 않는다 — §1-2·§2-6 Z4)."
           if z4 else "즉시 판정 발동 없음 — `P6-L-누적` 3건 게이트로만 연다."))
    fo_new = [nm for nm, v in R.items() if v["fo"]]
    say(f"- `P6-L-누적`: post5 삼양 **1**(as-of-post5 · PD-12 (가)) + 신규 `first_only` "
        f"**{len(fo_new)}** = **{1+len(fo_new)}** >= 3 ⇒ 게이트 열림. "
        f"(나) 제외 갈래도 **{len(fo_new)}** >= 3 ⇒ 열림.")

    # ── §10. first_only 축 ───────────────────────────────────────────────
    say()
    say("## §10. `first_only` 축 — `P6-L1'` · `P6-L1'-N` · `P6-L2'` · `P6-L-대칭`\n")
    say("**`P6-L1'`**: `frac_in` = 측도(feasible ∩ [등록일 저가, 등록일 고가]) / 측도(feasible) · "
        "`frac_in >= 0.5` 인 건이 **>= 2/3** 이면 성립.")
    say("🔴 문턱 **0.5** 는 `PREREG_POST6.md` §3-4 가 **«처음» 선언**한 값이다(관측 전 고정 · §18 등재).\n")
    say("| 종목 | 레그 | feasible 구간수 | 총 측도(원) | 등록일 봉 [저, 고] | "
        "봉 ∩ 측도(원) | **`frac_in`** | >= 0.5 |")
    say("|---|---|---|---|---|---|---|---|")
    L1 = []
    for nm in fo_new:
        v = R[nm]
        if not v["iv"]:
            say(f"| {nm} | {len(v['legs'])} | **0** | 0.00 | [{v['l0']:,.0f}, {v['h0']:,.0f}] | — | "
                f"⛔ **측정 불가**(해 0개) | ⛔ |")
            L1.append((nm, None))
            continue
        m_in = iv_clip_measure(v["iv"], v["l0"], v["h0"])
        fi = m_in / v["measure"]
        v["frac_in"] = fi
        L1.append((nm, fi))
        say(f"| {nm} | {len(v['legs'])} | {len(v['iv'])} | {v['measure']:,.2f} | "
            f"[{v['l0']:,.0f}, {v['h0']:,.0f}] | {m_in:,.2f} | **{fi:.4f}** | "
            f"{'성립' if fi >= 0.5 else '위반'} |")
    say(f"| _{SAM['nm']}_ | _2_ | _{SAM['n_iv']}_ | _{SAM['measure']:,.2f}_ | "
        f"_[{SAM['bar_low']:,.0f}, {SAM['bar_high']:,.0f}]_ | _보존값 없음_ | "
        f"_⛔ **인용 불가**_ | _⛔_ |")
    say()
    say("- 🔴 **모호 지점 (1)**: `frac_in` 은 `P6-L1'` 이 **이번 문서에서 처음 정의한 통계량**이라 "
        "post5 보존값에 **없다**. PD-12 는 삼양을 **재계산하지 말라**고 했으므로 (가) 갈래에서도 "
        "삼양은 `P6-L1'` **분모 밖**이다 ⇒ 🟢 **(가)·(나) 두 갈래의 `P6-L1'` 분모가 같다**(신규 3건) "
        "⇒ 이 항목에는 「누적 정의 의존」이 **없다**.")
    ok1 = [nm for nm, f in L1 if f is not None and f >= 0.5]
    meas1 = [nm for nm, f in L1 if f is not None]
    zero1 = [nm for nm, f in L1 if f is None]
    say()
    say("**최소 n 게이트 — 동결 문언 그대로**(§3-4 *「최소 n: §1-2 의 `P6-L-누적` **3건**"
        "(또는 **`REC-Z4`** 발동 시 즉시)」*):")
    say(f"- `P6-L-누적` = **{1+len(fo_new)}**(가) / **{len(fo_new)}**(나) — **둘 다 >= 3** ⇒ 게이트 열림")
    say(f"- `REC-Z4` **발동**(§9) ⇒ *「즉시 판정」* · PD-13 이 *「`P6-L-누적`(누적 4 >= 3 ⇒ **판정 의무**)」* "
        "라고 계산 «전»에 적어 두었다")
    say("- 🔴 **새 문턱을 만들지 않는다** — 「측정 가능한 건이 3건 이상이어야 한다」는 문언에 **없다.** "
        "⛔ 조건 ①은 *「`first_only` **누적** < 3」* 이고, 그 값은 위에서 충족됐다.")
    say()
    say(f"🔴 **모호 지점 (1-b)**: ⛔ 조건 ② *「feasible 이 **빈 집합**(해 0개)」* 는 post5 의 "
        f"**단일 건 문맥**에서 쓰였다. 분모가 여러 건인 지금 「그 «건»이 비면」인지 "
        f"「분모에 «하나라도» 비면」인지 **문언으로 갈리지 않는다**(해 0개 건 {len(zero1)}: "
        f"{', '.join(zero1) if zero1 else '없음'}) ⇒ **세 읽기를 전부 인쇄한다.**")
    say()
    say("| 읽기 | 분모 | `frac_in >= 0.5` | 비율 | 문턱 2/3 | 판정 |")
    say("|---|---|---|---|---|---|")
    if meas1:
        r_a = len(ok1) / len(meas1)
        say(f"| **(주)** 해 0개 건은 `frac_in` 이 «정의되지 않아» 분모 밖 | {len(meas1)} | "
            f"{len(ok1)} | **{100*r_a:.1f}%** | 66.7% | "
            f"**{'✅ 성립' if r_a >= 2/3 else '⛔ 불성립'}** |")
    else:
        r_a = None
        say("| **(주)** 해 0개 건은 분모 밖 | 0 | — | — | 66.7% | ⛔ 분모 0 |")
    r_b = len(ok1) / len(fo_new) if fo_new else None
    say(f"| (민감도 i) 해 0개 건을 «위반»으로 계상 | {len(fo_new)} | {len(ok1)} | "
        f"**{100*r_b:.1f}%** | 66.7% | **{'✅ 성립' if r_b >= 2/3 else '⛔ 불성립'}** |")
    say("| (민감도 ii) ⛔ ② 를 *「분모에 하나라도 비면 판정 불가」* 로 읽음 | — | — | — | — | "
        + ("⛔ **판정 불가**" if zero1 else "(해 0개 0건 ⇒ (주)와 같다)") + " |")
    say()
    if zero1:
        say("- 🔴 **방향 자기신고**: (민감도 ii) 는 아래 (주)·(i) 의 결론을 **지우는** 쪽이다. "
            "`P6-L1'` 이 «불성립»이면 그것은 가설 A 에 **불리한** 관측이므로, "
            "⛔ 로 읽는 선택은 **가설 A 에 유리한 방향**이다. 그래서 (주)를 ⛔ 로 바꾸지 않는다 "
            "— §1-2 가 *「(가)는 판정을 «미루는» 것이지 «면제하는» 것이 아니다」* 라고 못 박은 그 지점이다.")
    outcomes = [x for x in (r_a, r_b) if x is not None]
    l1_ok = (r_a >= 2 / 3) if r_a is not None else None
    if outcomes and all(x < 2 / 3 for x in outcomes):
        say(f"- ⇒ ⛔ **`P6-L1'` 불성립** (주 {len(ok1)}/{len(meas1)} = {100*r_a:.1f}%) — "
            "🟢 **어느 읽기에서도 「성립」이 나오지 않는다**(민감도 i 도 불성립 · ii 는 ⛔) "
            "⇒ 「지지」 방향으로는 **강건**하다.")
    elif outcomes and all(x >= 2 / 3 for x in outcomes):
        say(f"- ⇒ ✅ **`P6-L1'` 성립** (주 {len(ok1)}/{len(meas1)} = {100*r_a:.1f}%) — "
            "단 (민감도 ii) 읽기에서는 ⛔ 다.")
    else:
        say("- ⇒ ⛔ **판정 불가** — 읽기에 따라 성립/불성립이 갈린다(「정의 의존」).")

    # P6-L1'-N
    say()
    say("### `P6-L1'-N` (대칭 단언 · 필수 · 죽은 가드 방지)\n")
    say(f"같은 종목 창 `[D-19, D+4]` 에서 **무작위 «날»의 봉**으로 같은 `frac_in` 을 계산한다"
        f"(**{NREP:,}회** · 시드 **{SEED}**). 무작위 날의 `frac_in >= 0.5` 비율이 "
        "**50% 이상이면 `P6-L1'` 지지를 「판별력 없음」으로 강등**한다.\n")
    say("🔑 *이게 없으면 「봉이 넓어서 들어간 것」과 「등록일에 샀기 때문에 들어간 것」이 구분되지 않는다.*\n")
    say("| 종목 | 창 봉수 `[D-19, D+4]` | 등록일 `frac_in` | **귀무 `frac_in>=0.5` 비율** | "
        "(참고) 창 전 봉 전수 비율 | >= 50% |")
    say("|---|---|---|---|---|---|")
    nulls = []
    for nm in fo_new:
        v = R[nm]
        wb = win_bars(cur, v["code"], v["d0"], 19, 4)
        v["winbars"] = len(wb)
        if not v["iv"]:
            say(f"| {nm} | {len(wb)} | ⛔ 측정 불가 | — | — | — |")
            continue
        rng = random.Random(SEED)
        hits = 0
        for _ in range(NREP):
            _, lo_d, hi_d = wb[rng.randrange(len(wb))]
            if iv_clip_measure(v["iv"], lo_d, hi_d) / v["measure"] >= 0.5:
                hits += 1
        p = hits / NREP
        ex = sum(1 for _, a, b in wb
                 if iv_clip_measure(v["iv"], a, b) / v["measure"] >= 0.5) / len(wb)
        nulls.append((nm, p))
        say(f"| {nm} | {len(wb)} | {v['frac_in']:.4f} | **{100*p:.2f}%** | {100*ex:.2f}% | "
            f"{'🔴 **예**' if p >= 0.5 else '아니오'} |")
    say()
    if nulls:
        dem = [nm for nm, p in nulls if p >= 0.5]
        say(f"- 건별 귀무 비율 평균 **{100*statistics.mean(p for _, p in nulls):.2f}%** · "
            f"50% 이상인 건 **{len(dem)}/{len(nulls)}** ({', '.join(dem) if dem else '없음'})")
        say("- ⇒ " + ("🔴 **`P6-L1'` 지지를 「판별력 없음」으로 «강등»한다**(건별 50% 이상 존재)."
                      if dem else
                      "🟢 **강등 없음** — 무작위 날로는 `frac_in >= 0.5` 가 50% 미만이다."))
        if l1_ok is False:
            say("- 🔑 단 `P6-L1'` 자체가 **불성립**이라 강등 여부는 «지지를 깎는» 방향으로 작동할 대상이 없다 "
                "— 그래도 규칙대로 계산해 인쇄한다(죽은 가드 방지 장치는 결과와 무관하게 돌린다).")
    else:
        say("- ⇒ ⛔ 귀무 계산 대상 0건(해 0개).")

    # P6-L2' · P6-L-대칭
    say()
    say("### `P6-L2'` (측도가중 중앙값) · `P6-L-대칭`\n")
    say("**`P6-L2'`**: `b1 = 1 - P/H`(H = 등록일 고가)의 **feasible 집합 «측도 가중» 중앙값**. "
        "**범위 중점도 민감도로 의무 인쇄** — 두 값이 문턱 5% 를 사이에 두고 갈리면 "
        "⛔ 「통계량 정의 의존」.\n")
    say("**`P6-L-대칭`**: 누적 3건 시점에서 `b1` 중앙값이 **>= 5%** 면 **가설 A 를 기각**한다"
        "(문언 그대로 판정).\n")
    say("| 종목 | H(등록일 고가) | P 측도가중 중앙 | **`b1` 측도가중 중앙** | P 범위중점 | "
        "(민감도) `b1` 범위중점 | 두 값이 5% 를 가르나 |")
    say("|---|---|---|---|---|---|---|")
    L2w, L2m = [], []
    for nm in fo_new:
        v = R[nm]
        if not v["iv"]:
            say(f"| {nm} | {v['h0']:,.0f} | — | ⛔ **해 0개** | — | ⛔ | ⛔ |")
            continue
        pw = iv_weighted_median(v["iv"])
        b_w = 100 * (1 - pw / v["h0"])
        pm = (v["pmin"] + v["pmax"]) / 2
        b_m = 100 * (1 - pm / v["h0"])
        L2w.append(b_w)
        L2m.append(b_m)
        crossed = (b_w < 5.0) != (b_m < 5.0)
        say(f"| {nm} | {v['h0']:,.0f} | {pw:,.2f} | **{b_w:.2f}%** | {pm:,.2f} | {b_m:.2f}% | "
            f"{'🔴 **예**' if crossed else '아니오'} |")
    say(f"| _{SAM['nm']}_ | _{SAM['bar_high']:,.0f}_ | _보존값 없음_ | _⛔ **인용 불가**_ | "
        f"_{(SAM['pmin']+SAM['pmax'])/2:,.2f}_ | _{SAM['mid']:.2f}%_ | _⛔ 한쪽만 존재_ |")
    say()
    say("- 🔴 **모호 지점 (2)**: 삼양의 **«측도가중»** `b1` 은 post5 보존값에 없다(그 통계량은 post6 에서 "
        "처음 정의됐다) · PD-12 는 **재계산 금지**다 ⇒ (가) 갈래에서 삼양을 넣으려면 "
        "**범위중점 19.99% 를 대입**해야 하고 그것은 **두 통계량을 섞는 것**이다. "
        "🔴 **섞은 갈래와 제외한 갈래를 «둘 다» 인쇄하고, 어느 쪽도 규칙으로 고르지 않는다.**")
    say()
    say("| 갈래 | 분모 n | `b1` 중앙값 | < 5% (`P6-L2'`) | >= 5% (`P6-L-대칭` ⇒ 가설 A 기각) |")
    say("|---|---|---|---|---|")

    def branch(label, vals):
        if not vals:
            say(f"| {label} | 0 | ⛔ | ⛔ | ⛔ |")
            return None
        m = med(vals)
        say(f"| {label} | {len(vals)} | **{m:.2f}%** | {'✅ 성립' if m < 5 else '❌ 위반'} | "
            f"{'🔴 **기각**' if m >= 5 else '기각 안 함'} |")
        return m

    r_wn = branch("**주** 측도가중 · (나) 삼양 제외", L2w)
    r_wg = branch("측도가중 · (가) 삼양 = 범위중점 19.99% 대입 🔴정의 혼합", L2w + [SAM["mid"]] if L2w else [])
    r_mn = branch("(민감도) 범위중점 · (나) 삼양 제외", L2m)
    r_mg = branch("(민감도) 범위중점 · (가) 삼양 19.99% 포함", L2m + [SAM["mid"]] if L2m else [])
    say()
    labeled = (("측도가중/(나)", r_wn), ("측도가중/(가)", r_wg),
               ("범위중점/(나)", r_mn), ("범위중점/(가)", r_mg))
    got = [x for _, x in labeled if x is not None]
    if not got:
        say("- ⇒ ⛔ **`P6-L2'`·`P6-L-대칭` 판정 불가** — feasible 전건 해 0개(§3-4 ⛔ 조건 ②).")
    else:
        say("- 네 갈래 중앙값: " + " · ".join(
            f"{lab} **{val:.2f}%**" for lab, val in labeled if val is not None))
        same = all((x < 5) == (got[0] < 5) for x in got)
        if same:
            say(f"- 🟢 **네 갈래 전부 같은 쪽**(모두 {'< 5%' if got[0] < 5 else '>= 5%'}) ⇒ "
                "「통계량 정의 의존」·「누적 정의 의존」 **없음**")
            if zero1:
                say(f"- 🔴 **모호 지점 (2-b)** — §10 (1-b)와 같은 ⛔ 조건 ② 문제: 해 0개 건"
                    f"({', '.join(zero1)})을 «분모 밖»으로 두었다(주). "
                    "*「분모에 하나라도 비면 판정 불가」* 로 읽으면 ⛔ 다. "
                    "🔴 **방향 자기신고**: `b1` 중앙값이 5% «위»라 아래 판정은 "
                    "**가설 A 기각**인데, ⛔ 읽기는 그 기각을 **지우는** 쪽 = "
                    "**가설 A 에 유리한 방향**이다. 그래서 ⛔ 로 바꾸지 않는다"
                    "(§1-2 *「(가)는 판정을 «미루는» 것이지 «면제하는» 것이 아니다」*).")
            if got[0] < 5:
                say("- ⇒ ✅ **`P6-L2'` 성립** · `P6-L-대칭` **기각 안 함**(가설 A 살아 있다)")
            else:
                say("- ⇒ ❌ **`P6-L2'` 위반** ⇒ 🔴🔴 **`P6-L-대칭` 발동 — 가설 A 기각**(문언 그대로 판정)")
                say("  - 대상 = `PREREG_BUYLADDER.md` §5 가 세운 **가설 A**"
                    "(*「1차는 rung 이 아니라 등록 즉시 매수」*) · 근거 문언 = "
                    "`PREREG_POST6.md` §1-2 `P6-L-대칭` *「누적 3건 시점에서 `b1` 중앙값이 "
                    "**>= 5%** 면 **가설 A 를 기각**한다」*")
                say("  - 🔑 post5 §10 **N3** 이 예고한 그대로다 — *「(나) 로 읽으면 L2 중점 19.99% "
                    "≫ 5% 로 가설 A 기각」*. (가)로 미룬 판정이 «면제»가 아니었음을 "
                    "이번 글이 확인한다.")
        else:
            say("- ⇒ ⛔ **판정 불가** — 갈래가 문턱 5% 를 사이에 두고 **갈린다**: "
                "측도가중 vs 범위중점이 갈리면 §3-4 의 **「통계량 정의 의존」** · "
                "(가) vs (나) 가 갈리면 PD-12 의 **「누적 정의 의존」** ⇒ **지지 선언 금지**.")

    # ── §11. BUY-L5 ──────────────────────────────────────────────────────
    say()
    say("## §11. `BUY-L5`(반증축) — `P` 가 등록일 봉의 상단 1/3 인가 하단 1/3 인가\n")
    say("L5 문언: *「신규 건 중 **등록일에 고가를 찍고 되밀린 건**에서 `P` 가 [시가, 고가] 상단 1/3 에 "
        "몰리면 **즉시 진입**, 하단 1/3 이면 **밴드**. 어느 쪽도 과반이 아니면 **판별 불가**로 적는다」*")
    say("🔴 **전제 검사를 «먼저»**(post4·post5 승계) — `P` 가 「등록일에 산 가격」이라야 뜻이 있다.\n")
    say("| 종목 | 차수 | first_only | 등록일 봉 [저,시,고] | P 범위 | 전제(P ⊂ [저,고]) | "
        "상단1/3 하한 | 하단1/3 상한 | 판정 |")
    say("|---|---|---|---|---|---|---|---|---|")
    verdicts, fo_verdicts = [], []
    for nm, v in R.items():
        if not v["pull"]:
            continue
        o0, h0, l0 = v["o0"], v["h0"], v["l0"]
        up, dn = o0 + (h0 - o0) * 2 / 3, o0 + (h0 - o0) / 3
        stop = (v["tr"] >= 2 and frac >= 1 / 3)
        if not v["iv"]:
            vd, key, pr, pre = "⛔ **판정 불가 (해 0개)**", "불가", "**해 없음**", "⛔"
        elif stop:
            vd, key = "⛔ **적용 중단**", "불가"
            pr = f"{v['pmin']:,.2f}~{v['pmax']:,.2f}"
            pre = "🔴 **`REC-Y3` 중단 대상(다차수)**"
        else:
            pr = f"{v['pmin']:,.2f}~{v['pmax']:,.2f}"
            premise = (l0 <= v["pmin"]) and (v["pmax"] <= h0)
            pre = "성립" if premise else "🔴 **봉 밖**"
            if not premise:
                vd, key = "⛔ **판정 불가 (전제 미성립)**", "불가"
            elif v["pmin"] >= up:
                vd = key = "즉시진입"
            elif v["pmax"] <= dn:
                vd = key = "밴드"
            else:
                vd, key = "🟡 구간이 걸쳐 있음", "불가"
        verdicts.append(key)
        if v["fo"]:
            fo_verdicts.append(key)
        say(f"| {nm} | {v['tr']}차 | {'예' if v['fo'] else '아니오'} | "
            f"[{l0:,.0f}, {o0:,.0f}, {h0:,.0f}] | {pr} | {pre} | {up:,.0f} | {dn:,.0f} | {vd} |")
    say()
    for lab, vs in (("되밀림 신규 전건(L5 문언 정의역)", verdicts),
                    ("`first_only` 부분집합(`REC-Z4` 즉시판정 대상)", fo_verdicts)):
        if not vs:
            say(f"- {lab}: 대상 **0건** ⇒ ⛔ 판정 불가")
            continue
        bad = vs.count("불가")
        say(f"- {lab}: **{len(vs)}건** 중 판별 불가 **{bad}건** · "
            f"즉시진입 **{vs.count('즉시진입')}** · 밴드 **{vs.count('밴드')}**")
        if bad * 2 >= len(vs):
            say("  ⇒ ⛔ **`BUY-L5` 판정 불가**(과반이 판별 불가)")
        else:
            cnt = {k: vs.count(k) for k in ("즉시진입", "밴드")}
            top = max(cnt, key=cnt.get)
            if cnt[top] * 2 > len(vs):
                say(f"  ⇒ ✅ **{top}** — 즉시진입 {cnt['즉시진입']} · 밴드 {cnt['밴드']} / 분모 {len(vs)}")
            else:
                say(f"  ⇒ ⛔ **판별 불가**(어느 쪽도 과반 아님) — 즉시진입 {cnt['즉시진입']} · "
                    f"밴드 {cnt['밴드']} / 분모 {len(vs)}")

    # ── §12. Q1-R3 ───────────────────────────────────────────────────────
    say()
    say("## §12. `Q1-R3` — `b1` 구간이 직전 글 값과 부호·자릿수가 같은가 (구간 겹침 여부만)\n")
    say("A-6: 다차수 건의 `1-P/H` 는 「1차 밴드」가 아니라 「전 차수 평단」이다 ⇒ "
        "**범주 오류**(post4 §2 유지). "
        + ("`REC-Y3` 중단도 다차수 건에 겹친다." if frac >= 1 / 3 else "") + "\n")
    say("| 건 | 구분 | `b1` 구간 | 부호 | 자릿수(정수부) |")
    say("|---|---|---|---|---|")
    r3 = []
    for nm in fo_new:
        v = R[nm]
        if not v["iv"]:
            say(f"| {nm} | `first_only` | ⛔ 해 0개 | — | — |")
            continue
        lo_b, hi_b = 100 * (1 - v["pmax"] / v["h0"]), 100 * (1 - v["pmin"] / v["h0"])
        r3.append((nm, lo_b, hi_b))
        sg = "양" if lo_b > 0 else ("음" if hi_b < 0 else "🔴 **부호 걸침**")
        say(f"| {nm} | `first_only` | **[{lo_b:+.2f}%, {hi_b:+.2f}%]** | {sg} | "
            f"{len(str(int(abs(hi_b))))} 자리 |")
    say(f"| _{SAM['nm']}_ | _`first_only`(post5 보존)_ | "
        f"_[+{SAM['b1_lo']:.2f}%, +{SAM['b1_hi']:.2f}%]_ | _양_ | "
        f"_{len(str(int(SAM['b1_hi'])))} 자리_ |")
    say("| 솔트룩스(post4) | `first_only` | [−0.90%, +2.47%] | 걸침 | 1 자리 |")
    say("| 매드업(post4) | `first_only` | `b2` > +26.56% | 양 | 2 자리 |")
    say("| 케이엔알(직전 3글) | `full` | `b_last` <= +36.76% | 양 | 2 자리 |")
    say()
    say(f"- 최소 n **3**(`PREREG_POST6.md` §4 #54) — 두 읽기: "
        f"`first_only` **건수 {len(fo_new)}**(⇒ {'충족' if len(fo_new) >= 3 else '미달'}) vs "
        f"**측정 가능 {len(r3)}건**(⇒ {'충족' if len(r3) >= 3 else '미달'}) · "
        "🔴 §10 (1-b)와 **같은 ⛔ ② 모호**다 — 양쪽 인쇄한다.")
    if r3:
        ov_s = sum(1 for _, a, b in r3 if not (b < SAM["b1_lo"] or a > SAM["b1_hi"]))
        ov_p = sum(1 for _, a, b in r3 if not (b < -0.90 or a > 2.47))
        say(f"- 구간 겹침(측정 가능 {len(r3)}건 기준): post5 삼양 "
            f"`[+{SAM['b1_lo']:.2f}, +{SAM['b1_hi']:.2f}]` 과 **{ov_s}/{len(r3)}** · "
            f"post4 솔트룩스 `[−0.90, +2.47]` 과 **{ov_p}/{len(r3)}**")
        say(f"- 부호: 측정 가능 {len(r3)}건 전부 **양** · 자릿수(상한의 정수부 자릿수) "
            + ", ".join(f"{nm} {len(str(int(abs(b))))} 자리({b:+.2f}%)" for nm, _, b in r3))
    if len(r3) >= 3:
        say("- ⇒ 🟡 **`Q1-R3` = 겹침 여부 «기록»**(`PREREG_Q1_V2.md` §3 판정 규칙 = "
            "*「R3 은 구간 겹침 여부만」* — 지지/기각을 선언하는 항목이 아니다).")
    else:
        say(f"- ⇒ ⛔ **`Q1-R3` 판정 불가**(주) — 다차수는 범주 오류"
            + (" · `REC-Y3` 중단" if frac >= 1 / 3 else "")
            + f" · `first_only` **측정 가능 {len(r3)} < 3**. "
            "🟡 「건수 읽기」(3건 충족)를 택하면 위 겹침 값이 R3 의 «기록»이 된다 — "
            "🔴 어느 쪽이든 **R3 은 지지/기각을 선언하는 항목이 아니라** 결론은 같다"
            "(방향 자기신고: 이 모호는 판정을 움직이지 않는다).")

    # ── §13. P6-L3' ──────────────────────────────────────────────────────
    say()
    say("## §13. `P6-L3'` — A-7 전제 검사부터 (`PREREG_POST6.md` §3-5 정식 등록)\n")
    say("전제: 「`b1` 구간 폭 / sigma20 < **0.25**(= `PREREG_BUYLADDER.md` §5 L3 격자 ±0.25)인 건이 "
        "**과반**」 · 과반 미만이면 ⛔ **「전제 미달 — 미실행」**으로 적고 **돌리지 않는다.**\n")
    say("의무 인쇄: 건별 `sigma20` · 직전 봉수 · `b1` 폭 · 폭/sigma20 · 전제 통과 여부 "
        "(post5 = **0/6**)\n")
    say("| 종목 | sigma20 | 사용 봉(등록일 «직전») | `b1` 폭 | **폭/sigma20** | < 0.25 |")
    say("|---|---|---|---|---|---|")
    narrow = 0
    for nm, v in R.items():
        s, n = sigma20(cur, v["code"], v["d0"])
        v["sigma20"], v["prebars"] = s, n
        if s is None:
            say(f"| {nm} | ⛔ **없음**(21봉 미만) | {n} | — | — | ⛔ |")
            continue
        if not v["iv"]:
            say(f"| {nm} | {s:.4f} | {n} | ⛔ 해 0개 | — | ⛔ |")
            continue
        w = v["w"] / 100
        ok = w / s < 0.25
        narrow += int(ok)
        say(f"| {nm} | {s:.4f} | {n} | {v['w']:.2f}%p | **{w/s:.2f}** | "
            f"{'성립' if ok else '위반'} |")
    say(f"| _{SAM['nm']}_ | _⛔ 없음(21봉 미만)_ | _{SAM['prebars']}(직전)_ | _{SAM['w']:.2f}%p_ | "
        "_—_ | _⛔_ |")
    say()
    need = len(R) // 2 + 1
    say(f"- 폭/sigma20 < 0.25 인 건 **{narrow}/{len(R)}** ⇒ 과반 문턱 **{need}건** ⇒ "
        f"**{'전제 성립 — 공통해 탐색 실행' if narrow >= need else '전제 미달'}**")
    if narrow < need:
        say("- ⇒ ⛔ **`P6-L3'` 「전제 미달 — 미실행」.** 입력이 「점」이 아니라 격자보다 넓은 구간"
            "(또는 빈 집합)이면 *「공통해 탐색은 이런 입력이면 거의 항상 해를 찾는다」* = "
            "**돌리면 반드시 「지지」가 나오는 죽은 검정**이다. **돌리지 않았다.**")

    # ── §14. HDR-D1 ──────────────────────────────────────────────────────
    say()
    say("## §14. `HDR-D1` — `HDR 60%` 건의 `h_max` 중앙값이 0.50~0.70 인가\n")
    say("`h_max = (S_max - L)/(H - L)` · `H` = 등록일 고가 · `L` = min(low) over `[D, 종료]` · "
        "`S_max = P*(1+r1)` · 분모 = 프리셋 `HDR 60%` 건(A-4 · 이번 글 12/12 가 HDR60)\n")
    say("| 종목 | 프리셋 | 차수 | H | L | 창 최고가 | H == 창최고? | P 범위 | `h_max` 범위 | 폭 | "
        "Y3 중단 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    d1mids = []
    for nm, v in R.items():
        stop = (v["tr"] >= 2 and frac >= 1 / 3)
        aflag = "예" if v["h0"] >= v["HI"] else "🔴 **아니다**"
        if not v["iv"]:
            say(f"| {nm} | {v['preset']} | {v['tr']}차 | {v['h0']:,.0f} | {v['L']:,.0f} | "
                f"{v['HI']:,.0f} | {aflag} | **해 없음** | — | — | {'🔴' if stop else '—'} |")
            continue
        r1_ = v["legs"][0] / 100.0
        smin, smax = v["pmin"] * (1 + r1_), v["pmax"] * (1 + r1_)
        hlo, hhi = (smin - v["L"]) / (v["h0"] - v["L"]), (smax - v["L"]) / (v["h0"] - v["L"])
        say(f"| {nm} | {v['preset']} | {v['tr']}차 | {v['h0']:,.0f} | {v['L']:,.0f} | "
            f"{v['HI']:,.0f} | {aflag} | {v['pmin']:,.2f}~{v['pmax']:,.2f} | "
            f"**{hlo:.3f}~{hhi:.3f}** | {hhi-hlo:.3f} | {'🔴 중단' if stop else '—'} |")
        if v["preset"] == "HDR60" and not stop:
            d1mids.append((nm, (hlo + hhi) / 2, hhi - hlo, v["label"]))
    say()
    say(f"- `REC-Y3` 중단{' 발동 ⇒ 다차수 건 제외' if frac >= 1/3 else ' 미발동'} · 남는 분모 "
        f"**{len(d1mids)}건** ({', '.join(n for n, _, _, _ in d1mids) if d1mids else '없음'})")
    for n_, m_, w_, lb in d1mids:
        say(f"  - {n_}({lb}): 중점 **{m_:.3f}** · 폭 **{w_:.3f}**")
    if z3_frac >= 0.5:
        say("- ⇒ 🔴🔴 **`HDR-D1` 무효** — `REC-Z3` 앵커 붕괴(§8)가 발동했다"
            "(`PREREG_POST6.md` §4 #52 대칭 쌍 *「`REC-Z3` 앵커 붕괴 시 무효」*). "
            "아래 중앙값은 **인쇄만** 하고 판정으로 쓰지 않는다.")
    if len(d1mids) >= 3:
        ms = [m_ for _, m_, _, _ in d1mids]
        m = med(ms)
        say(f"- (인쇄) `h_max` 중점 중앙값 **{m:.3f}** · 0.50~0.70 "
            f"**{'안' if 0.50 <= m <= 0.70 else '밖'}** · n={len(ms)}")
        sl = [m_ for _, m_, _, lb in d1mids if lb != "SL"]
        if sl and len(sl) != len(ms):
            say(f"- (민감도 A-4) 라벨 `SL` 제외 시 n={len(sl)} · 중앙값 **{med(sl):.3f}**")
    else:
        say(f"- ⇒ ⛔ **`HDR-D1` 판정 불가** — 분모 **{len(d1mids)}건**"
            "(최소 n 3 미달 · `PREREG_POST6.md` §4 #52).")

    # ── §15. P6-R1' ──────────────────────────────────────────────────────
    say()
    say("## §15. `P6-R1'` — `first_only` DD < `full` DD (누적 · 양쪽 각 n >= 2)\n")
    say("`H4`=max(high) over `[D-4,D]` · `H5`=`[D-9,D]` · `H6`=`[D-19,D]` · "
        "`DD` = 1 - min(low over `[D, 종료]`) / H\n")
    say("| 건 | 구분 | 등록일 | 종료 | `DD(H4)` | `DD(H5)` | `DD(H6)` |")
    say("|---|---|---|---|---|---|---|")
    fo_dd = []
    for nm in fo_new:
        v = R[nm]
        row = [dd_h(cur, v["code"], v["d0"], END, k) for k in (5, 10, 20)]
        fo_dd.append((nm, row))
        say(f"| {nm} | `first_only`(신규) | {v['d0']} | {END} | "
            f"{row[0]:.2f}% | {row[1]:.2f}% | {row[2]:.2f}% |")
    say(f"| _{SAM['nm']}_ | _`first_only`(post5 보존)_ | _{SAM['d0']}_ | _2026-08-28_ | "
        f"_{SAM['dd']:.2f}%_ | _{SAM['dd']:.2f}%_ | _{SAM['dd']:.2f}%_ |")
    knr = [dd_h(cur, "199430", "2026-07-28", "2026-08-14", k) for k in (5, 10, 20)]
    say(f"| 케이엔알시스템 | `full`(누적 · 직전 3글) | 2026-07-28 | 2026-08-14 | "
        f"{knr[0]:.2f}% | {knr[1]:.2f}% | {knr[2]:.2f}% |")
    say()
    say("- 🔴 **이번 글 신규 `full` = 0건**(PD-13 *「`P6-R1'`(`full` 신규 0 ⇒ 관측만)」*)")
    say(f"- 누적 n: `first_only` **{len(fo_dd)+1}**(신규 {len(fo_dd)} + post5 삼양 1) · "
        f"(나) 갈래면 **{len(fo_dd)}** · `full` **1**(케이엔알)")
    say("- 문턱 **양쪽 각 n >= 2**(`PREREG_POST6.md` §3-3 이 «처음» 선언 — §18 등재) ⇒ "
        "`full` 1 < 2 ⇒ ⛔ **판정 안 함 · 관측만.**")
    dirn = sum(1 for _, row in fo_dd for a, b in zip(row, knr) if a < b)
    tot = len(fo_dd) * 3
    say(f"- (관측) 방향 일치(`first_only` DD < `full` DD) **{dirn}/{tot}** — 신규 {len(fo_dd)}건 × 세 H 정의. "
        f"post5 삼양은 보존값 기준 3/3 일치 ⇒ 누적 **{dirn+3}/{tot+3}**.")
    say("- 🔴 **판정이 아니다** — `Q1-R1` 은 *「위반 1건이면 기각」* 이라 n=1 짜리 기각을 막으려고 "
        "n >= 2 를 걸었다. 그 문턱이 **지금 실제로 판정을 막고 있다**(§18).")

    # ── §16. 재진입 제외 민감도 ──────────────────────────────────────────
    say()
    say("## §16. 재진입 2건 제외 민감도 (PD-3 · `PREREG_POST6.md` §1-5)\n")
    say("재진입 = 지투파워(`P6-PRIOR_CYCLE_IN_WINDOW`=1) · 현대약품(=0 · 직전 등록일 미상) — "
        "**분모 포함이 주 판정**이고 제외는 의무 민감도다.\n")
    sub = {nm: v for nm, v in R.items() if not v["reent"]}
    s_empty = [nm for nm, v in sub.items() if not v["iv"]]
    s_under = [nm for nm, v in sub.items() if v["under"]]
    s_z3 = [nm for nm in z3_hit if nm in sub]
    s_y1 = [nm for nm, v in sub.items() if len(v["legs"]) >= 4]
    s_y1u = [nm for nm in s_y1 if not sub[nm]["iv"]]
    say("| 항목 | 주 판정(신규 10) | **재진입 2 제외(8건)** | 문턱 | 판정이 뒤집히나 |")
    say("|---|---|---|---|---|")
    say(f"| `REC-Y3` 해 0개 비율 | {len(empty)}/{len(R)} = {100*frac:.1f}% | "
        f"**{len(s_empty)}/{len(sub)} = {100*len(s_empty)/len(sub):.1f}%** | >= 1/3 | "
        f"{'아니오' if (len(s_empty)/len(sub) >= 1/3) == (frac >= 1/3) else '🔴 **예**'} |")
    say(f"| `REC-Z1` 격자 미달 비율 | {z1_n}/{len(R)} = {100*z1_frac:.1f}% | "
        f"**{len(s_under)}/{len(sub)} = {100*len(s_under)/len(sub):.1f}%** | >= 1/3 | "
        f"{'아니오' if (len(s_under)/len(sub) >= 1/3) == (z1_frac >= 1/3) else '🔴 **예**'} |")
    say(f"| `REC-Z3` 앵커 붕괴 비율 | {len(z3_hit)}/{len(R)} = {100*z3_frac:.1f}% | "
        f"**{len(s_z3)}/{len(sub)} = {100*len(s_z3)/len(sub):.1f}%** | >= 1/2 | "
        f"{'아니오' if (len(s_z3)/len(sub) >= 0.5) == (z3_frac >= 0.5) else '🔴 **예**'} |")
    say(f"| `REC-Y1` 대상(레그>=4) | {len(y1_items)}건 · 미정의 {y1_undef} | "
        f"**{len(s_y1)}건 · 미정의 {len(s_y1u)}** | 최소 n 3 | "
        f"{'아니오' if (len(s_y1) >= 3) == (len(y1_items) >= 3) else '🔴 **예**'} |")
    say(f"| `P6-L1'`·`P6-L2'`·`Q1-R3` 분모 | first_only {len(fo_new)} | "
        f"**{len(fo_new)}**(재진입 아님) | — | 아니오 |")

    # ── §17. 봉수 정합 ───────────────────────────────────────────────────
    say()
    say("## §17. 봉수 표기 정합 (N8 승계 — «직전/포함»을 반드시 붙인다)\n")
    say("| 종목 | 등록일 | DB 최초 봉 | 등록일 «직전» 봉수 | 등록일 «포함» 봉수 | "
        "창 `[D, 종료]` 봉수 | 창 `[D-19, D+4]` 봉수 |")
    say("|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        cur.execute("SELECT min(date), count(*) FROM daily_prices WHERE stock_code=%s "
                    "AND date <= %s", (v["code"], v["d0"]))
        mn, inc = cur.fetchone()
        wbn = v.get("winbars")
        if wbn is None:
            wbn = len(win_bars(cur, v["code"], v["d0"], 19, 4))
            v["winbars"] = wbn
        say(f"| {nm} | {v['d0']} | {mn} | {v['prebars']} | {inc} | {v['nbars']} | {wbn} |")
    say()
    trunc = [nm for nm, v in R.items() if v["nbars"] < 5]
    say(f"- 창 `[D, {END}]` 이 5봉 미만인 건: **{len(trunc)}** ({', '.join(trunc) or '없음'}) — "
        "🔴 이 사실은 `LAD-` 축의 **PD-11 창5 절단**과 같은 원인이지만, REC- 축의 창은 "
        f"`[등록일, {END}]` **전체**라 절단 개념이 다르다. 혼동 방지로 나란히 적는다.")

    # ── §18. 처음 정한 문턱 · 모호 지점 ──────────────────────────────────
    say()
    say("## §18. 「이 문서에서 처음 정한 문턱」에 걸렸나 · 모호 지점\n")
    say("| 문턱 | 출처 | 이번 글에서 «걸렸나» |")
    say("|---|---|---|")
    if meas1:
        fis = sorted((f for _, f in L1 if f is not None), reverse=True)
        # 문턱을 t 로 바꿨을 때 (주) 판정이 뒤집히는가 — 뒤집힘 지점을 실제로 찾는다
        flip = None
        base = (sum(1 for f in fis if f >= 0.5) / len(fis)) >= 2 / 3
        for f in fis:
            if ((sum(1 for x in fis if x >= f) / len(fis)) >= 2 / 3) != base:
                flip = f
                break
        verdict05 = ("🔴 **걸렸다** — 문턱을 " + f"**{flip:.4f}** 이하로 내리면 (주) 판정이 뒤집힌다"
                     if flip is not None else
                     "**안 걸렸다** — 어떤 문턱에서도 (주) 판정이 같다")
        say(f"| `frac_in` **0.5** (`P6-L1'`) | `PREREG_POST6.md` §3-4 (신규) | "
            f"관측 `frac_in` = {', '.join(f'{f:.4f}' for f in fis)} ⇒ {verdict05} |")
    else:
        say("| `frac_in` **0.5** (`P6-L1'`) | `PREREG_POST6.md` §3-4 (신규) | "
            "측정 가능 건 0 ⇒ 문턱 무관(⛔) |")
    say("| **n >= 2** (`P6-R1'` 양쪽 각) | `PREREG_POST6.md` §3-3 (신규) | "
        "🔴 **걸렸다** — `full` 누적 1건이라 이 문턱 «때문에» 판정을 안 한다"
        "(문턱이 없었다면 `Q1-R1` 문언 *「위반 1건이면 기각」* 으로 n=1 판정이 섰다) |")
    say(f"| `REC-Z5` **0.022** 판정 / 0.020 민감도 | `PREREG_EXIT_V2.md` §2 · "
        f"`PREREG_POST6.md` §1-7 | "
        + (f"🔴 **걸렸다** — 두 문턱이 {len(split)}건에서 분류를 가른다(「문턱 민감」)"
           if split else "**안 걸렸다** — 두 문턱에서 분류 동일") + " |")
    say(f"| A-7 **0.25 · 과반** (`P6-L3'`) | `PREREG_POST6.md` §3-5(정식등록) | "
        f"{narrow}/{len(R)} vs 과반 {need} ⇒ "
        + ("전제 성립" if narrow >= need else
           "**전제 미달 — 미실행**(문턱을 낮췄다면 돌아갔을 것 — 낮추지 않는다)") + " |")
    say()
    say("### 모호 지점 (양쪽 인쇄 · 어느 쪽도 규칙으로 고르지 않는다)\n")
    say("1. 🔴 **삼양바이오팜의 `frac_in`·«측도가중» `b1` 이 post5 보존값에 없다** — 두 통계량은 "
        "`P6-L1'`·`P6-L2'`(§3-4)가 **post6 에서 처음 정의**했고, PD-12 는 **재계산 금지**다. "
        "⇒ `P6-L1'` 은 (가)·(나) 분모가 **같아지고**(신규 3건), `P6-L2'` 는 "
        "**「범위중점 대입(정의 혼합)」 갈래와 「제외」 갈래를 둘 다 인쇄**했다.")
    say("2. 🔴 **`BUY-L5` 의 정의역** — L5 문언은 *「신규 건 중 되밀린 건」*이고 `REC-Z4` 는 "
        "*「`first_only` 건이 나오면 L5 를 즉시 판정」*이다. **두 정의역을 나란히 인쇄**했다(§11).")
    say("3. 🔴 **`P6-L1'-N` 의 창** — `[D-19, D+4]` 에 등록일 `D` **자신이 포함**된다"
        "(문언 그대로 읽었다). 귀무 비율에 등록일이 `1/(창 봉수)` 만큼 섞인다는 사실을 적어 둔다.")
    say(f"4. 🔴 **⛔ 조건 ②(「feasible 이 빈 집합」)의 «건 단위 vs 분모 단위»** — 해 0개 "
        f"`first_only` 건이 {len(zero1)}건({', '.join(zero1) if zero1 else '없음'}) 있어 "
        "`P6-L1'`·`P6-L2'`·`Q1-R3` 셋 다 이 모호에 걸린다. **주 = 건 단위**(그 건만 분모 밖) · "
        "**⛔ = 분모 단위** 를 §10·§12 에 나란히 인쇄했다. "
        "🔴 방향 자기신고: ⛔ 읽기는 이번 글의 «불성립·기각»을 지우는 쪽 = **가설 A 에 유리**하다 "
        "⇒ 그 쪽으로 규칙을 옮기지 않는다.")
    say("5. 🔴 **최소 n 게이트는 동결 문언 그대로 읽었다** — `P6-L-누적` **3건**(또는 `REC-Z4` 발동 시 "
        "즉시)이며, 「측정 가능 건이 3건 이상」이라는 **새 문턱을 만들지 않았다**"
        "(그 문턱은 §3-4 ⛔ ① *「`first_only` **누적** < 3」* 문언에 없다).")
    say()
    say("🔴 **이 문서는 라이브 채택 대상이 아니다**(`PREREG.md` §0-2). **새 예측을 만들지 않았다** — "
        "동결된 항목(`PREREG_POST6.md` §4 #38~#54)만 계산했다.")

    (BASE / "RESULTS_RECONSTRUCT_POST6_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    print("\n[written] RESULTS_RECONSTRUCT_POST6_NUMBERS.md")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())

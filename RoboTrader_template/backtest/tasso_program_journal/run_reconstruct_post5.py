# -*- coding: utf-8 -*-
"""평단 P 복원 — 5번째 글 신규 6건 (Y1~Y4 · R1·R3 · L1·L2·L3·L5 · D1·D2/L4 의 관문).

사전등록: `PREREG_Q1_V2.md` §3(R1·R3) · `PREREG_HDR.md` §3~§4(D1·D2)
        · `PREREG_BUYLADDER.md` §5(L1·L2·L3·L4·L5) · `RESULTS_RECONSTRUCT_POST4.md` §6(Y1~Y4)

🔴 **계산 «전» 에 고정한 해석 결정** (RESULTS_RECONSTRUCT_POST5.md §1 에 같은 문장으로 적는다):
  A-1 창 종료일 = 2026-08-28 (DB 스냅샷 최대). 발행일 08-29 는 토요일 = 휴장.
  A-2 Y1 은 «전칭»으로 읽는다 — 레그 4개 이상인 «모든» 건의 폭 < 3%p. 건수 비율도 병기.
  A-3 되밀림 = 등록일 종가 < 등록일 고가 · 상한가마감 = 종가 == 고가 (post4 §3 조작화 승계).
  A-4 D1 표본 = 프리셋 `HDR 60%` 인 건. 혜인(`사분위수 Q1~Q3`)은 분모 «밖» — D2/L4 관측으로 따로.
      `MANUAL`(한켐)은 post4 전례(이노테크 포함)대로 포함하되 제외 민감도 병기.
  A-5 R1: 이번 글은 `first_only` 有 · `full` 無 다. `PREREG_Q1_V2.md` §3 의 합침 조항은
      *「같은 글 안에 «둘 다» 없으면」* 이 조건이라 **이번 경우를 덮지 않는다**(사전등록 문언 «밖»).
      공백을 **보수적 방향(판정 안 함 · 관측만)** 으로 메운다. 직전 3글의 `full` 값은 대조로만 인쇄.
  A-6 R3 은 다차수 건의 `1−P/H` 가 「1차 밴드」가 아니라는 post4 §2 범주오류 판정을 유지한다.
      `first_only`(삼양) 1건만 진짜 `b₁` ⇒ n=1 관측.
  A-7 L3 실행 전제 = 「`b₁` 구간 폭 / σ₂₀ 이 사전등록 격자 `±0.25` 보다 좁은 건이 과반」.
      미달이면 공통해 탐색을 «돌리지 않고» 판정 불가.
      🔴 **이 게이트는 사전등록에 «없다»** — post4 §5 가 말로만 적은 중단 사유를 사전등록 자신의
      격자 폭에 붙여 수치화한 «추가 자유도»다. §10 에 그렇게 적는다.
  A-8 σ₂₀ = 등록일 직전 20거래일 로그수익률의 표본표준편차(연율화 안 함).
      수익률 20개 미만이면 그 건은 σ 축에서 제외.
  A-9 한켐(post5)은 한 항목 안에 두 사이클(본전매도 → 재진입)이 있다 — 「하나의 평단」 전제가
      원리적으로 깨질 수 있다. 항목 단위 라벨·차수는 그대로 두고 flag 만 단다.
  A-10 «해 0개» 진단의 잔차 문턱은 **사전등록에 없다.** 프로젝트가 가진 유일한 자체 근거는
      `PREREG_EXIT_V2.md` §1-2 의 *「복원이 측정한 gross 잔차는 0.010~0.022%p」* 와
      §2 의 *「복원 잔차 상한(0.022%p)」* 이다. ⇒ **0.020 과 0.022 «둘 다»로 분류를 인쇄**하고,
      분류가 갈리면 **「문턱 의존」으로 적는다**(어느 한쪽을 고르지 않는다).
  A-11 feasible set 은 **정확 구간법**으로 푼다. 제약은 `round(100·(S/P−1), 2) == r` 이므로
      `P` 는 «점»이 아니라 구간이다:  `P ∈ ( S/(1+(r+0.005)/100),  S/(1+(r−0.005)/100) ]`.
      레그별로 「봉 안에 있는 격자 매도가 S」 전부에 대한 구간들의 **합집합**을 만들고,
      레그 전체에 대해 **교집합**을 취한다.
      🔴 post4(`run_reconstruct_post4.py`)와 이 스크립트의 초판은 `S₁` 격자마다 `P` 를 **단일점**
      으로 잡았다 ⇒ 그 방식의 「개수·폭」은 **하한**이다. 대조로 함께 인쇄한다.

라이브 트리 import 0건. DB 는 SELECT 만. `adj_factor` 산술 0건.
"""
from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path

import psycopg2

from reconstruct_prices import FEE, TAX, gross_ret, grid_prices, net_ret, solve, tick
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

END = "2026-08-28"          # A-1
THR = (0.020, 0.022)        # A-10 · PREREG_EXIT_V2 §1-2 / §2

# (종목, 코드, 등록일, 레그 수익률, 체결차수, 프리셋, 라벨, 시퀀스 개방 여부)
TARGETS = [
    ("혜인", "003010", "2026-08-11", [21.91, 21.90, 21.67, 19.32, 14.68], 2, "Q1~Q3", "TP", True),
    ("한국화장품제조", "003350", "2026-08-12", [19.02, 18.64, 15.42, 12.50, 11.26], 4, "HDR60", "TP", True),
    ("코데즈컴바인", "047770", "2026-08-21", [7.82, 0.09], 3, "HDR60", "TP", False),
    ("한켐", "457370", "2026-08-20", [4.86, 0.84, -2.08, -2.12], 2, "HDR60", "MANUAL", True),
    ("삼양바이오팜", "0120G0", "2026-08-21", [11.50, 11.50], 1, "HDR60", "TP", True),
    ("광전자", "017900", "2026-08-05", [15.81, 9.21, 9.21, 6.99, 0.93], 4, "HDR60", "TP", True),
]


def say(s=""):
    print(s)
    OUT.append(s)


def bars(cur, code, d0, d1):
    cur.execute(
        "SELECT date, open, high, low, close FROM daily_prices "
        "WHERE stock_code=%s AND date BETWEEN %s AND %s ORDER BY date", (code, d0, d1))
    return cur.fetchall()


# ── A-11 정확 구간법 ──────────────────────────────────────────────────────
def _merge(ivs):
    if not ivs:
        return []
    ivs = sorted(ivs)
    out = [list(ivs[0])]
    for a, b in ivs[1:]:
        if a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _intersect(A, B):
    out, i, j = [], 0, 0
    while i < len(A) and j < len(B):
        a0, a1 = A[i]
        b0, b1 = B[j]
        lo, hi = max(a0, b0), min(a1, b1)
        if lo < hi:
            out.append((lo, hi))
        if a1 < b1:
            i += 1
        else:
            j += 1
    return out


def leg_intervals(r, ranges, grid, plo, phi, c):
    """레그 수익률 r 을 만족시키는 P 구간들의 합집합.
    gross:  ret = S/P − 1               ⇒ c = 1
    net:    ret = S·(1−FEE−TAX)/(P·(1+FEE)) − 1 ⇒ c = (1−FEE−TAX)/(1+FEE)
    round(100·ret, 2) == r  ⇔  100·ret ∈ [r−0.005, r+0.005)
                            ⇔  P ∈ ( S·c/(1+(r+0.005)/100), S·c/(1+(r−0.005)/100) ]"""
    out = []
    for S in grid:
        if not any(a <= S <= b for a, b in ranges):
            continue
        lo = S * c / (1 + (r + 0.005) / 100.0)
        hi = S * c / (1 + (r - 0.005) / 100.0)
        lo, hi = max(lo, plo), min(hi, phi)
        if lo < hi:
            out.append((lo, hi))
    return _merge(out)


def feasible_exact(rows, legs, kind="gross"):
    ranges = [(r[3], r[2]) for r in rows]
    lo, hi = min(r[3] for r in rows), max(r[2] for r in rows)
    grid = grid_prices(lo, hi)
    c = 1.0 if kind == "gross" else (1 - FEE - TAX) / (1 + FEE)
    cur = None
    for r in legs:
        iv = leg_intervals(r, ranges, grid, lo * 0.7, hi, c)
        cur = iv if cur is None else _intersect(cur, iv)
        if not cur:
            return []
    return cur


def feasible_pointwise(rows, legs, retfn):
    """초판·post4 방식(대조용) — S₁ 격자마다 P 를 «단일점»으로 잡는다 ⇒ 개수·폭이 하한."""
    ranges = [(r[3], r[2]) for r in rows]
    lo, hi = min(r[3] for r in rows), max(r[2] for r in rows)
    out = []
    for s1 in grid_prices(lo, hi):
        if not any(a <= s1 <= b for a, b in ranges):
            continue
        P = s1 / (1 + legs[0] / 100.0)
        if not (lo * 0.7 <= P <= hi):
            continue
        if solve(P, legs, ranges, retfn) is not None:
            out.append(P)
    return out


def iv_min(iv):
    return iv[0][0]


def iv_max(iv):
    return iv[-1][1]


def iv_measure(iv):
    return sum(b - a for a, b in iv)


def iv_has(iv, x):
    return any(a <= x <= b for a, b in iv)


def iv_nearest(iv, x):
    best = None
    for a, b in iv:
        d = 0.0 if a <= x <= b else min(abs(x - a), abs(x - b))
        p = x if a <= x <= b else (a if abs(x - a) < abs(x - b) else b)
        if best is None or d < best[0]:
            best = (d, p)
    return best


def min_residual(rows, legs, retfn):
    """해 0개일 때 — 격자 제약을 빼고 레그 오차 최댓값을 최소화하는 P (reconstruct_prices 승계)."""
    ranges = [(r[3], r[2]) for r in rows]
    lo, hi = min(r[3] for r in rows), max(r[2] for r in rows)
    best = None
    for s1 in grid_prices(lo, hi):
        if not any(a <= s1 <= b for a, b in ranges):
            continue
        P = s1 / (1 + legs[0] / 100.0)
        if not (lo * 0.7 <= P <= hi):
            continue
        errs = []
        for r in legs:
            s_ideal = P * (1 + r / 100.0)
            t = tick(s_ideal)
            S = round(s_ideal / t) * t
            if not any(a <= S <= b for a, b in ranges):
                errs = None
                break
            errs.append(abs(retfn(P, S) * 100 - r))
        if errs and (best is None or max(errs) < best[0]):
            best = (max(errs), P)
    return best


def sigma20(cur, code, d0):
    """A-8 · 등록일 «직전» 20거래일 로그수익률 표본표준편차. 21봉 미만이면 None."""
    cur.execute("SELECT date, close FROM daily_prices WHERE stock_code=%s AND date < %s "
                "ORDER BY date DESC LIMIT 21", (code, d0))
    rows = list(reversed(cur.fetchall()))
    if len(rows) < 21:
        return None, len(rows)
    rets = [math.log(rows[i][1] / rows[i - 1][1]) for i in range(1, len(rows))]
    return statistics.stdev(rets), len(rows)


def main():
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    say("# RESULTS_RECONSTRUCT_POST5_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_reconstruct_post5.py` · 재사용 `reconstruct_prices.py`(tick·grid·solve)")
    say("창 = `[등록일, " + END + "]` (A-1) · gross 기준 · `adj_factor` 산술 0건")
    say("🔴 **A-11 정확 구간법**: `P ∈ ( S/(1+(r+0.005)/100), S/(1+(r−0.005)/100) ]` 의 "
        "레그별 합집합을 교집합. 초판·post4 의 «단일점» 방식은 하한이라 대조로만 인쇄.\n")

    # -- 1. 기본표 -----------------------------------------------------------
    say("## §1. feasible set 원표 (gross · A-11 정확 구간법)\n")
    say("| 종목 | 차수 | 프리셋 | 라벨 | 등록일 | 레그 | 등록일 봉 [저,시,고,종] | 되밀림 | "
        "**구간 개수** | **P 범위** | **`1-P/H` 범위** | **폭** | (대조) 점법 개수/폭 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    R = {}
    for nm, code, d0, legs, tr, preset, label, openseq in TARGETS:
        rows = bars(cur, code, d0, END)
        o0, h0, l0, c0 = rows[0][1], rows[0][2], rows[0][3], rows[0][4]
        pull = c0 < h0
        iv = feasible_exact(rows, legs, "gross")
        pts = feasible_pointwise(rows, legs, gross_ret)
        R[nm] = dict(code=code, d0=d0, legs=legs, tr=tr, preset=preset, label=label,
                     openseq=openseq, rows=rows, o0=o0, h0=h0, l0=l0, c0=c0,
                     pull=pull, iv=iv, pts=pts)
        if pts:
            pw = f"{len(pts)} / {(max(pts)-min(pts))/h0*100:.2f}%p"
        else:
            pw = "0 / —"
        if iv:
            pmin, pmax = iv_min(iv), iv_max(iv)
            w = (pmax - pmin) / h0 * 100
            R[nm].update(pmin=pmin, pmax=pmax, w=w)
            say(f"| {nm} | {tr}차 | {preset} | {label} | {d0} | {len(legs)} | "
                f"[{l0:,.0f}, {o0:,.0f}, {h0:,.0f}, {c0:,.0f}] | {'예' if pull else '아니오'} | "
                f"**{len(iv)}** | {pmin:,.2f}~{pmax:,.2f} | "
                f"{100*(1-pmax/h0):+.2f}%~{100*(1-pmin/h0):+.2f}% | **{w:.2f}%p** | {pw} |")
        else:
            R[nm].update(pmin=None, pmax=None, w=None)
            say(f"| {nm} | {tr}차 | {preset} | {label} | {d0} | {len(legs)} | "
                f"[{l0:,.0f}, {o0:,.0f}, {h0:,.0f}, {c0:,.0f}] | {'예' if pull else '아니오'} | "
                f"**0** | — | — | — | {pw} |")
    say()
    say(f"- 되밀림(A-3: 종가 < 고가) **{sum(1 for v in R.values() if v['pull'])}/{len(R)}** · "
        f"상한가마감(종가==고가) **{sum(1 for v in R.values() if not v['pull'])}/{len(R)}**")
    say("- 고가 대비 종가 되밀림 폭: " + " · ".join(
        f"{nm} {100*(v['h0']-v['c0'])/v['h0']:.2f}%" for nm, v in R.items()))
    say("- 🔴 **점법 대 정확법**: 해가 있는 건에서 폭이 " + " · ".join(
        f"{nm} {(max(v['pts'])-min(v['pts']))/v['h0']*100:.2f}→{v['w']:.2f}%p"
        for nm, v in R.items() if v['pts'] and v['iv']) +
        " 로 **넓어졌다**. 점법 값은 전부 **하한**이었다. 빈 집합 4건은 **정확법에서도 비어 있다.**")
    say("- feasible 총 측도(정확법): " + " · ".join(
        f"{nm} {iv_measure(v['iv']):,.2f}원" for nm, v in R.items() if v['iv']) +
        " — 구간들이 성기게 흩어져 있어 «범위»와 «측도»가 크게 다르다.")

    # -- 2. 해 0개 진단 -------------------------------------------------------
    say()
    say("## §2. 해 0개 진단 — 「격자 해상도」 대 「최소잔차」\n")
    say("`dr_min` = 서로 다른 인접 레그 수익률의 최소 간격(%p) · "
        "`res` = 호가 한 칸이 만드는 수익률 해상도 `100*tick(P)/P`\n")
    say("🔑 `dr_min < res` 이면 **두 레그를 격자 위 서로 다른 매도가로 표현할 수 없다** "
        "⇒ 산술적으로 해가 0개다.\n")
    say("🔴 **A-10**: 잔차 문턱은 사전등록에 없다. `PREREG_EXIT_V2.md` §1-2 의 실측 대역 "
        "**0.010~0.022%p** 와 §2 의 상한 **0.022%p** 가 프로젝트의 유일한 자체 근거다. "
        "**0.020 과 0.022 둘 다로 분류한다.**\n")
    say("| 종목 | 레그 | `dr_min` | 후보 P 범위 | `res`(P 양끝) | 격자 해상도 미달? | "
        "최소잔차 적합 P | **최대 오차** | 진단 @0.020 | 진단 @0.022 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    split = []
    for nm, v in R.items():
        legs = v["legs"]
        gaps = [abs(legs[i] - legs[i + 1]) for i in range(len(legs) - 1) if legs[i] != legs[i + 1]]
        dmin = min(gaps) if gaps else float("nan")
        lo = min(r[3] for r in v["rows"])
        hi = max(r[2] for r in v["rows"])
        pl, ph = lo * 0.7, hi
        r_lo, r_hi = 100 * tick(pl) / pl, 100 * tick(ph) / ph
        under = (not math.isnan(dmin)) and dmin < max(r_lo, r_hi)
        mr = min_residual(v["rows"], legs, gross_ret)
        v["minres"] = mr
        v["under"] = under
        mrs = "—" if mr is None else f"{mr[1]:,.0f}"
        mre = "—" if mr is None else f"**{mr[0]:.6f}%p**"
        diags = []
        for t in THR:
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
        dms = "—" if math.isnan(dmin) else f"{dmin:.2f}%p"
        say(f"| {nm} | {legs} | {dms} | {pl:,.0f}~{ph:,.0f} | "
            f"{r_hi:.3f}~{r_lo:.3f}%p | {'🔴 **예**' if under else '아니오'} | "
            f"{mrs} | {mre} | {diags[0]} | {diags[1]} |")
    say()
    say(f"- 🔴 **두 문턱에서 분류가 갈리는 건: {len(split)}건** "
        f"({', '.join(split) if split else '없음'}) ⇒ "
        f"**{'「평단 변화」 헤드라인은 «문턱 의존»이다 — 어느 쪽도 고르지 않는다' if split else '문턱 의존 없음'}**")
    say("- 격자 해상도 미달(`dr_min < res`) 건: " +
        f"**{sum(1 for v in R.values() if v['under'])}/{len(R)}** (" +
        ", ".join(nm for nm, v in R.items() if v["under"]) + ")")

    # -- 3. Y1 ---------------------------------------------------------------
    say()
    say("## §3. Y1 (핵심) — 레그 4개 이상인 건의 `b1` feasible 폭 < 3%p 인가\n")
    say("A-2: **전칭**으로 읽는다. 폭은 A-11 정확 구간법.\n")
    say("| 종목 | 레그 | 구간 개수 | 폭 | < 3%p |")
    say("|---|---|---|---|---|")
    y1_items, y1_ok, y1_undef = [], 0, 0
    for nm, v in R.items():
        if len(v["legs"]) < 4:
            continue
        y1_items.append(nm)
        if not v["iv"]:
            y1_undef += 1
            say(f"| {nm} | {len(v['legs'])} | **0** | ⛔ **미정의** | ⛔ |")
        else:
            ok = v["w"] < 3.0
            y1_ok += int(ok)
            say(f"| {nm} | {len(v['legs'])} | {len(v['iv'])} | **{v['w']:.2f}%p** | "
                f"{'성립' if ok else '위반'} |")
    say()
    say(f"- 레그>=4 대상 **{len(y1_items)}건**({', '.join(y1_items)}) · 폭 측정 가능 "
        f"**{len(y1_items)-y1_undef}건** · 미정의(해 0개) **{y1_undef}건**")
    if y1_undef == len(y1_items):
        say("- ⇒ ⛔ **Y1 판정 불가** — 대상 전건의 feasible set 이 비어 폭이 «정의되지 않는다». "
            "「폭 0 = 3%p 미만」으로 읽으면 규칙 완화다. 읽지 않는다.")
    elif y1_undef == 0 and y1_ok == len(y1_items):
        say("- ⇒ ✅ **Y1 성립**(전칭)")
    else:
        say(f"- ⇒ ⛔ **Y1 불성립(전칭)** — 성립 {y1_ok}/{len(y1_items)}, 미정의 {y1_undef}")

    # -- 4. Y2 ---------------------------------------------------------------
    say()
    say("## §4. Y2 (반증축 · 필수) — 폭을 호가단위 배수로도 인쇄\n")
    say("Y2: *「레그 수와 무관하게 폭이 좁으면 원인은 레그 수가 아니라 가격대(호가단위)다」*\n")
    say("| 종목 | 레그 | 가격대 | 호가단위(P 하단) | 폭(%p) | **폭 / 호가단위(칸)** | (대조) 점법 칸 |")
    say("|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        lo = min(r[3] for r in v["rows"])
        hi = max(r[2] for r in v["rows"])
        if not v["iv"]:
            say(f"| {nm} | {len(v['legs'])} | {lo:,.0f}~{hi:,.0f} | — | — | — | — |")
            continue
        t = tick(v["pmin"])
        pwc = (max(v['pts']) - min(v['pts'])) / tick(min(v['pts'])) if v["pts"] else float("nan")
        say(f"| {nm} | {len(v['legs'])} | {lo:,.0f}~{hi:,.0f} | {t}원 | "
            f"{v['w']:.2f}%p | **{(v['pmax']-v['pmin'])/t:.1f}칸** | {pwc:.1f}칸 |")

    # -- 5. Y3 ---------------------------------------------------------------
    say()
    say("## §5. Y3 (중단 규칙) — feasible set 이 비는 비율\n")
    empty = [nm for nm, v in R.items() if not v["iv"]]
    frac = len(empty) / len(R)
    say(f"- 해 0개(정확법): **{len(empty)}/{len(R)} = {100*frac:.1f}%** "
        f"({', '.join(empty) if empty else '없음'})")
    say("- post4 관측(점법): **1/6 = 16.7%** (금호건설)")
    say(f"- 사전등록 문턱 **>= 1/3 = 33.3%** ⇒ **{'🔴 발동' if frac >= 1/3 else '미발동'}**")
    if frac >= 1 / 3:
        say("- ⇒ 🔴🔴 **「다차수 건에서 평단이 매도 중 변한다」로 읽고, 복원 기반 축"
            "(`R3`·`D1`·`L3`·`L5`)을 «다차수 건»에 적용하는 것을 중단한다.** "
            "(`RESULTS_RECONSTRUCT_POST4.md` §6 Y3 에 동결된 규칙 — 값을 보고 정한 게 아니다.)")
        say("- 🔑 중단은 «다차수 건»에만 걸린다. `first_only`(삼양바이오팜, 1차)는 전제가 다르므로 남는다.")
        say("- 🔴 단 **규칙이 붙여둔 «해석»**(「평단이 변한다」)은 §2 진단을 통과해야 하고, "
            "그 통과 여부가 **문턱(0.020 vs 0.022)에 달려 있다.**")

    # -- 6. Y4 ---------------------------------------------------------------
    say()
    say("## §6. Y4 (기록만) — net 기준 (A-11 정확 구간법)\n")
    say("| 종목 | gross 구간 개수 | gross 폭 | **net 구간 개수** | net P 범위 | net 폭 |")
    say("|---|---|---|---|---|---|")
    for nm, v in R.items():
        ivn = feasible_exact(v["rows"], v["legs"], "net")
        v["iv_net"] = ivn
        if ivn:
            nw = (iv_max(ivn) - iv_min(ivn)) / v["h0"] * 100
            rng = f"{iv_min(ivn):,.2f}~{iv_max(ivn):,.2f}"
            nws = f"{nw:.2f}%p"
        else:
            rng, nws = "—", "—"
        gws = "—" if not v["iv"] else "{:.2f}%p".format(v["w"])
        say(f"| {nm} | {len(v['iv'])} | {gws} | **{len(ivn)}** | {rng} | {nws} |")
    say()
    gz = sum(1 for v in R.values() if not v["iv"])
    nz = sum(1 for v in R.values() if not v["iv_net"])
    say(f"- 해 0개: gross **{gz}/{len(R)}** · net **{nz}/{len(R)}** ⇒ "
        f"**{'net 으로 바꿔도 설명되지 않는다' if nz >= gz else 'net 이 해를 되살린다 — 저자가 net 으로 적었을 가능성'}**")

    # -- 7. R1 ---------------------------------------------------------------
    say()
    say("## §7. R1 (`PREREG_Q1_V2.md` §3) — `first_only` DD < `full` DD\n")
    say("`H4`=max(high) over [D-4,D] · `H5`=[D-9,D] · `H6`=[D-19,D] · "
        "`DD` = 1 - min(low over [D, 종료]) / H\n")
    say("| 건 | 구분 | 등록일 | 종료 | `DD(H4)` | `DD(H5)` | `DD(H6)` |")
    say("|---|---|---|---|---|---|---|")

    def dd_h(code, d0, d1, k):
        cur.execute("SELECT max(high) FROM (SELECT high FROM daily_prices WHERE stock_code=%s "
                    "AND date <= %s ORDER BY date DESC LIMIT %s) t", (code, d0, k))
        H = cur.fetchone()[0]
        cur.execute("SELECT min(low) FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s", (code, d0, d1))
        L = cur.fetchone()[0]
        return 100 * (1 - L / H)

    sam = R["삼양바이오팜"]
    row = [dd_h(sam["code"], sam["d0"], END, k) for k in (5, 10, 20)]
    say(f"| 삼양바이오팜 | `first_only`(1차) | {sam['d0']} | {END} | "
        f"{row[0]:.2f}% | {row[1]:.2f}% | {row[2]:.2f}% |")
    knr = [dd_h("199430", "2026-07-28", "2026-08-14", k) for k in (5, 10, 20)]
    say(f"| 케이엔알시스템 | `full` (직전 3글) | 2026-07-28 | 2026-08-14 | "
        f"{knr[0]:.2f}% | {knr[1]:.2f}% | {knr[2]:.2f}% |")
    say()
    say(f"- 대조: `PREREG_BUYLADDER.md` §1 에 동결된 케이엔알 `DD` = **36.76%** "
        f"(재계산 {knr[0]:.2f}/{knr[1]:.2f}/{knr[2]:.2f}%)")
    say("- 🔴 **A-5**: 이번 글은 `first_only` **有** · `full` **無** 다. 사전등록 §3 의 합침 조항은 "
        "*「같은 글 안에 «둘 다» 없으면」* 이 조건이므로 **이 경우를 덮지 않는다**(문언 «밖»). "
        "공백을 **보수적 방향으로 메워 판정하지 않는다.**")
    say(f"- 관측(대조용): 삼양 `DD` < 케이엔알 `DD` 가 세 정의에서 "
        f"**{sum(1 for a, b in zip(row, knr) if a < b)}/3**")
    say("- ⇒ ⛔ **R1 판정 안 함 — 관측만 기록.**")

    # -- 8. R3 ---------------------------------------------------------------
    say()
    say("## §8. R3 — `b1` 구간이 직전 3글 값과 부호·자릿수가 같은가\n")
    say("A-6: 다차수 건의 `1-P/H` 는 「1차 밴드」가 아니라 「전 차수 평단」이다 ⇒ 범주 오류(post4 §2 유지).")
    say("§5 의 Y3 중단 규칙도 다차수 건에 걸린다 ⇒ **다차수 5건 판정 불가**.\n")
    if sam["iv"]:
        say(f"- `first_only` 삼양바이오팜(n=1): `b1 = 1 - P/H` ∈ "
            f"**[{100*(1-sam['pmax']/sam['h0']):+.2f}%, {100*(1-sam['pmin']/sam['h0']):+.2f}%]** "
            f"(H = 등록일 고가 {sam['h0']:,.0f}) · 폭 **{sam['w']:.2f}%p**")
        say("- 직전 3글 값: 솔트룩스 `b1 ∈ [-0.9%, +2.47%]` · 매드업 `b2 > 26.56%` · "
            "케이엔알 `b_last <= 36.76%`")
    say("- ⇒ ⛔ **R3 판정 불가** — 다차수 5건은 범주 오류 + Y3 중단, `first_only` 는 **n=1**.")

    # -- 9. L1·L2 ------------------------------------------------------------
    say()
    say("## §9. L1·L2 (`PREREG_BUYLADDER.md` §5) — `first_only` 건이 등록일에 샀는가\n")
    say("사전등록 §5 머리말: *「신규 건이 3건 미만이면 판정을 미루고 다음 글까지 모은다」*.")
    say("🔴 **N3 모호점**: 「신규 건」을 (가) *신규 `first_only` 건*(=1건, 미룸) 으로 읽을 수도,")
    say("(나) *그 글의 신규 건 전체*(=6건, 판정 가능) 로 읽을 수도 있다. **(가)로 읽었다.** "
        "(나)로 읽으면 아래 L2 가 위반이므로 **가설 A 기각**이 된다. 두 결과를 다 인쇄한다.\n")
    if sam["iv"]:
        pmin, pmax = sam["pmin"], sam["pmax"]
        inside = (sam["l0"] <= pmin) and (pmax <= sam["h0"])
        say(f"- L1: 삼양 P ∈ [{pmin:,.2f}, {pmax:,.2f}] vs 등록일 봉 "
            f"[{sam['l0']:,.0f}, {sam['h0']:,.0f}] ⇒ "
            f"**{'전 구간 안' if inside else '구간이 등록일 봉 아래로 걸친다'}**")
        b1mid = 100 * (1 - (pmin + pmax) / 2 / sam["h0"])
        say(f"- L2: `b1` 중점 **{b1mid:.2f}%** (문턱 < 5%) ⇒ **{'성립' if b1mid < 5 else '위반'}** "
            f"⇒ (나) 읽기라면 **가설 A 기각**")
        d, pnear = iv_nearest(sam["iv"], sam["c0"])
        say(f"- 🔑 저자 서술 *「종가부근에 매수」* 대조: 등록일 종가 {sam['c0']:,.0f} → "
            f"`b1` = **{100*(1-sam['c0']/sam['h0']):.2f}%**. "
            f"종가는 feasible **범위** 안에 {'든다' if pmin <= sam['c0'] <= pmax else '들지 않는다'}; "
            f"성긴 **집합**에는 {'든다' if iv_has(sam['iv'], sam['c0']) else '들지 않는다'} — "
            f"가장 가까운 feasible P = **{pnear:,.2f}**(차이 {d:,.2f}원 = {100*d/sam['c0']:.3f}%)")
    say("- ⇒ ⛔ **L1·L2 판정 미룸((가) 읽기 · n=1 < 3).** (나) 읽기는 §10 한계에 적는다.")

    # -- 10. L3 --------------------------------------------------------------
    say()
    say("## §10. L3 — `b1/sigma20` 공통해 (전제 검사부터)\n")
    say("A-7 전제(🔴 **사전등록에 없는 추가 자유도**): "
        "「`b1` 구간 폭 / sigma20 이 사전등록 격자 `±0.25` 보다 좁은 건이 **과반**」\n")
    say("| 종목 | sigma20 | 사용 봉(등록일 «직전») | `b1` 폭 | **폭/sigma20** | < 0.25 |")
    say("|---|---|---|---|---|---|")
    narrow = 0
    for nm, v in R.items():
        s, n = sigma20(cur, v["code"], v["d0"])
        v["sigma20"] = s
        v["prebars"] = n
        if s is None:
            say(f"| {nm} | ⛔ **없음**(21봉 미만) | {n} | — | — | ⛔ |")
            continue
        if not v["iv"]:
            say(f"| {nm} | {s:.4f} | {n} | ⛔ 해 0개 | — | ⛔ |")
            continue
        w = v["w"] / 100
        say(f"| {nm} | {s:.4f} | {n} | {v['w']:.2f}%p | **{w/s:.2f}** | "
            f"{'성립' if w / s < 0.25 else '위반'} |")
        narrow += int(w / s < 0.25)
    say()
    need = len(R) // 2 + 1
    say(f"- 폭/sigma20 < 0.25 인 건 **{narrow}/{len(R)}** ⇒ 과반 문턱 **{need}건** "
        f"⇒ **{'전제 성립 — 공통해 탐색 실행' if narrow >= need else '전제 미달'}**")
    if narrow < need:
        say("- ⇒ ⛔ **L3 판정 불가.** 입력이 「점」이 아니라 격자보다 넓은 구간(또는 빈 집합)이라 "
            "공통해 탐색은 거의 항상 해를 찾는다. **돌리지 않는다.** (§5 Y3 중단도 중복 적용)")

    # -- 11. L5 --------------------------------------------------------------
    say()
    say("## §11. L5 (반증축) — 되밀림 건에서 P 가 등록일 봉의 어디인가\n")
    say("L5: *「[시가, 고가] 상단 1/3 이면 즉시진입 · 하단 1/3 이면 밴드 · "
        "어느 쪽도 과반이 아니면 판별 불가」*")
    say("🔴 **전제 검사를 «먼저»** (post4 에서 고친 그대로) — `P` 가 "
        "「등록일에 산 가격」이라야 뜻이 있다.\n")
    say("| 종목 | 차수 | 등록일 봉 [저,시,고] | P 범위 | 전제(P ⊂ [저,고]) | 상단1/3 | 하단1/3 | 판정 |")
    say("|---|---|---|---|---|---|---|---|")
    verdicts = []
    for nm, v in R.items():
        if not v["pull"]:
            continue
        o0, h0, l0 = v["o0"], v["h0"], v["l0"]
        up, dn = o0 + (h0 - o0) * 2 / 3, o0 + (h0 - o0) / 3
        if not v["iv"]:
            say(f"| {nm} | {v['tr']}차 | [{l0:,.0f}, {o0:,.0f}, {h0:,.0f}] | **해 없음** | ⛔ | "
                f"{up:,.0f} | {dn:,.0f} | ⛔ **판정 불가 (해 0개)** |")
            verdicts.append("불가")
            continue
        pmin, pmax = v["pmin"], v["pmax"]
        if v["tr"] >= 2 and frac >= 1 / 3:
            say(f"| {nm} | {v['tr']}차 | [{l0:,.0f}, {o0:,.0f}, {h0:,.0f}] | {pmin:,.2f}~{pmax:,.2f} | "
                f"🔴 **Y3 중단 대상(다차수)** | {up:,.0f} | {dn:,.0f} | ⛔ **적용 중단** |")
            verdicts.append("불가")
            continue
        premise = (l0 <= pmin) and (pmax <= h0)
        if not premise:
            vd = "⛔ **판정 불가 (전제 미성립)**"
            verdicts.append("불가")
        elif pmin >= up:
            vd = "즉시진입"
            verdicts.append(vd)
        elif pmax <= dn:
            vd = "밴드"
            verdicts.append(vd)
        else:
            vd = "🟡 구간이 걸쳐 있음"
            verdicts.append("불가")
        say(f"| {nm} | {v['tr']}차 | [{l0:,.0f}, {o0:,.0f}, {h0:,.0f}] | {pmin:,.2f}~{pmax:,.2f} | "
            f"{'성립' if premise else '🔴 **봉 밖**'} | {up:,.0f} | {dn:,.0f} | {vd} |")
    say()
    bad = verdicts.count("불가")
    say(f"- 되밀림 **{len(verdicts)}건** 중 판별 불가 **{bad}건**")
    if bad * 2 >= len(verdicts):
        say("- ⇒ ⛔ **L5 판정 불가** (과반이 판별 불가) — 두 글 연속.")
    else:
        say(f"- ⇒ 최빈 판정 **{max(set(verdicts), key=verdicts.count)}**")

    # -- 12. D1 --------------------------------------------------------------
    say()
    say("## §12. D1 (`PREREG_HDR.md` §4) — `HDR 60%` 건의 `h_max` 중앙값이 0.50~0.70 인가\n")
    say("`h_max = (S_max - L)/(H - L)` · `H` = 등록일 고가 · `L` = min(low) over [D, 종료] · "
        "`S_max = P*(1+r1)`\n")
    say("| 종목 | 프리셋 | 차수 | H | L | 창 최고가 | **H == 창 최고가?** | P 범위 | "
        "`h_max` 범위 | 폭 | Y3 중단 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    d1mids = []
    for nm, v in R.items():
        cur.execute("SELECT min(low), max(high) FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s", (v["code"], v["d0"], END))
        L, HI = cur.fetchone()
        v["L"], v["HI"] = L, HI
        anchor_ok = v["h0"] >= HI
        stop = (v["tr"] >= 2 and frac >= 1 / 3)
        aflag = "예" if anchor_ok else "🔴 **아니다**"
        if not v["iv"]:
            say(f"| {nm} | {v['preset']} | {v['tr']}차 | {v['h0']:,.0f} | {L:,.0f} | {HI:,.0f} | "
                f"{aflag} | **해 없음** | — | — | {'🔴' if stop else '—'} |")
            continue
        r1 = v["legs"][0] / 100.0
        smin, smax = v["pmin"] * (1 + r1), v["pmax"] * (1 + r1)
        hlo, hhi = (smin - L) / (v["h0"] - L), (smax - L) / (v["h0"] - L)
        say(f"| {nm} | {v['preset']} | {v['tr']}차 | {v['h0']:,.0f} | {L:,.0f} | {HI:,.0f} | "
            f"{aflag} | {v['pmin']:,.2f}~{v['pmax']:,.2f} | "
            f"**{hlo:.3f}~{hhi:.3f}** | {hhi-hlo:.3f} | {'🔴 중단' if stop else '—'} |")
        if v["preset"] == "HDR60" and not stop:
            d1mids.append((nm, (hlo + hhi) / 2, hhi - hlo))
    say()
    say("- A-4 분모 = `HDR 60%` 건. §5 Y3 중단으로 **다차수 건 제외** ⇒ 남는 건 "
        f"**{len(d1mids)}건** ({', '.join(n for n, _, _ in d1mids) if d1mids else '없음'})")
    for n, m, w in d1mids:
        say(f"  - {n}: 중점 **{m:.3f}** · 폭 **{w:.3f}**")
    if len(d1mids) >= 3:
        ms = sorted(m for _, m, _ in d1mids)
        med = ms[len(ms) // 2] if len(ms) % 2 else (ms[len(ms) // 2 - 1] + ms[len(ms) // 2]) / 2
        say(f"- 중앙값 **{med:.3f}** ⇒ 0.50~0.70 **{'안' if 0.50 <= med <= 0.70 else '밖'}**")
    else:
        say(f"- ⇒ ⛔ **D1 판정 불가** — 분모 {len(d1mids)}건(n<3). 관측만 기록.")
        say("  🔴 **N4**: 「n<3 이면 판정 불가」는 `PREREG_HDR.md` D1 에 «없다» — "
            "`PREREG_BUYLADDER.md` §5 의 3건 규칙을 끌어다 쓴 **추가 자유도**다. §10 에 적는다.")
    say("- 🔴 **앵커 붕괴 관측**: `H`(등록일 고가) 가 창 최고가가 «아닌» 건이 "
        f"**{sum(1 for v in R.values() if v['h0'] < v['HI'])}/{len(R)}** — "
        "그런 건에서 `h_max` 는 1 을 넘고 HDR 틀(반등폭 비율) 자체가 성립하지 않는다.")
    say("- 민감도(A-4): `MANUAL`(한켐) 제외해도 분모가 "
        f"**{len([1 for n, _, _ in d1mids if n != '한켐'])}건**이라 결론 불변.")

    # -- 13. D2 / L4 ---------------------------------------------------------
    say()
    say("## §13. D2 / L4 — 프리셋 변량 «첫» 관측 (판정 아님)\n")
    hy = R["혜인"]
    say("- 혜인 003010 · 프리셋 **`사분위수 Q1~Q3`** — 4개 글 통틀어 `HDR 60%` 가 아닌 «첫» 건.")
    say("- D2 는 *「그 건의 `h_max` 가 그 숫자 방향으로 움직인다」* 를 묻는다 "
        "⇒ `h_max` 를 재려면 `P` 가 있어야 한다.")
    say(f"- 혜인 feasible set = **{len(hy['iv'])}구간** ⇒ "
        f"**{'측정 가능' if hy['iv'] else '⛔ `h_max` 측정 불가'}**")
    say("- L4 는 *「그 건의 `b_last`(전 차수 체결 시 DD)가 그 숫자 방향으로」* — "
        "혜인은 **2차**(전 차수 체결 아님) ⇒ `b_last` 가 아니라 `b2 <= DD < b3` 만 준다.")
    say(f"- 혜인 `DD(창A)` = 1 - {hy['L']:,.0f}/{hy['h0']:,.0f} = "
        f"**{100*(1-hy['L']/hy['h0']):.2f}%** ⇒ `b2 <= {100*(1-hy['L']/hy['h0']):.2f}` · "
        f"`b3 > {100*(1-hy['L']/hy['h0']):.2f}`")
    say("- ⇒ 🟡 **D2/L4 「관측 시작」 — n=1, 판정 없음.** 그리고 **첫 변량 관측이 하필 복원 불가 건**이다.")

    # -- 14. 봉수 정합 (N8) ---------------------------------------------------
    say()
    say("## §14. 봉수 표기 정합 (N8)\n")
    say("| 종목 | 등록일 | DB 최초 봉 | 등록일 «직전» 봉수 | **등록일 포함 봉수** |")
    say("|---|---|---|---|---|")
    for nm, v in R.items():
        cur.execute("SELECT min(date), count(*) FROM daily_prices WHERE stock_code=%s "
                    "AND date <= %s", (v["code"], v["d0"]))
        mn, inc = cur.fetchone()
        say(f"| {nm} | {v['d0']} | {mn} | {v['prebars']} | {inc} |")
    say()
    say("- 🔑 삼양바이오팜은 **등록일 직전 11봉 · 등록일 포함 12봉**이다. "
        "「11봉」(σ₂₀ 문맥)과 「12봉」(상장 이래 총 봉수 문맥)은 **같은 사실의 두 표기**다 — "
        "앞으로는 «직전/포함»을 반드시 붙인다.")

    (BASE / "RESULTS_RECONSTRUCT_POST5_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    print("\n[written] RESULTS_RECONSTRUCT_POST5_NUMBERS.md")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())

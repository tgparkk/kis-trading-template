# -*- coding: utf-8 -*-
"""평단 P 복원 — 7번째 글 (REC-Y1~Y4 · REC-Z1~Z5 · Q1-R3 · HDR-D1 · P6-R1' · first_only 관측).

사전등록: `PREREG_POST6.md` §1-7(`REC-Z5`) · §2-6(`REC-Z1`~`Z5`) · §2-7(`REC-Y1`~`Y4` · A-1~A-11 승계)
        · §3-3(`P6-R1'`) · §3-6(정확 구간법 단일화) · §4 표 #38~#54 · §5-6(C-22)
        · `PREREG_HDR.md` §4(D1) · `PREREG_Q1_V2.md` §3(R1·R3)
인테이크: `PREDECISION_2026-09-15_post7.md`(PD-1·PD-2·PD-3·PD-4·PD-10·PD-11·PD-12·PD-13) ·
        `INTAKE_2026-09-15_post7.md` §1·§2·§5 · `LABELS_2026-09-15_post7.md`

🔴🔴 **`PREREG_BUYLADDER` 계열은 «종결»됐다** — 🔒 사장님 **결정 ④**(`PREREG_GRADE_TIERS.md` §5 표 ·
   동결 `342f6f0`) ⇒ **`P6-L1'`·`P6-L1'-N`·`P6-L2'`·`P6-L3'`·`P6-L-누적`·`P6-L-대칭`·
   `BUY-L1`~`BUY-L5` 를 «재개하지 않는다» · 기록 보존만**(PD-13 1번).
   **충돌 신고(§1-8 형식)**: `REC-Z4` 동결 문언의 귀결 ↔ 결정 ④(계열 종결). **사장님 결정이 이긴다** —
   `PREREG_ANCHOR_REDESIGN.md` §5-2 가 같은 문형으로 *「④가 「종결」로 결정되면 `BUY-L5` 재개 조항은
   **자동 소멸**한다」*고 **미리** 적어 두었다. ⇒ `REC-Z4` 는 **조건 충족 사실과 건수만 인쇄**(관측) ·
   **판정 없음**. 등급은 §6 단계에서 그 축 문언대로 매긴다(여기서 등급 이름을 미리 고르지 않는다 — PD-16).

🔴 **계산 «전» 에 고정한 해석 결정** — A-1~A-11 은 `RESULTS_RECONSTRUCT_POST5.md` §1 에서 **전부 승계**하고
   (`PREREG_POST6.md` §2-7), 창 종료일(A-1)만 이번 글의 값으로 바꾼다:

  A-1 창 종료일 = **2026-09-11** (발행 2026-09-12(토) **휴장** ⇒ 마지막 거래일 · **B-1** · PD-1).
      🔴 **`WRC-` 포함 전 축 같은 값**이다(`PREREG_WEIGHTED_RECON.md` §5-2 :679-680 이 B-1 을 승계).
      🔴 실행 시 `max(date)` 와 그 날짜 행수를 산출물에 **기록**한다(창으로 쓰지는 않는다).
  A-2 REC-Y1 은 «전칭»으로 읽는다 — 레그 4개 이상인 «모든» 건의 폭 < 3%p. 건수 비율도 병기.
  A-3 되밀림 = 등록일 종가 < 등록일 고가 · 상한가마감 = 종가 == 고가 (post4 §3 조작화 승계).
  A-4 HDR-D1 표본 = 프리셋 `HDR 60%` 인 건. 🔴 **서산(`사분위수 Q2~MAX / 표준형`)은 분모 «밖»**이다 —
      post5 혜인(`사분위수 Q1~Q3`) 전례 그대로(D2/L4 관측으로 따로 · PD-9).
      라벨 `SL`·`MANUAL` 은 post4·post5 전례대로 포함하되 제외 민감도 병기.
  A-5 P6-R1': `PREREG_POST6.md` §3-3 이 「한쪽만 없는 경우」로 확장하고 **양쪽 각 n >= 2** 를 요구한다.
  A-6 Q1-R3 은 다차수 건의 `1-P/H` 가 「1차 밴드」가 아니라는 post4 §2 범주오류 판정을 유지한다.
  A-7 P6-L3' 실행 전제 = 「`b1` 구간 폭 / sigma20 < 격자 0.25 인 건이 과반」.
      🔴 **이번 회차에는 적용되지 않는다 — 결정 ④로 그 축이 종결됐다**(기록 보존).
  A-8 sigma20 = 등록일 «직전» 20거래일 로그수익률의 표본표준편차(연율화 안 함). 21봉 미만이면 sigma 축 제외.
  A-9 「하나의 평단」 전제가 원리적으로 깨질 수 있는 건에는 flag 만 단다.
      🔴 이번 글의 후속 3건(한라캐스트·아난티·우리기술투자)은 **PD-2 4번**으로 REC- 축 «밖»이다.
      🔴🔴 한라캐스트는 그 전제가 **산술로 깨진 첫 사례**다(post6 마지막 −2.89 → post7 첫 11.22).
  A-10 «해 0개» 진단의 잔차 문턱 — `REC-Z5`(`PREREG_POST6.md` §1-7)가 **0.022 단일 판정 ·
      0.020 의무 민감도**로 못 박았다. 두 문턱이 분류를 가르면 **「문턱 민감」이라고 인쇄하되 판정은 0.022**.
  A-11 feasible set 은 **정확 구간법**으로 푼다(유일한 방법 · 점법 폐기 — `PREREG_POST6.md` §3-6):
      `P in ( S*c/(1+(r+0.005)/100),  S*c/(1+(r-0.005)/100) ]` · 레그별 합집합 → 레그 전체 교집합.
      gross(c=1) · net(c=(1-FEE-TAX)/(1+FEE)) 둘 다 푼다.
      의무 인쇄: **구간 개수 · P 범위 · 총 측도 · 폭 · 폭/호가단위(칸)**.
      🔴 점법은 «하한»이므로 인용 시 반드시 「하한」이라 적는다.

🔴 **PD-4 — 등록일 정밀도가 이 계열에서 «처음» 갈린다**: 신규 10 ≠ `exact` 6.
   **판정 분모 = 신규 ∧ `exact` = 6건**(`RNK-D5` · `ANC` §2-3 · `S5` §1-1 세 동결본 일치) ·
   **`approx` 2건(지투파워·한국화장품제조)은 의무 민감도**(§1-4 창 규약 갈래별) ·
   **`none` 2건(한전기술·한전산업)은 등록일 축 «밖»**(D 가 없다 ⇒ 창 `[D, END]` 이 정의되지 않는다).

🔴 **PD-12 (가) 문형 승계**: 직전 글의 보존값은 **재계산하지 않고 인용**한다. 이번 회차에서 그 자리에
   해당하는 것은 **아난티(후속 · post6 #5)** 하나이며, `first_only` 누적을 쓰던 축(`P6-L-누적`)이
   **결정 ④로 종결**됐으므로 **원장·기록에만** 남긴다(PD-13 2번).

🔴 **라이브 채택 금지**(`PREREG.md` §0-2) · 라이브 트리 import 0건 · DB 는 SELECT 만 ·
   `adj_factor` 산술 0건 · **새 예측 없음**(이 스크립트는 동결된 항목만 계산한다).
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

from reconstruct_prices import gross_ret, tick
# 🔴 새 코드 0줄 원칙 — 통계 핵·창 함수는 동결 스크립트에서 «그대로» import 한다(수정 금지 파일).
from run_reconstruct_post5 import (bars, feasible_exact, feasible_pointwise, iv_max,
                                   iv_measure, iv_min, min_residual, sigma20)
from run_reconstruct_post6 import (dd_h,        # run_reconstruct_post6.py:155
                                   fmt_pct,     # run_reconstruct_post6.py:118
                                   med,         # run_reconstruct_post6.py:113
                                   win_bars)    # run_reconstruct_post6.py:145
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list = []

END = "2026-09-11"          # A-1 · PD-1 (발행 09-12(토) 휴장 ⇒ 마지막 거래일 · B-1)
PUB_DATE = "2026-09-12"     # 발행일(토) — 창으로 쓰지 않는다. 표기 의무용.
THR_MAIN = 0.022            # REC-Z5 판정 문턱 (PREREG_EXIT_V2.md §2)
THR_SENS = 0.020            # REC-Z5 의무 민감도
SEED = 20260815             # 계열 고정 시드 — 🔴 이번 회차에는 «쓰이지 않는다»(아래 주석)
NREP = 20000                # 〃
# 🔴 `SEED`·`NREP` 는 `P6-L1'-N` 귀무(결정 ④로 «종결»)의 상수다. 값을 지우지 않고 남겨 두되
#    **이 스크립트는 귀무를 돌리지 않는다** — 축이 닫혔기 때문이지 시드를 바꿨기 때문이 아니다.
#    🔑 상수를 지우면 「왜 안 돌았나」가 산출물에서 사라진다.

# (종목, 코드, 등록일, 정밀도, 레그, 체결차수, 프리셋, 라벨, first_only, 재진입)
# 출처 = INTAKE_2026-09-15_post7.md §1 (신규 10건) · LABELS_2026-09-15_post7.md · PD-4
# 🔴 후속 3건(한라캐스트·아난티·우리기술투자)은 PD-2 4번으로 REC- 축 «밖» — TARGETS 에 없다.
TARGETS = [
    ("한전기술", "052690", None, "none",
     [13.61, 10.80, 7.37, 4.91, 3.34, -1.70], 4, "HDR60", "SL", False, False),
    ("한전산업", "130660", None, "none",
     [15.55, 14.88, 12.70, 8.97, 5.78, -1.32], 5, "HDR60", "SL", False, False),
    ("지투파워", "388050", None, "approx",
     [20.11, 18.58, 17.50, 15.08, 12.72], 3, "HDR60", "TP", False, True),
    ("서산", "079650", "2026-09-03", "exact",
     [22.16, 16.09, 10.02], 1, "Q2~MAX", "TP", True, False),
    ("강동씨엔앨", "198440", "2026-09-03", "exact",
     [24.28, 18.33, 18.31, 12.61], 1, "HDR60", "TP", True, False),
    ("로보티즈", "108490", "2026-09-04", "exact",
     [9.13], 1, "HDR60", "TP", True, False),
    ("해치텍", "0155E0", "2026-09-07", "exact",
     [4.06, 0.46], 4, "HDR60", "TP", False, False),
    ("빛과전자", "069540", "2026-09-08", "exact",
     [12.17], 1, "HDR60", "TP", True, True),
    ("한국화장품제조", "003350", None, "approx",
     [22.70, 16.81, 10.85], 1, "HDR60", "unknown", True, True),
    ("범한퓨얼셀", "382900", "2026-09-09", "exact",
     [18.89, 16.69, 14.55, 12.22, 10.8, 7.94], 1, "HDR60", "TP", True, False),
]

NM, CODE, D0, PREC, LEGS, TR, PRESET, LABEL, FO, REENT = range(10)

# 🔴 `approx` 2건의 §1-4 창 규약 갈래 — **달력 실측값을 PD-4 2번에서 «옮겨 적었다»**(재계산 아님).
#    「9월 초」 = 09-01~09-10 의 모든 거래일 8일 · 「8월 말」 = 08-21~08-31 의 모든 거래일 7일.
APPROX_BRANCHES = {
    "지투파워": ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
                 "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"],
    "한국화장품제조": ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26",
                       "2026-08-27", "2026-08-28", "2026-08-31"],
}

# PD-12 (가) 문형 — post6 보존값. **재계산하지 않는다.** 출처 = RESULTS_RECONSTRUCT_POST6_NUMBERS.md
ANANTI = dict(
    nm="아난티(post6 #5 · 후속)", code="025980", d0="2026-08-19", legs=[10.16],
    n_iv=156, pmin=4311.71, pmax=5492.26, b1_lo=4.32, b1_hi=24.88, w=20.57,
    measure=68.34, frac_in=0.5582, bar_low=4750.0, bar_open=4880.0, bar_high=5740.0,
    bar_close=5350.0, dd=17.25, prebars=21, cells="236.1칸(5원)", end="2026-09-04",
    src="RESULTS_RECONSTRUCT_POST6_NUMBERS.md §1·§5·§9·§10·§15",
)

# 🔴 PD-12 — 창5 `[D, D+4]` 절단 2건(주 창 09-11 기준). REC- 축의 창은 `[D, END]` 전체라
#    절단 «개념»이 다르지만, 혼동 방지로 나란히 인쇄한다(post6 §17 관용 승계).
WIN5_TRUNC = {"빛과전자": 4, "범한퓨얼셀": 3}

# 🔴 PD-10 3번 — 저자 표기 소수 자릿수 한계(잔차 해석 의무 표기).
DECIMAL_LIMIT = {"범한퓨얼셀": 10.8}

# 🔴 결정 ④(동결 `342f6f0`)로 «종결»된 항목 — 재개하지 않는다. 기록 보존용 목록.
CLOSED_BY_DECISION4 = ["`P6-L1'`", "`P6-L1'-N`", "`P6-L2'`", "`P6-L3'`",
                       "`P6-L-누적`", "`P6-L-대칭`", "`BUY-L1`", "`BUY-L2`",
                       "`BUY-L3`", "`BUY-L4`", "`BUY-L5`"]


def say(s=""):
    print(s)
    OUT.append(s)


def main() -> int:  # noqa: C901
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    say("# RESULTS_RECONSTRUCT_POST7_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_reconstruct_post7.py` · 재사용 `run_reconstruct_post5.py`"
        "(`feasible_exact`·`feasible_pointwise`·`min_residual`·`sigma20`·`bars`) + "
        "`run_reconstruct_post6.py`(`iv_clip_measure`·`win_bars`·`dd_h`·`med`·`fmt_pct`) + "
        "`reconstruct_prices.py`(`tick`·`grid_prices`·`gross_ret`)")
    say("사전등록 `PREREG_POST6.md` §1-7·§2-6·§2-7·§3-3·§3-6·§4(#38~#54) · "
        "`PREREG_HDR.md` §4 · `PREREG_Q1_V2.md` §3")
    say("인테이크 `PREDECISION_2026-09-15_post7.md` · `INTAKE_2026-09-15_post7.md` · "
        "`LABELS_2026-09-15_post7.md`\n")

    cur.execute("SELECT max(date) FROM daily_prices")
    snap = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (snap,))
    snap_rows = cur.fetchone()[0]

    exact = [t for t in TARGETS if t[PREC] == "exact"]
    approx = [t for t in TARGETS if t[PREC] == "approx"]
    none_ = [t for t in TARGETS if t[PREC] == "none"]

    say("## §0. 환경 · 승계 선언\n")
    say(f"- 🔴 **창 종료 {END} = 발행일 {PUB_DATE}(토) 휴장 ⇒ 마지막 거래일 · B-1**"
        "(`WRC-` 포함 전 축 · PD-1) · 창 = `[등록일, " + END + "]`")
    say(f"- **실행 시 `max(date)` = {snap}** · 그 날짜 행수 **{snap_rows:,}** — "
        "🔴 **기록일 뿐 창으로 쓰지 않는다**(`WRC-D7` 표기 의무 · §7-B #13)")
    say("- **A-1 ~ A-11 전부 승계**(`PREREG_POST6.md` §2-7 · 문장은 이 스크립트 docstring 에 박혀 있다) — "
        f"A-1 의 창 종료일만 이번 글 값 **{END}** 으로 바뀐다")
    say("- **A-11 정확 구간법이 유일한 방법**(§3-6) · 점법은 **폐기** — 대조로만 인쇄하고 "
        "인용 시 **「하한」**이라 적는다")
    say(f"- 🔴 **PD-4 — 판정 분모 = 신규 ∧ `exact` = {len(exact)}건**"
        f"(`RNK-D5`·`ANC` §2-3·`S5` §1-1 일치) · `approx` **{len(approx)}건**은 §1-4 창 규약 "
        f"갈래별 **의무 민감도** · `none` **{len(none_)}건**은 **등록일 축 밖**(D 가 없다)")
    say("- 🔴 **PD-2 4번**: 후속 3건(한라캐스트·아난티·우리기술투자)은 「하나의 평단」 전제가 깨져 "
        "**REC- 축 밖**이다. 🔴🔴 한라캐스트는 그 전제가 **산술로 깨진 첫 사례**"
        "(post6 마지막 −2.89 → post7 첫 11.22 = **+14.11%p 증가**)")
    say(f"- 🔴 **PD-12 (가) 문형**: 아난티(후속) 값은 **재계산하지 않고** 보존값을 인용한다"
        f"(`{ANANTI['src']}` · as-of-post6 창 {ANANTI['end']})")
    say(f"- `REC-Z5`: 판정 **{THR_MAIN:.3f}%p 단일** · **{THR_SENS:.3f}%p 의무 민감도**"
        "(갈리면 「문턱 민감」 인쇄 · 판정은 0.022 로 선다 — §1-7)")
    say("- 🔴🔴 **결정 ④(`342f6f0`)로 `PREREG_BUYLADDER` 계열 종결** ⇒ "
        + " · ".join(CLOSED_BY_DECISION4) + " **재개하지 않는다 · 기록 보존만**(§10)")
    say("- 🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2) — "
        "이 문서의 어떤 숫자도 매매 규칙으로 옮기지 않는다\n")

    # ── §1. feasible 원표 ────────────────────────────────────────────────
    say("## §1. feasible set 원표 (gross · A-11 정확 구간법) — 의무 인쇄 5칸\n")
    say("의무 인쇄(§3-6): **구간 개수 · P 범위 · 총 측도 · 폭 · 폭/호가단위(칸)**\n")
    say(f"🟢 **주 판정 분모 = `exact` {len(exact)}건**(PD-4) — 아래 표.\n")
    say("| 종목 | 차수 | 라벨 | 등록일 | 레그 | 등록일 봉 [저,시,고,종] | 되밀림 | "
        "**구간 개수** | **P 범위** | **총 측도(원)** | **`1-P/H` 범위** | **폭** | "
        "**폭/호가단위(칸)** | (대조·하한) 점법 개수/폭 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    R = {}
    for t in exact:
        nm, code, d0, legs = t[NM], t[CODE], t[D0], t[LEGS]
        rows = bars(cur, code, d0, END)
        o0, h0, l0, c0 = rows[0][1], rows[0][2], rows[0][3], rows[0][4]
        iv = feasible_exact(rows, legs, "gross")
        pts = feasible_pointwise(rows, legs, gross_ret)
        v = dict(code=code, d0=d0, legs=legs, tr=t[TR], preset=t[PRESET], label=t[LABEL],
                 fo=t[FO], reent=t[REENT], rows=rows, o0=o0, h0=h0, l0=l0, c0=c0,
                 pull=c0 < h0, iv=iv, pts=pts, nbars=len(rows))
        R[nm] = v
        pw = f"{len(pts)} / {(max(pts)-min(pts))/h0*100:.2f}%p" if pts else "0 / —"
        bar = f"[{l0:,.0f}, {o0:,.0f}, {h0:,.0f}, {c0:,.0f}]"
        pull_s = "예" if v["pull"] else "아니오"
        if iv:
            pmin, pmax = iv_min(iv), iv_max(iv)
            w = (pmax - pmin) / h0 * 100
            tk = tick(pmin)
            v.update(pmin=pmin, pmax=pmax, w=w, measure=iv_measure(iv), cells=(pmax - pmin) / tk)
            say(f"| {nm} | {t[TR]}차 | {t[LABEL]} | {d0} | {len(legs)} | {bar} | {pull_s} | "
                f"**{len(iv)}** | {pmin:,.2f}~{pmax:,.2f} | **{v['measure']:,.2f}** | "
                f"{100*(1-pmax/h0):+.2f}%~{100*(1-pmin/h0):+.2f}% | **{w:.2f}%p** | "
                f"**{v['cells']:.1f}칸**({tk}원) | {pw} |")
        else:
            v.update(pmin=None, pmax=None, w=None, measure=0.0, cells=None)
            say(f"| {nm} | {t[TR]}차 | {t[LABEL]} | {d0} | {len(legs)} | {bar} | {pull_s} | "
                f"**0** | — | **0.00** | — | — | — | {pw} |")
    say(f"| _{ANANTI['nm']}_ | 1차 | TP | {ANANTI['d0']} | 1 | "
        f"[{ANANTI['bar_low']:,.0f}, {ANANTI['bar_open']:,.0f}, {ANANTI['bar_high']:,.0f}, "
        f"{ANANTI['bar_close']:,.0f}] | 예 | "
        f"_{ANANTI['n_iv']}_ | _{ANANTI['pmin']:,.2f}~{ANANTI['pmax']:,.2f}_ | "
        f"_{ANANTI['measure']:,.2f}_ | _+{ANANTI['b1_lo']:.2f}%~+{ANANTI['b1_hi']:.2f}%_ | "
        f"_{ANANTI['w']:.2f}%p_ | _{ANANTI['cells']}_ | _156 / 20.56%p_ |")
    say()
    say(f"- 🔴 마지막 줄(_기울임_)은 **post6 보존값 인용**이다 — PD-12 (가) 문형 · "
        f"**재계산하지 않았다**(`{ANANTI['src']}` · 창 종료가 {ANANTI['end']} 라 이번 창과 «다르다»).")
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
    say(f"- 🔴 **소수 자릿수 한계**(PD-10 3번): "
        + " · ".join(f"{k} 「{v}」는 **소수 1자리**(나머지는 2자리)"
                     for k, v in DECIMAL_LIMIT.items())
        + f" ⇒ 복원 잔차 문턱(`REC-Z5` {THR_MAIN:.3f}%p)은 **소수 2자리 전제**이므로 "
          "**그 건의 잔차 해석에 한계 표기 의무**가 있다(§2 에 그대로 반영).")

    # ── §1-b. approx 갈래 (의무 민감도) ──────────────────────────────────
    say()
    say("## §1-b. `approx` 2건 — §1-4 창 규약 **첫 발동** · 갈래별 (의무 민감도 · 판정 아님)\n")
    say("🔴 **판정에 쓰지 않는다**(PD-4 1번) — 「9월 초」·「8월 말」의 «모든 거래일»을 갈래로 두고 "
        "값의 **범위**를 인쇄한다. 갈래 날짜는 PD-4 2번의 달력 실측값을 **옮겨 적은 것**이다.\n")
    say("| 종목 | 창 규약 문구 | 갈래 수 | 갈래 날짜 | 해 있는 갈래 | 구간 개수 범위 | 폭 범위(%p) |")
    say("|---|---|---|---|---|---|---|")
    AX = {}
    for t in approx:
        nm = t[NM]
        rowsets = []
        for d in APPROX_BRANCHES[nm]:
            rws = bars(cur, t[CODE], d, END)
            iv = feasible_exact(rws, t[LEGS], "gross") if rws else []
            wid = ((iv_max(iv) - iv_min(iv)) / rws[0][2] * 100) if iv else None
            rowsets.append((d, rws, iv, wid))
        AX[nm] = rowsets
        have = [x for x in rowsets if x[2]]
        ns = [len(x[2]) for x in have]
        ws = [x[3] for x in have]
        say(f"| {nm} | {'「9월 초」' if nm == '지투파워' else '「8월 말」'} | "
            f"{len(rowsets)} | {APPROX_BRANCHES[nm][0]} ~ {APPROX_BRANCHES[nm][-1]} | "
            f"**{len(have)}/{len(rowsets)}** | "
            f"{f'{min(ns)}~{max(ns)}' if ns else '—'} | "
            f"{f'{min(ws):.2f}~{max(ws):.2f}' if ws else '—'} |")
    say()
    say("- 🔴 **`approx` 를 분모에 넣으면 `REC-Y1` 이 «열린다»**(레그 ≥4 건이 2 → 3). "
        "**넣지 않는 선택은 축을 «닫는» 쪽**이며, `RNK-D5`·`S5` §1-1·`ANC` §2-3 "
        "**세 동결본이 같은 방향을 지시**한다(PD-13 3번 방향 자기신고).")
    say("- 🔴 **재진입 민감도와 `approx` 민감도가 «겹친다»**(재진입 3 중 2건이 `approx`) — "
        "PD-3 마지막 줄대로 **두 민감도를 따로 인쇄하고 합치지 않는다**.")
    say("- ⚠️ **`P6-W10`(무작위 «창» 귀무)은 `TV` 축으로는 미루지만 이 용도로는 의무 인쇄**다"
        "(PD-6 예외 한 자리) — 그 인쇄는 `run_d1_oos_post7.py` 가 맡는다. "
        "**두 용도를 한 수로 합치지 않는다.**")

    # ── §1-c. none 2건 ───────────────────────────────────────────────────
    say()
    say("## §1-c. `none` 2건 — 등록일 축 «밖» (PD-4 3번 · 구성으로 빠진다)\n")
    say("| 종목 | 코드 | 차수 | 레그 | 라벨 | 왜 밖인가 |")
    say("|---|---|---|---|---|---|")
    for t in none_:
        say(f"| {t[NM]} | {t[CODE]} | {t[TR]}차 | {len(t[LEGS])} | {t[LABEL]} | "
            "🔴 등록일 문장이 **없다**(「8월 26일」은 **급등 사유일**이고 등록 문장과 다른 줄) ⇒ "
            f"창 `[D, {END}]` 이 **정의되지 않는다** · 급등일을 등록일로 «승격하지 않는다» |")
    say()
    say("- 🔴 **값을 보고 뺀 것이 아니라 «정의로» 빠진다** — post1 의 23건과 같은 처리다(PD-4 3번).")

    # ── §2. 해 0개 진단 · REC-Z5 ─────────────────────────────────────────
    say()
    say("## §2. 해 0개 진단 · `REC-Z5` — 판정 0.022 / 민감도 0.020\n")
    say("`Δr_min` = 서로 «다른» 인접 레그 수익률의 최소 간격(%p) · "
        "`res` = 호가 한 칸이 만드는 수익률 해상도 `100*tick(P)/P`\n")
    say("🔑 `Δr_min < res` 이면 **두 레그를 격자 위 서로 다른 매도가로 표현할 수 없다** "
        "⇒ 산술적으로 해가 0개다.\n")
    say(f"🔴 **`REC-Z5`**(§1-7): 판정 문턱 **{THR_MAIN:.3f}%p 단일** · "
        f"**{THR_SENS:.3f}%p 는 의무 민감도**. 두 문턱이 분류를 가르면 **「문턱 민감」이라 인쇄하되 "
        f"판정은 {THR_MAIN:.3f} 로 선다**.\n")
    say("| 종목 | 레그 | `Δr_min` | 후보 P 범위 | `res`(P 양끝) | **`Δr_min` < `res`?** | "
        "최소잔차 적합 P | **최대 오차** | **판정 @0.022** | (민감도) @0.020 | 자릿수 한계 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
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
        for th in (THR_MAIN, THR_SENS):
            if v["iv"]:
                diags.append(f"해 {len(v['iv'])}구간 (진단 불필요)")
            elif mr is None:
                diags.append("🔴 적합 실패")
            elif mr[0] < th:
                diags.append("반올림으로 설명 가능")
            else:
                diags.append("🔴 **모델이 틀렸다**")
        if not v["iv"] and mr is not None and diags[0] != diags[1]:
            split.append(nm)
        lim = ("🔴 **소수 1자리 레그 有**" if nm in DECIMAL_LIMIT else "—")
        say(f"| {nm} | {legs} | {'—' if dmin is None else f'{dmin:.2f}%p'} | {pl:,.0f}~{ph:,.0f} | "
            f"{r_hi:.3f}~{r_lo:.3f}%p | {'🔴 **예**' if under else '아니오'} | "
            f"{'—' if mr is None else f'{mr[1]:,.0f}'} | "
            f"{'—' if mr is None else f'**{mr[0]:.6f}%p**'} | {diags[0]} | {diags[1]} | {lim} |")
    say()
    say(f"- 두 문턱에서 분류가 갈리는 건: **{len(split)}건** ({', '.join(split) if split else '없음'}) ⇒ "
        + ("🔴 **「문턱 민감」** — 판정은 0.022 로 서고 그 사실을 여기 인쇄한다."
           if split else "**문턱 민감 없음**(0.020·0.022 에서 분류 동일)"))
    say(f"- 격자 해상도 미달(`Δr_min` < `res`) 건: "
        f"**{sum(1 for v in R.values() if v['under'])}/{len(R)}** ("
        + (", ".join(nm for nm, v in R.items() if v["under"]) or "없음") + ")")
    say("- 🔑 레그가 **1개뿐인 건**(로보티즈·빛과전자)은 `Δr_min` 이 «정의되지 않는다» — "
        "격자 미달 판정에서 빠진다.")
    say("- 🔴 **한계 표기 의무(PD-10 3번)**: "
        + " · ".join(f"{k}의 레그 「{v}」는 소수 1자리다" for k, v in DECIMAL_LIMIT.items())
        + f" ⇒ 그 건의 `Δr`·잔차는 **±0.05%p 의 표기 불확실**을 안고 있다"
          f"(다른 건의 ±0.005%p 보다 **10배 넓다**). **문턱({THR_MAIN:.3f}%p)을 고치지 않는다** — "
          "한계로 적는다.")

    # ── §3. REC-Y1 ───────────────────────────────────────────────────────
    say()
    say("## §3. `REC-Y1`(핵심) — 레그 4개 이상인 건의 `b1` feasible 폭 < 3%p (전칭 · A-2)\n")
    say("| 종목 | 정밀도 | 레그 | 구간 개수 | 총 측도(원) | 폭 | < 3%p |")
    say("|---|---|---|---|---|---|---|")
    y1_items, y1_ok, y1_undef = [], 0, 0
    for nm, v in R.items():
        if len(v["legs"]) < 4:
            continue
        y1_items.append(nm)
        if not v["iv"]:
            y1_undef += 1
            say(f"| {nm} | exact | {len(v['legs'])} | **0** | 0.00 | ⛔ **미정의**(해 0개) | ⛔ |")
        else:
            ok = v["w"] < 3.0
            y1_ok += int(ok)
            say(f"| {nm} | exact | {len(v['legs'])} | {len(v['iv'])} | {v['measure']:,.2f} | "
                f"**{v['w']:.2f}%p** | {'성립' if ok else '위반'} |")
    ax_y1 = [t for t in approx if len(t[LEGS]) >= 4]
    for t in ax_y1:
        nm = t[NM]
        have = [x for x in AX[nm] if x[2]]
        ws = [x[3] for x in have]
        say(f"| _{nm}_ | _approx_ | _{len(t[LEGS])}_ | "
            f"_{len(have)}/{len(AX[nm])} 갈래에 해_ | _—_ | "
            f"_{f'{min(ws):.2f}~{max(ws):.2f}%p' if ws else '—'}_ | _민감도 전용_ |")
    say()
    say(f"- 레그>=4 **`exact` 대상 {len(y1_items)}건**({', '.join(y1_items)}) · 폭 측정 가능 "
        f"**{len(y1_items)-y1_undef}건** · 미정의(해 0개) **{y1_undef}건** · 최소 n **3** ⇒ "
        f"**{'충족' if len(y1_items) >= 3 else '미달'}**")
    say(f"- ⇒ ⛔ **`REC-Y1` 판정 불가 — 최소 n 미달**(`exact` 레그>=4 가 **{len(y1_items)} < 3** · "
        "`PREREG_POST6.md` §4 #38).")
    say(f"- (민감도 · 판정 아님) `approx` 포함 갈래: {len(y1_items)} + {len(ax_y1)} = "
        f"**{len(y1_items)+len(ax_y1)}건** ⇒ 최소 n 을 **넘긴다**. "
        "🔴 **그래도 판정하지 않는다** — PD-4 1번이 분모를 `exact` 로 못박았다.")
    say("- 🔴 **방향 자기신고**(PD-13 3번 축자): *「`approx` 를 분모에 넣으면 `REC-Y1` 이 **열린다**. "
        "넣지 않는 선택은 축을 **닫는 쪽**이며, `RNK-D5`·`S5` §1-1·`ANC` §2-3 세 동결본이 "
        "같은 방향을 지시한다」*.")

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
        tk = tick(v["pmin"])
        pwc = ((max(v["pts"]) - min(v["pts"])) / tick(min(v["pts"]))) if v["pts"] else None
        say(f"| {nm} | {len(v['legs'])} | {lo:,.0f}~{hi:,.0f} | {tk}원 | {v['w']:.2f}%p | "
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
    say(f"- 해 0개(정확법 · `exact` {len(R)}건): **{len(empty)}/{len(R)} = {100*frac:.1f}%** "
        f"({', '.join(empty) if empty else '없음'})")
    say("- 잣대 정합 계열(**전부 정확법**): post4 **1/6 = 16.7%**"
        "(`RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS.md` §2 · C-22 재계산) → post5 **4/6 = 66.7%** → "
        "post6 **5/10 = 50.0%**(← 동결 `RESULTS_RECONSTRUCT_POST6_NUMBERS.md` §5) → "
        f"post7 **{len(empty)}/{len(R)} = {100*frac:.1f}%**")
    say("- 🔴 **분모의 «정의»가 이번 글에서 바뀌었다** — post6 까지는 「신규 전건」이었고 "
        "post7 은 「신규 ∧ `exact`」다(PD-4 가 계산 «전»에 못박았다). "
        "***계열 비교를 할 때 이 사실을 같이 읽어야 한다.***")
    say(f"- 사전등록 문턱 **>= 1/3 = 33.3%** ⇒ **{'🔴 발동' if frac >= 1/3 else '미발동'}**")
    say(f"- 다차수(2차 이상) 건 **{len(multi)}/{len(R)}** 중 해 0개 **{len(empty_multi)}** "
        f"({', '.join(empty_multi) if empty_multi else '없음'})")
    if frac >= 1 / 3:
        say("- ⇒ 🔴🔴 **「다차수 건에서 평단이 매도 중 변한다」로 읽고, 복원 기반 축"
            "(`Q1-R3`·`HDR-D1`)을 «다차수 건»에 적용하는 것을 중단한다.** "
            "(`RESULTS_RECONSTRUCT_POST4.md` §6 Y3 동결 문언 — 값을 보고 정한 규칙이 아니다.) "
            "🔴 `P6-L3'`·`BUY-L5` 는 **결정 ④로 이미 종결**이라 중단 대상 목록에서 «자동으로» 빠진다.")
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
    say((f"| 격자 미달군(`Δr_min` < `res`) | {len(ga)} | **{len(ga_z)}** | "
         f"{(100*len(ga_z)/len(ga)):.1f}% | {', '.join(ga)} |") if ga else
        "| 격자 미달군(`Δr_min` < `res`) | 0 | — | — | — |")
    say((f"| 격자 충족군(`Δr_min` >= `res` 또는 미정의) | {len(gb)} | **{len(gb_z)}** | "
         f"{(100*len(gb_z)/len(gb)):.1f}% | {', '.join(gb)} |") if gb else
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
        f"**{'🔴🔴 발동' if z3_frac >= 0.5 else '미발동'}** (post5 3/6 = 50.0% · post6 6/10 = 60.0%)")
    if z3_frac >= 0.5:
        say("- ⇒ 🔴🔴 **앵커 붕괴가 «또» 재현됐다.** 앵커 재설계 사전등록은 post6 에서 이미 "
            "**의무 발생**했고 `PREREG_ANCHOR_REDESIGN.md`(동결 `ef17c4f`)로 이행됐다 ⇒ "
            "이번 회차의 `ANC-P1` 은 **그 재설계의 첫 검정**이다"
            "(`run_anchor_redesign.py --mode post7` 이 맡는다 · 이 산출물은 후보 앵커를 계산하지 않는다).")
        say("- 🔴 **`HDR-D1` 은 이 붕괴로 «무효»**(`PREREG_POST6.md` §4 #52 대칭 쌍) — §12 에 그대로 적용.")
    else:
        say("- ⇒ 앵커 재설계 의무 **미발생**. `HDR-D1` 은 이 축으로는 무효화되지 않는다.")
    say("- 🔑 `h = (S-L)/(H-L)` 는 `H` 가 천장일 때만 「저점 대비 반등폭 비율」이다 — "
        "천장이 뚫린 건에서는 `h_max` 가 1 을 넘고 HDR 틀 자체가 성립하지 않는다.")

    # ── §9. REC-Z4 ───────────────────────────────────────────────────────
    say()
    say("## §9. `REC-Z4` — `first_only` ∧ 서로 «다른» 값 레그 >= 3 · 🔴 **관측 인쇄만**\n")
    say("🔴🔴 **이 항목은 «판정하지 않는다».** 동결 문언의 귀결(= 그 자리에서 `BUY-` 계열을 연다)은 "
        "🔒 **결정 ④「`PREREG_BUYLADDER` 계열 종결·기록 보존」**(`PREREG_GRADE_TIERS.md` §5 · 동결 "
        "`342f6f0`)으로 **소멸**했다(PD-13 1번). **조건 충족 사실과 건수만 인쇄한다.**\n")
    say("| 종목 | 정밀도 | first_only | 레그 | 서로 다른 값 개수 | Z4 조건 충족 |")
    say("|---|---|---|---|---|---|")
    z4 = []
    for nm, v in R.items():
        if not v["fo"]:
            continue
        d = len(set(v["legs"]))
        hit = d >= 3
        if hit:
            z4.append(nm)
        say(f"| {nm} | exact | 예 | {v['legs']} | **{d}** | {'🟢 **충족**' if hit else '아니오'} |")
    for t in approx:
        if not t[FO]:
            continue
        d = len(set(t[LEGS]))
        say(f"| _{t[NM]}_ | _approx_ | _예_ | _{t[LEGS]}_ | _{d}_ | "
            f"_{'충족(민감도)' if d >= 3 else '아니오'}_ |")
    say(f"| _{ANANTI['nm']}_ | _none(후속)_ | _예(post6·post7 둘 다 1차)_ | _{ANANTI['legs']}_ | "
        "_1_ | _아니오_ |")
    say()
    fo_new = [nm for nm, v in R.items() if v["fo"]]
    say(f"- **`REC-Z4` 조건 충족(관측): {len(z4)}건** ({', '.join(z4) if z4 else '없음'}) — "
        "🔴 **판정 없음**(결정 ④). 등급은 §6 단계에서 그 축 문언대로 매긴다"
        "(여기서 등급 이름을 미리 고르지 않는다 — PD-16).")
    say(f"- `first_only` **`exact` {len(fo_new)}건** ({', '.join(fo_new)}) + "
        f"`approx` {sum(1 for t in approx if t[FO])}건(민감도) + 후속 아난티 1건(기록).")
    say("- 🔴 **충돌 신고(§1-8 형식)**: `REC-Z4` 동결 문언 ↔ 결정 ④. **사장님 결정이 이긴다** — "
        "`PREREG_ANCHOR_REDESIGN.md` §5-2 가 *「④가 「종결」로 결정되면 `BUY-L5` 재개 조항은 "
        "**자동 소멸**한다」*고 **미리** 적어 두었고, 그 뒤 `342f6f0` 이 결정을 기록했다.")

    # ── §10. BUY 계열 종결 (기록 보존) ───────────────────────────────────
    say()
    say("## §10. 🔒 `PREREG_BUYLADDER` 계열 — **종결 · 기록 보존** (결정 ④ · 계산 0회)\n")
    say("| 항목 | 지위 | 이번 회차 처리 |")
    say("|---|---|---|")
    for lab in CLOSED_BY_DECISION4:
        say(f"| {lab} | 🔒 **종결**(결정 ④ · `342f6f0`) | **재개하지 않는다 · 계산 0회 · 기록 보존** |")
    say()
    say(f"- 🔴 **귀무 상수는 남겨 두되 돌리지 않았다** — `SEED` = **{SEED}** · `NREP` = **{NREP:,}** "
        "는 `P6-L1'-N`(죽은 가드 방지 장치)의 상수다. **축이 닫혀서** 안 돌린 것이지 "
        "시드를 바꾼 것이 아니다. 🔑 *상수를 지우면 「왜 안 돌았나」가 산출물에서 사라진다.*")
    say(f"- **아난티(후속)의 `first_only` 누적 지위**(PD-13 2번 · post6 PD-12 문형 승계): "
        f"**(가) as-of-post6 유지**를 주로 두고(post6 1레그 {ANANTI['legs'][0]} · "
        f"`frac_in` {ANANTI['frac_in']:.4f}) **(나) 제외**를 민감도로 나란히 적는다. "
        "🔴 **그런데 이 누적을 «쓰던 축»(`P6-L-누적`)이 종결됐다** ⇒ **원장·기록에만 남긴다.**")
    say("- 🔴 **방향 자기신고**: 아난티는 이번에 **1차 유지 그대로 사이클이 끝났다**"
        "(2글 연속 `first_only`) — post6 삼양(2차 매수로 `first_only` 가 깨진 건)과 **반대 모양**이다. "
        "⇒ (가)는 「깨진 걸 보존한다」가 아니라 「끝까지 `first_only` 였다」가 된다. "
        "**이 사실이 판정을 만들지 않도록 기록 칸에만 둔다.**")

    # ── §11. Q1-R3 ───────────────────────────────────────────────────────
    say()
    say("## §11. `Q1-R3` — `b1` 구간이 직전 글 값과 부호·자릿수가 같은가 (구간 겹침 여부만)\n")
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
    say(f"| _{ANANTI['nm']}_ | _`first_only`(post6 보존)_ | "
        f"_[+{ANANTI['b1_lo']:.2f}%, +{ANANTI['b1_hi']:.2f}%]_ | _양_ | "
        f"_{len(str(int(ANANTI['b1_hi'])))} 자리_ |")
    say("| 삼양바이오팜(post5) | `first_only` | [+10.31%, +29.68%] | 양 | 2 자리 |")
    say("| 솔트룩스(post4) | `first_only` | [−0.90%, +2.47%] | 걸침 | 1 자리 |")
    say("| 케이엔알(직전 3글) | `full` | `b_last` <= +36.76% | 양 | 2 자리 |")
    say()
    say(f"- 최소 n **3**(`PREREG_POST6.md` §4 #54) — 두 읽기: "
        f"`first_only` **건수 {len(fo_new)}**(⇒ {'충족' if len(fo_new) >= 3 else '미달'}) vs "
        f"**측정 가능 {len(r3)}건**(⇒ {'충족' if len(r3) >= 3 else '미달'}) · "
        "🔴 ⛔ 조건 ②(「feasible 이 빈 집합」)의 «건 단위 vs 분모 단위» 모호다 — 양쪽 인쇄한다.")
    if r3:
        ov_a = sum(1 for _, a, b in r3 if not (b < ANANTI["b1_lo"] or a > ANANTI["b1_hi"]))
        ov_p = sum(1 for _, a, b in r3 if not (b < -0.90 or a > 2.47))
        say(f"- 구간 겹침(측정 가능 {len(r3)}건 기준): post6 아난티 "
            f"`[+{ANANTI['b1_lo']:.2f}, +{ANANTI['b1_hi']:.2f}]` 과 **{ov_a}/{len(r3)}** · "
            f"post4 솔트룩스 `[−0.90, +2.47]` 과 **{ov_p}/{len(r3)}**")
        say("- 부호·자릿수: " + ", ".join(
            f"{nm} {'양' if a > 0 else ('음' if b < 0 else '걸침')}/"
            f"{len(str(int(abs(b))))} 자리({b:+.2f}%)" for nm, a, b in r3))
    if len(r3) >= 3:
        say("- ⇒ 🟡 **`Q1-R3` = 겹침 여부 «기록»**(`PREREG_Q1_V2.md` §3 판정 규칙 = "
            "*「R3 은 구간 겹침 여부만」* — 지지/기각을 선언하는 항목이 아니다).")
    else:
        say(f"- ⇒ ⛔ **`Q1-R3` 판정 불가**(주) — `first_only` **측정 가능 {len(r3)} < 3**. "
            "🟡 「건수 읽기」를 택하면 위 겹침 값이 R3 의 «기록»이 된다 — "
            "🔴 어느 쪽이든 **R3 은 지지/기각을 선언하는 항목이 아니라** 결론은 같다.")

    # ── §12. HDR-D1 ──────────────────────────────────────────────────────
    say()
    say("## §12. `HDR-D1` — `HDR 60%` 건의 `h_max` 중앙값이 0.50~0.70 인가\n")
    say("`h_max = (S_max - L)/(H - L)` · `H` = 등록일 고가 · `L` = min(low) over `[D, 종료]` · "
        "`S_max = P*(1+r1)` · 분모 = 프리셋 `HDR 60%` 건(A-4)\n")
    say("🔴 **서산(`사분위수 Q2~MAX / 표준형`)은 분모 «밖»**이다 — post5 혜인(`Q1~Q3`) 전례 그대로 "
        "(HDR 숫자가 «없는» 축 · `HDR-D2`/`BUY-L4` 변량도 아니다 · PD-9 · 관측 n=2).\n")
    say("| 종목 | 프리셋 | 차수 | H | L | 창 최고가 | H == 창최고? | P 범위 | `h_max` 범위 | 폭 | "
        "Y3 중단 | D1 분모 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|")
    d1mids = []
    for nm, v in R.items():
        stop = (v["tr"] >= 2 and frac >= 1 / 3)
        aflag = "예" if v["h0"] >= v["HI"] else "🔴 **아니다**"
        inden = (v["preset"] == "HDR60" and not stop)
        den_s = "포함" if inden else ("🔴 **밖**(프리셋)" if v["preset"] != "HDR60" else "🔴 밖(Y3 중단)")
        if not v["iv"]:
            say(f"| {nm} | {v['preset']} | {v['tr']}차 | {v['h0']:,.0f} | {v['L']:,.0f} | "
                f"{v['HI']:,.0f} | {aflag} | **해 없음** | — | — | {'🔴' if stop else '—'} | {den_s} |")
            continue
        r1_ = v["legs"][0] / 100.0
        smin, smax = v["pmin"] * (1 + r1_), v["pmax"] * (1 + r1_)
        hlo, hhi = (smin - v["L"]) / (v["h0"] - v["L"]), (smax - v["L"]) / (v["h0"] - v["L"])
        say(f"| {nm} | {v['preset']} | {v['tr']}차 | {v['h0']:,.0f} | {v['L']:,.0f} | "
            f"{v['HI']:,.0f} | {aflag} | {v['pmin']:,.2f}~{v['pmax']:,.2f} | "
            f"**{hlo:.3f}~{hhi:.3f}** | {hhi-hlo:.3f} | {'🔴 중단' if stop else '—'} | {den_s} |")
        if inden:
            d1mids.append((nm, (hlo + hhi) / 2, hhi - hlo, v["label"]))
    say()
    say(f"- `REC-Y3` 중단{' 발동 ⇒ 다차수 건 제외' if frac >= 1/3 else ' 미발동'} · "
        f"프리셋 분모 밖 **{sum(1 for v in R.values() if v['preset'] != 'HDR60')}건**(서산) · "
        f"남는 분모 **{len(d1mids)}건** "
        f"({', '.join(n for n, _, _, _ in d1mids) if d1mids else '없음'})")
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
        sl = [m_ for _, m_, _, lb in d1mids if lb not in ("SL", "MANUAL")]
        if sl and len(sl) != len(ms):
            say(f"- (민감도 A-4) 라벨 `SL`·`MANUAL` 제외 시 n={len(sl)} · 중앙값 **{med(sl):.3f}**")
    else:
        say(f"- ⇒ ⛔ **`HDR-D1` 판정 불가** — 분모 **{len(d1mids)}건**"
            "(최소 n 3 미달 · `PREREG_POST6.md` §4 #52).")

    # ── §13. P6-R1' ──────────────────────────────────────────────────────
    say()
    say("## §13. `P6-R1'` — `first_only` DD < `full` DD (누적 · 양쪽 각 n >= 2)\n")
    say("`H4`=max(high) over `[D-4,D]` · `H5`=`[D-9,D]` · `H6`=`[D-19,D]` · "
        "`DD` = 1 - min(low over `[D, 종료]`) / H\n")
    say("| 건 | 구분 | 등록일 | 종료 | `DD(H4)` | `DD(H5)` | `DD(H6)` |")
    say("|---|---|---|---|---|---|---|")
    fo_dd = []
    for nm in fo_new:
        v = R[nm]
        row = [dd_h(cur, v["code"], v["d0"], END, k) for k in (5, 10, 20)]
        fo_dd.append((nm, row))
        say(f"| {nm} | `first_only`(신규 `exact`) | {v['d0']} | {END} | "
            f"{row[0]:.2f}% | {row[1]:.2f}% | {row[2]:.2f}% |")
    say(f"| _{ANANTI['nm']}_ | _`first_only`(post6 보존)_ | _{ANANTI['d0']}_ | _{ANANTI['end']}_ | "
        f"_{ANANTI['dd']:.2f}%_ | _{ANANTI['dd']:.2f}%_ | _{ANANTI['dd']:.2f}%_ |")
    knr = [dd_h(cur, "199430", "2026-07-28", "2026-08-14", k) for k in (5, 10, 20)]
    say(f"| 케이엔알시스템 | `full`(누적 · 직전 글들) | 2026-07-28 | 2026-08-14 | "
        f"{knr[0]:.2f}% | {knr[1]:.2f}% | {knr[2]:.2f}% |")
    say()
    say("- 🔴 **이번 글 신규 `full` = 0건**(PD-14 *「`P6-R1'` — `full` 신규 **0** "
        "(체결 차수 13/13 중 「전 차수 체결」 서술 0) ⇒ 관측만」*)")
    say(f"- 누적 n: `first_only` **{len(fo_dd)}**(신규 `exact`) · `full` **1**(케이엔알)")
    say("- 문턱 **양쪽 각 n >= 2**(`PREREG_POST6.md` §3-3) ⇒ `full` 1 < 2 ⇒ "
        "⛔ **판정 안 함 · 관측만.**")
    dirn = sum(1 for _, row in fo_dd for a, b in zip(row, knr) if a < b)
    tot = len(fo_dd) * 3
    say(f"- (관측) 방향 일치(`first_only` DD < `full` DD) **{dirn}/{tot}** — "
        f"신규 `exact` {len(fo_dd)}건 × 세 H 정의.")
    say("- 🔴 **판정이 아니다** — `Q1-R1` 은 *「위반 1건이면 기각」* 이라 n=1 짜리 기각을 막으려고 "
        "n >= 2 를 걸었다. 그 문턱이 **지금 실제로 판정을 막고 있다**(§15).")

    # ── §14. 재진입 제외 민감도 ──────────────────────────────────────────
    say()
    say("## §14. 재진입 제외 민감도 (PD-3 · `PREREG_POST6.md` §1-5)\n")
    say("🔴 **재진입 3건**(지투파워 3번째 사이클 · 한국화장품제조 · 빛과전자) 중 "
        "**`exact` 분모 안은 빛과전자 1건뿐**이고, 그 건의 `P6-PRIOR_CYCLE_IN_WINDOW` = **0** "
        "(직전 등록일 08-05 < 창 시작 08-11) ⇒ 🔴 **판정 분모 안 플래그 = 0**"
        "(글 전체 플래그 2건은 지투파워·한국화장품제조 = 둘 다 `approx` 갈래 · INTAKE §2-10).\n")
    sub = {nm: v for nm, v in R.items() if not v["reent"]}
    s_empty = [nm for nm, v in sub.items() if not v["iv"]]
    s_under = [nm for nm, v in sub.items() if v["under"]]
    s_z3 = [nm for nm in z3_hit if nm in sub]
    s_y1 = [nm for nm, v in sub.items() if len(v["legs"]) >= 4]
    say(f"| 항목 | 주 판정(`exact` {len(R)}) | **재진입 제외({len(sub)}건)** | 문턱 | 판정이 뒤집히나 |")
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
    say(f"| `REC-Y1` 대상(레그>=4) | {len(y1_items)}건 | **{len(s_y1)}건** | 최소 n 3 | "
        f"{'아니오' if (len(s_y1) >= 3) == (len(y1_items) >= 3) else '🔴 **예**'} |")
    say()
    say("- 🔴 **`approx` 제외 민감도와 «겹치지 않게» 따로 인쇄했다**(PD-3 마지막 줄) — "
        "재진입 3건 중 2건이 `approx` 라 두 민감도를 합치면 **같은 건을 두 번 빼는** 셈이 된다.")

    # ── §15. 봉수 정합 · 창5 절단 ────────────────────────────────────────
    say()
    say("## §15. 봉수 표기 정합 (N8 승계 — «직전/포함»을 반드시 붙인다) · 창5 절단 기록\n")
    say("| 종목 | 등록일 | DB 최초 봉 | 등록일 «직전» 봉수 | 등록일 «포함» 봉수 | "
        f"창 `[D, {END}]` 봉수 | 창 `[D-19, D+4]` 봉수 | 창5 `[D, D+4]` |")
    say("|---|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        cur.execute("SELECT min(date), count(*) FROM daily_prices WHERE stock_code=%s "
                    "AND date <= %s", (v["code"], v["d0"]))
        mn, inc = cur.fetchone()
        s, n = sigma20(cur, v["code"], v["d0"])
        v["sigma20"], v["prebars"] = s, n
        wbn = len(win_bars(cur, v["code"], v["d0"], 19, 4))
        v["winbars"] = wbn
        t5 = WIN5_TRUNC.get(nm)
        say(f"| {nm} | {v['d0']} | {mn} | {n} | {inc} | {v['nbars']} | {wbn} | "
            f"{'🔴 **' + str(t5) + '봉 = 절단**' if t5 else '완전'} |")
    say()
    say(f"- 🔴 **`P6-절단가드-A`**(창 `[D-19, D]` 봉수 < 20) 분자 = **1**"
        "(해치텍 10/20 = 등록일 포함 10봉 = **등록일 직전 9봉** · 신규 상장 08-25) ⇒ "
        f"**1/{len(R)} ≈ {100/len(R):.1f}% < 1/3 ⇒ 미발동**(산술 인쇄 · PD-12).")
    say(f"- 🔴 **`P6-창5절단가드-A`**(창5 절단 건 / **이번 글 신규 건**) = **{len(WIN5_TRUNC)}/10 = "
        f"{100*len(WIN5_TRUNC)/10:.0f}% < 1/3 ⇒ 미발동**(post6 PD-11 3번이 분모를 「이번 글 신규 건」으로 "
        "**못박았다** — 문언 그대로 신규 10 을 쓴다). "
        f"🔴 **`exact` 분모 갈래는 {len(WIN5_TRUNC)}/{len(R)} = "
        f"{100*len(WIN5_TRUNC)/len(R):.1f}% ≥ 1/3 ⇒ 발동 조건에 «닿는다»** — "
        "그 사실을 숨기지 않고 여기 그대로 인쇄한다(PD-12 3번).")
    say("- 🔴 **방향 기록(선택이 아니다 · PD-12 5번)**: 창이 09-15 였다면 이번 절단 2건이 **0건**이 되고 "
        "`P6-창5절단가드-A` 의 `exact` 갈래도 33.3% → 0% 로 **꺼졌다**. "
        "동결 문언이 지시한 09-11 은 가드를 **켜는 쪽 = 우리에게 불리한 쪽**이지만, "
        "🔑 **고른 것이 아니라 정해져 있던 값**이다.")
    say("- 🔴 **혼동 방지**: `REC-` 축의 창은 `[등록일, " + END + "]` **전체**라 **절단 개념이 다르다** — "
        "위 창5 열은 `LAD-`·`ANC-` 축이 쓰는 값이며 이 산출물의 판정에는 들어가지 않는다"
        "(post6 §17 관용 승계).")
    say("- 🔴 **60봉 특징(`f9_newhigh`)용 04-01~08-04 구간**: 해치텍은 **0봉**(상장 전) ⇒ "
        "**C-17 NaN 규약 대상 1건** — 그 처리는 `run_selection_post7.py` 가 맡는다"
        "(이 산출물은 60봉 특징을 쓰지 않는다).")

    # ── §16. 처음 정한 문턱 · 모호 지점 ──────────────────────────────────
    say()
    say("## §16. 「이 문서에서 처음 정한 문턱」에 걸렸나 · 모호 지점\n")
    say("| 문턱 | 출처 | 이번 글에서 «걸렸나» |")
    say("|---|---|---|")
    say("| **n >= 2** (`P6-R1'` 양쪽 각) | `PREREG_POST6.md` §3-3 | "
        "🔴 **걸렸다** — `full` 누적 1건이라 이 문턱 «때문에» 판정을 안 한다 |")
    say(f"| `REC-Z5` **0.022** 판정 / 0.020 민감도 | `PREREG_EXIT_V2.md` §2 · "
        f"`PREREG_POST6.md` §1-7 | "
        + (f"🔴 **걸렸다** — 두 문턱이 {len(split)}건에서 분류를 가른다(「문턱 민감」)"
           if split else "**안 걸렸다** — 두 문턱에서 분류 동일") + " |")
    say(f"| 최소 n **3** (`REC-Y1`) | `PREREG_POST6.md` §4 #38 | "
        f"🔴 **걸렸다** — `exact` 레그>=4 가 **{len(y1_items)} < 3** 이라 판정을 «안» 한다"
        f"(`approx` 를 넣으면 {len(y1_items)+len(ax_y1)} 로 열렸다 — 넣지 않았다) |")
    say("| **`frac_in` 0.5** · **A-7 0.25·과반** | `PREREG_POST6.md` §3-4·§3-5 | "
        "🔒 **해당 없음** — 결정 ④로 그 축들이 종결됐다(계산 0회) |")
    say()
    say("### 모호 지점 (양쪽 인쇄 · 어느 쪽도 규칙으로 고르지 않는다)\n")
    say("1. 🔴 **판정 분모의 «정의»가 이번 글에서 처음 갈린다** — `ANC` §2-3 은 분모를 "
        "*「신규 ∧ `exact`」*라 적으면서 *「post6 의 `REC-` 분모(10건)와 **같은 규칙**」*이라 "
        "덧붙였는데, **post6 의 신규 10건이 전부 `exact` 였기 때문에** 그때는 두 정의가 같은 수였다. "
        f"post7 에서 **신규 10 ≠ `exact` {len(R)}** 로 처음 갈린다 ⇒ **명시된 쪽(`exact`)을 쓰고** "
        "신규 10 갈래는 민감도로 병기했다(PD-4 1번 충돌 신고).")
    say("2. 🔴 **`approx` 2건의 창 규약 갈래** — 「9월 초」 8갈래 · 「8월 말」 7갈래를 "
        "**전부 계산해 범위로 인쇄**했다(§1-b). 어느 갈래도 «대표값»으로 고르지 않는다.")
    say("3. 🔴 **⛔ 조건 ②(「feasible 이 빈 집합」)의 «건 단위 vs 분모 단위»** — "
        "`Q1-R3`(§11)에서 **주 = 건 단위**(그 건만 분모 밖) · **⛔ = 분모 단위** 를 나란히 인쇄했다.")
    say("4. 🔴 **범한퓨얼셀의 소수 1자리 표기**(PD-10 3번) — 값을 「10.80」으로 **보정하지 않았다**. "
        "보정하면 저자가 적지 않은 자릿수를 우리가 만들어 넣는 것이다. "
        "대신 **잔차 해석에 ±0.05%p 한계**를 §2 에 박았다.")
    say("5. 🔴 **`unknown` 라벨(한국화장품제조)은 이 축에서 «그대로 남는다»** — "
        "`REC-` 는 라벨을 쓰지 않는 축이다(PD-7 3번). 그 건이 이 축에서 빠지는 이유는 "
        "**라벨이 아니라 `approx`** 다.")
    say("6. 🔒 **`REC-Z4` 의 귀결이 결정 ④로 소멸했다** — 조건 충족 건수(§9)만 남겼고 "
        "**등급 이름을 미리 고르지 않았다**(PD-16).")
    say()
    say("🔴 **이 문서는 라이브 채택 대상이 아니다**(`PREREG.md` §0-2). **새 예측을 만들지 않았다** — "
        "동결된 항목(`PREREG_POST6.md` §4 #38~#54)만 계산했다.")
    say()
    say("[[LABELS_2026-09-15_post7]] · [[INTAKE_2026-09-15_post7]] · [[PREDECISION_2026-09-15_post7]] · "
        "[[PREREG_POST6]] · [[PREREG_ANCHOR_REDESIGN]] · [[PREREG_GRADE_TIERS]] · "
        "[[RESULTS_RECONSTRUCT_POST6]] · [[RESULTS_RECONSTRUCT_POST5]]")

    (BASE / "RESULTS_RECONSTRUCT_POST7_NUMBERS.md").write_text("\n".join(OUT) + "\n",
                                                               encoding="utf-8")
    cur.close()
    conn.close()
    print("\n[written] RESULTS_RECONSTRUCT_POST7_NUMBERS.md")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())

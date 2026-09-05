# -*- coding: utf-8 -*-
"""`WRC-` 축 탐색 실행 — 다중체결 «가중» 평단 복원(`PREREG_WEIGHTED_RECON.md` §0-3 **3번**).

🔬 **탐색 표기 · 판정 아님.** 대상은 **post4·post5 «만»**이다(`WRC-O1` · §4-5).
post6 은 이 스크립트가 도는 시점에 **존재하지 않는다** — 어떤 post6 수치도 이 산출물에 없다.

사전등록: `PREREG_WEIGHTED_RECON.md`(동결 2026-09-02 · `WRC-D1`~`D7` 사장님 확정)
  §1 현행 제약 실측(C-S1·C-S2·C-L·C-P) · §2 모델(`WRC-A0`·`A1`·`A3`·`A4`) · §2-4 부분집합 정리
  §4 가드(`WRC-P1`·`N1`·`N2`·`B1`·`G1`·`O1`·`X1`·`V1`) · §5 실행 전제 · §6-1 판정 분모 · §7-B 실행 점검표

🔴 **계산 «전» 에 고정한 해석 결정 (A-1 ~ A-11)** — `RESULTS_RECONSTRUCT_POST5.md` §1 동결분을
   `PREREG_WEIGHTED_RECON.md` §1-3 이 *「전부 승계하고 스크립트 docstring 에 같은 문장을 박는다」*
   고 요구한다. 아래는 `run_reconstruct_post5.py` docstring 과 **같은 문장**이다:

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

⚠️ **A-1 의 «값»에 대한 승계 고지**: `PREREG_WEIGHTED_RECON.md` §5-2 2번 · `WRC-D7` 은
   창 종료일을 *「`PREREG_POST6.md` 실행 시 **DB 스냅샷 최대일**(A-1 승계)」* 로 동결했다.
   ⇒ **규칙(「DB 스냅샷 최대일」)을 승계하고 값은 실행 시점에서 다시 읽는다.**
   A-1 이 적은 `2026-08-28` 은 post5 실행 시점의 값이며, 이 실행의 값은 §0 에 박는다.
   🔴 그래서 **창이 post4(`~2026-08-21`)·post5(`~2026-08-28`)보다 길다** — 창이 길면 feasible set 은
   **넓어지기만 한다**(단조). 그 이동분은 §6 에서 세 열로 갈라 인쇄한다.

`WRC-` 축이 여기에 «처음» 거는 것(§2-1 공통 부가 제약 (가)(나)(다)(라)):
  (가) 순서 : `P₁ > P₂ > … > P_N` — 하향 분할매수 사다리. 동률 허용 안 함.
  (나) 도달 : 각 `Pₖ` 는 창 안 «어느 날의» `[저, 고]` 안 (`C-S2` 를 매수 쪽에 건 것).
  (다) 격자 : 각 `Pₖ` 는 호가 격자 위 — `reconstruct_prices.tick`/`grid_prices` 를 **import 해서** 쓴다.
  (라) 앵커 : `bₖ = 1 − Pₖ/H` · `H` = **등록일 고가** · `H < 창 최고가` 여부를 건별 의무 인쇄(`REC-Z3`).

🔴 `WRC-R6`(§5-1) — 호가단위·격자·해찾기는 **전부 기존 함수 import**:
   `reconstruct_prices.tick` · `.grid_prices` · `run_reconstruct_post5.leg_intervals` ·
   `.feasible_exact` · `._merge` · `._intersect` · `.iv_measure`. **표를 복사해 다시 쓰지 않는다.**
🔴 라이브 트리 import 0건 · DB 는 SELECT 만 · `adj_factor` 산술 0건 · 원장은 «읽기»만.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import psycopg2

from reconstruct_prices import gross_ret, grid_prices, tick
from run_reconstruct_post4 import TARGETS as TARGETS_P4
from run_reconstruct_post5 import (
    TARGETS as TARGETS_P5,
    _intersect,
    _merge,
    feasible_exact,
    iv_has,
    iv_max,
    iv_measure,
    iv_min,
    leg_intervals,
    min_residual,
)
from run_selection import PSEUDO
from run_tests import DSN

BASE = Path(__file__).resolve().parent
ART = BASE / "wrc_explore"
OUT: list[str] = []

SEED = 20260815          # §4-2 · `PREREG_POST6.md` §3-1 동결분
NREP = 20000             # 〃 (🔴 `run_selection.py:22` 는 NREP = 2000 — 차이를 §4 에 인쇄한다)
THR = (0.020, 0.022)     # A-10 · `REC-Z5` (판정 0.022 · 의무 민감도 0.020)
BAND_THR = 3.0           # %p · `WRC-P1`/`N2` 문턱 (RESULTS_RECONSTRUCT_POST4.md §6 Y1 «차용»)
G1_THR = 1.0 / 3.0       # `WRC-G1` 문턱 (〃 Y3 «차용»)
N_THR = 0.50             # `WRC-N1`·`N2` 문턱 (RESULTS_D1_OOS_POST5.md §9 W7 «차용»)

# §5-4 `WRC-R9` — 모든 `bₖ` 표에 «그대로» 붙이는 4줄.
NOTATION_4 = [
    "1. 🔴 **「라이브 채택 금지 — 이 표의 어떤 숫자도 매매 규칙으로 옮기지 않는다」**(`PREREG.md` §0-2).",
    "2. 🔴 **「검정 안 된 «후보»다 — `WRC-P1` 판정 전이거나 강등 상태면 그 사실을 이 줄에 적는다」** "
    "→ 🔬 **이 회차는 `WRC-P1` «판정 전»이다**(판정은 post6 부터 · §4-5 `WRC-O1`). "
    "그리고 `WRC-G1` 이 탐색 표본에서 «발동» 중이다(§1).",
    "3. 🔴 **「`P` 의 불확실성을 그대로 물려받는다 — 「존재한다」류 주장조차 약하다」** "
    "(`RESULTS_RECONSTRUCT_POST5.md` §10 승계).",
    "4. 🔴 **「이 표는 «단일 평단 전제가 성립한 건»만 담는다 — 그 배제는 무작위가 아니다」**"
    "(§5-3 2번 · 두 문장 묶음): "
    "*「`WRC-G1` 사유 ④ 가 `feasible(A0) = ∅` 인 건을 전부 분자로 보내 측정 불가로 처리한다 ⇒ "
    "중단 대상인 「전제가 깨진 건」은 이 축에 애초에 들어오지 못한다」* 와 "
    "*「그 배제는 무작위가 아니다 — 레그 간격이 촘촘한 건에 몰린다」* 는 **하나의 사실**이다.",
]


def say(s=""):
    print(s)
    OUT.append(s)


def med(xs):
    """중앙값 — `PREREG_POST6.md` §5-4(C-20) 관용구: **분모가 짝수면 두 가운데 값의 평균**이고
    그 사실을 산출물에 인쇄한다. (관용구 결함이 계열에서 이미 한 번 잡혔다.)"""
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def med_note(n):
    return "짝수 ⇒ 두 가운데 값의 «평균»" if n % 2 == 0 else "홀수 ⇒ 가운데 값"


def sha_list(xs):
    return hashlib.sha256(("\n".join(xs)).encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# 1. 창·격자 문맥 (`WRC-A1` 의 (나)(다) 를 만족하는 격자 집합 `G_win`)
# ══════════════════════════════════════════════════════════════════════════════
def make_ctx(rows):
    """rows = [(date, open, high, low, close)] (창 안 전 봉 · 오름차순).

    `G_win` = **창 안 어느 날의 `[저,고]` 안에 있는 호가 격자 값 전부** — (나)+(다).
    격자는 `reconstruct_prices.grid_prices`(=`tick` 승계)를 **import 해서** 만든다(`WRC-R6`).
    봉 구간은 `run_reconstruct_post5._merge` 로 합쳐서 훑는다(같은 이유 · 재정의 금지)."""
    ranges = [(r[3], r[2]) for r in rows]
    lo, hi = min(r[3] for r in rows), max(r[2] for r in rows)
    grid = grid_prices(lo, hi)
    merged = _merge(ranges)                    # (나) 도달 가능 구간 — 합집합
    U, mi = [], 0
    for p in grid:
        while mi < len(merged) and merged[mi][1] < p:
            mi += 1
        if mi < len(merged) and merged[mi][0] <= p <= merged[mi][1]:
            U.append(p)
    if not U:
        return None
    g = 0
    for x in U:
        g = math.gcd(g, int(x))
    u = [int(x) // g for x in U]
    # «연속» = 단위 격자에서 정수가 빈틈없이 이어진다 ⇒ §2 의 닫힌 형태가 성립한다(아래 주석).
    contiguous = (u[-1] - u[0] == len(u) - 1)
    return dict(rows=rows, ranges=ranges, lo=lo, hi=hi, grid=grid, U=U, g=g, u=u,
                contiguous=contiguous, o0=rows[0][1], h0=rows[0][2], l0=rows[0][3],
                c0=rows[0][4], d0=rows[0][0], dend=rows[-1][0], nbar_inc=len(rows))


# ══════════════════════════════════════════════════════════════════════════════
# 2. `WRC-A1`(균등 1/N) — 조합 열거를 «하지 않고» 정확히 푸는 방법
# ══════════════════════════════════════════════════════════════════════════════
# 🔴 **왜 전수 열거를 안 하는가**: `G_win` 은 실측 262~751개이고 `N ≤ 5` 이므로 조합 수는
#    C(751,5) ≈ 1.9e12 다. 열거는 불가능하다. 아래는 **근사가 아니라 «정확»한 재정식화**다.
#
# (가) 가 강한 순서(`P₁ > … > P_N`, 동률 금지)이므로 조합 하나 = `G_win` 의 **N-원소 «집합»**
#      하나와 1:1 대응한다(내림차순 배열은 유일). ⇒ 문제는 **부분합(subset-sum)** 이 된다:
#      `P = (1/N)·Σ Pₖ` 가 `feasible(A0)` 안에 드는 N-원소 집합이 존재하는가.
#
# ① **연속 격자일 때(실측: 판정 분모 9건 전부 · 대조군 다수)** — 닫힌 형태가 «정확»하다.
#    단위 정수 구간 `[a,b]` 에서 서로 다른 j개를 고른 합의 집합은 **연속 정수 구간**
#    `[j·a + j(j−1)/2, j·b − j(j−1)/2]` 이다(원소를 한 칸씩 옮겨 어떤 합도 만든다).
#    차수 `k`(1 = 최고가)의 값을 `v` 로 고정하면 「위 `k−1`개는 `(v,b]` 에서 · 아래 `N−k`개는
#    `[a,v)` 에서」 이고 두 쪽 합이 각각 연속 구간이므로 **총합도 연속 구간**이다.
#    ⇒ `(v,k)` 의 가능 여부 = 그 구간이 목표 합 집합과 겹치는가 — **O(1)**.
# ② **불연속일 때(대조군의 일부 — 호가단위 경계를 걸치거나 봉 사이에 틈이 있는 종목)** —
#    ①의 「연속」 전제가 깨지므로 **비트셋 부분합 DP** 로 «정확히» 푼다(근사 아님).
# 🟢 ①과 ②는 **같은 답을 내야 한다** — 연속 격자 건에서 둘 다 돌려 교차검증하고 그 건수를
#    산출물에 인쇄한다(`WRC-X1` 구현 점검).


def sum_targets(iv, N, g):
    """`P ∈ iv` ⟺ 합 `S`(단위) ∈ 반환 구간들. `P = g·S/N` · 구간은 `(lo, hi]`(A-11 승계)."""
    out = []
    for a, b in iv:
        s0 = math.floor(N * a / g) + 1          # S > N·a/g
        s1 = math.floor(N * b / g + 1e-9)       # S ≤ N·b/g
        if s1 >= s0:
            out.append((s0, s1))
    return out


def _hits(rngs, s0, s1):
    return any(not (s1 < a or b < s0) for a, b in rngs)


def a1_closed(u, N, tgt):
    """① 연속 격자 닫힌 형태. 반환 (feasible, n_means, ext, (smin_ok, smax_ok))."""
    a, b = u[0], u[-1]
    V = len(u)
    if V < N:
        return False, 0, None, None
    smin = N * a + N * (N - 1) // 2
    smax = N * b - N * (N - 1) // 2
    n_means = 0
    s_ok = []
    for s0, s1 in tgt:
        x0, x1 = max(s0, smin), min(s1, smax)
        if x1 >= x0:
            n_means += x1 - x0 + 1
            s_ok.append((x0, x1))
    if n_means == 0:
        return False, 0, None, None
    ext = []
    for k in range(1, N + 1):
        vlo, vhi = a + (N - k), b - (k - 1)
        above_hi = (k - 1) * b - (k - 2) * (k - 1) // 2
        below_lo = (N - k) * a + (N - k - 1) * (N - k) // 2

        def _ok(v, _k=k, _ah=above_hi, _bl=below_lo):
            lo_s = v + (_k - 1) * v + (_k - 1) * _k // 2 + _bl
            hi_s = v + _ah + (N - _k) * (v - 1) - (N - _k - 1) * (N - _k) // 2
            return _hits(tgt, lo_s, hi_s)

        vmin = next((v for v in range(vlo, vhi + 1) if _ok(v)), None)
        vmax = next((v for v in range(vhi, vlo - 1, -1) if _ok(v)), None)
        if vmin is None or vmax is None:
            return False, n_means, None, None
        ext.append((vmin, vmax))
    return True, n_means, ext, (min(x for x, _ in s_ok), max(y for _, y in s_ok))


def _dp_sums(vals, maxk):
    dp = [0] * (maxk + 1)
    dp[0] = 1
    for v in vals:
        for j in range(maxk, 0, -1):
            if dp[j - 1]:
                dp[j] |= dp[j - 1] << v
    return dp


def _mask(tgt, top):
    m = 0
    for s0, s1 in tgt:
        s0 = max(s0, 0)
        s1 = min(s1, top)
        if s1 >= s0:
            m |= ((1 << (s1 - s0 + 1)) - 1) << s0
    return m


def _conv_hits(A, B, shift, tm):
    """∃ a∈A, b∈B : (a + b + shift) ∈ tm ?  — 작은 쪽 비트를 훑는다(근사 아님 · 정확)."""
    if bin(A).count("1") > bin(B).count("1"):
        A, B = B, A
    t = tm >> shift
    if not t:
        return False
    x = A
    while x:
        low = x & -x
        a = low.bit_length() - 1
        if (B << a) & t:
            return True
        x ^= low
    return False


def a1_dp(u, N, tgt):
    """② 불연속 격자 — 비트셋 부분합 DP(정확). 반환 (feasible, n_means, ext, (smin,smax))."""
    V = len(u)
    if V < N:
        return False, 0, None, None
    top = N * u[-1] + 1
    tm = _mask(tgt, top)
    if not tm:
        return False, 0, None, None
    dp = _dp_sums(u, N)
    hit = dp[N] & tm
    if not hit:
        return False, 0, None, None
    n_means = bin(hit).count("1")
    s_lo = (hit & -hit).bit_length() - 1
    s_hi = hit.bit_length() - 1
    # 접미 DP: SUF[i][j] = u[i:] 에서 j개를 고른 합 비트셋 · 접두 DP: PRE[i][j] = u[:i]
    SUF = [None] * (V + 1)
    cur = [0] * N
    cur[0] = 1
    SUF[V] = list(cur)
    for i in range(V - 1, -1, -1):
        nxt = list(cur)
        for j in range(N - 1, 0, -1):
            if cur[j - 1]:
                nxt[j] |= cur[j - 1] << u[i]
        cur = nxt
        SUF[i] = list(cur)
    PRE = [None] * (V + 1)
    cur = [0] * N
    cur[0] = 1
    PRE[0] = list(cur)
    for i in range(V):
        nxt = list(cur)
        for j in range(N - 1, 0, -1):
            if cur[j - 1]:
                nxt[j] |= cur[j - 1] << u[i]
        cur = nxt
        PRE[i + 1] = list(cur)
    ext = []
    for k in range(1, N + 1):
        def _ok(i, _k=k):
            below = PRE[i][N - _k]
            above = SUF[i + 1][_k - 1]
            if not below or not above:
                return False
            return _conv_hits(below, above, u[i], tm)
        imin = next((i for i in range(V) if _ok(i)), None)          # 값이 작을수록 i 가 작다
        imax = next((i for i in range(V - 1, -1, -1) if _ok(i)), None)
        if imin is None or imax is None:
            return False, n_means, None, None
        ext.append((u[imin], u[imax]))
    return True, n_means, ext, (s_lo, s_hi)


def a1_solve(ctx, N, ivA0, cross=False):
    """`WRC-A1` 정확해. cross=True 면 ①②를 둘 다 돌려 교차검증한다."""
    if not ivA0 or N < 2:
        return None
    tgt = sum_targets(ivA0, N, ctx["g"])
    if not tgt:
        return None
    u = ctx["u"]
    if ctx["contiguous"]:
        feas, nm, ext, srng = a1_closed(u, N, tgt)
        out = dict(feasible=feas, n_means=nm, ext=ext, srng=srng, path="closed", cross=None)
        if cross:
            f2, nm2, ext2, s2 = a1_dp(u, N, tgt)
            out["cross"] = (feas == f2 and nm == nm2 and ext == ext2 and srng == s2)
            out["cross_ref"] = (f2, nm2, ext2, s2)
        return out
    feas, nm, ext, srng = a1_dp(u, N, tgt)
    return dict(feasible=feas, n_means=nm, ext=ext, srng=srng, path="dp", cross=None)


def feasible_plo(rows, legs, plo):
    """`feasible_exact` 와 «같은 구성»인데 `C-P` 하단만 `plo` 로 바꾼다(gross 전용).

    🔴 새 솔버가 아니다 — `leg_intervals`·`_merge`·`_intersect` 를 **import 해서** 조립한 것이며
    `plo = lo·0.7` 이면 `feasible_exact` 와 항등이다(§2-1 에서 그 항등을 실측 확인한다).
    쓰임: `A1`·`A3` 가 `P` 하단을 `lo·0.7` → `min G_win` 으로 «끌어올리는» 효과(§2-5)를
    **다른 경로로** 재현해 `_intersect` 결과와 대조한다."""
    ranges = [(r[3], r[2]) for r in rows]
    lo, hi = min(r[3] for r in rows), max(r[2] for r in rows)
    grid = grid_prices(lo, hi)
    acc = None
    for r in legs:
        iv = _merge(leg_intervals(r, ranges, grid, plo, hi, 1.0))
        acc = iv if acc is None else _intersect(acc, iv)
        if not acc:
            return []
    return acc or []


def a3_set(ctx, ivA0):
    """`WRC-A3`(자유 가중) feasible `P` 집합 = `A0` ∩ `[min G_win, max G_win]` (§2-4 3번).

    `_intersect` 를 **import 해서** 쓴다(`WRC-R6`)."""
    if not ivA0:
        return []
    return _intersect(ivA0, [(ctx["U"][0], ctx["U"][-1])])


def a3_bands(ctx, N):
    """`WRC-A3` 차수별 밴드 — 🔴 **「무정보 상한」으로만 인쇄**(§2-6 `WRC-R4`).

    가중치가 자유이므로 차수 `k` 의 값은 「위에 `k−1`개, 아래 `N−k`개가 남는」 모든 격자값을
    취할 수 있다 ⇒ `[u[N−k], u[V−k]]`. 🔴 이건 **상한**이다(실제 `A3` 밴드 ⊆ 이 구간).
    지지로 인용 금지 — `WRC-P1` 의 분자·분모에 넣지 않는다."""
    U = ctx["U"]
    V = len(U)
    if V < N:
        return None
    return [(U[N - k], U[V - k]) for k in range(1, N + 1)]


def bands_from_ext(ext, ctx):
    """차수별 `(Pmin, Pmax)` → `bₖ = 1 − Pₖ/H` 밴드·폭(%p)·호가 칸수(`REC-Y2` 승계)."""
    H = ctx["h0"]
    out = []
    for (vmin, vmax) in ext:
        pmin, pmax = vmin * ctx["g"], vmax * ctx["g"]
        blo, bhi = 100 * (1 - pmax / H), 100 * (1 - pmin / H)
        t = tick(pmin)
        out.append(dict(pmin=pmin, pmax=pmax, b_lo=blo, b_hi=bhi,
                        w=bhi - blo, cells=(pmax - pmin) / t, tick=t))
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 3. 원장 읽기 → §6-1 판정 분모 게이트 (재측정 · §1-4 표를 «복사하지 않는다»)
# ══════════════════════════════════════════════════════════════════════════════
def read_ledger():
    import csv
    tr = list(csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")))
    lg = list(csv.DictReader((BASE / "ledger_legs.csv").open(encoding="utf-8")))
    legs = {}
    for r in lg:
        legs.setdefault((r["post_log_no"], r["item_no"]), []).append(
            (int(r["leg_idx"]), float(r["ret_pct"])))
    for k in legs:
        legs[k] = [v for _, v in sorted(legs[k])]
    return tr, legs


CODEMAP = {t[0]: t[1] for t in TARGETS_P4}
CODEMAP.update({t[0]: t[1] for t in TARGETS_P5})


POST_LABEL = {"2026-08-22": "post4", "2026-08-29": "post5"}


def build_cases(tr, legs):
    """🔴 **원장 «전 글»**을 대상으로 §6-1 게이트를 다시 계산한다.

    §1-4 의 `exact 18` 은 «원장 전 글» 기준이고 판정 분모 10 은 그 부분집합이다 —
    post4·5 로 먼저 자르면 분모가 달라진다(초판이 그 실수를 했다)."""
    cases = []
    for r in tr:
        v = legs.get((r["post_log_no"], r["item_no"]), [])
        fill_n = int(r["fill_n"]) if r["fill_n"].strip() else None
        distinct = len(set(v))
        gate = (r["reg_date_precision"] == "exact" and fill_n is not None
                and fill_n >= 2 and distinct >= 3)
        cases.append(dict(
            post=POST_LABEL.get(r["post_date"], r["post_date"]),
            log_no=r["post_log_no"], item=r["item_no"], name=r["stock_name"],
            code=CODEMAP.get(r["stock_name"]), reg=r["reg_date"],
            prec=r["reg_date_precision"], fill_level=r["fill_level"], fill_n=fill_n,
            legs=v, n_legs=len(v), distinct=distinct,
            open_ended=int(r["open_ended"]), prog_ver=r["prog_ver"],
            preset=r["preset"], gate=gate))
    return cases


# ══════════════════════════════════════════════════════════════════════════════
# 4. main
# ══════════════════════════════════════════════════════════════════════════════
def main() -> int:
    t_start = time.time()
    ART.mkdir(exist_ok=True)
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    # ── §0. 실행 환경 ──────────────────────────────────────────────────────
    def git(*a):
        try:
            return subprocess.run(["git", *a], cwd=str(BASE), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace").stdout.strip()
        except Exception:  # noqa: BLE001
            return "(git 실행 실패)"

    head = git("rev-parse", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    anc = subprocess.run(["git", "merge-base", "--is-ancestor", "8d28e14", "HEAD"],
                         cwd=str(BASE), capture_output=True).returncode == 0
    cur.execute("SELECT max(date) FROM daily_prices")
    END = cur.fetchone()[0]
    cur.execute("SELECT count(*), count(DISTINCT stock_code) FROM daily_prices WHERE date=%s", (END,))
    end_rows, end_codes = cur.fetchone()

    say("# RESULTS_WRC_EXPLORE — 기계 생성 (수정 금지)\n")
    say("생성 `run_wrc_explore.py` · 사전등록 **`PREREG_WEIGHTED_RECON.md`**(§0-3 **3번** 탐색 실행)")
    say("재사용 `reconstruct_prices.py`(`tick`·`grid_prices`) · "
        "`run_reconstruct_post5.py`(`leg_intervals`·`feasible_exact`·`_merge`·`_intersect`·`iv_measure`)\n")
    say("🔬🔬 **이 문서의 «모든» 값은 탐색 표기이며 판정이 아니다** — 대상은 **post4·post5 «만»**이다"
        "(`WRC-O1` §4-5). **post6 은 이 실행 시점에 존재하지 않는다.** 판정은 post6 부터 누적한다.")
    say("⇒ 🔴 **이 문서의 모든 표에서 「판정(post6~ 누적)」 열은 ⬜ «미도래»다** — "
        "§4-6 이 그 병기표를 한 자리에 모아 둔다(§4-5 가 요구한 «항상 나란히»).\n")
    say("🔴 **라이브 채택 금지** — 이 문서의 어떤 숫자도 매매 규칙·파라미터로 옮기지 않는다"
        "(`PREREG.md` §0-2 · §0-1 승계).\n")
    say("## §0. 실행 환경 (`WRC-R7` · §5-2)\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| 브랜치 | `{branch}` {'✅' if branch == 'fix/tasso-post6-s5-fixes' else '🔴 **다르다**'} |")
    say(f"| `8d28e14`(§5-2 가 적은 그때의 HEAD)가 조상인가 | {'✅ 예' if anc else '🔴 아니오'} |")
    say("| HEAD 해시 | 🔴 **이 파일에 적지 않는다** — stdout 에만 낸다(아래 사유) |")
    say(f"| **DB 스냅샷 최신 봉** | **`{END}`** (그날 {end_rows:,}행 · {end_codes:,}종목) |")
    say(f"| 창 규약 | `[등록일, {END}]` — `WRC-D7`(A-1 의 «규칙» 승계 · 값은 실행 시 재측정) |")
    say(f"| 시드 · 반복 | `{SEED}` · **{NREP:,}회** |")
    say("| 잔차 문턱 | 판정 `0.022%p` · 의무 민감도 `0.020%p` (`REC-Z5`) |")
    say(f"| 중앙값 관용구 | {med_note(2)} / {med_note(3)} — **C-20 감사 결과 그대로**(§4-1) |")
    say()
    say(f"- 🔴 **`NREP` 고지**(§4-2): 이 축은 **{NREP:,}회**를 쓴다. "
        f"`run_selection.py:22` 는 **`NREP = 2000`** 이다 — **차이는 {NREP // 2000}배**이며 "
        "이 축의 값은 `PREREG_POST6.md` §3-1 동결분(20,000)을 따른다.")
    say(f"- 🔴 **창이 동결 산출물보다 길다**: post4 는 `~2026-08-21`, post5 는 `~2026-08-28` 이었고 "
        f"이 실행은 `~{END}` 다. 창이 길면 feasible set 은 **넓어지기만 한다**(단조) — "
        "그 이동분은 §6 에서 세 열로 갈라 인쇄한다.")
    say("- 🔴🔴 **HEAD 해시를 이 파일에 «박지 않는» 이유**(재현 게이트와의 충돌): 이 산출물은 "
        "§0-3 **4번(동결 커밋)**에서 커밋된다 ⇒ 커밋되는 «순간» HEAD 가 바뀐다 ⇒ "
        "***해시를 본문에 적으면 `regen_gate.py --rerun` 의 byte 비교가 «구조적으로» 실패한다*** "
        "(재실행이 새 HEAD 를 적어 넣는다). 그러면 이 문서 말미의 「같은 스냅샷에서 byte 동일」 "
        "주장과도 모순된다. ⇒ **본문에는 «브랜치 이름»과 «`8d28e14` 조상 여부(불변 참/거짓)»만 "
        "남기고 해시는 stdout 으로 뺀다.** 🔑 *커밋마다 바뀌는 값을 산출물에 적으면 그 산출물은 "
        "자기 자신을 재현할 수 없게 된다.*")
    say("- 🔴 **주말 규약**(`RESULTS_LADDER_TRANCHE.md` §1 `B-1` 승계): 발행일이 토·일이면 창은 "
        f"직전 거래일에서 끝난다. 이번 창 종료일 `{END}` 는 **거래일**이고 그날 봉이 "
        f"{end_rows:,}종목에 존재한다 ⇒ 규약이 «발동하지 않는» 실행이다.")

    # C-17~C-22 반영 확인 (§5-2 1번 — 안 들어갔으면 무효)
    c22 = (BASE / "RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS.md").exists()
    c17 = (BASE / "RESULTS_S5_SIDEBYSIDE.md").exists()
    gate_src = (BASE / "regen_gate.py").read_text(encoding="utf-8")
    c19 = "daily_prices[>=2026-04-01]" in gate_src
    registered = '"RESULTS_WRC_EXPLORE.md"' in gate_src
    ledger_fields = (BASE / "ledger_trades.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    say()
    say("**§5-2 1번 — C-17~C-22 반영 확인**(안 들어갔으면 이 산출물은 무효):\n")
    say("| 코드 항목 | 확인 방법 | 결과 |")
    say("|---|---|---|")
    say(f"| C-19 (`regen_gate` 지문 상한 제거) | `daily_prices[>=2026-04-01]` 슬라이스 존재 | "
        f"{'✅' if c19 else '🔴 **없다**'} |")
    say(f"| C-21 (`fill_n`) | `ledger_trades.csv` 필드 수 = **{len(ledger_fields)}** (17 이어야) | "
        f"{'✅' if len(ledger_fields) == 17 else '🔴 **다르다**'} |")
    say(f"| C-22 (post4 정확법) | `RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS.md` 존재 | "
        f"{'✅' if c22 else '🔴 **없다**'} |")
    say(f"| C-17·18·20·21 병기 | `RESULTS_S5_SIDEBYSIDE.md` 존재 | {'✅' if c17 else '🔴 **없다**'} |")
    say(f"| §5-2 4번 (`regen_gate` 등재) | `regen_gate.py` 의 `PAIRS` 에 `RESULTS_WRC_EXPLORE.md` | "
        f"{'✅ 등재됨' if registered else '🔴 **미등재**'} |")

    # ── 원장 → 게이트 재측정 ────────────────────────────────────────────────
    tr, legs_map = read_ledger()
    # 🔴🔴 **post6 이후 글의 «명시» 제외** — 이 산출물은 §0-3 3번(탐색)이고 대상은 post4·post5 «만»이다
    #    (`WRC-O1` §4-5). 초판은 이 필터를 **`POST_LABEL` 에 «암묵적으로» 맡겼는데**, `POST_LABEL` 은
    #    이름을 붙이는 «맵»일 뿐 «필터»가 아니다 — 원장에 6번째 글이 append 되자
    #    (2026-09-04 · 12행/47레그) `build_cases` 가 그 글의 5건을 판정 분모에 «그대로 통과»시켰다
    #    (실측: 원장 50→62행 · `exact` 18→28 · 판정 분모 10→**15**).
    #    ⇒ 그러면 이 «탐색» 산출물이 판정 표본을 삼켜 `WRC-O1`(탐색/판정 분리)이 무너지고,
    #      동결본(`FREEZE_WRC_2026-09-02.md`)의 byte 재현도 구조적으로 깨진다.
    #    🔑 ***「그 날짜가 아직 없으니 안 걸린다」는 필터가 아니다 — 날짜는 오고, 그때 조용히 들어온다.***
    #    (post1~3 은 남긴다: §1-4 의 「원장 전 글」 = 50행 기준이 그 셋을 포함한다.)
    EXPLORE_UPTO = "2026-08-29"          # = post5 발행일. 그 «뒤» 글은 판정 표본이라 여기 오지 않는다.
    tr = [r for r in tr if r["post_date"] <= EXPLORE_UPTO]
    cases = build_cases(tr, legs_map)
    n_all = len(tr)
    exact = [c for c in cases if c["prec"] == "exact"]
    gate_in = [c for c in cases if c["gate"]]
    blank = [c for c in exact if c["fill_n"] is None]
    only1 = [c for c in exact if c["fill_n"] == 1]
    few = [c for c in exact if c["fill_n"] is not None and c["fill_n"] >= 2 and c["distinct"] < 3]

    say()
    say("### 0-1. 원장 재측정 (§1-4 표를 «복사하지 않고» 다시 셌다)\n")
    say("| 구분 | 실측 | 문서 §1-4 | 일치 |")
    say("|---|---|---|---|")
    for lab, got, doc in [("전체(원장 전 글)", n_all, 50),
                          ("`reg_date_precision = exact`(원장 전 글)", len(exact), 18),
                          ("─ `fill_n` 빈칸", len(blank), 2),
                          ("─ `fill_n = 1`", len(only1), 4),
                          ("─ 다차수인데 서로 다른 값 레그 < 3", len(few), 2),
                          ("⇒ **판정 분모**", len(gate_in), 10)]:
        say(f"| {lab} | **{got}** | {doc} | {'✅' if got == doc else '🔴 **다르다**'} |")
    say()
    say(f"- 게이트 통과율(`exact` 대비) = **{len(gate_in)}/{len(exact)} = "
        f"{100*len(gate_in)/len(exact):.1f}%** (§4-6 이 분모 정의의 일부로 따로 인쇄하라 한 값 — "
        f"문서값 **10/18 = 55.6%**)")
    say(f"- 🔴 **분모는 «원장 전 글»에서 셌다** — 게이트를 통과한 {len(gate_in)}건이 "
        f"«전부» post4·post5 인지 실측: "
        f"**{sorted({c['post'] for c in gate_in})}** "
        f"⇒ {'✅ 그렇다' if {c['post'] for c in gate_in} <= {'post4', 'post5'} else '🔴 아니다'}")
    say(f"- 🔴 `open_ended = 1` 이 판정 분모 **{sum(c['open_ended'] for c in gate_in)}/{len(gate_in)}** "
        "— 시퀀스가 열려 있어 제약이 실제보다 «적다»(feasible 을 넓히는 방향).")
    say(f"- `prog_ver` 실측 집합(원장 전 글) = "
        f"**{{{', '.join(sorted({c['prog_ver'] for c in cases}))}}}** · "
        f"판정 분모 안 = **{{{', '.join(sorted({c['prog_ver'] for c in gate_in}))}}}** "
        "(§9 공변량 기록 — 부호가 버전별로 갈리면 통합 결론을 내지 않는다)")

    # ── 창·문맥 적재 (판정 분모 건만) ─────────────────────────────────────
    for c in gate_in:
        c["ctx"] = None
        if not c["code"]:
            continue
        cur.execute("SELECT date, open, high, low, close FROM daily_prices "
                    "WHERE stock_code=%s AND date BETWEEN %s AND %s ORDER BY date",
                    (c["code"], c["reg"], END))
        rows = cur.fetchall()
        if not rows:
            continue
        c["ctx"] = make_ctx(rows)
        cur.execute("SELECT count(*), min(date) FROM daily_prices WHERE stock_code=%s AND date < %s",
                    (c["code"], c["reg"]))
        c["nbar_pre"], c["first_bar"] = cur.fetchone()
        cur.execute("SELECT min(low), max(high) FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s", (c["code"], c["reg"], END))
        c["win_lo"], c["win_hi"] = cur.fetchone()

    # ── §1. `WRC-G1` — «먼저» 계산한다 (§7-B #24) ───────────────────────────
    say()
    say("---\n")
    say("## §1. `WRC-G1` (커버리지 가드) — **가장 먼저 계산한다** (§7-B #24)\n")
    say("🔴 **계산 순서를 못 박은 이유**: §4-6 이 *「1/3 이상이면 나머지 계산을 «돌리지 않는다»」* 라고 "
        "적었다. 그래서 `A0`·`A1`·`A3`·`A4` 를 «한 줄도» 계산하기 전에 이 절을 냈다.\n")
    say("**분자 = ①DB부재 + ④현행 해 0개** · 분모 = 판정 분모(§6-1). "
        "🔴 ②(`fill_n` 빈칸)·③(레그 <3)은 **분모 정의의 일부라 분자가 될 수 없다**(§4-6 정정).\n")

    for c in gate_in:
        c["a0"] = feasible_exact(c["ctx"]["rows"], c["legs"], "gross") if c["ctx"] else None
    g1_rows = []
    for post in ("post4", "post5"):
        sub = [c for c in gate_in if c["post"] == post]
        db_missing = [c for c in sub if c["ctx"] is None]
        zero = [c for c in sub if c["ctx"] is not None and not c["a0"]]
        g1_rows.append((post, len(sub), db_missing, zero))
    say("| 글 | 판정 분모 | ① DB부재 | ④ 해 0개 | **`WRC-G1`** | 게이트(≥ 1/3) |")
    say("|---|---|---|---|---|---|")
    tot_n = tot_a = tot_z = 0
    for post, n, dm, zr in g1_rows:
        v = (len(dm) + len(zr)) / n
        tot_n += n
        tot_a += len(dm)
        tot_z += len(zr)
        say(f"| {post} | {n} | {len(dm)} ({', '.join(c['name'] for c in dm) or '—'}) | "
            f"{len(zr)} ({', '.join(c['name'] for c in zr) or '—'}) | "
            f"**{len(dm)+len(zr)}/{n} = {100*v:.1f}%** | "
            f"{'🔴 **발동**' if v >= G1_THR else '🟢 미발동'} |")
    g1 = (tot_a + tot_z) / tot_n
    say(f"| **합** | **{tot_n}** | **{tot_a}** | **{tot_z}** | 🔴🔴 **{tot_a+tot_z}/{tot_n} = "
        f"{100*g1:.1f}%** | {'🔴 **발동**' if g1 >= G1_THR else '🟢 미발동'} |")
    say()
    say(f"- 문서 §4-6 이 적은 값 = post4 **1/5 = 20.0%** · post5 **5/5 = 100.0%** · 합 **6/10 = 60.0%** "
        f"⇒ 실측과 **{'일치' if abs(g1 - 0.6) < 1e-9 else '🔴 불일치 — 실측을 쓴다'}**")
    say("- 🔴 **편향 방향 신고**(§4-6): ① 은 **신규 상장주에 집중**되고 저자는 신규주를 자주 고른다 · "
        "④ 도 무작위가 아니다 — **레그 간격이 촘촘한 건**에 몰린다. "
        "⇒ ***측정 불가가 무작위가 아니다.***")
    say("- 🔴 **④ 는 「값을 보고 뺀 것」이 아니다** — §2-4 의 정리로 **계산 «전»에 이미 확정**되는 부류다. "
        "그래도 분자에 넣어 센다(빼면 커버리지가 좋아 보인다).")
    say()
    say("### 🔴🔴 여기서 «멈추지 않는» 이유 (§7-B #24 의 문언 대조)\n")
    say("#24 는 *「**post6 판정 분모**의 `WRC-G1` 을 먼저 계산한다 — 1/3 이상이면 나머지 계산을 "
        "돌리지 않는다」* 다. 🔴 **이 회차는 «판정»이 아니라 §0-3 3번의 «탐색»이고, 그 탐색은 "
        "`WRC-D1`(사장님 확정 2026-09-02 · (가) 지금 연다)이 지시한 단계다.** "
        "§4-5 `WRC-O1` 이 탐색값을 판정 분모에서 «구조적으로» 분리하므로 계속 계산한다.")
    say("⇒ 🔴 **아래 모든 값은 「못 좁힌다」가 아니라 「이 표본에선 못 쟀다」쪽 문장을 뒷받침한다**"
        "(§7-C 4번: *「둘은 다른 문장이다」*). post6 판정 분모에서 이 값이 1/3 이상이면 "
        "**그때는 정말로 나머지를 돌리지 않는다.**")

    # ── §2. 건별 A0 / A1 / A3 + B1 ─────────────────────────────────────────
    say()
    say("---\n")
    say("## §2. 건별 `WRC-A0` · `A1` · `A3` 와 `WRC-B1`(축소율) — 🔬 탐색 표기\n")
    say("`m(·)` = feasible `P` 집합의 **측도(원)**. 🔑 *「범위」가 아니라 「측도」로 잰다* "
        "(`RESULTS_RECONSTRUCT_POST5.md` §1 B4 정정 승계).\n")

    for c in gate_in:
        c["a1"] = c["a3"] = c["a3b"] = c["bands"] = None
        if not c["ctx"] or not c["a0"]:
            continue
        N = c["fill_n"]
        c["a1"] = a1_solve(c["ctx"], N, c["a0"], cross=True)
        c["a3"] = a3_set(c["ctx"], c["a0"])
        c["a3b"] = a3_bands(c["ctx"], N)
        c["bands"] = bands_from_ext(c["a1"]["ext"], c["ctx"]) if (c["a1"] and c["a1"]["ext"]) else None

    say("| 글 | 종목 | `N` | 레그 | 창 봉수(등록일 «포함») | `G_win` | "
        "**`m(A0)`** | **`m(A1)`** | **`m(A3)`** | **`A1` 성립?** | `A1` 해 개수 | "
        "**`WRC-B1` 축소율(A1)** | 축소율(A3) |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    b1_bad = []
    a1_killed = []
    for c in gate_in:
        if not c["ctx"]:
            say(f"| {c['post']} | {c['name']} | {c['fill_n']} | {len(c['legs'])} | ⛔ **DB 부재** | — | "
                "— | — | — | ⛔ | — | ⛔ | ⛔ |")
            continue
        ctx = c["ctx"]
        if not c["a0"]:
            say(f"| {c['post']} | {c['name']} | {c['fill_n']} | {len(c['legs'])} | "
                f"{ctx['nbar_inc']} | {len(ctx['U'])} | **0.00** | **0.00** | **0.00** | "
                "⛔ (`A0` 가 ∅) | 0 | ⛔ **정의 불가**(`m(A0)=0`) | ⛔ |")
            continue
        m0 = iv_measure(c["a0"])
        m3 = iv_measure(c["a3"])
        m1 = 0.0                     # 🔴 아래 「측도 0」 절 참조 — 유한집합이라 «정확히» 0이다.
        r1 = 1 - m1 / m0
        r3 = 1 - m3 / m0
        if r1 < -1e-12 or r3 < -1e-12:
            b1_bad.append(c["name"])
        ok1 = bool(c["a1"] and c["a1"]["feasible"])
        if not ok1:
            a1_killed.append(c["name"] + f"({c['post']})")
        say(f"| {c['post']} | {c['name']} | {c['fill_n']} | {len(c['legs'])} | {ctx['nbar_inc']} | "
            f"{len(ctx['U'])} | **{m0:,.2f}원** | **{m1:,.2f}원** | **{m3:,.2f}원** | "
            f"{'🟢 성립' if ok1 else '🔴 **∅**'} | {c['a1']['n_means'] if c['a1'] else 0} | "
            f"**{r1:.4f}** | {r3:.4f} |")
    say()
    say(f"- 🔴🔴 **`WRC-A1` 이 «실제로» 문다 — `A0` 는 있는데 `A1` 이 비는 건 {len(a1_killed)}건** "
        f"({', '.join(a1_killed) or '없음'}). "
        "***`A1` 의 `P` 는 격자값 `N` 개의 산술평균이라 «간격 `tick/N` 의 이산 후보»뿐이고, "
        "`A0` 의 feasible 집합은 성기게 흩어진 «좁은 조각»들이다*** ⇒ 조각과 후보가 «어긋나면» "
        "해가 통째로 사라진다. 문서 §2-5 는 「하단이 잘리는가」만 물었는데, **실측에서 더 크게 "
        "무는 것은 하단이 아니라 «격자 정합»이었다.**")
    say(f"- ⇒ 🔬 **탐색 표본에서 `A1` 로 밴드를 낼 수 있는 건은 판정 분모 {len(gate_in)}건 중 "
        f"«{sum(1 for c in gate_in if c.get('bands'))}건»뿐이다**(§1 의 `WRC-G1` 6건에 더해 "
        f"{len(a1_killed)}건이 «모델 쪽»에서 더 빠진다). 이건 `WRC-G1` 의 분자가 «아니다» — "
        "G1 의 사유 ④ 는 «현행(`A0`) 해 0개»로 정의돼 있다(§4-6). "
        "🔑 ***그래서 이 손실은 커버리지 가드에 «안 잡힌다». 여기 따로 적어 둔다.***")
    say("- 🔴🔴 **`m(A1) = 0` 은 버그가 아니라 «정의의 귀결»이다** — `A1` 의 `P` 는 격자값 `N` 개의 "
        "**산술평균**이므로 feasible `P` 집합이 **유한 점집합**이다. 르베그 측도는 **정확히 0**이고 "
        "따라서 `WRC-B1` 축소율은 측정 가능한 전 건에서 **1.0000** 이다.")
    say("  ⇒ 🔑 ***`WRC-B1` 은 §4-4 가 예고한 대로 「지지」를 만들지 않는다. 여기서는 한 걸음 더 나가 "
        "「측도 잣대에서는 «항상 1» 이라 건 사이를 가르지도 못한다」가 실측으로 확인됐다.*** "
        "가르는 정보는 **`A1` 해 개수**와 **§3-1 의 밴드 폭**에 있다(§8 #1 에 등재).")
    say("- `m(A3)` 는 `A0` 를 `[min G_win, max G_win]` 으로 자른 것이다(§2-4 3번) — "
        "`_intersect` 를 import 해서 계산했다.")
    if b1_bad:
        say(f"- 🔴🔴 **`WRC-X1` 발동: 축소율 < 0 인 건 {b1_bad}** ⇒ 이 산출물은 **무효**다.")
    else:
        say("- ⚠️ **축소율이 음수인 건 0건 — 그런데 이걸 §2-4 의 «확증»으로 읽으면 안 된다.** "
            "`m(A1) ≡ 0` 이므로 축소율 `= 1 − 0/m(A0) ≡ 1` 은 **항등식**이고, "
            "***항등식은 어떤 가설도 시험하지 않는다*** (`m(A0) > 0` 이기만 하면 무조건 참이다). "
            "🔑 ***「위반이 안 나왔다」가 「정리가 확인됐다」가 되려면 위반이 «날 수 있는» 검사여야 한다.*** "
            "§2-4 를 실제로 시험한 것은 **§2-1 의 `WRC-X1` 1번·2번**(포함관계 · "
            "`A0 = ∅ ⇒ A1 = ∅`)이며, 그 둘은 거짓이 될 수 있는 검사다. "
            "`WRC-B1` 이 남기는 것은 «`m(A0) > 0` 인 건에서 계산이 돌았다»뿐이다.")

    # X1 #1·#2 계산 점검
    say()
    say("### 2-1. `WRC-X1` 구현 점검 (§4-7)\n")
    subs_ok = subs_n = 0
    plo_ok = plo_n = 0
    viol1 = []
    for c in gate_in:
        if not c["ctx"] or not c["a0"] or not c["a1"] or not c["a1"]["feasible"]:
            continue
        subs_n += 1
        ctx = c["ctx"]
        # ① 산술: [min G_win, max G_win] ⊆ [lo, hi] ⊂ [lo·0.7, hi]  (§2-4 3번)
        hull = (ctx["U"][0] >= ctx["lo"] and ctx["U"][-1] <= ctx["hi"])
        # ② 집합: A1 의 «실제» 최소·최대 평균이 A0 «집합»(범위 아님) 안에 드는가 — iv_has
        s_lo, s_hi = c["a1"]["srng"]
        p_lo = ctx["g"] * s_lo / c["fill_n"]
        p_hi = ctx["g"] * s_hi / c["fill_n"]
        inside = iv_has(c["a0"], p_lo) and iv_has(c["a0"], p_hi)
        if not (hull and inside):
            viol1.append(c["name"])
        subs_ok += int(hull and inside)
        # ③ `C-P` 하단 항등: leg_intervals(plo = lo·0.7) 로 조립한 것이 feasible_exact 와 같은가
        plo_n += 1
        same = feasible_plo(ctx["rows"], c["legs"], ctx["lo"] * 0.7) == c["a0"]
        # ④ A3 = A0 ∩ [min G_win, max G_win] 을 «다른 경로»(하단만 끌어올린 재계산)로 대조
        alt = _intersect(feasible_plo(ctx["rows"], c["legs"], ctx["U"][0]),
                         [(ctx["U"][0], ctx["U"][-1])])
        plo_ok += int(same and alt == c["a3"])
    say(f"1. `feasible(A1) ⊄ feasible(A0)` 인 건: **{len(viol1)}건** "
        f"({', '.join(viol1) or '없음'}) — 검사는 두 갈래다: "
        f"§2-4 3번의 산술(`[min G_win, max G_win] ⊆ [lo, hi] ⊂ [lo·0.7, hi]`)과 "
        f"`A1` 의 **실제 최소·최대 평균**을 `iv_has` 로 «집합»에 대고 확인한 것 "
        f"(«범위» 확인이 아니다 — B4 정정 승계) ⇒ **{subs_ok}/{subs_n}건 통과**.")
    say(f"   · 부수 점검: `leg_intervals`+`_merge`+`_intersect` 로 조립한 경로가 "
        f"`feasible_exact`(하단 `lo·0.7`)와 항등이고 `A3` 를 «다른 경로»로도 재현하는가 ⇒ "
        f"**{plo_ok}/{plo_n}건 일치**.")
    n_a0_zero = [c["name"] for c in gate_in if c["ctx"] and not c["a0"]]
    n_viol2 = [c["name"] for c in gate_in
               if c["ctx"] and not c["a0"] and c.get("a1") and c["a1"]["feasible"]]
    say(f"2. `feasible(A0) = ∅` 인데 `feasible(A1) ≠ ∅` 인 건: **{len(n_viol2)}건** "
        f"(해 0개 건 = {', '.join(n_a0_zero)}) ⇒ "
        f"{'🟢 정리 위반 없음' if not n_viol2 else '🔴 **무효**'}")
    cross = [(c["name"], c["a1"]["cross"]) for c in gate_in
             if c.get("a1") and c["a1"].get("cross") is not None]
    say(f"3. (대조군 상수 여부는 §4 에서 판정) · 4. `tick`/`grid_prices` 는 **import** 했다"
        f"(표 재작성 0건) · 5. `adj_factor` **산술 사용 0회** — 문자열은 **이 고지문과 docstring 에만** "
        f"등장한다(곱·나눗셈 어디에도 쓰이지 않는다).")
    say(f"- 🟢 **①(닫힌 형태) ↔ ②(비트셋 DP) 교차검증**: "
        f"**{sum(1 for _, v in cross if v)}/{len(cross)}건 일치** "
        f"({', '.join(n for n, v in cross if v) or '없음'}) — 두 경로가 같은 답을 낸다.")

    # ── §3. 밴드 bₖ ────────────────────────────────────────────────────────
    say()
    say("---\n")
    say("## §3. 차수별 밴드 `bₖ = 1 − Pₖ/H` — 🔬 **탐색 표기 · 판정 아님**\n")
    say("🔴 **`H` = 등록일 고가**(§2-1 (라) · `PREREG_HDR.md`:25 정의). "
        "`REC-Z3` 의무 인쇄 = **`H < 창 최고가` 여부**를 건별로 적는다.\n")

    # ── 3-0. REC-Z3 앵커 — 🔴 «판정 분모 전건»에 건다(밴드가 나온 건만이 아니다) ──────
    say("### 3-0. 🔴🔴 `REC-Z3` 앵커 의무 인쇄 — **판정 분모 «전건»** (밴드가 나온 건만이 아니다)\n")
    say("🔴 **초판의 결함 자기신고**: 이 표를 «밴드 계산 루프 안»에서만 찍어서 "
        "**`A1` 해가 나온 건(2건)만** 인쇄됐다. §2-1 (라)는 *「`H < 창 최고가` 여부를 **건별 의무 인쇄**」* "
        "이고 그 대상은 **판정 분모**다 — 해가 없어도 앵커는 정의된다. ⇒ 아래는 "
        "**DB 봉이 있는 분모 전건**이다.\n")
    say("| 글 | 종목 | `H`(등록일 고가) | 창 최저 저가 | 창 최고가 | **`H < 창 최고가`?** | "
        "`H`/창최고가 | `A1` 밴드 |")
    say("|---|---|---|---|---|---|---|---|")
    z3_all, z3_ctx = [], []
    for c in gate_in:
        if not c["ctx"]:
            say(f"| {c['post']} | {c['name']} | ⛔ **DB 부재** | ⛔ | ⛔ | ⛔ **측정 불가** | — | ⛔ |")
            continue
        z3_ctx.append(c)
        bad = c["ctx"]["h0"] < c["win_hi"]
        if bad:
            z3_all.append(f"{c['name']}({c['post']})")
        say(f"| {c['post']} | {c['name']} | {c['ctx']['h0']:,.0f} | {c['win_lo']:,.0f} | "
            f"{c['win_hi']:,.0f} | {'🔴 **예**' if bad else '아니오'} | "
            f"{100*c['ctx']['h0']/c['win_hi']:.1f}% | "
            f"{'있음' if c.get('bands') else '없음(해 0개)'} |")
    say()
    say(f"- 🔴🔴 **실측 = {len(z3_all)}/{len(z3_ctx)} = {100*len(z3_all)/len(z3_ctx):.1f}%** "
        f"(분모 = **판정 분모 {len(gate_in)}건 중 DB 봉이 있는 {len(z3_ctx)}건** · "
        f"레메디는 종목코드 부재라 앵커 자체가 정의되지 않는다). "
        f"해당 건: {', '.join(z3_all) or '없음'}")
    say("- 🔴 **그런 건에서 `bₖ` 는 「등록일 고점 대비 낙폭」이라는 뜻을 잃는다** — "
        "`Pₖ > H` 가 가능해 **`bₖ` 가 음수로 나온다**(§3 표의 지투파워가 실제로 그렇다: "
        "1차 밴드가 통째로 음수).")
    say(f"- ⚠️🔴 **이 {100*len(z3_all)/len(z3_ctx):.1f}% 를 post5 동결 실측 «3/6 = 50.0%» 와 "
        "«직접» 비교하지 말 것** — 두 수는 **창이 다르다**. 이 실행의 창은 "
        f"`WRC-D7`(DB 스냅샷 최대일 = `{END}`)이라 post5 동결 창(`~2026-08-28`)보다 길고, "
        "***창이 길어지면 창 최고가는 «오르기만 하므로» 이 비율은 «구조적으로 커지는 방향»***이다"
        "(단조). ⇒ **잣대가 다른 두 수다.**")
    say("- 🟢 **그래서 지금 «멈추지» 않는다**: `REC-Z3` 의 의무 발생 조건은 "
        "*「**6번째 글에서** 한 건이라도 더 나오면 앵커 재설계 사전등록이 의무 발생」*이고, "
        "이 회차는 **post6 이 아니라 탐색**이다(§4-5 `WRC-O1`). "
        "⇒ **이 표는 판정이 아니며 §9 의 중단 방아쇠를 «당기지 않는다».**")
    say("- 🔴🔴 **그러나 «앵커 위험 관측»으로는 크게 적어 둔다** — 같은 창 규약(`WRC-D7`)을 post6 에 "
        "그대로 쓰면 창은 **더 길어지고**, 위 비율은 **더 오를 것이다.** "
        "***즉 이 축은 「앵커가 흔들린 표본」에서 밴드를 재게 될 공산이 크다.*** "
        "🔑 *`bₖ` 의 «뜻»이 흔들리는 건 폭이 넓은 것보다 나쁘다 — 넓은 폭은 무정보이고, "
        "뜻이 흔들린 값은 «틀린 정보»다.*")
    say()
    say("### 3-1. `bₖ` 밴드 원표 — **`WRC-A1` 해가 나온 건만** (🔬 탐색 표기)\n")
    say("⚠️ 이 표의 분모는 **§3-0 의 분모가 아니다** — 여기 있는 건 `A1` 이 해를 남긴 건뿐이고, "
        "그 배제는 §2 가 적은 대로 **무작위가 아니다**.\n")
    say("| 글 | 종목 | `N` | `H`(등록일 고가) | 창 최고가 | **`H < 창 최고가`?** | 차수 | "
        "`Pₖ` 범위 | **`bₖ` 밴드** | **폭(%p)** | 폭(호가 칸) |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    z3_bad = []
    band_cases = [c for c in gate_in if c.get("bands")]
    per_case_med = {}
    for c in gate_in:
        if not c.get("bands"):
            continue
        ctx = c["ctx"]
        anchor_bad = ctx["h0"] < c["win_hi"]
        if anchor_bad:
            z3_bad.append(c["name"])
        for k, b in enumerate(c["bands"], start=1):
            head_ = (f"| {c['post']} | {c['name']} | {c['fill_n']} | {ctx['h0']:,.0f} | "
                     f"{c['win_hi']:,.0f} | {'🔴 **예**' if anchor_bad else '아니오'} "
                     if k == 1 else "|  |  |  |  |  |  ")
            say(f"{head_}| {k}차 | {b['pmin']:,.0f}~{b['pmax']:,.0f} | "
                f"**{b['b_lo']:+.2f}% ~ {b['b_hi']:+.2f}%** | **{b['w']:.2f}%p** | {b['cells']:.1f}칸 |")
        ws = [b["w"] for b in c["bands"]]
        per_case_med[c["name"] + "/" + c["post"]] = med(ws)
    say()
    for ln in NOTATION_4:
        say(ln)
    say()
    say(f"- 🔴 **`REC-Z3` 앵커 — 이 표(밴드가 나온 {len(band_cases)}건) 안에서는 {len(z3_bad)}건** "
        f"({', '.join(z3_bad) or '없음'}) 이 `H < 창 최고가` 다. "
        f"🔴 **의무 인쇄의 «본»표는 §3-0**(판정 분모 전건 = {len(z3_all)}/{len(z3_ctx)}) — "
        "이 줄만 보면 **분모가 밴드 있는 건으로 좁아져** 앵커 위험이 작아 보인다.")
    say("- 🔴 post5 동결 실측 **3/6 = 50.0%** 는 문턱 1/2 에 «정확히» 걸쳐 있었고, "
        "*「6번째 글에서 한 건이라도 더 나오면 앵커 재설계 사전등록이 의무 발생하고 그러면 이 축도 "
        "함께 멈춘다」*(§9). 🔴 **창이 달라 직접 비교 불가**라는 고지는 §3-0 에 적었다.")
    say("- 폭을 **호가단위 배수(칸)로도** 인쇄했다 — `REC-Y2` 승계(§4-3).")
    say()
    say("### 3-2. 건별 중앙값과 `WRC-P1` 문턱 대조 (🔬 탐색 · 판정 아님)\n")
    say(f"통계량 = 건별 `N` 개 차수의 폭 **중앙값** · 문턱 **< {BAND_THR:.0f}%p**"
        f"(`RESULTS_RECONSTRUCT_POST4.md` §6 `REC-Y1` «차용» — "
        "🔴 그 값은 **평단 `b₁` 의 폭**을 재던 것이고 여기서는 **차수별 `bₖ`** 를 잰다).\n")
    say("| 글 | 종목 | 차수 수 | 중앙값 관용구 | **폭 중앙값** | 최소 폭 | 최대 폭 | < 3%p |")
    say("|---|---|---|---|---|---|---|---|")
    narrow_n = 0
    meas_n = 0
    for c in gate_in:
        if not c.get("bands"):
            continue
        ws = [b["w"] for b in c["bands"]]
        m = med(ws)
        meas_n += 1
        narrow_n += int(m < BAND_THR)
        say(f"| {c['post']} | {c['name']} | {len(ws)} | {med_note(len(ws))} | **{m:.2f}%p** | "
            f"{min(ws):.2f}%p | {max(ws):.2f}%p | {'성립' if m < BAND_THR else '🔴 위반'} |")
    say()
    need = math.ceil((meas_n + 1) / 2) if meas_n else 0
    say(f"- 측정 가능 **{meas_n}건** 중 중앙값 < {BAND_THR:.0f}%p 인 건 **{narrow_n}건** · "
        f"「과반」 = `⌈(n+1)/2⌉` = **{need}건**")
    say(f"- 🔬 **탐색 표기**: {'문턱을 넘는다' if narrow_n >= need else '문턱 미달'} — "
        "🔴 **이건 판정이 아니다.** `WRC-O1`(§4-5) 대로 탐색 성적은 판정 분모에 «넣지 않는다». "
        "판정은 post6 부터 누적한다.")
    allw = [b["w"] for c in gate_in if c.get("bands") for b in c["bands"]]
    minw = min(allw) if allw else None
    if minw is None:
        say("- 🔴 **죽은 가드 실측 점검(§7-B #14)**: 측정 가능한 밴드가 **0건**이라 "
            "3%p 의 달성 가능성 자체를 «못 쟀다». ⇒ 「못 좁힌다」가 아니라 「못 쟀다」다(§7-C 4번).")
    else:
        say(f"- 🔴 **죽은 가드 실측 점검(§7-B #14)**: 관측된 «전 건 전 차수» 폭의 최소 = "
            f"**{minw:.2f}%p** · 최대 = **{max(allw):.2f}%p** ⇒ "
            f"**3%p 는 이 탐색 표본에서 {'«달성 가능»하다' if minw < BAND_THR else '🔴 «달성되지 않았다»'}**"
            f" — {'가드는 살아 있다.' if minw < BAND_THR else '문언대로면 §4-1 의 «축 종료» 신호다. 🔴 그러나 이 회차는 «탐색»이고(§4-5 `WRC-O1`) 「축을 닫는다」는 «판정»이므로 여기서 선언하지 않는다 — **문턱을 3%p 에서 «올리는» 것은 어느 경우에도 금지**다.'}")
    say()
    say("### 3-3. `WRC-A3` 「무정보 상한」 (🔴 §2-6 `WRC-R4` — 지지로 인용 금지)\n")
    say("| 글 | 종목 | 차수 | `A3` `Pₖ` 상한구간 | `A3` 밴드 폭(%p) | (대조) `A1` 폭 | `A1`/`A3` |")
    say("|---|---|---|---|---|---|---|")
    for c in gate_in:
        if not c.get("bands") or not c.get("a3b"):
            continue
        H = c["ctx"]["h0"]
        for k, ((lo3, hi3), b) in enumerate(zip(c["a3b"], c["bands"]), start=1):
            w3 = 100 * (hi3 - lo3) / H
            say(f"| {c['post']} | {c['name'] if k == 1 else ''} | {k}차 | {lo3:,.0f}~{hi3:,.0f} | "
                f"{w3:.2f}%p | {b['w']:.2f}%p | **{b['w']/w3:.3f}** |")
    say()
    say("- 🔴 **이 열은 「무정보 상한」이다** — `A3` 는 가중치가 자유라 밴드가 사실상 격자 전체다. "
        "**`WRC-P1` 의 분자·분모에 넣지 않는다**(§2-6). 쓸모는 *「`A1` 이 얼마나 좁혔는가」의 «분모»*뿐이다.")
    say("- ⚠️ `A3` 상한은 **포함관계 방향의 상한**이다(실제 `A3` 밴드 ⊆ 이 구간). 근사가 아니라 "
        "**상한임을 명시**해 인쇄한다.")
    for ln in NOTATION_4:
        say(ln)

    # ── §4. 대조군 (WRC-A4 · N1 · N2) ──────────────────────────────────────
    say()
    say("---\n")
    say("## §4. `WRC-A4` 대조군 — `WRC-N1`(성립률) · `WRC-N2`(좁은 밴드 비율)\n")

    # 4-0. 의사티커 차분 (§7-B #18)
    cur.execute("SELECT DISTINCT stock_code FROM daily_prices WHERE stock_code !~ '^[0-9]' ORDER BY 1")
    nonnum = [r[0] for r in cur.fetchall()]
    final_pseudo = sorted(set(PSEUDO) | set(nonnum))
    say("### 4-0. 의사티커 제외 목록 «차분» 실측 (§7-B #18)\n")
    say("| 출처 | 개수 | 목록 |")
    say("|---|---|---|")
    say(f"| `run_selection.py:23` `PSEUDO`(**import 해서 씀**) | {len(PSEUDO)} | "
        f"{', '.join('`%s`' % p for p in PSEUDO)} |")
    say("| 프로젝트 메모리 서술 | **6종이라고 적혀 있다**(`KOSPI`·`KOSDAQ`·`KS11`·`KQ11` + 「등」) | "
        "🔴 나머지 2종의 이름이 적혀 있지 않다 |")
    say(f"| DB 실측(`daily_prices` 의 «숫자로 시작하지 않는» 종목코드 전수) | {len(nonnum)} | "
        f"{', '.join('`%s`' % p for p in nonnum)} |")
    say(f"| ⇒ **이 실행이 쓰는 최종 목록** | **{len(final_pseudo)}** | "
        f"{', '.join('`%s`' % p for p in final_pseudo)} |")
    say()
    say(f"- 🔴 **개수가 다르다**: 코드 {len(PSEUDO)} · 메모리 서술 **6** · DB 실측 {len(nonnum)}. "
        "⇒ ***메모리의 「6종」은 이 DB 에서 재현되지 않는다*** — `daily_prices` 에 숫자로 시작하지 "
        f"않는 종목코드는 **{len(nonnum)}개뿐**이다. §4-2 가 *「여기서 개수를 단정하지 않는다」*고 "
        "적은 그 자리가 이 표다.")
    say("- 최종 목록은 **코드 ∪ DB 실측**이며 그 결과 코드의 4종과 같다(추가 2종은 «존재하지 않는다»).")

    # 4-1. 유니버스 스냅샷 (§7-B #23)
    dates = sorted({c["reg"] for c in gate_in})
    universe = {}
    for d in dates:
        cur.execute("SELECT stock_code FROM daily_prices WHERE date=%s AND market_cap IS NOT NULL "
                    "AND market_cap > 0 AND close > 0 AND NOT (stock_code = ANY(%s)) ORDER BY 1",
                    (d, final_pseudo))
        universe[d] = [r[0] for r in cur.fetchall()]
    uni_sha = {d: sha_list(v) for d, v in universe.items()}
    say()
    say("### 4-1. 유니버스 스냅샷 (§7-B #23 · `PREREG_RANKING.md` §2-1 판정 유니버스 승계)\n")
    say("정의 = 등록일 `D` 에 **`market_cap > 0` ∧ `close > 0`** · 의사티커 제외.\n")
    say("| 등록일 | 종목수 | sha256(정렬 목록) 앞 16 |")
    say("|---|---|---|")
    for d in dates:
        say(f"| {d} | {len(universe[d]):,} | `{uni_sha[d][:16]}` |")
    say()
    say(f"- 🔴 **매일 돌리면 대조군 분포가 날마다 달라진다**(`PREREG_RANKING.md` §2-6 교훈 승계) "
        f"⇒ 위 목록 전체를 `wrc_explore/universe_snapshot.json` 에 박았다"
        f"(DB 스냅샷 `{END}` 기준).")

    # 4-2. 창 데이터 사전적재 (DB 왕복 0회로 만든다)
    t0 = time.time()
    cur.execute("SELECT stock_code, date, open, high, low, close FROM daily_prices "
                "WHERE date BETWEEN %s AND %s", (min(dates), END))
    byc: dict[str, list] = {}
    for sc, d, o, h, l, cl in cur.fetchall():
        byc.setdefault(sc, []).append((d, o, h, l, cl))
    for sc in byc:
        byc[sc].sort()
    t_load = time.time() - t0

    def ctx_for(code, d0):
        """🔴 **문맥은 캐시하지 않는다** — 27,000여 (종목, 창) 의 `G_win` 을 들고 있으면 수백 MB 다.
        아래 `EVAL_CACHE` 가 이미 «같은 입력의 재계산»을 막으므로 중복 계산은 사실상 없다."""
        rows = [r for r in byc.get(code, ()) if r[0] >= d0]
        return make_ctx(rows) if rows else None

    EVAL_CACHE: dict = {}
    nodata = [0]

    def evaluate(code, d0, legs, N, kind="gross"):
        """대조군 1건 = (성립 여부, 폭 중앙값).

        🔴 **캐시 키에 레그를 «정렬해 넣지 않는다».** 정렬해 넣으면 (나) 갈래(순서 셔플)가
        «캐시 때문에» 같은 값을 내고, 그러면 §4-5 의 「상수인가」 판정이 **측정이 아니라
        구현의 인공물**이 된다. 순서를 그대로 키에 넣어 **실제로 다시 계산**한다."""
        key = (code, d0, tuple(legs), N, kind)
        r = EVAL_CACHE.get(key)
        if r is not None:
            return r
        ctx = ctx_for(code, d0)
        if ctx is None:
            nodata[0] += 1
            r = (None, None, None)
        else:
            iv = feasible_exact(ctx["rows"], legs, kind)
            if not iv:
                r = (False, False, None)            # (A0 성립, A1 성립, 폭 중앙값)
            else:
                sol = a1_solve(ctx, N, iv)
                if not sol or not sol["feasible"] or not sol["ext"]:
                    r = (True, False, None)
                else:
                    bs = bands_from_ext(sol["ext"], ctx)
                    r = (True, True, med([b["w"] for b in bs]))
        EVAL_CACHE[key] = r
        return r

    rng = np.random.default_rng(SEED)
    ctrl_cases = [c for c in gate_in]           # 크기 정합 = 같은 날짜 집합 · 같은 건수
    say()
    say("### 4-2. 대조군 명세 (`WRC-R10` §4-2)\n")
    say("| 갈래 | 방법 | 크기 정합 | 자유도 |")
    say("|---|---|---|---|")
    say(f"| **(가) 무작위 종목** | 같은 등록일·같은 `N`·같은 레그 «값»을 그날 유니버스의 무작위 종목 "
        f"가격열에 건다 | 같은 날짜 집합 · 같은 건수(**{len(ctrl_cases)}건/회**) | `WRC-A1` 과 동일 |")
    say(f"| **(나) 셔플 레그** | 같은 종목·같은 창에 **레그 값 순서를 무작위 셔플** | 〃 | 〃 |")
    say()
    say(f"- 반복 **{NREP:,}회** · 시드 `{SEED}` (`numpy.random.default_rng`) · "
        f"레메디(코드 부재)는 (가)에서는 **날짜·`N`·레그만 쓰므로 포함**되고 (나)에서는 "
        "**같은 종목이 필요하므로 제외**된다 — 두 갈래의 분모를 따로 인쇄한다.")

    # (가) 무작위 종목
    t0 = time.time()
    ga_tot = ga_a0 = ga_feas = ga_narrow = 0
    ga_by_case = {}
    ga_varies, ga_codes = {}, {}
    for c in ctrl_cases:
        ga_by_case[c["name"] + "/" + c["post"]] = [0, 0, 0, 0]   # a0, a1, tot, narrow
        ga_varies[c["name"] + "/" + c["post"]] = set()
        ga_codes[c["name"] + "/" + c["post"]] = set()
    uni_arr = {d: np.array(universe[d]) for d in dates}
    for rep in range(NREP):
        for c in ctrl_cases:
            key = c["name"] + "/" + c["post"]
            arr = uni_arr[c["reg"]]
            code = str(arr[rng.integers(len(arr))])
            ok0, ok1, m = evaluate(code, c["reg"], c["legs"], c["fill_n"])
            ga_tot += 1
            ga_by_case[key][2] += 1
            # 🔴 «전 반복»에서 센다 — 앞 200회만 보면 희귀 성립(예: 8/20,000)을 놓쳐
            #    「상수다」를 잘못 적는다(`WRC-X1` 3번은 «전 반복» 문언이다).
            ga_varies[key].add((ok0, ok1, None if m is None else round(m, 6)))
            ga_codes[key].add(code)
            if ok0:
                ga_a0 += 1
                ga_by_case[key][0] += 1
            if ok1:
                ga_feas += 1
                ga_by_case[key][1] += 1
                if m is not None and m < BAND_THR:
                    ga_narrow += 1
                    ga_by_case[key][3] += 1
    ga_meas = ga_feas
    t_ga = time.time() - t0

    # (나) 셔플 레그
    t0 = time.time()
    gb_tot = gb_a0 = gb_feas = gb_narrow = 0
    gb_values, gb_perms = {}, {}
    gb_cases = [c for c in ctrl_cases if c["ctx"] is not None]
    for c in gb_cases:
        gb_values[c["name"] + "/" + c["post"]] = set()
        gb_perms[c["name"] + "/" + c["post"]] = set()
    for rep in range(NREP):
        for c in gb_cases:
            key = c["name"] + "/" + c["post"]
            perm = rng.permutation(len(c["legs"]))
            legs_s = [c["legs"][i] for i in perm]
            ok0, ok1, m = evaluate(c["code"], c["reg"], legs_s, c["fill_n"])
            gb_tot += 1
            gb_a0 += int(bool(ok0))
            gb_feas += int(bool(ok1))
            if ok1 and m is not None and m < BAND_THR:
                gb_narrow += 1
            gb_perms[key].add(tuple(legs_s))
            gb_values[key].add((bool(ok0), bool(ok1), None if m is None else round(m, 6)))
    t_gb = time.time() - t0

    obs_a0 = sum(1 for c in gate_in if c["ctx"] and c["a0"])
    obs_feas = sum(1 for c in gate_in if c.get("bands"))
    obs_tot = sum(1 for c in gate_in if c["ctx"])
    say()
    say("### 4-3. `WRC-N1` — feasible 성립률 (문턱 **≥ 50% ⇒ 「판별력 없음」 강등**)\n")
    say("🔴 **두 열로 나눠 인쇄한다** — `WRC-A4` 는 *「`A1` 과 «같은» 모델을 무작위에 건다」* 이므로 "
        "**`WRC-N1` 의 통계량은 `A1` 성립률**이다. `A0` 성립률은 «그 앞 단계»라 참고로 함께 적는다 "
        "(둘을 한 칸에 섞으면 「모델이 좁혔다」와 「창이 넓다」가 다시 붙는다).\n")
    say("| 갈래 | 분모(건·회) | `A0` 성립 | `A0` 성립률 | **`A1` 성립(=`WRC-N1`)** | "
        "**성립률** | 문턱 50% |")
    say("|---|---|---|---|---|---|---|")
    say(f"| **(가) 무작위 종목** | {ga_tot:,} | {ga_a0:,} | {100*ga_a0/ga_tot:.1f}% | "
        f"{ga_feas:,} | **{100*ga_feas/ga_tot:.1f}%** | "
        f"{'🔴 **발동 — 강등**' if ga_feas/ga_tot >= N_THR else '🟢 미발동'} |")
    say(f"| **(나) 셔플 레그** | {gb_tot:,} | {gb_a0:,} | {100*gb_a0/gb_tot:.1f}% | "
        f"{gb_feas:,} | **{100*gb_feas/gb_tot:.1f}%** | "
        f"⛔ **무정보 — 판별력 검정이 아니다**(§4-5) |")
    say(f"| (참고) 관측 — 같은 잣대 | {obs_tot} | {obs_a0} | {100*obs_a0/obs_tot:.1f}% | "
        f"{obs_feas} | **{100*obs_feas/obs_tot:.1f}%** | — |")
    say()
    say("| 글/종목 | 대조군 (가) `A0` 성립률 | 대조군 (가) **`A1` 성립률** | "
        "대조군 (가) 좁은밴드율 | 관측 `A0` | 관측 `A1` |")
    say("|---|---|---|---|---|---|")
    for c in ctrl_cases:
        key = c["name"] + "/" + c["post"]
        f0, f1, t_, nw = ga_by_case[key]
        o0 = "⛔ DB부재" if not c["ctx"] else ("성립" if c["a0"] else "🔴 해 0개")
        o1 = "⛔" if not c["ctx"] else ("성립" if c.get("bands") else "🔴 해 0개")
        say(f"| {c['post']} {c['name']} | {100*f0/t_:.2f}% ({f0:,}) | "
            f"**{100*f1/t_:.2f}%** ({f1:,}/{t_:,}) | "
            f"{('%.1f%%' % (100*nw/f1)) if f1 else '⛔ 분모 0'} | {o0} | {o1} |")
    say()
    say("### 4-4. `WRC-N2` — 대조군에서 `bₖ` 폭 중앙 < 3%p 인 비율 (문턱 ≥ 50% ⇒ 강등)\n")
    say("| 갈래 | 분모(=feasible 건) | 좁은 밴드 | **비율** | 문턱 50% |")
    say("|---|---|---|---|---|")
    say(f"| (가) 무작위 종목 | {ga_meas:,} | {ga_narrow:,} | "
        f"**{(100*ga_narrow/ga_meas if ga_meas else float('nan')):.1f}%** | "
        f"{'🔴 **발동 — 강등**' if ga_meas and ga_narrow/ga_meas >= N_THR else '🟢 미발동'} |")
    say(f"| (나) 셔플 레그 | {gb_feas:,} | {gb_narrow:,} | "
        f"**{(100*gb_narrow/gb_feas if gb_feas else float('nan')):.1f}%** | "
        f"⛔ **무정보 — 판별력 검정이 아니다**(§4-5) |")
    say(f"| (참고) 관측 | {meas_n} | {narrow_n} | "
        f"**{(100*narrow_n/meas_n if meas_n else float('nan')):.1f}%** | — |")
    say()
    say("- 🔴 **분모를 명시한다** — `WRC-N2` 의 분모는 **feasible 이 성립한 대조군 건**이다"
        "(밴드는 해가 있어야 정의된다). 전체 반복 대비 비율은 성립률을 이미 §4-3 이 인쇄했다.")

    # X1 #3 — 대조군이 상수인가
    varies_a = sum(1 for v in ga_varies.values() if len(v) > 1)
    const_b = [k for k, v in gb_values.items() if len(v) == 1]
    perm_seen = {k: len(v) for k, v in gb_perms.items()}      # 🔴 «순열» 다양성(결과가 아니라)
    say()
    say("### 4-5. 🔴🔴 `WRC-X1` 3번 — 「대조군이 전 반복에서 동일값을 내는가」\n")
    say("| 갈래 | 무작위화가 «실제로» 걸렸나 | 통계량이 갈리나 | 결과 |")
    say("|---|---|---|---|")
    const_a = [k for k, v in ga_varies.items() if len(v) == 1]
    say(f"| (가) 무작위 종목 | 건별 **{NREP:,}회 전부**에서 서로 다른 종목이 뽑힌다 "
        f"(추첨된 «서로 다른» 종목 {min(len(v) for v in ga_codes.values()):,}~"
        f"{max(len(v) for v in ga_codes.values()):,}가지) | "
        f"결과가 «갈리는» 건 **{varies_a}/{len(ga_varies)}** | 🟢 **상수 아님 — 가드 살아 있음** |")
    say(f"| (나) 셔플 레그 | 건별 서로 «다른» 순열 실측 "
        f"**{min(perm_seen.values())}~{max(perm_seen.values())}가지**(캐시 키에 순서를 넣어 "
        f"전부 실제로 재계산했다) | 결과가 갈리는 건 **{len(gb_values)-len(const_b)}/{len(gb_values)}** | "
        f"🔴🔴 **{'전건 상수' if len(const_b) == len(gb_values) else '일부만 상수'}"
        f"({len(const_b)}/{len(gb_values)}건)** |")
    say()
    const_detail = ", ".join(
        f"{k}(A0 {ga_by_case[k][0]:,}/{ga_by_case[k][2]:,} · A1 {ga_by_case[k][1]:,})"
        for k in sorted(const_a))
    say(f"- ⚠️ (가) 에서도 **결과가 상수인 건이 {len(const_a)}건** 있다 "
        f"({const_detail or '없음'}) — 🔴 그건 «무작위화 실패»가 아니라 "
        "***그 레그 열이 «어떤» 무작위 종목에서도 `A0` 조차 못 만든다***는 뜻이다"
        "(위 괄호의 실측 = 성립 0회).")
    say("  🔴 **초판 정정**: 이 문장을 앞선 판은 **첫 200회만 표집해** 판단했고, 그 표집 때문에 "
        f"**한켐/post5(`A1` {ga_by_case.get('한켐/post5', [0,0,0,0])[1]:,}/{NREP:,} = "
        f"{100*ga_by_case.get('한켐/post5', [0,1,1,0])[1]/NREP:.2f}%)** 처럼 "
        "***희귀하게만 성립하는 건이 「상수」로 잘못 분류***됐다. "
        "⇒ **지금은 «전 반복»에서 센다**(`WRC-X1` 3번의 문언도 「전 반복」이다). "
        "🔑 ***가드를 「표집해서」 확인하면, 드물게 발동하는 것과 결코 발동하지 않는 것이 같아 보인다.***")
    say("- **두 사건을 구별해 적는다** — 그래서 위 표에 「무작위화가 걸렸나」와 "
        "「통계량이 갈리나」를 **다른 열로** 두었다.")
    say()
    say("🔴🔴 **(나) 갈래는 «구현 실패»가 아니라 «모델의 성질»이다 — 이건 이 실행의 가장 큰 발견이다.**")
    say("- `feasible_exact` 는 레그별 구간의 **교집합**이다(`run_reconstruct_post5.py:133-137`). "
        "교집합은 **순서에 불변**이다.")
    say("- `WRC-A1` 의 (가)(나)(다)(라)는 «매수» 사다리 `P₁>…>P_N` 에 걸리고 **레그 순서를 참조하지 않는다.**")
    say("- ⇒ ***레그 값 «순서»를 셔플해도 `A0`·`A1` 의 답은 «항등적으로» 같다.*** "
        "§4-2 (나)가 괄호로 적은 *「(단조성 파괴)」* 는 **이 모델이 쓰지 않는 성질**이다.")
    say("- 🔴 **문언 그대로 읽으면 `WRC-X1` 3번의 「전 반복에서 동일값」에 (나) 갈래가 «해당»한다** ⇒ "
        "그 조항대로면 이 회차 산출물은 **무효**다. "
        "🔑 그러나 조항의 취지는 *「무작위화가 «안 걸렸다»(구현 결함)」* 이고, 여기서 확인된 것은 "
        "***「무작위화는 걸렸는데 통계량이 그 무작위화에 «불변»이다」*** 로 **다른 사건**이다"
        "(§4-1 의 *「달성 불가능한 가드였다」* 와 같은 계열).")
    say("- 🔴 **그래서 이 산출물은 두 사실을 «묶어» 인쇄하고 어느 쪽도 조용히 고르지 않는다**: "
        "① (가) 갈래는 살아 있고 판별력 질문에 답한다 · "
        "② (나) 갈래는 **이 모델에서 구조적으로 무정보**이며 «대조군의 자격이 없다». "
        "***판정 전에 사전등록 개정(또는 verifier 판단)이 필요한 항목으로 §7 에 올린다.***")
    say("- 🟢 **이 발견은 §0-2 와 «같은 형태»다** — 착수 지시가 「가중평균이 격자를 벗어난다」를 "
        "이미 반영된 완화로 오독했듯, (나) 갈래는 **모델이 쓰지 않는 성질(레그 순서)** 을 흔든다.")
    say()
    say("#### 🔴🔴 그래서 이 산출물의 «사용 조건»을 여기 못 박는다\n")
    say("| 읽기 | `WRC-X1` 3번을 어떻게 읽는가 | 이 산출물의 지위 |")
    say("|---|---|---|")
    say("| **엄격** | 「대조군 «갈래 하나»라도 전 반복 동일값이면 무효」 | 🔴 **이 회차 산출물 전체가 «무효»** "
        "— 값 인용 금지 |")
    say("| **관대** | 「대조군이 «무작위화를 못 받았으면»(구현 결함) 무효」 | 🟢 (가) 갈래가 무작위화를 "
        "받았으므로 **유효** · (나) 갈래만 «대조군 자격 없음»으로 폐기 |")
    say()
    say("🔴🔴 ***이 문서의 모든 값은 «관대한 읽기»에서만 인용 가능하다.*** "
        "이 문서는 두 읽기 중 어느 쪽도 «스스로» 고르지 않는다 — "
        "**선택은 사장님 결정(또는 verifier 판정) 사항**이며, 그 도장이 찍히기 «전»에는 "
        "**이 값들을 판정·인용의 근거로 쓰지 않는다.** "
        "🔑 *산출물이 자기 무효 조건을 스스로 해석해 넘어가면, 그 조항은 그때부터 장식이다.*")
    say("- 🟢 **어느 읽기든 바뀌지 않는 것**: (나) 갈래는 **다음 회차부터 대조군에서 빼거나 "
        "«다른 것을 흔드는» 갈래로 «사전등록을 고쳐» 다시 정의해야 한다.** "
        "🔴 **이 문서 안에서 슬며시 바꾸지 않는다**(§3 이 `A5`·`A6` 를 그렇게 미뤄 둔 것과 같은 처리).")

    # ── §4-6. WRC-O1 탐색↔판정 병기 ────────────────────────────────────────
    say()
    say("### 4-6. `WRC-O1` — 탐색과 판정을 «항상» 나란히 (§4-5)\n")
    say("§4-5 는 *「산출물의 모든 표에 **탐색(post4·post5)** 열과 **판정(post6~ 누적)** 열을 "
        "나란히 둔다」* 고 요구한다. 🔴 **이 회차의 판정 열은 «구조적으로» 비어 있다** — "
        "post6 은 이 실행 시점에 존재하지 않기 때문이다(§0-3 의 5번이 이 3번 «뒤»에 온다). "
        "⇒ 위·아래 모든 표의 판정 열은 **⬜ 미도래**이며, 그 사실을 여기 한 번에 못 박는다.\n")
    say("| 통계량 | 🔬 **탐색(post4·post5)** | **판정(post6~ 누적)** |")
    say("|---|---|---|")
    say(f"| `WRC-G1` 커버리지 | **{100*g1:.1f}%** (6/10 · 🔴 발동) | ⬜ 미도래 |")
    say(f"| `WRC-P1` 밴드 중앙 < 3%p | **{narrow_n}/{meas_n}** "
        f"({'문턱 미달' if narrow_n < need else '문턱 충족'}) | ⬜ 미도래 |")
    say(f"| `WRC-N1` 대조군 (가) 성립률 | **{100*ga_feas/ga_tot:.1f}%** "
        f"({'미발동' if ga_feas/ga_tot < N_THR else '발동'}) | ⬜ 미도래 |")
    say(f"| `WRC-N2` 대조군 (가) 좁은밴드율 | "
        f"**{(100*ga_narrow/ga_meas if ga_meas else float('nan')):.1f}%** "
        f"({'미발동' if ga_meas and ga_narrow/ga_meas < N_THR else '발동'}) | ⬜ 미도래 |")
    say("| `WRC-B1` 축소율 | **전건 1.0000**(측도 잣대) | ⬜ 미도래 |")
    say(f"| `WRC-X1` 위반 | **{len(viol1) + len(n_viol2)}건**(포함관계) · "
        f"**(나) 대조군 상수 = 문언상 해당**(§4-5) | ⬜ 미도래 |")
    say()
    say("- 🔴 **탐색 성적은 판정 분모에 «넣지 않는다»**(`PREREG_POST6.md` §2-1 ③ 문형 승계: "
        "*「소급값은 «탐색적 표기»로만 인쇄한다. 판정은 post6 부터 누적한다 … 누적 분모에 "
        "**넣지 않는다.**」*).")
    say("- 🔴 **괴리가 판정을 가르면** 그때 **「탐색 편향 의심」이라고 인쇄**하고 **어느 쪽도 지지로 "
        "선언하지 않는다.** 이 회차는 판정 열이 비어 있어 괴리 자체를 «아직» 잴 수 없다.")

    # ── §5. 민감도 4축 (WRC-V1) ────────────────────────────────────────────
    say()
    say("---\n")
    say("## §5. `WRC-V1` — 민감도 **4축을 «항상» 나란히** (갈리면 어느 쪽도 선언 금지)\n")

    # 축 2: net
    for c in gate_in:
        c["a0_net"] = feasible_exact(c["ctx"]["rows"], c["legs"], "net") if c["ctx"] else None
        c["bands_net"] = None
        if c["ctx"] and c["a0_net"]:
            s = a1_solve(c["ctx"], c["fill_n"], c["a0_net"])
            if s and s["ext"]:
                c["bands_net"] = bands_from_ext(s["ext"], c["ctx"])
    net_zero = [c["name"] for c in gate_in if c["ctx"] and not c["a0_net"]]
    gross_zero = [c["name"] for c in gate_in if c["ctx"] and not c["a0"]]
    net_meas = [c for c in gate_in if c.get("bands_net")]
    net_narrow = sum(1 for c in net_meas if med([b["w"] for b in c["bands_net"]]) < BAND_THR)

    # 축 1: 잔차 문턱 — 해 0개 건의 진단
    say("### 5-1. 축① 잔차 문턱 `0.022%p`(판정) ↔ `0.020%p`(의무 민감도) — `REC-Z5`\n")
    say("| 글 | 종목 | 최소잔차 적합 `P` | **최대 오차** | 진단 @0.020 | 진단 @0.022 | 갈리나 |")
    say("|---|---|---|---|---|---|---|")
    thr_split = []
    for c in gate_in:
        if not c["ctx"] or c["a0"]:
            continue
        mr = min_residual(c["ctx"]["rows"], c["legs"], gross_ret)
        d = []
        for t in THR:
            d.append("🔴 적합 실패" if mr is None else
                     ("반올림으로 설명 가능" if mr[0] < t else "🔴 **모델이 틀렸다**"))
        if mr is not None and d[0] != d[1]:
            thr_split.append(c["name"])
        say(f"| {c['post']} | {c['name']} | {'—' if mr is None else f'{mr[1]:,.0f}'} | "
            f"{'—' if mr is None else f'**{mr[0]:.6f}%p**'} | {d[0]} | {d[1]} | "
            f"{'🔴 **예**' if mr is not None and d[0] != d[1] else '아니오'} |")
    say()
    say(f"- 두 문턱에서 분류가 갈리는 건 **{len(thr_split)}건** ({', '.join(thr_split) or '없음'})")
    say("- 🔴 **이 축은 `WRC-` 통계량을 «움직이지 않는다»** — `WRC-G1`(①+④)·`WRC-B1`·밴드 폭은 "
        "잔차 문턱을 **입력으로 쓰지 않는다**(해 0개 여부는 정확 구간법이 정한다). "
        "⇒ 이 축의 갈림은 **「해 0개의 «해석»」에만** 걸린다. 그 사실을 여기 적어 둔다.")

    say()
    say("### 5-2. 축② 수수료 `gross`(판정) ↔ `net`(민감도) — `REC-Y4` 승계\n")
    say("| 잣대 | 해 0개 | 측정 가능 | 폭 중앙 < 3%p 인 건 |")
    say("|---|---|---|---|")
    say(f"| **`gross`(판정)** | {len(gross_zero)}/{obs_tot} ({', '.join(gross_zero) or '없음'}) | "
        f"{meas_n} | {narrow_n} |")
    say(f"| `net`(민감도) | {len(net_zero)}/{obs_tot} ({', '.join(net_zero) or '없음'}) | "
        f"{len(net_meas)} | {net_narrow} |")
    say()
    say(f"- **`A0` 해 0개 집합**: gross ↔ net 이 "
        f"**{'같다' if set(net_zero) == set(gross_zero) else '🔴 다르다'}** "
        "— `REC-Y4` 는 정확법에서 gross·net 둘 다 4/6 이었다(승계).")
    say(f"- 🔴🔴 **그런데 «측정 가능 분모»가 움직인다: {meas_n} → {len(net_meas)}건** "
        f"(`A1` 이 net 에서 한 건 더 지운다). "
        f"***이건 위 열에 이미 보이는 값이고, 「갈리지 않았다」로 뭉뚱그리면 안 된다.***")
    say(f"- 🟢 **그래도 `WRC-P1` 쪽 «판정»은 두 잣대에서 같다** — "
        f"gross **{narrow_n}/{meas_n}** · net **{net_narrow}/{len(net_meas)}** 로 "
        f"**둘 다 과반 미달**(각각 필요 {math.ceil((meas_n+1)/2)}건 · "
        f"{math.ceil((len(net_meas)+1)/2) if net_meas else 0}건). "
        "⇒ §4-8 의 문언(*「갈리면 어느 쪽도 선언하지 않는다」*) 기준으로 **이 축은 갈리지 않았다**. "
        "🔴 단 **분모가 움직였다는 사실은 위에 적었다** — 다음 회차에 분자가 0이 아니면 "
        "그 분모 이동이 판정을 가를 수 있다.")

    say()
    say("### 5-3. 축③ 재진입·미완결 **포함**(판정) ↔ **제외**(민감도) — §2-7 `WRC-R5`\n")
    reentry = [c for c in gate_in if c["post"] == "post5" and c["name"] == "한켐"]
    oe = [c for c in gate_in if c["open_ended"] == 1]
    say(f"- **재진입 2사이클**(A-9 · `구조차단` 플래그): **{len(reentry)}건** "
        f"({', '.join(c['post'] + ' ' + c['name'] for c in reentry) or '없음'})")
    say(f"- **미완결 `open_ended = 1`**: **{len(oe)}/{len(gate_in)}건** "
        f"({', '.join(c['name'] for c in oe)})")
    say()
    say("| 갈래 | 판정 분모 | `WRC-G1` | 측정 가능 | 폭 중앙 < 3%p |")
    say("|---|---|---|---|---|")

    def slice_stats(sub):
        n = len(sub)
        if n == 0:
            return "—", "—", "—", None
        a = sum(1 for c in sub if c["ctx"] is None)
        z = sum(1 for c in sub if c["ctx"] is not None and not c["a0"])
        mm = [c for c in sub if c.get("bands")]
        nn = sum(1 for c in mm if med([b["w"] for b in c["bands"]]) < BAND_THR)
        r = (a + z) / n
        verdict = "🔴 **발동**" if r >= G1_THR else "🟢 **미발동**"
        return f"{a+z}/{n} = {100*r:.1f}% · {verdict}", f"{len(mm)}", f"{nn}", r

    g1_slices = {}
    for lab, key, sub in [
            ("**포함(판정)**", "include", gate_in),
            ("제외 — `open_ended` 뺌", "no_oe", [c for c in gate_in if c["open_ended"] == 0]),
            ("제외 — 재진입 뺌", "no_re", [c for c in gate_in
                                     if not (c["post"] == "post5" and c["name"] == "한켐")]),
            ("제외 — 둘 다 뺌", "no_both", [c for c in gate_in if c["open_ended"] == 0
                                      and not (c["post"] == "post5" and c["name"] == "한켐")])]:
        g, m_, nn, r = slice_stats(sub)
        g1_slices[key] = r
        say(f"| {lab} | {len(sub)} | {g} | {m_} | {nn} |")
    say()
    flip = [k for k, r in g1_slices.items()
            if r is not None and (r >= G1_THR) != (g1_slices["include"] >= G1_THR)]
    say(f"- 🔴🔴 **이 축은 「분모 이동」이 아니라 «가드의 판정 자체»를 뒤집는다** — "
        f"`WRC-G1` 이 포함 갈래에서 **{100*g1_slices['include']:.1f}% (발동)** 인데 "
        f"「둘 다 뺌」에서는 **{100*g1_slices['no_both']:.1f}% "
        f"({'미발동' if g1_slices['no_both'] < G1_THR else '발동'})** 로 바뀐다 "
        f"(뒤집히는 갈래 **{len(flip)}개**: {', '.join(flip) or '없음'}).")
    say("- 🔴 **`WRC-G1` 은 이 축을 «닫는» 게이트다**(§6-2: *「`WRC-P1` 전체 — `WRC-G1` 이미 60.0% 로 "
        "발동 중」*). ⇒ ***민감도 갈래를 고르는 것이 곧 「축을 여는가 닫는가」를 고르는 것***이 된다. "
        "🔑 *「분모가 움직인다」로 적으면 이 사실이 안 보인다 — 움직이는 건 «결론»이다.*")
    _nb = [c for c in gate_in if c["open_ended"] == 0
           and not (c["post"] == "post5" and c["name"] == "한켐")]
    say(f"- 🔴 **그래서 §2-7 `WRC-R5` 의 동결 선택(«포함»이 판정 · 제외는 민감도)을 그대로 둔다.** "
        f"제외 갈래에서 `WRC-G1` 이 «미발동»으로 뒤집힌다고 해서 판정 갈래를 바꾸는 것은 금지다 — "
        f"그건 ***가드를 통과하는 부분집합을 «골라» 축을 여는 동작***이다. "
        f"🔴 게다가 그 갈래의 판정 분모는 **{len(_nb)}건**(§6-1 최소 3건은 넘지만) 이고 "
        f"**측정 가능은 {sum(1 for c in _nb if c.get('bands'))}건**이라, "
        f"열려도 「과반」을 물을 표본이 사실상 없다.")
    say("- 🔴 **`open_ended` 의 방향**: 제약이 실제보다 «적다» ⇒ feasible 을 **넓히는** 쪽이다. "
        "「해가 나왔다」의 증거력이 그만큼 약하다(`RESULTS_RECONSTRUCT_POST5.md` §10 승계).")
    say("- 🔴 **재진입 건(한켐 post5)은 「하나의 평단」 전제가 원리적으로 깨지는 «유일한» 형태**이고, "
        "이 건이 판정을 가르면 ⇒ ⛔ `WRC-V1`(§2-7). "
        "🟢 이번 표본에서 그 건은 **현행 해 0개**라 애초에 측정 가능 집합 «밖»이다.")

    say()
    say("### 5-4. 축④ 모델 `WRC-A1`(판정) ↔ `WRC-A3`(무정보 상한 대조) — §2-6\n")
    say("- §3-3 표가 그 병기다. `A3` 는 **지지로 인용 금지**이며 `WRC-P1` 의 분자·분모에 넣지 않는다.")
    say()
    say("### 5-5. 🔴 4축 종합 — 갈리면 «어느 쪽도 선언하지 않는다»\n")
    say("| 축 | 갈렸나 | 근거 |")
    say("|---|---|---|")
    say(f"| ① 잔차 문턱 | {'🔴 예' if thr_split else '아니오'} | §5-1 (단 `WRC-` 통계량엔 «입력이 아니다») |")
    say(f"| ② gross/net | {'🔴 예' if set(net_zero) != set(gross_zero) or net_narrow != narrow_n else '아니오'} | §5-2 |")
    say(f"| ③ 재진입·미완결 | 🔴 **예 — «가드 판정»이 뒤집힌다** | "
        f"`WRC-G1` 이 포함 갈래 **{100*g1_slices['include']:.1f}%(발동)** → 「둘 다 뺌」 "
        f"**{100*g1_slices['no_both']:.1f}%(미발동)**. ***「분모 이동」이 아니라 «축을 여는 결론»이 "
        f"움직인다***(§5-3) — `WRC-G1` 은 이 축을 닫는 게이트이므로 갈래 선택이 곧 개폐 선택이다. "
        f"🟢 단 `WRC-P1` 의 분자는 전 갈래에서 **0** 이라 P1 «자체»는 갈리지 않는다 |")
    say("| ④ 모델 A1/A3 | 🔴 **항상 갈린다**(설계) | `A3` 는 무정보 상한이라 «비교 대상이 아니다» |")
    say()
    say("🔴 **이 회차는 어차피 «판정»이 아니다**(§4-5 `WRC-O1`) — 위 표는 post6 판정 때 "
        "**같은 형식으로** 다시 찍기 위한 것이고, 그때 하나라도 갈리면 **어느 쪽도 선언하지 않는다**.")
    say("🔴 **`REC-Z5` 와의 차이 자기신고**(§4-8): `REC-Z5` 는 *「갈려도 0.022 로 «선다»」* 이고 "
        "`WRC-V1` 의 나머지 세 축은 *「갈리면 «안 선다»」* 다. **한 산출물 안에 두 처리가 공존한다.**")

    # ── §6. §2-5 재측정 (§7-B #17) ─────────────────────────────────────────
    say()
    say("---\n")
    say("## §6. §2-5 대조표 **한 스크립트 재측정** (§7-B #17)\n")
    say("🔴 문서 §2-5 는 *「두 문서의 표를 이어 붙인 대조」* 라고 자기신고했고 "
        "*「실행 시 한 스크립트에서 재측정하고 값이 다르면 이 표를 폐기하고 실측을 쓴다」* 고 적었다. "
        "**아래가 그 재측정이다.**\n")
    say("🔴 **세 열로 가른다** — `run_reconstruct_post4_exact.py` 가 세운 관용 그대로 "
        "(*「숫자가 문서마다 다르면 «원인 규명»이 먼저다 — 맞추지 말 것」*): "
        "**문서값** / **동결 창에서 재측정**(post4 `~2026-08-21` · post5 `~2026-08-28`) / "
        f"**이 실행의 창에서 재측정**(`~{END}`).\n")

    DOC25 = [   # (글, 종목, 코드, 등록일, 레그, 문서의 P 하단, 문서의 lo, 동결 창 종료일, 분모 안?)
        ("post4", "이노테크", "469610", "2026-08-13", [14.38, 13.93, 13.36, 13.36],
         15535.25, 15020, "2026-08-21", True),
        ("post4", "한켐", "457370", "2026-08-12", [11.97, 11.84, 5.95, 5.58],
         7975.32, 7460, "2026-08-21", True),
        ("post4", "지투파워", "388050", "2026-08-13", [6.75, 3.00, 0.37],
         8000.00, 8030, "2026-08-21", True),
        ("post4", "PS일렉트로닉스", "332570", "2026-08-13", [4.06, 0.40, -2.76],
         9811.18, 8530, "2026-08-21", True),
        ("post4", "코데즈컴바인", "047770", "2026-08-19", [10.54, 0.41],
         3306.35, 3320, "2026-08-21", False),
        ("post5", "코데즈컴바인", "047770", "2026-08-21", [7.82, 0.09],
         3102.25, 3075, "2026-08-28", False),
        ("post5", "삼양바이오팜", "0120G0", "2026-08-21", [11.50, 11.50],
         46903.73, 52300, "2026-08-28", False),
    ]
    obs_a0_in = sum(1 for c in gate_in if c["ctx"] and c["a0"])
    say("| 글 | 종목 | 분모 안? | 문서 `P` 하단 | 동결창 재측정 | 이 창 재측정 | "
        "문서 `lo` | 동결창 `lo` | 이 창 `lo` | 🔴 잘리나(이 창) |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    cut_in, cut_all = 0, 0
    doc_match = []
    remeasure = []
    for post, nm, code, d0, lgs, docP, docLo, dfz, indenom in DOC25:
        rec = dict(post=post, name=nm, code=code, reg=d0, doc_P=docP, doc_lo=docLo,
                   in_denom=indenom)
        vals = {}
        for tag, dend in (("frozen", dfz), ("now", END)):
            cur.execute("SELECT date, open, high, low, close FROM daily_prices WHERE stock_code=%s "
                        "AND date BETWEEN %s AND %s ORDER BY date", (code, d0, dend))
            rows = cur.fetchall()
            if not rows:
                vals[tag] = (None, None)
                continue
            iv = feasible_exact(rows, lgs, "gross")
            lo = min(r[3] for r in rows)
            vals[tag] = (iv_min(iv) if iv else None, lo)
        rec["frozen"] = vals["frozen"]
        rec["now"] = vals["now"]
        pf, lf = vals["frozen"]
        pn, ln = vals["now"]
        cut = (pn is not None and ln is not None and pn < ln)
        if cut:
            cut_all += 1
            if indenom:
                cut_in += 1
        okdoc = pf is not None and abs(pf - docP) < 0.01 and abs(lf - docLo) < 0.5
        doc_match.append(okdoc)
        rec["doc_reproduced_at_frozen_window"] = bool(okdoc)
        rec["cut_now"] = bool(cut)
        remeasure.append(rec)
        say(f"| {post} | {nm} | {'✅ 안' if indenom else '🔴 밖'} | {docP:,.2f} | "
            f"{'—' if pf is None else f'{pf:,.2f}'} | {'—' if pn is None else f'{pn:,.2f}'} | "
            f"{docLo:,.0f} | {'—' if lf is None else f'{lf:,.0f}'} | "
            f"{'—' if ln is None else f'{ln:,.0f}'} | {'🔴 **예**' if cut else '아니오'} |")
    say()
    say(f"- 🟢 **동결 창에서 문서값 재현**: **{sum(doc_match)}/{len(doc_match)}행 일치** "
        "⇒ §2-5 표는 «이어 붙인» 표였지만 **동결 창 기준으로는 틀리지 않았다**. "
        "다만 이 실행의 창은 더 길어서 값이 움직인다 — 그 이동은 «방법»이 아니라 «창» 때문이다.")
    say(f"- **이 창 기준 실측**: 잘리는 건 **{cut_all}/{len(DOC25)}**(해 있는 7건 대비 "
        f"{100*cut_all/len(DOC25):.1f}%) · 그중 **판정 분모 안은 {cut_in}건** ⇒ "
        f"🔴 **문서 §2-5 와 «같은 분모»**(= 판정 분모 안 «현행 해가 있는» 건 = `A0` 기준 {obs_a0_in}건) "
        f"대비 **{cut_in}/{obs_a0_in} = {100*cut_in/obs_a0_in:.1f}%**")
    say("  ⚠️ 분모를 `A1` 측정 가능(2건)으로 바꾸면 안 된다 — §2-5 는 **현행(`A0`) 해가 있는 건**을 "
        "분모로 쓴 표다(분모를 바꾸면 같은 이름의 «다른 비율»이 된다).")
    say("- 🔴 문서 §2-5 의 인용값은 **1/4 = 25.0%**(판정 분모 기준)였다 ⇒ "
        f"**{'일치' if cut_in == 1 and obs_a0_in == 4 else '🔴 이동했다 — «실측을 쓴다»(§7-B #17)'}**")
    say("- 🔴 **`fill_n = 1`(삼양바이오팜)의 「매수측 격자 `C1` 부활」은 판정에서 실현되지 않는다** — "
        "§6-1 게이트가 배제한다. **분모 «밖» 관찰로만 적고 축을 여는 근거로 쓰지 않는다**(§7-C 2번).")

    # 봉수 표기 (N8 · §7-B #19)
    say()
    say("### 6-1. 봉수 표기 정합 — 「등록일 «포함»/«직전»」 (§5-2 3번 · `N8` 승계)\n")
    say("🔴 **세 수를 «다른 이름으로» 적는다** — post5 §14 에서 「11봉」과 「12봉」이 같은 사실의 두 표기라 "
        "혼동됐던 그 자리다. ① `등록일 «직전» 봉수(DB 전 이력)` ② `창 봉수(등록일 «포함»)` "
        "③ `DB 최초 봉`.\n")
    say("| 글 | 종목 | 등록일 | ① 등록일 «직전» 봉수(DB 전 이력) | "
        "② **창 봉수(등록일 «포함»)** | ③ DB 최초 봉 | 창 종료 |")
    say("|---|---|---|---|---|---|---|")
    for c in gate_in:
        if not c["ctx"]:
            say(f"| {c['post']} | {c['name']} | {c['reg']} | ⛔ DB 부재 | ⛔ | ⛔ | — |")
            continue
        say(f"| {c['post']} | {c['name']} | {c['reg']} | {c['nbar_pre']:,} | "
            f"**{c['ctx']['nbar_inc']}** | {c['first_bar']} | {c['ctx']['dend']} |")
    say()
    say("- 🔑 *「직전」과 「포함」은 같은 사실의 두 표기다 — 앞으로는 반드시 붙인다*"
        "(`RESULTS_RECONSTRUCT_POST5.md` §10 `N8` 승계).")

    # ── §7. 점검표 ─────────────────────────────────────────────────────────
    wrc_files = subprocess.run(["git", "grep", "-l", "--untracked", "WRC-"], cwd=str(BASE),
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace").stdout.split()
    others = [f for f in wrc_files if "PREREG_WEIGHTED_RECON" not in f
              and "run_wrc_explore" not in f and "RESULTS_WRC_EXPLORE" not in f
              and "wrc_explore/" not in f and "regen_gate" not in f]
    say()
    say("---\n")
    say("## §7. §7-B 실행 점검표 #14 ~ #24 — 상태와 증거\n")
    say("| # | 점검 | 상태 | 증거 |")
    say("|---|---|---|---|")
    say(f"| 14 | 죽은 가드 실측 | {'✅' if allw else '⛔'} | "
        f"3%p 달성 가능성: 최소 폭 **{('%.2f%%p' % minw) if minw is not None else '측정 0건'}**(§3-2) · "
        f"대조군 상수 아님: (가) 🟢 {varies_a}/{len(ga_varies)} 갈림 / (나) 🔴 **전건 상수 ⇒ ⛔ 무정보 강등**(§4-5) · "
        f"🔴 **`WRC-B1` 은 이 칸의 증거가 «아니다»** — 축소율 `1 − 0/m(A0) ≡ 1` 은 **항등식**이라 "
        f"거짓이 될 수 없다(§2). 정리를 실제로 시험한 «거짓이 될 수 있는» 검사는 "
        f"**§2-1 의 `WRC-X1` 1번**(포함관계 위반 {len(viol1)}건) · **2번**(`A0=∅ ⇒ A1≠∅` 위반 "
        f"{len(n_viol2)}건)이고, 그 둘이 이 칸의 근거다 |")
    say(f"| 15 | 브랜치 `fix/tasso-post6-s5-fixes` · C-17~C-22 반영 | "
        f"{'✅' if branch == 'fix/tasso-post6-s5-fixes' and c22 and c17 and c19 else '🔴'} | "
        f"§0 표 · 브랜치 `{branch}` · `8d28e14` 조상 {'✅' if anc else '🔴'} "
        f"(🔴 HEAD 해시는 재현 게이트 때문에 본문에 적지 않는다 — §0) |")
    say(f"| 16 | `WRC-` grep 재확인 | {'✅' if not others else '🔴'} | "
        f"`git grep -l --untracked WRC-` 결과에서 **이 축의 파일**"
        f"(`PREREG_WEIGHTED_RECON.md`·`run_wrc_explore.py`·`RESULTS_WRC_EXPLORE.md`·"
        f"`wrc_explore/*`·`regen_gate.py` 등재줄)**을 뺀 나머지 = {len(others)}개** "
        f"({', '.join(sorted(others)) or '없음'}) — 🔴 전체 건수는 «실행 차수에 따라 달라지므로» "
        f"적지 않는다(산출물이 생기면 스스로 잡힌다 ⇒ 재현 게이트가 깨진다) |")
    say(f"| 17 | §2-5 한 스크립트 재측정 | ✅ | §6 세 열 대조 · 동결 창 재현 "
        f"{sum(doc_match)}/{len(doc_match)} |")
    say(f"| 18 | 의사티커 «차분» 실측 | ✅ | §4-0 — 코드 {len(PSEUDO)} · 메모리 서술 6 · "
        f"DB 실측 {len(nonnum)} ⇒ 최종 {len(final_pseudo)} |")
    say(f"| 19 | DB 스냅샷 최신 봉 · 봉수 「포함/직전」 | ✅ | §0 `{END}` · §6-1 표 |")
    say("| 20 | 라이브 채택 금지 + §5-4 4줄 | ✅ | 머리말 · §3-1 · §3-3 · `wrc_explore/bands.tsv` 머리 주석 (모든 `bₖ` 표) |")
    say(f"| 21 | `regen_gate.py` 등재 | {'✅ 등재' if registered else '🔴 미등재'} · "
        f"🔴 **부작용 있음 — 아래 §7-1** | "
        f"`PAIRS['RESULTS_WRC_EXPLORE.md'] = 'run_wrc_explore.py'` "
        f"{'존재' if registered else '**없다**'} · 매니페스트 기준선은 «아직» 미갱신 |")
    say("| 22 | 순서 증거(`FREEZE_WRC_*` ↔ `post_<logNo>.html`) | ⬜ **미도래** | "
        "§0-3 의 **4·5번 단계**에서 확인한다 — 이 실행은 **3번**이고 post6 은 «아직 없다». "
        "확인 명령: `git log --diff-filter=A -- post_<logNo>.html` |")
    say(f"| 23 | `WRC-A4` 유니버스 스냅샷 | ✅ | §4-1 표 + `wrc_explore/universe_snapshot.json` |")
    say(f"| 24 | `WRC-G1` 를 «먼저» 계산 | ✅ | §1 (이 문서의 첫 계산 절) · 합 **{100*g1:.1f}%** |")
    say()
    say("🔴 **#22 를 ✅ 로 적지 않는다** — 아직 일어나지 않은 일을 통과로 적으면 그게 죽은 가드다.")
    say()
    say("### 7-1. 🔴🔴 #21 의 «부작용» 신고 — 등재가 «명시된 테스트 하나»를 깨뜨린다\n")
    say("**이 산출물을 쓴 시점(= 매니페스트 갱신 «전») 기준으로 다음 테스트가 실패한다**:\n")
    say("> `tests/test_s5_fixes.py::test_c19_manifest_covers_every_pair`\n")
    say("- **왜**: 그 테스트의 단언은 `set(REGEN_MANIFEST.artifacts) == set(regen_gate.PAIRS)` 다. "
        "#21 이 요구한 등재가 `PAIRS` 에 **1건을 더했고** 매니페스트에는 그 항목이 «아직» 없다 "
        "⇒ 두 집합이 **정확히 그 1건만큼** 어긋난다(`Extra items in the right set: "
        "'RESULTS_WRC_EXPLORE.md'`). `regen_gate.py` 의 `check()` 도 같은 사유로 "
        "`매니페스트에 없음` 을 낸다.")
    say("- 🔴 **여기서 `--update` 로 고치지 않는다.** `--update` 는 «재생성한 뒤» 사람이 돌리는 "
        "명령이고, 그 한 번이 **쌓여 있던 「낡았다」 신호(DB 지문 이동 포함)를 전부 흡수**한다"
        "(`regen_gate.py` `build()` 주석). 그건 §0-3 **4번(동결 커밋)**의 동작이지 3번(이 실행)의 "
        "동작이 아니다.")
    say("- 🟢 **고치는 순서(동결 단계에서 이대로)**:")
    say("  1. HEAD 해시를 산출물에서 뺀다(§0 — **이 판에서 이미 반영**). "
        "안 그러면 동결 커밋 «직후» `--rerun` 이 구조적으로 깨진다.")
    say("  2. §0-3 4번에서 `python regen_gate.py --update` 를 돌려 기준선을 박는다.")
    say("  3. `python -m pytest tests/test_s5_fixes.py -q` 를 다시 돌려 **green 을 "
        "`FREEZE_WRC_<날짜>.md` 에 기록**한다.")
    say("- 🔑 ***「등재했다」가 「게이트가 통과한다」를 뜻하지 않는다*** — 등재는 «가드를 켜는» 동작이고, "
        "켜는 순간 기준선이 없으면 가드는 «실패»로 운다. 그 울음을 «지금» 지우지 않고 "
        "**여기 적어 두는 것**이 이 계열의 규약이다.")

    # ── §8. 발견 ───────────────────────────────────────────────────────────
    say()
    say("---\n")
    say("## §8. 이 실행에서 «놀란» 것 (판정 변경 없음 · 기록)\n")
    say(f"0. 🔴🔴 **`WRC-A1` 이 «해를 지운다» — `A0` 는 있는데 `A1` 이 비는 건 {len(a1_killed)}건** "
        f"({', '.join(a1_killed) or '없음'}). §2-4 정리는 *「좁아지기만 한다」* 였고 §2-5 는 "
        "*「하단 절단」* 을 예고했는데, **실측에서 무는 것은 하단이 아니라 «격자 정합»**이었다: "
        "`A1` 의 후보 평균은 간격 `tick/N` 의 이산점이고 `A0` 는 성긴 좁은 조각이라 "
        "**둘이 어긋나면 통째로 사라진다.** "
        "🔑 ***「제약을 추가하면 좁아진다」와 「그 제약이 어디를 무는가」는 다른 질문이다.*** "
        "그리고 이 손실은 `WRC-G1`(사유 ④ = «현행» 해 0개)에 **잡히지 않는다** — "
        "커버리지 가드가 모델 쪽 손실을 못 본다.")
    say("1. 🔴🔴 **`WRC-B1` 은 측도 잣대에서 «항상 1» 이다.** `A1` 의 `P` 집합은 격자값 `N` 개의 "
        "산술평균이라 **유한 점집합**이고 르베그 측도가 정확히 0이다. 문서 §4-4 는 "
        "*「축소율 < 0 이면 구현 결함」* 만 예고했는데, 실측은 한 걸음 더 나가 "
        "***「이 통계량은 건 사이를 «가르지도» 못한다」*** 였다. "
        "🔑 ***측도로 정의한 축소율은 「연속 → 이산」 변화를 재는 데 쓸 수 없다.*** "
        "가르는 정보는 **`A1` 해 개수**와 **밴드 폭**이다.")
    say("2. 🔴🔴 **대조군 (나)(셔플 레그)는 이 모델에서 «구조적으로 무정보»다** — §4-5. "
        "`feasible_exact` 가 레그 «교집합»이라 순서에 불변이고, `A1` 의 제약은 매수 사다리에만 걸린다. "
        "🔑 ***대조군을 설계할 때 「무엇을 흔드는가」가 「모델이 무엇을 읽는가」와 맞물리는지 "
        "먼저 확인해야 한다.*** (§0-2 가 지시의 전제를 깬 것과 «같은 형태»의 결함이다.)")
    n_ctx = [c for c in gate_in if c["ctx"]]
    n_contig = sum(1 for c in n_ctx if c["ctx"]["contiguous"])
    say(f"3. 🟢 **`G_win` 이 «연속»이었다 — 판정 분모 {n_contig}/{len(n_ctx)}건**(실측). "
        "창 안 격자가 빈틈없이 이어져(봉 구간 합집합에 틈 0) 조합 열거"
        f"(최대 `C({max(len(c['ctx']['U']) for c in n_ctx)},5)` ≈ 1.9e12)를 "
        "**닫힌 형태 `O(V·N)`** 로 «정확히» 대체할 수 있었다. 대조군에는 연속이 아닌 종목이 있어 "
        "**비트셋 부분합 DP**로 풀었고 두 경로를 교차검증했다(§2-1).")
    hi_lo = "높다" if ga_feas / ga_tot > obs_feas / obs_tot else "낮다"
    say(f"4. 🟡 **`WRC-N1` 은 «발동하지 않았다»** — (가) 대조군 `A1` 성립률 {100*ga_feas/ga_tot:.1f}% 로 "
        f"문턱 50% 아래이고, 관측 {100*obs_feas/obs_tot:.1f}% 보다 **{hi_lo}**. "
        "문서 §4-2 는 *「이 가드는 «발동할» 가능성이 상당하다」* 고 미리 신고했는데 "
        "**실측에선 발동하지 않았다** — 원인은 §8 #0 과 같다: "
        "***`A1` 의 격자 정합 제약이 «무작위 종목에서도» 해를 대량으로 지운다.*** "
        f"🔴 **그렇다고 「판별력이 있다」가 되지 않는다** — 관측 쪽 분모가 **{obs_tot}건(성립 "
        f"{obs_feas}건)**이라 비율의 불확실성이 지배적이고, 이 회차는 «판정»이 아니다(§4-5).")
    say("5. 🟡 **창이 길어지면 값이 움직인다** — 같은 방법·같은 레그인데 `~2026-08-21`(post4 동결창) 과 "
        f"`~{END}` 사이에서 `P` 하단·`lo` 가 이동했다(§6). ⇒ ***창 종료일을 「실행 시 스냅샷」으로 "
        "동결한 `WRC-D7` 은 「매 실행마다 값이 달라진다」를 «의미»한다.*** 그래서 §0 에 최신 봉을 박는다.")

    say()
    say("---\n")
    say(f"결정성: 시드 `{SEED}` 고정 · DB 는 SELECT 만 ⇒ **같은 DB 스냅샷에서 재실행하면 "
        f"byte 단위로 같다**(`regen_gate.py --rerun` 전제). "
        f"🔴 그래서 이 파일에는 **실행 시간을 적지 않는다** — 벽시계 값은 stdout 에만 낸다. "
        f"(스냅샷이 움직이면 값이 움직인다 — §0 의 최신 봉이 그 지문이다.)")
    say(f"평가 캐시 **{len(EVAL_CACHE):,}건** = 대조군에서 실제로 «다른» 계산의 수 "
        f"(반복 {NREP:,}회 × 건수는 그 위의 조회다) · 창 데이터 없는 추첨 **{nodata[0]:,}건**")
    print(f"\n[시간] 총 {time.time() - t_start:.1f}초 · 적재 {t_load:.1f}초 · "
          f"대조군 (가) {t_ga:.1f}초 · (나) {t_gb:.1f}초")
    print(f"[git] 브랜치 {branch} · HEAD {head} · `8d28e14` 조상 {anc}  "
          f"— 🔴 해시는 stdout 전용(본문에 박으면 --rerun 이 구조적으로 깨진다)")
    try:    # §7-1 의 «살아 있는» 수 — 매니페스트 상태에 따라 변하므로 본문에는 안 적는다
        _man = json.loads((BASE / "REGEN_MANIFEST.json").read_text(encoding="utf-8"))
        _pairs = len([1 for ln in gate_src.splitlines()
                      if ln.strip().startswith('"') and '.md": "' in ln])
        print(f"[게이트] regen_gate.PAIRS {_pairs}건 ↔ REGEN_MANIFEST.artifacts "
              f"{len(_man['artifacts'])}건 · 차이 {_pairs - len(_man['artifacts'])}건 "
              f"(= 이 축 등재분) ⇒ test_c19_manifest_covers_every_pair 는 동결 단계의 "
              f"`--update` 전까지 실패한다(§7-1)")
    except Exception as e:  # noqa: BLE001
        print(f"[게이트] 매니페스트 대조 실패: {type(e).__name__}")
    say()
    say("[[PREREG_WEIGHTED_RECON]] · [[PREREG_POST6]] · [[PREREG_RANKING]] · "
        "[[RESULTS_RECONSTRUCT_POST4]] · [[RESULTS_RECONSTRUCT_POST5]]")

    # ── 기계 산출물 ────────────────────────────────────────────────────────
    (ART / "universe_snapshot.json").write_text(json.dumps(
        {"db_snapshot_max_date": END, "pseudo_from_code": list(PSEUDO),
         "pseudo_nonnumeric_in_db": nonnum, "pseudo_final": final_pseudo,
         "universe": universe, "sha256": uni_sha}, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in gate_in:
        rec = {k: c[k] for k in ("post", "log_no", "item", "name", "code", "reg", "prec",
                                 "fill_level", "fill_n", "legs", "n_legs", "distinct",
                                 "open_ended", "prog_ver", "gate")}
        rec["window_end"] = END
        if c["ctx"]:
            rec["window"] = dict(lo=c["ctx"]["lo"], hi=c["ctx"]["hi"], h0=c["ctx"]["h0"],
                                 l0=c["ctx"]["l0"], o0=c["ctx"]["o0"], c0=c["ctx"]["c0"],
                                 bars_incl=c["ctx"]["nbar_inc"], bars_before=c["nbar_pre"],
                                 g_win=len(c["ctx"]["U"]), g_unit=c["ctx"]["g"],
                                 contiguous=c["ctx"]["contiguous"],
                                 win_low=c["win_lo"], win_high=c["win_hi"],
                                 anchor_below_window_high=bool(c["ctx"]["h0"] < c["win_hi"]))
            rec["A0"] = dict(n_intervals=len(c["a0"] or []),
                             measure=iv_measure(c["a0"]) if c["a0"] else 0.0,
                             pmin=iv_min(c["a0"]) if c["a0"] else None,
                             pmax=iv_max(c["a0"]) if c["a0"] else None)
            if c.get("a1"):
                rec["A1"] = dict(feasible=c["a1"]["feasible"], n_means=c["a1"]["n_means"],
                                 measure=0.0, path=c["a1"]["path"], cross_ok=c["a1"]["cross"])
            if c.get("a3"):
                rec["A3"] = dict(n_intervals=len(c["a3"]), measure=iv_measure(c["a3"]))
            if c.get("bands"):
                rec["bands"] = [dict(k=i + 1, **{kk: b[kk] for kk in
                                                 ("pmin", "pmax", "b_lo", "b_hi", "w", "cells", "tick")})
                                for i, b in enumerate(c["bands"])]
                rec["band_median_w"] = med([b["w"] for b in c["bands"]])
        else:
            rec["A0"] = None
            rec["reason"] = "DB 종목코드 부재 (WRC-G1 사유 ①)"
        rec["_notation"] = NOTATION_4
        (ART / f"case_{c['post']}_{c['item']}_{c['name']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "controls_summary.json").write_text(json.dumps({
        "seed": SEED, "nrep": NREP, "note_nrep": "run_selection.py:22 는 NREP=2000",
        "db_snapshot_max_date": END,
        "branch_a_random_stock": {"trials": ga_tot, "a0_feasible": ga_a0,
                                  "a1_feasible": ga_feas, "N1_rate": ga_feas / ga_tot,
                                  "band_denominator": ga_meas, "narrow": ga_narrow,
                                  "N2_rate": (ga_narrow / ga_meas) if ga_meas else None,
                                  "per_case": {k: dict(a0=v[0], a1=v[1], trials=v[2], narrow=v[3])
                                               for k, v in ga_by_case.items()}},
        "branch_b_shuffled_legs": {"trials": gb_tot, "a0_feasible": gb_a0,
                                   "a1_feasible": gb_feas, "N1_rate": gb_feas / gb_tot,
                                   "narrow": gb_narrow,
                                   "distinct_permutations_per_case": perm_seen,
                                   "constant_across_reps": len(const_b) == len(gb_values),
                                   "why_constant": "feasible_exact 는 레그 교집합이라 순서 불변 · "
                                                   "A1 제약은 매수 사다리에만 걸린다 ⇒ 통계량이 "
                                                   "셔플에 불변(WRC-X1 3번 문언 해당 · §4-5)"},
        "observed": {"cases": obs_tot, "a0_feasible": obs_a0, "a1_feasible": obs_feas,
                     "band_measurable": meas_n, "narrow": narrow_n},
        "thresholds": {"N1": N_THR, "N2": N_THR, "band_pp": BAND_THR, "G1": G1_THR},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (ART / "remeasure_2_5.json").write_text(json.dumps(remeasure, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    with (ART / "bands.tsv").open("w", encoding="utf-8") as f:
        # 🔴 `WRC-R9`(§5-4) — 이것도 `bₖ` 표다. 4줄을 «그대로» 머리에 단다(주석 블록).
        f.write("# RESULTS_WRC_EXPLORE — bₖ 밴드 (기계 생성 · 🔬 탐색 표기 · 판정 아님)\n")
        f.write(f"# 창 = [등록일, {END}] · gross · 시드 {SEED} · post4·post5 «만»(post6 미존재)\n")
        for ln in NOTATION_4:
            f.write("# " + ln.replace("\n", " ") + "\n")
        f.write("#\n")
        f.write("post\tname\tcode\treg\tfill_n\tk\tP_min\tP_max\tb_lo_pct\tb_hi_pct\tw_pp\tcells\n")
        for c in gate_in:
            if not c.get("bands"):
                continue
            for k, b in enumerate(c["bands"], start=1):
                f.write(f"{c['post']}\t{c['name']}\t{c['code']}\t{c['reg']}\t{c['fill_n']}\t{k}\t"
                        f"{b['pmin']:.2f}\t{b['pmax']:.2f}\t{b['b_lo']:.4f}\t{b['b_hi']:.4f}\t"
                        f"{b['w']:.4f}\t{b['cells']:.2f}\n")

    (BASE / "RESULTS_WRC_EXPLORE.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    print("\n[written] RESULTS_WRC_EXPLORE.md + wrc_explore/*.json|tsv")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())

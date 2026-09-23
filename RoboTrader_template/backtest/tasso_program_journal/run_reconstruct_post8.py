# -*- coding: utf-8 -*-
"""평단 P 복원 — 8번째 글 (REC-Y1~Y4 · REC-Z1~Z5 · Q1-R3 · HDR-D1 · P6-R1' · first_only 관측).

동결 준거(1순위 — 이 docstring 은 2차 출처다):
  사전등록  `PREREG_POST8.md`(동결 `04cd785` · 머지 `729f28b` · 🆕 첫 구속 회차 — 이 레인에 걸리는 것:
            §3 `D-3` `P8-approx의존신고` · §5 `D-5` `P8-갈래계수` · §9 `D-9` `P8-빈티지`·`P8-혼합빈티지신고`)
          · `PREREG_POST6.md` §1-4(창 규약) · §1-5(재진입) · §1-6(절단 가드) · §1-7(`REC-Z5`) · §2-6(`REC-Z1`~`Z5`)
            · §2-7(`REC-Y1`~`Y4` · A-1~A-11 승계) · §3-3(`P6-R1'`) · §3-6(정확 구간법 단일화) · §4 표 #38~#54
          · `PREREG_WEIGHTED_RECON.md` §2-7 `WRC-R5`(:432-435 — 「같은 항목 안 2사이클」 포함 + `구조차단` + 제외 민감도)
          · `PREREG_ANCHOR_REDESIGN.md` §2-1(:115-124 — `REC-` 레인이 «실제로 쓰는» `L`·`HI` = `[D, END]`) · §2-3
          · `PREREG_HDR.md` §4(D1) · `PREREG_Q1_V2.md` §3(R1·R3)
  인테이크  `PREDECISION_2026-09-18_post8.md`(PD-1·PD-2·PD-3·PD-4·PD-5·PD-10·PD-11·PD-12·PD-13·PD-14·
            PD-21·PD-23·PD-27 (바)) · `INTAKE_2026-09-18_post8.md` §1·§2·§5 · `LABELS_2026-09-18_post8.md`
  원장      `ledger_trades.csv`·`ledger_legs.csv` post8 10행/37레그(커밋 `b302f7f`)

🔴 **계산 «전» 에 고정한 해석 결정** — A-1~A-11 은 `RESULTS_RECONSTRUCT_POST5.md` §1 에서 **전부 승계**하고
   (`PREREG_POST6.md` §2-7), 창 종료일(A-1)만 이번 글의 값으로 바꾼다:

  A-1 창 종료일 = **2026-09-18** (발행 2026-09-18(금) = 거래일 ⇒ **발행 당일 봉 «포함»** · B-1 · PD-1).
      🔴 **`WRC-` 포함 전 축 같은 값**이다(`PREREG_WEIGHTED_RECON.md` §5-2 :679-680 이 B-1 을 승계).
      🔴 실행 시 `max(date)` 와 그 날짜 행수를 산출물에 **기록**한다(창으로 쓰지는 않는다).
  A-2 REC-Y1 은 «전칭»으로 읽는다 — 레그 4개 이상인 «모든» 건의 폭 < 3%p. 건수 비율도 병기.
  A-3 되밀림 = 등록일 종가 < 등록일 고가 · 상한가마감 = 종가 == 고가 (post4 §3 조작화 승계).
  A-4 HDR-D1 표본 = 프리셋 `HDR 60%` 인 건. 🔴 코데즈컴바인(`사분위수, 표준형`)은 `approx` 라 판정 분모 밖이고
      프리셋으로도 분모 밖이다(post5 혜인 · post7 서산 전례 · PD-9). 라벨 `SL`·`MANUAL` 은 포함하되 제외 민감도 병기.
  A-5 P6-R1': `PREREG_POST6.md` §3-3 이 「한쪽만 없는 경우」로 확장하고 **양쪽 각 n >= 2** 를 요구한다.
  A-6 Q1-R3 은 다차수 건의 `1-P/H` 가 「1차 밴드」가 아니라는 post4 §2 범주오류 판정을 유지한다.
  A-7 P6-L3' 실행 전제 — 🔴 **이번 회차에도 적용되지 않는다 — 결정 ④로 그 축이 종결됐다**(기록 보존).
  A-8 sigma20 = 등록일 «직전» 20거래일 로그수익률의 표본표준편차(연율화 안 함). 21봉 미만이면 sigma 축 제외.
  A-9 「하나의 평단」 전제가 원리적으로 깨질 수 있는 건에는 flag 만 단다.
      🔴🔴 **우리로 = 한 항목 안 두 사이클**(post5 한켐 A-9 이후 두 번째 · PD-3) — **포함 + `구조차단` 플래그 +
      「우리로 제외」 민감도**(🔒 #1-(i) · A-9 플래그 + `WRC-R5` 유추 · 두 평단 구조가 같다).
      🔴 **해 0개가 나와도 포함 값 그대로 인쇄**한다 — `WRC-R5` 「「하나의 평단」 전제가 원리적으로 깨지는 유일한 형태」.
      🔴 후속 3건(빛과전자·로보티즈·범한퓨얼셀)은 **PD-2 2번(등록일 축 밖 · 이중계상 금지)**으로 REC- 축 «밖»이다 —
      🔑 이번엔 「하나의 평단」 전제 깨짐 사유가 **서지 않는데도**(두 글 모두 1차 매수만 · PD-2 4) 밖이다.
  A-10 «해 0개» 진단의 잔차 문턱 — `REC-Z5`(`PREREG_POST6.md` §1-7)가 **0.022 단일 판정 ·
      0.020 의무 민감도**로 못 박았다. 두 문턱이 분류를 가르면 **「문턱 민감」이라고 인쇄하되 판정은 0.022**.
      🔴 우리로 「17%」는 **소수 0자리**(원장 17.00 정규화 · PD-10 1) ⇒ ±0.5%p 표기 불확실(다른 건 ±0.005%p 의
      **100배**) — 문턱을 고치지 않고 **한계로 적는다**(post7 범한퓨얼셀 「10.8」 ±0.05%p 전례 문형).
  A-11 feasible set 은 **정확 구간법**으로 푼다(유일한 방법 · 점법 폐기 — `PREREG_POST6.md` §3-6):
      `P in ( S*c/(1+(r+0.005)/100),  S*c/(1+(r-0.005)/100) ]` · 레그별 합집합 → 레그 전체 교집합.
      gross(c=1) · net(c=(1-FEE-TAX)/(1+FEE)) 둘 다 푼다.
      의무 인쇄: **구간 개수 · P 범위 · 총 측도 · 폭 · 폭/호가단위(칸)**.
      🔴 점법은 «하한»이므로 인용 시 반드시 「하한」이라 적는다.

🔴 **이번 회차 갈림(post7 대비)**:
  - 판정 분모 = 신규 ∧ `exact` = **4건**(우리로·JW신약·액스비스·우리기술) · `approx` 2(헥토파이낸셜·코데즈컴바인 ·
    「8월말」 → 08-21~08-31 거래일 7갈래 · PD-4 2) = 의무 민감도 · `none` 1(원익 · 🔒 #2) + 후속 3 = 등록일 축 밖.
  - 🔴 **`REC-` 대상 4/4**(초판 3/4 정정 · B-1) · 레그≥4 exact **3**(우리로 7·JW신약 4·우리기술 4) ⇒ **`REC-Y1` 이 열린다**
    (post7 은 2 < 3 으로 닫혔다) · 「우리로 제외」 갈래 2 < 3 ⇒ `P8-갈래계수` 상 **인쇄만**.
  - 🆕 `D-3` 신고 줄(PD-21 · 구성 예고 「없음」) · 🆕 `D-5` 갈래 세 쪽 인쇄(PD-23) ·
    🆕 `D-9` 읽은 시각·`max(updated_at)`·혼합 빈티지 신고(PD-27 (바) — 🔴 `REC-` 창이 두 문서에서 다르다:
    `PREREG_POST8.md:546` `[D−19, D]` ↔ `PREREG_ANCHOR_REDESIGN.md:115-124` `[D, END]` ⇒ **두 창 다** 인쇄).
  - 누적 계열(post4~7)을 **같은 스냅샷에서 재계산**해 나란히 인쇄한다(동결 인쇄값은 대조 열로만 · 판정은 그대로).
  - 🔴 **D-9 ① ↔ byte 결정론**: 벽시계는 재실행마다 바뀐다(post7 규약 = 벽시계는 stdout 전용 ·
    `RESULTS_SECTOR_POST7_NUMBERS.md:426`). ⇒ **「이 DB 지문을 처음 읽은 실행의 KST 시각」**을
    `reconstruct_post8/query_stamp.json` 에 박고 같은 지문의 재실행은 그 값을 다시 인쇄한다(재실행 벽시계는 stdout +
    그 파일 `runs_kst`). 지문이 바뀌면 새 시각이 찍힌다 ⇒ 산출물도 바뀐다(= 스냅샷 이동 감지).

🔴 **라이브 채택 금지**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1) · 라이브 트리 import 0건 · DB 는 SELECT 만 ·
   `adj_factor` 산술 0건 · **새 예측 없음**(이 스크립트는 동결된 항목만 계산한다) · 등급 이름을 쓰지 않는다(§6 단계).
"""
from __future__ import annotations

import hashlib
import itertools
import json
import sys
from pathlib import Path

import psycopg2

import run_reconstruct_post4 as P4M
import run_reconstruct_post5 as P5M
import run_reconstruct_post6 as P6M
import run_reconstruct_post7 as P7M
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

POST8_LOG_NO = "224416253270"
POST8_POST_DATE = "2026-09-18"
DB_UPTO = "2026-09-18"      # PD-1 · 창 종료 = 발행 당일(금 · 거래일) 봉 «포함» · 전 축
END = DB_UPTO               # A-1
PROG_VER = "1.0.42"         # PD-8 — 이 레인은 공변량으로 쓰지 않는다
LEDGER_COMMIT = "b302f7f"   # 원장 단계 커밋(post8 10행/37레그)
BOUNDARY = "2026-09-14"     # KRX 거래시간 연장 발효일(`PREREG_POST8.md` §9 · 제도 경계)
SWEEP_D1 = "2026-09-21 15:35:00"   # 09-18 봉의 D+1 sweep(PD-27 (마) 2)
WIN_START = "2026-07-24"    # PD-27 (다) 창 시작일(가장 이른 `[D−19, D]` 시작)
THR_MAIN = P7M.THR_MAIN     # 0.022 — REC-Z5 판정 (PREREG_EXIT_V2.md §2) · post7 상수 재사용
THR_SENS = P7M.THR_SENS     # 0.020 — REC-Z5 의무 민감도
SEED = P7M.SEED             # 계열 고정 시드 — 🔴 이번 회차에도 «쓰이지 않는다»(결정 ④)
NREP = P7M.NREP             # 〃
CLOSED_BY_DECISION4 = P7M.CLOSED_BY_DECISION4

# (종목, 코드, 등록일, 정밀도, 레그, 체결차수, 프리셋, 라벨, first_only, §1-5 재진입)
# 출처 = INTAKE_2026-09-18_post8.md §1 (신규 7건) · LABELS_2026-09-18_post8.md · PD-4 · PD-11 · 원장 b302f7f
# 🔴 후속 3건(빛과전자·로보티즈·범한퓨얼셀)은 PD-2 2번으로 등록일 축 «밖» — TARGETS 에 없다.
# 🔴 「§1-5 재진입」 = 등록 자체가 같은 종목의 두 번째 이상 사이클(원익·헥토·코데즈). 우리로(항목 내 2 사이클)는
#    이 칸이 아니라 STRUCT_BLOCK(`WRC-R5` `구조차단`)으로 표시한다 — 두 플래그를 한 칸에 섞지 않는다(PD-3).
TARGETS = [
    ("우리로", "046970", "2026-09-11", "exact",
     [24.20, 19.94, 17.00, 16.26, 13.32, 12.44, 0.54], 1, "HDR60", "TP", True, False),
    ("원익", "032940", None, "none",
     [19.49, 17.61, 15.54, 13.14], 1, "HDR60", "MANUAL", True, True),
    ("JW신약", "067290", "2026-09-01", "exact",
     [16.28, 12.68, 11.05, 10.78], 1, "HDR60", "MANUAL", True, False),
    ("헥토파이낸셜", "234340", None, "approx",
     [5.84, 2.98, 1.39, -2.28], 1, "HDR60", "MIX", True, True),
    ("액스비스", "0011A0", "2026-09-11", "exact",
     [11.64, 0.31], 1, "HDR60", "TP", True, False),
    ("코데즈컴바인", "047770", None, "approx",
     [13.20, 11.05, 11.03, 8.71, 6.59], 2, "사분위수", "TP", False, True),
    ("우리기술", "032820", "2026-09-09", "exact",
     [8.47, 8.47, 8.23, 4.75], 1, "HDR60", "TP", True, False),
]

NM, CODE, D0, PREC, LEGS, TR, PRESET, LABEL, FO, REENT = range(10)

# 🔴 PD-3 ③ (i) · 🔒 #1 — `REC-` = A-9 플래그 + `WRC-R5` 유추 · 「우리로 제외」 = 민감도 갈래.
STRUCT_BLOCK = {"우리로": "항목 내 2 사이클(post5 한켐 A-9 이후 두 번째) · 사이클 2 등록일 없음 · 레그 7 배분 불가"}

# 🔴 PD-2 — 후속 3건(REC- 축 밖 · 기록만).
FOLLOWUPS = [("빛과전자", "069540", "post7 #11 · 09-08"), ("로보티즈", "108490", "post7 #9 · 09-04"),
             ("범한퓨얼셀", "382900", "post7 #13 · 09-09")]

# 🔴 `approx` 2건의 §1-4 창 규약 갈래 — PD-4 2번의 달력 실측값을 «옮겨 적었다»(재계산 아님).
#    「8월 말」 = 08-21~08-31 의 모든 거래일 7일(post7 한국화장품제조 전례 · 붙여 쓴 「8월말」도 같은 문언).
_AUG_END = ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26",
            "2026-08-27", "2026-08-28", "2026-08-31"]
APPROX_BRANCHES = {"헥토파이낸셜": list(_AUG_END), "코데즈컴바인": list(_AUG_END)}
# 🔴 PD-3 — 헥토 「한번 더」 ∧ 직전 등록 08-28 ⇒ 08-21~08-27 다섯 갈래는 저자 문장과 논리적으로 모순(표시만 · 좁히지 않는다).
CONTRADICT = {"헥토파이낸셜": ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27"]}
# 🔴 §1-5 3 `P6-PRIOR_CYCLE_IN_WINDOW` 계산용 — 직전 사이클 등록일(원장 실측 · PD-3 표).
PRIOR_REG = {"헥토파이낸셜": ["2026-08-28"], "코데즈컴바인": ["2026-08-21", "2026-08-19"]}

# 🔴 PD-10 1번 — 저자 표기 소수 자릿수 한계(잔차 해석 의무 표기).
DECIMAL_LIMIT = {"우리로": ("17%", 17.00, 0)}

# 🔴 post4~7 동결 «인쇄값» — 대조 열로만 쓴다(재계산 값이 주). 출처 = 파일:줄(옮겨 적은 값이지 재계산이 아니다).
FROZEN = {
    "post4": dict(y3="1/6", y4n=None, z1=None, z3="0/6",
                  src="Y3 `RESULTS_RECONSTRUCT_POST4_EXACT_NUMBERS.md` §2(정확법) · "
                      "Z3 `PREREG_ANCHOR_REDESIGN.md:68`·`RESULTS_RECONSTRUCT_POST6.md:166`(계열 인용 — "
                      "post4 산출물(`RESULTS_RECONSTRUCT_POST4*.md`)에 `REC-Z3` 표는 없다: grep 실측)"),
    "post5": dict(y3="4/6", y4n="4/6", z1="2/6", z3="3/6",
                  src="Y3 `RESULTS_RECONSTRUCT_POST5_NUMBERS.md:72` · Y4 `:90` · "
                      "Z1 `PREREG_POST6.md:562` · Z3 `PREREG_POST6.md:568`"),
    "post6": dict(y3="5/10", y4n="5/10", z1="3/10", z3="6/10",
                  src="`RESULTS_RECONSTRUCT_POST6_NUMBERS.md` Y3 `:103` · Y4 `:125` · Z1 `:129` · Z3 `:153`"),
    "post7": dict(y3="2/6", y4n="2/6", z1="1/6", z3="6/6",
                  src="`RESULTS_RECONSTRUCT_POST7_NUMBERS.md` Y3 `:117` · Y4 `:136` · Z1 `:140` · Z3 `:160`"),
}
# Q1-R3 «인용» 참조값(재계산하지 않는다 — post4~7 표본 밖 · 점법 시대 값) · 출처 `RESULTS_RECONSTRUCT_POST7_NUMBERS.md:216-217`
QUOTED_SOLTLUX = (-0.90, 2.47)

# 관리자 착수 조건 실측(공통 지시문 §3) — 보관 파일의 md5 를 이 스크립트가 직접 잰다.
MGR_PROBE_DIR = Path("D:/archive/tasso-program-journal-20260918/probes_precalc_0924")
MGR_PROBE_FILES = ["run_time.txt", "p8_probes_postfetch_0924.txt", "p8_stab_3x.txt",
                   "p8_probes_postfetch.sql", "p8_stab.sql"]

STAMP = BASE / "reconstruct_post8" / "query_stamp.json"


def say(s=""):
    print(s)
    OUT.append(s)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호)."""
    print(s)


def pct(k, n):
    return f"{k}/{n} = {100 * k / n:.1f}%" if n else f"{k}/0"


def core(cur, code, d0, end, legs):
    """정확 구간법 핵(post5 `feasible_exact`) + 격자 해상도 진단(post5~7 §2 동일 식) + 앵커(post7 §8 동일 값).
    🔴 새 통계 0 — post7 main() 안에 흩어져 있던 식을 한 자리로 모았을 뿐이다(식·문턱 불변).
    `L`·`HI` = `bars()` 행의 min(low)·max(high) = post7 §8 의 `SELECT min(low), max(high) … BETWEEN d0 AND END` 와 같은 집합."""
    rows = bars(cur, code, d0, end)
    if not rows:
        return None
    o0, h0, l0, c0 = rows[0][1], rows[0][2], rows[0][3], rows[0][4]
    iv = feasible_exact(rows, legs, "gross")
    ivn = feasible_exact(rows, legs, "net")
    gaps = [abs(legs[i] - legs[i + 1]) for i in range(len(legs) - 1) if legs[i] != legs[i + 1]]
    dmin = min(gaps) if gaps else None
    lo = min(r[3] for r in rows)
    hi = max(r[2] for r in rows)
    pl, ph = lo * 0.7, hi
    r_lo, r_hi = 100 * tick(pl) / pl, 100 * tick(ph) / ph
    under = (dmin is not None) and dmin < max(r_lo, r_hi)
    v = dict(code=code, d0=d0, end=end, legs=legs, rows=rows, o0=o0, h0=h0, l0=l0, c0=c0,
             pull=c0 < h0, iv=iv, iv_net=ivn, dmin=dmin, under=under, pl=pl, ph=ph,
             r_lo=r_lo, r_hi=r_hi, L=lo, HI=hi, nbars=len(rows))
    if iv:
        pmin, pmax = iv_min(iv), iv_max(iv)
        v.update(pmin=pmin, pmax=pmax, w=(pmax - pmin) / h0 * 100, measure=iv_measure(iv),
                 cells=(pmax - pmin) / tick(pmin), b1=(100 * (1 - pmax / h0), 100 * (1 - pmin / h0)))
    else:
        v.update(pmin=None, pmax=None, w=None, measure=0.0, cells=None, b1=None)
    return v


def win_stats(cur, code, a, b):
    cur.execute("SELECT count(*), count(*) FILTER (WHERE date < %s), count(*) FILTER (WHERE date >= %s), "
                "min(date), max(date), min(updated_at), max(updated_at) FROM daily_prices "
                "WHERE stock_code=%s AND date BETWEEN %s AND %s", (BOUNDARY, BOUNDARY, code, a, b))
    n, nb, na, dmin_, dmax_, umin, umax = cur.fetchone()
    return dict(n=n, before=nb, after=na, first=dmin_, last=dmax_, umin=umin, umax=umax)


def d19_start(cur, code, d0):
    """`[D−19, D]` 창 시작일 = 등록일 포함 20봉의 첫 날(봉수는 종목 봉으로 센다 · B-8)."""
    cur.execute("SELECT min(date), count(*) FROM (SELECT date FROM daily_prices WHERE stock_code=%s "
                "AND date <= %s ORDER BY date DESC LIMIT 20) t", (code, d0))
    return cur.fetchone()


def win5_count(cur, code, d0):
    """창5 `[D, D+4]` 봉수 — 창 종료(END) 이하 봉만 센다."""
    cur.execute("SELECT count(*), max(date) FROM (SELECT date FROM daily_prices WHERE stock_code=%s "
                "AND date >= %s AND date <= %s ORDER BY date LIMIT 5) t", (code, d0, END))
    return cur.fetchone()


def md5_file(p: Path):
    try:
        return hashlib.md5(p.read_bytes()).hexdigest()
    except OSError:
        return None


def stamp_resolve(st, fp, wall):
    """D-9 ① — 같은 DB 지문이면 «처음 읽은 시각»을 유지하고 이번 벽시계만 `runs_kst` 에 덧붙인다.
    지문이 다르면(스냅샷 이동) 새 시각으로 다시 시작한다. 반환 = (새 stamp dict, 인쇄할 시각)."""
    if not st or st.get("fingerprint") != fp:
        st = dict(fingerprint=fp, first_query_kst=str(wall), runs_kst=[])
    st = dict(st, runs_kst=list(st.get("runs_kst", [])) + [str(wall)])
    return st, st["first_query_kst"]


def d3_hit(min_n, n_exact, n_incl):
    """`PREREG_POST8.md:253` 기계 검사 — `n_incl ≥ 최소 n > n_exact` 이면 참(= `approx` 로만 열린다 ⇒ 열지 않는다)."""
    return n_incl >= min_n > n_exact


def gc_status(res):
    """`P8-갈래계수`(`PREREG_POST8.md:337-341`) — res = [(갈래, n, 답, 최소 n 충족?(None=동결 최소 n 없음), 범주)].
    반환 = (상태 문자열, 「갈렸다」 여부)."""
    q = [r for r in res if r[3]]
    qa = sorted(set(r[4] for r in q))
    if res[0][3] is None:
        return "계수 대상 밖(동결 최소 n 없음 · `:338`)", False
    if not q:
        return "최소 n 충족 갈래 0 ⇒ `:341` 자리", False
    if len(qa) >= 2:
        return "🔴 **갈렸다**(`:340` · 충족 갈래 2 이상 · 답 상이)", True
    if len(q) == 1:
        return f"충족 갈래 1 ⇒ 그 답(`:340`) = {q[0][4]}", False
    return f"안 갈렸다 — 충족 {len(q)}갈래 전부 {qa[0]}", False


def re_dep_status(res, has_verdict):
    """§1-5 2 「재진입 의존」(`WRC-R5` 유추) — res[0] = 주 · res[1] = 「우리로 제외」. 반환 = (상태 문자열, 걸림 여부)."""
    diff = res[0][4] != res[1][4]
    if not has_verdict:
        return "판정 없는 항목(기록·관측) — 값만 인쇄" + (" · 값이 다르다" if diff else ""), False
    if diff and res[0][3] is not False and res[1][3] is not False:
        return "🔴 **갈린다** — 두 값이 판정을 가른다 ⇒ 「재진입 의존」 · 어느 쪽도 지지로 선언하지 않는다", True
    return ("답은 다르나 한쪽이 최소 n 미달 — 인쇄만" if diff else "같다"), False


def with_ax(R, vh, vk):
    """주 분모(exact) + `approx` 두 건의 한 갈래 조합 — `approx` 포함 민감도 갈래(D-3 우선 · 계수 밖)."""
    S = dict(R)
    S["헥토파이낸셜"], S["코데즈컴바인"] = vh, vk
    return S


def overlap(a, b):
    return not (a[1] < b[0] or a[0] > b[1])


def sign_of(b):
    lo_b, hi_b = b
    return "양" if lo_b > 0 else ("음" if hi_b < 0 else "걸침")


# ── 판정 함수(갈래마다 같은 식을 돌린다 · 식은 post6·post7 main() 의 판정 문장 그대로) ──────────────
def a_y1(Rs):
    items = [nm for nm, v in Rs.items() if len(v["legs"]) >= 4]
    n = len(items)
    undef = sum(1 for nm in items if not Rs[nm]["iv"])
    ok = sum(1 for nm in items if Rs[nm]["iv"] and Rs[nm]["w"] < 3.0)
    if n < 3:
        return n, f"최소 n 미달({n} < 3)", False, "최소 n 미달"
    if undef == n:   # run_reconstruct_post6.py:333-335 문형
        return n, f"판정 불가 — 대상 전건 해 0개(폭 미정의 {undef}/{n})", True, "판정 불가"
    if undef == 0 and ok == n:   # :336-337
        return n, f"성립(전칭) — 성립 {ok}/{n}", True, "성립"
    return n, f"불성립(전칭) — 성립 {ok}/{n} · 미정의 {undef}", True, "불성립"   # :338-339


def a_y2(Rs):
    narrow = [nm for nm, v in Rs.items() if v["iv"] and v["w"] < 3.0]
    if narrow:
        return len(narrow), f"구분 대상 있음({', '.join(narrow)})", True, "대상 있음"
    return 0, "구분할 대상 없음(좁은 폭 0건)", False, "대상 없음"


def a_y3(Rs):
    n = len(Rs)
    e = sum(1 for v in Rs.values() if not v["iv"])
    hit = n > 0 and e / n >= 1 / 3
    return n, f"{'발동' if hit else '미발동'} — 해 0개 {pct(e, n)}", None, ("발동" if hit else "미발동")


def a_y4(Rs):
    n = len(Rs)
    gz = sum(1 for v in Rs.values() if not v["iv"])
    nz = sum(1 for v in Rs.values() if not v["iv_net"])
    tag = "net 으로 설명 안 됨" if nz >= gz else "net 이 해를 되살림"
    return n, f"{tag} — gross {gz}/{n} · net {nz}/{n}", None, tag


def a_z1(Rs):
    n = len(Rs)
    k = sum(1 for v in Rs.values() if v["under"])
    ok = n > 0 and k / n >= 1 / 3
    return n, f"{'성립' if ok else '불성립'} — 격자 미달 {pct(k, n)}", n >= 3, ("성립" if ok else "불성립")


def a_z2(Rs):
    n = len(Rs)
    ga = [nm for nm, v in Rs.items() if v["under"]]
    gb = [nm for nm, v in Rs.items() if not v["under"]]
    ga_z = sum(1 for nm in ga if not Rs[nm]["iv"])
    gb_z = sum(1 for nm in gb if not Rs[nm]["iv"])
    tag = "충족군에서도 해 0개" if gb_z else "충족군 해 0개 없음"
    return n, f"{tag} — 미달군 {ga_z}/{len(ga)} · 충족군 {gb_z}/{len(gb)}", n >= 3, tag


def a_z3(Rs):
    n = len(Rs)
    k = sum(1 for v in Rs.values() if v["h0"] < v["HI"])
    hit = n > 0 and k / n >= 0.5
    return n, f"{'발동' if hit else '미발동'} — `H` < 창최고 {pct(k, n)}", n >= 3, ("발동" if hit else "미발동")


def a_z4(Rs):
    k = [nm for nm, v in Rs.items() if v["fo"] and len(set(v["legs"])) >= 3]
    return len(Rs), f"조건 충족 {len(k)}건(관측 · 판정 없음)", None, f"{len(k)}건"


def a_q1r3(Rs, refs, reading):
    fo = [nm for nm, v in Rs.items() if v["fo"]]
    meas = [nm for nm in fo if Rs[nm]["iv"]]
    n = len(fo) if reading == "건수" else len(meas)
    if n < 3:
        return n, f"판정 불가(`first_only` {reading} {n} < 3)", False, "판정 불가"
    ov = sum(1 for nm in meas for _, rb in refs if overlap(Rs[nm]["b1"], rb))
    return n, f"겹침 «기록» — 측정 가능 {len(meas)}건 × 직전 글 참조 {len(refs)}구간 중 겹침 {ov}", True, "기록"


def a_hdr(Rs):
    n_all = len(Rs)
    frac = (sum(1 for v in Rs.values() if not v["iv"]) / n_all) if n_all else 0
    z3 = (sum(1 for v in Rs.values() if v["h0"] < v["HI"]) / n_all) if n_all else 0
    den = []
    for nm, v in Rs.items():
        stop = v["tr"] >= 2 and frac >= 1 / 3
        if v["preset"] == "HDR60" and not stop and v["iv"]:
            r1 = v["legs"][0] / 100.0
            smin, smax = v["pmin"] * (1 + r1), v["pmax"] * (1 + r1)
            hlo = (smin - v["L"]) / (v["h0"] - v["L"])
            hhi = (smax - v["L"]) / (v["h0"] - v["L"])
            den.append((hlo + hhi) / 2)
    n = len(den)
    parts = []
    if z3 >= 0.5:
        parts.append("무효(`REC-Z3` 발동)")
    if n < 3:
        parts.append(f"판정 불가(분모 {n} < 3)")
    if not parts:
        m = med(den)
        parts.append(f"{'성립' if 0.50 <= m <= 0.70 else '불성립'}(중점 중앙 {m:.3f})")
    cat = parts[0].split("(")[0]
    return n, " · ".join(parts), n >= 3, cat


def a_r1(Rs):
    fo = sum(1 for v in Rs.values() if v["fo"])
    return fo, f"관측만 — `first_only` {fo} · `full` 누적 1(케이엔알) < 2", False, "관측만"


def main() -> int:  # noqa: C901
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    say("# RESULTS_RECONSTRUCT_POST8_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_reconstruct_post8.py` · 재사용 `run_reconstruct_post5.py`"
        "(`feasible_exact`·`feasible_pointwise`·`min_residual`·`sigma20`·`bars`) + "
        "`run_reconstruct_post6.py`(`win_bars`·`dd_h`·`med`·`fmt_pct`) + "
        "`run_reconstruct_post7.py`(`THR_MAIN`·`THR_SENS`·`SEED`·`NREP`·`CLOSED_BY_DECISION4`·`TARGETS`) + "
        "`run_reconstruct_post4.py`·`run_reconstruct_post5.py`·`run_reconstruct_post6.py`(`TARGETS` — 누적 재계산) + "
        "`reconstruct_prices.py`(`tick`·`grid_prices`·`gross_ret`)")
    say("사전등록 `PREREG_POST8.md`(동결 `04cd785` · 머지 `729f28b` · §3 `D-3` · §5 `D-5` · §9 `D-9` 첫 구속) · "
        "`PREREG_POST6.md` §1-4·§1-5·§1-6·§1-7·§2-6·§2-7·§3-3·§3-6·§4(#38~#54) · "
        "`PREREG_WEIGHTED_RECON.md` §2-7(`WRC-R5`) · `PREREG_ANCHOR_REDESIGN.md` §2-1·§2-3 · "
        "`PREREG_HDR.md` §4 · `PREREG_Q1_V2.md` §3")
    say("인테이크 `PREDECISION_2026-09-18_post8.md` · `INTAKE_2026-09-18_post8.md` · "
        f"`LABELS_2026-09-18_post8.md` · 원장 커밋 `{LEDGER_COMMIT}`(post8 10행/37레그)\n")

    # ── 스냅샷 · 창 구간 지문 (D-9 ②·④) ─────────────────────────────────
    cur.execute("SELECT max(date) FROM daily_prices")
    snap = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (snap,))
    snap_rows = cur.fetchone()[0]
    cur.execute("SELECT count(*), count(DISTINCT date), min(updated_at), max(updated_at) FROM daily_prices "
                "WHERE date BETWEEN %s AND %s", (WIN_START, END))
    g_n, g_dates, g_umin, g_umax = cur.fetchone()
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (END,))
    end_rows = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (SWEEP_D1[:10],))
    d1_rows = cur.fetchone()[0]
    cur.execute("SELECT now()")
    wall = cur.fetchone()[0]
    fp = dict(win=f"{WIN_START}~{END}", n=g_n, dates=g_dates, umin=str(g_umin), umax=str(g_umax),
              snap=str(snap), snap_rows=snap_rows, end_rows=end_rows)
    try:
        st = json.loads(STAMP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = None
    st, _first = stamp_resolve(st, fp, wall)
    STAMP.parent.mkdir(exist_ok=True)
    STAMP.write_text(json.dumps(st, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    note(f"[stdout 전용] 이번 실행 벽시계(DB now()) = {wall} · 지문 최초 읽기 = {st['first_query_kst']} · "
         f"같은 지문 실행 {len(st['runs_kst'])}회")
    umin_ok = str(g_umin) >= SWEEP_D1

    exact = [t for t in TARGETS if t[PREC] == "exact"]
    approx = [t for t in TARGETS if t[PREC] == "approx"]
    none_ = [t for t in TARGETS if t[PREC] == "none"]

    say("## §0. 실행 환경 · 승계 선언 · 🆕 `PREREG_POST8` 공통 인쇄 의무\n")
    say("| 칸 | 값 |")
    say("|---|---|")
    say("| 🔴 라이브 채택 | **대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1) — "
        "이 문서의 어떤 숫자도 매매 규칙으로 옮기지 않는다 |")
    say(f"| 창 종료 | 🔴 **창 종료 {END} = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · "
        "전 축(`WRC-` 포함) · PD-1** · 창 = `[등록일, " + END + "]` · 스크립트 상수 `DB_UPTO` |")
    say(f"| 실행 시 `max(date)` | **실행 시 `max(date)` = {snap} · 그 날짜 행수 {snap_rows:,} — 기록만(창 아님)** "
        "(`WRC-D7` 표기 의무 · §7-B #13) |")
    say(f"| D-9 ① 쿼리 실행 시각(KST) | **{st['first_query_kst']}** — 🔴 이 DB 지문(②·④·`max(date)`·행수)을 이 스크립트가 "
        "«처음» 읽은 실행의 DB `now()` · 같은 지문의 재실행은 같은 값을 인쇄한다(byte 결정론 — post7 규약 "
        "「벽시계는 stdout 전용」 `RESULTS_SECTOR_POST7_NUMBERS.md:426` 과의 절충 · 재실행마다의 실제 시각 = stdout + "
        "`reconstruct_post8/query_stamp.json` `runs_kst`) |")
    say(f"| D-9 ② 창 구간 `max(daily_prices.updated_at)` | **{g_umax}** (창 구간 `{WIN_START}` ~ `{END}` · 전 종목 "
        f"{g_n:,}행 · 거래일 {g_dates}) — 종목별 창의 값은 §0-b |")
    say(f"| D-9 ③ | **09-18 봉은 D+1(09-21) sweep 이후 읽음** — 09-21 행 {d1_rows:,} 존재 · ④ 기록 |")
    say(f"| D-9 ④ (기록 · 통과 조건 아님) | **창 구간 `min(updated_at)` = {g_umin} ≥ {SWEEP_D1[:16]}: "
        f"{'예' if umin_ok else '아니오'}** — 🔴 `updated_at` 은 sweep 이 전 행을 일괄 갱신한 값이라 "
        "빈티지 «증거»가 아니라 「그 sweep 이 창 구간을 한 번 훑고 지나갔다」는 기록이다(PD-27 (라)·(마) 2 (f)) |")
    say(f"| 09-18 행수 | **{end_rows:,}** (관리자 실측 09-18 19:16 값 2,764 · 09-24 00:07:44 3/3 안정 — 대조만) |")
    say("| `P-3` | 🔴 **판별력 0 — 「통과」로 인용하지 않는다**(`updated_at > created_at` 항등 참 · PD-27 (라)) · 인쇄만 |")
    say("| A-1~A-11 | **A-1 ~ A-11 전부 승계**(`PREREG_POST6.md` §2-7 · 문장은 이 스크립트 docstring 에 박혀 있다) — "
        f"A-1 의 창 종료일만 이번 글 값 **{END}** 으로 바뀐다 |")
    say("| A-11 | **정확 구간법이 유일한 방법**(§3-6) · 점법은 **폐기** — 대조로만 인쇄하고 인용 시 **「하한」**이라 적는다 |")
    say("| D-9 빈티지 정의 | `P8-빈티지` = `daily_prices.high`/`low` 의 **«D+1 안정 빈티지»**(시간외분이 들어간 채로 · "
        "`PREREG_POST8.md:539-540`) — 🔴 **「정규장만」 갈래는 열지 않는다**(`:549-550`) · `adj_factor` 산술 **0**(`:551`) |")
    say(f"| 판정 분모 | 🔴 **신규 ∧ `exact` = {len(exact)}건**(" + "·".join(t[NM] for t in exact) + ") — "
        "`REC-` 대상 **4/4**(우리로 포함 + `구조차단` · B-1 정정) · 「우리로 제외」 민감도 3 |")
    say(f"| `approx` | **{len(approx)}건**(" + "·".join(t[NM] for t in approx) + ") — 「8월말」 → §1-4 창 규약 "
        "08-21~08-31 거래일 7갈래 · **의무 민감도**(판정 아님 · PD-4 2) |")
    say(f"| 등록일 축 밖 | `none` **{len(none_)}건**(" + "·".join(t[NM] for t in none_) + " · 🔒 #2) + "
        "후속 **3건**(" + "·".join(f[0] for f in FOLLOWUPS) + " · PD-2 2) |")
    say(f"| `REC-Z5` | 판정 **{THR_MAIN:.3f}%p 단일** · **{THR_SENS:.3f}%p 의무 민감도**(갈리면 「문턱 민감」 인쇄 · "
        "판정은 0.022 로 선다 — §1-7) |")
    say("| 결정 ④ | 🔴🔴 `PREREG_BUYLADDER` 계열 **종결** ⇒ " + " · ".join(CLOSED_BY_DECISION4) +
        " **재개하지 않는다 · 기록 보존만**(§10) |")
    say(f"| 시드 | `SEED` = {SEED} · `NREP` = {NREP:,} — 🔴 **이 스크립트는 귀무를 돌리지 않는다**(축 종결 · 시드 불변) |")
    say(f"| `prog_ver` | `{PROG_VER}` — 🔴 이 산출물은 `prog_ver` 를 공변량으로 **쓰지 않는다** ⇒ `D-8` 수준 목록 "
        "의무 대상 아님(PD-26 · INTAKE §5 ⚠️ `D-8`) |")
    say()
    say("**관리자 착수 조건 실측(2026-09-24 00:07:44 KST · 공통 지시문 §3 · 보관 파일 md5 = 이 스크립트가 직접 잰 값)**\n")
    say("| 보관 파일(`" + str(MGR_PROBE_DIR).replace("\\", "/") + "/`) | md5 |")
    say("|---|---|")
    for f in MGR_PROBE_FILES:
        m = md5_file(MGR_PROBE_DIR / f)
        say(f"| `{f}` | `{m if m else '없음(경로 미존재)'}` |")
    say()
    say("- 실측(옮겨 적음 · 대조용): `daily_prices` 09-18 행수 2,764(3/3 안정) · 09-18 `max(updated_at)` = "
        "2026-09-23 15:46:25.855518 · 창 구간 `min(updated_at)` = 2026-09-23 15:45:10.623955 ≥ 09-21 15:35: 예 · "
        "실행 시 `max(date)` 2026-09-23(2,764 · 기록만) · `P-3` rewritten = n(판별력 0 · 인쇄만)")
    say()
    say("**🆕 `PREREG_POST8` 인쇄 의무 체크(이 산출물)**\n")
    say("| 의무 | 이 산출물 | 자리 |")
    say("|---|---|---|")
    say("| `D-9` ① 실행 시각 · ② `max(updated_at)` · ③ D+1 sweep 줄 · ④ `min(updated_at)` 기록 · ⑤ 혼합 빈티지 신고 | "
        "**적용** — 🔴 `REC-` 창 두 개(`[D−19, D]` · `[D, END]`) **둘 다** | §0 · §0-b |")
    say("| `D-3` `P8-approx의존신고` 한 줄 | **적용** | §15 |")
    say("| `D-5` `P8-갈래계수` — 갈래마다 `(이름, n, 답)` | **적용** | §14 |")
    say("| `D-6` `ddof` | 해당 없음 — 이 산출물은 `n_up` sd 를 인쇄하지 않는다 | — |")
    say("| `D-8` `P8-결측수준` | 해당 없음 — `prog_ver` 공변량 미사용 | §0 |")
    say("| `D-1`·`D-2`·`D-4`·`D-7`·`D-11` | 해당 없음 — 다른 축(`ANC-`·`EXIT-`·`WRC-`·`LAD-`·`REG-`) | — |")
    say("| `D-10` 등급 열 | 이 산출물은 등급을 쓰지 않는다(§6 단계 · PD-16·PD-28) | — |")
    say("| 공통 11 | 라이브 아님 · post4~7 같은 스냅샷 재계산 나란히(§17) · 새 예측 0 · 값 규칙 불변 · 모호는 양쪽 인쇄 | §0 · §17 · §18 |")

    # ── §0-b. D-9 창별 읽은 시각 · 혼합 빈티지 신고 ─────────────────────
    say()
    say("## §0-b. `D-9` — 종목별 창 · 읽은 시각(`updated_at`) · `P8-혼합빈티지신고` (🔴 `REC-` 창 두 개 다)\n")
    say("🔴🔴 **충돌 신고(§1-8 형식 · PD-27 (바) 승계)** — `PREREG_POST8.md:546` 은 `REC-`/`REG-` = **`[D−19, D]`** 로 적고, "
        "`PREREG_ANCHOR_REDESIGN.md:115-124`(§2-1 「`REC-` 레인이 «실제로 쓰는» 것」)는 `L`·`HI` 를 **`[D, END]`** 위에 "
        "정의한다. 🔑 이 레인은 **둘 다 실제로 읽는다** — `[D, END]` = `L`·`HI`·feasible 봉(§1·§8·§12) · `[D−19, D]` = "
        "`P6-R1'` 의 `H6`(§13) · 절단 가드(§16). ⇒ **두 창 다 인쇄**한다(더 많이 인쇄하는 쪽 · 바꿔 쓰지 않는다).\n")
    say("| 종목 | 정밀도 | 창 | 구간 | 봉수 | 경계 전 | 경계 후 | 걸침? | 창 `min(updated_at)` | 창 `max(updated_at)` |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    cross_lines = []
    vint = {}

    def vin_rows(nm, prec, code, d0):
        s19, n19 = d19_start(cur, code, d0)
        wa = win_stats(cur, code, d0, END)
        wb = win_stats(cur, code, s19, d0)
        for lab, w in (("`[D, END]`(ANC §2-1)", wa), ("`[D−19, D]`(POST8 :546)", wb)):
            cross = w["before"] > 0 and w["after"] > 0
            say(f"| {nm} | {prec} | {lab} | `[{w['first']}, {w['last']}]` | {w['n']} | {w['before']} | "
                f"{w['after']} | {'🔴 **걸침**' if cross else '안 걸침'} | {w['umin']} | {w['umax']} |")
            if cross:
                cross_lines.append(f"- {nm}({prec}) {lab.split('(')[0]}: *「창 `[{w['first']}, {w['last']}]` 은 "
                                   f"제도 경계 2026-09-14 를 걸친다 — 경계 전 `{w['before']}` 봉 / 후 `{w['after']}` 봉 · "
                                   "혼합 빈티지」*")
        return wa, wb

    for t in exact:
        vint[t[NM]] = vin_rows(t[NM], "exact", t[CODE], t[D0])
    for t in approx:
        for d in APPROX_BRANCHES[t[NM]]:
            vin_rows(f"_{t[NM]} D={d[5:]}_", "approx", t[CODE], d)
    say()
    say(f"**`P8-혼합빈티지신고`(의무 문장 · `PREREG_POST8.md:546-548` · 걸침 창 {len(cross_lines)}개)**\n")
    for ln in cross_lines:
        say(ln)
    say()
    say("- 🔴 **`[D−19, D]` 창은 전 건 «안 걸침»**(끝 = 등록일 ≤ 09-11 · approx 갈래 ≤ 08-31) — 발동은 `[D, END]` 줄이 낸다"
        "(PD-27 (바) 와 같은 구성).")
    say("- 참고(이 산출물은 봉수만 읽는다 · `H`·`L` 을 읽지 않는다): 창5 `[D, D+4]` 는 `LAD-` 축 창이다 — 걸침 신고는 "
        "`run_ladder_tranche_post8.py` 가 맡는다. §16 에 봉수만 적는다.")
    say("- post4~7 재계산 창(§17)은 **전부 종료 ≤ 2026-09-11** — 제도 경계 «전» · 안 걸침(그 창들의 `updated_at` 은 §17 표).")
    say("- 🔴 **「정규장만」 값은 만들지 않았다** — `overtime_daily` 는 09-14 `ovtm_vol>0` 0 · 09-15 이후 행 없음 · "
        "15:30 분봉 09-16~09-23 = 0·0·1·0·1·0(관리자 실측 · 보관 `p8_probes_postfetch_0924.txt` `P-5`) ⇒ "
        "뺄 소스도 재구성 경로도 없다(한계 · `PREREG_POST8.md:549-550`).")
    say("- 🔴 **방향 추론 인용 금지** — 「시간외분이 `H` 를 높이고 `L` 을 낮춘다」는 추론이다(`PREREG_POST8.md:586-589`).")

    # ── §1. feasible 원표 ────────────────────────────────────────────────
    say()
    say("## §1. feasible set 원표 (gross · A-11 정확 구간법) — 의무 인쇄 5칸\n")
    say("의무 인쇄(§3-6): **구간 개수 · P 범위 · 총 측도 · 폭 · 폭/호가단위(칸)**\n")
    say(f"🟢 **주 판정 분모 = `exact` {len(exact)}건**(PD-4) — 아래 표. 🔴 우리로는 **`구조차단`**(항목 내 2 사이클) — "
        "해 0개여도 해 있음이어도 **그 값은 «두 평단을 한 평단으로 푼» 결과**다(`WRC-R5` :435).\n")
    say("| 종목 | 차수 | 라벨 | 등록일 | 레그 | 등록일 봉 [저,시,고,종] | 되밀림 | "
        "**구간 개수** | **P 범위** | **총 측도(원)** | **`1-P/H` 범위** | **폭** | "
        "**폭/호가단위(칸)** | (대조·하한) 점법 개수/폭 | 플래그 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    R = {}
    for t in exact:
        nm = t[NM]
        v = core(cur, t[CODE], t[D0], END, t[LEGS])
        v.update(tr=t[TR], preset=t[PRESET], label=t[LABEL], fo=t[FO], reent=t[REENT])
        v["pts"] = feasible_pointwise(v["rows"], v["legs"], gross_ret)
        R[nm] = v
        pts = v["pts"]
        pw = f"{len(pts)} / {(max(pts)-min(pts))/v['h0']*100:.2f}%p" if pts else "0 / —"
        bar = f"[{v['l0']:,.0f}, {v['o0']:,.0f}, {v['h0']:,.0f}, {v['c0']:,.0f}]"
        pull_s = "예" if v["pull"] else "아니오"
        flag = "🔴 **`구조차단`**" if nm in STRUCT_BLOCK else "—"
        if v["iv"]:
            say(f"| {nm} | {t[TR]}차 | {t[LABEL]} | {t[D0]} | {len(t[LEGS])} | {bar} | {pull_s} | "
                f"**{len(v['iv'])}** | {v['pmin']:,.2f}~{v['pmax']:,.2f} | **{v['measure']:,.2f}** | "
                f"{v['b1'][0]:+.2f}%~{v['b1'][1]:+.2f}% | **{v['w']:.2f}%p** | "
                f"**{v['cells']:.1f}칸**({tick(v['pmin'])}원) | {pw} | {flag} |")
        else:
            say(f"| {nm} | {t[TR]}차 | {t[LABEL]} | {t[D0]} | {len(t[LEGS])} | {bar} | {pull_s} | "
                f"**0** | — | **0.00** | — | — | — | {pw} | {flag} |")
    say()
    say(f"- 되밀림(A-3: 종가 < 고가) **{sum(1 for v in R.values() if v['pull'])}/{len(R)}** · "
        f"상한가마감(종가==고가) **{sum(1 for v in R.values() if not v['pull'])}/{len(R)}**")
    say("- 고가 대비 종가 되밀림 폭: " + " · ".join(
        f"{nm} {100*(v['h0']-v['c0'])/v['h0']:.2f}%" for nm, v in R.items()))
    live = [(nm, v) for nm, v in R.items() if v["iv"]]
    if live:
        say("- feasible 총 측도(정확법): " + " · ".join(f"{nm} {v['measure']:,.2f}원" for nm, v in live) +
            " — 🔑 *「범위 안에 든다」와 「해다」는 다른 진술이다*: 범위 대비 측도를 함께 본다.")
        dirs = " · ".join(f"{nm} {(max(v['pts'])-min(v['pts']))/v['h0']*100:.2f}→{v['w']:.2f}%p"
                          for nm, v in live if v["pts"])
        say("- 🔴 **점법 대 정확법**(A-11 *「점법 값은 전부 하한」* 방향 확인): " +
            (dirs if dirs else "해가 있는 건에 점법 해 0개"))
    else:
        say("- feasible 총 측도(정확법): 해가 있는 건 **0** — 점법 대조도 대상 없음")
    for k, (raw, val, nd) in DECIMAL_LIMIT.items():
        say(f"- 🔴 **소수 자릿수 한계**(PD-10 1번): {k} 「{raw}」는 **소수 {nd}자리**(나머지 레그는 2자리 · 원장 "
            f"{val:.2f} 정규화) ⇒ 복원 잔차 문턱(`REC-Z5` {THR_MAIN:.3f}%p)은 **소수 2자리 전제**이므로 "
            "**그 건의 잔차·해 존재 해석에 한계 표기 의무**가 있다(§2 에 그대로 반영 · 값 규칙 불변).")
    say("- 🔴🔴 **우리로 = 「하나의 평단」 전제가 원리적으로 깨지는 형태**(`WRC-R5` :435 · A-9) — 두 사이클(각 「1차 매수」)의 "
        "레그 7개를 **한 평단으로** 푼다. 🔑 ***해 0개면 「두 평단이라서」와 「다른 이유」를 가르지 못하고, 해가 있으면 "
        "그 해는 두 평단이 우연히 한 구간에 겹친 것일 수 있다*** — 어느 쪽이든 포함 값 그대로 인쇄한다(🔒 #1-(i)).")

    # ── §1-b. approx 갈래 ────────────────────────────────────────────────
    say()
    say("## §1-b. `approx` 2건 — §1-4 창 규약(「8월 말」 7갈래) · 갈래별 (의무 민감도 · 판정 아님)\n")
    say("🔴 **판정에 쓰지 않는다**(PD-4 1번 · `D-3`) — 「8월 말」의 «모든 거래일»을 갈래로 두고 값의 **범위**를 인쇄한다. "
        "갈래 날짜는 PD-4 2번의 달력 실측값을 **옮겨 적은 것**이다 · 산출물 표시 = **「창 규약 적용」**(`PREREG_POST6.md:269`).\n")
    say("| 종목 | 갈래 D | 모순 갈래? | `P6-PRIOR_CYCLE_IN_WINDOW` | 봉 `[D, END]` | 구간 개수 | 폭(%p) | "
        "`H` < 창최고? | 격자 미달? |")
    say("|---|---|---|---|---|---|---|---|---|")
    AX = {}
    for t in approx:
        nm = t[NM]
        AX[nm] = []
        for d in APPROX_BRANCHES[nm]:
            v = core(cur, t[CODE], d, END, t[LEGS])
            v.update(tr=t[TR], preset=t[PRESET], label=t[LABEL], fo=t[FO], reent=t[REENT])
            wdates = [r[0] for r in win_bars(cur, t[CODE], d, 19, 0)]
            prior = int(any(p in wdates for p in PRIOR_REG.get(nm, [])))
            v["prior_flag"] = prior
            AX[nm].append((d, v))
            con = "🔴 **모순**(「한번 더」 ∧ 직전 08-28)" if d in CONTRADICT.get(nm, []) else "—"
            w_s = "—" if v["w"] is None else f"{v['w']:.2f}"
            say(f"| {nm} | {d} | {con} | {prior} | {v['nbars']} | {len(v['iv'])} | {w_s} | "
                f"{'예' if v['h0'] < v['HI'] else '아니오'} | {'예' if v['under'] else '아니오'} |")
    say()
    say("| 종목 | 갈래 수 | 해 있는 갈래 | 구간 개수 범위 | 폭 범위(%p) | `H` < 창최고 갈래 | 플래그 1 갈래 |")
    say("|---|---|---|---|---|---|---|")
    for t in approx:
        nm = t[NM]
        have = [v for _, v in AX[nm] if v["iv"]]
        ns = [len(v["iv"]) for v in have]
        ws = [v["w"] for v in have]
        say(f"| {nm} | {len(AX[nm])} | **{len(have)}/{len(AX[nm])}** | "
            f"{f'{min(ns)}~{max(ns)}' if ns else '—'} | {f'{min(ws):.2f}~{max(ws):.2f}' if ws else '—'} | "
            f"{sum(1 for _, v in AX[nm] if v['h0'] < v['HI'])}/{len(AX[nm])} | "
            f"{sum(v['prior_flag'] for _, v in AX[nm])}/{len(AX[nm])} |")
    say()
    say("- 🔴 **재진입 민감도와 `approx` 민감도가 «겹친다»**(헥토·코데즈 = 둘 다 `approx` ∧ §1-5 재진입) — "
        "PD-3 마지막 줄대로 **두 민감도를 따로 인쇄하고 합치지 않는다**(§14).")
    say("- 🔴 **헥토 「모순 갈래」**(08-21~08-27 · 5/7)는 표시만 — 창 규약을 **좁히지 않는다**(`PREREG_POST6.md:266` · PD-3).")
    say("- ⚠️ **`P6-W10`(무작위 «창» 귀무)은 `TV` 축으로는 미루지만 이 용도로는 의무 인쇄**다(PD-6 예외 한 자리) — "
        "그 인쇄는 `run_regday_post8.py`/`run_d1_oos_post8.py` 레인이 맡는다. **두 용도를 한 수로 합치지 않는다.**")

    # ── §1-c. 등록일 축 밖 ───────────────────────────────────────────────
    say()
    say("## §1-c. 등록일 축 «밖» — `none` 1건 · 후속 3건 (구성으로 빠진다)\n")
    say("| 종목 | 코드 | 차수 | 레그 | 라벨 | 왜 밖인가 |")
    say("|---|---|---|---|---|---|")
    for t in none_:
        say(f"| {t[NM]} | {t[CODE]} | {t[TR]}차 | {len(t[LEGS])} | {t[LABEL]} | "
            "🔴 등록일 **미명시**(「9월 3일, 한 차례 매매 후, 다시 … 등록」 — 두 사건 구문에서 날짜가 어느 사건에 붙는지 "
            "원문이 정하지 않는다 · 🔒 #2 `none`) ⇒ 창 `[D, " + END + "]` 이 **정의되지 않는다** · "
            "대안 독법 exact 09-03 은 **갈래로 계산하지 않는다**(PD-4) |")
    for nm, code, why in FOLLOWUPS:
        say(f"| {nm} | {code} | 1차 | — | — | 🔁 **후속**({why}) — PD-2 2번 **등록일 축 밖**(이중계상 금지) · "
            "🔑 「하나의 평단」 전제 깨짐 사유는 이번엔 서지 않는다(두 글 모두 1차 매수만 · PD-2 4) — 사유는 등록일 축 규약이다 |")
    say()
    say("- 🔴 **값을 보고 뺀 것이 아니라 «정의로» 빠진다**(PD-2 2 · PD-4 3).")
    say("- 🔴 **후속 3건의 연결 지점은 3/3 증가**(12.17→23.47 · 9.13→17.95 · 7.94→20.99 · PD-2 4) — 기록만 · 원인 해석 안 함.")

    # ── §2. 해 0개 진단 · REC-Z5 ─────────────────────────────────────────
    say()
    say("## §2. 해 0개 진단 · `REC-Z5` — 판정 0.022 / 민감도 0.020\n")
    say("`Δr_min` = 서로 «다른» 인접 레그 수익률의 최소 간격(%p) · "
        "`res` = 호가 한 칸이 만드는 수익률 해상도 `100*tick(P)/P`\n")
    say("🔑 `Δr_min < res` 이면 **두 레그를 격자 위 서로 다른 매도가로 표현할 수 없다** ⇒ 산술적으로 해가 0개다.\n")
    say(f"🔴 **`REC-Z5`**(§1-7): 판정 문턱 **{THR_MAIN:.3f}%p 단일** · "
        f"**{THR_SENS:.3f}%p 는 의무 민감도**. 두 문턱이 분류를 가르면 **「문턱 민감」이라 인쇄하되 "
        f"판정은 {THR_MAIN:.3f} 로 선다**.\n")
    say("| 종목 | 레그 | `Δr_min` | 후보 P 범위 | `res`(P 양끝) | **`Δr_min` < `res`?** | "
        "최소잔차 적합 P | **최대 오차** | **판정 @0.022** | (민감도) @0.020 | 자릿수 한계 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    split = []
    for nm, v in R.items():
        mr = min_residual(v["rows"], v["legs"], gross_ret)
        v["minres"] = mr
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
        v["diag"] = diags
        if not v["iv"] and mr is not None and diags[0] != diags[1]:
            split.append(nm)
        lim = "🔴 **소수 0자리 레그 有**(「17%」)" if nm in DECIMAL_LIMIT else "—"
        dm_s = "—" if v["dmin"] is None else f"{v['dmin']:.2f}%p"
        say(f"| {nm} | {v['legs']} | {dm_s} | "
            f"{v['pl']:,.0f}~{v['ph']:,.0f} | {v['r_hi']:.3f}~{v['r_lo']:.3f}%p | "
            f"{'🔴 **예**' if v['under'] else '아니오'} | "
            f"{'—' if mr is None else f'{mr[1]:,.0f}'} | "
            f"{'—' if mr is None else f'**{mr[0]:.6f}%p**'} | {diags[0]} | {diags[1]} | {lim} |")
    say()
    say(f"- 두 문턱에서 분류가 갈리는 건: **{len(split)}건** ({', '.join(split) if split else '없음'}) ⇒ "
        + ("🔴 **「문턱 민감」** — 판정은 0.022 로 서고 그 사실을 여기 인쇄한다."
           if split else "**문턱 민감 없음**(0.020·0.022 에서 분류 동일)"))
    say(f"- 격자 해상도 미달(`Δr_min` < `res`) 건: **{sum(1 for v in R.values() if v['under'])}/{len(R)}** ("
        + (", ".join(nm for nm, v in R.items() if v["under"]) or "없음") + ")")
    one_leg = [nm for nm, v in R.items() if v["dmin"] is None]
    say("- 🔑 서로 다른 값 레그가 **1개뿐인 건**은 `Δr_min` 이 «정의되지 않는다» — 격자 미달 판정에서 빠진다: "
        + (", ".join(one_leg) if one_leg else "이번 표본 **0건**"))
    say("- 🔴 **동률 레그**(우리기술 8.47·8.47)는 다중집합 그대로 푼다(같은 값 두 레그 = 같은 제약 두 번 · PD-10 2) — "
        "`Δr_min` 은 서로 «다른» 값 사이 간격만 센다(post5~7 식 그대로).")
    for k, (raw, val, nd) in DECIMAL_LIMIT.items():
        say(f"- 🔴 **한계 표기 의무(PD-10 1번)**: {k}의 레그 「{raw}」는 소수 {nd}자리다 ⇒ 그 레그의 `Δr`·잔차는 "
            f"**±0.5%p 의 표기 불확실**을 안고 있다(다른 건의 ±0.005%p 보다 **100배 넓다** · post7 범한퓨얼셀 「10.8」 "
            f"±0.05%p 의 10배). **문턱({THR_MAIN:.3f}%p)을 고치지 않고 값({val:.2f})을 보정하지 않는다** — 한계로 적는다.")

    # ── §3. REC-Y1 ───────────────────────────────────────────────────────
    say()
    say("## §3. `REC-Y1`(핵심) — 레그 4개 이상인 건의 `b1` feasible 폭 < 3%p (전칭 · A-2)\n")
    say("| 종목 | 정밀도 | 레그 | 구간 개수 | 총 측도(원) | 폭 | < 3%p | 플래그 |")
    say("|---|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        if len(v["legs"]) < 4:
            continue
        flag = "🔴 `구조차단`" if nm in STRUCT_BLOCK else "—"
        if not v["iv"]:
            say(f"| {nm} | exact | {len(v['legs'])} | **0** | 0.00 | ⛔ **미정의**(해 0개) | ⛔ | {flag} |")
        else:
            say(f"| {nm} | exact | {len(v['legs'])} | {len(v['iv'])} | {v['measure']:,.2f} | "
                f"**{v['w']:.2f}%p** | {'성립' if v['w'] < 3.0 else '위반'} | {flag} |")
    for t in approx:
        if len(t[LEGS]) < 4:
            continue
        have = [v for _, v in AX[t[NM]] if v["iv"]]
        ws = [v["w"] for v in have]
        say(f"| _{t[NM]}_ | _approx_ | _{len(t[LEGS])}_ | _{len(have)}/{len(AX[t[NM]])} 갈래에 해_ | _—_ | "
            f"_{f'{min(ws):.2f}~{max(ws):.2f}%p' if ws else '—'}_ | _민감도 전용_ | — |")
    y1n, y1ans, _, _ = a_y1(R)
    sub_ex = {nm: v for nm, v in R.items() if nm not in STRUCT_BLOCK}
    y1n_x, y1ans_x, _, _ = a_y1(sub_ex)
    ax_y1 = [t for t in approx if len(t[LEGS]) >= 4]
    say()
    say(f"- 레그>=4 **`exact` 대상 {y1n}건**(" + ", ".join(nm for nm, v in R.items() if len(v["legs"]) >= 4) +
        f") · 최소 n **3** ⇒ **{'충족' if y1n >= 3 else '미달'}** (post7 은 2 < 3 으로 닫혔다)")
    say(f"- ⇒ **`REC-Y1` = {y1ans}**(판정 문형 = `run_reconstruct_post6.py:333-339` 승계 — 전건 미정의 ⇒ 판정 불가 · "
        "전건 측정·전건 < 3%p ⇒ 성립 · 그 밖 ⇒ 불성립)")
    say(f"- 🔴 「우리로 제외」 갈래: 대상 **{y1n_x}건** ⇒ {y1ans_x} — `P8-갈래계수`(`PREREG_POST8.md:339`) 상 "
        "**인쇄만**(최소 n 미달 갈래는 「갈렸다」의 근거로 쓰지 않는다)")
    say(f"- (민감도 · 판정 아님) `approx` 포함 갈래: {y1n} + {len(ax_y1)} = **{y1n + len(ax_y1)}건** — "
        "🔴 `D-3` 이 우선(`approx` 로 최소 n 을 채우지 않는다 · 이번엔 `exact` 가 이미 채운다 ⇒ 신고 대상 아님 · §15)")
    say("- 🔴 *「해가 없으니 폭 0 = 3%p 미만 = 성립」*으로 읽으면 규칙 완화다. **읽지 않았다.**")
    say("- 🔴 **방향 자기신고**(PD-13 축자): 우리로 포함은 `REC-Y1` 을 **여는** 쪽이다(2 → 3). 동시에 우리로는 "
        "`WRC-R5` 가 「원리적으로 깨지는 유일한 형태」라 적은 모양이라 해 0개를 내기 쉬운 쪽일 수도 있다(추론 · §5 실측).")

    # ── §4. REC-Y2 ───────────────────────────────────────────────────────
    say()
    say("## §4. `REC-Y2`(반증축 · 필수) — 폭을 «호가단위 배수»로도 인쇄\n")
    say("Y2: *「레그 수와 무관하게 폭이 좁으면 원인은 레그 수가 아니라 가격대(호가단위)다」*\n")
    say("| 종목 | 레그 | 가격대 | 호가단위(P 하단) | 폭(%p) | **폭 / 호가단위(칸)** | (대조·하한) 점법 칸 |")
    say("|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        if not v["iv"]:
            say(f"| {nm} | {len(v['legs'])} | {v['L']:,.0f}~{v['HI']:,.0f} | — | — | — | — |")
            continue
        pwc = ((max(v["pts"]) - min(v["pts"])) / tick(min(v["pts"]))) if v["pts"] else None
        say(f"| {nm} | {len(v['legs'])} | {v['L']:,.0f}~{v['HI']:,.0f} | {tick(v['pmin'])}원 | {v['w']:.2f}%p | "
            f"**{v['cells']:.1f}칸** | {'—' if pwc is None else f'{pwc:.1f}칸'} |")
    y2n, y2ans, _, _ = a_y2(R)
    say()
    say(f"- ⇒ **`REC-Y2` = {y2ans}** (좁은 폭 < 3%p 건 {y2n}) · 누적 대상: post6 1(지투파워) + post7 0 + post8 {y2n}")

    # ── §5. REC-Y3 ───────────────────────────────────────────────────────
    say()
    say("## §5. `REC-Y3`(중단 규칙) — feasible set 이 비는 비율\n")
    empty = [nm for nm, v in R.items() if not v["iv"]]
    frac = len(empty) / len(R)
    multi = [nm for nm, v in R.items() if v["tr"] >= 2]
    empty_multi = [nm for nm in empty if R[nm]["tr"] >= 2]
    say(f"- 해 0개(정확법 · `exact` {len(R)}건): **{pct(len(empty), len(R))}** "
        f"({', '.join(empty) if empty else '없음'})")
    say(f"- 사전등록 문턱 **>= 1/3 = 33.3%** ⇒ **{'🔴 발동' if frac >= 1/3 else '미발동'}**")
    say(f"- 다차수(2차 이상) 건 **{len(multi)}/{len(R)}** 중 해 0개 **{len(empty_multi)}** "
        f"({', '.join(empty_multi) if empty_multi else '없음'})")
    if frac >= 1 / 3:
        say("- ⇒ 🔴🔴 **「다차수 건에서 평단이 매도 중 변한다」로 읽고, 복원 기반 축(`Q1-R3`·`HDR-D1`)을 «다차수 건»에 "
            "적용하는 것을 중단한다.** (`RESULTS_RECONSTRUCT_POST4.md` §6 Y3 동결 문언 — 값을 보고 정한 규칙이 아니다.) "
            "🔴 `P6-L3'`·`BUY-L5` 는 **결정 ④로 이미 종결**이라 중단 대상 목록에서 «자동으로» 빠진다.")
        say("- 🔑 중단은 «다차수 건»에만 걸린다. `first_only`(1차) 건은 전제가 다르므로 남는다 — "
            f"🔴 **이번 `exact` 는 다차수 {len(multi)}건** ⇒ 중단이 실제로 빼는 건 **{len(multi)}건**.")
    else:
        say("- ⇒ **중단 미발동** — 복원 기반 축을 다차수 건에도 적용한다.")
    if empty and all(R[nm]["tr"] == 1 for nm in empty):
        say("- 🔴 **해 0개 건이 전부 1차 체결이다** — 동결 해석문(「다차수 건에서 평단이 변한다」)과 이번 표본의 모양이 어긋난다"
            "(post7 과 같은 모양 · **발동은 문언대로 · 어긋남은 관측으로** · 해석문을 고치지 않는다).")
    if "우리로" in empty:
        say("- 🔴🔴 **우리로가 해 0개 쪽에 있다** — 두 사이클 · 두 평단(`구조차단`)이라 ***「1차 체결인데 풀리지 않았다」의 "
            "원인이 «평단 변화»일 수 있는 유일한 건***이다(두 번째 사이클의 1차 매수가 두 번째 평단). "
            "🔴 해석하지 않는다 — 포함 값 그대로 · 「우리로 제외」 값은 §14.")
    ex3 = {k: v for k, v in R.items() if k not in STRUCT_BLOCK}
    e3 = sum(1 for v in ex3.values() if not v["iv"])
    flip3 = (e3 / len(ex3) >= 1 / 3) != (frac >= 1 / 3)
    say(f"- 🔴 **「우리로 제외」 민감도**(🔒 #1-(i) · `WRC-R5` 유추): 해 0개 **{pct(e3, len(ex3))}** ⇒ "
        f"**{'발동' if e3 / len(ex3) >= 1/3 else '미발동'}** — " +
        ("🔴🔴 **주 갈래와 판정이 갈린다** ⇒ §1-5 2 문형 「재진입 의존」 · 어느 쪽도 지지로 선언하지 않는다 · "
         "`REC-Y3` 는 동결 최소 n 이 없어(#40 「—」) `P8-갈래계수` 대상 밖(`PREREG_POST8.md:338`) · "
         f"🔑 이번 `exact` 다차수 **{len(multi)}건** ⇒ 어느 갈래든 중단이 실제로 빼는 건 **{len(multi)}건**"
         if flip3 else "주 갈래와 같은 판정"))
    for k in STRUCT_BLOCK:
        if k in R:
            vv = R[k]
            say(f"- 🔴 **{k}의 해 존재는 두 가정 위의 값이다** — ① 「17%」 = 17.00 정규화(±0.5%p 표기 불확실 · §2) "
                "② 두 사이클을 한 평단으로 푼다(`WRC-R5` :435) · 실측: 구간 "
                f"**{len(vv['iv'])}** · 총 측도 **{vv['measure']:,.2f}원** · 폭 "
                f"**{'—' if vv['w'] is None else format(vv['w'], '.2f') + '%p'}** — "
                "🔴 해석하지 않는다(값 규칙 불변 · 보정 계산 0).")
    say(f"- 계열(같은 09-24 스냅샷 재계산 · §17): 이 문서의 post8 값 **{pct(len(empty), len(R))}** — "
        "post4~7 은 §17 표(동결 인쇄값 post4 1/6 → post5 4/6 → post6 5/10 → post7 2/6 과 나란히).")
    say("- 🔴 **분모 정의** — post6 까지 「신규 전건」 · post7 부터 「신규 ∧ `exact`」(PD-4) · post8 도 「신규 ∧ `exact`」. "
        "***계열 비교 때 같이 읽을 것.***")

    # ── §6. REC-Y4 ───────────────────────────────────────────────────────
    say()
    say("## §6. `REC-Y4`(기록만) — net 기준(정확 구간법) 해 개수 비교\n")
    say("| 종목 | gross 구간 개수 | gross 폭 | **net 구간 개수** | net P 범위 | net 총 측도(원) | net 폭 |")
    say("|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        ivn = v["iv_net"]
        gws = fmt_pct(v["w"])
        if ivn:
            nw = (iv_max(ivn) - iv_min(ivn)) / v["h0"] * 100
            say(f"| {nm} | {len(v['iv'])} | {gws} | **{len(ivn)}** | "
                f"{iv_min(ivn):,.2f}~{iv_max(ivn):,.2f} | {iv_measure(ivn):,.2f} | {nw:.2f}%p |")
        else:
            say(f"| {nm} | {len(v['iv'])} | {gws} | **0** | — | 0.00 | — |")
    _, y4ans, _, _ = a_y4(R)
    say()
    say(f"- ⇒ **{y4ans}**")

    # ── §7. REC-Z1 · Z2 ──────────────────────────────────────────────────
    say()
    say("## §7. `REC-Z1`(핵심) · `REC-Z2`(반증축)\n")
    z1_n = sum(1 for v in R.values() if v["under"])
    z1_frac = z1_n / len(R)
    say(f"- **`REC-Z1`**: `Δr_min` < `res` 인 건 **{pct(z1_n, len(R))}** · "
        f"문턱 **>= 1/3 = 33.3%** ⇒ **{'✅ 성립' if z1_frac >= 1/3 else '⛔ 불성립'}** · 최소 n 3 ⇒ 충족({len(R)}) "
        "(계열 §17)")
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
        " (post7: 미달군 1/1 · 충족군 1/5)")
    if ga and len(ga) == 1:
        say("- ⚠️ **격자 미달군이 1건뿐**이라 그 비율은 **분모 1** 이다. 비율로 읽지 말 것.")

    # ── §8. REC-Z3 앵커 ──────────────────────────────────────────────────
    say()
    say("## §8. `REC-Z3` — `H`(등록일 고가) < 창 최고가 인 건의 비율 (건별 인쇄 의무)\n")
    say("🔴 `H`·`L`·`HI` = `P8-빈티지`(D+1 안정 빈티지) · 창 `[D, END]` · 읽은 시각 = §0 ① · 창별 `max(updated_at)` = §0-b "
        "· 🔴 이 창은 **전 건 제도 경계를 걸친다**(§0-b 신고 줄).\n")
    say("| 종목 | `H` = 등록일 고가 | 창 최고가 `[D, 종료]` | 창 최저가 | **`H` < 창최고?** | 초과폭 | 경계 전/후 봉 |")
    say("|---|---|---|---|---|---|---|")
    z3_hit = []
    for nm, v in R.items():
        broken = v["h0"] < v["HI"]
        if broken:
            z3_hit.append(nm)
        over = f"{100*(v['HI']-v['h0'])/v['h0']:.2f}%" if broken else "—"
        wa = vint[nm][0]
        say(f"| {nm} | {v['h0']:,.0f} | {v['HI']:,.0f} | {v['L']:,.0f} | "
            f"{'🔴 **예**' if broken else '아니오'} | {over} | {wa['before']}/{wa['after']} |")
    z3_frac = len(z3_hit) / len(R)
    say()
    say(f"- **`REC-Z3` = {pct(len(z3_hit), len(R))}** "
        f"({', '.join(z3_hit) if z3_hit else '없음'}) · 문턱 **>= 1/2 = 50.0%** ⇒ "
        f"**{'🔴🔴 발동' if z3_frac >= 0.5 else '미발동'}** · 최소 n 3 ⇒ 충족({len(R)}) "
        "(계열 = 동결 인쇄값 post5 3/6 → post6 6/10 → post7 6/6 · 같은 스냅샷 재계산 §17)")
    ex8 = [nm for nm in z3_hit if nm not in STRUCT_BLOCK]
    nx8 = len([k for k in R if k not in STRUCT_BLOCK])
    say(f"- 「우리로 제외」 민감도: **{pct(len(ex8), nx8)}** ⇒ **{'발동' if len(ex8) / nx8 >= 0.5 else '미발동'}** "
        f"({'주 갈래와 같은 판정' if (len(ex8) / nx8 >= 0.5) == (z3_frac >= 0.5) else '🔴 주 갈래와 판정이 갈린다'})")
    if z3_frac >= 0.5:
        say("- ⇒ 🔴🔴 **앵커 붕괴가 «또» 재현됐다.** 앵커 재설계 사전등록은 post6 에서 이미 **의무 발생**했고 "
            "`PREREG_ANCHOR_REDESIGN.md`(동결 `ef17c4f`)로 이행됐다 ⇒ 후보 앵커 검정은 "
            "`run_anchor_redesign.py --mode post8` 이 맡는다(이 산출물은 후보 앵커를 계산하지 않는다).")
        say("- 🔴 **`HDR-D1` 은 이 붕괴로 «무효»**(`PREREG_POST6.md` §4 #52 대칭 쌍) — §12 에 그대로 적용.")
    else:
        say("- ⇒ 이번 회차 `REC-Z3` 미발동 — `HDR-D1` 무효 «승계» 여부는 §12 에 두 읽기로 적는다.")
    say("- 🔴🔴 **빈티지 신고**: 이 창은 **경계 전·후 봉이 섞인다**(§0-b) — `PREREG_POST8.md` §9 (다) 「이 조항이 틀렸다면」 "
        "행이 **`REC-Z3` 을 이름으로 지목**했다(*「혼합빈티지신고가 발동한 회차에서 … `REC-Z3` 의 값이 «경계 전 회차와 "
        "계통적으로 다르게» 움직인다」*) ⇒ 경계 전 회차(post5~7) 계열을 §17 에 같은 스냅샷으로 나란히 둔다 · "
        "「계통적」 여부는 이 산출물이 판정하지 않는다(판정 규칙이 동결돼 있지 않다 — 새 사전등록 사안).")
    say("- 🔑 `h = (S-L)/(H-L)` 는 `H` 가 천장일 때만 「저점 대비 반등폭 비율」이다 — "
        "천장이 뚫린 건에서는 `h_max` 가 1 을 넘고 HDR 틀 자체가 성립하지 않는다.")

    # ── §9. REC-Z4 ───────────────────────────────────────────────────────
    say()
    say("## §9. `REC-Z4` — `first_only` ∧ 서로 «다른» 값 레그 >= 3 · 🔴 **관측 인쇄만**\n")
    say("🔴🔴 **이 항목은 «판정하지 않는다».** 동결 문언의 귀결(= 그 자리에서 `BUY-` 계열을 연다)은 "
        "🔒 **결정 ④「`PREREG_BUYLADDER` 계열 종결·기록 보존」**(`PREREG_GRADE_TIERS.md` §5 · 동결 "
        "`342f6f0`)으로 **소멸**했다(PD-13). **조건 충족 사실과 건수만 인쇄한다.**\n")
    say("| 종목 | 정밀도 | first_only | 레그 | 서로 다른 값 개수 | Z4 조건 충족 | 플래그 |")
    say("|---|---|---|---|---|---|---|")
    z4 = []
    for nm, v in R.items():
        if not v["fo"]:
            continue
        d = len(set(v["legs"]))
        hit = d >= 3
        if hit:
            z4.append(nm)
        say(f"| {nm} | exact | 예 | {v['legs']} | **{d}** | {'🟢 **충족**' if hit else '아니오'} | "
            f"{'🔴 `구조차단`' if nm in STRUCT_BLOCK else '—'} |")
    for t in approx:
        if not t[FO]:
            say(f"| _{t[NM]}_ | _approx_ | _아니오({t[TR]}차)_ | _{t[LEGS]}_ | _{len(set(t[LEGS]))}_ | _대상 아님_ | — |")
            continue
        d = len(set(t[LEGS]))
        say(f"| _{t[NM]}_ | _approx_ | _예_ | _{t[LEGS]}_ | _{d}_ | "
            f"_{'충족(민감도)' if d >= 3 else '아니오'}_ | — |")
    fo_new = [nm for nm, v in R.items() if v["fo"]]
    z4x = [nm for nm in z4 if nm not in STRUCT_BLOCK]
    say()
    say(f"- **`REC-Z4` 조건 충족(관측): {len(z4)}건** ({', '.join(z4) if z4 else '없음'}) · 「우리로 제외」 {len(z4x)}건 — "
        "🔴 **판정 없음**(결정 ④) · 등급 이름을 미리 고르지 않는다(PD-16).")
    say(f"- `first_only` **`exact` {len(fo_new)}건** ({', '.join(fo_new)}) + "
        f"`approx` {sum(1 for t in approx if t[FO])}건(민감도).")
    say("- 🔴 **충돌 신고(§1-8 형식 · post7 승계)**: `REC-Z4` 동결 문언 ↔ 결정 ④. **사장님 결정이 이긴다** — "
        "`PREREG_ANCHOR_REDESIGN.md` §5-2 가 *「④가 「종결」로 결정되면 `BUY-L5` 재개 조항은 "
        "**자동 소멸**한다」*고 **미리** 적어 두었고, 그 뒤 `342f6f0` 이 결정을 기록했다.")

    # ── §10. BUY 계열 종결 ───────────────────────────────────────────────
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

    # ── §17 을 먼저 계산(§11 참조값 · §5/§7/§8 계열) ─────────────────────
    ref_post7 = []
    post_sets = [
        ("post4", [(t[0], t[1], t[2], t[3], t[4], t[5], "—", "—", False) for t in P4M.TARGETS], None),
        ("post5", [(t[0], t[1], t[2], P5M.END, t[3], t[4], t[5], t[6], t[7]) for t in P5M.TARGETS], P5M.END),
        ("post6", [(t[0], t[1], t[2], P6M.END, t[3], t[4], t[5], t[6], t[7]) for t in P6M.TARGETS], P6M.END),
        ("post7", [(t[NM], t[CODE], t[D0], P7M.END, t[LEGS], t[TR], t[PRESET], t[LABEL], t[FO])
                   for t in P7M.TARGETS if t[PREC] == "exact"], P7M.END),
    ]
    SR = {}
    for tag, items, _end in post_sets:
        Rp = {}
        umax = None
        for nm, code, d0, d1, legs, tr, preset, label, fo in items:
            v = core(cur, code, d0, d1, legs)
            if v is None:
                continue
            v.update(tr=tr, preset=preset, label=label, fo=fo)
            Rp[nm] = v
            w = win_stats(cur, code, d0, d1)
            umax = w["umax"] if umax is None or w["umax"] > umax else umax
        SR[tag] = (Rp, items, umax)
        if tag == "post7":
            ref_post7 = [(f"post7 {nm}", v["b1"]) for nm, v in Rp.items() if v["fo"] and v["iv"]]
    # post6 아난티 · post5 삼양 — `first_only` 참조값(같은 스냅샷 재계산)
    ref_old = []
    for tag, nm in (("post6", "아난티"), ("post5", "삼양바이오팜")):
        v = SR[tag][0].get(nm)
        if v is not None and v["iv"]:
            ref_old.append((f"{tag} {nm}", v["b1"]))

    # ── §11. Q1-R3 ───────────────────────────────────────────────────────
    say()
    say("## §11. `Q1-R3` — `b1` 구간이 직전 글 값과 부호·자릿수가 같은가 (구간 겹침 여부만)\n")
    say("A-6: 다차수 건의 `1-P/H` 는 「1차 밴드」가 아니라 「전 차수 평단」이다 ⇒ **범주 오류**(post4 §2 유지). "
        + ("`REC-Y3` 중단도 다차수 건에 겹친다." if frac >= 1 / 3 else "") +
        " 🔴 직전 글·그 전 참조값은 **같은 09-24 스냅샷에서 재계산**했다(§17 · 옮겨 적기 아님).\n")
    say("| 건 | 구분 | `b1` 구간 | 부호 | 자릿수(정수부) | 플래그 |")
    say("|---|---|---|---|---|---|")
    r3 = []
    for nm in fo_new:
        v = R[nm]
        fl = "🔴 `구조차단`" if nm in STRUCT_BLOCK else "—"
        if not v["iv"]:
            say(f"| {nm} | `first_only`(post8 `exact`) | ⛔ 해 0개 | — | — | {fl} |")
            continue
        r3.append(nm)
        lo_b, hi_b = v["b1"]
        sg = sign_of(v["b1"])
        say(f"| {nm} | `first_only`(post8 `exact`) | **[{lo_b:+.2f}%, {hi_b:+.2f}%]** | "
            f"{'🔴 **부호 걸침**' if sg == '걸침' else sg} | {len(str(int(abs(hi_b))))} 자리 | {fl} |")
    for lab, b in ref_post7 + ref_old:
        say(f"| _{lab}_ | _`first_only`(09-24 재계산)_ | _[{b[0]:+.2f}%, {b[1]:+.2f}%]_ | _{sign_of(b)}_ | "
            f"_{len(str(int(abs(b[1]))))} 자리_ | — |")
    say(f"| 솔트룩스(인용) | `first_only` | [{QUOTED_SOLTLUX[0]:+.2f}%, {QUOTED_SOLTLUX[1]:+.2f}%] | 걸침 | 1 자리 | "
        "인용 — `RESULTS_RECONSTRUCT_POST7_NUMBERS.md:216`(post4~7 표본 밖 · 점법 시대 값 · 재계산 안 함) |")
    say("| 케이엔알(인용) | `full` | `b_last` <= +36.76% | 양 | 2 자리 | 인용 — `RESULTS_RECONSTRUCT_POST7_NUMBERS.md:217` |")
    say()
    say(f"- 최소 n **3**(`PREREG_POST6.md` §4 #54) — 두 읽기: "
        f"`first_only` **건수 {len(fo_new)}**(⇒ {'충족' if len(fo_new) >= 3 else '미달'}) vs "
        f"**측정 가능 {len(r3)}건**(⇒ {'충족' if len(r3) >= 3 else '미달'}) · "
        "🔴 ⛔ 조건 ②의 단위는 `PREREG_POST6.md:743-746`(2026-09-10 B-2)이 **「건」 단위로 못박았다** — "
        "측정 가능 읽기가 그 단위 규약의 귀결이다(건수 읽기는 병기).")
    if r3:
        for lab, b in ref_post7 + ref_old + [("솔트룩스(인용)", QUOTED_SOLTLUX)]:
            ov = sum(1 for nm in r3 if overlap(R[nm]["b1"], b))
            say(f"  - 구간 겹침: {lab} `[{b[0]:+.2f}, {b[1]:+.2f}]` 과 **{ov}/{len(r3)}**")
        say("- 부호·자릿수: " + ", ".join(
            f"{nm} {sign_of(R[nm]['b1'])}/{len(str(int(abs(R[nm]['b1'][1]))))} 자리({R[nm]['b1'][1]:+.2f}%)"
            for nm in r3))
    if len(r3) >= 3:
        say("- ⇒ 🟡 **`Q1-R3` = 겹침 여부 «기록»**(`PREREG_Q1_V2.md` §3 판정 규칙 = "
            "*「R3 은 구간 겹침 여부만」* — 지지/기각을 선언하는 항목이 아니다).")
    else:
        say(f"- ⇒ ⛔ **`Q1-R3` 판정 불가**(측정 가능 읽기 · 건 단위) — `first_only` **측정 가능 {len(r3)} < 3**. "
            "🟡 「건수 읽기」를 택하면 위 겹침 값이 R3 의 «기록»이 된다 — "
            "🔴 어느 쪽이든 **R3 은 지지/기각을 선언하는 항목이 아니라** 결론은 같다.")

    # ── §12. HDR-D1 ──────────────────────────────────────────────────────
    say()
    say("## §12. `HDR-D1` — `HDR 60%` 건의 `h_max` 중앙값이 0.50~0.70 인가\n")
    say("`h_max = (S_max - L)/(H - L)` · `H` = 등록일 고가 · `L` = min(low) over `[D, 종료]` · "
        "`S_max = P*(1+r1)` · 분모 = 프리셋 `HDR 60%` 건(A-4)\n")
    say("| 종목 | 프리셋 | 차수 | 라벨 | H | L | 창 최고가 | H == 창최고? | P 범위 | `h_max` 범위 | 폭 | "
        "Y3 중단 | D1 분모 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    d1mids = []
    for nm, v in R.items():
        stop = (v["tr"] >= 2 and frac >= 1 / 3)
        aflag = "예" if v["h0"] >= v["HI"] else "🔴 **아니다**"
        inden = (v["preset"] == "HDR60" and not stop)
        den_s = "포함" if inden else ("🔴 **밖**(프리셋)" if v["preset"] != "HDR60" else "🔴 밖(Y3 중단)")
        if not v["iv"]:
            say(f"| {nm} | {v['preset']} | {v['tr']}차 | {v['label']} | {v['h0']:,.0f} | {v['L']:,.0f} | "
                f"{v['HI']:,.0f} | {aflag} | **해 없음** | — | — | {'🔴' if stop else '—'} | {den_s} |")
            continue
        r1_ = v["legs"][0] / 100.0
        smin, smax = v["pmin"] * (1 + r1_), v["pmax"] * (1 + r1_)
        hlo, hhi = (smin - v["L"]) / (v["h0"] - v["L"]), (smax - v["L"]) / (v["h0"] - v["L"])
        say(f"| {nm} | {v['preset']} | {v['tr']}차 | {v['label']} | {v['h0']:,.0f} | {v['L']:,.0f} | "
            f"{v['HI']:,.0f} | {aflag} | {v['pmin']:,.2f}~{v['pmax']:,.2f} | "
            f"**{hlo:.3f}~{hhi:.3f}** | {hhi-hlo:.3f} | {'🔴 중단' if stop else '—'} | {den_s} |")
        if inden:
            d1mids.append((nm, (hlo + hhi) / 2, hhi - hlo, v["label"]))
    say()
    say(f"- `REC-Y3` 중단{' 발동 ⇒ 다차수 건 제외' if frac >= 1/3 else ' 미발동'} · "
        f"프리셋 분모 밖 **{sum(1 for v in R.values() if v['preset'] != 'HDR60')}건** · "
        f"해 없음 **{sum(1 for v in R.values() if not v['iv'])}건** · 남는 분모 **{len(d1mids)}건** "
        f"({', '.join(n for n, _, _, _ in d1mids) if d1mids else '없음'})")
    for n_, m_, w_, lb in d1mids:
        say(f"  - {n_}({lb}): 중점 **{m_:.3f}** · 폭 **{w_:.3f}**")
    if z3_frac >= 0.5:
        say("- ⇒ 🔴🔴 **`HDR-D1` 무효** — 이번 회차 `REC-Z3` 앵커 붕괴(§8)가 발동했다"
            "(`PREREG_POST6.md` §4 #52 대칭 쌍 *「`REC-Z3` 앵커 붕괴 시 무효」*). "
            "아래 중앙값은 **인쇄만** 하고 판정으로 쓰지 않는다. 🟢 **「무효 승계」 읽기와 「그 회차 발동」 읽기가 "
            "같은 답**이다(이번 회차가 스스로 발동했다 — 승계를 물을 필요가 없다).")
    else:
        say("- 🔴 **모호 — 「무효 승계」 여부**: #52 문언 *「`REC-Z3` 앵커 붕괴 시 무효」*는 회차 조건으로 읽힌다(이번 회차 "
            "미발동 ⇒ 무효 사유 없음). 반면 `PREREG_ANCHOR_REDESIGN.md` §5-2 는 채택 «뒤»에야 `HDR-` `h` 축을 **재개**한다고 "
            "적었다(재개 전 = 정지 상태) ⇒ 두 읽기를 둘 다 적는다 · 🔴 판정 불가·모호.")
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
        sl = [n_ for n_, _, _, lb in d1mids if lb in ("SL", "MANUAL")]
        if sl:
            say(f"- (민감도 A-4) 라벨 `SL`·`MANUAL` 건: {', '.join(sl)} — 제외 시 분모 {len(d1mids) - len(sl)}")

    # ── §13. P6-R1' ──────────────────────────────────────────────────────
    say()
    say("## §13. `P6-R1'` — `first_only` DD < `full` DD (누적 · 양쪽 각 n >= 2)\n")
    say("`H4`=max(high) over `[D-4,D]` · `H5`=`[D-9,D]` · `H6`=`[D-19,D]` · "
        "`DD` = 1 - min(low over `[D, 종료]`) / H · 🔴 `H6` 창 = `[D−19, D]`(§0-b · 안 걸침) · `L` 창 = `[D, END]`(걸침)\n")
    say("| 건 | 구분 | 등록일 | 종료 | `DD(H4)` | `DD(H5)` | `DD(H6)` | 플래그 |")
    say("|---|---|---|---|---|---|---|---|")
    fo_dd = []
    for nm in fo_new:
        v = R[nm]
        row = [dd_h(cur, v["code"], v["d0"], END, k) for k in (5, 10, 20)]
        fo_dd.append((nm, row))
        say(f"| {nm} | `first_only`(신규 `exact`) | {v['d0']} | {END} | "
            f"{row[0]:.2f}% | {row[1]:.2f}% | {row[2]:.2f}% | {'🔴 `구조차단`' if nm in STRUCT_BLOCK else '—'} |")
    knr = [dd_h(cur, "199430", "2026-07-28", "2026-08-14", k) for k in (5, 10, 20)]
    say(f"| 케이엔알시스템 | `full`(누적 · 직전 글들) | 2026-07-28 | 2026-08-14 | "
        f"{knr[0]:.2f}% | {knr[1]:.2f}% | {knr[2]:.2f}% | — |")
    say()
    say("- 🔴 **이번 글 신규 `full` = 0건**(PD-13 *「`P6-R1′` — `full` 신규 **0**(「전 차수 체결」 서술 0) ⇒ 관측만」*)")
    say(f"- 누적 n: `first_only` **{len(fo_dd)}**(신규 `exact`) · `full` **1**(케이엔알)")
    say("- 문턱 **양쪽 각 n >= 2**(`PREREG_POST6.md` §3-3) ⇒ `full` 1 < 2 ⇒ "
        "⛔ **판정 안 함 · 관측만.**")
    dirn = sum(1 for _, row in fo_dd for a, b in zip(row, knr) if a < b)
    tot = len(fo_dd) * 3
    say(f"- (관측) 방향 일치(`first_only` DD < `full` DD) **{dirn}/{tot}** — "
        f"신규 `exact` {len(fo_dd)}건 × 세 H 정의.")
    say(f"- 🟢 케이엔알 재계산 **{knr[0]:.2f}%** — 동결값 **36.76%** 와 "
        f"{'일치' if f'{knr[0]:.2f}' == '36.76' else '🔴 **불일치**'}(계기 점검).")

    # ── §14. 갈래 (D-5) ──────────────────────────────────────────────────
    say()
    say("## §14. 🆕 `D-5` `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)` (PD-23 표의 `REC-` 갈래 전부)\n")
    say("규칙(`PREREG_POST8.md:337-342`): **최소 n 은 그 축의 동결문 값 그대로**(`PREREG_POST6.md` §4 #38~#54) · "
        "최소 n 미달 갈래는 **인쇄 의무 · 「갈렸다」의 근거로 쓰지 않는다** · 채운 갈래가 **2 이상이고 답이 갈리면** "
        "`:340` 「갈렸다」 · **1개면 그 답** · **0개면** `:341` · 동결문에 최소 n 이 **없는** 항목은 계수 대상 밖(`:338`). "
        "🔴 등급 칸은 §6 단계(여기서 등급 이름을 쓰지 않는다).\n")
    trunc = set()
    for nm, v in R.items():
        s19, n19 = d19_start(cur, v["code"], v["d0"])
        n5, _ = win5_count(cur, v["code"], v["d0"])
        v["n19"], v["n5"] = n19, n5
        if n19 < 20 or n5 < 5:
            trunc.add(nm)
    reent_ex = {nm for nm, v in R.items() if v["reent"]}
    B = [
        ("주(우리로 포함 · `exact` 4)", dict(R)),
        ("「우리로 제외」(`WRC-R5` 유추 · 🔒 #1-(i))", {k: v for k, v in R.items() if k not in STRUCT_BLOCK}),
        (f"§1-5 재진입 제외(등록 자체 2번째 · exact {len(reent_ex)}건 ⇒ "
         f"{'항등' if not reent_ex else '제외'})", {k: v for k, v in R.items() if k not in reent_ex}),
        (f"절단 제외(`[D−19,D]`<20 또는 창5<5 · {len(trunc)}건 ⇒ {'항등' if not trunc else '제외'})",
         {k: v for k, v in R.items() if k not in trunc}),
    ]
    refs_q = ref_post7
    ITEMS = [
        ("`REC-Y1`", "레그≥4 3건(#38)", lambda S: a_y1(S)),
        ("`REC-Y2`", "좁은 건 ≥1(#39)", lambda S: a_y2(S)),
        ("`REC-Y3`", "—(#40 · 계수 대상 밖)", lambda S: a_y3(S)),
        ("`REC-Y4`", "—(#41 · 기록)", lambda S: a_y4(S)),
        ("`REC-Z1`", "3(#42)", lambda S: a_z1(S)),
        ("`REC-Z2`", "3(#43)", lambda S: a_z2(S)),
        ("`REC-Z3`", "3(#44)", lambda S: a_z3(S)),
        ("`REC-Z4`", "—(#45 · 관측)", lambda S: a_z4(S)),
        ("`Q1-R3`(측정 가능 읽기)", "3(#54)", lambda S: a_q1r3(S, refs_q, "측정 가능")),
        ("`Q1-R3`(건수 읽기)", "3(#54)", lambda S: a_q1r3(S, refs_q, "건수")),
        ("`HDR-D1`", "3(#52)", lambda S: a_hdr(S)),
        ("`P6-R1'`", "양쪽 각 2(#53)", lambda S: a_r1(S)),
    ]
    # 판정을 «내는» 항목인가 — `REC-Y4`(기록만 · #41)·`REC-Z4`(관측만 · 결정 ④)는 판정이 없다 ⇒ 「재진입 의존」 대상 밖.
    NO_VERDICT = {"`REC-Y4`", "`REC-Z4`"}
    # approx 포함 갈래 — 두 approx 건의 7×7 = 49 조합(D-3 우선 · 계수 밖 · 인쇄만)
    combos = list(itertools.product(AX["헥토파이낸셜"], AX["코데즈컴바인"]))
    say("| 항목 | 최소 n(동결문) | 갈래 | n | 답 | 최소 n 충족? |")
    say("|---|---|---|---|---|---|")
    summary = []
    for lab, mn, fn in ITEMS:
        res = []
        for bname, S in B:
            n, ans, meets, cat = fn(S)
            res.append((bname, n, ans, meets, cat))
            say(f"| {lab} | {mn} | {bname} | {n} | {ans} | "
                f"{'— (대상 밖)' if meets is None else ('✅' if meets else '❌ 미달')} |")
        cats, ns = {}, []
        for (dh, vh), (dk, vk) in combos:
            n, ans, meets, cat = fn(with_ax(R, vh, vk))
            cats[cat] = cats.get(cat, 0) + 1
            ns.append(n)
        cat_s = " · ".join(f"{k} {c}/{len(combos)}" for k, c in sorted(cats.items()))
        say(f"| {lab} | {mn} | _`approx` 포함(헥토·코데즈 7×7 조합 · `D-3` 우선)_ | _{min(ns)}~{max(ns)}_ | "
            f"_{cat_s}_ | _— (`D-3`: `approx` 로 최소 n 을 채우지 않는다 · 계수 밖)_ |")
        summary.append((lab, mn, res))
    say()
    say("**계수 결과**(`approx` 갈래 제외 · 항등 갈래는 주와 같은 답으로 센다)\n")
    say("| 항목 | 최소 n 충족 갈래 수 | 충족 갈래의 답 | `P8-갈래계수` | 주 ↔ 「우리로 제외」 답 | §1-5 「재진입 의존」(`WRC-R5` 유추) |")
    say("|---|---|---|---|---|---|")
    split_items = []
    re_items = []
    for lab, mn, res in summary:
        q = [r for r in res if r[3]]
        qa = sorted(set(r[4] for r in q))
        gc, is_split = gc_status(res)
        if is_split:
            split_items.append(lab)
        re_dep, is_re = re_dep_status(res, lab not in NO_VERDICT)
        if is_re:
            re_items.append(lab)

        say(f"| {lab} | {len(q)} | {' · '.join(qa) if qa else '—'} | {gc} | {res[0][4]} ↔ {res[1][4]} | {re_dep} |")
    say()
    say(f"- 🔴 **「갈렸다」 항목: {len(split_items)}개** ({', '.join(split_items) if split_items else '없음'}) — "
        "등급은 §6 단계에서 그 축 문언대로(PD-16 · 여기서 이름을 고르지 않는다).")
    say(f"- 🔴 **§1-5 「재진입 의존」(주 ↔ 「우리로 제외」 판정이 갈림 · `WRC-R5` 유추) 항목: {len(re_items)}개** "
        f"({', '.join(re_items) if re_items else '없음'}) — 🔴 `P8-갈래계수`(동결 최소 n 이 있는 항목의 계수)와 "
        "**다른 문형**이다: 최소 n 이 «없는» 항목(`REC-Y3`)도 여기에 걸린다(모호 · §18 3번).")
    say(f"- 🔴 **§1-5 재진입(등록 자체가 두 번째 사이클) 제외 갈래 = {'항등' if not reent_ex else '제외 있음'}**"
        f"(exact 안 §1-5 재진입 {len(reent_ex)}건 — 원익은 `none` · 헥토·코데즈는 `approx`) · "
        f"**절단 제외 갈래 = {'항등' if not trunc else '제외 있음'}**(`[D−19,D]` 20/20 · 창5 5봉 — PD-12) — **항등을 명시 인쇄**한다.")
    say("- 🔴 **`approx` 갈래와 재진입 갈래를 합치지 않았다**(PD-3 마지막 줄) — 헥토·코데즈는 두 민감도에 동시에 걸린다.")
    say("- 🔴 **`P6-PRIOR_CYCLE_IN_WINDOW`**(§1-5 3 · 구조 차단 플래그): 판정 분모(exact) 안 **0**(우리로 = 측정 등록이 첫 사이클) · "
        "글 전체 1 인 자리는 `approx` 갈래뿐(헥토 " +
        f"{sum(v['prior_flag'] for _, v in AX['헥토파이낸셜'])}/7 · 코데즈 {sum(v['prior_flag'] for _, v in AX['코데즈컴바인'])}/7 · §1-b) — "
        "⚠️ `WRC-R5` `구조차단`(우리로 1)과 **다른 플래그**다(PD-3).")

    # ── §15. D-3 ─────────────────────────────────────────────────────────
    say()
    say("## §15. 🆕 `D-3` `P8-approx의존신고` (`PREREG_POST8.md:249` · 기계 검사 `:253`)\n")
    n_incl_y1 = y1n + len(ax_y1)
    rows_d3 = []
    for lab, mn, fn in ITEMS:
        mnv = {"`REC-Y1`": 3, "`REC-Z1`": 3, "`REC-Z2`": 3, "`REC-Z3`": 3, "`Q1-R3`(측정 가능 읽기)": 3,
               "`Q1-R3`(건수 읽기)": 3, "`HDR-D1`": 3}.get(lab)
        if mnv is None:
            continue
        ne = fn(R)[0]
        ni_all = [fn(with_ax(R, vh, vk))[0] for (_, vh), (_, vk) in combos]
        ni = max(ni_all)
        rows_d3.append((lab, mnv, ne, ni, d3_hit(mnv, ne, ni)))
    hit_axes = [r[0] for r in rows_d3 if r[4]]
    say(f"**「`approx` 포함 시 최소 n 이 차는 축: {', '.join(hit_axes) if hit_axes else '없음'} · "
        f"`exact` 분모 {y1n} / `approx` 포함 분모 {n_incl_y1}」**(`REC-Y1` · PD-21 표 행)\n")
    say("| 항목 | 최소 n | `n_exact` | `n_incl`(갈래 최대) | `n_incl ≥ 최소 n > n_exact`? |")
    say("|---|---|---|---|---|")
    for lab, mnv, ne, ni, hit in rows_d3:
        say(f"| {lab} | {mnv} | {ne} | {ni} | {'🔴 **예** ⇒ 열지 않는다' if hit else '아니오'} |")
    say()
    say("- 🔴 **기계 검사 결과**: `n_incl ≥ 최소 n > n_exact` 인 항목 **" + (", ".join(hit_axes) if hit_axes else "0개") +
        "** ⇒ " + ("그 항목은 `approx` 로만 열리므로 **열지 않는다**(`:250`)." if hit_axes else
                   "신고 대상 없음 — 구성 예고(PD-21 「없음」)와 같다.") +
        " `REC-Y4`·`REC-Y3`·`REC-Z4`·`P6-R1'` 는 동결 최소 n 이 없거나(—) `full` 축이라 표 밖.")
    say("- 🔴 `approx` 포함 값은 **판정 언어 없이** 민감도로만 인쇄했다(§1-b · §14 기울임 행).")

    # ── §16. 봉수 정합 · 절단 가드 ───────────────────────────────────────
    say()
    say("## §16. 봉수 표기 정합 (N8 승계 — «직전/포함»을 반드시 붙인다) · 절단 가드\n")
    say("| 종목 | 등록일 | DB 최초 봉 | 등록일 «직전» 봉수(σ₂₀ 용 · 최대 21) | 등록일 «포함» 봉수 | "
        f"창 `[D, {END}]` 봉수 | `[D-19, D]` 봉수(등록일 포함) | 창 `[D-19, D+4]` 봉수 | 창5 `[D, D+4]` |")
    say("|---|---|---|---|---|---|---|---|---|")
    for nm, v in R.items():
        cur.execute("SELECT min(date), count(*) FROM daily_prices WHERE stock_code=%s "
                    "AND date <= %s", (v["code"], v["d0"]))
        mn, inc = cur.fetchone()
        s, n = sigma20(cur, v["code"], v["d0"])
        wbn = len(win_bars(cur, v["code"], v["d0"], 19, 4))
        say(f"| {nm} | {v['d0']} | {mn} | {n} | {inc} | {v['nbars']} | {v['n19']}/20 | {wbn} | "
            f"{'완전' if v['n5'] >= 5 else '🔴 **' + str(v['n5']) + '봉 = 절단**'} |")
    t19 = sum(1 for v in R.values() if v["n19"] < 20)
    t5 = sum(1 for v in R.values() if v["n5"] < 5)
    code_of = {t[NM]: t[CODE] for t in approx}
    ax5_items = sorted({nm for nm in APPROX_BRANCHES for d, _ in AX[nm]
                        if win5_count(cur, code_of[nm], d)[0] < 5})
    say()
    say(f"- 🔴 **`P6-절단가드-A`**(창 `[D-19, D]` 봉수 < 20) 분자 = **{t19}** ⇒ **{pct(t19, len(R))} "
        f"{'≥' if t19 / len(R) >= 1/3 else '<'} 1/3 ⇒ {'🔴 발동' if t19 / len(R) >= 1/3 else '미발동'}**(산술 인쇄 · PD-12).")
    say(f"- 🔴 **`P6-창5절단가드-A`**(창5 절단 건 / **이번 글 신규 건**) = 주 분모 **{t5 + len(ax5_items)}/7** · "
        f"`exact` 갈래 **{t5}/{len(R)}** ⇒ 둘 다 < 1/3 ⇒ **미발동 · 분모 갈래: 갈리지 않음**(PD-25 · 원익은 D 가 없어 "
        "분자에 들 수 없다 — PD-12 의 「09-03」 독법 참고값은 5봉 완전) — 🔴 이 가드는 `LAD-` 축 값이며 "
        "이 산출물 판정에 들어가지 않는다(post6 §17 관용 승계) · 2회 연속 계수는 `LAD-` 레인(`D-7`).")
    say("- 🔴 **혼동 방지**: `REC-` 축의 판정 창은 `[등록일, " + END + "]` **전체**라 **절단 개념이 다르다** — "
        "창5 열은 `LAD-`·`ANC-` 축이 쓰는 값이다.")
    say("- 🔴 **60봉 특징(`f9_newhigh`)·C-17 NaN 규약**은 `run_selection_post8.py` 가 맡는다(이 산출물은 60봉 특징을 쓰지 않는다).")

    # ── §17. post4~7 같은 스냅샷 재계산 ──────────────────────────────────
    say()
    say("## §17. 누적 계열 — post4~7 표본을 **같은 스냅샷에서 재계산**(공통 §4-11) · 동결 인쇄값은 대조 열\n")
    say("🔴 **판정은 각 글의 동결 판정 그대로다** — 이 표는 소급 재판정이 아니라 **같은 잣대·같은 스냅샷의 계열**이다 "
        "(*소급 = 탐색* · `PREREG_POST8.md` 각 절 (라) 「post7 소급 금지」). 창·대상·레그 = 각 글 스크립트의 동결 상수"
        "(`run_reconstruct_post4/5/6/7.py` `TARGETS`·`END` · post4 는 건별 종료일 · post7 은 `exact` 6).\n")
    say("| 글 | 창 종료 | 분모 | `REC-Y3` 재계산 | 동결 | `REC-Y4` net 재계산 | 동결 | `REC-Z1` 재계산 | 동결 | "
        "`REC-Z3` 재계산 | 동결 | 창 `max(updated_at)` |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for tag, (Rp, items, umax) in SR.items():
        n = len(Rp)
        e = sum(1 for v in Rp.values() if not v["iv"])
        en = sum(1 for v in Rp.values() if not v["iv_net"])
        z1 = sum(1 for v in Rp.values() if v["under"])
        z3 = sum(1 for v in Rp.values() if v["h0"] < v["HI"])
        fz = FROZEN[tag]
        endv = {"post4": "건별(08-21)", "post5": P5M.END, "post6": P6M.END, "post7": P7M.END}[tag]

        def cmp(val, froz):
            if froz is None:
                return "—(당시 미정의)"
            return f"{froz} {'✅' if val == froz else '🔴 **다름**'}"
        say(f"| {tag} | {endv} | {n} | **{e}/{n}** | {cmp(f'{e}/{n}', fz['y3'])} | {en}/{n} | "
            f"{cmp(f'{en}/{n}', fz['y4n'])} | {z1}/{n} | {cmp(f'{z1}/{n}', fz['z1'])} | "
            f"**{z3}/{n}** | {cmp(f'{z3}/{n}', fz['z3'])} | {umax} |")
    say(f"| **post8** | {END} | {len(R)} | **{len(empty)}/{len(R)}** | (이 문서) | "
        f"{sum(1 for v in R.values() if not v['iv_net'])}/{len(R)} | (이 문서) | {z1_n}/{len(R)} | (이 문서) | "
        f"**{len(z3_hit)}/{len(R)}** | (이 문서) | {max(vint[nm][0]['umax'] for nm in R)} |")
    say()
    for tag, (Rp, items, umax) in SR.items():
        say(f"- {tag} 건별 — 해 0개: " + (", ".join(nm for nm, v in Rp.items() if not v["iv"]) or "없음") +
            " · 격자 미달: " + (", ".join(nm for nm, v in Rp.items() if v["under"]) or "없음") +
            " · `H` < 창최고: " + (", ".join(nm for nm, v in Rp.items() if v["h0"] < v["HI"]) or "없음"))
    say("- 동결 인쇄값 출처: " + " · ".join(f"{k}: {v['src']}" for k, v in FROZEN.items()))
    say("- 🔴 **「다름」이 있으면** 원인은 DB 스냅샷 이동(백필·재기록)이거나 잣대 차이다 — **맞추지 않는다**(계열 규칙: "
        "*숫자가 문서마다 다르면 «원인 규명»이 먼저다*). 동결 판정은 그대로 둔다.")
    say("- 🔴 **분모 정의가 글마다 다르다** — post4~6 「신규 전건」(= `exact`) · post7·post8 「신규 ∧ `exact`」(PD-4).")
    say("- 🔴 **제도 경계**: post4~7 창은 전부 09-14 «전» · post8 창은 «걸침»(§0-b) — "
        "***이 계열은 두 제도를 섞는다***(`PREREG_POST8.md` §14 · 분모를 쪼개지 않는다 — 쪼개려면 새 사전등록).")

    # ── §18. 처음 정한 문턱 · 모호 지점 · 충돌 ───────────────────────────
    say()
    say("## §18. 「처음 정한 문턱」에 걸렸나 · 모호 지점 · 충돌 신고\n")
    say("| 문턱 | 출처 | 이번 글에서 «걸렸나» |")
    say("|---|---|---|")
    say("| **n >= 2** (`P6-R1'` 양쪽 각) | `PREREG_POST6.md` §3-3 | "
        "🔴 **걸렸다** — `full` 누적 1건이라 이 문턱 «때문에» 판정을 안 한다(3글 연속) |")
    say("| `REC-Z5` **0.022** 판정 / 0.020 민감도 | `PREREG_EXIT_V2.md` §2 · `PREREG_POST6.md` §1-7 | "
        + (f"🔴 **걸렸다** — 두 문턱이 {len(split)}건에서 분류를 가른다(「문턱 민감」)"
           if split else "**안 걸렸다** — 두 문턱에서 분류 동일") + " |")
    say("| 최소 n **3** (`REC-Y1`) | `PREREG_POST6.md` §4 #38 | "
        + ("**안 걸렸다** — `exact` 레그>=4 가 3 ≥ 3 (「우리로 제외」 갈래는 2 < 3 — 인쇄만)"
           if y1n >= 3 else "🔴 **걸렸다**") + " |")
    say("| **`frac_in` 0.5** · **A-7 0.25·과반** | `PREREG_POST6.md` §3-4·§3-5 | "
        "🔒 **해당 없음** — 결정 ④로 그 축들이 종결됐다(계산 0회) |")
    say()
    say("### 모호 지점 · 충돌 신고 (양쪽 인쇄 · 어느 쪽도 규칙으로 고르지 않는다)\n")
    say("1. 🔴🔴 **`REC-` 창이 두 문서에서 다르다**(§1-8 형식) — `PREREG_POST8.md:546` `[D−19, D]` ↔ "
        "`PREREG_ANCHOR_REDESIGN.md:115-124` `[D, END]`. **읽기**: 이 레인은 두 창을 **둘 다 쓴다**(§0-b) ⇒ 두 창 다 "
        "읽은 시각·걸침을 인쇄했다. **대안**: 한 창만 인쇄 — 버렸다(더 적게 인쇄하는 쪽 · 바꿔 쓰는 일). "
        "발동 여부는 안 바뀐다(`[D, END]` 가 발동 · PD-27 (바)).")
    say("2. 🔴 **`D-9` ① ↔ byte 결정론**(§1-8 형식) — `PREREG_POST8.md:544` 「쿼리 실행 시각」 인쇄 의무 ↔ "
        "`RESULTS_SECTOR_POST7_NUMBERS.md:426`·`regen_gate.py --rerun` byte-diff(벽시계를 산출물에 적으면 자기 자신을 "
        "재현할 수 없다). **읽기**: 「이 DB 지문을 처음 읽은 실행의 시각」을 인쇄하고 지문이 같은 재실행은 그 값을 "
        "다시 쓴다(`reconstruct_post8/query_stamp.json`). **대안**: 벽시계 그대로(재실행 byte 불일치) · stdout 전용"
        "(D-9 무효). 🔴 **`D-9` ②(`max(updated_at)`)도 다음 sweep 뒤 재실행에서는 반드시 바뀐다** — 그건 이 절충과 무관한 "
        "동결 규칙의 귀결이다(관리자 `--rerun` 단계에서 볼 자리).")
    say("3. 🔴 **우리로의 「우리로 제외」 갈래의 판정 효과** — `REC-` 는 A-9(flag 만) + `WRC-R5` 유추(PD-3 ③ (i) · 🔒 #1). "
        "`WRC-R5` 는 「판정을 가르면 ⛔ `WRC-V1`」인데 `REC-` 에는 그 이름이 없다 ⇒ **§1-5 2 「재진입 의존」 문형**으로 "
        "적고(§14 끝 열) · `P8-갈래계수`(`:340`)를 같은 표에 둔다. 두 문형이 다른 답을 주는 자리는 §14 표가 보인다.")
    say("4. 🔴 **우리로 「17%」 소수 0자리**(PD-10 1) — 17.00 으로 **보정하지 않은 게 아니라 원장이 정규화했다**(`b302f7f` · "
        "`verify_ledger_post8` 선언). 잔차·해 존재 해석에 **±0.5%p 한계**를 §2 에 박았다 · 값 규칙 불변.")
    say("5. 🔴 **`REC-Y3` 의 분모 정의**가 post7 부터 「신규 ∧ `exact`」 — post4~6 계열과 **이어 붙일 때** 같이 읽는다(§17).")
    say("6. 🔒 **`REC-Z4` 의 귀결이 결정 ④로 소멸했다** — 조건 충족 건수(§9)만 남겼고 등급 이름을 미리 고르지 않았다(PD-16).")
    say("7. 🔴 **`Q1-R3` 두 읽기** — 건 단위 규약(`PREREG_POST6.md:743-746`)이 있어 측정 가능 읽기가 주 · 건수 읽기는 병기(§11·§14).")
    say()
    say("🔴 **이 문서는 라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1). **새 예측을 만들지 않았다** — "
        "동결된 항목(`PREREG_POST6.md` §4 #38~#54 · `PREREG_POST8.md` `D-3`·`D-5`·`D-9`)만 계산·인쇄했다.")
    say()
    say("[[LABELS_2026-09-18_post8]] · [[INTAKE_2026-09-18_post8]] · [[PREDECISION_2026-09-18_post8]] · "
        "[[PREREG_POST8]] · [[PREREG_POST6]] · [[PREREG_WEIGHTED_RECON]] · [[PREREG_ANCHOR_REDESIGN]] · "
        "[[PREREG_GRADE_TIERS]] · [[RESULTS_RECONSTRUCT_POST7]] · [[RESULTS_RECONSTRUCT_POST6]] · [[RESULTS_RECONSTRUCT_POST5]]")

    (BASE / "RESULTS_RECONSTRUCT_POST8_NUMBERS.md").write_text("\n".join(OUT) + "\n",
                                                               encoding="utf-8")
    cur.close()
    conn.close()
    note("\n[written] RESULTS_RECONSTRUCT_POST8_NUMBERS.md")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())

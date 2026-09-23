# -*- coding: utf-8 -*-
"""매수 사다리 「체결 차수 ↔ 낙폭」 정렬 축 — **8번째 글 누적 재계산** (`LAD-T1`·`T2`·`T3` · `LAD-P1`~`P3`).

준거(전부 동결본 · 규칙 변경 0):
  · `PREREG_LADDER_TRANCHE.md` §4(정의 · §4-2 B-5 「창5 절단 대체」 규칙)·§5(예측·결정규칙 · 게이트 = **누적** 40)
  · `PREREG_POST6.md` §1-4(창 규약)·§1-5(재진입)·§1-6(절단 가드)·§2-4 · §4 표 #21~#24
  · `PREREG_POST8.md`(동결 `04cd785` · 머지 `729f28b`) — 🆕 **첫 구속 회차**:
      `D-1`(§1 · 누적 쌍 «세 수» 인쇄 — `ANC-P3` 게이트 분모) · `D-5`(§5 `P8-갈래계수`) ·
      `D-7`(§7 `P6-창5절단가드-A` 분모 = 이번 글 신규 · `exact` 갈래 병기 · 2회 연속 계수) ·
      `D-9`(§9 `P8-빈티지` · `P8-혼합빈티지신고` · 읽은 시각 박제) · `D-3`(§3 `P8-approx의존신고`)
  · `RESULTS_LADDER_TRANCHE.md` §1(B-1~B-8 해석 결정) · §7(절단 창5 가짜 숫자 전례)
  · `PREDECISION_2026-09-18_post8.md` PD-1(창 종료 = **2026-09-18 · 발행 당일 봉 포함**) · PD-2(후속 3건 등록일 축 밖)
    · PD-3(우리로 = 항목 내 2 사이클 · 🔒 #1-(ii) `LAD-` = 포함 · 「우리로 제외」 인쇄만) · PD-4(`exact` 4 · `approx` 2 ·
    `none` 1) · PD-12(post7 절단 값 «대체») · PD-13(`first_only` · exact 전부 N=1) · PD-19(D-1) · PD-21(D-3) ·
    PD-23(D-5 갈래 목록) · PD-25(D-7) · PD-27 (마)(바)(착수 조건 · 혼합 빈티지 표)
  · `INTAKE_2026-09-18_post8.md` §1(항목 10건)·§2-10·§2-11·§5(이 축 행) · `LABELS_2026-09-18_post8.md`(B-2 carve-out)

🔴 이 스크립트는 **`run_ladder_tranche.py`·`run_ladder_tranche_post6.py`·`run_ladder_tranche_post7.py` 를
   «수정하지 않는다»**. 통계 핵(`pairset`·`statV`·`permute_null`·`run_axis`)은 첫째에서, 가드·판정 함수
   (`guard_a_fires`·`verdict_t1`·`median`)는 둘째에서, 누적 목록(`ITEMS` 28건)과 건별 원표 함수(`build_rows`)는
   셋째에서 **그대로 import** 한다. 이 파일이 새로 정의하는 것은 **post8 목록 · post8 의무 인쇄 · 읽은 시각 박제**뿐이다.
   ⚠️ `LAD.OUT` 재지정은 **`main()` 안에서만** 한다 — import 만으로는 post7 판의 버퍼 결속을 흔들지 않는다
   (`test_post7_ladder.py` P3 의 `LAD.OUT is P7.OUT` 가 같은 프로세스에서도 계속 참이어야 한다).

이번 회차의 갈림(계산 «전» 고정 · 전부 승계 · 신설 0):
  B-1  post8 발행 **2026-09-18(금) = 거래일** ⇒ 창A = `[D, 2026-09-18]`(발행 당일 봉 포함 · post6 09-04 금과 같은 갈래).
       옛 글의 창A 는 **그 글의 발행일**에서 끝난다(`pub_eff = min(pub, END)` · post7 판 `build_rows` 그대로).
  B-2  `MANUAL` 신규 2건 — JW신약(`exact`)은 매수 쪽 수동 서술이 없어 **포함** · 원익은 **`none`** 이라 밖
       (라벨이 사유가 아니다) · 로보티즈는 **후속**이라 밖(라벨이 사유가 아니다).
  B-7  같은 종목 2번째 사이클 = 누적 5건(코데즈 post5 · 한켐 post5 · 현대약품 post6 · 지투파워 post6 · 빛과전자 post7)
       + post8 은 `exact` 안 **0**(원익 `none` · 헥토·코데즈 `approx`) ⇒ 제외 민감도는 누적 5건 제외.
       🔴 우리로의 「항목 내 2 사이클」은 B-7(«글을 넘는» 재등록)이 아니다 — 🔒 #1-(ii): **포함 · 「우리로 제외」 인쇄만**.
  PD-4 주 표본 = 신규 ∧ `exact` **4**(우리로 · JW신약 · 액스비스 · 우리기술 — **전부 N = 1**) · `approx` 2 = §7-1 갈래
       민감도 · `none` 1 + 후속 3 = 등록일 축 밖. 가드-A 분모 = **이번 글 신규 7**(`PREREG_POST8.md` §7 D-7).
  PD-12 post7 절단 2건(빛과전자 09-08 · 범한퓨얼셀 09-09) + 지투파워 `approx` 3갈래(09-08·09-09·09-10)의 창5 가
       END 09-18 에서 **완전**해진다 ⇒ **값 대체**(`PREREG_LADDER_TRANCHE.md` §4-2 B-5 1~5) — 「절단 시점 값 → 대체 값」과
       **대체 전/후 `V`·`p`** 를 둘 다 인쇄한다(B-5 3번). 판정이 갈리면 ⛔ 「창5 절단 의존」.
  D-9  `H`·`L`·`L₅` = `daily_prices.high/low` 의 D+1 안정 빈티지(시간외분이 들어간 채로). 읽은 시각 = ① 쿼리 실행 시각(KST)
       ② 창 구간 `max(updated_at)`. ⚠️ **① 은 벽시계라 재실행마다 다르다** — byte 재현 의무(md5 3회 동일)와 충돌하므로,
       ① 은 «이 파일을 처음 만든 실행»의 시각을 박고, 재실행은 **② 지문 줄이 byte 같을 때만** 그 값을 잇는다
       (지문이 움직이면 새 시각을 박는다 · 이번 실행 시각은 stdout 에 항상 찍는다). 🔴 이것은 **재량**이다 — 보고서에 신고한다.

🔴 라이브 채택 대상이 아니다(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1). 라이브 트리 import 0건 · DB 는 SELECT 만 ·
   `adj_factor` 산술 0건 · 새 예측 0 · 값 보고 규칙을 바꾸지 않는다(모호하면 양쪽 인쇄 + 「모호」) · 등급 이름을 적지 않는다.
"""
from __future__ import annotations

import re
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
    NPERM,            # 200,000
    NULL_SEED,        # 20260815 — 기존 값 그대로
    PAIR_THRESHOLD,   # 40 (§5-1 · 누적)
    pairset,
    permute_null,
    run_axis,
    statV,
)
# 🔴 post6 판(수정 금지)에서 **가드·판정 함수**를 그대로 가져온다.
from run_ladder_tranche_post6 import (
    GUARD_A_DEN,
    GUARD_A_NUM,
    TRUNC5_MIN_BARS,           # 5 (창5 = D + 4거래일)
    guard_a_fires,
    median,
    verdict_t1,
)
import run_ladder_tranche_post6 as P6
# 🔴 post7 판(수정 금지)에서 **누적 목록 28건과 건별 원표 함수**를 그대로 가져온다 — 새 코드 0줄.
import run_ladder_tranche_post7 as P7
from run_ladder_tranche_post7 import ITEMS as ITEMS_CUM28, build_rows

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
NUMBERS = BASE / "RESULTS_LADDER_TRANCHE_POST8_NUMBERS.md"

END = "2026-09-18"          # 창 종료 (PD-1 · 발행 당일 봉 포함 · 전 축)
PUB8 = "2026-09-18"         # 8번째 글 발행일 = **금요일 = 거래일** (B-1 ⇒ 창A 는 발행 당일에서 끝난다)
END7 = "2026-09-11"         # post7 창 종료 — 「절단 시점 값」 재현용(대체 «전»)
BOUNDARY = "2026-09-14"     # KRX 연장 제도 경계 (`PREREG_POST8.md` §9 · P8-혼합빈티지신고)
SWEEP_D1 = "2026-09-21 15:35"   # 09-18 봉의 D+1 sweep (PD-27 (마) 2)
WIN_LO = "2026-07-24"       # 관리자 프로브 창 시작(PD-27 (다) · 부록 A) — 같은 잣대로 한 번 더 읽는다

# 계열 인쇄값 (나란히 인쇄용 · **판정에 쓰지 않는다** — 재계산값과 대조만 한다)
CUM_PAIRS_POST7 = 266       # `RESULTS_LADDER_TRANCHE_POST7_NUMBERS.md` §2
POST7_T1_V, POST7_T1_P = 127, 0.4064
POST7_T3_P = 0.1182
# (회차, 누적 목록, 창 종료, 인쇄 V, 인쇄 비교가능 쌍, 인쇄 p, 출처)
SERIES_PRIOR = [
    ("post4(1회차 · δ 현행 규칙)", "post4", "2026-08-28", 4, 7, 0.6664,
     "`RESULTS_LADDER_TRANCHE_NUMBERS.md` 「창5 (delta=1.0%p · 현행 규칙)」 행"),
    ("post5 누적", "post5", "2026-08-28", 21, 41, 0.5160, "`RESULTS_LADDER_TRANCHE.md` §0"),
    ("post6 누적", "post6", "2026-09-04", 80, 161, 0.4914, "`RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md` §2"),
    ("post7 누적", "post7", "2026-09-11", 127, 266, 0.4064, "`RESULTS_LADDER_TRANCHE_POST7_NUMBERS.md` §2"),
]

LAD_P2_LO, LAD_P2_HI = 15.0, 35.0       # `LAD-P2` 구간 (동결)
POST7_P2_MEDIAN = 20.11                 # post7 신규(exact 6) 중앙값 — 계열 인쇄용

N_NEW_POST8 = 7             # 🔴 가드-A 분모 = 「이번 글 신규 건」 (`PREREG_POST8.md` §7 (나) 1)
N_EXACT_POST8 = 4           # 주 표본 (PD-4 1번)

# (종목, 코드, 등록일, 차수 N, 글, 발행일, 두번째 사이클?, 비고) — `INTAKE_2026-09-18_post8.md` §1 순서
ITEMS_POST8_NEW = [
    ("우리로",   "046970", "2026-09-11", 1, "post8", PUB8, False,
     "first_only·`exact`·🔀 항목 내 2 사이클(`구조차단` · 사이클 1 등록일) — 「우리로 제외」 인쇄만(🔒 #1-(ii))"),
    ("JW신약",   "067290", "2026-09-01", 1, "post8", PUB8, False,
     "first_only·`exact`·`MANUAL` — B-2 carve-out(매도 쪽만 직접 · 포함)"),
    ("액스비스", "0011A0", "2026-09-11", 1, "post8", PUB8, False,
     "first_only·`exact`·코드 news 경유(PD-11)·DB 첫 봉 2026-04-13"),
    ("우리기술", "032820", "2026-09-09", 1, "post8", PUB8, False,
     "first_only·미완결·`exact`·≠ 우리기술투자 041190(PD-11)"),
]
ITEMS = list(ITEMS_CUM28) + ITEMS_POST8_NEW

# 🔴 `approx` 2건 — 「8월말」 = `2026-08-21 ~ 2026-08-31` 거래일 7갈래(PD-4 2번 · `PREREG_POST6.md` §1-4).
#    (종목, 코드, N, 저자 표기, 창 시작, 창 끝, 갈래수 기대, 직전 등록일(재진입 · PD-3))
APPROX_BRANCHES = [
    ("헥토파이낸셜", "234340", 1, "「8월말」", "2026-08-21", "2026-08-31", 7, "2026-08-28"),
    ("코데즈컴바인", "047770", 2, "「8월말」", "2026-08-21", "2026-08-31", 7, "2026-08-21"),
]

# 🔴 등록일 축 «밖» — 사유를 **라벨과 분리해** 적는다(B-2 · PD-2 · PD-4 3번).
OUT_OF_REGDAY_AXIS = [
    ("원익",       "032940", 1, "`MANUAL`",
     "`none` — 「9월 3일, 한 차례 매매 후, 다시 … 등록」의 날짜가 어느 사건에 붙는지 원문이 정하지 않는다"
     "(🔒 #2 · 약한 결정) ⇒ 창 `[D, END]` 를 세울 `D` 가 없다. 🔴 라벨(`MANUAL`)이 사유가 «아니다»"),
    ("빛과전자",   "069540", 1, "`TP`",
     "후속(post7 #11) — PD-2 이중계상 금지 · 그 등록 사건은 post7 행(주 표본 #27)이 이미 들고 있다"),
    ("로보티즈",   "108490", 1, "`MANUAL`",
     "후속(post7 #9) — PD-2. 🔴 **B-2 carve-out 은 `MANUAL` 을 LAD 에서 빼지 «않는다»** — 사유는 **후속**이다"),
    ("범한퓨얼셀", "382900", 1, "`TP`", "후속(post7 #13) — 〃"),
]

# `INTAKE` §2-10 · PD-13 — 신규 7건 `N` 분포 1:6 · 2:1(코데즈 `approx`)
FIRST_ONLY_POST8_NEW = ["우리로", "원익", "JW신약", "헥토파이낸셜", "액스비스", "우리기술"]
FIRST_ONLY_POST8_EXACT = ["우리로", "JW신약", "액스비스", "우리기술"]
# `P6-PRIOR_CYCLE_IN_WINDOW` (PD-3 표 · INTAKE §2-7) — 🔴 exact 열 안은 우리로 1건이고 그 값이 **0**
PRIOR_CYCLE_FLAG_POST8 = {"우리로": "0", "원익": "계산 안 함(`none`)",
                          "헥토파이낸셜": "갈래별 — 2/7 갈래 1 · 5/7 갈래 0", "코데즈컴바인": "7/7 갈래 1"}

# 🔴 PD-12 — post7 에서 「절단 시점 값」으로 인쇄된 값. **인용**이다(출처 `RESULTS_LADDER_TRANCHE_POST7_NUMBERS.md`
#    §1-1 · §7-1 — 그 파일은 손대지 않는다). 아래 §1-1b 는 같은 값을 END7 로 «다시» 읽어 재현 여부도 인쇄한다.
POST7_TRUNC_ASOF = {
    "빛과전자":   dict(d0="2026-09-08", n5_asof=4, dd5_asof=20.33),
    "범한퓨얼셀": dict(d0="2026-09-09", n5_asof=3, dd5_asof=6.42),
}
# 지투파워(388050 · post7 `approx` 「9월 초」) 절단 3갈래 — post7 §7-1 표 (갈래 D → (창5 봉수, DD5))
POST7_G2_CODE = "388050"
POST7_G2_DAYS = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
                 "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"]
POST7_G2_ASOF = {"2026-09-08": (4, 16.39), "2026-09-09": (3, 10.96), "2026-09-10": (2, 9.98)}

# 🔴 PD-27 (바) 표 — `LAD-` 창5 «걸침» 칸 (계산 «전» 구성 · 경계 전/후 봉수). 아래 §0-2 는 실측으로 다시 센다.
PD27_CROSS5 = {("우리로", "post8"): (1, 4), ("액스비스", "post8"): (1, 4), ("우리기술", "post8"): (3, 2),
               ("빛과전자", "post7"): (4, 1), ("범한퓨얼셀", "post7"): (3, 2)}
PD27_CROSS5_G2 = {"2026-09-08": (4, 1), "2026-09-09": (3, 2), "2026-09-10": (2, 3)}

# 착수 조건 충족 증거 — 관리자 실측(2026-09-24 00:07:44 KST · `p8_lane_common.md` §3) · **인용**
ADMIN_PROBE = [
    "보관 `D:/archive/tasso-program-journal-20260918/probes_precalc_0924/` — `run_time.txt`(00:07:44) · "
    "`p8_probes_postfetch_0924.txt`(P-2b·P-3·P-5 · 창 시작 07-24 · SQL = 부록 A `p8_probes_postfetch.sql` 축자) · "
    "`p8_stab_3x.txt`(3회 연속)",
    "`daily_prices` 09-18 행수 **2,764**(09-18 19:16 값과 동일 · 3/3 안정) · 09-18 `max(updated_at)` = "
    "**2026-09-23 15:46:25.855518** · 창 구간(07-24~09-18) `min(updated_at)` = **2026-09-23 15:45:10.623955**",
    "`P-3` rewritten = n(판별력 0 · 「통과」로 인용 금지 · 인쇄만) · `P-5` 15:30 분봉 09-16~09-23 = 0·0·1·0·1·0"
    "(정규장 상한 구성 불가) · `overtime_daily` 09-14 이후 `ovtm_vol>0` 0 · 09-22·23 행 없음",
]

HDR = ("| 축 | `V_obs` | 비교가능 쌍 | 버린 쌍 | 귀무 평균 `V` | **`p = P(V<=V_obs)`** | "
       "`P(V=0)` | 귀무 평균 비교가능 쌍 |")
SEP = "|---|---|---|---|---|---|---|---|"
LIVE_LINE = ("🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1) — "
             "이 산출물은 기록이지 전략 후보가 아니다.")
STAMP_RE = re.compile(r"^\| ① 쿼리 실행 시각\(KST\) \| \*\*(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\*\*", re.M)


def say(s=""):
    print(s)
    OUT.append(s)


def prior_stamp(path: Path, fp_line: str):
    """이전 산출물의 ① 값 — **② 지문 줄이 byte 같을 때만** 돌려준다(아니면 None · 새 시각을 박는다)."""
    if not path.exists():
        return None
    txt = path.read_text(encoding="utf-8")
    if fp_line not in txt.splitlines():
        return None
    m = STAMP_RE.search(txt)
    return m.group(1) if m else None


def cross_counts(cur, code, lo, hi):
    """창 `[lo, hi]` 안 그 종목의 봉을 제도 경계 전/후로 센다(B-8 · 그 종목의 봉)."""
    cur.execute("SELECT count(*) FILTER (WHERE date < %s), count(*) FILTER (WHERE date >= %s) "
                "FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s",
                (BOUNDARY, BOUNDARY, code, lo, hi))
    return cur.fetchone()


def window_bounds(cur, code, d0, nbars, end):
    """그 종목의 봉 기준 창 `[d0, d0 + (nbars-1) 봉]` 의 끝 날짜와 실제 봉수."""
    cur.execute("SELECT date FROM daily_prices WHERE stock_code=%s AND date >= %s AND date <= %s "
                "ORDER BY date LIMIT %s", (code, d0, end, nbars))
    ds = [r[0] for r in cur.fetchall()]
    return (ds[-1] if ds else None), len(ds)


def main():  # noqa: C901
    LAD.OUT = OUT              # 🔴 표 행(`run_axis`)을 이 실행의 버퍼로 — import 가 아니라 실행 시점에만 묶는다
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    # ── 읽은 시각 박제 재료 (D-9 ①②③④) ────────────────────────────────
    cur.execute("SELECT to_char(now() AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS')")
    now_kst = cur.fetchone()[0]
    cur.execute("SELECT max(date) FROM daily_prices")
    db_max = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (db_max,))
    db_max_rows = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (END,))
    end_rows = cur.fetchone()[0]
    cur.execute("SELECT count(*), min(updated_at), max(updated_at) FROM daily_prices "
                "WHERE date BETWEEN %s AND %s", (WIN_LO, END))
    w_n, w_umin, w_umax = cur.fetchone()
    cur.execute("SELECT min(updated_at), max(updated_at) FROM daily_prices WHERE date = %s", (END,))
    e_umin, e_umax = cur.fetchone()

    # 거래일 달력 (B-6)
    cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN '2026-07-01' AND %s "
                "ORDER BY date", (END,))
    cal = [r[0] for r in cur.fetchall()]

    rows = build_rows(cur, ITEMS, cal, END)

    # 이 축이 «실제로» 읽은 봉(종목 × [sigma20 21종가 창 시작, END]) 의 updated_at 범위
    ax_umin = ax_umax = None
    ax_lo = None
    ax_n = 0
    for r in rows:
        cur.execute("SELECT min(date) FROM (SELECT date FROM daily_prices WHERE stock_code=%s AND date < %s "
                    "ORDER BY date DESC LIMIT 21) t", (r["code"], r["d0"]))
        lo = cur.fetchone()[0] or r["d0"]
        cur.execute("SELECT count(*), min(updated_at), max(updated_at) FROM daily_prices "
                    "WHERE stock_code=%s AND date BETWEEN %s AND %s", (r["code"], lo, END))
        n_, a_, b_ = cur.fetchone()
        ax_n += n_
        ax_umin = a_ if ax_umin is None or a_ < ax_umin else ax_umin
        ax_umax = b_ if ax_umax is None or b_ > ax_umax else ax_umax
        ax_lo = lo if ax_lo is None or lo < ax_lo else ax_lo

    fp_line = (f"| ② 창 구간 `max(daily_prices.updated_at)` | 공통 창 `[{WIN_LO}, {END}]`(전 종목 {w_n:,}행): "
               f"`max` **{w_umax}** · `min` **{w_umin}** · 이 축이 읽은 봉(누적 {len(rows)}건 × `[σ₂₀ 창 시작, "
               f"{END}]` = `[{ax_lo}, {END}]` · 건별 합 {ax_n:,}행(같은 종목 두 건은 두 번 센다)): `max` **{ax_umax}** · `min` **{ax_umin}** · "
               f"실행 시 `max(date)` **{db_max}**({db_max_rows:,}행) |")
    prev = prior_stamp(NUMBERS, fp_line)
    stamp = prev or now_kst
    print(f"[run] 이번 실행 시각(KST) = {now_kst} · 산출물 ① = {stamp} "
          f"({'이전 산출물의 값을 이음 — ② 지문 동일' if prev else '새로 박음'})")

    say("# RESULTS_LADDER_TRANCHE_POST8_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_ladder_tranche_post8.py` · 통계 핵·표 포맷은 `run_ladder_tranche.py`, 가드·판정 함수는 "
        "`run_ladder_tranche_post6.py`, 누적 목록(28건)·건별 원표 함수(`build_rows`)는 `run_ladder_tranche_post7.py` 에서 "
        "import (**세 파일 다 수정하지 않았다**)")
    say("사전등록 `PREREG_LADDER_TRANCHE.md`(2026-08-22 동결) · `PREREG_POST6.md` §1-4·§1-5·§1-6·§2-4·§4 #21~#24 · "
        "🆕 `PREREG_POST8.md`(첫 구속 · `D-1`·`D-3`·`D-5`·`D-7`·`D-9`) · 해석 결정 `RESULTS_LADDER_TRANCHE.md` §1 "
        "B-1~B-8 + `PREDECISION_2026-09-18_post8.md` PD-1·PD-2·PD-3·PD-4·PD-12·PD-13·PD-19·PD-21·PD-23·PD-25·PD-27")
    say(f"`delta` = {DELTA}%p · `NULL_SEED` = {NULL_SEED} · 순열 표본 {NPERM:,} · "
        f"판정 문턱 = 누적 비교가능 쌍 {PAIR_THRESHOLD} — **넷 다 동결 그대로 손대지 않았다**")

    # ── §0. 실행 환경 · 창 종료 · 읽은 시각 (D-9) ───────────────────────
    say()
    say("## §0. 실행 환경 · 창 종료 규약 · 🆕 읽은 시각 박제 (PD-1 8번 · `PREREG_POST8.md` §9 D-9)\n")
    say(f"**창 종료 {END} = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1**")
    say(f"**실행 시 `max(date)` = {db_max} · 그 날짜 행수 {db_max_rows:,} — 기록만(창 아님)** · "
        f"창 종료 {END} 행수 **{end_rows:,}**")
    say()
    say("| D-9 의무 | 값 |")
    say("|---|---|")
    say(f"| ① 쿼리 실행 시각(KST) | **{stamp}** — 이 파일을 «처음» 만든 실행의 시각(DB `now()` · Asia/Seoul). "
        "재실행은 아래 ② 지문 줄이 byte 같을 때만 이 값을 잇는다(지문이 움직이면 새 시각) — byte 재현 의무와의 "
        "충돌을 피하려는 **재량**이다 · 각 실행의 실제 시각은 stdout `[run]` 줄 |")
    say(fp_line)
    say(f"| ③ 09-18 봉의 빈티지 | **「09-18 봉은 D+1(09-21) sweep 이후 읽음」** — 09-18 행 `min(updated_at)` = "
        f"**{e_umin}** ≥ {SWEEP_D1}: **{'예' if str(e_umin) >= SWEEP_D1 else '🔴 아니오'}** · `max` {e_umax} |")
    say(f"| ④ 창 구간 `min(updated_at)` | **「창 구간 `min(updated_at)` = {w_umin} ≥ 09-21 15:35: "
        f"{'예' if str(w_umin) >= SWEEP_D1 else '아니오'}」**(기록 · 통과 조건 아님 · `updated_at` 은 sweep 일괄 갱신값이라 "
        "빈티지 «증거»가 아니라 «읽은 시각» 기록 · PD-27 (라)) |")
    say("| ⑤ 혼합 빈티지 | §0-2 — `LAD-` 창5 걸침 칸마다 한 줄(PD-27 (바) 표 실측 재계수) |")
    say("| 「정규장만」 갈래 | **열지 않음**(`PREREG_POST8.md` §9 (나) 4) · `adj_factor` 산술 **0건** · 라이브 트리 import 0건 · "
        "DB 는 SELECT 만 |")
    say()
    say("**착수 조건 충족 증거(관리자 실측 · 2026-09-24 00:07:44 KST · 인용 — 이 레인은 ②③④ 를 위 표에서 직접 다시 읽었다)**:")
    for ln in ADMIN_PROBE:
        say(f"- {ln}")
    say()
    say(LIVE_LINE)
    say("🔵 라벨 접두(§0-3 규약): 이 문서의 `T1`·`T2`·`T3`·`P1`~`P3` 은 전부 **`LAD-`** 축이다"
        "(`PREREG_LADDER_TRANCHE.md` §5). 플래그·가드는 **`P6-`**, 이번 회차 신설 규약은 **`P8-`** 접두를 그대로 단다.")
    say("🔴 **새 예측을 만들지 않았다** — δ·창5·게이트 40·시드·순열 표본 수 전부 동결값 그대로다. "
        "🔴 **등급 이름을 적지 않는다**(`INTAKE_2026-09-18_post8.md` §6 단계 · PD-16·PD-28).")

    # ── §0-2. P8-혼합빈티지신고 (창5) ───────────────────────────────────
    say()
    say("### §0-2. 🆕 `P8-혼합빈티지신고` — `LAD-` 창5 `[D, D+4]` (PD-27 (바) · `PREREG_POST8.md` §9 (나) 3)\n")
    say("의무 문형 *「창 `[<시작>, <끝>]` 은 제도 경계 2026-09-14 를 걸친다 — 경계 전 `<n_before>` 봉 / 후 `<n_after>` 봉 · "
        "혼합 빈티지」* — 누적 풀 전 행을 실측으로 다시 셌다(그 종목의 봉 · B-8).\n")
    got5 = {}
    for r in rows:
        hi, nb = window_bounds(cur, r["code"], r["d0"], 5, END)
        b, a = cross_counts(cur, r["code"], r["d0"], hi)
        if b and a:
            got5[(r["nm"], r["post"])] = (b, a)
            say(f"- {r['nm']}({r['post']} · 등록 {r['d0']}): 창 `[{r['d0']}, {hi}]` 은 제도 경계 2026-09-14 를 걸친다 — "
                f"경계 전 {b} 봉 / 후 {a} 봉 · 혼합 빈티지")
    g2_cross = {}
    for d0 in POST7_G2_DAYS:
        hi, nb = window_bounds(cur, POST7_G2_CODE, d0, 5, END)
        b, a = cross_counts(cur, POST7_G2_CODE, d0, hi)
        if b and a:
            g2_cross[d0] = (b, a)
            say(f"- 지투파워(post7 `approx` 갈래 D={d0} · §1-1b 대체): 창 `[{d0}, {hi}]` 은 제도 경계 2026-09-14 를 걸친다 — "
                f"경계 전 {b} 봉 / 후 {a} 봉 · 혼합 빈티지")
    ok27 = (got5 == PD27_CROSS5) and (g2_cross == PD27_CROSS5_G2)
    say()
    say(f"- 걸침 칸 = **{len(got5)}건 + 지투파워 갈래 {len(g2_cross)}** ⇒ PD-27 (바) 표(창5 걸침 3건 + 대체 창 5)와 "
        f"**{'일치 ✅' if ok27 else '🔴 불일치 — 실측을 그대로 적는다'}**")
    say("- 🔴 **참고 병기(의무 목록 밖 · 판정 창 아님)** — `LAD-` 의 민감도 창(창3 `[D, D+2]` · 창A `[D, 발행일]`)도 걸치는 자리:")
    for r in rows:
        if r["post"] != "post8":
            continue
        hi3, _ = window_bounds(cur, r["code"], r["d0"], 3, END)
        b3, a3 = cross_counts(cur, r["code"], r["d0"], hi3)
        ba, aa_ = cross_counts(cur, r["code"], r["d0"], r["pub"])
        say(f"  - {r['nm']}: 창3 `[{r['d0']}, {hi3}]` 전 {b3} / 후 {a3}"
            f"{' · 걸침' if b3 and a3 else ' · 안 걸침'} · 창A `[{r['d0']}, {r['pub']}]` 전 {ba} / 후 {aa_}"
            f"{' · 걸침' if ba and aa_ else ' · 안 걸침'}")
    say("- 🔴 **방향 추론은 인용하지 않는다** — 「`H` 를 높이고 `L` 을 낮춘다」는 `PREREG_POST8.md` §9 (마)의 **추론**이다(실측 아님).")

    # ── §1-0. 표본 구성 ────────────────────────────────────────────────
    new8 = [r for r in rows if r["post"] == "post8"]
    old = [r for r in rows if r["post"] != "post8"]
    trunc = [r for r in new8 if r["trunc5"]]
    trunc_all = [r for r in rows if r["trunc5"]]
    say()
    say("## §1-0. 표본 구성 — 「이번 글 신규 7」 · 「주 표본 4」 · **4건 전부 N = 1** (PD-4 · PD-13)\n")
    say("| 구분 | 건 | 이 축에서의 지위 |")
    say("|---|---|---|")
    say(f"| 신규 ∧ `exact` | **{N_EXACT_POST8}** | 🟢 **주 표본** — 창 `[D, {END}]` 를 세울 `D` 가 있다 · 🔴 **전부 N = 1** |")
    say("| 신규 ∧ `approx` | **2** | ⚪ **갈래별 민감도**(§7-1) — 「8월말」 = 08-21~08-31 거래일 7갈래 · 판정 언어 금지 |")
    say("| 신규 ∧ `none` | **1** | 🔴 등록일 축 밖 — `D` 가 없다(원익 · 🔒 #2) |")
    say("| 기존 건 후속 | **3** | 🔴 등록일 축 밖 — PD-2 이중계상 금지 |")
    say(f"| **이번 글 신규 계** | **{N_NEW_POST8}** | 🔴 **가드-A 의 «분모»는 이 수**(`PREREG_POST8.md` §7 (나) 1 · D-7) |")
    say("| 항목 계 | 10 | `INTAKE` §1 |")
    say()
    say("### 등록일 축 «밖» 4건 — **사유를 라벨과 분리해 적는다**\n")
    say("| 종목 | 코드 | N | 라벨 | 밖인 사유 |")
    say("|---|---|---|---|---|")
    for nm, code, N, lbl, why in OUT_OF_REGDAY_AXIS:
        say(f"| {nm} | {code} | {N} | {lbl} | {why} |")
    say()
    say("🔴 **B-2 carve-out 재확인**: `RESULTS_LADDER_TRANCHE.md` §1 **B-2** 는 *「매도 쪽만 수동이면 포함」* 이다 ⇒ "
        "**`MANUAL` 3건은 이 축에서 라벨을 이유로 빠지지 «않는다»** — JW신약은 **포함**, 원익은 `none` 이라, 로보티즈는 "
        "후속이라 빠진다(`LABELS_2026-09-18_post8.md` 약한 결정 절: *「실제 LAD 신규 행은 **JW신약** 1건」*).")
    say("🔴 **우리로 = 항목 내 2 사이클**(post5 한켐 A-9 이후 두 번째) — 🔒 #1-(ii) 사장님 채택: **포함 · 「우리로 제외」 값은 "
        "«인쇄만» · `재진입 의존`/`P8-갈래계수` 효과 없음**. 등록 사건 = 사이클 1 의 09-11 `exact` · N = 1(「1차 매수 후」 축자).")

    # ── §1. 건별 원표 ───────────────────────────────────────────────────
    say()
    say("## §1. 건별 원표 — `(종목, 글, N, H, min_low, DD)` (§4-5 의무 인쇄 4)\n")
    say(f"`H` = 등록일 고가 · `DD` = 1 - min(low over 창) / H · 창5 = `[D, D+4거래일]`(그 종목의 봉 · B-8) · "
        f"창A = `[D, 그 글의 발행일]`(post8 = **{PUB8}** 발행 당일 포함 · 옛 글은 그 글의 발행일 · B-1) · "
        f"🔴 **post4~7 행도 이 실행(같은 스냅샷)에서 다시 읽은 값이다** — 직전 문서의 숫자를 옮겨 적지 않았다.\n")
    say("| # | 종목 | 글 | N | 등록일 | H | 창3 봉수 / min_low / **DD3** | "
        "창5 봉수 / min_low / **DD5** | 창A 끝 / min_low / **DD_A** | 경과거래일 E | sigma20 | "
        "`P6-WIN5_TRUNC` | 비고 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        memo = r["memo"]
        if r["post"] == "post7" and r["nm"] in POST7_TRUNC_ASOF:
            memo += " → 🆕 **post8 창에서 완전 · §1-1b 값 대체**"
        if r["post"] == "post6" and r["nm"] in P7.POST6_TRUNC_ASOF:
            memo += " → post7 회차에 값 대체 완료(창5 완전 · `RESULTS_LADDER_TRANCHE_POST7_NUMBERS.md` §1-1b)"
        sig_s = "—" if r["sig"] is None else f"{r['sig']:.4f}"
        say(f"| {r['i']} | {r['nm']} | {r['post']} | **{r['N']}** | {r['d0']} | {r['H']:,.0f} | "
            f"{r['n3']} / {r['l3']:,.0f} / **{r['dd3']:.2f}%** | "
            f"{r['n5']} / {r['l5']:,.0f} / **{r['dd5']:.2f}%** | "
            f"{r['pub']} / {r['la']:,.0f} / **{r['dda']:.2f}%** | {r['E']} | {sig_s} | "
            f"{'**1**' if r['trunc5'] else '0'} | {memo} |")
    say()
    say("- 「창A 끝」 칸은 **그 글의 발행일**이다 — 발행일이 토요일(post4 08-22 · post5 08-29 · post7 09-12)이면 휴장이라 "
        "창은 그 직전 마지막 거래일에서 끝난다(B-1 · `pub_eff = min(pub, END)` · post7 판 표기 그대로).")
    say(f"- 표본 **{len(rows)}건** = 기존 누적 {len(old)}(post4 6 + post5 6 + post6 10 + post7 6) + "
        f"**8번째 글 주 표본 {len(new8)}건**(신규 ∧ `exact`). 후속 3건·`none` 1건은 **등록일 축 밖**(§1-0) · "
        "`approx` 2건은 **§7-1 갈래 민감도**.")
    say(f"- 8번째 글 주 표본의 차수 다중집합 = {sorted(r['N'] for r in new8)} (`INTAKE` §2-10 신규 7건 분포 1:6 · 2:1 중 "
        "`exact` 부분) — 🔴🔴 **전부 N = 1** ⇒ 그 글 «단독» 비교가능 쌍은 **구성상 0**(§3-1 · D-1).")

    # ── §1-1. 창5 절단 · 가드-A (D-7) ───────────────────────────────────
    say()
    say("### §1-1. 창5 절단 · 🆕 `P6-창5절단가드-A` 분모 두 산술 (`PREREG_POST8.md` §7 D-7 · PD-25)\n")
    say(f"- **이번 글 신규 건 중 절단 = {len(trunc)}건**"
        + (": " + " · ".join(f"{r['nm']}(창5 {r['n5']}봉)" for r in trunc) if trunc else " — 주 표본 4건 전부 창5 **5봉 완전**")
        + f" · 누적 풀 전체 절단 = **{len(trunc_all)}건**(post7 절단 2건은 §1-1b 로 대체돼 완전)")
    ga_main = len(trunc) / N_NEW_POST8
    ga_exact = len(trunc) / N_EXACT_POST8
    split_ga = guard_a_fires(len(trunc), N_NEW_POST8) != guard_a_fires(len(trunc), N_EXACT_POST8)
    say()
    say("| 분모 갈래 | 산술 | 문턱 1/3 | 판정 |")
    say("|---|---|---|---|")
    say(f"| **주 — 이번 글 신규 건**(`PREREG_POST8.md` §7 (나) 1) | **{len(trunc)}/{N_NEW_POST8} = {100*ga_main:.1f}%** | "
        f"{100*GUARD_A_NUM/GUARD_A_DEN:.1f}% | **{'⛔ 발동' if guard_a_fires(len(trunc), N_NEW_POST8) else '미발동'}** |")
    say(f"| `exact` 분모 갈래(의무 민감도 · (나) 2) | **{len(trunc)}/{N_EXACT_POST8} = {100*ga_exact:.1f}%** | "
        f"{100*GUARD_A_NUM/GUARD_A_DEN:.1f}% | **{'⛔ 문턱 도달' if guard_a_fires(len(trunc), N_EXACT_POST8) else '미도달'}** |")
    say("| `approx` 갈래 포함(§7-1 · 참고) | 헥토·코데즈 7갈래 전부 창5 완전(§7-1 표) ⇒ 분자 +0 | — | 미발동 불변 |")
    say()
    say(f"- 🆕 **분모 갈래 신고**((나) 3): *「주 분모 {len(trunc)}/{N_NEW_POST8} · `exact` 분모 {len(trunc)}/{N_EXACT_POST8} · "
        f"문턱 1/3」* — **분모 갈래: {'🔴 갈린다(가드는 «발동 아님»)' if split_ga else '갈리지 않음'}**")
    say(f"- 🆕 **2회 연속 계수**((나) 4): **post8 = 1회차 · `exact` 갈래 "
        f"{'«도달»' if guard_a_fires(len(trunc), N_EXACT_POST8) else '«미도달»'}** — "
        "🔴 **post7 의 2/6 = 33.3% 도달은 「참고 전건」으로만 적고 2회 연속 계수에 «세지 않는다»**(소급 금지 · (나) 4 · (라)).")
    say("- 문턱 1/3 은 `REC-Y3` 에서 **차용**한 값이다(`PREREG_POST6.md` §1-6 6번 고지 승계) — 절단 비율에 대해 검증된 값이 아니다.")
    say(f"- **`P6-창5절단가드-B`**(절단 제외 민감도가 `LAD-T1` 판정을 뒤집으면 ⛔): 이번 풀의 절단 건 = **{len(trunc_all)}** ⇒ "
        "제외 표본 = 주 표본 **항등**(§6 에 항등 명시) ⇒ **구성상 미발동**. 대체 전/후 판정 비교는 §1-1b.")
    say("- 🔴 **방향 기록(선택 아님)**: 신규 절단 0 은 발행일(09-18)이 최대 등록일(09-11)보다 5거래일 뒤라서다 — "
        "고른 값이 아니라 PD-1 동결 문언이 준 값의 귀결이다(PD-12).")

    # ── §1-1b. PD-12 — post7 절단 값 «대체» ─────────────────────────────
    rows7_asof = build_rows(cur, ITEMS_CUM28, cal, END7)      # post7 판 그대로(END 09-11) — 「절단 시점 값」 재현
    asof_by = {(r["nm"], r["post"]): r for r in rows7_asof}
    say()
    say("### §1-1b. 🆕 post7 절단 건의 값 **«대체»** (PD-12 · `PREREG_LADDER_TRANCHE.md` §4-2 B-5 1~5)\n")
    say(f"주 창이 {END} 로 전진해 post7 의 절단 건은 창5 가 **완전**해졌다 ⇒ 이번 회차에 값을 대체한다(B-5 2번). "
        "🔴 **봉수 보정(4봉 값을 5봉으로 스케일링)은 하지 않았다**(B-5 4번).\n")
    say("| 종목 | 등록일 | post7 「절단 시점 값」(인용) 창5 봉수 / **DD5** | 같은 값을 END 2026-09-11 로 다시 읽음 | "
        "post8 창5 봉수 / **DD5(대체)** | 차이 |")
    say("|---|---|---|---|---|---|")
    repl_rows = {}
    for nm, ref in POST7_TRUNC_ASOF.items():
        cr = next((r for r in rows if r["nm"] == nm and r["post"] == "post7"), None)
        ar = asof_by.get((nm, "post7"))
        if cr is None or ar is None:
            say(f"| {nm} | {ref['d0']} | {ref['n5_asof']}봉 / **{ref['dd5_asof']:.2f}%** | 🔴 행 없음 | 🔴 행 없음 | — |")
            continue
        repl_rows[nm] = (ar, cr)
        rep_ok = ar["n5"] == ref["n5_asof"] and f"{ar['dd5']:.2f}" == f"{ref['dd5_asof']:.2f}"
        say(f"| {nm} | {ref['d0']} | {ref['n5_asof']}봉 / **{ref['dd5_asof']:.2f}%** | "
            f"{ar['n5']}봉 / {ar['dd5']:.2f}% {'✅ 재현' if rep_ok else '🔴 불일치'} | "
            f"{cr['n5']}봉 / **{cr['dd5']:.2f}%** {'✅ 완전' if cr['n5'] >= TRUNC5_MIN_BARS else '🔴 여전히 절단'} | "
            f"{cr['dd5'] - ref['dd5_asof']:+.2f}%p |")
    say()
    say("- 🔴 **왼쪽 열은 인용이다** — 출처 = `RESULTS_LADDER_TRANCHE_POST7_NUMBERS.md` §1-1. ***그 파일은 한 byte 도 고치지 않았다*** "
        "— 대체값은 **이 산출물 안에서만** 산다(`RESULTS_*_POST7_NUMBERS.md` md5 불변 의무). 「절단 시점 값」 표기는 유지한다(B-5 5번).")
    say("- 이 대체는 **§2 이후의 모든 누적 표(`LAD-T1`·`T2`·`T3`)에 이미 반영돼 있다**(B-5 2번 「덮어쓴 뒤 누적 쌍 전체를 재계산」).")
    # 대체 전/후 V·p (B-5 3번)
    ns_all = [r["N"] for r in rows]
    dd5_after = [r["dd5"] for r in rows]
    dd5_before = [(asof_by[(r["nm"], r["post"])]["dd5"]
                   if (r["post"] == "post7" and r["nm"] in POST7_TRUNC_ASOF) else r["dd5"]) for r in rows]
    say()
    say("#### 대체 전/후 `V`·`p` — 의무 인쇄(B-5 3번 · 판정이 갈리면 ⛔ 「창5 절단 의존」 = `P6-창5절단가드-B`)\n")
    say(HDR)
    say(SEP)
    r_before = run_axis(f"창5 · **대체 «전»**(빛과전자·범한퓨얼셀 = 절단 시점 값 · {len(rows)}건)", ns_all, dd5_before, DELTA)
    r_after = run_axis(f"창5 · **대체 «후»**(= §2 주 판정 · {len(rows)}건)", ns_all, dd5_after, DELTA)
    say()
    vb, va = verdict_t1(r_before), verdict_t1(r_after)
    say(f"- 대체 전 **{vb}**(`p` {r_before['p']:.4f} · 쌍 {r_before['comp']}) ↔ 대체 후 **{va}**(`p` {r_after['p']:.4f} · "
        f"쌍 {r_after['comp']}) ⇒ **{'🔴 ⛔ 「창5 절단 의존」 — 판정이 갈린다' if vb != va else '판정이 갈리지 않는다 — 「창5 절단 의존」 미발동'}**")

    # 지투파워 approx 3갈래 대체 (인쇄 · post7 §7-1 갈래 민감도)
    say()
    say("#### 지투파워(`388050` · post7 `approx` 「9월 초」) 절단 3갈래의 값 대체 — **민감도 표 · 판정 아님**\n")
    say("| 갈래 `D` | post7 「절단 시점 값」(인용) 창5 봉수 / DD5 | END 2026-09-11 로 다시 읽음 | post8 창5 봉수 / **DD5(대체)** | 차이 |")
    say("|---|---|---|---|---|")
    for d0 in POST7_G2_DAYS:
        cur.execute("SELECT date, high, low FROM daily_prices WHERE stock_code=%s AND date >= %s AND date <= %s "
                    "ORDER BY date", (POST7_G2_CODE, d0, END))
        bars = cur.fetchall()
        H = bars[0][1]
        w5 = bars[:5]
        dd5 = 100 * (1 - min(b[2] for b in w5) / H)
        w5a = [b for b in bars if b[0] <= END7][:5]
        dd5a = 100 * (1 - min(b[2] for b in w5a) / H)
        if d0 in POST7_G2_ASOF:
            n_q, v_q = POST7_G2_ASOF[d0]
            rep = len(w5a) == n_q and f"{dd5a:.2f}" == f"{v_q:.2f}"
            say(f"| {d0} | {n_q}봉 / **{v_q:.2f}%** | {len(w5a)}봉 / {dd5a:.2f}% {'✅ 재현' if rep else '🔴 불일치'} | "
                f"{len(w5)}봉 / **{dd5:.2f}%** | {dd5 - v_q:+.2f}%p |")
        else:
            say(f"| {d0} | (절단 아님) | {len(w5a)}봉 / {dd5a:.2f}% | {len(w5)}봉 / **{dd5:.2f}%** | {dd5 - dd5a:+.2f}%p |")
    say()
    say("- 🔴 지투파워 갈래는 post7 에서도 **판정 밖 민감도**였다(`approx` · §7-1) — 대체값도 **인쇄만** 한다.")

    # ── §1-2. [D-19, D] 창 봉수 ────────────────────────────────────────
    say()
    say("### §1-2. PD-12 재확인(참고) — 주 표본 4건의 `[D-19, D]` 창 봉수 (등록일 포함)\n")
    say("| 종목 | 등록일 | 창 시작(달력 D-19) | 그 종목 봉수 / 20 |")
    say("|---|---|---|---|")
    short20 = []
    for r in new8:
        cur.execute("SELECT min(date) FROM (SELECT DISTINCT date FROM daily_prices "
                    "WHERE date <= %s ORDER BY date DESC LIMIT 20) t", (r["d0"],))
        w_start = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s",
                    (r["code"], w_start, r["d0"]))
        nb = cur.fetchone()[0]
        if nb < 20:
            short20.append(r["nm"])
        say(f"| {r['nm']} | {r['d0']} | {w_start} | {'🔴 **' + str(nb) + '**' if nb < 20 else nb} / 20 |")
    say()
    say(f"- 20봉 미만 = **{len(short20)}건** ⇒ PD-12 표(4건 전부 20/20)와 "
        f"**{'일치 ✅' if not short20 else '🔴 불일치 — 그대로 적는다'}** · `P6-절단가드-A`(선정·등록일 축) 산술 = "
        f"{len(short20)}/{N_EXACT_POST8} ⇒ **{'⛔ 발동' if guard_a_fires(len(short20), N_EXACT_POST8) else '미발동'}** "
        "(이 축의 판정에는 쓰지 않는다 — 이름만 같고 대상이 다르다 · `PREREG_POST8.md` §7 (가) 이름 주의)")

    # ── §1-3. 배정 수 ─────────────────────────────────────────────────
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
        f"전체 {len(ns_all)*(len(ns_all)-1)//2} (🔴 post8 주 표본 4건이 전부 N = 1 이라 동률 쌍이 구성으로 늘어난다)")

    # ── §1-4. 창5 DD 퍼짐 ─────────────────────────────────────────────
    v5 = sorted(r["dd5"] for r in rows)
    q5 = statistics.quantiles(v5, n=4, method="inclusive")
    _span_full = v5[-1] - v5[0]
    say()
    say("### §1-4. 창5 `DD` 퍼짐 (계열 승계 · 「잡음 띠」 점검)\n")
    say("- 정렬: " + " · ".join(f"{x:.2f}" for x in v5))
    say(f"- 범위 **{v5[0]:.2f}~{v5[-1]:.2f}** · 폭 **{_span_full:.2f}%p**(전정밀도 `{v5[-1]!r} − {v5[0]!r}`) · "
        f"사분위 `Q1`={q5[0]:.2f} · `Q2`={q5[1]:.2f} · `Q3`={q5[2]:.2f} ⇒ **IQR {q5[2]-q5[0]:.2f}%p** "
        "(post7 누적 28건: 범위 21.48%p · IQR 6.79%p — 출처 `RESULTS_LADDER_TRANCHE_POST7_NUMBERS.md` §1-4)")

    # ── §2. 주 판정 ────────────────────────────────────────────────────
    say()
    say("## §2. `LAD-T1` 주 판정 + 창 민감도 — 창3 · **창5(주)** · 창A (§4-5 의무 1~3)\n")
    say(HDR)
    say(SEP)
    a3 = run_axis("창3 `[D,D+2]`", ns_all, [r["dd3"] for r in rows], DELTA)
    a5 = run_axis("**창5 `[D,D+4]` (주)**", ns_all, dd5_after, DELTA)
    aa = run_axis("창A `[D,발행일]`", ns_all, [r["dda"] for r in rows], DELTA)
    say()
    say(f"- 계열 값 나란히(인쇄값): post6 `V` = 80/161 · `p` = 0.4914 → post7 `V` = {POST7_T1_V}/{CUM_PAIRS_POST7} · "
        f"`p` = {POST7_T1_P:.4f} → **이번 `V` = {a5['V']}/{a5['comp']} · `p` = {a5['p']:.4f}**")
    say(f"- `P(V=0)`(§4-5 의무 2): 창3 {a3['pzero']:.5f} · 창5 {a5['pzero']:.5f} · 창A {aa['pzero']:.5f}")
    say(f"- §1 의 부호 반전(1회차: 창3 나쁨 / 창5·창A 나음) 재현 여부 — p(창3)={a3['p']:.4f} · p(창5)={a5['p']:.4f} · "
        f"p(창A)={aa['p']:.4f} ⇒ **{'재현' if (a3['p'] > 0.5 and a5['p'] < 0.5) else '재현되지 않음'}** "
        "(0.5 문턱 기계 판정 — post6 §9 1번이 신고한 knife-edge 조건 그대로 · post7 은 「재현되지 않음」)")

    # ── §2-1. 계열 재계산 (같은 스냅샷) ────────────────────────────────
    say()
    say("### §2-1. 계열 재계산 — post4~post7 풀을 **이 실행의 스냅샷**에서 그 회차의 창 종료로 다시 읽음(창5 · 옮겨 적기 아님)\n")
    say("🔴 **판정에 쓰지 않는다** — 옛 회차의 인쇄값이 이 스냅샷에서도 나오는지(데이터 이동 여부) 보는 재현 확인이다(소급 = 탐색).\n")
    say(HDR)
    say(SEP)
    pools = {"post4": LAD.ITEMS[:6], "post5": list(LAD.ITEMS), "post6": list(P6.ITEMS), "post7": list(ITEMS_CUM28)}
    series_res = []
    for title, key, end_k, v_q, c_q, p_q, src in SERIES_PRIOR:
        rk = build_rows(cur, pools[key], cal, end_k)
        res = run_axis(f"{title} · {len(rk)}건 · END {end_k}", [r["N"] for r in rk], [r["dd5"] for r in rk], DELTA)
        series_res.append((title, res, v_q, c_q, p_q, src))
    rows28_now = [r for r in rows if r["post"] != "post8"]
    r28 = run_axis(f"post7 풀 28건 · END {END}(대체 후 · post8 행 없음)", [r["N"] for r in rows28_now],
                   [r["dd5"] for r in rows28_now], DELTA)
    say()
    say("| 회차 | 재계산 `V`/쌍 · `p` | 인쇄값(인용) `V`/쌍 · `p` | 재현 | 출처 |")
    say("|---|---|---|---|---|")
    for title, res, v_q, c_q, p_q, src in series_res:
        rep = (res["V"], res["comp"], f"{res['p']:.4f}") == (v_q, c_q, f"{p_q:.4f}")
        say(f"| {title} | {res['V']}/{res['comp']} · {res['p']:.4f} | {v_q}/{c_q} · {p_q:.4f} | "
            f"{'✅ 재현' if rep else '🔴 불일치 — 그대로 적는다'} | {src} |")
    say()
    say(f"- 🔑 **post8 행이 낀 쌍** = 누적 {a5['comp']} − post7 풀(대체 후 · END {END}) {r28['comp']} = "
        f"**{a5['comp'] - r28['comp']}**(post8 4건 × N ≠ 1 인 옛 건) · 대체가 더한 쌍(post7 풀 대체 전 → 후) = "
        f"**{r28['comp'] - series_res[-1][1]['comp']:+d}** · 인쇄 누적 {CUM_PAIRS_POST7} 대비 **{a5['comp'] - CUM_PAIRS_POST7:+d}**")

    # ── §3. 게이트 · 판정 ──────────────────────────────────────────────
    say()
    say("## §3. 판정 — 게이트(§5-1 **누적** 비교가능 쌍 >= 40) · `LAD-T1`(§5-2)\n")
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
    say(f"- 계열: 1회차(post4) 13쌍 → post5 41쌍 · `p` 0.5160 → post6 161쌍 · `p` 0.4914 → post7 266쌍 · `p` 0.4064 → "
        f"**이번({len(rows)}건) {a5['comp']}쌍 · `p` {a5['p']:.4f}**")

    # ── §3-1. D-1 세 수 ────────────────────────────────────────────────
    ns8 = [r["N"] for r in new8]
    ps8, drop8 = pairset([r["dd5"] for r in new8], DELTA)
    v8, c8 = statV(ns8, ps8)
    say()
    say("### §3-1. 🆕 `D-1` — 비교가능 쌍 «세 수» (`PREREG_POST8.md` §1 (나) 3 · PD-19 · `ANC-P3` 게이트 분모)\n")
    say("| 수 | 값 | 비고 |")
    say("|---|---|---|")
    say(f"| ① 그 글 «단독»(post8 주 표본 {len(new8)}건끼리) | **{c8}** | 차수 {sorted(ns8)} — N 이 다른 쌍 없음 · "
        f"δ 로 버린 쌍 {drop8} · `V` = {v8} |")
    say(f"| ② 누적(창5 · 동률 대역 제외 후 · {len(rows)}건) | **{a5['comp']}** | §2 주 판정 행 |")
    say(f"| ③ 게이트 판정에 쓴 수(= ②) | **{a5['comp']}** | 문턱 {PAIR_THRESHOLD} ⇒ "
        f"{'열림' if a5['comp'] >= PAIR_THRESHOLD else '닫힘'} |")
    say()
    say(f"**누적 비교가능 쌍 = {a5['comp']}**")
    say()
    say("- **그 글 열 비교가능 쌍 0(구성 · exact 4건 전부 N=1)** — 값을 보고 닫은 것이 아니라 저자의 체결 차수 서술이 «구성»으로 닫았다"
        "(PD-13 · PD-19). 🔴 `approx`(코데즈 N=2)를 넣어 그 글 열을 채우는 경로는 쓰지 않는다(PD-21).")
    say("- 🔴 이 셋은 `ANC-` 레인(`run_anchor_redesign.py --mode post8`)이 `ANC-P3` 게이트(40)에 쓰는 수다 — "
        "`ANC-P3` 의 판정 자체는 그 레인이 낸다(이 문서는 `ANC-P3` 를 판정하지 않는다).")

    # ── §4. T2 ─────────────────────────────────────────────────────────
    say()
    say("## §4. `LAD-T2` (반증축 · 필수) — `DD/sigma20` 정규화\n")
    sub = [r for r in rows if r["sig"] is not None]
    drop = [r["nm"] for r in rows if r["sig"] is None]
    say(f"B-4: sigma20 없는 건은 T2 표본에서 통째로 제외. **표본 {len(sub)}건** "
        f"(제외 {len(drop)}건: {', '.join(drop) if drop else '없음'} — 값을 보고 뺀 것이 아니라 «구성»이다).\n")
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
        say(f"- ⇒ 정규화축 `p`({p_n:.4f}) **<** 원축 `p`({p_o:.4f}) ⇒ 문언상 `PREREG_BUYLADDER.md` §3 **가설 B** 쪽. "
            "🔴 **부호뿐이다**(차이 자체는 검정되지 않았다) · `PREREG_BUYLADDER` 계열은 🔒 결정 ④로 **종결** ⇒ **기록만**.")
    else:
        say(f"- ⇒ 정규화축 `p`({p_n:.4f}) **>=** 원축 `p`({p_o:.4f}) ⇒ **가설 B 는 지지 없음.**")
    say("- 계열 값 나란히(인쇄값): post5 원축 0.6767 · 정규화축 0.5562 → post6 0.5185 · 0.7626 → post7 0.3947 · 0.6361")

    # ── §5. T3 ─────────────────────────────────────────────────────────
    say()
    say("## §5. `LAD-T3` (반증축 · 필수) — 축을 「등록일 → 발행일 경과 거래일」로\n")
    say("B-3: 경과일은 %p 가 아니므로 동률 대역 = **정확히 같은 값만 제외**(delta_E = 0).\n")
    say(HDR)
    say(SEP)
    a_t3 = run_axis("T3 `경과 거래일 E`", ns_all, [float(r["E"]) for r in rows], 0.0)
    say()
    say("- 경과일 분포(post8 주 표본): " + " · ".join(f"{r['nm']} {r['E']}" for r in new8))
    if a_t3["p"] < 0.05:
        say(f"- ⇒ 🔴🔴 **T3 `p` = {a_t3['p']:.4f} < 0.05** ⇒ 사전등록(§5-2)대로 "
            "***`V` 는 사다리가 아니라 「오래 들고 있으면 차수가 는다」는 시간 효과를 재고 있다*** ⇒ "
            "**`LAD-T1` 영구 취소**(§5-2 「T1 지지를 취소한다」 · `PREREG_POST6.md` §2-4 「`p < 0.05` 로 내려가면 T1 은 영구 취소」).")
    else:
        say(f"- ⇒ T3 `p` = {a_t3['p']:.4f} >= 0.05 ⇒ 시간 효과로 대체 설명되지 않는다"
            "(**`LAD-T1` 영구 취소** 사유 없음 · 취소 축이라 「통과」에 ✅ 를 쓰지 않는다 — **미발동**).")
    say(f"- **부호 감시**(`RESULTS_LADDER_TRANCHE.md` §10 승계 · post5 0.2008 < 0.5160 · post6 0.1909 < 0.4914 · "
        f"post7 {POST7_T3_P:.4f} < {POST7_T1_P:.4f}): 이번 T3 `p` = **{a_t3['p']:.4f}** vs 창5 원축 `p` = **{a5['p']:.4f}** ⇒ "
        f"T3 가 원축보다 **{'낮다 — 부호 유지' if a_t3['p'] < a5['p'] else '낮지 않다 — 부호 유지되지 않음'}**"
        f"({'4글 연속 관찰' if a_t3['p'] < a5['p'] else '3글 연속이 끊겼다'}). "
        "🔴 추세로 읽지 않는다(표본이 매회 통째로 커진다).")

    # ── §6. 민감도 — 창5 절단 제외 (항등) ─────────────────────────────
    say()
    say("## §6. 민감도 — **창5 절단 제외** (PD-12 2번 · `P6-창5절단가드-B`)\n")
    if trunc_all:
        say(f"- 🔴 절단 건 {len(trunc_all)}건이 있다 — " + ", ".join(r["nm"] for r in trunc_all))
    else:
        say(f"- 🟢 **누적 풀 {len(rows)}건 중 창5 절단 = 0** ⇒ 제외 표본 = 주 표본 **항등**(`LAD-T1`·`T2`·`T3`·`LAD-P2` 전부 §2~§5·§8 과 같은 값). "
            "구분 불가(항등)임을 **명시 인쇄**하고 다른 정의로 «대체하지 않는다»(PD-14 1 ③ 문형 · PD-23).")
    say("- 🔑 이 표는 `ANC-P3` 가 쓰는 창5 `L₅` 와 같은 창·같은 제외 규칙이다 — 그 레인은 `build_rows()` 를 import 해 쓴다.")

    # ── §7. 민감도 — 2번째 사이클 제외 (B-7) ──────────────────────────
    say()
    say("## §7. 민감도 (B-7 + `PREREG_POST6.md` §1-5) — **같은 종목 2번째 사이클 제외** (🔴 `approx` 민감도와 «따로»)\n")
    sub2 = [r for r in rows if not r["second"]]
    excl2 = [r for r in rows if r["second"]]
    say("- 제외 대상: " + " · ".join(f"{r['nm']}({r['post']} · {r['d0']})" for r in excl2) + f" ⇒ 표본 **{len(sub2)}건**")
    say("- **`P6-PRIOR_CYCLE_IN_WINDOW`**(PD-3 표) — 이번 글: " + " · ".join(f"{k} = **{v}**" for k, v in PRIOR_CYCLE_FLAG_POST8.items()))
    say("- 🔴🔴 **주 표본(`exact` 4) 안의 §1-5 재진입 = 0** — 원익은 `none`, 헥토·코데즈는 `approx` ⇒ post8 은 제외 대상에 "
        "**한 건도 더하지 않는다**(재진입 민감도의 post8 몫은 **항등** · INTAKE §5 머리말). 우리로(항목 내 2 사이클)는 "
        "B-7 이 아니다(🔒 #1-(ii) · 아래 §7-2 「우리로 제외」 인쇄만).")
    say("- 🔴 **두 민감도를 합치지 않는다** — 재진입 3건(원익·헥토·코데즈) 중 2건이 `approx` 라 §7-1 과 겹친다(PD-3 마지막 줄).\n")
    say(HDR)
    say(SEP)
    ns2 = [r["N"] for r in sub2]
    s3 = run_axis("창3", ns2, [r["dd3"] for r in sub2], DELTA)
    s5 = run_axis("**창5(주)**", ns2, [r["dd5"] for r in sub2], DELTA)
    sa = run_axis("창A", ns2, [r["dda"] for r in sub2], DELTA)
    s_t3 = run_axis("T3 `경과 거래일 E`(delta_E = 0)", ns2, [float(r["E"]) for r in sub2], 0.0)
    say()
    v2x = verdict_t1(s5)
    say(f"- 제외본 창5 비교가능 쌍 {s5['comp']} ({'>=' if s5['comp'] >= PAIR_THRESHOLD else '<'} 문턱 {PAIR_THRESHOLD}) ⇒ "
        f"판정 **{v2x}**")
    say(f"- 주 판정 **{v1}** ↔ 재진입 제외 **{v2x}** ⇒ "
        + ("**🔴 「재진입 의존」 — 어느 쪽도 지지로 선언하지 않는다(§1-5 2번)**" if v2x != v1 and v2x != "보류"
           else "**판정이 갈리지 않는다**" if v2x == v1
           else "**제외본은 게이트 미달이라 이 민감도만으로 판정하지 않는다**"))
    say(f"- T3 제외본 `p` = {s_t3['p']:.4f} (주 판정 {a_t3['p']:.4f}) · 창3 {s3['p']:.4f} · 창A {sa['p']:.4f}")

    # ── §7-1. approx 갈래 ─────────────────────────────────────────────
    say()
    say("## §7-1. 민감도 — `approx` 2건의 **갈래별** 값 (PD-4 2번 · `PREREG_POST6.md` §1-4 창 규약)\n")
    say("「8월말」 = `2026-08-21 ~ 2026-08-31` 의 **모든 거래일**을 갈래로 만들어 값을 전부 인쇄한다. **주 판정에는 넣지 않는다** "
        "(`RNK-D5`·`PREREG_S5_FUND_NEWS_OOS.md` §1-1·`PREREG_ANCHOR_REDESIGN.md` §2-3 · 판정 언어 금지).\n")
    for nm, code, N, label, lo, hi, n_expect, prev_reg in APPROX_BRANCHES:
        cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN %s AND %s ORDER BY date", (lo, hi))
        days = [str(r[0]) for r in cur.fetchall()]
        say(f"### {nm} ({code}) · N = {N} · 저자 표기 {label} = `{lo}` ~ `{hi}` · 🔂 재진입(직전 등록 {prev_reg})\n")
        say(f"- 거래일 갈래 **{len(days)}개** — PD-4 2번 실측 **{n_expect}개**와 "
            f"**{'일치 ✅' if len(days) == n_expect else '🔴 불일치 — 그대로 적는다'}**: {', '.join(days)}\n")
        say("| 갈래 `D` | H | 창5 봉수 | min_low(창5) | **DD5** | 창A 끝 | **DD_A** | `P6-WIN5_TRUNC` | 비고 |")
        say("|---|---|---|---|---|---|---|---|---|")
        n_tr = 0
        for d0 in days:
            cur.execute("SELECT date, high, low FROM daily_prices WHERE stock_code=%s "
                        "AND date >= %s AND date <= %s ORDER BY date", (code, d0, END))
            bars = cur.fetchall()
            if not bars:
                say(f"| {d0} | 🔴 봉 없음 | — | — | — | — | — | — | — |")
                continue
            H = bars[0][1]
            w5 = bars[:5]
            dd5 = 100 * (1 - min(b[2] for b in w5) / H)
            dda = 100 * (1 - min(b[2] for b in bars) / H)
            tr = 1 if len(w5) < TRUNC5_MIN_BARS else 0
            n_tr += tr
            note = ("🔴 **모순 갈래**(직전 등록 08-28 보다 이르다 · 「한번 더」와 논리 모순 · PD-3 — 좁히지 않고 표시만)"
                    if (nm == "헥토파이낸셜" and d0 < prev_reg) else
                    ("직전 등록일과 같은 날(PD-3)" if d0 == prev_reg else ""))
            say(f"| {d0} | {H:,.0f} | {len(w5)} | {min(b[2] for b in w5):,.0f} | **{dd5:.2f}%** | "
                f"{END} | **{dda:.2f}%** | {'**1**' if tr else '0'} | {note} |")
        say()
        say(f"- 창5 절단 갈래 = **{n_tr}/{len(days)}** — PD-12 표(전 갈래 완전)와 "
            f"**{'일치 ✅' if n_tr == 0 else '🔴 불일치 — 그대로 적는다'}**")
        say()
    say("- 🔴 **이 표는 판정이 아니다.** 값을 인쇄하되 판정 언어를 쓰지 않는다. §7 과 겹친다(두 건 다 재진입) — **합치지 않는다**.")

    # ── §7-2. 우리로 제외 (인쇄만) ────────────────────────────────────
    sub_w = [r for r in rows if not (r["post"] == "post8" and r["nm"] == "우리로")]
    say()
    say("## §7-2. 「우리로 제외」 — **인쇄만 · 판정 효과 없음** (🔒 #1-(ii) · PD-3 (ii) · PD-23)\n")
    say("🔴 우리로의 측정 등록(09-11)은 **사이클 1** 이라 §1-5 재진입 논거(*「자기 첫 사이클의 고가에 막힌다」*)가 서지 않는다"
        "(`P6-PRIOR_CYCLE_IN_WINDOW` = 0) ⇒ 이 값은 `재진입 의존`·`P8-갈래계수` 의 «갈래»로 세지 않는다.\n")
    say(HDR)
    say(SEP)
    w5 = run_axis(f"창5 · 「우리로 제외」({len(sub_w)}건)", [r["N"] for r in sub_w], [r["dd5"] for r in sub_w], DELTA)
    say()
    say(f"- 「우리로 제외」 창5: `V` = {w5['V']}/{w5['comp']} · `p` = {w5['p']:.4f} ⇒ (참고) {verdict_t1(w5)} — "
        "**인쇄만 · 판정에 쓰지 않는다**.")

    # ── §7-3. D-5 갈래 표 ─────────────────────────────────────────────
    say()
    say("## §7-3. 🆕 `D-5` · `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)` (`PREREG_POST8.md` §5 (나) 2 · PD-23 `LAD-` 행)\n")
    say(f"최소 n = **누적 비교가능 쌍 {PAIR_THRESHOLD}**(`PREREG_LADDER_TRANCHE.md` §5-1 동결값 그대로). "
        "최소 n 을 채운 갈래만 「답」으로 세고, 2 이상이 갈리면 [갈래 의존] 이다(등급 칸은 §6 단계).\n")
    say("| 갈래 | n(건 · 비교가능 쌍) | 답(`LAD-T1` · 창5) | 계수 |")
    say("|---|---|---|---|")
    br = [("**주**(누적 · 대체 후 · 창5)", len(rows), a5, "계수"),
          ("창5 절단 제외", len(rows) - len(trunc_all), a5 if not trunc_all else None,
           "🟢 **항등**(절단 0 — 주 갈래와 같은 표본)"),
          ("재진입 제외(B-7 · 글을 넘는 2번째 사이클 · post8 exact 몫 0)", len(sub2), s5, "계수"),
          ("post7 대체 «전»(빛과전자·범한퓨얼셀 = 절단 시점 값)", len(rows), r_before, "계수(B-5 3번 의무)"),
          ("「우리로 제외」", len(sub_w), w5, "🔴 **인쇄만 — 계수하지 않는다**(🔒 #1-(ii))")]
    counted = []
    for nm_, n_items, res, how in br:
        if res is None:
            say(f"| {nm_} | {n_items}건 | — | {how} |")
            continue
        ans = verdict_t1(res)
        say(f"| {nm_} | {n_items}건 · **{res['comp']}쌍** | **{ans}**(`p` {res['p']:.4f}) | {how} |")
        if how.startswith("계수") and res["comp"] >= PAIR_THRESHOLD:
            counted.append(ans)
    say(f"| `approx` 갈래(헥토·코데즈 7갈래) | 갈래별 건 값(§7-1) | — (판정 언어 금지 · 풀 검정 안 함) | 🔴 `D-3` 우선 — 계수 대상 아님 |")
    say(f"| (창 민감도) 창3 · 창A | {len(rows)}건 · {a3['comp']}쌍 · {aa['comp']}쌍 | {verdict_t1(a3)}(`p` {a3['p']:.4f}) · "
        f"{verdict_t1(aa)}(`p` {aa['p']:.4f}) | 창 민감도(§4-5 1 의무 · 주 창은 창5 동결) |")
    say()
    say(f"- 최소 n 을 채운 계수 갈래 = **{len(counted)}개** · 답 = {sorted(set(counted))} ⇒ "
        f"**{'갈리지 않는다 — 주 갈래의 답을 그대로 쓴다' if len(set(counted)) <= 1 else '🔴 갈린다 — [갈래 의존]'}**")

    # ── §7-4. D-3 ─────────────────────────────────────────────────────
    say()
    say("### §7-4. 🆕 `D-3` · `P8-approx의존신고` (`PREREG_POST8.md` §3 (나) 3 · PD-21)\n")
    say(f"「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 {N_EXACT_POST8} / `approx` 포함 분모 {N_EXACT_POST8 + 2}」 — "
        f"`LAD-` 의 최소 n(누적 쌍 40)은 `exact` 만으로 이미 {a5['comp']} ≥ 40 이다. "
        "(참고 · `ANC-P3` 그 글 열: `exact` 0쌍 / `approx` 포함 ≤ 5쌍(코데즈 N=2 × 나머지 5건 상한 · δ 제외 «전») — "
        "판정에 쓰지 않는다)")

    # ── §8. LAD-P1 ~ P3 ───────────────────────────────────────────────
    say()
    say("## §8. 개별 예측 `LAD-P1`~`P3` (§5-3 · **값 기록 · 기각 사유 아님**)\n")
    say(f"- **`LAD-P1`** 「저자가 체결 차수를 명시」 — 8번째 글 **항목 10건 중 차수 명시 10건**(`INTAKE` §2-10). "
        f"후속 3건은 신규 분모 밖 ⇒ **분모 정의 = 「DB 있는 신규 건」 = {N_NEW_POST8}건 ⇒ {N_NEW_POST8}/{N_NEW_POST8} = 100%** "
        "(코드 **10/10** `daily_prices` 존재 — 액스비스 `0011A0` 포함 · PD-11) ⇒ ✅ **성립 · 5글 연속**"
        "(post4 6/6 → post5 6/6 → post6 10/10 → post7 10/10 → post8 7/7).")
    dd5_new = [r["dd5"] for r in new8]
    med_new = median(dd5_new)
    in_band = LAD_P2_LO <= med_new <= LAD_P2_HI
    say(f"- **`LAD-P2`** 「신규 건 `DD`(창5) 중앙값이 {LAD_P2_LO:.0f}~{LAD_P2_HI:.0f}%」 — 🔴 **주 분모 = 신규 ∧ `exact` {len(new8)}건** "
        "(`none` 1 은 `D` 가 없어 계산 자체가 안 선다 · `approx` 2 는 §7-1 갈래 표) — 값 = "
        + " · ".join(f"{r['nm']} {r['dd5']:.2f}%" for r in new8)
        + f" ⇒ 중앙값 **{med_new:.2f}%** ⇒ **{'✅ 구간 안' if in_band else '❌ 구간 밖'}** "
          f"(1회차 23.53% · post5 20.34% · post6 15.62% · post7 {POST7_P2_MEDIAN:.2f}%)")
    say(f"  - 절단 제외: 신규 절단 0 ⇒ **항등**. 하한까지 **{med_new - LAD_P2_LO:+.2f}%p** · 상한까지 {LAD_P2_HI - med_new:+.2f}%p — "
        "「구간 안이냐」만 묻는 예측이라 거리는 «다음 회차의 취약성»으로만 기록한다.")
    dd5_w = [r["dd5"] for r in new8 if r["nm"] != "우리로"]
    med_w = median(dd5_w)
    say(f"  - 「우리로 제외」(인쇄만 · 🔒 #1-(ii)): {len(dd5_w)}건 중앙값 **{med_w:.2f}%** ⇒ "
        f"{'구간 안' if LAD_P2_LO <= med_w <= LAD_P2_HI else '구간 밖'} — 판정에 쓰지 않는다.")
    say(f"- **`LAD-P3`** 「`first_only`(1차만 체결) 건 >= 1」 — 8번째 글 신규 **{len(FIRST_ONLY_POST8_NEW)}건**"
        f"({' · '.join(FIRST_ONLY_POST8_NEW)} · 전부 N = 1 · 그중 `exact` **{len(FIRST_ONLY_POST8_EXACT)}건**) ⇒ ✅ **성립** "
        "(post4 0 → post5 1 → post6 3 → post7 6 → **post8 6**). 🔴 `REC-Z4` 귀결(즉시 `L` 판정)은 🔒 결정 ④로 소멸"
        "(PD-13) ⇒ 이 축은 **「건 수」만 기록**한다. 🔑 §1-0 의 「exact 4 전부 N=1」과 **같은 사실**이다 — 독립 증거로 세지 않는다.")

    # ── §9. 모호·한계 ─────────────────────────────────────────────────
    say()
    say("## §9. 모호 지점 (양쪽 인쇄 · 「모호」 표기) · 한계\n")
    say("1. **post7 절단 값 대체**(§1-1b) — 「절단 시점 값 → 대체 값」과 대체 전/후 `V`·`p` 를 **둘 다** 적었다. "
        "🔴 `PREREG_LADDER_TRANCHE.md` §4-2 B-5 2번 *「옛 값은 산출물에 남기지 않는다」* ↔ 3번 *「덮어쓰기 전/후 V·p 를 둘 다 의무 인쇄」*"
        "·5번 *「「절단 시점 값」 표기를 유지」* — 이 산출물은 post7 판 선례(§1-1b 인용 열)대로 **옛 값을 «인용·표기»로만** 남기고 "
        "누적 계산에는 대체값만 넣었다(모호 · 양쪽 충족 쪽).")
    say("2. **읽은 시각 ①**(§0) — 벽시계라 재실행마다 다르다. byte 재현 의무와 충돌해 **최초 실행 시각을 잇는** 방식을 썼다(재량 · 지문이 움직이면 새 시각).")
    say("3. **우리로(항목 내 2 사이클)** — 포함(주) · 「우리로 제외」 인쇄만(§7-2 · 🔒 #1-(ii)). 레그를 두 사이클로 배분할 근거가 "
        "원문에 없지만 **이 축은 레그를 쓰지 않는다**(등록 사건의 N·창5 만 잰다).")
    say("4. **`approx` 2건** — 갈래별 값만(§7-1). 헥토 5/7 갈래(08-21~08-27)는 「한번 더」와 논리 모순 — 좁히지 않고 표시만(PD-3).")
    say("5. **`H` = 등록일 고가는 가정** — `ANC-` 레인(`run_anchor_redesign.py --mode post8`) 산출물과 함께 읽어야 한다(`PREREG_POST6.md` §4 #44).")
    say("6. 🔴 **제도 경계(09-14)가 계열 중간에 들어왔다** — 누적 풀이 «두 제도»를 섞는다(§0-2 걸침 줄). 분모를 쪼개지 않았다"
        "(`PREREG_POST8.md` §14 · 쪼개려면 새 사전등록). ⚠️ `overtime_daily` 는 09-14 `ovtm_vol>0` 0 · 09-15 이후 행 없음 ⇒ 시간외분을 "
        "`H`·`L` 에서 뺄 수 없다 · 15:30 마감 분봉 소실 ⇒ `minute_candles` 로 정규장 상한을 만들 수 없다(관리자 실측 인용 · PD-27 (바)).")
    say("7. `V` 는 개수이고 귀무에서 비교가능 쌍 수가 함께 흔들린다(관측 vs 귀무 평균을 같은 표에 인쇄했다).")
    say("8. **글 간 풀링이 국면을 섞는다**(post4~post8 = 5주) · 표본은 저자가 올리기로 «고른» 매매다(`PREREG_SELECTION.md` §0).")
    say("9. `N` 은 저자 서술 의존(「N차 매수된 상태」를 「N차까지 체결」로 읽었다 · 총 분할 수는 모른다).")
    say("10. **`prog_ver` 를 공변량으로 쓰지 않는다** ⇒ D-8 수준 목록 의무 해당 없음(PD-26). `n_up` sd 를 인쇄하지 않는다 ⇒ D-6 해당 없음.")
    say("11. **새 예측을 만들지 않았다** — δ·창5·게이트 40·시드·순열 표본 수 전부 동결값 그대로다.")

    NUMBERS.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    print(f"\n[written] {NUMBERS.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())

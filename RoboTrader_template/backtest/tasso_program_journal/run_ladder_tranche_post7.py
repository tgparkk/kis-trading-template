# -*- coding: utf-8 -*-
"""매수 사다리 「체결 차수 ↔ 낙폭」 정렬 축 — **7번째 글 누적 재계산** (`LAD-T1`·`T2`·`T3` · `LAD-P1`~`P3`).

준거(전부 동결본 · 규칙 변경 0):
  · `PREREG_LADDER_TRANCHE.md` §4(정의)·§5(예측·결정규칙)
  · `PREREG_POST6.md` §2-4(δ 1.0%p · 창5 · 게이트 40 불변 · 누적 쌍 재계산 · T3 부호 감시 ·
    DB 최신 봉 명기 · B-1·B-7 승계 · `LAD-P1` 분모 병기) · §4 표 #21~#24 · §1-4(창 규약) · §1-6(절단 가드)
  · `RESULTS_LADDER_TRANCHE.md` §1(B-1~B-8 해석 결정) · §7(절단 창5 가짜 숫자 전례) · §8 · §10
  · `PREDECISION_2026-09-15_post7.md` PD-1(창 종료 = **2026-09-11**) · PD-2(후속 3건 등록일 축 제외)
    · PD-3(재진입 3건) · PD-4(등록일 정밀도 `exact` 6 · `approx` 2 · `none` 2) · PD-7(라벨·B-2) ·
    PD-12(창5 절단 2건 + post6 절단 2건 값 «대체») · PD-13(`first_only`)
  · `INTAKE_2026-09-15_post7.md` §1(항목 13건)·§2-12(차수 분포)·§5(이 축의 대상 표본) ·
    `LABELS_2026-09-15_post7.md`

🔴 이 스크립트는 **동결 산출물 생성기 `run_ladder_tranche.py` 를 «수정하지 않는다»**. 그리고
   **`run_ladder_tranche_post6.py` 도 «수정하지 않는다»**. 통계 핵(`pairset`·`statV`·`permute_null`)과
   표 행 포맷(`run_axis`)은 전자에서, 누적 목록(`ITEMS` 22건)과 가드·판정 함수
   (`guard_a_fires`·`verdict_t1`·`median`)는 후자에서 **그대로 import 해 재사용**한다.
   이 파일이 새로 정의하는 것은 **post7 목록과 post7 고유 인쇄**뿐이다
   ⇒ 기존 22건의 계산 «경로»는 한 줄도 달라지지 않는다.
   🔑 ***「옛 산출물 byte 불변」은 옛 파일을 안 고치는 것으로 지킨다 — 옛 산출물을 다시 쓰지 않는다.***

계산 «전»에 고정된 해석 결정 — **전부 승계, 신설 0**:
  B-1  창A 의 「글 발행일」 = 그 항목이 실린 글의 발행일. **post7 = 2026-09-12(토) = 휴장**
       ⇒ 창A 는 **마지막 거래일 2026-09-11(금)** 에서 끝난다(PD-1 · post4 08-22 토 · post5 08-29 토 전례).
       코드에서는 `pub_eff = min(pub, END)` 가 그 절단을 «구조로» 준다(post6 승계 · 새 분기 0).
  B-2  매도 쪽만 수동인 건은 §4-1 carve-out 으로 **포함**한다. 🔴 이번 글 `MANUAL` 2건
       (아난티·우리기술투자)은 그 carve-out 대상이라 **라벨을 이유로는 빠지지 않는다** —
       두 건이 이 축에서 빠지는 사유는 **후속(PD-2)** 이다. 두 사유를 섞어 적지 않는다(§1-0).
  B-3  δ 는 DD 축(%p)의 정의다. T3 축(경과 거래일)은 **정확히 같은 값만 제외**(delta_E = 0).
  B-4  T2 는 **같은 표본·같은 쌍 집합**에서 순서만 정규화 축으로 바꾼다. sigma20 없는 건은 통째로 제외.
       부수로 `delta_norm = 1.0%p / median(sigma20)` 직접 적용 민감도도 인쇄.
  B-5  서로 다른 배정이 200,000 을 넘으면 시드 고정 200,000 표본(`NULL_SEED` = 20260815 — 기존 값 그대로).
  B-6  경과 거래일 E = `[D, 발행일]` 거래일 수(양끝 포함 · `daily_prices` 거래일 달력).
  B-7  같은 종목 2번째 사이클은 별개 관측으로 두되 **제외 민감도를 필수 인쇄**
       (이번 누적: 한켐 post5 · 코데즈컴바인 post5 · 지투파워 post6 · 현대약품 post6
        + **post7 빛과전자** — 주 표본 안. `approx` 갈래의 지투파워(3번째 사이클)·한국화장품제조는 §7-1).
       🔴 재진입 3건 중 **2건이 `approx`** 라 재진입 제외 민감도와 `approx` 제외 민감도가 **겹친다**
       ⇒ **두 민감도를 «따로» 인쇄하고 합치지 않는다**(PD-3 마지막 줄).
  B-8  창3·창5 의 「D+k거래일」은 **그 종목의 봉**으로 센다.
  PD-2 「기존 건 후속」 3건(한라캐스트·아난티·우리기술투자)은 **등록일 축 신규 분모에서 제외**
       (이중계상 금지) ⇒ post6 행은 그대로 둔다.
  PD-4 **등록일 정밀도가 처음 갈린다** — 신규 10 ≠ `exact` 6. 창 `[D, END]` 를 세우려면 `D` 가 있어야
       하므로 **주 표본 = `exact` 6**. `approx` 2 는 **갈래별 민감도**(§7-1) · `none` 2 는 등록일 축 밖.
       🔴 가드-A 의 «분모»만은 post6 PD-11 3번 문언이 *「이번 글 신규 건」* 으로 못박아 두었으므로
       **10** 을 쓴다 — 표본 수(6)와 가드 분모(10)가 이번 회차에 처음 갈린다. 둘 다 인쇄한다.
  PD-12 창5 `[D, D+4거래일]` 절단(빛과전자 4봉 · 범한퓨얼셀 3봉) = **분모에 넣고** 가용 봉으로 DD5 계산 ·
       플래그 `P6-WIN5_TRUNC`·건수·봉수 의무 인쇄 · 절단 2건 **제외 민감도**를 `LAD-T1`·`T2`·`T3`·`LAD-P2`
       전부에 인쇄 · `P6-창5절단가드-A`(절단 건 / 이번 글 신규 건 ≥ 1/3 ⇒ ⛔) ·
       `P6-창5절단가드-B`(제외 민감도가 `LAD-T1` 판정을 뒤집으면 ⇒ ⛔) · 이번 값은 **「절단 시점 값」**.
  PD-12-4 **post6 절단 2건(현대약품·비에이치)의 값 «대체»** — 주 창 09-11 에서 두 건의 창5 가
       **완전**해진다 ⇒ 이번 회차에 값을 대체하고 **「절단 시점 값 → 대체 값」을 둘 다** 적는다.
       🔴 이것은 `RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md` 를 «고치는 것이 아니다» — 그 파일은
       byte 불변이고, 대체값은 **이 산출물 안에서만** 인쇄된다.

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
    NPERM,            # 200,000
    NULL_SEED,        # 20260815 — 기존 값 그대로
    PAIR_THRESHOLD,   # 40 (§5-1)
    pairset,
    permute_null,
    run_axis,
    statV,
)
# 🔴 post6 판(수정 금지 파일)에서 **누적 목록과 가드·판정 함수**를 그대로 가져온다 — 새 코드 0줄.
import run_ladder_tranche_post6 as P6
from run_ladder_tranche_post6 import (
    GUARD_A_DEN,
    GUARD_A_NUM,
    ITEMS as ITEMS_CUM22,      # 누적 22건 (post4 6 + post5 6 + post6 10) — 그대로
    TRUNC5_MIN_BARS,           # 5 (창5 = D + 4거래일)
    guard_a_fires,
    median,
    verdict_t1,
)

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
# ⚠️ 순서 주의 — `run_ladder_tranche_post6` 를 import 하는 순간 그 모듈이 `LAD.OUT` 을 자기 버퍼로
#    묶는다. 이 재지정은 **그 import «뒤»** 에 와야 `run_axis` 의 표 행이 이 실행의 버퍼로 들어온다.
LAD.OUT = OUT

END = "2026-09-11"          # 창 종료 (PD-1 · 실행 시 재확인) — 발행일 09-12(토) 휴장 ⇒ 마지막 거래일
PUB7 = "2026-09-12"         # 7번째 글 발행일 = **토요일 = 휴장** (B-1 ⇒ 창A 는 END 에서 끝난다)
CUM_PAIRS_POST6 = 161       # `RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md` §2 — 누적 비교가능 쌍(창5)
POST6_T1_V, POST6_T1_P = 80, 0.4914     # post6 판정값 (나란히 인쇄용)
POST5_T1_V, POST5_T1_P = 21, 0.5160     # post5 판정값 (계열 인쇄용)
CUM_PAIRS_POST5 = 41

LAD_P2_LO, LAD_P2_HI = 15.0, 35.0       # `LAD-P2` 구간 (동결)
POST6_P2_MEDIAN = 15.62                 # post6 신규 중앙값 — 하한까지 **0.62%p** 였다(보고서 §6 #7)
POST6_P2_MEDIAN_EXTRUNC = 15.47         # post6 절단 2건 제외본

N_NEW_POST7 = 10            # 🔴 가드-A 분모 = 「이번 글 신규 건」 (post6 PD-11 3번 문언 그대로)
N_EXACT_POST7 = 6           # 주 표본 (PD-4 1번)

# (종목, 코드, 등록일, 차수 N, 글, 발행일, 두번째 사이클?, 비고)
# `INTAKE_2026-09-15_post7.md` §1 — 신규 10건 중 **`exact` 6건**(창 `[D, END]` 를 세울 D 가 있는 건).
ITEMS_POST7_NEW = [
    ("서산",         "079650", "2026-09-03", 1, "post7", PUB7, False,
     "first_only·`exact`·프리셋 사분위수 Q2~MAX/표준형(PD-9)"),
    ("강동씨엔앨",   "198440", "2026-09-03", 1, "post7", PUB7, False,
     "first_only·`exact`·🔴 DB명 「강동씨앤엘」(PD-10 4 · 이름 한 글자 차)"),
    ("로보티즈",     "108490", "2026-09-04", 1, "post7", PUB7, False,
     "first_only·미완결·`exact`"),
    ("해치텍",       "0155E0", "2026-09-07", 4, "post7", PUB7, False,
     "🔴 신규 상장(첫 봉 08-25)·`[D-19,D]` 10/20 절단·`exact`"),
    ("빛과전자",     "069540", "2026-09-08", 1, "post7", PUB7, True,
     "재진입(post3 #6 08-05)·`P6-PRIOR_CYCLE_IN_WINDOW`=0·first_only·미완결·🔴 창5 절단"),
    ("범한퓨얼셀",   "382900", "2026-09-09", 1, "post7", PUB7, False,
     "first_only·미완결·🔴 창5 절단·「10.8%」 소수 1자리(PD-10 3)"),
]
ITEMS = list(ITEMS_CUM22) + ITEMS_POST7_NEW

# 🔴 `approx` 2건 — 「N월 초/말」 창 규약(`PREREG_POST6.md` §1-4)의 **첫 발동**(PD-4 2번).
#    주 표본에 넣지 않고 **갈래별 민감도**로만 인쇄한다. (종목, 코드, N, 저자 표기, 창 시작, 창 끝, 갈래수 기대)
APPROX_BRANCHES = [
    ("지투파워",         "388050", 3, "「9월 초」", "2026-09-01", "2026-09-10", 8),
    ("한국화장품제조",   "003350", 1, "「8월 말」", "2026-08-21", "2026-08-31", 7),
]

# 🔴 등록일 축 «밖» — 사유를 **라벨과 분리해** 적는다(B-2 · PD-2 · PD-4 3번).
OUT_OF_REGDAY_AXIS = [
    ("한전기술",     "052690", 4, "`SL`",
     "`none` — 등록일 «문장»이 없다(PD-4). 「8월 26일」은 급등 사유일이고 등록 문장과 다른 줄이라 "
     "승격하지 않는다 ⇒ 창 `[D, END]` 를 세울 `D` 가 없다"),
    ("한전산업",     "130660", 5, "`SL`", "`none` — 〃"),
    ("한라캐스트",   "125490", 5, "`MIX`",
     "후속(post6 #3) — PD-2 이중계상 금지 · 원장 `reg_date` 비움. "
     "🔴 연결 시퀀스가 비증가와 «양립하지 않는다»(post6 −2.89 → post7 11.22)지만 이 축은 낙폭만 잰다"),
    ("아난티",       "025980", 1, "`MANUAL`",
     "후속(post6 #5) — PD-2. 🔴 **B-2 carve-out 은 `MANUAL` 을 LAD 에서 빼지 «않는다»** — "
     "이 건이 빠지는 사유는 라벨이 아니라 **후속**이다(두 사유를 섞지 않는다)"),
    ("우리기술투자", "041190", 4, "`MANUAL`", "후속(post6 #11) — 〃"),
]

# `INTAKE` §2-3 · PD-13 — `first_only`(차수 N = 1) 신규 6건(그중 `exact` 5) + 후속 아난티 1
FIRST_ONLY_POST7_NEW = ["서산", "강동씨엔앨", "로보티즈", "빛과전자", "한국화장품제조", "범한퓨얼셀"]
FIRST_ONLY_POST7_EXACT = ["서산", "강동씨엔앨", "로보티즈", "빛과전자", "범한퓨얼셀"]
# `P6-PRIOR_CYCLE_IN_WINDOW` (PD-3 표) — 🔴 주 표본 안은 빛과전자 1건뿐이고 그 값이 **0** 이다.
PRIOR_CYCLE_FLAG_POST7 = {"지투파워": 1, "한국화장품제조": 1, "빛과전자": 0}
PRIOR_CYCLE_IN_MAIN = ["빛과전자"]          # `exact` 분모 안 재진입 (INTAKE §5 머리말)

# 🔴 PD-12 4번 — post6 에서 「절단 시점 값」으로 인쇄된 두 건. **재계산이 아니라 인용**이다.
#    출처 = `RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md` §1-1·§8 (그 파일은 손대지 않는다).
POST6_TRUNC_ASOF = {
    "현대약품": dict(d0="2026-09-01", n5_asof=4, dd5_asof=24.00),
    "비에이치": dict(d0="2026-09-01", n5_asof=4, dd5_asof=14.00),
}

HDR = ("| 축 | `V_obs` | 비교가능 쌍 | 버린 쌍 | 귀무 평균 `V` | **`p = P(V<=V_obs)`** | "
       "`P(V=0)` | 귀무 평균 비교가능 쌍 |")
SEP = "|---|---|---|---|---|---|---|---|"


def say(s=""):
    print(s)
    OUT.append(s)


def build_rows(cur, items, cal, end=END):
    """건별 `(H, DD3, DD5, DD_A, E, sigma20, trunc5)` — post6 §1 계산 경로를 그대로 옮긴 것.

    🔑 `ANC-` 레인이 창5 `L₅` 를 필요로 하면 이 함수를 import 해 쓴다(새 코드 0줄 원칙).
    """
    rows = []
    for idx, (nm, code, d0, N, post, pub, second, memo) in enumerate(items, 1):
        pub_eff = min(pub, end)          # 🔴 B-1 — 발행일이 휴장이면 창A 는 END 에서 끝난다
        cur.execute("SELECT date, high, low FROM daily_prices WHERE stock_code=%s AND date >= %s "
                    "AND date <= %s ORDER BY date", (code, d0, end))
        bars = cur.fetchall()
        H = bars[0][1]
        w3, w5 = bars[:3], bars[:5]
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
    return rows


def main():  # noqa: C901
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    say("# RESULTS_LADDER_TRANCHE_POST7_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_ladder_tranche_post7.py` · 통계 핵·표 포맷은 `run_ladder_tranche.py` 에서, "
        "누적 목록(22건)·가드·판정 함수는 `run_ladder_tranche_post6.py` 에서 import "
        "(**두 파일 다 수정하지 않았다**)")
    say("사전등록 `PREREG_LADDER_TRANCHE.md`(2026-08-22 동결) · `PREREG_POST6.md` §1-4·§1-6·§2-4·§4 #21~#24 · "
        "해석 결정 `RESULTS_LADDER_TRANCHE.md` §1 B-1~B-8 + "
        "`PREDECISION_2026-09-15_post7.md` PD-1·PD-2·PD-3·PD-4·PD-7·PD-12·PD-13")
    say(f"`delta` = {DELTA}%p · `NULL_SEED` = {NULL_SEED} · 순열 표본 {NPERM:,} · "
        f"판정 문턱 = 누적 비교가능 쌍 {PAIR_THRESHOLD} — **셋 다 동결 그대로 손대지 않았다**")

    # ── §0. 실행 환경 · 창 종료 규약 ─────────────────────────────────────
    cur.execute("SELECT max(date) FROM daily_prices")
    db_max = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (db_max,))
    db_max_rows = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (END,))
    end_rows = cur.fetchone()[0]
    say()
    say("## §0. 실행 환경 · 창 종료 규약 (PD-1 5번 표기 의무)\n")
    say(f"**창 종료 {END} = 발행일({PUB7} 토) 휴장 ⇒ 마지막 거래일 · B-1(`WRC-` 포함 전 축)** — "
        "고른 값이 아니라 동결 문언이 지시한 한 값이다(PD-1 3번).")
    say(f"**실행 시 `max(date)` = `{db_max}` · 그 날짜 행수 {db_max_rows:,}** "
        f"(창으로 쓰지 «않는다» · PD-1 2번 표기 의무) · 창 종료 {END} 행수 **{end_rows:,}**")
    say(f"- 스크립트 `END` = {END} · DB 최신 봉과 "
        f"{'**일치**' if str(db_max) == END else f'**불일치**(DB 가 {db_max} 로 전진했다 — 창은 {END} 로 고정)'}"
        f" · `adj_factor` 산술 0건 · 라이브 트리 import 0건 · DB 는 SELECT 만")
    say("🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2) — 이 산출물은 기록이지 전략 후보가 아니다.")
    say("🔵 라벨 접두(§0-3 규약): 이 문서의 `T1`·`T2`·`T3`·`P1`~`P3` 은 전부 **`LAD-`** 축이다"
        "(`PREREG_LADDER_TRANCHE.md` §5). 이 글에서 쓰는 플래그·가드는 **`P6-`** 접두를 그대로 단다.")
    say("🔴 **새 예측을 만들지 않았다** — δ·창5·게이트 40·시드·순열 표본 수 전부 동결값 그대로다.")

    # 거래일 달력 (B-6)
    cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN '2026-07-01' AND %s "
                "ORDER BY date", (END,))
    cal = [r[0] for r in cur.fetchall()]

    # ── §1-0. 표본 구성 — 「신규 10」과 「주 표본 6」이 처음 갈린다 ──────────
    say()
    say("## §1-0. 표본 구성 — 🔴 **「이번 글 신규 10」과 「주 표본 6」이 이 계열 최초로 갈린다** (PD-4)\n")
    say("post6 까지는 신규 건이 **전부 `exact`** 였다 ⇒ 두 수가 같아서 구분할 필요가 없었다. "
        "post7 에서 처음 갈린다. **두 수를 한 수로 합치지 않는다.**\n")
    say("| 구분 | 건 | 이 축에서의 지위 |")
    say("|---|---|---|")
    say(f"| 신규 ∧ `exact` | **{N_EXACT_POST7}** | 🟢 **주 표본** — 창 `[D, {END}]` 를 세울 `D` 가 있다 |")
    say("| 신규 ∧ `approx` | **2** | ⚪ **갈래별 민감도**(§7-1) — `PREREG_POST6.md` §1-4 창 규약 첫 발동 |")
    say("| 신규 ∧ `none` | **2** | 🔴 등록일 축 밖 — `D` 가 없다 |")
    say("| 기존 건 후속 | **3** | 🔴 등록일 축 밖 — PD-2 이중계상 금지 |")
    say(f"| **이번 글 신규 계** | **{N_NEW_POST7}** | 🔴 **가드-A 의 «분모»는 이 수**(post6 PD-11 3번 문언 그대로) |")
    say("| 항목 계 | 13 | `INTAKE` §1 |")
    say()
    say("### 등록일 축 «밖» 5건 — **사유를 라벨과 분리해 적는다**\n")
    say("| 종목 | 코드 | N | 라벨 | 밖인 사유 |")
    say("|---|---|---|---|---|")
    for nm, code, N, lbl, why in OUT_OF_REGDAY_AXIS:
        say(f"| {nm} | {code} | {N} | {lbl} | {why} |")
    say()
    say("🔴 **B-2 carve-out 재확인**: `RESULTS_LADDER_TRANCHE.md` §1 **B-2** 는 *「매도 쪽만 수동이면 "
        "포함」* 이다 ⇒ **`MANUAL` 2건은 이 축에서 라벨을 이유로 빠지지 «않는다»**(PD-7 마지막 줄: "
        "*「두 건 다 매수 쪽 수동 서술이 없다 ⇒ **LAD 분모 포함**(단 둘 다 후속이라 등록일 축 밖)」*). "
        "***빠지는 사유는 후속이고, 그 둘을 섞어 적으면 다음 회차에 「`MANUAL` 은 LAD 에서 뺀다」로 읽힌다.***")

    # ── §1. 건별 원표 ─────────────────────────────────────────────────────
    say()
    say("## §1. 건별 원표 — `(종목, 글, N, H, min_low, DD)` (§4-5 의무 인쇄 4)\n")
    say(f"`H` = 등록일 고가 · `DD` = 1 - min(low over 창) / H · 창5 = `[D, D+4거래일]`(그 종목의 봉 · B-8) · "
        f"창A = `[D, 그 글의 발행일]`(post7 은 휴장 ⇒ **{END}** · B-1)\n")
    say("| # | 종목 | 글 | N | 등록일 | H | 창3 봉수 / min_low / **DD3** | "
        "창5 봉수 / min_low / **DD5** | 창A 끝 / min_low / **DD_A** | 경과거래일 E | sigma20 | "
        "`P6-WIN5_TRUNC` | 비고 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|")

    rows = build_rows(cur, ITEMS, cal, END)
    for r in rows:
        memo = r["memo"]
        if r["post"] == "post6" and r["nm"] in POST6_TRUNC_ASOF:
            memo += " → 🆕 **post7 창에서 완전 · §1-1b 값 대체**"
        sig_s = "—" if r["sig"] is None else f"{r['sig']:.4f}"
        say(f"| {r['i']} | {r['nm']} | {r['post']} | **{r['N']}** | {r['d0']} | {r['H']:,.0f} | "
            f"{r['n3']} / {r['l3']:,.0f} / **{r['dd3']:.2f}%** | "
            f"{r['n5']} / {r['l5']:,.0f} / **{r['dd5']:.2f}%** | "
            f"{r['pub']} / {r['la']:,.0f} / **{r['dda']:.2f}%** | {r['E']} | {sig_s} | "
            f"{'**1**' if r['trunc5'] else '0'} | {memo} |")

    new7 = [r for r in rows if r["post"] == "post7"]
    old = [r for r in rows if r["post"] != "post7"]
    trunc = [r for r in new7 if r["trunc5"]]

    say()
    say(f"- 표본 **{len(rows)}건** = 기존 누적 {len(old)}(post4 6 + post5 6 + post6 10) + "
        f"**7번째 글 주 표본 {len(new7)}건**(신규 ∧ `exact`). "
        "「기존 건 후속」 3건과 `none` 2건은 **등록일 축 밖**(§1-0) · `approx` 2건은 **§7-1 갈래 민감도**.")
    say(f"- 7번째 글 주 표본의 차수 다중집합 = {sorted(r['N'] for r in new7)} "
        "(`INTAKE` §2-12 **신규 10건** 분포 1:6 · 3:1 · 4:2 · 5:1 중 `exact` 부분) — "
        "🔴 post6(1:3·2:1·3:3·4:2·5:1)보다 **1차에 몰려 있다** ⇒ 비교가능 쌍 수가 «구성으로» 줄어든다.")

    # ── §1-1. 창5 절단 (PD-12) ───────────────────────────────────────────
    say()
    say("### §1-1. 창5 절단 — `P6-WIN5_TRUNC` (PD-12)\n")
    say(f"- **절단 건수 = {len(trunc)}** / 이번 글 신규 {N_NEW_POST7}건 · "
        + (" · ".join(f"{r['nm']}({r['d0']} 등록 · 창5 **{r['n5']}봉** / 규정 {TRUNC5_MIN_BARS}봉 · "
                      f"DD5 = **{r['dd5']:.2f}%**)" for r in trunc) if trunc else "해당 없음"))
    say("- 이 값들은 **「절단 시점 값」**이다(PD-12 1번) — 다음 글에서 창5 가 완전해지면 «대체»한다"
        "(그 대체의 이번 회차 실행이 §1-1b 다).")
    say("- 절단 건은 **분모에 넣는다**(값을 보고 빼지 않는다 · PD-12 1번). 제외 민감도는 §6.")
    ga_main = len(trunc) / N_NEW_POST7
    ga_exact = len(trunc) / N_EXACT_POST7
    say(f"- **`P6-창5절단가드-A`**(절단 건 / **이번 글 신규 건** ≥ 1/3 ⇒ ⛔ 판정 불가): "
        f"**{len(trunc)}/{N_NEW_POST7} = {100*ga_main:.1f}%** vs 문턱 {GUARD_A_NUM}/{GUARD_A_DEN} = "
        f"{100*GUARD_A_NUM/GUARD_A_DEN:.1f}% ⇒ "
        f"**{'⛔ 발동' if guard_a_fires(len(trunc), N_NEW_POST7) else '미발동'}** "
        "(해치텍 창5 는 5봉 **완전**이라 분자에 안 들어간다)")
    say(f"  - 🔴🔴 **`exact` 분모 갈래**: **{len(trunc)}/{N_EXACT_POST7} = {100*ga_exact:.1f}%** ⇒ "
        f"**{'⛔ 발동 조건에 «닿는다»' if guard_a_fires(len(trunc), N_EXACT_POST7) else '미발동'}**. "
        "post6 PD-11 3번이 분모를 *「이번 글 신규 건」* 으로 **못박아 두었으므로 주 판정은 신규 10 을 쓴다** — "
        "***문턱을 넘는 갈래가 있다는 사실을 숨기지 않는다***(PD-12 3번).")
    say(f"  - `approx` 갈래 포함(§7-1): 지투파워가 8갈래 중 3갈래(D=09-08·09-09·09-10)에서 창5 4·3·2봉으로 "
        f"절단 · 한국화장품제조는 7갈래 전부 완전 ⇒ 분자에 넣어도 **3/{N_NEW_POST7} = "
        f"{100*3/N_NEW_POST7:.1f}%** ⇒ **{'⛔ 발동' if guard_a_fires(3, N_NEW_POST7) else '미발동 불변'}**(PD-12 5번).")
    say(f"  - 참고 병기(누적 분모): 절단 {len(trunc)} / 누적 {len(rows)}건 = "
        f"{100*len(trunc)/len(rows):.1f}% — 「참고」다. 판정 분모는 **이번 글 신규 건**이다.")
    say("  - 문턱 1/3 은 `REC-Y3` 에서 **차용**한 값이다(`PREREG_POST6.md` §1-6 6번 고지 승계) — "
        "절단 비율에 대해 검증된 값이 아니다.")
    say("- **`P6-창5절단가드-B`**(절단 2건 제외 민감도가 `LAD-T1` 판정을 뒤집으면 ⇒ ⛔ 「판정 불가(창5 절단 의존)」): §6 에서 판정.")
    say("- 🔴 **방향 자기신고(PD-1 4번 · 선택이 아니다)**: 창이 09-15 였다면 이번 절단은 **0건**이고 "
        f"`exact` 갈래 가드도 {100*ga_exact:.1f}% → 0% 로 꺼졌다. 동결 문언이 지시한 09-11 은 가드를 "
        "**켜는 쪽 = 우리에게 불리한 쪽**이지만 **고른 것이 아니라 정해져 있던 값**이다.")
    say("- 🔑 전례: `RESULTS_LADDER_TRANCHE.md` §7 — 1회차의 창5 는 «잘려» 있었고 그 「위반 4」는 "
        "실재하지 않는 값이었다. **그래서 이번에도 절단을 플래그로 드러내고 제외 민감도를 함께 낸다.**")

    # ── §1-1b. PD-12 4번 — post6 절단 2건의 값 «대체» ────────────────────
    say()
    say("### §1-1b. 🆕 post6 절단 2건의 값 **«대체»** (PD-12 4번 · 누적 쌍 재계산 규약)\n")
    say(f"주 창이 {END} 로 전진해 post6 의 절단 2건은 창5 가 **완전**해졌다 ⇒ 이번 회차에 값을 대체한다.\n")
    say("| 종목 | 등록일 | post6 절단 시점 창5 봉수 / **DD5** | post7 창5 봉수 / **DD5(대체)** | 차이 |")
    say("|---|---|---|---|---|")
    for nm, ref in POST6_TRUNC_ASOF.items():
        currow = next((r for r in rows if r["nm"] == nm and r["post"] == "post6"), None)
        if currow is None:
            say(f"| {nm} | {ref['d0']} | {ref['n5_asof']}봉 / **{ref['dd5_asof']:.2f}%** | "
                "🔴 **행을 못 찾았다 — 아래 값 무효** | — |")
            continue
        say(f"| {nm} | {ref['d0']} | {ref['n5_asof']}봉 / **{ref['dd5_asof']:.2f}%** | "
            f"{currow['n5']}봉 / **{currow['dd5']:.2f}%** "
            f"{'✅ 완전' if currow['n5'] >= TRUNC5_MIN_BARS else '🔴 여전히 절단'} | "
            f"{currow['dd5'] - ref['dd5_asof']:+.2f}%p |")
    say()
    say("- 🔴 **왼쪽 열은 인용이다 — 재계산하지 않았다.** 출처 = "
        "`RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md` §1-1·§8. "
        "***그 파일은 한 byte 도 고치지 않았다*** — 대체값은 **이 산출물 안에서만** 산다"
        "(`RESULTS_*_POST6_NUMBERS.md` md5 불변 의무).")
    say("- 이 대체는 **§2 이후의 모든 누적 표(`LAD-T1`·`T2`·`T3`)에 이미 반영돼 있다** — "
        "위 표는 그 사실을 «보이게» 하는 것이지 따로 계산한 값이 아니다.")

    # ── §1-2. 창 봉수 재확인 (PD-12) ─────────────────────────────────────
    say()
    say("### §1-2. PD-12 재확인(참고) — 주 표본 6건의 `[D-19, D]` 창 봉수\n")
    say("PD-12 가 「해치텍 10/20 · 나머지 20/20」이라 적었고 계산 단계에서 재확인하라 했다. "
        "이 축의 판정에는 쓰이지 않는다(`P6-절단가드-A` 는 선정·등록일 축의 가드다 — 이름 분리 PD-11 3번).\n")
    say("| 종목 | 등록일 | 창 시작(달력 D-19) | 그 종목 봉수 / 20 |")
    say("|---|---|---|---|")
    short20 = []
    for r in new7:
        cur.execute("SELECT min(date) FROM (SELECT DISTINCT date FROM daily_prices "
                    "WHERE date <= %s ORDER BY date DESC LIMIT 20) t", (r["d0"],))
        w_start = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s",
                    (r["code"], w_start, r["d0"]))
        nb = cur.fetchone()[0]
        if nb < 20:
            short20.append(r["nm"])
        say(f"| {r['nm']} | {r['d0']} | {w_start} | "
            f"{'🔴 **' + str(nb) + '**' if nb < 20 else nb} / 20 |")
    say()
    say(f"- 20봉 미만 = **{len(short20)}건**"
        + (f" ({', '.join(short20)})" if short20 else "")
        + f" ⇒ PD-12 의 「분자 1(해치텍)」과 "
        f"**{'일치 ✅' if short20 == ['해치텍'] else '🔴 불일치 — 그대로 적는다'}**")
    say(f"- **`P6-절단가드-A`**(선정·등록일 축) 산술 = {len(short20)}/{N_EXACT_POST7} = "
        f"{100*len(short20)/N_EXACT_POST7:.1f}% vs 1/3 ⇒ "
        f"**{'⛔ 발동' if guard_a_fires(len(short20), N_EXACT_POST7) else '미발동'}** "
        "(PD-12 상단 · 이 축의 판정에는 쓰지 않는다 — 이름만 같고 대상이 다르다)")
    say("- 🔴 **방향**(§1-6 2번 승계): *「창이 짧으면 「창 최고」가 되기 쉽다 ⇒ **M1 관측에 유리**」* — "
        "해치텍의 짧은 창은 `Q1-R2`·`P6-M1′` 에 **유리한** 방향이다. 그 축의 절단 제외 민감도는 "
        "`run_regday_post7.py` 레인이 낸다.")

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
        f"전체 {len(ns_all)*(len(ns_all)-1)//2} "
        "(🔴 post7 주 표본이 **1차에 몰려 있어** 동률 쌍이 구성으로 늘어난다 · §1 마지막 줄)")

    # ── §1-4. 창5 DD 퍼짐 ────────────────────────────────────────────────
    v5 = sorted(r["dd5"] for r in rows)
    q5 = statistics.quantiles(v5, n=4, method="inclusive")
    say()
    say("### §1-4. 창5 `DD` 퍼짐 (계열 승계 · 「잡음 띠」 점검)\n")
    say("- 정렬: " + " · ".join(f"{x:.2f}" for x in v5))
    # 🔴 「폭」은 **전정밀도 차이**를 반올림한 값이다 — 인쇄된 반올림값끼리 빼면 다를 수 있다.
    #    두 수를 «둘 다» 적어 다음 사람이 「값이 틀렸다」와 「표기가 다르다」를 가를 수 있게 한다.
    _span_full = v5[-1] - v5[0]
    _span_rounded = round(v5[-1], 2) - round(v5[0], 2)
    say(f"- 범위 **{v5[0]:.2f}~{v5[-1]:.2f}** · 폭 **{_span_full:.2f}%p** · "
        f"사분위 `Q1`={q5[0]:.2f} · `Q2`={q5[1]:.2f} · `Q3`={q5[2]:.2f} ⇒ **IQR {q5[2]-q5[0]:.2f}%p** "
        "(post5 누적 12건: 범위 9.79%p · IQR 3.25%p · "
        "post6 누적 22건: 범위 14.45%p · IQR 6.49%p — "
        "출처 `RESULTS_LADDER_TRANCHE_POST6_NUMBERS.md` §1-4)")
    say(f"  - 🔑 **산술 출처**: 폭 = `max − min` 을 **전정밀도**로 빼고 반올림한 값 "
        f"(`{v5[-1]!r} − {v5[0]!r}` = **{_span_full:.4f}** → `{_span_full:.2f}%p`). "
        f"⚠️ **인쇄된 반올림값끼리 빼면 `{v5[-1]:.2f} − {v5[0]:.2f}` = "
        f"{_span_rounded:.2f}%p** 로 다르다 — ***두 수는 「틀린 값」이 아니라 「다른 잣대」다.*** "
        "이 문서는 **전정밀도 쪽**을 쓴다(계열 전체 동일).")

    # ── §2. 주 판정 ──────────────────────────────────────────────────────
    say()
    say("## §2. `LAD-T1` 주 판정 + 창 민감도 — 창3 · **창5(주)** · 창A (§4-5 의무 1~3)\n")
    say(HDR)
    say(SEP)
    a3 = run_axis("창3 `[D,D+2]`", ns_all, [r["dd3"] for r in rows], DELTA)
    a5 = run_axis("**창5 `[D,D+4]` (주)**", ns_all, [r["dd5"] for r in rows], DELTA)
    aa = run_axis("창A `[D,발행일]`", ns_all, [r["dda"] for r in rows], DELTA)
    say()
    say(f"- **누적 비교가능 쌍(창5) = {a5['comp']}** · post6 누적 **{CUM_PAIRS_POST6}** ⇒ "
        f"**신규 쌍 = {a5['comp'] - CUM_PAIRS_POST6}** (누적 쌍 재계산 · `PREREG_POST6.md` §2-4)")
    say(f"- 계열 값 나란히: post5 `V` = {POST5_T1_V}/{CUM_PAIRS_POST5} · `p` = {POST5_T1_P:.4f} → "
        f"post6 `V` = {POST6_T1_V}/{CUM_PAIRS_POST6} · `p` = {POST6_T1_P:.4f} → "
        f"**이번 `V` = {a5['V']}/{a5['comp']} · `p` = {a5['p']:.4f}**")
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
    say(f"- 계열: 1회차(post4 6건) 13쌍 → post5(12건) {CUM_PAIRS_POST5}쌍 · `p` {POST5_T1_P:.4f} ⛔ → "
        f"post6(22건) {CUM_PAIRS_POST6}쌍 · `p` {POST6_T1_P:.4f} ⛔ → "
        f"이번({len(rows)}건) {a5['comp']}쌍 · `p` {a5['p']:.4f} {'⛔' if v1 == '불성립' else ''}")

    # ── §4. T2 ───────────────────────────────────────────────────────────
    say()
    say("## §4. `LAD-T2` (반증축 · 필수) — `DD/sigma20` 정규화\n")
    sub = [r for r in rows if r["sig"] is not None]
    drop = [r["nm"] for r in rows if r["sig"] is None]
    say(f"B-4: sigma20 없는 건은 T2 표본에서 통째로 제외. **표본 {len(sub)}건** "
        f"(제외 {len(drop)}건: {', '.join(drop) if drop else '없음'}). "
        "🔴 **해치텍은 2026-08-25 첫 봉**이라 등록일(09-07) 직전 21종가를 못 채울 수 있다 — "
        "제외 목록에 그 이름이 있으면 그것이 사유다(값을 보고 뺀 것이 아니라 «구성»이다).\n")
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
            "🔴 **부호뿐이다** — 차이 자체는 검정되지 않았다(post5 §4 단서 승계). "
            "🔴 그리고 `PREREG_BUYLADDER` 계열은 🔒 결정 ④로 **종결**이다(PD-13 1번) ⇒ **기록만**.")
    else:
        say(f"- ⇒ 정규화축 `p`({p_n:.4f}) **>=** 원축 `p`({p_o:.4f}) ⇒ **가설 B 는 지지 없음.**")
    say("- 계열 값 나란히: post5 원축 0.6767 · 정규화축 0.5562 · 부수 0.5545 (표본 11건)")

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
            "**`LAD-T1` 영구 취소**(보고서 §6 #7 승계 — 「지지를 취소한다(영구)」).")
    else:
        say(f"- ⇒ T3 `p` = {a_t3['p']:.4f} >= 0.05 ⇒ 시간 효과로 대체 설명되지 않는다"
            "(**`LAD-T1` 영구 취소** 사유 없음).")
    say(f"- **부호 감시**(`RESULTS_LADDER_TRANCHE.md` §10 승계 · post5 T3 `p` = 0.2008 < 원축 0.5160 · "
        f"post6 T3 `p` = 0.1909 < 원축 {POST6_T1_P:.4f}): "
        f"이번 T3 `p` = **{a_t3['p']:.4f}** vs 창5 원축 `p` = **{a5['p']:.4f}** ⇒ "
        f"T3 가 원축보다 **{'낮다 — 부호 유지' if a_t3['p'] < a5['p'] else '낮지 않다 — 부호 유지되지 않음'}**"
        f"(**3글 연속 관찰**). 부호가 유지되면 ***「차수는 낙폭이 아니라 보유 기간을 따라간다」*** 쪽이 "
        "유일한 살아있는 설명이 된다. `p < 0.05` 로 내려가면 **T1 은 영구 취소**(이번 판정은 위 줄).")

    # ── §6. 민감도 — 창5 절단 2건 제외 (PD-12 2번) ───────────────────────
    say()
    say("## §6. 민감도 (PD-12 2번) — **창5 절단 2건 제외** (`LAD-T1`·`T2`·`T3`·`LAD-P2` 전부)\n")
    sub_t = [r for r in rows if not r["trunc5"]]
    say(f"- 제외: {', '.join(r['nm'] for r in trunc) if trunc else '없음'} ⇒ 표본 **{len(sub_t)}건**")
    say("- 🔑 이 표는 `ANC-P3`(앵커 재설계 · `PREREG_ANCHOR_REDESIGN.md` §4-1)가 쓰는 창5 `L₅` 와 "
        "**같은 창·같은 제외 규칙**이다 — 그 레인은 `build_rows()` 를 import 해 쓴다(새 코드 0줄).\n")
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
    say("## §7. 민감도 (B-7 + PD-3) — **같은 종목 2번째 사이클 제외** (🔴 `approx` 민감도와 «따로»)\n")
    sub2 = [r for r in rows if not r["second"]]
    excl2 = [r for r in rows if r["second"]]
    say("- 제외 대상: " + " · ".join(f"{r['nm']}({r['post']} · {r['d0']})" for r in excl2)
        + f" ⇒ 표본 **{len(sub2)}건**")
    say(f"- **`P6-PRIOR_CYCLE_IN_WINDOW`**(PD-3 · `[D-19, D]` 창 안에 자기 직전 사이클 등록일) — "
        "이번 글 재진입 **3건**: "
        + " · ".join(f"{k} = **{v}**" for k, v in PRIOR_CYCLE_FLAG_POST7.items())
        + f" (합 **{sum(PRIOR_CYCLE_FLAG_POST7.values())}**)")
    say(f"- 🔴🔴 **주 표본(`exact` {N_EXACT_POST7}) 안의 재진입은 {', '.join(PRIOR_CYCLE_IN_MAIN)} "
        f"1건뿐이고 그 건의 플래그가 «0» 이다** ⇒ **판정 분모 안 플래그 = 0**"
        "(직전 등록일 08-05 < 창 시작 08-11 ⇒ **구성상 0** — 관측이 0 인 것과 다르다). "
        "글 전체 플래그 2건(지투파워·한국화장품제조)은 **둘 다 `approx` 갈래**다(INTAKE §5 머리말 · §2-10).")
    say("- 🔴 **지투파워는 이 계열 최초의 «3번째 사이클»**이다(post4 08-13 → post6 08-26 → post7 「9월 초」). "
        "§1-5 문언은 *「2번째 사이클」* 이라 쓰여 있으나 플래그 정의가 *「자기 **직전** 사이클의 등록일」* "
        "이라 3번째에도 **그대로 적용된다**(문언 확장 아님 · PD-3).")
    say("- 🔴 **두 민감도를 합치지 않는다**: 재진입 3건 중 **2건이 `approx`** 라 이 §7 의 제외와 "
        "§7-1 의 `approx` 갈래가 **겹친다**. 겹친다고 한 표로 합치면 어느 축이 판정을 움직였는지 "
        "구분할 수 없게 된다(PD-3 마지막 줄).\n")
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
        + ("**🔴 「재진입 의존」 — 어느 쪽도 지지로 선언하지 않는다(PD-3 2번)**"
           if v2x != v1 and v2x != "보류"
           else "**판정이 갈리지 않는다**" if v2x == v1
           else "**제외본은 게이트 미달이라 이 민감도만으로 판정하지 않는다**"))
    say(f"- T3 제외본 `p` = {s_t3['p']:.4f} (주 판정 {a_t3['p']:.4f}) · 창3 {s3['p']:.4f} · 창A {sa['p']:.4f}")

    # ── §7-1. approx 갈래 민감도 (PD-4 2번 · 창 규약 첫 발동) ────────────
    say()
    say("## §7-1. 민감도 — `approx` 2건의 **갈래별** 값 (PD-4 2번 · `PREREG_POST6.md` §1-4 창 규약 «첫 발동»)\n")
    say("저자가 「9월 초」·「8월 말」이라 적은 두 건은 **등록일이 한 값이 아니다** ⇒ 창 규약대로 "
        "**그 구간의 «모든 거래일»을 갈래로 만들어** 값을 전부 인쇄한다. **주 판정에는 넣지 않는다.**\n")
    approx_trunc_names = []
    for nm, code, N, label, lo, hi, n_expect in APPROX_BRANCHES:
        cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN %s AND %s ORDER BY date",
                    (lo, hi))
        days = [str(r[0]) for r in cur.fetchall()]
        say(f"### {nm} ({code}) · N = {N} · 저자 표기 {label} = `{lo}` ~ `{hi}`\n")
        say(f"- 거래일 갈래 **{len(days)}개** — PD-4 2번 실측 **{n_expect}개**와 "
            f"**{'일치 ✅' if len(days) == n_expect else '🔴 불일치 — 그대로 적는다'}**: {', '.join(days)}\n")
        say("| 갈래 `D` | H | 창5 봉수 | min_low(창5) | **DD5** | 창A 끝 | **DD_A** | `P6-WIN5_TRUNC` |")
        say("|---|---|---|---|---|---|---|---|")
        n_tr = 0
        for d0 in days:
            cur.execute("SELECT date, high, low FROM daily_prices WHERE stock_code=%s "
                        "AND date >= %s AND date <= %s ORDER BY date", (code, d0, END))
            bars = cur.fetchall()
            if not bars:
                say(f"| {d0} | 🔴 봉 없음 | — | — | — | — | — | — |")
                continue
            H = bars[0][1]
            w5 = bars[:5]
            dd5 = 100 * (1 - min(b[2] for b in w5) / H)
            dda = 100 * (1 - min(b[2] for b in bars) / H)
            tr = 1 if len(w5) < TRUNC5_MIN_BARS else 0
            n_tr += tr
            say(f"| {d0} | {H:,.0f} | {len(w5)} | {min(b[2] for b in w5):,.0f} | **{dd5:.2f}%** | "
                f"{END} | **{dda:.2f}%** | {'**1**' if tr else '0'} |")
        if n_tr:
            approx_trunc_names.append(nm)
        say()
        say(f"- 창5 절단 갈래 = **{n_tr}/{len(days)}** — PD-12 5번 실측"
            f"({'지투파워 3갈래' if nm == '지투파워' else '한국화장품제조 0갈래(7갈래 전부 완전)'})와 "
            f"**{'일치 ✅' if (n_tr == 3 and nm == '지투파워') or (n_tr == 0 and nm != '지투파워') else '🔴 불일치 — 그대로 적는다'}**")
        say()
    say(f"- 🔴 `approx` 갈래를 가드-A 분자에 넣어도 **3/{N_NEW_POST7} < 1/3 ⇒ 미발동 불변**(§1-1).")
    say("- 🔴 **이 표는 판정이 아니다.** `RNK-D5`·`PREREG_S5_FUND_NEWS_OOS.md` §1-1·"
        "`PREREG_ANCHOR_REDESIGN.md` §2-3 세 동결본이 *「판정 분모 = `exact` 만 · `approx` 는 의무 민감도」* "
        "를 지시한다 ⇒ **값을 인쇄하되 판정 언어를 쓰지 않는다**.")
    say("- 🔴 **§7 과 겹친다**: 두 건 다 재진입이다. 위에서 적은 대로 **합치지 않는다**.")

    # ── §8. LAD-P1 ~ P3 ──────────────────────────────────────────────────
    say()
    say("## §8. 개별 예측 `LAD-P1`~`P3` (§5-3 · **값 기록 · 기각 사유 아님**)\n")
    say("- **`LAD-P1`** 「저자가 체결 차수를 명시」 — 7번째 글 **항목 13건 중 차수 명시 13건**"
        "(`INTAKE` §2-12). 그중 「기존 건 후속」 3건은 PD-2 로 신규 분모 밖. "
        f"⇒ **분모 정의 = 「DB 있는 신규 건」 = {N_NEW_POST7}건 ⇒ {N_NEW_POST7}/{N_NEW_POST7} = 100%** "
        "(코드 **13/13** DB 존재 — 해치텍 `0155E0` 포함 · PD-11) ⇒ ✅ **성립 · 4글 연속**"
        "(post4 6/6 → post5 6/6 → post6 10/10 → post7 10/10).")
    dd5_new = [r["dd5"] for r in new7]
    med_new = median(dd5_new)
    in_band = LAD_P2_LO <= med_new <= LAD_P2_HI
    say(f"- **`LAD-P2`** 「신규 건 `DD`(창5) 중앙값이 {LAD_P2_LO:.0f}~{LAD_P2_HI:.0f}%」 — "
        f"🔴 **주 분모 = 신규 ∧ `exact` {len(new7)}건**"
        "(신규 10 갈래는 `none` 2 의 `D` 가 없어 «계산 자체가 안 선다» · `approx` 2 는 §7-1 갈래 표) — 값 = "
        + " · ".join(f"{r['nm']} {r['dd5']:.2f}%" for r in new7)
        + f" ⇒ 중앙값 **{med_new:.2f}%** ⇒ **{'✅ 구간 안' if in_band else '❌ 구간 밖'}** "
          f"(1회차 23.53% · post5 20.34% · post6 {POST6_P2_MEDIAN:.2f}%)")
    dd5_nt = [r["dd5"] for r in new7 if not r["trunc5"]]
    med_nt = median(dd5_nt) if dd5_nt else None
    if med_nt is None:
        say("  - 절단 2건 제외(PD-12 2번): 🔴 **남는 건이 0 이라 중앙값이 없다** — 그대로 적는다.")
    else:
        in_band_nt = LAD_P2_LO <= med_nt <= LAD_P2_HI
        say(f"  - 절단 2건 제외(PD-12 2번): {len(dd5_nt)}건 중앙값 **{med_nt:.2f}%** ⇒ "
            f"**{'✅ 구간 안' if in_band_nt else '❌ 구간 밖'}** ⇒ "
            f"**{'갈리지 않는다' if in_band == in_band_nt else '🔴 갈린다 — 「절단 의존」'}** "
            f"(post6 제외본 {POST6_P2_MEDIAN_EXTRUNC:.2f}%)")
    say(f"  - 🆕 **하한 이탈 관찰(보고서 §6 #7 · 이번 글 의무)**: post6 중앙값 **{POST6_P2_MEDIAN:.2f}%** 는 "
        f"하한 {LAD_P2_LO:.0f}% 까지 **{POST6_P2_MEDIAN - LAD_P2_LO:.2f}%p** 였다 ⇒ "
        f"이번 값 **{med_new:.2f}%** 는 하한까지 **{med_new - LAD_P2_LO:+.2f}%p** ⇒ "
        f"**{'🔴🔴 하한 이탈' if med_new < LAD_P2_LO else '하한 이탈 없음'}** "
        f"(상한 {LAD_P2_HI:.0f}% 까지 {LAD_P2_HI - med_new:+.2f}%p). "
        "🔑 ***`LAD-P2` 는 「구간 안이냐」만 묻는 예측이라, 하한에 붙어 있다는 사실은 «예측의 강도»가 "
        "아니라 «다음 회차의 취약성»으로만 기록한다.***")
    say(f"- **`LAD-P3`** 「`first_only`(1차만 체결) 건 >= 1」 — 7번째 글 신규 **{len(FIRST_ONLY_POST7_NEW)}건**"
        f"({' · '.join(FIRST_ONLY_POST7_NEW)} · 전부 차수 N = 1 · 그중 `exact` "
        f"**{len(FIRST_ONLY_POST7_EXACT)}건**) + 후속 아난티 1 ⇒ ✅ **성립** "
        "(post4 0건 → post5 1건 → post6 3건 → **post7 6건 = post6 의 두 배**). "
        "🔴 `REC-Z4`(「`first_only` ∧ 서로 다른 값 레그 3개」) 충족 3건의 **귀결(즉시 `L` 판정)은 "
        "🔒 결정 ④로 소멸**했다(PD-13 1번) ⇒ 이 축은 **「건 수」만 기록**한다.")

    # ── §9. 모호 지점·한계 ───────────────────────────────────────────────
    say()
    say("## §9. 모호 지점 (양쪽 인쇄 · 「모호」 표기) · 한계\n")
    say(f"1. **창5 절단 2건**(빛과전자 4봉 · 범한퓨얼셀 3봉) — 「절단 시점 값」이다. 분모 포함(주)/제외(민감도) "
        f"**양쪽 인쇄**했다(§1-1·§6). 가드-A 는 주 분모 {len(trunc)}/{N_NEW_POST7} 미발동이지만 "
        f"**`exact` 갈래 {len(trunc)}/{N_EXACT_POST7} 는 문턱에 닿는다** — 숨기지 않았다.")
    say("2. **post6 절단 2건의 값 대체**(§1-1b) — 「절단 시점 값 → 대체 값」을 둘 다 적었다. "
        "🔴 옛 산출물은 **한 byte 도 고치지 않았다**(md5 불변 의무).")
    say("3. **재진입 3건** — 분모 포함(주)/제외(민감도) 양쪽 인쇄(§7). 🔴 주 표본 안 플래그는 **0**이고, "
        "플래그 1 인 두 건은 **`approx` 갈래**다(§7-1). 두 민감도를 **합치지 않았다**.")
    say("4. 🔴 **「신규 10」과 「주 표본 6」이 갈린 첫 회차**다(§1-0). 표본 수와 가드 분모가 다른 수가 되었고, "
        "**둘 다 인쇄**했다. ***어느 한쪽으로 통일하면 그것이 새 자유도다.***")
    say("5. **`MANUAL` 2건은 라벨 때문에 빠진 것이 아니다**(B-2 carve-out) — 후속이라 빠졌다(§1-0). "
        "규칙을 넓히지도 좁히지도 않았다.")
    say("6. **해치텍은 2026-08-25 첫 봉**(신규 상장)이라 `[D-19,D]` 가 10/20 이고 04-01~08-04 구간은 **0봉**이다. "
        "이 축은 창5·창A 만 쓰므로 막히지 않지만, sigma20 의 21종가 창은 못 채울 수 있다(§4 제외 목록 참조).")
    say("7. **`H` = 등록일 고가는 가정**이고 사전등록은 앵커 민감도를 넣지 않았다 — "
        "🔴 그 앵커가 post6 에서 **무너졌고**(`REC-Z3`), 이번 회차에 `PREREG_ANCHOR_REDESIGN.md` 의 "
        "`ANC-P1`~`P3` 이 처음 열린다 ⇒ **`run_anchor_redesign.py --mode post7` 산출물과 «함께» 읽어야 한다**"
        "(`PREREG_POST6.md` §4 #44).")
    say("8. `V` 는 개수이고 귀무에서 비교가능 쌍 수가 함께 흔들린다(관측 vs 귀무 평균을 같은 표에 인쇄했다). "
        "사전등록이 정규화하지 않기로 동결했으므로 그대로 뒀다.")
    say("9. **글 간 풀링이 국면을 섞는다**(post4~post7 = 4주). 표본은 저자가 올리기로 «고른» 매매다"
        "(`PREREG_SELECTION.md` §0 결과 조건화 위협).")
    say("10. `N` 은 저자 서술 의존(「N차 매수된 상태」를 「N차까지 체결」로 읽었고 **총 분할 수는 모른다**).")
    say("11. **프로그램 버전이 이 계열 최초로 «없다»**(PD-8) ⇒ 버전 공변량을 쓰는 분석에서 post7 행은 분모 밖.")
    say("12. **새 예측을 만들지 않았다** — δ·창5·게이트 40·시드·순열 표본 수 전부 동결값 그대로다.")

    (BASE / "RESULTS_LADDER_TRANCHE_POST7_NUMBERS.md").write_text("\n".join(OUT) + "\n",
                                                                  encoding="utf-8")
    cur.close()
    conn.close()
    print("\n[written] RESULTS_LADDER_TRANCHE_POST7_NUMBERS.md")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())

# -*- coding: utf-8 -*-
"""앵커(`H`) 재설계 — `ANC-` 축 **첫 실행** (`ANC-P1`·`P2`·`P3` · `ANC-N1`~`N5`).

사전등록: `PREREG_ANCHOR_REDESIGN.md`(2026-09-10 동결 `63e10a7` → 머지 `ef17c4f` · post7 fetch 보다 «앞»)
  §2-1 데이터·열 · §2-2 현행 앵커 `A0` · §2-3 판정 분모
  §3 후보 `A1`(전방 전창 최고) · `A2`(창5 최고) · `A3`(후방 20봉 최고) · `A0` 는 대조군 전용
  §4 예측 동결 표(`ANC-P1`·`P2`·`P3`) · §4-1 `DD` 정의 · §4-2 방향 자기신고
  §5-1 채택 최소 조건(전부 AND) · §5-2 세 갈래 · §5-3 항등 조항 · §5-4 소급분의 지위
  §6 대칭 단언 `ANC-N1`~`N5` · §7-1 시드 산술 · §7-2 순열 귀무(크기 정합 + 층화) · §7-3 무작위 앵커 `R`
  §8 표본 · §9-3 DB 스냅샷 · §10 판정 불가 조건 · §13 한계
인테이크: `PREDECISION_2026-09-15_post7.md`(PD-1 · PD-3 · PD-4 · PD-12 · PD-13 · PD-14) ·
  `INTAKE_2026-09-15_post7.md` §1·§2·§5 · `LABELS_2026-09-15_post7.md`

🔴🔴 **새 코드 0줄 원칙** — 후보 앵커 넷은 전부 «이미 동결된 코드가 계산하는 값»이다(§3).
   이 스크립트는 그 함수를 **import 해 그대로 쓴다**. 부득이 SQL 을 옮겨 적은 자리에는
   **출처 줄**을 달았고, 옮겨 적은 값이 동결 SQL 의 값과 «같다»는 것을 §2 의 **항등 대조 열**로
   매 실행 인쇄한다(옮겨 적으면서 조용히 달라지는 것을 막는 유일한 장치다).

  | 후보 | 값 | 출처(동결 코드) |
  |---|---|---|
  | `A0` | 등록일 고가 `H₀` | `run_reconstruct_post6.py` 의 `v["h0"]`(`SELECT high … date = D`) |
  | `A1` | `max(high) over [D, END]` | `run_reconstruct_post6.py:443-444` 의 `HI` **그 자체** |
  | `A2` | 창5 `[D, D+4거래일]` 의 `max(high)` | `run_reconstruct_post6.py:143-151` `win_bars(cur, code, D, back=0, fwd=4)` |
  | `A3` | `max(high) over [D−19, D]` | `run_reconstruct_post6.py:153-160` `dd_h(…, k=20)` 가 쓰는 `H` 그대로 |
  | `V`·`δ`·순열 | `LAD-T1` 통계 핵 | `run_ladder_tranche.py:79-119` `pairset`·`statV`·`permute_null` |
  | 소급 표본 | `exact` 28건 + 코드 | `run_ranking.py` `load_ledger`·`build_codes`·`exact_items` |

🔴 **`δ` 도 `V` 도 이 문서에서 고치지 않는다**(§4-1) — **앵커만 바꾼다.** 그래야
   「앵커가 원인이었나」를 잰다.

🔴 **계산 «전»에 고정된 해석 결정** (전부 동결 문언 인용 · 신설 0):

  ANC-A-1 창 종료 `END` = **2026-09-11**. 발행 2026-09-12 는 **토요일 = 휴장**이므로
      `RESULTS_LADDER_TRANCHE.md` §1 **B-1**(*「발행일이 토·일이면 창은 직전 거래일에서 끝난다」*)로
      마지막 거래일에서 끝난다. `PREREG_WEIGHTED_RECON.md` §5-2 :678-680 · `PREREG_ANCHOR_REDESIGN.md`
      §2-1 도 **같은 한 값**을 지시한다(PD-1 · 「창 종료일 충돌」은 없다).
  ANC-A-2 **판정 분모 = post7 «신규» ∧ `reg_date_precision = 'exact'` = 6건**(§2-3 · PD-4 1번).
      🔴 **충돌 신고(§1-8 형식)**: §2-3 은 이 분모를 *「post6 에서 `REC-` 축이 쓴 분모(10건)와 «같은 규칙»」*
      이라 적었는데 **post6 신규 10건은 전부 `exact`** 였다 ⇒ 그때는 두 정의가 같은 수였다.
      **post7 에서 신규 10 ≠ `exact` 6 으로 처음 갈린다.** ⇒ **명시된 쪽(`exact` 6)을 쓰고**
      신규 10 갈래는 **민감도로 병기**한다. 두 수를 한 수로 합치지 않는다.
  ANC-A-3 **소급 post1~6 = `exact` 28건 = 탐색**(§8 · §5-4). 산출물의 **매 표에**
      *「소급 = 탐색 · 채택은 post7 열로만」*을 적는다. `approx` 2 · `after` 1 은 판정 분모 제외 ·
      참고 갈래로만 병기(§8).
  ANC-A-4 🔴 **`WRC-` 판정 분모를 쓰지 않는다**(§2-3) — 두 분모의 수를 한 수로 합치지 않는다.
  ANC-A-5 **최소 n = 3**. `ANC-P1`·`ANC-P2` 는 post7 신규 `exact` 건이 3 미만이면 ⛔(§10).
      실측 6 ≥ 3 ⇒ **열린다**(PD-14 1번).
  ANC-A-6 🔴🔴 **`ANC-N4` ① 축이 이번 회차에 «항등»이다** — 발행일(09-12)이 휴장이라
      「발행 당일 봉 «포함»」과 「발행일 «직전» 봉」이 **같은 봉(09-11)** 을 가리킨다.
      ⇒ ① 은 §5-3 문형대로 **「구분 불가(항등)」로 명시 인쇄**하고 **②·③ 두 축으로만** 판정한다.
      🔴 **①을 다른 정의로 «대체하지 않는다»** — 대체하면 그게 새 자유도다(PD-14 1번).
  ANC-A-7 **`BUY-L5` 재개 조항은 🔒 사장님 결정 ④(`PREREG_BUYLADDER` 계열 종결·기록 보존 ·
      동결 `342f6f0`)로 «자동 소멸»**한다. §5-2 가 그 문형을 **미리** 적어 두었다(PD-13 1번).
      ⇒ 재개 문구를 인쇄하지 않고 **「결정 ④로 소멸」**이라 적는다.
  ANC-A-8 **`A0` 는 대조군 전용**(채택 후보가 아니다) · **혼합 금지**(「`h` 는 `A1`, `DD` 는 `A3`」 같은
      조합을 쓰지 않는다 · §3 상호 배타성).
  ANC-A-9 **`ANC-P3` 층화 = 재배정을 «글(post) 안에서» 한다**(§7-2 · 이 문서의 유일한 추가 자유도 1개).
      **층화 없는 갈래도 의무 민감도로 병기** · 두 갈래가 갈리면 `ANC-N4` 발동(선언 금지).
      🔴 **post7 «단독» 표본은 글이 하나라 층화 갈래와 비층화 갈래가 «구성상 항등»**이다
      (`RESULTS_RANKING_POST6_NUMBERS.md` 의 *「글이 하나다 ⇒ 구성상 항등 = 판별력 0」* 관용 승계).
  ANC-A-10 **`ANC-P3` 비교가능 쌍 게이트 40**(§10 · `PREREG_LADDER_TRANCHE.md` §5 승계).
      🔴 **문턱을 낮춰 열지 않는다**(§10 마지막 줄 · 게이트 보고 파라미터 하향 금지 조항).
      미달이면 **⛔ 「미룬다」**로 적고, 그 결과 §5-1 의 AND 가 완성되지 않으면
      **§5-2 의 세 갈래 중 어디로도 «선언하지 않는다»**(충돌 신고 · §7 참조).
  ANC-A-11 `adj_factor` 산술 **0건** · DB 는 **SELECT 만** · 라이브 트리 import **0건**.

🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2). 🔴 이 스크립트는 **새 예측을 만들지 않는다**.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import psycopg2

# 🔴 새 코드 0줄 — 동결 코드에서 그대로 가져온다(수정 금지 파일).
from run_reconstruct_post6 import dd_h, win_bars                      # noqa: F401  (dd_h = §3 `A3` 출처)
from run_ladder_tranche import (
    DELTA,            # 1.0 %p (동결 · §4-1 「고치지 않는다」)
    NPERM,            # 200,000
    NULL_SEED,        # 20260815 — §7-2 「새 시드를 만들지 않았다」
    PAIR_THRESHOLD,   # 40 (§10 게이트)
    pairset,
    permute_null,
    statV,
)
from run_ranking import build_codes, exact_items, load_ledger
from run_tests import DSN

BASE = Path(__file__).resolve().parent

# ── 동결 상수 ────────────────────────────────────────────────────────────────
END = "2026-09-11"          # ANC-A-1 · PD-1 (발행 09-12 토 = 휴장 ⇒ B-1 마지막 거래일)
PUB7 = "2026-09-12"         # 7번째 글 발행일 (토요일 · 휴장)
POST7_LOG_NO = "224409404744"
RETRO_LAST_POST_DATE = "2026-09-04"     # 소급 = post1~6 (§8)
# 🔴 소급 건의 창 종료는 **글마다 다르다** — 동결 §4 표(`PREREG_ANCHOR_REDESIGN.md:122`)가
#    `END` = 「그 글의 **발행 당일 봉 «포함»**」이라 못박고, §13(`:467`)도 *「`END` 가 글 발행일이라
#    후보마다 창 길이가 다르다」*고 적었다. 발행일이 휴장(토)이면 그 글의 마지막 봉 = 직전 거래일이다
#    (post4 `2026-08-22`토 → `08-21` · post5 `2026-08-29`토 → `08-28` · post6 `09-04`금 → `09-04`).
#    🔴🔴 소급 건에 post7 의 `END`(2026-09-11)를 쓰면 저자가 글을 쓸 때 «볼 수 없던» 봉이
#    창에 들어간다 — 그건 소급 «탐색»조차 아니고 **다른 축의 측정**이다.
_END_CACHE: dict = {}

S_ANCHOR = 100              # §7-3 무작위 앵커 대조군 시드 수 (시드 = NULL_SEED + j, j = 0…99)
M_TESTS = 3                 # §7-1 주 검정 수 (ANC-P1 · P2 · P3)
ALPHA = 0.05
HOLM1 = ALPHA / M_TESTS     # .0167
PERM_MIN_P = 1.0 / (S_ANCHOR + 1)       # .0099
S_MIN_REQUIRED = 20 * M_TESTS - 1       # 59 (REGISTRY.md 규칙 S >= 20m-1)
MIN_N = 3                   # §10 · ANC-A-5
PAIR_GATE = PAIR_THRESHOLD  # 40 (동결값 재사용 — 새 문턱 아님)

CANDIDATES = ("A0", "A1", "A2", "A3")
ADOPTABLE = ("A1", "A2", "A3")          # §3 「`A0` 는 대조군으로만 남는다」
IDENTITY_SLOTS = {("A1", "ANC-P1"), ("A1", "ANC-P2")}   # §5-3 항등 조항

# §4 예측 동결 표 — (후보, 소급 예측(탐색), post7 예측(검정))
PRED_P1 = {"A0": ("≥ 1/2 (= 6/10 재현)", "≥ 1/2"), "A1": ("항등 0/n", "항등 0/n"),
           "A2": ("< 1/2", "< 1/2"), "A3": ("≥ 1/2 (고쳐지지 «않는다»)", "≥ 1/2")}
PRED_P2 = {"A0": ("< 2/3", "< 2/3"), "A1": ("항등 1 (max close ≤ max high)", "항등 1"),
           "A2": ("≥ 2/3", "≥ 2/3"), "A3": ("< 2/3", "< 2/3")}
PRED_P3 = "어느 후보에서도 `p ≥ 0.05` (= post6 의 0.4914 는 앵커 탓이 아니다)"

RETRO_FOOTNOTE = ("🔴 **소급 = 탐색 · 채택은 post7 열로만**"
                  "(`PREREG_ANCHOR_REDESIGN.md` §5-4 · 같은 표본에 정의를 바꿔 다시 돌리는 것은 "
                  "정의상 사후적합).")

# ── post7 판정 분모 — `INTAKE_2026-09-15_post7.md` §1 표(동결) 그대로 옮겨 적음 ───────────
#    (종목, 코드, 등록일, 체결차수 N, first_only, 재진입, PRIOR_CYCLE_IN_WINDOW)
#    🔴 `exact` 6건 = ANC-A-2 의 판정 분모. 값을 보고 고르지 않았다 — 정밀도로 정해졌다.
POST7_EXACT = [
    ("서산",         "079650", "2026-09-03", 1, True,  False, 0),
    ("강동씨엔앨",   "198440", "2026-09-03", 1, True,  False, 0),
    ("로보티즈",     "108490", "2026-09-04", 1, True,  False, 0),
    ("해치텍",       "0155E0", "2026-09-07", 4, False, False, 0),
    ("빛과전자",     "069540", "2026-09-08", 1, True,  True,  0),   # PD-3 · 직전 등록일 08-05 < 창 시작 08-11
    ("범한퓨얼셀",   "382900", "2026-09-09", 1, True,  False, 0),
]
# 민감도 갈래 — 「신규 10」(ANC-A-2 충돌 신고). `approx` 2 + `none` 2 를 더한 것.
#    🔴 `none` 2건(한전기술·한전산업)은 **등록일이 없어** 앵커를 못 잰다 ⇒ 「측정 불가」로 센다.
POST7_APPROX = [
    ("지투파워",         "388050", "approx", "「9월 초」 = 09-01~09-10 거래일 8일", 3, True),
    ("한국화장품제조",   "003350", "approx", "「8월 말」 = 08-21~08-31 거래일 7일", 1, True),
]
POST7_NONE = [
    ("한전기술", "052690", "none", 4),
    ("한전산업", "130660", "none", 5),
]
POST7_FOLLOWUP = ["한라캐스트", "아난티", "우리기술투자"]    # PD-2 · 등록일 축 분모 «밖»

# PD-12 창5 `[D, D+4]` 절단 — 주 창 09-11 기준 실측(동결 표)
WIN5_TRUNC = {"빛과전자": 4, "범한퓨얼셀": 3}       # 봉수 (< 5 = 절단)

# §13 미리 적어두는 한계 (동결 문언 · 매 실행 인쇄)
LIMITS = [
    "🔴 **소급(post1~6)은 탐색이다.** 같은 표본에 새 앵커를 적용해 나온 수는 **증거가 아니다** — "
    "진짜 검정은 post7 열 하나뿐이다(§13).",
    "🔴 **`ANC-P3` 의 검정력이 낮을 수 있다.** post6 에서 쌍을 41 → 161(3.93배)로 늘렸는데 `p` 는 "
    "0.5160 → 0.4914 로 제자리였다 ⇒ ***쌍을 늘려도 안 움직이는 축이라, 앵커를 바꿔도 안 움직일 수 "
    "있다.*** 그때 답은 `ANC-N1` 발동(판별력 없음)이다(§13).",
    "🔴 **`h_obs` 는 `close` 로 재는 하한 검사다.** 저자의 매도는 장중가에 체결되므로 `h_obs ≤ 1` "
    "이라고 해서 실제 매도가가 앵커 아래였다는 뜻은 아니다. 복원 `P` 로 재는 진짜 `h_max` 는 "
    "`REC-Y3` 중단 때문에 못 쓴다 — **이 대체가 이 축의 가장 큰 약점**이다(§13).",
    "🔴 **`A2` 의 창5 는 `LAD-` 축에서 «위반 4쪽»이라는 걸 알고 고른 창이다**"
    "(`PREREG_LADDER_TRANCHE.md` §4-2 자기신고 승계). 앵커로 옮겨 써도 그 편향은 사라지지 않는다(§13).",
    "🔴 **`END` 가 «글마다» 그 글의 발행일이다**(§4 표 · §13) — 소급 post1~6 도 "
    "post7 의 `END` 가 아니라 **그 글의 발행 당일 봉 «포함»**(휴장이면 직전 거래일)으로 잰다: "
    "post1 `2026-07-31` · post2 `08-07` · post3 `08-14` · post4 `08-22`(토) → **`08-21`** · "
    "post5 `08-29`(토) → **`08-28`** · post6 `09-04` · post7 `09-12`(토) → **`09-11`**. "
    "⇒ **후보마다 창 길이가 다르다** — 등록이 발행 직전이면 창이 3~4봉뿐이고, 그때 "
    "**`A1` 과 `A2` 는 같은 값이 된다**(`A1` 의 창은 절단 개념 자체가 없다). "
    "***`ANC-N1` 이 그걸 잡는다***(§13).",
    "🔴 **소급 열의 창은 글마다 «짧다»** — post1 건의 창은 7월 말에서 끝난다. "
    "그래서 소급 값은 post7 값과 **같은 잣대로 잰 값이 아니고**, 나란히 놓아도 "
    "***「시간이 지나서 올랐나」를 «가르지 못한다»***. 소급이 탐색인 이유가 하나 더 있는 셈이다(§5-4).",
]

OUT: list[str] = []          # `_NUMBERS.md` 버퍼 (기계 생성)
DOC: list[str] = []          # `RESULTS_ANCHOR_POST7.md` 버퍼 (산문 + 표)


def say(s=""):
    print(s)
    OUT.append(s)


def doc(s=""):
    DOC.append(s)


def both(s=""):
    say(s)
    doc(s)


def note(s=""):
    """stdout 전용 — 산출물 본문에 넣지 않는다(바이트 결정론 보호)."""
    print(s)


def fmt(v, nd=1):
    return "—" if v is None else f"{v:.{nd}f}"


def frac(hit, n):
    return "—" if not n else f"{hit}/{n} = {100.0 * hit / n:.1f}%"


def med(xs):
    """C-20 — 짝수 n 에서 두 가운데 값의 평균(`statistics.median`)."""
    return statistics.median(xs) if xs else None


# ═══════════════════════════════════════════════════════════════════════════
# 1. 앵커 계산 — 전부 동결 코드의 값 (§3)
# ═══════════════════════════════════════════════════════════════════════════
def frozen_lo_hi(cur, code, d0, d1):
    """`(min(low), max(high))` over `[d0, d1]`.

    출처: `run_reconstruct_post6.py:443-444` — *「`SELECT min(low), max(high) FROM daily_prices
    WHERE stock_code=%s AND date BETWEEN %s AND %s`」* **그 SQL 그대로**. `max(high)` 가 곧 `HI`
    이고 §3 의 `A1` 은 *「이 값 그 자체」*다(새 코드 0줄).
    """
    cur.execute("SELECT min(low), max(high) FROM daily_prices WHERE stock_code=%s "
                "AND date BETWEEN %s AND %s", (code, d0, d1))
    return cur.fetchone()


def frozen_h_back(cur, code, d0, k=20):
    """`max(high) over [D−(k−1), D]` = §3 `A3`.

    출처: `run_reconstruct_post6.py:153-160` (`dd_h`) 의 **앞 절반 SQL 그대로**. `dd_h` 는
    `100*(1 − L/H)` 를 돌려주므로 `H` «만» 필요한 이 자리에서는 같은 SQL 을 그대로 옮겨 적었다
    (새 질의를 만들지 않았다 — `PREREG_Q1_V2.md` §2 `H6` 와 같은 값이다).
    """
    cur.execute("SELECT max(high) FROM (SELECT high FROM daily_prices WHERE stock_code=%s "
                "AND date <= %s ORDER BY date DESC LIMIT %s) t", (code, d0, k))
    return cur.fetchone()[0]


def frozen_h0(cur, code, d0):
    """등록일 고가 `H₀` = §2-2 현행 앵커 `A0`.

    출처: `run_reconstruct_post6.py` 의 `v["h0"]` — *「`SELECT high FROM daily_prices
    WHERE stock_code = %s AND date = %s`  -- date = D」*(`PREREG_ANCHOR_REDESIGN.md` §2-2 축자).
    """
    cur.execute("SELECT high FROM daily_prices WHERE stock_code=%s AND date=%s", (code, d0))
    r = cur.fetchone()
    return None if r is None else r[0]


def window_bars(cur, code, d0, d1):
    """창 `[d0, d1]` 의 봉 `(date, low, high, close)`.

    출처: `frozen_lo_hi` 와 **같은 표·같은 창**이다. `close` 열을 더 읽는 이유는 §4 의 `h_obs`
    정의(*「`max(close over [D,END])`」*)가 그 열을 요구하기 때문이고, 그 밖의 값은
    `frozen_lo_hi` 와 **항등**이어야 한다 ⇒ §2 표의 **항등 대조 열**이 매 실행 그것을 확인한다.
    🔑 옮겨 적은 값이 동결 값과 같은지를 «인쇄»하지 않으면, 옮겨 적기는 조용히 틀린다.
    """
    cur.execute("SELECT date, low, high, close FROM daily_prices WHERE stock_code=%s "
                "AND date BETWEEN %s AND %s ORDER BY date", (code, d0, d1))
    return cur.fetchall()


def trading_days_between(cal, d0, d1):
    """거래일 달력 `cal`(정렬된 date 리스트)에서 `d0` → `d1` 거래일 수(부호 있음)."""
    try:
        return cal.index(d1) - cal.index(d0)
    except ValueError:
        return None


def anchors_for(cur, code, d0, end):
    """한 건의 앵커 넷 + 파생값. 반환 dict.

    `H0`=A0 · `H1`=A1(=`HI`) · `H2`=A2(창5 최고) · `H3`=A3(후방 20봉 최고)
    `L`=창 최저 · `L5`=창5 최저 · `maxclose`=창 안 종가 최댓값 · `dstar`={후보: 그 고가를 낸 봉 날짜}
    """
    bars = window_bars(cur, code, d0, end)
    fz_lo, fz_hi = frozen_lo_hi(cur, code, d0, end)

    v = dict(code=code, d0=d0, bars=len(bars), frozen_L=fz_lo, frozen_HI=fz_hi)
    if not bars:
        v.update(H0=None, H1=None, H2=None, H3=None, L=None, L5=None,
                 maxclose=None, dstar={}, win5_bars=0, identity_ok=None)
        return v

    v["L"] = min(b[1] for b in bars)
    v["H1"] = max(b[2] for b in bars)
    v["maxclose"] = max(b[3] for b in bars)
    # 🔴 항등 대조 — 옮겨 적은 창이 동결 SQL 과 «같은 값»인가.
    v["identity_ok"] = (fz_lo is not None and fz_hi is not None
                        and float(fz_lo) == float(v["L"]) and float(fz_hi) == float(v["H1"]))

    v["H0"] = frozen_h0(cur, code, d0)

    # `A2` — 창5 `[D, D+4거래일]` (등록일 포함). 동결 `win_bars` 가 주는 봉 그대로.
    w5 = win_bars(cur, code, d0, back=0, fwd=4)
    v["win5_bars"] = len(w5)
    v["H2"] = max(b[2] for b in w5) if w5 else None
    v["L5"] = min(b[1] for b in w5) if w5 else None

    v["H3"] = frozen_h_back(cur, code, d0, 20)

    # `ANC-N3` — `H_X` 를 «낸» 봉의 날짜.
    dstar = {"A0": d0}
    dstar["A1"] = max(bars, key=lambda b: (b[2], b[0]))[0]
    dstar["A2"] = max(w5, key=lambda b: (b[2], b[0]))[0] if w5 else None
    cur.execute("SELECT date FROM (SELECT date, high FROM daily_prices WHERE stock_code=%s "
                "AND date <= %s ORDER BY date DESC LIMIT %s) t ORDER BY high DESC, date DESC LIMIT 1",
                (code, d0, 20))
    r = cur.fetchone()
    dstar["A3"] = None if r is None else r[0]
    v["dstar"] = dstar
    return v


def anchor_value(v, cand):
    return v.get({"A0": "H0", "A1": "H1", "A2": "H2", "A3": "H3"}[cand])


def z3(v, cand):
    """`ANC-P1` 통계량 — `H_X < HI` 인가(앵커 붕괴)."""
    h, hi = anchor_value(v, cand), v.get("H1")
    if h is None or hi is None:
        return None
    return float(h) < float(hi)


def h_obs(v, cand):
    """`ANC-P2` — `(max(close over [D,END]) − L) / (H_X − L)`  (§4 표 축자)."""
    h, L, mc = anchor_value(v, cand), v.get("L"), v.get("maxclose")
    if h is None or L is None or mc is None:
        return None
    den = float(h) - float(L)
    if den <= 0:
        return None
    return (float(mc) - float(L)) / den


def dd_anchor(v, cand):
    """§4-1 `DD(X) = 1 − L₅ / H_X` (창5 최저 · 앵커만 교체)."""
    h, L5 = anchor_value(v, cand), v.get("L5")
    if h is None or L5 is None or float(h) <= 0:
        return None
    return 100.0 * (1.0 - float(L5) / float(h))


# ═══════════════════════════════════════════════════════════════════════════
# 2. 귀무 — §7-2 (크기 정합 + 층화) · §7-3 무작위 앵커 `R`
# ═══════════════════════════════════════════════════════════════════════════
def permute_null_strat(ns, ps, groups, nperm=NPERM, seed=NULL_SEED):
    """§7-2 **층화** 순열 — 차수 재배정을 **글(post) «안에서»** 한다.

    출처: `run_ladder_tranche.py:105-119` `permute_null` 의 구조를 **그대로** 따르고
    (같은 `np.random.default_rng(seed)` · 같은 `rng.permuted(..., axis=1)` · 같은 크기 정합),
    **층 안에서만 섞도록 열 묶음을 나눈 것**이 유일한 차이다 — §7-2 가 선언한
    *「이 문서의 유일한 추가 자유도」* 1개가 바로 이 자리다.
    🔑 근거는 결과와 «무관하게» 먼저 적혀 있다: *「글마다 종목 수(3~12)와 시장 국면이 다르고,
       글을 섞어 재배정하면 「글 사이 차이」가 「차수 차이」로 새 들어온다」*(§7-2).
    """
    base = np.array(ns, dtype=np.int16)
    rng = np.random.default_rng(seed)
    M = np.tile(base, (nperm, 1))
    for g in sorted(set(groups)):
        idx = np.array([i for i, gg in enumerate(groups) if gg == g], dtype=np.int32)
        if idx.size > 1:
            M[:, idx] = rng.permuted(M[:, idx], axis=1)
    if not ps:
        z = np.zeros(nperm, dtype=np.int32)
        return z, z, nperm
    hi = np.array([h for h, _ in ps], dtype=np.int32)
    lo = np.array([l for _, l in ps], dtype=np.int32)
    A, B = M[:, hi], M[:, lo]
    V = (A < B).sum(axis=1)
    C = (A != B).sum(axis=1)
    return V, C, int((V == 0).sum())


def axis_stats(ns, xs, groups, delta=DELTA, stratified=True):
    """`LAD-T1` 통계 핵을 앵커만 바꿔 돌린다 — `pairset`·`statV` 는 동결 함수 그대로."""
    ps, dropped = pairset(xs, delta)
    v_obs, comp = statV(ns, ps)
    if stratified:
        vs, comps, zero = permute_null_strat(ns, ps, groups)
    else:
        vs, comps, zero = permute_null(ns, ps)
    p = float((vs <= v_obs).mean())
    return dict(V=v_obs, comp=comp, dropped=dropped, p=p, mean=float(vs.mean()),
                pzero=zero / len(vs), meancomp=float(comps.mean()), npairs=len(ps))


def required_count(cand):
    """§5-1 이 그 후보에게 요구하는 «충족 개수».

    §5-3 항등 조항 — `A1` 은 `ANC-P1`(0/n)·`ANC-P2`(1) 두 자리가 **정의상 참**이라
    충족 개수에 **산입하지 않는다** ⇒ **`A1` 은 `ANC-P3` 하나로만 결정된다.**
    🔑 ***`h ∈ [0,1]` 을 정의로 보장하는 앵커는 「틀이 성립한다」를 증명한 것이 아니라
       「측정을 포기한 것」이다***(§5-3).
    """
    return 3 - sum(1 for (c, _t) in IDENTITY_SLOTS if c == cand)


def cond_count(cand, ok1, ok2, ok3):
    """§5-1 충족 개수 — **항등 자리는 세지 않는다**(§5-3)."""
    n = 0
    if (cand, "ANC-P1") not in IDENTITY_SLOTS and ok1:
        n += 1
    if (cand, "ANC-P2") not in IDENTITY_SLOTS and ok2:
        n += 1
    if ok3:
        n += 1
    return n


def publish_bar_identity(cal, pub=PUB7, end=END):
    """`ANC-N4` ① 축 — 「발행 당일 봉 «포함»」과 「발행일 «직전» 봉」이 같은 봉인가.

    발행일이 **휴장**이면 둘 다 «마지막 거래일»을 가리킨다 ⇒ **구분 불가(항등)**.
    🔴 항등일 때 ①을 **다른 정의로 대체하지 않는다**(PD-14 1번 — 대체가 곧 새 자유도다).
    반환 `(항등인가, 당일포함 봉, 직전 봉)`.
    """
    incl = max([d for d in cal if str(d) <= pub], default=None)
    prev = max([d for d in cal if str(d) < pub], default=None)
    return (incl == prev), incl, prev


def random_anchor_highs(rows, j):
    """§7-3 — 건별로 창 `[D, END]` 안 **무작위 한 봉의 `high`**. 시드 = `NULL_SEED + j`.

    🔴 새 시드 계열을 만들지 않았다(`NULL_SEED` = `run_ladder_tranche.NULL_SEED`).
    """
    rng = np.random.default_rng(NULL_SEED + j)
    out = []
    for r in rows:
        highs = r["highs"]
        out.append(None if not highs else float(highs[int(rng.integers(0, len(highs)))]))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 3. 표본 조립
# ═══════════════════════════════════════════════════════════════════════════
def retro_items():
    """소급 post1~6 의 `exact` 28건(§8) — `run_ranking.py` 의 동결 로더를 그대로 쓴다."""
    rows = load_ledger("post6")             # 전 행 (필터는 아래에서 «글»로 건다)
    rows = [r for r in rows if r["post_date"] <= RETRO_LAST_POST_DATE]
    codes, _ = build_codes(include_post6=True)
    items, _post_idx = exact_items(rows, codes)
    nmap = {r["stock_name"] + "|" + r["reg_date"]: r for r in rows}
    for it in items:
        src = nmap.get(it["name"] + "|" + it["reg"])
        it["fill_n"] = (src or {}).get("fill_n") or ""
        it["post_date"] = (src or {}).get("post_date") or ""
    return items


def post7_items():
    """post7 판정 분모 — `exact` 6건(ANC-A-2). `INTAKE §1` 표를 옮겨 적은 그대로."""
    out = []
    for nm, code, reg, n, first_only, reentry, prior in POST7_EXACT:
        out.append(dict(post=7, log_no=POST7_LOG_NO, name=nm, code=code, reg=reg,
                        prec="exact", fill_n=str(n), first_only=first_only,
                        reentry=reentry, prior_cycle=prior, post_date=PUB7))
    return out


def end_for(cur, post_date):
    """그 글의 창 종료 `END` = **발행 당일 봉 «포함»**(동결 §4 표 `:122` · §13 `:467`).

    발행일이 휴장이면 그 글이 볼 수 있었던 마지막 봉 = **직전 거래일**이다.
    🔴 값을 «고르지» 않는다 — DB 의 `max(date) ≤ 발행일` 을 그대로 쓴다.
    """
    if not post_date:
        return END
    if post_date not in _END_CACHE:
        cur.execute("SELECT max(date) FROM daily_prices WHERE date <= %s", (post_date,))
        r = cur.fetchone()
        _END_CACHE[post_date] = str(r[0]) if r and r[0] else post_date
    return _END_CACHE[post_date]


def measure(cur, items):
    """건별 앵커 측정. 측정 불가(코드 없음·봉 없음)는 `ok=False` 로 남긴다.

    🔴 창 종료는 **건별 `end_for(post_date)`** 다(글별 발행일 포함) — post7 건은 `PUB7` 이
    토요일이라 `end_for` 가 `END`(2026-09-11)를 그대로 돌려준다(동결 `ANC-A-1` 과 일치).
    """
    for it in items:
        it["end"] = end_for(cur, it.get("post_date"))
        if not it.get("code"):
            it["ok"] = False
            it["why"] = "종목코드 미해결(사유 ① · DB 명부 부재)"
            continue
        v = anchors_for(cur, it["code"], it["reg"], it["end"])
        it["v"] = v
        it["ok"] = v["bars"] > 0 and v.get("H0") is not None
        if not it["ok"]:
            it["why"] = f"창 `[D, {it['end']}]` 봉 0 또는 등록일 봉 부재"
        it["highs"] = []
    return items


# ═══════════════════════════════════════════════════════════════════════════
# 4. 표 인쇄
# ═══════════════════════════════════════════════════════════════════════════
def p1_table(title, items, tag):
    """`ANC-P1` — `Z3(X)` = `H_X < HI` 인 건 비율."""
    both(f"### {title}\n")
    both(f"| 후보 | `Z3(X)` | 비율 | {tag} 예측 | 부합? | 최소 n {MIN_N} |")
    both("|---|---|---|---|---|---|")
    res = {}
    usable = [it for it in items if it.get("ok")]
    for c in CANDIDATES:
        if (c, "ANC-P1") in IDENTITY_SLOTS:
            both(f"| **{c}** | **항등 — 표 없음** | 0/n (정의상) | "
                 f"{PRED_P1[c][0 if tag == '소급' else 1]} | **항등** | "
                 "🔴 §5-3 — 충족 개수에 **산입 금지** |")
            res[c] = None
            continue
        hits = [it for it in usable if z3(it["v"], c)]
        n = len([it for it in usable if z3(it["v"], c) is not None])
        res[c] = (len(hits), n)
        ok = "판정 불가(n 미달)" if n < MIN_N else "—"
        both(f"| {c} | {len(hits)} | **{frac(len(hits), n)}** | "
             f"{PRED_P1[c][0 if tag == '소급' else 1]} | {ok} | "
             f"{'🟢 충족' if n >= MIN_N else '⛔ **미달**'} |")
    both("")
    both(RETRO_FOOTNOTE if tag == "소급" else
         "🟢 **이 열이 «검정»이다**(§5-4 — 채택 근거로 쓸 수 있는 유일한 열).")
    both("")
    return res


def p2_table(title, items, tag):
    """`ANC-P2` — `h_obs(X) ≤ 1` 인 건 비율(틀 성립률)."""
    both(f"### {title}\n")
    both(f"| 후보 | `h_obs ≤ 1` | 비율 | 중앙 `h_obs` | {tag} 예측 | 최소 n {MIN_N} |")
    both("|---|---|---|---|---|---|")
    res = {}
    usable = [it for it in items if it.get("ok")]
    for c in CANDIDATES:
        if (c, "ANC-P2") in IDENTITY_SLOTS:
            both(f"| **{c}** | **항등 — 표 없음** | 1 (정의상 · max close ≤ max high) | — | "
                 f"{PRED_P2[c][0 if tag == '소급' else 1]} | "
                 "🔴 §5-3 — 충족 개수에 **산입 금지** |")
            res[c] = None
            continue
        vals = [h_obs(it["v"], c) for it in usable]
        vals = [x for x in vals if x is not None]
        hit = sum(1 for x in vals if x <= 1.0)
        res[c] = (hit, len(vals))
        both(f"| {c} | {hit} | **{frac(hit, len(vals))}** | {fmt(med(vals), 3)} | "
             f"{PRED_P2[c][0 if tag == '소급' else 1]} | "
             f"{'🟢 충족' if len(vals) >= MIN_N else '⛔ **미달**'} |")
    both("")
    both(RETRO_FOOTNOTE if tag == "소급" else
         "🟢 **이 열이 «검정»이다**(§5-4).")
    both("")
    return res


# ═══════════════════════════════════════════════════════════════════════════
# 5. main
# ═══════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:      # noqa: C901
    ap = argparse.ArgumentParser(
        description="`ANC-` 앵커 재설계 축 — `PREREG_ANCHOR_REDESIGN.md` 실행. "
                    "🔴 `--mode` 는 **필수**다(C-23: 인자 없이 부르면 곁다리로 동결본을 덮어쓴다).")
    ap.add_argument("--mode", choices=("post7",), required=True,
                    help="post7 = 7번째 글 판정(소급 post1~6 탐색 열 + post7 검정 열).")
    a = ap.parse_args(argv)

    t0 = time.time()
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    # ── DB 실측 (창으로 쓰지 않는다 · 표기 의무 · PD-1 5번) ──────────────────
    cur.execute("SELECT max(date) FROM daily_prices")
    db_max = str(cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (db_max,))
    db_max_rows = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (END,))
    end_rows = cur.fetchone()[0]
    cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN '2026-06-01' AND %s "
                "ORDER BY date", (END,))
    cal = [r[0] for r in cur.fetchall()]

    # ═══ §0 ═══════════════════════════════════════════════════════════════
    say("# RESULTS_ANCHOR_POST7_NUMBERS — 기계 생성 (수정 금지)\n")
    doc("# `ANC-` 앵커 재설계 — 7번째 글 판정 (첫 실행)\n")
    both(f"생성 `run_anchor_redesign.py --mode {a.mode}` · 사전등록 `PREREG_ANCHOR_REDESIGN.md`"
         "(동결 `63e10a7` → 머지 `ef17c4f` · post7 fetch 보다 «앞» · PD-0)")
    both("재사용(새 코드 0줄) `run_reconstruct_post6.py`(`win_bars`·`dd_h` 및 그 SQL) · "
         "`run_ladder_tranche.py`(`DELTA`·`pairset`·`statV`·`permute_null`·`NULL_SEED`) · "
         "`run_ranking.py`(`load_ledger`·`build_codes`·`exact_items`)")
    both("")
    both("## §0. 실행 환경 · 동결 규약\n")
    both("| 항목 | 값 |")
    both("|---|---|")
    both(f"| 🔴 창 종료 | **{END}** = 발행일({PUB7} 토) 휴장 ⇒ 마지막 거래일 · "
         "**B-1**(`WRC-` 포함 전 축 · PD-1) |")
    both(f"| 🔴 실행 시 `max(date)` | **{db_max}** · 그 날짜 행수 **{db_max_rows:,}** "
         f"(표기 의무 · **창으로 쓰지 않는다** · PD-1 5번) |")
    both(f"| 창 종료일 행수 | `{END}` = **{end_rows:,}** 행 |")
    both(f"| 판정 분모 | post7 «신규» ∧ `exact` = **{len(POST7_EXACT)}건** (§2-3 · PD-4 1번) |")
    both(f"| 소급(탐색) | post1~6 `exact` **28건** (§8) — 🔴 **채택 근거 아님**(§5-4) |")
    both(f"| 주 검정 `m` | **{M_TESTS}** (`ANC-P1`·`P2`·`P3`) · Holm 1단계 = `.05/{M_TESTS}` = "
         f"**{HOLM1:.4f}** |")
    both(f"| 순열 시드 수 `S` | **{S_ANCHOR}** — `S ≥ 20m−1` = `20·{M_TESTS}−1` = "
         f"**{S_MIN_REQUIRED}**(권장 60) 위 · 최소 `p` = `1/{S_ANCHOR + 1}` = **{PERM_MIN_P:.4f}** "
         f"< {HOLM1:.4f} (§7-1) |")
    both(f"| 시드 | `NULL_SEED` = **{NULL_SEED}** (`run_ladder_tranche.py` 값 그대로 · "
         "🔴 새 시드를 만들지 않았다) · 무작위 앵커 `R` 시드 = "
         f"`NULL_SEED + j`, j = 0…{S_ANCHOR - 1} (§7-3) |")
    both(f"| `δ` · `V` · 순열 표본 | **{DELTA}%p** · `LAD-T1` 통계량 · **{NPERM:,}** — "
         "🔴 **이 문서에서 고치지 않는다. 앵커만 바꾼다**(§4-1) |")
    both(f"| `ANC-P3` 게이트 | 비교가능 쌍 **{PAIR_GATE}** (§10 · `PREREG_LADDER_TRANCHE.md` §5 승계) — "
         "🔴 **문턱을 낮춰 열지 않는다** |")
    both("| 최소 n | **3** (§10 · `ANC-P1`·`ANC-P2`) |")
    both("| `adj_factor` | **산술 0건** (가격에 곱하지 않는다 · 계열 SSOT) |")
    both("| DB | **SELECT 만** · 라이브 트리 import **0건** |")
    both("| 🔴 DB 지문 | *「`ANC-` 축의 DB 지문은 post7 판정 «시점»에 그때 값으로 박는다」*"
         "(§9-3) — 이 실행의 값이 위 두 줄이다 |")
    both("| 라이브 | 🔴 **라이브 채택 대상이 아니다** (`PREREG.md` §0-2) |")
    both("")
    both("🔴 **충돌 신고(§1-8 형식 · ANC-A-2)** — §2-3 은 판정 분모를 *「post6 에서 `REC-` 축이 쓴 "
         "분모(10건)와 «같은 규칙»」*이라 적었는데, **post6 신규 10건은 전부 `exact`** 였다 ⇒ 그때는 "
         "두 정의가 **같은 수**였다. **post7 에서 신규 10 ≠ `exact` 6 으로 처음 갈린다.** "
         "⇒ **명시된 쪽(`exact` 6)을 판정 분모로 쓰고, 신규 10 갈래는 민감도로 병기**한다. "
         "🔴 두 수를 **한 수로 합치지 않는다**.")
    both("🔴 **`WRC-` 판정 분모를 쓰지 않는다**(§2-3) — 갈래 종속을 피하기 위해서다. "
         "두 분모의 수를 한 수로 합치지 않는다.")
    both("🔴 **`A0` 는 대조군 전용**(채택 후보가 아니다 · §3) · **혼합 금지**"
         "(「`h` 는 `A1`, `DD` 는 `A3`」 같은 조합을 쓰지 않는다).")
    both("🔴 **`BUY-L5` 재개 조항 = 🔒 사장님 결정 ④(`PREREG_BUYLADDER` 계열 종결·기록 보존 · "
         "동결 `342f6f0`)로 «자동 소멸»**(§5-2 가 그 문형을 미리 적어 두었다 · PD-13 1번). "
         "이 산출물은 재개를 말하지 않는다.")
    both("🔴 **이 문서 안에서 새 예측을 만들지 않는다.**")
    both("")

    # ═══ §1 표본 ══════════════════════════════════════════════════════════
    both("## §1. 표본 — 판정(post7 `exact` 6) · 민감도(신규 10) · 소급(post1~6 `exact` 28)\n")
    retro = measure(cur, retro_items())
    p7 = measure(cur, post7_items())

    both("| 구분 | 건 | 측정 가능 | 측정 불가 | 지위 |")
    both("|---|---|---|---|---|")
    r_ok = [it for it in retro if it.get("ok")]
    both(f"| 소급 post1~6 `exact` | **{len(retro)}** | {len(r_ok)} | "
         f"{len(retro) - len(r_ok)} | 🔴 **탐색**(§5-4) |")
    p_ok = [it for it in p7 if it.get("ok")]
    both(f"| **post7 신규 `exact`** | **{len(p7)}** | **{len(p_ok)}** | "
         f"{len(p7) - len(p_ok)} | 🟢 **검정 · 판정 분모**(§2-3) |")
    both(f"| (민감도) post7 `approx` | {len(POST7_APPROX)} | — | — | "
         "⚪ 의무 민감도 · 판정 분모 **밖**(PD-4 1번) |")
    both(f"| (민감도) post7 `none` | {len(POST7_NONE)} | **0** | {len(POST7_NONE)} | "
         "🔴 등록일이 없어 앵커를 **못 잰다**(측정 불가) |")
    both(f"| post7 후속(등록일 축 밖) | {len(POST7_FOLLOWUP)} | — | — | PD-2 — 이중계상 금지 |")
    both("")
    both(f"⇒ **「신규 10」 갈래 = `exact` {len(POST7_EXACT)} + `approx` {len(POST7_APPROX)} + "
         f"`none` {len(POST7_NONE)}**. 🔴 `none` 2건은 **등록일 문장이 없어**(PD-4) 앵커의 `D` 가 "
         "없다 ⇒ **민감도 갈래에서도 측정 불가**로 센다. 「10건」과 「측정 가능 건」을 한 수로 "
         "합치지 않는다.")
    both("")
    for it in retro:
        if not it.get("ok"):
            both(f"- 🔴 소급 측정 불가 — post{it['post']} **{it['name']}**({it['reg']}): "
                 f"{it.get('why', '—')}")
    both("")
    both("| # | 글 | 종목 | 코드 | 등록일 | 창 봉수 | 창5 봉수 | 재진입 | `PRIOR_CYCLE_IN_WINDOW` |")
    both("|---|---|---|---|---|---|---|---|---|")
    for i, it in enumerate(p7, 1):
        v = it.get("v") or {}
        tr = "🔴 **절단**" if it["name"] in WIN5_TRUNC else "완전"
        both(f"| {i} | post7 | {it['name']} | `{it['code']}` | {it['reg']} | {v.get('bars', '—')} | "
             f"{v.get('win5_bars', '—')} ({tr}) | {'🔂 예' if it['reentry'] else '아니오'} | "
             f"**{it['prior_cycle']}** |")
    both("")
    both("🔴 **재진입 — 판정 분모 «안» 플래그 = 0**(PD-3): `exact` 6 안의 재진입은 **빛과전자 1건**뿐이고 "
         "그 건의 `P6-PRIOR_CYCLE_IN_WINDOW` = **0**(직전 등록일 08-05 < 창 시작 08-11 ⇒ **구성상 0**). "
         "🔴 글 전체 플래그 **2건**(지투파워·한국화장품제조)은 **둘 다 `approx` 갈래**다 — "
         "두 수를 한 수로 합치지 않는다.")
    both(f"🔴 **창5 절단 2건**(PD-12) — {' · '.join(f'{k} **{v}봉**' for k, v in WIN5_TRUNC.items())} "
         "(주 창 09-11 기준). `ANC-N4` ③ 축의 대상이다.")
    both("")

    # ═══ §2 앵커 원표 ══════════════════════════════════════════════════════
    both("## §2. 앵커 원표 — 건별 `A0`·`A1`·`A2`·`A3` (§3 · 새 코드 0줄)\n")
    both("| 종목 | 등록일 | `A0` 등록일고가 | `A1` 창최고(=`HI`) | `A2` 창5최고 | `A3` 후방20봉최고 | "
         "창최저 `L` | 창5최저 `L₅` | 창내 최대종가 | **항등 대조** |")
    both("|---|---|---|---|---|---|---|---|---|---|")
    ident_fail = []
    for it in p7:
        v = it.get("v") or {}
        if not it.get("ok"):
            both(f"| {it['name']} | {it['reg']} | — | — | — | — | — | — | — | ⛔ 측정 불가 |")
            continue
        okmark = "🟢 일치" if v.get("identity_ok") else "🔴 **불일치**"
        if not v.get("identity_ok"):
            ident_fail.append(it["name"])
        both(f"| {it['name']} | {it['reg']} | {fmt(v['H0'], 0)} | {fmt(v['H1'], 0)} | "
             f"{fmt(v['H2'], 0)} | {fmt(v['H3'], 0)} | {fmt(v['L'], 0)} | {fmt(v['L5'], 0)} | "
             f"{fmt(v['maxclose'], 0)} | {okmark} |")
    both("")
    both("🔑 **항등 대조 열이 무엇을 보나** — 이 스크립트가 `close` 까지 읽으려고 옮겨 적은 창이 "
         "동결 SQL(`run_reconstruct_post6.py:443-444` 의 `SELECT min(low), max(high)`)과 **같은 값**을 "
         "내는가. ***옮겨 적은 값이 동결 값과 같은지를 인쇄하지 않으면, 옮겨 적기는 조용히 틀린다.***")
    if ident_fail:
        both(f"🔴🔴 **항등 대조 실패 {len(ident_fail)}건**({', '.join(ident_fail)}) ⇒ "
             "**이 산출물은 무효다** — 옮겨 적은 창이 동결 창과 다르다.")
    both("")

    # ═══ §3 ANC-P1 ═════════════════════════════════════════════════════════
    both("## §3. `ANC-P1` — 앵커 붕괴 재발률 `Z3(X)` = `H_X < HI` 인 건 비율\n")
    p1_retro = p1_table("3-1. 소급 post1~6 (탐색)", retro, "소급")
    p1_post7 = p1_table("3-2. **post7 (검정)**", p7, "post7")

    # ═══ §4 ANC-P2 ═════════════════════════════════════════════════════════
    both("## §4. `ANC-P2` — 틀 성립률(복원 불요) `h_obs(X) ≤ 1` 인 건 비율\n")
    both("`h_obs(X) = (max(close over [D, END]) − L) / (H_X − L)` (§4 표 축자)\n")
    p2_retro = p2_table("4-1. 소급 post1~6 (탐색)", retro, "소급")
    p2_post7 = p2_table("4-2. **post7 (검정)**", p7, "post7")

    # ═══ §5 ANC-P3 ═════════════════════════════════════════════════════════
    both("## §5. `ANC-P3` — 앵커가 사다리 «순서»를 설명하는가 (`LAD-T1` 통계량 `V` · 앵커만 교체)\n")
    both(f"`DD(X) = 1 − L₅ / H_X` · `δ` = **{DELTA}%p** · 통계량 `V` · 단측 `p = P(V ≤ V_obs)` — "
         "🔴 전부 `PREREG_LADDER_TRANCHE.md` §4-2~§4-4 **그대로**(§4-1).\n")
    both(f"예측(소급·post7 공통): **{PRED_P3}**\n")

    def pool(items, tag):
        rows = []
        for it in items:
            if not it.get("ok"):
                continue
            try:
                n = int(it.get("fill_n") or 0)
            except ValueError:
                n = 0
            if n <= 0:
                continue
            v = it["v"]
            rows.append(dict(name=it["name"], post=it.get("post", 7), N=n, v=v,
                             highs=[b[2] for b in window_bars(
                                 cur, it["code"], it["reg"], it.get("end") or END)],
                             tag=tag))
        return rows

    pool_retro = pool(retro, "소급")
    pool_p7 = pool(p7, "post7")

    _r_nofill = [it["name"] for it in retro
                 if it.get("ok") and not str(it.get("fill_n") or "").strip().isdigit()]
    _r_notok = [it["name"] for it in retro if not it.get("ok")]
    both(f"- 소급 풀 **{len(pool_retro)}건**(차수 `fill_n` 이 있는 `exact` 건) · "
         f"post7 풀 **{len(pool_p7)}건** · **누적 풀 {len(pool_retro) + len(pool_p7)}건**")
    both(f"  - 🔑 **산술 출처**: 소급 `exact` **{len(retro)}건** "
         f"− 측정 불가 **{len(_r_notok)}건**"
         + (f"({', '.join(_r_notok)})" if _r_notok else "")
         + f" − 차수(`fill_n`) 빈칸 **{len(_r_nofill)}건**"
         + (f"({', '.join(_r_nofill)})" if _r_nofill else "")
         + f" = **{len(pool_retro)}건**. "
           "🔴 두 사유는 **다른 고장**이라 한 수로 묶지 않는다 — 앞은 «DB 에 봉이 없다», "
           "뒤는 «원장에 차수가 안 적혀 있다»다.")
    both("- 🔴 차수(`fill_n`)가 비어 있는 `exact` 건은 `ANC-P3` 에서 **빠진다** "
         "— 「차수가 없다」가 아니라 **「원장에 안 적혀 있다」**다"
         "(post2 의 `fill_level = unknown/full` 계열).")
    both("")

    def p3_block(title, rows, tag, allow_strat_note=True):
        both(f"### {title}\n")
        if len(rows) < 2:
            both(f"⛔ **표본 {len(rows)}건 — 쌍을 만들 수 없다. 미룬다.**\n")
            return None
        both("| 후보 | `V_obs` | 비교가능 쌍 | δ 대역 제외 | 귀무 평균 `V` | **`p`(층화)** | "
             "`p`(층화 없음 · 민감도) | 게이트 40 |")
        both("|---|---|---|---|---|---|---|---|")
        res = {}
        ns = [r["N"] for r in rows]
        groups = [r["post"] for r in rows]
        one_post = len(set(groups)) == 1
        for c in CANDIDATES:
            xs = [dd_anchor(r["v"], c) for r in rows]
            if any(x is None for x in xs):
                keep = [i for i, x in enumerate(xs) if x is not None]
                xs2 = [xs[i] for i in keep]
                ns2 = [ns[i] for i in keep]
                gs2 = [groups[i] for i in keep]
            else:
                xs2, ns2, gs2 = xs, ns, groups
            if len(xs2) < 2:
                both(f"| {c} | — | — | — | — | — | — | ⛔ 표본 부족 |")
                res[c] = None
                continue
            st = axis_stats(ns2, xs2, gs2, stratified=True)
            un = axis_stats(ns2, xs2, gs2, stratified=False)
            gate = ("🟢 열림" if st["comp"] >= PAIR_GATE
                    else f"⛔ **미달** ({st['comp']} < {PAIR_GATE})")
            both(f"| {c} | {st['V']} | **{st['comp']}** | {st['dropped']} | {st['mean']:.2f} | "
                 f"**{st['p']:.4f}** | {un['p']:.4f} | {gate} |")
            res[c] = dict(strat=st, unstrat=un)
        both("")
        if one_post and allow_strat_note:
            both("🔴🔴 **층화 갈래와 층화 없는 갈래가 «구성상 항등»이다** — 이 표본은 **글이 하나**라 "
                 "「글 «안에서» 재배정」과 「전체 재배정」이 **같은 동작**이다"
                 "(`RESULTS_RANKING_POST6_NUMBERS.md` 의 *「글이 하나다 ⇒ 구성상 항등 = 판별력 0」* "
                 "관용 승계). ⇒ 이 열의 두 `p` 가 같은 것은 **일치의 증거가 아니라 판별력 0**이다.")
        else:
            splits = [c for c, r in res.items() if r and
                      ((r["strat"]["p"] < ALPHA) != (r["unstrat"]["p"] < ALPHA))]
            if splits:
                both(f"🔴🔴 **층화 ↔ 비층화가 갈린다**({', '.join(splits)}) ⇒ **`ANC-N4` 발동 — "
                     "선언 금지**(§7-2 마지막 줄).")
            else:
                both("🟢 층화 ↔ 비층화가 `α = 0.05` 를 사이에 두고 갈리지 않는다(§7-2 의무 민감도).")
        both("")
        both(RETRO_FOOTNOTE if tag == "소급" else "🟢 **이 열이 «검정»이다**(§5-4).")
        both("")
        return res

    p3_post7 = p3_block("5-1. **post7 단독 (검정)**", pool_p7, "post7")
    # 🔴 게이트 40 이 이 표본에서 «값 때문에» 닫힌 것이 아니라 **구조적으로** 닫힌다는 증명.
    #    쌍의 상한은 C(n,2) 이고, 비교가능 쌍은 그 중 **`N` 이 서로 다른** 쌍뿐이다.
    if pool_p7:
        _ns = sorted(r["N"] for r in pool_p7)
        _n = len(_ns)
        _tot = _n * (_n - 1) // 2
        _cnt = {}
        for _v in _ns:
            _cnt[_v] = _cnt.get(_v, 0) + 1
        _same = sum(c * (c - 1) // 2 for c in _cnt.values())
        _diff = _tot - _same
        both(f"🔴🔴 **게이트 {PAIR_GATE} 은 이 표본에서 «값 때문에» 닫힌 것이 아니라 "
             "«구성»으로 닫힌다 — 산술로 증명한다.**")
        both("")
        both(f"- post7 풀 **{_n}건** ⇒ 만들 수 있는 쌍의 **상한** = "
             f"`C({_n},2)` = **{_tot}** — 이미 **{_tot} < {PAIR_GATE}** 다.")
        both(f"- 게다가 비교가능 쌍은 *「`N` 이 서로 «다른» 쌍」*뿐이다. 이 표본의 차수는 "
             f"`{_ns}` 이고 같은 `N` 끼리 묶인 쌍이 **{_same}** 이라 "
             f"**`N` 이 다른 쌍은 최대 {_diff}** 개다(δ 대역 제외 «전»의 상한).")
        both(f"- ⇒ ***어떤 앵커 후보를 넣어도 post7 «단독» 열의 비교가능 쌍은 {_diff} 을 "
             f"넘을 수 없다*** ⇒ 게이트 {PAIR_GATE} 은 **이 글에서 열릴 수 없었다.** "
             "🔑 ***그러므로 「미달」을 「예측이 틀렸다」로 읽으면 안 된다*** — "
             "«잴 수 없었던 것»이다.")
        both(f"- 🔴 **그리고 이것이 문턱을 낮출 이유가 «되지 않는다»** — {PAIR_GATE} 은 "
             "동결값이고(§10), 열리는 길은 **표본이 누적되는 것** 하나뿐이다.")
        both("")
    p3_cum = p3_block("5-2. 누적(소급 + post7) — 탐색", pool_retro + pool_p7, "소급",
                      allow_strat_note=False)

    # §7-3 무작위 앵커 대조군 R + ANC-N5
    both("### 5-3. 무작위 앵커 대조군 `R` (§7-3) · `ANC-N5` 상수 검사\n")
    r_rows = pool_p7 if pool_p7 else []
    n_distinct = [len({float(h) for h in r["highs"]}) for r in r_rows]
    n5_fail = [r["name"] for r, k in zip(r_rows, n_distinct) if k < 2]
    both(f"- `R` 시드 **{S_ANCHOR}개** = `NULL_SEED + j`, j = 0…{S_ANCHOR - 1} "
         f"(= {NULL_SEED} … {NULL_SEED + S_ANCHOR - 1}) — 🔴 새 시드 계열을 만들지 않았다.")
    both(f"- **`ANC-N5` 상수 검사** — 창 `[D, END]` 안 서로 다른 `high` 값의 개수: "
         + (", ".join(f"{r['name']} {k}" for r, k in zip(r_rows, n_distinct)) or "—"))
    if n5_fail:
        both(f"- 🔴🔴 **`ANC-N5` 실패 {len(n5_fail)}건**({', '.join(n5_fail)}) — `H_R` 값이 1가지뿐이다 "
             "⇒ **절차 무효**(`WRC-X1` 3번 관용).")
    else:
        both("- 🟢 **`ANC-N5` 통과** — 모든 건에서 서로 다른 `high` 가 2개 이상이다.")
    both("")

    r_beats = {}
    if r_rows and len(r_rows) >= 2:
        ns_r = [r["N"] for r in r_rows]
        gs_r = [r["post"] for r in r_rows]
        v_R = []
        for j in range(S_ANCHOR):
            hs = random_anchor_highs(r_rows, j)
            xs = []
            for r, h in zip(r_rows, hs):
                L5 = r["v"].get("L5")
                xs.append(None if (h is None or L5 is None or h <= 0)
                          else 100.0 * (1.0 - float(L5) / float(h)))
            keep = [i for i, x in enumerate(xs) if x is not None]
            if len(keep) < 2:
                continue
            ps, _dr = pairset([xs[i] for i in keep], DELTA)
            v_obs, _c = statV([ns_r[i] for i in keep], ps)
            v_R.append(v_obs)
        both(f"- `V(R_j)` 실현 **{len(v_R)}개** · 최소 {min(v_R) if v_R else '—'} · "
             f"중앙 {fmt(med(v_R), 1)} · 최대 {max(v_R) if v_R else '—'}")
        both("")
        both("🔒 **이 표는 «독법 A» — 동결 §5-1 3번 축자**: *「무작위 앵커 대조군 `R`"
             "(§7-3 · 시드 100개) 중 `V(R_j) ≤ V(X)` 인 것이 **0개**"
             " ⇒ 순열 `p = 1/101 = .0099 <` Holm 1단계 **.0167**」*"
             "(`PREREG_ANCHOR_REDESIGN.md:244-245`). "
             "🔴 **이 문언에는 «비교가능 쌍 게이트»가 없다.** "
             "게이트를 얹는 «독법 B»(§10)는 §7 에 따로 인쇄한다 — 두 독법이 상반된다(§1-8 충돌 신고).")
        both("")
        both("| 후보 | `V(X)` | `V(R_j) ≤ V(X)` 인 `R` 수 | §5-1 조건 ③ (0개여야 함) · **독법 A** |")
        both("|---|---|---|---|")
        for c in CANDIDATES:
            r3 = (p3_post7 or {}).get(c)
            if not r3:
                both(f"| {c} | — | — | ⛔ 미판정 |")
                r_beats[c] = None
                continue
            vx = r3["strat"]["V"]
            beat = sum(1 for v in v_R if v <= vx)
            r_beats[c] = beat
            both(f"| {c} | {vx} | **{beat}** | "
                 f"{'🟢 충족' if beat == 0 else '🔴 **미충족**'} |")
        both("")
        both(f"🔑 ***`R` 이 없으면 후보 간 `V` 차이는 뜻이 없다***(`REGISTRY.md`). "
             f"조건 ③ 충족 시 순열 `p` = `1/{S_ANCHOR + 1}` = **{PERM_MIN_P:.4f}** < Holm 1단계 "
             f"**{HOLM1:.4f}**(§5-1 3번).")
    else:
        both("- ⛔ post7 풀이 2건 미만이라 `R` 대조를 돌리지 않았다.")
    both("")

    # ═══ §6 대칭 단언 ══════════════════════════════════════════════════════
    both("## §6. 대칭 단언 `ANC-N1`~`N5` — **하나라도 빠지면 산출물 무효**(§6)\n")

    # N1 — 판별력
    sides = {}
    for c in CANDIDATES:
        r = p1_post7.get(c)
        sides[c] = None if not r or not r[1] else (r[0] / r[1] >= 0.5)
    measurable = {c: s for c, s in sides.items() if s is not None}
    n1_fire = len(set(measurable.values())) <= 1 and len(measurable) >= 2
    both("| 이름 | 무엇을 묻나 | 실측 | 발동 | 처리 |")
    both("|---|---|---|---|---|")
    both(f"| **`ANC-N1`** 판별력 | 후보들이 서로 «다른 답»을 주는가 | "
         + (" · ".join(f"{c} {'≥1/2' if s else '<1/2'}" for c, s in measurable.items()) or "—")
         + f" | {'🔴 **발동**' if n1_fire else '🟢 미발동'} | "
         + ("🔴 「앵커가 원인이 아니다」 ⇒ **어느 채택도 선언 금지**" if n1_fire
            else "후보 간 답이 갈린다 ⇒ 판정 계속") + " |")
    both("| **`ANC-N2`** 항등 고지 | 정의상 참을 증거로 세지 않았나 | "
         "`A1` 의 `ANC-P1`(0/n)·`ANC-P2`(1) | 🔴 **상시** | "
         "**「항등 — 표 없음」 인쇄 · §5-1 충족 개수 산입 «금지»** ⇒ "
         "**`A1` 은 `ANC-P3` 하나로만 결정된다**(이 비대칭을 매회 명시) |")

    # N3 — 사후 정보
    both("| **`ANC-N3`** 사후 정보 | `H_X` 가 확정되는 날이 언제인가 | 아래 §6-1 표 | "
         "🔴 **병기 의무**(탈락 사유 아님) | 중앙 > 0 이면 *「이 앵커는 사후 정보를 쓴다」* 상시 병기 |")

    # N4 — 창·표본 민감도 (① 항등 · ②③ 만으로 판정)
    both("| **`ANC-N4`** 창·표본 민감도 | 갈래를 바꾸면 답이 갈리나 | 아래 §6-2 세 축 | "
         "계산 후 판정 | 갈리는 축이 하나라도 있으면 🔴 **선언 금지** |")
    both(f"| **`ANC-N5`** 대조군 상수 검사 | `R` 이 상수가 아닌가 | 서로 다른 `H_R` 개수 "
         f"{'≥ 2 전건' if not n5_fail else f'1가지 {len(n5_fail)}건'} | "
         f"{'🟢 미발동' if not n5_fail else '🔴 **발동**'} | 1 이면 **절차 무효** |")
    both("")

    # §6-1 ANC-N3
    both("### 6-1. `ANC-N3` — 사후 정보(look-ahead) · 건별 `D` → `d*` 거래일 수\n")
    both("| 종목 | `A0` | `A1` | `A2` | `A3` |")
    both("|---|---|---|---|---|")
    lags = {c: [] for c in CANDIDATES}
    for it in p7:
        if not it.get("ok"):
            continue
        v, cells = it["v"], []
        for c in CANDIDATES:
            d = v["dstar"].get(c)
            k = None if d is None else trading_days_between(cal, v["d0"], d)
            if k is not None:
                lags[c].append(k)
            cells.append("—" if k is None else str(k))
        both(f"| {it['name']} | " + " | ".join(cells) + " |")
    both("")
    both("| 후보 | 중앙 거래일 수 | 사후 정보? |")
    both("|---|---|---|")
    for c in CANDIDATES:
        m = med(lags[c])
        post_info = (m is not None and m > 0)
        both(f"| {c} | {fmt(m, 1)} | "
             + ("🔴 **예 — 「이 앵커는 사후 정보를 쓴다」 상시 병기**" if post_info
                else "아니오(등록일 종가 시점에 확정)") + " |")
    both("")
    both("🔴 **`ANC-N3` 는 「탈락 사유」가 아니라 「병기 의무」다**(§6). 사후 정보를 쓰는 앵커도 채택될 수 "
         "있지만, 그때 그 산출물은 *「저자가 알 수 없었던 값으로 저자의 행동을 설명했다」*는 한계를 매번 "
         "달고 다닌다. 🔑 ***이 한계를 안 적으면 다음 사람이 그 앵커를 라이브 규칙으로 옮긴다.***")
    both("")

    # §6-2 ANC-N4
    both("### 6-2. `ANC-N4` — 창·표본 민감도 세 축\n")
    both("| 축 | 갈래 | 실측 | 판정이 갈리나 |")
    both("|---|---|---|---|")
    ax1_ident, ax1_incl, ax1_prev = publish_bar_identity(cal)
    both("| **①** `END` = 발행일 «직전» 봉 | 「발행 당일 봉 포함」 ↔ 「발행일 직전 봉」 | "
         + (f"🔴🔴 **둘 다 {ax1_incl} 을 가리킨다** — 발행일 {PUB7} 가 **휴장(토)** 이기 때문"
            if ax1_ident else f"당일포함 {ax1_incl} ↔ 직전 {ax1_prev}")
         + " | " + ("🔴 **구분 불가(항등)**" if ax1_ident else "계산 후 판정") + " |")
    # 🔴🔴 **`ANC-N4` 는 「세 판정 × 전 갈래」 전수 검사다.**
    #    동결 §6 `ANC-N4` 행(`PREREG_ANCHOR_REDESIGN.md:282`): *「① `END` = 발행일 «직전» 봉
    #    ② 재진입 포함↔제외 ③ 창5 절단 포함↔제외 — **세 축 전부 인쇄** |
    #    **판정이 갈리는 축이 하나라도 있으면 🔴 선언 금지**」*.
    #    여기서 「판정」은 §5-1 의 **세** 최소 조건(`ANC-P1`·`P2`·`P3`) 전부다 —
    #    축마다 «한» 검정만 보면 다른 검정에서 갈리는 것을 놓친다(이 스크립트의 옛 결함).
    def _n4_p1(items):
        usable = [it for it in items if it.get("ok")]
        out = {}
        for c in CANDIDATES:
            if (c, "ANC-P1") in IDENTITY_SLOTS:
                out[c] = (None, None)
                continue
            n = len([it for it in usable if z3(it["v"], c) is not None])
            hits = sum(1 for it in usable if z3(it["v"], c))
            out[c] = ((hits, n), None if n < MIN_N else bool(hits / n < 0.5))
        return out

    def _n4_p2(items):
        usable = [it for it in items if it.get("ok")]
        out = {}
        for c in CANDIDATES:
            if (c, "ANC-P2") in IDENTITY_SLOTS:
                out[c] = (None, None)
                continue
            vals = [x for x in (h_obs(it["v"], c) for it in usable) if x is not None]
            hit = sum(1 for x in vals if x <= 1.0)
            out[c] = ((hit, len(vals)),
                      None if len(vals) < MIN_N else bool(hit / len(vals) >= 2.0 / 3.0))
        return out

    def _n4_p3(items):
        """`ANC-P3`(§5-1 3번) = 무작위 앵커 `R` 중 `V(R_j) ≤ V(X)` 가 **0개**.

        게이트(비교가능 쌍 `PAIR_GATE`)가 닫히면 «미판정»(None) — §7 의 산술을 그대로 쓴다.
        """
        rows = pool(items, "post7")
        out = {c: (None, None) for c in CANDIDATES}
        if len(rows) < 2:
            return out
        ns = [r["N"] for r in rows]
        gs = [r["post"] for r in rows]
        st = {}
        for c in CANDIDATES:
            xs = [dd_anchor(r["v"], c) for r in rows]
            keep = [i for i, x in enumerate(xs) if x is not None]
            st[c] = (axis_stats([ns[i] for i in keep], [xs[i] for i in keep],
                                [gs[i] for i in keep], stratified=True)
                     if len(keep) >= 2 else None)
        gate = any(v and v["comp"] >= PAIR_GATE for v in st.values())
        vR = []
        for j in range(S_ANCHOR):
            hs = random_anchor_highs(rows, j)
            xs = []
            for r, h in zip(rows, hs):
                L5 = r["v"].get("L5")
                xs.append(None if (h is None or L5 is None or h <= 0)
                          else 100.0 * (1.0 - float(L5) / float(h)))
            keep = [i for i, x in enumerate(xs) if x is not None]
            if len(keep) < 2:
                continue
            ps, _dr = pairset([xs[i] for i in keep], DELTA)
            v_obs, _c = statV([ns[i] for i in keep], ps)
            vR.append(v_obs)
        for c in CANDIDATES:
            v = st.get(c)
            if not v or not vR:
                continue
            beat = sum(1 for x in vR if x <= v["V"])
            out[c] = ((beat, len(vR)), None if not gate else bool(beat == 0))
        return out

    def _n4_branch(items):
        """한 갈래에서 후보별 세 판정 — `{후보: {검정: (원값, True/False/None)}}`."""
        a, b, c3 = _n4_p1(items), _n4_p2(items), _n4_p3(items)
        return {c: {"ANC-P1": a[c], "ANC-P2": b[c], "ANC-P3": c3[c]} for c in CANDIDATES}

    N4_BASE = _n4_branch(p7)

    def _n4_diff(alt_items):
        """주 갈래 ↔ 대안 갈래의 **세 판정 전수** 차분.

        🔴 `True ↔ False` 만 「갈린다」로 센다 — «미판정»은 값이 없는 것이라 갈릴 수 없다.
        ⚠️ 다만 「판정 ↔ 미판정」으로 상태가 바뀐 자리는 따로 세어 인쇄한다(숨기지 않는다).
        """
        alt = _n4_branch(alt_items)
        flips, mutes = [], []
        for c in CANDIDATES:
            for k in ("ANC-P1", "ANC-P2", "ANC-P3"):
                x, y = N4_BASE[c][k][1], alt[c][k][1]
                if x is None and y is None:
                    continue
                if x is None or y is None:
                    mutes.append(c + "×`" + k + "`")
                elif x != y:
                    flips.append(c + "×`" + k + "`("
                                 + ("△" if y else "▽") + ")")
        return alt, flips, mutes

    # ② 재진입 포함 ↔ 제외
    p7_norein = [it for it in p7 if not it["reentry"]]
    alt2, split2, mute2 = _n4_diff(p7_norein)
    def _n4_cells(alt, key):
        """세 판정 중 한 검정의 「주 ↔ 대안」 «값»을 후보별로 한 칸에."""
        out = []
        for c in CANDIDATES:
            a, b = N4_BASE[c][key][0], alt[c][key][0]
            if a is None and b is None:
                out.append(c + " 항등")
                continue
            out.append(c + " " + (frac(*a) if a else "—")
                       + "↔" + (frac(*b) if b else "—"))
        return " · ".join(out)

    n_rein = sum(1 for it in p7 if it["reentry"])
    both("| **②** 재진입 포함 ↔ 제외 | 포함 "
         f"{len(p7)}건 ↔ 제외 {len(p7_norein)}건 | "
         f"`ANC-P1` {_n4_cells(alt2, 'ANC-P1')} │ `ANC-P2` {_n4_cells(alt2, 'ANC-P2')} "
         f"│ `ANC-P3`(`V(R)≤V(X)` 수) {_n4_cells(alt2, 'ANC-P3')} "
         f"— `exact` 안 재진입 **{n_rein}건** | "
         + (f"🔴 **갈린다**({', '.join(split2)})" if split2 else "🟢 안 갈린다")
         + (f" · ⚠️ 판정↔미판정 {len(mute2)}자리" if mute2 else "") + " |")
    # ③ 창5 절단 포함 ↔ 제외
    p7_notrunc = [it for it in p7 if it["name"] not in WIN5_TRUNC]
    alt3, split3, mute3 = _n4_diff(p7_notrunc)
    both(f"| **③** 창5 절단 포함 ↔ 제외 | 포함 {len(p7)}건 ↔ 제외 {len(p7_notrunc)}건 | "
         f"`ANC-P1` {_n4_cells(alt3, 'ANC-P1')} │ `ANC-P2` {_n4_cells(alt3, 'ANC-P2')} "
         f"│ `ANC-P3`(`V(R)≤V(X)` 수) {_n4_cells(alt3, 'ANC-P3')} — 절단 "
         f"**{len(WIN5_TRUNC)}건**("
         + " · ".join(f"{k} {v}봉" for k, v in WIN5_TRUNC.items()) + ") | "
         + (f"🔴 **갈린다**({', '.join(split3)})" if split3 else "🟢 안 갈린다")
         + (f" · ⚠️ 판정↔미판정 {len(mute3)}자리" if mute3 else "") + " |")
    both("")
    both(f"🔴🔴 **① 축이 이번 회차에 «항등»이다** — 발행일({PUB7})이 **휴장**이라 「발행 당일 봉 «포함»」과 "
         f"「발행일 «직전» 봉」이 **같은 봉({END})** 을 가리킨다. ⇒ ① 은 §5-3 문형대로 "
         "**「구분 불가(항등)」로 명시 인쇄**하고 **②·③ 두 축으로만 `ANC-N4` 를 판정**한다. "
         "🔴 ***①을 다른 정의로 «대체하지 않는다»*** — 대체하면 그게 새 자유도다(PD-14 1번).")
    n4_fire = bool(split2 or split3)
    both(f"⇒ **`ANC-N4` {'🔴 발동 — 선언 금지' if n4_fire else '🟢 미발동'}** "
         "— ②·③ 각 축에서 **세 판정(`ANC-P1`·`P2`·`P3`) 전수**를 대조한 결과다"
         "(① 은 이번 회차에 항등이라 갈릴 수 없다). "
         + (f"갈린 자리: **{' · '.join(split2 + split3)}** "
            "(△ = 대안 갈래에서 충족 · ▽ = 대안 갈래에서 미충족)."
            if n4_fire else "세 판정 × 두 축 어디에서도 `True ↔ False` 뒤집힘이 없다.")
         + (f" ⚠️ 판정↔미판정으로 «상태»만 바뀐 자리 {len(mute2) + len(mute3)}개는 "
            "갈림으로 세지 않았다(값이 없는 것은 갈릴 수 없다) — 그래도 위 표에 인쇄했다."
            if (mute2 or mute3) else ""))
    if n4_fire:
        both("")
        both("🔴🔴 **동결 §6 `ANC-N4` 행이 *「판정이 갈리는 축이 하나라도 있으면 "
             "🔴 선언 금지」*라고 적었다**(`PREREG_ANCHOR_REDESIGN.md:282`) ⇒ "
             "***이번 글에서는 어느 채택도 선언하지 않는다.*** "
             "🔑 ***갈리지 않는 축만 골라 읽으면 그게 사후적합이다.***")
    both("")

    # ═══ §7 채택 판정 ══════════════════════════════════════════════════════
    both("## §7. 채택 판정 — §5-1 최소 조건(전부 AND) · §5-2 세 갈래\n")
    both("🔒 **이 표의 ③ 열은 «독법 B»** — §10 의 *「비교가능 쌍 40」* 게이트를 "
         "§5-1 3번 «위에» 얹은 읽기다. **§5-3 표(«독법 A» · 게이트 없는 축자)와 기호가 "
         "상반될 수 있고, 이번이 그렇다.** 🔴 **두 표의 기호를 억지로 통일하지 않았다** "
         "— 아래 «충돌 신고» 참조.")
    both("")
    both("| 후보 | ① `Z3 < 1/2` | ② `h_obs ≤ 1` ≥ 2/3 | ③ `V(R_j) ≤ V(X)` = 0 (**독법 B**) | 충족 개수 | 비고 |")
    both("|---|---|---|---|---|---|")
    p3_gate_ok = bool(p3_post7) and any(
        r and r["strat"]["comp"] >= PAIR_GATE for r in p3_post7.values())
    adopted = []
    for c in ADOPTABLE:
        cells = []
        # ①
        r1 = p1_post7.get(c)
        ok1 = bool(r1 and r1[1] and (r1[0] / r1[1] < 0.5))
        cells.append("**항등 — 산입 금지**" if (c, "ANC-P1") in IDENTITY_SLOTS
                     else ("🟢 " if ok1 else "🔴 ") + (frac(*r1) if r1 else "—"))
        # ②
        r2 = p2_post7.get(c)
        ok2 = bool(r2 and r2[1] and (r2[0] / r2[1] >= 2.0 / 3.0))
        cells.append("**항등 — 산입 금지**" if (c, "ANC-P2") in IDENTITY_SLOTS
                     else ("🟢 " if ok2 else "🔴 ") + (frac(*r2) if r2 else "—"))
        # ③
        b = r_beats.get(c)
        ok3 = bool(p3_gate_ok and b == 0)
        if not p3_gate_ok:
            cells.append(f"⛔ **미판정**(쌍 < {PAIR_GATE})")
        else:
            cells.append(("🟢 0" if ok3 else f"🔴 {b}") if b is not None else "⛔ 미판정")
        cnt = cond_count(c, ok1, ok2, ok3)
        need = required_count(c)
        memo = ("🔴 §5-3 — `ANC-P3` 하나로만 결정된다" if c == "A1" else "—")
        both(f"| **{c}** | " + " | ".join(cells) + f" | **{cnt}/{need}** | {memo} |")
        if p3_gate_ok and cnt == need:
            adopted.append(c)
    both(f"| (대조군) `A0` | — | — | — | — | 🔴 **채택 후보가 아니다**(§3 · 이미 무너진 것을 "
         "다시 후보에 넣으면 「기각을 무르는」 동작) |")
    both("")

    def _p3_conflict_report():
        """🔴 §5-3(독법 A) ↔ §7 표(독법 B)가 조건 ③ 에 «상반된 기호»를 낸다.

        🔒 어느 쪽으로도 고치지 않고 **둘 다 인쇄**하고, 어느 독법이 맞는지는
        🔒 **사장님 결정**으로 넘긴다(§1-8 충돌 신고 형식).
        🔴 이 신고는 `ANC-N4`·`N1`·`N5` 가 먼저 발동해도 **반드시 인쇄한다** —
        다른 발동 때문에 가려지면 다음 사람이 §5-3 의 🟢 만 보고 「충족했다」고 읽는다.
        """
        # 🔴 §5-3(독법 A)과 §7(독법 B)이 조건 ③ 에 대해 **상반된 기호**를 낸다.
        #    어느 쪽으로도 «고치지 않고» 둘 다 인쇄하고, 판정은 🔒 사장님 결정으로 넘긴다.
        both("")
        both("### 🔴 충돌 신고 (§1-8 형식) — `ANC-P3`(조건 ③)의 두 독법\n")
        both("| 독법 | 동결 문언 | 이 표본에서의 기호 | 어디에 인쇄됐나 |")
        both("|---|---|---|---|")
        a_cells = " · ".join(
            f"{c} " + ("🟢 충족(0개)" if r_beats.get(c) == 0
                       else ("⛔ 미판정" if r_beats.get(c) is None else f"🔴 {r_beats[c]}개"))
            for c in CANDIDATES)
        both("| **A**(축자) | §5-1 3번 *「무작위 앵커 대조군 `R`(§7-3 · 시드 100개) 중 "
             "`V(R_j) ≤ V(X)` 인 것이 **0개** ⇒ 순열 `p = 1/101 = .0099 <` Holm **.0167**」* "
             f"(`PREREG_ANCHOR_REDESIGN.md:244-245`) — **쌍 게이트 문언이 없다** | {a_cells} | "
             "§5-3 표 |")
        both(f"| **B**(게이트) | §10 *「`ANC-P3` 의 열림 조건 = 비교가능 쌍 **{PAIR_GATE}**」* "
             f"+ §5-4 *「채택은 post7 열로만」* | ⛔ **전 후보 미판정** — post7 단독 풀의 "
             f"비교가능 쌍이 {PAIR_GATE} 미만 | 아래 §7 표 |")
        both("")
        both(f"🔴 **두 독법이 상반되는 이유** — §10 이 근거로 든 *「post6 은 **161쌍**으로 "
             "열려 있었다」* 의 161쌍은 **누적 표본**에서 나온 수다(§7-2 의 층화가 «글 사이»를 전제하는 "
             "것도 같은 방향이다). 그런데 §5-4 는 *「채택은 post7 열로만」*이라 못박는다. "
             "⇒ **post7 «단독» 열만으로는 게이트가 구조적으로 닫히고**, 그러면 §5-1 의 축자 독법 A 와 "
             "§10 의 게이트 독법 B 가 **같은 조건 ③ 에 대해 다른 기호**를 낸다.")
        both(f"🔴 **어느 쪽으로도 고치지 않았다** — §5-3 은 A 의 기호를, §7 표는 B 의 기호를 "
             "그대로 인쇄한다. 기호를 억지로 통일하면 그게 «문언 개정»이고, 개정은 "
             "**새 사전등록**으로만 한다. 🔴 **문턱을 낮춰 열지도 않는다**"
             f"(§10 마지막 줄 · 게이트 보고 파라미터 하향 금지).")
        both("")
        both("🔒🔒 **사장님 결정 항목** — 조건 ③ 를 «A(축자)»로 읽을지 «B(게이트)»로 "
             "읽을지는 **문언 해석**이지 값이 정할 수 있는 것이 아니다. "
             "그 결정 «전»에는 §5-2 의 세 갈래 중 **어디로도 가지 않는다**:")
        both("")
        both("- 🔴 **「충족 후보 0 ⇒ 앵커 기반 축 전면 폐기 상신」으로 읽지 «않는다»** — "
             "독법 A 에서는 조건 ③ 를 충족하는 후보가 "
             f"**{sum(1 for c in ADOPTABLE if r_beats.get(c) == 0)}개** 있다.")
        both("- 🔴 **「보류」라고도 «선언하지 않는다»** — 「보류」는 독법 B 를 «고른» 뒤에야 "
             "할 수 있는 말이고, 고르는 것 자체가 이 신고의 대상이다.")
        both("- 🔑 ***값을 보고 독법을 고르면 그게 사후적합이다.***")
        both("")

    if not p3_gate_ok:
        _p3_conflict_report()

    if n1_fire or n4_fire or n5_fail or ident_fail:
        reasons = []
        if ident_fail:
            reasons.append("항등 대조 실패(산출물 무효)")
        if n1_fire:
            reasons.append("`ANC-N1` 발동(판별력 없음)")
        if n4_fire:
            reasons.append("`ANC-N4` 발동(갈래에서 갈린다)")
        if n5_fail:
            reasons.append("`ANC-N5` 실패(대조군 상수 · 절차 무효)")
        both(f"⇒ 🔴🔴 **어느 채택도 선언하지 않는다** — {' · '.join(reasons)}(§6).")
        if not p3_gate_ok:
            both("🔴 **그리고 조건 ③ 는 위 «충돌 신고»대로 두 독법이 상반돼 있다** — "
                 "🔒 사장님 결정 전에는 §5-2 의 세 갈래 중 어디로도 가지 않는다. "
                 "특히 **「충족 후보 0 ⇒ 전면 폐기 상신」으로도, 「보류」로도 읽지 않는다.**")
    elif not p3_gate_ok:
        both("⇒ 🔴🔴 **조건 ③ 는 «두 독법»이 상반된다"
             " — «어느 쪽도 선언하지 않는다».** 위 «충돌 신고» 참조 "
             "(🔒 사장님 결정 항목).")
    elif len(adopted) == 1:
        both(f"⇒ 🟢 **채택: `{adopted[0]}`** (§5-2 — 충족 후보가 **정확히 1**).")
        both("🔴 **`BUY-L5` 재개 조항은 🔒 결정 ④로 «소멸»**했다(PD-13 1번) — "
             "`HDR-` `h` 축 · `LAD-` `DD` 축만 이 앵커로 다시 선다.")
    elif len(adopted) >= 2:
        both(f"⇒ 🔴 **채택하지 않는다 — 다음 글로 미룬다** (충족 후보 {len(adopted)}개: "
             f"{', '.join(adopted)}). 🔑 ***둘 중 하나를 값을 보고 고르면 그게 사후적합이다***(§5-2).")
    else:
        both("⇒ 🔴🔴 **충족 후보 0** — §5-2 대로 **앵커 기반 축 전면 폐기**를 사장님께 올린다"
             "(`HDR-D1`·`HDR-D2`·`LAD-T1`·`LAD-P2` 종결). "
             "🔴 `BUY-L5` 는 이미 🔒 결정 ④로 **소멸**해 이 목록에 없다.")
    both("")

    # ═══ §8 한계 ══════════════════════════════════════════════════════════
    both("## §8. 미리 적어둔 한계 (§13 · 동결 문언)\n")
    for s in LIMITS:
        both(f"- {s}")
    both("")
    both("- 🔴 이 분석은 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2). "
         "*등급이 「성립」이어도 라이브 채택 금지는 그대로다.*")
    both("")

    (BASE / "RESULTS_ANCHOR_POST7_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    (BASE / "RESULTS_ANCHOR_POST7.md").write_text("\n".join(DOC) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    note("")
    note(f"[written] RESULTS_ANCHOR_POST7_NUMBERS.md + RESULTS_ANCHOR_POST7.md · "
         f"런타임 {time.time() - t0:.3f}s")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())

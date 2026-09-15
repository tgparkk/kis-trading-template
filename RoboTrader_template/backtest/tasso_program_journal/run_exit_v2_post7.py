# -*- coding: utf-8 -*-
"""`PREREG_EXIT_V2.md` §3 + `PREREG_POST6.md` §2-3(X5~X9 재동결) 실행 — 7번째 글.

`run_exit_v2_post6.py` 승계. 라벨·완결 여부·시퀀스는 **계산 «전»에** 동결된
`LABELS_2026-09-15_post7.md` · `INTAKE_2026-09-15_post7.md` §1 에서 «그대로» 옮긴다
(`TP` 7 · `SL` 2 · `MIX` 1 · `MANUAL` 2 · 🔴 `unknown` **1**). 「손실률」로 적힌 레그는
저자 낱말 그대로 `loss_mask` 에 표시한다(`EXIT-X2` 가 이걸 쓴다).

🔴 **통계 핵과 표기 함수는 `run_exit_v2_post6.py` 에서 «그대로» import 한다**(새 코드 0줄 원칙) —
   `EPS`·`E1_MIN`·`E2_MIN`·`BE_MAX`·`nonincreasing`·`eps_pairs`·`num`·`seq`·`x2_leg`·`x6_legs`·`ratio`.
   `x6_legs` 는 post6 의 열 인덱스(LEGS=2 · OPEN_N=4 · TILDE=5)를 쓰므로 이 파일의 `TRADES`
   튜플은 **앞 9열을 post6 과 같은 순서로** 둔다(10번째 `PRESET` 만 뒤에 덧붙였다).
   ⇒ post6 스크립트는 **한 글자도 고치지 않는다**.

DB 를 읽지 않는다(저자 서술만) ⇒ 결정적이고 DB 스냅샷에 의존하지 않는다.
시드 불필요. 라이브 트리 import 0건.

🔴 **이번 회차에 «처음» 구속하는 것 세 가지**:
  1. **`unknown` 라벨**(한국화장품제조 · `안정형/HDR60` 이라 `TP` 첫 조건 미충족 · PD-7) —
     **어느 `EXIT-` 규칙에도 넣지 않는다**(`PREREG_EXIT_V2.md` §4 *「`unknown` 을 `TP` 로 접지 말 것」*).
     `TP` 갈래는 **의무 민감도**로 병기한다(🔒 관리자 결정 대기).
  2. **`EXIT-E1` 누적을 두 계열로 인쇄**(`PREREG_EXIT_V2.md` §3 의 2026-09-10 문언 정비 B-4 —
     *「post6 판정 불변 · **post7 부터 구속한다**」*): **(가) 전 레그 계열** / **(나) `EXIT-X6` 적용 계열**.
     두 줄이 90% 문턱을 사이에 두고 갈리면 ⛔ **「누적 정의 의존」**.
  3. **`~` 와 서술이 불일치하는 첫 사례**(한전기술 · PD-5 1번) — 주 판정은 **서술 기준(완결)** ·
     `~` 기준은 민감도 · 그 레그만 `leg_open_ended = 1`.
     🔴 **`~` 정규식 함정**: 본문 `~` 2곳 중 하나가 서산의 프리셋 이름 `Q2~MAX` 다(PD-5 2번).

🔴 이 산출물은 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2).
🔴 이 스크립트는 **새 예측을 만들지 않는다**(`PREREG_POST6.md` §7-B #11).
"""
from __future__ import annotations

import sys
from pathlib import Path

# 🔴 동결 스크립트에서 상수·통계 핵·표기 함수를 그대로 가져온다(수정 금지 파일).
from run_exit_v2_post6 import (  # noqa: F401
    BE_MAX,           # 1.0 — §3 E2 본전 매도 레그의 |ret| < 1.0%
    E1_MIN,           # 0.90 — §3 E1 / `EXIT-X5`
    E2_MIN,           # 0.80 — §3 E2 / `EXIT-X2`
    EPS,              # 0.05 %p — §2 허용 오차(동결분 · 고치지 않는다)
    eps_pairs,        # run_exit_v2_post6.py:89
    nonincreasing,    # run_exit_v2_post6.py:84
    num,              # run_exit_v2_post6.py:94
    ratio,            # run_exit_v2_post6.py:119
    seq,              # run_exit_v2_post6.py:99
    x2_leg,           # run_exit_v2_post6.py:105
    x6_legs,          # run_exit_v2_post6.py:114
)

BASE = Path(__file__).resolve().parent
OUT: list = []

# 🔴 `EXIT-X2` 의 최소 n — `PREREG_POST6.md` §4 표 **#16** 의 **고유 조항**이다:
#    *「최소 n = **완결 `TP` 3** · ⛔ 조건 = 완결 `TP` < 3」*(`PREREG_POST6.md:807`).
#    ⚠️ **#15 는 `EXIT-E2` 의 최소 n 3 이고 «다른 행»이다** — 두 행을 섞어 인용하지 않는다.
#    이 파일이 만든 문턱이 «아니고», n < 3 인 갈래에 ✅·❌ 를 찍으면 그것이
#    「통과/불통과」로 인용된다 ⇒ ⛔ 로 찍는다.
X2_MIN_N = 3

# 🔴 창 종료 규약 — 이 레인은 DB 를 읽지 않으므로 «표기 의무»로만 쓴다(PD-1 5번 · §7-B #13).
DB_UPTO = "2026-09-11"
PUB_DATE = "2026-09-12"          # 발행 2026-09-12(토) = 휴장 ⇒ B-1 로 창은 직전 거래일에서 끝난다

# 동결 인용값 — 4·5·6번째 글 (`RESULTS_EXIT_V2_POST{4,5,6}_NUMBERS.md` · **재계산 아님**)
POST4 = {"E1_ok": 4, "E1_n": 4, "E4_ok": 3, "E4_n": 3, "E2_ok": 2, "E2_n": 3}
POST5 = {"E1_ok": 6, "E1_n": 6, "E4_ok": 4, "E4_n": 4, "E2_ok": 2, "E2_n": 3,
         "X2_ok": 2, "X2_n": 2, "X8": 0, "X8_n": 2, "X9": 0}
# 🆕 post6 은 `EXIT-X6` 을 «처음» 적용한 글이라 (가)·(나) 두 값이 «다르다»(B-4 가 가리키는 그 자리).
POST6 = {"E1_ok": 8, "E1_n": 8,          # (나) `EXIT-X6` 적용 계열 — 동결 §누적 표
         "E1a_ok": 9, "E1a_n": 9,        # (가) 전 레그 계열 — 동결 §미완결 처리 민감도 표
         "E4_ok": 5, "E4_n": 5,
         "E2a_ok": 1, "E2a_n": 4, "E2b_ok": 1, "E2b_n": 2,
         "X2_ok": 1, "X2_n": 6, "X8": 0, "X8_n": 6, "X9": 0,
         "E3_SEQ": 1}                    # `SL` 시퀀스 누적(한라캐스트 1건)

# ── 표본 (계산 «전» 동결분 그대로 · `INTAKE_2026-09-15_post7.md` §1 · `LABELS_2026-09-15_post7.md`) ──
# (종목, 라벨, 레그, 「손실률」마스크, 서술기준 미완결, `~` 문자, breakeven_note, 신규, 범위만, 프리셋)
# 🔴 앞 9열은 post6 과 «같은 순서»다 — import 한 `x6_legs`·`x2_leg` 가 그 인덱스를 쓴다.
TRADES = [
    # 🔁 후속 3건 — `PREDECISION_2026-09-15_post7.md` PD-2 (등록일 축 분모 «밖» · 라벨은 부여)
    ("한라캐스트 🔁후속",   "MIX",    [11.22, 3.50, 3.43, 3.30, 2.04, -5.30],
     [0, 0, 0, 0, 0, 1],  False, False, True,  False, False, "HDR60/표준형"),
    ("아난티 🔁후속",       "MANUAL", [1.91],
     [0],                 False, False, True,  False, False, "HDR60/표준형"),
    ("우리기술투자 🔁후속", "MANUAL", [3.28, 3.25, 3.08],
     [0, 0, 0],           False, False, True,  False, False, "HDR60/표준형"),
    # 신규 10건
    ("한전기술",            "SL",     [13.61, 10.80, 7.37, 4.91, 3.34, -1.70],
     [0, 0, 0, 0, 0, 1],  False, True,  False, True,  False, "HDR60/표준형"),
    ("한전산업",            "SL",     [15.55, 14.88, 12.70, 8.97, 5.78, -1.32],
     [0, 0, 0, 0, 0, 1],  False, False, False, True,  False, "HDR60/표준형"),
    ("지투파워 🔂재진입",   "TP",     [20.11, 18.58, 17.50, 15.08, 12.72],
     [0] * 5,             False, False, False, True,  False, "HDR60/표준형"),
    ("서산",                "TP",     [22.16, 16.09, 10.02],
     [0, 0, 0],           False, False, False, True,  False, "Q2~MAX/표준형"),
    ("강동씨엔앨",          "TP",     [24.28, 18.33, 18.31, 12.61],
     [0] * 4,             False, False, False, True,  False, "HDR60/표준형"),
    ("로보티즈",            "TP",     [9.13],
     [0],                 True,  False, False, True,  False, "HDR60/표준형"),
    ("해치텍",              "TP",     [4.06, 0.46],
     [0, 0],              False, False, True,  True,  False, "HDR60/표준형"),
    ("빛과전자 🔂재진입",   "TP",     [12.17],
     [0],                 True,  False, False, True,  False, "HDR60/표준형"),
    ("한국화장품제조 🔂재진입", "unknown", [22.70, 16.81, 10.85],
     [0, 0, 0],           False, False, False, True,  False, "HDR60/안정형"),
    ("범한퓨얼셀",          "TP",     [18.89, 16.69, 14.55, 12.22, 10.8, 7.94],
     [0] * 6,             True,  False, False, True,  False, "HDR60/표준형"),
]

NAME, LABEL, LEGS, LOSSM, OPEN_N, TILDE, BE, NEW, RANGE, PRESET = range(10)

# post6 시퀀스 — 연결 시퀀스 「기록만」 한 줄용 (PD-2 4번). 판정에 쓰지 않는다.
POST6_SEQ = {"한라캐스트 🔁후속": [5.82, 5.72, -2.87, -2.89],
             "아난티 🔁후속": [10.16],
             "우리기술투자 🔁후속": [16.48, 13.80, 13.63, 10.19, 6.50]}

# 🔴 `leg_open_ended` — 레그 «단위» 표기(PD-5 1번 · post5 원장 관용 승계). 건 단위 미완결이 아니다.
LEG_OPEN_ENDED = {"한전기술": -1.70}

# 🔴 `~` 정규식 함정(PD-5 2번 · PD-10 5번) — 기계로 세면 서산이 미완결로 «오분류»된다.
TILDE_TRAP = "서산의 프리셋 이름 `Q2~MAX`"


def say(s=""):
    print(s)
    OUT.append(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def eff_label(t, as_tp=False):
    """`unknown` 갈래 전환 — 주 판정은 동결 라벨 그대로, **민감도 갈래에서만** `TP` 로 읽는다.

    근거: `PREDECISION_2026-09-15_post7.md` PD-7 5번(🔒 관리자 결정 대기 · 두 갈래 값을 둘 다 인쇄).
    🔴 이 함수는 «판정»을 바꾸지 않는다 — `as_tp=True` 는 민감도 표에서만 호출한다.
    """
    if as_tp and t[LABEL] == "unknown":
        return "TP"
    return t[LABEL]


def denoms(as_tp=False):
    """갈래별 분모 — 주 판정(`unknown`) ↔ 민감도(`TP`).

    동결 문언이 지시하는 분모를 «정의로» 만든다(값을 보고 고르지 않는다):
      · `EXIT-E1`  = 신규 ∧ `TP` ∧ (`EXIT-X6` 적용 후 레그 >= 1)
      · `EXIT-E4`  = 신규 ∧ `TP` ∧ (`EXIT-X6` 적용 후 레그 >= 3)
      · `EXIT-X2`  = 신규 ∧ `TP` ∧ 완결(서술 기준)
      · 생략 편향 = 신규 ∧ `TP` 중 미완결 건 / `TP` 분모
    """
    tp_new = [t for t in TRADES if t[NEW] and eff_label(t, as_tp) == "TP"]
    e1 = [t for t in tp_new if x6_legs(t, "narr")]
    e4 = [t for t in tp_new if len(x6_legs(t, "narr")) >= 3]
    x2 = [t for t in tp_new if not t[OPEN_N]]
    return dict(tp_new=tp_new, e1=e1, e4=e4, x2=x2,
                tp_n=len(tp_new), e1_n=len(e1), e4_n=len(e4), x2_n=len(x2),
                om=sum(1 for t in tp_new if t[OPEN_N]))


def e1_series(post7_ok, post7_n, series):
    """`EXIT-E1` 누적 — B-4 가 요구하는 **두 계열**을 따로 잇는다.

    series='ga' (가) 전 레그 계열(post4·post5 잣대 · post6 도 (가) 갈래값 9/9)
    series='na' (나) `EXIT-X6` 적용 계열(post6 이후 잣대 · post6 8/8)
    """
    if series == "ga":
        ok = POST4["E1_ok"] + POST5["E1_ok"] + POST6["E1a_ok"] + post7_ok
        n = POST4["E1_n"] + POST5["E1_n"] + POST6["E1a_n"] + post7_n
    else:
        ok = POST4["E1_ok"] + POST5["E1_ok"] + POST6["E1_ok"] + post7_ok
        n = POST4["E1_n"] + POST5["E1_n"] + POST6["E1_n"] + post7_n
    return ok, n


def main():  # noqa: C901
    D = denoms(False)          # 주 판정 — `unknown` 은 제외
    DT = denoms(True)          # 의무 민감도 — `unknown` 을 `TP` 로 접은 갈래
    tp_new, new = D["tp_new"], [t for t in TRADES if t[NEW]]
    foll = [t for t in TRADES if not t[NEW]]

    say("# RESULTS_EXIT_V2_POST7_NUMBERS — 기계 생성 (수정 금지)")
    say("")
    say("사전등록 `PREREG_EXIT_V2.md` §3 + `PREREG_POST6.md` §2-3(`EXIT-X5`~`X9` 재동결) · "
        "라벨 `LABELS_2026-09-15_post7.md` · 결정 `PREDECISION_2026-09-15_post7.md` · "
        "시퀀스 `INTAKE_2026-09-15_post7.md` §1 · 생성 `run_exit_v2_post7.py` · "
        "재사용 `run_exit_v2_post6.py`(`nonincreasing`·`eps_pairs`·`x2_leg`·`x6_legs`·`num`·`seq`·`ratio`)")
    say("허용 오차 ε = %g%%p(동결분 · 고치지 않는다) · 문턱 `EXIT-E1`/`X5` ≥ %.0f%% · "
        "`EXIT-E2`/`X2` ≥ %.0f%% · 본전 |ret| < %.1f%%"
        % (EPS, 100 * E1_MIN, 100 * E2_MIN, BE_MAX))
    say("")
    say("## §0. 환경 · 동결 규약")
    say("")
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| 🔴 창 종료 | **%s = 발행일 %s(토) 휴장 ⇒ 마지막 거래일 · B-1**(`WRC-` 포함 전 축 · PD-1) |"
        % (DB_UPTO, PUB_DATE))
    say("| 실행 시 `max(date)` · 그 날짜 행수 | **DB 조회 0회** — 이 레인은 저자 서술만 읽는다 ⇒ "
        "`max(date)` 실측은 DB 를 읽는 레인(`run_selection_post7.py`·`run_reconstruct_post7.py` 등)의 "
        "산출물에 박힌다. **이 산출물은 그 스냅샷에 의존하지 않는다**(§7-B #13 표기 의무 이행) |")
    say("| DB | **조회 0회** · 시드 불필요 · **결정적**(두 번 돌리면 byte 동일) |")
    say("| 라벨 동결 | `TP` **7** · `SL` **2** · `MIX` **1** · `MANUAL` **2** · 🔴 `unknown` **1** — "
        "값을 보기 «전»에 정해졌다(`LABELS_2026-09-15_post7.md`) |")
    say("| 라이브 | 🔴 **라이브 채택 대상이 아니다** (`PREREG.md` §0-2) |")
    say("")
    say("> 🔴 **`unknown` 1건(한국화장품제조)은 어느 `EXIT-` 규칙에도 넣지 않는다** — "
        "동결 원문(`PREREG_EXIT_V2.md`:43)의 `TP` 첫 조건 *「프리셋이 **`표준형/HDR*`**」* 을 "
        "**「HDR 60%, 안정형」이 문자로 미충족**하고, §4 가 *「`unknown` 을 `TP` 로 접지 말 것」* 을 "
        "명시한다(PD-7). **`TP` 갈래는 의무 민감도로 병기**한다(🔒 관리자 결정 대기).")
    say("> 🟢 **서산(`사분위수 Q2~MAX / 표준형`)은 `TP` 다** — 첫 조건의 「형」이 **표준형**이라 "
        "post5 혜인 *「프리셋 **Q1~Q3 도 `표준형`**」* 전례가 그대로 적용된다.")
    say("> 🔴 **이 문서는 새 예측을 만들지 않는다**(`PREREG_POST6.md` §7-B #11).")
    say("> 🟢 라벨 접두는 `PREREG_POST6.md` §0-3 규약대로 **`EXIT-`** 를 붙인다.")
    say("")

    # ── 원표 ────────────────────────────────────────────────────────────
    say("## §1. 원표 — 7번째 글 13건 (신규 10 + 🔁후속 3 · 라벨은 계산 «전» 동결)")
    say("")
    say("| # | 종목 | 구분 | 프리셋 | 라벨 | 완결(서술) | `~` | `be_note` | 레그 | "
        "시퀀스(저자 순서 · †=「손실률」) | 「손실률」 | 비증가 | 위반 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for k, t in enumerate(TRADES, 1):
        v = nonincreasing(t[LEGS])
        nloss = sum(t[LOSSM])
        say("| %d | %s | %s | %s | `%s` | %s | %s | %s | %d | %s%s | %s | %s | %s |" % (
            k, t[NAME], "신규" if t[NEW] else "🔁후속", t[PRESET], t[LABEL],
            "완결" if not t[OPEN_N] else "**미완결**",
            "**예**" if t[TILDE] else "—",
            "**1**" if t[BE] else "0", len(t[LEGS]), seq(t[LEGS], t[LOSSM]),
            " **(범위만)**" if t[RANGE] else "",
            ("%d개" % nloss) if nloss else "—",
            "✅" if not v else "❌",
            "—" if not v else "; ".join("%s→%s(+%.2f%%p)" % (num(a), num(b), b - a)
                                        for _, a, b in v)))
    say("")
    say("- 라벨 집계: `TP` %d · `SL` %d · `MIX` %d · `MANUAL` %d · 🔴 `unknown` %d "
        "(신규 10 = `TP` 7 + `SL` 2 + `unknown` 1 · 🔁후속 3 = `MIX` 1 + `MANUAL` 2)"
        % tuple(sum(1 for t in TRADES if t[LABEL] == x)
                for x in ("TP", "SL", "MIX", "MANUAL", "unknown")))
    say("- 레그 합계 **%d**(신규 %d · 후속 %d) · 「손실률」 레그 **%d**"
        "(한전기술 1 · 한전산업 1 · 한라캐스트 1)"
        % (sum(len(t[LEGS]) for t in TRADES), sum(len(t[LEGS]) for t in new),
           sum(len(t[LEGS]) for t in foll), sum(sum(t[LOSSM]) for t in TRADES)))
    say("- 미완결(서술 기준) **%d건**(로보티즈 · 빛과전자 · 범한퓨얼셀) — "
        "「나머지 물량 보유 중」이 판별 낱말이다(PD-5)."
        % sum(1 for t in TRADES if t[OPEN_N]))
    say("- 🔴 **`~` 와 서술이 «충돌»하는 첫 사례**(PD-5 1번): 한전기술은 값 줄에 `~` 가 있는데 "
        "서술이 *「4차 매수된 상태로 **전량** 분할 매도처리」* 다 ⇒ **주 판정 = 서술 기준(완결)** · "
        "`~` 기준은 민감도 · `~` 가 붙은 **%s 레그만 `leg_open_ended = 1`**(레그 단위 표기)."
        % num(LEG_OPEN_ENDED["한전기술"]))
    say("- 🔴🔴 **`~` 정규식 함정**: 본문의 `~` 2곳 중 하나는 **%s** 다 — `~` 를 기계로 세면 "
        "서산이 미완결로 **오분류**된다(PD-5 2번 · 원장 게이트 비고)." % TILDE_TRAP)
    say("- 🔴 표기 오기 2건(PD-10): 한전기술 「**4,91%**」(쉼표 소수점) → **4.91** · "
        "범한퓨얼셀 「**10.8%**」(소수 1자리 · 나머지는 2자리). 한국화장품제조는 "
        "**「수익률」 낱말 없이** 값만 적었다(12/13).")
    say("- 🔴 **`EXIT-X6` 적용 범위 = `EXIT-E1`·`EXIT-E4` «뿐»**(`PREREG_POST6.md` §1-8) — "
        "`EXIT-X2`·`EXIT-X8` 의 「마지막 레그」는 저자 «원» 시퀀스 기준이다.")

    # ── EXIT-E1 / EXIT-X5 ───────────────────────────────────────────────
    say("")
    say("## §2. `EXIT-E1` · `EXIT-X5` — `TP` 신규 건의 매도 레그 시퀀스가 비증가 (문턱 ≥%.0f%%)"
        % (100 * E1_MIN))
    say("")
    say("주 판정 = **서술 기준 미완결 `TP` 3건**(로보티즈·빛과전자·범한퓨얼셀)의 "
        "**마지막 레그 하나 제외**(`EXIT-X6` · PD-5).")
    say("")
    say("| 종목 | 완결 | 원 시퀀스 | `EXIT-X6` 후 | 레그 | 비증가 | 위반 |")
    say("|---|---|---|---|---|---|---|")
    e1_ok, e1_n, e1_out = 0, 0, []
    for t in tp_new:
        L = x6_legs(t, "narr")
        if not L:
            e1_out.append(t)
            say("| %s | **미완결** | %s | **(레그 0)** | 0 | — | 🔴 **분모 밖** |"
                % (t[NAME], seq(t[LEGS])))
            continue
        v = nonincreasing(L)
        e1_n += 1
        e1_ok += (not v)
        say("| %s | %s | %s | %s | %d | %s | %s |"
            % (t[NAME], "완결" if not t[OPEN_N] else "**미완결**", seq(t[LEGS]), seq(L), len(L),
               "✅" if not v else "❌",
               "—" if not v else "; ".join("%s→%s" % (num(a), num(b)) for _, a, b in v)))
    r1 = e1_ok / e1_n
    say("")
    say("- 🔴 **분모 밖 %d건**: %s — `EXIT-X6` 적용 후 레그 0 ⇒ 「비증가」의 정의역 밖"
        "(값을 보고 뺀 것이 아니라 **정의로** 빠진다 · post6 아난티 전례)."
        % (len(e1_out), ", ".join("%s(원 레그 %d)" % (t[NAME], len(t[LEGS])) for t in e1_out)))
    say("- **`EXIT-E1` = %d/%d = %.1f%%** ⇒ **%s** (문턱 %.0f%% · 주 판정 분모 **%d**)"
        % (e1_ok, e1_n, ratio(e1_ok, e1_n),
           "✅ 지지" if r1 >= E1_MIN else "❌ 불성립", 100 * E1_MIN, e1_n))
    say("- **`EXIT-X5`**(= `RESULTS_EXIT_V2_POST5.md` §10 의 재확인 예측) = 같은 계산 ⇒ **%s**"
        % ("✅ 적중" if r1 >= E1_MIN else "❌ 빗나감"))

    # 라벨 무관 확인
    withlegs = [t for t in TRADES if t[LEGS]]
    allv = [t for t in withlegs if nonincreasing(t[LEGS])]
    say("- 🔎 **라벨 제외 «전» %d건 전체**(원 시퀀스 · 후속·`SL`·`MIX`·`MANUAL`·`unknown` 포함): "
        "위반 **%d건** ⇒ 라벨 결정이 `EXIT-E1` 판정을 **%s**."
        % (len(withlegs), len(allv),
           "만들지 않았다" if len(allv) == e1_n - e1_ok else
           "만들 수 있는 자리가 있다 — 아래 갈래 표를 같이 읽을 것"))

    # ε
    used = [(t[NAME], a, b) for t in withlegs for a, b in eps_pairs(t[LEGS])]
    ties = [(t[NAME], a) for t in withlegs for a, b in zip(t[LEGS], t[LEGS][1:]) if a == b]
    drops = sorted(a - b for t in withlegs for a, b in zip(t[LEGS], t[LEGS][1:]) if a > b)
    say("- **ε 사용 건수 = %d회**(0 < 증가 ≤ %g%%p 인 쌍) — %s. 동률 %d쌍. "
        "**최소 하락 간격 = 강동씨엔앨 18.33 → 18.31 = %.2f%%p**"
        "(수익률 레그 한정에서도 같은 값) — **하락이라 ε 이 걸리지 않는다**(ε 은 증가에만 적용)."
        % (len(used), EPS, "ε 를 넉넉히 잡아서 통과한 게 아니다" if not used else "🔴 ε 에 기댄 통과가 있다",
           len(ties), drops[0] if drops else float("nan")))
    say("- ⇒ **ε 은 4글 연속 사용 0회**(post4 0 · post5 0 · post6 0 · post7 %d). "
        "`PREREG_EXIT_V2.md` §4 의 한계(*「이 대역이 안 맞으면 ε 을 고치지 말고 그대로 판정」*)는 "
        "**아직 시험된 적이 없다**(INTAKE §2-17 이 계산 «전»에 예고한 그대로)." % len(used))

    # 미완결 처리 3갈래 + `~` 기준 민감도
    say("")
    say("### §2-1. 미완결 처리 민감도 — (가)(나)(다) 병기(`EXIT-X6` #17 의무) + `~` 문자 기준(PD-5)")
    say("")
    say("| 처리 | 대상 `TP` 신규 | 비증가 | 비율 | 비고 |")
    say("|---|---|---|---|---|")
    a_ok = sum(1 for t in tp_new if not nonincreasing(t[LEGS]))
    say("| (가) 전 레그 포함 | %d | %d | %.1f%% | **민감도** · post4·post5 가 실제로 쓴 처리 |"
        % (len(tp_new), a_ok, ratio(a_ok, len(tp_new))))
    say("| (나) 미완결 건의 **마지막 레그만** 제거 = **서술 기준** | %d | %d | %.1f%% | "
        "🟢 **주 판정값**(PD-5 · 로보티즈·빛과전자는 레그 0 ⇒ 분모 밖) |"
        % (e1_n, e1_ok, ratio(e1_ok, e1_n)))
    comp = [t for t in tp_new if not t[OPEN_N]]
    c_ok = sum(1 for t in comp if not nonincreasing(t[LEGS]))
    say("| (다) 미완결 건을 **통째 제외** | %d | %d | %.1f%% | 민감도 · n=%d %s 3 |"
        % (len(comp), c_ok, ratio(c_ok, len(comp)), len(comp), "≥" if len(comp) >= 3 else "<"))
    t_ok = sum(1 for t in tp_new if not nonincreasing(x6_legs(t, "tilde")))
    say("| (`~` 문자 기준) `EXIT-X6` 을 `~` 로만 적용 | %d | %d | %.1f%% | "
        "민감도(PD-5) · 🔴 `TP` 분모 안 `~` 건은 **0** — `~` 는 한전기술(`SL`)에만 있다 |"
        % (len(tp_new), t_ok, ratio(t_ok, len(tp_new))))
    say("")
    verdicts = {ratio(a_ok, len(tp_new)) / 100 >= E1_MIN,
                r1 >= E1_MIN,
                (c_ok / len(comp) >= E1_MIN) if comp else r1 >= E1_MIN,
                (t_ok / len(tp_new)) >= E1_MIN}
    say("- ⇒ 네 처리가 **%s** ⇒ 판정이 처리 선택에 **%s**."
        % ("모두 같은 판정" if len(verdicts) == 1 else "서로 다른 판정",
           "의존하지 않는다" if len(verdicts) == 1 else "🔴 **의존한다 — 「표기 의존」으로 적는다**"))
    say("- 🔴 **`~` 문자 기준 vs 서술 기준**: 두 기준이 판정을 **%s** ⇒ %s. "
        "🔑 이번 글은 `~` 가 **`SL` 건(한전기술)에만** 있어 `TP` 분모에서는 두 기준이 "
        "**구성상 같은 답**을 낸다 — *「충돌은 있었지만 판정을 가르는 자리에는 없었다」*."
        % ("가르지 않는다" if len(verdicts) == 1 else "가른다",
           "「표기 의존」 조항(PD-5) **미발동**" if len(verdicts) == 1 else "🔴 「표기 의존」"))
    say("- ⚠️ 레그 **1개**인 건은 비증가를 **구조적으로 자동 만족**한다(쌍이 없다). "
        "(가) 갈래의 로보티즈·빛과전자가 그 경우다 — `EXIT-E4` 가 이 자동 통과분을 걷어낸다.")

    # 생략 편향
    om_tp, om_all = D["om"], sum(1 for t in new if t[OPEN_N])
    say("")
    say("### §2-2. 생략 편향 비율 — 의무 인쇄(`PREREG_POST6.md` §2-3)")
    say("")
    say("- **계열 연속값(`TP` 분모 · 주 판정)**: post4 **2/4 = 50.0%%** → post5 **4/6 = 66.7%%** → "
        "post6 **3/9 = 33.3%%** → **post7 %d/%d = %.1f%%**"
        % (om_tp, D["tp_n"], ratio(om_tp, D["tp_n"])))
    say("- 🔴 **`TP` 갈래 병기**(한국화장품제조 포함): **%d/%d = %.1f%%**"
        % (DT["om"], DT["tp_n"], ratio(DT["om"], DT["tp_n"])))
    say("- 병기(신규 10건 분모): **%d/%d = %.1f%%**" % (om_all, len(new), ratio(om_all, len(new))))
    say("- 동결 문언: *「생략분은 대개 뒤쪽(낮은 수익률)이라 「비증가」에 «유리한» 방향으로 편향된다」*"
        "(`RESULTS_EXIT_V2_POST5.md` §9-4). ⇒ **`EXIT-E1` 의 비율을 액면대로 읽지 말 것.**")
    say("- 🔴 **`EXIT-X5` 문언의 조건부 조항**: *「위반 1건이 곧 첫 반례 … 반례가 나오면 "
        "«생략 편향이 만든 100%%» 가설로 먼저 의심한다」*. 이번 글 위반 **%d건** ⇒ 이 조항은 **%s**."
        % (e1_n - e1_ok, "미발동" if e1_ok == e1_n else "🔴 **발동 — 생략 편향 가설을 먼저 검토한다**"))

    # ── 갈래별 분모 표 (unknown ↔ TP) ───────────────────────────────────
    say("")
    say("## §3. 🔴🔴 `unknown` 갈래별 분모 — **의무 병기**(PD-7 2번 · 🔒 관리자 결정 대기)")
    say("")
    say("| 갈래 | `EXIT-E1` 분모 | `EXIT-E4` | `EXIT-X2` 주 분모 | 생략 편향 |")
    say("|---|---|---|---|---|")
    say("| **주 판정 `unknown`**(한국화장품제조 제외) | **%d** | **%d** | **%d** | **%d/%d** |"
        % (D["e1_n"], D["e4_n"], D["x2_n"], D["om"], D["tp_n"]))
    say("| 민감도 `TP`(한국화장품제조 포함) | %d | %d | %d | %d/%d |"
        % (DT["e1_n"], DT["e4_n"], DT["x2_n"], DT["om"], DT["tp_n"]))
    say("")
    say("🔴 **방향 자기신고 — 이 건의 방향은 «혼합»이다**(PD-7 2번 축자 승계):")
    say("")
    say("- 이 건의 시퀀스(22.70 · 16.81 · 10.85)는 **비증가**이고 **완결 · 레그 3** 이라 "
        "`TP` 로 접으면 **`EXIT-E1`·`EXIT-E4` 에 «유리»** 하다.")
    say("- 🔴 **그러나 `EXIT-X2` 에는 «반대»다** — `EXIT-X2` 가 고르는 레그(「손실률」 제외 후 마지막)가 "
        "**10.85** 라 `|ret| < %.1f%%` 를 **못 넘는 건**이 하나 느는 쪽이다." % BE_MAX)
    say("- ⇒ **주 판정 `unknown` = `EXIT-E1`·`EXIT-E4` 에 «불리» · `EXIT-X2` 에 «유리»**. "
        "어느 한쪽으로 유리하게 고른 것이 아니라 **동결 문언이 지시한 대로 둔 결과**이며, "
        "🔑 한 방향으로만 적으면 유리한 자리를 숨기게 되므로 **둘 다** 적는다.")
    say("- 🔴 **`unknown` 건은 라벨을 쓰지 «않는» 축**(`SEL-`·`REG-`·`Q1-`·`LAD-`·`REC-`·`ANC-`·"
        "`RNK-`·`SEC-`·`WRC-`)**에서는 그대로 남는다** — 그 건은 어차피 `approx` 라 등록일 축에서는 "
        "민감도 갈래다(PD-4 · PD-7 3번).")

    # ── EXIT-E4 ─────────────────────────────────────────────────────────
    say("")
    say("## §4. `EXIT-E4` (반증축) — `TP` ∧ 레그 ≥3 (`EXIT-X6` 적용 후)만으로 재계산")
    say("")
    say("`PREREG_EXIT_V2.md` §3 의 우려: *「레그 2개짜리는 비증가를 거의 자동으로 만족한다」*.")
    say("")
    say("| 종목 | `EXIT-X6` 후 레그 | 시퀀스 | 비증가 |")
    say("|---|---|---|---|")
    e4 = []
    for t in D["e4"]:
        L = x6_legs(t, "narr")
        e4.append((t, L))
        say("| %s | %d | %s | %s |"
            % (t[NAME], len(L), seq(L), "✅" if not nonincreasing(L) else "❌"))
    e4_ok = sum(1 for _, L in e4 if not nonincreasing(L))
    e4_n = len(e4)
    r4 = e4_ok / e4_n
    say("")
    say("| 대상 | 건수 | 비증가 | 비율 |")
    say("|---|---|---|---|")
    say("| `TP` 신규 전체(`EXIT-X6` 후 · 분모 밖 제외) | %d | %d | %.1f%% |"
        % (e1_n, e1_ok, ratio(e1_ok, e1_n)))
    say("| `TP` ∩ 레그 ≥3 | %d | %d | %.1f%% |" % (e4_n, e4_ok, ratio(e4_ok, e4_n)))
    say("")
    say("- 제외된 건: %s"
        % (", ".join("%s(`EXIT-X6` 후 레그 %d)" % (t[NAME], len(x6_legs(t, "narr")))
                     for t in tp_new if 0 < len(x6_legs(t, "narr")) < 3) or "없음"))
    say("- ⇒ **%s** — 두 비율이 %s(%.1f%% vs %.1f%%)."
        % ("✅ 통과 — 레그 수가 만든 결과가 아니다" if r4 == r1 else "🔴 레그 수에 의존한다",
           "같다" if r4 == r1 else "다르다", ratio(e1_ok, e1_n), ratio(e4_ok, e4_n)))

    # ── EXIT-E2 · EXIT-X2 병기 ──────────────────────────────────────────
    say("")
    say("## §5. `EXIT-E2`(병기 · 판정 아님) · `EXIT-X2`(주 판정) — 같은 표에 인쇄 (§7-C 3 의무)")
    say("")
    say("🔴 **분모 충돌 신고**(`PREREG_POST6.md` §1-8 형식) — **두 동결 문언이 서로 다른 분모를 지시한다**:")
    say("")
    say("| 항목 | 동결 분모 | 동결 출처 | 이번 글 |")
    say("|---|---|---|---|")
    be_all = [t for t in TRADES if t[BE]]
    be_new = [t for t in be_all if t[NEW]]
    x2t = D["x2"]
    say("| `EXIT-E2` | 저자가 **본전 매도**라 적은 레그(`breakeven_note`) · **라벨·등록 사건 무관** | "
        "`PREREG_EXIT_V2.md` §3 + `PREREG_POST6.md` §1-1 | **%d건**(후속 포함 · 누적 계열) / 신규만 %d |"
        % (len(be_all), len(be_new)))
    say("| `EXIT-X2` | **신규 완결 `TP`** 건 | `PREREG_POST6.md` §2-3·§7-C 4 + "
        "`LABELS_2026-08-29_post5.md` X2 절 | **%d건** |" % len(x2t))
    say("")
    say("- **정의를 어느 쪽으로도 «고치지 않는다».** 둘 다 그대로 인쇄한다(병기 의무).")
    say("")
    say("### §5-1. 병기 표 — 두 규칙이 각 건에서 «어느 레그»를 고르나")
    say("")
    say("| 종목 | 구분 | 라벨 | 완결 | `be_note` | 시퀀스 | `EXIT-E2`(원 시퀀스 마지막) | "
        "`EXIT-X2`(「손실률」 제외 후 마지막) | 두 규칙이 다른가 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for t in TRADES:
        if not (t in be_all or t in x2t):
            continue
        last = t[LEGS][-1]
        xv, xp = x2_leg(t[LEGS], t[LOSSM])
        say("| %s | %s | `%s` | %s | %s | %s | **%s**%s | **%s**%s | %s |"
            % (t[NAME], "신규" if t[NEW] else "🔁후속", t[LABEL],
               "완결" if not t[OPEN_N] else "**미완결**", "1" if t[BE] else "0",
               seq(t[LEGS], t[LOSSM]),
               num(last), " (%s)" % ("✅" if abs(last) < BE_MAX else "❌"),
               num(xv), " (%s)" % ("✅" if abs(xv) < BE_MAX else "❌"),
               "**예**" if xv != last else "아니오"))
    say("")

    # E2 판정 — 두 분모 + 누적
    say("### §5-2. `EXIT-E2` — 원 동결 규칙(마지막 레그) · **병기 · 주 판정 아님** (문턱 ≥%.0f%%)"
        % (100 * E2_MIN))
    say("")
    e2a_ok = sum(1 for t in be_all if abs(t[LEGS][-1]) < BE_MAX)
    e2b_ok = sum(1 for t in be_new if abs(t[LEGS][-1]) < BE_MAX)
    cum_e2a = (POST4["E2_ok"] + POST5["E2_ok"] + POST6["E2a_ok"] + e2a_ok,
               POST4["E2_n"] + POST5["E2_n"] + POST6["E2a_n"] + len(be_all))
    say("| 분모 | 건 | `\\|ret\\| < %.1f%%` | 비율 | 판정 |" % BE_MAX)
    say("|---|---|---|---|---|")
    say("| **(주 계열) `breakeven_note` 전건 — 🔁후속 «포함»** | %d | %d | **%.1f%%** | %s |"
        % (len(be_all), e2a_ok, ratio(e2a_ok, len(be_all)),
           "✅ 지지" if e2a_ok / len(be_all) >= E2_MIN else "❌ 불성립"))
    say("| (민감도) 신규만 | %d | %d | %.1f%% | 🔴 **⛔ 신규 단독 판정 불가**"
        "(최소 n 3 · %d < 3 — `PREREG_POST6.md` §4 #15) · 인쇄만 |"
        % (len(be_new), e2b_ok, ratio(e2b_ok, len(be_new)), len(be_new)))
    say("")
    say("- 🔴 **`EXIT-E2` 최소 n = 3**(§4 #15) ⇒ **신규만 갈래 %d < 3 이라 신규 단독 판정 ⛔** · "
        "**누적 %d 로 판정**한다(post6 누적 %d + 이번 %d)."
        % (len(be_new), cum_e2a[1], POST4["E2_n"] + POST5["E2_n"] + POST6["E2a_n"], len(be_all)))
    say("- `breakeven_note` **%d건** = 한라캐스트 · 아난티 · 우리기술투자 · 해치텍 "
        "(🔴 신규 완결 `TP` 중 note 건은 **해치텍 1건뿐**이다)." % len(be_all))
    say("- 🔴 **방향 자기신고**: 후속 3건의 `EXIT-E2` 레그는 **%s · %s · %s** 다 ⇒ "
        "후속 «제외»가 `EXIT-E2` 에 유리한지는 값으로 갈린다 — **그래서 누적 계열은 포함(%d)으로 잇고 "
        "제외(%d)는 민감도로만 인쇄**한다(동결 문언 §1-1 이 「라벨·등록 사건 무관」이라 적었다)."
        % (num(foll[0][LEGS][-1]), num(foll[1][LEGS][-1]), num(foll[2][LEGS][-1]),
           len(be_all), len(be_new)))

    # X2 판정
    say("")
    say("### §5-3. `EXIT-X2` — **주 판정**(「손실률」 레그 제외 후 «원 시퀀스» 마지막) · "
        "신규 완결 `TP` (문턱 ≥%.0f%%)" % (100 * E2_MIN))
    say("")
    say("| 종목 | 시퀀스 | 「손실률」 제외 후 | `EXIT-X2` 레그 | 뒤에서 | `\\|ret\\|` | 판정 |")
    say("|---|---|---|---|---|---|---|")
    x2_ok, x2pos = 0, []
    for t in x2t:
        kept = [v for v, m in zip(t[LEGS], t[LOSSM]) if not m]
        xv, xp = x2_leg(t[LEGS], t[LOSSM])
        p = abs(xv) < BE_MAX
        x2_ok += p
        x2pos.append((t[NAME], xp, len(t[LEGS]), xv, t[LEGS][-1]))
        say("| %s | %s | %s | **%s** | %d번째 | %.2f | %s |"
            % (t[NAME], seq(t[LEGS], t[LOSSM]), seq(kept), num(xv),
               len(t[LEGS]) - xp, abs(xv), "✅" if p else "❌"))
    x2_n = len(x2t)
    r22 = x2_ok / x2_n
    say("")
    say("- **`EXIT-X2` = %d/%d = %.1f%%** ⇒ **%s** (문턱 %.0f%% · 최소 n = 완결 `TP` 3 ⇒ "
        "%d ≥ 3 이라 **보류 아님**)"
        % (x2_ok, x2_n, ratio(x2_ok, x2_n),
           "✅ 지지" if r22 >= E2_MIN else "❌ 불성립", 100 * E2_MIN, x2_n))
    say("")
    say("#### `EXIT-X2` 민감도 (의무 인쇄 · 판정에 «안» 쓴다)")
    say("")
    say("| 갈래 | 분모 | 적중 | 비율 | 판정 | 비고 |")
    say("|---|---|---|---|---|---|")
    say("| **주 판정** 신규 완결 `TP`(`unknown` 제외) | %d | %d | %.1f%% | %s | 동결 문언(§2-3·§7-C 4) |"
        % (x2_n, x2_ok, ratio(x2_ok, x2_n), "✅" if r22 >= E2_MIN else "❌"))
    st = DT["x2"]
    st_ok = sum(1 for t in st if abs(x2_leg(t[LEGS], t[LOSSM])[0]) < BE_MAX)
    say("| (민감도 `TP` 갈래) 한국화장품제조 포함 | %d | %d | %.1f%% | %s | "
        "🔴 이 갈래는 `EXIT-X2` 에 **불리**(10.85 는 `|ret| < 1%%` 미달) |"
        % (len(st), st_ok, ratio(st_ok, len(st)), "✅" if st_ok / len(st) >= E2_MIN else "❌"))
    sa = [t for t in x2t if t[BE]]
    sa_ok = sum(1 for t in sa if abs(x2_leg(t[LEGS], t[LOSSM])[0]) < BE_MAX)
    # 🔴 최소 n = **완결 `TP` 3**(`PREREG_POST6.md` §4 **#16** 고유 조항 · `:807`).
    #    ⚠️ #15(`EXIT-E2`)와 «다른 행»이다 — 수만 같고 근거 조항이 다르다.
    #    n < 3 인 갈래에 ✅·❌ 를 찍으면 **통과/불통과로 «인용»된다** ⇒ ⛔ 로 찍는다.
    sa_mark = ("⛔ (최소 n 3 · %d < 3 — 통과로 인용 금지)" % len(sa)) if len(sa) < X2_MIN_N \
        else ("✅" if sa and sa_ok / len(sa) >= E2_MIN else "❌")
    say("| (a) 좁은 분모 = 신규 완결 `TP` ∧ `be_note` | %d | %d | %.1f%% | %s | "
        "🔴 `EXIT-X2` 에 **유리한** 방향(해치텍 %s 1건) |"
        % (len(sa), sa_ok, ratio(sa_ok, len(sa)), sa_mark,
           num(x2_leg(sa[0][LEGS], sa[0][LOSSM])[0]) if sa else "—"))
    sb = x2t + foll
    sb_ok = sum(1 for t in sb if abs(x2_leg(t[LEGS], t[LOSSM])[0]) < BE_MAX)
    say("| (b) 🔁후속 포함 | %d | %d | %.1f%% | %s | "
        "🔴 **동결 적용 대상(「`TP` 완결 건」) «밖»의 확장 민감도** |"
        % (len(sb), sb_ok, ratio(sb_ok, len(sb)), "✅" if sb_ok / len(sb) >= E2_MIN else "❌"))
    say("")
    say("- 🔴 **방향 자기신고**: 좁은 분모((a) · 신규 완결 `TP` ∧ `be_note` = 해치텍 **%s** 1건)는 "
        "**`EXIT-X2` 에 «유리한» 방향**이다. **동결(넓은) 분모 %d 를 주 판정으로 쓰는 이 결정은 "
        "`EXIT-X2` 에 «불리한» 방향**이다. 좁은 분모는 민감도로 의무 인쇄했다."
        % (num(x2_leg(sa[0][LEGS], sa[0][LOSSM])[0]) if sa else "—", x2_n))
    # 🔴🔴 **「분모 의존」은 이 문서가 «처음 쓰는» 표현이고 동결본 어디에도 없다.**
    #    그래서 근거로 `PD-2 3번`·`PD-7 2번` 을 달지 않는다 — 그 두 조항은 «다른 것»을 말한다.
    #    그리고 값을 보면 «갈림»의 실체가 다르다: **최소 n(3)을 채운 세 갈래는 전부 ❌ 로 일치**하고,
    #    갈리는 것은 **n = 1 갈래 하나뿐**이다 — 그 갈래는 위 표에서 ⛔ 로 찍었다.
    br_named = [("주 판정", x2_n, r22 >= E2_MIN),
                ("민감도 `TP` 갈래", len(st), st_ok / len(st) >= E2_MIN),
                ("(a) 좁은 분모", len(sa), (sa_ok / len(sa) >= E2_MIN) if sa else None),
                ("(b) 후속 포함", len(sb), sb_ok / len(sb) >= E2_MIN)]
    enough = [(nm, n, v) for nm, n, v in br_named if n >= X2_MIN_N and v is not None]
    short = [(nm, n, v) for nm, n, v in br_named if n < X2_MIN_N]
    kinds = {v for _nm, _n, v in enough}
    say("- 🔒 **최소 n(%d)을 채운 갈래는 %d개**(%s)이고 **판정이 %s** — %s."
        % (X2_MIN_N, len(enough), ", ".join(nm for nm, _n, _v in enough),
           "전부 일치한다" if len(kinds) == 1 else "갈린다",
           ("전부 **%s**" % ("✅ 지지" if next(iter(kinds)) else "❌ 불성립"))
           if len(kinds) == 1 else "아래 갈래별 기호 참조"))
    if short:
        say("- 🔴 **갈리는 것은 최소 n 미달 갈래뿐이다** — %s. "
            "⛔ 그 갈래는 **통과로도 불통과로도 인용하지 않는다**(최소 n %d 미달 · "
            "`PREREG_POST6.md` §4 **#16** 고유 조항 — *「최소 n = 완결 `TP` 3」* · "
            "⚠️ #15(`EXIT-E2`)와 수만 같고 «다른 행»이다)."
            % (", ".join("%s(n = %d)" % (nm, n) for nm, n, _v in short), X2_MIN_N))
    say("- 🔴🔴 **자기신고 — 「분모 의존」은 «이 문서가 처음 쓰는» 표현이다.** "
        "동결본(`PREREG_EXIT_V2.md`·`PREREG_POST6.md`·`PREDECISION_2026-09-15_post7.md`) "
        "어디에도 이 라벨은 **없다**. 초판이 근거로 단 `PD-2 3번`·`PD-7 2번` 은 "
        "**다른 것을 말하는 조항**이어서 인용을 **삭제했다**. "
        "🔑 ***없는 라벨을 만들어 붙이면 다음 사람이 그것을 동결 조항으로 읽는다.***")
    if len(kinds) == 1:
        say("- 🟢 그러므로 이 회차에 쓸 수 있는 문장은 ***「최소 n 을 채운 갈래는 전부 "
            "같은 답을 냈고, 다른 답은 n = 1 갈래에서만 나왔다」*** 하나다 — "
            "**「분모를 바꾸면 결론이 바뀐다」가 아니다.**")
    say("")
    say("#### `EXIT-X2` 에서 «빠진» 건과 그 이유 (계산 «전» 동결분)")
    say("")
    say("| 종목 | 구분 | 라벨 | 완결 | 제외 사유 |")
    say("|---|---|---|---|---|")
    for t in TRADES:
        if t in x2t:
            continue
        if not t[NEW]:
            why = "🔁후속 — 동결 적용 대상은 «신규» 완결 `TP` (확장 민감도 (b) 에만 등장 · PD-2 3번)"
        elif t[LABEL] == "unknown":
            why = ("🔴 `unknown` — 판별표 **어느 행에도 해당하지 않는다**(`안정형/HDR60`) · "
                   "§4 *「`unknown` 을 `TP` 로 접지 말 것」* · `TP` 갈래는 민감도에만(PD-7)")
        elif t[LABEL] != "TP":
            why = "라벨이 `%s` — 대상은 `TP` 뿐(라벨은 계산 «전» 동결)" % t[LABEL]
        else:
            why = ("미완결(서술) — `EXIT-X2` 는 「남은 레그 중 **마지막**」을 고르는데 "
                   "**마지막 레그가 아직 안 적혔다**(`EXIT-X6` 미적용 · §1-8)")
        say("| %s | %s | `%s` | %s | %s |"
            % (t[NAME], "신규" if t[NEW] else "🔁후속", t[LABEL],
               "완결" if not t[OPEN_N] else "미완결", why))
    say("")
    say("- 🔴 **제외는 규칙의 «분자»가 아니라 «정의»에서 나온다** — 값을 보고 뺀 것이 아니다.")

    # ── EXIT-X8 ─────────────────────────────────────────────────────────
    say("")
    say("## §6. `EXIT-X8` (반증축) — `EXIT-X2` 가 고른 레그 ≠ 마지막 레그인 건 수")
    say("")
    say("| 종목 | 레그 수 | `EXIT-X2` 레그 | 뒤에서 | 「마지막 레그」 규칙 | 두 규칙이 다른가 |")
    say("|---|---|---|---|---|---|")
    x8 = 0
    for nm, pos, n, xv, last in x2pos:
        d = (xv != last)
        x8 += d
        say("| %s | %d | %s | %d번째 | %s | %s |"
            % (nm, n, num(xv), n - pos, num(last), "예" if d else "**아니오**"))
    say("")
    nloss_x2 = sum(sum(t[LOSSM]) for t in x2t)
    say("- 주 분모(%d건) 안 **%d건** — 주 분모엔 「손실률」 레그가 **%d개**라 두 규칙이 "
        "**구성상** 같은 레그를 고른다." % (x2_n, x8, nloss_x2))
    say("- ⇒ %s (`EXIT-X8` 동결 문언: *「그 수가 0 이면 여전히 「구분 불가」로 적는다」*) — "
        "**3글 연속 「구분 불가」**."
        % ("⛔ **두 규칙 구분 불가**" if x8 == 0 else "**두 규칙이 구분된다**"))
    ext = [t for t in TRADES if t not in x2t and t[LEGS]]
    x8b = sum(1 for t in ext if x2_leg(t[LEGS], t[LOSSM])[0] != t[LEGS][-1])
    say("- **민감도(확장 분모 · 후속·`SL`·`MIX`·`unknown` 포함)**: 분모 %d건 중 **%d건** — "
        "「손실률」 레그가 있는 건(한전기술·한전산업·한라캐스트)에서는 두 규칙이 **다른 레그를 고른다** "
        "⇒ **민감도에서만 「구분 가능」**이다. 그대로 인쇄한다(판정은 주 분모의 「구분 불가」)."
        % (x2_n + len(ext), x8 + x8b))
    say("- 🔴 ***`EXIT-X2` 의 「지지/불성립」은 `EXIT-X8` > 0 이 되기 전까지 「`EXIT-X2` 가 «작동»한다」의 "
        "증거가 아니다***(§7-C 3).")

    # ── EXIT-E3 / EXIT-X7 ───────────────────────────────────────────────
    say("")
    say("## §7. `EXIT-E3` · `EXIT-X7` — `SL` 건의 손절 레그 비증가 (ε 동일) · ⛔ **판정 불가**")
    say("")
    sl = [t for t in TRADES if t[LABEL] == "SL"]
    seqs = [t for t in sl if sum(t[LOSSM]) >= 2]
    say("| 종목 | 라벨 | 완결 | 전 시퀀스 | 손절(「손실률」) 레그 | 개수 | 「시퀀스」(값 2개 이상) |")
    say("|---|---|---|---|---|---|---|")
    for t in sl:
        loss = [v for v, m in zip(t[LEGS], t[LOSSM]) if m]
        say("| %s | `%s` | %s | %s | **%s** | %d | %s |"
            % (t[NAME], t[LABEL], "**미완결**" if t[OPEN_N] else "완결",
               seq(t[LEGS], t[LOSSM]), seq(loss), len(loss),
               "예" if len(loss) >= 2 else "🔴 **아니다**(값 1개)"))
    say("")
    say("- **`SL` %d건의 손실 레그가 각각 1개** ⇒ **「시퀀스」(값 2개 이상) = %d건**. "
        "`PREREG_POST6.md` §4 **#19**(최소 n = 「`SL` 시퀀스 3」) ⇒ **⛔ 판정 불가 유지**."
        % (len(sl), len(seqs)))
    say("- **누적 시퀀스 = post6 %d + post7 %d = %d < 3** ⇒ 누적으로도 열리지 않는다."
        % (POST6["E3_SEQ"], len(seqs), POST6["E3_SEQ"] + len(seqs)))
    say("- 🟢 **⛔ 는 «선언» 금지이지 «인쇄» 금지가 아니다**(post6 정정 1 승계) — "
        "관측값은 그대로 인쇄한다: 한전기술 **%s** · 한전산업 **%s**(각 1개라 간격이 «정의되지 않는다»)."
        % (num(-1.70), num(-1.32)))
    say("- 🔴 **사유가 네 번 다 다르다** — post4 `SL` 0건 ⇒ ⛔ · post5 `SL` 1건이나 **범위만** ⇒ ⛔ · "
        "post6 시퀀스 1건이나 **§4 #19 최소 n 미달** ⇒ ⛔ · post7 `SL` 2건이나 **시퀀스 0건** ⇒ ⛔. "
        "***표본이 생긴 것과 판정이 가능해진 것은 다르다.***")
    say("- **`EXIT-X6` 미적용**(적용 범위 = E1·E4 뿐 · §1-8).")
    say("- 🔴 **방향 자기신고**: 한전기술의 `~` 를 「미완결」로 읽어도 `SL` 이라 `EXIT-E1`/`E4` 분모 «밖»이고 "
        "`EXIT-X6` 도 E1·E4 한정이라 **이 결정이 바꾸는 판정은 0**이다(PD-5 1번). "
        "영향 자리는 ① 미완결 건수 인쇄 ② `EXIT-E3` 시퀀스 길이뿐이고, 후자는 값이 **하나뿐**이라 "
        "어느 갈래에서도 「시퀀스」가 아니다.")

    # ── EXIT-X9 ─────────────────────────────────────────────────────────
    say("")
    say("## §8. `EXIT-X9` — `MANUAL` 안의 자동 사이클 (관측 · 판정 아님) · 🔴 **약한 결정 · 두 갈래 병기**")
    say("")
    man = [t for t in TRADES if t[LABEL] == "MANUAL"]
    say("동결 문언 = *「한켐형(「**자동으로 본전매도 → 이후 직접 매도**」)이 또 나오면 건수를 센다」*.")
    say("")
    say("| 갈래 | 읽기 | 이번 글 | 누적 | 3건 게이트 |")
    say("|---|---|---|---|---|")
    say("| **주(판정에 쓰는 값)** | *「본전 위협**에 따라** 직접」* = 자동 본전매도가 "
        "**일어나지 «않은»** 서술 ⇒ 한켐형 아님 | **0건** | **%d** | 미달 |" % (POST5["X9"] + POST6["X9"]))
    say("| (민감도) | 「본전 위협」 낱말이 있으므로 한켐형으로 읽음 | %d건 | %d | %s |"
        % (len(man), POST5["X9"] + POST6["X9"] + len(man),
           "미달" if POST5["X9"] + POST6["X9"] + len(man) < 3 else "🔴 **도달**"))
    say("")
    say("- 🔴 **약한 결정**: 「본전 위협에 따라」와 「자동으로 본전매도 뒤」의 차이는 **한 낱말**이다. "
        "두 갈래를 나란히 인쇄하고 **판정엔 0 을 쓴다**.")
    say("- 🔴 **방향 자기신고**: 2건 갈래를 쓰면 누적 %d 로 3건 게이트에 **가까워진다** ⇒ "
        "**0 선택은 게이트를 «여는 쪽이 아니다»**(보수적)."
        % (POST5["X9"] + POST6["X9"] + len(man)))
    say("- **`MANUAL` 2건은 이 계열에서 처음 «후속»에 붙는다**(아난티·우리기술투자 · PD-7). "
        "🔴 방향 자기신고: `MANUAL` 로 두면 두 건이 `EXIT-E1` 분모에서 **빠진다** — "
        "우리기술투자(3.28·3.25·3.08)는 **비증가**라 E1 에 유리한 건이므로 "
        "**`MANUAL` 판정은 E1 에 «불리한» 방향**이다. 유리한 쪽을 고르지 않았다.")

    # ── 누적표 ──────────────────────────────────────────────────────────
    say("")
    say("## §9. 누적 집계 — 🆕 **`EXIT-E1` 두 계열 분리**(B-4 · post7 부터 구속)")
    say("")
    say("| 글 | `EXIT-E1` **(가) 전 레그** | `EXIT-E1` **(나) `X6` 적용** | `EXIT-E4` | "
        "`EXIT-E2`(후속 포함) | `EXIT-E2`(신규만) | `EXIT-X2` | `EXIT-X8` |")
    say("|---|---|---|---|---|---|---|---|")
    say("| 4번째(2026-08-22) *동결 인용* | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | "
        "%d/%d = %.1f%% | %d/%d = %.1f%% | — (동결만) | — |"
        % (POST4["E1_ok"], POST4["E1_n"], ratio(POST4["E1_ok"], POST4["E1_n"]),
           POST4["E1_ok"], POST4["E1_n"], ratio(POST4["E1_ok"], POST4["E1_n"]),
           POST4["E4_ok"], POST4["E4_n"], ratio(POST4["E4_ok"], POST4["E4_n"]),
           POST4["E2_ok"], POST4["E2_n"], ratio(POST4["E2_ok"], POST4["E2_n"]),
           POST4["E2_ok"], POST4["E2_n"], ratio(POST4["E2_ok"], POST4["E2_n"])))
    say("| 5번째(2026-08-29) *동결 인용* | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | "
        "%d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d |"
        % (POST5["E1_ok"], POST5["E1_n"], ratio(POST5["E1_ok"], POST5["E1_n"]),
           POST5["E1_ok"], POST5["E1_n"], ratio(POST5["E1_ok"], POST5["E1_n"]),
           POST5["E4_ok"], POST5["E4_n"], ratio(POST5["E4_ok"], POST5["E4_n"]),
           POST5["E2_ok"], POST5["E2_n"], ratio(POST5["E2_ok"], POST5["E2_n"]),
           POST5["E2_ok"], POST5["E2_n"], ratio(POST5["E2_ok"], POST5["E2_n"]),
           POST5["X2_ok"], POST5["X2_n"], ratio(POST5["X2_ok"], POST5["X2_n"]),
           POST5["X8"], POST5["X8_n"]))
    say("| 6번째(2026-09-04) *동결 인용* | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | "
        "%d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d |"
        % (POST6["E1a_ok"], POST6["E1a_n"], ratio(POST6["E1a_ok"], POST6["E1a_n"]),
           POST6["E1_ok"], POST6["E1_n"], ratio(POST6["E1_ok"], POST6["E1_n"]),
           POST6["E4_ok"], POST6["E4_n"], ratio(POST6["E4_ok"], POST6["E4_n"]),
           POST6["E2a_ok"], POST6["E2a_n"], ratio(POST6["E2a_ok"], POST6["E2a_n"]),
           POST6["E2b_ok"], POST6["E2b_n"], ratio(POST6["E2b_ok"], POST6["E2b_n"]),
           POST6["X2_ok"], POST6["X2_n"], ratio(POST6["X2_ok"], POST6["X2_n"]),
           POST6["X8"], POST6["X8_n"]))
    say("| **7번째(2026-09-12 발행) 이번** | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | "
        "%d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d |"
        % (a_ok, len(tp_new), ratio(a_ok, len(tp_new)),
           e1_ok, e1_n, ratio(e1_ok, e1_n), e4_ok, e4_n, ratio(e4_ok, e4_n),
           e2a_ok, len(be_all), ratio(e2a_ok, len(be_all)),
           e2b_ok, len(be_new), ratio(e2b_ok, len(be_new)),
           x2_ok, x2_n, ratio(x2_ok, x2_n), x8, x2_n))
    ga_ok, ga_n = e1_series(a_ok, len(tp_new), "ga")
    na_ok, na_n = e1_series(e1_ok, e1_n, "na")
    c = {}
    c["E4"] = (POST4["E4_ok"] + POST5["E4_ok"] + POST6["E4_ok"] + e4_ok,
               POST4["E4_n"] + POST5["E4_n"] + POST6["E4_n"] + e4_n)
    c["E2a"] = cum_e2a
    c["E2b"] = (POST4["E2_ok"] + POST5["E2_ok"] + POST6["E2b_ok"] + e2b_ok,
                POST4["E2_n"] + POST5["E2_n"] + POST6["E2b_n"] + len(be_new))
    c["X2"] = (POST5["X2_ok"] + POST6["X2_ok"] + x2_ok,
               POST5["X2_n"] + POST6["X2_n"] + x2_n)
    c["X8"] = (POST5["X8"] + POST6["X8"] + x8, POST5["X8_n"] + POST6["X8_n"] + x2_n)
    say("| **누적** | **%d/%d = %.1f%%** | **%d/%d = %.1f%%** | **%d/%d = %.1f%%** | "
        "**%d/%d = %.1f%%** | **%d/%d = %.1f%%** | **%d/%d = %.1f%%** | **%d/%d** |"
        % (ga_ok, ga_n, ratio(ga_ok, ga_n), na_ok, na_n, ratio(na_ok, na_n),
           c["E4"][0], c["E4"][1], ratio(*c["E4"]),
           c["E2a"][0], c["E2a"][1], ratio(*c["E2a"]), c["E2b"][0], c["E2b"][1], ratio(*c["E2b"]),
           c["X2"][0], c["X2"][1], ratio(*c["X2"]), c["X8"][0], c["X8"][1]))
    say("")
    say("### §9-1. 🆕 `EXIT-E1` 누적 — **두 줄을 항상 같이 적는다**(B-4 · post7 부터 구속)")
    say("")
    say("- **(가) 전 레그 계열** = **%d/%d = %.1f%%** ⇒ **%s**(문턱 %.0f%%)"
        % (ga_ok, ga_n, ratio(ga_ok, ga_n),
           "✅ 지지" if ga_ok / ga_n >= E1_MIN else "❌ 불성립", 100 * E1_MIN))
    say("- **(나) `EXIT-X6` 적용 계열** = **%d/%d = %.1f%%** ⇒ **%s**(문턱 %.0f%%)"
        % (na_ok, na_n, ratio(na_ok, na_n),
           "✅ 지지" if na_ok / na_n >= E1_MIN else "❌ 불성립", 100 * E1_MIN))
    split_e1 = (ga_ok / ga_n >= E1_MIN) != (na_ok / na_n >= E1_MIN)
    if split_e1:
        say("- ⇒ 🔴🔴 **⛔ 「누적 정의 의존」** — 두 줄이 **90% 문턱을 사이에 두고 갈린다** "
            "⇒ **누적 `EXIT-E1` 의 지지/불성립을 «선언하지 않는다»**(B-4 문언 그대로).")
    else:
        say("- ⇒ 🟢 **두 줄이 문턱을 사이에 두고 갈리지 «않는다»** ⇒ "
            "「누적 정의 의존」 **미발동**. 🔴 그래도 **두 줄을 계속 따로 적는다** — "
            "B-4 는 *「갈릴 때만 적어라」*가 아니라 *「항상 두 줄로 인쇄하라」*이다.")
    say("- 🔑 **두 계열이 왜 다른가**: post6 이 `EXIT-X6` 을 «처음» 적용한 글이라 그 항에서 "
        "(가) **%d/%d** ↔ (나) **%d/%d** 로 갈렸고, post7 항도 (가) **%d/%d** ↔ (나) **%d/%d** 다. "
        "post4·post5 항은 두 계열이 **같은 값**이다(그때는 `EXIT-X6` 이 없었다)."
        % (POST6["E1a_ok"], POST6["E1a_n"], POST6["E1_ok"], POST6["E1_n"],
           a_ok, len(tp_new), e1_ok, e1_n))
    say("")
    say("- 누적 `EXIT-E4` **%d/%d = %.1f%%** ⇒ **%s**"
        % (c["E4"][0], c["E4"][1], ratio(*c["E4"]),
           "✅ 통과" if ratio(*c["E4"]) == ratio(na_ok, na_n) else "🔴 레그 수 의존"))
    say("- 누적 `EXIT-E2` **%d/%d = %.1f%%**(후속 포함) / **%d/%d = %.1f%%**(신규만) ⇒ **%s** · "
        "누적 `EXIT-X2` **%d/%d = %.1f%%** ⇒ **%s**"
        % (c["E2a"][0], c["E2a"][1], ratio(*c["E2a"]), c["E2b"][0], c["E2b"][1], ratio(*c["E2b"]),
           "4글 연속 불성립" if c["E2a"][0] / c["E2a"][1] < E2_MIN else "지지",
           c["X2"][0], c["X2"][1], ratio(*c["X2"]),
           "✅ 지지" if c["X2"][0] / c["X2"][1] >= E2_MIN else "❌ 불성립"))
    say("- 누적 `EXIT-X8` **%d/%d** ⇒ **%s** — 세 글 연속 주 분모에서 두 규칙이 갈린 적이 «없다»."
        % (c["X8"][0], c["X8"][1], "⛔ 구분 불가" if c["X8"][0] == 0 else "구분 가능"))
    say("")
    say("### §9-2. 🔴 누적 분모에 대한 자기신고 (판정은 안 바꾼다)")
    say("")
    say("1. **3번째 글(2026-08-14)은 누적 분모에 «없다»** — `PREREG_EXIT_V2.md` 는 2026-08-15 동결이고 "
        "§1 이 *「이 문서가 구속하는 것은 **다음 글의 신규 건**뿐」*이라 못박았다.")
    say("2. 🆕 **`EXIT-E1` 누적을 두 계열로 갈라 적는 것이 이번 글부터 구속이다**(B-4) — "
        "post6 까지는 한 줄이었고 그 판정은 **불변**이다(문언 정비가 과거 판정을 소급하지 않는다).")
    say("3. `EXIT-E2` 의 두 계열은 post4·post5 에 «후속» 개념이 없었으므로 그 두 항이 **동일**하다.")
    say("4. `EXIT-X2` 누적 분모 **%d** 는 여전히 작다." % c["X2"][1])
    say("5. 🔴 **`unknown` 1건은 어느 누적 항에도 «안» 들어간다** — 갈래 민감도는 §3 표에만 있다.")

    # ── 연결 시퀀스 (기록만) ────────────────────────────────────────────
    say("")
    say("## §10. 연결 시퀀스 — 🔁후속 3건 (PD-2 4번 · **기록만** · 어떤 판정에도 안 쓴다)")
    say("")
    say("| 건 | post6 마지막 레그 | post7 첫 레그 | 이어 붙였을 때 | 전체 |")
    say("|---|---|---|---|---|")
    for t in foll:
        prev = POST6_SEQ[t[NAME]]
        delta = t[LEGS][0] - prev[-1]
        say("| %s | %s | %s | %s | post6 [%s] + post7 [%s] = **%d레그** |"
            % (t[NAME], num(prev[-1]), num(t[LEGS][0]),
               "감소 ✅" if delta <= 0 else "🔴 **+%.2f%%p 증가**" % delta,
               seq(prev), seq(t[LEGS], t[LOSSM]), len(prev) + len(t[LEGS])))
    say("")
    say("- 🔴🔴 **한라캐스트의 연결 시퀀스가 비증가와 «양립하지 않는다»** — post6 마지막 **%s** → "
        "post7 첫 **%s** = **+%.2f%%p 증가**. post6 PD-2 전례(광전자 0.93→0.80 · 삼양 11.50→6.77)와 "
        "이번 다른 둘(아난티 10.16→1.91 · 우리기술투자 6.50→3.28)은 전부 감소였다 ⇒ "
        "***「하나의 평단」 전제가 산술로 깨진 첫 사례***(INTAKE §2-9)."
        % (num(POST6_SEQ["한라캐스트 🔁후속"][-1]), num(11.22),
           11.22 - POST6_SEQ["한라캐스트 🔁후속"][-1]))
    say("- 🔴 **원인은 해석하지 않는다** — 관측만 적는다(PD-2 4번).")
    say("- 🔴 **방향 자기신고**: 연결을 «안» 하는 선택은 `EXIT-E1`(비증가) 분모에 "
        "**−2.89 → 11.22 라는 위반 쌍을 만들지 않는 쪽** = **E1 에 «유리한» 방향**이다. "
        "그래서 위반 쌍의 존재를 **관측으로 인쇄**했다(판정엔 안 씀). "
        "🟢 동시에 **세 후속 건은 전부 `MIX`/`MANUAL` 이라 애초에 `EXIT-E1` 분모 밖**이다 — "
        "이 사실도 같이 적는다(둘 다 참이어야 방향 신고가 정직하다).")

    # ── RANGE_ONLY 규약 ────────────────────────────────────────────────
    say("")
    say("## §11. `RANGE_ONLY` 규약 (PD-18 · post6 PD-10 승계)")
    say("")
    rng = [t for t in TRADES if t[RANGE]]
    say("- 동결 규약: **「A%% ~ B%%」 범위만 적힌 건은 어떤 «비증가 「건」 분모»에도 계상하지 않는다** — "
        "`EXIT-E1`/`E3`/`E4`/`X5`/`X7` 의 분모·분자 **모두 밖** · 값(범위 양끝)만 원장에 기록.")
    say("- 🟢 **이번 글 해당 %d건.** 한전기술의 *「손실률 -1.70%% ~」* 는 **끝값이 없어 "
        "「A%% ~ B%%」가 아니다** ⇒ 범위가 아니라 **미완결 표지**다(post5 한국화장품제조 "
        "*「11.26%% ~」* 와 같은 모양 · post5 한성기업 *「-16.25%% ~ -37.48%%」* 가 진짜 `RANGE_ONLY` 였다) "
        "⇒ PD-5 1번으로 처리한다." % len(rng))
    say("- 서산의 *「Q2~MAX」* 는 **프리셋 이름**이라 대상 아님(PD-5 2번).")

    # ── 모호 지점 ──────────────────────────────────────────────────────
    say("")
    say("## §12. 🔴 모호 지점 — 양쪽 인쇄 (규칙을 고치지 않는다)")
    say("")
    say("| # | 모호한 것 | 갈래 A | 갈래 B | 판정이 갈리나 |")
    say("|---|---|---|---|---|")
    say("| 1 | 🔴 **`unknown` ↔ `TP`**(「안정형」이 `표준형/HDR*` 의 확장인가) | "
        "주 `unknown`: E1 %d/%d · E4 %d/%d · X2 %d/%d | "
        "민감도 `TP`: E1 %d · E4 %d · X2 %d | %s |"
        % (e1_ok, e1_n, e4_ok, e4_n, x2_ok, x2_n,
           DT["e1_n"], DT["e4_n"], DT["x2_n"],
           "🔒 **관리자 결정 대기** — 분모가 갈리므로 두 갈래를 전부 인쇄"))
    say("| 2 | `EXIT-X6` 기준(`~` 문자 vs 서술) | `~` 기준 %d/%d = %.1f%% | "
        "서술 기준 %d/%d = %.1f%% | **아니오**(`~` 는 `SL` 건에만 있다) |"
        % (t_ok, len(tp_new), ratio(t_ok, len(tp_new)), e1_ok, e1_n, ratio(e1_ok, e1_n)))
    say("| 3 | `EXIT-E2` ↔ `EXIT-X2` 분모 충돌(동결 문언 둘) | `be_note` %d건 | "
        "신규 완결 `TP` %d건 | **해당 없음** — 서로 다른 항목이라 둘 다 인쇄(병기 의무) |"
        % (len(be_all), len(x2t)))
    say("| 4 | 🆕 `EXIT-E1` 누적 계열 (가)/(나) | (가) %d/%d = %.1f%% | (나) %d/%d = %.1f%% | %s |"
        % (ga_ok, ga_n, ratio(ga_ok, ga_n), na_ok, na_n, ratio(na_ok, na_n),
           "🔴 **예 — ⛔ 「누적 정의 의존」**" if split_e1 else "**아니오**(둘 다 같은 쪽)"))
    say("| 5 | `EXIT-X9` 「본전 위협에 따라」 읽기 | 0건(주) | %d건(민감도) | "
        "**아니오** — 누적 %d·%d 둘 다 3 미만 |"
        % (len(man), POST5["X9"] + POST6["X9"], POST5["X9"] + POST6["X9"] + len(man)))
    say("| 6 | 🔴 **`EXIT-X7` ↔ §4 #19 충돌**(동결 문언 둘 · post6 승계) | "
        "§2-3 `EXIT-X7`: 시퀀스면 **판정** | §4 #19: 시퀀스 < 3 ⇒ **⛔** | "
        "**해당 없음 이번 회차** — 시퀀스가 **0건**이라 두 문언이 **같은 답(⛔)** 을 낸다 |")
    say("| 7 | 범한퓨얼셀 「10.8」 소수 1자리 | 그대로 1자리 | 2자리로 「10.80」 보정 | "
        "**아니오**(비증가 판정 불변) — 🔴 그러나 `REC-Z5` 잔차 축에는 **한계 표기 의무**(PD-10 3번) |")
    say("")
    say("- 🔴 **#1 은 분모를 가른다** — 그래서 §3 에 갈래별 분모를 **전부** 인쇄하고 "
        "**동결 문언이 지시한 `unknown` 을 주 판정으로** 두었다(넓히는 결정은 관리자·사장님 몫).")
    say("- 나머지는 판정을 가르지 않는다. 가르는 항목이 더 나오면 **그 사실과 갈래별 값을 적고** "
        "**지지 선언을 하지 않는다**. 🔴 **이때 «…의존» 같은 이름표를 새로 만들어 붙이지 않는다** "
        "— 동결본에 없는 라벨은 다음 사람이 **동결 조항으로 읽는다**(§5-3 자기신고 참조). "
        "⚠️ 그리고 **최소 n 을 못 채운 갈래는 «갈렸다»의 근거로 세지 않는다.**")

    # ── 한계 ────────────────────────────────────────────────────────────
    say("")
    say("## §13. 미리 적어두는 한계 (승계 + 이번 회차 고유)")
    say("")
    say("1. 🔴 **ε = %g%%p 가 4글 연속 사용 0회** — 값을 정한 근거(근접쌍 8건)는 **첫 표본**에서 왔고, "
        "이 대역이 실제로 필요한 적이 아직 없다. `PREREG_EXIT_V2.md` §4 대로 **고치지 않는다**." % EPS)
    say("2. 🔴 **생략 편향** — `TP` 신규 %d건 중 %d건이 미완결이다(계열 최고 비율). "
        "생략분은 대개 뒤쪽(낮은 수익률)이라 「비증가」에 «유리한» 방향이다."
        % (D["tp_n"], om_tp))
    say("3. 🔴 **`EXIT-X2` 의 반증축이 세 글 연속 「구분 불가」** — 주 분모에서 「손실률」 레그가 0개라 "
        "두 규칙이 구성상 같은 레그를 고른다. `EXIT-X2` 의 결과는 「`EXIT-X2` 가 작동한다」의 증거가 아니다.")
    say("4. 🔴 **`EXIT-E3` ⛔ 판정 불가**(시퀀스 0 · 누적 %d < 3) — 관측은 인쇄하되 "
        "지지/불성립을 선언하지 않는다." % (POST6["E3_SEQ"] + len(seqs)))
    say("5. 🔴 **`unknown` 은 「모른다」이지 「불성립」이 아니다** — 이 건을 어느 `EXIT-` 분모에도 "
        "넣지 않은 것은 **판정을 미루는 것**이지 **면제하는 것**이 아니다. "
        "🔒 관리자 결정이 나오면 그 결정대로 «다음 글부터» 구속한다(이번 판정을 소급 수정하지 않는다).")
    say("6. 🔴 **저자가 레그별 시각·수량을 안 적는다.** 「시퀀스 순서 = 체결 순서」는 여전히 **가정**이다.")
    say("7. 🔴 **🔁후속 3건의 「하나의 평단」 전제가 이번에 산술로 깨졌다**(한라캐스트) — "
        "연결 시퀀스를 어디에도 쓰지 않는 이유가 «관행»에서 «실증»으로 바뀌었다.")
    say("8. 🔴 **프로그램 버전이 이 계열 최초로 «없다»**(PD-8) ⇒ 버전 공변량 축에서 post7 행은 **분모 밖**이다. "
        "이 산출물은 버전을 쓰지 않으므로 값에는 영향이 없다.")
    say("9. 이 분석은 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2).")
    say("")
    say("[[LABELS_2026-09-15_post7]] · [[INTAKE_2026-09-15_post7]] · [[PREDECISION_2026-09-15_post7]] · "
        "[[PREREG_POST6]] · [[PREREG_EXIT_V2]] · [[RESULTS_EXIT_V2_POST6]] · "
        "[[RESULTS_EXIT_V2_POST5]] · [[RESULTS_EXIT_V2_POST4]]")

    (BASE / "RESULTS_EXIT_V2_POST7_NUMBERS.md").write_text("\n".join(OUT) + "\n",
                                                           encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""`PREREG_EXIT_V2.md` §3 + `PREREG_POST6.md` §2-3(X5~X9 재동결) 실행 — 11번째 글 · 🔒 감시 모드 판정 축 `EXIT-`.

`run_exit_v2_post10.py` 의 얇은 승계판 — 판정 로직 신설 0.
  · 통계 핵·표기 함수 = `run_exit_v2_post6.py`(`EPS`·`E1_MIN`·`E2_MIN`·`BE_MAX`·`nonincreasing`·`eps_pairs`·`num`·`seq`·
    `x2_leg`·`x6_legs`·`ratio`)
  · 갈래 분모·재계산·표기 헬퍼 = `run_exit_v2_post8.py`(`denoms`·`e1_ok`·`recount`·`frac`·`mark` · 열 인덱스 · `URIRO`)
  · 옛 회차 재계산 입력 = `run_exit_v2_post{4,5,6,7,8,9,10}.py` 의 `TRADES`(import 만 · 한 글자도 고치지 않는다)
  🔴 새로 정의하는 것 = post11 `TRADES`(원장 · LABELS 동결값) · 🆕 `F-6`(`P11-완결서술`) 병기 갈래 `(광전자 미완결, n, 답)` ·
    post11 의무 인쇄뿐.

준거(동결 · 규칙 변경 0):
  · `PREREG_EXIT_V2.md` §2 판별표 · §3 E1~E4 · B-4(E1 누적 두 계열) · `:55`(「다음 글의 신규 건에만」)
  · `PREREG_POST6.md` §1-8(X6 적용 범위 = E1·E4) · §2-3 · §4 #13~#20(최소 n)
  · `PREREG_POST8.md` `D-2`(`P8-형변량`) · `D-5`(`P8-갈래계수` `:336-343`)
  · `PREREG_POST9.md` §1 `P9-공통독법` · `PREREG_POST10.md` §0-1 · 🆕 `PREREG_POST11.md` `F-1`(감시 모드) · `F-3`(`P10-기업행위봉`) ·
    `F-6`(`P11-완결서술`: 주 독법 완결 · 약한 자리 병기 갈래 의무 · `~` 값 줄 끝 = (P) 갈래)
  · 🔒 #1 ✅ A(2026-10-08) — 한국첨단소재 = 재진입 신규 `exact` ⇒ `EXIT-X2` 병기 갈래 `(광전자 미완결)` 분모 3 ≥ 3 ⇒ 갈래 계수 ·
    🔒 #2 ✅ 후속 — 한켐은 후속(주 분모 밖 · `EXIT-E2` 누적 포함)
  · `P11-최소n갈림` — 최소 n 미달 갈래 = 인쇄 의무 · 갈림 근거 아님
  · `PREDECISION_2026-10-08_post11.md` PD-5 · PD-7 · PD-14 · PD-23(`EXIT-` 행) · PD-32 · PD-35

DB 를 읽지 않는다(저자 서술만) ⇒ 결정적 · 시드 불필요 · 라이브 트리 import 0건.
🔴 라이브 채택 대상이 아니다(`PREREG_POST10.md` §0-1 축자 승계). 새 예측·새 라벨을 만들지 않는다 · 등급 이름을 적지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from run_exit_v2_post6 import (  # noqa: F401
    BE_MAX, E1_MIN, E2_MIN, EPS, eps_pairs, nonincreasing, num, ratio, seq, x2_leg, x6_legs,
)
import run_exit_v2_post4 as E4MOD
import run_exit_v2_post5 as E5MOD
import run_exit_v2_post6 as E6MOD
import run_exit_v2_post7 as E7MOD
import run_exit_v2_post8 as E8MOD
import run_exit_v2_post9 as E9MOD
import run_exit_v2_post10 as E10MOD
from run_exit_v2_post8 import (  # noqa: F401
    BE, E2_MIN_N, E3_MIN_N, E4_MIN_N, LABEL, LEGS, LOSSM, NAME, NEW, OPEN_N, PRESET, RANGE, TILDE, TP_MIN_N, URIRO,
    X2_MIN_N, denoms, e1_ok, frac, mark, recount,
)

BASE = Path(__file__).resolve().parent
OUT: list = []
NUMBERS = BASE / "RESULTS_EXIT_V2_POST11_NUMBERS.md"

DB_UPTO = "2026-10-08"
STAGE1_DBMAX = ("2026-10-16", "2,764")   # 착수 조건 관측(2026-10-16 19:53:25/19:53:48/19:54:12 KST · 3/3 동일) — 인용
PROBE_DIR = "D:/archive/tasso-program-journal-20261008/probes_precalc_1016/"
BOUND_UPPER = "2026-10-14"

# (종목, 라벨, 레그, 「손실률」마스크, 서술기준 미완결, `~` 문자, breakeven_note, 신규, 범위만, `(형, HDR)`)
# 🔴 앞 9열은 post6~post10 와 «같은 순서» — 원장 `ledger_trades.csv`/`ledger_legs.csv`(post11 9행) · LABELS 동결값 그대로
SANDS = "샌즈랩 🔁후속 (MIX 승계)"
ESTWO = "에스투더블유 🔁후속"
URORO = "우리로 🔁후속"
HANCOM = "한컴위드 🔁후속"
HANKEM = "한켐 🔁후속"
HANKUK = "한국첨단소재 🔂재진입"
GWANG = "광전자 🔂재진입"
TRADES = [
    (SANDS,   "MIX", [29.99, 29.68, 29.06, 28.88, 27.52],         [0] * 5, False, True,  False, False, False, "(표준형, 60) × 2(사이클 2)"),
    (ESTWO,   "TP",  [24.04, 24.02],                              [0] * 2, False, False, False, False, False, "(표준형, 60)"),
    (URORO,   "TP",  [23.36],                                     [0] * 1, False, False, False, False, False, "(표준형, 60)"),
    (HANCOM,  "TP",  [17.60, 17.60, 17.60, 15.64, 12.60, 11.99],  [0] * 6, False, False, False, False, False, "(표준형, 60)"),
    (HANKUK,  "TP",  [24.63, 18.59, 18.57, 12.51, 6.63, 6.46],    [0] * 6, False, False, False, True,  False, "(표준형, 사분위수)"),
    (GWANG,   "TP",  [10.76, 8.59, 6.10, 4.33],                   [0] * 4, False, False, False, True,  False, "(표준형, 60)"),
    ("삼현",  "TP",  [10.32, 0.49],                               [0] * 2, False, False, True,  True,  False, "(표준형, 60)"),
    ("쓰리빌리언", "TP", [9.46, 0.49],                             [0] * 2, False, False, True,  True,  False, "(표준형, 60)"),
    (HANKEM,  "TP",  [0.05],                                      [0] * 1, False, False, True,  False, False, "(표준형, 60)"),
]
FORM_WHITELIST = {"표준형"}
UNREGISTERED_FORMS: list = []          # 9/9 형 = 「표준형」 ⇒ 없음(`P8-형변량` · PD-20)
LEG_OPEN_ENDED = {SANDS: 27.52}        # 서술 미완결 0 — `~` 레그 표지 1(샌즈 값 줄 끝 · 후속·`MIX`)
TILDE_TRAP = ("레그 표지 1(샌즈 값 줄 끝 「27.52% ~」 · 후속·`MIX` 라 E1/E4/X6/X2 밖) · 차수 표기 5 · 날짜 1"
              "(「9월 22~23일」)")
WEAK_ONLY = (GWANG,)                    # 약한 자리 1(`F-6` · 확인 #2) — 병기 갈래 `(광전자 미완결)` 필수
X9_MAIN, X9_BROAD = 0, 0                # `MANUAL` 0 ⇒ 두 독법 모두 0
# 연결 시퀀스 입력 = 직전 글 `TRADES`(import 만) — (모듈, 그 모듈에서의 종목 이름)
FOLLOW_SRC = {SANDS: (E10MOD.TRADES, "샌즈랩 🔀2사이클"),
              ESTWO: (E9MOD.TRADES, "에스투더블유"),
              URORO: (E10MOD.TRADES, "우리로 🔂재진입"),
              HANCOM: (E10MOD.TRADES, "한컴위드 🔁후속"),
              HANKEM: (E10MOD.TRADES, "한켐 🔂재진입")}

LIVE_39 = ("> *「🔴 **라이브 채택 금지.** 저자가 *\"사람이 할 일은 종목 고르는 것까지\"* 라고 적었다. 후보 선정이 재량이면 "
           "규칙을 복원해도 자동화 대상이 아니다. 이 검정의 산출물은 **기록**이지 전략 후보가 아니다.」*")
LIVE_41 = ("⇒ `PREREG_POST8.md:26` 그대로 — *「이 문서가 만드는 **어떤 조항·규약·범주도** 라이브 전략·파라미터 변경의 근거가 "
           "아니다」*. 🔴 *등급이 「성립」이어도 라이브 채택 금지는 그대로다*(`PREREG_GRADE_TIERS.md:30`). `PREREG.md:14`"
           "(§0 1번 · 성과·엣지 추정 금지)도 그대로다. 라이브 8전략·페이퍼 전략과 **무관**하다(`PREREG_POST9.md:36-41` 축자 승계).")
LIVE_HEAD = "🔴 **라이브 채택 금지 — `PREREG_POST10.md` §0-1 문언 그대로**(`PREREG.md:15` 인용 · `:56`·`:58` · 축자 승계):"


def say(s=""):
    print(s)
    OUT.append(s)


def as_new(trades):
    """후속 확장 갈래(🔒 계수 안 함 · 인쇄만) — 후속 건을 «신규»로 넣은 사본(값·순서 불변)."""
    return [t[:NEW] + (True,) + t[NEW + 1:] for t in trades]


def frac0(p):
    """`frac` 승계 — 분모 0 이면 `nan%` 대신 「0/0」(표기만 · 값 불변)."""
    return "0/0" if (p is not None and p[1] == 0) else frac(p)


def launch_line():
    """`P11-착수상한` 신고 줄 — 첫 러너(`SEL-`)가 «DB 로 센» 줄을 그대로 인용한다(이 레인은 DB 조회 0회)."""
    p = BASE / "RESULTS_SELECTION_POST11_NUMBERS.md"
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.startswith("- 🔴 **`P11-착수상한`**"):
                return ln + " (인용 — 첫 러너 `run_selection_post11.py` 의 DB 집계 줄)"
    return "- 🔴 **`P11-착수상한`**: (첫 러너 `RESULTS_SELECTION_POST11_NUMBERS.md` 신고 줄 없음 — 인용 불가)"


def x2_ok_of(ts):
    return sum(1 for t in ts if abs(x2_leg(t[LEGS], t[LOSSM])[0]) < BE_MAX)


def ans(ok, n, thr, mn):
    return ("%d/%d = %.1f%% %s" % (ok, n, ratio(ok, n), "✅" if ok / n >= thr else "❌")) if n >= mn \
        else "%d/%d — 최소 n 미달(답 없음)" % (ok, n)


def main(numbers: Path = NUMBERS):  # noqa: C901
    OUT.clear()
    LAUNCH_LINE = launch_line()
    DN = denoms(TRADES)                          # (서술) 주
    DP = denoms(TRADES, basis="tilde")           # (P) 순수 `~` 문자 기준 — 민감도 갈래(확인 8)
    EXT = as_new(TRADES)
    DNX = denoms(EXT)                            # 후속 확장 (서술)
    DPX = denoms(EXT, basis="tilde")             # 후속 확장 (P)
    TW = [t[:OPEN_N] + (True,) + t[OPEN_N + 1:] if t[NAME] == WEAK_ONLY[0] else t for t in TRADES]   # `F-6` 병기: 광전자 미완결
    DW = denoms(TW)
    tp_new = DN["tp_new"]
    new = [t for t in TRADES if t[NEW]]
    foll = [t for t in TRADES if not t[NEW]]
    mix = [t for t in TRADES if t[LABEL] == "MIX"]

    say("# RESULTS_EXIT_V2_POST11_NUMBERS — 기계 생성 (수정 금지)")
    say("")
    say("사전등록 `PREREG_EXIT_V2.md` §3 + `PREREG_POST6.md` §2-3(`EXIT-X5`~`X9`) + `PREREG_POST8.md`(`D-2`·`D-5`) + "
        "`PREREG_POST9.md` §1 + 🆕 `PREREG_POST11.md`(동결 `bf59fd0` · `F-1`·`F-3`·`F-6`) · 🔒 #1 ✅ A(`EXIT-X2` 병기 갈래 계수) · "
        "라벨 `LABELS_2026-10-08_post11.md` · 결정 `PREDECISION_2026-10-08_post11.md` · 생성 `run_exit_v2_post11.py` · "
        "재사용 `run_exit_v2_post6.py`(통계 핵) · `run_exit_v2_post8.py`(`denoms`·`e1_ok`·`recount`·`frac`·`mark`) · "
        "옛 회차 재계산 입력 `run_exit_v2_post{4,5,6,7,8,9,10}.py` 의 `TRADES`(import 만)")
    say("허용 오차 ε = %g%%p(동결분) · 문턱 `EXIT-E1`/`X5` ≥ %.0f%% · `EXIT-E2`/`X2` ≥ %.0f%% · 본전 |ret| < %.1f%%"
        % (EPS, 100 * E1_MIN, 100 * E2_MIN, BE_MAX))
    say("")
    say("## §0. 환경 · 동결 규약 · 의무 대조")
    say("")
    say("**창 종료 %s = 발행 당일(목 · 거래일) 봉 «포함» · `END` · 3축 · PD-1**" % DB_UPTO)
    say("**실행 시 `max(date)` = %s · 그 날짜 행수 %s — 기록만(창 아님)** — 착수 조건 관측 인용(`%s` · 3/3 동일 · "
        "2026-10-16 19:53:25/19:53:48/19:54:12 KST) · 이 레인은 **DB 조회 0회**(저자 서술만) ⇒ 이 산출물은 그 스냅샷에 의존하지 않는다"
        % (STAGE1_DBMAX[0], STAGE1_DBMAX[1], PROBE_DIR))
    say("")
    say("- 🔒 **감시 모드 첫 회차(`F-1`)**: 판정 축 3(`SEL-`·`EXIT-`·`S5`) · 중단 7(`REG-`·`LAD-`·`REC-`·`TV-`·`WRC-`·`RNK-`·`SEC-` = 러너 0 · "
        "산출물 0) · 종결 `ANC-`")
    say(LAUNCH_LINE)
    say("- 라운드 상한 100 → 120(10-08 22:3x) → 170만(10-16 19:5x 🔒) · 착수 전 누계 ≈92")
    say("")
    say(LIVE_HEAD)
    say(LIVE_39)
    say(LIVE_41)
    say("")
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| DB | **조회 0회** · 시드 불필요 · **결정적**(두 번 돌리면 byte 동일) |")
    say("| 라벨 동결 | `TP` **8**(신규 4 · 후속 4) · `MIX` **1**(샌즈 · 후속 승계) · `MANUAL` **0** · `SL` **0** · `unknown` **0** — 값을 보기 «전»에 "
        "정해졌다(`LABELS_2026-10-08_post11.md`) |")
    say("| 🔒 결정 | post9 #4 선례(E1·E4 · 확인 8) · 🔒 #1 ✅ A(한국첨단소재 신규 `exact` ⇒ `X2` 병기 갈래 `(광전자 미완결)` 분모 3 계수) · 🔒 #2 ✅ 후속(한켐) |")
    say("")
    say("| 의무 | 이 산출물 | 자리 |")
    say("|---|---|---|")
    say("| `D-2`(`P8-형변량` 세 수) | **해당** | §3 |")
    say("| `D-5`(`P8-갈래계수`) | **해당** — 갈래마다 `(갈래 이름, n, 답)` 세 쪽 · 항등도 인쇄 | §12 |")
    say("| `D-3`(`P8-approx의존신고`) | 🔴 **대상 축 아님**(`EXIT-` 분모는 등록일 정밀도로 정의되지 않는다) · 신고 줄은 형식대로 인쇄 | §12-1 |")
    say("| `D-9`(읽은 시각 · 혼합 빈티지) · `P9-스탬프통일` | **해당 없음** — `H`·`L`·`L₅` 를 읽지 않는다(DB 0회 · `PREREG_POST9.md` §6 (나) 1 · PD-35 범위 밖) | — |")
    say("| `D-1`·`D-4`·`D-6`·`D-7`·`D-11` | 해당 없음(`ANC-`/`LAD-` · `WRC-` · `n_up` sd · 창5 가드 · `Q1-R2`) | — |")
    say("| `P9-공통독법`(§1) | 신고 줄 1줄 — 대상 없음(목록 밖 · `approx` 0) | §12-1 |")
    say("| `P9-행단위`·`P9-결측분리`(`D-8`) | 해당 없음 — `prog_ver` 를 공변량으로 쓰지 않는다(PD-26) · 수준·결측 줄은 `WRC-`·`RNK-`·`SEC-` 몫 | — |")
    say("| `F-3` `P10-기업행위봉` | **해당**(보수 「예」 · 창 = 그 축 동결 문언의 창 «그대로») | §12-1 |")
    say("| `F-5`(`P10-앵커종결`) · `P10-approx누적범위` | 해당 없음 — `EXIT-` 는 종결 5항목 밖 · 신규 `approx` 0 ⇒ 미발효 | — |")
    say("| 🆕 `F-6`(`P11-완결서술`) | **해당** — 주 독법 완결 9/9 · 약한 자리 1(광전자) 병기 갈래 · `~` 값 줄 끝 1(샌즈) (P) 갈래 | §2 · §4 · §5-2 · §12 |")
    say("| 🆕 `P11-최소n갈림` | **해당** — 최소 n 미달 갈래 = 인쇄 의무 · 갈림 근거 아님 | §4 · §5 · §12 |")
    say("| 🆕 `P11-착수상한` · 감시 모드 머리 줄 | **해당** | 머리 |")
    say("")
    say("> 🟢 **`P8-형변량` 적용 결과 `unknown` 0** — 9/9 형 = 「표준형」.")
    say("> 🔴 **이 문서는 새 예측을 만들지 않는다**(`PREREG_POST6.md` §7-B #11) · 🟢 라벨 접두는 **`EXIT-`**.")
    say("")

    # ── §1 원표 ─────────────────────────────────────────────────────────
    say("## §1. 원표 — 11번째 글 9건 (신규 4 + 🔁후속 5 · 라벨은 계산 «전» 동결)")
    say("")
    say("| # | 종목 | 구분 | `(형, HDR)` | 라벨 | 완결(서술) | `~` | `be_note` | 레그 | 시퀀스(저자 순서) | 「손실률」 | 비증가 | 위반 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for k, t in enumerate(TRADES, 1):
        v = nonincreasing(t[LEGS])
        nloss = sum(t[LOSSM])
        say("| %d | %s | %s | %s | `%s` | %s | %s | %s | %d | %s%s | %s | %s | %s |" % (
            k, t[NAME], "신규" if t[NEW] else "🔁후속", t[PRESET], t[LABEL],
            "완결" if not t[OPEN_N] else "**미완결**", "**예**" if t[TILDE] else "—",
            "**1**" if t[BE] else "0", len(t[LEGS]), seq(t[LEGS], t[LOSSM]),
            " **(범위만)**" if t[RANGE] else "", ("%d개" % nloss) if nloss else "—",
            "✅" if not v else "❌",
            "—" if not v else "; ".join("%s→%s(+%.2f%%p)" % (num(a), num(b), b - a) for _, a, b in v)))
    say("")
    lab = {x: sum(1 for t in TRADES if t[LABEL] == x) for x in ("TP", "SL", "MIX", "MANUAL", "unknown")}
    say("- 라벨 집계: `TP` %d · `SL` %d · `MIX` %d · `MANUAL` %d · `unknown` %d (신규 4 = `TP` 4 · 🔁후속 5 = `TP` 4 + `MIX` 1)"
        % (lab["TP"], lab["SL"], lab["MIX"], lab["MANUAL"], lab["unknown"]))
    say("- 레그 합계 **%d**(신규 %d · 후속 %d) · 「손실률」 레그 **%d**"
        % (sum(len(t[LEGS]) for t in TRADES), sum(len(t[LEGS]) for t in new),
           sum(len(t[LEGS]) for t in foll), sum(sum(t[LOSSM]) for t in TRADES)))
    say("- 미완결(서술 기준) **%d건**(%s) — 「나머지 물량은 보유 중」이 판별 낱말이다(PD-5 · 「완료」 키워드 파서 금지) · "
        "`leg_open_ended = 1` = %s."
        % (sum(1 for t in TRADES if t[OPEN_N]), " · ".join(t[NAME] for t in TRADES if t[OPEN_N]),
           " · ".join("%s %s" % (k, num(v)) for k, v in LEG_OPEN_ENDED.items())))
    say("- 🔴🔴 **`~` 정규식 함정**: 본문 `~` 7개(7줄) 중 레그 표지 **1** — %s(PD-5) ⇒ `TP` 분모에서 (P)(순수 `~` 문자 기준)는 미완결 **0건**"
        "(샌즈는 후속·`MIX` 라 분모 밖 · 값 줄 중간 `~` 0)." % TILDE_TRAP)
    say("- 🔴 표기 특이: 동률 17.60 ×3(한컴) · 값 개수 ≠ 서술 매도 횟수(샌즈 5 ↔ 1차+2~4차 · 한컴 6 ↔ 1차+2~4차 · 한국첨단소재 6 ↔ 1~4차 · "
        "에스투 2 · 우리로 1) — 원문 값 그대로 레그(확인 3).")
    say("- 🔴 **`EXIT-X6` 적용 범위 = `EXIT-E1`·`EXIT-E4` «뿐»**(`PREREG_POST6.md` §1-8) — `EXIT-X2`·`EXIT-X8` 의 「마지막 레그」는 "
        "저자 «원» 시퀀스 기준이다 · 🔴 `MIX` 1건(샌즈 · 후속)은 E1/E4/X6/X2 미적용(`PREREG_EXIT_V2.md:59` · 값만).")

    # ── §2 E1 / X5 ──────────────────────────────────────────────────────
    say("")
    say("## §2. `EXIT-E1` · `EXIT-X5` — `TP` 신규 건의 매도 레그 시퀀스가 비증가 (문턱 ≥%.0f%%)" % (100 * E1_MIN))
    say("")
    say("주 판정 = **(서술) 기준** — 서술 미완결 `TP` 신규 0건 ⇒ `EXIT-X6` 제거 대상 없음(🆕 `F-6` 주 독법 완결 9/9) · "
        "(P) 순수 `~` 문자 기준 = **민감도 갈래**(두 갈래 모두 최소 n 이면 답이 갈릴 때 [갈래 의존]) · 🆕 병기 갈래 `(광전자 미완결)`(`F-6` 약한 자리). 🔴 후속 5건은 "
        "**「신규 건에만」**(`PREREG_EXIT_V2.md:55`)으로 분모 밖(PD-2).")
    say("")
    say("| 종목 | 완결(서술) | 원 시퀀스 | `EXIT-X6`(서술) 후 | 레그 | 비증가 | 위반 |")
    say("|---|---|---|---|---|---|---|")
    for t in tp_new:
        L = x6_legs(t, "narr")
        v = nonincreasing(L)
        say("| %s | %s | %s | %s | %d | %s | %s |"
            % (t[NAME], "완결" if not t[OPEN_N] else "**미완결**", seq(t[LEGS]),
               seq(L) if L != list(t[LEGS]) else "(동일)", len(L), ("✅" if not v else "❌") if L else "— (분모 밖)",
               "—" if not v else "; ".join("%s→%s" % (num(a), num(b)) for _, a, b in v)))
    e1k, e1n = e1_ok(DN["e1"]), DN["e1_n"]
    e1pk, e1pn = e1_ok(DP["e1"], "tilde"), DP["e1_n"]
    e1xk, e1xn = e1_ok(DNX["e1"]), DNX["e1_n"]
    r1 = e1k / e1n
    say("")
    say("- **`EXIT-E1` (서술) 주 = %d/%d = %.1f%%** ⇒ **%s** (문턱 %.0f%% · 주 분모 **%d** ≥ `TP` 최소 n %d)"
        % (e1k, e1n, ratio(e1k, e1n), "✅ 지지" if r1 >= E1_MIN else "❌ 불성립", 100 * E1_MIN, e1n, TP_MIN_N))
    say("- (P) 민감도 갈래(확인 8) = **%d/%d = %.1f%%** ⇒ %s · 후속 확장 (서술)(계수 안 함 · 인쇄만) = %d/%d = %.1f%%"
        % (e1pk, e1pn, ratio(e1pk, e1pn), mark(e1pk, e1pn, E1_MIN, TP_MIN_N), e1xk, e1xn, ratio(e1xk, e1xn)))
    e1wk, e1wn = e1_ok(DW["e1"]), DW["e1_n"]
    say("- 🆕 **병기 갈래 `(광전자 미완결, n, 답)`**(`F-6` 약한 자리) = **(광전자 미완결, %d, %d/%d = %.1f%%)** ⇒ %s"
        % (e1wn, e1wk, e1wn, ratio(e1wk, e1wn), mark(e1wk, e1wn, E1_MIN, TP_MIN_N)))
    split_e1_p = (e1n >= TP_MIN_N and e1pn >= TP_MIN_N) and ((e1k / e1n >= E1_MIN) != (e1pk / e1pn >= E1_MIN))
    say("- ⇒ 확인 8: (서술)·(P) **두 갈래 모두 최소 n**(%d · %d ≥ %d) ⇒ 답이 %s"
        % (e1n, e1pn, TP_MIN_N,
           "🔴 **갈린다 — [갈래 의존](= 「표기 의존」 · post6 PD-4 `:90`)**" if split_e1_p else "**같다 — 갈리지 않는다**"))
    say("- **`EXIT-X5`**(= `RESULTS_EXIT_V2_POST5.md` §10 재확인 예측) = 같은 계산 ⇒ **%s** · 조건부 조항 *「위반 1건이 곧 첫 반례 … "
        "«생략 편향이 만든 100%%» 가설로 먼저 의심」* ⇒ 이번 위반 **%d건** ⇒ **%s**"
        % ("✅ 적중" if r1 >= E1_MIN else "❌ 빗나감", e1n - e1k, "미발동" if e1k == e1n else "🔴 발동"))
    withlegs = [t for t in TRADES if t[LEGS]]
    allv = [t for t in withlegs if nonincreasing(t[LEGS])]
    say("- 🔎 **라벨 제외 «전» %d건 전체**(원 시퀀스 · 후속·`MIX` 포함): 위반 **%d건** ⇒ 라벨 결정이 `EXIT-E1` 판정을 **%s**."
        % (len(withlegs), len(allv), "만들지 않았다" if not allv else "만들 수 있는 자리가 있다"))
    used = [(t[NAME], a, b) for t in withlegs for a, b in eps_pairs(t[LEGS])]
    ties = [(t[NAME], a) for t in withlegs for a, b in zip(t[LEGS], t[LEGS][1:]) if a == b]
    drops = sorted((round(a - b, 10), t[NAME], a, b) for t in withlegs for a, b in zip(t[LEGS], t[LEGS][1:]) if a > b)
    say("- **ε 사용 건수 = %d회**(0 < 증가 ≤ %g%%p 인 쌍) · 동률 %d쌍(%s) · **최소 하락 간격 = %s %s → %s = %.2f%%p** — "
        "%s · `PREREG_EXIT_V2.md` §4 한계 그대로."
        % (len(used), EPS, len(ties), " · ".join("%s %s" % (n, num(a)) for n, a in ties) or "없음",
           drops[0][1], num(drops[0][2]), num(drops[0][3]), drops[0][0],
           ("하락이라 ε 이 걸리지 않는다 ⇒ **ε 은 8글 연속 사용 0회**(post4~post11 · 글 안 관측)" if not used
            else "🔴 ε 이 걸린 쌍 있음 — 8글 연속 0회가 끊겼다")))

    say("")
    say("### §2-1. 미완결 처리 민감도 — (가)(나)(다) 병기(`EXIT-X6` #17 의무) + (P) 순수 `~` 문자 기준(확인 8)")
    say("")
    say("| 처리 | 대상 `TP` 신규 | 비증가 | 비율 | 비고 |")
    say("|---|---|---|---|---|")
    a_ok = sum(1 for t in tp_new if not nonincreasing(t[LEGS]))
    say("| (가) 전 레그 포함 | %d | %d | %.1f%% | 민감도 · post4·post5 가 쓴 처리 |" % (len(tp_new), a_ok, ratio(a_ok, len(tp_new))))
    say("| (나) 미완결 건의 **마지막 레그만** 제거 = **(서술) 기준** | %d | %d | %.1f%% | 🟢 **주 판정값**(미완결 건 0 ⇒ (가)와 항등) |"
        % (e1n, e1k, ratio(e1k, e1n)))
    comp = [t for t in tp_new if not t[OPEN_N]]
    c_ok = sum(1 for t in comp if not nonincreasing(t[LEGS]))
    say("| (다) 미완결 건을 **통째 제외** | %d | %d | %.1f%% | 민감도 · n=%d %s 3 |"
        % (len(comp), c_ok, ratio(c_ok, len(comp)), len(comp), "≥" if len(comp) >= 3 else "<"))
    say("| (P) `EXIT-X6` 을 `~` 로만 적용(순수 문자 기준) | %d | %d | %.1f%% | 확인 8 민감도 갈래 · `TP` 신규에 `~` 레그 표지 0 ⇒ 전 레그 |"
        % (e1pn, e1pk, ratio(e1pk, e1pn)))
    say("| (W) 병기 `(광전자 미완결)`(`F-6`) | %d | %d | %.1f%% | 광전자 마지막 레그 4.33 만 제거 |"
        % (e1wn, e1wk, ratio(e1wk, e1wn)))
    say("| (H) 서술 미완결 ∪ `~`(post8 레인 혼합 읽기) | %d | %d | %.1f%% | `TP` 신규에 `~` 0 ⇒ (서술)과 **항등** |"
        % (e1n, e1k, ratio(e1k, e1n)))
    say("")
    procs = [("가", a_ok, len(tp_new)), ("나", e1k, e1n), ("다", c_ok, len(comp)), ("P", e1pk, e1pn), ("W", e1wk, e1wn)]
    counted_p = [(nm, k_, n_) for nm, k_, n_ in procs if n_ >= TP_MIN_N]
    verdicts = {k_ / n_ >= E1_MIN for _nm, k_, n_ in counted_p}
    say("- ⇒ 최소 n 을 채운 처리(%s)가 **%s**%s ⇒ 판정이 처리 선택에 **%s**."
        % (" · ".join("(%s) n=%d" % (nm, n_) for nm, _k, n_ in counted_p),
           "모두 같은 판정" if len(verdicts) == 1 else "서로 다른 판정",
           "" if all(n_ >= TP_MIN_N for _nm, _k, n_ in procs) else
           " · 미달 처리: " + " · ".join("(%s) n=%d" % (nm, n_) for nm, _k, n_ in procs if n_ < TP_MIN_N) + " 은 인쇄만",
           "의존하지 않는다 — 「표기 의존」 미발동" if len(verdicts) == 1 else "🔴 의존한다 — 「표기 의존」"))
    say("- ⚠️ 레그 **2개**인 건(삼현·쓰리빌리언)은 비증가를 거의 자동으로 만족한다 — `EXIT-E4` 가 걷어낸다.")
    say("- `EXIT-X6`(서술) 적용 후 레그 0 이 되는 건: **%d**(%s)"
        % (sum(1 for t in tp_new if t[OPEN_N] and not x6_legs(t, "narr")),
           " · ".join(t[NAME] for t in tp_new if t[OPEN_N] and not x6_legs(t, "narr")) or "없음"))

    say("")
    say("### §2-2. 생략 편향 비율 — 의무 인쇄(`PREREG_POST6.md` §2-3)")
    say("")
    d9 = E9MOD.denoms(E9MOD.TRADES)
    d10 = E10MOD.denoms(E10MOD.TRADES)
    say("- **계열 연속값(`TP` 분모 · (서술))**: post4 2/4 → post5 4/6 → post6 3/9 → post7 3/7 → post8 2/4 → post9 %d/%d → post10 %d/%d → **post11 %d/%d = %.1f%%**"
        % (d9["om"], d9["tp_n"], d10["om"], d10["tp_n"], DN["om"], DN["tp_n"], ratio(DN["om"], DN["tp_n"])))
    say("- (P) 순수 문자 기준 **%d/%d = %.1f%%** · 신규 4건 분모 **%d/%d** · 🔴 약한 자리 1(광전자 「4차 매도완료 (총9차 분할매도 계획)」)를 "
        "미완결로 읽으면 완결 4 → 3 (§5 갈래)"
        % (DP["om"], DP["tp_n"], ratio(DP["om"], DP["tp_n"]), sum(1 for t in new if t[OPEN_N]), len(new)))
    say("- 동결 문언: *「생략분은 대개 뒤쪽(낮은 수익률)이라 「비증가」에 «유리한» 방향으로 편향된다」*(`RESULTS_EXIT_V2_POST5.md` §9-4) "
        "⇒ **`EXIT-E1` 의 비율을 액면대로 읽지 말 것.**")

    # ── §3 D-2 ──────────────────────────────────────────────────────────
    say("")
    say("## §3. `D-2` · `P8-형변량` — 세 수 (`PREREG_POST8.md` §2 (나) 기계 검사)")
    say("")
    say("| (i) 주 분모(`unknown` 제외) | (ii) `TP` 포함 민감도 분모 | (iii) 미등록 형 신고 줄 |")
    say("|---|---|---|")
    say("| `EXIT-E1` **%d** · `EXIT-E4` **%d** · `EXIT-X2` **%d** | `EXIT-E1` **%d** · `EXIT-E4` **%d** · `EXIT-X2` **%d** "
        "(`unknown` 0 ⇒ (i) 과 같다) | **미등록 형: %s** |"
        % (DN["e1_n"], DN["e4_n"], DN["x2_n"], DN["e1_n"], DN["e4_n"], DN["x2_n"],
           ", ".join(UNREGISTERED_FORMS) if UNREGISTERED_FORMS else "없음"))
    say("")
    say("- 🔴 (i) = (ii) 여도 **두 수를 둘 다 인쇄**한다 · 정규화 `(형, HDR수치)` 는 인테이크의 사람 판단(LABELS 동결) · "
        "형 화이트리스트 = `{%s}`." % ", ".join(sorted(FORM_WHITELIST)))
    say("- 🔴 `MIX` 1(샌즈 · 후속)은 `EXIT-E1`/`E4`/`X6`/`X2` 분모 밖(`PREREG_EXIT_V2.md:59` 「값만 기록」) — `X2`/`X8` `MIX` 확장 민감도는 §5-2 · §6 에 인쇄만.")

    # ── §4 E4 ───────────────────────────────────────────────────────────
    say("")
    say("## §4. `EXIT-E4` (반증축) — `TP` ∧ 레그 ≥3 (`EXIT-X6` 적용 후)만으로 재계산")
    say("")
    say("| 종목 | `EXIT-X6`(서술) 후 레그 | 시퀀스 | 비증가 |")
    say("|---|---|---|---|")
    for t in DN["e4"]:
        L = x6_legs(t, "narr")
        say("| %s | %d | %s | %s |" % (t[NAME], len(L), seq(L), "✅" if not nonincreasing(L) else "❌"))
    e4k, e4n = e1_ok(DN["e4"]), DN["e4_n"]
    e4pk, e4pn = e1_ok(DP["e4"], "tilde"), DP["e4_n"]
    e4xk, e4xn = e1_ok(DNX["e4"]), DNX["e4_n"]
    e4xpk, e4xpn = e1_ok(DPX["e4"], "tilde"), DPX["e4_n"]
    say("")
    say("| 갈래 | 건수 | 비증가 | 비율 | 표시 | 계수 |")
    say("|---|---|---|---|---|---|")
    say("| **(서술) 주** `TP` ∩ 레그 ≥3 | %d | %d | %.1f%% | %s | 계수 |"
        % (e4n, e4k, ratio(e4k, e4n), mark(e4k, e4n, E1_MIN, E4_MIN_N)))
    say("| (P) 민감도 갈래 | %d | %d | %.1f%% | %s | 🔴 **민감도 열** — 확인 8(주 갈래 최소 n 미달 ⇒ 여는 데 쓰지 않는다) |"
        % (e4pn, e4pk, ratio(e4pk, e4pn), mark(e4pk, e4pn, E1_MIN, E4_MIN_N)))
    say("| 후속 확장 (서술) | %d | %d | %.1f%% | — | 인쇄만(계수 안 함) |" % (e4xn, e4xk, ratio(e4xk, e4xn)))
    say("| 후속 확장 (P) | %d | %d | %.1f%% | — | 인쇄만(계수 안 함) |" % (e4xpn, e4xpk, ratio(e4xpk, e4xpn)))
    say("")
    say("- 제외된 건: %s" % (", ".join("%s(`EXIT-X6` 후 레그 %d)" % (t[NAME], len(x6_legs(t, "narr")))
                                       for t in tp_new if len(x6_legs(t, "narr")) < 3) or "없음"))
    e4wk, e4wn = e1_ok(DW["e4"]), DW["e4_n"]
    say("| 🆕 병기 `(광전자 미완결)`(`F-6`) | %d | %d | %.1f%% | %s | %s |"
        % (e4wn, e4wk, ratio(e4wk, e4wn), mark(e4wk, e4wn, E1_MIN, E4_MIN_N),
           "계수(갈림 검사)" if e4wn >= E4_MIN_N else "🔴 **인쇄만**(최소 n 미달 · `P11-최소n갈림`)"))
    say("")
    say("- ⇒ (서술) 주 n = %d %s %d ⇒ **%s** — (P) 갈래 n %d · 병기 `(광전자 미완결)` n %d%s ⇒ 최소 n 미달 경로 · 값은 인쇄만(`P11-최소n갈림` · 갈림 근거 아님)."
        % (e4n, "<" if e4n < E4_MIN_N else "≥", E4_MIN_N,
           "⛔ 최소 n 미달 — 통과로도 불통과로도 인용하지 않는다" if e4n < E4_MIN_N else
           ("✅ 통과" if e4k / e4n >= E1_MIN else "❌ 불통과"), e4pn, e4wn,
           "(둘 다 최소 n 미달)" if max(e4pn, e4wn) < E4_MIN_N else "(최소 n 을 채우지만 확인 8 로 닫힌 주 갈래를 열지 않는다)"))

    # ── §5 E2 · X2 ──────────────────────────────────────────────────────
    say("")
    say("## §5. `EXIT-E2`(병기 · 판정 아님) · `EXIT-X2`(주 판정) — 같은 표에 인쇄 (§7-C 3 의무)")
    say("")
    be_all = [t for t in TRADES if t[BE]]
    be_new = [t for t in be_all if t[NEW]]
    be_new_tp = [t for t in be_new if t[LABEL] == "TP" and not t[OPEN_N]]
    x2t = DN["x2"]
    say("🔴 **분모 충돌 신고**(`PREREG_POST6.md` §1-8 형식 · 승계) — 어느 쪽도 고치지 않는다: `EXIT-E2` = 저자가 **본전 매도**라 적은 레그"
        "(`breakeven_note` · 라벨·등록 사건 무관) **%d건** ↔ `EXIT-X2` = **신규 완결 `TP`** **%d건**." % (len(be_all), len(x2t)))
    say("")
    say("| 종목 | 구분 | 라벨 | 완결(서술) | `be_note` | 시퀀스 | `EXIT-E2`(원 시퀀스 마지막) | `EXIT-X2`(「손실률」 제외 후 마지막) | 다른가 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for t in TRADES:
        if not (t in be_all or t in DP["x2"] or t in mix):
            continue
        last = t[LEGS][-1]
        xv, _xp = x2_leg(t[LEGS], t[LOSSM])
        say("| %s | %s | `%s` | %s | %s | %s | **%s** (%s) | **%s** (%s) | %s |"
            % (t[NAME], "신규" if t[NEW] else "🔁후속", t[LABEL], "완결" if not t[OPEN_N] else "**미완결**", "1" if t[BE] else "0",
               seq(t[LEGS], t[LOSSM]), num(last), "✅" if abs(last) < BE_MAX else "❌",
               num(xv), "✅" if abs(xv) < BE_MAX else "❌", "**예**" if xv != last else "아니오"))
    say("")
    e2a_ok = sum(1 for t in be_all if abs(t[LEGS][-1]) < BE_MAX)
    e2bA_ok = sum(1 for t in be_new_tp if abs(t[LEGS][-1]) < BE_MAX)
    e2bB_ok = sum(1 for t in be_new if abs(t[LEGS][-1]) < BE_MAX)
    say("### §5-1. `EXIT-E2` — 원 동결 규칙(마지막 레그) · **병기 · 주 판정 아님** (문턱 ≥%.0f%%)" % (100 * E2_MIN))
    say("")
    say("| 분모(이번 글) | 건 | `\\|ret\\| < %.1f%%` | 비율 | 표시 |" % BE_MAX)
    say("|---|---|---|---|---|")
    say("| (가) `breakeven_note` 전건 — 🔁후속 «포함» | %d | %d | %.1f%% | %s |"
        % (len(be_all), e2a_ok, ratio(e2a_ok, len(be_all)), mark(e2a_ok, len(be_all), E2_MIN, E2_MIN_N)))
    say("| 신규만 (A) = 신규 완결 `TP` ∧ note | %d | %d | %.1f%% | %s |"
        % (len(be_new_tp), e2bA_ok, ratio(e2bA_ok, len(be_new_tp)), mark(e2bA_ok, len(be_new_tp), E2_MIN, E2_MIN_N)))
    say("| 신규만 (B) = 신규 ∧ note(라벨 무관) | %d | %d | %.1f%% | %s |"
        % (len(be_new), e2bB_ok, ratio(e2bB_ok, len(be_new)), mark(e2bB_ok, len(be_new), E2_MIN, E2_MIN_N)))
    say("")
    say("- `breakeven_note` **%d건** = %s. 신규 단독 분모는 최소 n %d %s((A) %d · (B) %d) — 두 정의 다 인쇄(post8 레인 처리 승계 · `P11-최소n갈림`)."
        % (len(be_all), " · ".join("%s(%s)" % (t[NAME], num(t[LEGS][-1])) for t in be_all), E2_MIN_N,
           "미달" if max(len(be_new_tp), len(be_new)) < E2_MIN_N else "에 닿는다", len(be_new_tp), len(be_new)))

    say("")
    say("### §5-2. `EXIT-X2` — **주 판정**(「손실률」 레그 제외 후 «원 시퀀스» 마지막) · 신규 완결 `TP` (문턱 ≥%.0f%%)" % (100 * E2_MIN))
    say("")
    say("| 종목 | 시퀀스 | `EXIT-X2` 레그 | 뒤에서 | `\\|ret\\|` | 판정 |")
    say("|---|---|---|---|---|---|")
    x2_ok, x2pos = 0, []
    for t in x2t:
        xv, xp = x2_leg(t[LEGS], t[LOSSM])
        p = abs(xv) < BE_MAX
        x2_ok += p
        x2pos.append((t[NAME], xp, len(t[LEGS]), xv, t[LEGS][-1]))
        say("| %s | %s | **%s** | %d번째 | %.2f | %s |" % (t[NAME], seq(t[LEGS], t[LOSSM]), num(xv), len(t[LEGS]) - xp,
                                                          abs(xv), "✅" if p else "❌"))
    x2_n = len(x2t)
    say("")
    say("- **`EXIT-X2` (서술) 주 = %d/%d = %.1f%%** ⇒ **%s**(`PREREG_POST6.md` §4 **#16** *「최소 n = 완결 `TP` 3」* · 판정 열림 = 구성)"
        % (x2_ok, x2_n, ratio(x2_ok, x2_n), "⛔ 보류 — 완결 `TP` %d < 3 · 통과로 인용 금지" % x2_n if x2_n < X2_MIN_N
           else ("✅ 지지" if x2_ok / x2_n >= E2_MIN else "❌ 불성립")))
    say("")
    say("#### `EXIT-X2` 갈래 (post10 #2 ⓑ 승계 · 의무 인쇄 · 최소 n 미달 갈래는 ✅·❌ 를 찍지 않는다)")
    say("")
    say("| 갈래 | 분모 | 적중 | 비율 | 표시 | 계수 |")
    say("|---|---|---|---|---|---|")
    xp_t = DP["x2"]
    xp_ok = x2_ok_of(xp_t)
    sa = [t for t in x2t if t[BE]]
    sa_ok = x2_ok_of(sa)
    wk_a = DW["x2"]                                              # 광전자만 미완결로 읽음(`F-6` 병기)
    mix_ext = x2t + [t for t in mix]
    xx_t, xxp_t = DNX["x2"], DPX["x2"]
    say("| **(서술) 주** 신규 완결 `TP` | %d | %d | %.1f%% | %s | 계수 |"
        % (x2_n, x2_ok, ratio(x2_ok, x2_n), mark(x2_ok, x2_n, E2_MIN, X2_MIN_N)))
    say("| (P) 갈래(순수 `~` 문자 기준) | %d | %d | %.1f%% | %s | post10 #2 ⓑ 승계 **계수** |"
        % (len(xp_t), xp_ok, ratio(xp_ok, len(xp_t)), mark(xp_ok, len(xp_t), E2_MIN, X2_MIN_N)))
    say("| 🆕 병기 `(%s 미완결)`(`F-6` · 🔒 #1 ✅ A) | %d | %d | %.1f%% | %s | 🔒 #1 ✅ A **계수**(분모 3 ≥ 3) |"
        % (WEAK_ONLY[0].split()[0], len(wk_a), x2_ok_of(wk_a), ratio(x2_ok_of(wk_a), len(wk_a)), mark(x2_ok_of(wk_a), len(wk_a), E2_MIN, X2_MIN_N)))
    say("| 좁은 분모 = 신규 완결 `TP` ∧ `be_note` | %d | %d | %.1f%% | %s | post10 #2-보충 승계 **계수** |"
        % (len(sa), sa_ok, ratio(sa_ok, len(sa)), mark(sa_ok, len(sa), E2_MIN, X2_MIN_N) if sa else "⛔ 분모 0"))
    say("| `MIX` 확장(주 분모 + 샌즈 · 후속) | %d | %d | %.1f%% | %d/%d(판정 언어 없음) | 인쇄만 |"
        % (len(mix_ext), x2_ok_of(mix_ext), ratio(x2_ok_of(mix_ext), len(mix_ext)), x2_ok_of(mix_ext), len(mix_ext)))
    say("| 후속 확장 (서술) | %d | %d | %.1f%% | %d/%d(판정 언어 없음) | 인쇄만(계수 안 함) |"
        % (len(xx_t), x2_ok_of(xx_t), ratio(x2_ok_of(xx_t), len(xx_t)), x2_ok_of(xx_t), len(xx_t)))
    say("| 후속 확장 (P) | %d | %d | %.1f%% | %d/%d(판정 언어 없음) | 인쇄만(계수 안 함) |"
        % (len(xxp_t), x2_ok_of(xxp_t), ratio(x2_ok_of(xxp_t), len(xxp_t)), x2_ok_of(xxp_t), len(xxp_t)))
    say("")
    x2_counted = [n for n in (x2_n, len(xp_t), len(wk_a), len(sa)) if n >= X2_MIN_N]
    say("- 🔒 **`P8-갈래계수` · post10 #2 ⓑ 승계**: 최소 n(%d)을 채운 계수 갈래 = **%d개**(`PREREG_POST8.md:340-343` · 갈림은 §12 에서 센다). "
        "🔴 `MIX` 확장 · 후속 확장은 **세지 않는다** — 새 라벨(「…의존」류)을 만들지 않는다."
        % (X2_MIN_N, len(x2_counted)))

    # ── §6 X8 ───────────────────────────────────────────────────────────
    say("")
    say("## §6. `EXIT-X8` (반증축) — `EXIT-X2` 가 고른 레그 ≠ 마지막 레그인 건 수")
    say("")
    say("| 종목 | 레그 수 | `EXIT-X2` 레그 | 뒤에서 | 「마지막 레그」 규칙 | 두 규칙이 다른가 |")
    say("|---|---|---|---|---|---|")
    x8 = 0
    for nm, pos, n, xv, last in x2pos:
        d = (xv != last)
        x8 += d
        say("| %s | %d | %s | %d번째 | %s | %s |" % (nm, n, num(xv), n - pos, num(last), "예" if d else "**아니오**"))
    ext = [t for t in TRADES if t not in x2t and t[LEGS]]
    x8b = sum(1 for t in ext if x2_leg(t[LEGS], t[LOSSM])[0] != t[LEGS][-1])
    say("")
    say("- 주 분모(%d건) 안 **%d건** — 「손실률」 레그 0개 ⇒ 두 규칙이 **구성상** 같은 레그를 고른다 ⇒ **%s**(**7글 연속**) · "
        "확장 분모(%d건)에서는 **%d건**." % (x2_n, x8, "⛔ 두 규칙 구분 불가" if x8 == 0 else "두 규칙이 구분된다", x2_n + len(ext), x8 + x8b))
    say("")
    say("| `MIX` 확장 민감도(인쇄만) | 시퀀스 | `EXIT-X2` 레그 | 마지막 레그 | 두 규칙이 다른가 |")
    say("|---|---|---|---|---|")
    for t in mix:
        xv, _ = x2_leg(t[LEGS], t[LOSSM])
        say("| %s | %s | %s | %s | %s |" % (t[NAME], seq(t[LEGS], t[LOSSM]), num(xv), num(t[LEGS][-1]),
                                          "**예**" if xv != t[LEGS][-1] else "아니오"))
    say("")
    say("- 🔴 `MIX` 확장(샌즈 · 「손실률」 레그 0)에서도 두 규칙이 구분되는 건 %d/%d — 주 분모에는 「손실률」 레그가 없다 ⇒ 인쇄만 · 판정에 쓰지 않는다."
        % (sum(1 for t in mix if x2_leg(t[LEGS], t[LOSSM])[0] != t[LEGS][-1]), len(mix)))

    # ── §7 E3 / X7 · §8 X9 ─────────────────────────────────────────────
    sl = [t for t in TRADES if t[LABEL] == "SL"]
    seqs = [t for t in sl if sum(t[LOSSM]) >= 2]
    say("")
    say("## §7. `EXIT-E3` · `EXIT-X7` — `SL` 건의 손절 레그 비증가 · ⛔ **판정 불가**")
    say("")
    say("- **`SL` %d건** ⇒ 「시퀀스」 **%d** · 누적 = post6 1 + post7 0 + post8 0 + post9 0 + post10 0 + post11 %d = **%d < %d**(§4 **#19**) ⇒ **⛔ 판정 불가 유지**."
        % (len(sl), len(seqs), len(seqs), 1 + len(seqs), E3_MIN_N))
    say("- 🔴 사유 계열: post4 `SL` 0 · post5 범위만 · post6 시퀀스 1 < 3 · post7 0 · post8 0 · post9 0 · post10 0 · **post11 `SL` 0**(`MIX` 1 은 `SL` 이 아니다) — "
        "***표본이 생긴 것과 판정이 가능해진 것은 다르다.***")
    say("")
    say("## §8. `EXIT-X9` — `MANUAL` 안의 자동 사이클 (관측 · 판정 아님)")
    say("")
    say("| 갈래 | 읽기 | 이번 글 | 3건 게이트 |")
    say("|---|---|---|---|")
    say("| **주** | 한켐형 = 자동 «본전»매도 → 직접 | **%d건** · 누적 **0** | 미달 |" % X9_MAIN)
    say("| (민감도 · 넓은 독법) | 「`MANUAL` 안 자동 사이클」 | **%d건**(이번 글 `MANUAL` 0) | 미달 · post8 넓은 독법 3 은 합치지 않는다 |" % X9_BROAD)

    # ── §9 누적 ─────────────────────────────────────────────────────────
    say("")
    say("## §9. 누적 집계 — `EXIT-E1` 두 계열(B-4) · post4~post10 은 그 회차 `TRADES` 로 «다시» 셌다")
    say("")
    prior = [("4번째(2026-08-22)", recount(E4MOD.TRADES, "p4"), E7MOD.POST4),
             ("5번째(2026-08-29)", recount(E5MOD.TRADES, "p5"), E7MOD.POST5),
             ("6번째(2026-09-04)", recount(E6MOD.TRADES, "p6"), E7MOD.POST6),
             ("7번째(2026-09-12)", recount(E7MOD.TRADES, "p7"), None),
             ("8번째(2026-09-18)", recount(E8MOD.TRADES, "p7"), None),
             ("9번째(2026-09-23)", recount(E9MOD.TRADES, "p7"), None),
             ("10번째(2026-10-02)", recount(E10MOD.TRADES, "p7"), None)]
    prior_x = prior[:4] + [("8번째(2026-09-18) 「우리로 제외」",
                            recount([t for t in E8MOD.TRADES if t[NAME] != URIRO], "p7"), None), prior[5], prior[6]]
    post11 = dict(E1a=(a_ok, len(tp_new)), E1n=(e1k, e1n), E4=(e4k, e4n), E2a=(e2a_ok, len(be_all)),
                  E2b=(e2bB_ok, len(be_new)), E2bA=(e2bA_ok, len(be_new_tp)), X2=(x2_ok, x2_n), X8=(x8, x2_n))
    say("| 글 | `EXIT-E1` **(가) 전 레그** | `EXIT-E1` **(나) `X6` 적용** | `EXIT-E4` | `EXIT-E2`(후속 포함) | "
        "`EXIT-E2`(신규만 (B)) | `EXIT-X2` | `EXIT-X8` |")
    say("|---|---|---|---|---|---|---|---|")
    for nm, r, _q in prior:
        say("| %s *재계산* | %s | %s | %s | %s | %s | %s | %s |"
            % (nm, frac0(r["E1a"]), frac0(r["E1n"]), frac0(r["E4"]), frac0(r["E2a"]), frac0(r["E2b"]),
               frac0(r["X2"]) if r["X2"] else "— (동결만)", "%d/%d" % r["X8"] if r["X8"] else "—"))
    say("| **11번째(2026-10-08) 이번 (서술)** | %s | %s | %s | %s | %s | %s | %d/%d |"
        % (frac0(post11["E1a"]), frac0(post11["E1n"]), frac0(post11["E4"]), frac0(post11["E2a"]), frac0(post11["E2b"]),
           frac0(post11["X2"]), post11["X8"][0], post11["X8"][1]))

    def cum(rows_, key, extra):
        ok = sum(r[key][0] for _n, r, _q in rows_ if r[key]) + extra[0]
        n = sum(r[key][1] for _n, r, _q in rows_ if r[key]) + extra[1]
        return ok, n

    c = {k: cum(prior, k, post11[k]) for k in ("E1a", "E1n", "E4", "E2a", "E2b", "X2", "X8")}
    cx = {k: cum(prior_x, k, post11[k]) for k in ("E1a", "E1n", "E4", "E2a", "E2b", "X2")}
    say("| **누적 (가)** | **%s** | **%s** | **%s** | **%s** | **%s** | **%s** | **%d/%d** |"
        % (frac(c["E1a"]), frac(c["E1n"]), frac(c["E4"]), frac(c["E2a"]), frac(c["E2b"]), frac(c["X2"]), c["X8"][0], c["X8"][1]))
    say("| 누적 「post8 우리로 제외」(확인 7) | %s | %s | %s | %s | %s | %s | — |"
        % (frac(cx["E1a"]), frac(cx["E1n"]), frac(cx["E4"]), frac(cx["E2a"]), frac(cx["E2b"]), frac(cx["X2"])))
    say("")
    say("#### §9-0. 재계산 ↔ 동결 인용값 대조 (옮겨 적지 않았다는 증거 · 판정에 쓰지 않는다)")
    say("")
    say("| 글 | 항목 | 재계산 | 동결 인용값 | 일치 |")
    say("|---|---|---|---|---|")
    keymap = {"4번째(2026-08-22)": [("E1a", "E1_ok", "E1_n"), ("E4", "E4_ok", "E4_n"), ("E2a", "E2_ok", "E2_n")],
              "5번째(2026-08-29)": [("E1a", "E1_ok", "E1_n"), ("E4", "E4_ok", "E4_n"), ("E2a", "E2_ok", "E2_n"),
                                   ("X2", "X2_ok", "X2_n")],
              "6번째(2026-09-04)": [("E1a", "E1a_ok", "E1a_n"), ("E1n", "E1_ok", "E1_n"), ("E4", "E4_ok", "E4_n"),
                                   ("E2a", "E2a_ok", "E2a_n"), ("E2b", "E2b_ok", "E2b_n"), ("X2", "X2_ok", "X2_n")]}
    n_bad = 0
    for nm, r, q in prior:
        if q is None:
            continue
        for k, qk, qn in keymap[nm]:
            same = tuple(r[k]) == (q[qk], q[qn])
            n_bad += (not same)
            say("| %s | `%s` | %d/%d | %d/%d | %s |" % (nm, k, r[k][0], r[k][1], q[qk], q[qn], "✅" if same else "🔴 불일치"))
    r7, r8, r9, r10 = prior[3][1], prior[4][1], prior[5][1], prior[6][1]
    row7 = ("| **7번째(2026-09-12 발행) 이번** | %s | %s | %s | %s | %s | %s | %d/%d |"
            % (frac(r7["E1a"]), frac(r7["E1n"]), frac(r7["E4"]), frac(r7["E2a"]), frac(r7["E2b"]), frac(r7["X2"]),
               r7["X8"][0], r7["X8"][1]))
    row8 = ("| **8번째(2026-09-18) 이번 (가)** | %s | %s | %s | %s | (A) %s · (B) %s | %s | %d/%d |"
            % (frac(r8["E1a"]), frac(r8["E1n"]), frac(r8["E4"]), frac(r8["E2a"]), frac(r8["E2bA"]), frac(r8["E2b"]),
               frac(r8["X2"]), r8["X8"][0], r8["X8"][1]))
    row9 = ("| **9번째(2026-09-23) 이번 (서술)** | %s | %s | %s | %s | %s | %s | %d/%d |"
            % (frac0(r9["E1a"]), frac0(r9["E1n"]), frac0(r9["E4"]), frac0(r9["E2a"]), frac0(r9["E2b"]), frac0(r9["X2"]),
               r9["X8"][0], r9["X8"][1]))
    row10 = ("| **10번째(2026-10-02) 이번 (서술)** | %s | %s | %s | %s | %s | %s | %d/%d |"
             % (frac0(r10["E1a"]), frac0(r10["E1n"]), frac0(r10["E4"]), frac0(r10["E2a"]), frac0(r10["E2b"]), frac0(r10["X2"]),
                r10["X8"][0], r10["X8"][1]))
    for lbl, row_, fn in (("7번째(2026-09-12)", row7, "RESULTS_EXIT_V2_POST7_NUMBERS.md"),
                          ("8번째(2026-09-18)", row8, "RESULTS_EXIT_V2_POST8_NUMBERS.md"),
                          ("9번째(2026-09-23)", row9, "RESULTS_EXIT_V2_POST9_NUMBERS.md"),
                          ("10번째(2026-10-02)", row10, "RESULTS_EXIT_V2_POST10_NUMBERS.md")):
        pth = BASE / fn
        hit = pth.exists() and row_ in pth.read_text(encoding="utf-8").splitlines()
        n_bad += (not hit)
        say("| %s | 행 전체 | (그 회차 `TRADES` 재계산 행) | `%s` §9 「… 이번」 행 | %s |" % (lbl, fn, "✅ 축자 일치" if hit else "🔴 불일치"))
    say("")
    say("- ⇒ 재계산 불일치 **%d건** — %s" % (n_bad, "옛 회차 값은 그 회차 `TRADES` 로 다시 세도 동결 인용값과 같다(소급 = 탐색 · 옛 판정 불변)."
                                           if n_bad == 0 else "🔴 불일치를 그대로 적는다(옛 판정은 바꾸지 않는다)."))
    say("")
    say("### §9-1. `EXIT-E1` 누적 — **두 줄을 항상 같이 적는다**(B-4) · 「post8 우리로 제외」 갈래(확인 7)")
    say("")
    ga, na = c["E1a"], c["E1n"]
    say("- **(가) 전 레그 계열** = **%s** ⇒ **%s** · 「post8 우리로 제외」 %s"
        % (frac(ga), "✅ 지지" if ga[0] / ga[1] >= E1_MIN else "❌ 불성립", frac(cx["E1a"])))
    say("- **(나) `EXIT-X6` 적용 계열** = **%s** ⇒ **%s** · 「post8 우리로 제외」 %s"
        % (frac(na), "✅ 지지" if na[0] / na[1] >= E1_MIN else "❌ 불성립", frac(cx["E1n"])))
    split_e1 = (ga[0] / ga[1] >= E1_MIN) != (na[0] / na[1] >= E1_MIN)
    split_x = any((c[k][0] / c[k][1] >= E1_MIN) != (cx[k][0] / cx[k][1] >= E1_MIN) for k in ("E1a", "E1n"))
    say("- ⇒ %s" % ("🔴🔴 **⛔ 「누적 정의 의존」** — 두 줄이 90%% 문턱을 사이에 두고 갈린다." if split_e1 else
                    "🟢 **두 줄이 문턱을 사이에 두고 갈리지 «않는다»** ⇒ 「누적 정의 의존」 **미발동**"))
    say("- ⇒ 「post8 우리로 제외」 갈래(확인 7 · 두 갈래가 최소 n 을 채우고 갈리면 [갈래 의존]): %s"
        % ("🔴 **갈린다**" if split_x else "**갈리지 않는다**"))
    e2c, e2cx = c["E2a"], cx["E2a"]
    say("- 누적 `EXIT-E4` **%s** · 누적 `EXIT-E2` (가) **%s** ⇒ **%s**(「post8 우리로 제외」 %s ⇒ %s) · "
        "누적 `EXIT-E2` 신규만 (B) **%s** · 누적 `EXIT-X2` **%s**(기록 — X2 판정은 글 단위 #16) · 누적 `EXIT-X8` **%d/%d** ⇒ %s"
        % (frac(c["E4"]), frac(e2c), "❌ 불성립 — 8글 연속" if e2c[0] / e2c[1] < E2_MIN else "지지",
           frac(e2cx), "❌" if e2cx[0] / e2cx[1] < E2_MIN else "✅", frac(c["E2b"]),
           frac(c["X2"]), c["X8"][0], c["X8"][1], "⛔ 구분 불가" if c["X8"][0] == 0 else "구분 가능"))

    # ── §10 연결 시퀀스 ─────────────────────────────────────────────────
    say("")
    say("## §10. 연결 시퀀스 — 🔁후속 5건 (PD-2 4 · **기록만** · 어떤 판정에도 안 쓴다)")
    say("")
    say("| 건 | 직전 글 시퀀스(그 글 판 `TRADES`) | 직전 마지막 | post11 첫 | 연결 |")
    say("|---|---|---|---|---|")
    n_up = 0
    for t in foll:
        src, nm_src = FOLLOW_SRC[t[NAME]]
        prev = next(x for x in src if x[NAME] == nm_src)[LEGS]
        delta = t[LEGS][0] - prev[-1]
        n_up += delta > 0
        say("| %s | [%s] | %s | %s | %s |"
            % (t[NAME], seq(prev), num(prev[-1]), num(t[LEGS][0]),
               "감소 ✅" if delta <= 0 else "🔴 **+%.2f%%p 증가**" % delta))
    say("")
    say("- 🔴 **후속 연결 지점 증가 %d/%d 관측** — 원인은 해석하지 않는다(판정 안 씀 · 🔑 저자가 매도 차수 번호를 이어 적었다 "
        "· INTAKE §2 3). 🔴 이 증가는 **글 경계**에 있다 — §2 의 「위반」은 글 안 관측이다." % (n_up, len(foll)))

    # ── §11 RANGE_ONLY ─────────────────────────────────────────────────
    say("")
    say("## §11. `RANGE_ONLY` 규약")
    say("")
    say("- 🟢 **이번 글 해당 %d건.** `~` 7개는 레그 표지 1(샌즈 값 줄 끝) · 그 밖은 차수·날짜 표기 — 「A%% ~ B%%」 형 수익률 범위가 아니다."
        % sum(1 for t in TRADES if t[RANGE]))

    # ── §12 D-5 ─────────────────────────────────────────────────────────
    say("")
    say("## §12. `D-5` · `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)` (`PREREG_POST8.md` §5 (나) 2 · PD-23 `EXIT-` 행 · post10 #2 ⓑ 승계)")
    say("")
    say("최소 n = 그 축의 동결값 그대로(`TP` 3 · E4 3 · E2 3 · X2 완결 `TP` 3). 최소 n 을 채운 «계수» 갈래만 「답」으로 센다. "
        "2 이상이 갈리면 [갈래 의존] · 1개면 그 답 · 0개면 규약 3번째 줄. 계수 여부는 결정(post9 #4 선례 · 🔒 #1 ✅ A)이 정한다(아래 계수 칸).")
    say("")
    say("| 축 | 갈래 | n | 답 | 계수 |")
    say("|---|---|---|---|---|")

    e1_main_ok = e1n >= TP_MIN_N
    e4_main_ok = e4n >= E4_MIN_N
    ct = "인쇄만(계수 안 함)"
    rows_d5 = [
        ("`EXIT-E1`", "(서술) 주", e1n, ans(e1k, e1n, E1_MIN, TP_MIN_N), e1_main_ok, "계수"),
        ("`EXIT-E1`", "(P) 민감도 갈래", e1pn, ans(e1pk, e1pn, E1_MIN, TP_MIN_N), e1_main_ok and e1pn >= TP_MIN_N,
         "계수(확인 8 · 주·(P) 둘 다 최소 n ⇒ 갈림 검사)"),
        ("`EXIT-E1`", "병기 `(광전자 미완결)`", e1wn, ans(e1wk, e1wn, E1_MIN, TP_MIN_N), e1_main_ok and e1wn >= TP_MIN_N,
         "계수(🆕 `F-6` 병기 · 주·병기 둘 다 최소 n ⇒ 갈림 검사)"),
        ("`EXIT-E1`", "후속 확장 (서술)", e1xn, ans(e1xk, e1xn, E1_MIN, TP_MIN_N), False, ct),
        ("`EXIT-E4`", "(서술) 주", e4n, ans(e4k, e4n, E1_MIN, E4_MIN_N), e4_main_ok, "계수"),
        ("`EXIT-E4`", "(P) 민감도 갈래", e4pn, ans(e4pk, e4pn, E1_MIN, E4_MIN_N), e4_main_ok and e4pn >= E4_MIN_N,
         "민감도 열(확인 8 · 주 갈래 최소 n 미달 ⇒ 여는 데 쓰지 않는다)" if not e4_main_ok else "계수(갈림 검사)"),
        ("`EXIT-E4`", "병기 `(광전자 미완결)`", e4wn, ans(e4wk, e4wn, E1_MIN, E4_MIN_N), e4wn >= E4_MIN_N,
         "계수(갈림 검사)" if e4wn >= E4_MIN_N else "인쇄만(최소 n 미달 · `P11-최소n갈림`)"),
        ("`EXIT-E4`", "후속 확장 (서술)", e4xn, ans(e4xk, e4xn, E1_MIN, E4_MIN_N), False, ct),
        ("`EXIT-E4`", "후속 확장 (P)", e4xpn, ans(e4xpk, e4xpn, E1_MIN, E4_MIN_N), False, ct),
        ("`EXIT-X2`", "(서술) 주", x2_n, ans(x2_ok, x2_n, E2_MIN, X2_MIN_N), x2_n >= X2_MIN_N, "계수"),
        ("`EXIT-X2`", "(P) 갈래", len(xp_t), ans(xp_ok, len(xp_t), E2_MIN, X2_MIN_N), len(xp_t) >= X2_MIN_N,
         "계수(post10 #2 ⓑ 승계)"),
        ("`EXIT-X2`", "병기 `(%s 미완결)`" % WEAK_ONLY[0].split()[0], len(wk_a),
         ans(x2_ok_of(wk_a), len(wk_a), E2_MIN, X2_MIN_N), len(wk_a) >= X2_MIN_N, "계수(🔒 #1 ✅ A · `F-6`)"),
        ("`EXIT-X2`", "좁은 분모(완결 `TP` ∧ note)", len(sa), ans(sa_ok, len(sa), E2_MIN, X2_MIN_N) if sa else "0/0 — 분모 0(답 없음)",
         len(sa) >= X2_MIN_N, "계수(post10 #2-보충 승계)"),
        ("`EXIT-X2`", "`MIX` 확장", len(mix_ext), ans(x2_ok_of(mix_ext), len(mix_ext), E2_MIN, X2_MIN_N), False, ct),
        ("`EXIT-X2`", "후속 확장 (서술)", len(xx_t), ans(x2_ok_of(xx_t), len(xx_t), E2_MIN, X2_MIN_N), False, ct),
        ("`EXIT-X2`", "후속 확장 (P)", len(xxp_t), ans(x2_ok_of(xxp_t), len(xxp_t), E2_MIN, X2_MIN_N), False, ct),
        ("`EXIT-E2` 누적", "(가) 후속 포함", e2c[1], ans(e2c[0], e2c[1], E2_MIN, E2_MIN_N), e2c[1] >= E2_MIN_N, "계수"),
        ("`EXIT-E2` 누적", "「post8 우리로 제외」(확인 7)", e2cx[1], ans(e2cx[0], e2cx[1], E2_MIN, E2_MIN_N),
         e2cx[1] >= E2_MIN_N, "계수"),
        ("`EXIT-E2`", "신규만 (A) 완결 `TP` ∧ note(이번 글)", len(be_new_tp), "0/0 — 분모 0(답 없음)" if not be_new_tp
         else ans(e2bA_ok, len(be_new_tp), E2_MIN, E2_MIN_N), len(be_new_tp) >= E2_MIN_N, "계수"),
        ("`EXIT-E2`", "신규만 (B) 신규 ∧ note(이번 글)", len(be_new), "0/0 — 분모 0(답 없음)" if not be_new
         else ans(e2bB_ok, len(be_new), E2_MIN, E2_MIN_N), len(be_new) >= E2_MIN_N, "계수"),
    ]
    for ax, br_, n, a_, cnt, how in rows_d5:
        say("| %s | %s | %d | %s | %s |" % (ax, br_, n, a_, how if cnt or not how.startswith("계수") else "계수 대상이나 최소 n 미달"))
    say("| `EXIT-X9` | 한켐형 / 넓은 독법 | %d / %d | 관측(최소 n 없음) | 계수 대상 밖 |" % (X9_MAIN, X9_BROAD))
    say("")
    for ax in ("`EXIT-E1`", "`EXIT-E4`", "`EXIT-X2`"):
        got = [(br_, a_) for a_x, br_, n, a_, cnt, _h in rows_d5 if a_x == ax and cnt]
        kinds = {a_.split()[-1] for _b, a_ in got}
        say("- %s: 최소 n 을 채운 계수 갈래 **%d개** ⇒ %s"
            % (ax, len(got), "0개 — 규약 3번째 줄(답 없음 · 최소 n 미달 경로)" if not got else
               ("1개 — 그 갈래의 답(%s)" % got[0][1] if len(got) == 1 else
                ("전부 같은 답(%s) — **갈리지 않는다**" % next(iter(kinds)) if len(kinds) == 1 else "🔴 **갈린다** — [갈래 의존]"))))
    e2got = [a_ for a_x, br_, n, a_, cnt, _h in rows_d5 if a_x.startswith("`EXIT-E2`") and cnt]
    e2k = {a_.split()[-1] for a_ in e2got}
    say("- `EXIT-E2`(병기 축 · 판정 아님): 최소 n 을 채운 계수 갈래 **%d개** ⇒ %s"
        % (len(e2got), ("전부 같은 답(%s) — 갈리지 않는다" % next(iter(e2k))) if len(e2k) == 1 else "🔴 갈린다"))
    say("")
    say("### §12-2. 🔴 충돌 신고 두 줄 (`PREREG_POST6.md` §1-8 형식 · INTAKE §5 `EXIT-` 행)")
    say("")
    say("1. **후속 확장 갈래 — post7 셈 ↔ post8 안 셈**: post7 레인은 「(b) 🔁후속 포함」을 최소 n 을 채운 갈래로 셌다"
        "(`RESULTS_EXIT_V2_POST7.md:214`·`:216`) ↔ post8 레인은 *「동결 적용 대상 «밖» · 계수 대상 아님」*(`RESULTS_EXIT_V2_POST8.md:114`) "
        "⇒ post9 #4-다 ⓐ · post10 #2(PD-44) · post11 = **계수 안 함**(`PREREG_EXIT_V2.md:55` 「다음 글의 **신규 건**에만」). 이번 글 후속 확장 (서술) n 은 "
        "X2 **%d** · E4 **%d** · E1 **%d** — 인쇄만."
        % (len(xx_t), e4xn, e1xn))
    say("2. **§1-8 문자 ↔ post6 PD-4**: 동결 PREREG 문자 `PREREG_POST6.md:351` 「미완결(`~`) 건」은 (P) 를, post6 PD-4 "
        "(`PREDECISION_2026-09-04_post6.md:90` — (서술) 주 · `~` 문자 기준은 민감도) 선례는 (서술)을 가리킨다 ⇒ `E1`·`E4` = post9 #4 선례(확인 8) · "
        "`X2` = 🔒 #1 ✅ A(D-5 대로 (서술)·(P)·병기 `(광전자 미완결)` 계수). (P) 를 «주»로 바꾸는 것은 규칙 변경(새 동결)이다.")
    say("")
    say("### §12-1. `D-3` 신고 줄 · `P9-공통독법` 신고 줄 · `F-3` 신고 줄 — 🔴 **이 축은 `D-3`·`P9-` 대상이 아니다**(형식만 인쇄)")
    say("")
    say("「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 E1 %d · E4 %d · X2 %d / `approx` 포함 분모 E1 %d · E4 %d · X2 %d」 — "
        "`EXIT-` 분모는 등록일 정밀도로 정의되지 않는다(`PREREG_EXIT_V2.md:55`) · 이번 글 신규 4건 전부 `exact` 라 두 분모가 같다."
        % (DN["e1_n"], DN["e4_n"], DN["x2_n"], DN["e1_n"], DN["e4_n"], DN["x2_n"]))
    say("")
    say("*「`P9-공통독법`: 답 = 판정 · (나)4 결과 = 대상 없음(`EXIT-` 는 `D-3` 목록 밖 · 이번 글 `approx` 0)」*")
    say("")
    say("*「`P10-기업행위봉`: 예(보수) · 봉을 읽지 않음 · 신고 줄 PD-36 인용 **0/%d** — 이 축은 봉 값을 읽지 않는다(창 줄 없음 ⇒ 집계할 봉 0 · 새 집계 0) · "
        "인테이크 예고 ⓐ 1/4(한국첨단소재 `split` 08-06)는 `SEL-`·`S5` 레인이 계산한 값이며 이 축의 값을 바꾸지 않는다 · `adj_factor` 산술 0 · 처리 = (나)」*"
        % len(new))
    say("*「`P11-최소n갈림`: 최소 n 미달 갈래(E4 (P)·병기 · X2 좁은 분모·후속 확장 등)는 `(갈래 이름, n, 답)` 으로 «인쇄만» 하고 갈림 근거로 세지 않는다」*")
    say("- 「기업행위 건 제외」 갈래(`F-3` (나) · 항등): `EXIT-E1` (서술) n %d · `EXIT-E4` (서술) n %d · `EXIT-X2` (서술) n %d — "
        "답(참고) · 세지 않는다(이 축은 봉을 읽지 않으므로 k = 0 ⇒ 주 갈래와 같은 표본 · 판정 불변)." % (e1n, e4n, x2_n))

    # ── §13 한계 ────────────────────────────────────────────────────────
    say("")
    say("## §13. 미리 적어두는 한계 (승계 + 이번 회차 고유)")
    say("")
    say("1. 🔴 **ε = %g%%p 가 8글 연속 사용 0회**(글 안) — 이 대역이 실제로 필요한 적이 아직 없다. 고치지 않는다." % EPS)
    say("2. 🔴 **생략 편향** — `TP` 신규 %d건 중 %d건이 (서술) 미완결이다. 「비증가」에 «유리한» 방향이다 · 저자 선택 규칙"
        "(「일부라도 매도된 종목」 · PD-32)도 «매도가 난» 건만 표본으로 만든다." % (DN["tp_n"], DN["om"]))
    say("3. 🔴 **`EXIT-X2` 반증축(`X8`)이 7글 연속 「구분 불가」** — 주 분모에 「손실률」 레그가 0개다(`MIX` 확장 샌즈도 「손실률」 레그 0 ⇒ 구분 불가).")
    say("4. 🔴 **`EXIT-E3` ⛔**(`SL` 0 · 누적 1 < 3).")
    say("5. 🔴 **저자가 레그별 시각·수량을 안 적는다** — 「시퀀스 순서 = 체결 순서」는 가정이다. 제도 경계(09-14) 전후·시간외 여부는 원문에 없다.")
    say("6. 🔴 **후속 연결 지점 증가 %d/%d**(§10) — 체결 차수 서술 연결(INTAKE §2 3)이 겹친다 · 원인 해석 안 함." % (n_up, len(foll)))
    say("7. 🔴 **값 개수 ≠ 서술 차수**(샌즈 5 ↔ 1+2~4차 · 한컴 6 ↔ 1+2~4차 · 한국첨단소재 6 ↔ 1~4차) · 동률 17.60 ×3 — 원문 값 그대로 레그(확인 3).")
    say("8. 🔴 **약한 자리 1**(광전자 「4차 매도완료 (총9차 분할매도 계획)」 · `F-6`) — 「보유 중」 부재 ⇒ 주 독법 완결. 병기 갈래 `(광전자 미완결)` 을 §4 · §5-2 · §12 에 인쇄했다.")
    say("9. 🔴 **프로그램 버전 `1.0.44`** — 이 산출물은 버전을 공변량으로 쓰지 않는다(`D-8` 해당 없음).")
    say("10. 이 분석은 **라이브 채택 대상이 아니다**(`PREREG_POST10.md` §0-1 문언 그대로 승계).")
    say("")
    say("[[LABELS_2026-10-08_post11]] · [[INTAKE_2026-10-08_post11]] · [[PREDECISION_2026-10-08_post11]] · [[PREREG_POST11]] · "
        "[[PREREG_POST9]] · [[PREREG_POST8]] · [[PREREG_POST6]] · [[PREREG_EXIT_V2]] · [[RESULTS_EXIT_V2_POST10]]")

    numbers.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())

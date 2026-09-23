# -*- coding: utf-8 -*-
"""`PREREG_EXIT_V2.md` §3 + `PREREG_POST6.md` §2-3(X5~X9 재동결) 실행 — 8번째 글.

`run_exit_v2_post7.py` 승계. 라벨·완결 여부·시퀀스는 **계산 «전»에** 동결된
`LABELS_2026-09-18_post8.md` · `INTAKE_2026-09-18_post8.md` §1 에서 «그대로» 옮긴다
(`TP` 6 · `MANUAL` 3 · `MIX` 1 · `SL` 0 · `unknown` 0 · 원장 `ledger_trades.csv`/`ledger_legs.csv` `b302f7f` 와 같은 값).
「손실률」로 적힌 레그는 저자 낱말 그대로 `loss_mask` 에 표시한다(`EXIT-X2` 가 이걸 쓴다).

준거(동결 · 규칙 변경 0):
  · `PREREG_EXIT_V2.md` §2 판별표(`:41-46`) · §3 E1~E4 · §3 B-4(E1 누적 두 계열 · post7 부터 구속) · §4 한계
  · `PREREG_POST6.md` §1-1(`MIX` 불확장) · §1-8(X6 적용 범위 = E1·E4 · X2 「마지막」 = 원 시퀀스) · §2-3(X5~X9) ·
    §4 #13~#20(최소 n: `TP` 3 · E4 3 · E2 3 · X2 완결 `TP` 3 · E3 `SL` 시퀀스 3)
  · `PREREG_POST8.md`(동결 `04cd785`) 🆕 첫 구속: `D-2`(§2 `P8-형변량` · 세 수) · `D-5`(§5 `P8-갈래계수`)
  · `PREDECISION_2026-09-18_post8.md` PD-2(후속 3건 = 「신규 건에만」 `PREREG_EXIT_V2.md:55` 로 E1/E4/X2 밖 · 연결 지점)
    · PD-5(미완결 = 서술 기준 · `~` 불일치 2번째 · `~` 5개 중 레그 표지 1) · PD-7(라벨 · 🔒 #1-b 우리로 = (가) 포함 +
    「우리로 제외」 갈래) · PD-10(표기 특이) · PD-18(`RANGE_ONLY` 0) · PD-20(D-2) · PD-23(D-5 `EXIT-` 행)

🔴 **통계 핵과 표기 함수는 `run_exit_v2_post6.py` 에서 «그대로» import 한다**(새 코드 0줄 원칙) —
   `EPS`·`E1_MIN`·`E2_MIN`·`BE_MAX`·`nonincreasing`·`eps_pairs`·`num`·`seq`·`x2_leg`·`x6_legs`·`ratio`.
   `TRADES` 튜플은 **앞 9열을 post6·post7 과 같은 순서로** 둔다(10번째 `PRESET` = `(형, HDR수치)` 정규화 표기).
   post4~post7 판(`run_exit_v2_post{4,5,6,7}.py`)은 **import 만** 한다 — 그 `TRADES` 로 옛 회차 값을 **다시 센다**
   (옮겨 적지 않는다 · 동결 인용값과 대조만 한다). ⇒ 옛 스크립트는 **한 글자도 고치지 않는다**.

DB 를 읽지 않는다(저자 서술만) ⇒ 결정적이고 DB 스냅샷에 의존하지 않는다. 시드 불필요. 라이브 트리 import 0건.

🔴 **이번 회차의 갈림**(계산 «전» 고정 · 전부 승계):
  1. **우리로 = 한 항목 · 두 사이클**(post5 한켐 A-9 이후 두 번째) — 🔒 #1-b 사장님 채택 **(가)**: 주 = 포함 +
     「항목 내 2 사이클」 표시 + **「우리로 제외」 갈래를 전 항목에 인쇄**(판정 효과 있음 — (i) 준용의 귀결 · PD-7).
  2. **`TP` 라벨 후속이 계열 처음 2건**(빛과전자·범한퓨얼셀) — 라벨이 아니라 `PREREG_EXIT_V2.md:55` 「다음 글의
     **신규 건**에만」으로 E1/E4/X2 주 분모 밖 · E2 누적은 범한퓨얼셀 포함(라벨·등록 무관 · PD-2 3).
  3. **`P8-형변량`**: `(표준형, 60)` 9 · `(표준형, 없음)` 1(코데즈 「사분위수, 표준형」) ⇒ `unknown` 0 · 「미등록 형: 없음」.
  4. **`~` 와 서술 불일치 2번째**(우리로 `0.54% ~` ∧ 「전량매도 … 분할매도 완료」) — 주 = 서술 기준(완결) ·
     `~` 기준 = 민감도(표기 의존 갈래) · 그 레그만 `leg_open_ended = 1`.

🔴 이 산출물은 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1).
🔴 이 스크립트는 **새 예측을 만들지 않는다**(`PREREG_POST6.md` §7-B #11) · 새 라벨(「…의존」류)을 만들지 않는다 ·
   등급 이름을 적지 않는다(`INTAKE_2026-09-18_post8.md` §6 단계).
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
    eps_pairs,
    nonincreasing,
    num,
    ratio,
    seq,
    x2_leg,
    x6_legs,
)
# 🔴 옛 회차 판 — **import 만**(재계산 입력 · 동결 인용값 대조용). 한 글자도 고치지 않는다.
import run_exit_v2_post4 as E4MOD
import run_exit_v2_post5 as E5MOD
import run_exit_v2_post6 as E6MOD
import run_exit_v2_post7 as E7MOD

BASE = Path(__file__).resolve().parent
OUT: list = []

# 최소 n — `PREREG_POST6.md` §4 (동결값 그대로 · 이 파일이 만든 문턱이 아니다)
TP_MIN_N = 3      # #13 `EXIT-E1`/`X5` — `TP` 3 (`PREREG_EXIT_V2.md:55`)
E4_MIN_N = 3      # #14
E2_MIN_N = 3      # #15
X2_MIN_N = 3      # #16 — 완결 `TP` 3 (⚠️ #15 와 «다른 행»)
E3_MIN_N = 3      # #19 — `SL` 시퀀스 3

# 🔴 창 종료 규약 — 이 레인은 DB 를 읽지 않으므로 «표기 의무»로만 쓴다(PD-1 8번).
DB_UPTO = "2026-09-18"
PUB_DATE = "2026-09-18"          # 발행 2026-09-18(금) = 거래일 ⇒ 발행 당일 봉 포함
ADMIN_DBMAX = ("2026-09-23", "2,764")   # 관리자 실측(2026-09-24 00:07:44 KST · `p8_lane_common.md` §3) — 인용

# ── 표본 (계산 «전» 동결분 그대로 · `INTAKE_2026-09-18_post8.md` §1 순서 · `LABELS_2026-09-18_post8.md`) ──
# (종목, 라벨, 레그, 「손실률」마스크, 서술기준 미완결, `~` 문자, breakeven_note, 신규, 범위만, `(형, HDR)`)
# 🔴 앞 9열은 post6·post7 과 «같은 순서»다 — import 한 `x6_legs`·`x2_leg` 가 그 인덱스를 쓴다.
URIRO = "우리로 🔀2사이클"
TRADES = [
    ("빛과전자 🔁후속",       "TP",     [23.47, 17.88],
     [0, 0],             False, False, False, False, False, "(표준형, 60)"),
    ("로보티즈 🔁후속",       "MANUAL", [17.95, 16.74],
     [0, 0],             False, False, False, False, False, "(표준형, 60)"),
    (URIRO,                   "TP",     [24.20, 19.94, 17.00, 16.26, 13.32, 12.44, 0.54],
     [0] * 7,            False, True,  True,  True,  False, "(표준형, 60) × 2(사이클 2 「기존 셋팅동일」)"),
    ("범한퓨얼셀 🔁후속",     "TP",     [20.99, 20.99, 0.43],
     [0, 0, 0],          False, False, True,  False, False, "(표준형, 60)"),
    ("원익 🔂재진입",         "MANUAL", [19.49, 17.61, 15.54, 13.14],
     [0] * 4,            False, False, False, True,  False, "(표준형, 60)"),
    ("JW신약",                "MANUAL", [16.28, 12.68, 11.05, 10.78],
     [0] * 4,            False, False, False, True,  False, "(표준형, 60)"),
    ("헥토파이낸셜 🔂재진입", "MIX",    [5.84, 2.98, 1.39, -2.28],
     [0, 0, 0, 1],       False, False, True,  True,  False, "(표준형, 60)"),
    ("액스비스",              "TP",     [11.64, 0.31],
     [0, 0],             False, False, True,  True,  False, "(표준형, 60)"),
    ("코데즈컴바인 🔂재진입", "TP",     [13.20, 11.05, 11.03, 8.71, 6.59],
     [0] * 5,            True,  False, False, True,  False, "(표준형, 없음) — 「사분위수, 표준형」"),
    ("우리기술",              "TP",     [8.47, 8.47, 8.23, 4.75],
     [0] * 4,            True,  False, False, True,  False, "(표준형, 60)"),
]

NAME, LABEL, LEGS, LOSSM, OPEN_N, TILDE, BE, NEW, RANGE, PRESET = range(10)

# 🔴 `P8-형변량`(`PREREG_POST8.md` §2) — 형 화이트리스트 = {표준형} · 정규화는 «인테이크의 사람 판단»(LABELS 동결)
FORM_WHITELIST = {"표준형"}
UNREGISTERED_FORMS: list = []          # 10/10 형 = 「표준형」 ⇒ 없음 (LABELS · PD-20)

# 🔴 `leg_open_ended` — 레그 «단위» 표기(PD-5 1번 · 원장 `ledger_legs.csv` 와 같은 값)
LEG_OPEN_ENDED = {URIRO: 0.54, "코데즈컴바인 🔂재진입": 6.59, "우리기술": 4.75}
# 🔴 `~` 정규식 함정(PD-5 2번) — 본문 `~` 5개 중 레그 표지는 우리로 1개뿐
TILDE_TRAP = "코데즈·우리기술 「1~4차」(차수 표기) · 산문 「상반기~하반기」·「2,000~3,000건」"

# 🔴 후속 3건의 post7 행(연결 시퀀스 «기록만» · PD-2 4번) — post7 판 `TRADES` 이름으로 찾아 쓴다(옮겨 적지 않는다)
FOLLOW_MAP = {"빛과전자 🔁후속": "빛과전자 🔂재진입", "로보티즈 🔁후속": "로보티즈", "범한퓨얼셀 🔁후속": "범한퓨얼셀"}
# 🔴 `EXIT-X9`(`PREDECISION_2026-09-18_post8.md` PD-7) — 주 = 한켐형(자동 «본전»매도 → 직접) 0 / 넓은 독법 3
X9_MAIN, X9_BROAD = 0, 3


def say(s=""):
    print(s)
    OUT.append(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def denoms(trades, excl=(), basis="narr"):
    """갈래별 분모 — 동결 문언이 지시하는 분모를 «정의로» 만든다(값을 보고 고르지 않는다).

      · `EXIT-E1`  = 신규 ∧ `TP` ∧ (`EXIT-X6` 적용 후 레그 >= 1)
      · `EXIT-E4`  = 신규 ∧ `TP` ∧ (`EXIT-X6` 적용 후 레그 >= 3)
      · `EXIT-X2`  = 신규 ∧ `TP` ∧ 완결 — basis='narr' 서술 기준(주) · 'tilde' `~` 기준(표기 의존 갈래)
      · 생략 편향 = 신규 ∧ `TP` 중 미완결 건 / `TP` 분모
    excl = 갈래에서 빼는 종목 이름(「우리로 제외」). `unknown` 은 post8 에 0건이라 `TP` 포함 갈래 = 주 갈래다.
    """
    open_idx = OPEN_N if basis == "narr" else TILDE
    tp_new = [t for t in trades if t[NEW] and t[LABEL] == "TP" and t[NAME] not in excl]
    e1 = [t for t in tp_new if x6_legs(t, basis)]
    e4 = [t for t in tp_new if len(x6_legs(t, basis)) >= 3]
    x2 = [t for t in tp_new if not t[open_idx]]
    return dict(tp_new=tp_new, e1=e1, e4=e4, x2=x2, tp_n=len(tp_new), e1_n=len(e1), e4_n=len(e4),
                x2_n=len(x2), om=sum(1 for t in tp_new if t[open_idx]))


def e1_ok(ts, basis="narr"):
    return sum(1 for t in ts if not nonincreasing(x6_legs(t, basis)))


def _p6fmt(t, fmt):
    """옛 회차 `TRADES` 튜플을 post6 의 앞 9열 형식으로 옮긴다(값·순서 불변 · 재계산 입력)."""
    if fmt == "p4":      # (종목, 라벨, 레그, `~`, be)
        return (t[0], t[1], t[2], [0] * len(t[2]), t[3], t[3], t[4], True, False)
    if fmt == "p5":      # (종목, 라벨, 레그, `~`, be, 손실률, 범위만)
        return (t[0], t[1], t[2], t[5], t[3], t[3], t[4], True, t[6])
    return tuple(t[:9])  # p6 · p7


def recount(trades, fmt):
    """옛 회차 한 글의 `EXIT-` 항 — 그 회차의 잣대로 «다시» 센다(post4·post5 = X6 이전 · post6~ = X6)."""
    ts = [_p6fmt(t, fmt) for t in trades]
    tp = [t for t in ts if t[NEW] and t[LABEL] == "TP" and t[LEGS]]
    x6 = fmt in ("p6", "p7")
    r = {}
    r["E1a"] = (sum(1 for t in tp if not nonincreasing(t[LEGS])), len(tp))
    if x6:
        e1 = [t for t in tp if x6_legs(t, "narr")]
        r["E1n"] = (e1_ok(e1), len(e1))
        e4 = [t for t in tp if len(x6_legs(t, "narr")) >= 3]
        r["E4"] = (e1_ok(e4), len(e4))
    else:
        r["E1n"] = r["E1a"]
        e4 = [t for t in tp if len(t[LEGS]) >= 3]
        r["E4"] = (sum(1 for t in e4 if not nonincreasing(t[LEGS])), len(e4))
    be_all = [t for t in ts if t[BE] and t[LEGS]]
    be_new = [t for t in be_all if t[NEW]]
    r["E2a"] = (sum(1 for t in be_all if abs(t[LEGS][-1]) < BE_MAX), len(be_all))
    r["E2b"] = (sum(1 for t in be_new if abs(t[LEGS][-1]) < BE_MAX), len(be_new))
    be_new_tp = [t for t in be_new if t[LABEL] == "TP" and not t[OPEN_N]]   # (A) 정의 — 참고 재계산
    r["E2bA"] = (sum(1 for t in be_new_tp if abs(t[LEGS][-1]) < BE_MAX), len(be_new_tp))
    if fmt == "p4":
        r["X2"] = r["X8"] = None
    else:
        x2 = [t for t in tp if not t[OPEN_N]]
        r["X2"] = (sum(1 for t in x2 if abs(x2_leg(t[LEGS], t[LOSSM])[0]) < BE_MAX), len(x2))
        r["X8"] = (sum(1 for t in x2 if x2_leg(t[LEGS], t[LOSSM])[0] != t[LEGS][-1]), len(x2))
    r["E3seq"] = sum(1 for t in ts if t[LABEL] == "SL" and sum(t[LOSSM]) >= 2)
    return r


def frac(p):
    return "—" if p is None else "%d/%d = %.1f%%" % (p[0], p[1], ratio(p[0], p[1]))


def mark(ok, n, thr, min_n):
    """최소 n 미달 갈래는 ✅·❌ 를 찍지 않는다(통과/불통과로 «인용»되는 것을 막는다)."""
    if n < min_n:
        return "⛔ 최소 n 미달(%d < %d · 답으로 세지 않는다)" % (n, min_n)
    return "✅" if ok / n >= thr else "❌"


def main():  # noqa: C901
    D = denoms(TRADES)                              # 주 판정 (가) — 우리로 포함
    DX = denoms(TRADES, excl={URIRO})               # 「우리로 제외」 갈래
    # `~` 기준 갈래(표기 의존) — 🔴 두 읽기를 «둘 다» 센다(모호 · §12-2):
    #   DTH = LABELS·PD-5·PD-23 문언 — 우리로(`~` ∧ 완결 서술)만 미완결로 «뒤집고» 서술 기준 미완결은 그대로(서술 ∪ `~`)
    #   DTP = post6 PD-4 「`~` 문자 기준(X6 적용 0건)」·post7 판 `x6_legs(t, "tilde")` 순수 문자 기준(`~` 있는 건만 미완결)
    HYB = [t[:OPEN_N] + (bool(t[OPEN_N] or t[TILDE]),) + t[OPEN_N + 1:] for t in TRADES]
    DTH = denoms(HYB)
    DTP = denoms(TRADES, basis="tilde")
    tp_new, new = D["tp_new"], [t for t in TRADES if t[NEW]]
    foll = [t for t in TRADES if not t[NEW]]

    say("# RESULTS_EXIT_V2_POST8_NUMBERS — 기계 생성 (수정 금지)")
    say("")
    say("사전등록 `PREREG_EXIT_V2.md` §3 + `PREREG_POST6.md` §2-3(`EXIT-X5`~`X9` 재동결) + 🆕 `PREREG_POST8.md`"
        "(`D-2`·`D-5` 첫 구속) · 라벨 `LABELS_2026-09-18_post8.md` · 결정 `PREDECISION_2026-09-18_post8.md` · "
        "시퀀스 `INTAKE_2026-09-18_post8.md` §1 · 생성 `run_exit_v2_post8.py` · "
        "재사용 `run_exit_v2_post6.py`(`nonincreasing`·`eps_pairs`·`x2_leg`·`x6_legs`·`num`·`seq`·`ratio`) · "
        "옛 회차 재계산 입력 `run_exit_v2_post{4,5,6,7}.py` 의 `TRADES`(import 만)")
    say("허용 오차 ε = %g%%p(동결분 · 고치지 않는다) · 문턱 `EXIT-E1`/`X5` ≥ %.0f%% · "
        "`EXIT-E2`/`X2` ≥ %.0f%% · 본전 |ret| < %.1f%%" % (EPS, 100 * E1_MIN, 100 * E2_MIN, BE_MAX))
    say("")
    say("## §0. 환경 · 동결 규약 · 🆕 `PREREG_POST8.md` 의무 대조")
    say("")
    say("| 항목 | 값 |")
    say("|---|---|")
    say("| 🔴 창 종료 | **창 종료 %s = 발행 당일(금 · 거래일) 봉 «포함» · B-1 · ANC §2-1 `END` · 전 축(`WRC-` 포함) · PD-1** |"
        % DB_UPTO)
    say("| 실행 시 `max(date)` · 그 날짜 행수 | **DB 조회 0회** — 이 레인은 저자 서술만 읽는다. 관리자 실측(인용): "
        "**실행 시 `max(date)` = %s · 그 날짜 행수 %s — 기록만(창 아님)**. **이 산출물은 그 스냅샷에 의존하지 않는다** |"
        % ADMIN_DBMAX)
    say("| DB | **조회 0회** · 시드 불필요 · **결정적**(두 번 돌리면 byte 동일) |")
    say("| 라벨 동결 | `TP` **6** · `MANUAL` **3** · `MIX` **1** · `SL` **0** · `unknown` **0** — 값을 보기 «전»에 정해졌다"
        "(`LABELS_2026-09-18_post8.md` · 커밋 `cdc6533` · 원장 `b302f7f`) |")
    say("| 라이브 | 🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1) |")
    say("")
    say("| `PREREG_POST8.md` 의무 | 이 산출물 | 자리 |")
    say("|---|---|---|")
    say("| `D-2`(§2 · `P8-형변량` 세 수) | **해당** — 주 분모 · `TP` 포함 민감도 분모 · 「미등록 형」 줄 | §3 |")
    say("| `D-5`(§5 · `P8-갈래계수`) | **해당** — 갈래마다 `(갈래 이름, n, 답)` | §12 |")
    say("| `D-3`(§3 · `P8-approx의존신고`) | 🔴 **대상 축 아님** — 이 축의 분모는 등록일 정밀도로 정의되지 않는다"
        "(`PREREG_EXIT_V2.md:55` 「신규 건」 · INTAKE §5 D-3 공통 의무 목록·PD-21 표에 `EXIT-` 없음) · 신고 줄은 형식대로 인쇄 | §12-1 |")
    say("| `D-9`(§9 · 읽은 시각 · 혼합 빈티지) | **해당 없음** — `H`·`L`·`L₅` 를 읽지 않는다(DB 0회 · §9 (나) 2 는 "
        "「`H`·`L`·`L₅` 를 뽑은 산출물」에 건다) · ③ 「09-18 봉은 D+1(09-21) sweep 이후 읽음」·④ 「창 구간 `min(updated_at)` "
        "= 2026-09-23 15:45:10 ≥ 09-21 15:35: 예」 는 관리자 실측 인용 · ⑤ 창 없음 | §0 |")
    say("| `D-1`·`D-4`·`D-6`·`D-7`·`D-11` | 해당 없음(`ANC-`/`LAD-` · `WRC-` · `n_up` sd · 창5 가드 · `Q1-R2` 축의 의무) | — |")
    say("| `D-8`(`prog_ver` 공변량) | 해당 없음 — 이 산출물은 `prog_ver`(1.0.42)를 공변량으로 쓰지 않는다(PD-26) | — |")
    say("")
    say("> 🟢 **`P8-형변량` 적용 결과 `unknown` 0** — 10/10 형 = 「표준형」(`(표준형, 60)` 9 · `(표준형, 없음)` 1 = 코데즈 "
        "「사분위수, 표준형」 ⇒ `P8-형변량` 표 1행 *「형 = 「표준형」 ∧ 손절 서술 없음 ⇒ `TP`」*).")
    say("> 🔴🔴 **우리로 = 한 항목 · 두 사이클** — 🔒 #1-b **(가)**: 주 = **포함** + 「항목 내 2 사이클」 표시 + "
        "**「우리로 제외」 갈래를 전 항목에 인쇄**((i) `REC-` A-9 · `WRC-` `WRC-R5` 의 **준용** · PD-7).")
    say("> 🔴 **이 문서는 새 예측을 만들지 않는다**(`PREREG_POST6.md` §7-B #11) · 🟢 라벨 접두는 **`EXIT-`**.")
    say("")

    # ── §1. 원표 ────────────────────────────────────────────────────────
    say("## §1. 원표 — 8번째 글 10건 (신규 7 + 🔁후속 3 · 라벨은 계산 «전» 동결)")
    say("")
    say("| # | 종목 | 구분 | `(형, HDR)` | 라벨 | 완결(서술) | `~` | `be_note` | 레그 | "
        "시퀀스(저자 순서 · †=「손실률」) | 「손실률」 | 비증가 | 위반 |")
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
    say("- 라벨 집계: `TP` %d · `SL` %d · `MIX` %d · `MANUAL` %d · `unknown` %d "
        "(신규 7 = `TP` 4 + `MANUAL` 2 + `MIX` 1 · 🔁후속 3 = `TP` 2 + `MANUAL` 1)"
        % (lab["TP"], lab["SL"], lab["MIX"], lab["MANUAL"], lab["unknown"]))
    say("- 레그 합계 **%d**(신규 %d · 후속 %d) · 「손실률」 레그 **%d**(헥토파이낸셜 −2.28)"
        % (sum(len(t[LEGS]) for t in TRADES), sum(len(t[LEGS]) for t in new),
           sum(len(t[LEGS]) for t in foll), sum(sum(t[LOSSM]) for t in TRADES)))
    say("- 미완결(서술 기준) **%d건**(코데즈컴바인 · 우리기술) — 「나머지 물량 (은) 보유 중」이 판별 낱말이다(PD-5)."
        % sum(1 for t in TRADES if t[OPEN_N]))
    say("- 🔴 **`~` 와 서술이 불일치하는 2번째 사례**(post7 한전기술이 첫 · PD-5 1번): 우리로는 값 줄 끝이 **`0.54%% ~`** 인데 "
        "서술이 *「본전 위협에 전량매도 / … 1,2,3차 차례로 분할매도 **완료**」* 다 ⇒ **주 = 서술 기준(완결)** · `~` 기준은 "
        "민감도(§2-1 · §5 표기 의존 갈래) · `leg_open_ended = 1` 은 레그 단위 표기(%s)."
        % " · ".join("%s %s" % (k.split()[0], num(v)) for k, v in LEG_OPEN_ENDED.items()))
    say("- 🔴🔴 **`~` 정규식 함정**: 본문 `~` 5개 중 레그 표지는 우리로 **1개**뿐 — 나머지는 %s 다(PD-5 2번). "
        "`~` 를 기계로 세면 코데즈·우리기술이 서술과 무관하게 「미완결」로 잡힌다(둘 다 우연히 미완결이라 결과가 맞아 보인다 — "
        "***맞는 결과가 옳은 파서의 증거가 아니다***)." % TILDE_TRAP)
    say("- 🔴 표기 특이(PD-10): 우리로 **「17%」**(소수 0자리 · 값 17.00) · 동률 레그 **2쌍**(범한퓨얼셀 20.99·20.99 · 우리기술 "
        "8.47·8.47 — 동률 = 비증가 · 다중집합 보존) · **값 개수 ≠ 서술 매도 횟수 4건**(원문 값 그대로 레그로 적었다).")
    say("- 🔴 **`EXIT-X6` 적용 범위 = `EXIT-E1`·`EXIT-E4` «뿐»**(`PREREG_POST6.md` §1-8) — `EXIT-X2`·`EXIT-X8` 의 "
        "「마지막 레그」는 저자 «원» 시퀀스 기준이다.")

    # ── §2. EXIT-E1 / X5 ─────────────────────────────────────────────────
    say("")
    say("## §2. `EXIT-E1` · `EXIT-X5` — `TP` 신규 건의 매도 레그 시퀀스가 비증가 (문턱 ≥%.0f%%)" % (100 * E1_MIN))
    say("")
    say("주 판정 = **(가) 우리로 포함** · 서술 기준 미완결 `TP` 2건(코데즈·우리기술)의 **마지막 레그 하나 제외**(`EXIT-X6`). "
        "🔴 후속 `TP` 2건(빛과전자·범한퓨얼셀)은 **「신규 건에만」**(`PREREG_EXIT_V2.md:55`)으로 분모 밖(PD-2 3).")
    say("")
    say("| 종목 | 완결 | 원 시퀀스 | `EXIT-X6` 후 | 레그 | 비증가 | 위반 |")
    say("|---|---|---|---|---|---|---|")
    for t in tp_new:
        L = x6_legs(t, "narr")
        v = nonincreasing(L)
        say("| %s | %s | %s | %s | %d | %s | %s |"
            % (t[NAME], "완결" if not t[OPEN_N] else "**미완결**", seq(t[LEGS]),
               seq(L) if L != list(t[LEGS]) else "(동일)", len(L), "✅" if not v else "❌",
               "—" if not v else "; ".join("%s→%s" % (num(a), num(b)) for _, a, b in v)))
    e1k, e1n = e1_ok(D["e1"]), D["e1_n"]
    e1xk, e1xn = e1_ok(DX["e1"]), DX["e1_n"]
    e1tk, e1tn = e1_ok(DTH["e1"]), DTH["e1_n"]
    r1 = e1k / e1n
    say("")
    say("- **`EXIT-E1` (가) 주 = %d/%d = %.1f%%** ⇒ **%s** (문턱 %.0f%% · 주 분모 **%d** ≥ `TP` 최소 n %d)"
        % (e1k, e1n, ratio(e1k, e1n), "✅ 지지" if r1 >= E1_MIN else "❌ 불성립", 100 * E1_MIN, e1n, TP_MIN_N))
    say("- 「우리로 제외」 갈래 = **%d/%d = %.1f%%** ⇒ %s · `~` 기준 갈래(우리로 0.54 를 X6 로 제외) = **%d/%d = %.1f%%** ⇒ %s"
        % (e1xk, e1xn, ratio(e1xk, e1xn), mark(e1xk, e1xn, E1_MIN, TP_MIN_N),
           e1tk, e1tn, ratio(e1tk, e1tn), mark(e1tk, e1tn, E1_MIN, TP_MIN_N)))
    say("- **`EXIT-X5`**(= `RESULTS_EXIT_V2_POST5.md` §10 의 재확인 예측) = 같은 계산 ⇒ **%s** · 조건부 조항 *「위반 1건이 곧 "
        "첫 반례 … «생략 편향이 만든 100%%» 가설로 먼저 의심」* ⇒ 이번 위반 **%d건** ⇒ **%s**"
        % ("✅ 적중" if r1 >= E1_MIN else "❌ 빗나감", e1n - e1k, "미발동" if e1k == e1n else "🔴 발동"))
    withlegs = [t for t in TRADES if t[LEGS]]
    allv = [t for t in withlegs if nonincreasing(t[LEGS])]
    say("- 🔎 **라벨 제외 «전» %d건 전체**(원 시퀀스 · 후속·`MANUAL`·`MIX` 포함): 위반 **%d건** ⇒ 라벨 결정이 `EXIT-E1` 판정을 **%s**."
        % (len(withlegs), len(allv), "만들지 않았다" if not allv else "만들 수 있는 자리가 있다"))
    used = [(t[NAME], a, b) for t in withlegs for a, b in eps_pairs(t[LEGS])]
    ties = [(t[NAME], a) for t in withlegs for a, b in zip(t[LEGS], t[LEGS][1:]) if a == b]
    drops = sorted((a - b, t[NAME], a, b) for t in withlegs for a, b in zip(t[LEGS], t[LEGS][1:]) if a > b)
    say("- **ε 사용 건수 = %d회**(0 < 증가 ≤ %g%%p 인 쌍) · 동률 %d쌍(%s) · **최소 하락 간격 = %s %s → %s = %.2f%%p** — "
        "하락이라 ε 이 걸리지 않는다 ⇒ **ε 은 5글 연속 사용 0회**(post4~post8) · `PREREG_EXIT_V2.md` §4 한계 그대로(고치지 않는다)."
        % (len(used), EPS, len(ties), " · ".join("%s %s" % (n.split()[0], num(a)) for n, a in ties),
           drops[0][1].split()[0], num(drops[0][2]), num(drops[0][3]), drops[0][0]))

    say("")
    say("### §2-1. 미완결 처리 민감도 — (가)(나)(다) 병기(`EXIT-X6` #17 의무) + `~` 문자 기준(PD-5) · 🔴 우리로 포함 주 갈래")
    say("")
    say("| 처리 | 대상 `TP` 신규 | 비증가 | 비율 | 비고 |")
    say("|---|---|---|---|---|")
    a_ok = sum(1 for t in tp_new if not nonincreasing(t[LEGS]))
    say("| (가) 전 레그 포함 | %d | %d | %.1f%% | 민감도 · post4·post5 가 쓴 처리 |" % (len(tp_new), a_ok, ratio(a_ok, len(tp_new))))
    say("| (나) 미완결 건의 **마지막 레그만** 제거 = **서술 기준** | %d | %d | %.1f%% | 🟢 **주 판정값** |" % (e1n, e1k, ratio(e1k, e1n)))
    comp = [t for t in tp_new if not t[OPEN_N]]
    c_ok = sum(1 for t in comp if not nonincreasing(t[LEGS]))
    say("| (다) 미완결 건을 **통째 제외** | %d | %d | %.1f%% | 민감도 · n=%d %s 3 |"
        % (len(comp), c_ok, ratio(c_ok, len(comp)), len(comp), "≥" if len(comp) >= 3 else "<"))
    say("| (`~` 기준 · LABELS·PD-23 문언) 우리로도 미완결(서술 미완결 ∪ `~`) | %d | %d | %.1f%% | 민감도(PD-5) · `TP` 분모 안 `~` 건 = **우리로 1** |"
        % (e1tn, e1tk, ratio(e1tk, e1tn)))
    e1pk, e1pn = e1_ok(DTP["e1"], "tilde"), DTP["e1_n"]
    say("| (`~` 문자 기준 · post6 PD-4 순수) `EXIT-X6` 을 `~` 로만 적용 | %d | %d | %.1f%% | 민감도 · 코데즈·우리기술은 `~` 가 없어 전 레그 |"
        % (e1pn, e1pk, ratio(e1pk, e1pn)))
    say("")
    verdicts = {a_ok / len(tp_new) >= E1_MIN, r1 >= E1_MIN, e1tk / e1tn >= E1_MIN, e1pk / e1pn >= E1_MIN}
    say("- ⇒ 최소 n 을 채운 처리(가·나·`~` 두 읽기)가 **%s** · (다)는 n = %d < 3 이라 인쇄만 ⇒ 판정이 처리 선택에 **%s**."
        % ("모두 같은 판정" if len(verdicts) == 1 else "서로 다른 판정", len(comp),
           "의존하지 않는다 — 「표기 의존」 조항(PD-5) 미발동" if len(verdicts) == 1 else "🔴 의존한다 — 「표기 의존」"))
    say("- ⚠️ 레그 **2개**인 건(액스비스)은 비증가를 거의 자동으로 만족한다(2지선다) — `EXIT-E4` 가 걷어낸다.")

    say("")
    say("### §2-2. 생략 편향 비율 — 의무 인쇄(`PREREG_POST6.md` §2-3)")
    say("")
    say("- **계열 연속값(`TP` 분모 · 주 판정)**: post4 2/4 → post5 4/6 → post6 3/9 → post7 3/7 → **post8 %d/%d = %.1f%%**"
        % (D["om"], D["tp_n"], ratio(D["om"], D["tp_n"])))
    say("- 「우리로 제외」 **%d/%d = %.1f%%** · 신규 7건 분모 **%d/%d = %.1f%%** · `~` 기준(LABELS 문언 — 우리로도 미완결) "
        "**%d/%d = %.1f%%** · (참고) 순수 문자 기준 %d/%d = %.1f%%(§12-2 모호)"
        % (DX["om"], DX["tp_n"], ratio(DX["om"], DX["tp_n"]),
           sum(1 for t in new if t[OPEN_N]), len(new), ratio(sum(1 for t in new if t[OPEN_N]), len(new)),
           DTH["om"], DTH["tp_n"], ratio(DTH["om"], DTH["tp_n"]),
           DTP["om"], DTP["tp_n"], ratio(DTP["om"], DTP["tp_n"])))
    say("- 동결 문언: *「생략분은 대개 뒤쪽(낮은 수익률)이라 「비증가」에 «유리한» 방향으로 편향된다」*(`RESULTS_EXIT_V2_POST5.md` §9-4) "
        "⇒ **`EXIT-E1` 의 비율을 액면대로 읽지 말 것.**")

    # ── §3. D-2 ─────────────────────────────────────────────────────────
    say("")
    say("## §3. 🆕 `D-2` · `P8-형변량` — 세 수 (`PREREG_POST8.md` §2 (나) 기계 검사 · PD-20)")
    say("")
    say("| (i) 주 분모(`unknown` 제외) | (ii) `TP` 포함 민감도 분모 | (iii) 미등록 형 신고 줄 |")
    say("|---|---|---|")
    say("| `EXIT-E1` **%d** · `EXIT-E4` **%d** · `EXIT-X2` **%d** | `EXIT-E1` **%d** · `EXIT-E4` **%d** · `EXIT-X2` **%d** "
        "(`unknown` 0 ⇒ (i) 과 같다) | **미등록 형: %s** |"
        % (D["e1_n"], D["e4_n"], D["x2_n"], D["e1_n"], D["e4_n"], D["x2_n"],
           ", ".join(UNREGISTERED_FORMS) if UNREGISTERED_FORMS else "없음"))
    say("")
    say("- 🔴 (i) = (ii) 여도 **두 수를 둘 다 인쇄**한다 — 기계 검사의 대상은 «세 수의 존재»다(`PREREG_POST8.md` §2 (나)).")
    say("- 🔴 정규화 `(형, HDR수치)` 는 **인테이크의 사람 판단**(`LABELS_2026-09-18_post8.md` 동결)이고 이 스크립트가 하지 않는다 — "
        "***검사가 통과했다는 사실이 라벨이 옳다는 뜻으로 읽히면 안 된다***. 형 화이트리스트 = `{%s}`."
        % ", ".join(sorted(FORM_WHITELIST)))
    say("- 🔴 **`MANUAL` 민감도(판정엔 안 씀 · LABELS 약한 결정)**: 원익·JW신약을 `TP` 로 읽으면 `EXIT-E1` 분모 %d → **%d** · "
        "`EXIT-E4` %d → **%d** — 두 건 다 비증가 ∧ 레그 4 ⇒ `MANUAL` 판정은 E1·E4 에 «불리한» 방향이다(유리한 쪽을 고르지 않았다)."
        % (D["e1_n"], D["e1_n"] + 2, D["e4_n"], D["e4_n"] + 2))

    # ── §4. EXIT-E4 ─────────────────────────────────────────────────────
    say("")
    say("## §4. `EXIT-E4` (반증축) — `TP` ∧ 레그 ≥3 (`EXIT-X6` 적용 후)만으로 재계산")
    say("")
    say("| 종목 | `EXIT-X6` 후 레그 | 시퀀스 | 비증가 |")
    say("|---|---|---|---|")
    for t in D["e4"]:
        L = x6_legs(t, "narr")
        say("| %s | %d | %s | %s |" % (t[NAME], len(L), seq(L), "✅" if not nonincreasing(L) else "❌"))
    e4k, e4n = e1_ok(D["e4"]), D["e4_n"]
    e4xk, e4xn = e1_ok(DX["e4"]), DX["e4_n"]
    say("")
    say("| 갈래 | 건수 | 비증가 | 비율 | 표시 |")
    say("|---|---|---|---|---|")
    say("| **(가) 주** `TP` ∩ 레그 ≥3 | %d | %d | %.1f%% | %s |" % (e4n, e4k, ratio(e4k, e4n), mark(e4k, e4n, E1_MIN, E4_MIN_N)))
    say("| 「우리로 제외」 | %d | %d | %.1f%% | %s |" % (e4xn, e4xk, ratio(e4xk, e4xn), mark(e4xk, e4xn, E1_MIN, E4_MIN_N)))
    say("")
    say("- 제외된 건: %s" % (", ".join("%s(`EXIT-X6` 후 레그 %d)" % (t[NAME], len(x6_legs(t, "narr")))
                                       for t in tp_new if 0 < len(x6_legs(t, "narr")) < 3) or "없음"))
    say("- ⇒ (가) 주 **%s** — `EXIT-E1` 과 %s(%.1f%% vs %.1f%%). 「우리로 제외」 갈래는 n = %d < %d 라 **답으로 세지 않는다** "
        "⇒ `P8-갈래계수` *「최소 n 을 채운 갈래가 1개뿐이면 그 갈래의 답을 그대로 쓴다」*(`PREREG_POST8.md` §5 (나) 2)."
        % ("✅ 통과 — 레그 수가 만든 결과가 아니다" if ratio(e4k, e4n) == ratio(e1k, e1n) else "🔴 레그 수에 의존한다",
           "같다" if ratio(e4k, e4n) == ratio(e1k, e1n) else "다르다", ratio(e1k, e1n), ratio(e4k, e4n), e4xn, E4_MIN_N))
    say("- 🔴 **방향 자기신고(PD-7)**: (가) 가 E4 를 **연다**(2 → 3) — 우리로 목록이 비증가 · 레그 7 이다. 🔴 유리함은 근거가 아니다 — "
        "근거는 (i) 동결 문형의 **준용**과 「건 = 원장 행」 단위뿐이다(🔒 #1-b 사장님 채택).")

    # ── §5. EXIT-E2 · EXIT-X2 ───────────────────────────────────────────
    say("")
    say("## §5. `EXIT-E2`(병기 · 판정 아님) · `EXIT-X2`(주 판정) — 같은 표에 인쇄 (§7-C 3 의무)")
    say("")
    say("🔴 **분모 충돌 신고**(`PREREG_POST6.md` §1-8 형식 · post6·post7 승계) — 두 동결 문언이 서로 다른 분모를 지시한다. "
        "**어느 쪽도 고치지 않는다**:")
    say("")
    say("| 항목 | 동결 분모 | 동결 출처 | 이번 글 |")
    say("|---|---|---|---|")
    be_all = [t for t in TRADES if t[BE]]
    be_new = [t for t in be_all if t[NEW]]
    be_new_tp = [t for t in be_new if t[LABEL] == "TP" and not t[OPEN_N]]
    x2t = D["x2"]
    say("| `EXIT-E2` | 저자가 **본전 매도**라 적은 레그(`breakeven_note`) · **라벨·등록 사건 무관** | "
        "`PREREG_EXIT_V2.md` §3 + `PREREG_POST6.md` §1-1 | **%d건**(후속 포함 · 누적 계열) |" % len(be_all))
    say("| `EXIT-X2` | **신규 완결 `TP`** 건 | `PREREG_POST6.md` §2-3·§7-C 4 | **%d건** |" % len(x2t))
    say("")
    say("### §5-1. 병기 표 — 두 규칙이 각 건에서 «어느 레그»를 고르나")
    say("")
    say("| 종목 | 구분 | 라벨 | 완결 | `be_note` | 시퀀스 | `EXIT-E2`(원 시퀀스 마지막) | `EXIT-X2`(「손실률」 제외 후 마지막) | 다른가 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for t in TRADES:
        if not (t in be_all or t in x2t):
            continue
        last = t[LEGS][-1]
        xv, _xp = x2_leg(t[LEGS], t[LOSSM])
        say("| %s | %s | `%s` | %s | %s | %s | **%s** (%s) | **%s** (%s) | %s |"
            % (t[NAME], "신규" if t[NEW] else "🔁후속", t[LABEL], "완결" if not t[OPEN_N] else "**미완결**",
               "1" if t[BE] else "0", seq(t[LEGS], t[LOSSM]), num(last), "✅" if abs(last) < BE_MAX else "❌",
               num(xv), "✅" if abs(xv) < BE_MAX else "❌", "**예**" if xv != last else "아니오"))
    say("")
    say("- 🔴 **`EXIT-X2` 본전매도 레그 = 저자 «원» 시퀀스의 마지막**(`PREREG_POST6.md` §1-8 · X6 미적용 · LABELS 「X2 본전매도 레그 "
        "식별」) — 우리로 **0.54** · 액스비스 **0.31**.")
    say("- 🔴 **우리로의 E2/X2 레그 전제 미확인**(LABELS): 「본전 위협에 전량매도」는 **사이클 1** 의 서술인데 원규칙은 목록의 "
        "**마지막 레그(0.54)** 를 고른다 — 두 사이클이라 「마지막 = 본전매도 레그」 전제가 **확인되지 않는다**. (가)는 원규칙 축자(0.54) · "
        "「우리로 제외」 갈래에서는 빠진다.")

    say("")
    say("### §5-2. `EXIT-E2` — 원 동결 규칙(마지막 레그) · **병기 · 주 판정 아님** (문턱 ≥%.0f%%)" % (100 * E2_MIN))
    say("")
    e2a_ok = sum(1 for t in be_all if abs(t[LEGS][-1]) < BE_MAX)
    e2x = [t for t in be_all if t[NAME] != URIRO]
    e2x_ok = sum(1 for t in e2x if abs(t[LEGS][-1]) < BE_MAX)
    e2bA_ok = sum(1 for t in be_new_tp if abs(t[LEGS][-1]) < BE_MAX)
    e2bB_ok = sum(1 for t in be_new if abs(t[LEGS][-1]) < BE_MAX)
    say("| 분모(이번 글) | 건 | `\\|ret\\| < %.1f%%` | 비율 | 표시 |" % BE_MAX)
    say("|---|---|---|---|---|")
    say("| (가) `breakeven_note` 전건 — 🔁후속 «포함» | %d | %d | %.1f%% | %s |"
        % (len(be_all), e2a_ok, ratio(e2a_ok, len(be_all)), mark(e2a_ok, len(be_all), E2_MIN, E2_MIN_N)))
    say("| 「우리로 제외」 | %d | %d | %.1f%% | %s |"
        % (len(e2x), e2x_ok, ratio(e2x_ok, len(e2x)), mark(e2x_ok, len(e2x), E2_MIN, E2_MIN_N)))
    say("| 신규만 (A) = 신규 완결 `TP` ∧ note — `INTAKE` §2-14 · PD-7 표 · PD-23 문언 | %d | %d | %.1f%% | %s |"
        % (len(be_new_tp), e2bA_ok, ratio(e2bA_ok, len(be_new_tp)), mark(e2bA_ok, len(be_new_tp), E2_MIN, E2_MIN_N)))
    say("| 신규만 (B) = 신규 ∧ note(라벨 무관) — `run_exit_v2_post7.py` `be_new` 정의 · 계열 「신규만」 누적의 잣대 | %d | %d | %.1f%% | %s |"
        % (len(be_new), e2bB_ok, ratio(e2bB_ok, len(be_new)), mark(e2bB_ok, len(be_new), E2_MIN, E2_MIN_N)))
    say("")
    say("- `breakeven_note` **%d건** = %s. 헥토파이낸셜은 `MIX`(「손실률 -2.28」 ∧ 「본전 위협에 전량매도」)이고 E2 는 **라벨 무관**이라 들어간다."
        % (len(be_all), " · ".join("%s(%s)" % (t[NAME].split()[0], num(t[LEGS][-1])) for t in be_all)))
    say("- 🔴🔴 **모호 신고 — 「신규만」 갈래의 정의가 두 문서에서 다르다**: 인테이크 3문서는 *「신규만(완결 `TP` ∧ note = 우리로·액스비스) "
        "**2** < 3」*(`PREDECISION_2026-09-18_post8.md` PD-7 표 · `INTAKE` §2-14 · `LABELS` E2 절)로 적었고, post7 판 코드와 계열 "
        "「신규만」 누적(post4 PS일렉 `MIX` · post5 한켐 `MANUAL` 포함)은 **신규 ∧ note(라벨 무관) = %d** 로 센다. "
        "옛 회차에서도 post6·post7 은 두 정의가 같은 수였고 **post4·post5 는 달랐다**(§9-0 재계산 — (B) 에만 `MIX`·`MANUAL` 건이 있다). "
        "⇒ **양쪽 인쇄** — (A) n = %d < 3 ⇒ 답 없음 · (B) n = %d ≥ 3 ⇒ %s. 계열 「신규만」 누적은 (B) 로 이어 왔으므로 **누적은 (B) 로 잇고** "
        "(A) 는 이번 글 단독 값·재계산 참고로만 둔다. 🔴 **E2 의 누적 판정은 (가) 계열이 낸다**(아래 §9) · 두 「신규만」 갈래는 민감도다 — "
        "(B) 의 답이 (가) 누적의 답과 같아 **판정을 가르지 않는다**."
        % (len(be_new), len(be_new_tp), len(be_new), mark(e2bB_ok, len(be_new), E2_MIN, E2_MIN_N)))

    say("")
    say("### §5-3. `EXIT-X2` — **주 판정**(「손실률」 레그 제외 후 «원 시퀀스» 마지막) · 신규 완결 `TP` (문턱 ≥%.0f%%)" % (100 * E2_MIN))
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
            % (t[NAME], seq(t[LEGS], t[LOSSM]), seq(kept), num(xv), len(t[LEGS]) - xp, abs(xv), "✅" if p else "❌"))
    x2_n = len(x2t)
    say("")
    say("- **`EXIT-X2` (가) 주 = %d/%d = %.1f%%** ⇒ **%s**(`PREREG_POST6.md` §4 **#16** 고유 조항 *「최소 n = 완결 `TP` 3」* · "
        "⚠️ #15(`EXIT-E2`)와 수만 같고 «다른 행»)"
        % (x2_ok, x2_n, ratio(x2_ok, x2_n), "⛔ 보류 — 완결 `TP` %d < 3 · 통과로 인용 금지" % x2_n if x2_n < X2_MIN_N
           else ("✅ 지지" if x2_ok / x2_n >= E2_MIN else "❌ 불성립")))
    say("")
    say("#### `EXIT-X2` 갈래 (의무 인쇄 · 최소 n 미달 갈래는 ✅·❌ 를 찍지 않는다)")
    say("")
    say("| 갈래 | 분모 | 적중 | 비율 | 표시 | 비고 |")
    say("|---|---|---|---|---|---|")
    xx = DX["x2"]
    xx_ok = sum(1 for t in xx if abs(x2_leg(t[LEGS], t[LOSSM])[0]) < BE_MAX)
    xt = DTH["x2"]
    xt_ok = sum(1 for t in xt if abs(x2_leg(t[LEGS], t[LOSSM])[0]) < BE_MAX)
    sa = [t for t in x2t if t[BE]]
    sa_ok = sum(1 for t in sa if abs(x2_leg(t[LEGS], t[LOSSM])[0]) < BE_MAX)
    sb = x2t + foll
    sb_ok = sum(1 for t in sb if abs(x2_leg(t[LEGS], t[LOSSM])[0]) < BE_MAX)
    say("| **(가) 주** 신규 완결 `TP` | %d | %d | %.1f%% | %s | 동결 문언(§2-3·§7-C 4) |"
        % (x2_n, x2_ok, ratio(x2_ok, x2_n), mark(x2_ok, x2_n, E2_MIN, X2_MIN_N)))
    say("| 「우리로 제외」 | %d | %d | %.1f%% | %s | 🔒 #1-b 준용 갈래 |"
        % (len(xx), xx_ok, ratio(xx_ok, len(xx)), mark(xx_ok, len(xx), E2_MIN, X2_MIN_N)))
    say("| (a) 좁은 분모 = 신규 완결 `TP` ∧ `be_note` | %d | %d | %.1f%% | %s | 🔴 X2 에 «유리한» 방향 — 이번엔 **넓은 분모 = 좁은 분모**(구성상 차이 0) |"
        % (len(sa), sa_ok, ratio(sa_ok, len(sa)), mark(sa_ok, len(sa), E2_MIN, X2_MIN_N)))
    say("| (`~` 기준 · LABELS 문언) 우리로를 미완결로 읽음 | %d | %d | %.1f%% | %s | 표기 의존 갈래(PD-5 · PD-23 X2 목록 밖 · 인쇄만) |"
        % (len(xt), xt_ok, ratio(xt_ok, len(xt)), mark(xt_ok, len(xt), E2_MIN, X2_MIN_N)))
    say("| (b) 🔁후속 포함 확장 | %d | %d | %.1f%% | 🔴 **동결 적용 대상(「`TP` 완결 건」) «밖»** — `P8-갈래계수` 계수 대상 아님(PD-23 목록 밖) | 확장 민감도 |"
        % (len(sb), sb_ok, ratio(sb_ok, len(sb))))
    say("")
    say("- 🔒 **`P8-갈래계수`**: 최소 n(%d)을 채운 계수 갈래 = **0개** ⇒ 「갈렸다」를 셀 대상이 없다 — 규약 3번째 줄(*「최소 n 을 채운 갈래가 "
        "0 개면」*)에 해당한다(`PREREG_POST8.md` §5 (나) 2 · 등급 칸은 §6 단계). 🔴 **새 라벨(「…의존」류)을 만들지 않는다**(post7 철회 교훈)."
        % X2_MIN_N)
    say("")
    say("#### `EXIT-X2` 에서 «빠진» 건과 그 이유 (계산 «전» 동결분)")
    say("")
    say("| 종목 | 구분 | 라벨 | 완결 | 제외 사유 |")
    say("|---|---|---|---|---|")
    for t in TRADES:
        if t in x2t:
            continue
        if not t[NEW]:
            why = "🔁후속 — 「다음 글의 **신규 건**에만」(`PREREG_EXIT_V2.md:55` · PD-2 3) · 라벨과 무관하게 빠진다(확장 민감도 (b) 에만)"
        elif t[LABEL] != "TP":
            why = "라벨이 `%s` — 대상은 `TP` 뿐(라벨은 계산 «전» 동결)" % t[LABEL]
        else:
            why = "미완결(서술) — 「남은 레그 중 **마지막**」이 아직 안 적혔다(`EXIT-X6` 미적용 · §1-8)"
        say("| %s | %s | `%s` | %s | %s |" % (t[NAME], "신규" if t[NEW] else "🔁후속", t[LABEL],
                                             "완결" if not t[OPEN_N] else "미완결", why))

    # ── §6. EXIT-X8 ─────────────────────────────────────────────────────
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
    say("- 주 분모(%d건) 안 **%d건** — 「손실률」 레그 0개 ⇒ 두 규칙이 **구성상** 같은 레그를 고른다 ⇒ **%s**(**4글 연속**)."
        % (x2_n, x8, "⛔ 두 규칙 구분 불가" if x8 == 0 else "두 규칙이 구분된다"))
    say("- 「우리로 제외」 갈래도 같다(주 분모 안 「손실률」 0). 확장 분모(후속·`MIX`·`MANUAL` 포함 %d건)에서는 **%d건**(헥토 `MIX` 1.39 ≠ −2.28) "
        "⇒ **민감도에서만 「구분 가능」**(판정은 주 분모의 「구분 불가」)." % (x2_n + len(ext), x8 + x8b))

    # ── §7. EXIT-E3 / X7 ────────────────────────────────────────────────
    sl = [t for t in TRADES if t[LABEL] == "SL"]
    seqs = [t for t in sl if sum(t[LOSSM]) >= 2]
    say("")
    say("## §7. `EXIT-E3` · `EXIT-X7` — `SL` 건의 손절 레그 비증가 · ⛔ **판정 불가**")
    say("")
    say("- **`SL` %d건** ⇒ 「시퀀스」 **%d** · 누적 = post6 1 + post7 0 + post8 %d = **%d < %d**(§4 **#19** 최소 n = 「`SL` 시퀀스 3」) "
        "⇒ **⛔ 판정 불가 유지**. 헥토의 손실 레그 −2.28 은 `MIX` 라 E3 대상 아님(관측 인쇄)."
        % (len(sl), len(seqs), len(seqs), 1 + len(seqs), E3_MIN_N))
    say("- 🔴 사유 계열: post4 `SL` 0 · post5 범위만 · post6 시퀀스 1 < 3 · post7 시퀀스 0 · **post8 `SL` 0** — "
        "***표본이 생긴 것과 판정이 가능해진 것은 다르다.***")

    # ── §8. EXIT-X9 ─────────────────────────────────────────────────────
    man = [t for t in TRADES if t[LABEL] == "MANUAL"]
    say("")
    say("## §8. `EXIT-X9` — `MANUAL` 안의 자동 사이클 (관측 · 판정 아님) · 🔴 **약한 결정 · 두 갈래 병기**")
    say("")
    say("동결 트리거 = *「한켐형(「**자동으로 본전매도 → 이후 직접 매도**」)이 또 나오면 건수를 센다」*.")
    say("")
    say("| 갈래 | 읽기 | 이번 글 | 3건 게이트 |")
    say("|---|---|---|---|")
    say("| **주(판정에 쓰는 값)** | 한켐형 = 자동 «본전»매도 → 직접 | **%d건** · 누적 **0** | 미달 |" % X9_MAIN)
    say("| (민감도 · 넓은 독법) | `PREREG_POST6.md:811` 가설 이름 「`MANUAL` 안 자동 사이클」 — %s 의 「자동 «익절» 매도 → 이후 직접」 | "
        "**%d건** | 🔴 이 한 글로 3건에 **닿는다** |" % (" · ".join(t[NAME].split()[0] for t in man), X9_BROAD))
    say("")
    say("- 🔴 **방향 자기신고**: 넓은 독법(3)을 쓰면 「3건 쌓이면 사전등록」에 **바로 닿는다** ⇒ **주 0 선택은 게이트를 여는 쪽이 아니다**. "
        "🔴 post7 민감도 갈래(「본전 위협에 따라 직접」 2건)는 **다른** 넓은 독법이라 **합치지 않는다**. 라벨 규약 불변 조항 그대로.")

    # ── §9. 누적 ────────────────────────────────────────────────────────
    say("")
    say("## §9. 누적 집계 — `EXIT-E1` 두 계열(B-4) · 🆕 **post4~post7 은 그 회차 `TRADES` 로 «다시» 셌다**(옮겨 적기 아님)")
    say("")
    prior = [("4번째(2026-08-22)", recount(E4MOD.TRADES, "p4"), E7MOD.POST4),
             ("5번째(2026-08-29)", recount(E5MOD.TRADES, "p5"), E7MOD.POST5),
             ("6번째(2026-09-04)", recount(E6MOD.TRADES, "p6"), E7MOD.POST6),
             ("7번째(2026-09-12)", recount(E7MOD.TRADES, "p7"), None)]
    post8 = dict(E1a=(a_ok, len(tp_new)), E1n=(e1k, e1n), E4=(e4k, e4n),
                 E2a=(e2a_ok, len(be_all)), E2bA=(e2bA_ok, len(be_new_tp)), E2bB=(e2bB_ok, len(be_new)),
                 X2=(x2_ok, x2_n), X8=(x8, x2_n))
    post8x = dict(E1a=(sum(1 for t in DX["tp_new"] if not nonincreasing(t[LEGS])), DX["tp_n"]),
                  E1n=(e1xk, e1xn), E4=(e4xk, e4xn), E2a=(e2x_ok, len(e2x)), X2=(xx_ok, len(xx)))
    say("| 글 | `EXIT-E1` **(가) 전 레그** | `EXIT-E1` **(나) `X6` 적용** | `EXIT-E4` | `EXIT-E2`(후속 포함) | "
        "`EXIT-E2`(신규만) | `EXIT-X2` | `EXIT-X8` |")
    say("|---|---|---|---|---|---|---|---|")
    for nm, r, _q in prior:
        say("| %s *재계산* | %s | %s | %s | %s | %s | %s | %s |"
            % (nm, frac(r["E1a"]), frac(r["E1n"]), frac(r["E4"]), frac(r["E2a"]), frac(r["E2b"]),
               frac(r["X2"]) if r["X2"] else "— (동결만)",
               "%d/%d" % r["X8"] if r["X8"] else "—"))
    say("| **8번째(2026-09-18) 이번 (가)** | %s | %s | %s | %s | (A) %s · (B) %s | %s | %d/%d |"
        % (frac(post8["E1a"]), frac(post8["E1n"]), frac(post8["E4"]), frac(post8["E2a"]),
           frac(post8["E2bA"]), frac(post8["E2bB"]), frac(post8["X2"]), post8["X8"][0], post8["X8"][1]))

    def cum(key, extra, rows_=prior, bkey=None):
        ok = sum(r[bkey or key][0] for _n, r, _q in rows_ if r[bkey or key]) + extra[0]
        n = sum(r[bkey or key][1] for _n, r, _q in rows_ if r[bkey or key]) + extra[1]
        return ok, n

    c = {k: cum(k, post8[k]) for k in ("E1a", "E1n", "E4", "E2a", "X2", "X8")}
    c["E2bA"] = cum("E2bA", post8["E2bA"])          # (A) 정의로 옛 회차까지 다시 센 참고 누적
    c["E2bB"] = cum("E2b", post8["E2bB"], bkey="E2b")   # (B) = 계열 「신규만」 누적의 잣대
    cx = {k: cum(k, post8x[k]) for k in ("E1a", "E1n", "E4", "E2a", "X2")}
    say("| **누적 (가)** | **%s** | **%s** | **%s** | **%s** | **(B) %s**(계열 잣대) · (A) 정의 재계산 참고 %s | **%s** | **%d/%d** |"
        % (frac(c["E1a"]), frac(c["E1n"]), frac(c["E4"]), frac(c["E2a"]), frac(c["E2bB"]), frac(c["E2bA"]),
           frac(c["X2"]), c["X8"][0], c["X8"][1]))
    say("| 누적 「우리로 제외」 | %s | %s | %s | %s | — | %s | — |"
        % (frac(cx["E1a"]), frac(cx["E1n"]), frac(cx["E4"]), frac(cx["E2a"]), frac(cx["X2"])))
    say("")
    say("#### §9-0. 재계산 ↔ 동결 인용값 대조 (옮겨 적지 않았다는 증거 · 판정에 쓰지 않는다)")
    say("")
    say("| 글 | 항목 | 재계산 | 동결 인용값(`run_exit_v2_post7.py` `POST4`/`POST5`/`POST6`) | 일치 |")
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
    r7 = prior[3][1]
    row7 = ("| **7번째(2026-09-12 발행) 이번** | %s | %s | %s | %s | %s | %s | %d/%d |"
            % (frac(r7["E1a"]), frac(r7["E1n"]), frac(r7["E4"]), frac(r7["E2a"]), frac(r7["E2b"]), frac(r7["X2"]),
               r7["X8"][0], r7["X8"][1]))
    p7num = BASE / "RESULTS_EXIT_V2_POST7_NUMBERS.md"
    hit7 = p7num.exists() and row7 in p7num.read_text(encoding="utf-8").splitlines()
    n_bad += (not hit7)
    say("| 7번째(2026-09-12) | 행 전체 | %s · %s · %s · %s · %s · %s · %d/%d | `RESULTS_EXIT_V2_POST7_NUMBERS.md` §9 「7번째 … 이번」 행 | %s |"
        % (frac(r7["E1a"]), frac(r7["E1n"]), frac(r7["E4"]), frac(r7["E2a"]), frac(r7["E2b"]), frac(r7["X2"]),
           r7["X8"][0], r7["X8"][1], "✅ 축자 일치" if hit7 else "🔴 불일치"))
    say("| (참고) 4~7번째 | `E2` 신규만 (A) 정의 | %s | — (동결본에 (A) 열이 없다) | 참고 |"
        % " · ".join("%s %d/%d" % (nm.split("(")[0], r["E2bA"][0], r["E2bA"][1]) for nm, r, _q in prior))
    say("")
    say("- ⇒ 재계산 불일치 **%d건** — %s" % (n_bad, "옛 회차 값은 그 회차 `TRADES` 로 다시 세도 동결 인용값과 같다(소급 = 탐색 · 옛 판정 불변)."
                                           if n_bad == 0 else "🔴 불일치를 그대로 적는다(옛 판정은 바꾸지 않는다)."))
    say("")
    say("### §9-1. `EXIT-E1` 누적 — **두 줄을 항상 같이 적는다**(B-4 · post7 부터 구속)")
    say("")
    ga, na = c["E1a"], c["E1n"]
    say("- **(가) 전 레그 계열** = **%s** ⇒ **%s** · 「우리로 제외」 %s" % (frac(ga), "✅ 지지" if ga[0] / ga[1] >= E1_MIN else "❌ 불성립", frac(cx["E1a"])))
    say("- **(나) `EXIT-X6` 적용 계열** = **%s** ⇒ **%s** · 「우리로 제외」 %s" % (frac(na), "✅ 지지" if na[0] / na[1] >= E1_MIN else "❌ 불성립", frac(cx["E1n"])))
    split_e1 = (ga[0] / ga[1] >= E1_MIN) != (na[0] / na[1] >= E1_MIN)
    say("- ⇒ %s" % ("🔴🔴 **⛔ 「누적 정의 의존」** — 두 줄이 90% 문턱을 사이에 두고 갈린다 ⇒ 누적 `EXIT-E1` 의 지지/불성립을 선언하지 않는다."
                    if split_e1 else "🟢 **두 줄이 문턱을 사이에 두고 갈리지 «않는다»** ⇒ 「누적 정의 의존」 **미발동** — 그래도 두 줄을 계속 따로 적는다."))
    say("- 누적 `EXIT-E4` **%s** · 누적 `EXIT-E2` (가) **%s** ⇒ **%s**(「우리로 제외」 %s) · 누적 `EXIT-X2` **%s**(기록 — X2 판정은 글 단위 #16) · "
        "누적 `EXIT-X8` **%d/%d** ⇒ %s"
        % (frac(c["E4"]), frac(c["E2a"]), "❌ 불성립 — 5글 연속" if c["E2a"][0] / c["E2a"][1] < E2_MIN else "지지",
           frac(cx["E2a"]), frac(c["X2"]), c["X8"][0], c["X8"][1], "⛔ 구분 불가" if c["X8"][0] == 0 else "구분 가능"))
    say("- 🔴 **3번째 글(2026-08-14)은 누적 분모에 없다**(`PREREG_EXIT_V2.md` 는 08-15 동결 · 「다음 글의 신규 건」). "
        "`EXIT-X2` 누적 분모 %d 는 여전히 작다." % c["X2"][1])

    # ── §10. 연결 시퀀스 ────────────────────────────────────────────────
    say("")
    say("## §10. 연결 시퀀스 — 🔁후속 3건 (PD-2 4번 · **기록만** · 어떤 판정에도 안 쓴다)")
    say("")
    say("| 건 | post7 시퀀스(post7 판 `TRADES`) | post7 마지막 | post8 첫 | 연결 | 체결 차수 |")
    say("|---|---|---|---|---|---|")
    p7 = {t[0]: t for t in E7MOD.TRADES}
    n_up = 0
    for t in foll:
        prev = p7[FOLLOW_MAP[t[NAME]]][2]
        delta = t[LEGS][0] - prev[-1]
        n_up += delta > 0
        say("| %s | [%s] | %s | %s | %s | 1차만(두 글 모두) |"
            % (t[NAME], seq(prev), num(prev[-1]), num(t[LEGS][0]),
               "감소 ✅" if delta <= 0 else "🔴 **+%.2f%%p 증가**" % delta))
    hk = E7MOD.POST6_SEQ["한라캐스트 🔁후속"]
    say("| (참고) post7 한라캐스트 | post6 […, %s] | %s | %s | 🔴 +%.2f%%p 증가 | 5차 |"
        % (num(hk[-1]), num(hk[-1]), num(11.22), 11.22 - hk[-1]))
    say("")
    say("- 🔴🔴 **후속 연결 지점 증가 %d/%d 관측** — 세 건 모두 두 글에 걸쳐 **1차 매수만**(평단 불변 서술)인데도 증가다. "
        "**원인은 해석하지 않는다**(판정 안 씀 · 다음 사전등록 재료 INTAKE §4 1번)." % (n_up, len(foll)))
    say("- 🔴 **방향 자기신고 — «혼합»**: 연결을 E1 에 안 넣는 것은 위반 쌍 3개를 만들지 않는 쪽 = E1 에 **유리** · post8 단독 레그"
        "(빛과전자 23.47→17.88 · 범한퓨얼셀 20.99=20.99→0.43 — 항목 내 비증가)를 안 넣는 것은 `TP` 2건을 빼는 쪽 = **불리**. "
        "어느 쪽도 고른 것이 아니라 **문언(`:55`)이 둘 다 뺀 결과**다.")

    # ── §11. RANGE_ONLY ─────────────────────────────────────────────────
    say("")
    say("## §11. `RANGE_ONLY` 규약 (PD-18)")
    say("")
    say("- 🟢 **이번 글 해당 %d건.** 우리로의 *「0.54%% ~」* 는 끝값이 없어 「A%% ~ B%%」가 아니다 ⇒ **미완결 표지**(PD-5 1). "
        "코데즈·우리기술의 *「1~4차」* 는 **차수 표기** · *「2,000~3,000건」* 은 산문." % sum(1 for t in TRADES if t[RANGE]))

    # ── §12. D-5 갈래 표 ────────────────────────────────────────────────
    say("")
    say("## §12. 🆕 `D-5` · `P8-갈래계수` — 갈래마다 `(갈래 이름, n, 답)` (`PREREG_POST8.md` §5 (나) 2 · PD-23 `EXIT-` 행)")
    say("")
    say("최소 n = 그 축의 동결값 그대로(`TP` 3 · E4 3 · E2 3 · X2 완결 `TP` 3). 최소 n 을 채운 갈래만 「답」으로 센다. "
        "2 이상이 갈리면 [갈래 의존] · 1개면 그 답 · 0개면 규약 3번째 줄(등급 칸은 §6 단계에서 매긴다).")
    say("")
    say("| 축 | 갈래 | n | 답 | 계수 |")
    say("|---|---|---|---|---|")

    def ans(ok, n, thr, mn):
        return ("%d/%d = %.1f%% %s" % (ok, n, ratio(ok, n), "✅" if ok / n >= thr else "❌")) if n >= mn \
            else "%d/%d — 최소 n 미달(답 없음)" % (ok, n)

    rows_d5 = [
        ("`EXIT-E1`", "(가) 우리로 포함(주)", e1n, ans(e1k, e1n, E1_MIN, TP_MIN_N), e1n >= TP_MIN_N),
        ("`EXIT-E1`", "「우리로 제외」", e1xn, ans(e1xk, e1xn, E1_MIN, TP_MIN_N), e1xn >= TP_MIN_N),
        ("`EXIT-E1`", "`~` 기준(우리로 0.54 X6)", e1tn, ans(e1tk, e1tn, E1_MIN, TP_MIN_N), e1tn >= TP_MIN_N),
        ("`EXIT-E4`", "(가) 주", e4n, ans(e4k, e4n, E1_MIN, E4_MIN_N), e4n >= E4_MIN_N),
        ("`EXIT-E4`", "「우리로 제외」", e4xn, ans(e4xk, e4xn, E1_MIN, E4_MIN_N), e4xn >= E4_MIN_N),
        ("`EXIT-X2`", "(가) 주", x2_n, ans(x2_ok, x2_n, E2_MIN, X2_MIN_N), x2_n >= X2_MIN_N),
        ("`EXIT-X2`", "「우리로 제외」", len(xx), ans(xx_ok, len(xx), E2_MIN, X2_MIN_N), len(xx) >= X2_MIN_N),
        ("`EXIT-X2`", "좁은 분모(완결 `TP` ∧ note)", len(sa), ans(sa_ok, len(sa), E2_MIN, X2_MIN_N), len(sa) >= X2_MIN_N),
        ("`EXIT-E2` 누적", "(가) 후속 포함", c["E2a"][1], ans(c["E2a"][0], c["E2a"][1], E2_MIN, E2_MIN_N), True),
        ("`EXIT-E2` 누적", "「우리로 제외」", cx["E2a"][1], ans(cx["E2a"][0], cx["E2a"][1], E2_MIN, E2_MIN_N), True),
        ("`EXIT-E2`", "신규만 (A) 완결 `TP` ∧ note(이번 글)", len(be_new_tp),
         ans(e2bA_ok, len(be_new_tp), E2_MIN, E2_MIN_N), len(be_new_tp) >= E2_MIN_N),
        ("`EXIT-E2`", "신규만 (B) 신규 ∧ note(이번 글 · 모호 병기)", len(be_new),
         ans(e2bB_ok, len(be_new), E2_MIN, E2_MIN_N), len(be_new) >= E2_MIN_N),
    ]
    for ax, br, n, a_, cnt in rows_d5:
        say("| %s | %s | %d | %s | %s |" % (ax, br, n, a_, "계수" if cnt else "인쇄만(최소 n 미달)"))
    say("| `EXIT-X9` | 한켐형 / 넓은 독법 | %d / %d | 관측(최소 n 없음) | 계수 대상 밖 |" % (X9_MAIN, X9_BROAD))
    say("")
    for ax in ("`EXIT-E1`", "`EXIT-E4`", "`EXIT-X2`"):
        got = [(br, a_) for a_x, br, n, a_, cnt in rows_d5 if a_x == ax and cnt]
        kinds = {a_.split()[-1] for _b, a_ in got}
        say("- %s: 최소 n 을 채운 갈래 **%d개** ⇒ %s"
            % (ax, len(got), "0개 — 규약 3번째 줄(답 없음 · 보류)" if not got else
               ("1개 — 그 갈래의 답(%s)" % got[0][1] if len(got) == 1 else
                ("전부 같은 답(%s) — **갈리지 않는다**" % next(iter(kinds)) if len(kinds) == 1 else "🔴 **갈린다** — [갈래 의존]"))))
    e2got = [a_ for a_x, br, n, a_, cnt in rows_d5 if a_x.startswith("`EXIT-E2`") and cnt]
    e2k = {a_.split()[-1] for a_ in e2got}
    say("- `EXIT-E2`(병기 축): 최소 n 을 채운 갈래 **%d개** ⇒ %s" % (len(e2got), "전부 같은 답(%s) — 갈리지 않는다" % next(iter(e2k))
                                                            if len(e2k) == 1 else "🔴 갈린다"))

    say("")
    say("### §12-2. 🔴 모호 신고 — `~` 기준의 두 읽기(E1 은 같은 답 · X2·생략 편향에서 갈린다)")
    say("")
    xp = DTP["x2"]
    xp_ok = sum(1 for t in xp if abs(x2_leg(t[LEGS], t[LOSSM])[0]) < BE_MAX)
    say("| 읽기 | 출처 | `EXIT-E1` | `EXIT-X2` | 생략 편향 |")
    say("|---|---|---|---|---|")
    say("| (H) 서술 미완결 ∪ `~` — 우리로만 뒤집는다 | `LABELS_2026-09-18_post8.md` 「우리로 완결 판정」 절 · PD-5 1 · PD-23 | %d/%d | %d/%d(%s) | %d/%d |"
        % (e1tk, e1tn, xt_ok, len(xt), mark(xt_ok, len(xt), E2_MIN, X2_MIN_N), DTH["om"], DTH["tp_n"]))
    say("| (P) 순수 `~` 문자 — `~` 있는 건만 미완결 | `PREDECISION_2026-09-04_post6.md` PD-4 「`~` 문자 기준(X6 적용 0건)」 · post7 판 `x6_legs(t, \"tilde\")` | %d/%d | %d/%d(%s) | %d/%d |"
        % (e1pk, e1pn, xp_ok, len(xp), mark(xp_ok, len(xp), E2_MIN, X2_MIN_N), DTP["om"], DTP["tp_n"]))
    say("")
    say("- 🔴 **이 레인은 (H) 를 `~` 기준 갈래로 썼다** — 이번 회차의 동결 인테이크(LABELS · PD-5 1 *「영향은 X2 완결 분모(2 ↔ 1 · "
        "둘 다 < 3)와 생략 편향 비율뿐」* · PD-23)가 그렇게 적었다. (P) 는 post6 PD-4 가 `EXIT-X6`(E1·E4) 적용 범위에서만 정의한 읽기이고 "
        "`EXIT-X2` 의 「완결」은 서술 기준이 정한다(`PREREG_POST6.md` §1-8). ⇒ **(P) 의 X2 값은 인쇄만 · 계수·판정에 쓰지 않는다**"
        "(PD-23 의 `EXIT-X2` 갈래 목록 밖 · 코데즈·우리기술은 서술상 「나머지 물량 보유 중」이라 (P) 는 저자가 아직 적지 않은 레그를 "
        "본전매도 자리로 지목한다). 관리자·리뷰어 확인 사안.")
    say("")
    say("### §12-1. `D-3` 신고 줄 — 🔴 **이 축은 대상이 아니다**(형식만 인쇄 · 모호 신고)")
    say("")
    ex_e1 = [t for t in D["e1"] if not t[NAME].startswith("코데즈")]
    ex_e4 = [t for t in D["e4"] if not t[NAME].startswith("코데즈")]
    ex_x2 = [t for t in D["x2"] if not t[NAME].startswith("코데즈")]
    say("「`approx` 포함 시 최소 n 이 차는 축: 없음 · `exact` 분모 — / `approx` 포함 분모 —」 — `EXIT-` 분모는 등록일 정밀도로 "
        "정의되지 않는다(`PREREG_EXIT_V2.md:55` 「신규 건」 · INTAKE §5 D-3 공통 의무 목록·PD-21 표에 `EXIT-` 없음 · "
        "post7 은 `approx` 지투파워를 E1·E4·X2 주 분모에 넣었다).")
    say("- 🔴🔴 **모호 신고(참고 산술 · 판정에 쓰지 않는다)**: 만약 정밀도로 가른다면 `exact` 만 = E1 **%d** · E4 **%d** · X2 **%d** "
        "/ `approx` 포함(= 주) = E1 %d · E4 %d · X2 %d ⇒ **E4 는 「`approx`(코데즈)를 넣어야 최소 n 3 이 차는」 모양**이다. "
        "이 산출물은 동결 인테이크(PD-7 표 「E4 (가) 3 = 우리로·코데즈·우리기술」 · PD-21 · INTAKE §5)와 post7 선례대로 "
        "**D-3 를 `EXIT-` 에 적용하지 않았다** — 관리자·리뷰어 확인 사안."
        % (len(ex_e1), len(ex_e4), len(ex_x2), D["e1_n"], D["e4_n"], D["x2_n"]))

    # ── §13. 한계 ───────────────────────────────────────────────────────
    say("")
    say("## §13. 미리 적어두는 한계 (승계 + 이번 회차 고유)")
    say("")
    say("1. 🔴 **ε = %g%%p 가 5글 연속 사용 0회** — 값을 정한 근거는 첫 표본에서 왔고 이 대역이 실제로 필요한 적이 아직 없다. 고치지 않는다." % EPS)
    say("2. 🔴 **생략 편향** — `TP` 신규 %d건 중 %d건이 미완결이다. 「비증가」에 «유리한» 방향이다." % (D["tp_n"], D["om"]))
    say("3. 🔴 **`EXIT-X2` 반증축이 4글 연속 「구분 불가」** — 주 분모에 「손실률」 레그가 0개다.")
    say("4. 🔴 **`EXIT-E3` ⛔**(`SL` 0 · 누적 1 < 3).")
    say("5. 🔴 **우리로 = 한 항목 두 사이클** — 레그 7개를 두 사이클로 배분할 근거가 원문에 없다(서술 매도 5회 ↔ 값 7개). "
        "「비증가는 한 사다리 안에서만 뜻이 있다」(`PREREG_EXIT_V2.md:27` · §1 «진단 · 검정 아님» 절)는 정의 절을 넘지 않는다 — "
        "🔒 #1-b (가)로 포함하고 「우리로 제외」 갈래를 전 항목에 인쇄했다. 「17%」 소수 0자리(±0.5%p 표기 불확실)는 비증가 판정에 무영향.")
    say("6. 🔴 **저자가 레그별 시각·수량을 안 적는다.** 「시퀀스 순서 = 체결 순서」는 여전히 **가정**이다 "
        "(부분 예외: 후속 3건 「이번주 9월 14일」 — 09-14 = KRX 연장 제도 첫날 · 기록만 · PD-10 #9).")
    say("7. 🔴 **후속 `TP` 의 연결 시퀀스가 3/3 증가**다(§10) — 평단 불변 서술인데도 증가 · 원인 해석 안 함 · 다음 사전등록 재료.")
    say("8. 🔴 **프로그램 `1.0.42`(업데이트 중)** — 이 산출물은 버전을 공변량으로 쓰지 않는다(D-8 해당 없음).")
    say("9. 이 분석은 **라이브 채택 대상이 아니다**(`PREREG.md` §0 2번 · `PREREG_POST8.md` §0-1).")
    say("")
    say("[[LABELS_2026-09-18_post8]] · [[INTAKE_2026-09-18_post8]] · [[PREDECISION_2026-09-18_post8]] · [[PREREG_POST8]] · "
        "[[PREREG_POST6]] · [[PREREG_EXIT_V2]] · [[RESULTS_EXIT_V2_POST7]] · [[RESULTS_EXIT_V2_POST6]]")

    (BASE / "RESULTS_EXIT_V2_POST8_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

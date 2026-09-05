# -*- coding: utf-8 -*-
"""`PREREG_EXIT_V2.md` §3 + `PREREG_POST6.md` §2-3(X5~X9 재동결) 실행 — 6번째 글.

`run_exit_v2_post5.py` 승계. 라벨·완결 여부·시퀀스는 **계산 «전»에** 동결된
`LABELS_2026-09-04_post6.md` · `INTAKE_2026-09-04_post6.md` §1 에서 «그대로» 옮긴다
(`TP` 9 · `SL` 1 · `MIX` 2(후속) · `MANUAL` 0). 「손실률」로 적힌 레그는 저자 낱말
그대로 `loss_mask` 에 표시한다(`EXIT-X2` 가 이걸 쓴다).

DB 를 읽지 않는다(저자 서술만) ⇒ 결정적이고 DB 스냅샷에 의존하지 않는다.
시드 불필요. 라이브 트리 import 0건.

🔴 이 산출물은 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2).
🔴 이 스크립트는 **새 예측을 만들지 않는다**(`PREREG_POST6.md` §7-B #11).
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT: list = []

EPS = 0.05          # `PREREG_EXIT_V2.md` §2 허용 오차 0.05%p (동결분 · 고치지 않는다)
E1_MIN = 0.90       # §3 E1 / `EXIT-X5`: `TP` 건의 90% 이상
E2_MIN = 0.80       # §3 E2 / `EXIT-X2`: 4/5 이상 = 80%
BE_MAX = 1.0        # §3 E2: 본전 매도 레그의 |ret| < 1.0%

# 동결 인용값 — 4·5번째 글 (`RESULTS_EXIT_V2_POST4_NUMBERS.md` · `RESULTS_EXIT_V2_POST5_NUMBERS.md`)
POST4 = {"E1_ok": 4, "E1_n": 4, "E4_ok": 3, "E4_n": 3, "E2_ok": 2, "E2_n": 3}
POST5 = {"E1_ok": 6, "E1_n": 6, "E4_ok": 4, "E4_n": 4, "E2_ok": 2, "E2_n": 3,
         "X2_ok": 2, "X2_n": 2, "X8": 0, "X8_n": 2, "X9": 0}

# ── 표본 (계산 «전» 동결분 그대로) ─────────────────────────────────────────
# (종목, 라벨, 레그, 「손실률」마스크, 서술기준 미완결, `~` 문자, breakeven_note, 신규, 범위만)
TRADES = [
    # 🔁 후속 2건 — `PREDECISION_2026-09-04_post6.md` PD-2
    ("광전자 🔁후속",       "MIX", [0.80, 0.52, 0.11, -7.22, -7.51],
     [0, 0, 0, 1, 1], False, False, True,  False, False),
    ("삼양바이오팜 🔁후속", "MIX", [6.77, 6.74, 4.78, 0.88, -1.73],
     [0, 0, 0, 0, 1], False, False, True,  False, False),
    # 신규 10건
    ("한라캐스트",         "SL",  [5.82, 5.72, -2.87, -2.89],
     [0, 0, 1, 1],       True,  False, False, True,  False),
    ("헥토파이낸셜",       "TP",  [22.24, 15.33, 8.27],
     [0, 0, 0],          False, False, False, True,  False),
    ("아난티",             "TP",  [10.16],
     [0],                True,  False, False, True,  False),
    ("아이티센글로벌",     "TP",  [5.72, 0.50],
     [0, 0],             False, False, True,  True,  False),
    ("현대약품 🔂재진입",  "TP",  [12.32, 2.97],
     [0, 0],             False, False, True,  True,  False),
    ("원익",               "TP",  [18.44, 16.18, 14.05, 13.09, 13.06, 9.48, 4.27],
     [0] * 7,            False, False, False, True,  False),
    ("쿠콘",               "TP",  [14.31, 10.74],
     [0, 0],             False, False, False, True,  False),
    ("지투파워 🔂재진입",  "TP",  [10.14, 7.36, 7.25, 5.19],
     [0, 0, 0, 0],       True,  False, False, True,  False),
    ("우리기술투자",       "TP",  [16.48, 13.80, 13.63, 10.19, 6.50],
     [0] * 5,            True,  False, False, True,  False),
    ("비에이치",           "TP",  [11.91, 10.65, 9.63, 8.36, 7.09, 6.08, 3.70],
     [0] * 7,            False, False, False, True,  False),
]

NAME, LABEL, LEGS, LOSSM, OPEN_N, TILDE, BE, NEW, RANGE = range(9)

# post5 시퀀스 — 연결 시퀀스 「기록만」 한 줄용 (PD-2 4번). 판정에 쓰지 않는다.
POST5_SEQ = {"광전자 🔁후속": [15.81, 9.21, 9.21, 6.99, 0.93],
             "삼양바이오팜 🔁후속": [11.50, 11.50]}


def say(s=""):
    print(s)
    OUT.append(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def nonincreasing(legs):
    """ε 이내의 증가는 위반으로 세지 않는다(`PREREG_EXIT_V2.md` §3 E1). 위반 쌍 목록."""
    return [(i, legs[i], legs[i + 1])
            for i in range(len(legs) - 1) if legs[i + 1] - legs[i] > EPS]


def eps_pairs(legs):
    """ε «에 기대어» 통과한 쌍(0 < 증가 ≤ ε). 사용 횟수 인쇄용."""
    return [(a, b) for a, b in zip(legs, legs[1:]) if 0 < b - a <= EPS]


def num(x):
    """저자 표기 그대로 2자리 고정(`INTAKE_2026-09-04_post6.md` §1)."""
    return "%.2f" % x


def seq(legs, mask=None):
    if mask is None:
        return ", ".join(num(x) for x in legs)
    return ", ".join(num(x) + ("†" if m else "") for x, m in zip(legs, mask))


def x2_leg(legs, mask):
    """`EXIT-X2` 동결 규칙: 「손실률」 레그를 뺀 뒤 남은 레그 중 **마지막**.
    `PREREG_POST6.md` §1-8 — 「마지막」은 저자 «원» 시퀀스 기준(`EXIT-X6` 미적용).
    돌려주는 값 = (레그값, 원 시퀀스 0-기반 위치) · 남는 게 없으면 (None, None)."""
    kept = [(i, v) for i, (v, m) in enumerate(zip(legs, mask)) if not m]
    if not kept:
        return None, None
    return kept[-1][1], kept[-1][0]


def x6_legs(t, basis):
    """`EXIT-X6` — 미완결 건의 **마지막 레그 하나**만 뺀다. 적용 범위 = E1·E4 뿐(§1-8).
    basis='narr' 서술 기준(주 판정 · PD-4) · basis='tilde' `~` 문자 기준(민감도 · 이번 글 0건)."""
    open_ = t[OPEN_N] if basis == "narr" else t[TILDE]
    return t[LEGS][:-1] if open_ else list(t[LEGS])


def ratio(ok, n):
    return (100.0 * ok / n) if n else float("nan")


def main():  # noqa: C901
    tp_new = [t for t in TRADES if t[NEW] and t[LABEL] == "TP"]
    new = [t for t in TRADES if t[NEW]]
    foll = [t for t in TRADES if not t[NEW]]

    say("# RESULTS_EXIT_V2_POST6_NUMBERS — 기계 생성 (수정 금지)")
    say("")
    say("사전등록 `PREREG_EXIT_V2.md` §3 + `PREREG_POST6.md` §2-3(`EXIT-X5`~`X9` 재동결) · "
        "라벨 `LABELS_2026-09-04_post6.md` · 결정 `PREDECISION_2026-09-04_post6.md` · "
        "시퀀스 `INTAKE_2026-09-04_post6.md` §1 · 생성 `run_exit_v2_post6.py`")
    say("허용 오차 ε = %g%%p(동결분 · 고치지 않는다) · 문턱 `EXIT-E1`/`X5` ≥ %.0f%% · "
        "`EXIT-E2`/`X2` ≥ %.0f%% · 본전 |ret| < %.1f%%"
        % (EPS, 100 * E1_MIN, 100 * E2_MIN, BE_MAX))
    say("")
    say("> 🟢 **DB 미사용**(저자 서술만) ⇒ DB 스냅샷 무관 · **시드 불필요 · 결정적**"
        "(두 번 돌리면 byte 동일).")
    say("> 🟢 계열 규약상 이번 글의 창 종료 = **2026-09-04 = 발행 당일 봉 «포함»**(PD-1) — "
        "이 산출물은 DB 를 읽지 않으므로 그 스냅샷에 **의존하지 않는다**(§7-B #13 표기 의무 이행).")
    say("> 🟢 **라벨 동결이 계산보다 앞선다** — `TP` 9 · `SL` 1 · `MIX` 2(후속) · `MANUAL` 0 은 "
        "값을 보기 «전»에 정해졌다(`LABELS` · verifier 4패스 APPROVE 판).")
    say("> 🔴 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2).")
    say("> 🔴 **이 문서는 새 예측을 만들지 않는다**(`PREREG_POST6.md` §7-B #11) — "
        "다음 글 예측은 이 산출물 밖에서 따로 동결한다.")
    say("> 🟢 라벨 접두는 `PREREG_POST6.md` §0-3 규약대로 **`EXIT-`** 를 붙인다.")
    say("> ⚠️ 값 표기 = **저자 표기 2자리 고정**(`0.50`·`3.70`). post5 스크립트의 `%g` 표기와 "
        "«글자»가 다르나 **값은 같다** — 표기 차이는 모호 지점에 적어 둔다.")
    say("")

    # ── 원표 ────────────────────────────────────────────────────────────
    say("## 원표 — 6번째 글 12건 (신규 10 + 🔁후속 2 · 라벨은 계산 «전» 동결)")
    say("")
    say("| # | 종목 | 구분 | 라벨 | 완결 | `be_note` | 레그 | 시퀀스(저자 순서 · †=「손실률」) | 「손실률」 | 비증가 | 위반 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    for k, t in enumerate(TRADES, 1):
        v = nonincreasing(t[LEGS])
        nloss = sum(t[LOSSM])
        say("| %d | %s | %s | `%s` | %s | %s | %d | %s%s | %s | %s | %s |" % (
            k, t[NAME], "신규" if t[NEW] else "🔁후속", t[LABEL],
            "완결" if not t[OPEN_N] else "**미완결**",
            "**1**" if t[BE] else "0", len(t[LEGS]), seq(t[LEGS], t[LOSSM]),
            " **(범위만)**" if t[RANGE] else "",
            ("%d개" % nloss) if nloss else "—",
            "✅" if not v else "❌",
            "—" if not v else "; ".join("%s→%s(+%.2f%%p)" % (num(a), num(b), b - a)
                                        for _, a, b in v)))
    say("")
    say("- 라벨 집계: `TP` %d · `SL` %d · `MIX` %d · `MANUAL` %d "
        "(신규 10 = `TP` 9 + `SL` 1 · 🔁후속 2 = `MIX` 2)"
        % tuple(sum(1 for t in TRADES if t[LABEL] == x)
                for x in ("TP", "SL", "MIX", "MANUAL")))
    say("- 레그 합계 **%d**(신규 %d · 후속 %d) · 「손실률」 레그 **%d**(광전자 2 · 삼양 1 · 한라캐스트 2)"
        % (sum(len(t[LEGS]) for t in TRADES), sum(len(t[LEGS]) for t in new),
           sum(len(t[LEGS]) for t in foll), sum(sum(t[LOSSM]) for t in TRADES)))
    say("- 미완결 표지 `~` **0건**(PD-4) — 완결/미완결은 **저자 서술**로 갈랐다"
        "(「나머지 물량은 보유 중」 = 미완결 / 「전량매도」·「분할매도 완료」 = 완결).")
    say("- 🔴 **`EXIT-X6` 적용 범위 = `EXIT-E1`·`EXIT-E4` «뿐»**(`PREREG_POST6.md` §1-8) — "
        "`EXIT-X2`·`EXIT-X8` 의 「마지막 레그」는 저자 «원» 시퀀스 기준이다.")

    # ── EXIT-E1 / EXIT-X5 ───────────────────────────────────────────────
    say("")
    say("## `EXIT-E1` · `EXIT-X5` — `TP` 신규 건의 매도 레그 시퀀스가 비증가 (문턱 ≥%.0f%%)"
        % (100 * E1_MIN))
    say("")
    say("주 판정 = **서술 기준 미완결 3건**(아난티·지투파워·우리기술투자)의 **마지막 레그 하나 제외**"
        "(`EXIT-X6` · PD-4).")
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
        "(값을 보고 뺀 것이 아니라 **정의로** 빠진다)."
        % (len(e1_out), ", ".join("%s(원 레그 %d)" % (t[NAME], len(t[LEGS])) for t in e1_out)))
    say("- **`EXIT-E1` = %d/%d = %.1f%%** ⇒ **%s** (문턱 %.0f%%)"
        % (e1_ok, e1_n, ratio(e1_ok, e1_n),
           "✅ 지지" if r1 >= E1_MIN else "❌ 불성립", 100 * E1_MIN))
    say("- **`EXIT-X5`**(= `RESULTS_EXIT_V2_POST5.md` §10 의 3회째 재확인 예측) = 같은 계산 ⇒ **%s**"
        % ("✅ 적중" if r1 >= E1_MIN else "❌ 빗나감"))

    # 라벨 무관 확인
    withlegs = [t for t in TRADES if t[LEGS]]
    allv = [t for t in withlegs if nonincreasing(t[LEGS])]
    say("- 🔎 **라벨 제외 «전» %d건 전체**(원 시퀀스 · 후속·`SL` 포함): 위반 **%d건** ⇒ "
        "`SL`·`MIX` 를 빼도 넣어도 위반 수가 같다 ⇒ **라벨 결정이 `EXIT-E1` 판정을 만들지 않았다.**"
        % (len(withlegs), len(allv)))

    # ε
    used = [(t[NAME], a, b) for t in withlegs for a, b in eps_pairs(t[LEGS])]
    ties = [(t[NAME], a) for t in withlegs for a, b in zip(t[LEGS], t[LEGS][1:]) if a == b]
    say("- **ε 사용 건수 = %d회**(0 < 증가 ≤ %g%%p 인 쌍) — %s. 동률 %d쌍. "
        "최소 하락 간격은 한라캐스트 −2.87→−2.89 = **0.02%%p**(수익률 레그 한정이면 원익 13.09→13.06 = 0.03%%p)이며 "
        "**둘 다 «하락»이라 ε 이 걸리지 않는다**(ε 은 증가에만 적용)."
        % (len(used), EPS, "ε 를 넉넉히 잡아서 통과한 게 아니다" if not used else "🔴 ε 에 기댄 통과가 있다",
           len(ties)))
    say("- ⇒ **ε 은 3글 연속 사용 0회**(post4 0 · post5 0 · post6 %d). "
        "`PREREG_EXIT_V2.md` §4 의 한계(*「이 대역이 안 맞으면 ε 을 고치지 말고 그대로 판정」*)는 "
        "**아직 시험된 적이 없다**." % len(used))

    # 미완결 처리 3갈래 + `~` 기준 민감도
    say("")
    say("### 미완결 처리 민감도 — (가)(나)(다) 병기(`EXIT-X6` #17 의무) + `~` 문자 기준(PD-4)")
    say("")
    say("| 처리 | 대상 `TP` 신규 | 비증가 | 비율 | 비고 |")
    say("|---|---|---|---|---|")
    a_ok = sum(1 for t in tp_new if not nonincreasing(t[LEGS]))
    say("| (가) 전 레그 포함 = **`~` 문자 기준**(이번 글 `EXIT-X6` 적용 **0건**) | %d | %d | %.1f%% | "
        "**민감도** · post4·post5 가 실제로 쓴 처리 |" % (len(tp_new), a_ok, ratio(a_ok, len(tp_new))))
    say("| (나) 미완결 건의 **마지막 레그만** 제거 = **서술 기준** | %d | %d | %.1f%% | "
        "🟢 **주 판정값**(PD-4 · 아난티는 레그 0 ⇒ 분모 밖) |" % (e1_n, e1_ok, ratio(e1_ok, e1_n)))
    comp = [t for t in tp_new if not t[OPEN_N]]
    c_ok = sum(1 for t in comp if not nonincreasing(t[LEGS]))
    say("| (다) 미완결 건을 **통째 제외** | %d | %d | %.1f%% | 민감도 · n=%d ≥ 3 이라 이번엔 보류 조항 미발동 |"
        % (len(comp), c_ok, ratio(c_ok, len(comp)), len(comp)))
    say("")
    verdicts = {ratio(a_ok, len(tp_new)) >= 100 * E1_MIN,
                r1 >= E1_MIN, ratio(c_ok, len(comp)) / 100 >= E1_MIN}
    say("- ⇒ 세 처리가 **%s** ⇒ 판정이 처리 선택에 **%s**."
        % ("모두 같은 판정" if len(verdicts) == 1 else "서로 다른 판정",
           "의존하지 않는다" if len(verdicts) == 1 else "🔴 **의존한다 — 「표기 의존」으로 적는다**"))
    say("- 🔴 **`~` 문자 기준 vs 서술 기준**: 두 기준이 판정을 **%s** ⇒ %s."
        % ("가르지 않는다" if len(verdicts) == 1 else "가른다",
           "「표기 의존」 조항(PD-4) **미발동**" if len(verdicts) == 1 else "🔴 「표기 의존」"))
    say("- ⚠️ 레그 **1개**인 건은 비증가를 **구조적으로 자동 만족**한다(쌍이 없다). "
        "(가) 갈래의 아난티가 그 경우다 — `EXIT-E4` 가 이 자동 통과분을 걷어낸다.")

    # 생략 편향
    om_tp = sum(1 for t in tp_new if t[OPEN_N])
    om_all = sum(1 for t in new if t[OPEN_N])
    say("")
    say("### 생략 편향 비율 — 의무 인쇄(`PREREG_POST6.md` §2-3)")
    say("")
    say("- **계열 연속값(`TP` 분모)**: post4 **2/4 = 50.0%%** → post5 **4/6 = 66.7%%** → "
        "post6 **%d/%d = %.1f%%**" % (om_tp, len(tp_new), ratio(om_tp, len(tp_new))))
    say("- 병기(신규 10건 분모): **%d/%d = %.1f%%**" % (om_all, len(new), ratio(om_all, len(new))))
    say("- 동결 문언: *「생략분은 대개 뒤쪽(낮은 수익률)이라 「비증가」에 «유리한» 방향으로 편향된다」*"
        "(`RESULTS_EXIT_V2_POST5.md` §9-4). ⇒ **`EXIT-E1` 의 100%% 를 액면대로 읽지 말 것.**")
    say("- 🔴 **`EXIT-X5` 문언의 조건부 조항**: *「위반 1건이 곧 첫 반례 … 반례가 나오면 «생략 편향이 만든 100%%» "
        "가설로 먼저 의심한다」*. 이번 글 위반 **%d건** ⇒ 이 조항은 **%s**."
        % (e1_n - e1_ok, "미발동" if e1_ok == e1_n else "🔴 **발동 — 생략 편향 가설을 먼저 검토한다**"))

    # 방향 자기신고 (PD-4)
    say("")
    say("### 🔴 방향 자기신고 ①(PD-4) — `EXIT-X6` 을 서술 기준으로 «확대» 적용하는 것")
    say("")
    say("- `~` 0건인데 서술 기준으로 `EXIT-X6` 을 확대 적용하는 것은 **마지막(대개 가장 낮은) 레그를 버리는 쪽**이라 "
        "`EXIT-E1`/`EXIT-X5`(비증가 ≥ 90%)에 **유리한 방향**이다(생략 편향과 같은 방향).")
    say("- 반대로 **아난티의 분모 제외**는 분모를 줄이는 쪽이다(%d → %d). **둘 다 인쇄한다.**"
        % (len(tp_new), e1_n))

    # ── EXIT-E4 ─────────────────────────────────────────────────────────
    say("")
    say("## `EXIT-E4` (반증축) — `TP` ∧ 레그 ≥3 (`EXIT-X6` 적용 후)만으로 재계산")
    say("")
    say("`PREREG_EXIT_V2.md` §3 의 우려: *「레그 2개짜리는 비증가를 거의 자동으로 만족한다」*.")
    say("")
    say("| 종목 | `EXIT-X6` 후 레그 | 시퀀스 | 비증가 |")
    say("|---|---|---|---|")
    e4 = []
    for t in tp_new:
        L = x6_legs(t, "narr")
        if len(L) >= 3:
            e4.append((t, L))
            say("| %s | %d | %s | %s |"
                % (t[NAME], len(L), seq(L), "✅" if not nonincreasing(L) else "❌"))
    e4_ok = sum(1 for _, L in e4 if not nonincreasing(L))
    e4_n = len(e4)
    r4 = e4_ok / e4_n
    say("")
    say("| 대상 | 건수 | 비증가 | 비율 |")
    say("|---|---|---|---|")
    say("| `TP` 신규 전체(`EXIT-X6` 후 · 분모 밖 제외) | %d | %d | %.1f%% |" % (e1_n, e1_ok, ratio(e1_ok, e1_n)))
    say("| `TP` ∩ 레그 ≥3 | %d | %d | %.1f%% |" % (e4_n, e4_ok, ratio(e4_ok, e4_n)))
    say("")
    say("- 제외된 건: %s"
        % (", ".join("%s(`EXIT-X6` 후 레그 %d)" % (t[NAME], len(x6_legs(t, "narr")))
                     for t in tp_new if len(x6_legs(t, "narr")) < 3) or "없음"))
    say("- ⇒ **%s** — 두 비율이 %s(%.1f%% vs %.1f%%)."
        % ("✅ 통과 — 레그 수가 만든 결과가 아니다" if r4 == r1 else "🔴 레그 수에 의존한다",
           "같다" if r4 == r1 else "다르다", ratio(e1_ok, e1_n), ratio(e4_ok, e4_n)))

    # ── EXIT-E2 · EXIT-X2 병기 ──────────────────────────────────────────
    say("")
    say("## `EXIT-E2`(병기 · 판정 아님) · `EXIT-X2`(주 판정) — 같은 표에 인쇄 (§7-C 3 의무)")
    say("")
    say("🔴 **분모 충돌 신고**(`PREREG_POST6.md` §1-8 형식) — **두 동결 문언이 서로 다른 분모를 지시한다**:")
    say("")
    say("| 항목 | 동결 분모 | 동결 출처 | 이번 글 |")
    say("|---|---|---|---|")
    be_all = [t for t in TRADES if t[BE]]
    be_new = [t for t in be_all if t[NEW]]
    x2t = [t for t in TRADES if t[NEW] and t[LABEL] == "TP" and not t[OPEN_N]]
    say("| `EXIT-E2` | 저자가 **본전 매도**라 적은 레그(`breakeven_note`) · **라벨·등록 사건 무관** | "
        "`PREREG_EXIT_V2.md` §3 + `PREREG_POST6.md` §1-1 | **%d건**(후속 포함 · 누적 계열) / 신규만 %d |"
        % (len(be_all), len(be_new)))
    say("| `EXIT-X2` | **신규 완결 `TP`** 건 | `PREREG_POST6.md` §2-3·§7-C 4 + `LABELS_2026-08-29_post5.md` X2 절 | "
        "**%d건** |" % len(x2t))
    say("")
    say("- **정의를 어느 쪽으로도 «고치지 않는다».** 둘 다 그대로 인쇄한다(병기 의무).")
    say("")
    say("### 병기 표 — 두 규칙이 각 건에서 «어느 레그»를 고르나")
    say("")
    say("| 종목 | 구분 | 라벨 | 완결 | `be_note` | 시퀀스 | `EXIT-E2`(원 시퀀스 마지막) | `EXIT-X2`(「손실률」 제외 후 마지막) | 두 규칙이 다른가 |")
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

    # E2 판정 — 두 분모
    say("### `EXIT-E2` — 원 동결 규칙(마지막 레그) · **병기 · 주 판정 아님** (문턱 ≥%.0f%%)"
        % (100 * E2_MIN))
    say("")
    e2a_ok = sum(1 for t in be_all if abs(t[LEGS][-1]) < BE_MAX)
    e2b_ok = sum(1 for t in be_new if abs(t[LEGS][-1]) < BE_MAX)
    say("| 분모 | 건 | `\\|ret\\| < %.1f%%` | 비율 | 판정 |" % BE_MAX)
    say("|---|---|---|---|---|")
    say("| **(주 계열) `breakeven_note` 전건 — 🔁후속 «포함»** | %d | %d | **%.1f%%** | %s |"
        % (len(be_all), e2a_ok, ratio(e2a_ok, len(be_all)),
           "✅ 지지" if e2a_ok / len(be_all) >= E2_MIN else "❌ 불성립"))
    say("| (민감도) 신규만 | %d | %d | %.1f%% | %s |"
        % (len(be_new), e2b_ok, ratio(e2b_ok, len(be_new)),
           "✅ 지지" if e2b_ok / len(be_new) >= E2_MIN else "❌ 불성립"))
    say("")
    say("- 두 분모의 판정이 **%s** ⇒ %s."
        % ("같다" if (e2a_ok / len(be_all) >= E2_MIN) == (e2b_ok / len(be_new) >= E2_MIN) else "갈린다",
           "분모 선택이 `EXIT-E2` 결론을 만들지 않았다"
           if (e2a_ok / len(be_all) >= E2_MIN) == (e2b_ok / len(be_new) >= E2_MIN)
           else "🔴 **분모 의존**"))
    say("- 🔴 **방향 자기신고 ②(PD-2 5번)**: 후속 2건의 `EXIT-E2` 레그는 **−7.51 · −1.73** 이라 둘 다 "
        "`|ret| < 1%%` 를 못 넘는다 ⇒ **후속 «제외»는 `EXIT-E2` 에 «유리한» 방향**이다. "
        "그래서 누적 계열은 **포함(%d)**으로 잇고 제외(%d)는 민감도로만 인쇄한다."
        % (len(be_all), len(be_new)))
    say("- 🔑 **세 글 연속 «같은 자리»에서 깨진다** — 저자가 마지막 값(들)만 낱말을 「손실률」로 바꿔 적었고, "
        "「마지막 레그」 규칙이 그 값을 본전매도로 강제 지목한다(post4 PS일렉 −2.76 · post5 한켐 −2.12 · "
        "post6 광전자 −7.51 · 삼양 −1.73). **규칙은 고치지 않는다.**")

    # X2 판정
    say("")
    say("### `EXIT-X2` — **주 판정**(「손실률」 레그 제외 후 «원 시퀀스» 마지막) · 신규 완결 `TP` (문턱 ≥%.0f%%)"
        % (100 * E2_MIN))
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
    say("- **`EXIT-X2` = %d/%d = %.1f%%** ⇒ **%s** (문턱 %.0f%% · 최소 n = 완결 `TP` 3 ⇒ %d ≥ 3 이라 **보류 아님**)"
        % (x2_ok, x2_n, ratio(x2_ok, x2_n),
           "✅ 지지" if r22 >= E2_MIN else "❌ 불성립", 100 * E2_MIN, x2_n))
    say("- 🔴 **방향 자기신고 ③(PD-6)**: 좁은 분모(신규 완결 `TP` ∧ `be_note`)는 **전량 익절 건**"
        "(마지막 레그가 본전에서 먼 건)을 분모에서 빼므로 **`EXIT-X2` 에 «유리한» 방향**이다. "
        "동결(넓은) 분모를 주 판정으로 쓰는 이 결정은 **`EXIT-X2` 에 «불리한» 방향**이다.")
    say("")
    say("#### `EXIT-X2` 민감도 (의무 인쇄 · 판정에 «안» 쓴다)")
    say("")
    say("| 갈래 | 분모 | 적중 | 비율 | 판정 | 비고 |")
    say("|---|---|---|---|---|---|")
    say("| **주 판정** 신규 완결 `TP` | %d | %d | %.1f%% | %s | 동결 문언(§2-3·§7-C 4) |"
        % (x2_n, x2_ok, ratio(x2_ok, x2_n), "✅" if r22 >= E2_MIN else "❌"))
    sa = [t for t in x2t if t[BE]]
    sa_ok = sum(1 for t in sa if abs(x2_leg(t[LEGS], t[LOSSM])[0]) < BE_MAX)
    say("| (a) 신규 완결 `TP` ∧ `be_note` | %d | %d | %.1f%% | %s | 🔴 `EXIT-X2` 에 **유리한** 방향 |"
        % (len(sa), sa_ok, ratio(sa_ok, len(sa)), "✅" if sa_ok / len(sa) >= E2_MIN else "❌"))
    sb = x2t + foll
    sb_ok = sum(1 for t in sb if abs(x2_leg(t[LEGS], t[LOSSM])[0]) < BE_MAX)
    say("| (b) 🔁후속 `MIX` 포함 | %d | %d | %.1f%% | %s | 🔴 **동결 적용 대상(「`TP` 완결 건」) «밖»의 확장 민감도** |"
        % (len(sb), sb_ok, ratio(sb_ok, len(sb)), "✅" if sb_ok / len(sb) >= E2_MIN else "❌"))
    say("")
    say("- (b) 의 후속 2건 `EXIT-X2` 레그 = 광전자 **%s** · 삼양바이오팜 **%s**(둘 다 `|ret| < 1%%`)."
        % (num(x2_leg(foll[0][LEGS], foll[0][LOSSM])[0]),
           num(x2_leg(foll[1][LEGS], foll[1][LOSSM])[0])))
    say("- 세 갈래의 판정이 **%s** ⇒ %s."
        % ("모두 같다" if len({r22 >= E2_MIN, sa_ok / len(sa) >= E2_MIN,
                             sb_ok / len(sb) >= E2_MIN}) == 1 else "갈린다",
           "분모 선택이 `EXIT-X2` 결론을 만들지 않았다"
           if len({r22 >= E2_MIN, sa_ok / len(sa) >= E2_MIN, sb_ok / len(sb) >= E2_MIN}) == 1
           else "🔴 **후속 의존 — 지지 선언 금지**(PD-2 3번)"))
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
    say("## `EXIT-X8` (반증축 · `EXIT-X3` 폐지분 대체) — `EXIT-X2` 가 고른 레그 ≠ 마지막 레그인 건 수")
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
    say("- 주 분모(%d건) 안 **%d건** — 주 분모엔 「손실률」 레그가 **0개**라 두 규칙이 **구성상** 같은 레그를 고른다."
        % (x2_n, x8))
    say("- ⇒ %s (`EXIT-X8` 동결 문언: *「그 수가 0 이면 여전히 「구분 불가」로 적는다」*)."
        % ("⛔ **두 규칙 구분 불가**" if x8 == 0 else "**두 규칙이 구분된다**"))
    x8b = sum(1 for t in foll if x2_leg(t[LEGS], t[LOSSM])[0] != t[LEGS][-1])
    say("- **민감도(🔁후속 포함)**: 분모 %d건(주 %d + 후속 %d) 중 **%d건** — 후속 2건에서는 "
        "「손실률」 레그가 있어 두 규칙이 **다른 레그를 고른다**(광전자 %s vs %s · 삼양바이오팜 %s vs %s). "
        "즉 **민감도에서만 「구분 가능」**이다 — 그대로 인쇄한다(판정은 주 분모의 「구분 불가」)."
        % (x2_n + len(foll), x2_n, len(foll), x8b,
           num(x2_leg(foll[0][LEGS], foll[0][LOSSM])[0]), num(foll[0][LEGS][-1]),
           num(x2_leg(foll[1][LEGS], foll[1][LOSSM])[0]), num(foll[1][LEGS][-1])))
    say("- 🔴 ***`EXIT-X2` 의 「지지/불성립」은 `EXIT-X8` > 0 이 되기 전까지 「`EXIT-X2` 가 «작동»한다」의 "
        "증거가 아니다***(§7-C 3).")

    # ── EXIT-E3 / EXIT-X7 ───────────────────────────────────────────────
    say("")
    say("## `EXIT-E3` · `EXIT-X7` — `SL` 건의 손절 레그 비증가 (ε 동일) · ⛔ **판정 불가**")
    say("")
    sl = [t for t in TRADES if t[LABEL] == "SL"]
    say("**동결 문언 두 개가 충돌한다**(§1-8 형식 신고 · `EXIT-E2`↔`EXIT-X2` 와 같은 틀):")
    say("")
    say("| 동결본 | 문언 | 이번 글에 대한 함의 |")
    say("|---|---|---|")
    say("| `PREREG_POST6.md` §2-3(`EXIT-X7` 재동결 인용) | *「`SL` 건이 **시퀀스로**"
        "(값 2개 이상, 범위 아님) 적히면 E3(손절 레그 비증가, ε 동일)를 **판정한다**」* | "
        "조건 충족(값 2개 · 범위 아님) ⇒ **판정** |")
    say("| `PREREG_POST6.md` §4 표 **#19** | 최소 n = **`SL` 시퀀스 3** · "
        "⛔ 판정 불가 조건 = **범위만 · 시퀀스 < 3** | 시퀀스 **%d < 3** ⇒ **⛔ 판정 불가** |" % len(sl))
    say("")
    say("🔴 **둘 다 동결이다.** §3 이 *「각 항목은 … **최소 n · 판정 불가 조건**을 전부 적는다」*라고 "
        "못박았으므로 §4 표의 그 두 열은 **구속력이 있다** ⇒ **이번 글은 §4 #19 로 ⛔ 판정 불가**로 적는다. "
        "**문언 통일은 다음 사전등록에서** 한다(결과를 보고 어느 쪽으로도 «고치지 않는다»).")
    say("🟢 **⛔ 는 «선언» 금지이지 «인쇄» 금지가 아니다** — 관측값과 n 은 그대로 인쇄한다.")
    say("")
    say("| 종목 | 라벨 | 완결 | 전 시퀀스 | 손절(「손실률」) 레그 | 간격 | 비증가 | 위반 |")
    say("|---|---|---|---|---|---|---|---|")
    e3_ok, e3_n = 0, 0
    for t in sl:
        loss = [v for v, m in zip(t[LEGS], t[LOSSM]) if m]
        v = nonincreasing(loss)
        e3_n += 1
        e3_ok += (not v)
        gaps = "; ".join("%+.2f%%p" % (b - a) for a, b in zip(loss, loss[1:])) or "—"
        say("| %s | `%s` | %s | %s | **%s** | %s | %s | %s |"
            % (t[NAME], t[LABEL], "**미완결**" if t[OPEN_N] else "완결",
               seq(t[LEGS], t[LOSSM]), seq(loss), gaps,
               "✅" if not v else "❌", "0" if not v else str(len(v))))
    say("")
    say("- **판정 = ⛔ 판정 불가**(`SL` 시퀀스 **%d < 3** · `PREREG_POST6.md` §4 #19 최소 n) — "
        "「지지」도 「불성립」도 **선언하지 않는다**." % e3_n)
    say("- **관측(인쇄 · 판정 아님)**: `EXIT-E3` = **%d/%d** · **n = %d** — "
        "한라캐스트 −2.87 → −2.89(간격 −0.02%%p · 비증가 위반 0). 누적은 판정이 열린 뒤부터."
        % (e3_ok, e3_n, e3_n))
    say("- 🔴 **`EXIT-X7` 조건 자체는 이번 글에서 처음 충족됐다**(post4 `SL` 0건 ⇒ ⛔ · "
        "post5 `SL` 1건이나 **범위만** ⇒ ⛔ · post6 시퀀스 %d건이나 **§4 #19 최소 n 미달** ⇒ ⛔). "
        "***사유가 세 번 다 다르다*** — 표본이 생긴 것과 판정이 가능해진 것은 다르다." % len(sl))
    say("- **`EXIT-X6` 미적용**(적용 범위 = E1·E4 뿐 · §1-8) — 한라캐스트는 **미완결**이나 손절 레그 2개를 "
        "**그대로** 쓴다. 미완결 사실만 병기한다.")
    say("- ε 사용 **0회**(간격 −0.02%p = 하락 ⇒ ε 은 걸리지 않는다).")
    say("- 🔴 **방향 자기신고 ④**: 두 손절 레그의 순서는 저자 문장에 **그대로 보인다** — "
        "⛔ 로 적으면서 관측을 **안 적는** 선택은 그것을 **숨기는 쪽**이었다. "
        "그래서 **판정은 §4 #19 대로 ⛔, 관측값은 그대로 인쇄**한다. "
        "🔴 반대 방향도 적는다: `EXIT-X7` 문언만 읽어 «판정»했다면 **n=1 짜리 100%** 가 "
        "산출물에 남았을 것이다 — ⛔ 는 그 쪽을 막는다.")

    # ── EXIT-X9 ─────────────────────────────────────────────────────────
    say("")
    say("## `EXIT-X9` — `MANUAL` 안의 자동 사이클 (관측 · 판정 아님)")
    say("")
    man = [t for t in TRADES if t[LABEL] == "MANUAL"]
    say("- 이번 글 `MANUAL` **%d건** ⇒ 한켐형(*「자동으로 본전매도 → 이후 직접 매도」*) 관측 **0건**." % len(man))
    say("- **누적 = %d건**(post5 %d + post6 0) — 3건 이상 쌓이면 그때 *「사이클 단위 라벨링」*을 "
        "**값을 보기 «전»에** 사전등록한다. **라벨 규약(「한 항목 = 한 라벨」)은 바꾸지 않는다.**"
        % (POST5["X9"] + 0, POST5["X9"]))

    # ── 누적표 ──────────────────────────────────────────────────────────
    say("")
    say("## 누적 집계 — `EXIT-E1` · `EXIT-E4` · `EXIT-E2`(두 분모) · `EXIT-X2` · `EXIT-X8`")
    say("")
    say("| 글 | `EXIT-E1` | `EXIT-E4` | `EXIT-E2`(후속 포함) | `EXIT-E2`(신규만) | `EXIT-X2` | `EXIT-X8` |")
    say("|---|---|---|---|---|---|---|")
    say("| 4번째(2026-08-22) *동결 인용* | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | — (동결만) | — |"
        % (POST4["E1_ok"], POST4["E1_n"], ratio(POST4["E1_ok"], POST4["E1_n"]),
           POST4["E4_ok"], POST4["E4_n"], ratio(POST4["E4_ok"], POST4["E4_n"]),
           POST4["E2_ok"], POST4["E2_n"], ratio(POST4["E2_ok"], POST4["E2_n"]),
           POST4["E2_ok"], POST4["E2_n"], ratio(POST4["E2_ok"], POST4["E2_n"])))
    say("| 5번째(2026-08-29) *동결 인용* | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d |"
        % (POST5["E1_ok"], POST5["E1_n"], ratio(POST5["E1_ok"], POST5["E1_n"]),
           POST5["E4_ok"], POST5["E4_n"], ratio(POST5["E4_ok"], POST5["E4_n"]),
           POST5["E2_ok"], POST5["E2_n"], ratio(POST5["E2_ok"], POST5["E2_n"]),
           POST5["E2_ok"], POST5["E2_n"], ratio(POST5["E2_ok"], POST5["E2_n"]),
           POST5["X2_ok"], POST5["X2_n"], ratio(POST5["X2_ok"], POST5["X2_n"]),
           POST5["X8"], POST5["X8_n"]))
    say("| **6번째(2026-09-04) 이번** | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% | %d/%d |"
        % (e1_ok, e1_n, ratio(e1_ok, e1_n), e4_ok, e4_n, ratio(e4_ok, e4_n),
           e2a_ok, len(be_all), ratio(e2a_ok, len(be_all)),
           e2b_ok, len(be_new), ratio(e2b_ok, len(be_new)),
           x2_ok, x2_n, ratio(x2_ok, x2_n), x8, x2_n))
    c = {}
    c["E1"] = (POST4["E1_ok"] + POST5["E1_ok"] + e1_ok, POST4["E1_n"] + POST5["E1_n"] + e1_n)
    c["E4"] = (POST4["E4_ok"] + POST5["E4_ok"] + e4_ok, POST4["E4_n"] + POST5["E4_n"] + e4_n)
    c["E2a"] = (POST4["E2_ok"] + POST5["E2_ok"] + e2a_ok, POST4["E2_n"] + POST5["E2_n"] + len(be_all))
    c["E2b"] = (POST4["E2_ok"] + POST5["E2_ok"] + e2b_ok, POST4["E2_n"] + POST5["E2_n"] + len(be_new))
    c["X2"] = (POST5["X2_ok"] + x2_ok, POST5["X2_n"] + x2_n)
    c["X8"] = (POST5["X8"] + x8, POST5["X8_n"] + x2_n)
    say("| **누적** | **%d/%d = %.1f%%** | **%d/%d = %.1f%%** | **%d/%d = %.1f%%** | **%d/%d = %.1f%%** | **%d/%d = %.1f%%** | **%d/%d** |"
        % (c["E1"][0], c["E1"][1], ratio(*c["E1"]), c["E4"][0], c["E4"][1], ratio(*c["E4"]),
           c["E2a"][0], c["E2a"][1], ratio(*c["E2a"]), c["E2b"][0], c["E2b"][1], ratio(*c["E2b"]),
           c["X2"][0], c["X2"][1], ratio(*c["X2"]), c["X8"][0], c["X8"][1]))
    say("")
    say("- 누적 `EXIT-E1` **%d/%d = %.1f%%** ⇒ **%s**(문턱 %.0f%%) · "
        "누적 `EXIT-E4` **%d/%d = %.1f%%** ⇒ **%s**"
        % (c["E1"][0], c["E1"][1], ratio(*c["E1"]),
           "✅ 지지" if c["E1"][0] / c["E1"][1] >= E1_MIN else "❌ 불성립", 100 * E1_MIN,
           c["E4"][0], c["E4"][1], ratio(*c["E4"]),
           "✅ 통과" if ratio(*c["E4"]) == ratio(*c["E1"]) else "🔴 레그 수 의존"))
    say("- 누적 `EXIT-E2` **%d/%d = %.1f%%**(후속 포함) / **%d/%d = %.1f%%**(신규만) ⇒ "
        "**3글 연속 불성립** · 누적 `EXIT-X2` **%d/%d = %.1f%%** ⇒ **%s**"
        % (c["E2a"][0], c["E2a"][1], ratio(*c["E2a"]), c["E2b"][0], c["E2b"][1], ratio(*c["E2b"]),
           c["X2"][0], c["X2"][1], ratio(*c["X2"]),
           "✅ 지지" if c["X2"][0] / c["X2"][1] >= E2_MIN else "❌ 불성립"))
    say("- 누적 `EXIT-X8` **%d/%d** ⇒ **%s** — 두 글 연속 주 분모에서 두 규칙이 갈린 적이 «없다»."
        % (c["X8"][0], c["X8"][1],
           "⛔ 구분 불가" if c["X8"][0] == 0 else "구분 가능"))
    say("")
    say("### 🔴 누적 분모에 대한 자기신고 (판정은 안 바꾼다)")
    say("")
    say("1. **3번째 글(2026-08-14)은 누적 분모에 «없다»** — `PREREG_EXIT_V2.md` 는 2026-08-15 동결이고 "
        "§1 이 *「이 문서가 구속하는 것은 **다음 글의 신규 건**뿐」* · *「v1 의 기각은 기각으로 둔다」*고 "
        "못박았다. 3번째 글엔 동결된 기전 라벨 파일도 없다.")
    say("2. 🔴 **`EXIT-E1` 누적은 «같은 처리»의 합이 아니다** — post4·post5 는 (가) 전 레그 포함으로 쟀고, "
        "post6 은 `EXIT-X6`(서술 기준)을 처음 적용했다. `EXIT-X6` 은 *「다음 글부터」*로 동결됐으므로 "
        "**규칙대로 발효한 것**이지만, 누적 비율은 그만큼 «두 처리의 합»이다. "
        "🟢 이번 글은 (가) 갈래도 %d/%d = %.1f%% 라 **누적이 어느 갈래로도 %d/%d = 100.0%%** 로 같다 ⇒ "
        "이번 회차에선 무해했다. **다음 글에서 갈릴 수 있다.**"
        % (a_ok, len(tp_new), ratio(a_ok, len(tp_new)),
           POST4["E1_n"] + POST5["E1_n"] + len(tp_new), POST4["E1_n"] + POST5["E1_n"] + len(tp_new)))
    say("3. `EXIT-E2` 의 두 계열은 post4·post5 에 «후속» 개념이 없었으므로 그 두 항이 **동일**하다 — "
        "차이는 post6 항(%d/%d vs %d/%d)에서만 생긴다."
        % (e2a_ok, len(be_all), e2b_ok, len(be_new)))
    say("4. `EXIT-X2` 누적의 post5 항은 **n=2** 였다(`RESULTS_EXIT_V2_POST5.md` §9-2). "
        "누적 %d 도 여전히 작다." % c["X2"][1])

    # ── 민감도: 한라캐스트 ──────────────────────────────────────────────
    say("")
    say("## 민감도 — 한라캐스트 `SL` 의 약한 결정 두 갈래 (🔴 판정에 «안» 쓴다)")
    say("")
    say("`LABELS_2026-09-04_post6.md` §약한 결정: 저자가 「분할손절」이라 쓰진 않았고 「보유 중」인데 "
        "손실 레그가 있다. 그래도 판별표 낱말 「손실률」이 **직접 해당**하고 본전 서술이 없어 `SL` 로 동결했다.")
    say("")
    hr = [t for t in TRADES if t[NAME] == "한라캐스트"][0]
    alt_x6 = x6_legs(hr, "narr")
    say("### ① 「`TP` 로 읽을 때」 — `EXIT-E1` 에는 손실 레그 제외 규칙이 «없다»")
    say("")
    say("| 축 | 동결 판정 | 한라캐스트를 `TP` 로 볼 때 | 뒤집히나 |")
    say("|---|---|---|---|")
    a1_ok = e1_ok + (0 if nonincreasing(alt_x6) else 1)
    a1_n = e1_n + 1
    say("| `EXIT-E1`(서술 기준 · 주) | %d/%d = %.1f%% %s | %d/%d = %.1f%% %s (`EXIT-X6` 후 %s) | %s |"
        % (e1_ok, e1_n, ratio(e1_ok, e1_n), "✅" if r1 >= E1_MIN else "❌",
           a1_ok, a1_n, ratio(a1_ok, a1_n), "✅" if a1_ok / a1_n >= E1_MIN else "❌",
           seq(alt_x6),
           "**아니오**" if (a1_ok / a1_n >= E1_MIN) == (r1 >= E1_MIN) else "🔴 **예**"))
    b1_ok = a_ok + (0 if nonincreasing(hr[LEGS]) else 1)
    b1_n = len(tp_new) + 1
    say("| `EXIT-E1`(`~` 문자 기준 · 민감도) | %d/%d = %.1f%% %s | %d/%d = %.1f%% %s (전 4레그) | %s |"
        % (a_ok, len(tp_new), ratio(a_ok, len(tp_new)), "✅" if a_ok / len(tp_new) >= E1_MIN else "❌",
           b1_ok, b1_n, ratio(b1_ok, b1_n), "✅" if b1_ok / b1_n >= E1_MIN else "❌",
           "**아니오**" if (b1_ok / b1_n >= E1_MIN) == (a_ok / len(tp_new) >= E1_MIN) else "🔴 **예**"))
    c1_ok = e4_ok + (0 if nonincreasing(alt_x6) else 1)
    c1_n = e4_n + 1
    say("| `EXIT-E4`(레그 ≥3) | %d/%d = %.1f%% %s | %d/%d = %.1f%% %s (`EXIT-X6` 후 %d레그 ⇒ 포함) | %s |"
        % (e4_ok, e4_n, ratio(e4_ok, e4_n), "✅" if r4 >= E1_MIN else "❌",
           c1_ok, c1_n, ratio(c1_ok, c1_n), "✅" if c1_ok / c1_n >= E1_MIN else "❌",
           len(alt_x6),
           "**아니오**" if (c1_ok / c1_n >= E1_MIN) == (r4 >= E1_MIN) else "🔴 **예**"))
    say("")
    hx, hp = x2_leg(hr[LEGS], hr[LOSSM])
    say("### ② 「`EXIT-X2` 규칙을 적용하면 남는 레그」 — **별도 항목**(본 판정에 «안» 들어간다)")
    say("")
    say("- 「손실률」 레그(%s) 제외 후 남는 레그 = **%s** ⇒ `EXIT-X2` 가 고를 값 = **%s**"
        "(`|ret|` = %.2f ⇒ %s)."
        % (seq([v for v, m in zip(hr[LEGS], hr[LOSSM]) if m]),
           seq([v for v, m in zip(hr[LEGS], hr[LOSSM]) if not m]), num(hx), abs(hx),
           "✅" if abs(hx) < BE_MAX else "❌"))
    say("- 🔴 그러나 `EXIT-X2` 의 동결 적용 대상은 **완결 `TP`** 이고 한라캐스트는 **`SL` ∧ 미완결**이라 "
        "**본 판정에 들어가지 않는다**. 값만 적어 둔다.")
    say("")
    say("- 🔴 두 갈래 중 어느 것도 **판정에 쓰지 않는다**. 동결 라벨은 `SL` 이다.")

    # ── 연결 시퀀스 (기록만) ────────────────────────────────────────────
    say("")
    say("## 연결 시퀀스 — 🔁후속 2건 (PD-2 4번 · **기록만** · 어떤 판정에도 안 쓴다)")
    say("")
    for t in foll:
        prev = POST5_SEQ[t[NAME]]
        say("- **%s**: post5 [%s] + post6 [%s] = **%d레그** — 🔴 **기록만**."
            % (t[NAME], seq(prev), seq(t[LEGS], t[LOSSM]), len(prev) + len(t[LEGS])))
    say("- 🔴 이어 붙이지 않는 이유(PD-2 4번): 삼양바이오팜은 **2차 매수 «후» 레그**라 「하나의 평단」 전제가 "
        "깨지고, 광전자도 post5 **4차 매수 상태의 후속**이라 평단 불변 보장이 없다 ⇒ `REC-` 축에도, "
        "비증가 판정 어디에도 넣지 않는다.")

    # ── RANGE_ONLY 규약 ────────────────────────────────────────────────
    say("")
    say("## `RANGE_ONLY` 규약 (PD-10 · `PREREG_POST6.md` §8-2 가 지시한 못박기)")
    say("")
    rng = [t for t in TRADES if t[RANGE]]
    say("- 동결 규약: **「A% ~ B%」 범위만 적힌 건은 어떤 «비증가 「건」 분모»에도 계상하지 않는다** — "
        "`EXIT-E1`/`E3`/`E4`/`X5`/`X7` 의 분모·분자 **모두 밖** · 값(범위 양끝)만 원장에 기록.")
    say("- 근거: `EXIT-X7` *「범위 서술은 시퀀스로 «승격하지 않는다»」*의 귀결 — 시퀀스가 아닌 것은 "
        "「비증가」의 정의역 밖이다.")
    say("- 🟢 **이번 글 해당 %d건** — 판정에 영향 없는 시점에 못박았다(사후적합 위험 0). "
        "한라캐스트의 −2.87, −2.89 는 «값 2개»라 범위가 **아니다**." % len(rng))

    # ── 모호 지점 ──────────────────────────────────────────────────────
    say("")
    say("## 🔴 모호 지점 — 양쪽 인쇄 (규칙을 고치지 않는다)")
    say("")
    say("| # | 모호한 것 | 갈래 A | 갈래 B | 판정이 갈리나 |")
    say("|---|---|---|---|---|")
    say("| 1 | `EXIT-X6` 기준(`~` 문자 0건 vs 서술) | `~` 기준 %d/%d = %.1f%% | 서술 기준 %d/%d = %.1f%% | **아니오**(둘 다 지지) |"
        % (a_ok, len(tp_new), ratio(a_ok, len(tp_new)), e1_ok, e1_n, ratio(e1_ok, e1_n)))
    say("| 2 | `EXIT-E2` ↔ `EXIT-X2` 분모 충돌(동결 문언 둘) | `be_note` %d건 | 신규 완결 `TP` %d건 | "
        "**해당 없음** — 서로 다른 항목이라 둘 다 인쇄(병기 의무) |" % (len(be_all), len(x2t)))
    say("| 3 | `EXIT-E2` 누적 계열(후속 포함/제외) | %d/%d = %.1f%% | %d/%d = %.1f%% | **아니오**(둘 다 불성립) |"
        % (c["E2a"][0], c["E2a"][1], ratio(*c["E2a"]), c["E2b"][0], c["E2b"][1], ratio(*c["E2b"])))
    say("| 4 | `EXIT-X2` 분모(주/좁은/후속 포함) | 주 %d/%d · (a) %d/%d | (b) %d/%d | **아니오**(셋 다 불성립) |"
        % (x2_ok, x2_n, sa_ok, len(sa), sb_ok, len(sb)))
    say("| 5 | `EXIT-E1` 누적이 «두 처리»의 합 | (가) 기준 누적 %d/%d | `EXIT-X6` 기준 누적 %d/%d | "
        "**아니오**(둘 다 100.0%%) — 다음 글에서 갈릴 수 있다 |"
        % (POST4["E1_ok"] + POST5["E1_ok"] + a_ok, POST4["E1_n"] + POST5["E1_n"] + len(tp_new),
           c["E1"][0], c["E1"][1]))
    say("| 6 | 값 표기(2자리 고정 vs post5 `%g`) | `0.50`·`3.70` | `0.5`·`3.7` | **값 동일 · 표기만 다름** |")
    say("| 7 | 🔴 **`EXIT-X7` ↔ §4 #19 충돌**(동결 문언 둘) | §2-3 `EXIT-X7`: 시퀀스면 **판정** | "
        "§4 #19: 시퀀스 < 3 ⇒ **⛔** | 🔴 **예 — 갈린다.** 이번은 **§4 #19 로 ⛔** · "
        "관측 1/1 은 인쇄 · 문언 통일은 다음 사전등록 |")
    say("")
    say("- 🟢 #1~#6 은 **판정을 가르지 않는다**. 🔴 **#7 은 가른다** — 그래서 `EXIT-E3`/`X7` 은 "
        "동결 문언 두 개 중 **§4 #19(⛔)** 를 따르고 **지지/불성립을 선언하지 않았다**. "
        "가르는 항목이 더 나오면 같은 틀로 「표기 의존」·「분모 의존」·「후속 의존」으로 적고 "
        "**지지 선언을 하지 않는다**(PD-2 3번·PD-4).")

    # ── 한계 ────────────────────────────────────────────────────────────
    say("")
    say("## 미리 적어두는 한계 (승계 + 이번 회차 고유)")
    say("")
    say("1. 🔴 **ε = %g%%p 가 3글 연속 사용 0회** — 값을 정한 근거(근접쌍 8건)는 **첫 표본**에서 왔고, "
        "이 대역이 실제로 필요한 적이 아직 없다. `PREREG_EXIT_V2.md` §4 대로 **고치지 않는다**." % EPS)
    say("2. 🔴 **생략 편향** — `TP` 신규 %d건 중 %d건이 미완결이다. 생략분은 대개 뒤쪽(낮은 수익률)이라 "
        "「비증가」에 «유리한» 방향이다." % (len(tp_new), om_tp))
    say("3. 🔴 **`EXIT-X2` 의 반증축이 두 글 연속 「구분 불가」** — 주 분모에서 「손실률」 레그가 0개라 "
        "두 규칙이 구성상 같은 레그를 고른다. `EXIT-X2` 의 결과는 「`EXIT-X2` 가 작동한다」의 증거가 아니다.")
    say("4. 🔴 **`EXIT-E3` ⛔ 판정 불가**(시퀀스 1 < 3 · §4 #19) — 관측 1/1 은 인쇄하되 "
        "지지/불성립을 선언하지 않는다. 🔴 **`EXIT-X7` 문언과 §4 #19 의 충돌은 «미해소»**다 — "
        "이번엔 §4 #19 로 ⛔ 를 적었고, **문언 통일은 다음 사전등록**의 몫이다.")
    say("5. 🔴 **저자가 레그별 시각·수량을 안 적는다.** 「시퀀스 순서 = 체결 순서」는 여전히 **가정**이다.")
    say("6. 🔴 **🔁후속 2건의 「지난주」가 어느 주인지 본문으로 확정할 수 없다**(PD-2) — "
        "「이번 주」라고 쓰지 않는다.")
    say("7. 🔴 **`EXIT-E1` 90%% 문턱은 %d건 분모에서 사실상 「위반 0건」과 같다** — "
        "위반 1건이면 %.1f%% %s 90%% 라 곧바로 불성립이다. 누적 %d건도 마찬가지 성질이다."
        % (e1_n, ratio(e1_n - 1, e1_n),
           "≥" if ratio(e1_n - 1, e1_n) >= 100 * E1_MIN else "<", c["E1"][1]))
    say("8. 이 분석은 **라이브 채택 대상이 아니다**(`PREREG.md` §0-2).")
    say("")
    say("[[LABELS_2026-09-04_post6]] · [[INTAKE_2026-09-04_post6]] · [[PREDECISION_2026-09-04_post6]] · "
        "[[PREREG_POST6]] · [[PREREG_EXIT_V2]] · [[RESULTS_EXIT_V2_POST5]] · [[RESULTS_EXIT_V2_POST4]]")

    (BASE / "RESULTS_EXIT_V2_POST6_NUMBERS.md").write_text("\n".join(OUT) + "\n",
                                                           encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""PREREG_EXIT_V2.md §3 + RESULTS_EXIT_V2_POST4.md §5(X1~X3) 실행 — 5번째 글 신규 건.

라벨은 `LABELS_2026-08-29_post5.md`에서 **계산 전에** 확정된 것을 그대로 옮긴다
(`TP` 6 · `MANUAL` 2 · `SL` 1 · `MIX` 0). 레그 수익률은 저자 본문
(`post_224393392105.txt`)에 적힌 순서·값 그대로다. 「손실률」로 적힌 레그는
`loss_mask` 에 저자 낱말 그대로 표시해 둔다(X2 가 이걸 쓴다).

`run_exit_v2_post4.py` 승계. DB 를 읽지 않는다(저자 서술만 쓴다) ⇒ 결정적이고
DB 스냅샷에 의존하지 않는다. 라이브 트리 import 0건.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT: list = []

EPS = 0.05          # 사전등록 §2: 허용 오차 0.05%p (동결분, 고치지 않는다)
E1_MIN = 0.90       # 사전등록 §3 E1 / POST4 §5 X1: TP 건의 90% 이상
E2_MIN = 0.80       # 사전등록 §3 E2 / POST4 §5 X2: 4/5 이상 = 80%
BE_MAX = 1.0        # 사전등록 §3 E2: 본전 매도 레그의 |ret| < 1.0%

# 4번째 글 동결 결과 — 누적 집계용 인용값 (RESULTS_EXIT_V2_POST4_NUMBERS.md)
POST4 = {"E1_ok": 4, "E1_n": 4, "E4_ok": 3, "E4_n": 3}

# (종목, 라벨, 레그 수익률, 생략표시「~」, 본전매도 서술, 「손실률」레그 마스크, 범위만)
TRADES = [
    ("혜인",             "TP",     [21.91, 21.90, 21.67, 19.32, 14.68], True,  False,
     [0, 0, 0, 0, 0], False),
    ("한국화장품제조",   "TP",     [19.02, 18.64, 15.42, 12.50, 11.26], True,  False,
     [0, 0, 0, 0, 0], False),
    ("코데즈컴바인",     "TP",     [7.82, 0.09],                        False, True,
     [0, 0], False),
    ("한켐",             "MANUAL", [4.86, 0.84, -2.08, -2.12],          False, True,
     [0, 0, 1, 1], False),
    ("삼양바이오팜",     "TP",     [11.50, 11.50],                      True,  False,
     [0, 0], False),
    ("광전자",           "TP",     [15.81, 9.21, 9.21, 6.99, 0.93],     True,  False,
     [0, 0, 0, 0, 0], False),
    ("레메디",           "TP",     [5.09, 5.01, 0.43],                  False, True,
     [0, 0, 0], False),
    ("한성기업",         "SL",     [-16.25, -37.48],                    False, False,
     [1, 1], True),   # 🔴 범위만(−16.25 ~ −37.48) — 시퀀스가 아니다
    ("SK아이이테크놀로지", "MANUAL", [],                                False, False,
     [], False),
]

NAME, LABEL, LEGS, TRUNC, BE, LOSSM, RANGE = range(7)

# 3번째 글(2026-08-14) — 참고용. v1 로 판정돼 기각됐고 v2 동결 라벨이 «없다».
POST3_RAW = [
    ("케이엔알시스템", [26.71, 24.03, 24.00, 21.74]),
    ("에스피지",       [21.44, 18.51, 12.03]),
    ("솔트룩스",       [16.20, 16.10, 10.63, 0.68]),
    ("마키나락스",     [16.58, 11.99, 10.55]),
    ("매드업",         [8.77, 0.40]),
    ("빛과전자",       [8.66, 0.34]),
    ("씨피시스템",     [9.29, 3.26, 3.24, 0.43, 0.42]),
]


def say(s=""):
    print(s)
    OUT.append(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def nonincreasing(legs):
    """ε 이내의 증가는 위반으로 세지 않는다(사전등록 §3 E1). 위반 쌍 목록을 돌려준다."""
    return [(i, legs[i], legs[i + 1])
            for i in range(len(legs) - 1) if legs[i + 1] - legs[i] > EPS]


def seq(legs):
    return ", ".join("%g" % x for x in legs)


def x2_leg(legs, mask):
    """X2 동결 규칙: 「손실률」로 적힌 레그를 뺀 뒤 남은 레그 중 **마지막**.
    돌려주는 값 = (레그값, 원 시퀀스에서의 0-기반 위치) · 남는 게 없으면 (None, None)."""
    kept = [(i, v) for i, (v, m) in enumerate(zip(legs, mask)) if not m]
    if not kept:
        return None, None
    return kept[-1][1], kept[-1][0]


def main():
    say("# RESULTS_EXIT_V2_POST5_NUMBERS — 기계 생성 (수정 금지)")
    say("")
    say("사전등록 `PREREG_EXIT_V2.md` §3 + `RESULTS_EXIT_V2_POST4.md` §5(X1~X3) · "
        "라벨 `LABELS_2026-08-29_post5.md` · 생성 `run_exit_v2_post5.py`")
    say("허용 오차 ε = %g%%p · **DB 미사용**(저자 서술만) ⇒ DB 스냅샷 무관 · 결정적"
        % EPS)
    say("")

    # ---------------- 원표 ------------------------------------------------
    say("## 원표 — 5번째 글 9건 (라벨은 계산 «전» 동결)")
    say("")
    say("| # | 종목 | 라벨 | 레그 수 | 시퀀스 | 「손실률」레그 | 생략`~` | 비증가 | 위반 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for k, t in enumerate(TRADES, 1):
        if not t[LEGS]:
            say("| %d | %s | `%s` | 0 | — | — | — | — | 레그 없음 |"
                % (k, t[NAME], t[LABEL]))
            continue
        v = nonincreasing(t[LEGS])
        nloss = sum(t[LOSSM])
        say("| %d | %s | `%s` | %d | %s%s | %s | %s | %s | %s |" % (
            k, t[NAME], t[LABEL], len(t[LEGS]), seq(t[LEGS]),
            " **(범위만)**" if t[RANGE] else "",
            ("%d개" % nloss) if nloss else "—",
            "**있음**" if t[TRUNC] else "—",
            "✅" if not v else "❌",
            "—" if not v else "; ".join("%g→%g(+%.2f%%p)" % (a, b, b - a) for _, a, b in v)))
    say("")
    say("- 라벨 집계: `TP` %d · `MANUAL` %d · `SL` %d · `MIX` %d"
        % tuple(sum(1 for t in TRADES if t[LABEL] == x)
                for x in ("TP", "MANUAL", "SL", "MIX")))

    tp = [t for t in TRADES if t[LABEL] == "TP"]

    # ---------------- E1 / X1 ---------------------------------------------
    say("")
    say("## E1 · X1 — `TP` 건의 매도 레그 시퀀스가 비증가 (문턱 ≥90%)")
    say("")
    ok = [t for t in tp if not nonincreasing(t[LEGS])]
    r = len(ok) / len(tp)
    say("- `TP` **%d건** 중 비증가 **%d건** = **%.1f%%** ⇒ **%s** (문턱 %.0f%%)"
        % (len(tp), len(ok), 100 * r, "✅ 지지" if r >= E1_MIN else "❌ 불성립", 100 * E1_MIN))
    say("- **X1**(POST4 §5 = *「다음 글 신규 `TP` 건의 비증가 ≥90%%」*) = 같은 계산 ⇒ **%s**"
        % ("✅ 적중" if r >= E1_MIN else "❌ 빗나감"))

    withlegs = [t for t in TRADES if t[LEGS]]
    allok = [t for t in withlegs if not nonincreasing(t[LEGS])]
    say("- 🔎 **라벨 제외 전 %d건 전체**(레그 있는 건): 비증가 **%d/%d** — "
        "`MANUAL`·`SL` 을 빼도 넣어도 위반은 %d건 ⇒ 라벨 결정이 E1 판정을 만들지 않았다."
        % (len(withlegs), len(allok), len(withlegs), len(withlegs) - len(allok)))

    used_eps = [(t[NAME], a, b) for t in withlegs
                for _, a, b in [(0, x, y) for x, y in zip(t[LEGS], t[LEGS][1:])]
                if 0 < b - a <= EPS]
    ties = [(t[NAME], a) for t in withlegs for a, b in zip(t[LEGS], t[LEGS][1:]) if a == b]
    say("- ε 사용 횟수 **%d회** — %s. 동률 %d쌍(%s)은 증가가 아니다."
        % (len(used_eps),
           "ε 를 넉넉히 잡아서 통과한 게 아니다" if not used_eps else "🔴 ε 에 기댄 통과가 있다",
           len(ties), "; ".join("%s %g=%g" % (n, a, a) for n, a in ties) or "없음"))

    # 미완결 처리 민감도 — 사전등록 §4 「제외 전후 건수를 둘 다 기록」
    say("")
    say("### 미완결(`~`) 처리 민감도 — 사전등록 §4 가 요구한 「제외 전후 둘 다 기록」")
    say("")
    say("| 처리 | 대상 `TP` | 비증가 | 비율 | 비고 |")
    say("|---|---|---|---|---|")
    say("| (가) 전 레그 포함 — **4번째 글이 실제로 쓴 처리** | %d | %d | %.1f%% | 판정에 쓰는 값 |"
        % (len(tp), len(ok), 100 * r))
    drop = [(t[NAME], t[LEGS][:-1] if t[TRUNC] else t[LEGS]) for t in tp]
    dok = [n for n, L in drop if not nonincreasing(L)]
    say("| (나) `~` 건의 **마지막 레그만** 제거 | %d | %d | %.1f%% | 사전등록 §2 문언의 다른 읽기 |"
        % (len(drop), len(dok), 100 * len(dok) / len(drop)))
    comp = [t for t in tp if not t[TRUNC]]
    cok = [t for t in comp if not nonincreasing(t[LEGS])]
    say("| (다) `~` 건을 **통째 제외** | %d | %d | %.1f%% | 🔴 n<3 ⇒ 사전등록 §3 이면 판정 보류 |"
        % (len(comp), len(cok), 100 * len(cok) / len(comp)))
    say("")
    say("- ⇒ 세 처리가 **모두 100%** 라 판정이 처리 선택에 **의존하지 않는다**.")

    # ---------------- E4 --------------------------------------------------
    say("")
    say("## E4 (반증축) — `TP` 중 **레그 3개 이상**만으로 재계산")
    say("")
    tp3 = [t for t in tp if len(t[LEGS]) >= 3]
    ok3 = [t for t in tp3 if not nonincreasing(t[LEGS])]
    r3 = len(ok3) / len(tp3) if tp3 else None
    say("| 대상 | 건수 | 비증가 | 비율 |")
    say("|---|---|---|---|")
    say("| `TP` 전체 | %d | %d | %.1f%% |" % (len(tp), len(ok), 100 * r))
    say("| `TP` ∩ 레그≥3 | %d | %d | %.1f%% |" % (len(tp3), len(ok3), 100 * r3))
    say("")
    say("- 제외된 건: " + (", ".join("%s(레그 %d)" % (t[NAME], len(t[LEGS]))
                                    for t in tp if len(t[LEGS]) < 3) or "없음"))
    say("- ⇒ **%s** — 두 비율이 %s."
        % ("✅ 레그 수가 만든 결과가 아니다" if r3 == r else "🔴 레그 수에 의존한다",
           "같다" if r3 == r else "다르다"))

    # ---------------- E2 (원 동결 규칙) -----------------------------------
    say("")
    say("## E2 — **원 동결 규칙**(마지막 레그) · 연속성 확인용 (문턱 ≥80%)")
    say("")
    say("대상 = 저자가 **본전 매도**라 서술한 건(`breakeven_note`). 4번째 글과 **같은 규칙**으로 잰다.")
    say("")
    be = [t for t in TRADES if t[BE]]
    say("| 종목 | 라벨 | 시퀀스 | 동결 규칙(마지막 레그) | `\\|ret\\|` | 판정 |")
    say("|---|---|---|---|---|---|")
    hit = 0
    for t in be:
        x = t[LEGS][-1]
        p = abs(x) < BE_MAX
        hit += p
        say("| %s | `%s` | %s | **%g** | %.2f | %s |"
            % (t[NAME], t[LABEL], seq(t[LEGS]), x, abs(x), "✅" if p else "❌"))
    r2 = hit / len(be)
    say("")
    say("- **%d/%d = %.1f%%** ⇒ **%s** (문턱 %.0f%%)"
        % (hit, len(be), 100 * r2, "✅ 지지" if r2 >= E2_MIN else "❌ 불성립", 100 * E2_MIN))
    say("- 🔑 4번째 글과 **같은 자리에서 같은 방식으로** 깨졌다 — 저자가 「손실률」이라 낱말을 바꿔 적은 "
        "레그(한켐 −2.12 / 4번째 글 PS일렉 −2.76)를 규칙이 본전매도로 강제 지목한다.")

    # ---------------- X2 --------------------------------------------------
    say("")
    say("## X2 — **새 규칙**(「손실률」 레그 제외 후 마지막) · 완결 `TP` 건 한정 (문턱 ≥80%)")
    say("")
    say("POST4 §5 X2 동결 문언 = *「저자가 「손실률」이라 낱말을 바꿔 적은 레그는 본전매도에서 제외하고 "
        "남은 레그 중 마지막」*. `LABELS_2026-08-29_post5.md` 가 **계산 전에** 적용 대상을 "
        "*「`TP` 완결 건」* 으로 못박았다.")
    say("")
    x2t = [t for t in TRADES if t[BE] and t[LABEL] == "TP" and not t[TRUNC]]
    say("| 종목 | 라벨 | 시퀀스 | 「손실률」 제외 후 | X2 레그 | 원 시퀀스 위치 | `\\|ret\\|` | 판정 |")
    say("|---|---|---|---|---|---|---|---|")
    hit2 = 0
    x2pos = []
    for t in x2t:
        kept = [v for v, m in zip(t[LEGS], t[LOSSM]) if not m]
        x, pos = x2_leg(t[LEGS], t[LOSSM])
        p = abs(x) < BE_MAX
        hit2 += p
        x2pos.append((t[NAME], pos, len(t[LEGS]), x, t[LEGS][-1]))
        say("| %s | `%s` | %s | %s | **%g** | 뒤에서 %d번째 | %.2f | %s |"
            % (t[NAME], t[LABEL], seq(t[LEGS]), seq(kept), x,
               len(t[LEGS]) - pos, abs(x), "✅" if p else "❌"))
    r22 = hit2 / len(x2t)
    say("")
    say("- **%d/%d = %.1f%%** ⇒ **%s** (문턱 %.0f%%)"
        % (hit2, len(x2t), 100 * r22, "✅ 지지" if r22 >= E2_MIN else "❌ 불성립", 100 * E2_MIN))
    say("")
    say("### X2 에서 «빠진» 건과 그 이유 (계산 전 동결분)")
    say("")
    say("| 종목 | 라벨 | `~` | 제외 사유 |")
    say("|---|---|---|---|")
    for t in TRADES:
        if t in x2t or not t[LEGS]:
            continue
        if t[BE] and t[LABEL] != "TP":
            why = "라벨이 `%s` — X2 대상은 `TP` 완결 건뿐(라벨은 계산 전 동결)" % t[LABEL]
        elif t[BE] and t[TRUNC]:
            why = "미완결(`~`) — **마지막 레그가 미확정**이라 「남은 레그 중 마지막」이 정의 안 됨"
        elif t[TRUNC]:
            why = "본전매도 서술 없음 + 미완결(`~`) — 마지막 레그 미확정"
        else:
            why = "본전매도 서술 없음(`breakeven_note`=0)"
        say("| %s | `%s` | %s | %s |" % (t[NAME], t[LABEL], "있음" if t[TRUNC] else "—", why))
    say("")
    say("- 🔴 **미완결 건이 빠지는 이유는 규칙의 «분자»가 아니라 «정의»다** — X2 는 「남은 레그 중 "
        "마지막」을 고르는데, `~` 로 끝난 시퀀스는 마지막 레그가 아직 안 적혔다. 값을 보고 뺀 게 아니다.")

    # ---------------- X3 --------------------------------------------------
    say("")
    say("## X3 (반증축 · 필수) — 본전매도 레그가 「마지막에서 두 번째」인 건 수")
    say("")
    say("| 종목 | 레그 수 | X2 가 고른 레그 | 뒤에서 몇 번째 | 「마지막 레그」 규칙이 고를 값 | 두 규칙이 다른가 |")
    say("|---|---|---|---|---|---|")
    second_last = 0
    differ = 0
    for nm, pos, n, x, last in x2pos:
        back = n - pos
        second_last += (back == 2)
        d = (x != last)
        differ += d
        say("| %s | %d | %g | %d | %g | %s |" % (nm, n, x, back, last, "예" if d else "**아니오**"))
    say("")
    say("- 「마지막에서 두 번째」인 건 = **%d건**" % second_last)
    say("- 두 규칙이 실제로 **다른 레그를 고른** 건 = **%d/%d건**" % (differ, len(x2pos)))
    if second_last == 0:
        say("- ⇒ **「두 규칙 구분 불가」** — X2 는 이번 표본에서 *「마지막 레그」* 규칙과 구분되지 않는다.")
    else:
        say("- ⇒ 두 규칙이 구분된다.")
    say("- 🔴 **X3 문언의 결함 자기신고**: 「마지막에서 두 번째」는 「마지막이 «아닌» 자리」의 "
        "**부분집합**이다. 아래 민감도에서 한켐을 넣으면 X2 가 고르는 레그는 **뒤에서 세 번째**라 "
        "X3 문언으로는 «안 잡히는데» 두 규칙의 결과는 갈린다. 문언은 **고치지 않고** 이번 판정은 "
        "동결대로 둔다(결과를 보고 고치면 사후 완화).")

    # ---------------- E3 --------------------------------------------------
    say("")
    say("## E3 — `SL` 건의 손절 레그 비증가")
    say("")
    sl = [t for t in TRADES if t[LABEL] == "SL"]
    say("- `SL` 건 **%d건**(%s)." % (len(sl), ", ".join(t[NAME] for t in sl)))
    for t in sl:
        say("- 🔴 %s: 저자가 **범위만** 적었다 — *「손실률 −16.25%% ~ −37.48%%」*. "
            "레그 «시퀀스»가 아니라 두 끝값이므로 **비증가 개념이 정의되지 않는다**." % t[NAME])
    say("- ⇒ **⛔ 판정 불가** (`SL` 표본은 생겼으나 시퀀스가 없다). "
        "원장에는 2레그 + `RANGE_ONLY` 표시로 보존한다.")

    # ---------------- 민감도 -----------------------------------------------
    say("")
    say("## 민감도 (🔴 판정에 «안» 쓴다) — 한켐 첫 2레그를 `TP` 로 볼 때")
    say("")
    say("`LABELS_2026-08-29_post5.md` §약한 결정: 한켐의 첫 사이클(4.86 → 0.84 본전)은 자동이었고 "
        "수동은 **두 번째 진입**에만 해당한다. 「한 항목 = 한 라벨」 규약(이노테크 전례)을 지켜 "
        "`MANUAL` 로 동결했으나, 대안도 병기해 둔다.")
    say("")
    hk = [t for t in TRADES if t[NAME] == "한켐"][0]
    alt = hk[LEGS][:2]
    say("| 축 | 동결 판정 | 한켐 첫 2레그를 `TP` 로 볼 때 | 뒤집히나 |")
    say("|---|---|---|---|")
    a_ok = len(ok) + (0 if nonincreasing(alt) else 1)
    a_n = len(tp) + 1
    say("| E1 | %d/%d = %.1f%% ✅ | %d/%d = %.1f%% %s | %s |"
        % (len(ok), len(tp), 100 * r, a_ok, a_n, 100 * a_ok / a_n,
           "✅" if a_ok / a_n >= E1_MIN else "❌",
           "**아니오**" if (a_ok / a_n >= E1_MIN) == (r >= E1_MIN) else "🔴 **예**"))
    a3_ok, a3_n = len(ok3), len(tp3)   # 레그 2개라 E4 부분집합에 안 들어간다
    say("| E4 | %d/%d = %.1f%% ✅ | %d/%d = %.1f%% ✅ (레그 2개라 부분집합 밖) | **아니오** |"
        % (len(ok3), len(tp3), 100 * r3, a3_ok, a3_n, 100 * a3_ok / a3_n))
    e2_alt_hit = sum(1 for t in be if abs((alt[-1] if t[NAME] == "한켐" else t[LEGS][-1])) < BE_MAX)
    say("| E2(원 규칙) | %d/%d = %.1f%% ❌ | %d/%d = %.1f%% %s | %s |"
        % (hit, len(be), 100 * r2, e2_alt_hit, len(be), 100 * e2_alt_hit / len(be),
           "✅" if e2_alt_hit / len(be) >= E2_MIN else "❌",
           "🔴 **예 — 라벨 하나로 판정이 갈린다**"
           if (e2_alt_hit / len(be) >= E2_MIN) != (r2 >= E2_MIN) else "**아니오**"))
    hk_x2, hk_pos = x2_leg(hk[LEGS], hk[LOSSM])
    say("| X2 | %d/%d = %.1f%% ✅ | %d/%d = %.1f%% ✅ (한켐 X2 레그 = **%g**) | **아니오** |"
        % (hit2, len(x2t), 100 * r22, hit2 + (abs(hk_x2) < BE_MAX), len(x2t) + 1,
           100 * (hit2 + (abs(hk_x2) < BE_MAX)) / (len(x2t) + 1), hk_x2))
    say("| X3 | 「마지막에서 두 번째」 %d건 ⇒ 구분 불가 | 한켐 X2 레그는 뒤에서 **%d번째** ⇒ 문언상 여전히 %d건 |"
        " 🔴 **문언은 아니오 · 실질은 예**(두 규칙이 %g vs %g 로 갈린다) |"
        % (second_last, len(hk[LEGS]) - hk_pos, second_last, hk_x2, hk[LEGS][-1]))
    say("")
    say("- 🔴 ***E2(원 규칙)의 판정이 라벨 하나에 뒤집힌다.*** 4번째 글 §3 의 자기신고와 **같은 형태**이고, "
        "그래서 X2 가 필요했다. 민감도는 **판정에 쓰지 않는다**.")

    # ---------------- 누적 -------------------------------------------------
    say("")
    say("## 누적 집계 — E1 · E4 (v2 규칙이 «구속하는» 글만)")
    say("")
    say("| 글 | E1 분자/분모 | E1 비율 | E4 분자/분모 | E4 비율 |")
    say("|---|---|---|---|---|")
    say("| 4번째 글(2026-08-22) *동결 인용* | %d/%d | %.1f%% | %d/%d | %.1f%% |"
        % (POST4["E1_ok"], POST4["E1_n"], 100 * POST4["E1_ok"] / POST4["E1_n"],
           POST4["E4_ok"], POST4["E4_n"], 100 * POST4["E4_ok"] / POST4["E4_n"]))
    say("| 5번째 글(2026-08-29) *이번* | %d/%d | %.1f%% | %d/%d | %.1f%% |"
        % (len(ok), len(tp), 100 * r, len(ok3), len(tp3), 100 * r3))
    ce_ok, ce_n = POST4["E1_ok"] + len(ok), POST4["E1_n"] + len(tp)
    c4_ok, c4_n = POST4["E4_ok"] + len(ok3), POST4["E4_n"] + len(tp3)
    say("| **누적** | **%d/%d** | **%.1f%%** | **%d/%d** | **%.1f%%** |"
        % (ce_ok, ce_n, 100 * ce_ok / ce_n, c4_ok, c4_n, 100 * c4_ok / c4_n))
    say("")
    say("- 누적 E1 **%d/%d = %.1f%%** ⇒ **%s** (문턱 %.0f%%) · 누적 E4 **%d/%d = %.1f%%** ⇒ **%s**"
        % (ce_ok, ce_n, 100 * ce_ok / ce_n,
           "✅ 지지" if ce_ok / ce_n >= E1_MIN else "❌ 불성립", 100 * E1_MIN,
           c4_ok, c4_n, 100 * c4_ok / c4_n,
           "✅ 통과" if c4_ok / c4_n == ce_ok / ce_n else "🔴 레그 수 의존"))

    say("")
    say("### 🔴 3번째 글(2026-08-14)이 누적 분모에 «없는» 이유")
    say("")
    say("- `PREREG_EXIT_V2.md` 는 2026-08-15 에 동결됐고 §1 이 *「이 문서가 구속하는 것은 **다음 글의 "
        "신규 건**뿐이다」* · *「v1 의 기각은 기각으로 둔다」* 고 못박았다. 3번째 글까지의 33건은 "
        "**v1 로 판정돼 기각된 표본**이다.")
    say("- 3번째 글에는 **동결된 기전 라벨 파일이 없다**(첫 라벨 파일 = `LABELS_2026-08-22_post4.md`). "
        "지금 라벨을 붙여 다시 재면 그게 바로 §1 이 금지한 **사후 완화**다.")
    say("- ⇒ 누적은 **4번째 + 5번째 글**로만 낸다.")
    say("")
    say("참고(🔴 **판정 아님 · 라벨 없음 · 누적 분모 밖 · 어떤 결론에도 안 쓴다**) — "
        "3번째 글 7건을 라벨 없이 «기계적으로»만 세면:")
    say("")
    p3ok = [n for n, L in POST3_RAW if not nonincreasing(L)]
    say("- 비증가 **%d/%d** (%s)" % (len(p3ok), len(POST3_RAW),
                                     " / ".join("%s [%s]" % (n, seq(L)) for n, L in POST3_RAW)))

    (BASE / "RESULTS_EXIT_V2_POST5_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

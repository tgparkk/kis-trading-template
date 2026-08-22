# -*- coding: utf-8 -*-
"""PREREG_EXIT_V2.md §3 실행 — 4번째 글 신규 건의 E1·E2·E3·E4.

라벨은 `LABELS_2026-08-22_post4.md`(커밋 f925570)에서 **계산 전에** 확정된 것을 그대로 옮긴다.
레그 수익률은 저자 본문(`post_224385784257.txt`)에 적힌 순서 그대로다.

DB 를 읽지 않는다(저자 서술만 쓴다) ⇒ DB 스냅샷에 의존하지 않는 유일한 산출물이다.
라이브 트리 import 0건.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

EPS = 0.05          # 사전등록 §2: 허용 오차 0.05%p (동결분, 고치지 않는다)
E1_MIN = 0.90       # 사전등록 §3 E1: TP 건의 90% 이상
E2_MIN = 0.80       # 사전등록 §3 E2: 4/5 이상 = 80%
BE_MAX = 1.0        # 사전등록 §3 E2: 본전 매도 레그의 |ret| < 1.0%

# (종목, 라벨, 레그 수익률 순서대로, 생략표시「~」, 본전매도 서술 여부)
TRADES = [
    ("이노테크",         "MANUAL", [14.38, 13.93, 13.36, 13.36],                    True,  False),
    ("한켐",             "TP",     [11.97, 11.84, 5.95, 5.58],                      False, False),
    ("금호건설",         "TP",     [23.90, 20.56, 16.75, 13.57, 10.26, 10.16],      True,  False),
    ("지투파워",         "TP",     [6.75, 3.00, 0.37],                              False, True),
    ("PS일렉트로닉스",   "MIX",    [4.06, 0.40, -2.76],                             False, True),
    ("코데즈컴바인",     "TP",     [10.54, 0.41],                                   False, True),
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


def main():
    say("# RESULTS_EXIT_V2_POST4_NUMBERS — 기계 생성 (수정 금지)\n")
    say("사전등록 `PREREG_EXIT_V2.md` §3 · 라벨 `LABELS_2026-08-22_post4.md` · 생성 `run_exit_v2_post4.py`")
    say(f"허용 오차 ε = {EPS}%p · **DB 미사용**(저자 서술만) ⇒ DB 스냅샷 무관\n")

    say("## 원표\n")
    say("| 종목 | 라벨 | 레그 수 | 시퀀스 | 생략`~` | 비증가 | 위반 |")
    say("|---|---|---|---|---|---|---|")
    for nm, lab, legs, trunc, _be in TRADES:
        v = nonincreasing(legs)
        say("| {} | `{}` | {} | {} | {} | {} | {} |".format(
            nm, lab, len(legs), ", ".join(f"{x:g}" for x in legs),
            "**있음**" if trunc else "—",
            "✅" if not v else "❌",
            "—" if not v else "; ".join(f"{a:g}→{b:g}(+{b-a:.2f}%p)" for _, a, b in v)))

    tp = [t for t in TRADES if t[1] == "TP"]
    say()
    say("## E1 — `TP` 건의 매도 레그 시퀀스가 비증가 (문턱 ≥90%)\n")
    ok = [t for t in tp if not nonincreasing(t[2])]
    r = len(ok) / len(tp)
    say(f"- `TP` **{len(tp)}건** 중 비증가 **{len(ok)}건** = **{100*r:.1f}%** "
        f"⇒ **{'✅ 지지' if r >= E1_MIN else '❌ 불성립'}** (문턱 {100*E1_MIN:.0f}%)")
    allok = [t for t in TRADES if not nonincreasing(t[2])]
    say(f"- 🔎 **제외 전 6건 전체**: 비증가 **{len(allok)}/6** "
        f"(`MANUAL`·`MIX` 를 빼도 넣어도 위반은 {6-len(allok)}건)")
    say(f"- ε 는 **한 번도 쓰이지 않았다** — 동률 1쌍(이노테크 13.36→13.36)은 증가가 아니다.")

    say()
    say("## E4 (반증축) — `TP` 중 **레그 3개 이상**만으로 재계산\n")
    tp3 = [t for t in tp if len(t[2]) >= 3]
    ok3 = [t for t in tp3 if not nonincreasing(t[2])]
    r3 = len(ok3) / len(tp3) if tp3 else None
    say("| 대상 | 건수 | 비증가 | 비율 |")
    say("|---|---|---|---|")
    say(f"| `TP` 전체 | {len(tp)} | {len(ok)} | {100*r:.1f}% |")
    say(f"| `TP` ∩ 레그≥3 | {len(tp3)} | {len(ok3)} | {100*r3:.1f}% |")
    say()
    say("- 제외된 건: " + (", ".join(t[0] + f"(레그 {len(t[2])})" for t in tp if len(t[2]) < 3) or "없음"))
    say(f"- ⇒ **{'✅ 레그 수가 만든 결과가 아니다' if r3 == r else '🔴 레그 수에 의존한다'}** — "
        f"두 비율이 {'같다' if r3 == r else '다르다'}.")

    say()
    say("## E2 — 저자가 **본전 매도**라 적은 레그의 `|ret| < 1.0%` (문턱 ≥80%)\n")
    say("🔴 **어느 레그가 본전매도인지 저자가 라벨하지 않았다.** "
        "`LABELS…md` §4-3 이 **계산 전에** *「마지막 레그」*로 동결했다.\n")
    be = [t for t in TRADES if t[4]]
    say("| 종목 | 라벨 | 시퀀스 | 동결 규칙(마지막 레그) | `|ret|` | 판정 |")
    say("|---|---|---|---|---|---|")
    hit = 0
    for nm, lab, legs, _t, _b in be:
        x = legs[-1]
        p = abs(x) < BE_MAX
        hit += p
        say(f"| {nm} | `{lab}` | {', '.join(f'{v:g}' for v in legs)} | **{x:g}** | {abs(x):.2f} | "
            f"{'✅' if p else '❌'} |")
    r2 = hit / len(be)
    say()
    say(f"- **{hit}/{len(be)} = {100*r2:.1f}%** ⇒ **{'✅ 지지' if r2 >= E2_MIN else '❌ 불성립'}** "
        f"(문턱 {100*E2_MIN:.0f}%)")

    # 민감도 — 동결 규칙이 «가정»임을 LABELS §4-3 이 명시했으므로 대안도 인쇄한다.
    say()
    say("### E2 민감도 (판정 아님 · 동결 규칙이 가정이라 함께 인쇄)\n")
    say("대안 규칙 = *「0 에 가장 가까운 «양(+)»의 레그」*를 본전매도로 볼 때:\n")
    say("| 종목 | 대안 레그 | `|ret|` | 판정 |")
    say("|---|---|---|---|")
    hit2 = 0
    for nm, _lab, legs, _t, _b in be:
        pos = [v for v in legs if v >= 0]
        x = min(pos, key=abs) if pos else legs[-1]
        p = abs(x) < BE_MAX
        hit2 += p
        say(f"| {nm} | **{x:g}** | {abs(x):.2f} | {'✅' if p else '❌'} |")
    say()
    say(f"- 대안 규칙이면 **{hit2}/{len(be)} = {100*hit2/len(be):.1f}%** ⇒ "
        f"**{'지지' if hit2/len(be) >= E2_MIN else '불성립'}**")
    say(f"- 🔴 ***두 규칙의 판정이 {'갈린다' if (r2>=E2_MIN) != (hit2/len(be)>=E2_MIN) else '같다'}.***")

    say()
    say("## E3 — `SL` 건의 손절 레그 비증가\n")
    sl = [t for t in TRADES if t[1] == "SL"]
    say(f"- `SL` 건 **{len(sl)}건** ⇒ **❌ 판정 불가**(대상 표본 없음).")
    say("- 참고: 손실 레그는 PS일렉트로닉스 **−2.76 단 1개**뿐이라 시퀀스를 정의할 수 없다.")

    (BASE / "RESULTS_EXIT_V2_POST4_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

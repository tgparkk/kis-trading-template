# -*- coding: utf-8 -*-
"""평단 P 복원 — 4번째 글 신규 6건 (R3·D1·L3·L5 의 관문).

🔴 **직전 복원과 전제가 다르다.** `reconstruct_prices.py` 는 「1차 매수만 체결」 건이 대상이라
   P 가 «격자 위 단일 체결가»였다. 4번째 글은 **6건 전부 2~5차 체결**이라 P 는 «가중평균 실수»다.
   ⇒ 제약 C1(P 가 격자 위)이 **사라진다**. 남는 건 C2(레그 수익률 소수 2자리)·C3(S 가 어느 봉 안).
   ⇒ ***복원이 원리적으로 약해진다. 이 스크립트의 첫째 목적은 「얼마나 약한지」를 재는 것이다.***

방법: S₁(1차 매도가)을 격자 위에서 훑고 P = S₁/(1+r₁) 로 역산한 뒤(M2 갈래),
      나머지 레그가 전부 C2·C3 를 만족하는지 본다. 통과한 P 전체가 feasible set.

라이브 트리 import 0건. DB 는 SELECT 만.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

from reconstruct_prices import gross_ret, grid_prices, net_ret, solve, tick
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

# (종목, 코드, 등록일, 종료일, 레그 수익률, 체결차수, 등록일 유형)
TARGETS = [
    ("이노테크",         "469610", "2026-08-13", "2026-08-21", [14.38, 13.93, 13.36, 13.36],               5, "되밀림"),
    ("한켐",             "457370", "2026-08-12", "2026-08-21", [11.97, 11.84, 5.95, 5.58],                 4, "되밀림"),
    ("금호건설",         "002990", "2026-08-12", "2026-08-21", [23.90, 20.56, 16.75, 13.57, 10.26, 10.16], 3, "상한가마감"),
    ("지투파워",         "388050", "2026-08-13", "2026-08-21", [6.75, 3.00, 0.37],                         2, "상한가마감"),
    ("PS일렉트로닉스",   "332570", "2026-08-13", "2026-08-21", [4.06, 0.40, -2.76],                        4, "상한가마감"),
    ("코데즈컴바인",     "047770", "2026-08-19", "2026-08-21", [10.54, 0.41],                              2, "되밀림"),
]


def say(s=""):
    print(s)
    OUT.append(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def main():
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    say("# RESULTS_RECONSTRUCT_POST4_NUMBERS — 기계 생성 (수정 금지)\n")
    say("생성 `run_reconstruct_post4.py` · 재사용 `reconstruct_prices.py`(tick·grid·solve)")
    say("🔴 **6건 전부 2~5차 체결 ⇒ P 는 가중평균 실수. 제약 C1(P 가 격자 위)이 사라진다.**\n")

    say("| 종목 | 차수 | 등록일 | 레그 | 등록일 봉 [저,고] | feasible P 개수(gross) | P 범위 | `b₁=1−P/H` 범위 | 폭 |")
    say("|---|---|---|---|---|---|---|---|---|")

    results = []
    for nm, code, d0, d1, legs, tr, typ in TARGETS:
        cur.execute(
            "SELECT date, open, high, low, close FROM daily_prices "
            "WHERE stock_code=%s AND date BETWEEN %s AND %s ORDER BY date", (code, d0, d1))
        rows = cur.fetchall()
        if not rows:
            say(f"| {nm} | {tr} | {d0} | — | **데이터 없음** | — | — | — | — |")
            continue
        ranges = [(r[3], r[2]) for r in rows]          # (low, high)
        o0, h0, l0 = rows[0][1], rows[0][2], rows[0][3]
        lo, hi = min(r[3] for r in rows), max(r[2] for r in rows)

        # M2: S₁ 을 격자에서 훑어 P = S₁/(1+r₁) 역산 → 나머지 레그 검사
        feas = []
        for s1 in grid_prices(lo, hi):
            if not any(a <= s1 <= b for a, b in ranges):
                continue
            P = s1 / (1 + legs[0] / 100.0)
            if not (lo * 0.7 <= P <= hi):
                continue
            if solve(P, legs, ranges, gross_ret) is not None:
                feas.append(P)

        if not feas:
            say(f"| {nm} | {tr}차 | {d0} | {len(legs)} | [{l0:,.0f}, {h0:,.0f}] | **0** | — | — | — |")
            results.append((nm, code, typ, tr, o0, h0, l0, []))
            continue
        pmin, pmax = min(feas), max(feas)
        b1lo, b1hi = 1 - pmax / h0, 1 - pmin / h0
        say(f"| {nm} | {tr}차 | {d0} | {len(legs)} | [{l0:,.0f}, {h0:,.0f}] | **{len(feas)}** | "
            f"{pmin:,.0f}~{pmax:,.0f} | {100*b1lo:+.2f}%~{100*b1hi:+.2f}% | "
            f"**{100*(b1hi-b1lo):.2f}%p** |")
        results.append((nm, code, typ, tr, o0, h0, l0, feas))

    say()
    say("## 🔴 복원 강도 — 직전(1차 체결 건)과 비교\n")
    widths = [(1 - min(f) / h) - (1 - max(f) / h) for *_, h, _l, f in
              [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in results] if f]
    if widths:
        say(f"- `b₁` 구간 폭: 최소 **{100*min(widths):.2f}%p** · 중앙 "
            f"**{100*sorted(widths)[len(widths)//2]:.2f}%p** · 최대 **{100*max(widths):.2f}%p**")
    say("- 직전 표본(`RESULTS_RECONSTRUCT.md`)의 솔트룩스는 `b₁ ∈ [−0.9%, +2.47%]` = 폭 **3.37%p** 였다"
        " — 그건 **1차 체결 건**이라 C1 이 살아 있었다.")

    say()
    say("## L5 (반증축) — 되밀림 건에서 P 가 등록일 봉의 어디인가\n")
    say("`PREREG_BUYLADDER.md` L5: *「[시가, 고가] 상단 1/3 이면 즉시진입 · 하단 1/3 이면 밴드"
        " · 어느 쪽도 과반이 아니면 판별 불가」*\n")
    say("🔴 **전제 검사를 «먼저» 한다** — L5 는 `P` 가 「등록일에 산 가격」이라야 뜻이 있다."
        " 다차수 체결이면 `P` 는 이후 며칠의 평단이라 등록일 봉 밖으로 나갈 수 있다.\n")
    say("| 종목 | 등록일 봉 [저,시,고] | P 범위 | **전제(P ⊂ 등록일 [저,고])** | 상단1/3 | 하단1/3 | 판정 |")
    say("|---|---|---|---|---|---|---|")
    verdicts = []
    for nm, _code, typ, _tr, o0, h0, l0, feas in results:
        if typ != "되밀림":
            continue
        if not feas:
            say(f"| {nm} | [{l0:,.0f}, {o0:,.0f}, {h0:,.0f}] | **해 없음** | — | — | — | ⛔ 판정 불가 |")
            verdicts.append("불가")
            continue
        pmin, pmax = min(feas), max(feas)
        span = h0 - o0
        up, dn = o0 + span * 2 / 3, o0 + span / 3
        premise = (l0 <= pmin) and (pmax <= h0)
        if not premise:
            v = "⛔ **판정 불가 (전제 미성립)**"
            verdicts.append("불가")
        elif pmin >= up:
            v = "즉시진입"; verdicts.append(v)
        elif pmax <= dn:
            v = "밴드"; verdicts.append(v)
        else:
            v = "🟡 구간이 걸쳐 있음"; verdicts.append("불가")
        say(f"| {nm} | [{l0:,.0f}, {o0:,.0f}, {h0:,.0f}] | {pmin:,.0f}~{pmax:,.0f} | "
            f"{'✅ 성립' if premise else '🔴 **P 가 등록일 봉 밖**'} | {up:,.0f} | {dn:,.0f} | {v} |")
    say()
    bad = verdicts.count("불가")
    say(f"- 되밀림 **{len(verdicts)}건** 중 전제 미성립·판별 불가 **{bad}건**")
    if bad * 2 >= len(verdicts):
        say("- ⇒ 🔴 **L5 판정 불가.** `P` 가 「등록일 체결가」가 아니라 «다차수 평단»이라 "
            "L5 가 묻는 대상 자체가 없다. (`PREREG_BUYLADDER.md` L1·L2 가 "
            "*「신규 first_only 건」*을 요구했고 그게 0건인 것과 **같은 이유**다.)")
    else:
        say(f"- ⇒ 최빈 판정 **{max(set(verdicts), key=verdicts.count)}**")

    # D1 (PREREG_HDR §4): h_max = (S_max − L)/(H − L),  S_max = P·(1+r_max)
    say()
    say("## D1 (`PREREG_HDR.md` §4) — 최고 매도가의 `h_max` 중앙값이 0.50~0.70 인가\n")
    say("`H` = 등록일 고가 · `L` = 등록일~종료 최저 저가 · `S_max` = `P·(1+r₁)`\n")
    say("| 종목 | H | L | P 범위 | S_max 범위 | **h_max 범위** | 폭 | 0.50~0.70 |")
    say("|---|---|---|---|---|---|---|---|")
    hmids, hwidths = [], []
    for (nm, code, _typ, _tr, _o0, h0, _l0, feas), (_n, _c, _d0, d1, legs, _t, _y) in zip(results, TARGETS):
        cur.execute("SELECT min(low) FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s",
                    (code, TARGETS[[t[0] for t in TARGETS].index(nm)][2], d1))
        L = cur.fetchone()[0]
        if not feas or L is None or h0 == L:
            say(f"| {nm} | {h0:,.0f} | {'—' if L is None else f'{L:,.0f}'} | **해 없음** | — | — | — | ⛔ |")
            continue
        r1 = legs[0] / 100.0
        smin, smax = min(feas) * (1 + r1), max(feas) * (1 + r1)
        hlo, hhi = (smin - L) / (h0 - L), (smax - L) / (h0 - L)
        inside = (0.50 <= (hlo + hhi) / 2 <= 0.70)
        hmids.append((hlo + hhi) / 2); hwidths.append(hhi - hlo)
        say(f"| {nm} | {h0:,.0f} | {L:,.0f} | {min(feas):,.0f}~{max(feas):,.0f} | "
            f"{smin:,.0f}~{smax:,.0f} | **{hlo:.3f}~{hhi:.3f}** | {hhi-hlo:.3f} | "
            f"{'✅' if inside else '❌'} (중점 {(hlo+hhi)/2:.3f}) |")
    if hmids:
        m = sorted(hmids)[len(hmids) // 2] if len(hmids) % 2 else \
            (sorted(hmids)[len(hmids)//2-1] + sorted(hmids)[len(hmids)//2]) / 2
        say()
        say(f"- **중점의 중앙값 {m:.3f}** ⇒ D1 문턱 0.50~0.70 **{'✅ 안' if 0.50 <= m <= 0.70 else '❌ 밖'}**")
        say(f"- 🔴 **구간 폭: 최소 {min(hwidths):.3f} · 중앙 "
            f"{sorted(hwidths)[len(hwidths)//2]:.3f} · 최대 {max(hwidths):.3f}** — "
            "폭이 0.20 을 넘으면 「0.50~0.70 에 든다」는 사실상 아무 값이나 든다는 뜻이다.")
        wide = sum(1 for w in hwidths if w > 0.20)
        say(f"- ⇒ 폭 > 0.20 인 건이 **{wide}/{len(hwidths)}** ⇒ "
            f"**{'🔴 D1 판정 불가 (복원이 너무 약하다)' if wide * 2 >= len(hwidths) else '🟡 약한 지지'}**")

    (BASE / "RESULTS_RECONSTRUCT_POST4_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close(); conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

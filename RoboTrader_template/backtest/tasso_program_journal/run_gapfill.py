# -*- coding: utf-8 -*-
"""§2 매도 갭 체결 가설 — 사전등록 `PREREG_CONDITIONAL.md`(`eb62f2a`) 실행.

기전 가설: 저자는 **지정가 매도 사다리를 미리 걸어둔다.** 그러면 **갭 상승한 시가에 여러
차수가 한꺼번에 체결**된다. 셋을 동시에 예측한다 — 첫 매도가 장 초반 · 매도가가 시가 근처 ·
레그들이 짧은 시간 안에.

🔴 그리디가 «가장 이른» 배정을 고르면 편향된다 ⇒ **최소(가장 이른)·최대(가장 늦은) 배정을
   둘 다 낸다.** 대칭으로 재는 것이 이 문서의 반증축이다.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import psycopg2

from reconstruct_prices import TARGETS, tick
from run_tests import CODES, DSN
from solve_common_band import feasible_P

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
N_NULL = 20000
NULL_SEED = 20260815
MAX_SOLUTIONS = 400
OPEN_THR = 0.30           # 사전등록 G2 — 시가 근처 판정 문턱
EARLY_END = "093000"      # G1 — 장 시작 30분


def say(s=""):
    print(s)
    OUT.append(s)


def legs_prices(P, legs):
    out = []
    for r in legs:
        S = P * (1 + r / 100.0)
        t = tick(S)
        out.append(round(S / t) * t)
    return out


def assign_first(dsets):
    """비감소 배정 중 «가장 이른» 것 (앞에서 그리디)."""
    picked, cur = [], None
    for s in dsets:
        cand = [d for d in s if cur is None or d >= cur]
        if not cand:
            return None
        cur = min(cand)
        picked.append(cur)
    return picked


def assign_last(dsets):
    """비감소 배정 중 «가장 늦은» 것 (뒤에서 그리디)."""
    picked, cur = [], None
    for s in reversed(dsets):
        cand = [d for d in s if cur is None or d <= cur]
        if not cand:
            return None
        cur = max(cand)
        picked.append(cur)
    return list(reversed(picked))


def main() -> int:
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    say("# §2 매도 갭 체결 가설 — 첫 매도 시각과 시가 대비 위치\n")
    say("지정가 사다리를 걸어두면 **갭 상승 시가에 여러 차수가 한꺼번에 체결**된다.")
    say("🔴 그리디 편향을 막기 위해 **최소(가장 이른)·최대(가장 늦은) 배정을 둘 다** 낸다.\n")
    say("> 🔴 **가설의 출처가 허상이었다 (자기 정정).** 이 가설은 `RESULTS_MINUTE_SELLTIMING.md`")
    say("> 의 S4 기술통계에서 *「7건 중 5건의 첫 매도가 09:00~09:21」* 를 보고 세웠다. 그런데 그")
    say("> 값은 **feasible set 에서 «맨 처음 찾은 해» 하나**의 것이었다(그 루프는 시간순·역순이")
    say("> 둘 다 확인되면 `break` 한다). **해 전체의 중앙값**으로 다시 재면 3/7 이다.")
    say("> 🔑 ***구간해에서 「대표값」을 안 정하면, 루프가 우연히 먼저 만난 해가 패턴처럼 보인다.***\n")

    rows, early_min, early_max, openpos = [], 0, 0, []
    n_ok = 0
    day_cache = []

    for name, d0, d1, legs, fill in TARGETS:
        code = CODES[name]
        cur.execute(
            "SELECT date, time, low, high, open FROM minute_candles "
            "WHERE stock_code=%s AND date BETWEEN %s AND %s AND volume > 0 ORDER BY date, time",
            (code, d0.replace("-", ""), d1.replace("-", "")))
        mb = cur.fetchall()
        if not mb:
            rows.append((name, "🔴 분봉 없음", "—", "—", "—", "—"))
            continue
        bars = [(r[2], r[3]) for r in mb]
        stamps = [(r[0], r[1]) for r in mb]

        cur.execute("SELECT low, high FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s ORDER BY date", (code, d0, d1))
        dr = cur.fetchall()
        ranges = [(r[0], r[1]) for r in dr]
        Ps = feasible_P(legs, ranges, min(r[0] for r in dr), max(r[1] for r in dr))
        if not Ps:
            rows.append((name, "🔴 복원 해 없음", "—", "—", "—", "—"))
            continue
        if len(Ps) > MAX_SOLUTIONS:
            st = len(Ps) / MAX_SOLUTIONS
            Ps = [Ps[int(i * st)] for i in range(MAX_SOLUTIONS)]

        firsts_min, firsts_max, opens, span_min, span_max = [], [], [], [], []
        for P in Ps:
            S = legs_prices(P, legs)
            ds = [[i for i, (lo, hi) in enumerate(bars) if lo <= s <= hi] for s in S]
            if any(not x for x in ds):
                continue
            a, b = assign_first(ds), assign_last(ds)
            if not a or not b:
                continue
            firsts_min.append(stamps[a[0]])
            firsts_max.append(stamps[b[0]])
            span_min.append(a[-1] - a[0])
            span_max.append(b[-1] - b[0])
            # open_pos — 첫 매도가 일어난 «그날»의 시가·고가 대비 S₁ 위치
            dsell = stamps[a[0]][0]
            same = [(lo, hi) for (dd, _), (lo, hi) in zip(stamps, bars) if dd == dsell]
            o = next(r[4] for r in mb if r[0] == dsell)          # 그날 첫 봉의 open
            dh = max(h for _, h in same)
            opens.append((S[0] - o) / (dh - o) if dh > o else np.nan)
        if not firsts_min:
            rows.append((name, "🔴 배정 불가", "—", "—", "—", "—"))
            continue

        n_ok += 1
        fmin = sorted(firsts_min)[len(firsts_min) // 2]
        fmax = sorted(firsts_max)[len(firsts_max) // 2]
        op = float(np.nanmedian(opens))
        e_min = fmin[1] <= EARLY_END
        e_max = fmax[1] <= EARLY_END
        early_min += e_min
        early_max += e_max
        openpos.append(op)
        day_cache.append((name, bars, stamps, mb))
        rows.append((name,
                     f"{fmin[0][4:6]}/{fmin[0][6:]} {fmin[1][:2]}:{fmin[1][2:4]}"
                     + (" ✅" if e_min else ""),
                     f"{fmax[0][4:6]}/{fmax[0][6:]} {fmax[1][:2]}:{fmax[1][2:4]}"
                     + (" ✅" if e_max else ""),
                     f"{op:.2f}",
                     f"{int(np.median(span_min))}봉",
                     f"{int(np.median(span_max))}봉"))

    say("| 종목 | 첫 매도 (최소배정) | 첫 매도 (최대배정) | open_pos | span 최소 | span 최대 |")
    say("|---|---|---|---|---|---|")
    for r in rows:
        say(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |")
    say()

    say(f"## G1 — 첫 매도가 09:00~09:30: 최소배정 **{early_min}/{n_ok}** · "
        f"최대배정 **{early_max}/{n_ok}** (기준: 둘 다 과반)")
    g1 = n_ok and early_min * 2 > n_ok and early_max * 2 > n_ok
    say(f"{'✅ 지지' if g1 else '❌ 기각'}"
        + ("" if g1 else " — 🔑 ***최대배정에서 깨지면 그리디 편향이 만든 것이다.***") + "\n")

    n_near = sum(1 for x in openpos if np.isfinite(x) and x < OPEN_THR)
    say(f"## G2 — `open_pos < {OPEN_THR}` (매도가가 시가 근처 = 갭 체결): "
        f"**{n_near}/{len(openpos)}** (기준 과반)")
    say(f"{'✅ 지지' if n_near * 2 > len(openpos) else '❌ 기각'}\n")

    # ── G3 반증축 ────────────────────────────────────────────────────────────
    say("## G3 (반증축) — 무작위 매도가로도 같은 비율이 나오는가\n")
    rng = random.Random(NULL_SEED)
    grids = []
    for name, bars, stamps, mb in day_cache:
        lo, hi = min(b[0] for b in bars), max(b[1] for b in bars)
        t = tick(lo)
        g = [lo + k * t for k in range(int((hi - lo) / t) + 1)]
        g = [x for x in g if any(a <= x <= b for a, b in bars)]
        grids.append((name, bars, stamps, mb, g))
    drawn = {nm: set() for nm, *_ in grids}
    null_counts = []
    for _ in range(N_NULL):
        c = 0
        for nm, bars, stamps, mb, g in grids:
            S2 = g[rng.randrange(len(g))]
            drawn[nm].add(S2)
            i = next(i for i, (lo, hi) in enumerate(bars) if lo <= S2 <= hi)
            dsell = stamps[i][0]
            same = [(lo, hi) for (dd, _), (lo, hi) in zip(stamps, bars) if dd == dsell]
            o = next(r[4] for r in mb if r[0] == dsell)
            dh = max(h for _, h in same)
            if dh > o and (S2 - o) / (dh - o) < OPEN_THR:
                c += 1
        null_counts.append(c)
    ge = sum(1 for x in null_counts if x >= n_near)
    pct = ge / len(null_counts) * 100
    say("| 종목 | 표집/격자 |")
    say("|---|---|")
    for nm, _, _, _, g in grids:
        say(f"| {nm} | {len(drawn[nm])}/{len(g)} |")
    say()
    say(f"- 귀무 평균 **{np.mean(null_counts):.2f}** · 관측({n_near}) 이상 "
        f"**{ge:,}/{len(null_counts):,}** ⇒ 백분위 **{pct:.1f}%**\n")
    if pct >= 5.0:
        say(f"🔴 **판별력 없음** — 백분위 {pct:.1f}% ≥ 5% ⇒ **G2 지지를 취소한다.**")
    else:
        say(f"🟡 **귀무보다 낫다** ({pct:.1f}% < 5%). 단 n={len(openpos)} 이라 승격하지 않는다.")
    say()
    say("🔴 **in-sample 탐색이다.** 확정 검정은 `PREREG_CONDITIONAL.md` §3 의 Q2·Q3.")

    cur.close()
    conn.close()
    (BASE / "RESULTS_GAPFILL.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_GAPFILL.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

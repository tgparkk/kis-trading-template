# -*- coding: utf-8 -*-
"""PREREG_HDR.md 실행 — 매도가를 「저점 대비 반등폭」 축으로 옮겨 사다리를 찾는다.

h = (S − L) / (H − L)   ·   H = 등록일 고가(v2 앵커) · L = 등록일~종료 최저 저가
S = P(1+r) · P 는 잔차 ≤ 0.025%p 인 feasible set (gross)

🔴 in-sample 은 탐색적이다. 진짜 검정은 PREREG_HDR.md §4 의 다음 글 예측 D1·D2.
라이브 트리 import 0건.
"""
from __future__ import annotations

import itertools
import random
import sys
from pathlib import Path

import numpy as np
import psycopg2

from reconstruct_prices import TARGETS, gross_ret, tick
from run_tests import CODES, DSN

N_NULL = 20000
# 🔴 시드 고정 = 산출물 재현 가능. 바꾸면 백분위가 바뀌므로 바꾸지 말 것.
NULL_SEED = 20260815

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
TOL = 0.025
COMPETITORS = [0.30, 0.50, 0.60, 0.80]     # H3 반증축 — 60 만 특별한가
BAND = 0.10                                # H1 허용폭 ±0.10


def say(s=""):
    print(s)
    OUT.append(s)


def feasible(legs, ranges, lo, hi):
    out = []
    step = max(1, tick(lo) // 4)
    P = lo
    while P <= hi:
        if any(a <= P <= b for a, b in ranges):
            worst, ok, Ss = 0.0, True, []
            for r in legs:
                S_ideal = P * (1 + r / 100.0)
                t = tick(S_ideal)
                S = round(S_ideal / t) * t
                if not any(a <= S <= b for a, b in ranges):
                    ok = False
                    break
                worst = max(worst, abs(gross_ret(P, S) * 100 - r))
                Ss.append(S)
            if ok and worst <= TOL:
                out.append((P, Ss))
        P += step
    return out


def main():
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    say("# 매도 사다리(HDR) — 저점 대비 반등폭 축\n")
    say("`h = (S − L)/(H − L)` · H = 등록일 고가 · L = 등록일~종료 최저 저가\n")

    rows_out = []
    for name, d0, d1, legs, fill in TARGETS:
        if name == "모나미":
            continue                       # 분할손절 건은 사전등록에서 제외
        code = CODES[name]
        cur.execute("SELECT date, high, low FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s ORDER BY date", (code, d0, d1))
        post = cur.fetchall()
        if not post:
            continue
        ranges = [(r[2], r[1]) for r in post]
        L = min(r[2] for r in post)
        H = post[0][1]                     # 등록일 고가
        lo, hi = L, max(r[1] for r in post)
        sols = feasible(legs, ranges, lo, hi)
        if not sols or H <= L:
            say(f"- **{name}**: 해 없음 / 앵커≤저점")
            continue
        hmax = sorted({(max(Ss) - L) / (H - L) for _, Ss in sols})
        rows_out.append((name, H, L, hmax, sols))
        say(f"- **{name}** · H={H:,.0f} · L={L:,.0f} · 해 {len(sols)}개 · "
            f"`h_max` 범위 **{min(hmax):.3f} ~ {max(hmax):.3f}**")

    # ── H1 / H3 ──────────────────────────────────────────────────────────────
    say(f"\n## H1·H3 — 어떤 목표값이 몇 건을 설명하나 (±{BAND})\n")
    say("| 목표 h | 설명한 건수 | 건별 |")
    say("|---|---|---|")
    best = {}
    for tgt in COMPETITORS:
        hits = [n for n, H, L, hm, _ in rows_out
                if any(abs(h - tgt) <= BAND for h in hm)]
        best[tgt] = len(hits)
        say(f"| **{tgt:.2f}** | **{len(hits)}/{len(rows_out)}** | {', '.join(hits) or '—'} |")
    n = len(rows_out)
    ok1 = best[0.60] >= 5
    say(f"\n**H1 (h_max ≈ 0.60 이 5건 이상)**: {best[0.60]}/{n} → "
        f"{'✅ 지지' if ok1 else '❌ 기각'}")
    rivals = [t for t in COMPETITORS if t != 0.60 and best[t] >= best[0.60]]
    if rivals:
        say(f"🔴 **H3 발동 — 경쟁 목표값 {rivals} 이 60% 만큼(또는 더) 설명한다.** "
            "⇒ **「60」이라는 숫자에 판별력이 없다. H1 지지를 취소한다.**")
    else:
        say(f"🟡 **H3 통과** — 0.60 이 경쟁값보다 많이 설명한다 "
            f"({ {f'{t:.2f}': best[t] for t in COMPETITORS} }).")

    # ── H2: 공통 h_max + 스케일 보존 귀무 ────────────────────────────────────
    say("\n## H2 — 공통 h_max 공동해법 + 귀무\n")
    NB, PAD = 201, int(0.01 / 0.005)       # h 0~1.0, 0.005 간격, ±0.01
    def mask_of(hs):
        m = 0
        for h in hs:
            c = int(round(h / 0.005))
            for k in range(c - PAD, c + PAD + 1):
                if 0 <= k < NB:
                    m |= 1 << k
        return m

    def cov(ms):
        for k in range(len(ms), 0, -1):
            for sub in itertools.combinations(range(len(ms)), k):
                acc = ms[sub[0]]
                for j in sub[1:]:
                    acc &= ms[j]
                    if not acc:
                        break
                if acc:
                    return k, ((acc & -acc).bit_length() - 1) * 0.005
        return 0, None

    obs_masks = [mask_of(hm) for _, _, _, hm, _ in rows_out]
    hit, h_star = cov(obs_masks)
    say(f"관측: 하나의 `h` 가 최대 **{hit}/{n}건**을 동시에 설명 (h ≈ **{h_star:.3f}**)")

    # 귀무: 같은 종목의 다른 고가를 앵커로 (스케일 보존)
    null = []
    alts = []
    for name, H, L, hm, sols in rows_out:
        code = CODES[name]
        d0 = next(t[1] for t in TARGETS if t[0] == name)
        cur.execute("SELECT high FROM daily_prices WHERE stock_code=%s AND date<=%s "
                    "ORDER BY date DESC LIMIT 20", (code, d0))
        cand = sorted({r[0] for r in cur.fetchall() if r[0] > L})
        alts.append([(mask_of([(max(Ss) - L) / (h - L) for _, Ss in sols])) for h in cand])
    # 🔴 `itertools.product` 을 20000 에서 자르면 앞자리 종목의 앵커가 인덱스 0 에 못 박힌다
    #    (solve_common_band.py 의 같은 결함 — 귀무 결함 4번째). 시드 고정 무작위 표본으로 바꾼다.
    rng = random.Random(NULL_SEED)
    drawn = [set() for _ in alts]
    while len(null) < N_NULL:
        combo = [rng.randrange(len(a)) for a in alts]
        for i, c in enumerate(combo):
            drawn[i].add(c)
        null.append(cov([alts[i][combo[i]] for i in range(len(alts))])[0])
    ge = sum(1 for x in null if x >= hit)

    # 자리별 실제 표집 종수를 산출물이 스스로 인쇄한다 (절단형 귀무 재발 감지)
    say("\n자리별 실제 표집 앵커 종수:\n")
    say("| 종목 | 표집/전체 앵커 |")
    say("|---|---|")
    for i, (name, _, _, _, _) in enumerate(rows_out):
        say(f"| {name} | {len(drawn[i])}/{len(alts[i])} |")
    say()

    say(f"귀무(스케일 보존 · 대체 앵커 {len(null)}조합): 평균 {np.mean(null):.2f} · "
        f"관측 이상 {ge}/{len(null)} ⇒ 백분위 **{ge/len(null)*100:.1f}%**")
    say(f"\n**H2**: {'🟡 귀무보다 낫다' if ge/len(null) < 0.05 else '🔴 판별력 없음'}")

    say("\n🔴 **어느 쪽이든 증거가 아니다** — 표본 전체가 `HDR 60%` 한 값이라 "
        "**변량이 없다.** 결정적 검정은 다음 글에서 **다른 프리셋 숫자**가 나올 때다(§4 D2).")

    cur.close()
    conn.close()
    (BASE / "RESULTS_HDR.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_HDR.md")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()

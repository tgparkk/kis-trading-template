# -*- coding: utf-8 -*-
"""매매기록 가격 수준 복원 — 「1차 매수만 체결」 건의 매수가·매도가를 역산한다.

원리: 1차 매수만 체결된 건은 매수가 P 가 하나뿐이므로
    r_i = S_i / P − 1   ⇒   S_i = P·(1 + r_i)
즉 모든 매도가가 미지수 P 하나로 묶인다. 제약 셋으로 P 를 좁힌다.
    C1  P 와 S_i 가 **호가단위 격자** 위에 있어야 한다 (격자는 DB 에서 실측 검증함)
    C2  저자가 수익률을 소수 2자리로 적었으므로 round(S_i/P−1, 4) 가 그 값과 정확히 같아야 한다
    C3  P 와 S_i 가 각각 어느 거래일의 [저가, 고가] 안에 들어야 한다

⚠️ 이건 「복원」이지 검정이 아니다. 해가 유일해도 그건 산술의 결과이지
   가설이 참이라는 뜻이 아니다. 검정은 PREREG_Q1_V2.md §3 의 다음 글 예측이다.

라이브 트리 import 0건.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

from run_tests import CODES, DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

# 수수료 모델 (memory: 거래세 0.18% + 수수료 0.015% 양방향)
FEE = 0.00015
TAX = 0.0018

# 복원 대상 — 8/14 글에서 「1차 매수」가 명시된 건 + 같은 글의 나머지(탐색)
TARGETS = [
    # (종목, 등록일, 종료일, [레그 수익률...], fill_level)
    ("에스피지",       "2026-07-31", "2026-08-14", [21.44, 18.51, 12.03],               "first_only"),
    ("솔트룩스",       "2026-08-04", "2026-08-14", [16.20, 16.10, 10.63, 0.68],         "first_only"),
    ("마키나락스",     "2026-08-05", "2026-08-14", [16.58, 11.99, 10.55],               "first_only"),
    ("매드업",         "2026-08-06", "2026-08-14", [8.77, 0.40],                        "first_only"),
    ("빛과전자",       "2026-08-05", "2026-08-14", [8.66, 0.34],                        "first_only"),
    ("케이엔알시스템", "2026-08-01", "2026-08-14", [26.71, 24.03, 24.00, 21.74],        "unknown"),
    ("씨피시스템",     "2026-08-01", "2026-08-14", [9.29, 3.26, 3.24, 0.43, 0.42],      "unknown"),
]


def say(s=""):
    print(s)
    OUT.append(s)


def tick(p: float) -> int:
    """KRX 호가단위. 이 표는 daily_prices 2026-07~08 종가로 실측 검증했다
    (20k~50k 구간 50원 배수 8,910/8,910 = 100% 등)."""
    if p < 2000:
        return 1
    if p < 5000:
        return 5
    if p < 20000:
        return 10
    if p < 50000:
        return 50
    if p < 200000:
        return 100
    if p < 500000:
        return 500
    return 1000


def grid_prices(lo: float, hi: float):
    """[lo, hi] 안의 호가 격자 값 전부."""
    out = []
    p = int(lo)
    while p <= hi:
        t = tick(p)
        p = (p // t) * t
        if p >= lo:
            out.append(p)
        p += t
    return out


def gross_ret(P, S):
    return S / P - 1.0


def net_ret(P, S):
    """매수 수수료 · 매도 수수료+거래세 반영."""
    return (S * (1 - FEE - TAX)) / (P * (1 + FEE)) - 1.0


def solve(P, legs, day_ranges, retfn):
    """P 가 주어졌을 때 각 레그를 만족하는 격자 매도가가 있는가.
    있으면 [(S, r_calc)...] 반환, 없으면 None."""
    sols = []
    for r in legs:
        target = r / 100.0
        # S 대략 위치에서 격자 몇 칸만 훑는다
        approx = P * (1 + target) * (1.003 if retfn is net_ret else 1.0)
        t = tick(approx)
        found = None
        for k in range(-6, 7):
            S = int(round(approx / t) * t) + k * t
            if S <= 0:
                continue
            if round(retfn(P, S) * 100, 2) == r:
                # C3: 어느 날의 [저가, 고가] 안에 드는가
                if any(lo <= S <= hi for lo, hi in day_ranges):
                    found = (S, retfn(P, S) * 100)
                    break
        if found is None:
            return None
        sols.append(found)
    return sols


def main():
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    say("# 매매기록 가격 복원 — 1차 매수가·매도가 역산\n")
    say("호가단위 격자는 `daily_prices` 2026-07~08 종가로 **실측 검증**했다(가정 아님).\n")

    for name, d0, d1, legs, fill in TARGETS:
        code = CODES[name]
        cur.execute(
            "SELECT date, high, low, close FROM daily_prices "
            "WHERE stock_code=%s AND date BETWEEN %s AND %s ORDER BY date", (code, d0, d1))
        rows = cur.fetchall()
        if not rows:
            say(f"## {name} — 데이터 없음\n")
            continue
        ranges = [(r[2], r[1]) for r in rows]
        lo = min(r[2] for r in rows)
        hi = max(r[1] for r in rows)

        say(f"## {name} ({code}) · {fill} · 등록 {d0} · 레그 {legs}\n")
        say(f"창 {d0}~{d1} · {len(rows)}봉 · 가격범위 {lo:,.0f}~{hi:,.0f} · 호가단위 {tick(lo)}원\n")

        # 후보 P 두 갈래:
        #   M1  P 가 격자 위 (단일 체결)
        #   M2  P 는 실수 (부분체결 평단) — 매도가만 격자. S₁ 을 격자에서 훑고 P = S₁/(1+r₁) 로 역산.
        grid = [p for p in grid_prices(lo, hi) if any(a <= p <= b for a, b in ranges)]
        cands = {("M1", float(p)) for p in grid}
        for S1 in grid:
            P = S1 / (1 + legs[0] / 100.0)
            if lo * 0.9 <= P <= hi and any(a <= P <= b for a, b in ranges):
                cands.add(("M2", round(P, 4)))

        for label, fn in (("gross (수수료 미반영)", gross_ret), ("net (수수료·세금 반영)", net_ret)):
            hits = []
            for model, P in sorted(cands, key=lambda x: x[1]):
                s = solve(P, legs, ranges, fn)
                if s:
                    hits.append((P, s, model))
            if not hits:
                # 진단: 「반올림 관례 차이」인가 「모델이 틀렸나」를 가른다.
                # 격자 제약을 빼고, 각 레그 오차의 최댓값을 최소화하는 P 를 찾는다.
                best = None
                for model, P in sorted(cands, key=lambda x: x[1]):
                    errs = []
                    for r in legs:
                        S_ideal = P * (1 + r / 100.0)
                        t = tick(S_ideal)
                        S = round(S_ideal / t) * t
                        if not any(a <= S <= b for a, b in ranges):
                            errs = None
                            break
                        errs.append(abs(fn(P, S) * 100 - r))
                    if errs and (best is None or max(errs) < best[0]):
                        best = (max(errs), P, model)
                if best:
                    say(f"- **{label}**: 해 **0개**. 최소잔차 적합 = 평단 {best[1]:,.1f} ({best[2]}) · "
                        f"**최대 오차 {best[0]:.3f}%p**"
                        + ("  ⇒ 반올림 관례 차이로 설명 가능한 크기" if best[0] < 0.02
                           else "  ⇒ 🔴 **반올림으로 설명 안 되는 크기 — 모델이 틀렸다**"))
                else:
                    say(f"- **{label}**: 해 **0개** · 최소잔차 적합도 실패(격자 매도가가 어느 날 범위에도 없음)")
                continue
            # 매도가 집합이 같으면 같은 해로 본다(P 가 실수라 미세하게 갈릴 뿐)
            uniq: dict[tuple, tuple] = {}
            for P, s, model in hits:
                uniq.setdefault(tuple(S for S, _ in s), (P, s, model))
            if len(uniq) == 1:
                P, s, model = next(iter(uniq.values()))
                say(f"- **{label}**: 🎯 **매도가 집합 유일 — 매수 평단 ≈ {P:,.1f}원** ({model})")
                say(f"  - 매도가: {', '.join(f'{S:,.0f}({rc:.2f}%)' for S, rc in s)}")
            else:
                say(f"- **{label}**: 매도가 집합 **{len(uniq)}가지** (해 {len(hits)}개)")
                for k, (P, s, model) in list(uniq.items())[:4]:
                    say(f"  - 평단 ≈ {P:,.1f} ({model}) → {', '.join(f'{S:,.0f}' for S in k)}")
                if len(uniq) > 4:
                    say(f"  - … 외 {len(uniq)-4}가지")
        say()

    cur.close()
    conn.close()
    (BASE / "RESULTS_RECONSTRUCT.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_RECONSTRUCT.md")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()

# -*- coding: utf-8 -*-
"""§B 매도 타이밍 — 분봉 해상도로 순서 재판정. 사전등록 `PREREG_MINUTE_FLOW.md`(`766e7b0`).

일봉판(`run_selltiming.py`)은 T1 7/7 인데 **반증축 T3 도 7/7** 이라 판별력 0 이었다.
원인은 해상도 — 7건 중 6건이 모든 레그가 «하루 안»에 들어가 순서 제약이 사라졌다.

분봉에서는 그 하루의 **가격 경로가 고정**이므로, 시간순이 성립하려면 그 안에서 실제로
가격이 내려가야 한다. 여기서 안 갈리면 **7건으로는 못 푼다고 적고 종결한다.**

🔴 S2 반증축 기준(시간순 − 역순 ≥ 2)은 **사전등록에 못박혀 있다.** 사후 완화 금지.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

from reconstruct_prices import TARGETS, tick
from run_tests import CODES, DSN
from solve_common_band import feasible_P

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
BREAKEVEN = 1.0
MAX_SOLUTIONS = 400      # 해가 많은 건에서 계산량 상한. 초과 시 균등 간격으로 솎고 «그 사실을 인쇄».


def say(s=""):
    print(s)
    OUT.append(s)


def legs_prices(P, legs):
    out = []
    for r in legs:
        S_ideal = P * (1 + r / 100.0)
        t = tick(S_ideal)
        out.append(round(S_ideal / t) * t)
    return out


def assign(dsets, ascending=True):
    """비감소(또는 비증가) 인덱스 배정이 있으면 그 배정. 그리디 = 최적."""
    picked, cur = [], None
    for s in dsets:
        cand = [d for d in s if cur is None or (d >= cur if ascending else d <= cur)]
        if not cand:
            return None
        cur = min(cand) if ascending else max(cand)
        picked.append(cur)
    return picked


def main() -> int:
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    say("# §B 매도 타이밍 — 분봉 해상도로 순서 재판정\n")
    say("일봉판은 T1 7/7 · 반증축 T3 **7/7** 로 판별력 0 이었다(창이 넓어 어느 순서든 배정됨).")
    say("분봉에서는 하루의 **가격 경로가 고정**이라 시간순은 실제로 내려가야 성립한다.\n")

    n_asc = n_desc = 0
    s3_hit = s3_tot = 0
    rows = []

    for name, d0, d1, legs, fill in TARGETS:
        code = CODES[name]
        # 분봉 창 (거래정지일 제외 — §0 규약)
        cur.execute(
            "SELECT date, time, low, high FROM minute_candles "
            "WHERE stock_code=%s AND date BETWEEN %s AND %s AND volume > 0 "
            "ORDER BY date, time",
            (code, d0.replace("-", ""), d1.replace("-", "")))
        mb = cur.fetchall()
        if not mb:
            rows.append((name, "🔴 분봉 없음", "—", "—", "—", "—"))
            continue
        bars = [(r[2], r[3]) for r in mb]        # (low, high) 시간순
        stamps = [(r[0], r[1]) for r in mb]

        cur.execute("SELECT low, high FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s ORDER BY date", (code, d0, d1))
        dr = cur.fetchall()
        ranges = [(r[0], r[1]) for r in dr]
        Ps = feasible_P(legs, ranges, min(r[0] for r in dr), max(r[1] for r in dr))
        if not Ps:
            rows.append((name, "🔴 복원 해 없음", "—", "—", "—", "—"))
            continue
        n_all = len(Ps)
        if n_all > MAX_SOLUTIONS:
            step = n_all / MAX_SOLUTIONS
            Ps = [Ps[int(i * step)] for i in range(MAX_SOLUTIONS)]

        asc_ok = desc_ok = False
        asc_ex = None
        for P in Ps:
            S = legs_prices(P, legs)
            ds = [[i for i, (lo, hi) in enumerate(bars) if lo <= s <= hi] for s in S]
            if any(not x for x in ds):
                continue
            a = assign(ds, True)
            if a and not asc_ok:
                asc_ok, asc_ex = True, (P, a)
            if assign(ds, False):
                desc_ok = True
            if asc_ok and desc_ok:
                break

        n_asc += asc_ok
        n_desc += desc_ok

        span = "—"
        s3 = "—"
        if asc_ok:
            P, a = asc_ex
            d_first, t_first = stamps[a[0]]
            d_last, t_last = stamps[a[-1]]
            span = f"{d_first[4:6]}/{d_first[6:]} {t_first[:2]}:{t_first[2:4]} → {d_last[4:6]}/{d_last[6:]} {t_last[:2]}:{t_last[2:4]}"
            if abs(legs[-1]) < BREAKEVEN:
                s3_tot += 1
                ok = a[-1] == max(a)
                s3_hit += ok
                s3 = "✅" if ok else "❌"

        note = f"{n_all}해" + (f"→{len(Ps)} 솎음" if n_all > MAX_SOLUTIONS else "")
        rows.append((name, note, "✅" if asc_ok else "❌", "✅" if desc_ok else "❌", span, s3))

    say("| 종목 | 해 | 시간순 | 역순 | 첫→끝 (시간순) | S3 본전=마지막 |")
    say("|---|---|---|---|---|---|")
    for r in rows:
        say(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |")
    say()

    n = len(rows)
    say(f"## S1 — 시간순 배정 가능: **{n_asc}/{n}** (기준 5건 이상)")
    say(f"{'✅ 지지' if n_asc >= 5 else '❌ 기각'}\n")
    say(f"## S3 — 본전 레그가 마지막: **{s3_hit}/{s3_tot}**")
    say(f"{'✅ 지지' if s3_tot and s3_hit == s3_tot else '❌ 기각' if s3_tot else '⛔ 해당 없음'}\n")
    diff = n_asc - n_desc
    say(f"## S2 (반증축) — 역순 배정 가능: **{n_desc}/{n}** · 차이 **{diff}** (기준 ≥ 2)")
    if diff >= 2:
        say(f"🟡 **시간순이 역순보다 낫다** (차 {diff}). 단 n={n} 이라 증거로 승격하지 않는다.")
    else:
        say(f"🔴 **판별력 없음** — 차이 {diff} < 2 ⇒ **S1 지지를 취소한다.**")
        say("🔑 ***분봉으로 올려도 안 갈렸다면 이 축은 7건으로 못 푼다.*** 사전등록 §B 의 종결 조건이다.")
    say()
    say("🔴 **in-sample 탐색이다.** 확정 검정은 `PREREG_MINUTE_FLOW.md` §D 의 P2.")

    cur.close()
    conn.close()
    (BASE / "RESULTS_MINUTE_SELLTIMING.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_MINUTE_SELLTIMING.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

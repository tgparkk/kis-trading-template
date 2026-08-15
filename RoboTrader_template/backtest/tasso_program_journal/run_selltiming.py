# -*- coding: utf-8 -*-
"""매도의 «시각·순서» — 사전등록 `PREREG_SELLTIMING.md`(커밋 b64093d) 실행.

표적: 레그 수익률이 **비증가**인데, 그게 시간순이면 «내려가면서» 판 것(하락 추종)이고
      역순이면 «올라가면서» 판 것(목표가 사다리)이다. 두 기전은 완전히 다르다.

방법(사전등록 §3 그대로): feasible_P(잔차 ≤0.025%p, gross) → 각 해의 레그 i 에 대해
  체결 가능 날짜 Dᵢ = {d : low_d ≤ Sᵢ ≤ high_d} → 시간순/역순 배정 존재를 그리디로 판정.

🔴 T3(반증축)를 반드시 함께 낸다 — 같은 가격이 여러 날 가능해 Dᵢ 가 크므로
   「배정이 존재한다」는 약한 주장이다. 역순도 같은 정도로 가능하면 판별력 없음.

라이브 트리 import 0건.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

from reconstruct_prices import TARGETS, gross_ret, tick
from run_tests import CODES, DSN
from solve_common_band import feasible_P

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
BREAKEVEN = 1.0     # |ret| < 1.0%p 이면 「본전 매도」 (PREREG.md Q3 P1 과 동일 기준)


def say(s=""):
    print(s)
    OUT.append(s)


def legs_prices(P, legs):
    """평단 P 에서 각 레그의 격자 매도가."""
    out = []
    for r in legs:
        S_ideal = P * (1 + r / 100.0)
        t = tick(S_ideal)
        out.append(round(S_ideal / t) * t)
    return out


def day_sets(S_list, bars):
    """레그별 체결 가능 «날짜 인덱스» 집합. bars = [(date, low, high), ...] 시간순."""
    return [[i for i, (_, lo, hi) in enumerate(bars) if lo <= S <= hi] for S in S_list]


def assign(dsets, ascending=True):
    """비감소(또는 비증가) 날짜 배정이 있으면 그 배정을 돌려준다. 그리디 = 최적.

    비감소: 앞에서부터 «가능한 가장 이른» 날을 고른다.
    비증가: 뒤집어서 같은 논리를 적용한다.
    """
    seq = dsets if ascending else [sorted(s, reverse=True) for s in dsets]
    picked = []
    cur = None
    for s in seq:
        cand = [d for d in s if cur is None or (d >= cur if ascending else d <= cur)]
        if not cand:
            return None
        cur = min(cand) if ascending else max(cand)
        picked.append(cur)
    return picked


def main() -> int:
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    say("# 매도의 «시각·순서» — 사전등록 PREREG_SELLTIMING.md 실행 결과\n")
    say("`h` 같은 가격 레벨이 아니라 **레그가 며칠에 일어났는가**를 묻는다.\n")

    n_asc = n_desc = 0
    n_both = 0
    t2_hit = t2_tot = 0
    rows = []

    for name, d0, d1, legs, fill in TARGETS:
        code = CODES[name]
        cur.execute("SELECT date, low, high FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s ORDER BY date", (code, d0, d1))
        bars = [(r[0], r[1], r[2]) for r in cur.fetchall()]
        ranges = [(lo, hi) for _, lo, hi in bars]
        lo, hi = min(r[1] for r in bars), max(r[2] for r in bars)
        Ps = feasible_P(legs, ranges, lo, hi)
        if not Ps:
            say(f"- **{name}** — 복원 해 없음, 제외")
            continue

        asc_ok = desc_ok = False
        asc_example = None
        for P in Ps:
            S = legs_prices(P, legs)
            ds = day_sets(S, bars)
            if any(not s for s in ds):
                continue
            a = assign(ds, ascending=True)
            d = assign(ds, ascending=False)
            if a and not asc_ok:
                asc_ok, asc_example = True, (P, S, a)
            if d:
                desc_ok = True
            if asc_ok and desc_ok:
                break

        n_asc += asc_ok
        n_desc += desc_ok
        n_both += (asc_ok and desc_ok)

        # T2 — 본전 레그가 시간순 배정의 «마지막 날짜»인가
        t2 = "—"
        if asc_ok and abs(legs[-1]) < BREAKEVEN:
            t2_tot += 1
            P, S, a = asc_example
            last_day = bars[a[-1]][0]
            is_last = a[-1] == max(a)
            t2_hit += is_last
            t2 = f"{'✅' if is_last else '❌'} {last_day}"

        span = "—"
        if asc_ok:
            P, S, a = asc_example
            span = f"{bars[a[0]][0]} → {bars[a[-1]][0]} ({a[-1] - a[0]}거래일)"

        rows.append((name, fill, len(legs), len(Ps),
                     "✅" if asc_ok else "❌", "✅" if desc_ok else "❌", span, t2))

    say("| 종목 | 체결 | 레그 | 해 | 시간순 | 역순 | 첫→끝 (시간순) | T2 본전=마지막 |")
    say("|---|---|---|---|---|---|---|---|")
    for r in rows:
        say(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} |")
    say()

    n = len(rows)
    say(f"## T1 — 시간순 배정이 가능한 건: **{n_asc}/{n}**  (기준: 5건 이상)")
    say(f"{'✅ 지지' if n_asc >= 5 else '❌ 기각'}\n")
    say(f"## T2 — 본전 레그가 마지막 날짜: **{t2_hit}/{t2_tot}**  (기준: 전부)")
    say(f"{'✅ 지지' if t2_tot and t2_hit == t2_tot else '❌ 기각' if t2_tot else '⛔ 해당 건 없음'}\n")
    say(f"## T3 (반증축) — 역순 배정이 가능한 건: **{n_desc}/{n}** · 양쪽 다 가능 {n_both}/{n}")
    if n_asc - n_desc <= 1:
        say(f"🔴 **판별력 없음** — 시간순({n_asc}) − 역순({n_desc}) = {n_asc - n_desc} ≤ 1.")
        say("⇒ **T1 지지를 취소한다.** 일봉 [저가,고가] 창이 넓어 어느 순서든 배정이 만들어진다.")
        say("🔑 ***반증축을 안 걸었으면 「7/7 시간순 가능」을 지지로 적었을 것이다*** — 세 번째 사례.")
    else:
        say(f"🟡 **시간순이 역순보다 낫다** (차 {n_asc - n_desc}). 단 n 이 작다.")
    say()
    say("🔴 **어느 쪽이든 in-sample 탐색이다.** 확정 검정은 `PREREG_SELLTIMING.md` §5 의 M1~M3.")

    cur.close()
    conn.close()
    (BASE / "RESULTS_SELLTIMING.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_SELLTIMING.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

# -*- coding: utf-8 -*-
"""§A 매수 타이밍 — 등록일 «몇 시»에 샀나. 사전등록 `PREREG_MINUTE_FLOW.md`(`766e7b0`) 실행.

🔑 표적은 자유도 0 의 이분법이다:
   **복원 평단 `P` 의 첫 도달 시각 `t(P)` 가 그날 «고가 시각» `t_high` 보다 앞인가 뒤인가.**
   올라가는 도중에 샀으면 **앞**(추격 진입), 눌림을 기다렸으면 **뒤**(밴드 매수).

🔴 N3 반증축을 반드시 함께 낸다 — `t(P) < t_high` 는 **`P` 의 당일 위치가 강제**할 수 있다.
   같은 날 호가격자에서 `P'` 를 균등 추출한 귀무로 그걸 통제한다.

라이브 트리 import 0건.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import psycopg2

from reconstruct_prices import TARGETS, tick
from run_tests import CODES, DSN
from solve_common_band import feasible_P

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
N_NULL = 20000
NULL_SEED = 20260815      # 🔴 바꾸지 말 것 — 바꾸면 산출물이 재현되지 않는다.

# 🔴 관리자 오류 정정 (첫 실행 뒤 발견, 양쪽 결과를 RESULTS 에 함께 남긴다)
#    첫 실행은 `reconstruct_prices.TARGETS` 의 `d0` 를 등록일로 썼는데, `unknown` 정밀도 2건은
#    그 값이 **복원 창 시작일 2026-08-01 = 토요일(휴장)** 이었다. 그래서 「분봉 없음」이 떴고
#    N1 이 4/7 로 나왔다. 사전등록 문언은 «등록일»이므로 이건 이탈이 아니라 **버그 수정**이다.
#    등록일 출처 = `PREREG_SELECTION.md` §5 (exact 4건 + approx 2건) + 씨피시스템 7/30.
REG_DATES = {
    "에스피지": "2026-07-31",
    "솔트룩스": "2026-08-04",
    "마키나락스": "2026-08-05",
    "매드업": "2026-08-06",
    "빛과전자": "2026-08-05",
    "케이엔알시스템": "2026-07-28",
    "씨피시스템": "2026-07-30",
}


def say(s=""):
    print(s)
    OUT.append(s)


def hhmm(t: str) -> str:
    t = str(t).zfill(6)
    return f"{t[:2]}:{t[2:4]}"


def first_touch(bars, price):
    """[(time, low, high), ...] 에서 price 가 처음 드는 봉의 시각. 없으면 None."""
    for t, lo, hi in bars:
        if lo <= price <= hi:
            return t
    return None


def main() -> int:
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    say("# §A 매수 타이밍 — 등록일 «몇 시»에 샀나\n")
    say("`t(P)` = 복원 평단이 처음 닿은 분봉 시각 · `t_high` = 그날 고가가 처음 찍힌 시각\n")
    say("🔑 **`t(P) < t_high` 이면 올라가는 도중에 샀다(추격), 뒤면 눌림을 기다렸다(밴드).**\n")
    say("> 🔴 **관리자 오류 정정 (첫 실행 → 재실행).** 첫 실행은 `TARGETS.d0` 를 등록일로 썼는데,")
    say("> `unknown` 정밀도 2건(케이엔알·씨피시스템)은 그 값이 **복원 창 시작일 2026-08-01 =**")
    say("> **토요일(휴장)** 이라 「분봉 없음」이 떴다. 사전등록 문언이 «등록일»이므로 **버그 수정**이지")
    say("> 이탈이 아니다. 첫 실행 수치: **N1 4/7 (기각)** · N2 4/4 · N3 백분위 **60.4%**.")
    say("> ⚠️ 결과를 본 뒤 고쳤으므로 **양쪽을 함께 남긴다.** 결론(N3 기각)은 양쪽에서 같다.\n")

    rows = []
    for name, _d0_win, d1, legs, fill in TARGETS:
        code = CODES[name]
        d0 = REG_DATES[name]                 # 🔴 창 시작일이 아니라 «등록일»
        ymd = d0.replace("-", "")

        # 등록일 분봉 (거래정지일이면 volume 합이 0 — §0 규약에 따라 제외)
        cur.execute("SELECT time, low, high, volume FROM minute_candles "
                    "WHERE stock_code=%s AND date=%s ORDER BY time", (code, ymd))
        mb = cur.fetchall()
        if not mb:
            # 🔑 「분봉 없음」에 두 종류가 있다 — 휴장일 vs 미수집. 같은 라벨로 세지 말 것.
            cur.execute("SELECT 1 FROM daily_prices WHERE stock_code=%s AND date=%s",
                        (code, d0))
            why = "미수집" if cur.fetchone() else "휴장일"
            rows.append((name, f"🔴 분봉 없음({why})", "—", "—", "—", "—"))
            continue
        if sum(r[3] or 0 for r in mb) == 0:
            rows.append((name, "🔴 거래정지(volume 0)", "—", "—", "—", "—"))
            continue
        bars = [(r[0], r[1], r[2]) for r in mb]
        day_lo = min(b[1] for b in bars)
        day_hi = max(b[2] for b in bars)
        t_high = first_touch(bars, day_hi)

        # feasible P (일봉 창 기준 — 복원 정의를 바꾸지 않는다)
        cur.execute("SELECT low, high FROM daily_prices WHERE stock_code=%s "
                    "AND date BETWEEN %s AND %s ORDER BY date", (code, _d0_win, d1))
        dr = cur.fetchall()
        ranges = [(r[0], r[1]) for r in dr]
        Ps = feasible_P(legs, ranges, min(r[0] for r in dr), max(r[1] for r in dr))
        if not Ps:
            rows.append((name, "🔴 복원 해 없음", "—", "—", "—", "—"))
            continue

        touched = [(P, first_touch(bars, P)) for P in Ps]
        hit = [(P, t) for P, t in touched if t is not None]
        if not hit:
            rows.append((name, f"🔴 P 미도달 (해 {len(Ps)})", "—", hhmm(t_high), "—", "—"))
            continue

        hit.sort(key=lambda x: x[1])
        t_med = hit[len(hit) // 2][1]                  # t(P) 의 중앙값
        P_med = hit[len(hit) // 2][0]
        pos = (P_med - day_lo) / (day_hi - day_lo) if day_hi > day_lo else float("nan")
        verdict = "앞(추격)" if t_med < t_high else "뒤(밴드)"
        rows.append((name, f"{len(hit)}/{len(Ps)}", hhmm(t_med), hhmm(t_high),
                     verdict, f"{pos:.2f}"))

    say("| 종목 | P 도달 해 | t(P) 중앙 | t_high | 판정 | P 위치 |")
    say("|---|---|---|---|---|---|")
    for r in rows:
        say(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |")
    say()

    n_ok = sum(1 for r in rows if r[2] != "—")
    n_before = sum(1 for r in rows if r[4] == "앞(추격)")
    say(f"## N1 — `P` 가 등록일 분봉에서 도달 가능: **{n_ok}/{len(rows)}** (기준 5건 이상)")
    say(f"{'✅ 지지' if n_ok >= 5 else '❌ 기각 ⇒ §A 전체 기각'}\n")
    say(f"## N2 — `t(P) < t_high` (앞=추격): **{n_before}/{n_ok}** (기준 과반)")
    say(f"{'✅ 지지' if n_ok and n_before * 2 > n_ok else '❌ 기각'}\n")

    # ── N3 반증축 ────────────────────────────────────────────────────────────
    say("## N3 (반증축) — `P` 의 당일 위치가 답을 강제하는가\n")
    say(f"같은 날 호가격자에서 `P'` 를 균등 추출({N_NULL:,}회 · 시드 {NULL_SEED}) 해 같은 비율을 잰다.\n")
    rng = random.Random(NULL_SEED)
    null_counts = []
    day_cache = []
    for name, _d0_win, d1, legs, fill in TARGETS:
        code = CODES[name]
        ymd = REG_DATES[name].replace("-", "")
        cur.execute("SELECT time, low, high, volume FROM minute_candles "
                    "WHERE stock_code=%s AND date=%s ORDER BY time", (code, ymd))
        mb = cur.fetchall()
        if not mb or sum(r[3] or 0 for r in mb) == 0:
            continue
        bars = [(r[0], r[1], r[2]) for r in mb]
        lo, hi = min(b[1] for b in bars), max(b[2] for b in bars)
        t = tick(lo)
        grid = [lo + k * t for k in range(int((hi - lo) / t) + 1)]
        grid = [g for g in grid if first_touch(bars, g) is not None]
        day_cache.append((name, bars, grid, first_touch(bars, hi)))

    drawn = {nm: set() for nm, _, _, _ in day_cache}
    for _ in range(N_NULL):
        c = 0
        for nm, bars, grid, th in day_cache:
            P2 = grid[rng.randrange(len(grid))]
            drawn[nm].add(P2)
            if first_touch(bars, P2) < th:
                c += 1
        null_counts.append(c)

    ge = sum(1 for x in null_counts if x >= n_before)
    pct = ge / len(null_counts) * 100
    say("자리별 실제 표집 가격 종수 (절단형 귀무 재발 감지):\n")
    say("| 종목 | 표집/격자 |")
    say("|---|---|")
    for nm, _, grid, _ in day_cache:
        say(f"| {nm} | {len(drawn[nm])}/{len(grid)} |")
    say()
    say(f"- 귀무 평균 **{sum(null_counts)/len(null_counts):.2f}** · 최대 {max(null_counts)}")
    say(f"- 관측({n_before}) 이상인 표본 **{ge:,}/{len(null_counts):,}** ⇒ 백분위 **{pct:.1f}%**\n")
    if pct >= 5.0:
        say(f"🔴 **판별력 없음** — 백분위 {pct:.1f}% ≥ 5%. 같은 날 아무 가격이나 골라도 "
            "이만큼 나온다 ⇒ ***N2 지지를 취소한다.*** 「앞/뒤」는 `P` 의 당일 위치가 만든 것이다.")
    else:
        say(f"🟡 **귀무보다 낫다** (백분위 {pct:.1f}% < 5%). 단 n=7 이라 증거로 승격하지 않는다.")
    say()
    say("🔴 **in-sample 탐색이다.** 확정 검정은 `PREREG_MINUTE_FLOW.md` §D 의 P1.")

    cur.close()
    conn.close()
    (BASE / "RESULTS_MINUTE_ENTRY.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_MINUTE_ENTRY.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

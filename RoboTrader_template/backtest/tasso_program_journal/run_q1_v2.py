# -*- coding: utf-8 -*-
"""PREREG_Q1_V2.md §2 실행 — H 를 「등록일 포함」 창의 최고 고가로.

🔴 in-sample 재검정은 **탐색적**이다(같은 7건에 정의만 바꿈 = 사후적합).
   진짜 검정은 §3 의 다음 글 예측 R1~R3 이다.

라이브 트리 import 0건.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

from run_tests import CODES, DSN, TRADES_Q1

BASE = Path(__file__).resolve().parent
OUT: list[str] = []


def say(s=""):
    print(s)
    OUT.append(s)


def series(cur, code, d0, d1):
    cur.execute(
        "SELECT date, high, low, close FROM daily_prices "
        "WHERE stock_code=%s AND date BETWEEN %s AND %s ORDER BY date", (code, d0, d1))
    return cur.fetchall()


def main():
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    say("# Q1 v2 결과 — H = 「등록일 포함」 창의 최고 고가 (🟡 탐색적)\n")

    WINDOWS = {"H4": 5, "H5": 10, "H6": 20}
    res = {}

    say("| 종목 | 라벨 | 등록일 | 등록일고가 | 이후최저가 | DD(H4·5일) | DD(H5·10일) | DD(H6·20일) | 등록일=창최고? |")
    say("|---|---|---|---|---|---|---|---|---|")
    surge_hit = surge_tot = 0
    for name, d, prec, end, lab in TRADES_Q1:
        code = CODES[name]
        pre = series(cur, code, "2026-05-01", d)
        post = series(cur, code, d, end)
        if not pre or not post:
            say(f"| {name} | {lab} | {d} | (데이터 없음) | | | | | |")
            continue
        low = min(r[2] for r in post)
        dd = {}
        for key, k in WINDOWS.items():
            win = pre[-k:]                       # 등록일 포함
            h = max(r[1] for r in win)
            dd[key] = 1 - low / h
        res[name] = (lab, dd)

        d_high = pre[-1][1]
        w20 = pre[-20:]
        is_surge = abs(d_high - max(r[1] for r in w20)) < 1e-9
        if prec in ("exact", "approx"):
            surge_tot += 1
            surge_hit += is_surge
        say(f"| {name} | {lab} | {d} | {d_high:,.0f} | {low:,.0f} | "
            f"{dd['H4']*100:.2f}% | {dd['H5']*100:.2f}% | {dd['H6']*100:.2f}% | "
            f"{'✅' if is_surge else '❌'} |")

    say("\n## 통계량 T = min(DD‖full) − max(DD‖first_only)\n")
    say("| H 정의 | min(full) | max(first_only) | T | |")
    say("|---|---|---|---|---|")
    signs = []
    for key in WINDOWS:
        f = [dd[key] for lab, dd in res.values() if lab == "full"]
        o = [dd[key] for lab, dd in res.values() if lab == "first_only"]
        T = min(f) - max(o)
        signs.append(T > 0)
        say(f"| {key} | {min(f)*100:.2f}% | {max(o)*100:.2f}% | **{T*100:+.2f}%p** | "
            f"{'✅' if T > 0 else '❌'} |")

    ok = all(signs)
    say(f"\n**판정: {'🟡 탐색적 지지 (3정의 전부 T>0)' if ok else '🔴 가설 기각 — 정의 탓이 아니다'}**")
    if not ok:
        say("v1(등록일 제외 계열)에 이어 v2(등록일 포함 계열)까지 실패하면 남는 설명이 없다.")
    say("🔴 **어느 쪽이든 「검정 통과」가 아니다** — n=2 vs 5 · 같은 7건 사후적합.\n")

    say(f"## 부수 관측 — 등록일이 급등일인가: **{surge_hit}/{surge_tot}**")
    say("(등록일 고가 == 직전 20거래일(등록일 포함) 최고 고가인 건의 비율 · 기술이지 예측 아님)\n")

    say("## 구간 추정\n")
    for key in WINDOWS:
        f = [dd[key] for lab, dd in res.values() if lab == "full"]
        o = [dd[key] for lab, dd in res.values() if lab == "first_only"]
        say(f"- `{key}`: `b₁ ≤ {min(o)*100:.2f}%` · `b₂ > {max(o)*100:.2f}%` · `b_last ≤ {min(f)*100:.2f}%`")

    # ── 예상 못 한 수렴: Q4 의 자가보고 −36.9% 가 v2 앵커로 재현되는가 ──────────
    say("\n## 🔑 예상하지 못한 수렴 — 자가보고 −36.9%\n")
    say("`PREREG_Q1_V2.md`(커밋 `c35ecec`)는 **−36.9% 를 한 번도 언급하지 않는다.**")
    say("v2 의 H 정의는 *「등록일이 창에서 빠져 있다」* 는 기전 이유만으로 골랐다.")
    say("그 정의로 잰 값이 저자 숫자와 얼마나 붙는지 사후에 확인한다.\n")
    rows = series(cur, CODES["케이엔알시스템"], "2026-07-28", "2026-08-07")
    h = rows[0][1]
    lo = min(r[2] for r in rows)
    lo_day = min(rows, key=lambda r: r[2])[0]
    dd = (1 - lo / h) * 100
    say(f"- 앵커 = 등록일(2026-07-28) **고가 {h:,.0f}**")
    say(f"- 저점 = {lo_day} **저가 {lo:,.0f}**")
    say(f"- 낙폭 = **−{dd:.2f}%** · 저자 진술 **−36.9%** · 차이 **{abs(dd-36.9):.2f}%p**")
    say("\n⚠️ **사후 관측이다.** 다만 −36.9% 는 정의 선택에 **쓰이지 않았고**, 사전등록 커밋이")
    say("실행보다 앞서므로 *「숫자를 보고 정의를 맞췄다」* 는 구조적으로 불가능하다.")
    say("🔑 ***Q4 가 판별 불가였던 것은 기전 없이 격자만 훑었기 때문이다*** — 72쌍 중")
    say("기전이 지목하는 단 하나가 저자 숫자에 붙는다. **다음 글에서 재현되면 그때 증거다.**")

    cur.close()
    conn.close()
    (BASE / "RESULTS_Q1_V2.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_Q1_V2.md")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()

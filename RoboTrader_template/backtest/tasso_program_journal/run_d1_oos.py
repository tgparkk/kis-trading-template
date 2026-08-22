# -*- coding: utf-8 -*-
"""PREREG_D1_OOS.md 실행 — D1(거래대금/시총) out-of-sample 재검정.

사전등록 `PREREG_D1_OOS.md`(커밋 d632ce1) → 이 스크립트 → `RESULTS_D1_OOS_NUMBERS.md`.
🔴 문언 분류(A=「급등 당시」 / B=「최대」)는 **계산 전에** 사전등록 §2 표에서 확정된 것이며
   여기서는 그대로 옮겨 쓴다. 값을 보고 바꾸지 않는다.

라이브 트리 import 0건.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

TOL = 0.20          # 사전등록 §2: 상대오차 ±20% (원 사전등록 그대로)
N2_DEGRADE = 30     # 사전등록 §4 N2: m 중앙값이 이 값 이상이면 「판별력 없음」으로 강등

# (표시명, 종목코드, 자가보고, 명시날짜|None, 등록일, 주측정 A|B)  — 사전등록 §2 표 그대로
TARGETS = [
    ("이노테크",             "469610", 0.70, "2026-08-13", "2026-08-13", "A"),
    ("PS일렉트로닉스",       "332570", 0.30, "2026-08-13", "2026-08-13", "A"),
    ("한켐",                 "457370", 0.83, None,         "2026-08-12", "B"),
    ("금호건설[등록08-12]",  "002990", 0.99, None,         "2026-08-12", "B"),
    ("금호건설[대안08-20]",  "002990", 0.99, None,         "2026-08-20", "B"),
    ("지투파워",             "388050", 0.77, "2026-08-13", "2026-08-13", "B"),
]
PSEUDO = ("KOSPI", "KOSDAQ", "KS11", "KQ11")


def say(s=""):
    print(s)
    OUT.append(s)


# 🔑 콘솔이 cp949 면 표의 전각 기호에서 죽는다. 산출 «파일»은 항상 UTF-8 로 쓴다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001  (구버전 파이썬·리다이렉션 환경)
    pass


def d1_series(cur, code):
    """(date, d1) 전 계열. market_cap<=0 또는 NULL 이면 d1=None (분모에서 뺀다)."""
    cur.execute(
        "SELECT date, trading_value, market_cap FROM daily_prices "
        "WHERE stock_code=%s ORDER BY date", (code,))
    out = []
    for dt, tv, mc in cur.fetchall():
        out.append((dt, (float(tv) / float(mc)) if (mc and mc > 0 and tv is not None) else None))
    return out


def universe_m(cur, date, selfrep):
    """N2: 그날 유니버스에서 자가보고값 ±20% 안에 드는 종목 수, 유니버스 크기."""
    cur.execute(
        "SELECT count(*) FILTER (WHERE trading_value::numeric/market_cap::numeric "
        "                        BETWEEN %s AND %s), count(*) "
        "FROM daily_prices WHERE date=%s AND market_cap>0 AND trading_value IS NOT NULL "
        "  AND stock_code <> ALL(%s)",
        (selfrep * (1 - TOL), selfrep * (1 + TOL), date, list(PSEUDO)))
    return cur.fetchone()


def main():
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()

    cur.execute("SELECT max(date) FROM daily_prices")
    max_date = cur.fetchone()[0]

    say("# RESULTS_D1_OOS_NUMBERS — 기계 생성 (수정 금지)\n")
    say(f"사전등록 `PREREG_D1_OOS.md` · 생성 `run_d1_oos.py` · `daily_prices` 최신 봉 **{max_date}**\n")
    say("| 종목 | 자가보고 | 주측정 | A 명시일 | B1 [D-19,D+4] | B1 최대일 | B2 [D-4,D+4] | 주측정값 | 상대오차 | 판정 | D6 | 창봉수 | 최대off | 시총결측 |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")

    rows, judged = [], []
    for name, code, sr, named, reg, prim in TARGETS:
        ser = d1_series(cur, code)
        idx = {d: i for i, (d, _) in enumerate(ser)}
        if reg not in idx:
            say(f"| {name} | {sr} | — | — | — | — | — | — | — | **등록일 봉 없음** | — | — | — | — |")
            continue
        r = idx[reg]
        def win(lo, hi):
            seg = [(d, v) for d, v in ser[max(0, r + lo): r + hi + 1] if v is not None]
            return max(seg, key=lambda t: t[1]) if seg else (None, None)
        b1d, b1 = win(-19, 4)
        b2d, b2 = win(-4, 4)
        a = next((v for d, v in ser if d == named), None) if named else None
        miss = sum(1 for d, v in ser[max(0, r - 19): r + 5] if v is None)
        bars = len(ser[max(0, r - 19): r + 5])
        maxoff = len(ser) - 1 - r

        val = a if prim == "A" else b1
        err = abs(val - sr) / sr if val is not None else None
        ok = (err is not None and err <= TOL)
        d6 = val * 10 if val is not None else None
        ok6 = (d6 is not None and abs(d6 - sr) / sr <= TOL)

        say("| {} | {:.2f} | {} | {} | {} | {} | {} | **{}** | {} | {} | {} | {} | {} | {} |".format(
            name, sr, prim,
            f"{a:.4f}" if a is not None else "—",
            f"{b1:.4f}" if b1 is not None else "—", b1d or "—",
            f"{b2:.4f}" if b2 is not None else "—",
            f"{val:.4f}" if val is not None else "—",
            f"{100*err:.2f}%" if err is not None else "—",
            "✅ 재현" if ok else "❌ 불일치",
            f"{d6:.3f}" if d6 is not None else "—", bars, maxoff, miss))

        # 금호건설 대안 등록일은 같은 자가보고의 중복 계산이므로 분모에 넣지 않는다
        if "대안" not in name:
            judged.append((name, sr, prim, val, err, ok, ok6))
        rows.append((name, sr, prim, b1d if prim == "B" else named))

    say()
    say("## 판정 (사전등록 §3)\n")
    n = len(judged)
    # 🔴 초판 결함: 조건 없이 `sum(1 for ...)` 를 써서 «전건»을 셌다(5/5). 아래 문언별 분해가
    #    3/3·0/2 를 인쇄해 어긋난 덕에 드러났다. 🔑 같은 수를 두 경로로 인쇄하면 오류가 스스로 드러난다.
    rec = sum(1 for j in judged if j[5])
    rec6 = sum(1 for j in judged if j[6])
    assert rec == sum(1 for j in judged if j[4] is not None and j[4] <= TOL), "재현 집계 불일치"
    verdict = "G1 지지" if rec >= 4 else ("G2 기각" if rec <= 2 else "🟡 판별 불가")
    say(f"- 주 측정 재현 **{rec}/{n}** ⇒ **{verdict}** (규칙: ≥4 지지 / ≤2 기각 / 3 판별 불가)")
    say(f"- **N1** 반증축: `D6 = D1×10` 재현 **{rec6}/{n}** — "
        f"{'🔴 D6 가 더 맞힌다 ⇒ G1 지지 취소' if rec6 > rec else '✅ 미발동'}")

    say()
    say("### N2 (판별력 · 대칭 단언)\n")
    say("| 종목 | 기준일 | 대역 내 종목 수 `m` | 유니버스 |")
    say("|---|---|---|---|")
    ms = []
    for (name, sr, prim, mdate) in rows:
        if "대안" in name or mdate is None:
            continue
        m, tot = universe_m(cur, mdate, sr)
        ms.append(m)
        say(f"| {name} | {mdate} | **{m}** | {tot} |")
    med = sorted(ms)[len(ms) // 2] if ms else None
    say()
    say(f"- `m` 중앙값 **{med}** (문턱 {N2_DEGRADE}) ⇒ "
        f"**{'🔴 판별력 없음으로 강등' if (med or 0) >= N2_DEGRADE else '✅ 판별력 있음'}**")

    say()
    say("### N3 (창 민감도)\n")
    say("표의 `B1` 과 `B2` 열을 대조할 것. **전부 같으면 창 의존 없음.**")

    say()
    say("### 문언별 분해 (사전등록되지 않은 사후 관측 — §5 W1~W3 으로 신규 동결)\n")
    for lab, sel in (("「최대」(B)", "B"), ("「당시」(A)", "A")):
        g = [j for j in judged if j[2] == sel]
        if not g:
            continue
        say(f"- {lab}: **{sum(1 for j in g if j[5])}/{len(g)}** 재현 · 오차 "
            + " · ".join(f"{100*j[4]:.2f}%" for j in g if j[4] is not None))

    (BASE / "RESULTS_D1_OOS_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""PREREG.md §3~§6 검정 실행. 결과는 RESULTS.md 로 사람이 옮겨 적는다.

라이브 트리 import 0건(psycopg2 + 표준 라이브러리). `utils.logger` 미사용.
DB 는 읽기만 한다(SELECT).
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

import psycopg2

BASE = Path(__file__).resolve().parent
DSN = dict(host="127.0.0.1", port=5433, user="robotrader",
           password="1234", dbname="kis_template")

# 종목코드 — stock_industry 조회 + KRX 공시(매드업 0039P0, 2026-07-01 코스닥 신규상장).
# ⚠️ 「삼화전자」는 009470 삼화전기가 **아니라** 011230 삼화전자공업이다(이름이 비슷한 별개 회사).
CODES = {
    "가온칩스": "399720", "다날": "064260", "다스코": "058730", "마키나락스": "477850",
    "티엑스알로보틱스": "484810", "금호건설": "002990", "데이타솔루션": "263800",
    "셀바스AI": "108860", "코스모로보틱스": "439960", "삼기": "122350",
    "씨피시스템": "413630", "현대약품": "004310", "금호전기": "001210",
    "동신건설": "025950", "남화토건": "091590", "삼호개발": "010960",
    "한성크린텍": "066980", "삼기에너지솔루션즈": "419050", "에스폴리텍": "050760",
    "삼화전자": "011230", "모나미": "005360", "한성기업": "003680",
    "지엔씨에너지": "119850", "케이엔알시스템": "199430", "에스피지": "058610",
    "솔트룩스": "304100", "매드업": "0039P0", "빛과전자": "069540",
}

OUT: list[str] = []


def say(s=""):
    print(s)
    OUT.append(s)


def bars(cur, code, d0, d1):
    cur.execute(
        "SELECT date, open, high, low, close, trading_value, market_cap "
        "FROM daily_prices WHERE stock_code=%s AND date BETWEEN %s AND %s ORDER BY date",
        (code, d0, d1))
    return cur.fetchall()


# ─── Q4: 자가보고 −36.9% 쌍 열거 ────────────────────────────────────────────
def q4(cur):
    say("## Q4 — look-ahead 재검토: 케이엔알시스템 자가보고 −36.9%\n")
    rows = bars(cur, CODES["케이엔알시스템"], "2026-06-01", "2026-08-07")
    say(f"창 2026-06-01~08-07 · {len(rows)}봉 · 등록일 2026-07-28\n")
    hits = []
    for pk in ("close", "high"):
        for tk in ("close", "low"):
            pi = {"close": 4, "high": 2}[pk]
            ti = {"close": 4, "low": 3}[tk]
            for a in range(len(rows)):
                for b in range(a + 1, len(rows)):
                    dd = 1 - rows[b][ti] / rows[a][pi]
                    if 0.364 <= dd <= 0.374:
                        hits.append((pk, tk, rows[a][0], rows[b][0], dd * 100))
    if not hits:
        say("⛔ −36.9%(±0.5%p) 를 만드는 쌍이 **0개**. 자가보고와 우리 데이터 불일치.\n")
        return
    # 각 정의조합의 「가장 이른 고점 → 가장 깊은 저점」 대표쌍만 보인다
    seen = set()
    say("| 고점정의 | 저점정의 | 고점일 | 저점일 | 낙폭 | 고점이 등록일(07-28) 이전인가 |")
    say("|---|---|---|---|---|---|")
    for pk, tk, pd_, td, dd in hits:
        key = (pk, tk, pd_)
        if key in seen:
            continue
        seen.add(key)
        say(f"| {pk} | {tk} | {pd_} | {td} | −{dd:.2f}% | "
            f"{'✅ 이전' if pd_ < '2026-07-28' else '❌ 이후/당일'} |")
    say(f"\n총 적합쌍 {len(hits)}개 · 고유 (정의,고점일) {len(seen)}개")
    peaks = {p for _, _, p, _, _ in hits}
    say(f"서로 다른 고점일 {len(peaks)}개: {sorted(peaks)}")
    before = sum(1 for p in peaks if p < "2026-07-28")
    say(f"→ 등록일 이전 고점 {before} / {len(peaks)}\n")


# ─── Q1: 밴드 경계 부등식 ────────────────────────────────────────────────────
TRADES_Q1 = [
    # (종목, 등록일, 등록일정밀도, 사이클종료일, 라벨)
    ("케이엔알시스템", "2026-07-28", "exact", "2026-08-07", "full"),
    ("모나미", "2026-07-16", "after", "2026-08-07", "full"),
    ("에스피지", "2026-07-31", "approx", "2026-08-14", "first_only"),
    ("솔트룩스", "2026-08-04", "approx", "2026-08-14", "first_only"),
    ("마키나락스", "2026-08-05", "exact", "2026-08-14", "first_only"),
    ("매드업", "2026-08-06", "exact", "2026-08-14", "first_only"),
    ("빛과전자", "2026-08-05", "exact", "2026-08-14", "first_only"),
]


def q1(cur):
    say("## Q1 — 밴드 경계 부등식\n")
    res = {}
    say("| 종목 | 라벨 | 등록일 | 정밀도 | 등록일종가 | 이후최저가 | DD(H1) | DD(H2) | DD(H3) |")
    say("|---|---|---|---|---|---|---|---|---|")
    for name, d, prec, end, lab in TRADES_Q1:
        code = CODES[name]
        pre = bars(cur, code, "2026-05-01", d)          # 등록일 포함 이전
        post = bars(cur, code, d, end)                   # 등록일~종료
        if not pre or not post:
            say(f"| {name} | {lab} | {d} | {prec} | (데이터 없음) | | | | |")
            continue
        c_d = pre[-1][4]
        win = pre[-21:-1] if len(pre) > 21 else pre[:-1]  # 직전 20거래일
        h1 = c_d
        h2 = max(r[4] for r in win) if win else c_d
        h3 = max(r[2] for r in win) if win else c_d
        low = min(r[3] for r in post)
        dd = {k: 1 - low / h for k, h in (("H1", h1), ("H2", h2), ("H3", h3))}
        res[name] = (lab, dd)
        say(f"| {name} | {lab} | {d} | {prec} | {c_d:,.0f} | {low:,.0f} | "
            f"{dd['H1']*100:.2f}% | {dd['H2']*100:.2f}% | {dd['H3']*100:.2f}% |")

    say("\n### 통계량 T = min(DD|full) − max(DD|first_only)\n")
    say("| H 정의 | min(DD‖full) | max(DD‖first_only) | T | 부호 |")
    say("|---|---|---|---|---|")
    signs = []
    for k in ("H1", "H2", "H3"):
        f = [dd[k] for lab, dd in res.values() if lab == "full"]
        o = [dd[k] for lab, dd in res.values() if lab == "first_only"]
        if not f or not o:
            continue
        T = min(f) - max(o)
        signs.append(T > 0)
        say(f"| {k} | {min(f)*100:.2f}% | {max(o)*100:.2f}% | {T*100:+.2f}%p | "
            f"{'✅ T>0' if T > 0 else '❌ T≤0'} |")
    say(f"\n**판정: {'✅ 지지 (3정의 전부 T>0)' if all(signs) and len(signs)==3 else '❌ 기각 (한 정의 이상에서 T≤0)'}**")
    say("⚠️ n = 2 vs 5. 완전분리라도 단측 정확 p = 2/21 ≈ 0.095 — **유의성 주장 불가**(사전등록 명시).\n")

    say("### 구간 추정 — 밴드 깊이 경계\n")
    for k in ("H1", "H2", "H3"):
        f = [dd[k] for lab, dd in res.values() if lab == "full"]
        o = [dd[k] for lab, dd in res.values() if lab == "first_only"]
        if f and o:
            say(f"- `{k}`: 1차 밴드 `b₁ ≤ {min(o)*100:.2f}%` · 2차 밴드 `b₂ > {max(o)*100:.2f}%` "
                f"· 최종차수 `b_last ≤ {min(f)*100:.2f}%`")

    say("\n### 부수검정 — 등록일 이후 저가 < 등록일 종가 (5/5 요구)\n")
    ok = 0
    tot = 0
    for name, d, prec, end, lab in TRADES_Q1:
        if lab != "first_only":
            continue
        tot += 1
        code = CODES[name]
        pre = bars(cur, code, "2026-05-01", d)
        post = bars(cur, code, d, end)
        if not pre or not post:
            continue
        c_d = pre[-1][4]
        low = min(r[3] for r in post)
        good = low < c_d
        ok += good
        say(f"- {name}: 등록일 종가 {c_d:,.0f} vs 이후 최저가 {low:,.0f} → {'✅' if good else '❌'}")
    say(f"\n**{ok}/{tot}** {'✅ 통과' if ok == tot else '❌ 기각'}\n")


# ─── Q2: 「끼」 지표 ─────────────────────────────────────────────────────────
def q2(cur):
    say("## Q2 — 「끼」 지표 정의 역산\n")
    say("### 자가보고 2점 대 D1 = trading_value / market_cap\n")
    say("| 종목 | 저자 진술 | 날짜 | D1 실측 | 상대오차 |")
    say("|---|---|---|---|---|")
    for name, claim, d0, d1 in (("매드업", 0.63, "2026-08-06", "2026-08-06"),
                                ("솔트룩스", 0.67, "2026-07-25", "2026-08-08")):
        rows = bars(cur, CODES[name], d0, d1)
        best = None
        for r in rows:
            if r[6]:
                v = r[5] / r[6]
                if best is None or abs(v - claim) < abs(best[1] - claim):
                    best = (r[0], v)
        if best:
            err = abs(best[1] - claim) / claim * 100
            say(f"| {name} | {claim}배 | {best[0]} | **{best[1]:.4f}** | {err:.1f}% |")
        else:
            say(f"| {name} | {claim}배 | — | (데이터 없음) | — |")

    say("\n### 솔트룩스 D1 시계열 (2026-07-25 ~ 08-08)\n")
    say("| 날짜 | 종가 | 거래대금(억) | 시총(억) | D1 |")
    say("|---|---|---|---|---|")
    for r in bars(cur, CODES["솔트룩스"], "2026-07-25", "2026-08-08"):
        if r[6]:
            say(f"| {r[0]} | {r[4]:,.0f} | {r[5]/1e8:,.0f} | {r[6]/1e8:,.0f} | {r[5]/r[6]:.4f} |")

    say("\n### 부수검정 — 「거래대금 1,000억원 이상」 절대문턱 (2026-07-28)\n")
    for name in ("케이엔알시스템", "씨피시스템"):
        rows = bars(cur, CODES[name], "2026-07-28", "2026-07-28")
        if rows:
            tv = rows[0][5]
            say(f"- {name}: 거래대금 **{tv/1e8:,.0f}억** → {'✅ ≥1,000억' if tv >= 1e11 else '❌ <1,000억'}")
    cur.execute(
        "SELECT COUNT(*) FROM daily_prices WHERE date='2026-07-28' AND trading_value >= 100000000000")
    k = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM daily_prices WHERE date='2026-07-28'")
    n = cur.fetchone()[0]
    say(f"\n🔑 **대조군**: 같은 날 1,000억 이상인 종목 **{k} / {n}** ({k/n*100:.1f}%).")
    say(f"→ {'문턱이 희소하다 = 판별력 있음' if k/n < 0.05 else '문턱이 흔하다 = 판별력 약함'}\n")


# ─── Q3: in-sample 기술 ─────────────────────────────────────────────────────
def q3():
    say("## Q3 — HDR 매도 사다리 (🔴 오염 · in-sample 기술만)\n")
    legs = list(csv.DictReader((BASE / "ledger_legs.csv").open(encoding="utf-8")))
    trades = {(t["post_log_no"], t["item_no"]): t
              for t in csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8"))}

    # P2: 비증가 순서
    bad = []
    by_trade: dict[tuple, list] = {}
    for l in legs:
        by_trade.setdefault((l["post_log_no"], l["item_no"]), []).append(float(l["ret_pct"]))
    for k, v in by_trade.items():
        if any(v[i] < v[i + 1] for i in range(len(v) - 1)):
            bad.append((trades[k]["stock_name"], v))
    say(f"**P2 (레그가 비증가 순서)**: 위반 {len(bad)}건 / {len(by_trade)}건 "
        f"{'✅' if not bad else '❌ ' + str(bad)}\n")

    # P1: 본전매도 건의 마지막 레그
    say("**P1 (본전매도 건의 마지막 레그 |ret| < 1.0%)**\n")
    say("| 종목 | 마지막 레그 | 판정 |")
    say("|---|---|---|")
    ok = tot = 0
    for k, t in trades.items():
        if t["breakeven_exit"] != "1":
            continue
        tot += 1
        last = by_trade[k][-1]
        good = abs(last) < 1.0
        ok += good
        say(f"| {t['stock_name']} ({t['post_date']}) | {last:+.2f}% | {'✅' if good else '❌'} |")
    say(f"\n**{ok}/{tot}**\n")

    # 근접쌍
    say("**근접쌍 (차이 ≤ 0.05%p)**\n")
    for k, v in by_trade.items():
        pairs = [(v[i], v[i + 1]) for i in range(len(v) - 1) if abs(v[i] - v[i + 1]) <= 0.05]
        if pairs:
            say(f"- {trades[k]['stock_name']} ({trades[k]['post_date']}): {pairs}")

    # 본전 군집
    near0 = [float(l["ret_pct"]) for l in legs if abs(float(l["ret_pct"])) < 1.0]
    say(f"\n**|ret| < 1.0% 레그**: {len(near0)} / {len(legs)} → {sorted(near0)}\n")


def main():
    with psycopg2.connect(**DSN) as conn, conn.cursor() as cur:
        say("# 검정 결과 — PREREG.md §3~§6\n")
        q4(cur)
        q1(cur)
        q2(cur)
    q3()
    (BASE / "RESULTS_raw.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_raw.md")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()

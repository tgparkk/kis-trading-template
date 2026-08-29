# -*- coding: utf-8 -*-
"""PREREG_SELECTION.md §7 실행 — S1~S4 를 5번째 글 신규 6건에 적용 (out-of-sample, 2회차).

`run_selection_post4.py` 를 승계한다. 특징 정의·백분위 통계량은 `run_selection.py` 의 것을
**그대로** 재사용한다(§1 특징 9개 · 창 안 일별 백분위의 «최댓값»).

🔴 **창 규칙에서 사전등록 문언과 post4 구현이 어긋난다** — 이 스크립트는 «둘 다» 인쇄한다.
   - `W_FROZEN`  = `PREREG_SELECTION.md` §2 문언 그대로 **[D−4, D] = 거래일 5일** → **판정 근거**
   - `W_POST4`   = `run_selection_post4.py` 구현 그대로 **달력 10일**(거래일 7~8일) → **대조용**
   어느 쪽을 판정에 쓸지는 **값을 보기 전에** 정했다(동결 문언 우선).

🔴 DB 스냅샷이 post4(최신 08-21)와 다르다(최신 **08-28**). post4 6건도 **같은 스냅샷에서 재계산**해
   나란히 인쇄한다. 직전 문서 숫자를 그대로 옮겨 비교하지 않는다.

라이브 트리 import 0건. DB 는 SELECT 만.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import psycopg2

from run_selection import FEATS, PSEUDO, build_features
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

DB_UPTO = "2026-08-28"          # DB 스냅샷 (post4 는 08-21)
W_TDAYS = 5                     # 동결 문언 [D−4, D] = 거래일 5일
W_CAL_POST4 = 10                # post4 구현 (달력 10일)

# 5번째 글 코드 있는 신규 6건 — 등록일은 저자 서술(INTAKE_2026-08-29_post5 §1). 전부 exact.
NEW5 = [
    ("혜인",             "003010", "2026-08-11"),
    ("한국화장품제조",   "003350", "2026-08-12"),
    ("코데즈컴바인",     "047770", "2026-08-21"),   # 재진입 — 4번째 글 08-19 건과 별개 사이클
    ("한켐",             "457370", "2026-08-20"),   # 재시작 — 4번째 글 08-12 건과 별개 사이클
    ("삼양바이오팜",     "0120G0", "2026-08-21"),   # 2026-08-05 신규상장 — 이력 12거래일뿐
    ("광전자",           "017900", "2026-08-05"),
]
# 🔴 레메디 — DB 에 없다(신규주 미편입). daily_prices·stock_info·stock_industry 3곳 전부 0행.
#    ⇒ S1~S4 분모에서 **제외**. 7건 중 6건이 분모다.

# 4번째 글 신규 6건 — 같은 스냅샷에서 재계산해 나란히 본다 (post4 판정을 대체하지 않는다).
NEW4 = [
    ("이노테크",         "469610", "2026-08-13"),
    ("한켐",             "457370", "2026-08-12"),
    ("금호건설",         "002990", "2026-08-12"),
    ("지투파워",         "388050", "2026-08-13"),
    ("PS일렉트로닉스",   "332570", "2026-08-13"),
    ("코데즈컴바인",     "047770", "2026-08-19"),
]

# `RESULTS_SELECTION_POST4_NUMBERS.md` 가 **발표한** 백분위 (달력 10일 창, 08-21 스냅샷).
# 같은 창으로 08-28 스냅샷에서 재계산해 셀 단위로 대조한다(§3-2).
PUB4 = {
    "이노테크":       [99.2, 95.1, 99.7, 84.4, 47.0, 91.8, 61.9, 98.5, 48.0],
    "한켐":           [99.9, 97.2, 99.6, 75.8, 14.9, 91.8, 41.1, 97.8, 48.0],
    "금호건설":       [99.8, 99.6, 96.1, 98.2, 55.8, 100.0, 83.2, 98.9, 48.0],
    "지투파워":       [99.7, 97.3, 100.0, 91.9, 71.6, 84.8, 66.6, 98.9, 48.0],
    "PS일렉트로닉스": [99.6, 99.3, 98.2, 97.3, 60.9, 91.8, 82.5, 98.9, 48.0],
    "코데즈컴바인":   [99.8, 98.1, 99.8, 86.3, 81.9, 85.2, 59.5, 98.6, 47.7],
}


def say(s=""):
    print(s)
    OUT.append(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def load_ext():
    """run_selection.load() 와 동일하되 상단을 08-28 로 넓힌다."""
    conn = psycopg2.connect(**DSN)
    df = pd.read_sql(
        "SELECT stock_code, date, high, low, close, trading_value, market_cap "
        f"FROM daily_prices WHERE date BETWEEN '2026-04-01' AND '{DB_UPTO}' "
        "AND market_cap IS NOT NULL AND market_cap > 0 AND close > 0", conn)
    conn.close()
    df = df[~df.stock_code.isin(PSEUDO)].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["stock_code", "date"]).reset_index(drop=True)


def load_raw_close():
    """S1 용 원시 종가·고가 (market_cap 필터 없이). 등록일 전일 종가가 필요하다."""
    conn = psycopg2.connect(**DSN)
    df = pd.read_sql(
        "SELECT stock_code, date, high, close FROM daily_prices "
        f"WHERE date BETWEEN '2026-01-01' AND '{DB_UPTO}' AND close > 0", conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["stock_code", "date"]).reset_index(drop=True)


def stat_tdays(df, code, d1, n):
    """창 = D 를 포함한 **직전 n 거래일**. 통계량 = 창 안 일별 백분위의 최댓값."""
    m = df[(df.stock_code == code) & (df.date <= d1)].tail(n)
    if m.empty:
        return None, 0
    return {f: m[f + "_pct"].max() for f in FEATS}, len(m)


def stat_cal(df, code, d1, ncal):
    """post4 구현: 창 = [D − ncal 달력일, D]."""
    m = df[(df.stock_code == code) & (df.date >= d1 - pd.Timedelta(days=ncal)) & (df.date <= d1)]
    if m.empty:
        return None, 0
    return {f: m[f + "_pct"].max() for f in FEATS}, len(m)


def raw_max_tdays(df, code, d1, n, col):
    m = df[(df.stock_code == code) & (df.date <= d1)].tail(n)
    return None if m.empty else float(m[col].max())


def med(xs):
    s = sorted(x for x in xs if x is not None and x == x)
    if not s:
        return None
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def s1_row(raw, code, reg):
    """등록일 종가/고가의 전일 종가 대비 등락."""
    m = raw[(raw.stock_code == code) & (raw.date <= pd.Timestamp(reg))].tail(2)
    if len(m) < 2 or m.date.iloc[-1] != pd.Timestamp(reg):
        return None
    pc = float(m.close.iloc[0])
    c = float(m.close.iloc[-1])
    h = float(m.high.iloc[-1])
    return dict(prev_close=pc, close=c, high=h, ret_c=c / pc - 1, ret_h=h / pc - 1)


def feat_table(title, rows):
    say(f"### {title}\n")
    say("| 종목 | 등록일 | 창봉수 | " + " | ".join(f.split("_", 1)[0] for f in FEATS) + " |")
    say("|---" * (len(FEATS) + 3) + "|")
    for nm, _c, reg, st, nb in rows:
        if st is None:
            say(f"| {nm} | {reg} | {nb} | " + " | ".join(["—"] * len(FEATS)) + " |")
            continue
        cells = []
        for f in FEATS:
            v = st[f]
            cells.append("—" if v != v else f"{v:.1f}")
        say(f"| {nm} | {reg} | {nb} | " + " | ".join(cells) + " |")
    say()


def verdicts(tag, rows, prev_s2, prev_s3, prev_s4):
    s2 = med([r[3]["f1_tv_mcap"] for r in rows if r[3]])
    s3 = med([r[3]["f9_newhigh"] for r in rows if r[3]])
    s4 = med([r[3]["f7_mcap"] for r in rows if r[3]])
    say(f"| **S2** | {tag} | ≥ 95 (값만 기록) | **{s2:.1f}** | {prev_s2} | "
        f"{'✅ 충족' if s2 >= 95 else '🟡 미달'} |")
    say(f"| **S3** | {tag} | **< 90** (핵심·위반 시 기각) | **{s3:.1f}** | {prev_s3} | "
        f"{'✅ 지지' if s3 < 90 else '❌ 기각'} |")
    say(f"| **S4** | {tag} | 40~80 (값만 기록) | **{s4:.1f}** | {prev_s4} | "
        f"{'✅ 구간 내' if 40 <= s4 <= 80 else '🟡 구간 밖'} |")
    return s2, s3, s4


def main():
    df = build_features(load_ext())
    raw = load_raw_close()

    say("# RESULTS_SELECTION_POST5_NUMBERS — 기계 생성 (수정 금지)\n")
    say("사전등록 `PREREG_SELECTION.md` §7 (`9e53825`, 8/15 동결) · 생성 `run_selection_post5.py`")
    say(f"유니버스 일자 수 **{df.date.nunique()}** · 종목 수 **{df.stock_code.nunique()}** "
        f"· 최신 **{df.date.max().date()}** (post4 스냅샷은 최신 08-21 — **같은 표가 아니다**)")
    say("통계량 = **창 안 일별 백분위의 최댓값**(그날 유니버스 기준, 0~100)")
    say(f"창 **판정** = 동결 문언 `[D−4, D]` = **거래일 {W_TDAYS}일** · "
        f"창 **대조** = post4 구현 `달력 {W_CAL_POST4}일`\n")

    # ── 0. 표본 구성 ────────────────────────────────────────────────────────
    say("## 0. 표본 — 5번째 글 코드 있는 6건 (레메디 제외)\n")
    say("| 종목 | 코드 | 등록일 | DB 행수 | DB 최초일 |")
    say("|---|---|---|---|---|")
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    for nm, code, reg in NEW5:
        cur.execute("SELECT count(*), min(date) FROM daily_prices WHERE stock_code=%s", (code,))
        n, mn = cur.fetchone()
        say(f"| {nm} | {code} | {reg} | {n} | {mn} |")
    hits = []
    for tbl, col in (("stock_info", "stock_name"), ("stock_industry", "corp_name"),
                     ("stock_industry", "stock_name")):
        cur.execute(f"SELECT count(*) FROM {tbl} WHERE {col} LIKE %s", ("%레메디%",))
        hits.append(f"`{tbl}.{col}` {cur.fetchone()[0]}행")
    say(f"| 레메디 | 🔴 **없음** | 2026-08-18 | " + " · ".join(hits) + " | — |")
    conn.close()
    say("\n🔴 **레메디는 종목코드 자체를 못 찾는다**(`stock_info`·`stock_industry` 이름 검색 0행) "
        "⇒ `daily_prices` 조회 자체가 불가 ⇒ S1~S4 분모에서 **제외**. **분모 = 6건.**\n")

    # ── 1. S1 (동결: 종가 기준) ─────────────────────────────────────────────
    say("## 1. S1 — 등록일 **종가** 전일대비 ≥ +15% (동결 문언)\n")
    say("| 종목 | 등록일 | 전일 종가 | 등록일 종가 | **종가 등락** | 판정 |")
    say("|---|---|---|---|---|---|")
    s1_hits, s1_rows = 0, []
    for nm, code, reg in NEW5:
        r = s1_row(raw, code, reg)
        s1_rows.append((nm, reg, r))
        if r is None:
            say(f"| {nm} | {reg} | — | — | — | (데이터 없음) |")
            continue
        ok = r["ret_c"] >= 0.15
        s1_hits += int(ok)
        say(f"| {nm} | {reg} | {r['prev_close']:,.0f} | {r['close']:,.0f} | "
            f"**{r['ret_c']:+.2%}** | {'✅' if ok else '❌'} |")
    say(f"\n⇒ **S1 = {s1_hits}/6 = {s1_hits/6*100:.1f}%** (문턱: ≥ 절반 = 3/6) ⇒ "
        f"**{'지지' if s1_hits >= 3 else '불성립'}**\n")

    # ── 1b. S1 탐색적 변량 (고가 기준) ──────────────────────────────────────
    say("### 1b. 🔬 **탐색적** — 같은 문턱을 **고가**로 재면 (동결 규칙 아님)\n")
    say("> `INTAKE_2026-08-22_post4.md` §3 이 *「고가 기준이면 6/6」은 탐색적 관측*이라 적었다. "
        "**판정에 쓰지 않는다.**\n")
    say("| 종목 | 등록일 | 전일 종가 | 등록일 고가 | **고가 등락** | (탐색) |")
    say("|---|---|---|---|---|---|")
    h_hits = 0
    for nm, reg, r in s1_rows:
        if r is None:
            say(f"| {nm} | {reg} | — | — | — | — |")
            continue
        ok = r["ret_h"] >= 0.15
        h_hits += int(ok)
        say(f"| {nm} | {reg} | {r['prev_close']:,.0f} | {r['high']:,.0f} | "
            f"**{r['ret_h']:+.2%}** | {'○' if ok else '×'} |")
    say(f"\n⇒ 탐색적 고가 변량 = **{h_hits}/6 = {h_hits/6*100:.1f}%** — "
        "🔬 **탐색적, 사전등록된 규칙이 아니다.**\n")

    # ── 1c. 4번째 글 6건 — 같은 스냅샷에서 S1 재계산 (post4 발표값 대조) ────
    say("### 1c. 4번째 글 6건 — 같은 08-28 스냅샷에서 S1 재계산 (post4 발표 3/6 대조)\n")
    say("| 종목 | 등록일 | 전일 종가 | 등록일 종가 | 종가 등락 | 동결(종가) | 등록일 고가 | 고가 등락 | (탐색) |")
    say("|---|---|---|---|---|---|---|---|---|")
    c4 = h4 = 0
    for nm, code, reg in NEW4:
        r = s1_row(raw, code, reg)
        if r is None:
            say(f"| {nm} | {reg} | — | — | — | — | — | — | — |")
            continue
        okc, okh = r["ret_c"] >= 0.15, r["ret_h"] >= 0.15
        c4 += int(okc)
        h4 += int(okh)
        say(f"| {nm} | {reg} | {r['prev_close']:,.0f} | {r['close']:,.0f} | {r['ret_c']:+.2%} | "
            f"{'✅' if okc else '❌'} | {r['high']:,.0f} | {r['ret_h']:+.2%} | "
            f"{'○' if okh else '×'} |")
    say(f"\n⇒ 4번째 글 재계산: 동결(종가) **{c4}/6 = {c4/6*100:.1f}%** "
        f"(post4 문서 발표값 3/6 = 50.0% — {'✅ 일치' if c4 == 3 else '🔴 다름'}) · "
        f"탐색(고가) **{h4}/6 = {h4/6*100:.1f}%**\n")

    # ── 2. 특징 백분위 ──────────────────────────────────────────────────────
    say("## 2. 특징별 백분위 (창 최대) — 9개 전부\n")
    rows5_t = [(nm, c, reg) + stat_tdays(df, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg in NEW5]
    rows5_c = [(nm, c, reg) + stat_cal(df, c, pd.Timestamp(reg), W_CAL_POST4) for nm, c, reg in NEW5]
    rows4_t = [(nm, c, reg) + stat_tdays(df, c, pd.Timestamp(reg), W_TDAYS) for nm, c, reg in NEW4]
    rows4_c = [(nm, c, reg) + stat_cal(df, c, pd.Timestamp(reg), W_CAL_POST4) for nm, c, reg in NEW4]

    feat_table(f"2-1. 5번째 글 6건 — **판정 창**(거래일 {W_TDAYS}일)", rows5_t)
    feat_table(f"2-2. 5번째 글 6건 — 대조 창(post4 구현·달력 {W_CAL_POST4}일)", rows5_c)
    feat_table(f"2-3. 4번째 글 6건 — 판정 창(거래일 {W_TDAYS}일) · **08-28 스냅샷 재계산**", rows4_t)
    feat_table(f"2-4. 4번째 글 6건 — 대조 창(달력 {W_CAL_POST4}일) · **08-28 스냅샷 재계산**", rows4_c)

    # ── 3. 판정 ─────────────────────────────────────────────────────────────
    say("## 3. 사전등록 §7 판정 (S2·S3·S4)\n")
    say("| 예측 | 창 | 문턱 | 이번(5번째 글 6건) | 직전 인용값 | 판정 |")
    say("|---|---|---|---|---|---|")
    s2t, s3t, s4t = verdicts(f"**판정** 거래일{W_TDAYS}", rows5_t, "99.4 → 99.7", "48.3 → 48.0", "61.6 → 64.2")
    say("| | | | | | |")
    s2c, s3c, s4c = verdicts(f"대조 달력{W_CAL_POST4}", rows5_c, "(post4 구현)", "(post4 구현)", "(post4 구현)")
    say()
    say("### 3-1. 4번째 글 6건 — 같은 08-28 스냅샷에서 재계산 (post4 판정을 대체하지 않는다)\n")
    say("| 예측 | 창 | 문턱 | 4번째 글(재계산) | post4 문서 발표값 | 일치? |")
    say("|---|---|---|---|---|---|")
    for tag, rr, pub in ((f"거래일{W_TDAYS}", rows4_t, ("—", "—", "—")),
                         (f"달력{W_CAL_POST4}", rows4_c, ("99.7", "48.0", "64.2"))):
        a = med([r[3]["f1_tv_mcap"] for r in rr if r[3]])
        b = med([r[3]["f9_newhigh"] for r in rr if r[3]])
        c_ = med([r[3]["f7_mcap"] for r in rr if r[3]])
        say(f"| S2 | {tag} | ≥95 | {a:.1f} | {pub[0]} | "
            f"{'✅' if pub[0] != '—' and abs(a - float(pub[0])) < 0.05 else ('—' if pub[0] == '—' else '🔴 다름')} |")
        say(f"| S3 | {tag} | <90 | {b:.1f} | {pub[1]} | "
            f"{'✅' if pub[1] != '—' and abs(b - float(pub[1])) < 0.05 else ('—' if pub[1] == '—' else '🔴 다름')} |")
        say(f"| S4 | {tag} | 40~80 | {c_:.1f} | {pub[2]} | "
            f"{'✅' if pub[2] != '—' and abs(c_ - float(pub[2])) < 0.05 else ('—' if pub[2] == '—' else '🔴 다름')} |")

    # ── 3-2. post4 발표 백분위와 셀 단위 대조 (같은 달력10 창) ─────────────
    say()
    say("### 3-2. post4 **발표 백분위**와 셀 단위 대조 (같은 달력 10일 창 · 08-21 → 08-28 스냅샷)")
    say()
    moved = []
    for nm, _c, _reg, st, _nb in rows4_c:
        if st is None or nm not in PUB4:
            continue
        for f, pub in zip(FEATS, PUB4[nm]):
            now = st[f]
            if now != now:
                continue
            if abs(now - pub) >= 0.05:
                moved.append((nm, f, pub, now))
    say(f"대조한 셀 **{len(PUB4)*len(FEATS)}개**(6종목 × 특징 9개) · "
        f"**움직인 셀 {len(moved)}개**")
    say()
    if moved:
        say("| 종목 | 특징 | post4 발표 | 08-28 재계산 | 차 |")
        say("|---|---|---|---|---|")
        for nm, f, pub, now in moved:
            say(f"| {nm} | `{f}` | {pub:.1f} | {now:.1f} | {now - pub:+.1f} |")
    else:
        say("움직인 셀 없음.")
    say()
    say("🔴 **「소수점까지 그대로 재현」은 «집계 4개»(S1·S2·S3·S4)에만 참이다** — "
        "개별 백분위는 위 표만큼 움직였다. 집계가 중앙값이라 흡수됐을 뿐이다.")

    # ── 4. f9 원값 ──────────────────────────────────────────────────────────
    say()
    say("## 4. 🔴 `f9_newhigh` 원값 — 이진이라 백분위가 축퇴한다\n")
    say("| 종목 | 창 봉수 | `f9` 원값(창 최대) | 갱신일 | 등록일 당일도 갱신? | `f9` 백분위 | 비고 |")
    say("|---|---|---|---|---|---|---|")
    n_raw1 = 0
    for nm, code, reg, st, nb in rows5_t:
        m = df[(df.stock_code == code) & (df.date <= pd.Timestamp(reg))].tail(W_TDAYS)
        raw_v = m["f9_newhigh"].max() if not m.empty else None
        n_hist = int((df.stock_code == code).sum())
        note = "🔴 이력 20봉 미만 ⇒ `f9` 는 «갱신 없음»이 아니라 **계산 불가**를 0 으로 접은 값" \
            if n_hist < 20 else ""
        raw_s = "—" if (raw_v is None or raw_v != raw_v) else f"{raw_v:.0f}"
        n_raw1 += int(raw_v == 1.0) if (raw_v is not None and raw_v == raw_v) else 0
        days = [str(d.date()) for d, v in zip(m.date, m.f9_newhigh) if v == 1.0]
        onD = "✅" if (len(m) and m.f9_newhigh.iloc[-1] == 1.0) else "—"
        pv = None if st is None else st["f9_newhigh"]
        pct_s = "—" if (pv is None or pv != pv) else f"{pv:.1f}"
        say(f"| {nm} | {nb} | {raw_s} | {'·'.join(days) if days else '—'} | {onD} | "
            f"{pct_s} | {note} |")
    say(f"\n⇒ **`f9` 원값 = 1 인 건 {n_raw1}/6** (4번째 글은 **0/6** 이었다 — `RESULTS_SELECTION_POST4.md` §2)")

    # ── 5. 삼양바이오팜 결측 진단 ───────────────────────────────────────────
    say()
    say("## 5. 🔴 삼양바이오팜 `0120G0` — 이력 부족으로 특징 일부가 «계산 불가»\n")
    m = df[df.stock_code == "0120G0"]
    say(f"`daily_prices` 행수 **{len(m)}** · 최초 **{m.date.min().date()}** · "
        f"등록일 08-21 까지의 봉 수 **{int((m.date <= pd.Timestamp('2026-08-21')).sum())}**\n")
    say("| 특징 | rolling 최소요구 | 08-21 값 | 상태 |")
    say("|---|---|---|---|")
    need = {"f1_tv_mcap": 1, "f2_tv": 1, "f3_tv_surge": 10, "f4_vol20": 10, "f5_pos60": 20,
            "f6_spikes60": 20, "f7_mcap": 1, "f8_ma20dev": 10, "f9_newhigh": 20}
    row = m[m.date == pd.Timestamp("2026-08-21")]
    for f in FEATS:
        v = float(row[f].iloc[0]) if len(row) else float("nan")
        st = "✅" if v == v else "🔴 NaN"
        if f == "f9_newhigh" and v == 0.0:
            st = "🔴 **0 이지만 「계산 불가」다** (`close >= NaN` → False)"
        say(f"| `{f}` | {need[f]}봉 | {'NaN' if v != v else f'{v:.6g}'} | {st} |")
    say()
    say("### 5-2b. `market_cap / close`(내재 주식수) — **봉 수와 「서로 다른 값」 개수는 다른 것이다**")
    say()
    mm = m.assign(sh=(m.market_cap / m.close).round(2))
    blkA = mm[mm.date <= pd.Timestamp("2026-08-18")]
    blkB = mm[mm.date >= pd.Timestamp("2026-08-19")]
    say("| 구간 | **봉 수** | **서로 다른 내재주식수** | 값 |")
    say("|---|---|---|---|")
    say(f"| 2026-08-05 ~ 08-18 | **{len(blkA)}** | **{blkA.sh.nunique()}** | "
        f"{blkA.sh.min():,.2f} ~ {blkA.sh.max():,.2f} (폭 {blkA.sh.max()-blkA.sh.min():,.2f}주 "
        f"= {(blkA.sh.max()-blkA.sh.min())/blkA.sh.mean()*100:.3f}%) |")
    say(f"| 2026-08-19 ~ 08-28 | **{len(blkB)}** | **{blkB.sh.nunique()}** | "
        f"{blkB.sh.iloc[0]:,.2f} 고정 |")
    say(f"| 전체 | **{len(mm)}** | **{mm.sh.nunique()}** | — |")
    say()
    say(f"🔑 **봉 수 {len(blkA)}+{len(blkB)}={len(mm)}** 이고 **서로 다른 값은 {mm.sh.nunique()}개**다 "
        "(앞 구간이 매봉 다른 값 + 뒤 구간 단일값). ⚠️**둘을 섞어 쓰지 말 것.**")
    say(f"⚠️ **2026-08-17 은 휴장**이라 08-14 다음 봉이 08-18 이다 — "
        "달력으로 세면 앞 구간이 10일로 보이지만 **봉은 {}개**다.".format(len(blkA)))
    say()
    say("| 날짜 | 종가 | `market_cap` | 내재 주식수 |")
    say("|---|---|---|---|")
    for _i, r in mm.iterrows():
        say(f"| {r.date.date()} | {r.close:,.0f} | {r.market_cap:,.2f} | {r.sh:,.2f} |")

    (BASE / "RESULTS_SELECTION_POST5_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

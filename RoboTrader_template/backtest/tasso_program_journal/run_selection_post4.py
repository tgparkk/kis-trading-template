# -*- coding: utf-8 -*-
"""PREREG_SELECTION.md §7 실행 — S1~S4 를 4번째 글 신규 6건에 적용 (out-of-sample).

특징 정의·창 규칙·백분위 통계량은 `run_selection.py` 의 것을 **그대로 재사용**한다
(§1 특징 9개 · §2 창 [D−4, D] · 창 안 일별 백분위의 «최댓값»).
바뀐 것은 **날짜 범위뿐**(08-14 → 08-21). 새 자유도 0.

라이브 트리 import 0건. DB 는 SELECT 만.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import psycopg2

from run_selection import FEATS, PSEUDO, build_features, window_stat
from run_tests import DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

# 4번째 글 신규 6건 — 등록일은 저자 서술(LABELS/INTAKE §1). 전부 exact.
NEW = [
    ("이노테크",           "469610", "2026-08-13"),
    ("한켐",               "457370", "2026-08-12"),
    ("금호건설",           "002990", "2026-08-12"),   # 본문 모순: 급등 서술은 08-20
    ("지투파워",           "388050", "2026-08-13"),
    ("PS일렉트로닉스",     "332570", "2026-08-13"),
    ("코데즈컴바인",       "047770", "2026-08-19"),
]
ALT = ("금호건설[대안08-20]", "002990", "2026-08-20")   # 날짜 의존 확인용 (분모 밖)


def say(s=""):
    print(s)
    OUT.append(s)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def load_ext():
    """run_selection.load() 와 동일하되 상단을 08-21 로 넓힌다."""
    conn = psycopg2.connect(**DSN)
    df = pd.read_sql(
        "SELECT stock_code, date, high, low, close, trading_value, market_cap "
        "FROM daily_prices WHERE date BETWEEN '2026-04-01' AND '2026-08-21' "
        "AND market_cap IS NOT NULL AND market_cap > 0 AND close > 0", conn)
    conn.close()
    df = df[~df.stock_code.isin(PSEUDO)].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["stock_code", "date"]).reset_index(drop=True)


def med(xs):
    s = sorted(x for x in xs if x is not None)
    if not s:
        return None
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def main():
    df = build_features(load_ext())
    say("# RESULTS_SELECTION_POST4_NUMBERS — 기계 생성 (수정 금지)\n")
    say("사전등록 `PREREG_SELECTION.md` §7 (`9e53825`, 8/15 동결) · 생성 `run_selection_post4.py`")
    say(f"유니버스 일자 수 **{df.date.nunique()}** · 종목 수 **{df.stock_code.nunique()}** "
        f"· 최신 **{df.date.max().date()}**")
    say("창 = `[등록일−4, 등록일]` · 통계량 = **창 안 일별 백분위의 최댓값**(그날 유니버스 기준, 0~100)\n")

    rows = []
    for nm, code, reg in NEW + [ALT]:
        d1 = pd.Timestamp(reg)
        st = window_stat(df, code, d1 - pd.Timedelta(days=10), d1)  # 달력 10일 ⊃ 거래일 4일
        rows.append((nm, code, reg, st))

    say("## 특징별 백분위 (창 최대) — 9개 전부\n")
    say("| 종목 | 등록일 | " + " | ".join(f.split("_", 1)[0] for f in FEATS) + " |")
    say("|---" * (len(FEATS) + 2) + "|")
    for nm, _c, reg, st in rows:
        if st is None:
            say(f"| {nm} | {reg} | " + " | ".join(["—"] * len(FEATS)) + " |")
            continue
        say(f"| {nm} | {reg} | " + " | ".join(f"{st[f]:.1f}" for f in FEATS) + " |")

    main_rows = [r for r in rows if "대안" not in r[0]]
    say()
    say("## 사전등록 §7 판정\n")

    s2 = med([r[3]["f1_tv_mcap"] for r in main_rows if r[3]])
    s3 = med([r[3]["f9_newhigh"] for r in main_rows if r[3]])
    s4 = med([r[3]["f7_mcap"] for r in main_rows if r[3]])

    say("| 예측 | 문언 | 문턱 | 이번 관측 | 직전 관측 | 판정 |")
    say("|---|---|---|---|---|---|")
    say(f"| **S2** | `거래대금/시총` 백분위 중앙 | ≥ 95 (값만 기록) | **{s2:.1f}** | 99.4 | "
        f"{'✅ 충족' if s2 >= 95 else '🟡 미달'} |")
    say(f"| **S3** | `60일 최고종가 갱신` 백분위 중앙 | **< 90** (핵심·위반 시 기각) | **{s3:.1f}** | 48.3 | "
        f"{'✅ 지지' if s3 < 90 else '❌ 기각'} |")
    say(f"| **S4** | `시가총액` 백분위 중앙 | 40~80 (값만 기록) | **{s4:.1f}** | 61.6 | "
        f"{'✅ 구간 내' if 40 <= s4 <= 80 else '🟡 구간 밖'} |")
    say()
    say("> **S1**(등록일 종가 +15% 과반)은 백분위가 아니라 등락률이라 이 스크립트 밖에서 계산했다 — "
        "`INTAKE_2026-08-22_post4.md` §3 참조: **3/6 = 50.0% 경계선 지지**.")

    say()
    say("### 🔴 `f9_newhigh` 는 이진이라 백분위가 축퇴한다 (직전 문서 W6 에서 지적된 사안)\n")
    say("| 종목 | `f9` 원값(창 최대) | `f9` 백분위 |")
    say("|---|---|---|")
    for nm, code, reg, st in main_rows:
        d1 = pd.Timestamp(reg)
        m = df[(df.stock_code == code) & (df.date >= d1 - pd.Timedelta(days=10)) & (df.date <= d1)]
        raw = m["f9_newhigh"].max() if not m.empty else None
        raw_s = "—" if raw is None else f"{raw:.0f}"
        pct_s = "—" if st is None else f"{st['f9_newhigh']:.1f}"
        say(f"| {nm} | {raw_s} | {pct_s} |")
    say()
    say("🔑 원값이 1 이면 「60일 최고 종가를 갱신했다」는 뜻이다. **백분위보다 원값 비율을 함께 볼 것.**")

    say()
    say("### 날짜 의존 확인 (금호건설)\n")
    a = next(r for r in rows if "대안" in r[0])
    b = next(r for r in rows if r[0] == "금호건설")
    if a[3] and b[3]:
        say("| 특징 | 등록 08-12 | 대안 08-20 | 차 |")
        say("|---|---|---|---|")
        for f in FEATS:
            say(f"| {f} | {b[3][f]:.1f} | {a[3][f]:.1f} | "
                f"{a[3][f] - b[3][f]:+.1f} |")
        s3b = med([r[3]["f9_newhigh"] for r in
                   [x for x in main_rows if x[0] != "금호건설"] + [a] if r[3]])
        say()
        say(f"- 금호건설을 **08-20** 으로 바꾸면 **S3 중앙값 {s3:.1f} → {s3b:.1f}** ⇒ "
            f"판정 **{'불변' if (s3 < 90) == (s3b < 90) else '🔴 뒤집힘'}**")

    (BASE / "RESULTS_SELECTION_POST4_NUMBERS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

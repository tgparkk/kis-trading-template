# -*- coding: utf-8 -*-
"""§2 선정 조건부 검정 — 표본을 33건으로 확장. 사전등록 `PREREG_LEG_STRUCTURE.md`(`43b2e69`).

`run_conditional.py`(n=5, 등록일 특정 건만)의 표본을 넓힌다: **창 안에 후보군 진입일이
하루라도 있는 건**을 양성으로 삼고, 통계량은 **진입일들의 후보군 내 순위 중앙값**.

🔴 사전등록에 미리 적어둔 약점: 창이 최대 15거래일이라 **느슨한 조건**이고 **신호가 희석**될 수
   있다. ⇒ n=5 판과 **둘 다 인쇄**하고, 어긋나면 **어느 쪽도 지지로 쓰지 않는다.**
"""
from __future__ import annotations

import csv
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from run_conditional import (ALL_FEATS, N_NULL, NULL_SEED, SURV, TAU, TWO_SIDED,
                             load_flow)
from run_selection import POST_WINDOW, REG, build_features, holm
from run_selection import load as load_price
from run_tests import CODES

warnings.filterwarnings("ignore")
BASE = Path(__file__).resolve().parent
OUT: list[str] = []


def say(s=""):
    print(s)
    OUT.append(s)


def main() -> int:
    df = build_features(load_price()).merge(
        load_flow().drop(columns=["trading_value"]), on=["stock_code", "date"], how="left")
    d = df[(df.date >= "2026-07-13") & (df.date <= "2026-08-14")].copy()
    mask = np.ones(len(d), dtype=bool)
    for f in SURV:
        mask &= (d[f + "_pct"] >= TAU).fillna(False).values
    cand = d[mask].copy()
    for f in ALL_FEATS:
        cand[f + "_r"] = cand.groupby("date")[f].rank(pct=True) * 100

    say("# §2 선정 조건부 검정 — 표본을 33건으로 확장\n")
    say(f"후보군(5축 AND · τ={TAU}): **{len(cand):,} 종목-일** · "
        f"고유 {cand.stock_code.nunique():,}종목\n")
    say("양성 = **창 안에 후보군 진입일이 하루라도 있는 건** · "
        "통계량 = 진입일들의 후보군 내 순위 **중앙값**\n")

    trades = list(csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")))
    pos, pos_days, names, no_entry = [], [], [], []
    for t in trades:
        code = CODES.get(t["stock_name"])
        if code is None:
            continue
        key = (t["post_log_no"], t["item_no"])
        if key in REG:
            d1 = pd.Timestamp(REG[key])
            d0 = d1 - pd.Timedelta(days=6)
        else:
            a, b = POST_WINDOW[t["post_log_no"]]
            d0, d1 = pd.Timestamp(a), pd.Timestamp(b)
        m = cand[(cand.stock_code == code) & (cand.date >= d0) & (cand.date <= d1)]
        if m.empty:
            no_entry.append(t["stock_name"])
            continue
        pos.append({f: float(np.nanmedian(m[f + "_r"])) for f in ALL_FEATS})
        pos_days.append(sorted(m.date.tolist()))
        names.append(t["stock_name"])

    say(f"양성 **{len(pos)}/{len(trades)}건** · 창 안 후보군 진입 없음 **{len(no_entry)}건**\n")
    say(f"- 진입한 건: {names}\n")
    if len(pos) < 3:
        say("🔴 3건 미만 ⇒ 판정 불가.")
        (BASE / "RESULTS_CONDITIONAL_WIDE.md").write_text("\n".join(OUT), encoding="utf-8")
        return 0

    # 귀무 — 각 양성의 «진입일들»에서 같은 날 후보군 무작위 1건씩, 같은 방식으로 중앙값
    rng = np.random.default_rng(NULL_SEED)
    by_day = {dt: g for dt, g in cand.groupby("date")}
    obs_med = {f: float(np.nanmedian([p[f] for p in pos])) for f in ALL_FEATS}
    null_med = {f: [] for f in ALL_FEATS}
    draw_ct = 0
    for _ in range(N_NULL):
        picks = []
        for days in pos_days:
            vals = []
            for dt in days:
                g = by_day[dt]
                vals.append(g.iloc[rng.integers(len(g))])
                draw_ct += 1
            picks.append({f: float(np.nanmedian([v[f + "_r"] for v in vals]))
                          for f in ALL_FEATS})
        for f in ALL_FEATS:
            v = np.nanmedian([p[f] for p in picks])
            if np.isfinite(v):
                null_med[f].append(float(v))

    say(f"귀무: 각 양성의 «진입일들»에서 같은 날 후보군 무작위 1건씩 · {N_NULL:,}회 · "
        f"시드 {NULL_SEED} · 총 추출 {draw_ct:,}회\n")

    pv = []
    for f in ALL_FEATS:
        arr = np.array(null_med[f])
        hi = float((arr >= obs_med[f]).mean())
        pv.append(2 * min(hi, 1 - hi) if f in TWO_SIDED else hi)
    adj = holm(np.array(pv))

    say("| 특징 | 판정축 | 관측 중앙 순위 | 귀무 중앙 | p | Holm p | 판정 |")
    say("|---|---|---|---|---|---|---|")
    alive = []
    for i, f in enumerate(ALL_FEATS):
        two = f in TWO_SIDED
        thr = (obs_med[f] >= 70) or (two and obs_med[f] <= 30)
        ok = (adj[i] < 0.05) and thr
        if ok:
            alive.append(f)
        say(f"| `{f}` | {'양측' if two else '단측'} | **{obs_med[f]:.1f}** | "
            f"{np.median(null_med[f]):.1f} | {pv[i]:.4f} | {adj[i]:.4f} | "
            f"{'✅ 연관' if ok else '⛔'} |")
    say(f"\n**Holm(family {len(ALL_FEATS)}) 통과: {alive or '없음'}**\n")

    say("## 🔴 n=5 판과의 대조 (사전등록 §2 의 요구)\n")
    say("| 특징 | n=5 (`bf39046`) | n=" + str(len(pos)) + " (이 문서) |")
    say("|---|---|---|")
    N5 = {"f1_tv_mcap": 60.0, "f2_tv": 80.0, "f3_tv_surge": 60.0, "f4_vol20": 60.0,
          "f5_pos60": 33.3, "f6_spikes60": 46.0, "f7_mcap": 63.6, "f8_ma20dev": 83.3,
          "f9_newhigh": 50.0, "f10_frgn": 83.3, "f11_orgn": 40.0, "f12_prsn": 25.0,
          "f13_short": 20.0, "f14_prog": 83.3, "f10r_frgn": 80.0, "f11r_orgn": 60.0,
          "f12r_prsn": 40.0, "f14r_prog": 80.0}
    flips = []
    for f in ALL_FEATS:
        a, b = N5[f], obs_med[f]
        same = (a - 50) * (b - 50) >= 0
        if not same:
            flips.append(f)
        say(f"| `{f}` | {a:.1f} | {b:.1f} {'' if same else '🔴 부호 반전'} |")
    say()
    if flips:
        say(f"🔴 **부호가 뒤집힌 특징 {len(flips)}개: {flips}** ⇒ 사전등록대로 "
            "**어느 쪽도 지지로 쓰지 않는다.**\n")
        say("### 🔴 사전등록 결함 5회째 (자기 신고)\n")
        near = [f for f in flips if abs(N5[f] - 50) < 10 and abs(obs_med[f] - 50) < 10]
        say(f"내 「부호 반전」 규칙은 **50 을 가로지르면** 발동한다. 그런데 뒤집힌 {len(flips)}개 중 "
            f"**{len(near)}개**({near})는 **양쪽 판 모두 50 근처**다 — 신호가 없는 특징이 "
            "잡음으로 넘나든 것이지 방향이 바뀐 게 아니다.")
        say("⇒ 🔑 ***「부호 반전」을 「0 근처를 가로지름」으로 정의하면, 신호 없는 특징이 "
            "무조건 발동해 진짜 신호까지 무효화한다.*** 실제로 방향이 일관되고 «강해진» "
            f"`f10_frgn`({N5['f10_frgn']:.1f}→{obs_med['f10_frgn']:.1f}, raw p "
            f"{pv[ALL_FEATS.index('f10_frgn')]:.4f})과 "
            f"`f13_short`({N5['f13_short']:.1f}→{obs_med['f13_short']:.1f}, raw p "
            f"{pv[ALL_FEATS.index('f13_short')]:.4f})까지 함께 죽는다.")
        say("⚠️ **그래도 규칙은 규칙이다 — 지금 완화하지 않는다.** 다음 사전등록에서 "
            "*「양쪽 판 모두 50±10 밖일 때만 부호 반전으로 센다」*로 고친다.")
    else:
        say("🟢 **두 판의 방향이 일치한다** — 창을 넓혀도 부호가 유지된다.")
    say()
    say("🔴 창이 최대 15거래일이라 **느슨한 조건**이고 신호가 희석된다. "
        "확정 검정은 `PREREG_LEG_STRUCTURE.md` §3 T-C.")

    (BASE / "RESULTS_CONDITIONAL_WIDE.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_CONDITIONAL_WIDE.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

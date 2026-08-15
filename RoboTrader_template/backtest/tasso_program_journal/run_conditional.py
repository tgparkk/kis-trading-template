# -*- coding: utf-8 -*-
"""§1 조건부 선정 — 귀무를 「유니버스」에서 「같은 날 후보군」으로 바꾼다.
사전등록 `PREREG_CONDITIONAL.md`(`eb62f2a`) 실행.

🔑🔑 지금까지 선정 축의 모든 검정은 귀무가 «유니버스 무작위 종목»이었다. 그러면 f1~f14 가
     유의한 건 거의 당연하다 — **후보군에 들었다는 사실 자체가 이미 상위**이기 때문이다.
     진짜 질문은 ***「같은 날 후보군 18종목 중 왜 이 1~2개인가」*** 다.

라이브 트리 import 0건.
"""
from __future__ import annotations

import csv
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

from run_selection import PSEUDO, REG, build_features, holm
from run_selection import load as load_price
from run_tests import CODES, DSN

warnings.filterwarnings("ignore")
BASE = Path(__file__).resolve().parent
OUT: list[str] = []

TAU = 90                       # 🔴 사전등록에 못박은 값. 다른 τ 로 다시 재지 않는다.
SURV = ["f1_tv_mcap", "f2_tv", "f4_vol20", "f6_spikes60", "f8_ma20dev"]
N_NULL = 20000
NULL_SEED = 20260815

BASE_FEATS = ["f1_tv_mcap", "f2_tv", "f3_tv_surge", "f4_vol20", "f5_pos60",
              "f6_spikes60", "f7_mcap", "f8_ma20dev", "f9_newhigh"]
FLOW = ["f10_frgn", "f11_orgn", "f12_prsn", "f13_short", "f14_prog"]
FLOW_R = ["f10r_frgn", "f11r_orgn", "f12r_prsn", "f14r_prog"]
ALL_FEATS = BASE_FEATS + FLOW + FLOW_R
# 🔴 부호를 미리 걸지 않은 특징 = **양측**으로 판정 (사전등록 결함 4회째 수정)
TWO_SIDED = {"f12_prsn", "f12r_prsn", "f13_short", "f5_pos60", "f7_mcap"}


def say(s=""):
    print(s)
    OUT.append(s)


def load_flow() -> pd.DataFrame:
    conn = psycopg2.connect(**DSN)
    q = """
    SELECT d.stock_code, d.date::date AS date, d.trading_value,
           i.frgn_ntby_tr_pbmn AS f10_frgn, i.orgn_ntby_tr_pbmn AS f11_orgn,
           i.prsn_ntby_tr_pbmn AS f12_prsn, s.ssts_vol_rlim AS f13_short,
           p.ntby_tr_pbmn AS f14_prog
    FROM daily_prices d
    LEFT JOIN investor_trend_daily i ON i.stock_code=d.stock_code AND i.date=d.date::date
    LEFT JOIN short_sale_daily     s ON s.stock_code=d.stock_code AND s.date=d.date::date
    LEFT JOIN program_trade_daily  p ON p.stock_code=d.stock_code AND p.date=d.date::date
    WHERE d.date BETWEEN '2026-07-01' AND '2026-08-14' AND d.volume > 0
    """
    df = pd.read_sql(q, conn)
    conn.close()
    df = df[~df.stock_code.isin(PSEUDO)].copy()
    df["date"] = pd.to_datetime(df["date"])
    # 🆕 정규화 수급 — 거래대금(원) → 백만원 단위로 맞춰 나눈다. 규모가 빠지고 방향만 남는다.
    tv_m = df.trading_value / 1e6
    for src, dst in (("f10_frgn", "f10r_frgn"), ("f11_orgn", "f11r_orgn"),
                     ("f12_prsn", "f12r_prsn"), ("f14_prog", "f14r_prog")):
        df[dst] = np.where(tv_m > 0, df[src] / tv_m, np.nan)
    return df


def main() -> int:
    price = build_features(load_price())
    flow = load_flow()
    df = price.merge(flow.drop(columns=["trading_value"]),
                     on=["stock_code", "date"], how="left")

    d = df[(df.date >= "2026-07-13") & (df.date <= "2026-08-14")].copy()
    mask = np.ones(len(d), dtype=bool)
    for f in SURV:
        mask &= (d[f + "_pct"] >= TAU).fillna(False).values
    cand = d[mask].copy()

    say("# §1 조건부 선정 — 귀무를 「같은 날 후보군」으로\n")
    say("🔑 지금까지의 귀무는 «유니버스 무작위»였다. 그러면 **후보군에 들었다는 사실만으로** "
        "유의가 나온다. 진짜 질문은 *「같은 날 후보군 중 왜 이 종목인가」*다.\n")
    say(f"후보군(5축 AND · τ={TAU}): **{len(cand):,} 종목-일** · 고유 "
        f"{cand.stock_code.nunique():,}종목 · 일별 중앙 **{cand.groupby('date').size().median():.0f}**\n")

    # 후보군 «안에서의» 백분위 순위
    for f in ALL_FEATS:
        cand[f + "_r"] = cand.groupby("date")[f].rank(pct=True) * 100

    trades = list(csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")))
    pos_rows, pos_days, names = [], [], []
    for (ln, it), reg in REG.items():
        nm = next(t["stock_name"] for t in trades
                  if t["post_log_no"] == ln and t["item_no"] == it)
        code, day = CODES[nm], pd.Timestamp(reg)
        r = cand[(cand.stock_code == code) & (cand.date == day)]
        if r.empty:
            continue
        pos_rows.append(r.iloc[0])
        pos_days.append(day)
        names.append(nm)
    say(f"양성(후보군 ∩ 원장 등록일): **{len(pos_rows)}/7** — {names}\n")
    if len(pos_rows) < 3:
        say("🔴 표본 3건 미만 ⇒ 판정 불가.")
        (BASE / "RESULTS_CONDITIONAL.md").write_text("\n".join(OUT), encoding="utf-8")
        return 0

    # 귀무 — 같은 날 후보군에서 무작위 1건씩
    rng = np.random.default_rng(NULL_SEED)
    by_day = {dt: g for dt, g in cand.groupby("date")}
    pool_sizes = [len(by_day[dt]) for dt in pos_days]
    obs_med = {f: float(np.nanmedian([r[f + "_r"] for r in pos_rows])) for f in ALL_FEATS}
    null_med = {f: [] for f in ALL_FEATS}
    drawn = set()
    for _ in range(N_NULL):
        pick = []
        for dt in pos_days:
            g = by_day[dt]
            i = rng.integers(len(g))
            drawn.add((dt, i))
            pick.append(g.iloc[i])
        for f in ALL_FEATS:
            v = np.nanmedian([p[f + "_r"] for p in pick])
            if np.isfinite(v):
                null_med[f].append(float(v))

    say(f"귀무: 같은 날 후보군에서 무작위 1건씩 · {N_NULL:,}회 · 시드 {NULL_SEED}")
    say(f"후보군 크기(양성 5일): {pool_sizes} · 귀무가 실제로 뽑은 (날짜,인덱스) 조합 "
        f"**{len(drawn)}** (절단형 귀무 재발 감지)\n")

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

    # 정규화 진단 — 개인이 외국인과 «같은 부호»로 상위면 지표가 아직 방향을 못 잰다
    say("## 🔑 정규화 진단 — 방향인가 규모인가\n")
    say(f"- 정규화 «전»: 외국인 {obs_med['f10_frgn']:.1f} · 개인 {obs_med['f12_prsn']:.1f}")
    say(f"- 정규화 «후»: 외국인 {obs_med['f10r_frgn']:.1f} · 개인 {obs_med['f12r_prsn']:.1f}")
    same_side = (obs_med["f10r_frgn"] - 50) * (obs_med["f12r_prsn"] - 50) > 0
    if same_side:
        say("\n🔴 **정규화 후에도 개인과 외국인이 같은 방향이다** ⇒ 지표가 아직 «방향»을 "
            "못 재고 있다. 사전등록대로 **수급 축 전체를 접는다.**")
    else:
        say("\n🟢 **정규화가 부호를 갈랐다** — 개인과 외국인이 반대 방향이다. "
            "이제 이 지표는 «방향»을 재고 있다.")
    say()
    say("🔴 **n=5 다.** 「유의하지 않음」이 「축이 아님」이 아니다.")
    say("🔴 **후보군은 우리 필터의 산물**이지 저자의 후보군이 아니다. 확정 검정은 §3 Q1.")

    (BASE / "RESULTS_CONDITIONAL.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_CONDITIONAL.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

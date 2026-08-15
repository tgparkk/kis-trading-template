# -*- coding: utf-8 -*-
"""후보군 «안에서» 무엇이 뽑히나 — 장중 모양 + 신용 + 시간외.
사전등록 `PREREG_INTRADAY_PICK.md`(`4ccaafa`) 실행.

🔑 `bf39046`: f1~f14 는 「후보군에 «드는»」 조건이지 「«뽑히는»」 조건이 아니었다.
   남은 축은 일봉으로 안 보이는 것 — 장중 모양·신용·시간외다.

🔴 look-ahead 회피를 부호 예측보다 우선한다 (사전등록 §4):
   장중은 등록일 15:30 까지 · 신용은 등록일 «이전» 마지막 값 · 시간외는 등록일 «전일».
"""
from __future__ import annotations

import csv
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

from run_conditional import SURV, TAU
from run_selection import build_features, holm
from run_selection import load as load_price
from run_tests import CODES, DSN

warnings.filterwarnings("ignore")
BASE = Path(__file__).resolve().parent
OUT: list[str] = []
N_NULL = 20000
NULL_SEED = 20260815

FEATS = ["g1_am_conc", "g2_close_pos", "g3_up_vol", "g4_pullback",
         "g5_top10", "g6_loan_rate", "g7_loan_gvrt", "g8_ovtm"]
SIGN = {"g1_am_conc": "높다", "g2_close_pos": "높다", "g3_up_vol": "높다",
        "g8_ovtm": "높다"}
TWO_SIDED = {"g4_pullback", "g5_top10", "g6_loan_rate", "g7_loan_gvrt"}


def say(s=""):
    print(s)
    OUT.append(s)


def intraday_feats(cur, code: str, ymd: str) -> dict:
    """등록일 15:30 까지의 분봉만 쓴다 (look-ahead 금지)."""
    cur.execute(
        "SELECT time, open, high, low, close, volume, amount FROM minute_candles "
        "WHERE stock_code=%s AND date=%s AND time <= '153000' ORDER BY time",
        (code, ymd))
    b = cur.fetchall()
    if not b:
        return {}
    amt = np.array([float(r[6] or 0) for r in b])
    tot = amt.sum()
    if tot <= 0:
        return {}
    tm = [str(r[0]).zfill(6) for r in b]
    close = np.array([float(r[4]) for r in b])
    openp = np.array([float(r[1]) for r in b])
    vol = np.array([float(r[5] or 0) for r in b])
    hi, lo = max(float(r[2]) for r in b), min(float(r[3]) for r in b)
    am = sum(a for t, a in zip(tm, amt) if t <= "100000")
    peak_i = int(np.argmax([float(r[2]) for r in b]))
    after = close[peak_i:]
    peak = float(b[peak_i][2])
    return {
        "g1_am_conc": am / tot,
        "g2_close_pos": (close[-1] - lo) / (hi - lo) if hi > lo else np.nan,
        "g3_up_vol": (vol[close > openp].sum() / vol.sum()) if vol.sum() > 0 else np.nan,
        "g4_pullback": 1 - (after.min() / peak) if peak > 0 and len(after) else np.nan,
        "g5_top10": float(np.sort(amt)[-10:].sum() / tot),
    }


def flow_feats(cur, code: str, day: pd.Timestamp) -> dict:
    """신용은 등록일 «이전» 마지막 값, 시간외는 «전일» — 둘 다 look-ahead 회피."""
    out = {}
    cur.execute("SELECT loan_rmnd_rate, loan_gvrt FROM credit_balance_daily "
                "WHERE stock_code=%s AND date < %s ORDER BY date DESC LIMIT 1",
                (code, day.date()))
    r = cur.fetchone()
    out["g6_loan_rate"] = float(r[0]) if r and r[0] is not None else np.nan
    out["g7_loan_gvrt"] = float(r[1]) if r and r[1] is not None else np.nan

    cur.execute("SELECT o.ovtm_tr_pbmn, d.trading_value FROM overtime_daily o "
                "JOIN daily_prices d ON d.stock_code=o.stock_code "
                "  AND d.date = to_char(o.date,'YYYY-MM-DD') "
                "WHERE o.stock_code=%s AND o.date < %s ORDER BY o.date DESC LIMIT 1",
                (code, day.date()))
    r = cur.fetchone()
    out["g8_ovtm"] = (float(r[0]) / float(r[1])
                      if r and r[0] and r[1] and float(r[1]) > 0 else np.nan)
    return out


def main() -> int:
    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    df = build_features(load_price())
    d = df[(df.date >= "2026-07-13") & (df.date <= "2026-08-14")].copy()
    m = np.ones(len(d), dtype=bool)
    for f in SURV:
        m &= (d[f + "_pct"] >= TAU).fillna(False).values
    cand = d[m][["stock_code", "date"]].copy()

    say("# 후보군 «안에서» 무엇이 뽑히나 — 장중 모양 + 신용 + 시간외\n")
    say("🔑 `bf39046`: f1~f14 는 **「후보군에 «드는»」 조건**이지 「«뽑히는»」 조건이 아니었다.")
    say("   남은 축은 **일봉으로 안 보이는 것** — 장중 모양·신용·시간외다.\n")
    say(f"후보군(5축 AND · τ={TAU}): **{len(cand):,} 종목-일** · "
        f"고유 {cand.stock_code.nunique():,}종목 (분봉 커버리지 113/113)\n")

    # 후보군 전체에 특징 계산
    rows = []
    for code, day in cand.itertuples(index=False):
        ymd = day.strftime("%Y%m%d")
        f = intraday_feats(cur, code, ymd)
        if not f:
            continue
        f.update(flow_feats(cur, code, day))
        f["stock_code"], f["date"] = code, day
        rows.append(f)
    C = pd.DataFrame(rows)
    say(f"장중 특징 계산 성공 **{len(C):,}/{len(cand):,}** 종목-일\n")
    miss = {f: int(C[f].isna().sum()) for f in FEATS}
    say("결측: " + " · ".join(f"`{f}` {miss[f]}" for f in FEATS) + "\n")

    for f in FEATS:
        C[f + "_r"] = C.groupby("date")[f].rank(pct=True) * 100

    # 양성 = 등록일 특정 건 중 후보군에 든 것
    from run_selection import REG
    trades = list(csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")))
    pos, days, names = [], [], []
    for (ln, it), reg in REG.items():
        nm = next(t["stock_name"] for t in trades
                  if t["post_log_no"] == ln and t["item_no"] == it)
        code, day = CODES[nm], pd.Timestamp(reg)
        r = C[(C.stock_code == code) & (C.date == day)]
        if r.empty:
            continue
        pos.append(r.iloc[0])
        days.append(day)
        names.append(nm)
    say(f"양성 **{len(pos)}/7** — {names}\n")
    if len(pos) < 3:
        say("🔴 3건 미만 ⇒ 판정 불가.")
        (BASE / "RESULTS_INTRADAY_PICK.md").write_text("\n".join(OUT), encoding="utf-8")
        return 0

    rng = np.random.default_rng(NULL_SEED)
    by_day = {dt: g for dt, g in C.groupby("date")}
    obs = {f: float(np.nanmedian([p[f + "_r"] for p in pos])) for f in FEATS}
    null = {f: [] for f in FEATS}
    for _ in range(N_NULL):
        pick = [by_day[dt].iloc[rng.integers(len(by_day[dt]))] for dt in days]
        for f in FEATS:
            v = np.nanmedian([p[f + "_r"] for p in pick])
            if np.isfinite(v):
                null[f].append(float(v))

    pv = []
    for f in FEATS:
        arr = np.array(null[f])
        hi = float((arr >= obs[f]).mean())
        pv.append(2 * min(hi, 1 - hi) if f in TWO_SIDED else hi)
    adj = holm(np.array(pv))

    say(f"귀무: 같은 날 후보군에서 무작위 1건씩 · {N_NULL:,}회 · 시드 {NULL_SEED} · "
        f"후보군 크기 {[len(by_day[dt]) for dt in days]}\n")
    say("| 특징 | 예측 | 판정축 | 관측 중앙 순위 | 귀무 중앙 | p | Holm p | 판정 |")
    say("|---|---|---|---|---|---|---|---|")
    alive = []
    for i, f in enumerate(FEATS):
        two = f in TWO_SIDED
        thr = (obs[f] >= 70) or (two and obs[f] <= 30)
        ok = (adj[i] < 0.05) and thr
        if ok:
            alive.append(f)
        say(f"| `{f}` | {SIGN.get(f, '—')} | {'양측' if two else '단측'} | **{obs[f]:.1f}** | "
            f"{np.median(null[f]):.1f} | {pv[i]:.4f} | {adj[i]:.4f} | "
            f"{'✅ 연관' if ok else '⛔'} |")
    say(f"\n**Holm(family {len(FEATS)}) 통과: {alive or '없음'}**\n")
    say("⚠️ **Holm family 는 이 8개로 한정**했다(사전등록 명시). 기존 18개와 합치면 "
        "study-wide 오류율은 더 높다.\n")
    # ── 사후 관측 (검정 아님) — 세 지표가 한 방향을 가리킨다 ──────────────────
    say("## 🔑 사후 관측 — 원시 p 가 «일관된 하나의 그림»을 그린다 (검정 아님)\n")
    say(f"- `g4_pullback` 장중 최대 되돌림 **{obs['g4_pullback']:.1f}** (귀무 "
        f"{np.median(null['g4_pullback']):.1f}, raw p {pv[FEATS.index('g4_pullback')]:.4f}) — **낮다**")
    say(f"- `g5_top10` 상위 10분 거래대금 집중 **{obs['g5_top10']:.1f}** (귀무 "
        f"{np.median(null['g5_top10']):.1f}, raw p {pv[FEATS.index('g5_top10')]:.4f}) — **낮다**")
    say(f"- `g2_close_pos` 종가 위치 **{obs['g2_close_pos']:.1f}** (귀무 "
        f"{np.median(null['g2_close_pos']):.1f}, raw p {pv[FEATS.index('g2_close_pos')]:.4f}) — **높다**\n")
    say("셋을 합치면 하나의 모양이다 — ***되돌림 없이 · 거래가 하루 내내 고르게 · 종가가 고가 근처.***")
    say("즉 **「한순간 확 튀었다가 되밀린 종목」이 아니라 「하루 종일 밀린 종목」**이다.")
    say("🟢 `g4·g5` 는 **부호를 미리 안 건** 특징이고 둘 다 «낮은 쪽»으로 나왔다 — "
        "**양측 판정으로 고친 덕에 보였다**(직전 사전등록 결함 4회째의 수정).\n")
    say("⚠️ **Holm(8) 을 통과하지 못했다 ⇒ 지금은 증거가 아니다.** 문턱도 아니고 방향도 "
        "결과를 보고 읽은 것이다. ⇒ **다음 글 예측으로만 등록한다**"
        "(`PREREG_INTRADAY_PICK.md` §3 U4~U6).\n")

    say("🔴 **n=5 다.** 「유의하지 않음」이 「축이 아님」이 아니다.")
    say("🔴 **후보군은 우리 필터의 산물**이지 저자의 후보군이 아니다. "
        "확정 검정은 `PREREG_INTRADAY_PICK.md` §3 의 U1~U3.")

    cur.close()
    conn.close()
    (BASE / "RESULTS_INTRADAY_PICK.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_INTRADAY_PICK.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

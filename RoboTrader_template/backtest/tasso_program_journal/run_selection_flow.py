# -*- coding: utf-8 -*-
"""§C 후보 선정 — 수급 5축(f10~f14). 사전등록 `PREREG_MINUTE_FLOW.md`(`766e7b0`).

기존 f1~f9 는 전부 가격·거래대금·변동성이라 **수급 축이 통째로 없었다.**
창·귀무·Holm·승패게이트는 `run_selection.py`(=`PREREG_SELECTION.md` §2~§4) **그대로 재사용**한다.

⚠️ **수급은 저자가 본문에서 언급한 적 없다.** 유의해도 *「저자가 수급을 본다」*가 아니라
   *「올라온 매매가 수급 상위였다」*는 뜻이다.

§0 규약: `daily_prices.volume = 0`(거래정지)인 날은 특징에서 **제외**한다.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

from run_selection import NREP, POST_WINDOW, PSEUDO, REG, RNG, holm
from run_tests import CODES, DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

# (특징, 예측 부호) — 사전등록 §C 표 그대로. None = 부호를 미리 걸지 않음(대조축).
FEATS = ["f10_frgn", "f11_orgn", "f12_prsn", "f13_short", "f14_prog"]
SIGN = {"f10_frgn": "높다", "f11_orgn": "높다", "f12_prsn": "—",
        "f13_short": "—", "f14_prog": "높다"}


def say(s=""):
    print(s)
    OUT.append(s)


def load() -> pd.DataFrame:
    conn = psycopg2.connect(**DSN)
    # 🔑 daily_prices 를 뼈대로 삼고 수급 3축을 붙인다. volume=0(거래정지)은 §0 규약대로 제외.
    #    daily_prices.date 는 text 'YYYY-MM-DD' → ::date 로 맞춘다.
    q = """
    SELECT d.stock_code, d.date::date AS date,
           i.frgn_ntby_tr_pbmn AS f10_frgn,
           i.orgn_ntby_tr_pbmn AS f11_orgn,
           i.prsn_ntby_tr_pbmn AS f12_prsn,
           s.ssts_vol_rlim     AS f13_short,
           p.ntby_tr_pbmn      AS f14_prog
    FROM daily_prices d
    LEFT JOIN investor_trend_daily i ON i.stock_code=d.stock_code AND i.date=d.date::date
    LEFT JOIN short_sale_daily     s ON s.stock_code=d.stock_code AND s.date=d.date::date
    LEFT JOIN program_trade_daily  p ON p.stock_code=d.stock_code AND p.date=d.date::date
    WHERE d.date BETWEEN '2026-07-01' AND '2026-08-14'
      AND d.volume > 0
    """
    df = pd.read_sql(q, conn)
    conn.close()
    df = df[~df.stock_code.isin(PSEUDO)].copy()
    df["date"] = pd.to_datetime(df["date"])
    # 일자별 백분위 (그날 유니버스 기준, 0~100). 결측은 백분위도 결측이다 —
    # 🔑 「모른다」를 「중간값」으로 채우면 그 종목이 조용히 통과한다.
    for f in FEATS:
        df[f + "_pct"] = df.groupby("date")[f].rank(pct=True) * 100
    return df.sort_values(["stock_code", "date"]).reset_index(drop=True)


def window_stat(df, code, d0, d1):
    m = df[(df.stock_code == code) & (df.date >= d0) & (df.date <= d1)]
    if m.empty:
        return None
    return {f: m[f + "_pct"].max() for f in FEATS}


def main() -> int:
    df = load()
    say("# §C 후보 선정 — 수급 5축 (f10~f14)\n")
    say(f"유니버스 {df.stock_code.nunique():,}종목 · {df.date.nunique()}거래일 "
        f"({df.date.min().date()}~{df.date.max().date()}) · 거래정지일(volume=0) 제외\n")
    cov = {f: float(df[f].notna().mean() * 100) for f in FEATS}
    say("수급 컬럼 커버리지: " + " · ".join(f"`{f}` {cov[f]:.1f}%" for f in FEATS) + "\n")

    trades = list(csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")))
    obs, windows, losses, skipped = [], [], [], []
    for t in trades:
        key = (t["post_log_no"], t["item_no"])
        code = CODES.get(t["stock_name"])
        if code is None:
            skipped.append(t["stock_name"])
            continue
        if key in REG:
            d1 = pd.Timestamp(REG[key])
            d0 = d1 - pd.Timedelta(days=6)
        else:
            a, b = POST_WINDOW[t["post_log_no"]]
            d0, d1 = pd.Timestamp(a), pd.Timestamp(b)
        s = window_stat(df, code, d0, d1)
        if s is None:
            skipped.append(t["stock_name"] + "(창내 데이터 없음)")
            continue
        obs.append(s)
        windows.append((d0, d1))
        losses.append(t["all_loss"] == "1")
    say(f"양성 표본 **{len(obs)}건** / 원장 {len(trades)}건 · 제외 {skipped}\n")

    # ── 귀무: 창 길이 보존 무작위 종목 (run_selection 과 동일) ──────────────
    codes = df.stock_code.unique()
    obs_med = {f: float(np.nanmedian([o[f] for o in obs])) for f in FEATS}
    obs_nan = {f: int(np.sum(~np.isfinite([o[f] for o in obs]))) for f in FEATS}
    null_med = {f: [] for f in FEATS}
    by_code = {c: g for c, g in df.groupby("stock_code")}
    drawn = set()
    for _ in range(NREP):
        draw = {f: [] for f in FEATS}
        for d0, d1 in windows:
            for _try in range(20):
                c = codes[RNG.integers(len(codes))]
                drawn.add(c)
                m = by_code[c]
                m = m[(m.date >= d0) & (m.date <= d1)]
                if not m.empty:
                    for f in FEATS:
                        draw[f].append(m[f + "_pct"].max())
                    break
        for f in FEATS:
            v = np.nanmedian(draw[f]) if draw[f] else np.nan
            if np.isfinite(v):
                null_med[f].append(float(v))

    pv = [float((np.array(null_med[f]) >= obs_med[f]).mean()) for f in FEATS]
    adj = holm(np.array(pv))

    say(f"## 결과 — 관측 중앙 백분위 대 귀무 (창 길이 보존 · {NREP:,}회)\n")
    say(f"귀무가 실제로 뽑은 서로 다른 종목: **{len(drawn):,}/{len(codes):,}** "
        "(절단형 귀무 재발 감지)\n")
    say("| 특징 | 예측 | 관측 중앙 | 귀무 중앙 | 결측 | p | Holm p | 판정 |")
    say("|---|---|---|---|---|---|---|---|")
    verdict = {}
    for i, f in enumerate(FEATS):
        ok = (adj[i] < 0.05) and (obs_med[f] >= 90)
        verdict[f] = ok
        say(f"| `{f}` | {SIGN[f]} | **{obs_med[f]:.1f}** | {np.median(null_med[f]):.1f} | "
            f"{obs_nan[f]}/{len(obs)} | {pv[i]:.4f} | {adj[i]:.4f} | "
            f"{'✅ 연관' if ok else '⛔ 판별력 없음'} |")
    alive = [f for f in FEATS if verdict[f]]
    say(f"\n**Holm 보정 후 살아남은 수급 특징: {alive or '없음'}**\n")
    say("⚠️ **Holm family 는 이 5개로 한정**했다(사전등록 명시). 기존 f1~f9 와 합치면 "
        "study-wide 오류율은 더 높다.\n")

    # ── 승/패 대조 게이트 ───────────────────────────────────────────────────
    say("## 승/패 대조 — 결과 조건화 배제 게이트\n")
    from scipy.stats import mannwhitneyu
    lo = [o for o, L in zip(obs, losses) if L]
    wi = [o for o, L in zip(obs, losses) if not L]
    say(f"전패 건 **{len(lo)}** · 나머지 **{len(wi)}**\n")
    say("| 특징 | 전패 중앙 | 나머지 중앙 | p (양측) |")
    say("|---|---|---|---|")
    gate = True
    for f in FEATS:
        a = [o[f] for o in lo if np.isfinite(o[f])]
        b = [o[f] for o in wi if np.isfinite(o[f])]
        if len(a) < 2 or len(b) < 2:
            say(f"| `{f}` | — | — | 표본 부족 |")
            continue
        p = float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
        gate &= p >= 0.05
        say(f"| `{f}` | {np.median(a):.1f} | {np.median(b):.1f} | {p:.4f} |")
    say()
    say("🟡 **게이트 통과**" if gate else "🔴 **게이트 실패 — 「선정 규칙」으로 인용 금지**")
    say("⚠️ 전패 건이 적어 **검정력이 매우 낮다. 「차이 없음」이 「같음」이 아니다.**\n")

    # ── 해석 경고 ────────────────────────────────────────────────────────────
    say("## 🔴 대조축이 잡은 것 — 「수급 방향」이 아니라 「수급 규모」일 수 있다\n")
    say(f"`f12_prsn`(개인)은 **부호를 미리 걸지 않은 대조축**인데 관측 **{obs_med['f12_prsn']:.1f}** 로 "
        f"외국인({obs_med['f10_frgn']:.1f})·프로그램({obs_med['f14_prog']:.1f})과 **같이 높다.**\n")
    say("개인과 외국인은 대체로 거울상인데 **둘 다 상위 백분위**라는 건, 이 특징들이 수급의 "
        "**«방향»이 아니라 «절대 규모»**를 재고 있다는 뜻이다 — 유니버스 대부분이 0 근처라 "
        "거래대금이 큰 종목은 어느 주체든 순매수 «금액»의 절댓값이 크게 나온다.")
    say("🔑 ***그리고 「절대 규모」는 이미 `f2_tv`(거래대금)로 잡힌 축이다.*** "
        "즉 살아남은 3개는 **거래대금의 그림자일 공산이 크다.**\n")
    say("🟢 **대조축을 안 넣었으면 「외국인·프로그램 수급이 선정 축」이라고 적었을 것이다.** "
        "부호를 미리 안 건 특징 하나가 세 개의 해석을 뒤집었다.\n")
    say("⇒ 이를 가르려면 **거래대금으로 정규화한 순매수 비율**을 봐야 하는데, 그건 "
        "**새 사전등록 대상**이다(결과를 보고 만든 지표를 지금 재면 사후적합).\n")

    say("## 🔴 사전등록 결함 1건 (자기 신고)\n")
    say(f"`f13_short`(공매도 비중)는 *「부호를 미리 걸지 않는다」*고 적어놓고, 결정규칙은 "
        f"**관측 ≥ 90** 이라는 **한쪽 꼬리**만 본다. 관측 {obs_med['f13_short']:.1f} 대 "
        f"귀무 {np.median(null_med['f13_short']):.1f} 로 **낮은 쪽**인데 내 규칙으로는 "
        "그걸 잴 수 없다.")
    say("⚠️ **기각은 기각으로 둔다.** 양측 규칙으로 바꿔 다시 재는 것은 사후 완화다. "
        "다음 사전등록에서 고친다 — **사전등록 결함 4회째**.\n")
    say("🔴 **in-sample 탐색이다.** 확정 검정은 `PREREG_MINUTE_FLOW.md` §D 의 P3 "
        "(Holm 통과가 없으면 **P3 는 적용하지 않는다** — 사후에 만들지 않는다).")

    (BASE / "RESULTS_SELECTION_FLOW.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_SELECTION_FLOW.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

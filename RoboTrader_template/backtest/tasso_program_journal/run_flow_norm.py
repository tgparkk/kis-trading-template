# -*- coding: utf-8 -*-
"""`PREREG_FLOW_NORM.md`(`44587e8`) 실행 — 수급 축이 「방향」인가 「거래대금의 그림자」인가.

2×2 요인: {금액, 비율} × {창 최댓값, 창 중앙값}. 셀 A(금액×최댓값)는 `fa2b5d8` 의 재현 확인이다.

🔴 **셀 A 재현을 위해 귀무 추출 경로를 `run_selection_flow.py` 와 «비트 단위로» 같게 유지한다** —
   같은 `codes` 배열 · 같은 창 목록 · 같은 재시도(20회) · 같은 시드. 행을 거르지 않고 «열만» 더한다.
   (`trading_value` 를 WHERE 에 넣으면 `codes` 가 바뀌어 추출 순서가 달라진다.)

라이브 트리 import 0건 (psycopg2 / pandas / numpy / scipy + 표준 라이브러리). DB 는 SELECT 만.
"""
from __future__ import annotations

import csv
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from scipy.stats import spearmanr

from run_selection import NREP, POST_WINDOW, PSEUDO, REG, holm
from run_tests import CODES, DSN

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

SEED = 20260815          # §4 — 셀 간 대응 비교를 위해 «일부러» 같은 시드
EFF = 10.0               # §4 효과크기 문턱 (백분위점)
MATCH_BAND = (5.0, 10.0)  # §6 매칭 밴드 (1회만 넓힌다)
MATCH_MIN = 20           # §6 최소 후보 종목 수

AMT = ["f10_frgn", "f11_orgn", "f12_prsn", "f14_prog"]
RAT = ["r10_frgn", "r11_orgn", "r12_prsn", "r14_prog"]
# §1-① 단위 보정 — investor 는 백만원, program·trading_value 는 원
UNIT = {"r10_frgn": 1e6, "r11_orgn": 1e6, "r12_prsn": 1e6, "r14_prog": 1.0}
SRC = {"r10_frgn": "f10_frgn", "r11_orgn": "f11_orgn",
       "r12_prsn": "f12_prsn", "r14_prog": "f14_prog"}
ALL = AMT + RAT + ["f2_tv"]
COL = {f: i for i, f in enumerate(ALL)}

# `fa2b5d8`(RESULTS_SELECTION_FLOW.md) 의 셀 A 값 — 재현 대조 기준선
CELL_A_REF = {"f10_frgn": (94.6, 84.2), "f11_orgn": (86.9, 80.8),
              "f12_prsn": (96.5, 86.0), "f14_prog": (94.7, 84.2)}


def say(s=""):
    print(s)
    OUT.append(s)


def load() -> pd.DataFrame:
    """`run_selection_flow.load()` 와 «같은 행 집합» + `trading_value` 열 추가."""
    conn = psycopg2.connect(**DSN)
    q = """
    SELECT d.stock_code, d.date::date AS date,
           d.trading_value,
           i.frgn_ntby_tr_pbmn AS f10_frgn,
           i.orgn_ntby_tr_pbmn AS f11_orgn,
           i.prsn_ntby_tr_pbmn AS f12_prsn,
           p.ntby_tr_pbmn      AS f14_prog
    FROM daily_prices d
    LEFT JOIN investor_trend_daily i ON i.stock_code=d.stock_code AND i.date=d.date::date
    LEFT JOIN program_trade_daily  p ON p.stock_code=d.stock_code AND p.date=d.date::date
    WHERE d.date BETWEEN '2026-07-01' AND '2026-08-14'
      AND d.volume > 0
    """
    df = pd.read_sql(q, conn)
    conn.close()
    df = df[~df.stock_code.isin(PSEUDO)].copy()
    df["date"] = pd.to_datetime(df["date"])
    # numeric 컬럼이 Decimal(object) 로 오면 rank 가 죽는다. 행 집합은 안 바뀐다.
    for c in ["trading_value"] + AMT:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 분모: NULL·0 이면 결측(§1-④). 🔑 행을 «거르지 않고» 값만 NaN 으로 둔다.
    tv = df["trading_value"].astype("float64")
    tv = tv.where(tv > 0)
    df["f2_tv"] = tv
    for r in RAT:
        df[r] = df[SRC[r]].astype("float64") * UNIT[r] / tv

    for f in ALL:
        df[f + "_pct"] = df.groupby("date")[f].rank(pct=True) * 100
    return df.sort_values(["stock_code", "date"]).reset_index(drop=True)


def pack(df):
    """코드별 (정렬된 날짜 int64, 백분위 행렬) — 창 슬라이스를 searchsorted 로 만든다.

    `df` 가 (stock_code, date) 로 정렬돼 있으므로 groupby 슬라이스는 원본과 동일하다.
    """
    cols = [f + "_pct" for f in ALL]
    out = {}
    for c, g in df.groupby("stock_code", sort=False):
        out[c] = (g["date"].values.astype("datetime64[ns]").astype("int64"),
                  g[cols].to_numpy(dtype="float64"))
    return out


def slice_stat(packed, code, lo, hi, feats, agg):
    """창 [lo, hi] 안 일별 백분위의 max / median. 창에 행이 없으면 None."""
    ent = packed.get(code)
    if ent is None:
        return None
    dates, mat = ent
    a = np.searchsorted(dates, lo, "left")
    b = np.searchsorted(dates, hi, "right")
    if b <= a:
        return None                      # 원본의 `m.empty` 와 같은 판정
    sub = mat[a:b]
    fn = np.nanmax if agg == "max" else np.nanmedian
    with warnings.catch_warnings():      # all-NaN 슬라이스 → NaN (pandas 와 동치)
        warnings.simplefilter("ignore", RuntimeWarning)
        return {f: float(fn(sub[:, COL[f]])) for f in feats}


def null_dist(packed, codes, windows, feats, agg, pools=None):
    """창 길이 보존 귀무. `pools` 가 주어지면 창별 «매칭 후보»에서만 뽑는다(§6).

    🔴 추출 순서·재시도(20회)는 `run_selection_flow.py` 와 동일하게 유지 — 셀 A 재현 조건.
    """
    rng = np.random.default_rng(SEED)
    out = {f: [] for f in feats}
    drawn = set()
    for _ in range(NREP):
        draw = {f: [] for f in feats}
        for wi, (lo, hi) in enumerate(windows):
            pool = codes if pools is None else pools[wi]
            for _try in range(20):
                c = pool[rng.integers(len(pool))]
                drawn.add(c)
                s = slice_stat(packed, c, lo, hi, feats, agg)
                if s is not None:
                    for f in feats:
                        draw[f].append(s[f])
                    break
        for f in feats:
            v = np.nanmedian(draw[f]) if draw[f] else np.nan
            if np.isfinite(v):
                out[f].append(float(v))
    return out, drawn


def judge(feats, obs, null_med):
    """§4 — 양측 p · Holm(4) · 효과크기 문턱."""
    om = {f: float(np.nanmedian([o[f] for o in obs])) for f in feats}
    nan = {f: int(np.sum(~np.isfinite([o[f] for o in obs]))) for f in feats}
    nm, pv = {}, []
    for f in feats:
        arr = np.array(null_med[f])
        nm[f] = float(np.median(arr))
        hi = float((arr >= om[f]).mean())
        lo = float((arr <= om[f]).mean())
        pv.append(min(1.0, 2.0 * min(hi, lo)))
    adj = holm(np.array(pv))
    ok = {f: bool(adj[i] < 0.05 and abs(om[f] - nm[f]) >= EFF)
          for i, f in enumerate(feats)}
    return om, nm, nan, pv, adj, ok


def table(feats, om, nm, nan, pv, adj, ok, n):
    say("| 특징 | 관측 중앙 | 귀무 중앙 | 이탈 | 결측 | 양측 p | Holm p | 판정 |")
    say("|---|---|---|---|---|---|---|---|")
    for i, f in enumerate(feats):
        say(f"| `{f}` | **{om[f]:.1f}** | {nm[f]:.1f} | {om[f]-nm[f]:+.1f} | "
            f"{nan[f]}/{n} | {pv[i]:.4f} | {adj[i]:.4f} | "
            f"{'✅ 연관' if ok[f] else '⛔'} |")
    alive = [f for f in feats if ok[f]]
    say(f"\n**Holm(4) 통과: {alive or '없음'}**\n")
    return alive


def main() -> int:
    df = load()
    packed = pack(df)
    codes = df.stock_code.unique()

    say("# 수급 축은 「방향」인가 「거래대금의 그림자」인가\n")
    say(f"사전등록 `PREREG_FLOW_NORM.md` (`44587e8`) · 실행은 그 «뒤»다.\n")
    say(f"유니버스 **{df.stock_code.nunique():,}종목** · {df.date.nunique()}거래일 "
        f"({df.date.min().date()}~{df.date.max().date()}) · 거래정지일(volume=0) 제외\n")
    say("단위 보정(§1-①): " + " · ".join(f"`{r}` ×{UNIT[r]:,.0f}" for r in RAT) + "\n")
    tvbad = int((~np.isfinite(df["f2_tv"])).sum())
    say(f"분모 결측(`trading_value` NULL·0): **{tvbad:,}행 / {len(df):,}행**\n")

    # ── 관측 표본 (PREREG_SELECTION §2 그대로) ────────────────────────────────
    trades = list(csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")))
    windows, names, skipped = [], [], []
    for t in trades:
        code = CODES.get(t["stock_name"])
        if code is None:
            skipped.append(t["stock_name"])
            continue
        key = (t["post_log_no"], t["item_no"])
        if key in REG:
            d1 = pd.Timestamp(REG[key])
            d0 = d1 - pd.Timedelta(days=6)
        else:
            a, b = POST_WINDOW[t["post_log_no"]]
            d0, d1 = pd.Timestamp(a), pd.Timestamp(b)
        lo, hi = d0.value, d1.value
        if slice_stat(packed, code, lo, hi, AMT, "max") is None:
            skipped.append(t["stock_name"] + "(창내 데이터 없음)")
            continue
        windows.append((lo, hi))
        names.append((t["stock_name"], code))
    n = len(windows)
    say(f"양성 표본 **{n}건** / 원장 {len(trades)}건 · 제외 {skipped}\n")

    # ── §4 네 셀 ──────────────────────────────────────────────────────────────
    cells = [("A", "금액", "max", AMT), ("B", "금액", "median", AMT),
             ("C", "비율", "max", RAT), ("D", "비율", "median", RAT)]
    res = {}
    for tag, kind, agg, feats in cells:
        obs = [slice_stat(packed, c, lo, hi, feats, agg)
               for (_, c), (lo, hi) in zip(names, windows)]
        nulls, drawn = null_dist(packed, codes, windows, feats, agg)
        res[tag] = judge(feats, obs, nulls) + (feats, drawn)

    say("## §4 결과 — 2×2 요인 (성분을 하나씩 끈다)\n")
    say(f"귀무: 창 길이 보존 · {NREP:,}회 · 시드 {SEED} (셀 간 동일 추출)\n")
    for tag, kind, agg, _ in cells:
        om, nm, nan, pv, adj, ok, feats, drawn = res[tag]
        label = {"max": "창 최댓값", "median": "창 중앙값"}[agg]
        note = " — **재현 확인 (검정 아님)**" if tag == "A" else ""
        say(f"### 셀 {tag} — {kind} × {label}{note}\n")
        say(f"표집 다양성: 귀무가 실제로 뽑은 고유 종목 **{len(drawn):,}/{len(codes):,}**\n")
        table(feats, om, nm, nan, pv, adj, ok, n)

    # 셀 A 재현 대조
    say("### 셀 A 재현 대조 — `fa2b5d8` 대비\n")
    say("| 특징 | 관측 (이번 / fa2b5d8) | 귀무 (이번 / fa2b5d8) | 일치 |")
    say("|---|---|---|---|")
    omA, nmA = res["A"][0], res["A"][1]
    repro = True
    for f in AMT:
        ro, rn = CELL_A_REF[f]
        good = abs(omA[f] - ro) < 0.05 and abs(nmA[f] - rn) < 0.05
        repro &= good
        say(f"| `{f}` | {omA[f]:.1f} / {ro:.1f} | {nmA[f]:.1f} / {rn:.1f} | "
            f"{'✅' if good else '🔴 불일치'} |")
    say()
    say("🟢 **재현 확인** — 귀무 추출 경로가 원본과 동일하다."
        if repro else
        "🔴 **재현 실패 — 이 결과 전체를 신뢰하지 말 것.** 추출 경로가 갈렸다는 뜻이다.")
    say()

    # ── §5 V1·V2·V3 판정 ─────────────────────────────────────────────────────
    aliveB = [f for f in AMT if res["B"][5][f]]
    aliveC = [f for f in RAT if res["C"][5][f]]
    aliveD = [f for f in RAT if res["D"][5][f]]
    say("## §5 예측 판정\n")
    say("| 예측 | 내용 | 결과 | 판정 |")
    say("|---|---|---|---|")
    say(f"| **V1** (주·성분 S) | 셀 C 통과 0 | 통과 {len(aliveC)}: {aliveC or '없음'} | "
        f"{'✅ 지지' if not aliveC else '❌ 기각'} |")
    say(f"| **V2** (성분 W) | 셀 B 통과 0 | 통과 {len(aliveB)}: {aliveB or '없음'} | "
        f"{'✅ 지지' if not aliveB else '❌ 기각'} |")
    say(f"| **V3** (반증축) | 셀 D 통과 0 | 통과 {len(aliveD)}: {aliveD or '없음'} | "
        f"{'✅ 반증 없음' if not aliveD else '🔴 **반증 발동**'} |")
    say()
    if aliveD:
        say(f"🔴 **V3 발동 — {aliveD} 는 두 성분을 다 제거하고도 살아남았다.** "
            "사전등록대로 **「그림자 확정」 결론을 취소**하고 이 축을 「그림자 아님」으로 격상한다.\n")

    # ── §5 V4 구조·산술 확증 ──────────────────────────────────────────────────
    say("## §5 V4 — 구조 확증 (산술 · 귀무 불필요)\n")
    sub = df[np.isfinite(df.f10_frgn_pct) & np.isfinite(df.f12_prsn_pct)]
    per_day = []
    for _, g in sub.groupby("date"):
        if len(g) >= 30:
            per_day.append(spearmanr(g.f10_frgn_pct, g.f12_prsn_pct).statistic)
    rho_med = float(np.median(per_day))
    rho_pool = float(spearmanr(sub.f10_frgn_pct, sub.f12_prsn_pct).statistic)
    say(f"**(a)** 같은 날 `f10_frgn_pct` × `f12_prsn_pct` Spearman — "
        f"일별 중앙 **{rho_med:+.3f}** ({len(per_day)}일) · 통합 {rho_pool:+.3f} "
        f"→ 문턱 `< −0.5`: {'✅' if rho_med < -0.5 else '❌'}\n")

    same = float(((sub.f10_frgn_pct >= 90) & (sub.f12_prsn_pct >= 90)).mean())
    hits = tot = 0
    for lo, hi in windows:
        for c in codes:
            s = slice_stat(packed, c, lo, hi, ["f10_frgn", "f12_prsn"], "max")
            if s is None or not (np.isfinite(s["f10_frgn"]) and np.isfinite(s["f12_prsn"])):
                continue
            tot += 1
            hits += int(s["f10_frgn"] >= 90 and s["f12_prsn"] >= 90)
    wmax = hits / tot if tot else float("nan")
    ratio = wmax / same if same > 0 else float("inf")
    say(f"**(b)** 두 축 동시 ≥90 비율 — 같은 날 **{same*100:.3f}%** vs "
        f"창 최댓값 **{wmax*100:.3f}%** ({hits:,}/{tot:,}) = **{ratio:.1f}배** "
        f"→ 문턱 `≥ 5배`: {'✅' if ratio >= 5 else '❌'}\n")
    v4 = (rho_med < -0.5) and (ratio >= 5)
    say(f"**V4 판정: {'✅ 성분 W 를 산술로 확인' if v4 else '❌ 미충족'}**\n")

    # ── §6 V5 매칭 귀무 ───────────────────────────────────────────────────────
    say("## §6 V5 — 거래대금 매칭 귀무 (지표 불변, 비교 대상만 교체)\n")
    wq = {}      # 창별 {code: 창 안 f2_tv 백분위 중앙값}
    for lo, hi in set(windows):
        d = {}
        for c in codes:
            s = slice_stat(packed, c, lo, hi, ["f2_tv"], "median")
            if s is not None and np.isfinite(s["f2_tv"]):
                d[c] = s["f2_tv"]
        wq[(lo, hi)] = d

    keep, pools, bands, dropped = [], [], [], []
    for i, ((lo, hi), (nm_, c)) in enumerate(zip(windows, names)):
        d = wq[(lo, hi)]
        q = d.get(c)
        if q is None:
            dropped.append(nm_ + "(거래대금 결측)")
            continue
        arr = np.array(list(d.keys()))
        val = np.array([d[k] for k in arr])
        chosen = None
        for band in MATCH_BAND:
            pool = arr[np.abs(val - q) <= band]
            if len(pool) >= MATCH_MIN:
                chosen = (pool, band)
                break
        if chosen is None:
            dropped.append(f"{nm_}(후보 {len(pool)}<{MATCH_MIN})")
            continue
        keep.append(i)
        pools.append(chosen[0])
        bands.append(chosen[1])
    say(f"매칭 성립 **{len(keep)}/{n}건** · 밴드 ±5 **{bands.count(5.0)}건** / "
        f"±10 **{bands.count(10.0)}건** · 결측 {dropped or '없음'}\n")

    matched = None
    if len(keep) >= 3:
        w2 = [windows[i] for i in keep]
        obs2 = [slice_stat(packed, names[i][1], *windows[i], AMT, "max") for i in keep]
        nulls2, drawn2 = null_dist(packed, codes, w2, AMT, "max", pools=pools)
        om2, nm2, nan2, pv2, adj2, ok2 = judge(AMT, obs2, nulls2)
        say(f"표집 다양성: **{len(drawn2):,}/{len(codes):,}** (매칭 제약이 있으므로 유니버스보다 작다)\n")
        table(AMT, om2, nm2, nan2, pv2, adj2, ok2, len(keep))
        # V5: 매칭 귀무의 p 가 유니버스 귀무의 p 보다 큰 특징 수
        #     ⚠️ 표본이 줄었을 수 있으므로 같은 부분집합으로 유니버스 귀무도 다시 잰다.
        obs1 = [slice_stat(packed, names[i][1], *windows[i], AMT, "max") for i in keep]
        nulls1, _ = null_dist(packed, codes, w2, AMT, "max")
        _, nm1, _, pv1, _, _ = judge(AMT, obs1, nulls1)
        say("| 특징 | 유니버스 귀무 중앙 / p | 매칭 귀무 중앙 / p | p 증가 |")
        say("|---|---|---|---|")
        bigger = 0
        for i, f in enumerate(AMT):
            up = pv2[i] > pv1[i]
            bigger += int(up)
            say(f"| `{f}` | {nm1[f]:.1f} / {pv1[i]:.4f} | {nm2[f]:.1f} / {pv2[i]:.4f} | "
                f"{'✅' if up else '—'} |")
        matched = (om2, nm2, pv2, adj2)
        say(f"\n**V5 판정: {bigger}/4 에서 p 증가 → 문턱 `≥3`: "
            f"{'✅ 지지' if bigger >= 3 else '❌ 기각'}**\n")
        say("⚠️ 표본이 줄어든 경우를 대비해 **같은 부분집합으로 유니버스 귀무도 다시 쟀다** — "
            "표에서 비교되는 두 p 는 동일 표본이다.\n")
    else:
        say("🔴 **매칭 성립 건이 3건 미만 ⇒ V5 판정 불가.**\n")

    # ── 🏁 판정·해석 (서술은 사후, 숫자는 전부 위에서 계산된 것) ──────────────
    say("## 🏁 판정 — 「그림자」는 맞다. 그런데 더 큰 성분은 «창 연산자»였다\n")
    say("V1·V2·V3·V4·V5 **전부 사전등록 방향대로**. 반증축 V3 미발동.\n")
    say("### 성분 분해 — 관측 중앙 − 귀무 중앙 (백분위점)\n")
    say("| 축 | 셀 A 원본 | 셀 B `W` 제거 | 셀 C `S` 제거 | 셀 D 둘 다 |")
    say("|---|---|---|---|---|")
    for i, lab in enumerate(["외국인", "기관", "개인", "프로그램"]):
        d = []
        for tag, feats in (("A", AMT), ("B", AMT), ("C", RAT), ("D", RAT)):
            om_, nm_ = res[tag][0], res[tag][1]
            d.append(om_[feats[i]] - nm_[feats[i]])
        say(f"| {lab} | **{d[0]:+.1f}** | {d[1]:+.1f} | {d[2]:+.1f} | {d[3]:+.1f} |")
    say()
    say("🔑 ***성분을 «어느 쪽이든 하나만» 꺼도 신호가 죽는다.*** 그리고 `W` 를 끄는 쪽이 더 완전하다 — "
        f"외국인이 **{res['A'][0]['f10_frgn']:.1f} → {res['B'][0]['f10_frgn']:.1f}** 로 "
        "중앙값 부근까지 내려앉는다.\n")
    say("### 🔑🔑 가장 결정적인 숫자는 통계가 아니라 산술이다\n")
    say(f"같은 날 기준 개인 × 외국인 Spearman **{rho_med:+.3f}** — 제로섬이 데이터로 확인된다. "
        "그러면 두 축이 «같은 날» 동시에 90+ 인 일은 드물어야 하고, 실제로 "
        f"**{same*100:.3f}%** 뿐이다. 그런데 창 안 최댓값으로 바꾸면 **{wmax*100:.3f}%** "
        f"= **{ratio:.1f}배**로 뛴다.\n")
    say("⇒ ***창 안 최댓값을 쓰면 유니버스의 «4분의 1»이 서로 거울상인 두 축에서 동시에 90+ 가 된다.*** "
        "「개인도 외국인도 상위였다」는 **발견이 아니라 연산자가 만든 것**이다.\n")
    if matched is not None:
        om2, nm2 = matched[0], matched[1]
        near = [f for f in AMT if abs(om2[f] - nm2[f]) < 2]
        say("🔑 그리고 매칭 귀무가 같은 말을 **다른 길로** 한다 — 거래대금 백분위를 ±5 로 맞추면 "
            f"대조군 중앙이 **{min(nm2.values()):.1f}~{max(nm2.values()):.1f}** 로 올라가 "
            f"**{len(near)}/4 축({', '.join(f'`{f}`' for f in near)})이 관측과 2 백분위점 안**으로 붙는다 — "
            f"유니버스 귀무에서 +10 이던 것들이다.\n")
        say("⇒ ***「상위 95%」가 이상해 보였던 건 대조군이 잘못돼 있었기 때문이다.*** "
            f"🔴 예외는 `f11_orgn` 하나로, 관측 {om2['f11_orgn']:.1f} 이 매칭 대조군 "
            f"{nm2['f11_orgn']:.1f} 보다 **{nm2['f11_orgn']-om2['f11_orgn']:.1f} 낮다**"
            "(§9 N-V4 로 등록).\n")

    say("### 🔴 사전 문턱이 실제로 일을 했다 — 셀 C 는 «아깝게» 미달이다\n")
    cadj = res["C"][4]
    say(f"셀 C 는 네 축 **전부 Holm p < 0.05** 다(최대 {max(cadj):.4f}). 그런데 판정은 ⛔ —"
        f" 이탈이 " + " · ".join(f"{res['C'][0][r]-res['C'][1][r]:+.1f}" for r in RAT) +
        f" 로 **사전 고정한 {EFF:.0f} 백분위점 문턱**에 못 미쳤다. "
        "그리고 **네 축이 전부 «낮은 쪽»**이다.\n")
    say("⚠️ **이건 사후 관측이다.** 문턱을 9 로 낮추면 *「정규화하면 부호가 뒤집힌다」*가 발견이 되는데, "
        "그건 **결과를 보고 문턱을 옮기는 것**이다. **기각은 기각으로 둔다.**")
    say("🟢 다만 네 축의 방향이 같고 기전도 그럴듯하다 — 거래대금이 폭발한 종목은 매수·매도가 상쇄돼 "
        "**순매수 «비율»이 오히려 작아진다.** ⇒ **다음 글 예측으로만 등록한다** "
        "(`PREREG_FLOW_NORM.md` §9 **N-V3**).")
    if matched is not None:
        om2, nm2, _, adj2 = matched
        say(f"같은 형태가 매칭 귀무에도 있다 — `f11_orgn` 이탈 "
            f"**{om2['f11_orgn']-nm2['f11_orgn']:+.1f}**"
            f"(Holm p {adj2[AMT.index('f11_orgn')]:.4f})도 문턱 미달이다.\n")

    say("### 이 결과가 «취소하는» 것\n")
    say("🔴 `fa2b5d8` 의 *「Holm 통과 수급 3축(`f10`·`f12`·`f14`)」*은 **선정 축으로 인용할 수 없다.** "
        "그 세 축은 **거래대금 규모 × 창 최댓값 연산자**의 산물이다.")
    say("🔴 그리고 이 결함은 **`f10~f14` 만의 문제가 아니다** — 창 최댓값은 `f1~f9` 에도 쓰였다. "
        "다만 `f1~f9` 는 대부분 **부호가 한쪽인 양수 지표**(거래대금·변동성 등)라 제로섬 거울상이 없고, "
        "`bf39046` 이 이미 **후보군 귀무로 94~99 → 46~80** 을 보였다. "
        "🔑 ***두 진단이 같은 곳을 가리킨다 — 유의성의 출처는 「선택」이 아니라 「대조군」이었다.***\n")

    # ── 한계 (사전등록 §8 승계) ───────────────────────────────────────────────
    say("## 🔴 한계 — 사전등록 §8 그대로\n")
    say(f"- **n = {n}건.** 어떤 결과도 이걸 못 넘는다.")
    say("- Holm family 는 **셀마다 4개씩 따로**다. 네 셀 + 기존 18개를 합치면 "
        "**study-wide 오류율은 훨씬 높다.**")
    say("- 수급 데이터가 **2026-07-03 부터**라 7월 글의 창 일부는 앞이 잘린다(결측 인쇄분).")
    say("- **「그림자 확정」은 「`f10`·`f12`·`f14` 가 선정 축이 아니다」는 뜻이지 "
        "「수급이 축이 아니다」는 뜻이 아니다.**")
    say("- **수급은 저자가 본문에서 언급한 적이 없다** — 유의해도 *「저자가 수급을 본다」*가 아니라 "
        "*「올라온 매매가 수급 상위였다」*는 뜻이다.")
    say("- 승/패 대조 게이트는 **이 문서에 등록하지 않았다.** 표본이 `fa2b5d8` 과 같으므로 "
        "거기서 통과한 게이트가 승계된다 — 새로 계산해 붙이지 않는다(사후 추가 방지).")
    say("- 라이브 채택 대상이 아니다.")

    (BASE / "RESULTS_FLOW_NORM.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_FLOW_NORM.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

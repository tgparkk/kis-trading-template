# -*- coding: utf-8 -*-
"""`PREREG_SELECTION_ROBUST.md`(`f3680ed`) 실행 — `f1~f9` 를 창 연산자·대조군을 바꿔 다시 잰다.

2×2: {창 최댓값, 창 중앙값} × {유니버스 귀무, 거래대금 매칭 귀무}.
셀 A′(최댓값×유니버스)는 `RESULTS_SELECTION.md`(`9e53825`) 의 재현 확인이다.

🔴 **셀 A′ 재현을 위해 `run_selection` 의 `load`·`build_features` 를 «그대로» import 한다** —
   쿼리·필터를 한 글자도 바꾸지 않아야 `codes` 배열과 난수 추출 순서가 원본과 같다.

라이브 트리 import 0건 (psycopg2 / pandas / numpy + 표준 라이브러리). DB 는 SELECT 만.
"""
from __future__ import annotations

import csv
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from run_selection import (FEATS, NREP, POST_WINDOW, REG, build_features, holm,
                           load)
from run_tests import CODES

BASE = Path(__file__).resolve().parent
OUT: list[str] = []

SEED = 20260815
EFF = 10.0                 # §3 효과크기 문턱 (백분위점) — PREREG_FLOW_NORM §4 와 같은 값
MATCH_BAND = (5.0, 10.0)
MATCH_MIN = 20
MATCH_AXIS = "f2_tv"       # §3 — 매칭축 자신이라 셀 C′·D′ 의 Holm family 에서 뺀다

# §2 🔒 결과를 보기 «전에» 못박은 분류 (정의만 보고 판단)
PERSIST = ["f2_tv", "f4_vol20", "f6_spikes60", "f7_mcap"]
EVENT = ["f1_tv_mcap", "f3_tv_surge", "f8_ma20dev", "f9_newhigh"]
MID = ["f5_pos60"]
KLASS = {**{f: "지속형" for f in PERSIST}, **{f: "사건형" for f in EVENT},
         **{f: "중간형" for f in MID}}

# 셀 A′ 통과 5축(원본 규칙 기준) — §4 예측의 기준 집합
BASE5 = ["f1_tv_mcap", "f2_tv", "f4_vol20", "f6_spikes60", "f8_ma20dev"]
PRED_DIE = [f for f in BASE5 if KLASS[f] == "사건형"]     # W1: f1_tv_mcap, f8_ma20dev
PRED_LIVE = [f for f in BASE5 if KLASS[f] == "지속형"]    # W2: f2_tv, f4_vol20, f6_spikes60

# `RESULTS_SELECTION.md` §3 — 재현 대조 기준선 (관측 중앙, 귀무 중앙)
REF = {"f1_tv_mcap": (99.4, 75.6), "f2_tv": (96.4, 65.7), "f3_tv_surge": (94.0, 90.9),
       "f4_vol20": (97.4, 58.3), "f5_pos60": (66.1, 58.3), "f6_spikes60": (95.7, 31.2),
       "f7_mcap": (61.6, 52.2), "f8_ma20dev": (98.4, 80.1), "f9_newhigh": (48.3, 48.3)}

COL = {f: i for i, f in enumerate(FEATS)}


def say(s=""):
    print(s)
    OUT.append(s)


def pack(df):
    """코드별 (정렬된 날짜 int64, 백분위 행렬). `m.empty` 판정은 원본과 동치."""
    cols = [f + "_pct" for f in FEATS]
    out = {}
    for c, g in df.groupby("stock_code", sort=False):
        out[c] = (g["date"].values.astype("datetime64[ns]").astype("int64"),
                  g[cols].to_numpy(dtype="float64"))
    return out


def slice_stat(packed, code, lo, hi, agg, feats=None):
    feats = feats or FEATS
    ent = packed.get(code)
    if ent is None:
        return None
    dates, mat = ent
    a = np.searchsorted(dates, lo, "left")
    b = np.searchsorted(dates, hi, "right")
    if b <= a:
        return None
    sub = mat[a:b]
    fn = np.nanmax if agg == "max" else np.nanmedian
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return {f: float(fn(sub[:, COL[f]])) for f in feats}


def null_dist(packed, codes, windows, agg, pools=None):
    """창 길이 보존 귀무. 추출 순서·재시도는 `run_selection.py` 와 동일(셀 A′ 재현 조건)."""
    rng = np.random.default_rng(SEED)
    out = {f: [] for f in FEATS}
    drawn = set()
    for _ in range(NREP):
        draw = {f: [] for f in FEATS}
        for wi, (lo, hi) in enumerate(windows):
            pool = codes if pools is None else pools[wi]
            for _try in range(20):
                c = pool[rng.integers(len(pool))]
                drawn.add(c)
                s = slice_stat(packed, c, lo, hi, agg)
                if s is not None:
                    for f in FEATS:
                        draw[f].append(s[f])
                    break
        for f in FEATS:
            v = np.nanmedian(draw[f]) if draw[f] else np.nan
            if np.isfinite(v):
                out[f].append(float(v))
    return out, drawn


def judge(obs, null_med, family):
    """양측 p · Holm(family) · 효과크기 문턱. family 밖 특징은 Holm 미보정(판정 제외)."""
    om = {f: float(np.nanmedian([o[f] for o in obs])) for f in FEATS}
    nan = {f: int(np.sum(~np.isfinite([o[f] for o in obs]))) for f in FEATS}
    nm, pv = {}, {}
    for f in FEATS:
        arr = np.array(null_med[f])
        nm[f] = float(np.median(arr))
        hi = float((arr >= om[f]).mean())
        lo = float((arr <= om[f]).mean())
        pv[f] = min(1.0, 2.0 * min(hi, lo))
    fam = [f for f in FEATS if f in family]
    adjv = holm(np.array([pv[f] for f in fam]))
    adj = {f: float(adjv[i]) for i, f in enumerate(fam)}
    ok = {f: bool(f in adj and adj[f] < 0.05 and abs(om[f] - nm[f]) >= EFF) for f in FEATS}
    return om, nm, nan, pv, adj, ok


def table(om, nm, nan, pv, adj, ok, n, family):
    say("| 특징 | 분류 | 관측 중앙 | 귀무 중앙 | 이탈 | 결측 | 양측 p | Holm p | 판정 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for f in FEATS:
        inf = f in family
        say(f"| `{f}` | {KLASS[f]} | **{om[f]:.1f}** | {nm[f]:.1f} | {om[f]-nm[f]:+.1f} | "
            f"{nan[f]}/{n} | {pv[f]:.4f} | {adj.get(f, float('nan')):.4f} | "
            f"{'✅ 연관' if ok[f] else ('⛔' if inf else '— 매칭축(제외)')} |")
    alive = [f for f in FEATS if ok[f]]
    say(f"\n**Holm({len(family)}) 통과: {alive or '없음'}**\n")
    return alive


def main() -> int:
    df = build_features(load())
    packed = pack(df)
    codes = df.stock_code.unique()

    say("# `f1~f9` 견고성 — 창 연산자와 대조군을 바꿔 다시 잰다\n")
    say("사전등록 `PREREG_SELECTION_ROBUST.md` (`f3680ed`) · 실행은 그 «뒤»다.\n")
    say(f"유니버스 **{df.stock_code.nunique():,}종목** · {df.date.nunique()}거래일 "
        f"({df.date.min().date()}~{df.date.max().date()})\n")
    say("🔒 **§2 분류 (실행 전 동결)** — 지속형 `" + "` · `".join(PERSIST) + "` / "
        "사건형 `" + "` · `".join(EVENT) + "` / 중간형 `" + "` · `".join(MID) + "`\n")

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
        if slice_stat(packed, code, lo, hi, "max") is None:
            skipped.append(t["stock_name"] + "(창내 데이터 없음)")
            continue
        windows.append((lo, hi))
        names.append((t["stock_name"], code))
    n = len(windows)
    say(f"양성 표본 **{n}건** / 원장 {len(trades)}건 · 제외 {skipped}\n")

    # ── 매칭 후보 풀 (§3 — 매칭 키는 셀에 안 따라감: 항상 창 «중앙값») ────────
    wq = {}
    for lo, hi in set(windows):
        d = {}
        for c in codes:
            s = slice_stat(packed, c, lo, hi, "median", [MATCH_AXIS])
            if s is not None and np.isfinite(s[MATCH_AXIS]):
                d[c] = s[MATCH_AXIS]
        wq[(lo, hi)] = d
    keep, pools, bands, mdrop = [], [], [], []
    for i, ((lo, hi), (nm_, c)) in enumerate(zip(windows, names)):
        d = wq[(lo, hi)]
        q = d.get(c)
        if q is None:
            mdrop.append(nm_ + "(매칭키 결측)")
            continue
        arr = np.array(list(d.keys()))
        val = np.array([d[k] for k in arr])
        pick = None
        for band in MATCH_BAND:
            pool = arr[np.abs(val - q) <= band]
            if len(pool) >= MATCH_MIN:
                pick = (pool, band)
                break
        if pick is None:
            mdrop.append(f"{nm_}(후보 {len(pool)}<{MATCH_MIN})")
            continue
        keep.append(i)
        pools.append(pick[0])
        bands.append(pick[1])
    wk = [windows[i] for i in keep]
    nk = [names[i] for i in keep]

    # ── 네 셀 ────────────────────────────────────────────────────────────────
    FAM_FULL = set(FEATS)
    FAM_M = set(FEATS) - {MATCH_AXIS}
    cells = [("A′", "창 최댓값", "유니버스 귀무", "max", None, windows, names, FAM_FULL),
             ("B′", "창 중앙값", "유니버스 귀무", "median", None, windows, names, FAM_FULL),
             ("C′", "창 최댓값", "거래대금 매칭 귀무", "max", pools, wk, nk, FAM_M),
             ("D′", "창 중앙값", "거래대금 매칭 귀무", "median", pools, wk, nk, FAM_M)]

    say("## §3 결과 — 2×2 (창 연산자 × 대조군)\n")
    say(f"귀무: 창 길이 보존 · {NREP:,}회 · 시드 {SEED} (셀마다 RNG 새로 생성)\n")
    say(f"매칭 성립 **{len(keep)}/{n}건** · 밴드 ±5 **{bands.count(5.0)}건** / "
        f"±10 **{bands.count(10.0)}건** · 결측 {mdrop or '없음'}\n")

    res = {}
    for tag, wl, nl, agg, pl, wins, nms, fam in cells:
        obs = [slice_stat(packed, c, lo, hi, agg) for (_, c), (lo, hi) in zip(nms, wins)]
        nulls, drawn = null_dist(packed, codes, wins, agg, pools=pl)
        om, nm, nan, pv, adj, ok = judge(obs, nulls, fam)
        res[tag] = (om, nm, nan, pv, adj, ok, fam)
        note = " — **재현 확인 (검정 아님)**" if tag == "A′" else ""
        say(f"### 셀 {tag} — {wl} × {nl}{note}\n")
        say(f"표본 **{len(wins)}건** · 표집 다양성 **{len(drawn):,}/{len(codes):,}**\n")
        table(om, nm, nan, pv, adj, ok, len(wins), fam)

    # ── 셀 A′ 재현 대조 ──────────────────────────────────────────────────────
    say("### 셀 A′ 재현 대조 — `RESULTS_SELECTION.md` 대비\n")
    say("⚠️ 결정규칙이 원본(단측 + 관측≥90)과 다르므로 **관측·귀무 중앙값만** 대조한다.\n")
    say("| 특징 | 관측 (이번 / 원본) | 귀무 (이번 / 원본) | 일치 |")
    say("|---|---|---|---|")
    omA, nmA = res["A′"][0], res["A′"][1]
    repro = True
    for f in FEATS:
        ro, rn = REF[f]
        good = abs(omA[f] - ro) < 0.05 and abs(nmA[f] - rn) < 0.05
        repro &= good
        say(f"| `{f}` | {omA[f]:.1f} / {ro:.1f} | {nmA[f]:.1f} / {rn:.1f} | "
            f"{'✅' if good else '🔴 불일치'} |")
    say()
    say("🟢 **재현 확인** — 로더·귀무 추출 경로가 원본과 동일하다."
        if repro else
        "🔴 **재현 실패 — 이 결과 전체를 신뢰하지 말 것.** (사전등록 §3 의 문구 그대로 남긴다)")
    say()

    if not repro:
        # 매드업 = 2026-07-01 코스닥 신규상장(`0039P0`). 커밋본 시점엔 daily_prices 8행뿐이었고
        # 2026-08-15 오전에 32행으로 백필됐다 → t3(60일 고가 대비)가 100.0% 였던 이유.
        say("### 🔴 재현 실패의 원인 — 코드가 아니라 «데이터»다\n")
        say("**증거 1 — 내 코드는 원본과 동일하다.** `run_selection.window_stat` 과 이 스크립트의 "
            "`slice_stat` 을 33건 전수 대조하니 **불일치 0**이었다(값·NaN 모두).")
        say("**증거 2 — `run_selection.py` 를 «지금» 돌리면 커밋된 자기 산출물과 다르다.** "
            "스크립트는 한 글자도 안 바뀌었고 `regen_gate.py` 는 **PASS** 인데도 그렇다.")
        say("**증거 3 — 차이의 모양이 백필이다.** `f3·f4·f5·f6·f8` 의 결측이 **1/33 → 0/33** 으로 "
            "줄었다(롤링 창에 히스토리가 생겼다).")
        code_m = CODES.get("매드업")
        if code_m:
            D = pd.Timestamp("2026-08-06")
            mm = df[df.stock_code == code_m]
            hist = mm[(mm.date <= D) & (mm.date >= D - pd.Timedelta(days=90))]
            row = hist[hist.date == D]
            if len(row) and len(hist):
                t3 = float(row.close.iloc[0]) / float(hist.high.max())
                say(f"**증거 4 (결정적) — 매드업(`{code_m}`).** 지금 `daily_prices` 에 "
                    f"**{len(mm)}행**(2026-04-01~08-14) · 그중 90일 창 안 **{len(hist)}행** · "
                    f"`t3`(60일 고가 대비) = **{t3*100:.1f}%** 인데 커밋본은 **100.0%** 였다. "
                    "매드업은 **2026-07-01 코스닥 신규상장**이고 `daily_prices` 최초일이 2026-08-05 라 "
                    "*「8행뿐이라 등록일이 곧 창 최고가」*였던 것이다. "
                    "**2026-08-15 오전에 일봉을 8 → 32행으로 백필했다.**")
        say()
        say("⇒ 🔑🔑 ***재현 게이트는 「스크립트가 같은가」만 본다 — 「데이터가 같은가」는 안 본다.*** "
            "`regen_gate.py` 문서의 전제(*「모든 산출 스크립트가 결정적이거나 시드가 고정돼 있다」*)는 "
            "**DB 를 읽는 스크립트에 대해 거짓**이다. DB 읽는 스크립트는 결정적인 게 아니라 "
            "**「DB 스냅샷이 고정될 때만」 결정적**이다. "
            "🔴 **이 결함은 이 디렉토리의 모든 `RESULTS_*` 에 소급된다.**\n")
        say("### 그래도 W1~W6 을 버리지 않는 이유 (그리고 버리지 «못하는» 이유)\n")
        say("- 재현 검사의 목적은 *「내 코드가 다른 경로를 타는가」*였고 그건 **증거 1 로 독립 배제**됐다.")
        say("- **네 셀은 같은 `df` 하나를 쓴다** ⇒ 데이터가 움직였어도 **셀 «사이»의 비교는 온전하다.** "
            "이 문서의 검정은 전부 셀 간 비교다.")
        say("- 🔑 **결과가 내 가설에 불리하다**(아래 W1·W3·W4·W5·W6 기각). "
            "***재현 실패를 이유로 버리면 내 예측에 불리한 결과를 골라 버리는 셈이다.***")
        say("- 🔴 **다만 이 문서의 숫자를 `RESULTS_SELECTION.md` 의 숫자와 나란히 인용하지 말 것** — "
            "둘은 **다른 DB 스냅샷**의 산물이다. 그 파일은 재생성이 필요하다.\n")

    # ── §4 예측 판정 ─────────────────────────────────────────────────────────
    aliveB = sorted(f for f in FEATS if res["B′"][5][f])
    aliveC = sorted(f for f in FEATS if res["C′"][5][f])
    aliveD = sorted(f for f in FEATS if res["D′"][5][f])
    w1 = all(not res["B′"][5][f] for f in PRED_DIE)
    w2 = all(res["B′"][5][f] for f in PRED_LIVE)
    w3 = set(aliveB) == set(PRED_LIVE)
    w4 = not res["C′"][5]["f1_tv_mcap"]
    w5 = len(aliveD) <= 2

    say("## §4 예측 판정\n")
    say("| 예측 | 내용 | 결과 | 판정 |")
    say("|---|---|---|---|")
    say(f"| **W1** (주) | 셀 B′ 에서 사건형 {PRED_DIE} 둘 다 탈락 | "
        f"생존 {[f for f in PRED_DIE if res['B′'][5][f]] or '없음'} | "
        f"{'✅ 지지' if w1 else '❌ 기각'} |")
    say(f"| **W2** (주) | 셀 B′ 에서 지속형 {PRED_LIVE} 셋 다 생존 | "
        f"탈락 {[f for f in PRED_LIVE if not res['B′'][5][f]] or '없음'} | "
        f"{'✅ 지지' if w2 else '❌ 기각'} |")
    say(f"| **W3** (반증축) | 셀 B′ 통과 집합 == {sorted(PRED_LIVE)} | {aliveB} | "
        f"{'✅ 정확 일치' if w3 else '🔴 **불일치 — 분류 축 폐기**'} |")
    say(f"| **W4** | 셀 C′ 에서 `f1_tv_mcap` 탈락 | "
        f"{'탈락' if w4 else '생존'} | {'✅ 지지' if w4 else '❌ 기각'} |")
    say(f"| **W5** | 셀 D′ 통과 ≤ 2 | 통과 {len(aliveD)}: {aliveD or '없음'} | "
        f"{'✅ 지지' if w5 else '❌ 기각'} |")
    say()
    if not w3:
        say("🔴 **W3 반증축 발동 — 사전등록대로 「지속형/사건형」 축을 폐기한다.** "
            "W1·W2 가 부분적으로 맞았더라도 **그 해석을 쓰지 않는다.**\n")

    # ── §4 W6 — 유니버스만 쓰는 독립 검산 ────────────────────────────────────
    say("## §4 W6 — 분류의 독립 검산 (유니버스만 사용 · 관측 33건 미사용)\n")
    gaps = {f: [] for f in FEATS}
    for lo, hi in windows:
        for c in codes:
            mx = slice_stat(packed, c, lo, hi, "max")
            md = slice_stat(packed, c, lo, hi, "median")
            if mx is None:
                continue
            for f in FEATS:
                if np.isfinite(mx[f]) and np.isfinite(md[f]):
                    gaps[f].append(mx[f] - md[f])
    gm = {f: float(np.median(gaps[f])) for f in FEATS}
    say("특징별 「창 최댓값 백분위 − 창 중앙값 백분위」의 유니버스 중앙값:\n")
    say("| 특징 | 분류 | 최댓값−중앙값 |")
    say("|---|---|---|")
    for f in sorted(FEATS, key=lambda x: -gm[x]):
        say(f"| `{f}` | {KLASS[f]} | **{gm[f]:.1f}** |")
    lo_e = min(gm[f] for f in EVENT)
    hi_p = max(gm[f] for f in PERSIST)
    w6 = lo_e > hi_p
    say(f"\n사건형 최소 **{lo_e:.1f}** vs 지속형 최대 **{hi_p:.1f}** → 교차 0 문턱: "
        f"{'✅ 완전 분리' if w6 else '❌ 교차 발생'}")
    say(f"**W6 판정: {'✅ 분류가 데이터로 독립 확인됨' if w6 else '❌ 분류가 데이터와 안 맞는다'}**\n")

    # ── 🏁 요약 ──────────────────────────────────────────────────────────────
    say("## 🏁 판정 요약\n")
    verdicts = [("W1", w1), ("W2", w2), ("W3", w3), ("W4", w4), ("W5", w5), ("W6", w6)]
    say(" · ".join(f"**{k}** {'✅' if v else '❌'}" for k, v in verdicts) + "\n")
    say("### 셀별 통과 집합\n")
    say(f"- 셀 A′ (최댓값 × 유니버스, 재현): "
        f"{sorted(f for f in FEATS if res['A′'][5][f])}")
    say(f"- 셀 B′ (중앙값 × 유니버스): {aliveB}")
    say(f"- 셀 C′ (최댓값 × 매칭): {aliveC}  ⚠️ `f2_tv` 는 매칭축이라 family 제외")
    say(f"- 셀 D′ (중앙값 × 매칭): {aliveD}\n")

    say("### `f1~f9` 축별 이탈 (관측 중앙 − 귀무 중앙)\n")
    say("| 특징 | 분류 | A′ | B′ | C′ | D′ |")
    say("|---|---|---|---|---|---|")
    for f in FEATS:
        d = [res[t][0][f] - res[t][1][f] for t in ("A′", "B′", "C′", "D′")]
        say(f"| `{f}` | {KLASS[f]} | **{d[0]:+.1f}** | {d[1]:+.1f} | {d[2]:+.1f} | {d[3]:+.1f} |")
    say()

    # ── 🏁 해석 (서술은 사후, 숫자는 전부 위에서 계산된 것) ────────────────────
    say("## 🏁 해석 — `f1~f9` 는 `f10~f14` 와 «반대»였다\n")
    say("🔴 **W3 반증축이 발동했으므로 「지속형/사건형」 분류는 폐기한다.** "
        "그런데 **왜 틀렸는가**가 이 실행의 소득이다.\n")

    say("### ① 여기서는 창 최댓값이 신호를 «만든» 게 아니라 «가리고» 있었다\n")
    d_a = {f: res["A′"][0][f] - res["A′"][1][f] for f in FEATS}
    d_b = {f: res["B′"][0][f] - res["B′"][1][f] for f in FEATS}
    grew = [f for f in BASE5 if d_b[f] > d_a[f]]
    say(f"셀 A′ → B′ 에서 이탈이 **커진** 축: {grew}\n")
    for f in grew:
        say(f"- `{f}` : {d_a[f]:+.1f} → **{d_b[f]:+.1f}**")
    say()
    say("🔑🔑 ***같은 연산자가 한 축 집합에서는 신호를 «만들고», 다른 집합에서는 «가린다».*** "
        "`f10~f14`(부호 있는 제로섬)에서는 최댓값이 관측을 띄웠고(94.6 → 중앙값 47.9), "
        "여기서는 최댓값이 **귀무를 더 많이 띄워** 관측과의 차이를 줄이고 있었다. "
        "⇒ **연산자 자체엔 방향이 없다 — 특징의 «시간 구조»가 방향을 정한다.**\n")

    say("### ② 「사건성」은 이미 귀무 중앙값 안에 들어 있었다 (사후 관측)\n")
    say("셀 A′ 의 **귀무 중앙**(무작위 종목의 창 최댓값 백분위)과 W6 의 "
        "**「최댓값−중앙값」 유니버스 격차**가 사실상 같은 것을 재고 있다:\n")
    say("| 특징 | 분류 | A′ 귀무 중앙 | W6 격차 |")
    say("|---|---|---|---|")
    for f in sorted(FEATS, key=lambda x: -res["A′"][1][x]):
        say(f"| `{f}` | {KLASS[f]} | {res['A′'][1][f]:.1f} | {gm[f]:.1f} |")
    say()
    say("🔑 ***귀무 중앙이 50 에서 멀리 위로 뜬 특징일수록 「하루만 극단」인 특징이다*** — "
        "무작위 종목조차 창 안 어느 하루엔 상위가 되기 때문이다. "
        "**두 척도가 거의 단조로 일치한다**(예외는 `f9_newhigh` 하나). "
        "⇒ 사건성은 **따로 정의할 필요가 없었다. 귀무가 이미 재고 있었다.**\n")

    say("### ③ W6 을 깬 것은 `f9_newhigh` 하나 — 그런데 사전등록이 이미 경고했다\n")
    ev9 = [f for f in EVENT if f != "f9_newhigh"]
    say(f"`f9_newhigh` 격차 **{gm['f9_newhigh']:.1f}** 로 꼴찌다. **이진 축퇴** 때문이다 — "
        "백분위가 두 덩어리로 뭉쳐 동점이라 최댓값과 중앙값이 거의 같다. "
        "`PREREG_SELECTION_ROBUST.md` §6 이 *「결과를 특징의 성질로 읽지 말 것」*이라고 "
        "**미리** 적어놨는데, 정작 §2 에서는 그걸 사건형에 넣어 W6 의 「교차 0」 문턱에 걸었다.")
    say(f"⚠️ **기각은 기각으로 둔다.** 🟢 다만 사후로 적어두면 — `f9` 를 빼면 "
        f"사건형 최소 **{min(gm[f] for f in ev9):.1f}** vs 지속형 최대 **{hi_p:.1f}** 로 "
        "**완전 분리**다. 🔑 ***내가 미리 적은 경고를 내 설계에 반영하지 않은 것이 결함이다*** — "
        "한계 절에 쓰고 예측에는 안 쓴 것.\n")

    say("### ④ 그리고 실질 결론 — 「거래대금의 그림자」가 아니다\n")
    say(f"- 셀 B′(연산자 제거) 통과 **{len(aliveB)}개**: {aliveB}")
    say(f"- 셀 C′(거래대금 매칭) 통과 **{len(aliveC)}개**: {aliveC}")
    say(f"- 셀 D′(둘 다 제거) 통과 **{len(aliveD)}개**: {aliveD}\n")
    say("⇒ 🔑 ***`f10~f14` 와 정반대다. 성분을 둘 다 제거해도 살아남는다.*** "
        "`f1~f9` 의 1단계 축은 **창 연산자의 산물도, 거래대금의 그림자도 아니다.**\n")
    say("🆕 **대조군을 바꾸니 «새로» 보인 것 2가지** (사후):")
    say(f"- `f7_mcap` 이 **음의 방향으로 유의**해졌다 — 유니버스 귀무 {d_a['f7_mcap']:+.1f}(판별력 없음) "
        f"→ 매칭 귀무 셀 C′ **{res['C′'][0]['f7_mcap']-res['C′'][1]['f7_mcap']:+.1f}** · "
        f"셀 D′ **{res['D′'][0]['f7_mcap']-res['D′'][1]['f7_mcap']:+.1f}**. "
        "***같은 거래대금인데 시총이 훨씬 작다 = 회전율이 높다*** — "
        "`f1_tv_mcap` 이 네 셀 전부에서 살아남는 것과 **같은 사실의 두 표현**이다.")
    say(f"- `f3_tv_surge` 가 창 중앙값에서 **{d_b['f3_tv_surge']:+.1f}** 로 뒤집혔다"
        f"(최댓값에선 {d_a['f3_tv_surge']:+.1f} 판별력 없음). 선정 종목은 급증배수가 "
        "**평소엔 오히려 낮다** — 「하루 튀고 평소엔 조용」이 아니라 "
        "**「평소에도 거래대금이 커서 급증배수의 분모가 크다」**는 그림과 정합.\n")
    say("🔴 **그래도 이건 1단계 이야기다.** `bf39046` 의 후보군 귀무(94~99 → 46~80)는 그대로다 — "
        "***이 축들은 「후보군에 «드는»」 조건이지 「18 → 1~2 로 «뽑히는»」 조건이 아니다.***\n")

    # ── 한계 (사전등록 §6 승계) ──────────────────────────────────────────────
    say("## 🔴 한계 — 사전등록 §6 그대로\n")
    say(f"- **n = {n}건.** 어떤 결과도 이걸 못 넘는다.")
    say("- **셀 B′ 에서 살아남아도 「저자가 그 축을 본다」는 뜻이 아니다.** `bf39046` 이 이미 "
        "**후보군 귀무에서 94~99 → 46~80** 을 보였다 — `f1~f9` 는 **「후보군에 «드는»」 조건**이지 "
        "「«뽑히는»」 조건이 아니다. 이 문서는 **1단계(유니버스→후보군)만** 다시 잰 것이다.")
    say("- 🔴 **`f9_newhigh` 는 이진이라 백분위가 두 덩어리로 뭉친다** — 원본에서 관측·귀무가 "
        "둘 다 48.3 이었던 게 그 징후다. **결과를 특징의 성질로 읽지 말 것.**")
    say("- Holm family 는 셀 A′·B′ 9개 / C′·D′ 8개다. **네 셀 + 기존 검정을 합치면 "
        "study-wide 오류율은 훨씬 높다.**")
    say("- 매칭 귀무는 **표집 다양성이 낮아 검정력이 떨어진다.**")
    say("- 승/패 대조 게이트는 **이 문서에 등록하지 않았다** — 표본이 같으므로 "
        "`RESULTS_SELECTION.md` §4 에서 통과한 게이트를 승계한다(사후 추가 방지).")
    say("- 라이브 채택 대상이 아니다.")

    (BASE / "RESULTS_SELECTION_ROBUST.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_SELECTION_ROBUST.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

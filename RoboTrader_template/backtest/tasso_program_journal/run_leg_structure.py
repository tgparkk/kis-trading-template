# -*- coding: utf-8 -*-
"""§1 매도 레그의 «구조» — 복원·배정 없이. 사전등록 `PREREG_LEG_STRUCTURE.md`(`43b2e69`).

🔑🔑 지금까지 매도 분석은 전부 「가격 복원 → 시점 배정」이라는 **두 겹의 모호성**을 통과해야
     했고 전부 거기서 판별력을 잃었다. 레그 수익률 «그 자체»는 저자가 적은 숫자라 그 모호성이
     없고, 표본이 **7건이 아니라 33건 / 119레그**다.

라이브 트리 import 0건 (표준 라이브러리 + numpy).
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
OUT: list[str] = []
EPS = 0.05          # 🔴 PREREG_EXIT_V2 §2 에서 이미 고정한 값. 새 자유도 없음.
N_NULL = 20000
NULL_SEED = 20260815
CV_THR = 0.30
EXCLUDE = {"모나미"}   # 분할손절 — 기전이 다르다 (기존 관례)


def say(s=""):
    print(s)
    OUT.append(s)


def merge_levels(rs: list[float], eps: float = EPS) -> list[float]:
    """인접 차가 eps 이내면 «같은 차수의 분할 체결»로 보고 병합한다."""
    out = [rs[0]]
    for r in rs[1:]:
        if abs(out[-1] - r) <= eps:
            continue
        out.append(r)
    return out


def cv(x: list[float]) -> float:
    a = np.array(x, dtype=float)
    m = a.mean()
    return float(a.std(ddof=0) / m) if m > 0 else np.nan


def load_legs():
    """(종목, 프리셋, 레그수익률 리스트) — 미완결 레그는 제외."""
    legs_by_trade = {}
    for r in csv.DictReader((BASE / "ledger_legs.csv").open(encoding="utf-8")):
        key = (r["post_log_no"], r["item_no"])
        legs_by_trade.setdefault(key, []).append(r)
    out = []
    for t in csv.DictReader((BASE / "ledger_trades.csv").open(encoding="utf-8")):
        if t["stock_name"] in EXCLUDE:
            continue
        key = (t["post_log_no"], t["item_no"])
        rows = legs_by_trade.get(key, [])
        vals = []
        for r in sorted(rows, key=lambda x: int(x["leg_idx"])):
            if str(r.get("leg_open_ended", "0")) == "1":
                continue                      # 미완결 제외 (사전등록 명시)
            try:
                vals.append(float(r["ret_pct"]))
            except (TypeError, ValueError):
                continue
        if len(vals) >= 2:
            out.append((t["stock_name"], t.get("preset", ""), vals))
    return out


def main() -> int:
    trades = load_legs()
    say("# §1 매도 레그의 «구조» — 복원도 배정도 없이\n")
    say("🔑 레그 수익률은 **저자가 적은 숫자**다. 가격 복원(구간)과 시점 배정(다중해)이라는 "
        "두 겹의 모호성을 **통과하지 않는다.** 표본도 7건이 아니라 33건이다.\n")

    n_raw = sum(len(v) for _, _, v in trades)
    merged = [(nm, pr, v, merge_levels(v)) for nm, pr, v in trades]
    n_mrg = sum(len(m) for _, _, _, m in merged)
    say(f"대상 **{len(trades)}건** · 레그 **{n_raw}개**(미완결·분할손절 제외) → "
        f"병합 후 고유 레벨 **{n_mrg}개** (ε={EPS}%p)\n")
    say(f"🔑 ***{n_raw - n_mrg}개가 「같은 레벨의 분할 체결」로 흡수됐다*** "
        f"— 우리가 세던 레그 수의 **{(n_raw - n_mrg) / n_raw * 100:.1f}%**.\n")

    # ── H1 고유 레벨 수 분포 ────────────────────────────────────────────────
    from collections import Counter
    c_raw = Counter(len(v) for _, _, v, _ in merged)
    c_mrg = Counter(len(m) for _, _, _, m in merged)
    say("## H1 — 레벨 수 분포 (병합 전 / 후)\n")
    say("| 레벨 수 | 병합 전 건수 | 병합 후 건수 |")
    say("|---|---|---|")
    for k in sorted(set(c_raw) | set(c_mrg)):
        say(f"| {k} | {c_raw.get(k, 0)} | {c_mrg.get(k, 0)} |")
    say()

    # ── H2 간격 CV ──────────────────────────────────────────────────────────
    usable = [(nm, pr, m) for nm, pr, _, m in merged if len(m) >= 3]
    say(f"## H2 — 간격 CV (레벨 3개 이상인 건 **{len(usable)}**개)\n")
    if len(usable) < 5:
        say("🔴 **판정 보류** — 사전등록대로 5건 미만이면 판정하지 않는다.\n")
        obs_cv = None
    else:
        cvs = [cv([m[i] - m[i + 1] for i in range(len(m) - 1)]) for _, _, m in usable]
        obs_cv = float(np.nanmedian(cvs))
        say("| 종목 | 레벨 | 간격 | CV |")
        say("|---|---|---|---|")
        for (nm, pr, m), c in zip(usable, cvs):
            gaps = [round(m[i] - m[i + 1], 2) for i in range(len(m) - 1)]
            say(f"| {nm} | {[round(x, 2) for x in m]} | {gaps} | {c:.3f} |")
        say()
        say(f"**관측 CV 중앙값 = {obs_cv:.3f}** (기준 < {CV_THR})")
        say(f"{'✅ 균등 사다리 지지' if obs_cv < CV_THR else '❌ 기각'}\n")

    # ── H3 반증축 ───────────────────────────────────────────────────────────
    say("## H3 (반증축) — 무작위 비증가 수열도 이만큼 균등한가\n")
    if obs_cv is None:
        say("⛔ H2 보류로 생략.\n")
    else:
        rng = random.Random(NULL_SEED)
        null = []
        shapes = [(len(m), max(m), min(m)) for _, _, m in usable]
        for _ in range(N_NULL):
            cs = []
            for k, hi, lo in shapes:
                pts = sorted((rng.uniform(lo, hi) for _ in range(k)), reverse=True)
                cs.append(cv([pts[i] - pts[i + 1] for i in range(k - 1)]))
            null.append(float(np.nanmedian(cs)))
        arr = np.array(null)
        le = int((arr <= obs_cv).sum())
        pct = le / len(arr) * 100
        say(f"같은 레벨 수·같은 [min,max] 범위에서 무작위 비증가 수열 · {N_NULL:,}회 · "
            f"시드 {NULL_SEED}\n")
        say(f"- 귀무 CV 중앙값의 중앙 **{np.median(arr):.3f}** · 최소 {arr.min():.3f}")
        say(f"- 관측({obs_cv:.3f}) **이하**인 표본 **{le:,}/{len(arr):,}** ⇒ 백분위 **{pct:.1f}%**\n")
        if pct >= 5.0:
            say(f"🔴 **판별력 없음** — 백분위 {pct:.1f}% ≥ 5%. 아무 비증가 수열이나 "
                f"이만큼 균등하다 ⇒ **H2 지지를 취소한다.**")
        else:
            say(f"🟡 **귀무보다 균등하다** ({pct:.1f}% < 5%). 단 n={len(usable)} 이라 "
                "증거로 승격하지 않는다.")
        say()

        # 🔴 사후 관측 (검정 아님) — CV 분포에 눈에 띄는 «틈»이 있다.
        srt = sorted(c for c in cvs if np.isfinite(c))
        gaps = [(srt[i + 1] - srt[i], srt[i], srt[i + 1]) for i in range(len(srt) - 1)]
        g, lo_v, hi_v = max(gaps)
        n_low = sum(1 for c in srt if c <= lo_v)
        say("### 🔴 사후 관측 — CV 분포가 이봉으로 보인다 (검정 아님)\n")
        say(f"정렬한 CV 에서 가장 큰 틈은 **{lo_v:.3f} → {hi_v:.3f}** (폭 {g:.3f})이고, "
            f"그 아래에 **{n_low}건**이 몰려 있다:")
        low_names = [nm for (nm, _, _), c in zip(usable, cvs) if np.isfinite(c) and c <= lo_v]
        say(f"**{low_names}** — 이 건들의 간격은 사실상 «완전 균등»이다.\n")
        say("⚠️ **이건 결과를 본 뒤 눈에 띈 것이고, 문턱도 데이터를 보고 정했다.** "
            "지금 지지로 쓸 수 없다 ⇒ **다음 글 예측으로만 등록한다**"
            "(`PREREG_LEG_STRUCTURE.md` §3 T-D).")
        say("🔑 만약 실재한다면 *「균등 사다리를 쓰는 건」과 「그렇지 않은 건」이 섞여 있다*는 "
            "뜻이고, 그건 **프리셋이 건마다 다르다**(가설 C)와 같은 방향이다.\n")

    # ── H4 건 간 공통성 ─────────────────────────────────────────────────────
    say("## H4 — 첫 간격 `D₁` 이 건 «간에» 공통인가\n")
    for label, sel in (("전체", usable),
                       ("프리셋 명시 건만", [u for u in usable if u[1]])):
        if len(sel) < 3:
            say(f"- **{label}**: {len(sel)}건 — 표본 부족, 판정 안 함")
            continue
        d1 = [m[0] - m[1] for _, _, m in sel]
        say(f"- **{label}** ({len(sel)}건): `D₁` = {[round(x, 2) for x in d1]} · "
            f"평균 {np.mean(d1):.2f} · 표준편차 **{np.std(d1):.2f}** · CV {np.std(d1)/np.mean(d1):.2f}")
    say()
    say("🔴 **레그 순서는 저자의 «표기» 순서**다. 체결 순서라는 보장이 없다(§B 에서 못 갈랐다) "
        "⇒ `Dⱼ` 는 「가격 레벨의 간격」이지 「시간 간격」이 아니다.")
    say("🔴 **in-sample 탐색이다.** 확정 검정은 `PREREG_LEG_STRUCTURE.md` §3 의 T-A·T-B.")

    (BASE / "RESULTS_LEG_STRUCTURE.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS_LEG_STRUCTURE.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

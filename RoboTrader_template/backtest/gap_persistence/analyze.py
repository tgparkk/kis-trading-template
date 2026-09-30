"""갭 지속 조건 — 층화 비교·날짜 클러스터 부트스트랩·MDE·판정 (사전등록 `docs/prereg_2026-09-30_gap_persistence.md` §6~§8).

실행(워크트리 `RoboTrader_template/` 에서, build_events 다음):
    python -m backtest.gap_persistence.analyze

입력 = `D:/research-archive/gap_persistence_20260930/events.parquet` · DB 접속 없음.
출력 = 같은 폴더 `analysis_stdout.txt`(stdout 사본은 호출 쪽 tee) · `comparisons.csv` · `analysis_meta.json`.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

import numpy as np          # noqa: E402
import pandas as pd         # noqa: E402
from scipy.stats import norm  # noqa: E402

PREREG = ROOT / "docs" / "prereg_2026-09-30_gap_persistence.md"
OUT = Path(os.environ.get("GAP_PERSIST_OUT", "D:/research-archive/gap_persistence_20260930"))

SEED = 20260930
B = 1000
Z_A = norm.ppf(1 - 0.025)            # 1.95996
Z_P = norm.ppf(0.80)                 # 0.84162
Z_BONF = norm.ppf(1 - 0.0125 / 2)    # 2.49771
K_MDE = Z_A + Z_P                    # 2.80158
K_MDE_BONF = Z_BONF + Z_P            # 3.33933
LV_PRIMARY = 0.9875
LV_EXPL = 0.95
MIN_N1, MIN_DATES = 30, 10
OUTCOMES = ["r_oc", "r_c1", "r_c5", "r_o5", "hit"]
TAGS = [("tag1", "유상증자"), ("tag2", "CB/BW/EB"), ("tag3", "자기주식취득"), ("tag4", "공급계약"),
        ("tag5", "최대주주변경"), ("tag6", "잠정실적"), ("tag7", "소송·횡령"), ("tag_other", "기타")]


def say(*a) -> None:
    print(*a, flush=True)


def pct(x: float) -> str:
    return "  nan" if x is None or not np.isfinite(x) else f"{x * 100:+.2f}"


def compare(df: pd.DataFrame, cond: str, y: str, extra_strata: str | None = None,
            level: float = LV_EXPL) -> dict:
    """§6 날짜(또는 날짜×extra) 고정효과 차이 + 날짜 클러스터 부트스트랩 + MDE."""
    d = df[df[cond].notna() & df[y].notna()]
    cv = d[cond].to_numpy(dtype=float)
    yv = d[y].to_numpy(dtype=float)
    n1, n0 = int((cv == 1).sum()), int((cv == 0).sum())
    out = dict(cond=cond, y=y, strata="date" + (f"×{extra_strata}" if extra_strata else ""),
               level=level, n1=n1, n0=n0)
    if n1 < 2 or n0 < 2:
        out.update(beta=np.nan, verdict="판별 보류(표본 부족)", n_dates=0, n_inf_dates=0)
        return out
    y1, y0 = yv[cv == 1], yv[cv == 0]
    m1, m0 = float(y1.mean()), float(y0.mean())
    s1, s0 = float(y1.std(ddof=1)), float(y0.std(ddof=1))
    sp = float(np.sqrt(((n1 - 1) * s1 ** 2 + (n0 - 1) * s0 ** 2) / (n1 + n0 - 2)))
    se = sp * np.sqrt(1 / n1 + 1 / n0)
    mde, mde_b = K_MDE * se, K_MDE_BONF * se

    keys = ["date"] + ([extra_strata] if extra_strata else [])
    g = d.assign(_c=cv, _y=yv).groupby(keys + ["_c"])["_y"].agg(["size", "sum"]).unstack("_c", fill_value=0)
    n1s = g[("size", 1.0)].to_numpy(dtype=float) if ("size", 1.0) in g.columns else np.zeros(len(g))
    n0s = g[("size", 0.0)].to_numpy(dtype=float) if ("size", 0.0) in g.columns else np.zeros(len(g))
    s1s = g[("sum", 1.0)].to_numpy(dtype=float) if ("sum", 1.0) in g.columns else np.zeros(len(g))
    s0s = g[("sum", 0.0)].to_numpy(dtype=float) if ("sum", 0.0) in g.columns else np.zeros(len(g))
    both = (n1s > 0) & (n0s > 0)
    w = np.where(both, n1s * n0s / np.maximum(n1s + n0s, 1), 0.0)
    diff = np.where(both, s1s / np.maximum(n1s, 1) - s0s / np.maximum(n0s, 1), 0.0)
    strata_dates = g.index.get_level_values("date").to_numpy()
    dates = np.array(sorted(d["date"].unique()))
    pos = {x: i for i, x in enumerate(dates)}
    di = np.array([pos[x] for x in strata_dates])
    A = np.bincount(di, weights=w * diff, minlength=len(dates))
    W = np.bincount(di, weights=w, minlength=len(dates))
    n_inf = int((W > 0).sum())
    beta = float(A.sum() / W.sum()) if W.sum() > 0 else np.nan

    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(dates), size=(B, len(dates)))
    M = np.zeros((B, len(dates)))
    for b in range(B):
        M[b] = np.bincount(draws[b], minlength=len(dates))
    Ab, Wb = M @ A, M @ W
    ok = Wb > 0
    betas = Ab[ok] / Wb[ok]
    a = (1 - level) / 2
    lo, hi = (np.quantile(betas, [a, 1 - a]) if betas.size else (np.nan, np.nan))
    boot_se = float(betas.std(ddof=1)) if betas.size > 1 else np.nan

    if n1 < MIN_N1 or n_inf < MIN_DATES or not np.isfinite(beta):
        verdict = "판별 보류(표본 부족)"
    elif abs(beta) >= mde and (lo > 0 or hi < 0):
        verdict = "있음"
    elif lo >= -mde and hi <= mde:
        verdict = "없음"
    else:
        verdict = "판별 보류"
    out.update(m1_raw=m1, m0_raw=m0, sd_pooled=sp, se=se, mde=mde, mde_bonf=mde_b,
               beta=beta, ci_lo=float(lo), ci_hi=float(hi), boot_se=boot_se, mde_boot=K_MDE * boot_se,
               n_dates=int(len(dates)), n_inf_dates=n_inf, boot_dropped=int((~ok).sum()), verdict=verdict)
    return out


HDR = (f"{'id':6s} {'집합':10s} {'조건':6s} {'결과':5s} {'층':12s} {'n1':>6s} {'n0':>6s} {'날짜':>4s} "
       f"{'평균1':>7s} {'평균0':>7s} {'차이β':>7s} {'CI_lo':>7s} {'CI_hi':>7s} {'MDE':>6s} 판정")


def row_str(rid: str, setname: str, r: dict) -> str:
    return (f"{rid:6s} {setname:10s} {r['cond']:6s} {r['y']:5s} {r['strata']:12s} {r['n1']:6d} {r['n0']:6d} "
            f"{r.get('n_inf_dates', 0):4d} {pct(r.get('m1_raw', np.nan)):>7s} {pct(r.get('m0_raw', np.nan)):>7s} "
            f"{pct(r.get('beta', np.nan)):>7s} {pct(r.get('ci_lo', np.nan)):>7s} {pct(r.get('ci_hi', np.nan)):>7s} "
            f"{pct(r.get('mde', np.nan))[1:]:>6s} {r['verdict']}")


def main() -> None:
    t0 = time.time()
    prereg_sha = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    p_ev = OUT / "events.parquet"
    ev_sha = hashlib.sha256(p_ev.read_bytes()).hexdigest()
    ev = pd.read_parquet(p_ev)
    say("=" * 110)
    say("갭 지속 조건 — analyze")
    say(f"사전등록 sha256 = {prereg_sha}")
    say(f"입력 {p_ev} · {len(ev):,}행 · sha256 = {ev_sha}")
    say(f"시드 = default_rng({SEED}) (비교마다 새로) · 부트스트랩 B = {B} · 날짜 클러스터")
    say(f"MDE 계수 = z(0.975)+z(0.80) = {K_MDE:.4f} · Bonferroni 참고 = z(1−0.00625)+z(0.80) = {K_MDE_BONF:.4f}")
    say("단위: 수익률 = % · hit = %p · 모든 숫자 소수 2자리")

    fin = ev[ev.u4 & ev.u5 & ev.u6].copy()
    E5 = fin[fin.set == "E5"].copy()
    E3 = fin[fin.set == "E3"].copy()
    say(f"최종 이벤트: E5 = {len(E5):,} · E3 = {len(E3):,} · 창 날짜 수(E5 있는 날) = {E5.date.nunique()}")
    rows: list = []

    # ── X14 기술통계(먼저) ───────────────────────────────────────────────────────
    say("\n[X14] 기술통계 — 전체 이벤트(조건 무관)")
    say(f"  {'집합':14s} " + " ".join(f"{o + '_n':>8s} {o + '_평균':>9s} {o + '_중앙':>9s}" for o in OUTCOMES))
    for nm, s in (("E5", E5), ("E3", E3)):
        say(f"  {nm:14s} " + " ".join(
            f"{int(s[o].notna().sum()):8d} {pct(s[o].mean()):>9s} {pct(s[o].median()):>9s}" for o in OUTCOMES))
    say("  관리자 수치 대조(07-01~09-30 · U5·U6 적용 · U4 있음/없음) — r_oc 평균 · hit(종가>시가 비율):")
    q = ev[ev.u5 & ev.u6 & (ev.date >= "2026-07-01")]
    for lab, s in (("ADTV 필터 없음", q), ("ADTV 필터 있음", q[q.u4])):
        for nm in ("E5", "E3"):
            t = s[s.set == nm]
            say(f"    {lab} {nm}: n = {len(t):,} · r_oc 평균 = {pct(t.r_oc.mean())}% · hit = {t.hit.mean() * 100:.2f}%")
    say("  ADTV20 5분위별 N1 비율(E5 · N1 커버 날짜 · 진단):")
    c1 = E5[E5.N1.notna()].copy()
    c1["q5"] = pd.qcut(c1.adtv20, 5, labels=[1, 2, 3, 4, 5])
    for k, t in c1.groupby("q5", observed=True):
        say(f"    Q{k}: n = {len(t):,} · N1 = {t.N1.mean() * 100:.2f}% · N1L = {t.N1L.mean() * 100:.2f}% · "
            f"N2 = {t.N2.mean() * 100:.2f}% · ADTV 중앙 = {t.adtv20.median() / 1e8:.2f}억")
    say(f"  조건 빈도(E5): N1 커버 {int(E5.N1.notna().sum()):,} 중 N1=1 {int((E5.N1 == 1).sum()):,} · "
        f"N1b=1 {int((E5.N1b == 1).sum()):,} · N1L=1 {int((E5.N1L == 1).sum()):,} · "
        f"N2=1 {int((E5.N2 == 1).sum()):,}/{len(E5):,} · N2c=1 {int((E5.N2c == 1).sum()):,} · "
        f"N2b 커버 {int(E5.N2b.notna().sum()):,} 중 N2b=1 {int((E5.N2b == 1).sum()):,}")

    # ── §6 MDE 먼저 인쇄(주 검정 4) ──────────────────────────────────────────────
    primaries = [("P1", "N1", "r_oc"), ("P2", "N1", "r_c1"), ("P3", "N2", "r_oc"), ("P4", "N2", "r_c1")]
    say("\n[MDE — 비교 전 인쇄] 주 검정 4 · E5")
    say(f"  {'id':4s} {'조건':4s} {'결과':5s} {'n1':>6s} {'n0':>6s} {'합동SD':>7s} {'SE':>6s} {'MDE':>6s} {'MDE_bonf':>8s}")
    for pid, cnd, y in primaries:
        d = E5[E5[cnd].notna() & E5[y].notna()]
        cv, yv = d[cnd].to_numpy(), d[y].to_numpy()
        n1, n0 = int((cv == 1).sum()), int((cv == 0).sum())
        s1, s0 = yv[cv == 1].std(ddof=1), yv[cv == 0].std(ddof=1)
        sp = np.sqrt(((n1 - 1) * s1 ** 2 + (n0 - 1) * s0 ** 2) / (n1 + n0 - 2))
        se = sp * np.sqrt(1 / n1 + 1 / n0)
        say(f"  {pid:4s} {cnd:4s} {y:5s} {n1:6d} {n0:6d} {sp * 100:7.2f} {se * 100:6.2f} {K_MDE * se * 100:6.2f} "
            f"{K_MDE_BONF * se * 100:8.2f}")

    # ── §7 주 검정 ──────────────────────────────────────────────────────────────
    say("\n[주 검정] E5 · 날짜 FE · 98.75% 날짜 클러스터 부트스트랩 CI · 판정 = §7 규칙")
    say("  " + HDR)
    for pid, cnd, y in primaries:
        r = compare(E5, cnd, y, level=LV_PRIMARY)
        r.update(id=pid, set="E5", kind="주")
        rows.append(r)
        say("  " + row_str(pid, "E5", r))
        say(f"         부트스트랩 SE = {pct(r['boot_se'])[1:]} · MDE(부트 SE 기준·참고) = {pct(r['mde_boot'])[1:]} · "
            f"MDE_bonf(참고) = {pct(r['mde_bonf'])[1:]} · 버린 재표본 = {r['boot_dropped']} · 표본 날짜 = {r['n_dates']}")

    # ── §8 탐색 ─────────────────────────────────────────────────────────────────
    def ex(rid: str, setname: str, df: pd.DataFrame, cnd: str, y: str, strata: str | None = None) -> None:
        r = compare(df, cnd, y, extra_strata=strata, level=LV_EXPL)
        r.update(id=rid, set=setname, kind="탐색")
        rows.append(r)
        say("  " + row_str(rid, setname, r))

    say("\n[탐색] 95% CI · 판정 열 = 「규칙 적용(탐색)」 — 결론에 쓰지 않음")
    say("  " + HDR)
    say("  -- X1 E5 × {N1,N2} × {r_c5,r_o5,hit}")
    for cnd in ("N1", "N2"):
        for y in ("r_c5", "r_o5", "hit"):
            ex("X1", "E5", E5, cnd, y)
    say("  -- X2 E3 × {N1,N2} × 5결과")
    for cnd in ("N1", "N2"):
        for y in OUTCOMES:
            ex("X2", "E3", E3, cnd, y)
    say("  -- X3 갭 구간 × {N1,N2} × {r_oc,r_c1}")
    for gb in ("5-10", "10-20", "20+"):
        sub = E5[E5.gap_bucket == gb]
        for cnd in ("N1", "N2"):
            for y in ("r_oc", "r_c1"):
                ex("X3", f"gap{gb}", sub, cnd, y)
    say("  -- X4 E5 × N1b × 5결과")
    for y in OUTCOMES:
        ex("X4", "E5", E5, "N1b", y)
    say("  -- X5 E5 × N1L × {r_oc,r_c1}")
    for y in ("r_oc", "r_c1"):
        ex("X5", "E5", E5, "N1L", y)
    say("  -- X6 E5 × N2c × {r_oc,r_c1}")
    for y in ("r_oc", "r_c1"):
        ex("X6", "E5", E5, "N2c", y)
    say("  -- X7 E5 × 태그(vs N2=0) × {r_oc,r_c1}")
    for col, nm in TAGS:
        sub = E5[(E5[col] == 1) | (E5.N2 == 0)]
        for y in ("r_oc", "r_c1"):
            r = compare(sub, col, y, level=LV_EXPL)
            r.update(id="X7", set="E5", kind="탐색", tag=nm)
            rows.append(r)
            say("  " + row_str("X7", f"E5:{nm}"[:10], r))
    say("  -- X8 E5 × N2b × {r_oc,r_c1}")
    for y in ("r_oc", "r_c1"):
        ex("X8", "E5", E5, "N2b", y)
    say("  -- X9 E5 × N12(N1 커버 날짜) × {r_oc,r_c1}")
    E5c = E5[E5.N1.notna()].copy()
    E5c["N12"] = ((E5c.N1 == 1) | (E5c.N2 == 1)).astype(float)
    for y in ("r_oc", "r_c1"):
        ex("X9", "E5", E5c, "N12", y)
    say("  -- X10 층 = 날짜×갭구간")
    for cnd in ("N1", "N2"):
        for y in ("r_oc", "r_c1"):
            ex("X10", "E5", E5, cnd, y, strata="gap_bucket")
    say("  -- X11 층 = 날짜×ADTV3분위(E5 전체 기준 3분위)")
    E5["adtv_t3"] = pd.qcut(E5.adtv20, 3, labels=["t1", "t2", "t3"]).astype(str)
    for cnd in ("N1", "N2"):
        for y in ("r_oc", "r_c1"):
            ex("X11", "E5", E5, cnd, y, strata="adtv_t3")
    say("  -- X12 전일 수익률 부호별")
    for lab, sub in (("prev>0", E5[E5.r_prev > 0]), ("prev<=0", E5[E5.r_prev <= 0])):
        for cnd in ("N1", "N2"):
            for y in ("r_oc", "r_c1"):
                ex("X12", lab, sub, cnd, y)
    say("  -- X13 N1 기간 분할")
    for lab, sub in (("25-12~26-02", E5[E5.date <= "2026-02-28"]), ("26-08~09", E5[E5.date >= "2026-08-18"])):
        for y in ("r_oc", "r_c1"):
            ex("X13", lab, sub, "N1", y)

    # ── 예시(비나텍) ────────────────────────────────────────────────────────────
    say("\n[예시] 비나텍 126340 · 2026-09-30")
    vx = ev[(ev.stock_code == "126340") & (ev.date == "2026-09-30")]
    cols = ["stock_code", "date", "close_prev", "open", "close", "gap", "r_oc", "r_c1", "r_c5", "hit",
            "adtv20", "u4", "u5", "u6", "N1", "N1b", "N1L", "n1_articles", "N2", "N2c", "N2b"]
    say(vx[cols].to_string(index=False))
    same = E5[E5.date == "2026-09-30"]
    say(f"  같은 날 E5 이벤트 = {len(same)} (평균 r_oc = {pct(same.r_oc.mean())}% · hit = {same.hit.mean() * 100:.2f}%)")
    for lab, m in (("N1=0 ∧ N2=0", (same.N1 == 0) & (same.N2 == 0)), ("N1=1", same.N1 == 1),
                   ("N2=1", same.N2 == 1), ("N1=1 ∨ N2=1", (same.N1 == 1) | (same.N2 == 1))):
        t = same[m]
        say(f"    {lab:12s}: n = {len(t):3d} · 평균 r_oc = {pct(t.r_oc.mean())}% · 중앙 r_oc = {pct(t.r_oc.median())}% "
            f"· hit = {(t.hit.mean() * 100 if len(t) else float('nan')):.2f}%")
    t = same.sort_values("gap", ascending=False)[["stock_code", "gap", "r_oc", "N1", "N1L", "N2"]].head(12)
    say("  같은 날 E5 상위 12(갭 순):")
    say("  " + t.assign(gap=(t.gap * 100).round(2), r_oc=(t.r_oc * 100).round(2)).to_string(index=False)
        .replace("\n", "\n  "))

    # ── 저장 ────────────────────────────────────────────────────────────────────
    cmp = pd.DataFrame(rows)
    p_cmp = OUT / "comparisons.csv"
    cmp.to_csv(p_cmp, index=False, encoding="utf-8-sig")
    meta = dict(prereg_sha256=prereg_sha, events_sha256=ev_sha, seed=SEED, B=B, K_MDE=K_MDE,
                K_MDE_BONF=K_MDE_BONF, n_E5=int(len(E5)), n_E3=int(len(E3)), n_comparisons=int(len(cmp)),
                elapsed_sec=round(time.time() - t0, 1))
    (OUT / "analysis_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"\n출력: {p_cmp} ({len(cmp)}행) · {OUT / 'analysis_meta.json'}")
    say(f"실행 시간 = {meta['elapsed_sec']}초")


if __name__ == "__main__":
    main()

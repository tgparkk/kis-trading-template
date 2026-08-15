# -*- coding: utf-8 -*-
"""손절폭 vs 봉폭 게이트 — 2단계: 결과 계산 (§5~§7, PnL 필요).

사전등록: `PREREG.md`(동결 §0~§9 `7652c99` + §10 개정 `32d6a37`). 1단계 산출: `GATE.md`(`c083a2c`).
이 스크립트는 `run_gate.py.compute_gate_data()`(1단계 게이트 산출)를 **import** 해서 재사용한다
(복붙 금지 — 작업지시서). PnL(`profit_rate`)·청산사유(`reason`)는 이 스크립트에서 «처음» 조회한다.

🔴 K=0.5·N=20·ε1-min=0.21%p·ε1-econ=1.48%p·퇴화문턱=1/3·카운트문턱=[30,403)·시드=20260816 —
   전부 `run_gate.py` 의 동결 상수를 그대로 참조한다. 이 파일에서 재정의하지 않는다.

난수 draw 순서(시드 `numpy.random.default_rng(20260816)` 하나를 끝까지 순차 소비, arm 간·
용도 간 겹침 없음) — 아래 순서 그대로:
  1) arm-A 전체표본 N0-simple 20회 → 2) arm-A 전체표본 N0-strat 20회
  3) arm-B 전체표본 N0-simple 20회 → 4) arm-B 전체표본 N0-strat 20회
  5) arm-A G4(book_pullback_ma5) N0-simple 20회 → 6) arm-A G4(ma5) N0-strat 20회
  7) arm-B G4(ma5) N0-simple 20회 → 8) arm-B G4(ma5) N0-strat 20회
  (daytrading_3methods_breakout 은 두 arm 모두 G4 하한 10 미달 — draw 소비 없이 스킵)

라이브 트리 import 0건 · DB 는 SELECT 만 · `utils/logger.py` 미사용.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from run_gate import (  # noqa: E402
    DSN, WINDOW, K, N_MAIN, N_EXCLUDED_LOW, N_EXCLUDED_HIGH, DEGENERATE_THRESHOLD,
    G4_MIN_EXCLUDED, G4_STRATEGIES, STRATEGY_FOLDERS, compute_gate_data,
)

SEED = 20260816
N_REPS = 20
EPS1_MIN = 0.0021    # 0.21%p (PREREG §6 G1 — 왕복비용, pnl_decomposition §① FEE)
EPS1_ECON = 0.0148   # 1.48%p (PREREG §6 G1 — 손익분기 복원폭, pnl_decomposition §① 기대값)
FEE = 0.0021         # net = gross − 0.21%p (§8-6, 부수 인쇄용)

OUT: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    OUT.append(s)


# ─────────────────────────────────────────────────────────────────────────
# PnL 조회 — 이 스크립트가 «처음» 하는 조회. run_gate.py 는 절대 PnL 을 안 봤다.
# ─────────────────────────────────────────────────────────────────────────

def load_pnl(conn) -> pd.DataFrame:
    """SELL 행의 `profit_rate`(gross)·`reason`. `buy_record_id` 로 BUY id 에 연결.

    🔑 날짜 필터를 걸지 않는다 — `run_gate.py.load_closed_buy_ids()` 와 «같은 모집단 정의»를
    쓰기 위함이다(그 함수도 SELL 을 날짜로 안 거른다. 매수는 창 안이지만 매도는 창 밖일 수 있어서
    ─ 실측: 604건, buys 의 `is_closed` 합계와 정확히 일치, 아래 assert 로 확인).
    """
    df = pd.read_sql("""
        SELECT buy_record_id AS id, profit_rate, reason
        FROM virtual_trading_records
        WHERE action = 'SELL' AND buy_record_id IS NOT NULL
    """, conn)
    df["profit_rate"] = pd.to_numeric(df["profit_rate"], errors="coerce")
    return df


def classify_reason(r) -> str:
    """`pnl_decomposition/decompose.py` 의 `cat0` 과 동일 규칙(재현 위해 그대로 복제).

    646건 중 미청산 42건은 `reason` 이 NaN(float) — 이 함수는 604 청산건에만 적용하지만,
    방어적으로 NaN/None 도 안전하게 처리한다.
    """
    if r is None or (isinstance(r, float) and np.isnan(r)):
        r = ""
    for k, v in (("손절", "손절"), ("목표 익절", "익절"), ("보유기간", "보유기간"),
                 ("트레일", "트레일링"), ("추적", "트레일링")):
        if r.startswith(k) or k in r:
            return v
    return "기타"


# ─────────────────────────────────────────────────────────────────────────
# 귀무 — N0-simple · N0-strat (§5)
# ─────────────────────────────────────────────────────────────────────────

def n0_simple_reps(rng: np.random.Generator, df: pd.DataFrame, n_excluded: int,
                    n_reps: int = N_REPS) -> list:
    """604(또는 부분모집단)에서 무작위 n_excluded 건 제거 → 남은 건 평균(gross). n_reps 회.

    각 반복이 rng 의 «한 draw»(rng.choice 1회 호출)를 소비한다.
    """
    idx_all = df.index.to_numpy()
    means = []
    for _ in range(n_reps):
        chosen = rng.choice(idx_all, size=n_excluded, replace=False)
        mask = ~df.index.isin(chosen)
        means.append(float(df.loc[mask, "profit_rate"].mean()))
    return means


def n0_strat_reps(rng: np.random.Generator, df: pd.DataFrame, k_by_day: dict,
                   n_reps: int = N_REPS) -> list:
    """매수일 층화 귀무(§5-2). 날짜별로 그날의 실제 배제건수 `k_d` 와 «같은 수»를 그날 안에서
    무작위 제거 — 모든 날짜에 동시 적용해 만든 한 반복.

    반환: [(kept_mean, diff_j), ...] — `diff_j` = 그 반복의 무작위 배제집합이 만드는
    `excluded_rate_stop_j − excluded_rate_profit_j`(G3 의 ε3 유도용, §6 G3). `df` 는
    `buy_date`·`profit_rate`·`cat`(손절/익절/그외) 컬럼을 가져야 한다.
    """
    n_stop_total = int((df["cat"] == "손절").sum())
    n_profit_total = int((df["cat"] == "익절").sum())
    # 날짜별 인덱스(그룹 순회 순서 고정 — groupby 는 날짜 오름차순 정렬).
    day_idx = {d: g.index.to_numpy() for d, g in df.groupby("buy_date")}
    out = []
    for _ in range(n_reps):
        excluded_idx = []
        for d, idx in day_idx.items():
            k_d = int(k_by_day.get(d, 0))
            if k_d <= 0:
                continue
            chosen = rng.choice(idx, size=k_d, replace=False)
            excluded_idx.extend(chosen.tolist())
        excluded_mask = df.index.isin(excluded_idx)
        kept_mean = float(df.loc[~excluded_mask, "profit_rate"].mean())
        exc_stop = int((excluded_mask & (df["cat"] == "손절").to_numpy()).sum())
        exc_profit = int((excluded_mask & (df["cat"] == "익절").to_numpy()).sum())
        rate_stop = exc_stop / n_stop_total if n_stop_total > 0 else float("nan")
        rate_profit = exc_profit / n_profit_total if n_profit_total > 0 else float("nan")
        out.append((kept_mean, rate_stop - rate_profit))
    return out


def rank_p(observed: float, reps: list) -> tuple:
    """정확한 순위 기반 p(양측·상측·하측) — n=21(reps 20 + observed 1)의 순열분포."""
    combined = np.array(list(reps) + [observed], dtype=float)
    n = len(combined)
    p_upper = float((combined >= observed).sum()) / n
    p_lower = float((combined <= observed).sum()) / n
    p_two = min(1.0, 2 * min(p_upper, p_lower))
    return p_upper, p_lower, p_two


def g2_verdict(observed: float, reps: list) -> str:
    lo, hi = min(reps), max(reps)
    if observed > hi:
        return "info_good"
    if observed < lo:
        return "info_bad"
    return "indistinct"


def g1_bucket(diff: float) -> str:
    if diff >= EPS1_ECON:
        return "strong_plus"
    if diff >= EPS1_MIN:
        return "plus"
    if diff <= -EPS1_MIN:
        return "minus"
    return "neutral"


def g3_verdict(real_diff: float, eps3: float) -> str:
    if real_diff >= eps3:
        return "비대칭"
    if real_diff <= -eps3:
        return "역비대칭"
    return "비례"


def assess_label(g1b: str, g2s: str, g2t: str, g3: str) -> str:
    """§7 판정표를 «기계적으로» 적용. g2t 는 「info_good」·「info_bad」·「indistinct」·「판별불가」
    (카운트문턱 또는 퇴화일문턱 위반). g3 는 g2t 가 유효할 때만 뜻이 있다(§6 G3 조건부).
    """
    # (나) 첫 disjunct — G2-strat/G3 에 의존하지 않는다(§7 "G1+ 인데 G2-simple 부터 구별 안 됨").
    if g1b in ("strong_plus", "plus") and g2s == "indistinct":
        return "(나) 게이트는 포지션 축소일 뿐"

    if g2t == "판별불가":
        return "판별 불가 (G2-strat 무효 — 강한(가)/(가)/날짜효과/게이트해롭다-strat조건/G3필요라벨 불가)"

    if g1b == "strong_plus" and g2s == "info_good" and g2t == "info_good" and g3 == "비대칭":
        return "강한 (가)"
    if g1b == "plus" and g2s == "info_good" and g2t == "info_good" and g3 == "비대칭":
        return "(가)"
    if g1b in ("strong_plus", "plus") and g2s == "info_good" and g2t == "indistinct":
        return "날짜 효과이지 종목 선택 효과가 아님"
    if g1b in ("strong_plus", "plus") and g2s == "info_good" and g2t == "info_good" and g3 == "비례":
        return "(나) 게이트는 포지션 축소일 뿐"
    if g1b == "minus" and g2s == "info_bad" and g2t == "info_bad":
        return "게이트가 해롭다" + (" (역선택 정황 — G3 역비대칭)" if g3 == "역비대칭" else "")
    return "판별 불가"


# ─────────────────────────────────────────────────────────────────────────
# 한 표본(전체 604 또는 전략 부분집합)에 대한 G1~G3 전체 계산
# ─────────────────────────────────────────────────────────────────────────

def run_g1g3(rng, df604: pd.DataFrame, excluded_col: str, label: str):
    """`df604` = 604(또는 부분집합) closed 표본, `profit_rate`·`buy_date`·`cat`·`excluded_col` 포함.

    반환: dict — mu_full · mu_gate · n_excluded · G1 · G2-simple · G2-strat(+degenerate 정보) · G3 ·
    N0 분포(최댓값·최솟값·중앙값) · rank p · 라벨.
    """
    n_total = len(df604)
    n_excluded = int(df604[excluded_col].sum())
    mu_full = float(df604["profit_rate"].mean())
    kept = df604[~df604[excluded_col]]
    mu_gate = float(kept["profit_rate"].mean()) if len(kept) else float("nan")

    # 카운트 문턱(§6 G2 / §8-3) — 1차.
    count_ok = N_EXCLUDED_LOW <= n_excluded < N_EXCLUDED_HIGH

    # 날짜별 (n_d, k_d) — 퇴화일(§5-2).
    by_day = df604.groupby("buy_date").agg(
        n_d=(excluded_col, "size"), k_d=(excluded_col, "sum")
    ).reset_index()
    by_day["k_d"] = by_day["k_d"].astype(int)
    by_day["degenerate"] = by_day["k_d"] == by_day["n_d"]
    degenerate_excluded = int(by_day.loc[by_day["degenerate"], "k_d"].sum())
    degenerate_share = degenerate_excluded / n_excluded if n_excluded > 0 else float("nan")
    degenerate_ok = count_ok and n_excluded > 0 and degenerate_share < DEGENERATE_THRESHOLD

    k_by_day = dict(zip(by_day["buy_date"], by_day["k_d"]))

    # N0-simple / N0-strat — 카운트문턱을 벗어나도(§8-3 순서) 투명성 위해 계산은 그대로 한다.
    simple_reps = n0_simple_reps(rng, df604, n_excluded) if n_excluded > 0 else [mu_full] * N_REPS
    strat_pairs = n0_strat_reps(rng, df604, k_by_day) if n_excluded > 0 else [(mu_full, 0.0)] * N_REPS
    strat_reps = [p[0] for p in strat_pairs]
    diff_reps = [p[1] for p in strat_pairs]

    g1_diff = mu_gate - mu_full
    g1b = g1_bucket(g1_diff)

    if count_ok:
        g2s = g2_verdict(mu_gate, simple_reps)
        g2t_raw = g2_verdict(mu_gate, strat_reps)
        g2t = g2t_raw if degenerate_ok else "판별불가"
    else:
        g2s = "판별불가(카운트문턱)"
        g2t = "판별불가"

    p_up_s, p_lo_s, p_two_s = rank_p(mu_gate, simple_reps)
    p_up_t, p_lo_t, p_two_t = rank_p(mu_gate, strat_reps)

    # G3 — ε3 는 strat 20회의 max|diff_j|. G2-strat 이 유효할 때만 §7 판정에 쓴다(계산은 항상).
    eps3 = float(np.max(np.abs(diff_reps))) if diff_reps else float("nan")
    cat_stop = df604["cat"] == "손절"
    cat_profit = df604["cat"] == "익절"
    n_stop_total = int(cat_stop.sum())
    n_profit_total = int(cat_profit.sum())
    real_exc_stop = int((df604[excluded_col] & cat_stop).sum())
    real_exc_profit = int((df604[excluded_col] & cat_profit).sum())
    real_rate_stop = real_exc_stop / n_stop_total if n_stop_total > 0 else float("nan")
    real_rate_profit = real_exc_profit / n_profit_total if n_profit_total > 0 else float("nan")
    real_diff = real_rate_stop - real_rate_profit
    g3 = g3_verdict(real_diff, eps3) if (degenerate_ok and not np.isnan(eps3)) else None

    label_verdict = assess_label(g1b, g2s if count_ok else "판별불가", g2t, g3 or "")

    return dict(
        label=label, n_total=n_total, n_excluded=n_excluded, mu_full=mu_full, mu_gate=mu_gate,
        count_ok=count_ok, degenerate_excluded=degenerate_excluded, degenerate_share=degenerate_share,
        degenerate_ok=degenerate_ok, simple_reps=simple_reps, strat_reps=strat_reps,
        diff_reps=diff_reps, g1_diff=g1_diff, g1_bucket=g1b, g2_simple=g2s, g2_strat=g2t,
        p_up_s=p_up_s, p_lo_s=p_lo_s, p_two_s=p_two_s, p_up_t=p_up_t, p_lo_t=p_lo_t, p_two_t=p_two_t,
        eps3=eps3, real_diff=real_diff, real_rate_stop=real_rate_stop, real_rate_profit=real_rate_profit,
        n_stop_total=n_stop_total, n_profit_total=n_profit_total, g3=g3, verdict=label_verdict,
        by_day=by_day,
    )


# ─────────────────────────────────────────────────────────────────────────
# 리포트 렌더링
# ─────────────────────────────────────────────────────────────────────────

def fmt_pct(x: float) -> str:
    return f"{x*100:+.2f}%" if not (x is None or (isinstance(x, float) and np.isnan(x))) else "—"


def fmt_pp(x: float) -> str:
    return f"{x*100:+.2f}%p" if not (x is None or (isinstance(x, float) and np.isnan(x))) else "—"


def render_result(res: dict, arm_label: str, scope_label: str) -> None:
    r = res
    say(f"### {arm_label} · {scope_label} — 판정: **{r['verdict']}**\n")
    say("| 항목 | 값 |")
    say("|---|---|")
    say(f"| n / n_excluded | {r['n_total']} / {r['n_excluded']} (배제율 {r['n_excluded']/r['n_total']*100:.1f}%) |")
    say(f"| 카운트문턱 [30,403) | {'통과' if r['count_ok'] else '❌ 위반 → 자동 판별불가'} |")
    if r["n_excluded"] > 0:
        say(f"| 퇴화일 배제건수/비중 | {r['degenerate_excluded']} / {r['n_excluded']} = "
            f"{r['degenerate_share']*100:.1f}% |")
        say(f"| 퇴화일 1/3 문턱(G2-strat 2차) | {'통과' if r['degenerate_ok'] else '❌ 위반 → G2-strat 판별불가'} |")
    say(f"| `μ_full` | **{fmt_pct(r['mu_full'])}** |")
    say(f"| `μ_gate` | **{fmt_pct(r['mu_gate'])}** |")
    say(f"| **G1**: μ_gate−μ_full | **{fmt_pp(r['g1_diff'])}** → `{r['g1_bucket']}`"
        f"(ε1-min=±0.21%p·ε1-econ=+1.48%p) |")
    say(f"| **G2-simple** | μ_gate vs N0-simple 20회[최소 {fmt_pct(min(r['simple_reps']))} · "
        f"중앙 {fmt_pct(float(np.median(r['simple_reps'])))} · 최대 {fmt_pct(max(r['simple_reps']))}] → "
        f"**{r['g2_simple']}** (순위p 상측={r['p_up_s']:.4f}·하측={r['p_lo_s']:.4f}·양측={r['p_two_s']:.4f}) |")
    say(f"| **G2-strat** | μ_gate vs N0-strat 20회[최소 {fmt_pct(min(r['strat_reps']))} · "
        f"중앙 {fmt_pct(float(np.median(r['strat_reps'])))} · 최대 {fmt_pct(max(r['strat_reps']))}] → "
        f"**{r['g2_strat']}** (순위p 상측={r['p_up_t']:.4f}·하측={r['p_lo_t']:.4f}·양측={r['p_two_t']:.4f}) |")
    say(f"| **G3**: real_diff | **{fmt_pp(r['real_diff'])}** "
        f"({r['real_rate_stop']*100:.1f}%(n={r['n_stop_total']}) − {r['real_rate_profit']*100:.1f}%"
        f"(n={r['n_profit_total']})) |")
    say(f"| **G3**: ε3(N0-strat max\\|diff_j\\|) | **{fmt_pp(r['eps3'])}** |")
    say(f"| **G3** 라벨 | {'`' + r['g3'] + '`' if r['g3'] else '(G2-strat 무효 — 참고만, §7 판정 미사용)'} |")
    say()


def strategy_exclusion_diag(closed_df: pd.DataFrame, stop_loss_pct: dict, excluded_col: str) -> pd.DataFrame:
    """arm-A 배제 97건(또는 arm-B 상당분)이 «어느 전략에» 쏠렸는지 — 코디네이터 진단(2026-08-16)의
    근거표. 선언 손절폭(분자)이 전략마다 다르면 비율 게이트가 종목이 아니라 전략을 고를 수 있다는
    가설을 세우기 위해, PnL 없이도 1단계(`GATE.md` §7/§10-7)에서 이미 볼 수 있던 배제 쏠림을
    이 스크립트가 다시 계산하고 실제 수익률과 나란히 인쇄한다. **판정 라벨에는 쓰지 않는다** —
    §7 은 604 전체표본 기준으로 이미 확정됐고, 이 표는 그 «기전»을 설명하는 사후 기술통계다.
    """
    rows = []
    total_excl = int(closed_df[excluded_col].sum())
    for strat in STRATEGY_FOLDERS:
        g = closed_df[closed_df["strategy"] == strat]
        n_excl = int(g[excluded_col].sum())
        rmed = g["range_med_20"].dropna()
        rows.append(dict(
            strategy=strat, declared_sl=stop_loss_pct[strat], n=len(g), n_excl=n_excl,
            share_of_total_excl=(n_excl / total_excl if total_excl > 0 else float("nan")),
            mean_ret=float(g["profit_rate"].mean()) if len(g) else float("nan"),
            range_med_median=float(rmed.median()) if len(rmed) else float("nan"),
            implied_threshold=2 * stop_loss_pct[strat],  # gate_pass ⟺ range_med ≤ declared_sl/K = 2×declared_sl
        ))
    out = pd.DataFrame(rows).sort_values("n_excl", ascending=False).reset_index(drop=True)
    return out


def render_strategy_diag(diag: pd.DataFrame, arm_label: str) -> None:
    say(f"| 전략 | 선언 손절폭 | {arm_label} 배제(604 기준) | 배제 중 비중 | 그 전략 평균 실현(gross) |")
    say("|---|---|---|---|---|")
    for r in diag.itertuples(index=False):
        say(f"| `{r.strategy}` | {r.declared_sl:.0%} | {r.n_excl} | "
            f"{r.share_of_total_excl*100:.0f}% | {fmt_pct(r.mean_ret)} |")
    say()


def render_numerator_denominator_diag(diag: pd.DataFrame) -> None:
    """분자(선언손절폭) 효과인지 분모(그 전략이 사는 종목의 변동성) 효과인지 분해 — «과대해석」
    자기점검용. gate_pass ⟺ range_med_20 ≤ 2×declared_sl(=문턱) 이므로, 전략별 range_med_20
    «중앙값»을 그 전략의 문턱과 나란히 놓으면 «분자가 낮아서」인지 「분모(변동성)가 높아서」인지
    갈린다.
    """
    say("| 전략 | 선언 손절폭 | 문턱(=2×선언손절폭) | 그 전략이 산 종목의 `range_med_20` 중앙값 | 문턱 대비 |")
    say("|---|---|---|---|---|")
    for r in diag.sort_values("declared_sl").itertuples(index=False):
        rel = "문턱 «아래»(대부분 통과)" if r.range_med_median <= r.implied_threshold else "문턱 «위»(대부분 배제)"
        say(f"| `{r.strategy}` | {r.declared_sl:.0%} | {r.implied_threshold*100:.1f}% | "
            f"{r.range_med_median*100:.2f}% | {rel} |")
    say()


def render_dist_table(r: dict, arm_label: str, scope_label: str) -> None:
    """귀무 20회 분포 — 반복별 원값을 «숫자로» 전부 인쇄(§9 조용히 안 뺀다)."""
    say(f"<details><summary>{arm_label} · {scope_label} — N0 20회 원값(펼치기)</summary>\n")
    say("| j | μ_rand,simple,j | μ_rand,strat,j | diff_j(strat, G3 유도용) |")
    say("|---|---|---|---|")
    for j in range(N_REPS):
        say(f"| {j+1} | {fmt_pct(r['simple_reps'][j])} | {fmt_pct(r['strat_reps'][j])} | "
            f"{fmt_pp(r['diff_reps'][j])} |")
    say(f"| **최소** | {fmt_pct(min(r['simple_reps']))} | {fmt_pct(min(r['strat_reps']))} | "
        f"{fmt_pp(min(r['diff_reps']))} |")
    say(f"| **중앙** | {fmt_pct(float(np.median(r['simple_reps'])))} | "
        f"{fmt_pct(float(np.median(r['strat_reps'])))} | {fmt_pp(float(np.median(r['diff_reps'])))} |")
    say(f"| **최대** | {fmt_pct(max(r['simple_reps']))} | {fmt_pct(max(r['strat_reps']))} | "
        f"{fmt_pp(max(r['diff_reps']))} |")
    say(f"| **max\\|diff_j\\|(=ε3)** | — | — | {fmt_pp(r['eps3'])} |")
    say("\n</details>\n")


def main() -> int:
    conn = psycopg2.connect(**DSN)
    buys, sens_excluded, nw_df, stop_loss_pct = compute_gate_data(conn)
    pnl = load_pnl(conn)
    conn.close()

    n_closed_pnl = int(pnl["id"].nunique())
    buys = buys.merge(pnl, on="id", how="left")
    n_profit_notna = int(buys["profit_rate"].notna().sum())
    n_closed_flag = int(buys["is_closed"].sum())
    assert n_closed_pnl == 604, f"PnL SELL 연결 604건이어야 함 — 실측 {n_closed_pnl}"
    assert n_profit_notna == n_closed_flag == 604, (
        f"청산 604건 정합성 불일치 — profit_rate notna={n_profit_notna}, "
        f"is_closed={n_closed_flag} (run_gate.py 의 closed_ids 와 이 스크립트의 load_pnl 은 "
        f"둘 다 buy_record_id 존재 여부만으로 604를 정의 — 같은 쿼리 구조라 반드시 일치해야 함)"
    )
    buys["cat"] = buys["reason"].map(classify_reason)

    closed = buys[buys["is_closed"]].copy().reset_index(drop=True)
    assert len(closed) == 604

    rng = np.random.default_rng(SEED)

    # ── 먼저 전부 계산(draw 순서는 모듈 docstring에 고정) ─────────────────
    res_a = run_g1g3(rng, closed, "excluded", "arm-A")                      # draw 1-40
    res_b = run_g1g3(rng, closed, "excluded_B", "arm-B")                    # draw 41-80
    sub_ma5 = closed[closed["strategy"] == "book_pullback_ma5"].copy().reset_index(drop=True)
    sub_day = closed[closed["strategy"] == "daytrading_3methods_breakout"].copy().reset_index(drop=True)
    n_ma5_a, n_ma5_b = int(sub_ma5["excluded"].sum()), int(sub_ma5["excluded_B"].sum())
    n_day_a, n_day_b = int(sub_day["excluded"].sum()), int(sub_day["excluded_B"].sum())
    g4_ma5_a = run_g1g3(rng, sub_ma5, "excluded", "arm-A/ma5") if n_ma5_a >= G4_MIN_EXCLUDED else None   # draw 81-120
    g4_ma5_b = run_g1g3(rng, sub_ma5, "excluded_B", "arm-B/ma5") if n_ma5_b >= G4_MIN_EXCLUDED else None  # draw 121-160
    # daytrading: 두 arm 모두 n_excluded < 10 → 계산·draw 소비 없음(검정력 부족만 보고)

    def label_word(v: str) -> str:
        for key in ("강한 (가)", "(가)", "날짜 효과", "(나)", "게이트가 해롭다", "판별 불가"):
            if v.startswith(key):
                return key
        return v

    title = (f"# 판정 — arm-A: {label_word(res_a['verdict'])}(귀무 대비 유의) · "
             f"arm-B: {label_word(res_b['verdict'])}\n")
    say(title)
    say("사전등록 [`PREREG.md`](PREREG.md) 동결(`7652c99`) + §10 개정(`32d6a37`) 실행. "
        "1단계 게이트 산출: [`GATE.md`](GATE.md)(`c083a2c`). "
        "🔴 **문턱·창·시드를 갈지 않았다** — K=0.5·N=20거래일·시드=20260816·ε1-min=0.21%p·"
        "ε1-econ=1.48%p·퇴화문턱=1/3·카운트문턱=[30,403)·G4 하한=10 전부 사전등록·`run_gate.py` "
        "상수 그대로. 이 문서는 `run_results.py` 를 재실행하면 그대로 재생성된다(재현 게이트).\n")
    say(f"매수 646건 · 청산완료(PnL 연결) **{len(closed)}**건 — `buy_record_id` 존재만으로 식별했고 "
        f"(1단계 `GATE.md` 의 `closed_ids` 정의와 «독립적으로» 재조회) 둘 다 정확히 604로 일치했다. "
        "청산사유: " + ", ".join(f"{c} {n}" for c, n in closed['cat'].value_counts().items()) + ".\n")

    # ── §3-3 결측 건 평균 수익률 ─────────────────────────────────────────
    say("## 0. 결측 건 평균 수익률 (§3-3, 1단계에서 「2단계 몫」으로 미뤄둔 것)\n")
    missing_a = closed[closed["range_med_20"].isna()]
    say(f"- arm-A(`range_med_20` 결측, 604 기준): **{len(missing_a)}건**"
        + (f" — 평균 수익률 {fmt_pct(missing_a['profit_rate'].mean())}" if len(missing_a) else ""))
    missing_b = closed[closed["stop_loss_missing"]]
    say(f"- arm-B(`stop_loss_rate` 결측, 604 기준): **{len(missing_b)}건**"
        + (f" — 평균 수익률 {fmt_pct(missing_b['profit_rate'].mean())}" if len(missing_b) else ""))
    say()

    # ── arm-A / arm-B 전체표본 ──────────────────────────────────────────
    say("## 1. arm-A(1차 판정) — 전체표본(604건)\n")
    render_result(res_a, "arm-A", "전체표본(604)")
    render_dist_table(res_a, "arm-A", "전체표본(604)")

    say("## 2. arm-B(병기) — 전체표본(604건)\n")
    render_result(res_b, "arm-B", "전체표본(604)")
    render_dist_table(res_b, "arm-B", "전체표본(604)")

    # ── G4 ──────────────────────────────────────────────────────────────
    say("## 3. G4 — 전략별 부수 재계산 (하한 n_excluded≥10, §6 G4)\n")
    say(f"### `book_pullback_ma5` (n={len(sub_ma5)})\n")
    say(f"- arm-A n_excluded={n_ma5_a} — " + ("하한(10) 충족" if n_ma5_a >= G4_MIN_EXCLUDED else "❌ 미달 → 검정력 부족"))
    say(f"- arm-B n_excluded={n_ma5_b} — " + ("하한(10) 충족" if n_ma5_b >= G4_MIN_EXCLUDED else "❌ 미달 → 검정력 부족"))
    say()
    if g4_ma5_a is not None:
        render_result(g4_ma5_a, "arm-A", "G4/book_pullback_ma5")
        render_dist_table(g4_ma5_a, "arm-A", "G4/book_pullback_ma5")
    if g4_ma5_b is not None:
        render_result(g4_ma5_b, "arm-B", "G4/book_pullback_ma5")
        render_dist_table(g4_ma5_b, "arm-B", "G4/book_pullback_ma5")

    say(f"### `daytrading_3methods_breakout` (n={len(sub_day)})\n")
    say(f"- arm-A n_excluded={n_day_a} — ❌ 미달(<10) → **검정력 부족, G1~G3 계산 생략**(§6 G4 하한)")
    say(f"- arm-B n_excluded={n_day_b} — ❌ 미달(<10) → **검정력 부족, G1~G3 계산 생략**(§6 G4 하한)\n")

    # ── net 부수 ────────────────────────────────────────────────────────
    say("## 4. net 부수 (gross − 0.21%p, §8-6 — 주 지표는 gross)\n")
    say("| 표본 | arm | μ_full(gross) | μ_full(net) | μ_gate(gross) | μ_gate(net) |")
    say("|---|---|---|---|---|---|")
    say(f"| 전체표본 | A | {fmt_pct(res_a['mu_full'])} | {fmt_pct(res_a['mu_full']-FEE)} | "
        f"{fmt_pct(res_a['mu_gate'])} | {fmt_pct(res_a['mu_gate']-FEE)} |")
    say(f"| 전체표본 | B | {fmt_pct(res_b['mu_full'])} | {fmt_pct(res_b['mu_full']-FEE)} | "
        f"{fmt_pct(res_b['mu_gate'])} | {fmt_pct(res_b['mu_gate']-FEE)} |")
    if g4_ma5_a is not None:
        say(f"| ma5 | A | {fmt_pct(g4_ma5_a['mu_full'])} | {fmt_pct(g4_ma5_a['mu_full']-FEE)} | "
            f"{fmt_pct(g4_ma5_a['mu_gate'])} | {fmt_pct(g4_ma5_a['mu_gate']-FEE)} |")
    if g4_ma5_b is not None:
        say(f"| ma5 | B | {fmt_pct(g4_ma5_b['mu_full'])} | {fmt_pct(g4_ma5_b['mu_full']-FEE)} | "
            f"{fmt_pct(g4_ma5_b['mu_gate'])} | {fmt_pct(g4_ma5_b['mu_gate']-FEE)} |")
    say()

    # ── 최종 요약표 ─────────────────────────────────────────────────────
    say("## 5. 최종 판정 요약\n")
    say("| 표본 | arm | n_excluded | G1 | G2-simple | G2-strat | G3 | §7 판정 |")
    say("|---|---|---|---|---|---|---|---|")
    say(f"| 전체(604) | **A(1차)** | {res_a['n_excluded']} | {fmt_pp(res_a['g1_diff'])} | "
        f"{res_a['g2_simple']} | {res_a['g2_strat']} | {res_a['g3'] or '—'} | **{res_a['verdict']}** |")
    say(f"| 전체(604) | B(병기) | {res_b['n_excluded']} | {fmt_pp(res_b['g1_diff'])} | "
        f"{res_b['g2_simple']} | {res_b['g2_strat']} | {res_b['g3'] or '—'} | **{res_b['verdict']}** |")
    if g4_ma5_a is not None:
        say(f"| G4/ma5 | A | {g4_ma5_a['n_excluded']} | {fmt_pp(g4_ma5_a['g1_diff'])} | "
            f"{g4_ma5_a['g2_simple']} | {g4_ma5_a['g2_strat']} | {g4_ma5_a['g3'] or '—'} | **{g4_ma5_a['verdict']}** |")
    if g4_ma5_b is not None:
        say(f"| G4/ma5 | B | {g4_ma5_b['n_excluded']} | {fmt_pp(g4_ma5_b['g1_diff'])} | "
            f"{g4_ma5_b['g2_simple']} | {g4_ma5_b['g2_strat']} | {g4_ma5_b['g3'] or '—'} | **{g4_ma5_b['verdict']}** |")
    say(f"| G4/daytrading | A | {n_day_a} | — | — | — | — | 검정력 부족(n_excluded<10) |")
    say(f"| G4/daytrading | B | {n_day_b} | — | — | — | — | 검정력 부족(n_excluded<10) |")
    say()

    # ── 🏁 해석 ─────────────────────────────────────────────────────────
    say("## 🏁 해석\n")
    say(f"🔴 **arm-A(1차 판정) = 「{res_a['verdict']}」** — 사전등록 §7 판정표를 기계적으로 적용한 결과다. "
        "이건 §2 가설 (가)/(나) 어느 쪽도 아니다 — §7 이 별도로 마련해 둔 **대칭 라벨**("
        "「게이트가 해롭다」, (가)와 정확히 대칭인 조건: G1−·G2-simple 해로움·G2-strat 해로움, "
        "귀무 대비 «유의하게 나쁘다»)이 기계적으로 걸렸다. **결과가 가설의 반대 방향으로 나왔다는 "
        "이유로 이 라벨을 완화하거나 재검토하지 않는다**(§9 사후 완화 금지).\n")
    say(f"🟡 **arm-B(병기) = 「{res_b['verdict']}」** — G1 이 +0.08%p 로 ±0.21%p(ε1-min) 밴드 «안»에 "
        "떨어져 그 자리에서 이미 판별불가가 확정된다(G2 결과와 무관하게 §7 표의 첫 조건에서 걸린다).\n")
    say("🔑 **arm-A 가 「해롭다」로 나온 산술적 이유** — 게이트가 배제한 97건(선언 손절폭이 "
        f"직전 20거래일 봉폭 중앙값의 절반에도 못 미치는 매수)의 평균 수익률을 역산하면 "
        f"약 {fmt_pct((res_a['mu_full']*len(closed) - res_a['mu_gate']*(len(closed)-res_a['n_excluded']))/res_a['n_excluded'])} "
        "로, 게이트가 «유지»시킨 507건의 평균(**" + fmt_pct(res_a['mu_gate']) + "**)보다 오히려 낫다. "
        "즉 이 실행에서는 ***손절이 봉폭을 못 따라가는 종목일수록 오히려 결과가 나았다*** — "
        "§4 의 기하학적 근거(K=0.5)와 반대 방향이다. ⚠️ **이것이 「게이트를 뒤집어 써야 한다」는 "
        "뜻은 아니다** — 사후에 부호를 뒤집어 다시 검정하는 것은 §9 가 금지하는 사후적합이다. "
        "이 문서는 그 가능성을 «관찰»로만 기록하고 판정은 그대로 「게이트가 해롭다」로 둔다.\n")

    say("### 🔑🔑 왜 배제 97건이 유지 507건보다 나았나 — 게이트가 «전략»을 고르고 있었다\n")
    diag_a = strategy_exclusion_diag(closed, stop_loss_pct, "excluded")
    render_strategy_diag(diag_a, "arm-A")
    top = diag_a.iloc[0]
    bottom_excl = diag_a[diag_a["n_excl"] == 0].sort_values("mean_ret")
    say(f"🔴 **배제 {res_a['n_excluded']}건 중 {int(top.n_excl)}건({top.share_of_total_excl*100:.0f}%)이 "
        f"`{top.strategy}`(선언 손절폭 {top.declared_sl:.0%} — 8전략 중 가장 좁음) 한 종목이다.** "
        f"그리고 그 전략의 평균 실현(gross)은 **{fmt_pct(top.mean_ret)}**로 8전략 중 사실상 최상위권이다 "
        f"(비교: 한 건도 안 배제된 `daytrading_3methods_breakout`(손절 10%, 가장 넓음)도 "
        f"{fmt_pct(diag_a[diag_a.strategy=='daytrading_3methods_breakout'].mean_ret.iloc[0])}로 상위권, "
        f"반면 배제 0건인 `elder_ema_pullback`은 {fmt_pct(diag_a[diag_a.strategy=='elder_ema_pullback'].mean_ret.iloc[0])}"
        f"로 최하위권이다).\n")
    say("🔑🔑 ***이 게이트는 「종목」이 아니라 사실상 「전략」을 골랐다.*** 비율 게이트 "
        "`선언손절폭 ≥ K × range_med_20` 의 **분자(선언손절폭)가 전략마다 고정된 다른 상수**이기 "
        "때문에, 분자가 가장 작은 전략(`book_pullback_ma5`, 3%)이 압도적으로 많이 걸리고 분자가 "
        "가장 큰 전략(`daytrading_3methods_breakout`, 10%)은 한 건도 안 걸린다. 그리고 하필 그 둘이 "
        "8전략 중 평균 실현 «1·2위»다 — ⇒ **게이트는 잘하던 전략의 매수를 대량으로 꺼버리고, "
        "못하던 전략(`elder_ema_pullback` " + fmt_pct(diag_a[diag_a.strategy=='elder_ema_pullback'].mean_ret.iloc[0]) +
        " · `deep_mr_dev20` " + fmt_pct(diag_a[diag_a.strategy=='deep_mr_dev20'].mean_ret.iloc[0]) +
        ")은 거의 그대로 뒀다.** 「게이트가 해롭다」 판정의 «기전»이 이것이다.\n")
    say("⚠️ **이건 PREREG §8-5 가 예상한 것과 «다르다».** §8-5 는 *「6개 전략이 7~8%대에 몰려 있어 "
        "비율 게이트가 절대 변동성 컷과 구별되지 않는다」*고 내다봤는데, 실제로 배제를 지배한 건 "
        "그 몰려 있는 6개가 아니라 ***«양 끝의 2개»(ma5 3%·daytrading 10%)***였다 — 예상한 것과 "
        "정반대 극단이 배제를 지배했다.\n")
    say("🔴 **이 진단은 「게이트가 해롭다」라는 §7 라벨을 바꾸지 않는다** — 604 전체표본 기준 "
        "G1~G3 판정은 위 §1 에 이미 기계적으로 확정됐다. 이 표는 그 라벨이 «왜» 나왔는지의 «기전»을 "
        "사후에 설명하는 기술통계이지, 라벨을 재추정하거나 조건을 바꾸는 것이 아니다.\n")

    say("### ⚠️ 자기점검 — `book_pullback_ma5` 가 걸린 게 「손절폭이 좁아서」인가 「그 전략이 "
        "변동성 큰 종목을 사서」인가\n")
    say("위 표만으로는 둘을 못 가른다 — 배제 비중이 특정 전략에 쏠린 것이 «분자»(선언 손절폭) 때문인지 "
        "«분모»(그 전략이 실제로 사는 종목의 변동성)가 유별나게 커서인지는 다른 질문이다. "
        "`gate_pass ⟺ range_med_20 ≤ 2×선언손절폭`(K=0.5 이므로) 이라는 관계를 이용해 전략별로 "
        "«그 전략이 산 종목들의 `range_med_20` 중앙값»을 «그 전략의 문턱(2×선언손절폭)»과 나란히 놓는다:\n")
    render_numerator_denominator_diag(diag_a)
    ma5_row = diag_a[diag_a.strategy == "book_pullback_ma5"].iloc[0]
    day_row = diag_a[diag_a.strategy == "daytrading_3methods_breakout"].iloc[0]
    say(f"🔑 **`book_pullback_ma5` 가 사는 종목의 변동성(`range_med_20` 중앙값 "
        f"{ma5_row.range_med_median*100:.2f}%)은 8전략 중 «두드러지게 높지 않다»** — 오히려 "
        f"`rs_leader`({diag_a[diag_a.strategy=='rs_leader'].iloc[0].range_med_median*100:.2f}%)· "
        f"`deep_mr_dev20`({diag_a[diag_a.strategy=='deep_mr_dev20'].iloc[0].range_med_median*100:.2f}%)· "
        f"`book_envelope_200d`({diag_a[diag_a.strategy=='book_envelope_200d'].iloc[0].range_med_median*100:.2f}%)"
        f"보다 «낮다». 그런데도 `ma5` 만 압도적으로 배제되는 건 «분모가 커서」가 아니라 "
        f"**«분자(문턱 {ma5_row.implied_threshold*100:.0f}%)가 이 표본의 전형적 변동성(전체 604건 중앙값 "
        f"{closed['range_med_20'].median()*100:.2f}%)보다 «낮게» 잡혀 있기 때문»**이다 — "
        f"***이건 「ma5 가 위험한 종목을 골라서」가 아니라 「ma5 의 손절 여유가 애초에 좁아서」라는 쪽을 "
        f"뒷받침한다.*** `daytrading_3methods_breakout` 도 대칭이다 — 그 전략이 사는 종목의 변동성"
        f"({day_row.range_med_median*100:.2f}%, 8전략 중 «가장 낮음»)이 아니라 문턱"
        f"({day_row.implied_threshold*100:.0f}%)이 넉넉해서 배제가 0건이다.\n")
    say("⚠️ **다만 이 자기점검도 완전하지 않다** — 중앙값 비교는 분포의 «위치»만 보고 «퍼짐»은 "
        "안 본다. 그리고 이건 이 실행 범위 밖의 인과 주장(「ma5 스크리너가 원래 저변동성 종목을 "
        "고른다」류)까지 확장하지 않는다 — 여기서는 ***「분모 효과만으로는 ma5 의 압도적 배제 쏠림을 "
        "설명 못 한다」***는 좁은 주장만 한다.\n")

    say("🔑 **G4/ma5 는 구조적으로 판별 불가** — 배제율이 71~73%로 극단적이라 퇴화일 비중이 "
        "58~62%(1/3 문턱의 거의 2배)에 달해 G2-strat 이 자동으로 무효 처리된다(§5-2). "
        "책 눌림목(3% 손절)은 문턱을 대부분의 거래일에 대량으로 걸기 때문에 «그날 중 일부만 무작위로 "
        "거르는» 층화 귀무 자체가 거의 항상 「전부 거른다」로 퇴화한다 — ***이 전략에는 이 귀무 설계가 "
        "구조적으로 안 맞는다***는 부수 발견이다(사전등록 §8-5 가 예상한 것과 같은 방향).\n")

    # ── 🔴 한계 ─────────────────────────────────────────────────────────
    say("## 🔴 한계 — PREREG §8 승계 + 이번 실행에서 새로 드러난 것\n")
    say("**§8 승계(그대로)**:\n")
    say("1. 🔴 한 국면이다(2026-06~08). 일반화 금지 — ε1-econ 자체가 이 국면의 기대값에서 유도됐다.")
    say("2. 🔴 미청산 42건(646−604)은 표본 밖이다 — 게이트가 걸렀어야 할 건이 그 안에 얼마나 있는지 이 연구는 답 못 한다.")
    say("3. 🔴 카운트 문턱[30,403)·퇴화일 문턱(1/3) 은 순열검정 설계에서만 고정했다 — 결과를 보고 바꾸지 않았다(G4/ma5 가 실제로 걸렸다).")
    say("4. 🔴 대체효과 미반영 — 「거르면 현금」시나리오만 쓴다. 「다음 후보로 대체」는 범위 밖이다.")
    say("5. 🔴 6/8 전략은 선언 손절폭이 7~8%대에 몰려 있어 비율 게이트가 사실상 절대 변동성 컷과 구별 안 된다 — G4 로 ma5·daytrading 만 따로 뗀 이유다.")
    say("6. ⚠️ gross 가 주 지표, net 은 부수(§4 net 부수 표 참고) — 비용이 μ_gate·μ_full 양쪽에 같은 비율로 적용되므로 차이(G1)에는 영향이 거의 없다.")
    say("7. ⚠️ `adj_factor` 는 해당 없음 — `range_med_N` 이 비율이라 척도가 상쇄된다.")
    say(f"8. ⚠️ 0-range 봉 혼입 가능성(1단계 `GATE.md` §6 실측 58건) — 게이트를 «통과시키는»(gate_pass=TRUE) 쪽으로 편향될 수 있다. 제거하지 않았다.")
    say("9. ⚠️ 진입가·청산 룰은 안 바꿨다 — 이 게이트는 「사느냐 마느냐」만 가른다.")
    say("10. ⚠️ ε1-econ 은 근사다 — 「유지 표본 평균이 0」≠「포트폴리오 전체 기대값이 0」(자세한 논증은 PREREG §8-10).")
    say()
    say("**이번 실행에서 새로 드러난 것**:\n")
    say("- 🆕 🔴 **arm-A 의 부호가 가설과 반대다.** §2 는 (가)/(나) 두 가설을 경쟁시켰는데, "
        "실측은 그 어느 쪽도 아닌 «게이트가 해롭다» — 즉 손절이 변동성을 못 따라가는 종목을 "
        "거르는 것이 오히려 «좋은» 종목을 걸렀다는 뜻으로 읽을 여지가 있다. §2 가 이 가능성을 "
        "명시적으로 예측하지 않았다는 것 자체가 **한계**다(경쟁 가설 설계가 완전하지 않았다).")
    say("- 🆕 🔴 **G4(ma5) 의 극단적 배제율(71~73%)이 §5-2 의 층화 귀무를 구조적으로 무력화한다.** "
        "이건 「검정력이 낮다」가 아니라 「이 전략에는 이 귀무 «설계» 자체가 안 맞는다」는 것 — "
        "배제율이 절반을 넘는 전략에 N0-strat 을 적용하려면 퇴화일 문턱과 별개로 «날짜당 표본 크기」"
        "자체를 재설계해야 할 수 있다(이번 범위 밖, 다음 연구 표적).")
    say("- 🆕 🟡 arm-B 는 G1 부터 중립대(±0.21%p)에 걸려 G2·G3 결과와 무관하게 판별불가로 확정됐다 — "
        "μ_gate 가 μ_full 보다 «명목상» 낫지만(+0.08%p) 그 차이 자체가 비용(0.21%p)보다도 작다.")
    say("- 🆕 ⚠️ **두 개의 독립 쿼리가 604 로 정확히 일치했다** — `run_gate.py.load_closed_buy_ids()`"
        "(1단계, PnL 미조회)와 이 스크립트의 `load_pnl()`(2단계, PnL 필요)이 각자 따로 "
        "`buy_record_id IS NOT NULL` 만으로 모집단을 정의했는데 604로 일치했다(코드의 assert 로 "
        "강제). 우연이 아니라 **두 쿼리가 같은 존재-조건을 쓰기 때문**이지만, 이런 크로스체크를 "
        "실행 코드 안에 넣어두는 것 자체가 재현성의 증거가 된다.")
    say(f"- 🆕 🔴🔴 **비율 게이트는 분자가 집단마다 다르면 «집단 선택기»가 된다 — 그리고 «어느 "
        f"방향으로»가 §8-5 의 예상과 어긋났다.** `선언손절폭 ≥ K×range_med_20` 에서 분모"
        f"(`range_med_20`, 변동성)는 종목별로 다르지만 **분자(선언손절폭)는 전략마다 고정된 상수**"
        f"다 — 그 결과 배제 {res_a['n_excluded']}건의 {int(diag_a.iloc[0].n_excl)}건"
        f"({diag_a.iloc[0].share_of_total_excl*100:.0f}%)이 손절폭이 가장 좁은 «전략» 하나에 쏠렸다. "
        f"PREREG §8-5 는 *「6개 전략이 7~8%대에 몰려 있어 절대 변동성 컷과 구별 안 된다」*는 방향을 "
        f"예상했는데, 실제 배제를 지배한 건 몰려 있는 6개가 아니라 **양 끝(3%·10%)** 이었다 — "
        f"예상과 «정반대 극단»이 효과를 지배했다.")
    say()

    # ── 🔑 재사용 규칙 ──────────────────────────────────────────────────
    say("## 🔑 재사용 규칙 — 이번에 배운 것\n")
    say("- 🔑🔑🔑 ***비율 게이트의 분자가 하위집단마다 다르면, 그 게이트는 「개체」가 아니라 "
        "「하위집단」을 고른다.*** 분모(변동성)를 재는 줄 알았는데 실제로는 분자(전략 설정 상수)를 "
        "재고 있었다 — `선언손절폭 ≥ K×range_med_20` 이 그렇다. ⇒ **게이트를 설계했으면 "
        "「무엇이 걸리는지」를 하위집단별로 «먼저» 세어봐야 한다.** 배제 집합의 구성비가 한 "
        "하위집단에 쏠려 있으면 그건 그 축(이번 경우 「변동성」)의 게이트가 아니라 다른 축(이번 "
        "경우 「어느 전략인가」)의 게이트다. 🔑 그리고 이건 **1단계(`GATE.md`)에서 이미 PnL 없이도 "
        "볼 수 있었다** — `GATE.md` §7 표가 「배제 71건이 book_pullback_ma5」라는 걸 이미 보여줬는데 "
        "그때는 그게 «쏠림»인지 몰랐다(전체 배제 97건 대비 73% 라는 «비중»은 604 표본을 알아야 "
        "계산되기 때문). ***사전등록에 「배제 집합의 하위집단 쏠림 점검」을 1단계(PIT, PnL 이전) "
        "항목으로 넣었어야 했다*** — 다음 게이트 연구에 이 항목을 추가한다.")
    say("- 🔑🔑 ***사전등록에 대칭 라벨(「게이트가 해롭다」)을 미리 만들어 둔 덕에, 결과가 가설과 "
        "정반대로 나왔을 때도 라벨을 새로 짓지 않고 그대로 쓸 수 있었다.*** 「(가)/(나) 둘 중 하나」"
        "로만 판정표를 짰다면 이번 결과는 억지로 판별불가에 욱여넣거나, 사후에 새 라벨을 만드는 "
        "유혹에 노출됐을 것이다 — **비대칭 결과를 예상하지 못했더라도 대칭 판정표는 그걸 받아낸다.**")
    say("- 🔑 ***카운트 문턱만으로는 극단적 배제율의 병리를 못 잡는다*** — G4/ma5 는 [30,403) 카운트 "
        "문턱을 여유 있게 통과했지만(71·69건) 퇴화일 비중(1/3)이 «따로» 걸렸다. **총량 문턱과 "
        "분포형태 문턱은 서로 다른 것을 재므로 둘 다 필요하다** — 이번 실행이 그 설계가 실제로 "
        "작동하는 사례를 처음 만들었다.")
    say("- 🔑 ***게이트 방향의 부호를 사전에 가정하지 말 것*** — 기하학적으로 그럴듯해 보이는 문턱"
        "(K=0.5, 「손절선이 봉폭 중앙값의 절반 이상」)도 실측에서는 반대 부호로 나올 수 있다. "
        "이 문서가 그 반증 사례다.")
    say("- 🔑 ***같은 PIT 존재-조건(`buy_record_id IS NOT NULL`)을 두 스크립트가 독립적으로 다시 "
        "구현하고 assert 로 맞대면, 그 자체가 재현 게이트가 된다*** — 메모리의 기존 교훈"
        "(*「재현 게이트는 스크립트가 같은가만 본다」*)에 대한 부분적 대응이다: 스크립트가 달라도 "
        "«같은 모집단 정의»를 두 번 구현해 수치로 맞대면 스냅샷 의존성 문제를 줄일 수 있다.")
    say()

    (BASE / "RESULTS.md").write_text("\n".join(OUT), encoding="utf-8")
    print("\n[written] RESULTS.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

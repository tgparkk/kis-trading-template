"""매수 빈도 시나리오 산수 — `DESIGN.md` 그대로(관리자 고정 2026-09-26).

관측 산수(관찰) · 판정 없음 · p·라벨 없음 · 라이브 룰 변경 근거 인용 금지(~10-16 룰 변경 0).
목적: 10-17 안건(자금·K·하루 횟수 제한 재검토) 대비 «얼마나 자주 사면 비용이 얼마인가».

입력 = `candidate_ledger/results/ledger.csv` 하나(md5 고정 · 불일치면 중단). DB 조회 0 · 라이브 코드 0줄.
후보 L0 = band_ok=True ∧ entry_price 있음. 전략마다 시나리오 8개(N∈{1,3,5,∞} × K∈{현행,∞}) + 참고판 R(=L0 전부 ·
상한·중복 거부 없음). 하루 처리 = entry_date 오름차순 · 같은 날은 rank 오름차순 · 중복(같은 전략·같은 종목 보유 중)
거부 · 자리는 [entry_date, exit_date] 동안 차지하고 exit_date 다음 거래일부터 빈다. open 로트는 창 끝까지 차지하되
손익·비용·net 합에서는 뺀다(건수만 인쇄).

실행(워크트리 RoboTrader_template 에서):
  python -m backtest.concept_axes.candidate_ledger.freq_scenarios.run_freq
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]                                     # …/RoboTrader_template
LEDGER_CSV = BASE.parent / "results" / "ledger.csv"
LEDGER_MD5_EXPECT = "980e58492a7ac2ed11d25526f4488dbc"
DESIGN_MD = BASE / "DESIGN.md"

# ── §입력·시나리오 🔒(DESIGN.md 그대로) ──────────────────────────────────────
STRATS = ["book_pullback_ma20", "minervini_volume_dryup", "daytrading_3methods_breakout"]
SHORT = {"book_pullback_ma20": "ma20", "minervini_volume_dryup": "minervini",
         "daytrading_3methods_breakout": "daytrading"}
K_CURRENT = {"book_pullback_ma20": 10, "minervini_volume_dryup": 6, "daytrading_3methods_breakout": 10}
N_VALUES: List[Optional[int]] = [1, 3, 5, None]            # None = ∞
K_KINDS = ["현행", "∞"]                                     # K=∞ → None (무제한)
W_START, W_END = "2024-03-13", "2026-09-23"
FULL_DAYS = 617
COST_RATE = 0.0025
CAPITAL_PER_LOT = 1_000_000
LIVE_WIN = ("2026-08-24", "2026-09-23")
LIVE_RATE_PER_BUYDAY = {"ma20": 1.7, "minervini": 1.3, "daytrading": 2.0}   # 관리자 제공(§ 대조 인쇄)


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


# ════════════════════════════════════════════════════════════════════════════
# 1. 입력 · 달력
# ════════════════════════════════════════════════════════════════════════════
def load_ledger(path: Path = LEDGER_CSV, expect: Optional[str] = LEDGER_MD5_EXPECT) -> pd.DataFrame:
    got = md5(path)
    if expect is not None and got != expect:
        raise SystemExit(f"ledger.csv md5 불일치 {got} ≠ {expect} — 중단(DESIGN.md §입력)")
    return pd.read_csv(path, dtype={"stock_code": str, "scan_date": str, "entry_date": str,
                                    "exit_date": str}, low_memory=False)


def build_calendar(df: pd.DataFrame) -> List[str]:
    """거래일 달력 = ledger 전 행의 scan_date 집합(617일 · entry_date·exit_date 모두 이 집합의 부분집합)."""
    return sorted(df["scan_date"].unique().tolist())


def bucket_years(cal: List[str]) -> "Dict[str, List[int]]":
    """버킷 이름 → 그 버킷에 속하는 달력 인덱스 목록. 「전체」 + 연도별(달력에 실제 있는 연도만)."""
    buckets: Dict[str, List[int]] = {"전체": list(range(len(cal)))}
    for y in sorted({d[:4] for d in cal}):
        buckets[y] = [i for i, d in enumerate(cal) if d[:4] == y]
    return buckets


# ════════════════════════════════════════════════════════════════════════════
# 2. 후보 집합 L0 · 자리 인덱스
# ════════════════════════════════════════════════════════════════════════════
def build_l0(df: pd.DataFrame, strategy: str) -> pd.DataFrame:
    """L0 = band_ok=True ∧ entry_price 있음(DESIGN.md §후보 집합). scan_date 의 rank 로 tie-break."""
    s = df[(df["strategy"] == strategy) & (df["band_ok"].astype("boolean") == True) &  # noqa: E712
           (df["entry_price"].notna())].copy()
    return s.reset_index(drop=True)


def prep_l0(l0: pd.DataFrame, cal_idx: Dict[str, int], n_days: int) -> pd.DataFrame:
    """진입/자리반환 달력 인덱스를 붙이고 (entry_idx, rank) 오름차순으로 정렬한다.

    자리 반환 규약(🔒 DESIGN.md): exit_reason=open 은 창 끝까지 차지(release_idx=n_days, 창 안에서는 절대 안 빔).
    그 외는 exit_date 다음 거래일부터 빔(release_idx = exit_idx + 1).
    """
    o = l0.copy()
    o["_entry_idx"] = o["entry_date"].map(cal_idx).astype(int)
    exit_idx = o["exit_date"].map(cal_idx).astype(int)
    is_open = o["exit_reason"] == "open"
    o["_release_idx"] = np.where(is_open, n_days, exit_idx + 1)
    return o.sort_values(["_entry_idx", "rank"], kind="mergesort").reset_index(drop=True)


# ════════════════════════════════════════════════════════════════════════════
# 3. 시나리오 시뮬레이션
# ════════════════════════════════════════════════════════════════════════════
def simulate_capped(l0p: pd.DataFrame, n_days: int, n_cap: Optional[int],
                     k_cap: Optional[int]) -> Tuple[pd.DataFrame, List[int]]:
    """N(하루 매수 상한) · K(동시 보유 상한) 적용 · 같은 종목 중복 보유 거부. (선택된 로트, 일별 보유 수)."""
    by_day: Dict[int, List[Tuple[str, int, int]]] = {}
    for day, code, rel, idx in zip(l0p["_entry_idx"], l0p["stock_code"], l0p["_release_idx"], l0p.index):
        by_day.setdefault(int(day), []).append((code, int(rel), int(idx)))

    n_lim = n_cap if n_cap is not None else float("inf")
    k_lim = k_cap if k_cap is not None else float("inf")
    held: Dict[str, int] = {}
    levels = [0] * n_days
    selected_idx: List[int] = []
    for day in range(n_days):
        if held:
            for code in [c for c, rel in held.items() if rel <= day]:
                del held[code]
        day_buys = 0
        for code, rel, idx in by_day.get(day, []):
            if code in held:                 # 같은 전략·같은 종목 이미 보유 중 → 건너뜀
                continue
            if day_buys >= n_lim:
                continue
            if len(held) >= k_lim:
                continue
            held[code] = rel
            day_buys += 1
            selected_idx.append(idx)
        levels[day] = len(held)
    selected = l0p.loc[selected_idx]
    return selected, levels


def simulate_uncapped(l0p: pd.DataFrame, n_days: int) -> Tuple[pd.DataFrame, List[int]]:
    """참고판 R = L0 전부(상한·중복 거부 없음 · 로트 독립). 자리 점유만 같은 규약으로 셈."""
    diff = [0] * (n_days + 1)
    for start, rel in zip(l0p["_entry_idx"], l0p["_release_idx"]):
        diff[int(start)] += 1
        if rel <= n_days:
            diff[int(rel)] -= 1
    levels = [0] * n_days
    cur = 0
    for day in range(n_days):
        cur += diff[day]
        levels[day] = cur
    return l0p, levels


# ════════════════════════════════════════════════════════════════════════════
# 4. 지표
# ════════════════════════════════════════════════════════════════════════════
def compute_metrics(selected: pd.DataFrame, cal_idx: Dict[str, int], day_idxs: List[int],
                     levels: List[int]) -> Dict[str, Any]:
    """전략×시나리오×버킷 1행. 🔴해석: open 로트는 자리 점유(최대 동시 보유·필요 자금)에는 들어가지만
    gross·비용·net·로트당 net·승률에서는 전부 빠진다(DESIGN.md 의 「손익 합」 제외 규정을 비용·net 에도 동일 적용
    — 「건수만 인쇄」와 일관되게 재무 지표 전부를 청산 완료 로트로 한정). 근거는 RESULTS_freq.md 「해석 기록」.
    """
    day_set = set(day_idxs)
    sub = selected[selected["_entry_idx"].isin(day_set)]
    completed = sub[sub["exit_reason"] != "open"]
    opens = sub[sub["exit_reason"] == "open"]
    n_completed = int(len(completed))
    n_open = int(len(opens))
    n_days_bucket = len(day_idxs)
    buys_per_day = (n_completed + n_open) / n_days_bucket if n_days_bucket else 0.0

    gross = int(round(completed["pnl_won"].sum())) if n_completed else 0
    cost = int(round((completed["notional"] * COST_RATE).sum())) if n_completed else 0
    net = gross - cost
    net_per_lot = round(net / n_completed) if n_completed else None
    win_rate = float((completed["ret_pct"] > 0).mean()) if n_completed else None
    cost_over_gross = (cost / abs(gross)) if gross else None

    max_conc = max((levels[i] for i in day_idxs), default=0)
    capital_needed = max_conc * CAPITAL_PER_LOT

    return dict(n_buys_completed=n_completed, n_open=n_open, buys_per_day=round(buys_per_day, 2),
                gross_won=gross, cost_won=cost, net_won=net, net_per_lot_won=net_per_lot,
                win_rate=None if win_rate is None else round(win_rate, 4),
                max_concurrent=int(max_conc), capital_needed_won=int(capital_needed),
                cost_over_abs_gross=None if cost_over_gross is None else round(cost_over_gross, 4))


# ════════════════════════════════════════════════════════════════════════════
# 5. 전체 실행
# ════════════════════════════════════════════════════════════════════════════
def scenario_list() -> List[Tuple[Optional[int], str]]:
    return [(n, k) for n in N_VALUES for k in K_KINDS]


def n_label(n: Optional[int]) -> str:
    return "∞" if n is None else str(n)


def run_all(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    """freq_table 전 행 + 전략별 (5,현행) 선택 결과(대조 인쇄용)를 함께 돌려준다."""
    cal = build_calendar(df)
    cal_idx = {d: i for i, d in enumerate(cal)}
    n_days = len(cal)
    buckets = bucket_years(cal)

    rows: List[Dict[str, Any]] = []
    cur5: Dict[str, Dict[str, Any]] = {}

    for strat in STRATS:
        l0 = build_l0(df, strat)
        l0p = prep_l0(l0, cal_idx, n_days)
        k_now = K_CURRENT[strat]

        for n_cap, k_kind in scenario_list():
            k_cap = k_now if k_kind == "현행" else None
            selected, levels = simulate_capped(l0p, n_days, n_cap, k_cap)
            if n_cap == 5 and k_kind == "현행":
                cur5[strat] = dict(selected=selected, levels=levels, cal_idx=cal_idx, cal=cal)
            for bname, day_idxs in buckets.items():
                m = compute_metrics(selected, cal_idx, day_idxs, levels)
                rows.append(dict(strategy=strat, scenario=f"N={n_label(n_cap)},K={k_kind}",
                                 N=n_label(n_cap), K=k_kind, bucket=bname, **m))

        # 참고판 R
        selected_r, levels_r = simulate_uncapped(l0p, n_days)
        for bname, day_idxs in buckets.items():
            m = compute_metrics(selected_r, cal_idx, day_idxs, levels_r)
            rows.append(dict(strategy=strat, scenario="R", N="-", K="-", bucket=bname, **m))

    return pd.DataFrame(rows), cur5


# ════════════════════════════════════════════════════════════════════════════
# 6. 대조 인쇄(판정 없음)
# ════════════════════════════════════════════════════════════════════════════
def comparison_block(cur5: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    lo, hi = LIVE_WIN
    out = []
    for strat, d in cur5.items():
        cal_idx, cal = d["cal_idx"], d["cal"]
        day_idxs = [i for i, dt in enumerate(cal) if lo <= dt <= hi]
        m = compute_metrics(d["selected"], cal_idx, day_idxs, d["levels"])
        short = SHORT[strat]
        out.append(dict(strategy=strat, short=short, win=f"{lo}~{hi}", n_days=len(day_idxs),
                        buys_per_tradingday=m["buys_per_day"], live_per_buyday=LIVE_RATE_PER_BUYDAY[short]))
    return out


# ════════════════════════════════════════════════════════════════════════════
# 7. 출력
# ════════════════════════════════════════════════════════════════════════════
def fmt_won(v) -> str:
    if v is None:
        return "-"
    return f"{int(round(v)):,}"


def fmt_pct(v) -> str:
    if v is None:
        return "-"
    return f"{v * 100:.2f}%"


def write_results_md(path: Path, table: pd.DataFrame, cmp_rows: List[Dict[str, Any]], meta: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# 매수 빈도 시나리오 산수 — RESULTS")
    lines.append("")
    lines.append("> 🔴 관측 산수(관찰) · 판정 없음 · p·라벨 없음 · 라이브 룰 변경 근거 인용 금지."
                 " `DESIGN.md`(관리자 고정 2026-09-26) 그대로 · 결과를 본 뒤 설계를 바꾸지 않았다.")
    lines.append(f"- git sha `{meta['git_sha']}` · ledger.csv md5 `{meta['ledger_md5']}`(기대치와 일치)"
                 f" · 창 {W_START}~{W_END}(거래일 {FULL_DAYS})")
    lines.append(f"- 실행 {meta['secs_total']}s · 시작 {meta['started']} · 끝 {meta['finished']}")
    lines.append("")

    order = [f"N={n_label(n)},K={k}" for n, k in scenario_list()] + ["R"]
    cols = ["scenario", "n_buys_completed", "n_open", "buys_per_day", "gross_won", "cost_won", "net_won",
           "net_per_lot_won", "win_rate", "max_concurrent", "capital_needed_won", "cost_over_abs_gross"]
    head = ["시나리오", "매수(완료)", "open", "거래일당", "gross", "비용", "net", "로트당net", "승률",
           "최대동시보유", "필요자금", "비용/|gross|"]

    for strat in STRATS:
        lines.append(f"## {strat} — 전체 창({W_START}~{W_END})")
        lines.append("")
        lines.append("| " + " | ".join(head) + " |")
        lines.append("|" + "---|" * len(head))
        sub = table[(table["strategy"] == strat) & (table["bucket"] == "전체")].set_index("scenario").loc[order]
        for scen, r in sub.iterrows():
            lines.append("| " + " | ".join([
                scen, str(r["n_buys_completed"]), str(r["n_open"]), f"{r['buys_per_day']:.2f}",
                fmt_won(r["gross_won"]), fmt_won(r["cost_won"]), fmt_won(r["net_won"]),
                fmt_won(r["net_per_lot_won"]), fmt_pct(r["win_rate"]), str(r["max_concurrent"]),
                fmt_won(r["capital_needed_won"]),
                "-" if r["cost_over_abs_gross"] is None else f"{r['cost_over_abs_gross'] * 100:.2f}%",
            ]) + " |")
        lines.append("")

    lines.append("## 연도별 — 매수 건수(완료+open) · 거래일당 · net(원) (전체 시나리오)")
    lines.append("")
    for strat in STRATS:
        lines.append(f"### {strat}")
        lines.append("")
        lines.append("| 시나리오 | 2024 매수/거래일당/net | 2025 매수/거래일당/net | 2026 매수/거래일당/net |")
        lines.append("|---|---|---|---|")
        for scen in order:
            cells = [scen]
            for y in ("2024", "2025", "2026"):
                r = table[(table["strategy"] == strat) & (table["scenario"] == scen)
                         & (table["bucket"] == y)]
                if len(r) == 0:
                    cells.append("-")
                    continue
                r = r.iloc[0]
                n_tot = int(r["n_buys_completed"]) + int(r["n_open"])
                cells.append(f"{n_tot} / {r['buys_per_day']:.2f} / {fmt_won(r['net_won'])}")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    lines.append("## 대조 인쇄(판정 없음) — 현행 근사(N=5,K=현행) · 2026-08-24~2026-09-23 entry_date 구간")
    lines.append("")
    lines.append("| 전략 | 구간 거래일 | 본 산수(거래일당 매수) | 라이브 실측(매수일당 매수 · 관리자 제공) |")
    lines.append("|---|---|---|---|")
    for c in cmp_rows:
        lines.append(f"| {c['strategy']} | {c['n_days']}일 | {c['buys_per_tradingday']:.2f}"
                     f" | {c['live_per_buyday']:.2f} |")
    lines.append("")
    lines.append("- 🔴 두 값은 분모가 다르다(본 산수 = 전체 거래일 기준 · 라이브 제공값 = 매수가 있었던 날만 기준"
                 " «매수일당») — 그 위에 자본·현금·장중 타이밍·밴드 근사 차이까지 겹친다. 판정 없음.")
    lines.append("")

    lines.append("## 해석 기록(애매한 대목 · 문자 그대로 해석)")
    lines.append("")
    lines.append("- open 로트: 자리 점유(최대 동시 보유·필요 자금)에는 창 끝까지 포함하되, gross·비용·net·"
                 "로트당 net·승률에서는 전부 제외했다(DESIGN.md 의 「손익 합」 제외 규정을 재무 지표 전체로 확장 — "
                 "건수만 인쇄한다는 문언과 일관). 미결 로트의 매수 수수료(실제로는 이미 지불됐을 금액)는 이 비용 "
                 "합계에 없다.")
    lines.append("- 「거래일당 매수 수」 분자 = 매수(완료)+open(그날 실제로 «매수»가 일어난 사건 수 전부).")
    lines.append("- 「로트당 net」 분모 = 매수 건수(청산 완료)만(open 은 net 합에 없으므로 분모에도 넣지 않음).")
    lines.append("- 연도 버킷 = entry_date 의 연도(그 해 실제 거래일 수를 분모로 씀 · 2024·2026 은 부분년).")
    lines.append("- 최대 동시 보유·필요 자금은 버킷 구간 안의 일별 보유 수(전 구간 연속 시뮬레이션 결과)의 최댓값"
                 "이다 — 그 해에 새 매수가 없어도 이전 해 이월 보유가 그 해 최댓값일 수 있고, 그 경우도 올바로 "
                 "잡힌다(레벨은 하루 단위로 연속 갱신).")
    lines.append("- 참고판 R = L0 전부(중복·상한 없음) — 같은 종목이 겹쳐도 로트를 독립으로 센다(원장 B1과 동일 "
                 "가정). R 의 최대 동시 보유·필요 자금도 같은 자리 규약으로 셌다.")
    lines.append("- 비용 = Σ notional × 0.25% 를 버킷 안에서 먼저 합산한 뒤 마지막에 한 번 반올림했다(로트별 "
                 "반올림 아님).")
    lines.append("")

    lines.append("## 한계")
    lines.append("")
    lines.append("- 원장 한계 승계(일봉 청산 근사 · 생존자 유니버스 · 빈티지 · 시가 밴드 근사).")
    lines.append("- 비용 0.25% 는 산술 가정(세금·호가 미끄러짐 미반영). 한 국면(2024-03~2026-09).")
    lines.append("- 🔴 로트당 gross 가 시나리오마다 다른 것은 검정하지 않았고 오늘 결과상 측정 불가 크기다 ⇒ 이 표로"
                 " 시나리오를 고르지 않는다(DESIGN.md 쓰임새 규칙). 용도는 비용 총액·필요 자금의 빈도별 크기뿐.")
    lines.append("")
    lines.append("## 파일")
    lines.append("")
    lines.append("- `DESIGN.md` · `run_freq.py` · `freq_table.csv`(전략×시나리오×버킷 전 행) · `run_meta.json`"
                 " · `RESULTS_freq.md`(이 문서)")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    t0 = time.time()
    started = datetime.now().isoformat(timespec="seconds")
    if not DESIGN_MD.exists():
        raise SystemExit("DESIGN.md 없음 — §순서 위반(설계 먼저)")

    df = load_ledger()
    table, cur5 = run_all(df)
    cmp_rows = comparison_block(cur5)

    out_dir = BASE
    table.to_csv(out_dir / "freq_table.csv", index=False)

    finished = datetime.now().isoformat(timespec="seconds")
    secs_total = round(time.time() - t0, 1)
    meta = dict(git_sha=git_sha(), ledger_md5=LEDGER_MD5_EXPECT, started=started, finished=finished,
               secs_total=secs_total)
    write_results_md(out_dir / "RESULTS_freq.md", table, cmp_rows, meta)

    run_meta = dict(design="freq_scenarios/DESIGN.md", git_sha=meta["git_sha"],
                   input_md5=dict(ledger_csv=LEDGER_MD5_EXPECT), window=[W_START, W_END],
                   full_trading_days=FULL_DAYS, cost_rate=COST_RATE, capital_per_lot=CAPITAL_PER_LOT,
                   n_values=[n_label(n) for n in N_VALUES], k_kinds=K_KINDS, k_current=K_CURRENT,
                   started=started, finished=finished, secs_total=secs_total,
                   comparison=cmp_rows,
                   outputs=["DESIGN.md", "run_freq.py", "freq_table.csv", "run_meta.json", "RESULTS_freq.md"])
    (out_dir / "run_meta.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=1, default=str),
                                           encoding="utf-8")
    sys.stderr.write(f"done in {secs_total}s → {out_dir}\n")


if __name__ == "__main__":
    main()

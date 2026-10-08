"""테마 신호(스펙 §4) — 경기장 키(scan_date·stock_code)마다 돌출도 S 와 인쇄 항목.

🔴 결과 열(ret·exit 등)을 읽지 않는다 — 원장에서 `strategy, scan_date, stock_code, rank` 만 읽는다.

    python -X utf8 -m backtest.concept_axes.theme_rank.build_signals --n-cut <N_CUT>
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import argparse                                                        # noqa: E402
import json                                                            # noqa: E402
import subprocess                                                      # noqa: E402
from dataclasses import dataclass                                      # noqa: E402
from datetime import date                                              # noqa: E402
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple  # noqa: E402

import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.candidate_ledger import run as CL           # noqa: E402
from backtest.concept_axes.theme_rank import build_arena as BA         # noqa: E402
from backtest.concept_axes.theme_rank import membership as MB          # noqa: E402
from backtest.concept_axes.theme_rank import returns as RT             # noqa: E402
from backtest.concept_axes.theme_rank import signal as SG              # noqa: E402
from backtest.concept_axes.theme_rank import snapshot as SN            # noqa: E402

PX_START = "2024-02-01"          # 창 첫날(2024-03-13)의 D−1 과 A″ 연속 일수 여유
SIG_COLS = ["scan_date", "stock_code", "s_input_ok", "s", "log10_p", "m", "main_theme", "k_main", "n_main",
            "single", "s_full", "a_mean_excess", "c_same_theme", "b_rank_in_theme", "b_limit_up", "a2_streak"]


@dataclass
class Inputs:
    states: Dict[date, SG.DayState]
    excess: Dict[date, Dict[str, float]]
    raw_r: Dict[date, Dict[str, float]]
    themes_of: Dict[str, FrozenSet[int]]
    members: Dict[int, FrozenSet[str]]
    themes_of_full: Dict[str, FrozenSet[int]]
    members_full: Dict[int, FrozenSet[str]]
    day_codes: Dict[date, FrozenSet[str]]
    streak_of: Dict[Tuple[int, date], int]


def compute_rows(keys: Sequence[Tuple[date, str]], inp: Inputs) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for d, code in keys:
        st = inp.states.get(d)
        if st is None:
            out.append({k: "" for k in SIG_COLS} | dict(scan_date=d, stock_code=code, s_input_ok=False))
            continue
        sp = SG.surprise(code, inp.themes_of, inp.members, st)
        full = SG.surprise(code, inp.themes_of_full, inp.members_full, st)
        ex = inp.excess[d]
        t = sp.main_theme
        out.append(dict(
            scan_date=d, stock_code=code, s_input_ok=True, s=sp.s, log10_p=sp.log10_p, m=sp.m,
            main_theme="" if t is None else t, k_main=sp.k_main, n_main=sp.n_main, single=sp.single,
            s_full=full.s,
            a_mean_excess=SG.mean_excess_max(code, inp.themes_of, inp.members, ex),
            c_same_theme="" if t is None else SG.same_theme_count(code, t, inp.members,
                                                                   inp.day_codes.get(d, frozenset())),
            b_rank_in_theme="" if t is None else SG.rank_in_theme(code, t, inp.members, ex),
            b_limit_up=inp.raw_r[d].get(code, 0.0) >= SG.LIMIT_UP_R,
            a2_streak="" if t is None else inp.streak_of.get((t, d), 0)))
    return out


def primary_s(keys: Sequence[Tuple[date, str]], states: Mapping[date, SG.DayState],
              themes_of: Mapping[str, FrozenSet[int]], members: Mapping[int, FrozenSet[str]]) -> List[float]:
    """S 만(플라시보 재계산용 · run.py). 상태 없는 날 = NaN."""
    return [SG.surprise(c, themes_of, members, states[d]).s if d in states else float("nan") for d, c in keys]


def load_keys() -> Tuple[List[Tuple[date, str]], Dict[date, FrozenSet[str]]]:
    if BA.md5(BA.LEDGER_CSV) != BA.LEDGER_MD5:
        raise SystemExit("ledger.csv md5 불일치 — 중단")
    led = pd.read_csv(BA.LEDGER_CSV, usecols=["strategy", "scan_date", "stock_code", "rank"],
                      dtype={"stock_code": str, "scan_date": str})
    led = led[led["strategy"] == BA.STRATEGY]
    led["d"] = pd.to_datetime(led["scan_date"]).dt.date
    led["c"] = led["stock_code"].map(SN.norm_code)
    day_codes = {d: frozenset(g["c"]) for d, g in led.groupby("d")}
    arena = led[led["rank"] <= BA.ARENA_MAX_RANK].sort_values(["d", "rank"])
    return list(zip(arena["d"], arena["c"])), day_codes


def load_day_states(conn) -> Tuple[Dict[date, SG.DayState], Dict[date, Dict[str, float]],
                                   Dict[date, Dict[str, float]], List[date]]:
    from backtest.concept_axes.replayer import loader as LD
    cal = [pd.Timestamp(d).date() for d in LD.load_trading_calendar(conn, PX_START, CL.W_END)]
    px = LD.load_prices(conn, PX_START, CL.W_END)
    rets = RT.daily_returns(px, cal, RT.bad_rows(px))
    excess = RT.excess_by_day(rets)
    return {d: SG.day_state(e) for d, e in excess.items()}, excess, RT.raw_by_day(rets), cal


def streak_table(themes: Sequence[int], members: Mapping[int, FrozenSet[str]],
                 states: Mapping[date, SG.DayState], cal: Sequence[date]) -> Dict[Tuple[int, date], int]:
    out: Dict[Tuple[int, date], int] = {}
    for t in themes:
        run = 0
        for d in cal:
            st = states.get(d)
            run = run + 1 if (st is not None and SG.theme_logp(t, members, st) < SG.STREAK_LOGP) else 0
            out[(t, d)] = run
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-cut", type=int, required=True)
    a = ap.parse_args(argv)
    keys, day_codes = load_keys()
    conn = CL._connect()
    snap = SN.load_snapshot(conn, MB.SNAP_DATE)
    states, excess, raw_r, cal = load_day_states(conn)
    conn.close()
    elig = MB.eligible_themes(snap.theme_name, a.n_cut)
    members = MB.restrict(snap.members, elig)
    inp = Inputs(states=states, excess=excess, raw_r=raw_r, themes_of=SN.invert(members), members=members,
                 themes_of_full=SN.invert(snap.members), members_full=dict(snap.members), day_codes=day_codes,
                 streak_of=streak_table(sorted(elig), members, states, cal))
    rows = compute_rows(keys, inp)
    BA.OUT.mkdir(parents=True, exist_ok=True)
    path = BA.OUT / "signals.csv"
    pd.DataFrame(rows, columns=SIG_COLS).to_csv(path, index=False, encoding="utf-8")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = dict(git_sha=sha, n_cut=a.n_cut, patterns=list(MB.EXCLUDED_NAME_PATTERNS), snap_date=str(MB.SNAP_DATE),
                n_eligible_themes=len(elig), n_rows=len(rows), ledger_md5=BA.LEDGER_MD5, signals_md5=BA.md5(path))
    (BA.OUT / "signals_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"신호 {len(rows):,}행 · 적격 테마 {len(elig)} · md5 {meta['signals_md5']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

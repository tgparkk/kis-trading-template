"""도구 교정(스펙 §5-3) — 실제 소속표 + 테마×날짜 AR(1) 잡음으로 만든 가짜 S 400개를 실제 결과에 돌린다.

실제 S 는 읽지 않는다(가짜 신호 × 결과만). 합격 = p<0.10 거부율 ∈ [0.07, 0.13].
lag 11 → 22 → 33 순으로 첫 합격 lag 를 쓰고, 모두 불합격이면 lag 11 가짜 t 의 경험분포로 p 를 보정한다.

    python -X utf8 -m backtest.concept_axes.theme_rank.calibrate --n-cut <N_CUT>
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import argparse                                                        # noqa: E402
import json                                                            # noqa: E402
import math                                                            # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence  # noqa: E402

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.theme_rank import bandfill as BF            # noqa: E402
from backtest.concept_axes.theme_rank import build_arena as BA         # noqa: E402
from backtest.concept_axes.theme_rank import stats as ST               # noqa: E402

N_FAKES = 400
PHI = 0.9
ACCEPT = (0.07, 0.13)
LAGS = (11, 22, 33)
SEED = 20261008
Z10 = 1.6448536269514722                    # 양측 p < 0.10 ⟺ |t| ≥ 1.645
OUT = Path(__file__).resolve().parent / "calibration"


def fake_t_stats(arena: pd.DataFrame, themes_of: Mapping[str, FrozenSet[int]],
                 members: Mapping[int, FrozenSet[str]], days: Sequence[str], lags: Sequence[int] = LAGS,
                 n_fakes: int = N_FAKES, seed: int = SEED) -> Dict[int, List[float]]:
    di = {d: i for i, d in enumerate(days)}
    out: Dict[int, List[float]] = {L: [] for L in lags}
    for i in range(n_fakes):
        z = ST.ar1_noise(members.keys(), len(days), PHI, np.random.default_rng([seed, i]))
        sig = [ST.fake_s(c, themes_of, members, {t: z[t][di[d]] for t in themes_of.get(c, ())})
               for d, c in zip(arena["scan_date"], arena["stock_code"])]
        ic, _ = ST.daily_ic(arena.assign(_f=sig), "_f", "ret_net")
        for L in lags:
            out[L].append(ST.hac_t(ic, L)["t_hac"])
    return out


def choose(t_by_lag: Mapping[int, Sequence[float]]) -> Dict[str, object]:
    rates = {L: sum(1 for t in ts if math.isfinite(t) and abs(t) >= Z10) / len(ts) for L, ts in t_by_lag.items()}
    for L in sorted(t_by_lag):
        if ACCEPT[0] <= rates[L] <= ACCEPT[1]:
            return {"mode": "hac", "lag": L, "rates": rates}
    return {"mode": "empirical", "lag": min(t_by_lag), "rates": rates}


def calibrated_p(t: float, calib: Mapping[str, object], lag: Optional[int] = None) -> float:
    if not math.isfinite(t):
        return float("nan")
    if calib["mode"] == "hac":
        return math.erfc(abs(t) / math.sqrt(2))
    fakes = [x for x in calib["t_fakes"][str(calib["lag"] if lag is None else lag)] if math.isfinite(x)]
    return (1 + sum(1 for x in fakes if abs(x) >= abs(t))) / (len(fakes) + 1)


def main(argv: Optional[Sequence[str]] = None) -> int:
    from backtest.concept_axes.candidate_ledger import run as CL
    from backtest.concept_axes.theme_rank import membership as MB
    from backtest.concept_axes.theme_rank import snapshot as SN
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-cut", type=int, required=True)
    a = ap.parse_args(argv)
    arena = BF.filled(pd.read_csv(BA.OUT / "arena.csv", dtype={"stock_code": str, "scan_date": str}))
    conn = CL._connect()
    snap = SN.load_snapshot(conn, MB.SNAP_DATE)
    conn.close()
    members = MB.restrict(snap.members, MB.eligible_themes(snap.theme_name, a.n_cut))
    days = sorted(arena["scan_date"].unique())
    t = fake_t_stats(arena, SN.invert(members), members, days)
    c = choose(t)
    calib = dict(c, t_fakes={str(L): v for L, v in t.items()}, n_fakes=N_FAKES, phi=PHI, accept=list(ACCEPT),
                 n_cut=a.n_cut, arena_md5=BA.md5(BA.OUT / "arena.csv"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "calib.json").write_text(json.dumps(calib, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# 도구 교정 결과(가짜 테마 신호)", "",
             f"- 가짜 {N_FAKES}개 · AR(1) φ={PHI} · 합격 [{ACCEPT[0]}, {ACCEPT[1]}] · N_cut {a.n_cut}",
             *[f"- lag {L}: p<0.10 거부율 {r:.3f}" for L, r in c["rates"].items()],
             f"- 선택: mode={c['mode']} · lag={c['lag']}", f"- calib.json md5: {BA.md5(OUT / 'calib.json')}"]
    (OUT / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

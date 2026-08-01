"""본실행. 사전등록된 격자만 돈다."""
from __future__ import annotations

TRUNCATION_COLUMNS = (
    "cell", "strategy_trades", "strategy_truncated", "strategy_mean_fills",
    "control_trades", "control_truncated", "control_mean_fills",
)


def required_outputs() -> tuple[str, ...]:
    return (
        "trades.parquet", "cells.csv", "by_year.csv",
        "by_bucket.csv", "truncation.csv", "calibration_scores.csv",
        "verdict.json",
    )


import json
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from lab.bands import BUCKETS, exogenous_quantiles, ladder, pit_quantiles
from lab.control import control_levels
from lab.data import load_daily
from lab.segments import find_segments
from lab.sim import simulate
from lab.stats import delta_t, mde, white_reality_check

START, END = "2021-01-04", "2026-07-31"
HOLD, COST = 20, 0.0021
C_GRID = (0.6, 0.8, 1.0)
SEED = 20260801


def _seed(*parts) -> int:
    """재현 가능한 시드. 내장 hash() 는 실행마다 달라져 대조군이 재현되지 않는다."""
    return zlib.crc32("|".join(str(p) for p in parts).encode()) ^ SEED


def _bucket_name(gain: float) -> str:
    lo = 0.0
    for b in BUCKETS:
        if gain >= b:
            lo = b
    return f">={lo:.2f}"


def flush_pending(pending, as_of: str):
    """창이 닫힌 표본만 history 로 내보낸다. (ready, still_pending) 반환.

    ⚠️ 이 게이트가 PIT 판본의 전부다. 아직 창이 열려 있는 구간의
       실현 하락폭을 분포에 넣으면 미래를 보고 밴드를 그리는 것이 된다.
    """
    ready, still = [], []
    for end_date, gain, realized in pending:
        (ready.append((gain, realized)) if end_date <= as_of
         else still.append((end_date, gain, realized)))
    return ready, still


def main() -> None:
    out = Path("out")
    out.mkdir(exist_ok=True)
    bars = load_daily(START, END)
    by_code = {c: g.reset_index(drop=True) for c, g in bars.groupby("stock_code", sort=False)}
    selected = json.loads((out / "selected_definitions.json").read_text(encoding="utf-8"))

    rows = []
    for d in selected:
        segs = sorted(find_segments(bars, d["variant"], d["lookback"], d["min_gain"]),
                      key=lambda s: s.peak_date)
        history: list[tuple[float, float]] = []
        pending: list[tuple[str, float, float]] = []   # (창 종료일, gain, 실현 하락폭)

        for seg in segs:
            ready, pending = flush_pending(pending, as_of=seg.peak_date)   # PIT 게이트
            history.extend(ready)

            g = by_code[seg.code]
            idx = g.index[g["date"] == seg.peak_date]
            if len(idx) == 0:
                continue
            i_peak = int(idx[0])
            window = g.iloc[i_peak + 1: i_peak + 1 + d["valid_days"] + HOLD].reset_index(drop=True)
            if window.empty:
                continue

            for version in ("pit", "exo"):
                q = pit_quantiles(history, seg.gain) if version == "pit" else exogenous_quantiles(seg.gain)
                if q is None:                     # PIT 표본 부족 → 진입 금지
                    continue
                for c in C_GRID:
                    levels = ladder(seg.peak_px, q[0], q[1], c)
                    t_s = simulate(window, levels, HOLD, COST, seg.code,
                                   max_fill_bars=d["valid_days"])
                    if t_s is None:
                        continue
                    rng = np.random.default_rng(_seed(seg.code, seg.peak_date, version, c))
                    t_c = simulate(window, control_levels(seg.peak_px, min(levels), rng),
                                   HOLD, COST, seg.code, max_fill_bars=d["valid_days"])
                    if t_c is None:
                        continue
                    rows.append({
                        "cell": f'{d["name"]}|{version}|c{c}',
                        "code": seg.code, "peak_date": seg.peak_date,
                        "year": seg.peak_date[:4], "bucket": _bucket_name(seg.gain),
                        "gain": seg.gain,
                        "ret_s": t_s.ret_net, "ret_c": t_c.ret_net,
                        "trunc_s": t_s.truncated, "trunc_c": t_c.truncated,
                        "fill_s": t_s.filled_n, "fill_c": t_c.filled_n,
                    })

            realized = 1.0 - float(window["low"].min()) / seg.peak_px
            pending.append((str(window["date"].iat[-1]), seg.gain, realized))

    df = pd.DataFrame(rows)
    df.to_parquet(out / "trades.parquet")
    df["d"] = df["ret_s"] - df["ret_c"]

    cell_rows = []
    for cell, grp in df.groupby("cell"):
        delta, t = delta_t(grp["ret_s"].to_numpy(), grp["ret_c"].to_numpy())
        cell_rows.append({"cell": cell, "n": len(grp), "n_codes": grp["code"].nunique(),
                          "delta": delta, "t": t,
                          "mean_s": grp["ret_s"].mean(), "mean_c": grp["ret_c"].mean()})
    pd.DataFrame(cell_rows).to_csv(out / "cells.csv", index=False)

    df.groupby("year")["d"].agg(["count", "mean"]).to_csv(out / "by_year.csv")
    df.groupby("bucket")["d"].agg(["count", "mean"]).to_csv(out / "by_bucket.csv")
    df.groupby("cell").agg(
        strategy_trades=("ret_s", "size"), strategy_truncated=("trunc_s", "sum"),
        strategy_mean_fills=("fill_s", "mean"),
        control_trades=("ret_c", "size"), control_truncated=("trunc_c", "sum"),
        control_mean_fills=("fill_c", "mean"),
    ).reset_index().to_csv(out / "truncation.csv", index=False)

    p = white_reality_check(df[["cell", "code", "d"]], b=1000, seed=SEED)
    sd = float(df["ret_s"].std(ddof=1))
    verdict = {"p": p, "n_trades": int(len(df)), "n_codes": int(df["code"].nunique()),
               "n_cells": int(df["cell"].nunique()), "sd": sd,
               "mde": mde(len(df), sd), "seed": SEED,
               "verdict": "PASS" if p < 0.05 else "FAIL"}
    (out / "verdict.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False))


if __name__ == "__main__":
    main()

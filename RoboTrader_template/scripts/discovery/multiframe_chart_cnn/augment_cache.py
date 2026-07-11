# scripts/discovery/multiframe_chart_cnn/augment_cache.py
"""기존 캐시 증강: 이미지 재렌더링 없이 스칼라·그리드라벨을 행 정렬 그대로 추가.

계획 2 사전등록 스펙은 6채널 이미지 + 변동성 스칼라 2개(lookback range%, atr%)
이며, TP/SL 은 폴드 학습창에서 {3x3, 3x5} 중 고른다. 기존 280K 캐시
(images.npy / meta.parquet)는 고정 3%/3% 라벨만 담고 스칼라가 없다 —
이 모듈이 build_dataset 의 순회를 EXACT 하게 재현해 스칼라와 {3x3,3x5} 라벨을
같은 행 순서로 재계산한다. 이미지는 다시 그리지 않는다(build_dataset 의
_build_hist_and_path 를 공유하므로 3x3 라벨·스칼라는 bit-identical).

끝에서 하드 정렬 게이트: 기존 meta.parquet 와 (stock_code, trade_date,
entry_time) 3-튜플이 행 단위로 일치하고 outcome_3x3 == meta.outcome,
realized_3x3 ≈ meta.realized_ret 임을 assert 로 검증한다 — 이것이 스칼라·3x5
라벨이 이미지에 올바르게 정렬됨을 증명한다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.discovery.intraday_rebound.db import MINUTE_DB, read_sql
from scripts.discovery.intraday_rebound.resample import resample_ohlcv
from scripts.discovery.intraday_rebound.universe import load_frozen_universe
from .build_dataset import (
    CACHE_DIR, DECISION_START, REGULAR_CLOSE, REGULAR_OPEN,
    _BARS_SQL, _DAYS_SQL, _build_hist_and_path,
    eligible_entry_days, iter_candidate_times,
)
from .label3d import label3d
from .scalars import vol_scalars

EXPECTED_N = 279899


def _grid_label(tp: float, sl: float) -> str:
    return f"{int(round(tp * 100))}x{int(round(sl * 100))}"


def parse_grid(s: str) -> list[tuple[float, float]]:
    out = []
    for tok in s.split(","):
        tp_s, sl_s = tok.strip().lower().split("x")
        out.append((int(tp_s) / 100.0, int(sl_s) / 100.0))
    return out


def build_sample_aux(day_bars_1m: dict, entry_day: str, entry_dt,
                     grid: list[tuple[float, float]],
                     stock_code: str | None = None, lookback_days: int = 3):
    """스칼라 + 그리드 라벨만 조립한다(이미지 없음).

    build_sample 과 동일한 _build_hist_and_path 로 hist·전방경로를 만들고,
    build_forward_path 를 한 번만 호출해 얻은 경로 위에서 grid 의 각 (tp,sl)
    에 대해 label3d 를 계산한다. build_sample 이 None 을 반환하던 조건(전방
    경로 없음 / hist 비어 있음)에서 동일하게 None 을 반환한다.
    """
    built = _build_hist_and_path(day_bars_1m, entry_day, entry_dt, lookback_days)
    if built is None:
        return None
    hist, fwd, _ = built
    entry_open, fh, fl, fo, fc = fwd
    labels = {(tp, sl): label3d(entry_open, fh, fl, fo, fc, tp, sl) for tp, sl in grid}
    scal = vol_scalars(resample_ohlcv(hist, 3))
    return {
        "scalars": scal,
        "labels": labels,
        "stock_code": stock_code,
        "trade_date": entry_day,
        "entry_time": pd.Timestamp(entry_dt),
    }


def augment(start: str, end: str, grid: list[tuple[float, float]],
            out_dir: Path = CACHE_DIR, every: int = 1, time_stride: int = 5,
            lookback_days: int = 3, cutoff_from_end_bars: int = 20) -> dict:
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
    entry_days = eligible_entry_days(days, every)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scalar_rows: list[np.ndarray] = []
    label_rows: list[dict] = []

    day_index = {d: i for i, d in enumerate(days)}
    for d in entry_days:
        i = day_index[d]
        window = days[max(0, i - lookback_days): i + 3]
        per_stock: dict[str, dict] = {code: {} for code in codes}
        for wd in window:
            raw = read_sql(_BARS_SQL, (wd, codes), MINUTE_DB)
            if raw.empty:
                continue
            raw["datetime"] = pd.to_datetime(raw["datetime"])
            t = raw["datetime"].dt.time
            raw = raw[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]
            for code, g in raw.groupby("stock_code", sort=False):
                per_stock[code][wd] = g.reset_index(drop=True)

        for code in codes:
            day_bars = per_stock[code]
            if d not in day_bars:
                continue
            bars3 = resample_ohlcv(day_bars[d], 3)
            for entry_dt in iter_candidate_times(bars3, DECISION_START, cutoff_from_end_bars,
                                                 stride=time_stride):
                s = build_sample_aux(day_bars, d, entry_dt, grid, stock_code=code,
                                     lookback_days=lookback_days)
                if s is None:
                    continue
                scalar_rows.append(s["scalars"])
                row = {"stock_code": s["stock_code"], "trade_date": s["trade_date"],
                       "entry_time": s["entry_time"]}
                for tp, sl in grid:
                    lab = _grid_label(tp, sl)
                    outcome, realized = s["labels"][(tp, sl)]
                    row[f"outcome_{lab}"] = outcome
                    row[f"realized_{lab}"] = realized
                label_rows.append(row)
        print(f"day {d}: samples_so_far={len(scalar_rows)}", flush=True)

    scalars_arr = (np.stack(scalar_rows).astype(np.float32)
                   if scalar_rows else np.zeros((0, 2), dtype=np.float32))
    np.save(out_dir / "scalars.npy", scalars_arr)
    labels_df = pd.DataFrame(label_rows)
    labels_df.to_parquet(out_dir / "labels_grid.parquet", index=False)

    _verify_alignment(labels_df, scalars_arr, out_dir, grid)

    return {"n": len(labels_df), "scalars_shape": scalars_arr.shape,
            "grid": [_grid_label(tp, sl) for tp, sl in grid]}


def _verify_alignment(labels_df: pd.DataFrame, scalars_arr: np.ndarray,
                      out_dir: Path, grid: list[tuple[float, float]]) -> None:
    """하드 정렬 게이트: 기존 meta.parquet 와 행 단위 일치를 assert 로 증명."""
    meta = pd.read_parquet(out_dir / "meta.parquet")
    n = len(labels_df)
    assert n == len(meta) == EXPECTED_N, (
        f"ALIGNMENT FAIL: 행 수 불일치 aug={n} meta={len(meta)} expected={EXPECTED_N}")
    assert len(scalars_arr) == n, (
        f"ALIGNMENT FAIL: scalars={len(scalars_arr)} labels={n}")

    for col in ("stock_code", "trade_date"):
        mism = (labels_df[col].to_numpy() != meta[col].to_numpy())
        assert not mism.any(), (
            f"ALIGNMENT FAIL: {col} 불일치 {int(mism.sum())} rows "
            f"(first at {int(np.argmax(mism))})")
    et_a = pd.to_datetime(labels_df["entry_time"]).to_numpy()
    et_m = pd.to_datetime(meta["entry_time"]).to_numpy()
    assert (et_a == et_m).all(), (
        f"ALIGNMENT FAIL: entry_time 불일치 {int((et_a != et_m).sum())} rows")

    # (0.03,0.03) 이 그리드에 있어야 3x3 대조가 가능.
    assert (0.03, 0.03) in grid, "grid 에 3x3 이 없어 정렬 검증 불가"
    out_mism = (labels_df["outcome_3x3"].to_numpy() != meta["outcome"].to_numpy())
    assert not out_mism.any(), (
        f"ALIGNMENT FAIL: outcome_3x3 vs meta.outcome 불일치 {int(out_mism.sum())} rows")
    assert np.allclose(labels_df["realized_3x3"].to_numpy(dtype=float),
                       meta["realized_ret"].to_numpy(dtype=float), atol=1e-6), (
        "ALIGNMENT FAIL: realized_3x3 vs meta.realized_ret 불일치 (atol=1e-6)")

    print(f"ALIGNMENT VERIFIED: {n}/{EXPECTED_N} rows, 3x3 labels match", flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20250721")
    ap.add_argument("--end", default="20260225")
    ap.add_argument("--grid", default="3x3,3x5")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--stride", type=int, default=5)
    ap.add_argument("--lookback", type=int, default=3)
    args = ap.parse_args()
    print(augment(args.start, args.end, parse_grid(args.grid), every=args.every,
                  time_stride=args.stride, lookback_days=args.lookback))

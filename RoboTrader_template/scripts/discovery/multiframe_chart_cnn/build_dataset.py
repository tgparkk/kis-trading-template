# scripts/discovery/multiframe_chart_cnn/build_dataset.py
"""데이터셋 추출: 199종목 전 거래일 전 시점 → (이미지·스칼라·라벨·메타) 캐시.

순수 조립부(iter_candidate_times/build_sample)는 DB 무관·테스트 고정.
build_dataset 만 DB를 순회한다. TP/SL 은 인자로 주입한다(계획 2 워크포워드가
폴드 학습에서 정한 값을 넣는다).

시점 stride: 예산 스파이크(Task 1)가 전 시점(3분 간격) 순회 시 약 610만
이미지·150GB 를 추정 — 15분 간격(3분봉 5개마다 1개, time_stride=5)으로
서브샘플링해 저장 용량을 관리 가능한 규모로 줄인다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.discovery.intraday_rebound.db import MINUTE_DB, read_sql
from scripts.discovery.intraday_rebound.resample import resample_ohlcv
from scripts.discovery.intraday_rebound.universe import load_frozen_universe
from .forward_path import build_forward_path
from .label3d import label3d
from .rasterize import render_multiframe
from .scalars import vol_scalars

REGULAR_OPEN = pd.Timestamp("09:00:00").time()
REGULAR_CLOSE = pd.Timestamp("15:30:00").time()
DECISION_START = pd.Timestamp("10:00:00").time()
CACHE_DIR = Path(__file__).parent / "_cache"

_DAYS_SQL = """
SELECT DISTINCT trade_date FROM minute_candles
WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date
"""
_BARS_SQL = """
SELECT stock_code, datetime, open, high, low, close, volume, amount
FROM minute_candles WHERE trade_date = %s AND stock_code = ANY(%s)
ORDER BY stock_code, datetime
"""


def iter_candidate_times(bars3: pd.DataFrame, decision_start, cutoff_from_end_bars: int,
                         stride: int = 1):
    if bars3 is None or len(bars3) == 0:
        return []
    dt = pd.to_datetime(bars3["datetime"])
    times = dt[dt.dt.time >= decision_start]
    if cutoff_from_end_bars > 0:
        times = times.iloc[:-cutoff_from_end_bars] if len(times) > cutoff_from_end_bars else times.iloc[0:0]
    times = times.iloc[::stride]
    return list(times)


def eligible_entry_days(days: list[str], sample_every_n_days: int) -> list[str]:
    # 3거래일 전방창을 온전히 갖춘 날짜만 진입일 후보로 남긴다(라벨은 3거래일
    # 전방이 필요하므로 마지막 2거래일은 창이 잘려 설계상 제외된다).
    return [d for i, d in enumerate(days)
            if i % sample_every_n_days == 0 and i + 3 <= len(days)]


def _build_hist_and_path(day_bars_1m: dict, entry_day: str, entry_dt,
                         lookback_days: int = 3):
    """진입 시점 이력(hist) + 3거래일 전방경로(fwd) + 유효 전방일수를 조립한다.

    build_sample 과 build_sample_aux 가 공유하는 순수 내부 조립부 — 이미지·
    스칼라·라벨을 계산하기 위한 입력을 bit-identical 하게 재현한다. build_sample
    이 None 을 반환하던 조건(진입일 부재 / hist 비어 있음 / 전방경로 없음)을
    그대로 유지한다.

    반환: (hist, fwd, n_forward_days) 또는 None.
    """
    # Plan-1 addendum(Task 7): 진입일 데이터만으로는 15분봉 채널이 절대 60봉을
    # 채울 수 없다(하루 최대 ~27봉) — 직전 lookback_days 거래일을 이미지
    # 이력에 포함한다. 단, 진입일 프레임은 여전히 entry_dt 이하로만 필터링해
    # look-ahead 를 막는다(직전 거래일은 날짜 자체가 entry_dt 이전이라 필터
    # 불필요).
    days_sorted = sorted(day_bars_1m.keys())
    if entry_day not in days_sorted:
        return None
    ei = days_sorted.index(entry_day)
    # Task 7 부가: horizon(최대 3거래일) 중 실제로 봉이 존재하는 거래일 수 —
    # 전방창이 종목별로 조기 절단됐는지(라벨 신뢰도) 메타로 노출한다.
    n_forward_days = sum(1 for d in days_sorted[ei:ei + 3] if len(day_bars_1m.get(d, [])) > 0)

    hist_days = days_sorted[max(0, ei - lookback_days): ei + 1]
    frames = []
    for d in hist_days:
        frame = day_bars_1m[d]
        if d == entry_day:
            frame = frame[pd.to_datetime(frame["datetime"]) <= entry_dt]
        frames.append(frame)
    hist = pd.concat(frames, ignore_index=True)
    if len(hist) == 0:
        return None

    fwd = build_forward_path(day_bars_1m, entry_day, entry_dt, horizon_days=3)
    if fwd is None:
        return None
    return hist, fwd, n_forward_days


def build_sample(day_bars_1m: dict, entry_day: str, entry_dt, tp: float, sl: float,
                 stock_code: str | None = None, lookback_days: int = 3):
    built = _build_hist_and_path(day_bars_1m, entry_day, entry_dt, lookback_days)
    if built is None:
        return None
    hist, fwd, n_forward_days = built
    entry_open, fh, fl, fo, fc = fwd
    outcome, realized = label3d(entry_open, fh, fl, fo, fc, tp, sl)

    image = render_multiframe(hist)
    scal = vol_scalars(resample_ohlcv(hist, 3))
    return {
        "image": image, "scalars": scal,
        "outcome": outcome, "realized_ret": realized,
        "stock_code": stock_code, "trade_date": entry_day,
        "entry_time": pd.Timestamp(entry_dt),
        "n_forward_days": n_forward_days,
    }


def build_dataset(start: str, end: str, tp: float = 0.03, sl: float = 0.03,
                  sample_every_n_days: int = 1, cutoff_from_end_bars: int = 20,
                  time_stride: int = 5, lookback_days: int = 3,
                  out_dir: Path = CACHE_DIR) -> dict:
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
    # 날짜 층화 추출: sample_every_n_days 간격의 거래일 중 3거래일 전방창이
    # 온전한 날짜만 진입일로(마지막 2거래일은 설계상 진입일에서 제외됨).
    entry_days = eligible_entry_days(days, sample_every_n_days)

    out_dir.mkdir(parents=True, exist_ok=True)
    images = []
    meta_rows = []

    # 3거래일 전방창(라벨) + lookback_days 거래일 후방창(15분봉 이미지 충전)을
    # 위해 각 진입일마다 [i-lookback_days, i+3) 범위의 봉이 필요.
    day_index = {d: i for i, d in enumerate(days)}
    for d in entry_days:
        i = day_index[d]
        window = days[max(0, i - lookback_days): i + 3]
        # 창 거래일 봉을 종목별로 로드.
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
                s = build_sample(day_bars, d, entry_dt, tp, sl, stock_code=code,
                                 lookback_days=lookback_days)
                if s is None:
                    continue
                # OVERRIDE 2: 샘플마다 즉시 uint8 로 변환 후 append(예산 스파이크가
                # float32 610만장=150GB 를 추정 — uint8 는 1/4 인 ~28GB). 리스트에
                # float32 이미지를 전부 쌓았다가 끝에 한 번에 변환하면 변환 순간
                # float32+uint8 스택이 동시에 메모리에 존재해 피크 RAM 이 4배로
                # 튄다 — 샘플 단위 변환으로 피크를 uint8 스택 크기로 제한한다.
                # render_multiframe/build_sample 은 float32 [0,1] 을 그대로
                # 반환한다(순수함수 계약 불변); 여기서만 0~255 로 스케일해 변환.
                img_u8 = (s["image"] * 255.0).round().clip(0, 255).astype(np.uint8)
                images.append(img_u8)
                meta_rows.append({k: s[k] for k in
                                  ("outcome", "realized_ret", "stock_code", "trade_date",
                                   "entry_time", "n_forward_days")})
        print(f"day {d}: samples_so_far={len(images)}")

    if not images:
        return {"n": 0, "image_shape": None, "dtype": None, "images_gb": 0.0,
                "pct_tp": float("nan"), "pct_sl": float("nan"),
                "pct_timeout": float("nan")}
    # 소비자는 로드 후 반드시 255.0 으로 나눠 [0,1] 로 복원해야 한다:
    #   images = np.load(...).astype(np.float32) / 255.0
    arr = np.stack(images)
    np.save(out_dir / "images.npy", arr)
    meta = pd.DataFrame(meta_rows)
    meta.to_parquet(out_dir / "meta.parquet", index=False)
    return {"n": len(images), "image_shape": arr.shape,
            "dtype": str(arr.dtype),
            "images_gb": arr.nbytes / 1e9,
            "pct_tp": float((meta["outcome"] == "tp").mean()),
            "pct_sl": float((meta["outcome"] == "sl").mean()),
            "pct_timeout": float((meta["outcome"] == "timeout").mean())}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20260601")
    ap.add_argument("--end", default="20260607")
    ap.add_argument("--tp", type=float, default=0.03)
    ap.add_argument("--sl", type=float, default=0.03)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--stride", type=int, default=5)
    ap.add_argument("--lookback", type=int, default=3)
    args = ap.parse_args()
    print(build_dataset(args.start, args.end, args.tp, args.sl, args.every,
                        time_stride=args.stride, lookback_days=args.lookback))

# scripts/discovery/intraday_rebound/shape_samples.py
"""사람이 눈으로 판별하는 시각화용 캔들 샘플 추출.

목적: -6% 급락 직전 20봉(pre) + 급락봉(entry) + 이후 20봉(post)을 실제 캔들
그대로 뽑아, 사람이 반등(up)/지속하락(down)을 눈으로 맞춰보게 한다. 이 모듈은
백테스트도, 매매 룰도, 차트도 만들지 않는다 — JSON 데이터만 낸다.

이벤트 정의는 shape_events.py 와 완전히 동일하다 (같은 tf/lookback/drop_pct/
forward/theta/유니버스/기간): 여기서는 그 모듈의 상수와 순수 함수를 그대로
재사용하고(find_first_event_idx, build_event_row, zscore_rows, _window_label,
_filter_regular_session, _DAYS_SQL, _BARS_SQL), 프라이빗 헬퍼는 새로 만들지
않는다.

샘플링 대상은 shape_events 의 "종목-일당 이벤트 1개" 전체 모집단(4,323건)
중에서: outcome 이 up/down 인 것 AND entry봉 이후 forward bar 가 20개(=
FORWARD_BARS, forward_min=60분과 동일) 전부 남아 있는 것만이다 — reveal이
항상 꽉 찬 20봉을 보여주도록. 그 부분모집단에서 60 up + 60 down 을 4개
기간창(W1..W4)에 최대한 고르게(칸당 15개 목표) 층화추출한다.

euclid_cluster 는 shape_events 의 8-클러스터 KMeans를 여기서 다시 적합한다
(전체 4,323건의 z-정규화 w0..w19 기준, k=8/n_init=10/seed=42 — shape_events
의 compute_stats._cluster_stats 와 동일한 파라미터). 표본 이벤트는 그 적합된
모델로 최근접 클러스터에 배정될 뿐이다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from .db import MINUTE_DB, read_sql
from .resample import resample_ohlcv
from .shape_events import (
    _BARS_SQL,
    _DAYS_SQL,
    EVENT_COLUMNS,
    FORWARD_BARS,
    LOOKBACK_BARS,
    MIN_LOOKBACK_BARS,
    START_DATE,
    END_DATE,
    W_COLS,
    _filter_regular_session,
    build_event_row,
    find_first_event_idx,
    zscore_rows,
)
from .universe import load_frozen_universe

CACHE_DIR = Path(__file__).parent / "_cache"
SAMPLES_JSON = CACHE_DIR / "shape_samples.json"

N_SAMPLE_PER_CLASS = 60
WINDOWS = ["W1", "W2", "W3", "W4"]
SEED = 42
CLUSTER_K = 8

UP_TARGET = 103.0
DN_TARGET = 97.0
_TOUCH_EPS = 1e-6


# ---------------------------------------------------------------------------
# DB-independent helpers
# ---------------------------------------------------------------------------

def _prior_high_series(bars: pd.DataFrame) -> np.ndarray:
    """find_first_event_idx 내부 계산과 동일한 규칙(rolling(20,
    min_periods=5).max().shift(1))으로 prior_high 시계열을 낸다. 그 함수는
    조건 판정에만 쓰고 prior_high 값 자체를 반환하지 않으므로, drop_pct
    계산을 위해 같은 상수로 다시 계산한다.
    """
    high = bars["high"].to_numpy(dtype=float)
    return (
        pd.Series(high)
        .rolling(LOOKBACK_BARS, min_periods=MIN_LOOKBACK_BARS)
        .max()
        .shift(1)
        .to_numpy()
    )


def build_eligible_record(bars: pd.DataFrame, idx: int, row: dict) -> dict | None:
    """순수 함수 (DB 무관): 이미 계산된 event row(build_event_row 출력) +
    원본 bars/idx -> 샘플링 후보 레코드 dict, 또는 자격 미달이면 None.

    자격: outcome 이 up/down 이고, idx 이후 forward bar 가 FORWARD_BARS(20)개
    전부 남아 있어야 한다 (n-1 >= idx + FORWARD_BARS).
    """
    outcome = row["outcome"]
    if outcome not in ("up", "down"):
        return None

    n = len(bars)
    if idx + FORWARD_BARS > n - 1:
        return None

    prior_high = float(_prior_high_series(bars)[idx])
    ohlc = bars[["open", "high", "low", "close"]].to_numpy(dtype=float)
    entry_close = float(ohlc[idx, 3])
    trade_date = row["trade_date"]

    return {
        "code": row["stock_code"],
        "date": f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}",
        "entry_time": bars["datetime"].iloc[idx].strftime("%H:%M"),
        "window": row["window"],
        "outcome": outcome,
        "drop_pct": entry_close / prior_high - 1.0,
        "pre_vol": row["pre_vol"],
        "w": [row[f"w{j}"] for j in range(LOOKBACK_BARS)],
        "entry_close": entry_close,
        "pre_ohlc": ohlc[idx - LOOKBACK_BARS: idx],
        "entry_ohlc": ohlc[idx],
        "post_ohlc": ohlc[idx + 1: idx + 1 + FORWARD_BARS],
    }


def fit_cluster_model(full_events: pd.DataFrame, k: int = CLUSTER_K,
                      seed: int = SEED) -> KMeans:
    """전체 이벤트 모집단(w0..w19, z-정규화)에 KMeans 를 적합한다."""
    w_matrix = full_events[W_COLS].to_numpy(dtype=float)
    z = zscore_rows(w_matrix)
    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    km.fit(z)
    return km


def assign_cluster(km: KMeans, w: list[float]) -> int:
    """표본 이벤트 1건의 raw w0..w19 -> 적합된 모델 기준 최근접 클러스터."""
    z = zscore_rows(np.array([w], dtype=float))
    return int(km.predict(z)[0])


def _normalize_ohlc(arr: np.ndarray, entry_close: float) -> list[list[float]]:
    """가격을 entry_close 로 나누고 100 을 곱해 절대 가격대를 지운다."""
    scale = 100.0 / entry_close
    return np.round(arr * scale, 3).tolist()


def _find_touch_offset(post: list[list[float]], outcome: str) -> int:
    """post(정규화된 [o,h,l,c] 리스트) 안에서 outcome 이 결정된 첫 봉의
    1-based offset. up 이면 고가가 UP_TARGET 을 처음 건드리는 봉, down 이면
    저가가 DN_TARGET 을 처음 건드리는 봉.
    """
    for offset, bar in enumerate(post, start=1):
        _, hi, lo, _ = bar
        if outcome == "up" and hi >= UP_TARGET - _TOUCH_EPS:
            return offset
        if outcome == "down" and lo <= DN_TARGET + _TOUCH_EPS:
            return offset
    raise ValueError(f"outcome={outcome!r} never touches its barrier within post window")


def _finalize_event(record: dict, km: KMeans, event_id: str) -> dict:
    """정규화 + 클러스터 배정 + touch_offset + 새너티 어서션을 거친 최종 이벤트 dict."""
    entry_close = record["entry_close"]

    pre = _normalize_ohlc(record["pre_ohlc"], entry_close)
    entry = [round(float(x), 3) for x in
             (np.asarray(record["entry_ohlc"], dtype=float) * (100.0 / entry_close))]
    post = _normalize_ohlc(record["post_ohlc"], entry_close)

    outcome = record["outcome"]
    touch_offset = _find_touch_offset(post, outcome)

    if outcome == "up":
        touched_highs = [bar[1] for bar in post[:touch_offset]]
        assert max(touched_highs) >= UP_TARGET - _TOUCH_EPS, (
            f"{record['code']} {record['date']}: up outcome but post[:touch_offset] "
            "never reaches up_target"
        )
    else:
        touched_lows = [bar[2] for bar in post[:touch_offset]]
        assert min(touched_lows) <= DN_TARGET + _TOUCH_EPS, (
            f"{record['code']} {record['date']}: down outcome but post[:touch_offset] "
            "never reaches dn_target"
        )

    cluster = assign_cluster(km, record["w"])

    return {
        "id": event_id,
        "code": record["code"],
        "date": record["date"],
        "entry_time": record["entry_time"],
        "window": record["window"],
        "outcome": outcome,
        "drop_pct": round(record["drop_pct"], 4),
        "pre_vol": round(record["pre_vol"], 4),
        "euclid_cluster": cluster,
        "pre": pre,
        "entry": entry,
        "post": post,
        "up_target": UP_TARGET,
        "dn_target": DN_TARGET,
        "touch_offset": touch_offset,
    }


def _bucket_by_window(records: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {w: [] for w in WINDOWS}
    for r in records:
        buckets[r["window"]].append(r)
    return buckets


def stratified_sample(records: list[dict], target: int,
                      rng: np.random.Generator) -> list[dict]:
    """records(단일 outcome class 모집단)에서 target 개를 WINDOWS 에 최대한
    고르게(칸당 target/len(WINDOWS)개 목표) 뽑는다. 한 칸이 모자라면, 남는
    부족분은 그때그때 잔여수가 가장 많은 칸에서 하나씩 채운다(반복마다
    최댓값을 다시 고르므로 자연히 여러 큰 칸에 분산된다).
    """
    buckets = _bucket_by_window(records)
    base = target // len(WINDOWS)

    selected: list[dict] = []
    remaining: dict[str, list[dict]] = {}
    for w in WINDOWS:
        bucket = buckets[w]
        order = rng.permutation(len(bucket))
        shuffled = [bucket[i] for i in order]
        take = min(base, len(shuffled))
        selected.extend(shuffled[:take])
        remaining[w] = shuffled[take:]

    need = target - len(selected)
    while need > 0:
        w_best = max(remaining, key=lambda w: len(remaining[w]))
        if not remaining[w_best]:
            raise ValueError(
                f"not enough eligible events to reach target={target} "
                f"(selected={len(selected)})"
            )
        selected.append(remaining[w_best].pop(0))
        need -= 1

    return selected


def sample_events(eligible: list[dict], km: KMeans,
                  rng: np.random.Generator) -> list[dict]:
    """eligible 모집단 -> 60 up + 60 down 층화추출 -> 셔플 -> 최종 이벤트 리스트."""
    up = [r for r in eligible if r["outcome"] == "up"]
    down = [r for r in eligible if r["outcome"] == "down"]

    sampled_up = stratified_sample(up, N_SAMPLE_PER_CLASS, rng)
    sampled_down = stratified_sample(down, N_SAMPLE_PER_CLASS, rng)

    combined = sampled_up + sampled_down
    order = rng.permutation(len(combined))
    shuffled = [combined[i] for i in order]

    return [_finalize_event(r, km, f"E{i + 1:03d}") for i, r in enumerate(shuffled)]


def _by_window_summary(events: list[dict]) -> dict:
    summary = {w: {"up": 0, "down": 0} for w in WINDOWS}
    for e in events:
        summary[e["window"]][e["outcome"]] += 1
    return summary


# ---------------------------------------------------------------------------
# DB-dependent extraction
# ---------------------------------------------------------------------------

def build_events_and_pool(start: str = START_DATE,
                          end: str = END_DATE) -> tuple[pd.DataFrame, list[dict]]:
    """day -> stock(정규장) 루프. shape_events.build_events() 와 같은 스캔을
    한 번만 돌면서, (1) 전체 이벤트 표(클러스터 적합용)와 (2) 샘플링 후보
    풀(자격 미달 제외)을 동시에 만든다.
    """
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()

    full_rows: list[dict] = []
    eligible: list[dict] = []

    for i, day in enumerate(days):
        raw = read_sql(_BARS_SQL, (day, codes), MINUTE_DB)
        if raw.empty:
            continue
        raw["datetime"] = pd.to_datetime(raw["datetime"])
        raw = _filter_regular_session(raw)
        if raw.empty:
            continue

        for code, g in raw.groupby("stock_code", sort=False):
            bars = resample_ohlcv(g, 3)
            if len(bars) < MIN_LOOKBACK_BARS + 2:
                continue

            idx = find_first_event_idx(bars)
            if idx is None:
                continue

            row = build_event_row(bars, idx, day, code)
            full_rows.append(row)

            record = build_eligible_record(bars, idx, row)
            if record is not None:
                eligible.append(record)

        if (i + 1) % 20 == 0:
            print(f"day {i + 1}/{len(days)} {day} full={len(full_rows)} "
                  f"eligible={len(eligible)}")

    full_events = (pd.DataFrame(full_rows, columns=EVENT_COLUMNS) if full_rows
                  else pd.DataFrame(columns=EVENT_COLUMNS))
    return full_events, eligible


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("building full event set + eligible pool...")
    full_events, eligible = build_events_and_pool()
    n_up = sum(1 for r in eligible if r["outcome"] == "up")
    n_down = sum(1 for r in eligible if r["outcome"] == "down")
    print(f"full_events n={len(full_events)} eligible n={len(eligible)} "
          f"(up={n_up} down={n_down})")

    print("fitting cluster model...")
    km = fit_cluster_model(full_events)

    rng = np.random.default_rng(SEED)
    events = sample_events(eligible, km, rng)

    payload = {
        "n": len(events),
        "counts": {
            "up": sum(1 for e in events if e["outcome"] == "up"),
            "down": sum(1 for e in events if e["outcome"] == "down"),
        },
        "by_window": _by_window_summary(events),
        "events": events,
    }

    with open(SAMPLES_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"wrote {SAMPLES_JSON}")


if __name__ == "__main__":
    main()

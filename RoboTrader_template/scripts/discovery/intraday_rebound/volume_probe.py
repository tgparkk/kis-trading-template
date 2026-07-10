# scripts/discovery/intraday_rebound/volume_probe.py
"""거래량 궤적(volume trajectory) 프로브: 가격 모양(P) vs 거래량 모양(V) vs
결합(PV)이 급락 후 반등/지속하락(outcome)과 연관이 있는가.

거래량은 지금까지 스칼라 요약(vol_z, vol_ratio_drop, log_amount_cum)으로만
검정돼 왔고 전부 비유의였다. 궤적 자체는 아직 검정된 적이 없다.

거래량은 극단적으로 두꺼운 꼬리(heavy-tailed)를 가지므로, 행 단위
z-정규화 전에 반드시 log1p(volume) 을 먼저 취한다 -- 원시 거래량을 바로
z-정규화하면 하루 중 몇 봉에서 튀는 대량거래가 행 표준편차를 지배해 나머지
19봉의 형태 정보를 지워버린다. log1p 는 거래량 0 도 안전하게 다룬다
(log(0) 미정의를 회피).

세 임베딩(20봉 궤적 기준, 이벤트 정의는 shape_events.py 와 완전히 동일):
  P  = z-정규화 종가 w0..w19 (shape_events.zscore_rows 재사용)
  V  = z-정규화 log1p(거래량) v0..v19
  PV = hstack([P, V]) / sqrt(2) -- 두 블록이 총분산에 동일하게 기여하도록
       스케일

세 임베딩 모두 KMeans(k=8, n_init=10, seed=42) 로 군집화하고(shape_compare
와 동일 파라미터), shape_compare 의 옴니버스 블록-순열 검정(그대로 재사용)
으로 채점한다 -- 네 스코어링(P/V/PV/vol_slope 버킷) 모두 동일한 B=3000
순열 초안을 공유한다(shape_compare.py 의 관행과 동일).

추가로 스칼라 하나(vol_slope = log1p(v0..v19) 에 대한 최소자승 기울기,
x=0..19)를 5분위 버킷으로 나눠 같은 스코어러로 채점한다 -- "거래량이 마르는
중이냐 쌓이는 중이냐"를 직접 묻는 저비용 체크.

마지막으로, 사람이 눈으로 판별하는 기존 표본(shape_samples.json, 120건)에
거래량을 조인해 shape_samples_vol.json 으로 재발행한다. 결정론적 재현이
아니라 기존 표본을 (code, date, entry_time) 으로 다시 찾아 거래량만
얹는다.

이것은 백테스트가 아니고 매매 룰을 만들지 않으며 해석도 하지 않는다 --
세 방법 + 1개 스칼라의 T_obs/p/edge 숫자만 낸다.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .db import MINUTE_DB, read_sql
from .resample import resample_ohlcv
from .shape_compare import (
    B_PERM,
    K as CLUSTER_K,
    PERM_SEED,
    SEED as SHAPE_SEED,
    euclidean_kmeans,
    make_blocks,
    omnibus_test,
)
from .shape_events import (
    CACHE_DIR,
    END_DATE,
    EVENT_COLUMNS,
    FORWARD_BARS,
    LOOKBACK_BARS,
    MIN_LOOKBACK_BARS,
    OUTCOME_LABELS,
    START_DATE,
    TF,
    W_COLS,
    _BARS_SQL,
    _DAYS_SQL,
    _filter_regular_session,
    build_event_row,
    find_first_event_idx,
    zscore_rows,
)
from .shape_samples import SAMPLES_JSON
from .universe import load_frozen_universe

V_COLS = [f"v{i}" for i in range(LOOKBACK_BARS)]
EVENT_COLUMNS_VOL = EVENT_COLUMNS + V_COLS + ["v_entry"]

EVENTS_PARQUET_VOL = CACHE_DIR / "shape_events_d6_vol.parquet"
PROBE_JSON = CACHE_DIR / "volume_probe.json"
SAMPLES_JSON_VOL = CACHE_DIR / "shape_samples_vol.json"

N_SLOPE_BUCKETS = 5


# ---------------------------------------------------------------------------
# Step 1: event extraction with volume (mirrors shape_events.build_events,
# reusing its event-definition helpers -- only the volume columns are new)
# ---------------------------------------------------------------------------

def build_event_row_with_volume(bars: pd.DataFrame, idx: int, trade_date: str,
                                stock_code: str) -> dict:
    """build_event_row(재사용) 출력에 거래량 컬럼(v0..v19, v_entry)만 얹는다."""
    row = build_event_row(bars, idx, trade_date, stock_code)
    volume = bars["volume"].to_numpy(dtype=float)
    v = volume[idx - LOOKBACK_BARS: idx]
    for i in range(LOOKBACK_BARS):
        row[f"v{i}"] = float(v[i])
    row["v_entry"] = float(volume[idx])
    return row


def build_events(start: str = START_DATE, end: str = END_DATE) -> pd.DataFrame:
    """shape_events.build_events 와 동일한 day -> stock(정규장) 루프
    (find_first_event_idx/_filter_regular_session 재사용) + 거래량 컬럼만 추가.
    """
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()

    rows: list[dict] = []
    for i, day in enumerate(days):
        raw = read_sql(_BARS_SQL, (day, codes), MINUTE_DB)
        if raw.empty:
            continue
        raw["datetime"] = pd.to_datetime(raw["datetime"])
        raw = _filter_regular_session(raw)
        if raw.empty:
            continue

        for code, g in raw.groupby("stock_code", sort=False):
            bars = resample_ohlcv(g, TF)
            if len(bars) < MIN_LOOKBACK_BARS + 2:
                continue

            idx = find_first_event_idx(bars)
            if idx is None:
                continue

            rows.append(build_event_row_with_volume(bars, idx, day, code))

        if (i + 1) % 20 == 0:
            print(f"day {i + 1}/{len(days)} {day} events_so_far={len(rows)}")

    if not rows:
        return pd.DataFrame(columns=EVENT_COLUMNS_VOL)
    return pd.DataFrame(rows, columns=EVENT_COLUMNS_VOL)


def summary_stats(events: pd.DataFrame) -> dict:
    n_total = len(events)
    n_dates = int(events["trade_date"].nunique()) if n_total else 0
    vc = events["outcome"].value_counts()
    counts = {k: int(vc.get(k, 0)) for k in OUTCOME_LABELS}
    return {"n": n_total, "n_dates": n_dates, "counts": counts}


# ---------------------------------------------------------------------------
# Step 2: three embeddings (P / V / PV)
# ---------------------------------------------------------------------------

def _log1p_zscore(matrix: np.ndarray) -> np.ndarray:
    """log1p 후 행 단위 z-정규화 (zscore_rows 재사용, flat 행 -> 0)."""
    return zscore_rows(np.log1p(matrix))


def build_price_matrix(events: pd.DataFrame) -> np.ndarray:
    return zscore_rows(events[W_COLS].to_numpy(dtype=float))


def build_volume_matrix(events: pd.DataFrame) -> np.ndarray:
    return _log1p_zscore(events[V_COLS].to_numpy(dtype=float))


def build_price_volume_matrix(P: np.ndarray, V: np.ndarray) -> np.ndarray:
    return np.hstack([P, V]) / np.sqrt(2.0)


# ---------------------------------------------------------------------------
# Step 3: vol_slope scalar + quintile buckets
# ---------------------------------------------------------------------------

def compute_vol_slope(v_matrix: np.ndarray) -> np.ndarray:
    """log1p(v0..v19) 에 대한 최소자승 기울기(행마다, x=0..19)."""
    log_v = np.log1p(v_matrix)
    n = log_v.shape[1]
    x = np.arange(n, dtype=float)
    x_centered = x - x.mean()
    denom = float(np.sum(x_centered ** 2))
    y_centered = log_v - log_v.mean(axis=1, keepdims=True)
    return (y_centered @ x_centered) / denom


def slope_quintile_buckets(vol_slope: np.ndarray,
                           n_buckets: int = N_SLOPE_BUCKETS) -> np.ndarray:
    codes = pd.qcut(pd.Series(vol_slope), n_buckets, labels=False, duplicates="drop")
    assert not codes.isna().any(), "vol_slope quintile bucketing produced NaN"
    return codes.to_numpy(dtype=int)


# ---------------------------------------------------------------------------
# scoring orchestration: one shared permutation null across all four scorers
# ---------------------------------------------------------------------------

def _format_method(res: dict) -> dict:
    return {
        "T": res["T_obs"],
        "null_med": res["null_median"],
        "null_p95": res["null_p95"],
        "p": res["p"],
        "clusters": [
            {"cluster": c["cluster"], "n": c["n"], "pct_up": c["pct_up"],
             "pct_dn": c["pct_dn"], "edge_pp": c["edge_pp"], "z": c["z"]}
            for c in res["clusters"]
        ],
    }


def _format_slope_buckets(res: dict, bucket_labels: np.ndarray,
                          vol_slope: np.ndarray) -> dict:
    buckets = []
    for c in res["clusters"]:
        q = c["cluster"]
        mask = bucket_labels == q
        mean_slope = round(float(np.mean(vol_slope[mask])), 6) if mask.any() else None
        buckets.append({
            "q": q, "n": c["n"], "pct_up": c["pct_up"], "pct_dn": c["pct_dn"],
            "edge_pp": c["edge_pp"], "z": c["z"], "mean_slope": mean_slope,
        })
    return {"T": res["T_obs"], "null_med": res["null_median"], "p": res["p"],
           "buckets": buckets}


def score_all(events: pd.DataFrame) -> dict:
    """P/V/PV(k=8 KMeans) + vol_slope 5분위 버킷을 동일한 옴니버스 블록-순열
    검정(shape_compare.omnibus_test 재사용)으로 채점한다. 네 호출 모두 같은
    B=3000 순열 초안을 공유한다(첫 호출에서 만든 perm_up/perm_down 재사용).
    """
    outcomes = events["outcome"].to_numpy()
    pre_vol = events["pre_vol"].to_numpy(dtype=float)
    trade_date = events["trade_date"].to_numpy()
    blocks = make_blocks(trade_date, pre_vol)

    P = build_price_matrix(events)
    V = build_volume_matrix(events)
    PV = build_price_volume_matrix(P, V)

    labels_price = euclidean_kmeans(P, k=CLUSTER_K, seed=SHAPE_SEED)
    res_price, perm_up, perm_down = omnibus_test(
        labels_price, outcomes, pre_vol, k=CLUSTER_K, blocks=blocks,
        B=B_PERM, seed=PERM_SEED)

    labels_volume = euclidean_kmeans(V, k=CLUSTER_K, seed=SHAPE_SEED)
    res_volume, _, _ = omnibus_test(labels_volume, outcomes, pre_vol, k=CLUSTER_K,
                                    perm_up=perm_up, perm_down=perm_down)

    labels_pv = euclidean_kmeans(PV, k=CLUSTER_K, seed=SHAPE_SEED)
    res_pv, _, _ = omnibus_test(labels_pv, outcomes, pre_vol, k=CLUSTER_K,
                                perm_up=perm_up, perm_down=perm_down)

    vol_slope = compute_vol_slope(events[V_COLS].to_numpy(dtype=float))
    bucket_labels = slope_quintile_buckets(vol_slope)
    n_buckets = int(bucket_labels.max()) + 1
    res_slope, _, _ = omnibus_test(bucket_labels, outcomes, pre_vol, k=n_buckets,
                                   perm_up=perm_up, perm_down=perm_down)

    return {
        "methods": {
            "price": _format_method(res_price),
            "volume": _format_method(res_volume),
            "price_volume": _format_method(res_pv),
        },
        "vol_slope_buckets": _format_slope_buckets(res_slope, bucket_labels, vol_slope),
    }


# ---------------------------------------------------------------------------
# Step 4: re-emit the human sample with volumes (join on code/date/entry_time)
# ---------------------------------------------------------------------------

def _load_existing_samples() -> dict:
    with open(SAMPLES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def _group_by_trade_date(events: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for e in events:
        trade_date = e["date"].replace("-", "")
        groups.setdefault(trade_date, []).append(e)
    return groups


def _relocate_event_volumes(bars: pd.DataFrame, entry_time: str) -> dict:
    """이미 알려진 이벤트(code,date)의 정규장 봉에서 find_first_event_idx
    (재사용)로 idx 를 다시 찾고(entry_time 일치를 검증), pre/entry/post
    거래량과 vol_ref(중앙값, 0이면 평균, 그것도 0이면 1.0)를 뽑는다.
    """
    idx = find_first_event_idx(bars)
    if idx is None:
        raise ValueError("event no longer reproducible: find_first_event_idx returned None")

    actual_time = bars["datetime"].iloc[idx].strftime("%H:%M")
    if actual_time != entry_time:
        raise ValueError(f"entry_time mismatch: expected {entry_time} got {actual_time}")

    n = len(bars)
    if idx + FORWARD_BARS > n - 1:
        raise ValueError("not enough forward bars to fill post_vol_bars")

    volume = bars["volume"].to_numpy(dtype=float)
    pre = [float(x) for x in volume[idx - LOOKBACK_BARS: idx]]
    entry_vol = float(volume[idx])
    post = [float(x) for x in volume[idx + 1: idx + 1 + FORWARD_BARS]]

    ref = float(np.median(pre))
    if ref == 0:
        ref = float(np.mean(pre))
    if ref == 0:
        ref = 1.0

    return {"pre_vol_bars": pre, "entry_vol": entry_vol, "post_vol_bars": post,
           "vol_ref": ref}


def assert_same_ids_and_outcomes(original: dict, regenerated: dict) -> None:
    orig_events = original["events"]
    new_events = regenerated["events"]
    assert len(orig_events) == len(new_events), (
        f"event count mismatch: {len(orig_events)} != {len(new_events)}")
    for o, n in zip(orig_events, new_events):
        assert o["id"] == n["id"], f"id order mismatch: {o['id']!r} != {n['id']!r}"
        assert o["outcome"] == n["outcome"], (
            f"outcome mismatch for {o['id']}: {o['outcome']!r} != {n['outcome']!r}")


def build_samples_with_volume() -> dict:
    """기존 shape_samples.json 을 로드해 같은 120건에 거래량만 조인한다."""
    payload = _load_existing_samples()
    events = payload["events"]
    groups = _group_by_trade_date(events)

    volume_by_id: dict[str, dict] = {}
    for trade_date, evs in groups.items():
        codes = sorted({e["code"] for e in evs})
        raw = read_sql(_BARS_SQL, (trade_date, codes), MINUTE_DB)
        if raw.empty:
            raise ValueError(f"no bars returned for trade_date={trade_date} codes={codes}")
        raw["datetime"] = pd.to_datetime(raw["datetime"])
        raw = _filter_regular_session(raw)
        by_code = dict(tuple(raw.groupby("stock_code", sort=False)))
        for e in evs:
            g = by_code.get(e["code"])
            if g is None:
                raise ValueError(
                    f"no bars for event {e['id']} code={e['code']} date={trade_date}")
            bars = resample_ohlcv(g, TF)
            volume_by_id[e["id"]] = _relocate_event_volumes(bars, e["entry_time"])

    new_events = []
    for e in events:
        new_e = dict(e)
        new_e.update(volume_by_id[e["id"]])
        new_events.append(new_e)

    new_payload = dict(payload)
    new_payload["events"] = new_events
    return new_payload


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("step1: building events with volume...")
    events = build_events()
    print(f"events built: n={len(events)}")
    events.to_parquet(EVENTS_PARQUET_VOL, index=False)
    print(f"wrote {EVENTS_PARQUET_VOL}")

    print("step2+3: scoring price/volume/price_volume + vol_slope buckets...")
    scored = score_all(events)

    out = {**summary_stats(events), **scored}
    with open(PROBE_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=True, indent=2)
    print(f"wrote {PROBE_JSON}")

    print("step4: re-emitting human sample with volumes...")
    original = _load_existing_samples()
    regenerated = build_samples_with_volume()
    assert_same_ids_and_outcomes(original, regenerated)
    with open(SAMPLES_JSON_VOL, "w", encoding="utf-8") as f:
        json.dump(regenerated, f, ensure_ascii=False)
    print(f"wrote {SAMPLES_JSON_VOL}")

    print("done.")


if __name__ == "__main__":
    main()

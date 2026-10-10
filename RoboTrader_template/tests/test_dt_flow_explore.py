"""dt_flow_explore 최소 시험 — 날짜 안 꼬리 Δ 를 손으로 만든 작은 표 2개로 확인 (DB 없음)."""
import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.dt_flow_explore import explore as EX


def test_within_day_delta_hand_table_1():
    # 날 1: 꼬리 −5 vs 나머지 평균 2.5 → −7.5 (n 5) · 날 2: 꼬리 평균 1 vs 나머지 5 → −4 (n 4)
    # 날 3: 꼬리만 있음 → 무효(빠짐). 가중 = (5·−7.5 + 4·−4) / 9
    df = pd.DataFrame({
        "scan_date": ["d1"] * 5 + ["d2"] * 4 + ["d3"],
        "tail": [True, False, False, False, False, True, True, False, False, True],
        "y": [-5, 1, 2, 3, 4, 0, 2, 4, 6, 100],
    })
    assert EX.within_day_delta(df) == pytest.approx((5 * -7.5 + 4 * -4) / 9)


def test_tail_frame_and_sample_hand_table_2():
    # 날 A: 후보 10 · 값 1..10 · 하위 꼬리 = pct ≤ 0.2 → 값 1·2
    # 날 B: 후보 9 → 후보 < 10 으로 빠짐 · 날 C: 후보 10 중 3 결측 → 커버리지 70% 로 빠짐
    a = pd.DataFrame({"scan_date": "A", "stock_code": [f"{i:02d}" for i in range(10)],
                      "v": np.arange(1, 11, dtype=float)})
    b = pd.DataFrame({"scan_date": "B", "stock_code": [f"{i:02d}" for i in range(9)],
                      "v": np.arange(1, 10, dtype=float)})
    c = pd.DataFrame({"scan_date": "C", "stock_code": [f"{i:02d}" for i in range(10)],
                      "v": [np.nan] * 3 + list(range(7))})
    C = pd.concat([a, b, c], ignore_index=True)
    C["n_cands"] = C.groupby("scan_date")["stock_code"].transform("size")
    d = EX.tail_frame(C, "v", "low")
    assert set(d["scan_date"]) == {"A"}
    assert sorted(d.loc[d["tail"], "v"]) == [1.0, 2.0]
    assert d.attrs["n_cov_drop"] == 1
    # 상위 꼬리 = pct > 0.8 → 값 9·10
    d_hi = EX.tail_frame(C, "v", "high")
    assert sorted(d_hi.loc[d_hi["tail"], "v"]) == [9.0, 10.0]
    # 표본 제한은 분위 «뒤»: 값 1(꼬리)·3·4(나머지)만 표본 · y = 값×10 → Δ = 10 − 35 = −25
    d = d.assign(y=d["v"] * 10, keep=d["v"].isin([1.0, 3.0, 4.0]))
    assert EX.within_day_delta(d[d["keep"]]) == pytest.approx(10 - 35)


def test_episode_first_rule():
    L = pd.DataFrame({"strategy": "s", "stock_code": ["A", "A", "A", "A", "B"], "cal_i": [1, 2, 3, 5, 2]})
    assert EX.episode_first(L).tolist() == [True, False, False, True, True]

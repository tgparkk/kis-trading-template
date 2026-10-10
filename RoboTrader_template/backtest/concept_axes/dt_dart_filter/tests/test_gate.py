from datetime import date, timedelta

import numpy as np
import pandas as pd

from backtest.concept_axes.dt_dart_filter import gate as G
from backtest.concept_axes.dt_dart_filter import sample as SM

DAYS = [date(2022, 1, 3) + timedelta(days=i) for i in range(120)]
CI = {d: i for i, d in enumerate(DAYS)}


def _led(seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for d in DAYS:
        for k in range(25):
            code = f"{rng.integers(0, 600):06d}"
            rows.append(dict(scan_date=d, stock_code=code, status="filled", p_L=float(rng.random() * 0.49),
                             ret_sl=float(rng.normal(0, 8)), ret_tp=0.0, unresolved=False, both=False,
                             halted_in_path=False, trading_value=1e10))
    led = pd.DataFrame(rows).drop_duplicates(["scan_date", "stock_code"])
    led["ret_tp"] = led["ret_sl"]
    return led


def test_analysis_frame_filters_and_marks():
    led = _led()
    led.loc[led.index[0], "status"] = "no_fill"
    led.loc[led.index[1], "p_L"] = 0.9
    mk = {(led.iloc[2]["stock_code"], led.iloc[2]["scan_date"])}
    df = SM.analysis_frame(led, mk, CI)
    assert (df["x"] == 1).sum() == 1 and len(df) <= len(led) - 2
    assert set(df["quint"].unique()) <= {1, 2, 3, 4, 5}
    assert np.allclose(df["y_sl"] + 0.25, df["ret_sl"])


def test_fake_pool_fallback_and_excludes_real_stocks():
    led = _led(1)
    real = led.sample(60, random_state=3)
    mk = set(zip(real["stock_code"], real["scan_date"]))
    df = SM.analysis_frame(led, mk, CI)
    out = G.fake_gate(df, n_fake=20, seed=7)
    assert out["n_real_marks"] == int((df["x"] == 1).sum())
    assert 0.0 <= out["rej_cr1"] <= 1.0 and out["tool"] in ("cr1", "2way", "fail")
    assert out["sd_null"] > 0


def test_fake_gate_deterministic_with_seed():
    led = _led(2)
    s = led.sample(40, random_state=4)   # 앞 40행은 0·1일 전체를 표식으로 덮어 가짜 풀이 0 → NaN 비교 실패
    mk = set(zip(s["stock_code"], s["scan_date"]))
    df = SM.analysis_frame(led, mk, CI)
    assert G.fake_gate(df, n_fake=10, seed=5) == G.fake_gate(df, n_fake=10, seed=5)

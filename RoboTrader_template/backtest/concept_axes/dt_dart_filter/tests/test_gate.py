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


# ── final review I3 · 블라인드 · 비복원 · 스킵 · 유효 복제 경계 ─────────────────
import math

import pytest

from backtest.concept_axes.dt_dart_filter import settings as S
from backtest.concept_axes.dt_dart_filter.stats import FE


def _marked(seed=1, n=60):
    led = _led(seed)
    real = led.sample(n, random_state=3)
    return SM.analysis_frame(led, set(zip(real["stock_code"], real["scan_date"])), CI)


def test_gate_blind_to_real_mark_returns():
    df = _marked()
    a = G.fake_gate(df, n_fake=15, seed=11)
    df2 = df.copy()
    m = df2["x"] == 1
    df2.loc[m, "y_sl"] = np.random.default_rng(99).normal(50, 30, int(m.sum()))
    df2.loc[m, "y_tp"] = -df2.loc[m, "y_sl"]
    assert G.fake_gate(df2, n_fake=15, seed=11) == a


def test_fake_draw_never_hits_real_stock_and_is_without_replacement():
    df = _marked(seed=4, n=120)
    pools = G.build_pools(df)
    real_stocks = set(df.loc[df["x"] == 1, "stock"])
    for i in range(25):
        chosen, skipped = G.draw_replicate(pools, np.random.default_rng([5, 7, i]))
        assert len(chosen) == len(set(chosen))
        assert not (set(pools["base"].loc[chosen, "stock"]) & real_stocks)
        assert len(chosen) + skipped == len(pools["real"])


def _tiny():
    rows = [  # day, stock, x, quint
        (0, "A", 1, 1), (0, "B", 1, 1), (0, "C", 0, 1), (0, "D", 0, 2),
        (1, "E", 1, 1), (1, "A", 0, 1),   # day 1: 유일한 대조 A 는 실제 표식 종목 → 풀 0 → 건너뜀
    ]
    df = pd.DataFrame(rows, columns=["day", "stock", "x", "quint"])
    df["y_sl"] = 0.0
    df["block"] = 0
    return df


def test_fake_draw_fallback_without_replacement_and_skip_path():
    pools = G.build_pools(_tiny())
    chosen, skipped = G.draw_replicate(pools, np.random.default_rng(0))
    stocks = sorted(pools["base"].loc[chosen, "stock"])
    assert stocks == ["C", "D"]          # B 는 같은 분위 C 가 이미 뽑혀 같은 날 아무 분위(D)로 내려감
    assert skipped == 1                  # E(day 1) 풀 없음


def _fes(n_valid, n_rej, n_total=400):
    nan = float("nan")
    out = []
    for i in range(n_total):
        if i < n_valid:
            p = 0.01 if i < n_rej else 0.5
            out.append(FE(-0.1 * (i % 7), 1.0, 1.0, 0.5, p, 0.5, p, 100, 10, 50, 40, 10))
        else:
            out.append(FE(0.3, nan, nan, nan, nan, nan, nan, 100, 10, 50, 1, 1))
    return out


def test_gate_valid_replicate_boundary():
    need = math.ceil(S.FAKE_VALID_FRAC * 400)
    assert need == 380
    ok = G.summarize(_fes(380, 38), 400)
    assert ok["n_valid"] == 380 and ok["tool"] == "cr1" and ok["reason"] == "ok"
    assert ok["rej_cr1"] == pytest.approx(38 / 380)
    bad = G.summarize(_fes(379, 38), 400)
    assert bad["n_valid"] == 379 and bad["tool"] == "fail" and bad["reason"] == "degenerate"


def test_gate_nan_p_not_counted_as_non_rejection():
    s = G.summarize(_fes(390, 26), 400)         # 26/390 = 0.0667 (구 규칙 26/400 = 0.065) — 둘 다 밴드 밖
    assert s["rej_cr1"] == pytest.approx(26 / 390)
    s2 = G.summarize(_fes(390, 50), 400)        # 50/390 = 0.128 → 밴드 안 · 구 규칙 50/400 = 0.125 와 구분
    assert s2["rej_cr1"] == pytest.approx(50 / 390) and s2["tool"] == "cr1"
    s3 = G.summarize(_fes(390, 51), 400)        # 51/390 = 0.1308 → 밴드 밖(구 규칙 51/400 = 0.1275 면 안)
    assert s3["tool"] != "cr1"
    assert math.isfinite(s["sd_null"]) and s["sd_null"] > 0


def test_gate_prints_lower_tail_and_mean_fake_n1():
    s = G.summarize(_fes(380, 38), 400)
    assert s["rej_lo_cr1"] == 0.0 and s["mean_fake_n1"] == 10.0

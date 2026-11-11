"""2단계 리뷰(§5 변이 검사)에서 «틀리게 고쳐도 통과»했던 5종 + 경계 날짜 2종 + 라벨 view 시각 — 틀린 구현이면 실패.

각 테스트 위에 잡는 변이 이름(리뷰 표)을 적었다. 확인 방법 = 변이를 메모리에서 끼운 뒤 이 파일을 돌려 실패를 본다
(수정 1 보고 · scratchpad `mutants_check.py`).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.minute_rules import engine as E
from backtest.concept_axes.minute_rules import rules as R
from backtest.concept_axes.minute_rules import run as RUN
from backtest.concept_axes.minute_rules import test_stats as S

from .synth import flat, put
from .test_run import CAL, CTX, D1, DT, RULES, daily_flat, path_of
from .test_stage2_prereg import bundle


def _b_bars(high_0903: float) -> np.ndarray:
    b = flat(10000.0)
    put(b, 3, 10100, high_0903, 10100, 10100)          # 09:03 시가 10,100(≠ a 종가 10,000) · 그 분 고가만 바꿈
    return b


# 변이 b_px_is_a — 모델 b 가 a 의 체결가(10,000)로 청산하면 09:03 고가 11,050 ≥ 11,000 → +10% 가 나온다
def test_model_b_uses_next_open_price_for_exit_lines():
    out = RUN.arm_result(_b_bars(11050), CTX, R.BASELINE, RULES, path_of(daily_flat()["000001"]), RUN.never_probe,
                         10000.0)
    assert out["px_tick"] == 10000 and out["b_px"] == 10100 and out["b_time"] == "090300"
    assert out["ret"] == pytest.approx(10.0)                        # a = 09:03 고가로 익절선 11,000 닿음
    assert out["b_ret"] == pytest.approx((10000 / 10100 - 1) * 100)  # b 선 11,110 미달 → 일봉 만기 시가 10,000


# 변이 b_scan_next — 모델 b 청산을 t+2 분부터 보면 09:03(체결 분) 고가 11,200 의 익절을 놓친다
def test_model_b_exit_scan_includes_fill_minute():
    out = RUN.arm_result(_b_bars(11200), CTX, R.BASELINE, RULES, path_of(daily_flat()["000001"]), RUN.never_probe,
                         10000.0)
    assert out["b_ret"] == pytest.approx(10.0)


# 변이 holm_nostep — 앞에서 멈춘 뒤 뒤 규칙이 자기 문턱 아래여도 기각하면 안 된다
def test_holm_stops_after_first_failure():
    rows = {r.rule: r for r in S.holm({"A": 0.03, "B": 0.04}, m=2)}
    assert not rows["A"].rejected and rows["A"].threshold == pytest.approx(0.025)
    assert rows["B"].compare <= rows["B"].threshold and not rows["B"].rejected       # 0.04 ≤ 0.05 지만 멈춤
    rows6 = {r.rule: r.rejected for r in S.holm({"R1": 0.01, "R3": 0.009, "R4": 0.048}, m=6)}
    assert rows6 == {"R3": False, "R1": False, "R4": False}                          # 0.009 > 0.05/6


# 변이 perm_across_days — 섞기는 «같은 날 안»에서만(날마다 keep 수 보존 → Δ 는 ±10 만 가능)
def test_filter_perm_shuffles_within_day_only():
    ret = [0.0, 10.0, 0.0, 0.0]
    keep = [True, False, True, True]
    days = ["a", "a", "b", "b"]
    perm = S.filter_perm(ret, keep, days, 400, S.rng_for(0, 77))
    assert set(np.round(perm, 9)) <= {-10.0, 10.0}
    assert {-10.0, 10.0} <= set(np.round(perm, 9))


# 변이 twoway_same_axis — 가중 = (종목 뽑힌 수)×(날짜 뽑힌 수) · 같은 시드로 손계산 재생
def test_twoway_weights_stock_times_day_draws():
    stocks, days = ["a", "b", "b", "c"], ["x", "y", "x", "y"]
    W = S.twoway_weights(stocks, days, 6, S.rng_for(0, 9))
    rng = S.rng_for(0, 9)
    cs = np.stack([np.bincount(rng.integers(0, 3, 3), minlength=3) for _ in range(6)])
    cd = np.stack([np.bincount(rng.integers(0, 2, 2), minlength=2) for _ in range(6)])
    s_idx, d_idx = np.array([0, 1, 1, 2]), np.array([0, 1, 0, 1])
    assert W.tolist() == (cs[:, s_idx] * cd[:, d_idx]).astype(float).tolist()


def _row(entry):
    return dict(strategy=DT, scan_date=CAL[0].isoformat(), stock_code="000001", rank="1", ref_close="10000",
                band_lo="", band_hi="10300", band_ok="True", entry_date=entry.isoformat(), exit_reason="sl", flags="")


# 변이 ledger 창 끝 배타 — 진입일 = 창 시작·창 끝 모두 포함
def test_ledger_window_bounds_inclusive():
    rows = [_row(CAL[5]), _row(CAL[9]), _row(CAL[4]), _row(CAL[10])]
    got = [x.entry_date for x in RUN.lots_from_ledger(rows, [DT], CAL[5], CAL[9])]
    assert got == [CAL[5], CAL[9]]


# 변이 U print_only 경계(>) — 2026-06-01 진입은 인쇄만 · 05-29 는 판정 창
def test_u_print_only_boundary_0601_inclusive():
    cal = [date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29), date(2026, 6, 1), date(2026, 6, 2)]
    a = RUN.Lot("A", DT, cal[1], cal[2], "000001", "1", 10000.0, None, 10300.0, True)
    b = RUN.Lot("A", DT, cal[2], cal[3], "000002", "1", 10000.0, None, 10300.0, True)
    days = cal + CAL
    daily = {**daily_flat(code="000001", days=days), **daily_flat(code="000002", days=days)}
    rows, _, _ = RUN.build_rows("U", RUN.WINDOWS["U"], [a, b], bundle([(a, flat(), {}), (b, flat(), {})]), daily,
                                cal, {"A": cal[-1]}, {})
    po = {r["stock_code"]: r["print_only"] for r in rows if r["arm"] == "R0"}
    assert po == {"000001": False, "000002": True}
    assert RUN.U_PRINT_ONLY_FROM == date(2026, 6, 1)


# 동등 변이 label_view6 를 막는 단언 — 거르기 라벨 view 는 09:05 행까지(행 0..5 · 행 5 는 종가만)
def test_filter_label_view_is_0905(monkeypatch):
    seen = []

    def spy(view, ctx):
        seen.append(view.copy())
        return E.LABEL_KEEP

    E.label_day(flat(), CTX, spy)
    v = seen[0]
    assert v.shape[0] == E.IDX_FILTER_AT + 1 == 6
    assert np.isnan(v[5, [E.F_OPEN, E.F_HIGH, E.F_LOW, E.F_VOL, E.F_AMT]]).all() and np.isfinite(v[5, E.F_CLOSE])
    assert X.Pos is not None and D1 == CTX.day

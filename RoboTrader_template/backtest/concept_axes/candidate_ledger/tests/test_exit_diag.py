"""청산 경로 진단 §2~3 단위 테스트 — 합성 데이터 · DB 없음.

사전등록 `docs/prereg_2026-09-24_exit_path_diagnosis.md` §6-2 ②: 청산 뒤 창 경계 · 장벽 기준가 · 분봉 재분류 1건 손계산.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.candidate_ledger.exit_diag import run_exit_diag as D
from backtest.concept_axes.ledger8 import exitsim8 as X


def _cal(start: str, n: int):
    cal = [t.date() for t in pd.bdate_range(start=start, periods=n)]
    return cal, {d: i for i, d in enumerate(cal)}


def _book(code: str, cal, highs, lows):
    return {code: (np.array([pd.Timestamp(d).to_datetime64() for d in cal], dtype="datetime64[ns]"),
                   np.asarray(highs, dtype=float), np.asarray(lows, dtype=float))}


def _lot(code: str, reason: str, entry: date, exit_: date, E: float = 10_000.0, exit_price: float = 9_200.0):
    return dict(strategy="book_pullback_ma20", scan_date="2024-01-01", stock_code=code, entry_date=entry.isoformat(),
                entry_price=str(E), exit_date=exit_.isoformat(), exit_reason=reason, exit_price=str(exit_price),
                ret_pct="-8", hold_days="1", flags="")


# ── 청산 뒤 창 경계: exit_date 봉 제외 · +W 거래일 포함 · +W+1 제외 · 창 끝 초과 제외 ────────────────
def test_window_end_is_w_trading_days_after_exit_and_none_past_calendar():
    cal, idx = _cal("2024-03-04", 20)
    assert D.window_end(cal, idx, cal[2]) == cal[12]                  # (exit, exit + 10 거래일]
    assert D.window_end(cal, idx, cal[9]) == cal[19]                  # 달력 끝 딱 맞음
    assert D.window_end(cal, idx, cal[10]) is None                    # 달력 밖 = 창 끝 > 마지막 날 ⇒ 제외


def test_window_bounds_exclude_exit_bar_include_wth_bar_exclude_next():
    cal, idx = _cal("2024-03-04", 20)
    dates = np.array([pd.Timestamp(d).to_datetime64() for d in cal], dtype="datetime64[ns]")
    ex = cal[2]
    wend = D.window_end(cal, idx, ex)
    lo, hi = D.window_bounds(dates, ex, wend)
    assert (lo, hi) == (3, 13) and hi - lo == D.W
    # 익절 장벽 11,000 을 넘는 고가가 exit_date 봉(2)과 W+1 번째 봉(13)에만 있으면 (b) = 미도달
    E, tp, sl = 10_000.0, 0.10, 0.08
    highs = np.full(20, 10_000.0)
    lows = np.full(20, 9_500.0)
    highs[2] = highs[13] = 12_000.0
    hit, _ = D.pair_metric(X.EXIT_SL, E, tp, sl, highs[lo:hi], lows[lo:hi])
    assert hit is False
    highs[12] = 11_000.0                                              # +10 번째 거래일(창 끝) 봉 = 포함
    hit, _ = D.pair_metric(X.EXIT_SL, E, tp, sl, highs[lo:hi], lows[lo:hi])
    assert hit is True


def test_diagnose_lots_waterfall_window_corp_impossible():
    cal, idx = _cal("2026-09-01", 25)                                 # 2026-09-01 ~ 10-03 (창 끝 판정용)
    assert cal[16] == date(2026, 9, 23)
    book = {}
    for c in ("A00001", "A00002", "A00003", "A00004", "A00005"):
        book.update(_book(c, cal, np.full(25, 10_000.0), np.full(25, 9_500.0)))
    lots = pd.DataFrame([
        _lot("A00001", X.EXIT_SL, cal[0], cal[6]),                    # 창 끝 = cal[16] = 09-23 ⇒ 포함
        _lot("A00002", X.EXIT_SL, cal[0], cal[7]),                    # 창 끝 = cal[17] = 09-24 > 09-23 ⇒ ① 제외
        _lot("A00003", X.EXIT_SL, cal[0], cal[6]),                    # corp_event 가 창 끝 날(09-23)에 ⇒ ② 제외
        _lot("A00004", X.EXIT_SL, cal[0], cal[6]),                    # impossible_bar 가 entry_date 에 ⇒ ③ 제외
        _lot("A00005", "trail_ma", cal[0], cal[6]),                   # 짝 대상 아님
    ])
    ts = lambda d: np.array([pd.Timestamp(d).to_datetime64()], dtype="datetime64[ns]")  # noqa: E731
    rows = D.diagnose_lots(lots, 0.10, 0.08, cal, idx, book, {"A00003": ts(cal[16])}, {"A00004": ts(cal[0])})
    by = {r["stock_code"]: r for r in rows}
    assert set(by) == {"A00001", "A00002", "A00003", "A00004"}
    assert by["A00001"]["excl"] == "" and by["A00001"]["n_bars_win"] == D.W
    assert by["A00002"]["excl"] == D.EXCL_WIN
    assert by["A00003"]["excl"] == D.EXCL_CORP
    assert by["A00004"]["excl"] == D.EXCL_IMP


# ── 장벽 기준가: E 도 체결가도 아니라 E×(1+tp) · E×(1−sl) ──────────────────────────────
def test_barrier_reference_not_fill_price():
    E, tp, sl = 10_000.0, 0.10, 0.08
    assert D.barriers(E, tp, sl) == pytest.approx((11_000.0, 9_200.0))
    # tp 로트가 갭 익절 11,500(체결가)로 나갔다 · 창 max high 11,300 ⇒ (c) = ln(11300/11000) > 0 (체결가 기준이면 음수)
    hit, c = D.pair_metric(X.EXIT_TP, E, tp, sl, np.array([11_300.0, 11_200.0]), np.array([10_900.0, 10_800.0]))
    assert hit is False
    assert c == pytest.approx(math.log(11_300 / 11_000)) and c > 0 and math.log(11_300 / 11_500) < 0
    # (b′) 손절 장벽 9,200 에 «정확히» 닿으면 도달
    hit, _ = D.pair_metric(X.EXIT_TP, E, tp, sl, np.array([10_000.0]), np.array([9_200.0]))
    assert hit is True
    # sl 로트가 갭 손절 8,800 으로 나갔다 · 창 min low 9,000 ⇒ (c′) = −ln(9000/9200) > 0 (체결가 기준이면 음수)
    hit, cp = D.pair_metric(X.EXIT_SL, E, tp, sl, np.array([11_000.0]), np.array([9_000.0]))
    assert cp == pytest.approx(-math.log(9_000 / 9_200)) and cp > 0 and -math.log(9_000 / 8_800) < 0
    assert hit is True                                                # (b) 익절 장벽 11,000 에 정확히 닿음 = 도달


@pytest.mark.parametrize("E", [10_000.0, 1_075.0, 1_100.0])
def test_exact_barrier_touch_survives_float(E):
    """H3 — minervini tp 0.12: E×1.12 가 11200.000000000002 처럼 올라가 가격 곱셈 비교는 정확한 도달을 놓친다
    (손절 쪽은 그런 일이 없어 비대칭 오차가 된다) ⇒ 수익률 비교식이어야 한다."""
    tp, sl = 0.12, 0.08
    tp_px = float(round(E * 1.12))
    assert not (tp_px >= E * (1 + tp))                                # 가격 곱셈 비교는 놓친다
    hit, _ = D.pair_metric(X.EXIT_SL, E, tp, sl, np.array([tp_px]), np.array([E]))
    assert hit is True


def test_empty_window_is_no_touch_and_nan():
    hit, v = D.pair_metric(X.EXIT_SL, 10_000.0, 0.10, 0.08, np.empty(0), np.empty(0))
    assert hit is False and math.isnan(v)


# ── (a) 분봉 재분류 1건 손계산 ────────────────────────────────────────────────
def test_minute_reclass_hand_calc():
    E, tp, sl = 10_000.0, 0.10, 0.08                                  # 익절 11,000 · 손절 9,200
    bars = [("090000", 10_100.0, 9_950.0),                            # 어느 쪽도 안 닿음
            ("090100", 10_200.0, 9_500.0),                            # 안 닿음(9,500 > 9,200)
            ("090200", 11_050.0, 9_800.0),                            # 익절만 ⇒ 익절 먼저
            ("091000", 10_000.0, 9_100.0)]                            # 뒤의 손절은 무관
    assert D.reclassify_minutes(E, tp, sl, bars) == (D.MIN_TP_FIRST, "090200")
    assert D.reclassify_minutes(E, tp, sl, bars[:2] + bars[3:]) == (D.MIN_SL_FIRST, "091000")
    assert D.reclassify_minutes(E, tp, sl, [("090000", 11_000.0, 9_200.0)]) == (D.MIN_BOTH, "090000")
    assert D.reclassify_minutes(E, tp, sl, bars[:2]) == (D.MIN_NONE, None)


def test_same_bar_rows_session_filter_and_ret_after():
    ex = date(2025, 3, 5)
    row = _lot("A00001", X.EXIT_SL, date(2025, 3, 4), ex)
    row["flags"] = "survivor_universe;" + X.FLAG_SL_TP_BOTH
    L = pd.DataFrame([row])
    minutes = {("A00001", "20250305"): [("085900", 12_000.0, 9_000.0),     # 정규장 밖 — 무시
                                        ("090000", 10_100.0, 9_950.0),
                                        ("090200", 11_050.0, 9_800.0),     # 익절 먼저
                                        ("091000", 10_000.0, 9_100.0)]}
    out = D.same_bar_rows(L, 0.10, 0.08, minutes)
    assert len(out) == 1
    r = out[0]
    assert r["category"] == D.MIN_TP_FIRST and r["first_touch_time"] == "090200"
    assert r["n_minute_rows"] == 4 and r["n_session_bars"] == 3
    assert r["ret_before"] == pytest.approx(-8.0) and r["ret_after"] == pytest.approx(10.0)
    # 분봉 범위(2025-02-24) 이전 봉은 조회하지 않는다
    row2 = _lot("A00002", X.EXIT_SL, date(2024, 3, 4), date(2024, 3, 5))
    row2["flags"] = X.FLAG_SL_TP_BOTH
    out2 = D.same_bar_rows(pd.DataFrame([row2]), 0.10, 0.08, {("A00002", "20240305"): [("090000", 1.0, 1.0)]})
    assert out2[0]["category"] == "분봉 없음" and out2[0]["ret_after"] == pytest.approx(-8.0)


# ── §3 부트스트랩 · 판정 ──────────────────────────────────────────────────────
def _diag_frame():
    rows = []
    for g in range(30):
        code = f"{g:06d}"
        for k in range(4):
            rows.append(dict(stock_code=code, exit_reason=X.EXIT_SL, hit=(k == 0), logval=0.02))
            rows.append(dict(stock_code=code, exit_reason=X.EXIT_TP, hit=(k == 0), logval=0.02))
    return pd.DataFrame(rows)


def test_aggregate_point_and_bootstrap_same_resample():
    codes, agg = D.aggregate(_diag_frame())
    assert len(codes) == 30 and list(codes) == sorted(codes)
    st = D.pair_stats(agg)
    assert st["b"] == pytest.approx(0.25) and st["bp"] == pytest.approx(0.25)
    assert st["c"] == pytest.approx(0.02) and st["cp"] == pytest.approx(0.02)
    d_b, d_c = D.bootstrap_diffs(agg, np.random.default_rng([D.SEED_ROOT, D.SEED_STREAM, 0]), 200)
    # 모든 종목이 짝 두 값에서 같은 구성 ⇒ 한 재표집 안에서 같이 계산하면 차는 매번 정확히 0
    assert np.allclose(d_b, 0.0) and np.allclose(d_c, 0.0)
    d_b2, _ = D.bootstrap_diffs(agg, np.random.default_rng([D.SEED_ROOT, D.SEED_STREAM, 0]), 200)
    assert np.array_equal(d_b, d_b2)                                  # 시드 재현


def test_pair_verdict_and_label():
    assert D.pair_verdict(2.5, 0.4, 4.1, 500, 500) == "비대칭"
    assert D.pair_verdict(-2.0, -3.9, -0.1, 500, 500) == "비대칭"      # |차| = 2.0 경계 포함
    assert D.pair_verdict(2.5, -0.1, 4.1, 500, 500) == "기준 미달"      # CI 가 0 포함
    assert D.pair_verdict(1.9, 0.5, 3.0, 500, 500) == "기준 미달"       # |차| < 2.0
    assert D.pair_verdict(5.0, 3.0, 7.0, 199, 500).startswith("판정 불가")
    assert D.strategy_label("기준 미달", "비대칭") == D.LAB_ASYM
    assert D.strategy_label("기준 미달", "기준 미달") == D.LAB_NONE
    assert D.strategy_label("판정 불가(분모<200)", "기준 미달") == D.LAB_NA


def test_breakeven_matches_prereg():
    got = [D.breakeven(tp, sl) for tp, sl in ((0.10, 0.08), (0.12, 0.08), (0.10, 0.10))]
    assert [round(a, 1) for a, _ in got] == [44.4, 40.0, 50.0]
    assert [b for _, b in got] == pytest.approx([45.8333333, 41.25, 51.25])   # 문서 45.8·41.3·51.3 = 반올림(half-up)

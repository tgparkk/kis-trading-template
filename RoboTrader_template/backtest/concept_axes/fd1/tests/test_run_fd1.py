"""FD1 §1-1 PIT 경계 · §1-2 합집합 D · §1-3 U1 3계단 · §3-0-b-ii 꼬리 창 — 합성 데이터 · DB 없음."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest.concept_axes.fd1 import run_fd1 as F


def _d(s: str) -> np.datetime64:
    return np.datetime64(s, "D")


# ── §1-1 PIT 경계 ──────────────────────────────────────────────────────────
def test_pit_boundary_rcept_on_decision_day_is_invisible():
    rc = {2023: _d("2024-03-20"), 2022: _d("2023-03-20")}
    assert F.pit_year(rc, _d("2024-03-20")) == 2022          # rcept == D → 안 보인다
    assert F.pit_year(rc, _d("2024-03-21")) == 2023          # rcept == D−1 → 보인다
    assert F.pit_year({2023: None}, _d("2025-01-01")) is None


def test_classify_uses_latest_visible_year_only_and_prev_year_separately():
    fin = {"000001": {2022: (_d("2023-03-10"), -5.0, 100.0, 10.0, 50.0),
                      2023: (_d("2024-03-10"), 7.0, 100.0, 10.0, 50.0)},
           "000002": {2023: (None, -5.0, 100.0, 10.0, 50.0)}}          # 013 = rcept 없음 → 모름
    codes = np.array(["000001", "000001", "000002", "999999"])
    dates = np.array(["2024-03-10", "2024-03-11", "2024-06-01", "2024-06-01"], dtype="datetime64[D]")
    C = F.classify(fin, codes, dates)
    assert C["fin_y"].tolist()[:2] == [2022, 2023]
    assert C["D"].tolist()[0] == 1 and C["D"].tolist()[1] == 0        # 2023 흑자 → 다른 해를 찾지 않는다
    assert C["unk"].tolist()[2:] == ["no_visible_year", "no_rows"]


# ── §1-2 합집합 D (3치 논리) ────────────────────────────────────────────────
def test_flag_d_union_and_unknown():
    assert F.flag_d(-1, 100, 10, 50, None, False)[0] == 1            # (a)
    assert F.flag_d(5, 0, 10, 50, None, False)[0] == 1               # (c) 완전잠식
    assert F.flag_d(5, 4, 10, 50, None, False)[0] == 1               # (c) 부분잠식 50%+
    assert F.flag_d(5, 10, 10, 41, None, False)[0] == 1              # (d) 부채비율 410%
    assert F.flag_d(5, 10, 10, 40, None, False)[0] == 0              # 400% 는 초과 아님
    D, comps = F.flag_d(-1, 100, 10, 50, -2, True)
    assert D == 1 and comps["b"] is True
    assert F.flag_d(-1, 100, 10, 50, -2, False)[1]["b"] is None       # 전년 안 보임 → (b) 모름
    assert F.flag_d(None, 100, 10, 50, None, False)[0] is None        # (a) 모름 · 나머지 거짓 → 모름
    assert F.flag_d(-1, None, None, None, None, False)[0] == 1        # 참 성분 하나면 결측이 있어도 D=1
    assert F.flag_d(5, 100, None, 50, None, False)[0] is None         # ic NULL → (c) 모름(SQL 3치)


# ── §1-3 U1 3계단 ──────────────────────────────────────────────────────────
def test_u1_tiers_and_bd_order():
    assert [F.u1_tier(x) for x in (0, None, 1)] == [0, 1, 2]
    cands = [("A", 1, 1), ("B", 2, None), ("C", 3, 0), ("D", 4, 0), ("E", 5, 1)]
    assert F.b_topk(cands, 3) == ["A", "B", "C"]
    assert F.bd_topk(cands, 5) == ["C", "D", "B", "A", "E"]          # 비플래그 → 모름 → 플래그 · 안에선 rank
    assert set(F.bd_topk(cands, 5)) == set(F.b_topk(cands, 5))        # G1 — 후보 집합 불변


# ── §3-0-b-ii 꼬리 창 (합성 · phase 2 경로) ──────────────────────────────────
def test_tail_window_uses_t0_close_and_censors_end():
    cal = list(pd.bdate_range("2024-01-01", periods=60))
    n = len(cal)
    op = np.full(n, 100.0)
    op[30] = 91.0                                                       # t0=25 종가 100 × 0.92 = 92 아래
    px = pd.DataFrame({"stock_code": "000001", "d": cal, "open": op, "close": np.full(n, 100.0),
                       "vol_adj": np.full(n, 1e6), "adj1": np.ones(n)})
    ev = F.tail_events(px, cal).set_index("d")
    assert ev.loc[cal[25], "i_s08_w10_inc"] == 1.0                     # t0+5 에 시가 91
    assert ev.loc[cal[29], "i_s08_w10_inc"] == 1.0
    assert ev.loc[cal[30], "i_s08_w10_inc"] == 0.0                     # 당일 자신은 창 밖
    assert ev.loc[cal[19], "i_s08_w10_inc"] == 0.0                     # t0+11 은 창 밖
    assert ev.loc[cal[27], "i_s08_w2_inc"] == 0.0 and ev.loc[cal[28], "i_s08_w2_inc"] == 1.0
    assert ev.loc[cal[25], "i_s10_w10_inc"] == 0.0                     # s=0.10 → 90 미만 아님
    assert np.isnan(ev.loc[cal[n - 1], "i_s08_w10_inc"])               # 우측 절단

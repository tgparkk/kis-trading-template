"""scripts/eval_sector_news_shadow 순수 헬퍼. 연구 트리 격리: sys.path + importorskip."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
pd = pytest.importorskip("pandas")
ev = pytest.importorskip("scripts.eval_sector_news_shadow")


def test_sector_validity_quintiles_and_small_days():
    rows = []
    for i in range(10):                         # 점수와 수익률이 같은 방향 → 양의 상관
        rows.append({"trade_date": "2026-10-01", "score_signed": (i - 5) / 5, "ret_median": (i - 5) / 100})
    rows.append({"trade_date": "2026-10-01", "score_signed": 0.0, "ret_median": 9.9})   # 0 은 제외
    rows += [{"trade_date": "2026-10-02", "score_signed": 0.5, "ret_median": 0.01}] * 3   # 5행 미만
    out = ev.sector_validity(pd.DataFrame(rows)).set_index("trade_date")
    assert out.loc["2026-10-01", "n"] == 10 and out.loc["2026-10-01", "spearman"] > 0.9
    assert out.loc["2026-10-01", "q5_minus_q1"] > 0
    assert out.loc["2026-10-02", "n"] == 3 and pd.isna(out.loc["2026-10-02", "spearman"])   # float 열이라 None→NaN


def test_classify_transitions():
    log = pd.DataFrame([
        {"stock_code": "A", "orig_rank": 22, "new_rank": 19},   # entered
        {"stock_code": "B", "orig_rank": 20, "new_rank": 21},   # displaced
        {"stock_code": "C", "orig_rank": 5, "new_rank": 3},     # top3_in
        {"stock_code": "D", "orig_rank": 2, "new_rank": 4},     # top3_out
        {"stock_code": "E", "orig_rank": 7, "new_rank": 6},     # 해당 없음
    ])
    out = ev.classify_transitions(log, slots=20).set_index("stock_code")["group"].to_dict()
    assert out == {"A": "entered", "B": "displaced", "C": "top3_in", "D": "top3_out"}


def test_forward_return_none_when_insufficient():
    prices = pd.DataFrame([{"stock_code": "A", "date": f"2026-10-0{d}", "close": 100 + d} for d in range(1, 8)])
    assert abs(ev.forward_return(prices, "A", "2026-10-01", n=5) - (106 / 101 - 1)) < 1e-12
    assert ev.forward_return(prices, "A", "2026-10-03", n=5) is None       # 5봉 부족
    assert ev.forward_return(prices, "A", "2026-09-30", n=5) is None       # d0 행 없음
    assert ev.forward_return(prices, "Z", "2026-10-01", n=5) is None


def test_reason_distribution():
    log = pd.DataFrame([
        {"strategy": "s1", "trade_date": "2026-10-01", "reason": "ok", "orig_rank": 1, "new_rank": 2},
        {"strategy": "s1", "trade_date": "2026-10-01", "reason": "ok", "orig_rank": 2, "new_rank": 1},
        {"strategy": "s1", "trade_date": "2026-10-02", "reason": "stale", "orig_rank": 1, "new_rank": 1},
    ])
    out = ev.reason_distribution(log).set_index(["strategy", "reason"])
    assert out.loc[("s1", "ok"), "days"] == 1 and out.loc[("s1", "ok"), "avg_moved"] == 2
    assert out.loc[("s1", "stale"), "days"] == 1 and out.loc[("s1", "stale"), "avg_moved"] == 0

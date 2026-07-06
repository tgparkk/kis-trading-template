import scripts.kis_db.smoke_state_restore as smk
from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE


def test_build_summary_positions_and_candidates_sorted():
    ops = [
        {"stock_code": "000660", "quantity": 5, "buy_price": 100.0, "strategy": "elder"},
        {"stock_code": "005930", "quantity": 3, "buy_price": 200.0, "strategy": "ma5"},
    ]
    s = smk.build_restore_summary(ops, {}, ["005930", "000660", "000660"])
    assert s["open_position_codes"] == ["000660", "005930"]
    assert s["n_open"] == 2
    assert s["candidate_codes"] == ["000660", "005930"]  # dedup + sorted


def test_build_summary_cash_uses_live_formula():
    sums = {"elder": {"buy_gross": 1000.0, "sell_gross": 500.0}}
    s = smk.build_restore_summary([], sums, [], capital=10000.0)
    expected = 10000.0 - 1000.0 * (1 + COMMISSION_RATE) + 500.0 * (1 - COMMISSION_RATE - SECURITIES_TAX_RATE)
    assert s["per_strategy_cash"]["elder"] == round(expected, 2)


def test_compare_summaries_pass_when_identical():
    base = {"open_position_codes": ["A"], "candidate_codes": ["X"],
            "per_strategy_cash": {"elder": 100.0}}
    cand = {"open_position_codes": ["A"], "candidate_codes": ["X"],
            "per_strategy_cash": {"elder": 100.4}}  # 0.4 < 1.0 → 일치
    c = smk.compare_summaries(base, cand)
    assert c["open_positions_match"] is True
    assert c["candidates_match"] is True
    assert c["cash_match"] is True
    assert c["verdict"] == "PASS"


def test_compare_summaries_fail_on_position_mismatch():
    base = {"open_position_codes": ["A", "B"], "candidate_codes": ["X"],
            "per_strategy_cash": {"elder": 100.0}}
    cand = {"open_position_codes": ["A"], "candidate_codes": ["X"],
            "per_strategy_cash": {"elder": 100.0}}
    c = smk.compare_summaries(base, cand)
    assert c["open_positions_match"] is False
    assert c["verdict"] == "FAIL"


def test_compare_summaries_fail_on_cash_drift():
    base = {"open_position_codes": [], "candidate_codes": [],
            "per_strategy_cash": {"elder": 100.0}}
    cand = {"open_position_codes": [], "candidate_codes": [],
            "per_strategy_cash": {"elder": 250.0}}  # 150 diff
    c = smk.compare_summaries(base, cand)
    assert c["cash_max_abs_diff"] == 150.0
    assert c["cash_match"] is False
    assert c["verdict"] == "FAIL"

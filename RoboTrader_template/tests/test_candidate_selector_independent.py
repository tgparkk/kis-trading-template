from unittest.mock import MagicMock
from core.candidate_selector import CandidateSelector


def _cand(code):
    c = MagicMock()
    c.code = code
    c.name = code
    return c


def test_same_stock_kept_for_multiple_strategies():
    selector = CandidateSelector.__new__(CandidateSelector)
    selector.logger = MagicMock()

    def fake_fetch(strategy_name, max_candidates):
        return [_cand("010170"), _cand(f"{strategy_name}_only")]
    selector._fetch_candidates_for_strategy = fake_fetch

    result = selector.select_candidates_per_strategy(
        {"minervini": MagicMock(), "rs_leader": MagicMock()}, max_per_strategy=10
    )
    minv_codes = {c.code for c in result["minervini"]}
    rs_codes = {c.code for c in result["rs_leader"]}
    assert "010170" in minv_codes
    assert "010170" in rs_codes

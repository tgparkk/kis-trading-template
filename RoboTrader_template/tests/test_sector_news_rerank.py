"""core.sector_news_rerank.rerank — 순수 함수 계약 (스펙 B §5.2)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.sector_news_rerank import rerank, RerankRow, classify_sector_news_exception  # noqa: E402

C8 = [f"S{i}" for i in range(1, 9)]   # S1..S8, 원래 순위 = 번호


def _ranks(rows):
    return {r.stock_code: r.new_rank for r in rows}


def test_no_scores_keeps_order():
    codes, rows = rerank(C8, {}, {})
    assert codes == C8
    assert [r.new_rank for r in rows] == list(range(1, 9)) and [r.orig_rank for r in rows] == list(range(1, 9))
    assert all(r.sector_key is None and r.sector_score is None for r in rows)


def test_plus_one_moves_exactly_max_shift_up():
    codes, rows = rerank(C8, {"S5": "261"}, {"261": 1.0}, max_shift=3)
    assert codes == ["S1", "S5", "S2", "S3", "S4", "S6", "S7", "S8"]
    assert _ranks(rows)["S5"] == 2 and rows[4] == RerankRow("S5", "261", 1.0, 5, 2)


def test_minus_one_moves_exactly_max_shift_down():
    codes, rows = rerank(C8, {"S2": "641"}, {"641": -1.0}, max_shift=3)
    assert codes == ["S1", "S3", "S4", "S5", "S2", "S6", "S7", "S8"]
    assert _ranks(rows)["S2"] == 5


def test_cannot_move_above_first_or_below_last():
    codes, _ = rerank(C8, {"S2": "a"}, {"a": 1.0})
    assert codes[0] == "S2"
    codes, _ = rerank(C8, {"S7": "a"}, {"a": -1.0})
    assert codes[-1] == "S7"


def test_fractional_score_rounds_half_away_from_zero():
    codes, _ = rerank(C8, {"S5": "a"}, {"a": 0.5}, max_shift=3)     # 1.5 → 2
    assert codes.index("S5") + 1 == 3
    codes, _ = rerank(C8, {"S3": "a"}, {"a": -0.5}, max_shift=3)    # -1.5 → -2
    assert codes.index("S3") + 1 == 5
    codes, _ = rerank(C8, {"S5": "a"}, {"a": 0.4}, max_shift=3)     # 1.2 → 1
    assert codes.index("S5") + 1 == 4


def test_below_min_abs_does_not_move_but_is_recorded():
    codes, rows = rerank(C8, {"S5": "a"}, {"a": 0.19}, min_abs=0.2)
    assert codes == C8 and _ranks(rows)["S5"] == 5
    assert rows[4].sector_key == "a" and rows[4].sector_score == 0.19


def test_unknown_sector_and_sector_without_score_unchanged():
    codes, rows = rerank(C8, {"S5": "zzz"}, {"261": 1.0})
    assert codes == C8 and rows[4].sector_key == "zzz" and rows[4].sector_score is None


def test_score_is_clipped_to_unit_range():
    codes, rows = rerank(C8, {"S8": "a"}, {"a": 7.5}, max_shift=3)
    assert codes.index("S8") + 1 == 5 and rows[7].sector_score == 7.5


def test_tie_broken_by_original_rank():
    # S4 shift 1 → key 2.5 · S6 shift 3 → key 2.5 → 동률 → S4 먼저
    codes, _ = rerank(C8, {"S4": "a", "S6": "b"}, {"a": 0.34, "b": 1.0}, max_shift=3)
    assert codes[:4] == ["S1", "S2", "S4", "S6"]


def test_two_way_movement_together():
    codes, _ = rerank(C8, {"S5": "up", "S2": "dn"}, {"up": 1.0, "dn": -1.0})
    assert codes == ["S1", "S5", "S3", "S4", "S2", "S6", "S7", "S8"]


def test_permutation_preserved_and_new_ranks_are_1_to_n():
    codes, rows = rerank(C8, {"S1": "a", "S8": "b", "S4": "c"}, {"a": -1.0, "b": 1.0, "c": 0.6})
    assert sorted(codes) == sorted(C8) and sorted(r.new_rank for r in rows) == list(range(1, 9))
    assert [r.orig_rank for r in rows] == list(range(1, 9))


def test_max_shift_zero_is_identity():
    codes, _ = rerank(C8, {"S5": "a"}, {"a": 1.0}, max_shift=0)
    assert codes == C8


def test_duplicate_codes_rejected():
    with pytest.raises(ValueError, match="중복"):
        rerank(["S1", "S1"], {}, {})


def test_negative_max_shift_rejected():
    with pytest.raises(ValueError):
        rerank(C8, {}, {}, max_shift=-1)


def test_empty_input():
    assert rerank([], {}, {}) == ([], [])


def test_classify_exception():
    class UndefinedFunction(Exception):
        pass

    class UndefinedTable(Exception):
        pass
    assert classify_sector_news_exception(UndefinedFunction()) == "fn_missing"
    assert classify_sector_news_exception(UndefinedTable()) == "table_missing"
    assert classify_sector_news_exception(RuntimeError("x")) == "error:RuntimeError"

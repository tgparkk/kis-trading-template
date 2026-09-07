import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests._mock_modules  # noqa: F401,E402
from bot.candidate_loader import format_candidate_lines  # noqa: E402
from core.candidate_selector import CandidateStock  # noqa: E402


def _c(code, note=""):
    return CandidateStock(code=code, name=f"N{code}", market="KRX", score=50.0, reason="r", sector_note=note)


def test_lines_include_sector_note_only_when_present():
    pool = {"s1": [_c("A1"), _c("A5", " (↑3 261 +1.0)")], "s2": [], "s3": [_c("B1")]}
    assert format_candidate_lines(pool) == [
        "  [s1] A1(NA1), A5(NA5) (↑3 261 +1.0)",
        "  [s3] B1(NB1)",
    ]


def test_objects_without_sector_note_attribute_are_fine():
    class Legacy:
        code, name = "L1", "레거시"
    assert format_candidate_lines({"s": [Legacy()]}) == ["  [s] L1(레거시)"]

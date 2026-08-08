import os
import sys

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import f1_worklist as f1  # noqa: E402


def test_years_start_at_2019():
    """타겟이 2021-01 부터이고 그때 알 수 있던 최신 연간재무는 2019 사업연도다."""
    assert f1.YEARS[0] == "2019"
    assert "2025" in f1.YEARS


def test_worklist_is_cross_product_of_stocks_and_years():
    rows = [("005930", "00126380"), ("000660", "00164779")]
    wl = f1.build_worklist(rows, ["2019", "2020"])
    assert len(wl) == 4
    assert {w["stock_code"] for w in wl} == {"005930", "000660"}
    assert {w["bsns_year"] for w in wl} == {"2019", "2020"}


def test_worklist_is_deterministically_ordered():
    """재개가 성립하려면 순서가 매 실행 같아야 한다."""
    rows = [("000660", "00164779"), ("005930", "00126380")]
    a = f1.build_worklist(rows, ["2020", "2019"])
    b = f1.build_worklist(list(reversed(rows)), ["2019", "2020"])
    assert a == b
    assert [w["stock_code"] for w in a][:2] == ["000660", "000660"]


def test_rows_without_corp_code_are_dropped():
    """corp_code 가 없으면 호출 자체가 불가능하다 — 조용히 빈 문자열로 부르지 않는다."""
    rows = [("005930", "00126380"), ("900300", ""), ("900301", None)]
    wl = f1.build_worklist(rows, ["2019"])
    assert [w["stock_code"] for w in wl] == ["005930"]


def test_same_stock_code_with_and_without_corp_does_not_raise():
    """🔴 정렬이 필터보다 먼저면 여기서 TypeError 가 난다."""
    rows = [("005930", None), ("005930", "00126380")]
    wl = f1.build_worklist(rows, ["2019"])
    assert [w["corp_code"] for w in wl] == ["00126380"]

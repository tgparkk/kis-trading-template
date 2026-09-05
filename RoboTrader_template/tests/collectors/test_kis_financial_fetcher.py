import inspect
from collectors import kis_financial_fetcher as k
from collectors import financial_metrics as fm


def test_quarterly_div_cls_is_1(monkeypatch):
    """div_cls 기본값은 '0'(연간)이다. 분기를 받으려면 '1' 을 «명시»해야 한다."""
    seen = {}

    def fake(code, div_cls="0", tr_cont=""):
        seen["div_cls"] = div_cls
        return []

    monkeypatch.setattr(k, "get_financial_ratio", fake)
    k.fetch_quarterly_ratio("005930")
    assert seen["div_cls"] == "1"


def test_pit_view_does_not_reference_kis_table():
    """🔴 KIS 는 접수일이 없어 PIT 을 못 준다.
    PIT 조회 경로가 이 테이블을 «참조조차» 하면 안 된다 — 주석이 아니라 구조로 막는다."""
    assert "kis_financial_ratio" not in fm.DDL_VIEW
    assert "kis_financial_ratio" not in inspect.getsource(fm)

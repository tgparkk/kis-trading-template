import inspect
import types
from datetime import datetime
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


def test_row_mapping_with_mixed_numeric_strings(monkeypatch):
    """재무비율 행 매핑: 숫자 문자열, 공백, "-" 등 혼합 데이터에서 정확히 파싱되는지 확인."""
    fake_entry = types.SimpleNamespace(
        stock_code="005930",
        statement_ym="202409",
        roe_value=15.5,  # 데이터클래스 필드 (사용 안 함, raw에서만 읽음)
        per=10.0,
        eps=2000.0,
        sps=30000.0,
        bps=50000.0,
        reserve_ratio=20.0,
        liability_ratio=30.0,
        sales_growth=5.5,
        operating_income_growth=3.2,
        net_income_growth=2.8,
        created_at=datetime.now(),
        raw={
            "stac_yymm": "202409",
            "roe_val": "15.5",        # 숫자 문자열
            "per_pbr_rate": "10.2",
            "eps": "2,000",           # 쉼표 있는 숫자
            "sps": "",                # 공백 → None
            "bps": "-",               # "-" → None
            "rsrv_rate": "20.5",
            "lblt_rate": None,        # None → None
            "grs": "5.5%",            # 파싱 실패 → None
            "bsop_prfi_inrt": "3.2",
            "ntin_inrt": "2.8"
        }
    )

    def fake_get(code, div_cls="0", tr_cont=""):
        assert div_cls == "1"
        return [fake_entry]

    monkeypatch.setattr(k, "get_financial_ratio", fake_get)
    rows = k.fetch_quarterly_ratio("005930")

    assert len(rows) == 1
    row = rows[0]

    # 14개 컬럼 확인
    assert set(row.keys()) == {
        "stock_code", "stac_yymm", "div_cls",
        "roe_value", "per", "eps", "sps", "bps",
        "reserve_ratio", "liability_ratio",
        "sales_growth", "operating_income_growth", "net_income_growth",
        "raw_json"
    }

    # 값 검증
    assert row["stock_code"] == "005930"
    assert row["stac_yymm"] == "202409"
    assert row["div_cls"] == "1"
    assert row["roe_value"] == 15.5
    assert row["per"] == 10.2
    assert row["eps"] == 2000.0  # 쉼표 제거
    assert row["sps"] is None    # 공백
    assert row["bps"] is None    # "-"
    assert row["reserve_ratio"] == 20.5
    assert row["liability_ratio"] is None  # None
    assert row["sales_growth"] is None     # 파싱 실패
    assert row["operating_income_growth"] == 3.2
    assert row["net_income_growth"] == 2.8


def test_missing_statement_ym_is_skipped_with_warning(monkeypatch):
    """statement_ym 없는 항목은 건너뛰고 경고를 기록한다."""
    fake_entry = types.SimpleNamespace(
        stock_code="005930",
        statement_ym="",  # 비어있음
        roe_value=15.5,
        per=10.0,
        eps=2000.0,
        sps=30000.0,
        bps=50000.0,
        reserve_ratio=20.0,
        liability_ratio=30.0,
        sales_growth=5.5,
        operating_income_growth=3.2,
        net_income_growth=2.8,
        created_at=datetime.now(),
        raw={
            "stac_yymm": "",  # 비어있음
            "roe_val": "15.5",
            "per_pbr_rate": "10.2",
            "eps": "2000",
            "sps": "30000",
            "bps": "50000",
            "rsrv_rate": "20.5",
            "lblt_rate": "30.0",
            "grs": "5.5",
            "bsop_prfi_inrt": "3.2",
            "ntin_inrt": "2.8"
        }
    )

    def fake_get(code, div_cls="0", tr_cont=""):
        assert div_cls == "1"
        return [fake_entry]

    monkeypatch.setattr(k, "get_financial_ratio", fake_get)

    # Monkeypatch logger to track warning calls
    warnings = []
    original_warning = k.logger.warning

    def mock_warning(msg):
        warnings.append(msg)
        original_warning(msg)

    monkeypatch.setattr(k.logger, "warning", mock_warning)

    rows = k.fetch_quarterly_ratio("005930")

    # 항목이 건너뛰어짐
    assert len(rows) == 0

    # 경고가 기록됨
    assert len(warnings) == 1
    assert "statement_ym 없음" in warnings[0]
    assert "005930" in warnings[0]

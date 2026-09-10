# tests/api/test_index_daily_chart.py
"""KIS 업종 일봉 래퍼 — 파라미터 계약 (설계 §2 · 프로브 실측 정정).

🔴 설계 초안의 URL `inquire-daily-indexchart` 는 이 서버에 «없다»(HTTP 404 · 본문 빈
   문자열). 실측으로 확정된 경로는 주식기간별시세와 «같은» URL 에 시장구분 `U` 다:
   `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice` + tr_id
   `FHKUP03500100`.  → scratchpad/index_kis_probe/RESULT.md §1·§5

🔑 `kis._url_fetch` 는 404 에 «예외 대신 None» 을 준다(DEBUG 로그만). 그래서 래퍼는
   None 을 실패로 접어 호출자에게 None 을 돌려줘야 한다 — 호출자는 그걸 폴백 사유로 쓴다.
"""
import pandas as pd

import api.kis_market_api as kma


class _Body:
    def __init__(self, output2):
        self.output2 = output2


class _Res:
    def __init__(self, output2, ok=True):
        self._b = _Body(output2)
        self._ok = ok

    def isOK(self):
        return self._ok

    def getBody(self):
        return self._b


def _capture(monkeypatch, res):
    seen = {}

    def _fake_url_fetch(url, tr_id, tr_cont, params, *a, **k):
        seen["url"] = url
        seen["tr_id"] = tr_id
        seen["params"] = params
        return res

    monkeypatch.setattr(kma.kis, "_url_fetch", _fake_url_fetch)
    return seen


def test_index_daily_chart_param_contract(monkeypatch):
    seen = _capture(monkeypatch, _Res([{"stck_bsop_date": "20260907", "bstp_nmix_prpr": "6995.39"}]))

    df = kma.get_index_daily_chart("0001", "20260901", "20260909")

    assert seen["url"].endswith("/quotations/inquire-daily-itemchartprice")
    assert seen["tr_id"] == "FHKUP03500100"
    p = seen["params"]
    assert p["FID_COND_MRKT_DIV_CODE"] == "U"      # J(주식) 아님 — 업종
    assert p["FID_INPUT_ISCD"] == "0001"
    assert p["FID_INPUT_DATE_1"] == "20260901" and p["FID_INPUT_DATE_2"] == "20260909"
    assert p["FID_PERIOD_DIV_CODE"] == "D"
    assert p["FID_ORG_ADJ_PRC"] == "0"             # 업종엔 무의미하나 인자 형식상 필수
    assert isinstance(df, pd.DataFrame) and len(df) == 1


def test_index_daily_chart_accepts_kosdaq_code(monkeypatch):
    seen = _capture(monkeypatch, _Res([]))
    kma.get_index_daily_chart("1001", "20260901", "20260909")
    assert seen["params"]["FID_INPUT_ISCD"] == "1001"


def test_index_daily_chart_returns_none_when_url_fetch_returns_none(monkeypatch):
    """404 → `_url_fetch` 가 None 을 준다. 래퍼도 None 이어야 폴백이 돈다."""
    _capture(monkeypatch, None)
    assert kma.get_index_daily_chart("0001", "20260901", "20260909") is None


def test_index_daily_chart_returns_none_when_not_ok(monkeypatch):
    _capture(monkeypatch, _Res([], ok=False))
    assert kma.get_index_daily_chart("0001", "20260901", "20260909") is None


def test_index_daily_chart_empty_output2_is_empty_df_not_none(monkeypatch):
    """🔴 «빈 output2» 는 장애가 아니라 판정 대상이다 — None(=장애)과 구분한다."""
    _capture(monkeypatch, _Res([]))
    df = kma.get_index_daily_chart("0001", "20260901", "20260909")
    assert df is not None and len(df) == 0


def test_index_daily_chart_defaults_date_window(monkeypatch):
    """날짜 미지정이면 YYYYMMDD 8자리 창을 스스로 만든다."""
    seen = _capture(monkeypatch, _Res([]))
    kma.get_index_daily_chart("0001")
    p = seen["params"]
    assert len(p["FID_INPUT_DATE_1"]) == 8 and p["FID_INPUT_DATE_1"].isdigit()
    assert len(p["FID_INPUT_DATE_2"]) == 8 and p["FID_INPUT_DATE_2"].isdigit()
    assert p["FID_INPUT_DATE_1"] <= p["FID_INPUT_DATE_2"]

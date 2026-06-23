# tests/collectors/test_daily_collector.py
import pandas as pd

import collectors.daily_collector as dc
from collectors.daily_collector import reconcile_verdict, collect_one


def test_reconcile_verdict_pass_when_full_coverage_and_match():
    v = reconcile_verdict(real_rows=2600, new_rows=2600, value_match=2598)
    assert v["coverage"] >= 0.99
    assert v["value_match_rate"] >= 0.99
    assert v["verdict"] == "PASS"


def test_reconcile_verdict_fail_on_low_coverage():
    v = reconcile_verdict(real_rows=2600, new_rows=1500, value_match=1500)
    assert v["verdict"] == "FAIL"


def test_reconcile_verdict_handles_zero_real():
    v = reconcile_verdict(real_rows=0, new_rows=0, value_match=0)
    assert v["verdict"] in ("PASS", "EMPTY")


def _descending_daily_df():
    """KIS output2 처럼 최신일 우선(내림차순) 일봉 df (5 bars, 06-23 가장 위)."""
    return pd.DataFrame([
        {"stck_bsop_date": d, "stck_clpr": "100", "stck_oprc": "100",
         "stck_hgpr": "100", "stck_lwpr": "100", "acml_vol": "10", "acml_tr_pbmn": "1000"}
        for d in ["20260623", "20260620", "20260619", "20260618", "20260617"]
    ])


def test_collect_one_returns_newest_bars_on_descending_response(monkeypatch):
    """API가 내림차순(최신 먼저)으로 줘도 collect_one은 최신 lookback_days 바를 반환해야 한다.
    (회귀: 이전엔 rows[-N:]가 가장 오래된 바를 골라 당일 데이터 누락)."""
    monkeypatch.setattr(dc.kis_market_api, "get_inquire_daily_itemchartprice",
                        lambda **k: _descending_daily_df())
    monkeypatch.setattr(dc.kis_market_api, "get_stock_market_cap", lambda code: None)

    rows = collect_one("005930", lookback_days=3)
    dates = [r["date"] for r in rows]
    # 최신 3개(오름차순) — 가장 최근 06-23 반드시 포함
    assert dates == ["2026-06-19", "2026-06-20", "2026-06-23"]
    assert rows[-1]["date"] == "2026-06-23"
    assert all(r["stock_code"] == "005930" for r in rows)

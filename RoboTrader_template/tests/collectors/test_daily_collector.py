# tests/collectors/test_daily_collector.py
"""일봉 수집기 테스트.

🔴 2026-08-17 — `reconcile_verdict` 4개 테스트 삭제:
   그 함수는 「새 DB vs 레거시 robotrader_quant」 대조의 판정 헬퍼였고,
   유일한 소비자였던 reconcile_daily/index/foreign_flow 가 레거시 DB 폐기와 함께
   제거되면서 같이 사라졌다. **없어진 함수를 계속 시험할 수는 없다.**
   (삭제된 테스트: pass_when_full_coverage_and_match · fail_on_low_coverage ·
    handles_zero_real · pass_when_new_db_has_broader_coverage)
   대신 「되살아나지 않는다」를 아래 한 줄로 고정한다.
"""
import pandas as pd

import collectors.daily_collector as dc
from collectors.daily_collector import collect_one


def test_legacy_reconcile_helpers_are_gone():
    """레거시 대조 심볼 재유입 방지 — 죽은 DB 에 직접 붙던 코드다."""
    for nm in ("reconcile_daily", "reconcile_verdict", "COVERAGE_MIN", "VALUE_MATCH_MIN"):
        assert not hasattr(dc, nm), f"제거된 심볼이 되살아났다: {nm}"


def test_collect_daily_stamps_split_factor_before_adj(monkeypatch):
    """Item 3 배선: split_factor 스탬프가 update_adj_factors 보다 먼저 호출돼야
    새로 확정된 권리락 배수를 daily_adj 가 같은 밤에 반영한다."""
    order = []

    class _CM:
        def __enter__(self):
            return object()

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(dc.KisDbConnection, "get_connection", lambda: _CM())
    monkeypatch.setattr(dc, "load_universe", lambda conn: [])
    monkeypatch.setattr(dc, "update_returns_volatility", lambda conn: None)
    monkeypatch.setattr(dc, "infer_and_stamp_split_factors",
                        lambda conn: order.append("stamp") or 2)
    monkeypatch.setattr(dc, "update_adj_factors",
                        lambda conn: order.append("adj") or 0)

    out = dc.collect_daily()
    assert order == ["stamp", "adj"]          # 순서 보장
    assert out["split_factor_stamped"] == 2


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

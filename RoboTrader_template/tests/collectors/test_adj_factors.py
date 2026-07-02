"""compute_adj_factors 승격(동적 import 정상화) characterization — 동작 보존 검증."""
import datetime as dt


def test_compute_adj_factors_behavior_preserved():
    from collectors.adj_factors import compute_adj_factors
    events = {"005930": [(dt.date(2026, 3, 2), 0.02)]}
    stock_dates = {"005930": ["2026-02-27", "2026-03-02", "2026-03-03"]}
    out = compute_adj_factors(events, stock_dates)
    assert out["005930"]["2026-02-27"] == 0.02   # 이벤트 이전 날짜 → 분할계수 적용
    assert out["005930"]["2026-03-02"] == 1.0    # ed > T 조건: 당일은 미적용
    assert out["005930"]["2026-03-03"] == 1.0


def test_daily_adj_uses_promoted_function():
    """daily_adj가 importlib 없이 승격된 함수를 바인딩하는지."""
    import collectors.daily_adj as da
    from collectors.adj_factors import compute_adj_factors
    assert da.compute_adj_factors is compute_adj_factors


def test_research_script_reimports_same_object():
    """연구 스크립트(p0)의 역방향 import가 같은 객체인지 (숫자 시작 디렉토리라 importlib)."""
    import importlib
    p0 = importlib.import_module("scripts.10pct_strategy.p0_apply_adj_factor")
    from collectors.adj_factors import compute_adj_factors
    assert p0.compute_adj_factors is compute_adj_factors

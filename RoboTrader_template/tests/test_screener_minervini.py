# tests/test_screener_minervini.py
import pandas as pd
from strategies.minervini_volume_dryup.screener import MinerviniVolumeDryupScreenerAdapter


def _dryup_df():
    # 직전 30봉 거래량 1000, 최근 10봉 거래량 500 → ratio 0.5 <= 0.70
    vols = [1000] * 30 + [500] * 10
    n = len(vols)
    closes = [1000 + i for i in range(n)]
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n),
        "open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
        "close": closes, "volume": vols,
    })


def test_match_triggers_on_volume_dryup():
    a = MinerviniVolumeDryupScreenerAdapter()
    df = _dryup_df()
    verdict = a.match(df, a.default_params())
    assert verdict is not None
    assert "dryup" in verdict[1].lower()


def test_base_filter_excludes_when_market_cap_unknown():
    """market_cap=0(미상)이면 시총 컨셉(중형 이상) 검증 불가 → fail-closed 제외."""
    a = MinerviniVolumeDryupScreenerAdapter()
    universe = [
        {"code": "X", "name": "unknown", "market_cap": 0, "trading_value": 1e10},
        {"code": "Y", "name": "low_tv",  "market_cap": 0, "trading_value": 1e6},   # trading_value 미달
        {"code": "Z", "name": "none",                     "trading_value": 1e10},  # 키 결측
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert kept == []


def test_base_filter_min_cap_boundary_and_live_equivalence():
    """채워진 시총엔 기존과 동일한 하한 컷(라이브 동등성). 경계값(정확히 min)은 통과."""
    a = MinerviniVolumeDryupScreenerAdapter()
    p = a.default_params()
    tv = p["min_trading_value"] * 2
    universe = [
        {"code": "EQ", "name": "eq", "market_cap": p["min_market_cap"],     "trading_value": tv},
        {"code": "LO", "name": "lo", "market_cap": p["min_market_cap"] - 1, "trading_value": tv},
        {"code": "HI", "name": "hi", "market_cap": p["min_market_cap"] + 1, "trading_value": tv},
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert kept == ["EQ", "HI"]


def test_match_none_when_volume_not_dry():
    a = MinerviniVolumeDryupScreenerAdapter()
    df = _dryup_df()
    df.loc[df.index[-10:], "volume"] = 1000  # 최근도 1000 → ratio 1.0
    assert a.match(df, a.default_params()) is None


# ─── Trend Template 배선 (2026-08-18) ────────────────────────────────────────
# 근거: backtest/concept_axes/minervini/ — DT(dryup∧TT) +1.54% vs D(현행) +0.00%.
# 사장님 승인 「1단계 — 추세조건 추가」. 기본은 shadow(기록만, 후보 불변).

def _tt_pass_df(n=260):
    """TT 8조건을 만족하는 단조 상승 + 최근 dryup 프레임."""
    closes = [100.0 * (1.0 + 0.004 * i) for i in range(n)]
    vols = [1000] * (n - 10) + [500] * 10
    return pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=n, freq="B"),
        "open": closes, "high": [c * 1.001 for c in closes],
        "low": [c * 0.999 for c in closes], "close": closes, "volume": vols,
    })


def test_tt_wiring_constants_match_backtest():
    """창·가드 상수가 백테스트 run.py 와 어긋나면 +1.54%p 는 따라오지 않는다."""
    a = MinerviniVolumeDryupScreenerAdapter()
    # run.py:81 LOOKBACK = 260. TT 는 220봉 요구 + 52주 고저에 iloc[-252:].
    assert a.lookback_days == 260
    assert a.lookback_days >= 252
    # 창을 늘려도 위생 가드 범위는 기존(90봉) 고정 — 후보 집합을 바꾸지 않기 위해.
    assert a.sanity_window == 90
    assert a.wants_context is True


def test_shadow_mode_never_changes_the_verdict():
    """🔑 회귀 게이트 — shadow 는 «기록만» 한다. off 와 결과가 다르면 안 된다."""
    a = MinerviniVolumeDryupScreenerAdapter()
    p = a.default_params()
    df = _tt_pass_df()
    for ctx in ({"rs_value": 99.0}, {"rs_value": 1.0}, {}, None):
        off = a.match(df, {**p, "tt_filter_mode": "off"}, ctx)
        shadow = a.match(df, {**p, "tt_filter_mode": "shadow"}, ctx)
        assert (off is None) == (shadow is None)
        if off is not None:
            assert off[0] == shadow[0], "shadow 가 score 를 바꿨다"


def test_on_mode_gates_by_rs_percentile():
    """mode=on 은 TT 를 실제로 «건다» — RS 백분위만 바꿔 통과/탈락이 갈려야 한다."""
    a = MinerviniVolumeDryupScreenerAdapter()
    p = {**a.default_params(), "tt_filter_mode": "on"}
    df = _tt_pass_df()
    assert a.match(df, p, {"rs_value": 99.0}) is not None, "RS 상위인데 탈락"
    assert a.match(df, p, {"rs_value": 10.0}) is None, "RS 하위인데 통과 (rs_threshold=70)"


def test_tt_is_fail_closed_without_context():
    """🔴 ctx 가 안 오면 TT 는 조용히 False 다 — on 모드에서 후보 0건이 된다.

    이 동작 자체는 rules.py 의 계약이라 바꾸지 않는다. 대신 «그런 일이 일어난다»는
    사실을 테스트로 못박아, 배관이 끊겼을 때 진단 로그(ERROR)를 지우지 못하게 한다.
    """
    a = MinerviniVolumeDryupScreenerAdapter()
    p = {**a.default_params(), "tt_filter_mode": "on"}
    assert a.match(_tt_pass_df(), p, {}) is None
    assert a.match(_tt_pass_df(), p, None) is None


def test_short_frame_cannot_pass_tt():
    """220봉 미만이면 TT 는 무조건 False — 라이브 lookback_days 가 90이면 이 상태였다."""
    a = MinerviniVolumeDryupScreenerAdapter()
    p = {**a.default_params(), "tt_filter_mode": "on"}
    short = _tt_pass_df(n=90)
    assert a.match(short, p, {"rs_value": 99.0}) is None
    # 같은 프레임이 off/shadow 에서는 여전히 dryup 후보다(= 오늘까지의 동작).
    assert a.match(short, {**p, "tt_filter_mode": "off"}, None) is not None


def test_match_records_the_mode_that_actually_ran():
    """진단이 «안 돈 모드»를 인쇄하면 안 된다(표시 계약)."""
    a = MinerviniVolumeDryupScreenerAdapter()
    p = a.default_params()
    a.match(_tt_pass_df(), {**p, "tt_filter_mode": "off"}, None)
    assert a._tally["mode"] == "off"
    a.match(_tt_pass_df(), {**p, "tt_filter_mode": "on"}, {"rs_value": 99.0})
    assert a._tally["mode"] == "on"


def test_match_works_without_scan_counters_initialised():
    """`match()` 는 `scan()` 없이도 호출된다(단위 테스트 경로). 터지면 안 된다."""
    a = MinerviniVolumeDryupScreenerAdapter()
    assert a.match(_dryup_df(), a.default_params()) is not None

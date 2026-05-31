import numpy as np
import pandas as pd
import pytest
from scripts.exit_multiverse import portfolio_sim
from scripts.exit_multiverse import adapters


# ---------------------------------------------------------------------------
# 회귀: elder stop 경로 line-115 df.iloc[trigger_high_idx] 범위초과 방어.
#
# 진짜 근본원인 = 유니버스 비결정성(ORDER BY turnover DESC LIMIT N, tiebreak 없음)으로
# 동일 종목코드에 대해 워커마다 길이가 다른 df 가 들어올 수 있고, 이때 부모에서
# 사전계산한 신호 인덱스(=trigger_high_idx 의 출처)가 더 짧은 df 길이를 넘어서면
# df.iloc[trigger_high_idx] 가 "single positional indexer is out-of-bounds" 를 던졌다.
# (이전 오진: screen1_uptrend(wclose) 의 ema65.iloc[-6] — 이미 len<6 가드가 있어 무관.)
#
# 이 테스트는 stop 분기에서 stale 한 pending(=trigger_high_idx 가 df 길이 초과)을
# 직접 구성해, 수정 전엔 IndexError, 수정 후엔 stale pending 제거로 무사 완주함을 확인한다.
# ---------------------------------------------------------------------------

def _make_elder_stop_df(n=80):
    """Elder 매수스톱 경로를 통과할 수 있는 최소 데이터프레임 (완만한 우상향)."""
    closes = [100.0 + 0.5 * k for k in range(n)]
    return pd.DataFrame({
        "datetime": pd.date_range("2021-01-01", periods=n),
        "open":  closes,
        "high":  [c + 1.0 for c in closes],  # high > close → stop trigger 가능
        "low":   [c - 1.0 for c in closes],
        "close": closes,
        "volume": [10000] * n,
    })


def test_elder_stop_normal_path_no_index_error():
    """elder stop 분기 정상 경로(완만한 우상향, 신호→pending→체결/만료)가
    line-115 df.iloc[trigger_high_idx] 를 정상 인덱스로 반복 실행하며
    IndexError 없이 완주해야 한다(근본원인 라인의 happy-path 커버)."""
    df = _make_elder_stop_df(n=80)
    data = {"000001": df}
    signal_cache = {"000001": [70, 72, 74]}  # 워밍업 이후 여러 신호 → pending 추적
    ad = adapters.ADAPTERS["elder_ema_pullback"]
    params = {
        "stop_loss_pct": 0.08, "take_profit_pct": 0.30,
        "max_hold_bars": 60, "trail_ema": None, "trend_flip_exit": False,
    }
    res = portfolio_sim.run_portfolio(
        data=data, signal_cache=signal_cache, adapter=ad, params=params,
        turnover={"000001": 1.0}, initial_capital=10_000_000,
        max_positions=5, max_per_stock=3_000_000, unconstrained=False)
    assert isinstance(res["equity_curve"], list)
    assert len(res["equity_curve"]) > 0


def test_prior_high_at_out_of_bounds_returns_none():
    """근본원인 단위 회귀: stop 매수의 직전봉 고가 조회 헬퍼 _prior_high_at 가
    trigger_idx 가 df 범위를 벗어날 때(=유니버스 비결정성으로 부모/자식 df 길이가
    어긋난 stale pending) IndexError 대신 None 을 반환해야 한다.

    수정 전 portfolio_sim 의 stop 분기는 df.iloc[trigger_high_idx] 를 무가드로 접근해
    'single positional indexer is out-of-bounds' IndexError 를 던졌다(병렬 전용 크래시).
    """
    df = _make_elder_stop_df(n=20)
    n = len(df)
    # 정상(in-bounds): 실제 고가 반환
    assert portfolio_sim._prior_high_at(df, 0) == float(df.iloc[0]["high"])
    assert portfolio_sim._prior_high_at(df, n - 1) == float(df.iloc[n - 1]["high"])
    # OOB(=길이 이상): None (수정 전엔 IndexError 가 났던 지점)
    assert portfolio_sim._prior_high_at(df, n) is None
    assert portfolio_sim._prior_high_at(df, n + 5) is None
    # 방어적: 음수/None 도 None
    assert portfolio_sim._prior_high_at(df, -1) is None
    assert portfolio_sim._prior_high_at(df, None) is None
    # 가드가 없었다면 OOB 접근은 IndexError 였음을 명시
    with pytest.raises(IndexError):
        _ = df.iloc[n]["high"]


def test_elder_stop_stale_pending_out_of_bounds_no_crash(monkeypatch):
    """end-to-end 회귀: stop 분기에서 pending 의 trigger_high_idx 가 df 범위를
    벗어나도(부모/자식 df 길이 불일치 모사) run_portfolio 가 IndexError 없이
    완주하고 stale pending 을 제거해야 한다.

    포트심은 일관 입력 하에선 이 상태를 자체 생성하지 않으므로, krx_tick·
    screen1_uptrend 를 가로채 pending 을 유지시키고, _prior_high_at 를 감싸
    '항상 OOB' 처럼 동작하게 해 stop 체결을 강제로 막는다(=가드 분기 상시 진입)."""
    df = _make_elder_stop_df(n=80)
    data = {"000001": df}
    signal_cache = {"000001": [70, 72, 74]}
    ad = adapters.ADAPTERS["elder_ema_pullback"]
    params = {
        "stop_loss_pct": 0.08, "take_profit_pct": 0.30,
        "max_hold_bars": 60, "trail_ema": None, "trend_flip_exit": False,
    }

    # _prior_high_at 를 'trigger_idx 가 곧 len(df) 인 것처럼' OOB 로 강제 → 항상 None →
    # 가드 분기(stale pending pop)가 매 사이클 실행됨. IndexError 없이 완주해야 한다.
    monkeypatch.setattr(portfolio_sim, "_prior_high_at", lambda _df, _idx: None)

    res = portfolio_sim.run_portfolio(
        data=data, signal_cache=signal_cache, adapter=ad, params=params,
        turnover={"000001": 1.0}, initial_capital=10_000_000,
        max_positions=5, max_per_stock=3_000_000, unconstrained=False)
    assert len(res["equity_curve"]) > 0
    # 모든 pending 이 가드로 제거되었으므로 매수 체결은 0 건이어야 한다.
    assert sum(1 for t in res["trades"] if t["side"] == "buy") == 0


def _flat_then_drop(n=80):
    closes = [100.0] * 72 + [100.0, 100.0, 100.0, 100.0, 100.0, 90.0, 90.0, 90.0]
    closes = (closes + [90.0] * n)[:n]
    return pd.DataFrame({
        "datetime": pd.date_range("2021-01-01", periods=n),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [1000] * n,
    })


def test_max_positions_caps_holdings():
    data = {f"{i:06d}": _flat_then_drop() for i in range(5)}
    signal_cache = {code: [72] for code in data}  # 모두 i=72 신호
    ad = adapters.ADAPTERS["book_pullback_ma5"]
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.99, "max_hold_bars": 999, "trail_ma": None}
    res = portfolio_sim.run_portfolio(
        data=data, signal_cache=signal_cache, adapter=ad, params=params,
        turnover={code: float(i) for i, code in enumerate(data)},
        initial_capital=10_000_000, max_positions=2, max_per_stock=3_000_000,
        unconstrained=False)
    assert res["max_concurrent_positions"] <= 2
    assert res["n_skipped"] >= 1


def test_equity_curve_nonempty():
    data = {"000001": _flat_then_drop()}
    signal_cache = {"000001": [72]}
    ad = adapters.ADAPTERS["book_pullback_ma5"]
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.99, "max_hold_bars": 999, "trail_ma": None}
    res = portfolio_sim.run_portfolio(
        data=data, signal_cache=signal_cache, adapter=ad, params=params,
        turnover={"000001": 1.0}, initial_capital=10_000_000,
        max_positions=5, max_per_stock=3_000_000, unconstrained=False)
    assert len(res["equity_curve"]) > 0
    assert "daily_returns" in res
    assert isinstance(res["daily_returns"], pd.Series)


def test_force_close_at_series_end():
    # 청산 조건이 끝까지 안 걸리는 종목은 시리즈 종료 시 forced_close 되어야 한다.
    n = 80
    closes = [100.0] * n  # 평탄 → sl/tp/mh(999)/trail(None) 미발동
    df = pd.DataFrame({
        "datetime": pd.date_range("2021-01-01", periods=n),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [1000] * n,
    })
    data = {"000777": df}
    signal_cache = {"000777": [72]}
    ad = adapters.ADAPTERS["book_pullback_ma5"]
    params = {"stop_loss_pct": 0.99, "take_profit_pct": 0.99, "max_hold_bars": 999, "trail_ma": None}
    res = portfolio_sim.run_portfolio(
        data=data, signal_cache=signal_cache, adapter=ad, params=params,
        turnover={"000777": 1.0}, initial_capital=10_000_000,
        max_positions=5, max_per_stock=3_000_000, unconstrained=False)
    sells = [t for t in res["trades"] if t["side"] == "sell"]
    assert len(sells) == 1
    assert sells[0]["reason"] == "forced_close"

"""deep_mr_dev20 전략 단위 테스트 — 진입(룰 단일소스)·청산 우선순위·일봉 청산 해상도.

검증 근거: 발굴 게이트 deep_mr_dev20 (reports/discovery/gate_deep_mr_dev20.md)
백테스트 정합: 진입=scripts.discovery.rules.MeanReversionMA20Rule(-20%),
청산=MAReversionExitAdapter 와 동일 우선순위(sl→tp→recovery→max_hold).
"""
import numpy as np
import pandas as pd

from strategies.deep_mr_dev20.strategy import DeepMrDev20Strategy


def _crash_df(last_close: float, n: int = 40):
    close = np.full(n, 100.0)
    close[-3] = 90.0
    close[-2] = 80.0
    close[-1] = last_close
    return pd.DataFrame({
        "datetime": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": [1000.0] * n,
    })


# --- 진입 (백테스트 룰 단일소스) ---

def test_entry_triggers_on_deep_crash():
    # last=77 → MA20≈97.35 → dev≈-20.9% ≤ -20 AND RSI14<30(연속하락)
    ok, reasons = DeepMrDev20Strategy.evaluate_entry(_crash_df(77.0))
    assert ok and reasons


def test_entry_no_trigger_shallow():
    # last=85 → dev≈-13% > -20 → 미발사
    ok, _ = DeepMrDev20Strategy.evaluate_entry(_crash_df(85.0))
    assert not ok


def test_entry_insufficient_bars():
    ok, _ = DeepMrDev20Strategy.evaluate_entry(_crash_df(77.0, n=20))
    assert not ok


# --- 청산 우선순위 (백테스트 MAReversionExitAdapter 정합: sl→tp→recovery→mh) ---

def test_sell_stop_loss_first():
    df = _crash_df(70.0)
    should, reasons, why = DeepMrDev20Strategy.evaluate_sell_conditions(
        df, entry_price=77.0, hold_days=1)
    assert should and why == "stop_loss"


def test_sell_take_profit():
    df = _crash_df(88.0)  # entry 77 → +14.3% ≥ tp12. recovery 보다 tp 가 우선
    should, _, why = DeepMrDev20Strategy.evaluate_sell_conditions(
        df, entry_price=77.0, hold_days=1)
    assert should and why == "take_profit"


def test_sell_ma_recovery():
    # entry 80 → +6.3%(tp 미달, sl 미달), close 85 vs MA20×0.9≈87.9? → 85<87.9 미회복.
    # close 89: MA20=(17*100+90+80+89)/20=97.95, 0.9×=88.2 → 89>=88.2 회복. ret +11.3%<tp12.
    df = _crash_df(89.0)
    should, _, why = DeepMrDev20Strategy.evaluate_sell_conditions(
        df, entry_price=80.0, hold_days=1)
    assert should and why == "ma_recovery"


def test_sell_max_hold():
    df = _crash_df(78.0)  # entry 77 → +1.3%, 회복선 미달
    should, _, why = DeepMrDev20Strategy.evaluate_sell_conditions(
        df, entry_price=77.0, hold_days=7)
    assert should and why == "max_hold"


def test_sell_hold_when_nothing():
    df = _crash_df(78.0)
    should, _, _ = DeepMrDev20Strategy.evaluate_sell_conditions(
        df, entry_price=77.0, hold_days=2)
    assert not should


# --- 라이브 안전장치 ---

def test_exit_timeframe_daily():
    # Elder whipsaw 교훈(2026-06-09): 일봉 청산 전략은 exit_timeframe='daily' 필수
    assert DeepMrDev20Strategy.exit_timeframe == "daily"


def test_holding_period_swing():
    assert DeepMrDev20Strategy.holding_period == "swing"


def test_no_volume_fallback():
    # 폭락 희소조건 — 후보 없으면 미진입이 정합 (거래량 상위 폴백 풀 부적합)
    assert DeepMrDev20Strategy.accepts_volume_fallback is False


# --- 분봉 청산 가드 (2026-06-12 즉시청산 버그) ---
# position_monitor.py가 보유종목 매도판단에 무조건 timeframe='intraday'로 분봉을
# 전달 → 분봉 MA20≈현재가라 '현재가 ≥ MA20×0.9'가 항상 참 → 매수 수분 내
# ma_recovery 즉시청산(06-12 라이브 3종목 전부). exit_timeframe='daily' 선언만으로는
# base.on_tick 경로만 보호되므로 generate_signal 자체가 분봉 매도판단을 거부해야 한다.

def _held_strategy(entry_price: float = 100.0) -> DeepMrDev20Strategy:
    s = DeepMrDev20Strategy(config={})
    s.on_init(None, None, None)
    s.positions["000001"] = {
        "quantity": 10, "entry_price": entry_price, "entry_time": None,
    }
    return s


def _flat_df(n: int = 40, price: float = 100.0):
    """분봉 유사 데이터 — MA20≈현재가 → 가드 없으면 ma_recovery 즉시 발사."""
    close = np.full(n, price)
    return pd.DataFrame({
        "datetime": pd.date_range("2024-01-02 09:00", periods=n, freq="min"),
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": [1000.0] * n,
    })


def test_intraday_timeframe_never_triggers_sell():
    """timeframe='intraday'(position_monitor 경로)는 보유 중이어도 매도신호 금지."""
    s = _held_strategy()
    assert s.generate_signal("000001", _flat_df(), timeframe="intraday") is None


def test_daily_timeframe_still_sells_on_ma_recovery():
    """가드 이동이 정상 일봉 청산(base.on_tick daily 경로)을 죽이면 안 됨."""
    from strategies.base import SignalType
    s = _held_strategy()
    sig = s.generate_signal("000001", _flat_df(), timeframe="daily")
    assert sig is not None
    assert sig.signal_type == SignalType.SELL
    assert sig.metadata.get("exit_reason") == "ma_recovery"

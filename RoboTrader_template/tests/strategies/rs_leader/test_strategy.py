from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from strategies.rs_leader.strategy import RSLeaderStrategy


def test_exit_timeframe_daily():
    # Elder/deep_mr whipsaw 교훈(2026-06-09): 일봉 swing 전략이 exit_timeframe='intraday'면
    # ma_break를 분봉 MA로 평가해 '매수 직후 매도' whipsaw 발생. 실전 진입 전 필수 방어.
    assert RSLeaderStrategy.exit_timeframe == "daily"


def _load_config():
    cfg_path = Path(__file__).resolve().parents[3] / "strategies" / "rs_leader" / "config.yaml"
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


# 라이브 ctx.get_daily_data 가 공급하는 확정 일봉 수의 보수적 하한.
# robotrader ~78~85봉(OHLCV_LOOKBACK_DAYS 120 기반, 주말/휴장/당일 제외) — 2026-06-10 실측 78.
LIVE_DAILY_BAR_SUPPLY = 78


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1000] * n,
    })


def test_entry_gate_accepts_live_bar_supply():
    """진입 게이트(min_daily_bars)는 라이브 일봉 공급(~78봉) 이하여야 한다.

    실제 진입 룰(RSLeaderRule)은 MA60+60일수익 = 61봉이면 충분한데,
    config 의 min_daily_bars 가 스크리너 RS워밍업(130)을 차용하면
    라이브 일봉(<130)이 영구히 게이트를 못 넘어 매수 0건이 된다(2026-06-10 버그).
    """
    strat = RSLeaderStrategy(config=_load_config())
    gate = strat.get_min_data_length()
    assert gate <= LIVE_DAILY_BAR_SUPPLY, (
        f"게이트 {gate}봉 > 라이브 공급 {LIVE_DAILY_BAR_SUPPLY}봉 → 영구 미발사"
    )
    # 그 게이트로 통과한 라이브 폭(78봉) 상승추세는 실제 진입 시그널을 내야 한다.
    closes = list(np.linspace(10000, 20000, LIVE_DAILY_BAR_SUPPLY))
    ok, reasons = RSLeaderStrategy.evaluate_entry(_df(closes), min_daily_bars=gate)
    assert ok is True and reasons


def test_evaluate_entry_uptrend_true():
    closes = list(np.linspace(10000, 20000, 130))
    ok, reasons = RSLeaderStrategy.evaluate_entry(_df(closes), min_daily_bars=130)
    assert ok is True and reasons


def test_evaluate_entry_downtrend_false():
    closes = list(np.linspace(20000, 10000, 130))
    ok, reasons = RSLeaderStrategy.evaluate_entry(_df(closes), min_daily_bars=130)
    assert ok is False


def test_sell_stop_loss():
    closes = [10000] * 25 + [9000]
    should, reasons, code = RSLeaderStrategy.evaluate_sell_conditions(
        _df(closes), entry_price=10000.0, hold_days=1,
        stop_loss_pct=0.08, max_hold_days=30, trail_ma=20)
    assert should and code == "stop_loss"


def test_sell_ma20_break_unconditional():
    # 상승 후 MA20 아래로 마감 → ma_break (수익여부 무관, 검증 4-bis 정합)
    closes = list(range(10000, 10030)) + [10010]
    should, reasons, code = RSLeaderStrategy.evaluate_sell_conditions(
        _df(closes), entry_price=10010.0, hold_days=1,
        stop_loss_pct=0.08, max_hold_days=30, trail_ma=20)
    assert should and code == "ma_break"


def test_sell_hold_when_above_ma():
    closes = list(range(10000, 10040))
    should, reasons, code = RSLeaderStrategy.evaluate_sell_conditions(
        _df(closes), entry_price=10030.0, hold_days=1,
        stop_loss_pct=0.08, max_hold_days=30, trail_ma=20)
    assert should is False


# --- 분봉 청산 가드 (whipsaw 방지) ---
# position_monitor.py가 보유종목 매도판단에 무조건 timeframe='intraday'로 분봉을
# 전달한다. rs_leader의 ma_break는 무조건(ret 게이트 없음)이라 분봉 MA20≈현재가
# 부근에서 항상 발동 → 매수 직후 청산. timeframe 가드가 매도분기보다 앞에 있어야
# 분봉 경로가 차단된다. 일봉(base.on_tick) 경로는 그대로 동작해야 한다.

def _held_strategy(entry_price: float = 10000.0):
    s = RSLeaderStrategy(config=_load_config())
    s.on_init(None, None, None)
    s.positions["000001"] = {
        "quantity": 10, "entry_price": entry_price, "entry_time": None,
    }
    return s


def _ma_break_df():
    """상승 후 MA20 아래로 마감 → ma_break(무조건) 발동 형태.

    get_min_data_length()(=65봉) 통과를 위해 71봉으로 구성. 마지막 봉(10050)이
    MA20(10059.5) 아래라 ma_break 발동, entry_price=10050이면 ret=0이라
    stop_loss/take_profit 미충족 → 청산 사유는 ma_break 단독.
    """
    closes = list(range(10000, 10070)) + [10050]
    return _df(closes)


def test_intraday_held_no_sell():
    """timeframe='intraday'(position_monitor 경로)는 보유 중이어도 매도신호 금지."""
    s = _held_strategy(entry_price=10050.0)
    assert s.generate_signal("000001", _ma_break_df(), timeframe="intraday") is None


def test_daily_held_still_sells_on_ma_break():
    """가드 이동이 정상 일봉 청산(base.on_tick daily 경로)을 죽이면 안 됨."""
    from strategies.base import SignalType
    s = _held_strategy(entry_price=10050.0)
    sig = s.generate_signal("000001", _ma_break_df(), timeframe="daily")
    assert sig is not None
    assert sig.signal_type == SignalType.SELL
    assert sig.metadata.get("exit_reason") == "ma_break"


# --- 진입 밴드 (2026-06-15) — 돌파형: up=3%, down=None ---

def test_buy_signal_has_breakout_band(monkeypatch):
    """BUY 신호에 돌파형 밴드(max=cur*1.03, min=None)가 담긴다."""
    import pytest
    from strategies.base import SignalType

    monkeypatch.setattr(
        "strategies.rs_leader.strategy.MarketHours.is_market_open",
        staticmethod(lambda market="KRX": True),
    )
    strat = RSLeaderStrategy(config=_load_config())
    strat.on_init(None, None, None)

    closes = list(np.linspace(10000, 20000, LIVE_DAILY_BAR_SUPPLY))
    df = _df(closes)
    sig = strat.generate_signal("005930", df, timeframe="daily")
    assert sig is not None and sig.signal_type == SignalType.BUY
    cur = float(df["close"].iloc[-1])
    assert sig.entry_max_price == pytest.approx(cur * 1.03)
    assert sig.entry_min_price is None

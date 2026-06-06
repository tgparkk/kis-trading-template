import pandas as pd

from scripts.rs_leader.exit_adapter import MA20TrailExitAdapter


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2021-01-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1000] * n,
    })


PARAMS = {"stop_loss_pct": 0.08, "take_profit_pct": 99.0, "max_hold_bars": 100}


def test_stop_loss_first():
    # 진입가 100, 현재가 90 → -10% ≤ -8% 손절.
    closes = [100] * 25 + [90]
    df = _df(closes)
    pos = {"entry_idx": 24, "entry_price": 100.0, "qty": 10, "entry_date": "x"}
    adapter = MA20TrailExitAdapter()
    assert adapter.exit_reason(df, 25, pos, PARAMS) == "stop_loss"


def test_ma_break_exits_when_close_below_ma20():
    # 상승 후 마지막 봉이 MA20 아래로 종가 마감 → ma_break (손절 전엔 아님).
    closes = list(range(100, 130)) + [110]  # 30봉 상승(100..129) 후 110으로 하락
    df = _df(closes)
    pos = {"entry_idx": 28, "entry_price": 110.0, "qty": 1, "entry_date": "x"}
    adapter = MA20TrailExitAdapter()
    # 마지막 봉(i=30) close=110, MA20(직전20봉 평균)은 110보다 높음 → ma_break.
    assert adapter.exit_reason(df, 30, pos, PARAMS) == "ma_break"


def test_hold_when_above_ma_and_not_stopped():
    # 단조 상승 → 종가>MA20, 손절·만기 아님 → None(보유).
    closes = list(range(100, 140))
    df = _df(closes)
    pos = {"entry_idx": 30, "entry_price": 130.0, "qty": 1, "entry_date": "x"}
    adapter = MA20TrailExitAdapter()
    assert adapter.exit_reason(df, 39, pos, PARAMS) is None


def test_max_hold():
    closes = list(range(100, 140))
    df = _df(closes)
    pos = {"entry_idx": 10, "entry_price": 110.0, "qty": 1, "entry_date": "x"}
    adapter = MA20TrailExitAdapter()
    p = dict(PARAMS, max_hold_bars=5)
    # i=20, hold=10 ≥ 5. 단 종가>MA20 이라 ma_break 아님 → max_hold 도달.
    assert adapter.exit_reason(df, 20, pos, p) == "max_hold"

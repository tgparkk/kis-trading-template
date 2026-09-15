"""캡/한도 스킵 계기 — `generate_signal` 이 None 을 돌려준 «사유» 3개를 구분해 남긴다.

닫으려는 결함(CRITIC_synthesis.md §D-3, 2026-09-15): 3전략의 None 경로가
①`timeframe != "daily"` ②`daily_trades >= _max_daily_trades`
③`len(positions) >= _max_positions` 로 셋인데, 로그가 전부 동일해
「캡 포화로 막힌 날」이 「룰 미충족」으로 위장됐다(09-14·09-15 EOD 실측:
ma20 5/5·minervini 3/3 포화가 첫 틱부터 매수 불가였는데 로그로 구분 불가).

이 파일이 단언하는 것:
  ① 세 사유가 각각 «구분되는» INFO 한 줄로 찍힌다
  ② 반환값은 셋 다 그대로 None — 로그 계층이 매매 판단을 바꾸지 않는다
  ③ 같은 (전략, 종목, 사유) 는 하루 1회만 찍는다(2,900회 폭주 금지)
  ④ 캡에 안 걸리는 경로는 이 줄을 «안» 찍는다(거짓 양성 금지)

⚠️ logger 는 `utils/logger.py:106` 에서 `propagate = False` 라 caplog 로 안
   잡힌다. 그래서 Mock 로거를 꽂아 호출을 직접 본다.
"""
from datetime import date
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from strategies.book_pullback_ma20.strategy import BookPullbackMa20Strategy
from strategies.minervini_volume_dryup.strategy import MinerviniVolumeDryupStrategy
from strategies.daytrading_3methods_breakout.strategy import (
    DayTrading3MethodsBreakoutStrategy,
)

CASES = [
    (BookPullbackMa20Strategy, "book_pullback_ma20"),
    (MinerviniVolumeDryupStrategy, "minervini_volume_dryup"),
    (DayTrading3MethodsBreakoutStrategy, "daytrading_3methods_breakout"),
]


def _flat_daily(n: int = 120) -> pd.DataFrame:
    """평평한 일봉 — 어떤 진입 룰도 만족시키지 않는다(사유 격리용)."""
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "datetime": idx,
            "open": np.full(n, 10000.0),
            "high": np.full(n, 10000.0),
            "low": np.full(n, 10000.0),
            "close": np.full(n, 10000.0),
            "volume": np.full(n, 100000.0),
        }
    )


def _make(cls):
    s = cls({"paper_trading": True})
    s.on_init(None, None, None)
    s.logger = Mock()
    return s


def _cap_lines(strategy) -> list:
    return [
        c.args[0]
        for c in strategy.logger.info.call_args_list
        if c.args and isinstance(c.args[0], str) and c.args[0].startswith("[캡]")
    ]


@pytest.mark.parametrize("cls,key", CASES)
def test_timeframe_skip_logs_reason(cls, key):
    s = _make(cls)
    data = _flat_daily()

    assert s.generate_signal("005930", data, timeframe="intraday") is None

    lines = _cap_lines(s)
    assert len(lines) == 1, lines
    assert lines[0] == (
        f"[캡] {key} 005930 평가 스킵 사유=timeframe "
        f"보유=0/{s._max_positions} 일일매수=0/{s._max_daily_trades}"
    )


@pytest.mark.parametrize("cls,key", CASES)
def test_daily_trades_cap_logs_reason(cls, key):
    s = _make(cls)
    s.daily_trades = s._max_daily_trades
    data = _flat_daily()

    assert s.generate_signal("005930", data, timeframe="daily") is None

    lines = _cap_lines(s)
    assert len(lines) == 1, lines
    assert lines[0] == (
        f"[캡] {key} 005930 평가 스킵 사유=daily_trades "
        f"보유=0/{s._max_positions} 일일매수={s._max_daily_trades}/{s._max_daily_trades}"
    )


@pytest.mark.parametrize("cls,key", CASES)
def test_max_positions_cap_logs_reason(cls, key):
    s = _make(cls)
    k = s._max_positions
    s.positions = {f"1000{i:02d}": {"quantity": 1} for i in range(k)}
    data = _flat_daily()

    assert s.generate_signal("005930", data, timeframe="daily") is None

    lines = _cap_lines(s)
    assert len(lines) == 1, lines
    assert lines[0] == (
        f"[캡] {key} 005930 평가 스킵 사유=max_positions "
        f"보유={k}/{k} 일일매수=0/{s._max_daily_trades}"
    )


@pytest.mark.parametrize("cls,key", CASES)
def test_same_stock_reason_logged_once_per_day(cls, key):
    s = _make(cls)
    s.daily_trades = s._max_daily_trades
    data = _flat_daily()

    for _ in range(50):
        assert s.generate_signal("005930", data, timeframe="daily") is None

    assert len(_cap_lines(s)) == 1

    # 다른 종목은 별도 1회
    for _ in range(50):
        s.generate_signal("035720", data, timeframe="daily")
    assert len(_cap_lines(s)) == 2

    # 날짜가 바뀌면(다음 거래일) 억제가 풀린다
    s._cap_skip_log_date = date(2000, 1, 1)
    s.generate_signal("005930", data, timeframe="daily")
    assert len(_cap_lines(s)) == 3


@pytest.mark.parametrize("cls,key", CASES)
def test_no_cap_line_when_rule_simply_unmet(cls, key):
    """캡이 비어 있으면(룰 미충족 경로) `[캡]` 줄이 «없어야» 한다."""
    s = _make(cls)
    data = _flat_daily()

    assert s.generate_signal("005930", data, timeframe="daily") is None
    assert _cap_lines(s) == []


@pytest.mark.parametrize("cls,key", CASES)
def test_held_stock_takes_sell_path_without_cap_line(cls, key):
    """보유 종목 매도 판단 경로는 캡 계기의 대상이 아니다(순서 불변 증거)."""
    s = _make(cls)
    s.daily_trades = s._max_daily_trades
    s.positions = {"005930": {"quantity": 1}}
    s._check_sell = Mock(return_value=None)
    data = _flat_daily()

    # ma20 은 timeframe 체크가 매도분기보다 «앞»이므로 daily 로 호출한다.
    assert s.generate_signal("005930", data, timeframe="daily") is None
    s._check_sell.assert_called_once()
    assert _cap_lines(s) == []

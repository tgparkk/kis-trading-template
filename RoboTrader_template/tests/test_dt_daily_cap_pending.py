"""daytrading 하루 매수 한도(max_daily_trades) = «체결 매수 + 미체결 매수(BUY_PENDING)» (2026-10-29 창구 ⑭).

닫으려는 구멍(10-26 결함 수정 `451e912` 리뷰 M1): 자리(K) 검사에는 `_pending_buy_count()` 를
더했지만 하루 한도 검사 `self.daily_trades >= self._max_daily_trades` 는 체결 콜백에서만 +1 되는
`daily_trades` 만 셌다. 실전 지정가가 미체결로 머무는 동안 «체결 4 + 미체결 1» 이면 새 신호가
6번째 매수 주문으로 나간다(자리 구멍과 같은 구조).

수정: dt 하루 한도 판정 = `daily_trades + _pending_buy_count() >= max_daily_trades`.
미체결은 체결되면 positions 로 옮겨 가 `_pending_buy_count` 에서 빠지고 `daily_trades` 가 +1
되므로 이중 계상 0 · 취소/타임아웃이면 provider 목록에서 빠져 한도가 복귀한다.
M2: 훅(provider) 예외 → 0 폴백은 그대로, 처음 1회만 WARNING 을 남긴다(무로그 폴백 금지).

⚠️ logger 는 propagate=False 라 caplog 로 안 잡힌다 — Mock 로거를 꽂아 호출을 직접 본다.
"""
from datetime import datetime
from unittest.mock import Mock

import numpy as np
import pandas as pd

from strategies.base import OrderInfo
from strategies.daytrading_3methods_breakout.strategy import (
    DayTrading3MethodsBreakoutStrategy,
)

DAILY_CAP = 5
FILLED4 = ["000001", "000002", "000003", "000004"]  # 오늘 체결 매수 4
PENDING_CODE = "338840"
NEW_CODE = "005930"
BUY_SIGNAL = object()  # _check_buy 도달 표지


def _make(provider=None):
    s = DayTrading3MethodsBreakoutStrategy(
        {"paper_trading": False, "risk_management": {"max_positions": 10, "max_daily_trades": DAILY_CAP}}
    )
    assert s.on_init(None, None, None)
    s.logger = Mock()
    s._check_buy = Mock(return_value=BUY_SIGNAL)
    if provider is not None:
        s.pending_buy_codes_provider = provider
    return s


def _buy_fill(code: str) -> OrderInfo:
    return OrderInfo(order_id="O1", stock_code=code, side="buy", quantity=1,
                     price=10000.0, filled_at=datetime(2026, 10, 29, 9, 20))


def _fill_today(s, codes):
    """체결 콜백 경로로 오늘 매수 체결을 만든다(daily_trades·positions 동시 반영)."""
    for c in codes:
        s.on_order_filled(_buy_fill(c))


def _daily(n: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    flat = np.full(n, 10000.0)
    return pd.DataFrame(
        {"datetime": idx, "open": flat, "high": flat, "low": flat,
         "close": flat, "volume": np.full(n, 100000.0)}
    )


def _cap_lines(s) -> list:
    return [
        c.args[0] for c in s.logger.info.call_args_list
        if c.args and isinstance(c.args[0], str) and c.args[0].startswith("[캡]")
    ]


# (a) 체결 4 + 미체결 1 + 새 신호 → 막힘 -------------------------------------------

def test_filled4_plus_pending1_blocks_new_buy():
    pending = [PENDING_CODE]
    s = _make(lambda: list(pending))
    _fill_today(s, FILLED4)
    assert s.daily_trades == 4

    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is None
    s._check_buy.assert_not_called()
    lines = _cap_lines(s)
    assert len(lines) == 1, lines
    assert "사유=daily_trades" in lines[0]
    # 기존 파서 호환: «일일매수=d/D» 는 체결 수 그대로 · 미체결은 기존 꼬리 필드로
    assert "일일매수=4/5 " in lines[0]
    assert lines[0].endswith("미체결매수=1")


# (b) 미체결 취소(provider 빈 목록) → 같은 신호 통과 ----------------------------------

def test_pending_cancelled_reopens_daily_cap():
    pending = [PENDING_CODE]
    s = _make(lambda: list(pending))
    _fill_today(s, FILLED4)
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is None

    pending.clear()  # 엔진: 취소/타임아웃 BUY_PENDING → SELECTED/COMPLETED
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is BUY_SIGNAL
    s._check_buy.assert_called_once()


# (c) 체결 5 → 막힘(기존 동작) ----------------------------------------------------

def test_filled5_blocks_without_pending():
    s = _make(lambda: [])
    _fill_today(s, FILLED4 + ["000005"])
    assert s.daily_trades == 5
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is None
    s._check_buy.assert_not_called()
    lines = _cap_lines(s)
    assert len(lines) == 1 and "사유=daily_trades" in lines[0], lines
    assert "미체결매수" not in lines[0]


# (d) 미체결이 체결되면 positions 로 이동 — 이중 계상 없이 5/5 ---------------------------

def test_pending_filled_counts_once_4_plus_1_to_5_plus_0():
    pending = [PENDING_CODE]  # 체결 콜백 순간 엔진 상태가 아직 BUY_PENDING 이어도
    s = _make(lambda: list(pending))
    _fill_today(s, FILLED4)
    assert s.daily_trades + s._pending_buy_count() == 5

    s.on_order_filled(_buy_fill(PENDING_CODE))
    assert s.daily_trades == 5
    assert s._pending_buy_count() == 0  # positions 에 있는 코드는 미체결로 안 셈
    assert s.daily_trades + s._pending_buy_count() == 5  # 6 이 아니다
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is None


def test_pending_filled_3_plus_1_to_4_plus_0_stays_open():
    pending = [PENDING_CODE]
    s = _make(lambda: list(pending))
    _fill_today(s, FILLED4[:3])
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is BUY_SIGNAL  # 3+1=4 <5

    s.on_order_filled(_buy_fill(PENDING_CODE))  # 상태가 늦게 바뀌어도 4+0 = 4
    assert s.generate_signal("000777", _daily(), timeframe="daily") is BUY_SIGNAL


# (e) provider None → 0 · 경고 0 -------------------------------------------------

def test_no_provider_zero_and_no_warning():
    s = _make()
    assert s.pending_buy_codes_provider is None
    _fill_today(s, FILLED4)
    assert s._pending_buy_count() == 0
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is BUY_SIGNAL  # 4 <5 기존 동작
    s.logger.warning.assert_not_called()


# (f) provider 예외 → 0 + WARNING 1회(두 번째 호출엔 경고 없음) ------------------------

def test_provider_exception_warns_once_then_silent():
    def boom():
        raise RuntimeError("state manager gone")

    s = _make(boom)
    assert s._pending_buy_count() == 0
    assert s.logger.warning.call_count == 1
    msg = s.logger.warning.call_args.args[0]
    assert msg.startswith("[자리훅] pending_buy_codes_provider 예외 → 0 폴백: ")
    assert "RuntimeError('state manager gone')" in msg

    assert s._pending_buy_count() == 0
    _fill_today(s, FILLED4)
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is BUY_SIGNAL  # 폴백 = 기존 동작
    assert s.logger.warning.call_count == 1  # 중복 억제

"""일일 한도(`max_daily_trades`) = «하루 매수 체결 수» — 매도는 세지 않는다 (2026-10-08 발효).

닫으려는 결함: 활성 8전략의 `on_order_filled` 가 `self.daily_trades += 1` 을 `is_buy` 분기
«앞»에서 실행해 매도도 셌다. 아침에 손절·익절·보유기간 만료 매도가 몰리면 자리가 비어도
그날 매수가 막혔다(10-07 daytrading 매도 4 + 매수 1 → 09:06 한도 → 자리 6칸 빈 채 마감).
점검 기록: audit_2026-08-24 M20-9 · R-4 · DM-11 · audit_2026-08-23 E-5.

이 파일이 단언하는 것(8전략 각각):
  ① 매도 5건 체결 뒤에도 매수 판단(`_check_buy`)에 도달한다 — 카운터 0
  ② 매수 5건 체결 뒤엔 막힌다 — 보유를 다 판 뒤라 `max_positions` 가 아니라 `daily_trades` 가 막는다
  ③ 리셋(`on_market_open` → 0)은 그대로이고, 장 마감 줄은 «매수 N건» 이다
"""
from datetime import datetime
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from strategies.base import OrderInfo
from strategies.book_envelope_200d.strategy import BookEnvelope200dStrategy
from strategies.book_pullback_ma20.strategy import BookPullbackMa20Strategy
from strategies.book_pullback_ma5.strategy import BookPullbackMa5Strategy
from strategies.daytrading_3methods_breakout.strategy import (
    DayTrading3MethodsBreakoutStrategy,
)
from strategies.deep_mr_dev20.strategy import DeepMrDev20Strategy
from strategies.elder_ema_pullback.strategy import ElderEmaPullbackStrategy
from strategies.minervini_volume_dryup.strategy import MinerviniVolumeDryupStrategy
from strategies.rs_leader.strategy import RSLeaderStrategy

CLASSES = [
    ElderEmaPullbackStrategy,
    BookEnvelope200dStrategy,
    DayTrading3MethodsBreakoutStrategy,
    MinerviniVolumeDryupStrategy,
    BookPullbackMa20Strategy,
    BookPullbackMa5Strategy,
    RSLeaderStrategy,
    DeepMrDev20Strategy,
]
CODES = ["000010", "000020", "000030", "000040", "000050"]
NEW_CODE = "005930"
BUY_SIGNAL = object()  # _check_buy 도달 표지


def _make(cls):
    s = cls({"paper_trading": True})
    assert s.on_init(None, None, None)
    s.logger = Mock()
    assert s._max_daily_trades == 5
    # 진입 룰과 무관하게 «캡을 통과해 매수 판단에 도달했는가»만 본다.
    s._check_buy = Mock(return_value=BUY_SIGNAL)
    return s


def _daily(strategy) -> pd.DataFrame:
    n = max(300, strategy.get_min_data_length() + 5)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    flat = np.full(n, 10000.0)
    return pd.DataFrame({"datetime": idx, "open": flat, "high": flat,
                         "low": flat, "close": flat, "volume": np.full(n, 100000.0)})


def _fill(strategy, code: str, side: str) -> None:
    strategy.on_order_filled(OrderInfo(
        order_id=f"T-{side}-{code}", stock_code=code, side=side,
        quantity=1, price=10000.0, filled_at=datetime(2026, 10, 8, 9, 5),
    ))


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.__name__)
def test_five_sells_do_not_block_buy(cls):
    s = _make(cls)
    # 전날 보유 5종목(기동 복원 경로) → 아침 매도 5건 체결
    s.sync_positions({c: {"quantity": 1, "entry_price": 10000.0, "entry_time": None}
                      for c in CODES})
    for c in CODES:
        _fill(s, c, "sell")

    assert s.positions == {}
    assert s.daily_trades == 0
    assert s.generate_signal(NEW_CODE, _daily(s), timeframe="daily") is BUY_SIGNAL
    s._check_buy.assert_called_once()


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.__name__)
def test_five_buys_block_buy(cls):
    s = _make(cls)
    for c in CODES:
        _fill(s, c, "buy")
    assert s.daily_trades == 5
    # 보유를 전부 팔아 자리를 비운다 — 매도는 카운터를 바꾸지 않는다
    for c in CODES:
        _fill(s, c, "sell")
    assert s.positions == {}
    assert s.daily_trades == 5

    assert s.generate_signal(NEW_CODE, _daily(s), timeframe="daily") is None
    s._check_buy.assert_not_called()


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.__name__)
def test_market_open_resets_and_close_line_counts_buys(cls):
    s = _make(cls)
    for c in CODES:
        _fill(s, c, "buy")
    _fill(s, CODES[0], "sell")
    s.on_market_close()
    s.logger.info.assert_any_call(f"장 마감 — 매수 5건, 보유 {len(CODES) - 1}종목")

    s.on_market_open()
    assert s.daily_trades == 0
    for c in CODES[1:]:
        _fill(s, c, "sell")
    assert s.generate_signal(NEW_CODE, _daily(s), timeframe="daily") is BUY_SIGNAL

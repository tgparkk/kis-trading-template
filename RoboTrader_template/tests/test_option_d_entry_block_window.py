"""
옵션 D-C: 09:05~09:08 진입 차단 윈도우 검증
==========================================

사장님 결재 2026-05-14 — scientist 분석 결과
09:05~09:08 시간대 매수 승률 17% (n=6) → 회피 목적.

검증 지점: strategies/sample/strategy.py
  generate_signal()의 매수 분기 직전 차단 가드.

설계 선택: 옵션 (b) — 정밀 윈도우 차단
  - 09:00 시가 진입(승률 47%)은 유지
  - 09:05:00 <= now < 09:08:00 차단
  - 09:08:00 이후 진입 허용

검증 시나리오:
  1. 09:00:00 — 차단됨 (기존 market_open_skip_minutes=5 가드, 09:00~09:05)
     ※ 의뢰의 "09:00 시가 진입 유지"는 09:05 직후를 의미하므로
        09:00 자체는 기존 가드에 의해 차단 — 코드 동작 그대로
  2. 09:04:59 — 차단됨 (market_open_skip 영역, 09:05 직전)
  3. 09:05:00 — 차단됨 (entry_block_window 시작)
  4. 09:07:59 — 차단됨 (entry_block_window 끝 직전)
  5. 09:08:00 — 허용됨 (entry_block_window 종료)
  6. 09:10:00 — 허용됨 (의뢰 "09:10 이후 진입 허용")
  7. 10:00:00 — 허용됨 (정상 매수 시간대)
  8. 윈도우 비활성화 (start_min >= end_min) — 회귀 호환 검증
"""
import sys
from datetime import datetime, time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.sample.strategy import SampleStrategy


# ============================================================================
# Helpers
# ============================================================================

def _make_strategy(*, block_start_min=5, block_end_min=8,
                   market_open_skip_minutes=5) -> SampleStrategy:
    """SampleStrategy 인스턴스 + on_init 호출."""
    config = {
        "strategy": {"name": "SampleStrategy", "version": "1.0.0"},
        "parameters": {
            "ma_short_period": 5,
            "ma_long_period": 20,
            "rsi_period": 14,
            "rsi_oversold": 40,
            "rsi_overbought": 70,
            "rsi_entry_max": 60,
            "volume_multiplier": 1.5,
            "min_buy_signals": 1,
            "market_open_skip_minutes": market_open_skip_minutes,
            "entry_block_window_start_min": block_start_min,
            "entry_block_window_end_min": block_end_min,
        },
        "risk_management": {
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "max_position_size": 0.10,
            "max_daily_trades": 5,
        },
        "target_stocks": [],
    }
    s = SampleStrategy(config)
    # on_init은 broker/data_provider/executor 의존성 있으므로 수동 세팅
    s.on_init(broker=None, data_provider=None, executor=None)
    return s


def _make_buyable_data(length: int = 30) -> pd.DataFrame:
    """매수 조건을 만족하는 OHLCV 데이터 (MA5 > MA20, 거래량 급증)."""
    # 우상향 가격 + 마지막 봉 거래량 폭증
    prices = np.array([10000 + i * 50 for i in range(length)], dtype=float)
    volumes = [1_000_000] * (length - 1) + [3_000_000]  # 마지막만 3배
    return pd.DataFrame({
        "open": prices * 0.995,
        "high": prices * 1.005,
        "low": prices * 0.990,
        "close": prices,
        "volume": volumes,
    })


def _gen_signal_at_time(strategy: SampleStrategy, h: int, m: int, s: int = 0,
                       stock_code: str = "005930"):
    """주어진 시각에 generate_signal 실행한 결과를 반환."""
    fake_now = datetime(2026, 5, 14, h, m, s)
    data = _make_buyable_data()
    with patch('strategies.sample.strategy.datetime') as mock_dt:
        mock_dt.now.return_value = fake_now
        # datetime 클래스 호출 자체는 통과시켜야 함 (time(9,0) 등)
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        return strategy.generate_signal(stock_code, data, timeframe='daily')


# ============================================================================
# Test: 옵션 D-C 진입 차단 윈도우
# ============================================================================

class TestEntryBlockWindow:
    """09:05~09:08 정밀 차단 윈도우 동작 검증."""

    def test_0900_blocked_by_market_open_skip(self):
        """09:00:00 — 기존 market_open_skip 가드(09:00~09:05)에 의해 차단."""
        s = _make_strategy()
        signal = _gen_signal_at_time(s, 9, 0, 0)
        assert signal is None, "09:00 차단되어야 함 (market_open_skip)"

    def test_0904_59_blocked_by_market_open_skip(self):
        """09:04:59 — 기존 market_open_skip 가드 영역."""
        s = _make_strategy()
        signal = _gen_signal_at_time(s, 9, 4, 59)
        assert signal is None, "09:04:59 차단되어야 함 (market_open_skip)"

    def test_0905_00_blocked_by_entry_block_window(self):
        """09:05:00 — entry_block_window 시작 시각, 차단."""
        s = _make_strategy()
        signal = _gen_signal_at_time(s, 9, 5, 0)
        assert signal is None, "09:05:00 차단되어야 함 (entry_block_window)"

    def test_0907_59_blocked_by_entry_block_window(self):
        """09:07:59 — entry_block_window 끝 직전, 차단."""
        s = _make_strategy()
        signal = _gen_signal_at_time(s, 9, 7, 59)
        assert signal is None, "09:07:59 차단되어야 함 (entry_block_window)"

    def test_0908_00_allowed(self):
        """09:08:00 — entry_block_window 종료, 매수 허용."""
        s = _make_strategy()
        signal = _gen_signal_at_time(s, 9, 8, 0)
        # 매수 신호가 발생하거나, 적어도 차단 사유(market_open_skip/entry_block)가
        # 아닌 다른 사유로 None일 수 있음. 핵심: 차단 윈도우 통과 검증.
        # → 매수 데이터를 buyable로 구성했으므로 BUY 신호 기대
        assert signal is not None, \
            "09:08:00에는 매수 신호가 발생해야 함 (차단 통과)"
        from strategies.base import SignalType
        assert signal.signal_type == SignalType.BUY

    def test_0910_00_allowed(self):
        """09:10:00 — 의뢰 본문 '09:10 이후 진입 허용' 명시 시각."""
        s = _make_strategy()
        signal = _gen_signal_at_time(s, 9, 10, 0)
        assert signal is not None, "09:10:00에는 매수 신호가 발생해야 함"

    def test_1000_00_allowed(self):
        """10:00:00 — 일반 매수 시간대, 정상 허용."""
        s = _make_strategy()
        signal = _gen_signal_at_time(s, 10, 0, 0)
        assert signal is not None, "10:00:00에는 매수 신호가 발생해야 함"

    def test_window_disabled_when_start_ge_end(self):
        """block_start_min >= block_end_min 이면 윈도우 비활성 (회귀 호환).

        검증: 윈도우를 비활성화하면 기존 market_open_skip 가드(09:00~09:05)만
        남고, 09:05 이후는 모두 매수 허용 (옵션 D-C 적용 이전 동작과 동일).
        """
        s = _make_strategy(block_start_min=8, block_end_min=8)
        assert s._entry_block_enabled is False, "동일 값일 때 비활성"

        # 09:04:59 — 기존 market_open_skip 가드에 의해 차단 (윈도우와 무관)
        signal = _gen_signal_at_time(s, 9, 4, 59)
        assert signal is None, "09:04:59는 market_open_skip 가드로 차단"

        # 09:05:00 — market_open_skip(09:00~09:05) 통과 + 윈도우 비활성
        # → 옵션 D-C 적용 이전 동작 = 매수 신호 발생 가능
        signal = _gen_signal_at_time(s, 9, 5, 0)
        assert signal is not None, \
            "윈도우 비활성이면 09:05:00에 옵션 D-C 적용 이전 동작 유지"

        # 09:06, 09:07도 윈도우 비활성이면 매수 가능 (회귀 동작)
        signal = _gen_signal_at_time(s, 9, 7, 0)
        assert signal is not None, "윈도우 비활성 시 09:07도 매수 허용"

    def test_entry_block_attrs_initialized(self):
        """on_init에서 차단 윈도우 속성이 올바르게 초기화되는지."""
        s = _make_strategy(block_start_min=5, block_end_min=8)
        assert s._entry_block_start == time(9, 5)
        assert s._entry_block_end == time(9, 8)
        assert s._entry_block_enabled is True

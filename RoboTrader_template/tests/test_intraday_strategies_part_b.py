"""
Smoke 테스트 — 분봉 데이트레이딩 전략 Part B (전략 6~10)
=========================================================

각 전략의 BUY 신호 발생 케이스와 None 반환 케이스를 검증한다.
_base_intraday.py가 없으면 전체 스킵.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Base import guard
# ---------------------------------------------------------------------------
try:
    from strategies.intraday._base_intraday import IntradayBaseStrategy  # noqa: F401
except ImportError:
    pytest.skip("_base_intraday.py 미작성 — Part B 스킵", allow_module_level=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minute_df(
    n: int,
    base_price: float = 10000,
    start: datetime = None,
    price_fn=None,
    volume_fn=None,
) -> pd.DataFrame:
    """분봉 DataFrame 생성 헬퍼.

    Args:
        n: 봉 수
        base_price: 기준 가격
        start: 시작 datetime (기본 09:00)
        price_fn: (i, base) -> close 값 함수 (없으면 base_price 고정)
        volume_fn: (i) -> volume 값 함수 (없으면 1_000_000 고정)
    """
    if start is None:
        start = datetime(2026, 5, 16, 9, 0, 0)
    if price_fn is None:
        price_fn = lambda i, bp: bp
    if volume_fn is None:
        volume_fn = lambda i: 1_000_000

    rows = []
    for i in range(n):
        dt = start + timedelta(minutes=i)
        c = price_fn(i, base_price)
        rows.append({
            "datetime": dt,
            "open": c * 0.999,
            "high": c * 1.002,
            "low": c * 0.998,
            "close": c,
            "volume": volume_fn(i),
        })
    return pd.DataFrame(rows)


def _make_strategy(cls, extra_config: dict = None):
    """전략 인스턴스 생성 헬퍼."""
    config = {
        "strategy": {"name": cls.name, "version": "1.0.0"},
        "parameters": {},
        "risk_management": {
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "eod_cutoff_buy": "15:00",
        },
    }
    if extra_config:
        for k, v in extra_config.items():
            if isinstance(v, dict) and k in config:
                config[k].update(v)
            else:
                config[k] = v
    return cls(config=config)


# ===========================================================================
# 전략 6: VWAPTrade
# ===========================================================================

class TestVwapTradeStrategy:
    @pytest.fixture
    def strategy(self):
        from strategies.intraday.vwap_trade.strategy import VwapTradeStrategy
        return _make_strategy(VwapTradeStrategy, {"parameters": {"vol_zscore_threshold": 1.0, "vol_window": 20}})

    def _make_vwap_buy_data(self) -> pd.DataFrame:
        """VWAP보다 높은 close + 높은 거래량(z-score > 1) 데이터."""
        n = 30
        start = datetime(2026, 5, 16, 9, 0)
        rows = []
        base = 10000
        for i in range(n):
            dt = start + timedelta(minutes=i)
            # close를 점진적으로 올려서 VWAP보다 위로 만들기
            c = base + i * 10
            # 마지막 봉은 거래량 급증 (z-score > 1 확보)
            vol = 500_000 if i < n - 1 else 3_000_000
            rows.append({
                "datetime": dt,
                "open": c - 5,
                "high": c + 10,
                "low": c - 10,
                "close": c,
                "volume": vol,
                "amount": c * vol,
            })
        return pd.DataFrame(rows)

    def test_buy_signal_generated(self, strategy):
        """close > VWAP + volume z-score > 1 → BUY 신호."""
        from strategies.base import SignalType
        data = self._make_vwap_buy_data()
        signal = strategy.generate_signal("005930", data, timeframe="minute")
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.stock_code == "005930"
        assert signal.stop_loss is not None
        assert signal.target_price is not None

    def test_wrong_timeframe_returns_none(self, strategy):
        """timeframe='daily' → None."""
        data = self._make_vwap_buy_data()
        signal = strategy.generate_signal("005930", data, timeframe="daily")
        assert signal is None

    def test_insufficient_data_returns_none(self, strategy):
        """데이터 부족 → None."""
        data = _make_minute_df(5)
        signal = strategy.generate_signal("005930", data, timeframe="minute")
        assert signal is None

    def test_after_eod_cutoff_returns_none(self, strategy):
        """15:00 이후 datetime → None."""
        n = 30
        start = datetime(2026, 5, 16, 15, 1)
        data = _make_minute_df(n, start=start, volume_fn=lambda i: 3_000_000)
        signal = strategy.generate_signal("005930", data, timeframe="minute")
        assert signal is None

    def test_close_below_vwap_returns_none(self, strategy):
        """close < VWAP → None (거래량 많아도)."""
        n = 30
        start = datetime(2026, 5, 16, 9, 0)
        rows = []
        base = 10000
        for i in range(n):
            dt = start + timedelta(minutes=i)
            # close가 하락해서 VWAP 아래로
            c = base - i * 20
            rows.append({
                "datetime": dt,
                "open": c + 5,
                "high": c + 10,
                "low": c - 10,
                "close": c,
                "volume": 3_000_000,
                "amount": c * 3_000_000,
            })
        data = pd.DataFrame(rows)
        signal = strategy.generate_signal("005930", data, timeframe="minute")
        assert signal is None


# ===========================================================================
# 전략 7: SupportResistance
# ===========================================================================

class TestSupportResistanceStrategy:
    @pytest.fixture
    def strategy(self):
        from strategies.intraday.support_resistance.strategy import SupportResistanceStrategy
        return _make_strategy(SupportResistanceStrategy, {"parameters": {"near_s1_band_pct": 0.005}})

    def _prev_ohlc(self):
        """전일 OHLC — S1 계산용."""
        return {"high": 11000.0, "low": 9000.0, "close": 10000.0}

    def _calc_s1(self, prev):
        """S1 = 2*pivot - high."""
        pivot = (prev["high"] + prev["low"] + prev["close"]) / 3
        return 2 * pivot - prev["high"]

    def test_buy_signal_near_s1(self, strategy):
        """현재가가 S1 ± 0.5% 범위 → BUY 신호."""
        from strategies.base import SignalType
        prev = self._prev_ohlc()
        s1 = self._calc_s1(prev)

        n = 15
        start = datetime(2026, 5, 16, 9, 30)
        # close를 S1에 맞추기
        data = _make_minute_df(n, base_price=s1, start=start)
        data.attrs["prev_day_ohlc"] = prev

        signal = strategy.generate_signal("000660", data, timeframe="minute")
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert "s1" in signal.metadata
        assert "r1" in signal.metadata

    def test_no_signal_far_from_s1(self, strategy):
        """현재가가 S1에서 멀리 떨어짐 → None."""
        prev = self._prev_ohlc()
        s1 = self._calc_s1(prev)

        n = 15
        start = datetime(2026, 5, 16, 9, 30)
        # close를 S1에서 5% 위로
        data = _make_minute_df(n, base_price=s1 * 1.05, start=start)
        data.attrs["prev_day_ohlc"] = prev

        signal = strategy.generate_signal("000660", data, timeframe="minute")
        assert signal is None

    def test_no_prev_ohlc_returns_none(self, strategy):
        """prev_day_ohlc 없으면 None."""
        data = _make_minute_df(15)
        signal = strategy.generate_signal("000660", data, timeframe="minute")
        assert signal is None

    def test_wrong_timeframe_returns_none(self, strategy):
        """timeframe='daily' → None."""
        prev = self._prev_ohlc()
        data = _make_minute_df(15)
        data.attrs["prev_day_ohlc"] = prev
        signal = strategy.generate_signal("000660", data, timeframe="daily")
        assert signal is None

    def test_after_eod_cutoff_returns_none(self, strategy):
        """15:00 이후 → None."""
        prev = self._prev_ohlc()
        s1 = self._calc_s1(prev)
        start = datetime(2026, 5, 16, 15, 5)
        data = _make_minute_df(15, base_price=s1, start=start)
        data.attrs["prev_day_ohlc"] = prev
        signal = strategy.generate_signal("000660", data, timeframe="minute")
        assert signal is None


# ===========================================================================
# 전략 8: RedToGreen
# ===========================================================================

class TestRedToGreenStrategy:
    @pytest.fixture
    def strategy(self):
        from strategies.intraday.red_to_green.strategy import RedToGreenStrategy
        return _make_strategy(RedToGreenStrategy)

    def test_buy_signal_on_crossing(self, strategy):
        """전일 종가 상향 돌파 분봉 → BUY 신호.

        red_to_green()은 첫 교차 시점 봉에만 True를 반환한다.
        전략은 signals.iloc[-1]을 체크하므로 마지막 봉이 첫 교차여야 한다.
        여기서는 6봉(min_len=5 통과) 데이터의 마지막 봉을 첫 교차로 만든다.
        """
        from strategies.base import SignalType
        prev_close = 10000.0
        start = datetime(2026, 5, 16, 9, 0)

        # 5봉은 prev_close 아래, 마지막(6번째) 봉이 위로 돌파
        rows = []
        prices = [9800, 9850, 9900, 9930, 9970, 10050]
        for i, p in enumerate(prices):
            dt = start + timedelta(minutes=i)
            rows.append({
                "datetime": dt,
                "open": p - 10,
                "high": p + 20,
                "low": p - 20,
                "close": p,
                "volume": 1_000_000,
            })
        data = pd.DataFrame(rows)
        data.attrs["prev_close"] = prev_close

        signal = strategy.generate_signal("035420", data, timeframe="minute")
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata.get("prev_close") == prev_close

    def test_no_signal_stays_below_prev_close(self, strategy):
        """close가 계속 prev_close 아래 → None."""
        prev_close = 10000.0
        start = datetime(2026, 5, 16, 9, 0)
        data = _make_minute_df(10, base_price=9800, start=start)
        data.attrs["prev_close"] = prev_close

        signal = strategy.generate_signal("035420", data, timeframe="minute")
        assert signal is None

    def test_no_prev_close_returns_none(self, strategy):
        """prev_close 없으면 None."""
        data = _make_minute_df(10)
        signal = strategy.generate_signal("035420", data, timeframe="minute")
        assert signal is None

    def test_wrong_timeframe_returns_none(self, strategy):
        """timeframe='daily' → None."""
        data = _make_minute_df(10)
        data.attrs["prev_close"] = 10000.0
        signal = strategy.generate_signal("035420", data, timeframe="daily")
        assert signal is None

    def test_after_eod_cutoff_returns_none(self, strategy):
        """15:00 이후 → None."""
        prev_close = 9000.0
        start = datetime(2026, 5, 16, 15, 1)
        data = _make_minute_df(10, base_price=10000, start=start)
        data.attrs["prev_close"] = prev_close
        signal = strategy.generate_signal("035420", data, timeframe="minute")
        assert signal is None


# ===========================================================================
# 전략 9: ORB
# ===========================================================================

class TestOrbStrategy:
    @pytest.fixture
    def strategy(self):
        from strategies.intraday.orb.strategy import OrbStrategy
        return _make_strategy(OrbStrategy, {"parameters": {"box_minutes": 30}})

    def _make_orb_data(self, breakout: bool = True) -> pd.DataFrame:
        """09:00~10:00 분봉 60개 데이터.

        breakout=True: 09:30 이후 봉이 박스 고가를 돌파.
        breakout=False: 박스 고가 아래 유지.
        """
        start = datetime(2026, 5, 16, 9, 0)
        rows = []
        box_high = 10500  # 개장 30분 박스 고가

        for i in range(60):
            dt = start + timedelta(minutes=i)
            if i < 30:
                # 개장 박스: 9800 ~ 10500 범위
                c = 10000 + (i % 5) * 100
                h = 10500
                l = 9800
            else:
                # 09:30 이후
                if breakout:
                    c = box_high + 200  # 돌파
                    h = c + 50
                    l = c - 50
                else:
                    c = box_high - 100  # 돌파 안 함
                    h = c + 50
                    l = c - 50
            rows.append({
                "datetime": dt,
                "open": c - 20,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1_000_000,
            })
        return pd.DataFrame(rows)

    def test_buy_signal_on_orb_breakout(self, strategy):
        """09:30 이후 박스 고가 돌파 → BUY 신호."""
        from strategies.base import SignalType
        data = self._make_orb_data(breakout=True)
        signal = strategy.generate_signal("247540", data, timeframe="minute")
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata.get("or_high") is not None

    def test_no_signal_no_breakout(self, strategy):
        """박스 고가 아래 유지 → None."""
        data = self._make_orb_data(breakout=False)
        signal = strategy.generate_signal("247540", data, timeframe="minute")
        assert signal is None

    def test_no_signal_before_breakout_time(self, strategy):
        """09:30 이전 → None (박스 완성 전)."""
        # 09:29까지만 데이터 (29봉)
        start = datetime(2026, 5, 16, 9, 0)
        data = _make_minute_df(29, base_price=10700, start=start)
        signal = strategy.generate_signal("247540", data, timeframe="minute")
        assert signal is None

    def test_wrong_timeframe_returns_none(self, strategy):
        """timeframe='daily' → None."""
        data = self._make_orb_data(breakout=True)
        signal = strategy.generate_signal("247540", data, timeframe="daily")
        assert signal is None

    def test_after_eod_cutoff_returns_none(self, strategy):
        """15:00 이후 → None."""
        start = datetime(2026, 5, 16, 15, 5)
        data = _make_minute_df(40, base_price=10700, start=start)
        signal = strategy.generate_signal("247540", data, timeframe="minute")
        assert signal is None


# ===========================================================================
# 전략 10: Pullback
# ===========================================================================

class TestPullbackStrategy:
    @pytest.fixture
    def strategy(self):
        from strategies.intraday.pullback.strategy import PullbackStrategy
        return _make_strategy(
            PullbackStrategy,
            {
                "parameters": {
                    "ema_period": 5,
                    "lookback_bars": 5,
                    "lower_band": 0.99,
                    "upper_band": 1.005,
                }
            },
        )

    def _make_pullback_buy_data(self) -> pd.DataFrame:
        """EMA 단조 상승 추세 + 마지막 봉이 EMA 근처에서 반등하는 데이터.

        전략 조건:
          1) ema_window = ema.iloc[-(lookback_bars+1):-1] 이 단조 상승
             → lookback_bars=5 이므로 iloc[-6:-1] (5개) 가 모두 상승이어야 함
          2) last_close 가 prev_ema 의 99%~100.5% 범위
          3) last_close > prev_close (반등)

        설계:
          - 22봉 완만한 상승(봉당 +5원) → EMA5 도 단조 상승
          - index 21(prev): close = index 20 close 보다 약간 낮아 눌림목
          - index 22(last): close > index 21 close 이고 prev_ema 범위 내
          - lookback window = ema[idx 16..20] (5개) 가 모두 상승 → 단조 상승 성립
        """
        start = datetime(2026, 5, 16, 9, 0)
        rows = []

        # 봉당 +5원 상승 (idx 0~20: 21봉) → EMA window(idx 16~20) 단조 상승 보장
        base = 15000
        prices = [base + i * 5 for i in range(21)]  # idx 0~20: 15000~15100

        # idx 21 (prev): EMA[21]≈15090.7 보다 살짝 낮은 눌림목
        # idx 22 (last): prev(15092)보다 높고 EMA 범위(99%~100.5%) 안
        prices.append(15092)   # idx 21 (prev): 눌림목
        prices.append(15096)   # idx 22 (last): 반등, prev보다 높고 EMA 범위 내

        for i, c in enumerate(prices):
            dt = start + timedelta(minutes=i)
            rows.append({
                "datetime": dt,
                "open": c - 3,
                "high": c + 5,
                "low": c - 5,
                "close": c,
                "volume": 1_000_000,
            })
        return pd.DataFrame(rows)

    def test_buy_signal_on_pullback(self, strategy):
        """EMA 단조 상승 + 눌림목 + 반등 → BUY 신호."""
        from strategies.base import SignalType
        data = self._make_pullback_buy_data()
        signal = strategy.generate_signal("096770", data, timeframe="minute")
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert "ema_value" in signal.metadata

    def test_no_signal_non_monotone_ema(self, strategy):
        """EMA가 단조 상승하지 않으면 → None."""
        start = datetime(2026, 5, 16, 9, 0)
        # 가격이 오르내려서 EMA 단조 상승 안 됨
        prices = [10000, 10200, 9900, 10100, 9800, 10050, 9950, 10000,
                  9900, 10100, 9800, 10050, 9950, 10000, 9950, 10000]
        rows = []
        for i, c in enumerate(prices):
            dt = start + timedelta(minutes=i)
            rows.append({
                "datetime": dt,
                "open": c - 10,
                "high": c + 15,
                "low": c - 15,
                "close": c,
                "volume": 1_000_000,
            })
        data = pd.DataFrame(rows)
        signal = strategy.generate_signal("096770", data, timeframe="minute")
        assert signal is None

    def test_insufficient_data_returns_none(self, strategy):
        """데이터 부족 → None."""
        data = _make_minute_df(10)
        signal = strategy.generate_signal("096770", data, timeframe="minute")
        assert signal is None

    def test_wrong_timeframe_returns_none(self, strategy):
        """timeframe='daily' → None."""
        data = self._make_pullback_buy_data()
        signal = strategy.generate_signal("096770", data, timeframe="daily")
        assert signal is None

    def test_after_eod_cutoff_returns_none(self, strategy):
        """15:00 이후 → None."""
        start = datetime(2026, 5, 16, 15, 1)
        data = self._make_pullback_buy_data()
        # datetime 컬럼을 15:00 이후로 교체
        data["datetime"] = [start + timedelta(minutes=i) for i in range(len(data))]
        signal = strategy.generate_signal("096770", data, timeframe="minute")
        assert signal is None

"""유지윤 『하루 만에 수익 내는 데이트레이딩 3대 타법』 — 일봉 룰 단위 테스트.

지지(10캔들) / 바닥(3×3) / 바닥(2지지) / 돌파(전고점) 4종 일봉 룰의
트리거·경계실패·워밍업·no-lookahead·모듈레벨(ALL_RULES/build_strategy/BOOK_META).
trading_legends 일봉 테스트 레이아웃 1:1 미러.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# 공통 헬퍼: 일봉 OHLCV 생성 (trading_legends 테스트와 동일 시그니처)
# ---------------------------------------------------------------------------

def _make_df(close, *, open_=None, high=None, low=None, volume=None):
    close = np.asarray(close, dtype=float)
    n = len(close)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    open_ = close.copy() if open_ is None else np.asarray(open_, dtype=float)
    high = (np.maximum(open_, close) * 1.005) if high is None else np.asarray(high, dtype=float)
    low = (np.minimum(open_, close) * 0.995) if low is None else np.asarray(low, dtype=float)
    volume = np.full(n, 1_000.0) if volume is None else np.asarray(volume, dtype=float)
    return pd.DataFrame({
        "datetime": dates,
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


# ---------------------------------------------------------------------------
# T1: rule_support_10candle (지지 타법 — 급등 후 지지 10캔들 + 거래량 점감 → 폭증 진입)
# ---------------------------------------------------------------------------

def _support_10candle_triggering_df():
    """급등 30봉 윈도우(+25%↑) → 지지 10캔들(고점 부근 유지·거래량 점감) → 당일 거래량 폭증 양봉.

    레이아웃(인덱스, 뒤에서부터):
      pre_window = df.iloc[-(30+10+1):-(10+1)] = df.iloc[-41:-11]  (급등 탐색 30봉)
      support_window = df.iloc[-11:-1]  (지지 10캔들)
      current = df.iloc[-1]  (거래량 폭증 양봉)
    need = 30+10+2 = 42봉.
    """
    # warmup 1봉(need=42 충족용; 음수 인덱스 슬라이싱 불변)
    warmup = np.full(1, 8_000.0)
    # 급등 30봉: 8000 → 10500 (+31% > +25%), 거래량 고수준(급등 봉 거래량 큼)
    surge = np.linspace(8_000.0, 10_500.0, 30)
    # 지지 10봉: 10000 부근 유지 (pre_high=10500 의 (1-0.10)=9450 이상)
    support = np.full(10, 10_000.0)
    # current 1봉 placeholder
    close = np.concatenate([warmup, surge, support, np.array([10_050.0])])
    n = len(close)  # warmup1+surge30+support10+1 = 42
    assert n == 42
    vol = np.concatenate([
        np.full(1, 5_000.0),    # warmup
        np.full(30, 5_000.0),   # 급등 구간 고거래량 (argmax close=마지막 급등봉=5000)
        np.full(10, 1_000.0),   # 지지 구간 점감 거래량 (avg=1000 < surge_vol 5000*0.80=4000)
        np.array([3_000.0]),    # current placeholder
    ])
    df = _make_df(close, volume=vol)
    # current 봉: 양봉 + 거래량 >= avg_support_vol(1000) * 2.0 = 2000
    df.loc[df.index[-1], "open"] = 10_000.0
    df.loc[df.index[-1], "close"] = 10_300.0   # 양봉
    df.loc[df.index[-1], "high"] = 10_350.0
    df.loc[df.index[-1], "low"] = 9_990.0
    df.loc[df.index[-1], "volume"] = 3_000.0   # >= 2000
    return df


class TestRuleSupport10Candle:
    def test_triggers_on_surge_support_volspike(self):
        from strategies.books.daytrading_3methods.rules import rule_support_10candle
        df = _support_10candle_triggering_df()
        res = rule_support_10candle().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.side == "buy"
        assert "pre_high" in res.metadata
        assert "vol_ratio" in res.metadata

    def test_fails_without_surge(self):
        from strategies.books.daytrading_3methods.rules import rule_support_10candle
        df = _support_10candle_triggering_df()
        # 급등 구간을 평탄화 → surge 조건 미달
        for i in range(-41, -11):
            df.loc[df.index[i], "open"] = 10_000.0
            df.loc[df.index[i], "high"] = 10_050.0
            df.loc[df.index[i], "low"] = 9_950.0
            df.loc[df.index[i], "close"] = 10_000.0
        res = rule_support_10candle().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_fails_without_volume_spike(self):
        from strategies.books.daytrading_3methods.rules import rule_support_10candle
        df = _support_10candle_triggering_df()
        df.loc[df.index[-1], "volume"] = 1_100.0  # < avg_support_vol(1000)*2.0
        res = rule_support_10candle().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_insufficient_warmup_returns_false(self):
        from strategies.books.daytrading_3methods.rules import rule_support_10candle
        df = _make_df(np.full(20, 10_000.0))  # < 30+10+2
        res = rule_support_10candle().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T2: rule_floor_3x3 (바닥 타법 — 상승3일 + 지지3일 → 돌파 진입)
# ---------------------------------------------------------------------------

def _floor_3x3_triggering_df():
    """상승 3봉(+5%↑ 단조증가) → 지지 3봉(횡보) → 당일 돌파 양봉 + 거래량.

    need = rise_bars(3)+support_bars(3)+6 = 12봉.
      rise_window = df.iloc[-7:-4]  (상승 3봉)
      support_window = df.iloc[-4:-1]  (지지 3봉)
      current = df.iloc[-1]
    """
    warmup = np.full(5, 9_500.0)            # 5봉 (거래량 평균 기준선 + warmup)
    rise = np.array([9_500.0, 9_900.0, 10_200.0])   # 단조증가, (10200-9500)/9500=+7.4% > +5%
    support = np.full(3, 10_200.0)         # rise.close.iloc[-1]=10200 부근 횡보
    current = np.array([10_400.0])
    close = np.concatenate([warmup, rise, support, current])
    assert len(close) == 12
    vol = np.concatenate([
        np.full(11, 1_000.0),
        np.array([2_000.0]),   # current 거래량 (직전 5봉 평균 1000 * 1.2 = 1200 이상)
    ])
    df = _make_df(close, volume=vol)
    # support 3봉: low >= 10200*(1-0.05)=9690, high <= 10200*(1+0.10)=11220
    for i in range(-4, -1):
        df.loc[df.index[i], "low"] = 10_100.0
        df.loc[df.index[i], "high"] = 10_300.0
        df.loc[df.index[i], "open"] = 10_200.0
        df.loc[df.index[i], "close"] = 10_200.0
    # current: 양봉 + close >= max(support high)=10300 (돌파)
    df.loc[df.index[-1], "open"] = 10_250.0
    df.loc[df.index[-1], "close"] = 10_400.0   # > 10300 돌파, 양봉
    df.loc[df.index[-1], "high"] = 10_450.0
    df.loc[df.index[-1], "low"] = 10_240.0
    df.loc[df.index[-1], "volume"] = 2_000.0
    return df


class TestRuleFloor3x3:
    def test_triggers_on_rise3_support3_breakout(self):
        from strategies.books.daytrading_3methods.rules import rule_floor_3x3
        df = _floor_3x3_triggering_df()
        res = rule_floor_3x3().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.side == "buy"
        assert "breakout_level" in res.metadata

    def test_fails_without_rise(self):
        from strategies.books.daytrading_3methods.rules import rule_floor_3x3
        df = _floor_3x3_triggering_df()
        # 상승 3봉을 평탄화 → 단조증가/+5% 미달
        for i in range(-7, -4):
            df.loc[df.index[i], "close"] = 10_200.0
            df.loc[df.index[i], "open"] = 10_200.0
        res = rule_floor_3x3().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_fails_without_breakout(self):
        from strategies.books.daytrading_3methods.rules import rule_floor_3x3
        df = _floor_3x3_triggering_df()
        # current 종가가 지지 고점 이하 → 돌파 실패
        df.loc[df.index[-1], "close"] = 10_250.0  # < max support high 10300
        res = rule_floor_3x3().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_insufficient_warmup_returns_false(self):
        from strategies.books.daytrading_3methods.rules import rule_floor_3x3
        df = _make_df(np.full(8, 10_000.0))  # < 12
        res = rule_floor_3x3().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T3: rule_floor_2support (바닥 타법 — 상한가 후 2지지 → 재공략)
# ---------------------------------------------------------------------------

def _floor_2support_triggering_df():
    """직전 7봉 윈도우 내 강한 양봉(+20%↑) → 그 후 2봉 이상 지지(저점 유지·고점 미돌파) → 당일 양봉 재공략.

    need = lookback(7)+4 = 11봉.
      scan window = df.iloc[-8:-1]  (직전 7봉)
      current = df.iloc[-1]
    """
    warmup = np.full(4, 10_000.0)
    # scan 7봉: [spike(+20%), support1, support2, support3, ...]
    # spike: prev=10000 → close=12500 (+25% > +20%), high=12600
    spike = np.array([12_500.0])
    supports = np.array([12_300.0, 12_200.0, 12_400.0, 12_300.0, 12_350.0, 12_300.0])  # 6봉 지지
    current = np.array([12_600.0])
    close = np.concatenate([warmup, spike, supports, current])
    assert len(close) == 12  # 4 + 1 + 6 + 1
    vol = np.concatenate([
        np.full(11, 1_000.0),
        np.array([1_500.0]),   # current 거래량 (직전 5봉 평균 1000 * 1.2 = 1200 이상)
    ])
    df = _make_df(close, volume=vol)
    # spike 봉(인덱스 -8 = warmup4 다음): prev close=10000 대비 +25%, high=12600
    df.loc[df.index[-8], "close"] = 12_500.0
    df.loc[df.index[-8], "high"] = 12_600.0
    df.loc[df.index[-8], "low"] = 10_050.0
    df.loc[df.index[-8], "open"] = 10_100.0
    # support 봉들(-7..-2): low >= spike_close(12500)*(1-0.10)=11250, high <= spike_high(12600)
    for i in range(-7, -1):
        df.loc[df.index[i], "low"] = 11_500.0   # >= 11250 지지
        df.loc[df.index[i], "high"] = 12_550.0  # <= 12600 (조정, spike high 미돌파)
        df.loc[df.index[i], "open"] = 12_300.0
    # current: 양봉 + close > prev close(12300) + 거래량
    df.loc[df.index[-1], "open"] = 12_350.0
    df.loc[df.index[-1], "close"] = 12_600.0   # > prev close 12300, 양봉
    df.loc[df.index[-1], "high"] = 12_650.0
    df.loc[df.index[-1], "low"] = 12_340.0
    df.loc[df.index[-1], "volume"] = 1_500.0
    return df


class TestRuleFloor2Support:
    def test_triggers_on_spike_then_2support(self):
        from strategies.books.daytrading_3methods.rules import rule_floor_2support
        df = _floor_2support_triggering_df()
        res = rule_floor_2support().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.side == "buy"
        assert "spike_close" in res.metadata
        assert "n_supports" in res.metadata

    def test_fails_without_spike(self):
        from strategies.books.daytrading_3methods.rules import rule_floor_2support
        df = _floor_2support_triggering_df()
        # spike 봉(-8)의 등락률을 약화(+5%) → 강한 양봉 부재
        df.loc[df.index[-8], "close"] = 10_500.0  # prev 10000 대비 +5% < +20%
        df.loc[df.index[-8], "high"] = 10_550.0
        res = rule_floor_2support().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_fails_when_support_broken(self):
        from strategies.books.daytrading_3methods.rules import rule_floor_2support
        df = _floor_2support_triggering_df()
        # 모든 지지봉 저점을 무너뜨림 → 지지 유지 봉 부족
        for i in range(-7, -1):
            df.loc[df.index[i], "low"] = 10_000.0  # < spike_close*(1-0.10)=11250
        res = rule_floor_2support().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_insufficient_warmup_returns_false(self):
        from strategies.books.daytrading_3methods.rules import rule_floor_2support
        df = _make_df(np.full(8, 10_000.0))  # < 7+4
        res = rule_floor_2support().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T4: rule_breakout_prev_high (돌파 타법 — 전고점 거래량 동반 돌파)
# ---------------------------------------------------------------------------

def _breakout_prev_high_triggering_df():
    """종가가 직전 20봉 전고점 돌파 + 거래량 직전 20일 평균 × 2.0 + 양봉.

    need = high_window(20)+2 = 22봉.
      prior_high = max(df["high"].iloc[-21:-1])
      avg_vol = mean(df["volume"].iloc[-21:-1])
    """
    base = np.full(21, 10_000.0)
    df = _make_df(np.concatenate([base, np.array([10_400.0])]), volume=np.full(22, 1_000.0))
    # current: 직전 20봉 고가(~10050) 돌파, 거래량 3배, 양봉
    df.loc[df.index[-1], "open"] = 10_010.0
    df.loc[df.index[-1], "close"] = 10_400.0  # > prior_high ~10050
    df.loc[df.index[-1], "high"] = 10_450.0
    df.loc[df.index[-1], "low"] = 10_000.0
    df.loc[df.index[-1], "volume"] = 3_000.0   # >= avg(1000)*2.0
    return df


class TestRuleBreakoutPrevHigh:
    def test_triggers_on_prev_high_vol_breakout(self):
        from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high
        df = _breakout_prev_high_triggering_df()
        res = rule_breakout_prev_high().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.side == "buy"
        assert "prior_high" in res.metadata
        assert "vol_ratio" in res.metadata

    def test_fails_without_volume(self):
        from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high
        df = _breakout_prev_high_triggering_df()
        df.loc[df.index[-1], "volume"] = 1_100.0  # < avg*2.0
        res = rule_breakout_prev_high().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_fails_without_breakout(self):
        from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high
        df = _breakout_prev_high_triggering_df()
        df.loc[df.index[-1], "close"] = 10_020.0  # < prior_high ~10050
        df.loc[df.index[-1], "high"] = 10_030.0
        res = rule_breakout_prev_high().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_insufficient_warmup_returns_false(self):
        from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high
        df = _make_df(np.full(15, 10_000.0))  # < 22
        res = rule_breakout_prev_high().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T5: no-lookahead — t 시점 평가가 t+1 이후 봉 추가로 바뀌지 않음
# ---------------------------------------------------------------------------

class TestNoLookahead:
    def _assert_no_lookahead(self, rule, df):
        res_t = rule.evaluate(df, {"stock_code": "TEST"})
        # 미래 봉 5개 추가(임의 값) — t 시점 평가는 슬라이스 백 시 동일해야 함
        future = _make_df(np.full(5, 99_999.0), volume=np.full(5, 99_999.0))
        ext = pd.concat([df, future], ignore_index=True)
        res_back = rule.evaluate(ext.iloc[: len(df)], {"stock_code": "TEST"})
        assert res_t.triggered == res_back.triggered
        assert res_t.metadata == res_back.metadata

    def test_support_10candle_no_lookahead(self):
        from strategies.books.daytrading_3methods.rules import rule_support_10candle
        self._assert_no_lookahead(rule_support_10candle(), _support_10candle_triggering_df())

    def test_floor_3x3_no_lookahead(self):
        from strategies.books.daytrading_3methods.rules import rule_floor_3x3
        self._assert_no_lookahead(rule_floor_3x3(), _floor_3x3_triggering_df())

    def test_floor_2support_no_lookahead(self):
        from strategies.books.daytrading_3methods.rules import rule_floor_2support
        self._assert_no_lookahead(rule_floor_2support(), _floor_2support_triggering_df())

    def test_breakout_prev_high_no_lookahead(self):
        from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high
        self._assert_no_lookahead(rule_breakout_prev_high(), _breakout_prev_high_triggering_df())


# ---------------------------------------------------------------------------
# T6: ALL_RULES / build_strategy / BOOK_META 모듈레벨
# ---------------------------------------------------------------------------

def test_all_rules_export_has_4_rules():
    from strategies.books.daytrading_3methods.rules import ALL_RULES
    assert len(ALL_RULES) == 4
    names = [cls().name for cls in ALL_RULES]
    assert set(names) == {
        "support_10candle", "floor_3x3", "floor_2support", "breakout_prev_high",
    }


def test_build_strategy_single_mode():
    from strategies.books.daytrading_3methods.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="support_10candle")
    assert strat.name == "DayTrading3MethodsStrategy"
    assert strat.holding_period == "swing"
    assert strat.target_rule == "support_10candle"


def test_build_strategy_all_and_mode():
    from strategies.books.daytrading_3methods.strategy import build_strategy
    strat = build_strategy(mode="all_AND")
    assert strat.mode == "all_AND"
    assert len(strat.rules) == 4


def test_book_meta():
    from strategies.books.daytrading_3methods.strategy import BOOK_META
    assert BOOK_META["id"] == "daytrading_3methods"
    assert BOOK_META["data_granularity"] == "daily"
    assert BOOK_META["category"] == "swing"


def test_generate_signal_returns_signal():
    from strategies.books.daytrading_3methods.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="breakout_prev_high")
    df = _breakout_prev_high_triggering_df()
    sig = strat.generate_signal("TEST", df, "daily")
    assert sig is not None
    assert sig.signal_type.name in ("BUY", "STRONG_BUY")

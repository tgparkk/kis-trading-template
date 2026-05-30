"""강창권 단기 트레이딩의 정석 — 분봉 룰 단위 테스트."""
from __future__ import annotations

from datetime import time as dtime

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# 공통 헬퍼: 연속 분봉 생성 (09:00~15:30, 1분 간격, 다일 연결)
# ---------------------------------------------------------------------------

def _session_index(date: str, n: int) -> pd.DatetimeIndex:
    """date 09:00 부터 n개의 1분봉 타임스탬프."""
    start = pd.Timestamp(f"{date} 09:00:00")
    return pd.date_range(start, periods=n, freq="min")


def _make_df(datetimes, close, *, open_=None, high=None, low=None, volume=None):
    close = np.asarray(close, dtype=float)
    open_ = close.copy() if open_ is None else np.asarray(open_, dtype=float)
    high = (np.maximum(open_, close) * 1.001) if high is None else np.asarray(high, dtype=float)
    low = (np.minimum(open_, close) * 0.999) if low is None else np.asarray(low, dtype=float)
    volume = np.full(len(close), 1_000.0) if volume is None else np.asarray(volume, dtype=float)
    return pd.DataFrame({
        "datetime": pd.DatetimeIndex(datetimes),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


# ---------------------------------------------------------------------------
# T1: rule_ck480 — 시그니처
# ---------------------------------------------------------------------------

class TestRuleCk480:
    def _ck480_df(self):
        """직전일 종가 10000, 당일 장중 +16% 급등(고가 11600) 후 480분선까지 눌림 →
        점심시간(12:19) 480선 지지 양봉 진입.

        구조:
          - day1(전일): 300봉, 종가 10000 (480 warmup 일부, 기준종가)
          - day2(당일): 09:00부터 200봉. 시초가 직후 11600까지 급등(장중 고가)했다가
            480분선(~10666)까지 눌림. 직전 15봉이 480선 부근 횡보 후 마지막 양봉 반등.
        '당일 +15%' 는 장중 고가 기준(_day_high_return): (11600-10000)/10000 = +16%.
        """
        d1_dt = _session_index("2026-04-01", 300)
        d1_close = np.full(300, 10_000.0)
        # day2: 200봉. 09:00+199분 = 12:19 (점심시간). 대부분 480선 부근(10666) 위에서 횡보.
        d2_dt = _session_index("2026-04-02", 200)
        d2_close = np.full(200, 10_750.0)  # 480선 약간 위에서 횡보 (지지대)
        dt = list(d1_dt) + list(d2_dt)
        close = np.concatenate([d1_close, d2_close])
        df = _make_df(dt, close)
        # 당일 장중 고가: 시초가 직후 한 봉이 11600 (급등 흔적) — 그 외엔 횡보
        spike_idx = 300 + 5  # day2 6번째 봉
        df.loc[df.index[spike_idx], "high"] = 11_600.0
        df.loc[df.index[spike_idx], "close"] = 11_550.0
        df.loc[df.index[spike_idx], "open"] = 11_000.0

        ma480 = pd.Series(df["close"]).rolling(480).mean().iloc[-1]
        # 지지구간(직전 15봉): 저가가 480선 부근, 종가 480선 위 횡보
        for j in range(2, 17):
            df.loc[df.index[-j], "low"] = ma480 * 1.001
            df.loc[df.index[-j], "open"] = ma480 * 1.004
            df.loc[df.index[-j], "close"] = ma480 * 1.004
            df.loc[df.index[-j], "high"] = ma480 * 1.007
        # 마지막 봉: 480선 터치 후 양봉 재상승
        df.loc[df.index[-1], "low"] = ma480 * 1.002
        df.loc[df.index[-1], "open"] = ma480 * 1.003
        df.loc[df.index[-1], "close"] = ma480 * 1.012
        df.loc[df.index[-1], "high"] = ma480 * 1.015
        return df

    def test_triggers_on_surge_and_480_support_at_lunch(self):
        from strategies.books.haru_silijeon.rules import rule_ck480
        df = self._ck480_df()
        res = rule_ck480().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.side == "buy"
        assert "ma480" in res.metadata

    def test_fails_outside_lunch_window(self):
        from strategies.books.haru_silijeon.rules import rule_ck480
        df = self._ck480_df()
        # 마지막 봉 시각을 09:30 으로 바꿔 시간 필터 탈락
        df.loc[df.index[-1], "datetime"] = pd.Timestamp("2026-04-02 09:30:00")
        # 시간 순서 유지를 위해 마지막 직전도 조정
        res = rule_ck480().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_fails_when_day_return_below_15pct(self):
        from strategies.books.haru_silijeon.rules import rule_ck480
        df = self._ck480_df()
        # 당일 고가/종가를 전일 종가(10000) 근처로 → 장중 등락률 < 15%
        today = (df["datetime"].dt.date == pd.Timestamp("2026-04-02").date()).values
        df.loc[today, "high"] = 10_100.0
        df.loc[today, "close"] = 10_050.0
        df.loc[df.index[-1], "close"] = 10_060.0
        res = rule_ck480().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_fails_when_insufficient_bars(self):
        from strategies.books.haru_silijeon.rules import rule_ck480
        dt = _session_index("2026-04-02", 100)
        df = _make_df(dt, np.linspace(10_000, 11_500, 100))
        res = rule_ck480().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T2: rule_ma_5_10_pullback
# ---------------------------------------------------------------------------

class TestRuleMa510Pullback:
    def test_triggers_on_pullback_to_ma5(self):
        from strategies.books.haru_silijeon.rules import rule_ma_5_10_pullback
        dt = _session_index("2026-04-02", 40)
        # 상승 추세 후 마지막 봉이 ma5 부근 눌림 양봉
        close = np.linspace(10_000, 10_400, 39).tolist()
        close.append(10_410.0)
        df = _make_df(dt, close)
        ma5 = pd.Series(df["close"]).rolling(5).mean().iloc[-1]
        df.loc[df.index[-1], "low"] = ma5 * 1.0  # 저가가 ma5 터치
        df.loc[df.index[-1], "open"] = ma5 * 0.999
        df.loc[df.index[-1], "close"] = ma5 * 1.004
        res = rule_ma_5_10_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.side == "buy"

    def test_fails_on_no_trend(self):
        from strategies.books.haru_silijeon.rules import rule_ma_5_10_pullback
        dt = _session_index("2026-04-02", 40)
        df = _make_df(dt, np.full(40, 10_000.0))  # 평탄 = 추세 없음
        res = rule_ma_5_10_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T3: rule_ma20_pullback
# ---------------------------------------------------------------------------

class TestRuleMa20Pullback:
    def test_triggers_on_ma20_support_bounce(self):
        from strategies.books.haru_silijeon.rules import rule_ma20_pullback
        dt = _session_index("2026-04-02", 40)
        close = np.linspace(10_000, 10_300, 40)
        df = _make_df(dt, close)
        ma20 = pd.Series(df["close"]).rolling(20).mean().iloc[-1]
        df.loc[df.index[-1], "low"] = ma20  # ma20 터치
        df.loc[df.index[-1], "open"] = ma20 * 1.0005
        df.loc[df.index[-1], "close"] = ma20 * 1.004
        df.loc[df.index[-2], "close"] = ma20 * 1.002
        res = rule_ma20_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True

    def test_fails_when_below_ma20(self):
        from strategies.books.haru_silijeon.rules import rule_ma20_pullback
        dt = _session_index("2026-04-02", 40)
        close = np.linspace(10_300, 10_000, 40)  # 하락 → 종가 ma20 아래
        df = _make_df(dt, close)
        res = rule_ma20_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T4: rule_ma_240_480_support
# ---------------------------------------------------------------------------

class TestRuleMa240480Support:
    def test_triggers_on_480_support_with_volume(self):
        from strategies.books.haru_silijeon.rules import rule_ma_240_480_support
        # 500봉, 마지막 봉이 480선 위 + 480선 터치 + 거래량 회복 양봉
        dt = list(_session_index("2026-04-01", 390)) + list(_session_index("2026-04-02", 120))
        close = np.concatenate([
            np.full(390, 10_000.0),
            np.linspace(10_000, 10_500, 120),
        ])
        vol = np.full(510, 1_000.0)
        df = _make_df(dt, close, volume=vol)
        ma480 = pd.Series(df["close"]).rolling(480).mean().iloc[-1]
        df.loc[df.index[-1], "low"] = ma480 * 1.002   # 480선 부근 터치
        df.loc[df.index[-1], "open"] = ma480 * 1.005
        df.loc[df.index[-1], "close"] = ma480 * 1.012  # 480선 위 양봉
        df.loc[df.index[-1], "high"] = ma480 * 1.015
        df.loc[df.index[-1], "volume"] = 5_000.0       # 거래량 회복
        res = rule_ma_240_480_support().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True

    def test_fails_below_480(self):
        from strategies.books.haru_silijeon.rules import rule_ma_240_480_support
        dt = list(_session_index("2026-04-01", 390)) + list(_session_index("2026-04-02", 120))
        close = np.concatenate([np.full(390, 10_000.0), np.linspace(10_000, 9_500, 120)])
        df = _make_df(dt, close)
        res = rule_ma_240_480_support().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T5: rule_prev_high_break
# ---------------------------------------------------------------------------

class TestRulePrevHighBreak:
    def test_triggers_on_break_with_volume(self):
        from strategies.books.haru_silijeon.rules import rule_prev_high_break
        # 전일 고가 10200, 당일 마지막 봉이 이를 돌파 + 거래량 급증 양봉
        d1 = _make_df(_session_index("2026-04-01", 60), np.full(60, 10_000.0))
        d1.loc[d1.index[30], "high"] = 10_200.0  # 전일 고가
        d2 = _make_df(_session_index("2026-04-02", 30), np.linspace(10_050, 10_150, 30),
                      volume=np.full(30, 1_000.0))
        df = pd.concat([d1, d2], ignore_index=True)
        df.loc[df.index[-2], "close"] = 10_150.0  # 전일 고가 아래
        df.loc[df.index[-1], "open"] = 10_180.0
        df.loc[df.index[-1], "close"] = 10_260.0  # 전일 고가 10200 돌파
        df.loc[df.index[-1], "volume"] = 5_000.0  # 거래량 급증
        res = rule_prev_high_break().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.metadata["prev_high"] == pytest.approx(10_200.0)

    def test_fails_without_prev_day(self):
        from strategies.books.haru_silijeon.rules import rule_prev_high_break
        df = _make_df(_session_index("2026-04-02", 30), np.linspace(10_000, 10_300, 30))
        res = rule_prev_high_break().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T6: rule_open_two_red_then_green
# ---------------------------------------------------------------------------

class TestRuleOpenTwoRedThenGreen:
    def test_triggers_on_two_red_then_strong_green(self):
        from strategies.books.haru_silijeon.rules import rule_open_two_red_then_green
        dt = _session_index("2026-04-02", 16)
        close = np.full(16, 10_000.0)
        open_ = np.full(16, 10_000.0)
        vol = np.full(16, 1_000.0)
        # 마지막 3봉: 음, 음, 강양봉
        open_[-3], close[-3] = 10_000.0, 9_960.0   # red
        open_[-2], close[-2] = 9_960.0, 9_930.0    # red
        open_[-1], close[-1] = 9_930.0, 9_990.0    # strong green (>0.3%)
        vol[-1] = 3_000.0                          # 거래량 급증
        df = _make_df(dt, close, open_=open_, volume=vol)
        res = rule_open_two_red_then_green().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True

    def test_fails_when_not_two_red(self):
        from strategies.books.haru_silijeon.rules import rule_open_two_red_then_green
        dt = _session_index("2026-04-02", 16)
        close = np.full(16, 10_000.0)
        open_ = np.full(16, 9_990.0)  # 전부 양봉
        df = _make_df(dt, close, open_=open_)
        res = rule_open_two_red_then_green().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# T7: ALL_RULES / build_strategy
# ---------------------------------------------------------------------------

def test_all_rules_export_has_6_minute_rules():
    from strategies.books.haru_silijeon import rules as rules_mod
    assert len(rules_mod.ALL_RULES) == 6
    names = [cls().name for cls in rules_mod.ALL_RULES]
    assert set(names) == {
        "ck480", "ma_5_10_pullback", "ma20_pullback",
        "ma_240_480_support", "prev_high_break", "open_two_red_then_green",
    }


def test_build_strategy_single_mode():
    from strategies.books.haru_silijeon.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="ck480")
    assert strat.name == "HaruSilijeonStrategy"
    assert strat.holding_period == "intraday"
    assert strat.target_rule == "ck480"


def test_build_strategy_all_and_mode():
    from strategies.books.haru_silijeon.strategy import build_strategy
    strat = build_strategy(mode="all_AND")
    assert strat.mode == "all_AND"
    assert len(strat.rules) == 6


def test_book_meta_id():
    from strategies.books.haru_silijeon.strategy import BOOK_META
    assert BOOK_META["id"] == "haru_silijeon"
    assert BOOK_META["data_granularity"] == "minute"


def test_generate_signal_returns_signal_on_ck480():
    from strategies.books.haru_silijeon.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="ck480")
    df = TestRuleCk480()._ck480_df()
    sig = strat.generate_signal("TEST", df, "intraday")
    assert sig is not None
    assert sig.signal_type.name in ("BUY", "STRONG_BUY")

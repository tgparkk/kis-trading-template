"""디노(백새봄) 급등주 투자법 — 일봉 룰 단위 테스트.

룰 함수 단위테스트 + no-lookahead 가드 + 진입/청산 경계값.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# 공통 헬퍼: 일봉 OHLCV 생성
# ---------------------------------------------------------------------------

def _make_df(close, *, open_=None, high=None, low=None, volume=None):
    close = np.asarray(close, dtype=float)
    n = len(close)
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    open_ = close.copy() if open_ is None else np.asarray(open_, dtype=float)
    high = (np.maximum(open_, close) * 1.005) if high is None else np.asarray(high, dtype=float)
    low = (np.minimum(open_, close) * 0.995) if low is None else np.asarray(low, dtype=float)
    volume = np.full(n, 1_000.0) if volume is None else np.asarray(volume, dtype=float)
    return pd.DataFrame({
        "datetime": dates,
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


def _surge_then_pullback(drawdown=0.30, n_warm=130):
    """급등 후 고점대비 -drawdown 만큼 눌린 시계열 (OBV 우상향 유지용 거래량 패턴 포함).

    high_lookback=120 안에 고점이 들어오도록 배치. 종가가 고점대비 -drawdown.
    OBV 우상향: 전반 상승(거래량 큼) → 후반 완만 하락(거래량 작음) → 누적 OBV 우상향 유지.
    """
    peak = 20_000.0
    bottom = peak * (1.0 - drawdown)
    base = np.concatenate([
        np.full(10, 10_000.0),                  # 초반
        np.linspace(10_000, peak, 70),          # 급등 (고점 형성)
        np.linspace(peak, bottom, 42),          # 눌림 (얕은 하락)
        np.full(8, bottom),                     # 바닥 횡보 (OBV 미이탈 = 매물 출회 멈춤)
    ])
    # OBV 미이탈: 급등구간 대량 매집 → 눌림 소량 → 바닥 횡보(거래량 거의 0, OBV 평탄)
    vol = np.concatenate([
        np.full(10, 1_000.0),
        np.full(70, 5_000.0),                   # 급등 = 대량 매집
        np.full(42, 500.0),                     # 눌림 = 소량 (OBV 차감 적음)
        np.full(8, 50.0),                        # 바닥 횡보 = 거래 고갈 (OBV 평탄 → 미이탈)
    ])
    return _make_df(base, volume=vol)


# ---------------------------------------------------------------------------
# 지표 헬퍼 테스트
# ---------------------------------------------------------------------------

class TestIndicators:
    def test_obv_rising_on_accumulation(self):
        from strategies.books.dino_surge.rules import obv_rising
        df = _surge_then_pullback()
        # 매집 구간 포괄 lookback(기본 60) → 눌림에도 OBV 미이탈 = True
        assert obv_rising(df["close"], df["volume"]) is True

    def test_obv_not_rising_on_distribution(self):
        from strategies.books.dino_surge.rules import obv_rising
        # 지속 하락 + 하락구간 대량거래 → OBV 우하향(레벨 이탈) = False
        base = np.linspace(20_000, 12_000, 150)
        vol = np.full(150, 3_000.0)
        df = _make_df(base, volume=vol)
        assert obv_rising(df["close"], df["volume"]) is False

    def test_rsi_bounds(self):
        from strategies.books.dino_surge.rules import rsi
        up = _make_df(np.linspace(10_000, 20_000, 60))
        down = _make_df(np.linspace(20_000, 10_000, 60))
        assert float(rsi(up["close"], 14).iloc[-1]) > 60.0
        assert float(rsi(down["close"], 14).iloc[-1]) < 40.0

    def test_drawdown_from_high(self):
        from strategies.books.dino_surge.rules import _drawdown_from_high
        df = _surge_then_pullback(drawdown=0.30)
        dd = _drawdown_from_high(df, 120)
        assert dd is not None
        assert -0.40 <= dd <= -0.20  # 고점대비 약 -30%

    def test_hammer_detection(self):
        from strategies.books.dino_surge.rules import _is_hammer
        # 아래꼬리 긴 양봉: open=100, close=101, low=90, high=101.5
        bar = {"open": 100.0, "close": 101.0, "low": 90.0, "high": 101.5}
        assert _is_hammer(bar) is True
        # 위꼬리 큰 봉 → 아님
        bar2 = {"open": 100.0, "close": 101.0, "low": 99.5, "high": 110.0}
        assert _is_hammer(bar2) is False


# ---------------------------------------------------------------------------
# Variant A: rule_dino_test_pullback
# ---------------------------------------------------------------------------

class TestRuleDinoTestPullback:
    def _triggering_df(self):
        """디노테스트 진입 조건 충족 df (마지막 봉 = 바닥반전 장대양봉, RSI 침체)."""
        df = _surge_then_pullback(drawdown=0.30)
        # 마지막 봉을 장대양봉(바닥반전)으로 override — RSI는 직전 하락으로 침체 유지
        prev_close = float(df["close"].iloc[-2])
        df.loc[df.index[-1], "open"] = prev_close * 0.995
        df.loc[df.index[-1], "close"] = prev_close * 1.04   # +4% 장대양봉
        df.loc[df.index[-1], "high"] = prev_close * 1.045
        df.loc[df.index[-1], "low"] = prev_close * 0.99
        return df

    def test_triggers_with_no_fin_gate(self):
        from strategies.books.dino_surge.rules import rule_dino_test_pullback
        df = self._triggering_df()
        # dino_fin 미주입 → 재무축 중립(통과)
        res = rule_dino_test_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.side == "buy"
        assert "drawdown" in res.metadata

    def test_fin_hard_fail_blocks(self):
        from strategies.books.dino_surge.rules import rule_dino_test_pullback
        df = self._triggering_df()
        ctx = {"dino_fin": {"hard_pass": False, "fin_score": 5.0, "min_fin_score": 3.0}}
        res = rule_dino_test_pullback().evaluate(df, ctx)
        assert res.triggered is False  # 좀비 하드필터 탈락

    def test_fin_score_below_cutoff_blocks(self):
        from strategies.books.dino_surge.rules import rule_dino_test_pullback
        df = self._triggering_df()
        ctx = {"dino_fin": {"hard_pass": True, "fin_score": 1.0, "min_fin_score": 3.0}}
        res = rule_dino_test_pullback().evaluate(df, ctx)
        assert res.triggered is False  # 재무점수 컷오프 미달

    def test_fin_score_pass(self):
        from strategies.books.dino_surge.rules import rule_dino_test_pullback
        df = self._triggering_df()
        ctx = {"dino_fin": {"hard_pass": True, "fin_score": 4.0, "min_fin_score": 3.0}}
        res = rule_dino_test_pullback().evaluate(df, ctx)
        assert res.triggered is True

    def test_no_pullback_blocks(self):
        from strategies.books.dino_surge.rules import rule_dino_test_pullback
        # 신고가 부근(눌림 없음) → drawdown 거의 0 → 탈락
        df = _make_df(np.linspace(10_000, 20_000, 150),
                      volume=np.concatenate([np.full(75, 5_000.0), np.full(75, 5_000.0)]))
        res = rule_dino_test_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_high_rsi_blocks(self):
        from strategies.books.dino_surge.rules import rule_dino_test_pullback
        df = self._triggering_df()
        # rsi_max 를 0으로 강제 → RSI 어떤 값이든 초과 → 탈락 (RSI 게이트 경계 검증)
        res = rule_dino_test_pullback(rsi_max=0.0).evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_non_reversal_bar_blocks(self):
        from strategies.books.dino_surge.rules import rule_dino_test_pullback
        df = self._triggering_df()
        # 마지막 봉을 음봉으로 → 바닥반전 봉 아님
        prev_close = float(df["close"].iloc[-2])
        df.loc[df.index[-1], "open"] = prev_close * 1.01
        df.loc[df.index[-1], "close"] = prev_close * 0.97
        df.loc[df.index[-1], "high"] = prev_close * 1.012
        df.loc[df.index[-1], "low"] = prev_close * 0.965
        res = rule_dino_test_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_insufficient_warmup_returns_false(self):
        from strategies.books.dino_surge.rules import rule_dino_test_pullback
        df = _make_df(np.full(30, 10_000.0))  # high_lookback=120 미만
        res = rule_dino_test_pullback().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# Variant B: rule_pullback_rebound
# ---------------------------------------------------------------------------

class TestRulePullbackRebound:
    def _triggering_df(self):
        """눌림 + RSI 저점 반등 + 장대양봉 + 거래량 증가."""
        df = _surge_then_pullback(drawdown=0.30)
        # 직전 봉은 추가 하락(RSI 저점 만들기), 마지막 봉은 강한 반등 양봉
        c2 = float(df["close"].iloc[-3])
        df.loc[df.index[-2], "close"] = c2 * 0.97   # 추가 하락 → RSI 저점
        df.loc[df.index[-2], "open"] = c2 * 0.99
        df.loc[df.index[-2], "high"] = c2 * 0.995
        df.loc[df.index[-2], "low"] = c2 * 0.965
        prev_close = float(df["close"].iloc[-2])
        df.loc[df.index[-1], "open"] = prev_close * 0.998
        df.loc[df.index[-1], "close"] = prev_close * 1.04   # +4% 반등 → RSI 상향전환
        df.loc[df.index[-1], "high"] = prev_close * 1.045
        df.loc[df.index[-1], "low"] = prev_close * 0.99
        df.loc[df.index[-1], "volume"] = 2_000.0            # 직전평균(500) 대비 증가
        return df

    def test_triggers_on_rebound(self):
        from strategies.books.dino_surge.rules import rule_pullback_rebound
        df = self._triggering_df()
        res = rule_pullback_rebound().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is True
        assert res.side == "buy"

    def test_no_volume_increase_blocks(self):
        from strategies.books.dino_surge.rules import rule_pullback_rebound
        df = self._triggering_df()
        df.loc[df.index[-1], "volume"] = 100.0  # 거래량 급감 → 탈락
        res = rule_pullback_rebound().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_rsi_falling_blocks(self):
        from strategies.books.dino_surge.rules import rule_pullback_rebound
        df = self._triggering_df()
        # 마지막 봉을 음봉으로 → RSI 상향전환 실패 + 장대양봉 아님
        prev_close = float(df["close"].iloc[-2])
        df.loc[df.index[-1], "open"] = prev_close * 1.0
        df.loc[df.index[-1], "close"] = prev_close * 0.96
        res = rule_pullback_rebound().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False

    def test_small_body_blocks(self):
        from strategies.books.dino_surge.rules import rule_pullback_rebound
        df = self._triggering_df()
        # 몸통 작은 양봉(+0.5%) → 장대양봉 아님
        prev_close = float(df["close"].iloc[-2])
        df.loc[df.index[-1], "open"] = prev_close * 1.0
        df.loc[df.index[-1], "close"] = prev_close * 1.005
        df.loc[df.index[-1], "high"] = prev_close * 1.007
        df.loc[df.index[-1], "low"] = prev_close * 0.999
        res = rule_pullback_rebound().evaluate(df, {"stock_code": "TEST"})
        assert res.triggered is False


# ---------------------------------------------------------------------------
# no-lookahead 가드
# ---------------------------------------------------------------------------

class TestNoLookahead:
    def test_rule_only_uses_window_up_to_t(self):
        """df 마지막 행 이후 데이터를 변경해도 evaluate 결과는 동일해야 한다.

        룰은 df(=윈도우, 과거~t)만 받으므로, 미래 봉을 append 한 전체 df 와
        그 미래봉을 제거한 df 의 마지막 시점 평가가 동일함을 확인.
        실제 런타임은 df.iloc[:i+1] 슬라이스를 넘기므로, 슬라이스 결과 == 전체 결과[해당 t].
        """
        from strategies.books.dino_surge.rules import rule_dino_test_pullback
        df_full = TestRuleDinoTestPullback()._triggering_df()
        res_t = rule_dino_test_pullback().evaluate(df_full, {"stock_code": "TEST"})

        # 미래봉 2개 추가 (급락) → t 시점 슬라이스는 동일해야
        future = df_full.copy()
        extra = df_full.iloc[[-1, -1]].copy()
        extra["close"] = [5_000.0, 4_000.0]
        future = pd.concat([future, extra], ignore_index=True)
        # t 시점(원래 마지막)까지만 슬라이스
        window_t = future.iloc[: len(df_full)]
        res_slice = rule_dino_test_pullback().evaluate(window_t, {"stock_code": "TEST"})

        assert res_t.triggered == res_slice.triggered
        assert res_t.metadata.get("drawdown") == pytest.approx(res_slice.metadata.get("drawdown"))


# ---------------------------------------------------------------------------
# 전략/메타 빌드
# ---------------------------------------------------------------------------

def test_all_rules_export_has_2_rules():
    from strategies.books.dino_surge import rules as rd
    assert len(rd.ALL_RULES) == 2
    names = [cls().name for cls in rd.ALL_RULES]
    assert set(names) == {"dino_test_pullback", "pullback_rebound"}


def test_build_strategy_single_mode():
    from strategies.books.dino_surge.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="dino_test_pullback")
    assert strat.name == "DinoSurgeStrategy"
    assert strat.holding_period == "swing"
    assert strat.target_rule == "dino_test_pullback"


def test_build_strategy_all_and_mode():
    from strategies.books.dino_surge.strategy import build_strategy
    strat = build_strategy(mode="all_AND")
    assert strat.mode == "all_AND"
    assert len(strat.rules) == 2


def test_book_meta():
    from strategies.books.dino_surge.strategy import BOOK_META
    assert BOOK_META["id"] == "dino_surge"
    assert BOOK_META["data_granularity"] == "daily"


def test_generate_signal_returns_signal():
    from strategies.books.dino_surge.strategy import build_strategy
    strat = build_strategy(mode="single", target_rule="dino_test_pullback")
    df = TestRuleDinoTestPullback()._triggering_df()
    sig = strat.generate_signal("TEST", df, "daily")
    assert sig is not None
    assert sig.signal_type.name in ("BUY", "STRONG_BUY")


# ---------------------------------------------------------------------------
# run 스크립트 청산 파라미터 (+10% 무조건 익절)
# ---------------------------------------------------------------------------

class TestVariantParams:
    def test_variant_a_tp_is_10pct_with_ma5_trail(self):
        from scripts.run_dino_surge import VARIANT_PARAMS
        a = VARIANT_PARAMS["A"]
        assert a["take_profit_pct"] == pytest.approx(0.10)
        assert a["stop_loss_pct"] == pytest.approx(0.07)
        assert a["trail_ma"] == 5

    def test_variant_b_tp_is_10pct_tight_sl(self):
        from scripts.run_dino_surge import VARIANT_PARAMS
        b = VARIANT_PARAMS["B"]
        assert b["take_profit_pct"] == pytest.approx(0.10)
        assert b["stop_loss_pct"] == pytest.approx(0.05)
        assert b["trail_ma"] is None


class TestVariantCTrendExit:
    """variant C — 디노 진입(pullback_rebound) + Elder식 추세청산.

    진입은 B와 동일(건드리지 않음). 청산만 EMA13 트레일 + EMA65 trend_flip +
    초기손절 8% + mh 100 + 고정익절 tp=0.30(사실상 추세에 맡김).
    """

    def test_variant_c_params_trend_exit(self):
        from scripts.run_dino_surge import VARIANT_PARAMS
        c = VARIANT_PARAMS["C"]
        assert c["exit_mode"] == "trend"
        assert c["stop_loss_pct"] == pytest.approx(0.08)
        assert c["take_profit_pct"] == pytest.approx(0.30)  # 사실상 추세에 맡김
        assert c["max_hold_bars"] == 100
        assert c["trail_ma"] is None
        assert c["trail_ema"] == 13
        assert c["trend_ema"] == 65

    def test_variant_c_keeps_AB_intact(self):
        """A/B 회귀 보호 — 기존 청산 파라미터 불변."""
        from scripts.run_dino_surge import VARIANT_PARAMS
        a, b = VARIANT_PARAMS["A"], VARIANT_PARAMS["B"]
        assert a["take_profit_pct"] == pytest.approx(0.10) and a["trail_ma"] == 5
        assert b["take_profit_pct"] == pytest.approx(0.10) and b["trail_ma"] is None
        assert "exit_mode" not in a and "exit_mode" not in b  # A/B 는 fixed 분기

    def test_ema_helper_matches_ewm(self):
        from scripts.run_dino_surge import _ema
        s = pd.Series(np.linspace(100.0, 200.0, 80))
        got = _ema(s, 13)
        exp = s.ewm(span=13, adjust=False).mean()
        assert float(got.iloc[-1]) == pytest.approx(float(exp.iloc[-1]))

    def _uptrend_then_break(self):
        """진입 후 상승 지속하다 EMA65 하향이탈로 추세반전(trend_flip) 트리거되는 시계열.

        warmup 이후 신호 발생을 강제하지 않고 청산 분기만 검증하므로,
        simulate_one_stock 에 강한 추세→붕괴 패턴을 넣어 trend 청산이 fixed 와
        다른 시점/사유로 작동함을 본다.
        """
        base = np.concatenate([
            np.linspace(10_000, 9_000, 30),     # 초반 눌림
            np.linspace(9_000, 14_000, 60),     # 강한 상승 추세 (EMA65 우상향)
            np.linspace(14_000, 8_000, 40),     # 추세붕괴 (EMA65 하향이탈)
        ])
        return _make_df(base)

    def test_trend_exit_produces_trades_with_trend_reasons(self):
        """variant C 시뮬: 청산 사유에 추세청산(trend_flip/ema_trail/max_hold)이 포함."""
        from scripts.run_dino_surge import simulate_one_stock, VARIANT_PARAMS
        from strategies.books.dino_surge.strategy import build_strategy

        df = self._uptrend_then_break()
        # 항상 매수 신호를 내는 더미 전략으로 청산 로직만 격리 검증
        class _AlwaysBuy:
            def generate_signal_with_extra_ctx(self, code, window, tf, extra):
                from strategies.base import Signal, SignalType
                return Signal(signal_type=SignalType.BUY, stock_code=code,
                              confidence=70, reasons=["test_entry"])

        c = VARIANT_PARAMS["C"]
        res = simulate_one_stock(
            code="TEST", df=df, fin_by_idx=[None] * len(df), strategy=_AlwaysBuy(),
            stop_loss_pct=c["stop_loss_pct"], take_profit_pct=c["take_profit_pct"],
            max_hold_bars=c["max_hold_bars"], trail_ma=c["trail_ma"],
            exit_mode=c["exit_mode"], trail_ema=c["trail_ema"], trend_ema=c["trend_ema"],
        )
        assert res["n_trades"] >= 1
        reasons = {t["reason"] for t in res["trades"] if t["side"] == "sell"}
        trend_reasons = {"trend_flip", "ema_trail", "max_hold", "stop_loss",
                         "take_profit", "forced_close"}
        assert reasons.issubset(trend_reasons)
        # 추세청산 모드에서는 적어도 한 번은 trend_flip 또는 ema_trail 로 빠져야 함
        assert reasons & {"trend_flip", "ema_trail"}

    def test_trend_exit_no_lookahead_in_ema(self):
        """EMA(i) 값은 i 이후 데이터에 불변 (ewm 누적 특성) — no-lookahead 가드."""
        from scripts.run_dino_surge import _ema
        s_full = pd.Series(self._uptrend_then_break()["close"].values)
        idx = 80
        e_full = _ema(s_full, 13).iloc[idx]
        e_trunc = _ema(s_full.iloc[: idx + 1], 13).iloc[idx]
        assert float(e_full) == pytest.approx(float(e_trunc))


class TestDinoFinScore:
    def test_zombie_hard_fail(self):
        from scripts.run_dino_surge import _dino_fin_score
        curr = {"revenue": 100.0, "operating_profit": -10.0, "operating_margin": -5.0,
                "debt_ratio": 250.0, "roe": -3.0}
        out = _dino_fin_score(curr, None, 3.0)
        assert out["hard_pass"] is False

    def test_healthy_high_score(self):
        from scripts.run_dino_surge import _dino_fin_score
        prev = {"revenue": 100.0}
        curr = {"revenue": 120.0, "operating_profit": 30.0, "operating_margin": 25.0,
                "debt_ratio": 30.0, "roe": 15.0}
        out = _dino_fin_score(curr, prev, 3.0)
        # 매출+20%(+1), opm25%(+1), 흑자(+1), roe>0(+1), 부채<50(감점없음) = 4
        assert out["fin_score"] == pytest.approx(4.0)
        assert out["hard_pass"] is True

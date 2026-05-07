"""trend_starter v2 ExitRule + Sizer 단위 테스트.

ATR 기반 SL/TP, 트레일링 스톱, 시간 청산, _TSSizer 다양한 주가 시나리오를 검증.
DB 의존성 없음 — MagicMock으로 PITContext.read_daily를 대체.
"""
from __future__ import annotations

import math
from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.personas.trend_starter import (
    _TSExitRule,
    _TSHoldingCap,
    _TSSizer,
    _resolve_atr_at_entry,
)


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _make_ohlcv_df(n: int = 20, close: float = 50_000) -> pd.DataFrame:
    """OHLCV 일봉 DataFrame 생성 (ATR 산출 가능한 최소 15행 보장).

    close 고정, high=close*1.03, low=close*0.97 — atr_ratio ≈ 0.06.
    """
    closes = [close] * n
    highs = [c * 1.03 for c in closes]
    lows = [c * 0.97 for c in closes]
    opens = closes
    volumes = [1_000_000] * n
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="B"),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def _mock_ctx(df: pd.DataFrame | None = None) -> MagicMock:
    """read_daily 를 df 반환하도록 mock."""
    ctx = MagicMock()
    ctx.as_of_date = date(2024, 6, 1)
    if df is None:
        df = _make_ohlcv_df()
    ctx.read_daily.return_value = df
    return ctx


def _base_paramset(**overrides) -> ParamSet:
    """테스트용 최소 유효 ParamSet. W 섹션 기본값 사용."""
    from dataclasses import replace
    from RoboTrader_template.multiverse.composable.personas._grid import _BASELINE
    ps = replace(
        _BASELINE,
        max_positions=3,
        max_weight_per_stock=0.20,
        ts_atr_min=0.06,
        ts_volz_min=1.5,
        ts_box_min=0.20,
        ts_sl_atr_mult=1.5,
        ts_tp_atr_mult=3.0,
        ts_trail_trigger_atr=0.0,
        ts_trail_offset_atr=0.5,
        ts_hold_days=5,
        ts_target_pct=0.15,
        ts_stop_pct=-0.08,
    )
    if overrides:
        ps = replace(ps, **overrides)
    ps.validate()
    return ps


def _position(
    entry_price: float = 50_000,
    current_price: float | None = None,
    atr_at_entry: float | None = None,
    trailing_high: float = 0.0,
    held_days: int = 1,
    symbol: str = "005930",
) -> dict:
    return {
        "symbol": symbol,
        "entry_price": entry_price,
        "current_price": current_price if current_price is not None else entry_price,
        "atr_at_entry": atr_at_entry,
        "trailing_high": trailing_high,
        "held_days": held_days,
        "qty": 10,
        "entry_date": date(2024, 5, 1),
        "lock_step": 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_atr_at_entry 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveAtrAtEntry:

    def test_returns_stored_value_when_present(self):
        """pos_dict에 atr_at_entry > 0 이면 ctx 호출 없이 그대로 반환."""
        ctx = MagicMock()
        pos = _position(atr_at_entry=3_000.0)
        result = _resolve_atr_at_entry(pos, ctx)
        assert result == 3_000.0
        ctx.read_daily.assert_not_called()

    def test_computes_from_ctx_when_stored_is_none(self):
        """atr_at_entry=None 이면 ctx.read_daily로 산출."""
        df = _make_ohlcv_df(n=20, close=50_000)
        ctx = _mock_ctx(df)
        pos = _position(atr_at_entry=None)
        result = _resolve_atr_at_entry(pos, ctx)
        # atr_ratio ≈ 0.06 (ATR ~3000원) — 양수여야 함
        assert result is not None
        assert result > 0

    def test_returns_none_for_empty_df(self):
        """빈 DataFrame 이면 None 반환."""
        ctx = _mock_ctx(pd.DataFrame())
        pos = _position(atr_at_entry=None)
        result = _resolve_atr_at_entry(pos, ctx)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# _TSExitRule 테스트 — ATR SL 발동
# ─────────────────────────────────────────────────────────────────────────────

class TestTSExitRuleAtrSL:

    def test_atr_sl_triggers_when_price_drops_below_sl(self):
        """current_price <= entry - atr * sl_mult 이면 'atr_stop_loss' 반환."""
        entry = 50_000.0
        atr = 3_000.0  # sl_mult=1.5 → sl_price = 50000 - 4500 = 45500
        current = 45_000.0  # sl 아래
        ps = _base_paramset(ts_sl_atr_mult=1.5, ts_tp_atr_mult=3.0)
        pos = _position(entry_price=entry, current_price=current, atr_at_entry=atr)
        ctx = _mock_ctx()

        rule = _TSExitRule()
        exit_flag, reason = rule.should_exit(ctx, pos, ps)

        assert exit_flag is True
        assert reason == "atr_stop_loss"

    def test_atr_sl_no_trigger_when_price_above_sl(self):
        """current_price > sl_price 이면 청산 안 함."""
        entry = 50_000.0
        atr = 3_000.0  # sl_price = 45500
        current = 48_000.0  # sl 위
        ps = _base_paramset(ts_sl_atr_mult=1.5, ts_tp_atr_mult=3.0)
        pos = _position(entry_price=entry, current_price=current, atr_at_entry=atr)
        ctx = _mock_ctx()

        rule = _TSExitRule()
        exit_flag, reason = rule.should_exit(ctx, pos, ps)

        assert exit_flag is False


# ─────────────────────────────────────────────────────────────────────────────
# _TSExitRule 테스트 — ATR TP 발동
# ─────────────────────────────────────────────────────────────────────────────

class TestTSExitRuleAtrTP:

    def test_atr_tp_triggers_when_price_above_tp(self):
        """current_price >= entry + atr * tp_mult 이면 'atr_take_profit' 반환."""
        entry = 50_000.0
        atr = 3_000.0  # tp_mult=3.0 → tp_price = 50000 + 9000 = 59000
        current = 60_000.0  # tp 위
        ps = _base_paramset(ts_sl_atr_mult=1.5, ts_tp_atr_mult=3.0)
        pos = _position(entry_price=entry, current_price=current, atr_at_entry=atr)
        ctx = _mock_ctx()

        rule = _TSExitRule()
        exit_flag, reason = rule.should_exit(ctx, pos, ps)

        assert exit_flag is True
        assert reason == "atr_take_profit"

    def test_atr_tp_no_trigger_when_price_below_tp(self):
        """current_price < tp_price 이면 청산 안 함."""
        entry = 50_000.0
        atr = 3_000.0  # tp_price = 59000
        current = 55_000.0
        ps = _base_paramset(ts_sl_atr_mult=1.5, ts_tp_atr_mult=3.0)
        pos = _position(entry_price=entry, current_price=current, atr_at_entry=atr)
        ctx = _mock_ctx()

        rule = _TSExitRule()
        exit_flag, reason = rule.should_exit(ctx, pos, ps)

        assert exit_flag is False


# ─────────────────────────────────────────────────────────────────────────────
# _TSExitRule 테스트 — 트레일링 스톱 발동
# ─────────────────────────────────────────────────────────────────────────────

class TestTSExitRuleTrailingStop:

    def test_trailing_stop_triggers_after_trigger_reached(self):
        """트리거 도달 후 trailing_high 하회 시 'trailing_stop' 반환.

        entry=50000, atr=3000, trigger_atr=1.5 → trigger_price=54500
        offset_atr=0.5 → trail_stop = trailing_high - 1500
        trailing_high=58000 → trail_stop=56500
        current=56000 < 56500 → 청산
        """
        entry = 50_000.0
        atr = 3_000.0
        trailing_high = 58_000.0
        current = 56_000.0  # trailing_high - offset*atr = 58000 - 1500 = 56500 이하
        ps = _base_paramset(
            ts_sl_atr_mult=1.5,
            ts_tp_atr_mult=3.0,
            ts_trail_trigger_atr=1.5,  # trigger_price = 50000 + 4500 = 54500
            ts_trail_offset_atr=0.5,   # trail_stop = trailing_high - 1500
        )
        pos = _position(
            entry_price=entry,
            current_price=current,
            atr_at_entry=atr,
            trailing_high=trailing_high,
        )
        ctx = _mock_ctx()

        rule = _TSExitRule()
        exit_flag, reason = rule.should_exit(ctx, pos, ps)

        assert exit_flag is True
        assert reason == "trailing_stop"

    def test_trailing_stop_no_trigger_before_trigger_price_reached(self):
        """current_price < trigger_price 이면 트레일링 발동 안 함."""
        entry = 50_000.0
        atr = 3_000.0
        # trigger_price = 50000 + 1.5*3000 = 54500
        current = 52_000.0  # trigger_price 미달
        trailing_high = 52_000.0
        ps = _base_paramset(
            ts_sl_atr_mult=1.5,
            ts_tp_atr_mult=3.0,
            ts_trail_trigger_atr=1.5,
            ts_trail_offset_atr=0.5,
        )
        pos = _position(
            entry_price=entry,
            current_price=current,
            atr_at_entry=atr,
            trailing_high=trailing_high,
        )
        ctx = _mock_ctx()

        rule = _TSExitRule()
        exit_flag, reason = rule.should_exit(ctx, pos, ps)

        assert exit_flag is False

    def test_trailing_stop_disabled_when_trigger_atr_zero(self):
        """ts_trail_trigger_atr=0 이면 트레일링 스톱 비활성."""
        entry = 50_000.0
        atr = 3_000.0
        trailing_high = 60_000.0
        current = 55_000.0  # 트레일링이라면 청산될 값
        ps = _base_paramset(
            ts_sl_atr_mult=1.5,
            ts_tp_atr_mult=3.0,
            ts_trail_trigger_atr=0.0,  # 비활성
            ts_trail_offset_atr=0.5,
        )
        pos = _position(
            entry_price=entry,
            current_price=current,
            atr_at_entry=atr,
            trailing_high=trailing_high,
        )
        ctx = _mock_ctx()

        rule = _TSExitRule()
        exit_flag, reason = rule.should_exit(ctx, pos, ps)

        assert exit_flag is False

    def test_trailing_stop_no_trigger_when_trailing_high_zero(self):
        """trailing_high=0 이면 트레일링 청산 발동 안 함 (아직 고점 기록 없음)."""
        entry = 50_000.0
        atr = 3_000.0
        current = 55_000.0  # trigger_price(54500) 초과
        trailing_high = 0.0  # 고점 미기록
        ps = _base_paramset(
            ts_sl_atr_mult=1.5,
            ts_tp_atr_mult=3.0,
            ts_trail_trigger_atr=1.5,
            ts_trail_offset_atr=0.5,
        )
        pos = _position(
            entry_price=entry,
            current_price=current,
            atr_at_entry=atr,
            trailing_high=trailing_high,
        )
        ctx = _mock_ctx()

        rule = _TSExitRule()
        exit_flag, reason = rule.should_exit(ctx, pos, ps)

        assert exit_flag is False


# ─────────────────────────────────────────────────────────────────────────────
# _TSExitRule 테스트 — ATR 폴백 (atr_at_entry=None, ctx 빈 DataFrame)
# ─────────────────────────────────────────────────────────────────────────────

class TestTSExitRuleFallback:

    def test_fallback_to_fixed_pct_on_no_atr(self):
        """atr_at_entry=None & ctx 빈 DataFrame → 고정 비율 폴백."""
        entry = 50_000.0
        # ts_stop_pct=-0.08 → 손절 = 50000 * (1 - 0.08) = 46000
        current = 45_000.0  # 손절 아래
        ps = _base_paramset()
        pos = _position(entry_price=entry, current_price=current, atr_at_entry=None)
        ctx = _mock_ctx(pd.DataFrame())  # 빈 DataFrame → atr 산출 불가

        rule = _TSExitRule()
        exit_flag, reason = rule.should_exit(ctx, pos, ps)

        assert exit_flag is True
        assert reason == "stop_loss"

    def test_fallback_tp_on_no_atr(self):
        """atr_at_entry=None & ctx 빈 DataFrame → ts_target_pct 폴백."""
        entry = 50_000.0
        # ts_target_pct=0.15 → 익절 = 57500
        current = 58_000.0
        ps = _base_paramset()
        pos = _position(entry_price=entry, current_price=current, atr_at_entry=None)
        ctx = _mock_ctx(pd.DataFrame())

        rule = _TSExitRule()
        exit_flag, reason = rule.should_exit(ctx, pos, ps)

        assert exit_flag is True
        assert reason == "take_profit"


# ─────────────────────────────────────────────────────────────────────────────
# _TSHoldingCap 테스트 — 시간 청산
# ─────────────────────────────────────────────────────────────────────────────

class TestTSHoldingCap:

    def test_force_exit_when_held_days_ge_hold_days(self):
        """held_days >= ts_hold_days → True."""
        ps = _base_paramset(ts_hold_days=3)
        cap = _TSHoldingCap()
        pos = _position(held_days=3)
        assert cap.should_force_exit_by_age(pos, date(2024, 6, 1), ps) is True

    def test_no_exit_when_held_days_lt_hold_days(self):
        """held_days < ts_hold_days → False."""
        ps = _base_paramset(ts_hold_days=3)
        cap = _TSHoldingCap()
        pos = _position(held_days=2)
        assert cap.should_force_exit_by_age(pos, date(2024, 6, 1), ps) is False


# ─────────────────────────────────────────────────────────────────────────────
# _TSSizer 테스트 — 다양한 주가 시나리오
# ─────────────────────────────────────────────────────────────────────────────

class TestTSSizer:

    def test_size_with_high_score_as_entry_price(self):
        """score >= 100 → entry_price로 해석해 수량 산출.

        capital=10_000_000, max_weight=0.20 → target_value=2_000_000
        score=50_000 → qty = int(2_000_000 / 50_000) = 40
        """
        ps = _base_paramset(max_weight_per_stock=0.20)
        sizer = _TSSizer()
        qty = sizer.size(capital=10_000_000, score=50_000.0, paramset=ps)
        assert qty == 40

    def test_size_with_low_price_stock(self):
        """저가주(score=5_000) → int(2_000_000 / 5_000) = 400."""
        ps = _base_paramset(max_weight_per_stock=0.20)
        sizer = _TSSizer()
        qty = sizer.size(capital=10_000_000, score=5_000.0, paramset=ps)
        assert qty == 400

    def test_size_with_high_price_stock(self):
        """고가주(score=500_000) → int(2_000_000 / 500_000) = 4."""
        ps = _base_paramset(max_weight_per_stock=0.20)
        sizer = _TSSizer()
        qty = sizer.size(capital=10_000_000, score=500_000.0, paramset=ps)
        assert qty == 4

    def test_size_minimum_one_share(self):
        """매우 고가(score=5_000_000) → 최소 1주 보장."""
        ps = _base_paramset(max_weight_per_stock=0.20)
        sizer = _TSSizer()
        qty = sizer.size(capital=10_000_000, score=5_000_000.0, paramset=ps)
        assert qty >= 1

    def test_size_fallback_for_feature_score(self):
        """score < 100 (피처 매칭 개수 0~3) → 5만원 가정 폴백, 최소 1주."""
        ps = _base_paramset(max_weight_per_stock=0.20)
        sizer = _TSSizer()
        qty = sizer.size(capital=10_000_000, score=3.0, paramset=ps)
        # int(2_000_000 / 50_000) = 40, max(40, 1) = 40
        assert qty == 40

    def test_size_always_positive(self):
        """항상 qty >= 1 (score=0 포함)."""
        ps = _base_paramset(max_weight_per_stock=0.20)
        sizer = _TSSizer()
        for score in [0.0, 1.0, 2.0, 3.0, 50_000.0, 300_000.0]:
            qty = sizer.size(capital=10_000_000, score=score, paramset=ps)
            assert qty >= 1, f"score={score}에서 qty={qty} < 1"

"""Minervini VCP — rule_vcp_contraction_breakout (제대로 된 VCP 핵심) 테스트.

VCP 책 사양(research.md §3):
  - 베이스 ≥ base_lookback 거래일
  - 2~4(min~max)회 연속 되돌림(contraction leg)
  - 각 contraction 진폭(낙폭%)이 직전의 contraction_shrink_ratio 이내로 단계적 축소
  - 각 contraction 평균 거래량이 직전보다 감소(거래량 dry-up 시퀀스)
  - 피벗 = 마지막 contraction 의 고점(직전 swing high)
  - 돌파 = 종가 > 피벗×(1+pivot_buffer) + 돌파 거래량 ≥ base 평균×rvol_mult
  - no-lookahead: df.iloc[:t+1] 만 사용

TDD: 이 파일은 구현 전 먼저 작성되어 실패를 확인한 뒤 통과시킨다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.books.minervini_vcp.rules import (
    rule_vcp_contraction_breakout,
    ALL_RULES,
)
from strategies.books._base_book_strategy import BookStrategy
from backtest.book_backtester import BookBacktester


# ---------------------------------------------------------------------------
# toy df 빌더: 단계적으로 축소되는 연속 수축파동 + 거래량 감소 + 피벗 돌파
# ---------------------------------------------------------------------------

def _leg(start_price, peak, trough, up_bars, down_bars, vol):
    """한 contraction leg = 직전 저점에서 peak 로 상승(up_bars) 후 trough 로 하락(down_bars).

    각 봉 close 리스트와 volume 리스트를 반환. high/low 는 close 기준 ±소폭.
    """
    closes = list(np.linspace(start_price, peak, up_bars + 1))[1:]
    closes += list(np.linspace(peak, trough, down_bars + 1))[1:]
    vols = [vol] * len(closes)
    return closes, vols


def _build_vcp_df(
    *,
    base_start=100.0,
    # 3개 contraction: 낙폭 -25% → -12% → -5% (단계적 축소), 거래량 감소
    legs=(
        # (peak, trough, up_bars, down_bars, vol)
        (120.0, 90.0, 8, 8, 3000),   # leg1 깊은 수축, 큰 거래량
        (118.0, 104.0, 6, 6, 2000),  # leg2 얕아짐, 거래량 감소
        (116.0, 110.0, 5, 5, 1200),  # leg3 더 얕음, 거래량 더 감소
    ),
    warmup_pad=30,
    breakout_price=125.0,
    breakout_vol=8000,
    final_pad=0,
):
    """수축 파동 시퀀스 → 마지막 봉에서 피벗(가장 최근 swing high) 돌파 + 대량거래.

    warmup_pad: 룰 base_lookback 충족용 평탄 prefix.
    """
    closes = [base_start] * warmup_pad
    vols = [2500] * warmup_pad
    cur = base_start
    for (peak, trough, up_b, down_b, vol) in legs:
        c, v = _leg(cur, peak, trough, up_b, down_b, vol)
        closes += c
        vols += v
        cur = trough
    # 돌파봉
    closes.append(breakout_price)
    vols.append(breakout_vol)
    for _ in range(final_pad):
        closes.append(breakout_price)
        vols.append(breakout_vol)

    n = len(closes)
    df = pd.DataFrame({
        "datetime": pd.date_range("2025-01-01", periods=n, freq="D"),
        "open": closes,
        "high": [c * 1.005 for c in closes],
        "low": [c * 0.995 for c in closes],
        "close": closes,
        "volume": vols,
    })
    return df


# ---------------------------------------------------------------------------
# 1. 정상 VCP: 단계적 수축 + 거래량 감소 + 피벗 돌파 + RVOL → triggered=True
# ---------------------------------------------------------------------------

def test_valid_vcp_breakout_triggers():
    df = _build_vcp_df()
    rule = rule_vcp_contraction_breakout()
    res = rule.evaluate(df, {})
    assert res.triggered is True
    assert res.side == "buy"
    assert "pivot" in res.metadata
    assert res.metadata["n_contractions"] >= rule.min_contractions


# ---------------------------------------------------------------------------
# 2. 수축이 단계적으로 축소되지 않으면(낙폭이 오히려 커짐) → False
# ---------------------------------------------------------------------------

def test_non_shrinking_contractions_fail():
    df = _build_vcp_df(
        legs=(
            (116.0, 110.0, 5, 5, 1200),   # leg1 얕음
            (118.0, 104.0, 6, 6, 2000),   # leg2 더 깊음 (확대 — VCP 위반)
            (120.0, 90.0, 8, 8, 3000),    # leg3 가장 깊음
        ),
    )
    rule = rule_vcp_contraction_breakout()
    res = rule.evaluate(df, {})
    assert res.triggered is False


# ---------------------------------------------------------------------------
# 3. 돌파봉 거래량 부족(RVOL 미달) → False
# ---------------------------------------------------------------------------

def test_insufficient_breakout_volume_fails():
    df = _build_vcp_df(breakout_vol=1000)  # base 평균보다 작음 → RVOL < 1
    rule = rule_vcp_contraction_breakout(rvol_mult=1.5)
    res = rule.evaluate(df, {})
    assert res.triggered is False


# ---------------------------------------------------------------------------
# 4. 피벗 돌파 없음(종가가 피벗 미만) → False
# ---------------------------------------------------------------------------

def test_no_pivot_breakout_fails():
    df = _build_vcp_df(breakout_price=112.0)  # 마지막 피벗(116) 아래
    rule = rule_vcp_contraction_breakout()
    res = rule.evaluate(df, {})
    assert res.triggered is False


# ---------------------------------------------------------------------------
# 5. 거래량이 contraction 마다 감소하지 않으면(증가) → False
# ---------------------------------------------------------------------------

def test_volume_not_drying_up_fails():
    df = _build_vcp_df(
        legs=(
            (120.0, 90.0, 8, 8, 1000),    # 거래량 증가 시퀀스
            (118.0, 104.0, 6, 6, 2000),
            (116.0, 110.0, 5, 5, 3000),
        ),
    )
    rule = rule_vcp_contraction_breakout()
    res = rule.evaluate(df, {})
    assert res.triggered is False


# ---------------------------------------------------------------------------
# 6. 데이터 부족(base_lookback 미만) → False (no-lookahead 가드)
# ---------------------------------------------------------------------------

def test_insufficient_data_fails():
    df = _build_vcp_df(warmup_pad=2)  # 너무 짧음
    rule = rule_vcp_contraction_breakout(base_lookback=60)
    short = df.iloc[:20].reset_index(drop=True)
    res = rule.evaluate(short, {})
    assert res.triggered is False


# ---------------------------------------------------------------------------
# 7. 파라미터 dataclass 필드 존재 확인
# ---------------------------------------------------------------------------

def test_rule_has_tunable_fields():
    from dataclasses import fields
    names = {f.name for f in fields(rule_vcp_contraction_breakout)}
    for expected in (
        "base_lookback", "min_contractions", "max_contractions",
        "contraction_shrink_ratio", "pivot_buffer", "rvol_mult",
    ):
        assert expected in names, f"missing tunable field {expected!r}"


# ---------------------------------------------------------------------------
# 8. ALL_RULES 에 합류 + 기존 룰 보존
# ---------------------------------------------------------------------------

def test_rule_registered_and_existing_preserved():
    names = {cls().name for cls in ALL_RULES}
    assert "vcp_contraction_breakout" in names
    # 기존 룰 보존
    for kept in ("trend_template", "vcp_breakout", "tight_closes", "volume_dryup"):
        assert kept in names


# ---------------------------------------------------------------------------
# 9. no-lookahead: t 시점 평가가 t 이후 봉에 의존하지 않음
# ---------------------------------------------------------------------------

def test_no_lookahead_window_invariance():
    df = _build_vcp_df(final_pad=10)  # 돌파 이후 봉 다수
    rule = rule_vcp_contraction_breakout()
    # 돌파봉 인덱스(첫 breakout_price 위치)
    breakout_idx = df.index[df["close"] >= 125.0][0]
    window_at_breakout = df.iloc[: breakout_idx + 1]
    res_truncated = rule.evaluate(window_at_breakout, {})
    # 같은 시점을 전체 df 의 슬라이스로 평가해도 동일해야 함
    res_full_slice = rule.evaluate(df.iloc[: breakout_idx + 1].copy(), {})
    assert res_truncated.triggered == res_full_slice.triggered


# ---------------------------------------------------------------------------
# 10. run_single 백테스트 거래 발생 (BookStrategy single 모드)
# ---------------------------------------------------------------------------

def test_run_single_produces_trade():
    df = _build_vcp_df(final_pad=8)
    strat = BookStrategy(
        rules=[rule_vcp_contraction_breakout()],
        mode="single",
        target_rule="vcp_contraction_breakout",
    )
    bt = BookBacktester(
        strategy=strat,
        initial_capital=1_000_000,
        warmup_bars=35,
        stop_loss_pct=0.08,
        take_profit_pct=0.20,
        max_hold_bars=35,
        eod_liquidate=False,
    )
    result = bt.run_single("005930", df)
    assert any(t["side"] == "buy" for t in result.trades)

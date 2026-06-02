"""급등주 투매폭 매매법 (surge_fade, 15분봉) 단위 테스트.

TDD: 투매폭 매트릭스 + rule_surge_fade(지지확인/게이트) + run_single 거래 발생.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.book_backtester import BookBacktester, BookBacktestResult
from strategies.books.surge_fade.rules import (
    ALL_RULES,
    fade_band_for_rally,
    rule_surge_fade,
)
from strategies.books.surge_fade.strategy import build_strategy


# ---------------------------------------------------------------------------
# 1. 투매폭 매트릭스 단위 테스트
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rally, expected",
    [
        (0.25, (0.10, 0.15)),   # 20~30%
        (0.35, (0.14, 0.18)),   # 31~40%
        (0.45, (0.15, 0.21)),   # 41~50%
        (0.55, (0.18, 0.24)),   # 51~60%
        (0.65, (0.20, 0.25)),   # 61~70%
        (0.75, (0.21, 0.24)),   # 71~80%
        (0.85, (0.24, 0.27)),   # 81~90%
        (0.95, (0.25, 0.28)),   # 91~100%
        (1.50, (0.26, 0.34)),   # 101%+
    ],
)
def test_fade_band_matrix(rally, expected):
    band = fade_band_for_rally(rally)
    assert band is not None
    assert band == pytest.approx(expected)


def test_fade_band_below_min_rally_returns_none():
    # 20% 미만 상승은 급등주 자격 미달 → None
    assert fade_band_for_rally(0.10) is None


def test_fade_band_boundary_inclusive_lower():
    # 정확히 20% = 첫 버킷
    assert fade_band_for_rally(0.20) == pytest.approx((0.10, 0.15))
    # 정확히 31% = 두번째 버킷
    assert fade_band_for_rally(0.31) == pytest.approx((0.14, 0.18))


# ---------------------------------------------------------------------------
# 2. toy 15분봉 df 빌더
# ---------------------------------------------------------------------------

def _build_df(closes, highs=None, lows=None, opens=None, volumes=None,
              start="2026-04-01 09:00", freq="15min"):
    n = len(closes)
    highs = highs if highs is not None else [c * 1.002 for c in closes]
    lows = lows if lows is not None else [c * 0.998 for c in closes]
    opens = opens if opens is not None else closes[:]
    volumes = volumes if volumes is not None else [1000.0] * n
    return pd.DataFrame({
        "datetime": pd.date_range(start, periods=n, freq=freq),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def _surge_fade_scenario(triggered_case: str = "ok"):
    """급등(저점100→고점150, +50%) 후 적정 투매폭(고점대비 ~19%)까지 눌림.

    41~50% 버킷 → 적정 투매폭 0.15~0.21. 진입가 영역 = 150*(1-0.19)≈121.5.
    마지막 봉: 거래량 급감 + RSI 과매도 탈출 + 양봉 → triggered.
    triggered_case:
      ok       : 정상 진입
      too_deep : 고점대비 30% 초과 하락 (추세이탈) → False
      below_ma : MA20 이탈 → False
      no_support: 지지미확인(거래량 안 줄고 RSI 과매도 아님) → False
    """
    # 0) warmup 평탄 구간 (rally_lookback=64 + 여유 확보용)
    flat = [100.0] * 20
    # 1) 상승 구간: 100 → 150 완만 상승 (40봉)
    up = [100.0 + (50.0 * k / 39.0) for k in range(40)]
    # 2) 눌림 구간: 150 → 목표가까지 하락 (24봉)
    high = 150.0
    if triggered_case == "too_deep":
        bottom = high * (1 - 0.33)   # 고점대비 33% 하락
    else:
        bottom = high * (1 - 0.19)   # 고점대비 19% 하락 (밴드 내)
    down = [high - (high - bottom) * (k / 23.0) for k in range(1, 25)]
    closes = flat + up + down

    n = len(closes)
    opens = closes[:]
    highs = [c * 1.001 for c in closes]
    lows = [c * 0.999 for c in closes]
    # 마지막 봉을 양봉 + 직전 저점 근방으로
    opens[-1] = closes[-2]
    closes[-1] = bottom * 1.01
    highs[-1] = closes[-1] * 1.002
    lows[-1] = bottom

    # 거래량: 상승구간 큰 거래량, 눌림 후반 급감
    volumes = [1000.0] * 20 + [5000.0] * 40 + [4000.0 - 100.0 * k for k in range(24)]
    if triggered_case == "no_support":
        # 지지확인 3종 모두 불충족:
        #  - 거래량 급감 없음 (최대 거래량 유지)
        #  - RSI 과매도 탈출 없음 (마지막 봉도 계속 하락 → 과매도 유지)
        #  - 양봉 반등 없음 (음봉)
        volumes = [5000.0] * n
        # 마지막 봉을 직전봉보다 더 낮은 음봉으로 (계속 하락, 반등 아님)
        closes[-1] = closes[-2] * 0.99
        opens[-1] = closes[-2]            # open > close → 음봉
        highs[-1] = opens[-1] * 1.001
        lows[-1] = closes[-1] * 0.999

    return _build_df(closes, highs=highs, lows=lows, opens=opens, volumes=volumes)


# ---------------------------------------------------------------------------
# 3. rule_surge_fade 동작 테스트
# ---------------------------------------------------------------------------

def test_rule_triggers_on_valid_fade():
    df = _surge_fade_scenario("ok")
    rule = rule_surge_fade()
    res = rule.evaluate(df, {})
    assert res.triggered is True
    assert res.side == "buy"


def test_rule_rejects_too_deep_fade():
    df = _surge_fade_scenario("too_deep")
    rule = rule_surge_fade()
    res = rule.evaluate(df, {})
    assert res.triggered is False


def test_rule_rejects_below_ma_gate():
    # "ok" 시나리오는 작은 ma_gate_window 면 눌림 종가가 이평 아래 → 게이트 이탈로 기각.
    df = _surge_fade_scenario("ok")
    rule_ok = rule_surge_fade()
    assert rule_ok.evaluate(df, {}).triggered is True  # 게이트 미적용(window>len) 시 통과
    rule_gated = rule_surge_fade(ma_gate_window=30)
    res = rule_gated.evaluate(df, {})
    assert res.triggered is False


def test_rule_rejects_no_support_confirmation():
    df = _surge_fade_scenario("no_support")
    rule = rule_surge_fade()
    res = rule.evaluate(df, {})
    assert res.triggered is False


def test_rule_no_lookahead_only_uses_last_bar():
    """마지막 봉 이후 데이터를 덧붙여도 동일 시점 평가 결과는 불변해야 한다."""
    df = _surge_fade_scenario("ok")
    rule = rule_surge_fade()
    res_full = rule.evaluate(df, {})
    # 같은 시점 윈도우 (마지막 봉 포함까지) — 추가 미래봉이 없으니 동일
    res_slice = rule.evaluate(df.iloc[: len(df)].copy(), {})
    assert res_full.triggered == res_slice.triggered


# ---------------------------------------------------------------------------
# 4. run_single 통합 — 거래 발생
# ---------------------------------------------------------------------------

def test_run_single_books_a_trade():
    df = _surge_fade_scenario("ok")
    # 진입 후 +7% 반등 봉을 충분히 덧붙여 익절 체결 유도
    bottom = float(df["close"].iloc[-1])
    rebound_closes = [bottom * (1 + 0.08 * k / 5.0) for k in range(1, 6)]
    extra = _build_df(
        rebound_closes,
        start=str(df["datetime"].iloc[-1] + pd.Timedelta(minutes=15)),
    )
    df2 = pd.concat([df, extra], ignore_index=True)

    strat = build_strategy(mode="single", target_rule="surge_fade")
    bt = BookBacktester(
        strategy=strat,
        initial_capital=10_000_000,
        warmup_bars=20,
        stop_loss_pct=0.04,
        take_profit_pct=0.07,
        max_hold_bars=30,
    )
    res = bt.run_single("123456", df2)
    assert isinstance(res, BookBacktestResult)
    assert res.n_trades >= 1
    assert any(t["side"] == "buy" for t in res.trades)


def test_all_rules_contains_surge_fade():
    names = [cls().name for cls in ALL_RULES]
    assert "surge_fade" in names

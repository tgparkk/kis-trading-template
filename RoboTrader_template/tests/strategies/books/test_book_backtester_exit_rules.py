"""BookBacktester 확장 청산 규칙 테스트.

대상: `backtest/concept_axes/ma5_exit/PREREG.md` §2-1 arm 표 / §2-3 우선순위 / §5-1 귀무 `R_exit`.

🔴 **이 파일에서 가장 중요한 것은 맨 위의 골든 회귀 두 건이다.**
기대값은 확장 «이전» 코드가 실제로 찍어낸 체결 기록을 그대로 박아넣은 것이라,
새 파라미터를 하나도 주지 않았을 때 그 기록이 한 글자도 달라지지 않아야 한다.
"""

import random

import pandas as pd
import pytest

from backtest.book_backtester import BookBacktester
from strategies.books._base_book_strategy import BookStrategy, Rule, RuleResult


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

class _AlwaysBuy(Rule):
    """무포지션이면 항상 매수 — 청산 규칙만 떼어 보기 위한 룰."""

    name = "always_buy"

    def evaluate(self, df, ctx):
        return RuleResult(triggered=True, side="buy", reasons=["always_buy"])


class _BuyAtBar(Rule):
    """정확히 한 봉에서만 매수 — 진입 시점을 못박는다."""

    name = "buy_at_bar"

    def __init__(self, bar: int):
        self._bar = bar

    def evaluate(self, df, ctx):
        if len(df) - 1 == self._bar:
            return RuleResult(triggered=True, side="buy", reasons=["buy_at_bar"])
        return RuleResult(triggered=False)


def _strategy(rule: Rule) -> BookStrategy:
    return BookStrategy(rules=[rule], mode="single", target_rule=rule.name)


def _mkdf(closes) -> pd.DataFrame:
    """open=high=low=close 인 합성 봉 — 체결가가 아니라 «사유/봉» 을 보기 위한 것."""
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2026-04-01 09:00", periods=n, freq="1min"),
        "open": list(closes),
        "high": list(closes),
        "low": list(closes),
        "close": list(closes),
        "volume": [1000] * n,
    })


# 수수료·세금·슬리피지 0 — 청산 사유와 발동 봉만 남긴다.
_FRICTIONLESS = dict(
    initial_capital=1_000_000,
    commission_rate=0.0,
    tax_rate=0.0,
    slippage_rate=0.0,
    eod_liquidate=False,
)


def _reasons(result):
    return [(t["side"], t["idx"], t["reason"]) for t in result.trades]


# ===========================================================================
# 1. 🔴 골든 회귀 — 「새 파라미터를 안 주면 확장 전과 완전히 동일」
# ===========================================================================
#
# 아래 두 리터럴은 «확장 이전» book_backtester 가 실제로 산출한 체결 기록이다.
# stop_loss / take_profit / max_hold / eod / forced_close 다섯 사유를 모두 덮는다.

def _golden_df() -> pd.DataFrame:
    closes = [
        100.0, 100.0, 100.0, 100.0,          # 0-3   워밍업
        101.0, 102.0, 103.5, 105.0, 106.0,   # 4-8   상승 → take_profit
        104.0, 102.0, 100.0, 98.0, 96.0,     # 9-13  하락 → stop_loss
        96.2, 96.1, 96.3, 96.2, 96.4,        # 14-18 평탄 → max_hold
        96.3, 96.5, 96.4, 96.6, 96.5,        # 19-23 평탄 → max_hold
        97.0, 99.0, 101.0, 100.0, 98.0,      # 24-28 등락
        97.0, 96.0, 96.5, 97.5, 98.5,        # 29-33
        99.5, 99.0, 98.0, 97.0, 96.5, 96.0,  # 34-39 → eod / forced_close
    ]
    opens = [round(c * 0.998, 6) for c in closes]
    return pd.DataFrame({
        "datetime": pd.date_range("2026-04-01 09:00", periods=len(closes), freq="1min"),
        "open": opens,
        "high": [round(max(o, c) * 1.002, 6) for o, c in zip(opens, closes)],
        "low": [round(min(o, c) * 0.998, 6) for o, c in zip(opens, closes)],
        "close": closes,
        "volume": [1000 + i for i in range(len(closes))],
    })


GOLDEN_EOD_TRUE = [
    {"side": "buy", "idx": 4, "price": 100.89879799999999, "qty": 9811, "reason": "always_buy", "entry_price": 100.89879799999999, "pnl_pct": 0.0},
    {"side": "sell", "idx": 8, "price": 105.68221199999999, "qty": 9811, "reason": "take_profit", "entry_price": 100.89879799999999, "pnl_pct": 0.04740803750704749},
    {"side": "buy", "idx": 9, "price": 103.89579199999999, "qty": 9955, "reason": "always_buy", "entry_price": 103.89579199999999, "pnl_pct": 0.0},
    {"side": "sell", "idx": 12, "price": 97.706196, "qty": 9955, "reason": "stop_loss", "entry_price": 103.89579199999999, "pnl_pct": -0.059575040344270934},
    {"side": "buy", "idx": 13, "price": 95.903808, "qty": 10127, "reason": "always_buy", "entry_price": 95.903808, "pnl_pct": 0.0},
    {"side": "sell", "idx": 19, "price": 96.0112926, "qty": 10127, "reason": "max_hold", "entry_price": 95.903808, "pnl_pct": 0.0011207542457543134},
    {"side": "buy", "idx": 20, "price": 96.403307, "qty": 10065, "reason": "always_buy", "entry_price": 96.403307, "pnl_pct": 0.0},
    {"side": "sell", "idx": 26, "price": 100.697202, "qty": 10065, "reason": "max_hold", "entry_price": 96.403307, "pnl_pct": 0.044540951276702635},
    {"side": "buy", "idx": 27, "price": 99.89979999999998, "qty": 10120, "reason": "always_buy", "entry_price": 99.89979999999998, "pnl_pct": 0.0},
    {"side": "sell", "idx": 30, "price": 95.712192, "qty": 10120, "reason": "stop_loss", "entry_price": 99.89979999999998, "pnl_pct": -0.04191808191808175},
    {"side": "buy", "idx": 31, "price": 96.403307, "qty": 10031, "reason": "always_buy", "entry_price": 96.403307, "pnl_pct": 0.0},
    {"side": "sell", "idx": 35, "price": 98.703198, "qty": 10031, "reason": "take_profit", "entry_price": 96.403307, "pnl_pct": 0.023856972043500565},
    {"side": "buy", "idx": 36, "price": 97.90180399999998, "qty": 10090, "reason": "always_buy", "entry_price": 97.90180399999998, "pnl_pct": 0.0},
    {"side": "sell", "idx": 39, "price": 95.712192, "qty": 10090, "reason": "eod", "entry_price": 97.90180399999998, "pnl_pct": -0.022365389712328314},
]

GOLDEN_EOD_FALSE = GOLDEN_EOD_TRUE[:-1] + [
    {"side": "sell", "idx": 39, "price": 95.904, "qty": 10090, "reason": "forced_close", "entry_price": 97.90180399999998, "pnl_pct": -0.02040620211656149},
]


def _assert_trades_match(actual, expected):
    assert len(actual) == len(expected), (
        f"체결 «건수» 가 달라졌다: {len(actual)} != {len(expected)}\n{actual}"
    )
    for i, (got, want) in enumerate(zip(actual, expected)):
        assert got["side"] == want["side"], f"trade[{i}].side"
        assert got["idx"] == want["idx"], f"trade[{i}].idx"
        assert got["reason"] == want["reason"], f"trade[{i}].reason"
        assert got["qty"] == want["qty"], f"trade[{i}].qty"
        assert got["price"] == pytest.approx(want["price"], rel=1e-12), f"trade[{i}].price"
        assert got["entry_price"] == pytest.approx(want["entry_price"], rel=1e-12), \
            f"trade[{i}].entry_price"
        assert got["pnl_pct"] == pytest.approx(want["pnl_pct"], rel=1e-12, abs=1e-15), \
            f"trade[{i}].pnl_pct"


def _golden_bt(**kw):
    base = dict(
        strategy=_strategy(_AlwaysBuy()),
        initial_capital=1_000_000,
        warmup_bars=3,
        max_hold_bars=5,
    )
    base.update(kw)
    return BookBacktester(**base)


def test_defaults_reproduce_pre_extension_trades_eod_liquidate():
    """🔴 회귀: 새 파라미터를 하나도 주지 않으면 확장 전 체결 기록과 동일하다."""
    result = _golden_bt(eod_liquidate=True).run_single("005930", _golden_df())
    _assert_trades_match(result.trades, GOLDEN_EOD_TRUE)
    # 골든이 네 분기를 실제로 덮고 있는지 — 「덮지 못한 골든」을 회귀 증거로 쓰지 않기 위해.
    assert {t["reason"] for t in result.trades if t["side"] == "sell"} == {
        "take_profit", "stop_loss", "max_hold", "eod",
    }


def test_defaults_reproduce_pre_extension_trades_forced_close():
    """🔴 회귀: eod_liquidate=False 경로(forced_close 포함)도 확장 전과 동일하다."""
    result = _golden_bt(eod_liquidate=False).run_single("005930", _golden_df())
    _assert_trades_match(result.trades, GOLDEN_EOD_FALSE)
    assert result.trades[-1]["reason"] == "forced_close"


def test_defaults_leave_new_exit_reasons_unreachable():
    """기본값에서는 새 사유가 «구조적으로» 나올 수 없다."""
    for eod in (True, False):
        result = _golden_bt(eod_liquidate=eod).run_single("005930", _golden_df())
        reasons = {t["reason"] for t in result.trades if t["side"] == "sell"}
        assert reasons.isdisjoint({"line_break", "disaster_stop", "random_exit"})


# ===========================================================================
# 2. line_break — 「정확히 의도한 봉」에서만
# ===========================================================================

def _line_break_df() -> pd.DataFrame:
    # 0~14: 100→114 단조 상승(종가가 SMA5 위) / 15~19: 108 로 하향 이탈
    return _mkdf([100.0 + i for i in range(15)] + [108.0] * 5)


def _line_bt(**kw):
    base = dict(
        strategy=_strategy(_BuyAtBar(6)),
        warmup_bars=6,
        max_hold_bars=100,
        stop_loss_pct=None,
        take_profit_pct=None,
        exit_line="SMA5",
        **_FRICTIONLESS,
    )
    base.update(kw)
    return BookBacktester(**base)


def test_line_break_fires_on_the_exact_intended_bar():
    df = _line_break_df()
    result = _line_bt().run_single("005930", df)

    # 진입 봉 7 / 청산 판정 봉 15 → 체결은 «다음 봉» 16
    assert _reasons(result) == [
        ("buy", 7, "buy_at_bar"),
        ("sell", 16, "line_break"),
    ]


def test_line_break_not_armed_on_the_bar_before():
    """직전 봉에서는 «미발동» 이어야 한다 — 발동 봉이 하나만 맞는지 직접 확인."""
    df = _line_break_df()
    bt = _line_bt()
    for i in (13, 14):
        window = df.iloc[: i + 1]
        assert bt._is_line_broken(window, float(df["close"].iloc[i])) is False, f"i={i}"
    window15 = df.iloc[:16]
    assert bt._exit_line_value(window15) == pytest.approx(111.6)
    assert bt._is_line_broken(window15, float(df["close"].iloc[15])) is True


def test_exit_line_uses_only_closed_bars_no_lookahead():
    """선은 `df.iloc[: i+1]` 의 close 로만 계산된다 — 미래 봉을 바꿔도 값이 안 변한다."""
    df = _line_break_df()
    bt = _line_bt()
    before = bt._exit_line_value(df.iloc[:16])

    tampered = df.copy()
    tampered.loc[16:, "close"] = 1.0  # 미래 봉을 망가뜨린다
    after = bt._exit_line_value(tampered.iloc[:16])

    assert before == after


@pytest.mark.parametrize("line,expected", [
    ("SMA5", 5), ("SMA10", 10), ("SMA20", 20), ("SMA60", 60),
])
def test_sma_lines_match_plain_rolling_mean(line, expected):
    df = _mkdf([100.0 + (i % 7) for i in range(80)])
    bt = _line_bt(exit_line=line)
    window = df.iloc[:80]
    assert bt._exit_line_value(window) == pytest.approx(
        window["close"].rolling(expected).mean().iloc[-1]
    )


def test_line_break_requires_strict_inequality():
    """`close_t < line_t` 다 — 정확히 «같으면» 미발동."""
    bt = _line_bt()
    flat = _mkdf([100.0] * 10)
    window = flat.iloc[:10]
    assert bt._exit_line_value(window) == pytest.approx(100.0)
    assert bt._is_line_broken(window, 100.0) is False, "동일가는 「이탈」이 아니다"
    assert bt._is_line_broken(window, 99.999) is True


def test_ema_has_no_warmup_nan_by_construction():
    """🔴 문서화용 — `adjust=False` EMA 는 첫 봉부터 값이 나온다(= NaN 워밍업이 없다).

    따라서 EMA13/EMA65 arm 에서 `NaN` 미발동 가드는 «걸리지 않는다».
    PREREG §7-5 의 「EMA65 는 60봉에서 수렴하지 않는다」는 결측이 아니라
    «수렴 부족» 문제이고, 이 백테스터는 그것을 결측으로 표시하지 않는다.
    """
    short = _mkdf([100.0, 101.0, 102.0])
    for line in ("EMA13", "EMA65"):
        bt = _line_bt(exit_line=line)
        assert not pd.isna(bt._exit_line_value(short.iloc[:3]))
    # 대조: 같은 길이에서 SMA5 는 NaN 이다.
    assert pd.isna(_line_bt(exit_line="SMA5")._exit_line_value(short.iloc[:3]))


@pytest.mark.parametrize("line,span", [("EMA13", 13), ("EMA65", 65)])
def test_ema_lines_match_ewm_adjust_false(line, span):
    df = _mkdf([100.0 + (i % 7) for i in range(80)])
    bt = _line_bt(exit_line=line)
    window = df.iloc[:80]
    assert bt._exit_line_value(window) == pytest.approx(
        window["close"].ewm(span=span, adjust=False).mean().iloc[-1]
    )


# ===========================================================================
# 3. 워밍업 부족(NaN) → 미발동
# ===========================================================================

def _declining_df() -> pd.DataFrame:
    # 15봉 단조 하락 — 선이 계산되기만 하면 «반드시» 이탈한다.
    return _mkdf([100.0 - 2 * i for i in range(15)])


def _warmup_bt(exit_line):
    return BookBacktester(
        strategy=_strategy(_BuyAtBar(3)),
        warmup_bars=3,
        max_hold_bars=100,
        stop_loss_pct=None,
        take_profit_pct=None,
        exit_line=exit_line,
        **_FRICTIONLESS,
    )


def test_line_break_suppressed_while_line_is_nan():
    """SMA20 은 15봉짜리 df 에서 끝까지 NaN → 단조 하락인데도 미발동."""
    df = _declining_df()
    bt = _warmup_bt("SMA20")

    assert pd.isna(bt._exit_line_value(df.iloc[:15])), "이 시나리오는 선이 NaN 이어야 뜻이 있다"
    assert bt._is_line_broken(df.iloc[:15], float(df["close"].iloc[14])) is False

    result = bt.run_single("005930", df)
    assert _reasons(result) == [("buy", 4, "buy_at_bar"), ("sell", 14, "forced_close")]
    assert all(t["reason"] != "line_break" for t in result.trades)


def test_same_data_does_break_once_the_line_is_computable():
    """🔑 대칭 단언 — 같은 데이터에 SMA5 를 걸면 발동한다.

    즉 위 테스트의 「미발동」은 데이터가 밋밋해서가 아니라 «NaN 가드» 때문이다.
    """
    df = _declining_df()
    result = _warmup_bt("SMA5").run_single("005930", df)
    assert _reasons(result) == [("buy", 4, "buy_at_bar"), ("sell", 5, "line_break")]


# ===========================================================================
# 4. 우선순위 (PREREG §2-3)
# ===========================================================================

def _crash_df() -> pd.DataFrame:
    # 0~9: 100 평탄 / 10~15: 85 (-15% 급락)
    return _mkdf([100.0] * 10 + [85.0] * 6)


def _crash_bt(**kw):
    base = dict(
        strategy=_strategy(_BuyAtBar(3)),
        warmup_bars=3,
        max_hold_bars=100,
        take_profit_pct=None,
        **_FRICTIONLESS,
    )
    base.update(kw)
    return BookBacktester(**base)


def test_disaster_stop_wins_over_stop_loss_and_line_break_on_same_bar():
    """같은 봉(i=10)에서 세 조건이 «동시에» 성립한다 — 마지노선이 이긴다."""
    df = _crash_df()
    result = _crash_bt(
        disaster_stop_pct=0.10, stop_loss_pct=0.02, exit_line="SMA5",
    ).run_single("005930", df)
    assert _reasons(result) == [("buy", 4, "buy_at_bar"), ("sell", 11, "disaster_stop")]


def test_without_disaster_the_same_bar_falls_through_to_stop_loss():
    """🔑 대칭 — 마지노선만 끄면 같은 봉이 stop_loss 로 잡힌다(조건은 그대로 성립)."""
    df = _crash_df()
    result = _crash_bt(
        disaster_stop_pct=None, stop_loss_pct=0.02, exit_line="SMA5",
    ).run_single("005930", df)
    assert _reasons(result) == [("buy", 4, "buy_at_bar"), ("sell", 11, "stop_loss")]


def test_without_disaster_and_stop_loss_the_same_bar_falls_through_to_line_break():
    """🔑 대칭 — %손절까지 끄면 같은 봉이 line_break 로 잡힌다."""
    df = _crash_df()
    result = _crash_bt(
        disaster_stop_pct=None, stop_loss_pct=None, exit_line="SMA5",
    ).run_single("005930", df)
    assert _reasons(result) == [("buy", 4, "buy_at_bar"), ("sell", 11, "line_break")]


def test_disaster_stop_wins_over_random_exit_on_same_bar():
    """우선순위 1) disaster_stop > 2) random_exit — 둘이 같은 봉에서 성립하게 맞춘다."""
    df = _crash_df()
    bt = _crash_bt(
        disaster_stop_pct=0.10, stop_loss_pct=None,
        random_exit_seed=0, random_exit_max_bars=6,
    )
    # 이 시나리오가 성립하려면 k 가 정확히 6 이어야 한다(진입 4 + 6 = 급락 봉 10).
    assert bt._random_exit_bars("005930", 4) == 6

    result = bt.run_single("005930", df)
    assert _reasons(result) == [("buy", 4, "buy_at_bar"), ("sell", 11, "disaster_stop")]


def test_without_disaster_the_same_bar_falls_through_to_random_exit():
    """🔑 대칭 — 마지노선만 끄면 같은 봉이 random_exit 로 잡힌다."""
    df = _crash_df()
    result = _crash_bt(
        disaster_stop_pct=None, stop_loss_pct=None,
        random_exit_seed=0, random_exit_max_bars=6,
    ).run_single("005930", df)
    assert _reasons(result) == [("buy", 4, "buy_at_bar"), ("sell", 11, "random_exit")]


# ---------------------------------------------------------------------------
# PREREG §2-1 arm 표 → §2-3 우선순위 대조
# ---------------------------------------------------------------------------
#
# §2-3 은 계열별로 이렇게 적혀 있다:
#     FIXED : 손절 → 익절 → max_hold
#     LINE  : 마지노선(−10%) → 선 이탈 → max_hold
# 구현의 단일 사슬(disaster → random → sl → tp → line → max_hold → eod)이
# «각 계열의 파라미터를 넣었을 때» 위 두 줄로 «축약» 되는지를 여기서 못박는다.

_FIXED_ARMS = {                                     # PREREG §2-1
    "X0": dict(stop_loss_pct=0.03, take_profit_pct=0.15),
    "X1": dict(stop_loss_pct=0.05, take_profit_pct=0.10),
    "X2": dict(stop_loss_pct=0.06, take_profit_pct=0.12),
}
_LINE_ARMS = {
    "L5": "SMA5", "L10": "SMA10", "L20": "SMA20",
    "L60": "SMA60", "LE13": "EMA13", "LE65": "EMA65",
}


@pytest.mark.parametrize("arm", sorted(_FIXED_ARMS))
def test_prereg_fixed_arm_reduces_to_stop_take_maxhold(arm):
    """FIXED 계열엔 마지노선도 선도 없다 → 사슬이 손절 → 익절 → max_hold 로 축약."""
    bt = BookBacktester(
        strategy=_strategy(_BuyAtBar(3)), warmup_bars=3, max_hold_bars=30,
        **_FIXED_ARMS[arm], **_FRICTIONLESS,
    )
    assert bt.disaster_stop_pct is None and bt.exit_line is None
    assert bt.random_exit_seed is None
    # -15% 급락 봉은 손절로 잡힌다(마지노선이 없으므로).
    assert _reasons(bt.run_single("005930", _crash_df())) == [
        ("buy", 4, "buy_at_bar"), ("sell", 11, "stop_loss"),
    ]


@pytest.mark.parametrize("arm", sorted(_LINE_ARMS))
def test_prereg_line_arm_reduces_to_disaster_line_maxhold(arm):
    """LINE 계열엔 익절도 %손절도 없다 → 사슬이 마지노선 → 선 이탈 → max_hold 로 축약."""
    bt = BookBacktester(
        strategy=_strategy(_BuyAtBar(3)), warmup_bars=3, max_hold_bars=30,
        stop_loss_pct=None, take_profit_pct=None,
        exit_line=_LINE_ARMS[arm], disaster_stop_pct=0.10,
        **_FRICTIONLESS,
    )
    assert bt.stop_loss_pct is None and bt.take_profit_pct is None
    assert bt.random_exit_seed is None
    # -15% 는 마지노선(-10%)을 깨므로 선 이탈보다 «먼저» 잡혀야 한다.
    assert _reasons(bt.run_single("005930", _crash_df())) == [
        ("buy", 4, "buy_at_bar"), ("sell", 11, "disaster_stop"),
    ]


# ===========================================================================
# 5. stop_loss_pct / take_profit_pct = None → 해당 분기 비활성
# ===========================================================================

def _swing_df() -> pd.DataFrame:
    # 진입가 100 → -30% 급락 → +30% 급등. 문턱이 살아 있으면 손절이 «먼저» 잡힌다.
    return _mkdf([100.0] * 5 + [70.0, 72.0, 74.0, 130.0, 128.0, 126.0] + [120.0] * 3)


def test_none_thresholds_disable_stop_loss_and_take_profit():
    df = _swing_df()
    result = BookBacktester(
        strategy=_strategy(_BuyAtBar(3)),
        warmup_bars=3, max_hold_bars=100,
        stop_loss_pct=None, take_profit_pct=None,
        **_FRICTIONLESS,
    ).run_single("005930", df)
    sell_reasons = {t["reason"] for t in result.trades if t["side"] == "sell"}
    assert sell_reasons == {"forced_close"}
    assert sell_reasons.isdisjoint({"stop_loss", "take_profit"})


def test_same_data_does_stop_out_when_thresholds_are_set():
    """🔑 대칭 — 문턱을 되살리면 같은 데이터가 손절로 잡힌다."""
    df = _swing_df()
    result = BookBacktester(
        strategy=_strategy(_BuyAtBar(3)),
        warmup_bars=3, max_hold_bars=100,
        stop_loss_pct=0.02, take_profit_pct=0.03,
        **_FRICTIONLESS,
    ).run_single("005930", df)
    assert "stop_loss" in {t["reason"] for t in result.trades if t["side"] == "sell"}


# ===========================================================================
# 6. random_exit 결정성 (재현 게이트 요건)
# ===========================================================================

def _rand_bt(seed, **kw):
    base = dict(
        strategy=_strategy(_AlwaysBuy()),
        warmup_bars=3, max_hold_bars=100,
        stop_loss_pct=None, take_profit_pct=None,
        random_exit_seed=seed, random_exit_max_bars=30,
        **_FRICTIONLESS,
    )
    base.update(kw)
    return BookBacktester(**base)


def _rand_df(offset: float) -> pd.DataFrame:
    return _mkdf([100.0 + offset + (i % 5) for i in range(60)])


def test_same_key_always_draws_the_same_k():
    a, b = _rand_bt(7), _rand_bt(7)
    for entry_idx in range(1, 40):
        k = a._random_exit_bars("005930", entry_idx)
        assert 1 <= k <= 30
        assert k == a._random_exit_bars("005930", entry_idx), "같은 인스턴스 재호출"
        assert k == b._random_exit_bars("005930", entry_idx), "다른 인스턴스, 같은 시드"


def test_k_depends_on_stock_code():
    """키에 종목코드가 들어간다 — 전 종목이 같은 k 를 쓰면 귀무가 무너진다."""
    bt = _rand_bt(7)
    a = [bt._random_exit_bars("005930", j) for j in range(1, 40)]
    b = [bt._random_exit_bars("000660", j) for j in range(1, 40)]
    assert a != b


def test_random_exit_is_immune_to_global_rng_state():
    """🔴 전역 RNG 미사용 — `random.seed()` 를 흔들어도 결과가 안 변한다."""
    df = _rand_df(0.0)

    random.seed(1)
    first = _rand_bt(3).run_single("005930", df).trades

    random.seed(999_999)
    [random.random() for _ in range(1000)]
    second = _rand_bt(3).run_single("005930", df).trades

    assert first == second
    assert any(t["reason"] == "random_exit" for t in first), "이 시나리오는 random_exit 이 나야 뜻이 있다"


def test_random_exit_is_independent_of_stock_iteration_order():
    """🔴🔴 종목 순회 «순서» 가 바뀌어도 종목별 결과가 같아야 한다."""
    codes = ["005930", "000660", "035720"]
    data = {code: _rand_df(i * 3.0) for i, code in enumerate(codes)}

    forward = _rand_bt(11).run_universe(data)
    reversed_data = {code: data[code] for code in reversed(codes)}
    backward = _rand_bt(11).run_universe(reversed_data)

    for code in codes:
        assert forward.per_stock[code].trades == backward.per_stock[code].trades, code
        assert any(
            t["reason"] == "random_exit" for t in forward.per_stock[code].trades
        ), f"{code}: random_exit 이 한 번도 안 나면 순서 독립성이 공허하다"


def test_random_exit_single_run_matches_universe_run():
    """종목을 따로 돌린 결과와 유니버스로 돌린 결과가 같다."""
    codes = ["005930", "000660", "035720"]
    data = {code: _rand_df(i * 3.0) for i, code in enumerate(codes)}

    universe = _rand_bt(11).run_universe(data)
    for code in codes:
        alone = _rand_bt(11).run_single(code, data[code])
        assert alone.trades == universe.per_stock[code].trades, code


def test_different_seed_changes_the_draws():
    a = [_rand_bt(0)._random_exit_bars("005930", j) for j in range(1, 61)]
    b = [_rand_bt(1)._random_exit_bars("005930", j) for j in range(1, 61)]
    assert a != b
    assert sorted(a) != sorted(b), "값 자체가 달라야 한다(재배열이 아니라)"


def test_random_exit_respects_max_bars_bound():
    bt = _rand_bt(5, random_exit_max_bars=3)
    ks = {bt._random_exit_bars("005930", j) for j in range(1, 200)}
    assert ks <= {1, 2, 3}
    assert len(ks) == 3, "상한이 3이면 1·2·3 이 모두 나와야 한다"


def test_seed_zero_is_honoured_not_treated_as_unset():
    """🔑 시드 0 은 falsy 다 — `is not None` 으로 갈라야 한다."""
    df = _rand_df(0.0)
    result = _rand_bt(0).run_single("005930", df)
    assert any(t["reason"] == "random_exit" for t in result.trades)


# ===========================================================================
# 7. exit_line 검증
# ===========================================================================

@pytest.mark.parametrize("line", ["SMA5", "SMA10", "SMA20", "SMA60", "EMA13", "EMA65"])
def test_allowed_exit_lines_are_accepted(line):
    bt = BookBacktester(strategy=_strategy(_AlwaysBuy()), exit_line=line)
    assert bt.exit_line == line


@pytest.mark.parametrize("bad", ["SMA3", "MA5", "sma5", "EMA20", "BOLL", "", "SMA_5", "EMA13 "])
def test_invalid_exit_line_raises_value_error(bad):
    with pytest.raises(ValueError, match="exit_line"):
        BookBacktester(strategy=_strategy(_AlwaysBuy()), exit_line=bad)


def test_exit_line_none_is_allowed():
    bt = BookBacktester(strategy=_strategy(_AlwaysBuy()), exit_line=None)
    assert bt.exit_line is None

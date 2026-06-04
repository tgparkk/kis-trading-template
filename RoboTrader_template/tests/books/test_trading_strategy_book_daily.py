"""『트레이딩 전략서』 (Book 19) — 일봉 조건식 A~I 단위테스트.

all-pass 픽스처에서 각 조건을 단독으로 무너뜨려 게이트를 확인한다.
조건 C(양봉)는 조건 I(close>=open*1.03)에 함의되므로 단독 C-fail 케이스는 없음.
모든 평가는 df 마지막 행(t)만 사용 — no-lookahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


N = 210  # 최소봉수(high_window 200 + 여유) 충족


def _arrays():
    """all-pass 기본 배열 (210봉). 마지막 봉이 조건식 A~I 전부 충족하는 돌파봉."""
    close = np.full(N, 1000.0)
    open_ = np.full(N, 1000.0)
    high = np.full(N, 1000.0)
    low = np.full(N, 995.0)
    volume = np.full(N, 6_000_000.0)
    # 마지막 봉(t = index N-1) = 200일 신고가 돌파 + 양봉 + 거래량 증가
    close[-1] = 1300.0     # 직전 200봉 종가 최고 (나머지 1000)
    open_[-1] = 1010.0     # 양봉, 갭<7%(1010<1000*1.07=1070), 시가대비 close +28%
    high[-1] = 1300.0      # 종가=고가
    low[-1] = 1005.0       # 이등분선=(1300+1005)/2=1152.5 < close
    volume[-1] = 8_000_000.0  # vol_t >= vol_prev
    return open_, high, low, close, volume


def _make_df(open_, high, low, close, volume):
    n = len(close)
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    return pd.DataFrame({
        "datetime": dates,
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


def _rule():
    from strategies.books.trading_strategy_book.rules import rule_envelope_200d_high
    return rule_envelope_200d_high()


def _eval(open_, high, low, close, volume):
    return _rule().evaluate(_make_df(open_, high, low, close, volume), {})


def test_all_pass_triggers():
    res = _eval(*_arrays())
    assert res.triggered is True
    assert res.side == "buy"


def test_A_not_200d_high_blocks():
    o, h, l, c, v = _arrays()
    c[50] = 1400.0  # 과거 종가가 더 높음 → t 가 200일 신고가 아님
    assert _eval(o, h, l, c, v).triggered is False


def test_B_below_envelope_blocks():
    o, h, l, c, v = _arrays()
    c[-1] = 1100.0   # A 통과 유지(여전히 200일 신고가) but Envelope 상단(~1111) 미달 → B 단독 실패
    h[-1] = 1100.0
    o[-1] = 1000.0   # I 통과(1100>=1030), C 통과
    assert _eval(o, h, l, c, v).triggered is False


def test_D_volume_below_prev_blocks():
    o, h, l, c, v = _arrays()
    v[-1] = 5_000_000.0  # vol_t < vol_prev(6e6)
    assert _eval(o, h, l, c, v).triggered is False


def test_E_close_below_bisector_blocks():
    o, h, l, c, v = _arrays()
    h[-1] = 1700.0  # 윗꼬리 김 → 이등분선=(1700+1005)/2=1352.5 > close(1300)
    assert _eval(o, h, l, c, v).triggered is False


def test_F_low_trading_value_blocks():
    o, h, l, c, v = _arrays()
    v[:] = 4_000_000.0   # close*vol≈4e9 → 4000백만 < 5000 → F 단독 실패 (B 는 close 1300으로 통과 유지)
    v[-1] = 8_000_000.0  # D 는 통과 유지(vol_t>vol_prev)
    assert _eval(o, h, l, c, v).triggered is False


def test_G_gap_up_excluded():
    o, h, l, c, v = _arrays()
    o[-1] = 1100.0  # 시가 >= 전일종가*1.07(1070) → 갭상승 제외. I 는 1300>=1133 통과
    assert _eval(o, h, l, c, v).triggered is False


def test_H_prior_surge_excluded():
    o, h, l, c, v = _arrays()
    c[-2] = 1200.0  # 어제 종가 >= 그제(1000)*1.10 → 직전 급등 제외
    assert _eval(o, h, l, c, v).triggered is False


def test_I_intraday_gain_below_3pct_blocks():
    o, h, l, c, v = _arrays()
    o[-1] = 1290.0  # close(1300) < open*1.03(1328.7) → I 실패. C(1290<1300)는 통과
    assert _eval(o, h, l, c, v).triggered is False


def test_no_lookahead_future_bars_irrelevant():
    """t 시점 트리거는 이후 봉과 무관 — df 를 t 까지 자른 결과가 동일."""
    o, h, l, c, v = _arrays()
    df_full = _make_df(o, h, l, c, v)
    res_full = _rule().evaluate(df_full, {})
    # 이후 봉(폭락) 추가 후 t 까지 슬라이스 → 동일 결과
    extra = _make_df(
        np.full(5, 500.0), np.full(5, 500.0), np.full(5, 490.0),
        np.full(5, 500.0), np.full(5, 1_000.0),
    )
    df_more = pd.concat([df_full, extra], ignore_index=True)
    res_sliced = _rule().evaluate(df_more.iloc[: len(df_full)], {})
    assert res_full.triggered == res_sliced.triggered is True


def test_insufficient_bars_no_trigger():
    o, h, l, c, v = _arrays()
    df = _make_df(o, h, l, c, v).iloc[-50:]  # 200봉 미만
    assert _rule().evaluate(df, {}).triggered is False


def test_driver_resolves_book_and_rule():
    """멀티버스 드라이버가 책/룰을 해석할 수 있어야 한다(_load_book + _resolve_rule_cls)."""
    from scripts.book_param_multiverse import _load_book, _resolve_rule_cls, _rule_defaults
    _strat_mod, rules_mod = _load_book("trading_strategy_book")
    cls = _resolve_rule_cls(rules_mod, "envelope_200d_high")
    assert cls().name == "envelope_200d_high"
    # 클래스명(rule_ 접두) 입력도 동일 클래스로 해석 (이름 리팩터에 강건)
    assert _resolve_rule_cls(rules_mod, "rule_envelope_200d_high") is cls
    # 기본값(책 원문) 노출 확인
    d = _rule_defaults(cls)
    assert d["high_window"] == 200 and d["env_pct"] == 0.10 and d["intraday_gain"] == 0.03

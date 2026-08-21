"""rs_leader 진입/청산 교집합 불변식 (2026-08-22 수정).

배경: 매수(RSLeaderRule) = 종가>MA(ma_long) ∧ MA(ma_short)>MA(ma_long) ∧ ret>0 였고,
매도 ma_break(evaluate_sell_conditions) = 종가<MA(ma_short) 가 무조건 발동했다.
매수가 종가와 MA(ma_short)의 관계를 요구하지 않으므로 겹침 구간
(MA(ma_long) < 종가 < MA(ma_short), MA(ma_short)>MA(ma_long) 이므로 이 구간은
원리적으로 항상 비어있지 않음)에서 매수 직후 ma_break 로 즉시 매도되는 whipsaw가
발생했다. 실측(2026-08-22): 후보풀의 26.5%, 라이브 매수 71건 중 17건(23.94%)이 이
상태였고, 마스킹 결함이 걷힌 뒤로는 2/2 = 100% 가 1초 만에 왕복 체결됐다.
수정: 진입에 `종가 > MA(ma_short)` 추가(rule.py). 이 파일은 그 불변식을 고정한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.rs_leader.rule import RSLeaderRule
from strategies.rs_leader.strategy import RSLeaderStrategy


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1000] * n,
    })


def _uptrend_df():
    """단조 상승 70봉 — 정상 진입 케이스(종가 > MA20 도 자연히 성립)."""
    return _df(list(np.linspace(10000, 20000, 70)))


def _overlap_zone_df():
    """MA60 < 종가 < MA20 겹침 구간을 명시적으로 구성한 70봉.

    구성: 50봉 완만한 상승(10000→14000, MA60 기준선) + 19봉 급상승
    (14000→20000, MA20을 끌어올림) + 마지막 1봉 16500으로 되돌림.
    실측(이 함수의 산출값): c=16500, MA20≈16975, MA60≈13930.44, ret≈+53.7%
    → MA60 < c < MA20 ∧ MA20 > MA60 ∧ ret > 0 (수정 전 코드라면 매수 발화 조건).
    """
    seg1 = list(np.linspace(10000, 14000, 50))
    seg2 = list(np.linspace(14000, 20000, 19))
    seg3 = [16500.0]
    return _df(seg1 + seg2 + seg3)


def test_entry_exit_intersection_empty_uptrend():
    """진입 조건이 참인 df(정상 상승) 는 같은 df 로 평가한 청산이 ma_break 가 아니다."""
    df = _uptrend_df()
    ok, _ = RSLeaderStrategy.evaluate_entry(df, min_daily_bars=len(df))
    if ok:
        entry_price = float(df["close"].astype(float).iloc[-1])
        should, _, exit_reason = RSLeaderStrategy.evaluate_sell_conditions(
            df, entry_price=entry_price, hold_days=0)
        assert exit_reason != "ma_break"


def test_entry_exit_intersection_empty_overlap_zone():
    """겹침 구간 df — 진입이 발화했다면(구식 룰이라면) 청산이 ma_break 가 아니어야
    한다는 불변식. 수정된 rule.py 에서는 애초에 진입이 발화하지 않으므로(가드 아래
    분기가 실행 안 됨) 이 테스트는 통과한다.

    🔑 이빨 검증: `c > ma_s` 를 rule.py 에서 제거하면 이 df 는 진입이 발화하고
    (겹침 구간이 구식 룰의 정의역이므로) 청산이 ma_break 로 나와 아래 assert 가
    **실제로 실패한다**(수동 확인: 2026-08-22, plain-python 재현 — pytest 미실행).
    """
    df = _overlap_zone_df()
    entry_price = float(df["close"].astype(float).iloc[-1])
    ok, _ = RSLeaderStrategy.evaluate_entry(df, min_daily_bars=len(df))
    if ok:
        should, _, exit_reason = RSLeaderStrategy.evaluate_sell_conditions(
            df, entry_price=entry_price, hold_days=0)
        assert exit_reason != "ma_break"


def test_overlap_zone_no_entry_signal():
    """겹침 구간(MA60 < 종가 < MA20) 은 수정 후 매수 신호가 없다(None)."""
    df = _overlap_zone_df()
    rule = RSLeaderRule()
    assert rule.generate_signal("000001", df, "daily") is None

    ok, reasons = RSLeaderStrategy.evaluate_entry(df, min_daily_bars=len(df))
    assert ok is False
    assert reasons == []


def test_normal_entry_still_fires():
    """기존 정상 진입 케이스(종가 > MA20 도 성립하는 단조 상승)는 여전히 신호가
    난다 — 회귀 방지."""
    df = _uptrend_df()
    rule = RSLeaderRule()
    sig = rule.generate_signal("000001", df, "daily")
    assert sig is not None

    ok, reasons = RSLeaderStrategy.evaluate_entry(df, min_daily_bars=len(df))
    assert ok is True and reasons

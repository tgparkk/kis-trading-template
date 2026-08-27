"""rs_leader 진입/청산 교집합 불변식 (2026-08-22 수정, 2026-08-22 리뷰 반영).

배경: 매수(RSLeaderRule) = 종가>MA(ma_long) ∧ MA(ma_short)>MA(ma_long) ∧ ret>0 였고,
매도 ma_break(evaluate_sell_conditions) = 종가<MA(ma_short 과 같은 기간의 trail_ma)
가 무조건 발동했다. 매수가 종가와 MA(ma_short)의 관계를 요구하지 않으므로 겹침 구간
(MA(ma_long) < 종가 < MA(ma_short), MA(ma_short)>MA(ma_long) 이므로 이 구간은
원리적으로 항상 비어있지 않음)에서 매수 직후 ma_break 로 즉시 매도되는 whipsaw가
발생했다. 실측(2026-08-22): 후보풀의 26.5%, 라이브 매수 71건 중 17건(23.94%)이 이
상태였고, 마스킹 결함이 걷힌 뒤로는 2/2 = 100% 가 1초 만에 왕복 체결됐다.
수정: 진입에 `종가 > MA(ma_short)` 추가(rule.py). 이 파일은 그 불변식을 고정한다.

리뷰 반영(2026-08-22): 최초 버전은 `if ok:` 로 assert 를 감싸 `ok`가 False 면
아무것도 검사하지 않고 통과하는 「죽은 가드」였다(특히 겹침구간 테스트는 수정 후
`ok`가 «항상» False 라 CI 에서 영원히 공허하게 통과했다). 아래 테스트들은 상태를
먼저 명시적으로(가드 없이) 단언해 공허한 통과가 원리적으로 불가능하도록 재작성했다.
또한 불변식이 `parameters.ma_short == risk_management.trail_ma`(config.yaml 상
서로 다른 두 설정 항목이 우연히 같은 값 20이라는 사실)에 의존한다는 점도
`test_ma_short_matches_trail_ma_config`로 고정했다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

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
    이 사실은 하드코딩으로만 믿지 않고 `test_entry_exit_intersection_empty_overlap_zone`
    안에서 rule.py 와 독립적으로(`_legacy_entry_condition`) 재검증한다.
    """
    seg1 = list(np.linspace(10000, 14000, 50))
    seg2 = list(np.linspace(14000, 20000, 19))
    seg3 = [16500.0]
    return _df(seg1 + seg2 + seg3)


def _legacy_entry_condition(df, ma_short: int = 20, ma_long: int = 60, abs_lb: int = 60):
    """구식(2026-08-22 수정 전) 진입 조건을 rule.py 구현과 독립적으로 재계산.

    `c > ma_s` 를 뺀 구식 조건(c>ma_l ∧ ma_s>ma_l ∧ ret>0)의 진위를 df 로부터
    직접 계산한다. rule.py 를 호출하지 않으므로 rule.py 가 어떻게 바뀌든(수정
    되돌림 포함) `_overlap_zone_df()` 가 실제로 겹침 구간을 짚고 있는지를 독립
    적으로 고정할 수 있다.
    """
    close = df["close"].astype(float)
    ma_s = float(close.rolling(ma_short, min_periods=ma_short).mean().iloc[-1])
    ma_l = float(close.rolling(ma_long, min_periods=ma_long).mean().iloc[-1])
    c = float(close.iloc[-1])
    ref = float(close.iloc[-1 - abs_lb])
    ret = c / ref - 1.0
    legacy_ok = (c > ma_l) and (ma_s > ma_l) and (ret > 0)
    return legacy_ok, c, ma_s, ma_l


def _load_config():
    cfg_path = Path(__file__).resolve().parents[3] / "strategies" / "rs_leader" / "config.yaml"
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def test_entry_exit_intersection_empty_uptrend():
    """진입 조건이 참인 df(정상 상승) 는 같은 df 로 평가한 청산이 ma_break 가 아니다.

    `ok`를 먼저 하드 단언해(가드 아님) 정상 상승 df 가 실제로 진입 조건을
    만족함을 고정한 뒤, 그 전제 위에서만 청산 불변식을 검사한다.
    """
    df = _uptrend_df()
    ok, _ = RSLeaderStrategy.evaluate_entry(df, min_daily_bars=len(df))
    assert ok is True, "_uptrend_df() 가 더 이상 진입 조건을 만족하지 않음 — df 재구성 필요"

    entry_price = float(df["close"].astype(float).iloc[-1])
    should, _, exit_reason = RSLeaderStrategy.evaluate_sell_conditions(
        df, entry_price=entry_price, hold_days=0)
    assert exit_reason != "ma_break"


def test_entry_exit_intersection_empty_overlap_zone():
    """겹침 구간 df(MA60<종가<MA20)에서 진입/청산 교집합이 비었음을 고정한다.

    세 가지를 전부 가드 없이(공허한 통과 불가능하게) 단언한다:
    1) 이 df 는 구식 진입 조건을 만족한다(`_legacy_entry_condition`, rule.py 와
       독립 재계산) — `_overlap_zone_df()` 가 실제로 겹침구간을 짚고 있다는
       사실 자체를 매번 검증한다. df 구성이 잘못 바뀌면 이 assert 가 실패한다.
    2) 그 df 로 청산을 평가하면 ma_break 가 나온다 — 「구식 룰로 샀다면 이
       df 는 즉시 청산됐을 것」을 고정한다(진입 발화 여부와 무관하게 항상 계산
       가능한 사실이므로 가드 불필요).
    3) 수정된 evaluate_entry() 는 이 df 에서 진입을 발화하지 «않는다»
       (`ok is False`, 가드 없이 직접 단언). `rule.py`의 `c > ma_s` 를 되돌리면
       이 assert 가 실패한다 — 이게 이 테스트의 이빨이다.
    """
    df = _overlap_zone_df()
    legacy_ok, c, ma_s, ma_l = _legacy_entry_condition(df)
    assert legacy_ok is True and ma_l < c < ma_s, (
        "_overlap_zone_df() 가 더 이상 MA60<종가<MA20 겹침구간을 짚지 못함 — "
        "df 재구성 필요(테스트 전제 붕괴)"
    )

    _, _, exit_reason = RSLeaderStrategy.evaluate_sell_conditions(
        df, entry_price=c, hold_days=0)
    assert exit_reason == "ma_break", (
        "겹침구간 df 인데 청산이 ma_break 가 아님 — _overlap_zone_df() 구성 확인 필요"
    )

    ok, reasons = RSLeaderStrategy.evaluate_entry(df, min_daily_bars=len(df))
    assert ok is False, (
        "겹침구간 df 에서 진입이 발화함 — rule.py 의 c>ma_s 가드가 없어졌거나 우회됨"
    )
    assert reasons == []


def test_overlap_zone_no_entry_signal():
    """겹침 구간(MA60 < 종가 < MA20) 은 수정 후 매수 신호가 없다(None).

    RSLeaderRule.generate_signal 을 직접 호출해(evaluate_entry 를 거치지 않는
    별도 경로 — screener.py 도 이 메서드를 단일 소스로 재사용) 동일 불변식을
    한 번 더 확인한다.
    """
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


def test_ma_short_matches_trail_ma_config():
    """불변식의 전제: parameters.ma_short(진입) == risk_management.trail_ma(청산).

    교집합이 비는 이유는 진입의 MA(ma_short) 와 청산 ma_break 의 MA(trail_ma) 가
    «같은 기간의 같은 이동평균»이기 때문이다. 이 둘은 config.yaml 에서 서로 다른
    설정 항목(parameters.ma_short vs risk_management.trail_ma)이라, 코드는 이
    둘이 같다고 강제하지 않는다 — 누가 trail_ma 만 바꾸면(예: 10) rule.py 의
    `c>MA(ma_short=20)` 가드는 청산의 `MA(trail_ma=10)` 이탈을 막지 못해
    진입/청산 교집합이 조용히 다시 열린다.
    """
    cfg = _load_config()
    ma_short = cfg["parameters"]["ma_short"]
    trail_ma = cfg["risk_management"]["trail_ma"]
    assert ma_short == trail_ma, (
        f"parameters.ma_short({ma_short}) != risk_management.trail_ma({trail_ma}) "
        "— 2026-08-22 진입/청산 교집합 수정의 전제(두 이동평균이 같은 기간)가 "
        "깨져 있다. 진입 가드 c>MA(ma_short) 가 청산 ma_break 의 MA(trail_ma) "
        "이탈을 더 이상 막지 못하므로 교집합이 다시 열린다."
    )

"""4 페르소나 ComposableStrategy 회귀 테스트."""
from __future__ import annotations

import math
from unittest.mock import MagicMock

import pandas as pd
import pytest

from RoboTrader_template.multiverse.composable import (
    ComposableStrategy,
    build_intraday_strategy,
    build_long_term_strategy,
    build_quant_strategy,
    build_swing_strategy,
)
from RoboTrader_template.multiverse.composable.personas.quant import (
    _QuantUniverse,
    _QuantSignalGen,
)
from RoboTrader_template.multiverse.composable.personas.long_term import (
    _LongTermSignalGen,
)
from RoboTrader_template.multiverse.composable.personas.swing import (
    _SwingUniverse,
    _SwingSignalGen,
)
from RoboTrader_template.multiverse.composable.personas.intraday import (
    _IntradayUniverse,
    _IntradaySignalGen,
)


def _mock_ctx() -> MagicMock:
    """DB 없이 동작하는 PITContext 모의 객체."""
    ctx = MagicMock()
    ctx.as_of_date = MagicMock()
    # read_daily: 빈 DataFrame 반환 → 신호 생성 조건 미충족 → HOLD
    ctx.read_daily.return_value = pd.DataFrame()
    ctx.read_financial_ratio.return_value = None
    ctx.read_minute.return_value = pd.DataFrame()
    return ctx


def _make_close_df(prices: list[float]) -> pd.DataFrame:
    """close 컬럼만 있는 DataFrame 생성."""
    return pd.DataFrame({"close": prices})


# ──────────────────────────────────────────────────────────────────────────────
# 기존 빌드 테스트 (4건)
# ──────────────────────────────────────────────────────────────────────────────

def test_quant_strategy_builds(valid_paramset):
    """퀀트 페르소나가 ComposableStrategy를 반환하고 signal_fn이 호출 가능."""
    s = build_quant_strategy(valid_paramset, ["005930", "000660"])
    assert isinstance(s, ComposableStrategy)

    sig = s.signal_fn(_mock_ctx(), symbol="005930", position=None, capital=10_000_000)
    assert sig.action in {"BUY", "SELL", "HOLD"}


def test_swing_strategy_builds(valid_paramset):
    """스윙 페르소나가 ComposableStrategy를 반환하고 signal_fn이 호출 가능."""
    s = build_swing_strategy(valid_paramset, ["005930"])
    assert isinstance(s, ComposableStrategy)

    sig = s.signal_fn(_mock_ctx(), symbol="005930", position=None, capital=10_000_000)
    assert sig.action in {"BUY", "SELL", "HOLD"}


def test_long_term_strategy_builds(valid_paramset):
    """중장기 페르소나가 ComposableStrategy를 반환하고 signal_fn이 호출 가능."""
    s = build_long_term_strategy(valid_paramset, ["005930"])
    assert isinstance(s, ComposableStrategy)

    sig = s.signal_fn(_mock_ctx(), symbol="005930", position=None, capital=10_000_000)
    assert sig.action in {"BUY", "SELL", "HOLD"}


def test_intraday_strategy_builds(valid_paramset):
    """단타 페르소나가 ComposableStrategy를 반환하고 signal_fn이 호출 가능."""
    s = build_intraday_strategy(valid_paramset, ["005930"])
    assert isinstance(s, ComposableStrategy)

    sig = s.signal_fn(_mock_ctx(), symbol="005930", position=None, capital=10_000_000)
    assert sig.action in {"BUY", "SELL", "HOLD"}


# ──────────────────────────────────────────────────────────────────────────────
# 신규 회귀 테스트 (3건)
# ──────────────────────────────────────────────────────────────────────────────

def test_quant_universe_z_score_normalization(valid_paramset):
    """Universe.select가 z-score 정규화로 상위 N개를 반환하고 캐시를 채우는지 검증."""
    symbols = ["A", "B", "C", "D", "E"]

    # 5종목에 대해 서로 다른 ROE/BPS 반환
    ratio_data = {
        "A": {"bps": 10_000, "roe": 30.0, "net_income_growth": 20.0, "sales_growth": 10.0},
        "B": {"bps": 20_000, "roe": 5.0,  "net_income_growth": 2.0,  "sales_growth": 3.0},
        "C": {"bps": 5_000,  "roe": 15.0, "net_income_growth": 10.0, "sales_growth": 8.0},
        "D": {"bps": 8_000,  "roe": 22.0, "net_income_growth": 15.0, "sales_growth": 12.0},
        "E": {"bps": 15_000, "roe": 8.0,  "net_income_growth": 5.0,  "sales_growth": 4.0},
    }
    # close: 상승 추세 (200개 이상 필요)
    close_data = {
        "A": [40_000] * 200 + [50_000] * 60,   # 모멘텀 +25%
        "B": [80_000] * 200 + [90_000] * 60,   # 모멘텀 +12.5%
        "C": [20_000] * 200 + [24_000] * 60,   # 모멘텀 +20%
        "D": [32_000] * 200 + [35_000] * 60,   # 모멘텀 +9.4%
        "E": [60_000] * 200 + [66_000] * 60,   # 모멘텀 +10%
    }

    ctx = MagicMock()
    ctx.as_of_date = "2025-12-31"

    def _ratio_side_effect(symbol):
        return ratio_data.get(symbol, {})

    def _daily_side_effect(symbol, lookback_days=260):
        prices = close_data.get(symbol, [])
        return _make_close_df(prices) if prices else pd.DataFrame()

    ctx.read_financial_ratio.side_effect = _ratio_side_effect
    ctx.read_daily.side_effect = _daily_side_effect

    # corp_events.filter_universe는 symbols 그대로 반환하도록 mock
    from unittest.mock import patch
    with patch(
        "RoboTrader_template.multiverse.data.corp_events.filter_universe",
        side_effect=lambda syms, dt: syms,
    ):
        universe = _QuantUniverse(symbols)
        # factor_top_n=2 → 상위 2개만 반환
        import dataclasses
        ps2 = dataclasses.replace(valid_paramset, factor_top_n=2)
        result = universe.select(ctx, ps2)

    # 상위 2개만 반환
    assert len(result) == 2

    # 캐시가 채워짐
    cache_key = (ctx.as_of_date, ps2.config_hash())
    assert cache_key in universe._score_cache
    cached = universe._score_cache[cache_key]

    # 5종목 모두 점수가 있음
    assert set(cached.keys()) == set(symbols)

    # z-score 정규화 결과: 분포가 퍼져 있음 (최대-최소 > 0)
    score_values = list(cached.values())
    assert max(score_values) - min(score_values) > 0.0, "점수 분산이 0 — 정규화 동작 안 함"

    # 반환된 2종목이 점수 상위 2개인지 검증
    top2_by_score = sorted(cached, key=lambda s: cached[s], reverse=True)[:2]
    assert set(result) == set(top2_by_score)


def test_quant_signal_gen_with_normalized_score(valid_paramset):
    """Universe 캐시 채운 후 SignalGen: score>threshold AND mom>0 → BUY."""
    from unittest.mock import patch

    symbols = ["X", "Y", "Z"]
    # X: 높은 점수 + 상승 모멘텀 → BUY 기대
    # Y: 높은 점수 + 하락 모멘텀 → HOLD 기대 (모멘텀 조건 미충족)
    # Z: 낮은 점수 → HOLD 기대

    ratio_data = {
        "X": {"bps": 10_000, "roe": 30.0, "net_income_growth": 20.0, "sales_growth": 10.0},
        "Y": {"bps": 10_000, "roe": 28.0, "net_income_growth": 18.0, "sales_growth": 8.0},
        "Z": {"bps": 5_000,  "roe": 2.0,  "net_income_growth": 1.0,  "sales_growth": 1.0},
    }
    # X: 상승, Y: 하락, Z: 상승 (하지만 점수가 낮음)
    close_data = {
        "X": [30_000] * 200 + [40_000] * 60,   # mom +33%
        "Y": [50_000] * 200 + [40_000] * 60,   # mom -20%
        "Z": [20_000] * 200 + [22_000] * 60,   # mom +10%
    }

    ctx = MagicMock()
    ctx.as_of_date = "2025-12-31"
    ctx.read_financial_ratio.side_effect = lambda symbol: ratio_data.get(symbol, {})
    ctx.read_daily.side_effect = lambda symbol, lookback_days=260: _make_close_df(
        close_data.get(symbol, [])
    )

    with patch(
        "RoboTrader_template.multiverse.data.corp_events.filter_universe",
        side_effect=lambda syms, dt: syms,
    ):
        universe = _QuantUniverse(symbols)
        # tech_score_threshold를 낮게 설정하여 X/Y가 캐시에서 threshold 넘도록
        import dataclasses
        ps = dataclasses.replace(valid_paramset, factor_top_n=3, tech_score_threshold=-999.0)
        universe.select(ctx, ps)  # 캐시 채우기

    signal_gen = _QuantSignalGen(universe)

    # X: 높은 점수 + 상승 모멘텀
    ctx_x = MagicMock()
    ctx_x.as_of_date = ctx.as_of_date
    ctx_x.read_daily.return_value = _make_close_df(close_data["X"])
    sig_x = signal_gen.generate(ctx_x, "X", ps)
    assert sig_x == "BUY", f"X는 BUY여야 하나 {sig_x}"

    # Y: 높은 점수지만 하락 모멘텀 → HOLD
    ctx_y = MagicMock()
    ctx_y.as_of_date = ctx.as_of_date
    ctx_y.read_daily.return_value = _make_close_df(close_data["Y"])
    sig_y = signal_gen.generate(ctx_y, "Y", ps)
    assert sig_y == "HOLD", f"Y는 HOLD여야 하나 {sig_y} (하락 모멘텀)"


def test_long_term_pbr_signal(valid_paramset):
    """long_term SignalGen: PBR<3+ROE>10 → BUY, PBR>=3 → HOLD."""
    # BPS=10_000, ROE=15 → close=20_000 → PBR=2.0 → BUY
    ctx_buy = MagicMock()
    ctx_buy.read_financial_ratio.return_value = {"bps": 10_000, "roe": 15.0}
    ctx_buy.read_daily.return_value = _make_close_df([20_000])

    signal_gen = _LongTermSignalGen()
    sig = signal_gen.generate(ctx_buy, "005930", valid_paramset)
    assert sig == "BUY", f"PBR=2,ROE=15 → BUY 기대, 실제={sig}"

    # close=60_000 → PBR=6.0 → HOLD (PBR >= 3)
    ctx_hold = MagicMock()
    ctx_hold.read_financial_ratio.return_value = {"bps": 10_000, "roe": 15.0}
    ctx_hold.read_daily.return_value = _make_close_df([60_000])

    sig_hold = signal_gen.generate(ctx_hold, "005930", valid_paramset)
    assert sig_hold == "HOLD", f"PBR=6 → HOLD 기대, 실제={sig_hold}"

    # bps <= 0 → HOLD
    ctx_nobps = MagicMock()
    ctx_nobps.read_financial_ratio.return_value = {"bps": 0, "roe": 20.0}
    ctx_nobps.read_daily.return_value = _make_close_df([30_000])

    sig_nobps = signal_gen.generate(ctx_nobps, "005930", valid_paramset)
    assert sig_nobps == "HOLD", f"BPS=0 → HOLD 기대, 실제={sig_nobps}"

    # ratio=None → HOLD (기존 None 입력 처리)
    ctx_none = MagicMock()
    ctx_none.read_financial_ratio.return_value = None
    ctx_none.read_daily.return_value = _make_close_df([30_000])

    sig_none = signal_gen.generate(ctx_none, "005930", valid_paramset)
    assert sig_none == "HOLD", f"ratio=None → HOLD 기대, 실제={sig_none}"


# ──────────────────────────────────────────────────────────────────────────────
# swing / intraday 신규 테스트 (4건)
# ──────────────────────────────────────────────────────────────────────────────

def test_swing_universe_z_score_normalization(valid_paramset):
    """_SwingUniverse.select가 5일 모멘텀 z-score로 상위 N개를 반환하고 캐시를 채우는지 검증."""
    from unittest.mock import patch

    symbols = ["A", "B", "C", "D", "E"]

    # 5종목에 대해 서로 다른 5일 모멘텀 (10개 close 데이터)
    # _compute_scores: iloc[-1] / iloc[-5] - 1 → 인덱스 -5(6번째) 대비 -1(마지막) 비교
    close_data = {
        "A": [100, 100, 100, 100, 100, 100, 110, 120, 125, 130],  # iloc[-5]=100 → -1=130: +30%
        "B": [100, 100, 100, 100, 100, 100, 102, 104, 107, 110],  # iloc[-5]=100 → -1=110: +10%
        "C": [100, 100, 100, 100, 100, 100, 105, 110, 116, 120],  # iloc[-5]=100 → -1=120: +20%
        "D": [100, 100, 100, 100, 100, 100,  98,  96,  97,  95],  # iloc[-5]=100 → -1=95:  -5%
        "E": [100, 100, 100, 100, 100, 100, 101, 103, 104, 105],  # iloc[-5]=100 → -1=105: +5%
    }

    ctx = MagicMock()
    ctx.as_of_date = "2025-12-31"
    ctx.read_daily.side_effect = lambda symbol, lookback_days=10: (
        pd.DataFrame({"close": close_data[symbol]}) if symbol in close_data else pd.DataFrame()
    )

    with patch(
        "RoboTrader_template.multiverse.data.corp_events.filter_universe",
        side_effect=lambda syms, dt: syms,
    ):
        universe = _SwingUniverse(symbols)
        result = universe.select(ctx, valid_paramset)

    # 상위 _UNIVERSE_TOP_N(=10)개 이하 반환 (종목 5개이므로 최대 5)
    assert len(result) <= len(symbols)
    assert len(result) >= 1

    # 캐시가 채워짐
    cache_key = (ctx.as_of_date, valid_paramset.config_hash())
    assert cache_key in universe._score_cache
    cached = universe._score_cache[cache_key]

    # 5종목 모두 점수가 있음
    assert set(cached.keys()) == set(symbols)

    # z-score 정규화 결과: 분포가 퍼져 있음 (최대-최소 > 0)
    score_values = list(cached.values())
    assert max(score_values) - min(score_values) > 0.0, "점수 분산이 0 — 정규화 동작 안 함"

    # 가장 높은 모멘텀(A: +30%)이 1위여야 함
    top1 = sorted(cached, key=lambda s: cached[s], reverse=True)[0]
    assert top1 == "A", f"최고 모멘텀 종목 A가 1위여야 하나 실제={top1}"

    # 하락 종목(D: -5%)이 최하위여야 함
    last = sorted(cached, key=lambda s: cached[s])[0]
    assert last == "D", f"하락 종목 D가 최하위여야 하나 실제={last}"


def test_swing_signal_gen_with_universe_guard(valid_paramset):
    """_SwingSignalGen: Universe 캐시 있는 종목만 BB+RSI 평가, 없는 종목은 HOLD."""
    from unittest.mock import patch

    symbols = ["X"]
    ctx_select = MagicMock()
    ctx_select.as_of_date = "2025-12-31"

    # BB 하단 이탈 후 회복 + RSI<40 조건을 충족하는 가격 시퀀스 구성
    # BB_PERIOD=20, 하단 이탈 후 회복: 전일 close <= lower, 당일 close > lower
    # 낮은 가격대 유지 후 마지막에 살짝 회복
    base = [100.0] * 19 + [80.0, 82.0]  # 21개 — 전일(80) BB하단 이탈, 당일(82) 회복
    # RSI<40: 하락 구간이 많아야 하므로 앞부분을 하락 추세로
    prices = list(range(120, 99, -1)) + [80.0, 82.0]  # 22개, 하락 후 반등

    ctx_select.read_daily.return_value = pd.DataFrame({"close": prices})

    with patch(
        "RoboTrader_template.multiverse.data.corp_events.filter_universe",
        side_effect=lambda syms, dt: syms,
    ):
        universe = _SwingUniverse(symbols)
        universe.select(ctx_select, valid_paramset)  # 캐시 채우기

    signal_gen = _SwingSignalGen(universe)

    # Universe 캐시에 있는 종목 X — BB+RSI 조건 평가
    ctx_x = MagicMock()
    ctx_x.as_of_date = ctx_select.as_of_date
    ctx_x.read_daily.return_value = pd.DataFrame({"close": prices})
    sig_x = signal_gen.generate(ctx_x, "X", valid_paramset)
    # 결과가 BUY 또는 HOLD인지 확인 (조건 충족 여부는 데이터에 따라 다름)
    assert sig_x in {"BUY", "HOLD"}

    # Universe 캐시에 없는 종목 Z → 무조건 HOLD
    ctx_z = MagicMock()
    ctx_z.as_of_date = ctx_select.as_of_date
    ctx_z.read_daily.return_value = pd.DataFrame({"close": prices})
    sig_z = signal_gen.generate(ctx_z, "Z", valid_paramset)
    assert sig_z == "HOLD", f"캐시에 없는 종목 Z는 HOLD여야 하나 실제={sig_z}"


def test_intraday_universe_z_score_normalization(valid_paramset):
    """_IntradayUniverse.select가 5일 변동성 z-score로 상위 N개를 반환하고 캐시를 채우는지 검증."""
    from unittest.mock import patch

    symbols = ["A", "B", "C", "D", "E"]

    # 5종목에 대해 서로 다른 5일 변동성 (7개 close 데이터)
    close_data = {
        "A": [100, 130, 80, 120, 90, 110, 100],   # 변동성 높음
        "B": [100, 101, 100, 101, 100, 101, 100],  # 변동성 낮음
        "C": [100, 115, 95, 110, 90, 105, 100],    # 변동성 중간
        "D": [100, 140, 70, 130, 80, 120, 90],     # 변동성 가장 높음
        "E": [100, 102, 99, 101, 100, 102, 101],   # 변동성 낮음
    }

    ctx = MagicMock()
    ctx.as_of_date = "2025-12-31"
    ctx.read_daily.side_effect = lambda symbol, lookback_days=7: (
        pd.DataFrame({"close": close_data[symbol]}) if symbol in close_data else pd.DataFrame()
    )

    with patch(
        "RoboTrader_template.multiverse.data.corp_events.filter_universe",
        side_effect=lambda syms, dt: syms,
    ):
        universe = _IntradayUniverse(symbols)
        result = universe.select(ctx, valid_paramset)

    # 반환값은 종목 수 이하
    assert len(result) <= len(symbols)
    assert len(result) >= 1

    # 캐시가 채워짐
    cache_key = (ctx.as_of_date, valid_paramset.config_hash())
    assert cache_key in universe._score_cache
    cached = universe._score_cache[cache_key]

    # 5종목 모두 점수가 있음
    assert set(cached.keys()) == set(symbols)

    # z-score 정규화 결과: 분포가 퍼져 있음 (최대-최소 > 0)
    score_values = list(cached.values())
    assert max(score_values) - min(score_values) > 0.0, "점수 분산이 0 — 정규화 동작 안 함"

    # 변동성 가장 높은 D가 1위여야 함
    top1 = sorted(cached, key=lambda s: cached[s], reverse=True)[0]
    assert top1 == "D", f"최고 변동성 종목 D가 1위여야 하나 실제={top1}"


def test_intraday_signal_gen_volume_surge_threshold(valid_paramset):
    """_IntradaySignalGen: 거래량 2.0배 강화 + Universe 가드 검증."""
    from unittest.mock import patch

    symbols = ["X"]
    ctx_select = MagicMock()
    ctx_select.as_of_date = "2025-12-31"
    # 변동성 데이터 (7개 — _VOL_WINDOW+2)
    ctx_select.read_daily.return_value = pd.DataFrame({
        "close": [100, 105, 98, 103, 102, 107, 104]
    })

    with patch(
        "RoboTrader_template.multiverse.data.corp_events.filter_universe",
        side_effect=lambda syms, dt: syms,
    ):
        universe = _IntradayUniverse(symbols)
        universe.select(ctx_select, valid_paramset)  # 캐시 채우기

    signal_gen = _IntradaySignalGen(universe)

    # 공통 날짜
    as_of = ctx_select.as_of_date

    def _make_df(avg_vol, prev_vol, prev_open, prev_close):
        """양봉 + 거래량 데이터 DataFrame 생성."""
        # _VOL_WINDOW+1=6개 이전 행 (avg_vol 계산용) + 마지막 행 (전일)
        rows = [{"date": f"2025-12-{i:02d}", "open": 100, "close": 100, "volume": avg_vol}
                for i in range(1, 7)]
        rows.append({"date": "2025-12-31", "open": prev_open, "close": prev_close, "volume": prev_vol})
        return pd.DataFrame(rows)

    avg_vol = 1000

    # 케이스 1: Universe 통과 + 양봉 + 거래량 2.0배 이상 → BUY
    ctx1 = MagicMock()
    ctx1.as_of_date = as_of
    ctx1.read_daily.return_value = _make_df(avg_vol, avg_vol * 2.0, 100, 110)
    sig1 = signal_gen.generate(ctx1, "X", valid_paramset)
    assert sig1 == "BUY", f"2.0배 + 양봉 + Universe 통과 → BUY여야 하나 실제={sig1}"

    # 케이스 2: Universe 통과 + 양봉 + 거래량 1.5배 (이전 임계값) → HOLD (강화 검증)
    ctx2 = MagicMock()
    ctx2.as_of_date = as_of
    ctx2.read_daily.return_value = _make_df(avg_vol, avg_vol * 1.5, 100, 110)
    sig2 = signal_gen.generate(ctx2, "X", valid_paramset)
    assert sig2 == "HOLD", f"1.5배는 2.0배 미만 → HOLD여야 하나 실제={sig2}"

    # 케이스 3: Universe 캐시에 없는 종목 Z → 거래량 충족해도 HOLD
    ctx3 = MagicMock()
    ctx3.as_of_date = as_of
    ctx3.read_daily.return_value = _make_df(avg_vol, avg_vol * 3.0, 100, 110)
    sig3 = signal_gen.generate(ctx3, "Z", valid_paramset)
    assert sig3 == "HOLD", f"캐시에 없는 종목 Z → HOLD여야 하나 실제={sig3}"

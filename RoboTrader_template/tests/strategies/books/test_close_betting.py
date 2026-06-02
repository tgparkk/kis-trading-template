"""종가배팅(close_betting) 일봉 룰 테스트 — TDD.

태쏘 『데이트레이딩 바이블 2』 기법 B 코드화.
셋업: D0 장대양봉(+7~25%, 거래대금≥300억, 시세초입) → D1 단봉조정(변동폭≤7%,
거래량<D0의 30%, [D0의 1/2가격~D0종가] 위치) → D1종가 진입(백테스터 다음봉 시가).

no-lookahead 엄수: evaluate 는 df 마지막 행(t=D1)까지만 사용, D0=직전봉.
"""

import pandas as pd
import pytest

from backtest.book_backtester import BookBacktester
from strategies.books.close_betting.rules import (
    ALL_RULES,
    rule_close_betting_setup,
)
from strategies.books.close_betting.strategy import build_strategy


# ---------------------------------------------------------------------------
# toy df 빌더
# ---------------------------------------------------------------------------

def _row(o, h, l, c, v, dt):
    return {"datetime": dt, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _base_df(n_warmup: int = 30):
    """평탄한 박스권 워밍업 봉 + 시세초입 돌파를 위한 낮은 전고점.

    종가·고가 모두 ~100 근방의 좁은 박스 → D0 장대양봉이 전고점을 돌파하도록.
    """
    rows = []
    dt = pd.Timestamp("2026-01-01")
    for i in range(n_warmup):
        rows.append(_row(100.0, 101.0, 99.0, 100.0, 100_000_000, dt))
        dt += pd.Timedelta(days=1)
    return rows, dt


def _make_setup_df():
    """적격 셋업: 박스권 → D0 장대양봉(+15%, 전고점돌파, 큰 거래대금)
    → D1 단봉(변동폭 작음, 거래량 급감, D0 몸통 안쪽 위치).
    """
    rows, dt = _base_df()
    # D0 장대양봉: open 100 -> close 115 (+15%), high 116, 거래대금 345억(>=300억)
    d0_close = 115.0
    rows.append(_row(100.0, 116.0, 99.5, d0_close, 300_000_000, dt))
    dt += pd.Timedelta(days=1)
    # D1 단봉(신호일): D0 중간값(=(100+115)/2=107.5)~D0종가(115) 사이.
    # 변동폭 작게(high-low)/prev_close 작게, 거래량 D0의 30% 미만(50M/300M=16.7%).
    rows.append(_row(112.0, 113.0, 110.0, 112.5, 50_000_000, dt))  # range=3/115=2.6%
    return pd.DataFrame(rows)


def _df_from_d1(d1):
    """공통 베이스 + D0 양봉 + 주어진 D1 봉으로 df 구성."""
    rows, dt = _base_df()
    rows.append(_row(100.0, 116.0, 99.5, 115.0, 300_000_000, dt))  # D0 거래대금 345억
    dt += pd.Timedelta(days=1)
    d1 = dict(d1)
    d1["datetime"] = dt
    rows.append(d1)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. 양성 케이스 — triggered=True
# ---------------------------------------------------------------------------

def test_setup_triggers_buy():
    rule = rule_close_betting_setup()
    df = _make_setup_df()
    res = rule.evaluate(df, {})
    assert res.triggered is True
    assert res.side == "buy"
    # 단봉저점이 metadata 에 기록되어야 한다(손절 표현용).
    assert "d1_low" in res.metadata
    assert res.metadata["d1_low"] == pytest.approx(110.0)


# ---------------------------------------------------------------------------
# 2. 음성 케이스 (no-lookahead, 조건 이탈)
# ---------------------------------------------------------------------------

def test_no_d0_long_bullish_rejected():
    """D0 가 장대양봉이 아니면(상승률 부족) 거부."""
    rows, dt = _base_df()
    rows.append(_row(100.0, 103.0, 99.5, 102.0, 5_000_000, dt))  # +2% only
    dt += pd.Timedelta(days=1)
    rows.append(_row(101.0, 101.5, 100.0, 100.5, 1_000_000, dt))
    df = pd.DataFrame(rows)
    assert rule_close_betting_setup().evaluate(df, {}).triggered is False


def test_volume_not_dried_up_rejected():
    """D1 거래량이 D0 대비 충분히 급감하지 않으면 거부."""
    df = _df_from_d1(_row(112.0, 113.0, 110.0, 112.5, 240_000_000, None))  # 80% of D0 (not dried up)
    assert rule_close_betting_setup().evaluate(df, {}).triggered is False


def test_range_too_wide_rejected():
    """D1 일중 변동폭이 너무 크면(단봉 아님) 거부."""
    df = _df_from_d1(_row(112.0, 120.0, 105.0, 112.5, 1_000_000, None))  # range=15/115=13%
    assert rule_close_betting_setup().evaluate(df, {}).triggered is False


def test_position_below_midpoint_rejected():
    """D1 저가가 D0 중간값(107.5) 아래로 이탈하면 거부."""
    df = _df_from_d1(_row(106.0, 107.0, 104.0, 105.0, 1_000_000, None))  # low 104 < 107.5
    assert rule_close_betting_setup().evaluate(df, {}).triggered is False


def test_close_above_d0_close_rejected():
    """D1 종가가 D0 종가(115)를 초과하면(조정 아님) 거부."""
    df = _df_from_d1(_row(115.5, 117.0, 114.0, 116.5, 1_000_000, None))  # close 116.5 > 115
    assert rule_close_betting_setup().evaluate(df, {}).triggered is False


def test_d0_body_too_large_rejected():
    """D0 상승률이 body_max(25%) 초과면 거부(추격 위험)."""
    rows, dt = _base_df()
    rows.append(_row(100.0, 140.0, 99.5, 135.0, 300_000_000, dt))  # +35% (turnover OK, body 초과로 거부)
    dt += pd.Timedelta(days=1)
    # D1 단봉: 중간값=(100+135)/2=117.5 ~ 135 사이
    rows.append(_row(125.0, 126.0, 123.0, 124.0, 50_000_000, dt))
    df = pd.DataFrame(rows)
    assert rule_close_betting_setup().evaluate(df, {}).triggered is False


def test_low_turnover_rejected():
    """D0 거래대금(close*volume)이 turnover_min 미만이면 거부."""
    rows, dt = _base_df()
    rows.append(_row(100.0, 116.0, 99.5, 115.0, 10_000, dt))  # 115*10000=1.15M << 300억
    dt += pd.Timedelta(days=1)
    rows.append(_row(112.0, 113.0, 110.0, 112.5, 2_000, dt))
    df = pd.DataFrame(rows)
    assert rule_close_betting_setup().evaluate(df, {}).triggered is False


def test_insufficient_data_returns_false():
    """워밍업 미만 데이터는 거부(no-lookahead·인덱스 가드)."""
    df = pd.DataFrame([_row(100, 101, 99, 100, 1000, pd.Timestamp("2026-01-01"))])
    assert rule_close_betting_setup().evaluate(df, {}).triggered is False


# ---------------------------------------------------------------------------
# 3. BookBacktester 통합 — 거래 1건 이상
# ---------------------------------------------------------------------------

def test_backtester_books_a_trade():
    """셋업 시퀀스 뒤에 익절 가능한 상승봉을 붙여 거래 1건 발생 확인.

    진입 = D1 신호의 다음봉 시가(≈익일 오전). max_hold_bars=1, tp=0.03.
    """
    df = _make_setup_df()
    # D1 다음봉(진입 체결봉) + 익일 익절 도달봉을 추가.
    last_dt = df["datetime"].iloc[-1]
    extra = [
        # 진입 체결봉: 시가 112.5 근방
        _row(112.5, 114.0, 111.0, 113.0, 1_500_000, last_dt + pd.Timedelta(days=1)),
        # 익절 도달봉: +3% 이상
        _row(116.0, 120.0, 115.5, 119.0, 2_000_000, last_dt + pd.Timedelta(days=2)),
        _row(119.0, 121.0, 118.0, 120.0, 1_000_000, last_dt + pd.Timedelta(days=3)),
    ]
    df = pd.concat([df, pd.DataFrame(extra)], ignore_index=True)

    strat = build_strategy(mode="single", target_rule="close_betting_setup")
    bt = BookBacktester(
        strategy=strat,
        initial_capital=1_000_000,
        warmup_bars=30,
        stop_loss_pct=0.02,
        take_profit_pct=0.03,
        max_hold_bars=1,
        eod_liquidate=True,
    )
    result = bt.run_single(stock_code="005930", df=df)
    assert result.n_trades >= 1
    assert any(t["side"] == "buy" for t in result.trades)


# ---------------------------------------------------------------------------
# 4. 모듈 구성 sanity
# ---------------------------------------------------------------------------

def test_all_rules_registered():
    names = [cls().name for cls in ALL_RULES]
    assert "close_betting_setup" in names


def test_build_strategy_loads():
    strat = build_strategy(mode="single", target_rule="close_betting_setup")
    assert strat.target_rule == "close_betting_setup"

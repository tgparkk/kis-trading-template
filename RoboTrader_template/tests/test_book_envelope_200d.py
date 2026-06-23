"""book_envelope_200d 라이브 전략 — 백테스트 룰 1:1 동등성 + 청산 + 어댑터 배선.

Book19 envelope_200d_high (200일 신고가+Envelope 돌파). OOS 홀드아웃 train 1.20/test 1.82
강건 확인 후 6번째 페이퍼 전략으로 추가. 진입 평가는 200봉 필요 → quant(QuantDailyReader) 일봉 사용.
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_evaluate_entry_matches_backtest_rule():
    """evaluate_entry 는 백테스트 rule_envelope_200d_high 와 1:1 동등(실제 quant 일봉)."""
    from db.quant_daily_reader import QuantDailyReader
    from strategies.books.trading_strategy_book.rules import rule_envelope_200d_high
    from strategies.book_envelope_200d.strategy import BookEnvelope200dStrategy

    qr = QuantDailyReader()
    df = qr.get_daily_prices("005930", end_date=dt.date(2025, 12, 30), days=260)
    assert len(df) >= 202, "테스트 전제: 260일 요청 시 200+봉"
    df = df.assign(datetime=df["date"])  # 조건E(이등분선) today_mask 용
    rule_res = rule_envelope_200d_high().evaluate(df, {})
    trig, reasons, meta = BookEnvelope200dStrategy.evaluate_entry(df)
    assert trig == rule_res.triggered


def test_evaluate_sell_priority_sl_tp_mh():
    """청산 우선순위 sl → tp → max_hold (trailing 없음)."""
    from strategies.book_envelope_200d.strategy import BookEnvelope200dStrategy

    def df_at(close):
        return pd.DataFrame({"open": [close] * 5, "high": [close] * 5,
                             "low": [close] * 5, "close": [close] * 5,
                             "volume": [1000] * 5})

    # 손절: -8%
    s, _, r = BookEnvelope200dStrategy.evaluate_sell_conditions(
        df_at(92.0), entry_price=100.0, hold_days=1,
        take_profit_pct=0.10, stop_loss_pct=0.08, max_hold_days=10)
    assert s and r == "stop_loss"
    # 익절: +10%
    s, _, r = BookEnvelope200dStrategy.evaluate_sell_conditions(
        df_at(110.0), entry_price=100.0, hold_days=1,
        take_profit_pct=0.10, stop_loss_pct=0.08, max_hold_days=10)
    assert s and r == "take_profit"
    # 최대보유: 10거래일
    s, _, r = BookEnvelope200dStrategy.evaluate_sell_conditions(
        df_at(103.0), entry_price=100.0, hold_days=10,
        take_profit_pct=0.10, stop_loss_pct=0.08, max_hold_days=10)
    assert s and r == "max_hold"
    # 보유 지속
    s, _, r = BookEnvelope200dStrategy.evaluate_sell_conditions(
        df_at(103.0), entry_price=100.0, hold_days=3,
        take_profit_pct=0.10, stop_loss_pct=0.08, max_hold_days=10)
    assert not s


def test_build_adapter_envelope_registered():
    """build_adapter 에 book_envelope_200d 등록됨 + RuleScreenerBase(quant) 사용."""
    from runners._adapter_factory import build_adapter

    a = build_adapter("book_envelope_200d")
    assert a is not None
    assert a.strategy_name == "book_envelope_200d"
    assert a.lookback_days >= 202, "200일 신고가 평가에 200+봉 필요"


def test_strategy_class_importable_and_swing():
    from strategies.book_envelope_200d.strategy import BookEnvelope200dStrategy
    assert BookEnvelope200dStrategy.holding_period == "swing"


def test_exit_timeframe_daily():
    # 일봉 swing 전략 — 분봉 청산 whipsaw 방지 (2026-06-18 점검). intraday 상속 회귀 방지.
    from strategies.book_envelope_200d.strategy import BookEnvelope200dStrategy
    assert BookEnvelope200dStrategy.exit_timeframe == "daily"


def test_min_gate_small_so_ontick_not_skipped():
    """on_tick 게이트는 전달 일봉(robotrader ~85봉)에 적용 → 작아야 함.

    get_min_data_length 가 200+ 이면 on_tick(`len(ctx data) < min_len → skip`)이
    envelope 을 항상 스킵해 영영 미발사한다. 진입 200봉 요구는 evaluate_entry 내부에서 강제.
    """
    from strategies.config import StrategyLoader
    from strategies.book_envelope_200d.strategy import BookEnvelope200dStrategy

    s = StrategyLoader.load_strategy("book_envelope_200d")
    assert s.get_min_data_length() <= 85, "게이트가 ctx 일봉(~85봉)보다 크면 on_tick 항상 스킵"
    # 짧은 df 는 진입 평가에서 거부(200봉 내부 검증 유지)
    short = pd.DataFrame({c: [1.0] * 50 for c in ["open", "high", "low", "close", "volume"]})
    trig, _, _ = BookEnvelope200dStrategy.evaluate_entry(short)
    assert trig is False


def test_entry_band_wired_breakout(monkeypatch):
    """_check_buy 가 돌파형 밴드(up=3%, down=None)를 Signal 에 담는다."""
    from strategies.book_envelope_200d.strategy import BookEnvelope200dStrategy
    from strategies.base import SignalType

    monkeypatch.setattr(
        "strategies.book_envelope_200d.strategy.MarketHours.is_market_open",
        staticmethod(lambda market="KRX": True),
    )

    REF = 10000.0
    # 최소 봉 수(202)를 충족하는 fake_df — close 전부 REF
    n = 210
    fake_df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": [REF] * n, "high": [REF] * n, "low": [REF] * n,
        "close": [REF] * n, "volume": [1000] * n,
    })

    # _fetch_entry_history 가 fake_df 를 반환하도록 패치
    monkeypatch.setattr(
        BookEnvelope200dStrategy, "_fetch_entry_history",
        lambda self, code: fake_df,
    )
    # evaluate_entry 를 항상 True 로 패치 (룰 계산 불필요)
    monkeypatch.setattr(
        BookEnvelope200dStrategy, "evaluate_entry",
        staticmethod(lambda df, **kw: (True, ["test_rule"], {})),
    )

    strat = BookEnvelope200dStrategy({
        "parameters": {"min_gate_bars": 5, "min_daily_bars": 202, "entry_lookback_bars": 210},
        "risk_management": {"take_profit_pct": 0.10, "stop_loss_pct": 0.08,
                            "max_hold_days": 10},
        "paper_trading": False,
    })
    strat.on_init(None, None, None)

    sig = strat._check_buy("005930", fake_df)
    assert sig is not None
    assert sig.signal_type == SignalType.BUY
    # breakout: max = ref * 1.03, min = None
    assert sig.entry_max_price == pytest.approx(REF * 1.03)
    assert sig.entry_min_price is None


def test_fetch_entry_history_drops_today_bar_no_lookahead():
    """_fetch_entry_history 가 당일(KST) 미확정 봉을 제거해 iloc[-1]=확정봉이 되는지.
    look-ahead 보증이 이 단일 가드에 의존하므로 회귀 테스트로 고정(감사 2026-06-23).
    당일 봉이 남으면 '당일 +3% 양봉/신고가' 조건이 미정산 종가를 읽는 hard look-ahead."""
    import logging
    from strategies.book_envelope_200d.strategy import BookEnvelope200dStrategy
    from utils.korean_time import now_kst

    today = now_kst().date()
    dates = pd.to_datetime([today - dt.timedelta(days=2),
                            today - dt.timedelta(days=1), today])
    df = pd.DataFrame({"date": dates, "open": [1.0, 1.0, 1.0],
                       "high": [1.0, 1.0, 1.0], "low": [1.0, 1.0, 1.0],
                       "close": [1.0, 1.0, 9.0], "volume": [1, 1, 1]})

    class _Stub:
        def get_daily_prices(self, code, end_date=None, days=None):
            return df.copy()

    s = object.__new__(BookEnvelope200dStrategy)  # __init__ 우회
    s._entry_df_cache = {}
    s._entry_lookback = 210
    s.logger = logging.getLogger("test_envelope")
    s._quant_reader = lambda: _Stub()

    out = s._fetch_entry_history("005930")
    assert out is not None and len(out) == 2          # 당일봉 1개 제거
    assert pd.to_datetime(out["date"].iloc[-1]).date() < today  # 마지막=확정봉

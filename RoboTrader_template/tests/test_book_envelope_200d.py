"""book_envelope_200d 라이브 전략 — 백테스트 룰 1:1 동등성 + 청산 + 어댑터 배선.

Book19 envelope_200d_high (200일 신고가+Envelope 돌파). OOS 홀드아웃 train 1.20/test 1.82
강건 확인 후 6번째 페이퍼 전략으로 추가. 진입 평가는 200봉 필요 → quant(QuantDailyReader) 일봉 사용.
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

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

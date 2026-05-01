"""Phase 1 PIT 가드 — pit_reader가 미래 데이터 노출을 모두 차단."""
import pytest
from datetime import date, time
from RoboTrader_template.multiverse.data import pit_reader


def test_read_daily_requires_as_of_date():
    """as_of_date 미입력 시 TypeError raise."""
    with pytest.raises(TypeError):
        pit_reader.read_daily(symbol="005930")  # as_of_date 누락


def test_read_daily_excludes_as_of_date_close():
    """as_of_date 당일 종가는 절대 반환 금지."""
    df = pit_reader.read_daily(symbol="005930", as_of_date=date(2026, 4, 1))
    if not df.empty:
        assert df["date"].max() < date(2026, 4, 1)


def test_read_minute_respects_as_of_time():
    """as_of_time 직전 분봉까지만."""
    df = pit_reader.read_minute(
        symbol="005930", as_of_date=date(2026, 4, 1), as_of_time=time(9, 1)
    )
    if not df.empty:
        latest = df.iloc[-1]
        # 09:00 분봉까지 OK, 09:01은 금지
        assert (latest["date"] < date(2026, 4, 1)) or (
            latest["date"] == date(2026, 4, 1) and latest["time"] < time(9, 1)
        )


def test_read_financial_ratio_applies_disclosure_lag():
    """공시 lag 60일 적용."""
    ratio = pit_reader.read_financial_ratio(
        symbol="005930", as_of_date=date(2026, 4, 1)
    )
    # 데이터 없으면 None OK. 있으면 60일 이전 공시분.
    if ratio is not None:
        assert "disclosure_date" not in ratio or \
               ratio["disclosure_date"] <= date(2026, 4, 1).replace(month=2, day=1)

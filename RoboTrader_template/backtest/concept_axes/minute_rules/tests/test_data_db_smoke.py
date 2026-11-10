"""실제 DB 스모크 1개(SELECT 만) — code-day 10개 적재 · 가드 플래그 형태만 본다(가격·수익률 계산 없음)."""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from backtest.concept_axes.minute_rules import data as D
from backtest.concept_axes.minute_rules import engine as E

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def conn():
    try:
        c = D.connect()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"DB 접속 불가: {e}")
    yield c
    c.close()


def test_load_ten_code_days_guard_flags(conn):
    cal = D.load_calendar(conn, date(2026, 9, 1), date(2026, 11, 10))
    day = cal[-2]
    codes = [r[0] for r in D._fetch(conn, "SELECT DISTINCT stock_code FROM minute_candles WHERE trade_date = %s "
                                          "ORDER BY stock_code LIMIT 10", (day.strftime("%Y%m%d"),))]
    assert len(codes) == 10
    phantom = ("005930", date(2025, 10, 6))                   # EXPERT_SYSTEM Q3 유령일
    b = D.load_minute_days(conn, [(c, day) for c in codes] + [phantom], D.load_market_of(conn), calendar=None)
    assert b.excluded.get(phantom) == D.EXCL_PHANTOM
    assert len(b.keys) + sum(1 for k in b.excluded if k != phantom) == 10
    assert b.bars.dtype == np.float32 and b.bars.shape == (len(b.keys), E.N_SLOTS, E.N_FIELDS)
    assert set(b.checksums) == set(b.keys)
    for m in b.meta:
        assert isinstance(m.has_1530, bool) and isinstance(m.market_gap_day, bool)
        assert isinstance(m.long_gap, bool) and isinstance(m.open_gap_flag, bool)
        assert m.filled_minutes >= 0 and m.n_rows > 0
        assert m.prev_day_volume is None or m.prev_day_volume >= 0


def test_market_gap_1106_kospi_event_from_db(conn):
    """G5 형태 검사(가격·수익률 아님) — 11-06 KOSPI 장중 공백 = 시장 사건 · KOSDAQ·10-13 = 아님(초안 G5 · [Y]:26)."""
    mk = D.load_market_of(conn)
    stats = D.market_gap_stats(D.fetch_market_gap_rows(conn, [date(2026, 11, 6), date(2026, 10, 13)]), mk)
    flags = {g: k >= D.MARKET_GAP_FRAC * n for g, (k, n) in stats.items()}
    assert flags[(date(2026, 11, 6), "KOSPI")] is True
    assert flags[(date(2026, 11, 6), "KOSDAQ")] is False
    assert not flags[(date(2026, 10, 13), "KOSPI")] and not flags[(date(2026, 10, 13), "KOSDAQ")]

"""data — 빈 분 채움 · v0 봉 · 15:30 봉 · 0가격 · 통째 결측 · long_gap·market_gap_day · VWAP · 체크섬 · 유령일."""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from backtest.concept_axes.minute_rules import data as D
from backtest.concept_axes.minute_rules import engine as E


def _row(i, px=10000.0, vol=100.0, amt=None, t=None):
    return (t or E.idx_to_time(i), px, px, px, px, vol, amt if amt is not None else (i + 1) * vol * px)


def _full(px=10000.0):
    return [_row(i, px) for i in range(E.N_CONT)]


def test_fill_empty_minutes_flat_from_previous_close():
    rows = [_row(0, 10000), _row(1, 10100), _row(4, 10200)]   # 09:02·09:03 빈 분
    bars, obs, meta, why = D.assemble_day(rows)
    assert why == "" and bars.shape == (E.N_SLOTS, E.N_FIELDS)
    assert (bars[2, :4] == 10100).all() and bars[2, E.F_VOL] == 0 and bars[2, E.F_AMT] == rows[1][6]
    assert not obs[2] and obs[4]
    assert meta.filled_minutes == 2 + (E.N_CONT - 5)            # 09:02·09:03 + 09:05~15:19
    assert bars[E.N_CONT - 1, E.F_CLOSE] == 10200


def test_minutes_before_first_trade_have_no_price():
    bars, _, meta, _ = D.assemble_day([_row(3, 10000)] + [_row(i) for i in range(4, E.N_CONT)])
    assert np.isnan(bars[:3]).all() and meta.first_trade_idx == 3 and meta.filled_minutes == 0


def test_zero_volume_bar_is_no_trade_minute():
    rows = _full()
    rows[10] = (E.idx_to_time(10), 12000.0, 12000.0, 12000.0, 12000.0, 0.0, rows[9][6])
    bars, obs, meta, _ = D.assemble_day(rows)
    assert not obs[10] and meta.zero_volume_minutes == 1 and meta.filled_minutes == 0
    assert bars[10, E.F_CLOSE] == 10000                          # 직전 종가로 평평하게


def test_1530_bar_flag_and_off_grid_rows():
    rows = _full() + [_row(0, t="152000"), _row(0, t="153000")]
    bars, _, meta, _ = D.assemble_day(rows)
    assert meta.has_1530 and meta.off_grid_rows == 1 and bars[E.IDX_1530, E.F_CLOSE] == 10000
    bars2, _, meta2, _ = D.assemble_day(_full())
    assert not meta2.has_1530 and np.isnan(bars2[E.IDX_1530]).all()


def test_zero_price_and_whole_day_missing_excluded():
    rows = _full()
    rows[50] = (E.idx_to_time(50), 0.0, 10000.0, 0.0, 10000.0, 10.0, 1.0)
    assert D.assemble_day(rows)[3] == D.EXCL_ZERO_PRICE
    assert D.assemble_day([])[3] == D.EXCL_NO_MINUTE


def test_long_gap_info_flag_threshold():
    rows = [r for i, r in enumerate(_full()) if not 100 <= i < 120]      # 20분 공백
    m = D.assemble_day(rows)[2]
    assert m.long_gap and m.long_gap_minutes == 20 and not m.market_gap_day
    rows19 = [r for i, r in enumerate(_full()) if not 100 <= i < 119]
    assert not D.assemble_day(rows19)[2].long_gap


def _meta(code, day, gap=None):
    rows = [r for i, r in enumerate(_full()) if gap is None or not gap[0] <= i < gap[1]]
    m = D.assemble_day(rows)[2]
    m.code, m.day = code, day
    return m


def _gap_rows(td, gaps_by_code):
    """`fetch_market_gap_rows` 꼴 — (trade_date, code, [[lo, hi], …] 또는 None)."""
    return [(td, c, [list(g) for g in gs] or None) for c, gs in gaps_by_code.items()]


def test_market_gap_small_group_single_candidate_gap_is_not_market_event():
    """B2 소집단 — 후보 1종목의 21분 자기 공백은 그날 시장 전 종목(분모) 기준으로 시장 사건이 아니다."""
    d = date(2026, 10, 2)
    gaps = {"Q1": [(100, 120)]}                                     # 21분(행 100..120)
    gaps.update({f"Q{i}": [] for i in range(2, 21)})                # 같은 시장 나머지 19종목 공백 없음
    mk = {c: "KOSDAQ" for c in gaps}
    stats = D.market_gap_stats(_gap_rows("20261002", gaps), mk)
    assert stats == {(d, "KOSDAQ"): (1, 20)}
    m = _meta("Q1", d, (100, 121))
    assert m.long_gap and m.long_gap_minutes == 21
    assert D.mark_market_gap_days([m], stats, mk) == {(d, "KOSDAQ"): False} and not m.market_gap_day
    # 소집단 그 자체(그날 분봉 종목이 1개뿐)여도 분모 = 그날 전 종목 → 1/1 이면 참(번들 크기와 무관)
    assert D.market_gap_stats(_gap_rows("20261002", {"Q1": [(100, 120)]}), mk) == {(d, "KOSDAQ"): (1, 1)}


def test_market_gap_1106_kospi_shape_true_kosdaq_false():
    """11-06 꼴 — KOSPI 전 종목 09:03~09:04 부터 ≈29분 공백 · KOSDAQ 은 소수만 → KOSPI 참 · KOSDAQ 거짓."""
    d = date(2026, 11, 6)
    gaps = {f"P{i}": [(3 + i % 2, 31 + i % 3)] for i in range(10)}
    gaps.update({f"K{i}": ([(3, 33)] if i < 2 else []) for i in range(30)})
    mk = {c: ("KOSPI" if c.startswith("P") else "KOSDAQ") for c in gaps}
    stats = D.market_gap_stats(_gap_rows("20261106", gaps), mk)
    assert stats == {(d, "KOSPI"): (10, 10), (d, "KOSDAQ"): (2, 30)}
    ms = [_meta("P0", d, (3, 32)), _meta("K5", d), _meta("K0", d, (3, 34))]
    assert D.mark_market_gap_days(ms, stats, mk) == {(d, "KOSPI"): True, (d, "KOSDAQ"): False}
    assert [m.market_gap_day for m in ms] == [True, False, False]
    # 시장을 섞으면(한 군) 12/40 = 30% → 안 걸린다 — 그래서 market_of 필수
    assert D.market_gap_stats(_gap_rows("20261106", gaps), {}) == {(d, D.MARKET_UNKNOWN): (12, 40)}


def test_market_gap_unknown_market_group_always_false():
    """U1 — stock_market 에 없는 코드(UNKNOWN 군) 1종목 21분 공백 → 1/1 이어도 False(소집단 차단)."""
    d = date(2026, 10, 2)
    stats = D.market_gap_stats(_gap_rows("20261002", {"Z1": [(100, 120)]}), {})
    assert stats == {(d, D.MARKET_UNKNOWN): (1, 1)}
    m = _meta("Z1", d, (100, 121))
    assert D.mark_market_gap_days([m], stats, {}) == {(d, D.MARKET_UNKNOWN): False} and not m.market_gap_day


def test_market_gap_needs_same_window_and_market_of_required():
    d = date(2026, 11, 6)
    gaps = {"A1": [(3, 32)], "A2": [(100, 124)], "A3": []}          # 각자 공백 · 같은 창 아님 → 최대 1/3
    mk = {c: "KOSPI" for c in gaps}
    assert D.market_gap_stats(_gap_rows("20261106", gaps), mk) == {(d, "KOSPI"): (1, 3)}
    assert D.market_gap_stats(_gap_rows("20261106", {"A1": [(3, 21)]}), mk) == {(d, "KOSPI"): (0, 1)}   # 19분
    with pytest.raises(ValueError):
        D.mark_market_gap_days([], {}, None)
    with pytest.raises(ValueError):
        D.load_minute_days(_FakeConn({}), [("A1", d)], None)


def test_vwap_from_cumulative_amount():
    rows = [_row(0, 100.0, 10, amt=1000.0), _row(1, 200.0, 30, amt=7000.0)]
    bars, _, _, _ = D.assemble_day(rows)
    vw = D.vwap(bars)
    assert vw[0] == pytest.approx(100.0) and vw[1] == pytest.approx(7000.0 / 40)
    assert vw[2] == pytest.approx(7000.0 / 40)                   # 빈 분: 누적 유지


def test_checksum_and_digest():
    rows = [_row(0, 100.0, 10), _row(1, 200.0, 30)]
    assert D.raw_checksum(rows) == (2, 40.0, 300.0)
    a = {("000001", date(2026, 11, 10)): (2, 40.0, 300.0), ("000002", date(2026, 11, 10)): (1, 1.0, 1.0)}
    b = dict(reversed(list(a.items())))
    assert D.checksum_digest(a) == D.checksum_digest(b)
    a[("000002", date(2026, 11, 10))] = (1, 1.0, 1.5)
    assert D.checksum_digest(a) != D.checksum_digest(b)


def test_apply_daily_open_gap_and_prev_volume_units():
    bars, _, meta, _ = D.assemble_day(_full(10000.0))
    meta.code, meta.day = "000001", date(2026, 11, 10)
    prev = date(2026, 11, 9)
    daily = {("000001", meta.day): (10300.0, 10000.0, 500, 2.0), ("000001", prev): (9900.0, 9950.0, 1000, 1.0)}
    D.apply_daily(meta, bars, daily, prev)
    assert meta.open_gap_flag and meta.open_gap_pct == pytest.approx((10000 / 10300 - 1) * 100)
    assert meta.prev_close == 9950.0 and meta.prev_day_volume == pytest.approx(500.0)   # 1000 × 1.0 / 2.0
    assert meta.adj_changed is True and not meta.adj_null_prev and not meta.adj_null_entry
    daily[("000001", meta.day)] = (10100.0, 10000.0, 500, None)
    meta2 = D.DayMeta("000001", meta.day)
    D.apply_daily(meta2, bars, daily, prev)
    assert not meta2.open_gap_flag
    assert meta2.adj_null_entry and not meta2.adj_null_prev   # 당일 adj NULL = 1.0(COALESCE)
    assert meta2.adj_changed is False
    assert meta2.prev_day_volume == pytest.approx(1000.0)                  # 1000 × 1.0 / 1.0
    daily[("000001", prev)] = (9900.0, 9950.0, 1000, None)
    daily[("000001", meta.day)] = (10100.0, 10000.0, 500, 2.0)
    meta4 = D.DayMeta("000001", meta.day)
    D.apply_daily(meta4, bars, daily, prev)
    assert meta4.adj_null_prev and not meta4.adj_null_entry and meta4.adj_changed is True
    assert meta4.prev_day_volume == pytest.approx(500.0)
    daily[("000001", prev)] = (9900.0, 9950.0, 1000, 1.0)
    daily[("000001", meta.day)] = (10100.0, 10000.0, 500, 1.0)
    meta3 = D.DayMeta("000001", meta.day)
    D.apply_daily(meta3, bars, daily, prev)
    assert meta3.adj_changed is False and meta3.prev_day_volume == pytest.approx(1000.0)


class _FakeCur:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, args=()):
        self.conn.calls.append((sql, args))
        if "LAG(" in sql:
            self._rows = list(self.conn.gap_rows)
        elif "minute_candles" in sql:
            self._rows = self.conn.minute_rows(args)
        elif "DISTINCT date" in sql:
            lo, hi = date.fromisoformat(args[1]), date.fromisoformat(args[2])
            self._rows = [(d.isoformat(),) for d in self.conn.calendar if lo <= d <= hi]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, data, calendar=(), gap_rows=()):
        self.data, self.calls, self.calendar, self.gap_rows = data, [], sorted(calendar), gap_rows

    def cursor(self):
        return _FakeCur(self)

    def minute_rows(self, args):
        out = []
        for c, d in zip(*args):
            for r in self.data.get((c, d), []):
                out.append((c, d) + tuple(r))
        return out


def test_load_minute_days_phantom_day_never_read_and_missing_day_excluded():
    good, phantom, empty = date(2026, 10, 2), date(2026, 10, 6), date(2026, 10, 10)
    conn = _FakeConn({("000001", "20261002"): _full(), ("000001", "20261006"): _full(99.0)})
    cal = [date(2026, 10, 1), good, empty]
    bundle = D.load_minute_days(conn, [("000001", good), ("000001", phantom), ("000001", empty)], {}, calendar=cal)
    assert bundle.keys == [("000001", good)]
    assert bundle.bars.dtype == np.float32 and bundle.bars.shape == (1, E.N_SLOTS, E.N_FIELDS)
    assert bundle.excluded == {("000001", phantom): D.EXCL_PHANTOM, ("000001", empty): D.EXCL_NO_MINUTE}
    minute_args = [a for s, a in conn.calls if "minute_candles" in s and "LAG(" not in s]
    assert all("20261006" not in a[1] for a in minute_args)              # 유령일은 쿼리에도 없음
    assert bundle.checksums == {("000001", good): (E.N_CONT, 100.0 * E.N_CONT, 10000.0 * E.N_CONT)}


def test_load_minute_days_calendar_none_uses_min_date_over_all_codes():
    """B1 — 키는 (code, date) 정렬이라 첫 키 날짜 ≠ 최소 날짜. 더 이른 다른 종목 날짜가 phantom 으로 빠지면 안 된다."""
    late, early = date(2026, 10, 2), date(2026, 7, 2)
    cal = [date(2026, 6, 1), date(2026, 7, 1), early, date(2026, 9, 1), date(2026, 10, 1), late]
    gap_rows = [("20261002", "000001", [[100, 125]]), ("20261002", "000002", None)]   # 1/2 = 50% → 시장 사건
    conn = _FakeConn({("000001", "20261002"): _full(), ("999999", "20260702"): _full(5000.0)}, calendar=cal,
                     gap_rows=gap_rows)
    mk = {"000001": "KOSPI", "000002": "KOSPI", "999999": "KOSDAQ"}
    bundle = D.load_minute_days(conn, [("000001", late), ("999999", early)], mk, calendar=None)
    assert [m.market_gap_day for m in bundle.meta] == [True, False]
    assert bundle.unknown_market_codes == 0
    b2 = D.load_minute_days(_FakeConn({("000001", "20261002"): _full()}, calendar=cal, gap_rows=gap_rows),
                            [("000001", late)], {"000002": "KOSPI"})
    assert b2.unknown_market_codes == 1 and b2.meta[0].market_gap_day is False   # 000001 = UNKNOWN 군
    gap_args = [a for s, a in conn.calls if "LAG(" in s][0]
    assert sorted(gap_args[0]) == ["20260702", "20261002"] and gap_args[1] == D.GAP_MINUTES
    assert bundle.excluded == {}
    assert bundle.keys == [("000001", late), ("999999", early)]
    cal_args = [a for s, a in conn.calls if "DISTINCT date" in s][0]
    assert date.fromisoformat(cal_args[1]) <= date(2026, 6, 2)          # 최소 날짜 − 30일
    daily_args = [a for s, a in conn.calls if "daily_prices d" in s][0]
    assert ("999999", "2026-07-01") in set(zip(*daily_args))           # 전 거래일(prev_of)도 잡힘


def test_bundle_index_is_dict_lookup():
    b = D.MinuteBundle([("A", date(2026, 1, 2)), ("B", date(2026, 1, 2))], np.zeros((2, E.N_SLOTS, E.N_FIELDS)),
                       np.zeros((2, E.N_SLOTS), bool), [])
    assert b.index(("B", date(2026, 1, 2))) == 1 and isinstance(b._pos, dict)
    with pytest.raises(KeyError):
        b.index(("C", date(2026, 1, 2)))
